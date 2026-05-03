"""
JEPX スポット市場価格 API 通信・DB 管理モジュール
CSV: https://www.jepx.jp/market/excel/spot_{YYYY}.csv  (CP932 エンコーディング)
"""
import csv
import io
import logging
import time
from datetime import date, datetime

import requests
from PySide6.QtCore import Signal

from app.api.base import BaseWorker
from app.api.market.hjks import LegacySSLAdapter
from app.core.config import API_JEPX_SPOT_BASE, DB_JEPX_SPOT
from app.core.database import get_db_connection

logger = logging.getLogger(__name__)


# ── 会計年度ユーティリティ ─────────────────────────────────────────────────────

def fiscal_year_of(d: date) -> int:
    """日付から会計年度を返す (4月始まり)。例: 2026年4月 → 2026年度"""
    return d.year if d.month >= 4 else d.year - 1


def fiscal_year_range(fy: int) -> tuple[str, str]:
    """会計年度の開始日・終了日 (YYYY-MM-DD) を返す。"""
    return (f"{fy}-04-01", f"{fy + 1}-03-31")


def current_fiscal_year() -> int:
    return fiscal_year_of(date.today())


_JEPX_SPOT_FIRST_YEAR = 2016   # JEPX スポット CSV が公開されている最古年度


def _years_to_download() -> list[int]:
    """ダウンロード対象の暦年リスト (2016〜当年)。

    JEPX スポット CSV は 2016 年が最古。それ以前を要求すると 404 が連発し
    sleep 0.3s × N の無駄なネットワーク待機が発生するため範囲を絞る。
    """
    return list(range(_JEPX_SPOT_FIRST_YEAR, datetime.now().year + 1))


# ── DB スキーマ ────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS jepx_spot_prices (
    date         TEXT    NOT NULL,
    slot         INTEGER NOT NULL,
    system_price REAL,
    hokkaido     REAL,
    tohoku       REAL,
    tokyo        REAL,
    chubu        REAL,
    hokuriku     REAL,
    kansai       REAL,
    chugoku      REAL,
    shikoku      REAL,
    kyushu       REAL,
    PRIMARY KEY (date, slot)
)
"""


def _ensure_schema(conn) -> None:
    conn.execute(_DDL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jepx_spot_date ON jepx_spot_prices (date)"
    )
    conn.commit()


def _existing_years(conn) -> set[int]:
    rows = conn.execute(
        "SELECT DISTINCT CAST(strftime('%Y', date) AS INTEGER) FROM jepx_spot_prices"
    ).fetchall()
    return {r[0] for r in rows if r[0]}


def _upsert(conn, rows: list[tuple]) -> None:
    conn.executemany(
        """INSERT OR REPLACE INTO jepx_spot_prices
           (date, slot, system_price, hokkaido, tohoku, tokyo, chubu,
            hokuriku, kansai, chugoku, shikoku, kyushu)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()


# ── CSV パーサー ───────────────────────────────────────────────────────────────

def _safe_float(row: list[str], idx: int) -> float | None:
    if idx < 0 or idx >= len(row):
        return None
    try:
        v = row[idx].strip().replace(",", "")
        return float(v) if v else None
    except ValueError:
        return None


def _parse_date(raw: str) -> str | None:
    """YYYY/MM/DD または YYYYMMDD → YYYY-MM-DD。"""
    raw = raw.strip()
    if "/" in raw:
        p = raw.split("/")
        if len(p) == 3:
            return f"{p[0]}-{p[1].zfill(2)}-{p[2].zfill(2)}"
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return None


def _find_col(header: list[str], keywords: list[str]) -> int:
    for kw in keywords:
        for i, h in enumerate(header):
            if kw in h:
                return i
    return -1


def parse_spot_csv(content: str) -> list[tuple]:
    """JEPX スポット市場 CSV を解析してタプルリストを返す。"""
    reader = csv.reader(io.StringIO(content))
    header = None
    for row in reader:
        if any(k in "".join(row) for k in ["約定日", "年月日", "コマ"]):
            header = [h.strip() for h in row]
            break

    if not header:
        logger.warning("JEPXスポットCSV: ヘッダー行が見つかりません")
        return []

    c_date = _find_col(header, ["約定日", "年月日"])
    c_slot = _find_col(header, ["コマ", "時刻コード", "時刻"])
    c_sys  = _find_col(header, ["システムプライス", "システム"])
    c_hkd  = _find_col(header, ["北海道"])
    c_thk  = _find_col(header, ["東北"])
    c_tky  = _find_col(header, ["東京"])
    c_chb  = _find_col(header, ["中部"])
    c_hkr  = _find_col(header, ["北陸"])
    c_kns  = _find_col(header, ["関西"])
    c_cgk  = _find_col(header, ["中国"])
    c_skk  = _find_col(header, ["四国"])
    c_kys  = _find_col(header, ["九州"])

    if c_date < 0 or c_slot < 0:
        logger.error(f"JEPXスポットCSV: 必須カラム不足 header={header[:8]}")
        return []

    rows: list[tuple] = []
    for row in reader:
        if not row or len(row) <= max(c_date, c_slot):
            continue
        d = _parse_date(row[c_date])
        if not d:
            continue
        try:
            slot = int(row[c_slot].strip())
        except (ValueError, IndexError):
            continue
        rows.append((
            d, slot,
            _safe_float(row, c_sys),
            _safe_float(row, c_hkd),
            _safe_float(row, c_thk),
            _safe_float(row, c_tky),
            _safe_float(row, c_chb),
            _safe_float(row, c_hkr),
            _safe_float(row, c_kns),
            _safe_float(row, c_cgk),
            _safe_float(row, c_skk),
            _safe_float(row, c_kys),
        ))
    return rows


# ── HTTP セッション ────────────────────────────────────────────────────────────

def _make_session() -> requests.Session:
    s = requests.Session()
    s.mount("https://", LegacySSLAdapter())
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    return s


def _download_year(session: requests.Session, year: int) -> list[tuple]:
    url = f"{API_JEPX_SPOT_BASE}/spot_{year}.csv"
    logger.info(f"JEPX スポット {year}年 CSV 取得: {url}")
    r = session.get(url, timeout=30)
    r.raise_for_status()
    rows = parse_spot_csv(r.content.decode("cp932", errors="replace"))
    logger.info(f"JEPX スポット {year}年: {len(rows)} 行")
    return rows


# ── Workers ────────────────────────────────────────────────────────────────────

class FetchJepxSpotHistoryWorker(BaseWorker):
    """DB にない暦年データを一括ダウンロードして DB に保存する。

    progress(current, total, year) シグナルで進捗を通知。
    当年は常に再取得して当日分の新規データを反映させる。
    """
    finished = Signal()
    progress = Signal(int, int, int)   # current, total, year

    def run(self):
        with get_db_connection(DB_JEPX_SPOT) as conn:
            _ensure_schema(conn)
            existing = _existing_years(conn)

        all_years = _years_to_download()
        missing   = [y for y in all_years if y not in existing]
        # 当年は常に再取得
        if all_years[-1] not in missing:
            missing.append(all_years[-1])
        missing.sort()

        if not missing:
            self.finished.emit()
            return

        session = _make_session()
        total   = len(missing)
        for i, year in enumerate(missing, 1):
            self.progress.emit(i, total, year)
            try:
                rows = _download_year(session, year)
                if rows:
                    with get_db_connection(DB_JEPX_SPOT) as conn:
                        _ensure_schema(conn)
                        _upsert(conn, rows)
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    logger.info(f"JEPX {year}年 CSV なし (404)、スキップ")
                else:
                    logger.warning(f"JEPX {year}年 取得失敗: {e}")
            except Exception as e:
                logger.warning(f"JEPX {year}年 取得失敗: {e}")
            time.sleep(0.3)   # サーバー負荷軽減

        self.finished.emit()


class FetchJepxSpotTodayWorker(BaseWorker):
    """当年 CSV を取得して DB を更新。当日データの有無 (bool) を返す。"""
    finished = Signal(bool)

    def run(self):
        today   = date.today().isoformat()
        session = _make_session()
        try:
            rows = _download_year(session, datetime.now().year)
            if rows:
                with get_db_connection(DB_JEPX_SPOT) as conn:
                    _ensure_schema(conn)
                    _upsert(conn, rows)
                    count = conn.execute(
                        "SELECT COUNT(*) FROM jepx_spot_prices WHERE date=?",
                        (today,),
                    ).fetchone()[0]
                self.finished.emit(count > 0)
            else:
                self.finished.emit(False)
        except Exception as e:
            logger.warning(f"JEPX 当日データ取得失敗: {e}")
            self.error.emit(str(e))
            self.finished.emit(False)
