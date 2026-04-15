"""
JKM（Japan Korea Marker）LNG スポット価格ウィジェット

データソース: Yahoo Finance (yfinance)
  シンボル: JKM=F (LNG Japan Korea Marker Platts Swap Futures, USD/MMBtu)
  取得方法: yf.Ticker('JKM=F').history() — APIキー不要・完全無料
"""
import logging
import pyqtgraph as pg
import sqlite3
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDateEdit, QMessageBox, QHeaderView, QApplication, QSplitter,
    QTableWidgetItem, QGraphicsDropShadowEffect
)
from PySide6.QtCore import QThread, Signal, QDate, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont
from app.ui.common import ExcelCopyTableWidget, BaseWidget, BasePlotWidget
from app.core.config import JKM_TICKER, DB_JKM, load_settings
from app.core.database import get_db_connection
from app.core.i18n import tr
from app.api.jkm_api import FetchJkmWorker
from app.core.events import bus

pg.setConfigOptions(antialias=True)

logger = logging.getLogger(__name__)


class JkmWidget(BaseWidget):
    def __init__(self):
        super().__init__()
        self._worker = None
        self._dates  = []
        self._closes = []
        self._last_highs = []
        self._last_lows = []

        self._build_ui()
        self._refresh_chart()

        # 다른 위젯과 API 요청이 겹치지 않도록 30초 지연 후 정규 타이머 시작
        self.setup_timer(self.settings.get("jkm_interval", 180), self._on_fetch, stagger_seconds=30)
        
    def apply_settings_custom(self):
        self.update_timer_interval(self.settings.get("jkm_interval", 180))

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 상단 컨트롤
        top = QHBoxLayout()
        title = QLabel(tr("JKM LNG スポット価格 (USD/MMBtu)"))
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        top.addWidget(title)
        top.addSpacing(20)

        self.fetch_btn = QPushButton(tr("Yahoo Finance から取込"))
        self.fetch_btn.clicked.connect(self._on_fetch)
        top.addWidget(self.fetch_btn)

        top.addSpacing(16)
        top.addWidget(QLabel(tr("表示期間:")))

        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate().addMonths(-6))
        self.start_date.setDisplayFormat("yyyy/MM/dd")
        top.addWidget(self.start_date)

        top.addWidget(QLabel(tr("〜")))

        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())
        self.end_date.setDisplayFormat("yyyy/MM/dd")
        top.addWidget(self.end_date)

        self.show_btn = QPushButton(tr("表示"))
        self.show_btn.clicked.connect(self._refresh_chart)
        top.addWidget(self.show_btn)

        self.status_label = QLabel(tr("待機中"))
        self.status_label.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        top.addWidget(self.status_label)
        top.addStretch()
        layout.addLayout(top)

        # 그래프 복사 버튼
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(6, 2, 6, 2)
        self.copy_btn = QPushButton(tr("グラフ画像をコピー"))
        self.copy_btn.clicked.connect(self._copy_graph)
        
        self.reset_zoom_btn = QPushButton(tr("ビュー初期化"))
        self.reset_zoom_btn.clicked.connect(lambda: self.plot_widget.enableAutoRange())
        toolbar.addStretch()
        toolbar.addWidget(self.reset_zoom_btn)
        toolbar.addWidget(self.copy_btn)
        layout.addLayout(toolbar)

        # 스플리터: 테이블(좌) + 그래프(우)
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, 1)

        self.table = ExcelCopyTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([tr("日付"), tr("終値\n(USD/MMBtu)"), tr("高値"), tr("安値"), tr("前日比(%)")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        splitter.addWidget(self.table)

        self.plot_widget = BasePlotWidget(y_label="USD/MMBtu", x_label=tr("日付"))
        splitter.addWidget(self.plot_widget)
        splitter.setSizes([450, 550])
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)

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

        self.hover_point = pg.PlotDataItem(pen=None, symbol='o', symbolSize=12, zValue=10)
        self.plot_widget.addItem(self.hover_point)

        self.hover_proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self._on_hover
        )
        
    def apply_theme_custom(self):
        is_dark = self.is_dark
        self.plot_widget.set_theme(is_dark)
        self.tooltip_label.setStyleSheet(
            f"QLabel {{ background-color: {'#252526' if is_dark else '#ffffff'}; "
            f"border: 1px solid {'#444444' if is_dark else '#cccccc'}; "
            f"border-radius: 6px; padding: 7px 10px; color: {'#d4d4d4' if is_dark else '#333333'}; }}"
        )
        
        if hasattr(self, 'tooltip_shadow'):
            self.tooltip_shadow.setColor(QColor(0, 0, 0, 160) if is_dark else QColor(0, 0, 0, 60))
        if self._dates:
            self.plot_widget.setTitle(f"JKM (JKM=F)  {self._dates[0]} 〜 {self._dates[-1]}  {tr('最新')}: {self._closes[-1]:.3f} USD/MMBtu", color='#cccccc' if is_dark else '#333333', size='11pt')
            self._update_table(self._last_highs, self._last_lows)

    def _on_fetch(self):
        if not self.check_online_status(): return
        try:
            if self._worker and self._worker.isRunning():
                return
        except RuntimeError:
            self._worker = None
        self.fetch_btn.setEnabled(False)
        self.status_label.setText(tr("データ取得中..."))
        self.status_label.setStyleSheet("color: #64b5f6; font-weight: bold;")
        self._worker = FetchJkmWorker()
        self._worker.finished.connect(self._on_fetch_done)
        self._worker.error.connect(self._on_fetch_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()
        self.track_worker(self._worker)

    def _on_fetch_done(self, count: int):
        self.fetch_btn.setEnabled(True)
        self.status_label.setText(f"{tr('取得完了')}: {count}")
        self.status_label.setStyleSheet("color: #4caf50; font-weight: bold;")
        self._refresh_chart()
        bus.jkm_updated.emit()

    def _on_fetch_error(self, err: str):
        self.fetch_btn.setEnabled(True)
        self.status_label.setText(tr("取得失敗"))
        self.status_label.setStyleSheet("color: #ff5252; font-weight: bold;")
        QMessageBox.warning(self, tr("エラー"), err)

    def _refresh_chart(self):
        start_qdate = self.start_date.date()
        end_qdate   = self.end_date.date()
        if start_qdate > end_qdate:
            self.status_label.setText(tr("開始日は終了日以前である必要があります。"))
            self.status_label.setStyleSheet("color: #ff5252; font-weight: bold;")
            return
        start = start_qdate.toString("yyyy-MM-dd")
        end   = end_qdate.toString("yyyy-MM-dd")
        try:
            with get_db_connection(DB_JKM) as conn:
                rows = conn.execute(
                    "SELECT date, close, high, low FROM jkm_prices "
                    "WHERE date BETWEEN ? AND ? ORDER BY date",
                    (start, end),
                ).fetchall()
        except sqlite3.Error as e:
            self.status_label.setText(tr("DBエラー: {0}").format(e))
            self.status_label.setStyleSheet("color: #ff5252; font-weight: bold;")
            return

        if not rows:
            self.table.setRowCount(0)
            self.plot_widget.clear()
            self.status_label.setText(
                tr("DBにデータがありません。「Yahoo Finance から取込」で取得してください。")
            )
            self.status_label.setStyleSheet("color: #aaaaaa; font-weight: bold;")
            return

        self._dates  = [r[0] for r in rows]
        self._closes = [r[1] for r in rows]
        self._last_highs = [r[2] for r in rows]
        self._last_lows  = [r[3] for r in rows]

        self._update_table(self._last_highs, self._last_lows)
        self._update_chart()
        self.status_label.setText(
            tr("表示: {0}件  最新: {1} USD/MMBtu  ({2})").format(len(rows), f"{self._closes[-1]:.3f}", self._dates[-1])
        )
        self.status_label.setStyleSheet("color: #4caf50; font-weight: bold;")

    def _create_table_item(self, text):
        it = QTableWidgetItem(text)
        it.setTextAlignment(Qt.AlignCenter)
        return it

    def _update_table(self, highs, lows):
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(self._dates))

        rev = list(zip(reversed(self._dates), reversed(self._closes), reversed(highs), reversed(lows)))
        for i, (d, c, h, l) in enumerate(rev):
            self.table.setItem(i, 0, self._create_table_item(d))
            self.table.setItem(i, 1, self._create_table_item(f"{c:.3f}" if c is not None else "—"))
            self.table.setItem(i, 2, self._create_table_item(f"{h:.3f}" if h is not None else "—"))
            self.table.setItem(i, 3, self._create_table_item(f"{l:.3f}" if l is not None else "—"))

            orig_i = len(self._dates) - 1 - i
            if orig_i > 0:
                prev = self._closes[orig_i - 1]
                pct  = (c - prev) / prev * 100 if prev else 0
                chg  = self._create_table_item(f"{pct:+.2f}%")
                chg.setForeground(QBrush(QColor(('#ff6666' if self.is_dark else '#d32f2f') if pct < 0 else ('#4caf50' if self.is_dark else '#388e3c'))))
                self.table.setItem(i, 4, chg)
            else:
                self.table.setItem(i, 4, self._create_table_item("—"))

        self.table.setUpdatesEnabled(True)

    def _update_chart(self):
        self.plot_widget.clear()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        x = list(range(len(self._dates)))
        
        brush_color = QColor('#2196F3')
        brush_color.setAlpha(50)
        self.plot_widget.plot(
            x, self._closes,
            pen=pg.mkPen(color='#2196F3', width=2.5),
            fillLevel=0, brush=pg.mkBrush(brush_color),
            symbol='o', symbolSize=4,
            symbolBrush=pg.mkBrush('#2196F3'),
            symbolPen=pg.mkPen('white', width=1),
        )
        step  = max(1, len(self._dates) // 10)
        ticks = [(i, d) for i, d in enumerate(self._dates) if i % step == 0]
        self.plot_widget.getAxis('bottom').setTicks([ticks])
        self.plot_widget.setTitle(
            f"JKM (JKM=F)  {self._dates[0]} 〜 {self._dates[-1]}"
            f"  {tr('最新')}: {self._closes[-1]:.3f} USD/MMBtu",
            color='#cccccc' if self.is_dark else '#333333', size='11pt',
        )
        
        # 뷰포트 제한
        self.plot_widget.getViewBox().setLimits(xMin=-1, xMax=max(1, len(self._dates)), yMin=0)
        self.plot_widget.enableAutoRange()
        
        # clear()로 인해 캔버스에서 삭제된 호버 마커를 다시 추가
        self.plot_widget.addItem(self.hover_point)

    def _on_hover(self, evt):
        pos = evt[0]
        vb  = self.plot_widget.plotItem.vb
        if not vb.sceneBoundingRect().contains(pos):
            self.tooltip_label.hide()
            self.hover_point.setData([], [])
            self._last_hover_x = None
            return

        x_idx = round(vb.mapSceneToView(pos).x())
        if not self._dates or not (0 <= x_idx < len(self._dates)):
            self.tooltip_label.hide()
            self.hover_point.setData([], [])
            self._last_hover_x = None
            return

        # 동일한 X축 상에서 마우스가 움직일 때는 데이터 갱신 스킵
        if getattr(self, '_last_hover_x', None) != x_idx:
            self._last_hover_x = x_idx
            y_val = self._closes[x_idx]
            bg_color = '#1e1e1e' if getattr(self, 'is_dark', True) else '#ffffff'
            self.hover_point.setData([x_idx], [y_val])
            self.hover_point.setSymbolBrush(pg.mkBrush('#2196F3'))
            self.hover_point.setSymbolPen(pg.mkPen(bg_color, width=1.5))
            self.tooltip_label.setText(
                f"{tr('日付')}: {self._dates[x_idx]}\n{tr('終値')}: {self._closes[x_idx]:.3f} USD/MMBtu"
            )
            self.tooltip_label.adjustSize()

        vp  = self.plot_widget.viewport()
        wpos = vp.mapFromGlobal(self.plot_widget.mapToGlobal(self.plot_widget.mapFromScene(pos)))
        tx = min(int(wpos.x()) + 15, vp.width()  - self.tooltip_label.width()  - 4)
        ty = max(int(wpos.y()) - self.tooltip_label.height() - 8, 4)
        self.tooltip_label.move(tx, ty)
        self.tooltip_label.raise_()
        self.tooltip_label.show()

    def _copy_graph(self):
        QApplication.clipboard().setPixmap(self.plot_widget.grab())
        QMessageBox.information(
            self, tr("完了"),
            tr("グラフ画像をクリップボードにコピーしました。\n(Excel等に貼り付け可能です)"),
        )
