"""LeeSegment — Segmented control (탭형 토글).

디자인 출처: handoff/02-components.md §8.1, varA-detail-screens.jsx SegTabs

Usage
-----
seg = LeeSegment(
    options=[("daily", "当日"), ("daily_avg", "日次平均"), ...],
    value="daily",
    accent="#FF7A45",
)
seg.value_changed.connect(lambda key: ...)
"""
from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton


class LeeSegment(QFrame):
    """Segmented (탭형) 컨트롤. 한 번에 하나만 선택, 이미 선택된 항목 재클릭 무시.

    Parameters
    ----------
    options : list[tuple[str, str]]
        [(key, label), ...] — key 는 내부 식별자, label 는 표시 텍스트.
    value : str | None
        초기 선택 key. None ⇒ 첫 번째.
    accent : str
        활성 배경 컬러 (헥스).
    """

    value_changed = Signal(str)

    def __init__(
        self,
        options: Sequence[tuple[str, str]],
        *,
        value: Optional[str] = None,
        accent: str = "#FF7A45",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("leeSegment")
        self._is_dark = True
        self._accent = accent
        self._options = list(options)
        self._buttons: dict[str, QPushButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        for key, label in self._options:
            btn = QPushButton(label)
            btn.setObjectName("segmentBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, k=key: self._on_click(k))
            self._buttons[key] = btn
            layout.addWidget(btn)

        initial = value if value and value in self._buttons else self._options[0][0]
        self._value = initial
        self._buttons[initial].setChecked(True)
        self._apply_qss()

    # ── 외부 API ─────────────────────────────────────────────
    def value(self) -> str:
        return self._value

    def set_value(self, key: str, *, emit: bool = False) -> None:
        if key not in self._buttons or key == self._value:
            return
        self._buttons[self._value].setChecked(False)
        self._value = key
        self._buttons[key].setChecked(True)
        if emit:
            self.value_changed.emit(key)

    def set_accent(self, color: str) -> None:
        self._accent = color
        self._apply_qss()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    # ── 내부 ─────────────────────────────────────────────────
    def _on_click(self, key: str) -> None:
        if key == self._value:
            self._buttons[key].setChecked(True)  # toggle 취소 방지
            return
        if self._value in self._buttons:
            self._buttons[self._value].setChecked(False)
        self._value = key
        self._buttons[key].setChecked(True)
        self.value_changed.emit(key)

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        bg_surface_2 = "#1B1E26" if is_dark else "#F0F2F5"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_on_accent = "#FFFFFF"
        accent = self._accent
        accent_hover = self._rgba(accent, 0.10)

        self.setStyleSheet(f"""
            QFrame#leeSegment {{
                background: {bg_surface_2};
                border-radius: 12px;
            }}
            QPushButton#segmentBtn {{
                background: transparent;
                color: {fg_secondary};
                border: none;
                border-radius: 9px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 700;
                min-height: 22px;
            }}
            QPushButton#segmentBtn:hover {{
                background: {accent_hover};
                color: {accent};
            }}
            QPushButton#segmentBtn:checked {{
                background: {accent};
                color: {fg_on_accent};
            }}
        """)

    @staticmethod
    def _rgba(hex_str: str, alpha: float) -> str:
        h = hex_str.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r = int(h[0:2], 16); g = int(h[2:4], 16); b = int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"


def qss(tokens: dict) -> str:
    """LeeSegment 는 자체 stylesheet 로 처리하지만 호환을 위해 빈 문자열 반환."""
    return ""
