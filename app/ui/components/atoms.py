"""Phase 1 atom 컴포넌트 묶음 — 작은 재사용 atom 들.

이 파일에 포함된 atom:
    - LeeIconTile  : 컬러 타일 + 아이콘 (사이드바·카드·헤더 공통)
    - LeeSparkline : SVG 스타일 mini 라인 차트 (pyqtgraph 베이스)
    - LeeTrend     : ▲/▼ 화살표 + 퍼센트 (delta 표시)
    - LeeCountValue: 숫자 카운트업 애니메이션 라벨

디자인 출처: handoff/LEE_PROJECT/varA-atoms.jsx, varA-detail-atoms.jsx
"""
from __future__ import annotations

from typing import Optional, Callable, Literal

import pyqtgraph as pg
from PySide6.QtCore import (
    Qt, QTimer, QSize, QEasingCurve, QVariantAnimation,
    QPropertyAnimation, Property,
)
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget


# ──────────────────────────────────────────────────────────────────────
# 1. LeeIconTile — 컬러 타일 + 아이콘
# ──────────────────────────────────────────────────────────────────────
class LeeIconTile(QLabel):
    """컬러 타일 + 아이콘 (사이드바, 카드 헤더, 디테일 헤더 공통).

    Parameters
    ----------
    icon : QIcon | str | None
        QIcon 인스턴스, 리소스 경로 (':/img/...'), 또는 None (텍스트 글리프 사용)
    color : str
        타일 색상 (CSS hex). 배경은 color@15% 알파, 아이콘 틴트는 color
    size : int
        타일 한 변 크기 (픽셀). 기본 36
    radius : int | None
        라운드 반경. None 이면 size * 0.33 자동 계산
    glyph : str | None
        icon 이 None 일 때 사용할 텍스트 글리프 (예: ⚡)
    active : bool
        True 면 배경=color, 아이콘=흰색 (사이드바 active 상태)
    """

    def __init__(
        self,
        icon=None,
        *,
        color: str = "#5B8DEF",
        size: int = 36,
        radius: Optional[int] = None,
        glyph: Optional[str] = None,
        active: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("leeIconTile")
        self._color = color
        self._tile_size = size
        self._radius = radius if radius is not None else max(6, int(size * 0.33))
        self._icon = icon
        self._glyph = glyph
        self._active = active
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self._render()

    def _render(self) -> None:
        # 아이콘 또는 글리프
        if self._icon is not None:
            qicon = self._icon if isinstance(self._icon, QIcon) else QIcon(self._icon)
            inner = int(self._tile_size * 0.55)
            pix = qicon.pixmap(inner, inner)
            if not self._active:
                pix = self._tinted(pix, QColor(self._color))
            else:
                pix = self._tinted(pix, QColor("#ffffff"))
            self.setPixmap(pix)
        elif self._glyph is not None:
            self.setText(self._glyph)
        # 스타일
        if self._active:
            bg = self._color
            fg = "#ffffff"
        else:
            bg = self._rgba_from_hex(self._color, 0.15)
            fg = self._color
        glyph_size = int(self._tile_size * 0.5)
        self.setStyleSheet(f"""
            QLabel#leeIconTile {{
                background: {bg};
                color: {fg};
                border-radius: {self._radius}px;
                font-size: {glyph_size}px;
                font-weight: 700;
            }}
        """)

    def set_active(self, active: bool) -> None:
        if self._active != active:
            self._active = active
            self._render()

    def set_color(self, color: str) -> None:
        self._color = color
        self._render()

    def set_icon(self, icon) -> None:
        self._icon = icon
        self._glyph = None
        self.clear()
        self._render()

    @staticmethod
    def _tinted(src: QPixmap, color: QColor) -> QPixmap:
        if src.isNull():
            return src
        out = QPixmap(src.size())
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.drawPixmap(0, 0, src)
        p.setCompositionMode(QPainter.CompositionMode_SourceIn)
        p.fillRect(out.rect(), color)
        p.end()
        return out

    @staticmethod
    def _rgba_from_hex(hex_str: str, alpha: float) -> str:
        h = hex_str.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r = int(h[0:2], 16); g = int(h[2:4], 16); b = int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"


# ──────────────────────────────────────────────────────────────────────
# 2. LeeSparkline — pyqtgraph 베이스 mini 라인 차트
# ──────────────────────────────────────────────────────────────────────
class LeeSparkline(pg.PlotWidget):
    """28~48px 높이의 mini 라인 차트 (라인 + 영역 채우기).

    Parameters
    ----------
    color : str
        라인 + 채우기 색상
    height : int
        높이 (기본 28)
    fill_alpha : int
        영역 채우기 알파 (0-255, 기본 38)
    """

    def __init__(
        self,
        color: str = "#5B8DEF",
        *,
        height: int = 28,
        fill_alpha: int = 38,
        card_bg: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._color = color
        self._fill_alpha = fill_alpha
        self._explicit_card_bg = card_bg   # None 이면 부모 카드 색 자동 follow (transparent)
        # 카드 surface 컬러 자동 결정 (명시값 우선, 없으면 현재 테마의 bg_surface)
        from app.ui.theme import ThemeManager
        tm = ThemeManager.instance()
        self._card_bg = card_bg or tm.tokens["bg_surface"]
        self.setFixedHeight(height)
        if card_bg is None:
            # 자동 follow 모드 — pyqtgraph viewport / Qt 배경 모두 transparent
            # → 부모 카드 색 (active 시 rgba 합성 포함) 그대로 노출, 모든 상태에서
            # 색차 없음. 명시 카드 색을 강제하고 싶을 땐 set_card_bg() 호출.
            self.setBackground(QColor(0, 0, 0, 0))
            self.setStyleSheet("background: transparent; border: none;")
        else:
            self.setBackground(self._card_bg)
            self.setStyleSheet(f"background: {self._card_bg}; border: none;")
        self.hideAxis('bottom')
        self.hideAxis('left')
        self.setMouseEnabled(False, False)
        self.setMenuEnabled(False)
        self.getPlotItem().getViewBox().setMouseEnabled(False, False)
        self.getPlotItem().setContentsMargins(0, 0, 0, 0)
        self.getPlotItem().hideButtons()
        # 테마 전환 시 자동으로 카드 배경 follow (명시값이 없을 때만 호환 유지용)
        if card_bg is None:
            tm.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, theme: str) -> None:
        """ThemeManager.theme_changed 시그널 핸들러 — auto-follow 모드는 transparent 유지."""
        if self._explicit_card_bg is not None:
            # 명시 색이 있으면 그 색 유지 (호환)
            return
        # 자동 follow 모드 — 부모 카드 배경 그대로 노출하므로 갱신 불필요
        # 단 일부 환경에서 transparent 가 풀리는 경우를 대비해 재적용
        self.setBackground(QColor(0, 0, 0, 0))
        self.setStyleSheet("background: transparent; border: none;")

    def set_card_bg(self, color: str) -> None:
        """카드 surface 컬러로 sparkline 배경 통일 (수동 override 시 호출)."""
        self._card_bg = color
        self.setBackground(color)
        self.setStyleSheet(f"background: {color}; border: none;")

    def set_data(self, values: list[float]) -> None:
        self.clear()
        if not values or len(values) < 2:
            return
        x = list(range(len(values)))
        c = QColor(self._color)
        self.plot(
            x, values,
            pen=pg.mkPen(self._color, width=2),
            fillLevel=min(values) - (max(values) - min(values)) * 0.1,
            brush=pg.mkBrush(c.red(), c.green(), c.blue(), self._fill_alpha),
        )
        self.enableAutoRange()

    def set_color(self, color: str) -> None:
        self._color = color


# ──────────────────────────────────────────────────────────────────────
# 3. LeeTrend — ▲/▼ + 퍼센트
# ──────────────────────────────────────────────────────────────────────
TrendInverse = Literal["normal", "inverse"]


class LeeTrend(QLabel):
    """▲ N.N% / ▼ N.N% — delta 변화율 표시.

    Parameters
    ----------
    inverse : "normal" | "inverse"
        normal: 양수=빨강(나쁨), 음수=초록(좋음) — 가격/임밸런스 등
        inverse: 양수=초록(좋음), 음수=빨강(나쁨) — 예비율 등 높은 게 좋은 지표
    """

    _C_BAD = "#FF453A"
    _C_OK = "#30D158"

    def __init__(self, *, inverse: TrendInverse = "normal", parent=None):
        super().__init__(parent)
        self.setObjectName("leeTrend")
        self._inverse = inverse
        self._render(None)

    def set_value(self, percent: Optional[float]) -> None:
        self._render(percent)

    def _render(self, percent: Optional[float]) -> None:
        if percent is None or abs(percent) < 0.01:
            self.setText("")
            return
        up = percent > 0
        if self._inverse == "inverse":
            color = self._C_OK if up else self._C_BAD
        else:
            color = self._C_BAD if up else self._C_OK
        arrow = "▲" if up else "▼"
        self.setText(f"{arrow} {abs(percent):.2f}%")
        self.setStyleSheet(
            f"QLabel#leeTrend {{ color: {color}; font-size: 11px; font-weight: 700; background: transparent; }}"
        )


# ──────────────────────────────────────────────────────────────────────
# 4. LeeCountValue — 숫자 카운트업 애니메이션 라벨
# ──────────────────────────────────────────────────────────────────────
class LeeCountValue(QLabel):
    """숫자 카운트업 애니메이션 (mono 폰트 + tnum)."""

    def __init__(
        self,
        *,
        formatter: Optional[Callable[[float], str]] = None,
        duration_ms: int = 700,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("leeCountValue")
        self._formatter = formatter or (lambda v: f"{v:.1f}")
        self._duration = duration_ms
        self._anim: Optional[QVariantAnimation] = None
        self._cur = 0.0
        self.setText(self._formatter(0.0))

    def set_value(self, target: float, *, animate: bool = True) -> None:
        # 진행 중인 애니메이션은 어떤 경우든 중단 (텍스트 덮어쓰기 방지)
        if self._anim is not None:
            self._anim.stop()
        if not animate or self._cur == target:
            self._cur = float(target)
            self.setText(self._formatter(self._cur))
            return
        anim = QVariantAnimation(self)
        anim.setStartValue(float(self._cur))
        anim.setEndValue(float(target))
        anim.setDuration(self._duration)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(self._on_tick)
        anim.finished.connect(lambda v=target: self._on_done(v))
        self._anim = anim
        anim.start()

    def _on_tick(self, v) -> None:
        self._cur = float(v)
        self.setText(self._formatter(self._cur))

    def _on_done(self, target: float) -> None:
        self._cur = float(target)
        self.setText(self._formatter(self._cur))


# ──────────────────────────────────────────────────────────────────────
# QSS — atoms 공통 (단, LeeIconTile/LeeTrend/LeeCountValue 는 인스턴스별 스타일)
# ──────────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────
# 5. LeeRingSpinner — 회전 링 스피너 (lw-spin 1s linear infinite 재현)
# ──────────────────────────────────────────────────────────────────────
class LeeRingSpinner(QWidget):
    """{size}px 회전 링 — track + accent 호 회전.

    Parameters
    ----------
    size : int
        한 변 픽셀 (40 / 64 / ...)
    color : str
        회전 호 컬러 (track 은 자동으로 살짝 보이는 회색)
    track_alpha : int
        트랙 (회색 호) 알파 (0-255)
    arc_length_deg : int
        회전하는 호의 길이 (각도, 기본 90)
    duration_ms : int
        한 바퀴 회전 시간 (기본 1000ms)
    border_width : int
        선 굵기 (기본 3)
    """

    def __init__(
        self,
        *,
        size: int = 40,
        color: str = "#FF7A45",
        track_alpha: int = 18,
        arc_length_deg: int = 90,
        duration_ms: int = 1000,
        border_width: int = 3,
        parent=None,
    ):
        super().__init__(parent)
        self._size = size
        self._color = color
        self._track_alpha = track_alpha
        self._arc_length = arc_length_deg
        self._border = border_width
        self._angle = 0
        self.setFixedSize(size, size)
        self._anim = QPropertyAnimation(self, b"angle", self)
        self._anim.setStartValue(0)
        self._anim.setEndValue(360)
        self._anim.setDuration(duration_ms)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Linear)

    def start(self) -> None:
        if self._anim.state() != QPropertyAnimation.Running:
            self._anim.start()

    def stop(self) -> None:
        self._anim.stop()

    def get_angle(self) -> int:
        return self._angle

    def set_angle(self, value: int) -> None:
        self._angle = value
        self.update()

    angle = Property(int, get_angle, set_angle)

    def set_color(self, color: str) -> None:
        self._color = color
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        margin = self._border // 2 + 1
        rect = self.rect().adjusted(margin, margin, -margin, -margin)

        # 트랙 (전체 회색 호)
        track_pen = QPen(QColor(255, 255, 255, self._track_alpha), self._border)
        track_pen.setCapStyle(Qt.RoundCap)
        p.setPen(track_pen)
        p.drawArc(rect, 0, 360 * 16)

        # 회전하는 accent 호 (90도 시작 + angle 회전, arc_length 길이)
        active_pen = QPen(QColor(self._color), self._border)
        active_pen.setCapStyle(Qt.RoundCap)
        p.setPen(active_pen)
        p.drawArc(rect, (90 - self._angle) * 16, self._arc_length * 16)


# ──────────────────────────────────────────────────────────────────────
# QSS
# ──────────────────────────────────────────────────────────────────────
_QSS = """
QLabel#leeCountValue {{
    font-family: "JetBrains Mono", "Consolas", monospace;
    font-variant-numeric: tabular-nums;
    background: transparent;
}}
"""


def qss(tokens: dict) -> str:
    return _QSS.format(**tokens)
