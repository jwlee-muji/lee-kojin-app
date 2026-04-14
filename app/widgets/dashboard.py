import logging
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect
)
from PySide6.QtCore import (
    Qt, QTimer, QThread, Signal, QPropertyAnimation, QEasingCurve,
    Property, QObject
)
from PySide6.QtGui import QColor, QPixmap
from app.core.config import (
    DB_IMBALANCE, DB_HJKS, DB_JKM, BASE_DIR,
    TIME_COL_IDX, YOJO_START_COL_IDX, YOJO_END_COL_IDX, FUSOKU_START_COL_IDX,
)
import sqlite3
from app.core.database import get_db_connection
from app.ui.common import BaseWidget, get_tinted_pixmap
from app.core.events import bus
from app.core.i18n import tr

logger = logging.getLogger(__name__)


class SummaryCard(QFrame):
    clicked = Signal()

    def __init__(self, title, icon_name, color):
        super().__init__()
        self.is_dark = True
        self.setCursor(Qt.PointingHandCursor)
        self.card_color = color
        self.icon_name = icon_name
        self._val_color = None
        self._has_animated = False  # 初回のみアニメーションを実行するためのフラグ
        self._hover_offset = 0.0    # ホバーアニメーション用
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        header_layout = QHBoxLayout()
        self.icon_lbl = QLabel()
            
        title_lbl = QLabel(title)
        self.title_lbl = title_lbl
        
        header_layout.addWidget(self.icon_lbl)
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        
        self.value_lbl = QLabel("--")
        self.value_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        self.sub_lbl = QLabel(tr("データ待機中..."))
        self.sub_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        layout.addLayout(header_layout)
        layout.addStretch()
        layout.addWidget(self.value_lbl)
        layout.addWidget(self.sub_lbl)
        
        self._apply_style()
        
        # ドロップシャドウの追加でカードを浮き上がらせる
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(15)
        self.shadow.setOffset(0, 4)
        self.setGraphicsEffect(self.shadow)
        
        # ホバーアニメーションの設定
        self._hover_anim = QPropertyAnimation(self, b"hoverOffset")
        self._hover_anim.setDuration(150)
        self._hover_anim.setEasingCurve(QEasingCurve.OutQuad)
        
        # 初期化時に1回だけスケルトンローディングを開始
        self.set_loading(True)

    def _is_effect_alive(self, attr: str) -> bool:
        """저장된 QGraphicsEffect C++ 객체가 아직 유효한지 확인합니다."""
        try:
            if hasattr(self, attr):
                getattr(self, attr).opacity()
                return True
        except RuntimeError:
            try:
                delattr(self, attr)
            except AttributeError:
                pass
        return False

    def set_loading(self, is_loading: bool):
        """스켈레톤(Skeleton) 로딩 애니메이션 활성화/비활성화"""
        if is_loading:
            self.value_lbl.setText("----")
            self.sub_lbl.setText(tr("データ取得中..."))

            # C++ 객체 유효성 검사 후 필요 시 재생성
            if not self._is_effect_alive('_skel_effect'):
                # setGraphicsEffect()가 소유권을 가져가므로 부모를 지정하지 않습니다.
                self._skel_effect = QGraphicsOpacityEffect()
                self._skel_anim = QPropertyAnimation(self._skel_effect, b"opacity")
                self._skel_anim.setDuration(800)
                self._skel_anim.setStartValue(0.3)
                self._skel_anim.setEndValue(1.0)
                self._skel_anim.setLoopCount(-1)

            # 페이드 이펙트가 붙어있으면 스켈레톤으로 교체
            self.value_lbl.setGraphicsEffect(self._skel_effect)
            self._skel_anim.start()
        else:
            if hasattr(self, '_skel_anim'):
                try:
                    self._skel_anim.stop()
                except RuntimeError:
                    pass
            # 스켈레톤 이펙트가 현재 적용 중일 때만 제거 (페이드 이펙트는 건드리지 않음)
            if self._is_effect_alive('_skel_effect') and self.value_lbl.graphicsEffect() is self._skel_effect:
                self.value_lbl.setGraphicsEffect(None)

    def set_value(self, val_str, sub_str, val_color=None, target_val=None, format_str=None, animate_fade=False):
        self.set_loading(False)  # 값이 설정되면 스켈레톤 중지
        if animate_fade:
            self._next_val_str = val_str
            self._next_sub_str = sub_str
            self._next_val_color = val_color
            self._start_fade_out()
            return
            
        self._val_color = val_color
        self.sub_lbl.setText(sub_str)
        self._apply_style()
        
        # 目標値とフォーマットが渡され、かつ未アニメーションの場合のみ実行
        if target_val is not None and format_str is not None and not self._has_animated:
            self._has_animated = True
            self._anim_target = float(target_val)
            self._anim_format = format_str
            self._anim_step = 0
            self._anim_max_steps = 30  # 約1秒かけてカウントアップ (30フレーム)
            
            if not hasattr(self, '_anim_timer'):
                self._anim_timer = QTimer(self)
                self._anim_timer.timeout.connect(self._on_anim_step)
            self._anim_timer.start(33)
        else:
            self.value_lbl.setText(val_str)
            
    def _on_anim_step(self):
        self._anim_step += 1
        progress = self._anim_step / self._anim_max_steps
        # Ease-Out Cubic: 減速しながら滑らかに目標値へ近づく
        ease = 1 - pow(1 - progress, 3)
        current_val = self._anim_target * ease
        
        self.value_lbl.setText(self._anim_format.format(current_val))
        
        if self._anim_step >= self._anim_max_steps:
            self._anim_timer.stop()
            self.value_lbl.setText(self._anim_format.format(self._anim_target))
            
    def _start_fade_out(self):
        # C++ 객체 유효성 검사 후 필요 시 재생성
        if not self._is_effect_alive('_fade_opacity_effect'):
            self._fade_opacity_effect = QGraphicsOpacityEffect()  # 소유권은 setGraphicsEffect에게
            self._fade_out_anim = QPropertyAnimation(self._fade_opacity_effect, b"opacity")
            self._fade_out_anim.setDuration(180)
            self._fade_out_anim.setEasingCurve(QEasingCurve.InQuad)
            self._fade_out_anim.finished.connect(self._on_fade_out_done)
            self._fade_in_anim = QPropertyAnimation(self._fade_opacity_effect, b"opacity")
            self._fade_in_anim.setDuration(180)
            self._fade_in_anim.setEasingCurve(QEasingCurve.OutQuad)

        if self.value_lbl.graphicsEffect() is not self._fade_opacity_effect:
            self.value_lbl.setGraphicsEffect(self._fade_opacity_effect)

        self._fade_in_anim.stop()
        self._fade_out_anim.setStartValue(self._fade_opacity_effect.opacity())
        self._fade_out_anim.setEndValue(0.0)
        self._fade_out_anim.start()

    def _on_fade_out_done(self):
        self.set_value(self._next_val_str, self._next_sub_str, self._next_val_color)
        self._fade_in_anim.setStartValue(0.0)
        self._fade_in_anim.setEndValue(1.0)
        self._fade_in_anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def enterEvent(self, event):
        # 애니메이션 중복 트리거 및 큐 꼬임 방지
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_offset)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        # 애니메이션 중복 트리거 및 큐 꼬임 방지
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_offset)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        super().leaveEvent(event)

    @Property(float)
    def hoverOffset(self):
        return self._hover_offset

    @hoverOffset.setter
    def hoverOffset(self, val):
        self._hover_offset = val
        if hasattr(self, 'shadow'):
            self.shadow.setOffset(0, 4 + val * 4)
            self.shadow.setBlurRadius(15 + val * 10)
            base_alpha = 100 if self.is_dark else 30
            target_alpha = 150 if self.is_dark else 60
            current_alpha = int(base_alpha + (target_alpha - base_alpha) * val)
            self.shadow.setColor(QColor(0, 0, 0, current_alpha))

    def set_theme(self, is_dark):
        self.is_dark = is_dark
        # Dynamic Property 상태를 Qt 스타일 엔진에 전파
        self.setProperty("theme", "dark" if is_dark else "light")
        self.style().unpolish(self)
        self.style().polish(self)
        self._apply_style()
        
    def _apply_style(self):
        tc = "#eeeeee" if self.is_dark else "#333333"

        try:
            # Qt 리소스 시스템에서 메모리로 직접 아이콘 로드
            self.icon_lbl.setPixmap(get_tinted_pixmap(f":/img/{self.icon_name}.svg", self.is_dark))
        except Exception:
            self.icon_lbl.setText(self.icon_name)
            self.icon_lbl.setStyleSheet("font-size: 26px; background: transparent;")

        # 배경/테두리는 theme.py의 동적 속성에 맡기고, 인스턴스 고유 컬러인 border-left만 별도 적용
        self.setStyleSheet(
            f"SummaryCard {{ border-left: 6px solid {self.card_color}; }}"
        )
        self.title_lbl.setStyleSheet(f"font-size: 15px; font-weight: bold; background: transparent; color: {'#aaaaaa' if self.is_dark else '#666666'};")
        self.sub_lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; background: transparent; color: {'#888888' if self.is_dark else '#888888'};")
        vc = self._val_color if self._val_color else tc
        self.value_lbl.setStyleSheet(f"font-size: 32px; font-weight: bold; background: transparent; color: {vc};")
        
        if hasattr(self, 'shadow'):
            self.shadow.setOffset(0, 4 + self._hover_offset * 4)
            self.shadow.setBlurRadius(15 + self._hover_offset * 10)
            base_alpha = 100 if self.is_dark else 30
            target_alpha = 150 if self.is_dark else 60
            current_alpha = int(base_alpha + (target_alpha - base_alpha) * self._hover_offset)
            self.shadow.setColor(QColor(0, 0, 0, current_alpha))


class DashboardDataService(QObject):
    """백그라운드 스레드에 상주하며 DB 커넥션을 캐싱하고 쿼리를 처리하는 서비스"""
    imb_result = Signal(float, str)
    imb_empty = Signal()
    jkm_result = Signal(float, str, float)
    jkm_empty = Signal()
    hjks_result = Signal(float, float)
    hjks_empty = Signal()

    def __init__(self):
        super().__init__()

    def fetch_data(self, fetch_type):
        if fetch_type in ("all", "imbalance"):
            self._fetch_imbalance()
        if fetch_type in ("all", "jkm"):
            self._fetch_jkm()
        if fetch_type in ("all", "hjks"):
            self._fetch_hjks()


    def _fetch_imbalance(self):
        try:
            today_yyyymmdd = int(datetime.now().strftime("%Y%m%d"))
            with get_db_connection(DB_IMBALANCE) as conn:
                cursor = conn.execute("SELECT name FROM pragma_table_info('imbalance_prices')")
                cols = [r[0] for r in cursor.fetchall()]
                if not cols: return self.imb_empty.emit()
                
                rows = conn.execute(f'SELECT * FROM imbalance_prices WHERE "{cols[1]}" = ? OR "{cols[1]}" = ?', 
                                    (today_yyyymmdd, str(today_yyyymmdd))).fetchall()
                
                if not rows: return self.imb_empty.emit()
            
            max_val = None
            max_col = ""
            max_slot = ""
            
            for row in rows:
                slot = str(row[TIME_COL_IDX])
                for i in range(YOJO_START_COL_IDX, len(cols)):
                    if (YOJO_START_COL_IDX <= i <= YOJO_END_COL_IDX or i >= FUSOKU_START_COL_IDX) and '変更S' not in cols[i]:
                        val_str = row[i]
                        if val_str:
                            try:
                                v = float(val_str)
                                if max_val is None or v > max_val:
                                    max_val = v
                                    max_col = cols[i]
                                    max_slot = slot
                            except (ValueError, TypeError):
                                pass
            
            if max_val is not None:
                self.imb_result.emit(float(max_val), tr("コマ {0} / {1}").format(max_slot, tr(max_col)))
            else: self.imb_empty.emit()
        except (sqlite3.Error, ValueError, IndexError) as e:
            logger.warning(f"インバランスDBのクエリ中にエラー: {e}")
            self.imb_empty.emit()
        except Exception as e:
            logger.error(f"インバランスデータの取得中に予期せぬエラー: {e}", exc_info=True)
            self.imb_empty.emit()
            
    def _fetch_jkm(self):
        try:
            with get_db_connection(DB_JKM) as conn:
                rows = conn.execute("SELECT date, close FROM jkm_prices ORDER BY date DESC LIMIT 2").fetchall()
                if not rows: return self.jkm_empty.emit()
                latest_date, latest_price = rows[0]
                pct = ((latest_price - rows[1][1]) / rows[1][1] * 100) if len(rows) > 1 else 0.0
                self.jkm_result.emit(latest_price, latest_date, pct)
        except sqlite3.Error as e:
            logger.warning(f"JKM DBのクエリ中にエラー: {e}")
            self.jkm_empty.emit()
        except Exception as e:
            logger.error(f"JKMデータの取得中に予期せぬエラー: {e}", exc_info=True)
            self.jkm_empty.emit()
            
    def _fetch_hjks(self):
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            with get_db_connection(DB_HJKS) as conn:
                row = conn.execute("SELECT SUM(operating_kw), SUM(stopped_kw) FROM hjks_capacity WHERE date = ?", (today_str,)).fetchone()
                if not row or row[0] is None: return self.hjks_empty.emit()
                self.hjks_result.emit(float(row[0]) / 1000.0, float(row[1]) / 1000.0)
        except sqlite3.Error as e:
            logger.warning(f"HJKS DBのクエリ中にエラー: {e}")
            self.hjks_empty.emit()
        except Exception as e:
            logger.error(f"HJKSデータの取得中に予期せぬエラー: {e}", exc_info=True)
            self.hjks_empty.emit()


class DashboardWidget(BaseWidget):
    request_fetch = Signal(str)
    
    def __init__(self):
        super().__init__()
        self._weather_list = []
        self._weather_index = 0
        
        # 영구 백그라운드 DB 쿼리 서비스 설정
        self._service_thread = QThread()
        self._service = DashboardDataService()
        self._service.moveToThread(self._service_thread)
        self.request_fetch.connect(self._service.fetch_data)
        
        self._service.imb_result.connect(self._on_imb_result)
        self._service.imb_empty.connect(self._on_imb_empty)
        self._service.jkm_result.connect(self._on_jkm_result)
        self._service.jkm_empty.connect(self._on_jkm_empty)
        self._service.hjks_result.connect(self._on_hjks_result)
        self._service.hjks_empty.connect(self._on_hjks_empty)
        
        self._service_thread.start()
        
        from PySide6.QtWidgets import QApplication
        QApplication.instance().aboutToQuit.connect(self._cleanup_thread)

        self._build_ui()
        
        # Event Bus 구독 (Sub)
        bus.occto_updated.connect(self.update_occto)
        bus.imbalance_updated.connect(self.refresh_imbalance)
        bus.jkm_updated.connect(self.refresh_jkm)
        bus.hjks_updated.connect(self.refresh_hjks)
        bus.weather_updated.connect(self.update_weather)
        
        self.refresh_data() # 최초 1회 로드, 이후에는 각 위젯이 보내는 EventBus 시그널로만 갱신됨
        
        self.weather_cycle_timer = QTimer(self)
        self.weather_cycle_timer.timeout.connect(self._cycle_weather)
        self.weather_cycle_timer.start(3000)
        
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        self.title_lbl = QLabel(tr("総合ダッシュボード"))
        layout.addWidget(self.title_lbl)
        layout.addSpacing(20)

        grid = QGridLayout()
        grid.setSpacing(20)

        self.card_imb   = SummaryCard(tr("本日の最大インバランス"), "won", "#F44336")
        self.card_occto = SummaryCard(tr("本日の最低電力予備率"), "power", "#2196F3")
        self.card_wea   = SummaryCard(tr("全国の天気"), "weather", "#4CAF50")
        self.card_jkm   = SummaryCard(tr("最新 JKM LNG 価格"), "fire", "#FF9800")
        self.card_hjks  = SummaryCard(tr("本日の発電稼働容量"), "plant", "#9C27B0")
        
        grid.addWidget(self.card_imb, 0, 0)
        grid.addWidget(self.card_occto, 0, 1)
        grid.addWidget(self.card_wea, 0, 2, 2, 1)
        grid.addWidget(self.card_jkm, 1, 0)
        grid.addWidget(self.card_hjks, 1, 1)

        # 카드 클릭 → 해당 탭으로 이동
        self.card_occto.clicked.connect(lambda: bus.page_requested.emit(1))
        self.card_imb.clicked.connect(lambda: bus.page_requested.emit(2))
        self.card_jkm.clicked.connect(lambda: bus.page_requested.emit(3))
        self.card_wea.clicked.connect(lambda: bus.page_requested.emit(4))
        self.card_hjks.clicked.connect(lambda: bus.page_requested.emit(5))

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        
        layout.addLayout(grid)
        
    def apply_theme_custom(self):
        is_dark = self.is_dark
        tc = "#eeeeee" if is_dark else "#333333"
        self.title_lbl.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {tc};")
        self.card_imb.set_theme(is_dark)
        self.card_occto.set_theme(is_dark)
        self.card_wea.set_theme(is_dark)
        self.card_jkm.set_theme(is_dark)
        self.card_hjks.set_theme(is_dark)

    def _cleanup_thread(self):
        self._service_thread.quit()
        self._service_thread.wait()
        
    def refresh_data(self):
        # 백그라운드 갱신 시 기존 값을 지우지 않고 조용히 새 데이터를 요청합니다.
        self.request_fetch.emit("all")
        
    def refresh_imbalance(self):
        self.request_fetch.emit("imbalance")

    def _on_imb_result(self, max_val, max_info):
        color = ("#ff5252" if self.is_dark else "#d32f2f") if max_val >= 40 else (("#ffa726" if self.is_dark else "#f57c00") if max_val >= 20 else None)
        self.card_imb.set_value(f"{max_val:,.1f} 円", max_info, color, target_val=max_val, format_str="{:,.1f} 円")
        
    def _on_imb_empty(self):
        self.card_imb.set_value(tr("-- 円"), tr("本日のデータなし"))
            
    def refresh_jkm(self):
        self.request_fetch.emit("jkm")
        
    def _on_jkm_result(self, price, date, pct):
        sign, color = ("▲", ("#ff5252" if self.is_dark else "#d32f2f")) if pct < 0 else ("▼", ("#4caf50" if self.is_dark else "#388e3c"))
        self.card_jkm.set_value(f"{price:.3f} USD", tr("{0} (前日比 {1} {2}%)").format(date, sign, abs(pct)) if pct else date, color if pct else None, target_val=price, format_str="{:.3f} USD")
        
    def _on_jkm_empty(self):
        self.card_jkm.set_value(tr("-- USD"), tr("データなし"))
            
    def refresh_hjks(self):
        self.request_fetch.emit("hjks")
        
    def _on_hjks_result(self, operating_mw, stopped_mw):
        self.card_hjks.set_value(f"{operating_mw:,.0f} MW", tr("停止中: {0} MW").format(f"{stopped_mw:,.0f}"), target_val=operating_mw, format_str="{:,.0f} MW")
        
    def _on_hjks_empty(self):
        self.card_hjks.set_value("0 MW", tr("本日のデータなし"))
            
    def update_occto(self, time_str, area_str, min_val):
        color = ("#ff5252" if self.is_dark else "#d32f2f") if min_val <= 8.0 else (("#ffa726" if self.is_dark else "#f57c00") if min_val <= 10.0 else None)
        self.card_occto.set_value(f"{min_val:.1f} %", f"{time_str} / {area_str}", color, target_val=min_val, format_str="{:.1f} %")
        
    def update_weather(self, weather_list):
        self._weather_list = weather_list
        self._weather_index = 0
        self._cycle_weather()
        
    def _cycle_weather(self):
        if not self._weather_list:
            return
        region, w_text, t_text, color = self._weather_list[self._weather_index]
        self.card_wea.set_value(t_text, f"{region} / {w_text}", color, animate_fade=True)
        self._weather_index = (self._weather_index + 1) % len(self._weather_list)