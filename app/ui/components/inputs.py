"""Phase 1 atom — Input 컴포넌트.

이 파일에 포함된 컴포넌트:
    - LeeDateInput : 디자인 톤에 맞춘 날짜 picker (◀ [QDateEdit] ▶ 今日)

디자인 출처: handoff/LEE_PROJECT/varA-datepicker.jsx
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtWidgets import QDateEdit, QFrame, QHBoxLayout, QPushButton

from .button import LeeButton


class LeeDateInput(QFrame):
    """날짜 picker (◀ / [QDateEdit] / ▶ / 今日 / 액센트 컬러 underline).

    Signals
    -------
    date_changed(QDate)
    """

    date_changed = Signal(QDate)

    def __init__(
        self,
        *,
        accent: str = "#5B8DEF",
        show_today_btn: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("leeDateInput")
        self._is_dark = True
        self._accent = accent

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._btn_prev = QPushButton("◀")
        self._btn_prev.setObjectName("dateNavBtn")
        self._btn_prev.setFixedSize(28, 30)
        self._btn_prev.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self._btn_prev)

        self._date_edit = QDateEdit()
        self._date_edit.setObjectName("dateEditCenter")
        self._date_edit.setCalendarPopup(True)
        # Phase 6 — 디자인 시스템 톤의 popup 적용
        try:
            from app.ui.components.mini_calendar import LeeMiniCalendar
            self._date_edit.setCalendarWidget(LeeMiniCalendar(accent=accent))
        except Exception:
            pass
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setFixedHeight(30)
        self._date_edit.setMinimumWidth(120)
        layout.addWidget(self._date_edit)

        self._btn_next = QPushButton("▶")
        self._btn_next.setObjectName("dateNavBtn")
        self._btn_next.setFixedSize(28, 30)
        self._btn_next.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self._btn_next)

        if show_today_btn:
            self._btn_today = LeeButton("今日", variant="secondary", size="sm")
            layout.addWidget(self._btn_today)
        else:
            self._btn_today = None

        self._btn_prev.clicked.connect(lambda: self._date_edit.setDate(self._date_edit.date().addDays(-1)))
        self._btn_next.clicked.connect(lambda: self._date_edit.setDate(self._date_edit.date().addDays(1)))
        if self._btn_today is not None:
            self._btn_today.clicked.connect(lambda: self._date_edit.setDate(QDate.currentDate()))
        self._date_edit.dateChanged.connect(self.date_changed.emit)

        self._apply_qss()

    # ── 외부 API ─────────────────────────────────────────────
    def date(self) -> QDate:
        return self._date_edit.date()

    def set_date(self, d: QDate) -> None:
        self._date_edit.setDate(d)

    def set_accent(self, color: str) -> None:
        self._accent = color
        self._apply_qss()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    # ── 내부 ─────────────────────────────────────────────────
    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        bg_input     = "#1B1E26" if is_dark else "#FFFFFF"
        bg_surface_2 = "#1B1E26" if is_dark else "#F0F2F5"
        border       = "rgba(255,255,255,0.08)" if is_dark else "rgba(11,18,32,0.10)"
        accent       = self._accent
        accent_hover = self._rgba(accent, 0.10)
        accent_border= self._rgba(accent, 0.30)
        self.setStyleSheet(f"""
            QFrame#leeDateInput {{ background: transparent; }}
            QPushButton#dateNavBtn {{
                background: {bg_surface_2};
                color: {fg_secondary};
                border: 1px solid {border};
                border-radius: 6px;
                font-size: 11px;
                font-weight: 700;
            }}
            QPushButton#dateNavBtn:hover {{
                background: {accent_hover};
                color: {accent};
                border-color: {accent_border};
            }}
            QDateEdit#dateEditCenter {{
                background: {bg_input};
                color: {fg_primary};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 0 10px;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 12px; font-weight: 600;
            }}
            QDateEdit#dateEditCenter:focus {{
                border-color: {accent};
            }}
        """)

    @staticmethod
    def _rgba(hex_str: str, alpha: float) -> str:
        h = hex_str.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r = int(h[0:2], 16); g = int(h[2:4], 16); b = int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"
