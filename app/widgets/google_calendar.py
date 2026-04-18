"""
Google Calendar 위젯 v5
- 왼쪽: MiniCalendar (드래그 범위 선택 최대 7일) + 캘린더 체크박스 목록
- 오른쪽: WeekStrip(1줄) + 24h 시간축 뷰
  - 이벤트: 시간대 정확한 배치, 겹침 처리
  - 이벤트 드래그: 날짜+시간 15분 단위 이동
  - 빈 시간대 드래그: 신규 이벤트 생성
- 이벤트 클릭: EventDetailDialog (상세/편집/삭제)
"""
import json
import logging
from datetime import datetime, timezone
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSplitter, QScrollArea, QFrame, QDialog,
    QStackedWidget, QCheckBox, QLineEdit, QDateTimeEdit, QTextEdit,
    QComboBox, QSizePolicy, QMessageBox,
)
from PySide6.QtCore import (
    Qt, QDate, QDateTime, QTime, QTimer, Signal, QRect, QSize,
    QMimeData, QByteArray, QPoint,
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QFont, QCursor, QDrag,
)
from app.ui.common import BaseWidget
from app.core.i18n import tr
from app.core.events import bus

logger = logging.getLogger(__name__)

# ── 시간 그리드 상수 ──────────────────────────────────────────────────────────
HOUR_H    = 64      # 1시간 높이(px)  ← 64px = 16px/15분
DAY_H     = 24 * HOUR_H   # = 1536px
SNAP_MIN  = 15      # 스냅 단위(분)
RULER_W   = 52      # 타임 룰러 폭(px)

_CAL_COLORS = [
    "#4285F4", "#EA4335", "#FBBC05", "#34A853",
    "#FF6D00", "#46BDC6", "#7986CB", "#E67C73",
    "#F4511E", "#0B8043", "#8E24AA", "#D50000",
]
_DAY_NAMES_JP = ["月", "火", "水", "木", "金", "土", "日"]


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def _cal_color(cal: dict, idx: int = 0) -> str:
    bg = cal.get("backgroundColor", "")
    return bg if bg else _CAL_COLORS[idx % len(_CAL_COLORS)]


def _cal_name(cal: dict) -> str:
    return cal.get("summaryOverride") or cal.get("summary") or cal.get("id", "")


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    try:
        c = QColor(hex_color)
        return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"
    except Exception as e:
        logger.debug(f"_hex_to_rgba 変換失敗 ({hex_color!r}): {e}")
        return f"rgba(66,133,244,{alpha})"


def _week_monday(date: QDate) -> QDate:
    return date.addDays(-(date.dayOfWeek() - 1))


def _week_sunday(date: QDate) -> QDate:
    """해당 날짜를 포함하는 주의 일요일(직전 또는 당일)을 반환."""
    return date.addDays(-((date.dayOfWeek() - 7) % 7))


def _min_to_y(minutes: int) -> float:
    return minutes / 60.0 * HOUR_H


def _y_to_min(y: float) -> int:
    """Y 좌표 → 시간(분, 0-1439), 15분 스냅."""
    m = int(y / HOUR_H * 60)
    m = max(0, min(23 * 60 + 59, (m // SNAP_MIN) * SNAP_MIN))
    return m


# ── MiniCalendar ──────────────────────────────────────────────────────────────

class MiniCalendarWidget(QWidget):
    """QPainter 기반 미니 달력. 드래그로 최대 7일 연속 범위 선택."""
    range_selected = Signal(QDate, QDate)
    month_changed  = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        today = QDate.currentDate()
        self._current_month = today.month()
        self._current_year  = today.year()
        self._sel_start: QDate = today
        self._sel_end:   QDate = today
        self._drag_anchor: QDate | None = None
        self._event_dates:  set  = set()
        self._event_colors: dict = {}
        self._is_dark = True
        self.setMinimumSize(200, 200)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMouseTracking(True)

    def set_theme(self, is_dark: bool):
        self._is_dark = is_dark; self.update()

    def set_range(self, start: QDate, end: QDate):
        self._sel_start = start; self._sel_end = end; self.update()

    def set_events(self, events: list, cal_colors: dict):
        self._event_dates.clear(); self._event_colors.clear()
        for ev in events:
            ds = (ev.get("start", {}).get("date") or
                  ev.get("start", {}).get("dateTime", ""))
            if not ds:
                continue
            try:
                p   = ds[:10].split("-")
                key = (int(p[0]), int(p[1]), int(p[2]))
                self._event_dates.add(key)
                color = cal_colors.get(ev.get("_calendar_id", ""), "#4285F4")
                self._event_colors.setdefault(key, [])
                if color not in self._event_colors[key]:
                    self._event_colors[key].append(color)
            except Exception as e:
                logger.debug(f"イベント日付パース失敗 ({ds!r}): {e}")
        self.update()

    def navigate(self, delta: int):
        m = self._current_month + delta
        y = self._current_year
        if m > 12: m = 1;  y += 1
        elif m < 1: m = 12; y -= 1
        self._current_month = m; self._current_year = y
        self.update(); self.month_changed.emit(y, m)

    def _date_at(self, x: float, y: float) -> QDate | None:
        W, H = self.width(), self.height()
        HEADER_H = 36; DAY_H_ROW = 20
        cell_w = W / 7
        cell_h = max(28, (H - HEADER_H - DAY_H_ROW) / 6)
        if y < HEADER_H + DAY_H_ROW:
            return None
        col = int(x / cell_w)
        row = int((y - HEADER_H - DAY_H_ROW) / cell_h)
        if col < 0 or col > 6 or row < 0:
            return None
        first_day = QDate(self._current_year, self._current_month, 1)
        start_col = (first_day.dayOfWeek() - 1) % 7
        day_idx   = row * 7 + col - start_col + 1
        if 1 <= day_idx <= first_day.daysInMonth():
            return QDate(self._current_year, self._current_month, day_idx)
        return None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        d = self._is_dark

        bg       = QColor("#1e1e1e" if d else "#ffffff")
        txt_c    = QColor("#e0e0e0" if d else "#212121")
        sub_c    = QColor("#888888")
        sat_c    = QColor("#42A5F5")   # 土: 파랑
        sun_c    = QColor("#EF5350")   # 日: 빨강
        today_bg = QColor("#1a73e8")
        sel_bg   = QColor("#1e4d78" if d else "#1a73e8")
        rng_bg   = QColor(30, 77, 120, 90) if d else QColor(26, 115, 232, 45)

        p.fillRect(0, 0, W, H, bg)
        HEADER_H = 36; DAY_H_ROW = 20
        cell_w = W / 7
        cell_h = max(28, (H - HEADER_H - DAY_H_ROW) / 6)

        p.setFont(QFont("Segoe UI", 11, QFont.Bold))
        p.setPen(QColor("#e0e0e0" if d else "#212121"))
        p.drawText(QRect(30, 0, W - 60, HEADER_H), Qt.AlignCenter,
                   f"{self._current_year}年 {self._current_month}月")
        p.setPen(QPen(sub_c, 1.5))
        p.setFont(QFont("Segoe UI", 14))
        p.drawText(QRect(4, 0, 26, HEADER_H), Qt.AlignCenter, "‹")
        p.drawText(QRect(W - 30, 0, 26, HEADER_H), Qt.AlignCenter, "›")

        p.setFont(QFont("Segoe UI", 9))
        for i, name in enumerate(_DAY_NAMES_JP):
            p.setPen(sat_c if i == 5 else (sun_c if i == 6 else sub_c))
            p.drawText(QRect(int(i * cell_w), HEADER_H, int(cell_w), DAY_H_ROW),
                       Qt.AlignCenter, name)

        first_day = QDate(self._current_year, self._current_month, 1)
        start_col = (first_day.dayOfWeek() - 1) % 7
        today     = QDate.currentDate()
        sel_s = self._sel_start; sel_e = self._sel_end

        row = 0; col = start_col
        for day in range(1, first_day.daysInMonth() + 1):
            cx = int(col * cell_w); cy = int(HEADER_H + DAY_H_ROW + row * cell_h)
            cw = int(cell_w);       ch = int(cell_h)
            qd  = QDate(self._current_year, self._current_month, day)
            key = (self._current_year, self._current_month, day)

            is_today  = (qd == today)
            is_sel_s  = (qd == sel_s); is_sel_e = (qd == sel_e)
            in_range  = (sel_s <= qd <= sel_e)
            is_single = (sel_s == sel_e)

            if in_range and not is_single:
                p.setPen(Qt.NoPen); p.setBrush(rng_bg)
                if is_sel_s or is_sel_e:
                    p.drawRoundedRect(cx, cy + 2, cw, ch - 4, 4, 4)
                else:
                    p.drawRect(cx, cy + 2, cw, ch - 4)

            R  = min(cw, ch) // 2 - 2
            ex = cx + cw // 2 - R; ey = cy + 2
            if is_today:
                p.setPen(Qt.NoPen); p.setBrush(today_bg)
                p.drawEllipse(ex, ey, R * 2, R * 2)
            elif is_sel_s or is_sel_e:
                p.setPen(Qt.NoPen); p.setBrush(sel_bg)
                p.drawEllipse(ex, ey, R * 2, R * 2)

            dow = qd.dayOfWeek()
            if is_today or is_sel_s or is_sel_e:
                p.setPen(QColor("white"))
            elif dow == 6:
                p.setPen(sat_c)
            elif dow == 7:
                p.setPen(sun_c)
            else:
                p.setPen(txt_c)
            p.setFont(QFont("Segoe UI", 10,
                            QFont.Bold if (is_today or is_sel_s or is_sel_e) else QFont.Normal))
            p.drawText(QRect(cx, cy + 1, cw, int(ch * 0.65)), Qt.AlignCenter, str(day))

            colors = self._event_colors.get(key, [])
            if colors:
                dot_r = 3; total = min(len(colors), 3)
                gap = dot_r * 2 + 2
                sx  = cx + cw // 2 - (total * gap) // 2
                dy  = cy + ch - dot_r - 3
                p.setPen(Qt.NoPen)
                for di, c in enumerate(colors[:3]):
                    p.setBrush(QColor(c))
                    p.drawEllipse(sx + di * gap, dy, dot_r * 2, dot_r * 2)

            col += 1
            if col == 7:
                col = 0; row += 1
        p.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        x, y = event.position().x(), event.position().y()
        if y < 36:
            W = self.width()
            if x < 30:       self.navigate(-1)
            elif x > W - 30: self.navigate(1)
            return
        d = self._date_at(x, y)
        if d:
            self._drag_anchor = d
            self._sel_start   = d
            self._sel_end     = d
            self.update()

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton) or self._drag_anchor is None:
            return
        d = self._date_at(event.position().x(), event.position().y())
        if d is None:
            return
        anchor = self._drag_anchor
        if d >= anchor:
            self._sel_start = anchor
            self._sel_end   = min(d, anchor.addDays(6))
        else:
            self._sel_start = max(d, anchor.addDays(-6))
            self._sel_end   = anchor
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_anchor is not None:
            self._drag_anchor = None
            self.range_selected.emit(self._sel_start, self._sel_end)

    def sizeHint(self):
        return QSize(220, 220)


# ── WeekStrip (1줄) ───────────────────────────────────────────────────────────

class _WeekStrip(QWidget):
    date_clicked = Signal(QDate)
    _H = 44

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sel_start = QDate.currentDate()
        self._sel_end   = QDate.currentDate()
        self._event_dates: set = set()
        self._is_dark = True
        self.setFixedHeight(self._H)
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def set_range(self, start: QDate, end: QDate):
        self._sel_start = start; self._sel_end = end; self.update()

    def set_event_dates(self, dates: set):
        self._event_dates = dates; self.update()

    def set_theme(self, is_dark: bool):
        self._is_dark = is_dark; self.update()

    def _week_start(self) -> QDate:
        return _week_sunday(self._sel_start)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        d = self._is_dark

        bg    = QColor("#252526" if d else "#f8f9fa")
        txt   = QColor("#e0e0e0" if d else "#3c4043")
        sub   = QColor("#888888" if d else "#70757a")
        sat_c   = QColor("#4285F4")   # 土: 파랑
        sun_c   = QColor("#EA4335")   # 日: 빨강
        today_c = QColor("#1a73e8")
        sel_c   = QColor("#0e639c" if d else "#1a73e8")
        rng_c   = QColor(30, 77, 120, 100) if d else QColor(26, 115, 232, 40)

        p.fillRect(0, 0, W, H, bg)

        cell_w = W / 7.0; today = QDate.currentDate(); ws = self._week_start()

        range_cells = [i for i in range(7)
                       if self._sel_start <= ws.addDays(i) <= self._sel_end]
        if len(range_cells) > 1:
            x0 = int(range_cells[0]  * cell_w + cell_w * 0.1)
            x1 = int(range_cells[-1] * cell_w + cell_w * 0.9)
            bar_y = (H - 28) // 2
            p.setPen(Qt.NoPen); p.setBrush(rng_c)
            p.drawRoundedRect(x0, bar_y, x1 - x0, 28, 14, 14)

        R = 13
        for i in range(7):
            dd  = ws.addDays(i); cx = i * cell_w; mid = cx + cell_w / 2
            is_today = (dd == today)
            in_range = (self._sel_start <= dd <= self._sel_end)
            has_ev   = (dd.year(), dd.month(), dd.day()) in self._event_dates
            dow      = dd.dayOfWeek()

            p.setFont(QFont("Segoe UI", 8))
            name_col = sat_c if dow == 6 else (sun_c if dow == 7 else sub)
            p.setPen(name_col)
            p.drawText(QRect(int(cx), 2, int(cell_w * 0.44), H),
                       Qt.AlignCenter, _DAY_NAMES_JP[dow - 1])

            num_cx = int(mid + cell_w * 0.07 - R); num_cy = (H - R * 2) // 2
            if is_today:
                p.setPen(Qt.NoPen); p.setBrush(today_c)
                p.drawEllipse(num_cx, num_cy, R * 2, R * 2)
                p.setPen(QColor("white"))
            elif in_range and len(range_cells) == 1:
                p.setPen(Qt.NoPen); p.setBrush(sel_c)
                p.drawEllipse(num_cx, num_cy, R * 2, R * 2)
                p.setPen(QColor("white"))
            elif in_range:
                p.setPen(QColor("white"))
            else:
                p.setPen(sat_c if dow == 6 else (sun_c if dow == 7 else txt))

            p.setFont(QFont("Segoe UI", 10,
                            QFont.Bold if (is_today or in_range) else QFont.Normal))
            p.drawText(QRect(num_cx, num_cy, R * 2, R * 2), Qt.AlignCenter, str(dd.day()))

            if has_ev:
                dot_y = num_cy + R * 2 + 2
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("white") if (is_today or in_range) else today_c)
                p.drawEllipse(int(mid) - 3, dot_y, 6, 6)
        p.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        i = int(event.position().x() / (self.width() / 7))
        if 0 <= i <= 6:
            d = self._week_start().addDays(i)
            self._sel_start = d; self._sel_end = d
            self.update(); self.date_clicked.emit(d)


# ── DayColHeader (1줄) ────────────────────────────────────────────────────────

class _DayColHeader(QWidget):
    H = 36

    def __init__(self, parent=None):
        super().__init__(parent)
        self._date = QDate.currentDate()
        self._is_today = False; self._is_sel = False; self._is_dark = True
        self.setFixedHeight(self.H)

    def set_date(self, date: QDate, is_today: bool, is_sel: bool):
        self._date = date; self._is_today = is_today; self._is_sel = is_sel
        self.update()

    def set_theme(self, is_dark: bool):
        self._is_dark = is_dark; self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.H
        d = self._is_dark

        bg      = QColor("#252526" if d else "#f8f9fa")
        txt     = QColor("#e0e0e0" if d else "#3c4043")
        sub     = QColor("#888" if d else "#70757a")
        sat_c   = QColor("#4285F4")   # 土: 파랑
        sun_c   = QColor("#EA4335")   # 日: 빨강
        today_c = QColor("#1a73e8"); sel_c = QColor("#0e639c" if d else "#1a73e8")

        p.fillRect(0, 0, W, H, bg)
        dow = self._date.dayOfWeek()
        name_col = sat_c if dow == 6 else (sun_c if dow == 7 else sub)

        p.setFont(QFont("Segoe UI", 8))
        p.setPen(name_col)
        p.drawText(QRect(0, 0, int(W * 0.38), H), Qt.AlignCenter, _DAY_NAMES_JP[dow - 1])

        R   = min(H, int(W * 0.62)) // 2 - 2
        mid = int(W * 0.38) + int(W * 0.62) // 2
        oy  = (H - R * 2) // 2
        if self._is_today:
            p.setPen(Qt.NoPen); p.setBrush(today_c)
            p.drawEllipse(mid - R, oy, R * 2, R * 2); p.setPen(QColor("white"))
        elif self._is_sel:
            p.setPen(Qt.NoPen); p.setBrush(sel_c)
            p.drawEllipse(mid - R, oy, R * 2, R * 2); p.setPen(QColor("white"))
        else:
            p.setPen(sat_c if dow == 6 else (sun_c if dow == 7 else txt))

        p.setFont(QFont("Segoe UI", 10,
                        QFont.Bold if (self._is_today or self._is_sel) else QFont.Normal))
        p.drawText(QRect(mid - R, oy, R * 2, R * 2), Qt.AlignCenter, str(self._date.day()))
        p.end()


# ── TimeRuler ─────────────────────────────────────────────────────────────────

class _TimeRuler(QWidget):
    """시간 레이블(00:00~23:00) 세로 눈금자."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark = True
        self.setFixedWidth(RULER_W)
        self.setFixedHeight(DAY_H)

    def set_theme(self, is_dark: bool):
        self._is_dark = is_dark; self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        d = self._is_dark
        p.fillRect(0, 0, RULER_W, DAY_H, QColor("#1e1e1e" if d else "#ffffff"))
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor("#666666" if d else "#70757a"))
        for hour in range(1, 24):
            y = int(hour * HOUR_H)
            p.drawText(QRect(0, y - 9, RULER_W - 6, 18),
                       Qt.AlignRight | Qt.AlignVCenter, f"{hour:02d}:00")
        p.end()


# ── TimedDayColumn ────────────────────────────────────────────────────────────

_RESIZE_EDGE_PX = 8   # 상단/하단 리사이즈 핸들 영역(px)


class _TimedDayColumn(QWidget):
    """24시간 시간축 기반 하루 열 위젯."""
    event_clicked    = Signal(dict)
    event_dropped    = Signal(dict, QDate, int)   # (ev, new_date, new_start_min)
    event_resized    = Signal(dict, int, int)      # (ev, new_start_min, new_end_min)
    create_requested = Signal(QDate, int, int)    # (date, start_min, end_min)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._date:       QDate = QDate.currentDate()
        self._events:     list  = []
        self._cal_colors: dict  = {}
        self._is_dark:    bool  = True
        self._is_today:   bool  = False
        self._layout_cache: list | None = None

        # 드래그 상태
        self._press_pos:       QPoint | None = None
        self._press_ev:        dict | None   = None
        self._press_offset:    int           = 0
        self._creating:        bool          = False
        self._create_s:        int           = 0
        self._create_e:        int           = 0
        # 드롭 고스트 상태 (이벤트 이동 드래그 수신 시)
        self._drop_y:          int | None    = None
        self._drop_duration:   int           = 60   # 드롭 고스트 지속 시간(분)
        self._drop_offset_min: int           = 0    # 이벤트 내 클릭 오프셋(분)
        # 리사이즈 상태 (이벤트 상단/하단 가장자리 드래그)
        self._resizing:        bool          = False
        self._resize_ev:       dict | None   = None
        self._resize_edge:     str | None    = None  # 'top' | 'bottom'
        self._resize_s_min:    int           = 0
        self._resize_e_min:    int           = 0

        self.setFixedHeight(DAY_H)
        self.setMinimumWidth(60)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)

    def set_day(self, date: QDate, events: list, cal_colors: dict,
                is_today: bool = False, is_selected: bool = False):
        self._date         = date
        self._events       = events
        self._cal_colors   = cal_colors
        self._is_today     = is_today
        self._layout_cache = None
        self.update()

    def set_theme(self, is_dark: bool):
        self._is_dark      = is_dark
        self._layout_cache = None
        self.update()

    # ── 레이아웃 계산 ──────────────────────────────────────────────────────────

    def _get_layout(self) -> list:
        if self._layout_cache is not None:
            return self._layout_cache

        timed = []
        for ev in self._events:
            start = ev.get("start", {}); end_d = ev.get("end", {})
            if "date" in start:
                continue   # 종일 이벤트는 별도 처리
            try:
                s_dt  = datetime.fromisoformat(
                    start["dateTime"].replace("Z", "+00:00")).astimezone()
                e_dt  = datetime.fromisoformat(
                    end_d["dateTime"].replace("Z", "+00:00")).astimezone()
                s_min = s_dt.hour * 60 + s_dt.minute
                e_min = e_dt.hour * 60 + e_dt.minute
                e_min = max(s_min + SNAP_MIN, min(e_min, 24 * 60))
                timed.append({"ev": ev, "s_min": s_min, "e_min": e_min})
            except Exception as e:
                logger.debug(f"イベントレイアウト計算スキップ: {e}")
                continue

        timed.sort(key=lambda x: (x["s_min"], -(x["e_min"] - x["s_min"])))

        # 겹침 열 할당
        active: list[tuple[int, int]] = []
        for item in timed:
            active = [(e, c) for e, c in active if e > item["s_min"]]
            used   = {c for _, c in active}
            col    = 0
            while col in used:
                col += 1
            active.append((item["e_min"], col))
            item["col"] = col

        for item in timed:
            max_c = item["col"]
            for other in timed:
                if other is item:
                    continue
                if other["s_min"] < item["e_min"] and other["e_min"] > item["s_min"]:
                    max_c = max(max_c, other["col"])
            item["total_cols"] = max_c + 1

        self._layout_cache = timed
        return timed

    def _ev_rect(self, item: dict) -> QRect:
        W     = self.width()
        col   = item["col"]; total = item["total_cols"]
        MARG  = 2
        col_w = max(1, (W - MARG * 2) / total)
        x     = int(MARG + col * col_w) + 1
        w     = max(4, int(col_w) - 2)
        y     = int(_min_to_y(item["s_min"]))
        h     = max(SNAP_MIN, int(_min_to_y(item["e_min"])) - y)
        return QRect(x, y, w, h)

    def _allday_events(self) -> list:
        return [ev for ev in self._events if "date" in ev.get("start", {})]

    # ── 그리기 ────────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W = self.width()
        d = self._is_dark

        bg_c    = QColor("#1e1e1e" if d else "#ffffff")
        grid_c  = QColor("#2e2e2e" if d else "#dadce0")   # 시간선 강화
        half_c  = QColor("#262626" if d else "#edeef0")   # 30분선
        now_c   = QColor("#EA4335")
        txt_c   = QColor("#e0e0e0" if d else "#212121")
        allday_bg = QColor("#252526" if d else "#eef1ff")

        p.fillRect(0, 0, W, DAY_H, bg_c)

        # 오늘 열 파란 틴트 — 한눈에 구분
        if self._is_today:
            tint = QColor("#1a73e8"); tint.setAlpha(14 if d else 9)
            p.fillRect(0, 0, W, DAY_H, tint)

        # 종일 이벤트 (상단 고정 칩)
        allday = self._allday_events()
        for ai, ev in enumerate(allday):
            cal_id = ev.get("_calendar_id", "")
            color  = QColor(self._cal_colors.get(cal_id, "#4285F4"))
            chip_bg = QColor(color); chip_bg.setAlpha(60 if d else 45)
            cy_ad = ai * 22
            p.setPen(Qt.NoPen); p.setBrush(chip_bg)
            p.drawRoundedRect(2, cy_ad, W - 4, 20, 3, 3)
            # 왼쪽 강조 바 (종일 이벤트)
            p.setBrush(color)
            p.drawRoundedRect(2, cy_ad, 3, 20, 1, 1)
            p.setPen(txt_c); p.setFont(QFont("Segoe UI", 7))
            p.drawText(QRect(8, cy_ad + 2, W - 12, 16), Qt.AlignLeft | Qt.AlignVCenter,
                       (ev.get("summary", "") or "")[:20])

        # 시간 그리드선
        for hour in range(24):
            y = int(hour * HOUR_H)
            p.setPen(QPen(grid_c, 1)); p.drawLine(0, y, W, y)
            half_y = int(hour * HOUR_H + HOUR_H / 2)
            pen = QPen(half_c, 1, Qt.DashLine)
            p.setPen(pen); p.drawLine(0, half_y, W, half_y)

        resize_id = self._resize_ev.get("id", "") if self._resize_ev else ""

        # 시간 지정 이벤트
        for item in self._get_layout():
            ev    = item["ev"]
            # 리사이즈 중인 이벤트: 원래 위치 스킵 → 아래에서 고스트로 그림
            if self._resizing and ev.get("id") == resize_id:
                continue

            rect  = self._ev_rect(item)
            cal_id = ev.get("_calendar_id", "")
            color  = QColor(self._cal_colors.get(cal_id, "#4285F4"))

            ev_bg = QColor(color); ev_bg.setAlpha(85 if d else 65)
            border_c = QColor(color); border_c.setAlpha(190 if d else 230)
            # 배경
            p.setPen(Qt.NoPen); p.setBrush(ev_bg)
            p.drawRoundedRect(rect, 3, 3)
            # 테두리 (이벤트 색상 반투명)
            p.setPen(QPen(border_c, 1)); p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect, 3, 3)
            # 왼쪽 강조 바 (4px 솔리드)
            p.setPen(Qt.NoPen); p.setBrush(color)
            p.drawRoundedRect(rect.x(), rect.y(), 4, rect.height(), 2, 2)

            # 제목 — 이벤트 배경 위에서 가독성 높은 색상 사용
            title = ev.get("summary", tr("(タイトルなし)"))
            ev_txt_c = QColor("#f5f5f5" if d else "#1a1a1a")
            p.setPen(ev_txt_c)
            if rect.height() >= 18:
                p.setFont(QFont("Segoe UI", 8, QFont.Bold))
                t_rect = QRect(rect.x() + 6, rect.y() + 2,
                               rect.width() - 8, min(14, rect.height() - 4))
                p.drawText(t_rect, Qt.AlignLeft | Qt.AlignVCenter,
                           title[:28] + ("…" if len(title) > 28 else ""))
            # 시간 레이블 (높이 충분하면 시작~종료 함께 표시)
            if rect.height() >= 34:
                s_h, s_m = divmod(item["s_min"], 60)
                e_h, e_m = divmod(item["e_min"], 60)
                p.setFont(QFont("Segoe UI", 7))
                p.setPen(QColor("#d0d0d0" if d else "#444444"))
                time_str = (f"{s_h:02d}:{s_m:02d}–{e_h:02d}:{e_m:02d}"
                            if rect.height() >= 50 else f"{s_h:02d}:{s_m:02d}")
                p.drawText(QRect(rect.x() + 6, rect.y() + 17, rect.width() - 8, 13),
                           Qt.AlignLeft, time_str)
                p.setPen(ev_txt_c)

        # 리사이즈 고스트 (리사이즈 중인 이벤트를 새 시간으로 표시)
        if self._resizing and self._resize_ev is not None:
            for item in self._get_layout():
                if item["ev"].get("id") == resize_id:
                    ghost_item = dict(item)
                    ghost_item["s_min"] = self._resize_s_min
                    ghost_item["e_min"] = self._resize_e_min
                    ghost_rect = self._ev_rect(ghost_item)
                    cal_id = self._resize_ev.get("_calendar_id", "")
                    color  = QColor(self._cal_colors.get(cal_id, "#4285F4"))
                    ev_bg  = QColor(color); ev_bg.setAlpha(130 if d else 100)
                    border = QColor(color); border.setAlpha(230)
                    p.setPen(Qt.NoPen); p.setBrush(ev_bg)
                    p.drawRoundedRect(ghost_rect, 3, 3)
                    p.setPen(QPen(border, 1.5)); p.setBrush(Qt.NoBrush)
                    p.drawRoundedRect(ghost_rect, 3, 3)
                    # 왼쪽 강조 바
                    p.setPen(Qt.NoPen); p.setBrush(color)
                    p.drawRoundedRect(ghost_rect.x(), ghost_rect.y(), 4, ghost_rect.height(), 2, 2)
                    # 시간 레이블
                    if ghost_rect.height() >= 18:
                        p.setPen(QColor("#f5f5f5" if d else "#1a1a1a"))
                        p.setFont(QFont("Segoe UI", 7, QFont.Bold))
                        s_h, s_m = divmod(self._resize_s_min, 60)
                        e_h, e_m = divmod(self._resize_e_min, 60)
                        p.drawText(QRect(ghost_rect.x() + 6, ghost_rect.y() + 2,
                                         ghost_rect.width() - 8, 12),
                                   Qt.AlignLeft, f"{s_h:02d}:{s_m:02d}–{e_h:02d}:{e_m:02d}")
                    break

        # 신규 이벤트 드래그 고스트
        if self._creating and self._create_e > self._create_s:
            y1 = int(_min_to_y(self._create_s))
            y2 = int(_min_to_y(self._create_e))
            gc = QColor("#1a73e8"); gc.setAlpha(90)
            p.setPen(QPen(QColor("#1a73e8"), 1))
            p.setBrush(gc)
            p.drawRoundedRect(2, y1, W - 4, max(4, y2 - y1), 3, 3)
            p.setPen(QColor("white"))
            p.setFont(QFont("Segoe UI", 7, QFont.Bold))
            s_h, s_m = divmod(self._create_s, 60)
            e_h, e_m = divmod(self._create_e, 60)
            p.drawText(QRect(5, y1 + 2, W - 8, 12), Qt.AlignLeft,
                       f"{s_h:02d}:{s_m:02d} – {e_h:02d}:{e_m:02d}")

        # 드롭 위치 투명 고스트 블록
        if self._drop_y is not None:
            drop_m  = _y_to_min(self._drop_y)
            gs_min  = max(0, (drop_m - self._drop_offset_min) // SNAP_MIN * SNAP_MIN)
            ge_min  = min(24 * 60, gs_min + max(SNAP_MIN, self._drop_duration))
            gy1     = int(_min_to_y(gs_min))
            gy2     = int(_min_to_y(ge_min))
            gh      = max(8, gy2 - gy1)
            ghost_fill = QColor("#1a73e8"); ghost_fill.setAlpha(55)
            ghost_bd   = QColor("#1a73e8"); ghost_bd.setAlpha(200)
            p.setPen(QPen(ghost_bd, 1.5))
            p.setBrush(ghost_fill)
            p.drawRoundedRect(2, gy1, W - 4, gh, 3, 3)
            # 시작 시각 표시
            p.setPen(QColor("white"))
            p.setFont(QFont("Segoe UI", 7, QFont.Bold))
            gs_h, gs_m = divmod(gs_min, 60)
            ge_h, ge_m = divmod(ge_min, 60)
            p.drawText(QRect(6, gy1 + 2, W - 8, 12), Qt.AlignLeft,
                       f"{gs_h:02d}:{gs_m:02d}–{ge_h:02d}:{ge_m:02d}")

        # 현재 시각선
        if self._is_today:
            now = datetime.now().astimezone()
            ny  = int(_min_to_y(now.hour * 60 + now.minute))
            p.setPen(QPen(now_c, 2)); p.setBrush(now_c)
            p.drawEllipse(-2, ny - 4, 8, 8)
            p.drawLine(5, ny, W, ny)

        p.end()

    # ── 이벤트 히트 테스트 ─────────────────────────────────────────────────────

    def _ev_at(self, pos: QPoint) -> tuple[dict, int] | None:
        for item in self._get_layout():
            rect = self._ev_rect(item)
            if rect.contains(pos):
                offset = _y_to_min(pos.y()) - item["s_min"]
                return item["ev"], max(0, offset)
        return None

    def _ev_resize_edge_at(self, pos: QPoint) -> tuple[dict, str] | None:
        """이벤트 상단/하단 _RESIZE_EDGE_PX 내 범위 검사. (ev, 'top'|'bottom') or None."""
        for item in self._get_layout():
            rect = self._ev_rect(item)
            if not (rect.left() <= pos.x() <= rect.right()):
                continue
            if abs(pos.y() - rect.top()) <= _RESIZE_EDGE_PX:
                return item["ev"], "top"
            if (rect.height() > _RESIZE_EDGE_PX * 2 and
                    abs(pos.y() - rect.bottom()) <= _RESIZE_EDGE_PX):
                return item["ev"], "bottom"
        return None

    # ── 마우스 이벤트 ─────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        self._press_pos = e.position().toPoint()

        # 리사이즈 엣지 우선 검사
        edge_result = self._ev_resize_edge_at(self._press_pos)
        if edge_result:
            ev, edge = edge_result
            self._resize_ev   = ev
            self._resize_edge = edge
            # 원래 시간 초기화
            for item in self._get_layout():
                if item["ev"].get("id") == ev.get("id"):
                    self._resize_s_min = item["s_min"]
                    self._resize_e_min = item["e_min"]
                    break
            self._resizing = True
            return

        result = self._ev_at(self._press_pos)
        if result:
            self._press_ev, self._press_offset = result
        else:
            self._press_ev = None; self._press_offset = 0
            self._create_s = _y_to_min(e.position().y())
            self._create_e = self._create_s + SNAP_MIN
            self._creating = False
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if not (e.buttons() & Qt.LeftButton):
            # 호버 커서: 리사이즈 엣지 → 세로 리사이즈 / 이벤트 위 → 포인터 / 빈 영역 → 십자
            pos = e.position().toPoint()
            edge = self._ev_resize_edge_at(pos)
            if edge:
                self.setCursor(QCursor(Qt.SizeVerCursor))
            else:
                result = self._ev_at(pos)
                self.setCursor(QCursor(Qt.PointingHandCursor if result else Qt.CrossCursor))
            return

        # 리사이즈 모드
        if self._resizing and self._resize_ev is not None:
            cur_min = _y_to_min(e.position().y())
            if self._resize_edge == "top":
                self._resize_s_min = max(0, min(cur_min, self._resize_e_min - SNAP_MIN))
            else:
                self._resize_e_min = min(24 * 60, max(cur_min, self._resize_s_min + SNAP_MIN))
            self.update()
            return

        if self._press_pos is None:
            return
        if (e.position().toPoint() - self._press_pos).manhattanLength() < 8:
            return

        if self._press_ev is not None:
            # 기존 이벤트 드래그 이동
            ev = self._press_ev; offset = self._press_offset
            self._press_pos = None; self._press_ev = None
            mime = QMimeData()
            mime.setData("application/x-calendar-event", QByteArray(
                json.dumps({"ev": ev, "drag_offset_min": offset},
                           ensure_ascii=False).encode()
            ))
            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.exec(Qt.MoveAction)
        else:
            # 드래그로 신규 이벤트 범위 선택
            em = _y_to_min(e.position().y())
            self._create_e = max(em + SNAP_MIN, self._create_s + SNAP_MIN)
            self._creating = True
            self.update()

        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return

        # 리사이즈 완료
        if self._resizing and self._resize_ev is not None:
            self.event_resized.emit(self._resize_ev, self._resize_s_min, self._resize_e_min)
            self._resizing    = False
            self._resize_ev   = None
            self._resize_edge = None
            self.update()
            super().mouseReleaseEvent(e)
            return

        if self._creating:
            if self._create_e > self._create_s:
                self.create_requested.emit(self._date, self._create_s, self._create_e)
        elif self._press_ev is not None:
            self.event_clicked.emit(self._press_ev)
        # 빈 곳 단순 클릭은 무시 (드래그 생성만 지원)
        self._press_pos = None; self._press_ev = None
        self._creating  = False
        self.update()
        super().mouseReleaseEvent(e)

    # ── 드래그 앤 드롭 수신 ───────────────────────────────────────────────────

    def _parse_drop_mime(self, mime_data) -> None:
        """MIME 데이터에서 드롭 고스트용 duration/offset 추출."""
        try:
            raw  = json.loads(bytes(mime_data.data("application/x-calendar-event")).decode())
            ev   = raw.get("ev", raw) if isinstance(raw, dict) and "ev" in raw else raw
            off  = raw.get("drag_offset_min", 0) if isinstance(raw, dict) else 0
            self._drop_offset_min = int(off)
            start = ev.get("start", {}); end_d = ev.get("end", {})
            if "dateTime" in start and "dateTime" in end_d:
                s_dt = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
                e_dt = datetime.fromisoformat(end_d["dateTime"].replace("Z", "+00:00"))
                self._drop_duration = max(SNAP_MIN, int((e_dt - s_dt).total_seconds() / 60))
            else:
                self._drop_duration = 24 * 60   # 종일 이벤트
        except Exception as e:
            logger.debug(f"ドロップデータ解析失敗 (デフォルト60分): {e}")
            self._drop_duration = 60; self._drop_offset_min = 0

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat("application/x-calendar-event"):
            self._parse_drop_mime(e.mimeData())
            self._drop_y = int(e.position().y()); self.update()
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat("application/x-calendar-event"):
            self._drop_y = int(e.position().y()); self.update()
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self._drop_y = None; self.update()

    def dropEvent(self, e):
        self._drop_y = None; self.update()
        if not e.mimeData().hasFormat("application/x-calendar-event"):
            e.ignore(); return
        try:
            raw  = json.loads(
                bytes(e.mimeData().data("application/x-calendar-event")).decode())
            ev   = raw.get("ev", raw) if isinstance(raw, dict) and "ev" in raw else raw
            off  = raw.get("drag_offset_min", 0) if isinstance(raw, dict) else 0
            drop_min      = _y_to_min(e.position().y())
            new_start_min = max(0, (drop_min - off) // SNAP_MIN * SNAP_MIN)
            self.event_dropped.emit(ev, self._date, new_start_min)
            e.acceptProposedAction()
        except Exception as exc:
            logger.warning(f"Drop parse error: {exc}"); e.ignore()


# ── MultiDayView ─────────────────────────────────────────────────────────────

class _MultiDayView(QWidget):
    """타임 룰러 + 선택 범위(1~7일) 열 뷰."""
    event_clicked    = Signal(dict)
    event_dropped    = Signal(dict, QDate, int)
    event_resized    = Signal(dict, int, int)      # (ev, new_start_min, new_end_min)
    create_requested = Signal(QDate, int, int)

    _MAX_COLS = 7

    def __init__(self, parent=None):
        super().__init__(parent)
        self._columns:  list[_TimedDayColumn] = []
        self._headers:  list[_DayColHeader]   = []
        self._col_seps: list[QFrame]          = []
        self._build_ui()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # ── 헤더 행 (스크롤 없음) ─────────────────────────────────────────────
        hdr_row = QWidget(); hdr_row.setFixedHeight(_DayColHeader.H)
        hl = QHBoxLayout(hdr_row)
        hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(0)

        spacer = QWidget(); spacer.setFixedWidth(RULER_W); hl.addWidget(spacer)
        rs = QFrame(); rs.setObjectName("colSep")
        rs.setFrameShape(QFrame.VLine); rs.setFixedWidth(1); hl.addWidget(rs)

        for i in range(self._MAX_COLS):
            hdr = _DayColHeader(); self._headers.append(hdr)
            hl.addWidget(hdr, 1)
            if i < self._MAX_COLS - 1:
                sep = QFrame(); sep.setObjectName("colSep")
                sep.setFrameShape(QFrame.VLine); sep.setFixedWidth(1)
                self._col_seps.append(sep); hl.addWidget(sep)
        main.addWidget(hdr_row)

        sep_line = QFrame(); sep_line.setObjectName("colHdrSep")
        sep_line.setFrameShape(QFrame.HLine); sep_line.setFixedHeight(1)
        main.addWidget(sep_line)

        # ── 스크롤 영역 ───────────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        inner = QWidget(); inner.setMinimumHeight(DAY_H)
        il = QHBoxLayout(inner)
        il.setContentsMargins(0, 0, 0, 0); il.setSpacing(0)

        self._ruler = _TimeRuler(); il.addWidget(self._ruler)
        rs2 = QFrame(); rs2.setObjectName("colSep")
        rs2.setFrameShape(QFrame.VLine); rs2.setFixedWidth(1); il.addWidget(rs2)

        for i in range(self._MAX_COLS):
            col = _TimedDayColumn()
            col.event_clicked.connect(self.event_clicked)
            col.event_dropped.connect(self.event_dropped)
            col.event_resized.connect(self.event_resized)
            col.create_requested.connect(self.create_requested)
            self._columns.append(col); il.addWidget(col, 1)

        self._scroll.setWidget(inner)
        main.addWidget(self._scroll, 1)

        # 초기 스크롤: 오전 8시
        QTimer.singleShot(150, lambda: self._scroll.verticalScrollBar().setValue(
            max(0, int(8 * HOUR_H - self._scroll.height() / 3))
        ))

    def update_view(self, sel_start: QDate, sel_end: QDate,
                    events: list, cal_colors: dict):
        n_days = min(max(sel_start.daysTo(sel_end) + 1, 1), self._MAX_COLS)
        today  = QDate.currentDate()

        dke: dict[str, list] = {}
        for ev in events:
            ds = (ev.get("start", {}).get("date") or
                  ev.get("start", {}).get("dateTime", ""))[:10]
            if ds:
                dke.setdefault(ds, []).append(ev)

        for i in range(self._MAX_COLS):
            if i < n_days:
                self._columns[i].show(); self._headers[i].show()
                d   = sel_start.addDays(i)
                key = f"{d.year()}-{d.month():02d}-{d.day():02d}"
                self._columns[i].set_day(d, dke.get(key, []), cal_colors,
                                          is_today=(d == today), is_selected=True)
                self._headers[i].set_date(d, d == today, True)
            else:
                self._columns[i].hide(); self._headers[i].hide()

        for i, sep in enumerate(self._col_seps):
            sep.setVisible(i < n_days - 1)

    def set_theme(self, is_dark: bool):
        self._ruler.set_theme(is_dark)
        for col in self._columns:
            col.set_theme(is_dark)
        for hdr in self._headers:
            hdr.set_theme(is_dark)


# ── EventDetailDialog ─────────────────────────────────────────────────────────

class EventDetailDialog(QDialog):
    event_saved   = Signal(str, dict, str)
    event_deleted = Signal(str, str)

    def __init__(self, ev: dict, cal_colors: dict, calendars: list,
                 is_dark: bool = True, parent=None):
        super().__init__(parent)
        self._ev = ev; self._cal_colors = cal_colors
        self._calendars = calendars; self._is_dark = is_dark
        self.setWindowTitle(ev.get("summary", tr("イベント詳細")))
        self.setMinimumWidth(440); self.setModal(True)
        self._build_ui(); self._apply_theme()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setSpacing(0); main.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_detail_page())
        self._stack.addWidget(self._build_edit_page())
        main.addWidget(self._stack)

    def _build_detail_page(self) -> QWidget:
        w = QWidget(); layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 20, 24, 20); layout.setSpacing(10)

        ev = self._ev; cal_id = ev.get("_calendar_id", "")
        color = self._cal_colors.get(cal_id, "#4285F4")

        title_row = QHBoxLayout()
        bar = QFrame(); bar.setFixedSize(4, 40)
        bar.setStyleSheet(f"background: {color}; border-radius: 2px;")
        title_lbl = QLabel(ev.get("summary", tr("(タイトルなし)")))
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; padding-left: 4px;")
        title_lbl.setWordWrap(True)
        title_row.addWidget(bar); title_row.addWidget(title_lbl, 1)
        layout.addLayout(title_row)

        start = ev.get("start", {}); end = ev.get("end", {})
        if "date" in start:
            time_str = f"🗓  {tr('終日')}  {start['date']}"
        else:
            try:
                s_dt = datetime.fromisoformat(
                    start.get("dateTime", "").replace("Z", "+00:00")).astimezone()
                e_dt = datetime.fromisoformat(
                    end.get("dateTime", "").replace("Z", "+00:00")).astimezone()
                time_str = (f"🕐  {s_dt.strftime('%Y/%m/%d %H:%M')} "
                            f"– {e_dt.strftime('%H:%M')}")
            except Exception as e:
                logger.debug(f"イベント時刻フォーマット失敗 (フォールバック): {e}")
                s = start.get("dateTime", "")[:16].replace("T", " ")
                e = end.get("dateTime", "")[-5:]
                time_str = f"🕐  {s} – {e}"
        time_lbl = QLabel(time_str)
        time_lbl.setStyleSheet("font-size: 13px; color: #888; padding-left: 8px;")
        layout.addWidget(time_lbl)

        cal_obj  = next((c for c in self._calendars if c.get("id") == cal_id), {})
        cal_name = _cal_name(cal_obj) if cal_obj else cal_id
        cal_lbl  = QLabel(f"●  {cal_name}")
        cal_lbl.setStyleSheet(
            f"font-size: 12px; color: {color}; padding-left: 8px; font-weight: 600;")
        layout.addWidget(cal_lbl)

        memo = ev.get("description", "").strip()
        if memo:
            sep_l = QFrame(); sep_l.setFrameShape(QFrame.HLine)
            layout.addWidget(sep_l)
            memo_lbl = QLabel(memo)
            memo_lbl.setStyleSheet("font-size: 12px; color: #999; padding-left: 8px;")
            memo_lbl.setWordWrap(True); layout.addWidget(memo_lbl)

        layout.addStretch()
        sep = QFrame(); sep.setFrameShape(QFrame.HLine); layout.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_edit = QPushButton(f"✏  {tr('編集')}")
        btn_edit.setObjectName("secondaryActionBtn"); btn_edit.setFixedHeight(32)
        btn_edit.setCursor(Qt.PointingHandCursor); btn_edit.clicked.connect(self._switch_to_edit)
        btn_del = QPushButton(f"🗑  {tr('削除')}")
        btn_del.setObjectName("deleteBtnDlg"); btn_del.setFixedHeight(32)
        btn_del.setCursor(Qt.PointingHandCursor); btn_del.clicked.connect(self._on_delete)
        btn_close = QPushButton(tr("閉じる"))
        btn_close.setObjectName("primaryActionBtn"); btn_close.setFixedHeight(32)
        btn_close.setCursor(Qt.PointingHandCursor); btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_edit); btn_row.addWidget(btn_del)
        btn_row.addStretch(); btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)
        return w

    def _build_edit_page(self) -> QWidget:
        self._edit_panel = EventEditPanel()
        self._edit_panel.save_requested.connect(self._on_save)
        self._edit_panel.cancel_requested.connect(lambda: self._stack.setCurrentIndex(0))
        return self._edit_panel

    def _switch_to_edit(self):
        self._edit_panel.load_event(self._ev, self._calendars)
        self._stack.setCurrentIndex(1)
        self.setWindowTitle(tr("イベントを編集")); self.adjustSize()

    def _on_save(self, cal_id: str, body: dict, event_id: str):
        self.event_saved.emit(cal_id, body, event_id); self.accept()

    def _on_delete(self):
        title = self._ev.get("summary", "")
        if QMessageBox.question(
            self, tr("削除の確認"),
            tr("「{0}」を削除しますか？").format(title),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.event_deleted.emit(
                self._ev.get("_calendar_id", "primary"), self._ev.get("id", ""))
            self.accept()

    def _apply_theme(self):
        d = self._is_dark
        bg = "#1e1e1e" if d else "#ffffff"; bd = "#3e3e42" if d else "#e0e0e0"
        txt = "#e0e0e0" if d else "#212121"
        self.setStyleSheet(f"""
            QDialog, QWidget {{ background: {bg}; color: {txt}; }}
            QFrame {{ border: none; }}
            QFrame[frameShape="4"] {{ border-top: 1px solid {bd}; }}
            QPushButton#primaryActionBtn {{
                background: #0e639c; color: #fff; border: none;
                border-radius: 4px; padding: 0 16px; font-weight: bold; }}
            QPushButton#primaryActionBtn:hover {{ background: #1177bb; }}
            QPushButton#secondaryActionBtn {{
                background: {'#3e3e42' if d else '#e0e0e0'}; color: {txt};
                border: none; border-radius: 4px; padding: 0 12px; }}
            QPushButton#secondaryActionBtn:hover {{ background: {'#505055' if d else '#d0d0d0'}; }}
            QPushButton#deleteBtnDlg {{
                background: #3d1111; color: #ff6b6b;
                border: 1px solid #5c1a1a; border-radius: 4px; padding: 0 12px; }}
            QPushButton#deleteBtnDlg:hover {{ background: #5c1a1a; }}
            QLineEdit, QTextEdit, QDateTimeEdit {{
                background: {'#2d2d2d' if d else '#f8f8f8'};
                border: 1px solid {bd}; border-radius: 4px; padding: 4px 8px; color: {txt}; }}
            QComboBox {{
                background: {'#3d3d3d' if d else '#f0f0f0'};
                border: 1px solid {bd}; border-radius: 4px; padding: 4px 8px; color: {txt}; }}
            QCheckBox {{ color: {txt}; }}
        """)


# ── EventEditPanel ────────────────────────────────────────────────────────────

class EventEditPanel(QWidget):
    save_requested   = Signal(str, dict, str)
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._calendars = []; self._editing_event = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16); layout.setSpacing(12)

        title_lbl = QLabel(tr("イベントを編集"))
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title_lbl)
        sep = QFrame(); sep.setFrameShape(QFrame.HLine); layout.addWidget(sep)

        form_w = QWidget(); form = QVBoxLayout(form_w); form.setSpacing(10)

        def _row(lbl_txt, widget):
            row = QHBoxLayout(); lbl = QLabel(lbl_txt)
            lbl.setFixedWidth(70); lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lbl.setStyleSheet("color: #888; font-size: 12px;")
            row.addWidget(lbl); row.addWidget(widget); form.addLayout(row)

        self.edit_title = QLineEdit()
        self.edit_title.setPlaceholderText(tr("タイトル (必須)")); self.edit_title.setFixedHeight(34)
        _row(tr("タイトル:"), self.edit_title)

        self.cmb_calendar = QComboBox(); self.cmb_calendar.setFixedHeight(34)
        _row(tr("カレンダー:"), self.cmb_calendar)

        self.chk_allday = QCheckBox(tr("終日イベント"))
        self.chk_allday.toggled.connect(self._toggle_allday); form.addWidget(self.chk_allday)

        self.edit_start = QDateTimeEdit()
        self.edit_start.setDisplayFormat("yyyy/MM/dd  HH:mm"); self.edit_start.setFixedHeight(34)
        self.edit_start.setCalendarPopup(True)
        self.edit_start.setDateTime(QDateTime.currentDateTime()); _row(tr("開始:"), self.edit_start)

        self.edit_end = QDateTimeEdit()
        self.edit_end.setDisplayFormat("yyyy/MM/dd  HH:mm"); self.edit_end.setFixedHeight(34)
        self.edit_end.setCalendarPopup(True)
        self.edit_end.setDateTime(QDateTime.currentDateTime().addSecs(3600)); _row(tr("終了:"), self.edit_end)

        self.edit_memo = QTextEdit()
        self.edit_memo.setPlaceholderText(tr("メモ・詳細 (任意)")); self.edit_memo.setFixedHeight(80)
        _row(tr("メモ:"), self.edit_memo)

        layout.addWidget(form_w); layout.addStretch()

        btn_row = QHBoxLayout()
        self.btn_save = QPushButton(tr("保存")); self.btn_save.setObjectName("primaryActionBtn")
        self.btn_save.setFixedHeight(34); self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_cancel = QPushButton(tr("キャンセル")); self.btn_cancel.setObjectName("secondaryActionBtn")
        self.btn_cancel.setFixedHeight(34); self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.cancel_requested.emit)
        btn_row.addStretch(); btn_row.addWidget(self.btn_cancel); btn_row.addWidget(self.btn_save)
        layout.addLayout(btn_row)

    def _toggle_allday(self, checked: bool):
        fmt = "yyyy/MM/dd" if checked else "yyyy/MM/dd  HH:mm"
        self.edit_start.setDisplayFormat(fmt); self.edit_end.setDisplayFormat(fmt)

    def load_event(self, event: dict | None, calendars: list,
                   default_date: QDate = None,
                   default_start_min: int | None = None,
                   default_end_min:   int | None = None):
        self._calendars = calendars; self._editing_event = event
        self.cmb_calendar.clear()
        for cal in calendars:
            self.cmb_calendar.addItem(_cal_name(cal), cal.get("id", ""))

        if event is None:
            # primary カレンダー (本人のカレンダー) をデフォルト選択
            for i, cal in enumerate(calendars):
                if cal.get("primary"):
                    self.cmb_calendar.setCurrentIndex(i)
                    break
            self.edit_title.clear(); self.edit_memo.clear()
            self.chk_allday.setChecked(False)
            base_date = default_date or QDate.currentDate()
            if default_start_min is not None:
                s_h, s_m = divmod(default_start_min, 60)
                e_h, e_m = divmod(min(default_end_min or (default_start_min + 60), 23 * 60), 60)
                self.edit_start.setDateTime(QDateTime(base_date, QTime(s_h, s_m)))
                self.edit_end.setDateTime(QDateTime(base_date, QTime(e_h, e_m)))
            else:
                now = QDateTime.currentDateTime()
                self.edit_start.setDateTime(QDateTime(base_date, now.time()))
                self.edit_end.setDateTime(QDateTime(base_date, now.time()).addSecs(3600))
        else:
            self.edit_title.setText(event.get("summary", ""))
            self.edit_memo.setText(event.get("description", ""))
            start = event.get("start", {}); end = event.get("end", {})
            if "date" in start:
                self.chk_allday.setChecked(True)
                self.edit_start.setDate(QDate.fromString(start["date"], Qt.ISODate))
                self.edit_end.setDate(QDate.fromString(end.get("date", start["date"]), Qt.ISODate))
            else:
                self.chk_allday.setChecked(False)
                s_dt = QDateTime.fromString(start.get("dateTime", "")[:19], "yyyy-MM-ddTHH:mm:ss")
                e_dt = QDateTime.fromString(end.get("dateTime", "")[:19], "yyyy-MM-ddTHH:mm:ss")
                if s_dt.isValid(): self.edit_start.setDateTime(s_dt)
                if e_dt.isValid(): self.edit_end.setDateTime(e_dt)
            cal_id = event.get("_calendar_id", "")
            for i in range(self.cmb_calendar.count()):
                if self.cmb_calendar.itemData(i) == cal_id:
                    self.cmb_calendar.setCurrentIndex(i); break

    def _on_save(self):
        title = self.edit_title.text().strip()
        if not title:
            QMessageBox.warning(self, tr("エラー"), tr("タイトルを入力してください。")); return
        cal_id = self.cmb_calendar.currentData() or ""
        if not cal_id and self._calendars:
            cal_id = self._calendars[0].get("id", "primary")
        tz_offset = datetime.now(timezone.utc).astimezone().strftime("%z")
        tz_str = f"{tz_offset[:3]}:{tz_offset[3:]}"
        if self.chk_allday.isChecked():
            body = {
                "summary":     title,
                "description": self.edit_memo.toPlainText(),
                "start": {"date": self.edit_start.date().toString(Qt.ISODate)},
                "end":   {"date": self.edit_end.date().addDays(1).toString(Qt.ISODate)},
            }
        else:
            s = self.edit_start.dateTime().toString("yyyy-MM-ddTHH:mm:ss")
            e = self.edit_end.dateTime().toString("yyyy-MM-ddTHH:mm:ss")
            body = {
                "summary":     title,
                "description": self.edit_memo.toPlainText(),
                "start": {"dateTime": f"{s}{tz_str}"},
                "end":   {"dateTime": f"{e}{tz_str}"},
            }
        event_id = self._editing_event.get("id", "") if self._editing_event else ""
        self.save_requested.emit(cal_id, body, event_id)


# ── GoogleCalendarWidget ──────────────────────────────────────────────────────

class GoogleCalendarWidget(BaseWidget):
    def __init__(self):
        super().__init__()
        self._calendars: list     = []
        self._cal_colors: dict    = {}
        self._cal_enabled: set    = set()
        self._events: list        = []
        self._event_date_set: set = set()
        today = QDate.currentDate()
        # 기본: 오늘이 포함된 일요일~토요일 7일 표시
        self._sel_start: QDate    = _week_sunday(today)
        self._sel_end:   QDate    = _week_sunday(today).addDays(6)
        self._events_worker       = None

        self._toggle_timer = QTimer(self)
        self._toggle_timer.setSingleShot(True)
        self._toggle_timer.setInterval(400)
        self._toggle_timer.timeout.connect(self._refresh_events)

        self._nav_timer = QTimer(self)
        self._nav_timer.setSingleShot(True)
        self._nav_timer.setInterval(300)
        self._nav_timer.timeout.connect(self._refresh_events)

        # 자동 갱신 타이머 (기본 15분)
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._auto_refresh)

        self._build_ui()
        bus.google_auth_changed.connect(self._on_auth_changed)
        QTimer.singleShot(0, self._check_auth_and_load)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self._make_header())

        splitter = QSplitter(Qt.Horizontal); splitter.setHandleWidth(1)
        left = self._build_left_panel()
        self._mini_cal.month_changed.connect(self._on_month_changed)
        self._mini_cal.range_selected.connect(self._on_range_selected)
        splitter.addWidget(left)

        self._right_stack = QStackedWidget()
        self._right_stack.addWidget(self._build_event_view())
        self._right_stack.addWidget(self._build_edit_panel())
        splitter.addWidget(self._right_stack)
        splitter.setSizes([230, 500])
        splitter.setStretchFactor(0, 0); splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        self._auth_overlay = self._build_auth_overlay()
        root.addWidget(self._auth_overlay); self._auth_overlay.hide()

    def _make_header(self) -> QWidget:
        hdr = QFrame(); hdr.setObjectName("calHdr")
        hrow = QHBoxLayout(hdr)
        hrow.setContentsMargins(16, 10, 16, 10); hrow.setSpacing(8)

        icon_lbl  = QLabel("📅"); icon_lbl.setStyleSheet("font-size: 18px;")
        title_lbl = QLabel(tr("Google カレンダー"))
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        self._status_lbl = QLabel()
        self._status_lbl.setStyleSheet("color: #888; font-size: 12px;")

        self._btn_today = QPushButton(tr("今日")); self._btn_today.setObjectName("todayBtn")
        self._btn_today.setFixedSize(52, 30); self._btn_today.setCursor(Qt.PointingHandCursor)
        self._btn_today.clicked.connect(self._goto_today)

        self._btn_refresh = QPushButton(tr("🔄 更新"))
        self._btn_refresh.setObjectName("secondaryActionBtn"); self._btn_refresh.setFixedHeight(30)
        self._btn_refresh.setCursor(Qt.PointingHandCursor)
        self._btn_refresh.clicked.connect(self._refresh_events)

        self._btn_new = QPushButton(f"＋  {tr('新規イベント')}")
        self._btn_new.setObjectName("primaryActionBtn"); self._btn_new.setFixedHeight(30)
        self._btn_new.setCursor(Qt.PointingHandCursor); self._btn_new.clicked.connect(self._on_new_event)

        hrow.addWidget(icon_lbl); hrow.addWidget(title_lbl); hrow.addWidget(self._status_lbl)
        hrow.addStretch(); hrow.addWidget(self._btn_today)
        hrow.addWidget(self._btn_refresh); hrow.addWidget(self._btn_new)
        return hdr

    def _build_left_panel(self) -> QWidget:
        w = QWidget(); w.setMinimumWidth(210); w.setMaximumWidth(260)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8); layout.setSpacing(8)

        self._mini_cal = MiniCalendarWidget(); layout.addWidget(self._mini_cal)
        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setStyleSheet("color: #333;")
        layout.addWidget(sep)

        cal_lbl = QLabel(tr("カレンダー"))
        cal_lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #888; margin-left: 4px;")
        layout.addWidget(cal_lbl)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._cal_list_widget  = QWidget()
        self._cal_list_layout  = QVBoxLayout(self._cal_list_widget)
        self._cal_list_layout.setContentsMargins(2, 2, 2, 2); self._cal_list_layout.setSpacing(4)
        self._cal_list_layout.addStretch()
        scroll.setWidget(self._cal_list_widget); layout.addWidget(scroll, 1)
        return w

    def _build_event_view(self) -> QWidget:
        w = QWidget(); layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)

        self._week_strip = _WeekStrip()
        self._week_strip.set_range(self._sel_start, self._sel_end)
        self._week_strip.date_clicked.connect(self._on_strip_clicked)
        layout.addWidget(self._week_strip)

        strip_sep = QFrame(); strip_sep.setObjectName("stripSep")
        strip_sep.setFrameShape(QFrame.HLine); layout.addWidget(strip_sep)

        self._multi_day_view = _MultiDayView(w)
        self._multi_day_view.event_clicked.connect(self._on_event_card_clicked)
        self._multi_day_view.event_dropped.connect(self._on_event_dropped_timed)
        self._multi_day_view.event_resized.connect(self._on_event_resized_timed)
        self._multi_day_view.create_requested.connect(self._on_create_at_time)
        layout.addWidget(self._multi_day_view, 1)
        return w

    def _build_edit_panel(self) -> EventEditPanel:
        panel = EventEditPanel()
        panel.save_requested.connect(self._on_save_event)
        panel.cancel_requested.connect(lambda: self._right_stack.setCurrentIndex(0))
        return panel

    def _build_auth_overlay(self) -> QFrame:
        overlay = QFrame(); layout = QVBoxLayout(overlay); layout.setAlignment(Qt.AlignCenter)
        lbl = QLabel("🔑  " + tr("Google 認証が必要です"))
        lbl.setStyleSheet("font-size: 15px; color: #aaa;"); lbl.setAlignment(Qt.AlignCenter)
        sub = QLabel(tr("設定画面から Google アカウントで認証してください。"))
        sub.setStyleSheet("font-size: 12px; color: #666;"); sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl); layout.addWidget(sub)
        return overlay

    # ── 데이터 ────────────────────────────────────────────────────────────────

    def _check_auth_and_load(self):
        from app.api.google_auth import is_authenticated
        if is_authenticated():
            self._auth_overlay.hide(); self._refresh_calendars()
            self._start_auto_timer()
        else:
            self._auth_overlay.show()

    def _start_auto_timer(self):
        interval_min = self.settings.get("calendar_auto_refresh_interval", 15)
        self._auto_timer.start(interval_min * 60 * 1000)

    def _auto_refresh(self):
        """조용한 자동 갱신."""
        from app.api.google_auth import is_authenticated
        if is_authenticated():
            self._refresh_events()

    def _refresh_calendars(self):
        from app.api.calendar_api import FetchCalendarListWorker
        self._status_lbl.setText(tr("読込中..."))
        w = FetchCalendarListWorker()
        w.data_fetched.connect(self._on_calendars_fetched)
        w.error.connect(self._on_error); w.finished.connect(w.deleteLater)
        w.start(); self.track_worker(w)

    def _refresh_events(self):
        if self._events_worker is not None:
            try: self._events_worker.data_fetched.disconnect()
            except RuntimeError: pass
            self._events_worker = None

        if not self._cal_enabled:
            self._events = []; self._event_date_set.clear()
            self._status_lbl.setText("")
            self._week_strip.set_event_dates(set())
            self._multi_day_view.update_view(
                self._sel_start, self._sel_end, [], self._cal_colors)
            return

        from app.api.calendar_api import FetchEventsWorker, make_time_range
        self._status_lbl.setText(tr("読込中..."))
        time_min, time_max = make_time_range(self._sel_start)
        w = FetchEventsWorker(list(self._cal_enabled), time_min, time_max)
        w.data_fetched.connect(self._on_events_fetched)
        w.error.connect(self._on_error); w.finished.connect(w.deleteLater)
        w.finished.connect(lambda: setattr(self, '_events_worker', None))
        w.start(); self._events_worker = w; self.track_worker(w)

    def _save_enabled_calendars(self):
        from app.core.config import load_settings, save_settings
        s = load_settings(); s["calendar_enabled_ids"] = sorted(self._cal_enabled)
        save_settings(s)

    # ── 핸들러 ────────────────────────────────────────────────────────────────

    def _on_calendars_fetched(self, calendars: list):
        self._calendars  = calendars; self._cal_colors = {}
        from app.core.config import load_settings
        saved_ids    = set(load_settings().get("calendar_enabled_ids", []))
        existing_ids = {cal.get("id", "") for cal in calendars}
        self._cal_enabled = (saved_ids & existing_ids) if saved_ids else set()
        if not self._cal_enabled:
            self._cal_enabled = {c.get("id", "") for c in calendars if c.get("primary")}
        for i, cal in enumerate(calendars):
            self._cal_colors[cal.get("id", "")] = _cal_color(cal, i)

        while self._cal_list_layout.count() > 1:
            item = self._cal_list_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        # 체크된 캘린더 이름순 → 미체크 캘린더 이름순
        calendars_sorted = sorted(calendars, key=lambda c: (
            0 if c.get("id", "") in self._cal_enabled else 1,
            _cal_name(c).lower(),
        ))
        for i, cal in enumerate(calendars_sorted):
            cid   = cal.get("id", ""); name = _cal_name(cal)
            color = self._cal_colors.get(cid, _CAL_COLORS[i % len(_CAL_COLORS)])
            row_w = QWidget(); row = QHBoxLayout(row_w); row.setContentsMargins(2, 2, 2, 2)
            dot = QLabel("●"); dot.setStyleSheet(f"color: {color}; font-size: 14px;"); dot.setFixedWidth(18)
            chk = QCheckBox(name); chk.setChecked(cid in self._cal_enabled)
            chk.toggled.connect(lambda checked, c=cid: self._on_cal_toggled(c, checked))
            row.addWidget(dot); row.addWidget(chk); row.addStretch()
            self._cal_list_layout.insertWidget(self._cal_list_layout.count() - 1, row_w)
        self._refresh_events()

    def _on_events_fetched(self, events: list):
        self._events = events
        ev_dates: set = set()
        for ev in events:
            ds = (ev.get("start", {}).get("date") or ev.get("start", {}).get("dateTime", ""))
            if not ds: continue
            try:
                p = ds[:10].split("-"); ev_dates.add((int(p[0]), int(p[1]), int(p[2])))
            except Exception as e:
                logger.debug(f"イベント日付セット構築失敗 ({ds!r}): {e}")
        self._event_date_set = ev_dates
        cnt = len(events)
        self._status_lbl.setText(tr("{0}件のイベント").format(cnt) if cnt else tr("イベントなし"))
        self._mini_cal.set_events(events, self._cal_colors)
        self._week_strip.set_event_dates(ev_dates)
        self._render_view()

    def _render_view(self):
        self._week_strip.set_range(self._sel_start, self._sel_end)
        self._mini_cal.set_range(self._sel_start, self._sel_end)
        self._multi_day_view.update_view(
            self._sel_start, self._sel_end, self._events, self._cal_colors)

    def _on_event_card_clicked(self, ev: dict):
        dlg = EventDetailDialog(ev, self._cal_colors, self._calendars,
                                is_dark=self.is_dark, parent=self)
        dlg.event_saved.connect(self._on_save_event)
        dlg.event_deleted.connect(self._on_delete_event_from_dialog)
        dlg.exec()

    def _on_range_selected(self, start: QDate, end: QDate):
        self._sel_start = start; self._sel_end = end
        if (start.year() != self._week_strip._week_start().year() or
                start.month() != self._week_strip._week_start().month()):
            self._refresh_events()
        else:
            self._render_view()

    def _on_strip_clicked(self, date: QDate):
        prev_start = self._sel_start
        self._sel_start = date; self._sel_end = date
        self._mini_cal.set_range(date, date)
        self._mini_cal._sel_start = date; self._mini_cal._sel_end = date
        if date.year() != prev_start.year() or date.month() != prev_start.month():
            self._mini_cal._current_year  = date.year()
            self._mini_cal._current_month = date.month()
            self._mini_cal.update(); self._refresh_events()
        else:
            self._mini_cal.update(); self._render_view()

    def _on_month_changed(self, year: int, month: int):
        new_date = QDate(year, month, 1)
        self._sel_start = new_date; self._sel_end = new_date
        self._mini_cal._sel_start = new_date; self._mini_cal._sel_end = new_date
        self._mini_cal.update()
        self._week_strip.set_range(new_date, new_date)
        self._nav_timer.start()

    def _goto_today(self):
        today      = QDate.currentDate()
        week_start = _week_sunday(today)
        week_end   = week_start.addDays(6)
        prev = self._sel_start
        self._sel_start = week_start; self._sel_end = week_end
        self._mini_cal._sel_start = week_start; self._mini_cal._sel_end = week_end
        self._mini_cal._current_year  = today.year()
        self._mini_cal._current_month = today.month()
        self._mini_cal.update(); self._week_strip.set_range(week_start, week_end)
        if today.year() != prev.year() or today.month() != prev.month():
            self._refresh_events()
        else:
            self._render_view()

    def _on_cal_toggled(self, cal_id: str, enabled: bool):
        if enabled: self._cal_enabled.add(cal_id)
        else:        self._cal_enabled.discard(cal_id)
        self._save_enabled_calendars(); self._toggle_timer.start()

    def _on_new_event(self):
        panel = self._right_stack.widget(1)
        now = datetime.now().astimezone()
        start_min = (now.hour * 60 + now.minute) // SNAP_MIN * SNAP_MIN
        panel.load_event(None, self._calendars, self._sel_start,
                         default_start_min=start_min, default_end_min=start_min + 60)
        self._right_stack.setCurrentIndex(1)

    def _on_create_at_time(self, date: QDate, start_min: int, end_min: int):
        """빈 시간대 드래그 → 신규 이벤트 편집 패널 열기."""
        panel = self._right_stack.widget(1)
        panel.load_event(None, self._calendars, date,
                         default_start_min=start_min, default_end_min=end_min)
        self._right_stack.setCurrentIndex(1)

    def _on_save_event(self, cal_id: str, body: dict, event_id: str):
        from app.api.calendar_api import CreateEventWorker, UpdateEventWorker
        w = UpdateEventWorker(cal_id, event_id, body) if event_id \
            else CreateEventWorker(cal_id, body)
        w.success.connect(lambda _: self._on_save_success())
        w.error.connect(self._on_error)
        w.finished.connect(w.deleteLater); w.start(); self.track_worker(w)

    def _on_save_success(self):
        self._right_stack.setCurrentIndex(0); self._refresh_events()

    def _on_delete_event_from_dialog(self, cal_id: str, event_id: str):
        from app.api.calendar_api import DeleteEventWorker
        w = DeleteEventWorker(cal_id, event_id)
        w.success.connect(lambda _: self._refresh_events())
        w.error.connect(self._on_error)
        w.finished.connect(w.deleteLater); w.start(); self.track_worker(w)

    def _on_event_dropped_timed(self, ev: dict, new_date: QDate, new_start_min: int):
        """드래그 앤 드롭으로 이벤트 날짜+시간 변경 (15분 스냅)."""
        start    = ev.get("start", {}); end_d = ev.get("end", {})
        cal_id   = ev.get("_calendar_id", "primary")
        event_id = ev.get("id", "")
        if not event_id:
            return

        body = {k: v for k, v in ev.items() if not k.startswith("_")}

        if "date" in start:
            # 종일 이벤트: 날짜만 이동, 기간 유지
            old_s = QDate.fromString(start["date"], Qt.ISODate)
            old_e = QDate.fromString(end_d.get("date", start["date"]), Qt.ISODate)
            delta = old_s.daysTo(new_date)
            body["start"] = {"date": new_date.toString(Qt.ISODate)}
            body["end"]   = {"date": old_e.addDays(delta).toString(Qt.ISODate)}
        else:
            try:
                s_dt = datetime.fromisoformat(
                    start["dateTime"].replace("Z", "+00:00")).astimezone()
                e_dt = datetime.fromisoformat(
                    end_d["dateTime"].replace("Z", "+00:00")).astimezone()
                duration = e_dt - s_dt
                from datetime import timedelta
                new_h, new_m = divmod(new_start_min, 60)
                new_s = s_dt.replace(
                    year=new_date.year(), month=new_date.month(), day=new_date.day(),
                    hour=new_h, minute=new_m, second=0, microsecond=0)
                new_e = new_s + duration
                tz_off = new_s.strftime("%z")
                tz_str = f"{tz_off[:3]}:{tz_off[3:]}" if tz_off else "+00:00"
                body["start"] = {"dateTime": new_s.strftime("%Y-%m-%dT%H:%M:%S") + tz_str}
                body["end"]   = {"dateTime": new_e.strftime("%Y-%m-%dT%H:%M:%S") + tz_str}
            except Exception as exc:
                logger.error(f"Drop time calculation error: {exc}"); return

        from app.api.calendar_api import UpdateEventWorker
        w = UpdateEventWorker(cal_id, event_id, body)
        w.success.connect(lambda _: self._refresh_events())
        w.error.connect(self._on_error)
        w.finished.connect(w.deleteLater); w.start(); self.track_worker(w)

    def _on_event_resized_timed(self, ev: dict, new_s_min: int, new_e_min: int):
        """상단/하단 드래그로 이벤트 시간 변경 (15분 스냅)."""
        start    = ev.get("start", {}); end_d = ev.get("end", {})
        cal_id   = ev.get("_calendar_id", "primary")
        event_id = ev.get("id", "")
        if not event_id or "dateTime" not in start:
            return   # 종일 이벤트는 리사이즈 불가

        try:
            s_dt = datetime.fromisoformat(
                start["dateTime"].replace("Z", "+00:00")).astimezone()
            e_dt = datetime.fromisoformat(
                end_d["dateTime"].replace("Z", "+00:00")).astimezone()

            new_s_h, new_s_m = divmod(new_s_min, 60)
            new_e_h, new_e_m = divmod(min(new_e_min, 23 * 60 + 59), 60)
            new_s_dt = s_dt.replace(hour=new_s_h, minute=new_s_m, second=0, microsecond=0)
            new_e_dt = e_dt.replace(hour=new_e_h, minute=new_e_m, second=0, microsecond=0)

            tz_off = new_s_dt.strftime("%z")
            tz_str = f"{tz_off[:3]}:{tz_off[3:]}" if tz_off else "+00:00"
            body = {k: v for k, v in ev.items() if not k.startswith("_")}
            body["start"] = {"dateTime": new_s_dt.strftime("%Y-%m-%dT%H:%M:%S") + tz_str}
            body["end"]   = {"dateTime": new_e_dt.strftime("%Y-%m-%dT%H:%M:%S") + tz_str}

            from app.api.calendar_api import UpdateEventWorker
            w = UpdateEventWorker(cal_id, event_id, body)
            w.success.connect(lambda _: self._refresh_events())
            w.error.connect(self._on_error)
            w.finished.connect(w.deleteLater)
            w.start(); self.track_worker(w)
        except Exception as exc:
            logger.error(f"Resize time calc error: {exc}")

    def _on_error(self, err: str):
        self._status_lbl.setText(tr("エラー")); logger.error(f"Calendar error: {err}")

    def _on_auth_changed(self, authenticated: bool):
        if authenticated:
            self._auth_overlay.hide(); self._refresh_calendars()
            self._start_auto_timer()
        else:
            self._auth_overlay.show()
            self._auto_timer.stop()
            self._multi_day_view.update_view(self._sel_start, self._sel_end, [], {})
            self._status_lbl.setText("")

    # ── 테마 ──────────────────────────────────────────────────────────────────

    def set_theme(self, is_dark: bool):
        self.is_dark = is_dark
        self._mini_cal.set_theme(is_dark)
        self._week_strip.set_theme(is_dark)
        self._multi_day_view.set_theme(is_dark)
        self.apply_theme_custom()

    def apply_theme_custom(self):
        d   = self.is_dark
        bg  = "#1e1e1e" if d else "#ffffff"
        bg2 = "#252526" if d else "#f5f5f5"
        bd  = "#3e3e42" if d else "#e0e0e0"
        txt = "#e0e0e0" if d else "#212121"
        self.setStyleSheet(f"""
            QWidget {{ background: {bg}; color: {txt}; }}
            QFrame#calHdr  {{ background: {bg2}; border-bottom: 1px solid {bd}; }}
            QFrame#stripSep {{ border: none; border-top: 1px solid {bd}; max-height: 1px; }}
            QFrame#colSep   {{ border: none; border-left: 1px solid {bd}; max-width: 1px; }}
            QFrame#colHdrSep {{ border: none; border-top: 1px solid {bd}; max-height: 1px; }}
            QPushButton#primaryActionBtn {{
                background: #0e639c; color: #fff; border: none;
                border-radius: 4px; padding: 0 14px; font-weight: bold; }}
            QPushButton#primaryActionBtn:hover {{ background: #1177bb; }}
            QPushButton#todayBtn {{
                background: {'#3e3e42' if d else '#e8f0fe'};
                color: {'#e0e0e0' if d else '#1a73e8'};
                border: 1px solid {'#555' if d else '#1a73e8'};
                border-radius: 4px; font-weight: bold; }}
            QPushButton#todayBtn:hover {{ background: {'#505055' if d else '#d2e3fc'}; }}
            QPushButton#secondaryActionBtn {{
                background: {'#3e3e42' if d else '#e0e0e0'};
                color: {txt}; border: none; border-radius: 4px; padding: 0 12px; }}
            QPushButton#secondaryActionBtn:hover {{ background: {'#505055' if d else '#d0d0d0'}; }}
            QLineEdit, QTextEdit, QDateTimeEdit {{
                background: {'#2d2d2d' if d else '#f8f8f8'};
                border: 1px solid {bd}; border-radius: 4px; padding: 4px 8px; color: {txt}; }}
            QComboBox {{
                background: {'#3d3d3d' if d else '#f0f0f0'};
                border: 1px solid {bd}; border-radius: 4px; padding: 4px 8px; color: {txt}; }}
            QCheckBox {{ color: {txt}; spacing: 6px; }}
            QScrollBar:vertical {{ background: {bg2}; width: 6px; }}
            QScrollBar::handle:vertical {{ background: {'#555' if d else '#ccc'}; border-radius: 3px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

    def closeEvent(self, event):
        try:
            bus.google_auth_changed.disconnect(self._on_auth_changed)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        from app.api.google_auth import is_authenticated
        if is_authenticated() and not self._calendars:
            self._refresh_calendars()
