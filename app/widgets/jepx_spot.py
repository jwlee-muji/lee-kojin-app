"""JEPX スポット 市場 ウィジェット — Phase 5.2 リニューアル.

디자인 출처: handoff/LEE_PROJECT/varA-detail-screens.jsx SpotDetail
모킹업 1:1 구현:
    - 5탭 SegmentedControl (当日 / 日次平均 / 月次平均 / 年次平均 / 曜日別)
    - DetailHeader (back · icon · title · subtitle · badge · CSV)
    - KPI strip (システム平均 · 最高値 · 最安値 · 取引量)
    - LeePivotTable (행: 시간/날짜/년월/년 · 열: 11에리어)
    - 라인 차트 + 에리어 on/off 칩 (LeeChartFrame 래퍼)
    - エリア別 平均価格 가로 비교 바 (10에리어)

[기존 보존]
    - FetchJepxSpotHistoryWorker (起動時 不足年度 자동 다운로드)
    - FetchJepxSpotTodayWorker (10:00~10:30 폴링)
    - 백그라운드 _JepxQueryTask (QThread.moveToThread) + 쿼리 캐시
    - DB 인덱스 자동 생성 (date 컬럼)
    - bus.settings_saved 구독 → imbalance_alert 재로드 (가격 색상 임계값)
"""
from __future__ import annotations

import csv
import logging
import math
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QDate, QTime, QTimer, QPoint, QThread, Signal, QObject
from PySide6.QtGui import QColor, QFont, QIcon, QPainter
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QSizePolicy, QToolTip,
    QVBoxLayout, QWidget,
)

from app.api.market.jepx_spot import (
    FetchJepxSpotHistoryWorker, FetchJepxSpotTodayWorker,
    current_fiscal_year, fiscal_year_range,
)
from app.core.config import (
    DB_JEPX_SPOT, JEPX_SPOT_AREAS, JEPX_SPOT_START_FY, load_settings,
)
from app.core.database import (
    get_db_connection, ensure_index, validate_column_name,
)
from app.core.events import bus
from app.core.i18n import tr
from app.ui.common import BaseWidget
from app.ui.components import (
    LeeButton, LeeCard, LeeChartFrame, LeeCountValue, LeeDateInput,
    LeeDetailHeader, LeeDialog, LeeIconTile, LeeKPI, LeePivotTable,
    LeeSegment, LeeSparkline, LeeTrend,
)

pg.setConfigOptions(antialias=True)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 토큰 / 정수
# ──────────────────────────────────────────────────────────────────────
_C_SPOT = "#FF7A45"   # --c-spot
_C_OK   = "#30D158"
_C_WARN = "#FF9F0A"
_C_BAD  = "#FF453A"

# 모드 ↔ 라벨 (SegTabs)
_MODES = [
    ("daily",       "当日"),
    ("daily_avg",   "日次平均"),
    ("monthly_avg", "月次平均"),
    ("yearly_avg",  "年次平均"),
    ("weekday_avg", "曜日別"),
]

# DB strftime('%w') 기준: 日=0 / 月=1 / ... / 土=6
_WEEKDAY_OPTIONS = [
    ("月曜日", 1), ("火曜日", 2), ("水曜日", 3), ("木曜日", 4),
    ("金曜日", 5), ("土曜日", 6), ("日曜日", 0),
]

# 에리어별 라인 색상 (PivotTable.AREA_COLORS 와 일관성 유지)
_AREA_COLORS = {
    "システム": "#FF7A45",
    "北海道":   "#4285F4",
    "東北":     "#EA4335",
    "東京":     "#FBBC05",
    "中部":     "#34A853",
    "北陸":     "#FF6D00",
    "関西":     "#7986CB",
    "中国":     "#E67C73",
    "四国":     "#0B8043",
    "九州":     "#8E24AA",
}

_LEFT_AXIS_W = 56


# ──────────────────────────────────────────────────────────────────────
# A. JepxSpotCard — 대시보드용 카드 (모킹업 1:1, varA-cards.jsx SpotCard)
# ──────────────────────────────────────────────────────────────────────
class JepxSpotCard(LeeCard):
    """JEPX スポット 카드 — varA-cards.jsx SpotCard 1:1.

    레이아웃:
        ┌─────────────────────────────────────────────────────┐
        │ [icon] JEPX スポット平均       [今日] [明日]         │ ← header
        │                                                      │
        │ 東京                       12.34 円/kWh ▲ 0.5        │ ← area + 큰 숫자 + Trend
        │                                                      │
        │ ╱╲╱╲╱╲╱╲╱╲╱╲ (sparkline)                            │
        │                                                      │
        │ 00:00  06:00  12:00  18:00  24:00                   │ ← time labels
        └─────────────────────────────────────────────────────┘
    """

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(accent_color="spot", interactive=True, parent=parent)
        self.setMinimumHeight(220)
        self._is_dark = True
        # 데이터 상태
        self._today_data: list[tuple] = []      # [(area, avg, max, min), ...]
        self._tomorrow_data: list[tuple] = []
        self._yesterday_data: list[tuple] = []  # trend 계산 (오늘 vs 어제)
        self._today_slots: list[float] = []     # [system_price × 48]
        self._tomorrow_slots: list[float] = []
        self._mode = "today"  # "today" | "tomorrow"
        self._area_idx = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(0)

        # ── 헤더: icon + title + (today/tomorrow 토글) ──────────
        header = QHBoxLayout()
        header.setSpacing(12)
        header.setContentsMargins(0, 0, 0, 14)

        self._icon = LeeIconTile(
            icon=QIcon(":/img/spot.svg"),
            color=_C_SPOT, size=40, radius=12,
        )
        header.addWidget(self._icon, 0, Qt.AlignTop)

        title_box = QVBoxLayout(); title_box.setSpacing(2); title_box.setContentsMargins(0, 0, 0, 0)
        self._title_lbl = QLabel(tr("JEPX スポット平均"))
        self._title_lbl.setObjectName("spotCardTitle")
        self._sub_lbl = QLabel(tr("JEPX リアルタイム · 9エリア"))
        self._sub_lbl.setObjectName("spotCardSub")
        title_box.addWidget(self._title_lbl)
        title_box.addWidget(self._sub_lbl)
        header.addLayout(title_box, 1)

        # 토글 pill (今日 / 明日) — QButtonGroup 으로 exclusive 보장
        from PySide6.QtWidgets import QButtonGroup
        toggle_wrap = QFrame(); toggle_wrap.setObjectName("spotToggleWrap")
        tg = QHBoxLayout(toggle_wrap); tg.setContentsMargins(2, 2, 2, 2); tg.setSpacing(0)
        self._btn_today = QPushButton(tr("今日"))
        self._btn_today.setObjectName("spotToggleBtn")
        self._btn_today.setCheckable(True); self._btn_today.setChecked(True)
        self._btn_today.setCursor(Qt.PointingHandCursor)
        self._btn_tomorrow = QPushButton(tr("明日"))
        self._btn_tomorrow.setObjectName("spotToggleBtn")
        self._btn_tomorrow.setCheckable(True)
        self._btn_tomorrow.setCursor(Qt.PointingHandCursor)
        self._toggle_group = QButtonGroup(self)
        self._toggle_group.setExclusive(True)
        self._toggle_group.addButton(self._btn_today, 0)
        self._toggle_group.addButton(self._btn_tomorrow, 1)
        self._btn_today.clicked.connect(lambda: self._switch_mode("today"))
        self._btn_tomorrow.clicked.connect(lambda: self._switch_mode("tomorrow"))
        tg.addWidget(self._btn_today)
        tg.addWidget(self._btn_tomorrow)
        header.addWidget(toggle_wrap, 0, Qt.AlignTop)

        layout.addLayout(header)

        # ── 메인 row: 에리어명(좌, 큼) / 큰 숫자 + 단위 + Trend (우) ──
        main_row = QHBoxLayout()
        main_row.setContentsMargins(0, 0, 0, 10)
        main_row.setSpacing(0)
        main_row.setAlignment(Qt.AlignBaseline)

        self._area_lbl = QLabel("--")
        self._area_lbl.setObjectName("spotCardArea")
        main_row.addWidget(self._area_lbl, 1, Qt.AlignBaseline)

        # 우측 숫자 그룹
        num_box = QHBoxLayout(); num_box.setSpacing(4); num_box.setAlignment(Qt.AlignBaseline)
        self._value_lbl = LeeCountValue(formatter=lambda v: f"{v:.2f}")
        self._value_lbl.setObjectName("spotCardValue")
        self._unit_lbl = QLabel(tr("円/kWh"))
        self._unit_lbl.setObjectName("spotCardUnit")
        self._trend = LeeTrend(inverse="normal")  # 가격 ↑ = bad (red)
        num_box.addWidget(self._value_lbl, 0, Qt.AlignBaseline)
        num_box.addWidget(self._unit_lbl,  0, Qt.AlignBaseline)
        num_box.addSpacing(6)
        num_box.addWidget(self._trend, 0, Qt.AlignVCenter)
        main_row.addLayout(num_box)

        layout.addLayout(main_row)

        # ── Sparkline + Y range 인디케이터 (오늘 모드 전용) ─────────
        self._chart_box = QWidget()
        # 부모 LeeCard 의 배경색을 그대로 노출 (시스템 default 색 침투 차단)
        self._chart_box.setAttribute(Qt.WA_TranslucentBackground, True)
        self._chart_box.setStyleSheet("background: transparent;")
        chart_layout = QVBoxLayout(self._chart_box)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.setSpacing(2)

        # 상단: range pill (MIN ~ MAX) — 오른쪽 정렬
        range_row = QHBoxLayout()
        range_row.setContentsMargins(0, 0, 0, 0); range_row.setSpacing(0)
        range_row.addStretch()
        self._range_lbl = QLabel("")
        self._range_lbl.setObjectName("spotRangeLbl")
        range_row.addWidget(self._range_lbl)
        chart_layout.addLayout(range_row)

        # Sparkline
        self._spark = LeeSparkline(_C_SPOT, height=48, fill_alpha=80)
        chart_layout.addWidget(self._spark)

        # 시간 라벨 (00:00 / 06:00 / 12:00 / 18:00 / 24:00)
        time_row = QHBoxLayout()
        time_row.setContentsMargins(0, 2, 0, 0); time_row.setSpacing(0)
        self._time_labels: list[QLabel] = []
        for t in ("00:00", "06:00", "12:00", "18:00", "24:00"):
            tl = QLabel(t); tl.setObjectName("spotTimeLbl")
            tl.setAlignment(Qt.AlignCenter)
            time_row.addWidget(tl, 1)
            self._time_labels.append(tl)
        chart_layout.addLayout(time_row)

        layout.addWidget(self._chart_box)

        # 슬롯 데이터 미공개 시 placeholder (chart_box 와 교체 표시)
        self._tomorrow_note = QLabel("")
        self._tomorrow_note.setObjectName("spotTomorrowNote")
        self._tomorrow_note.setAlignment(Qt.AlignCenter)
        self._tomorrow_note.setMinimumHeight(72)
        layout.addWidget(self._tomorrow_note)
        self._tomorrow_note.setVisible(False)   # setVisible 은 layout 추가 후

        layout.addStretch()

        # 에리어 cycling 타이머 (3초)
        self._cycle_timer = QTimer(self)
        self._cycle_timer.setInterval(3000)
        self._cycle_timer.timeout.connect(self._cycle_area)

        self._apply_local_qss()
        self.set_no_data()

    # ── 외부 API ─────────────────────────────────────────────
    def set_today_data(self, data: list[tuple]) -> None:
        """data: [(area_name, avg, max, min), ...]"""
        self._today_data = list(data) if data else []
        # 현재 모드의 데이터가 갱신됐으면 idx 리셋 + 재렌더
        # 다른 모드라도 trend 비교 대조군이 갱신됐으니 재렌더
        if self._mode == "today":
            self._area_idx = 0
        self._render_current()

    def set_tomorrow_data(self, data: list[tuple]) -> None:
        self._tomorrow_data = list(data) if data else []
        if self._mode == "tomorrow":
            self._area_idx = 0
        self._render_current()

    def set_yesterday_data(self, data: list[tuple]) -> None:
        """前日의 area 평균 — today 모드 trend 계산용."""
        self._yesterday_data = list(data) if data else []
        # 모드 전환 없이 trend 만 갱신
        self._render_current()

    def set_today_slots(self, slot_values: list[float]) -> None:
        """48 코마 system price (sparkline 用)"""
        self._today_slots = list(slot_values) if slot_values else []
        self._update_sparkline()

    def set_tomorrow_slots(self, slot_values: list[float]) -> None:
        """翌日 48 코마 system price (sparkline 用) — 14:00 頃 公開."""
        self._tomorrow_slots = list(slot_values) if slot_values else []
        self._update_sparkline()

    def set_no_data(self) -> None:
        self._today_data = []
        self._tomorrow_data = []
        self._yesterday_data = []
        self._today_slots = []
        self._tomorrow_slots = []
        self._area_lbl.setText(tr("データなし"))
        self._value_lbl.set_value(0.0, animate=False)
        self._value_lbl.setText("--")
        self._trend.set_value(None)
        self._range_lbl.setText("")
        self._update_chart_visibility()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        # sparkline 배경을 카드 surface 와 동일하게
        bg_surface = "#14161C" if is_dark else "#FFFFFF"
        self._spark.set_card_bg(bg_surface)
        self._apply_local_qss()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._cycle_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._cycle_timer.stop()

    # ── 내부 ─────────────────────────────────────────────────
    def _switch_mode(self, mode: str) -> None:
        if mode == self._mode:
            self._btn_today.setChecked(self._mode == "today")
            self._btn_tomorrow.setChecked(self._mode == "tomorrow")
            return
        self._mode = mode
        self._btn_today.setChecked(mode == "today")
        self._btn_tomorrow.setChecked(mode == "tomorrow")
        self._area_idx = 0
        self._render_current()
        self._update_sparkline()

    def _current_slots(self) -> list[float]:
        return self._today_slots if self._mode == "today" else self._tomorrow_slots

    def _update_sparkline(self) -> None:
        """현재 모드의 슬롯으로 sparkline + range 라벨 + 가시성 갱신."""
        slots = self._current_slots()
        self._spark.set_data(slots)
        self._update_range_label()
        self._update_chart_visibility()

    def _update_chart_visibility(self) -> None:
        """현재 모드의 슬롯 데이터 있을 때만 chart_box 표시, 없으면 placeholder."""
        show_chart = bool(self._current_slots())
        self._chart_box.setVisible(show_chart)
        self._tomorrow_note.setVisible(not show_chart)
        if not show_chart:
            if self._mode == "tomorrow":
                self._tomorrow_note.setText(tr("明日のデータ未公開 (毎日 10:05 頃公開)"))
            else:
                self._tomorrow_note.setText(tr("当日チャートデータ未公開"))

    def _update_range_label(self) -> None:
        """현재 모드 슬롯의 Y range 인디케이터 갱신."""
        slots = self._current_slots()
        if not slots:
            self._range_lbl.setText("")
            return
        mn = min(slots); mx = max(slots)
        self._range_lbl.setText(f"MIN {mn:.1f}  ·  MAX {mx:.1f}")

    def _cycle_area(self) -> None:
        # hover 중이면 스킵
        if self.underMouse():
            return
        data = self._current_data()
        if not data:
            return
        self._area_idx = (self._area_idx + 1) % len(data)
        self._render_current()

    def _current_data(self) -> list:
        return self._today_data if self._mode == "today" else self._tomorrow_data

    def _render_current(self) -> None:
        data = self._current_data()
        if not data:
            self._area_lbl.setText(tr("データなし"))
            self._value_lbl.set_value(0.0, animate=False)
            self._value_lbl.setText("--")
            self._trend.set_value(None)
            return
        idx = self._area_idx % len(data)
        entry = data[idx]
        # entry: (area, avg, max, min) — max/min 은 카드에서는 미사용
        area, avg = entry[0], entry[1]
        self._area_lbl.setText(tr(str(area)))
        self._value_lbl.set_value(float(avg))

        # Trend — 모드별로 비교 base 가 다름 (각 area 마다 다른 % 가 나오도록)
        # · today 모드: 오늘 area 평균 vs 어제 같은 area 평균
        # · tomorrow 모드: 내일 area 평균 vs 오늘 같은 area 평균
        # 가격 ↑ 면 ▲ red (bad), ↓ 면 ▼ green (ok)
        trend_value: Optional[float] = None
        if self._mode == "today" and self._yesterday_data:
            base = next(
                (row[1] for row in self._yesterday_data if row and row[0] == area), None
            )
            if base is not None and base > 0:
                trend_value = (avg - base) / base * 100.0
        elif self._mode == "tomorrow" and self._today_data:
            base = next(
                (row[1] for row in self._today_data if row and row[0] == area), None
            )
            if base is not None and base > 0:
                trend_value = (avg - base) / base * 100.0
        self._trend.set_value(trend_value)

    def _apply_local_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary    = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary  = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary   = "#6B7280" if is_dark else "#8A93A6"
        bg_surface_2  = "#1B1E26" if is_dark else "#F0F2F5"
        # 토글 pill (한 컨테이너 내 두 개 toggleable button)
        self.setStyleSheet(f"""
            QLabel#spotCardTitle {{
                font-size: 13px; font-weight: 600;
                color: {fg_secondary}; background: transparent;
            }}
            QLabel#spotCardSub {{
                font-size: 11px;
                color: {fg_tertiary}; background: transparent;
            }}
            QLabel#spotCardArea {{
                font-size: 22px; font-weight: 700;
                color: {_C_SPOT}; background: transparent;
                letter-spacing: -0.01em;
            }}
            QLabel#spotCardValue {{
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 32px; font-weight: 800;
                color: {fg_primary}; background: transparent;
                letter-spacing: -0.02em;
            }}
            QLabel#spotCardUnit {{
                font-size: 12px; font-weight: 600;
                color: {fg_tertiary}; background: transparent;
                padding-bottom: 4px;
            }}
            QLabel#spotTimeLbl {{
                font-size: 10px;
                color: {fg_tertiary}; background: transparent;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QLabel#spotRangeLbl {{
                font-size: 9px; font-weight: 700;
                color: {fg_tertiary}; background: transparent;
                font-family: "JetBrains Mono", "Consolas", monospace;
                letter-spacing: 0.04em;
            }}
            QLabel#spotTomorrowNote {{
                font-size: 11px; font-weight: 500;
                color: {fg_tertiary}; background: transparent;
                font-style: italic;
            }}
            QFrame#spotToggleWrap {{
                background: {bg_surface_2};
                border-radius: 999px;
            }}
            QPushButton#spotToggleBtn {{
                background: transparent;
                color: {fg_secondary};
                border: none;
                border-radius: 999px;
                padding: 4px 12px;
                font-size: 11px; font-weight: 600;
                min-height: 18px;
            }}
            QPushButton#spotToggleBtn:checked {{
                background: {_C_SPOT};
                color: #FFFFFF;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# B. _SpotMultiAreaChart — 11에리어 라인 차트 + 트래커 + 호버 툴팁
# ──────────────────────────────────────────────────────────────────────
class _SpotMultiAreaChart(pg.PlotWidget):
    """다중 에리어 라인 차트 (pyqtgraph) — area on/off 외부에서 set_visible()."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark = True
        self.showGrid(x=True, y=True, alpha=0.15)
        self.plotItem.hideAxis("top")
        self.plotItem.hideAxis("right")
        self.getAxis("left").setWidth(_LEFT_AXIS_W)

        self.plotItem.vb.disableAutoRange()
        self.setMenuEnabled(False)
        self.getPlotItem().hideButtons()

        self._vline = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen("#888", width=1, style=Qt.DashLine),
        )
        self._vline.setZValue(50)
        self.addItem(self._vline)

        self._tracker = pg.ScatterPlotItem()
        self._tracker.setZValue(100)
        self.addItem(self._tracker)

        self._proxy = pg.SignalProxy(
            self.scene().sigMouseMoved, rateLimit=120, slot=self._on_mouse
        )
        self._x_to_label: dict[float, str] = {}
        self._curves: list[pg.PlotDataItem] = []
        self._curve_meta: list[tuple[str, str]] = []  # (name, color)

        self._apply_theme_colors()

    # ── 외관 ─────────────────────────────────────────────────
    def _apply_theme_colors(self) -> None:
        bg = "#14161C" if self._is_dark else "#FFFFFF"
        ax_c = "#3D424D" if self._is_dark else "#C2C8D2"
        text_c = "#A8B0BD" if self._is_dark else "#4A5567"
        self.setBackground(bg)
        ax_pen = pg.mkPen(ax_c, width=1)
        text_pen = pg.mkPen(text_c)
        for name in ("left", "bottom"):
            ax = self.getAxis(name)
            ax.setPen(ax_pen)
            ax.setTextPen(text_pen)
        self.setLabel("left", tr("価格 (円/kWh)"), color=text_c, size="9pt")

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_theme_colors()

    def set_x_label(self, label: str) -> None:
        text_c = "#A8B0BD" if self._is_dark else "#4A5567"
        self.setLabel("bottom", label, color=text_c, size="9pt")

    def set_x_labels(self, x_to_label: dict) -> None:
        self._x_to_label = x_to_label

    # ── 마우스 / 트래커 ────────────────────────────────────────
    def _on_mouse(self, evt):
        scene_pos = evt[0]
        if not self.sceneBoundingRect().contains(scene_pos):
            self._tracker.setData([])
            QToolTip.hideText()
            return
        mp = self.plotItem.vb.mapSceneToView(scene_pos)
        self._vline.setPos(mp.x())
        self._update_tracker(mp.x())

        text = self._build_tooltip(mp.x())
        if text:
            vp = self.mapFromScene(scene_pos)
            gp = self.mapToGlobal(QPoint(int(vp.x()), int(vp.y())))
            QToolTip.showText(gp + QPoint(14, -10), text, self)
        else:
            QToolTip.hideText()

    def _nearest_x(self, x: float) -> Optional[float]:
        best_x = None
        best_d = float("inf")
        for c in self._curves:
            xd, _ = c.getData()
            if xd is None or len(xd) == 0:
                continue
            idx = int(np.argmin(np.abs(xd - x)))
            dist = abs(float(xd[idx]) - x)
            if dist < best_d:
                best_d = dist
                best_x = float(xd[idx])
        return best_x

    def _update_tracker(self, x: float) -> None:
        nx = self._nearest_x(x)
        if nx is None:
            self._tracker.setData([])
            return
        spots = []
        for c, (_, color) in zip(self._curves, self._curve_meta):
            xd, yd = c.getData()
            if xd is None or len(xd) == 0:
                continue
            idx = int(np.argmin(np.abs(xd - nx)))
            yv = float(yd[idx])
            if not math.isnan(yv):
                spots.append({
                    "pos":   (float(xd[idx]), yv),
                    "size":  10,
                    "pen":   pg.mkPen("white" if self._is_dark else "#0B1220", width=1.5),
                    "brush": pg.mkBrush(color),
                })
        self._tracker.setData(spots)

    def _build_tooltip(self, x: float) -> str:
        nx = self._nearest_x(x)
        if nx is None:
            return ""
        header = self._x_to_label.get(nx, f"{nx:.4g}")
        lines = [f"<b>{header}</b>"]
        for c, (name, color) in zip(self._curves, self._curve_meta):
            xd, yd = c.getData()
            if xd is None or len(xd) == 0:
                continue
            idx = int(np.argmin(np.abs(xd - nx)))
            y = float(yd[idx])
            if not math.isnan(y):
                lines.append(
                    f"<span style='color:{color}'>{name}</span>: "
                    f"<b>{y:.2f}</b> 円/kWh"
                )
        return "<br>".join(lines) if len(lines) > 1 else ""

    # ── 커브 관리 ────────────────────────────────────────────
    def clear_curves(self) -> None:
        for c in self._curves:
            self.removeItem(c)
        self._curves.clear()
        self._curve_meta.clear()
        self._tracker.setData([])
        self._x_to_label = {}

    def add_curve(self, x, y, name: str, color: str) -> None:
        pen = pg.mkPen(color=color, width=2)
        c = self.plot(x, y, pen=pen, name=name)
        self._curves.append(c)
        self._curve_meta.append((name, color))

    def fit_view(self, padding: float = 0.05) -> None:
        all_x: list[float] = []
        all_y: list[float] = []
        for c in self._curves:
            xd, yd = c.getData()
            if xd is not None and len(xd):
                all_x.extend(xd.tolist())
            if yd is not None and len(yd):
                all_y.extend(v for v in yd.tolist() if not math.isnan(v))
        if not all_x or not all_y:
            return
        x_min, x_max = min(all_x), max(all_x)
        y_min, y_max = min(all_y), max(all_y)
        x_span = (x_max - x_min) or 1.0
        y_span = (y_max - y_min) or 1.0
        self.plotItem.vb.setRange(
            xRange=(x_min - x_span * padding, x_max + x_span * padding),
            yRange=(y_min - y_span * padding, y_max + y_span * padding),
            padding=0,
        )

    def copy_to_clipboard(self) -> None:
        QApplication.clipboard().setPixmap(self.grab())


# ──────────────────────────────────────────────────────────────────────
# C. _SpotAreaBars — 에리어별 평균가격 가로 비교 바 (10개)
# ──────────────────────────────────────────────────────────────────────
class _SpotAreaBar(QWidget):
    """단일 가로 바 — 라벨 + 컬러 트랙 + 값."""

    def __init__(self, label: str, value: float, max_value: float, color: str, *, is_dark: bool):
        super().__init__()
        self._label = label
        self._value = value
        self._max_value = max(max_value, 1.0)
        self._color = color
        self._is_dark = is_dark
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        # 라벨 영역
        label_w = 60
        bar_x0 = label_w + 6
        val_w = 64
        bar_x1 = w - val_w - 6
        bar_h = 8
        bar_y = h // 2 - bar_h // 2

        # 라벨
        p.setPen(QColor("#A8B0BD" if self._is_dark else "#4A5567"))
        f = p.font(); f.setPointSize(9); f.setWeight(QFont.Weight.DemiBold); p.setFont(f)
        p.drawText(0, 0, label_w, h, Qt.AlignVCenter | Qt.AlignLeft, self._label)

        # 트랙
        track_color = QColor("#1B1E26") if self._is_dark else QColor("#F0F2F5")
        p.setPen(Qt.NoPen)
        p.setBrush(track_color)
        p.drawRoundedRect(bar_x0, bar_y, bar_x1 - bar_x0, bar_h, bar_h / 2, bar_h / 2)

        # 채움
        pct = max(0.0, min(1.0, self._value / self._max_value))
        fill_w = int((bar_x1 - bar_x0) * pct)
        if fill_w > 0:
            p.setBrush(QColor(self._color))
            p.drawRoundedRect(bar_x0, bar_y, fill_w, bar_h, bar_h / 2, bar_h / 2)

        # 값
        p.setPen(QColor("#F2F4F7" if self._is_dark else "#0B1220"))
        f2 = p.font(); f2.setFamily("JetBrains Mono"); f2.setPointSize(9); f2.setWeight(QFont.Weight.Bold)
        p.setFont(f2)
        val_txt = f"{self._value:.2f}"
        p.drawText(bar_x1 + 6, 0, val_w - 6, h, Qt.AlignVCenter | Qt.AlignRight, val_txt)
        p.end()


class _SpotAreaBars(QFrame):
    """에리어별 평균가격 비교 — 2열 그리드."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("spotAreaBars")
        self._is_dark = True
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 18)
        outer.setSpacing(8)

        self._title = QLabel(tr("エリア別 平均価格"))
        self._title.setObjectName("spotAreaBarsTitle")
        outer.addWidget(self._title)

        self._grid_box = QWidget()
        self._grid_layout = QHBoxLayout(self._grid_box)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(20)

        self._left_col = QVBoxLayout()
        self._right_col = QVBoxLayout()
        self._left_col.setSpacing(4)
        self._right_col.setSpacing(4)
        self._grid_layout.addLayout(self._left_col, 1)
        self._grid_layout.addLayout(self._right_col, 1)
        outer.addWidget(self._grid_box)

        self._apply_qss()

    def set_data(self, area_avgs: list[tuple[str, float]]) -> None:
        # 기존 자식 제거
        for col in (self._left_col, self._right_col):
            while col.count():
                item = col.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.setParent(None)
        if not area_avgs:
            return
        max_v = max((v for _, v in area_avgs), default=1.0)
        for i, (name, val) in enumerate(area_avgs):
            color = _AREA_COLORS.get(name, _C_SPOT)
            bar = _SpotAreaBar(name, val, max_v, color, is_dark=self._is_dark)
            (self._left_col if i % 2 == 0 else self._right_col).addWidget(bar)
        # stretch
        self._left_col.addStretch()
        self._right_col.addStretch()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()
        # 자식 바도 리페인트
        for col in (self._left_col, self._right_col):
            for i in range(col.count()):
                w = col.itemAt(i).widget()
                if isinstance(w, _SpotAreaBar):
                    w._is_dark = is_dark
                    w.update()

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary = "#F2F4F7" if is_dark else "#0B1220"
        bg_surface = "#14161C" if is_dark else "#FFFFFF"
        border_subtle = "rgba(255,255,255,0.04)" if is_dark else "rgba(11,18,32,0.06)"
        self.setStyleSheet(f"""
            QFrame#spotAreaBars {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 18px;
            }}
            QLabel#spotAreaBarsTitle {{
                font-size: 14px; font-weight: 700;
                color: {fg_primary};
                background: transparent;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# D. 백그라운드 쿼리 (기존 _JepxQueryTask 그대로 보존 + DB 헬퍼)
# ──────────────────────────────────────────────────────────────────────
def _run_db_query(mode: str, params: dict, areas: list) -> tuple:
    """SQLite 쿼리를 백그라운드 스레드에서 실행하는 순수 함수."""
    is_raw = mode == "daily"
    col_exprs = ", ".join(
        validate_column_name(col) if is_raw
        else f"AVG({validate_column_name(col)})"
        for _, col, _ in areas
    )

    with get_db_connection(DB_JEPX_SPOT) as conn:
        if mode == "daily":
            rows = conn.execute(
                f"SELECT slot, {col_exprs} FROM jepx_spot_prices "
                f"WHERE date=? ORDER BY slot",
                (params["date"],)
            ).fetchall()
            x_vals = [r[0] for r in rows]
            x_labels = [_slot_label(s) for s in x_vals]

        elif mode == "daily_avg":
            rows = conn.execute(
                f"SELECT date, {col_exprs} FROM jepx_spot_prices "
                f"WHERE date BETWEEN ? AND ? GROUP BY date ORDER BY date",
                (params["d0"], params["d1"])
            ).fetchall()
            x_vals = list(range(len(rows)))
            x_labels = [r[0] for r in rows]

        elif mode == "monthly_avg":
            rows = conn.execute(
                f"SELECT strftime('%Y-%m',date) ym, {col_exprs} "
                f"FROM jepx_spot_prices WHERE date BETWEEN ? AND ? "
                f"GROUP BY ym ORDER BY ym",
                (params["d0"], params["d1"])
            ).fetchall()
            x_vals = list(range(len(rows)))
            x_labels = [r[0] for r in rows]

        elif mode == "yearly_avg":
            rows = conn.execute(
                f"SELECT strftime('%Y',date) y, {col_exprs} "
                f"FROM jepx_spot_prices GROUP BY y ORDER BY y"
            ).fetchall()
            x_vals = [int(r[0]) for r in rows]
            x_labels = [r[0] for r in rows]

        else:  # weekday_avg
            rows = conn.execute(
                f"SELECT date, {col_exprs} FROM jepx_spot_prices "
                f"WHERE date BETWEEN ? AND ? "
                f"AND CAST(strftime('%w', date) AS INT) = ? "
                f"GROUP BY date ORDER BY date",
                (params["d0"], params["d1"], params["weekday"])
            ).fetchall()
            x_vals = list(range(len(rows)))
            x_labels = [r[0] for r in rows]

    return rows, x_vals, x_labels


class _JepxQueryTask(QObject):
    """현대화된 QObject 기반 쿼리 워커 (QThread.moveToThread 패턴)."""

    result = Signal(object, object, object, object)
    error  = Signal(str)

    def __init__(self, key: tuple, mode: str, params: dict, areas: list):
        super().__init__()
        self._key    = key
        self._mode   = mode
        self._params = params
        self._areas  = areas

    def run(self):
        try:
            rows, x_vals, x_labels = _run_db_query(self._mode, self._params, self._areas)
            self.result.emit(self._key, rows, x_vals, x_labels)
        except Exception as e:
            self.error.emit(str(e))


# ──────────────────────────────────────────────────────────────────────
# E. JepxSpotWidget — 디테일 페이지 (5モード × 9エリア + システム, 디자인 1:1)
# ──────────────────────────────────────────────────────────────────────
class JepxSpotWidget(BaseWidget):
    """JEPX スポット 디테일 페이지 — 5탭 SegmentedControl + 라인 + area-toggle 칩."""

    def __init__(self):
        super().__init__()
        # ── 상태 (기존 유지) ───────────────────────────────────
        self._mode         = "daily"
        self._sel_date     = QDate.currentDate()
        self._area_on: dict[str, bool] = {col: True for _, col in JEPX_SPOT_AREAS}
        fy_start_str, _    = fiscal_year_range(current_fiscal_year())
        self._dr_start     = QDate.fromString(fy_start_str, "yyyy-MM-dd")
        self._dr_end       = QDate.currentDate()
        self._sel_weekday  = 1  # 月曜
        self._fy_start     = max(JEPX_SPOT_START_FY, current_fiscal_year() - 2)
        self._fy_end       = current_fiscal_year()
        self._fetching     = False
        self._last_poll_date: Optional[QDate] = None
        # 쿼리 캐시 + 워커
        self._query_cache: dict[tuple, tuple] = {}
        self._query_thread: Optional[QThread] = None
        self._query_task: Optional[_JepxQueryTask] = None
        self._alert_val: float = float(load_settings().get("imbalance_alert", 40.0))

        # 마지막 데이터 (CSV / 코피용)
        self._last_headers: list[str] = []
        self._last_rows: list[list] = []
        self._last_x_vals: list = []
        self._last_x_labels: list = []

        # 에리어 체크박스 디바운스
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(50)
        self._refresh_timer.timeout.connect(self._refresh)

        bus.settings_saved.connect(self._reload_settings)

        self._build_ui()
        QTimer.singleShot(2250, self._ensure_db_index)
        QTimer.singleShot(3000, self._start_history_fetch)
        self._setup_poll_timer()

    # ──────────────────────────────────────────────────────────
    # UI 빌드
    # ──────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        # 페이지 자체는 ScrollArea 만 담는 빈 컨테이너 (배경 토큰화)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setObjectName("spotPageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer.addWidget(scroll, 1)

        content = QWidget()
        content.setObjectName("spotPageContent")
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(16)

        # 1) DetailHeader
        self._header = LeeDetailHeader(
            title=tr("JEPX スポット市場"),
            subtitle=tr("日本卸電力取引所 · 30分単位 · システム + 9エリア"),
            accent=_C_SPOT,
            icon_qicon=QIcon(":/img/spot.svg"),
            badge="",
            show_export=True,
        )
        self._header.back_clicked.connect(lambda: bus.page_requested.emit(0))
        self._header.export_clicked.connect(self._export_csv)
        root.addWidget(self._header)

        # 2) 모드 탭 + 모드별 컨트롤 + 액션 (filter row)
        root.addWidget(self._build_filter_row())

        # 3) 에리어 on/off 칩
        root.addWidget(self._build_area_chips())

        # 4) KPI strip
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self._kpi_avg   = LeeKPI(tr("システム平均"), value="--", unit=tr("円/kWh"), color=_C_SPOT, sub="")
        self._kpi_max   = LeeKPI(tr("最高値"),       value="--", unit=tr("円/kWh"), color=_C_BAD,  sub=tr("ピーク帯"))
        self._kpi_min   = LeeKPI(tr("最安値"),       value="--", unit=tr("円/kWh"), color=_C_OK,   sub=tr("深夜帯"))
        self._kpi_count = LeeKPI(tr("データ件数"),   value="--", unit=tr("件"),      sub="")
        kpi_row.addWidget(self._kpi_avg, 1)
        kpi_row.addWidget(self._kpi_max, 1)
        kpi_row.addWidget(self._kpi_min, 1)
        kpi_row.addWidget(self._kpi_count, 1)
        root.addLayout(kpi_row)

        # 5) PivotTable (고정 min) + Chart (고정 min) — splitter 제거, 스크롤이 처리
        self._pivot = LeePivotTable(
            mode="spot", accent=_C_SPOT, height=320,
            show_stats=False, row_header_label=tr("時刻"),
        )
        self._pivot.setMinimumHeight(360)
        root.addWidget(self._pivot)

        self._chart = _SpotMultiAreaChart()
        self._chart.setMinimumHeight(280)
        self._chart_frame = LeeChartFrame(
            tr("価格推移"),
            subtitle="",
            accent=_C_SPOT,
        )
        self._chart_frame.set_content(self._chart)
        self._chart_frame.setMinimumHeight(340)
        root.addWidget(self._chart_frame)
        # 첫 fetch 동안 차트 영역에 shimmer skeleton (디자인 정합)
        from app.ui.components.skeleton import install_skeleton_overlay
        self._chart_skel = install_skeleton_overlay(self._chart)

        # 6) エリア別 平均価格 bars
        self._area_bars = _SpotAreaBars()
        self._area_bars.setMinimumHeight(220)
        root.addWidget(self._area_bars)

        # 7) 진행 표시 + 상태 라벨 (작게)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(10)
        self._refresh_indicator = QLabel("")
        self._refresh_indicator.setObjectName("spotRefreshIndicator")
        bottom.addWidget(self._refresh_indicator)
        self._status = QLabel(tr("待機中"))
        self._status.setObjectName("spotStatusLabel")
        self._status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bottom.addStretch()
        bottom.addWidget(self._status)
        root.addLayout(bottom)

    def _build_filter_row(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("spotFilterBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)

        # 모드 SegmentedControl
        self._seg = LeeSegment(_MODES, value="daily", accent=_C_SPOT)
        self._seg.value_changed.connect(self._on_mode_changed)
        h.addWidget(self._seg)

        sep1 = self._make_sep()
        h.addWidget(sep1)

        # 모드별 컨트롤: 단일 날짜 (daily)
        self._day_box = QWidget()
        dl = QHBoxLayout(self._day_box)
        dl.setContentsMargins(0, 0, 0, 0); dl.setSpacing(6)
        self._date_input = LeeDateInput(accent=_C_SPOT, show_today_btn=True)
        self._date_input.date_changed.connect(self._on_day_changed)
        dl.addWidget(self._date_input)
        h.addWidget(self._day_box)

        # 모드별 컨트롤: 기간 (daily_avg, weekday_avg)
        self._dr_box = QWidget()
        drl = QHBoxLayout(self._dr_box)
        drl.setContentsMargins(0, 0, 0, 0); drl.setSpacing(6)
        drl.addWidget(self._period_lbl(tr("期間:")))
        self._dr_start_input = LeeDateInput(accent=_C_SPOT, show_today_btn=False)
        self._dr_start_input.set_date(self._dr_start)
        self._dr_start_input.date_changed.connect(self._on_dr_changed)
        self._dr_end_input = LeeDateInput(accent=_C_SPOT, show_today_btn=False)
        self._dr_end_input.set_date(self._dr_end)
        self._dr_end_input.date_changed.connect(self._on_dr_changed)
        self._btn_dr_fy = LeeButton(tr("今年度"), variant="secondary", size="sm")
        self._btn_dr_fy.clicked.connect(self._reset_dr_to_current_fy)
        sep_lbl = QLabel("〜"); sep_lbl.setObjectName("spotPeriodSep")
        drl.addWidget(self._dr_start_input)
        drl.addWidget(sep_lbl)
        drl.addWidget(self._dr_end_input)
        drl.addWidget(self._btn_dr_fy)
        self._dr_box.hide()
        h.addWidget(self._dr_box)

        # 모드별 컨트롤: 요일 (weekday_avg)
        self._wd_box = QWidget()
        wdl = QHBoxLayout(self._wd_box)
        wdl.setContentsMargins(0, 0, 0, 0); wdl.setSpacing(6)
        wdl.addWidget(self._period_lbl(tr("曜日:")))
        self._cmb_weekday = QComboBox()
        self._cmb_weekday.setObjectName("spotCombo")
        self._cmb_weekday.setFixedHeight(30)
        for label, val in _WEEKDAY_OPTIONS:
            self._cmb_weekday.addItem(label, val)
        self._cmb_weekday.currentIndexChanged.connect(self._on_weekday_changed)
        wdl.addWidget(self._cmb_weekday)
        self._wd_box.hide()
        h.addWidget(self._wd_box)

        # 모드별 컨트롤: 회계년도 (monthly_avg)
        self._fy_box = QWidget()
        fl = QHBoxLayout(self._fy_box)
        fl.setContentsMargins(0, 0, 0, 0); fl.setSpacing(6)
        fl.addWidget(self._period_lbl(tr("年度:")))
        cur_fy = current_fiscal_year()
        fy_list = list(range(JEPX_SPOT_START_FY, cur_fy + 1))
        self._cmb_fy_s = QComboBox(); self._cmb_fy_s.setObjectName("spotCombo")
        self._cmb_fy_e = QComboBox(); self._cmb_fy_e.setObjectName("spotCombo")
        for cmb in (self._cmb_fy_s, self._cmb_fy_e):
            cmb.setFixedHeight(30)
        for fy in fy_list:
            lbl = f"{fy}年度"
            self._cmb_fy_s.addItem(lbl, fy)
            self._cmb_fy_e.addItem(lbl, fy)
        self._cmb_fy_s.setCurrentIndex(max(0, len(fy_list) - 3))
        self._cmb_fy_e.setCurrentIndex(len(fy_list) - 1)
        self._cmb_fy_s.currentIndexChanged.connect(self._on_fy_changed)
        self._cmb_fy_e.currentIndexChanged.connect(self._on_fy_changed)
        fy_sep = QLabel("〜"); fy_sep.setObjectName("spotPeriodSep")
        fl.addWidget(self._cmb_fy_s)
        fl.addWidget(fy_sep)
        fl.addWidget(self._cmb_fy_e)
        self._fy_box.hide()
        h.addWidget(self._fy_box)

        # 연 모드: コントロールなし → label 표시
        self._yr_box = QLabel(tr("DB 全期間集計"))
        self._yr_box.setObjectName("spotYearLabel")
        self._yr_box.hide()
        h.addWidget(self._yr_box)

        h.addStretch()

        # 액션 버튼
        self._btn_refresh = LeeButton(tr("更新"), variant="secondary", size="sm")
        self._btn_refresh.clicked.connect(self._start_history_fetch)
        h.addWidget(self._btn_refresh)

        self._btn_copy = LeeButton(tr("📋 コピー"), variant="secondary", size="sm")
        self._btn_copy.clicked.connect(self._copy_table)
        h.addWidget(self._btn_copy)

        self._btn_csv = LeeButton(tr("⬇ CSV"), variant="secondary", size="sm")
        self._btn_csv.clicked.connect(self._export_csv)
        h.addWidget(self._btn_csv)

        self._btn_reset_view = LeeButton(tr("ビュー"), variant="ghost", size="sm")
        # _chart 는 _build_ui 후반에 생성됨 → 람다로 늦은 바인딩
        self._btn_reset_view.clicked.connect(lambda: self._chart.fit_view())
        h.addWidget(self._btn_reset_view)

        self._filter_bar = bar
        self._apply_filter_qss()
        return bar

    def _build_area_chips(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("spotChipsWrap")
        outer = QHBoxLayout(wrap)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        # 全選択 / クリア
        btn_all   = LeeButton(tr("全選択"), variant="ghost", size="sm")
        btn_clear = LeeButton(tr("クリア"), variant="ghost", size="sm")
        btn_all.clicked.connect(self._select_all_areas)
        btn_clear.clicked.connect(self._deselect_all_areas)
        outer.addWidget(btn_all)
        outer.addWidget(btn_clear)
        outer.addWidget(self._make_sep())

        # 칩들 (가로 스크롤 가능)
        chip_scroll = QScrollArea()
        chip_scroll.setObjectName("spotChipScroll")
        chip_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        chip_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        chip_scroll.setFrameShape(QFrame.NoFrame)
        chip_scroll.setWidgetResizable(True)

        chip_inner = QWidget()
        chip_layout = QHBoxLayout(chip_inner)
        chip_layout.setContentsMargins(0, 0, 0, 0)
        chip_layout.setSpacing(4)

        self._area_chips: dict[str, QPushButton] = {}
        for name, col in JEPX_SPOT_AREAS:
            color = _AREA_COLORS.get(name, _C_SPOT)
            chip = QPushButton(name)
            chip.setObjectName("spotAreaChip")
            chip.setCheckable(True)
            chip.setChecked(True)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setProperty("areaColor", color)
            chip.clicked.connect(lambda checked, c=col: self._on_area_toggled(c, checked))
            self._area_chips[col] = chip
            chip_layout.addWidget(chip)
        chip_layout.addStretch()
        chip_scroll.setWidget(chip_inner)
        chip_scroll.setFixedHeight(38)
        outer.addWidget(chip_scroll, 1)

        self._chip_wrap = wrap
        self._apply_chip_qss()
        return wrap

    @staticmethod
    def _period_lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("spotPeriodLbl")
        return lbl

    def _make_sep(self) -> QFrame:
        sep = QFrame()
        sep.setObjectName("spotFilterSep")
        sep.setFixedSize(1, 22)
        return sep

    # ──────────────────────────────────────────────────────────
    # 스타일
    # ──────────────────────────────────────────────────────────
    def _apply_filter_qss(self) -> None:
        is_dark = self.is_dark
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        bg_input     = "#1B1E26" if is_dark else "#FFFFFF"
        sep_color    = "rgba(255,255,255,0.10)" if is_dark else "rgba(11,18,32,0.10)"
        border       = "rgba(255,255,255,0.08)" if is_dark else "rgba(11,18,32,0.10)"
        self._filter_bar.setStyleSheet(f"""
            QFrame#spotFilterBar {{ background: transparent; }}
            QFrame#spotFilterSep {{ background: {sep_color}; border: none; }}
            QLabel#spotPeriodLbl {{
                font-size: 12px; font-weight: 700;
                color: {fg_secondary}; background: transparent;
                margin-right: 2px;
            }}
            QLabel#spotPeriodSep {{
                color: {fg_tertiary}; font-size: 12px;
                background: transparent;
                padding: 0 2px;
            }}
            QLabel#spotYearLabel {{
                font-size: 12px; font-style: italic;
                color: {fg_tertiary}; background: transparent;
            }}
            QComboBox#spotCombo {{
                background: {bg_input};
                color: {fg_primary};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 0 10px;
                font-size: 12px; font-weight: 600;
            }}
            QComboBox#spotCombo::drop-down {{ border: none; width: 18px; }}
            QLabel#spotRefreshIndicator {{
                font-size: 11px; font-weight: 600;
                color: {_C_OK};
                background: rgba(48,209,88,0.10);
                border: 1px solid rgba(48,209,88,0.25);
                border-radius: 999px;
                padding: 3px 10px;
            }}
            QLabel#spotStatusLabel {{
                font-size: 11px;
                color: {fg_secondary}; background: transparent;
            }}
        """)

    def _apply_chip_qss(self) -> None:
        is_dark = self.is_dark
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        bg_surface_2 = "#1B1E26" if is_dark else "#F0F2F5"
        border       = "rgba(255,255,255,0.08)" if is_dark else "rgba(11,18,32,0.10)"

        chip_qss_parts = [
            f"""
            QFrame#spotChipsWrap {{ background: transparent; }}
            QScrollArea#spotChipScroll {{ background: transparent; border: none; }}
            QPushButton#spotAreaChip {{
                background: {bg_surface_2};
                color: {fg_secondary};
                border: 1px solid {border};
                border-radius: 999px;
                padding: 4px 12px;
                font-size: 11px; font-weight: 700;
                min-height: 22px;
            }}
            QPushButton#spotAreaChip:!checked {{
                color: {fg_secondary};
            }}
            """
        ]
        # 칩별 색상 — checked 상태 컬러 적용
        for col, chip in self._area_chips.items():
            color = chip.property("areaColor") or _C_SPOT
            r, g, b = self._hex_to_rgb(color)
            chip_qss_parts.append(f"""
                QPushButton#spotAreaChip[areaColor="{color}"]:checked {{
                    background: rgba({r},{g},{b},0.14);
                    color: {color};
                    border: 1px solid {color};
                }}
            """)
        self._chip_wrap.setStyleSheet("\n".join(chip_qss_parts))

    @staticmethod
    def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
        h = hex_str.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    # ──────────────────────────────────────────────────────────
    # BaseWidget hooks
    # ──────────────────────────────────────────────────────────
    def apply_theme_custom(self) -> None:
        d = self.is_dark
        self._header.set_theme(d)
        for k in (self._kpi_avg, self._kpi_max, self._kpi_min, self._kpi_count):
            k.set_theme(d)
        self._date_input.set_theme(d)
        self._dr_start_input.set_theme(d)
        self._dr_end_input.set_theme(d)
        self._seg.set_theme(d)
        self._pivot.set_theme(d)
        self._chart_frame.set_theme(d)
        self._chart.set_theme(d)
        self._area_bars.set_theme(d)
        self._apply_page_qss()
        self._apply_filter_qss()
        self._apply_chip_qss()

    def _apply_page_qss(self) -> None:
        """ScrollArea / page content 의 배경을 bg_app 토큰으로."""
        bg_app = "#0A0B0F" if self.is_dark else "#F5F6F8"
        self.setStyleSheet(f"""
            JepxSpotWidget {{ background: {bg_app}; }}
            QScrollArea#spotPageScroll {{
                background: {bg_app};
                border: none;
            }}
            QWidget#spotPageContent {{ background: {bg_app}; }}
        """)

    def apply_settings_custom(self) -> None:
        # imbalance_alert 가 변하면 캐시 색상이 바뀌므로 (셀 색상은 가격 기반) — 재렌더만
        if self._last_headers and self._last_rows:
            self._render_all()

    # ──────────────────────────────────────────────────────────
    # 스케줄 / 폴링 (기존 보존)
    # ──────────────────────────────────────────────────────────
    def _start_history_fetch(self) -> None:
        if self._fetching:
            return
        self._fetching = True
        self._btn_refresh.setEnabled(False)
        self._set_status(tr("データ取得中…"))
        if getattr(self, "_chart_skel", None) is not None:
            self._chart_skel.start()

        w = FetchJepxSpotHistoryWorker()
        w.progress.connect(self._on_hist_progress)
        w.finished.connect(self._on_hist_finished)
        w.error.connect(lambda m: logger.warning(f"JEPX 履歴DLエラー: {m}"))
        self.track_worker(w); w.start()

    def _setup_poll_timer(self) -> None:
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(3 * 60 * 1000)  # 3 min
        self._poll_timer.timeout.connect(self._on_poll)
        self._poll_timer.start()

    def _on_poll(self) -> None:
        # JEPX는 매일 10:05 경 翌日 분 발표 → 10:00 ~ 11:00 사이 폴링
        now = QTime.currentTime()
        if QTime(10, 0) <= now <= QTime(11, 0):
            today = QDate.currentDate()
            if self._last_poll_date != today and not self._fetching:
                self._fetch_today()

    def _fetch_today(self) -> None:
        w = FetchJepxSpotTodayWorker()
        w.finished.connect(self._on_today_finished)
        w.error.connect(lambda m: self._set_status(tr("エラー: {0}").format(m)))
        self.track_worker(w); w.start()

    def _on_hist_progress(self, cur: int, total: int, year: int) -> None:
        self._set_status(tr("{0}年 データ取得中… ({1}/{2})").format(year, cur, total))

    def _on_hist_finished(self) -> None:
        self._fetching = False
        self._btn_refresh.setEnabled(True)
        self._query_cache.clear()
        self._set_status(tr("データ取得完了"))
        self._refresh()
        bus.jepx_spot_updated.emit()  # 대시보드 카드 재쿼리 트리거

    def _on_today_finished(self, found: bool) -> None:
        if found:
            self._last_poll_date = QDate.currentDate()
            self._query_cache.clear()
            self._set_status(
                tr("当日データ取得完了 ({0})").format(
                    QDate.currentDate().toString("yyyy-MM-dd"))
            )
            self._refresh()
            bus.jepx_spot_updated.emit()  # 대시보드 카드 재쿼리 트리거
        else:
            self._set_status(tr("当日データ未公開 — 次回再試行"))

    def _ensure_db_index(self) -> None:
        ensure_index(DB_JEPX_SPOT, "jepx_spot_prices", "date")

    def _reload_settings(self) -> None:
        self._alert_val = float(load_settings().get("imbalance_alert", 40.0))
        self._query_cache.clear()
        self._refresh()

    # ──────────────────────────────────────────────────────────
    # 모드 / 컨트롤 핸들러
    # ──────────────────────────────────────────────────────────
    def _on_mode_changed(self, key: str) -> None:
        self._mode = key
        is_daily   = key == "daily"
        is_monthly = key == "monthly_avg"
        is_weekday = key == "weekday_avg"
        is_yearly  = key == "yearly_avg"
        uses_dr    = key in ("daily_avg", "weekday_avg")

        self._day_box.setVisible(is_daily)
        self._dr_box.setVisible(uses_dr)
        self._wd_box.setVisible(is_weekday)
        self._fy_box.setVisible(is_monthly)
        self._yr_box.setVisible(is_yearly)
        self._refresh()

    def _on_day_changed(self, d: QDate) -> None:
        self._sel_date = d
        if self._mode == "daily":
            self._refresh()

    def _on_dr_changed(self, _d: QDate = None) -> None:
        self._dr_start = self._dr_start_input.date()
        self._dr_end   = self._dr_end_input.date()
        if self._mode in ("daily_avg", "weekday_avg"):
            self._refresh()

    def _reset_dr_to_current_fy(self) -> None:
        fy_start_str, _ = fiscal_year_range(current_fiscal_year())
        self._dr_start_input.set_date(QDate.fromString(fy_start_str, "yyyy-MM-dd"))
        self._dr_end_input.set_date(QDate.currentDate())

    def _on_fy_changed(self) -> None:
        self._fy_start = self._cmb_fy_s.currentData()
        self._fy_end   = self._cmb_fy_e.currentData()
        if self._mode == "monthly_avg":
            self._refresh()

    def _on_weekday_changed(self) -> None:
        self._sel_weekday = self._cmb_weekday.currentData()
        if self._mode == "weekday_avg":
            self._refresh()

    def _on_area_toggled(self, col: str, on: bool) -> None:
        self._area_on[col] = on
        self._refresh_timer.start()

    def _select_all_areas(self) -> None:
        for col, chip in self._area_chips.items():
            chip.blockSignals(True)
            chip.setChecked(True)
            self._area_on[col] = True
            chip.blockSignals(False)
            chip.style().unpolish(chip); chip.style().polish(chip)
        self._refresh_timer.start()

    def _deselect_all_areas(self) -> None:
        for col, chip in self._area_chips.items():
            chip.blockSignals(True)
            chip.setChecked(False)
            self._area_on[col] = False
            chip.blockSignals(False)
            chip.style().unpolish(chip); chip.style().polish(chip)
        self._refresh_timer.start()

    # ──────────────────────────────────────────────────────────
    # 데이터 취득 / 캐시 / 렌더링
    # ──────────────────────────────────────────────────────────
    def _enabled_areas(self) -> list[tuple[str, str, str]]:
        return [
            (name, col, _AREA_COLORS.get(name, _C_SPOT))
            for name, col in JEPX_SPOT_AREAS
            if self._area_on.get(col)
        ]

    def _fy_sql_range(self) -> tuple[str, str]:
        fy_s = min(self._fy_start, self._fy_end)
        fy_e = max(self._fy_start, self._fy_end)
        return fiscal_year_range(fy_s)[0], fiscal_year_range(fy_e)[1]

    def _dr_sql_range(self) -> tuple[str, str]:
        d0 = min(self._dr_start, self._dr_end).toString("yyyy-MM-dd")
        d1 = max(self._dr_start, self._dr_end).toString("yyyy-MM-dd")
        return d0, d1

    def _cache_key(self, areas: list) -> tuple:
        mode = self._mode
        area_cols = tuple(col for _, col, _ in areas)
        dark = self.is_dark
        if mode == "daily":
            return (mode, self._sel_date.toString("yyyy-MM-dd"), area_cols, dark)
        if mode in ("daily_avg", "weekday_avg"):
            d0, d1 = self._dr_sql_range()
            wd = self._sel_weekday if mode == "weekday_avg" else None
            return (mode, d0, d1, wd, area_cols, dark)
        if mode == "monthly_avg":
            return (mode, self._fy_start, self._fy_end, area_cols, dark)
        return (mode, area_cols, dark)  # yearly

    def _build_query_params(self) -> dict:
        params: dict = {}
        if self._mode == "daily":
            params["date"] = self._sel_date.toString("yyyy-MM-dd")
        elif self._mode in ("daily_avg", "weekday_avg"):
            params["d0"], params["d1"] = self._dr_sql_range()
            if self._mode == "weekday_avg":
                params["weekday"] = self._sel_weekday
        elif self._mode == "monthly_avg":
            params["d0"], params["d1"] = self._fy_sql_range()
        return params

    def _refresh(self) -> None:
        if self._fetching:
            return
        areas = self._enabled_areas()
        if not areas:
            self._pivot.set_data([], [])
            self._chart.clear_curves()
            self._area_bars.set_data([])
            self._set_status(tr("エリアが選択されていません"))
            self._update_kpis([], [])
            return

        key = self._cache_key(areas)
        if key in self._query_cache:
            rows, x_vals, x_labels = self._query_cache[key]
            self._on_data(rows, x_vals, x_labels, areas)
            return

        # 백그라운드 쿼리
        try:
            if self._query_thread and self._query_thread.isRunning():
                try:
                    if self._query_task:
                        self._query_task.result.disconnect()
                        self._query_task.error.disconnect()
                except (RuntimeError, TypeError):
                    pass
        except RuntimeError:
            self._query_thread = None
            self._query_task = None

        self._query_thread = QThread()
        self._query_task = _JepxQueryTask(key, self._mode, self._build_query_params(), areas)
        self._query_task.moveToThread(self._query_thread)
        self._query_thread.started.connect(self._query_task.run)
        self._query_task.result.connect(self._on_query_done)
        self._query_task.error.connect(self._on_query_error)
        self._query_task.result.connect(self._query_thread.quit)
        self._query_task.error.connect(self._query_thread.quit)
        self._query_thread.finished.connect(self._query_thread.deleteLater)
        self._query_task.result.connect(self._query_task.deleteLater)
        self._query_task.error.connect(self._query_task.deleteLater)

        self._query_thread.start()
        self.track_worker(self._query_thread)
        self._set_status(tr("データ読込中…"))

    def _on_query_done(self, key, rows, x_vals, x_labels) -> None:
        current_areas = self._enabled_areas()
        current_key = self._cache_key(current_areas)
        if key != current_key:
            return  # 옛 결과 폐기
        self._query_cache[key] = (rows, x_vals, x_labels)
        self._on_data(rows, x_vals, x_labels, current_areas)

    def _on_query_error(self, msg: str) -> None:
        logger.warning(f"JEPXスポット クエリ失敗: {msg}")
        self._set_status(tr("データ取得エラー: {0}").format(msg))

    def _on_data(self, rows, x_vals, x_labels, areas) -> None:
        # 마지막 데이터 기억
        x_hdr = self._row_header_label_for_mode()
        headers = [x_hdr] + [name for name, _, _ in areas]
        # rows → 표시용 (시간/날짜 + value strings)
        display_rows = self._build_display_rows(rows, areas, x_labels)
        self._last_headers = headers
        self._last_rows    = display_rows
        self._last_x_vals  = x_vals
        self._last_x_labels = x_labels
        self._render_all()
        self._update_status_count(rows)

    def _row_header_label_for_mode(self) -> str:
        return {
            "daily":       tr("時刻"),
            "daily_avg":   tr("日付"),
            "monthly_avg": tr("年月"),
            "yearly_avg":  tr("年"),
            "weekday_avg": tr("日付"),
        }.get(self._mode, tr("X"))

    def _build_display_rows(self, rows, areas, x_labels) -> list[list]:
        is_daily = self._mode == "daily"
        out: list[list] = []
        for i, row in enumerate(rows):
            if is_daily:
                slot = row[0]
                lbl = f"{_slot_label(slot)}"
            else:
                lbl = x_labels[i] if i < len(x_labels) else str(row[0])
            cells = [lbl]
            for ci in range(1, len(areas) + 1):
                v = row[ci] if ci < len(row) else None
                cells.append(f"{v:.2f}" if v is not None else "—")
            out.append(cells)
        return out

    def _render_all(self) -> None:
        # 1) PivotTable
        self._pivot.set_data(self._last_headers, self._last_rows)
        # 2) Chart
        self._render_chart()
        # 3) Area bars (전체 평균)
        self._render_area_bars()
        # 4) KPIs
        areas = self._enabled_areas()
        rows = self._raw_rows_from_cache(areas)
        self._update_kpis(rows, areas)
        # 5) Chart subtitle 갱신
        self._chart_frame.set_subtitle(self._mode_subtitle())

    def _raw_rows_from_cache(self, areas: list) -> list:
        key = self._cache_key(areas)
        cached = self._query_cache.get(key)
        if cached is None:
            return []
        return cached[0]

    def _render_chart(self) -> None:
        rows = self._raw_rows_from_cache(self._enabled_areas())
        x_vals, x_labels = self._last_x_vals, self._last_x_labels
        areas = self._enabled_areas()
        self._chart.clear_curves()
        # 데이터 도착 시 skeleton 숨기기 (재사용 가능 — refresh 시 다시 .start())
        if rows and areas and getattr(self, "_chart_skel", None) is not None:
            self._chart_skel.stop()
        if not rows or not areas:
            return

        mode = self._mode
        is_indexed = mode in ("daily_avg", "monthly_avg", "weekday_avg")

        x_label_map = {
            "daily":       tr("時刻 (30分単位)"),
            "daily_avg":   tr("日付"),
            "monthly_avg": tr("年月"),
            "yearly_avg":  tr("年"),
            "weekday_avg": tr("日付"),
        }
        self._chart.set_x_label(x_label_map.get(mode, ""))

        if is_indexed:
            step = max(1, math.ceil(len(x_labels) / 20))
            ticks = [
                [(x_vals[i], x_labels[i]) for i in range(0, len(x_labels), step)]
            ]
            self._chart.getAxis("bottom").setTicks(ticks)
        elif mode == "daily":
            ticks = [[(s, _slot_label(s)) for s in range(1, 49, 4)]]
            self._chart.getAxis("bottom").setTicks(ticks)
        else:
            self._chart.getAxis("bottom").setTicks(None)

        if is_indexed:
            x_to_lbl = {float(i): x_labels[i] for i in range(len(x_labels))}
        elif mode == "daily":
            x_to_lbl = {float(s): f"{_slot_label(s)}〜{_slot_label_end(s)}" for s in x_vals}
        else:
            x_to_lbl = {float(v): str(v) for v in x_vals}
        self._chart.set_x_labels(x_to_lbl)

        for i, (name, _, color) in enumerate(areas):
            y_vals = [
                (row[i + 1] if (i + 1) < len(row) and row[i + 1] is not None else float("nan"))
                for row in rows
            ]
            self._chart.add_curve(x_vals, y_vals, name=name, color=color)

        self._chart.fit_view()

    def _render_area_bars(self) -> None:
        rows = self._raw_rows_from_cache(self._enabled_areas())
        areas = self._enabled_areas()
        if not rows or not areas:
            self._area_bars.set_data([])
            return
        out: list[tuple[str, float]] = []
        for i, (name, _, _) in enumerate(areas):
            vals = [row[i + 1] for row in rows if (i + 1) < len(row) and row[i + 1] is not None]
            if vals:
                out.append((name, sum(vals) / len(vals)))
        self._area_bars.set_data(out)

    def _update_kpis(self, rows: list, areas: list) -> None:
        if not rows or not areas:
            self._kpi_avg.set_value("--",  unit=tr("円/kWh"), color=_C_SPOT, sub="")
            self._kpi_max.set_value("--",  unit=tr("円/kWh"), color=_C_BAD,  sub="")
            self._kpi_min.set_value("--",  unit=tr("円/kWh"), color=_C_OK,   sub="")
            self._kpi_count.set_value("0", unit=tr("件"), sub="")
            return

        all_vals: list[float] = []
        for row in rows:
            for ci in range(1, len(areas) + 1):
                if ci < len(row) and row[ci] is not None:
                    all_vals.append(float(row[ci]))
        if not all_vals:
            self._kpi_avg.set_value("--",  unit=tr("円/kWh"), color=_C_SPOT, sub="")
            self._kpi_max.set_value("--",  unit=tr("円/kWh"), color=_C_BAD,  sub="")
            self._kpi_min.set_value("--",  unit=tr("円/kWh"), color=_C_OK,   sub="")
            self._kpi_count.set_value("0", unit=tr("件"), sub="")
            return

        avg = sum(all_vals) / len(all_vals)
        mx = max(all_vals)
        mn = min(all_vals)
        self._kpi_avg.set_value(f"{avg:.2f}", unit=tr("円/kWh"), color=_C_SPOT, sub=self._mode_subtitle())
        self._kpi_max.set_value(f"{mx:.2f}", unit=tr("円/kWh"), color=_C_BAD,  sub=tr("ピーク値"))
        self._kpi_min.set_value(f"{mn:.2f}", unit=tr("円/kWh"), color=_C_OK,   sub=tr("最安値"))
        self._kpi_count.set_value(f"{len(rows):,}", unit=tr("件"), sub=tr("{0} エリア表示中").format(len(areas)))

    def _mode_subtitle(self) -> str:
        m = self._mode
        if m == "daily":
            return tr("{0} · 48 コマ").format(self._sel_date.toString("yyyy-MM-dd"))
        if m == "daily_avg":
            d0, d1 = self._dr_sql_range()
            return tr("{0} 〜 {1} 日次平均").format(d0, d1)
        if m == "monthly_avg":
            return tr("{0}年度 〜 {1}年度 月次平均").format(self._fy_start, self._fy_end)
        if m == "yearly_avg":
            return tr("DB 全期間 年次平均")
        if m == "weekday_avg":
            d0, d1 = self._dr_sql_range()
            wd_label = self._cmb_weekday.currentText()
            return tr("{0} ({1} 〜 {2})").format(wd_label, d0, d1)
        return ""

    def _update_status_count(self, rows: list) -> None:
        if not rows:
            self._set_status(tr("データなし"))
            return
        if self._mode == "weekday_avg":
            d0, d1 = self._dr_sql_range()
            self._set_status(
                tr("{0} ({1} 〜 {2}): {3} 件").format(
                    self._cmb_weekday.currentText(), d0, d1, len(rows))
            )
        else:
            self._set_status(tr("{0} 件のデータを表示中").format(len(rows)))

    def _set_status(self, msg: str) -> None:
        self._status.setText(msg)

    # ──────────────────────────────────────────────────────────
    # CSV / 코피
    # ──────────────────────────────────────────────────────────
    def _copy_table(self) -> None:
        if not self._last_headers or not self._last_rows:
            bus.toast_requested.emit(tr("コピー可能なデータがありません"), "warning")
            return
        lines = ["\t".join(self._last_headers)]
        for r in self._last_rows:
            lines.append("\t".join(str(c) for c in r))
        QApplication.clipboard().setText("\n".join(lines))
        bus.toast_requested.emit(tr("テーブルをコピーしました"), "success")

    def _export_csv(self) -> None:
        if not self._last_rows:
            LeeDialog.error(tr("エラー"), tr("保存するデータがありません。"), parent=self)
            return
        suffix = self._mode
        if self._mode == "daily":
            suffix = self._sel_date.toString("yyyyMMdd")
        elif self._mode in ("daily_avg", "weekday_avg"):
            d0, d1 = self._dr_sql_range()
            suffix = f"{d0}_{d1}".replace("-", "")
        elif self._mode == "monthly_avg":
            suffix = f"FY{self._fy_start}_{self._fy_end}"
        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("CSV保存"),
            f"JEPX_spot_{self._mode}_{suffix}.csv",
            "CSV Files (*.csv)",
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(self._last_headers)
                for row in self._last_rows:
                    writer.writerow(row)
            LeeDialog.info(
                tr("完了"),
                tr("CSVファイルとして保存しました。\nExcelで開くことができます。"),
                parent=self,
            )
        except (IOError, csv.Error) as e:
            LeeDialog.error(
                tr("エラー"), tr("保存に失敗しました:\n{0}").format(e), parent=self,
            )

    # ──────────────────────────────────────────────────────────
    # 정리
    # ──────────────────────────────────────────────────────────
    def closeEvent(self, event):
        try:
            bus.settings_saved.disconnect(self._reload_settings)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)


# ──────────────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────────────
def _slot_label(slot: int) -> str:
    m = (slot - 1) * 30
    return f"{m // 60:02d}:{m % 60:02d}"


def _slot_label_end(slot: int) -> str:
    m = slot * 30
    return f"{m // 60:02d}:{m % 60:02d}"
