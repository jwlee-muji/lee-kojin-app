import requests
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QSplitter, QTableWidgetItem, QHeaderView, QMessageBox, QFrame, QPushButton,
    QApplication,
)
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QFont, QColor, QBrush
from app.ui.common import ExcelCopyTableWidget, BaseWidget
from app.core.config import WEATHER_REGIONS, load_settings, API_OPEN_METEO

logger = logging.getLogger(__name__)

# WMO 날씨 코드를 일본어 및 이모지로 변환하는 매핑 함수
def get_weather_info(code):
    mapping = {
        0:  ("☀️ 晴れ", "#FF9800"),
        1:  ("🌤️ 概ね晴れ", "#FFB74D"),
        2:  ("⛅ 一部曇り", "#78909C"),
        3:  ("☁️ 曇り", "#607D8B"),
        45: ("🌫️ 霧", "#9E9E9E"),
        48: ("🌫️ 霧氷", "#9E9E9E"),
        51: ("🌧️ 弱い霧雨", "#4FC3F7"),
        53: ("🌧️ 霧雨", "#29B6F6"),
        55: ("🌧️ 強い霧雨", "#039BE5"),
        56: ("🌧️ 弱い着氷性霧雨", "#4DD0E1"),
        57: ("🌧️ 強い着氷性霧雨", "#00BCD4"),
        61: ("☔ 弱い雨", "#4FC3F7"),
        63: ("☔ 雨", "#039BE5"),
        65: ("☔ 強い雨", "#0277BD"),
        66: ("☔ 弱い着氷性の雨", "#26C6DA"),
        67: ("☔ 強い着氷性の雨", "#0097A7"),
        71: ("❄️ 弱い雪", "#E1F5FE"),
        73: ("❄️ 雪", "#B3E5FC"),
        75: ("❄️ 強い雪", "#81D4FA"),
        77: ("❄️ 霧雪", "#E1F5FE"),
        80: ("🌦️ 弱い小雨", "#4FC3F7"),
        81: ("🌦️ 小雨", "#039BE5"),
        82: ("🌦️ 激しい小雨", "#0277BD"),
        85: ("🌨️ 弱い雪降る", "#B3E5FC"),
        86: ("🌨️ 強い雪降る", "#81D4FA"),
        95: ("⛈️ 雷雨", "#F44336"),
        96: ("⛈️ 弱い雹を伴う雷雨", "#D32F2F"),
        99: ("⛈️ 強い雹を伴う雷雨", "#B71C1C"),
    }
    return mapping.get(code, ("❓ 不明", "#757575"))


class FetchWeatherWorker(QThread):
    finished = Signal(list)
    error    = Signal(str)

    def run(self):
        with requests.Session() as session:
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            try:
                logger.info("Open-Meteo から全国天気予報のデータ取得を開始します。")
                lats = ",".join(str(r["lat"]) for r in WEATHER_REGIONS)
                lons = ",".join(str(r["lon"]) for r in WEATHER_REGIONS)
                
                params = {
                    "latitude": lats,
                    "longitude": lons,
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,cloud_cover_mean,wind_speed_10m_max",
                    "timezone": "Asia/Tokyo"
                }
                
                response = session.get(API_OPEN_METEO, params=params, timeout=15)
                response.raise_for_status()
                data = response.json()
                logger.info("天気予報データの取得に成功しました。")
                
                # 단일 지역 조회일 경우 dict로 반환되므로 리스트로 변환
                if isinstance(data, dict):
                    data = [data]
                    
                self.finished.emit(data)
            except Exception as e:
                logger.error(f"天気予報データの取得中にエラーが発生しました: {str(e)}")
                self.error.emit(f"天気の取得に失敗しました: {str(e)}")


class RegionCard(QFrame):
    """좌측 목록에 표시될 각 지역별 요약 카드"""
    def __init__(self, region_name, today_data, is_dark=True):
        super().__init__()
        self.setStyleSheet("QFrame { background: transparent; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)

        # 지역명
        name_lbl = QLabel(region_name)
        name_lbl.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {'#eeeeee' if is_dark else '#333333'}; background: transparent;")
        layout.addWidget(name_lbl)

        # 오늘 날씨 정보 파싱 (빈 리스트 방어 처리)
        w_code = today_data.get("weather_code",                    [0])[0] if today_data.get("weather_code")                    else 0
        t_max  = today_data.get("temperature_2m_max",           [None])[0] if today_data.get("temperature_2m_max")           else None
        t_min  = today_data.get("temperature_2m_min",           [None])[0] if today_data.get("temperature_2m_min")           else None
        pop    = today_data.get("precipitation_probability_max",   [0])[0] if today_data.get("precipitation_probability_max") else 0
        
        w_text, w_color = get_weather_info(w_code)

        # 날씨 및 기온
        info_layout = QHBoxLayout()
        weather_lbl = QLabel(w_text)
        weather_lbl.setStyleSheet(f"font-size: 11pt; color: {w_color}; font-weight: bold; background: transparent;")
        
        t_max_str = f"{t_max}℃" if t_max is not None else "—"
        t_min_str = f"{t_min}℃" if t_min is not None else "—"
        
        tc = '#eeeeee' if is_dark else '#333333'
        temp_lbl = QLabel(f"<span style='color:#ef5350;'>{t_max_str}</span> <span style='color:{tc};'>/</span> <span style='color:#42a5f5;'>{t_min_str}</span>")
        temp_lbl.setStyleSheet("font-size: 11pt; background: transparent;")
        
        pop_lbl = QLabel(f"☔ {pop}%")
        pop_lbl.setStyleSheet("font-size: 10pt; color: #aaaaaa; background: transparent;")

        # HTML(Rich Text) 렌더링 시 높이 계산 오류로 인한 하단 잘림 방지
        weather_lbl.setMinimumHeight(24)
        temp_lbl.setMinimumHeight(24)
        pop_lbl.setMinimumHeight(20)

        info_layout.addWidget(weather_lbl)
        info_layout.addStretch()
        info_layout.addWidget(temp_lbl)
        
        layout.addLayout(info_layout)
        layout.addWidget(pop_lbl, alignment=Qt.AlignRight)


class WeatherWidget(BaseWidget):
    summary_updated = Signal(list)

    def __init__(self):
        super().__init__()
        self.weather_data = []
        self.worker = None
        self._build_ui()
        
        # 실행 시 날씨 갱신 (이후 1시간마다 자동 갱신)
        self.fetch_weather()
        self.setup_timer(self.settings.get("weather_interval", 60), self.fetch_weather)
        
    def apply_settings_custom(self):
        self.update_timer_interval(self.settings.get("weather_interval", 60))

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        
        # 상단 타이틀 바
        top = QHBoxLayout()
        title = QLabel(self.tr("全国天気予報 (Open-Meteo)"))
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.status_label = QLabel(self.tr("待機中..."))
        self.status_label.setStyleSheet("color: #aaaaaa;")
        
        top.addWidget(title)
        top.addSpacing(15)
        top.addWidget(self.status_label)
        top.addStretch()
        
        self.refresh_btn = QPushButton(self.tr("更新 (再取得)"))
        self.refresh_btn.clicked.connect(self.fetch_weather)
        top.addWidget(self.refresh_btn)
        
        main_layout.addLayout(top)
        
        # 메인 스플리터 (좌: 지역 목록, 우: 세부 정보)
        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter, 1)
        
        # 좌측 지역 리스트
        self.region_list = QListWidget()
        self.region_list.currentRowChanged.connect(self._on_region_selected)
        self.splitter.addWidget(self.region_list)
        
        # 우측 상세 테이블 패널
        detail_container = QWidget()
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(10, 0, 0, 0)
        
        self.detail_title = QLabel(self.tr("👈 左側の地域を選択してください"))
        self.detail_title.setStyleSheet("font-size: 16px; font-weight: bold; padding-bottom: 10px; color: #eeeeee;")
        detail_layout.addWidget(self.detail_title)
        
        self.detail_table = ExcelCopyTableWidget()
        self.detail_table.setColumnCount(8)
        self.detail_table.setHorizontalHeaderLabels([self.tr("日付"), self.tr("天気"), self.tr("最高気温"), self.tr("最低気温"), self.tr("降水確率"), self.tr("降水量"), self.tr("雲量"), self.tr("最大風速")])
        self.detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.detail_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.detail_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        # 행 높이를 위젯 높이에 맞춰 자동으로 조절
        self.detail_table.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.detail_table.setAlternatingRowColors(True)
        
        detail_layout.addWidget(self.detail_table)
        self.splitter.addWidget(detail_container)
        
        self.splitter.setSizes([250, 650])
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 7)
        
        self.apply_theme_custom()

    def apply_theme_custom(self):
        is_dark = self.is_dark
        self.detail_title.setStyleSheet(f"font-size: 16px; font-weight: bold; padding-bottom: 10px; color: {'#eeeeee' if is_dark else '#333333'};")
        
        if is_dark:
            self.region_list.setStyleSheet("""
                QListWidget { background-color: #1e1e1e; border: none; border-right: 1px solid #3e3e42; outline: 0; }
                QListWidget::item { border-bottom: 1px solid #2d2d30; margin: 0px; border-radius: 0px; }
                QListWidget::item:hover { background-color: #252526; }
                QListWidget::item:selected { background-color: #2d2d30; border-left: 4px solid #094771; }
            """)
        else:
            self.region_list.setStyleSheet("""
                QListWidget { background-color: #ffffff; border: none; border-right: 1px solid #dddddd; outline: 0; }
                QListWidget::item { border-bottom: 1px solid #eeeeee; margin: 0px; border-radius: 0px; }
                QListWidget::item:hover { background-color: #fafafa; }
                QListWidget::item:selected { background-color: #f4f8ff; border-left: 4px solid #2196f3; }
            """)

        self._populate_region_list()
        self._on_region_selected(self.region_list.currentRow())

    def fetch_weather(self):
        if not self.check_online_status(): return
        if self.worker and self.worker.isRunning():
            return
        self.refresh_btn.setEnabled(False)
        self.status_label.setText("天気データを取得中...")
        self.status_label.setStyleSheet("color: #64b5f6;")
        
        self.worker = FetchWeatherWorker()
        self.worker.finished.connect(self._on_fetch_success)
        self.worker.error.connect(self._on_fetch_error)
        self.worker.start()

    def _on_fetch_success(self, data_list):
        self.refresh_btn.setEnabled(True)
        self.weather_data = data_list
        self.status_label.setText("取得完了")
        self.status_label.setStyleSheet("color: #4caf50;")
        self._populate_region_list()

        # ダッシュボード用に全国の天気を送信
        weather_summary = []
        for i, region in enumerate(WEATHER_REGIONS):
            if i >= len(self.weather_data): break
            daily = self.weather_data[i].get("daily", {})
            if daily:
                w_code = daily.get("weather_code", [0])[0] if daily.get("weather_code") else 0
                t_max  = daily.get("temperature_2m_max", [None])[0] if daily.get("temperature_2m_max") else None
                t_min  = daily.get("temperature_2m_min", [None])[0] if daily.get("temperature_2m_min") else None
                w_text, w_color = get_weather_info(w_code)
                t_max_str = f"{t_max}℃" if t_max is not None else "—"
                t_min_str = f"{t_min}℃" if t_min is not None else "—"
                weather_summary.append((region["name"], w_text, f"{t_max_str} / {t_min_str}", w_color))
        
        if weather_summary:
            self.summary_updated.emit(weather_summary)

    def _on_fetch_error(self, err_msg):
        self.refresh_btn.setEnabled(True)
        self.status_label.setText("取得失敗")
        self.status_label.setStyleSheet("color: #ff5252;")
        QMessageBox.warning(self, "エラー", err_msg)

    def _populate_region_list(self):
        self.region_list.clear()
        
        for i, region in enumerate(WEATHER_REGIONS):
            if i >= len(self.weather_data):
                break
            
            daily = self.weather_data[i].get("daily", {})
            if not daily:
                continue
                
            item = QListWidgetItem(self.region_list)
            card = RegionCard(region["name"], daily, self.is_dark)
            item.setSizeHint(card.sizeHint())
            self.region_list.setItemWidget(item, card)
            
        # 데이터 로드 후 첫 번째 항목 자동 선택
        if self.region_list.count() > 0:
            self.region_list.setCurrentRow(0)

    def _create_table_item(self, text, color=None, bold=False):
        it = QTableWidgetItem(str(text))
        it.setTextAlignment(Qt.AlignCenter)
        if color:
            it.setForeground(QBrush(QColor(color)))
        if bold:
            f = it.font()
            f.setBold(True)
            it.setFont(f)
        return it

    def _on_region_selected(self, index):
        if index < 0 or index >= len(self.weather_data):
            return
            
        region_name = WEATHER_REGIONS[index]["name"]
        self.detail_title.setText(f"📍 {region_name} の詳細天気 (7日間)")
        
        daily = self.weather_data[index].get("daily", {})
        if not daily:
            return
            
        dates   = daily.get("time", [])
        w_codes = daily.get("weather_code", [])
        t_maxs  = daily.get("temperature_2m_max", [])
        t_mins  = daily.get("temperature_2m_min", [])
        pops    = daily.get("precipitation_probability_max", [])
        p_sums  = daily.get("precipitation_sum", [])
        clouds  = daily.get("cloud_cover_mean", [])
        winds   = daily.get("wind_speed_10m_max", [])
        
        self.detail_table.setUpdatesEnabled(False)
        self.detail_table.setRowCount(len(dates))
        
        for row, date_str in enumerate(dates):
            w_text, _ = get_weather_info(w_codes[row])
            
            self.detail_table.setItem(row, 0, self._create_table_item(date_str))
            self.detail_table.setItem(row, 1, self._create_table_item(w_text))
            self.detail_table.setItem(row, 2, self._create_table_item(f"{t_maxs[row]} ℃", "#ef5350", bold=True))
            self.detail_table.setItem(row, 3, self._create_table_item(f"{t_mins[row]} ℃", "#42a5f5", bold=True))
            
            pop_val = pops[row]
            pop_color = "#66bb6a" if pop_val < 30 else "#ffa726" if pop_val < 60 else "#ef5350"
            self.detail_table.setItem(row, 4, self._create_table_item(f"{pop_val} %", pop_color, bold=True))
            
            psum_val = p_sums[row]
            psum_str = f"{psum_val} mm" if psum_val > 0 else "-"
            self.detail_table.setItem(row, 5, self._create_table_item(psum_str, "#29b6f6" if psum_val > 0 else "#9E9E9E"))

            cloud_val = clouds[row] if row < len(clouds) else 'N/A'
            self.detail_table.setItem(row, 6, self._create_table_item(f"{cloud_val} %", "#78909C"))

            wind_val = winds[row] if row < len(winds) else 'N/A'
            self.detail_table.setItem(row, 7, self._create_table_item(f"{wind_val} km/h", "#8D6E63"))

        self.detail_table.setUpdatesEnabled(True)