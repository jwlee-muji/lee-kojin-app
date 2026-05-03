import sys
import logging
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from app.core.config import LOG_FILE

# PyInstaller 静的解析用: build.bat にて --collect-submodules を使用するため、
# ここでの大量の import は不要になりました。

# --- 통합 로그 시스템 설정 ---
# RotatingFileHandler: 10MB 초과 시 자동 로테이션, 최대 2개 백업 파일 유지
_file_handler = RotatingFileHandler(
    LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=2, encoding='utf-8'
)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] %(name)s : %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        _file_handler,
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def global_exception_handler(exc_type, exc_value, exc_traceback):
    """앱 전역 미처리 예외 핸들러.

    P1-14 — Qt 이벤트 루프 중 발생한 unhandled exception 을 로그로 기록하고
    LeeDialog.error 로 사용자에게 알린 뒤, "バグ報告" 버튼으로 BugReport
    위젯을 자동으로 열어 즉시 신고 가능하도록 함.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical(
        "Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback)
    )

    # QApplication 이 살아있을 때만 다이얼로그 시도 (early-stage crash 보호)
    try:
        from PySide6.QtWidgets import QApplication
        if QApplication.instance() is None:
            return
        # LeeDialog import 는 lazy — 초기 부팅 단계 import 사이클 방지
        from app.ui.components import LeeDialog
        from app.core.events import bus

        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        message = f"{exc_type.__name__}: {exc_value}"

        # 다이얼로그 직접 인스턴스화 (LeeDialog.error 는 close 만 가능 → 버그 리포트 버튼 추가)
        dlg = LeeDialog("予期しないエラー", kind="error")
        dlg.set_message(message, details=tb_text[-2000:])   # 마지막 2000 chars 만
        dlg.add_button("閉じる", variant="ghost", role="reject")
        dlg.add_button("バグ報告", variant="primary", role="accept")
        result = dlg.exec()

        if result == 1:   # accepted = 버그 신고 클릭
            # MainWindow 의 BugReport 페이지로 이동 시그널 emit
            try:
                bus.page_requested.emit(0)   # BugReport 인덱스는 동적 — 일단 dashboard 로 이동
                bus.toast_requested.emit(
                    "バグ報告ページから詳細をお送りください", "info",
                )
            except Exception:
                pass
    except Exception:
        # 다이얼로그 표시 자체 실패 — 이미 로그에 기록되었으니 silent OK
        logger.warning("global_exception_handler dialog failed", exc_info=True)


sys.excepthook = global_exception_handler


def _qt_message_handler(mode, context, message):
    """Qt 내부 메시지 핸들러 — 모든 Qt 경고/에러를 로그로만 라우트.

    Qt 의 디폴트 핸들러는 critical/fatal 메시지에 대해 Windows 네이티브
    에러 다이얼로그를 띄울 수 있음 (특히 디버그 빌드에서). 이를 제거.
    """
    from PySide6.QtCore import QtMsgType
    msg_str = f"[Qt] {message}"
    if mode == QtMsgType.QtFatalMsg:
        logger.critical(msg_str)
    elif mode == QtMsgType.QtCriticalMsg:
        logger.error(msg_str)
    elif mode == QtMsgType.QtWarningMsg:
        logger.warning(msg_str)
    elif mode == QtMsgType.QtInfoMsg:
        logger.info(msg_str)
    else:
        logger.debug(msg_str)


# Qt 메시지 핸들러 설치 (QApplication 생성 전에)
try:
    from PySide6.QtCore import qInstallMessageHandler
    qInstallMessageHandler(_qt_message_handler)
except Exception:
    pass


def main():
    # インストーラーからの再起動時、使用済みの一時フォルダを自動削除する
    if len(sys.argv) >= 3 and sys.argv[1] == '--cleanup':
        from app.core.updater import cleanup_update_file
        cleanup_update_file(sys.argv[2])

    logger.info("=== LEE電力モニター アプリ起動 ===")

    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont, QIcon
    from PySide6.QtCore import Qt
    from app.core.updater import UpdateManager
    from app.core.i18n import init_language

    init_language()

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)

    base_dir = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).parent

    app.setStyle("Fusion")

    # resources_rc をフォントロードより先に import する
    _resources_rc_loaded = False
    try:
        import resources_rc  # noqa: F401
        _resources_rc_loaded = True
    except ImportError:
        logger.debug("resources_rc.py が見つかりません。ファイルパスで代替します。")

    from PySide6.QtGui import QFontDatabase
    if _resources_rc_loaded:
        QFontDatabase.addApplicationFont(":/fonts/Pretendard-Regular.otf")
        QFontDatabase.addApplicationFont(":/fonts/Pretendard-SemiBold.otf")
        QFontDatabase.addApplicationFont(":/fonts/Pretendard-Bold.otf")
        QFontDatabase.addApplicationFont(":/fonts/JetBrainsMono-Regular.ttf")
        app.setFont(QFont("Pretendard", 9))
        app.setWindowIcon(QIcon(":/img/icon.png"))
    else:
        app.setFont(QFont("Meiryo, Segoe UI, sans-serif", 9))
        icon_path = base_dir / "img" / "icon.png"
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))

    from app.ui.theme import ThemeManager
    ThemeManager.instance().set_theme("dark")

    app.setQuitOnLastWindowClosed(False)

    # ── ウィンドウ管理 ────────────────────────────────────────────────────
    from app.ui.login_window import LoginWindow
    from app.core.events import bus
    from PySide6.QtGui import QShortcut, QKeySequence

    _state = {"main_window": None}

    def _install_dev_shortcuts(window):
        """DEV: Ctrl+Shift+U → 가짜 업데이트 흐름 시뮬레이션."""
        sc = QShortcut(QKeySequence("Ctrl+Shift+U"), window)
        sc.activated.connect(update_manager.simulate_update_flow)

    def _show_main(email: str):
        # ① インメモリセッションメールを確実に設定 (SettingsWidget の管理者判定に使用)
        from app.core.config import set_session_email
        set_session_email(email)

        # ② ファイルにも保存 (userinfo API 失敗時のフォールバック)
        try:
            from app.api.google.auth import _save_user_email
            _save_user_email(email)
        except Exception:
            pass

        try:
            from app.ui.main_window import MainWindow
            win = MainWindow()
            _state["main_window"] = win
            _install_dev_shortcuts(win)
            login_win.hide()
            win.show_with_animation()
            logger.info(f"メインウィンドウ表示: {email}")
        except Exception as e:
            logger.critical("メインウィンドウ起動失敗", exc_info=True)
            from app.ui.components import LeeDialog
            from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton
            from PySide6.QtCore import Qt
            login_win.show()

            dlg = LeeDialog("起動エラー", kind="error", parent=login_win)
            dlg.set_message(
                f"メインウィンドウの起動に失敗しました。\n{type(e).__name__}: {e}",
                details=traceback.format_exc(),
            )

            # 로그 경로 라벨 + ログを開く 인라인 버튼 (디자인 모킹업)
            log_row = QFrame()
            log_row.setObjectName("startupErrLogRow")
            log_layout = QHBoxLayout(log_row)
            log_layout.setContentsMargins(10, 6, 6, 6)
            log_layout.setSpacing(6)
            path_lbl = QLabel(str(LOG_FILE))
            path_lbl.setObjectName("startupErrLogPath")
            path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            log_layout.addWidget(path_lbl, 1)
            inline_open = QPushButton("ログを開く")
            inline_open.setObjectName("startupErrInlineOpenBtn")
            inline_open.setCursor(Qt.PointingHandCursor)
            log_layout.addWidget(inline_open)
            log_row.setStyleSheet("""
                QFrame#startupErrLogRow {
                    background: #1B1E26;
                    border-radius: 6px;
                }
                QLabel#startupErrLogPath {
                    font-family: "JetBrains Mono", "Consolas", monospace;
                    color: #6B7280;
                    font-size: 10px;
                    background: transparent;
                }
                QPushButton#startupErrInlineOpenBtn {
                    background: transparent;
                    color: #FF7A45;
                    border: none;
                    font-size: 10px;
                    font-weight: 700;
                    padding: 4px 6px;
                }
                QPushButton#startupErrInlineOpenBtn:hover { color: #FF8A55; }
            """)
            dlg.add_body_widget(log_row)

            def _open_log_folder():
                import os
                try:
                    log_path = Path(LOG_FILE)
                    if log_path.parent.exists():
                        os.startfile(log_path.parent)  # type: ignore[attr-defined]
                except Exception:
                    pass
            inline_open.clicked.connect(_open_log_folder)

            # 푸터: ログを開く (left) + OK (right)
            log_btn = dlg.add_button("ログを開く", "secondary", role="reject")
            log_btn.clicked.disconnect()
            log_btn.clicked.connect(_open_log_folder)
            log_btn.clicked.connect(dlg.reject)
            dlg.add_button("OK", "primary", role="accept")

            dlg.exec()

    def _show_login():
        _state["main_window"] = None   # 旧ウィンドウを GC
        login_win.reset()
        login_win.show_animated()
        logger.info("ログイン画面に戻りました")

    # UpdateManager 를 윈도우 생성보다 먼저 만들어 _install_dev_shortcuts 가 참조 가능하게 함
    update_manager = UpdateManager(app)

    login_win = LoginWindow()
    login_win.login_success.connect(_show_main)
    bus.user_logged_out.connect(_show_login)
    _install_dev_shortcuts(login_win)

    # --tray 起動は従来通りメインウィンドウを直接起動 (バックグラウンドデーモン用)
    if '--tray' in sys.argv:
        from app.ui.main_window import MainWindow
        win = MainWindow()
        _state["main_window"] = win
        _install_dev_shortcuts(win)
        win.hide()
    else:
        login_win.show_animated()

    update_manager.start_check()

    # P1-15 — 이전 세션에서 송신 실패한 bug report 가 있으면 백그라운드 재송신
    def _flush_pending():
        try:
            from app.api.email_api import flush_pending_bug_reports
            n = flush_pending_bug_reports()
            if n:
                logger.info(f"전 세션 bug report 재송신 완료: {n} 건")
        except Exception:
            logger.warning("flush_pending_bug_reports 호출 실패", exc_info=True)
    from PySide6.QtCore import QTimer
    QTimer.singleShot(8_000, _flush_pending)   # 8 초 후 (네트워크 안정 시점)

    app.aboutToQuit.connect(lambda: logger.info("=== LEE電力モニター アプリ終了 ==="))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
