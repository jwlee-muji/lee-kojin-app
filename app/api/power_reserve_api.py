"""
電力予備率(OCCTO) API 通信モジュール
"""
import logging
import requests
from PySide6.QtCore import Signal
from app.api.base import BaseWorker, HTTP_TIMEOUT
from app.core.config import API_OCCTO_RESERVE

logger = logging.getLogger(__name__)


class FetchPowerReserveWorker(BaseWorker):
    """BaseWorker 継承により共通の error シグナルと _emit_error() を利用します。"""
    data_fetched = Signal(list, list)

    def __init__(self, target_date_str):
        super().__init__()
        self.target_date_str = target_date_str

    def run(self):
        with requests.Session() as session:
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest"
            })

            try:
                logger.info(f"OCCTO 電力予備率データ({self.target_date_str})のAPI取得を開始します。")
                params = {"inputDate": self.target_date_str.replace("-", "/")}

                res = session.get(API_OCCTO_RESERVE, params=params, timeout=HTTP_TIMEOUT)
                res.raise_for_status()

                if "application/json" not in res.headers.get("Content-Type", ""):
                    raise ValueError("APIからの応答がJSON形式ではありません。")

                data = res.json()
                area_list = data.get("todayAreaRsvRateList")
                if not area_list:
                    self.data_fetched.emit([], [])
                    return

                AREA_MAP = {1: "北海道", 2: "東北", 3: "東京", 4: "中部", 5: "北陸", 6: "関西", 7: "中国", 8: "四国", 9: "九州", 10: "沖縄"}
                processed_areas = []

                for a in area_list:
                    cd = int(a.get("areaCd", 99))
                    items = a.get("areaRsvRateItems", [])
                    val_map = {}
                    for i, item in enumerate(items):
                        val = item.get("koikRsvRate")
                        if val is None: val = item.get("areaRsvRate", item.get("rsvRate"))
                        t_time = item.get("targetTime")
                        val_map[t_time if t_time else f"{i // 2:02d}:{(i % 2) * 30:02d}"] = val
                    processed_areas.append({"cd": cd, "val_map": val_map})

                processed_areas.sort(key=lambda x: x["cd"])
                headers = ["時間"] + [AREA_MAP.get(pa["cd"], f"エリア{pa['cd']}") for pa in processed_areas]

                final_rows = []
                for time_idx in range(48):
                    time_str = f"{time_idx // 2:02d}:{(time_idx % 2) * 30:02d}"
                    row_data = [time_str]
                    for pa in processed_areas:
                        val = pa["val_map"].get(time_str)
                        row_data.append(f"{float(val):.1f}%" if val is not None else "-")
                    final_rows.append(row_data)

                logger.info(f"OCCTO APIからのデータ抽出が完了しました。 (行数: {len(final_rows)}行)")
                self.data_fetched.emit(headers, final_rows)
            except requests.exceptions.RequestException as e:
                self._emit_error(f"通信エラーが発生しました", e)
            except (ValueError, KeyError, TypeError) as e:
                self._emit_error(f"API応答の解析エラー", e)
            except Exception as e:
                self._emit_error(f"予期せぬエラーが発生しました", e)