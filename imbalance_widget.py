import sqlite3
import pandas as pd
import io
import requests
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDateEdit, QTableWidgetItem, QMessageBox, QHeaderView,
    QSplitter, QComboBox, QCheckBox, QApplication,
    QScrollArea, QFrame,
)
from PySide6.QtCore import QThread, Signal, QDate, Qt, QTimer
from PySide6.QtGui import QFont, QBrush, QColor
from widgets import ExcelCopyTableWidget

pg.setConfigOptions(antialias=True)

# 컬럼 인덱스 상수
DATE_COL_IDX = 1
TIME_COL_IDX = 3
YOJO_START_COL_IDX = 5
YOJO_END_COL_IDX = 21
FUSOKU_START_COL_IDX = 23

# 모던 컬러 팔레트
COLORS = [
    '#2196F3', '#F44336', '#4CAF50', '#FF9800', '#9C27B0',
    '#00BCD4', '#FF5722', '#8BC34A', '#FFC107', '#3F51B5',
    '#E91E63', '#009688', '#96CEB4', '#673AB7', '#795548',
    '#607D8B', '#FF6B6B', '#4ECDC4', '#45B7D1', '#CDDC39',
]


class LegendButton(QFrame):
    """クリックで線の表示/非表示を切り替えるカスタム凡例アイテム"""
    toggled = Signal(str, bool)

    def __init__(self, col_name, color, parent=None):
        super().__init__(parent)
        self.col_name = col_name
        self.color = color
        self.active = True
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(26)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(7)

        self.indicator = QLabel()
        self.indicator.setFixedSize(10, 10)

        self.text_label = QLabel(col_name)
        font = QFont()
        font.setPointSize(9)
        self.text_label.setFont(font)

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

    def _apply_style(self):
        self.setStyleSheet(
            "QFrame { background: transparent; border-radius: 4px; }"
            "QFrame:hover { background: #eeeeee; }"
        )
        if self.active:
            self.indicator.setStyleSheet(
                f"background-color: {self.color}; border-radius: 2px;"
            )
            self.text_label.setStyleSheet("color: #222222;")
        else:
            self.indicator.setStyleSheet(
                "background-color: #cccccc; border-radius: 2px;"
            )
            self.text_label.setStyleSheet(
                "color: #aaaaaa; text-decoration: line-through;"
            )


# DB 업데이트를 담당하는 백그라운드 스레드
class UpdateImbalanceWorker(QThread):
    finished = Signal(str)
    error = Signal(str)

    def run(self):
        try:
            base = "https://www.imbalanceprices-cs.jp"
            s = requests.Session()
            s.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })

            # 1. CSV 목록 API에서 今月分(첫 번째 항목) 경로 취득
            r = s.get(f"{base}/imbalance-price-list/priceList", timeout=15)
            r.raise_for_status()
            items = r.json()["imbalance_list"]
            csv_path = items[0]["path"]  # 항상 첫 번째가 최신 월

            # 2. CSV 직접 다운로드
            csv_url = f"{base}/public/price/{csv_path}"
            r = s.get(csv_url, timeout=30)
            r.raise_for_status()
            csv_content = r.content.decode('cp932', errors='replace')

            # 3. pandas로 읽어 SQLite에 누적 저장
            df = pd.read_csv(io.StringIO(csv_content), skiprows=3)
            df.columns = df.columns.astype(str).str.strip().str.replace('\ufeff', '')

            conn = sqlite3.connect('imbalance_data.db')
            try:
                try:
                    existing_df = pd.read_sql('SELECT * FROM imbalance_prices', conn)
                    existing_df.columns = existing_df.columns.astype(str).str.strip().str.replace('\ufeff', '')
                    combined_df = pd.concat([existing_df, df]).drop_duplicates()
                except Exception:
                    combined_df = df
                combined_df.to_sql('imbalance_prices', conn, if_exists='replace', index=False)
            finally:
                conn.close()

            self.finished.emit("DB更新が完了しました。")

        except Exception as e:
            self.error.emit(f"更新エラー: {str(e)}")


class ImbalanceWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # 상단 컨트롤 패널
        top_layout = QHBoxLayout()
        self.title_label = QLabel("インバランス単価")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")

        self.update_btn = QPushButton("今月分 DB更新")
        self.update_btn.setStyleSheet("background-color: #e6f7ff;")
        self.update_btn.clicked.connect(self.update_database)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy/MM/dd")

        self.type_combo = QComboBox()
        self.type_combo.addItems(["余剰インバランス料金単価", "不足インバランス料金単価"])
        self.type_combo.currentIndexChanged.connect(self.display_data)

        self.show_btn = QPushButton("表示")
        self.show_btn.clicked.connect(self.display_data)

        self.show_table_cb = QCheckBox("表表示")
        self.show_table_cb.setChecked(True)
        self.show_table_cb.stateChanged.connect(self.toggle_views)
        self.show_graph_cb = QCheckBox("グラフ表示")
        self.show_graph_cb.setChecked(True)
        self.show_graph_cb.stateChanged.connect(self.toggle_views)

        self.status_label = QLabel("待機中")
        self.status_label.setStyleSheet("color: gray;")

        top_layout.addWidget(self.title_label)
        top_layout.addWidget(self.update_btn)
        top_layout.addSpacing(20)
        top_layout.addWidget(self.date_edit)
        top_layout.addWidget(self.type_combo)
        top_layout.addWidget(self.show_btn)
        top_layout.addWidget(self.show_table_cb)
        top_layout.addWidget(self.show_graph_cb)
        top_layout.addWidget(self.status_label)
        top_layout.addStretch()
        layout.addLayout(top_layout)

        # 하단 스플리터: 표(좌) + 그래프(우)
        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter, 1)

        # 좌측: 데이터 테이블
        self.table = ExcelCopyTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(
            "alternate-background-color: #f9f9f9; background-color: #ffffff;"
        )
        self.splitter.addWidget(self.table)

        # 우측: 그래프 열 + 범례 패널
        self.graph_container = QWidget()
        graph_inner = QHBoxLayout(self.graph_container)
        graph_inner.setContentsMargins(0, 0, 0, 0)
        graph_inner.setSpacing(0)

        # 그래프 열 (툴바 + PlotWidget)
        graph_col = QWidget()
        graph_col_layout = QVBoxLayout(graph_col)
        graph_col_layout.setContentsMargins(0, 0, 0, 0)
        graph_col_layout.setSpacing(0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(6, 4, 6, 2)
        _btn_style = (
            "QPushButton { font-size: 11px; color: #555555; border: 1px solid #dddddd;"
            " border-radius: 4px; padding: 3px 10px; background: #f5f5f5; }"
            "QPushButton:hover { background: #e8e8e8; }"
            "QPushButton:pressed { background: #d8d8d8; }"
        )
        self.btn_copy_graph = QPushButton("グラフ画像をコピー")
        self.btn_copy_graph.setStyleSheet(_btn_style)
        self.btn_copy_graph.clicked.connect(self.copy_graph_to_clipboard)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_copy_graph)
        graph_col_layout.addLayout(toolbar)

        self.plot_widget = pg.PlotWidget()
        self._init_plot_style()
        graph_col_layout.addWidget(self.plot_widget, 1)

        graph_inner.addWidget(graph_col, 1)

        # 범례 패널 (우측 고정 사이드바)
        legend_panel = QWidget()
        legend_panel.setFixedWidth(170)
        legend_panel.setStyleSheet(
            "background-color: #fafafa; border-left: 1px solid #eeeeee;"
        )
        lp_layout = QVBoxLayout(legend_panel)
        lp_layout.setContentsMargins(0, 10, 0, 6)
        lp_layout.setSpacing(0)

        legend_title = QLabel("  エリア")
        legend_title.setStyleSheet(
            "font-size: 10px; font-weight: bold; color: #aaaaaa;"
            " letter-spacing: 1px; padding-bottom: 6px;"
        )
        lp_layout.addWidget(legend_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #eeeeee;")
        lp_layout.addWidget(sep)

        self.legend_scroll = QScrollArea()
        self.legend_scroll.setWidgetResizable(True)
        self.legend_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )
        self.legend_inner = QWidget()
        self.legend_inner.setStyleSheet("background: transparent;")
        self.legend_layout = QVBoxLayout(self.legend_inner)
        self.legend_layout.setContentsMargins(4, 6, 4, 6)
        self.legend_layout.setSpacing(1)
        self.legend_layout.addStretch()
        self.legend_scroll.setWidget(self.legend_inner)
        lp_layout.addWidget(self.legend_scroll, 1)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #eeeeee;")
        lp_layout.addWidget(sep2)

        lp_btn_layout = QHBoxLayout()
        lp_btn_layout.setContentsMargins(6, 5, 6, 0)
        lp_btn_layout.setSpacing(4)
        _lp_btn_style = (
            "QPushButton { font-size: 10px; color: #666666; border: 1px solid #dddddd;"
            " border-radius: 3px; padding: 2px 6px; background: #f0f0f0; }"
            "QPushButton:hover { background: #e4e4e4; }"
        )
        self.btn_select_all = QPushButton("全選択")
        self.btn_select_all.setStyleSheet(_lp_btn_style)
        self.btn_select_all.clicked.connect(self.select_all_lines)
        self.btn_deselect_all = QPushButton("全解除")
        self.btn_deselect_all.setStyleSheet(_lp_btn_style)
        self.btn_deselect_all.clicked.connect(self.deselect_all_lines)
        lp_btn_layout.addWidget(self.btn_select_all)
        lp_btn_layout.addWidget(self.btn_deselect_all)
        lp_layout.addLayout(lp_btn_layout)

        graph_inner.addWidget(legend_panel)
        self.splitter.addWidget(self.graph_container)

        self.splitter.setSizes([400, 600])
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 6)

        # 호버 툴팁 (plot_widget 위에 겹치는 QLabel)
        self.tooltip_label = QLabel(self.plot_widget.viewport())
        self.tooltip_label.setStyleSheet(
            "QLabel {"
            "  background-color: white;"
            "  border: 1px solid #cccccc;"
            "  border-radius: 6px;"
            "  padding: 7px 10px;"
            "  color: #333333;"
            "}"
        )
        self.tooltip_label.setFont(QFont("", 9))
        self.tooltip_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.tooltip_label.hide()

        # 내부 상태 변수
        self.curves = {}
        self.legend_buttons = {}
        self._x_labels = []

        # PyQtGraph 마우스 호버 이벤트
        self.hover_proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved,
            rateLimit=60,
            slot=self.on_hover,
        )

        # 40円超コマの通知済みセット（セッション中の重複通知防止）
        self._alerted_high_prices = set()

        # 5分ごとに自動更新するタイマー (DB 업데이트 후 화면도 갱신)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_database)
        self.timer.start(300_000)

    def _init_plot_style(self):
        self.plot_widget.setBackground('#ffffff')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.plotItem.hideAxis('top')
        self.plot_widget.plotItem.hideAxis('right')
        for axis_name in ('left', 'bottom'):
            axis = self.plot_widget.getAxis(axis_name)
            axis.setPen(pg.mkPen(color='#dddddd', width=1))
            axis.setTextPen(pg.mkPen('#666666'))
        self.plot_widget.setLabel('left', '単価 [円/kWh]', color='#666666', size='9pt')
        self.plot_widget.setLabel('bottom', '時刻コード', color='#666666', size='9pt')

    def _clear_legend_panel(self):
        self.legend_buttons = {}
        while self.legend_layout.count() > 1:  # 마지막 stretch 유지
            item = self.legend_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def toggle_views(self):
        self.table.setVisible(self.show_table_cb.isChecked())
        self.graph_container.setVisible(self.show_graph_cb.isChecked())

    def update_database(self):
        if hasattr(self, 'worker') and self.worker.isRunning():
            return
        self.update_btn.setEnabled(False)
        self.status_label.setText("DB更新中...")
        self.status_label.setStyleSheet("color: blue;")
        self.worker = UpdateImbalanceWorker()
        self.worker.finished.connect(self.on_update_success)
        self.worker.error.connect(self.on_update_error)
        self.worker.start()

    def on_update_success(self, msg):
        self.update_btn.setEnabled(True)
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("color: green;")
        self.display_data()
        self._check_high_price_alerts()

    def on_update_error(self, err):
        self.update_btn.setEnabled(True)
        self.status_label.setText("更新失敗")
        self.status_label.setStyleSheet("color: red;")
        QMessageBox.warning(self, "エラー", err)

    def display_data(self):
        target_date = self.date_edit.date().toString("yyyy/MM/dd")
        target_yyyymmdd = int(self.date_edit.date().toString("yyyyMMdd"))

        try:
            conn = sqlite3.connect('imbalance_data.db')
            try:
                cursor = conn.execute('SELECT * FROM imbalance_prices LIMIT 0')
                col_names = [desc[0].strip().replace('\ufeff', '') for desc in cursor.description]
                date_col = col_names[DATE_COL_IDX]
                df = pd.read_sql(
                    f'SELECT * FROM imbalance_prices WHERE CAST("{date_col}" AS INTEGER) = ?',
                    conn, params=[target_yyyymmdd]
                )
                df.columns = [c.strip().replace('\ufeff', '') for c in df.columns]
            finally:
                conn.close()
        except Exception:
            self.status_label.setText("DBが存在しません。まず更新してください。")
            return

        time_col = df.columns[TIME_COL_IDX]
        yojo_cols = [
            col for idx, col in enumerate(df.columns)
            if YOJO_START_COL_IDX <= idx <= YOJO_END_COL_IDX and '変更S' not in str(col)
        ]
        fusoku_cols = [
            col for idx, col in enumerate(df.columns)
            if idx >= FUSOKU_START_COL_IDX and '変更S' not in str(col)
        ]

        if df.empty:
            self.table.clear()
            self.table.setRowCount(0)
            self.plot_widget.clear()
            self._clear_legend_panel()

            try:
                conn = sqlite3.connect('imbalance_data.db')
                try:
                    row = conn.execute(
                        f'SELECT MIN(CAST("{date_col}" AS INTEGER)), MAX(CAST("{date_col}" AS INTEGER))'
                        f' FROM imbalance_prices'
                    ).fetchone()
                finally:
                    conn.close()
                if row and row[0]:
                    min_d, max_d = str(int(row[0])), str(int(row[1]))
                    min_date = f"{min_d[:4]}/{min_d[4:6]}/{min_d[6:]}"
                    max_date = f"{max_d[:4]}/{max_d[4:6]}/{max_d[6:]}"
                    msg = (f"{target_date} のデータがありません。\n"
                           f"(DBに保存されている期間: {min_date} ~ {max_date})")
                else:
                    msg = "DBに有効なデータがありません。"
            except Exception:
                msg = "DBに有効なデータがありません。"

            self.status_label.setText("データなし")
            self.status_label.setStyleSheet("color: red;")
            QMessageBox.information(self, "通知", msg)
            return

        selected_type = self.type_combo.currentText()
        target_cols = yojo_cols if selected_type == "余剰インバランス料金単価" else fusoku_cols
        display_columns = [time_col] + target_cols

        # --- 1. 테이블 그리기 ---
        self.table.setUpdatesEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(display_columns))
        self.table.setHorizontalHeaderLabels(display_columns)
        self.table.setRowCount(len(df))

        for row_idx, (_, row_data) in enumerate(df[display_columns].iterrows()):
            for col_idx, value in enumerate(row_data):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                if col_idx > 0:
                    try:
                        val = float(str(value).replace(',', ''))
                        if val >= 40:
                            item.setBackground(QBrush(QColor('#000000')))
                            item.setForeground(QBrush(QColor('#FF4444')))
                            f = item.font()
                            f.setBold(True)
                            item.setFont(f)
                        elif val >= 20:
                            item.setBackground(QBrush(QColor('#FF6666')))
                        elif val >= 15:
                            item.setBackground(QBrush(QColor('#FFA500')))
                        elif val >= 10:
                            item.setBackground(QBrush(QColor('#90EE90')))
                        elif val >= 0:
                            item.setBackground(QBrush(QColor('#87CEEB')))
                    except (ValueError, TypeError):
                        pass
                self.table.setItem(row_idx, col_idx, item)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        if display_columns:
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.setUpdatesEnabled(True)

        # --- 2. 그래프 그리기 ---
        self.plot_widget.clear()
        self._clear_legend_panel()
        self.curves = {}
        self._x_labels = df[time_col].astype(str).tolist()
        x_indices = list(range(len(self._x_labels)))

        # clear() 후 grid가 제거되므로 재적용
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)

        # X축 눈금: 4 코마(2시간) 간격으로 표시
        step = 4
        ticks = [(i, s) for i, s in enumerate(self._x_labels) if i % step == 0]
        self.plot_widget.getAxis('bottom').setTicks([ticks])

        self.plot_widget.setTitle(
            f"{selected_type}  ({target_date})",
            color='#333333', size='11pt',
        )

        for idx, col in enumerate(target_cols):
            color = COLORS[idx % len(COLORS)]
            try:
                y_values = pd.to_numeric(
                    df[col].astype(str).str.replace(',', ''), errors='coerce'
                ).tolist()
                curve = self.plot_widget.plot(
                    x_indices, y_values,
                    pen=pg.mkPen(color=color, width=2.5),
                    symbol='o',
                    symbolSize=5,
                    symbolBrush=pg.mkBrush(color),
                    symbolPen=pg.mkPen('white', width=1.5),
                )
                self.curves[col] = curve

                btn = LegendButton(col, color)
                btn.toggled.connect(self.on_legend_toggle)
                self.legend_layout.insertWidget(self.legend_layout.count() - 1, btn)
                self.legend_buttons[col] = btn
            except Exception:
                pass

        # 확대/축소 상태를 초기화하여 모든 데이터가 보이게 함
        self.plot_widget.enableAutoRange()

        self.status_label.setText(f"{target_date} 表示完了")
        self.status_label.setStyleSheet("color: green;")

    def on_legend_toggle(self, col_name, visible):
        if col_name in self.curves:
            self.curves[col_name].setVisible(visible)

    def on_hover(self, evt):
        pos = evt[0]
        vb = self.plot_widget.plotItem.vb
        if not vb.sceneBoundingRect().contains(pos):
            self.tooltip_label.hide()
            return

        mouse_point = vb.mapSceneToView(pos)
        x_idx = round(mouse_point.x())

        if not self._x_labels or not (0 <= x_idx < len(self._x_labels)):
            self.tooltip_label.hide()
            return

        # 마우스 Y 위치에 가장 가까운 선을 찾아 툴팁 표시
        best_col, best_y = None, None
        best_dist = float('inf')
        for col, curve in self.curves.items():
            if not curve.isVisible():
                continue
            _, yd = curve.getData()
            if yd is None or x_idx >= len(yd):
                continue
            y_val = float(yd[x_idx])
            if pd.isna(y_val):
                continue
            dist = abs(y_val - mouse_point.y())
            if dist < best_dist:
                best_dist, best_col, best_y = dist, col, y_val

        if best_col is None:
            self.tooltip_label.hide()
            return

        self.tooltip_label.setText(
            f"エリア: {best_col}\n時刻: {self._x_labels[x_idx]}\n単価: {best_y:,.2f} 円"
        )
        self.tooltip_label.adjustSize()

        # 마우스 커서 근처에 표시 (뷰포트 경계 내로 클램프)
        vp = self.plot_widget.viewport()
        widget_pos = vp.mapFromGlobal(
            self.plot_widget.mapToGlobal(self.plot_widget.mapFromScene(pos))
        )
        tx = int(widget_pos.x()) + 15
        ty = int(widget_pos.y()) - self.tooltip_label.height() - 8
        tx = min(tx, vp.width() - self.tooltip_label.width() - 4)
        ty = max(ty, 4)
        self.tooltip_label.move(tx, ty)
        self.tooltip_label.raise_()
        self.tooltip_label.show()

    def select_all_lines(self):
        for col, btn in self.legend_buttons.items():
            btn.set_active(True)
            if col in self.curves:
                self.curves[col].setVisible(True)

    def deselect_all_lines(self):
        for col, btn in self.legend_buttons.items():
            btn.set_active(False)
            if col in self.curves:
                self.curves[col].setVisible(False)

    def copy_graph_to_clipboard(self):
        pixmap = self.plot_widget.grab()
        QApplication.clipboard().setPixmap(pixmap)
        QMessageBox.information(
            self, "完了",
            "グラフ画像をクリップボードにコピーしました。\n(Excel等に貼り付け可能です)"
        )

    def _check_high_price_alerts(self):
        """DB更新後、本日データで40円超のコマが新たに出現した場合に警告する"""
        from datetime import datetime as dt_now
        now = dt_now.now()
        today_yyyymmdd = int(now.strftime("%Y%m%d"))  # 常に今日のデータを対象

        try:
            conn = sqlite3.connect('imbalance_data.db')
            try:
                cursor = conn.execute('SELECT * FROM imbalance_prices LIMIT 0')
                col_names = [desc[0].strip().replace('\ufeff', '') for desc in cursor.description]
                date_col = col_names[DATE_COL_IDX]
                df = pd.read_sql(
                    f'SELECT * FROM imbalance_prices WHERE CAST("{date_col}" AS INTEGER) = ?',
                    conn, params=[today_yyyymmdd]
                )
                df.columns = [c.strip().replace('\ufeff', '') for c in df.columns]
            finally:
                conn.close()
        except Exception:
            return

        if df.empty:
            return

        # 余剰・不足 両方のエリア列をチェック
        check_cols = [
            col for idx, col in enumerate(df.columns)
            if (YOJO_START_COL_IDX <= idx <= YOJO_END_COL_IDX
                or idx >= FUSOKU_START_COL_IDX)
            and '変更S' not in str(col)
        ]
        time_col = df.columns[TIME_COL_IDX]

        new_alerts = []
        for _, row in df.iterrows():
            slot_label = str(row[time_col])
            for col in check_cols:
                try:
                    val = float(str(row[col]).replace(',', ''))
                    if val >= 40:
                        key = (today_yyyymmdd, slot_label, col)
                        if key not in self._alerted_high_prices:
                            self._alerted_high_prices.add(key)
                            new_alerts.append((slot_label, col, val))
                except (ValueError, TypeError):
                    pass

        if new_alerts:
            lines = "\n".join(
                f"  コマ {slot}  |  {area}:  {val:,.1f} 円"
                for slot, area, val in new_alerts
            )
            QMessageBox.warning(
                self, "⚠ インバランス単価 警告",
                f"本日データに40円超のインバランス単価が発生しました。\n\n{lines}"
            )
