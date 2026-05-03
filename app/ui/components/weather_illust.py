"""LeeWeatherIllust — 天気アニメーションイラスト (QPainter).

12 카테고리 지원 (모킹업 weather-illust.jsx 1:1 포팅):
    clear / mostly_clear / partly_cloudy / cloudy / foggy /
    drizzle / rainy / heavy_rain /
    light_snow / snowy / heavy_snow /
    stormy

Usage
-----
    from app.ui.components import LeeWeatherIllust

    illust = LeeWeatherIllust(parent)
    illust.set_category("rainy", is_dark=True)
    illust.setFixedSize(120, 80)

WMO 코드 → category 매핑은 외부에서 처리 (예: weather widget 의 _WMO_CATEGORY).
"""
from __future__ import annotations

import math
import random as _random

from PySide6.QtCore import Qt, QPointF, QRectF, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class LeeWeatherIllust(QWidget):
    """天気カードに重ねて表示するアニメーションイラスト (QPainter 직접 그리기).

    Categories
    ----------
    clear / mostly_clear / partly_cloudy / cloudy / foggy /
    drizzle / rainy / heavy_rain /
    light_snow / snowy / heavy_snow /
    stormy

    set_category(name, is_dark) 로 즉시 전환. 32ms tick 으로 자연스러운 애니메이션.
    """

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")
        self._category = "clear"
        self._is_dark  = True
        self._phase    = 0.0
        self._flash    = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(32)  # 약 30fps — CPU 부하 방지
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ── 외부 API ─────────────────────────────────────────────
    def set_category(self, category: str, is_dark: bool = True) -> None:
        self._category = category
        self._is_dark  = is_dark
        self._flash    = 0.0
        self.update()

    def category(self) -> str:
        return self._category

    # ── 내부 ─────────────────────────────────────────────────
    def _tick(self):
        if not self.isVisible():
            return
        self._phase = (self._phase + 0.015) % (2 * math.pi)
        if self._category == "stormy":
            if _random.random() < 0.04:
                self._flash = 1.0
            elif self._flash > 0:
                self._flash = max(0.0, self._flash - 0.25)
        self.update()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        self._timer.start()
        super().showEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        if w < 20 or h < 20:
            p.end(); return
        {
            "clear":         self._draw_clear,
            "mostly_clear":  self._draw_mostly_clear,
            "partly_cloudy": self._draw_partly_cloudy,
            "cloudy":        self._draw_cloudy,
            "foggy":         self._draw_foggy,
            "drizzle":       self._draw_drizzle,
            "rainy":         self._draw_rainy,
            "heavy_rain":    self._draw_heavy_rain,
            "light_snow":    self._draw_light_snow,
            "snowy":         self._draw_snowy,
            "heavy_snow":    self._draw_heavy_snow,
            "stormy":        self._draw_stormy,
        }.get(self._category, self._draw_clear)(p, w, h)
        p.end()

    # ── 공유 헬퍼 ────────────────────────────────────────────
    def _cloud(self, p: QPainter, cx: float, cy: float, r: float, color: QColor):
        p.setPen(QPen(Qt.PenStyle.NoPen))
        p.setBrush(QBrush(color))
        # 5개의 타원을 겹쳐 구름 모양
        for dx, dy, rx, ry in [
            ( 0.00,  0.00, 1.00, 0.70),
            (-0.60,  0.10, 0.60, 0.55),
            ( 0.60,  0.10, 0.65, 0.50),
            (-0.20, -0.40, 0.55, 0.50),
            ( 0.35, -0.28, 0.50, 0.45),
        ]:
            p.drawEllipse(QPointF(cx + dx * r, cy + dy * r), rx * r, ry * r)

    def _sun(self, p: QPainter, sx: float, sy: float, r: float,
             n_rays: int = 8, ray_len_fac: float = 0.90, alpha: int = 230):
        # 태양 맥박 (Pulse) — 살아있는 느낌
        pulse = 1.0 + 0.05 * math.sin(self._phase * 2)
        ri = (r + r * 0.25) * pulse
        ro = (r + r * ray_len_fac) * pulse
        ray_pen = QPen(QColor(255, 200, 50, 160), max(2.0, r * 0.18),
                       Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(ray_pen)
        for i in range(n_rays):
            a = self._phase * 1.5 + i * (2 * math.pi / n_rays)
            p.drawLine(
                QPointF(sx + ri * math.cos(a), sy + ri * math.sin(a)),
                QPointF(sx + ro * math.cos(a), sy + ro * math.sin(a)),
            )
        p.setBrush(QBrush(QColor(255, 215, 50, alpha)))
        p.setPen(QPen(QColor(255, 180, 30, 80), 1.5))
        p.drawEllipse(QPointF(sx, sy), r * pulse, r * pulse)

    # ── 카테고리별 그리기 ────────────────────────────────────
    def _draw_clear(self, p, w, h):
        r = min(w, h) * 0.18
        self._sun(p, w * 0.5, h * 0.5, r, n_rays=8, ray_len_fac=0.90)

    def _draw_mostly_clear(self, p, w, h):
        r = min(w, h) * 0.16
        self._sun(p, w * 0.42, h * 0.42, r, n_rays=8, ray_len_fac=0.75)
        cr    = min(w, h) * 0.14
        bob   = math.sin(self._phase * 0.6) * (h * 0.012)
        color = QColor(190, 195, 210, 180) if self._is_dark else QColor(170, 175, 185, 155)
        self._cloud(p, w * 0.67, h * 0.62 + bob, cr, color)

    def _draw_partly_cloudy(self, p, w, h):
        r = min(w, h) * 0.14
        self._sun(p, w * 0.35, h * 0.34, r, n_rays=6, ray_len_fac=0.65, alpha=190)
        cr    = min(w, h) * 0.22
        bob   = math.sin(self._phase * 0.5) * (h * 0.012)
        color = QColor(175, 180, 198, 210) if self._is_dark else QColor(145, 152, 165, 185)
        self._cloud(p, w * 0.55, h * 0.5 + bob, cr, color)

    def _draw_cloudy(self, p, w, h):
        r  = min(w, h) * 0.24
        sy = h * 0.5 + math.sin(self._phase * 0.5) * (h * 0.015)
        color = QColor(180, 185, 200, 200) if self._is_dark else QColor(120, 130, 145, 170)
        self._cloud(p, w * 0.5, sy, r, color)

    def _draw_foggy(self, p, w, h):
        p.setPen(QPen(Qt.PenStyle.NoPen))
        for i in range(4):
            t     = self._phase * 0.6 + i * 1.1
            alpha = 90 + int(40 * math.sin(t))
            color = QColor(160, 165, 178, alpha) if self._is_dark else QColor(140, 145, 158, alpha)
            p.setBrush(QBrush(color))
            lh = h * 0.09
            ox = math.sin(self._phase * 0.5 + i * 0.9) * (w * 0.03)
            y  = h * 0.20 + i * (h * 0.18) + math.sin(t) * (h * 0.01)
            p.drawRoundedRect(QRectF(w * 0.05 + ox, y, w * 0.90, lh), lh / 2, lh / 2)

    def _draw_rain_base(self, p, w, h, n, drop_alpha, cloud_alpha,
                        drop_scale=1.0, cloud_dark_color=(100, 120, 160), cloud_y_frac=0.36):
        cx      = w * 0.5
        r       = min(w, h) * 0.22
        cloud_y = h * cloud_y_frac
        cd = cloud_dark_color
        color   = QColor(cd[0], cd[1], cd[2], cloud_alpha) if self._is_dark \
                  else QColor(max(0, cd[0]-15), max(0, cd[1]-15), max(0, cd[2]-15), int(cloud_alpha * 0.86))
        self._cloud(p, cx, cloud_y, r, color)
        span = w * 0.55
        fall = h - cloud_y - r * 0.6
        dlen = h * 0.07 * drop_scale
        dw   = max(1.5, r * 0.07) * drop_scale
        for i in range(n):
            t    = (self._phase * 1.5 + i * (2 * math.pi / n)) % (2 * math.pi)
            prog = t / (2 * math.pi)
            opacity_factor = math.sin(prog * math.pi)
            current_alpha  = int(drop_alpha * opacity_factor)
            drop_pen = QPen(QColor(100, 160, 225, current_alpha), dw,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            p.setPen(drop_pen)
            x = cx + ((i / max(n - 1, 1)) - 0.5) * span
            y = cloud_y + r * 0.55 + prog * fall
            p.drawLine(QPointF(x, y), QPointF(x - dlen * 0.2, y + dlen))

    def _draw_drizzle(self, p, w, h):
        self._draw_rain_base(p, w, h, n=5, drop_alpha=130, cloud_alpha=175,
                             drop_scale=0.75, cloud_dark_color=(110, 125, 155))

    def _draw_rainy(self, p, w, h):
        self._draw_rain_base(p, w, h, n=9, drop_alpha=200, cloud_alpha=210)

    def _draw_heavy_rain(self, p, w, h):
        self._draw_rain_base(p, w, h, n=14, drop_alpha=230, cloud_alpha=235,
                             drop_scale=1.25, cloud_dark_color=(70, 85, 130),
                             cloud_y_frac=0.30)

    def _draw_snow_base(self, p, w, h, n, alpha, cloud_alpha,
                        flake_scale=1.0, cloud_dark_color=(140, 155, 175)):
        cx      = w * 0.5
        r       = min(w, h) * 0.22
        cloud_y = h * 0.34
        cd = cloud_dark_color
        color   = QColor(cd[0], cd[1], cd[2], cloud_alpha) if self._is_dark \
                  else QColor(max(0, cd[0]-25), max(0, cd[1]-25), max(0, cd[2]-25), int(cloud_alpha * 0.85))
        self._cloud(p, cx, cloud_y, r, color)
        span = w * 0.60
        fr   = max(2.0, min(w, h) * 0.025 * flake_scale)
        fall = h - cloud_y - r * 0.5
        p.setPen(QPen(Qt.PenStyle.NoPen))
        p.setBrush(QBrush(QColor(205, 225, 248, alpha)))
        for i in range(n):
            t    = (self._phase * 1.0 + i * (2 * math.pi / n)) % (2 * math.pi)
            prog = t / (2 * math.pi)
            opacity_factor = math.sin(prog * math.pi)
            current_alpha  = int(alpha * opacity_factor)
            p.setBrush(QBrush(QColor(205, 225, 248, current_alpha)))
            x = cx + ((i / max(n - 1, 1)) - 0.5) * span \
                + math.sin(self._phase * 2.0 + i * 3) * (w * 0.035)
            y = cloud_y + r * 0.5 + prog * fall
            p.drawEllipse(QPointF(x, y), fr, fr)

    def _draw_light_snow(self, p, w, h):
        self._draw_snow_base(p, w, h, n=5, alpha=175, cloud_alpha=175,
                             flake_scale=0.8, cloud_dark_color=(150, 162, 180))

    def _draw_snowy(self, p, w, h):
        self._draw_snow_base(p, w, h, n=8, alpha=215, cloud_alpha=200)

    def _draw_heavy_snow(self, p, w, h):
        self._draw_snow_base(p, w, h, n=13, alpha=230, cloud_alpha=225,
                             flake_scale=1.2, cloud_dark_color=(120, 135, 158))

    def _draw_stormy(self, p, w, h):
        cx      = w * 0.5
        r       = min(w, h) * 0.24
        cloud_y = h * 0.30
        color   = QColor(55, 60, 78, 230) if self._is_dark else QColor(75, 80, 100, 210)
        self._cloud(p, cx, cloud_y, r, color)
        bw   = w * 0.085
        by0  = cloud_y + r * 0.35
        bym  = h * 0.60
        by1  = h * 0.82
        path = QPainterPath()
        path.moveTo(cx + bw,         by0)
        path.lineTo(cx - bw,         bym)
        path.lineTo(cx + bw * 0.30,  bym)
        path.lineTo(cx - bw * 1.30,  by1)
        if self._flash > 0.15:
            gp = QPen(QColor(255, 255, 200, int(70 * self._flash)),
                      max(7.0, bw * 1.8))
            gp.setStyle(Qt.PenStyle.SolidLine)
            gp.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(gp)
            p.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            p.drawPath(path)
        lp = QPen(QColor(255, 235, 50, int(200 + 55 * self._flash)),
                  max(2.5, bw * 0.40))
        lp.setStyle(Qt.PenStyle.SolidLine)
        lp.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(lp)
        p.drawPath(path)


# WMO 코드 → 카테고리 표준 매핑 (외부에서 import 가능)
WMO_CATEGORY: dict[int, str] = {
    0:  "clear",
    1:  "mostly_clear",
    2:  "partly_cloudy",
    3:  "cloudy",
    45: "foggy",        48: "foggy",
    51: "drizzle",      53: "drizzle",      55: "drizzle",
    56: "drizzle",      57: "drizzle",
    61: "rainy",        63: "rainy",        65: "heavy_rain",
    66: "rainy",        67: "heavy_rain",
    71: "light_snow",   73: "snowy",        75: "heavy_snow",
    77: "light_snow",
    80: "rainy",        81: "rainy",        82: "heavy_rain",
    85: "snowy",        86: "heavy_snow",
    95: "stormy",       96: "stormy",       99: "stormy",
}


def category_for_wmo(code: int) -> str:
    """WMO 코드 → 일러스트 카테고리. 미지원 코드는 'clear'."""
    return WMO_CATEGORY.get(int(code), "clear")


def qss(tokens: dict) -> str:
    """LeeWeatherIllust 는 paintEvent 기반이라 별도 QSS 없음."""
    return ""
