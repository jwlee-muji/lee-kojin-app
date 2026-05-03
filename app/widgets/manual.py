"""共有マニュアル (Wiki) ウィジェット — Phase 5.11 リニューアル.

권한:
    - 일반 사용자: 열람 + 검색 + 코멘트
    - 관리자 / 본인 작성자: CRUD + 카테고리 관리 + 이미지 편집

데이터:
    - Google Drive 공유 SQLite DB (app.core.shared_database)
    - 이미지: SHARED_IMAGE_DIR (UUID 파일명, JPEG 80%)

디자인 출처:
    - handoff/01-design-tokens.md, 02-components.md
    - handoff/LEE_PROJECT/varA-manual-detail.jsx
    - LeeDetailHeader / LeeCard / LeeButton / LeePill / LeeDialog / LeeIconTile
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QEvent, QMimeData, QObject, QPointF, QRectF, Qt, QThread,
    QTimer, QUrl, Signal,
)
from PySide6.QtGui import (
    QBrush, QColor, QCursor, QDesktopServices, QDrag, QFont,
    QIcon, QImage, QKeySequence, QPainter, QPainterPath, QPen, QPixmap,
    QShortcut, QTextCharFormat, QTextCursor, QTransform,
)
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QFileDialog,
    QFrame, QGraphicsItem, QGraphicsScene, QGraphicsView, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QPushButton, QScrollArea, QSizePolicy, QSlider, QSplitter,
    QTextBrowser, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from app.api.google.auth import get_current_user_email
from app.core.config import ADMIN_EMAIL
from app.core.events import bus
from app.core.i18n import tr
from app.core.shared_database import (
    SHARED_IMAGE_DIR, get_shared_db, init_shared_db,
)
from app.ui.common import BaseWidget, FadeStackedWidget
from app.ui.components import (
    LeeButton, LeeDetailHeader, LeeDialog, LeeIconTile, LeePill,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 토큰 (모듈 로컬)
# ──────────────────────────────────────────────────────────────────────
_C_MANUAL  = "#5856D6"   # iOS 인디고 — Manual / Wiki accent
_C_BAD     = "#FF453A"

_SYSTEM_CATEGORY = "未分類"   # 보호 카테고리 — rename/delete 금지


# ──────────────────────────────────────────────────────────────────────
# 권한 헬퍼
# ──────────────────────────────────────────────────────────────────────
def _is_admin() -> bool:
    try:
        em = (get_current_user_email() or "").lower()
        return em == ADMIN_EMAIL.lower()
    except Exception:
        return False


def _can_edit_manual(manual: dict) -> bool:
    if not manual:
        return False
    em = (get_current_user_email() or "").lower()
    return em == (manual.get("author_email") or "").lower() or _is_admin()


# ──────────────────────────────────────────────────────────────────────
# 1. ImageEditView — QGraphicsView 기반 벡터 편집기 (펜/사각/체크/텍스트/이동/크롭)
# ──────────────────────────────────────────────────────────────────────
class ImageEditView(QGraphicsView):
    """드래그·확대축소·그리기·자르기 기능을 지원하는 벡터 뷰어."""

    def __init__(self, image: QImage, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

        self.bg_image = image.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        self.pixmap_item = self.scene.addPixmap(QPixmap.fromImage(self.bg_image))
        self.scene.setSceneRect(self.pixmap_item.boundingRect())

        self.tool = "pen"
        self.pen_color = QColor(_C_BAD)
        self.pen_width = 4
        self.items_history: list = []

        self.current_item = None
        self.current_path: Optional[QPainterPath] = None
        self.start_pos = QPointF()
        self.crop_rect_item = None

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        if tool == "move":
            self.setDragMode(QGraphicsView.RubberBandDrag)
            for item in self.items_history:
                item.setFlag(QGraphicsItem.ItemIsMovable, True)
                item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        else:
            self.setDragMode(QGraphicsView.NoDrag)
            for item in self.items_history:
                item.setFlag(QGraphicsItem.ItemIsMovable, False)
                item.setFlag(QGraphicsItem.ItemIsSelectable, False)
            self.scene.clearSelection()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            zoom_in = 1.15
            zoom_out = 1 / zoom_in
            factor = zoom_in if event.angleDelta().y() > 0 else zoom_out
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        if self.tool == "move":
            super().mousePressEvent(event); return
        if event.button() != Qt.LeftButton:
            return
        scene_pos = self.mapToScene(event.position().toPoint())
        self.start_pos = scene_pos

        if self.tool == "text":
            text, ok = QInputDialog.getText(
                self, tr("テキスト入力"), tr("挿入するテキストを入力してください:"),
            )
            if ok and text:
                ti = self.scene.addText(text, QFont("sans-serif", 16, QFont.Bold))
                ti.setDefaultTextColor(self.pen_color)
                ti.setPos(scene_pos)
                self.items_history.append(ti)
        elif self.tool == "pen":
            self.current_path = QPainterPath()
            self.current_path.moveTo(scene_pos)
            self.current_path.lineTo(scene_pos + QPointF(0.1, 0.1))
            self.current_item = self.scene.addPath(
                self.current_path,
                QPen(self.pen_color, self.pen_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin),
            )
            self.items_history.append(self.current_item)
        elif self.tool == "rect":
            self.current_item = self.scene.addRect(
                QRectF(scene_pos, scene_pos),
                QPen(self.pen_color, self.pen_width),
            )
            self.items_history.append(self.current_item)
        elif self.tool == "check":
            self.current_item = self.scene.addPath(
                QPainterPath(),
                QPen(self.pen_color, self.pen_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin),
            )
            self.items_history.append(self.current_item)
        elif self.tool == "crop":
            if self.crop_rect_item:
                self.scene.removeItem(self.crop_rect_item)
            self.crop_rect_item = self.scene.addRect(
                QRectF(scene_pos, scene_pos),
                QPen(Qt.white, 2, Qt.DashLine),
                QBrush(QColor(0, 0, 0, 50)),
            )

    def mouseMoveEvent(self, event):
        if self.tool == "move":
            super().mouseMoveEvent(event); return
        if event.buttons() & Qt.LeftButton and self.current_item:
            scene_pos = self.mapToScene(event.position().toPoint())
            if self.tool == "pen" and self.current_path is not None:
                self.current_path.lineTo(scene_pos)
                self.current_item.setPath(self.current_path)
            elif self.tool == "rect":
                r = QRectF(self.start_pos, scene_pos).normalized()
                self.current_item.setRect(r)
            elif self.tool == "check":
                r = QRectF(self.start_pos, scene_pos).normalized()
                if r.width() > 5 and r.height() > 5:
                    p1 = QPointF(r.left() + r.width() * 0.2, r.top() + r.height() * 0.5)
                    p2 = QPointF(r.left() + r.width() * 0.4, r.bottom() - r.height() * 0.1)
                    p3 = QPointF(r.right() - r.width() * 0.1, r.top() + r.height() * 0.1)
                    path = QPainterPath()
                    path.moveTo(p1); path.lineTo(p2); path.lineTo(p3)
                    self.current_item.setPath(path)
        elif event.buttons() & Qt.LeftButton and self.tool == "crop" and self.crop_rect_item:
            scene_pos = self.mapToScene(event.position().toPoint())
            r = QRectF(self.start_pos, scene_pos).normalized()
            self.crop_rect_item.setRect(r)

    def mouseReleaseEvent(self, event):
        if self.tool == "move":
            super().mouseReleaseEvent(event); return
        if event.button() == Qt.LeftButton:
            self.current_item = None

    def apply_crop(self) -> None:
        if not self.crop_rect_item:
            return
        rect = self.crop_rect_item.rect().toRect()
        if rect.width() < 10 or rect.height() < 10:
            self.scene.removeItem(self.crop_rect_item)
            self.crop_rect_item = None
            return
        self.scene.removeItem(self.crop_rect_item)
        self.crop_rect_item = None
        self.scene.clearSelection()

        img = QImage(rect.size(), QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing)
        self.scene.render(painter, target=QRectF(img.rect()), source=QRectF(rect))
        painter.end()

        self.scene.clear()
        self.items_history.clear()
        self.bg_image = img
        self.pixmap_item = self.scene.addPixmap(QPixmap.fromImage(self.bg_image))
        self.scene.setSceneRect(self.pixmap_item.boundingRect())
        self.setTransform(QTransform())
        self.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def clear_drawing(self) -> None:
        self.scene.clear()
        self.items_history.clear()
        self.pixmap_item = self.scene.addPixmap(QPixmap.fromImage(self.bg_image))
        self.scene.setSceneRect(self.pixmap_item.boundingRect())
        self.setTransform(QTransform())

    def undo(self) -> None:
        if self.items_history:
            item = self.items_history.pop()
            self.scene.removeItem(item)

    def get_edited_image(self) -> QImage:
        self.scene.clearSelection()
        if self.crop_rect_item:
            self.scene.removeItem(self.crop_rect_item)
        img = QImage(self.scene.sceneRect().size().toSize(), QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing)
        self.scene.render(painter)
        painter.end()
        return img


# ──────────────────────────────────────────────────────────────────────
# 2. ImageEditDialog — LeeDialog 베이스 (5 도구 + 6 컬러 + 굵기)
# ──────────────────────────────────────────────────────────────────────
class ImageEditDialog(LeeDialog):
    """画像エディタ — 펜/사각/체크/텍스트/이동/크롭 + 6 컬러 + 굵기 슬라이더."""

    PALETTE = [
        ("#FF453A", "Bad"),
        ("#FF9F0A", "Warn"),
        ("#30D158", "OK"),
        ("#0A84FF", "Info"),
        ("#FFFFFF", "White"),
        ("#000000", "Black"),
    ]

    TOOLS = [
        ("pen",   "✎",  tr("ペン")),
        ("rect",  "▢",  tr("矩形")),
        ("check", "✓",  tr("チェック")),
        ("text",  "T",  tr("テキスト")),
        ("crop",  "⌗",  tr("クロップ")),
        ("move",  "✥",  tr("移動")),
    ]

    def __init__(self, image: QImage, parent=None):
        super().__init__(tr("画像エディタ"), kind="info", parent=parent)
        self._is_dark = True
        self.set_message(tr("ペン・矩形・テキストなどで注釈を追加 (Ctrl+ホイールでズーム)"))

        # 캔버스 + 툴바를 본문 영역에 삽입
        self.image_widget = ImageEditView(image)
        self.image_widget.setMinimumSize(640, 380)

        # 툴바 컨테이너 (도구 / 색 / 굵기 / Undo / 클리어)
        toolbar = QFrame(); toolbar.setObjectName("manualImgToolbar")
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(10, 8, 10, 8); tb_lay.setSpacing(6)

        self._tool_btns: dict[str, QPushButton] = {}
        for tool_id, glyph, name in self.TOOLS:
            b = QPushButton(glyph); b.setObjectName("manualToolBtn")
            b.setProperty("toolId", tool_id)
            b.setFixedSize(32, 32); b.setCheckable(True)
            b.setToolTip(name)
            b.clicked.connect(lambda _=False, t=tool_id: self._set_tool(t))
            tb_lay.addWidget(b)
            self._tool_btns[tool_id] = b
        self._tool_btns["pen"].setChecked(True)

        # 적용 버튼 (crop 모드일 때만 표시)
        self._btn_apply_crop = QPushButton("✔"); self._btn_apply_crop.setObjectName("manualToolBtn")
        self._btn_apply_crop.setFixedSize(32, 32); self._btn_apply_crop.setToolTip(tr("クロップ適用"))
        self._btn_apply_crop.clicked.connect(self.image_widget.apply_crop)
        self._btn_apply_crop.hide()
        tb_lay.addWidget(self._btn_apply_crop)

        # 구분선
        sep1 = QFrame(); sep1.setObjectName("manualToolSep"); sep1.setFixedSize(1, 22); tb_lay.addWidget(sep1)

        # 6 컬러 선택
        self._color_btns: list[QPushButton] = []
        for color_hex, _ in self.PALETTE:
            cb = QPushButton(); cb.setObjectName("manualColorDot")
            cb.setProperty("colorHex", color_hex)
            cb.setFixedSize(22, 22); cb.setCheckable(True)
            cb.setStyleSheet(self._color_btn_qss(color_hex, selected=(color_hex == _C_BAD)))
            cb.clicked.connect(lambda _=False, c=color_hex: self._set_color(c))
            tb_lay.addWidget(cb)
            self._color_btns.append(cb)

        # 구분선
        sep2 = QFrame(); sep2.setObjectName("manualToolSep"); sep2.setFixedSize(1, 22); tb_lay.addWidget(sep2)

        # 굵기 슬라이더
        self._width_slider = QSlider(Qt.Horizontal)
        self._width_slider.setRange(1, 20); self._width_slider.setValue(4)
        self._width_slider.setFixedWidth(100)
        self._width_slider.valueChanged.connect(self._set_width)
        tb_lay.addWidget(self._width_slider)
        self._width_lbl = QLabel("4px"); self._width_lbl.setObjectName("manualWidthLbl")
        self._width_lbl.setFixedWidth(36)
        tb_lay.addWidget(self._width_lbl)

        tb_lay.addStretch()

        # Undo / 클리어
        self._btn_undo = QPushButton("↶"); self._btn_undo.setObjectName("manualToolBtn")
        self._btn_undo.setFixedSize(32, 32); self._btn_undo.setToolTip(tr("元に戻す") + " (Ctrl+Z)")
        self._btn_undo.clicked.connect(self.image_widget.undo)
        tb_lay.addWidget(self._btn_undo)
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self.image_widget.undo)

        self._btn_clear = QPushButton("🗑"); self._btn_clear.setObjectName("manualToolBtn")
        self._btn_clear.setFixedSize(32, 32); self._btn_clear.setToolTip(tr("全削除"))
        self._btn_clear.clicked.connect(self.image_widget.clear_drawing)
        tb_lay.addWidget(self._btn_clear)

        # 본문에 삽입 (toolbar 위, canvas 아래)
        self.add_body_widget(toolbar)
        self.add_body_widget(self.image_widget)

        # 푸터 버튼
        self.add_button(tr("キャンセル"), variant="ghost",   role="reject")
        self.add_button(tr("挿入"),       variant="primary", role="accept")

        # 다이얼로그 크기 조정
        screen = QApplication.primaryScreen().availableGeometry()
        max_w, max_h = int(screen.width() * 0.9), int(screen.height() * 0.9)
        w = min(max(image.width() + 80, 800), max_w)
        h = min(max(image.height() + 240, 640), max_h)
        self.resize(w, h)

        self._apply_local_qss()

    def _color_btn_qss(self, color_hex: str, selected: bool) -> str:
        border = "2px solid #FFFFFF" if selected else "1px solid rgba(255,255,255,0.18)"
        return (
            f"QPushButton#manualColorDot {{ background: {color_hex};"
            f" border: {border}; border-radius: 11px; }}"
        )

    def _apply_local_qss(self) -> None:
        # LeeDialog 본문 안 toolbar / 캔버스 스타일 — dialog 모드는 항상 다크 베이스
        bg_surface_2 = "#1B1E26"
        border_subtle = "rgba(255,255,255,0.06)"
        border = "rgba(255,255,255,0.10)"
        fg_tertiary = "#6B7280"
        accent = _C_MANUAL
        self.setStyleSheet(self.styleSheet() + f"""
            QFrame#manualImgToolbar {{
                background: {bg_surface_2};
                border: 1px solid {border_subtle};
                border-radius: 10px;
            }}
            QFrame#manualToolSep {{ background: {border}; }}
            QPushButton#manualToolBtn {{
                background: #14161C; color: #F2F4F7;
                border: 1px solid {border_subtle}; border-radius: 7px;
                font-size: 14px; font-weight: 800;
            }}
            QPushButton#manualToolBtn:checked {{
                background: {accent}; color: white; border: 1px solid {accent};
            }}
            QPushButton#manualToolBtn:hover:!checked {{
                background: #232730; border: 1px solid {border};
            }}
            QLabel#manualWidthLbl {{
                color: {fg_tertiary};
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 10px; background: transparent;
            }}
            QGraphicsView {{
                background: {bg_surface_2};
                border: 1px solid {border_subtle};
                border-radius: 10px;
            }}
            QSlider::groove:horizontal {{
                background: {border}; height: 4px; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {accent}; width: 14px; height: 14px;
                margin: -5px 0; border-radius: 7px;
            }}
        """)

    def _set_tool(self, tool_id: str) -> None:
        for t, btn in self._tool_btns.items():
            btn.setChecked(t == tool_id)
        self._btn_apply_crop.setVisible(tool_id == "crop")
        self.image_widget.set_tool(tool_id)

    def _set_color(self, color_hex: str) -> None:
        for cb in self._color_btns:
            chx = cb.property("colorHex")
            cb.setChecked(chx == color_hex)
            cb.setStyleSheet(self._color_btn_qss(chx, selected=(chx == color_hex)))
        self.image_widget.pen_color = QColor(color_hex)

    def _set_width(self, v: int) -> None:
        self.image_widget.pen_width = v
        self._width_lbl.setText(f"{v}px")

    def get_edited_image(self) -> QImage:
        return self.image_widget.get_edited_image()


# ──────────────────────────────────────────────────────────────────────
# 3. ImagePreviewDialog — LeeDialog 베이스 (줌 + 팬 + 메타)
# ──────────────────────────────────────────────────────────────────────
class ImagePreviewDialog(LeeDialog):
    """画像プレビュー — 줌 컨트롤 (+/−/fit/100%) + 휠 줌 + 드래그 팬."""

    def __init__(self, image_path: str, parent=None):
        super().__init__(tr("画像プレビュー"), kind="info", parent=parent)
        self._is_dark = True
        self.set_message(tr("マウスホイールでズーム — ドラッグでパン"))

        self._image_path = image_path
        self._scene = QGraphicsScene(self)

        url = QUrl(image_path)
        local = url.toLocalFile() if url.isLocalFile() else image_path
        self._pixmap = QPixmap(local)
        if self._pixmap.isNull():
            self._pixmap = QPixmap(image_path)

        self._view = _PannableGraphicsView(self._scene, self)
        self._view.setMinimumSize(640, 420)
        if not self._pixmap.isNull():
            self._scene.addPixmap(self._pixmap)
            self._scene.setSceneRect(0, 0, self._pixmap.width(), self._pixmap.height())

        # 줌 툴바
        zbar = QFrame(); zbar.setObjectName("manualPreviewBar")
        zbl = QHBoxLayout(zbar); zbl.setContentsMargins(10, 8, 10, 8); zbl.setSpacing(8)

        meta_text = self._meta_text(local)
        self._meta_lbl = QLabel(meta_text); self._meta_lbl.setObjectName("manualPreviewMeta")
        zbl.addWidget(self._meta_lbl, 1)

        for glyph, tip, slot in (
            ("−",    tr("縮小"),       lambda: self._view.scale(1 / 1.2, 1 / 1.2)),
            ("100%", tr("等倍"),       self._view.zoom_reset),
            ("Fit",  tr("ウィンドウに合わせる"), self._view.zoom_fit),
            ("＋",    tr("拡大"),       lambda: self._view.scale(1.2, 1.2)),
        ):
            b = QPushButton(glyph); b.setObjectName("manualToolBtn")
            b.setFixedHeight(28); b.setMinimumWidth(36)
            b.setToolTip(tip); b.clicked.connect(slot)
            zbl.addWidget(b)

        self.add_body_widget(zbar)
        self.add_body_widget(self._view)
        self.add_button(tr("閉じる"), variant="primary", role="accept")

        # 다이얼로그 크기
        screen = QApplication.primaryScreen().availableGeometry()
        max_w, max_h = int(screen.width() * 0.9), int(screen.height() * 0.9)
        if not self._pixmap.isNull():
            w = min(max(self._pixmap.width() + 80, 720), max_w)
            h = min(max(self._pixmap.height() + 200, 560), max_h)
        else:
            w, h = 720, 560
        self.resize(w, h)

        self._apply_local_qss()
        QTimer.singleShot(0, self._view.zoom_fit)

    def _meta_text(self, local_path: str) -> str:
        name = Path(local_path).name if local_path else "(unknown)"
        try:
            size_kb = Path(local_path).stat().st_size / 1024
            size_str = f"{size_kb:,.1f} KB"
        except OSError:
            size_str = "—"
        if self._pixmap and not self._pixmap.isNull():
            res_str = f"{self._pixmap.width()} × {self._pixmap.height()}"
        else:
            res_str = "—"
        return f"📎 {name}  ·  {size_str}  ·  {res_str}"

    def _apply_local_qss(self) -> None:
        bg_surface_2 = "#1B1E26"
        border_subtle = "rgba(255,255,255,0.06)"
        fg_tertiary = "#6B7280"
        self.setStyleSheet(self.styleSheet() + f"""
            QFrame#manualPreviewBar {{
                background: {bg_surface_2};
                border: 1px solid {border_subtle};
                border-radius: 10px;
            }}
            QLabel#manualPreviewMeta {{
                color: {fg_tertiary};
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 11px; background: transparent;
            }}
            QPushButton#manualToolBtn {{
                background: #14161C; color: #F2F4F7;
                border: 1px solid {border_subtle}; border-radius: 7px;
                font-size: 11px; font-weight: 700; padding: 0 8px;
            }}
            QPushButton#manualToolBtn:hover {{
                background: #232730;
            }}
            QGraphicsView {{
                background: {bg_surface_2};
                border: 1px solid {border_subtle};
                border-radius: 10px;
            }}
        """)


class _PannableGraphicsView(QGraphicsView):
    """휠 줌 + 드래그 팬 지원 뷰어."""
    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def wheelEvent(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        self.scale(factor, factor)

    def zoom_reset(self) -> None:
        self.setTransform(QTransform())

    def zoom_fit(self) -> None:
        if not self.scene().items():
            return
        self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)


# ──────────────────────────────────────────────────────────────────────
# 4. CategoryManagerDialog — LeeDialog 베이스 (SYSTEM 보호)
# ──────────────────────────────────────────────────────────────────────
class CategoryManagerDialog(LeeDialog):
    """카테고리 관리 — 추가/이름변경/삭제/순서. SYSTEM 카테고리 (未分類) 보호."""

    def __init__(self, categories: list, is_dark: bool, parent=None):
        super().__init__(tr("カテゴリ管理"), kind="info", parent=parent)
        self._is_dark = is_dark
        self.set_message(tr("ドラッグで並び替え · 「{0}」 は SYSTEM のため変更不可").format(_SYSTEM_CATEGORY))

        self.action_taken = False
        self.action_type: Optional[str] = None
        self.old_name: Optional[str] = None
        self.new_name: Optional[str] = None
        # SYSTEM 은 별도 보호 — 리스트엔 표시하지만 편집 불가
        self._editable = [c for c in categories if c != _SYSTEM_CATEGORY]

        body = QFrame(); body.setObjectName("manualCatMgrBody")
        bl = QVBoxLayout(body); bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(8)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("manualCatList")
        self.list_widget.setDragDropMode(QListWidget.InternalMove)
        for c in self._editable:
            self.list_widget.addItem(c)
        # 시스템 카테고리는 맨 아래에 비활성 표시
        sys_item = QListWidgetItem(f"🔒 {_SYSTEM_CATEGORY}  ({tr('SYSTEM')})")
        sys_item.setFlags(Qt.ItemIsSelectable & ~Qt.ItemIsSelectable)
        self.list_widget.addItem(sys_item)
        self.list_widget.setMinimumHeight(220)
        bl.addWidget(self.list_widget, 1)

        # 액션 행 — LeeButton 으로 통일
        action_row = QHBoxLayout(); action_row.setSpacing(6)
        self.btn_add = LeeButton("＋ " + tr("新規"),     variant="secondary", size="sm")
        self.btn_rename = LeeButton("✎ " + tr("名前変更"), variant="secondary", size="sm")
        self.btn_delete = LeeButton("🗑 " + tr("削除"),    variant="destructive", size="sm")
        self.btn_add.clicked.connect(self._on_add)
        self.btn_rename.clicked.connect(self._on_rename)
        self.btn_delete.clicked.connect(self._on_delete)
        action_row.addWidget(self.btn_add)
        action_row.addWidget(self.btn_rename)
        action_row.addWidget(self.btn_delete)
        action_row.addStretch()
        bl.addLayout(action_row)

        self.add_body_widget(body)
        self.add_button(tr("完了"), variant="primary", role="accept")

        self._apply_local_qss()
        self.resize(520, 460)

    def _apply_local_qss(self) -> None:
        bg_surface_2 = "#1B1E26"
        border_subtle = "rgba(255,255,255,0.06)"
        fg_primary = "#F2F4F7"
        accent_bg = "rgba(88,86,214,0.18)"
        self.setStyleSheet(self.styleSheet() + f"""
            QListWidget#manualCatList {{
                background: {bg_surface_2};
                color: {fg_primary};
                border: 1px solid {border_subtle};
                border-radius: 10px;
                padding: 4px;
                font-size: 12.5px;
            }}
            QListWidget#manualCatList::item {{
                padding: 8px 10px;
                border-radius: 6px;
            }}
            QListWidget#manualCatList::item:selected {{
                background: {accent_bg};
                color: {fg_primary};
            }}
        """)

    def _selected_editable(self) -> Optional[str]:
        item = self.list_widget.currentItem()
        if not item:
            return None
        text = item.text()
        if text.startswith("🔒"):
            return None
        return text

    def _on_add(self) -> None:
        new_name, ok = QInputDialog.getText(
            self, tr("新規"), tr("新しいカテゴリ名を入力:"),
        )
        if not ok or not new_name:
            return
        new_name = new_name.strip()
        if not new_name or new_name == _SYSTEM_CATEGORY or new_name in self._editable:
            return
        self.action_taken = True
        self.action_type = "add"
        self.new_name = new_name
        self.accept()

    def _on_rename(self) -> None:
        old = self._selected_editable()
        if old is None:
            return
        new_name, ok = QInputDialog.getText(
            self, tr("名前変更"), tr("新しいカテゴリ名:"), text=old,
        )
        if not ok or not new_name or new_name.strip() == old:
            return
        nm = new_name.strip()
        if nm == _SYSTEM_CATEGORY:
            return
        self.action_taken = True
        self.action_type = "rename"
        self.old_name = old
        self.new_name = nm
        self.accept()

    def _on_delete(self) -> None:
        cat = self._selected_editable()
        if cat is None:
            return
        if not LeeDialog.confirm(
            tr("削除の確認"),
            tr("カテゴリ「{0}」を削除し、含まれるマニュアルを「{1}」にしますか?").format(
                cat, _SYSTEM_CATEGORY,
            ),
            ok_text=tr("削除"), destructive=True, parent=self,
        ):
            return
        self.action_taken = True
        self.action_type = "delete"
        self.old_name = cat
        self.accept()

    def get_ordered_categories(self) -> list[str]:
        out = []
        for i in range(self.list_widget.count()):
            t = self.list_widget.item(i).text()
            if not t.startswith("🔒"):
                out.append(t)
        return out


# ──────────────────────────────────────────────────────────────────────
# 5. ResponsiveTextBrowser — viewer (image auto-resize, 동일 동작 유지)
# ──────────────────────────────────────────────────────────────────────
class ResponsiveTextBrowser(QTextBrowser):
    """HTML 렌더링 시 이미지가 창 폭을 넘지 않도록 자동 리사이징."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._images_original_size: dict[str, tuple[int, int]] = {}

    def setHtml(self, html: str):
        super().setHtml(html)
        self._extract_original_sizes()
        self._adjust_images()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_images()

    def _extract_original_sizes(self):
        self._images_original_size.clear()
        doc = self.document()
        cursor = QTextCursor(doc)
        while not cursor.atEnd():
            cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
            fmt = cursor.charFormat()
            if fmt.isImageFormat():
                img_fmt = fmt.toImageFormat()
                name = img_fmt.name()
                if name not in self._images_original_size:
                    if img_fmt.width() > 0 and img_fmt.height() > 0:
                        self._images_original_size[name] = (img_fmt.width(), img_fmt.height())
                    else:
                        url = QUrl(name)
                        img = QImage(url.toLocalFile() if url.isLocalFile() else name)
                        if not img.isNull():
                            self._images_original_size[name] = (img.width(), img.height())
            cursor.clearSelection()

    def _adjust_images(self):
        doc = self.document()
        max_w = max(100, self.viewport().width() - 50)
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        while not cursor.atEnd():
            cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
            fmt = cursor.charFormat()
            if fmt.isImageFormat():
                img_fmt = fmt.toImageFormat()
                name = img_fmt.name()
                if name in self._images_original_size:
                    orig_w, orig_h = self._images_original_size[name]
                    if orig_w > max_w:
                        ratio = max_w / orig_w
                        img_fmt.setWidth(max_w)
                        img_fmt.setHeight(orig_h * ratio)
                    else:
                        img_fmt.setWidth(orig_w)
                        img_fmt.setHeight(orig_h)
                    cursor.setCharFormat(img_fmt)
            cursor.clearSelection()
        cursor.endEditBlock()


# ──────────────────────────────────────────────────────────────────────
# 6. ManualTreeWidget — 카테고리 ↔ 매뉴얼 드래그 드롭
# ──────────────────────────────────────────────────────────────────────
class ManualTreeWidget(QTreeWidget):
    """드래그앤드롭으로 매뉴얼 카테고리 이동."""
    item_moved = Signal(str, str, list)   # manual_id, new_category, ordered_ids

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QTreeWidget.InternalMove)

    def dropEvent(self, event):
        dragged = self.currentItem()
        if not dragged:
            event.ignore(); return
        manual_id = dragged.data(0, Qt.UserRole)
        if not manual_id:
            event.ignore(); return
        target = self.itemAt(event.position().toPoint())
        if not target:
            event.ignore(); return

        drop_indicator = self.dropIndicatorPosition()
        is_target_cat = (target.parent() is None)
        if is_target_cat and drop_indicator in (
            QAbstractItemView.DropIndicatorPosition.AboveItem,
            QAbstractItemView.DropIndicatorPosition.BelowItem,
        ):
            event.ignore(); return

        if not is_target_cat and drop_indicator == QAbstractItemView.DropIndicatorPosition.OnItem:
            parent = target.parent()
            if parent:
                idx = parent.indexOfChild(target)
                old_parent = dragged.parent()
                if old_parent:
                    old_parent.takeChild(old_parent.indexOfChild(dragged))
                parent.insertChild(idx, dragged)
                self.setCurrentItem(dragged)
            else:
                event.ignore(); return
        else:
            super().dropEvent(event)

        new_parent = dragged.parent()
        if new_parent:
            new_cat = new_parent.text(0).split("  ", 1)[0].strip()  # "業務マニュアル  3" → "業務マニュアル"
            ordered_ids = []
            for i in range(new_parent.childCount()):
                m_id = new_parent.child(i).data(0, Qt.UserRole)
                if m_id:
                    ordered_ids.append(m_id)
            self.item_moved.emit(manual_id, new_cat, ordered_ids)


# ──────────────────────────────────────────────────────────────────────
# 7. MarkdownEditor / AutoResizingTextEdit / SortableSectionsContainer / ManualSectionWidget
#    — 섹션 기반 에디터 (drag-drop 정렬, 이미지 paste/drop)
# ──────────────────────────────────────────────────────────────────────
class MarkdownEditor(QTextEdit):
    """drag&drop / clipboard paste 로 이미지 처리."""
    image_dropped = Signal(QImage, QTextEdit)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def canInsertFromMimeData(self, source):
        if source.hasImage() or source.hasUrls():
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        if source.hasImage():
            image = source.imageData()
            if isinstance(image, QImage) and not image.isNull():
                self.image_dropped.emit(image, self); return
        elif source.hasUrls():
            for url in source.urls():
                if url.isLocalFile():
                    p = url.toLocalFile()
                    ext = Path(p).suffix.lower()
                    if ext in [".png", ".jpg", ".jpeg", ".gif", ".bmp"]:
                        image = QImage(p)
                        if not image.isNull():
                            self.image_dropped.emit(image, self); return
        super().insertFromMimeData(source)


class AutoResizingTextEdit(MarkdownEditor):
    """내용 입력에 따라 높이 자동 조절."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.document().documentLayout().documentSizeChanged.connect(self._adjust_height)
        self._adjust_height(self.document().size())

    def _adjust_height(self, size):
        h = int(size.height()) + 14
        self.setFixedHeight(max(80, min(h, 600)))


class SortableSectionsContainer(QWidget):
    """섹션들을 담고 드래그앤드롭 정렬."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._drag_source: Optional[QWidget] = None

    def dragEnterEvent(self, event):
        src = event.source()
        if isinstance(src, ManualSectionWidget) and event.mimeData().hasFormat("application/x-manual-section"):
            self._drag_source = src
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._drag_source and event.mimeData().hasFormat("application/x-manual-section"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not self._drag_source:
            return
        layout = self.layout()
        pos = event.position().toPoint()
        target_idx = layout.count() - 2
        for i in range(layout.count() - 1):
            w = layout.itemAt(i).widget()
            if isinstance(w, ManualSectionWidget) and pos.y() < w.y() + w.height() / 2:
                target_idx = i; break
        current_idx = layout.indexOf(self._drag_source)
        if current_idx != target_idx:
            layout.removeWidget(self._drag_source)
            if target_idx > current_idx: target_idx -= 1
            layout.insertWidget(target_idx, self._drag_source)
        self._drag_source = None
        event.acceptProposedAction()


class ManualSectionWidget(QFrame):
    """섹션 (제목 + 이미지 + 본문) 에디터 행."""
    remove_requested    = Signal(QWidget)
    move_up_requested   = Signal(QWidget)
    move_down_requested = Signal(QWidget)
    image_requested     = Signal(QWidget)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_url = ""
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.setObjectName("manualSection")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12); layout.setSpacing(8)

        # 헤더 행
        hdr = QHBoxLayout(); hdr.setSpacing(6)
        self._idx_lbl = QLabel("•"); self._idx_lbl.setObjectName("manualSectionIdx")
        self._idx_lbl.setFixedSize(24, 24); self._idx_lbl.setAlignment(Qt.AlignCenter)
        hdr.addWidget(self._idx_lbl)
        self.edit_subtitle = QLineEdit()
        self.edit_subtitle.setObjectName("manualSectionTitle")
        self.edit_subtitle.setPlaceholderText(tr("項目の見出し..."))
        hdr.addWidget(self.edit_subtitle, 1)

        self.btn_up = QPushButton("▲"); self.btn_up.setObjectName("manualSectionMini")
        self.btn_down = QPushButton("▼"); self.btn_down.setObjectName("manualSectionMini")
        self.btn_remove = QPushButton("✕"); self.btn_remove.setObjectName("manualSectionMini")
        self.btn_remove.setProperty("danger", True)
        for b in (self.btn_up, self.btn_down, self.btn_remove):
            b.setFixedSize(26, 26); hdr.addWidget(b)
        self.btn_up.clicked.connect(lambda: self.move_up_requested.emit(self))
        self.btn_down.clicked.connect(lambda: self.move_down_requested.emit(self))
        self.btn_remove.clicked.connect(lambda: self.remove_requested.emit(self))

        # 이미지 행
        img_row = QHBoxLayout(); img_row.setSpacing(8)
        self.btn_image = QPushButton("📷  " + tr("画像を選択"))
        self.btn_image.setObjectName("manualImagePick")
        self.btn_image.clicked.connect(lambda: self.image_requested.emit(self))
        img_row.addWidget(self.btn_image)
        self.lbl_image = QLabel(tr("(画像なし)"))
        self.lbl_image.setObjectName("manualImageName")
        img_row.addWidget(self.lbl_image, 1)
        self.btn_img_clear = QPushButton("🗑"); self.btn_img_clear.setObjectName("manualSectionMini")
        self.btn_img_clear.setFixedSize(26, 26); self.btn_img_clear.hide()
        self.btn_img_clear.clicked.connect(self.clear_image)
        img_row.addWidget(self.btn_img_clear)

        # 본문
        self.edit_desc = AutoResizingTextEdit()
        self.edit_desc.setObjectName("manualDescEdit")
        self.edit_desc.setPlaceholderText(tr("詳細説明 (Markdown 対応: **太字**, - リスト)..."))

        layout.addLayout(hdr)
        layout.addLayout(img_row)
        layout.addWidget(self.edit_desc)

    def set_index(self, idx: int) -> None:
        self._idx_lbl.setText(str(idx))

    def set_image(self, url: str) -> None:
        self.image_url = url
        if url:
            try:
                name = url.split("/")[-1]
                if "?" in name:
                    name = name.split("?")[0]
                self.lbl_image.setText(name)
            except Exception:
                self.lbl_image.setText(url)
            self.btn_img_clear.show()
            self.btn_image.setText("📷  " + tr("画像を変更"))
        else:
            self.lbl_image.setText(tr("(画像なし)"))
            self.btn_img_clear.hide()
            self.btn_image.setText("📷  " + tr("画像を選択"))

    def clear_image(self) -> None:
        self.set_image("")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton) or not hasattr(self, "_drag_start_pos"):
            return
        if (event.position().toPoint() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return
        drag = QDrag(self)
        mime = QMimeData(); mime.setData("application/x-manual-section", b"section")
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(event.position().toPoint())
        drag.exec(Qt.MoveAction)


# ──────────────────────────────────────────────────────────────────────
# 8. ManualWorker — DB 비동기 (verbatim 보존)
# ──────────────────────────────────────────────────────────────────────
class ManualWorker(QObject):
    """공유 DB 작업을 백그라운드에서 처리."""
    result = Signal(str, object)
    error  = Signal(str)

    def __init__(self, operation: str, **kwargs):
        super().__init__()
        self.operation = operation
        self.kwargs = kwargs

    def run(self):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self._do_work(); return
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    if attempt < max_retries - 1:
                        time.sleep(1.0); continue
                    self.error.emit(tr("データベースが混雑しています。しばらくしてから再試行してください。"))
                    return
                self.error.emit(f"DB Error: {e}"); return
            except Exception as e:
                logger.error(f"ManualWorker error ({self.operation}): {e}", exc_info=True)
                self.error.emit(str(e)); return

    def _do_work(self):
        with get_shared_db() as conn:
            conn.row_factory = sqlite3.Row
            op = self.operation
            if op == "fetch_list":
                rows = conn.execute(
                    "SELECT id, title, category, tags, author_email, updated_at "
                    "FROM manuals ORDER BY sort_order ASC, updated_at DESC"
                ).fetchall()
                cat_rows = conn.execute(
                    "SELECT name FROM manual_categories ORDER BY sort_order ASC"
                ).fetchall()
                self.result.emit("list", {
                    "manuals": [dict(r) for r in rows],
                    "categories": [r[0] for r in cat_rows],
                })
            elif op == "fetch_one":
                row = conn.execute(
                    "SELECT * FROM manuals WHERE id = ?", (self.kwargs["manual_id"],),
                ).fetchone()
                self.result.emit("one", dict(row) if row else None)
            elif op == "save":
                data = self.kwargs.get("data", {})
                manual_id = data.get("id")
                now = datetime.now().isoformat()
                cat = data.get("category", _SYSTEM_CATEGORY)
                tags = data.get("tags", "")
                if manual_id:
                    conn.execute(
                        "UPDATE manuals SET title=?, category=?, tags=?, content=?, updated_at=? WHERE id=?",
                        (data["title"], cat, tags, data["content"], now, manual_id),
                    )
                else:
                    manual_id = str(uuid.uuid4())
                    author = get_current_user_email() or "unknown"
                    conn.execute(
                        "INSERT INTO manuals (id, title, category, tags, content, author_email, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (manual_id, data["title"], cat, tags, data["content"], author, now, now),
                    )
                conn.execute("INSERT OR IGNORE INTO manual_categories (name) VALUES (?)", (cat,))
                conn.commit()
                new_row = conn.execute("SELECT * FROM manuals WHERE id=?", (manual_id,)).fetchone()
                self.result.emit("save", dict(new_row))
            elif op == "delete":
                manual_id = self.kwargs["manual_id"]
                row = conn.execute("SELECT content FROM manuals WHERE id=?", (manual_id,)).fetchone()
                if row:
                    try:
                        d = json.loads(row["content"])
                        if d.get("version") == 2:
                            for sec in d.get("sections", []):
                                u = sec.get("image_url")
                                if u and u.startswith("file:///"):
                                    try:
                                        parsed = urllib.parse.urlparse(u)
                                        ip = Path(urllib.request.url2pathname(parsed.path))
                                        if ip.exists():
                                            ip.unlink()
                                            logger.info(f"添付画像を削除: {ip.name}")
                                    except Exception as e:
                                        logger.warning(f"画像削除エラー ({u}): {e}")
                    except Exception:
                        pass
                conn.execute("DELETE FROM manuals WHERE id=?", (manual_id,))
                conn.commit()
                self.result.emit("delete", manual_id)
            elif op == "rename_category":
                old, new = self.kwargs["old_name"], self.kwargs["new_name"]
                conn.execute("INSERT OR REPLACE INTO manual_categories (name) VALUES (?)", (new,))
                conn.execute("DELETE FROM manual_categories WHERE name=?", (old,))
                conn.execute("UPDATE manuals SET category=? WHERE category=?", (new, old))
                conn.commit()
                self.result.emit("category_changed", None)
            elif op == "delete_category":
                cat = self.kwargs["cat_name"]
                conn.execute("DELETE FROM manual_categories WHERE name=?", (cat,))
                conn.execute("UPDATE manuals SET category=? WHERE category=?", (_SYSTEM_CATEGORY, cat))
                conn.commit()
                self.result.emit("category_changed", None)
            elif op == "add_category":
                conn.execute("INSERT OR IGNORE INTO manual_categories (name) VALUES (?)", (self.kwargs["cat_name"],))
                conn.commit()
                self.result.emit("category_changed", None)
            elif op == "move_category":
                m_id = self.kwargs["manual_id"]
                n_cat = self.kwargs["new_category"]
                ordered = self.kwargs.get("ordered_ids", [])
                now = datetime.now().isoformat()
                conn.execute("UPDATE manuals SET category=?, updated_at=? WHERE id=?", (n_cat, now, m_id))
                for i, oid in enumerate(ordered):
                    conn.execute("UPDATE manuals SET sort_order=? WHERE id=?", (i, oid))
                conn.commit()
                self.result.emit("category_changed", None)
            elif op == "reorder_categories":
                for i, c in enumerate(self.kwargs.get("ordered_cats", [])):
                    conn.execute("UPDATE manual_categories SET sort_order=? WHERE name=?", (i, c))
                conn.commit()
                self.result.emit("category_changed", None)
            elif op == "fetch_comments":
                rows = conn.execute(
                    "SELECT * FROM manual_comments WHERE manual_id=? ORDER BY created_at ASC",
                    (self.kwargs["manual_id"],),
                ).fetchall()
                self.result.emit("comments", [dict(r) for r in rows])
            elif op == "add_comment":
                d = self.kwargs["data"]
                c_id = str(uuid.uuid4())
                now = datetime.now().isoformat()
                conn.execute(
                    "INSERT INTO manual_comments (id, manual_id, author_email, comment_text, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (c_id, d["manual_id"], d["author_email"], d["comment_text"], now),
                )
                conn.commit()
                self.result.emit("comment_added", None)
            elif op == "delete_comment":
                conn.execute("DELETE FROM manual_comments WHERE id=?", (self.kwargs["comment_id"],))
                conn.commit()
                self.result.emit("comment_deleted", None)


# ──────────────────────────────────────────────────────────────────────
# 9. ManualCard — 대시보드용 가벼운 카드 (옵션)
# ──────────────────────────────────────────────────────────────────────
class ManualCard(QFrame):
    """대시보드 카드 — 業務マニュアル 진입점 + 최근 본 항목 placeholder."""
    open_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("manualDashCard")
        self.setCursor(Qt.PointingHandCursor)
        self._is_dark = True
        self._build_ui()
        self._apply_qss()

    def _build_ui(self) -> None:
        v = QVBoxLayout(self); v.setContentsMargins(18, 16, 18, 16); v.setSpacing(10)
        head = QHBoxLayout(); head.setSpacing(10)
        head.addWidget(LeeIconTile(icon=QIcon(":/img/manual.svg"), color=_C_MANUAL, size=40, radius=10))
        title_box = QVBoxLayout(); title_box.setSpacing(2); title_box.setContentsMargins(0, 0, 0, 0)
        t = QLabel(tr("業務マニュアル")); t.setObjectName("manualDashTitle")
        s = QLabel(tr("社内ナレッジ Wiki")); s.setObjectName("manualDashSub"); s.setWordWrap(True)
        title_box.addWidget(t); title_box.addWidget(s)
        head.addLayout(title_box, 1)
        from app.ui.components import LeePill
        self._count_pill = LeePill("0", variant="info")
        head.addWidget(self._count_pill, 0, Qt.AlignTop)
        v.addLayout(head)

        # 최근 매뉴얼 미리보기 (최대 3개)
        self._recent_box = QVBoxLayout(); self._recent_box.setSpacing(3)
        v.addLayout(self._recent_box)

        self._empty_lbl = QLabel(tr("最近: —"))
        self._empty_lbl.setObjectName("manualDashRecent")
        v.addWidget(self._empty_lbl)

    def set_recent(self, title: str) -> None:
        # 호환 — 단일 제목만 받는 기존 시그니처 유지
        if title:
            self._set_recent_list([{"title": title}])
        else:
            self._set_recent_list([])

    def _set_recent_list(self, manuals: list) -> None:
        # 기존 미리보기 제거
        while self._recent_box.count() > 0:
            it = self._recent_box.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        if not manuals:
            self._empty_lbl.setVisible(True); return
        self._empty_lbl.setVisible(False)
        for m in manuals[:3]:
            cat = (m.get("category") or "未分類")[:12]
            ttl = (m.get("title") or "?")[:28]
            row = QLabel(f"<b style='color:{_C_MANUAL}'>{cat}</b>  ·  {ttl}")
            row.setObjectName("manualDashRow")
            row.setTextFormat(Qt.RichText)
            self._recent_box.addWidget(row)

    def refresh(self) -> None:
        """공유 DB 에서 매뉴얼 통계 + 최근 3개 fetch.

        DB 미초기화 / Google Drive 미연결 시 카운트 0 표시 (에러 X).
        """
        try:
            init_shared_db()
            with get_shared_db() as conn:
                conn.row_factory = sqlite3.Row
                # 카운트
                cnt = conn.execute("SELECT COUNT(*) FROM manuals").fetchone()[0]
                # 최근 3개
                rows = conn.execute(
                    "SELECT title, category FROM manuals "
                    "ORDER BY updated_at DESC LIMIT 3"
                ).fetchall()
            self._count_pill.setText(f"{cnt}")
            self._set_recent_list([dict(r) for r in rows])
        except Exception as e:
            logger.debug(f"ManualCard.refresh 실패: {e}")
            self._count_pill.setText("?")
            self._empty_lbl.setText(tr("(DB 未接続)"))
            self._empty_lbl.setVisible(True)

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    def _apply_qss(self) -> None:
        d = self._is_dark
        bg = "#14161C" if d else "#FFFFFF"
        fg_p = "#F2F4F7" if d else "#0B1220"
        fg_t = "#6B7280" if d else "#8A93A6"
        bs = "rgba(255,255,255,0.06)" if d else "rgba(11,18,32,0.06)"
        self.setStyleSheet(f"""
            QFrame#manualDashCard {{
                background: {bg}; border: 1px solid {bs};
                border-left: 4px solid {_C_MANUAL};
                border-radius: 14px;
            }}
            QFrame#manualDashCard:hover {{ border-color: {_C_MANUAL}; }}
            QLabel#manualDashTitle {{
                color: {fg_p}; background: transparent;
                font-size: 14px; font-weight: 800;
            }}
            QLabel#manualDashSub {{
                color: {fg_t}; background: transparent; font-size: 11px;
            }}
            QLabel#manualDashRecent {{
                color: {fg_t}; background: transparent; font-size: 11px;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QLabel#manualDashRow {{
                color: {fg_p}; background: transparent;
                font-size: 11px;
            }}
        """)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.open_requested.emit()
        super().mouseReleaseEvent(event)


# ──────────────────────────────────────────────────────────────────────
# 10. ManualWidget — 메인 디테일 페이지
# ──────────────────────────────────────────────────────────────────────
class ManualWidget(BaseWidget):
    """共有マニュアル (Wiki) 메인 위젯."""

    def __init__(self):
        super().__init__()
        self._current_manual: Optional[dict] = None
        self._worker_thread: Optional[QThread] = None
        self._worker_task: Optional[ManualWorker] = None
        self._is_new_manual_mode = False
        self._pending_anchor: Optional[str] = None
        self._pending_select_id: Optional[str] = None
        self._manual_cache: dict[str, dict] = {}
        self._history_stack: list[str] = []
        self._categories: list[str] = []
        self._is_admin_user = _is_admin()

        init_shared_db()
        self._build_ui()
        self._connect_signals()

        QTimer.singleShot(100, self._load_list)

    # ── 빌드 ─────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 22); outer.setSpacing(14)

        # 1) DetailHeader
        self._header = LeeDetailHeader(
            title=tr("共有マニュアル (Wiki)"),
            subtitle=tr("社内ナレッジ共有 — 全ユーザーが閲覧可能"),
            accent=_C_MANUAL,
            icon_qicon=QIcon(":/img/manual.svg"),
            badge=tr("ADMIN") if self._is_admin_user else None,
            show_export=False,
        )
        self._header.back_clicked.connect(lambda: bus.page_requested.emit(0))
        outer.addWidget(self._header)

        # 2) 외곽 카드 — 좌측 트리 + 우측 컨텐츠
        outer_card = QFrame(); outer_card.setObjectName("manualOuterCard")
        oc_lay = QHBoxLayout(outer_card); oc_lay.setContentsMargins(0, 0, 0, 0); oc_lay.setSpacing(0)
        outer.addWidget(outer_card, 1)
        self._outer_card = outer_card

        # 좌측 — 280px
        left = QFrame(); left.setObjectName("manualLeftPane")
        left.setFixedWidth(280)
        ll = QVBoxLayout(left); ll.setContentsMargins(12, 12, 12, 12); ll.setSpacing(8)
        oc_lay.addWidget(left)

        # 좌측: 검색 + 액션 행
        search_row = QHBoxLayout(); search_row.setSpacing(6)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("manualSearchInput")
        self.search_input.setPlaceholderText("🔍  " + tr("検索 (タイトル/タグ)"))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedHeight(30)
        search_row.addWidget(self.search_input, 1)
        self.btn_manage_cat = QPushButton("⚙"); self.btn_manage_cat.setObjectName("manualMiniBtn")
        self.btn_manage_cat.setFixedSize(30, 30); self.btn_manage_cat.setToolTip(tr("カテゴリ管理"))
        self.btn_refresh = QPushButton("↻"); self.btn_refresh.setObjectName("manualMiniBtn")
        self.btn_refresh.setFixedSize(30, 30); self.btn_refresh.setToolTip(tr("更新"))
        search_row.addWidget(self.btn_manage_cat); search_row.addWidget(self.btn_refresh)
        ll.addLayout(search_row)

        # 좌측: 트리
        self.manual_list = ManualTreeWidget()
        self.manual_list.setObjectName("manualTree")
        self.manual_list.setHeaderHidden(True)
        self.manual_list.setIndentation(12)
        ll.addWidget(self.manual_list, 1)

        # 좌측: 신규 버튼 (관리자 또는 모든 유저 - 모든 사용자 작성 가능)
        self.btn_new = LeeButton("＋  " + tr("新規マニュアル作成"), variant="primary", size="md")
        ll.addWidget(self.btn_new)

        # 좌-우 구분선 (1px)
        sep = QFrame(); sep.setObjectName("manualVSep"); sep.setFixedWidth(1)
        oc_lay.addWidget(sep)

        # 우측 — 컨텐츠 영역
        right = QFrame(); right.setObjectName("manualRightPane")
        rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)
        oc_lay.addWidget(right, 1)

        # 우측 상단: 툴바
        toolbar = QFrame(); toolbar.setObjectName("manualToolbar")
        tlb = QHBoxLayout(toolbar); tlb.setContentsMargins(14, 10, 14, 10); tlb.setSpacing(6)
        toolbar.setFixedHeight(54)

        self.btn_back = LeeButton("◀  " + tr("戻る"),       variant="secondary", size="sm")
        tlb.addWidget(self.btn_back)
        self.btn_back.setVisible(False)
        tlb.addStretch()

        # 모드 표시 pill (편집중 / 신규작성중)
        self._mode_pill = LeePill(tr("編集中"), variant="accent")
        tlb.addWidget(self._mode_pill)
        self._mode_pill.setVisible(False)

        # 뷰 모드 pill (閲覧のみ)
        self._readonly_pill = LeePill("👁  " + tr("閲覧のみ"), variant="info")
        tlb.addWidget(self._readonly_pill)
        self._readonly_pill.setVisible(False)

        self.btn_export_pdf = LeeButton("📄  " + tr("PDF"),        variant="secondary", size="sm")
        self.btn_copy_link  = LeeButton("🔗  " + tr("リンクコピー"), variant="secondary", size="sm")
        self.btn_edit       = LeeButton("✎  " + tr("編集"),        variant="secondary", size="sm")
        self.btn_delete     = LeeButton("🗑  " + tr("削除"),        variant="destructive", size="sm")
        for b in (self.btn_export_pdf, self.btn_copy_link, self.btn_edit, self.btn_delete):
            tlb.addWidget(b); b.setVisible(False)

        rl.addWidget(toolbar)

        # 우측: 뷰어/에디터 스택
        self.content_stack = FadeStackedWidget()
        rl.addWidget(self.content_stack, 1)

        # ── 뷰어 페이지 ────────────────────────────────────────
        viewer_page = QWidget()
        vp = QVBoxLayout(viewer_page); vp.setContentsMargins(0, 0, 0, 0); vp.setSpacing(0)
        self.viewer_splitter = QSplitter(Qt.Vertical)
        vp.addWidget(self.viewer_splitter, 1)

        # 뷰어 본문
        viewer_wrap = QFrame(); viewer_wrap.setObjectName("manualViewerWrap")
        vw_lay = QVBoxLayout(viewer_wrap); vw_lay.setContentsMargins(0, 0, 0, 0); vw_lay.setSpacing(0)
        self.viewer_tags_lbl = QLabel("")
        self.viewer_tags_lbl.setObjectName("manualViewerTags")
        self.viewer_tags_lbl.setContentsMargins(28, 16, 28, 0)
        self.viewer_tags_lbl.setVisible(False)
        vw_lay.addWidget(self.viewer_tags_lbl)
        self.viewer = ResponsiveTextBrowser()
        self.viewer.setObjectName("manualViewer")
        self.viewer.setOpenExternalLinks(False)
        self.viewer.setOpenLinks(False)
        self.viewer.setContextMenuPolicy(Qt.CustomContextMenu)
        self.viewer.viewport().setMouseTracking(True)
        self.viewer.viewport().installEventFilter(self)
        vw_lay.addWidget(self.viewer, 1)
        self.viewer_splitter.addWidget(viewer_wrap)

        # 코멘트 영역
        comment_wrap = QFrame(); comment_wrap.setObjectName("manualCommentWrap")
        cw_lay = QVBoxLayout(comment_wrap); cw_lay.setContentsMargins(20, 14, 20, 14); cw_lay.setSpacing(8)

        head = QHBoxLayout(); head.setSpacing(8)
        c_title = QLabel("💬  " + tr("コメント")); c_title.setObjectName("manualCommentTitle")
        head.addWidget(c_title)
        self._comment_count_pill = LeePill("0", variant="info")
        head.addWidget(self._comment_count_pill)
        head.addStretch()
        cw_lay.addLayout(head)

        self.comment_list = QListWidget()
        self.comment_list.setObjectName("manualCommentList")
        self.comment_list.setContextMenuPolicy(Qt.CustomContextMenu)
        cw_lay.addWidget(self.comment_list, 1)

        c_input_row = QHBoxLayout(); c_input_row.setSpacing(6)
        self.comment_input = QLineEdit()
        self.comment_input.setObjectName("manualCommentInput")
        self.comment_input.setPlaceholderText(tr("コメントを入力..."))
        self.comment_input.setFixedHeight(32)
        c_input_row.addWidget(self.comment_input, 1)
        self.btn_send_comment = LeeButton(tr("送信"), variant="primary", size="sm")
        c_input_row.addWidget(self.btn_send_comment)
        cw_lay.addLayout(c_input_row)

        self.viewer_splitter.addWidget(comment_wrap)
        self.viewer_splitter.setSizes([700, 280])
        self.content_stack.addWidget(viewer_page)

        # ── 에디터 페이지 ──────────────────────────────────────
        editor_page = QWidget()
        ep = QVBoxLayout(editor_page); ep.setContentsMargins(20, 16, 20, 16); ep.setSpacing(10)

        # 카테고리 / 제목 / 태그
        meta_row = QHBoxLayout(); meta_row.setSpacing(8)
        self.edit_category = QComboBox()
        self.edit_category.setObjectName("manualMetaInput")
        self.edit_category.setEditable(True)
        self.edit_category.setFixedHeight(32)
        self.edit_category.setMinimumWidth(160)
        meta_row.addWidget(self.edit_category)
        self.edit_title = QLineEdit()
        self.edit_title.setObjectName("manualMetaInput")
        self.edit_title.setPlaceholderText(tr("タイトル..."))
        self.edit_title.setFixedHeight(32)
        meta_row.addWidget(self.edit_title, 5)
        self.edit_tags = QLineEdit()
        self.edit_tags.setObjectName("manualMetaInput")
        self.edit_tags.setPlaceholderText(tr("タグ (カンマ区切り)"))
        self.edit_tags.setFixedHeight(32)
        meta_row.addWidget(self.edit_tags, 3)
        ep.addLayout(meta_row)

        # 섹션 스크롤
        self.sections_scroll = QScrollArea()
        self.sections_scroll.setObjectName("manualSectionsScroll")
        self.sections_scroll.setWidgetResizable(True)
        self.sections_scroll.setFrameShape(QFrame.NoFrame)
        self.sections_container = SortableSectionsContainer()
        self.sections_layout = QVBoxLayout(self.sections_container)
        self.sections_layout.setContentsMargins(0, 0, 0, 0); self.sections_layout.setSpacing(10)
        self.sections_layout.addStretch()
        self.sections_layout.setAlignment(Qt.AlignTop)
        self.sections_scroll.setWidget(self.sections_container)
        ep.addWidget(self.sections_scroll, 1)

        self.btn_add_section = LeeButton("＋  " + tr("項目を追加"), variant="secondary", size="md")
        ep.addWidget(self.btn_add_section)

        # 저장/취소
        edit_actions = QHBoxLayout(); edit_actions.setSpacing(8)
        edit_actions.addStretch()
        self.btn_cancel = LeeButton(tr("キャンセル"), variant="ghost", size="md")
        self.btn_save = LeeButton(tr("保存"), variant="primary", size="md")
        edit_actions.addWidget(self.btn_cancel); edit_actions.addWidget(self.btn_save)
        ep.addLayout(edit_actions)

        self.content_stack.addWidget(editor_page)

    def _connect_signals(self) -> None:
        self.search_input.textChanged.connect(self._filter_tree)
        self.btn_manage_cat.clicked.connect(self._open_category_manager)
        self.btn_refresh.clicked.connect(self._load_list)

        self.manual_list.itemSelectionChanged.connect(self._on_list_selection_changed)
        self.manual_list.item_moved.connect(self._on_manual_moved)

        self.btn_new.clicked.connect(self._show_editor_for_new)
        self.btn_save.clicked.connect(self._save_manual)
        self.btn_cancel.clicked.connect(self._cancel_edit)
        self.btn_edit.clicked.connect(self._show_editor_for_edit)
        self.btn_delete.clicked.connect(self._delete_manual)
        self.btn_back.clicked.connect(self._go_back)
        self.btn_copy_link.clicked.connect(self._copy_deep_link)
        self.btn_export_pdf.clicked.connect(self._export_pdf)
        self.btn_add_section.clicked.connect(self._add_empty_section)

        self.viewer.customContextMenuRequested.connect(self._show_viewer_context_menu)
        self.viewer.anchorClicked.connect(self._on_anchor_clicked)

        self.comment_list.customContextMenuRequested.connect(self._show_comment_menu)
        self.btn_send_comment.clicked.connect(self._add_comment)
        self.comment_input.returnPressed.connect(self._add_comment)

    # ── 테마 ─────────────────────────────────────────────────
    def apply_theme_custom(self) -> None:
        self._header.set_theme(self.is_dark)
        self._apply_qss()
        if self._current_manual:
            self._render_viewer_html()
        for i in range(self.sections_layout.count() - 1):
            w = self.sections_layout.itemAt(i).widget()
            if isinstance(w, ManualSectionWidget):
                self._style_section(w)

    def _apply_qss(self) -> None:
        d = self.is_dark
        bg_surface    = "#14161C" if d else "#FFFFFF"
        bg_surface_2  = "#1B1E26" if d else "#F0F2F5"
        bg_surface_3  = "#232730" if d else "#E6E9EE"
        fg_primary    = "#F2F4F7" if d else "#0B1220"
        fg_secondary  = "#A8B0BD" if d else "#4A5567"
        border_subtle = "rgba(255,255,255,0.06)" if d else "rgba(11,18,32,0.06)"
        accent        = _C_MANUAL
        accent_bg     = "rgba(88,86,214,0.18)" if d else "rgba(88,86,214,0.12)"

        self.setStyleSheet(f"""
            QFrame#manualOuterCard {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 16px;
            }}
            QFrame#manualLeftPane {{
                background: {bg_surface_2};
                border-top-left-radius: 16px;
                border-bottom-left-radius: 16px;
            }}
            QFrame#manualVSep {{ background: {border_subtle}; }}
            QFrame#manualRightPane {{
                background: {bg_surface};
                border-top-right-radius: 16px;
                border-bottom-right-radius: 16px;
            }}
            QFrame#manualToolbar {{
                background: {bg_surface};
                border-bottom: 1px solid {border_subtle};
            }}

            QLineEdit#manualSearchInput, QLineEdit#manualMetaInput {{
                background: {bg_surface}; color: {fg_primary};
                border: 1px solid {border_subtle}; border-radius: 7px;
                padding: 0 10px; font-size: 11.5px;
            }}
            QLineEdit#manualSearchInput:focus, QLineEdit#manualMetaInput:focus {{
                border: 1px solid {accent};
            }}
            QComboBox#manualMetaInput {{
                background: {bg_surface}; color: {fg_primary};
                border: 1px solid {border_subtle}; border-radius: 7px;
                padding: 0 10px; font-size: 12px;
            }}
            QPushButton#manualMiniBtn {{
                background: {bg_surface}; color: {fg_secondary};
                border: 1px solid {border_subtle}; border-radius: 7px;
                font-size: 13px; font-weight: 800;
            }}
            QPushButton#manualMiniBtn:hover {{
                background: {bg_surface_3}; color: {fg_primary};
            }}

            QTreeWidget#manualTree {{
                background: transparent;
                color: {fg_primary};
                border: none; outline: 0;
                font-size: 11.5px;
            }}
            QTreeWidget#manualTree::item {{
                padding: 5px 6px; border-radius: 6px;
            }}
            QTreeWidget#manualTree::item:selected {{
                background: {accent_bg}; color: {accent};
            }}
            QTreeWidget#manualTree::item:hover:!selected {{
                background: {bg_surface_3};
            }}
            QTreeWidget#manualTree::branch {{ background: transparent; }}

            QTextBrowser#manualViewer {{
                background: {bg_surface};
                color: {fg_primary};
                border: none;
                padding: 24px 36px;
                font-size: 13.5px;
            }}
            QFrame#manualViewerWrap {{ background: {bg_surface}; }}
            QLabel#manualViewerTags {{
                background: {bg_surface}; padding-bottom: 4px;
            }}

            QFrame#manualCommentWrap {{
                background: {bg_surface_2};
                border-top: 1px solid {border_subtle};
            }}
            QLabel#manualCommentTitle {{
                color: {fg_secondary}; font-size: 12px; font-weight: 800;
                background: transparent; letter-spacing: 0.04em;
            }}
            QListWidget#manualCommentList {{
                background: {bg_surface};
                color: {fg_primary};
                border: 1px solid {border_subtle}; border-radius: 10px;
                padding: 4px;
                font-size: 12px;
            }}
            QListWidget#manualCommentList::item {{
                padding: 8px 10px;
                border-radius: 6px;
                margin: 2px 0;
            }}
            QListWidget#manualCommentList::item:hover {{
                background: {bg_surface_2};
            }}
            QLineEdit#manualCommentInput {{
                background: {bg_surface}; color: {fg_primary};
                border: 1px solid {border_subtle}; border-radius: 7px;
                padding: 0 10px; font-size: 12px;
            }}
            QLineEdit#manualCommentInput:focus {{ border: 1px solid {accent}; }}

            QScrollArea#manualSectionsScroll {{
                background: transparent; border: none;
            }}
        """)

    def _style_section(self, w: "ManualSectionWidget") -> None:
        d = self.is_dark
        bg            = "#1B1E26" if d else "#F0F2F5"
        bg_sub        = "#14161C" if d else "#FFFFFF"
        fg_primary    = "#F2F4F7" if d else "#0B1220"
        fg_tertiary   = "#6B7280" if d else "#8A93A6"
        border_subtle = "rgba(255,255,255,0.06)" if d else "rgba(11,18,32,0.06)"
        border        = "rgba(255,255,255,0.10)" if d else "rgba(11,18,32,0.10)"
        accent        = _C_MANUAL

        w.setStyleSheet(f"""
            QFrame#manualSection {{
                background: {bg}; border: 1px solid {border_subtle};
                border-radius: 10px;
            }}
            QLabel#manualSectionIdx {{
                background: {accent}; color: white;
                border-radius: 6px;
                font-size: 11px; font-weight: 800;
            }}
            QLineEdit#manualSectionTitle {{
                background: {bg_sub}; color: {fg_primary};
                border: 1px solid {border_subtle}; border-radius: 7px;
                padding: 0 10px; font-size: 12.5px; font-weight: 700;
            }}
            QLineEdit#manualSectionTitle:focus {{ border: 1px solid {accent}; }}
            QPushButton#manualSectionMini {{
                background: {bg_sub}; color: {fg_primary};
                border: 1px solid {border_subtle}; border-radius: 6px;
                font-size: 10px; font-weight: 800;
            }}
            QPushButton#manualSectionMini:hover {{ background: {bg}; }}
            QPushButton#manualSectionMini[danger="true"]:hover {{
                color: {_C_BAD}; border: 1px solid {_C_BAD};
            }}
            QPushButton#manualImagePick {{
                background: {bg_sub}; color: {fg_primary};
                border: 1px dashed {border}; border-radius: 7px;
                padding: 6px 12px; font-size: 11px; font-weight: 700;
            }}
            QPushButton#manualImagePick:hover {{
                background: {bg};
                color: {accent}; border: 1px dashed {accent};
            }}
            QLabel#manualImageName {{
                color: {fg_tertiary}; background: transparent;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 10.5px;
            }}
            QTextEdit#manualDescEdit {{
                background: {bg_sub}; color: {fg_primary};
                border: 1px solid {border_subtle}; border-radius: 7px;
                padding: 8px 10px; font-size: 12px;
            }}
            QTextEdit#manualDescEdit:focus {{ border: 1px solid {accent}; }}
        """)

    # ── Worker 호출 ─────────────────────────────────────────────
    def _run_worker(self, operation: str, **kwargs) -> None:
        try:
            if self._worker_thread and self._worker_thread.isRunning():
                if getattr(self, "_current_operation", None) == operation:
                    return
        except RuntimeError:
            self._worker_thread = None

        if self._worker_task:
            try:
                self._worker_task.result.disconnect()
                self._worker_task.error.disconnect()
            except (RuntimeError, TypeError):
                pass

        self._current_operation = operation
        self._worker_thread = QThread()
        self._worker_task = ManualWorker(operation, **kwargs)
        self._worker_task.moveToThread(self._worker_thread)

        self._worker_task.result.connect(self._on_worker_result)
        self._worker_task.error.connect(self._on_worker_error)

        self._worker_thread.started.connect(self._worker_task.run)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.finished.connect(self._worker_task.deleteLater)
        self._worker_task.result.connect(self._worker_thread.quit)
        self._worker_task.error.connect(self._worker_thread.quit)

        self._worker_thread.start()
        self.track_worker(self._worker_thread)

    def _on_worker_result(self, operation: str, data: object) -> None:
        self.set_loading(False)
        if operation == "list":
            self._populate_list(data)
        elif operation == "one":
            if data:
                self._manual_cache[data["id"]] = data
            self._display_content(data)
        elif operation == "save":
            self._on_save_finished(data)
        elif operation == "delete":
            self._on_delete_finished(data)
        elif operation == "comments":
            self._populate_comments(data)
        elif operation in ("comment_added", "comment_deleted"):
            if self._current_manual:
                self._run_worker("fetch_comments", manual_id=self._current_manual["id"])
        elif operation == "category_changed":
            if self._current_manual:
                self._pending_select_id = self._current_manual["id"]
            self._load_list()

    def _on_worker_error(self, error_msg: str) -> None:
        self.set_loading(False)
        LeeDialog.error(tr("エラー"), error_msg, parent=self)

    # ── 리스트 ──────────────────────────────────────────────────
    def _load_list(self) -> None:
        self.set_loading(True, self.manual_list)
        self._run_worker("fetch_list")

    def _populate_list(self, data: dict) -> None:
        manuals = data.get("manuals", [])
        saved_cats = data.get("categories", [])

        self.set_loading(False, self.manual_list)
        self.manual_list.clear()
        self._categories = list(saved_cats)
        # _SYSTEM_CATEGORY 가 없으면 항상 추가
        if _SYSTEM_CATEGORY not in self._categories:
            self._categories.append(_SYSTEM_CATEGORY)

        if not manuals:
            ph = QTreeWidgetItem([tr("(マニュアルなし)")])
            ph.setFlags(ph.flags() & ~Qt.ItemIsSelectable)
            self.manual_list.addTopLevelItem(ph)
            self._update_category_combo()
            return

        grouped: dict[str, list] = {c: [] for c in self._categories}
        for m in manuals:
            cat = m.get("category") or _SYSTEM_CATEGORY
            if cat not in self._categories:
                self._categories.append(cat); grouped.setdefault(cat, [])
            grouped.setdefault(cat, []).append(m)

        for cat in self._categories:
            items = grouped.get(cat, [])
            if not items:
                # 매뉴얼이 없는 카테고리도 (관리용으로) 표시
                cat_item = QTreeWidgetItem([f"{cat}  0"])
                cat_item.setFlags(cat_item.flags() & ~Qt.ItemIsSelectable)
                f = cat_item.font(0); f.setBold(True); cat_item.setFont(0, f)
                self.manual_list.addTopLevelItem(cat_item)
                continue
            cat_item = QTreeWidgetItem([f"{cat}  {len(items)}"])
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemIsSelectable)
            f = cat_item.font(0); f.setBold(True); cat_item.setFont(0, f)
            self.manual_list.addTopLevelItem(cat_item)
            for m in items:
                m_item = QTreeWidgetItem([m["title"]])
                m_item.setData(0, Qt.UserRole, m["id"])
                m_item.setData(0, Qt.UserRole + 1, m.get("tags", ""))
                cat_item.addChild(m_item)
            cat_item.setExpanded(True)

        self._update_category_combo()

        # 새 글 작성/수정 후 비동기 로딩 완료 후 선택
        if self._pending_select_id:
            for i in range(self.manual_list.topLevelItemCount()):
                parent = self.manual_list.topLevelItem(i)
                for j in range(parent.childCount()):
                    child = parent.child(j)
                    if child.data(0, Qt.UserRole) == self._pending_select_id:
                        self.manual_list.setCurrentItem(child)
                        break
            self._pending_select_id = None

    def _update_category_combo(self) -> None:
        current = self.edit_category.currentText()
        self.edit_category.clear()
        self.edit_category.addItem(_SYSTEM_CATEGORY)
        cats = [c for c in self._categories if c != _SYSTEM_CATEGORY]
        self.edit_category.addItems(cats)
        if current:
            self.edit_category.setCurrentText(current)

    def _filter_tree(self, text: str) -> None:
        text = text.lower().strip()
        for i in range(self.manual_list.topLevelItemCount()):
            cat_item = self.manual_list.topLevelItem(i)
            cat_match = text in cat_item.text(0).lower()
            any_child_match = False
            for j in range(cat_item.childCount()):
                child = cat_item.child(j)
                tags = child.data(0, Qt.UserRole + 1) or ""
                child_match = text in child.text(0).lower() or text in tags.lower()
                child.setHidden(not (child_match or cat_match))
                if child_match: any_child_match = True
            cat_item.setHidden(not (cat_match or any_child_match) if text else False)

    def _open_category_manager(self) -> None:
        if not self._is_admin_user:
            LeeDialog.info(tr("権限なし"), tr("カテゴリ管理は管理者のみ可能です。"), parent=self)
            return
        cats = [c for c in self._categories if c != _SYSTEM_CATEGORY]
        dlg = CategoryManagerDialog(cats, self.is_dark, self)
        result = dlg.exec()
        if result == QDialog.Accepted and dlg.action_taken:
            if self._current_manual:
                self._pending_select_id = self._current_manual["id"]
            if dlg.action_type == "add":
                self._run_worker("add_category", cat_name=dlg.new_name); return
            self.set_loading(True)
            if dlg.action_type == "rename":
                self._run_worker("rename_category", old_name=dlg.old_name, new_name=dlg.new_name)
            elif dlg.action_type == "delete":
                self._run_worker("delete_category", cat_name=dlg.old_name)
        elif result == QDialog.Accepted:
            new_order = dlg.get_ordered_categories()
            if new_order != cats:
                self.set_loading(True)
                self._run_worker("reorder_categories", ordered_cats=new_order)

    def _on_manual_moved(self, manual_id: str, new_category: str, ordered_ids: list) -> None:
        if not self._is_admin_user and not _can_edit_manual(self._manual_cache.get(manual_id, {})):
            self._load_list(); return
        self.set_loading(True)
        self._pending_select_id = manual_id
        self._run_worker("move_category", manual_id=manual_id,
                         new_category=new_category, ordered_ids=ordered_ids)

    def _on_list_selection_changed(self) -> None:
        items = self.manual_list.selectedItems()
        if not items: return
        cur = items[0]
        if not cur.data(0, Qt.UserRole):
            return
        manual_id = cur.data(0, Qt.UserRole)
        if self._current_manual and self._current_manual["id"] == manual_id:
            return
        if self._current_manual and self._current_manual["id"] != manual_id:
            self._history_stack.append(self._current_manual["id"])
        self._load_manual_by_id(manual_id)

    def _load_manual_by_id(self, manual_id: str) -> None:
        if manual_id in self._manual_cache:
            self._display_content(self._manual_cache[manual_id])
        else:
            self.set_loading(True, self.viewer)
        self._run_worker("fetch_one", manual_id=manual_id)

    # ── 뷰어 ────────────────────────────────────────────────────
    def _display_content(self, manual: Optional[dict]) -> None:
        self.set_loading(False, self.viewer)
        self._current_manual = manual
        if not manual:
            self._update_ui_for_no_selection(); return

        self._render_viewer_html()
        self._update_toolbar_permissions()
        self.content_stack.setCurrentIndex(0)

        if self._pending_anchor:
            try:
                block_num = int(self._pending_anchor)
                doc = self.viewer.document()
                if 0 <= block_num < doc.blockCount():
                    block = doc.findBlockByNumber(block_num)
                    cursor = self.viewer.textCursor()
                    cursor.setPosition(block.position())
                    self.viewer.setTextCursor(cursor)
                    self.viewer.ensureCursorVisible()
                    self._highlight_block(block)
            except (ValueError, TypeError):
                pass
            finally:
                self._pending_anchor = None

        self._run_worker("fetch_comments", manual_id=manual["id"])

    def _render_viewer_html(self) -> None:
        if not self._current_manual:
            return
        manual = self._current_manual
        content_raw = manual.get("content", "")

        # v2 JSON sections → markdown 합성
        md = ""
        try:
            data = json.loads(content_raw)
            if data.get("version") == 2:
                md = f"# {manual.get('title', '')}\n\n"
                for i, sec in enumerate(data.get("sections", [])):
                    if sec.get("subtitle"):
                        md += f"## {i + 1}. {sec['subtitle']}\n\n"
                    if sec.get("image_url"):
                        md += f"![image]({sec['image_url']})\n"
                    if sec.get("description"):
                        desc = re.sub(
                            r'(?<![="\'\[<])(?:https?://|lee://manual/)[^\s()<>"]+',
                            lambda m: f"<{m.group(0)}>", sec["description"],
                        )
                        md += f"{desc}\n\n"
                    elif sec.get("image_url"):
                        md += "\n"
                    md += "---\n\n"
            else:
                md = content_raw
        except json.JSONDecodeError:
            md = content_raw

        from PySide6.QtGui import QTextDocument
        temp_doc = QTextDocument()
        temp_doc.setMarkdown(md)
        html = temp_doc.toHtml()

        d = self.is_dark
        accent       = _C_MANUAL
        text_color   = "#F2F4F7" if d else "#0B1220"
        text_sec     = "#A8B0BD" if d else "#4A5567"
        bg_card      = "#1B1E26" if d else "#F8F9FC"
        code_bg      = "#232730" if d else "#F0F2F5"
        code_fg      = "#FF9F0A"
        border_c     = "rgba(255,255,255,0.08)" if d else "rgba(11,18,32,0.08)"
        h_line       = "rgba(255,255,255,0.06)" if d else "rgba(11,18,32,0.06)"
        tag_bg       = "rgba(88,86,214,0.15)" if d else "rgba(88,86,214,0.10)"

        # 인라인 스타일 정리
        for prop in (
            r'margin-[a-z]+:[^;"]+;?',
            r'-qt-block-indent:[^;"]+;?',
            r'text-indent:[^;"]+;?',
            r'font-[a-z]+:[^;"]+;?',
            r'color:[^;"]+;?',
            r'background-color:[^;"]+;?',
        ):
            html = re.sub(prop, "", html)
        html = re.sub(r'\s*style="\s*"', "", html)
        html = re.sub(r"<p>\s*<br\s*/?>\s*</p>|<p>\s*</p>", "", html)

        # 헤딩 — accent 라인
        html = re.sub(
            r'<h1[^>]*>',
            f'<h1 style="color:{accent}; font-size:24px; font-weight:800; '
            f'margin:2px 0 12px; padding-bottom:6px; border-bottom:2px solid {accent};">',
            html,
        )
        html = re.sub(
            r'<h2[^>]*>',
            f'<h2 style="color:{text_color}; font-size:17px; font-weight:700; '
            f'margin:18px 0 8px; padding-left:12px; border-left:4px solid {accent};">',
            html,
        )
        html = re.sub(
            r'<h3[^>]*>',
            f'<h3 style="color:{text_color}; font-size:14px; font-weight:600; '
            f'margin:14px 0 6px;">',
            html,
        )

        # 인용/코드 — 카드형
        html = re.sub(
            r'<blockquote[^>]*>(.*?)</blockquote>',
            rf'<table width="100%" style="margin:10px 0; background:{bg_card}; '
            rf'border-radius:8px; border:1px solid {border_c};" cellspacing="0" cellpadding="12">'
            rf'<tr><td style="color:{text_color}; font-size:13.5px; line-height:1.6;">\1</td></tr></table>',
            html, flags=re.DOTALL,
        )
        html = re.sub(
            r'<pre[^>]*>(.*?)</pre>',
            rf'<table width="100%" style="margin:10px 0; background:{code_bg}; '
            rf'border-radius:8px; border:1px solid {border_c};" cellspacing="0" cellpadding="12">'
            rf'<tr><td><pre style="margin:0; font-family:\'Consolas\', monospace; '
            rf'font-size:12.5px; color:{text_color}; line-height:1.5;">\1</pre></td></tr></table>',
            html, flags=re.DOTALL,
        )

        # hr
        html = re.sub(
            r'<hr[^>]*>',
            f'<hr style="background:{h_line}; height:1px; border:none; margin:20px 0;" />',
            html,
        )

        css = f"""
            <style>
            body {{
                font-family: 'Pretendard', 'Noto Sans JP', '-apple-system', 'Segoe UI', sans-serif;
                font-size: 13.5px; color: {text_color}; line-height: 1.7;
            }}
            p {{ margin: 2px 0 8px; }}
            img {{ display: block; margin: 6px 0; border-radius: 8px; }}
            a {{ color: {accent}; text-decoration: none; font-weight: 600; }}
            table {{ border-collapse: collapse; margin: 14px 0; width: 100%; border: 1px solid {border_c}; }}
            th {{ background: {bg_card}; color: {text_color}; font-weight: 700;
                  padding: 12px; border-bottom: 1px solid {border_c}; text-align: left; font-size: 13px; }}
            td {{ border-bottom: 1px solid {border_c}; padding: 12px; font-size: 13px; }}
            code {{ font-family: 'Consolas', monospace; color: {code_fg};
                    background: {code_bg}; padding: 2px 6px; font-size: 12.5px; border-radius: 4px; }}
            ul, ol {{ margin: 4px 0 12px 24px; }}
            li {{ margin-bottom: 5px; }}
            </style>
        """
        html = html.replace("</head>", f"{css}</head>")
        self.viewer.setHtml(html)

        # 메타 — 작성자/일자/카테고리
        meta_html = (
            f"<span style='color:{text_sec}; font-size:11.5px;'>"
            f"👤 {(manual.get('author_email') or '').split('@')[0]}"
            f" &nbsp;·&nbsp; 📅 {(manual.get('updated_at') or '')[:16].replace('T', ' ')}"
            f" &nbsp;·&nbsp; "
            f"<span style='background:{bg_card}; padding:2px 8px; border-radius:4px;'>"
            f"{manual.get('category') or _SYSTEM_CATEGORY}</span></span>"
        )

        # 태그
        tags = (manual.get("tags") or "").strip()
        tag_html = ""
        if tags:
            tag_html = " ".join(
                f"<span style='background:{tag_bg}; color:{accent}; "
                f"padding:3px 10px; font-size:10.5px; font-weight:800; "
                f"border-radius:999px; border:1px solid {border_c}; margin-right:5px;'>"
                f"#{t.strip()}</span>"
                for t in tags.split(",") if t.strip()
            )

        if tags or meta_html:
            self.viewer_tags_lbl.setText(tag_html + ("<br/>" if tag_html else "") + meta_html)
            self.viewer_tags_lbl.setVisible(True)
        else:
            self.viewer_tags_lbl.setVisible(False)

    def _update_toolbar_permissions(self) -> None:
        has_sel = self._current_manual is not None
        can_edit = _can_edit_manual(self._current_manual) if has_sel else False
        self.btn_edit.setVisible(has_sel and can_edit)
        self.btn_delete.setVisible(has_sel and can_edit)
        self.btn_copy_link.setVisible(has_sel)
        self.btn_export_pdf.setVisible(has_sel)
        self.btn_back.setVisible(len(self._history_stack) > 0)
        # 모드 pill
        self._mode_pill.setVisible(False)
        self._readonly_pill.setVisible(has_sel and not can_edit)

    def _update_ui_for_no_selection(self) -> None:
        self.viewer.clear()
        self.viewer.setPlaceholderText(tr("マニュアルを選択してください"))
        self.viewer_tags_lbl.setVisible(False)
        self.btn_edit.setVisible(False)
        self.btn_delete.setVisible(False)
        self.btn_copy_link.setVisible(False)
        self.btn_export_pdf.setVisible(False)
        self.btn_back.setVisible(False)
        self._mode_pill.setVisible(False)
        self._readonly_pill.setVisible(False)
        self.comment_list.clear()
        self._comment_count_pill.setText("0")

    # ── 에디터 ───────────────────────────────────────────────────
    def _show_editor_for_new(self) -> None:
        self._is_new_manual_mode = True
        self._current_manual = None
        self.edit_title.clear()
        self.edit_tags.clear()
        self.edit_category.setCurrentText(_SYSTEM_CATEGORY)
        self._clear_sections()
        self._add_empty_section()
        self.content_stack.setCurrentIndex(1)
        self.edit_title.setFocus()
        # 모드 pill 표시
        self._mode_pill.setText(tr("新規作成中"))
        self._mode_pill.setVisible(True)
        self._readonly_pill.setVisible(False)
        for b in (self.btn_edit, self.btn_delete, self.btn_copy_link, self.btn_export_pdf):
            b.setVisible(False)

    def _show_editor_for_edit(self) -> None:
        if not self._current_manual:
            return
        self._is_new_manual_mode = False
        self.edit_title.setText(self._current_manual.get("title", ""))
        self.edit_tags.setText(self._current_manual.get("tags", ""))
        self.edit_category.setCurrentText(self._current_manual.get("category", _SYSTEM_CATEGORY))
        self._clear_sections()
        content_raw = self._current_manual.get("content", "")
        try:
            data = json.loads(content_raw)
            if data.get("version") == 2:
                for sec in data.get("sections", []):
                    self._add_section(
                        sec.get("subtitle", ""), sec.get("image_url", ""),
                        sec.get("description", ""),
                    )
            else:
                self._add_section("", "", content_raw)
        except json.JSONDecodeError:
            self._add_section("", "", content_raw)
        self.content_stack.setCurrentIndex(1)
        self._mode_pill.setText(tr("編集中"))
        self._mode_pill.setVisible(True)
        self._readonly_pill.setVisible(False)
        for b in (self.btn_edit, self.btn_delete, self.btn_copy_link, self.btn_export_pdf):
            b.setVisible(False)

    def _cancel_edit(self) -> None:
        if self._current_manual:
            self._display_content(self._current_manual)
        else:
            self._update_ui_for_no_selection()
        self.content_stack.setCurrentIndex(0)
        self._update_toolbar_permissions()

    def _save_manual(self) -> None:
        title = self.edit_title.text().strip()
        if not title:
            LeeDialog.error(tr("エラー"), tr("タイトルを入力してください。"), parent=self)
            return
        sections_data = []
        for i in range(self.sections_layout.count() - 1):
            w = self.sections_layout.itemAt(i).widget()
            if isinstance(w, ManualSectionWidget):
                sections_data.append({
                    "subtitle": w.edit_subtitle.text().strip(),
                    "image_url": w.image_url,
                    "description": w.edit_desc.toPlainText(),
                })
        cat = self.edit_category.currentText().strip() or _SYSTEM_CATEGORY
        tags = self.edit_tags.text().strip()
        content_json = json.dumps({"version": 2, "sections": sections_data}, ensure_ascii=False)
        data = {"title": title, "category": cat, "tags": tags, "content": content_json}
        if not self._is_new_manual_mode and self._current_manual:
            data["id"] = self._current_manual.get("id")
        self.set_loading(True)
        self._run_worker("save", data=data)

    def _on_save_finished(self, saved_manual: dict) -> None:
        self._history_stack.clear()
        self._pending_select_id = saved_manual.get("id")
        self._load_list()
        self.content_stack.setCurrentIndex(0)
        self._update_toolbar_permissions()

    def _delete_manual(self) -> None:
        if not self._current_manual:
            return
        title = self._current_manual.get("title", "Untitled")
        if not LeeDialog.confirm(
            tr("削除の確認"),
            tr("「{0}」を削除しますか?").format(title),
            ok_text=tr("削除"), destructive=True, parent=self,
        ):
            return
        self.set_loading(True)
        self._run_worker("delete", manual_id=self._current_manual.get("id"))

    def _on_delete_finished(self, _deleted_id: str) -> None:
        self._current_manual = None
        self._update_ui_for_no_selection()
        self._load_list()

    def _export_pdf(self) -> None:
        if not self._current_manual:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("PDF 保存"),
            f"{self._current_manual.get('title', 'manual')}.pdf",
            "PDF Files (*.pdf)",
        )
        if not path:
            return
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(path)
        self.viewer.document().print_(printer)
        bus.toast_requested.emit(tr("PDFファイルとして保存しました。"), "success")

    # ── 섹션 ────────────────────────────────────────────────────
    def _clear_sections(self) -> None:
        while self.sections_layout.count() > 1:
            item = self.sections_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _add_empty_section(self) -> None:
        self._add_section("", "", "")

    def _add_section(self, subtitle: str, image_url: str, description: str) -> ManualSectionWidget:
        sec = ManualSectionWidget(self)
        sec.edit_subtitle.setText(subtitle)
        sec.set_image(image_url)
        sec.edit_desc.setPlainText(description)
        self._style_section(sec)

        sec.remove_requested.connect(self._remove_section)
        sec.move_up_requested.connect(self._move_section_up)
        sec.move_down_requested.connect(self._move_section_down)
        sec.image_requested.connect(self._attach_section_image)
        sec.edit_desc.image_dropped.connect(
            lambda img, _editor: self._attach_section_image_from_data(sec, img)
        )

        idx = self.sections_layout.count() - 1
        self.sections_layout.insertWidget(idx, sec)
        self._reindex_sections()
        return sec

    def _remove_section(self, sec: ManualSectionWidget) -> None:
        self.sections_layout.removeWidget(sec)
        sec.deleteLater()
        QTimer.singleShot(0, self._reindex_sections)

    def _move_section_up(self, sec: ManualSectionWidget) -> None:
        idx = self.sections_layout.indexOf(sec)
        if idx > 0:
            self.sections_layout.takeAt(idx)
            self.sections_layout.insertWidget(idx - 1, sec)
            self._reindex_sections()

    def _move_section_down(self, sec: ManualSectionWidget) -> None:
        idx = self.sections_layout.indexOf(sec)
        if idx < self.sections_layout.count() - 2:
            self.sections_layout.takeAt(idx)
            self.sections_layout.insertWidget(idx + 1, sec)
            self._reindex_sections()

    def _reindex_sections(self) -> None:
        n = 1
        for i in range(self.sections_layout.count() - 1):
            w = self.sections_layout.itemAt(i).widget()
            if isinstance(w, ManualSectionWidget):
                w.set_index(n); n += 1

    # ── 이미지 attachment ──────────────────────────────────────
    def _edit_and_save_image(self, image: QImage) -> str:
        dlg = ImageEditDialog(image, self)
        if dlg.exec() == QDialog.Accepted:
            edited = dlg.get_edited_image()
            if edited.width() > 1200:
                edited = edited.scaledToWidth(1200, Qt.SmoothTransformation)
            new_filename = f"{uuid.uuid4().hex}.jpg"
            dest = SHARED_IMAGE_DIR / new_filename
            if edited.save(str(dest), "JPEG", 80):
                return dest.as_uri()
            raise IOError("Failed to save image.")
        return ""

    def _attach_section_image_from_data(self, section: ManualSectionWidget, image: QImage) -> None:
        try:
            url = self._edit_and_save_image(image)
            if url:
                section.set_image(url)
        except Exception as e:
            LeeDialog.error(tr("エラー"), str(e), parent=self)

    def _attach_section_image(self, section: ManualSectionWidget) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("画像を選択"), "", "Images (*.png *.jpg *.jpeg *.gif)",
        )
        if not path:
            return
        image = QImage(path)
        if image.isNull():
            LeeDialog.error(tr("エラー"), tr("画像の読み込みに失敗しました。"), parent=self)
            return
        try:
            url = self._edit_and_save_image(image)
            if url:
                section.set_image(url)
        except Exception as e:
            LeeDialog.error(tr("エラー"), str(e), parent=self)

    # ── 이미지 미리보기 (뷰어 클릭) ─────────────────────────────
    def eventFilter(self, obj, event):
        if obj is self.viewer.viewport():
            if event.type() == QEvent.Type.MouseMove:
                cursor = self.viewer.cursorForPosition(event.pos())
                if cursor.charFormat().isImageFormat():
                    self.viewer.viewport().setCursor(Qt.PointingHandCursor)
                else:
                    self.viewer.viewport().unsetCursor()
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.LeftButton:
                    cursor = self.viewer.cursorForPosition(event.pos())
                    if cursor.charFormat().isImageFormat():
                        name = cursor.charFormat().toImageFormat().name()
                        if name:
                            self._show_image_popup(name)
                            return True
        return super().eventFilter(obj, event)

    def _show_image_popup(self, image_name: str) -> None:
        dlg = ImagePreviewDialog(image_name, self)
        dlg.exec()

    # ── 딥링크 / 히스토리 ───────────────────────────────────────
    def _on_anchor_clicked(self, url: QUrl) -> None:
        scheme = url.scheme().lower()
        url_str = url.toString()
        if scheme == "lee" and "manual" in url_str:
            target_id = url_str.split("manual/")[-1].split("#")[0].strip("/")
            self._pending_anchor = url.fragment() if url.hasFragment() else None
            found = False
            for i in range(self.manual_list.topLevelItemCount()):
                parent = self.manual_list.topLevelItem(i)
                for j in range(parent.childCount()):
                    child = parent.child(j)
                    if child.data(0, Qt.UserRole) == target_id:
                        self.manual_list.setCurrentItem(child); found = True; break
                if found: break
            if not found:
                if self._current_manual and self._current_manual["id"] != target_id:
                    self._history_stack.append(self._current_manual["id"])
                self._load_manual_by_id(target_id)
        elif scheme in ("http", "https", "ftp", "mailto"):
            QDesktopServices.openUrl(url)
        elif not scheme and url.hasFragment():
            self.viewer.scrollToAnchor(url.fragment())

    def _go_back(self) -> None:
        if self._history_stack:
            self._load_manual_by_id(self._history_stack.pop())

    def _copy_deep_link(self) -> None:
        if not self._current_manual:
            return
        link = f"lee://manual/{self._current_manual['id']}"
        QApplication.clipboard().setText(link)
        bus.toast_requested.emit(tr("リンクをクリップボードにコピーしました。"), "success")

    def _show_viewer_context_menu(self, pos) -> None:
        if not self._current_manual:
            return
        cursor = self.viewer.cursorForPosition(pos)
        block = cursor.block()
        if not block.isValid():
            return
        block_num = block.blockNumber()
        manual_id = self._current_manual["id"]
        anchor_link = f"lee://manual/{manual_id}#{block_num}"
        menu = QMenu(self)
        copy_action = menu.addAction(tr("この段落へのリンクをコピー"))
        action = menu.exec(QCursor.pos())
        if action == copy_action:
            QApplication.clipboard().setText(anchor_link)
            bus.toast_requested.emit(tr("アンカーリンクをコピーしました。"), "success")

    def _highlight_block(self, block) -> None:
        self.viewer.setExtraSelections([])
        sel = QTextEdit.ExtraSelection()
        sel.cursor = QTextCursor(block)
        fmt = QTextCharFormat()
        color = QColor(_C_MANUAL); color.setAlpha(80 if self.is_dark else 50)
        fmt.setBackground(color); sel.format = fmt
        self.viewer.setExtraSelections([sel])
        QTimer.singleShot(1500, lambda: self.viewer.setExtraSelections([]))

    # ── 코멘트 ──────────────────────────────────────────────────
    def _populate_comments(self, comments: list) -> None:
        self.comment_list.clear()
        for c in comments:
            author = (c.get("author_email") or "").split("@")[0] or "?"
            time_str = (c.get("created_at") or "")[:16].replace("T", " ")
            text = f"[{author} · {time_str}]\n{c.get('comment_text', '')}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, c)
            self.comment_list.addItem(item)
        self.comment_list.scrollToBottom()
        self._comment_count_pill.setText(str(len(comments)))

    def _add_comment(self) -> None:
        text = self.comment_input.text().strip()
        if not text or not self._current_manual:
            return
        author = get_current_user_email() or "unknown"
        data = {
            "manual_id": self._current_manual["id"],
            "author_email": author,
            "comment_text": text,
        }
        self.comment_input.clear()
        self._run_worker("add_comment", data=data)

    def _show_comment_menu(self, pos) -> None:
        item = self.comment_list.itemAt(pos)
        if not item:
            return
        c_data = item.data(Qt.UserRole)
        em = (get_current_user_email() or "").lower()
        if (c_data.get("author_email") or "").lower() != em and not _is_admin():
            return
        menu = QMenu(self)
        del_action = menu.addAction(tr("削除"))
        action = menu.exec(QCursor.pos())
        if action == del_action:
            self._run_worker("delete_comment", comment_id=c_data["id"])


__all__ = [
    "ManualWidget",
    "ManualCard",
    "ImageEditDialog",
    "ImagePreviewDialog",
    "CategoryManagerDialog",
]
