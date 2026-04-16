import logging
import math
import sqlite3
import pyqtgraph as pg
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDateEdit, QTableWidgetItem, QMessageBox, QHeaderView,
    QSplitter, QComboBox, QCheckBox, QApplication, QGraphicsDropShadowEffect,
    QScrollArea, QFrame, QSystemTrayIcon,
)
from PySide6.QtCore import QThread, Signal, QDate, Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QBrush, QColor, QLinearGradient
from app.ui.common import ExcelCopyTableWidget, BaseWidget
from app.ui.theme import UIColors
from app.core.config import (
    DB_IMBALANCE, IMBALANCE_COLORS, load_settings,
    DATE_COL_IDX, TIME_COL_IDX, YOJO_START_COL_IDX, YOJO_END_COL_IDX, FUSOKU_START_COL_IDX,
)
from app.core.database import get_db_connection, validate_column_name
from app.core.i18n import tr
from app.api.imbalance_api import UpdateImbalanceWorker
from app.core.events import bus

pg.setConfigOptions(antialias=True)

logger = logging.getLogger(__name__)


class LoadImbalanceDataWorker(QThread):
    """UI 스레드 프리징을 막기 위해 sqlite3 직접 조회 및 정제(List 변환)를 수행하는 워커"""
    finished = Signal(list, list, str, int)  # rows, target_cols, time_col, target_yyyymmdd
    error = Signal(str)
    no_data = Signal(str)

    def __init__(self, target_date, target_yyyymmdd, is_yojo):
        super().__init__()
        self.target_date = target_date
        self.target_yyyymmdd = target_yyyymmdd
        self.is_yojo = is_yojo

    def run(self):
        try:
            with get_db_connection(DB_IMBALANCE) as conn:
                pragma_rows = conn.execute("PRAGMA table_info('imbalance_prices')").fetchall()
                col_names = [row[1].strip().replace('\ufeff', '') for row in pragma_rows]
                date_col = validate_column_name(col_names[DATE_COL_IDX])

                rows = conn.execute(
                    f'SELECT * FROM imbalance_prices WHERE "{date_col}" = ? OR "{date_col}" = ?',
                    (self.target_yyyymmdd, str(self.target_yyyymmdd))
                ).fetchall()

                # データなし → 同一コネクション内で日付範囲を取得 (2回目のコネクション開設を省略)
                if not rows:
                    range_row = conn.execute(
                        f'SELECT MIN(CAST("{date_col}" AS INTEGER)), MAX(CAST("{date_col}" AS INTEGER)) FROM imbalance_prices'
                    ).fetchone()
                    if range_row and range_row[0] is not None:
                        min_d, max_d = str(int(range_row[0])), str(int(range_row[1]))
                        msg = tr("{0} のデータがありません。\n(DBに保存されている期間: {1} ~ {2})").format(
                            self.target_date,
                            f"{min_d[:4]}/{min_d[4:6]}/{min_d[6:]}",
                            f"{max_d[:4]}/{max_d[4:6]}/{max_d[6:]}"
                        )
                    else:
                        msg = tr("DBに有効なデータがありません。")
                    self.no_data.emit(msg)
                    return

            time_col = col_names[TIME_COL_IDX]
            yojo_cols = [c for i, c in enumerate(col_names) if YOJO_START_COL_IDX <= i <= YOJO_END_COL_IDX and '変更S' not in c]
            fusoku_cols = [c for i, c in enumerate(col_names) if i >= FUSOKU_START_COL_IDX and '変更S' not in c]
            target_cols = yojo_cols if self.is_yojo else fusoku_cols

            display_cols = [time_col] + target_cols
            col_indices = {name: idx for idx, name in enumerate(col_names)}
            
            # List 메모리 캐스팅을 통한 Pandas 오버헤드 완벽 제거
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


class LegendButton(QFrame):
    """클릭으로 선의 표시/숨김을 전환하는 커스텀 범례 아이템"""
    toggled = Signal(str, bool)

    def __init__(self, col_name, color, parent=None):
        super().__init__(parent)
        self.col_name = col_name
        self.color    = color
        self.active   = True
        self.is_dark  = True
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(26)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(7)

        self.indicator  = QLabel()
        self.indicator.setFixedSize(10, 10)
        self.text_label = QLabel(tr(col_name))
        self.text_label.setFont(QFont("Meiryo", 10))

        layout.addWidget(self.indicator)
        layout.addWidget(self.text_label)
        layout.addStretch()
        self._apply_style()

    def mousePressEvent(self, _):
        self.active = not self.active
        self._apply_style()
        self.toggled.emit(self.col_name, self.active)

    def set_active(self, active):
        if self.active != active:
            self.active = active
            self._apply_style()
            
    def set_theme(self, is_dark):
        self.is_dark = is_dark
        self._apply_style()

    def _apply_style(self):
        p_colors = UIColors.get_panel_colors(self.is_dark)
        self.setStyleSheet(
            "QFrame { background: transparent; border-radius: 4px; }"
            f"QFrame:hover {{ background: {p_colors['hover']}; }}"
        )
        if self.active:
            self.indicator.setStyleSheet(f"background-color: {self.color}; border-radius: 2px;")
            self.text_label.setStyleSheet(f"color: {p_colors['text']}; font-weight: {'normal' if self.is_dark else 'bold'};")
        else:
            self.indicator.setStyleSheet("background-color: #cccccc; border-radius: 2px;")
            self.text_label.setStyleSheet(f"color: {p_colors['text_dim']}; text-decoration: line-through; font-weight: normal;")



class ImbalanceWidget(BaseWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # 상단 컨트롤
        top = QHBoxLayout()
        self.title_label = QLabel(tr("インバランス単価"))
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")

        self.update_btn = QPushButton(tr("今月分 DB更新"))
        self.update_btn.clicked.connect(self.update_database)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy/MM/dd")

        self.type_combo = QComboBox()
        self.type_combo.addItems([tr("余剰インバランス料金単価"), tr("不足インバランス料金単価")])
        self.type_combo.currentIndexChanged.connect(self.display_data)

        self.show_btn = QPushButton(tr("表示"))
        self.show_btn.clicked.connect(self.display_data)

        self.show_table_cb = QCheckBox(tr("表表示"))
        self.show_table_cb.setChecked(True)
        self.show_table_cb.stateChanged.connect(self._toggle_views)
        self.show_table_cb.setCursor(Qt.PointingHandCursor)
        self.show_graph_cb = QCheckBox(tr("グラフ表示"))
        self.show_graph_cb.setChecked(True)
        self.show_graph_cb.stateChanged.connect(self._toggle_views)
        self.show_graph_cb.setCursor(Qt.PointingHandCursor)

        self.status_label = QLabel(tr("待機中"))
        self.status_label.setStyleSheet("color: #aaaaaa;")

        for w in (self.title_label, self.update_btn):
            top.addWidget(w)
        top.addSpacing(20)
        for w in (self.date_edit, self.type_combo, self.show_btn,
                  self.show_table_cb, self.show_graph_cb, self.status_label):
            top.addWidget(w)
        top.addStretch()
        layout.addLayout(top)

        # 스플리터: 테이블(좌) + 그래프(우)
        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter, 1)

        self.table = ExcelCopyTableWidget()
        self.table.setAlternatingRowColors(True)
        self.splitter.addWidget(self.table)

        # 그래프 영역
        graph_container = QWidget()
        graph_inner     = QHBoxLayout(graph_container)
        graph_inner.setContentsMargins(0, 0, 0, 0)
        graph_inner.setSpacing(0)

        graph_col        = QWidget()
        graph_col_layout = QVBoxLayout(graph_col)
        graph_col_layout.setContentsMargins(0, 0, 0, 0)
        graph_col_layout.setSpacing(0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(6, 4, 6, 2)
        self.btn_copy_graph = QPushButton(tr("グラフ画像をコピー"))
        self.btn_copy_graph.clicked.connect(self._copy_graph)
        
        self.btn_reset_zoom = QPushButton(tr("ビュー初期化"))
        self.btn_reset_zoom.clicked.connect(lambda: self.plot_widget.enableAutoRange())
        toolbar.addStretch()
        toolbar.addWidget(self.btn_reset_zoom)
        toolbar.addWidget(self.btn_copy_graph)
        graph_col_layout.addLayout(toolbar)

        self.plot_widget = pg.PlotWidget()
        graph_col_layout.addWidget(self.plot_widget, 1)
        graph_inner.addWidget(graph_col, 1)

        # 범례 패널
        self.legend_panel = QWidget()
        self.legend_panel.setFixedWidth(170)
        self.legend_panel.setStyleSheet("background-color: #252526; border-left: 1px solid #3e3e42;")
        lp_layout = QVBoxLayout(self.legend_panel)
        lp_layout.setContentsMargins(0, 10, 0, 6)
        lp_layout.setSpacing(0)

        self.legend_title = QLabel(tr("  エリア"))
        self.legend_title.setStyleSheet(
            "font-size: 10px; font-weight: bold; color: #888888; letter-spacing: 1px; padding-bottom: 6px; background: transparent;"
        )
        lp_layout.addWidget(self.legend_title)

        self.sep = QFrame()
        self.sep.setFrameShape(QFrame.HLine)
        self.sep.setStyleSheet("color: #3e3e42;")
        lp_layout.addWidget(self.sep)

        self.legend_scroll = QScrollArea()
        self.legend_scroll.setWidgetResizable(True)
        self.legend_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.legend_inner  = QWidget()
        self.legend_inner.setStyleSheet("background: transparent;")
        self.legend_layout = QVBoxLayout(self.legend_inner)
        self.legend_layout.setContentsMargins(4, 6, 4, 6)
        self.legend_layout.setSpacing(1)
        self.legend_layout.addStretch()
        self.legend_scroll.setWidget(self.legend_inner)
        lp_layout.addWidget(self.legend_scroll, 1)

        self.sep2 = QFrame()
        self.sep2.setFrameShape(QFrame.HLine)
        self.sep2.setStyleSheet("color: #3e3e42;")
        lp_layout.addWidget(self.sep2)

        lp_btn_layout = QHBoxLayout()
        lp_btn_layout.setContentsMargins(6, 5, 6, 0)
        lp_btn_layout.setSpacing(4)
        self.btn_select_all   = QPushButton(tr("全選択"))
        self.btn_deselect_all = QPushButton(tr("全解除"))
        self.btn_select_all.clicked.connect(self._select_all)
        self.btn_deselect_all.clicked.connect(self._deselect_all)
        lp_btn_layout.addWidget(self.btn_select_all)
        lp_btn_layout.addWidget(self.btn_deselect_all)
        lp_layout.addLayout(lp_btn_layout)

        graph_inner.addWidget(self.legend_panel)
        self.graph_container = graph_container
        self.splitter.addWidget(graph_container)
        self.splitter.setSizes([450, 550])
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 6)

        # 호버 툴팁
        self.tooltip_label = QLabel(self.plot_widget.viewport())
        self.tooltip_label.setStyleSheet(
            "QLabel { background-color: #252526; border: 1px solid #444444;"
            " border-radius: 6px; padding: 7px 10px; color: #d4d4d4; }"
        )
        self.tooltip_label.setFont(QFont("Meiryo", 9))
        self.tooltip_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        
        self.tooltip_shadow = QGraphicsDropShadowEffect(self)
        self.tooltip_shadow.setBlurRadius(12)
        self.tooltip_shadow.setOffset(2, 3)
        self.tooltip_label.setGraphicsEffect(self.tooltip_shadow)
        self.tooltip_label.hide()

        self.hover_points = pg.PlotDataItem(pen=None, symbol='o', symbolSize=12, zValue=10)
        self.plot_widget.addItem(self.hover_points)

        self.curves         = {}
        self.legend_buttons = {}
        self._x_labels      = []
        self._alerted_high_prices = set()
        self.worker = None
        self._load_worker = None

        self.hover_proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self._on_hover
        )

        self._is_initializing = True
        self.apply_theme_custom()
        self._is_initializing = False
        self.setup_timer(self.settings.get("imbalance_interval", 5), self.update_database)

        # 최초 기동 시 자동 수집 및 표시
        self.update_database()

    def set_loading(self, is_loading: bool):
        super().set_loading(is_loading, self.splitter)

    def apply_settings_custom(self):
        self.update_timer_interval(self.settings.get("imbalance_interval", 5))
        self.display_data()

    def apply_theme_custom(self):
        is_dark = self.is_dark
        p_colors = UIColors.get_panel_colors(is_dark)
        g_colors = UIColors.get_graph_colors(is_dark)
        
        cb_style = f"""
            QCheckBox {{
                border: none; 
                padding: 6px 10px; 
                border-radius: 6px; 
                background: transparent; 
                color: {p_colors['text']};
                font-size: 13px;
            }}
            QCheckBox:hover {{
                background-color: {p_colors['hover']};
            }}
        """
        self.show_table_cb.setStyleSheet(cb_style)
        self.show_graph_cb.setStyleSheet(cb_style)
        
        self.legend_panel.setStyleSheet(f"background-color: {p_colors['bg']}; border-left: 1px solid {p_colors['border']};")
        self.legend_title.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {p_colors['text_dim']}; letter-spacing: 1px; padding-bottom: 6px; background: transparent;")
        self.sep.setStyleSheet(f"color: {p_colors['border']};")
        self.sep2.setStyleSheet(f"color: {p_colors['border']};")
        self.tooltip_label.setStyleSheet(
            f"QLabel {{ background-color: {p_colors['bg']}; border: 1px solid {p_colors['border']}; border-radius: 6px; padding: 7px 10px; color: {p_colors['text']}; }}"
        )
        self.plot_widget.setBackground(g_colors['bg'])
        ax_pen = pg.mkPen(color=g_colors['axis'], width=1)
        text_pen = pg.mkPen(g_colors['text'])
        for ax_name in ('left', 'bottom'):
            ax = self.plot_widget.getAxis(ax_name)
            ax.setPen(ax_pen)
            ax.setTextPen(text_pen)
        self.plot_widget.setLabel('left', tr('単価 [円/kWh]'), color=g_colors['text'], size='9pt')
        self.plot_widget.setLabel('bottom', tr('時刻コード'), color=g_colors['text'], size='9pt')
        
        if hasattr(self, 'tooltip_shadow'):
            self.tooltip_shadow.setColor(QColor(0, 0, 0, 160) if is_dark else QColor(0, 0, 0, 60))
        
        for btn in self.legend_buttons.values():
            btn.set_theme(is_dark)
            
        for curve in self.curves.values():
            curve.setSymbolPen(pg.mkPen(g_colors['bg'], width=1.5))

        # Update Colors in Table and Graph Title (초기화 중에는 스킵)
        if not getattr(self, '_is_initializing', False):
            self.display_data()

    def _clear_legend(self):
        self.legend_buttons = {}
        while self.legend_layout.count() > 1:
            item = self.legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _toggle_views(self):
        self.table.setVisible(self.show_table_cb.isChecked())
        self.graph_container.setVisible(self.show_graph_cb.isChecked())

    def update_database(self):
        if not self.check_online_status(): return
        try:
            if self.worker and self.worker.isRunning():
                return
        except RuntimeError:
            self.worker = None
        self.update_btn.setEnabled(False)
        self.set_loading(True)
        self.status_label.setText(tr("DB更新中..."))
        self.status_label.setStyleSheet("color: #64b5f6;")
        self.worker = UpdateImbalanceWorker()
        self.worker.finished.connect(self._on_update_success)
        self.worker.error.connect(self._on_update_error)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()
        self.track_worker(self.worker)

    def _on_update_success(self, msg):
        self.update_btn.setEnabled(True)
        self.set_loading(False)
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("color: #4caf50;")
        self.display_data()
        bus.imbalance_updated.emit()

    def _on_update_error(self, err):
        self.update_btn.setEnabled(True)
        self.set_loading(False)
        self.status_label.setText(tr("更新失敗"))
        self.status_label.setStyleSheet("color: #ff5252;")
        QMessageBox.warning(self, tr("エラー"), err)

    def display_data(self):
        target_date    = self.date_edit.date().toString("yyyy/MM/dd")
        target_yyyymmdd = int(self.date_edit.date().toString("yyyyMMdd"))
        is_yojo = self.type_combo.currentIndex() == 0

        try:
            if getattr(self, '_load_worker', None) and self._load_worker.isRunning():
                return
        except RuntimeError:
            self._load_worker = None
            
        self.set_loading(True)
        self.status_label.setText(tr("データ読込中..."))
        self.status_label.setStyleSheet("color: #64b5f6;")
        
        self._load_worker = LoadImbalanceDataWorker(target_date, target_yyyymmdd, is_yojo)
        self._load_worker.finished.connect(self._on_load_finished)
        self._load_worker.no_data.connect(self._on_load_no_data)
        self._load_worker.error.connect(self._on_load_error)
        self._load_worker.finished.connect(self._load_worker.deleteLater)
        self._load_worker.start()
        self.track_worker(self._load_worker)

    def _on_load_no_data(self, msg):
        self.set_loading(False)
        self.table.clear()
        self.table.setRowCount(0)
        # clear() は hover_points も除去するため、カーブのみ個別削除して hover_points をシーンに残す
        for curve in self.curves.values():
            self.plot_widget.removeItem(curve)
        self.curves = {}
        self._clear_legend()
        self.status_label.setText(tr("データなし"))
        self.status_label.setStyleSheet("color: #ff5252;")
        QMessageBox.information(self, tr("通知"), msg)

    def _on_load_error(self, err):
        self.set_loading(False)
        self.table.clear()
        self.table.setRowCount(0)
        # clear() は hover_points も除去するため、カーブのみ個別削除して hover_points をシーンに残す
        for curve in self.curves.values():
            self.plot_widget.removeItem(curve)
        self.curves = {}
        self._clear_legend()
        self.status_label.setText(tr("読込エラー"))
        self.status_label.setStyleSheet("color: #ff5252;")
        logger.warning(f"インバランスDBの読み込みに失敗しました: {err}")

    def _on_load_finished(self, rows, target_cols, time_col, target_yyyymmdd):
        self.set_loading(False)
        target_date = self.date_edit.date().toString("yyyy/MM/dd")
        display_cols  = [time_col] + target_cols

        # 테이블
        self.table.setUpdatesEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(display_cols))
        self.table.setHorizontalHeaderLabels([tr(c) for c in display_cols])
        self.table.setRowCount(len(rows))
        
        alert_val = self.settings.get("imbalance_alert", 40.0)

        for row_idx, row_data in enumerate(rows):
            for col_idx, value in enumerate(row_data):
                item_text = str(value) if col_idx == 0 else (str(value) if value is not None else "-")
                item = QTableWidgetItem(item_text)
                item.setTextAlignment(Qt.AlignCenter)
                if col_idx > 0:
                    val = value
                    if val is not None:
                        if   val >= alert_val: 
                            bg, fg = UIColors.get_imbalance_alert_colors(self.is_dark, 5)
                            item.setBackground(QBrush(QColor(bg))); item.setForeground(QBrush(QColor(fg))); f = item.font(); f.setBold(True); item.setFont(f)
                        elif val >= 20: 
                            bg, fg = UIColors.get_imbalance_alert_colors(self.is_dark, 4)
                            item.setBackground(QBrush(QColor(bg))); item.setForeground(QBrush(QColor(fg)))
                        elif val >= 15: 
                            bg, fg = UIColors.get_imbalance_alert_colors(self.is_dark, 3)
                            item.setBackground(QBrush(QColor(bg))); item.setForeground(QBrush(QColor(fg)))
                        elif val >= 10: 
                            bg, fg = UIColors.get_imbalance_alert_colors(self.is_dark, 2)
                            item.setBackground(QBrush(QColor(bg))); item.setForeground(QBrush(QColor(fg)))
                        elif val >= 0:  
                            bg, fg = UIColors.get_imbalance_alert_colors(self.is_dark, 1)
                            item.setBackground(QBrush(QColor(bg))); item.setForeground(QBrush(QColor(fg)))
                self.table.setItem(row_idx, col_idx, item)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        if display_cols:
            hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.setUpdatesEnabled(True)

        # 그래프 — clear() は hover_points まで除去してしまうため、
        # 登録済みカーブのみ個別に削除して hover_points はシーンに残す
        for curve in self.curves.values():
            self.plot_widget.removeItem(curve)
        self._clear_legend()
        self.curves    = {}
        
        # 최적화: 데이터가 많아질 경우 버벅임 방지
        self.plot_widget.setClipToView(True)
        self.plot_widget.setDownsampling(mode='peak', auto=True)
        
        self._x_labels = [str(r[0]) for r in rows]
        x_indices      = list(range(len(self._x_labels)))
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.getPlotItem().setContentsMargins(10, 10, 10, 10)

        step  = 4
        ticks = [(i, s) for i, s in enumerate(self._x_labels) if i % step == 0]
        self.plot_widget.getAxis('bottom').setTicks([ticks])
        self.plot_widget.setTitle(
            f"{self.type_combo.currentText()}  ({target_date})",
            color='#cccccc' if self.is_dark else '#333333', size='11pt',
        )
        
        g_colors = UIColors.get_graph_colors(self.is_dark)

        for idx, col in enumerate(target_cols):
            color = IMBALANCE_COLORS[idx % len(IMBALANCE_COLORS)]
            
            # 현대화: QLinearGradient를 사용한 수직 그라데이션 Area 필링
            grad = QLinearGradient(0, 0, 0, 1)
            grad.setCoordinateMode(QLinearGradient.CoordinateMode.ObjectBoundingMode)
            c1 = QColor(color); c1.setAlpha(80)
            c2 = QColor(color); c2.setAlpha(5)
            grad.setColorAt(0.0, c1)
            grad.setColorAt(1.0, c2)
            
            try:
                col_idx = display_cols.index(col)
                # None일 경우 float('nan') 처리하여 그래프가 자연스럽게 끊기도록 함
                y_vals = [float('nan') if r[col_idx] is None else r[col_idx] for r in rows]
                curve  = self.plot_widget.plot(
                    x_indices, y_vals,
                    pen=pg.mkPen(color=color, width=2.5),
                    fillLevel=0, brush=QBrush(grad),
                    symbol='o', symbolSize=6,
                    symbolBrush=pg.mkBrush(color),
                    symbolPen=pg.mkPen(g_colors['bg'], width=1.5),
                )
                self.curves[col] = curve
                btn = LegendButton(col, color)
                btn.set_theme(self.is_dark)
                btn.toggled.connect(self._on_legend_toggle)
                self.legend_layout.insertWidget(self.legend_layout.count() - 1, btn)
                self.legend_buttons[col] = btn
            except Exception:
                pass

        # X축과 Y축이 데이터 영역 밖으로 과도하게 스크롤되지 않도록 뷰포트 제한
        self.plot_widget.getViewBox().setLimits(xMin=-1, xMax=max(1, len(self._x_labels)), yMin=0)
        
        self.plot_widget.enableAutoRange()
        self.status_label.setText(f"{target_date} {tr('更新完了')}")
        self.status_label.setStyleSheet("color: #4caf50;")
        
        # 조회한 데이터가 오늘 날짜인 경우에만 40엔 초과 경고 검사 (DB 재조회 방지)
        today_yyyymmdd = int(datetime.now().strftime("%Y%m%d"))
        if target_yyyymmdd == today_yyyymmdd:
            self._check_high_price_alerts(rows, target_cols, today_yyyymmdd)

    def _on_legend_toggle(self, col_name, visible):
        if col_name in self.curves:
            self.curves[col_name].setVisible(visible)

    def _on_hover(self, evt):
        pos = evt[0]
        vb  = self.plot_widget.plotItem.vb
        if not vb.sceneBoundingRect().contains(pos):
            self.tooltip_label.hide()
            self.hover_points.setData([], [])
            self._last_hover_state = None
            return

        mouse_pt = vb.mapSceneToView(pos)
        x_idx    = round(mouse_pt.x())
        if not self._x_labels or not (0 <= x_idx < len(self._x_labels)):
            self.tooltip_label.hide()
            self.hover_points.setData([], [])
            self._last_hover_state = None
            return

        best_col, best_y, best_dist = None, None, float('inf')
        for col, curve in self.curves.items():
            if not curve.isVisible():
                continue
            _, yd = curve.getData()
            if yd is None or x_idx >= len(yd):
                continue
            y_val = float(yd[x_idx])
            if math.isnan(y_val):
                continue

            dist = abs(y_val - mouse_pt.y())
            if dist < best_dist:
                best_dist, best_col, best_y = dist, col, y_val

        if best_col is None:
            self.tooltip_label.hide()
            self.hover_points.setData([], [])
            self._last_hover_state = None
            return

        # 현재 마우스 위치의 (X인덱스, 가까운 선) 상태가 이전과 다를 때만 무거운 UI 갱신 로직 실행
        current_state = (x_idx, best_col)
        if getattr(self, '_last_hover_state', None) != current_state:
            self._last_hover_state = current_state
            
            g_colors = UIColors.get_graph_colors(self.is_dark)
            best_color = self.legend_buttons[best_col].color
            self.hover_points.setData([x_idx], [best_y])
            self.hover_points.setSymbolBrush(pg.mkBrush(best_color))
            self.hover_points.setSymbolPen(pg.mkPen(g_colors['bg'], width=1.5))
            self.tooltip_label.setText(
                tr("エリア: {0}\n時刻: {1}\n単価: {2} 円").format(best_col, self._x_labels[x_idx], f"{best_y:,.2f}")
            )
            self.tooltip_label.adjustSize()

        vp       = self.plot_widget.viewport()
        wpos     = vp.mapFromGlobal(self.plot_widget.mapToGlobal(self.plot_widget.mapFromScene(pos)))
        tx = min(int(wpos.x()) + 15, vp.width()  - self.tooltip_label.width()  - 4)
        ty = max(int(wpos.y()) - self.tooltip_label.height() - 8, 4)
        self.tooltip_label.move(tx, ty)
        self.tooltip_label.raise_()
        self.tooltip_label.show()

    def _select_all(self):
        for col, btn in self.legend_buttons.items():
            btn.set_active(True)
            if col in self.curves:
                self.curves[col].setVisible(True)

    def _deselect_all(self):
        for col, btn in self.legend_buttons.items():
            btn.set_active(False)
            if col in self.curves:
                self.curves[col].setVisible(False)

    def _copy_graph(self):
        QApplication.clipboard().setPixmap(self.plot_widget.grab())
        QMessageBox.information(
            self, tr("完了"),
            tr("グラフ画像をクリップボードにコピーしました。\n(Excel等に貼り付け可能です)")
        )

    def _check_high_price_alerts(self, rows, target_cols, today_yyyymmdd: int):
        if not rows: return
        
        new_alerts = []
        alert_val  = self.settings.get("imbalance_alert", 40.0)
        
        for row in rows:
            slot = str(row[0])
            for i, col in enumerate(target_cols, start=1):
                val = row[i]
                if val is not None and val >= alert_val:
                    key = (today_yyyymmdd, slot, col)
                    if key not in self._alerted_high_prices:
                        self._alerted_high_prices.add(key)
                        new_alerts.append((slot, col, float(val)))

        if new_alerts:
            display_alerts = new_alerts[:5]
            lines = "\n".join(f"  {tr('コマ')} {s}  |  {tr(a)}:  {v:,.1f} {tr('円')}" for s, a, v in display_alerts)
            if len(new_alerts) > 5:
                lines += "\n  " + tr("...他 {0}件の警告があります").format(len(new_alerts) - 5)

            timestamp = datetime.now().strftime("%H:%M:%S")
            total_count = len(new_alerts)

            main_window = next((w for w in QApplication.topLevelWidgets() if w.inherits("QMainWindow")), None)

            prefix = tr("本日データに{0}円超の単価が 【計 {1}件】 発生しました。").format(alert_val, total_count)
            plain_msg = prefix + f"\n\n{lines}"
            html_lines = lines.replace('\n', '<br>').replace('  ', '&nbsp;&nbsp;')
            html_msg  = prefix + f"<br><br>{html_lines}"

            title = tr("⚠ インバランス 警告 (計 {0}件) - {1}").format(total_count, timestamp)
            
            # 알림 센터 패널에 기록 추가
            if main_window and hasattr(main_window, 'add_notification'):
                main_window.add_notification(title, plain_msg)

            if main_window and main_window.isHidden() and hasattr(main_window, 'tray_icon'):
                main_window.tray_icon.showMessage(
                    title,
                    plain_msg,
                    QApplication.instance().windowIcon(),
                    10000
                )
            else:
                QMessageBox.warning(self, title, html_msg)
