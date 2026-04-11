import re
import io
import ssl
import requests
import sqlite3
import urllib3
import pandas as pd
import pyqtgraph as pg
from urllib3.util.ssl_ import create_urllib3_context
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QSplitter, QFrame, QMessageBox, QApplication
)
from PySide6.QtCore import QThread, Signal, Qt, QTimer

pg.setConfigOptions(antialias=True)

# SSL 인증서 경고 무시 (JEPX 사이트 SSL 우회용)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 날짜·숫자 파싱용 정규식 (모듈 로드 시 1회만 컴파일)
_RE_DATE = re.compile(r'(\d{2,4})[/-](\d{1,2})[/-](\d{1,2})')
_RE_NUM  = re.compile(r'(\d+(\.\d+)?)')


class LegacySSLAdapter(requests.adapters.HTTPAdapter):
    """구형 서버(JEPX 등)의 엄격한 OpenSSL 연결 거부를 우회하는 커스텀 어댑터"""
    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        ctx = create_urllib3_context()
        try:
            # OpenSSL 3.0+ 의 기본 보안 레벨을 낮춰 DH_KEY_TOO_SMALL 등의 에러 우회
            ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        except ssl.SSLError:
            pass
            
        # verify=False 설정 시 발생하는 check_hostname 충돌 에러 방지
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        pool_kwargs['ssl_context'] = ctx
        return super().init_poolmanager(connections, maxsize, block, **pool_kwargs)

REGIONS = ["北海道", "東北", "東京", "中部", "北陸", "関西", "中国", "四国", "九州", "沖縄"]
METHODS = ["火力（石炭）", "火力（ガス）", "火力（石油）", "原子力", "水力", "その他"]

# 발전 방식별 색상 매핑
METHOD_COLORS = {
    "火力（石炭）": "#795548", # Brown
    "火力（ガス）": "#EF5350", # Red
    "火力（石油）": "#FF9800", # Orange
    "原子力": "#9C27B0",       # Purple
    "水力": "#42A5F5",         # Blue
    "その他": "#9E9E9E"        # Gray
}


class FetchHjksWorker(QThread):
    finished = Signal(str)
    error    = Signal(str)

    @staticmethod
    def _get_col(df, candidates):
        """컬럼명을 완전 일치 → 부분 일치 순으로 탐색"""
        for c in candidates:
            if c in df.columns:
                return c
            for df_c in df.columns:
                if c in df_c:
                    return df_c
        return None

    @staticmethod
    def _parse_date(d_str, default_dt):
        """날짜 문자열을 date 객체로 변환. 파싱 불가 시 default_dt 반환"""
        if pd.isna(d_str) or not str(d_str).strip():
            return default_dt
        if hasattr(d_str, 'date'):          # Pandas Timestamp 대응
            return d_str.date()
        s = str(d_str).strip().split()[0]
        s = s.replace('／', '/').replace('ー', '-').replace('－', '-')
        m = _RE_DATE.search(s)
        if m:
            try:
                y = int(m.group(1))
                if y < 100:  y += 2000
                if y > 9999: y  = 9999
                return datetime(y, int(m.group(2)), int(m.group(3))).date()
            except Exception:
                if int(m.group(1)) >= 9999:
                    return datetime(9999, 12, 31).date()
        return default_dt

    def run(self):
        try:
            session = requests.Session()
            session.verify = False  # SSL 인증서 검증 비활성화
            session.mount("https://", LegacySSLAdapter())
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            })
            url = "https://hjks.jepx.or.jp/hjks/outages"
            
            # 1. 폼의 숨겨진 데이터(Token 등) 파싱을 위해 GET 요청
            res = session.get(url, timeout=30)
            res.raise_for_status()
            soup = BeautifulSoup(res.content, 'html.parser')
            
            data = {}
            # 불필요한 select(area 등) 값이 전송되어 일부 데이터만 받아오는 현상 방지
            for inp in soup.find_all('input'):
                name = inp.get('name')
                if name:
                    data[name] = inp.get('value', '')
                    
            # 2. CSV 다운로드 파라미터 추가
            data['csv'] = 'csv'
            
            # 3. CSV 다운로드 요청 (POST)
            session.headers.update({"Referer": url})
            csv_res = session.post(url, data=data, timeout=90)
            csv_res.raise_for_status()
            
            try:
                csv_text = csv_res.content.decode('cp932')
            except Exception:
                csv_text = csv_res.content.decode('utf-8', errors='replace')
                
            if '<html' in csv_text.lower()[:500] or '<body' in csv_text.lower()[:500]:
                # HTML이 반환된 경우 (CSV 다운로드 차단 시 Fallback)
                soup_html = BeautifulSoup(csv_res.content, 'html.parser')
                table = soup_html.find('table')
                if not table:
                    raise ValueError("CSVの取得に失敗し、HTML内にもデータが見つかりませんでした。")
                df = pd.read_html(io.StringIO(str(table)))[0]
            else:
                # 정상적인 CSV 파싱
                lines = csv_text.split('\n')
                # ユーザー指定のカラム("エリア" と "停止日時")が含まれる行をヘッダーとする
                header_idx = next((i for i, line in enumerate(lines[:20]) if "エリア" in line and "停止日時" in line), -1)
                if header_idx == -1:
                    header_idx = next((i for i, line in enumerate(lines[:20]) if "エリア" in line), -1)
                    if header_idx == -1:
                        raise ValueError("CSVファイル内にヘッダー行(エリアなど)が見つかりませんでした。")
                
                # 행 밀림(Index drift) 방지: 헤더 행부터 끝까지만 정확하게 잘라서 Pandas에 전달
                csv_data = '\n'.join(lines[header_idx:])
                df = pd.read_csv(io.StringIO(csv_data), index_col=False)
                
            df.columns = df.columns.astype(str).str.strip().str.replace('\ufeff', '').str.replace('\u3000', '')
            df = df.loc[:, ~df.columns.duplicated()] # 중복 컬럼 제거 (안정성 강화)
            
            col_area  = self._get_col(df, ["エリア"])
            col_type  = self._get_col(df, ["発電形式"])
            col_drop  = self._get_col(df, ["低下量"])
            col_auth  = self._get_col(df, ["認可出力"])
            col_start = self._get_col(df, ["停止日時", "開始"])
            col_end   = self._get_col(df, ["復旧予定日", "復旧予定", "終了"])
            
            # 최소 필수 컬럼 검증
            if not all([col_area, col_start]) or (not col_drop and not col_auth):
                missing = []
                if not col_area: missing.append("エリア")
                if not col_start: missing.append("停止日時")
                if not col_drop and not col_auth: missing.append("低下量 または 認可出力")
                cols_str = ", ".join(df.columns.tolist())
                raise ValueError(f"データ形式が想定と異なります。\n不足列: {', '.join(missing)}\n実際の列: {cols_str[:150]}")
                
            far_future = datetime(9999, 12, 31).date()
            clean_data = []
            
            # 필터링 사유 추적용 카운터
            filtered_by_region = 0
            filtered_by_kw = 0
            filtered_by_date = 0
            
            # 4. 각 정지건별 데이터를 규격화하여 DB 저장용 리스트 생성
            for _, row in df.iterrows():
                area_str = str(row.get(col_area, ''))
                type_str = str(row.get(col_type, ''))
                
                region = next((r for r in REGIONS if r in area_str), None)
                if not region:
                    filtered_by_region += 1
                    continue
                
                method = "その他"
                if "石炭" in type_str:
                    method = "火力（石炭）"
                elif any(x in type_str for x in ["ガス", "LNG", "コンバインド"]):
                    method = "火力（ガス）"
                elif any(x in type_str for x in ["石油", "重油", "原油", "内燃"]):
                    method = "火力（石油）"
                elif "原" in type_str:
                    method = "原子力"
                elif any(x in type_str for x in ["水", "揚水"]): method = "水力"
                
                kw = 0.0
                # 1순위: 低下量 (저하량) 추출
                if col_drop and pd.notna(row.get(col_drop)):
                    try:
                        val = row.get(col_drop)
                        if isinstance(val, (int, float)):
                            kw = float(val)
                        else:
                            drop_str = str(val).replace(',', '')
                            m = _RE_NUM.search(drop_str)
                            if m: kw = float(m.group(1))
                    except Exception:
                        pass
                        
                # 2순위: 低下量이 비어있거나 0.0일 경우 認可出力 (인가출력) 추출
                if kw <= 0.0 and col_auth and pd.notna(row.get(col_auth)):
                    try:
                        val = row.get(col_auth)
                        if isinstance(val, (int, float)):
                            kw = float(val)
                        else:
                            auth_str = str(val).replace(',', '')
                            m = _RE_NUM.search(auth_str)
                            if m: kw = float(m.group(1))
                    except Exception:
                        pass
                if kw <= 0.0:
                    filtered_by_kw += 1
                    continue
                
                start_dt = self._parse_date(row.get(col_start, ''), None)
                if not start_dt:
                    filtered_by_date += 1
                    continue
                end_dt = self._parse_date(row.get(col_end, ''), far_future) if col_end else far_future
                
                clean_data.append({
                    "region": region,
                    "method": method,
                    "capacity": kw,
                    "start_date": start_dt.strftime("%Y-%m-%d"),
                    "end_date": end_dt.strftime("%Y-%m-%d")
                })
                
            if not clean_data:
                # 추출된 데이터가 하나도 없을 경우 원인 파악을 위한 디버그 에러 출력
                cols_str = ", ".join(df.columns.tolist())
                sample_info = "データが空です"
                
                if not df.empty:
                    first_row = df.iloc[0]
                    s_area = str(first_row.get(col_area, ''))
                    s_drop = str(first_row.get(col_drop, ''))
                    s_auth = str(first_row.get(col_auth, ''))
                    s_start = str(first_row.get(col_start, ''))
                    sample_info = f"・エリア: {s_area}\n・低下量: {s_drop} / 認可出力: {s_auth}\n・停止日時: {s_start}"
                    
                err_msg = (
                    f"抽出条件に合うデータが0件でした。\n\n"
                    f"【除外理由ごとの件数】\n"
                    f"・エリア名不一致: {filtered_by_region}件\n"
                    f"・容量(kW)ゼロ/解析不可: {filtered_by_kw}件\n"
                    f"・停止日時の形式不明: {filtered_by_date}件\n\n"
                    f"【1行目の解析サンプル】\n{sample_info}\n\n"
                    f"【認識されたカラム一覧】\n{cols_str[:150]}"
                )
                raise ValueError(err_msg)
                
            # 5. SQLite DB에 저장 (데이터 갱신 시 테이블 덮어쓰기)
            conn = sqlite3.connect('hjks_data.db')
            outage_df = pd.DataFrame(clean_data)
            outage_df.to_sql('hjks_outages', conn, if_exists='replace', index=False)
            conn.close()

            self.finished.emit("データ取得およびDB更新完了")

        except Exception as e:
            self.error.emit(f"データの取得に失敗しました: {str(e)}")


class HjksWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self._base_daily_data = None  # 계산 결과 캐시 저장소
        self.aggregated_data = []

        self._build_ui()
        self.fetch_data()

        # 3시간마다 자동 갱신
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.fetch_data)
        self.timer.start(3 * 60 * 60 * 1000)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 상단 컨트롤 바
        top = QHBoxLayout()
        title = QLabel("発電所停止状況 (HJKS)")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        top.addWidget(title)
        top.addSpacing(20)

        self.refresh_btn = QPushButton("データ更新")
        self.refresh_btn.setStyleSheet("background-color: #e6f7ff;")
        self.refresh_btn.clicked.connect(self.fetch_data)
        top.addWidget(self.refresh_btn)

        top.addSpacing(15)
        self.status_label = QLabel("待機中...")
        self.status_label.setStyleSheet("color: gray;")
        top.addWidget(self.status_label)
        top.addStretch()
        
        # 그래프 복사 버튼
        _btn_style = (
            "QPushButton { font-size: 11px; color: #555; border: 1px solid #ddd;"
            " border-radius: 4px; padding: 3px 10px; background: #f5f5f5; }"
            "QPushButton:hover { background: #e8e8e8; }"
        )
        self.copy_btn = QPushButton("グラフ画像をコピー")
        self.copy_btn.setStyleSheet(_btn_style)
        self.copy_btn.clicked.connect(self._copy_graph)
        top.addWidget(self.copy_btn)
        
        layout.addLayout(top)

        # 메인 스플리터 (좌: 체크박스 영역, 우: 그래프 영역)
        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter, 1)

        # 좌측 지역 선택 패널
        left_panel = QFrame()
        left_panel.setStyleSheet("QFrame { background-color: #fcfcfc; border: 1px solid #eee; border-radius: 4px; }")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        
        lbl_region = QLabel("表示エリア選択")
        lbl_region.setStyleSheet("font-weight: bold; color: #333; border: none;")
        left_layout.addWidget(lbl_region)
        
        btn_layout = QHBoxLayout()
        self.btn_select_all = QPushButton("全選択")
        self.btn_deselect_all = QPushButton("全解除")
        for btn in (self.btn_select_all, self.btn_deselect_all):
            btn.setStyleSheet("font-size: 11px; padding: 4px;")
        self.btn_select_all.clicked.connect(self._select_all_regions)
        self.btn_deselect_all.clicked.connect(self._deselect_all_regions)
        btn_layout.addWidget(self.btn_select_all)
        btn_layout.addWidget(self.btn_deselect_all)
        left_layout.addLayout(btn_layout)
        
        left_layout.addSpacing(5)
        
        self.checkboxes = {}
        for region in REGIONS:
            cb = QCheckBox(region)
            cb.setChecked(True)  # 기본적으로 모두 체크
            cb.setStyleSheet("border: none; padding: 2px;")
            cb.stateChanged.connect(self._update_chart)
            left_layout.addWidget(cb)
            self.checkboxes[region] = cb
            
        left_layout.addStretch()
        
        # 발전 방식 범례 표시
        left_layout.addWidget(QLabel("【凡例】"))
        for method in METHODS:
            leg_layout = QHBoxLayout()
            color_box = QLabel()
            color_box.setFixedSize(12, 12)
            color_box.setStyleSheet(f"background-color: {METHOD_COLORS[method]}; border-radius: 2px; border: none;")
            leg_lbl = QLabel(method)
            leg_lbl.setStyleSheet("font-size: 11px; border: none;")
            leg_layout.addWidget(color_box)
            leg_layout.addWidget(leg_lbl)
            leg_layout.addStretch()
            left_layout.addLayout(leg_layout)

        self.splitter.addWidget(left_panel)

        # 우측 그래프 패널
        self.plot_widget = pg.PlotWidget()
        self._init_plot_style()
        self.splitter.addWidget(self.plot_widget)
        
        self.splitter.setSizes([180, 720])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        # 호버 툴팁
        self.tooltip_label = QLabel(self.plot_widget.viewport())
        self.tooltip_label.setStyleSheet(
            "QLabel { background-color: rgba(255, 255, 255, 230); border: 1px solid #cccccc;"
            " border-radius: 6px; padding: 8px 12px; color: #333333; font-size: 12px; }"
        )
        self.tooltip_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.tooltip_label.hide()

        self.hover_proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self._on_hover
        )

    def _init_plot_style(self):
        self.plot_widget.setBackground('#ffffff')
        self.plot_widget.showGrid(y=True, alpha=0.3)
        self.plot_widget.plotItem.hideAxis('top')
        self.plot_widget.plotItem.hideAxis('right')
        for ax_name in ('left', 'bottom'):
            ax = self.plot_widget.getAxis(ax_name)
            ax.setPen(pg.mkPen(color='#dddddd', width=1))
            ax.setTextPen(pg.mkPen('#666666'))
        self.plot_widget.setLabel('left', '停止容量 (kW)', color='#666666', size='10pt')

    def _select_all_regions(self):
        for cb in self.checkboxes.values():
            cb.setChecked(True)

    def _deselect_all_regions(self):
        for cb in self.checkboxes.values():
            cb.setChecked(False)

    def fetch_data(self):
        if self.worker and self.worker.isRunning():
            return
        self.refresh_btn.setEnabled(False)
        self.status_label.setText("データ取得中...")
        self.status_label.setStyleSheet("color: blue;")
        
        self.worker = FetchHjksWorker()
        self.worker.finished.connect(self._on_fetch_success)
        self.worker.error.connect(self._on_fetch_error)
        self.worker.start()

    def _on_fetch_success(self, msg):
        self.refresh_btn.setEnabled(True)
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("color: green;")
        self._base_daily_data = None  # 데이터가 갱신되었으므로 캐시 초기화
        self._update_chart()

    def _on_fetch_error(self, err_msg):
        self.refresh_btn.setEnabled(True)
        self.status_label.setText("取得失敗")
        self.status_label.setStyleSheet("color: red;")
        QMessageBox.warning(self, "エラー", err_msg)

    def _update_chart(self):
        self.plot_widget.clear()
            
        selected_regions = [r for r, cb in self.checkboxes.items() if cb.isChecked()]
        
        # 1. 필요 시 베이스 데이터 캐싱 (DB 읽기 + 10일간의 날짜/에리어/방식별 사전 집계)
        if self._base_daily_data is None:
            self._base_daily_data = []
            try:
                conn = sqlite3.connect('hjks_data.db')
                df = pd.read_sql('SELECT * FROM hjks_outages', conn)
                conn.close()
            except Exception:
                df = pd.DataFrame()

            base_date = datetime.now().date()
            self._target_dates = [base_date + timedelta(days=i) for i in range(10)]
            self._dates_str = [dt.strftime("%Y-%m-%d") for dt in self._target_dates]
            
            for dt_str in self._dates_str:
                day_dict = {r: {m: 0 for m in METHODS} for r in REGIONS}
                if not df.empty:
                    # 復旧予定日(終了日)はその日の停止容量から除外する (dt_str < end_date)
                    mask = (df['start_date'] <= dt_str) & (df['end_date'] > dt_str)
                    active_df = df[mask]
                    if not active_df.empty:
                        grouped = active_df.groupby(['region', 'method'])['capacity'].sum()
                        for (r, m), c in grouped.items():
                            if r in day_dict and m in day_dict[r]:
                                day_dict[r][m] += c
                self._base_daily_data.append(day_dict)

        if not selected_regions:
            return

        x_indices = list(range(10))
        # X축 날짜 틱 설정
        ticks = [(i, dt.strftime("%m-%d")) for i, dt in enumerate(self._target_dates)]
        self.plot_widget.getAxis('bottom').setTicks([ticks])
        
        self.aggregated_data = []
        
        # 2. 캐시된 베이스 데이터에서 체크된 에리어들의 데이터만 합산
        for i, dt_str in enumerate(self._dates_str):
            day_dict = self._base_daily_data[i]
            agg_methods = {m: 0 for m in METHODS}
            agg_regions = {r: 0 for r in REGIONS}
            total = 0
            
            for r in selected_regions:
                r_data = day_dict[r]
                r_total = sum(r_data.values())
                if r_total > 0:
                    agg_regions[r] = r_total
                    total += r_total
                    for m in METHODS:
                        agg_methods[m] += r_data[m]
                        
            self.aggregated_data.append({
                "date": dt_str,
                "total": total,
                "methods": agg_methods,
                "regions": agg_regions
            })
        
        y0_array = [0] * 10
        for method in METHODS:
            heights = [day["methods"][method] for day in self.aggregated_data]
            if sum(heights) > 0:
                bar_item = pg.BarGraphItem(x=x_indices, y0=y0_array[:], height=heights, width=0.6, brush=METHOD_COLORS[method])
                self.plot_widget.addItem(bar_item)
                for i in range(10):
                    y0_array[i] += heights[i]
                
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
        tooltip_text = f"<b>{data['date']}</b><br>合計: {data['total']:,.0f} kW<hr style='margin:4px 0;'>"
        
        tooltip_text += "<span style='font-size:10px; color:#666;'>【発電方式別】</span><br>"
        for method in METHODS:
            val = data['methods'].get(method, 0)
            if val > 0:
                color = METHOD_COLORS[method]
                tooltip_text += f"<span style='color:{color};'>■</span> {method}: {val:,.0f} kW<br>"
                
        tooltip_text += "<hr style='margin:4px 0;'><span style='font-size:10px; color:#666;'>【選択エリア別】</span><br>"
        for region in REGIONS:
            val = data['regions'].get(region, 0)
            if val > 0:
                tooltip_text += f" • {region}: {val:,.0f} kW<br>"

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