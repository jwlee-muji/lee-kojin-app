import logging
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QStackedWidget,
    QSplitter, QSystemTrayIcon, QMenu, QApplication, QPushButton, QMessageBox, QLabel,
    QListWidgetItem, QGraphicsOpacityEffect, QFrame,
)
from PySide6.QtCore import (
    Qt, QTimer, Signal, QPropertyAnimation, QEasingCurve, QSize,
    QByteArray,
)
from PySide6.QtGui import QAction, QIcon, QColor, QKeySequence, QShortcut
from PySide6.QtNetwork import QNetworkInformation
from app.widgets.power_reserve import PowerReserveWidget
from app.widgets.imbalance import ImbalanceWidget
from app.widgets.jkm import JkmWidget
from app.widgets.weather import WeatherWidget
from app.widgets.hjks import HjksWidget
from app.widgets.log_viewer import LogViewerWidget
from app.widgets.settings import SettingsWidget
from app.widgets.dashboard import DashboardWidget
from app.widgets.bug_report import BugReportWidget
from app.widgets.ai_chat import AiChatWidget
from app.widgets.text_memo import TextMemoWidget
from app.widgets.google_calendar import GoogleCalendarWidget
from app.widgets.gmail import GmailWidget
from app.widgets.jepx_spot import JepxSpotWidget
from app.ui.common import FadeStackedWidget, get_tinted_icon, clear_tint_cache
from app.ui.theme import UIColors
from app.core.events import bus
from app.core.i18n import tr
from app.api.database_worker import DataRetentionWorker

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.is_dark = True
        self._is_quitting = False
        self._theme_transitioning = False   # 테마 전환 중 중복 클릭 방지
        self._notifications_tab_index: int | None = None

        # row(sidebar) → content_stack index 매핑 (그룹 헤더는 제외)
        self._row_to_content:  dict[int, int] = {}
        # content_stack index → sidebar row 역매핑
        self._content_to_row:  dict[int, int] = {}
        # sidebar row → icon_name (테마 동기화용)
        self._row_icons:       dict[int, str]  = {}
        # 유틸리티 버튼 (하단 스트립) → content index
        self._util_btns:       list[tuple[QPushButton, int]] = []
        # 현재 활성 유틸리티 버튼
        self._active_util_btn: QPushButton | None = None
        # 사이드바 그룹 (접기/펼치기 상태 포함)
        # {"header_row": int, "item_rows": list[int], "collapsed": bool, "label": str}
        self._groups:          list[dict] = []

        self._setup_tray_icon()

        from app.core.config import __version__
        self.setWindowTitle(f"LEE 個人アプリ  v{__version__}")

        screen = QApplication.primaryScreen().availableGeometry()
        w = max(820, min(int(screen.width()  * 0.78), screen.width()))
        h = max(560, min(int(screen.height() * 0.82), screen.height()))
        self.resize(w, h)
        # チャイルドウィジェットの最小サイズヒントを上書きし、自由なリサイズを許容する
        self.setMinimumSize(680, 420)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # ── 사이드바 컨테이너 ─────────────────────────────────────────────────
        sidebar_container = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_container)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        self.sidebar = QListWidget()
        # HiDPI 대응: 논리 픽셀 기준으로 아이콘 크기 조정 (Qt6 가 DPI 스케일 자동 적용)
        _dpr = QApplication.primaryScreen().devicePixelRatio()
        _icon_px = int(20 * min(_dpr, 2.0)) if _dpr > 1.25 else 20
        self.sidebar.setIconSize(QSize(_icon_px, _icon_px))
        self.sidebar.itemClicked.connect(self._on_sidebar_item_clicked)
        sidebar_layout.addWidget(self.sidebar, 1)

        # ── 하단 유틸리티 스트립 (설정 / 로그 / 버그 리포트) ─────────────────
        util_frame = QFrame()
        util_frame.setObjectName("utilStrip")
        util_layout = QHBoxLayout(util_frame)
        util_layout.setContentsMargins(4, 4, 4, 4)
        util_layout.setSpacing(2)
        sidebar_layout.addWidget(util_frame)

        # ── 네트워크 상태 + 테마 버튼 ─────────────────────────────────────────
        self.network_lbl = QLabel(tr("🟢 オンライン"))
        self.network_lbl.setAlignment(Qt.AlignCenter)
        self.network_lbl.setStyleSheet(
            f"color: {UIColors.ONLINE_COLOR}; font-weight: bold; padding: 5px;"
        )
        sidebar_layout.addWidget(self.network_lbl)

        self.theme_btn = QPushButton(tr("☀️ ライトモード"))
        self.theme_btn.setStyleSheet("margin: 5px; font-weight: bold;")
        self.theme_btn.clicked.connect(self._toggle_theme)
        sidebar_layout.addWidget(self.theme_btn)

        sidebar_w = max(160, min(int(screen.width() * 0.12), 210))
        sidebar_container.setMinimumWidth(sidebar_w)
        self.main_splitter.addWidget(sidebar_container)

        # ── 컨텐츠 영역 ──────────────────────────────────────────────────────
        self.content_stack = FadeStackedWidget()
        self.main_splitter.addWidget(self.content_stack)
        self.sidebar.currentRowChanged.connect(self._on_sidebar_changed)

        self.main_splitter.setSizes([sidebar_w, w - sidebar_w])
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)

        # ── 알림 센터 (테마 지원 포함) ────────────────────────────────────────
        self.w_notifications = QListWidget()
        self.w_notifications.setWordWrap(True)
        self.w_notifications.itemClicked.connect(self._mark_notification_read)
        self.w_notifications.itemDoubleClicked.connect(self._remove_notification)

        # ── 위젯 생성 ──────────────────────────────────────────────────────────
        self.w_dashboard      = DashboardWidget()
        self.w_reserve        = PowerReserveWidget()
        self.w_imbalance      = ImbalanceWidget()
        self.w_jkm            = JkmWidget()
        self.w_weather        = WeatherWidget()
        self.w_hjks           = HjksWidget()
        self.w_log            = LogViewerWidget()
        self.w_settings       = SettingsWidget()
        self.w_bug_report     = BugReportWidget()
        self.w_ai_chat        = AiChatWidget()
        self.w_text_memo      = TextMemoWidget()
        self.w_google_calendar = GoogleCalendarWidget()
        self.w_gmail          = GmailWidget()
        self.w_jepx_spot      = JepxSpotWidget()

        # ── Event Bus 구독 ─────────────────────────────────────────────────────
        bus.settings_saved.connect(self._apply_settings_all)
        bus.page_requested.connect(self._navigate_to_content)
        bus.gmail_new_mail.connect(self._on_gmail_new_mail)

        # ── 사이드바 페이지 등록 (그룹 헤더 포함) ──────────────────────────────
        #  그룹 1: 電力データ
        self._add_group_header(tr("⚡  電力データ"))
        self._add_page(self.w_dashboard,       tr("ダッシュボード"),    "board")
        self._add_page(self.w_jepx_spot,       tr("スポット市場"),       "spot")
        self._add_page(self.w_reserve,         tr("電力予備率"),        "power")
        self._add_page(self.w_imbalance,       tr("インバランス"),      "won")
        self._add_page(self.w_jkm,             tr("JKM LNG 価格"),     "fire")
        self._add_page(self.w_weather,         tr("全国天気"),          "weather")
        self._add_page(self.w_hjks,            tr("発電稼働状況"),      "plant")
        #  그룹 2: Google
        self._add_group_header(tr("🔵  Google"))
        self._add_page(self.w_google_calendar, tr("Google カレンダー"), "calendar")
        self._add_page(self.w_gmail,           tr("Gmail"),             "gmail")
        #  그룹 3: ツール
        self._add_group_header(tr("🛠  ツール"))
        self._add_page(self.w_notifications,   tr("通知センター ({0})").format(0), "notice")
        self._add_page(self.w_ai_chat,         tr("AI チャット"),       "chat")
        self._add_page(self.w_text_memo,       tr("テキストメモ"),      "memo")

        # ── 유틸리티 하단 스트립 버튼 (설정 / 로그 / 버그) ─────────────────────
        #  content_stack에 먼저 추가
        self.content_stack.addWidget(self.w_log)
        self.content_stack.addWidget(self.w_bug_report)
        self.content_stack.addWidget(self.w_settings)
        log_idx      = self.content_stack.indexOf(self.w_log)
        bug_idx      = self.content_stack.indexOf(self.w_bug_report)
        settings_idx = self.content_stack.indexOf(self.w_settings)

        for icon_name, label, idx in [
            ("log",     tr("ログ"),      log_idx),
            ("bug",     tr("バグ"),      bug_idx),
            ("setting", tr("設定"),      settings_idx),
        ]:
            btn = QPushButton()
            btn.setObjectName("utilBtn")
            btn.setToolTip(label)
            btn.setCheckable(True)
            btn.setFixedHeight(32)
            btn.clicked.connect(lambda _, i=idx, b=btn: self._on_util_btn(i, b))
            util_layout.addWidget(btn, 1)
            self._util_btns.append((btn, idx))
            # 아이콘은 테마 동기화에서 설정됨
            self._row_icons[-(idx + 1)] = icon_name   # 음수 키로 유틸 아이콘 저장

        # ── 테마 초기화 + 창 배치 ────────────────────────────────────────────
        self._sync_theme()
        self._restore_geometry()
        self._restore_group_states()
        # show() 後にジオメトリを確定 (最大化解除 + 画面内補正)
        QTimer.singleShot(0, self._post_show_geometry_fix)

        # ── 키보드 단축키 (Ctrl+1~6) ──────────────────────────────────────────
        _KEYS = [Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4, Qt.Key_5, Qt.Key_6]
        for i, key in enumerate(_KEYS):
            sc = QShortcut(QKeySequence(Qt.CTRL | key), self)
            sc.activated.connect(lambda n=i: self._shortcut_navigate(n))
        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_Comma), self).activated.connect(
            lambda: self._navigate_to_content(settings_idx)
        )

        # ── 네트워크 모니터링 초기화 ───────────────────────────────────────────
        QApplication.instance().is_online = True
        QNetworkInformation.loadBackendByFeatures(QNetworkInformation.Feature.Reachability)
        self.net_info = QNetworkInformation.instance()
        if self.net_info:
            self.net_info.reachabilityChanged.connect(self._on_reachability_changed)
            is_online = (self.net_info.reachability()
                         == QNetworkInformation.Reachability.Online)
            self._update_network_ui(is_online)

        # ── 데이터 보존 백그라운드 작업 ───────────────────────────────────────
        from app.core.config import load_settings as _load
        _s = _load()
        self._retention_worker = DataRetentionWorker(_s.get("retention_days", 1460))
        self._retention_worker.finished.connect(self._retention_worker.deleteLater)
        QTimer.singleShot(0, self._retention_worker.start)
        bus.app_quitting.connect(self._safe_stop_retention)

    # ── 사이드바 헬퍼 ──────────────────────────────────────────────────────────

    def _refresh_header_colors(self, is_dark: bool):
        color = QColor("#e0e0e0" if is_dark else "#1a1a1a")
        for g in self._groups:
            item = self.sidebar.item(g["header_row"])
            if item:
                item.setForeground(color)

    def _add_group_header(self, label: str):
        """클릭 가능 그룹 헤더 (▼/▶ 접기 토글 지원)."""
        header_row = self.sidebar.count()
        item = QListWidgetItem(f"  ▼ {label}")
        item.setFlags(Qt.ItemIsEnabled)   # 클릭 가능, 선택 불가
        f = item.font(); f.setBold(True); f.setPointSize(11); item.setFont(f)
        item.setForeground(QColor("#e0e0e0" if self.is_dark else "#1a1a1a"))
        self.sidebar.addItem(item)
        self._groups.append({
            "header_row": header_row,
            "item_rows":  [],
            "collapsed":  False,
            "label":      label,
        })

    def _add_page(self, widget: QWidget, label: str, icon_name: str = ""):
        """위젯을 content_stack에, 라벨을 sidebar에 함께 등록."""
        content_idx = self.content_stack.count()
        self.content_stack.addWidget(widget)

        sidebar_row = self.sidebar.count()
        item = QListWidgetItem(f"  {label}")
        if icon_name:
            item.setIcon(get_tinted_icon(f":/img/{icon_name}.svg", self.is_dark))
        self.sidebar.addItem(item)

        self._row_to_content[sidebar_row] = content_idx
        self._content_to_row[content_idx] = sidebar_row
        if icon_name:
            self._row_icons[sidebar_row] = icon_name

        if widget is self.w_notifications:
            self._notifications_tab_index = sidebar_row

        # 마지막 그룹에 아이템 row 등록
        if self._groups:
            self._groups[-1]["item_rows"].append(sidebar_row)

    def _on_sidebar_item_clicked(self, item: QListWidgetItem):
        """그룹 헤더 클릭 → 접기/펼치기 토글."""
        row = self.sidebar.row(item)
        for group in self._groups:
            if group["header_row"] == row:
                self._toggle_group(group)
                return

    def _toggle_group(self, group: dict):
        """그룹 접기/펼치기."""
        group["collapsed"] = not group["collapsed"]
        collapsed = group["collapsed"]
        for row in group["item_rows"]:
            self.sidebar.setRowHidden(row, collapsed)
        # 헤더 ▼/▶ 갱신
        indicator = "▶" if collapsed else "▼"
        self.sidebar.item(group["header_row"]).setText(
            f"  {indicator} {group['label']}"
        )
        # 현재 선택 row가 숨겨진 경우 → 첫 번째 보이는 페이지로 이동
        if collapsed:
            current_row = self.sidebar.currentRow()
            if current_row in group["item_rows"]:
                first_visible = next(
                    (r for g in self._groups
                     for r in g["item_rows"]
                     if not g["collapsed"]),
                    None,
                )
                if first_visible is not None:
                    self.sidebar.setCurrentRow(first_visible)
        self._save_group_states()

    def _save_group_states(self):
        """그룹 접힘 상태를 설정 파일에 저장."""
        from app.core.config import load_settings, save_settings
        s = load_settings()
        s["sidebar_collapsed"] = {
            str(g["header_row"]): g["collapsed"] for g in self._groups
        }
        save_settings(s)

    def _restore_group_states(self):
        """저장된 그룹 접힘 상태 복원."""
        from app.core.config import load_settings
        states = load_settings().get("sidebar_collapsed", {})
        for g in self._groups:
            if states.get(str(g["header_row"]), False):
                g["collapsed"] = True
                for row in g["item_rows"]:
                    self.sidebar.setRowHidden(row, True)
                self.sidebar.item(g["header_row"]).setText(
                    f"  ▶ {g['label']}"
                )

    def _on_sidebar_changed(self, row: int):
        """사이드바 선택 변경 → 그룹 헤더이면 무시, 아니면 해당 페이지로 이동."""
        if row < 0 or row not in self._row_to_content:
            return
        content_idx = self._row_to_content[row]
        self.content_stack.setCurrentIndex(content_idx)
        # 유틸 버튼 선택 해제
        self._set_util_active(None)

    def _on_util_btn(self, content_idx: int, btn: QPushButton):
        """하단 유틸리티 버튼 클릭 → 해당 페이지로 이동, 사이드바 선택 해제."""
        self.sidebar.blockSignals(True)
        self.sidebar.clearSelection()
        self.sidebar.setCurrentRow(-1)
        self.sidebar.blockSignals(False)
        self.content_stack.setCurrentIndex(content_idx)
        self._set_util_active(btn)

    def _set_util_active(self, btn: QPushButton | None):
        """유틸 버튼의 활성 상태 시각화."""
        for b, _ in self._util_btns:
            b.setChecked(b is btn)
        self._active_util_btn = btn

    def _navigate_to_content(self, content_idx: int):
        """content_stack 인덱스로 직접 네비게이션 (이벤트 버스 page_requested 수신)."""
        if content_idx in self._content_to_row:
            row = self._content_to_row[content_idx]
            # 접힌 그룹에 있으면 자동 펼침
            for group in self._groups:
                if group["collapsed"] and row in group["item_rows"]:
                    self._toggle_group(group)
                    break
            self.sidebar.setCurrentRow(row)
        else:
            # 유틸 아이템
            self.content_stack.setCurrentIndex(content_idx)
            for btn, idx in self._util_btns:
                if idx == content_idx:
                    self._set_util_active(btn)
                    break

    def _shortcut_navigate(self, n: int):
        """Ctrl+1~6 → 보이는 페이지 순서로 이동."""
        rows = sorted(
            r for r in self._row_to_content
            if not self.sidebar.isRowHidden(r)
        )
        if n < len(rows):
            self.sidebar.setCurrentRow(rows[n])

    # ── 알림 센터 ──────────────────────────────────────────────────────────────

    def add_notification(self, title: str, message: str):
        from datetime import datetime
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        item = QListWidgetItem(f"[{time_str}] {title}\n{message}")
        f = item.font(); f.setBold(True); item.setFont(f)
        item.setData(Qt.UserRole, False)
        self.w_notifications.insertItem(0, item)
        self._update_notification_badge()

    def _mark_notification_read(self, item: QListWidgetItem):
        if not item.data(Qt.UserRole):
            item.setData(Qt.UserRole, True)
            f = item.font(); f.setBold(False); item.setFont(f)
            item.setForeground(QColor(UIColors.TEXT_MUTED))
            self._update_notification_badge()

    def _remove_notification(self, item: QListWidgetItem):
        self.w_notifications.takeItem(self.w_notifications.row(item))
        self._update_notification_badge()

    def _update_notification_badge(self):
        unread = sum(
            1 for i in range(self.w_notifications.count())
            if not self.w_notifications.item(i).data(Qt.UserRole)
        )
        if self._notifications_tab_index is not None:
            row = self._notifications_tab_index
            if row < self.sidebar.count():
                self.sidebar.item(row).setText(
                    f"  {tr('通知センター ({0})').format(unread)}"
                )

    # ── Gmail 새 메일 ──────────────────────────────────────────────────────────

    def _on_gmail_new_mail(self, label_name: str, unread_count: int):
        """Gmail 新着メール → 通知センター + トレイ通知."""
        title = tr("📧 新着メール ({0}件) - {1}").format(unread_count, label_name)
        self.add_notification("Gmail", title)
        if hasattr(self, "tray_icon") and self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                "Gmail", title, QSystemTrayIcon.Information, 4000,
            )

    # ── 테마 ───────────────────────────────────────────────────────────────────

    def _toggle_theme(self):
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
        # キャッシュキーに is_dark が含まれるため、テーマ切替時のクリアは不要。
        # 旧テーマのアイコンはキャッシュに残り、再切替時に再利用される。
        app = QApplication.instance()
        from app.core.config import get_theme_qss
        from app.ui.theme import get_global_qss
        mode = "dark" if self.is_dark else "light"
        app.setStyleSheet(get_theme_qss(mode) + "\n" + get_global_qss(mode))
        self.theme_btn.setText(
            tr("☀️ ライトモード") if self.is_dark else tr("🌙 ダークモード"))
        self._sync_theme()

        self._theme_effect = QGraphicsOpacityEffect(self._theme_overlay)
        self._theme_overlay.setGraphicsEffect(self._theme_effect)
        self._theme_anim = QPropertyAnimation(self._theme_effect, b"opacity", self)
        self._theme_anim.setDuration(300)
        self._theme_anim.setStartValue(1.0); self._theme_anim.setEndValue(0.0)
        self._theme_anim.setEasingCurve(QEasingCurve.OutQuad)
        self._theme_anim.finished.connect(self._theme_overlay.deleteLater)
        self._theme_anim.finished.connect(lambda: setattr(self, "_theme_transitioning", False))
        self._theme_anim.start()

    def _sync_theme(self):
        d = self.is_dark
        # 컨텐츠 위젯 테마 동기화
        for i in range(self.content_stack.count()):
            w = self.content_stack.widget(i)
            if hasattr(w, "set_theme"):
                w.set_theme(d)
        # 알림 센터 (BaseWidget 아닌 QListWidget)
        self.w_notifications.setStyleSheet(
            "QListWidget { background: #1e1e1e; color: #e0e0e0; }"
            "QListWidget::item { border-bottom: 1px solid #333; padding: 15px; font-size: 13px; }"
            if d else
            "QListWidget { background: #ffffff; color: #212121; }"
            "QListWidget::item { border-bottom: 1px solid #e0e0e0; padding: 15px; font-size: 13px; }"
        )
        # 사이드바 아이콘 갱신
        for row, icon_name in self._row_icons.items():
            if row >= 0 and row < self.sidebar.count():
                self.sidebar.item(row).setIcon(
                    get_tinted_icon(f":/img/{icon_name}.svg", d))
        # 유틸 버튼 아이콘 갱신
        for btn, idx in self._util_btns:
            key = -(idx + 1)
            icon_name = self._row_icons.get(key, "")
            if icon_name:
                btn.setIcon(get_tinted_icon(f":/img/{icon_name}.svg", d))
        # 유틸 스트립 스타일
        self._apply_util_strip_style(d)
        # 그룹 헤더 색 갱신
        self._refresh_header_colors(d)

    def _apply_util_strip_style(self, is_dark: bool):
        d = is_dark
        bg  = "#252526" if d else "#f0f0f0"
        bd  = "#3e3e42" if d else "#e0e0e0"
        txt = "#cccccc" if d else "#555555"
        act = "#0e639c" if d else "#1a73e8"
        self.findChild(QFrame, "utilStrip").setStyleSheet(f"""
            QFrame#utilStrip {{
                background: {bg};
                border-top: 1px solid {bd};
            }}
            QPushButton#utilBtn {{
                background: transparent;
                border: none;
                border-radius: 4px;
                color: {txt};
                font-size: 11px;
                padding: 2px 4px;
            }}
            QPushButton#utilBtn:hover {{
                background: {"rgba(255,255,255,0.08)" if d else "rgba(0,0,0,0.07)"};
            }}
            QPushButton#utilBtn:checked {{
                background: {act};
                color: #ffffff;
            }}
        """)

    # ── 설정 반영 ──────────────────────────────────────────────────────────────

    def _apply_settings_all(self):
        current = self.content_stack.currentWidget()
        for i in range(self.content_stack.count()):
            w = self.content_stack.widget(i)
            if not hasattr(w, "apply_settings"):
                continue
            if w is current:
                w.apply_settings()
            else:
                w._settings_dirty = True

    # ── 네트워크 ──────────────────────────────────────────────────────────────

    def _on_reachability_changed(self, reachability):
        self._update_network_ui(
            reachability == QNetworkInformation.Reachability.Online)

    def _update_network_ui(self, is_online: bool):
        QApplication.instance().is_online = is_online
        if is_online:
            self.network_lbl.setText(tr("🟢 オンライン"))
            self.network_lbl.setStyleSheet(
                f"color: {UIColors.ONLINE_COLOR}; font-weight: bold; padding: 5px;"
            )
        else:
            self.network_lbl.setText(tr("🔴 オフライン"))
            self.network_lbl.setStyleSheet(
                f"color: {UIColors.OFFLINE_COLOR}; font-weight: bold; padding: 5px;"
            )
            logger.warning("ネットワーク接続が切断されました。自動更新を一時停止します。")

    # ── 창 위치/크기 저장·복원 ────────────────────────────────────────────────

    def _restore_geometry(self):
        from app.core.config import load_settings
        geo = load_settings().get("window_geometry")
        if geo:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geo.encode()))
                return
            except Exception:
                pass
        self._center_window()

    def _post_show_geometry_fix(self):
        """show() 後に実行: 最大化を解除し画面内に収める。
        showNormal() は非同期なので、もう一度タイマーを挟んで補正する。"""
        if self.isMaximized() or self.isFullScreen():
            self.showNormal()
            QTimer.singleShot(80, self._ensure_on_screen)
        else:
            self._ensure_on_screen()

    def _save_geometry(self):
        from app.core.config import load_settings, save_settings
        s = load_settings()
        s["window_geometry"] = bytes(self.saveGeometry().toBase64()).decode()
        save_settings(s)

    def _center_window(self):
        geo = QApplication.primaryScreen().availableGeometry()
        self.move((geo.width() - self.width()) // 2,
                  (geo.height() - self.height()) // 2)

    def _ensure_on_screen(self):
        """保存済みジオメトリが現在のスクリーンに収まるよう補正する。
        サイズが画面を超える場合は画面比率 (78%/82%) で再計算する。"""
        screen = QApplication.primaryScreen().availableGeometry()
        g = self.geometry()
        if g.width() > screen.width() or g.height() > screen.height():
            cw = max(820, min(int(screen.width()  * 0.78), screen.width()))
            ch = max(560, min(int(screen.height() * 0.82), screen.height()))
        else:
            cw, ch = g.width(), g.height()
        cx = max(screen.x(), min(g.x(), screen.x() + screen.width()  - cw))
        cy = max(screen.y(), min(g.y(), screen.y() + screen.height() - ch))
        if (cw, ch, cx, cy) != (g.width(), g.height(), g.x(), g.y()):
            self.setGeometry(cx, cy, cw, ch)

    # ── 트레이 / 종료 ─────────────────────────────────────────────────────────

    def _setup_tray_icon(self):
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

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_normal()

    def _show_normal(self):
        self.showNormal(); self.activateWindow()

    def _quit_app(self):
        self._is_quitting = True
        self._save_geometry()
        bus.app_quitting.emit()
        QApplication.instance().quit()

    def closeEvent(self, event):
        if self._is_quitting:
            event.accept(); return
        msg = QMessageBox(self)
        msg.setWindowTitle(tr("終了の確認"))
        msg.setText(tr(
            "アプリケーションを完全に終了しますか？\n"
            "それともトレイ（バックグラウンド）に最小化しますか？"))
        btn_tray   = msg.addButton(tr("トレイに最小化"), QMessageBox.ActionRole)
        btn_quit   = msg.addButton(tr("完全に終了"),     QMessageBox.DestructiveRole)
        _btn_cancel = msg.addButton(tr("キャンセル"),    QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() is btn_quit:
            self._quit_app(); event.accept()
        elif msg.clickedButton() is btn_tray:
            self._save_geometry(); event.ignore(); self.hide()
            self.tray_icon.showMessage(
                tr("LEE電力モニター"),
                tr("バックグラウンドで実行中です。\nアイコンをダブルクリックで開きます。"),
                QApplication.instance().windowIcon(), 3000)
        else:
            event.ignore()

    def _safe_stop_retention(self):
        try:
            if hasattr(self, "_retention_worker") and self._retention_worker.isRunning():
                self._retention_worker.quit()
                self._retention_worker.wait(1000)
        except RuntimeError:
            pass
