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

    改善点:
    - 現在プロセスの PID を渡し、完全に終了するまで待機してから move を実行
    - move 失敗時はリトライ（ファイルロック解除待ち）
    - 新 exe 起動前に追加の待機（DLL 展開猶予）
    """
    import os
    current_exe = Path(sys.executable)
    current_pid = os.getpid()

    bat = (
        "@echo off\n"
        # 1. 旧プロセスが完全に終了するまで PID で確認しながら待つ
        ":wait_exit\n"
        f'tasklist /fi "PID eq {current_pid}" 2>nul | find /i "{current_pid}" >nul\n'
        "if not errorlevel 1 (\n"
        "  timeout /t 1 /nobreak >nul\n"
        "  goto wait_exit\n"
        ")\n"
        # 2. OS がファイルを完全に解放するまで追加で 3 秒待つ
        "timeout /t 3 /nobreak >nul\n"
        # 3. ファイル置換（失敗したら 1 秒後にリトライ）
        ":try_move\n"
        f'move /y "{new_exe_path}" "{current_exe}" >nul 2>&1\n'
        "if errorlevel 1 (\n"
        "  timeout /t 1 /nobreak >nul\n"
        "  goto try_move\n"
        ")\n"
        # 4. 新 exe 起動
        f'start "" "{current_exe}"\n'
        # 5. バッチ自己削除
        'del "%~f0"\n'
    )
    bat_path = current_exe.parent / "_update_apply.bat"
    bat_path.write_text(bat, encoding='cp932')

    subprocess.Popen(
        ['cmd', '/c', str(bat_path)],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
