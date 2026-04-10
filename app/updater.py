"""
자동 업데이트 모듈

【업데이트 흐름】
  1. 앱 기동 시 GitHub Releases API로 신버전 확인
  2. 사용자가 동의하면 _update.exe 다운로드
  3. _update.exe 를 --finish-update <현재exe경로> 로 실행 후 앱 종료
  4. _update.exe 가 자신을 현재 exe 경로에 복사
  5. 복사 완료 후 정상 exe를 --cleanup <_update.exe경로> 로 실행 후 종료
  6. 정상 exe 가 기동하면서 _update.exe 삭제 (이미 종료됐으므로 파일 잠금 없음)
"""
import os
import sys
import subprocess
import requests
from pathlib import Path
from packaging.version import Version
from version import __version__

GITHUB_REPO   = "jwlee-muji/lee-kojin-app"
RELEASES_API  = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_APPDATA_DIR  = Path(os.environ.get('APPDATA', Path.home())) / 'LEE電力モニター'
_INSTALL_FILE = _APPDATA_DIR / 'install_path.txt'


# ── 버전 확인 ─────────────────────────────────────────────────────────────
def check_for_update(timeout: int = 5):
    """신버전이 있으면 {"version": str, "url": str}을 반환, 없으면 None."""
    try:
        r    = requests.get(RELEASES_API, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        latest = data.get("tag_name", "").lstrip("v")
        if not latest:
            return None
        if Version(latest) > Version(__version__):
            url = data.get("html_url", "")
            for asset in data.get("assets", []):
                if asset.get("name", "").endswith(".exe"):
                    url = asset["browser_download_url"]
                    break
            return {"version": latest, "url": url}
    except Exception:
        pass
    return None


# ── 다운로드 ──────────────────────────────────────────────────────────────
def download_update(url: str, progress_callback=None) -> Path:
    """새 exe를 <현재exe명>_update.exe 로 다운로드. 개발 환경에서는 RuntimeError."""
    if not getattr(sys, 'frozen', False):
        raise RuntimeError("開発環境では自動更新はサポートされていません。")

    current_exe  = Path(sys.executable)
    new_exe_path = current_exe.with_name(current_exe.stem + '_update.exe')

    r     = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    total = int(r.headers.get('Content-Length', 0))
    done  = 0
    with open(new_exe_path, 'wb') as f:
        for chunk in r.iter_content(chunk_size=65536):
            f.write(chunk)
            done += len(chunk)
            if progress_callback:
                progress_callback(done, total)
    return new_exe_path


# ── 업데이트 적용 ─────────────────────────────────────────────────────────
def apply_update(new_exe_path: Path, current_exe: Path):
    """_update.exe 를 --finish-update 인수로 실행. 호출 후 QApplication.quit() 할 것."""
    subprocess.Popen(
        [str(new_exe_path), '--finish-update', str(current_exe)],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


# ── 업데이트 완료 처리 (_update.exe 로 실행된 경우) ──────────────────────
def handle_finish_update(target_exe: Path):
    """
    _update.exe 로 --finish-update <target_exe> 로 기동됐을 때 호출.
    자신을 target_exe 에 복사 → target_exe 를 --cleanup <자기경로> 로 실행 → 종료.
    QApplication 을 전혀 생성하지 않으므로 DLL 충돌 없음.
    """
    import shutil, time

    current_exe = Path(sys.executable)
    time.sleep(2)   # 구버전 프로세스 완전 종료 대기

    for _ in range(30):
        try:
            shutil.copy2(str(current_exe), str(target_exe))
            break
        except OSError:
            time.sleep(1)
    else:
        # 복사 실패 시 _update.exe 그대로 기동
        subprocess.Popen([str(current_exe)])
        sys.exit(0)

    # 정상 exe 를 --cleanup <_update.exe경로> 로 실행
    # → _update.exe(자신)는 이미 종료 예정이므로 정상 exe 가 파일 잠금 없이 삭제 가능
    subprocess.Popen([str(target_exe), '--cleanup', str(current_exe)])
    sys.exit(0)


# ── _update.exe 파일 삭제 (정상 exe 기동 시 호출) ────────────────────────
def cleanup_update_file(update_exe: Path):
    """
    --cleanup <update_exe> 인수로 기동됐을 때 호출.
    _update.exe 는 이미 종료된 상태이므로 파일 잠금 없이 삭제 가능.
    """
    import time
    time.sleep(1)   # _update.exe 프로세스 완전 종료 대기
    for _ in range(10):
        try:
            if update_exe.exists():
                update_exe.unlink()
            break
        except OSError:
            time.sleep(1)


# ── 다운로드 폴더 실행 감지 ───────────────────────────────────────────────
def _get_downloads_folder() -> Path:
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        ) as key:
            return Path(winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")[0])
    except Exception:
        return Path.home() / "Downloads"


def handle_downloads_launch():
    """
    다운로드 폴더에서 실행된 경우 이전 설치 경로로 자동 이동.
    이전 경로 미등록 시 현재 경로를 설치 경로로 저장 후 그대로 실행.
    """
    if not getattr(sys, 'frozen', False):
        return

    current_exe = Path(sys.executable)
    downloads   = _get_downloads_folder()

    if current_exe.parent.resolve() != downloads.resolve():
        # 다운로드 폴더 아님 → 현재 경로를 설치 경로로 저장
        _save_install_path(current_exe)
        return

    # 다운로드 폴더에서 실행됨
    install_path = _load_install_path()
    if not install_path:
        _save_install_path(current_exe)
        return

    try:
        import shutil
        shutil.copy2(str(current_exe), str(install_path))
        subprocess.Popen([str(install_path)])
        sys.exit(0)
    except Exception:
        _save_install_path(current_exe)


def _save_install_path(exe_path: Path):
    _APPDATA_DIR.mkdir(parents=True, exist_ok=True)
    _INSTALL_FILE.write_text(str(exe_path), encoding='utf-8')


def _load_install_path() -> 'Path | None':
    try:
        p = Path(_INSTALL_FILE.read_text(encoding='utf-8').strip())
        return p if p.parent.exists() else None
    except Exception:
        return None


# ── Qt 의존 클래스 (업데이트 UI) ─────────────────────────────────────────
from PySide6.QtCore import QThread, Signal, Qt, QObject
from PySide6.QtWidgets import QMessageBox, QProgressDialog, QApplication


class UpdateCheckWorker(QThread):
    result = Signal(dict)

    def run(self):
        try:
            info = check_for_update()
            if info:
                self.result.emit(info)
        except Exception:
            pass


class DownloadWorker(QThread):
    progress = Signal(int, int)
    finished = Signal(str)
    error    = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            new_exe = download_update(self.url, progress_callback=lambda d, t: self.progress.emit(d, t))
            self.finished.emit(str(new_exe))
        except Exception as e:
            self.error.emit(str(e))


class UpdateManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._check_worker    = None
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
        mb = downloaded / 1024 / 1024
        if total > 0:
            self._progress_dialog.setValue(int(downloaded / total * 100))
            self._progress_dialog.setLabelText(
                f"ダウンロード中... {mb:.1f} MB / {total / 1024 / 1024:.1f} MB"
            )
        else:
            self._progress_dialog.setLabelText(f"ダウンロード中... {mb:.1f} MB")

    def _on_download_finished(self, new_exe_path: str):
        if self._progress_dialog:
            self._progress_dialog.close()
        QMessageBox.information(None, "アップデート完了", "ダウンロードが完了しました。\nアプリを再起動します。")
        apply_update(Path(new_exe_path), Path(sys.executable))
        QApplication.quit()

    def _on_download_error(self, err: str):
        if self._progress_dialog:
            self._progress_dialog.close()
        QMessageBox.warning(None, "ダウンロードエラー", f"ダウンロードに失敗しました:\n{err}")
