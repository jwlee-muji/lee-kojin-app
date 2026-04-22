"""
電力予備率(OCCTO) API 通信モジュール
- FetchPowerReserveWorker      : 指定日の予備率取得 (ウィジェット表示用)
- FetchPowerReserveHistoryWorker: 前年度開始〜今日の履歴一括取得 (並列6ワーカー)
"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import requests
from PySide6.QtCore import Signal

from app.api.base import BaseWorker, HTTP_TIMEOUT
from app.core.config import API_OCCTO_RESERVE, DB_POWER_RESERVE
from app.core.database import get_db_connection

logger = logging.getLogger(__name__)

# OCCTO エリアコード → DB カラム名
_AREA_MAP_COL = {
    1: "hokkaido", 2: "tohoku",   3: "tokyo",  4: "chubu",  5: "hokuriku",
    6: "kansai",   7: "chugoku",  8: "shikoku", 9: "kyushu", 10: "okinawa",
}
_ALL_AREA_COLS = [
    "hokkaido", "tohoku", "tokyo", "chubu", "hokuriku",
    "kansai", "chugoku", "shikoku", "kyushu", "okinawa",
]

_CREATE_POWER_RESERVE_DDL = """
    CREATE TABLE IF NOT EXISTS power_reserve (
        date     TEXT NOT NULL,
        time     TEXT NOT NULL,
        hokkaido REAL, tohoku REAL, tokyo   REAL,
        chubu    REAL, hokuriku REAL, kansai REAL,
        chugoku  REAL, shikoku  REAL, kyushu REAL, okinawa REAL,
        PRIMARY KEY (date, time)
    )
"""

_API_HEADERS = {
    "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":           "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}


# ── 共通パーサー ────────────────────────────────────────────────────────────────

def _parse_occto_to_records(date_str: str, data: dict) -> list[tuple]:
    """OCCTO JSON レスポンスを power_reserve テーブル用タプルリストに変換。"""
    area_list = data.get("todayAreaRsvRateList") or []
    if not area_list:
        return []

    area_data: dict[str, dict[str, float | None]] = {}
    for a in area_list:
        cd  = int(a.get("areaCd", 99))
        col = _AREA_MAP_COL.get(cd)
        if not col:
            continue
        items = a.get("areaRsvRateItems", [])
        area_data[col] = {}
        for i, item in enumerate(items):
            val    = item.get("koikRsvRate")
            if val is None:
                val = item.get("areaRsvRate") or item.get("rsvRate")
            t_time = item.get("targetTime") or f"{i // 2:02d}:{(i % 2) * 30:02d}"
            try:
                area_data[col][t_time] = float(val) if val is not None else None
            except (ValueError, TypeError):
                area_data[col][t_time] = None

    records: list[tuple] = []
    for slot in range(48):
        time_str = f"{slot // 2:02d}:{(slot % 2) * 30:02d}"
        rec = [date_str, time_str] + [area_data.get(c, {}).get(time_str) for c in _ALL_AREA_COLS]
        records.append(tuple(rec))
    return records


def _save_records(records: list[tuple]) -> None:
    """power_reserve テーブルに UPSERT。"""
    if not records:
        return
    cols_sql = "date, time, " + ", ".join(_ALL_AREA_COLS)
    ph       = ", ".join(["?"] * (2 + len(_ALL_AREA_COLS)))
    with get_db_connection(DB_POWER_RESERVE) as conn:
        conn.execute(_CREATE_POWER_RESERVE_DDL)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pr_date ON power_reserve(date)")
        conn.executemany(
            f"INSERT OR REPLACE INTO power_reserve ({cols_sql}) VALUES ({ph})",
            records,
        )
        conn.commit()


# ── 単日取得 Worker ────────────────────────────────────────────────────────────

class FetchPowerReserveWorker(BaseWorker):
    """BaseWorker 継承により共通の error シグナルと _emit_error() を利用します。"""
    data_fetched = Signal(list, list)

    def __init__(self, target_date_str):
        super().__init__()
        self.target_date_str = target_date_str

    def run(self):
        with requests.Session() as session:
            session.headers.update(_API_HEADERS)
            try:
                logger.info(f"OCCTO 電力予備率データ({self.target_date_str})のAPI取得を開始します。")
                params = {"inputDate": self.target_date_str.replace("-", "/")}

                res = session.get(API_OCCTO_RESERVE, params=params, timeout=HTTP_TIMEOUT)
                res.raise_for_status()

                if "application/json" not in res.headers.get("Content-Type", ""):
                    raise ValueError("APIからの応答がJSON形式ではありません。")

                data = res.json()
                area_list = data.get("todayAreaRsvRateList")
                if not area_list:
                    self.data_fetched.emit([], [])
                    return

                AREA_MAP = {
                    1: "北海道", 2: "東北", 3: "東京", 4: "中部", 5: "北陸",
                    6: "関西",   7: "中国", 8: "四国", 9: "九州", 10: "沖縄",
                }
                processed_areas = []
                for a in area_list:
                    cd    = int(a.get("areaCd", 99))
                    items = a.get("areaRsvRateItems", [])
                    val_map = {}
                    for i, item in enumerate(items):
                        val    = item.get("koikRsvRate")
                        if val is None:
                            val = item.get("areaRsvRate", item.get("rsvRate"))
                        t_time = item.get("targetTime")
                        val_map[t_time if t_time else f"{i // 2:02d}:{(i % 2) * 30:02d}"] = val
                    processed_areas.append({"cd": cd, "val_map": val_map})

                processed_areas.sort(key=lambda x: x["cd"])
                headers   = ["時間"] + [AREA_MAP.get(pa["cd"], f"エリア{pa['cd']}") for pa in processed_areas]
                final_rows = []
                for time_idx in range(48):
                    time_str = f"{time_idx // 2:02d}:{(time_idx % 2) * 30:02d}"
                    row_data = [time_str]
                    for pa in processed_areas:
                        val = pa["val_map"].get(time_str)
                        row_data.append(f"{float(val):.1f}%" if val is not None else "-")
                    final_rows.append(row_data)

                logger.info(f"OCCTO APIからのデータ抽出が完了しました。 (行数: {len(final_rows)}行)")
                self.data_fetched.emit(headers, final_rows)
            except requests.exceptions.RequestException as e:
                self._emit_error("通信エラーが発生しました", e)
            except (ValueError, KeyError, TypeError) as e:
                self._emit_error("API応答の解析エラー", e)
            except Exception as e:
                self._emit_error("予期せぬエラーが発生しました", e)


# ── 履歴一括取得 Worker ────────────────────────────────────────────────────────

def _prev_fy_start() -> date:
    """前年度の開始日 (4月1日) を返す。例: 2026年4月 → 2025-04-01"""
    today = date.today()
    year  = today.year - 1 if today.month >= 4 else today.year - 2
    return date(year, 4, 1)


def _dates_in_db() -> set[str]:
    """power_reserve テーブルに存在する日付 (YYYY-MM-DD) の集合を返す。"""
    try:
        with get_db_connection(DB_POWER_RESERVE) as conn:
            conn.execute(_CREATE_POWER_RESERVE_DDL)
            conn.commit()
            rows = conn.execute("SELECT DISTINCT date FROM power_reserve").fetchall()
        return {row[0] for row in rows}
    except Exception as e:
        logger.debug(f"予備率DB日付確認エラー: {e}")
        return set()


def _fetch_single(date_str: str) -> tuple[str, dict | None]:
    """1日分の OCCTO データを取得して返す。失敗時は None。"""
    try:
        r = requests.get(
            API_OCCTO_RESERVE,
            params={"inputDate": date_str.replace("-", "/")},
            headers=_API_HEADERS,
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        if "application/json" not in r.headers.get("Content-Type", ""):
            return date_str, None
        return date_str, r.json()
    except Exception as e:
        logger.debug(f"予備率 {date_str} 取得失敗: {e}")
        return date_str, None


class FetchPowerReserveHistoryWorker(BaseWorker):
    """前年度開始 (4月1日) 〜 今日の予備率データを DB に一括取得。
    既存日はスキップ、当日は常に再取得。並列 6 ワーカーで処理する。
    """
    finished = Signal(str)
    progress = Signal(str)

    def run(self):
        try:
            logger.info("電力予備率 履歴取得: 開始")

            # 対象日リスト
            start = _prev_fy_start()
            today = date.today()
            all_dates = []
            d = start
            while d <= today:
                all_dates.append(d.isoformat())
                d += timedelta(days=1)

            # DB 存在チェック (当日は常に再取得)
            today_str    = today.isoformat()
            existing     = _dates_in_db()
            missing      = [d for d in all_dates if d not in existing or d == today_str]

            if not missing:
                self.finished.emit("データは最新です。")
                return

            logger.info(f"電力予備率 履歴取得: {len(missing)}日分")
            self.progress.emit(f"0/{len(missing)} 日取得開始...")

            db_lock  = threading.Lock()
            saved    = 0
            done_cnt = 0

            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = {executor.submit(_fetch_single, d): d for d in missing}
                for future in as_completed(futures):
                    date_str, data = future.result()
                    done_cnt += 1

                    if data:
                        records = _parse_occto_to_records(date_str, data)
                        if records:
                            with db_lock:
                                try:
                                    _save_records(records)
                                    saved += 1
                                except Exception as e:
                                    logger.warning(f"予備率 {date_str} DB保存失敗: {e}")

                    if done_cnt % 10 == 0 or done_cnt == len(missing):
                        self.progress.emit(
                            f"({done_cnt}/{len(missing)}) 最新: {date_str}"
                        )

            msg = f"予備率履歴 取得完了 ({saved}/{len(missing)}日分)"
            logger.info(msg)
            self.finished.emit(msg)

        except Exception as e:
            logger.error(f"予備率履歴取得エラー: {e}", exc_info=True)
            self.error.emit(f"エラー: {str(e)}")
