"""
発電所稼働状況 (HJKS) API 通信および集計モジュール
"""
import ssl
import time
import random
import requests
import sqlite3
import logging
from urllib3.util.ssl_ import create_urllib3_context
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from PySide6.QtCore import QThread, QObject, Signal
from app.api.base import BaseWorker
from app.core.config import DB_HJKS, HJKS_REGIONS, HJKS_METHODS
from app.core.database import get_db_connection
from app.models.data_models import HjksRecord

# urllib3.disable_warnings() はプロセス全体に影響するため使用しない。
# LegacySSLAdapter は証明書検証を維持したまま暗号スイートのみ緩和する設計のため、
# InsecureRequestWarning は発生しない。

logger = logging.getLogger(__name__)

class LegacySSLAdapter(requests.adapters.HTTPAdapter):
    """JEPX の古い TLS 暗号スイートに対応するアダプター。
    証明書検証は維持しつつ、暗号スイートのセキュリティレベルのみ緩和します。
    (CERT_NONE は使用しない — MITM 攻撃防止のため)
    """
    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        ctx = create_urllib3_context()
        try:
            # JEPX が使用する古い暗号スイートに対応するため SECLEVEL=1 に緩和
            ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        except ssl.SSLError:
            pass
        # 証明書検証とホスト名確認は有効のまま維持
        pool_kwargs['ssl_context'] = ctx
        return super().init_poolmanager(connections, maxsize, block, **pool_kwargs)

class FetchHjksWorker(BaseWorker):
    finished = Signal(str)

    def run(self):
        try:
            logger.info("HJKS 発電所稼働状況のAPIデータ取得を開始します。")
            
            records = []
            with requests.Session() as session:
                session.mount("https://", LegacySSLAdapter())
                
                # 1. 初回アクセス（Cookie取得とエリア一覧の取得）
                session.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                })
                
                main_url = "https://hjks.jepx.or.jp/hjks/unit_status"
                res_main = session.get(main_url, timeout=15)
                soup = BeautifulSoup(res_main.content, 'html.parser')
                
                area_select = soup.find('select', attrs={'name': 'area'})
                area_options = []
                if area_select:
                    for opt in area_select.find_all('option'):
                        val = opt.get('value')
                        txt = opt.text.strip()
                        if val and txt != 'すべて':
                            mapped_name = next((r for r in HJKS_REGIONS if r in txt), txt)
                            area_options.append((mapped_name, val))
                if not area_options:
                    area_options = [(r, str(i)) for i, r in enumerate(HJKS_REGIONS, 1)]

                # フォームトークンを初回レスポンスから一度だけ抽出 — ループ内の再GETを省略
                base_form_data: dict[str, str] = {}
                for inp in soup.find_all('input'):
                    name = inp.get('name')
                    if name:
                        base_form_data[name] = inp.get('value', '')

                ajax_url = "https://hjks.jepx.or.jp/hjks/unit_status_ajax"

                # 3. 順次取得 (同一セッションのKeep-Aliveを使うため高速)
                for region_name, area_val in area_options:
                    session.headers.pop("X-Requested-With", None)
                    session.headers.update({"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})

                    form_data = {**base_form_data, 'area': area_val}

                    # サーバー側のセッションに選択エリアを認識させるための完全なPOST送信
                    session.post(main_url, data=form_data, timeout=10)
                    
                    # AJAX通信用にヘッダーを切り替え
                    session.headers.update({
                        "Accept": "application/json, text/javascript, */*; q=0.01",
                        "X-Requested-With": "XMLHttpRequest",
                        "Referer": main_url
                    })
                    
                    cb = random.randint(0, 999_999_999)
                    res = session.get(ajax_url, params={"_": cb}, timeout=10)
                    
                    try:
                        data = res.json()
                    except ValueError as e:
                        logger.warning(f"HJKS JSON解析失敗 (エリア: {region_name}): {e}")
                        continue
                        
                    if not data or 'startdtList' not in data:
                        continue
                        
                    dates = data['startdtList']
                    op_series = {item['name']: item['data'] for item in data.get('unitStatusSeriesList', [])}
                    st_series = {item['name']: item['data'] for item in data.get('unitStopStatusSeriesList', [])}
                    
                    for i, dt_str in enumerate(dates):
                        try:
                            parsed_dt = datetime.strptime(dt_str, "%Y/%m/%d").strftime("%Y-%m-%d")
                        except ValueError:
                            continue
                            
                        for api_method in op_series.keys():
                            op_kw = op_series[api_method][i] if i < len(op_series[api_method]) else 0
                            st_kw_list = st_series.get(api_method, [])
                            st_kw = st_kw_list[i] if i < len(st_kw_list) else 0
                            
                            method = api_method if api_method in HJKS_METHODS else "その他"
                            
                            records.append(HjksRecord(
                                date=parsed_dt,
                                region=region_name,
                                method=method,
                                operating_kw=float(op_kw),
                                stopped_kw=float(st_kw)
                            ))
                    # WAF対策の微小スリープ
                    time.sleep(0.1)

            if not records:
                raise ValueError("APIから取得したデータが0件です。(通信拒否またはデータなし)")

            # Pandas 제거: 순수 Python을 이용한 고속 Group By 집계 연산
            agg_data = {}
            for r in records:
                key = (r.date, r.region, r.method)
                if key not in agg_data:
                    agg_data[key] = {"op": 0.0, "st": 0.0}
                agg_data[key]["op"] += r.operating_kw
                agg_data[key]["st"] += r.stopped_kw
            
            with get_db_connection(DB_HJKS) as conn:
                conn.execute("DROP TABLE IF EXISTS hjks_capacity")
                conn.execute("CREATE TABLE hjks_capacity (date TEXT, region TEXT, method TEXT, operating_kw REAL, stopped_kw REAL)")
                insert_rows = [(k[0], k[1], k[2], v["op"], v["st"]) for k, v in agg_data.items()]
                conn.executemany("INSERT INTO hjks_capacity VALUES (?, ?, ?, ?, ?)", insert_rows)
                conn.commit()
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_hjks_cap_date "
                    "ON hjks_capacity(date)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_hjks_cap_date_region "
                    "ON hjks_capacity(date, region)"
                )

            logger.info("HJKS DB更新が完了しました。")
            self.finished.emit("データ取得およびDB更新完了")

        except requests.exceptions.RequestException as e:
            logger.error(f"HJKS データ取得中の通信エラー: {str(e)}")
            self.error.emit(f"通信エラー: {str(e)}")
        except (ValueError, KeyError) as e:
            logger.error(f"HJKS API応答の解析エラー: {str(e)}")
            self.error.emit(f"API応答の解析エラー: {str(e)}")
        except sqlite3.Error as e:
            logger.error(f"HJKS DB保存エラー: {str(e)}")
            self.error.emit(f"DB保存エラー: {str(e)}")
        except Exception as e:
            logger.error(f"HJKS データ取得中に予期せぬエラーが発生しました: {str(e)}", exc_info=True)
            self.error.emit(f"予期せぬエラー: {str(e)}")

class AggregateHjksTask(QObject):
    """현대화된 QObject 기반 Worker 및 SQLite 집계 오프로딩 적용"""
    finished = Signal(list, list)

    def run(self):
        base_daily_data = []
        dates_str = []
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            with get_db_connection(DB_HJKS) as conn:
                query = """
                    WITH target_dates AS (
                        SELECT DISTINCT date FROM hjks_capacity
                        WHERE date >= ? ORDER BY date LIMIT 14
                    )
                    SELECT h.date, h.region, h.method, SUM(h.operating_kw), SUM(h.stopped_kw)
                    FROM hjks_capacity h
                    WHERE h.date IN (SELECT date FROM target_dates)
                    GROUP BY h.date, h.region, h.method
                    ORDER BY h.date
                """
                rows = conn.execute(query, [today_str]).fetchall()
        except sqlite3.Error as e:
            logger.error(f"HJKS DB 집계 데이터 로드 실패: {e}")
            rows = []
        except Exception as e:
            logger.error(f"HJKS 집계 중 예기치 않은 오류: {e}", exc_info=True)
            rows = []

        if rows:
            unique_dates = sorted(list(set(r[0] for r in rows)))
            dates_str = unique_dates
            
            # SQLite에서 이미 집계된 데이터를 즉시 Dictionary로 할당 (Python 연산 오버헤드 제거)
            day_dicts = {dt: {r: {m: {"op": 0, "st": 0} for m in HJKS_METHODS} for r in HJKS_REGIONS} for dt in unique_dates}
            
            for row in rows:
                dt, r, m, op, st = row
                if dt in day_dicts and r in day_dicts[dt] and m in day_dicts[dt][r]:
                    day_dicts[dt][r][m]["op"] = op
                    day_dicts[dt][r][m]["st"] = st
                    
            base_daily_data = [day_dicts[dt] for dt in unique_dates]
        else:
            base_date = datetime.now().date()
            dates_str = [(base_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(14)]
            base_daily_data = [{r: {m: {"op": 0, "st": 0} for m in HJKS_METHODS} for r in HJKS_REGIONS} for _ in range(14)]

        self.finished.emit(base_daily_data, dates_str)