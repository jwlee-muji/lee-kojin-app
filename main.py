import sys
import logging
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from app.core.config import LOG_FILE, get_theme_qss

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
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = global_exception_handler

def main():
    # _update.exe 로 실행된 경우 → 업데이트 완료 처리만 하고 종료 (Qt 미기동)
    if len(sys.argv) == 3 and sys.argv[1] == '--finish-update':
        from app.core.updater import handle_finish_update
        handle_finish_update(Path(sys.argv[2]))
        return

    # 업데이트 후 정상 기동 시 → _update.exe 파일 삭제 후 계속 실행
    if len(sys.argv) == 3 and sys.argv[1] == '--cleanup':
        from app.core.updater import cleanup_update_file
        cleanup_update_file(Path(sys.argv[2]))

    # 다운로드 폴더에서 실행된 경우 이전 설치 경로로 이동
    from app.core.updater import handle_downloads_launch
    handle_downloads_launch()

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

    app.setFont(QFont("Meiryo, Segoe UI, sans-serif", 9))
    app.setStyle("Fusion")

    from app.ui.theme import get_global_qss
    app.setStyleSheet(get_theme_qss("dark") + "\n" + get_global_qss("dark"))

    app.setQuitOnLastWindowClosed(False)

    _resources_rc_loaded = False
    try:
        import resources_rc  # noqa: F401
        _resources_rc_loaded = True
    except ImportError:
        logger.debug("resources_rc.py が見つかりません。ファイルパスで代替します。")

    if _resources_rc_loaded:
        app.setWindowIcon(QIcon(":/img/icon.png"))
    else:
        icon_path = base_dir / "img" / "icon.png"
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))

    # ── ウィンドウ管理 ────────────────────────────────────────────────────
    from app.ui.login_window import LoginWindow
    from app.core.events import bus

    _state = {"main_window": None}

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
            login_win.hide()
            win.show_with_animation()
            logger.info(f"メインウィンドウ表示: {email}")
        except Exception as e:
            logger.critical("メインウィンドウ起動失敗", exc_info=True)
            from PySide6.QtWidgets import QMessageBox
            login_win.show()
            QMessageBox.critical(
                None,
                "起動エラー",
                f"メインウィンドウの起動に失敗しました。\n\n{type(e).__name__}: {e}\n\n"
                "ログファイルを確認してください。",
            )

    def _show_login():
        _state["main_window"] = None   # 旧ウィンドウを GC
        login_win.reset()
        login_win.show_animated()
        logger.info("ログイン画面に戻りました")

    login_win = LoginWindow()
    login_win.login_success.connect(_show_main)
    bus.user_logged_out.connect(_show_login)

    # --tray 起動は従来通りメインウィンドウを直接起動 (バックグラウンドデーモン用)
    if '--tray' in sys.argv:
        from app.ui.main_window import MainWindow
        win = MainWindow()
        _state["main_window"] = win
        win.hide()
    else:
        login_win.show_animated()

    update_manager = UpdateManager(app)
    update_manager.start_check()

    app.aboutToQuit.connect(lambda: logger.info("=== LEE電力モニター アプリ終了 ==="))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
