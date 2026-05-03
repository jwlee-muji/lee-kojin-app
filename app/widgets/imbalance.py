"""インバランス単価 ウィジェット — Phase 5.3 リニューアル.

디자인 출처: handoff/LEE_PROJECT/varA-detail-screens.jsx ImbalanceDetail
            handoff/LEE_PROJECT/varA-cards.jsx ImbCard
모킹업 1:1 구현:
    - ImbalanceCard (대시보드): LeeCard(accent="imb") + 직근30분 큰 숫자 +
      sparkline + 알림 pill (急騰/注意/安定)
    - ImbalanceWidget (디테일): DetailHeader + KPI strip + 余剰/不足 SegSwitch +
      에리어 chips + LeePivotTable + LeeChartFrame (multi-area line chart)

[기존 보존]
    - UpdateImbalanceWorker (CSV DB 업데이트)
    - LoadImbalanceDataTask (백그라운드 DB 로드)
    - 高単価 アラート 검출 + 알림 센터/트레이/Toast
    - settings.imbalance_alert / imbalance_interval
    - bus.imbalance_updated emit
"""
from __future__ import annotations

import csv
import logging
import math
import sqlite3
from datetime import datetime
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import (
    Qt, QDate, QPoint, QThread, QTimer, Signal, QObject,
)
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QApplication, QDialog, QDoubleSpinBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QToolTip, QVBoxLayout, QWidget,
)

from app.api.market.imbalance import UpdateImbalanceWorker
from app.core.config import (
    DB_IMBALANCE, IMBALANCE_COLORS,
    DATE_COL_IDX, TIME_COL_IDX, YOJO_START_COL_IDX, YOJO_END_COL_IDX,
    FUSOKU_START_COL_IDX, load_settings,
)
from app.core.database import get_db_connection, validate_column_name
from app.core.events import bus
from app.core.i18n import tr
from app.ui.common import BaseWidget, ToastNotification
from app.ui.components import (
    LeeButton, LeeCard, LeeChartFrame, LeeCountValue, LeeDateInput,
    LeeDetailHeader, LeeDialog, LeeIconTile, LeeKPI, LeePill, LeePivotTable,
    LeeSegment, LeeSparkline,
)

pg.setConfigOptions(antialias=True)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 토큰 / 정수
# ──────────────────────────────────────────────────────────────────────
_C_IMB  = "#F25C7A"   # --c-imb
_C_OK   = "#30D158"
_C_WARN = "#FF9F0A"
_C_BAD  = "#FF453A"

# 에리어별 라인 색상 (PivotTable.AREA_COLORS 와 일관)
_AREA_COLORS = {
    "北海道": "#4285F4", "東北": "#EA4335", "東京": "#FBBC05",
    "中部":   "#34A853", "北陸": "#FF6D00", "関西": "#7986CB",
    "中国":   "#E67C73", "四国": "#0B8043", "九州": "#8E24AA",
    "沖縄":   "#D50000",
}

_LEFT_AXIS_W = 56


# ──────────────────────────────────────────────────────────────────────
# A. ImbalanceCard — 대시보드용 카드 (모킹업 ImbCard 1:1)
# ──────────────────────────────────────────────────────────────────────
class ImbalanceCard(LeeCard):
    """インバランス 카드 — 직근 30分 가격 + sparkline + 알림 pill.

    레이아웃:
        ┌─────────────────────────────────────────────────────┐
        │ [icon] インバランス               [⚠ 急騰 / 安定]    │
        │        OCCTO リアルタイム · 直近30分                │
        │                                                      │
        │ 38.50 円/kWh                                         │
        │ 18:30 · 東京エリア                                   │
        │                                                      │
        │ ╱╲╱╲╱╲╱╲╱╲╱╲ (sparkline 48 slots)                  │
        │                                                      │
        │ 00:00 06:00 12:00 18:00 24:00                       │
        └─────────────────────────────────────────────────────┘
    """

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(accent_color="imb", interactive=True, parent=parent)
        self.setMinimumHeight(220)
        self._is_dark = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(0)

        # ── 헤더: icon + (title/sub) + alert pill ───────────────
        header = QHBoxLayout()
        header.setSpacing(12)
        header.setContentsMargins(0, 0, 0, 12)

        self._icon = LeeIconTile(
            icon=QIcon(":/img/won.svg"),
            color=_C_IMB, size=40, radius=12,
        )
        header.addWidget(self._icon, 0, Qt.AlignTop)

        title_box = QVBoxLayout(); title_box.setSpacing(2); title_box.setContentsMargins(0, 0, 0, 0)
        self._title_lbl = QLabel(tr("インバランス"))
        self._title_lbl.setObjectName("imbCardTitle")
        self._sub_lbl = QLabel(tr("OCCTO リアルタイム · 直近30分"))
        self._sub_lbl.setObjectName("imbCardSub")
        title_box.addWidget(self._title_lbl)
        title_box.addWidget(self._sub_lbl)
        header.addLayout(title_box, 1)

        self._alert_pill = LeePill("", variant="success")
        header.addWidget(self._alert_pill, 0, Qt.AlignTop)
        self._alert_pill.setVisible(False)   # setVisible 은 layout 추가 후

        layout.addLayout(header)

        # ── 큰 숫자 + 단위 ────────────────────────────────────
        num_row = QHBoxLayout(); num_row.setSpacing(4)
        num_row.setContentsMargins(0, 0, 0, 2)
        num_row.setAlignment(Qt.AlignBaseline)
        self._value_lbl = LeeCountValue(formatter=lambda v: f"{v:.2f}")
        self._value_lbl.setObjectName("imbCardValue")
        self._unit_lbl = QLabel(tr("円/kWh"))
        self._unit_lbl.setObjectName("imbCardUnit")
        num_row.addWidget(self._value_lbl, 0, Qt.AlignBaseline)
        num_row.addWidget(self._unit_lbl,  0, Qt.AlignBaseline)
        num_row.addStretch()
        layout.addLayout(num_row)

        # ── 직근 슬롯/에리어 정보 ──────────────────────────────
        self._slot_lbl = QLabel("")
        self._slot_lbl.setObjectName("imbCardSlot")
        layout.addWidget(self._slot_lbl)

        # ── Sparkline ─────────────────────────────────────────
        self._chart_box = QWidget()
        chart_lay = QVBoxLayout(self._chart_box)
        chart_lay.setContentsMargins(0, 8, 0, 0)
        chart_lay.setSpacing(2)

        # range pill (MIN ~ MAX)
        range_row = QHBoxLayout(); range_row.setContentsMargins(0, 0, 0, 0); range_row.setSpacing(0)
        range_row.addStretch()
        self._range_lbl = QLabel("")
        self._range_lbl.setObjectName("imbRangeLbl")
        range_row.addWidget(self._range_lbl)
        chart_lay.addLayout(range_row)

        self._spark = LeeSparkline(_C_IMB, height=48, fill_alpha=80)
        chart_lay.addWidget(self._spark)

        time_row = QHBoxLayout(); time_row.setContentsMargins(0, 2, 0, 0); time_row.setSpacing(0)
        for t in ("00:00", "06:00", "12:00", "18:00", "24:00"):
            tl = QLabel(t); tl.setObjectName("imbTimeLbl"); tl.setAlignment(Qt.AlignCenter)
            time_row.addWidget(tl, 1)
        chart_lay.addLayout(time_row)

        layout.addWidget(self._chart_box)

        # 데이터 없을 때 placeholder
        self._note = QLabel(tr("データなし"))
        self._note.setObjectName("imbCardNote")
        self._note.setAlignment(Qt.AlignCenter)
        self._note.setMinimumHeight(72)
        layout.addWidget(self._note)
        self._note.setVisible(False)   # setVisible 은 layout 추가 후

        layout.addStretch()
        self._apply_local_qss()
        self.set_no_data()

    # ── 외부 API ─────────────────────────────────────────────
    def set_payload(self, payload: dict) -> None:
        latest = payload.get("latest_price")
        if latest is None:
            self.set_no_data(); return
        self._value_lbl.set_value(float(latest))
        slot = payload.get("latest_slot", "")
        area = payload.get("latest_area", "")
        slot_text = self._format_slot(slot)
        if slot_text and area:
            self._slot_lbl.setText(f"{slot_text} · {tr(area)}")
        elif slot_text:
            self._slot_lbl.setText(slot_text)
        elif area:
            self._slot_lbl.setText(tr(area))
        else:
            self._slot_lbl.setText("")

        # Alert pill — 현재 가격 vs 임계값
        level = payload.get("alert_level", "ok")
        if level == "bad":
            self._alert_pill.setText(tr("⚠ 急騰"))
            self._alert_pill.set_variant("danger")
        elif level == "warn":
            self._alert_pill.setText(tr("注意"))
            self._alert_pill.set_variant("warn")
        else:
            self._alert_pill.setText(tr("● 安定"))
            self._alert_pill.set_variant("success")
        self._alert_pill.setVisible(True)

        # Sparkline
        slots = payload.get("slots") or []
        values = [v for _, v in slots]
        self._spark.set_data(values)
        self._update_range_label(values)

        # 가시성
        show = bool(values)
        self._chart_box.setVisible(show)
        self._note.setVisible(not show)
        if not show:
            self._note.setText(tr("チャートデータなし"))

    def set_no_data(self) -> None:
        self._value_lbl.set_value(0.0, animate=False)
        self._value_lbl.setText("--")
        self._slot_lbl.setText(tr("データなし"))
        self._alert_pill.setVisible(False)
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

    # ── 내부 ─────────────────────────────────────────────────
    @staticmethod
    def _format_slot(slot: str) -> str:
        """슬롯 정규화 — '10' → '10:00', '10:30' → '10:30', 그 외 그대로."""
        if not slot:
            return ""
        s = str(slot).strip()
        if ":" in s:
            return s
        # "1030" / "1000" 패턴
        if s.isdigit() and len(s) >= 3:
            return f"{s[:-2].zfill(2)}:{s[-2:]}"
        return s

    def _update_range_label(self, values: list[float]) -> None:
        if not values:
            self._range_lbl.setText("")
            return
        mn = min(values); mx = max(values)
        self._range_lbl.setText(f"MIN {mn:.1f}  ·  MAX {mx:.1f}")

    def _apply_local_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        self.setStyleSheet(f"""
            QLabel#imbCardTitle {{
                font-size: 13px; font-weight: 600;
                color: {fg_secondary}; background: transparent;
            }}
            QLabel#imbCardSub {{
                font-size: 11px; color: {fg_tertiary};
                background: transparent;
            }}
            QLabel#imbCardValue {{
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 32px; font-weight: 800;
                color: {_C_IMB}; background: transparent;
                letter-spacing: -0.02em;
            }}
            QLabel#imbCardUnit {{
                font-size: 13px; font-weight: 600;
                color: {fg_tertiary}; background: transparent;
                padding-bottom: 4px;
            }}
            QLabel#imbCardSlot {{
                font-size: 11px; color: {fg_secondary};
                background: transparent;
            }}
            QLabel#imbTimeLbl {{
                font-size: 10px; color: {fg_tertiary};
                background: transparent;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QLabel#imbRangeLbl {{
                font-size: 9px; font-weight: 700;
                color: {fg_tertiary}; background: transparent;
                font-family: "JetBrains Mono", "Consolas", monospace;
                letter-spacing: 0.04em;
            }}
            QLabel#imbCardNote {{
                font-size: 11px; font-weight: 500;
                color: {fg_tertiary}; background: transparent;
                font-style: italic;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# B. _ImbMultiAreaChart — 다중 에리어 라인 차트 + 호버 + threshold 가이드
# ──────────────────────────────────────────────────────────────────────
class _ImbMultiAreaChart(pg.PlotWidget):
    """インバランス 라인 차트 — area on/off 외부 제어, threshold 가이드라인."""

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

        # 임계값 가이드라인 (warn / bad)
        self._guide_lines: list[pg.InfiniteLine] = []

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
        self.setLabel("left", tr("単価 (円/kWh)"), color=text_c, size="9pt")

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_theme_colors()

    def set_x_label(self, label: str) -> None:
        text_c = "#A8B0BD" if self._is_dark else "#4A5567"
        self.setLabel("bottom", label, color=text_c, size="9pt")

    def set_x_labels(self, x_to_label: dict) -> None:
        self._x_to_label = x_to_label

    def set_thresholds(self, thresholds: list[tuple[float, str]]) -> None:
        """thresholds: [(value, color), ...] — 가로 가이드라인."""
        for line in self._guide_lines:
            self.removeItem(line)
        self._guide_lines.clear()
        for level, gcolor in thresholds:
            line = pg.InfiniteLine(
                pos=level, angle=0,
                pen=pg.mkPen(QColor(gcolor), width=1, style=Qt.DashLine),
            )
            line.setZValue(-10)
            self.addItem(line)
            self._guide_lines.append(line)

    # 호버 / 트래커
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
            if xd is None or len(xd) == 0: continue
            idx = int(np.argmin(np.abs(xd - nx)))
            y = float(yd[idx])
            if not math.isnan(y):
                lines.append(
                    f"<span style='color:{color}'>{name}</span>: "
                    f"<b>{y:.2f}</b> 円/kWh"
                )
        return "<br>".join(lines) if len(lines) > 1 else ""

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

    def copy_to_clipboard(self) -> None:
        QApplication.clipboard().setPixmap(self.grab())


# ──────────────────────────────────────────────────────────────────────
# C. LoadImbalanceDataTask — 백그라운드 DB 로드 (기존 보존)
# ──────────────────────────────────────────────────────────────────────
class LoadImbalanceDataTask(QObject):
    """현대화된 QObject 기반 Worker (QThread.moveToThread 패턴)."""
    finished = Signal(list, list, str, int)  # rows, target_cols, time_col, target_yyyymmdd
    error    = Signal(str)
    no_data  = Signal(str)

    def __init__(self, target_date, target_yyyymmdd, is_yojo):
        super().__init__()
        self.target_date     = target_date
        self.target_yyyymmdd = target_yyyymmdd
        self.is_yojo         = is_yojo

    def run(self):
        try:
            with get_db_connection(DB_IMBALANCE) as conn:
                pragma_rows = conn.execute("PRAGMA table_info('imbalance_prices')").fetchall()
                col_names = [row[1].strip().replace('﻿', '') for row in pragma_rows]
                date_col = validate_column_name(col_names[DATE_COL_IDX])

                rows = conn.execute(
                    f'SELECT * FROM imbalance_prices WHERE "{date_col}" = ? OR "{date_col}" = ?',
                    (self.target_yyyymmdd, str(self.target_yyyymmdd)),
                ).fetchall()

                if not rows:
                    range_row = conn.execute(
                        f'SELECT MIN(CAST("{date_col}" AS INTEGER)), MAX(CAST("{date_col}" AS INTEGER)) FROM imbalance_prices'
                    ).fetchone()
                    if range_row and range_row[0] is not None:
                        min_d, max_d = str(int(range_row[0])), str(int(range_row[1]))
                        msg = tr("{0} のデータがありません。\n(DBに保存されている期間: {1} ~ {2})").format(
                            self.target_date,
                            f"{min_d[:4]}/{min_d[4:6]}/{min_d[6:]}",
                            f"{max_d[:4]}/{max_d[4:6]}/{max_d[6:]}",
                        )
                    else:
                        msg = tr("DBに有効なデータがありません。")
                    self.no_data.emit(msg)
                    return

            time_col = col_names[TIME_COL_IDX]
            yojo_cols = [
                c for i, c in enumerate(col_names)
                if YOJO_START_COL_IDX <= i <= YOJO_END_COL_IDX and '変更S' not in c
            ]
            fusoku_cols = [
                c for i, c in enumerate(col_names)
                if i >= FUSOKU_START_COL_IDX and '変更S' not in c
            ]
            target_cols = yojo_cols if self.is_yojo else fusoku_cols

            display_cols = [time_col] + target_cols
            col_indices  = {name: idx for idx, name in enumerate(col_names)}

            processed_rows = []
            for row in rows:
                processed_row = []
                for col in display_cols:
                    val = row[col_indices[col]]
                    if col != time_col and val is not None and str(val).strip() != "":
                        try: val = float(val)
                        except ValueError: val = None
                    processed_row.append(val)
                processed_rows.append(processed_row)

            self.finished.emit(processed_rows, target_cols, time_col, self.target_yyyymmdd)
        except sqlite3.Error as e:
            self.error.emit(f"DBエラー: {e}")
        except Exception as e:
            logger.error(f"インバランスデータの読み込み中に予期せぬエラー: {e}", exc_info=True)
            self.error.emit(str(e))


# ──────────────────────────────────────────────────────────────────────
# D. _ThresholdDialog — 알림 임계값 설정
# ──────────────────────────────────────────────────────────────────────
class _ThresholdDialog(LeeDialog):
    """インバランス 알림 임계값 (円/kWh) 설정 다이얼로그."""

    def __init__(self, current: float, parent=None):
        super().__init__(tr("アラート閾値"), kind="info", parent=parent)
        self._spin = QDoubleSpinBox()
        self._spin.setRange(0.0, 1000.0)
        self._spin.setSingleStep(0.5)
        self._spin.setDecimals(1)
        self._spin.setSuffix(f" {tr('円/kWh')}")
        self._spin.setValue(float(current))
        self._spin.setMinimumWidth(180)

        # LeeDialog body 에 spin 추가
        body_widget = QWidget()
        bl = QVBoxLayout(body_widget)
        bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(8)
        bl.addWidget(QLabel(tr("インバランス急騰アラートを発令する閾値:")))
        bl.addWidget(self._spin)
        self.set_message_widget(body_widget) if hasattr(self, "set_message_widget") else self.set_message(
            tr("急騰閾値: {0} 円/kWh").format(current)
        )

        self.add_button(tr("キャンセル"), "secondary", role="reject")
        self.add_button(tr("保存"), "primary", role="accept")

    def value(self) -> float:
        return float(self._spin.value())


# ──────────────────────────────────────────────────────────────────────
# E. ImbalanceWidget — 디테일 페이지 (디자인 1:1)
# ──────────────────────────────────────────────────────────────────────
class ImbalanceWidget(BaseWidget):
    """インバランス単価 디테일 — DetailHeader + KPI + filter + PivotTable + Chart."""

    def __init__(self):
        super().__init__()
        self._is_yojo = True   # True=余剰, False=不足
        self._sel_date = QDate.currentDate()
        self._area_on: dict[str, bool] = {}     # col_name → bool
        self._last_rows: list[list] = []
        self._last_cols: list[str]  = []
        self._last_time_col: str    = ""
        self._last_yyyymmdd: int    = 0
        self._alerted_high_prices: set = set()
        self.worker: Optional[UpdateImbalanceWorker] = None
        self._load_task: Optional[LoadImbalanceDataTask] = None
        self._load_thread: Optional[QThread] = None

        self._build_ui()

        interval = int(self.settings.get("imbalance_interval", 5))
        self.setup_timer(interval, self.update_database)
        QTimer.singleShot(2250, self.update_database)

    # ──────────────────────────────────────────────────────────
    # UI 빌드
    # ──────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        # 페이지 자체는 ScrollArea 만 담는 빈 컨테이너
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setObjectName("imbPageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer.addWidget(scroll, 1)

        content = QWidget()
        content.setObjectName("imbPageContent")
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(16)

        # 1) DetailHeader
        self._header = LeeDetailHeader(
            title=tr("インバランス単価"),
            subtitle=tr("OCCTO リアルタイム · 系統需給差から算定"),
            accent=_C_IMB,
            icon_qicon=QIcon(":/img/won.svg"),
            badge="",
            show_export=True,
        )
        self._header.back_clicked.connect(lambda: bus.page_requested.emit(0))
        self._header.export_clicked.connect(self._export_csv)
        # 헤더 actions slot 에 ⚙ 임계값 버튼
        self._btn_threshold = LeeButton(tr("⚙ 閾値"), variant="ghost", size="sm")
        self._btn_threshold.clicked.connect(self._open_threshold_dialog)
        self._header.add_action(self._btn_threshold)
        root.addWidget(self._header)

        # 2) Filter row: SegSwitch (余剰/不足) + Date + Areas + Actions
        root.addWidget(self._build_filter_row())

        # 3) Area chips
        root.addWidget(self._build_area_chips())

        # 4) KPI strip (4 cards)
        kpi_row = QHBoxLayout(); kpi_row.setSpacing(12)
        self._kpi_latest = LeeKPI(tr("直近30分"),  value="--", unit=tr("円/kWh"), color=_C_IMB)
        self._kpi_avg    = LeeKPI(tr("本日平均"),  value="--", unit=tr("円/kWh"), sub=tr("基準価格"))
        self._kpi_peak   = LeeKPI(tr("ピーク"),    value="--", unit=tr("円/kWh"), color=_C_BAD)
        self._kpi_alert  = LeeKPI(tr("異常検出"),  value="0",  unit=tr("件"),     color=_C_WARN, sub=tr("急騰スロット"))
        kpi_row.addWidget(self._kpi_latest, 1)
        kpi_row.addWidget(self._kpi_avg, 1)
        kpi_row.addWidget(self._kpi_peak, 1)
        kpi_row.addWidget(self._kpi_alert, 1)
        root.addLayout(kpi_row)

        # 5) PivotTable
        self._pivot = LeePivotTable(
            mode="imb", accent=_C_IMB, height=320,
            show_stats=False, row_header_label=tr("時刻"),
        )
        self._pivot.setMinimumHeight(360)
        root.addWidget(self._pivot)

        # 6) Chart frame
        self._chart = _ImbMultiAreaChart()
        self._chart.setMinimumHeight(280)
        self._chart_frame = LeeChartFrame(
            tr("30分単位 インバランス単価"),
            subtitle="",
            accent=_C_IMB,
        )
        self._chart_frame.set_content(self._chart)
        self._chart_frame.setMinimumHeight(340)
        root.addWidget(self._chart_frame)
        # 첫 fetch 동안 차트 영역에 shimmer skeleton
        from app.ui.components.skeleton import install_skeleton_overlay
        self._chart_skel = install_skeleton_overlay(self._chart)

        # 7) 진행 상태 라벨
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0); bottom.setSpacing(10)
        self._refresh_indicator = QLabel("")
        self._refresh_indicator.setObjectName("imbRefreshIndicator")
        bottom.addWidget(self._refresh_indicator)
        self._status = QLabel(tr("待機中"))
        self._status.setObjectName("imbStatusLbl")
        self._status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bottom.addStretch()
        bottom.addWidget(self._status)
        root.addLayout(bottom)

        self._update_refresh_indicator()

    def _build_filter_row(self) -> QWidget:
        bar = QFrame(); bar.setObjectName("imbFilterBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0); h.setSpacing(10)

        # 余剰 / 不足 segment
        self._seg = LeeSegment(
            [("yojo", tr("余剰")), ("fusoku", tr("不足"))],
            value="yojo", accent=_C_IMB,
        )
        self._seg.value_changed.connect(self._on_seg_changed)
        h.addWidget(self._seg)

        h.addWidget(self._make_sep())

        # 날짜 선택
        self._date_input = LeeDateInput(accent=_C_IMB, show_today_btn=True)
        self._date_input.set_date(self._sel_date)
        self._date_input.date_changed.connect(self._on_date_changed)
        h.addWidget(self._date_input)

        h.addStretch()

        # 액션
        self._btn_update = LeeButton(tr("更新"), variant="secondary", size="sm")
        self._btn_update.clicked.connect(self.update_database)
        h.addWidget(self._btn_update)

        self._btn_copy = LeeButton(tr("📋 コピー"), variant="secondary", size="sm")
        self._btn_copy.clicked.connect(self._copy_table)
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

    def _build_area_chips(self) -> QWidget:
        wrap = QFrame(); wrap.setObjectName("imbChipsWrap")
        outer = QHBoxLayout(wrap)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(6)

        btn_all   = LeeButton(tr("全選択"), variant="ghost", size="sm")
        btn_clear = LeeButton(tr("クリア"), variant="ghost", size="sm")
        btn_all.clicked.connect(self._select_all_areas)
        btn_clear.clicked.connect(self._deselect_all_areas)
        outer.addWidget(btn_all)
        outer.addWidget(btn_clear)
        outer.addWidget(self._make_sep())

        chip_scroll = QScrollArea()
        chip_scroll.setObjectName("imbChipScroll")
        chip_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        chip_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        chip_scroll.setFrameShape(QFrame.NoFrame)
        chip_scroll.setWidgetResizable(True)

        chip_inner = QWidget()
        self._chip_layout = QHBoxLayout(chip_inner)
        self._chip_layout.setContentsMargins(0, 0, 0, 0)
        self._chip_layout.setSpacing(4)
        self._chip_layout.addStretch()
        chip_scroll.setWidget(chip_inner)
        chip_scroll.setFixedHeight(38)
        outer.addWidget(chip_scroll, 1)

        self._area_chips: dict[str, QPushButton] = {}
        self._chip_wrap = wrap
        self._apply_chip_qss()
        return wrap

    def _make_sep(self) -> QFrame:
        sep = QFrame(); sep.setObjectName("imbFilterSep")
        sep.setFixedSize(1, 22)
        return sep

    def _update_refresh_indicator(self) -> None:
        interval = int(self.settings.get("imbalance_interval", 5))
        self._refresh_indicator.setText(f"●  {interval}{tr('分ごと')}")

    # ──────────────────────────────────────────────────────────
    # 스타일
    # ──────────────────────────────────────────────────────────
    def _apply_page_qss(self) -> None:
        bg_app = "#0A0B0F" if self.is_dark else "#F5F6F8"
        self.setStyleSheet(f"""
            ImbalanceWidget {{ background: {bg_app}; }}
            QScrollArea#imbPageScroll {{ background: {bg_app}; border: none; }}
            QWidget#imbPageContent {{ background: {bg_app}; }}
        """)

    def _apply_filter_qss(self) -> None:
        is_dark = self.is_dark
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        sep_color    = "rgba(255,255,255,0.10)" if is_dark else "rgba(11,18,32,0.10)"
        self._filter_bar.setStyleSheet(f"""
            QFrame#imbFilterBar {{ background: transparent; }}
            QFrame#imbFilterSep {{ background: {sep_color}; border: none; }}
            QLabel#imbRefreshIndicator {{
                font-size: 11px; font-weight: 600;
                color: {_C_OK};
                background: rgba(48,209,88,0.10);
                border: 1px solid rgba(48,209,88,0.25);
                border-radius: 999px;
                padding: 3px 10px;
            }}
            QLabel#imbStatusLbl {{
                font-size: 11px; color: {fg_secondary};
                background: transparent; min-width: 60px;
            }}
        """)

    def _apply_chip_qss(self) -> None:
        is_dark = self.is_dark
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        bg_surface_2 = "#1B1E26" if is_dark else "#F0F2F5"
        border       = "rgba(255,255,255,0.08)" if is_dark else "rgba(11,18,32,0.10)"

        parts = [f"""
            QFrame#imbChipsWrap {{ background: transparent; }}
            QScrollArea#imbChipScroll {{ background: transparent; border: none; }}
            QPushButton#imbAreaChip {{
                background: {bg_surface_2};
                color: {fg_secondary};
                border: 1px solid {border};
                border-radius: 999px;
                padding: 4px 12px;
                font-size: 11px; font-weight: 700;
                min-height: 22px;
            }}
        """]
        for col, chip in self._area_chips.items():
            color = chip.property("areaColor") or _C_IMB
            r, g, b = self._hex_to_rgb(color)
            parts.append(f"""
                QPushButton#imbAreaChip[areaColor="{color}"]:checked {{
                    background: rgba({r},{g},{b},0.14);
                    color: {color};
                    border: 1px solid {color};
                }}
            """)
        self._chip_wrap.setStyleSheet("\n".join(parts))

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
        for k in (self._kpi_latest, self._kpi_avg, self._kpi_peak, self._kpi_alert):
            k.set_theme(d)
        self._date_input.set_theme(d)
        self._seg.set_theme(d)
        self._pivot.set_theme(d)
        self._chart_frame.set_theme(d)
        self._chart.set_theme(d)
        self._apply_page_qss()
        self._apply_filter_qss()
        self._apply_chip_qss()

    def apply_settings_custom(self) -> None:
        interval = int(self.settings.get("imbalance_interval", 5))
        self.update_timer_interval(interval)
        self._update_refresh_indicator()
        if self._last_rows:
            self._render_all()

    def set_loading(self, is_loading: bool) -> None:
        super().set_loading(is_loading, self._pivot)

    # ──────────────────────────────────────────────────────────
    # 컨트롤 핸들러
    # ──────────────────────────────────────────────────────────
    def _on_seg_changed(self, key: str) -> None:
        self._is_yojo = (key == "yojo")
        self._area_chips_built = False  # 컬럼 변경 → chips 재구성
        self._area_on.clear()
        self.display_data()

    def _on_date_changed(self, d: QDate) -> None:
        self._sel_date = d
        self.display_data()

    def _on_area_toggled(self, col: str, on: bool) -> None:
        self._area_on[col] = on
        self._render_chart()  # 차트만 재그리기 (테이블은 그대로)

    def _select_all_areas(self) -> None:
        for col, chip in self._area_chips.items():
            chip.blockSignals(True)
            chip.setChecked(True)
            self._area_on[col] = True
            chip.blockSignals(False)
            chip.style().unpolish(chip); chip.style().polish(chip)
        self._render_chart()

    def _deselect_all_areas(self) -> None:
        for col, chip in self._area_chips.items():
            chip.blockSignals(True)
            chip.setChecked(False)
            self._area_on[col] = False
            chip.blockSignals(False)
            chip.style().unpolish(chip); chip.style().polish(chip)
        self._render_chart()

    def _open_threshold_dialog(self) -> None:
        cur = float(self.settings.get("imbalance_alert", 40.0))
        dlg = _ThresholdDialog(cur, parent=self)
        if dlg.exec() == QDialog.Accepted:
            new_val = dlg.value()
            from app.core.config import save_settings
            try:
                # settings 파일 갱신 시도 — 실패시 내부 dict 만 갱신
                cfg = load_settings()
                cfg["imbalance_alert"] = new_val
                save_settings(cfg)
            except Exception as e:
                logger.warning(f"settings 저장 실패: {e}")
            self.settings["imbalance_alert"] = new_val
            bus.settings_saved.emit()
            if self._last_rows:
                self._render_all()

    # ──────────────────────────────────────────────────────────
    # 데이터 취득
    # ──────────────────────────────────────────────────────────
    def update_database(self) -> None:
        if not self.check_online_status():
            return
        try:
            if self.worker and self.worker.isRunning():
                return
        except RuntimeError:
            self.worker = None

        self._btn_update.setEnabled(False)
        self.set_loading(True)
        self._set_status(tr("DB更新中..."))
        self.worker = UpdateImbalanceWorker()
        self.worker.finished.connect(self._on_update_success)
        self.worker.error.connect(self._on_update_error)
        self.worker.progress.connect(self._on_update_progress)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()
        self.track_worker(self.worker)

    def _on_update_progress(self, msg: str) -> None:
        self._set_status(msg)

    def _on_update_success(self, msg: str) -> None:
        self._btn_update.setEnabled(True)
        self.set_loading(False)
        self._set_status(msg)
        self.display_data()
        bus.imbalance_updated.emit()
        # 토스트 — 메인 토스트 시스템 으로 라우팅 (burst 시 큐로 통합)
        bus.toast_requested.emit(msg, "success")

    def _on_update_error(self, err: str) -> None:
        self._btn_update.setEnabled(True)
        self.set_loading(False)
        self._set_status(tr("更新失敗: {0}").format(err))
        bus.toast_requested.emit(tr("⚠ インバランス 取得失敗"), "error")

    def display_data(self) -> None:
        target_date     = self._sel_date.toString("yyyy/MM/dd")
        target_yyyymmdd = int(self._sel_date.toString("yyyyMMdd"))

        try:
            if self._load_thread and self._load_thread.isRunning():
                return
        except RuntimeError:
            self._load_thread = None

        self.set_loading(True)
        self._set_status(tr("データ読込中..."))

        self._load_thread = QThread()
        self._load_task   = LoadImbalanceDataTask(target_date, target_yyyymmdd, self._is_yojo)
        self._load_task.moveToThread(self._load_thread)

        self._load_thread.started.connect(self._load_task.run)
        self._load_task.finished.connect(self._on_load_finished)
        self._load_task.no_data.connect(self._on_load_no_data)
        self._load_task.error.connect(self._on_load_error)

        for sig in (self._load_task.finished, self._load_task.no_data, self._load_task.error):
            sig.connect(self._load_thread.quit)
            sig.connect(self._load_task.deleteLater)
        self._load_thread.finished.connect(self._load_thread.deleteLater)

        self._load_thread.start()
        self.track_worker(self._load_thread)

    def _on_load_no_data(self, msg: str) -> None:
        self.set_loading(False)
        self._last_rows = []; self._last_cols = []
        self._pivot.set_data([], [])
        self._chart.clear_curves()
        self._update_kpis_empty()
        # 자동 호출 — 모달 X (status + 본문 빈 상태 표시로 충분)
        # 이전에는 LeeDialog.info 모달이 자동으로 떠 사용자 인터럽트 + 다중 호출 시 깜빡임
        self._set_status(tr("データなし: {0}").format(msg))

    def _on_load_error(self, err: str) -> None:
        self.set_loading(False)
        self._last_rows = []; self._last_cols = []
        self._pivot.set_data([], [])
        self._chart.clear_curves()
        self._set_status(tr("読込エラー"))
        logger.warning(f"インバランスDB読み込み失敗: {err}")

    def _on_load_finished(self, rows, target_cols, time_col, target_yyyymmdd) -> None:
        self.set_loading(False)
        self._last_rows     = rows
        self._last_cols     = target_cols
        self._last_time_col = time_col
        self._last_yyyymmdd = target_yyyymmdd

        # area chips 재구성 (컬럼 변경 시)
        self._rebuild_area_chips(target_cols)

        self._render_all()

        # 본일 데이터일 때만 알림 검사
        today_yyyymmdd = int(datetime.now().strftime("%Y%m%d"))
        if target_yyyymmdd == today_yyyymmdd:
            self._check_high_price_alerts(rows, target_cols, today_yyyymmdd)

        self._set_status(f"{self._sel_date.toString('yyyy/MM/dd')} {tr('更新完了')}")

    def _rebuild_area_chips(self, target_cols: list[str]) -> None:
        # 기존 칩 제거
        while self._chip_layout.count() > 0:
            item = self._chip_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self._area_chips.clear()

        for i, col in enumerate(target_cols):
            # 에리어명 추출 (예: "東京 余剰" → "東京")
            area_name = self._area_name_from_col(col)
            color = _AREA_COLORS.get(area_name, IMBALANCE_COLORS[i % len(IMBALANCE_COLORS)])
            chip = QPushButton(area_name)
            chip.setObjectName("imbAreaChip")
            chip.setCheckable(True)
            chip.setChecked(True)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setProperty("areaColor", color)
            chip.clicked.connect(lambda checked, c=col: self._on_area_toggled(c, checked))
            self._chip_layout.addWidget(chip)
            self._area_chips[col] = chip
            self._area_on[col] = True
        self._chip_layout.addStretch()
        self._apply_chip_qss()

    @staticmethod
    def _area_name_from_col(col: str) -> str:
        """'東京 余剰' / '東京 不足' → '東京' 등 area 이름만 추출."""
        s = col.strip()
        for suffix in ("余剰", "不足"):
            if s.endswith(suffix):
                s = s[: -len(suffix)].strip()
                break
        return s

    # ──────────────────────────────────────────────────────────
    # 렌더링
    # ──────────────────────────────────────────────────────────
    def _render_all(self) -> None:
        if not self._last_rows or not self._last_cols:
            return
        # 1) PivotTable
        self._render_pivot()
        # 2) Chart
        self._render_chart()
        # 3) KPIs
        self._update_kpis()
        # 4) Header badge
        self._update_header_badge()
        # 5) Chart subtitle
        self._chart_frame.set_subtitle(
            f"{self._sel_date.toString('yyyy/MM/dd')} · "
            f"{tr('選択中')} {sum(1 for v in self._area_on.values() if v)} "
            f"{tr('エリア')}"
        )

    def _render_pivot(self) -> None:
        # PivotTable 헤더: [시각, 에리어1, 에리어2, ...]
        headers = [tr("時刻")] + [self._area_name_from_col(c) for c in self._last_cols]
        # rows: [[time, val1, val2, ...]]
        display_rows: list[list] = []
        for row in self._last_rows:
            cells = [str(row[0])]
            for v in row[1:]:
                cells.append(f"{v:.2f}" if v is not None else "—")
            display_rows.append(cells)
        self._pivot.set_data(headers, display_rows)

    def _render_chart(self) -> None:
        self._chart.clear_curves()
        if not self._last_rows or not self._last_cols:
            return
        # 첫 데이터 도착 시 skeleton 제거
        if getattr(self, "_chart_skel", None) is not None:
            self._chart_skel.stop(); self._chart_skel.deleteLater(); self._chart_skel = None

        # X 축: 슬롯 라벨
        x_labels = [str(r[0]) for r in self._last_rows]
        x_vals   = list(range(len(x_labels)))

        step = max(1, math.ceil(len(x_labels) / 12))
        ticks = [
            [(x_vals[i], x_labels[i]) for i in range(0, len(x_labels), step)]
        ]
        self._chart.getAxis("bottom").setTicks(ticks)
        self._chart.set_x_label(tr("時刻"))
        self._chart.set_x_labels({float(i): x_labels[i] for i in range(len(x_labels))})

        # 임계값 가이드라인
        alert_val = float(self.settings.get("imbalance_alert", 40.0))
        self._chart.set_thresholds([
            (alert_val, _C_BAD),         # 急騰
            (alert_val * 0.5, _C_WARN),  # 注意
        ])

        # 활성 에리어 커브
        for i, col in enumerate(self._last_cols):
            if not self._area_on.get(col, True):
                continue
            area_name = self._area_name_from_col(col)
            color = _AREA_COLORS.get(area_name, IMBALANCE_COLORS[i % len(IMBALANCE_COLORS)])
            y_vals = [
                (row[i + 1] if (i + 1) < len(row) and row[i + 1] is not None else float("nan"))
                for row in self._last_rows
            ]
            self._chart.add_curve(x_vals, y_vals, name=area_name, color=color)

        self._chart.fit_view()

    def _update_kpis(self) -> None:
        # 모든 가격 모음
        all_prices: list[float] = []
        latest_price = None
        latest_slot = ""
        peak = None; peak_slot = ""; peak_area = ""
        for row in self._last_rows:
            slot = str(row[0])
            slot_max = None
            for ci, col in enumerate(self._last_cols, 1):
                v = row[ci] if ci < len(row) else None
                if v is None:
                    continue
                all_prices.append(float(v))
                if slot_max is None or v > slot_max:
                    slot_max = v
                if peak is None or v > peak:
                    peak = v; peak_slot = slot; peak_area = self._area_name_from_col(col)
            if slot_max is not None:
                latest_price = slot_max
                latest_slot = slot

        if not all_prices:
            self._update_kpis_empty(); return

        avg = sum(all_prices) / len(all_prices)
        alert_val = float(self.settings.get("imbalance_alert", 40.0))
        n_alerts = sum(1 for p in all_prices if p >= alert_val)

        self._kpi_latest.set_value(
            f"{latest_price:.2f}" if latest_price is not None else "--",
            unit=tr("円/kWh"), color=self._color_for(latest_price, alert_val),
            sub=tr("コマ {0}").format(latest_slot) if latest_slot else "",
        )
        self._kpi_avg.set_value(
            f"{avg:.2f}", unit=tr("円/kWh"),
            sub=tr("基準価格 {0:.0f}円").format(alert_val * 0.5),
        )
        if peak is not None:
            self._kpi_peak.set_value(
                f"{peak:.2f}", unit=tr("円/kWh"),
                color=self._color_for(peak, alert_val),
                sub=f"{peak_slot} · {peak_area}",
            )
        self._kpi_alert.set_value(
            f"{n_alerts}", unit=tr("件"),
            color=_C_BAD if n_alerts > 0 else _C_OK,
            sub=tr("閾値 {0:.0f}円超").format(alert_val),
        )

    def _update_kpis_empty(self) -> None:
        for k in (self._kpi_latest, self._kpi_avg, self._kpi_peak):
            k.set_value("--", unit=tr("円/kWh"), sub="")
        self._kpi_alert.set_value("0", unit=tr("件"), sub="")

    @staticmethod
    def _color_for(val: Optional[float], alert: float) -> str:
        if val is None:
            return _C_IMB
        if val >= alert:
            return _C_BAD
        if val >= alert * 0.5:
            return _C_WARN
        return _C_IMB

    def _update_header_badge(self) -> None:
        # 본일 데이터일 때 알림 개수 표시
        today_yyyymmdd = int(datetime.now().strftime("%Y%m%d"))
        if self._last_yyyymmdd != today_yyyymmdd:
            self._header.set_badge(None); return

        alert_val = float(self.settings.get("imbalance_alert", 40.0))
        n_alerts = 0
        for row in self._last_rows:
            for ci in range(1, len(self._last_cols) + 1):
                v = row[ci] if ci < len(row) else None
                if v is not None and v >= alert_val:
                    n_alerts += 1
        if n_alerts > 0:
            self._header.set_badge(tr("⚠ 警戒 ({0}件)").format(n_alerts))
        else:
            self._header.set_badge(None)

    # ──────────────────────────────────────────────────────────
    # 알림 검출 (본일 데이터)
    # ──────────────────────────────────────────────────────────
    def _check_high_price_alerts(self, rows, target_cols, today_yyyymmdd: int) -> None:
        if not rows: return
        new_alerts = []
        alert_val  = float(self.settings.get("imbalance_alert", 40.0))

        for row in rows:
            slot = str(row[0])
            for i, col in enumerate(target_cols, start=1):
                val = row[i]
                if val is not None and val >= alert_val:
                    key = (today_yyyymmdd, slot, col)
                    if key not in self._alerted_high_prices:
                        self._alerted_high_prices.add(key)
                        new_alerts.append((slot, col, float(val)))

        if not new_alerts:
            return

        display = new_alerts[:5]
        lines = "\n".join(
            f"  {tr('コマ')} {s}  |  {tr(self._area_name_from_col(a))}:  {v:,.1f} {tr('円')}"
            for s, a, v in display
        )
        if len(new_alerts) > 5:
            lines += "\n  " + tr("...他 {0}件の警告があります").format(len(new_alerts) - 5)

        timestamp = datetime.now().strftime("%H:%M:%S")
        total = len(new_alerts)
        prefix = tr("本日データに{0}円超の単価が 【計 {1}件】 発生しました。").format(alert_val, total)
        plain = prefix + f"\n\n{lines}"
        title = tr("⚠ インバランス 警告 (計 {0}件) - {1}").format(total, timestamp)

        main_window = next(
            (w for w in QApplication.topLevelWidgets() if w.inherits("QMainWindow")), None
        )
        if main_window and hasattr(main_window, "add_notification"):
            main_window.add_notification(title, plain)
        # 트레이 balloon — 메인 윈도우가 숨겨진 경우 + cooldown 통과 시만
        if (main_window and main_window.isHidden()
                and hasattr(main_window, "tray_icon")
                and getattr(main_window, "_can_show_tray_balloon", lambda: True)()):
            main_window.tray_icon.showMessage(
                title, plain, QApplication.instance().windowIcon(), 10000,
            )

    # ──────────────────────────────────────────────────────────
    # CSV / 코피
    # ──────────────────────────────────────────────────────────
    def _copy_table(self) -> None:
        if not self._last_rows or not self._last_cols:
            bus.toast_requested.emit(tr("コピー可能なデータがありません"), "warning")
            return
        headers = [self._last_time_col] + [self._area_name_from_col(c) for c in self._last_cols]
        lines = ["\t".join(headers)]
        for row in self._last_rows:
            cells = [str(row[0])]
            for v in row[1:]:
                cells.append(f"{v:.2f}" if v is not None else "—")
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))
        bus.toast_requested.emit(tr("テーブルをコピーしました"), "success")

    def _export_csv(self) -> None:
        if not self._last_rows:
            LeeDialog.error(tr("エラー"), tr("保存するデータがありません。"), parent=self)
            return
        date_str = self._sel_date.toString("yyyyMMdd")
        kind = "yojo" if self._is_yojo else "fusoku"
        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("CSV保存"),
            f"imbalance_{kind}_{date_str}.csv",
            "CSV Files (*.csv)",
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                headers = [self._last_time_col] + list(self._last_cols)
                writer.writerow(headers)
                for row in self._last_rows:
                    writer.writerow([row[0]] + [
                        (f"{v:.2f}" if isinstance(v, (int, float)) else "")
                        for v in row[1:]
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
