"""MainWindow — Phase 4 리뉴얼.

레이아웃:
    ┌──────────────────────────────────────────────────────┐
    │  TopBar (48px)                                       │
    ├────────────┬─────────────────────────────────────────┤
    │            │                                         │
    │  Sidebar   │  Stage (FadeStackedWidget)              │
    │  (240px)   │                                         │
    │            │                                         │
    └────────────┴─────────────────────────────────────────┘

- TopBar: 로고 + 검색 (Ctrl+K) + 3 카테고리 필터 탭 (Market/Operation/Tool)
- Sidebar: 4 그룹 (market / ops / tool / system) — 접기/펴기 + 액티브 인디케이터
- Stage: 모든 페이지 등록, sidebar.item_clicked → setCurrentIndex
- closeEvent: QuitConfirmDialog (3 버튼)
- 트레이/테마/알림/토스트/단축키 모두 보존
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Callable

from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize, QByteArray,
    QRect, QPoint,
)
from PySide6.QtGui import (
    QAction, QIcon, QColor, QKeySequence, QShortcut,
)
from PySide6.QtNetwork import QNetworkInformation
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QSizePolicy, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from app.ui.components import LeeDialog, LeeSidebar, LeeTopBar
from app.ui.dialogs import QuitConfirmDialog

# ── 위젯 클래스 ─────────────────────────────────────────────────────────
from app.widgets.dashboard import DashboardWidget
from app.widgets.jepx_spot import JepxSpotWidget
from app.widgets.power_reserve import PowerReserveWidget
from app.widgets.imbalance import ImbalanceWidget
from app.widgets.jkm import JkmWidget
from app.widgets.weather import WeatherWidget
from app.widgets.hjks import HjksWidget
from app.widgets.google_calendar import GoogleCalendarWidget
from app.widgets.gmail import GmailWidget
from app.widgets.text_memo import TextMemoWidget
from app.widgets.ai_chat import AiChatWidget
from app.widgets.briefing import BriefingWidget
from app.widgets.manual import ManualWidget
from app.widgets.log_viewer import LogViewerWidget
from app.widgets.bug_report import BugReportWidget
from app.widgets.settings import SettingsWidget

from app.ui.common import FadeStackedWidget, get_tinted_icon
from app.ui.theme import UIColors
from app.core.events import bus
from app.core.constants import Timers, Animations, Layout, Notifications as NC
from app.core.i18n import tr
from app.api.database_worker import DataRetentionWorker

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 페이지 정의 — 순서가 곧 content_stack 인덱스 (대시보드 카드의 page_requested
# 인덱스 1~6 호환을 위해 market 그룹의 첫 7개 위젯 순서를 고정)
# ──────────────────────────────────────────────────────────────────────
_ITEM_DEFS: list[tuple[str, str, type, str, str, str]] = [
    # (key, group_key, factory, label_jp, icon_name, accent_color)
    # group_key 가 "system" 인 항목은 사이드바 푸터 영역 (그룹 헤더 없이)
    ("dashboard", "market", DashboardWidget,        "ダッシュボード",     "board",    "#A8B0BD"),
    ("spot",      "market", JepxSpotWidget,         "スポット市場",        "spot",     "#FF7A45"),
    ("power",     "market", PowerReserveWidget,     "電力予備率",          "power",    "#5B8DEF"),
    ("imb",       "market", ImbalanceWidget,        "インバランス",        "won",      "#F25C7A"),
    ("jkm",       "market", JkmWidget,              "エネルギー指標",      "fire",     "#F4B740"),
    ("weather",   "market", WeatherWidget,          "全国天気",            "weather",  "#2EC4B6"),
    ("hjks",      "market", HjksWidget,             "発電稼働状況",        "plant",    "#A78BFA"),
    ("calendar",  "ops",    GoogleCalendarWidget,   "カレンダー",          "calendar", "#34C759"),
    ("gmail",     "ops",    GmailWidget,            "Gmail",               "gmail",    "#EA4335"),
    ("notice",    "tools",  None,                   "通知センター",        "notice",   "#FF9500"),
    ("memo",      "tools",  TextMemoWidget,         "テキストメモ",        "memo",     "#FFCC00"),
    ("ai_chat",   "tools",  AiChatWidget,           "AI チャット",         "chat",     "#5856D6"),
    ("briefing",  "tools",  BriefingWidget,         "AI ブリーフィング",  "brief",     "#5856D6"),
    ("manual",    "system", ManualWidget,           "マニュアル",          "manual",   "#A8B0BD"),
    ("log",       "system", LogViewerWidget,        "ログ",                "log",      "#A8B0BD"),
    ("bug",       "system", BugReportWidget,        "バグ報告",            "bug",      "#A8B0BD"),
    ("settings",  "system", SettingsWidget,         "設定",                "setting",  "#A8B0BD"),
]

# 표시되는 일반 그룹 (system 은 별도 푸터 영역)
_GROUP_DEFS: list[tuple[str, str]] = [
    ("market", "電力データ"),
    ("ops",    "Google"),
    ("tools",  "ツール"),
]


class MainWindow(QMainWindow):
    """Frameless borderless window — TopBar 가 타이틀바 역할.

    순수 Qt mouseEvent 로 드래그/리사이즈/더블클릭 max/수동 스냅을 모두 처리.
    Windows 의 WS_THICKFRAME invisible padded border 가 visible edge 보다
    넓게 resize zone 을 만드는 문제를 피하기 위함.
    """

    BORDER_PX = 6  # 리사이즈 감지 영역 두께

    def __init__(self):
        super().__init__()
        self.is_dark = True
        self._is_quitting = False
        self._theme_transitioning = False

        # key ↔ content_stack 인덱스 매핑
        self._key_to_idx: dict[str, int] = {}
        self._idx_to_key: dict[int, str] = {}
        # 미생성 위젯 팩토리 (지연 생성)
        self._idx_factories: dict[int, Callable[[], QWidget]] = {}
        # key → 아이콘 이름 (테마 동기화용)
        self._key_to_icon: dict[str, str] = {}

        from app.core.config import __version__
        self.setWindowTitle(f"LEE 個人アプリ  v{__version__}")

        # ── Frameless ─────────────────────────────────────────────
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)

        screen = QApplication.primaryScreen().availableGeometry()
        w = max(Layout.WINDOW_MIN_WIDTH,  min(int(screen.width()  * Layout.WINDOW_WIDTH_RATIO),  screen.width()))
        h = max(Layout.WINDOW_MIN_HEIGHT, min(int(screen.height() * Layout.WINDOW_HEIGHT_RATIO), screen.height()))
        self.resize(w, h)
        self.setMinimumSize(Layout.WINDOW_ABSOLUTE_MIN_W, Layout.WINDOW_ABSOLUTE_MIN_H)

        # 트레이 아이콘 우선 셋업 (다른 곳에서 self.tray_icon 참조)
        self._setup_tray_icon()

        # 알림 센터 — Phase 5.8 신규 NotificationWidget (사이드바 콘텐츠)
        from app.widgets.notification import NotificationWidget
        self.w_notifications = NotificationWidget()

        # ── 메인 레이아웃: VBox(TopBar, HBox(Sidebar, Stage)) ─────
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.topbar = LeeTopBar()
        root.addWidget(self.topbar)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.sidebar = LeeSidebar()
        self.sidebar.set_icon_provider(lambda name, dark: get_tinted_icon(f":/img/{name}.svg", dark))

        self.content_stack = FadeStackedWidget()
        self.content_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        body_layout.addWidget(self.sidebar)
        body_layout.addWidget(self.content_stack, 1)
        root.addWidget(body, 1)

        # ── 사이드바 그룹 + 아이템 등록 ──────────────────────────
        self._setup_groups_and_pages()

        # ── 시그널 연결 ──────────────────────────────────────────
        self.sidebar.item_clicked.connect(self._on_item_clicked)
        self.sidebar.group_toggled.connect(self._save_group_states)
        self.topbar.top_tab_changed.connect(self.sidebar.set_active_tab)
        self.topbar.top_tab_changed.connect(self._on_top_tab_changed)
        self.topbar.theme_toggle_clicked.connect(self._toggle_theme)
        self.topbar.user_clicked.connect(self._on_user_pill_clicked)
        # 윈도우 컨트롤 (frameless 타이틀바)
        self.topbar.minimize_clicked.connect(self.showMinimized)
        self.topbar.maximize_toggle_clicked.connect(self._toggle_maximize)
        self.topbar.close_clicked.connect(self.close)

        # 유저 정보 → TopBar 아바타
        try:
            from app.api.google.auth import get_current_user_email
            _email = get_current_user_email() or ""
        except Exception:
            _email = ""
        if _email:
            self.topbar.set_user(email=_email)
        # 초기 테마 글리프 동기화
        self.topbar.set_theme_glyph(self.is_dark)

        # 알림 센터 DB 초기화 (sidebar item 등록 후 호출 — 라벨 갱신 가능)
        self._init_notification_db()

        # ── Event Bus 구독 ──────────────────────────────────────
        bus.settings_saved.connect(self._apply_settings_all)
        bus.page_requested.connect(self._navigate_to_content)
        bus.gmail_new_mail.connect(self._on_gmail_new_mail)
        bus.toast_requested.connect(self._show_toast)
        # 알림 변경 시 사이드바 배지 자동 갱신 — burst 대비 debounce
        from PySide6.QtCore import QTimer as _QTimer
        self._badge_refresh_timer = _QTimer(self)
        self._badge_refresh_timer.setSingleShot(True)
        self._badge_refresh_timer.setInterval(180)
        self._badge_refresh_timer.timeout.connect(self._update_notification_badge)
        bus.notifications_changed.connect(self._badge_refresh_timer.start)

        # ── 토스트 시스템 — Phase 6 LeeToast 로 단일화 ─────────────────────
        # 워밍업 / dedupe / 큐 / 우선순위 / 슬라이드 in 모두 ToastManager 가 처리
        from app.ui.components.toast import LeeToast as _LeeToast
        _LeeToast.set_host(self)

        # 테마 + 그룹 상태 + 윈도우 위치 복원
        self._sync_theme()
        self._restore_geometry()
        self._restore_group_states()

        # 초기 페이지: dashboard
        self._activate_key("dashboard")

        # 백그라운드 프리페치
        QTimer.singleShot(Timers.PREFETCH_DELAY_MS, self._prefetch_all_widgets)

        # 키보드 단축키
        self._setup_shortcuts()

        # 네트워크 모니터링
        self._setup_network()

        # 데이터 보존 워커
        self._setup_retention_worker()

        # 마우스 이벤트 인터셉트 — 자식 위젯 위에서도 edge resize / titlebar drag 동작
        # (QMainWindow.mousePressEvent 는 자식이 이벤트 흡수하면 호출 안 됨)
        QApplication.instance().installEventFilter(self)
        self.setMouseTracking(True)

        # 첫 표시 후 app_ready emit — 위젯들이 fetch 시작 신호로 사용 가능
        self._app_ready_emitted = False

    def showEvent(self, event):
        super().showEvent(event)
        # 한 번만 emit — 사용자 위젯 들이 첫 fetch 게이팅에 사용
        if not self._app_ready_emitted:
            self._app_ready_emitted = True
            QTimer.singleShot(50, bus.app_ready.emit)

    # ──────────────────────────────────────────────────────────────
    # 사이드바 / 페이지 셋업
    # ──────────────────────────────────────────────────────────────
    def _setup_groups_and_pages(self) -> None:
        # 일반 그룹 등록 (system 은 별도)
        for key, label in _GROUP_DEFS:
            self.sidebar.add_group(key, label)

        # 아이템 등록 (content_stack 도 동시 빌드)
        for key, group_key, factory, label, icon_name, color in _ITEM_DEFS:
            idx = self.content_stack.count()

            if key == "notice":
                # 알림 센터는 미리 만든 인스턴스 사용
                self.content_stack.addWidget(self.w_notifications)
            elif factory is None:
                self.content_stack.addWidget(QWidget())  # placeholder
            else:
                self.content_stack.addWidget(QWidget())  # placeholder
                self._idx_factories[idx] = factory

            self._key_to_idx[key] = idx
            self._idx_to_key[idx] = key
            self._key_to_icon[key] = icon_name

            if group_key == "system":
                self.sidebar.add_system_item(key, tr(label), icon_name=icon_name, color=color)
            else:
                self.sidebar.add_item(group_key, key, tr(label), icon_name=icon_name, color=color)

    def _on_user_pill_clicked(self) -> None:
        """TopBar 우상단 유저 아바타 pill 클릭 → 메뉴 (로그아웃)."""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QCursor
        menu = QMenu(self)
        act_logout = menu.addAction(tr("⏻  ログアウト"))
        chosen = menu.exec(QCursor.pos())
        if chosen is act_logout:
            self._do_logout()

    # ──────────────────────────────────────────────────────────────
    # 단축키 / 네트워크 / 워커
    # ──────────────────────────────────────────────────────────────
    def _setup_shortcuts(self) -> None:
        # Ctrl+K: TopBar 검색 포커스
        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_K), self).activated.connect(
            self.topbar.focus_search
        )
        # Ctrl+1~6: visible 사이드바 아이템 N번째로 이동
        _KEYS = [Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4, Qt.Key_5, Qt.Key_6]
        for i, key in enumerate(_KEYS):
            sc = QShortcut(QKeySequence(Qt.CTRL | key), self)
            sc.activated.connect(lambda n=i: self._shortcut_navigate(n))
        # Ctrl+,: 設定
        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Comma), self).activated.connect(
            lambda: self._activate_key("settings")
        )

    def _setup_network(self) -> None:
        QApplication.instance().is_online = True
        self.net_info = None
        try:
            QNetworkInformation.loadBackendByFeatures(QNetworkInformation.Feature.Reachability)
            self.net_info = QNetworkInformation.instance()
        except Exception as e:
            logger.warning(f"ネットワーク監視バックエンド初期化失敗 (無視して続行): {e}")
        if self.net_info:
            self.net_info.reachabilityChanged.connect(self._on_reachability_changed)
            is_online = (self.net_info.reachability() == QNetworkInformation.Reachability.Online)
            self._update_network_ui(is_online)

    def _setup_retention_worker(self) -> None:
        try:
            from app.core.config import load_settings as _load
            _s = _load()
            self._retention_worker = DataRetentionWorker(_s.get("retention_days", 1460))
            self._retention_worker.finished.connect(self._retention_worker.deleteLater)
            QTimer.singleShot(Timers.STARTUP_DELAY_MS, self._retention_worker.start)
            bus.app_quitting.connect(self._safe_stop_retention)
        except Exception as e:
            logger.warning(f"DataRetentionWorker 初期化失敗 (無視して続行): {e}")

    # ──────────────────────────────────────────────────────────────
    # 페이지 네비게이션
    # ──────────────────────────────────────────────────────────────
    def _activate_key(self, key: str) -> None:
        """Sidebar 활성 + Stage 전환 + 위젯 lazy create."""
        idx = self._key_to_idx.get(key)
        if idx is None:
            return
        # 접힌 그룹에 있다면 펼치기
        for group_key, g in self.sidebar._groups.items():
            for item_key, _btn in g["items"]:
                if item_key == key and g["collapsed"]:
                    self.sidebar.set_group_collapsed(group_key, False, emit=True)
                    break
        self._ensure_widget_created(idx)
        self.content_stack.setCurrentIndex(idx)
        self.sidebar.set_active(key)

    def _on_item_clicked(self, key: str) -> None:
        idx = self._key_to_idx.get(key)
        if idx is None:
            return
        self._ensure_widget_created(idx)
        self.content_stack.setCurrentIndex(idx)
        # 사이드바 아이템 클릭은 페이지 이동만. Top 탭 / 그룹 필터는 변경하지 않음
        # (사용자가 Top 탭을 직접 클릭한 경우에만 필터링)

    def _on_top_tab_changed(self, tab_key: str) -> None:
        """Top 탭 직접 클릭 시 그룹 첫 아이템으로 이동.
        빈 문자열 = 필터 해제 — 페이지 이동 없이 사이드바만 모두 표시."""
        if not tab_key:
            return  # 필터 해제만, 현재 페이지 유지
        if tab_key == "market":
            self._activate_key("dashboard")
            return
        first_key = next(
            (k for k, g, *_ in _ITEM_DEFS if g == tab_key),
            None,
        )
        if first_key is not None:
            self._activate_key(first_key)

    def _navigate_to_content(self, content_idx: int) -> None:
        """bus.page_requested(int) 핸들러 — 대시보드 카드 호환 (idx 1~6)."""
        key = self._idx_to_key.get(int(content_idx))
        if key is not None:
            self._activate_key(key)

    def _shortcut_navigate(self, n: int) -> None:
        """Ctrl+N → visible 아이템 N번째."""
        keys = self.sidebar.visible_item_keys()
        if 0 <= n < len(keys):
            self._activate_key(keys[n])

    def _ensure_widget_created(self, idx: int) -> None:
        if idx not in self._idx_factories:
            return
        factory = self._idx_factories.pop(idx)
        widget = factory()
        if hasattr(widget, "set_theme"):
            widget.set_theme(self.is_dark)
        self.content_stack.blockSignals(True)
        placeholder = self.content_stack.widget(idx)
        self.content_stack.insertWidget(idx, widget)
        self.content_stack.removeWidget(placeholder)
        self.content_stack.blockSignals(False)
        # QDateEdit/QDateTimeEdit popup 을 디자인 시스템 톤으로 통일
        try:
            from app.ui.components.mini_calendar import install_on_date_edits
            install_on_date_edits(widget)
        except Exception:
            pass

    def _prefetch_all_widgets(self) -> None:
        pending = sorted(self._idx_factories.keys())

        def _step(remaining: list[int]) -> None:
            if not remaining:
                return
            idx = remaining[0]
            if idx in self._idx_factories:
                self._ensure_widget_created(idx)
            if len(remaining) > 1:
                QTimer.singleShot(Timers.PREFETCH_INTERVAL_MS, lambda r=remaining[1:]: _step(r))

        if pending:
            _step(pending)

    # ──────────────────────────────────────────────────────────────
    # 그룹 접힘 상태 영속화
    # ──────────────────────────────────────────────────────────────
    def _save_group_states(self, *_args) -> None:
        from app.core.config import load_settings, save_settings
        s = load_settings()
        # key 형식이 변경됐으므로 새 키 명으로 저장
        s["sidebar_collapsed_v2"] = self.sidebar.collapsed_states()
        save_settings(s)

    def _restore_group_states(self) -> None:
        from app.core.config import load_settings
        states = load_settings().get("sidebar_collapsed_v2", {})
        if states:
            self.sidebar.restore_collapsed_states(states)

    # ──────────────────────────────────────────────────────────────
    # 알림 센터
    # ──────────────────────────────────────────────────────────────
    def _init_notification_db(self) -> None:
        """Phase 5.8: NotificationWidget 으로 모든 처리 위임. 초기 동기화만 수행."""
        from app.widgets.notification import ensure_notification_db
        ensure_notification_db()
        self._update_notification_badge()

    def add_notification(self, title: str, message: str, level: str = "info") -> None:
        """외부 (gmail 등) 에서 호출. bus.notifications_changed 가 자동으로 갱신."""
        from app.widgets.notification import add_notification as _add
        _add(title, message, level)

    def _update_notification_badge(self) -> None:
        from app.widgets.notification import count_unread
        unread = count_unread()
        suffix = f" ({unread})" if unread else ""
        self.sidebar.update_item_label("notice", tr("通知センター") + suffix)

    # ──────────────────────────────────────────────────────────────
    # Gmail 새 메일
    # ──────────────────────────────────────────────────────────────
    def _on_gmail_new_mail(self, label_name: str, unread_count: int) -> None:
        title = tr("📧 新着メール ({0}件) - {1}").format(unread_count, label_name)
        self.add_notification("Gmail", title)
        # 트레이 balloon — 메인 윈도우가 숨겨진 경우에만 (앱 보이면 알림센터에서 확인 가능)
        # + 최소 30 초 간격 — burst 시 Windows 네이티브 알림 폭주/깜빡임 방지
        if (hasattr(self, "tray_icon") and self.tray_icon.isVisible()
                and self.isHidden() and self._can_show_tray_balloon()):
            self.tray_icon.showMessage(
                "Gmail", title, QSystemTrayIcon.Information, 4000,
            )

    def _can_show_tray_balloon(self) -> bool:
        """트레이 balloon 발화 가능 여부 — 마지막 발화로부터 N 초 지났는지."""
        import time as _time
        now = _time.monotonic()
        last = getattr(self, "_last_tray_balloon_t", 0.0)
        if now - last < 30.0:    # 30 초 cooldown
            return False
        self._last_tray_balloon_t = now
        return True

    # ──────────────────────────────────────────────────────────────
    # 토스트 통지 (기존 로직 유지)
    # ──────────────────────────────────────────────────────────────
    def _show_toast(self, message: str, level: str = "info") -> None:
        """레거시 wrapper — LeeToast 직접 호출로 forward.

        외부 호출 호환을 위해 시그니처 유지 (신규 코드는 LeeToast.show() 권장).
        ToastManager 가 내부적으로 워밍업/dedupe/큐 모두 처리.
        """
        from app.ui.components.toast import LeeToast
        LeeToast.show(message, kind=level)

    # 레거시 토스트 메서드들은 LeeToast 시스템 (components/toast.py) 으로 단일화됨.
    # 워밍업 / dedupe / 큐 / 우선순위는 모두 ToastManager 가 처리.

    # ──────────────────────────────────────────────────────────────
    # 테마
    # ──────────────────────────────────────────────────────────────
    def _toggle_theme(self) -> None:
        if self._theme_transitioning:
            return
        self._theme_transitioning = True

        if hasattr(self, "_theme_anim"):
            try:   self._theme_anim.stop()
            except RuntimeError: pass
        if hasattr(self, "_theme_overlay") and self._theme_overlay is not None:
            try:   self._theme_overlay.deleteLater()
            except RuntimeError: pass
            self._theme_overlay = None
        self._theme_effect = None

        self._theme_overlay = QLabel(self)
        self._theme_overlay.setPixmap(self.grab())
        self._theme_overlay.setGeometry(self.rect())
        self._theme_overlay.show(); self._theme_overlay.raise_()

        self.is_dark = not self.is_dark
        from app.ui.theme import ThemeManager
        # 1) 글로벌 QSS 만 즉시 교체 (스냅샷 overlay 가 덮고 있어 사용자에게 보이지 않음)
        ThemeManager.instance().set_theme("dark" if self.is_dark else "light")
        self.topbar.set_theme_glyph(self.is_dark)

        self._theme_effect = QGraphicsOpacityEffect(self._theme_overlay)
        self._theme_overlay.setGraphicsEffect(self._theme_effect)
        self._theme_anim = QPropertyAnimation(self._theme_effect, b"opacity", self)
        self._theme_anim.setDuration(Animations.THEME_FADE_MS)
        self._theme_anim.setStartValue(1.0); self._theme_anim.setEndValue(0.0)
        self._theme_anim.setEasingCurve(QEasingCurve.OutQuad)
        self._theme_anim.finished.connect(self._theme_overlay.deleteLater)
        # 2) 무거운 per-widget set_theme 는 fade-out 완료 후에 (transition 중 stutter 방지)
        self._theme_anim.finished.connect(self._sync_theme)
        self._theme_anim.finished.connect(lambda: setattr(self, "_theme_transitioning", False))
        self._theme_anim.start()

    def _sync_theme(self) -> None:
        d = self.is_dark
        for i in range(self.content_stack.count()):
            w = self.content_stack.widget(i)
            if hasattr(w, "set_theme"):
                w.set_theme(d)
        self.w_notifications.setStyleSheet(UIColors.get_notification_list_style(d))
        self.sidebar.set_theme(d)

    # ──────────────────────────────────────────────────────────────
    # 설정 반영 / 네트워크 / 위치
    # ──────────────────────────────────────────────────────────────
    def _apply_settings_all(self) -> None:
        current = self.content_stack.currentWidget()
        for i in range(self.content_stack.count()):
            w = self.content_stack.widget(i)
            if not hasattr(w, "apply_settings"):
                continue
            if w is current:
                w.apply_settings()
            else:
                w._settings_dirty = True

    def _on_reachability_changed(self, reachability) -> None:
        self._update_network_ui(reachability == QNetworkInformation.Reachability.Online)

    def _update_network_ui(self, is_online: bool) -> None:
        QApplication.instance().is_online = is_online
        # TopBar 우상단 온라인 pill 갱신
        self.topbar.set_online(is_online)
        if not is_online:
            logger.warning("ネットワーク接続が切断されました。自動更新を一時停止します。")

    def _restore_geometry(self) -> None:
        from app.core.config import load_settings
        geo = load_settings().get("window_geometry")
        if geo:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geo.encode()))
                return
            except Exception:
                pass
        self._center_window()

    def _save_geometry(self) -> None:
        from app.core.config import load_settings, save_settings
        s = load_settings()
        s["window_geometry"] = bytes(self.saveGeometry().toBase64()).decode()
        save_settings(s)

    def _center_window(self) -> None:
        geo = QApplication.primaryScreen().availableGeometry()
        self.move((geo.width() - self.width()) // 2,
                  (geo.height() - self.height()) // 2)

    def _ensure_on_screen(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        g = self.geometry()
        if g.width() > screen.width() or g.height() > screen.height():
            cw = max(Layout.WINDOW_MIN_WIDTH,  min(int(screen.width()  * Layout.WINDOW_WIDTH_RATIO),  screen.width()))
            ch = max(Layout.WINDOW_MIN_HEIGHT, min(int(screen.height() * Layout.WINDOW_HEIGHT_RATIO), screen.height()))
        else:
            cw, ch = g.width(), g.height()
        cx = max(screen.x(), min(g.x(), screen.x() + screen.width()  - cw))
        cy = max(screen.y(), min(g.y(), screen.y() + screen.height() - ch))
        if (cw, ch, cx, cy) != (g.width(), g.height(), g.x(), g.y()):
            self.setGeometry(cx, cy, cw, ch)

    # ──────────────────────────────────────────────────────────────
    # 트레이 / 종료
    # ──────────────────────────────────────────────────────────────
    def _setup_tray_icon(self) -> None:
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QApplication.instance().windowIcon())
        self.tray_icon.setToolTip(tr("LEE電力モニター - バックグラウンド実行中"))
        menu = QMenu()
        show_action = QAction(tr("開く (Open)"), self)
        show_action.triggered.connect(self._show_normal)
        quit_action = QAction(tr("完全に終了 (Quit)"), self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(show_action); menu.addSeparator(); menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_normal()

    def _show_normal(self) -> None:
        self.showNormal(); self.activateWindow()

    def _quit_app(self) -> None:
        self._is_quitting = True
        try:
            QApplication.instance().removeEventFilter(self)
        except Exception:
            pass
        self._save_geometry()
        bus.app_quitting.emit()
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:
        if self._is_quitting:
            event.accept(); return
        dlg = QuitConfirmDialog(self)
        dlg.exec()
        if dlg.choice == QuitConfirmDialog.Quit:
            self._quit_app(); event.accept()
        elif dlg.choice == QuitConfirmDialog.Tray:
            self._save_geometry(); event.ignore(); self.hide()
            self.tray_icon.showMessage(
                tr("LEE電力モニター"),
                tr("バックグラウンドで実行中です。\nアイコンをダブルクリックで開きます。"),
                QApplication.instance().windowIcon(), 3000)
        else:
            event.ignore()

    # ──────────────────────────────────────────────────────────────
    # Frameless window chrome — 순수 Qt 기반 드래그/리사이즈/스냅
    # ──────────────────────────────────────────────────────────────
    # WS_THICKFRAME 의 invisible padded border 가 visible edge 보다 넓게
    # resize zone 을 만드는 문제를 피하기 위해 Windows native 프레임을
    # 비활성한 채 Qt 만으로 처리. Aero Snap 은 drag 종료 시점에 화면 가장자리
    # 거리 기반으로 수동 구현.

    _DRAG_NONE = 0
    _DRAG_MOVE = 1   # 타이틀바 드래그로 윈도우 이동
    _RESIZE_LEFT         = 0x01
    _RESIZE_RIGHT        = 0x02
    _RESIZE_TOP          = 0x04
    _RESIZE_BOTTOM       = 0x08
    _RESIZE_TOPLEFT      = _RESIZE_TOP | _RESIZE_LEFT
    _RESIZE_TOPRIGHT     = _RESIZE_TOP | _RESIZE_RIGHT
    _RESIZE_BOTTOMLEFT   = _RESIZE_BOTTOM | _RESIZE_LEFT
    _RESIZE_BOTTOMRIGHT  = _RESIZE_BOTTOM | _RESIZE_RIGHT
    _SNAP_PX = 16  # drag 종료 시 화면 edge 까지의 거리 임계값

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, event) -> None:
        # 윈도우 상태 변경 시 max 버튼 툴팁 갱신
        from PySide6.QtCore import QEvent as _QEvent
        if event.type() == _QEvent.WindowStateChange:
            if hasattr(self, "topbar"):
                self.topbar.set_maximized(self.isMaximized())
        super().changeEvent(event)

    # ── 마우스 이벤트: 드래그 / 리사이즈 / 더블클릭 max 토글 ───────
    def _edge_at(self, local_pos: QPoint) -> int:
        """local_pos 가 윈도우 가장자리 영역이면 _RESIZE_* 비트 마스크, 아니면 0."""
        if self.isMaximized():
            return 0
        b = self.BORDER_PX
        x, y = local_pos.x(), local_pos.y()
        w, h = self.width(), self.height()
        edge = 0
        if x < b:           edge |= self._RESIZE_LEFT
        elif x >= w - b:    edge |= self._RESIZE_RIGHT
        if y < b:           edge |= self._RESIZE_TOP
        elif y >= h - b:    edge |= self._RESIZE_BOTTOM
        return edge

    def _cursor_for_edge(self, edge: int):
        if edge in (self._RESIZE_TOPLEFT, self._RESIZE_BOTTOMRIGHT):
            return Qt.SizeFDiagCursor
        if edge in (self._RESIZE_TOPRIGHT, self._RESIZE_BOTTOMLEFT):
            return Qt.SizeBDiagCursor
        if edge in (self._RESIZE_LEFT, self._RESIZE_RIGHT):
            return Qt.SizeHorCursor
        if edge in (self._RESIZE_TOP, self._RESIZE_BOTTOM):
            return Qt.SizeVerCursor
        return Qt.ArrowCursor

    # 마우스 이벤트는 QApplication 레벨 eventFilter 로 처리.
    # QMainWindow 의 mousePressEvent 는 centralWidget 의 자식들이 이벤트를
    # 흡수하면 호출되지 않으므로, 자식 위젯의 마우스 이벤트도 가로채려면
    # app.installEventFilter(self) 가 필요하다.
    # P1-9 — 모든 마우스 이벤트 가로채기 비용을 최소화하기 위해 5 종류만 통과
    _RELEVANT_EVENT_TYPES = frozenset()   # 첫 호출 때 lazy 초기화

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent as _QEvent
        et = event.type()

        # 0) Fast path — 마우스 이벤트가 아니면 즉시 반환 (대부분의 경우)
        if not MainWindow._RELEVANT_EVENT_TYPES:
            MainWindow._RELEVANT_EVENT_TYPES = frozenset({
                _QEvent.MouseButtonPress, _QEvent.MouseButtonRelease,
                _QEvent.MouseMove, _QEvent.MouseButtonDblClick,
            })
        if et not in MainWindow._RELEVANT_EVENT_TYPES:
            return False

        # 우리 윈도우 안의 위젯 이벤트만 처리
        if not isinstance(obj, QWidget) or obj.window() is not self:
            return False

        # ── 1) MouseButtonPress: edge 면 resize 시작, 타이틀바 빈 영역이면 drag ──
        if et == _QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            global_pos = event.globalPosition().toPoint()
            local = self.mapFromGlobal(global_pos)
            edge = self._edge_at(local)
            if edge:
                self._drag_state = self._DRAG_NONE
                self._resize_edge = edge
                self._drag_start_global = global_pos
                self._drag_start_geo = self.geometry()
                return True  # consume — 자식 위젯이 받지 않게
            # 타이틀바 드래그?
            if hasattr(self, "topbar") and 0 <= local.y() < self.topbar.height():
                tb_local = self.topbar.mapFromGlobal(global_pos)
                if self.topbar.is_drag_zone(tb_local):
                    self._drag_state = self._DRAG_MOVE
                    self._resize_edge = 0
                    self._drag_start_global = global_pos
                    self._drag_start_geo = self.geometry()
                    self._drag_start_was_max = self.isMaximized()
                    return True
            return super().eventFilter(obj, event)

        # ── 2) MouseMove: 진행 중인 drag/resize 처리 + idle 시 edge cursor ──
        if et == _QEvent.MouseMove:
            global_pos = event.globalPosition().toPoint()
            if getattr(self, "_drag_state", 0) == self._DRAG_MOVE:
                self._do_drag_move(global_pos)
                return True
            if getattr(self, "_resize_edge", 0):
                self._apply_resize(global_pos)
                return True
            # idle: edge 위면 cursor 변경 (인터랙티브 자식 위는 무시)
            if not (event.buttons() & Qt.LeftButton):
                local = self.mapFromGlobal(global_pos)
                edge = self._edge_at(local)
                if edge:
                    if self.cursor().shape() != self._cursor_for_edge(edge):
                        self.setCursor(self._cursor_for_edge(edge))
                else:
                    if self.cursor().shape() != Qt.ArrowCursor:
                        self.unsetCursor()
            return super().eventFilter(obj, event)

        # ── 3) MouseButtonRelease: drag 종료 → 수동 스냅 ──
        if et == _QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if getattr(self, "_drag_state", 0) == self._DRAG_MOVE:
                self._maybe_snap(event.globalPosition().toPoint())
                self._drag_state = self._DRAG_NONE
                return True
            if getattr(self, "_resize_edge", 0):
                self._resize_edge = 0
                return True
            return super().eventFilter(obj, event)

        # ── 4) MouseButtonDblClick: 타이틀바 빈 영역 더블클릭 → max 토글 ──
        if et == _QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
            global_pos = event.globalPosition().toPoint()
            local = self.mapFromGlobal(global_pos)
            if hasattr(self, "topbar") and 0 <= local.y() < self.topbar.height():
                tb_local = self.topbar.mapFromGlobal(global_pos)
                if self.topbar.is_drag_zone(tb_local):
                    self._toggle_maximize()
                    return True

        return super().eventFilter(obj, event)

    def _do_drag_move(self, global_pos: QPoint) -> None:
        """진행 중인 타이틀바 드래그 — 윈도우 이동 + 최대화 상태 복원."""
        delta = global_pos - self._drag_start_global
        # 최대화 상태에서 드래그 시작 시 → 복원하면서 마우스 위치 비례 이동
        if getattr(self, "_drag_start_was_max", False):
            self.showNormal()
            ratio = (self._drag_start_global.x() - self._drag_start_geo.left()) / max(1, self._drag_start_geo.width())
            new_left = global_pos.x() - int(self.width() * ratio)
            self.move(new_left, global_pos.y() - 10)
            self._drag_start_global = global_pos
            self._drag_start_geo = self.geometry()
            self._drag_start_was_max = False
            return
        self.move(self._drag_start_geo.topLeft() + delta)

    def _apply_resize(self, global_pos: QPoint) -> None:
        """현재 마우스 글로벌 위치로 윈도우 geometry 재계산 + 적용."""
        edge = self._resize_edge
        delta = global_pos - self._drag_start_global
        geo = QRect(self._drag_start_geo)
        min_w = self.minimumWidth() or 200
        min_h = self.minimumHeight() or 200

        if edge & self._RESIZE_LEFT:
            new_left = geo.left() + delta.x()
            new_left = min(new_left, geo.right() - min_w + 1)
            geo.setLeft(new_left)
        if edge & self._RESIZE_RIGHT:
            new_right = geo.right() + delta.x()
            new_right = max(new_right, geo.left() + min_w - 1)
            geo.setRight(new_right)
        if edge & self._RESIZE_TOP:
            new_top = geo.top() + delta.y()
            new_top = min(new_top, geo.bottom() - min_h + 1)
            geo.setTop(new_top)
        if edge & self._RESIZE_BOTTOM:
            new_bottom = geo.bottom() + delta.y()
            new_bottom = max(new_bottom, geo.top() + min_h - 1)
            geo.setBottom(new_bottom)
        self.setGeometry(geo)

    def _maybe_snap(self, global_pos: QPoint) -> None:
        """드래그 종료 위치가 화면 가장자리 근처면 스냅."""
        screen = QApplication.screenAt(global_pos) or QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        snap = self._SNAP_PX
        # 상단 → 최대화
        if global_pos.y() <= avail.top() + snap:
            self.showMaximized()
            return
        # 좌측 → 화면 좌측 절반
        if global_pos.x() <= avail.left() + snap:
            half = QRect(avail.left(), avail.top(), avail.width() // 2, avail.height())
            self.setGeometry(half)
            return
        # 우측 → 화면 우측 절반
        if global_pos.x() >= avail.right() - snap:
            half = QRect(avail.left() + avail.width() // 2, avail.top(),
                         avail.width() - avail.width() // 2, avail.height())
            self.setGeometry(half)
            return

    def _safe_stop_retention(self) -> None:
        try:
            if hasattr(self, "_retention_worker") and self._retention_worker.isRunning():
                self._retention_worker.quit()
                self._retention_worker.wait(1000)
        except RuntimeError:
            pass

    # ──────────────────────────────────────────────────────────────
    # ログアウト
    # ──────────────────────────────────────────────────────────────
    @staticmethod
    def _build_user_card(email: str) -> QFrame:
        """로그아웃 다이얼로그용 사용자 카드 (아바타 22px + email mono)."""
        box = QFrame()
        box.setObjectName("userInfoCard")
        h = QHBoxLayout(box)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(10)

        # 아바타 (이메일 첫 글자)
        initial = (email[:1] or "?").upper()
        avatar = QLabel(initial)
        avatar.setObjectName("userInfoAvatar")
        avatar.setFixedSize(22, 22)
        avatar.setAlignment(Qt.AlignCenter)
        h.addWidget(avatar)

        text_box = QVBoxLayout()
        text_box.setSpacing(0)
        # 이메일 앞부분 (@ 앞) → 이름 자리
        name = email.split("@", 1)[0] if "@" in email else email
        name_lbl = QLabel(name)
        name_lbl.setObjectName("userInfoName")
        email_lbl = QLabel(email)
        email_lbl.setObjectName("userInfoEmail")
        text_box.addWidget(name_lbl)
        text_box.addWidget(email_lbl)
        h.addLayout(text_box, 1)

        box.setStyleSheet("""
            QFrame#userInfoCard {
                background: #1B1E26;
                border: 1px solid rgba(255,255,255,0.04);
                border-radius: 8px;
            }
            QLabel#userInfoAvatar {
                background: #FF7A45;
                color: #ffffff;
                border-radius: 11px;
                font-size: 10px;
                font-weight: 800;
            }
            QLabel#userInfoName {
                color: #F2F4F7;
                font-size: 11px;
                font-weight: 700;
                background: transparent;
            }
            QLabel#userInfoEmail {
                font-family: "JetBrains Mono", "Consolas", monospace;
                color: #6B7280;
                font-size: 10px;
                background: transparent;
            }
        """)
        return box

    def _do_logout(self) -> None:
        from app.core.config import get_session_email
        email = get_session_email() or ""

        # 디자인 모킹업: warning 아이콘 + 메시지 + 사용자 카드 (아바타 + name + email)
        dlg = LeeDialog(tr("ログアウト"), kind="warning", parent=self)
        dlg.set_message(tr(
            "ログアウトしますか？\n"
            "Google アカウントの認証は解除されます。\n"
            "次回ログイン時に再度サインインが必要です。"
        ))
        if email:
            dlg.add_body_widget(self._build_user_card(email))
        dlg.add_button(tr("キャンセル"), "secondary", role="reject")
        dlg.add_button(tr("ログアウト"), "destructive", role="accept")
        from PySide6.QtWidgets import QDialog as _QDialog
        if dlg.exec() != _QDialog.Accepted:
            return
        bus.app_quitting.emit()
        try:
            from app.api.google.auth import revoke_credentials
            revoke_credentials()
        except Exception:
            pass
        self._save_geometry()
        self._is_quitting = True
        bus.user_logged_out.emit()
        QTimer.singleShot(50, self.close)

    # ──────────────────────────────────────────────────────────────
    # 표시 애니메이션
    # ──────────────────────────────────────────────────────────────
    def show_with_animation(self) -> None:
        self.setWindowOpacity(0.0)
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self.show()
        self.raise_()
        self.activateWindow()

        if self.isMaximized() or self.isFullScreen():
            self.showNormal()
        self._ensure_on_screen()

        target_pos = self.pos()
        start_pos = QPoint(target_pos.x(), target_pos.y() + 40)
        self.move(start_pos)

        self._anim_win_op = QPropertyAnimation(self, b"windowOpacity")
        self._anim_win_op.setStartValue(0.0); self._anim_win_op.setEndValue(1.0)
        self._anim_win_op.setDuration(Animations.WINDOW_SHOW_MS)
        self._anim_win_op.setEasingCurve(QEasingCurve.OutCubic)

        self._anim_win_pos = QPropertyAnimation(self, b"pos")
        self._anim_win_pos.setStartValue(start_pos); self._anim_win_pos.setEndValue(target_pos)
        self._anim_win_pos.setDuration(Animations.WINDOW_SLIDE_MS)
        self._anim_win_pos.setEasingCurve(QEasingCurve.OutCubic)

        def _start_anims():
            self._anim_win_op.start()
            self._anim_win_pos.start()

        QTimer.singleShot(Animations.STARTUP_ANIM_DELAY_MS, _start_anims)
