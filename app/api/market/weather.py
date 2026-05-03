"""
全国天気予報 (Open-Meteo) API 通信モジュール
- FetchWeatherWorker      : 7日間予報 (10分 TTL キャッシュ付き)
- FetchWeatherHistoryWorker: 2022-03 〜 昨日の過去実測データ一括取得
"""
import time
import threading
import logging
from datetime import date, timedelta

import requests
from PySide6.QtCore import Signal

from app.api.base import BaseWorker
from app.core.config import API_OPEN_METEO, WEATHER_REGIONS, DB_WEATHER
from app.core.database import get_db_connection

logger = logging.getLogger(__name__)

_ARCHIVE_API       = "https://archive-api.open-meteo.com/v1/archive"
_HISTORY_START     = date(2022, 3, 1)   # インバランスと同じ起点

# 過去データ取得用の daily 変数 (precipitation_probability_max は予報専用のため除外)
_ARCHIVE_DAILY = (
    "weather_code,temperature_2m_max,temperature_2m_min,"
    "precipitation_sum,cloud_cover_mean,wind_speed_10m_max"
)

_WEATHER_CACHE_TTL = 600
_weather_cache: list | None = None
_weather_cache_ts: float    = 0.0
_weather_cache_lock         = threading.Lock()

# DB スキーマ (weather.py ウィジェットと共通)
_CREATE_WEATHER_DDL = """
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


# ── 予報 Worker ─────────────────────────────────────────────────────────────────

class FetchWeatherWorker(BaseWorker):
    finished = Signal(list)

    def run(self):
        global _weather_cache, _weather_cache_ts

        with _weather_cache_lock:
            now = time.monotonic()
            if _weather_cache is not None and (now - _weather_cache_ts) < _WEATHER_CACHE_TTL:
                logger.info("天気予報データをキャッシュから返します。")
                self.finished.emit(_weather_cache)
                return

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
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m",
                    "hourly":  "temperature_2m,weather_code,precipitation_probability,wind_speed_10m",
                    "daily":   "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,cloud_cover_mean,wind_speed_10m_max",
                    "forecast_hours": 24,
                    "timezone": "Asia/Tokyo",
                }

                response = session.get(API_OPEN_METEO, params=params, timeout=15)
                response.raise_for_status()
                data = response.json()
                logger.info("天気予報データの取得に成功しました。")

                if isinstance(data, dict):
                    data = [data]

                with _weather_cache_lock:
                    _weather_cache    = data
                    _weather_cache_ts = time.monotonic()

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


# ── 過去データ Worker ───────────────────────────────────────────────────────────

def _build_year_batches() -> list[tuple[str, str, int]]:
    """2022-03 〜 昨日を年単位のバッチに分割。(start, end, year) のリストを返す。"""
    yesterday = date.today() - timedelta(days=1)
    batches: list[tuple[str, str, int]] = []
    y = _HISTORY_START.year
    while y <= yesterday.year:
        start = _HISTORY_START if y == _HISTORY_START.year else date(y, 1, 1)
        end   = date(y, 12, 31) if y < yesterday.year else yesterday
        if start <= end:
            batches.append((start.isoformat(), end.isoformat(), y))
        y += 1
    return batches


def _years_in_db() -> set[int]:
    """DB に過去実測データ (fetched_date = date) が存在する年の集合を返す。"""
    try:
        with get_db_connection(DB_WEATHER) as conn:
            conn.execute(_CREATE_WEATHER_DDL)
            rows = conn.execute(
                "SELECT DISTINCT CAST(strftime('%Y', date) AS INTEGER) "
                "FROM weather_forecast WHERE fetched_date = date"
            ).fetchall()
        return {row[0] for row in rows if row[0]}
    except Exception as e:
        logger.debug(f"DB年確認エラー: {e}")
        return set()


def _save_history_batch(data: list, start: str, end: str) -> int:
    """API レスポンスを DB に保存。fetched_date = date (実測マーカー)。
    保存件数を返す。"""
    records: list[tuple] = []
    for i, region_info in enumerate(WEATHER_REGIONS):
        if i >= len(data):
            break
        daily = data[i].get("daily", {})
        if not daily:
            continue
        region_name = region_info["name"]
        dates   = daily.get("time", [])
        w_codes = daily.get("weather_code", [])
        t_maxs  = daily.get("temperature_2m_max", [])
        t_mins  = daily.get("temperature_2m_min", [])
        p_sums  = daily.get("precipitation_sum", [])
        clouds  = daily.get("cloud_cover_mean", [])
        winds   = daily.get("wind_speed_10m_max", [])

        for j, d in enumerate(dates):
            records.append((
                d,                                           # fetched_date = date
                region_name, d,
                w_codes[j] if j < len(w_codes) else None,
                t_maxs[j]  if j < len(t_maxs)  else None,
                t_mins[j]  if j < len(t_mins)   else None,
                None,                                        # precip_prob (予報専用)
                p_sums[j]  if j < len(p_sums)   else None,
                int(clouds[j]) if j < len(clouds) and clouds[j] is not None else None,
                winds[j]   if j < len(winds)    else None,
            ))

    if not records:
        return 0

    with get_db_connection(DB_WEATHER) as conn:
        conn.execute(_CREATE_WEATHER_DDL)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wf_date_region "
            "ON weather_forecast(date, region)"
        )
        conn.executemany(
            "INSERT OR REPLACE INTO weather_forecast "
            "(fetched_date, region, date, weather_code, temp_max, temp_min, "
            "precip_prob, precip_sum, cloud_cover, wind_speed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            records,
        )
        conn.commit()
    return len(records)


class FetchWeatherHistoryWorker(BaseWorker):
    """2022-03-01 〜 昨日の過去実測データを Open-Meteo Archive API から取得してDBに保存。
    既にDBにある年 (当年を除く) はスキップして差分のみ取得する。
    """
    finished = Signal(str)
    progress = Signal(str)

    def run(self):
        try:
            logger.info("過去天気データ取得: 開始")
            batches      = _build_year_batches()
            existing     = _years_in_db()
            current_year = date.today().year

            # 当年は常に再取得、それ以外は DB に存在しない年のみ
            to_fetch = [
                (s, e, y) for s, e, y in batches
                if y not in existing or y == current_year
            ]

            if not to_fetch:
                self.finished.emit("過去データは最新です。")
                return

            logger.info(f"過去天気データ: {len(to_fetch)}年分取得予定")

            lats = ",".join(str(r["lat"]) for r in WEATHER_REGIONS)
            lons = ",".join(str(r["lon"]) for r in WEATHER_REGIONS)

            total_records = 0
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0"})

            for i, (start, end, year) in enumerate(to_fetch, 1):
                self.progress.emit(f"({i}/{len(to_fetch)}) {year}年 取得中... ({start} 〜 {end})")
                logger.info(f"過去天気 {year}年: {start} 〜 {end}")

                try:
                    r = session.get(
                        _ARCHIVE_API,
                        params={
                            "latitude":   lats,
                            "longitude":  lons,
                            "start_date": start,
                            "end_date":   end,
                            "daily":      _ARCHIVE_DAILY,
                            "timezone":   "Asia/Tokyo",
                        },
                        timeout=60,
                    )
                    r.raise_for_status()
                    data = r.json()
                    if isinstance(data, dict):
                        data = [data]

                    saved = _save_history_batch(data, start, end)
                    total_records += saved
                    logger.info(f"過去天気 {year}年: {saved}件保存")

                except requests.HTTPError as e:
                    logger.warning(f"過去天気 {year}年 HTTP エラー: {e}")
                except Exception as e:
                    logger.warning(f"過去天気 {year}年 取得失敗: {e}")

                time.sleep(0.3)

            msg = f"過去データ取得完了 ({len(to_fetch)}年分 / {total_records}件)"
            logger.info(msg)
            self.finished.emit(msg)

        except requests.exceptions.RequestException as e:
            logger.error(f"過去天気 通信エラー: {e}")
            self.error.emit(f"通信エラー: {str(e)}")
        except Exception as e:
            logger.error(f"過去天気 取得エラー: {e}", exc_info=True)
            self.error.emit(f"エラー: {str(e)}")
