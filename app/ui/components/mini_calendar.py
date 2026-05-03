"""LeeMiniCalendar — QCalendarWidget 서브클래스.

QDateEdit / QDateTimeEdit 의 popup 을 디자인 시스템 톤에 맞춰 통일.

사용법:
    from app.ui.components import LeeMiniCalendar

    date_edit = QDateEdit()
    date_edit.setCalendarPopup(True)
    date_edit.setCalendarWidget(LeeMiniCalendar())

특징:
    - 다크 톤 / 둥근 모서리 / accent (FF7A45) selection
    - 토/일 색상 구분 (sat #42A5F5, sun #EF5350)
    - 헤더/푸터 (今日 버튼) 커스텀
    - 다크/라이트 자동 적응 (set_theme)
"""
from __future__ import annotations

from PySide6.QtCore import (
    QDate, Qt, Signal, QPropertyAnimation, QEasingCurve, QRect,
    QParallelAnimationGroup,
)
from PySide6.QtGui import QTextCharFormat, QColor, QFont
from PySide6.QtWidgets import (
    QCalendarWidget, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton,
    QToolButton, QVBoxLayout, QWidget,
)


# 디자인 정합 (varA-datepicker.jsx:109,128) — Tailwind 표준 채도
_C_ACCENT  = "#FF7A45"
_C_SAT     = "#3B82F6"
_C_SUN     = "#EF4444"


class LeeMiniCalendar(QCalendarWidget):
    """디자인 시스템 톤의 QCalendarWidget — QDateEdit popup 으로 사용 권장.

    Signals
    -------
    today_clicked : 푸터 「今日」 버튼 클릭 (옵션)
    """

    today_clicked = Signal()

    def __init__(self, parent=None, accent: str = _C_ACCENT, is_dark: bool = True):
        super().__init__(parent)
        self._accent = accent
        self._is_dark = is_dark

        # 기본 동작
        self.setGridVisible(False)
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.SingleLetterDayNames)
        self.setFirstDayOfWeek(Qt.Monday)
        self.setNavigationBarVisible(True)
        self.setSelectionMode(QCalendarWidget.SingleSelection)

        # 헤더 nav 버튼 텍스트화 (이모지 ◀ ▶)
        self._customize_nav_bar()

        # 토/일 색상 구분
        self._apply_weekend_colors()

        # 푸터 (今日 버튼) — QCalendarWidget 자체에는 footer 가 없으므로
        # 외부에서 wrap 하면 됨. 단순화를 위해 본 위젯은 footer 없이 내부만.
        self._apply_qss()

    # ── 팝업 calPop (디자인: 0.15s scale 0.97→1.0 + opacity 0→1, ease-out) ──
    def showEvent(self, event):
        super().showEvent(event)
        # Opacity fade-in
        eff = QGraphicsOpacityEffect(self)
        eff.setOpacity(0.0)
        self.setGraphicsEffect(eff)
        anim_op = QPropertyAnimation(eff, b"opacity", self)
        anim_op.setDuration(150)
        anim_op.setEasingCurve(QEasingCurve.OutCubic)
        anim_op.setStartValue(0.0); anim_op.setEndValue(1.0)
        anim_op.finished.connect(lambda: self.setGraphicsEffect(None))

        # Scale-in (center-anchored geometry shrink → grow)
        # Qt 의 QWidget 은 QGraphicsScale 직접 적용 불가 → geometry 애니메이션으로 모방
        full = QRect(self.geometry())
        cx, cy = full.center().x(), full.center().y()
        sw = max(1, int(full.width() * 0.97))
        sh = max(1, int(full.height() * 0.97))
        start_geom = QRect(cx - sw // 2, cy - sh // 2, sw, sh)
        anim_g = QPropertyAnimation(self, b"geometry", self)
        anim_g.setDuration(150)
        anim_g.setEasingCurve(QEasingCurve.OutCubic)
        anim_g.setStartValue(start_geom)
        anim_g.setEndValue(full)

        grp = QParallelAnimationGroup(self)
        grp.addAnimation(anim_op); grp.addAnimation(anim_g)
        self.setGeometry(start_geom)   # 시작 위치 즉시 적용 → 깜빡임 방지
        grp.start()
        self._pop_anim = grp           # GC 방지

    # ── public ────────────────────────────────────────────────
    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_weekend_colors()
        self._apply_qss()

    def set_accent(self, accent: str) -> None:
        self._accent = accent
        self._apply_qss()

    # ── 내부 ──────────────────────────────────────────────────
    def _customize_nav_bar(self) -> None:
        """nav bar 의 PrevMonth/NextMonth 버튼 글리프 변경."""
        # QCalendarWidget 의 prev/next 버튼은 QToolButton 자식
        for btn in self.findChildren(QToolButton):
            name = btn.objectName()
            if name == "qt_calendar_prevmonth":
                btn.setText("◀"); btn.setIcon(QIcon())   # icon 제거
            elif name == "qt_calendar_nextmonth":
                btn.setText("▶"); btn.setIcon(QIcon())

    def _apply_weekend_colors(self) -> None:
        sat_fmt = QTextCharFormat()
        sat_fmt.setForeground(QColor(_C_SAT))
        sun_fmt = QTextCharFormat()
        sun_fmt.setForeground(QColor(_C_SUN))
        self.setWeekdayTextFormat(Qt.Saturday, sat_fmt)
        self.setWeekdayTextFormat(Qt.Sunday,   sun_fmt)

    def _apply_qss(self) -> None:
        d = self._is_dark
        bg_app        = "#0A0B0F" if d else "#F5F6F8"
        bg_surface    = "#14161C" if d else "#FFFFFF"
        bg_surface_2  = "#1B1E26" if d else "#F0F2F5"
        bg_surface_3  = "#232730" if d else "#E6E9EE"
        fg_primary    = "#F2F4F7" if d else "#0B1220"
        fg_secondary  = "#A8B0BD" if d else "#4A5567"
        fg_disabled   = "#3D424D" if d else "#C2C8D2"
        bs            = "rgba(255,255,255,0.06)" if d else "rgba(11,18,32,0.06)"
        accent        = self._accent
        accent_bg     = self._rgba(accent, 0.20)

        self.setStyleSheet(f"""
            QCalendarWidget {{
                background: {bg_surface};
                color: {fg_primary};
                border: 1px solid {bs};
                border-radius: 10px;
            }}
            /* nav bar */
            QCalendarWidget QWidget#qt_calendar_navigationbar {{
                background: {bg_surface_2};
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                border-bottom: 1px solid {bs};
            }}
            QCalendarWidget QToolButton {{
                background: transparent;
                color: {fg_primary};
                border: none;
                font-size: 12.5px;
                font-weight: 700;
                padding: 4px 10px;
                margin: 4px 2px;
                border-radius: 6px;
            }}
            QCalendarWidget QToolButton:hover {{
                background: {bg_surface_3};
            }}
            QCalendarWidget QToolButton::menu-indicator {{ image: none; }}
            QCalendarWidget QToolButton#qt_calendar_prevmonth,
            QCalendarWidget QToolButton#qt_calendar_nextmonth {{
                font-size: 14px;
                qproperty-icon: none;
                min-width: 28px;
            }}
            QCalendarWidget QSpinBox {{
                background: {bg_surface_2}; color: {fg_primary};
                border: 1px solid {bs}; border-radius: 6px;
            }}
            QCalendarWidget QMenu {{
                background: {bg_surface_2}; color: {fg_primary};
                border: 1px solid {bs};
            }}
            /* day grid */
            QCalendarWidget QAbstractItemView {{
                background: {bg_surface};
                color: {fg_primary};
                selection-background-color: {accent};
                selection-color: white;
                outline: none;
                font-size: 12px;
            }}
            QCalendarWidget QAbstractItemView:disabled {{
                color: {fg_disabled};
            }}
            QCalendarWidget QAbstractItemView::item:hover {{
                background: {accent_bg};
            }}
        """)

    @staticmethod
    def _rgba(hex_color: str, alpha: float) -> str:
        c = QColor(hex_color)
        return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


# QToolButton.setIcon(QIcon()) 사용을 위한 import (위에서 lazy 회피)
from PySide6.QtGui import QIcon   # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# Helper — QDateEdit / QDateTimeEdit 에 일괄 적용
# ──────────────────────────────────────────────────────────────────────
def install_on_date_edits(root: QWidget, accent: str = _C_ACCENT) -> int:
    """root 의 모든 QDateEdit / QDateTimeEdit 에 LeeMiniCalendar popup 적용.

    Returns 적용된 개수.
    """
    from PySide6.QtWidgets import QDateEdit, QDateTimeEdit
    count = 0
    for w in root.findChildren(QDateEdit):
        if not w.calendarPopup():
            w.setCalendarPopup(True)
        try:
            if isinstance(w.calendarWidget(), LeeMiniCalendar):
                continue
            w.setCalendarWidget(LeeMiniCalendar(accent=accent))
            count += 1
        except Exception:
            pass
    for w in root.findChildren(QDateTimeEdit):
        if isinstance(w, QDateEdit):
            continue   # QDateEdit subclass — already handled
        if not w.calendarPopup():
            w.setCalendarPopup(True)
        try:
            if isinstance(w.calendarWidget(), LeeMiniCalendar):
                continue
            w.setCalendarWidget(LeeMiniCalendar(accent=accent))
            count += 1
        except Exception:
            pass
    return count


__all__ = ["LeeMiniCalendar", "install_on_date_edits"]
