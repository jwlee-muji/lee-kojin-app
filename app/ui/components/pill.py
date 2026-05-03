"""LeePill — 인라인 라벨 / 배지 (pill shape).

Usage:
    from app.ui.components import LeePill

    pill = LeePill("NEW", variant="accent")
    pill = LeePill("成功", variant="success")
    pill = LeePill("Beta", variant="subtle")
    pill = LeePill("ERROR", variant="danger")

    # 런타임 variant 변경
    pill.set_variant("danger")
"""
from __future__ import annotations
from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

PillVariant = Literal["subtle", "accent", "success", "danger", "info", "warn"]


class LeePill(QLabel):
    """필 형태 인라인 라벨 (radius 999, padding 4×10).

    Variants
    --------
    subtle    무채색 (서피스2 배경 + 보조 텍스트)
    accent    앱 액센트 (오렌지 12% bg + 액센트 글자)
    success   --c-ok (그린)
    danger    --c-bad (빨강)
    info      --c-power (파랑) 또는 --c-info — 임계 "通常" / 정보 표시
    warn      --c-warn (주황/노랑) — 임계 "注意" / 경고 표시
    """

    def __init__(self, text: str = "", *, variant: PillVariant = "subtle", parent=None):
        super().__init__(text, parent)
        self.setObjectName("leePill")
        self.setProperty("variant", variant)
        self.setAlignment(Qt.AlignCenter)

    def set_variant(self, variant: PillVariant) -> None:
        self.setProperty("variant", variant)
        self.style().unpolish(self)
        self.style().polish(self)


_QSS = """
QLabel#leePill {{
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    qproperty-alignment: AlignCenter;
}}
QLabel#leePill[variant="subtle"]  {{ background: {bg_surface_2}; color: {fg_secondary}; }}
QLabel#leePill[variant="accent"]  {{ background: rgba(255,122,69,0.15); color: {accent}; }}
QLabel#leePill[variant="success"] {{ background: rgba(48,209,88,0.15);  color: {c_ok}; }}
QLabel#leePill[variant="danger"]  {{ background: rgba(255,69,58,0.15);  color: {c_bad}; }}
QLabel#leePill[variant="info"]    {{ background: rgba(91,141,239,0.15); color: {c_power}; }}
QLabel#leePill[variant="warn"]    {{ background: rgba(255,159,10,0.15); color: {c_warn}; }}
"""


def qss(tokens: dict) -> str:
    """tokens 를 QSS 템플릿에 .format() 해서 반환."""
    return _QSS.format(**tokens)
