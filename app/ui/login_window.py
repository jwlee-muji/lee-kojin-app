"""
ログイン画面

フロー:
  1. Google アカウントでログイン ボタン → OAuth (バックグラウンドスレッド)
  2. 認証成功 → ユーザー登録確認 (Sheets)
  3. 登録済み → login_success シグナル (email) → メインウィンドウへ
  4. 未登録 → 「登録されていません」画面 → アクセス申請 or 戻る
"""
import re
import logging
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QLineEdit,
    QFrame, QApplication, QDialog, QTextEdit,
)
from PySide6.QtCore import (
    Qt, QThread, Signal, QPropertyAnimation, QEasingCurve, QTimer, QRect,
)
from app.core.i18n import tr
from app.ui.theme import get_global_qss, ThemePalette, UIColors

logger = logging.getLogger(__name__)

# ── ページインデックス ──────────────────────────────────────────────────────
_PAGE_LOGIN         = 0
_PAGE_NOT_REGISTERED = 1
_PAGE_LOADING       = 2


class _LoginWorker(QThread):
    """バックグラウンドで OAuth + ユーザー登録確認を実行するスレッド。"""
    success        = Signal(str)   # 登録済み → email
    not_registered = Signal(str)   # 未登録 → email
    failed         = Signal(str)   # エラー → message

    def run(self):
        try:
            from app.api.google.auth import run_oauth_flow, get_current_user_email, revoke_credentials
            from app.api.user_registry import is_user_registered, RegistryCheckError

            ok = run_oauth_flow()
            if not ok:
                self.failed.emit(tr("Google 認証に失敗しました。もう一度お試しください。"))
                return

            email = get_current_user_email() or ""
            if not email:
                revoke_credentials()
                self.failed.emit(tr("メールアドレスを取得できませんでした。"))
                return

            try:
                registered = is_user_registered(email)
            except RegistryCheckError as e:
                revoke_credentials()
                self.failed.emit(
                    tr("ユーザー確認中にエラーが発生しました。\n管理者に連絡してください。\n\n") + str(e)
                )
                return

            if registered:
                self.success.emit(email)
            else:
                revoke_credentials()
                self.not_registered.emit(email)

        except Exception as e:
            logger.error(f"ログインワーカーエラー: {e}", exc_info=True)
            self.failed.emit(str(e))


class _AccessRequestDialog(QDialog):
    """アクセス申請ダイアログ (内蔵 SMTP で管理者へ直接送信)。"""

    def __init__(self, prefill_email: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("アクセスを申請する"))
        self.setFixedSize(420, 290)
        self.setModal(True)
        self._worker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        desc = QLabel(tr("管理者 (jw.lee@shirokumapower.com) へアクセス申請メールを送信します。"))
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #aaa; font-size: 12px;")
        layout.addWidget(desc)

        layout.addWidget(QLabel(tr("申請メールアドレス:")))
        self.email_edit = QLineEdit(prefill_email)
        self.email_edit.setPlaceholderText("your@example.com")
        self.email_edit.setFixedHeight(34)
        layout.addWidget(self.email_edit)

        layout.addWidget(QLabel(tr("メッセージ (任意):")))
        self.msg_edit = QTextEdit()
        self.msg_edit.setPlaceholderText(tr("アクセスをリクエストします。"))
        self.msg_edit.setFixedHeight(64)
        layout.addWidget(self.msg_edit)

        self.status_lbl = QLabel()
        self.status_lbl.setStyleSheet("font-size: 12px;")
        self.status_lbl.setWordWrap(True)
        layout.addWidget(self.status_lbl)

        btns = QHBoxLayout()
        self.btn_cancel = QPushButton(tr("キャンセル"))
        self.btn_cancel.setObjectName("secondaryActionBtn")
        self.btn_cancel.setFixedHeight(34)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_send = QPushButton(tr("メールを送信"))
        self.btn_send.setObjectName("primaryActionBtn")
        self.btn_send.setFixedHeight(34)
        self.btn_send.clicked.connect(self._send)

        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_send)
        layout.addLayout(btns)

    def _send(self):
        email = self.email_edit.text().strip()
        if not email:
            self.email_edit.setFocus()
            self.status_lbl.setText(tr("⚠  メールアドレスを入力してください。"))
            self.status_lbl.setStyleSheet("font-size: 12px; color: #ff9800;")
            return
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            self.email_edit.setFocus()
            self.status_lbl.setText(tr("⚠  メールアドレスの形式が正しくありません。"))
            self.status_lbl.setStyleSheet("font-size: 12px; color: #ff9800;")
            return

        from app.core.config import __version__
        subject = f"[LEE v{__version__}] アクセス申請: {email}"
        body = (
            f"【申請メールアドレス】{email}\n\n"
            f"【メッセージ】\n{self.msg_edit.toPlainText().strip() or tr('(なし)')}\n\n"
            "--- LEE 電力モニター アクセス申請 ---"
        )

        self.btn_send.setEnabled(False)
        self.btn_send.setText(tr("送信中..."))
        self.status_lbl.setText("")

        from app.api.email_api import SendBugReportWorker
        self._worker = SendBugReportWorker(subject, body)
        self._worker.success.connect(self._on_send_success)
        self._worker.error.connect(self._on_send_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_send_success(self):
        self.status_lbl.setText(tr("✅  申請メールを送信しました。管理者の承認をお待ちください。"))
        self.status_lbl.setStyleSheet("font-size: 12px; color: #4caf50;")
        self.btn_send.setText(tr("送信完了"))
        QTimer.singleShot(2000, self.accept)

    def _on_send_error(self, err: str):
        self.btn_send.setEnabled(True)
        self.btn_send.setText(tr("メールを送信"))
        self.status_lbl.setText(f"❌  {tr('送信失敗:')} {err[:80]}")
        self.status_lbl.setStyleSheet("font-size: 12px; color: #ff5252;")


class LoginWindow(QMainWindow):
    """ログイン画面。認証成功時に login_success(email) を emit する。"""

    login_success = Signal(str)  # ログイン成功 → email

    def __init__(self):
        super().__init__()
        self._worker: _LoginWorker | None = None
        self._failed_email = ""
        self._setup_ui()
        self._apply_style()

    # ── UI 構築 ─────────────────────────────────────────────────────────────

    def _setup_ui(self):
        from app.core.config import __version__
        self.setWindowTitle(f"LEE 電力モニター  v{__version__}")
        self.setMinimumSize(480, 580)
        self.resize(480, 580)
        self._center()

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        self.stack.addWidget(self._build_login_page())        # 0
        self.stack.addWidget(self._build_not_registered_page())  # 1
        self.stack.addWidget(self._build_loading_page())      # 2

    # ── ログインページ ───────────────────────────────────────────────────────

    def _build_login_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(56, 0, 56, 40)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignCenter)

        # アイコン
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(88, 88)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setObjectName("loginIcon")
        self._set_app_icon(icon_lbl)

        # タイトル
        title = QLabel("LEE 電力モニター")
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("loginTitle")

        # サブタイトル
        subtitle = QLabel(tr("承認済みアカウントでサインイン"))
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setObjectName("loginSubtitle")

        # セパレーター
        sep = self._hline()

        # Google ボタン
        self.btn_google = QPushButton()
        self.btn_google.setFixedHeight(48)
        self.btn_google.setObjectName("googleBtn")
        self.btn_google.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_google_btn_text(tr("  Google アカウントでサインイン"))
        self.btn_google.clicked.connect(self._start_login)

        # エラーラベル
        self.lbl_error = QLabel()
        self.lbl_error.setAlignment(Qt.AlignCenter)
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setObjectName("loginError")
        self.lbl_error.hide()

        # 区切り
        or_layout = QHBoxLayout()
        or_layout.setSpacing(10)
        l1, l2 = self._hline(), self._hline()
        or_lbl = QLabel(tr("または"))
        or_lbl.setAlignment(Qt.AlignCenter)
        or_lbl.setObjectName("loginOr")
        or_layout.addWidget(l1); or_layout.addWidget(or_lbl); or_layout.addWidget(l2)

        # アクセス申請リンク
        self.btn_request = QPushButton(tr("アクセスを申請する →"))
        self.btn_request.setFlat(True)
        self.btn_request.setObjectName("requestLink")
        self.btn_request.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_request.clicked.connect(lambda: self._open_request_dialog(""))

        layout.addStretch(2)
        layout.addWidget(icon_lbl, alignment=Qt.AlignCenter)
        layout.addSpacing(18)
        layout.addWidget(title)
        layout.addSpacing(6)
        layout.addWidget(subtitle)
        layout.addSpacing(32)
        layout.addWidget(sep)
        layout.addSpacing(28)
        layout.addWidget(self.btn_google)
        layout.addSpacing(8)
        layout.addWidget(self.lbl_error)
        layout.addSpacing(28)
        layout.addLayout(or_layout)
        layout.addSpacing(16)
        layout.addWidget(self.btn_request, alignment=Qt.AlignCenter)
        layout.addStretch(3)
        return page

    # ── 未登録ページ ─────────────────────────────────────────────────────────

    def _build_not_registered_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(56, 0, 56, 40)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignCenter)

        icon_lbl = QLabel("⚠️")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 52px;")

        title = QLabel(tr("登録されていません"))
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("loginTitle")

        self.lbl_nr_email = QLabel()
        self.lbl_nr_email.setAlignment(Qt.AlignCenter)
        self.lbl_nr_email.setObjectName("loginSubtitle")

        desc = QLabel(tr(
            "このアカウントはアクセス権がありません。\n"
            "管理者にアクセスを申請してください。"
        ))
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setObjectName("loginDesc")

        sep = self._hline()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        btn_back = QPushButton(tr("← 戻る"))
        btn_back.setObjectName("secondaryActionBtn")
        btn_back.setFixedHeight(40)
        btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_back.clicked.connect(self.reset)

        btn_req = QPushButton(tr("アクセスを申請"))
        btn_req.setObjectName("primaryActionBtn")
        btn_req.setFixedHeight(40)
        btn_req.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_req.clicked.connect(lambda: self._open_request_dialog(self._failed_email))

        btn_row.addWidget(btn_back)
        btn_row.addWidget(btn_req)

        layout.addStretch(2)
        layout.addWidget(icon_lbl)
        layout.addSpacing(20)
        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(self.lbl_nr_email)
        layout.addSpacing(16)
        layout.addWidget(desc)
        layout.addSpacing(32)
        layout.addWidget(sep)
        layout.addSpacing(24)
        layout.addLayout(btn_row)
        layout.addStretch(3)
        return page

    # ── ローディングページ ───────────────────────────────────────────────────

    def _build_loading_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)

        spinner = QLabel("⏳")
        spinner.setAlignment(Qt.AlignCenter)
        spinner.setStyleSheet("font-size: 48px;")

        lbl = QLabel(tr("認証中..."))
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setObjectName("loginSubtitle")

        hint = QLabel(tr("ブラウザでサインインを完了してください"))
        hint.setAlignment(Qt.AlignCenter)
        hint.setObjectName("loginDesc")

        hint2 = QLabel(tr("(ブラウザを閉じると 2 分後に自動キャンセルされます)"))
        hint2.setAlignment(Qt.AlignCenter)
        hint2.setStyleSheet("font-size: 11px; color: #555;")

        btn_cancel = QPushButton(tr("キャンセル"))
        btn_cancel.setObjectName("secondaryActionBtn")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setFixedWidth(120)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self._cancel_login)

        layout.addWidget(spinner)
        layout.addSpacing(16)
        layout.addWidget(lbl)
        layout.addSpacing(8)
        layout.addWidget(hint)
        layout.addSpacing(4)
        layout.addWidget(hint2)
        layout.addSpacing(28)
        layout.addWidget(btn_cancel, alignment=Qt.AlignCenter)
        return page

    # ── ロジック ─────────────────────────────────────────────────────────────

    def _start_login(self):
        self.lbl_error.hide()
        self.stack.setCurrentIndex(_PAGE_LOADING)

        self._worker = _LoginWorker()
        self._worker.success.connect(self._on_success)
        self._worker.not_registered.connect(self._on_not_registered)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_success(self, email: str):
        logger.info(f"ログイン成功: {email}")
        self._animate_out(email)

    def _on_not_registered(self, email: str):
        self._failed_email = email
        self.lbl_nr_email.setText(email)
        self.stack.setCurrentIndex(_PAGE_NOT_REGISTERED)

    def _on_failed(self, msg: str):
        self.stack.setCurrentIndex(_PAGE_LOGIN)
        self.lbl_error.setText(f"⚠  {msg}")
        self.lbl_error.show()

    def _cancel_login(self):
        """認証中にキャンセルボタンを押した場合の処理。"""
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(800)
            self._worker = None
        self.stack.setCurrentIndex(_PAGE_LOGIN)
        self.lbl_error.hide()

    def _open_request_dialog(self, prefill: str):
        dlg = _AccessRequestDialog(prefill_email=prefill, parent=self)
        dlg.exec()

    # ── アニメーション ────────────────────────────────────────────────────────

    def _animate_out(self, email: str):
        """ログイン成功後にウィンドウを沈み込ませながらフェードアウト。"""
        self._out_op_anim = QPropertyAnimation(self, b"windowOpacity")
        self._out_op_anim.setStartValue(1.0)
        self._out_op_anim.setEndValue(0.0)
        self._out_op_anim.setDuration(300)
        self._out_op_anim.setEasingCurve(QEasingCurve.InCubic)

        start_rect = self.geometry()
        end_rect = QRect(start_rect.x(), start_rect.y() + 20, start_rect.width(), start_rect.height())
        self._out_pos_anim = QPropertyAnimation(self, b"geometry")
        self._out_pos_anim.setStartValue(start_rect)
        self._out_pos_anim.setEndValue(end_rect)
        self._out_pos_anim.setDuration(300)
        self._out_pos_anim.setEasingCurve(QEasingCurve.InCubic)

        self._out_op_anim.finished.connect(lambda: self.login_success.emit(email))
        self._out_op_anim.start()
        self._out_pos_anim.start()

    # ── ユーティリティ ────────────────────────────────────────────────────────

    def reset(self):
        """ログイン画面をリセットして先頭ページに戻す。"""
        self.setWindowOpacity(1.0)
        self._failed_email = ""
        self.lbl_error.hide()
        self._set_google_btn_text(tr("  Google アカウントでサインイン"))
        self.btn_google.setEnabled(True)
        self.stack.setCurrentIndex(_PAGE_LOGIN)

    def show_animated(self):
        """下から浮かび上がりながらフェードインする。"""
        self.setWindowOpacity(0.0)
        self.show()
        
        start_rect = self.geometry()
        start_rect.moveTop(start_rect.top() + 20)
        end_rect = self.geometry()
        self.setGeometry(start_rect)

        self._in_op_anim = QPropertyAnimation(self, b"windowOpacity")
        self._in_op_anim.setStartValue(0.0)
        self._in_op_anim.setEndValue(1.0)
        self._in_op_anim.setDuration(400)
        self._in_op_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._in_pos_anim = QPropertyAnimation(self, b"geometry")
        self._in_pos_anim.setStartValue(start_rect)
        self._in_pos_anim.setEndValue(end_rect)
        self._in_pos_anim.setDuration(500)
        self._in_pos_anim.setEasingCurve(QEasingCurve.OutExpo)

        self._in_op_anim.start()
        self._in_pos_anim.start()

    def closeEvent(self, event):
        """ログイン画面を閉じたらアプリを終了する。
        hide() 時は呼ばれないため、メインウィンドウ移行後に誤って終了することはない。"""
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(500)
        event.accept()
        QApplication.instance().quit()

    def _center(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - self.width())  // 2,
            (screen.height() - self.height()) // 2,
        )

    @staticmethod
    def _hline() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("loginSep")
        return line

    def _set_app_icon(self, label: QLabel):
        try:
            icon = QApplication.instance().windowIcon()
            if not icon.isNull():
                px = icon.pixmap(80, 80)
                label.setPixmap(px)
                return
        except Exception:
            pass
        label.setText("⚡")
        label.setStyleSheet("font-size: 52px;")

    def _set_google_btn_text(self, text: str):
        self.btn_google.setText(text)

    # ── スタイル ─────────────────────────────────────────────────────────────

    def _apply_style(self, is_dark: bool = True):
        bg         = ThemePalette.bg_primary(is_dark)
        card_bg    = ThemePalette.bg_secondary(is_dark)
        tc_emph    = UIColors.text_emphasis(is_dark)
        tc_dim     = UIColors.text_secondary(is_dark)
        sep_c      = UIColors.BORDER_DARK if is_dark else UIColors.BORDER_LIGHT
        bc         = "#555555" if is_dark else "#cccccc"
        primary    = UIColors.action_blue(is_dark)
        primary_hv = "#1177bb" if is_dark else "#1565c0"
        sec_bg     = ThemePalette.BG_INPUT_DARK if is_dark else "#dddddd"
        sec_hv     = "#4a4a4a" if is_dark else "#cccccc"
        sec_tc     = "#cccccc" if is_dark else UIColors.text_primary(is_dark)
        google_dis = "#555555" if is_dark else "#cccccc"
        google_dtc = "#999999" if is_dark else "#888888"
        or_c       = "#666666" if is_dark else "#aaaaaa"

        mode = "dark" if is_dark else "light"
        self.setStyleSheet(get_global_qss(mode) + f"""
            QMainWindow, QWidget {{
                background-color: {bg};
            }}
            QLabel#loginTitle {{
                font-size: 26px;
                font-weight: bold;
                color: {tc_emph};
            }}
            QLabel#loginSubtitle {{
                font-size: 13px;
                color: {tc_dim};
            }}
            QLabel#loginDesc {{
                font-size: 12px;
                color: {UIColors.TEXT_MUTED};
                line-height: 1.6;
            }}
            QLabel#loginOr {{
                font-size: 12px;
                color: {or_c};
                min-width: 40px;
            }}
            QLabel#loginError {{
                font-size: 12px;
                color: {UIColors.OFFLINE_COLOR};
                padding: 6px 12px;
                background: rgba(255,82,82,0.1);
                border-radius: 4px;
            }}
            QFrame#loginSep {{
                color: {sep_c};
                max-height: 1px;
            }}
            QPushButton#googleBtn {{
                background-color: #4285F4;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                padding: 0 16px;
            }}
            QPushButton#googleBtn:hover {{ background-color: #357ae8; }}
            QPushButton#googleBtn:pressed {{ background-color: #2a6dd9; }}
            QPushButton#googleBtn:disabled {{
                background-color: {google_dis};
                color: {google_dtc};
            }}
            QPushButton#requestLink {{
                background: transparent;
                border: none;
                color: #4285F4;
                font-size: 13px;
                text-decoration: underline;
            }}
            QPushButton#requestLink:hover {{ color: #76a9f5; }}
            QPushButton#primaryActionBtn {{
                background-color: {primary};
                color: #ffffff;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                padding: 6px 20px;
            }}
            QPushButton#primaryActionBtn:hover {{ background-color: {primary_hv}; }}
            QPushButton#secondaryActionBtn {{
                background-color: {sec_bg};
                color: {sec_tc};
                border: 1px solid {bc};
                border-radius: 4px;
                font-size: 13px;
                padding: 6px 20px;
            }}
            QPushButton#secondaryActionBtn:hover {{ background-color: {sec_hv}; }}
            QDialog {{ background: {card_bg}; }}
        """)
