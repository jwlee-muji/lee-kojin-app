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
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSplitter, QScrollArea, QFrame, QDialog,
    QStackedWidget, QCheckBox, QLineEdit, QDateTimeEdit, QTextEdit,
    QComboBox, QSizePolicy,
)
from PySide6.QtCore import (
    Qt, QDate, QDateTime, QTime, QTimer, Signal, QRect, QSize,
    QMimeData, QByteArray, QPoint,
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QFont, QCursor, QDrag, QIcon,
)
from app.ui.common import BaseWidget
from app.ui.components import (
    LeeButton, LeeDetailHeader, LeeDialog, LeeIconTile, LeePill, LeeSegment,
)
from app.ui.theme import UIColors
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
            start = ev.get("start", {})
            end_d = ev.get("end", {})
            color = cal_colors.get(ev.get("_calendar_id", ""), "#4285F4")
            try:
                if "date" in start:
                    s_date = QDate.fromString(start["date"], Qt.ISODate)
                    e_date = QDate.fromString(end_d.get("date", start["date"]), Qt.ISODate)
                    d = s_date
                    while d < e_date:
                        key = (d.year(), d.month(), d.day())
                        self._event_dates.add(key)
                        self._event_colors.setdefault(key, []).append(color) if color not in self._event_colors.get(key, []) else None
                        d = d.addDays(1)
                elif "dateTime" in start:
                    s_dt = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00")).astimezone()
                    e_dt = datetime.fromisoformat(end_d.get("dateTime", start["dateTime"]).replace("Z", "+00:00")).astimezone()
                    s_date = QDate(s_dt.year, s_dt.month, s_dt.day)
                    e_date = QDate(e_dt.year, e_dt.month, e_dt.day)
                    if e_dt.hour == 0 and e_dt.minute == 0 and e_dt.second == 0 and s_date != e_date:
                        e_date = e_date.addDays(-1)
                    d = s_date
                    while d <= e_date:
                        key = (d.year(), d.month(), d.day())
                        self._event_dates.add(key)
                        self._event_colors.setdefault(key, []).append(color) if color not in self._event_colors.get(key, []) else None
                        d = d.addDays(1)
            except Exception as e:
                logger.debug(f"Event date parsing failed: {e}")
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
        pc = UIColors.get_panel_colors(d)

        bg       = QColor(pc["bg"])
        txt_c    = QColor(pc["text"])
        sub_c    = QColor(pc["text_dim"])
        sat_c    = QColor("#42A5F5" if d else "#1a73e8")
        sun_c    = QColor("#EF5350" if d else "#d32f2f")
        today_bg = QColor(UIColors.ACCENT_DARK if d else UIColors.ACCENT_LIGHT)
        sel_bg   = QColor(UIColors.ACCENT_DARK if d else UIColors.ACCENT_LIGHT)
        rng_bg   = QColor(sel_bg); rng_bg.setAlpha(60 if d else 30)

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
                dot_r = 2; total = min(len(colors), 3)
                gap = dot_r * 2 + 2
                sx  = cx + cw // 2 - (total * gap) // 2 + 1
                dy  = cy + ch - dot_r - 4
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
        pc = UIColors.get_panel_colors(d)

        bg      = QColor(pc["bg"])
        txt     = QColor(pc["text"])
        sub     = QColor(pc["text_dim"])
        sat_c   = QColor("#42A5F5" if d else "#1a73e8")
        sun_c   = QColor("#EF5350" if d else "#d32f2f")
        today_c = QColor(UIColors.ACCENT_DARK if d else UIColors.ACCENT_LIGHT)
        sel_c   = QColor(UIColors.ACCENT_DARK if d else UIColors.ACCENT_LIGHT)
        rng_c   = QColor(sel_c); rng_c.setAlpha(60 if d else 30)

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
        pc = UIColors.get_panel_colors(d)

        bg      = QColor(pc["bg"])
        txt     = QColor(pc["text"])
        sub     = QColor(pc["text_dim"])
        sat_c   = QColor("#42A5F5" if d else "#1a73e8")
        sun_c   = QColor("#EF5350" if d else "#d32f2f")
        today_c = QColor(UIColors.ACCENT_DARK if d else UIColors.ACCENT_LIGHT)
        sel_c   = QColor(UIColors.ACCENT_DARK if d else UIColors.ACCENT_LIGHT)

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
        pc = UIColors.get_panel_colors(d)
        p.fillRect(0, 0, RULER_W, DAY_H, QColor(pc["bg"]))
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(pc["text_dim"]))
        for hour in range(1, 24):
            y = int(hour * HOUR_H)
            p.drawText(QRect(0, y - 9, RULER_W - 6, 18),
                       Qt.AlignRight | Qt.AlignVCenter, f"{hour:02d}:00")
        p.end()


# ── AllDayColumn (종일 일정 전용 고정 영역) ──────────────────────────────────

class _AllDayColumn(QWidget):
    """스크롤 영역 바깥에 상단 고정되는 종일 이벤트 전용 열."""
    event_clicked = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._date: QDate = QDate.currentDate()
        self._events: list = []
        self._cal_colors: dict = {}
        self._is_dark: bool = True
        self._is_today: bool = False
        self._hovered_ev = None
        self.setMouseTracking(True)

    def set_day(self, date: QDate, events: list, cal_colors: dict, is_today: bool = False):
        self._date = date
        self._events = events
        self._cal_colors = cal_colors
        self._is_today = is_today
        self.update()

    def set_theme(self, is_dark: bool):
        self._is_dark = is_dark
        self.update()

    def _ev_rect(self, idx: int) -> QRect:
        return QRect(2, 2 + idx * 22, self.width() - 4, 20)

    def _ev_at(self, pos: QPoint) -> dict | None:
        for i, ev in enumerate(self._events):
            if self._ev_rect(i).contains(pos):
                return ev
        return None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        d = self._is_dark
        pc = UIColors.get_panel_colors(d)

        # 배경 그리기 (오늘 파란 틴트 적용)
        p.fillRect(0, 0, W, H, QColor(pc["bg"]))
        if self._is_today:
            tint = QColor(UIColors.ACCENT_DARK if d else UIColors.ACCENT_LIGHT); tint.setAlpha(14 if d else 9)
            p.fillRect(0, 0, W, H, tint)

        txt_c = QColor(pc["text"])
        for i, ev in enumerate(self._events):
            rect = self._ev_rect(i)
            color = QColor(self._cal_colors.get(ev.get("_calendar_id", ""), "#4285F4"))
            chip_bg = QColor(color); chip_bg.setAlpha(60 if d else 45)
            
            p.setPen(Qt.NoPen); p.setBrush(chip_bg)
            p.drawRoundedRect(rect, 3, 3)
            p.setBrush(color)
            p.drawRoundedRect(rect.x(), rect.y(), 3, rect.height(), 1, 1)
            
            p.setPen(txt_c); p.setFont(QFont("Segoe UI", 7))
            title = ev.get("summary", tr("(タイトルなし)"))
            t_rect = QRect(rect.x() + 6, rect.y() + 2, rect.width() - 8, rect.height() - 4)
            p.drawText(t_rect, Qt.AlignLeft | Qt.AlignVCenter, title[:20] + ("…" if len(title) > 20 else ""))
        p.end()

    def mouseMoveEvent(self, e):
        ev = self._ev_at(e.position().toPoint())
        if ev:
            self.setCursor(QCursor(Qt.PointingHandCursor))
            if ev != self._hovered_ev:
                self._hovered_ev = ev
                self.setToolTip(ev.get("summary", tr("(タイトルなし)")))
        else:
            self.setCursor(QCursor(Qt.ArrowCursor))
            if self._hovered_ev:
                self._hovered_ev = None
                self.setToolTip("")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            ev = self._ev_at(e.position().toPoint())
            if ev:
                self.event_clicked.emit(ev)


# ── TimedDayColumn ────────────────────────────────────────────────────────────

_RESIZE_EDGE_PX = 8   # 상단/하단 리사이즈 핸들 영역(px)


class _TimedDayColumn(QWidget):
    """24시간 시간축 기반 하루 열 위젯."""
    event_clicked    = Signal(dict)
    event_dropped    = Signal(dict, QDate, int)   # (ev, new_date, new_start_min) — 이동
    event_copied     = Signal(dict, QDate, int)   # (ev, new_date, new_start_min) — Ctrl+드래그 복사
    event_resized    = Signal(dict, int, int)     # (ev, new_start_min, new_end_min)
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
                
                s_date = QDate(s_dt.year, s_dt.month, s_dt.day)
                e_date = QDate(e_dt.year, e_dt.month, e_dt.day)
                
                if s_date < self._date:
                    s_min = 0
                else:
                    s_min = s_dt.hour * 60 + s_dt.minute
                    
                if e_date > self._date or (e_date == self._date and e_dt.hour == 0 and e_dt.minute == 0 and s_date < e_date):
                    e_min = 24 * 60
                else:
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

    # ── 그리기 ────────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W = self.width()
        d = self._is_dark
        pc = UIColors.get_panel_colors(d)

        bg_c    = QColor(pc["bg"])
        grid_c  = QColor(pc["border"])
        half_c  = QColor(pc["border"]); half_c.setAlpha(half_c.alpha() // 2)
        now_c   = QColor("#EA4335" if d else "#d32f2f")
        txt_c   = QColor(pc["text"])

        p.fillRect(0, 0, W, DAY_H, bg_c)

        # 오늘 열 파란 틴트 — 한눈에 구분
        if self._is_today:
            tint = QColor(UIColors.ACCENT_DARK if d else UIColors.ACCENT_LIGHT); tint.setAlpha(14 if d else 9)
            p.fillRect(0, 0, W, DAY_H, tint)

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
            accent = QColor(UIColors.ACCENT_DARK if d else UIColors.ACCENT_LIGHT)
            gc = QColor(accent); gc.setAlpha(90)
            p.setPen(QPen(accent, 1))
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
            accent = QColor(UIColors.ACCENT_DARK if d else UIColors.ACCENT_LIGHT)
            ghost_fill = QColor(accent); ghost_fill.setAlpha(55)
            ghost_bd   = QColor(accent); ghost_bd.setAlpha(200)
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
            # 기존 이벤트 드래그 — Ctrl 키 시 복사 / 그렇지 않으면 이동
            from PySide6.QtWidgets import QApplication as _QA
            is_copy = bool(_QA.keyboardModifiers() & Qt.ControlModifier)
            ev = self._press_ev; offset = self._press_offset
            self._press_pos = None; self._press_ev = None
            mime = QMimeData()
            mime.setData("application/x-calendar-event", QByteArray(
                json.dumps({"ev": ev, "drag_offset_min": offset, "is_copy": is_copy},
                           ensure_ascii=False).encode()
            ))
            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.exec(Qt.CopyAction if is_copy else Qt.MoveAction)
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
            is_copy = bool(raw.get("is_copy", False)) if isinstance(raw, dict) else False
            drop_min      = _y_to_min(e.position().y())
            new_start_min = max(0, (drop_min - off) // SNAP_MIN * SNAP_MIN)
            if is_copy:
                self.event_copied.emit(ev, self._date, new_start_min)
            else:
                self.event_dropped.emit(ev, self._date, new_start_min)
            e.acceptProposedAction()
        except Exception as exc:
            logger.warning(f"Drop parse error: {exc}"); e.ignore()


# ── MultiDayView ─────────────────────────────────────────────────────────────

class _MultiDayView(QWidget):
    """타임 룰러 + 선택 범위(1~7일) 열 뷰."""
    event_clicked    = Signal(dict)
    event_dropped    = Signal(dict, QDate, int)
    event_copied     = Signal(dict, QDate, int)    # Ctrl+드래그 복사
    event_resized    = Signal(dict, int, int)
    create_requested = Signal(QDate, int, int)

    _MAX_COLS = 7

    def __init__(self, parent=None):
        super().__init__(parent)
        self._columns:  list[_TimedDayColumn] = []
        self._headers:  list[_DayColHeader]   = []
        self._allday_columns: list[_AllDayColumn] = []
        self._col_seps: list[QFrame]          = []
        self._allday_seps: list[QFrame]       = []
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

        # ── 종일 이벤트 고정 행 (스크롤 없음) ─────────────────────────────────
        self._allday_row_widget = QWidget()
        self._allday_row_widget.setMinimumHeight(24)
        allday_layout = QHBoxLayout(self._allday_row_widget)
        allday_layout.setContentsMargins(0, 0, 0, 0); allday_layout.setSpacing(0)
        
        spacer_ad = QWidget(); spacer_ad.setFixedWidth(RULER_W); allday_layout.addWidget(spacer_ad)
        rs_ad = QFrame(); rs_ad.setObjectName("colSep")
        rs_ad.setFrameShape(QFrame.VLine); rs_ad.setFixedWidth(1); allday_layout.addWidget(rs_ad)

        for i in range(self._MAX_COLS):
            ad_col = _AllDayColumn()
            ad_col.event_clicked.connect(self.event_clicked)
            self._allday_columns.append(ad_col); allday_layout.addWidget(ad_col, 1)
            if i < self._MAX_COLS - 1:
                sep = QFrame(); sep.setObjectName("colSep")
                sep.setFrameShape(QFrame.VLine); sep.setFixedWidth(1)
                self._allday_seps.append(sep); allday_layout.addWidget(sep)
        
        main.addWidget(self._allday_row_widget)

        sep_line2 = QFrame(); sep_line2.setObjectName("colHdrSep")
        sep_line2.setFrameShape(QFrame.HLine); sep_line2.setFixedHeight(1)
        main.addWidget(sep_line2)

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
            col.event_copied.connect(self.event_copied)
            col.event_resized.connect(self.event_resized)
            col.create_requested.connect(self.create_requested)
            self._columns.append(col); il.addWidget(col, 1)

        self._scroll.setWidget(inner)
        main.addWidget(self._scroll, 1)

        # 초기 스크롤: 오전 8시
        QTimer.singleShot(2250, lambda: self._scroll.verticalScrollBar().setValue(
            max(0, int(8 * HOUR_H - self._scroll.height() / 3))
        ))

    def update_view(self, sel_start: QDate, sel_end: QDate,
                    events: list, cal_colors: dict):
        n_days = min(max(sel_start.daysTo(sel_end) + 1, 1), self._MAX_COLS)
        today  = QDate.currentDate()

        dke_timed: dict[str, list] = {}
        dke_allday: dict[str, list] = {}
        
        for ev in events:
            start = ev.get("start", {})
            end_d = ev.get("end", {})
            try:
                if "date" in start:
                    s_date = QDate.fromString(start["date"], Qt.ISODate)
                    e_date = QDate.fromString(end_d.get("date", start["date"]), Qt.ISODate)
                    d = s_date
                    while d < e_date:
                        key = f"{d.year()}-{d.month():02d}-{d.day():02d}"
                        dke_allday.setdefault(key, []).append(ev)
                        d = d.addDays(1)
                elif "dateTime" in start:
                    s_dt = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00")).astimezone()
                    e_dt = datetime.fromisoformat(end_d.get("dateTime", start["dateTime"]).replace("Z", "+00:00")).astimezone()
                    s_date = QDate(s_dt.year, s_dt.month, s_dt.day)
                    e_date = QDate(e_dt.year, e_dt.month, e_dt.day)
                    if e_dt.hour == 0 and e_dt.minute == 0 and e_dt.second == 0 and s_date != e_date:
                        e_date = e_date.addDays(-1)
                    d = s_date
                    while d <= e_date:
                        key = f"{d.year()}-{d.month():02d}-{d.day():02d}"
                        dke_timed.setdefault(key, []).append(ev)
                        d = d.addDays(1)
            except Exception as e:
                logger.debug(f"Event parsing failed: {e}")

        # 종일 이벤트 행의 동적 높이 계산
        max_allday = 0
        for i in range(self._MAX_COLS):
            if i < n_days:
                d = sel_start.addDays(i)
                key = f"{d.year()}-{d.month():02d}-{d.day():02d}"
                max_allday = max(max_allday, len(dke_allday.get(key, [])))
        self._allday_row_widget.setFixedHeight(max(24, max_allday * 22 + 4))

        for i in range(self._MAX_COLS):
            if i < n_days:
                self._columns[i].show(); self._headers[i].show(); self._allday_columns[i].show()
                d   = sel_start.addDays(i)
                key = f"{d.year()}-{d.month():02d}-{d.day():02d}"
                self._columns[i].set_day(d, dke_timed.get(key, []), cal_colors, is_today=(d == today), is_selected=True)
                self._allday_columns[i].set_day(d, dke_allday.get(key, []), cal_colors, is_today=(d == today))
                self._headers[i].set_date(d, d == today, True)
            else:
                self._columns[i].hide(); self._headers[i].hide(); self._allday_columns[i].hide()

        for i, sep in enumerate(self._col_seps):
            sep.setVisible(i < n_days - 1)
        for i, sep in enumerate(self._allday_seps):
            sep.setVisible(i < n_days - 1)

    def set_theme(self, is_dark: bool):
        self._ruler.set_theme(is_dark)
        for col in self._columns:
            col.set_theme(is_dark)
        for ad_col in self._allday_columns:
            ad_col.set_theme(is_dark)
        for hdr in self._headers:
            hdr.set_theme(is_dark)


# ── MonthView ────────────────────────────────────────────────────────────────

class _MonthCell(QFrame):
    """월뷰 1일 셀 — 일자 + 이벤트 칩 (최대 3개) + 드래그 드롭."""
    cell_clicked     = Signal(QDate)               # 빈 영역 클릭
    event_clicked    = Signal(dict)                # 이벤트 칩 클릭
    event_dropped    = Signal(dict, QDate, int)    # (ev, new_date, new_start_min) — 이동
    event_copied     = Signal(dict, QDate, int)    # Ctrl+드래그 복사

    _MAX_CHIPS = 3
    _CHIP_H = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self._date = QDate.currentDate()
        self._events: list = []
        self._cal_colors: dict = {}
        self._is_today = False
        self._is_other_month = False
        self._is_dark = True
        self._press_pos: QPoint | None = None
        self._press_ev: dict | None = None
        self.setObjectName("monthCell")
        self.setMinimumHeight(80)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)

    def set_day(self, date: QDate, events: list, cal_colors: dict,
                is_today: bool, is_other_month: bool, is_dark: bool):
        self._date = date
        self._events = events
        self._cal_colors = cal_colors
        self._is_today = is_today
        self._is_other_month = is_other_month
        self._is_dark = is_dark
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        d = self._is_dark

        # 배경
        bg_app   = "#0A0B0F" if d else "#F5F6F8"
        bg_cell  = "#14161C" if d else "#FFFFFF"
        bg_other = "#0F1115" if d else "#FAFBFC"
        bd       = "rgba(255,255,255,0.06)" if d else "rgba(11,18,32,0.06)"
        fg_pri   = "#F2F4F7" if d else "#0B1220"
        fg_oth   = "#3D424D" if d else "#C2C8D2"
        fg_ter   = "#6B7280" if d else "#8A93A6"
        sat_c    = "#42A5F5" if d else "#1a73e8"
        sun_c    = "#EF5350" if d else "#d32f2f"

        bg = bg_other if self._is_other_month else bg_cell
        p.fillRect(0, 0, W, H, QColor(bg))

        # 오늘 셀 배경 강조
        if self._is_today:
            tint = QColor("#34C759"); tint.setAlpha(28 if d else 22)
            p.fillRect(0, 0, W, H, tint)

        # 일자 라벨
        dow = self._date.dayOfWeek()
        if self._is_other_month:
            num_color = fg_oth
        elif dow == 6:
            num_color = sat_c
        elif dow == 7:
            num_color = sun_c
        else:
            num_color = fg_pri

        if self._is_today:
            # 원형 배경 + 흰 숫자
            p.setPen(Qt.NoPen); p.setBrush(QColor("#34C759"))
            p.drawEllipse(6, 6, 22, 22)
            p.setPen(QColor("white"))
            p.setFont(QFont("Inter", 9, QFont.Bold))
            p.drawText(QRect(6, 6, 22, 22), Qt.AlignCenter, str(self._date.day()))
        else:
            p.setPen(QColor(num_color))
            p.setFont(QFont("Inter", 9, QFont.Bold if dow in (6, 7) else QFont.Normal))
            p.drawText(QRect(8, 4, 26, 18), Qt.AlignLeft | Qt.AlignVCenter,
                       str(self._date.day()))

        # 이벤트 칩 (최대 3개)
        chip_y = 26
        max_chips = min(len(self._events), self._MAX_CHIPS)
        for i in range(max_chips):
            ev = self._events[i]
            cal_id = ev.get("_calendar_id", "")
            color = QColor(self._cal_colors.get(cal_id, "#34C759"))
            chip_rect = QRect(4, chip_y + i * (self._CHIP_H + 2), W - 8, self._CHIP_H)

            # 종일 vs 시간지정 구분
            start = ev.get("start", {})
            is_allday = "date" in start

            if is_allday:
                # 종일: 배경 채움
                bg_c = QColor(color); bg_c.setAlpha(190)
                p.setPen(Qt.NoPen); p.setBrush(bg_c)
                p.drawRoundedRect(chip_rect, 3, 3)
                p.setPen(QColor("white"))
                p.setFont(QFont("Inter", 7, QFont.Bold))
                title = ev.get("summary", tr("(タイトルなし)"))
                t_rect = QRect(chip_rect.x() + 5, chip_rect.y(),
                               chip_rect.width() - 8, chip_rect.height())
                p.drawText(t_rect, Qt.AlignLeft | Qt.AlignVCenter,
                           title[:18] + ("…" if len(title) > 18 else ""))
            else:
                # 시간 지정: 도트 + 시간 + 제목
                p.setPen(Qt.NoPen); p.setBrush(color)
                p.drawEllipse(chip_rect.x() + 4, chip_rect.y() + 5, 6, 6)
                title = ev.get("summary", tr("(タイトルなし)"))
                # 시각 추출
                time_str = ""
                try:
                    s_dt = datetime.fromisoformat(
                        start["dateTime"].replace("Z", "+00:00")).astimezone()
                    time_str = s_dt.strftime("%H:%M")
                except Exception:
                    pass
                p.setPen(QColor(fg_ter))
                p.setFont(QFont("JetBrains Mono", 7))
                t_rect = QRect(chip_rect.x() + 14, chip_rect.y(), 32, chip_rect.height())
                p.drawText(t_rect, Qt.AlignLeft | Qt.AlignVCenter, time_str)
                p.setPen(QColor(fg_pri))
                p.setFont(QFont("Inter", 7))
                title_rect = QRect(chip_rect.x() + 50, chip_rect.y(),
                                   chip_rect.width() - 50, chip_rect.height())
                p.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter,
                           title[:14] + ("…" if len(title) > 14 else ""))

        # 더보기 표시
        if len(self._events) > self._MAX_CHIPS:
            extra = len(self._events) - self._MAX_CHIPS
            p.setPen(QColor(fg_ter))
            p.setFont(QFont("Inter", 7, QFont.Bold))
            p.drawText(QRect(4, chip_y + self._MAX_CHIPS * (self._CHIP_H + 2),
                             W - 8, self._CHIP_H),
                       Qt.AlignLeft | Qt.AlignVCenter, tr("他 {0} 件").format(extra))

        # 셀 보더
        p.setPen(QPen(QColor(bd), 1)); p.setBrush(Qt.NoBrush)
        p.drawRect(0, 0, W - 1, H - 1)
        p.end()

    def _ev_chip_at(self, pos: QPoint) -> dict | None:
        chip_y = 26
        max_chips = min(len(self._events), self._MAX_CHIPS)
        for i in range(max_chips):
            chip_rect = QRect(4, chip_y + i * (self._CHIP_H + 2),
                              self.width() - 8, self._CHIP_H)
            if chip_rect.contains(pos):
                return self._events[i]
        return None

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        self._press_pos = e.position().toPoint()
        self._press_ev = self._ev_chip_at(self._press_pos)

    def mouseMoveEvent(self, e):
        if not (e.buttons() & Qt.LeftButton) or self._press_pos is None:
            return
        if (e.position().toPoint() - self._press_pos).manhattanLength() < 8:
            return
        if self._press_ev is None:
            return
        is_copy = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
        ev = self._press_ev
        self._press_pos = None; self._press_ev = None
        mime = QMimeData()
        mime.setData("application/x-calendar-event", QByteArray(
            json.dumps({"ev": ev, "drag_offset_min": 0, "is_copy": is_copy},
                       ensure_ascii=False).encode()
        ))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction if is_copy else Qt.MoveAction)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self._press_ev is not None:
            self.event_clicked.emit(self._press_ev)
        elif self._press_pos is not None:
            # 빈 영역 → 새 이벤트
            self.cell_clicked.emit(self._date)
        self._press_pos = None; self._press_ev = None

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat("application/x-calendar-event"):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat("application/x-calendar-event"):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        if not e.mimeData().hasFormat("application/x-calendar-event"):
            e.ignore(); return
        try:
            raw = json.loads(
                bytes(e.mimeData().data("application/x-calendar-event")).decode())
            ev = raw.get("ev", raw) if isinstance(raw, dict) and "ev" in raw else raw
            is_copy = bool(raw.get("is_copy", False)) if isinstance(raw, dict) else False
            # 월뷰: 시간 정보 보존 (start_min = -1 을 'preserve' 신호로 사용)
            new_start_min = -1
            if is_copy:
                self.event_copied.emit(ev, self._date, new_start_min)
            else:
                self.event_dropped.emit(ev, self._date, new_start_min)
            e.acceptProposedAction()
        except Exception as exc:
            logger.warning(f"MonthCell drop parse error: {exc}"); e.ignore()


class _MonthView(QWidget):
    """6 행 x 7 열 월 뷰 — 각 셀에 일자 + 이벤트 칩."""
    event_clicked    = Signal(dict)
    event_dropped    = Signal(dict, QDate, int)
    event_copied     = Signal(dict, QDate, int)
    create_requested = Signal(QDate, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._year = QDate.currentDate().year()
        self._month = QDate.currentDate().month()
        self._is_dark = True
        self._cells: list[_MonthCell] = []
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        # 요일 헤더
        hdr = QFrame(); hdr.setObjectName("monthDayHdr")
        hdr.setFixedHeight(28)
        hl = QHBoxLayout(hdr); hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(0)
        for i, name in enumerate(_DAY_NAMES_JP):
            lbl = QLabel(name)
            lbl.setObjectName("monthDayHdrLbl")
            lbl.setProperty("dow", "sat" if i == 5 else ("sun" if i == 6 else "wd"))
            lbl.setAlignment(Qt.AlignCenter)
            hl.addWidget(lbl, 1)
        v.addWidget(hdr)

        # 6 x 7 그리드
        from PySide6.QtWidgets import QGridLayout
        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0); grid.setSpacing(0)
        for r in range(6):
            for c in range(7):
                cell = _MonthCell()
                cell.cell_clicked.connect(lambda d: self.create_requested.emit(d, 9 * 60, 10 * 60))
                cell.event_clicked.connect(self.event_clicked)
                cell.event_dropped.connect(self.event_dropped)
                cell.event_copied.connect(self.event_copied)
                self._cells.append(cell)
                grid.addWidget(cell, r, c)
        for r in range(6):
            grid.setRowStretch(r, 1)
        for c in range(7):
            grid.setColumnStretch(c, 1)
        v.addWidget(grid_w, 1)

    def update_view(self, year: int, month: int, events: list, cal_colors: dict):
        self._year = year
        self._month = month

        first = QDate(year, month, 1)
        # 월의 1일이 속한 주의 월요일
        start_col = (first.dayOfWeek() - 1) % 7
        grid_start = first.addDays(-start_col)

        today = QDate.currentDate()

        # 이벤트를 날짜별로 분류
        by_day: dict[tuple, list] = {}
        for ev in events:
            start = ev.get("start", {}); end_d = ev.get("end", {})
            try:
                if "date" in start:
                    s_date = QDate.fromString(start["date"], Qt.ISODate)
                    e_date = QDate.fromString(end_d.get("date", start["date"]), Qt.ISODate)
                    d = s_date
                    while d < e_date:
                        by_day.setdefault((d.year(), d.month(), d.day()), []).append(ev)
                        d = d.addDays(1)
                elif "dateTime" in start:
                    s_dt = datetime.fromisoformat(
                        start["dateTime"].replace("Z", "+00:00")).astimezone()
                    e_dt = datetime.fromisoformat(end_d.get("dateTime",
                        start["dateTime"]).replace("Z", "+00:00")).astimezone()
                    s_date = QDate(s_dt.year, s_dt.month, s_dt.day)
                    e_date = QDate(e_dt.year, e_dt.month, e_dt.day)
                    if e_dt.hour == 0 and e_dt.minute == 0 and e_dt.second == 0 and s_date != e_date:
                        e_date = e_date.addDays(-1)
                    d = s_date
                    while d <= e_date:
                        by_day.setdefault((d.year(), d.month(), d.day()), []).append(ev)
                        d = d.addDays(1)
            except Exception as e:
                logger.debug(f"MonthView event parse failed: {e}")

        # 셀에 분배
        for i, cell in enumerate(self._cells):
            d = grid_start.addDays(i)
            key = (d.year(), d.month(), d.day())
            day_events = by_day.get(key, [])
            # 시간순 정렬 — 종일 우선
            def _sort_key(ev):
                s = ev.get("start", {})
                if "date" in s:
                    return (0, "")
                return (1, s.get("dateTime", ""))
            day_events.sort(key=_sort_key)
            cell.set_day(d, day_events, cal_colors,
                         is_today=(d == today),
                         is_other_month=(d.month() != month),
                         is_dark=self._is_dark)

    def set_theme(self, is_dark: bool):
        self._is_dark = is_dark
        # 테마는 다음 update_view 에서 반영됨 — 즉시 반영을 위해 update 호출
        for cell in self._cells:
            cell._is_dark = is_dark
            cell.update()


# ── EventDetailDialog ─────────────────────────────────────────────────────────

class EventDetailDialog(LeeDialog):
    event_saved   = Signal(str, dict, str)
    event_deleted = Signal(str, str)

    def __init__(self, ev: dict, cal_colors: dict, calendars: list,
                 is_dark: bool = True, parent=None):
        super().__init__(ev.get("summary", tr("イベント詳細")) or tr("イベント詳細"),
                         kind="info", parent=parent)
        self._ev = ev; self._cal_colors = cal_colors
        self._calendars = calendars; self._is_dark = is_dark
        self.setMinimumWidth(440)
        # body 영역을 stacked (detail/edit) 로 교체, footer 는 페이지 내부 액션바 사용
        self.set_footer_visible(False)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_detail_page())
        self._stack.addWidget(self._build_edit_page())
        self.set_compact_body(self._stack)
        # QDateEdit/QDateTimeEdit popup 통일 (안전망)
        try:
            from app.ui.components.mini_calendar import install_on_date_edits
            install_on_date_edits(self, accent=_C_CAL)
        except Exception:
            pass

    def _build_detail_page(self) -> QWidget:
        w = QWidget(); w.setObjectName("evtDetailPage")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 20, 24, 16); layout.setSpacing(10)

        ev = self._ev; cal_id = ev.get("_calendar_id", "")
        # 캘린더 색 매핑이 없는 경우 디자인 토큰 c_cal (#34C759) 로 fallback
        from app.ui.theme import ThemeManager
        color = self._cal_colors.get(cal_id) or ThemeManager.instance().tokens["c_cal"]

        title_row = QHBoxLayout(); title_row.setSpacing(10)
        bar = QFrame(); bar.setObjectName("evtColorBar"); bar.setFixedSize(4, 40)
        bar.setStyleSheet(f"background: {color}; border-radius: 2px;")
        title_lbl = QLabel(ev.get("summary", tr("(タイトルなし)")))
        title_lbl.setObjectName("evtTitle")
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
        time_lbl = QLabel(time_str); time_lbl.setObjectName("evtTime")
        layout.addWidget(time_lbl)

        cal_obj  = next((c for c in self._calendars if c.get("id") == cal_id), {})
        cal_name = _cal_name(cal_obj) if cal_obj else cal_id
        cal_lbl  = QLabel(f"●  {cal_name}"); cal_lbl.setObjectName("evtCalLabel")
        cal_lbl.setStyleSheet(f"color: {color}; font-size: 12px; "
                              f"padding-left: 8px; font-weight: 600;")
        layout.addWidget(cal_lbl)

        memo = ev.get("description", "").strip()
        if memo:
            sep_l = QFrame(); sep_l.setObjectName("evtSep"); sep_l.setFixedHeight(1)
            layout.addWidget(sep_l)
            memo_lbl = QLabel(memo); memo_lbl.setObjectName("evtMemo")
            memo_lbl.setWordWrap(True); layout.addWidget(memo_lbl)

        layout.addStretch()
        sep = QFrame(); sep.setObjectName("evtSep"); sep.setFixedHeight(1)
        layout.addWidget(sep)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        btn_edit  = LeeButton(f"✏  {tr('編集')}",  variant="secondary",   size="md")
        btn_del   = LeeButton(f"🗑  {tr('削除')}",  variant="destructive", size="md")
        btn_close = LeeButton(tr("閉じる"),         variant="primary",     size="md")
        btn_edit.clicked.connect(self._switch_to_edit)
        btn_del.clicked.connect(self._on_delete)
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_edit); btn_row.addWidget(btn_del)
        btn_row.addStretch(); btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self._apply_detail_qss(w)
        return w

    def _apply_detail_qss(self, w: QWidget):
        from app.ui.theme import TOKENS_DARK, TOKENS_LIGHT
        t = TOKENS_DARK if self._is_dark else TOKENS_LIGHT
        w.setStyleSheet(f"""
            QWidget#evtDetailPage {{ background: {t['bg_surface']}; }}
            QLabel#evtTitle {{
                color: {t['fg_primary']};
                font-size: 16px; font-weight: 700;
                padding-left: 4px;
                background: transparent;
            }}
            QLabel#evtTime {{
                color: {t['fg_secondary']};
                font-size: 13px; padding-left: 8px;
                background: transparent;
            }}
            QLabel#evtMemo {{
                color: {t['fg_secondary']};
                font-size: 12px; padding-left: 8px;
                background: transparent;
            }}
            QFrame#evtSep {{
                background: {t['border_subtle']};
                border: none;
            }}
        """)

    def _build_edit_page(self) -> QWidget:
        self._edit_panel = EventEditPanel()
        self._edit_panel.save_requested.connect(self._on_save)
        self._edit_panel.cancel_requested.connect(lambda: self._stack.setCurrentIndex(0))
        return self._edit_panel

    def _switch_to_edit(self):
        self._edit_panel.load_event(self._ev, self._calendars)
        self._stack.setCurrentIndex(1)
        self.adjustSize()

    def _on_save(self, cal_id: str, body: dict, event_id: str):
        self.event_saved.emit(cal_id, body, event_id); self.accept()

    def _on_delete(self):
        title = self._ev.get("summary", "")
        is_recurring = bool(self._ev.get("recurringEventId") or self._ev.get("recurrence"))
        if is_recurring:
            # 반복 이벤트: LeeDialog 로 3 옵션 confirm
            dlg = LeeDialog(tr("繰り返しイベントの削除"), kind="question", parent=self)
            dlg.set_message(tr("「{0}」 (繰り返し) を削除します。\n\n"
                               "どの範囲を削除しますか?").format(title))
            dlg.add_button(tr("キャンセル"), variant="ghost", role="reject")
            # accept 시 self._delete_mode 에 결과 저장
            self._delete_mode: str = ""
            def _set_mode(m):
                self._delete_mode = m
                dlg.accept()
            b1 = dlg.add_button(tr("このイベントのみ"),     variant="secondary", role="accept")
            b2 = dlg.add_button(tr("以降すべて"),         variant="secondary", role="accept")
            b3 = dlg.add_button(tr("シリーズ全体"),       variant="destructive", role="accept")
            # 기본 connect 를 끊고 모드 세팅
            try:
                b1.clicked.disconnect(); b2.clicked.disconnect(); b3.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            b1.clicked.connect(lambda: _set_mode("this"))
            b2.clicked.connect(lambda: _set_mode("future"))
            b3.clicked.connect(lambda: _set_mode("all"))
            if dlg.exec() == QDialog.Accepted and getattr(self, "_delete_mode", ""):
                cal_id = self._ev.get("_calendar_id", "primary")
                if self._delete_mode == "all":
                    # 시리즈 전체 — 부모 ID 사용
                    eid = self._ev.get("recurringEventId") or self._ev.get("id", "")
                else:
                    # this / future — 단일 인스턴스 ID
                    eid = self._ev.get("id", "")
                self.event_deleted.emit(cal_id, eid)
                self.accept()
            return

        if LeeDialog.confirm(
            tr("削除の確認"),
            tr("「{0}」を削除しますか？").format(title),
            ok_text=tr("削除"),
            destructive=True,
            parent=self,
        ):
            self.event_deleted.emit(
                self._ev.get("_calendar_id", "primary"), self._ev.get("id", ""))
            self.accept()

# ── EventEditPanel ────────────────────────────────────────────────────────────

class EventEditPanel(QWidget):
    save_requested   = Signal(str, dict, str)
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._calendars = []; self._editing_event = None
        self.setObjectName("evtEditPanel")
        self._build_ui()
        self._apply_qss()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16); layout.setSpacing(12)

        title_lbl = QLabel(tr("イベントを編集"))
        title_lbl.setObjectName("evtEditTitle")
        layout.addWidget(title_lbl)
        sep = QFrame(); sep.setObjectName("evtEditSep"); sep.setFixedHeight(1)
        layout.addWidget(sep)

        form_w = QWidget(); form = QVBoxLayout(form_w); form.setSpacing(10)

        def _row(lbl_txt, widget):
            row = QHBoxLayout(); lbl = QLabel(lbl_txt); lbl.setObjectName("evtEditRowLabel")
            lbl.setFixedWidth(70); lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(lbl); row.addWidget(widget); form.addLayout(row)

        self.edit_title = QLineEdit()
        self.edit_title.setPlaceholderText(tr("タイトル (必須)")); self.edit_title.setFixedHeight(34)
        _row(tr("タイトル:"), self.edit_title)

        self.cmb_calendar = QComboBox(); self.cmb_calendar.setFixedHeight(34)
        _row(tr("カレンダー:"), self.cmb_calendar)

        self.chk_allday = QCheckBox(tr("終日イベント"))
        self.chk_allday.toggled.connect(self._toggle_allday); form.addWidget(self.chk_allday)

        # Phase 6 — 디자인 시스템 톤의 popup 적용
        from app.ui.components.mini_calendar import LeeMiniCalendar as _MC

        self.edit_start = QDateTimeEdit()
        self.edit_start.setDisplayFormat("yyyy/MM/dd  HH:mm"); self.edit_start.setFixedHeight(34)
        self.edit_start.setCalendarPopup(True)
        try: self.edit_start.setCalendarWidget(_MC(accent=_C_CAL))
        except Exception: pass
        self.edit_start.setDateTime(QDateTime.currentDateTime()); _row(tr("開始:"), self.edit_start)

        self.edit_end = QDateTimeEdit()
        self.edit_end.setDisplayFormat("yyyy/MM/dd  HH:mm"); self.edit_end.setFixedHeight(34)
        self.edit_end.setCalendarPopup(True)
        try: self.edit_end.setCalendarWidget(_MC(accent=_C_CAL))
        except Exception: pass
        self.edit_end.setDateTime(QDateTime.currentDateTime().addSecs(3600)); _row(tr("終了:"), self.edit_end)

        self.edit_location = QLineEdit()
        self.edit_location.setPlaceholderText(tr("場所 (任意)")); self.edit_location.setFixedHeight(34)
        _row(tr("場所:"), self.edit_location)

        # 반복
        self.cmb_recur = QComboBox(); self.cmb_recur.setFixedHeight(34)
        self.cmb_recur.addItem(tr("なし"),       "")
        self.cmb_recur.addItem(tr("毎日"),       "RRULE:FREQ=DAILY")
        self.cmb_recur.addItem(tr("毎週"),       "RRULE:FREQ=WEEKLY")
        self.cmb_recur.addItem(tr("毎月"),       "RRULE:FREQ=MONTHLY")
        self.cmb_recur.addItem(tr("毎年"),       "RRULE:FREQ=YEARLY")
        _row(tr("繰り返し:"), self.cmb_recur)

        # 알림
        self.cmb_reminder = QComboBox(); self.cmb_reminder.setFixedHeight(34)
        self.cmb_reminder.addItem(tr("なし"),     -1)
        self.cmb_reminder.addItem(tr("10分前"),  10)
        self.cmb_reminder.addItem(tr("30分前"),  30)
        self.cmb_reminder.addItem(tr("1時間前"), 60)
        self.cmb_reminder.addItem(tr("1日前"),   1440)
        _row(tr("通知:"), self.cmb_reminder)

        self.edit_memo = QTextEdit()
        self.edit_memo.setPlaceholderText(tr("メモ・詳細 (任意)")); self.edit_memo.setFixedHeight(80)
        _row(tr("メモ:"), self.edit_memo)

        layout.addWidget(form_w); layout.addStretch()

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        self.btn_cancel = LeeButton(tr("キャンセル"), variant="secondary", size="md")
        self.btn_cancel.clicked.connect(self.cancel_requested.emit)
        self.btn_save = LeeButton(tr("保存"), variant="primary", size="md")
        self.btn_save.clicked.connect(self._on_save)
        btn_row.addStretch(); btn_row.addWidget(self.btn_cancel); btn_row.addWidget(self.btn_save)
        layout.addLayout(btn_row)

    def _apply_qss(self):
        from app.ui.theme import ThemeManager, TOKENS_DARK, TOKENS_LIGHT
        d = ThemeManager.instance().is_dark()
        t = TOKENS_DARK if d else TOKENS_LIGHT
        self.setStyleSheet(f"""
            QWidget#evtEditPanel {{ background: {t['bg_surface']}; }}
            QLabel#evtEditTitle {{
                color: {t['fg_primary']};
                font-size: 15px; font-weight: 700;
                background: transparent;
            }}
            QLabel#evtEditRowLabel {{
                color: {t['fg_tertiary']};
                font-size: 12px;
                background: transparent;
            }}
            QFrame#evtEditSep {{
                background: {t['border_subtle']};
                border: none;
            }}
            QLineEdit, QTextEdit, QDateTimeEdit, QComboBox {{
                background: {t['bg_input']};
                color: {t['fg_primary']};
                border: 1px solid {t['border']};
                border-radius: 6px;
                padding: 4px 8px;
            }}
            QLineEdit:focus, QTextEdit:focus,
            QDateTimeEdit:focus, QComboBox:focus {{
                border: 1px solid {t['accent']};
            }}
            QCheckBox {{ color: {t['fg_primary']}; background: transparent; }}
        """)

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
            self.edit_location.clear()
            self.chk_allday.setChecked(False)
            self.cmb_recur.setCurrentIndex(0)
            self.cmb_reminder.setCurrentIndex(0)
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
            self.edit_location.setText(event.get("location", ""))
            # 반복 — recurrence 배열에서 RRULE 첫 줄만 추출
            recur = event.get("recurrence", [])
            recur_value = ""
            if recur:
                for r in recur:
                    if r.startswith("RRULE:"):
                        # 단순 매칭 — FREQ 값만 비교
                        for i in range(self.cmb_recur.count()):
                            stored = self.cmb_recur.itemData(i)
                            if stored and stored in r:
                                recur_value = stored; break
                        break
            for i in range(self.cmb_recur.count()):
                if self.cmb_recur.itemData(i) == recur_value:
                    self.cmb_recur.setCurrentIndex(i); break
            # 알림 — reminders.overrides 첫 항목
            reminders = event.get("reminders", {}) or {}
            overrides = reminders.get("overrides") or []
            r_minutes = -1
            if overrides:
                r_minutes = overrides[0].get("minutes", -1)
            for i in range(self.cmb_reminder.count()):
                if self.cmb_reminder.itemData(i) == r_minutes:
                    self.cmb_reminder.setCurrentIndex(i); break
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
            LeeDialog.error(tr("エラー"), tr("タイトルを入力してください。"), parent=self); return
        cal_id = self.cmb_calendar.currentData() or ""
        if not cal_id and self._calendars:
            cal_id = self._calendars[0].get("id", "primary")
        tz_offset = datetime.now(timezone.utc).astimezone().strftime("%z")
        tz_str = f"{tz_offset[:3]}:{tz_offset[3:]}"
        if self.chk_allday.isChecked():
            body = {
                "summary":     title,
                "description": self.edit_memo.toPlainText(),
                "location":    self.edit_location.text().strip(),
                "start": {"date": self.edit_start.date().toString(Qt.ISODate)},
                "end":   {"date": self.edit_end.date().addDays(1).toString(Qt.ISODate)},
            }
        else:
            s = self.edit_start.dateTime().toString("yyyy-MM-ddTHH:mm:ss")
            e = self.edit_end.dateTime().toString("yyyy-MM-ddTHH:mm:ss")
            body = {
                "summary":     title,
                "description": self.edit_memo.toPlainText(),
                "location":    self.edit_location.text().strip(),
                "start": {"dateTime": f"{s}{tz_str}"},
                "end":   {"dateTime": f"{e}{tz_str}"},
            }
        # 반복
        recur_rule = self.cmb_recur.currentData()
        if recur_rule:
            body["recurrence"] = [recur_rule]
        # 알림 — overrides 가 빈 list 면 useDefault, 아니면 popup 알림
        r_minutes = self.cmb_reminder.currentData()
        if isinstance(r_minutes, int) and r_minutes >= 0:
            body["reminders"] = {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": r_minutes}],
            }
        else:
            body["reminders"] = {"useDefault": True}
        event_id = self._editing_event.get("id", "") if self._editing_event else ""
        self.save_requested.emit(cal_id, body, event_id)


# ── GoogleCalendarWidget ──────────────────────────────────────────────────────

_C_CAL = "#34C759"   # iOS Green (--c-cal)


class GoogleCalendarWidget(BaseWidget):
    def __init__(self):
        super().__init__()
        self._calendars: list     = []
        self._cal_colors: dict    = {}
        self._cal_enabled: set    = set()
        self._events: list        = []
        self._event_date_set: set = set()
        today = QDate.currentDate()
        # 기본: 주 뷰 (오늘 포함 일~토)
        self._view_mode: str      = "week"     # "month" | "week" | "day"
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
        QTimer.singleShot(2250, self._check_auth_and_load)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 22); outer.setSpacing(14)

        # 1) DetailHeader
        self._header = LeeDetailHeader(
            title=tr("Google カレンダー"),
            subtitle=tr("予定の管理 · 月 / 週 / 日"),
            accent=_C_CAL,
            icon_qicon=QIcon(":/img/calendar.svg"),
            badge=None,
            show_export=False,
        )
        self._header.back_clicked.connect(lambda: bus.page_requested.emit(0))
        outer.addWidget(self._header)

        # 2) 툴바 (← / 今日 / → / 라벨 / 뷰 segment / + 신규 / 갱신)
        toolbar = QFrame(); toolbar.setObjectName("calToolbar")
        tl = QHBoxLayout(toolbar); tl.setContentsMargins(14, 10, 14, 10); tl.setSpacing(6)
        outer.addWidget(toolbar)

        self._btn_prev = LeeButton("◀", variant="secondary", size="sm")
        self._btn_prev.setFixedWidth(34)
        self._btn_prev.clicked.connect(lambda: self._navigate(-1))
        tl.addWidget(self._btn_prev)

        self._btn_today = LeeButton(tr("今日"), variant="secondary", size="sm")
        self._btn_today.clicked.connect(self._goto_today)
        tl.addWidget(self._btn_today)

        self._btn_next = LeeButton("▶", variant="secondary", size="sm")
        self._btn_next.setFixedWidth(34)
        self._btn_next.clicked.connect(lambda: self._navigate(1))
        tl.addWidget(self._btn_next)

        self._range_lbl = QLabel("")
        self._range_lbl.setObjectName("calRangeLbl")
        tl.addWidget(self._range_lbl)
        tl.addStretch()

        self._view_seg = LeeSegment(
            [("month", tr("月")), ("week", tr("週")), ("day", tr("日"))],
            value="week", accent=_C_CAL,
        )
        self._view_seg.value_changed.connect(self._on_view_changed)
        tl.addWidget(self._view_seg)

        self._status_pill = LeePill("", variant="info")
        tl.addWidget(self._status_pill)
        self._status_pill.setVisible(False)

        self._btn_refresh = LeeButton("↻  " + tr("更新"), variant="secondary", size="sm")
        self._btn_refresh.clicked.connect(self._refresh_events)
        tl.addWidget(self._btn_refresh)

        self._btn_new = LeeButton("＋  " + tr("新規"), variant="primary", size="sm")
        self._btn_new.clicked.connect(self._on_new_event)
        tl.addWidget(self._btn_new)

        # 3) 외곽 카드 + splitter
        outer_card = QFrame(); outer_card.setObjectName("calOuterCard")
        oc = QVBoxLayout(outer_card); oc.setContentsMargins(0, 0, 0, 0); oc.setSpacing(0)
        outer.addWidget(outer_card, 1)
        self._outer_card = outer_card

        splitter = QSplitter(Qt.Horizontal); splitter.setHandleWidth(1)
        oc.addWidget(splitter, 1)

        # 좌측 패널
        left = self._build_left_panel()
        self._mini_cal.month_changed.connect(self._on_month_changed)
        self._mini_cal.range_selected.connect(self._on_range_selected)
        splitter.addWidget(left)

        # 우측 — 뷰 스택 (month / multi_day / edit panel)
        self._right_stack = QStackedWidget()
        self._right_stack.addWidget(self._build_event_view())     # idx 0: 월/주/일 뷰 컨테이너
        self._right_stack.addWidget(self._build_edit_panel())     # idx 1: edit panel
        splitter.addWidget(self._right_stack)
        splitter.setSizes([220, 800])
        splitter.setStretchFactor(0, 0); splitter.setStretchFactor(1, 1)

        # 미인증 오버레이
        self._auth_overlay = self._build_auth_overlay()
        outer.addWidget(self._auth_overlay); self._auth_overlay.setVisible(False)

        self._update_range_label()

    def _build_left_panel(self) -> QWidget:
        w = QFrame(); w.setObjectName("calLeftPane")
        w.setMinimumWidth(210); w.setMaximumWidth(260)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 10, 10, 10); layout.setSpacing(8)

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
        """월/주/일 뷰를 담는 컨테이너 (내부 stack 으로 전환)."""
        w = QWidget(); layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)

        self._view_stack = QStackedWidget(w)
        layout.addWidget(self._view_stack, 1)

        # idx 0: Month View
        self._month_view = _MonthView()
        self._month_view.event_clicked.connect(self._on_event_card_clicked)
        self._month_view.event_dropped.connect(self._on_event_dropped_month)
        self._month_view.event_copied.connect(self._on_event_copied_month)
        self._month_view.create_requested.connect(self._on_create_at_time)
        self._view_stack.addWidget(self._month_view)

        # idx 1: Multi-Day View (week / day 공유)
        multi_wrap = QWidget()
        mw = QVBoxLayout(multi_wrap); mw.setContentsMargins(0, 0, 0, 0); mw.setSpacing(0)

        self._week_strip = _WeekStrip()
        self._week_strip.set_range(self._sel_start, self._sel_end)
        self._week_strip.date_clicked.connect(self._on_strip_clicked)
        mw.addWidget(self._week_strip)

        strip_sep = QFrame(); strip_sep.setObjectName("stripSep")
        strip_sep.setFrameShape(QFrame.HLine); mw.addWidget(strip_sep)

        self._multi_day_view = _MultiDayView(multi_wrap)
        self._multi_day_view.event_clicked.connect(self._on_event_card_clicked)
        self._multi_day_view.event_dropped.connect(self._on_event_dropped_timed)
        self._multi_day_view.event_copied.connect(self._on_event_copied_timed)
        self._multi_day_view.event_resized.connect(self._on_event_resized_timed)
        self._multi_day_view.create_requested.connect(self._on_create_at_time)
        mw.addWidget(self._multi_day_view, 1)
        self._view_stack.addWidget(multi_wrap)

        # 초기: 주 뷰
        self._view_stack.setCurrentIndex(1)
        return w

    def _build_edit_panel(self) -> EventEditPanel:
        panel = EventEditPanel()
        panel.save_requested.connect(self._on_save_event)
        panel.cancel_requested.connect(lambda: self._right_stack.setCurrentIndex(0))
        return panel

    def _build_auth_overlay(self) -> QFrame:
        overlay = QFrame(); overlay.setObjectName("calAuthOverlay")
        layout = QVBoxLayout(overlay); layout.setAlignment(Qt.AlignCenter); layout.setSpacing(8)
        lbl = QLabel("🔑  " + tr("Google 認証が必要です"))
        lbl.setObjectName("calAuthLbl"); lbl.setAlignment(Qt.AlignCenter)
        sub = QLabel(tr("設定画面から Google アカウントで認証してください。"))
        sub.setObjectName("calAuthSub"); sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl); layout.addWidget(sub)
        return overlay

    # ── 데이터 ────────────────────────────────────────────────────────────────

    def _check_auth_and_load(self):
        from app.api.google.auth import is_authenticated
        if is_authenticated():
            self._auth_overlay.setVisible(False); self._outer_card.setVisible(True); self._refresh_calendars()
            self._start_auto_timer()
        else:
            self._auth_overlay.setVisible(True); self._outer_card.setVisible(False)

    def _start_auto_timer(self):
        interval_min = self.settings.get("calendar_auto_refresh_interval", 15)
        self._auto_timer.start(interval_min * 60 * 1000)

    def _auto_refresh(self):
        """조용한 자동 갱신."""
        from app.api.google.auth import is_authenticated
        if is_authenticated():
            self._refresh_events()

    def _refresh_calendars(self):
        from app.api.google.calendar import FetchCalendarListWorker
        self._set_status(tr("読込中..."))
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
            self._set_status("")
            self._week_strip.set_event_dates(set())
            self._render_view()
            return

        from app.api.google.calendar import FetchEventsWorker
        self._set_status(tr("読込中..."))
        self.set_loading(True, self._multi_day_view)
        time_min, time_max = self._current_time_range()
        w = FetchEventsWorker(list(self._cal_enabled), time_min, time_max)
        w.data_fetched.connect(self._on_events_fetched)
        w.error.connect(self._on_error); w.finished.connect(w.deleteLater)
        w.finished.connect(lambda: setattr(self, '_events_worker', None))
        w.start(); self._events_worker = w; self.track_worker(w)

    def _current_time_range(self) -> tuple[str, str]:
        """뷰 모드별 ISO 시간 범위 — 월뷰는 표시되는 6주 영역, 주/일뷰는 sel_start~sel_end."""
        from datetime import date as _date, timedelta
        if self._view_mode == "month":
            first = QDate(self._sel_start.year(), self._sel_start.month(), 1)
            start_col = (first.dayOfWeek() - 1) % 7
            grid_start = first.addDays(-start_col)
            grid_end = grid_start.addDays(42)
            t_min = datetime(grid_start.year(), grid_start.month(), grid_start.day(),
                             tzinfo=timezone.utc)
            t_max = datetime(grid_end.year(), grid_end.month(), grid_end.day(),
                             tzinfo=timezone.utc)
        else:
            s, e = self._sel_start, self._sel_end
            t_min = datetime(s.year(), s.month(), s.day(), tzinfo=timezone.utc)
            t_max = datetime(e.year(), e.month(), e.day(), tzinfo=timezone.utc) + \
                    timedelta(days=1)
        return (
            t_min.isoformat().replace("+00:00", "Z"),
            t_max.isoformat().replace("+00:00", "Z"),
        )

    def _set_status(self, text: str) -> None:
        if text:
            self._status_pill.setText(text)
            self._status_pill.setVisible(True)
        else:
            self._status_pill.setVisible(False)

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
        self.set_loading(False, self._multi_day_view)
        self._events = events
        ev_dates: set = set()
        for ev in events:
            start = ev.get("start", {})
            end_d = ev.get("end", {})
            try:
                if "date" in start:
                    s_date = QDate.fromString(start["date"], Qt.ISODate)
                    e_date = QDate.fromString(end_d.get("date", start["date"]), Qt.ISODate)
                    d = s_date
                    while d < e_date:
                        ev_dates.add((d.year(), d.month(), d.day()))
                        d = d.addDays(1)
                elif "dateTime" in start:
                    s_dt = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00")).astimezone()
                    e_dt = datetime.fromisoformat(end_d.get("dateTime", start["dateTime"]).replace("Z", "+00:00")).astimezone()
                    s_date = QDate(s_dt.year, s_dt.month, s_dt.day)
                    e_date = QDate(e_dt.year, e_dt.month, e_dt.day)
                    if e_dt.hour == 0 and e_dt.minute == 0 and e_dt.second == 0 and s_date != e_date:
                        e_date = e_date.addDays(-1)
                    d = s_date
                    while d <= e_date:
                        ev_dates.add((d.year(), d.month(), d.day()))
                        d = d.addDays(1)
            except Exception as e:
                logger.debug(f"イベント日付セット構築失敗: {e}")
        self._event_date_set = ev_dates
        cnt = len(events)
        self._set_status(tr("{0} 件").format(cnt) if cnt else "")
        self._mini_cal.set_events(events, self._cal_colors)
        self._week_strip.set_event_dates(ev_dates)
        self._render_view()

    def _render_view(self):
        self._week_strip.set_range(self._sel_start, self._sel_end)
        self._mini_cal.set_range(self._sel_start, self._sel_end)
        self._update_range_label()
        if self._view_mode == "month":
            self._month_view.update_view(
                self._sel_start.year(), self._sel_start.month(),
                self._events, self._cal_colors,
            )
        else:
            self._multi_day_view.update_view(
                self._sel_start, self._sel_end, self._events, self._cal_colors)

    def _on_event_card_clicked(self, ev: dict):
        dlg = EventDetailDialog(ev, self._cal_colors, self._calendars,
                                is_dark=self.is_dark, parent=self)
        dlg.event_saved.connect(self._on_save_event)
        dlg.event_deleted.connect(self._on_delete_event_from_dialog)
        dlg.exec()

    def _on_range_selected(self, start: QDate, end: QDate):
        if start == end:
            prev_ws = _week_sunday(self._sel_start)
            prev_we = prev_ws.addDays(6)
            if prev_ws <= start <= prev_we:
                self._sel_start = start; self._sel_end = start
            else:
                self._sel_start = _week_sunday(start)
                self._sel_end = self._sel_start.addDays(6)
        else:
            self._sel_start = start; self._sel_end = end

        if (self._sel_start.year() != self._week_strip._week_start().year() or
                self._sel_start.month() != self._week_strip._week_start().month()):
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
        today = QDate.currentDate()
        prev = self._sel_start
        if self._view_mode == "month":
            self._sel_start = QDate(today.year(), today.month(), 1)
            self._sel_end = QDate(today.year(), today.month(),
                                   self._sel_start.daysInMonth())
        elif self._view_mode == "day":
            self._sel_start = today; self._sel_end = today
        else:
            self._sel_start = _week_sunday(today)
            self._sel_end = self._sel_start.addDays(6)
        self._mini_cal._sel_start = self._sel_start
        self._mini_cal._sel_end = self._sel_end
        self._mini_cal._current_year = today.year()
        self._mini_cal._current_month = today.month()
        self._mini_cal.update()
        self._week_strip.set_range(self._sel_start, self._sel_end)
        self._update_range_label()
        if today.year() != prev.year() or today.month() != prev.month():
            self._refresh_events()
        else:
            self._render_view()

    def _navigate(self, delta: int) -> None:
        """← / → — 뷰 모드별 네비게이션."""
        if self._view_mode == "month":
            new_first = self._sel_start.addMonths(delta)
            new_first = QDate(new_first.year(), new_first.month(), 1)
            self._sel_start = new_first
            self._sel_end = QDate(new_first.year(), new_first.month(), new_first.daysInMonth())
        elif self._view_mode == "day":
            self._sel_start = self._sel_start.addDays(delta)
            self._sel_end = self._sel_start
        else:
            new_start = self._sel_start.addDays(delta * 7)
            self._sel_start = new_start
            self._sel_end = new_start.addDays(6)
        self._mini_cal._sel_start = self._sel_start
        self._mini_cal._sel_end = self._sel_end
        self._mini_cal._current_year = self._sel_start.year()
        self._mini_cal._current_month = self._sel_start.month()
        self._mini_cal.update()
        self._week_strip.set_range(self._sel_start, self._sel_end)
        self._update_range_label()
        self._refresh_events()

    def _on_view_changed(self, key: str) -> None:
        """LeeSegment 뷰 변경 — month/week/day."""
        self._view_mode = key
        today = QDate.currentDate()
        anchor = self._sel_start if self._sel_start else today
        if key == "month":
            self._sel_start = QDate(anchor.year(), anchor.month(), 1)
            self._sel_end = QDate(anchor.year(), anchor.month(), self._sel_start.daysInMonth())
            self._view_stack.setCurrentIndex(0)
        elif key == "day":
            d = anchor if anchor else today
            self._sel_start = d; self._sel_end = d
            self._view_stack.setCurrentIndex(1)
        else:   # week
            self._sel_start = _week_sunday(anchor)
            self._sel_end = self._sel_start.addDays(6)
            self._view_stack.setCurrentIndex(1)
        self._mini_cal._sel_start = self._sel_start
        self._mini_cal._sel_end = self._sel_end
        self._mini_cal.update()
        self._week_strip.set_range(self._sel_start, self._sel_end)
        self._update_range_label()
        self._refresh_events()

    def _update_range_label(self) -> None:
        if self._view_mode == "month":
            txt = f"{self._sel_start.year()}年 {self._sel_start.month()}月"
        elif self._view_mode == "day":
            d = self._sel_start
            txt = f"{d.year()}年 {d.month()}月 {d.day()}日 ({_DAY_NAMES_JP[d.dayOfWeek() - 1]})"
        else:
            s, e = self._sel_start, self._sel_end
            if s.year() == e.year() and s.month() == e.month():
                txt = f"{s.year()}年 {s.month()}月 {s.day()} – {e.day()}"
            else:
                txt = f"{s.year()}/{s.month():02d}/{s.day():02d} – {e.year()}/{e.month():02d}/{e.day():02d}"
        self._range_lbl.setText(txt)

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
        from app.api.google.calendar import CreateEventWorker, UpdateEventWorker
        w = UpdateEventWorker(cal_id, event_id, body) if event_id \
            else CreateEventWorker(cal_id, body)
        w.success.connect(lambda _: self._on_save_success())
        w.error.connect(self._on_error)
        w.finished.connect(w.deleteLater); w.start(); self.track_worker(w)

    def _on_save_success(self):
        self._right_stack.setCurrentIndex(0); self._refresh_events()

    def _on_delete_event_from_dialog(self, cal_id: str, event_id: str):
        from app.api.google.calendar import DeleteEventWorker
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

        from app.api.google.calendar import UpdateEventWorker
        w = UpdateEventWorker(cal_id, event_id, body)
        w.success.connect(lambda _: self._refresh_events())
        w.error.connect(self._on_error)
        w.finished.connect(w.deleteLater); w.start(); self.track_worker(w)

    def _on_event_copied_timed(self, ev: dict, new_date: QDate, new_start_min: int):
        """Ctrl+드래그 복사 (주/일 뷰) — 시간 영역 드롭 → CreateEvent."""
        body = self._build_clone_body(ev, new_date, new_start_min)
        if not body:
            return
        cal_id = ev.get("_calendar_id", "primary")
        from app.api.google.calendar import CreateEventWorker
        w = CreateEventWorker(cal_id, body)
        w.success.connect(lambda _e: self._refresh_events())
        w.error.connect(self._on_error)
        w.finished.connect(w.deleteLater); w.start(); self.track_worker(w)

    def _on_event_dropped_month(self, ev: dict, new_date: QDate, _new_start_min: int):
        """월뷰 드롭 — 시간 정보 보존, 날짜만 변경."""
        body = self._build_move_body_preserve_time(ev, new_date)
        if not body:
            return
        cal_id = ev.get("_calendar_id", "primary")
        event_id = ev.get("id", "")
        if not event_id:
            return
        from app.api.google.calendar import UpdateEventWorker
        w = UpdateEventWorker(cal_id, event_id, body)
        w.success.connect(lambda _e: self._refresh_events())
        w.error.connect(self._on_error)
        w.finished.connect(w.deleteLater); w.start(); self.track_worker(w)

    def _on_event_copied_month(self, ev: dict, new_date: QDate, _new_start_min: int):
        """월뷰 Ctrl+드래그 복사."""
        body = self._build_move_body_preserve_time(ev, new_date)
        if not body:
            return
        # id 제거 — CreateEventWorker 가 새 ID 부여
        for k in ("id", "iCalUID", "etag", "htmlLink", "created", "updated",
                  "creator", "organizer", "_calendar_id"):
            body.pop(k, None)
        cal_id = ev.get("_calendar_id", "primary")
        from app.api.google.calendar import CreateEventWorker
        w = CreateEventWorker(cal_id, body)
        w.success.connect(lambda _e: self._refresh_events())
        w.error.connect(self._on_error)
        w.finished.connect(w.deleteLater); w.start(); self.track_worker(w)

    def _build_clone_body(self, ev: dict, new_date: QDate, new_start_min: int) -> dict:
        """Ctrl+드래그 복사용 — 새 시작 시간으로 body 생성, id 제거."""
        from datetime import timedelta
        start = ev.get("start", {}); end_d = ev.get("end", {})
        body = {k: v for k, v in ev.items() if not k.startswith("_")}
        for k in ("id", "iCalUID", "etag", "htmlLink", "created", "updated",
                  "creator", "organizer", "recurringEventId"):
            body.pop(k, None)
        if "date" in start:
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
                new_h, new_m = divmod(new_start_min, 60)
                new_s = s_dt.replace(year=new_date.year(), month=new_date.month(),
                                     day=new_date.day(), hour=new_h, minute=new_m,
                                     second=0, microsecond=0)
                new_e = new_s + duration
                tz_off = new_s.strftime("%z")
                tz_str = f"{tz_off[:3]}:{tz_off[3:]}" if tz_off else "+00:00"
                body["start"] = {"dateTime": new_s.strftime("%Y-%m-%dT%H:%M:%S") + tz_str}
                body["end"]   = {"dateTime": new_e.strftime("%Y-%m-%dT%H:%M:%S") + tz_str}
            except Exception as e:
                logger.error(f"Clone body calc error: {e}"); return {}
        return body

    def _build_move_body_preserve_time(self, ev: dict, new_date: QDate) -> dict:
        """월뷰 드롭용 — 시간은 보존, 날짜만 이동."""
        start = ev.get("start", {}); end_d = ev.get("end", {})
        body = {k: v for k, v in ev.items() if not k.startswith("_")}
        if "date" in start:
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
                new_s = s_dt.replace(year=new_date.year(), month=new_date.month(),
                                     day=new_date.day())
                new_e = new_s + duration
                tz_off = new_s.strftime("%z")
                tz_str = f"{tz_off[:3]}:{tz_off[3:]}" if tz_off else "+00:00"
                body["start"] = {"dateTime": new_s.strftime("%Y-%m-%dT%H:%M:%S") + tz_str}
                body["end"]   = {"dateTime": new_e.strftime("%Y-%m-%dT%H:%M:%S") + tz_str}
            except Exception as e:
                logger.error(f"Move body calc error: {e}"); return {}
        return body

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

            from app.api.google.calendar import UpdateEventWorker
            w = UpdateEventWorker(cal_id, event_id, body)
            w.success.connect(lambda _: self._refresh_events())
            w.error.connect(self._on_error)
            w.finished.connect(w.deleteLater)
            w.start(); self.track_worker(w)
        except Exception as exc:
            logger.error(f"Resize time calc error: {exc}")

    def _on_error(self, err: str):
        self.set_loading(False, self._multi_day_view)
        self._set_status(tr("エラー")); logger.error(f"Calendar error: {err}")

    def _on_auth_changed(self, authenticated: bool):
        if authenticated:
            self._auth_overlay.setVisible(False); self._outer_card.setVisible(True); self._refresh_calendars()
            self._start_auto_timer()
        else:
            self._auth_overlay.setVisible(True); self._outer_card.setVisible(False)
            self._auto_timer.stop()
            self.set_loading(False, self._multi_day_view)
            self._events = []
            self._render_view()
            self._set_status("")

    # ── 設定変更 즉시 반영 (bus.settings_saved → _apply_settings_all → 본 hook) ──
    def apply_settings_custom(self):
        """settings 변경 시 호출 — 자동 갱신 주기 / 폴링 주기 재적용."""
        try:
            from app.api.google.auth import is_authenticated
            if not is_authenticated():
                return
            interval_min = int(self.settings.get("calendar_auto_refresh_interval", 15))
            new_ms = max(1, interval_min) * 60 * 1000
            if self._auto_timer.isActive():
                self._auto_timer.start(new_ms)   # restart with new interval
        except Exception as e:
            logger.debug(f"Calendar apply_settings_custom 실패: {e}")

    # ── 테마 ──────────────────────────────────────────────────────────────────

    def set_theme(self, is_dark: bool):
        self.is_dark = is_dark
        self._header.set_theme(is_dark)
        self._view_seg.set_theme(is_dark)
        self._mini_cal.set_theme(is_dark)
        self._week_strip.set_theme(is_dark)
        self._multi_day_view.set_theme(is_dark)
        self._month_view.set_theme(is_dark)
        self.apply_theme_custom()

    def apply_theme_custom(self):
        d = self.is_dark
        bg_app        = "#0A0B0F" if d else "#F5F6F8"
        bg_surface    = "#14161C" if d else "#FFFFFF"
        bg_surface_2  = "#1B1E26" if d else "#F0F2F5"
        fg_primary    = "#F2F4F7" if d else "#0B1220"
        fg_secondary  = "#A8B0BD" if d else "#4A5567"
        fg_tertiary   = "#6B7280" if d else "#8A93A6"
        border_subtle = "rgba(255,255,255,0.06)" if d else "rgba(11,18,32,0.06)"
        border        = "rgba(255,255,255,0.10)" if d else "rgba(11,18,32,0.10)"
        accent        = _C_CAL

        self.setStyleSheet(f"""
            QFrame#calToolbar {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 14px;
            }}
            QLabel#calRangeLbl {{
                color: {fg_primary}; background: transparent;
                font-size: 14px; font-weight: 800;
                padding: 0 12px;
            }}
            QFrame#calOuterCard {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 16px;
            }}
            QFrame#calLeftPane {{
                background: {bg_surface_2};
                border-top-left-radius: 16px;
                border-bottom-left-radius: 16px;
            }}
            QFrame#calAuthOverlay {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 16px;
            }}
            QLabel#calAuthLbl {{
                color: {fg_secondary}; background: transparent;
                font-size: 15px; font-weight: 700;
            }}
            QLabel#calAuthSub {{
                color: {fg_tertiary}; background: transparent;
                font-size: 12px;
            }}
            QFrame#stripSep, QFrame#colHdrSep {{
                border: none; border-top: 1px solid {border_subtle}; max-height: 1px;
            }}
            QFrame#colSep {{
                border: none; border-left: 1px solid {border_subtle}; max-width: 1px;
            }}

            /* 월뷰 */
            QFrame#monthDayHdr {{
                background: {bg_surface_2};
                border-bottom: 1px solid {border_subtle};
            }}
            QLabel#monthDayHdrLbl {{
                color: {fg_secondary}; background: transparent;
                font-size: 11px; font-weight: 800;
                letter-spacing: 0.04em;
            }}
            QLabel#monthDayHdrLbl[dow="sat"] {{ color: #42A5F5; }}
            QLabel#monthDayHdrLbl[dow="sun"] {{ color: #EF5350; }}
            QFrame#monthCell {{ background: transparent; border: none; }}

            /* 입력 */
            QLineEdit, QTextEdit, QDateTimeEdit {{
                background: {bg_surface_2}; color: {fg_primary};
                border: 1px solid {border_subtle}; border-radius: 7px;
                padding: 4px 8px;
            }}
            QLineEdit:focus, QTextEdit:focus, QDateTimeEdit:focus {{
                border: 1px solid {accent};
            }}
            QComboBox {{
                background: {bg_surface_2}; color: {fg_primary};
                border: 1px solid {border_subtle}; border-radius: 7px;
                padding: 4px 8px;
            }}
            QComboBox:focus {{ border: 1px solid {accent}; }}
            QCheckBox {{ color: {fg_primary}; spacing: 6px; }}

            QScrollBar:vertical {{ background: {bg_surface_2}; width: 6px; }}
            QScrollBar::handle:vertical {{
                background: {'#555' if d else '#ccc'}; border-radius: 3px;
            }}
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
        from app.api.google.auth import is_authenticated
        if is_authenticated() and not self._calendars:
            self._refresh_calendars()


# ── CalendarCard (대시보드) ──────────────────────────────────────────────────

class CalendarCard(QFrame):
    """대시보드 — 미니 월 뷰 + 오늘의 이벤트 3개."""
    open_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("calDashCard")
        self.setCursor(Qt.PointingHandCursor)
        self._is_dark = True
        self._today_events: list = []
        self._build_ui()
        self._apply_qss()

    def _build_ui(self):
        v = QVBoxLayout(self); v.setContentsMargins(18, 16, 18, 16); v.setSpacing(10)

        head = QHBoxLayout(); head.setSpacing(10)
        head.addWidget(LeeIconTile(icon=QIcon(":/img/calendar.svg"), color=_C_CAL,
                                    size=40, radius=10))
        title_box = QVBoxLayout(); title_box.setSpacing(2); title_box.setContentsMargins(0, 0, 0, 0)
        t = QLabel(tr("カレンダー")); t.setObjectName("calDashTitle")
        s = QLabel(""); s.setObjectName("calDashSub")
        title_box.addWidget(t); title_box.addWidget(s)
        head.addLayout(title_box, 1)
        self._sub_lbl = s
        v.addLayout(head)

        # 오늘 이벤트 미리보기
        self._events_box = QVBoxLayout(); self._events_box.setSpacing(4)
        v.addLayout(self._events_box)

        self._empty_lbl = QLabel(tr("本日の予定: なし"))
        self._empty_lbl.setObjectName("calDashEmpty")
        v.addWidget(self._empty_lbl)

        # 오늘 일자 표시
        today = QDate.currentDate()
        self._sub_lbl.setText(
            f"{today.year()}年 {today.month()}月 {today.day()}日 "
            f"({_DAY_NAMES_JP[today.dayOfWeek() - 1]})"
        )

    def set_today_events(self, events: list):
        """오늘의 이벤트 3개까지 표시."""
        # 기존 미리보기 제거
        while self._events_box.count() > 0:
            it = self._events_box.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        if not events:
            self._empty_lbl.setVisible(True); return
        self._empty_lbl.setVisible(False)
        for ev in events[:3]:
            start = ev.get("start", {})
            time_str = ""
            if "dateTime" in start:
                try:
                    s_dt = datetime.fromisoformat(
                        start["dateTime"].replace("Z", "+00:00")).astimezone()
                    time_str = s_dt.strftime("%H:%M")
                except Exception:
                    pass
            elif "date" in start:
                time_str = tr("終日")
            title = ev.get("summary", tr("(タイトルなし)"))[:24]
            row = QLabel(f"<b style='color:{_C_CAL}'>{time_str:>5}</b>  {title}")
            row.setObjectName("calDashRow")
            row.setTextFormat(Qt.RichText)
            self._events_box.addWidget(row)

    def refresh(self) -> None:
        """대시보드 데이터 페치 — 오늘의 이벤트 (자기 primary 캘린더 + saved 활성)."""
        try:
            from app.api.google.auth import is_authenticated
            if not is_authenticated():
                self.set_today_events([]); return
            from app.api.google.calendar import FetchCalendarListWorker, FetchEventsWorker
            from datetime import timedelta as _td

            today = QDate.currentDate()
            t_min = datetime(today.year(), today.month(), today.day(), tzinfo=timezone.utc)
            t_max = t_min + _td(days=1)
            tmin_iso = t_min.isoformat().replace("+00:00", "Z")
            tmax_iso = t_max.isoformat().replace("+00:00", "Z")

            def _on_cals(cals: list):
                # primary 만 — settings 의 enabled_ids 가 있으면 그걸 사용
                from app.core.config import load_settings
                saved = set(load_settings().get("calendar_enabled_ids", []) or [])
                ids = [c.get("id", "") for c in cals if c.get("id") in saved] if saved \
                      else [c.get("id", "") for c in cals if c.get("primary")]
                if not ids and cals:
                    ids = [cals[0].get("id", "")]
                if not ids:
                    self.set_today_events([]); return
                self._ev_worker = FetchEventsWorker(ids, tmin_iso, tmax_iso)
                self._ev_worker.data_fetched.connect(self.set_today_events)
                self._ev_worker.error.connect(lambda _e: None)
                self._ev_worker.finished.connect(self._ev_worker.deleteLater)
                self._ev_worker.start()

            self._cal_worker = FetchCalendarListWorker()
            self._cal_worker.data_fetched.connect(_on_cals)
            self._cal_worker.error.connect(lambda _e: None)
            self._cal_worker.finished.connect(self._cal_worker.deleteLater)
            self._cal_worker.start()
        except Exception as e:
            logger.debug(f"CalendarCard.refresh 실패: {e}")

    def set_theme(self, is_dark: bool):
        self._is_dark = is_dark
        self._apply_qss()

    def _apply_qss(self):
        d = self._is_dark
        bg = "#14161C" if d else "#FFFFFF"
        fg_p = "#F2F4F7" if d else "#0B1220"
        fg_t = "#6B7280" if d else "#8A93A6"
        bs = "rgba(255,255,255,0.06)" if d else "rgba(11,18,32,0.06)"
        self.setStyleSheet(f"""
            QFrame#calDashCard {{
                background: {bg}; border: 1px solid {bs};
                border-left: 4px solid {_C_CAL};
                border-radius: 14px;
            }}
            QFrame#calDashCard:hover {{ border-color: {_C_CAL}; }}
            QLabel#calDashTitle {{
                color: {fg_p}; background: transparent;
                font-size: 14px; font-weight: 800;
            }}
            QLabel#calDashSub {{
                color: {fg_t}; background: transparent; font-size: 11px;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QLabel#calDashRow {{
                color: {fg_p}; background: transparent;
                font-size: 11.5px;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QLabel#calDashEmpty {{
                color: {fg_t}; background: transparent; font-size: 11px;
                font-style: italic;
            }}
        """)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.open_requested.emit()
        super().mouseReleaseEvent(event)


__all__ = ["GoogleCalendarWidget", "CalendarCard"]
