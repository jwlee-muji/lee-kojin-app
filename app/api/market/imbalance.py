"""
インバランス単価 API 通信モジュール
/imbalance-price-list/priceList JSON API から全月リストを取得し、
リビジョン差分のみ DB に保存する。
"""
import csv
import logging
import re
import time

import requests
from PySide6.QtCore import Signal

from app.api.base import BaseWorker
from app.core.config import DB_IMBALANCE, API_IMBALANCE_BASE, DATE_COL_IDX, TIME_COL_IDX
from app.core.database import get_db_connection

logger = logging.getLogger(__name__)

_PATH_RE = re.compile(r'(\d{6})_imbalance-price_(\d{2})\.csv')


# ── CSV パーサー ────────────────────────────────────────────────────────────────

def _parse_imbalance_csv(csv_content: str) -> tuple[list[str], list[list[str]]]:
    """CSVを解析して (ヘッダーリスト, 行リスト) を返す。
    - 先頭3行スキップ (H メタ行)
    - 重複カラム名には _1, _2 ... サフィックス付与
    - カラム数不一致行・空行はスキップ
    - 数値内カンマ除去・空白トリム
    """
    reader = csv.reader(csv_content.splitlines())
    for _ in range(3):
        next(reader, None)

    headers = next(reader, None)
    if not headers:
        raise ValueError("CSVのヘッダーが見つかりません。")
    headers = [str(h).strip().replace('﻿', '') for h in headers]

    seen: dict[str, int] = {}
    unique_headers: list[str] = []
    for h in headers:
        if h in seen:
            seen[h] += 1
            unique_headers.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            unique_headers.append(h)
    headers = unique_headers

    rows: list[list[str]] = []
    for row in reader:
        if not row:
            continue
        if len(row) != len(headers):
            continue
        rows.append([val.replace(',', '').strip() if isinstance(val, str) else val for val in row])

    return headers, rows


# ── DB ヘルパー ─────────────────────────────────────────────────────────────────

def _ensure_meta_table(conn) -> None:
    """月別ダウンロード済みリビジョンを管理するメタテーブルを作成する。"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS imbalance_meta (
            yyyymm   TEXT PRIMARY KEY,
            revision INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.commit()


def _get_downloaded_revisions(conn) -> dict[str, int]:
    """DBに保存済みの月別リビジョン番号を返す。{yyyymm: revision}"""
    _ensure_meta_table(conn)
    rows = conn.execute("SELECT yyyymm, revision FROM imbalance_meta").fetchall()
    return {row[0]: row[1] for row in rows}


def _save_revision(conn, yyyymm: str, revision: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO imbalance_meta (yyyymm, revision) VALUES (?, ?)",
        (yyyymm, revision)
    )
    conn.commit()


def _ensure_schema_and_upsert(conn, headers: list[str], rows: list[list[str]]) -> None:
    """テーブル作成/列拡張 → UPSERT。スキーマに無い新規列は ALTER TABLE で追加する。"""
    existing_cols = [
        row[1].strip()
        for row in conn.execute("PRAGMA table_info(imbalance_prices)").fetchall()
    ]

    if not existing_cols:
        cols_def = ", ".join([f'"{h}" TEXT' for h in headers])
        conn.execute(f"CREATE TABLE imbalance_prices ({cols_def})")
        date_col = headers[DATE_COL_IDX]
        time_col = headers[TIME_COL_IDX]
        conn.execute(
            f'CREATE UNIQUE INDEX IF NOT EXISTS idx_imb_dt '
            f'ON imbalance_prices ("{date_col}", "{time_col}")'
        )
    else:
        for h in headers:
            if h not in existing_cols:
                conn.execute(f'ALTER TABLE imbalance_prices ADD COLUMN "{h}" TEXT')
                logger.info(f"インバランスDB: 新規列追加 {h!r}")

    current_cols = [
        row[1].strip()
        for row in conn.execute("PRAGMA table_info(imbalance_prices)").fetchall()
    ]
    insert_headers = [h for h in headers if h in current_cols]
    indices        = [headers.index(h) for h in insert_headers]
    cols_str       = ", ".join([f'"{h}"' for h in insert_headers])
    placeholders   = ", ".join(["?"] * len(insert_headers))

    filtered_rows = [[row[i] for i in indices] for row in rows]
    conn.executemany(
        f'INSERT OR REPLACE INTO imbalance_prices ({cols_str}) VALUES ({placeholders})',
        filtered_rows
    )
    conn.commit()


# ── API ヘルパー ────────────────────────────────────────────────────────────────

def _fetch_month_list(session: requests.Session) -> list[tuple[str, str, int]]:
    """JSON API から全月の (yyyymm, path, revision) リストを返す。新しい月順。
    path は public/price/ を含まない相対パス。
    """
    r = session.get(
        f"{API_IMBALANCE_BASE}/imbalance-price-list/priceList",
        timeout=15,
    )
    r.raise_for_status()
    items = r.json().get("imbalance_list", [])

    result: list[tuple[str, str, int]] = []
    for item in items:
        path = item.get("path", "")
        m = _PATH_RE.search(path)
        if not m:
            logger.debug(f"パス解析スキップ: {path!r}")
            continue
        yyyymm = m.group(1)
        rev    = int(m.group(2))
        result.append((yyyymm, path, rev))

    logger.info(f"インバランスCSV月リスト取得: {len(result)}件")
    return result


# ── Worker ─────────────────────────────────────────────────────────────────────

class UpdateImbalanceWorker(BaseWorker):
    finished = Signal(str)
    progress = Signal(str)   # UI ステータスメッセージ

    def run(self):
        try:
            logger.info("インバランス単価: 全量スキャン開始")
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })

            # Step 1: API から全月リスト取得
            self.progress.emit("月リストを取得中...")
            month_list = _fetch_month_list(session)
            if not month_list:
                self.error.emit("月リストの取得に失敗しました。APIレスポンスを確認してください。")
                return

            # Step 2: DBに保存済みのリビジョンを確認
            with get_db_connection(DB_IMBALANCE) as conn:
                downloaded = _get_downloaded_revisions(conn)

            # Step 3: ダウンロード対象月を決定
            #   - 当月: 常に再取得 (月途中でデータが追加されるため)
            #   - 過去月: サイトのリビジョンがDB保存済みより新しい場合のみ
            from datetime import date
            current_yyyymm = date.today().strftime("%Y%m")

            targets: list[tuple[str, str, int]] = []
            for yyyymm, path, site_rev in month_list:
                db_rev = downloaded.get(yyyymm, -1)
                if yyyymm == current_yyyymm or site_rev > db_rev:
                    targets.append((yyyymm, path, site_rev))

            if not targets:
                self.finished.emit("データは最新です。")
                return

            # 古い月から順にダウンロード
            targets.sort(key=lambda x: x[0])
            logger.info(f"インバランス: {len(targets)}件のダウンロードを開始")

            # Step 4: ダウンロード → DB保存 → リビジョン記録
            saved = 0
            for i, (yyyymm, path, rev) in enumerate(targets, 1):
                year_s, month_s = yyyymm[:4], yyyymm[4:]
                self.progress.emit(
                    f"({i}/{len(targets)}) {year_s}年{month_s}月 取得中... (rev={rev})"
                )

                try:
                    url = f"{API_IMBALANCE_BASE}/public/price/{path}"
                    r = session.get(url, timeout=30)
                    r.raise_for_status()
                    csv_content = r.content.decode('cp932', errors='replace')
                    headers, rows = _parse_imbalance_csv(csv_content)

                    if rows:
                        with get_db_connection(DB_IMBALANCE) as conn:
                            _ensure_schema_and_upsert(conn, headers, rows)
                            _save_revision(conn, yyyymm, rev)
                        saved += 1
                        logger.info(
                            f"インバランス {year_s}年{month_s}月: {len(rows)}行保存 (rev={rev})"
                        )

                except requests.HTTPError as e:
                    logger.warning(f"インバランス {yyyymm} HTTP エラー: {e}")
                except Exception as e:
                    logger.warning(f"インバランス {yyyymm} 取得失敗: {e}")

                time.sleep(0.5)

            msg = f"更新完了 ({saved}/{len(targets)}件)"
            logger.info(msg)
            self.finished.emit(msg)

        except requests.exceptions.RequestException as e:
            logger.error(f"インバランス通信エラー: {e}")
            self.error.emit(f"通信エラー: {str(e)}")
        except Exception as e:
            logger.error(f"インバランス更新エラー: {e}", exc_info=True)
            self.error.emit(f"予期せぬエラー: {str(e)}")
