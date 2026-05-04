"""Gmail 로컬 SQLite 캐시 — fetch 비용 절감.

캐시 대상:
    - mail_metadata : 메일 리스트 항목 (id, sender, subject, date, snippet,
                      unread/starred 플래그, label_ids)
    - mail_body     : 본문 HTML + 첨부 메타 (id 단위)

활용 패턴:
    - 리스트 새로고침 시: messages.list 로 현재 ID 만 가져온 뒤 cache 에 없는
      ID 만 metadata 배치 fetch → 매 새로고침마다 50건 배치 호출이 1~2건으로
      축소되어 round-trip 시간이 대폭 감소.
    - 본문 클릭 시: cache hit 이면 즉시 emit (network 0), miss 이면 fetch
      후 cache 적재 → 같은 메일 재오픈은 즉시 표시.

상태 변경 동기화:
    - mark read / star 동작 시 invalidate_or_update_metadata() 호출하여
      관련 행만 갱신 (전체 cache 폐기 아님).

저장 위치: APP_DIR/gmail_cache.db
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Optional

logger = logging.getLogger(__name__)

# 기본 TTL — metadata 는 6시간, body 는 30일
_METADATA_TTL_SEC = 6 * 3600
_BODY_TTL_SEC     = 30 * 24 * 3600

_db_initialized = False


def _db_path():
    from app.core.config import APP_DIR
    return APP_DIR / "gmail_cache.db"


def _ensure_db() -> None:
    global _db_initialized
    if _db_initialized:
        return
    try:
        with sqlite3.connect(_db_path()) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS mail_metadata (
                    id            TEXT PRIMARY KEY,
                    thread_id     TEXT,
                    snippet       TEXT,
                    from_addr     TEXT,
                    subject       TEXT,
                    date          TEXT,
                    is_unread     INTEGER,
                    is_starred    INTEGER,
                    label_ids     TEXT,
                    cached_at     INTEGER
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS mail_body (
                    id            TEXT PRIMARY KEY,
                    body_html     TEXT,
                    attachments   TEXT,
                    cached_at     INTEGER
                )
            """)
        _db_initialized = True
    except sqlite3.Error as e:
        logger.warning(f"gmail_cache DB 初期化失敗: {e}")


# ──────────────────────────────────────────────────────────────────────
# Metadata cache
# ──────────────────────────────────────────────────────────────────────
def get_cached_metadata(
    message_ids: list[str], *, max_age_sec: int = _METADATA_TTL_SEC,
) -> dict[str, dict]:
    """주어진 ID 들의 캐시된 metadata 를 dict[id → mail_dict] 로 반환.

    max_age_sec 보다 오래된 행은 stale 로 간주, 결과에 포함하지 않음 (=
    호출자가 fresh fetch 대상으로 처리).
    """
    if not message_ids:
        return {}
    _ensure_db()
    cutoff = int(time.time()) - max_age_sec
    placeholders = ",".join("?" * len(message_ids))
    out: dict[str, dict] = {}
    try:
        with sqlite3.connect(_db_path()) as con:
            rows = con.execute(
                f"SELECT id, thread_id, snippet, from_addr, subject, date, "
                f"       is_unread, is_starred, label_ids "
                f"FROM mail_metadata WHERE id IN ({placeholders}) AND cached_at >= ?",
                list(message_ids) + [cutoff],
            ).fetchall()
        for r in rows:
            out[r[0]] = {
                "id":         r[0],
                "thread_id":  r[1] or "",
                "snippet":    r[2] or "",
                "from":       r[3] or "",
                "subject":    r[4] or "(件名なし)",
                "date":       r[5] or "",
                "is_unread":  bool(r[6]),
                "is_starred": bool(r[7]),
                "label_ids":  json.loads(r[8]) if r[8] else [],
            }
    except sqlite3.Error as e:
        logger.warning(f"mail_metadata 조회 실패: {e}")
    return out


def cache_metadata(mails: list[dict]) -> None:
    """metadata 행 일괄 upsert."""
    if not mails:
        return
    _ensure_db()
    now = int(time.time())
    rows = [
        (
            m.get("id", ""),
            m.get("thread_id", ""),
            m.get("snippet", ""),
            m.get("from", ""),
            m.get("subject", "(件名なし)"),
            m.get("date", ""),
            int(bool(m.get("is_unread", False))),
            int(bool(m.get("is_starred", False))),
            json.dumps(m.get("label_ids", [])),
            now,
        )
        for m in mails if m.get("id")
    ]
    if not rows:
        return
    try:
        with sqlite3.connect(_db_path()) as con:
            con.executemany(
                "INSERT OR REPLACE INTO mail_metadata "
                "(id, thread_id, snippet, from_addr, subject, date, "
                " is_unread, is_starred, label_ids, cached_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
    except sqlite3.Error as e:
        logger.warning(f"mail_metadata upsert 실패: {e}")


def update_metadata_flags(
    message_id: str, *,
    is_unread: Optional[bool] = None,
    is_starred: Optional[bool] = None,
    add_labels: Optional[list[str]] = None,
    remove_labels: Optional[list[str]] = None,
) -> None:
    """단건 메일의 unread/starred/labels 만 갱신 — server 와 동기 위해 호출.

    원격에 mark read/star 를 적용한 직후 같이 호출하면 stale cache 로 인한
    잘못된 표시를 방지.
    """
    if not message_id:
        return
    _ensure_db()
    try:
        with sqlite3.connect(_db_path()) as con:
            row = con.execute(
                "SELECT is_unread, is_starred, label_ids FROM mail_metadata WHERE id=?",
                (message_id,),
            ).fetchone()
            if row is None:
                return
            cur_unread, cur_star, cur_labels_json = row
            labels = json.loads(cur_labels_json) if cur_labels_json else []
            if add_labels:
                for l in add_labels:
                    if l not in labels:
                        labels.append(l)
            if remove_labels:
                labels = [l for l in labels if l not in remove_labels]
            new_unread = int(is_unread) if is_unread is not None else cur_unread
            new_star = int(is_starred) if is_starred is not None else cur_star
            con.execute(
                "UPDATE mail_metadata SET is_unread=?, is_starred=?, label_ids=?, "
                "cached_at=? WHERE id=?",
                (new_unread, new_star, json.dumps(labels), int(time.time()),
                 message_id),
            )
    except sqlite3.Error as e:
        logger.warning(f"mail_metadata flag 갱신 실패: {e}")


def invalidate_metadata(message_ids: list[str]) -> None:
    """주어진 ID 들의 metadata cache 행 삭제 (다음 fetch 강제)."""
    if not message_ids:
        return
    _ensure_db()
    placeholders = ",".join("?" * len(message_ids))
    try:
        with sqlite3.connect(_db_path()) as con:
            con.execute(
                f"DELETE FROM mail_metadata WHERE id IN ({placeholders})",
                list(message_ids),
            )
    except sqlite3.Error as e:
        logger.warning(f"mail_metadata invalidate 실패: {e}")


# ──────────────────────────────────────────────────────────────────────
# Body cache
# ──────────────────────────────────────────────────────────────────────
def get_cached_body(message_id: str) -> Optional[dict]:
    """{body_html, attachments} 또는 None."""
    if not message_id:
        return None
    _ensure_db()
    try:
        with sqlite3.connect(_db_path()) as con:
            row = con.execute(
                "SELECT body_html, attachments FROM mail_body WHERE id=?",
                (message_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "body_html":   row[0] or "",
            "attachments": json.loads(row[1]) if row[1] else [],
        }
    except sqlite3.Error as e:
        logger.warning(f"mail_body 조회 실패: {e}")
        return None


def cache_body(message_id: str, body_html: str, attachments: list) -> None:
    """본문 HTML + 첨부 메타 upsert."""
    if not message_id:
        return
    _ensure_db()
    try:
        with sqlite3.connect(_db_path()) as con:
            con.execute(
                "INSERT OR REPLACE INTO mail_body "
                "(id, body_html, attachments, cached_at) VALUES (?,?,?,?)",
                (message_id, body_html or "",
                 json.dumps(attachments or []), int(time.time())),
            )
    except sqlite3.Error as e:
        logger.warning(f"mail_body upsert 실패: {e}")


def evict_old(now: Optional[int] = None) -> None:
    """오래된 cache 행 삭제 — 시작 시 1회 호출 권장. DB 크기 폭증 방지."""
    _ensure_db()
    now = now if now is not None else int(time.time())
    body_cutoff = now - _BODY_TTL_SEC
    meta_cutoff = now - _METADATA_TTL_SEC * 28   # ~7일 정도까지 보관
    try:
        with sqlite3.connect(_db_path()) as con:
            con.execute("DELETE FROM mail_body WHERE cached_at < ?", (body_cutoff,))
            con.execute("DELETE FROM mail_metadata WHERE cached_at < ?", (meta_cutoff,))
    except sqlite3.Error as e:
        logger.warning(f"gmail_cache evict 실패: {e}")
