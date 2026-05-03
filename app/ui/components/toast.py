"""LeeToast — 세련된 우상단 슬라이드 토스트 시스템.

사용법 (직접 호출 — 권장):
    from app.ui.components import LeeToast
    LeeToast.show("保存しました", kind="success")
    LeeToast.show("接続失敗", kind="error", duration=5000)

기존 시그널 호환 (점진적 마이그레이션):
    from app.core.events import bus
    bus.toast_requested.emit("...", "info")
    # MainWindow 가 자동으로 LeeToast.show() 로 forward (main_window.py)

특징:
    - 우상단 슬라이드 인 (X 위치 right - margin → 단말 right - margin)
    - 세로 스택 큐 (최대 4개 동시 표시, 5번째부터는 가장 오래된 것 fade out 후 진입)
    - kind 별 색상 + 아이콘 (info/success/warning/error/update)
    - 디바운스 + dedupe — 250ms 윈도우 안 같은 메시지 합산
    - 워밍업 — 부팅 후 3초간 info/success 무음
    - 클릭 시 즉시 dismiss
"""
from __future__ import annotations

import time
from collections import deque
from typing import Literal, Optional

from PySide6.QtCore import (
    QEasingCurve, QObject, QPoint, QPropertyAnimation, QRect, QTimer, Qt, Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)


ToastKind = Literal["info", "success", "warning", "error", "update"]


# ──────────────────────────────────────────────────────────────────────
# kind 별 색상 + 아이콘
# ──────────────────────────────────────────────────────────────────────
_KIND_META: dict[str, tuple[str, str]] = {
    "info":    ("#0A84FF", "ⓘ"),
    "success": ("#30D158", "✓"),
    "warning": ("#FF9F0A", "⚠"),
    "error":   ("#FF453A", "✕"),
    "update":  ("#FF7A45", "↑"),
}

_LEVEL_PRIORITY = {"error": 0, "warning": 1, "update": 2, "success": 3, "info": 4}


# ──────────────────────────────────────────────────────────────────────
# _ToastItem — 단일 토스트 위젯 (frameless, top-right)
# ──────────────────────────────────────────────────────────────────────
class _ToastItem(QFrame):
    """단일 토스트 시각 위젯.

    배치는 _ToastManager 가 setGeometry 로 직접 제어.
    """

    dismissed = Signal(object)   # _ToastItem self

    def __init__(self, message: str, kind: str, duration_ms: int,
                 host: QWidget):
        super().__init__(host)
        self.message = message
        self.kind = kind
        self.duration_ms = duration_ms
        self._is_dismissing = False

        self.setObjectName("leeToast")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)

        color, glyph = _KIND_META.get(kind, _KIND_META["info"])
        self._color = color
        self._build_ui(message, glyph, color)
        self._apply_qss(color)

        # 드롭 섀도 (뜬 카드 느낌)
        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(28); sh.setOffset(0, 6)
        sh.setColor(QColor(0, 0, 0, 110))
        self.setGraphicsEffect(sh)

        # 자동 dismiss 타이머
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self.dismiss)
        self._auto_timer.start(max(800, int(duration_ms)))

        # 호버 시 타이머 일시정지
        self._paused_remaining_ms: Optional[int] = None

    def _build_ui(self, message: str, glyph: str, color: str) -> None:
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 12, 14, 12); h.setSpacing(10)

        # 색상 dot + glyph
        icon = QLabel(glyph)
        icon.setObjectName("leeToastIcon")
        icon.setFixedSize(24, 24); icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(
            f"QLabel#leeToastIcon {{ background: {color}; color: white;"
            f" border-radius: 12px; font-size: 13px; font-weight: 800; }}"
        )
        h.addWidget(icon, 0, Qt.AlignVCenter)

        # 메시지
        msg_lbl = QLabel(message)
        msg_lbl.setObjectName("leeToastMsg")
        msg_lbl.setWordWrap(True)
        msg_lbl.setMinimumWidth(180); msg_lbl.setMaximumWidth(360)
        h.addWidget(msg_lbl, 1, Qt.AlignVCenter)

        # 닫기 버튼
        close_btn = QPushButton("✕")
        close_btn.setObjectName("leeToastClose")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.dismiss)
        h.addWidget(close_btn, 0, Qt.AlignTop)

    def _apply_qss(self, color: str) -> None:
        # 다크 베이스 (토스트는 항상 다크 톤)
        self.setStyleSheet(f"""
            QFrame#leeToast {{
                background: #14161C;
                border: 1px solid rgba(255,255,255,0.08);
                border-left: 3px solid {color};
                border-radius: 10px;
            }}
            QLabel#leeToastMsg {{
                color: #F2F4F7; background: transparent;
                font-size: 12.5px; font-weight: 600;
            }}
            QPushButton#leeToastClose {{
                background: transparent; color: #6B7280;
                border: none; font-size: 11px; font-weight: 700;
            }}
            QPushButton#leeToastClose:hover {{
                color: #F2F4F7;
            }}
        """)

    # ── 호버 → 자동 dismiss 일시정지 ──────────────────────────
    def enterEvent(self, e):
        if self._auto_timer.isActive():
            self._paused_remaining_ms = self._auto_timer.remainingTime()
            self._auto_timer.stop()

    def leaveEvent(self, e):
        if self._paused_remaining_ms is not None and not self._is_dismissing:
            self._auto_timer.start(max(800, self._paused_remaining_ms))
            self._paused_remaining_ms = None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.dismiss()
        super().mousePressEvent(e)

    # ── dismiss ───────────────────────────────────────────────
    def dismiss(self) -> None:
        if self._is_dismissing:
            return
        self._is_dismissing = True
        self._auto_timer.stop()
        self.dismissed.emit(self)


# ──────────────────────────────────────────────────────────────────────
# _ToastManager — 싱글톤. 큐 / 우선순위 / 워밍업 / dedupe / stack 위치
# ──────────────────────────────────────────────────────────────────────
class _ToastManager(QObject):
    _instance: Optional["_ToastManager"] = None

    # 설정
    MAX_VISIBLE          = 4          # 동시에 보이는 최대 개수
    MARGIN_TOP_PX        = 18         # 윈도우 우상단 여백
    MARGIN_RIGHT_PX      = 18
    GAP_PX               = 10         # 토스트 간 세로 간격
    SLIDE_DURATION_MS    = 260
    FADE_DURATION_MS     = 220
    DEDUPE_WINDOW_MS     = 250
    WARMUP_MS            = 3000       # 부팅 후 무음 (info/success 만)

    @classmethod
    def instance(cls) -> "_ToastManager":
        if cls._instance is None:
            cls._instance = _ToastManager()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._host: Optional[QWidget] = None
        self._visible: list[_ToastItem] = []
        self._queue: deque[tuple[str, str, int, QWidget]] = deque()
        self._app_start_ms = int(time.monotonic() * 1000)
        # debounce — DEDUPE_WINDOW_MS 안 같은 메시지 dedupe
        self._recent: list[tuple[str, int]] = []   # (signature, t_ms)
        # 윈도우 리사이즈 시 토스트 위치 갱신
        self._resync_timer = QTimer(self)
        self._resync_timer.setSingleShot(True)
        self._resync_timer.setInterval(40)
        self._resync_timer.timeout.connect(self._reposition_all)

    # ── public ────────────────────────────────────────────────
    def set_host(self, host: QWidget) -> None:
        """토스트가 띄워질 부모 위젯 (보통 MainWindow)."""
        # 기존 host 의 resize 이벤트 필터 해제는 단순화 — 새로 set 만
        self._host = host
        host.installEventFilter(self)

    def enqueue(self, message: str, kind: str = "info",
                duration_ms: int = 4000, parent: Optional[QWidget] = None) -> None:
        # 워밍업 — 부팅 후 워밍업 윈도우 안 info/success 무음
        now_ms = int(time.monotonic() * 1000)
        elapsed = now_ms - self._app_start_ms
        if elapsed < self.WARMUP_MS and kind in ("info", "success"):
            return

        # dedupe
        sig = f"{kind}|{message}"
        self._recent = [(s, t) for s, t in self._recent
                        if now_ms - t < self.DEDUPE_WINDOW_MS]
        if any(s == sig for s, _ in self._recent):
            return
        self._recent.append((sig, now_ms))

        host = parent or self._host
        if host is None:
            host = self._find_host()
        if host is None:
            return   # host 없음 — 무시

        # 큐에 적재
        self._queue.append((message, kind, duration_ms, host))
        self._pump()

    def _find_host(self) -> Optional[QWidget]:
        """top-level main window 자동 탐색."""
        for w in QApplication.topLevelWidgets():
            if w.isVisible() and w.__class__.__name__ == "MainWindow":
                self._host = w
                w.installEventFilter(self)
                return w
        return None

    # ── 큐 펌프 ──────────────────────────────────────────────
    def _pump(self) -> None:
        # MAX_VISIBLE 미만이면 큐에서 꺼내 표시
        while self._queue and len(self._visible) < self.MAX_VISIBLE:
            msg, kind, dur, host = self._queue.popleft()
            self._present(msg, kind, dur, host)

    def _present(self, message: str, kind: str, duration_ms: int,
                 host: QWidget) -> None:
        item = _ToastItem(message, kind, duration_ms, host)
        item.dismissed.connect(self._on_dismissed)
        item.adjustSize()
        # 시작 위치 — 화면 밖 (오른쪽)
        target_x, target_y = self._target_pos_for(len(self._visible), item)
        start_x = host.width() + 20
        item.move(start_x, target_y)
        item.show(); item.raise_()
        self._visible.append(item)
        # slide in 애니
        anim = QPropertyAnimation(item, b"pos", item)
        anim.setDuration(self.SLIDE_DURATION_MS)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(QPoint(start_x, target_y))
        anim.setEndValue(QPoint(target_x, target_y))
        anim.start()
        item._slide_anim = anim   # GC 방지 — instance 유지

    def _target_pos_for(self, index: int, item: QWidget) -> tuple[int, int]:
        """index 번째 토스트의 (target_x, target_y)."""
        host = self._host
        if host is None:
            return (0, 0)
        item.adjustSize()
        x = host.width() - item.width() - self.MARGIN_RIGHT_PX
        # 누적 height (앞선 토스트들)
        y = self.MARGIN_TOP_PX
        for i in range(index):
            if i < len(self._visible):
                y += self._visible[i].height() + self.GAP_PX
        return (x, y)

    def _reposition_all(self) -> None:
        """모든 visible 토스트 위치 재계산 (host resize / 토스트 dismiss 후)."""
        for i, it in enumerate(self._visible):
            tx, ty = self._target_pos_for(i, it)
            anim = QPropertyAnimation(it, b"pos", it)
            anim.setDuration(180)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.setEndValue(QPoint(tx, ty))
            anim.start()
            it._slide_anim = anim

    def _on_dismissed(self, item: _ToastItem) -> None:
        if item not in self._visible:
            try: item.deleteLater()
            except Exception: pass
            return
        # fade out 후 제거
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        eff = QGraphicsOpacityEffect(item)
        eff.setOpacity(1.0)
        item.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", item)
        anim.setDuration(self.FADE_DURATION_MS)
        anim.setStartValue(1.0); anim.setEndValue(0.0)
        def _cleanup():
            try:
                if item in self._visible:
                    self._visible.remove(item)
                item.hide(); item.deleteLater()
            finally:
                self._reposition_all()
                self._pump()
        anim.finished.connect(_cleanup)
        anim.start()
        item._fade_anim = anim

    # ── host resize 추적 ─────────────────────────────────────
    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent as _QE
        if obj is self._host and event.type() == _QE.Type.Resize:
            self._resync_timer.start()
        return super().eventFilter(obj, event)


# ──────────────────────────────────────────────────────────────────────
# LeeToast — public API (직접 호출 권장)
# ──────────────────────────────────────────────────────────────────────
class LeeToast:
    """전역 토스트 — 직접 호출 API (싱글톤 매니저 경유).

    Examples
    --------
    >>> LeeToast.show("保存しました", kind="success")
    >>> LeeToast.show("接続失敗", kind="error", duration=5000)
    >>> LeeToast.show("更新中...", kind="info", parent=some_widget)
    """

    @staticmethod
    def show(message: str, kind: ToastKind = "info",
             duration: int = 4000, parent: Optional[QWidget] = None) -> None:
        _ToastManager.instance().enqueue(message, kind, duration, parent)

    @staticmethod
    def set_host(host: QWidget) -> None:
        """토스트 부모 위젯 등록 (보통 MainWindow 가 시작 시 호출)."""
        _ToastManager.instance().set_host(host)


__all__ = ["LeeToast", "ToastKind"]
