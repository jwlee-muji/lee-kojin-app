"""LeeDialog — 커스텀 다이얼로그 베이스 (QMessageBox 대체).

Usage:
    from app.ui.components import LeeDialog

    # Confirm (bool 반환)
    if LeeDialog.confirm("削除確認", "本当に削除しますか?",
                          ok_text="削除", destructive=True, parent=self):
        self._do_delete()

    # Info / Warning / Error (반환값 없음)
    LeeDialog.info("完了", "保存しました", parent=self)
    LeeDialog.warning("注意", "変更が保存されていません", parent=self)
    LeeDialog.error("エラー", "処理に失敗しました",
                     details=str(exc), parent=self)

    # 직접 인스턴스화 + 커스텀 버튼
    dlg = LeeDialog("確認", kind="question", parent=self)
    dlg.set_message("本当に実行しますか?")
    dlg.add_button("キャンセル", "secondary", role="reject")
    dlg.add_button("実行", "primary", role="accept")
    if dlg.exec() == QDialog.Accepted:
        ...

Frameless + 커스텀 타이틀바 (드래그 이동 지원).
ESC 키로 reject, Enter 로 default 버튼 (accept) 활성화.
"""
from __future__ import annotations
from typing import Literal, Optional

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QMouseEvent, QColor
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QGraphicsDropShadowEffect, QSizePolicy,
)

from .button import LeeButton, ButtonVariant

DialogKind = Literal["info", "warning", "error", "success", "question", "update"]
ButtonRole = Literal["accept", "reject"]

_KIND_GLYPH = {
    "info":     "i",
    "warning":  "!",
    "error":    "✕",
    "success":  "✓",
    "question": "?",
    "update":   "↑",
}


class LeeDialog(QDialog):
    """커스텀 다이얼로그 베이스. QMessageBox 의 디자인 시스템 대체.

    프레임 구성:
        ┌─────────────────────────────┐
        │ ── 타이틀바 (32px, 드래그) ──│
        ├─────────────────────────────┤
        │  [ICON]  메시지              │
        │   56px   (선택) details      │
        ├─────────────────────────────┤
        │ ── 푸터 ──────── [버튼들] ──│
        └─────────────────────────────┘

    Parameters
    ----------
    title : str
        타이틀바에 표시할 제목.
    kind : {"info", "warning", "error", "success", "question"}
        아이콘 컬러/글리프를 결정.
    parent : QWidget or None
        부모 윈도우 (있으면 자동으로 중앙 정렬).
    """

    def __init__(self, title: str, kind: DialogKind = "info", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)

        self._kind = kind
        self._drag_pos: Optional[QPoint] = None
        self._setup_ui(title)

    def _setup_ui(self, title: str) -> None:
        # 외곽 (드롭섀도 표시 영역 확보용 마진)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(0)

        # 메인 프레임
        self._frame = QFrame()
        self._frame.setObjectName("leeDialogFrame")
        outer.addWidget(self._frame)

        shadow = QGraphicsDropShadowEffect(self._frame)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 140))
        self._frame.setGraphicsEffect(shadow)

        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        # ── 타이틀바 (macOS traffic lights + 중앙 제목) ──────────
        self._titlebar = QFrame()
        self._titlebar.setObjectName("leeDialogTitleBar")
        self._titlebar.setFixedHeight(32)
        title_layout = QHBoxLayout(self._titlebar)
        title_layout.setContentsMargins(12, 0, 12, 0)
        title_layout.setSpacing(8)

        # 좌측 traffic lights 3개 (레드만 클릭 시 닫기, 나머지는 시각용)
        for color, action in (
            ("#FF5F57", "close"), ("#FEBC2E", None), ("#28C840", None),
        ):
            dot = QPushButton()
            dot.setObjectName("leeDialogTrafficDot")
            dot.setProperty("dotColor", color)
            dot.setFixedSize(11, 11)
            if action == "close":
                dot.setCursor(Qt.PointingHandCursor)
                dot.clicked.connect(self.reject)
            else:
                dot.setEnabled(False)
            title_layout.addWidget(dot)

        title_label = QLabel(title)
        title_label.setObjectName("leeDialogTitle")
        title_label.setAlignment(Qt.AlignCenter)
        title_layout.addStretch()
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        # 우측 spacer (좌측 dot 3개 + 8px 간격 ≈ 41px → 균형용)
        right_spacer = QFrame(); right_spacer.setFixedWidth(33)
        right_spacer.setObjectName("leeDialogTitleSpacer")
        title_layout.addWidget(right_spacer)

        frame_layout.addWidget(self._titlebar)

        # ── 본문 (icon + text) ────────────────────────────────
        body = QFrame()
        body.setObjectName("leeDialogBody")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(24, 24, 24, 24)
        body_layout.setSpacing(20)
        body_layout.setAlignment(Qt.AlignTop)

        self._icon = QLabel(_KIND_GLYPH.get(self._kind, "i"))
        self._icon.setObjectName("leeDialogIcon")
        self._icon.setProperty("kind", self._kind)
        self._icon.setFixedSize(56, 56)
        self._icon.setAlignment(Qt.AlignCenter)
        body_layout.addWidget(self._icon, 0, Qt.AlignTop)

        self._msg_layout = QVBoxLayout()
        self._msg_layout.setSpacing(8)
        self._message = QLabel("")
        self._message.setObjectName("leeDialogMessage")
        self._message.setWordWrap(True)
        self._message.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._msg_layout.addWidget(self._message)

        self._details = QLabel("")
        self._details.setObjectName("leeDialogDetails")
        self._details.setWordWrap(True)
        self._msg_layout.addWidget(self._details)
        self._details.setVisible(False)   # setVisible 은 layout 추가 후
        self._msg_layout.addStretch()
        body_layout.addLayout(self._msg_layout, 1)

        self._body = body
        frame_layout.addWidget(body, 1)

        # ── 푸터 (버튼 영역) ──────────────────────────────────
        self._footer = QFrame()
        self._footer.setObjectName("leeDialogFooter")
        self._footer.setFixedHeight(64)
        self._footer_layout = QHBoxLayout(self._footer)
        self._footer_layout.setContentsMargins(24, 16, 24, 16)
        self._footer_layout.setSpacing(8)
        self._footer_layout.addStretch()

        frame_layout.addWidget(self._footer)

        self.setMinimumWidth(440)

    # ── 콘텐츠 설정 ────────────────────────────────────────────
    def set_message(self, message: str, *, details: str = "") -> None:
        """본문 메시지 (필수) + details (선택, 모노스페이스 캡션) 설정."""
        self._message.setText(message)
        if details:
            self._details.setText(details)
            self._details.setVisible(True)
        else:
            self._details.setVisible(False)

    def add_button(
        self,
        text: str,
        variant: ButtonVariant = "secondary",
        *,
        role: ButtonRole = "accept",
    ) -> LeeButton:
        """푸터에 버튼 추가. role 에 따라 accept/reject signal 연결."""
        btn = LeeButton(text, variant=variant, size="md")
        if role == "accept":
            btn.clicked.connect(self.accept)
            btn.setDefault(True)
        else:
            btn.clicked.connect(self.reject)
        self._footer_layout.addWidget(btn)
        return btn

    def add_body_widget(self, widget) -> None:
        """본문 메시지 영역(아이콘 우측)에 위젯 추가.

        message/details 와 stretch 사이에 삽입되므로,
        메시지 아래에 추가 위젯(예: 버전 카드, 프로그레스 바)을 배치할 수 있다.
        """
        count = self._msg_layout.count()
        self._msg_layout.insertWidget(count - 1, widget)

    def add_footer_spacer(self) -> None:
        """이미 추가된 버튼들을 좌측 그룹으로 두고, 이후 add_button 은 우측 그룹.

        사용:
            dlg.add_button("キャンセル", "ghost", role="reject")  # 좌측
            dlg.add_footer_spacer()                                 # 좌-우 분리
            dlg.add_button("トレイに最小化", "secondary")           # 우측
            dlg.add_button("完全に終了", "destructive")             # 우측 끝
        """
        # 처음에 자동 추가된 stretch 가 있으면 제거 (좌측 정렬 위해)
        if self._footer_layout.count() > 0:
            first_item = self._footer_layout.itemAt(0)
            if first_item is not None and first_item.spacerItem() is not None:
                self._footer_layout.takeAt(0)
        # 끝에 새 stretch 추가 → 이후 add_button 은 우측에 정렬
        self._footer_layout.addStretch(1)

    def set_compact_body(self, widget) -> None:
        """본문 영역 전체를 위젯 하나로 교체 (icon/message/details 모두 숨김).

        Custom 다이얼로그용 — message 박스가 아니라 임의의 콘텐츠 (예: form,
        stacked widget, 상세 보기 등) 를 표시할 때 사용.
        """
        self._icon.setVisible(False)
        self._message.setVisible(False)
        self._details.setVisible(False)
        body_layout = self._body.layout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(widget)

    def set_footer_visible(self, visible: bool) -> None:
        """푸터(버튼 영역)의 표시 여부 설정. 버튼 없는 다이얼로그용."""
        self._footer.setVisible(visible)
        if not visible:
            self._footer.setFixedHeight(0)

    # ── 드래그 이동 (커스텀 타이틀바) ────────────────────────────
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            global_pos = event.globalPosition().toPoint()
            local = self._titlebar.mapFromGlobal(global_pos)
            if self._titlebar.rect().contains(local):
                self._drag_pos = global_pos - self.frameGeometry().topLeft()
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

    # ── Burst 보호 가드 ────────────────────────────────────────
    # 자동 fetch error 등에서 다이얼로그가 burst 로 호출되어
    # 모달 캐스케이드 (수십개가 연속으로 떴다 사라짐) 가 발생하던 문제 차단.
    #
    # 핵심: count 증가를 dialog 생성 BEFORE 에 함 (race condition 차단).
    # dialog 생성 자체가 Qt event loop 를 spin 시켜 다른 시그널을 처리할 수 있어,
    # count 증가가 늦으면 이중 dialog 생성 가능.
    _active_modal_count: int = 0
    _last_msg_signature: tuple = ("", 0.0)
    _burst_dedupe_seconds: float = 3.0   # 3초 내 동일 메시지 무시 (보수적)

    @classmethod
    def _allow_modal(cls, signature: str) -> bool:
        import time as _time
        now = _time.monotonic()
        last_sig, last_t = cls._last_msg_signature
        if cls._active_modal_count > 0:
            return False
        if signature == last_sig and (now - last_t) < cls._burst_dedupe_seconds:
            return False
        cls._last_msg_signature = (signature, now)
        return True

    @classmethod
    def _build_and_exec(cls, kind: DialogKind, title: str, message: str,
                        buttons: list, parent, details: str = "") -> int:
        """count 를 즉시 증가시킨 후 dialog 생성 + exec.

        Race condition 방지: dialog 의 부모 widget 생성 / set_message / add_button 이
        Qt event loop 를 spin 시켜 그동안 다른 LeeDialog 시도가 들어와도 차단되도록.
        """
        cls._active_modal_count += 1
        try:
            dlg = cls(title, kind, parent)
            if details:
                dlg.set_message(message, details=details)
            else:
                dlg.set_message(message)
            for label, variant, role in buttons:
                dlg.add_button(label, variant, role=role)
            return dlg.exec()
        finally:
            cls._active_modal_count -= 1

    # ── 편의 classmethods ──────────────────────────────────────
    @classmethod
    def confirm(
        cls,
        title: str,
        message: str,
        *,
        kind: DialogKind = "question",
        ok_text: str = "OK",
        cancel_text: str = "キャンセル",
        destructive: bool = False,
        parent=None,
    ) -> bool:
        """Yes/No 확인 다이얼로그. confirm 은 burst 가드 X (사용자 응답 필요)."""
        ok_variant = "destructive" if destructive else "primary"
        result = cls._build_and_exec(
            kind, title, message,
            [(cancel_text, "secondary", "reject"),
             (ok_text, ok_variant, "accept")],
            parent,
        )
        return result == QDialog.Accepted

    @classmethod
    def info(cls, title: str, message: str, *, parent=None) -> None:
        if not cls._allow_modal(f"info|{title}|{message}"):
            return
        cls._build_and_exec("info", title, message,
                            [("OK", "primary", "accept")], parent)

    @classmethod
    def warning(cls, title: str, message: str, *, parent=None) -> None:
        if not cls._allow_modal(f"warning|{title}|{message}"):
            return
        cls._build_and_exec("warning", title, message,
                            [("OK", "primary", "accept")], parent)

    @classmethod
    def error(cls, title: str, message: str, *, details: str = "", parent=None) -> None:
        if not cls._allow_modal(f"error|{title}|{message}|{details}"):
            return
        cls._build_and_exec("error", title, message,
                            [("閉じる", "secondary", "reject")],
                            parent, details=details)


_QSS = """
/* ── Frame (메인 컨테이너) ─────────────────────────────────── */
QFrame#leeDialogFrame {{
    background: {bg_surface};
    border-radius: 12px;
    border: 1px solid {border_subtle};
}}

/* ── 타이틀바 (macOS traffic lights) ───────────────────────── */
QFrame#leeDialogTitleBar {{
    background: {bg_surface_2};
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
    border-bottom: 1px solid {border_subtle};
}}
QFrame#leeDialogTitleSpacer {{ background: transparent; }}
QPushButton#leeDialogTrafficDot {{
    border: none;
    border-radius: 5px;
}}
QPushButton#leeDialogTrafficDot[dotColor="#FF5F57"] {{ background: #FF5F57; }}
QPushButton#leeDialogTrafficDot[dotColor="#FEBC2E"] {{ background: #FEBC2E; }}
QPushButton#leeDialogTrafficDot[dotColor="#28C840"] {{ background: #28C840; }}
QLabel#leeDialogTitle {{
    font-size: 11px;
    font-weight: 600;
    color: {fg_tertiary};
    background: transparent;
}}

/* ── 본문 ─────────────────────────────────────────────────── */
QFrame#leeDialogBody {{
    background: {bg_surface};
}}
QLabel#leeDialogMessage {{
    color: {fg_primary};
    font-size: 14px;
    background: transparent;
}}
QLabel#leeDialogDetails {{
    color: {fg_tertiary};
    font-size: 11px;
    font-family: "JetBrains Mono", "Consolas", monospace;
    background: transparent;
}}

/* ── 아이콘 (56px 사각형 라운드 + 글리프 + 보더) ──────────── */
QLabel#leeDialogIcon {{
    border-radius: 16px;
    font-size: 28px;
    font-weight: 800;
    font-family: "JetBrains Mono", "Consolas", monospace;
    qproperty-alignment: AlignCenter;
}}
QLabel#leeDialogIcon[kind="info"] {{
    background: rgba(44,123,229,0.16);
    border: 1px solid rgba(44,123,229,0.30);
    color: #2C7BE5;
}}
QLabel#leeDialogIcon[kind="warning"] {{
    background: rgba(255,159,10,0.16);
    border: 1px solid rgba(255,159,10,0.30);
    color: {c_warn};
}}
QLabel#leeDialogIcon[kind="error"] {{
    background: rgba(255,69,58,0.16);
    border: 1px solid rgba(255,69,58,0.30);
    color: {c_bad};
}}
QLabel#leeDialogIcon[kind="success"] {{
    background: rgba(48,209,88,0.16);
    border: 1px solid rgba(48,209,88,0.30);
    color: {c_ok};
}}
QLabel#leeDialogIcon[kind="question"] {{
    background: rgba(255,122,69,0.16);
    border: 1px solid rgba(255,122,69,0.30);
    color: {accent};
}}
QLabel#leeDialogIcon[kind="update"] {{
    background: rgba(255,122,69,0.16);
    border: 1px solid rgba(255,122,69,0.30);
    color: {accent};
}}

/* ── 푸터 ─────────────────────────────────────────────────── */
QFrame#leeDialogFooter {{
    background: {bg_surface_2};
    border-bottom-left-radius: 12px;
    border-bottom-right-radius: 12px;
    border-top: 1px solid {border_subtle};
}}
"""


def qss(tokens: dict) -> str:
    """tokens 를 QSS 템플릿에 .format() 해서 반환."""
    return _QSS.format(**tokens)
