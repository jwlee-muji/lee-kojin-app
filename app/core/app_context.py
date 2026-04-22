"""
アプリ現在データコンテキスト — AI チャット RAG 用
各ウィジェットが取得した最新データをメモリにキャッシュし、
AI リクエスト時にシステムプロンプトへ注入する。
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# OCCTO エリアDBカラム → 日本語名
_RESERVE_AREA_NAMES = {
    "hokkaido": "北海道", "tohoku": "東北",   "tokyo":   "東京",
    "chubu":    "中部",   "hokuriku": "北陸", "kansai":  "関西",
    "chugoku":  "中国",   "shikoku":  "四国",  "kyushu":  "九州",
    "okinawa":  "沖縄",
}


class _AppContextStore:
    def __init__(self):
        self._occto_fallback: tuple | None = None
        from app.core.events import bus
        bus.occto_updated.connect(self._on_occto)

    def _on_occto(self, time_str: str, area_str: str, min_val: float):
        self._occto_fallback = (time_str, area_str, min_val)

    def get_context(self) -> str:
        """現在のアプリデータを自然言語テキストとして返す。データがなければ空文字。"""
        now = datetime.now()
        lines = [
            "【現在のLEE電力モニターデータ】",
            f"現在時刻: {now.strftime('%Y年%m月%d日 %H:%M')}",
        ]

        lines.extend(self._fetch_jepx_spot(now))
        lines.extend(self._fetch_imbalance(now))
        lines.extend(self._fetch_jkm())
        lines.extend(self._fetch_hjks(now))
        lines.extend(self._fetch_power_reserve(now))
        lines.extend(self._fetch_weather(now))

        if len(lines) <= 2:
            return ""

        lines.append("【以上がアプリの最新取得データです】")
        return "\n".join(lines)

    # ── 既存 DB フェッチ ─────────────────────────────────────────────────────

    def _fetch_jepx_spot(self, now: datetime) -> list[str]:
        try:
            from app.core.config import DB_JEPX_SPOT
            from app.core.database import get_db_connection
            today = now.strftime("%Y-%m-%d")
            with get_db_connection(DB_JEPX_SPOT) as conn:
                row = conn.execute(
                    "SELECT AVG(system_price), AVG(tokyo), AVG(kansai) "
                    "FROM jepx_spot_prices WHERE date = ?",
                    (today,)
                ).fetchone()
            if row and row[0] is not None:
                sys_s = f"{row[0]:.2f}"
                tok_s = f"{row[1]:.2f}" if row[1] is not None else "—"
                kan_s = f"{row[2]:.2f}" if row[2] is not None else "—"
                return [f"JEPXスポット単価 (本日平均): システム={sys_s} / 東京={tok_s} / 関西={kan_s} 円/kWh"]
        except Exception as e:
            logger.debug(f"app_context jepx: {e}")
        return []

    def _fetch_imbalance(self, now: datetime) -> list[str]:
        try:
            from app.core.config import DB_IMBALANCE, TIME_COL_IDX, YOJO_START_COL_IDX, YOJO_END_COL_IDX, FUSOKU_START_COL_IDX
            from app.core.database import get_db_connection, validate_column_name
            today = int(now.strftime("%Y%m%d"))
            with get_db_connection(DB_IMBALANCE) as conn:
                cursor = conn.execute("SELECT name FROM pragma_table_info('imbalance_prices')")
                cols = [r[0] for r in cursor.fetchall()]
                if not cols:
                    return []
                date_col = validate_column_name(cols[1])
                rows = conn.execute(
                    f'SELECT * FROM imbalance_prices WHERE "{date_col}" = ? OR "{date_col}" = ?',
                    (today, str(today))
                ).fetchall()
            max_val = None
            for row in rows:
                for i in range(YOJO_START_COL_IDX, len(cols)):
                    if (YOJO_START_COL_IDX <= i <= YOJO_END_COL_IDX or
                            i >= FUSOKU_START_COL_IDX) and '変更S' not in cols[i]:
                        try:
                            v = float(row[i] or 0)
                            if max_val is None or v > max_val:
                                max_val = v
                        except (ValueError, TypeError):
                            pass
            if max_val is not None:
                return [f"インバランス最大単価 (本日): {max_val:.1f} 円/kWh"]
        except Exception as e:
            logger.debug(f"app_context imbalance: {e}")
        return []

    def _fetch_jkm(self) -> list[str]:
        try:
            from app.core.config import DB_JKM
            from app.core.database import get_db_connection
            with get_db_connection(DB_JKM) as conn:
                row = conn.execute(
                    "SELECT date, close FROM jkm_prices ORDER BY date DESC LIMIT 1"
                ).fetchone()
            if row:
                return [f"JKM LNG最新価格: {row[1]:.3f} USD/MMBtu ({row[0]})"]
        except Exception as e:
            logger.debug(f"app_context jkm: {e}")
        return []

    def _fetch_hjks(self, now: datetime) -> list[str]:
        try:
            from app.core.config import DB_HJKS
            from app.core.database import get_db_connection
            today_str = now.strftime("%Y-%m-%d")
            with get_db_connection(DB_HJKS) as conn:
                row = conn.execute(
                    "SELECT SUM(operating_kw), SUM(stopped_kw) FROM hjks_capacity WHERE date=?",
                    (today_str,)
                ).fetchone()
            if row and row[0]:
                ope = float(row[0]) / 1000.0
                stp = float(row[1]) / 1000.0
                return [f"発電稼働容量 (本日): {ope:,.0f} MW (停止: {stp:,.0f} MW)"]
        except Exception as e:
            logger.debug(f"app_context hjks: {e}")
        return []

    # ── 新規 DB フェッチ ─────────────────────────────────────────────────────

    def _fetch_power_reserve(self, now: datetime) -> list[str]:
        try:
            from app.core.config import DB_POWER_RESERVE
            from app.core.database import get_db_connection
            today = now.strftime("%Y-%m-%d")
            cols = list(_RESERVE_AREA_NAMES.keys())
            col_min_sql = ", ".join(f"MIN({c})" for c in cols)

            with get_db_connection(DB_POWER_RESERVE) as conn:
                # DB に保存されている全日付の最低予備率サマリー (新しい順 30日分)
                summary_rows = conn.execute(
                    f"SELECT date, {col_min_sql} FROM power_reserve "
                    "GROUP BY date ORDER BY date DESC LIMIT 30"
                ).fetchall()
                # 今日の詳細 (時刻別・警戒エリア抽出用)
                today_rows = conn.execute(
                    f"SELECT time, {', '.join(cols)} FROM power_reserve "
                    "WHERE date=? ORDER BY time",
                    (today,)
                ).fetchall()

            if not summary_rows:
                if self._occto_fallback:
                    t, a, v = self._occto_fallback
                    return [f"電力予備率 最低: {v:.1f}% ({t} / {a})"]
                return []

            result = []

            # 日別サマリー
            date_lines = []
            for row in summary_rows:
                date_str = row[0]
                vals = [(row[i + 1], _RESERVE_AREA_NAMES[cols[i]])
                        for i in range(len(cols)) if row[i + 1] is not None]
                if not vals:
                    continue
                min_val, min_area = min(vals, key=lambda x: x[0])
                date_lines.append(f"  {date_str}: 最低 {min_val:.1f}% ({min_area})")
            if date_lines:
                result.append(f"電力予備率 日別最低値 (直近{len(date_lines)}日):")
                result.extend(date_lines)

            # 今日の警戒エリア (10%未満・現在時刻以降)
            if today_rows:
                warn_threshold = 10.0
                current_min = now.hour * 60 + now.minute
                warn_areas: list[str] = []
                for row in today_rows:
                    time_str = row[0]
                    try:
                        h, m = time_str.split(":")
                        slot_min = int(h) * 60 + int(m)
                    except (ValueError, AttributeError):
                        slot_min = -1
                    for ci, col in enumerate(cols):
                        val = row[ci + 1]
                        if val is not None and slot_min >= current_min and val < warn_threshold:
                            label = f"{_RESERVE_AREA_NAMES[col]}({time_str}:{val:.1f}%)"
                            if label not in warn_areas:
                                warn_areas.append(label)
                if warn_areas:
                    result.append(f"本日予備率警戒 ({warn_threshold}%未満): {', '.join(warn_areas[:6])}")

            return result
        except Exception as e:
            logger.debug(f"app_context power_reserve: {e}")
        return []

    def _fetch_weather(self, now: datetime) -> list[str]:
        try:
            from app.core.config import DB_WEATHER
            from app.core.database import get_db_connection
            from datetime import timedelta

            with get_db_connection(DB_WEATHER) as conn:
                # 各 date について、最も近い fetched_date (同日 or 直近) のデータを使用
                # fetched_date <= date の中で最新のもの = 実測に最も近い予報
                rows = conn.execute(
                    """
                    SELECT w.region, w.date, w.weather_code,
                           w.temp_max, w.temp_min, w.precip_prob
                    FROM weather_forecast w
                    INNER JOIN (
                        SELECT date, region, MAX(fetched_date) AS best_fetch
                        FROM weather_forecast
                        WHERE fetched_date <= date
                        GROUP BY date, region
                    ) best ON w.date = best.date
                          AND w.region = best.region
                          AND w.fetched_date = best.best_fetch
                    ORDER BY w.date DESC, w.region
                    LIMIT 200
                    """
                ).fetchall()

            if not rows:
                return []

            from app.widgets.weather import get_weather_info

            # 日付ごとに地域をまとめる
            from collections import defaultdict
            by_date: dict[str, list[str]] = defaultdict(list)
            for region, date, wcode, t_max, t_min, pop in rows:
                w_text, _ = get_weather_info(wcode or 0)
                t_max_s = f"{t_max:.0f}℃" if t_max is not None else "—"
                t_min_s = f"{t_min:.0f}℃" if t_min is not None else "—"
                pop_s   = f"☔{pop}%" if pop is not None else ""
                by_date[date].append(f"    {region}: {w_text} {t_max_s}/{t_min_s} {pop_s}".rstrip())

            result = []
            today_str = now.strftime("%Y-%m-%d")
            for date in sorted(by_date.keys()):
                label = "本日" if date == today_str else date
                result.append(f"  [{label}]")
                result.extend(by_date[date])
            if result:
                result.insert(0, "天気予報 (DB保存分):")
            return result
        except Exception as e:
            logger.debug(f"app_context weather: {e}")
        return []


_store = _AppContextStore()


def get_current_context() -> str:
    """AI に渡す現在のアプリデータコンテキスト文字列を返す。"""
    return _store.get_context()
