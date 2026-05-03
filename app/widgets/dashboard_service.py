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
    imb_result      = Signal(float, str)        # legacy (max_val, max_info)
    imb_card_result = Signal(dict)               # rich payload for new ImbalanceCard
    imb_empty       = Signal()
    jkm_result      = Signal(float, str, float)   # legacy (price, date, pct_dod)
    jkm_card_result = Signal(dict)                # rich payload for new JkmCard
    jkm_empty       = Signal()
    hjks_result = Signal(float, float)
    hjks_card_result = Signal(dict)   # rich payload for new HjksCard
    hjks_empty = Signal()
    spot_today_result     = Signal(list)   # [(area_name, avg, max, min), ...]
    spot_tomorrow_result  = Signal(list)
    spot_yesterday_result = Signal(list)   # 前日 — トレンド計算用
    spot_today_slots_result    = Signal(list)  # [(slot_int, system_price), ...] — 48コマ
    spot_tomorrow_slots_result = Signal(list)  # 同上 (翌日 14:00 頃公開)

    def __init__(self):
        super().__init__()
        # P1-11 — fetch 마다 ThreadPoolExecutor 를 새로 만들면
        # 스레드 생성/소멸 비용이 누적되므로 인스턴스 1 개를 재사용한다.
        # max_workers=4 — fetch_type "all" 시 동시 실행되는 4 개 task 분량.
        self._executor = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="dash-svc"
        )

    def __del__(self):
        try:
            self._executor.shutdown(wait=False)
        except Exception:
            pass

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
            futures = [self._executor.submit(t) for t in tasks]
            for f in as_completed(futures):
                if exc := f.exception():
                    logger.error(f"並行DBフェッチ中にエラー: {exc}", exc_info=True)

    def _fetch_imbalance(self):
        try:
            from app.core.config import load_settings
            today_yyyymmdd = int(datetime.now().strftime("%Y%m%d"))
            with get_db_connection(DB_IMBALANCE) as conn:
                cursor = conn.execute("SELECT name FROM pragma_table_info('imbalance_prices')")
                cols = [r[0] for r in cursor.fetchall()]
                if not cols: return self.imb_empty.emit()
                date_col = validate_column_name(cols[1])

                rows = conn.execute(f'SELECT * FROM imbalance_prices WHERE "{date_col}" = ? OR "{date_col}" = ?',
                                    (today_yyyymmdd, str(today_yyyymmdd))).fetchall()

                if not rows: return self.imb_empty.emit()

            # 데이터 한 번 순회하며 카드용 풀 페이로드 계산
            slots = []                # [(slot_str, max_price_at_slot)] - 48 sparkline
            all_prices = []           # 평균 계산용
            today_max = None
            today_max_slot = ""
            today_max_area = ""
            latest_slot = ""
            latest_price = None
            latest_area = ""

            for row in rows:
                slot = str(row[TIME_COL_IDX])
                slot_max = None
                slot_max_area = ""
                for i in range(YOJO_START_COL_IDX, len(cols)):
                    if (YOJO_START_COL_IDX <= i <= YOJO_END_COL_IDX or i >= FUSOKU_START_COL_IDX) and '変更S' not in cols[i]:
                        val_str = row[i]
                        if val_str:
                            try:
                                v = float(val_str)
                                all_prices.append(v)
                                if slot_max is None or v > slot_max:
                                    slot_max = v
                                    slot_max_area = cols[i]
                                if today_max is None or v > today_max:
                                    today_max = v
                                    today_max_slot = slot
                                    today_max_area = cols[i]
                            except (ValueError, TypeError):
                                pass
                if slot_max is not None:
                    slots.append((slot, slot_max))
                    # "직근" = 데이터가 있는 마지막 슬롯
                    latest_slot = slot
                    latest_price = slot_max
                    latest_area = slot_max_area

            if today_max is None or latest_price is None:
                return self.imb_empty.emit()

            today_avg = sum(all_prices) / len(all_prices) if all_prices else 0.0
            alert_threshold = float(load_settings().get("imbalance_alert", 40.0))
            # 알림 레벨: latest 가 임계값 이상=bad, 절반 이상=warn, 그 외=ok
            if latest_price >= alert_threshold:
                alert_level = "bad"
            elif latest_price >= alert_threshold * 0.5:
                alert_level = "warn"
            else:
                alert_level = "ok"

            # legacy (SummaryCard 시절 호환)
            self.imb_result.emit(
                float(today_max),
                tr("コマ {0} / {1}").format(today_max_slot, tr(today_max_area)),
            )
            # 신규 ImbalanceCard 페이로드
            self.imb_card_result.emit({
                "latest_price":    float(latest_price),
                "latest_slot":     latest_slot,
                "latest_area":     latest_area,
                "today_avg":       float(today_avg),
                "today_max":       float(today_max),
                "today_max_slot":  today_max_slot,
                "today_max_area":  today_max_area,
                "alert_level":     alert_level,
                "alert_threshold": alert_threshold,
                "slots":           slots,  # [(slot_str, max_price)] × N (≤ 48)
            })
        except (sqlite3.Error, ValueError, IndexError) as e:
            logger.warning(f"インバランスDBのクエリ中にエラー: {e}")
            self.imb_empty.emit()
        except Exception as e:
            logger.error(f"インバランスデータの取得中に予期せぬエラー: {e}", exc_info=True)
            self.imb_empty.emit()

    def _fetch_jkm(self):
        try:
            # 1차: 신규 통합 테이블 energy_prices (indicator='jkm')
            from app.core.config import DB_ENERGY
            rows = []
            try:
                with get_db_connection(DB_ENERGY) as conn:
                    rows = conn.execute(
                        "SELECT date, close FROM energy_prices "
                        "WHERE indicator = 'jkm' ORDER BY date DESC LIMIT 30"
                    ).fetchall()
            except sqlite3.OperationalError:
                # 테이블 미생성 — fallback
                rows = []

            # 2차 fallback: 구 jkm_prices
            if not rows:
                with get_db_connection(DB_JKM) as conn:
                    rows = conn.execute(
                        "SELECT date, close FROM jkm_prices ORDER BY date DESC LIMIT 30"
                    ).fetchall()
                if not rows:
                    return self.jkm_empty.emit()

            # 시간 순 (과거 → 최신) 정렬
            asc = list(reversed(rows))
            latest_date, latest_close = asc[-1]

            def _pct(curr, base):
                if base in (None, 0):
                    return None
                return (curr - base) / base * 100.0

            # n 일 전 종가 (인덱스 거리 기준 — 휴일 무시 거래일 단위)
            def _close_n_back(n: int):
                idx = len(asc) - 1 - n
                return asc[idx][1] if idx >= 0 else None

            dod = _pct(latest_close, _close_n_back(1))   # 1 거래일
            wow = _pct(latest_close, _close_n_back(5))   # 5 거래일 ≈ 1 주
            mom = _pct(latest_close, _close_n_back(20))  # 20 거래일 ≈ 1 개월

            # legacy
            self.jkm_result.emit(float(latest_close), str(latest_date), float(dod or 0.0))
            # rich
            self.jkm_card_result.emit({
                "latest":      float(latest_close),
                "latest_date": str(latest_date),
                "dod_pct":     dod,
                "wow_pct":     wow,
                "mom_pct":     mom,
                # 30일 sparkline: [(date_str, close)] (오래된 → 최신)
                "sparkline":   [(str(d), float(c)) for d, c in asc],
            })
        except sqlite3.Error as e:
            logger.warning(f"JKM DBのクエリ中にエラー: {e}")
            self.jkm_empty.emit()
        except Exception as e:
            logger.error(f"JKMデータの取得中に予期せぬエラー: {e}", exc_info=True)
            self.jkm_empty.emit()

    def _fetch_hjks(self):
        try:
            from app.core.config import HJKS_METHODS, HJKS_COLORS
            today_str = datetime.now().strftime("%Y-%m-%d")
            with get_db_connection(DB_HJKS) as conn:
                # 本日のメソッド別合計
                rows = conn.execute(
                    "SELECT method, SUM(operating_kw), SUM(stopped_kw) "
                    "FROM hjks_capacity WHERE date = ? GROUP BY method",
                    (today_str,),
                ).fetchall()
                if not rows:
                    return self.hjks_empty.emit()

                method_map = {m: {"op": 0.0, "st": 0.0} for m in HJKS_METHODS}
                for m, op, st in rows:
                    if m in method_map:
                        method_map[m]["op"] = float(op or 0.0)
                        method_map[m]["st"] = float(st or 0.0)
                total_op = sum(v["op"] for v in method_map.values())
                total_st = sum(v["st"] for v in method_map.values())
                if total_op <= 0:
                    return self.hjks_empty.emit()

                # 7日間のスパークライン (合計 operating_mw)
                spark_rows = conn.execute(
                    "SELECT date, SUM(operating_kw) FROM hjks_capacity "
                    "WHERE date <= ? GROUP BY date "
                    "ORDER BY date DESC LIMIT 7",
                    (today_str,),
                ).fetchall()
                spark = [(d, float(v or 0.0) / 1000.0) for d, v in reversed(spark_rows)]

            methods_payload = [
                {"name": m, "op_mw": method_map[m]["op"] / 1000.0,
                 "color": HJKS_COLORS.get(m, "#9E9E9E")}
                for m in HJKS_METHODS if method_map[m]["op"] > 0
            ]
            # legacy
            self.hjks_result.emit(total_op / 1000.0, total_st / 1000.0)
            # rich
            self.hjks_card_result.emit({
                "date":          today_str,
                "total_op_mw":   total_op / 1000.0,
                "total_st_mw":   total_st / 1000.0,
                "methods":       methods_payload,
                "sparkline":     spark,        # [(date_str, op_mw)]
            })
        except sqlite3.Error as e:
            logger.warning(f"HJKS DBのクエリ中にエラー: {e}")
            self.hjks_empty.emit()
        except Exception as e:
            logger.error(f"HJKSデータの取得中に予期せぬエラー: {e}", exc_info=True)
            self.hjks_empty.emit()

    def _fetch_spot(self):
        from datetime import timedelta
        today     = datetime.now().date()
        tomorrow  = today + timedelta(days=1)
        yesterday = today - timedelta(days=1)
        self.spot_today_result.emit(self._query_spot(today.isoformat()))
        self.spot_tomorrow_result.emit(self._query_spot(tomorrow.isoformat()))
        self.spot_yesterday_result.emit(self._query_spot(yesterday.isoformat()))
        self.spot_today_slots_result.emit(self._query_spot_slots(today.isoformat()))
        self.spot_tomorrow_slots_result.emit(self._query_spot_slots(tomorrow.isoformat()))

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

    def _query_spot_slots(self, date_str: str) -> list:
        """指定日の 48 コマ system_price を時間順に返す。Card sparkline 用。"""
        try:
            with get_db_connection(DB_JEPX_SPOT) as conn:
                rows = conn.execute(
                    "SELECT slot, system_price FROM jepx_spot_prices "
                    "WHERE date=? AND system_price IS NOT NULL ORDER BY slot",
                    (date_str,)
                ).fetchall()
                return [(int(r[0]), float(r[1])) for r in rows]
        except Exception as e:
            logger.warning(f"JEPXスポット 48 コマ取得エラー: {e}")
            return []
