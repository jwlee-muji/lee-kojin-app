import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDoubleSpinBox, QSpinBox, QGroupBox, QFormLayout, QMessageBox,
    QScrollArea, QCheckBox, QComboBox, QFrame, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QPropertyAnimation
from PySide6.QtWidgets import QApplication
from app.core.config import load_settings, save_settings
from app.core.platform import set_autostart
from app.core.i18n import tr, LANG_OPTIONS
from app.ui.common import BaseWidget
from app.ui.theme import UIColors
from app.core.events import bus
from app.api.database_worker import DataRetentionWorker

logger = logging.getLogger(__name__)

_LANG_CODES = [code for _, code in LANG_OPTIONS]

_GEMINI_MODELS = [
    ("gemini-2.5-flash  (推奨)",       "gemini-2.5-flash"),
    ("gemini-2.5-pro  (高精度・低速)", "gemini-2.5-pro"),
    ("gemini-2.0-flash",               "gemini-2.0-flash"),
    ("gemini-2.0-flash-lite  (軽量)",  "gemini-2.0-flash-lite"),
]
_GEMINI_MODEL_CODES = [v for _, v in _GEMINI_MODELS]

_MAX_TOKENS_OPTIONS = [512, 1024, 2048, 4096]


# ── Admin Workers ────────────────────────────────────────────────────────────

class FetchUsersWorker(QThread):
    success = Signal(list)
    error = Signal(str)
    def run(self):
        try:
            from app.api.google.sheets import get_all_users
            self.success.emit(get_all_users())
        except Exception as e:
            self.error.emit(str(e))


class RemoveUserWorker(QThread):
    success = Signal()
    error = Signal(str)
    def __init__(self, email):
        super().__init__()
        self.email = email
    def run(self):
        try:
            from app.api.google.sheets import remove_user
            remove_user(self.email)
            self.success.emit()
        except Exception as e:
            self.error.emit(str(e))


class AddUserWorker(QThread):
    success = Signal()
    error = Signal(str)
    def __init__(self, email, name):
        super().__init__()
        self.email = email
        self.name = name
    def run(self):
        try:
            from app.api.google.sheets import add_user
            add_user(self.email, self.name)
            self.success.emit()
        except Exception as e:
            self.error.emit(str(e))


class SettingsWidget(BaseWidget):
    def __init__(self):
        super().__init__()
        self._current_settings = {}
        self._note_labels: list = []
        self._build_ui()
        self._load_data()
        self.apply_theme_custom()

    # ── UI 構築 ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ヘッダー
        hdr = QFrame()
        hdr.setObjectName("settingsHeader")
        self._hdr_frame = hdr
        hrow = QHBoxLayout(hdr)
        hrow.setContentsMargins(20, 14, 20, 14)
        from app.core.config import __version__
        title_lbl = QLabel(tr("設定"))
        title_lbl.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.ver_lbl = QLabel(f"v{__version__}")
        hrow.addWidget(title_lbl)
        hrow.addStretch()
        hrow.addWidget(self.ver_lbl)
        root.addWidget(hdr)

        # スクロールエリア
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        c = QVBoxLayout(container)
        c.setContentsMargins(16, 14, 16, 20)
        c.setSpacing(10)

        c.addWidget(self._build_alert_section())
        c.addWidget(self._build_interval_section())
        c.addWidget(self._build_google_section())
        c.addWidget(self._build_ai_section())
        c.addWidget(self._build_retention_section())
        c.addWidget(self._build_app_section())

        try:
            from app.core.config import get_session_email, ADMIN_EMAIL
            _sess = get_session_email()
            _admin = ADMIN_EMAIL.lower()
            logger.debug(f"管理者判定: session={_sess!r} admin={_admin!r} match={_sess == _admin}")
            if _sess == _admin:
                c.addWidget(self._build_admin_section())
        except Exception as e:
            logger.error(f"管理者パネル構築エラー: {e}", exc_info=True)

        c.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

        # フッター
        footer = QFrame()
        footer.setObjectName("settingsFooter")
        self._footer_frame = footer
        frow = QHBoxLayout(footer)
        frow.setContentsMargins(20, 10, 20, 10)
        frow.setSpacing(10)

        self.toast_label = QLabel()
        self.toast_label.setObjectName("successToast")
        self.toast_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #4caf50;")
        
        self._toast_effect = QGraphicsOpacityEffect(self.toast_label)
        self.toast_label.setGraphicsEffect(self._toast_effect)
        self._toast_anim = QPropertyAnimation(self._toast_effect, b"opacity")
        self._toast_anim.setDuration(300)
        self.toast_label.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._hide_toast)

        self.btn_reset = QPushButton(tr("初期化"))
        self.btn_reset.setObjectName("secondaryActionBtn")
        self.btn_reset.setFixedHeight(32)
        self.btn_reset.setMinimumWidth(88)
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset.clicked.connect(self._reset_to_defaults)

        self.btn_save = QPushButton("  " + tr("設定を保存") + "  →")
        self.btn_save.setObjectName("primaryActionBtn")
        self.btn_save.setFixedHeight(32)
        self.btn_save.setMinimumWidth(130)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self._save_data)

        frow.addWidget(self.toast_label, 1)
        frow.addWidget(self.btn_reset)
        frow.addWidget(self.btn_save)
        root.addWidget(footer)

    # ── セクション共通ヘルパー ────────────────────────────────────────────────

    @staticmethod
    def _make_group(title: str) -> tuple[QGroupBox, QFormLayout]:
        grp = QGroupBox(title)
        grp.setObjectName("settingsGroup")
        form = QFormLayout(grp)
        form.setContentsMargins(18, 14, 18, 16)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        return grp, form

    def _note(self, text: str, word_wrap: bool = False) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(word_wrap)
        self._note_labels.append(lbl)
        return lbl

    @staticmethod
    def _spn_int(lo: int, hi: int, suffix: str, tip: str) -> QSpinBox:
        w = QSpinBox()
        w.setRange(lo, hi)
        w.setSuffix(suffix)
        w.setMinimumWidth(120)
        w.setFixedHeight(32)
        w.setToolTip(tip)
        return w

    @staticmethod
    def _spn_float(lo: float, hi: float, suffix: str, tip: str, step: float = 1.0) -> QDoubleSpinBox:
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setSuffix(suffix)
        w.setSingleStep(step)
        w.setMinimumWidth(120)
        w.setFixedHeight(32)
        w.setToolTip(tip)
        return w

    @staticmethod
    def _cmb(items: list[str], tip: str = "", min_width: int = 180) -> QComboBox:
        w = QComboBox()
        for item in items:
            w.addItem(item)
        w.setMinimumWidth(min_width)
        w.setFixedHeight(32)
        if tip:
            w.setToolTip(tip)
        return w

    @staticmethod
    def _sep() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setObjectName("settingsSep")
        return f

    # ── セクション構築 ────────────────────────────────────────────────────────

    def _build_alert_section(self) -> QGroupBox:
        grp, form = self._make_group("⚠️   " + tr("アラートしきい値"))

        self.spn_imb_alert = self._spn_float(
            0, 1000, "  円",
            tr("インバランス単価がこの値を超過した場合、警告を通知します。"),
        )
        self.spn_res_low = self._spn_float(
            0, 100, "  %",
            tr("電力予備率がこの値を下回った場合、赤色の警告を通知します。"),
        )
        self.spn_res_warn = self._spn_float(
            0, 100, "  %",
            tr("電力予備率がこの値を下回った場合、黄色の注意を通知します。"),
        )

        form.addRow(tr("インバランス単価 警告:"), self.spn_imb_alert)
        form.addRow(tr("電力予備率 警告 (赤):"),  self.spn_res_low)
        form.addRow(tr("電力予備率 注意 (黄):"),  self.spn_res_warn)
        return grp

    def _build_interval_section(self) -> QGroupBox:
        grp, form = self._make_group("⏱️   " + tr("自動更新間隔"))

        self.spn_imb_int  = self._spn_int(1, 1440, tr("  分"), tr("インバランス単価のデータ取得間隔（分）"))
        self.spn_res_int  = self._spn_int(1, 1440, tr("  分"), tr("電力予備率のデータ取得間隔（分）"))
        self.spn_wea_int  = self._spn_int(1, 1440, tr("  分"), tr("全国天気予報のデータ取得間隔（分）"))
        self.spn_hjks_int = self._spn_int(1, 1440, tr("  分"), tr("発電停止状況(HJKS)のデータ取得間隔（分）"))
        self.spn_jkm_int  = self._spn_int(1, 1440, tr("  分"), tr("JKM LNG 価格のデータ取得間隔（分）"))

        form.addRow(tr("インバランス単価:"),    self.spn_imb_int)
        form.addRow(tr("電力予備率:"),          self.spn_res_int)
        form.addRow(tr("全国天気予報:"),        self.spn_wea_int)
        form.addRow(tr("発電停止状況 (HJKS):"), self.spn_hjks_int)
        form.addRow(tr("JKM LNG 価格:"),       self.spn_jkm_int)
        return grp

    def _build_google_section(self) -> QGroupBox:
        grp, form = self._make_group("🔗   " + tr("Google 連携"))

        # アカウント表示
        from app.api.google.auth import get_current_user_email
        email = get_current_user_email() or tr("ログイン済み")
        acct_w = QWidget()
        acct_row = QHBoxLayout(acct_w)
        acct_row.setContentsMargins(0, 0, 0, 0)
        acct_row.setSpacing(6)
        dot = QLabel("●")
        dot.setStyleSheet("color: #4CAF50; font-size: 9px;")
        acct_lbl = QLabel(email)
        acct_lbl.setStyleSheet("font-size: 12px;")
        acct_row.addWidget(dot)
        acct_row.addWidget(acct_lbl)
        acct_row.addStretch()

        self.spn_cal_int = self._spn_int(1, 1440, tr("  分"),
            tr("Google カレンダーのイベント取得間隔（分）"))
        self.spn_gmail_int = self._spn_int(1, 1440, tr("  分"),
            tr("Gmail の受信確認間隔（分）"))
        self.spn_gmail_max = self._spn_int(10, 500, tr("  件"),
            tr("一度に取得する Gmail メッセージの最大件数"))

        form.addRow(tr("アカウント:"),       acct_w)
        form.addRow(tr("カレンダー更新:"),   self.spn_cal_int)
        form.addRow(tr("Gmail 更新:"),       self.spn_gmail_int)
        form.addRow(tr("メール取得件数:"),   self.spn_gmail_max)
        return grp

    def _build_ai_section(self) -> QGroupBox:
        grp, form = self._make_group("🤖   " + tr("AI チャット"))

        self.cmb_gemini_model = QComboBox()
        for display, _ in _GEMINI_MODELS:
            self.cmb_gemini_model.addItem(display)
        self.cmb_gemini_model.setMinimumWidth(250)
        self.cmb_gemini_model.setFixedHeight(32)
        self.cmb_gemini_model.setToolTip(
            tr("Gemini 3.1 Flash Lite の次に試みるフォールバックモデル。\n通常は gemini-2.5-flash (推奨) で十分です。")
        )

        self.spn_temperature = QDoubleSpinBox()
        self.spn_temperature.setRange(0.1, 2.0)
        self.spn_temperature.setSingleStep(0.1)
        self.spn_temperature.setDecimals(1)
        self.spn_temperature.setMinimumWidth(120)
        self.spn_temperature.setFixedHeight(32)
        self.spn_temperature.setToolTip(
            tr("AIの回答の多様性を制御します。\n低い値 (0.1〜0.5): 正確・一貫\n高い値 (1.0〜2.0): 多様・創造的\n推奨: 0.7")
        )

        self.cmb_max_tokens = QComboBox()
        for v in _MAX_TOKENS_OPTIONS:
            self.cmb_max_tokens.addItem(f"{v:,}  トークン", v)
        self.cmb_max_tokens.setMinimumWidth(180)
        self.cmb_max_tokens.setFixedHeight(32)
        self.cmb_max_tokens.setToolTip(
            tr("一回の回答で生成する最大トークン数。長い回答が必要な場合は 4096 を選択。\n推奨: 2,048")
        )

        self.spn_history = self._spn_int(4, 100, tr("  件"),
            tr("AIに渡す過去の会話メッセージ数の上限。多いほどコンテキストが保たれますが API 使用量が増加します。\n推奨: 20"))
        self.spn_history.setSingleStep(2)

        form.addRow(tr("フォールバックモデル:"), self.cmb_gemini_model)
        form.addRow(tr("応答の温度:"),           self.spn_temperature)
        form.addRow(tr("最大トークン数:"),        self.cmb_max_tokens)
        form.addRow(tr("会話履歴の保持数:"),      self.spn_history)
        form.addRow("", self._note(
            tr("※ 優先順位: Gemini 2.5 Flash Lite → 上記モデル → Groq (llama-3.3-70b)")
        ))
        return grp

    def _build_retention_section(self) -> QGroupBox:
        grp, form = self._make_group("💾   " + tr("データ管理"))

        self.spn_retention = self._spn_int(30, 3650, tr("  日"),
            tr("この日数を超えた古いデータは自動的にバックアップされ、メインDBから削除されます。"))

        self.btn_run_retention = QPushButton("  " + tr("今すぐ整理実行") + "  ")
        self.btn_run_retention.setObjectName("secondaryActionBtn")
        self.btn_run_retention.setFixedHeight(30)
        self.btn_run_retention.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_run_retention.setToolTip(
            tr("今すぐ手動で古いデータのバックアップと削除処理を実行します。")
        )
        self.btn_run_retention.clicked.connect(self._manual_retention)

        form.addRow(tr("データ保持期間:"), self.spn_retention)
        form.addRow("", self._note(
            tr("※ 設定日数を超えたデータは backups フォルダへ自動バックアップされます。")
        ))
        form.addRow("", self.btn_run_retention)
        return grp

    def _build_app_section(self) -> QGroupBox:
        """言語・システム設定の統合セクション。"""
        grp, form = self._make_group("⚙️   " + tr("アプリ設定"))

        self.cmb_language = QComboBox()
        for display_name, _ in LANG_OPTIONS:
            self.cmb_language.addItem(display_name)
        self.cmb_language.setMinimumWidth(180)
        self.cmb_language.setFixedHeight(32)

        self.chk_auto_start = QCheckBox(tr("Windows 起動時にバックグラウンドで自動実行する"))
        self.chk_auto_start.setObjectName("settingsCheckbox")
        self.chk_auto_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_auto_start.setToolTip(
            tr("PC起動時、自動的にバックグラウンド（トレイアイコン）で実行します。")
        )

        form.addRow(tr("表示言語:"), self.cmb_language)
        form.addRow("", self._note(tr("※ 言語変更は再起動後に適用されます。")))
        form.addRow("", self.chk_auto_start)
        return grp

    def _build_admin_section(self) -> QGroupBox:
        """管理者専用: ユーザー管理セクション。"""
        grp = QGroupBox("👑   " + tr("ユーザー管理 (管理者専用)"))
        grp.setObjectName("settingsGroup")

        root = QVBoxLayout(grp)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)

        # ── Sheets ID ──────────────────────────────────────────────────────
        lbl_sheets = QLabel(tr("Google Sheets ID"))
        lbl_sheets.setStyleSheet("font-weight: bold; font-size: 12px;")

        sheets_row = QHBoxLayout()
        sheets_row.setSpacing(8)
        self.edt_sheets_id = QLineEdit()
        self.edt_sheets_id.setPlaceholderText(tr(".env で管理されています"))
        self.edt_sheets_id.setFixedHeight(32)
        self.edt_sheets_id.setDisabled(True)

        sheets_row.addWidget(self.edt_sheets_id, 1)

        note_sheets = self._note(
            tr("※ Sheets ID は環境変数 (.env) で一元管理されているため、ここでは読み取り専用です。"),
            word_wrap=True
        )

        sep1 = self._sep()

        # ── ユーザー一覧 ────────────────────────────────────────────────────
        tbl_hdr_row = QHBoxLayout()
        lbl_users = QLabel(tr("登録ユーザー"))
        lbl_users.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.lbl_users_status = QLabel()
        self.lbl_users_status.setStyleSheet("font-size: 11px; color: #888;")
        tbl_hdr_row.addWidget(lbl_users)
        tbl_hdr_row.addStretch()
        tbl_hdr_row.addWidget(self.lbl_users_status)

        self.tbl_users = QTableWidget(0, 3)
        self.tbl_users.setHorizontalHeaderLabels([tr("メールアドレス"), tr("名前"), tr("登録日")])
        self.tbl_users.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_users.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_users.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_users.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_users.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_users.setMinimumHeight(160)
        self.tbl_users.setMaximumHeight(240)
        self.tbl_users.setAlternatingRowColors(True)
        self.tbl_users.verticalHeader().setVisible(False)

        tbl_btn_row = QHBoxLayout()
        tbl_btn_row.setSpacing(8)
        btn_refresh = QPushButton("  " + tr("一覧を更新") + "  ")
        btn_refresh.setObjectName("secondaryActionBtn")
        btn_refresh.setFixedHeight(30)
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.clicked.connect(self._refresh_user_list)

        btn_remove = QPushButton("  " + tr("選択ユーザーを削除") + "  ")
        btn_remove.setObjectName("secondaryActionBtn")
        btn_remove.setFixedHeight(30)
        btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_remove.clicked.connect(self._remove_selected_user)

        tbl_btn_row.addWidget(btn_refresh)
        tbl_btn_row.addWidget(btn_remove)
        tbl_btn_row.addStretch()

        sep2 = self._sep()

        # ── ユーザー追加 ────────────────────────────────────────────────────
        lbl_add = QLabel(tr("ユーザーを追加"))
        lbl_add.setStyleSheet("font-weight: bold; font-size: 12px;")

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.edt_add_email = QLineEdit()
        self.edt_add_email.setPlaceholderText(tr("メールアドレス"))
        self.edt_add_email.setFixedHeight(32)

        self.edt_add_name = QLineEdit()
        self.edt_add_name.setPlaceholderText(tr("名前 (任意)"))
        self.edt_add_name.setFixedWidth(150)
        self.edt_add_name.setFixedHeight(32)

        btn_add = QPushButton("  " + tr("追加") + "  ")
        btn_add.setObjectName("primaryActionBtn")
        btn_add.setFixedHeight(32)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self._add_user)

        add_row.addWidget(self.edt_add_email, 1)
        add_row.addWidget(self.edt_add_name)
        add_row.addWidget(btn_add)

        # 組み立て
        root.addWidget(lbl_sheets)
        root.addLayout(sheets_row)
        root.addWidget(note_sheets)
        root.addWidget(sep1)
        root.addLayout(tbl_hdr_row)
        root.addWidget(self.tbl_users)
        root.addLayout(tbl_btn_row)
        root.addWidget(sep2)
        root.addWidget(lbl_add)
        root.addLayout(add_row)

        from app.core.config import SHEETS_REGISTRY_ID
        self.edt_sheets_id.setText(SHEETS_REGISTRY_ID)
        return grp

    # ── 管理者アクション ────────────────────────────────────────────────────

    def _refresh_user_list(self):
        self.lbl_users_status.setText(tr("取得中..."))
        self._fetch_users_worker = FetchUsersWorker()
        self._fetch_users_worker.success.connect(self._on_users_fetched)
        self._fetch_users_worker.error.connect(lambda e: self.lbl_users_status.setText(str(e)[:60]))
        self._fetch_users_worker.finished.connect(self._fetch_users_worker.deleteLater)
        self._fetch_users_worker.start()
        self.track_worker(self._fetch_users_worker)

    def _on_users_fetched(self, users):
        self.tbl_users.setRowCount(0)
        for u in users:
            r = self.tbl_users.rowCount()
            self.tbl_users.insertRow(r)
            self.tbl_users.setItem(r, 0, QTableWidgetItem(u["email"]))
            self.tbl_users.setItem(r, 1, QTableWidgetItem(u["name"]))
            self.tbl_users.setItem(r, 2, QTableWidgetItem(u["added"]))
        self.lbl_users_status.setText(tr("{0} 件").format(len(users)))

    def _remove_selected_user(self):
        if not self.tbl_users.selectedItems():
            return
        email = self.tbl_users.item(self.tbl_users.currentRow(), 0).text()
        reply = QMessageBox.question(
            self, tr("確認"),
            tr("{0} を削除しますか？").format(email),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.lbl_users_status.setText(tr("削除中..."))
        self._remove_user_worker = RemoveUserWorker(email)
        self._remove_user_worker.success.connect(self._refresh_user_list)
        self._remove_user_worker.error.connect(lambda e: QMessageBox.warning(self, tr("エラー"), str(e)))
        self._remove_user_worker.finished.connect(self._remove_user_worker.deleteLater)
        self._remove_user_worker.start()
        self.track_worker(self._remove_user_worker)

    def _add_user(self):
        email = self.edt_add_email.text().strip()
        name  = self.edt_add_name.text().strip()
        if not email:
            self.edt_add_email.setFocus()
            return
        self.lbl_users_status.setText(tr("追加中..."))
        self._add_user_worker = AddUserWorker(email, name)
        self._add_user_worker.success.connect(self._on_user_added)
        self._add_user_worker.error.connect(lambda e: QMessageBox.warning(self, tr("エラー"), str(e)))
        self._add_user_worker.finished.connect(self._add_user_worker.deleteLater)
        self._add_user_worker.start()
        self.track_worker(self._add_user_worker)

    def _on_user_added(self):
        self.edt_add_email.clear()
        self.edt_add_name.clear()
        self._refresh_user_list()
        self._show_toast("✅  " + tr("ユーザーを追加しました"))

    # ── テーマ ───────────────────────────────────────────────────────────────

    def set_theme(self, is_dark: bool):
        if is_dark:
            cmb_style = (
                "QComboBox {"
                "  background-color: #3d3d3d; color: #e0e0e0;"
                "  border: 1px solid #666666; border-radius: 4px; padding: 4px 10px;"
                "}"
                "QComboBox:hover { border-color: #909090; }"
                "QComboBox:focus { border: 1px solid #0e639c; }"
                "QComboBox::drop-down { background-color: #505050; width: 22px; border-left: 1px solid #666666; }"
                "QComboBox QAbstractItemView {"
                "  background-color: #464646; color: #e0e0e0;"
                "  selection-background-color: #0e639c; selection-color: #ffffff;"
                "  border: 1px solid #707070; outline: none;"
                "}"
                "QComboBox QAbstractItemView::item { padding: 5px 10px; min-height: 22px; }"
                "QComboBox QAbstractItemView::item:hover { background-color: #565656; color: #ffffff; }"
            )
            spin_style = (
                "QSpinBox, QDoubleSpinBox {"
                "  background-color: #3d3d3d; color: #e0e0e0;"
                "  border: 1px solid #666666; border-radius: 4px; padding: 4px 10px;"
                "}"
                "QSpinBox:hover, QDoubleSpinBox:hover { border-color: #909090; }"
                "QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid #0e639c; }"
            )
        else:
            cmb_style = (
                "QComboBox {"
                "  background-color: #ffffff; color: #333333;"
                "  border: 1px solid #cccccc; border-radius: 4px; padding: 4px 10px;"
                "}"
                "QComboBox:hover { border-color: #999999; }"
                "QComboBox:focus { border: 1px solid #1a73e8; }"
                "QComboBox::drop-down { background-color: #f0f0f0; width: 22px; border-left: 1px solid #cccccc; }"
                "QComboBox QAbstractItemView {"
                "  background-color: #ffffff; color: #333333;"
                "  selection-background-color: #1a73e8; selection-color: #ffffff;"
                "  border: 1px solid #cccccc; outline: none;"
                "}"
                "QComboBox QAbstractItemView::item { padding: 5px 10px; min-height: 22px; }"
                "QComboBox QAbstractItemView::item:hover { background-color: #f0f0f0; color: #1a73e8; }"
            )
            spin_style = (
                "QSpinBox, QDoubleSpinBox {"
                "  background-color: #ffffff; color: #333333;"
                "  border: 1px solid #cccccc; border-radius: 4px; padding: 4px 10px;"
                "}"
                "QSpinBox:hover, QDoubleSpinBox:hover { border-color: #999999; }"
                "QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid #1a73e8; }"
            )

        for w in self.findChildren(QComboBox):
            w.setStyleSheet(cmb_style)
        for w in self.findChildren(QSpinBox) + self.findChildren(QDoubleSpinBox):
            w.setStyleSheet(spin_style)

        super().set_theme(is_dark)
        self.apply_theme_custom()

    def apply_theme_custom(self):
        is_dark = self.is_dark
        pc = UIColors.get_panel_colors(is_dark)
        bc = pc["border"]
        dc = pc["text_dim"]
        self._hdr_frame.setStyleSheet(
            f"QFrame#settingsHeader {{ border-bottom: 1px solid {bc}; }}"
        )
        self._footer_frame.setStyleSheet(
            f"QFrame#settingsFooter {{ border-top: 1px solid {bc}; }}"
        )
        self.ver_lbl.setStyleSheet(f"color: {dc}; font-size: 12px;")
        for lbl in self._note_labels:
            lbl.setStyleSheet(f"color: {dc}; font-size: 11px;")
        for sep in self.findChildren(QFrame, "settingsSep"):
            sep.setStyleSheet(f"QFrame#settingsSep {{ border-top: 1px solid {bc}; }}")

        line_edit_style = f"""
            QLineEdit {{
                background-color: {'#3d3d3d' if is_dark else '#ffffff'};
                color: {'#e0e0e0' if is_dark else '#333333'};
                border: 1px solid {'#666666' if is_dark else '#cccccc'};
                border-radius: 4px; padding: 4px 10px;
            }}
            QLineEdit:hover {{ border-color: {'#909090' if is_dark else '#999999'}; }}
            QLineEdit:focus {{ border: 1px solid {'#0e639c' if is_dark else '#1a73e8'}; }}
        """
        for w in self.findChildren(QLineEdit):
            w.setStyleSheet(line_edit_style)

        scroll_style = f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; }}
            QScrollBar::handle:vertical {{ background: {'rgba(255,255,255,0.2)' if is_dark else 'rgba(0,0,0,0.2)'}; border-radius: 4px; }}
            QScrollBar::handle:vertical:hover {{ background: {'rgba(255,255,255,0.3)' if is_dark else 'rgba(0,0,0,0.3)'}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """
        for w in self.findChildren(QScrollArea):
            w.setStyleSheet(scroll_style)

    # ── データ読み書き ────────────────────────────────────────────────────────

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

        model = s.get("gemini_model", "gemini-2.5-flash")
        self.cmb_gemini_model.setCurrentIndex(
            _GEMINI_MODEL_CODES.index(model) if model in _GEMINI_MODEL_CODES else 0
        )
        self.spn_temperature.setValue(float(s.get("ai_temperature", 0.7)))

        max_tok = int(s.get("ai_max_tokens", 2048))
        self.cmb_max_tokens.setCurrentIndex(
            _MAX_TOKENS_OPTIONS.index(max_tok) if max_tok in _MAX_TOKENS_OPTIONS else 2
        )
        self.spn_history.setValue(int(s.get("chat_history_limit", 20)))

        lang = s.get("language", "auto")
        self.cmb_language.setCurrentIndex(
            _LANG_CODES.index(lang) if lang in _LANG_CODES else 0
        )

        self.spn_cal_int.setValue(int(s.get("calendar_poll_interval", 5)))
        self.spn_gmail_int.setValue(int(s.get("gmail_poll_interval", 5)))
        self.spn_gmail_max.setValue(int(s.get("gmail_max_results", 50)))

    def _get_ui_settings(self) -> dict:
        return {
            "imbalance_alert":        self.spn_imb_alert.value(),
            "reserve_low":            self.spn_res_low.value(),
            "reserve_warn":           self.spn_res_warn.value(),
            "imbalance_interval":     self.spn_imb_int.value(),
            "reserve_interval":       self.spn_res_int.value(),
            "weather_interval":       self.spn_wea_int.value(),
            "hjks_interval":          self.spn_hjks_int.value(),
            "jkm_interval":           self.spn_jkm_int.value(),
            "retention_days":         self.spn_retention.value(),
            "auto_start":             self.chk_auto_start.isChecked(),
            "language":               _LANG_CODES[self.cmb_language.currentIndex()],
            "gemini_model":           _GEMINI_MODEL_CODES[self.cmb_gemini_model.currentIndex()],
            "ai_temperature":         round(self.spn_temperature.value(), 1),
            "ai_max_tokens":          _MAX_TOKENS_OPTIONS[self.cmb_max_tokens.currentIndex()],
            "chat_history_limit":     self.spn_history.value(),
            "calendar_poll_interval": self.spn_cal_int.value(),
            "gmail_poll_interval":    self.spn_gmail_int.value(),
            "gmail_max_results":      self.spn_gmail_max.value(),
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
        self._toast_anim.stop()
        self._toast_anim.setStartValue(0.0)
        self._toast_anim.setEndValue(1.0)
        if self._toast_anim.receivers(self._toast_anim.finished):
            self._toast_anim.finished.disconnect()
        self._toast_anim.start()
        self._toast_timer.start(3500)

    def _hide_toast(self):
        self._toast_anim.stop()
        self._toast_anim.setStartValue(1.0)
        self._toast_anim.setEndValue(0.0)
        self._toast_anim.finished.connect(self.toast_label.hide)
        self._toast_anim.start()

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
        self.cmb_max_tokens.setCurrentIndex(2)
        self.spn_history.setValue(20)

    # ── データ整理 ────────────────────────────────────────────────────────────

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
        self._retention_worker = DataRetentionWorker(self.spn_retention.value())
        self._retention_worker.finished.connect(self._on_retention_finished)
        self._retention_worker.error.connect(self._on_retention_error)
        self._retention_worker.finished.connect(self._retention_worker.deleteLater)
        self._retention_worker.start()
        self.track_worker(self._retention_worker)

    def _on_retention_finished(self):
        QApplication.restoreOverrideCursor()
        self.btn_run_retention.setEnabled(True)
        self.btn_run_retention.setText("  " + tr("今すぐ整理実行") + "  ")
        QMessageBox.information(
            self, tr("完了"),
            tr("古いデータのバックアップと削除が完了しました。\n(保存先: backups フォルダ)"),
        )

    def _on_retention_error(self, err: str):
        QApplication.restoreOverrideCursor()
        self.btn_run_retention.setEnabled(True)
        self.btn_run_retention.setText("  " + tr("今すぐ整理実行") + "  ")
        QMessageBox.warning(
            self, tr("エラー"),
            tr("処理中にエラーが発生しました:") + f"\n{err}",
        )

    # ── 自動起動 ─────────────────────────────────────────────────────────────

    def _toggle_auto_start(self, enable: bool):
        set_autostart(enable)
