"""
JEPX スポット市場価格ウィジェット

表示モード:
  1. 当日スポット価格    — 指定日の 48 コマ価格
  2. 日次平均推移        — 指定期間の日平均
  3. 月次平均推移        — 指定会計年度範囲の月平均
  4. 年次平均推移        — DB 全期間の年平均
  5. 曜日別日次推移      — 指定期間・指定曜日に該当する各日の日平均

スケジュール:
  - 起動時 → 不足暦年を一括ダウンロード (FetchJepxSpotHistoryWorker)
  - 毎日 10:00〜10:30 → 3 分ごとポーリング (FetchJepxSpotTodayWorker)
"""
import logging
import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QDate, QTime, QTimer, QPoint, QThread, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QSplitter, QDateEdit, QFrame,
    QHeaderView, QTableWidgetItem, QProgressBar, QApplication, QToolTip,
    QScrollArea,
)

from app.api.market.jepx_spot import (
    FetchJepxSpotHistoryWorker, FetchJepxSpotTodayWorker,
    current_fiscal_year, fiscal_year_range,
)
from app.core.config import DB_JEPX_SPOT, JEPX_SPOT_AREAS, JEPX_SPOT_START_FY, load_settings
from app.core.database import get_db_connection, ensure_index, validate_column_name
from app.core.events import bus
from app.core.i18n import tr
from app.ui.common import BaseWidget, ExcelCopyTableWidget
from app.ui.theme import UIColors, Typography

pg.setConfigOptions(antialias=True)
logger = logging.getLogger(__name__)

# ── 定数 ──────────────────────────────────────────────────────────────────────

_MODES = [
    ("当日スポット価格",      "daily"),
    ("日次平均推移",          "daily_avg"),
    ("月次平均推移",          "monthly_avg"),
    ("年次平均推移",          "yearly_avg"),
    ("曜日別日次推移",        "weekday_avg"),
]

_WEEKDAY_OPTIONS = [
    ("月曜日", 1), ("火曜日", 2), ("水曜日", 3), ("木曜日", 4),
    ("金曜日", 5), ("土曜日", 6), ("日曜日", 0),
]

_AREA_COLORS = [
    "#4285F4", "#EA4335", "#FBBC05", "#34A853",
    "#FF6D00", "#7986CB", "#E67C73", "#0B8043",
    "#8E24AA", "#D50000",
]

_LEFT_AXIS_W = 60


# ── チャートウィジェット ───────────────────────────────────────────────────────

class _SpotChart(pg.PlotWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_dark = True
        self.showGrid(x=True, y=True, alpha=0.2)
        self.plotItem.hideAxis("top")
        self.plotItem.hideAxis("right")
        self.getAxis("left").setWidth(_LEFT_AXIS_W)
        self._legend = self.addLegend(offset=(10, 10))
        self._curves: list[pg.PlotDataItem]  = []
        self._colors: list[str]              = []

        self.plotItem.vb.disableAutoRange()

        self._vline = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen("#888888", width=1, style=Qt.DashLine),
        )
        self.addItem(self._vline)
        self._vline.setZValue(50)

        # 全カーブ共用のトラッカードット (1つの ScatterPlotItem で管理)
        self._tracker = pg.ScatterPlotItem()
        self._tracker.setZValue(100)
        self.addItem(self._tracker)

        # rateLimit を上げて追従性を向上
        self._proxy = pg.SignalProxy(
            self.scene().sigMouseMoved, rateLimit=120, slot=self._on_mouse
        )
        self._x_to_label: dict[float, str] = {}
        self._apply_colors()

    # ── 外観 ─────────────────────────────────────────────────────────────────

    def _apply_colors(self):
        bg = "#1e1e1e" if self.is_dark else "#ffffff"
        self.setBackground(bg)
        ax = pg.mkPen("#555555" if self.is_dark else "#dddddd", width=1)
        tc = UIColors.TEXT_SECONDARY_DARK if self.is_dark else UIColors.TEXT_SECONDARY_LIGHT
        for name in ("left", "bottom"):
            a = self.getAxis(name)
            a.setPen(ax)
            a.setTextPen(pg.mkPen(tc))
        self.setLabel("left", tr("価格 (円/kWh)"), color=tc, size=Typography.CHART)

    def set_theme(self, is_dark: bool):
        self.is_dark = is_dark
        self._apply_colors()

    def set_x_label(self, label: str):
        tc = UIColors.TEXT_SECONDARY_DARK if self.is_dark else UIColors.TEXT_SECONDARY_LIGHT
        self.setLabel("bottom", label, color=tc, size=Typography.CHART)

    def set_x_labels(self, x_to_label: dict):
        self._x_to_label = x_to_label

    # ── マウスイベント + ツールチップ ─────────────────────────────────────────

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
            vp  = self.mapFromScene(scene_pos)
            gp  = self.mapToGlobal(QPoint(int(vp.x()), int(vp.y())))
            QToolTip.showText(gp + QPoint(14, -10), text, self)
        else:
            QToolTip.hideText()

    def _nearest_x(self, x: float) -> float | None:
        """全カーブから最近傍の x 値を返す。"""
        best_x   = None
        best_d   = float("inf")
        for c in self._curves:
            xd, _ = c.getData()
            if xd is None or len(xd) == 0:
                continue
            idx  = int(np.argmin(np.abs(xd - x)))
            dist = abs(float(xd[idx]) - x)
            if dist < best_d:
                best_d = dist
                best_x = float(xd[idx])
        return best_x

    def _update_tracker(self, x: float):
        """カーソル位置に最も近い各カーブ上の点にドットを表示する。"""
        nx = self._nearest_x(x)
        if nx is None:
            self._tracker.setData([])
            return
        spots: list[dict] = []
        for c, color in zip(self._curves, self._colors):
            xd, yd = c.getData()
            if xd is None or len(xd) == 0:
                continue
            idx = int(np.argmin(np.abs(xd - nx)))
            yv  = float(yd[idx])
            if not math.isnan(yv):
                spots.append({
                    "pos":   (float(xd[idx]), yv),
                    "size":  10,
                    "pen":   pg.mkPen("white", width=1.5),
                    "brush": pg.mkBrush(color),
                })
        self._tracker.setData(spots)

    def _build_tooltip(self, x: float) -> str:
        nx = self._nearest_x(x)
        if nx is None:
            return ""
        header = self._x_to_label.get(nx, f"{nx:.4g}")
        lines  = [f"<b>{header}</b>"]
        for c in self._curves:
            xd, yd = c.getData()
            if xd is None or len(xd) == 0:
                continue
            idx = int(np.argmin(np.abs(xd - nx)))
            y   = float(yd[idx])
            if not math.isnan(y):
                lines.append(f"{c.name() or '?'}: <b>{y:.2f}</b> 円/kWh")
        return "<br>".join(lines) if len(lines) > 1 else ""

    # ── カーブ管理 ────────────────────────────────────────────────────────────

    def clear_curves(self):
        for c in self._curves:
            self.removeItem(c)
        self._curves.clear()
        self._colors.clear()
        if self._legend:
            self._legend.clear()
        self._tracker.setData([])
        self._x_to_label = {}

    def add_curve(self, x, y, name: str, color: str):
        pen = pg.mkPen(color=color, width=2)
        c   = self.plot(x, y, pen=pen, name=name)
        self._curves.append(c)
        self._colors.append(color)

    # ── ビュー制御 ────────────────────────────────────────────────────────────

    def _fit_all_data(self, padding: float = 0.05):
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

    def finalize(self):
        self._fit_all_data()

    def reset_view(self):
        self._fit_all_data()

    def copy_to_clipboard(self):
        QApplication.clipboard().setPixmap(self.grab())


# ── バックグラウンドクエリ ─────────────────────────────────────────────────────

def _run_db_query(mode: str, params: dict, areas: list) -> tuple:
    """SQLite クエリをバックグラウンドスレッドから実行する純粋関数。"""
    is_raw    = mode == "daily"
    col_exprs = ", ".join(
        validate_column_name(col) if is_raw
        else f"AVG({validate_column_name(col)})"
        for _, col, _ in areas
    )

    with get_db_connection(DB_JEPX_SPOT) as conn:
        if mode == "daily":
            rows = conn.execute(
                f"SELECT slot, {col_exprs} FROM jepx_spot_prices WHERE date=? ORDER BY slot",
                (params["date"],)
            ).fetchall()
            x_vals   = [r[0] for r in rows]
            x_labels = [_slot_label(s) for s in x_vals]

        elif mode == "daily_avg":
            rows = conn.execute(
                f"SELECT date, {col_exprs} FROM jepx_spot_prices "
                f"WHERE date BETWEEN ? AND ? GROUP BY date ORDER BY date",
                (params["d0"], params["d1"])
            ).fetchall()
            x_vals   = list(range(len(rows)))
            x_labels = [r[0] for r in rows]

        elif mode == "monthly_avg":
            rows = conn.execute(
                f"SELECT strftime('%Y-%m',date) ym, {col_exprs} "
                f"FROM jepx_spot_prices WHERE date BETWEEN ? AND ? "
                f"GROUP BY ym ORDER BY ym",
                (params["d0"], params["d1"])
            ).fetchall()
            x_vals   = list(range(len(rows)))
            x_labels = [r[0] for r in rows]

        elif mode == "yearly_avg":
            rows = conn.execute(
                f"SELECT strftime('%Y',date) y, {col_exprs} "
                f"FROM jepx_spot_prices GROUP BY y ORDER BY y"
            ).fetchall()
            x_vals   = [int(r[0]) for r in rows]
            x_labels = [r[0] for r in rows]

        else:  # weekday_avg
            rows = conn.execute(
                f"SELECT date, {col_exprs} FROM jepx_spot_prices "
                f"WHERE date BETWEEN ? AND ? "
                f"AND CAST(strftime('%w', date) AS INT) = ? "
                f"GROUP BY date ORDER BY date",
                (params["d0"], params["d1"], params["weekday"])
            ).fetchall()
            x_vals   = list(range(len(rows)))
            x_labels = [r[0] for r in rows]

    return rows, x_vals, x_labels


class _JepxQueryWorker(QThread):
    result = Signal(object, object, object, object)  # key, rows, x_vals, x_labels
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


# ── メインウィジェット ─────────────────────────────────────────────────────────

class JepxSpotWidget(BaseWidget):
    def __init__(self):
        super().__init__()
        self._mode          = "daily"
        self._sel_date      = QDate.currentDate()
        self._area_on: dict[str, bool] = {col: True for _, col in JEPX_SPOT_AREAS}
        fy_start_str, _     = fiscal_year_range(current_fiscal_year())
        self._dr_start      = QDate.fromString(fy_start_str, "yyyy-MM-dd")
        self._dr_end        = QDate.currentDate()
        self._sel_weekday   = 1   # 月曜 (strftime('%w') = 1)
        self._fy_start      = max(JEPX_SPOT_START_FY, current_fiscal_year() - 2)
        self._fy_end        = current_fiscal_year()
        self._fetching      = False
        self._last_poll_date: QDate | None = None
        # クエリキャッシュ: cache_key → (rows, x_vals, x_labels)
        self._query_cache: dict[tuple, tuple] = {}
        self._query_worker: _JepxQueryWorker | None = None
        self._alert_val: float = load_settings().get("imbalance_alert", 40.0)

        # エリアチェックボックスのデバウンスタイマー (50ms)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(50)
        self._refresh_timer.timeout.connect(self._refresh)

        bus.settings_saved.connect(self._reload_settings)

        self._setup_ui()
        # DB インデックスを初回のみ非同期で作成 (起動時間に影響しない)
        QTimer.singleShot(2250, self._ensure_db_index)
        QTimer.singleShot(3000, self._start_history_fetch)
        self._setup_poll_timer()

    # ── UI 構築 ───────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 4)
        root.setSpacing(4)

        root.addWidget(self._build_ctrl_bar())
        root.addWidget(self._build_area_bar())

        self._prog = QProgressBar()
        self._prog.setFixedHeight(3)
        self._prog.setTextVisible(False)
        self._prog.hide()
        root.addWidget(self._prog)

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        root.addWidget(self._splitter, 1)

        self._table = ExcelCopyTableWidget()
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(ExcelCopyTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(
            ExcelCopyTableWidget.SelectionBehavior.SelectItems
        )
        self._table.setSelectionMode(
            ExcelCopyTableWidget.SelectionMode.ContiguousSelection
        )
        self._table.verticalHeader().setDefaultSectionSize(22)
        self._table.verticalHeader().hide()
        self._splitter.addWidget(self._table)

        self._chart = _SpotChart()
        self._splitter.addWidget(self._chart)
        self._splitter.setSizes([450, 550])
        self._splitter.setStretchFactor(0, 4)
        self._splitter.setStretchFactor(1, 6)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        root.addWidget(self._status)

    def _build_ctrl_bar(self) -> QWidget:
        bar = QWidget()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self._cmb_mode = QComboBox()
        self._cmb_mode.setFixedHeight(30)
        for label, key in _MODES:
            self._cmb_mode.addItem(tr(label), key)
        self._cmb_mode.currentIndexChanged.connect(self._on_mode_changed)
        lay.addWidget(self._cmb_mode)

        # ── 当日モード: 日付ピッカー ──────────────────────────────────────────
        self._day_box = QWidget()
        dl = QHBoxLayout(self._day_box)
        dl.setContentsMargins(0, 0, 0, 0); dl.setSpacing(3)
        self._btn_prev  = QPushButton("◀"); self._btn_prev.setFixedSize(26, 30)
        self._de_day    = QDateEdit(self._sel_date)
        self._de_day.setCalendarPopup(True); self._de_day.setDisplayFormat("yyyy-MM-dd")
        self._de_day.setFixedHeight(30)
        self._de_day.dateChanged.connect(self._on_day_changed)
        self._btn_next  = QPushButton("▶"); self._btn_next.setFixedSize(26, 30)
        self._btn_today = QPushButton(tr("今日")); self._btn_today.setFixedHeight(30)
        self._btn_prev.clicked.connect(
            lambda: self._de_day.setDate(self._de_day.date().addDays(-1)))
        self._btn_next.clicked.connect(
            lambda: self._de_day.setDate(self._de_day.date().addDays(1)))
        self._btn_today.clicked.connect(
            lambda: self._de_day.setDate(QDate.currentDate()))
        for w in (self._btn_prev, self._de_day, self._btn_next, self._btn_today):
            dl.addWidget(w)
        lay.addWidget(self._day_box)

        # ── 日次/曜日別モード: 日付範囲ピッカー ──────────────────────────────
        self._dr_box = QWidget()
        drl = QHBoxLayout(self._dr_box)
        drl.setContentsMargins(0, 0, 0, 0); drl.setSpacing(4)
        drl.addWidget(QLabel(tr("期間:")))
        self._de_dr_s = QDateEdit(self._dr_start)
        self._de_dr_s.setCalendarPopup(True); self._de_dr_s.setDisplayFormat("yyyy-MM-dd")
        self._de_dr_s.setFixedHeight(30); self._de_dr_s.dateChanged.connect(self._on_dr_changed)
        self._de_dr_e = QDateEdit(self._dr_end)
        self._de_dr_e.setCalendarPopup(True); self._de_dr_e.setDisplayFormat("yyyy-MM-dd")
        self._de_dr_e.setFixedHeight(30); self._de_dr_e.dateChanged.connect(self._on_dr_changed)
        self._btn_dr_fy = QPushButton(tr("今年度")); self._btn_dr_fy.setFixedHeight(30)
        self._btn_dr_fy.clicked.connect(self._reset_dr_to_current_fy)
        for w in (self._de_dr_s, QLabel("〜"), self._de_dr_e, self._btn_dr_fy):
            drl.addWidget(w)
        self._dr_box.hide()
        lay.addWidget(self._dr_box)

        # ── 曜日別モード: 曜日セレクタ ────────────────────────────────────────
        self._wd_box = QWidget()
        wdl = QHBoxLayout(self._wd_box)
        wdl.setContentsMargins(0, 0, 0, 0); wdl.setSpacing(4)
        wdl.addWidget(QLabel(tr("曜日:")))
        self._cmb_weekday = QComboBox(); self._cmb_weekday.setFixedHeight(30)
        for label, val in _WEEKDAY_OPTIONS:
            self._cmb_weekday.addItem(label, val)
        self._cmb_weekday.currentIndexChanged.connect(self._on_weekday_changed)
        wdl.addWidget(self._cmb_weekday)
        self._wd_box.hide()
        lay.addWidget(self._wd_box)

        # ── 月次モード: 会計年度セレクタ ──────────────────────────────────────
        self._fy_box = QWidget()
        fl = QHBoxLayout(self._fy_box)
        fl.setContentsMargins(0, 0, 0, 0); fl.setSpacing(4)
        fl.addWidget(QLabel(tr("年度:")))
        cur_fy  = current_fiscal_year()
        fy_list = list(range(JEPX_SPOT_START_FY, cur_fy + 1))
        self._cmb_fy_s = QComboBox(); self._cmb_fy_s.setFixedHeight(30)
        self._cmb_fy_e = QComboBox(); self._cmb_fy_e.setFixedHeight(30)
        for fy in fy_list:
            lbl = f"{fy}年度"
            self._cmb_fy_s.addItem(lbl, fy)
            self._cmb_fy_e.addItem(lbl, fy)
        self._cmb_fy_s.setCurrentIndex(max(0, len(fy_list) - 3))
        self._cmb_fy_e.setCurrentIndex(len(fy_list) - 1)
        self._cmb_fy_s.currentIndexChanged.connect(self._on_fy_changed)
        self._cmb_fy_e.currentIndexChanged.connect(self._on_fy_changed)
        fl.addWidget(self._cmb_fy_s); fl.addWidget(QLabel("〜")); fl.addWidget(self._cmb_fy_e)
        self._fy_box.hide()
        lay.addWidget(self._fy_box)

        lay.addStretch()

        self._btn_refresh = QPushButton(tr("更新"))
        self._btn_refresh.setFixedHeight(30)
        self._btn_refresh.clicked.connect(self._start_history_fetch)
        lay.addWidget(self._btn_refresh)

        self._btn_reset_view = QPushButton(tr("ビューリセット"))
        self._btn_reset_view.setFixedHeight(30)
        self._btn_reset_view.clicked.connect(lambda: self._chart.reset_view())
        lay.addWidget(self._btn_reset_view)

        lay.addWidget(_vsep())

        self._chk_tbl = QCheckBox(tr("表")); self._chk_tbl.setChecked(True)
        self._chk_cht = QCheckBox(tr("グラフ")); self._chk_cht.setChecked(True)
        self._chk_tbl.stateChanged.connect(self._on_vis_changed)
        self._chk_cht.stateChanged.connect(self._on_vis_changed)
        lay.addWidget(self._chk_tbl); lay.addWidget(self._chk_cht)

        lay.addWidget(_vsep())

        self._btn_copy = QPushButton(tr("グラフコピー"))
        self._btn_copy.setFixedHeight(30)
        self._btn_copy.clicked.connect(lambda: (
            self._chart.copy_to_clipboard(),
            self._set_status(tr("グラフをクリップボードにコピーしました")),
        ))
        lay.addWidget(self._btn_copy)
        return bar

    def _build_area_bar(self) -> QScrollArea:
        inner = QWidget()
        lay = QHBoxLayout(inner)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(4)
        lay.addWidget(QLabel(tr("エリア:")))
        btn_all  = QPushButton(tr("全選択")); btn_none = QPushButton(tr("全解除"))
        for b in (btn_all, btn_none): b.setFixedHeight(24)
        btn_all.clicked.connect(self._select_all_areas)
        btn_none.clicked.connect(self._deselect_all_areas)
        lay.addWidget(btn_all); lay.addWidget(btn_none); lay.addWidget(_vsep())

        self._area_chks: dict[str, QCheckBox] = {}
        for i, (name, col) in enumerate(JEPX_SPOT_AREAS):
            chk = QCheckBox(name); chk.setChecked(True)
            color = _AREA_COLORS[i % len(_AREA_COLORS)]
            chk.setStyleSheet(
                f"QCheckBox::indicator:checked {{"
                f"background:{color}; border-radius:2px; border:1px solid {color};}}"
            )
            chk.stateChanged.connect(lambda s, c=col: self._on_area_toggled(c, bool(s)))
            self._area_chks[col] = chk; lay.addWidget(chk)
        lay.addStretch()

        # 横スクロール可能なコンテナに収めて最小幅を伝播させない
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedHeight(inner.sizeHint().height() + 4)
        scroll.setFrameShape(QFrame.NoFrame)
        return scroll

    # ── エリア一括操作 ────────────────────────────────────────────────────────

    def _schedule_refresh(self):
        self._refresh_timer.start()

    def _select_all_areas(self):
        for col, chk in self._area_chks.items():
            chk.blockSignals(True)
            chk.setChecked(True)
            self._area_on[col] = True
            chk.blockSignals(False)
        self._schedule_refresh()

    def _deselect_all_areas(self):
        for col, chk in self._area_chks.items():
            chk.blockSignals(True)
            chk.setChecked(False)
            self._area_on[col] = False
            chk.blockSignals(False)
        self._schedule_refresh()

    # ── スケジュール ──────────────────────────────────────────────────────────

    def _start_history_fetch(self):
        if self._fetching:
            return
        self._fetching = True
        self._prog.setRange(0, 0); self._prog.show()
        self._btn_refresh.setEnabled(False)
        self._set_status(tr("データ取得中…"))

        w = FetchJepxSpotHistoryWorker()
        w.progress.connect(self._on_hist_progress)
        w.finished.connect(self._on_hist_finished)
        w.error.connect(lambda m: logger.warning(f"JEPX 履歴DLエラー: {m}"))
        self.track_worker(w); w.start()

    def _setup_poll_timer(self):
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(3 * 60 * 1000)
        self._poll_timer.timeout.connect(self._on_poll)
        self._poll_timer.start()

    def _on_poll(self):
        now = QTime.currentTime()
        if QTime(10, 0) <= now <= QTime(10, 30):
            today = QDate.currentDate()
            if self._last_poll_date != today and not self._fetching:
                self._fetch_today()

    def _fetch_today(self):
        w = FetchJepxSpotTodayWorker()
        w.finished.connect(self._on_today_finished)
        w.error.connect(lambda m: self._set_status(tr("エラー: {0}").format(m)))
        self.track_worker(w); w.start()

    # ── シグナルハンドラ ──────────────────────────────────────────────────────

    def _on_hist_progress(self, cur: int, total: int, year: int):
        self._prog.setRange(0, total); self._prog.setValue(cur)
        self._set_status(tr("{0}年 データ取得中… ({1}/{2})").format(year, cur, total))

    def _on_hist_finished(self):
        self._fetching = False
        self._prog.hide(); self._btn_refresh.setEnabled(True)
        self._query_cache.clear()          # DBが更新されたのでキャッシュ全破棄
        self._set_status(tr("データ取得完了"))
        self._refresh()

    def _on_today_finished(self, found: bool):
        if found:
            self._last_poll_date = QDate.currentDate()
            self._query_cache.clear()
            self._set_status(
                tr("当日データ取得完了 ({0})").format(
                    QDate.currentDate().toString("yyyy-MM-dd"))
            )
            self._refresh()
        else:
            self._set_status(tr("当日データ未公開 — 次回再試行"))

    def _on_mode_changed(self):
        self._mode     = self._cmb_mode.currentData()
        is_daily       = self._mode == "daily"
        is_monthly     = self._mode == "monthly_avg"
        uses_dr        = self._mode in ("daily_avg", "weekday_avg")
        is_weekday     = self._mode == "weekday_avg"

        self._day_box.setVisible(is_daily)
        self._dr_box.setVisible(uses_dr)
        self._wd_box.setVisible(is_weekday)
        self._fy_box.setVisible(is_monthly)
        self._refresh()

    def _on_day_changed(self, d: QDate):
        self._sel_date = d
        if self._mode == "daily": self._refresh()

    def _on_dr_changed(self):
        self._dr_start = self._de_dr_s.date()
        self._dr_end   = self._de_dr_e.date()
        if self._mode in ("daily_avg", "weekday_avg"): self._refresh()

    def _reset_dr_to_current_fy(self):
        fy_start_str, _ = fiscal_year_range(current_fiscal_year())
        self._de_dr_s.setDate(QDate.fromString(fy_start_str, "yyyy-MM-dd"))
        self._de_dr_e.setDate(QDate.currentDate())

    def _on_fy_changed(self):
        self._fy_start = self._cmb_fy_s.currentData()
        self._fy_end   = self._cmb_fy_e.currentData()
        if self._mode == "monthly_avg": self._refresh()

    def _on_weekday_changed(self):
        self._sel_weekday = self._cmb_weekday.currentData()
        if self._mode == "weekday_avg": self._refresh()

    def _on_area_toggled(self, col: str, on: bool):
        self._area_on[col] = on
        self._schedule_refresh()

    def _on_vis_changed(self):
        self._table.setVisible(self._chk_tbl.isChecked())
        self._chart.setVisible(self._chk_cht.isChecked())

    def _reload_settings(self):
        self._alert_val = load_settings().get("imbalance_alert", 40.0)
        self._query_cache.clear()
        self._refresh()

    # ── データ取得・表示 ──────────────────────────────────────────────────────

    def _enabled_areas(self) -> list[tuple[str, str, str]]:
        return [
            (name, col, _AREA_COLORS[i % len(_AREA_COLORS)])
            for i, (name, col) in enumerate(JEPX_SPOT_AREAS)
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
        # is_dark をキーに含めることでテーマ切替時にキャッシュ全破棄が不要になる
        dark = self.is_dark
        if mode == "daily":
            return (mode, self._sel_date.toString("yyyy-MM-dd"), area_cols, dark)
        if mode in ("daily_avg", "weekday_avg"):
            d0, d1 = self._dr_sql_range()
            wd = self._sel_weekday if mode == "weekday_avg" else None
            return (mode, d0, d1, wd, area_cols, dark)
        if mode == "monthly_avg":
            return (mode, self._fy_start, self._fy_end, area_cols, dark)
        return (mode, area_cols, dark)  # yearly_avg

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

    def _refresh(self):
        if self._fetching:
            return
        areas = self._enabled_areas()
        if not areas:
            self._table.setRowCount(0)
            self._chart.clear_curves()
            self._set_status(tr("エリアが選択されていません"))
            return

        key = self._cache_key(areas)
        if key in self._query_cache:
            rows, x_vals, x_labels = self._query_cache[key]
            self._render_table(rows, areas, x_labels)
            self._render_chart(rows, x_vals, x_labels, areas)
            self._update_status(rows)
            return

        # キャッシュミス: バックグラウンドスレッドでクエリを実行
        if self._query_worker and self._query_worker.isRunning():
            try:
                self._query_worker.result.disconnect()
                self._query_worker.error.disconnect()
            except RuntimeError:
                pass
        self._query_worker = _JepxQueryWorker(key, self._mode, self._build_query_params(), areas)
        self._query_worker.result.connect(self._on_query_done)
        self._query_worker.error.connect(self._on_query_error)
        self.track_worker(self._query_worker)
        self._query_worker.start()
        self._set_status(tr("データ読込中…"))

    def _on_query_done(self, key, rows, x_vals, x_labels):
        current_areas = self._enabled_areas()
        current_key   = self._cache_key(current_areas)
        if key != current_key:
            return  # 旧クエリ結果は破棄
        self._query_cache[key] = (rows, x_vals, x_labels)
        self._render_table(rows, current_areas, x_labels)
        self._render_chart(rows, x_vals, x_labels, current_areas)
        self._update_status(rows)

    def _on_query_error(self, msg: str):
        logger.warning(f"JEPXスポット クエリ失敗: {msg}")
        self._set_status(tr("データ取得エラー: {0}").format(msg))

    def _query(self, areas) -> tuple[list, list, list]:
        mode      = self._mode
        is_raw    = mode == "daily"
        col_exprs = ", ".join(
            validate_column_name(col) if is_raw
            else f"AVG({validate_column_name(col)})"
            for _, col, _ in areas
        )

        with get_db_connection(DB_JEPX_SPOT) as conn:
            if mode == "daily":
                d    = self._sel_date.toString("yyyy-MM-dd")
                rows = conn.execute(
                    f"SELECT slot, {col_exprs} FROM jepx_spot_prices "
                    f"WHERE date=? ORDER BY slot", (d,)
                ).fetchall()
                x_vals   = [r[0] for r in rows]
                x_labels = [_slot_label(s) for s in x_vals]

            elif mode == "daily_avg":
                d0, d1 = self._dr_sql_range()
                rows   = conn.execute(
                    f"SELECT date, {col_exprs} FROM jepx_spot_prices "
                    f"WHERE date BETWEEN ? AND ? GROUP BY date ORDER BY date",
                    (d0, d1)
                ).fetchall()
                x_vals   = list(range(len(rows)))
                x_labels = [r[0] for r in rows]

            elif mode == "monthly_avg":
                d0, d1 = self._fy_sql_range()
                rows   = conn.execute(
                    f"SELECT strftime('%Y-%m',date) ym, {col_exprs} "
                    f"FROM jepx_spot_prices WHERE date BETWEEN ? AND ? "
                    f"GROUP BY ym ORDER BY ym", (d0, d1)
                ).fetchall()
                x_vals   = list(range(len(rows)))
                x_labels = [r[0] for r in rows]

            elif mode == "yearly_avg":
                rows   = conn.execute(
                    f"SELECT strftime('%Y',date) y, {col_exprs} "
                    f"FROM jepx_spot_prices GROUP BY y ORDER BY y"
                ).fetchall()
                x_vals   = [int(r[0]) for r in rows]
                x_labels = [r[0] for r in rows]

            else:  # weekday_avg — 指定曜日に該当する各日の日平均
                d0, d1 = self._dr_sql_range()
                rows   = conn.execute(
                    f"SELECT date, {col_exprs} FROM jepx_spot_prices "
                    f"WHERE date BETWEEN ? AND ? "
                    f"AND CAST(strftime('%w', date) AS INT) = ? "
                    f"GROUP BY date ORDER BY date",
                    (d0, d1, self._sel_weekday)
                ).fetchall()
                x_vals   = list(range(len(rows)))
                x_labels = [r[0] for r in rows]   # 各月曜日の日付

        return rows, x_vals, x_labels

    def _update_status(self, rows: list):
        if not rows:
            self._set_status(tr("データなし")); return
        if self._mode == "weekday_avg":
            d0, d1 = self._dr_sql_range()
            self._set_status(
                tr("{0} ({1} 〜 {2}): {3} 件").format(
                    self._cmb_weekday.currentText(), d0, d1, len(rows))
            )
        else:
            self._set_status(tr("{0} 件のデータを表示中").format(len(rows)))

    # ── 表レンダリング ────────────────────────────────────────────────────────

    def _render_table(self, rows: list, areas: list, x_labels: list):
        self._table.setUpdatesEnabled(False)
        try:
            self._render_table_inner(rows, areas, x_labels)
        finally:
            self._table.setUpdatesEnabled(True)

    def _render_table_inner(self, rows: list, areas: list, x_labels: list):
        mode     = self._mode
        is_daily = mode == "daily"
        x_hdr = {
            "daily":       tr("時刻"),
            "daily_avg":   tr("日付"),
            "monthly_avg": tr("年月"),
            "yearly_avg":  tr("年"),
            "weekday_avg": tr("日付"),
        }.get(mode, tr("X"))

        col_hdrs = [x_hdr] + [name for name, _, _ in areas]
        self._table.setColumnCount(len(col_hdrs))
        self._table.setHorizontalHeaderLabels(col_hdrs)

        n_sum = 3 if (is_daily and rows) else 0
        self._table.setRowCount(len(rows) + n_sum)

        alert_val = self._alert_val

        # ── サマリー行 (当日モードのみ: 平均 / 最高 / 最低) ─────────────────────
        if n_sum:
            sep_color = QColor("#3a3a4a" if self.is_dark else "#dce3ef")
            for ri, lbl in enumerate([tr("平均"), tr("最高"), tr("最低")]):
                it = QTableWidgetItem(lbl)
                it.setTextAlignment(Qt.AlignCenter)
                f = it.font(); f.setBold(True); it.setFont(f)
                it.setBackground(QBrush(sep_color))
                self._table.setItem(ri, 0, it)
            for c_col in range(1, len(areas) + 1):
                vals = [row[c_col] for row in rows if row[c_col] is not None]
                if not vals:
                    continue
                for ri, v in enumerate([sum(vals) / len(vals), max(vals), min(vals)]):
                    it2 = QTableWidgetItem(f"{v:.2f}")
                    f2 = it2.font(); f2.setBold(True); it2.setFont(f2)
                    it2.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    _apply_price_color(it2, v, alert_val, self.is_dark)
                    self._table.setItem(ri, c_col, it2)

        # ── データ行 ─────────────────────────────────────────────────────────────
        for r, row in enumerate(rows):
            r_idx = r + n_sum
            lbl = (f"{_slot_label(row[0])}〜{_slot_label_end(row[0])}" if is_daily
                   else (x_labels[r] if r < len(x_labels) else str(row[0])))
            it = QTableWidgetItem(lbl)
            it.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(r_idx, 0, it)

            for c, (_, col, _) in enumerate(areas, 1):
                val = row[c]
                txt = f"{val:.2f}" if val is not None else "—"
                it2 = QTableWidgetItem(txt)
                it2.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if val is not None:
                    _apply_price_color(it2, val, alert_val, self.is_dark)
                self._table.setItem(r_idx, c, it2)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        if col_hdrs:
            hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)

    # ── グラフレンダリング ────────────────────────────────────────────────────

    def _render_chart(self, rows: list, x_vals: list, x_labels: list, areas: list):
        self._chart.clear_curves()
        if not rows:
            return

        mode       = self._mode
        # weekly_avg も indexed (日付ベース) になった
        is_indexed = mode in ("daily_avg", "monthly_avg", "weekday_avg")

        x_label_map = {
            "daily":       tr("時刻"),
            "daily_avg":   tr("日付"),
            "monthly_avg": tr("年月"),
            "yearly_avg":  tr("年"),
            "weekday_avg": tr("日付"),
        }
        self._chart.set_x_label(x_label_map.get(mode, ""))

        if is_indexed:
            step  = max(1, math.ceil(len(x_labels) / 20))
            ticks = [
                [(x_vals[i], x_labels[i]) for i in range(0, len(x_labels), step)]
            ]
            self._chart.getAxis("bottom").setTicks(ticks)
        elif mode == "daily":
            ticks = [[(s, _slot_label(s)) for s in range(1, 49, 2)]]
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

        for i, (name, col, color) in enumerate(areas):
            y_vals = [
                (row[i + 1] if row[i + 1] is not None else float("nan"))
                for row in rows
            ]
            self._chart.add_curve(x_vals, y_vals, name=name, color=color)

        self._chart.finalize()

    # ── テーマ ────────────────────────────────────────────────────────────────

    def _ensure_db_index(self):
        """jepx_spot_prices の date カラムにインデックスを作成する (初回のみ)。"""
        ensure_index(DB_JEPX_SPOT, "jepx_spot_prices", "date")

    def closeEvent(self, event):
        try:
            bus.settings_saved.disconnect(self._reload_settings)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)

    def apply_theme_custom(self):
        self._chart.set_theme(self.is_dark)
        tc2 = UIColors.text_secondary(self.is_dark)
        self._status.setStyleSheet(
            f"color: {tc2}; font-size: {Typography.SMALL}; padding: 2px 4px;"
        )
        if self.is_dark:
            self._table.setStyleSheet(
                "alternate-background-color:#2a2a2e; background:#1e1e1e; color:#d4d4d4;"
            )
        else:
            self._table.setStyleSheet(
                "alternate-background-color:#f0f4ff; background:#ffffff; color:#333333;"
            )
        self._alert_val = load_settings().get("imbalance_alert", 40.0)
        # is_dark をキャッシュキーに含めているのでテーマ切替時の全破棄は不要
        self._refresh()

    def _set_status(self, msg: str):
        self._status.setText(msg)


# ── ヘルパー関数 ──────────────────────────────────────────────────────────────

def _slot_label(slot: int) -> str:
    m = (slot - 1) * 30
    return f"{m // 60:02d}:{m % 60:02d}"

def _slot_label_end(slot: int) -> str:
    m = slot * 30
    return f"{m // 60:02d}:{m % 60:02d}"

def _apply_price_color(
    item: QTableWidgetItem, val: float, alert_val: float, is_dark: bool
) -> None:
    if   val >= alert_val: level = 5
    elif val >= 20:        level = 4
    elif val >= 15:        level = 3
    elif val >= 10:        level = 2
    elif val >= 0:         level = 1
    else:                  return
    bg, fg = UIColors.get_imbalance_alert_colors(is_dark, level)
    item.setBackground(QBrush(QColor(bg)))
    item.setForeground(QBrush(QColor(fg)))

def _vsep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setFrameShadow(QFrame.Sunken)
    return f
