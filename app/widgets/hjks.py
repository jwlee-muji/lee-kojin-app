import logging
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QSplitter, QFrame, QMessageBox, QApplication, QGraphicsDropShadowEffect
)
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QColor
from app.core.config import HJKS_REGIONS, HJKS_METHODS, HJKS_COLORS, load_settings
from app.api.hjks_api import FetchHjksWorker, AggregateHjksWorker
from app.ui.common import BaseWidget
from app.core.events import bus

pg.setConfigOptions(antialias=True)

logger = logging.getLogger(__name__)

class HjksWidget(BaseWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self._base_daily_data = None  # 계산 결과 캐시 저장소
        self._dates_str = []          # 집계 날짜 목록 캐시
        self.aggregated_data = []

        self._build_ui()
        self.fetch_data()

        # 다른 위젯과 API 요청이 겹치지 않도록 15초 지연 후 정규 타이머 시작
        self.setup_timer(self.settings.get("hjks_interval", 180), self.fetch_data, stagger_seconds=15)
        
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
        
        self.reset_zoom_btn = QPushButton(self.tr("ビュー初期化"))
        self.reset_zoom_btn.clicked.connect(lambda: self.plot_widget.enableAutoRange())
        top.addWidget(self.reset_zoom_btn)
        
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

        self.hover_point = pg.PlotDataItem(pen=None, symbol='o', symbolSize=12, zValue=10)
        self.plot_widget.addItem(self.hover_point)

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
        self.track_worker(self.worker)

    def _on_fetch_success(self, msg):
        self.refresh_btn.setEnabled(True)
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("color: #4caf50;")
        self._base_daily_data = None  # 데이터가 갱신되었으므로 캐시 초기화
        self._dates_str = []          # 캐시 초기화에 맞춰 날짜 목록도 리셋
        self._update_chart()
        bus.hjks_updated.emit()

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
            self.track_worker(self._agg_worker)
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
        
        # clear()로 인해 캔버스에서 삭제된 호버 마커를 다시 추가
        self.plot_widget.addItem(self.hover_point)

        self.plot_widget.enableAutoRange()

    def _on_hover(self, evt):
        pos = evt[0]
        vb = self.plot_widget.plotItem.vb
        if not vb.sceneBoundingRect().contains(pos):
            self.tooltip_label.hide()
            self.hover_point.setData([], [])
            self._last_hover_x = None
            return

        x_idx = round(vb.mapSceneToView(pos).x())
        if not self.aggregated_data or not (0 <= x_idx < len(self.aggregated_data)):
            self.tooltip_label.hide()
            self.hover_point.setData([], [])
            self._last_hover_x = None
            return

        # 동일한 X축 상에서 마우스가 움직일 때는 데이터 갱신 스킵
        if getattr(self, '_last_hover_x', None) != x_idx:
            self._last_hover_x = x_idx
            data = self.aggregated_data[x_idx]
            total_op_mw = data['total_op'] / 1000.0

            bg_color = '#1e1e1e' if getattr(self, 'is_dark', True) else '#ffffff'
            self.hover_point.setData([x_idx], [total_op_mw])
            self.hover_point.setSymbolBrush(pg.mkBrush('#FF9800'))
            self.hover_point.setSymbolPen(pg.mkPen(bg_color, width=1.5))

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