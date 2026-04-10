"""
自動アップデートモジュール
GitHub Releases API を使って新バージョンを確認し、
ダウンロードリンクをユーザーに案内する。
"""
import requests
from packaging.version import Version
from version import __version__

# ここにリポジトリを設定する (例: "lee-taro/energy-monitor")
GITHUB_REPO = "jwlee-muji/lee-kojin-app"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def check_for_update(timeout: int = 5):
    """
    最新リリースを確認する。
    新バージョンがあれば {"version": str, "url": str, "notes": str} を返す。
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
            # .exe アセットの URL を探す
            download_url = data.get("html_url", "")
            for asset in data.get("assets", []):
                if asset.get("name", "").endswith(".exe"):
                    download_url = asset["browser_download_url"]
                    break

            return {
                "version": latest_ver,
                "url": download_url,
                "notes": data.get("body", ""),
            }
    except Exception:
        pass
    return None
