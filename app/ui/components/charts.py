"""Phase 1 atom — 차트 / 표 / 비교 바 컴포넌트.

이 파일에 포함된 컴포넌트:
    - LeeBigChart    : 24h SVG-style 라인 차트 + crosshair + 영역 fill + draw 애니메이션
    - LeePivotTable  : 30분 × 에리어 매트릭스 (컬러 셀 + row/col 호버 + 카피)
    - LeeReserveBars : 가로 비교 막대 (라벨 + 막대 + 값 + threshold 마커)

디자인 출처:
    - varA-detail-atoms.jsx (BigChart)
    - varA-pivot.jsx (PivotTable, priceColor)
    - varA-detail-screens2.jsx (ReserveBars)
"""
from __future__ import annotations

from typing import Optional, Callable, Literal

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal, QTimer, QEvent
from PySide6.QtGui import QColor, QPen, QBrush
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QSizePolicy, QStyledItemDelegate, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)


# ── 행/열 hover crosshair delegate (LeePivotTable 용) ────────────────
class _PivotCrosshairDelegate(QStyledItemDelegate):
    """현재 호버 row/col 과 일치하는 셀에 accent 오버레이를 덧칠."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hover_row = -1
        self.hover_col = -1
        self.overlay_color = QColor(255, 122, 69, 28)   # accent 11%

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if index.row() == self.hover_row or index.column() == self.hover_col:
            painter.save()
            painter.fillRect(option.rect, self.overlay_color)
            painter.restore()


# ──────────────────────────────────────────────────────────────────────
# 컬러 스케일 (varA-pivot.jsx 의 priceColor 와 동일)
# ──────────────────────────────────────────────────────────────────────
PivotMode = Literal["spot", "imb", "reserve"]


def price_color(value: Optional[float], mode: PivotMode = "spot") -> Optional[tuple[str, str]]:
    """value → (bg, fg) tuple. None 이면 기본색."""
    if value is None:
        return None
    if mode == "spot":
        if value < 5:   return ("rgba(52,168,83,0.18)",  "#0b8043")
        if value < 10:  return ("rgba(251,188,5,0.16)",  "#a87100")
        if value < 15:  return ("rgba(255,109,0,0.18)",  "#bf4f00")
        if value < 25:  return ("rgba(234,67,53,0.18)",  "#c5221f")
        return                ("rgba(213,0,0,0.25)",     "#9b0000")
    if mode == "imb":
        if value < 0:   return ("rgba(52,168,83,0.16)",  "#0b8043")
        if value < 8:   return ("rgba(251,188,5,0.14)",  "#a87100")
        if value < 16:  return ("rgba(255,109,0,0.18)",  "#bf4f00")
        return                ("rgba(234,67,53,0.22)",   "#c5221f")
    if mode == "reserve":
        # 낮을수록 위험
        if value < 3:   return ("rgba(213,0,0,0.25)",    "#9b0000")
        if value < 8:   return ("rgba(234,67,53,0.18)",  "#c5221f")
        if value < 15:  return ("rgba(255,109,0,0.18)",  "#bf4f00")
        if value < 25:  return ("rgba(251,188,5,0.14)",  "#a87100")
        return                ("rgba(52,168,83,0.18)",   "#0b8043")
    return None


# ──────────────────────────────────────────────────────────────────────
# 1. LeeBigChart — 24h SVG 라인 차트 + crosshair + 영역 fill
# ──────────────────────────────────────────────────────────────────────
class LeeBigChart(pg.PlotWidget):
    """24h 라인 차트 (라인 + 영역 + crosshair + 호버 dot/label).

    Parameters
    ----------
    color : str
        라인 컬러
    y_unit : str
        Y축 라벨 (예: "%", "USD/MMBtu")
    x_label : str
        X축 라벨 (기본 "時刻")
    guide_lines : list[tuple[float, str]]
        가로 가이드라인 [(value, color), ...]
    """

    def __init__(
        self,
        *,
        color: str = "#5B8DEF",
        y_unit: str = "",
        x_label: str = "時刻",
        guide_lines: Optional[list[tuple[float, str]]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._is_dark = True
        self._color = color
        self._y_unit = y_unit
        self._x_label = x_label
        self._x_data: list[float] = []
        self._y_data: list[float] = []
        self._curve = None

        self.setMenuEnabled(False)
        self.getPlotItem().hideButtons()
        self.showGrid(x=True, y=True, alpha=0.15)
        self.plotItem.hideAxis('top')
        self.plotItem.hideAxis('right')

        # X 축: 0~1440 분 (4시간 단위 라벨)
        ax_x = self.getAxis('bottom')
        ax_x.setTicks([
            [(t * 60, f"{t:02d}:00") for t in (0, 4, 8, 12, 16, 20, 24)],
        ])
        self.setXRange(0, 1440, padding=0.02)

        # Guide lines
        if guide_lines:
            for level, gcolor in guide_lines:
                line = pg.InfiniteLine(
                    pos=level, angle=0,
                    pen=pg.mkPen(QColor(gcolor), width=1, style=Qt.DashLine),
                )
                line.setZValue(-10)
                self.addItem(line)

        # Crosshair items
        self._vline = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen(color, width=1, style=Qt.DashLine),
        )
        self._vline.setVisible(False)
        self.addItem(self._vline, ignoreBounds=True)

        # hover dot fill: 다크 모드는 흰색, 라이트 모드는 surface (대비 유지)
        self._hover_dot = pg.ScatterPlotItem(
            size=10, pen=pg.mkPen(color, width=2),
            brush=pg.mkBrush(255, 255, 255, 230),
        )
        self._hover_dot.setVisible(False)
        self.addItem(self._hover_dot, ignoreBounds=True)
        # 초기 brush 는 다크 기준 — apply_theme() 에서 라이트일 때 교체

        self._hover_label = pg.TextItem("", anchor=(0, 1), color=color)
        self._hover_label.setVisible(False)
        self.addItem(self._hover_label, ignoreBounds=True)

        self._proxy = pg.SignalProxy(
            self.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved
        )

        self.apply_theme()

    # ── 외부 API ─────────────────────────────────────────────
    def set_data(self, x_minutes: list[float], y_values: list[float]) -> None:
        if self._curve is not None:
            self.removeItem(self._curve)
            self._curve = None
        self._x_data = list(x_minutes)
        self._y_data = list(y_values)
        self._vline.setVisible(False)
        self._hover_dot.setVisible(False)
        self._hover_label.setVisible(False)
        if not x_minutes or not y_values:
            return
        c = QColor(self._color)
        self._curve = self.plot(
            x_minutes, y_values,
            pen=pg.mkPen(self._color, width=2),
            fillLevel=0,
            brush=pg.mkBrush(c.red(), c.green(), c.blue(), 50 if self._is_dark else 90),
        )
        if y_values:
            ymax = max(y_values) * 1.1
            ymin = min(y_values) * 0.9
            if ymax - ymin < 1:
                ymax = ymin + 1
            self.setYRange(max(0, ymin), max(ymax, 30 if self._y_unit == "%" else ymax), padding=0)

    def set_color(self, color: str) -> None:
        self._color = color

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self.apply_theme()
        if self._curve is not None:
            c = QColor(self._color)
            try:
                self._curve.setFillBrush(
                    pg.mkBrush(c.red(), c.green(), c.blue(), 50 if is_dark else 90)
                )
            except AttributeError:
                pass

    def apply_theme(self) -> None:
        is_dark = self._is_dark
        bg     = "#14161C" if is_dark else "#FFFFFF"
        axis_c = "#3D424D" if is_dark else "#C2C8D2"
        text_c = "#A8B0BD" if is_dark else "#4A5567"
        self.setBackground(bg)
        ax_pen   = pg.mkPen(color=axis_c, width=1, style=Qt.DashLine)
        text_pen = pg.mkPen(text_c)
        # hover dot fill: 라이트모드에서는 짙은 색으로 대비 유지
        if hasattr(self, "_hover_dot") and self._hover_dot is not None:
            if is_dark:
                self._hover_dot.setBrush(pg.mkBrush(255, 255, 255, 230))
            else:
                self._hover_dot.setBrush(pg.mkBrush(11, 18, 32, 230))
        for ax_name in ('left', 'bottom'):
            ax = self.getAxis(ax_name)
            ax.setPen(ax_pen)
            ax.setTextPen(text_pen)
        if self._y_unit:
            self.setLabel('left', self._y_unit, color=text_c, size="9pt")
        self.setLabel('bottom', self._x_label, color=text_c, size="9pt")

    # ── 호버 핸들러 ──────────────────────────────────────────
    def _on_mouse_moved(self, evt) -> None:
        if not self._x_data:
            return
        pos = evt[0]
        if not self.sceneBoundingRect().contains(pos):
            self._vline.setVisible(False)
            self._hover_dot.setVisible(False)
            self._hover_label.setVisible(False)
            return
        view_pt = self.plotItem.vb.mapSceneToView(pos)
        x_target = view_pt.x()
        idx = min(range(len(self._x_data)), key=lambda i: abs(self._x_data[i] - x_target))
        x_at = self._x_data[idx]
        y_at = self._y_data[idx]
        self._vline.setPos(x_at)
        self._vline.setVisible(True)
        self._hover_dot.setData([x_at], [y_at])
        self._hover_dot.setVisible(True)
        # 시간 라벨 (X 가 분 단위라면)
        if self._x_label.startswith("時") or self._x_label == "":
            h = int(x_at // 60); m = int(x_at % 60)
            x_str = f"{h:02d}:{m:02d}"
        else:
            x_str = f"{x_at:.1f}"
        unit = self._y_unit or ""
        self._hover_label.setText(f"  {x_str}\n  {y_at:.2f} {unit}")
        self._hover_label.setPos(x_at, y_at)
        self._hover_label.setVisible(True)

    def leaveEvent(self, event) -> None:
        self._vline.setVisible(False)
        self._hover_dot.setVisible(False)
        self._hover_label.setVisible(False)
        super().leaveEvent(event)


# ──────────────────────────────────────────────────────────────────────
# 2. LeePivotTable — 30분 × 에리어 매트릭스 + 컬러 셀 + 호버
# ──────────────────────────────────────────────────────────────────────
class LeePivotTable(QFrame):
    """행 (시간/날짜) × 열 (에리어/지표) 의 컬러 코드 매트릭스 표.

    Parameters
    ----------
    mode : "spot" | "imb" | "reserve"
        priceColor 모드 (셀 컬러 결정)
    accent : str
        헤더 컬러바 액센트
    height : int
        표 본문 영역 최대 높이
    show_stats : bool
        하단에 평균/최고/최저 stats 행 표시 여부
    row_header_label : str
        좌측 헤더 텍스트 (기본 "時刻")
    """

    AREA_COLORS = {
        "北海道": "#4285F4", "東北": "#EA4335", "東京": "#FBBC05", "中部": "#34A853",
        "北陸": "#FF6D00", "関西": "#7986CB", "中国": "#E67C73", "四国": "#0B8043",
        "九州": "#8E24AA", "沖縄": "#D50000",
    }

    copy_clicked = Signal()

    def __init__(
        self,
        *,
        mode: PivotMode = "spot",
        accent: str = "#FF7A45",
        height: int = 360,
        show_stats: bool = False,
        row_header_label: str = "時刻",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("leePivotTable")
        self._is_dark = True
        self._mode = mode
        self._accent = accent
        self._show_stats = show_stats
        self._row_header_label = row_header_label
        self._headers: list[str] = []
        self._rows: list[list[str]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header bar
        header = QFrame()
        header.setObjectName("pivotHeader")
        h = QHBoxLayout(header)
        h.setContentsMargins(16, 12, 12, 12)
        h.setSpacing(10)

        title = QLabel("30分単位 × エリア別 一覧")
        title.setObjectName("pivotHeaderTitle")
        h.addWidget(title); h.addStretch()

        # 컬러 범례
        legend_lbl = QLabel("単価別カラー")
        legend_lbl.setObjectName("pivotLegendLbl")
        h.addWidget(legend_lbl)

        legend_box = QHBoxLayout(); legend_box.setSpacing(3)
        for v in [2, 7, 12, 20, 30]:
            sw = QFrame(); sw.setFixedSize(22, 14); sw.setObjectName("pivotLegendSwatch")
            c = price_color(float(v), mode)
            if c is not None:
                sw.setStyleSheet(
                    f"QFrame#pivotLegendSwatch {{ background: {c[0]}; border: 1px solid {c[1]}33; border-radius: 3px; }}"
                )
            legend_box.addWidget(sw)
        h.addLayout(legend_box)

        copy_btn = QPushButton("コピー")
        copy_btn.setObjectName("pivotCopyBtn")
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.clicked.connect(self._on_copy)
        h.addWidget(copy_btn)

        outer.addWidget(header)

        # Table
        self._table = QTableWidget()
        self._table.setObjectName("pivotTable")
        # height 는 minimumHeight 로 적용 — 외부 splitter 가 동적 조정 가능
        self._table.setMinimumHeight(min(height, 160))
        self._table.setShowGrid(False)
        self._table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self._table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        self._table.setSelectionMode(QTableWidget.NoSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setHighlightSections(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # row/col hover crosshair
        self._table.setMouseTracking(True)
        self._table.viewport().setMouseTracking(True)
        self._crosshair = _PivotCrosshairDelegate(self._table)
        self._table.setItemDelegate(self._crosshair)
        self._table.cellEntered.connect(self._on_cell_hovered)
        self._table.viewport().installEventFilter(self)
        outer.addWidget(self._table)

        self._apply_qss()

    def _on_cell_hovered(self, row: int, col: int) -> None:
        if row == self._crosshair.hover_row and col == self._crosshair.hover_col:
            return
        self._crosshair.hover_row = row
        self._crosshair.hover_col = col
        self._table.viewport().update()

    def eventFilter(self, obj, ev):
        if obj is self._table.viewport() and ev.type() == QEvent.Leave:
            if self._crosshair.hover_row != -1 or self._crosshair.hover_col != -1:
                self._crosshair.hover_row = -1
                self._crosshair.hover_col = -1
                self._table.viewport().update()
        return super().eventFilter(obj, ev)

    # ── 외부 API ─────────────────────────────────────────────
    def set_data(
        self,
        headers: list[str],
        rows: list[list[str]],
    ) -> None:
        """headers: ["時刻", "北海道", "東北", ...] / rows: [[time, v1, v2, ...], ...]"""
        self._headers = headers
        self._rows = rows
        self._table.clear()
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels([self._row_header_label if i == 0 else h for i, h in enumerate(headers)])
        self._table.setRowCount(len(rows))

        # 헤더 색상 바 (각 에리어별)
        for col, name in enumerate(headers):
            if col == 0:
                continue
            color = self.AREA_COLORS.get(name, self._accent)
            it = self._table.horizontalHeaderItem(col)
            if it is not None:
                it.setForeground(QColor(color))
        # 헤더 col 0
        if self._table.horizontalHeaderItem(0) is not None:
            self._table.horizontalHeaderItem(0).setText(self._row_header_label)

        # 데이터 셀 채우기
        for ri, row_data in enumerate(rows):
            for ci, cell in enumerate(row_data):
                item = QTableWidgetItem(str(cell))
                item.setTextAlignment(Qt.AlignCenter)
                if ci == 0:
                    # 시간 컬럼: mono, fg-secondary
                    item.setForeground(QColor("#A8B0BD" if self._is_dark else "#4A5567"))
                    f = item.font(); f.setBold(ri % 4 == 0); item.setFont(f)
                else:
                    val = self._parse_value(cell)
                    c = price_color(val, self._mode)
                    if c is not None:
                        item.setBackground(QColor(c[0].replace("rgba(", "rgba(").replace(")", ")"))) \
                            if False else None
                        # QTableWidgetItem 은 rgba 직접 안 받음 → setData 로 처리하거나 setBackground(QBrush(QColor))
                        bg_qc = self._rgba_to_qcolor(c[0])
                        item.setBackground(QBrush(bg_qc))
                        item.setForeground(QColor(c[1]))
                        f = item.font(); f.setBold(True); item.setFont(f)
                self._table.setItem(ri, ci, item)

        # 첫 컬럼 (시간) 폭 좁게
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setMinimumSectionSize(64)

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()
        # 셀 색상 재적용
        if self._headers and self._rows:
            self.set_data(self._headers, self._rows)

    # ── 내부 ─────────────────────────────────────────────────
    def _parse_value(self, cell: str) -> Optional[float]:
        try:
            return float(str(cell).replace('%', '').replace(',', '').strip())
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _rgba_to_qcolor(rgba_str: str) -> QColor:
        """rgba(r,g,b,a) 형태 문자열 → QColor."""
        try:
            inner = rgba_str.replace("rgba(", "").rstrip(")").strip()
            parts = [p.strip() for p in inner.split(",")]
            r = int(parts[0]); g = int(parts[1]); b = int(parts[2])
            a = int(round(float(parts[3]) * 255)) if len(parts) > 3 else 255
            return QColor(r, g, b, a)
        except Exception:
            return QColor(0, 0, 0, 0)

    def _on_copy(self) -> None:
        if not self._rows:
            return
        lines = ["\t".join(self._headers)]
        for r in self._rows:
            lines.append("\t".join(str(c) for c in r))
        QApplication.clipboard().setText("\n".join(lines))
        self.copy_clicked.emit()
        try:
            from app.core.events import bus
            bus.toast_requested.emit("テーブルをコピーしました", "success")
        except Exception:
            pass

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        bg_surface   = "#14161C" if is_dark else "#FFFFFF"
        bg_surface_2 = "#1B1E26" if is_dark else "#F0F2F5"
        bg_surface_3 = "#232730" if is_dark else "#E6E9EE"
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        border_subtle= "rgba(255,255,255,0.04)" if is_dark else "rgba(11,18,32,0.06)"
        self.setStyleSheet(f"""
            QFrame#leePivotTable {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 18px;
            }}
            QFrame#pivotHeader {{
                background: transparent;
                border-bottom: 1px solid {border_subtle};
            }}
            QLabel#pivotHeaderTitle {{
                font-size: 13px; font-weight: 700;
                color: {fg_primary};
                background: transparent;
            }}
            QLabel#pivotLegendLbl {{
                font-size: 11px;
                color: {fg_tertiary};
                background: transparent;
            }}
            QPushButton#pivotCopyBtn {{
                background: {bg_surface_2};
                color: {fg_secondary};
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 10px;
                padding: 5px 12px;
                font-size: 11px; font-weight: 600;
            }}
            QPushButton#pivotCopyBtn:hover {{
                color: {fg_primary};
            }}
            QTableWidget#pivotTable {{
                background: {bg_surface};
                color: {fg_primary};
                border: none;
                gridline-color: transparent;
                font-size: 11px;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QHeaderView::section {{
                background: {bg_surface_2};
                color: {fg_secondary};
                font-size: 11px; font-weight: 700;
                border: none;
                border-bottom: 1px solid {border_subtle};
                padding: 8px 6px;
            }}
            QTableWidget#pivotTable::item {{
                padding: 5px 6px;
                border-bottom: 1px solid {border_subtle};
            }}
            QTableWidget#pivotTable::item:hover {{
                background: {bg_surface_3};
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# 3. LeeReserveBars — 가로 비교 바 (라벨 + 막대 + 값 + threshold 마커)
# ──────────────────────────────────────────────────────────────────────
class LeeReserveBars(QFrame):
    """가로 비교 바 차트 (예: 10에리어 예비율 비교).

    rows: [(label, value, status), ...]
        status: "ok" | "warn" | "bad" | None
    """

    def __init__(
        self,
        *,
        max_value: float = 25.0,
        thresholds: Optional[list[tuple[float, str]]] = None,
        large: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("leeReserveBars")
        self._is_dark = True
        self._max_value = max_value
        self._thresholds = thresholds or [(8.0, "#FF9F0A"), (3.0, "#FF453A")]
        self._large = large
        self._rows: list[tuple[str, float, Optional[str]]] = []

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(14 if large else 10)

        self._apply_qss()

    # ── 외부 API ─────────────────────────────────────────────
    def set_data(self, rows: list[tuple[str, float, Optional[str]]]) -> None:
        self._rows = list(rows)
        # 기존 자식 제거
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        for label, value, status in self._rows:
            self._layout.addWidget(self._build_row(label, value, status))
        self._layout.addStretch(1)

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()
        if self._rows:
            self.set_data(self._rows)

    # ── 내부 ─────────────────────────────────────────────────
    def _color_for(self, status: Optional[str]) -> str:
        if status == "bad":
            return "#FF453A"
        if status == "warn":
            return "#FF9F0A"
        return "#5B8DEF"  # c-power (ok)

    def _build_row(self, label: str, value: float, status: Optional[str]) -> QWidget:
        large = self._large
        row = QWidget(); row.setObjectName("rsBarRow")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)

        lbl = QLabel(label); lbl.setObjectName("rsBarLabel")
        lbl.setFixedWidth(80 if large else 56)
        h.addWidget(lbl)

        color = self._color_for(status)

        # 막대 (QPainter 직접 그리기)
        custom_track = _BarTrack(
            value=value, max_value=self._max_value,
            color=color, thresholds=self._thresholds,
            track_color=("rgba(255,255,255,0.06)" if self._is_dark else "rgba(11,18,32,0.08)"),
            height=22 if large else 14,
        )
        h.addWidget(custom_track, 1)

        val_lbl = QLabel(f"{value:.1f}"); val_lbl.setObjectName("rsBarValue")
        val_lbl.setFixedWidth(70 if large else 56)
        val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        val_lbl.setStyleSheet(
            f"QLabel#rsBarValue {{ color: {color}; font-family: 'JetBrains Mono', monospace; "
            f"font-size: {14 if large else 12}px; font-weight: 700; background: transparent; }}"
        )
        h.addWidget(val_lbl)
        return row

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        self.setStyleSheet(f"""
            QFrame#leeReserveBars {{
                background: transparent;
            }}
            QLabel#rsBarLabel {{
                font-size: {14 if self._large else 12}px;
                font-weight: 600;
                color: {fg_primary};
                background: transparent;
            }}
        """)


class _BarTrack(QWidget):
    """LeeReserveBars 내부의 trakc + fill + threshold 마커 (QPainter)."""

    def __init__(
        self,
        *,
        value: float,
        max_value: float,
        color: str,
        thresholds: list[tuple[float, str]],
        track_color: str,
        height: int = 14,
        parent=None,
    ):
        super().__init__(parent)
        self._value = value
        self._max_value = max_value
        self._color = color
        self._thresholds = thresholds
        self._track_color = track_color
        self.setFixedHeight(height + 4)  # threshold 마커 여유
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # 부모 카드 배경을 그대로 노출 (paintEvent 가 background 그리지 않음)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QColor, QBrush
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height() - 4  # bar 영역
        track_top = 2

        # Track
        p.setPen(Qt.NoPen)
        track_qc = self._rgba_to_qcolor(self._track_color)
        p.setBrush(QBrush(track_qc))
        p.drawRoundedRect(0, track_top, w, h, h / 2, h / 2)

        # Fill
        if self._max_value > 0:
            pct = max(0.0, min(1.0, self._value / self._max_value))
            fw = int(w * pct)
            if fw > 0:
                p.setBrush(QBrush(QColor(self._color)))
                p.drawRoundedRect(0, track_top, fw, h, h / 2, h / 2)

        # Thresholds
        for th_v, th_c in self._thresholds:
            if self._max_value > 0:
                tx = int(w * (th_v / self._max_value))
                p.setPen(QColor(th_c))
                # 위/아래로 살짝 튀어나오게
                p.drawLine(tx, 0, tx, h + 4)
        p.end()

    @staticmethod
    def _rgba_to_qcolor(rgba_str: str) -> QColor:
        try:
            if rgba_str.startswith("#"):
                return QColor(rgba_str)
            inner = rgba_str.replace("rgba(", "").rstrip(")").strip()
            parts = [p.strip() for p in inner.split(",")]
            r = int(parts[0]); g = int(parts[1]); b = int(parts[2])
            a = int(round(float(parts[3]) * 255)) if len(parts) > 3 else 255
            return QColor(r, g, b, a)
        except Exception:
            return QColor(80, 80, 80, 80)
