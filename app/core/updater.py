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
from PySide6.QtCore import QThread, Signal, QObject, QTimer
from PySide6.QtWidgets import QApplication, QDialog
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
        self._last_url        = ""   # 재시도용
        self._last_sha256_url = ""

        # Dev simulation 상태
        self._dev_simulating  = False
        self._sim_timer       = None
        self._sim_progress    = 0

    def _parent_window(self):
        """현재 활성 윈도우를 다이얼로그 부모로 사용 (없으면 None)."""
        return QApplication.activeWindow()

    def start_check(self):
        self._check_worker = UpdateCheckWorker()
        self._check_worker.result.connect(self._on_update_found)
        self._check_worker.finished.connect(self._check_worker.deleteLater)
        self._check_worker.start()

    def _on_update_found(self, info: dict):
        from app.ui.dialogs import UpdateAvailableDialog
        dlg = UpdateAvailableDialog(__version__, info['version'], parent=self._parent_window())
        if dlg.exec() == QDialog.Accepted:
            self._start_download(info['url'], info.get('sha256_url', ''))

    def _start_download(self, url: str, sha256_url: str = ""):
        self._last_url        = url
        self._last_sha256_url = sha256_url

        from app.ui.dialogs import UpdateProgressDialog
        self._progress_dialog = UpdateProgressDialog(parent=self._parent_window())
        self._progress_dialog.show()

        if self._dev_simulating:
            self._start_simulated_download()
            return

        self._download_worker = DownloadWorker(url, sha256_url)
        self._download_worker.progress.connect(self._on_progress)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.error.connect(self._on_download_error)
        self._download_worker.finished.connect(self._download_worker.deleteLater)
        self._download_worker.start()

    def _on_progress(self, downloaded: int, total: int):
        if not self._progress_dialog:
            return
        downloaded_mb = downloaded / 1024 / 1024
        total_mb      = total / 1024 / 1024 if total > 0 else 0.0
        self._progress_dialog.update_progress(downloaded_mb, total_mb)

    def _on_download_finished(self, installer_path: str):
        if self._progress_dialog:
            # progress 다이얼로그는 closeEvent 를 무시하므로 deleteLater
            self._progress_dialog.deleteLater()
            self._progress_dialog = None

        from app.ui.dialogs import UpdateReadyDialog
        UpdateReadyDialog(parent=self._parent_window()).exec()

        if self._dev_simulating:
            logger.info("[DEV] アップデートシミュレーション完了 (apply_update スキップ)")
            self._dev_simulating = False
            return

        apply_update(Path(installer_path))
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, '_is_quitting'):
                widget._is_quitting = True
        sys.exit(0)

    def _on_download_error(self, err: str):
        if self._progress_dialog:
            self._progress_dialog.deleteLater()
            self._progress_dialog = None

        from app.ui.dialogs import DownloadErrorDialog
        dlg = DownloadErrorDialog(err, details="", parent=self._parent_window())
        dlg.retry.connect(self._on_retry_download)
        dlg.exec()

    def _on_retry_download(self):
        """DownloadErrorDialog 의 retry signal 핸들러."""
        if self._last_url:
            logger.info("ダウンロードを再試行します")
            self._start_download(self._last_url, self._last_sha256_url)

    # ── Dev: 가짜 업데이트 흐름 시뮬레이션 ────────────────────────────────
    def simulate_update_flow(self):
        """Ctrl+Shift+U: 실제 GitHub 통신 없이 다이얼로그 흐름을 시뮬레이션 (dev 전용).

        가짜 버전 정보로 _on_update_found 부터 흐름을 시작.
        Yes 선택 시 가짜 다운로드 진행률 → 완료 → ReadyDialog 까지.
        실제 apply_update / sys.exit 은 호출하지 않음.
        """
        if self._dev_simulating:
            logger.warning("[DEV] 既に シミュレーション 実行中")
            return
        logger.info("[DEV] アップデートシミュレーション開始")
        self._dev_simulating = True
        fake_info = {
            "version":    "9.9.9",
            "url":        "https://example.invalid/fake/LEE_Setup.exe",
            "sha256_url": "",
        }
        self._on_update_found(fake_info)
        # 사용자가 後で 선택하면 _on_update_found 만 실행되고 끝
        # Yes 선택 시 _start_download 가 호출되며 _start_simulated_download 로 분기됨
        if not self._progress_dialog:
            # Yes 안 누르고 닫음
            self._dev_simulating = False

    def _start_simulated_download(self):
        """가짜 다운로드: QTimer 로 50ms 마다 2% 씩 진행."""
        self._sim_progress = 0
        self._sim_timer = QTimer(self)
        self._sim_timer.timeout.connect(self._tick_simulated_progress)
        self._sim_timer.start(50)

    def _tick_simulated_progress(self):
        if not self._progress_dialog:
            self._sim_timer.stop()
            return
        self._sim_progress += 2
        # 가짜 18 MB 다운로드
        done_mb  = self._sim_progress * 0.18
        total_mb = 18.0
        self._progress_dialog.update_progress(done_mb, total_mb)

        if self._sim_progress >= 100:
            self._sim_timer.stop()
            self._sim_timer.deleteLater()
            self._sim_timer = None
            self._on_download_finished("")  # fake path
