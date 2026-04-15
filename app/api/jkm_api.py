"""
JKM LNG スポット価格 API 通信モジュール (Yahoo Finance)
"""
import yfinance as yf
import logging
import requests
import sqlite3
from PySide6.QtCore import QThread, Signal
from app.api.base import BaseWorker
from app.core.config import JKM_TICKER, DB_JKM
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

class FetchJkmWorker(BaseWorker):
    finished = Signal(int)

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