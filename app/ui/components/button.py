"""LeeButton — 디자인 시스템 표준 버튼.

Variants × Sizes 매트릭스:

    variant ∈ {primary, secondary, destructive, ghost}
    size    ∈ {sm, md, lg}

Usage:
    from app.ui.components import LeeButton

    btn = LeeButton("保存", variant="primary", size="md")
    btn.clicked.connect(self._on_save)

    # 런타임 variant 변경
    btn.set_variant("destructive")

State 처리 (Qt QSS pseudo-state로 자동):
    :hover, :pressed, :disabled, :focus
"""
from __future__ import annotations
from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

ButtonVariant = Literal["primary", "secondary", "destructive", "ghost"]
ButtonSize = Literal["sm", "md", "lg"]


class LeeButton(QPushButton):
    """디자인 시스템 표준 버튼.

    Parameters
    ----------
    text : str
        버튼 라벨.
    variant : {"primary", "secondary", "destructive", "ghost"}
        primary     주요 액션 (액센트 컬러 배경 + 흰 글자)
        secondary   부수 액션 (서피스 배경 + 보더)
        destructive 삭제/위험 액션 (빨강 배경)
        ghost       취소/부정 (투명, 텍스트만)
    size : {"sm", "md", "lg"}
        sm  height 28, font 11/700, padding-x 12
        md  height 36, font 12/700, padding-x 18  (기본)
        lg  height 44, font 14/700, padding-x 22
    """

    def __init__(
        self,
        text: str = "",
        *,
        variant: ButtonVariant = "secondary",
        size: ButtonSize = "md",
        parent=None,
    ):
        super().__init__(text, parent)
        self.setProperty("variant", variant)
        self.setProperty("btnSize", size)
        self.setCursor(Qt.PointingHandCursor)

    def set_variant(self, variant: ButtonVariant) -> None:
        """런타임에 variant를 변경하고 즉시 스타일 재적용."""
        self.setProperty("variant", variant)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_size(self, size: ButtonSize) -> None:
        """런타임에 size를 변경하고 즉시 스타일 재적용."""
        self.setProperty("btnSize", size)
        self.style().unpolish(self)
        self.style().polish(self)


_QSS = """
/* ── Variants ──────────────────────────────────────────────── */
QPushButton[variant="primary"] {{
    background: {accent};
    color: {fg_on_accent};
    border: 1px solid rgba(255,122,69,0.6);
    font-weight: 700;
}}
QPushButton[variant="primary"]:hover    {{ background: #FF8A55; }}
QPushButton[variant="primary"]:pressed  {{ background: #E66C3D; }}
QPushButton[variant="primary"]:disabled {{
    background: rgba(255,122,69,0.4);
    color: rgba(255,255,255,0.4);
    border-color: rgba(255,122,69,0.3);
}}

QPushButton[variant="secondary"] {{
    background: {bg_surface};
    color: {fg_primary};
    border: 1px solid {border};
    font-weight: 600;
}}
QPushButton[variant="secondary"]:hover    {{ background: {bg_surface_2}; }}
QPushButton[variant="secondary"]:pressed  {{ background: {bg_surface_3}; }}
QPushButton[variant="secondary"]:disabled {{
    color: {fg_quaternary};
    border-color: {border_subtle};
}}

QPushButton[variant="destructive"] {{
    background: {c_bad};
    color: {fg_on_accent};
    border: 1px solid {c_bad};
    font-weight: 700;
}}
QPushButton[variant="destructive"]:hover    {{ background: #FF564B; }}
QPushButton[variant="destructive"]:pressed  {{ background: #E63A30; }}
QPushButton[variant="destructive"]:disabled {{
    background: rgba(255,69,58,0.4);
    color: rgba(255,255,255,0.4);
    border-color: rgba(255,69,58,0.3);
}}

QPushButton[variant="ghost"] {{
    background: transparent;
    color: {fg_secondary};
    border: 1px solid transparent;
    font-weight: 600;
}}
QPushButton[variant="ghost"]:hover    {{ color: {fg_primary}; background: {bg_surface_2}; }}
QPushButton[variant="ghost"]:pressed  {{ background: {bg_surface_3}; }}
QPushButton[variant="ghost"]:disabled {{ color: {fg_quaternary}; }}

/* ── Sizes ─────────────────────────────────────────────────── */
QPushButton[btnSize="sm"] {{ min-height: 28px; padding: 0 12px; font-size: 11px; border-radius: 6px; }}
QPushButton[btnSize="md"] {{ min-height: 36px; padding: 0 18px; font-size: 12px; border-radius: 8px; }}
QPushButton[btnSize="lg"] {{ min-height: 44px; padding: 0 22px; font-size: 14px; border-radius: 10px; }}
"""


def qss(tokens: dict) -> str:
    """tokens 를 QSS 템플릿에 .format() 해서 반환."""
    return _QSS.format(**tokens)
