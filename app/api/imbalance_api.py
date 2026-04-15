"""
インバランス単価 API 通信モジュール
"""
import logging
import requests
import csv
import sqlite3
from PySide6.QtCore import QThread, Signal
from app.api.base import BaseWorker
from app.core.config import DB_IMBALANCE, API_IMBALANCE_BASE, DATE_COL_IDX, TIME_COL_IDX
from app.core.database import get_db_connection

logger = logging.getLogger(__name__)

class UpdateImbalanceWorker(BaseWorker):
    finished = Signal(str)

    def run(self):
        try:
            logger.info("インバランス単価のデータ取得を開始します。")
            s    = requests.Session()
            s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

            r        = s.get(f"{API_IMBALANCE_BASE}/imbalance-price-list/priceList", timeout=15)
            r.raise_for_status()
            csv_path = r.json()["imbalance_list"][0]["path"]

            r = s.get(f"{API_IMBALANCE_BASE}/public/price/{csv_path}", timeout=30)
            r.raise_for_status()
            csv_content = r.content.decode('cp932', errors='replace')
            logger.info("CSVデータのダウンロードに成功しました。DBへの保存を開始します。")

            # Pandas 제거: 내장 csv 파서 사용
            reader = csv.reader(csv_content.splitlines())
            for _ in range(3):
                next(reader, None)  # 첫 3줄 스킵
                
            headers = next(reader, None)
            if not headers:
                raise ValueError("CSVのヘッダーが見つかりません。")
            headers = [str(h).strip().replace('\ufeff', '') for h in headers]
            
            # Pandas가 수행해주던 중복 컬럼명 방지 처리 (예: 変更S -> 変更S_1)
            seen = {}
            unique_headers = []
            for h in headers:
                if h in seen:
                    seen[h] += 1
                    unique_headers.append(f"{h}_{seen[h]}")
                else:
                    seen[h] = 0
                    unique_headers.append(h)
            headers = unique_headers
            
            rows = []
            for row in reader:
                if not row: continue
                # CSV 하단의 꼬리말이나 잘못된 빈 줄을 건너뛰는 방어 로직
                if len(row) != len(headers):
                    continue
                clean_row = [val.replace(',', '').strip() if isinstance(val, str) else val for val in row]
                rows.append(clean_row)

            with get_db_connection(DB_IMBALANCE) as conn:
                cols_def = ", ".join([f'"{h}" TEXT' for h in headers])
                placeholders = ", ".join(["?"] * len(headers))
                date_col = headers[DATE_COL_IDX]
                time_col = headers[TIME_COL_IDX]

                # 기존 스키마와 비교하여 변경된 경우에만 테이블 재생성
                existing_cols = [row[1] for row in conn.execute("PRAGMA table_info(imbalance_prices)").fetchall()]
                schema_changed = (existing_cols != headers)

                if schema_changed:
                    # 안전한 테이블 스왑: 신규 데이터를 임시 테이블에 먼저 저장한 뒤 교체
                    logger.info(f"スキーマ変更を検出。テーブルを再作成します。(旧:{len(existing_cols)}列 → 新:{len(headers)}列)")
                    conn.execute("DROP TABLE IF EXISTS imbalance_prices_new")
                    conn.execute(f"CREATE TABLE imbalance_prices_new ({cols_def})")
                    conn.executemany(f"INSERT INTO imbalance_prices_new VALUES ({placeholders})", rows)
                    conn.execute("DROP TABLE IF EXISTS imbalance_prices")
                    conn.execute("ALTER TABLE imbalance_prices_new RENAME TO imbalance_prices")
                else:
                    # 스키마 동일: 기존 데이터 유지하며 행 단위 갱신 (데이터 손실 없음)
                    conn.executemany(f"INSERT OR REPLACE INTO imbalance_prices VALUES ({placeholders})", rows)

                conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS idx_imb_dt ON imbalance_prices ("{date_col}", "{time_col}")')
                conn.commit()
                logger.info(f"DB更新が完了しました。 (処理行数: {len(rows)}行)")

            self.finished.emit("DB更新が完了しました。")
        except requests.exceptions.RequestException as e:
            logger.error(f"インバランス単価のCSVダウンロード中に通信エラーが発生しました: {str(e)}")
            self.error.emit(f"通信エラー: {str(e)}")
        except (ValueError, csv.Error) as e:
            logger.error(f"インバランス単価のCSV解析中にエラーが発生しました: {str(e)}")
            self.error.emit(f"CSV解析エラー: {str(e)}")
        except sqlite3.Error as e:
            logger.error(f"インバランス単価のDB保存中にエラーが発生しました: {str(e)}")
            self.error.emit(f"DB保存エラー: {str(e)}")
        except Exception as e:
            logger.error(f"インバランス単価の更新中に予期せぬエラーが発生しました: {str(e)}", exc_info=True)
            self.error.emit(f"予期せぬエラー: {str(e)}")