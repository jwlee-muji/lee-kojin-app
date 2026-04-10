import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog
from PySide6.QtGui import QFont
from PySide6.QtCore import QThread, Signal, Qt, QObject
from main_window import MainWindow
from version import __version__


# ── アップデート完了処理 (_update.exe として起動された場合) ───────────────
def _finish_update(target_exe: Path):
    """
    _update.exe として --finish-update <target_exe> 引数で起動された時に呼ばれる。
    自分自身 (sys.executable = _update.exe) を target_exe に上書きコピーして
    target_exe を起動し、_update.exe を終了する。
    Qt を一切起動しないため DLL の競合が発生しない。
    """
    import shutil
    import time

    current_exe = Path(sys.executable)
    time.sleep(2)  # 旧プロセスが完全に終了するまで待機

    # コピー成功まで最大 30 秒リトライ
    for _ in range(30):
        try:
            shutil.copy2(str(current_exe), str(target_exe))
            break
        except OSError:
            time.sleep(1)
    else:
        # コピー失敗 → _update.exe のまま起動してお茶を濁す
        subprocess.Popen([str(current_exe)])
        sys.exit(0)

    # 正規パスで新バージョンを起動
    import subprocess
    subprocess.Popen([str(target_exe)])
    sys.exit(0)


# ── バックグラウンドでアップデートを確認するスレッド ──────────────────────
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


# ── バックグラウンドでダウンロードするスレッド ────────────────────────────
class DownloadWorker(QThread):
    progress = Signal(int, int)   # (downloaded_bytes, total_bytes)
    finished = Signal(str)        # new_exe_path
    error = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            from updater import download_update
            new_exe = download_update(
                self.url,
                progress_callback=lambda d, t: self.progress.emit(d, t),
            )
            self.finished.emit(str(new_exe))
        except Exception as e:
            self.error.emit(str(e))


# ── アップデート全体を管理するクラス ─────────────────────────────────────
class UpdateManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._check_worker = None
        self._download_worker = None
        self._progress_dialog = None

    def start_check(self):
        self._check_worker = UpdateCheckWorker()
        self._check_worker.result.connect(self._on_update_found)
        self._check_worker.start()

    def _on_update_found(self, info: dict):
        reply = QMessageBox.question(
            None,
            "アップデートのお知らせ",
            f"新しいバージョン v{info['version']} が利用可能です。\n"
            f"（現在: v{__version__}）\n\n"
            "今すぐ更新しますか？\n"
            "（ダウンロード後、アプリが自動的に再起動します）",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            self._start_download(info['url'])

    def _start_download(self, url: str):
        self._progress_dialog = QProgressDialog("準備中...", None, 0, 100)
        self._progress_dialog.setWindowTitle("アップデートをダウンロード中")
        self._progress_dialog.setWindowModality(Qt.ApplicationModal)
        self._progress_dialog.setMinimumDuration(0)
        self._progress_dialog.setMinimumWidth(380)
        self._progress_dialog.setValue(0)
        self._progress_dialog.show()

        self._download_worker = DownloadWorker(url)
        self._download_worker.progress.connect(self._on_progress)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.error.connect(self._on_download_error)
        self._download_worker.start()

    def _on_progress(self, downloaded: int, total: int):
        if not self._progress_dialog:
            return
        mb_done = downloaded / 1024 / 1024
        if total > 0:
            pct = int(downloaded / total * 100)
            mb_total = total / 1024 / 1024
            self._progress_dialog.setValue(pct)
            self._progress_dialog.setLabelText(
                f"ダウンロード中... {mb_done:.1f} MB / {mb_total:.1f} MB"
            )
        else:
            self._progress_dialog.setLabelText(f"ダウンロード中... {mb_done:.1f} MB")

    def _on_download_finished(self, new_exe_path: str):
        if self._progress_dialog:
            self._progress_dialog.close()
        QMessageBox.information(
            None, "アップデート完了",
            "ダウンロードが完了しました。\nアプリを再起動します。"
        )
        from updater import apply_update
        # _update.exe を --finish-update 引数付きで起動して旧アプリを終了
        apply_update(Path(new_exe_path), Path(sys.executable))
        QApplication.quit()

    def _on_download_error(self, err: str):
        if self._progress_dialog:
            self._progress_dialog.close()
        QMessageBox.warning(
            None, "ダウンロードエラー",
            f"ダウンロードに失敗しました:\n{err}"
        )


# ── エントリーポイント ────────────────────────────────────────────────────
def main():
    # _update.exe として起動された場合 → Qt 初期化前に完了処理だけ行って終了
    if len(sys.argv) == 3 and sys.argv[1] == '--finish-update':
        _finish_update(Path(sys.argv[2]))
        return

    app = QApplication(sys.argv)
    app.setFont(QFont("Meiryo", 9))

    window = MainWindow()
    window.show()

    update_manager = UpdateManager(app)
    update_manager.start_check()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
