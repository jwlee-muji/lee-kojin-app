from PySide6.QtWidgets import QTableWidget, QApplication, QWidget, QStackedWidget, QGraphicsOpacityEffect, QMessageBox
from PySide6.QtGui import QKeySequence, QPixmap, QPainter, QColor, QIcon
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Qt
from PySide6.QtSvg import QSvgRenderer
import pyqtgraph as pg
from app.core.config import load_settings
from app.ui.theme import UIColors, Typography
from typing import Optional
from app.core.events import bus
from app.core.i18n import tr


_tint_icon_cache:   dict[tuple[str, bool], QIcon]         = {}
_tint_pixmap_cache: dict[tuple[str, bool, int, int], QPixmap] = {}


def get_tinted_icon(icon_path: str, is_dark: bool) -> QIcon:
    """SVG/PNG 이미지에 테마에 맞는 색상을 덧입혀 QIcon으로 반환합니다。結果はキャッシュされます。"""
    key = (icon_path, is_dark)
    if key in _tint_icon_cache:
        return _tint_icon_cache[key]
    pixmap = QPixmap(icon_path)
    if not pixmap.isNull():
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(UIColors.icon_tint(is_dark)))
        painter.end()
    icon = QIcon(pixmap)
    _tint_icon_cache[key] = icon
    return icon


def get_tinted_pixmap(icon_path: str, is_dark: bool, width: int = 26, height: int = 26) -> QPixmap:
    """SVG/PNG 이미지에 테마에 맞는 색상을 덧입혀 지정된 크기의 QPixmap으로 반환합니다。結果はキャッシュされます。"""
    key = (icon_path, is_dark, width, height)
    if key in _tint_pixmap_cache:
        return _tint_pixmap_cache[key]

    # 明示的に透明背景を作成し、SVGレンダラーで描画することで
    # QPixmap() 直接ロード時に発生する白背景の問題を回避する
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.transparent)
    renderer = QSvgRenderer(icon_path)
    if renderer.isValid():
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
    else:
        # SVG以外のフォーマット(PNG等)のフォールバック
        src = QPixmap(icon_path).scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        painter = QPainter(pixmap)
        painter.drawPixmap(0, 0, src)
        painter.end()

    if not pixmap.isNull():
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(UIColors.icon_tint(is_dark)))
        painter.end()

    _tint_pixmap_cache[key] = pixmap
    return pixmap


def clear_tint_cache() -> None:
    """アイコンキャッシュを全クリアします。
    キャッシュキーは (path, is_dark) なのでテーマ切替時はクリア不要。
    リソース再ロード等が必要な場合にのみ呼び出してください。"""
    _tint_icon_cache.clear()
    _tint_pixmap_cache.clear()


class ExcelCopyTableWidget(QTableWidget):
    """Ctrl+C로 헤더 포함 Excel 붙여넣기 가능한 테이블"""

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self._copy_selection()
        else:
            super().keyPressEvent(event)

    def _copy_selection(self):
        selection = self.selectedIndexes()
        if not selection:
            return

        top    = min(i.row()    for i in selection)
        bottom = max(i.row()    for i in selection)
        left   = min(i.column() for i in selection)
        right  = max(i.column() for i in selection)

        headers = [
            (self.horizontalHeaderItem(c).text()
             if self.horizontalHeaderItem(c) else "")
            for c in range(left, right + 1)
        ]
        rows = []
        for r in range(top, bottom + 1):
            rows.append([
                (self.item(r, c).text() if self.item(r, c) else "")
                for c in range(left, right + 1)
            ])

        text = "\t".join(headers) + "\n"
        text += "\n".join("\t".join(row) for row in rows) + "\n"
        QApplication.clipboard().setText(text)


class FadeStackedWidget(QStackedWidget):
    """부드러운 페이드 인/아웃 화면 전환 애니메이션이 적용된 StackedWidget"""
    def __init__(self, parent=None):
        super().__init__(parent)
        # parent 지정으로 Qt 객체 트리에 등록 → 위젯 소멸 시 자동 정리
        self._fade_anim = QPropertyAnimation(self)
        self._fade_anim.setPropertyName(b"opacity")
        self._fade_anim.setDuration(200)
        self._fade_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._fade_anim.finished.connect(self._on_fade_finished)
        self.currentChanged.connect(self._on_current_changed)

    def _on_current_changed(self, index):
        if self._fade_anim.state() == QPropertyAnimation.Running:
            self._fade_anim.stop()
            self._on_fade_finished()
            
        self._current_widget = self.widget(index)
        if not self._current_widget: return
        self._effect = QGraphicsOpacityEffect(self._current_widget)
        self._current_widget.setGraphicsEffect(self._effect)
        self._fade_anim.setTargetObject(self._effect)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

    def _on_fade_finished(self):
        # 애니메이션이 끝나면 이펙트를 제거하여 하위 위젯(그림자 등)의 QPainter 렌더링 충돌을 방지합니다.
        if hasattr(self, '_current_widget') and self._current_widget:
            self._current_widget.setGraphicsEffect(None)


class BasePlotWidget(pg.PlotWidget):
    """앱 전체에서 공통으로 사용되는 PyQtGraph 추상화 클래스"""
    def __init__(self, y_label="値", x_label="日付", parent=None):
        super().__init__(parent)
        self.is_dark = True
        self.y_label = y_label
        self.x_label = x_label
        self.showGrid(x=True, y=True, alpha=0.25)
        self.plotItem.hideAxis('top')
        self.plotItem.hideAxis('right')
        self.apply_theme_custom()  # setBackground はここで一元管理

    def set_theme(self, is_dark: bool):
        self.is_dark = is_dark
        self.apply_theme_custom()

    def apply_theme_custom(self):
        gc = UIColors.get_graph_colors(self.is_dark)
        self.setBackground(gc['bg'])
        ax_pen   = pg.mkPen(color=gc['axis'], width=1)
        text_col = gc['text']
        text_pen = pg.mkPen(text_col)
        for ax_name in ('left', 'bottom'):
            ax = self.getAxis(ax_name)
            ax.setPen(ax_pen)
            ax.setTextPen(text_pen)
        self.setLabel('left',   self.y_label, color=text_col, size=Typography.CHART)
        self.setLabel('bottom', self.x_label, color=text_col, size=Typography.CHART)


class BaseWidget(QWidget):
    """アプリ全体の共通ウィジェット基底クラス"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_dark = True
        self.settings = load_settings()
        self.timer = QTimer(self)
        self._active_workers: list = []
        self._skel_effect: Optional[QGraphicsOpacityEffect] = None
        self._skel_anim: Optional[QPropertyAnimation] = None
        bus.app_quitting.connect(self._safe_terminate_workers)

    def closeEvent(self, event):
        """ウィジェット破棄時にシグナル接続を安全に解除してメモリ漏れを防ぎます。"""
        try:
            bus.app_quitting.disconnect(self._safe_terminate_workers)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)

    def track_worker(self, worker):
        """워커 스레드를 등록하여 앱 종료 시 안전하게 해제되도록 관리합니다."""
        if worker not in self._active_workers:
            self._active_workers.append(worker)
            worker.finished.connect(lambda: self._remove_worker(worker))

    def _remove_worker(self, worker):
        if worker in self._active_workers:
            self._active_workers.remove(worker)

    def _safe_terminate_workers(self):
        """앱 종료 시 실행 중인 스레드를 안전하게 종료합니다.
        quit() + wait() 후에도 실행 중이면 terminate() 로 강제 종료하여 좀비 스레드를 방지합니다."""
        for worker in self._active_workers:
            if worker.isRunning():
                worker.quit()
                if not worker.wait(1000):
                    worker.terminate()
                    worker.wait()

    def _copy_graph(self, target_widget=None):
        """グラフウィジェットをクリップボードにコピーします。target_widget が None の場合は self.plot_widget を使用。"""
        widget = target_widget if target_widget is not None else getattr(self, 'plot_widget', None)
        if widget is None:
            return
        QApplication.clipboard().setPixmap(widget.grab())
        QMessageBox.information(
            self, tr("完了"),
            tr("グラフ画像をクリップボードにコピーしました。\n(Excel等に貼り付け可能です)"),
        )

    def setup_timer(self, interval_minutes: int, timeout_slot, stagger_seconds: int = 0):
        """타이머를 설정합니다.
        stagger_seconds > 0 이면 첫 실행을 해당 초만큼 지연하여
        여러 위젯의 API 요청이 동시에 집중되는 것을 방지합니다."""
        self.timer.timeout.connect(timeout_slot)
        self.update_timer_interval(interval_minutes)
        if stagger_seconds > 0:
            # 첫 tick을 지연시킨 후 정규 간격으로 시작
            QTimer.singleShot(stagger_seconds * 1000, self.timer.start)
        else:
            self.timer.start()

    def update_timer_interval(self, interval_minutes: int):
        self.timer.setInterval(interval_minutes * 60 * 1000)

    def apply_settings(self):
        self.settings = load_settings()
        self._settings_dirty = False
        self.apply_settings_custom()

    def apply_settings_custom(self):
        pass

    def showEvent(self, event):
        """タブ切替で表示された際に保留中の設定更新を適用します。"""
        super().showEvent(event)
        if getattr(self, '_settings_dirty', False):
            self.apply_settings()

    def set_theme(self, is_dark: bool):
        self.is_dark = is_dark
        self.apply_theme_custom()

    def apply_theme_custom(self):
        pass

    def set_loading(self, is_loading: bool, target_widget: Optional[QWidget] = None):
        """スケルトンローディングアニメーションを対象ウィジェットに適用する共通メソッド。
        target_widget が None の場合は self 自身に適用する。
        setGraphicsEffect() が古いエフェクトを削除するため、None チェックで再生成を管理します。"""
        widget = target_widget if target_widget is not None else self
        if is_loading:
            if self._skel_effect is None:
                if self._skel_anim is not None:
                    self._skel_anim.stop()
                self._skel_effect = QGraphicsOpacityEffect()
                self._skel_anim = QPropertyAnimation(self._skel_effect, b"opacity", self)
                self._skel_anim.setDuration(800)
                self._skel_anim.setStartValue(0.3)
                self._skel_anim.setEndValue(1.0)
                self._skel_anim.setLoopCount(-1)
            widget.setGraphicsEffect(self._skel_effect)
            self._skel_anim.start()
        else:
            if self._skel_anim is not None:
                self._skel_anim.stop()
            widget.setGraphicsEffect(None)
            self._skel_effect = None  # Qt がエフェクトを削除したため参照をクリア

    def check_online_status(self) -> bool:
        if not getattr(QApplication.instance(), 'is_online', True):
            if hasattr(self, 'status_label'):
                self.status_label.setText("オフライン (待機中)")
                self.status_label.setStyleSheet("color: #ff5252; font-weight: bold;")
            return False
        return True
