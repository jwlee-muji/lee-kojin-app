import sys
import winreg
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDoubleSpinBox, QSpinBox, QGroupBox, QFormLayout, QMessageBox, QScrollArea, QCheckBox
)
from PySide6.QtCore import Signal, Qt, QTimer, QThread
from PySide6.QtWidgets import QApplication
from app.core.config import load_settings, save_settings
from app.ui.common import BaseWidget

logger = logging.getLogger(__name__)


class _RetentionWorker(QThread):
    """手動データ整理をバックグラウンドで実行するワーカースレッド"""
    finished = Signal()
    error = Signal(str)

    def __init__(self, retention_days: int):
        super().__init__()
        self.retention_days = retention_days

    def run(self):
        try:
            from app.core.database import run_retention_policy
            run_retention_policy(self.retention_days)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

class SettingsWidget(BaseWidget):
    settings_saved = Signal()
    
    def __init__(self):
        super().__init__()
        self._current_settings = {}
        self._build_ui()
        self._load_data()
        
    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        from version import __version__
        header = QHBoxLayout()
        title = QLabel(self.tr("⚙️ 設定 (Settings)"))
        title.setStyleSheet("font-weight: bold; font-size: 16px;")
        ver_lbl = QLabel(f"v{__version__}")
        ver_lbl.setStyleSheet("color: #888888; font-size: 12px;")
        ver_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(ver_lbl)
        layout.addLayout(header)
        layout.addSpacing(10)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        c_layout = QVBoxLayout(container)
        
        # --- Alert Settings Group ---
        self.grp_alert = QGroupBox(self.tr("⚠️ アラートしきい値設定"))
        self.grp_alert.setObjectName("settingsGroup")
        form_alert = QFormLayout(self.grp_alert)
        form_alert.setContentsMargins(15, 25, 15, 15)
        form_alert.setSpacing(10)
        
        self.spn_imb_alert = QDoubleSpinBox()
        self.spn_imb_alert.setRange(0, 1000)
        self.spn_imb_alert.setSuffix(self.tr(" 円"))
        self.spn_imb_alert.setToolTip(self.tr("インバランス単価がこの値を超過した場合、警告を通知します。"))
        form_alert.addRow(self.tr("インバランス単価 警告:"), self.spn_imb_alert)
        
        self.spn_res_low = QDoubleSpinBox()
        self.spn_res_low.setRange(0, 100)
        self.spn_res_low.setSuffix(self.tr(" %"))
        self.spn_res_low.setToolTip(self.tr("電力予備率がこの値を下回った場合、赤色の警告を通知します。"))
        form_alert.addRow(self.tr("電力予備率 警告 (赤):"), self.spn_res_low)
        
        self.spn_res_warn = QDoubleSpinBox()
        self.spn_res_warn.setRange(0, 100)
        self.spn_res_warn.setSuffix(self.tr(" %"))
        self.spn_res_warn.setToolTip(self.tr("電力予備率がこの値を下回った場合、黄色の注意を通知します。"))
        form_alert.addRow(self.tr("電力予備率 注意 (黄):"), self.spn_res_warn)
        c_layout.addWidget(self.grp_alert)
        
        # --- Interval Settings Group ---
        self.grp_interval = QGroupBox(self.tr("⏱️ 自動更新間隔 (分)"))
        self.grp_interval.setObjectName("settingsGroup")
        form_interval = QFormLayout(self.grp_interval)
        form_interval.setContentsMargins(15, 25, 15, 15)
        form_interval.setSpacing(10)
        
        self.spn_imb_int = QSpinBox(); self.spn_imb_int.setRange(1, 1440)
        self.spn_imb_int.setToolTip(self.tr("インバランス単価のデータ取得間隔（分）"))
        self.spn_res_int = QSpinBox(); self.spn_res_int.setRange(1, 1440)
        self.spn_res_int.setToolTip(self.tr("電力予備率のデータ取得間隔（分）"))
        self.spn_wea_int = QSpinBox(); self.spn_wea_int.setRange(1, 1440)
        self.spn_wea_int.setToolTip(self.tr("全国天気予報のデータ取得間隔（分）"))
        self.spn_hjks_int = QSpinBox(); self.spn_hjks_int.setRange(1, 1440)
        self.spn_hjks_int.setToolTip(self.tr("発電停止状況(HJKS)のデータ取得間隔（分）"))
        self.spn_jkm_int = QSpinBox(); self.spn_jkm_int.setRange(1, 1440)
        self.spn_jkm_int.setToolTip(self.tr("JKM LNG 価格のデータ取得間隔（分）"))
        
        form_interval.addRow(self.tr("インバランス単価:"), self.spn_imb_int)
        form_interval.addRow(self.tr("電力予備率:"), self.spn_res_int)
        form_interval.addRow(self.tr("全国天気予報:"), self.spn_wea_int)
        form_interval.addRow(self.tr("発電停止状況 (HJKS):"), self.spn_hjks_int)
        form_interval.addRow(self.tr("JKM LNG 価格:"), self.spn_jkm_int)
        c_layout.addWidget(self.grp_interval)
        
        # --- Retention Settings Group ---
        self.grp_retention = QGroupBox(self.tr("💾 データ寿命管理 (バックアップと削除)"))
        self.grp_retention.setObjectName("settingsGroup")
        form_retention = QFormLayout(self.grp_retention)
        form_retention.setContentsMargins(15, 25, 15, 15)
        form_retention.setSpacing(10)
        
        self.spn_retention = QSpinBox()
        self.spn_retention.setRange(30, 3650)
        self.spn_retention.setSuffix(self.tr(" 日"))
        self.spn_retention.setToolTip(self.tr("この日数を超えた古いデータは自動的にバックアップされ、メインDBから削除されます。"))
        self.btn_run_retention = QPushButton(self.tr("今すぐ古いデータを整理"))
        self.btn_run_retention.setToolTip(self.tr("今すぐ手動で古いデータのバックアップと削除処理を実行します。"))
        self.btn_run_retention.setObjectName("secondaryActionBtn")
        self.btn_run_retention.clicked.connect(self._manual_retention)
        form_retention.addRow(self.tr("データの保持期間:"), self.spn_retention)
        form_retention.addRow("", self.btn_run_retention)
        c_layout.addWidget(self.grp_retention)
        
        # --- System Settings Group ---
        self.grp_system = QGroupBox(self.tr("💻 システム設定"))
        self.grp_system.setObjectName("settingsGroup")
        form_system = QFormLayout(self.grp_system)
        form_system.setContentsMargins(15, 25, 15, 15)
        self.chk_auto_start = QCheckBox(self.tr("Windows 起動時にバックグラウンドで自動実行する"))
        self.chk_auto_start.setObjectName("settingsCheckbox")
        self.chk_auto_start.setCursor(Qt.PointingHandCursor)
        self.chk_auto_start.setToolTip(self.tr("PC起動時、自動的にバックグラウンド（トレイアイコン）で実行します。"))
        form_system.addRow("", self.chk_auto_start)
        c_layout.addWidget(self.grp_system)
        
        c_layout.addStretch()
        
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
        btn_layout = QHBoxLayout()
        
        self.toast_label = QLabel(self.tr("✅ 保存しました"))
        self.toast_label.setObjectName("successToast")
        self.toast_label.hide()
        
        self.btn_reset = QPushButton(self.tr("🔄 初期化"))
        self.btn_reset.setObjectName("secondaryActionBtn")
        self.btn_reset.setFixedWidth(100)
        self.btn_reset.clicked.connect(self._reset_to_defaults)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.toast_label)
        btn_layout.addSpacing(10)
        btn_layout.addWidget(self.btn_reset)
        self.btn_save = QPushButton(self.tr("設定を保存"))
        self.btn_save.setObjectName("primaryActionBtn")
        self.btn_save.setFixedWidth(150)
        self.btn_save.clicked.connect(self._save_data)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)
        
    def apply_theme_custom(self):
        # 하드코딩된 인라인 스타일을 제거하고 전역 QSS(theme.py)에서 관리합니다.
        pass

    def _manual_retention(self):
        reply = QMessageBox.question(
            self, "確認",
            f"保持期間({self.spn_retention.value()}日)より古いデータを\nバックアップして削除しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_run_retention.setEnabled(False)
        self.btn_run_retention.setText(self.tr("整理中..."))
        QApplication.setOverrideCursor(Qt.WaitCursor)

        self._retention_worker = _RetentionWorker(self.spn_retention.value())
        self._retention_worker.finished.connect(self._on_retention_finished)
        self._retention_worker.error.connect(self._on_retention_error)
        self._retention_worker.finished.connect(self._retention_worker.deleteLater)
        self._retention_worker.start()

    def _on_retention_finished(self):
        QApplication.restoreOverrideCursor()
        self.btn_run_retention.setEnabled(True)
        self.btn_run_retention.setText(self.tr("今すぐ古いデータを整理"))
        QMessageBox.information(self, "完了", "古いデータのバックアップと削除が完了しました。\n(保存先: backups フォルダ)")

    def _on_retention_error(self, err: str):
        QApplication.restoreOverrideCursor()
        self.btn_run_retention.setEnabled(True)
        self.btn_run_retention.setText(self.tr("今すぐ古いデータを整理"))
        QMessageBox.warning(self, "エラー", f"処理中にエラーが発生しました:\n{err}")

    def _load_data(self):
        self._current_settings = load_settings()
        s = self._current_settings
        self.spn_imb_alert.setValue(s.get("imbalance_alert", 40.0))
        self.spn_res_low.setValue(s.get("reserve_low", 8.0))
        self.spn_res_warn.setValue(s.get("reserve_warn", 10.0))
        self.spn_imb_int.setValue(s.get("imbalance_interval", 5))
        self.spn_res_int.setValue(s.get("reserve_interval", 5))
        self.spn_wea_int.setValue(s.get("weather_interval", 60))
        self.spn_hjks_int.setValue(s.get("hjks_interval", 180))
        self.spn_jkm_int.setValue(s.get("jkm_interval", 180))
        self.spn_retention.setValue(s.get("retention_days", 1460))
        self.chk_auto_start.setChecked(s.get("auto_start", False))
        
    def _get_ui_settings(self):
        return {
            "imbalance_alert": self.spn_imb_alert.value(), "reserve_low": self.spn_res_low.value(),
            "reserve_warn": self.spn_res_warn.value(), "imbalance_interval": self.spn_imb_int.value(),
            "reserve_interval": self.spn_res_int.value(), "weather_interval": self.spn_wea_int.value(),
            "hjks_interval": self.spn_hjks_int.value(), "jkm_interval": self.spn_jkm_int.value(),
            "retention_days": self.spn_retention.value(), "auto_start": self.chk_auto_start.isChecked()
        }

    def _save_data(self):
        new_settings = self._get_ui_settings()
        
        has_changes = False
        for k, v in new_settings.items():
            if self._current_settings.get(k) != v:
                has_changes = True
                break
                
        if not has_changes:
            self._show_toast("変更がありません")
            return
            
        if self._current_settings.get("auto_start") != new_settings["auto_start"]:
            self._toggle_auto_start(new_settings["auto_start"])
            
        save_settings(new_settings)
        self._current_settings = new_settings
        
        self._show_toast("✅ 保存しました")
        self.settings_saved.emit()
        
    def _show_toast(self, msg):
        self.toast_label.setText(msg)
        self.toast_label.show()
        QTimer.singleShot(3000, self.toast_label.hide)
        
    def _reset_to_defaults(self):
        reply = QMessageBox.question(self, "確認", "設定を初期値に戻しますか？", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.spn_imb_alert.setValue(40.0)
            self.spn_res_low.setValue(8.0)
            self.spn_res_warn.setValue(10.0)
            self.spn_imb_int.setValue(5)
            self.spn_res_int.setValue(5)
            self.spn_wea_int.setValue(60)
            self.spn_hjks_int.setValue(180)
            self.spn_jkm_int.setValue(180)
            self.spn_retention.setValue(1460)
            self.chk_auto_start.setChecked(False)
        
    def _toggle_auto_start(self, enable: bool):
        if not getattr(sys, 'frozen', False):
            return  # .exe로 컴파일된 환경에서만 작동
            
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "LEEPowerMonitor"
        exe_path = f'"{sys.executable}" --tray'
        
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS) as key:
                if enable:
                    winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
                else:
                    try: winreg.DeleteValue(key, app_name)
                    except FileNotFoundError: pass
        except Exception as e:
            logger.error(f"Auto-start registry update failed: {e}")