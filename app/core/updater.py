"""
자동 업데이트 모듈 (インストーラー方式)

【업데이트 흐름】
  1. 앱 기동 시 GitHub Releases API로 신버전 확인
  2. 사용자가 동의하면 LEE_Setup.exe 를 임시 폴더에 다운로드
  3. LEE_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES 로 실행
  4. Inno Setup が実行中アプリを閉じてファイルを差し替え
  5. インストール完了後、新バージョンが自動起動
"""
import sys
import hashlib
import tempfile
import subprocess
import requests
import logging
import shutil
import time
from threading import Thread
from pathlib import Path
from typing import Optional
from packaging.version import Version
from PySide6.QtCore import QThread, Signal, Qt, QObject
from PySide6.QtWidgets import QMessageBox, QProgressDialog, QApplication
from app.core.config import __version__

logger = logging.getLogger(__name__)

GITHUB_REPO  = "jwlee-muji/lee-kojin-app"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


# ── 버전 확인 ─────────────────────────────────────────────────────────────
def check_for_update(timeout: int = 5) -> Optional[dict]:
    """신버전이 있으면 {"version": str, "url": str, "sha256_url": str}을 반환, 없으면 None."""
    try:
        r = requests.get(RELEASES_API, timeout=timeout)
        r.raise_for_status()
        data   = r.json()
        latest = data.get("tag_name", "").lstrip("v")
        if not latest:
            return None
        if Version(latest) <= Version(__version__):
            return None

        url        = ""
        sha256_url = ""
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name == "LEE_Setup.exe":
                url = asset["browser_download_url"]
            elif name == "LEE_Setup.sha256":
                sha256_url = asset["browser_download_url"]

        if not url:
            return None
        return {"version": latest, "url": url, "sha256_url": sha256_url}

    except requests.exceptions.RequestException as e:
        logger.warning(f"업데이트 확인 중 통신 오류: {e}")
    except Exception as e:
        logger.error(f"업데이트 확인 중 오류: {e}", exc_info=True)
    return None


def _verify_checksum(file_path: Path, sha256_url: str) -> bool:
    if not sha256_url:
        logger.error("SHA256 ファイルが Release に含まれていません。ダウンロードを中止します。")
        return False
    try:
        r = requests.get(sha256_url, timeout=15)
        r.raise_for_status()
        expected = r.text.strip().split()[0].lower()
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        actual = sha256.hexdigest()
        if actual != expected:
            logger.error(f"SHA256 検証失敗: expected={expected}, actual={actual}")
            return False
        logger.info("SHA256 検証成功")
        return True
    except Exception as e:
        logger.error(f"SHA256 検証中にエラー: {e}")
        return False


# ── 다운로드 ──────────────────────────────────────────────────────────────
def download_update(url: str, progress_callback=None, sha256_url: str = "") -> Path:
    """LEE_Setup.exe を一時フォルダへダウンロードして返す。"""
    if not getattr(sys, 'frozen', False):
        raise RuntimeError("開発環境では自動更新はサポートされていません。")

    tmp_dir  = Path(tempfile.mkdtemp(prefix="lee_update_"))
    out_path = tmp_dir / "LEE_Setup.exe"

    try:
        r = requests.get(url, stream=True, timeout=120)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"ダウンロード失敗: {e}")
        raise

    total = int(r.headers.get('Content-Length', 0))
    done  = 0
    with open(out_path, 'wb') as f:
        for chunk in r.iter_content(chunk_size=65536):
            f.write(chunk)
            done += len(chunk)
            if progress_callback:
                progress_callback(done, total)

    if not _verify_checksum(out_path, sha256_url):
        out_path.unlink(missing_ok=True)
        raise ValueError("SHA256 検証失敗。ダウンロードファイルが破損しています。")

    return out_path


# ── 업데이트 적용 ─────────────────────────────────────────────────────────
def apply_update(installer_path: Path):
    """インストーラーをサイレント実行。Inno Setup が既存アプリを閉じてファイルを更新する。"""
    log_file = installer_path.with_name("install_log.txt")
    subprocess.Popen(
        [str(installer_path), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/FORCECLOSEAPPLICATIONS', f'/LOG={log_file}'],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

def cleanup_update_file(src_dir: str):
    """アップデート完了後、インストーラーが配置されていた一時フォルダを遅延削除する。"""
    def _cleanup():
        time.sleep(3)  # インストーラーが完全に終了し、ファイルのロックが解除されるのを待つ
        target = Path(src_dir)
        # 安全のため、本当にアプリが作成した一時フォルダか名前でチェック
        if target.exists() and "lee_update_" in target.name:
            try:
                shutil.rmtree(target, ignore_errors=True)
                logger.info(f"アップデート一時フォルダを削除しました: {target}")
            except Exception as e:
                logger.warning(f"アップデート一時フォルダの削除に失敗しました: {e}")

    Thread(target=_cleanup, daemon=True).start()



# ── Qt 依存クラス (アップデート UI) ──────────────────────────────────────

class UpdateCheckWorker(QThread):
    result = Signal(dict)

    def run(self):
        try:
            info = check_for_update()
            if info:
                self.result.emit(info)
        except Exception as e:
            logger.error(f"UpdateCheckWorker エラー: {e}")


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
            path = download_update(
                self.url,
                progress_callback=lambda d, t: self.progress.emit(d, t),
                sha256_url=self.sha256_url,
            )
            self.finished.emit(str(path))
        except requests.exceptions.RequestException as e:
            self.error.emit(f"通信エラー: {e}")
        except (RuntimeError, IOError, ValueError) as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"予期しないエラー: {e}")


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
            "（ダウンロード後、インストーラーが自動実行されアプリが再起動します）",
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

    def _on_download_finished(self, installer_path: str):
        if self._progress_dialog:
            self._progress_dialog.close()
        QMessageBox.information(
            None,
            "アップデート準備完了",
            "ダウンロードが完了しました。\n"
            "インストーラーを起動します。アプリは自動的に再起動されます。"
        )
        apply_update(Path(installer_path))
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, '_is_quitting'):
                widget._is_quitting = True
        sys.exit(0)

    def _on_download_error(self, err: str):
        if self._progress_dialog:
            self._progress_dialog.close()
        QMessageBox.warning(None, "ダウンロードエラー", f"ダウンロードに失敗しました:\n{err}")
