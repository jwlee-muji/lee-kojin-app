"""ダッシュボード — Phase 5.15 통합 (16 cards + layout editor v2).

Phase 5.15 v2 변경사항 (안정성 + UX):
    - 카드/오버레이 영구 보존 (installEventFilter 1회만, incremental 재배치)
    - 드래그 드롭 이동 (편집 모드 시 카드 헤더 드래그 → 다른 카드와 swap / 빈 셀 이동)
    - 테두리 클릭+드래그 리사이즈 (우/하/우하단 edge cursor + 픽셀 단위 드래그 → col span snap)
    - 스켈레톤 로딩 (펄싱 placeholder, 데이터 도착 시 자동 hide)
    - 반응형 wrap (< 900 px → compact 2-col stack, >= 900 px → 사용자 cfg)
    - "全て更新" 버튼 — 활성 카드만 refresh

레이아웃 (12-column grid):
    Row 0  KPI         : PowerReserve / JepxSpot / Imbalance / JKM         (3col x 4)
    Row 1  運営         : Weather (3) / HJKS (4) / Calendar (5)
    Row 2  소통         : Gmail / Notice / Memo / AI                       (3col x 4)
    Row 3  AI ブリーフィング                                                (full 12)
    Row 4  시스템       : Manual / LogViewer / BugReport (admin only)      (4col x 3)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from PySide6.QtCore import (
    QByteArray, QEvent, QMimeData, QObject, QPoint, QPropertyAnimation,
    QThread, QTimer, Qt, Signal,
)
from PySide6.QtGui import QColor, QCursor, QDrag, QPainter
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMenu,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from app.core.events import bus
from app.core.i18n import tr
from app.ui.common import BaseWidget
from app.ui.components import LeeButton, LeePill

# ── 카드 import (Phase 5.1~5.14 결과물) ───────────────────────────────────
from app.widgets.dashboard_service import DashboardDataService
from app.widgets.power_reserve import PowerReserveCard
from app.widgets.jepx_spot import JepxSpotCard
from app.widgets.imbalance import ImbalanceCard
from app.widgets.jkm import JkmCard
from app.widgets.weather import WeatherCard
from app.widgets.hjks import HjksCard
from app.widgets.text_memo import MemoCard, _load_memos
from app.widgets.notification import NotificationCard, list_notifications
from app.widgets.briefing import BriefCard, latest_briefing
from app.widgets.ai_chat import (
    AiChatCard, latest_user_message, latest_assistant_after,
)
from app.widgets.gmail import GmailCard
from app.widgets.google_calendar import CalendarCard
from app.widgets.manual import ManualCard
from app.widgets.log_viewer import LogViewerCard
from app.widgets.bug_report import BugReportCard

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 토큰 + 메타
# ──────────────────────────────────────────────────────────────────────
_TOTAL_COLS         = 9             # 9 column 그리드
_RESPONSIVE_BP_PX   = 900           # 이 값 미만 → compact 2col stack
_EDGE_THICKNESS_PX  = 10            # 테두리 드래그 감지 두께
_GRIP_SIZE_PX       = 18            # 우하단 명시적 resize grip 크기
_MIN_COL_SPAN       = 1             # 카드 최소 가로 col span (1/9)
_MIN_ROW_SPAN       = 1             # 카드 최소 세로 row span
_GRID_GAP_PX        = 14            # cell 간 간격
_DRAG_THRESHOLD_PX  = 8             # 드래그 시작 임계
_DRAG_MIME          = "application/x-lee-dashcard"

# 기본 레이아웃 — 9 column 그리드, 정사각형 cell
# Row 합계는 9 col 정확히 채움 (겹침 0)
_DEFAULT_LAYOUT: list[dict] = [
    # Row 0 — KPI 4 카드 (각 2~3 col, h=2 로 정사각 ~ 가로형)
    {"key": "power",    "row": 0, "col": 0, "w": 2, "h": 2, "visible": True},
    {"key": "spot",     "row": 0, "col": 2, "w": 2, "h": 2, "visible": True},
    {"key": "imb",      "row": 0, "col": 4, "w": 2, "h": 2, "visible": True},
    {"key": "jkm",      "row": 0, "col": 6, "w": 3, "h": 2, "visible": True},
    # Row 2 — 운영
    {"key": "weather",  "row": 2, "col": 0, "w": 2, "h": 2, "visible": True},
    {"key": "hjks",     "row": 2, "col": 2, "w": 3, "h": 2, "visible": True},
    {"key": "calendar", "row": 2, "col": 5, "w": 4, "h": 2, "visible": True},
    # Row 4 — 소통
    {"key": "gmail",    "row": 4, "col": 0, "w": 2, "h": 2, "visible": True},
    {"key": "notice",   "row": 4, "col": 2, "w": 2, "h": 2, "visible": True},
    {"key": "memo",     "row": 4, "col": 4, "w": 3, "h": 2, "visible": True},
    {"key": "ai_chat",  "row": 4, "col": 7, "w": 2, "h": 2, "visible": True},
    # Row 6 — AI 브리핑 (full width, height 2)
    {"key": "briefing", "row": 6, "col": 0, "w": 9, "h": 2, "visible": True},
    # Row 8 — 시스템 / 관리
    {"key": "manual",   "row": 8, "col": 0, "w": 3, "h": 2, "visible": True},
    {"key": "log",      "row": 8, "col": 3, "w": 3, "h": 2, "visible": True},
    {"key": "bug",      "row": 8, "col": 6, "w": 3, "h": 2, "visible": True},
]

# 카드 메타: key → (display_name_jp, page_idx, admin_only)
_CARD_META: dict[str, tuple[str, int, bool]] = {
    "power":    ("電力予備率",         2,  False),
    "spot":     ("JEPX スポット",      1,  False),
    "imb":      ("インバランス",       3,  False),
    "jkm":      ("JKM LNG",            4,  False),
    "weather":  ("全国天気",           5,  False),
    "hjks":     ("発電稼働状況",       6,  False),
    "calendar": ("カレンダー",         7,  False),
    "gmail":    ("Gmail",              8,  False),
    "notice":   ("通知センター",       9,  False),
    "memo":     ("テキストメモ",      10,  False),
    "ai_chat":  ("AI チャット",       11,  False),
    "briefing": ("AI ブリーフィング", 12,  False),
    "manual":   ("マニュアル",        13,  False),
    "log":      ("システムログ",      14,  False),
    "bug":      ("バグ報告 / 申請",   15,  True),
}


def _is_admin() -> bool:
    try:
        from app.api.google.auth import get_current_user_email
        from app.core.config import ADMIN_EMAIL
        return (get_current_user_email() or "").lower() == ADMIN_EMAIL.lower()
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────
# Skeleton — 디자인 시스템 컴포넌트 사용 (Phase 6)
# ──────────────────────────────────────────────────────────────────────
from app.ui.components.skeleton import LeeSkeleton as _SkeletonOverlay   # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# CardOverlay — 편집 모드 시 카드 위 컨트롤 + 드래그 핸들
# ──────────────────────────────────────────────────────────────────────
class _CardOverlay(QFrame):
    """편집 모드 시 카드 위에 떠 있는 컨트롤 + 가시성 강조 페인트.

    - 카드 전체 dashed border (편집 영역 명시)
    - 우상단: ✕ 숨김 버튼
    - 우하단: 항상 표시되는 resize grip (대각 줄무늬, 클릭 가능)
    - 마우스 hover edge 시 그 가장자리 두께 highlight
    """
    hide_requested = Signal(str)

    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self._key = key
        self._hovered_edge: Optional[str] = None
        self.setObjectName("dashCardOverlay")
        # 마우스 이벤트는 통과 (resize grip 영역만 자체 처리)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._build_ui()
        self._apply_qss()
        self.setVisible(False)

    def set_hovered_edge(self, edge: Optional[str]) -> None:
        if edge != self._hovered_edge:
            self._hovered_edge = edge
            self.update()

    def _build_ui(self) -> None:
        # ✕ 버튼은 별도 child — 마우스 이벤트 받아야 함
        self._btn_close = QPushButton("✕", self)
        self._btn_close.setObjectName("dashOverBtn")
        self._btn_close.setProperty("danger", "true")
        self._btn_close.setFixedSize(26, 26)
        self._btn_close.setToolTip(tr("非表示"))
        self._btn_close.setCursor(Qt.PointingHandCursor)
        self._btn_close.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._btn_close.clicked.connect(lambda: self.hide_requested.emit(self._key))

        # 드래그 힌트 (좌상단)
        self._hint_lbl = QLabel("⋮⋮  " + tr("ドラッグ移動"), self)
        self._hint_lbl.setObjectName("dashOverHint")
        self._hint_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # 위치 갱신
        self._btn_close.move(self.width() - 26 - 8, 8)
        self._hint_lbl.adjustSize()
        self._hint_lbl.move(8, 8)

    def paintEvent(self, e):
        super().paintEvent(e)
        from PySide6.QtGui import QPen as _QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # ── 1) 우하단 resize grip (편집 모드 시 항상 표시) ──
        gp = QColor("#FF7A45"); gp.setAlpha(230)
        p.setPen(Qt.NoPen); p.setBrush(gp)
        p.drawRoundedRect(w - _GRIP_SIZE_PX - 4, h - _GRIP_SIZE_PX - 4,
                          _GRIP_SIZE_PX, _GRIP_SIZE_PX, 4, 4)
        p.setPen(_QPen(QColor("white"), 1.5))
        gx = w - _GRIP_SIZE_PX - 4
        gy = h - _GRIP_SIZE_PX - 4
        for i in range(3):
            off = 4 + i * 5
            p.drawLine(gx + _GRIP_SIZE_PX - off, gy + _GRIP_SIZE_PX - 2,
                       gx + _GRIP_SIZE_PX - 2, gy + _GRIP_SIZE_PX - off)

        # ── 2) 가장자리 highlight (hover 시만) ──
        edge = self._hovered_edge
        if edge:
            accent = QColor("#FF7A45"); accent.setAlpha(180)
            p.setPen(Qt.NoPen); p.setBrush(accent)
            T = _EDGE_THICKNESS_PX
            if "r" in edge:
                p.drawRect(w - T, 0, T, h)
            if "l" in edge:
                p.drawRect(0, 0, T, h)
            if "b" in edge:
                p.drawRect(0, h - T, w, T)
            if "t" in edge:
                p.drawRect(0, 0, w, T)
        p.end()

    def set_theme(self, is_dark: bool) -> None:
        self._apply_qss()

    def _apply_qss(self) -> None:
        from app.ui.theme import ThemeManager, TOKENS_DARK, TOKENS_LIGHT
        d = ThemeManager.instance().is_dark()
        t = TOKENS_DARK if d else TOKENS_LIGHT
        hint_bg = "rgba(11, 18, 32, 0.7)" if d else "rgba(255, 255, 255, 0.85)"
        self.setStyleSheet(f"""
            QFrame#dashCardOverlay {{
                background: transparent;
                border: 2px dashed rgba(255, 122, 69, 0.85);
                border-radius: 14px;
            }}
            QPushButton#dashOverBtn {{
                background: {t['bg_surface']}; color: {t['fg_primary']};
                border: 1px solid {t['border_strong']};
                border-radius: 6px;
                font-size: 12px; font-weight: 800;
            }}
            QPushButton#dashOverBtn[danger="true"]:hover {{
                background: {t['c_bad']}; color: white; border: 1px solid {t['c_bad']};
            }}
            QLabel#dashOverHint {{
                color: {t['accent']};
                background: {hint_bg};
                font-size: 10px; font-weight: 800;
                letter-spacing: 0.04em;
                padding: 3px 8px;
                border-radius: 8px;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# DropIndicator — drag-drop 시 ghost preview (카드 사이즈 영역 표시)
# ──────────────────────────────────────────────────────────────────────
class _DropIndicator(QFrame):
    """Drop preview — 위치 라벨 + 충돌 여부 색상 분기 (녹색 OK / 빨강 충돌)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dashDropInd")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._invalid = False
        self._info_lbl = QLabel(self)
        self._info_lbl.setObjectName("dashDropLbl")
        self._info_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._apply_qss()
        self.setVisible(False)

    def set_invalid(self, invalid: bool) -> None:
        if invalid != self._invalid:
            self._invalid = invalid
            self._apply_qss()

    def set_info(self, text: str) -> None:
        self._info_lbl.setText(text)
        self._info_lbl.adjustSize()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._info_lbl.adjustSize()
        # 라벨을 좌상단에 8px 마진
        self._info_lbl.move(8, 8)

    def _apply_qss(self) -> None:
        if self._invalid:
            bg = "rgba(255, 69, 58, 0.18)"
            bd = "#FF453A"
            tag_bg = "#FF453A"
        else:
            bg = "rgba(255, 122, 69, 0.18)"
            bd = "#FF7A45"
            tag_bg = "#FF7A45"
        self.setStyleSheet(f"""
            QFrame#dashDropInd {{
                background: {bg};
                border: 2px dashed {bd};
                border-radius: 14px;
            }}
            QLabel#dashDropLbl {{
                color: white;
                background: {tag_bg};
                font-size: 11px; font-weight: 800;
                padding: 4px 10px;
                border-radius: 6px;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# CardEdgeFilter — 카드 가장자리 hover/drag 처리 (편집 모드 시만)
# ──────────────────────────────────────────────────────────────────────
class _CardInteractionFilter(QObject):
    """편집 모드 시 카드의 마우스 이벤트를 가로채:
        - 가장자리 hover → cursor 변경 (Size{Hor,Ver,FDiag}Cursor)
        - 가장자리 클릭+드래그 → resize 시작 (픽셀 → col/row span)
        - 드래그 핸들 (상단 36px) 클릭+이동 → drag start (QDrag)
        - 그 외 영역 클릭 → 클릭 통과 (카드 자체 처리)
    """

    def __init__(self, dashboard: "DashboardWidget", key: str, card: QWidget):
        super().__init__(card)
        self._dash = dashboard
        self._key  = key
        self._card = card
        # 상태
        self._press_pos: Optional[QPoint] = None     # 카드 로컬 좌표
        self._press_global: Optional[QPoint] = None
        self._resize_edge: Optional[str] = None
        self._drag_armed = False
        self._cell_size: tuple[float, float] = (0.0, 0.0)   # (col_w, row_h) px

    # ── public ────────────────────────────────────────────────
    def reset(self) -> None:
        self._press_pos = None
        self._press_global = None
        self._resize_edge = None
        self._drag_armed = False
        self._card.unsetCursor()

    # ── eventFilter ──────────────────────────────────────────
    def eventFilter(self, obj, event):
        if obj is not self._card:
            return False
        edit_mode = self._dash._edit_mode

        et = event.type()
        # 편집 모드 외에는 cursor 정리만
        if not edit_mode:
            if et == QEvent.Type.Leave:
                self._card.unsetCursor()
            return False

        if et == QEvent.Type.MouseMove:
            return self._on_move(event)
        if et == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
            return self._on_press(event)
        if et == QEvent.Type.MouseButtonRelease and event.button() == Qt.LeftButton:
            return self._on_release(event)
        # 편집 모드 중 더블클릭도 consume — 카드 더블클릭 핸들러 차단
        if et == QEvent.Type.MouseButtonDblClick:
            return True
        if et == QEvent.Type.Leave:
            if self._resize_edge is None and not self._drag_armed:
                self._card.unsetCursor()
        return False

    # ── helpers ───────────────────────────────────────────────
    def _detect_edge(self, pos: QPoint) -> Optional[str]:
        w, h = self._card.width(), self._card.height()
        EDGE = _EDGE_THICKNESS_PX
        on_right  = pos.x() >= w - EDGE
        on_bottom = pos.y() >= h - EDGE
        on_left   = pos.x() <= EDGE
        on_top    = pos.y() <= EDGE
        if on_right and on_bottom: return "br"
        if on_right and on_top:    return "tr"
        if on_left  and on_bottom: return "bl"
        if on_right: return "r"
        if on_bottom: return "b"
        return None

    def _set_cursor_for_edge(self, edge: Optional[str]) -> None:
        if edge in ("r",):
            self._card.setCursor(Qt.SizeHorCursor)
        elif edge in ("b",):
            self._card.setCursor(Qt.SizeVerCursor)
        elif edge in ("br", "tl"):
            self._card.setCursor(Qt.SizeFDiagCursor)
        elif edge in ("tr", "bl"):
            self._card.setCursor(Qt.SizeBDiagCursor)
        else:
            self._card.unsetCursor()

    def _on_move(self, event) -> bool:
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        # 드래그 중인 경우
        if self._press_pos is not None and (event.buttons() & Qt.LeftButton):
            # 1) 리사이즈 진행 중
            if self._resize_edge is not None and self._press_global is not None:
                cur_global = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
                delta = cur_global - self._press_global
                self._dash._on_card_resize_drag(self._key, self._resize_edge, delta.x(), delta.y())
                return True
            # 2) 드래그 시작 임계 도달 시 QDrag 시작
            if self._drag_armed:
                if (pos - self._press_pos).manhattanLength() >= _DRAG_THRESHOLD_PX:
                    self._drag_armed = False
                    self._dash._start_card_drag(self._key)
                    self.reset()
                    return True
            return False
        # 호버 — 가장자리 검출
        edge = self._detect_edge(pos)
        self._set_cursor_for_edge(edge)
        return False

    def _on_press(self, event) -> bool:
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        edge = self._detect_edge(pos)
        self._press_pos = pos
        self._press_global = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
        if edge is not None:
            self._resize_edge = edge
            self._dash._on_card_resize_start(self._key)
            return True
        # 가장자리 외 — 어디든 drag 가능 (영역 제한 없음)
        self._drag_armed = True
        self._card.setCursor(Qt.ClosedHandCursor)
        # drag 시작 시 grab offset (카드 내 좌표 비율) 저장
        cw = max(1, self._card.width())
        ch = max(1, self._card.height())
        self._dash._drag_grab_ratio = (pos.x() / cw, pos.y() / ch)
        return True

    def _on_release(self, _event) -> bool:
        # 편집 모드에서는 항상 consume — 카드 자체 mouseReleaseEvent (clicked emit) 차단
        if self._resize_edge is not None:
            self._dash._on_card_resize_end(self._key)
        self.reset()
        return True


# ──────────────────────────────────────────────────────────────────────
# DashboardWidget
# ──────────────────────────────────────────────────────────────────────
class DashboardWidget(BaseWidget):
    request_fetch = Signal(str)

    def __init__(self):
        super().__init__()
        self._weather_list: list = []
        self._is_admin = _is_admin()
        self._edit_mode = False
        self._compact = False
        self._cards: dict[str, QWidget] = {}
        self._overlays: dict[str, _CardOverlay] = {}
        self._skeletons: dict[str, _SkeletonOverlay] = {}
        self._filters: dict[str, _CardInteractionFilter] = {}
        self._cards_with_data: set[str] = set()        # 데이터 도착한 카드 — 스켈레톤 hide
        self._layout_cfg: list[dict] = self._load_layout()
        # 현재 진행 중 리사이즈 상태
        self._rz_key: Optional[str] = None
        self._rz_orig: Optional[dict] = None    # 원래 cfg 사본
        self._rz_orig_geom: Optional[tuple[int, int, int, int]] = None  # x, y, w, h px
        self._drag_grab_ratio: tuple[float, float] = (0.5, 0.2)   # 0..1 비율 (잡은 위치)
        self._drag_source_key: Optional[str] = None   # drag 진행 중인 카드 key

        # ── 백그라운드 데이터 서비스 ─────────────────────────────────
        self._service_thread = QThread()
        self._service = DashboardDataService()
        self._service.moveToThread(self._service_thread)
        self.request_fetch.connect(self._service.fetch_data)
        self._service_thread.finished.connect(self._service.deleteLater)
        self.track_worker(self._service_thread)

        self._service.imb_card_result.connect(self._on_imb_card_result)
        self._service.imb_empty.connect(self._on_imb_empty)
        self._service.jkm_card_result.connect(self._on_jkm_card_result)
        self._service.jkm_empty.connect(self._on_jkm_empty)
        self._service.hjks_card_result.connect(self._on_hjks_card_result)
        self._service.hjks_empty.connect(self._on_hjks_empty)
        self._service.spot_today_result.connect(self._on_spot_today_result)
        self._service.spot_tomorrow_result.connect(self._on_spot_tomorrow_result)
        self._service.spot_yesterday_result.connect(self._on_spot_yesterday_result)
        self._service.spot_today_slots_result.connect(self._on_spot_today_slots_result)
        self._service.spot_tomorrow_slots_result.connect(self._on_spot_tomorrow_slots_result)

        self._service_thread.start()

        self._build_ui()

        # Event Bus 구독
        bus.occto_updated.connect(self.update_occto)
        bus.occto_areas.connect(self.update_occto_areas)
        bus.imbalance_updated.connect(self.refresh_imbalance)
        bus.jkm_updated.connect(self.refresh_jkm)
        bus.jepx_spot_updated.connect(self.refresh_spot)
        bus.hjks_updated.connect(self.refresh_hjks)
        bus.weather_updated.connect(self.update_weather)
        bus.briefing_generated.connect(lambda *_: self._refresh_brief_card())

        self._notice_refresh_timer = QTimer(self)
        self._notice_refresh_timer.setSingleShot(True)
        self._notice_refresh_timer.setInterval(180)
        self._notice_refresh_timer.timeout.connect(self._refresh_notice_card)
        bus.notifications_changed.connect(self._notice_refresh_timer.start)

        self._ai_refresh_timer = QTimer(self)
        self._ai_refresh_timer.setSingleShot(True)
        self._ai_refresh_timer.setInterval(180)
        self._ai_refresh_timer.timeout.connect(self._refresh_ai_card)
        bus.ai_chat_changed.connect(self._ai_refresh_timer.start)

        # 드래그 드롭 (대시보드 본체)
        self.setAcceptDrops(True)

        QTimer.singleShot(2250, self.refresh_data)

    # ── 레이아웃 영속화 ───────────────────────────────────────
    # v2 = 9-col absolute grid (Phase 5.15 v2)
    _LAYOUT_VERSION = 2

    def _load_layout(self) -> list[dict]:
        try:
            saved_v = self.settings.get("dashboard_layout_version", 0)
            saved = self.settings.get("dashboard_layout") or []
            if (not isinstance(saved, list) or not saved
                    or saved_v != self._LAYOUT_VERSION):
                # 버전 불일치 → 기본 레이아웃 으로 reset
                return [dict(c) for c in _DEFAULT_LAYOUT]
            # 9 col 범위 강제 보정
            valid = []
            for c in saved:
                if not isinstance(c, dict): continue
                w = max(_MIN_COL_SPAN, min(_TOTAL_COLS, int(c.get("w", 3))))
                col = max(0, min(_TOTAL_COLS - w, int(c.get("col", 0))))
                valid.append({**c, "w": w, "col": col})
            saved_keys = {c.get("key") for c in valid}
            next_row = max((c.get("row", 0) + c.get("h", 1) for c in valid),
                           default=0)
            for default in _DEFAULT_LAYOUT:
                if default["key"] not in saved_keys:
                    new = dict(default); new["row"] = next_row
                    valid.append(new); next_row += new.get("h", 1)
            return valid
        except Exception:
            return [dict(c) for c in _DEFAULT_LAYOUT]

    def _save_layout(self) -> None:
        try:
            from app.core.config import load_settings, save_settings
            s = load_settings()
            s["dashboard_layout"] = self._layout_cfg
            s["dashboard_layout_version"] = self._LAYOUT_VERSION
            save_settings(s)
        except Exception as e:
            logger.warning(f"dashboard layout 저장 실패: {e}")

    # ── 카드 1회 생성 ──────────────────────────────────────────
    def _create_card_widget(self, key: str) -> Optional[QWidget]:
        meta = _CARD_META.get(key)
        if not meta:
            return None
        page_idx = meta[1]

        ctor = {
            "power": PowerReserveCard, "spot": JepxSpotCard, "imb": ImbalanceCard,
            "jkm": JkmCard, "weather": WeatherCard, "hjks": HjksCard,
            "calendar": CalendarCard, "gmail": GmailCard, "notice": NotificationCard,
            "memo": MemoCard, "ai_chat": AiChatCard, "briefing": BriefCard,
            "manual": ManualCard, "log": LogViewerCard, "bug": BugReportCard,
        }.get(key)
        if ctor is None:
            return None
        try:
            c = ctor()
        except Exception as e:
            logger.error(f"카드 {key} 생성 실패: {e}", exc_info=True)
            return None

        # 클릭 → 라우팅
        for sig_name in ("clicked", "open_requested"):
            sig = getattr(c, sig_name, None)
            if sig is not None:
                sig.connect(lambda _=None, idx=page_idx: bus.page_requested.emit(idx))
                break
        if key == "memo" and hasattr(c, "new_clicked"):
            c.new_clicked.connect(self._open_memo_new)
        if key == "ai_chat" and hasattr(c, "new_clicked"):
            c.new_clicked.connect(self._open_ai_new)

        c.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        c.setMouseTracking(True)
        return c

    def _ensure_all_cards(self) -> None:
        """모든 카드 + 오버레이 + 스켈레톤 + 인터랙션 필터를 1회만 생성.

        Absolute positioning grid: 각 카드를 grid_wrap 의 child 로 만들고
        setGeometry 로 직접 위치 지정.
        """
        from PySide6.QtCore import QEasingCurve as _EC
        appear_idx = 0
        for cfg in self._layout_cfg:
            key = cfg.get("key")
            meta = _CARD_META.get(key)
            if not meta:
                continue
            if key in self._cards:
                continue
            card = self._create_card_widget(key)
            if card is None:
                continue
            # grid_wrap 의 child 로 reparent
            card.setParent(self._grid_wrap)
            # min size 풀어서 1×1 cell 까지 작아질 수 있게
            card.setMinimumSize(1, 1)
            self._cards[key] = card

            # 스켈레톤 (카드의 child)
            sk = _SkeletonOverlay(parent=card)
            sk.setGeometry(0, 0, max(1, card.width()), max(1, card.height()))
            sk.start()
            self._skeletons[key] = sk

            # 오버레이 (편집 모드 시)
            ov = _CardOverlay(key, parent=card)
            ov.hide_requested.connect(self._on_hide_card)
            ov.setGeometry(0, 0, max(1, card.width()), max(1, card.height()))
            self._overlays[key] = ov

            # 인터랙션 필터 — 1회만 install
            f = _CardInteractionFilter(self, key, card)
            self._filters[key] = f
            card.installEventFilter(f)
            card.installEventFilter(self)   # resize 추적

            # 등장 애니메이션 — opacity 0→1, 240ms OutBack, stagger 30ms
            self._animate_card_appear(card, delay_ms=appear_idx * 30)
            appear_idx += 1

    def _animate_card_appear(self, card: QWidget, delay_ms: int = 0) -> None:
        """카드 등장 — opacity 0 → 1 페이드 (240ms OutBack)."""
        from PySide6.QtCore import QEasingCurve as _EC
        eff = QGraphicsOpacityEffect(card)
        eff.setOpacity(0.0)
        card.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", card)
        anim.setDuration(240)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(_EC.OutBack)

        def _cleanup():
            try: card.setGraphicsEffect(None)
            except Exception: pass
        anim.finished.connect(_cleanup)
        # delay
        if delay_ms > 0:
            QTimer.singleShot(delay_ms, anim.start)
        else:
            anim.start()
        # GC 방지
        card._appear_anim = anim

    # ── absolute positioning grid ────────────────────────────
    def _cell_size_px(self) -> tuple[float, float]:
        """현재 inner width 기준 (cell_w, cell_h) — 정사각형."""
        wrap_w = max(1, self._grid_wrap.width())
        # cell_w = (inner_w - gap*(cols+1)) / cols
        cell = (wrap_w - _GRID_GAP_PX * (_TOTAL_COLS + 1)) / _TOTAL_COLS
        cell = max(20.0, cell)   # 최소 20px (극단적으로 좁아도)
        return (cell, cell)      # 정사각형

    def _cell_to_geom(self, row: int, col: int, w: int, h: int) -> tuple[int, int, int, int]:
        """row/col/w/h → 픽셀 (x, y, width, height)."""
        cw, ch = self._cell_size_px()
        x = _GRID_GAP_PX + col * (cw + _GRID_GAP_PX)
        y = _GRID_GAP_PX + row * (ch + _GRID_GAP_PX)
        pw = w * cw + (w - 1) * _GRID_GAP_PX
        ph = h * ch + (h - 1) * _GRID_GAP_PX
        return (int(x), int(y), int(max(20, pw)), int(max(20, ph)))

    def _apply_grid_positions(self) -> None:
        """현재 layout_cfg 에 따라 모든 카드 setGeometry."""
        if self._compact:
            self._apply_compact_grid()
            return

        max_row_end = 0
        for cfg in self._layout_cfg:
            key = cfg.get("key")
            meta = _CARD_META.get(key)
            if not meta:
                continue
            if meta[2] and not self._is_admin:
                cfg["visible"] = False
            visible = bool(cfg.get("visible", True))
            card = self._cards.get(key)
            if card is None:
                continue
            if not visible:
                card.hide(); continue

            row = max(0, int(cfg.get("row", 0)))
            col = max(0, min(_TOTAL_COLS - 1, int(cfg.get("col", 0))))
            w = max(_MIN_COL_SPAN, min(_TOTAL_COLS - col, int(cfg.get("w", 3))))
            h = max(_MIN_ROW_SPAN, int(cfg.get("h", 1)))
            x, y, pw, ph = self._cell_to_geom(row, col, w, h)
            card.setGeometry(x, y, pw, ph)
            card.show()
            card.raise_()
            # 카드 사이즈에 따라 적응 — 카드가 set_compact_level 가지고 있으면 호출
            self._adapt_card_to_size(card, w, h)
            max_row_end = max(max_row_end, row + h)

        # inner widget 의 minimum height 갱신 → scroll bar 자동 노출
        cw, _ = self._cell_size_px()
        inner_h = int(_GRID_GAP_PX + max_row_end * (cw + _GRID_GAP_PX))
        self._grid_wrap.setMinimumHeight(inner_h)

        self._sync_overlay_geom()

    def _adapt_card_to_size(self, card, w_cells: int, h_cells: int) -> None:
        """카드가 자체 sizing 메서드 가지고 있으면 사이즈 정보 전달."""
        # set_compact_level(level) — 0(매우 작음)~3(큰)
        area = w_cells * h_cells
        if area <= 1:
            level = 0
        elif area <= 4:
            level = 1
        elif area <= 9:
            level = 2
        else:
            level = 3
        for fn_name in ("set_compact_level", "set_compact"):
            fn = getattr(card, fn_name, None)
            if callable(fn):
                try: fn(level)
                except Exception: pass
                break

    def _apply_compact_grid(self) -> None:
        """좁은 화면 — 모든 visible 카드를 폭 9 col / row 2 (정사각) stack."""
        visible_cfgs = []
        for cfg in self._layout_cfg:
            key = cfg.get("key")
            meta = _CARD_META.get(key)
            if not meta: continue
            if meta[2] and not self._is_admin:
                continue
            if cfg.get("visible", True) and key in self._cards:
                visible_cfgs.append(cfg)
        visible_cfgs.sort(key=lambda c: (c.get("row", 0), c.get("col", 0)))
        # 모든 카드 hide
        for cfg in self._layout_cfg:
            card = self._cards.get(cfg.get("key"))
            if card: card.hide()
        # 1col stack — 전체 폭, 높이 = 2 row
        for i, cfg in enumerate(visible_cfgs):
            card = self._cards[cfg.get("key")]
            x, y, pw, ph = self._cell_to_geom(i * 2, 0, _TOTAL_COLS, 2)
            card.setGeometry(x, y, pw, ph)
            card.show(); card.raise_()
            self._adapt_card_to_size(card, _TOTAL_COLS, 2)
        cw, _ = self._cell_size_px()
        inner_h = int(_GRID_GAP_PX + len(visible_cfgs) * 2 * (cw + _GRID_GAP_PX))
        self._grid_wrap.setMinimumHeight(inner_h)
        self._sync_overlay_geom()

    def _sync_overlay_geom(self) -> None:
        """오버레이 + 스켈레톤이 카드 사이즈 따라가도록."""
        for key, card in self._cards.items():
            ov = self._overlays.get(key)
            if ov is not None:
                ov.setGeometry(0, 0, card.width(), card.height())
                ov.setVisible(self._edit_mode and card.isVisible())
                ov.raise_()
            sk = self._skeletons.get(key)
            if sk is not None:
                sk.setGeometry(0, 0, card.width(), card.height())
                if key in self._cards_with_data:
                    sk.stop()
                else:
                    sk.start()
                # skeleton 은 overlay 아래로
                sk.lower()

    # ── eventFilter (카드 resize 추적) ────────────────────────
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Resize:
            # grid_wrap 자체 resize → 모든 카드 재배치
            if obj is self._grid_wrap:
                # debounce 로 cascading 방지
                if not hasattr(self, "_wrap_resize_timer"):
                    self._wrap_resize_timer = QTimer(self)
                    self._wrap_resize_timer.setSingleShot(True)
                    self._wrap_resize_timer.setInterval(20)
                    self._wrap_resize_timer.timeout.connect(self._apply_grid_positions)
                self._wrap_resize_timer.start()
                return False
            # 카드 resize → overlay/skeleton 위치 갱신
            for key, card in self._cards.items():
                if obj is card:
                    ov = self._overlays.get(key)
                    if ov is not None:
                        ov.setGeometry(0, 0, card.width(), card.height())
                    sk = self._skeletons.get(key)
                    if sk is not None:
                        sk.setGeometry(0, 0, card.width(), card.height())
                    break
        return super().eventFilter(obj, event)

    # ── 빌드 ─────────────────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 16); outer.setSpacing(14)

        outer.addWidget(self._build_greeting_header())

        # ── 9 col 그리드 + 세로 스크롤 + 정사각형 cell ────────────────
        from PySide6.QtWidgets import QScrollArea
        self._scroll = QScrollArea()
        self._scroll.setObjectName("dashScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)

        # inner — absolute positioning grid (no layout)
        self._grid_wrap = QFrame()
        self._grid_wrap.setObjectName("dashGridWrap")
        # accept drop on inner widget
        self._grid_wrap.setAcceptDrops(True)
        self._grid_wrap.installEventFilter(self)   # resize 추적
        self._scroll.setWidget(self._grid_wrap)
        outer.addWidget(self._scroll, 1)

        # drop indicator (inner widget child)
        self._drop_ind = _DropIndicator(parent=self._grid_wrap)
        self._drop_ind.hide()

        # 리사이즈 사이즈 라벨 (e.g., "3×2 → 4×2")
        self._size_label = QLabel("", parent=self._grid_wrap)
        self._size_label.setObjectName("dashSizeLbl")
        self._size_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._size_label.hide()

        outer.addWidget(self._build_status_bar())

        # 카드 1회 생성 + 첫 배치
        self._ensure_all_cards()
        self._apply_grid_positions()

    # ── 인사말 헤더 ──────────────────────────────────────────
    def _build_greeting_header(self) -> QWidget:
        wrap = QWidget(); wrap.setObjectName("dashGreetingWrap")
        h = QHBoxLayout(wrap); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(12)
        h.setAlignment(Qt.AlignBottom)

        text_box = QVBoxLayout(); text_box.setContentsMargins(0, 0, 0, 0); text_box.setSpacing(4)
        now = datetime.now()
        weekday_jp = "月火水木金土日"[now.weekday()]
        date_str = (f"{now.year}年 {now.month}月 {now.day}日 "
                    f"({weekday_jp})  ·  {now.strftime('%H:%M')}")
        self._date_caption = QLabel(date_str)
        self._date_caption.setObjectName("dashDateCaption")
        text_box.addWidget(self._date_caption)
        try:
            from app.api.google.auth import get_current_user_email
            email = get_current_user_email() or ""
        except Exception:
            email = ""
        name = email.split("@", 1)[0] if "@" in email else (email or tr("ゲスト"))
        greeting = self._greeting_for_hour(now.hour)
        self._greeting_lbl = QLabel(f"{greeting}、{name}さん")
        self._greeting_lbl.setObjectName("dashGreeting")
        text_box.addWidget(self._greeting_lbl)
        self._summary_lbl = QLabel(tr("本日の電力市場のサマリーをここに表示します。"))
        self._summary_lbl.setObjectName("dashSummary"); self._summary_lbl.setWordWrap(True)
        text_box.addWidget(self._summary_lbl)
        h.addLayout(text_box, 1)

        self._btn_refresh_all = LeeButton("↻  " + tr("全て更新"), variant="secondary", size="md")
        self._btn_refresh_all.clicked.connect(self._refresh_all_visible)
        h.addWidget(self._btn_refresh_all, 0, Qt.AlignBottom)

        self._btn_add_widget = LeeButton("＋  " + tr("ウィジェット追加"),
                                          variant="secondary", size="md")
        self._btn_add_widget.clicked.connect(self._show_add_widget_menu)
        h.addWidget(self._btn_add_widget, 0, Qt.AlignBottom)

        self._btn_edit = LeeButton(tr("レイアウト編集"), variant="primary", size="md")
        self._btn_edit.clicked.connect(self._toggle_edit_mode)
        h.addWidget(self._btn_edit, 0, Qt.AlignBottom)

        self._edit_pill = LeePill(tr("編集中"), variant="warning")
        self._edit_pill.setVisible(False)
        h.addWidget(self._edit_pill, 0, Qt.AlignBottom)
        return wrap

    @staticmethod
    def _greeting_for_hour(hour: int) -> str:
        if 5 <= hour < 11:  return tr("おはようございます")
        if 11 <= hour < 18: return tr("こんにちは")
        return tr("こんばんは")

    def _build_status_bar(self) -> QWidget:
        bar = QWidget(); bar.setObjectName("dashStatusBar")
        bar.setFixedHeight(32)
        h = QHBoxLayout(bar); h.setContentsMargins(14, 0, 14, 0); h.setSpacing(10)
        dot = QLabel("●"); dot.setObjectName("dashStatusDot"); h.addWidget(dot)
        from app.core.config import __version__
        now = datetime.now()
        self._status_lbl = QLabel(
            tr("全データ同期中  ·  最終更新 {0}").format(now.strftime("%H:%M:%S"))
        )
        self._status_lbl.setObjectName("dashStatusText")
        h.addWidget(self._status_lbl); h.addStretch()
        ver_lbl = QLabel(f"v{__version__}  ·  LEE 電力モニター")
        ver_lbl.setObjectName("dashStatusVersion")
        h.addWidget(ver_lbl)
        return bar

    # ── 편집 모드 ────────────────────────────────────────────
    def _toggle_edit_mode(self) -> None:
        self._edit_mode = not self._edit_mode
        self._edit_pill.setVisible(self._edit_mode)
        self._btn_edit.setText(tr("完了") if self._edit_mode else tr("レイアウト編集"))
        self._sync_overlay_geom()
        if not self._edit_mode:
            self._save_layout()
            try:
                bus.toast_requested.emit(tr("レイアウトを保存しました"), "success")
            except Exception: pass

    # ── 카드 hide/add ────────────────────────────────────────
    def _on_hide_card(self, key: str) -> None:
        cfg = self._cfg_of(key)
        if cfg is None: return
        cfg["visible"] = False
        self._apply_grid_positions()
        try: bus.toast_requested.emit(
            tr("「{0}」 を非表示にしました").format(_CARD_META[key][0]), "info")
        except Exception: pass

    def _show_add_widget_menu(self) -> None:
        menu = QMenu(self)
        any_hidden = False
        for cfg in self._layout_cfg:
            key = cfg.get("key")
            meta = _CARD_META.get(key)
            if not meta: continue
            if meta[2] and not self._is_admin: continue
            if cfg.get("visible", True): continue
            any_hidden = True
            label = meta[0]
            act = menu.addAction(f"+  {label}")
            act.triggered.connect(lambda _=False, k=key: self._on_add_card(k))
        if not any_hidden:
            act = menu.addAction(tr("(追加可能なウィジェットなし)"))
            act.setEnabled(False)
        menu.exec(QCursor.pos())

    def _on_add_card(self, key: str) -> None:
        cfg = self._cfg_of(key)
        if cfg is None: return
        cfg["visible"] = True
        # 사이즈 보존 (없으면 default 3×2)
        w = max(_MIN_COL_SPAN, min(_TOTAL_COLS, cfg.get("w", 3)))
        h = max(_MIN_ROW_SPAN, cfg.get("h", 2))
        cfg["w"] = w; cfg["h"] = h
        # 빈 공간 자동 탐색
        spot = self._find_empty_spot(w, h, exclude=key)
        cfg["row"], cfg["col"] = spot
        self._apply_grid_positions()
        try: bus.toast_requested.emit(
            tr("「{0}」 を追加しました").format(_CARD_META[key][0]), "success")
        except Exception: pass

    def _find_empty_spot(self, w: int, h: int, exclude: Optional[str] = None) -> tuple[int, int]:
        """w×h 크기의 빈 공간 (row, col) 을 위에서부터 탐색.

        없으면 마지막 row 다음 (col=0).
        """
        max_existing_row = max(
            (c.get("row", 0) + c.get("h", 1) for c in self._layout_cfg
             if c.get("visible") and c.get("key") != exclude),
            default=0,
        )
        # 0 row 부터 차근차근 — w 가 col 안 넘는 한
        for r in range(max_existing_row + 2):
            for c in range(_TOTAL_COLS - w + 1):
                cand = {"row": r, "col": c, "w": w, "h": h}
                if not self._has_collision_with(exclude or "__none__", cand):
                    return (r, c)
        return (max_existing_row, 0)

    # ── 드래그 드롭 이동 ─────────────────────────────────────
    def _start_card_drag(self, key: str) -> None:
        card = self._cards.get(key)
        if card is None or not card.isVisible():
            return
        self._drag_source_key = key
        # 원본 카드 opacity 낮춤 (드래그 중 시각 피드백)
        eff = QGraphicsOpacityEffect(card)
        eff.setOpacity(0.35)
        card.setGraphicsEffect(eff)

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(_DRAG_MIME, QByteArray(key.encode("utf-8")))
        drag.setMimeData(mime)
        # ghost preview — 카드 축소판 (50%)
        pix = card.grab()
        if pix.width() > 0 and pix.height() > 0:
            pix = pix.scaled(pix.width() // 2, pix.height() // 2,
                             Qt.KeepAspectRatio, Qt.SmoothTransformation)
            drag.setPixmap(pix)
            # hot spot — grab ratio 기반 (잡은 위치가 ghost 의 어디에 오도록)
            gx = int(pix.width() * self._drag_grab_ratio[0])
            gy = int(pix.height() * self._drag_grab_ratio[1])
            drag.setHotSpot(QPoint(gx, gy))
        drag.exec(Qt.MoveAction)
        # 드래그 종료 — opacity 복원 + indicator hide
        try:
            card.setGraphicsEffect(None)
        except Exception:
            pass
        self._drop_ind.hide()
        self._drag_source_key = None

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(_DRAG_MIME):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if not e.mimeData().hasFormat(_DRAG_MIME):
            e.ignore(); return
        key = bytes(e.mimeData().data(_DRAG_MIME)).decode()
        cfg = self._cfg_of(key)
        if cfg is None:
            self._drop_ind.hide(); e.acceptProposedAction(); return

        # 잡은 위치 비율을 빼서 카드의 새 좌상단 cell 계산
        wrap_pos = self._grid_wrap.mapFrom(self, e.position().toPoint())
        new_row, new_col = self._cell_for_drop(wrap_pos, cfg)
        if new_row is None:
            self._drop_ind.hide(); e.acceptProposedAction(); return

        w, h = cfg.get("w", 3), cfg.get("h", 1)
        # drop validity — swap 가능 (다른 카드 위) 또는 빈 영역만 OK, 부분 충돌 = invalid
        candidate = {"row": new_row, "col": new_col, "w": w, "h": h}
        target_key = self._exact_target_key(new_row, new_col, exclude=key)
        valid = (target_key is not None or
                 not self._has_collision_with(key, candidate))

        x, y, gw, gh = self._cells_to_pixels(new_row, new_col, w, h)
        self._drop_ind.setGeometry(x, y, gw, gh)
        if target_key is not None:
            t_meta = _CARD_META.get(target_key)
            t_name = t_meta[0] if t_meta else target_key
            self._drop_ind.set_info(tr("入替: {0}").format(t_name))
            self._drop_ind.set_invalid(False)
        elif valid:
            self._drop_ind.set_info(f"row {new_row + 1}, col {new_col + 1}  ·  {w}×{h}")
            self._drop_ind.set_invalid(False)
        else:
            self._drop_ind.set_info(tr("⚠ 衝突"))
            self._drop_ind.set_invalid(True)
        self._drop_ind.show()
        self._drop_ind.raise_()
        e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._drop_ind.hide()

    def dropEvent(self, e):
        self._drop_ind.hide()
        if not e.mimeData().hasFormat(_DRAG_MIME):
            e.ignore(); return
        key = bytes(e.mimeData().data(_DRAG_MIME)).decode()
        cfg = self._cfg_of(key)
        if cfg is None:
            e.ignore(); return

        wrap_pos = self._grid_wrap.mapFrom(self, e.position().toPoint())
        new_row, new_col = self._cell_for_drop(wrap_pos, cfg)
        if new_row is None:
            e.ignore(); return

        w, h = cfg.get("w", 3), cfg.get("h", 1)
        target_key = self._exact_target_key(new_row, new_col, exclude=key)
        if target_key is not None:
            # ── SWAP ── 두 카드 위치만 교환 (사이즈는 유지)
            t_cfg = self._cfg_of(target_key)
            if t_cfg is not None:
                old_row, old_col = cfg.get("row", 0), cfg.get("col", 0)
                t_cfg["row"], t_cfg["col"] = old_row, old_col
                cfg["row"], cfg["col"] = t_cfg.get("row"), t_cfg.get("col")
                # 다시 정정 — t_cfg 가 이미 변경된 상태이므로
                cfg["row"], cfg["col"] = old_row, old_col
                t_cfg["row"], t_cfg["col"] = old_row, old_col
                cfg["row"], cfg["col"] = new_row, new_col
        else:
            candidate = {"row": new_row, "col": new_col, "w": w, "h": h}
            if self._has_collision_with(key, candidate):
                # 충돌 → reject (사이즈 변경 절대 금지)
                try: bus.toast_requested.emit(
                    tr("⚠ 移動先に他のウィジェットがあります"), "warning")
                except Exception: pass
                e.ignore(); return
            cfg["row"], cfg["col"] = new_row, new_col
        # 사이즈 (w, h) 는 절대 변경하지 않음
        self._apply_grid_positions()
        self._save_layout()
        e.acceptProposedAction()

    def _cell_for_drop(self, wrap_pos: QPoint,
                       cfg: dict) -> tuple[Optional[int], Optional[int]]:
        """grab ratio 기준으로 카드의 새 좌상단 cell 계산 — 정사각 cell."""
        if self._grid_wrap.width() <= 0:
            return (None, None)
        cw, ch = self._cell_size_px()
        cell_pitch = cw + _GRID_GAP_PX
        w, h = cfg.get("w", 3), cfg.get("h", 1)
        gx, gy = self._drag_grab_ratio
        card_w_px = w * cw + (w - 1) * _GRID_GAP_PX
        card_h_px = h * ch + (h - 1) * _GRID_GAP_PX
        top_left_x = wrap_pos.x() - gx * card_w_px
        top_left_y = wrap_pos.y() - gy * card_h_px
        col = int(round((top_left_x - _GRID_GAP_PX) / cell_pitch))
        row = int(round((top_left_y - _GRID_GAP_PX) / cell_pitch))
        col = max(0, min(_TOTAL_COLS - w, col))
        row = max(0, row)   # 아래로는 무한
        return (row, col)

    def _cells_to_pixels(self, row: int, col: int, w: int, h: int) -> tuple[int, int, int, int]:
        return self._cell_to_geom(row, col, w, h)

    def _exact_target_key(self, row: int, col: int,
                          exclude: Optional[str] = None) -> Optional[str]:
        """좌상단이 정확히 (row, col) 인 카드 — swap 후보."""
        for cfg in self._layout_cfg:
            if cfg.get("key") == exclude: continue
            if not cfg.get("visible", True): continue
            if cfg.get("row", 0) == row and cfg.get("col", 0) == col:
                return cfg.get("key")
        return None

    @staticmethod
    def _cells_of(cfg: dict) -> set[tuple[int, int]]:
        r, c = cfg.get("row", 0), cfg.get("col", 0)
        w, h = cfg.get("w", 3), cfg.get("h", 1)
        return {(rr, cc) for rr in range(r, r + h) for cc in range(c, c + w)}

    def _cfg_of(self, key: str) -> Optional[dict]:
        for cfg in self._layout_cfg:
            if cfg.get("key") == key:
                return cfg
        return None

    # ── 픽셀 단위 리사이즈 (테두리 드래그) ────────────────────
    def _on_card_resize_start(self, key: str) -> None:
        cfg = self._cfg_of(key)
        if cfg is None: return
        self._rz_key = key
        self._rz_orig = dict(cfg)
        card = self._cards.get(key)
        if card is None: return
        self._rz_orig_geom = (card.x(), card.y(), card.width(), card.height())
        # 사이즈 라벨 표시 시작
        self._size_label.setText(f"{cfg.get('w', 3)}×{cfg.get('h', 1)}")
        self._size_label.adjustSize()
        self._size_label.show()
        self._size_label.raise_()
        self._update_size_label_pos(card)

    def _on_card_resize_drag(self, key: str, edge: str, dx: int, dy: int) -> None:
        if key != self._rz_key or self._rz_orig is None or self._rz_orig_geom is None:
            return
        # 정사각형 cell — col_w == row_h
        cw, ch = self._cell_size_px()
        col_w = cw + _GRID_GAP_PX     # cell + gap = pitch
        row_h = ch + _GRID_GAP_PX

        new_w = self._rz_orig.get("w", 3)
        new_h = self._rz_orig.get("h", 1)
        new_col = self._rz_orig.get("col", 0)
        new_row = self._rz_orig.get("row", 0)

        if "r" in edge:
            delta_cols = round(dx / col_w)
            new_w = max(_MIN_COL_SPAN,
                        min(_TOTAL_COLS - new_col, self._rz_orig.get("w", 3) + delta_cols))
        if "b" in edge:
            delta_rows = round(dy / row_h)
            new_h = max(_MIN_ROW_SPAN, self._rz_orig.get("h", 1) + delta_rows)
        if "l" in edge:
            delta_cols = round(dx / col_w)
            shrink = max(0, delta_cols)
            grow = max(0, -delta_cols)
            base_w = self._rz_orig.get("w", 3)
            base_col = self._rz_orig.get("col", 0)
            new_col = max(0, min(base_col + base_w - _MIN_COL_SPAN, base_col + shrink - grow))
            new_w = max(_MIN_COL_SPAN, base_w - (new_col - base_col))
        if "t" in edge:
            delta_rows = round(dy / row_h)
            shrink = max(0, delta_rows)
            grow = max(0, -delta_rows)
            base_h = self._rz_orig.get("h", 1)
            base_row = self._rz_orig.get("row", 0)
            new_row = max(0, min(base_row + base_h - _MIN_ROW_SPAN, base_row + shrink - grow))
            new_h = max(_MIN_ROW_SPAN, base_h - (new_row - base_row))

        cfg = self._cfg_of(key)
        if cfg is None: return
        # 충돌 검사
        candidate = dict(cfg)
        candidate.update(row=new_row, col=new_col, w=new_w, h=new_h)
        collision = self._has_collision_with(key, candidate)

        # 사이즈 라벨 갱신 (충돌이어도 표시)
        old_w, old_h = self._rz_orig.get("w", 3), self._rz_orig.get("h", 1)
        if (new_w, new_h) == (old_w, old_h):
            self._size_label.setText(f"{new_w}×{new_h}")
        else:
            self._size_label.setText(f"{old_w}×{old_h} → {new_w}×{new_h}")
        self._size_label.adjustSize()
        self._size_label.setProperty("invalid", "true" if collision else "false")
        self._size_label.style().unpolish(self._size_label)
        self._size_label.style().polish(self._size_label)
        card = self._cards.get(key)
        if card: self._update_size_label_pos(card)

        if collision:
            return
        if (cfg.get("row") == new_row and cfg.get("col") == new_col and
                cfg.get("w") == new_w and cfg.get("h") == new_h):
            return
        cfg.update(row=new_row, col=new_col, w=new_w, h=new_h)
        self._apply_grid_positions()
        # apply_grid_positions 후 카드 위치 갱신되었으므로 라벨도 다시
        if card: self._update_size_label_pos(card)

    def _on_card_resize_end(self, key: str) -> None:
        if self._rz_key == key:
            self._rz_key = None
            self._rz_orig = None
            self._rz_orig_geom = None
            self._size_label.hide()
            self._save_layout()

    def _update_size_label_pos(self, card: QWidget) -> None:
        """사이즈 라벨을 카드 우하단 모서리 옆에 배치 (grid_wrap 좌표)."""
        if not card.isVisible():
            return
        # 카드 우하단 → grid_wrap 좌표
        br_global = card.mapToGlobal(QPoint(card.width(), card.height()))
        br_wrap   = self._grid_wrap.mapFromGlobal(br_global)
        x = br_wrap.x() + 4
        y = br_wrap.y() - self._size_label.height() - 4
        # grid_wrap 영역 안에 들어오도록 보정
        x = max(4, min(self._grid_wrap.width() - self._size_label.width() - 4, x))
        y = max(4, min(self._grid_wrap.height() - self._size_label.height() - 4, y))
        self._size_label.move(x, y)

    def _has_collision_with(self, moving_key: str, cfg_candidate: dict) -> bool:
        cells = self._cells_of(cfg_candidate)
        for cfg in self._layout_cfg:
            if cfg.get("key") == moving_key: continue
            if not cfg.get("visible", True): continue
            if cells & self._cells_of(cfg):
                return True
        return False

    # ── 갱신 ─────────────────────────────────────────────────
    def _refresh_all_visible(self) -> None:
        active = [c.get("key") for c in self._layout_cfg if c.get("visible", True)]
        for fk in (("imbalance" if "imb" in active else None),
                   ("jkm" if "jkm" in active else None),
                   ("hjks" if "hjks" in active else None),
                   ("spot" if "spot" in active else None)):
            if fk: self.request_fetch.emit(fk)
        for key in active:
            card = self._cards.get(key)
            if card is None: continue
            for fn_name in ("refresh", "reload"):
                fn = getattr(card, fn_name, None)
                if callable(fn):
                    try: fn()
                    except Exception as e: logger.debug(f"{key}.{fn_name}() 실패: {e}")
                    break
        if "memo" in active:     self._refresh_memo_card()
        if "notice" in active:   self._refresh_notice_card()
        if "briefing" in active: self._refresh_brief_card()
        if "ai_chat" in active:  self._refresh_ai_card()
        self._status_lbl.setText(
            tr("全データ同期中  ·  最終更新 {0}").format(datetime.now().strftime("%H:%M:%S"))
        )
        try: bus.toast_requested.emit(tr("✅ 全カード更新を実行しました"), "success")
        except Exception: pass

    def refresh_data(self) -> None:
        self.request_fetch.emit("all")

    def refresh_imbalance(self): self.request_fetch.emit("imbalance")
    def refresh_jkm(self):       self.request_fetch.emit("jkm")
    def refresh_spot(self):      self.request_fetch.emit("spot")
    def refresh_hjks(self):      self.request_fetch.emit("hjks")

    def _mark_data_arrived(self, key: str) -> None:
        """카드에 데이터 도착 → 스켈레톤 hide."""
        self._cards_with_data.add(key)
        sk = self._skeletons.get(key)
        if sk is not None:
            sk.stop()

    # ── 데이터 핸들러 ────────────────────────────────────────
    def _on_imb_card_result(self, payload: dict):
        c = self._cards.get("imb")
        if c: c.set_payload(payload); self._mark_data_arrived("imb")

    def _on_imb_empty(self):
        c = self._cards.get("imb")
        if c: c.set_no_data(); self._mark_data_arrived("imb")

    def _on_jkm_card_result(self, payload: dict):
        c = self._cards.get("jkm")
        if c: c.set_payload(payload); self._mark_data_arrived("jkm")
        b = self._cards.get("briefing")
        if b:
            try: b.set_kpis(jkm=float(payload.get("latest") or 0.0))
            except Exception: pass

    def _on_jkm_empty(self):
        c = self._cards.get("jkm")
        if c: c.set_no_data(); self._mark_data_arrived("jkm")

    def _on_hjks_card_result(self, payload: dict):
        c = self._cards.get("hjks")
        if c: c.set_payload(payload); self._mark_data_arrived("hjks")

    def _on_hjks_empty(self):
        c = self._cards.get("hjks")
        if c: c.set_no_data(); self._mark_data_arrived("hjks")

    def update_occto(self, time_str, area_str, min_val):
        c = self._cards.get("power")
        if c: c.set_value(min_val, f"{time_str} / {area_str}"); self._mark_data_arrived("power")
        b = self._cards.get("briefing")
        if b:
            try: b.set_kpis(reserve=float(min_val))
            except Exception: pass

    def update_occto_areas(self, stats: list):
        c = self._cards.get("power")
        if c: c.set_areas(stats); self._mark_data_arrived("power")

    def update_weather(self, weather_list):
        self._weather_list = weather_list
        c = self._cards.get("weather")
        if c: c.set_entries(weather_list or []); self._mark_data_arrived("weather")

    def _on_spot_today_result(self, data: list):
        filtered = [row for row in data if row and row[0] != "システム"]
        c = self._cards.get("spot")
        if c: c.set_today_data(filtered); self._mark_data_arrived("spot")
        b = self._cards.get("briefing")
        if b:
            try:
                sys_row = next((r for r in data if r and r[0] == "システム"), None)
                if sys_row: b.set_kpis(spot=float(sys_row[1]))
                elif filtered:
                    avg = sum(float(r[1]) for r in filtered) / len(filtered)
                    b.set_kpis(spot=avg)
            except Exception: pass

    def _on_spot_tomorrow_result(self, data: list):
        c = self._cards.get("spot")
        if c: c.set_tomorrow_data([r for r in data if r and r[0] != "システム"])

    def _on_spot_yesterday_result(self, data: list):
        c = self._cards.get("spot")
        if c: c.set_yesterday_data([r for r in data if r and r[0] != "システム"])

    def _on_spot_today_slots_result(self, slots: list):
        c = self._cards.get("spot")
        if c: c.set_today_slots([v for _, v in slots] if slots else [])

    def _on_spot_tomorrow_slots_result(self, slots: list):
        c = self._cards.get("spot")
        if c: c.set_tomorrow_slots([v for _, v in slots] if slots else [])

    def _refresh_memo_card(self):
        c = self._cards.get("memo")
        if c is None: return
        try: c.set_memos(_load_memos())
        except Exception: c.set_memos([])
        self._mark_data_arrived("memo")

    def _refresh_notice_card(self):
        c = self._cards.get("notice")
        if c is None: return
        try: c.set_notifications(list_notifications())
        except Exception: c.set_notifications([])
        self._mark_data_arrived("notice")

    def _refresh_brief_card(self):
        c = self._cards.get("briefing")
        if c is None: return
        try: c.set_briefing(latest_briefing("daily", "ja"))
        except Exception: c.set_briefing(None)
        self._mark_data_arrived("briefing")

    def _refresh_ai_card(self):
        c = self._cards.get("ai_chat")
        if c is None: return
        try:
            user = latest_user_message()
            if user is None:
                c.set_no_data()
            else:
                ai_text = latest_assistant_after(user["session_id"], user["id"]) or ""
                c.set_data(user_text=user["content"], ai_text=ai_text)
        except Exception:
            c.set_no_data()
        self._mark_data_arrived("ai_chat")

    # ── + 버튼 ───────────────────────────────────────────────
    def _open_memo_new(self):
        bus.page_requested.emit(10)
        from PySide6.QtWidgets import QApplication as _QA
        def _trigger():
            from app.widgets.text_memo import TextMemoWidget
            for w in _QA.topLevelWidgets():
                for child in w.findChildren(TextMemoWidget):
                    child._new_memo(); return
        QTimer.singleShot(80, _trigger)

    def _open_ai_new(self):
        bus.page_requested.emit(11)
        from PySide6.QtWidgets import QApplication as _QA
        def _trigger():
            from app.widgets.ai_chat import AiChatWidget as _AW
            for w in _QA.topLevelWidgets():
                for child in w.findChildren(_AW):
                    child._on_new_session_clicked(); return
        QTimer.singleShot(80, _trigger)

    # ── 라이프사이클 ─────────────────────────────────────────
    def showEvent(self, event):
        super().showEvent(event)
        if "memo" in self._cards:    self._refresh_memo_card()
        if "notice" in self._cards:  self._refresh_notice_card()
        if "briefing" in self._cards: self._refresh_brief_card()
        if "ai_chat" in self._cards:  self._refresh_ai_card()
        # refresh() 메서드를 가진 카드들 — log/bug/gmail/calendar/manual
        for k in ("log", "bug", "gmail", "calendar", "manual"):
            card = self._cards.get(k)
            if card is None or not callable(getattr(card, "refresh", None)):
                continue
            try:
                card.refresh()
                self._mark_data_arrived(k)
            except Exception as e:
                logger.debug(f"{k}.refresh() 실패: {e}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 반응형 — < 900px 이면 compact mode
        new_compact = self.width() < _RESPONSIVE_BP_PX
        if new_compact != self._compact:
            self._compact = new_compact
            self._apply_grid_positions()
        else:
            # 사이즈 변경 시 오버레이/스켈레톤 위치 갱신
            QTimer.singleShot(0, self._sync_overlay_geom)

    def closeEvent(self, event):
        for sig, slot in [
            (bus.occto_updated,     self.update_occto),
            (bus.occto_areas,       self.update_occto_areas),
            (bus.imbalance_updated, self.refresh_imbalance),
            (bus.jkm_updated,       self.refresh_jkm),
            (bus.jepx_spot_updated, self.refresh_spot),
            (bus.hjks_updated,      self.refresh_hjks),
            (bus.weather_updated,   self.update_weather),
        ]:
            try: sig.disconnect(slot)
            except (RuntimeError, TypeError): pass
        super().closeEvent(event)

    # ── 테마 ─────────────────────────────────────────────────
    def apply_theme_custom(self):
        is_dark = self.is_dark
        self._apply_dashboard_qss(is_dark)
        for c in self._cards.values():
            if hasattr(c, "set_theme"):
                try: c.set_theme(is_dark)
                except Exception: pass
        for sk in self._skeletons.values():
            sk.set_theme(is_dark)
        # 편집 모드 overlay 도 테마 갱신
        for ov in self._overlays.values():
            if hasattr(ov, "set_theme"):
                try: ov.set_theme(is_dark)
                except Exception: pass

    def _apply_dashboard_qss(self, is_dark: bool) -> None:
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        bg_surface   = "#14161C" if is_dark else "#FFFFFF"
        border_subtle= "rgba(255,255,255,0.04)" if is_dark else "rgba(11,18,32,0.06)"
        self.setStyleSheet(f"""
            QFrame#dashGridWrap {{ background: transparent; }}
            QScrollArea#dashScroll {{
                background: transparent; border: none;
            }}
            QScrollArea#dashScroll > QWidget > QWidget {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(168, 176, 189, 0.4);
                border-radius: 4px;
                min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(168, 176, 189, 0.7);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QLabel#dashSizeLbl {{
                color: white;
                background: #FF7A45;
                font-size: 12px; font-weight: 800;
                padding: 5px 10px;
                border-radius: 6px;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QLabel#dashSizeLbl[invalid="true"] {{
                background: #FF453A;
            }}
            QLabel#dashDateCaption {{
                font-size: 11px; font-weight: 700;
                color: {fg_tertiary}; background: transparent;
                letter-spacing: 0.06em;
            }}
            QLabel#dashGreeting {{
                font-size: 28px; font-weight: 800;
                color: {fg_primary}; background: transparent;
                letter-spacing: -0.02em;
            }}
            QLabel#dashSummary {{
                font-size: 13px; color: {fg_secondary};
                background: transparent; padding-top: 2px;
            }}
            QWidget#dashStatusBar {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 10px;
            }}
            QLabel#dashStatusDot {{
                color: #30D158; background: transparent; font-size: 9px;
            }}
            QLabel#dashStatusText {{
                color: {fg_tertiary}; background: transparent; font-size: 11px;
            }}
            QLabel#dashStatusVersion {{
                color: {fg_tertiary}; background: transparent;
                font-size: 11px;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
        """)


__all__ = ["DashboardWidget"]
