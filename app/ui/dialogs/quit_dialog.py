"""QuitConfirmDialog — 終了の確認 (3 버튼) 다이얼로그.

main_window.closeEvent 에서 사용. 3가지 선택:
    - トレイに最小化  (default, primary)
    - 完全に終了      (destructive)
    - キャンセル      (ghost)

Usage:
    dlg = QuitConfirmDialog(parent=self)
    dlg.exec()
    if dlg.choice == QuitConfirmDialog.Quit:
        ...
    elif dlg.choice == QuitConfirmDialog.Tray:
        ...
    else:  # Cancel
        ...
"""
from __future__ import annotations
from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

from app.ui.components.button import LeeButton
from app.ui.components.dialog import LeeDialog
from app.core.i18n import tr

QuitChoice = Literal["tray", "quit", "cancel"]


class QuitConfirmDialog(LeeDialog):
    """終了確認 다이얼로그 (3 버튼).

    Attributes
    ----------
    choice : str
        exec() 종료 후 선택된 버튼: "tray" | "quit" | "cancel".
        ESC 또는 닫기로 종료 시 "cancel".
    """

    Tray = "tray"
    Quit = "quit"
    Cancel = "cancel"

    def __init__(self, parent=None):
        super().__init__(tr("終了の確認"), "question", parent)
        self.set_message(tr("アプリケーションを完全に終了しますか？"))
        self._choice: QuitChoice = self.Cancel
        self.setMinimumWidth(500)

        # 추가 안내 텍스트 (디자인의 작은 부가 설명 부분)
        sub_label = QLabel(tr("それともトレイ(バックグラウンド)に最小化しますか？"))
        sub_label.setObjectName("quitDialogSub")
        sub_label.setWordWrap(True)
        sub_label.setStyleSheet(
            "QLabel#quitDialogSub { font-size: 12px; color: #A8B0BD; "
            "background: transparent; padding-top: 4px; }"
        )
        self.add_body_widget(sub_label)

        # ⓘ 정보 박스 (트레이 동작 안내) — 디자인 모킹업의 핵심 요소
        info_box = self._build_info_box(tr(
            "トレイに最小化すれば、バックグラウンドで自動更新・通知を継続できます。"
        ))
        self.add_body_widget(info_box)

        # 푸터 — 좌: cancel (ghost) | 우: tray + quit
        cancel_btn = LeeButton(tr("キャンセル"), variant="ghost", size="md")
        cancel_btn.clicked.connect(lambda: self._set_choice_and_close(self.Cancel))
        self._footer_layout.addWidget(cancel_btn)

        # 좌-우 분리 spacer
        self.add_footer_spacer()

        tray_btn = LeeButton(tr("トレイに最小化"), variant="secondary", size="md")
        tray_btn.clicked.connect(lambda: self._set_choice_and_close(self.Tray))
        self._footer_layout.addWidget(tray_btn)

        quit_btn = LeeButton(tr("完全に終了"), variant="destructive", size="md")
        quit_btn.clicked.connect(lambda: self._set_choice_and_close(self.Quit))
        # tray 가 기본 액션 (트레이 권장)
        tray_btn.setDefault(True)
        self._footer_layout.addWidget(quit_btn)

    @staticmethod
    def _build_info_box(text: str) -> QFrame:
        """ⓘ accent 정보 박스 (디자인 모킹업 그대로)."""
        box = QFrame()
        box.setObjectName("quitInfoBox")
        h = QHBoxLayout(box)
        h.setContentsMargins(12, 10, 12, 10)
        h.setSpacing(8)
        h.setAlignment(Qt.AlignTop)

        icon = QLabel("ⓘ")
        icon.setObjectName("quitInfoIcon")
        icon.setFixedWidth(16)
        icon.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        h.addWidget(icon)

        msg = QLabel(text)
        msg.setObjectName("quitInfoText")
        msg.setWordWrap(True)
        h.addWidget(msg, 1)

        box.setStyleSheet("""
            QFrame#quitInfoBox {
                background: rgba(255,122,69,0.08);
                border: 1px solid rgba(255,122,69,0.20);
                border-radius: 8px;
            }
            QLabel#quitInfoIcon {
                color: #FF7A45;
                font-size: 14px;
                font-weight: 700;
                background: transparent;
            }
            QLabel#quitInfoText {
                color: #A8B0BD;
                font-size: 11px;
                background: transparent;
            }
        """)
        return box

    def _set_choice_and_close(self, choice: QuitChoice) -> None:
        self._choice = choice
        self.accept()

    @property
    def choice(self) -> QuitChoice:
        return self._choice

    def reject(self) -> None:
        # ESC / 외부 닫기 → cancel
        self._choice = self.Cancel
        super().reject()
