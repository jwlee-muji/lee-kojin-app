import ssl
import time
import requests
import sqlite3
import urllib3
import pandas as pd
import logging
import pyqtgraph as pg
from urllib3.util.ssl_ import create_urllib3_context
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QSplitter, QFrame, QMessageBox, QApplication, QGraphicsDropShadowEffect
)
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QColor
from app.core.config import DB_HJKS, HJKS_REGIONS, HJKS_METHODS, HJKS_COLORS, load_settings
from app.core.database import get_db_connection
from app.ui.common import BaseWidget

pg.setConfigOptions(antialias=True)

# SSL 인증서 경고 무시 (JEPX 사이트 SSL 우회용)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class LegacySSLAdapter(requests.adapters.HTTPAdapter):
    """JEPX等の古いSSL設定を回避するためのアダプター"""
    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        ctx = create_urllib3_context()
        try:
            ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        except ssl.SSLError:
            pass
            
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        pool_kwargs['ssl_context'] = ctx
        return super().init_poolmanager(connections, maxsize, block, **pool_kwargs)


class FetchHjksWorker(QThread):
    finished = Signal(str)
    error    = Signal(str)

    def run(self):
        try:
            logger.info("HJKS 発電所稼働状況のAPIデータ取得を開始します。")
            
            records = []
            with requests.Session() as session:
                session.verify = False
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

                ajax_url = "https://hjks.jepx.or.jp/hjks/unit_status_ajax"
                
                # 3. 順次取得 (同一セッションのKeep-Aliveを使うため10回でも非常に高速です)
                for region_name, area_val in area_options:
                    # HTML用ヘッダーに戻してメインページにアクセスし、セキュリティトークンを取得
                    if "X-Requested-With" in session.headers:
                        del session.headers["X-Requested-With"]
                    session.headers.update({"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
                    
                    res_m = session.get(main_url, timeout=10)
                    soup_m = BeautifulSoup(res_m.content, 'html.parser')
                    
                    form_data = {}
                    for inp in soup_m.find_all('input'):
                        name = inp.get('name')
                        if name:
                            form_data[name] = inp.get('value', '')
                    form_data['area'] = area_val
                    
                    # サーバー側のセッションに選択エリアを認識させるための完全なPOST送信
                    session.post(main_url, data=form_data, timeout=10)
                    
                    # AJAX通信用にヘッダーを切り替え
                    session.headers.update({
                        "Accept": "application/json, text/javascript, */*; q=0.01",
                        "X-Requested-With": "XMLHttpRequest",
                        "Referer": main_url
                    })
                    
                    cb = int(time.time() * 1000)
                    res = session.get(ajax_url, params={"_": cb}, timeout=10)
                    
                    try:
                        data = res.json()
                    except Exception:
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
                            
                            records.append({
                                "date": parsed_dt,
                                "region": region_name,
                                "method": method,
                                "operating_kw": op_kw,
                                "stopped_kw": st_kw
                            })
                    # WAF対策の微小スリープ
                    time.sleep(0.1)

            if not records:
                raise ValueError("APIから取得したデータが0件です。(通信拒否またはデータなし)")

            df = pd.DataFrame(records)
            df = df.groupby(['date', 'region', 'method'], as_index=False).sum()
            
            with get_db_connection(DB_HJKS) as conn:
                df.to_sql('hjks_capacity', conn, if_exists='replace', index=False)

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


class AggregateHjksWorker(QThread):
    finished = Signal(list, list)

    def run(self):
        base_daily_data = []
        dates_str = []
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            with get_db_connection(DB_HJKS) as conn:
                # LIMIT 140 を排除し、日付ベースで正確に14日分を取得
                query = """
                    SELECT * FROM hjks_capacity WHERE date IN (
                        SELECT DISTINCT date FROM hjks_capacity WHERE date >= ? ORDER BY date LIMIT 14
                    ) ORDER BY date
                """
                df = pd.read_sql(query, conn, params=[today_str])
        except sqlite3.Error as e:
            logger.error(f"HJKS DB 집계 데이터 로드 실패: {e}")
            df = pd.DataFrame()
        except Exception as e:
            logger.error(f"HJKS 집계 중 예기치 않은 오류: {e}", exc_info=True)
            df = pd.DataFrame()

        if not df.empty and 'region' in df.columns:
            unique_dates = sorted(df['date'].unique())
            dates_str = unique_dates
            for dt in unique_dates:
                day_df = df[df['date'] == dt]
                day_dict = {r: {m: {"op": 0, "st": 0} for m in HJKS_METHODS} for r in HJKS_REGIONS}
                for _, row in day_df.iterrows():
                    r = row['region']
                    m = row['method']
                    if r in day_dict and m in day_dict[r]:
                        day_dict[r][m]["op"] += row['operating_kw']
                        day_dict[r][m]["st"] += row['stopped_kw']
                base_daily_data.append(day_dict)
        else:
            base_date = datetime.now().date()
            dates_str = [(base_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(14)]
            base_daily_data = [{r: {m: {"op": 0, "st": 0} for m in HJKS_METHODS} for r in HJKS_REGIONS} for _ in range(14)]

        self.finished.emit(base_daily_data, dates_str)


class HjksWidget(BaseWidget):
    data_updated = Signal()

    def __init__(self):
        super().__init__()
        self.worker = None
        self._base_daily_data = None  # 계산 결과 캐시 저장소
        self._dates_str = []          # 집계 날짜 목록 캐시
        self.aggregated_data = []

        self._build_ui()
        self.fetch_data()

        self.setup_timer(self.settings.get("hjks_interval", 180), self.fetch_data)
        
    def apply_settings_custom(self):
        self.update_timer_interval(self.settings.get("hjks_interval", 180))

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 상단 컨트롤 바
        top = QHBoxLayout()
        title = QLabel(self.tr("発電所 稼働可能容量 推移 (HJKS)"))
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        top.addWidget(title)
        top.addSpacing(20)

        self.refresh_btn = QPushButton(self.tr("データ更新"))
        self.refresh_btn.clicked.connect(self.fetch_data)
        top.addWidget(self.refresh_btn)

        top.addSpacing(15)
        self.status_label = QLabel(self.tr("待機中..."))
        self.status_label.setStyleSheet("color: #aaaaaa;")
        top.addWidget(self.status_label)
        top.addStretch()
        
        # 그래프 복사 버튼
        self.copy_btn = QPushButton(self.tr("グラフ画像をコピー"))
        self.copy_btn.clicked.connect(self._copy_graph)
        top.addWidget(self.copy_btn)
        
        layout.addLayout(top)

        # 메인 스플리터 (좌: 체크박스 영역, 우: 그래프 영역)
        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter, 1)

        # 좌측 지역 선택 패널
        self.left_panel = QFrame()
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(10, 15, 10, 15)
        
        self.lbl_region = QLabel(self.tr("表示エリア選択"))
        self.lbl_region.setStyleSheet("font-weight: bold; color: #eeeeee; border: none; background: transparent;")
        left_layout.addWidget(self.lbl_region)
        
        btn_layout = QHBoxLayout()
        self.btn_select_all = QPushButton(self.tr("全選択"))
        self.btn_deselect_all = QPushButton(self.tr("全解除"))
        self.btn_select_all.setCursor(Qt.PointingHandCursor)
        self.btn_deselect_all.setCursor(Qt.PointingHandCursor)
        self.btn_select_all.clicked.connect(self._select_all_regions)
        self.btn_deselect_all.clicked.connect(self._deselect_all_regions)
        btn_layout.addWidget(self.btn_select_all)
        btn_layout.addWidget(self.btn_deselect_all)
        left_layout.addLayout(btn_layout)
        
        left_layout.addSpacing(5)
        
        self.checkboxes = {}
        for region in HJKS_REGIONS:
            cb = QCheckBox(region)
            cb.setChecked(True)
            cb.setCursor(Qt.PointingHandCursor)
            cb.stateChanged.connect(self._update_chart)
            left_layout.addWidget(cb)
            self.checkboxes[region] = cb
            
        left_layout.addSpacing(15)

        # 발전 방식 범례 표시
        self.leg_title = QLabel(self.tr("【発電方式 凡例】"))
        self.leg_title.setStyleSheet("background: transparent; color: #eeeeee;")
        left_layout.addWidget(self.leg_title)
        left_layout.addSpacing(10)
        self.leg_labels = []
        for method in HJKS_METHODS:
            leg_layout = QHBoxLayout()
            color_box = QLabel()
            color_box.setFixedSize(12, 12)
            color_box.setStyleSheet(f"background-color: {HJKS_COLORS[method]}; border-radius: 2px; border: none;")
            leg_lbl = QLabel(method)
            leg_lbl.setStyleSheet("font-size: 11px; border: none; background: transparent; color: #d4d4d4;")
            self.leg_labels.append(leg_lbl)
            leg_layout.addWidget(color_box)
            leg_layout.addWidget(leg_lbl)
            leg_layout.addStretch()
            left_layout.addLayout(leg_layout)
        left_layout.addStretch()

        self.splitter.addWidget(self.left_panel)

        # 우측 그래프 패널
        self.plot_widget = pg.PlotWidget()
        self.splitter.addWidget(self.plot_widget)
        
        self.splitter.setSizes([180, 720])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        # 호버 툴팁
        self.tooltip_label = QLabel(self.plot_widget.viewport())
        self.tooltip_label.setStyleSheet(
            "QLabel { background-color: rgba(45, 45, 45, 230); border: 1px solid #555555;"
            " border-radius: 6px; padding: 8px 12px; color: #eeeeee; font-size: 12px; }"
        )
        self.tooltip_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        
        self.tooltip_shadow = QGraphicsDropShadowEffect(self)
        self.tooltip_shadow.setBlurRadius(12)
        self.tooltip_shadow.setOffset(2, 3)
        self.tooltip_label.setGraphicsEffect(self.tooltip_shadow)
        self.tooltip_label.hide()

        self.hover_proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self._on_hover
        )

        self.apply_theme_custom()

    def apply_theme_custom(self):
        is_dark = self.is_dark
        self.left_panel.setStyleSheet(f"QFrame {{ background-color: {'#252526' if is_dark else '#fcfcfc'}; border: 1px solid {'#3e3e42' if is_dark else '#eee'}; border-radius: 4px; }}")
        if hasattr(self, 'lbl_region'):
            self.lbl_region.setStyleSheet(f"font-weight: bold; color: {'#eeeeee' if is_dark else '#333'}; border: none; background: transparent;")
        self.leg_title.setStyleSheet(f"font-weight: bold; background: transparent; color: {'#eeeeee' if is_dark else '#333'};")
        if hasattr(self, 'checkboxes'):
            cb_style = f"""
                QCheckBox {{
                    border: none; 
                    padding: 6px 10px; 
                    border-radius: 6px; 
                    background: transparent; 
                    color: {'#d4d4d4' if is_dark else '#333333'};
                    font-size: 13px;
                }}
                QCheckBox:hover {{
                    background-color: {'#333333' if is_dark else '#e8e8e8'};
                }}
            """
            for cb in self.checkboxes.values():
                cb.setStyleSheet(cb_style)
                
        btn_style = f"""
            QPushButton {{
                background-color: {'#333333' if is_dark else '#e0e0e0'};
                color: {'#eeeeee' if is_dark else '#333333'};
                border: none;
                border-radius: 4px;
                padding: 6px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {'#444444' if is_dark else '#d0d0d0'}; }}
            QPushButton:pressed {{ background-color: {'#222222' if is_dark else '#bdbdbd'}; }}
        """
        if hasattr(self, 'btn_select_all'):
            self.btn_select_all.setStyleSheet(btn_style)
            self.btn_deselect_all.setStyleSheet(btn_style)
        for lbl in self.leg_labels:
            lbl.setStyleSheet(f"font-size: 12px; border: none; background: transparent; color: {'#d4d4d4' if is_dark else '#333'};")

        self.plot_widget.setBackground('#1e1e1e' if is_dark else '#ffffff')
        ax_pen = pg.mkPen(color='#555555' if is_dark else '#dddddd', width=1)
        text_pen = pg.mkPen('#aaaaaa' if is_dark else '#666666')
        for ax_name in ('left', 'bottom'):
            ax = self.plot_widget.getAxis(ax_name)
            ax.setPen(ax_pen)
            ax.setTextPen(text_pen)
        self.plot_widget.setLabel('left', '稼働可能容量 (MW)', color='#aaaaaa' if is_dark else '#666666', size='10pt')
        self.tooltip_label.setStyleSheet(
            f"QLabel {{ background-color: {'rgba(45, 45, 45, 230)' if is_dark else 'rgba(255, 255, 255, 230)'}; border: 1px solid {'#555555' if is_dark else '#cccccc'}; border-radius: 6px; padding: 8px 12px; color: {'#eeeeee' if is_dark else '#333333'}; font-size: 12px; }}"
        )

        if hasattr(self, 'tooltip_shadow'):
            self.tooltip_shadow.setColor(QColor(0, 0, 0, 160) if is_dark else QColor(0, 0, 0, 60))

    def _select_all_regions(self):
        for cb in getattr(self, 'checkboxes', {}).values():
            cb.setChecked(True)

    def _deselect_all_regions(self):
        for cb in getattr(self, 'checkboxes', {}).values():
            cb.setChecked(False)

    def fetch_data(self):
        if not self.check_online_status(): return
        try:
            if self.worker and self.worker.isRunning():
                return
        except RuntimeError:
            self.worker = None
        self.refresh_btn.setEnabled(False)
        self.status_label.setText("データ取得中...")
        self.status_label.setStyleSheet("color: #64b5f6;")
        
        self.worker = FetchHjksWorker()
        self.worker.finished.connect(self._on_fetch_success)
        self.worker.error.connect(self._on_fetch_error)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _on_fetch_success(self, msg):
        self.refresh_btn.setEnabled(True)
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("color: #4caf50;")
        self._base_daily_data = None  # 데이터가 갱신되었으므로 캐시 초기화
        self._dates_str = []          # 캐시 초기화에 맞춰 날짜 목록도 리셋
        self._update_chart()
        self.data_updated.emit()

    def _on_fetch_error(self, err_msg):
        self.refresh_btn.setEnabled(True)
        self.status_label.setText("取得失敗")
        self.status_label.setStyleSheet("color: #ff5252;")
        QMessageBox.warning(self, "エラー", err_msg)

    def _update_chart(self):
        # 1. 필요 시 베이스 데이터 캐싱 (DB 읽기 + 10일간의 날짜/에리어/방식별 사전 집계)
        if self._base_daily_data is None:
            try:
                if getattr(self, '_agg_worker', None) and self._agg_worker.isRunning():
                    return
            except RuntimeError:
                self._agg_worker = None
            self._agg_worker = AggregateHjksWorker()
            self._agg_worker.finished.connect(self._on_aggregate_finished)
            self._agg_worker.finished.connect(self._agg_worker.deleteLater)
            self._agg_worker.start()
            return
            
        self._render_chart()
        
    def _on_aggregate_finished(self, base_daily_data, dates_str):
        self._base_daily_data = base_daily_data
        self._dates_str = dates_str
        self._render_chart()

    def _render_chart(self):
        self.plot_widget.clear()

        selected_regions = [r for r, cb in getattr(self, 'checkboxes', {}).items() if cb.isChecked()]
        if not selected_regions or not self._dates_str:
            return

        x_indices = list(range(len(self._dates_str)))
        # X축 날짜 틱 설정
        ticks = [(i, dt[5:].replace('-', '/')) for i, dt in enumerate(self._dates_str)]
        self.plot_widget.getAxis('bottom').setTicks([ticks])
        
        self.aggregated_data = []
        
        # 2. 캐시된 베이스 데이터에서 체크된 에리어들의 데이터만 합산
        for i, dt_str in enumerate(self._dates_str):
            day_dict = self._base_daily_data[i]
            agg_methods = {m: {"op": 0, "st": 0} for m in HJKS_METHODS}
            agg_regions = {r: {"op": 0, "st": 0} for r in HJKS_REGIONS}
            total_op = 0
            total_st = 0
            
            for r in selected_regions:
                r_data = day_dict.get(r, {})
                r_total = sum(d["op"] for d in r_data.values())
                if r_total > 0:
                    agg_regions[r]["op"] = sum(d["op"] for d in r_data.values())
                    agg_regions[r]["st"] = sum(d["st"] for d in r_data.values())
                    total_op += agg_regions[r]["op"]
                    total_st += agg_regions[r]["st"]
                    for m in HJKS_METHODS:
                        agg_methods[m]["op"] += r_data.get(m, {}).get("op", 0)
                        agg_methods[m]["st"] += r_data.get(m, {}).get("st", 0)

            self.aggregated_data.append({
                "date": dt_str,
                "total_op": total_op,
                "total_st": total_st,
                "methods": agg_methods,
                "regions": agg_regions
            })
        
        y0_array_kw = [0] * len(self._dates_str)
        for method in HJKS_METHODS:
            heights_kw = [day["methods"][method]["op"] for day in self.aggregated_data]
            if sum(heights_kw) > 0:
                heights_mw = [h / 1000.0 for h in heights_kw]
                y0_mw      = [y / 1000.0 for y in y0_array_kw]
                bar_item = pg.BarGraphItem(x=x_indices, y0=y0_mw[:], height=heights_mw, width=0.6, brush=HJKS_COLORS[method])
                self.plot_widget.addItem(bar_item)
                for i in range(len(self._dates_str)):
                    y0_array_kw[i] += heights_kw[i]
                
        # 뷰포트 제한
        self.plot_widget.getViewBox().setLimits(xMin=-1, xMax=max(1, len(self._dates_str)), yMin=0)
        
        self.plot_widget.enableAutoRange()

    def _on_hover(self, evt):
        pos = evt[0]
        vb = self.plot_widget.plotItem.vb
        if not vb.sceneBoundingRect().contains(pos):
            self.tooltip_label.hide()
            return

        x_idx = round(vb.mapSceneToView(pos).x())
        if not self.aggregated_data or not (0 <= x_idx < len(self.aggregated_data)):
            self.tooltip_label.hide()
            return

        data = self.aggregated_data[x_idx]
        total_op_mw = data['total_op'] / 1000.0
        total_st_mw = data['total_st'] / 1000.0
        tooltip_text = f"<b>{data['date']}</b><br>稼働可能容量: {total_op_mw:,.0f} MW<br><span style='color:#aaaaaa; font-size:11px;'> (停止中: {total_st_mw:,.0f} MW)</span><hr style='margin:4px 0;'>"
        
        tooltip_text += f"<span style='font-size:10px; color:{'#aaaaaa' if self.is_dark else '#666666'};'>【発電方式別】</span><br>"
        for method in HJKS_METHODS:
            val_kw = data['methods'].get(method, {}).get("op", 0)
            if val_kw > 0:
                val_mw = val_kw / 1000.0
                color = HJKS_COLORS[method]
                tooltip_text += f"<span style='color:{color};'>■</span> {method}: {val_mw:,.0f} MW<br>"

        tooltip_text += f"<hr style='margin:4px 0; border-color:{'#555' if self.is_dark else '#ccc'};'><span style='font-size:10px; color:{'#aaaaaa' if self.is_dark else '#666666'};'>【選択エリア別】</span><br>"
        for region in HJKS_REGIONS:
            val_kw = data.get('regions', {}).get(region, {}).get("op", 0)
            if val_kw > 0:
                val_mw = val_kw / 1000.0
                tooltip_text += f" • {region}: {val_mw:,.0f} MW<br>"

        self.tooltip_label.setText(tooltip_text)
        self.tooltip_label.adjustSize()

        vp = self.plot_widget.viewport()
        wpos = vp.mapFromGlobal(self.plot_widget.mapToGlobal(self.plot_widget.mapFromScene(pos)))
        tx = min(int(wpos.x()) + 15, vp.width() - self.tooltip_label.width() - 4)
        ty = max(int(wpos.y()) - self.tooltip_label.height() - 8, 4)
        self.tooltip_label.move(tx, ty)
        self.tooltip_label.raise_()
        self.tooltip_label.show()

    def _copy_graph(self):
        QApplication.clipboard().setPixmap(self.plot_widget.grab())
        QMessageBox.information(self, "完了", "グラフ画像をクリップボードにコピーしました。")