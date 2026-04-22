import logging
import sqlite3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from PySide6.QtCore import QObject, Signal
from app.core.config import (
    DB_IMBALANCE, DB_HJKS, DB_JKM,
    DB_JEPX_SPOT, JEPX_SPOT_AREAS,
    TIME_COL_IDX, YOJO_START_COL_IDX, YOJO_END_COL_IDX, FUSOKU_START_COL_IDX,
)
from app.core.database import get_db_connection, validate_column_name
from app.core.i18n import tr

logger = logging.getLogger(__name__)


class DashboardDataService(QObject):
    """백그라운드 스레드에 상주하며 DB 커넥션을 캐싱하고 쿼리를 처리하는 서비스"""
    imb_result = Signal(float, str)
    imb_empty = Signal()
    jkm_result = Signal(float, str, float)
    jkm_empty = Signal()
    hjks_result = Signal(float, float)
    hjks_empty = Signal()
    spot_today_result    = Signal(list)   # [(area_name, avg, max, min), ...]
    spot_tomorrow_result = Signal(list)

    def __init__(self):
        super().__init__()

    def fetch_data(self, fetch_type):
        tasks = []
        if fetch_type in ("all", "imbalance"):
            tasks.append(self._fetch_imbalance)
        if fetch_type in ("all", "jkm"):
            tasks.append(self._fetch_jkm)
        if fetch_type in ("all", "hjks"):
            tasks.append(self._fetch_hjks)
        if fetch_type in ("all", "spot"):
            tasks.append(self._fetch_spot)

        if not tasks:
            return
        if len(tasks) == 1:
            tasks[0]()
        else:
            with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
                futures = [executor.submit(t) for t in tasks]
                for f in as_completed(futures):
                    if exc := f.exception():
                        logger.error(f"並行DBフェッチ中にエラー: {exc}", exc_info=True)

    def _fetch_imbalance(self):
        try:
            today_yyyymmdd = int(datetime.now().strftime("%Y%m%d"))
            with get_db_connection(DB_IMBALANCE) as conn:
                cursor = conn.execute("SELECT name FROM pragma_table_info('imbalance_prices')")
                cols = [r[0] for r in cursor.fetchall()]
                if not cols: return self.imb_empty.emit()
                date_col = validate_column_name(cols[1])

                rows = conn.execute(f'SELECT * FROM imbalance_prices WHERE "{date_col}" = ? OR "{date_col}" = ?',
                                    (today_yyyymmdd, str(today_yyyymmdd))).fetchall()

                if not rows: return self.imb_empty.emit()

            max_val = None
            max_col = ""
            max_slot = ""

            for row in rows:
                slot = str(row[TIME_COL_IDX])
                for i in range(YOJO_START_COL_IDX, len(cols)):
                    if (YOJO_START_COL_IDX <= i <= YOJO_END_COL_IDX or i >= FUSOKU_START_COL_IDX) and '変更S' not in cols[i]:
                        val_str = row[i]
                        if val_str:
                            try:
                                v = float(val_str)
                                if max_val is None or v > max_val:
                                    max_val = v
                                    max_col = cols[i]
                                    max_slot = slot
                            except (ValueError, TypeError):
                                pass

            if max_val is not None:
                self.imb_result.emit(float(max_val), tr("コマ {0} / {1}").format(max_slot, tr(max_col)))
            else: self.imb_empty.emit()
        except (sqlite3.Error, ValueError, IndexError) as e:
            logger.warning(f"インバランスDBのクエリ中にエラー: {e}")
            self.imb_empty.emit()
        except Exception as e:
            logger.error(f"インバランスデータの取得中に予期せぬエラー: {e}", exc_info=True)
            self.imb_empty.emit()

    def _fetch_jkm(self):
        try:
            with get_db_connection(DB_JKM) as conn:
                rows = conn.execute("SELECT date, close FROM jkm_prices ORDER BY date DESC LIMIT 2").fetchall()
                if not rows: return self.jkm_empty.emit()
                latest_date, latest_price = rows[0]
                pct = ((latest_price - rows[1][1]) / rows[1][1] * 100) if len(rows) > 1 else 0.0
                self.jkm_result.emit(latest_price, latest_date, pct)
        except sqlite3.Error as e:
            logger.warning(f"JKM DBのクエリ中にエラー: {e}")
            self.jkm_empty.emit()
        except Exception as e:
            logger.error(f"JKMデータの取得中に予期せぬエラー: {e}", exc_info=True)
            self.jkm_empty.emit()

    def _fetch_hjks(self):
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            with get_db_connection(DB_HJKS) as conn:
                row = conn.execute("SELECT SUM(operating_kw), SUM(stopped_kw) FROM hjks_capacity WHERE date = ?", (today_str,)).fetchone()
                if not row or row[0] is None: return self.hjks_empty.emit()
                self.hjks_result.emit(float(row[0]) / 1000.0, float(row[1]) / 1000.0)
        except sqlite3.Error as e:
            logger.warning(f"HJKS DBのクエリ中にエラー: {e}")
            self.hjks_empty.emit()
        except Exception as e:
            logger.error(f"HJKSデータの取得中に予期せぬエラー: {e}", exc_info=True)
            self.hjks_empty.emit()

    def _fetch_spot(self):
        from datetime import timedelta
        today    = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        self.spot_today_result.emit(self._query_spot(today.isoformat()))
        self.spot_tomorrow_result.emit(self._query_spot(tomorrow.isoformat()))

    def _query_spot(self, date_str: str) -> list:
        try:
            with get_db_connection(DB_JEPX_SPOT) as conn:
                result = []
                for name, col in JEPX_SPOT_AREAS:
                    safe_col = validate_column_name(col)
                    row = conn.execute(
                        f"SELECT AVG({safe_col}), MAX({safe_col}), MIN({safe_col})"
                        f" FROM jepx_spot_prices WHERE date=?",
                        (date_str,)
                    ).fetchone()
                    if row and row[0] is not None:
                        result.append((name, float(row[0]), float(row[1]), float(row[2])))
                return result
        except Exception as e:
            logger.warning(f"JEPXスポット取得エラー: {e}")
            return []
