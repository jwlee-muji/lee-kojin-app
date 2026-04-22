import logging
from PySide6.QtWidgets import QVBoxLayout, QLabel, QGridLayout
from PySide6.QtCore import QTimer, QThread, Signal
from app.ui.common import BaseWidget
from app.ui.theme import UIColors
from app.core.events import bus
from app.core.i18n import tr
from app.widgets.dashboard_cards import (
    SummaryCard, SpotDashCard,
    _WMO_CATEGORY, _WMO_BG_DARK, _WMO_BG_LIGHT,
    _high_alert_color, _low_alert_color,
)
from app.widgets.dashboard_service import DashboardDataService

logger = logging.getLogger(__name__)


class DashboardWidget(BaseWidget):
    request_fetch = Signal(str)

    def __init__(self):
        super().__init__()
        self._weather_list: list = []
        self._weather_index: int = 0
        self._spot_today: list[tuple] = []
        self._spot_tomorrow: list[tuple] = []
        self._spot_index: int = 0

        # 영구 백그라운드 DB 쿼리 서비스 설정
        self._service_thread = QThread()
        self._service = DashboardDataService()
        self._service.moveToThread(self._service_thread)
        self.request_fetch.connect(self._service.fetch_data)
        self._service_thread.finished.connect(self._service.deleteLater)
        self.track_worker(self._service_thread)   # app_quitting 시 자동 정리

        self._service.imb_result.connect(self._on_imb_result)
        self._service.imb_empty.connect(self._on_imb_empty)
        self._service.jkm_result.connect(self._on_jkm_result)
        self._service.jkm_empty.connect(self._on_jkm_empty)
        self._service.hjks_result.connect(self._on_hjks_result)
        self._service.hjks_empty.connect(self._on_hjks_empty)
        self._service.spot_today_result.connect(self._on_spot_today_result)
        self._service.spot_tomorrow_result.connect(self._on_spot_tomorrow_result)

        self._service_thread.start()

        self._build_ui()

        # Event Bus 구독 (Sub)
        bus.occto_updated.connect(self.update_occto)
        bus.imbalance_updated.connect(self.refresh_imbalance)
        bus.jkm_updated.connect(self.refresh_jkm)
        bus.hjks_updated.connect(self.refresh_hjks)
        bus.weather_updated.connect(self.update_weather)

        QTimer.singleShot(2250, self.refresh_data)  # 최초 1회 로드

        self.weather_cycle_timer = QTimer(self)
        self.weather_cycle_timer.timeout.connect(self._cycle_weather)

        self.spot_cycle_timer = QTimer(self)
        self.spot_cycle_timer.timeout.connect(self._cycle_spot)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        self.title_lbl = QLabel(tr("総合ダッシュボード"))
        layout.addWidget(self.title_lbl)
        layout.addSpacing(20)

        grid = QGridLayout()
        grid.setSpacing(20)

        self.card_imb   = SummaryCard(tr("本日の最大インバランス"), "won", "#F44336")
        self.card_occto = SummaryCard(tr("本日の最低電力予備率"), "power", "#2196F3")
        self.card_wea   = SummaryCard(tr("全国の天気"), "weather", "#4CAF50")
        self.card_jkm   = SummaryCard(tr("最新 JKM LNG 価格"), "fire", "#FF9800")
        self.card_hjks  = SummaryCard(tr("本日の発電稼働容量"), "plant", "#9C27B0")
        self.card_spot  = SpotDashCard()
        self.card_spot.mode_changed.connect(self._on_spot_mode_changed)

        # row 0-1: 既存カード, row 2: スポットカード, col 2: 天気(3行スパン)
        grid.addWidget(self.card_imb,   0, 0)
        grid.addWidget(self.card_occto, 0, 1)
        grid.addWidget(self.card_wea,   0, 2, 3, 1)   # 3行スパン
        grid.addWidget(self.card_jkm,   1, 0)
        grid.addWidget(self.card_hjks,  1, 1)
        grid.addWidget(self.card_spot,  2, 0, 1, 2)   # 2列スパン

        # 카드 클릭 → 해당 탭으로 이동
        # content_stack 순서: 0=Dashboard, 1=JepxSpot, 2=PowerReserve, 3=Imbalance,
        #                     4=JKM, 5=Weather, 6=HJKS
        self.card_spot.clicked.connect(lambda: bus.page_requested.emit(1))
        self.card_occto.clicked.connect(lambda: bus.page_requested.emit(2))
        self.card_imb.clicked.connect(lambda: bus.page_requested.emit(3))
        self.card_jkm.clicked.connect(lambda: bus.page_requested.emit(4))
        self.card_wea.clicked.connect(lambda: bus.page_requested.emit(5))
        self.card_hjks.clicked.connect(lambda: bus.page_requested.emit(6))

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        grid.setRowStretch(2, 1)

        layout.addLayout(grid)

    def showEvent(self, event):
        super().showEvent(event)
        self.weather_cycle_timer.start(3000)
        self.spot_cycle_timer.start(3000)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.weather_cycle_timer.stop()
        self.spot_cycle_timer.stop()

    def apply_theme_custom(self):
        is_dark = self.is_dark
        self.title_lbl.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {UIColors.text_default(is_dark)};")
        self.card_imb.set_theme(is_dark)
        self.card_occto.set_theme(is_dark)
        self.card_wea.set_theme(is_dark)
        self.card_jkm.set_theme(is_dark)
        self.card_hjks.set_theme(is_dark)
        self.card_spot.set_theme(is_dark)
        if self.card_wea._illust:
            self.card_wea._illust.set_category(
                self.card_wea._illust._category, is_dark
            )
        if self._weather_list:
            cur_idx = (self._weather_index - 1) % len(self._weather_list)
            entry   = self._weather_list[cur_idx]
            category = _WMO_CATEGORY.get(entry.wmo_code, "clear")
            self.card_wea.set_card_bg(
                (_WMO_BG_DARK if is_dark else _WMO_BG_LIGHT).get(category, ""))
            self.card_wea.set_value(
                entry.temp_str, self._weather_sub_html(entry), entry.accent_color)

    def closeEvent(self, event):
        for sig, slot in [
            (bus.occto_updated,     self.update_occto),
            (bus.imbalance_updated, self.refresh_imbalance),
            (bus.jkm_updated,       self.refresh_jkm),
            (bus.hjks_updated,      self.refresh_hjks),
            (bus.weather_updated,   self.update_weather),
        ]:
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        super().closeEvent(event)

    def refresh_data(self):
        self.request_fetch.emit("all")

    def refresh_imbalance(self):
        self.request_fetch.emit("imbalance")

    def _on_imb_result(self, max_val, max_info):
        color = _high_alert_color(max_val, self.is_dark)
        self.card_imb.set_value(f"{max_val:,.1f} 円", max_info, color, target_val=max_val, format_str="{:,.1f} 円")

    def _on_imb_empty(self):
        self.card_imb.set_value(tr("-- 円"), tr("本日のデータなし"))

    def refresh_jkm(self):
        self.request_fetch.emit("jkm")

    def _on_jkm_result(self, price, date, pct):
        sign, color = ("▲", ("#ff5252" if self.is_dark else "#d32f2f")) if pct < 0 else ("▼", ("#4caf50" if self.is_dark else "#388e3c"))
        self.card_jkm.set_value(f"{price:.3f} USD", tr("{0} (前日比 {1} {2}%)").format(date, sign, abs(pct)) if pct else date, color if pct else None, target_val=price, format_str="{:.3f} USD")

    def _on_jkm_empty(self):
        self.card_jkm.set_value(tr("-- USD"), tr("データなし"))

    def refresh_hjks(self):
        self.request_fetch.emit("hjks")

    def _on_hjks_result(self, operating_mw, stopped_mw):
        self.card_hjks.set_value(f"{operating_mw:,.0f} MW", tr("停止中: {0} MW").format(f"{stopped_mw:,.0f}"), target_val=operating_mw, format_str="{:,.0f} MW")

    def _on_hjks_empty(self):
        self.card_hjks.set_value("0 MW", tr("本日のデータなし"))

    def update_occto(self, time_str, area_str, min_val):
        color = _low_alert_color(min_val, self.is_dark)
        self.card_occto.set_value(f"{min_val:.1f} %", f"{time_str} / {area_str}", color, target_val=min_val, format_str="{:.1f} %")

    def update_weather(self, weather_list):
        self._weather_list = weather_list
        self._weather_index = 0
        self._cycle_weather()

    def _weather_sub_html(self, entry) -> str:
        region_color = "#81c784" if self.is_dark else "#2e7d32"
        return (
            f"<span style='font-size:15px;font-weight:bold;color:{region_color};'>"
            f"{entry.region}</span>"
            f"<br/><span style='font-size:11px;color:#888888;'>{entry.weather_text}</span>"
        )

    def _cycle_weather(self):
        if not self._weather_list:
            return
        if self.card_wea.underMouse():
            return
        entry    = self._weather_list[self._weather_index]
        category = _WMO_CATEGORY.get(entry.wmo_code, "clear")
        bg_map   = _WMO_BG_DARK if self.is_dark else _WMO_BG_LIGHT
        self.card_wea.set_card_bg(bg_map.get(category, ""))
        self.card_wea.set_weather_illust(category, self.is_dark)
        self.card_wea.set_value(
            entry.temp_str,
            self._weather_sub_html(entry),
            entry.accent_color,
            animate_fade=True,
        )
        self._weather_index = (self._weather_index + 1) % len(self._weather_list)

    # ── JEPX スポット ─────────────────────────────────────────────────────────

    def _on_spot_today_result(self, data: list):
        self._spot_today = data
        if self.card_spot._date_mode == 'today':
            self._spot_index = 0
            self._cycle_spot()

    def _on_spot_tomorrow_result(self, data: list):
        self._spot_tomorrow = data
        if self.card_spot._date_mode == 'tomorrow':
            self._spot_index = 0
            self._cycle_spot()

    def _on_spot_mode_changed(self, _mode: str):
        self._spot_index = 0
        self._cycle_spot()

    def _cycle_spot(self):
        if self.card_spot.underMouse():
            return
        data = self._spot_today if self.card_spot._date_mode == 'today' else self._spot_tomorrow
        if not data:
            self.card_spot.set_no_data()
            return
        entry = data[self._spot_index % len(data)]
        avg = entry[1]
        color = _high_alert_color(avg, self.is_dark)
        self.card_spot.set_data(entry[0], avg, entry[2], entry[3], val_color=color)
        self._spot_index = (self._spot_index + 1) % len(data)
