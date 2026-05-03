"""Phase 1 베이스 컴포넌트.

Usage:
    from app.ui.components import LeeButton, LeeCard, LeeDialog, LeePill

    btn  = LeeButton("保存", variant="primary", size="md")
    card = LeeCard(accent_color="spot", interactive=True)
    pill = LeePill("NEW", variant="accent")

    if LeeDialog.confirm("削除確認", "本当に削除しますか?",
                          ok_text="削除", destructive=True, parent=self):
        self._do_delete()

QSS 적용은 ThemeManager.set_theme() 가 자동으로 components_qss(tokens) 를
호출하여 앱 전역 스타일시트에 합칩니다.
"""
from __future__ import annotations

from .button import LeeButton, ButtonVariant, ButtonSize
from .card import LeeCard, AccentColor
from .dialog import LeeDialog, DialogKind
from .pill import LeePill, PillVariant
from .topbar import LeeTopBar, TAB_KEYS
from .sidebar import LeeSidebar
from .segment import LeeSegment

# Phase 1 신규 atom 들
from .atoms import LeeIconTile, LeeSparkline, LeeTrend, LeeCountValue, LeeRingSpinner
from .detail import LeeKPI, LeeDetailHeader, LeeChartFrame
from .charts import LeeBigChart, LeePivotTable, LeeReserveBars, price_color, PivotMode
from .inputs import LeeDateInput
from .weather_illust import LeeWeatherIllust, WMO_CATEGORY, category_for_wmo

# Phase 6 폴리싱 컴포넌트
from .toast import LeeToast, ToastKind
from .skeleton import LeeSkeleton, SkeletonKind, install_skeleton_overlay
from .mini_calendar import LeeMiniCalendar, install_on_date_edits

__all__ = [
    # 기존
    "LeeButton",
    "LeeCard",
    "LeeDialog",
    "LeePill",
    "LeeTopBar",
    "LeeSidebar",
    "LeeSegment",
    "ButtonVariant",
    "ButtonSize",
    "AccentColor",
    "DialogKind",
    "PillVariant",
    "TAB_KEYS",
    # Phase 1 신규
    "LeeIconTile",
    "LeeSparkline",
    "LeeTrend",
    "LeeCountValue",
    "LeeRingSpinner",
    "LeeKPI",
    "LeeDetailHeader",
    "LeeChartFrame",
    "LeeBigChart",
    "LeePivotTable",
    "LeeReserveBars",
    "price_color",
    "PivotMode",
    "LeeDateInput",
    "LeeWeatherIllust",
    "WMO_CATEGORY",
    "category_for_wmo",
    # Phase 6 폴리싱
    "LeeToast",
    "ToastKind",
    "LeeSkeleton",
    "SkeletonKind",
    "install_skeleton_overlay",
    "LeeMiniCalendar",
    "install_on_date_edits",
    # 결합기
    "components_qss",
]


def components_qss(tokens: dict) -> str:
    """전체 컴포넌트 QSS를 토큰으로 .format() 하여 결합한 결과를 반환."""
    from . import button, card, dialog, pill, topbar, sidebar, atoms, segment
    return "\n".join([
        button.qss(tokens),
        card.qss(tokens),
        pill.qss(tokens),
        dialog.qss(tokens),
        topbar.qss(tokens),
        sidebar.qss(tokens),
        atoms.qss(tokens),
        segment.qss(tokens),
    ])
