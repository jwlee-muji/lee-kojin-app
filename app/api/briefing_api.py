"""
AI ブリーフィング生成モジュール
対応期間: daily / weekly / monthly / next_month
"""
import json
import logging
import sqlite3
import urllib.request
import urllib.error
from calendar import monthrange
from collections import defaultdict
from datetime import datetime, timedelta

from PySide6.QtCore import Signal
from app.api.base import BaseWorker, HTTP_TIMEOUT
from app.api.ai_api import (
    get_all_gemini_keys, get_builtin_groq_key,
    GEMINI_API_URL, GEMINI_LITE_MODEL, GEMINI_DEFAULT_MODEL,
    GROQ_API_URL, GROQ_DEFAULT_MODEL,
    RateLimitError, ServiceUnavailableError,
)

logger = logging.getLogger(__name__)

PERIOD_LABELS = {
    "daily":      {"ja": "デイリーブリーフィング",    "ko": "데일리 브리핑",  "en": "Daily Briefing",      "zh": "每日简报"},
    "weekly":     {"ja": "ウィークリーブリーフィング","ko": "주간 브리핑",    "en": "Weekly Briefing",     "zh": "每周简报"},
    "monthly":    {"ja": "マンスリーブリーフィング",  "ko": "이번달 브리핑",  "en": "Monthly Briefing",    "zh": "本月简报"},
    "next_month": {"ja": "来月ブリーフィング",        "ko": "다음달 브리핑",  "en": "Next Month Briefing", "zh": "下月简报"},
}

LANG_INSTRUCTIONS = {
    "ja": "日本語でブリーフィングを作成してください。",
    "ko": "한국어로 브리핑을 작성해 주세요。",
    "en": "Please write the briefing in English.",
    "zh": "请用中文撰写简报。",
}

SECTION_LABELS = {
    "ja": ("## 過去分析", "## 現在状況", "## 将来予測"),
    "ko": ("## 과거 분석", "## 현재 상황", "## 미래 예측"),
    "en": ("## Past Analysis", "## Current Situation", "## Future Outlook"),
    "zh": ("## 历史分析", "## 当前状况", "## 未来展望"),
}

_AREA_COLS  = ["hokkaido","tohoku","tokyo","chubu","hokuriku","kansai","chugoku","shikoku","kyushu"]
_AREA_NAMES = {"hokkaido":"北海道","tohoku":"東北","tokyo":"東京","chubu":"中部",
               "hokuriku":"北陸","kansai":"関西","chugoku":"中国","shikoku":"四国","kyushu":"九州"}


# ── 重み計算 ───────────────────────────────────────────────────────────────────

def calc_weights(period: str, now: datetime) -> tuple[int, int, int]:
    """(過去%, 現在%, 将来%) を返す。progress 0.0 = 期間先頭, 1.0 = 期間末尾。"""
    if period == "next_month":
        return 5, 15, 80

    if period == "daily":
        progress = now.hour / 23.0
    elif period == "weekly":
        progress = now.weekday() / 6.0
    elif period == "monthly":
        days_in_month = monthrange(now.year, now.month)[1]
        progress = (now.day - 1) / max(days_in_month - 1, 1)
    else:
        progress = 0.5

    progress = max(0.0, min(1.0, progress))
    past    = round(10 + progress * 60)
    future  = round(70 - progress * 60)
    current = 100 - past - future
    return past, current, future


# ── 期間ヘルパー ──────────────────────────────────────────────────────────────

def _period_range(period: str, now: datetime) -> tuple[datetime, datetime]:
    if period == "daily":
        return now.replace(hour=0, minute=0, second=0, microsecond=0), now
    elif period == "weekly":
        monday = now - timedelta(days=now.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0), now
    elif period == "monthly":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now
    elif period == "next_month":
        y, m = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
        return datetime(y, m, 1), datetime(y, m, monthrange(y, m)[1], 23, 59)
    return now, now


def _hist_start(period: str, now: datetime) -> str:
    delta = {
        "daily":      timedelta(days=7),
        "weekly":     timedelta(weeks=4),
        "monthly":    timedelta(days=90),
        "next_month": timedelta(days=365),
    }.get(period, timedelta(days=30))
    return (now - delta).strftime("%Y-%m-%d")


# ── データカバレッジチェック ───────────────────────────────────────────────────

def _coverage_window(period: str, now: datetime) -> tuple[str, int]:
    """(check_start_date_str, expected_days) を返す。"""
    if period == "daily":
        return now.strftime("%Y-%m-%d"), 1
    elif period == "weekly":
        monday = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        return monday, now.weekday() + 1
    elif period == "monthly":
        return now.replace(day=1).strftime("%Y-%m-%d"), now.day
    elif period == "next_month":
        nm = (now.month % 12) + 1
        y  = now.year + 1 if now.month == 12 else now.year
        return (now - timedelta(days=365)).strftime("%Y-%m-%d"), monthrange(y, nm)[1]
    return now.strftime("%Y-%m-%d"), 1


def check_coverage(period: str, now: datetime) -> dict[str, str]:
    """各 DB のカバレッジを確認し、不足している場合の警告テキストを返す。
    daily ブリーフィングはチェックをスキップ (当日データは随時更新されるため)。"""
    if period == "daily":
        return {}

    warnings: dict[str, str] = {}
    check_start, expected = _coverage_window(period, now)
    threshold = max(1, int(expected * 0.5))

    try:
        from app.core.config import DB_POWER_RESERVE, DB_WEATHER, DB_HJKS, DB_IMBALANCE
        from app.core.database import get_db_connection, validate_column_name

        # 電力予備率
        try:
            if not DB_POWER_RESERVE.exists():
                warnings["電力予備率"] = "DBなし — 「電力予備率」タブでデータを取得してください"
            else:
                with get_db_connection(DB_POWER_RESERVE) as conn:
                    if period == "next_month":
                        nm = (now.month % 12) + 1
                        count = conn.execute(
                            "SELECT COUNT(DISTINCT date) FROM power_reserve "
                            "WHERE strftime('%m', date) = ?", (f"{nm:02d}",)
                        ).fetchone()[0]
                    else:
                        count = conn.execute(
                            "SELECT COUNT(DISTINCT date) FROM power_reserve WHERE date >= ?",
                            (check_start,)
                        ).fetchone()[0]
                if count < threshold:
                    warnings["電力予備率"] = f"データ不足 ({count}/{expected}日) — 「電力予備率」タブで更新してください"
        except Exception as e:
            logger.debug(f"coverage power_reserve: {e}")

        # 天気予報
        try:
            if not DB_WEATHER.exists():
                warnings["天気予報"] = "DBなし — 「全国天気」タブでデータを取得してください"
            else:
                with get_db_connection(DB_WEATHER) as conn:
                    if period == "next_month":
                        nm = (now.month % 12) + 1
                        count = conn.execute(
                            "SELECT COUNT(DISTINCT date) FROM weather_forecast "
                            "WHERE strftime('%m', date) = ?", (f"{nm:02d}",)
                        ).fetchone()[0]
                    else:
                        count = conn.execute(
                            "SELECT COUNT(DISTINCT date) FROM weather_forecast "
                            "WHERE fetched_date <= date AND date >= ?", (check_start,)
                        ).fetchone()[0]
                if count < threshold:
                    warnings["天気予報"] = f"データ不足 ({count}/{expected}日) — 「全国天気」タブで更新してください"
        except Exception as e:
            logger.debug(f"coverage weather: {e}")

        # 発電稼働状況
        try:
            if not DB_HJKS.exists():
                warnings["発電稼働状況"] = "DBなし — 「発電稼働状況」タブでデータを取得してください"
            else:
                wd_threshold = max(1, int(threshold * 5 / 7))
                with get_db_connection(DB_HJKS) as conn:
                    if period == "next_month":
                        nm = (now.month % 12) + 1
                        count = conn.execute(
                            "SELECT COUNT(DISTINCT date) FROM hjks_capacity "
                            "WHERE strftime('%m', date) = ?", (f"{nm:02d}",)
                        ).fetchone()[0]
                    else:
                        count = conn.execute(
                            "SELECT COUNT(DISTINCT date) FROM hjks_capacity WHERE date >= ?",
                            (check_start,)
                        ).fetchone()[0]
                if count < wd_threshold:
                    warnings["発電稼働状況"] = f"データ不足 ({count}/{wd_threshold}日) — 「発電稼働状況」タブで更新してください"
        except Exception as e:
            logger.debug(f"coverage hjks: {e}")

        # JEPX スポット
        try:
            from app.core.config import DB_JEPX_SPOT
            if not DB_JEPX_SPOT.exists():
                warnings["JEPXスポット"] = "DBなし — 「スポット市場」タブでデータを取得してください"
            else:
                with get_db_connection(DB_JEPX_SPOT) as conn:
                    if period == "next_month":
                        nm = (now.month % 12) + 1
                        count = conn.execute(
                            "SELECT COUNT(DISTINCT date) FROM jepx_spot_prices "
                            "WHERE strftime('%m', date) = ?", (f"{nm:02d}",)
                        ).fetchone()[0]
                    else:
                        count = conn.execute(
                            "SELECT COUNT(DISTINCT date) FROM jepx_spot_prices WHERE date >= ?",
                            (check_start,)
                        ).fetchone()[0]
                if count < threshold:
                    warnings["JEPXスポット"] = f"データ不足 ({count}/{expected}日) — 「スポット市場」タブで更新してください"
        except Exception as e:
            logger.debug(f"coverage jepx: {e}")

        # インバランス
        try:
            if not DB_IMBALANCE.exists():
                warnings["インバランス単価"] = "DBなし — 「インバランス」タブでデータを取得してください"
            else:
                with get_db_connection(DB_IMBALANCE) as conn:
                    col_meta = conn.execute(
                        "SELECT name FROM pragma_table_info('imbalance_prices')"
                    ).fetchall()
                    if col_meta and len(col_meta) >= 2:
                        cols = [r[0] for r in col_meta]
                        date_col = validate_column_name(cols[1])
                        if period == "next_month":
                            nm = (now.month % 12) + 1
                            count = conn.execute(
                                f'SELECT COUNT(DISTINCT "{date_col}") FROM imbalance_prices '
                                f'WHERE substr(CAST("{date_col}" AS TEXT), 5, 2) = ?',
                                (f"{nm:02d}",)
                            ).fetchone()[0]
                        else:
                            threshold_int = int(check_start.replace("-", ""))
                            count = conn.execute(
                                f'SELECT COUNT(DISTINCT "{date_col}") FROM imbalance_prices '
                                f'WHERE CAST("{date_col}" AS INTEGER) >= ?',
                                (threshold_int,)
                            ).fetchone()[0]
                        if count < threshold:
                            warnings["インバランス単価"] = f"データ不足 ({count}/{expected}日) — 「インバランス」タブで更新してください"
        except Exception as e:
            logger.debug(f"coverage imbalance: {e}")

    except ImportError as e:
        logger.debug(f"coverage import error: {e}")

    return warnings


# ── JKM 自動プリフェッチ ──────────────────────────────────────────────────────

def prefetch_jkm_if_needed(period: str, now: datetime) -> str:
    """JKM データが不足していれば yfinance から自動取得してDBに保存する。
    BriefingWorker スレッド内で呼ぶこと (ブロッキング処理)。
    成功・不要時は空文字、失敗時はエラーメッセージを返す。"""
    if period == "daily":
        return ""
    try:
        from app.core.config import DB_JKM, JKM_TICKER
        from app.core.database import get_db_connection
        from app.api.market.jkm import _save_jkm, _to_float

        check_start, expected = _coverage_window(period, now)
        threshold = max(1, int(expected * 5 / 7 * 0.5))

        if DB_JKM.exists():
            with get_db_connection(DB_JKM) as conn:
                count = conn.execute(
                    "SELECT COUNT(DISTINCT date) FROM jkm_prices WHERE date >= ?",
                    (check_start,)
                ).fetchone()[0]
            if count >= threshold:
                return ""  # 十分なデータあり

        import yfinance as yf
        hist = yf.Ticker(JKM_TICKER).history(period="2y")
        if hist.empty:
            return "JKM自動取得失敗 (データなし)"

        rows = [
            (
                dt.strftime("%Y-%m-%d"),
                _to_float(row.get("Open")),
                _to_float(row.get("High")),
                _to_float(row.get("Low")),
                float(row["Close"]),
            )
            for dt, row in hist.iterrows()
        ]
        _save_jkm(rows)
        logger.info(f"JKM 自動プリフェッチ完了: {len(rows)}件")
        return ""
    except Exception as e:
        logger.warning(f"JKM prefetch: {e}")
        return f"JKM自動取得失敗: {e}"


# ── データ収集 ────────────────────────────────────────────────────────────────

def collect_briefing_data(period: str, now: datetime) -> dict:
    """全 DB から指定期間の参考データを収集して返す。"""
    try:
        from app.core.config import (
            DB_IMBALANCE, DB_JKM, DB_HJKS, DB_POWER_RESERVE, DB_WEATHER,
            YOJO_START_COL_IDX, YOJO_END_COL_IDX, FUSOKU_START_COL_IDX,
        )
        from app.core.database import get_db_connection, validate_column_name
    except ImportError as e:
        logger.error(f"briefing import error: {e}")
        return {}

    hist = _hist_start(period, now)
    data: dict = {}

    # ── JEPX スポット ──────────────────────────────────────────────────────────
    try:
        from app.core.config import DB_JEPX_SPOT
        if DB_JEPX_SPOT.exists():
            with get_db_connection(DB_JEPX_SPOT) as conn:
                if period == "next_month":
                    nm = (now.month % 12) + 1
                    jepx_rows = conn.execute(
                        "SELECT date, AVG(system_price), AVG(tokyo), AVG(kansai) "
                        "FROM jepx_spot_prices WHERE strftime('%m', date) = ? "
                        "GROUP BY date ORDER BY date DESC LIMIT 60",
                        (f"{nm:02d}",)
                    ).fetchall()
                else:
                    jepx_rows = conn.execute(
                        "SELECT date, AVG(system_price), AVG(tokyo), AVG(kansai) "
                        "FROM jepx_spot_prices WHERE date >= ? "
                        "GROUP BY date ORDER BY date",
                        (hist,)
                    ).fetchall()
            data["jepx"] = jepx_rows
    except Exception as e:
        logger.debug(f"briefing jepx: {e}")

    # ── JKM ──────────────────────────────────────────────────────────────────
    try:
        if DB_JKM.exists():
            with get_db_connection(DB_JKM) as conn:
                rows = conn.execute(
                    "SELECT date, close FROM jkm_prices WHERE date >= ? ORDER BY date",
                    (hist,)
                ).fetchall()
            data["jkm"] = rows
    except Exception as e:
        logger.debug(f"briefing jkm: {e}")

    # ── HJKS ──────────────────────────────────────────────────────────────────
    try:
        if DB_HJKS.exists():
            with get_db_connection(DB_HJKS) as conn:
                rows = conn.execute(
                    "SELECT date, SUM(operating_kw), SUM(stopped_kw) FROM hjks_capacity "
                    "WHERE date >= ? GROUP BY date ORDER BY date",
                    (hist,)
                ).fetchall()
            data["hjks"] = rows
    except Exception as e:
        logger.debug(f"briefing hjks: {e}")

    # ── 電力予備率 ──────────────────────────────────────────────────────────────
    try:
        if DB_POWER_RESERVE.exists():
            col_sql = ", ".join(f"MIN({c})" for c in _AREA_COLS)
            with get_db_connection(DB_POWER_RESERVE) as conn:
                rows = conn.execute(
                    f"SELECT date, {col_sql} FROM power_reserve "
                    "WHERE date >= ? GROUP BY date ORDER BY date",
                    (hist,)
                ).fetchall()
            data["power_reserve"] = rows
    except Exception as e:
        logger.debug(f"briefing power_reserve: {e}")

    # ── インバランス ─────────────────────────────────────────────────────────────
    try:
        if DB_IMBALANCE.exists():
            with get_db_connection(DB_IMBALANCE) as conn:
                col_meta = conn.execute(
                    "SELECT name FROM pragma_table_info('imbalance_prices')"
                ).fetchall()
                if col_meta and len(col_meta) >= 2:
                    cols = [r[0] for r in col_meta]
                    date_col = validate_column_name(cols[1])
                    threshold_int = int(hist.replace("-", ""))
                    rows = conn.execute(
                        f'SELECT * FROM imbalance_prices '
                        f'WHERE CAST("{date_col}" AS INTEGER) >= ? ORDER BY "{date_col}"',
                        (threshold_int,)
                    ).fetchall()
                    by_date: dict[str, float] = {}
                    for row in rows:
                        date_key = str(row[1])[:8]
                        for i in range(YOJO_START_COL_IDX, len(cols)):
                            if (YOJO_START_COL_IDX <= i <= YOJO_END_COL_IDX or
                                    i >= FUSOKU_START_COL_IDX) and '変更S' not in cols[i]:
                                try:
                                    v = float(row[i] or 0)
                                    if v > by_date.get(date_key, 0):
                                        by_date[date_key] = v
                                except (ValueError, TypeError):
                                    pass
                    data["imbalance"] = sorted(by_date.items())
    except Exception as e:
        logger.debug(f"briefing imbalance: {e}")

    # ── Gmail 未読メール (cache 기반, network 0) ────────────────────────────
    # 시장 상황과 직접 무관하지만 사용자가 받은 직근 미읽음 메일 — 거래처 / 알림
    # 메일 등 brief 와 함께 한눈에 파악할 수 있도록 포함.
    try:
        from app.api.google.gmail_cache import _db_path as _gmail_db, _ensure_db as _gmail_init
        _gmail_init()
        with sqlite3.connect(_gmail_db()) as gc:
            rows = gc.execute(
                "SELECT subject, from_addr, snippet, date FROM mail_metadata "
                "WHERE is_unread = 1 ORDER BY cached_at DESC LIMIT 15"
            ).fetchall()
        if rows:
            data["gmail_unread"] = rows
    except Exception as e:
        logger.debug(f"briefing gmail: {e}")

    # ── システム通知 (notifications.db) ──────────────────────────────────────
    try:
        from app.widgets.notification import list_notifications
        cutoff = (now - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00")
        items = [
            n for n in list_notifications()
            if (n.get("timestamp") or "") >= cutoff
        ]
        if items:
            data["notifications"] = items
    except Exception as e:
        logger.debug(f"briefing notifications: {e}")

    # ── Google Calendar 직근 예정 (live API, optional) ───────────────────────
    try:
        from app.api.google.auth import is_authenticated, build_service
        if is_authenticated():
            svc = build_service("calendar", "v3")
            time_min = now.isoformat() + "Z"
            time_max = (now + timedelta(days=7)).isoformat() + "Z"
            result = svc.events().list(
                calendarId="primary",
                timeMin=time_min, timeMax=time_max,
                maxResults=15, singleEvents=True, orderBy="startTime",
            ).execute()
            events = result.get("items", [])
            if events:
                data["calendar"] = events
    except Exception as e:
        logger.debug(f"briefing calendar: {e}")

    # ── 天気 ──────────────────────────────────────────────────────────────────
    try:
        if DB_WEATHER.exists():
            with get_db_connection(DB_WEATHER) as conn:
                if period == "next_month":
                    nm = (now.month % 12) + 1
                    weather_rows = conn.execute(
                        "SELECT region, date, weather_code, temp_max, temp_min, precip_prob "
                        "FROM weather_forecast WHERE strftime('%m', date) = ? "
                        "ORDER BY date DESC LIMIT 500",
                        (f"{nm:02d}",)
                    ).fetchall()
                else:
                    weather_rows = conn.execute(
                        """SELECT w.region, w.date, w.weather_code,
                                  w.temp_max, w.temp_min, w.precip_prob
                           FROM weather_forecast w
                           INNER JOIN (
                               SELECT date, region, MAX(fetched_date) AS best_fetch
                               FROM weather_forecast
                               WHERE fetched_date <= date AND date >= ?
                               GROUP BY date, region
                           ) best ON w.date = best.date
                                 AND w.region = best.region
                                 AND w.fetched_date = best.best_fetch
                           ORDER BY w.date DESC LIMIT 300""",
                        (hist,)
                    ).fetchall()
            data["weather"] = weather_rows
    except Exception as e:
        logger.debug(f"briefing weather: {e}")

    return data


# ── プロンプト構築 ────────────────────────────────────────────────────────────

def _format_data_text(period: str, data: dict, now: datetime) -> str:
    lines = []

    if data.get("jepx"):
        rows = data["jepx"]
        if period == "next_month":
            lines.append("[JEPXスポット価格 (来月同月の過去平均 円/kWh)]")
        else:
            lines.append("[JEPXスポット価格 (日平均 円/kWh)]")
        for row in rows[-14:]:
            date_str, sys_avg, tok_avg, kan_avg = row
            sys_s = f"{sys_avg:.2f}" if sys_avg is not None else "—"
            tok_s = f"{tok_avg:.2f}" if tok_avg is not None else "—"
            kan_s = f"{kan_avg:.2f}" if kan_avg is not None else "—"
            lines.append(
                f"  {date_str}: システム={sys_s} / 東京={tok_s} / 関西={kan_s}"
            )
        if len(rows) > 1 and period != "next_month":
            sys_vals = [r[1] for r in rows if r[1] is not None]
            if sys_vals:
                lines.append(
                    f"  期間レンジ: {min(sys_vals):.2f} ~ {max(sys_vals):.2f} 円/kWh"
                )

    if data.get("jkm"):
        rows = data["jkm"]
        latest = rows[-1]
        lines.append("\n[JKM LNG価格]")
        lines.append(f"  最新: {latest[1]:.3f} USD/MMBtu ({latest[0]})")
        if len(rows) > 1:
            oldest = rows[0]
            change = latest[1] - oldest[1]
            lines.append(f"  期間変化: {change:+.3f} USD ({oldest[0]} → {latest[0]})")
            vals = [r[1] for r in rows if r[1] is not None]
            if vals:
                lines.append(f"  期間レンジ: {min(vals):.3f} ~ {max(vals):.3f}")

    if data.get("hjks"):
        lines.append("\n[発電稼働状況]")
        for date_str, op_kw, st_kw in data["hjks"][-10:]:
            op_mw = (op_kw or 0) / 1000.0
            st_mw = (st_kw or 0) / 1000.0
            lines.append(f"  {date_str}: 稼働 {op_mw:,.0f}MW / 停止 {st_mw:,.0f}MW")

    if data.get("power_reserve"):
        lines.append("\n[電力予備率 (日別最低値)]")
        for row in data["power_reserve"][-14:]:
            date_str = row[0]
            vals = [(row[i + 1], _AREA_NAMES.get(_AREA_COLS[i], _AREA_COLS[i]))
                    for i in range(len(_AREA_COLS)) if row[i + 1] is not None]
            if vals:
                min_val, min_area = min(vals, key=lambda x: x[0])
                lines.append(f"  {date_str}: 最低 {min_val:.1f}% ({min_area})")

    if data.get("imbalance"):
        lines.append("\n[インバランス単価 (日別最大値)]")
        for date_key, max_v in data["imbalance"][-14:]:
            d = f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:]}"
            lines.append(f"  {d}: {max_v:.1f} 円/kWh")

    if data.get("weather"):
        if period == "next_month":
            lines.append("\n[来月同月の過去気象データ (季節パターン参考)]")
        else:
            lines.append("\n[天気予報・実績]")
        by_date: dict[str, list[str]] = defaultdict(list)
        for region, date_str, wcode, t_max, t_min, pop in data["weather"]:
            t_max_s = f"{t_max:.0f}℃" if t_max is not None else "—"
            t_min_s = f"{t_min:.0f}℃" if t_min is not None else "—"
            pop_s   = f"☔{pop}%" if pop is not None else ""
            by_date[date_str].append(f"{region}: {t_max_s}/{t_min_s} {pop_s}".strip())
        limit = 7 if period == "next_month" else 10
        for date_str in sorted(by_date.keys())[-limit:]:
            lines.append(f"  [{date_str}]")
            for item in by_date[date_str][:5]:
                lines.append(f"    {item}")

    if data.get("calendar"):
        lines.append("\n[Google Calendar 直近の予定 (7日間)]")
        for ev in data["calendar"][:10]:
            start = ev.get("start", {}) or {}
            when = start.get("dateTime") or start.get("date") or ""
            title = (ev.get("summary") or "(無題)")[:60]
            lines.append(f"  {when[:16]}  {title}")

    if data.get("notifications"):
        from collections import Counter
        level_count = Counter(n.get("level", "info") for n in data["notifications"])
        summary = ", ".join(
            f"{lv}={cnt}" for lv, cnt in sorted(level_count.items())
        )
        lines.append(f"\n[システム通知 (直近7日: {summary})]")
        for n in data["notifications"][:6]:
            ts = (n.get("timestamp") or "")[:16]
            title = (n.get("title") or "")[:50]
            lines.append(f"  {ts} [{n.get('level','info')}] {title}")

    if data.get("gmail_unread"):
        lines.append("\n[Gmail 未読メール (cache 上位)]")
        for subject, from_addr, snippet, mdate in data["gmail_unread"][:8]:
            sender = ((from_addr or "").split("<")[0].strip() or
                      (from_addr or "").strip())[:32]
            subj = (subject or "(件名なし)")[:55]
            snip_short = ((snippet or "").replace("\n", " ").strip())[:60]
            lines.append(f"  {sender} | {subj}")
            if snip_short:
                lines.append(f"    {snip_short}")

    return "\n".join(lines) if lines else "（データなし）"


def build_prompt(period: str, lang: str, now: datetime, data: dict,
                 coverage_warnings: dict | None = None) -> str:
    past_w, cur_w, fut_w = calc_weights(period, now)
    p_label    = PERIOD_LABELS.get(period, {}).get(lang, period)
    lang_instr = LANG_INSTRUCTIONS.get(lang, LANG_INSTRUCTIONS["ja"])
    sec        = SECTION_LABELS.get(lang, SECTION_LABELS["ja"])
    p_start, p_end = _period_range(period, now)
    data_text  = _format_data_text(period, data, now)

    warn_section = ""
    if coverage_warnings:
        warn_lines = "\n".join(f"  - {k}: {v}" for k, v in coverage_warnings.items())
        warn_section = (
            f"\n【データカバレッジ警告】\n"
            f"以下のデータが不足しています。参考として考慮してください。\n"
            f"{warn_lines}\n"
        )

    return (
        f"あなたは日本の電力市場の専門アナリストです。\n"
        f"以下のデータを基に「{p_label}」を作成してください。\n\n"
        f"{lang_instr}\n\n"
        f"対象期間: {p_start.strftime('%Y-%m-%d')} ～ {p_end.strftime('%Y-%m-%d')}\n"
        f"生成日時: {now.strftime('%Y年%m月%d日 %H:%M')}\n\n"
        f"分析の重点配分:\n"
        f"- 過去分析: {past_w}%\n"
        f"- 現在状況: {cur_w}%\n"
        f"- 将来予測: {fut_w}%\n\n"
        f"【参考データ】\n{data_text}\n"
        f"{warn_section}\n"
        f"以下の構成で、重点配分に応じた詳細度でブリーフィングを作成してください。\n"
        f"重点の高いセクションをより詳しく、低いセクションは簡潔に記述してください。\n\n"
        f"{sec[0]} ({past_w}%)\n\n"
        f"{sec[1]} ({cur_w}%)\n\n"
        f"{sec[2]} ({fut_w}%)\n"
    )


# ── ワーカー ──────────────────────────────────────────────────────────────────

class BriefingWorker(BaseWorker):
    """ブリーフィングを非同期で生成する QThread ワーカー。"""
    result = Signal(str)
    status = Signal(str)   # 進捗メッセージ

    def __init__(self, period: str, lang: str):
        super().__init__()
        self.period = period
        self.lang   = lang

    def run(self):
        now = datetime.now()

        # Step 1: JKM 自動プリフェッチ (weekly / monthly / next_month のみ)
        if self.period != "daily":
            self.status.emit("JKM データを確認中...")
            jkm_err = prefetch_jkm_if_needed(self.period, now)
            if jkm_err:
                logger.warning(jkm_err)

        # Step 2: カバレッジチェック
        self.status.emit("データカバレッジを確認中...")
        coverage = check_coverage(self.period, now)
        if coverage:
            logger.info(f"ブリーフィング カバレッジ警告: {coverage}")

        # Step 3: データ収集
        self.status.emit("データを収集中...")
        try:
            data = collect_briefing_data(self.period, now)
        except Exception as e:
            self._emit_error(f"データ収集エラー: {e}", e)
            return

        # Step 4: AI 生成
        self.status.emit("AI ブリーフィングを生成中...")
        prompt      = build_prompt(self.period, self.lang, now, data,
                                   coverage_warnings=coverage if coverage else None)
        gemini_keys = get_all_gemini_keys()
        groq_key    = get_builtin_groq_key()
        messages    = [{"role": "user", "content": prompt}]

        last_err         = ""
        all_rate_limited = True

        for gemini_model in [GEMINI_LITE_MODEL, GEMINI_DEFAULT_MODEL]:
            for idx, key in enumerate(gemini_keys, 1):
                try:
                    reply = self._call_gemini(key, gemini_model, messages)
                    self.result.emit(reply)
                    return
                except ServiceUnavailableError:
                    all_rate_limited = False
                    break
                except RateLimitError:
                    logger.debug(f"briefing {gemini_model} key{idx}: 429")
                except Exception as e:
                    all_rate_limited = False
                    last_err = str(e)
                    logger.warning(f"briefing {gemini_model} key{idx}: {e}")

        if groq_key:
            try:
                reply = self._call_groq(groq_key, messages)
                self.result.emit(reply)
                return
            except RateLimitError:
                logger.debug("briefing Groq: 429")
            except Exception as e:
                all_rate_limited = False
                last_err = str(e)
                logger.error(f"briefing Groq: {e}")

        if all_rate_limited:
            self._emit_error("レート制限 — しばらく待ってから再試行してください")
        else:
            self._emit_error(last_err or "不明なエラー")

    def _call_gemini(self, api_key: str, model: str, messages: list) -> str:
        url = GEMINI_API_URL.format(model=model, key=api_key)
        payload = {
            "contents": [{"role": "user", "parts": [{"text": messages[0]["content"]}]}],
            "generationConfig": {"temperature": 0.6, "maxOutputTokens": 4096},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RateLimitError()
            if e.code == 503:
                raise ServiceUnavailableError()
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini HTTP {e.code}: {body[:300]}")
        try:
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise RuntimeError(f"Unexpected Gemini response: {result}")

    def _call_groq(self, api_key: str, messages: list) -> str:
        payload = {
            "model": GROQ_DEFAULT_MODEL,
            "messages": [{"role": "user", "content": messages[0]["content"]}],
            "temperature": 0.6,
            "max_tokens": 4096,
        }
        req = urllib.request.Request(
            GROQ_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "LEE-Monitor/2.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RateLimitError()
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Groq HTTP {e.code}: {body[:300]}")
        try:
            return result["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            raise RuntimeError(f"Unexpected Groq response: {result}")
