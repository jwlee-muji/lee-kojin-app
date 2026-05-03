"""LeeSkeleton — 데이터 로딩 동안 표시되는 shimmer placeholder.

사용법:
    sk = LeeSkeleton(kind="card", parent=card)
    sk.setGeometry(0, 0, card.width(), card.height())
    sk.start()              # shimmer animation 시작
    # ... 데이터 도착
    sk.stop()               # 자동 hide

variant:
    "card"   — 회색 bar 3개 (제목 / 본문 / footer)
    "line"   — 단일 라인 (텍스트 1줄 placeholder)
    "avatar" — 원형 (아바타 자리)
    "block"  — 단순 사각 블록

shimmer:
    배경 위로 밝은 그라데이션 띠가 좌→우로 1.6초 loop 이동.
    setAttribute(WA_TransparentForMouseEvents) 로 클릭 통과.
"""
from __future__ import annotations

from typing import Literal

from PySide6.QtCore import (
    Property, QPropertyAnimation, QRect, Qt, QEvent, QObject,
)
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QFrame, QWidget


SkeletonKind = Literal["card", "line", "avatar", "block"]


class LeeSkeleton(QFrame):
    """전역 스켈레톤 로더 — shimmer 그라데이션 좌→우 이동.

    Parameters
    ----------
    kind : "card" | "line" | "avatar" | "block"
        placeholder 모양
    width, height : int (옵션)
        고정 크기 — 0 이면 부모/setGeometry 에 맡김
    parent : QWidget
    """

    SHIMMER_MS = 1600

    def __init__(self, *, kind: SkeletonKind = "card",
                 width: int = 0, height: int = 0, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._is_dark = True
        self._shimmer_pos: float = -0.3   # -0.3 ~ 1.3 — 그라데이션 띠의 X 위치 (정규화)
        self.setObjectName("leeSkeleton")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        if width > 0 and height > 0:
            self.setFixedSize(width, height)
        self.setMinimumSize(20, 20)

        self._anim = QPropertyAnimation(self, b"shimmer_pos", self)
        self._anim.setDuration(self.SHIMMER_MS)
        self._anim.setStartValue(-0.3)
        self._anim.setEndValue(1.3)
        self._anim.setLoopCount(-1)

    # ── public ────────────────────────────────────────────────
    def start(self) -> None:
        self.show()
        self._anim.start()

    def stop(self) -> None:
        self._anim.stop()
        self.hide()

    def set_kind(self, kind: SkeletonKind) -> None:
        self._kind = kind
        self.update()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self.update()

    # ── shimmer pos property ──────────────────────────────────
    def _get_shimmer_pos(self) -> float:
        return self._shimmer_pos

    def _set_shimmer_pos(self, v: float) -> None:
        self._shimmer_pos = float(v)
        self.update()

    shimmer_pos = Property(float, _get_shimmer_pos, _set_shimmer_pos)

    # ── paint ─────────────────────────────────────────────────
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            p.end(); return

        d = self._is_dark
        bg_base   = QColor(255, 255, 255, 16) if d else QColor(11, 18, 32, 14)
        bg_bar    = QColor(255, 255, 255, 24) if d else QColor(11, 18, 32, 22)
        # shimmer 띠 색상 — 살짝 밝은 highlight
        sh_mid    = QColor(255, 255, 255, 70) if d else QColor(255, 255, 255, 130)

        # ── 1) 모양별 base placeholder ─────────────────────
        p.setPen(Qt.NoPen)

        if self._kind == "card":
            # 카드 풀 background
            p.setBrush(bg_base)
            p.drawRoundedRect(0, 0, w, h, 14, 14)
            # 회색 bar 3개 (제목 / 본문 / footer)
            p.setBrush(bg_bar)
            p.drawRoundedRect(20, 24, min(160, w - 40), 14, 6, 6)
            p.drawRoundedRect(20, 50, min(220, w - 40), 10, 5, 5)
            if h > 80:
                p.drawRoundedRect(20, h - 36, min(120, w - 40), 10, 5, 5)
        elif self._kind == "line":
            # 단일 라인
            p.setBrush(bg_bar)
            p.drawRoundedRect(0, 0, w, h, h // 2, h // 2)
        elif self._kind == "avatar":
            # 원형
            p.setBrush(bg_bar)
            d_min = min(w, h)
            p.drawEllipse((w - d_min) // 2, (h - d_min) // 2, d_min, d_min)
        else:   # "block"
            p.setBrush(bg_bar)
            p.drawRoundedRect(0, 0, w, h, 8, 8)

        # ── 2) shimmer 그라데이션 띠 ───────────────────────
        # 좌→우로 이동하는 좁은 highlight band
        band_x = self._shimmer_pos * w
        band_w = max(60, w * 0.35)
        grad = QLinearGradient(band_x - band_w / 2, 0, band_x + band_w / 2, 0)
        transparent = QColor(sh_mid); transparent.setAlpha(0)
        grad.setColorAt(0.0, transparent)
        grad.setColorAt(0.5, sh_mid)
        grad.setColorAt(1.0, transparent)
        p.setBrush(grad)
        # round-clipped: 카드 모양에 맞춰 클립
        if self._kind == "card":
            p.setClipRect(QRect(0, 0, w, h))
            p.drawRoundedRect(0, 0, w, h, 14, 14)
        elif self._kind == "line":
            p.drawRoundedRect(0, 0, w, h, h // 2, h // 2)
        elif self._kind == "avatar":
            d_min = min(w, h)
            p.drawEllipse((w - d_min) // 2, (h - d_min) // 2, d_min, d_min)
        else:
            p.drawRoundedRect(0, 0, w, h, 8, 8)
        p.end()


def install_skeleton_overlay(target: QWidget, kind: SkeletonKind = "card") -> LeeSkeleton:
    """target 위에 LeeSkeleton 오버레이 생성 + auto-resize 설치 후 반환.

    Skeleton 이 ``deleteLater()`` 로 제거되면 event filter 도 자동으로 분리.

    Usage:
        self._sk = install_skeleton_overlay(self._chart_area)
        # ... 첫 데이터 도착
        self._sk.stop(); self._sk.deleteLater(); self._sk = None
    """
    sk = LeeSkeleton(kind=kind, parent=target)
    sk.setGeometry(0, 0, max(target.width(), 20), max(target.height(), 20))

    class _ResizeFilter(QObject):
        def eventFilter(self_filter, obj, ev):
            if obj is target and ev.type() == QEvent.Resize:
                try:
                    sk.setGeometry(0, 0, target.width(), target.height())
                except RuntimeError:
                    # sk 가 deleteLater() 로 제거됨 — filter 도 자기 분리
                    try: target.removeEventFilter(self_filter)
                    except RuntimeError: pass
            return False

    f = _ResizeFilter(target)
    target.installEventFilter(f)
    sk._auto_resize_filter = f   # GC 방지

    # sk 가 destroyed 되면 filter 도 자동 제거 (cleanup 이중 안전망)
    def _on_sk_destroyed(*_args) -> None:
        try: target.removeEventFilter(f)
        except RuntimeError: pass
    sk.destroyed.connect(_on_sk_destroyed)

    sk.start()
    return sk


__all__ = ["LeeSkeleton", "SkeletonKind", "install_skeleton_overlay"]
