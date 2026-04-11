import sys
from pathlib import Path


def main():
    # _update.exe 로 실행된 경우 → 업데이트 완료 처리만 하고 종료 (Qt 미기동)
    if len(sys.argv) == 3 and sys.argv[1] == '--finish-update':
        from app.updater import handle_finish_update
        handle_finish_update(Path(sys.argv[2]))
        return

    # 업데이트 후 정상 기동 시 → _update.exe 파일 삭제 후 계속 실행
    if len(sys.argv) == 3 and sys.argv[1] == '--cleanup':
        from app.updater import cleanup_update_file
        cleanup_update_file(Path(sys.argv[2]))

    # 다운로드 폴더에서 실행된 경우 이전 설치 경로로 이동
    from app.updater import handle_downloads_launch
    handle_downloads_launch()

    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont, QIcon
    from app.main_window import MainWindow
    from app.updater import UpdateManager

    app = QApplication(sys.argv)
    app.setFont(QFont("Meiryo", 9))

    # PyInstaller --onefile 환경에서는 리소스가 sys._MEIPASS 에 풀림
    base_dir  = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).parent
    icon_path = base_dir / "img" / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()

    update_manager = UpdateManager(app)
    update_manager.start_check()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
