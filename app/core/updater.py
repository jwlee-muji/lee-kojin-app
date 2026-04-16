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
import hashlib
import shutil
import time
import subprocess
import requests
import winreg
import logging
from pathlib import Path
from typing import Optional
from packaging.version import Version
from PySide6.QtCore import QThread, Signal, Qt, QObject
from PySide6.QtWidgets import QMessageBox, QProgressDialog, QApplication
from app.core.config import __version__
from app.core.config import APP_DIR, INSTALL_FILE

logger = logging.getLogger(__name__)

GITHUB_REPO   = "jwlee-muji/lee-kojin-app"
RELEASES_API  = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


# ── 버전 확인 ─────────────────────────────────────────────────────────────
def check_for_update(timeout: int = 5):
    """신버전이 있으면 {"version": str, "url": str, "sha256_url": str}을 반환, 없으면 None."""
    try:
        r    = requests.get(RELEASES_API, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        latest = data.get("tag_name", "").lstrip("v")
        if not latest:
            return None
        if Version(latest) > Version(__version__):
            url        = data.get("html_url", "")
            sha256_url = ""
            for asset in data.get("assets", []):
                name = asset.get("name", "")
                if name.endswith(".exe"):
                    url = asset["browser_download_url"]
                elif name.endswith(".sha256"):
                    sha256_url = asset["browser_download_url"]
            return {"version": latest, "url": url, "sha256_url": sha256_url}
    except requests.exceptions.RequestException as e:
        logger.warning(f"업데이트 확인 중 통신 오류 발생: {e}")
    except Exception as e:
        logger.error(f"업데이트 확인 중 예기치 않은 오류 발생: {e}", exc_info=True)
    return None


def _verify_checksum(exe_path: Path, sha256_url: str) -> bool:
    """GitHub Release の .sha256 ファイルと照合して整合性を確認します。
    sha256_url が空の場合はスキップ (True を返す)。"""
    if not sha256_url:
        return True
    try:
        r = requests.get(sha256_url, timeout=15)
        r.raise_for_status()
        # フォーマット: "<hex>  <filename>" または "<hex>"
        expected = r.text.strip().split()[0].lower()
        sha256 = hashlib.sha256()
        with open(exe_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        actual = sha256.hexdigest()
        if actual != expected:
            logger.error(f"SHA256 検証失敗: expected={expected}, actual={actual}")
            return False
        logger.info("SHA256 検証成功")
        return True
    except requests.exceptions.RequestException as e:
        logger.warning(f"SHA256 ファイルのダウンロードに失敗 (検証スキップ): {e}")
        return True  # ネットワーク障害時はスキップ (ダウンロード済みファイルを使用)
    except OSError as e:
        logger.error(f"SHA256 計算中に IO エラー: {e}")
        return False


# ── 다운로드 ──────────────────────────────────────────────────────────────
def download_update(url: str, progress_callback=None, sha256_url: str = "") -> Path:
    """새 exe를 <현재exe명>_update.exe 로 다운로드. 개발 환경에서는 RuntimeError."""
    if not getattr(sys, 'frozen', False):
        raise RuntimeError("開発環境では自動更新はサポートされていません。")

    current_exe  = Path(sys.executable)
    new_exe_path = current_exe.with_name(current_exe.stem + '_update.exe')

    try:
        r = requests.get(url, stream=True, timeout=120)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"업데이트 파일 다운로드 실패 (통신 오류): {url}, {e}")
        raise

    total = int(r.headers.get('Content-Length', 0))
    done  = 0
    try:
        with open(new_exe_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
                done += len(chunk)
                if progress_callback:
                    progress_callback(done, total)
    except IOError as e:
        logger.error(f"업데이트 파일 저장 실패: {new_exe_path}, {e}")
        raise

    if not _verify_checksum(new_exe_path, sha256_url):
        new_exe_path.unlink(missing_ok=True)
        raise ValueError("ダウンロードしたファイルの SHA256 検証に失敗しました。")

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
    current_exe = Path(sys.executable)
    logger.info(f"アップデート適用開始: {current_exe} → {target_exe}")
    time.sleep(0.3)  # 구버전 프로세스 종료 대기 (QApplication.quit() 후 OS가 파일 잠금 해제)

    for attempt in range(30):
        try:
            shutil.copy2(str(current_exe), str(target_exe))
            logger.info(f"ファイルコピー成功 (試行 {attempt + 1}回目)")
            break
        except OSError as e:
            logger.warning(f"コピー失敗 (試行 {attempt + 1}回目): {e}")
            time.sleep(0.3)
    else:
        # 복사 실패 시 _update.exe 그대로 기동
        logger.error("30回試行してもコピーに失敗。_update.exe をそのまま起動します。")
        subprocess.Popen([str(current_exe)])
        sys.exit(0)

    # 정상 exe 를 --cleanup <_update.exe경로> 로 실행
    # → _update.exe(자신)는 이미 종료 예정이므로 정상 exe 가 파일 잠금 없이 삭제 가능
    logger.info(f"新バージョンを起動します: {target_exe}")
    subprocess.Popen([str(target_exe), '--cleanup', str(current_exe)])
    sys.exit(0)


# ── _update.exe 파일 삭제 (정상 exe 기동 시 호출) ────────────────────────
def cleanup_update_file(update_exe: Path):
    """
    --cleanup <update_exe> 인수로 기동됐을 때 호출.
    _update.exe 는 이미 종료된 상태이므로 파일 잠금 없이 삭제 가능.
    """
    time.sleep(0.1)  # _update.exe プロセス終了まで最小限だけ待機
    for _ in range(10):
        try:
            if update_exe.exists():
                update_exe.unlink()
            break
        except OSError:
            time.sleep(0.3)


# ── 다운로드 폴더 실행 감지 ───────────────────────────────────────────────
def _get_downloads_folder() -> Path:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        ) as key:
            return Path(winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")[0])
    except (FileNotFoundError, TypeError) as e:
        logger.warning(f"다운로드 폴더 레지스트리 조회 실패, 기본 경로 반환: {e}, 기본 경로를 사용합니다.")
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
        shutil.copy2(str(current_exe), str(install_path))
        subprocess.Popen([str(install_path)])
        sys.exit(0)
    except (OSError, subprocess.SubprocessError) as e:
        logger.error(f"설치 경로로 복사 후 실행 실패: {e}")
        _save_install_path(current_exe)


def _save_install_path(exe_path: Path):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    INSTALL_FILE.write_text(str(exe_path), encoding='utf-8')


def _load_install_path() -> Optional[Path]:
    try:
        p = Path(INSTALL_FILE.read_text(encoding='utf-8').strip())
        return p if p.parent.exists() else None
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        logger.debug(f"설치 경로 파일 로드 실패: {e}")
        return None


# ── Qt 依存クラス (アップデート UI) ──────────────────────────────────────

class UpdateCheckWorker(QThread):
    result = Signal(dict)

    def run(self):
        try:
            info = check_for_update()
            if info:
                self.result.emit(info)
        except Exception as e:
            logger.error(f"UpdateCheckWorker 실행 중 오류: {e}")


class DownloadWorker(QThread):
    progress = Signal(int, int)
    finished = Signal(str)
    error    = Signal(str)

    def __init__(self, url: str, sha256_url: str = ""):
        super().__init__()
        self.url        = url
        self.sha256_url = sha256_url

    def run(self):
        try:
            new_exe = download_update(
                self.url,
                progress_callback=lambda d, t: self.progress.emit(d, t),
                sha256_url=self.sha256_url,
            )
            self.finished.emit(str(new_exe))
        except requests.exceptions.RequestException as e:
            self.error.emit(f"통신 오류: {e}")
        except (RuntimeError, IOError, ValueError) as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"예기치 않은 오류: {e}")


class UpdateManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._check_worker    = None
        self._download_worker = None
        self._progress_dialog = None

    def start_check(self):
        self._check_worker = UpdateCheckWorker()
        self._check_worker.result.connect(self._on_update_found)
        self._check_worker.finished.connect(self._check_worker.deleteLater)
        self._check_worker.start()

    def _on_update_found(self, info: dict):
        reply = QMessageBox.question(
            None,
            "アップデートのお知らせ",
            f"新しいバージョン v{info['version']} が利用可能です。\n"
            f"（現在: v{__version__}）\n\n"
            "今すぐ更新しますか？\n"
            "（ダウンロード後、アプリが自動的に再起動します）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._start_download(info['url'], info.get('sha256_url', ''))

    def _start_download(self, url: str, sha256_url: str = ""):
        self._progress_dialog = QProgressDialog("準備中...", None, 0, 100)
        self._progress_dialog.setWindowTitle("アップデートをダウンロード中")
        self._progress_dialog.setWindowModality(Qt.ApplicationModal)
        self._progress_dialog.setMinimumDuration(0)
        self._progress_dialog.setMinimumWidth(380)
        self._progress_dialog.setValue(0)
        self._progress_dialog.show()

        self._download_worker = DownloadWorker(url, sha256_url)
        self._download_worker.progress.connect(self._on_progress)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.error.connect(self._on_download_error)
        self._download_worker.finished.connect(self._download_worker.deleteLater)
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
        # closeEvent の「トレイ最小化／キャンセル」ダイアログが出ないよう、
        # MainWindow の終了フラグを立ててから強制終了する
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, '_is_quitting'):
                widget._is_quitting = True
            if hasattr(widget, 'network_monitor'):
                widget.network_monitor.stop()
        QApplication.quit()

    def _on_download_error(self, err: str):
        if self._progress_dialog:
            self._progress_dialog.close()
        QMessageBox.warning(None, "ダウンロードエラー", f"ダウンロードに失敗しました:\n{err}")
