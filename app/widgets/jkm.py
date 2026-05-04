"""エネルギー指標 ウィジェット (旧 JKM) — Phase 5.4 リニューアル.

데이터 소스: Yahoo Finance (yfinance) — multi-ticker (LNG/原油/為替 など)

디자인 출처: handoff/LEE_PROJECT/varA-detail-screens2.jsx EnergyIndicatorsDetail
            handoff/LEE_PROJECT/varA-cards.jsx JkmCard

모킹업 1:1 구현:
    - JkmCard (대시보드): JKM 중심 (대표 LNG 가격) + sparkline + Trend
    - JkmWidget (디테일): 지표 타일 그리드 (8개) + 활성 지표 차트/KPI
      DetailHeader + period segment (30D/90D/1Y/All) + KPI 6종 + 라인 차트 (MA)

[기존 보존]
    - 구 FetchJkmWorker / DB_JKM (jkm_prices) — 호환성 유지 (fallback)
    - settings.jkm_interval (자동 갱신)
    - bus.jkm_updated emit

[신규]
    - FetchEnergyIndicatorsWorker — 6 지표 병렬 다운로드 (LNG/HH/Brent/WTI/USD-JPY/EUR-JPY)
    - DB_ENERGY (energy_prices 테이블) 통합 저장
"""
from __future__ import annotations

import csv
import logging
import math
import sqlite3
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QPoint, QTimer, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QToolTip, QVBoxLayout, QWidget,
)

from app.api.market.energy_indicators import (
    FetchEnergyIndicatorsWorker, has_indicator_data, migrate_legacy_jkm,
    query_indicator,
)
from app.core.config import DB_JKM, ENERGY_INDICATORS
from app.core.database import get_db_connection
from app.core.events import bus
from app.core.i18n import tr
from app.ui.common import BaseWidget
from app.ui.components import (
    LeeButton, LeeCard, LeeChartFrame, LeeCountValue, LeeDetailHeader,
    LeeDialog, LeeIconTile, LeeKPI, LeeSegment, LeeSparkline, LeeTrend,
)

pg.setConfigOptions(antialias=True)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 토큰 / 정수
# ──────────────────────────────────────────────────────────────────────
_C_JKM  = "#F4B740"   # --c-jkm
_C_OK   = "#30D158"
_C_WARN = "#FF9F0A"
_C_BAD  = "#FF453A"

# 기간 → 거래일 수 (대략, 휴일 무시)
_PERIODS = [
    ("30d",  "30日"),
    ("90d",  "90日"),
    ("1y",   "1年"),
    ("all",  "全期間"),
]
_PERIOD_DAYS = {"30d": 30, "90d": 90, "1y": 250, "all": 0}  # 0 = 무제한

# MA 윈도우 (거래일)
_MA_4W  = 20  # 4 주
_MA_12W = 60  # 12 주

_LEFT_AXIS_W = 60


# ──────────────────────────────────────────────────────────────────────
# A. JkmCard — 대시보드 카드
# ──────────────────────────────────────────────────────────────────────
class JkmCard(LeeCard):
    """JKM LNG 카드 — 모킹업 JkmCard 1:1.

    레이아웃:
        ┌─────────────────────────────────────────────────────┐
        │ [icon] JKM LNG                          ▲ 1.2%      │
        │        Japan Korea Marker · USD/MMBtu              │
        │                                                      │
        │ 14.32 USD/MMBtu                                      │
        │ 2026-05-01                                           │
        │                                                      │
        │ MIN 12.50  ·  MAX 16.80                              │
        │ ╱╲╱╲╱╲╱╲ (sparkline 30d)                            │
        │ 30日前                                       最新   │
        └─────────────────────────────────────────────────────┘
    """

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(accent_color="jkm", interactive=True, parent=parent)
        self.setMinimumHeight(220)
        self._is_dark = True
        self._last_payload: Optional[dict] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(0)

        # 헤더
        header = QHBoxLayout(); header.setSpacing(12); header.setContentsMargins(0, 0, 0, 12)
        self._icon = LeeIconTile(
            icon=QIcon(":/img/fire.svg"),
            color=_C_JKM, size=40, radius=12,
        )
        header.addWidget(self._icon, 0, Qt.AlignTop)

        title_box = QVBoxLayout(); title_box.setSpacing(2); title_box.setContentsMargins(0, 0, 0, 0)
        self._title_lbl = QLabel(tr("エネルギー指標"))
        self._title_lbl.setObjectName("jkmCardTitle")
        self._sub_lbl = QLabel(tr("LNG · 原油 · 為替 (JKM 中心)"))
        self._sub_lbl.setObjectName("jkmCardSub")
        title_box.addWidget(self._title_lbl)
        title_box.addWidget(self._sub_lbl)
        header.addLayout(title_box, 1)

        # Trend (전일비)
        self._trend = LeeTrend(inverse="normal")  # 가격 ↑ → 빨강
        header.addWidget(self._trend, 0, Qt.AlignTop)

        layout.addLayout(header)

        # 큰 숫자 + 단위
        num_row = QHBoxLayout(); num_row.setSpacing(4)
        num_row.setContentsMargins(0, 0, 0, 2); num_row.setAlignment(Qt.AlignBaseline)
        self._value_lbl = LeeCountValue(formatter=lambda v: f"{v:.3f}")
        self._value_lbl.setObjectName("jkmCardValue")
        self._unit_lbl = QLabel(tr("USD/MMBtu"))
        self._unit_lbl.setObjectName("jkmCardUnit")
        num_row.addWidget(self._value_lbl, 0, Qt.AlignBaseline)
        num_row.addWidget(self._unit_lbl,  0, Qt.AlignBaseline)
        num_row.addStretch()
        layout.addLayout(num_row)

        self._date_lbl = QLabel("")
        self._date_lbl.setObjectName("jkmCardDate")
        layout.addWidget(self._date_lbl)

        # Sparkline + range
        chart_box = QWidget()
        chart_lay = QVBoxLayout(chart_box)
        chart_lay.setContentsMargins(0, 8, 0, 0); chart_lay.setSpacing(2)

        range_row = QHBoxLayout(); range_row.setContentsMargins(0, 0, 0, 0); range_row.setSpacing(0)
        range_row.addStretch()
        self._range_lbl = QLabel(""); self._range_lbl.setObjectName("jkmRangeLbl")
        range_row.addWidget(self._range_lbl)
        chart_lay.addLayout(range_row)

        self._spark = LeeSparkline(_C_JKM, height=44, fill_alpha=80)
        chart_lay.addWidget(self._spark)

        # 시작 / 끝 날짜 라벨
        edge_row = QHBoxLayout(); edge_row.setContentsMargins(0, 2, 0, 0); edge_row.setSpacing(0)
        self._start_lbl = QLabel("30日前"); self._start_lbl.setObjectName("jkmEdgeLbl")
        self._end_lbl   = QLabel("最新"); self._end_lbl.setObjectName("jkmEdgeLbl")
        self._end_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        edge_row.addWidget(self._start_lbl)
        edge_row.addStretch()
        edge_row.addWidget(self._end_lbl)
        chart_lay.addLayout(edge_row)

        self._chart_box = chart_box
        layout.addWidget(self._chart_box)

        # 데이터 없을 때
        self._note = QLabel(tr("データなし"))
        self._note.setObjectName("jkmCardNote")
        self._note.setAlignment(Qt.AlignCenter)
        self._note.setMinimumHeight(72)
        layout.addWidget(self._note)
        self._note.setVisible(False)   # setVisible 은 layout 추가 후

        layout.addStretch()
        self._apply_local_qss()
        self.set_no_data()

    # ── 외부 API ─────────────────────────────────────────────
    def set_payload(self, payload: dict) -> None:
        latest = payload.get("latest")
        if latest is None:
            self.set_no_data(); return
        self._last_payload = payload

        self._value_lbl.set_value(float(latest))
        self._date_lbl.setText(str(payload.get("latest_date", "")))

        # Trend (전일비를 헤더에 표시)
        dod = payload.get("dod_pct")
        self._trend.set_value(dod)

        # Sparkline
        spark = payload.get("sparkline") or []
        values = [v for _, v in spark]
        self._spark.set_data(values)

        if values:
            mn = min(values); mx = max(values)
            self._range_lbl.setText(f"MIN {mn:.2f}  ·  MAX {mx:.2f}")
            if spark:
                self._start_lbl.setText(str(spark[0][0]))
                self._end_lbl.setText(str(spark[-1][0]))
            self._chart_box.setVisible(True)
            self._note.setVisible(False)
        else:
            self._chart_box.setVisible(False)
            self._note.setVisible(True)
            self._note.setText(tr("チャートデータなし"))

    def set_no_data(self) -> None:
        self._last_payload = None
        self._value_lbl.set_value(0.0, animate=False)
        self._value_lbl.setText("--")
        self._date_lbl.setText(tr("データなし"))
        self._trend.set_value(None)
        self._spark.set_data([])
        self._range_lbl.setText("")
        self._chart_box.setVisible(False)
        self._note.setVisible(True)
        self._note.setText(tr("データなし"))

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        bg_surface = "#14161C" if is_dark else "#FFFFFF"
        self._spark.set_card_bg(bg_surface)
        self._apply_local_qss()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def _apply_local_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        self.setStyleSheet(f"""
            QLabel#jkmCardTitle {{
                font-size: 13px; font-weight: 600;
                color: {fg_secondary}; background: transparent;
            }}
            QLabel#jkmCardSub {{
                font-size: 11px; color: {fg_tertiary};
                background: transparent;
            }}
            QLabel#jkmCardValue {{
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 32px; font-weight: 800;
                color: {_C_JKM}; background: transparent;
                letter-spacing: -0.02em;
            }}
            QLabel#jkmCardUnit {{
                font-size: 12px; font-weight: 600;
                color: {fg_tertiary}; background: transparent;
                padding-bottom: 4px;
            }}
            QLabel#jkmCardDate {{
                font-size: 11px; color: {fg_secondary};
                background: transparent;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QLabel#jkmRangeLbl {{
                font-size: 9px; font-weight: 700;
                color: {fg_tertiary}; background: transparent;
                font-family: "JetBrains Mono", "Consolas", monospace;
                letter-spacing: 0.04em;
            }}
            QLabel#jkmEdgeLbl {{
                font-size: 10px; color: {fg_tertiary};
                background: transparent;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QLabel#jkmCardNote {{
                font-size: 11px; font-weight: 500;
                color: {fg_tertiary}; background: transparent;
                font-style: italic;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# B. _JkmChart — 라인 차트 + MA 오버레이 + 호버
# ──────────────────────────────────────────────────────────────────────
class _JkmChart(pg.PlotWidget):
    """JKM 라인 차트 — close 라인 + 4w / 12w MA 옵션 토글, 호버 툴팁."""

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
            self.scene().sigMouseMoved, rateLimit=120, slot=self._on_mouse,
        )
        self._x_to_label: dict[float, str] = {}
        self._curves: list[pg.PlotDataItem] = []
        self._curve_meta: list[tuple[str, str]] = []  # (name, color)

        self._apply_theme_colors()

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
        self.setLabel("left", tr("USD/MMBtu"), color=text_c, size="9pt")

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_theme_colors()

    def set_x_label(self, label: str) -> None:
        text_c = "#A8B0BD" if self._is_dark else "#4A5567"
        self.setLabel("bottom", label, color=text_c, size="9pt")

    def set_x_labels(self, x_to_label: dict) -> None:
        self._x_to_label = x_to_label

    # 호버
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
        best_x = None; best_d = float("inf")
        for c in self._curves:
            xd, _ = c.getData()
            if xd is None or len(xd) == 0:
                continue
            idx = int(np.argmin(np.abs(xd - x)))
            dist = abs(float(xd[idx]) - x)
            if dist < best_d:
                best_d = dist; best_x = float(xd[idx])
        return best_x

    def _update_tracker(self, x: float) -> None:
        nx = self._nearest_x(x)
        if nx is None:
            self._tracker.setData([]); return
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
        if nx is None: return ""
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
                    f"<b>{y:.3f}</b> USD/MMBtu"
                )
        return "<br>".join(lines) if len(lines) > 1 else ""

    def clear_curves(self) -> None:
        for c in self._curves:
            self.removeItem(c)
        self._curves.clear()
        self._curve_meta.clear()
        self._tracker.setData([])
        self._x_to_label = {}

    def add_curve(
        self, x, y, name: str, color: str,
        *, width: int = 2, fill: bool = False, dashed: bool = False,
    ) -> None:
        style = Qt.DashLine if dashed else Qt.SolidLine
        pen = pg.mkPen(color=color, width=width, style=style)
        if fill:
            c = QColor(color)
            valid_y = [v for v in y if not math.isnan(v)] if y else []
            base = (min(valid_y) - (max(valid_y) - min(valid_y)) * 0.05) if valid_y else 0
            curve = self.plot(
                x, y, pen=pen, name=name,
                fillLevel=base,
                brush=pg.mkBrush(c.red(), c.green(), c.blue(), 40),
            )
        else:
            curve = self.plot(x, y, pen=pen, name=name)
        self._curves.append(curve)
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
        if not all_x or not all_y: return
        x_min, x_max = min(all_x), max(all_x)
        y_min, y_max = min(all_y), max(all_y)
        x_span = (x_max - x_min) or 1.0
        y_span = (y_max - y_min) or 1.0
        self.plotItem.vb.setRange(
            xRange=(x_min - x_span * padding, x_max + x_span * padding),
            yRange=(y_min - y_span * padding, y_max + y_span * padding),
            padding=0,
        )


# ──────────────────────────────────────────────────────────────────────
# C. JkmWidget — 디테일 페이지
# ──────────────────────────────────────────────────────────────────────
class JkmWidget(BaseWidget):
    """エネルギー指標 디테일 — 지표 타일 + 활성 지표 차트 + KPI 6종 + MA."""

    def __init__(self):
        super().__init__()
        self._active_id = "jkm"   # 활성 지표 ID
        self._period = "90d"
        self._show_ma4  = False
        self._show_ma12 = False
        self._dates: list[str]   = []
        self._closes: list[float] = []
        self._highs: list[float]  = []
        self._lows: list[float]   = []
        self._worker: Optional[FetchEnergyIndicatorsWorker] = None
        # 지표별 메타 (config 기반 lookup)
        self._ind_by_id = {ind["id"]: ind for ind in ENERGY_INDICATORS}
        # 타일 위젯들
        self._tiles: dict[str, "_IndicatorTile"] = {}

        self._build_ui()

        # 1) 시작 시 구 jkm_prices → energy_prices 일회성 마이그레이션
        try:
            migrated = migrate_legacy_jkm()
            if migrated > 0:
                logger.info(f"JKM 데이터 {migrated} 행을 energy_prices 로 마이그레이션")
        except Exception as e:
            logger.warning(f"JKM migrate 실패 (무시): {e}")

        # 2) 첫 렌더 + 데이터 부재 시 자동 fetch 트리거
        QTimer.singleShot(2250, self._refresh_all)
        QTimer.singleShot(3000, self._auto_fetch_if_empty)

        # 3) 30 초 stagger 후 자동 갱신 타이머
        self.setup_timer(self.settings.get("jkm_interval", 180), self._on_fetch, stagger_seconds=30)

    def _auto_fetch_if_empty(self) -> None:
        """6 지표 중 단 하나라도 데이터 없으면 자동 fetch.
        (JKM 위젯 시작 시 새로 추가된 ticker 데이터 수집)."""
        for ind in ENERGY_INDICATORS:
            if not has_indicator_data(ind["id"]):
                logger.info(f"{ind['id']} 데이터 부재 → 자동 fetch 트리거")
                self._on_fetch()
                return

    # ──────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        # 페이지 ScrollArea 래핑
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        scroll = QScrollArea(self)
        scroll.setObjectName("jkmPageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer.addWidget(scroll, 1)

        content = QWidget()
        content.setObjectName("jkmPageContent")
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(16)

        # 1) DetailHeader
        self._header = LeeDetailHeader(
            title=tr("エネルギー指標"),
            subtitle=tr("LNG · 原油 · 為替 — Yahoo Finance 多銘柄"),
            accent=_C_JKM,
            icon_qicon=QIcon(":/img/fire.svg"),
            badge="",
            show_export=True,
        )
        self._header.back_clicked.connect(lambda: bus.page_requested.emit(0))
        self._header.export_clicked.connect(self._export_csv)
        root.addWidget(self._header)

        # 2) Indicator tile grid — 4 cols × 2 rows, click to switch active
        root.addWidget(self._build_indicator_grid())

        # 3) Filter row: Period segment + MA toggles + Update / Copy / CSV / View
        root.addWidget(self._build_filter_row())

        # 3) KPI strip (6 cards): 最新値 / 前日比 / 前週比 / 前月比 / MA 4w / MA 12w
        kpi_row = QHBoxLayout(); kpi_row.setSpacing(10)
        self._kpi_latest = LeeKPI(tr("最新値"), value="--", unit="USD/MMBtu", color=_C_JKM)
        self._kpi_dod    = LeeKPI(tr("前日比"), value="--", unit="%")
        self._kpi_wow    = LeeKPI(tr("前週比"), value="--", unit="%")
        self._kpi_mom    = LeeKPI(tr("前月比"), value="--", unit="%")
        self._kpi_ma4    = LeeKPI(tr("4w MA"),  value="--", unit="USD/MMBtu", color=_C_WARN)
        self._kpi_ma12   = LeeKPI(tr("12w MA"), value="--", unit="USD/MMBtu", color=_C_OK)
        for k in (self._kpi_latest, self._kpi_dod, self._kpi_wow, self._kpi_mom, self._kpi_ma4, self._kpi_ma12):
            kpi_row.addWidget(k, 1)
        root.addLayout(kpi_row)

        # 4) Chart frame
        self._chart = _JkmChart()
        self._chart.setMinimumHeight(360)
        self._chart_frame = LeeChartFrame(
            tr("JKM LNG 推移"),
            subtitle="",
            accent=_C_JKM,
        )
        self._chart_frame.set_content(self._chart)
        self._chart_frame.setMinimumHeight(420)
        root.addWidget(self._chart_frame)
        # 첫 fetch 동안 차트 영역에 shimmer skeleton
        from app.ui.components.skeleton import install_skeleton_overlay
        self._chart_skel = install_skeleton_overlay(self._chart)

        # 5) 진행 표시
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0); bottom.setSpacing(10)
        self._refresh_indicator = QLabel("")
        self._refresh_indicator.setObjectName("jkmRefreshIndicator")
        bottom.addWidget(self._refresh_indicator)
        self._status = QLabel(tr("待機中"))
        self._status.setObjectName("jkmStatusLbl")
        self._status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bottom.addStretch()
        bottom.addWidget(self._status)
        root.addLayout(bottom)

        self._update_refresh_indicator()

    def _build_indicator_grid(self) -> QWidget:
        wrap = QFrame(); wrap.setObjectName("jkmIndGrid")
        grid = QGridLayout(wrap)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        cols = 4
        # 모든 컬럼 동일 stretch — 타일 너비 일정하게 유지
        for c in range(cols):
            grid.setColumnStretch(c, 1)
        for i, ind in enumerate(ENERGY_INDICATORS):
            tile = _IndicatorTile(ind, is_dark=self.is_dark)
            tile.clicked.connect(lambda _id=ind["id"]: self._on_indicator_selected(_id))
            r, c = divmod(i, cols)
            grid.addWidget(tile, r, c)
            self._tiles[ind["id"]] = tile
        return wrap

    def _build_filter_row(self) -> QWidget:
        bar = QFrame(); bar.setObjectName("jkmFilterBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0); h.setSpacing(10)

        # Period segment
        self._seg = LeeSegment(_PERIODS, value=self._period, accent=_C_JKM)
        self._seg.value_changed.connect(self._on_period_changed)
        h.addWidget(self._seg)

        h.addWidget(self._make_sep())

        # MA 토글 버튼
        self._btn_ma4 = QPushButton(tr("MA 4w"))
        self._btn_ma4.setObjectName("jkmMaToggle")
        self._btn_ma4.setCheckable(True)
        self._btn_ma4.setChecked(self._show_ma4)
        self._btn_ma4.setCursor(Qt.PointingHandCursor)
        self._btn_ma4.setProperty("maColor", _C_WARN)
        self._btn_ma4.clicked.connect(lambda checked: self._on_ma_toggle("ma4", checked))

        self._btn_ma12 = QPushButton(tr("MA 12w"))
        self._btn_ma12.setObjectName("jkmMaToggle")
        self._btn_ma12.setCheckable(True)
        self._btn_ma12.setChecked(self._show_ma12)
        self._btn_ma12.setCursor(Qt.PointingHandCursor)
        self._btn_ma12.setProperty("maColor", _C_OK)
        self._btn_ma12.clicked.connect(lambda checked: self._on_ma_toggle("ma12", checked))

        h.addWidget(self._btn_ma4)
        h.addWidget(self._btn_ma12)

        h.addStretch()

        # 액션
        self._btn_fetch = LeeButton(tr("Yahoo 取込"), variant="secondary", size="sm")
        self._btn_fetch.clicked.connect(self._on_fetch)
        h.addWidget(self._btn_fetch)

        self._btn_copy = LeeButton(tr("📋 コピー"), variant="secondary", size="sm")
        self._btn_copy.clicked.connect(self._copy_data)
        h.addWidget(self._btn_copy)

        self._btn_csv = LeeButton(tr("⬇ CSV"), variant="secondary", size="sm")
        self._btn_csv.clicked.connect(self._export_csv)
        h.addWidget(self._btn_csv)

        self._btn_reset_view = LeeButton(tr("ビュー"), variant="ghost", size="sm")
        self._btn_reset_view.clicked.connect(lambda: self._chart.fit_view())
        h.addWidget(self._btn_reset_view)

        self._filter_bar = bar
        self._apply_filter_qss()
        return bar

    def _make_sep(self) -> QFrame:
        sep = QFrame(); sep.setObjectName("jkmFilterSep")
        sep.setFixedSize(1, 22)
        return sep

    def _update_refresh_indicator(self) -> None:
        interval = int(self.settings.get("jkm_interval", 180))
        self._refresh_indicator.setText(f"●  {interval}{tr('分ごと')}")

    # ──────────────────────────────────────────────────────────
    # 스타일
    # ──────────────────────────────────────────────────────────
    def _apply_page_qss(self) -> None:
        bg_app = "#0A0B0F" if self.is_dark else "#F5F6F8"
        self.setStyleSheet(f"""
            JkmWidget {{ background: {bg_app}; }}
            QScrollArea#jkmPageScroll {{ background: {bg_app}; border: none; }}
            QWidget#jkmPageContent {{ background: {bg_app}; }}
        """)

    def _apply_filter_qss(self) -> None:
        is_dark = self.is_dark
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        bg_surface_2 = "#1B1E26" if is_dark else "#F0F2F5"
        border       = "rgba(255,255,255,0.08)" if is_dark else "rgba(11,18,32,0.10)"
        sep_color    = "rgba(255,255,255,0.10)" if is_dark else "rgba(11,18,32,0.10)"

        # MA toggle 버튼 — 부모(카드 또는 페이지) 색 follow + border 만으로 경계
        from app.ui.theme import ThemeManager
        toggle_bg = ThemeManager.instance().tokens["bg_surface"]
        ma_qss = f"""
            QFrame#jkmFilterBar {{ background: transparent; }}
            QFrame#jkmFilterSep {{ background: {sep_color}; border: none; }}
            QPushButton#jkmMaToggle {{
                background: {toggle_bg};
                color: {fg_secondary};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 4px 12px;
                font-size: 11px; font-weight: 700;
                min-height: 22px;
            }}
            QPushButton#jkmMaToggle[maColor="{_C_WARN}"]:checked {{
                background: rgba(255,159,10,0.14);
                color: {_C_WARN};
                border: 1px solid {_C_WARN};
            }}
            QPushButton#jkmMaToggle[maColor="{_C_OK}"]:checked {{
                background: rgba(48,209,88,0.14);
                color: {_C_OK};
                border: 1px solid {_C_OK};
            }}
            QLabel#jkmRefreshIndicator {{
                font-size: 11px; font-weight: 600;
                color: {_C_OK};
                background: rgba(48,209,88,0.10);
                border: 1px solid rgba(48,209,88,0.25);
                border-radius: 999px;
                padding: 3px 10px;
            }}
            QLabel#jkmStatusLbl {{
                font-size: 11px; color: {fg_secondary};
                background: transparent; min-width: 60px;
            }}
        """
        self._filter_bar.setStyleSheet(ma_qss)

    # ──────────────────────────────────────────────────────────
    # BaseWidget hooks
    # ──────────────────────────────────────────────────────────
    def apply_theme_custom(self) -> None:
        d = self.is_dark
        self._header.set_theme(d)
        for k in (self._kpi_latest, self._kpi_dod, self._kpi_wow, self._kpi_mom, self._kpi_ma4, self._kpi_ma12):
            k.set_theme(d)
        # 6 개 지표 타일 (JKM/Henry Hub/Brent/WTI/USD-JPY/EUR-JPY) — 누락 시
        # 내부 sparkline 의 viewport bg 가 다크 그대로 유지되어 라이트모드에서 어색
        for tile in self._tiles.values():
            tile.set_theme(d)
        self._seg.set_theme(d)
        self._chart_frame.set_theme(d)
        self._chart.set_theme(d)
        self._apply_page_qss()
        self._apply_filter_qss()

    def apply_settings_custom(self) -> None:
        interval = int(self.settings.get("jkm_interval", 180))
        self.update_timer_interval(interval)
        self._update_refresh_indicator()

    def set_loading(self, is_loading: bool) -> None:
        super().set_loading(is_loading, self._chart_frame)

    # ──────────────────────────────────────────────────────────
    # 컨트롤
    # ──────────────────────────────────────────────────────────
    def _on_period_changed(self, key: str) -> None:
        self._period = key
        self._refresh_chart()

    def _on_ma_toggle(self, kind: str, checked: bool) -> None:
        if kind == "ma4":
            self._show_ma4 = checked
        else:
            self._show_ma12 = checked
        self._render_chart()

    def _on_indicator_selected(self, indicator_id: str) -> None:
        """지표 타일 클릭 — 활성 지표 변경 + 차트/KPI 재로드."""
        if indicator_id == self._active_id:
            return
        self._active_id = indicator_id
        # 타일 활성 상태 업데이트
        for _id, tile in self._tiles.items():
            tile.set_active(_id == indicator_id)
        # 액센트 컬러 갱신 (header / chart)
        ind = self._ind_by_id.get(indicator_id)
        if ind:
            self._header.set_accent(ind["color"])
        self._refresh_chart()

    # ──────────────────────────────────────────────────────────
    # 데이터 fetch (Yahoo Finance multi-ticker)
    # ──────────────────────────────────────────────────────────
    def _on_fetch(self) -> None:
        if not self.check_online_status(): return
        try:
            if self._worker and self._worker.isRunning():
                return
        except RuntimeError:
            self._worker = None
        self._btn_fetch.setEnabled(False)
        self._set_status(tr("全銘柄データ取得中..."))
        if getattr(self, "_chart_skel", None) is not None:
            self._chart_skel.start()
        self._worker = FetchEnergyIndicatorsWorker()
        self._worker.progress.connect(self._set_status)
        self._worker.finished.connect(self._on_fetch_done)
        self._worker.error.connect(self._on_fetch_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()
        self.track_worker(self._worker)

    def _on_fetch_done(self, results: dict) -> None:
        self._btn_fetch.setEnabled(True)
        success = sum(1 for v in results.values() if v > 0)
        total = len(results)
        self._set_status(tr("取得完了: {0}/{1} 銘柄").format(success, total))
        # JKM 데이터 변경 → 대시보드 카드 동기화
        if results.get("jkm", 0) > 0:
            bus.jkm_updated.emit()
        self._refresh_all()

    def _on_fetch_error(self, err: str) -> None:
        self._btn_fetch.setEnabled(True)
        self._set_status(tr("取得失敗: {0}").format(err))
        bus.toast_requested.emit(tr("⚠ エネルギー指標 取得失敗"), "error")

    # ──────────────────────────────────────────────────────────
    # DB 로드 + 렌더링
    # ──────────────────────────────────────────────────────────
    def _refresh_all(self) -> None:
        """타일 그리드 + 활성 지표 차트 모두 갱신."""
        self._refresh_tiles()
        self._refresh_chart()

    def _refresh_tiles(self) -> None:
        """모든 타일에 30일 데이터 채우기 (mini sparkline + last/dod)."""
        for ind in ENERGY_INDICATORS:
            ind_id = ind["id"]
            rows = query_indicator(ind_id, limit=30)
            # JKM 의 경우 신규 DB 비어있으면 구 jkm_prices fallback
            if not rows and ind_id == "jkm":
                rows = self._load_legacy_jkm(limit=30)
            tile = self._tiles.get(ind_id)
            if tile is None:
                continue
            if not rows:
                tile.set_no_data()
                continue
            closes = [float(r[1]) for r in rows]
            last = closes[-1]
            prev = closes[-2] if len(closes) >= 2 else None
            dod = ((last - prev) / prev * 100) if prev else None
            tile.set_data(value=last, dod_pct=dod, sparkline=closes)

    def _refresh_chart(self) -> None:
        """활성 지표의 시계열을 로드 → 차트/KPI 렌더링."""
        days = _PERIOD_DAYS.get(self._period, 90)
        rows = query_indicator(self._active_id, limit=(days if days > 0 else None))
        # JKM 신규 DB 비어있으면 구 jkm_prices 로 fallback
        if not rows and self._active_id == "jkm":
            rows = self._load_legacy_jkm(limit=(days if days > 0 else None))

        if not rows:
            self._dates = []; self._closes = []
            self._highs = []; self._lows = []
            self._chart.clear_curves()
            self._update_kpis_empty()
            self._chart_frame.set_subtitle("")
            self._header.set_badge(None)
            self._set_status(
                tr("DBにデータがありません。「Yahoo 取込」で取得してください。")
            )
            return

        self._dates  = [r[0] for r in rows]
        self._closes = [float(r[1]) for r in rows]
        self._highs  = [r[2] for r in rows]
        self._lows   = [r[3] for r in rows]

        self._render_all()
        ind = self._ind_by_id.get(self._active_id, {})
        unit = ind.get("unit", "")
        period_label = next((l for k, l in _PERIODS if k == self._period), self._period)
        self._set_status(
            tr("{0} · {1}: {2}件  最新: {3:.3f} {4}  ({5})").format(
                ind.get("label", self._active_id), period_label,
                len(rows), self._closes[-1], unit, self._dates[-1],
            )
        )

    def _load_legacy_jkm(self, *, limit: Optional[int]) -> list[tuple]:
        """구 jkm_prices 테이블 fallback (신규 DB 마이그레이션 전)."""
        try:
            with get_db_connection(DB_JKM) as conn:
                if limit and limit > 0:
                    rows = conn.execute(
                        "SELECT date, close, high, low FROM jkm_prices "
                        "ORDER BY date DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                    return list(reversed(rows))
                return conn.execute(
                    "SELECT date, close, high, low FROM jkm_prices ORDER BY date"
                ).fetchall()
        except sqlite3.Error as e:
            logger.warning(f"legacy jkm_prices 쿼리 실패: {e}")
            return []

    def _render_all(self) -> None:
        self._render_chart()
        self._update_kpis()
        ind = self._ind_by_id.get(self._active_id, {})
        period_label = next((l for k, l in _PERIODS if k == self._period), self._period)
        self._chart_frame.set_subtitle(
            f"{ind.get('label', self._active_id)} · {period_label} · {len(self._dates)} {tr('ポイント')}"
        )
        self._chart_frame.set_title(tr("{0} 推移").format(ind.get("label", "")))
        # Header badge — 최신 값 + 단위
        if self._closes:
            self._header.set_badge(f"{ind.get('label','')} {self._closes[-1]:.2f}")

    def _render_chart(self) -> None:
        self._chart.clear_curves()
        if not self._dates or not self._closes:
            return
        # 데이터 도착 시 skeleton 숨기기 (재사용 가능 — refresh 시 다시 .start())
        if getattr(self, "_chart_skel", None) is not None:
            self._chart_skel.stop()

        x_vals = list(range(len(self._dates)))
        n = len(self._dates)
        target_ticks = 8
        step = max(1, n // target_ticks)
        ticks = [(i, self._dates[i]) for i in range(0, n, step)]
        if ticks and ticks[-1][0] != n - 1:
            ticks.append((n - 1, self._dates[-1]))
        self._chart.getAxis("bottom").setTicks([ticks])
        self._chart.set_x_label(tr("日付"))
        self._chart.set_x_labels({float(i): self._dates[i] for i in range(n)})

        # Y축 단위 + 라인 컬러는 활성 지표 기반
        ind = self._ind_by_id.get(self._active_id, {})
        line_color = ind.get("color", _C_JKM)
        unit = ind.get("unit", "")
        text_c = "#A8B0BD" if self.is_dark else "#4A5567"
        self._chart.setLabel("left", unit, color=text_c, size="9pt")

        # Close 라인 (메인)
        self._chart.add_curve(x_vals, self._closes, name=ind.get("label", tr("Close")),
                              color=line_color, width=2, fill=True)

        # MA 4w
        if self._show_ma4:
            ma4 = self._moving_avg(self._closes, _MA_4W)
            self._chart.add_curve(x_vals, ma4, name=tr("MA 4w"), color=_C_WARN, width=1, dashed=True)

        # MA 12w
        if self._show_ma12:
            ma12 = self._moving_avg(self._closes, _MA_12W)
            self._chart.add_curve(x_vals, ma12, name=tr("MA 12w"), color=_C_OK, width=1, dashed=True)

        self._chart.fit_view()

    @staticmethod
    def _moving_avg(values: list[float], window: int) -> list[float]:
        """단순 이동평균 (NaN padding for early values)."""
        out = []
        for i in range(len(values)):
            if i + 1 < window:
                out.append(float("nan"))
            else:
                seg = values[i + 1 - window: i + 1]
                out.append(sum(seg) / len(seg))
        return out

    def _update_kpis(self) -> None:
        if not self._closes:
            self._update_kpis_empty(); return

        ind = self._ind_by_id.get(self._active_id, {})
        unit = ind.get("unit", "")
        ind_color = ind.get("color", _C_JKM)

        latest = self._closes[-1]

        def _pct(curr: float, base: Optional[float]) -> Optional[float]:
            if base is None or base == 0:
                return None
            return (curr - base) / base * 100.0

        prev_d  = self._closes[-2]   if len(self._closes) >= 2  else None
        prev_w  = self._closes[-6]   if len(self._closes) >= 6  else None
        prev_m  = self._closes[-21]  if len(self._closes) >= 21 else None

        dod = _pct(latest, prev_d)
        wow = _pct(latest, prev_w)
        mom = _pct(latest, prev_m)

        self._kpi_latest.set_value(
            f"{latest:.3f}", unit=unit, color=ind_color,
            sub=str(self._dates[-1]),
        )
        for kpi, pct in ((self._kpi_dod, dod), (self._kpi_wow, wow), (self._kpi_mom, mom)):
            txt = "--" if pct is None else f"{('+' if pct >= 0 else '')}{pct:.2f}"
            kpi.set_value(txt, unit="%", color=self._color_for_pct(pct))

        ma4_vals  = self._moving_avg(self._closes, _MA_4W)
        ma12_vals = self._moving_avg(self._closes, _MA_12W)
        ma4_last  = next((v for v in reversed(ma4_vals) if not math.isnan(v)), None)
        ma12_last = next((v for v in reversed(ma12_vals) if not math.isnan(v)), None)
        self._kpi_ma4.set_value(
            f"{ma4_last:.3f}" if ma4_last is not None else "--",
            unit=unit, color=_C_WARN, sub=tr("過去4週平均"),
        )
        self._kpi_ma12.set_value(
            f"{ma12_last:.3f}" if ma12_last is not None else "--",
            unit=unit, color=_C_OK, sub=tr("過去12週平均"),
        )

    def _update_kpis_empty(self) -> None:
        for k in (self._kpi_latest, self._kpi_dod, self._kpi_wow,
                  self._kpi_mom, self._kpi_ma4, self._kpi_ma12):
            k.set_value("--", unit="", sub="")

    @staticmethod
    def _color_for_pct(pct: Optional[float]) -> str:
        if pct is None:
            return _C_JKM
        if pct > 0:
            return _C_BAD   # 가격 ↑ = 빨강
        if pct < 0:
            return _C_OK    # 가격 ↓ = 초록
        return _C_JKM

    # ──────────────────────────────────────────────────────────
    # CSV / Copy
    # ──────────────────────────────────────────────────────────
    def _copy_data(self) -> None:
        if not self._dates:
            bus.toast_requested.emit(tr("コピー可能なデータがありません"), "warning")
            return
        lines = ["\t".join([tr("日付"), tr("終値"), tr("高値"), tr("安値")])]
        for i, d in enumerate(self._dates):
            c = self._closes[i] if i < len(self._closes) else None
            h = self._highs[i]  if i < len(self._highs)  else None
            l = self._lows[i]   if i < len(self._lows)   else None
            lines.append("\t".join([
                str(d),
                f"{c:.3f}" if c is not None else "",
                f"{h:.3f}" if h is not None else "",
                f"{l:.3f}" if l is not None else "",
            ]))
        QApplication.clipboard().setText("\n".join(lines))
        bus.toast_requested.emit(tr("テーブルをコピーしました"), "success")

    def _export_csv(self) -> None:
        if not self._dates:
            LeeDialog.error(tr("エラー"), tr("保存するデータがありません。"), parent=self)
            return
        suffix = self._period
        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("CSV保存"), f"jkm_{suffix}.csv", "CSV Files (*.csv)",
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["date", "close", "high", "low"])
                for i, d in enumerate(self._dates):
                    writer.writerow([
                        d,
                        f"{self._closes[i]:.3f}" if i < len(self._closes) and self._closes[i] is not None else "",
                        f"{self._highs[i]:.3f}"  if i < len(self._highs)  and self._highs[i]  is not None else "",
                        f"{self._lows[i]:.3f}"   if i < len(self._lows)   and self._lows[i]   is not None else "",
                    ])
            LeeDialog.info(
                tr("完了"),
                tr("CSVファイルとして保存しました。\nExcelで開くことができます。"),
                parent=self,
            )
        except (IOError, csv.Error) as e:
            LeeDialog.error(tr("エラー"), tr("保存に失敗しました:\n{0}").format(e), parent=self)

    # ──────────────────────────────────────────────────────────
    # 상태
    # ──────────────────────────────────────────────────────────
    def _set_status(self, msg: str) -> None:
        self._status.setText(msg)


# ──────────────────────────────────────────────────────────────────────
# D. _IndicatorTile — 디테일 페이지 상단 지표 타일 (4×2 그리드)
# ──────────────────────────────────────────────────────────────────────
class _IndicatorTile(QFrame):
    """단일 지표 타일 — label, last value, dod%, mini sparkline. 클릭 시 활성화.

    레이아웃:
        ┌─────────────────────────┐
        │ JKM (LNG)        ▲ 1.2% │
        │ 14.32 USD/MMBtu         │
        │ ╱╲╱╲ (mini sparkline)   │
        └─────────────────────────┘
    """

    clicked = Signal()

    def __init__(self, indicator: dict, *, is_dark: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("jkmIndTile")
        self._indicator = indicator
        self._is_dark = is_dark
        self._active = (indicator.get("id") == "jkm")  # JKM 기본 활성
        self.setCursor(Qt.PointingHandCursor)
        # 크기 고정 — 활성/비활성 전환 시 sizeHint 변동 방지 (타일 점프/리사이즈 방지)
        self.setFixedHeight(108)
        from PySide6.QtWidgets import QSizePolicy as _QSP
        self.setSizePolicy(_QSP.Expanding, _QSP.Fixed)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # 헤더: 라벨 + dod %
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0); head.setSpacing(6)
        self._label_lbl = QLabel(tr(indicator.get("label", "")))
        self._label_lbl.setObjectName("indTileLabel")
        head.addWidget(self._label_lbl, 1)
        self._dod_lbl = QLabel("")
        self._dod_lbl.setObjectName("indTileDod")
        head.addWidget(self._dod_lbl, 0, Qt.AlignRight)
        layout.addLayout(head)

        # 큰 숫자 + 단위
        num_row = QHBoxLayout()
        num_row.setContentsMargins(0, 0, 0, 0); num_row.setSpacing(4)
        num_row.setAlignment(Qt.AlignBaseline)
        self._value_lbl = QLabel("--")
        self._value_lbl.setObjectName("indTileValue")
        self._unit_lbl = QLabel(tr(indicator.get("unit", "")))
        self._unit_lbl.setObjectName("indTileUnit")
        num_row.addWidget(self._value_lbl, 0, Qt.AlignBaseline)
        num_row.addWidget(self._unit_lbl, 0, Qt.AlignBaseline)
        num_row.addStretch()
        layout.addLayout(num_row)

        # mini sparkline
        self._spark = LeeSparkline(indicator.get("color", "#F4B740"), height=28, fill_alpha=60)
        layout.addWidget(self._spark)

        self._apply_qss()

    def set_data(self, *, value: float, dod_pct: Optional[float], sparkline: list[float]) -> None:
        self._value_lbl.setText(f"{value:.2f}" if value is not None else "--")
        if dod_pct is None or abs(dod_pct) < 0.01:
            self._dod_lbl.setText("")
        else:
            arrow = "▲" if dod_pct > 0 else "▼"
            color = _C_BAD if dod_pct > 0 else _C_OK
            self._dod_lbl.setStyleSheet(
                f"color: {color}; font-size: 10px; font-weight: 700; background: transparent;"
            )
            self._dod_lbl.setText(f"{arrow} {abs(dod_pct):.2f}%")
        self._spark.set_data(sparkline or [])

    def set_no_data(self) -> None:
        self._value_lbl.setText("--")
        self._dod_lbl.setText("")
        self._spark.set_data([])

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self._apply_qss()
        # 강제 재스타일 — sizeHint 변동 없이 색깔만 즉시 반영
        self.style().unpolish(self); self.style().polish(self)

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        bg_surface = "#14161C" if is_dark else "#FFFFFF"
        self._spark.set_card_bg(bg_surface)
        self._apply_qss()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        color = self._indicator.get("color", "#F4B740")
        bg_surface   = "#14161C" if is_dark else "#FFFFFF"
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        border_subtle = "rgba(255,255,255,0.06)" if is_dark else "rgba(11,18,32,0.06)"

        if self._active:
            border = color
            r, g, b = self._hex_to_rgb(color)
            bg = f"rgba({r},{g},{b},0.10)"
        else:
            border = border_subtle
            bg = bg_surface

        self.setStyleSheet(f"""
            QFrame#jkmIndTile {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 14px;
            }}
            QFrame#jkmIndTile:hover {{
                border: 1px solid {color};
            }}
            QLabel#indTileLabel {{
                font-size: 11px; font-weight: 600;
                color: {fg_secondary}; background: transparent;
            }}
            QLabel#indTileDod {{
                font-size: 10px; font-weight: 700;
                background: transparent;
            }}
            QLabel#indTileValue {{
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 18px; font-weight: 800;
                color: {fg_primary}; background: transparent;
            }}
            QLabel#indTileUnit {{
                font-size: 10px; color: {fg_tertiary};
                background: transparent;
            }}
        """)

    @staticmethod
    def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
        h = hex_str.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
