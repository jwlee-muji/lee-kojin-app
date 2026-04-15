import re
import sqlite3
import shutil
import logging
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timedelta
from app.core.config import DB_IMBALANCE, DB_HJKS, DB_JKM, BACKUP_DIR

logger = logging.getLogger(__name__)

# pragma_table_info 由来のカラム名に使える文字 (日本語・英数・スペース・括弧など)
_SAFE_COL_RE = re.compile(r'^[\w\s\(\)\-\./\u3000-\u9fff\uff00-\uffef]+$')


def validate_column_name(name: str) -> str:
    """カラム名に SQL インジェクションのリスクがある文字が含まれていないことを検証します。
    不正な場合は ValueError を送出します。"""
    if not name or not _SAFE_COL_RE.match(name):
        raise ValueError(f"不正なカラム名が検出されました: {name!r}")
    return name

@contextmanager
def get_db_connection(db_path: Path):
    """
    통합 DB 커넥션 관리자 (Context Manager)
    - 기존 현재 폴더에 있던 DB 파일을 APPDATA 폴더로 자동 마이그레이션
    - WAL 모드 활성화로 UI 멈춤 방지 및 동시성 대폭 향상
    """
    old_path = Path(db_path.name)
    if old_path.exists() and not db_path.exists():
        try:
            shutil.move(str(old_path), str(db_path))
            logger.info(f"DBファイルの移行完了: {old_path} -> {db_path}")
        except Exception as e:
            logger.error(f"DBファイルの移行失敗: {e}")

    conn = sqlite3.connect(str(db_path), timeout=15.0)
    try:
        conn.execute('PRAGMA journal_mode=WAL;')
        yield conn
    finally:
        conn.close()


def run_retention_policy(retention_days: int):
    """지정된 일수(days)가 지난 과거 데이터를 백업하고 메인 DB에서 삭제 (최적화)"""
    if retention_days <= 0:
        return
        
    threshold_dt = datetime.now() - timedelta(days=retention_days)
    str_dash = threshold_dt.strftime("%Y-%m-%d")
    int_yyyymmdd = int(threshold_dt.strftime("%Y%m%d"))
    
    try:
        _backup_and_delete_imbalance(int_yyyymmdd)
        _backup_and_delete_hjks(str_dash)
        _backup_and_delete_jkm(str_dash)
    except Exception as e:
        logger.error(f"データ寿命管理(バックアップと削除)の実行中にエラーが発生しました: {e}")

def _attach_backup_db(conn: sqlite3.Connection, backup_path: Path) -> None:
    """ATTACH DATABASE を安全に実行します。
    ATTACH はパラメータバインディング非対応のため、シングルクォートをエスケープして注入を防ぎます。"""
    safe_path = str(backup_path.resolve()).replace("'", "''")
    conn.execute(f"ATTACH DATABASE '{safe_path}' AS backup_db")


def _backup_and_delete_imbalance(threshold_int: int):
    if not DB_IMBALANCE.exists(): return
    with get_db_connection(DB_IMBALANCE) as conn:
        cols = conn.execute("SELECT name FROM pragma_table_info('imbalance_prices')").fetchall()
        if len(cols) < 2: return
        date_col = validate_column_name(cols[1][0])

        count = conn.execute(f'SELECT COUNT(*) FROM imbalance_prices WHERE CAST("{date_col}" AS INTEGER) < ?', (threshold_int,)).fetchone()[0]
        if count == 0: return

        backup_db = BACKUP_DIR / 'backup_imbalance.db'
        _attach_backup_db(conn, backup_db)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS backup_db.imbalance_prices AS SELECT * FROM imbalance_prices WHERE 0")
            conn.execute(f'INSERT OR IGNORE INTO backup_db.imbalance_prices SELECT * FROM imbalance_prices WHERE CAST("{date_col}" AS INTEGER) < ?', (threshold_int,))
            conn.execute(f'DELETE FROM imbalance_prices WHERE CAST("{date_col}" AS INTEGER) < ?', (threshold_int,))
            conn.commit()  # 트랜잭션 확정 및 Lock 해제
        finally:
            conn.execute("DETACH DATABASE backup_db")
            
        _vacuum_safely(conn, "インバランス単価")
        logger.info(f"インバランス単価の古いデータ({count}件)をバックアップし削除しました。")

def _backup_and_delete_hjks(threshold_str: str):
    if not DB_HJKS.exists(): return
    with get_db_connection(DB_HJKS) as conn:
        if not conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hjks_capacity'").fetchone(): return
        count = conn.execute("SELECT COUNT(*) FROM hjks_capacity WHERE date < ?", (threshold_str,)).fetchone()[0]
        if count == 0: return

        backup_db = BACKUP_DIR / 'backup_hjks.db'
        _attach_backup_db(conn, backup_db)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS backup_db.hjks_capacity AS SELECT * FROM hjks_capacity WHERE 0")
            conn.execute("INSERT OR IGNORE INTO backup_db.hjks_capacity SELECT * FROM hjks_capacity WHERE date < ?", (threshold_str,))
            conn.execute("DELETE FROM hjks_capacity WHERE date < ?", (threshold_str,))
            conn.commit()
        finally:
            conn.execute("DETACH DATABASE backup_db")

        _vacuum_safely(conn, "HJKS")
        logger.info(f"HJKSの古いデータ({count}件)をバックアップし削除しました。")

def _backup_and_delete_jkm(threshold_str: str):
    if not DB_JKM.exists(): return
    with get_db_connection(DB_JKM) as conn:
        if not conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jkm_prices'").fetchone(): return
        count = conn.execute("SELECT COUNT(*) FROM jkm_prices WHERE date < ?", (threshold_str,)).fetchone()[0]
        if count == 0: return

        backup_db = BACKUP_DIR / 'backup_jkm.db'
        _attach_backup_db(conn, backup_db)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS backup_db.jkm_prices AS SELECT * FROM jkm_prices WHERE 0")
            conn.execute("INSERT OR IGNORE INTO backup_db.jkm_prices SELECT * FROM jkm_prices WHERE date < ?", (threshold_str,))
            conn.execute("DELETE FROM jkm_prices WHERE date < ?", (threshold_str,))
            conn.commit()
        finally:
            conn.execute("DETACH DATABASE backup_db")

        _vacuum_safely(conn, "JKM")
        logger.info(f"JKMの古いデータ({count}件)をバックアップし削除しました。")


def _vacuum_safely(conn: sqlite3.Connection, db_label: str) -> None:
    """VACUUM を安全に実行します。
    isolation_level の変更前に元の値を保存し、finally で必ず復元します。"""
    original_isolation = conn.isolation_level
    try:
        conn.isolation_level = None   # VACUUM は autocommit モードでのみ実行可能
        conn.execute("VACUUM")
    except sqlite3.OperationalError as e:
        logger.warning(f"{db_label} DBのVACUUMをスキップしました (使用中): {e}")
    finally:
        try:
            conn.isolation_level = original_isolation
        except Exception:
            pass  # クローズ直前のコネクションでも安全に続行