"""
全国天気予報 (Open-Meteo) API 通信モジュール
"""
import requests
import logging
from PySide6.QtCore import QThread, Signal
from app.api.base import BaseWorker
from app.core.config import API_OPEN_METEO, WEATHER_REGIONS

logger = logging.getLogger(__name__)

class FetchWeatherWorker(BaseWorker):
    finished = Signal(list)

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
            except requests.exceptions.RequestException as e:
                logger.error(f"天気予報データの取得中に通信エラーが発生しました: {str(e)}")
                self.error.emit(f"天気の取得に失敗しました(通信エラー): {str(e)}")
            except (ValueError, KeyError) as e:
                logger.error(f"天気予報APIの応答解析中にエラーが発生しました: {str(e)}")
                self.error.emit(f"API応答の解析に失敗しました: {str(e)}")
            except Exception as e:
                logger.error(f"天気予報データの取得中に予期せぬエラーが発生しました: {str(e)}", exc_info=True)
                self.error.emit(f"天気の取得中に予期せぬエラーが発生しました: {str(e)}")