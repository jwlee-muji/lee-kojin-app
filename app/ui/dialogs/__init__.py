"""도메인 특화 다이얼로그.

LeeDialog 베이스를 상속한 업무용 다이얼로그들을 모은 패키지.

서브패키지:
    update_dialogs : 자동 업데이트 흐름 4종
        - UpdateAvailableDialog : 신버전 안내 (Yes/No)
        - UpdateProgressDialog  : 다운로드 진행률
        - UpdateReadyDialog     : 다운로드 완료
        - DownloadErrorDialog   : 다운로드 실패 (재시도)
"""
from __future__ import annotations

from .update_dialogs import (
    UpdateAvailableDialog,
    UpdateProgressDialog,
    UpdateReadyDialog,
    DownloadErrorDialog,
)
from .quit_dialog import QuitConfirmDialog

__all__ = [
    "UpdateAvailableDialog",
    "UpdateProgressDialog",
    "UpdateReadyDialog",
    "DownloadErrorDialog",
    "QuitConfirmDialog",
    "dialogs_qss",
]


def dialogs_qss(tokens: dict) -> str:
    """도메인 다이얼로그들의 QSS 를 결합해 반환 (ThemeManager 가 호출)."""
    from . import update_dialogs
    return update_dialogs.qss(tokens)
