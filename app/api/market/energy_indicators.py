"""エネルギー指標 (LNG · 原油 · 為替) — Yahoo Finance 多銘柄 取込.

설계:
    - 단일 통합 테이블 `energy_prices` 에 모든 지표 시계열 저장
    - PRIMARY KEY (indicator, date) — 지표별 일별 종가/고저
    - `FetchEnergyIndicatorsWorker` 가 config.ENERGY_INDICATORS 의 모든 ticker 를
      yfinance 로 일괄 다운로드 (병렬 thread)

기존 `FetchJkmWorker` (`jkm_prices` 테이블) 와 별개로 운영.
JKM 관련 카드/디테일은 본 모듈의 새 테이블을 우선 사용하되, 데이터 부재 시
구 `jkm_prices` 로 fallback 가능.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import requests
import yfinance as yf
from PySide6.QtCore import Signal

from app.api.base import BaseWorker
from app.core.config import DB_ENERGY, ENERGY_INDICATORS
from app.core.database import get_db_connection

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# DB schema / helpers
# ──────────────────────────────────────────────────────────────────────
_DDL = """
CREATE TABLE IF NOT EXISTS energy_prices (
    indicator TEXT NOT NULL,
    date      TEXT NOT NULL,
    open      REAL,
    high      REAL,
    low       REAL,
    close     REAL NOT NULL,
    PRIMARY KEY (indicator, date)
)
"""


def _ensure_schema(conn) -> None:
    conn.execute(_DDL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_energy_ind_date ON energy_prices (indicator, date)"
    )
    conn.commit()


def _to_float(val) -> Optional[float]:
    try:
        f = float(val)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _save_indicator(indicator_id: str, rows: list[tuple]) -> int:
    """rows: [(date_str, open, high, low, close), ...]"""
    if not rows:
        return 0
    payload = [(indicator_id, *r) for r in rows]
    with get_db_connection(DB_ENERGY) as conn:
        _ensure_schema(conn)
        cur = conn.executemany(
            "INSERT OR REPLACE INTO energy_prices "
            "(indicator, date, open, high, low, close) "
            "VALUES (?,?,?,?,?,?)",
            payload,
        )
        conn.commit()
        return cur.rowcount


def query_indicator(indicator_id: str, *, limit: Optional[int] = None) -> list[tuple]:
    """지표의 시계열 (date, close, high, low) 반환 — 오래된 → 최신 정렬.

    limit 가 주어지면 최근 N 거래일만.
    """
    try:
        with get_db_connection(DB_ENERGY) as conn:
            _ensure_schema(conn)
            if limit and limit > 0:
                rows = conn.execute(
                    "SELECT date, close, high, low FROM energy_prices "
                    "WHERE indicator = ? ORDER BY date DESC LIMIT ?",
                    (indicator_id, limit),
                ).fetchall()
                return list(reversed(rows))
            return conn.execute(
                "SELECT date, close, high, low FROM energy_prices "
                "WHERE indicator = ? ORDER BY date",
                (indicator_id,),
            ).fetchall()
    except Exception as e:
        logger.warning(f"energy_prices 쿼리 실패 ({indicator_id}): {e}")
        return []


def has_indicator_data(indicator_id: str) -> bool:
    try:
        with get_db_connection(DB_ENERGY) as conn:
            _ensure_schema(conn)
            row = conn.execute(
                "SELECT 1 FROM energy_prices WHERE indicator = ? LIMIT 1",
                (indicator_id,),
            ).fetchone()
            return row is not None
    except Exception:
        return False


def latest_date(indicator_id: str) -> Optional[str]:
    """지표의 최신 데이터 날짜 (YYYY-MM-DD) 또는 None."""
    try:
        with get_db_connection(DB_ENERGY) as conn:
            _ensure_schema(conn)
            row = conn.execute(
                "SELECT MAX(date) FROM energy_prices WHERE indicator = ?",
                (indicator_id,),
            ).fetchone()
            return row[0] if row else None
    except Exception:
        return None


def migrate_legacy_jkm() -> int:
    """기존 `jkm_prices` (DB_JKM) → `energy_prices` (DB_ENERGY, indicator='jkm')
    일회성 마이그레이션. 이미 존재하는 행은 INSERT OR IGNORE 로 skip.
    반환: 새로 추가된 행 수.
    """
    import sqlite3
    from app.core.config import DB_JKM
    try:
        with get_db_connection(DB_JKM) as src:
            try:
                rows = src.execute(
                    "SELECT date, open, high, low, close FROM jkm_prices ORDER BY date"
                ).fetchall()
            except sqlite3.OperationalError:
                return 0  # jkm_prices 테이블 없음 (정상)
        if not rows:
            return 0
        with get_db_connection(DB_ENERGY) as dst:
            _ensure_schema(dst)
            payload = [("jkm", r[0], r[1], r[2], r[3], r[4]) for r in rows]
            cur = dst.executemany(
                "INSERT OR IGNORE INTO energy_prices "
                "(indicator, date, open, high, low, close) VALUES (?,?,?,?,?,?)",
                payload,
            )
            dst.commit()
            return cur.rowcount
    except Exception as e:
        logger.warning(f"JKM legacy 마이그레이션 실패: {e}")
        return 0


# ──────────────────────────────────────────────────────────────────────
# Fetch worker — 모든 지표 병렬 다운로드
# ──────────────────────────────────────────────────────────────────────
def _fetch_one_ticker(indicator_id: str, ticker: str) -> tuple[str, int, Optional[str]]:
    """단일 ticker 다운로드 + DB 저장. 성공 시 (id, count, None), 실패 시 (id, 0, err_msg)."""
    try:
        hist = yf.Ticker(ticker).history(period="max")
        if hist.empty:
            return indicator_id, 0, f"empty data ({ticker})"
        rows = []
        for dt_idx, row in hist.iterrows():
            close = _to_float(row.get("Close"))
            if close is None:
                continue
            rows.append((
                dt_idx.strftime("%Y-%m-%d"),
                _to_float(row.get("Open")),
                _to_float(row.get("High")),
                _to_float(row.get("Low")),
                close,
            ))
        if not rows:
            return indicator_id, 0, f"no valid rows ({ticker})"
        count = _save_indicator(indicator_id, rows)
        return indicator_id, count, None
    except requests.exceptions.RequestException as e:
        return indicator_id, 0, f"通信エラー: {e}"
    except Exception as e:
        logger.warning(f"{indicator_id} ({ticker}) fetch 실패: {e}")
        return indicator_id, 0, str(e)


class FetchEnergyIndicatorsWorker(BaseWorker):
    """ENERGY_INDICATORS 의 모든 ticker 를 병렬로 다운로드해 energy_prices 에 저장.

    Signals
    -------
    progress(str)        — '中: id (3/6)' 진행 메시지
    finished(dict)       — {indicator_id: count} (실패는 0)
    error(str)           — 전체 실패 시
    """

    progress = Signal(str)
    finished = Signal(dict)

    def run(self):
        try:
            tasks = list(ENERGY_INDICATORS)
            if not tasks:
                self.finished.emit({})
                return

            results: dict[str, int] = {}
            errors: list[str] = []
            total = len(tasks)
            done = 0

            self.progress.emit(f"取得開始: {total} 銘柄")

            # 병렬 fetch (yfinance 는 IO bound)
            with ThreadPoolExecutor(max_workers=min(6, total)) as ex:
                fut_map = {
                    ex.submit(_fetch_one_ticker, ind["id"], ind["ticker"]): ind
                    for ind in tasks
                }
                for fut in as_completed(fut_map):
                    ind = fut_map[fut]
                    try:
                        _id, count, err = fut.result()
                        results[_id] = count
                        if err:
                            errors.append(f"{_id}: {err}")
                    except Exception as e:
                        results[ind["id"]] = 0
                        errors.append(f"{ind['id']}: {e}")
                    done += 1
                    self.progress.emit(f"取得中: {ind['label']} ({done}/{total})")

            success_count = sum(1 for v in results.values() if v > 0)
            self.progress.emit(f"取得完了: {success_count}/{total} 銘柄成功")

            if success_count == 0:
                self.error.emit(
                    "全銘柄の取得に失敗しました。\n" + "\n".join(errors[:6])
                )
                return

            self.finished.emit(results)
        except Exception as e:
            logger.error(f"FetchEnergyIndicatorsWorker 致命的エラー: {e}", exc_info=True)
            self.error.emit(f"予期せぬエラー: {e}")
