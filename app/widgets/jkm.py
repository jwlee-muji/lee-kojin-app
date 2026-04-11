"""
JKM（Japan Korea Marker）LNG スポット価格ウィジェット

データソース: Yahoo Finance (yfinance)
  シンボル: JKM=F (LNG Japan Korea Marker Platts Swap Futures, USD/MMBtu)
  取得方法: yf.Ticker('JKM=F').history() — APIキー不要・完全無料
"""
import sqlite3
import yfinance as yf
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDateEdit, QMessageBox, QHeaderView, QApplication, QSplitter,
    QTableWidgetItem,
)
from PySide6.QtCore import QThread, Signal, QDate, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont
from .common import ExcelCopyTableWidget

pg.setConfigOptions(antialias=True)

DB_PATH = 'jkm_data.db'
TICKER  = 'JKM=F'


def _init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS jkm_prices (
            date  TEXT PRIMARY KEY,
            open  REAL,
            high  REAL,
            low   REAL,
            close REAL NOT NULL
        )
    ''')
    conn.commit()
    conn.close()


def _to_float(val):
    try:
        f = float(val)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _save(rows: list) -> int:
    if not rows:
        return 0
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.executemany(
            "INSERT OR REPLACE INTO jkm_prices (date, open, high, low, close) VALUES (?,?,?,?,?)",
            rows,
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


class FetchJkmWorker(QThread):
    finished = Signal(int)
    error    = Signal(str)

    def run(self):
        try:
            hist = yf.Ticker(TICKER).history(period='max')
            if hist.empty:
                self.error.emit(f"Yahoo Finance からデータを取得できませんでした (シンボル: {TICKER})")
                return
            rows = [
                (
                    dt_idx.strftime('%Y-%m-%d'),
                    _to_float(row.get('Open')),
                    _to_float(row.get('High')),
                    _to_float(row.get('Low')),
                    float(row['Close']),
                )
                for dt_idx, row in hist.iterrows()
            ]
            self.finished.emit(_save(rows))
        except Exception as e:
            self.error.emit(str(e))


class JkmWidget(QWidget):
    def __init__(self):
        super().__init__()
        _init_db()
        self._worker = None
        self._dates  = []
        self._closes = []

        self._build_ui()
        self._refresh_chart()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_fetch)
        self.timer.start(3 * 60 * 60 * 1000)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 상단 컨트롤
        top = QHBoxLayout()
        title = QLabel("JKM LNG スポット価格 (USD/MMBtu)")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        top.addWidget(title)
        top.addSpacing(20)

        self.fetch_btn = QPushButton("Yahoo Finance から取込")
        self.fetch_btn.setStyleSheet("background-color: #e6f7ff;")
        self.fetch_btn.clicked.connect(self._on_fetch)
        top.addWidget(self.fetch_btn)

        top.addSpacing(16)
        top.addWidget(QLabel("表示期間:"))

        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate().addMonths(-6))
        self.start_date.setDisplayFormat("yyyy/MM/dd")
        top.addWidget(self.start_date)

        top.addWidget(QLabel("〜"))

        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())
        self.end_date.setDisplayFormat("yyyy/MM/dd")
        top.addWidget(self.end_date)

        self.show_btn = QPushButton("表示")
        self.show_btn.clicked.connect(self._refresh_chart)
        top.addWidget(self.show_btn)

        self.status_label = QLabel("待機中")
        self.status_label.setStyleSheet("color: gray; font-weight: bold;")
        top.addWidget(self.status_label)
        top.addStretch()
        layout.addLayout(top)

        # 그래프 복사 버튼
        _btn_style = (
            "QPushButton { font-size: 11px; color: #555; border: 1px solid #ddd;"
            " border-radius: 4px; padding: 3px 10px; background: #f5f5f5; }"
            "QPushButton:hover { background: #e8e8e8; }"
        )
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(6, 2, 6, 2)
        self.copy_btn = QPushButton("グラフ画像をコピー")
        self.copy_btn.setStyleSheet(_btn_style)
        self.copy_btn.clicked.connect(self._copy_graph)
        toolbar.addStretch()
        toolbar.addWidget(self.copy_btn)
        layout.addLayout(toolbar)

        # 스플리터: 테이블(좌) + 그래프(우)
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, 1)

        self.table = ExcelCopyTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["日付", "終値\n(USD/MMBtu)", "高値", "安値", "前日比(%)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("alternate-background-color: #f9f9f9; background-color: #ffffff;")
        splitter.addWidget(self.table)

        self.plot_widget = pg.PlotWidget()
        self._init_plot_style()
        splitter.addWidget(self.plot_widget)
        splitter.setSizes([450, 550])
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)

        # 호버 툴팁
        self.tooltip_label = QLabel(self.plot_widget.viewport())
        self.tooltip_label.setStyleSheet(
            "QLabel { background-color: white; border: 1px solid #cccccc;"
            " border-radius: 6px; padding: 7px 10px; color: #333333; }"
        )
        self.tooltip_label.setFont(QFont("", 9))
        self.tooltip_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.tooltip_label.hide()

        self.hover_proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self._on_hover
        )

    def _init_plot_style(self):
        self.plot_widget.setBackground('#ffffff')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.plotItem.hideAxis('top')
        self.plot_widget.plotItem.hideAxis('right')
        for ax_name in ('left', 'bottom'):
            ax = self.plot_widget.getAxis(ax_name)
            ax.setPen(pg.mkPen(color='#dddddd', width=1))
            ax.setTextPen(pg.mkPen('#666666'))
        self.plot_widget.setLabel('left',   'USD/MMBtu', color='#666666', size='9pt')
        self.plot_widget.setLabel('bottom', '日付',       color='#666666', size='9pt')

    def _on_fetch(self):
        if self._worker and self._worker.isRunning():
            return
        self.fetch_btn.setEnabled(False)
        self.status_label.setText("取込中...")
        self.status_label.setStyleSheet("color: blue; font-weight: bold;")
        self._worker = FetchJkmWorker()
        self._worker.finished.connect(self._on_fetch_done)
        self._worker.error.connect(self._on_fetch_error)
        self._worker.start()

    def _on_fetch_done(self, count: int):
        self.fetch_btn.setEnabled(True)
        self.status_label.setText(f"取込完了: {count}件")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")
        self._refresh_chart()

    def _on_fetch_error(self, err: str):
        self.fetch_btn.setEnabled(True)
        self.status_label.setText("取込失敗")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        QMessageBox.warning(self, "取込エラー", err)

    def _refresh_chart(self):
        start = self.start_date.date().toString("yyyy-MM-dd")
        end   = self.end_date.date().toString("yyyy-MM-dd")
        try:
            conn = sqlite3.connect(DB_PATH)
            rows = conn.execute(
                "SELECT date, close, high, low FROM jkm_prices "
                "WHERE date BETWEEN ? AND ? ORDER BY date",
                (start, end),
            ).fetchall()
            conn.close()
        except Exception as e:
            self.status_label.setText(f"DBエラー: {e}")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            return

        if not rows:
            self.table.setRowCount(0)
            self.plot_widget.clear()
            self.status_label.setText(
                "DBにデータがありません。「Yahoo Finance から取込」で取得してください。"
            )
            self.status_label.setStyleSheet("color: gray; font-weight: bold;")
            return

        self._dates  = [r[0] for r in rows]
        self._closes = [r[1] for r in rows]
        highs        = [r[2] for r in rows]
        lows         = [r[3] for r in rows]

        self._update_table(highs, lows)
        self._update_chart()
        self.status_label.setText(
            f"表示: {len(rows)}件  最新: {self._closes[-1]:.3f} USD/MMBtu  ({self._dates[-1]})"
        )
        self.status_label.setStyleSheet("color: green; font-weight: bold;")

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
                chg.setForeground(QBrush(QColor('#cc0000') if pct < 0 else QColor('#006600')))
                self.table.setItem(i, 4, chg)
            else:
                self.table.setItem(i, 4, self._create_table_item("—"))

        self.table.setUpdatesEnabled(True)

    def _update_chart(self):
        self.plot_widget.clear()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        x = list(range(len(self._dates)))
        self.plot_widget.plot(
            x, self._closes,
            pen=pg.mkPen(color='#2196F3', width=2.5),
            symbol='o', symbolSize=4,
            symbolBrush=pg.mkBrush('#2196F3'),
            symbolPen=pg.mkPen('white', width=1),
        )
        step  = max(1, len(self._dates) // 10)
        ticks = [(i, d) for i, d in enumerate(self._dates) if i % step == 0]
        self.plot_widget.getAxis('bottom').setTicks([ticks])
        self.plot_widget.setTitle(
            f"JKM (JKM=F)  {self._dates[0]} 〜 {self._dates[-1]}"
            f"  最新: {self._closes[-1]:.3f} USD/MMBtu",
            color='#333333', size='11pt',
        )
        self.plot_widget.enableAutoRange()

    def _on_hover(self, evt):
        pos = evt[0]
        vb  = self.plot_widget.plotItem.vb
        if not vb.sceneBoundingRect().contains(pos):
            self.tooltip_label.hide()
            return

        x_idx = round(vb.mapSceneToView(pos).x())
        if not self._dates or not (0 <= x_idx < len(self._dates)):
            self.tooltip_label.hide()
            return

        self.tooltip_label.setText(
            f"日付: {self._dates[x_idx]}\n終値: {self._closes[x_idx]:.3f} USD/MMBtu"
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
            self, "完了",
            "グラフ画像をクリップボードにコピーしました。\n(Excel等に貼り付け可能です)",
        )
