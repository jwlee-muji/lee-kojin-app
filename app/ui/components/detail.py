"""Phase 1 atom — 디테일 페이지 공통 빌딩 블록.

이 파일에 포함된 컴포넌트:
    - LeeKPI         : 라벨 + 큰 값 + 단위 + delta + sub 의 KPI 타일
    - LeeDetailHeader: 디테일 페이지 공통 헤더 (back + icon tile + title + subtitle + badge + actions)
    - LeeChartFrame  : 차트 카드 (제목 + 코피 + 확대 모달 버튼)

디자인 출처: handoff/LEE_PROJECT/varA-detail-atoms.jsx
"""
from __future__ import annotations

from typing import Optional, Callable

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from .atoms import LeeIconTile, LeeTrend
from .button import LeeButton


# ──────────────────────────────────────────────────────────────────────
# 1. LeeKPI — 작은 KPI 타일
# ──────────────────────────────────────────────────────────────────────
class LeeKPI(QFrame):
    """라벨 + 큰 값 + 단위 + delta + sub 의 KPI 타일.

    레이아웃:
        ┌──────────────────────────────────┐
        │  LABEL                            │  ← 11px 700 letterspaced
        │  28.45 USD       ▲ 1.2%           │  ← 28px 800 mono + delta
        │  期間平均                          │  ← 11px secondary
        └──────────────────────────────────┘
    """

    def __init__(
        self,
        label: str = "",
        *,
        value: str = "--",
        unit: Optional[str] = None,
        color: Optional[str] = None,
        delta: Optional[float] = None,
        delta_inverse: bool = False,
        sub: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("leeKPI")
        self._is_dark = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        self._label_lbl = QLabel(label)
        self._label_lbl.setObjectName("leeKPILabel")
        layout.addWidget(self._label_lbl)

        row = QHBoxLayout()
        row.setSpacing(5)
        row.setAlignment(Qt.AlignBaseline)

        self._value_lbl = QLabel(value)
        self._value_lbl.setObjectName("leeKPIValue")
        if color:
            self._value_color = color
        else:
            self._value_color = None

        self._unit_lbl = QLabel(unit or "")
        self._unit_lbl.setObjectName("leeKPIUnit")

        self._trend = LeeTrend(inverse="inverse" if delta_inverse else "normal")
        self._trend.set_value(delta)

        row.addWidget(self._value_lbl, 0, Qt.AlignBaseline)
        row.addWidget(self._unit_lbl,  0, Qt.AlignBaseline)
        row.addStretch()
        row.addWidget(self._trend, 0, Qt.AlignVCenter)
        layout.addLayout(row)
        # setVisible 은 반드시 layout 추가 후 호출 — 그렇지 않으면 부모 없는 위젯이
        # 일순간 top-level window 로 화면에 깜빡 표시됨 (구 Windows 다이얼로그처럼 보임)
        self._unit_lbl.setVisible(bool(unit))

        self._sub_lbl = QLabel(sub or "")
        self._sub_lbl.setObjectName("leeKPISub")
        layout.addWidget(self._sub_lbl)
        self._sub_lbl.setVisible(bool(sub))

        self._apply_qss()

    # ── 외부 API ─────────────────────────────────────────────
    def set_value(
        self,
        value: str,
        *,
        unit: Optional[str] = None,
        color: Optional[str] = None,
        delta: Optional[float] = None,
        sub: Optional[str] = None,
    ) -> None:
        self._value_lbl.setText(value)
        if unit is not None:
            self._unit_lbl.setText(unit)
            self._unit_lbl.setVisible(bool(unit))
        if color is not None:
            self._value_color = color
            self._apply_qss()
        if delta is not None or delta == 0:
            self._trend.set_value(delta)
        if sub is not None:
            self._sub_lbl.setText(sub)
            self._sub_lbl.setVisible(bool(sub))

    def set_label(self, label: str) -> None:
        self._label_lbl.setText(label)

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    # ── 내부 ─────────────────────────────────────────────────
    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        bg_surface   = "#14161C" if is_dark else "#FFFFFF"
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        border       = "rgba(255,255,255,0.04)" if is_dark else "rgba(11,18,32,0.06)"
        value_color  = self._value_color or fg_primary
        self.setStyleSheet(f"""
            QFrame#leeKPI {{
                background: {bg_surface};
                border: 1px solid {border};
                border-radius: 16px;
            }}
            QLabel#leeKPILabel {{
                font-size: 11px; font-weight: 600;
                color: {fg_tertiary};
                background: transparent;
                letter-spacing: 0.6px;
                text-transform: uppercase;
            }}
            QLabel#leeKPIValue {{
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 28px; font-weight: 800;
                color: {value_color};
                background: transparent;
                letter-spacing: -0.5px;
            }}
            QLabel#leeKPIUnit {{
                font-size: 12px; font-weight: 600;
                color: {fg_tertiary};
                background: transparent;
                padding-bottom: 4px;
            }}
            QLabel#leeKPISub {{
                font-size: 11px;
                color: {fg_secondary};
                background: transparent;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# 2. LeeDetailHeader — 디테일 페이지 공통 헤더
# ──────────────────────────────────────────────────────────────────────
class LeeDetailHeader(QFrame):
    """디테일 페이지 공통 헤더.

    레이아웃:
        ┌─────────────────────────────────────────────────────────────┐
        │ [←]  [icon]  Title              [actions] [badge] [Export] │
        │              Subtitle                                       │
        └─────────────────────────────────────────────────────────────┘

    Signals
    -------
    back_clicked: ← 戻る 클릭 시
    export_clicked: エクスポート 클릭 시 (set_export_visible 로 표시 토글)
    """

    back_clicked   = Signal()
    export_clicked = Signal()

    def __init__(
        self,
        title: str = "",
        *,
        subtitle: str = "",
        accent: str = "#5B8DEF",
        icon_glyph: str = "⚡",
        icon_qicon: Optional[QIcon] = None,
        badge: Optional[str] = None,
        show_export: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("leeDetailHeader")
        self._is_dark = True
        self._accent = accent

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 18)
        layout.setSpacing(14)

        # Back 버튼
        self._back_btn = QPushButton("←")
        self._back_btn.setObjectName("dhBackBtn")
        self._back_btn.setFixedSize(36, 36)
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.clicked.connect(self.back_clicked.emit)
        layout.addWidget(self._back_btn)

        # Icon tile (44x44)
        self._icon_tile = LeeIconTile(
            icon=icon_qicon,
            color=accent,
            size=44,
            radius=12,
            glyph=icon_glyph if icon_qicon is None else None,
        )
        layout.addWidget(self._icon_tile)

        # Title + subtitle
        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(2)
        self._title_lbl = QLabel(title)
        self._title_lbl.setObjectName("dhTitle")
        self._subtitle_lbl = QLabel(subtitle)
        self._subtitle_lbl.setObjectName("dhSubtitle")
        text_box.addWidget(self._title_lbl)
        text_box.addWidget(self._subtitle_lbl)
        layout.addLayout(text_box, 1)

        # Actions slot (외부 위젯 삽입용)
        self._actions_layout = QHBoxLayout()
        self._actions_layout.setSpacing(6)
        layout.addLayout(self._actions_layout)

        # Badge pill
        self._badge_lbl = QLabel(badge or "")
        self._badge_lbl.setObjectName("dhBadge")
        layout.addWidget(self._badge_lbl)
        # setVisible 은 layout 추가 후 — 부모 없는 widget 의 setVisible 은 top-level window
        # 깜빡임 (구 Windows 다이얼로그처럼) 유발
        self._badge_lbl.setVisible(bool(badge))

        # Export button
        self._export_btn = LeeButton("⬇  エクスポート", variant="secondary", size="sm")
        self._export_btn.clicked.connect(self.export_clicked.emit)
        layout.addWidget(self._export_btn)
        self._export_btn.setVisible(show_export)

        self._apply_qss()

    # ── 외부 API ─────────────────────────────────────────────
    def add_action(self, widget: QWidget) -> None:
        self._actions_layout.addWidget(widget)

    def set_title(self, title: str) -> None:
        self._title_lbl.setText(title)

    def set_subtitle(self, subtitle: str) -> None:
        self._subtitle_lbl.setText(subtitle)

    def set_badge(self, text: Optional[str]) -> None:
        if text:
            self._badge_lbl.setText(text)
            self._badge_lbl.setVisible(True)
        else:
            self._badge_lbl.setVisible(False)

    def set_accent(self, color: str) -> None:
        self._accent = color
        self._icon_tile.set_color(color)
        self._apply_qss()

    def set_export_visible(self, visible: bool) -> None:
        self._export_btn.setVisible(visible)

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    # ── 내부 ─────────────────────────────────────────────────
    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        bg_surface   = "#14161C" if is_dark else "#FFFFFF"
        bg_surface_2 = "#1B1E26" if is_dark else "#F0F2F5"
        border       = "rgba(255,255,255,0.08)" if is_dark else "rgba(11,18,32,0.10)"
        border_subtle= "rgba(255,255,255,0.04)" if is_dark else "rgba(11,18,32,0.06)"
        accent       = self._accent
        accent_bg    = self._rgba(accent, 0.12)
        self.setStyleSheet(f"""
            QFrame#leeDetailHeader {{
                background: transparent;
                border-bottom: 1px solid {border_subtle};
            }}
            QPushButton#dhBackBtn {{
                background: {bg_surface};
                color: {fg_secondary};
                border: 1px solid {border};
                border-radius: 10px;
                font-size: 16px;
                font-weight: 700;
            }}
            QPushButton#dhBackBtn:hover {{
                background: {bg_surface_2};
                color: {fg_primary};
                border-color: {accent};
            }}
            QLabel#dhTitle {{
                font-size: 22px; font-weight: 800;
                color: {fg_primary};
                background: transparent;
                letter-spacing: -0.3px;
            }}
            QLabel#dhSubtitle {{
                font-size: 12px;
                color: {fg_secondary};
                background: transparent;
            }}
            QLabel#dhBadge {{
                background: {accent_bg};
                color: {accent};
                font-size: 11px; font-weight: 700;
                border-radius: 999px;
                padding: 5px 12px;
                letter-spacing: 0.3px;
            }}
        """)

    @staticmethod
    def _rgba(hex_str: str, alpha: float) -> str:
        h = hex_str.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r = int(h[0:2], 16); g = int(h[2:4], 16); b = int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"


# ──────────────────────────────────────────────────────────────────────
# 3. LeeChartFrame — 차트 카드 (제목 + 코피 + 확대 모달)
# ──────────────────────────────────────────────────────────────────────
class _ChartExpandDialog(QDialog):
    """ChartFrame 의 확대 모달."""

    def __init__(self, title: str, subtitle: str, content: QWidget, *, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Window)
        self.setWindowTitle(title)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("chartExpandHeader")
        h = QHBoxLayout(header)
        h.setContentsMargins(22, 14, 14, 14)
        h.setSpacing(8)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_lbl = QLabel(title); title_lbl.setObjectName("chartExpandTitle")
        sub_lbl = QLabel(subtitle); sub_lbl.setObjectName("chartExpandSubtitle")
        title_box.addWidget(title_lbl); title_box.addWidget(sub_lbl)
        # setVisible 은 layout 추가 후 — top-level window 깜빡임 방지
        sub_lbl.setVisible(bool(subtitle))
        h.addLayout(title_box, 1)
        close_btn = LeeButton("✕  閉じる", variant="secondary", size="sm")
        close_btn.clicked.connect(self.close)
        h.addWidget(close_btn)
        outer.addWidget(header)

        # Body
        body = QFrame()
        body.setObjectName("chartExpandBody")
        b = QVBoxLayout(body)
        b.setContentsMargins(20, 20, 20, 20)
        b.addWidget(content)
        outer.addWidget(body, 1)

        self.resize(1200, 700)


class LeeChartFrame(QFrame):
    """차트 카드 (제목 + subtitle + actions + copy + expand 버튼).

    Parameters
    ----------
    title : str
    subtitle : str
    accent : str (액센트 컬러)
    copy_target : QWidget | None
        코피 버튼 클릭 시 grab() 해서 클립보드에 넣을 위젯. None 이면 self 의 첫 자식 차트
    expand_factory : Callable[[], QWidget] | None
        확대 모달 띄울 때 새 차트 위젯을 만들어 반환하는 팩토리.
        None 이면 모달 버튼 숨김.
    """

    def __init__(
        self,
        title: str = "",
        *,
        subtitle: str = "",
        accent: str = "#5B8DEF",
        copy_target: Optional[QWidget] = None,
        expand_factory: Optional[Callable[[], QWidget]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("leeChartFrame")
        self._is_dark = True
        self._accent = accent
        self._copy_target = copy_target
        self._expand_factory = expand_factory

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("chartFrameHeader")
        h = QHBoxLayout(header)
        h.setContentsMargins(20, 14, 14, 12)
        h.setSpacing(8)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self._title_lbl = QLabel(title); self._title_lbl.setObjectName("chartFrameTitle")
        self._sub_lbl = QLabel(subtitle); self._sub_lbl.setObjectName("chartFrameSub")
        title_box.addWidget(self._title_lbl)
        title_box.addWidget(self._sub_lbl)
        h.addLayout(title_box, 1)
        # setVisible 은 layout 추가 후 — top-level window 깜빡임 방지
        self._sub_lbl.setVisible(bool(subtitle))

        self._actions_layout = QHBoxLayout()
        self._actions_layout.setSpacing(6)
        h.addLayout(self._actions_layout)

        self._copy_btn = QPushButton("📋")
        self._copy_btn.setObjectName("chartIconBtn")
        self._copy_btn.setToolTip("グラフをコピー")
        self._copy_btn.setCursor(Qt.PointingHandCursor)
        self._copy_btn.setFixedSize(32, 32)
        self._copy_btn.clicked.connect(self._on_copy)
        h.addWidget(self._copy_btn)

        self._expand_btn = QPushButton("⛶")
        self._expand_btn.setObjectName("chartIconBtn")
        self._expand_btn.setToolTip("拡大表示")
        self._expand_btn.setCursor(Qt.PointingHandCursor)
        self._expand_btn.setFixedSize(32, 32)
        self._expand_btn.clicked.connect(self._on_expand)
        h.addWidget(self._expand_btn)
        # setVisible 은 layout 추가 후 — top-level window 깜빡임 방지
        self._expand_btn.setVisible(expand_factory is not None)

        outer.addWidget(header)

        # Body slot
        self._body = QFrame()
        self._body.setObjectName("chartFrameBody")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)
        outer.addWidget(self._body, 1)

        self._apply_qss()

    # ── 외부 API ─────────────────────────────────────────────
    def set_content(self, widget: QWidget) -> None:
        # 기존 자식 제거
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self._body_layout.addWidget(widget)
        if self._copy_target is None:
            self._copy_target = widget

    def add_action(self, widget: QWidget) -> None:
        self._actions_layout.addWidget(widget)

    def set_title(self, title: str) -> None:
        self._title_lbl.setText(title)

    def set_subtitle(self, subtitle: str) -> None:
        self._sub_lbl.setText(subtitle)
        self._sub_lbl.setVisible(bool(subtitle))

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    # ── 내부 ─────────────────────────────────────────────────
    def _on_copy(self) -> None:
        target = self._copy_target
        if target is None:
            for i in range(self._body_layout.count()):
                w = self._body_layout.itemAt(i).widget()
                if w is not None:
                    target = w
                    break
        if target is None:
            return
        QApplication.clipboard().setPixmap(target.grab())
        try:
            from app.core.events import bus
            bus.toast_requested.emit("グラフ画像をコピーしました", "success")
        except Exception:
            pass

    def _on_expand(self) -> None:
        if self._expand_factory is None:
            return
        try:
            content = self._expand_factory()
        except Exception:
            return
        dlg = _ChartExpandDialog(
            self._title_lbl.text(), self._sub_lbl.text(), content, parent=self
        )
        dlg.exec()

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        bg_surface   = "#14161C" if is_dark else "#FFFFFF"
        bg_surface_2 = "#1B1E26" if is_dark else "#F0F2F5"
        border_subtle= "rgba(255,255,255,0.04)" if is_dark else "rgba(11,18,32,0.06)"
        border       = "rgba(255,255,255,0.08)" if is_dark else "rgba(11,18,32,0.10)"
        self.setStyleSheet(f"""
            QFrame#leeChartFrame {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 18px;
            }}
            QFrame#chartFrameHeader {{
                background: transparent;
                border-bottom: 1px solid {border_subtle};
            }}
            QFrame#chartFrameBody {{
                background: transparent;
            }}
            QLabel#chartFrameTitle {{
                font-size: 14px; font-weight: 700;
                color: {fg_primary};
                background: transparent;
            }}
            QLabel#chartFrameSub {{
                font-size: 11px;
                color: {fg_secondary};
                background: transparent;
            }}
            QPushButton#chartIconBtn {{
                background: {bg_surface_2};
                color: {fg_secondary};
                border: 1px solid {border};
                border-radius: 8px;
                font-size: 14px;
            }}
            QPushButton#chartIconBtn:hover {{
                color: {fg_primary};
                border-color: {self._accent};
            }}
        """)
