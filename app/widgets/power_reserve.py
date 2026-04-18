import re
import csv
import logging
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidgetItem,
    QPushButton, QMessageBox, QHeaderView, QDateEdit, QFileDialog,
    QApplication, QSystemTrayIcon, QCheckBox, QSizePolicy, QFrame,
)
from PySide6.QtCore import QDate, Qt, QRect
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from app.ui.common import ExcelCopyTableWidget, BaseWidget
from app.ui.theme import UIColors
from app.core.config import load_settings
from app.core.i18n import tr
from app.api.power_reserve_api import FetchPowerReserveWorker
from app.core.events import bus

logger = logging.getLogger(__name__)

# ヒートマップ描画マージン (px)
_HM_ML = 70   # 左: エリアラベル
_HM_MT = 6    # 上
_HM_MR = 80   # 右: 凡例
_HM_MB = 30   # 下: 時刻ラベル


class ReserveHeatmapWidget(QWidget):
    """
    エリア別予備率ヒートマップ。QPainter 直接描画。
    X 軸: 時刻コマ / Y 軸: エリア / セル色: 予備率レベル。
    ホバー: ゼロ遅延のインライン情報パネルを表示。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._regions:  list[str]       = []
        self._rows:     list[list[str]] = []
        self._is_dark    = True
        self._low_th     = 8.0
        self._warn_th    = 10.0
        self._is_today   = False
        self._is_past_day = False
        # ホバー状態
        self._hover_ci  = -1
        self._hover_ri  = -1
        self._hover_mx  = 0
        self._hover_my  = 0
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

    # ── データ更新 ────────────────────────────────────────────────────────────
    def update_data(
        self,
        headers:      list[str],
        rows:         list[list[str]],
        is_dark:      bool,
        low_th:       float,
        warn_th:      float,
        is_today:     bool = False,
        is_past_day:  bool = False,
    ):
        self._regions     = headers[1:] if len(headers) > 1 else []
        self._rows        = rows
        self._is_dark     = is_dark
        self._low_th      = low_th
        self._warn_th     = warn_th
        self._is_today    = is_today
        self._is_past_day = is_past_day
        # ホバー状態リセット (新データで位置がズレるため)
        self._hover_ci = -1
        self._hover_ri = -1
        self.update()

    # ── ヘルパー ──────────────────────────────────────────────────────────────
    def _val_color(self, val_str: str) -> QColor:
        try:
            val = float(val_str.replace('%', '').strip())
        except (ValueError, AttributeError):
            return QColor('#252525' if self._is_dark else '#e0e0e0')
        if val <= self._low_th:
            return QColor('#9b2335' if self._is_dark else '#ef9a9a')
        if val <= self._warn_th:
            return QColor('#9c6000' if self._is_dark else '#ffcc80')
        if val <= 15.0:
            return QColor('#1e6b2e' if self._is_dark else '#a5d6a7')
        if val <= 25.0:
            return QColor('#1255a0' if self._is_dark else '#90caf9')
        return QColor('#223587' if self._is_dark else '#c5cae9')

    @staticmethod
    def _slot_minutes(time_str: str) -> int:
        """'H:MM'/'HH:MM' → 深夜0時からの分数。解析失敗時 -1。"""
        try:
            h, m = str(time_str)[:5].split(':')
            return int(h) * 60 + int(m)
        except (ValueError, AttributeError, IndexError):
            return -1

    def _cell_at(self, mx: float, my: float) -> tuple[int, int]:
        """マウス座標からセル (col, row) インデックスを返す。範囲外は (-1, -1)。"""
        n_cols = len(self._rows)
        n_rows = len(self._regions)
        if n_cols == 0 or n_rows == 0:
            return -1, -1
        W, H   = self.width(), self.height()
        cell_w = (W - _HM_ML - _HM_MR) / n_cols
        cell_h = (H - _HM_MT - _HM_MB) / n_rows
        ci = int((mx - _HM_ML) / cell_w) if cell_w > 0 else -1
        ri = int((my - _HM_MT) / cell_h) if cell_h > 0 else -1
        if 0 <= ci < n_cols and 0 <= ri < n_rows:
            return ci, ri
        return -1, -1

    # ── マウスイベント ────────────────────────────────────────────────────────
    def mouseMoveEvent(self, event):
        mx, my = event.position().x(), event.position().y()
        ci, ri = self._cell_at(mx, my)
        # ホバー位置が変化した場合のみ再描画 (不要な repaint を排除)
        if ci != self._hover_ci or ri != self._hover_ri or \
           abs(mx - self._hover_mx) > 1 or abs(my - self._hover_my) > 1:
            self._hover_ci = ci
            self._hover_ri = ri
            self._hover_mx = int(mx)
            self._hover_my = int(my)
            self.update()

    def leaveEvent(self, event):
        if self._hover_ci >= 0:
            self._hover_ci = -1
            self._hover_ri = -1
            self.update()

    # ── 描画 ─────────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H    = self.width(), self.height()
        is_dark = self._is_dark

        # ① 背景
        bg = QColor('#1a1a1a' if is_dark else '#f5f5f5')
        p.fillRect(0, 0, W, H, bg)

        if not self._rows or not self._regions:
            p.setPen(QColor('#666666'))
            p.drawText(QRect(0, 0, W, H), Qt.AlignCenter, tr("データなし"))
            p.end()
            return

        n_cols = len(self._rows)
        n_rows = len(self._regions)
        grid_w = W - _HM_ML - _HM_MR
        grid_h = H - _HM_MT - _HM_MB
        if grid_w <= 0 or grid_h <= 0:
            p.end()
            return
        cell_w = grid_w / n_cols
        cell_h = grid_h / n_rows

        lbl_color  = QColor('#9e9e9e' if is_dark else '#616161')
        tick_step  = max(1, round(n_cols / 12))   # ~2時間ごと

        # ② セル描画
        p.setPen(Qt.NoPen)
        for ci, row_data in enumerate(self._rows):
            x      = int(_HM_ML + ci * cell_w)
            x_next = int(_HM_ML + (ci + 1) * cell_w)
            for ri in range(n_rows):
                val_str = row_data[ri + 1] if ri + 1 < len(row_data) else ""
                y      = int(_HM_MT + ri * cell_h)
                y_next = int(_HM_MT + (ri + 1) * cell_h)
                p.fillRect(
                    x, y,
                    max(1, x_next - x - 1),
                    max(1, y_next - y - 1),
                    self._val_color(val_str),
                )

        # ③ 過去コマのオーバーレイ
        #    本日: 現在時刻より前のコマだけ暗転
        #    過去日: 全コマ暗転 (すべて終了済み)
        past_brush = QColor(0, 0, 0, 70)
        if self._is_today:
            now_min = datetime.now().hour * 60 + datetime.now().minute
            p.setPen(Qt.NoPen)
            for ci, row_data in enumerate(self._rows):
                slot_min = self._slot_minutes(row_data[0] if row_data else "")
                if 0 <= slot_min < now_min:
                    x      = int(_HM_ML + ci * cell_w)
                    x_next = int(_HM_ML + (ci + 1) * cell_w)
                    p.fillRect(x, _HM_MT, max(1, x_next - x - 1), grid_h, past_brush)
        elif self._is_past_day:
            p.setPen(Qt.NoPen)
            p.fillRect(int(_HM_ML), _HM_MT, max(1, int(grid_w)), grid_h, past_brush)

        # ④ 2時間刻み縦区切り線 (サブテキスト: 時刻ラベルの基準)
        tick_pen = QPen(QColor('#333333' if is_dark else '#d0d0d0'), 1)
        p.setPen(tick_pen)
        for ci in range(0, n_cols, tick_step):
            x = int(_HM_ML + ci * cell_w)
            p.drawLine(x, _HM_MT, x, _HM_MT + grid_h)

        # ⑤ 現在時刻マーカー (破線 + 輝きライン)
        now_min  = datetime.now().hour * 60 + datetime.now().minute
        slot_min = 1440.0 / n_cols if n_cols else 1440.0
        now_slot = now_min / slot_min
        if 0.0 <= now_slot <= float(n_cols):
            cx = int(_HM_ML + now_slot * cell_w)
            # グロー効果: 太い半透明→細い実線の順に重ねる
            glow_c = QColor(255, 255, 255, 35) if is_dark else QColor(0, 0, 0, 20)
            p.setPen(QPen(glow_c, 5))
            p.drawLine(cx, _HM_MT, cx, _HM_MT + grid_h)
            line_c = QColor('#e0e0e0' if is_dark else '#333333')
            p.setPen(QPen(line_c, 1, Qt.DashLine))
            p.drawLine(cx, _HM_MT, cx, _HM_MT + grid_h)

        # ⑥ Y 軸ラベル (エリア名)
        font_y = p.font()
        font_y.setPixelSize(max(9, min(12, int(cell_h * 0.65))))
        p.setFont(font_y)
        p.setPen(lbl_color)
        for ri, name in enumerate(self._regions):
            y = int(_HM_MT + ri * cell_h)
            p.drawText(
                QRect(2, y, _HM_ML - 6, max(1, int(cell_h))),
                Qt.AlignVCenter | Qt.AlignRight, name,
            )

        # ⑦ X 軸ラベル (時刻)
        font_x = p.font()
        font_x.setPixelSize(9)
        p.setFont(font_x)
        p.setPen(lbl_color)
        for ci, row_data in enumerate(self._rows):
            if ci % tick_step != 0:
                continue
            time_str = str(row_data[0])[:5] if row_data else ""
            cx = _HM_ML + (ci + 0.5) * cell_w
            lx = max(0, int(cx - cell_w))
            p.drawText(
                QRect(lx, H - _HM_MB + 3, int(cell_w * 2), _HM_MB - 3),
                Qt.AlignCenter, time_str,
            )

        # ⑧ ホバーセル: ハイライト枠 + インライン情報パネル
        ci_h, ri_h = self._hover_ci, self._hover_ri
        if 0 <= ci_h < n_cols and 0 <= ri_h < n_rows:
            # ハイライト枠 (白/黒の2pxボーダー)
            hx = int(_HM_ML + ci_h * cell_w)
            hy = int(_HM_MT + ri_h * cell_h)
            hw = max(2, int(_HM_ML + (ci_h + 1) * cell_w) - hx - 1)
            hh = max(2, int(_HM_MT + (ri_h + 1) * cell_h) - hy - 1)
            hi_pen = QPen(QColor('#ffffff' if is_dark else '#333333'), 2)
            p.setPen(hi_pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(hx, hy, hw - 1, hh - 1)

            # 情報パネル: テキスト準備
            time_str = str(self._rows[ci_h][0])[:5] if self._rows[ci_h] else "?"
            region   = self._regions[ri_h]
            val_str  = (self._rows[ci_h][ri_h + 1]
                        if ri_h + 1 < len(self._rows[ci_h]) else "—")
            val_color = self._val_color(val_str)

            font_tt = p.font()
            font_tt.setPixelSize(11)
            font_tt.setBold(False)
            p.setFont(font_tt)
            fm = p.fontMetrics()

            line1 = f"{time_str}  {region}"
            line2 = val_str
            font_tt2 = p.font()
            font_tt2.setPixelSize(13)
            font_tt2.setBold(True)
            p.setFont(font_tt2)
            fm2 = p.fontMetrics()

            pad_x, pad_y = 10, 7
            dot       = 8
            line1_w   = fm.horizontalAdvance(line1)
            line2_w   = fm2.horizontalAdvance(line2)
            panel_w   = max(line1_w, dot + 4 + line2_w) + pad_x * 2
            panel_h   = fm.height() + fm2.height() + pad_y * 2 + 4

            # 位置: カーソル右側 → 右端を超えるなら左側
            mx_, my_ = self._hover_mx, self._hover_my
            px = mx_ + 14
            if px + panel_w > W - 4:
                px = mx_ - panel_w - 10
            py = my_ - panel_h // 2
            py = max(2, min(py, H - panel_h - 2))

            # パネル背景 + ボーダー
            p.setRenderHint(QPainter.Antialiasing, True)
            bg_tt = QColor(28, 28, 30, 230) if is_dark else QColor(255, 255, 255, 235)
            p.setPen(Qt.NoPen)
            p.setBrush(bg_tt)
            p.drawRoundedRect(px, py, panel_w, panel_h, 5, 5)
            bd_tt = QColor('#4a4a50' if is_dark else '#cccccc')
            p.setPen(QPen(bd_tt, 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(px, py, panel_w, panel_h, 5, 5)

            # Line1: 時刻 + エリア名 (細字)
            p.setFont(font_tt)
            p.setPen(QColor('#aaaaaa' if is_dark else '#666666'))
            p.drawText(px + pad_x, py + pad_y + fm.ascent(), line1)

            # Line2: 予備率 (太字 + カラードット)
            y2 = py + pad_y + fm.height() + 4
            p.setPen(Qt.NoPen)
            p.setBrush(val_color)
            p.drawEllipse(px + pad_x, y2 + (fm2.height() - dot) // 2, dot, dot)
            p.setPen(QColor('#ffffff' if is_dark else '#1a1a1a'))
            p.setFont(font_tt2)
            p.drawText(px + pad_x + dot + 5, y2 + fm2.ascent(), line2)

        # ⑨ 凡例
        legend = [
            (self._val_color(str(self._low_th)),    f"≤{self._low_th:.0f}%"),
            (self._val_color(str(self._warn_th)),   f"≤{self._warn_th:.0f}%"),
            (self._val_color("12"),                  "≤15%"),
            (self._val_color("20"),                  "≤25%"),
            (self._val_color("99"),                  ">25%"),
        ]
        lx, ly, box, gap = W - _HM_MR + 6, _HM_MT + 6, 10, 15
        bd_lg   = QPen(QColor('#444444' if is_dark else '#bbbbbb'), 1)
        font_lg = p.font()
        font_lg.setPixelSize(10)
        font_lg.setBold(False)
        p.setFont(font_lg)
        for color, label in legend:
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(lx, ly, box, box, 2, 2)
            p.setPen(bd_lg)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(lx, ly, box, box, 2, 2)
            p.setPen(lbl_color)
            p.drawText(lx + box + 4, ly + box - 1, label)
            ly += gap
        p.end()


class PowerReserveWidget(BaseWidget):
    def __init__(self):
        super().__init__()
        self._last_headers = []
        self._last_rows    = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ── コントロールバー ─────────────────────────────────────────────────
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)
        self.title_label  = QLabel(tr("エリア別 予備率 (5分自動更新)"))
        self.date_edit    = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setFixedHeight(30)
        self._btn_prev_day = QPushButton("◀"); self._btn_prev_day.setFixedSize(26, 30)
        self._btn_next_day = QPushButton("▶"); self._btn_next_day.setFixedSize(26, 30)
        self._btn_today    = QPushButton(tr("今日")); self._btn_today.setFixedHeight(30)
        self._btn_prev_day.clicked.connect(lambda: self.date_edit.setDate(self.date_edit.date().addDays(-1)))
        self._btn_next_day.clicked.connect(lambda: self.date_edit.setDate(self.date_edit.date().addDays(1)))
        self._btn_today.clicked.connect(lambda: self.date_edit.setDate(QDate.currentDate()))
        self.date_edit.dateChanged.connect(self.fetch_data)
        self.status_label = QLabel(tr("待機中"))
        self.status_label.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        self.refresh_btn  = QPushButton(tr("表示"))
        self.refresh_btn.clicked.connect(self.fetch_data)
        self.export_btn   = QPushButton(tr("Excel(CSV) 保存"))
        self.export_btn.clicked.connect(self._export_csv)

        self.show_table_cb = QCheckBox(tr("表表示"))
        self.show_table_cb.setChecked(True)
        self.show_table_cb.stateChanged.connect(self._toggle_views)
        self.show_map_cb = QCheckBox(tr("マップ表示"))
        self.show_map_cb.setChecked(True)
        self.show_map_cb.stateChanged.connect(self._toggle_views)

        top_layout.addWidget(self.title_label)
        top_layout.addWidget(self._btn_prev_day)
        top_layout.addWidget(self.date_edit)
        top_layout.addWidget(self._btn_next_day)
        top_layout.addWidget(self._btn_today)
        top_layout.addWidget(self.status_label)
        top_layout.addSpacing(10)
        top_layout.addWidget(self.show_table_cb)
        top_layout.addWidget(self.show_map_cb)
        top_layout.addStretch()
        top_layout.addWidget(self.export_btn)
        top_layout.addWidget(self.refresh_btn)
        layout.addLayout(top_layout)

        # ── テーブル ─────────────────────────────────────────────────────────
        self.table = ExcelCopyTableWidget()
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 3)

        # ── ヒートマップカード ────────────────────────────────────────────────
        self._heatmap_card = QFrame()
        self._heatmap_card.setObjectName("heatmapCard")
        card_layout = QVBoxLayout(self._heatmap_card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        self._hm_header = QWidget()
        self._hm_header.setObjectName("hmHeader")
        hm_hdr_layout = QHBoxLayout(self._hm_header)
        hm_hdr_layout.setContentsMargins(10, 5, 8, 5)
        hm_hdr_layout.setSpacing(8)
        self._hm_header_lbl = QLabel(tr("予備率ヒートマップ"))
        self.btn_copy_heatmap = QPushButton(tr("マップ画像をコピー"))
        self.btn_copy_heatmap.clicked.connect(self._copy_heatmap)
        hm_hdr_layout.addWidget(self._hm_header_lbl)
        hm_hdr_layout.addStretch()
        hm_hdr_layout.addWidget(self.btn_copy_heatmap)
        card_layout.addWidget(self._hm_header)

        self._hm_sep = QFrame()
        self._hm_sep.setFrameShape(QFrame.HLine)
        card_layout.addWidget(self._hm_sep)

        self.heatmap = ReserveHeatmapWidget()
        card_layout.addWidget(self.heatmap, 1)
        layout.addWidget(self._heatmap_card, 2)

        self.worker = None
        self._alerted_low_reserve = set()
        self.setup_timer(self.settings.get("reserve_interval", 5), self.fetch_data)
        self.fetch_data()
        self._apply_card_theme()

    # ── カードテーマ ─────────────────────────────────────────────────────────
    def _apply_card_theme(self):
        is_dark  = self.is_dark
        c_border = '#3e3e42' if is_dark else '#d0d0d0'
        c_header = '#252526' if is_dark else '#f0f0f0'
        c_sep    = '#3e3e42' if is_dark else '#d0d0d0'
        c_lbl    = '#888888' if is_dark else '#666666'
        self._heatmap_card.setStyleSheet(
            f"QFrame#heatmapCard {{ border: 1px solid {c_border}; }}"
        )
        self._hm_header.setStyleSheet(
            f"QWidget#hmHeader {{ background-color: {c_header}; }}"
        )
        self._hm_sep.setStyleSheet(f"color: {c_sep};")
        self._hm_header_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {c_lbl};"
            f" letter-spacing: 1px; background: transparent;"
        )

    # ── ビュー切替・コピー ────────────────────────────────────────────────────
    def _toggle_views(self):
        self.table.setVisible(self.show_table_cb.isChecked())
        self._heatmap_card.setVisible(self.show_map_cb.isChecked())

    def _copy_heatmap(self):
        QApplication.clipboard().setPixmap(self.heatmap.grab())

    # ── テーマ・設定 ─────────────────────────────────────────────────────────
    def apply_settings_custom(self):
        self.update_timer_interval(self.settings.get("reserve_interval", 5))
        if self._last_headers and self._last_rows:
            self._update_table(self._last_headers, self._last_rows)

    def set_loading(self, is_loading: bool):
        super().set_loading(is_loading, self.table)

    def apply_theme_custom(self):
        self._apply_card_theme()
        if self._last_headers and self._last_rows:
            self._update_table(self._last_headers, self._last_rows)

    # ── データ取得 ────────────────────────────────────────────────────────────
    def fetch_data(self):
        if not self.check_online_status():
            return
        try:
            if self.worker and self.worker.isRunning():
                return
        except RuntimeError:
            self.worker = None
        selected_date = self.date_edit.date().toString("yyyy-MM-dd")
        self.refresh_btn.setEnabled(False)
        self.set_loading(True)
        self.status_label.setText(tr("更新中..."))
        self.status_label.setStyleSheet("color: #64b5f6; font-weight: bold;")
        self.worker = FetchPowerReserveWorker(selected_date)
        self.worker.data_fetched.connect(self._update_table)
        self.worker.error.connect(self._handle_error)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()
        self.track_worker(self.worker)

    def _handle_error(self, err):
        self.set_loading(False)
        self.status_label.setText(tr("更新失敗"))
        self.status_label.setStyleSheet("color: #ff5252; font-weight: bold;")
        QMessageBox.warning(
            self, tr("エラー"),
            tr("データの取得中にエラーが発生しました:\n{0}").format(err),
        )
        self.refresh_btn.setEnabled(True)

    # ── テーブル & ヒートマップ更新 ──────────────────────────────────────────
    def _update_table(self, headers, rows):
        self.set_loading(False)
        self._last_rows = rows
        self.table.setUpdatesEnabled(False)

        if headers != self._last_headers or self.table.columnCount() != len(headers):
            self._last_headers = headers
            self.table.clear()
            self.table.setColumnCount(len(headers))
            self.table.setHorizontalHeaderLabels([tr(h) for h in headers])
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.Stretch)
            if headers:
                header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
                header.setMinimumSectionSize(80)
        else:
            self._last_headers = headers
            self.table.setRowCount(0)

        now           = datetime.now()
        selected_qd   = self.date_edit.date()
        selected_date = datetime(selected_qd.year(), selected_qd.month(), selected_qd.day())
        is_today      = selected_date.date() == now.date()
        is_past_day   = selected_date.date() <  now.date()
        threshold     = now + timedelta(minutes=30)
        new_alerts    = []

        low_th  = self.settings.get("reserve_low",  8.0)
        warn_th = self.settings.get("reserve_warn", 10.0)

        min_val  = 999.0
        min_area = ""
        min_time = ""

        for row_idx, row_data in enumerate(rows):
            self.table.insertRow(row_idx)

            is_past = is_past_day
            if not is_past and is_today and row_data:
                m = re.search(r'(\d{1,2}):(\d{2})', row_data[0])
                if m:
                    h, m_min = int(m.group(1)), int(m.group(2))
                    row_dt   = (datetime.combine(now.date(), datetime.min.time())
                                + timedelta(hours=h, minutes=m_min))
                    is_past  = row_dt < threshold

            for col_idx, cell_data in enumerate(row_data):
                item = QTableWidgetItem(cell_data)
                item.setTextAlignment(Qt.AlignCenter)
                val = None

                reserve_level = None
                if col_idx > 0:
                    try:
                        val = float(cell_data.replace('%', '').strip())
                        if is_today and val < min_val:
                            min_val  = val
                            min_area = headers[col_idx] if col_idx < len(headers) else f"Area{col_idx}"
                            min_time = row_data[0]
                        if   val <= low_th:  reserve_level = 'low'
                        elif val <= warn_th: reserve_level = 'warning'
                    except ValueError:
                        pass

                status_key = reserve_level if reserve_level else ('past' if is_past else None)
                if status_key:
                    bg, fg = UIColors.get_reserve_alert_colors(self.is_dark, status_key)
                    item.setBackground(QBrush(QColor(bg)))
                    item.setForeground(QBrush(QColor(fg)))

                self.table.setItem(row_idx, col_idx, item)

                if is_today and reserve_level == 'low' and val is not None:
                    area = headers[col_idx] if col_idx < len(headers) else f"Area{col_idx}"
                    key  = (row_data[0], area)
                    if key not in self._alerted_low_reserve:
                        self._alerted_low_reserve.add(key)
                        new_alerts.append((row_data[0], area, val))

            self.refresh_btn.setEnabled(True)

        if min_val != 999.0:
            bus.occto_updated.emit(min_time, tr(min_area), min_val)

        self.status_label.setText(tr("更新完了"))
        self.status_label.setStyleSheet("color: #4caf50; font-weight: bold;")
        self.table.setUpdatesEnabled(True)

        # ヒートマップ更新 (is_today/is_past_day を渡すことで過去コマ暗転を制御)
        self.heatmap.update_data(headers, rows, self.is_dark, low_th, warn_th, is_today, is_past_day)

        if new_alerts:
            display_alerts = new_alerts[:5]
            lines = "\n".join(
                f"  {t}  |  {tr(area)}:  {val}%" for t, area, val in display_alerts
            )
            if len(new_alerts) > 5:
                lines += "\n  " + tr("...他 {0}件の警告があります").format(len(new_alerts) - 5)

            timestamp   = datetime.now().strftime("%H:%M:%S")
            total_count = len(new_alerts)
            main_window = next(
                (w for w in QApplication.topLevelWidgets() if w.inherits("QMainWindow")), None
            )
            prefix    = tr(
                "本日のデータに予備率{0}%以下のコマが 【計 {1}件】 発生しています。"
            ).format(low_th, total_count)
            plain_msg  = prefix + f"\n\n{lines}"
            html_lines = lines.replace('\n', '<br>').replace('  ', '&nbsp;&nbsp;')
            html_msg   = prefix + f"<br><br>{html_lines}"
            title      = tr("⚠ 予備率警告 (計 {0}件) - {1}").format(total_count, timestamp)

            if main_window and hasattr(main_window, 'add_notification'):
                main_window.add_notification(title, plain_msg)

            if main_window and main_window.isHidden() and hasattr(main_window, 'tray_icon'):
                main_window.tray_icon.showMessage(
                    title, plain_msg, QApplication.instance().windowIcon(), 10000
                )
            else:
                QMessageBox.warning(self, title, html_msg)

    # ── CSV エクスポート ──────────────────────────────────────────────────────
    def _export_csv(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, tr("エラー"), tr("保存するデータがありません。"))
            return

        date_str = self.date_edit.date().toString('yyyyMMdd')
        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("CSV保存"), f"OCCTO_予備率_{date_str}.csv", "CSV Files (*.csv)"
        )
        if not file_path:
            return

        try:
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer  = csv.writer(f)
                headers = [
                    self.table.horizontalHeaderItem(i).text()
                    for i in range(self.table.columnCount())
                ]
                writer.writerow(headers)
                for row in range(self.table.rowCount()):
                    writer.writerow([
                        self.table.item(row, col).text() if self.table.item(row, col) else ""
                        for col in range(self.table.columnCount())
                    ])
            QMessageBox.information(
                self, tr("完了"),
                tr("CSVファイルとして保存しました。\nExcelで開くことができます。"),
            )
        except (IOError, csv.Error) as e:
            QMessageBox.warning(self, tr("エラー"), tr("保存に失敗しました:\n{0}").format(e))
