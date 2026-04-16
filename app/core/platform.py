"""
Windows プラットフォーム固有のユーティリティ

- スタートアップ登録 / 解除 (レジストリ)
"""
import sys
import winreg
import logging

logger = logging.getLogger(__name__)

_AUTOSTART_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_NAME = "LEEPowerMonitor"


def set_autostart(enable: bool) -> None:
    """Windows スタートアップへの登録・解除を行う。
    フローズン環境 (PyInstaller EXE) 以外では何もしない。"""
    if not getattr(sys, "frozen", False):
        return

    exe_path = f'"{sys.executable}" --tray'
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_ALL_ACCESS
        ) as key:
            if enable:
                winreg.SetValueEx(key, _AUTOSTART_NAME, 0, winreg.REG_SZ, exe_path)
            else:
                try:
                    winreg.DeleteValue(key, _AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
    except OSError as e:
        logger.error(f"Auto-start registry update failed: {e}")
