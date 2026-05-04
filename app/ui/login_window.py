"""ログイン画面 — A+ Refined Dark.

Frameless + 커스텀 그라데이션 배경 (paintEvent) + 3 페이지 스택.

フロー:
  1. Google アカウントでログイン (Page 0) → OAuth (バックグラウンドスレッド, Page 2)
  2. 認証成功 → ユーザー登録確認 (Sheets)
  3. 登録済み → login_success(email) → メインウィンドウへ
  4. 未登録 → Page 1 (アクセス申請 / 戻る)
"""
from __future__ import annotations

import re
import logging

from PySide6.QtCore import (
    Qt, QThread, Signal, QPropertyAnimation, QEasingCurve, QTimer, QRect, QPoint,
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QRadialGradient, QMouseEvent,
)
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QLineEdit,
    QFrame, QApplication, QTextEdit, QSizePolicy,
)

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QPixmap
from PySide6.QtSvg import QSvgRenderer

from app.core.i18n import tr
from app.core.config import __version__
from app.ui.components import LeeButton, LeeDialog, LeeRingSpinner

logger = logging.getLogger(__name__)

# ── ページインデックス ──────────────────────────────────────────────────────
_PAGE_LOGIN          = 0
_PAGE_NOT_REGISTERED = 1
_PAGE_LOADING        = 2

# ── ウィンドウサイズ (固定) ─────────────────────────────────────────────────
_WIN_W = 480
_WIN_H = 580


# ──────────────────────────────────────────────────────────────────────────
# Google G 4-color SVG (varA-login-window.jsx 의 LWGoogleBtn 와 동일)
# ──────────────────────────────────────────────────────────────────────────
_GOOGLE_G_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
</svg>"""


def _google_g_pixmap(size: int = 18) -> QPixmap:
    """Google G 로고를 size×size QPixmap으로 렌더."""
    renderer = QSvgRenderer(QByteArray(_GOOGLE_G_SVG))
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p)
    p.end()
    return pix


# ──────────────────────────────────────────────────────────────────────────
# 警告 글리프 타일 (varA-login-window.jsx:139-144 / :703-707 디자인 정합)
# 72×72 amber tile + 36px stroke 삼각형 + 중앙 ! 마크
# ──────────────────────────────────────────────────────────────────────────
class _WarnTile(QFrame):
    def __init__(self, size: int = 72, parent=None):
        super().__init__(parent)
        self.setObjectName("loginWarnTile")
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        from PySide6.QtGui import QPainterPath
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        amber = QColor("#FF9F0A")
        pen = QPen(amber, 2.5)
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        # 36px 삼각형 stroke
        s = 36.0
        cx = self.width() / 2
        cy = self.height() / 2 + 1.5
        path = QPainterPath()
        path.moveTo(cx, cy - s / 2)
        path.lineTo(cx + s / 2, cy + s / 2)
        path.lineTo(cx - s / 2, cy + s / 2)
        path.closeSubpath()
        p.drawPath(path)
        # 내부 ! (라인 + 점)
        p.drawLine(cx, cy - 4, cx, cy + 5)
        p.setBrush(amber); p.setPen(Qt.NoPen)
        p.drawEllipse(int(cx - 1.5), int(cy + 9), 3, 3)
        p.end()


# ──────────────────────────────────────────────────────────────────────────
# OAuth Worker (기존 그대로)
# ──────────────────────────────────────────────────────────────────────────
class _LoginWorker(QThread):
    """バックグラウンドで OAuth + ユーザー登録確認を実行。"""
    success        = Signal(str)
    not_registered = Signal(str)
    failed         = Signal(str)

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


# ──────────────────────────────────────────────────────────────────────────
# AccessRequestDialog — LeeDialog 베이스 + 폼 위젯
# ──────────────────────────────────────────────────────────────────────────
class _SubmitAccessRequestWorker(QThread):
    """Google Sheets (AccessRequests シート) にアクセス申請を 1 行追加."""
    success = Signal(str)   # request_id
    error   = Signal(str)

    def __init__(self, email: str, message: str, app_version: str):
        super().__init__()
        self._email = email
        self._message = message
        self._app_version = app_version

    def run(self) -> None:
        try:
            from app.api.google.sheets import submit_access_request
            request_id = submit_access_request(
                self._email, self._message, self._app_version,
            )
            self.success.emit(request_id)
        except Exception as e:
            logger.error(f"AccessRequest submit failed: {e}", exc_info=True)
            self.error.emit(str(e))


class _AccessRequestDialog(LeeDialog):
    """アクセス申請 폼 (Google Sheets AccessRequests シートに登録)."""

    def __init__(self, prefill_email: str = "", parent=None):
        super().__init__(tr("アクセスを申請する"), kind="info", parent=parent)
        self._worker = None

        self.set_message(tr("管理者宛の申請を Google スプレッドシートに登録します。承認されるとアクセスできるようになります。"))

        # ── 폼 필드 (본문 영역 추가) ──
        email_label = QLabel(tr("申請メールアドレス:"))
        email_label.setObjectName("accessReqLabel")
        self.add_body_widget(email_label)

        self._email_edit = QLineEdit(prefill_email)
        self._email_edit.setPlaceholderText("your@example.com")
        self._email_edit.setMinimumHeight(34)
        self.add_body_widget(self._email_edit)

        msg_label = QLabel(tr("メッセージ (任意):"))
        msg_label.setObjectName("accessReqLabel")
        self.add_body_widget(msg_label)

        self._msg_edit = QTextEdit()
        self._msg_edit.setPlaceholderText(tr("アクセスをリクエストします。"))
        self._msg_edit.setFixedHeight(72)
        self.add_body_widget(self._msg_edit)

        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("accessReqStatus")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setMinimumHeight(20)
        self.add_body_widget(self._status_lbl)

        # ── 푸터: 取消(reject) + 送信(custom) ──
        self.add_button(tr("キャンセル"), "secondary", role="reject")
        self._btn_send = LeeButton(tr("申請する"), variant="primary", size="md")
        self._btn_send.clicked.connect(self._send)
        self._footer_layout.addWidget(self._btn_send)

        self.setMinimumWidth(460)

    # ── 송신 로직 ─────────────────────────────────────────────────────────
    def _send(self) -> None:
        email = self._email_edit.text().strip()
        if not email:
            self._email_edit.setFocus()
            self._set_status(tr("⚠  メールアドレスを入力してください。"), "warn")
            return
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            self._email_edit.setFocus()
            self._set_status(tr("⚠  メールアドレスの形式が正しくありません。"), "warn")
            return

        message = self._msg_edit.toPlainText().strip()

        self._btn_send.setEnabled(False)
        self._btn_send.setText(tr("送信中..."))
        self._set_status("", "")

        # Sheets ベースの申請 — service_account.json (アプリ同梱) で書き込み.
        # SMTP / Google アカウント認証 不要 (旧 SMTP 経由は資格情報配布問題で廃止).
        self._worker = _SubmitAccessRequestWorker(email, message, f"v{__version__}")
        self._worker.success.connect(self._on_send_success)
        self._worker.error.connect(self._on_send_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _set_status(self, text: str, kind: str) -> None:
        """kind: 'warn' | 'ok' | 'err' | '' """
        colors = {"warn": "#FF9F0A", "ok": "#30D158", "err": "#FF453A"}
        color = colors.get(kind, "")
        if color:
            self._status_lbl.setStyleSheet(
                f"font-size: 11px; padding-top: 4px; color: {color}; background: transparent;"
            )
        else:
            self._status_lbl.setStyleSheet("font-size: 11px; padding-top: 4px; background: transparent;")
        self._status_lbl.setText(text)

    def _on_send_success(self, request_id: str = "") -> None:
        self._set_status(tr("✅  申請を登録しました。管理者の承認をお待ちください。"), "ok")
        self._btn_send.setText(tr("送信完了"))
        QTimer.singleShot(2000, self.accept)

    def _on_send_error(self, err: str) -> None:
        self._btn_send.setEnabled(True)
        self._btn_send.setText(tr("申請する"))
        self._set_status(f"❌  {tr('送信失敗:')} {err[:80]}", "err")


# ──────────────────────────────────────────────────────────────────────────
# LoginWindow — A+ Refined Dark
# ──────────────────────────────────────────────────────────────────────────
class LoginWindow(QMainWindow):
    """프레임리스 + 그라데이션 배경 + 3 페이지 스택."""

    login_success = Signal(str)

    def __init__(self):
        super().__init__()
        self._worker: _LoginWorker | None = None
        self._failed_email = ""
        self._drag_pos: QPoint | None = None

        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setFixedSize(_WIN_W, _WIN_H)
        self.setWindowTitle(f"LEE 電力モニター v{__version__}")

        self._setup_ui()
        self._apply_overrides()
        self._center()

    # ── PaintEvent: 배경 그라데이션 + 글로우 + 그리드 + vignette ─────────────
    # 정적 배경 (5 그라디언트 + grid) 은 QPixmap 으로 캐싱 → 매 paint 마다 재계산 X
    # 리사이즈 시에만 _bg_cache 재생성. 윈도우 드래그 / repaint 시 CPU 절감.
    def _build_bg_pixmap(self, size) -> QPixmap:
        """현재 size 에 맞는 정적 배경 QPixmap 을 생성."""
        w, h = size.width(), size.height()
        pm = QPixmap(size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        rect = pm.rect()

        # 1. Base radial (앵커: 우상단)
        base = QRadialGradient(w, 0, w * 1.4)
        base.setColorAt(0,    QColor("#2a1410"))
        base.setColorAt(0.35, QColor("#160c0a"))
        base.setColorAt(0.7,  QColor("#14161C"))
        p.fillRect(rect, QBrush(base))

        # 2. 우상단 오렌지 글로우 (FF7A45 18%)
        tr_glow = QRadialGradient(w, 0, w * 0.6)
        tr_glow.setColorAt(0, QColor(255, 122, 69, int(255 * 0.18)))
        tr_glow.setColorAt(1, QColor(255, 122, 69, 0))
        p.fillRect(rect, QBrush(tr_glow))

        # 3. 좌하단 큰 빛무리 (FF9F0A 22% → FF7A45 0%)
        bl_halo = QRadialGradient(0, h, w * 0.7)
        bl_halo.setColorAt(0,   QColor(255, 159, 10, int(255 * 0.22)))
        bl_halo.setColorAt(0.5, QColor(255, 122, 69, int(255 * 0.05)))
        bl_halo.setColorAt(1,   QColor(255, 122, 69, 0))
        p.fillRect(rect, QBrush(bl_halo))

        # 4. 미세 그리드 (white 4%)
        p.setPen(QPen(QColor(255, 255, 255, int(255 * 0.04)), 1))
        for x in range(0, w, 24):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, 24):
            p.drawLine(0, y, w, y)

        # 5. Vignette (black 25%, 코너)
        vig = QRadialGradient(w / 2, h / 2, w * 0.7)
        vig.setColorAt(0,   QColor(0, 0, 0, 0))
        vig.setColorAt(0.6, QColor(0, 0, 0, 0))
        vig.setColorAt(1,   QColor(0, 0, 0, int(255 * 0.25)))
        p.fillRect(rect, QBrush(vig))
        p.end()
        return pm

    def paintEvent(self, event):
        # 캐시 hit/miss
        size = self.size()
        cache_key = getattr(self, "_bg_cache_key", None)
        if cache_key != (size.width(), size.height()):
            self._bg_cache = self._build_bg_pixmap(size)
            self._bg_cache_key = (size.width(), size.height())
        p = QPainter(self)
        p.drawPixmap(0, 0, self._bg_cache)

    def resizeEvent(self, event):
        # 사이즈 변경 시 캐시 무효화 (다음 paintEvent 에서 재생성)
        self._bg_cache_key = None
        super().resizeEvent(event)

    # ── 드래그 이동 ────────────────────────────────────────────────────────
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos is not None and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    # ── UI 構築 ────────────────────────────────────────────────────────────
    def _setup_ui(self) -> None:
        central = QWidget()
        central.setObjectName("loginCentral")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # macOS 풍 28px 타이틀바
        root.addWidget(self._build_titlebar())

        # 컨텐츠 영역 (margin 적용)
        content = QWidget()
        content.setObjectName("loginContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 18, 28, 18)
        content_layout.setSpacing(0)
        root.addWidget(content, 1)
        root = content_layout  # 이후 부분은 content_layout 에 추가

        root.addWidget(self._build_header())

        self.stack = QStackedWidget()
        self.stack.setObjectName("loginStack")
        root.addWidget(self.stack, 1)

        self.stack.addWidget(self._build_login_page())          # 0
        self.stack.addWidget(self._build_not_registered_page()) # 1
        self.stack.addWidget(self._build_loading_page())        # 2

        root.addWidget(self._build_footer())

    # ── 타이틀바 (macOS traffic lights + 중앙 제목) ──
    def _build_titlebar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("loginTitleBar")
        bar.setFixedHeight(28)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(6)

        for color, action in (
            ("#FF5F57", "close"), ("#FEBC2E", None), ("#28C840", None),
        ):
            dot = QPushButton()
            dot.setObjectName("loginTrafficDot")
            dot.setProperty("dotColor", color)
            dot.setFixedSize(11, 11)
            if action == "close":
                dot.setCursor(Qt.PointingHandCursor)
                dot.clicked.connect(self.close)
            else:
                dot.setEnabled(False)   # 시각용 — 클릭/커서 비활성화
            layout.addWidget(dot)

        title_label = QLabel(f"LEE 電力モニター  v{__version__}")
        title_label.setObjectName("loginTitleBarText")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addStretch()
        layout.addWidget(title_label)
        layout.addStretch()
        # 우측 spacer (좌측 dot 3개 균형용)
        right_spacer = QFrame(); right_spacer.setFixedWidth(33)
        right_spacer.setObjectName("loginTitleSpacer")
        layout.addWidget(right_spacer)

        return bar

    # ── Brand Header (icon + title + subtitle) ──
    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("loginHeader")
        header.setFixedHeight(40)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 브랜드 아이콘 — 기존 앱 아이콘 (:/img/icon.png) 사용
        icon = QLabel()
        icon.setObjectName("brandIcon")
        icon.setFixedSize(32, 32)
        icon.setAlignment(Qt.AlignCenter)
        try:
            qicon = QApplication.instance().windowIcon()
            if not qicon.isNull():
                icon.setPixmap(qicon.pixmap(32, 32))
            else:
                icon.setText("⚡")
                icon.setStyleSheet("font-size: 22px; color: #FF7A45; background: transparent;")
        except Exception:
            icon.setText("⚡")
            icon.setStyleSheet("font-size: 22px; color: #FF7A45; background: transparent;")

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(0)
        title = QLabel("LEE 電力モニター")
        title.setObjectName("brandTitle")
        sub = QLabel(f"POWER MARKET INTEL · v{__version__}")
        sub.setObjectName("brandSub")
        f = sub.font()
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        sub.setFont(f)
        text_box.addWidget(title)
        text_box.addWidget(sub)

        layout.addWidget(icon, 0, Qt.AlignVCenter)
        layout.addLayout(text_box)
        layout.addStretch()
        return header

    # ── Page 0: Login ──
    def _build_login_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("loginPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 0, 8, 8)
        layout.setSpacing(0)
        layout.addStretch(2)

        secure = QLabel(tr("SECURE ACCESS"))
        secure.setObjectName("secureBadge")
        secure.setAlignment(Qt.AlignCenter)
        f = secure.font()
        f.setLetterSpacing(QFont.AbsoluteSpacing, 4)
        secure.setFont(f)

        welcome = QLabel(tr("ようこそ"))
        welcome.setObjectName("welcomeTitle")
        welcome.setAlignment(Qt.AlignCenter)

        sub = QLabel(tr("承認済みアカウントでサインイン"))
        sub.setObjectName("welcomeSub")
        sub.setAlignment(Qt.AlignCenter)

        self.btn_google = QPushButton(tr("  Google アカウントでサインイン"))
        self.btn_google.setObjectName("googleBtn")
        self.btn_google.setMinimumHeight(46)
        self.btn_google.setCursor(Qt.PointingHandCursor)
        self.btn_google.setIcon(_google_g_pixmap(18))
        from PySide6.QtCore import QSize
        self.btn_google.setIconSize(QSize(18, 18))
        self.btn_google.clicked.connect(self._start_login)

        self.lbl_error = QLabel()
        self.lbl_error.setObjectName("loginError")
        self.lbl_error.setAlignment(Qt.AlignCenter)
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()

        # "또는" 구분선
        or_row = QHBoxLayout()
        or_row.setSpacing(10)
        or_lbl = QLabel(tr("または"))
        or_lbl.setObjectName("loginOr")
        or_lbl.setAlignment(Qt.AlignCenter)
        or_row.addWidget(self._hline())
        or_row.addWidget(or_lbl)
        or_row.addWidget(self._hline())

        self.btn_request = QPushButton(tr("アクセスを申請する  →"))
        self.btn_request.setObjectName("requestLink")
        self.btn_request.setFlat(True)
        self.btn_request.setCursor(Qt.PointingHandCursor)
        self.btn_request.clicked.connect(lambda: self._open_request_dialog(""))

        layout.addWidget(secure)
        layout.addSpacing(20)
        layout.addWidget(welcome)
        layout.addSpacing(8)
        layout.addWidget(sub)
        layout.addSpacing(36)
        layout.addWidget(self.btn_google)
        layout.addSpacing(8)
        layout.addWidget(self.lbl_error)
        layout.addSpacing(28)
        layout.addLayout(or_row)
        layout.addSpacing(14)
        layout.addWidget(self.btn_request, 0, Qt.AlignCenter)
        layout.addStretch(3)
        return page

    # ── Page 1: Not Registered ──
    def _build_not_registered_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("loginPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 0, 8, 8)
        layout.setSpacing(0)
        layout.addStretch(2)

        # 디자인 정합: 72×72 amber tile + stroke 삼각형
        icon = _WarnTile(size=72)
        icon_row = QHBoxLayout()
        icon_row.addStretch(); icon_row.addWidget(icon); icon_row.addStretch()

        title = QLabel(tr("登録されていません"))
        title.setObjectName("welcomeTitle")
        title.setAlignment(Qt.AlignCenter)

        # 이메일 칩 (auto-width)
        self.lbl_nr_email = QLabel()
        self.lbl_nr_email.setObjectName("emailPill")
        self.lbl_nr_email.setAlignment(Qt.AlignCenter)
        self.lbl_nr_email.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        pill_row = QHBoxLayout()
        pill_row.addStretch()
        pill_row.addWidget(self.lbl_nr_email)
        pill_row.addStretch()

        desc = QLabel(tr(
            "このアカウントはアクセス権がありません。\n"
            "管理者にアクセスを申請してください。"
        ))
        desc.setObjectName("welcomeSub")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_back = LeeButton(tr("← 戻る"), variant="ghost", size="md")
        btn_back.clicked.connect(self.reset)
        btn_req = LeeButton(tr("アクセスを申請"), variant="primary", size="md")
        btn_req.clicked.connect(lambda: self._open_request_dialog(self._failed_email))
        btn_row.addWidget(btn_back)
        btn_row.addWidget(btn_req)

        layout.addLayout(icon_row)
        layout.addSpacing(14)
        layout.addWidget(title)
        layout.addSpacing(12)
        layout.addLayout(pill_row)
        layout.addSpacing(14)
        layout.addWidget(desc)
        layout.addSpacing(28)
        layout.addLayout(btn_row)
        layout.addStretch(3)
        return page

    # ── Page 2: Loading ──
    def _build_loading_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("loginPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 0, 8, 8)
        layout.setSpacing(0)
        layout.addStretch(2)

        self._spinner = LeeRingSpinner(size=64, color="#FF7A45")
        self._spinner.setObjectName("loginSpinner")

        lbl = QLabel(tr("認証中..."))
        lbl.setObjectName("welcomeTitle")
        lbl.setAlignment(Qt.AlignCenter)

        hint = QLabel(tr("ブラウザでサインインを完了してください"))
        hint.setObjectName("welcomeSub")
        hint.setAlignment(Qt.AlignCenter)

        hint2 = QLabel(tr("(ブラウザを閉じると 2 分後に自動キャンセルされます)"))
        hint2.setObjectName("loginHint")
        hint2.setAlignment(Qt.AlignCenter)

        btn_cancel = LeeButton(tr("キャンセル"), variant="secondary", size="md")
        btn_cancel.setFixedWidth(140)
        btn_cancel.clicked.connect(self._cancel_login)

        layout.addWidget(self._spinner, 0, Qt.AlignHCenter)
        layout.addSpacing(16)
        layout.addWidget(lbl)
        layout.addSpacing(8)
        layout.addWidget(hint)
        layout.addSpacing(2)
        layout.addWidget(hint2)
        layout.addSpacing(28)
        layout.addWidget(btn_cancel, 0, Qt.AlignCenter)
        layout.addStretch(3)
        return page

    # ── Footer (varA-login-window.jsx:775-786 정합 — copy LEFT, email RIGHT) ──
    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("loginFooter")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        copy = QLabel("© Shirokuma Power")
        copy.setObjectName("footerCopy")
        copy.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        email = QLabel("jw.lee@shirokumapower.com")
        email.setObjectName("footerEmail")
        email.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout.addWidget(copy, 1)
        layout.addWidget(email, 1)
        return footer

    # ── 헬퍼 ──────────────────────────────────────────────────────────────
    @staticmethod
    def _hline() -> QFrame:
        line = QFrame()
        line.setObjectName("loginSep")
        line.setFixedHeight(1)
        return line

    def _center(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - self.width())  // 2,
            (screen.height() - self.height()) // 2,
        )

    # ── 로직 ──────────────────────────────────────────────────────────────
    def _start_login(self) -> None:
        self.lbl_error.hide()
        self.stack.setCurrentIndex(_PAGE_LOADING)
        self._spinner.start()

        self._worker = _LoginWorker()
        self._worker.success.connect(self._on_success)
        self._worker.not_registered.connect(self._on_not_registered)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_success(self, email: str) -> None:
        logger.info(f"ログイン成功: {email}")
        self._spinner.stop()
        self._animate_out(email)

    def _on_not_registered(self, email: str) -> None:
        self._spinner.stop()
        self._failed_email = email
        self.lbl_nr_email.setText(email)
        self.stack.setCurrentIndex(_PAGE_NOT_REGISTERED)

    def _on_failed(self, msg: str) -> None:
        self._spinner.stop()
        self.stack.setCurrentIndex(_PAGE_LOGIN)
        self.lbl_error.setText(f"⚠  {msg}")
        self.lbl_error.show()

    def _cancel_login(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(800)
            self._worker = None
        self._spinner.stop()
        self.stack.setCurrentIndex(_PAGE_LOGIN)
        self.lbl_error.hide()

    def _open_request_dialog(self, prefill: str) -> None:
        dlg = _AccessRequestDialog(prefill_email=prefill, parent=self)
        dlg.exec()

    # ── 애니메이션 ────────────────────────────────────────────────────────
    def _animate_out(self, email: str) -> None:
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

    def show_animated(self) -> None:
        """下から浮かび上がりながらフェードイン。"""
        self.setWindowOpacity(0.0)
        self.show()

        end_rect = self.geometry()
        start_rect = QRect(end_rect.x(), end_rect.y() + 20, end_rect.width(), end_rect.height())
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

    def reset(self) -> None:
        """ログイン画面をリセットして先頭ページに戻す。"""
        self.setWindowOpacity(1.0)
        self._failed_email = ""
        self.lbl_error.hide()
        self.btn_google.setText(tr("  Google アカウントでサインイン"))
        self.btn_google.setEnabled(True)
        self._spinner.stop()
        self.stack.setCurrentIndex(_PAGE_LOGIN)

    def closeEvent(self, event):
        """ログイン画面を閉じたらアプリを終了する。
        hide() 時は呼ばれないため、メインウィンドウ移行後に誤って終了することはない。"""
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(500)
        self._spinner.stop()
        event.accept()
        QApplication.instance().quit()

    # ── 스타일 오버라이드 (paintEvent 그라데이션 노출 + 페이지 위젯 톤) ────
    def _apply_overrides(self) -> None:
        # 디자인 토큰 (TOKENS_DARK) 으로 hex 자동 동기화 — 토큰 변경 시 propagate
        from app.ui.theme import TOKENS_DARK as _T
        qss = ("""
        /* ── 배경 투명화 (QWidget 글로벌 dark bg 오버라이드) ── */
        QWidget#loginCentral,
        QWidget#loginContent,
        QWidget#loginPage,
        QWidget#loginHeader,
        QWidget#loginFooter,
        QStackedWidget#loginStack,
        QStackedWidget#loginStack > QWidget {
            background: transparent;
        }

        /* ── macOS 풍 28px 타이틀바 ── */
        QFrame#loginTitleBar {
            background: rgba(255,255,255,0.04);
            border-bottom: 1px solid rgba(255,255,255,0.06);
        }
        QFrame#loginTitleSpacer { background: transparent; }
        QPushButton#loginTrafficDot {
            border: none;
            border-radius: 5px;
        }
        QPushButton#loginTrafficDot[dotColor="#FF5F57"] { background: #FF5F57; }
        QPushButton#loginTrafficDot[dotColor="#FEBC2E"] { background: #FEBC2E; }
        QPushButton#loginTrafficDot[dotColor="#28C840"] { background: #28C840; }
        QLabel#loginTitleBarText {
            font-size: 11px;
            font-weight: 600;
            color: #6B7280;
            background: transparent;
        }

        /* ── Brand header ── */
        QLabel#brandIcon {
            background: transparent;
        }
        QLabel#brandTitle {
            font-size: 13px;
            font-weight: 800;
            color: #F2F4F7;
            background: transparent;
            letter-spacing: -0.01em;
        }
        QLabel#brandSub {
            font-family: "JetBrains Mono", "Consolas", monospace;
            font-size: 9px;
            font-weight: 600;
            color: #6B7280;
            background: transparent;
            letter-spacing: 0.08em;
        }

        /* ── 타이포 ── */
        QLabel#secureBadge {
            font-size: 10px;
            font-weight: 700;
            color: #FF7A45;
            background: transparent;
        }
        QLabel#welcomeTitle {
            font-size: 28px;
            font-weight: 700;
            color: #F2F4F7;
            background: transparent;
        }
        QLabel#welcomeSub {
            font-size: 13px;
            color: #A8B0BD;
            background: transparent;
        }
        QLabel#loginHint {
            font-size: 10px;
            color: #6B7280;
            background: transparent;
        }
        QFrame#loginWarnTile {
            background: rgba(255, 159, 10, 0.14);
            border: 1px solid rgba(255, 159, 10, 0.30);
            border-radius: 14px;
        }

        /* ── Email pill ── */
        QLabel#emailPill {
            font-family: "JetBrains Mono", "Consolas", monospace;
            font-size: 12px;
            font-weight: 600;
            color: #FF7A45;
            background: rgba(255,122,69,0.12);
            border: 1px solid rgba(255,122,69,0.25);
            border-radius: 999px;
            padding: 6px 14px;
        }

        /* ── Google 버튼 ── */
        QPushButton#googleBtn {
            background: rgba(255,255,255,0.06);
            color: #F2F4F7;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 10px;
            font-size: 14px;
            font-weight: 600;
            padding: 0 20px;
        }
        QPushButton#googleBtn:hover {
            background: rgba(255,255,255,0.10);
            border-color: rgba(255,122,69,0.40);
        }
        QPushButton#googleBtn:pressed {
            background: rgba(255,255,255,0.04);
        }
        QPushButton#googleBtn:disabled {
            color: rgba(255,255,255,0.30);
            border-color: rgba(255,255,255,0.05);
        }

        /* ── 申請 링크 ── */
        QPushButton#requestLink {
            background: transparent;
            color: #FF7A45;
            border: none;
            font-size: 12px;
            font-weight: 600;
            padding: 4px 8px;
        }
        QPushButton#requestLink:hover {
            color: #FF8A55;
        }

        /* ── 또는 구분선 ── */
        QFrame#loginSep {
            background: rgba(255,255,255,0.10);
            border: none;
            max-height: 1px;
        }
        QLabel#loginOr {
            font-size: 10px;
            font-weight: 600;
            color: #6B7280;
            background: transparent;
            min-width: 40px;
        }

        /* ── 에러 메시지 ── */
        QLabel#loginError {
            font-size: 11px;
            color: #FF453A;
            background: rgba(255,69,58,0.10);
            border: 1px solid rgba(255,69,58,0.25);
            border-radius: 6px;
            padding: 6px 12px;
        }

        /* ── Spinner (LeeRingSpinner widget — paintEvent 사용) ── */
        QWidget#loginSpinner { background: transparent; }

        /* ── Footer ── */
        QLabel#footerCopy {
            font-size: 10px;
            color: #6B7280;
            background: transparent;
        }
        QLabel#footerEmail {
            font-family: "JetBrains Mono", "Consolas", monospace;
            font-size: 10px;
            color: #4A5567;
            background: transparent;
        }

        /* ── _AccessRequestDialog 폼 라벨/상태 ── */
        QLabel#accessReqLabel {
            font-size: 11px;
            font-weight: 600;
            color: #A8B0BD;
            background: transparent;
            padding-top: 6px;
        }
        QLabel#accessReqStatus {
            background: transparent;
        }
        """
            .replace("#F2F4F7", _T["fg_primary"])
            .replace("#A8B0BD", _T["fg_secondary"])
            .replace("#6B7280", _T["fg_tertiary"])
            .replace("#FF7A45", _T["accent"])
            .replace("#FF453A", _T["c_bad"])
        )
        self.setStyleSheet(qss)
