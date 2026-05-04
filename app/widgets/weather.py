"""全国天気予報 ウィジェット — Phase 5.5 リニューアル.

데이터 소스: Open-Meteo (current + hourly + daily 통합 응답)

디자인 출처: handoff/LEE_PROJECT/varA-cards.jsx WeatherCard
            handoff/LEE_PROJECT/weather-illust.jsx (LeeWeatherIllust 로 추출됨)

모킹업 1:1:
    - WeatherCard (대시보드): LeeCard(accent="weather") + LeeWeatherIllust +
      도시명 + 현재 기온 + 体感温度 + 습도 + 풍속 (자동 사이클링)
    - WeatherWidget (디테일): 도시 segment + 큰 현재 날씨 카드 +
      24h 가로스크롤 + 7day 주간 카드

[기존 보존]
    - FetchWeatherWorker / FetchWeatherHistoryWorker
    - DB_WEATHER (weather_forecast) 스키마
    - settings.weather_interval (자동 갱신)
    - bus.weather_updated (WeatherSummaryEntry 리스트)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from app.api.market.weather import FetchWeatherWorker, FetchWeatherHistoryWorker
from app.core.config import WEATHER_REGIONS, BASE_DIR
from app.core.events import bus, WeatherSummaryEntry
from app.core.i18n import tr
from app.ui.common import BaseWidget
from app.ui.components import (
    LeeButton, LeeCard, LeeCountValue, LeeDetailHeader, LeeDialog,
    LeeIconTile, LeeKPI, LeeSegment, LeeWeatherIllust, category_for_wmo,
)


logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 토큰 / WMO 매핑
# ──────────────────────────────────────────────────────────────────────
_C_WEATHER = "#2EC4B6"
_C_OK   = "#30D158"
_C_WARN = "#FF9F0A"
_C_BAD  = "#FF453A"

# WMO 코드 → (텍스트, 강조색)
_WMO_TEXT: dict[int, tuple[str, str]] = {
    0:  ("晴れ",            "#FF9800"),
    1:  ("概ね晴れ",        "#FFB74D"),
    2:  ("一部曇り",        "#78909C"),
    3:  ("曇り",            "#607D8B"),
    45: ("霧",              "#9E9E9E"),
    48: ("霧氷",            "#9E9E9E"),
    51: ("弱い霧雨",        "#4FC3F7"),
    53: ("霧雨",            "#29B6F6"),
    55: ("強い霧雨",        "#039BE5"),
    56: ("弱い着氷性霧雨",  "#4DD0E1"),
    57: ("強い着氷性霧雨",  "#00BCD4"),
    61: ("弱い雨",          "#4FC3F7"),
    63: ("雨",              "#039BE5"),
    65: ("強い雨",          "#0277BD"),
    66: ("弱い着氷性の雨",  "#26C6DA"),
    67: ("強い着氷性の雨",  "#0097A7"),
    71: ("弱い雪",          "#90CAF9"),
    73: ("雪",              "#4FC3F7"),
    75: ("強い雪",          "#29B6F6"),
    77: ("霧雪",            "#90CAF9"),
    80: ("弱い小雨",        "#4FC3F7"),
    81: ("小雨",            "#039BE5"),
    82: ("激しい小雨",      "#0277BD"),
    85: ("弱い雪降る",      "#B3E5FC"),
    86: ("強い雪降る",      "#81D4FA"),
    95: ("雷雨",            "#F44336"),
    96: ("弱い雹の雷雨",   "#D32F2F"),
    99: ("強い雹の雷雨",   "#B71C1C"),
}


def get_weather_info(code: int) -> tuple[str, str]:
    """WMO 코드 → (번역된 텍스트, 강조색)."""
    txt, color = _WMO_TEXT.get(int(code), ("不明", "#757575"))
    return tr(txt), color


# ──────────────────────────────────────────────────────────────────────
# A. WeatherCard — 대시보드 카드
# ──────────────────────────────────────────────────────────────────────
class WeatherCard(LeeCard):
    """全国天気 카드 — 큰 일러스트 + 도시명 + 현재 기온 + 体感/습도/풍속.

    여러 도시를 자동 사이클링. 카드 클릭 → 디테일 페이지로 이동.
    """

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(accent_color="weather", interactive=True, parent=parent)
        self.setMinimumHeight(280)
        self._is_dark = True
        self._entries: list[WeatherSummaryEntry] = []
        self._idx = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(0)

        # 헤더
        header = QHBoxLayout(); header.setSpacing(12); header.setContentsMargins(0, 0, 0, 12)
        self._icon = LeeIconTile(
            icon=QIcon(":/img/weather.svg"),
            color=_C_WEATHER, size=40, radius=12,
        )
        header.addWidget(self._icon, 0, Qt.AlignTop)

        title_box = QVBoxLayout(); title_box.setSpacing(2); title_box.setContentsMargins(0, 0, 0, 0)
        self._title_lbl = QLabel(tr("全国天気"))
        self._title_lbl.setObjectName("weaCardTitle")
        self._sub_lbl = QLabel(tr("Open-Meteo · 10地域"))
        self._sub_lbl.setObjectName("weaCardSub")
        title_box.addWidget(self._title_lbl)
        title_box.addWidget(self._sub_lbl)
        header.addLayout(title_box, 1)

        layout.addLayout(header)

        # 큰 일러스트 (가운데 큰 영역)
        self._illust = LeeWeatherIllust(self)
        self._illust.setMinimumSize(160, 110)
        self._illust.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._illust.setFixedHeight(110)
        layout.addWidget(self._illust, 0, Qt.AlignCenter)

        # 도시명 (큰 글씨)
        self._region_lbl = QLabel("--")
        self._region_lbl.setObjectName("weaCardRegion")
        self._region_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._region_lbl)

        # 현재 기온 (큰 숫자)
        self._temp_lbl = LeeCountValue(formatter=lambda v: f"{v:.1f}")
        self._temp_lbl.setObjectName("weaCardTemp")
        self._temp_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._temp_lbl)

        # 날씨 텍스트
        self._weather_text_lbl = QLabel("")
        self._weather_text_lbl.setObjectName("weaCardWeatherText")
        self._weather_text_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._weather_text_lbl)

        # 보조 라인: 体感 / 湿度 / 風速
        sub_row = QHBoxLayout(); sub_row.setSpacing(10); sub_row.setContentsMargins(0, 8, 0, 0)
        self._feels_lbl = QLabel("--")
        self._humid_lbl = QLabel("--")
        self._wind_lbl  = QLabel("--")
        for lbl in (self._feels_lbl, self._humid_lbl, self._wind_lbl):
            lbl.setObjectName("weaCardStat")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setTextFormat(Qt.RichText)
            sub_row.addWidget(lbl, 1)
        layout.addLayout(sub_row)

        # 도시 페이저 (●○○...)
        self._pager_box = QWidget()
        # 부모 카드 배경 그대로 노출 (시스템 default 색 침투 차단)
        self._pager_box.setAttribute(Qt.WA_TranslucentBackground, True)
        self._pager_box.setStyleSheet("background: transparent;")
        pager_lay = QHBoxLayout(self._pager_box)
        pager_lay.setContentsMargins(0, 8, 0, 0); pager_lay.setSpacing(4)
        pager_lay.setAlignment(Qt.AlignCenter)
        self._pager_dots: list[QFrame] = []
        layout.addWidget(self._pager_box)

        layout.addStretch()

        # cycle timer (3초)
        self._cycle_timer = QTimer(self)
        self._cycle_timer.setInterval(3000)
        self._cycle_timer.timeout.connect(self._cycle)

        self._apply_local_qss()
        self.set_no_data()

    # ── 외부 API ─────────────────────────────────────────────
    def set_entries(self, entries: list[WeatherSummaryEntry]) -> None:
        self._entries = list(entries) if entries else []
        self._idx = 0
        self._rebuild_pager()
        self._render_current()

    def set_no_data(self) -> None:
        self._entries = []
        self._region_lbl.setText(tr("データなし"))
        self._temp_lbl.set_value(0.0, animate=False)
        self._temp_lbl.setText("--")
        self._weather_text_lbl.setText("")
        self._feels_lbl.setText(self._stat_html(tr("体感"), None))
        self._humid_lbl.setText(self._stat_html(tr("湿度"), None, suffix="%"))
        self._wind_lbl.setText(self._stat_html(tr("風速"), None, suffix=" km/h"))
        self._illust.set_category("clear", self._is_dark)
        self._rebuild_pager()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        if self._entries:
            entry = self._entries[self._idx % len(self._entries)]
            self._illust.set_category(category_for_wmo(entry.wmo_code), is_dark)
        self._apply_local_qss()
        self._rebuild_pager()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._cycle_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._cycle_timer.stop()

    # ── 내부 ─────────────────────────────────────────────────
    def _cycle(self):
        if not self._entries or len(self._entries) < 2:
            return
        if self.underMouse():
            return
        self._idx = (self._idx + 1) % len(self._entries)
        self._render_current()
        self._sync_pager_active()

    def _render_current(self):
        if not self._entries:
            self.set_no_data(); return
        entry = self._entries[self._idx % len(self._entries)]
        # 일러스트
        self._illust.set_category(category_for_wmo(entry.wmo_code), self._is_dark)
        # 도시 / 날씨 텍스트
        self._region_lbl.setText(entry.region)
        self._weather_text_lbl.setText(entry.weather_text)
        self._weather_text_lbl.setStyleSheet(
            f"color: {entry.accent_color}; font-size: 13px; font-weight: 700;"
            f"background: transparent; padding-bottom: 4px;"
        )
        # 현재 기온 — 우선 current_temp, 없으면 max
        cur = entry.current_temp if entry.current_temp is not None else entry.temp_max
        if cur is not None:
            self._temp_lbl.set_value(float(cur))
        else:
            self._temp_lbl.set_value(0.0, animate=False)
            self._temp_lbl.setText("--")
        # 보조 라인
        self._feels_lbl.setText(self._stat_html(tr("体感"), entry.apparent_temp, suffix="℃"))
        self._humid_lbl.setText(self._stat_html(tr("湿度"), entry.humidity, suffix="%"))
        self._wind_lbl.setText(self._stat_html(tr("風速"), entry.wind_speed, suffix=" km/h"))

    def _stat_html(self, label: str, val, *, suffix: str = "℃") -> str:
        v_txt = "--" if val is None else (f"{val:.1f}{suffix}" if isinstance(val, float) else f"{val}{suffix}")
        fg_secondary = "#A8B0BD" if self._is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if self._is_dark else "#8A93A6"
        return (
            f"<span style='font-size:9px; font-weight:700; color:{fg_tertiary};"
            f" letter-spacing:0.06em;'>{label}</span><br/>"
            f"<span style='font-family:\"JetBrains Mono\",monospace;"
            f" font-size:12px; font-weight:700; color:{fg_secondary};'>{v_txt}</span>"
        )

    def _rebuild_pager(self):
        # clear
        layout = self._pager_box.layout()
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None: w.setParent(None)
        self._pager_dots.clear()
        # 새 dots
        n = len(self._entries)
        if n <= 1:
            return
        for i in range(min(n, 12)):  # 최대 12개 표시
            dot = QFrame()
            dot.setObjectName("weaPagerDot")
            dot.setFixedSize(6, 6)
            dot.setProperty("active", i == self._idx)
            layout.addWidget(dot)
            self._pager_dots.append(dot)
        self._sync_pager_active()

    def _sync_pager_active(self):
        for i, dot in enumerate(self._pager_dots):
            active = (i == self._idx % len(self._pager_dots))
            dot.setProperty("active", active)
            dot.style().unpolish(dot); dot.style().polish(dot)

    def _apply_local_qss(self):
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        self.setStyleSheet(f"""
            QLabel#weaCardTitle {{
                font-size: 13px; font-weight: 600;
                color: {fg_secondary}; background: transparent;
            }}
            QLabel#weaCardSub {{
                font-size: 11px; color: {fg_tertiary};
                background: transparent;
            }}
            QLabel#weaCardRegion {{
                font-size: 16px; font-weight: 700;
                color: {fg_primary}; background: transparent;
                letter-spacing: -0.01em;
            }}
            QLabel#weaCardTemp {{
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 38px; font-weight: 800;
                color: {_C_WEATHER}; background: transparent;
                letter-spacing: -0.03em;
            }}
            QLabel#weaCardWeatherText {{
                background: transparent;
            }}
            QLabel#weaCardStat {{ background: transparent; }}
            QFrame#weaPagerDot {{
                background: rgba(255,255,255,0.12) if 0 else;
            }}
            QFrame#weaPagerDot[active="false"] {{
                background: rgba(255,255,255,{0.18 if is_dark else 0.16});
                border-radius: 3px;
            }}
            QFrame#weaPagerDot[active="true"] {{
                background: {_C_WEATHER};
                border-radius: 3px;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# B. _HourCard / _DayCard — 디테일 페이지의 24h / 7day 항목
# ──────────────────────────────────────────────────────────────────────
class _HourCard(QFrame):
    """24h 가로 스크롤의 1시간 단위 카드."""

    def __init__(self, hour: str, temp: float, code: int, pop: int, *, is_dark: bool):
        super().__init__()
        self.setObjectName("weaHourCard")
        self.setFixedSize(76, 132)
        self._is_dark = is_dark

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 10); layout.setSpacing(4)

        hour_lbl = QLabel(hour)
        hour_lbl.setObjectName("weaHourLabel")
        hour_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(hour_lbl)

        illust = LeeWeatherIllust(self)
        illust.setFixedSize(48, 36)
        illust.set_category(category_for_wmo(code), is_dark)
        layout.addWidget(illust, 0, Qt.AlignCenter)

        temp_lbl = QLabel(f"{temp:.1f}℃" if temp is not None else "--")
        temp_lbl.setObjectName("weaHourTemp")
        temp_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(temp_lbl)

        if pop is not None and pop > 0:
            pop_lbl = QLabel(f"☔ {pop}%")
            pop_lbl.setObjectName("weaHourPop")
            pop_lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(pop_lbl)

        self._apply_qss()

    def _apply_qss(self):
        is_dark = self._is_dark
        # 미니 시간 카드 — 페이지(bg_app) 위에 직접 놓이므로 bg_surface (1단계 surface)
        # 사용. 이전엔 bg_surface_2 (#1B1E26) 가 페이지(#0A0B0F) 와 색차가 커
        # "떠 있는" 인상.
        bg_surface   = "#14161C" if is_dark else "#FFFFFF"
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        border_subtle = "rgba(255,255,255,0.04)" if is_dark else "rgba(11,18,32,0.06)"
        self.setStyleSheet(f"""
            QFrame#weaHourCard {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 12px;
            }}
            QLabel#weaHourLabel {{
                font-size: 11px; font-weight: 700;
                color: {fg_tertiary}; background: transparent;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QLabel#weaHourTemp {{
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 13px; font-weight: 700;
                color: {fg_primary}; background: transparent;
            }}
            QLabel#weaHourPop {{
                font-size: 9px; color: #4FC3F7;
                background: transparent;
            }}
        """)


class _DayCard(QFrame):
    """7일 주간 카드 — date / illust / max-min / pop."""

    def __init__(self, date_str: str, code: int, t_max: float, t_min: float,
                 pop: int, *, is_dark: bool):
        super().__init__()
        self.setObjectName("weaDayCard")
        self.setMinimumWidth(150)
        self.setFixedHeight(160)
        self._is_dark = is_dark

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12); layout.setSpacing(4)

        # 요일 라벨 (ISO date → "月" 같은 요일)
        weekday = self._weekday_jp(date_str)
        head = QLabel(weekday); head.setObjectName("weaDayHead"); head.setAlignment(Qt.AlignCenter)
        layout.addWidget(head)

        sub = QLabel(date_str[5:] if len(date_str) >= 10 else date_str)  # MM-DD
        sub.setObjectName("weaDaySub"); sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)

        illust = LeeWeatherIllust(self)
        illust.setFixedSize(64, 48)
        illust.set_category(category_for_wmo(code), is_dark)
        layout.addWidget(illust, 0, Qt.AlignCenter)

        # 최고/최저
        c_max = "#ff8a80" if is_dark else "#d32f2f"
        c_min = "#82b1ff" if is_dark else "#1976d2"
        temp_lbl = QLabel(
            f"<span style='color:{c_max}; font-weight:700;'>{t_max:.0f}°</span>"
            f"&nbsp;<span style='color:{fg_color_for(is_dark)}; opacity:0.5;'>/</span>&nbsp;"
            f"<span style='color:{c_min}; font-weight:700;'>{t_min:.0f}°</span>"
        )
        temp_lbl.setObjectName("weaDayTemp"); temp_lbl.setAlignment(Qt.AlignCenter)
        temp_lbl.setTextFormat(Qt.RichText)
        layout.addWidget(temp_lbl)

        # 강수확률
        if pop is not None:
            pop_lbl = QLabel(f"☔ {pop}%")
            pop_lbl.setObjectName("weaDayPop"); pop_lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(pop_lbl)

        self._apply_qss()

    @staticmethod
    def _weekday_jp(date_str: str) -> str:
        try:
            d = datetime.strptime(date_str[:10], "%Y-%m-%d")
            return "月火水木金土日"[d.weekday()]
        except Exception:
            return ""

    def _apply_qss(self):
        is_dark = self._is_dark
        # 미니 일자 카드 — 페이지(bg_app) 위에 직접 놓이므로 bg_surface (1단계 surface)
        bg_surface   = "#14161C" if is_dark else "#FFFFFF"
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        border_subtle = "rgba(255,255,255,0.04)" if is_dark else "rgba(11,18,32,0.06)"
        self.setStyleSheet(f"""
            QFrame#weaDayCard {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 14px;
            }}
            QLabel#weaDayHead {{
                font-size: 14px; font-weight: 800;
                color: {fg_primary}; background: transparent;
            }}
            QLabel#weaDaySub {{
                font-size: 11px; color: {fg_tertiary};
                background: transparent;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QLabel#weaDayTemp {{ background: transparent; font-size: 12px; }}
            QLabel#weaDayPop {{
                font-size: 10px; color: #4FC3F7;
                background: transparent;
            }}
        """)


def fg_color_for(is_dark: bool) -> str:
    return "#A8B0BD" if is_dark else "#4A5567"


# ──────────────────────────────────────────────────────────────────────
# C. WeatherWidget — 디테일 페이지 (도시 segment + 큰 카드 + 24h + 7day)
# ──────────────────────────────────────────────────────────────────────
class WeatherWidget(BaseWidget):
    """全国天気 디테일 — 도시 selector + 현재 카드 + 24h 가로스크롤 + 7day."""

    def __init__(self):
        super().__init__()
        self.weather_data: list = []
        self._region_idx = 2  # 기본: 東京 (index 2)
        self.worker: Optional[FetchWeatherWorker] = None
        self._history_worker: Optional[FetchWeatherHistoryWorker] = None

        self._build_ui()

        QTimer.singleShot(2250, self.fetch_weather)
        self.setup_timer(self.settings.get("weather_interval", 60), self.fetch_weather)
        QTimer.singleShot(8000, self._auto_fetch_history)

    def apply_settings_custom(self):
        self.update_timer_interval(self.settings.get("weather_interval", 60))
        self._update_refresh_indicator()

    # ──────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setObjectName("weaPageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer.addWidget(scroll, 1)

        content = QWidget()
        content.setObjectName("weaPageContent")
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(16)

        # 1) DetailHeader
        self._header = LeeDetailHeader(
            title=tr("全国天気予報"),
            subtitle=tr("Open-Meteo · 10地域 · 現在 + 24時間 + 7日間"),
            accent=_C_WEATHER,
            icon_qicon=QIcon(":/img/weather.svg"),
            badge="",
            show_export=False,
        )
        self._header.back_clicked.connect(lambda: bus.page_requested.emit(0))
        root.addWidget(self._header)

        # 2) 도시 segment (모든 region 옵션)
        root.addWidget(self._build_filter_row())

        # 3-5) 데이터 영역 (현재 + 시간별 + 주간) — 첫 fetch skeleton 대상
        self._data_wrap = QFrame()
        self._data_wrap.setObjectName("weaDataWrap")
        dw = QVBoxLayout(self._data_wrap)
        dw.setContentsMargins(0, 0, 0, 0); dw.setSpacing(10)
        dw.addWidget(self._build_current_card())
        dw.addWidget(self._build_hourly_section())
        dw.addWidget(self._build_weekly_section())
        root.addWidget(self._data_wrap)

        # 첫 fetch skeleton overlay
        from app.ui.components.skeleton import install_skeleton_overlay
        self._data_skel = install_skeleton_overlay(self._data_wrap)

        # 6) 진행 인디케이터
        bottom = QHBoxLayout(); bottom.setContentsMargins(0, 0, 0, 0); bottom.setSpacing(10)
        self._refresh_indicator = QLabel("")
        self._refresh_indicator.setObjectName("weaRefreshIndicator")
        bottom.addWidget(self._refresh_indicator)
        self._status = QLabel(tr("待機中"))
        self._status.setObjectName("weaStatusLbl")
        self._status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bottom.addStretch()
        bottom.addWidget(self._status)
        root.addLayout(bottom)

        self._update_refresh_indicator()

    def _build_filter_row(self) -> QWidget:
        bar = QFrame(); bar.setObjectName("weaFilterBar")
        h = QHBoxLayout(bar); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(10)

        # 도시 segment — 10 region 다 표시 (가로 스크롤 안 됨, 한 줄)
        # 너무 많으니 short label + segmented (4 안에 표시)
        # 디자인 단순화: dropdown (ComboBox)
        from PySide6.QtWidgets import QComboBox
        self._city_combo = QComboBox()
        self._city_combo.setObjectName("weaCityCombo")
        self._city_combo.setFixedHeight(34)
        self._city_combo.setMinimumWidth(220)
        for region in WEATHER_REGIONS:
            self._city_combo.addItem(tr(region["name"]))
        self._city_combo.setCurrentIndex(self._region_idx)
        self._city_combo.currentIndexChanged.connect(self._on_region_changed)
        h.addWidget(self._city_combo)

        h.addStretch()

        self._btn_refresh = LeeButton(tr("更新"), variant="secondary", size="sm")
        self._btn_refresh.clicked.connect(self.fetch_weather)
        h.addWidget(self._btn_refresh)

        self._btn_history = LeeButton(tr("過去データ"), variant="ghost", size="sm")
        self._btn_history.clicked.connect(self.fetch_history)
        h.addWidget(self._btn_history)

        self._filter_bar = bar
        self._apply_filter_qss()
        return bar

    def _build_current_card(self) -> QWidget:
        card = LeeCard(accent_color="weather", interactive=False)
        card.setMinimumHeight(220)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(28, 20, 28, 20); layout.setSpacing(28)

        # 좌: 큰 일러스트
        self._cur_illust = LeeWeatherIllust(self)
        self._cur_illust.setFixedSize(180, 140)
        self._cur_illust.set_category("clear", self.is_dark)
        layout.addWidget(self._cur_illust, 0, Qt.AlignCenter)

        # 우: 도시 + 큰 기온 + 보조
        info = QVBoxLayout(); info.setSpacing(2)

        self._cur_region = QLabel("--")
        self._cur_region.setObjectName("weaCurRegion")
        info.addWidget(self._cur_region)

        self._cur_weather_text = QLabel("")
        self._cur_weather_text.setObjectName("weaCurText")
        info.addWidget(self._cur_weather_text)

        # 큰 기온
        temp_row = QHBoxLayout(); temp_row.setSpacing(6); temp_row.setAlignment(Qt.AlignBaseline)
        self._cur_temp = LeeCountValue(formatter=lambda v: f"{v:.1f}")
        self._cur_temp.setObjectName("weaCurTemp")
        unit = QLabel("℃"); unit.setObjectName("weaCurUnit")
        temp_row.addWidget(self._cur_temp, 0, Qt.AlignBaseline)
        temp_row.addWidget(unit, 0, Qt.AlignBaseline)
        temp_row.addStretch()
        info.addLayout(temp_row)

        # 보조 KPI 미니
        sub = QHBoxLayout(); sub.setContentsMargins(0, 8, 0, 0); sub.setSpacing(20)
        self._cur_feels = self._mini_stat(tr("体感"), "--")
        self._cur_humid = self._mini_stat(tr("湿度"), "--")
        self._cur_wind  = self._mini_stat(tr("風速"), "--")
        self._cur_max   = self._mini_stat(tr("最高"), "--")
        self._cur_min   = self._mini_stat(tr("最低"), "--")
        for w in (self._cur_feels, self._cur_humid, self._cur_wind, self._cur_max, self._cur_min):
            sub.addWidget(w)
        sub.addStretch()
        info.addLayout(sub)

        layout.addLayout(info, 1)

        self._current_card = card
        self._apply_current_card_qss()
        return card

    def _mini_stat(self, label: str, value: str) -> QWidget:
        wrap = QWidget()
        # 부모 카드 배경을 그대로 노출 (wrap 자체는 색 안 가짐)
        wrap.setAttribute(Qt.WA_TranslucentBackground)
        wrap.setStyleSheet("background: transparent;")
        v = QVBoxLayout(wrap); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(2)
        head = QLabel(label); head.setObjectName("weaMiniHead")
        val  = QLabel(value); val.setObjectName("weaMiniVal")
        v.addWidget(head); v.addWidget(val)
        # value 라벨에 접근 가능하도록 객체에 보관
        wrap._head_lbl = head; wrap._val_lbl = val  # type: ignore[attr-defined]
        return wrap

    def _build_hourly_section(self) -> QWidget:
        wrap = QFrame(); wrap.setObjectName("weaHourlyWrap")
        v = QVBoxLayout(wrap); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(8)
        title = QLabel(tr("時間別予報 (24時間)"))
        title.setObjectName("weaSectionTitle")
        v.addWidget(title)

        self._hourly_scroll = QScrollArea()
        self._hourly_scroll.setObjectName("weaHourlyScroll")
        self._hourly_scroll.setWidgetResizable(True)
        self._hourly_scroll.setFrameShape(QFrame.NoFrame)
        self._hourly_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._hourly_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._hourly_scroll.setFixedHeight(160)

        inner = QWidget()
        self._hourly_layout = QHBoxLayout(inner)
        self._hourly_layout.setContentsMargins(0, 0, 0, 0); self._hourly_layout.setSpacing(8)
        self._hourly_layout.addStretch()
        self._hourly_scroll.setWidget(inner)
        v.addWidget(self._hourly_scroll)
        return wrap

    def _build_weekly_section(self) -> QWidget:
        wrap = QFrame(); wrap.setObjectName("weaWeeklyWrap")
        v = QVBoxLayout(wrap); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(8)
        title = QLabel(tr("週間予報 (7日間)"))
        title.setObjectName("weaSectionTitle")
        v.addWidget(title)

        self._weekly_box = QWidget()
        self._weekly_layout = QHBoxLayout(self._weekly_box)
        self._weekly_layout.setContentsMargins(0, 0, 0, 0); self._weekly_layout.setSpacing(10)
        v.addWidget(self._weekly_box)
        return wrap

    def _update_refresh_indicator(self) -> None:
        if not hasattr(self, "_refresh_indicator"):
            return
        interval = int(self.settings.get("weather_interval", 60))
        self._refresh_indicator.setText(f"●  {interval}{tr('分ごと')}")

    # ──────────────────────────────────────────────────────────
    # 스타일
    # ──────────────────────────────────────────────────────────
    def _apply_page_qss(self) -> None:
        bg_app = "#0A0B0F" if self.is_dark else "#F5F6F8"
        self.setStyleSheet(f"""
            WeatherWidget {{ background: {bg_app}; }}
            QScrollArea#weaPageScroll {{ background: {bg_app}; border: none; }}
            QWidget#weaPageContent {{ background: {bg_app}; }}
            QScrollArea#weaHourlyScroll {{ background: transparent; border: none; }}
            QFrame#weaHourlyWrap, QFrame#weaWeeklyWrap {{ background: transparent; }}
            QLabel#weaSectionTitle {{
                font-size: 13px; font-weight: 700;
                color: {'#A8B0BD' if self.is_dark else '#4A5567'};
                background: transparent;
            }}
        """)

    def _apply_filter_qss(self) -> None:
        is_dark = self.is_dark
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        bg_input     = "#1B1E26" if is_dark else "#FFFFFF"
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        border       = "rgba(255,255,255,0.08)" if is_dark else "rgba(11,18,32,0.10)"
        self._filter_bar.setStyleSheet(f"""
            QFrame#weaFilterBar {{ background: transparent; }}
            QComboBox#weaCityCombo {{
                background: {bg_input};
                color: {fg_primary};
                border: 1px solid {border};
                border-radius: 10px;
                padding: 0 12px;
                font-size: 13px; font-weight: 600;
            }}
            QComboBox#weaCityCombo::drop-down {{ border: none; width: 22px; }}
            QLabel#weaRefreshIndicator {{
                font-size: 11px; font-weight: 600;
                color: {_C_OK};
                background: rgba(48,209,88,0.10);
                border: 1px solid rgba(48,209,88,0.25);
                border-radius: 999px;
                padding: 3px 10px;
            }}
            QLabel#weaStatusLbl {{
                font-size: 11px; color: {fg_secondary};
                background: transparent;
            }}
        """)

    def _apply_current_card_qss(self) -> None:
        is_dark = self.is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        self._current_card.setStyleSheet(f"""
            QLabel#weaCurRegion {{
                font-size: 22px; font-weight: 800;
                color: {fg_primary}; background: transparent;
                letter-spacing: -0.02em;
            }}
            QLabel#weaCurText {{
                font-size: 14px; font-weight: 700;
                color: {_C_WEATHER}; background: transparent;
                padding-bottom: 6px;
            }}
            QLabel#weaCurTemp {{
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 64px; font-weight: 800;
                color: {fg_primary}; background: transparent;
                letter-spacing: -0.04em;
            }}
            QLabel#weaCurUnit {{
                font-size: 24px; font-weight: 700;
                color: {fg_tertiary}; background: transparent;
                padding-bottom: 14px;
            }}
            QLabel#weaMiniHead {{
                font-size: 9px; font-weight: 700;
                color: {fg_tertiary}; background: transparent;
                letter-spacing: 0.06em;
            }}
            QLabel#weaMiniVal {{
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 13px; font-weight: 700;
                color: {fg_secondary}; background: transparent;
            }}
        """)

    # ──────────────────────────────────────────────────────────
    # BaseWidget hooks
    # ──────────────────────────────────────────────────────────
    def apply_theme_custom(self) -> None:
        d = self.is_dark
        self._header.set_theme(d)
        self._cur_illust.set_category(self._cur_illust.category(), d)
        self._apply_page_qss()
        self._apply_filter_qss()
        self._apply_current_card_qss()
        # 행 카드들 재구축 (스타일 갱신)
        if self.weather_data:
            self._render_region(self._region_idx)

    # ──────────────────────────────────────────────────────────
    # 컨트롤
    # ──────────────────────────────────────────────────────────
    def _on_region_changed(self, idx: int) -> None:
        self._region_idx = idx
        self._render_region(idx)

    # ──────────────────────────────────────────────────────────
    # 데이터 fetch
    # ──────────────────────────────────────────────────────────
    def fetch_weather(self) -> None:
        if not self.check_online_status(): return
        try:
            if self.worker and self.worker.isRunning():
                return
        except RuntimeError:
            self.worker = None
        self._btn_refresh.setEnabled(False)
        self._set_status(tr("天気データ取得中..."))
        if getattr(self, "_data_skel", None) is not None:
            self._data_skel.start()
        self.worker = FetchWeatherWorker()
        self.worker.finished.connect(self._on_fetch_success)
        self.worker.error.connect(self._on_fetch_error)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()
        self.track_worker(self.worker)

    def _on_fetch_success(self, data_list: list) -> None:
        self._btn_refresh.setEnabled(True)
        self.weather_data = data_list
        self._set_status(tr("取得完了"))
        # 현재 선택된 지역 렌더
        self._render_region(self._region_idx)
        # 대시보드 카드용 summary 송신
        self._emit_weather_summary(data_list)
        # DB 저장
        self._save_to_db(data_list)

    def _on_fetch_error(self, err_msg: str) -> None:
        self._btn_refresh.setEnabled(True)
        self._set_status(tr("取得失敗: {0}").format(err_msg))
        bus.toast_requested.emit(tr("⚠ 天気 取得失敗"), "error")

    def _emit_weather_summary(self, data_list: list) -> None:
        weather_summary: list[WeatherSummaryEntry] = []
        for i, region in enumerate(WEATHER_REGIONS):
            if i >= len(data_list): break
            data = data_list[i]
            daily = data.get("daily") or {}
            current = data.get("current") or {}
            if not daily and not current:
                continue
            w_code = (daily.get("weather_code") or [0])[0] if daily.get("weather_code") else current.get("weather_code", 0)
            t_max  = (daily.get("temperature_2m_max") or [None])[0] if daily.get("temperature_2m_max") else None
            t_min  = (daily.get("temperature_2m_min") or [None])[0] if daily.get("temperature_2m_min") else None
            w_text, w_color = get_weather_info(w_code)
            t_max_str = f"{t_max}℃" if t_max is not None else "—"
            t_min_str = f"{t_min}℃" if t_min is not None else "—"
            weather_summary.append(WeatherSummaryEntry(
                region=tr(region["name"]),
                weather_text=w_text,
                temp_str=f"{t_max_str} / {t_min_str}",
                accent_color=w_color,
                wmo_code=w_code,
                current_temp=current.get("temperature_2m"),
                apparent_temp=current.get("apparent_temperature"),
                humidity=current.get("relative_humidity_2m"),
                wind_speed=current.get("wind_speed_10m"),
                temp_max=t_max,
                temp_min=t_min,
            ))
        if weather_summary:
            bus.weather_updated.emit(weather_summary)

    # ──────────────────────────────────────────────────────────
    # 렌더링
    # ──────────────────────────────────────────────────────────
    def _render_region(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.weather_data):
            return
        # 데이터 도착 시 skeleton 숨기기 (재사용 가능 — refresh 시 다시 .start())
        if getattr(self, "_data_skel", None) is not None:
            self._data_skel.stop()
        region = WEATHER_REGIONS[idx]
        data   = self.weather_data[idx]
        current = data.get("current") or {}
        daily   = data.get("daily")   or {}
        hourly  = data.get("hourly")  or {}

        # 현재 카드
        w_code = current.get("weather_code", (daily.get("weather_code") or [0])[0] if daily.get("weather_code") else 0)
        w_text, w_color = get_weather_info(w_code)
        self._cur_illust.set_category(category_for_wmo(w_code), self.is_dark)
        self._cur_region.setText(tr(region["name"]))
        self._cur_weather_text.setText(w_text)
        self._cur_weather_text.setStyleSheet(
            f"color: {w_color}; font-size: 14px; font-weight: 700;"
            f"background: transparent; padding-bottom: 6px;"
        )
        cur_t = current.get("temperature_2m")
        if cur_t is not None:
            self._cur_temp.set_value(float(cur_t))
        else:
            self._cur_temp.set_value(0.0, animate=False)
            self._cur_temp.setText("--")

        # 미니 stats
        self._set_mini(self._cur_feels, _fmt_temp(current.get("apparent_temperature")))
        self._set_mini(self._cur_humid, _fmt_pct(current.get("relative_humidity_2m")))
        self._set_mini(self._cur_wind,  _fmt_wind(current.get("wind_speed_10m")))
        self._set_mini(self._cur_max,   _fmt_temp((daily.get("temperature_2m_max") or [None])[0] if daily.get("temperature_2m_max") else None))
        self._set_mini(self._cur_min,   _fmt_temp((daily.get("temperature_2m_min") or [None])[0] if daily.get("temperature_2m_min") else None))

        # 24h 가로 스크롤
        self._render_hourly(hourly)

        # 7day
        self._render_weekly(daily)

        # Header badge
        if cur_t is not None:
            self._header.set_badge(f"{tr(region['name'])} {cur_t:.1f}℃")
        else:
            self._header.set_badge(None)

    def _set_mini(self, mini_widget: QWidget, value: str) -> None:
        lbl = getattr(mini_widget, "_val_lbl", None)
        if lbl is not None:
            lbl.setText(value)

    def _render_hourly(self, hourly: dict) -> None:
        # clear existing
        while self._hourly_layout.count() > 0:
            item = self._hourly_layout.takeAt(0)
            w = item.widget()
            if w is not None: w.setParent(None)

        times = hourly.get("time") or []
        temps = hourly.get("temperature_2m") or []
        codes = hourly.get("weather_code") or []
        pops  = hourly.get("precipitation_probability") or []
        if not times:
            self._hourly_layout.addStretch()
            return

        for i, t in enumerate(times[:24]):
            # ISO time → "HH:00"
            try:
                dt = datetime.fromisoformat(t)
                hour_label = dt.strftime("%H:%M")
            except Exception:
                hour_label = str(t)[-5:]
            temp = temps[i] if i < len(temps) else None
            code = codes[i] if i < len(codes) else 0
            pop  = pops[i]  if i < len(pops)  else None
            card = _HourCard(hour_label, temp, code, pop, is_dark=self.is_dark)
            self._hourly_layout.addWidget(card)
        self._hourly_layout.addStretch()

    def _render_weekly(self, daily: dict) -> None:
        # clear
        while self._weekly_layout.count() > 0:
            item = self._weekly_layout.takeAt(0)
            w = item.widget()
            if w is not None: w.setParent(None)

        dates  = daily.get("time") or []
        codes  = daily.get("weather_code") or []
        t_maxs = daily.get("temperature_2m_max") or []
        t_mins = daily.get("temperature_2m_min") or []
        pops   = daily.get("precipitation_probability_max") or []

        for i, d in enumerate(dates[:7]):
            code  = codes[i]  if i < len(codes)  else 0
            t_mx  = t_maxs[i] if i < len(t_maxs) else 0.0
            t_mn  = t_mins[i] if i < len(t_mins) else 0.0
            pop   = pops[i]   if i < len(pops)   else None
            card  = _DayCard(str(d), code, t_mx, t_mn, pop, is_dark=self.is_dark)
            self._weekly_layout.addWidget(card)
        self._weekly_layout.addStretch()

    # ──────────────────────────────────────────────────────────
    # DB 저장 (기존 보존)
    # ──────────────────────────────────────────────────────────
    def _save_to_db(self, data_list: list):
        from datetime import date as _date
        fetched_date = _date.today().strftime("%Y-%m-%d")
        try:
            from app.core.config import DB_WEATHER
            from app.core.database import get_db_connection
            records = []
            for i, region_info in enumerate(WEATHER_REGIONS):
                if i >= len(data_list): break
                daily = data_list[i].get("daily") or {}
                if not daily: continue
                region_name = region_info["name"]
                dates  = daily.get("time", [])
                w_codes = daily.get("weather_code", [])
                t_maxs  = daily.get("temperature_2m_max", [])
                t_mins  = daily.get("temperature_2m_min", [])
                pops    = daily.get("precipitation_probability_max", [])
                p_sums  = daily.get("precipitation_sum", [])
                clouds  = daily.get("cloud_cover_mean", [])
                winds   = daily.get("wind_speed_10m_max", [])
                for j, d in enumerate(dates):
                    records.append((
                        fetched_date, region_name, d,
                        w_codes[j] if j < len(w_codes) else None,
                        t_maxs[j]  if j < len(t_maxs)  else None,
                        t_mins[j]  if j < len(t_mins)  else None,
                        int(pops[j]) if j < len(pops) and pops[j] is not None else None,
                        p_sums[j]  if j < len(p_sums)  else None,
                        int(clouds[j]) if j < len(clouds) and clouds[j] is not None else None,
                        winds[j]   if j < len(winds)   else None,
                    ))
            with get_db_connection(DB_WEATHER) as conn:
                conn.execute(_CREATE_WEATHER)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_wf_date_region "
                    "ON weather_forecast(date, region)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_wf_fetched "
                    "ON weather_forecast(fetched_date)"
                )
                conn.executemany(
                    "INSERT OR REPLACE INTO weather_forecast "
                    "(fetched_date, region, date, weather_code, temp_max, temp_min, "
                    "precip_prob, precip_sum, cloud_cover, wind_speed) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    records,
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"天気DB保存エラー: {e}")

    def _auto_fetch_history(self):
        try:
            from app.core.config import DB_WEATHER
            from app.core.database import get_db_connection
            if not DB_WEATHER.exists():
                self.fetch_history(); return
            with get_db_connection(DB_WEATHER) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM weather_forecast WHERE fetched_date = date"
                ).fetchone()[0]
            if count < 100:
                self.fetch_history()
        except Exception as e:
            logger.debug(f"天気履歴自動取得チェックエラー: {e}")

    def fetch_history(self):
        if not self.check_online_status(): return
        try:
            if self._history_worker and self._history_worker.isRunning():
                return
        except RuntimeError:
            self._history_worker = None
        self._btn_history.setEnabled(False)
        self._set_status(tr("過去データ確認中..."))
        self._history_worker = FetchWeatherHistoryWorker()
        self._history_worker.finished.connect(self._on_history_success)
        self._history_worker.error.connect(self._on_history_error)
        self._history_worker.progress.connect(self._on_history_progress)
        self._history_worker.finished.connect(self._history_worker.deleteLater)
        self._history_worker.start()
        self.track_worker(self._history_worker)

    def _on_history_progress(self, msg: str):
        self._set_status(msg)

    def _on_history_success(self, msg: str):
        self._btn_history.setEnabled(True)
        self._set_status(msg)

    def _on_history_error(self, err_msg: str):
        self._btn_history.setEnabled(True)
        self._set_status(tr("過去データ取得失敗"))
        LeeDialog.error(tr("エラー"), err_msg, parent=self)

    def _set_status(self, msg: str) -> None:
        self._status.setText(msg)


# ──────────────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────────────
def _fmt_temp(val) -> str:
    if val is None: return "--"
    try:    return f"{float(val):.1f}℃"
    except: return "--"


def _fmt_pct(val) -> str:
    if val is None: return "--"
    try:    return f"{int(val)}%"
    except: return "--"


def _fmt_wind(val) -> str:
    if val is None: return "--"
    try:    return f"{float(val):.1f} km/h"
    except: return "--"


# DB 스키마 (호환)
_CREATE_WEATHER = """
    CREATE TABLE IF NOT EXISTS weather_forecast (
        fetched_date TEXT NOT NULL,
        region       TEXT NOT NULL,
        date         TEXT NOT NULL,
        weather_code INTEGER,
        temp_max     REAL,
        temp_min     REAL,
        precip_prob  INTEGER,
        precip_sum   REAL,
        cloud_cover  INTEGER,
        wind_speed   REAL,
        PRIMARY KEY (fetched_date, region, date)
    )
"""


# ──────────────────────────────────────────────────────────────────────
# Backward-compat: 기존 import 사용처 보존
# ──────────────────────────────────────────────────────────────────────
def get_weather_pixmap(wmo_code: int, size: int = 28):
    """기존 import 호환용 — SVG 미사용 위젯 마이그레이션 후 점진 제거 예정."""
    from PySide6.QtGui import QPixmap
    from app.core.config import BASE_DIR as _B
    icon_name = {
        0: "sunny", 1: "mostly_sunny", 2: "partly_cloudy", 3: "cloudy",
        45: "fog", 48: "fog", 51: "drizzle", 53: "drizzle", 55: "drizzle",
        61: "light_rain", 63: "rain", 65: "rain",
        71: "light_snow", 73: "snow", 75: "snow",
        80: "rain_shower", 81: "rain_shower", 82: "rain_shower",
        85: "snow_shower", 86: "snow_shower",
        95: "thunderstorm", 96: "thunderstorm_hail", 99: "thunderstorm_hail",
    }.get(int(wmo_code), "cloudy")
    pix = QPixmap(f":/img/weather/{icon_name}.svg")
    if pix.isNull():
        svg = _B / "img" / "weather" / f"{icon_name}.svg"
        if svg.exists():
            pix = QPixmap(str(svg))
    if not pix.isNull():
        pix = pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return pix
