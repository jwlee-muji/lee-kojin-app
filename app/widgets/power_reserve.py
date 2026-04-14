import re
import csv
import logging
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidgetItem,
    QPushButton, QMessageBox, QHeaderView, QDateEdit, QFileDialog,
    QApplication, QSystemTrayIcon,
)
from PySide6.QtCore import QTimer, QThread, Signal, QDate, Qt
from PySide6.QtGui import QBrush, QColor
from app.ui.common import ExcelCopyTableWidget, BaseWidget
from app.ui.theme import UIColors
from app.core.config import load_settings
from app.core.i18n import tr
from app.api.power_reserve_api import FetchPowerReserveWorker
from app.core.events import bus

logger = logging.getLogger(__name__)


class PowerReserveWidget(BaseWidget):
    def __init__(self):
        super().__init__()
        self._last_headers = []
        self._last_rows = []
        layout = QVBoxLayout(self)

        top_layout = QHBoxLayout()
        self.title_label  = QLabel(tr("エリア別 予備率 (5分自動更新)"))
        self.date_edit    = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.status_label = QLabel(tr("待機中"))
        self.status_label.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        self.refresh_btn  = QPushButton(tr("表示"))
        self.refresh_btn.clicked.connect(self.fetch_data)
        self.export_btn   = QPushButton(tr("Excel(CSV) 保存"))
        self.export_btn.clicked.connect(self._export_csv)

        top_layout.addWidget(self.title_label)
        top_layout.addWidget(self.date_edit)
        top_layout.addWidget(self.status_label)
        top_layout.addStretch()
        top_layout.addWidget(self.export_btn)
        top_layout.addWidget(self.refresh_btn)
        layout.addLayout(top_layout)

        self.table = ExcelCopyTableWidget()
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        self.worker = None
        self._alerted_low_reserve = set()

        self.setup_timer(self.settings.get("reserve_interval", 5), self.fetch_data)

        self.fetch_data()
        
    def apply_settings_custom(self):
        self.update_timer_interval(self.settings.get("reserve_interval", 5))
        if self._last_headers and self._last_rows:
            self._update_table(self._last_headers, self._last_rows)

    def set_loading(self, is_loading: bool):
        super().set_loading(is_loading, self.table)

    def apply_theme_custom(self):
        if self._last_headers and self._last_rows:
            self._update_table(self._last_headers, self._last_rows)

    def fetch_data(self):
        if not self.check_online_status(): return
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
        self.worker.error_occurred.connect(self._handle_error)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()
        self.track_worker(self.worker)

    def _handle_error(self, err):
        self.set_loading(False)
        self.status_label.setText(tr("更新失敗"))
        self.status_label.setStyleSheet("color: #ff5252; font-weight: bold;")
        QMessageBox.warning(self, tr("エラー"), tr("データの取得中にエラーが発生しました:\n{0}").format(err))
        self.refresh_btn.setEnabled(True)

    def _update_table(self, headers, rows):
        self.set_loading(False)
        self._last_headers = headers
        self._last_rows    = rows
        self.table.setUpdatesEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels([tr(h) for h in headers])
        self.table.setRowCount(0)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        if headers:
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)

        now           = datetime.now()
        selected_qd   = self.date_edit.date()
        selected_date = datetime(selected_qd.year(), selected_qd.month(), selected_qd.day())
        is_today      = selected_date.date() == now.date()
        is_past_day   = selected_date.date() <  now.date()
        # 기준: 현재 시간보다 최소 30분 '이후'의 코마
        threshold     = now + timedelta(minutes=30)
        new_alerts    = []
        
        low_th = self.settings.get("reserve_low", 8.0)
        warn_th = self.settings.get("reserve_warn", 10.0)
        
        min_val = 999.0
        min_area = ""
        min_time = ""

        for row_idx, row_data in enumerate(rows):
            self.table.insertRow(row_idx)

            is_past = is_past_day
            row_dt  = None
            if not is_past and is_today and row_data:
                m = re.search(r'(\d{1,2}):(\d{2})', row_data[0])
                if m:
                    h, m_min = int(m.group(1)), int(m.group(2))
                    row_dt = datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=h, minutes=m_min)
                    is_past = row_dt < threshold

            for col_idx, cell_data in enumerate(row_data):
                item = QTableWidgetItem(cell_data)
                item.setTextAlignment(Qt.AlignCenter)
                val = None

                reserve_level = None
                if col_idx > 0:
                    try:
                        val = float(cell_data.replace('%', '').strip())
                        
                        if is_today and val < min_val:
                            min_val = val
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
                
                # 오늘 날짜이며 예비율 경고(low)인 경우 알림 목록에 추가 (시간 무관, 캐시로 중복 방지)
                if is_today and reserve_level == 'low' and val is not None:
                    area = headers[col_idx] if col_idx < len(headers) else f"Area{col_idx}"
                    key = (row_data[0], area)
                    if key not in self._alerted_low_reserve:
                        self._alerted_low_reserve.add(key)
                        new_alerts.append((row_data[0], area, val))

            self.refresh_btn.setEnabled(True)

        if min_val != 999.0:
            bus.occto_updated.emit(min_time, tr(min_area), min_val)

        self.status_label.setText(tr("更新完了"))
        self.status_label.setStyleSheet("color: #4caf50; font-weight: bold;")
        self.table.setUpdatesEnabled(True)

        if new_alerts:
            display_alerts = new_alerts[:5]
            lines = "\n".join(f"  {t}  |  {tr(area)}:  {val}%" for t, area, val in display_alerts)
            if len(new_alerts) > 5:
                lines += "\n  " + tr("...他 {0}件の警告があります").format(len(new_alerts) - 5)

            timestamp = datetime.now().strftime("%H:%M:%S")
            total_count = len(new_alerts)

            main_window = next((w for w in QApplication.topLevelWidgets() if w.inherits("QMainWindow")), None)

            prefix = tr("本日のデータに予備率{0}%以下のコマが 【計 {1}件】 発生しています。").format(low_th, total_count)
            plain_msg = prefix + f"\n\n{lines}"
            html_lines = lines.replace('\n', '<br>').replace('  ', '&nbsp;&nbsp;')
            html_msg  = prefix + f"<br><br>{html_lines}"

            title = tr("⚠ 予備率警告 (計 {0}件) - {1}").format(total_count, timestamp)
            
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

    def _export_csv(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, tr("エラー"), tr("保存するデータがありません。"))
            return
            
        date_str = self.date_edit.date().toString('yyyyMMdd')
        file_path, _ = QFileDialog.getSaveFileName(self, tr("CSV保存"), f"OCCTO_予備率_{date_str}.csv", "CSV Files (*.csv)")
        
        if not file_path:
            return
            
        try:
            # Excelで文字化けしないように utf-8-sig (BOM付きUTF-8) を使用
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                headers = [self.table.horizontalHeaderItem(i).text() for i in range(self.table.columnCount())]
                writer.writerow(headers)
                
                for row in range(self.table.rowCount()):
                    row_data = [self.table.item(row, col).text() if self.table.item(row, col) else "" for col in range(self.table.columnCount())]
                    writer.writerow(row_data)
                    
            QMessageBox.information(self, tr("完了"), tr("CSVファイルとして保存しました。\nExcelで開くことができます。"))
        except (IOError, csv.Error) as e:
            QMessageBox.warning(self, tr("エラー"), tr("保存に失敗しました:\n{0}").format(e))
