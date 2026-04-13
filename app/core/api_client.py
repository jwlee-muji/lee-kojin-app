import yfinance as yf
import logging
import requests
import io
import pandas as pd
import sqlite3
from PySide6.QtCore import QThread, Signal
from app.core.config import (
    JKM_TICKER, DB_JKM, DB_IMBALANCE, API_IMBALANCE_BASE, API_OCCTO_RESERVE,
    DATE_COL_IDX, TIME_COL_IDX,
)
from app.core.database import get_db_connection

logger = logging.getLogger(__name__)

def _to_float(val):
    try:
        f = float(val)
        return None if f != f else f
    except (TypeError, ValueError):
        return None

def _save_jkm(rows: list) -> int:
    if not rows: return 0
    with get_db_connection(DB_JKM) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS jkm_prices (
                date  TEXT PRIMARY KEY,
                open  REAL,
                high  REAL,
                low   REAL,
                close REAL NOT NULL
            )
        ''')
        cur = conn.executemany("INSERT OR REPLACE INTO jkm_prices (date, open, high, low, close) VALUES (?,?,?,?,?)", rows)
        conn.commit()
        return cur.rowcount

class FetchJkmWorker(QThread):
    finished = Signal(int)
    error    = Signal(str)

    def run(self):
        try:
            logger.info(f"Yahoo Finance から {JKM_TICKER} (JKM) のデータ取得を開始します。")
            hist = yf.Ticker(JKM_TICKER).history(period='max')
            if hist.empty:
                self.error.emit(f"Yahoo Finance からデータを取得できませんでした (シンボル: {JKM_TICKER})")
                return
            rows = [
                (
                    dt_idx.strftime('%Y-%m-%d'),
                    _to_float(row.get('Open')),
                    _to_float(row.get('High')),
                    _to_float(row.get('Low')),
                    float(row['Close']),
                )
                for dt_idx, row in hist.iterrows()
            ]
            saved_count = _save_jkm(rows)
            logger.info(f"JKM データの取得およびDB保存が完了しました。 (処理行数: {saved_count}件)")
            self.finished.emit(saved_count)
        except requests.exceptions.RequestException as e:
            logger.error(f"JKM データ取得中に通信エラーが発生しました: {str(e)}")
            self.error.emit(f"通信エラー: {str(e)}")
        except Exception as e:
            logger.error(f"JKM データ取得中に予期せぬエラーが発生しました: {str(e)}", exc_info=True)
            self.error.emit(f"予期せぬエラー: {str(e)}")


class UpdateImbalanceWorker(QThread):
    finished = Signal(str)
    error    = Signal(str)

    def run(self):
        try:
            logger.info("インバランス単価のデータ取得を開始します。")
            s    = requests.Session()
            s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

            r        = s.get(f"{API_IMBALANCE_BASE}/imbalance-price-list/priceList", timeout=15)
            r.raise_for_status()
            csv_path = r.json()["imbalance_list"][0]["path"]

            r = s.get(f"{API_IMBALANCE_BASE}/public/price/{csv_path}", timeout=30)
            r.raise_for_status()
            csv_content = r.content.decode('cp932', errors='replace')
            logger.info("CSVデータのダウンロードに成功しました。DBへの保存を開始します。")

            df = pd.read_csv(io.StringIO(csv_content), skiprows=3, thousands=',')
            df.columns = df.columns.astype(str).str.strip().str.replace('\ufeff', '')

            with get_db_connection(DB_IMBALANCE) as conn:
                df.to_sql('imbalance_prices', conn, if_exists='replace', index=False)
                date_col = df.columns[DATE_COL_IDX]
                time_col = df.columns[TIME_COL_IDX]
                conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS idx_imb_dt ON imbalance_prices ("{date_col}", "{time_col}")')
                conn.commit()
                logger.info(f"DB更新が完了しました。 (処理行数: {len(df)}行)")

            self.finished.emit("DB更新が完了しました。")
        except requests.exceptions.RequestException as e:
            logger.error(f"インバランス単価のCSVダウンロード中に通信エラーが発生しました: {str(e)}")
            self.error.emit(f"通信エラー: {str(e)}")
        except (ValueError, pd.errors.ParserError) as e:
            logger.error(f"インバランス単価のCSV解析中にエラーが発生しました: {str(e)}")
            self.error.emit(f"CSV解析エラー: {str(e)}")
        except sqlite3.Error as e:
            logger.error(f"インバランス単価のDB保存中にエラーが発生しました: {str(e)}")
            self.error.emit(f"DB保存エラー: {str(e)}")
        except Exception as e:
            logger.error(f"インバランス単価の更新中に予期せぬエラーが発生しました: {str(e)}", exc_info=True)
            self.error.emit(f"予期せぬエラー: {str(e)}")


class FetchPowerReserveWorker(QThread):
    data_fetched   = Signal(list, list)
    error_occurred = Signal(str)

    def __init__(self, target_date_str):
        super().__init__()
        self.target_date_str = target_date_str

    def run(self):
        with requests.Session() as session:
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest"
            })

            try:
                logger.info(f"OCCTO 電力予備率データ({self.target_date_str})のAPI取得を開始します。")
                params = {"inputDate": self.target_date_str.replace("-", "/")}

                res = session.get(API_OCCTO_RESERVE, params=params, timeout=15)
                res.raise_for_status()

                if "application/json" not in res.headers.get("Content-Type", ""):
                    raise ValueError("APIからの応答がJSON形式ではありません。")

                data = res.json()
                area_list = data.get("todayAreaRsvRateList")
                if not area_list:
                    self.data_fetched.emit([], [])
                    return

                AREA_MAP = {1: "北海道", 2: "東北", 3: "東京", 4: "中部", 5: "北陸", 6: "関西", 7: "中国", 8: "四国", 9: "九州", 10: "沖縄"}
                processed_areas = []

                for a in area_list:
                    cd = int(a.get("areaCd", 99))
                    items = a.get("areaRsvRateItems", [])
                    val_map = {}
                    for i, item in enumerate(items):
                        val = item.get("koikRsvRate")
                        if val is None: val = item.get("areaRsvRate", item.get("rsvRate"))
                        t_time = item.get("targetTime")
                        val_map[t_time if t_time else f"{i // 2:02d}:{(i % 2) * 30:02d}"] = val
                    processed_areas.append({"cd": cd, "val_map": val_map})

                processed_areas.sort(key=lambda x: x["cd"])
                headers = ["時間"] + [AREA_MAP.get(pa["cd"], f"エリア{pa['cd']}") for pa in processed_areas]

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
                logger.error(f"OCCTO APIリクエストエラー: {str(e)}")
                self.error_occurred.emit(f"通信エラーが発生しました: {str(e)}")
            except (ValueError, KeyError, TypeError) as e:
                logger.error(f"OCCTO API応答の解析中にエラーが発生しました: {str(e)}")
                self.error_occurred.emit(f"API応答の解析エラー: {str(e)}")
            except Exception as e:
                logger.error(f"OCCTO データ処理中に予期せぬエラーが発生しました: {str(e)}", exc_info=True)
                self.error_occurred.emit(f"予期せぬエラーが発生しました: {str(e)}")
