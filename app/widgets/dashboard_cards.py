import math
import random as _random
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QPushButton,
)
from PySide6.QtCore import (
    Qt, QTimer, Signal, QPropertyAnimation, QEasingCurve,
    Property, QRectF, QPointF,
)
from PySide6.QtGui import QColor, QCursor, QPainter, QPen, QBrush, QPainterPath
from app.ui.common import get_tinted_pixmap
from app.ui.theme import Typography, UIColors
from app.core.i18n import tr


_WMO_CATEGORY: dict[int, str] = {
    0:  "clear",
    1:  "mostly_clear",
    2:  "partly_cloudy",
    3:  "cloudy",
    45: "foggy",    48: "foggy",
    51: "drizzle",  53: "drizzle",  55: "drizzle",
    56: "drizzle",  57: "drizzle",
    61: "rainy",    63: "rainy",    65: "heavy_rain",
    66: "rainy",    67: "rainy",
    71: "light_snow", 73: "snowy",  75: "heavy_snow", 77: "snowy",
    80: "rainy",    81: "rainy",    82: "heavy_rain",
    85: "light_snow", 86: "snowy",
    95: "stormy",   96: "stormy",   99: "stormy",
}
_WMO_BG_DARK = {
    "clear":        "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #3a2e00,stop:1 #14161C)",
    "mostly_clear": "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #302800,stop:1 #14161C)",
    "partly_cloudy":"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #2e2a18,stop:1 #14161C)",
    "cloudy":       "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #2a2a2a,stop:1 #14161C)",
    "foggy":        "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #303030,stop:1 #14161C)",
    "drizzle":      "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0d1e30,stop:1 #14161C)",
    "rainy":        "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0a1e3a,stop:1 #14161C)",
    "heavy_rain":   "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #051228,stop:1 #14161C)",
    "light_snow":   "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #1e2a35,stop:1 #14161C)",
    "snowy":        "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #1a2530,stop:1 #14161C)",
    "heavy_snow":   "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #141e2a,stop:1 #14161C)",
    "stormy":       "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #1a1030,stop:1 #14161C)",
}
_WMO_BG_LIGHT = {
    "clear":        "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #fffde7,stop:1 #ffffff)",
    "mostly_clear": "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #fff8d6,stop:1 #ffffff)",
    "partly_cloudy":"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #fdf5e0,stop:1 #f5f5f5)",
    "cloudy":       "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #f5f5f5,stop:1 #ffffff)",
    "foggy":        "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #eeeeee,stop:1 #ffffff)",
    "drizzle":      "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #eaf4fc,stop:1 #ffffff)",
    "rainy":        "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #e3f2fd,stop:1 #ffffff)",
    "heavy_rain":   "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #d0e8f8,stop:1 #ffffff)",
    "light_snow":   "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #eef5fa,stop:1 #ffffff)",
    "snowy":        "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #e8f4f8,stop:1 #ffffff)",
    "heavy_snow":   "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ddeef8,stop:1 #ffffff)",
    "stormy":       "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ede7f6,stop:1 #ffffff)",
}


def _high_alert_color(val: float, is_dark: bool,
                      red_thresh: float = 40.0, orange_thresh: float = 20.0) -> str | None:
    """値が高いほど危険な指標のアラート色 (インバランス・スポット価格等)。
    디자인 토큰 c_bad / c_warn 사용 (라이트 모드는 약간 더 진한 변형)."""
    if val >= red_thresh:
        return "#FF453A" if is_dark else "#D32F2F"
    if val >= orange_thresh:
        return "#FF9F0A" if is_dark else "#E65100"
    return None


def _low_alert_color(val: float, is_dark: bool,
                     red_thresh: float = 8.0, orange_thresh: float = 10.0) -> str | None:
    """値が低いほど危険な指標のアラート色 (電力予備率等)。
    디자인 토큰 c_bad / c_warn 사용."""
    if val <= red_thresh:
        return "#FF453A" if is_dark else "#D32F2F"
    if val <= orange_thresh:
        return "#FF9F0A" if is_dark else "#E65100"
    return None


class _WeatherIllust(QWidget):
    """天気カード上に重ねて表示するアニメーションイラスト。QPainter で直接描画する。"""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")
        self._category = "clear"
        self._is_dark  = True
        self._phase    = 0.0
        self._flash    = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(32)  # CPU 부하 및 튕김 방지를 위해 안정적인 30fps로 조정
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_category(self, category: str, is_dark: bool):
        self._category = category
        self._is_dark  = is_dark
        self._flash    = 0.0
        self.update()

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

    # ── 共有ヘルパー ─────────────────────────────────────────────────────────

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        self._timer.start()
        super().showEvent(event)

    def _cloud(self, p: QPainter, cx: float, cy: float, r: float, color: QColor):
        p.setPen(QPen(Qt.PenStyle.NoPen))
        p.setBrush(QBrush(color))
        # 5개의 타원을 겹쳐 구름 모양을 만듭니다.
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
        # 태양의 맥박(Pulse) 효과 추가로 살아있는 느낌 부여
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

    # ── 天気別描画 ───────────────────────────────────────────────────────────

    def _draw_clear(self, p: QPainter, w: float, h: float):
        r = min(w, h) * 0.18
        self._sun(p, w * 0.5, h * 0.42, r, n_rays=8, ray_len_fac=0.90)

    def _draw_mostly_clear(self, p: QPainter, w: float, h: float):
        """太陽 (やや左寄り) + 右下に小さな雲。"""
        r = min(w, h) * 0.16
        self._sun(p, w * 0.42, h * 0.38, r, n_rays=8, ray_len_fac=0.75)
        cr    = min(w, h) * 0.14
        bob   = math.sin(self._phase * 0.6) * (h * 0.012)
        color = QColor(190, 195, 210, 180) if self._is_dark else QColor(170, 175, 185, 155)
        self._cloud(p, w * 0.67, h * 0.58 + bob, cr, color)

    def _draw_partly_cloudy(self, p: QPainter, w: float, h: float):
        """太陽 (左上、半分隠れ) + 大きな雲が前面に重なる。"""
        r = min(w, h) * 0.14
        self._sun(p, w * 0.35, h * 0.34, r, n_rays=6, ray_len_fac=0.65, alpha=190)
        cr    = min(w, h) * 0.22
        bob   = math.sin(self._phase * 0.5) * (h * 0.012)
        color = QColor(175, 180, 198, 210) if self._is_dark else QColor(145, 152, 165, 185)
        self._cloud(p, w * 0.55, h * 0.46 + bob, cr, color)

    def _draw_cloudy(self, p: QPainter, w: float, h: float):
        r  = min(w, h) * 0.24
        sy = h * 0.44 + math.sin(self._phase * 0.5) * (h * 0.015)
        color = QColor(180, 185, 200, 200) if self._is_dark else QColor(120, 130, 145, 170)
        self._cloud(p, w * 0.5, sy, r, color)

    def _draw_foggy(self, p: QPainter, w: float, h: float):
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

    def _draw_rain_base(self, p: QPainter, w: float, h: float,
                        n: int, drop_alpha: int, cloud_alpha: int,
                        drop_scale: float = 1.0, cloud_dark_color: tuple = (100, 120, 160),
                        cloud_y_frac: float = 0.33):
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
            
            # 빗방울이 위아래 끝에서 부드럽게 사라지도록 페이드 알파 적용
            opacity_factor = math.sin(prog * math.pi)
            current_alpha = int(drop_alpha * opacity_factor)
            drop_pen = QPen(QColor(100, 160, 225, current_alpha), dw,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            p.setPen(drop_pen)
            
            x    = cx + ((i / max(n - 1, 1)) - 0.5) * span
            y    = cloud_y + r * 0.55 + prog * fall
            p.drawLine(QPointF(x, y), QPointF(x - dlen * 0.2, y + dlen))

    def _draw_drizzle(self, p: QPainter, w: float, h: float):
        self._draw_rain_base(p, w, h, n=5, drop_alpha=130, cloud_alpha=175,
                             drop_scale=0.75, cloud_dark_color=(110, 125, 155))

    def _draw_rainy(self, p: QPainter, w: float, h: float):
        self._draw_rain_base(p, w, h, n=9, drop_alpha=200, cloud_alpha=210)

    def _draw_heavy_rain(self, p: QPainter, w: float, h: float):
        self._draw_rain_base(p, w, h, n=14, drop_alpha=230, cloud_alpha=235,
                             drop_scale=1.25, cloud_dark_color=(70, 85, 130),
                             cloud_y_frac=0.28)

    def _draw_snow_base(self, p: QPainter, w: float, h: float,
                        n: int, alpha: int, cloud_alpha: int,
                        flake_scale: float = 1.0, cloud_dark_color: tuple = (140, 155, 175)):
        cx      = w * 0.5
        r       = min(w, h) * 0.22
        cloud_y = h * 0.31
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
            
            # 눈송이의 부드러운 페이드 인/아웃 및 자연스러운 흔들림 강화
            opacity_factor = math.sin(prog * math.pi)
            current_alpha = int(alpha * opacity_factor)
            p.setBrush(QBrush(QColor(205, 225, 248, current_alpha)))
            
            x    = cx + ((i / max(n - 1, 1)) - 0.5) * span \
                   + math.sin(self._phase * 2.0 + i * 3) * (w * 0.035)
            y    = cloud_y + r * 0.5 + prog * fall
            p.drawEllipse(QPointF(x, y), fr, fr)

    def _draw_light_snow(self, p: QPainter, w: float, h: float):
        self._draw_snow_base(p, w, h, n=5, alpha=175, cloud_alpha=175,
                             flake_scale=0.8, cloud_dark_color=(150, 162, 180))

    def _draw_snowy(self, p: QPainter, w: float, h: float):
        self._draw_snow_base(p, w, h, n=8, alpha=215, cloud_alpha=200)

    def _draw_heavy_snow(self, p: QPainter, w: float, h: float):
        self._draw_snow_base(p, w, h, n=13, alpha=230, cloud_alpha=225,
                             flake_scale=1.2, cloud_dark_color=(120, 135, 158))

    def _draw_stormy(self, p: QPainter, w: float, h: float):
        cx      = w * 0.5
        r       = min(w, h) * 0.24
        cloud_y = h * 0.28
        color   = QColor(55, 60, 78, 230) if self._is_dark else QColor(75, 80, 100, 210)
        self._cloud(p, cx, cloud_y, r, color)
        bw   = w * 0.085
        by0  = cloud_y + r * 0.35
        bym  = h * 0.56
        by1  = h * 0.78
        path = QPainterPath()
        path.moveTo(cx + bw,         by0)
        path.lineTo(cx - bw,         bym)
        path.lineTo(cx + bw * 0.30,  bym)
        path.lineTo(cx - bw * 1.30,  by1)
        if self._flash > 0.15:
            gp = QPen(QColor(255, 255, 200, int(70 * self._flash)),
                      max(7.0, bw * 1.8), Qt.PenStyle.SolidLine, Qt.PenJoinStyle.RoundJoin)
            p.setPen(gp)
            p.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            p.drawPath(path)
        lp = QPen(QColor(255, 235, 50, int(200 + 55 * self._flash)),
                  max(2.5, bw * 0.40), Qt.PenStyle.SolidLine, Qt.PenJoinStyle.RoundJoin)
        p.setPen(lp)
        p.drawPath(path)


class SummaryCard(QFrame):
    clicked = Signal()

    def __init__(self, title, icon_name, color):
        super().__init__()
        self.is_dark = True
        self.setCursor(Qt.PointingHandCursor)
        self.card_color = color
        self.icon_name = icon_name
        self._val_color = None
        self._has_animated = False  # 初回のみアニメーションを実行するためのフラグ
        self._hover_offset = 0.0    # ホバーアニメーション用
        self._card_bg_css = ""      # 天気カード用背景グラデーション
        self._illust: _WeatherIllust | None = None
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        header_layout = QHBoxLayout()
        self.icon_lbl = QLabel()

        title_lbl = QLabel(title)
        self.title_lbl = title_lbl

        header_layout.addWidget(self.icon_lbl)
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()

        self.value_lbl = QLabel("--")
        self.value_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.sub_lbl = QLabel(tr("データ待機中..."))
        self.sub_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout.addLayout(header_layout)
        layout.addStretch()
        layout.addWidget(self.value_lbl)
        layout.addWidget(self.sub_lbl)

        self._apply_style()

        # ドロップシャドウの追加でカードを浮き上がらせる
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(15)
        self.shadow.setOffset(0, 4)
        self.setGraphicsEffect(self.shadow)

        # ホバーアニメーションの設定
        self._hover_anim = QPropertyAnimation(self, b"hoverOffset")
        self._hover_anim.setDuration(150)
        self._hover_anim.setEasingCurve(QEasingCurve.OutQuad)

        # エフェクト参照を None で初期化 (set_loading() 呼び出し前に必ず行う)
        self._skel_effect: QGraphicsOpacityEffect | None = None
        self._skel_anim: QPropertyAnimation | None = None
        self._fade_opacity_effect: QGraphicsOpacityEffect | None = None
        self._fade_out_anim: QPropertyAnimation | None = None
        self._fade_in_anim: QPropertyAnimation | None = None

        # 初期化時に1回だけスケルトンローディングを開始
        self.set_loading(True)

    # ------------------------------------------------------------------
    # エフェクトライフサイクル管理ヘルパー
    # ------------------------------------------------------------------

    def _clear_skel(self):
        """スケルトンエフェクト・アニメーションを停止し参照をクリアします。"""
        if self._skel_anim is not None:
            self._skel_anim.stop()
            self._skel_anim.deleteLater()
        self._skel_effect = None
        self._skel_anim = None

    def _clear_fade(self):
        """フェードエフェクト・アニメーションを停止し参照をクリアします。"""
        if self._fade_out_anim is not None:
            self._fade_out_anim.stop()
            self._fade_out_anim.deleteLater()
        if self._fade_in_anim is not None:
            self._fade_in_anim.stop()
            self._fade_in_anim.deleteLater()
        self._fade_opacity_effect = None
        self._fade_out_anim = None
        self._fade_in_anim = None

    def set_loading(self, is_loading: bool):
        """스켈레톤(Skeleton) 로딩 애니메이션 활성화/비활성화"""
        if is_loading:
            self.value_lbl.setText("----")
            self.sub_lbl.setText(tr("データ取得中..."))

            if self._skel_anim is None:
                self._skel_effect = QGraphicsOpacityEffect()
                self._skel_anim = QPropertyAnimation(self._skel_effect, b"opacity", self)
                self._skel_anim.setDuration(800)
                self._skel_anim.setStartValue(0.3)
                self._skel_anim.setEndValue(1.0)
                self._skel_anim.setLoopCount(-1)

            # フェードエフェクトが現在適用中なら、setGraphicsEffect() で Qt が削除する前に参照をクリア
            if self._fade_opacity_effect is not None and self.value_lbl.graphicsEffect() is self._fade_opacity_effect:
                self._clear_fade()

            self.value_lbl.setGraphicsEffect(self._skel_effect)
            self._skel_anim.start()
        else:
            if self._fade_out_anim is not None:
                self._fade_out_anim.stop()
            if self._fade_in_anim is not None:
                self._fade_in_anim.stop()
            if self._skel_anim is not None:
                self._skel_anim.stop()
            # スケルトンエフェクトが現在適用中の時のみ解除
            if self._skel_effect is not None and self.value_lbl.graphicsEffect() is self._skel_effect:
                self.value_lbl.setGraphicsEffect(None)
                self._clear_skel()  # Qt がエフェクトを削除したため参照をクリア

    def set_value(self, val_str, sub_str, val_color=None, target_val=None, format_str=None, animate_fade=False):
        self.set_loading(False)  # 값이 설정되면 스켈레톤 중지
        if animate_fade:
            self._next_val_str = val_str
            self._next_sub_str = sub_str
            self._next_val_color = val_color
            self._start_fade_out()
            return

        self._val_color = val_color
        self.sub_lbl.setText(sub_str)
        self._apply_style()

        # 目標値とフォーマットが渡され、かつ未アニメーションの場合のみ実行
        if target_val is not None and format_str is not None and not self._has_animated:
            self._has_animated = True
            self._anim_target = float(target_val)
            self._anim_format = format_str
            self._anim_step = 0
            self._anim_max_steps = 60  # 約1秒かけてカウントアップ (60フレーム)

            if not hasattr(self, '_anim_timer'):
                self._anim_timer = QTimer(self)
                self._anim_timer.timeout.connect(self._on_anim_step)
            self._anim_timer.start(16)
        else:
            self.value_lbl.setText(val_str)

    def _on_anim_step(self):
        self._anim_step += 1
        progress = self._anim_step / self._anim_max_steps
        # Ease-Out Cubic: 減速しながら滑らかに目標値へ近づく
        ease = 1 - pow(1 - progress, 3)
        current_val = self._anim_target * ease

        self.value_lbl.setText(self._anim_format.format(current_val))

        if self._anim_step >= self._anim_max_steps:
            self._anim_timer.stop()
            self.value_lbl.setText(self._anim_format.format(self._anim_target))

    def _start_fade_out(self):
        if self._fade_out_anim is None:
            self._fade_opacity_effect = QGraphicsOpacityEffect()
            self._fade_out_anim = QPropertyAnimation(self._fade_opacity_effect, b"opacity", self)
            self._fade_out_anim.setDuration(180)
            self._fade_out_anim.setEasingCurve(QEasingCurve.InQuad)
            self._fade_out_anim.finished.connect(self._on_fade_out_done)
            self._fade_in_anim = QPropertyAnimation(self._fade_opacity_effect, b"opacity", self)
            self._fade_in_anim.setDuration(180)
            self._fade_in_anim.setEasingCurve(QEasingCurve.OutQuad)

        # スケルトンエフェクトが現在適用中なら、setGraphicsEffect() で Qt が削除する前に参照をクリア
        if self._skel_anim is not None:
            if self.value_lbl.graphicsEffect() is self._skel_effect:
                self._clear_skel()

        if self.value_lbl.graphicsEffect() is not self._fade_opacity_effect:
            self.value_lbl.setGraphicsEffect(self._fade_opacity_effect)

        self._fade_in_anim.stop()
        self._fade_out_anim.setStartValue(self._fade_opacity_effect.opacity())
        self._fade_out_anim.setEndValue(0.0)
        self._fade_out_anim.start()

    def _on_fade_out_done(self):
        self.set_value(self._next_val_str, self._next_sub_str, self._next_val_color)
        self._fade_in_anim.setStartValue(0.0)
        self._fade_in_anim.setEndValue(1.0)
        self._fade_in_anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def enterEvent(self, event):
        # 애니메이션 중복 트리거 및 큐 꼬임 방지
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_offset)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        # 애니메이션 중복 트리거 및 큐 꼬임 방지
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_offset)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        super().leaveEvent(event)

    @Property(float)
    def hoverOffset(self):
        return self._hover_offset

    @hoverOffset.setter
    def hoverOffset(self, val):
        self._hover_offset = val
        if hasattr(self, 'shadow'):
            self.shadow.setOffset(0, 4 + val * 6)
            self.shadow.setBlurRadius(15 + val * 12)
            base_alpha = 120 if self.is_dark else 40
            target_alpha = 180 if self.is_dark else 80
            current_alpha = int(base_alpha + (target_alpha - base_alpha) * val)
            self.shadow.setColor(QColor(0, 0, 0, current_alpha))

    def set_card_bg(self, css: str):
        """天気タイプに応じた背景グラデーションを適用する。空文字でリセット。"""
        self._card_bg_css = css
        self._apply_style()

    def set_weather_illust(self, category: str, is_dark: bool):
        """天気イラストウィジェットを表示・更新する。"""
        if self._illust is None:
            self._illust = _WeatherIllust(self)
        self._illust.set_category(category, is_dark)
        self._illust.raise_()
        self._reposition_illust()
        self._illust.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_illust()

    def _reposition_illust(self):
        if not self._illust:
            return
        try:
            val_top = self.value_lbl.mapTo(self, self.value_lbl.rect().topLeft()).y()
        except RuntimeError:
            return
        top = 54   # ヘッダー下端 (マージン20 + アイコン行 ~34px)
        w   = max(10, self.width()  - 40)
        h   = max(10, val_top - top - 8)
        self._illust.setGeometry(20, top, w, h)

    def set_theme(self, is_dark):
        self.is_dark = is_dark
        # Dynamic Property 상태를 Qt 스타일 엔진에 전파
        self.setProperty("theme", "dark" if is_dark else "light")
        self.style().unpolish(self)
        self.style().polish(self)
        self._apply_style()

    def _apply_style(self):
        tc = UIColors.text_default(self.is_dark)

        try:
            self.icon_lbl.setPixmap(get_tinted_pixmap(f":/img/{self.icon_name}.svg", self.is_dark))
            self.icon_lbl.setStyleSheet("background: transparent;")
        except Exception:
            self.icon_lbl.setText(self.icon_name)
            self.icon_lbl.setStyleSheet("font-size: 26px; background: transparent;")

        # border-left はインスタンス固有。背景は _card_bg_css がある場合のみ上書き。
        bg_line = f" background: {self._card_bg_css} !important;" if self._card_bg_css else ""
        self.setStyleSheet(
            f"SummaryCard {{ border-left: 6px solid {self.card_color};{bg_line} }}"
        )
        self.title_lbl.setStyleSheet(f"font-size: {Typography.H2}; font-weight: bold; background: transparent; color: {UIColors.text_secondary(self.is_dark)};")
        self.sub_lbl.setStyleSheet(f"font-size: {Typography.BUTTON}; font-weight: bold; background: transparent; color: {UIColors.TEXT_MUTED};")
        vc = self._val_color if self._val_color else tc
        self.value_lbl.setStyleSheet(f"font-size: {Typography.DISPLAY}; font-weight: bold; background: transparent; color: {vc};")

        if hasattr(self, 'shadow'):
            self.shadow.setOffset(0, 4 + self._hover_offset * 6)
            self.shadow.setBlurRadius(15 + self._hover_offset * 12)
            base_alpha = 120 if self.is_dark else 40
            target_alpha = 180 if self.is_dark else 80
            current_alpha = int(base_alpha + (target_alpha - base_alpha) * self._hover_offset)
            self.shadow.setColor(QColor(0, 0, 0, current_alpha))


class SpotDashCard(QFrame):
    """JEPX スポット価格カード — 当日 / 翌日の地域別平均を循環表示"""

    clicked      = Signal()
    mode_changed = Signal(str)   # 'today' | 'tomorrow'

    def __init__(self):
        super().__init__()
        self.is_dark = True
        self._date_mode = 'today'
        self._hover_offset = 0.0
        self._val_color: str | None = None
        
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)

        # ── ヘッダー ──────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        self.icon_lbl = QLabel()
        self.title_lbl = QLabel(tr("JEPXスポット平均価格"))
        hdr.addWidget(self.icon_lbl)
        hdr.addWidget(self.title_lbl)
        hdr.addStretch()
        self.btn_today    = QPushButton(tr("今日"))
        self.btn_tomorrow = QPushButton(tr("明日"))
        for btn in (self.btn_today, self.btn_tomorrow):
            btn.setFixedSize(50, 22)
            btn.setCheckable(True)
        self.btn_today.clicked.connect(lambda: self._switch('today'))
        self.btn_tomorrow.clicked.connect(lambda: self._switch('tomorrow'))
        self.btn_today.setChecked(True)
        hdr.addWidget(self.btn_today)
        hdr.addWidget(self.btn_tomorrow)
        lay.addLayout(hdr)

        lay.addStretch()

        # ── 値エリア ──────────────────────────────────────────────────────────
        val_row = QHBoxLayout()
        self.area_lbl = QLabel("--")
        val_row.addWidget(self.area_lbl, 1)
        self.value_lbl = QLabel("-- 円/kWh")
        self.value_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        val_row.addWidget(self.value_lbl, 2)
        lay.addLayout(val_row)

        self.stats_lbl = QLabel("--")
        self.stats_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.stats_lbl)

        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(15)
        self.shadow.setOffset(0, 4)
        self.setGraphicsEffect(self.shadow)

        self._apply_style()

        self._hover_anim = QPropertyAnimation(self, b"hoverOffset")
        self._hover_anim.setDuration(150)
        self._hover_anim.setEasingCurve(QEasingCurve.OutQuad)
        self.setCursor(Qt.PointingHandCursor)

    def _switch(self, mode: str):
        self._date_mode = mode
        self.btn_today.setChecked(mode == 'today')
        self.btn_tomorrow.setChecked(mode == 'tomorrow')
        self.mode_changed.emit(mode)

    def set_theme(self, is_dark: bool):
        self.is_dark = is_dark
        self._apply_style()

    def _apply_style(self):
        tc = "#eeeeee" if self.is_dark else "#333333"
        sc = "#888888"
        pc = UIColors.get_panel_colors(self.is_dark)
        try:
            self.icon_lbl.setPixmap(get_tinted_pixmap(":/img/spot.svg", self.is_dark))
            self.icon_lbl.setStyleSheet("background: transparent;")
        except Exception:
            self.icon_lbl.setText("⚡")
            self.icon_lbl.setStyleSheet("font-size: 20px; background: transparent;")
        self.setStyleSheet(
            f"SpotDashCard {{ background-color: {pc['bg']}; border: 1px solid {pc['border']};"
            f" border-left: 6px solid #FF7043; border-radius: 8px; }}"
        )
        self.title_lbl.setStyleSheet(
            f"font-size: {Typography.H2}; font-weight: bold; background: transparent;"
            f" color: {'#aaaaaa' if self.is_dark else '#666666'};"
        )
        self.area_lbl.setStyleSheet(
            f"font-size: {Typography.H1}; font-weight: bold; background: transparent;"
            f" color: {'#FF7043' if self.is_dark else '#E64A19'};"
        )
        vc = self._val_color if self._val_color else tc
        self.value_lbl.setStyleSheet(
            f"font-size: {Typography.DISPLAY}; font-weight: bold; background: transparent; color: {vc};"
        )
        self.stats_lbl.setStyleSheet(
            f"font-size: {Typography.SMALL}; background: transparent; color: {sc};"
        )
        tog = (
            f"QPushButton {{ font-size: {Typography.SMALL}; border: 1px solid #FF7043;"
            f" border-radius: 10px; background: transparent; color: #FF7043; padding: 0 6px; }}"
            f"QPushButton:checked {{ background: #FF7043; color: white; }}"
        )
        self.btn_today.setStyleSheet(tog)
        self.btn_tomorrow.setStyleSheet(tog)
        base_alpha   = 120 if self.is_dark else 40
        target_alpha = 180 if self.is_dark else 80
        current_alpha = int(base_alpha + (target_alpha - base_alpha) * self._hover_offset)
        self.shadow.setColor(QColor(0, 0, 0, current_alpha))
        self.shadow.setOffset(0, 4 + self._hover_offset * 6)
        self.shadow.setBlurRadius(15 + self._hover_offset * 12)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_offset)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        # ボタン等の子ウィジェットへの移動ではホバーを維持する
        if not self.rect().contains(self.mapFromGlobal(QCursor.pos())):
            self._hover_anim.stop()
            self._hover_anim.setStartValue(self._hover_offset)
            self._hover_anim.setEndValue(0.0)
            self._hover_anim.start()
        super().leaveEvent(event)

    @Property(float)
    def hoverOffset(self):
        return self._hover_offset

    @hoverOffset.setter
    def hoverOffset(self, val):
        self._hover_offset = val
        if hasattr(self, 'shadow'):
            self.shadow.setOffset(0, 4 + val * 6)
            self.shadow.setBlurRadius(15 + self._hover_offset * 12)
            base_alpha   = 120 if self.is_dark else 40
            target_alpha = 180 if self.is_dark else 80
            current_alpha = int(base_alpha + (target_alpha - base_alpha) * val)
            self.shadow.setColor(QColor(0, 0, 0, current_alpha))

    def set_data(self, area: str, avg: float, max_v: float, min_v: float,
                 val_color: str | None = None):
        self._val_color = val_color
        self.area_lbl.setText(area)
        self.value_lbl.setText(f"{avg:.2f} 円/kWh")
        self.stats_lbl.setText(f"{tr('最高')} {max_v:.2f}  /  {tr('最低')} {min_v:.2f}")
        vc = val_color if val_color else UIColors.text_default(self.is_dark)
        self.value_lbl.setStyleSheet(
            f"font-size: {Typography.DISPLAY}; font-weight: bold;"
            f" background: transparent; color: {vc};"
        )

    def set_no_data(self):
        self._val_color = None
        self.area_lbl.setText(tr("データなし"))
        self.value_lbl.setText("-- 円/kWh")
        self.stats_lbl.setText("--")
        self.value_lbl.setStyleSheet(
            f"font-size: {Typography.DISPLAY}; font-weight: bold;"
            f" background: transparent; color: {UIColors.text_default(self.is_dark)};"
        )
