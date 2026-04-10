"""
自動アップデートモジュール
GitHub Releases API を使って新バージョンを確認し、
ダウンロード・自己置換・再起動を行う。
"""
import sys
import subprocess
import requests
from pathlib import Path
from packaging.version import Version
from version import __version__

GITHUB_REPO = "jwlee-muji/lee-kojin-app"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def check_for_update(timeout: int = 5):
    """
    最新リリースを確認する。
    新バージョンがあれば {"version": str, "url": str} を返す。
    最新版または取得失敗時は None を返す。
    """
    try:
        r = requests.get(RELEASES_API, timeout=timeout)
        r.raise_for_status()
        data = r.json()

        latest_ver = data.get("tag_name", "").lstrip("v")
        if not latest_ver:
            return None

        if Version(latest_ver) > Version(__version__):
            download_url = data.get("html_url", "")
            for asset in data.get("assets", []):
                if asset.get("name", "").endswith(".exe"):
                    download_url = asset["browser_download_url"]
                    break
            return {"version": latest_ver, "url": download_url}
    except Exception:
        pass
    return None


def download_update(url: str, progress_callback=None) -> Path:
    """
    新しい exe をダウンロードして <現在のexe>.new に保存する。
    progress_callback(downloaded_bytes, total_bytes) が随時呼ばれる。
    Returns: ダウンロード先の Path
    Raises: RuntimeError（開発環境）/ requests.RequestException
    """
    if not getattr(sys, 'frozen', False):
        raise RuntimeError("開発環境では自動更新はサポートされていません。")

    current_exe = Path(sys.executable)
    new_exe_path = current_exe.with_suffix('.new')

    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()

    total = int(r.headers.get('Content-Length', 0))
    downloaded = 0
    with open(new_exe_path, 'wb') as f:
        for chunk in r.iter_content(chunk_size=65536):
            f.write(chunk)
            downloaded += len(chunk)
            if progress_callback:
                progress_callback(downloaded, total)

    return new_exe_path


def apply_update(new_exe_path: Path):
    """
    バッチスクリプト経由で exe を自己置換し、再起動する。
    呼び出し後は QApplication.quit() でアプリを終了すること。
    (Windows: 実行中の exe は自分自身を上書きできないため bat 経由で行う)
    """
    current_exe = Path(sys.executable)

    # 旧プロセス終了を待ってから置換・再起動・自己削除するバッチ
    bat = (
        "@echo off\n"
        "timeout /t 2 /nobreak >nul\n"
        f'move /y "{new_exe_path}" "{current_exe}"\n'
        f'start "" "{current_exe}"\n'
        'del "%~f0"\n'
    )
    bat_path = current_exe.parent / "_update_apply.bat"
    bat_path.write_text(bat, encoding='shift_jis')

    subprocess.Popen(
        ['cmd', '/c', str(bat_path)],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
