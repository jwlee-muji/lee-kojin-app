import sys
import logging
import traceback
from pathlib import Path
from app.core.config import LOG_FILE, get_theme_qss

# --- 통합 로그 시스템 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] %(name)s : %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
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

    from PySide6.QtWidgets import QApplication, QSplashScreen
    from PySide6.QtGui import QFont, QIcon, QPixmap, QPainter, QColor
    from PySide6.QtCore import Qt
    from PySide6.QtCore import QTranslator, QLocale
    from app.ui.main_window import MainWindow
    from app.core.updater import UpdateManager
    
    # 고해상도(HiDPI) 모니터 스케일링 지원 명시 (글자/그래프 흐림 방지)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)

    # PyInstaller --onefile環境ではリソースが sys._MEIPASS に展開される
    base_dir  = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).parent

    # 다국어 지원 (i18n) 설정
    translator = QTranslator()
    # 시스템 로캘(예: 한국어 OS면 ko_KR)에 맞는 번역 파일(.qm)을 translations 폴더에서 탐색
    locale_name = QLocale.system().name()
    # 추후 translations 폴더에 app_ko_KR.qm 등을 넣으면 자동으로 로드됩니다.
    if translator.load(f"app_{locale_name}", str(base_dir / "translations")):
        app.installTranslator(translator)

    app.setFont(QFont("Meiryo, Segoe UI, sans-serif", 9))
    app.setStyle("Fusion")

    from app.ui.theme import get_global_qss
    app.setStyleSheet(get_theme_qss("dark") + "\n" + get_global_qss("dark"))

    app.setQuitOnLastWindowClosed(False)  # 트레이 아이콘을 위해 마지막 창이 닫혀도 앱 유지

    # 앱 아이콘: Qt 가상 리소스(resources_rc) 우선, 없으면 파일 경로로 폴백
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

    is_tray = '--tray' in sys.argv

    if not is_tray:
        splash_pix = QPixmap(400, 200)
        splash_pix.fill(QColor("#1e1e1e"))
        painter = QPainter(splash_pix)
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Meiryo", 16, QFont.Bold))
        painter.drawText(splash_pix.rect(), Qt.AlignCenter, "LEE電力モニター\n\n起動中...")
        painter.end()
        
        splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
        splash.show()
        app.processEvents()

    window = MainWindow()
    if not is_tray:
        window.show()
        splash.finish(window)
    else:
        window.hide()

    update_manager = UpdateManager(app)
    update_manager.start_check()

    app.aboutToQuit.connect(lambda: logger.info("=== LEE電力モニター アプリ終了 ==="))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
