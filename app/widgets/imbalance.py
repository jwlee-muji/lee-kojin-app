import pandas as pd
import logging
import pyqtgraph as pg
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDateEdit, QTableWidgetItem, QMessageBox, QHeaderView,
    QSplitter, QComboBox, QCheckBox, QApplication, QGraphicsDropShadowEffect,
    QScrollArea, QFrame, QSystemTrayIcon
)
from PySide6.QtCore import QThread, Signal, QDate, Qt, QTimer
from PySide6.QtGui import QFont, QBrush, QColor
from app.ui.common import ExcelCopyTableWidget, BaseWidget
from app.core.config import (
    DB_IMBALANCE, IMBALANCE_COLORS, load_settings,
    DATE_COL_IDX, TIME_COL_IDX, YOJO_START_COL_IDX, YOJO_END_COL_IDX, FUSOKU_START_COL_IDX,
)
from app.core.database import get_db_connection
from app.ui.api_client import UpdateImbalanceWorker

pg.setConfigOptions(antialias=True)

logger = logging.getLogger(__name__)


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
        self.text_label = QLabel(col_name)
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
        self.setStyleSheet(
            "QFrame { background: transparent; border-radius: 4px; }"
            f"QFrame:hover {{ background: {'#333333' if self.is_dark else '#d0d0d0'}; }}"
        )
        if self.active:
            self.indicator.setStyleSheet(f"background-color: {self.color}; border-radius: 2px;")
            self.text_label.setStyleSheet(f"color: {'#d4d4d4' if self.is_dark else '#000000'}; font-weight: {'normal' if self.is_dark else 'bold'};")
        else:
            self.indicator.setStyleSheet("background-color: #cccccc; border-radius: 2px;")
            self.text_label.setStyleSheet(f"color: {'#666666' if self.is_dark else '#555555'}; text-decoration: line-through; font-weight: normal;")



class ImbalanceWidget(BaseWidget):
    data_updated = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # 상단 컨트롤
        top = QHBoxLayout()
        self.title_label = QLabel(self.tr("インバランス単価"))
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")

        self.update_btn = QPushButton(self.tr("今月分 DB更新"))
        self.update_btn.clicked.connect(self.update_database)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy/MM/dd")

        self.type_combo = QComboBox()
        self.type_combo.addItems([self.tr("余剰インバランス料金単価"), self.tr("不足インバランス料金単価")])
        self.type_combo.currentIndexChanged.connect(self.display_data)

        self.show_btn = QPushButton(self.tr("表示"))
        self.show_btn.clicked.connect(self.display_data)

        self.show_table_cb = QCheckBox(self.tr("表表示"))
        self.show_table_cb.setChecked(True)
        self.show_table_cb.stateChanged.connect(self._toggle_views)
        self.show_table_cb.setCursor(Qt.PointingHandCursor)
        self.show_graph_cb = QCheckBox(self.tr("グラフ表示"))
        self.show_graph_cb.setChecked(True)
        self.show_graph_cb.stateChanged.connect(self._toggle_views)
        self.show_graph_cb.setCursor(Qt.PointingHandCursor)

        self.status_label = QLabel(self.tr("待機中"))
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
        self.btn_copy_graph = QPushButton(self.tr("グラフ画像をコピー"))
        self.btn_copy_graph.clicked.connect(self._copy_graph)
        toolbar.addStretch()
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

        self.legend_title = QLabel(self.tr("  エリア"))
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
        self.btn_select_all   = QPushButton(self.tr("全選択"))
        self.btn_deselect_all = QPushButton(self.tr("全解除"))
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

        self.curves         = {}
        self.legend_buttons = {}
        self._x_labels      = []
        self._alerted_high_prices = set()
        self.worker = None

        self.hover_proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self._on_hover
        )

        self._is_initializing = True
        self.apply_theme_custom()
        self._is_initializing = False
        self.setup_timer(self.settings.get("imbalance_interval", 5), self.update_database)

        # 최초 기동 시 자동 수집 및 표시
        self.update_database()

    def apply_settings_custom(self):
        self.update_timer_interval(self.settings.get("imbalance_interval", 5))
        self.display_data()

    def apply_theme_custom(self):
        is_dark = self.is_dark
        
        cb_style = f"""
            QCheckBox {{
                border: none; 
                padding: 6px 10px; 
                border-radius: 6px; 
                background: transparent; 
                color: {'#d4d4d4' if is_dark else '#333333'};
                font-size: 13px;
            }}
            QCheckBox:hover {{
                background-color: {'#333333' if is_dark else '#e8e8e8'};
            }}
        """
        self.show_table_cb.setStyleSheet(cb_style)
        self.show_graph_cb.setStyleSheet(cb_style)
        
        self.legend_panel.setStyleSheet(f"background-color: {'#252526' if is_dark else '#e8e8e8'}; border-left: 1px solid {'#3e3e42' if is_dark else '#cccccc'};")
        self.legend_title.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {'#888888' if is_dark else '#000000'}; letter-spacing: 1px; padding-bottom: 6px; background: transparent;")
        self.sep.setStyleSheet(f"color: {'#3e3e42' if is_dark else '#cccccc'};")
        self.sep2.setStyleSheet(f"color: {'#3e3e42' if is_dark else '#cccccc'};")
        self.tooltip_label.setStyleSheet(
            f"QLabel {{ background-color: {'#252526' if is_dark else '#ffffff'}; border: 1px solid {'#444444' if is_dark else '#cccccc'}; border-radius: 6px; padding: 7px 10px; color: {'#d4d4d4' if is_dark else '#333333'}; }}"
        )
        self.plot_widget.setBackground('#1e1e1e' if is_dark else '#ffffff')
        ax_pen = pg.mkPen(color='#555555' if is_dark else '#dddddd', width=1)
        text_pen = pg.mkPen('#aaaaaa' if is_dark else '#666666')
        for ax_name in ('left', 'bottom'):
            ax = self.plot_widget.getAxis(ax_name)
            ax.setPen(ax_pen)
            ax.setTextPen(text_pen)
        self.plot_widget.setLabel('left', '単価 [円/kWh]', color='#aaaaaa' if is_dark else '#666666', size='9pt')
        self.plot_widget.setLabel('bottom', '時刻コード', color='#aaaaaa' if is_dark else '#666666', size='9pt')
        
        if hasattr(self, 'tooltip_shadow'):
            self.tooltip_shadow.setColor(QColor(0, 0, 0, 160) if is_dark else QColor(0, 0, 0, 60))
        
        for btn in self.legend_buttons.values():
            btn.set_theme(is_dark)

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
        if self.worker and self.worker.isRunning():
            return
        self.update_btn.setEnabled(False)
        self.status_label.setText("DB更新中...")
        self.status_label.setStyleSheet("color: #64b5f6;")
        self.worker = UpdateImbalanceWorker()
        self.worker.finished.connect(self._on_update_success)
        self.worker.error.connect(self._on_update_error)
        self.worker.start()

    def _on_update_success(self, msg):
        self.update_btn.setEnabled(True)
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("color: #4caf50;")
        self.display_data()
        self.data_updated.emit()

    def _on_update_error(self, err):
        self.update_btn.setEnabled(True)
        self.status_label.setText("更新失敗")
        self.status_label.setStyleSheet("color: #ff5252;")
        QMessageBox.warning(self, "エラー", err)

    def display_data(self):
        target_date    = self.date_edit.date().toString("yyyy/MM/dd")
        target_yyyymmdd = int(self.date_edit.date().toString("yyyyMMdd"))

        try:
            with get_db_connection(DB_IMBALANCE) as conn:
                cursor    = conn.execute('SELECT * FROM imbalance_prices LIMIT 0')
                col_names = [desc[0].strip().replace('\ufeff', '') for desc in cursor.description]
                date_col  = col_names[DATE_COL_IDX]
                df        = pd.read_sql(
                    # CAST演算を排除し、インデックスをフル活用する高速クエリ
                    f'SELECT * FROM imbalance_prices WHERE "{date_col}" = ? OR "{date_col}" = ?',
                    conn, params=[target_yyyymmdd, str(target_yyyymmdd)]
                )
                df.columns = [c.strip().replace('\ufeff', '') for c in df.columns]
        except Exception:
            self.status_label.setText("DBが存在しません。まず更新してください。")
            return

        time_col    = df.columns[TIME_COL_IDX]
        yojo_cols   = [c for i, c in enumerate(df.columns)
                       if YOJO_START_COL_IDX <= i <= YOJO_END_COL_IDX and '変更S' not in str(c)]
        fusoku_cols = [c for i, c in enumerate(df.columns)
                       if i >= FUSOKU_START_COL_IDX and '変更S' not in str(c)]

        if df.empty:
            self.table.clear()
            self.table.setRowCount(0)
            self.plot_widget.clear()
            self._clear_legend()
            try:
                with get_db_connection(DB_IMBALANCE) as conn:
                    row = conn.execute(
                        f'SELECT MIN(CAST("{date_col}" AS INTEGER)), MAX(CAST("{date_col}" AS INTEGER))'
                        f' FROM imbalance_prices'
                    ).fetchone()
                if row and row[0]:
                    min_d, max_d = str(int(row[0])), str(int(row[1]))
                    msg = (f"{target_date} のデータがありません。\n"
                           f"(DBに保存されている期間: "
                           f"{min_d[:4]}/{min_d[4:6]}/{min_d[6:]} ~ "
                           f"{max_d[:4]}/{max_d[4:6]}/{max_d[6:]})")
                else:
                    msg = "DBに有効なデータがありません。"
            except Exception:
                msg = "DBに有効なデータがありません。"
            self.status_label.setText("データなし")
            self.status_label.setStyleSheet("color: #ff5252;")
            QMessageBox.information(self, "通知", msg)
            return

        target_cols   = yojo_cols if self.type_combo.currentText() == "余剰インバランス料金単価" else fusoku_cols
        display_cols  = [time_col] + target_cols

        # 테이블
        self.table.setUpdatesEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(display_cols))
        self.table.setHorizontalHeaderLabels(display_cols)
        self.table.setRowCount(len(df))
        
        alert_val = self.settings.get("imbalance_alert", 40.0)

        for row_idx, (_, row_data) in enumerate(df[display_cols].iterrows()):
            for col_idx, value in enumerate(row_data):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                if col_idx > 0:
                    try:
                        val = float(str(value).replace(',', ''))
                        if   val >= alert_val: item.setBackground(QBrush(QColor('#5c1111' if self.is_dark else '#ffcccc'))); item.setForeground(QBrush(QColor('#ffffff' if self.is_dark else '#ff0000'))); f = item.font(); f.setBold(True); item.setFont(f)
                        elif val >= 20: item.setBackground(QBrush(QColor('#801515' if self.is_dark else '#ffdddd')))
                        elif val >= 15: item.setBackground(QBrush(QColor('#804000' if self.is_dark else '#fff0cc')))
                        elif val >= 10: item.setBackground(QBrush(QColor('#1e401e' if self.is_dark else '#dcf0dc')))
                        elif val >= 0:  item.setBackground(QBrush(QColor('#113344' if self.is_dark else '#e1f5fe')))
                    except (ValueError, TypeError):
                        pass
                self.table.setItem(row_idx, col_idx, item)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        if display_cols:
            hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.setUpdatesEnabled(True)

        # 그래프
        self.plot_widget.clear()
        self._clear_legend()
        self.curves    = {}
        self._x_labels = df[time_col].astype(str).tolist()
        x_indices      = list(range(len(self._x_labels)))
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)

        step  = 4
        ticks = [(i, s) for i, s in enumerate(self._x_labels) if i % step == 0]
        self.plot_widget.getAxis('bottom').setTicks([ticks])
        self.plot_widget.setTitle(
            f"{self.type_combo.currentText()}  ({target_date})",
            color='#cccccc' if self.is_dark else '#333333', size='11pt',
        )

        for idx, col in enumerate(target_cols):
            color = IMBALANCE_COLORS[idx % len(IMBALANCE_COLORS)]
            try:
                y_vals = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').tolist()
                curve  = self.plot_widget.plot(
                    x_indices, y_vals,
                    pen=pg.mkPen(color=color, width=2.5),
                    symbol='o', symbolSize=5,
                    symbolBrush=pg.mkBrush(color),
                    symbolPen=pg.mkPen('white', width=1.5),
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
        self.status_label.setText(f"{target_date} 表示完了")
        self.status_label.setStyleSheet("color: #4caf50;")
        
        # 조회한 데이터가 오늘 날짜인 경우에만 40엔 초과 경고 검사 (DB 재조회 방지)
        today_yyyymmdd = int(datetime.now().strftime("%Y%m%d"))
        if target_yyyymmdd == today_yyyymmdd:
            self._check_high_price_alerts(df, today_yyyymmdd)

    def _on_legend_toggle(self, col_name, visible):
        if col_name in self.curves:
            self.curves[col_name].setVisible(visible)

    def _on_hover(self, evt):
        pos = evt[0]
        vb  = self.plot_widget.plotItem.vb
        if not vb.sceneBoundingRect().contains(pos):
            self.tooltip_label.hide()
            return

        mouse_pt = vb.mapSceneToView(pos)
        x_idx    = round(mouse_pt.x())
        if not self._x_labels or not (0 <= x_idx < len(self._x_labels)):
            self.tooltip_label.hide()
            return

        best_col, best_y, best_dist = None, None, float('inf')
        for col, curve in self.curves.items():
            if not curve.isVisible():
                continue
            _, yd = curve.getData()
            if yd is None or x_idx >= len(yd):
                continue
            y_val = float(yd[x_idx])
            if pd.isna(y_val):
                continue
            dist = abs(y_val - mouse_pt.y())
            if dist < best_dist:
                best_dist, best_col, best_y = dist, col, y_val

        if best_col is None:
            self.tooltip_label.hide()
            return

        self.tooltip_label.setText(
            f"エリア: {best_col}\n時刻: {self._x_labels[x_idx]}\n単価: {best_y:,.2f} 円"
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
            self, "完了",
            "グラフ画像をクリップボードにコピーしました。\n(Excel等に貼り付け可能です)"
        )

    def _check_high_price_alerts(self, df, today_yyyymmdd: int):
        if df.empty:
            return

        check_cols = [
            c for i, c in enumerate(df.columns)
            if (YOJO_START_COL_IDX <= i <= YOJO_END_COL_IDX or i >= FUSOKU_START_COL_IDX)
            and '変更S' not in str(c)
        ]
        time_col   = df.columns[TIME_COL_IDX]
        new_alerts = []
        alert_val  = self.settings.get("imbalance_alert", 40.0)
        
        if not check_cols:
            return
            
        # NaN 이슈를 방지하기 위해 컬럼 단위로 안전하게 필터링
        for col in check_cols:
            series = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')
            # 임계값을 초과하는 순수 수치만 필터링 (NaN 자동 제외)
            over_series = series[series >= alert_val]
            for row_idx, val in over_series.items():
                slot = str(df.loc[row_idx, time_col])
                key = (today_yyyymmdd, slot, col)
                if key not in self._alerted_high_prices:
                    self._alerted_high_prices.add(key)
                    new_alerts.append((slot, col, float(val)))

        if new_alerts:
            display_alerts = new_alerts[:5]
            lines = "\n".join(f"  コマ {s}  |  {a}:  {v:,.1f} 円" for s, a, v in display_alerts)
            if len(new_alerts) > 5:
                lines += f"\n  ...他 {len(new_alerts) - 5}件の警告があります"
                
            timestamp = datetime.now().strftime("%H:%M:%S")
            total_count = len(new_alerts)
            
            main_window = next((w for w in QApplication.topLevelWidgets() if w.inherits("QMainWindow")), None)
            
            plain_msg = f"本日データに{alert_val}円超の単価が 【計 {total_count}件】 発生しました。\n\n{lines}"
            html_lines = lines.replace('\n', '<br>').replace('  ', '&nbsp;&nbsp;')
            html_msg  = f"本日データに{alert_val}円超の単価が <span style='color: #ff5252; font-weight: bold; font-size: 14px;'>【計 {total_count}件】</span> 発生しました。<br><br>{html_lines}"

            title = f"⚠ インバランス 警告 (計 {total_count}件) - {timestamp}"
            
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
