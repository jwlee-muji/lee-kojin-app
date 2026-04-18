import logging
import math
import random as _random
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QPushButton
)
from PySide6.QtCore import (
    Qt, QTimer, QThread, Signal, QPropertyAnimation, QEasingCurve,
    Property, QObject, QRectF, QPointF
)
from PySide6.QtGui import QColor, QPixmap, QCursor, QPainter, QPen, QBrush, QPainterPath
from app.core.config import (
    DB_IMBALANCE, DB_HJKS, DB_JKM, BASE_DIR,
    DB_JEPX_SPOT, JEPX_SPOT_AREAS,
    TIME_COL_IDX, YOJO_START_COL_IDX, YOJO_END_COL_IDX, FUSOKU_START_COL_IDX,
)
import sqlite3
from app.core.database import get_db_connection, validate_column_name
from app.ui.common import BaseWidget, get_tinted_pixmap
from app.ui.theme import Typography, UIColors
from app.core.events import bus
from app.core.i18n import tr

logger = logging.getLogger(__name__)

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
    "clear":        "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #3a2e00,stop:1 #252526)",
    "mostly_clear": "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #302800,stop:1 #252526)",
    "partly_cloudy":"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #2e2a18,stop:1 #252526)",
    "cloudy":       "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #2a2a2a,stop:1 #252526)",
    "foggy":        "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #303030,stop:1 #252526)",
    "drizzle":      "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0d1e30,stop:1 #252526)",
    "rainy":        "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0a1e3a,stop:1 #252526)",
    "heavy_rain":   "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #051228,stop:1 #252526)",
    "light_snow":   "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #1e2a35,stop:1 #252526)",
    "snowy":        "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #1a2530,stop:1 #252526)",
    "heavy_snow":   "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #141e2a,stop:1 #252526)",
    "stormy":       "qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #1a1030,stop:1 #252526)",
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
    """値が高いほど危険な指標のアラート色 (インバランス・スポット価格等)。"""
    if val >= red_thresh:
        return "#ff5252" if is_dark else "#d32f2f"
    if val >= orange_thresh:
        return "#ffa726" if is_dark else "#f57c00"
    return None


def _low_alert_color(val: float, is_dark: bool,
                     red_thresh: float = 8.0, orange_thresh: float = 10.0) -> str | None:
    """値が低いほど危険な指標のアラート色 (電力予備率等)。"""
    if val <= red_thresh:
        return "#ff5252" if is_dark else "#d32f2f"
    if val <= orange_thresh:
        return "#ffa726" if is_dark else "#f57c00"
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
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_category(self, category: str, is_dark: bool):
        self._category = category
        self._is_dark  = is_dark
        self._flash    = 0.0
        self.update()

    def _tick(self):
        self._phase = (self._phase + 0.05) % (2 * math.pi)
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

    def _cloud(self, p: QPainter, cx: float, cy: float, r: float, color: QColor):
        p.setPen(QPen(Qt.PenStyle.NoPen))
        p.setBrush(QBrush(color))
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
        """太陽本体 + 回転光線を描画する汎用ヘルパー。"""
        ri = r + r * 0.25
        ro = r + r * ray_len_fac
        ray_pen = QPen(QColor(255, 200, 50, 160), max(2.0, r * 0.18),
                       Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(ray_pen)
        for i in range(n_rays):
            a = self._phase + i * (2 * math.pi / n_rays)
            p.drawLine(
                QPointF(sx + ri * math.cos(a), sy + ri * math.sin(a)),
                QPointF(sx + ro * math.cos(a), sy + ro * math.sin(a)),
            )
        p.setBrush(QBrush(QColor(255, 215, 50, alpha)))
        p.setPen(QPen(QColor(255, 180, 30, 80), 1.5))
        p.drawEllipse(QPointF(sx, sy), r, r)

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
        drop_pen = QPen(QColor(100, 160, 225, drop_alpha), dw,
                        Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(drop_pen)
        for i in range(n):
            t    = (self._phase * 1.5 + i * (2 * math.pi / n)) % (2 * math.pi)
            prog = t / (2 * math.pi)
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
            t    = (self._phase * 1.1 + i * (2 * math.pi / n)) % (2 * math.pi)
            prog = t / (2 * math.pi)
            x    = cx + ((i / max(n - 1, 1)) - 0.5) * span \
                   + math.sin(self._phase * 0.5 + i * 1.4) * (w * 0.025)
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
    # _is_effect_alive() の RuntimeError パターンを廃止し、
    # setGraphicsEffect() が古いエフェクトを削除するタイミングで
    # Python 側の参照を None にリセットする方式に統一する。
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

            if self._skel_effect is None:
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
            self._anim_max_steps = 30  # 約1秒かけてカウントアップ (30フレーム)
            
            if not hasattr(self, '_anim_timer'):
                self._anim_timer = QTimer(self)
                self._anim_timer.timeout.connect(self._on_anim_step)
            self._anim_timer.start(33)
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
        if self._fade_opacity_effect is None:
            self._fade_opacity_effect = QGraphicsOpacityEffect()
            self._fade_out_anim = QPropertyAnimation(self._fade_opacity_effect, b"opacity", self)
            self._fade_out_anim.setDuration(180)
            self._fade_out_anim.setEasingCurve(QEasingCurve.InQuad)
            self._fade_out_anim.finished.connect(self._on_fade_out_done)
            self._fade_in_anim = QPropertyAnimation(self._fade_opacity_effect, b"opacity", self)
            self._fade_in_anim.setDuration(180)
            self._fade_in_anim.setEasingCurve(QEasingCurve.OutQuad)

        # スケルトンエフェクトが現在適用中なら、setGraphicsEffect() で Qt が削除する前に参照をクリア
        if self._skel_effect is not None and self.value_lbl.graphicsEffect() is self._skel_effect:
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
            self.shadow.setOffset(0, 4 + val * 4)
            self.shadow.setBlurRadius(15 + val * 10)
            base_alpha = 100 if self.is_dark else 30
            target_alpha = 150 if self.is_dark else 60
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
            self.shadow.setOffset(0, 4 + self._hover_offset * 4)
            self.shadow.setBlurRadius(15 + self._hover_offset * 10)
            base_alpha = 100 if self.is_dark else 30
            target_alpha = 150 if self.is_dark else 60
            current_alpha = int(base_alpha + (target_alpha - base_alpha) * self._hover_offset)
            self.shadow.setColor(QColor(0, 0, 0, current_alpha))


class DashboardDataService(QObject):
    """백그라운드 스레드에 상주하며 DB 커넥션을 캐싱하고 쿼리를 처리하는 서비스"""
    imb_result = Signal(float, str)
    imb_empty = Signal()
    jkm_result = Signal(float, str, float)
    jkm_empty = Signal()
    hjks_result = Signal(float, float)
    hjks_empty = Signal()
    spot_today_result    = Signal(list)   # [(area_name, avg, max, min), ...]
    spot_tomorrow_result = Signal(list)

    def __init__(self):
        super().__init__()

    def fetch_data(self, fetch_type):
        tasks = []
        if fetch_type in ("all", "imbalance"):
            tasks.append(self._fetch_imbalance)
        if fetch_type in ("all", "jkm"):
            tasks.append(self._fetch_jkm)
        if fetch_type in ("all", "hjks"):
            tasks.append(self._fetch_hjks)
        if fetch_type in ("all", "spot"):
            tasks.append(self._fetch_spot)

        if not tasks:
            return
        if len(tasks) == 1:
            tasks[0]()
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
                futures = [executor.submit(t) for t in tasks]
                for f in as_completed(futures):
                    if exc := f.exception():
                        logger.error(f"並行DBフェッチ中にエラー: {exc}", exc_info=True)


    def _fetch_imbalance(self):
        try:
            today_yyyymmdd = int(datetime.now().strftime("%Y%m%d"))
            with get_db_connection(DB_IMBALANCE) as conn:
                cursor = conn.execute("SELECT name FROM pragma_table_info('imbalance_prices')")
                cols = [r[0] for r in cursor.fetchall()]
                if not cols: return self.imb_empty.emit()
                date_col = validate_column_name(cols[1])

                rows = conn.execute(f'SELECT * FROM imbalance_prices WHERE "{date_col}" = ? OR "{date_col}" = ?',
                                    (today_yyyymmdd, str(today_yyyymmdd))).fetchall()
                
                if not rows: return self.imb_empty.emit()
            
            max_val = None
            max_col = ""
            max_slot = ""
            
            for row in rows:
                slot = str(row[TIME_COL_IDX])
                for i in range(YOJO_START_COL_IDX, len(cols)):
                    if (YOJO_START_COL_IDX <= i <= YOJO_END_COL_IDX or i >= FUSOKU_START_COL_IDX) and '変更S' not in cols[i]:
                        val_str = row[i]
                        if val_str:
                            try:
                                v = float(val_str)
                                if max_val is None or v > max_val:
                                    max_val = v
                                    max_col = cols[i]
                                    max_slot = slot
                            except (ValueError, TypeError):
                                pass
            
            if max_val is not None:
                self.imb_result.emit(float(max_val), tr("コマ {0} / {1}").format(max_slot, tr(max_col)))
            else: self.imb_empty.emit()
        except (sqlite3.Error, ValueError, IndexError) as e:
            logger.warning(f"インバランスDBのクエリ中にエラー: {e}")
            self.imb_empty.emit()
        except Exception as e:
            logger.error(f"インバランスデータの取得中に予期せぬエラー: {e}", exc_info=True)
            self.imb_empty.emit()
            
    def _fetch_jkm(self):
        try:
            with get_db_connection(DB_JKM) as conn:
                rows = conn.execute("SELECT date, close FROM jkm_prices ORDER BY date DESC LIMIT 2").fetchall()
                if not rows: return self.jkm_empty.emit()
                latest_date, latest_price = rows[0]
                pct = ((latest_price - rows[1][1]) / rows[1][1] * 100) if len(rows) > 1 else 0.0
                self.jkm_result.emit(latest_price, latest_date, pct)
        except sqlite3.Error as e:
            logger.warning(f"JKM DBのクエリ中にエラー: {e}")
            self.jkm_empty.emit()
        except Exception as e:
            logger.error(f"JKMデータの取得中に予期せぬエラー: {e}", exc_info=True)
            self.jkm_empty.emit()
            
    def _fetch_hjks(self):
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            with get_db_connection(DB_HJKS) as conn:
                row = conn.execute("SELECT SUM(operating_kw), SUM(stopped_kw) FROM hjks_capacity WHERE date = ?", (today_str,)).fetchone()
                if not row or row[0] is None: return self.hjks_empty.emit()
                self.hjks_result.emit(float(row[0]) / 1000.0, float(row[1]) / 1000.0)
        except sqlite3.Error as e:
            logger.warning(f"HJKS DBのクエリ中にエラー: {e}")
            self.hjks_empty.emit()
        except Exception as e:
            logger.error(f"HJKSデータの取得中に予期せぬエラー: {e}", exc_info=True)
            self.hjks_empty.emit()

    def _fetch_spot(self):
        from datetime import timedelta
        today    = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        self.spot_today_result.emit(self._query_spot(today.isoformat()))
        self.spot_tomorrow_result.emit(self._query_spot(tomorrow.isoformat()))

    def _query_spot(self, date_str: str) -> list:
        try:
            with get_db_connection(DB_JEPX_SPOT) as conn:
                result = []
                for name, col in JEPX_SPOT_AREAS:
                    safe_col = validate_column_name(col)
                    row = conn.execute(
                        f"SELECT AVG({safe_col}), MAX({safe_col}), MIN({safe_col})"
                        f" FROM jepx_spot_prices WHERE date=?",
                        (date_str,)
                    ).fetchone()
                    if row and row[0] is not None:
                        result.append((name, float(row[0]), float(row[1]), float(row[2])))
                return result
        except Exception as e:
            logger.warning(f"JEPXスポット取得エラー: {e}")
            return []


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
        self.btn_today.setChecked(True)
        self.btn_today.clicked.connect(lambda: self._switch('today'))
        self.btn_tomorrow.clicked.connect(lambda: self._switch('tomorrow'))
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
        try:
            self.icon_lbl.setPixmap(get_tinted_pixmap(":/img/spot.svg", self.is_dark))
            self.icon_lbl.setStyleSheet("background: transparent;")
        except Exception:
            self.icon_lbl.setText("⚡")
            self.icon_lbl.setStyleSheet("font-size: 20px; background: transparent;")
        bg  = "#252526" if self.is_dark else "#ffffff"
        bdr = "#3e3e42" if self.is_dark else "#dddddd"
        self.setStyleSheet(
            f"SpotDashCard {{ background-color: {bg}; border: 1px solid {bdr};"
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
        base_alpha   = 100 if self.is_dark else 30
        target_alpha = 150 if self.is_dark else 60
        current_alpha = int(base_alpha + (target_alpha - base_alpha) * self._hover_offset)
        self.shadow.setColor(QColor(0, 0, 0, current_alpha))
        self.shadow.setOffset(0, 4 + self._hover_offset * 4)
        self.shadow.setBlurRadius(15 + self._hover_offset * 10)

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
            self.shadow.setOffset(0, 4 + val * 4)
            self.shadow.setBlurRadius(15 + val * 10)
            base_alpha   = 100 if self.is_dark else 30
            target_alpha = 150 if self.is_dark else 60
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


class DashboardWidget(BaseWidget):
    request_fetch = Signal(str)
    
    def __init__(self):
        super().__init__()
        self._weather_list: list = []
        self._weather_index: int = 0
        self._spot_today: list[tuple] = []
        self._spot_tomorrow: list[tuple] = []
        self._spot_index: int = 0

        # 영구 백그라운드 DB 쿼리 서비스 설정
        self._service_thread = QThread()
        self._service = DashboardDataService()
        self._service.moveToThread(self._service_thread)
        self.request_fetch.connect(self._service.fetch_data)
        self._service_thread.finished.connect(self._service.deleteLater)
        self.track_worker(self._service_thread)   # app_quitting 시 자동 정리

        self._service.imb_result.connect(self._on_imb_result)
        self._service.imb_empty.connect(self._on_imb_empty)
        self._service.jkm_result.connect(self._on_jkm_result)
        self._service.jkm_empty.connect(self._on_jkm_empty)
        self._service.hjks_result.connect(self._on_hjks_result)
        self._service.hjks_empty.connect(self._on_hjks_empty)
        self._service.spot_today_result.connect(self._on_spot_today_result)
        self._service.spot_tomorrow_result.connect(self._on_spot_tomorrow_result)

        self._service_thread.start()

        self._build_ui()

        # Event Bus 구독 (Sub)
        bus.occto_updated.connect(self.update_occto)
        bus.imbalance_updated.connect(self.refresh_imbalance)
        bus.jkm_updated.connect(self.refresh_jkm)
        bus.hjks_updated.connect(self.refresh_hjks)
        bus.weather_updated.connect(self.update_weather)

        self.refresh_data()  # 최초 1회 로드

        self.weather_cycle_timer = QTimer(self)
        self.weather_cycle_timer.timeout.connect(self._cycle_weather)
        self.weather_cycle_timer.start(3000)

        self.spot_cycle_timer = QTimer(self)
        self.spot_cycle_timer.timeout.connect(self._cycle_spot)
        self.spot_cycle_timer.start(3000)
        
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        self.title_lbl = QLabel(tr("総合ダッシュボード"))
        layout.addWidget(self.title_lbl)
        layout.addSpacing(20)

        grid = QGridLayout()
        grid.setSpacing(20)

        self.card_imb   = SummaryCard(tr("本日の最大インバランス"), "won", "#F44336")
        self.card_occto = SummaryCard(tr("本日の最低電力予備率"), "power", "#2196F3")
        self.card_wea   = SummaryCard(tr("全国の天気"), "weather", "#4CAF50")
        self.card_jkm   = SummaryCard(tr("最新 JKM LNG 価格"), "fire", "#FF9800")
        self.card_hjks  = SummaryCard(tr("本日の発電稼働容量"), "plant", "#9C27B0")
        self.card_spot  = SpotDashCard()
        self.card_spot.mode_changed.connect(self._on_spot_mode_changed)

        # row 0-1: 既存カード, row 2: スポットカード, col 2: 天気(3行スパン)
        grid.addWidget(self.card_imb,   0, 0)
        grid.addWidget(self.card_occto, 0, 1)
        grid.addWidget(self.card_wea,   0, 2, 3, 1)   # 3行スパン
        grid.addWidget(self.card_jkm,   1, 0)
        grid.addWidget(self.card_hjks,  1, 1)
        grid.addWidget(self.card_spot,  2, 0, 1, 2)   # 2列スパン

        # 카드 클릭 → 해당 탭으로 이동
        # content_stack 순서: 0=Dashboard, 1=JepxSpot, 2=PowerReserve, 3=Imbalance,
        #                     4=JKM, 5=Weather, 6=HJKS
        self.card_spot.clicked.connect(lambda: bus.page_requested.emit(1))
        self.card_occto.clicked.connect(lambda: bus.page_requested.emit(2))
        self.card_imb.clicked.connect(lambda: bus.page_requested.emit(3))
        self.card_jkm.clicked.connect(lambda: bus.page_requested.emit(4))
        self.card_wea.clicked.connect(lambda: bus.page_requested.emit(5))
        self.card_hjks.clicked.connect(lambda: bus.page_requested.emit(6))

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        grid.setRowStretch(2, 1)
        
        layout.addLayout(grid)
        
    def apply_theme_custom(self):
        is_dark = self.is_dark
        self.title_lbl.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {UIColors.text_default(is_dark)};")
        self.card_imb.set_theme(is_dark)
        self.card_occto.set_theme(is_dark)
        self.card_wea.set_theme(is_dark)
        self.card_jkm.set_theme(is_dark)
        self.card_hjks.set_theme(is_dark)
        self.card_spot.set_theme(is_dark)
        if self.card_wea._illust:
            self.card_wea._illust.set_category(
                self.card_wea._illust._category, is_dark
            )
        if self._weather_list:
            cur_idx = (self._weather_index - 1) % len(self._weather_list)
            entry   = self._weather_list[cur_idx]
            category = _WMO_CATEGORY.get(entry.wmo_code, "clear")
            self.card_wea.set_card_bg(
                (_WMO_BG_DARK if is_dark else _WMO_BG_LIGHT).get(category, ""))
            self.card_wea.set_value(
                entry.temp_str, self._weather_sub_html(entry), entry.accent_color)

    def closeEvent(self, event):
        for sig, slot in [
            (bus.occto_updated,     self.update_occto),
            (bus.imbalance_updated, self.refresh_imbalance),
            (bus.jkm_updated,       self.refresh_jkm),
            (bus.hjks_updated,      self.refresh_hjks),
            (bus.weather_updated,   self.update_weather),
        ]:
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        super().closeEvent(event)

    def refresh_data(self):
        # 백그라운드 갱신 시 기존 값을 지우지 않고 조용히 새 데이터를 요청합니다.
        self.request_fetch.emit("all")
        
    def refresh_imbalance(self):
        self.request_fetch.emit("imbalance")

    def _on_imb_result(self, max_val, max_info):
        color = _high_alert_color(max_val, self.is_dark)
        self.card_imb.set_value(f"{max_val:,.1f} 円", max_info, color, target_val=max_val, format_str="{:,.1f} 円")
        
    def _on_imb_empty(self):
        self.card_imb.set_value(tr("-- 円"), tr("本日のデータなし"))
            
    def refresh_jkm(self):
        self.request_fetch.emit("jkm")
        
    def _on_jkm_result(self, price, date, pct):
        sign, color = ("▲", ("#ff5252" if self.is_dark else "#d32f2f")) if pct < 0 else ("▼", ("#4caf50" if self.is_dark else "#388e3c"))
        self.card_jkm.set_value(f"{price:.3f} USD", tr("{0} (前日比 {1} {2}%)").format(date, sign, abs(pct)) if pct else date, color if pct else None, target_val=price, format_str="{:.3f} USD")
        
    def _on_jkm_empty(self):
        self.card_jkm.set_value(tr("-- USD"), tr("データなし"))
            
    def refresh_hjks(self):
        self.request_fetch.emit("hjks")
        
    def _on_hjks_result(self, operating_mw, stopped_mw):
        self.card_hjks.set_value(f"{operating_mw:,.0f} MW", tr("停止中: {0} MW").format(f"{stopped_mw:,.0f}"), target_val=operating_mw, format_str="{:,.0f} MW")
        
    def _on_hjks_empty(self):
        self.card_hjks.set_value("0 MW", tr("本日のデータなし"))
            
    def update_occto(self, time_str, area_str, min_val):
        color = _low_alert_color(min_val, self.is_dark)
        self.card_occto.set_value(f"{min_val:.1f} %", f"{time_str} / {area_str}", color, target_val=min_val, format_str="{:.1f} %")
        
    def update_weather(self, weather_list):
        self._weather_list = weather_list
        self._weather_index = 0
        self._cycle_weather()
        
    def _weather_sub_html(self, entry) -> str:
        region_color = "#81c784" if self.is_dark else "#2e7d32"
        return (
            f"<span style='font-size:15px;font-weight:bold;color:{region_color};'>"
            f"{entry.region}</span>"
            f"<br/><span style='font-size:11px;color:#888888;'>{entry.weather_text}</span>"
        )

    def _cycle_weather(self):
        if not self._weather_list:
            return
        entry    = self._weather_list[self._weather_index]
        category = _WMO_CATEGORY.get(entry.wmo_code, "clear")
        bg_map   = _WMO_BG_DARK if self.is_dark else _WMO_BG_LIGHT
        self.card_wea.set_card_bg(bg_map.get(category, ""))
        self.card_wea.set_weather_illust(category, self.is_dark)
        self.card_wea.set_value(
            entry.temp_str,
            self._weather_sub_html(entry),
            entry.accent_color,
            animate_fade=True,
        )
        self._weather_index = (self._weather_index + 1) % len(self._weather_list)

    # ── JEPX スポット ─────────────────────────────────────────────────────────

    def _on_spot_today_result(self, data: list):
        self._spot_today = data
        if self.card_spot._date_mode == 'today':
            self._spot_index = 0
            self._cycle_spot()

    def _on_spot_tomorrow_result(self, data: list):
        self._spot_tomorrow = data
        if self.card_spot._date_mode == 'tomorrow':
            self._spot_index = 0
            self._cycle_spot()

    def _on_spot_mode_changed(self, _mode: str):
        self._spot_index = 0
        self._cycle_spot()

    def _cycle_spot(self):
        data = self._spot_today if self.card_spot._date_mode == 'today' else self._spot_tomorrow
        if not data:
            self.card_spot.set_no_data()
            return
        entry = data[self._spot_index % len(data)]
        avg = entry[1]
        color = _high_alert_color(avg, self.is_dark)
        self.card_spot.set_data(entry[0], avg, entry[2], entry[3], val_color=color)
        self._spot_index = (self._spot_index + 1) % len(data)