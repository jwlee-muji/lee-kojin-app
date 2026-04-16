import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDoubleSpinBox, QSpinBox, QGroupBox, QFormLayout, QMessageBox,
    QScrollArea, QCheckBox, QComboBox, QFrame,
)
from PySide6.QtCore import Signal, Qt, QTimer, QThread
from PySide6.QtWidgets import QApplication
from app.core.config import load_settings, save_settings
from app.core.platform import set_autostart
from app.core.i18n import tr, LANG_OPTIONS
from app.ui.common import BaseWidget
from app.core.events import bus

logger = logging.getLogger(__name__)

_LANG_CODES = [code for _, code in LANG_OPTIONS]

# Gemini フォールバックモデル (Tier 2) の選択肢
_GEMINI_MODELS = [
    ("gemini-2.5-flash  (推奨)",          "gemini-2.5-flash"),
    ("gemini-2.5-pro  (高精度・低速)",    "gemini-2.5-pro"),
    ("gemini-2.0-flash",                   "gemini-2.0-flash"),
    ("gemini-2.0-flash-lite  (軽量)",     "gemini-2.0-flash-lite"),
]
_GEMINI_MODEL_CODES = [v for _, v in _GEMINI_MODELS]

_MAX_TOKENS_OPTIONS = [512, 1024, 2048, 4096]


class _RetentionWorker(QThread):
    """手動データ整理をバックグラウンドで実行"""
    finished = Signal()
    error    = Signal(str)

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
    def __init__(self):
        super().__init__()
        self._current_settings = {}
        self._build_ui()
        self._load_data()

    # ── UI 構築 ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── ヘッダー ────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setObjectName("settingsHeader")
        hdr.setStyleSheet("QFrame#settingsHeader { border-bottom: 1px solid #2a2a2a; }")
        hrow = QHBoxLayout(hdr)
        hrow.setContentsMargins(20, 14, 20, 14)

        from app.core.config import __version__
        title_lbl = QLabel(tr("設定"))
        title_lbl.setStyleSheet("font-weight: bold; font-size: 16px;")
        ver_lbl = QLabel(f"v{__version__}")
        ver_lbl.setStyleSheet("color: #666; font-size: 12px;")

        hrow.addWidget(title_lbl)
        hrow.addStretch()
        hrow.addWidget(ver_lbl)
        root.addWidget(hdr)

        # ── スクロールエリア ──────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        c = QVBoxLayout(container)
        c.setContentsMargins(16, 14, 16, 14)
        c.setSpacing(8)

        c.addWidget(self._build_alert_section())
        c.addWidget(self._build_interval_section())
        c.addWidget(self._build_ai_section())
        c.addWidget(self._build_retention_section())
        c.addWidget(self._build_system_section())
        c.addWidget(self._build_language_section())
        c.addStretch()

        scroll.setWidget(container)
        root.addWidget(scroll, 1)

        # ── フッター ─────────────────────────────────────────────────────
        footer = QFrame()
        footer.setObjectName("settingsFooter")
        footer.setStyleSheet("QFrame#settingsFooter { border-top: 1px solid #2a2a2a; }")
        frow = QHBoxLayout(footer)
        frow.setContentsMargins(20, 10, 20, 10)
        frow.setSpacing(10)

        self.toast_label = QLabel()
        self.toast_label.setObjectName("successToast")
        self.toast_label.setStyleSheet("font-size: 12px;")
        self.toast_label.hide()

        self.btn_reset = QPushButton(tr("初期化"))
        self.btn_reset.setObjectName("secondaryActionBtn")
        self.btn_reset.setFixedHeight(32)
        self.btn_reset.setMinimumWidth(88)
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset.clicked.connect(self._reset_to_defaults)

        self.btn_save = QPushButton(tr("設定を保存") + "  →")
        self.btn_save.setObjectName("primaryActionBtn")
        self.btn_save.setFixedHeight(32)
        self.btn_save.setMinimumWidth(130)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self._save_data)

        frow.addWidget(self.toast_label, 1)
        frow.addWidget(self.btn_reset)
        frow.addWidget(self.btn_save)
        root.addWidget(footer)

    # ── セクション構築 ────────────────────────────────────────────────────

    @staticmethod
    def _make_group(title: str) -> tuple[QGroupBox, QFormLayout]:
        grp = QGroupBox(title)
        grp.setObjectName("settingsGroup")
        form = QFormLayout(grp)
        form.setContentsMargins(18, 18, 18, 16)
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        return grp, form

    @staticmethod
    def _note(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #666; font-size: 11px;")
        lbl.setWordWrap(True)
        return lbl

    def _build_alert_section(self) -> QGroupBox:
        grp, form = self._make_group("⚠️   " + tr("アラートしきい値"))

        self.spn_imb_alert = QDoubleSpinBox()
        self.spn_imb_alert.setRange(0, 1000)
        self.spn_imb_alert.setSuffix(tr("  円"))
        self.spn_imb_alert.setFixedWidth(110)
        self.spn_imb_alert.setToolTip(tr("インバランス単価がこの値を超過した場合、警告を通知します。"))

        self.spn_res_low = QDoubleSpinBox()
        self.spn_res_low.setRange(0, 100)
        self.spn_res_low.setSuffix(tr("  %"))
        self.spn_res_low.setFixedWidth(110)
        self.spn_res_low.setToolTip(tr("電力予備率がこの値を下回った場合、赤色の警告を通知します。"))

        self.spn_res_warn = QDoubleSpinBox()
        self.spn_res_warn.setRange(0, 100)
        self.spn_res_warn.setSuffix(tr("  %"))
        self.spn_res_warn.setFixedWidth(110)
        self.spn_res_warn.setToolTip(tr("電力予備率がこの値を下回った場合、黄色の注意を通知します。"))

        form.addRow(tr("インバランス単価 警告:"), self.spn_imb_alert)
        form.addRow(tr("電力予備率 警告 (赤):"),  self.spn_res_low)
        form.addRow(tr("電力予備率 注意 (黄):"),  self.spn_res_warn)
        return grp

    def _build_interval_section(self) -> QGroupBox:
        grp, form = self._make_group("⏱️   " + tr("自動更新間隔"))

        def _spn(tip: str) -> QSpinBox:
            w = QSpinBox()
            w.setRange(1, 1440)
            w.setSuffix(tr("  分"))
            w.setFixedWidth(110)
            w.setToolTip(tip)
            return w

        self.spn_imb_int  = _spn(tr("インバランス単価のデータ取得間隔（分）"))
        self.spn_res_int  = _spn(tr("電力予備率のデータ取得間隔（分）"))
        self.spn_wea_int  = _spn(tr("全国天気予報のデータ取得間隔（分）"))
        self.spn_hjks_int = _spn(tr("発電停止状況(HJKS)のデータ取得間隔（分）"))
        self.spn_jkm_int  = _spn(tr("JKM LNG 価格のデータ取得間隔（分）"))

        form.addRow(tr("インバランス単価:"),    self.spn_imb_int)
        form.addRow(tr("電力予備率:"),          self.spn_res_int)
        form.addRow(tr("全国天気予報:"),        self.spn_wea_int)
        form.addRow(tr("発電停止状況 (HJKS):"), self.spn_hjks_int)
        form.addRow(tr("JKM LNG 価格:"),       self.spn_jkm_int)
        return grp

    def _build_ai_section(self) -> QGroupBox:
        grp, form = self._make_group("🤖   " + tr("AI チャット"))

        # フォールバックモデル (Tier 2)
        self.cmb_gemini_model = QComboBox()
        for display, _ in _GEMINI_MODELS:
            self.cmb_gemini_model.addItem(display)
        self.cmb_gemini_model.setMinimumWidth(230)
        self.cmb_gemini_model.setToolTip(
            tr("Gemini 3.1 Flash Lite の次に試みるフォールバックモデル。\n通常は gemini-2.5-flash (推奨) で十分です。")
        )

        # 応答温度
        self.spn_temperature = QDoubleSpinBox()
        self.spn_temperature.setRange(0.1, 2.0)
        self.spn_temperature.setSingleStep(0.1)
        self.spn_temperature.setDecimals(1)
        self.spn_temperature.setFixedWidth(110)
        self.spn_temperature.setToolTip(
            tr("AIの回答の多様性を制御します。\n低い値 (0.1〜0.5): 正確・一貫した回答\n高い値 (1.0〜2.0): 多様・創造的な回答\n推奨: 0.7")
        )

        # 最大トークン数
        self.cmb_max_tokens = QComboBox()
        for v in _MAX_TOKENS_OPTIONS:
            self.cmb_max_tokens.addItem(f"{v:,}  トークン", v)
        self.cmb_max_tokens.setMinimumWidth(160)
        self.cmb_max_tokens.setToolTip(
            tr("一回の回答で生成する最大文字数を制御します。\n長い回答が必要な場合は 4096 を選択。\n推奨: 2,048")
        )

        # 会話履歴の保持数
        self.spn_history = QSpinBox()
        self.spn_history.setRange(4, 100)
        self.spn_history.setSingleStep(2)
        self.spn_history.setSuffix(tr("  件"))
        self.spn_history.setFixedWidth(110)
        self.spn_history.setToolTip(
            tr("AIに渡す過去の会話メッセージ数の上限です。\n多いほどコンテキストが保たれますが API 使用量が増加します。\n推奨: 20")
        )

        form.addRow(tr("フォールバックモデル:"),  self.cmb_gemini_model)
        form.addRow(tr("応答の温度:"),            self.spn_temperature)
        form.addRow(tr("最大トークン数:"),         self.cmb_max_tokens)
        form.addRow(tr("会話履歴の保持数:"),       self.spn_history)
        form.addRow("", self._note(
            tr("※ 優先順位: Gemini 3.1 Flash Lite → 上記モデル → Groq (llama-3.3-70b)")
        ))
        return grp

    def _build_retention_section(self) -> QGroupBox:
        grp, form = self._make_group("💾   " + tr("データ管理"))

        self.spn_retention = QSpinBox()
        self.spn_retention.setRange(30, 3650)
        self.spn_retention.setSuffix(tr("  日"))
        self.spn_retention.setFixedWidth(110)
        self.spn_retention.setToolTip(
            tr("この日数を超えた古いデータは自動的にバックアップされ、メインDBから削除されます。")
        )

        self.btn_run_retention = QPushButton(tr("今すぐ古いデータを整理"))
        self.btn_run_retention.setObjectName("secondaryActionBtn")
        self.btn_run_retention.setFixedHeight(30)
        self.btn_run_retention.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_run_retention.setToolTip(
            tr("今すぐ手動で古いデータのバックアップと削除処理を実行します。")
        )
        self.btn_run_retention.clicked.connect(self._manual_retention)

        form.addRow(tr("データの保持期間:"), self.spn_retention)
        form.addRow("", self.btn_run_retention)
        return grp

    def _build_system_section(self) -> QGroupBox:
        grp, form = self._make_group("💻   " + tr("システム"))

        self.chk_auto_start = QCheckBox(tr("Windows 起動時にバックグラウンドで自動実行する"))
        self.chk_auto_start.setObjectName("settingsCheckbox")
        self.chk_auto_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_auto_start.setToolTip(
            tr("PC起動時、自動的にバックグラウンド（トレイアイコン）で実行します。")
        )

        form.addRow("", self.chk_auto_start)
        return grp

    def _build_language_section(self) -> QGroupBox:
        grp, form = self._make_group("🌍   " + tr("言語 (Language)"))

        self.cmb_language = QComboBox()
        for display_name, _ in LANG_OPTIONS:
            self.cmb_language.addItem(display_name)
        self.cmb_language.setMinimumWidth(180)

        form.addRow(tr("表示言語:"), self.cmb_language)
        form.addRow("", self._note(tr("変更は再起動後に適用されます")))
        return grp

    def set_theme(self, is_dark: bool):
        if is_dark:
            cmb_style = (
                "QComboBox {"
                "  background-color: #3d3d3d;"
                "  color: #e0e0e0;"
                "  border: 1px solid #666666;"
                "  border-radius: 4px;"
                "  padding: 4px 10px;"
                "}"
                "QComboBox:hover { border-color: #909090; }"
                "QComboBox::drop-down {"
                "  background-color: #505050;"
                "  width: 22px;"
                "  border-left: 1px solid #666666;"
                "}"
                "QComboBox QAbstractItemView {"
                "  background-color: #464646;"
                "  color: #e0e0e0;"
                "  selection-background-color: #0e639c;"
                "  selection-color: #ffffff;"
                "  border: 1px solid #707070;"
                "  outline: none;"
                "}"
                "QComboBox QAbstractItemView::item {"
                "  padding: 5px 10px;"
                "  min-height: 22px;"
                "}"
                "QComboBox QAbstractItemView::item:hover {"
                "  background-color: #565656;"
                "  color: #ffffff;"
                "}"
            )
        else:
            cmb_style = ""

        for w in (self.cmb_gemini_model, self.cmb_max_tokens, self.cmb_language):
            w.setStyleSheet(cmb_style)

        super().set_theme(is_dark)

    # ── データ読み書き ────────────────────────────────────────────────────

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

        # AI 設定
        model = s.get("gemini_model", "gemini-2.5-flash")
        midx = _GEMINI_MODEL_CODES.index(model) if model in _GEMINI_MODEL_CODES else 0
        self.cmb_gemini_model.setCurrentIndex(midx)

        self.spn_temperature.setValue(float(s.get("ai_temperature", 0.7)))

        max_tok = int(s.get("ai_max_tokens", 2048))
        tidx = _MAX_TOKENS_OPTIONS.index(max_tok) if max_tok in _MAX_TOKENS_OPTIONS else 2
        self.cmb_max_tokens.setCurrentIndex(tidx)

        self.spn_history.setValue(int(s.get("chat_history_limit", 20)))

        lang = s.get("language", "auto")
        lidx = _LANG_CODES.index(lang) if lang in _LANG_CODES else 0
        self.cmb_language.setCurrentIndex(lidx)

    def _get_ui_settings(self) -> dict:
        return {
            "imbalance_alert":    self.spn_imb_alert.value(),
            "reserve_low":        self.spn_res_low.value(),
            "reserve_warn":       self.spn_res_warn.value(),
            "imbalance_interval": self.spn_imb_int.value(),
            "reserve_interval":   self.spn_res_int.value(),
            "weather_interval":   self.spn_wea_int.value(),
            "hjks_interval":      self.spn_hjks_int.value(),
            "jkm_interval":       self.spn_jkm_int.value(),
            "retention_days":     self.spn_retention.value(),
            "auto_start":         self.chk_auto_start.isChecked(),
            "language":           _LANG_CODES[self.cmb_language.currentIndex()],
            "gemini_model":       _GEMINI_MODEL_CODES[self.cmb_gemini_model.currentIndex()],
            "ai_temperature":     round(self.spn_temperature.value(), 1),
            "ai_max_tokens":      _MAX_TOKENS_OPTIONS[self.cmb_max_tokens.currentIndex()],
            "chat_history_limit": self.spn_history.value(),
        }

    def _save_data(self):
        new_ui = self._get_ui_settings()
        has_changes = any(self._current_settings.get(k) != v for k, v in new_ui.items())
        if not has_changes:
            self._show_toast(tr("変更がありません"))
            return

        if self._current_settings.get("auto_start") != new_ui["auto_start"]:
            self._toggle_auto_start(new_ui["auto_start"])

        language_changed = self._current_settings.get("language") != new_ui.get("language")

        new_settings = {**self._current_settings, **new_ui}
        save_settings(new_settings)
        self._current_settings = new_settings

        if language_changed:
            self._show_toast(tr("変更は再起動後に適用されます"))
        else:
            self._show_toast("✅  " + tr("保存しました"))

        bus.settings_saved.emit()

    def _show_toast(self, msg: str):
        self.toast_label.setText(msg)
        self.toast_label.show()
        QTimer.singleShot(3500, self.toast_label.hide)

    def _reset_to_defaults(self):
        reply = QMessageBox.question(
            self, tr("確認"), tr("設定を初期値に戻しますか？"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

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
        self.cmb_language.setCurrentIndex(0)
        self.cmb_gemini_model.setCurrentIndex(0)
        self.spn_temperature.setValue(0.7)
        self.cmb_max_tokens.setCurrentIndex(2)   # 2048
        self.spn_history.setValue(20)

    # ── データ整理 ────────────────────────────────────────────────────────

    def _manual_retention(self):
        days = int(self.spn_retention.value())
        reply = QMessageBox.question(
            self, tr("確認"),
            tr("保持期間({0}日)より古いデータを\nバックアップして削除しますか？").format(days),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_run_retention.setEnabled(False)
        self.btn_run_retention.setText(tr("整理中..."))
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        self._retention_worker = _RetentionWorker(self.spn_retention.value())
        self._retention_worker.finished.connect(self._on_retention_finished)
        self._retention_worker.error.connect(self._on_retention_error)
        self._retention_worker.finished.connect(self._retention_worker.deleteLater)
        self._retention_worker.start()
        self.track_worker(self._retention_worker)

    def _on_retention_finished(self):
        QApplication.restoreOverrideCursor()
        self.btn_run_retention.setEnabled(True)
        self.btn_run_retention.setText(tr("今すぐ古いデータを整理"))
        QMessageBox.information(
            self, tr("完了"),
            tr("古いデータのバックアップと削除が完了しました。\n(保存先: backups フォルダ)"),
        )

    def _on_retention_error(self, err: str):
        QApplication.restoreOverrideCursor()
        self.btn_run_retention.setEnabled(True)
        self.btn_run_retention.setText(tr("今すぐ古いデータを整理"))
        QMessageBox.warning(
            self, tr("エラー"),
            tr("処理中にエラーが発生しました:") + f"\n{err}",
        )

    # ── 自動起動 (Windows レジストリ) ────────────────────────────────────

    def _toggle_auto_start(self, enable: bool):
        set_autostart(enable)
