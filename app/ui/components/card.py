"""LeeCard — 라운드 카드 컨테이너 (좌측 액센트 바 + 드롭섀도).

Usage:
    from app.ui.components import LeeCard
    from PySide6.QtWidgets import QVBoxLayout, QLabel

    # 단순 카드
    card = LeeCard()
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 24, 20, 24)
    layout.addWidget(QLabel("내용"))

    # 액센트 바 + 인터랙티브 (호버 효과)
    spot_card = LeeCard(accent_color="spot", interactive=True)

    # 사용 가능한 accent_color (지표 토큰 11종)
    # power | spot | imb | jkm | weather | hjks | cal | mail | ai | memo | notice
"""
from __future__ import annotations
from typing import Literal, Optional

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect

AccentColor = Literal[
    "power", "spot", "imb", "jkm", "weather",
    "hjks", "cal", "mail", "ai", "memo", "notice",
]

# 디자인 명세: hover 시 shadow → md, translateY(-1px), 120ms
# Qt 에서 transform 미지원 → drop shadow blur/offset/alpha 변화로 lift 효과 모방
_REST_BLUR    = 24
_REST_OFFSETY = 4
_REST_ALPHA   = 60
_HOVER_BLUR   = 36
_HOVER_OFFSETY= 8
_HOVER_ALPHA  = 110
_HOVER_DUR_MS = 120   # design spec: 02-components.md hover lift 120ms


class LeeCard(QFrame):
    """카드 컨테이너 (radius 20, border subtle, drop shadow).

    Parameters
    ----------
    accent_color : str or None
        지표 컬러 토큰 키 (예: "power", "spot", "imb"). None 이면 액센트 바 없음.
    interactive : bool
        True 일 때 hover 효과 (shadow lift + 포인터 커서).
    parent : QWidget or None
    """

    def __init__(
        self,
        accent_color: Optional[AccentColor] = None,
        interactive: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("leeCard")
        self._interactive = interactive
        self.setProperty("interactive", "true" if interactive else "false")
        if accent_color:
            self.setProperty("accent", accent_color)
        if interactive:
            self.setCursor(Qt.PointingHandCursor)
            # P1-18 — 키보드 Tab 네비게이션 지원
            self.setFocusPolicy(Qt.StrongFocus)

        # QSS box-shadow 미지원 → QGraphicsDropShadowEffect
        self._shadow: Optional[QGraphicsDropShadowEffect] = None
        self._hover_anim: Optional[QParallelAnimationGroup] = None
        self._install_shadow()

    # ── 호버 lift (interactive 카드 전용) ─────────────────────
    def enterEvent(self, event):
        if self._interactive:
            self._animate_shadow(_HOVER_BLUR, _HOVER_OFFSETY, _HOVER_ALPHA)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._interactive:
            self._animate_shadow(_REST_BLUR, _REST_OFFSETY, _REST_ALPHA)
        super().leaveEvent(event)

    # ── shadow lifecycle (Qt 가 setGraphicsEffect 교체 시 C++ 객체 자동 삭제) ─
    def _install_shadow(self) -> None:
        """drop shadow effect 를 새로 생성/할당. self._shadow 가 dangling 이거나
        다른 effect 로 교체된 경우 복원하는 데 사용."""
        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(_REST_BLUR)
        sh.setOffset(0, _REST_OFFSETY)
        sh.setColor(QColor(0, 0, 0, _REST_ALPHA))
        self.setGraphicsEffect(sh)
        self._shadow = sh

    def _ensure_shadow_valid(self) -> bool:
        """self._shadow 가 살아있는지 확인. dead 면 재생성. valid 면 True."""
        eff = self.graphicsEffect()
        if eff is None or eff is not self._shadow:
            # 외부에서 setGraphicsEffect(...) 로 교체되었거나 None 처리됨
            # → shadow 가 다른 effect 의 lifetime 에 종속되었으므로 재생성 시 충돌 위험
            # 다른 effect (예: opacity fade-in) 가 활성 중이면 hover 비활성
            return False
        try:
            _ = self._shadow.blurRadius()   # C++ 객체 살아있는지 빠른 체크
            return True
        except RuntimeError:
            # dangling — 새로 설치
            self._shadow = None
            self._install_shadow()
            return True

    def _animate_shadow(self, blur: int, offset_y: int, alpha: int) -> None:
        if not self._ensure_shadow_valid():
            return   # 외부 effect 가 활성 중 — hover anim 스킵 (다음 leaveEvent 까지)
        if self._hover_anim is not None:
            try: self._hover_anim.stop()
            except RuntimeError: pass
        grp = QParallelAnimationGroup(self)
        a_blur = QPropertyAnimation(self._shadow, b"blurRadius", self)
        a_blur.setDuration(_HOVER_DUR_MS)
        a_blur.setEasingCurve(QEasingCurve.OutCubic)
        a_blur.setEndValue(float(blur))
        grp.addAnimation(a_blur)
        a_off = QPropertyAnimation(self._shadow, b"yOffset", self)
        a_off.setDuration(_HOVER_DUR_MS)
        a_off.setEasingCurve(QEasingCurve.OutCubic)
        a_off.setEndValue(float(offset_y))
        grp.addAnimation(a_off)
        # alpha 는 즉시 set (color 프로퍼티는 애니메이션 어색)
        c = QColor(self._shadow.color()); c.setAlpha(alpha)
        self._shadow.setColor(c)
        grp.start()
        self._hover_anim = grp


_QSS = """
QFrame#leeCard {{
    background: {bg_surface};
    border: 1px solid {border_subtle};
    border-radius: 20px;
}}
QFrame#leeCard[interactive="true"]:hover {{
    border-color: {border};
}}
/* P1-18 — 키보드 포커스 시 accent 색 outline (스크린리더/Tab 네비게이션) */
QFrame#leeCard[interactive="true"]:focus {{
    border: 2px solid {accent};
    outline: none;
}}

/* 좌측 4px 인디케이터 액센트 바 */
QFrame#leeCard[accent="power"]   {{ border-left: 4px solid {c_power}; }}
QFrame#leeCard[accent="spot"]    {{ border-left: 4px solid {c_spot}; }}
QFrame#leeCard[accent="imb"]     {{ border-left: 4px solid {c_imb}; }}
QFrame#leeCard[accent="jkm"]     {{ border-left: 4px solid {c_jkm}; }}
QFrame#leeCard[accent="weather"] {{ border-left: 4px solid {c_weather}; }}
QFrame#leeCard[accent="hjks"]    {{ border-left: 4px solid {c_hjks}; }}
QFrame#leeCard[accent="cal"]     {{ border-left: 4px solid {c_cal}; }}
QFrame#leeCard[accent="mail"]    {{ border-left: 4px solid {c_mail}; }}
QFrame#leeCard[accent="ai"]      {{ border-left: 4px solid {c_ai}; }}
QFrame#leeCard[accent="memo"]    {{ border-left: 4px solid {c_memo}; }}
QFrame#leeCard[accent="notice"]  {{ border-left: 4px solid {c_notice}; }}
"""


def qss(tokens: dict) -> str:
    """tokens 를 QSS 템플릿에 .format() 해서 반환."""
    return _QSS.format(**tokens)
