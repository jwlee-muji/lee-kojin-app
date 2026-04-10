import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QFont
from PySide6.QtCore import QThread, Signal
from main_window import MainWindow
from version import __version__


class UpdateCheckWorker(QThread):
    result = Signal(dict)

    def run(self):
        try:
            from updater import check_for_update
            info = check_for_update()
            if info:
                self.result.emit(info)
        except Exception:
            pass


def show_update_dialog(info: dict):
    msg = QMessageBox()
    msg.setWindowTitle("アップデートのお知らせ")
    msg.setText(
        f"新しいバージョン <b>v{info['version']}</b> が公開されています。<br>"
        f"（現在: v{__version__}）<br><br>"
        f"<a href='{info['url']}'>ダウンロードページを開く</a>"
    )
    msg.setTextFormat(0x00000001)  # Qt.RichText
    msg.setStandardButtons(QMessageBox.Ok)
    msg.exec()


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Meiryo", 9))

    window = MainWindow()
    window.show()

    # バックグラウンドでアップデートを確認
    update_worker = UpdateCheckWorker()
    update_worker.result.connect(show_update_dialog)
    update_worker.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
