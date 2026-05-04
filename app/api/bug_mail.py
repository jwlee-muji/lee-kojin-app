"""バグレポート Gmail バックエンド (Option 2 — Sheets 代替)

セキュリティ事情:
    旧 Sheets バックエンドは service_account.json をユーザー配布 exe に
    同梱する必要があり、ユーザー側 PC に資格情報が露出する問題があった。
    本モジュールでは:
      - 一般ユーザー: SMTP のみで送信 (Google 資格情報 0)
      - 管理者: 自分の Gmail 受信トレイを OAuth で読み取り、
                BUG_REPORT_TO 宛のレポートメールをパースして表示
    管理者 PC のみ Google OAuth トークン (DPAPI 暗号化) を保持。

メール書式 (送信側 = _BugFormPage._on_send 生成):
    Subject: [LEE v{version}] {category_label}: {summary}
    Body sections:
      【分類】 ...
      【概要】 ...
      【ユーザー】 ...
      【アプリ】 v...
      【OS】 ...
      【画面】 ...
      【詳細・再現手順】 + 本文
      【ログ (直近 80 行)】 + log

状態管理:
    管理者 PC のローカル SQLite (bug_mail_state.db) に
    Gmail message_id をキーに status / priority / deleted を上書き。
    Gmail 自体には触れず (ラベル変更なし)、削除は論理削除のみ。

公開 API:
    - is_available()        : 管理者として Gmail OAuth が有効か
    - set_status(mid, st)   : ローカル状態 — status 更新
    - set_priority(mid, p)  : ローカル状態 — priority 更新
    - set_deleted(mid)      : ローカル状態 — 論理削除
    - BugMailReadWorker     : 非同期 Gmail fetch + parse + state join
"""
from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal

from app.api.email_api import BUG_REPORT_TO

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# ローカル状態 DB
# ──────────────────────────────────────────────────────────────────────
def _state_db() -> Path:
    from app.core.config import APP_DIR
    return APP_DIR / "bug_mail_state.db"


_db_initialized = False


def _ensure_db() -> None:
    global _db_initialized
    if _db_initialized:
        return
    try:
        with sqlite3.connect(_state_db()) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS bug_mail_state (
                    message_id TEXT PRIMARY KEY,
                    status     TEXT DEFAULT 'open',
                    priority   TEXT DEFAULT 'medium',
                    deleted    INTEGER DEFAULT 0,
                    updated_at TEXT
                )
            """)
        _db_initialized = True
    except sqlite3.Error as e:
        logger.error(f"bug_mail_state DB init 실패: {e}")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_all_states() -> dict[str, dict]:
    _ensure_db()
    try:
        with sqlite3.connect(_state_db()) as con:
            rows = con.execute(
                "SELECT message_id, status, priority, deleted FROM bug_mail_state"
            ).fetchall()
        return {
            r[0]: {"status": r[1], "priority": r[2], "deleted": bool(r[3])}
            for r in rows
        }
    except sqlite3.Error as e:
        logger.warning(f"bug_mail_state load 실패: {e}")
        return {}


def _upsert_state(message_id: str, **fields) -> None:
    _ensure_db()
    if not message_id or not fields:
        return
    try:
        with sqlite3.connect(_state_db()) as con:
            con.execute(
                "INSERT OR IGNORE INTO bug_mail_state (message_id, updated_at) VALUES (?, ?)",
                (message_id, _now()),
            )
            sets = ", ".join(f"{k}=?" for k in fields) + ", updated_at=?"
            params = list(fields.values()) + [_now(), message_id]
            con.execute(
                f"UPDATE bug_mail_state SET {sets} WHERE message_id=?", params
            )
    except sqlite3.Error as e:
        logger.warning(f"bug_mail_state upsert 실패: {e}")


def set_status(message_id: str, status: str, source: str = "gmail") -> None:
    """status 갱신 — source 따라 백엔드 분기.

    source="gmail": Gmail メッセージ ID → 로컬 SQLite 오버레이 (기존 경로)
    source="sheet": Sheets request_id  → AccessRequests 시트 F 열 직접 갱신
    """
    if source == "sheet":
        try:
            from app.api.google.sheets import update_access_request_status
            update_access_request_status(message_id, status)
        except Exception as e:
            logger.warning(f"AccessRequest status update failed: {e}")
        return
    _upsert_state(message_id, status=status)


def set_priority(message_id: str, priority: str, source: str = "gmail") -> None:
    """priority 갱신 — Sheets 기반 access 는 priority 컬럼 미보유, 무시."""
    if source == "sheet":
        return
    _upsert_state(message_id, priority=priority)


def set_deleted(message_id: str, source: str = "gmail") -> None:
    """소프트 삭제 — source 따라 백엔드 분기."""
    if source == "sheet":
        try:
            from app.api.google.sheets import delete_access_request
            delete_access_request(message_id)
        except Exception as e:
            logger.warning(f"AccessRequest delete failed: {e}")
        return
    _upsert_state(message_id, deleted=1)


# ──────────────────────────────────────────────────────────────────────
# 可用性チェック
# ──────────────────────────────────────────────────────────────────────
def is_available() -> bool:
    """管理者 Gmail OAuth が認証済みか (= レポート読み取り可能か)."""
    try:
        from app.api.google.auth import is_authenticated
        return is_authenticated()
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────
# パーサ
# ──────────────────────────────────────────────────────────────────────
# 件名: "[LEE v4.3.7] バグ・エラー: ボタン無反応"  / 旧 "[LEE v...] bug: ..."
_SUBJECT_RE = re.compile(
    r"^\s*\[LEE\s+v([^\]]+)\]\s*([^:]+?)\s*:\s*(.*)$"
)

# 本文: 【...】 セクション抽出 — 同一行 or 複数行に渡る本文をブロック単位で取得
_BLOCK_RE = re.compile(r"【([^】]+)】\s*(.*?)(?=【|\Z)", re.DOTALL)

# 일본어 카테고리 라벨 → key (역매핑)
_CATEGORY_LABEL_TO_KEY = {
    "バグ・エラー":         "bug",
    "UI 表示の問題":        "ui",
    "データ取得エラー":     "data",
    "パフォーマンス問題":   "perf",
    "機能要望":             "feat",
    "その他":               "other",
}


def _category_key_from_label(label: str) -> str:
    """件名 / 本文の分類ラベルから内部 key を逆引き."""
    s = (label or "").strip()
    # "🐛  バグ・エラー" 形式 — 絵文字を除去
    if "  " in s:
        s = s.split("  ", 1)[-1].strip()
    return _CATEGORY_LABEL_TO_KEY.get(s, "other")


def _strip_email_brackets(s: str) -> str:
    """'Foo Bar <foo@example.com>' → 'foo@example.com'"""
    m = re.search(r"<([^>]+)>", s)
    return m.group(1).strip() if m else s.strip()


def _parse_internal_date_ms(ms_str: str) -> str:
    """Gmail internalDate (epoch ms) → 'YYYY-MM-DD HH:MM:SS'."""
    try:
        ts = int(ms_str) / 1000.0
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OSError):
        return ""


def _detect_kind(subject: str, blocks: dict) -> str:
    """件名・本文から種別 (bug / access) を判定."""
    if "アクセス申請" in subject:
        return "access"
    if "申請メールアドレス" in blocks:
        return "access"
    return "bug"


def parse_bug_mail(msg: dict, state: Optional[dict] = None) -> dict:
    """Gmail full-format message dict → report record dict (bug or access).

    Args:
        msg: gmail.users().messages().get(format="full") の戻り値
        state: ローカル状態 {status, priority, deleted} (任意)
    """
    from app.api.google.gmail import _extract_body, _get_header

    headers = msg.get("payload", {}).get("headers", [])
    subject = _get_header(headers, "Subject") or ""
    from_h  = _get_header(headers, "From") or ""

    # Subject パース — "[LEE v4.3.7] {分類|アクセス申請}: {summary|email}"
    app_version = ""
    category_label = ""
    summary = subject
    m = _SUBJECT_RE.match(subject)
    if m:
        app_version = "v" + m.group(1).strip()
        category_label = m.group(2).strip()
        summary = m.group(3).strip()

    # 本文 抽出
    _html, plain = _extract_body(msg.get("payload", {}))
    body_text = plain or ""
    blocks: dict[str, str] = {}
    for bm in _BLOCK_RE.finditer(body_text):
        key = bm.group(1).strip()
        val = bm.group(2).strip()
        blocks[key] = val

    kind = _detect_kind(subject, blocks)

    # ── 種別ごとに分岐 ───────────────────────────────────────────────
    if kind == "access":
        # アクセス申請メール (login_window.py が送信)
        # subject: "[LEE v...] アクセス申請: {email}"
        # body  : 【申請メールアドレス】 + 【メッセージ】
        applicant = blocks.get("申請メールアドレス", "") or summary
        reporter = applicant or _strip_email_brackets(from_h)
        message  = blocks.get("メッセージ", "")
        if message in ("(なし)", "(未記入)"):
            message = ""
        category = "access"
        # summary は申請者のメールアドレスを表示
        summary = applicant or _strip_email_brackets(from_h) or "(unknown)"
        detail  = message
        log_text = ""
        os_info  = ""
        app_v    = app_version
    else:
        # バグレポート (既存)
        category = _category_key_from_label(category_label)
        if "分類" in blocks and blocks["分類"]:
            category = _category_key_from_label(blocks["分類"])
        if "概要" in blocks and blocks["概要"]:
            summary = blocks["概要"]
        reporter = blocks.get("ユーザー", "") or _strip_email_brackets(from_h)
        if reporter == "(unknown)":
            reporter = _strip_email_brackets(from_h)
        app_v = blocks.get("アプリ", "") or app_version
        os_info = blocks.get("OS", "")
        # 詳細 — 「詳細・再現手順」優先, fallback 「詳細」
        detail_keys = ("詳細・再現手順", "詳細")
        detail = ""
        for k in detail_keys:
            if k in blocks and blocks[k]:
                detail = blocks[k].strip()
                break
        if detail in ("(未記入)", "(미기입)"):
            detail = ""
        # ログ
        log_keys = [k for k in blocks if k.startswith("ログ")]
        log_text = blocks.get(log_keys[0], "") if log_keys else ""

    created_at = _parse_internal_date_ms(msg.get("internalDate", ""))

    state = state or {}
    return {
        "id":             msg.get("id", ""),       # Gmail message_id (str)
        "thread_id":      msg.get("threadId", ""),
        "source":         "gmail",                  # 상태 dispatch 용
        "kind":           kind,                     # "bug" | "access"
        "category":       category,
        "summary":        summary,
        "detail":         detail,
        "log":            log_text,
        "reporter_email": reporter,
        "app_version":    app_v,
        "os_info":        os_info,
        "screenshot_path": "",
        "status":         state.get("status",   "open"),
        "priority":       state.get("priority", "medium"),
        "created_at":     created_at,
        "updated_at":     created_at,
    }


def fetch_sheet_access_requests() -> list[dict]:
    """Google Sheets AccessRequests 시트의 申請を Gmail 동일 dict 형식으로 반환.

    parse_bug_mail 의 출력과 호환되도록 같은 키 구조 채움.
    source="sheet" 로 표시 — 상태 갱신 시 Sheets 백엔드로 dispatch.
    """
    try:
        from app.api.google.sheets import get_access_requests
        rows = get_access_requests()
    except Exception as e:
        logger.warning(f"AccessRequests fetch from Sheet failed: {e}")
        return []

    out = []
    for r in rows:
        out.append({
            "id":             r["request_id"],
            "thread_id":      "",
            "source":         "sheet",
            "kind":           "access",
            "category":       "access",
            "summary":        r["email"],
            "detail":         r["message"],
            "log":            "",
            "reporter_email": r["email"],
            "app_version":    r["app_version"],
            "os_info":        "",
            "screenshot_path": "",
            "status":         r["status"] or "open",
            "priority":       "medium",
            "created_at":     r["requested_at"],
            "updated_at":     r["requested_at"],
        })
    return out


# ──────────────────────────────────────────────────────────────────────
# 비동기 Worker
# ──────────────────────────────────────────────────────────────────────
class BugMailReadWorker(QThread):
    """管理者 Gmail から BUG_REPORT_TO 宛のレポート (バグ/アクセス申請) を fetch + parse."""
    finished = Signal(list, dict)   # (records, stats)
    error    = Signal(str)

    # 取得上限 (古いものは Gmail 検索結果から自然に外れる)
    MAX_RESULTS = 200

    def __init__(self, status_f: str = "", category_f: str = "",
                 search: str = "", kind_f: str = ""):
        super().__init__()
        self.status_f = status_f
        self.category_f = category_f
        self.search = search
        self.kind_f = kind_f

    def run(self):
        try:
            from app.api.google.auth import build_service
            from app.api.google.gmail import _execute_batch_chunks, _execute_single

            svc = build_service("gmail", "v1")
            # `to:` 만으로 1차 좁힘 — subject 토큰화로 대괄호가 매치 안 되는
            # 문제를 회피하고, "[LEE v" 접두 필터는 client-side で適用.
            query = f'to:{BUG_REPORT_TO}'
            logger.info(f"BugMailRead query={query!r} max={self.MAX_RESULTS}")
            result = _execute_single(svc.users().messages().list(
                userId="me", q=query, maxResults=self.MAX_RESULTS,
            ))
            messages = result.get("messages", [])
            logger.info(f"BugMailRead Gmail hit={len(messages)} 件")
            if not messages:
                self.finished.emit([], _empty_stats())
                return

            # 全文 一括 fetch (batch)
            full: dict[str, dict] = {}

            def _cb(rid, resp, exc):
                if exc is None and resp:
                    full[rid] = resp
                else:
                    logger.warning(f"bug mail fetch [{rid}]: {exc}")

            req_map = {
                m["id"]: svc.users().messages().get(
                    userId="me", id=m["id"], format="full",
                )
                for m in messages
            }
            _execute_batch_chunks(svc, req_map, _cb)
            logger.info(f"BugMailRead fetched body={len(full)} 件")

            # subject prefix 필터 ("[LEE v" 또는 "[LEE" 로 시작)
            from app.api.google.gmail import _get_header
            filtered: dict[str, dict] = {}
            for mid, msg in full.items():
                hdrs = msg.get("payload", {}).get("headers", [])
                subj = (_get_header(hdrs, "Subject") or "").strip()
                if subj.startswith("[LEE"):
                    filtered[mid] = msg
            logger.info(
                f"BugMailRead subject filter '[LEE' prefix → {len(filtered)} 件 残"
            )

            # 状態 join + 削除フィルタ
            states = _load_all_states()
            records: list[dict] = []
            for mid, msg in filtered.items():
                st = states.get(mid, {})
                if st.get("deleted"):
                    continue
                records.append(parse_bug_mail(msg, st))

            # Sheets 기반 アクセス申請 추가 — 신청 채널 메일 → 시트 이전.
            # Gmail legacy access 申請 (source=gmail) 와 새 sheet 申請 (source=sheet)
            # 모두 표시되며, 상태 변경 시 source 에 맞춰 백엔드 dispatch.
            records.extend(fetch_sheet_access_requests())

            # 種別 (kind) は最上位フィルタ — stats も種別範囲内で計算
            if self.kind_f:
                records = [r for r in records if r["kind"] == self.kind_f]

            # 件数 stats — kind 適用後 / status・category・search 適用前
            s = _empty_stats()
            s["total"] = len(records)
            for r in records:
                k = r["status"]
                if k in s:
                    s[k] += 1

            # 残りのフィルタ
            if self.status_f:
                records = [r for r in records if r["status"] == self.status_f]
            if self.category_f:
                records = [r for r in records if r["category"] == self.category_f]
            if self.search:
                q = self.search.lower()
                records = [
                    r for r in records
                    if q in r["summary"].lower() or q in r["detail"].lower()
                ]

            # 受信日時 降順
            records.sort(key=lambda r: r["created_at"], reverse=True)

            logger.info(
                f"BugMailRead 完了 — 表示 {len(records)} / 全 {s['total']} 件 "
                f"(open={s['open']} wip={s['wip']} fixed={s['fixed']})"
            )
            self.finished.emit(records, s)
        except Exception as e:
            logger.error(f"BugMailReadWorker error: {e}", exc_info=True)
            self.error.emit(str(e))
            # 위젯 cleanup 보장 — 빈 결과로도 finished
            self.finished.emit([], _empty_stats())


def _empty_stats() -> dict:
    return {"total": 0, "open": 0, "wip": 0, "fixed": 0, "wontfix": 0}
