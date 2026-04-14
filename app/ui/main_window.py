import logging
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QStackedWidget,
    QSplitter, QSystemTrayIcon, QMenu, QApplication, QPushButton, QMessageBox, QLabel,
    QListWidgetItem, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, QThread, QTimer, Signal, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui import QAction, QIcon, QColor
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
from app.ui.common import FadeStackedWidget, get_tinted_icon
from app.core.events import bus
from app.core.i18n import tr

logger = logging.getLogger(__name__)


class RetentionWorker(QThread):
    def run(self):
        from app.core.config import load_settings
        from app.core.database import run_retention_policy
        settings = load_settings()
        run_retention_policy(settings.get("retention_days", 1460))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.is_dark = True
        self._is_quitting = False
        self._notifications_tab_index = None
        self._setup_tray_icon()

        from version import __version__
        self.setWindowTitle(f"LEE 個人アプリ  v{__version__}")
        self.resize(1050, 650)

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # 사이드바 컨테이너 (메뉴 + 테마 토글 버튼)
        sidebar_container = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_container)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setIconSize(QSize(22, 22))
        sidebar_layout.addWidget(self.sidebar)

        self.network_lbl = QLabel(tr("🟢 オンライン"))
        self.network_lbl.setAlignment(Qt.AlignCenter)
        self.network_lbl.setStyleSheet("color: #4caf50; font-weight: bold; padding: 5px;")
        sidebar_layout.addWidget(self.network_lbl)

        self.theme_btn = QPushButton(tr("☀️ ライトモード"))
        self.theme_btn.setStyleSheet("margin: 5px; font-weight: bold;")
        self.theme_btn.clicked.connect(self._toggle_theme)
        sidebar_layout.addWidget(self.theme_btn)

        sidebar_container.setMinimumWidth(180)
        self.main_splitter.addWidget(sidebar_container)

        # 컨텐츠 영역
        self.content_stack = FadeStackedWidget()
        self.main_splitter.addWidget(self.content_stack)
        self.sidebar.currentRowChanged.connect(self.content_stack.setCurrentIndex)

        self.main_splitter.setSizes([200, 700])
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)

        # 알림 센터 패널 — 위젯 생성 전에 초기화해야 add_notification()이 안전하게 호출됨
        self.w_notifications = QListWidget()
        self.w_notifications.setWordWrap(True)
        self.w_notifications.setStyleSheet("QListWidget::item { border-bottom: 1px solid #333; padding: 15px; font-size: 13px; }")
        self.w_notifications.itemClicked.connect(self._mark_notification_read)
        self.w_notifications.itemDoubleClicked.connect(self._remove_notification)

        self.w_dashboard = DashboardWidget()
        self.w_reserve = PowerReserveWidget()
        self.w_imbalance = ImbalanceWidget()
        self.w_jkm = JkmWidget()
        self.w_weather = WeatherWidget()
        self.w_hjks = HjksWidget()
        self.w_log = LogViewerWidget()
        self.w_settings = SettingsWidget()
        self.w_bug_report = BugReportWidget()
        self.w_ai_chat = AiChatWidget()
        self.w_text_memo = TextMemoWidget()

        # 아이콘 목록을 저장하여 테마 변경 시 동기화에 사용
        self._page_icons = [
            "board", "power", "won", "fire", "weather", "plant", "notice",
            "chat", "memo", "log", "bug", "setting"
        ]

        # Event Bus 구독
        bus.settings_saved.connect(self._apply_settings_all)
        bus.page_requested.connect(self.sidebar.setCurrentRow)

        self._add_page(self.w_dashboard,      tr("ダッシュボード"),    "board")
        self._add_page(self.w_reserve,         tr("電力予備率"),        "power")
        self._add_page(self.w_imbalance,       tr("インバランス"),      "won")
        self._add_page(self.w_jkm,             tr("JKM LNG 価格"),     "fire")
        self._add_page(self.w_weather,         tr("全国天気"),          "weather")
        self._add_page(self.w_hjks,            tr("発電稼働状況"),      "plant")
        self._add_page(self.w_notifications,   tr("通知センター ({0})").format(0), "notice")
        self._add_page(self.w_ai_chat,         tr("AI チャット"),       "chat")
        self._add_page(self.w_text_memo,       tr("テキストメモ"),      "memo")
        self._add_page(self.w_log,             tr("システムログ"),      "log")
        self._add_page(self.w_bug_report,      tr("バグレポート"),      "bug")
        self._add_page(self.w_settings,        tr("設定"),              "setting")

        # 앱 기동 시 모든 위젯의 테마 초기 상태를 완벽하게 동기화
        self._sync_theme()

        # 起動時にディスプレイのど真ん中へ配置
        self._center_window()

        # 앱 기동 10초 후 백그라운드에서 오래된 데이터 자동 정리 및 백업 실행
        self._retention_worker = RetentionWorker(self)
        self._retention_worker.finished.connect(self._retention_worker.deleteLater)
        QTimer.singleShot(10000, self._retention_worker.start)
        bus.app_quitting.connect(self._safe_stop_retention)

    def _safe_stop_retention(self):
        try:
            if hasattr(self, '_retention_worker') and self._retention_worker.isRunning():
                self._retention_worker.quit()
                self._retention_worker.wait(1000)
        except RuntimeError:
            pass

        # OS 레벨 네트워크 모니터링 시작
        QApplication.instance().is_online = True
        QNetworkInformation.loadBackendByFeatures(QNetworkInformation.Feature.Reachability)
        self.net_info = QNetworkInformation.instance()
        if self.net_info:
            self.net_info.reachabilityChanged.connect(self._on_reachability_changed)
            is_online = self.net_info.reachability() == QNetworkInformation.Reachability.Online
            self._update_network_ui(is_online)

    def _center_window(self):
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)

    def add_notification(self, title: str, message: str):
        from datetime import datetime
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        item = QListWidgetItem(f"[{time_str}] {title}\n{message}")

        font = item.font()
        font.setBold(True)
        item.setFont(font)
        item.setData(Qt.UserRole, False)

        self.w_notifications.insertItem(0, item)
        self._update_notification_badge()

    def _mark_notification_read(self, item):
        if not item.data(Qt.UserRole):
            item.setData(Qt.UserRole, True)
            font = item.font()
            font.setBold(False)
            item.setFont(font)
            item.setForeground(QColor("#888888"))
            self._update_notification_badge()

    def _remove_notification(self, item):
        row = self.w_notifications.row(item)
        self.w_notifications.takeItem(row)
        self._update_notification_badge()

    def _update_notification_badge(self):
        unread_count = sum(
            1 for i in range(self.w_notifications.count())
            if not self.w_notifications.item(i).data(Qt.UserRole)
        )
        if self._notifications_tab_index is not None and self._notifications_tab_index < self.sidebar.count():
            self.sidebar.item(self._notifications_tab_index).setText(
                tr("通知センター ({0})").format(unread_count)
            )

    def _apply_settings_all(self):
        if hasattr(self.w_reserve,   'apply_settings'): self.w_reserve.apply_settings()
        if hasattr(self.w_imbalance, 'apply_settings'): self.w_imbalance.apply_settings()
        if hasattr(self.w_jkm,       'apply_settings'): self.w_jkm.apply_settings()
        if hasattr(self.w_weather,   'apply_settings'): self.w_weather.apply_settings()
        if hasattr(self.w_hjks,      'apply_settings'): self.w_hjks.apply_settings()

    def _toggle_theme(self):
        if hasattr(self, '_theme_anim'):
            self._theme_anim.stop()
        if hasattr(self, '_theme_overlay') and self._theme_overlay is not None:
            try:
                self._theme_overlay.deleteLater()
            except RuntimeError:
                pass
            self._theme_overlay = None

        self._theme_overlay = QLabel(self)
        self._theme_overlay.setPixmap(self.grab())
        self._theme_overlay.setGeometry(self.rect())
        self._theme_overlay.show()
        self._theme_overlay.raise_()

        self.is_dark = not self.is_dark
        app = QApplication.instance()
        from app.core.config import get_theme_qss
        from app.ui.theme import get_global_qss
        theme_mode = "dark" if self.is_dark else "light"
        app.setStyleSheet(get_theme_qss(theme_mode) + "\n" + get_global_qss(theme_mode))
        self.theme_btn.setText(tr("☀️ ライトモード") if self.is_dark else tr("🌙 ダークモード"))
        self._sync_theme()

        effect = QGraphicsOpacityEffect(self._theme_overlay)
        self._theme_overlay.setGraphicsEffect(effect)
        self._theme_anim = QPropertyAnimation(effect, b"opacity", self)
        self._theme_anim.setDuration(300)
        self._theme_anim.setStartValue(1.0)
        self._theme_anim.setEndValue(0.0)
        self._theme_anim.setEasingCurve(QEasingCurve.OutQuad)
        self._theme_anim.finished.connect(self._theme_overlay.deleteLater)
        self._theme_anim.start()

    def _on_reachability_changed(self, reachability):
        is_online = reachability == QNetworkInformation.Reachability.Online
        self._update_network_ui(is_online)

    def _update_network_ui(self, is_online):
        QApplication.instance().is_online = is_online
        if is_online:
            self.network_lbl.setText(tr("🟢 オンライン"))
            self.network_lbl.setStyleSheet("color: #4caf50; font-weight: bold; padding: 5px;")
        else:
            self.network_lbl.setText(tr("🔴 オフライン"))
            self.network_lbl.setStyleSheet("color: #ff5252; font-weight: bold; padding: 5px;")
            logger.warning(tr("ネットワーク接続が切断されました。自動更新を一時停止します。"))

    def _sync_theme(self):
        for i in range(self.content_stack.count()):
            w = self.content_stack.widget(i)
            if hasattr(w, 'set_theme'):
                w.set_theme(self.is_dark)

        for i, icon_name in enumerate(self._page_icons):
            if icon_name and i < self.sidebar.count():
                self.sidebar.item(i).setIcon(get_tinted_icon(f":/img/{icon_name}.svg", self.is_dark))

    def _setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QApplication.instance().windowIcon())
        self.tray_icon.setToolTip(tr("LEE電力モニター - バックグラウンド実行中"))

        tray_menu = QMenu()
        show_action = QAction(tr("開く (Open)"), self)
        show_action.triggered.connect(self._show_normal)

        quit_action = QAction(tr("完全に終了 (Quit)"), self)
        quit_action.triggered.connect(self._quit_app)

        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_normal()

    def _show_normal(self):
        self.showNormal()
        self.activateWindow()

    def _quit_app(self):
        self._is_quitting = True
        bus.app_quitting.emit()
        QApplication.instance().quit()

    def closeEvent(self, event):
        if self._is_quitting:
            event.accept()
            return

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(tr("終了の確認"))
        msg_box.setText(tr("アプリケーションを完全に終了しますか？\nそれともトレイ（バックグラウンド）に最小化しますか？"))

        btn_tray   = msg_box.addButton(tr("トレイに最小化"), QMessageBox.ActionRole)
        btn_quit   = msg_box.addButton(tr("完全に終了"),     QMessageBox.DestructiveRole)
        _btn_cancel = msg_box.addButton(tr("キャンセル"),    QMessageBox.RejectRole)

        msg_box.exec()

        if msg_box.clickedButton() is btn_quit:
            self._quit_app()
            event.accept()
        elif msg_box.clickedButton() is btn_tray:
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                tr("LEE電力モニター"),
                tr("バックグラウンドで実行中です。\nアイコンをダブルクリックで開きます。"),
                QApplication.instance().windowIcon(),
                3000
            )
        else:
            event.ignore()

    def _add_page(self, widget, label: str, icon_name: str = None):
        """위젯과 사이드바 항목을 한 번에 등록. 새 페이지 추가 시 이 메서드만 호출."""
        self.content_stack.addWidget(widget)

        # 알림 탭 인덱스를 저장하여 배지 업데이트에 사용
        if widget is self.w_notifications:
            self._notifications_tab_index = self.sidebar.count()
            if self.w_notifications.count() > 0:
                unread_count = sum(
                    1 for i in range(self.w_notifications.count())
                    if not self.w_notifications.item(i).data(Qt.UserRole)
                )
                label = tr("通知センター ({0})").format(unread_count)

        item = QListWidgetItem(label)
        if icon_name:
            item.setIcon(get_tinted_icon(f":/img/{icon_name}.svg", self.is_dark))

        self.sidebar.addItem(item)
