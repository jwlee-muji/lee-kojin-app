import sqlite3
import logging
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Google Drive 공유 폴더 경로 설정 (팀 공용)
SHARED_DRIVE_BASE = Path(r"G:\共有ドライブ\S.PPS事業推進チーム\99_個人用\むじ\app\db")
SHARED_DB_PATH = SHARED_DRIVE_BASE / "shared_manual.db"
SHARED_IMAGE_DIR = SHARED_DRIVE_BASE / "images"

def init_shared_db():
    """공유 드라이브 폴더 및 데이터베이스 테이블을 초기화합니다."""
    if not SHARED_DRIVE_BASE.exists():
        logger.warning(f"Google Drive 경로를 찾을 수 없습니다: {SHARED_DRIVE_BASE}")
        return
        
    SHARED_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    
    with get_shared_db() as conn:
        try:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(manuals)").fetchall()]
            if cols and "category" not in cols:
                conn.execute("ALTER TABLE manuals ADD COLUMN category TEXT DEFAULT '未分類'")
            if cols and "tags" not in cols:
                conn.execute("ALTER TABLE manuals ADD COLUMN tags TEXT DEFAULT ''")
            if cols and "sort_order" not in cols:
                conn.execute("ALTER TABLE manuals ADD COLUMN sort_order INTEGER DEFAULT 0")
                
            conn.execute("""
                CREATE TABLE IF NOT EXISTS manual_categories (
                    name TEXT PRIMARY KEY,
                    sort_order INTEGER DEFAULT 0
                )
            """)
        except Exception as e:
            logger.error(f"マニュアルDBマイグレーションエラー: {e}")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS manuals (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT DEFAULT '未分類',
                tags TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0,
                content TEXT NOT NULL,
                author_email TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS manual_comments (
                id TEXT PRIMARY KEY,
                manual_id TEXT NOT NULL,
                author_email TEXT NOT NULL,
                comment_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(manual_id) REFERENCES manuals(id) ON DELETE CASCADE
            )
        """)
        conn.commit()

@contextmanager
def get_shared_db():
    """공유 드라이브용 SQLite 커넥션. 파일 동기화 충돌 방지를 위해 WAL 모드 사용 금지."""
    conn = sqlite3.connect(str(SHARED_DB_PATH), timeout=20.0)  # 동기화 지연 대비 넉넉한 타임아웃
    try:
        conn.execute('PRAGMA journal_mode=TRUNCATE;')  # WAL 금지
        yield conn
    finally:
        conn.close()