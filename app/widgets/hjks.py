"""HJKS 発電稼働状況 ウィジェット — Phase 5.6 リニューアル.

데이터 소스: JEPX HJKS (発電所運用情報公表システム) 14日分

디자인 출처: handoff/LEE_PROJECT/varA-detail-screens4.jsx HjksDetail
            handoff/LEE_PROJECT/varA-cards.jsx HjksCard

[Card]
    HjksCard (대시보드)
        - LeeCard accent="hjks" (#A78BFA)
        - 本日の発電稼働容量 大きな数値 (GW)
        - 発電方式別 multi-color プログレスバー
        - 6 chip legend (方式 + MW)
        - 7 日 sparkline (合計 op MW 推移)

[Detail page]
    HjksWidget
        - DetailHeader (← back, plant icon, badge)
        - 4 KPI strip: 期間平均, ピーク, ボトム, 再エネ比率
        - Filter row: DateRange (start + end + 7/14 quick), region chips, method chips
        - LeeChartFrame: 期間内 日次出力 (stacked bar by method)
        - Region bars + Method donut (2 column)
        - 停止中設備 listing (DB stopped_kw > 0)
"""
from __future__ import annotations

import logging
import math
import sqlite3
from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import (
    Qt, QDate, QObject, QPoint, QRect, QSize, QThread, QTimer, Signal,
)
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QToolTip, QVBoxLayout, QWidget,
)

from app.api.market.hjks import FetchHjksWorker
from app.core.config import DB_HJKS, HJKS_COLORS, HJKS_METHODS, HJKS_REGIONS
from app.core.database import get_db_connection
from app.core.events import bus
from app.core.i18n import tr
from app.ui.common import BaseWidget
from app.ui.components import (
    LeeButton, LeeCard, LeeChartFrame, LeeCountValue, LeeDateInput,
    LeeDetailHeader, LeeDialog, LeeIconTile, LeeKPI, LeeSparkline,
)

pg.setConfigOptions(antialias=True)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 토큰
# ──────────────────────────────────────────────────────────────────────
_C_HJKS = "#A78BFA"   # --c-hjks (퍼플)
_C_OK   = "#30D158"
_C_INFO = "#5B8DEF"
_C_WARN = "#FF9F0A"
_C_BAD  = "#FF453A"

# 재생에너지 - 우리 DB methods 상 "水力" + "その他" 일부 (태양광/풍력은 その他에 포함)
_RENEWABLE_METHODS = {"水力", "その他"}


# ──────────────────────────────────────────────────────────────────────
# A. HjksCard — 대시보드 카드
# ──────────────────────────────────────────────────────────────────────
class HjksCard(LeeCard):
    """HJKS 카드 — 모킹업 HjksCard 1:1.

    레이아웃:
        ┌─────────────────────────────────────────────────────┐
        │ [icon] 本日の発電稼働容量                            │
        │        HJKS · 全国合計                               │
        │                                                      │
        │ 142.3 GW                                             │
        │ 2026-05-02                                           │
        │                                                      │
        │ ███▓▓▓░░░ (multi-color stacked bar)                  │
        │                                                      │
        │ ■ 火力(石炭)  ■ 火力(ガス)  ■ 火力(石油)             │
        │ ■ 原子力      ■ 水力        ■ その他                 │
        └─────────────────────────────────────────────────────┘
    """

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(accent_color="hjks", interactive=True, parent=parent)
        self.setMinimumHeight(220)
        self._is_dark = True
        self._last_payload: Optional[dict] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(0)

        # 헤더
        header = QHBoxLayout(); header.setSpacing(12); header.setContentsMargins(0, 0, 0, 12)
        self._icon = LeeIconTile(
            icon=QIcon(":/img/plant.svg"),
            color=_C_HJKS, size=40, radius=12,
        )
        header.addWidget(self._icon, 0, Qt.AlignTop)

        title_box = QVBoxLayout(); title_box.setSpacing(2); title_box.setContentsMargins(0, 0, 0, 0)
        self._title_lbl = QLabel(tr("本日の発電稼働容量"))
        self._title_lbl.setObjectName("hjksCardTitle")
        self._sub_lbl = QLabel(tr("HJKS · 全国合計"))
        self._sub_lbl.setObjectName("hjksCardSub")
        title_box.addWidget(self._title_lbl)
        title_box.addWidget(self._sub_lbl)
        header.addLayout(title_box, 1)

        layout.addLayout(header)

        # 큰 숫자 + 단위
        num_row = QHBoxLayout(); num_row.setSpacing(4)
        num_row.setContentsMargins(0, 0, 0, 2); num_row.setAlignment(Qt.AlignBaseline)
        self._value_lbl = LeeCountValue(formatter=lambda v: f"{v:.1f}")
        self._value_lbl.setObjectName("hjksCardValue")
        self._unit_lbl = QLabel("GW")
        self._unit_lbl.setObjectName("hjksCardUnit")
        num_row.addWidget(self._value_lbl, 0, Qt.AlignBaseline)
        num_row.addWidget(self._unit_lbl,  0, Qt.AlignBaseline)
        num_row.addStretch()
        layout.addLayout(num_row)

        self._date_lbl = QLabel("")
        self._date_lbl.setObjectName("hjksCardDate")
        layout.addWidget(self._date_lbl)

        # Multi-color 스택 바
        self._stack_bar = _MethodStackBar(height=10)
        layout.addSpacing(10)
        layout.addWidget(self._stack_bar)

        # Legend grid (3 cols × 2 rows)
        self._legend_wrap = QWidget()
        legend_layout = QGridLayout(self._legend_wrap)
        legend_layout.setContentsMargins(0, 8, 0, 0)
        legend_layout.setHorizontalSpacing(10)
        legend_layout.setVerticalSpacing(4)
        self._legend_chips: dict[str, _LegendChip] = {}
        for i, m in enumerate(HJKS_METHODS):
            chip = _LegendChip(m, HJKS_COLORS.get(m, "#9E9E9E"))
            r, c = divmod(i, 3)
            legend_layout.addWidget(chip, r, c)
            self._legend_chips[m] = chip
        layout.addWidget(self._legend_wrap)

        # 데이터 없을 때
        self._note = QLabel(tr("データなし"))
        self._note.setObjectName("hjksCardNote")
        self._note.setAlignment(Qt.AlignCenter)
        self._note.setMinimumHeight(48)
        layout.addWidget(self._note)
        self._note.setVisible(False)   # setVisible 은 layout 추가 후 (top-level 깜빡임 방지)

        layout.addStretch()
        self._apply_local_qss()
        self.set_no_data()

    # ── 외부 API ─────────────────────────────────────────────
    def set_payload(self, payload: dict) -> None:
        total = payload.get("total_op_mw")
        methods = payload.get("methods") or []
        if total is None or total <= 0:
            self.set_no_data(); return
        self._last_payload = payload

        self._value_lbl.set_value(float(total) / 1000.0)  # MW → GW
        self._date_lbl.setText(str(payload.get("date", "")))

        # Stack bar
        # methods: [{name, op_mw, color}, ...]
        bar_data = [(m["name"], float(m["op_mw"]), m.get("color", "#9E9E9E")) for m in methods]
        self._stack_bar.set_segments(bar_data)

        # Legend update — 값 표시
        active = {m["name"] for m in methods}
        for m, chip in self._legend_chips.items():
            seg = next((x for x in methods if x["name"] == m), None)
            if seg:
                chip.set_value(float(seg["op_mw"]) / 1000.0)
                chip.set_dim(False)
            else:
                chip.set_value(None)
                chip.set_dim(True)

        self._stack_bar.setVisible(True)
        self._legend_wrap.setVisible(True)
        self._note.setVisible(False)

    def set_no_data(self) -> None:
        self._last_payload = None
        self._value_lbl.set_value(0.0, animate=False)
        self._value_lbl.setText("--")
        self._date_lbl.setText(tr("データなし"))
        self._stack_bar.set_segments([])
        for chip in self._legend_chips.values():
            chip.set_value(None)
            chip.set_dim(True)
        self._stack_bar.setVisible(False)
        self._legend_wrap.setVisible(False)
        self._note.setVisible(True)
        self._note.setText(tr("データなし"))

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._stack_bar.set_theme(is_dark)
        for chip in self._legend_chips.values():
            chip.set_theme(is_dark)
        self._apply_local_qss()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def _apply_local_qss(self) -> None:
        is_dark = self._is_dark
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        self.setStyleSheet(f"""
            QLabel#hjksCardTitle {{
                font-size: 13px; font-weight: 600;
                color: {fg_secondary}; background: transparent;
            }}
            QLabel#hjksCardSub {{
                font-size: 11px; color: {fg_tertiary};
                background: transparent;
            }}
            QLabel#hjksCardValue {{
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 32px; font-weight: 800;
                color: {_C_HJKS}; background: transparent;
                letter-spacing: -0.02em;
            }}
            QLabel#hjksCardUnit {{
                font-size: 12px; font-weight: 600;
                color: {fg_tertiary}; background: transparent;
                padding-bottom: 4px;
            }}
            QLabel#hjksCardDate {{
                font-size: 11px; color: {fg_secondary};
                background: transparent;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QLabel#hjksCardNote {{
                font-size: 11px; font-weight: 500;
                color: {fg_tertiary}; background: transparent;
                font-style: italic;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# A1. _MethodStackBar — 발전 방식별 multi-color 스택 바 (카드용)
# ──────────────────────────────────────────────────────────────────────
class _MethodStackBar(QWidget):
    """Multi-color horizontal stacked bar — methods 비율로 컬러 채우기.

    QPainter 직접 그리기 (raised pill 모양).
    """

    def __init__(self, *, height: int = 10, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._segments: list[tuple[str, float, str]] = []   # (name, value, color)
        self._is_dark = True

    def set_segments(self, segments: list) -> None:
        self._segments = list(segments) if segments else []
        self.update()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self.update()

    def paintEvent(self, _evt) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        radius = rect.height() / 2.0

        # 배경 (track)
        track = QColor("#1B1E26") if self._is_dark else QColor("#F0F2F5")
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(rect, radius, radius)

        if not self._segments:
            return

        total = sum(v for _, v, _ in self._segments) or 1.0
        x = float(rect.x())
        y = float(rect.y())
        w = float(rect.width())
        h = float(rect.height())
        # 첫 / 마지막 세그먼트만 라운드 처리
        last_idx = len(self._segments) - 1
        for i, (_, v, col) in enumerate(self._segments):
            if v <= 0: continue
            seg_w = (v / total) * w
            seg_rect = QRect(int(x), int(y), int(round(seg_w)), int(h))
            # 안쪽 세그먼트는 사각, 양 끝만 둥글게 (clipping 없이 단순 라운드)
            p.setBrush(QColor(col))
            if i == 0 or i == last_idx:
                p.drawRoundedRect(seg_rect, radius, radius)
            else:
                p.drawRect(seg_rect)
            x += seg_w


# ──────────────────────────────────────────────────────────────────────
# A2. _LegendChip — 카드 legend 칩
# ──────────────────────────────────────────────────────────────────────
class _LegendChip(QFrame):
    """카드 하단 발전방식 chip — 색상 도트 + 라벨 + GW 값."""

    def __init__(self, name: str, color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("hjksLegendChip")
        self._is_dark = True
        self._color = color
        self._dim = False
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0); h.setSpacing(6)

        self._dot = QLabel("●")
        self._dot.setObjectName("hjksLegendDot")
        self._dot.setFixedWidth(8)
        h.addWidget(self._dot)

        self._lbl = QLabel(tr(name))
        self._lbl.setObjectName("hjksLegendLabel")
        h.addWidget(self._lbl, 1)

        self._val = QLabel("--")
        self._val.setObjectName("hjksLegendVal")
        self._val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        h.addWidget(self._val, 0)

        self._apply_qss()

    def set_value(self, gw: Optional[float]) -> None:
        if gw is None:
            self._val.setText("--")
        else:
            self._val.setText(f"{gw:.1f}")

    def set_dim(self, dim: bool) -> None:
        self._dim = dim
        self._apply_qss()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        opa = "0.4" if self._dim else "1.0"
        self.setStyleSheet(f"""
            QFrame#hjksLegendChip {{ background: transparent; }}
            QLabel#hjksLegendDot {{
                color: {self._color}; background: transparent;
                font-size: 10px;
            }}
            QLabel#hjksLegendLabel {{
                color: {fg_secondary}; background: transparent;
                font-size: 10px; font-weight: 600;
            }}
            QLabel#hjksLegendVal {{
                color: {fg_primary}; background: transparent;
                font-size: 10px; font-weight: 700;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
        """)
        # opacity through stylesheet: not supported on QFrame easily — use widget opacity
        try:
            from PySide6.QtWidgets import QGraphicsOpacityEffect
            eff = self.graphicsEffect()
            if not isinstance(eff, QGraphicsOpacityEffect):
                eff = QGraphicsOpacityEffect(self); self.setGraphicsEffect(eff)
            eff.setOpacity(0.4 if self._dim else 1.0)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────
# B. _HjksRangeAggregateTask — 디테일 페이지 background DB 집계
# ──────────────────────────────────────────────────────────────────────
class _HjksRangeAggregateTask(QObject):
    """선택 기간 [start, end] 의 일별 region/method 합계를 background 에서 집계.

    emit: (rows: list[dict])
        각 dict = {
            'date': 'YYYY-MM-DD',
            'methods': {method: op_mw, ...},
            'regions': {region: op_mw, ...},
            'total_op_mw': float,
            'total_st_mw': float,
        }
    """

    finished = Signal(list)

    def __init__(self, start_iso: str, end_iso: str):
        super().__init__()
        self._start = start_iso
        self._end   = end_iso

    def run(self) -> None:
        rows: list[dict] = []
        try:
            with get_db_connection(DB_HJKS) as conn:
                raw = conn.execute(
                    "SELECT date, region, method, "
                    "       SUM(operating_kw), SUM(stopped_kw) "
                    "FROM hjks_capacity "
                    "WHERE date BETWEEN ? AND ? "
                    "GROUP BY date, region, method "
                    "ORDER BY date",
                    (self._start, self._end),
                ).fetchall()
        except sqlite3.Error as e:
            logger.warning(f"HJKS range query 失敗: {e}")
            self.finished.emit([])
            return

        if not raw:
            self.finished.emit([])
            return

        # 날짜별 집계
        by_date: dict[str, dict] = {}
        for d, r, m, op, st in raw:
            entry = by_date.setdefault(d, {
                "date": d,
                "methods": {x: 0.0 for x in HJKS_METHODS},
                "regions": {x: 0.0 for x in HJKS_REGIONS},
                "regions_st": {x: 0.0 for x in HJKS_REGIONS},
                "total_op_mw": 0.0,
                "total_st_mw": 0.0,
            })
            op_mw = float(op or 0.0) / 1000.0
            st_mw = float(st or 0.0) / 1000.0
            if m in entry["methods"]:
                entry["methods"][m] += op_mw
            if r in entry["regions"]:
                entry["regions"][r] += op_mw
                entry["regions_st"][r] += st_mw
            entry["total_op_mw"] += op_mw
            entry["total_st_mw"] += st_mw

        rows = [by_date[d] for d in sorted(by_date.keys())]
        self.finished.emit(rows)


class _HjksStoppedTask(QObject):
    """停止中 (stopped_kw > 0) 의 본일 (또는 end_iso) 데이터 조회.

    emit: list[dict] — [{region, method, stopped_mw, color}, ...]
    """

    finished = Signal(list)

    def __init__(self, on_date: str, top_n: int = 10):
        super().__init__()
        self._date = on_date
        self._top_n = top_n

    def run(self) -> None:
        results = []
        try:
            with get_db_connection(DB_HJKS) as conn:
                rows = conn.execute(
                    "SELECT region, method, stopped_kw FROM hjks_capacity "
                    "WHERE date = ? AND stopped_kw > 0 "
                    "ORDER BY stopped_kw DESC LIMIT ?",
                    (self._date, self._top_n),
                ).fetchall()
        except sqlite3.Error as e:
            logger.warning(f"HJKS 停止クエリ 失敗: {e}")
            self.finished.emit([])
            return
        for r, m, st in rows:
            results.append({
                "region": r,
                "method": m,
                "stopped_mw": float(st or 0.0) / 1000.0,
                "color": HJKS_COLORS.get(m, "#9E9E9E"),
            })
        self.finished.emit(results)


# ──────────────────────────────────────────────────────────────────────
# C. _StackedBarChart — 디테일 페이지 일별 stacked bar
# ──────────────────────────────────────────────────────────────────────
class _StackedBarChart(pg.PlotWidget):
    """일별 stacked bar (방식별 색상 누적) + 호버 툴팁."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark = True
        self._dates: list[str] = []
        self._rows:  list[dict] = []
        self._sel_methods: list[str] = list(HJKS_METHODS)
        self._sel_regions: list[str] = list(HJKS_REGIONS)
        self._hover_idx: Optional[int] = None
        # 추가/제거 추적용 — plotItem.items iteration 보다 신뢰성 ↑
        self._bars: list[pg.BarGraphItem] = []

        self.showGrid(x=False, y=True, alpha=0.15)
        self.plotItem.hideAxis("top")
        self.plotItem.hideAxis("right")
        self.getAxis("left").setWidth(56)
        self.setMenuEnabled(False)
        self.getPlotItem().hideButtons()
        self.plotItem.vb.setMouseEnabled(False, False)

        self._vline = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen("#888", width=1, style=Qt.DashLine),
        )
        self._vline.setZValue(60)
        self.addItem(self._vline)
        self._vline.hide()

        self._proxy = pg.SignalProxy(
            self.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse,
        )
        self._apply_theme_colors()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_theme_colors()
        self._render()

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
        self.setLabel("left", tr("出力 (GW)"), color=text_c, size="9pt")

    def set_data(
        self, rows: list[dict],
        sel_methods: list[str],
        sel_regions: list[str],
    ) -> None:
        self._rows = rows or []
        self._dates = [r["date"] for r in self._rows]
        self._sel_methods = list(sel_methods)
        self._sel_regions = list(sel_regions)
        self._render()

    def _filtered_value(self, row: dict, method: str) -> float:
        """선택된 region 비율 만큼만 method 의 op_mw 를 표시.

        DB는 region × method 별로 저장되어 있으므로 region 합계 기반으로
        해당 row 의 region 가중치를 구해 method 출력에 곱한다.
        """
        # row['regions'] 는 모든 region 의 op_mw 합. selected region 비율
        all_regions_total = sum(row["regions"].get(r, 0.0) for r in HJKS_REGIONS) or 1.0
        sel_region_total  = sum(row["regions"].get(r, 0.0) for r in self._sel_regions)
        ratio = sel_region_total / all_regions_total
        return row["methods"].get(method, 0.0) * ratio

    def _render(self) -> None:
        # 명시 추적 리스트로 안전하게 모든 BarGraphItem 제거
        for bar in self._bars:
            try:
                self.plotItem.removeItem(bar)
            except Exception:
                pass
        self._bars.clear()
        self._vline.hide()

        if not self._rows:
            self.plotItem.vb.setRange(xRange=(0, 1), yRange=(0, 1))
            self.getAxis("bottom").setTicks([[]])
            self.plotItem.vb.update()
            return

        n = len(self._rows)
        x_indices = list(range(n))
        # 누적용 y0
        y0 = [0.0] * n
        max_total = 0.0
        bar_w = 0.72 if n <= 30 else 0.85

        for method in self._sel_methods:
            heights = [self._filtered_value(r, method) / 1000.0 for r in self._rows]  # GW
            if sum(heights) <= 0: continue
            color = HJKS_COLORS.get(method, "#9E9E9E")
            bar = pg.BarGraphItem(
                x=x_indices, y0=y0[:], height=heights,
                width=bar_w, brush=QColor(color), pen=pg.mkPen(None),
            )
            bar.setToolTip(method)
            self.plotItem.addItem(bar)
            self._bars.append(bar)
            for i in range(n):
                y0[i] += heights[i]

        max_total = max(y0) if y0 else 1.0

        # X 축 ticks (간격 자동)
        target_ticks = 8
        step = max(1, n // target_ticks)
        ticks = []
        for i in range(0, n, step):
            d = self._rows[i]["date"]
            ticks.append((i, d[5:].replace("-", "/")))
        if ticks and ticks[-1][0] != n - 1:
            d = self._rows[-1]["date"]
            ticks.append((n - 1, d[5:].replace("-", "/")))
        self.getAxis("bottom").setTicks([ticks])

        # 뷰 설정
        x_pad = 0.5
        y_pad = max(0.1, max_total * 0.06)
        self.plotItem.vb.setRange(
            xRange=(-x_pad, n - 1 + x_pad),
            yRange=(0, max_total + y_pad),
            padding=0,
        )
        # 안전장치 — Qt 가 paint 큐를 깨우도록 강제
        self.plotItem.vb.update()
        self.update()

    def _on_mouse(self, evt) -> None:
        scene_pos = evt[0]
        if not self.sceneBoundingRect().contains(scene_pos):
            self._vline.hide(); QToolTip.hideText()
            self._hover_idx = None
            return
        if not self._rows:
            return
        mp = self.plotItem.vb.mapSceneToView(scene_pos)
        idx = int(round(mp.x()))
        if not (0 <= idx < len(self._rows)):
            self._vline.hide(); QToolTip.hideText()
            return
        self._vline.setPos(idx); self._vline.show()
        self._hover_idx = idx
        self._show_tooltip(idx, scene_pos)

    def _show_tooltip(self, idx: int, scene_pos) -> None:
        row = self._rows[idx]
        # filtered total
        total_g = sum(self._filtered_value(row, m) for m in self._sel_methods) / 1000.0
        text_c = "#A8B0BD" if self._is_dark else "#4A5567"
        lines = [f"<b>{row['date']}</b>"]
        for m in self._sel_methods:
            v = self._filtered_value(row, m) / 1000.0
            if v <= 0: continue
            color = HJKS_COLORS.get(m, "#9E9E9E")
            lines.append(
                f"<span style='color:{color}'>■</span> {m}: <b>{v:.2f}</b> GW"
            )
        lines.append(
            f"<span style='color:{_C_HJKS}'>合計</span>: <b>{total_g:.2f}</b> GW"
        )
        text = "<br>".join(lines)
        vp = self.mapFromScene(scene_pos)
        gp = self.mapToGlobal(QPoint(int(vp.x()), int(vp.y())))
        QToolTip.showText(gp + QPoint(14, -10), text, self)


# ──────────────────────────────────────────────────────────────────────
# D. _RegionBarsPanel — 좌측 panel: 지역별 평균 출력 horizontal bar
# ──────────────────────────────────────────────────────────────────────
class _RegionBarsPanel(QFrame):
    """선택 기간 region 별 평균 op (GW) 를 horizontal stacked bar 로 표시."""

    # 9 area + 沖縄 = 10. 각 영역 컬러 (디자인 mockup HJKS_AREAS 색상)
    _AREA_COLORS = {
        "北海道": "#5B8DEF",
        "東北":   "#34C759",
        "東京":   "#FF7A45",
        "中部":   "#A78BFA",
        "北陸":   "#2EC4B6",
        "関西":   "#F25C7A",
        "中国":   "#F59E0B",
        "四国":   "#10B981",
        "九州":   "#EF4444",
        "沖縄":   "#8E8E93",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("hjksRegionPanel")
        self._is_dark = True
        self._averages: dict[str, float] = {}  # region → avg op (GW)
        self._max = 1.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel(tr("エリア別 平均出力"))
        title.setObjectName("hjksPanelTitle")
        layout.addWidget(title)

        # Region rows container
        self._rows_box = QVBoxLayout()
        self._rows_box.setContentsMargins(0, 0, 0, 0)
        self._rows_box.setSpacing(10)
        self._row_widgets: dict[str, _RegionRow] = {}
        for region in HJKS_REGIONS:
            row = _RegionRow(region, self._AREA_COLORS.get(region, "#9E9E9E"))
            self._rows_box.addWidget(row)
            self._row_widgets[region] = row
        layout.addLayout(self._rows_box)
        layout.addStretch()
        self._apply_qss()

    def set_data(self, averages: dict[str, float]) -> None:
        """averages: {region: avg op MW}."""
        self._averages = averages or {}
        self._max = max(self._averages.values()) if self._averages else 1.0
        self._max = max(self._max, 1.0)
        for region, row in self._row_widgets.items():
            mw = self._averages.get(region, 0.0)
            gw = mw / 1000.0
            ratio = (mw / self._max) if self._max > 0 else 0.0
            row.set_value(gw=gw, ratio=ratio)

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        for r in self._row_widgets.values():
            r.set_theme(is_dark)
        self._apply_qss()

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        bg_surface   = "#14161C" if is_dark else "#FFFFFF"
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        border_subtle = "rgba(255,255,255,0.06)" if is_dark else "rgba(11,18,32,0.06)"
        self.setStyleSheet(f"""
            QFrame#hjksRegionPanel {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 16px;
            }}
            QLabel#hjksPanelTitle {{
                font-size: 14px; font-weight: 700;
                color: {fg_primary}; background: transparent;
            }}
        """)


class _RegionRow(QWidget):
    """단일 region 한 행 — 도트 + 라벨 + 값 + 그라데이션 막대."""

    def __init__(self, region: str, color: str, parent=None):
        super().__init__(parent)
        self._is_dark = True
        self._color = color
        self._gw = 0.0
        self._ratio = 0.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(4)

        head = QHBoxLayout(); head.setContentsMargins(0, 0, 0, 0); head.setSpacing(8)
        self._dot = QLabel("●")
        self._dot.setObjectName("rgnDot")
        self._dot.setFixedWidth(10)
        head.addWidget(self._dot)
        self._lbl = QLabel(tr(region))
        self._lbl.setObjectName("rgnLbl")
        head.addWidget(self._lbl, 1)
        self._val_lbl = QLabel("--")
        self._val_lbl.setObjectName("rgnVal")
        self._val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        head.addWidget(self._val_lbl)
        layout.addLayout(head)

        # 막대 (custom paint widget)
        self._bar = _RegionBar(color)
        self._bar.setFixedHeight(8)
        layout.addWidget(self._bar)

        self._apply_qss()

    def set_value(self, *, gw: float, ratio: float) -> None:
        self._gw = gw
        self._ratio = max(0.0, min(1.0, ratio))
        self._val_lbl.setText(f"{gw:.2f} GW")
        self._bar.set_ratio(self._ratio)

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._bar.set_theme(is_dark)
        self._apply_qss()

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        self.setStyleSheet(f"""
            QLabel#rgnDot {{ color: {self._color}; background: transparent; }}
            QLabel#rgnLbl {{
                font-size: 12px; font-weight: 700;
                color: {fg_primary}; background: transparent;
            }}
            QLabel#rgnVal {{
                font-size: 11px;
                font-family: "JetBrains Mono", "Consolas", monospace;
                color: {fg_secondary}; background: transparent;
            }}
        """)


class _RegionBar(QWidget):
    """region 단일 horizontal 그라데이션 바."""

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._is_dark = True
        self._color = color
        self._ratio = 0.0
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_ratio(self, r: float) -> None:
        self._ratio = max(0.0, min(1.0, r))
        self.update()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self.update()

    def paintEvent(self, _evt) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        radius = rect.height() / 2.0
        # track
        track = QColor("#1B1E26") if self._is_dark else QColor("#F0F2F5")
        p.setPen(Qt.NoPen); p.setBrush(track)
        p.drawRoundedRect(rect, radius, radius)
        # filled
        if self._ratio <= 0: return
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QLinearGradient
        fill_w = rect.width() * self._ratio
        fr = QRectF(rect.x(), rect.y(), fill_w, rect.height())
        grad = QLinearGradient(fr.topLeft(), fr.topRight())
        c1 = QColor(self._color); c1.setAlpha(170)
        c2 = QColor(self._color); c2.setAlpha(255)
        grad.setColorAt(0.0, c1)
        grad.setColorAt(1.0, c2)
        p.setBrush(grad)
        p.drawRoundedRect(fr, radius, radius)


# ──────────────────────────────────────────────────────────────────────
# E. _StoppedListPanel — 停止中 설비 목록
# ──────────────────────────────────────────────────────────────────────
class _StoppedListPanel(QFrame):
    """指定日 停止中 設備 (region × method, stopped_mw > 0) 의 상위 N 개 리스트."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("hjksStoppedPanel")
        self._is_dark = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel(tr("停止中の主要設備"))
        title.setObjectName("hjksPanelTitle")
        layout.addWidget(title)

        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(10)
        layout.addLayout(self._grid)

        self._empty_lbl = QLabel(tr("停止中の設備はありません"))
        self._empty_lbl.setObjectName("hjksStoppedEmpty")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._empty_lbl)
        self._empty_lbl.setVisible(False)   # setVisible 은 layout 추가 후

        layout.addStretch()
        self._apply_qss()

    def set_data(self, items: list[dict]) -> None:
        # 기존 카드 제거
        while self._grid.count():
            it = self._grid.takeAt(0)
            w = it.widget()
            if w: w.deleteLater()

        if not items:
            self._empty_lbl.setVisible(True)
            return
        self._empty_lbl.setVisible(False)

        for i, entry in enumerate(items):
            r, c = divmod(i, 2)
            card = _StoppedItemCard(entry, is_dark=self._is_dark)
            self._grid.addWidget(card, r, c)

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        for i in range(self._grid.count()):
            w = self._grid.itemAt(i).widget()
            if isinstance(w, _StoppedItemCard):
                w.set_theme(is_dark)
        self._apply_qss()

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        bg_surface   = "#14161C" if is_dark else "#FFFFFF"
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        border_subtle = "rgba(255,255,255,0.06)" if is_dark else "rgba(11,18,32,0.06)"
        self.setStyleSheet(f"""
            QFrame#hjksStoppedPanel {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 16px;
            }}
            QLabel#hjksPanelTitle {{
                font-size: 14px; font-weight: 700;
                color: {fg_primary}; background: transparent;
            }}
            QLabel#hjksStoppedEmpty {{
                font-size: 12px; color: {fg_tertiary};
                background: transparent; font-style: italic;
                padding: 24px 0;
            }}
        """)


class _StoppedItemCard(QFrame):
    """단일 停止中 항목 카드 — left border (color) + title + sub + 값."""

    def __init__(self, entry: dict, *, is_dark: bool, parent=None):
        super().__init__(parent)
        self._is_dark = is_dark
        self._entry = entry
        self.setObjectName("hjksStoppedItem")

        h = QHBoxLayout(self)
        h.setContentsMargins(14, 12, 14, 12)
        h.setSpacing(10)

        text_box = QVBoxLayout(); text_box.setSpacing(2)
        self._title_lbl = QLabel(f"{tr(entry['region'])}")
        self._title_lbl.setObjectName("itemTitle")
        text_box.addWidget(self._title_lbl)
        self._sub_lbl = QLabel(f"{tr(entry['method'])}")
        self._sub_lbl.setObjectName("itemSub")
        text_box.addWidget(self._sub_lbl)
        h.addLayout(text_box, 1)

        self._val_lbl = QLabel(f"{entry['stopped_mw']:.0f} MW")
        self._val_lbl.setObjectName("itemVal")
        h.addWidget(self._val_lbl, 0, Qt.AlignVCenter)

        self._apply_qss()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        color = self._entry.get("color", "#9E9E9E")
        bg_surface_2 = "#1B1E26" if is_dark else "#F0F2F5"
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        self.setStyleSheet(f"""
            QFrame#hjksStoppedItem {{
                background: {bg_surface_2};
                border: none;
                border-left: 3px solid {color};
                border-radius: 12px;
            }}
            QLabel#itemTitle {{
                font-size: 13px; font-weight: 700;
                color: {fg_primary}; background: transparent;
            }}
            QLabel#itemSub {{
                font-size: 11px;
                color: {fg_secondary}; background: transparent;
            }}
            QLabel#itemVal {{
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 13px; font-weight: 700;
                color: {fg_tertiary}; background: transparent;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# F. _ChipToggleRow — 다중 체크 chip row (region / method)
# ──────────────────────────────────────────────────────────────────────
class _ChipToggleRow(QWidget):
    """라벨 + 全選択 / 解除 + 칩 리스트."""

    selection_changed = Signal()

    def __init__(self, label: str, items: list[str], colors: dict[str, str], parent=None):
        super().__init__(parent)
        self._is_dark = True
        self._items = list(items)
        self._colors = dict(colors)
        self._selected: set[str] = set(items)
        self._chips: dict[str, QPushButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(8)

        self._label_lbl = QLabel(label)
        self._label_lbl.setObjectName("chipRowLabel")
        layout.addWidget(self._label_lbl)

        self._all_btn = QPushButton(tr("全選択"))
        self._all_btn.setObjectName("chipMiniBtn")
        self._all_btn.setCursor(Qt.PointingHandCursor)
        self._all_btn.clicked.connect(self.select_all)
        layout.addWidget(self._all_btn)

        self._none_btn = QPushButton(tr("解除"))
        self._none_btn.setObjectName("chipMiniBtn")
        self._none_btn.setCursor(Qt.PointingHandCursor)
        self._none_btn.clicked.connect(self.deselect_all)
        layout.addWidget(self._none_btn)

        for name in self._items:
            btn = QPushButton(tr(name))
            btn.setCheckable(True); btn.setChecked(True)
            btn.setObjectName("chipToggle")
            btn.setProperty("chipColor", self._colors.get(name, "#9E9E9E"))
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, n=name: self._on_toggle(n, checked))
            layout.addWidget(btn)
            self._chips[name] = btn

        layout.addStretch()
        self._apply_qss()

    def selected(self) -> list[str]:
        # items 순서 유지
        return [n for n in self._items if n in self._selected]

    def select_all(self) -> None:
        self._selected = set(self._items)
        for n, btn in self._chips.items():
            btn.blockSignals(True); btn.setChecked(True); btn.blockSignals(False)
        self._refresh_styles()
        self.selection_changed.emit()

    def deselect_all(self) -> None:
        self._selected.clear()
        for n, btn in self._chips.items():
            btn.blockSignals(True); btn.setChecked(False); btn.blockSignals(False)
        self._refresh_styles()
        self.selection_changed.emit()

    def _on_toggle(self, name: str, checked: bool) -> None:
        if checked:
            self._selected.add(name)
        else:
            self._selected.discard(name)
        self._refresh_styles()
        self.selection_changed.emit()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    def _refresh_styles(self) -> None:
        for n, btn in self._chips.items():
            btn.style().unpolish(btn); btn.style().polish(btn)

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        bg_surface_2 = "#1B1E26" if is_dark else "#F0F2F5"
        border       = "rgba(255,255,255,0.10)" if is_dark else "rgba(11,18,32,0.10)"
        # chip 컬러는 각 버튼의 chipColor 프로퍼티로 분기
        rules: list[str] = [f"""
            QLabel#chipRowLabel {{
                font-size: 11px; font-weight: 700;
                color: {fg_tertiary};
                background: transparent;
                letter-spacing: 0.04em;
                padding-right: 4px;
            }}
            QPushButton#chipMiniBtn {{
                font-size: 10px; font-weight: 700;
                padding: 4px 10px;
                border: 1px solid {border};
                background: {bg_surface_2};
                color: {fg_secondary};
                border-radius: 7px;
            }}
            QPushButton#chipToggle {{
                font-size: 11px; font-weight: 700;
                padding: 5px 12px;
                border-radius: 999px;
                border: 1px solid {border};
                background: {bg_surface_2};
                color: {fg_tertiary};
            }}
            QPushButton#chipToggle:hover {{ border-color: rgba(255,255,255,0.20); }}
        """]
        # checked 상태별 색상 분기 (chipColor 프로퍼티 기반)
        used_colors = sorted({c for c in self._colors.values()})
        for col in used_colors:
            r, g, b = self._hex_to_rgb(col)
            rules.append(f"""
                QPushButton#chipToggle[chipColor="{col}"]:checked {{
                    border: 1px solid {col};
                    background: rgba({r},{g},{b},0.14);
                    color: {col};
                }}
            """)
        self.setStyleSheet("\n".join(rules))

    @staticmethod
    def _hex_to_rgb(s: str) -> tuple[int, int, int]:
        h = s.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# ──────────────────────────────────────────────────────────────────────
# G. HjksWidget — 디테일 페이지
# ──────────────────────────────────────────────────────────────────────
class HjksWidget(BaseWidget):
    """HJKS 디테일 — DetailHeader + KPI + Filter + StackedBar + RegionBars + StoppedList."""

    # 지역 색상 (panel 과 통일)
    _AREA_COLORS = _RegionBarsPanel._AREA_COLORS

    def __init__(self):
        super().__init__()
        self._fetch_worker: Optional[FetchHjksWorker] = None
        self._range_thread: Optional[QThread] = None
        self._range_task:   Optional[_HjksRangeAggregateTask] = None
        self._stopped_thread: Optional[QThread] = None
        self._stopped_task:   Optional[_HjksStoppedTask] = None
        # 진행 중에 새 요청이 들어오면 마지막 요청만 보존 (race condition 방지)
        self._pending_range:   Optional[tuple[str, str]] = None
        self._pending_stopped: Optional[str] = None

        self._rows: list[dict] = []
        self._sel_regions: list[str] = list(HJKS_REGIONS)
        self._sel_methods: list[str] = list(HJKS_METHODS)

        # 기본 기간 — 오늘부터 미래 7 일 (start = 오늘, end = 오늘 + 6)
        start = QDate.currentDate()
        end = start.addDays(6)
        self._default_start, self._default_end = start, end

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(80)
        self._refresh_timer.timeout.connect(self._refresh_data)

        self._build_ui()
        self._refresh_data()

        # 자동 fetch 첫 실행 (다른 위젯과 겹치지 않도록 stagger)
        QTimer.singleShot(2250, self._on_fetch)
        self.setup_timer(
            self.settings.get("hjks_interval", 180),
            self._on_fetch,
            stagger_seconds=15,
        )

    def apply_settings_custom(self) -> None:
        self.update_timer_interval(self.settings.get("hjks_interval", 180))
        self._update_refresh_indicator()

    # ──────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        scroll = QScrollArea(self)
        scroll.setObjectName("hjksPageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer.addWidget(scroll, 1)

        content = QWidget(); content.setObjectName("hjksPageContent")
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(28, 22, 28, 22); root.setSpacing(16)

        # 1) DetailHeader
        self._header = LeeDetailHeader(
            title=tr("HJKS 発電稼働状況"),
            subtitle=tr("広域機関 公表電源稼働情報 · エリア × 電源種別 (日次)"),
            accent=_C_HJKS,
            icon_qicon=QIcon(":/img/plant.svg"),
            badge="",
            show_export=False,
        )
        self._header.back_clicked.connect(lambda: bus.page_requested.emit(0))
        root.addWidget(self._header)

        # 2) KPI strip (4 cards)
        kpi_row = QHBoxLayout(); kpi_row.setSpacing(10)
        self._kpi_avg  = LeeKPI(tr("期間 平均出力"), value="--", unit="GW", color=_C_HJKS)
        self._kpi_peak = LeeKPI(tr("期間 ピーク"),  value="--", unit="GW", color="#FF7A45")
        self._kpi_min  = LeeKPI(tr("期間 ボトム"),  value="--", unit="GW", color=_C_INFO)
        self._kpi_ren  = LeeKPI(tr("再エネ比率"),    value="--", unit="%",  color=_C_OK)
        for k in (self._kpi_avg, self._kpi_peak, self._kpi_min, self._kpi_ren):
            kpi_row.addWidget(k, 1)
        root.addLayout(kpi_row)

        # 3) Filter card
        root.addWidget(self._build_filter_card())

        # 4) ChartFrame
        self._chart = _StackedBarChart()
        self._chart.setMinimumHeight(360)
        self._chart_frame = LeeChartFrame(
            tr("期間内 日次出力"),
            subtitle=tr("電源種別の累積 (各日 平均出力)"),
            accent=_C_HJKS,
        )
        self._chart_frame.set_content(self._chart)
        self._chart_frame.setMinimumHeight(420)
        root.addWidget(self._chart_frame)
        # 첫 fetch 동안 차트 영역에 shimmer skeleton
        from app.ui.components.skeleton import install_skeleton_overlay
        self._chart_skel = install_skeleton_overlay(self._chart)

        # 5) Region bars + Stopped list
        bottom = QHBoxLayout(); bottom.setSpacing(16)
        self._region_panel = _RegionBarsPanel()
        self._stopped_panel = _StoppedListPanel()
        bottom.addWidget(self._region_panel, 6)
        bottom.addWidget(self._stopped_panel, 5)
        root.addLayout(bottom)

        # 6) Status row
        st_row = QHBoxLayout(); st_row.setSpacing(10)
        self._refresh_indicator = QLabel("")
        self._refresh_indicator.setObjectName("hjksRefreshIndicator")
        st_row.addWidget(self._refresh_indicator)
        self._status = QLabel(tr("待機中"))
        self._status.setObjectName("hjksStatusLbl")
        self._status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        st_row.addStretch()
        st_row.addWidget(self._status)
        root.addLayout(st_row)

        self._update_refresh_indicator()

    def _build_filter_card(self) -> QWidget:
        card = QFrame(); card.setObjectName("hjksFilterCard")
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 16, 20, 16); v.setSpacing(12)

        # Row 1 — 期間 + 7/14/30 quick + 取込
        row1 = QHBoxLayout(); row1.setSpacing(10)
        lab = QLabel(tr("期間"))
        lab.setObjectName("chipRowLabel")
        row1.addWidget(lab)

        self._start_input = LeeDateInput(accent=_C_HJKS, show_today_btn=False)
        self._start_input.set_date(self._default_start)
        self._start_input.date_changed.connect(self._on_range_changed)
        row1.addWidget(self._start_input)

        sep_lbl = QLabel("〜"); sep_lbl.setObjectName("chipRowLabel")
        row1.addWidget(sep_lbl)

        self._end_input = LeeDateInput(accent=_C_HJKS, show_today_btn=False)
        self._end_input.set_date(self._default_end)
        self._end_input.date_changed.connect(self._on_range_changed)
        row1.addWidget(self._end_input)

        # Quick range buttons
        for label, days in [("7日", 7), ("14日", 14), ("30日", 30)]:
            b = QPushButton(label)
            b.setObjectName("chipMiniBtn")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, d=days: self._set_range_days(d))
            row1.addWidget(b)

        row1.addStretch()
        self._btn_fetch = LeeButton(tr("最新取込"), variant="secondary", size="sm")
        self._btn_fetch.clicked.connect(self._on_fetch)
        row1.addWidget(self._btn_fetch)
        v.addLayout(row1)

        # Row 2 — エリア
        self._region_row = _ChipToggleRow(
            tr("エリア"), HJKS_REGIONS, self._AREA_COLORS,
        )
        self._region_row.selection_changed.connect(self._on_filter_changed)
        v.addWidget(self._region_row)

        # Row 3 — 電源種別
        self._method_row = _ChipToggleRow(
            tr("電源種別"), HJKS_METHODS, HJKS_COLORS,
        )
        self._method_row.selection_changed.connect(self._on_filter_changed)
        v.addWidget(self._method_row)

        self._filter_card = card
        self._apply_filter_qss()
        return card

    def _apply_page_qss(self) -> None:
        bg_app = "#0A0B0F" if self.is_dark else "#F5F6F8"
        self.setStyleSheet(f"""
            HjksWidget {{ background: {bg_app}; }}
            QScrollArea#hjksPageScroll {{ background: {bg_app}; border: none; }}
            QWidget#hjksPageContent {{ background: {bg_app}; }}
        """)

    def _apply_filter_qss(self) -> None:
        is_dark = self.is_dark
        bg_surface   = "#14161C" if is_dark else "#FFFFFF"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        border_subtle = "rgba(255,255,255,0.06)" if is_dark else "rgba(11,18,32,0.06)"
        self._filter_card.setStyleSheet(f"""
            QFrame#hjksFilterCard {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 14px;
            }}
        """)
        # 상태 + indicator
        self.setStyleSheet(self.styleSheet() + f"""
            QLabel#hjksRefreshIndicator {{
                font-size: 11px; font-weight: 600;
                color: {_C_OK};
                background: rgba(48,209,88,0.10);
                border: 1px solid rgba(48,209,88,0.25);
                border-radius: 999px;
                padding: 3px 10px;
            }}
            QLabel#hjksStatusLbl {{
                font-size: 11px; color: {fg_secondary};
                background: transparent;
            }}
        """)

    def _update_refresh_indicator(self) -> None:
        try:
            interval = int(self.settings.get("hjks_interval", 180))
        except Exception:
            interval = 180
        self._refresh_indicator.setText(f"●  {interval}{tr('分ごと')}")

    # ──────────────────────────────────────────────────────────
    # BaseWidget hooks
    # ──────────────────────────────────────────────────────────
    def apply_theme_custom(self) -> None:
        d = self.is_dark
        self._header.set_theme(d)
        for k in (self._kpi_avg, self._kpi_peak, self._kpi_min, self._kpi_ren):
            k.set_theme(d)
        self._chart_frame.set_theme(d)
        self._chart.set_theme(d)
        self._region_panel.set_theme(d)
        self._stopped_panel.set_theme(d)
        self._region_row.set_theme(d)
        self._method_row.set_theme(d)
        self._start_input.set_theme(d)
        self._end_input.set_theme(d)
        self._apply_page_qss()
        self._apply_filter_qss()

    def set_loading(self, is_loading: bool) -> None:
        super().set_loading(is_loading, self._chart_frame)

    # ──────────────────────────────────────────────────────────
    # Filter / range 변경
    # ──────────────────────────────────────────────────────────
    def _on_range_changed(self, _qd: QDate = None) -> None:
        self._refresh_timer.start()

    def _on_filter_changed(self) -> None:
        self._sel_regions = self._region_row.selected()
        self._sel_methods = self._method_row.selected()
        # Filter 만 변경 → 차트/패널 재렌더링 (DB 재쿼리 X)
        self._render()

    def _set_range_days(self, days: int) -> None:
        """현재 start 를 앵커로 미래로 N 일 적용 (모킹업 동작)."""
        start = self._start_input.date()
        end = start.addDays(days - 1)
        # blockSignals 로 date_changed 발화 방지 → 직접 refresh 트리거
        self._end_input.blockSignals(True)
        self._end_input.set_date(end)
        self._end_input.blockSignals(False)
        # 동일 range 라도 즉시 새로고침 보장
        self._refresh_timer.start()

    # ──────────────────────────────────────────────────────────
    # Data fetch (HJKS API → DB)
    # ──────────────────────────────────────────────────────────
    def _on_fetch(self) -> None:
        if not self.check_online_status(): return
        try:
            if self._fetch_worker and self._fetch_worker.isRunning():
                return
        except RuntimeError:
            self._fetch_worker = None
        self._btn_fetch.setEnabled(False)
        self._set_status(tr("データ取得中..."))
        self._fetch_worker = FetchHjksWorker()
        self._fetch_worker.finished.connect(self._on_fetch_done)
        self._fetch_worker.error.connect(self._on_fetch_error)
        self._fetch_worker.finished.connect(self._fetch_worker.deleteLater)
        self._fetch_worker.start()
        self.track_worker(self._fetch_worker)

    def _on_fetch_done(self, msg: str) -> None:
        self._btn_fetch.setEnabled(True)
        self._set_status(msg)
        bus.hjks_updated.emit()
        self._refresh_data()

    def _on_fetch_error(self, err: str) -> None:
        self._btn_fetch.setEnabled(True)
        self._set_status(tr("取得失敗: {0}").format(err))
        # 자동 갱신 시 모달 X — 짧은 토스트 (상세는 위젯 status 라벨에)
        bus.toast_requested.emit(tr("⚠ HJKS 取得失敗"), "error")

    # ──────────────────────────────────────────────────────────
    # DB 로드 (background) → 렌더링
    # ──────────────────────────────────────────────────────────
    def _refresh_data(self) -> None:
        start = self._start_input.date().toString("yyyy-MM-dd")
        end   = self._end_input.date().toString("yyyy-MM-dd")
        if start > end:
            start, end = end, start

        # 마지막 요청을 기록 — 진행 중에 들어와도 보존되어 끝나면 재실행
        self._pending_range = (start, end)
        self._pending_stopped = end

        self._set_status(tr("データ集計中..."))

        # range thread — 진행 중이면 그냥 리턴 (끝날 때 pending 자동 처리)
        try:
            range_busy = bool(self._range_thread and self._range_thread.isRunning())
        except RuntimeError:
            range_busy = False
            self._range_thread = None
        if not range_busy:
            self._start_range_task(start, end)

        # stopped thread — 동일 로직
        try:
            stopped_busy = bool(self._stopped_thread and self._stopped_thread.isRunning())
        except RuntimeError:
            stopped_busy = False
            self._stopped_thread = None
        if not stopped_busy:
            self._start_stopped_task(end)

    def _start_range_task(self, start: str, end: str) -> None:
        # 진행 시작 시 pending 클리어 (현재 처리 중인 요청과 동일)
        self._pending_range = None
        self._range_thread = QThread()
        self._range_task = _HjksRangeAggregateTask(start, end)
        self._range_task.moveToThread(self._range_thread)
        self._range_thread.started.connect(self._range_task.run)
        self._range_task.finished.connect(self._on_range_done)
        self._range_task.finished.connect(self._range_thread.quit)
        self._range_task.finished.connect(self._range_task.deleteLater)
        self._range_thread.finished.connect(self._range_thread.deleteLater)
        self._range_thread.start()
        self.track_worker(self._range_thread)

    def _start_stopped_task(self, end: str) -> None:
        self._pending_stopped = None
        self._stopped_thread = QThread()
        self._stopped_task = _HjksStoppedTask(end, top_n=10)
        self._stopped_task.moveToThread(self._stopped_thread)
        self._stopped_thread.started.connect(self._stopped_task.run)
        self._stopped_task.finished.connect(self._on_stopped_done)
        self._stopped_task.finished.connect(self._stopped_thread.quit)
        self._stopped_task.finished.connect(self._stopped_task.deleteLater)
        self._stopped_thread.finished.connect(self._stopped_thread.deleteLater)
        self._stopped_thread.start()
        self.track_worker(self._stopped_thread)

    def _on_range_done(self, rows: list) -> None:
        self._rows = rows or []
        if not self._rows:
            self._set_status(tr("該当データなし"))
        else:
            self._set_status(
                tr("{0}日間 · {1}件").format(len(self._rows), self._count_records())
            )
        self._render()
        # pending 요청 있으면 재실행 (race condition 방지)
        if self._pending_range is not None:
            s, e = self._pending_range
            QTimer.singleShot(0, lambda: self._start_range_task(s, e))

    def _count_records(self) -> int:
        # row 안 method 비0 항목 수 세기 (참고용)
        n = 0
        for r in self._rows:
            for v in r["methods"].values():
                if v > 0: n += 1
        return n

    def _on_stopped_done(self, items: list) -> None:
        self._stopped_panel.set_data(items)
        if self._pending_stopped is not None:
            d = self._pending_stopped
            QTimer.singleShot(0, lambda: self._start_stopped_task(d))

    # ──────────────────────────────────────────────────────────
    # 렌더링
    # ──────────────────────────────────────────────────────────
    def _render(self) -> None:
        # 첫 데이터 도착 시 skeleton 제거
        if self._rows and getattr(self, "_chart_skel", None) is not None:
            self._chart_skel.stop(); self._chart_skel.deleteLater(); self._chart_skel = None
        # Chart
        self._chart.set_data(self._rows, self._sel_methods, self._sel_regions)
        self._render_kpi()
        self._render_region_panel()
        # Header badge
        n_days = len(self._rows)
        self._header.set_badge(
            f"{len(self._sel_regions)}/{len(HJKS_REGIONS)} エリア · "
            f"{len(self._sel_methods)}/{len(HJKS_METHODS)} 電源 · {n_days}日"
        )
        # Chart subtitle (range)
        if self._rows:
            d0 = self._rows[0]["date"]; d1 = self._rows[-1]["date"]
            self._chart_frame.set_subtitle(
                tr("{0} 〜 {1} · 電源種別の累積 (各日 出力)").format(d0, d1)
            )
        else:
            self._chart_frame.set_subtitle(tr("データなし"))

    def _render_kpi(self) -> None:
        if not self._rows:
            for k in (self._kpi_avg, self._kpi_peak, self._kpi_min, self._kpi_ren):
                k.set_value("--", unit="", sub="")
            return

        # 각 row 의 filtered total (region+method 적용)
        totals = []
        for r in self._rows:
            t = self._filtered_total(r)  # MW
            totals.append(t)
        avg_mw = sum(totals) / len(totals) if totals else 0.0
        peak_mw = max(totals) if totals else 0.0
        min_mw  = min(totals) if totals else 0.0
        peak_idx = totals.index(peak_mw) if totals else -1
        min_idx  = totals.index(min_mw)  if totals else -1

        # 재생에너지 비율
        ren_total = 0.0
        for r in self._rows:
            for m in self._sel_methods:
                if m in _RENEWABLE_METHODS:
                    ren_total += self._method_value(r, m)
        ren_avg_mw = ren_total / len(self._rows) if self._rows else 0.0
        ren_pct = (ren_avg_mw / avg_mw * 100.0) if avg_mw > 0 else 0.0

        peak_lbl = self._rows[peak_idx]["date"][5:].replace("-", "/") if peak_idx >= 0 else "-"
        min_lbl  = self._rows[min_idx]["date"][5:].replace("-", "/")  if min_idx >= 0 else "-"

        self._kpi_avg.set_value(
            f"{avg_mw / 1000.0:.1f}", unit="GW", color=_C_HJKS,
            sub=tr("{0}日間平均").format(len(self._rows)),
        )
        self._kpi_peak.set_value(
            f"{peak_mw / 1000.0:.1f}", unit="GW", color="#FF7A45", sub=peak_lbl,
        )
        self._kpi_min.set_value(
            f"{min_mw / 1000.0:.1f}", unit="GW", color=_C_INFO, sub=min_lbl,
        )
        self._kpi_ren.set_value(
            f"{ren_pct:.1f}", unit="%", color=_C_OK, sub=tr("水力 + その他"),
        )

    def _filtered_total(self, row: dict) -> float:
        """선택된 region/method 만 합한 MW 총합."""
        return sum(self._method_value(row, m) for m in self._sel_methods)

    def _method_value(self, row: dict, method: str) -> float:
        """row 안에서 선택된 region 비율 가중 적용한 method op_mw."""
        all_total = sum(row["regions"].get(r, 0.0) for r in HJKS_REGIONS) or 1.0
        sel_total = sum(row["regions"].get(r, 0.0) for r in self._sel_regions)
        ratio = sel_total / all_total
        return row["methods"].get(method, 0.0) * ratio

    def _render_region_panel(self) -> None:
        if not self._rows:
            self._region_panel.set_data({})
            return
        # 기간 평균: 각 region 의 일평균 op_mw — 단, method 필터 반영 (해당 region 의 op_mw 비례)
        averages: dict[str, float] = {}
        n = len(self._rows)
        # method 필터 적용 시: row['methods'] 값 중 sel_methods 합 / row['methods'] 전체 합 비율로 region 값 보정
        for region in HJKS_REGIONS:
            # 단순화 — region 별 op_mw 전체 평균 (method 비율은 row 단위로 적용)
            total = 0.0
            for r in self._rows:
                row_methods_sel = sum(r["methods"].get(m, 0.0) for m in self._sel_methods)
                row_methods_all = sum(r["methods"].values()) or 1.0
                ratio = row_methods_sel / row_methods_all
                total += r["regions"].get(region, 0.0) * ratio
            averages[region] = total / n if n else 0.0
        self._region_panel.set_data(averages)

    # ──────────────────────────────────────────────────────────
    # 상태
    # ──────────────────────────────────────────────────────────
    def _set_status(self, msg: str) -> None:
        self._status.setText(msg)
