from PySide6.QtWidgets import QTableWidget, QApplication, QWidget, QStackedWidget, QGraphicsOpacityEffect
from PySide6.QtGui import QKeySequence
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve
import pyqtgraph as pg
from app.core.config import load_settings


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
        self._fade_anim = QPropertyAnimation()
        self._fade_anim.setPropertyName(b"opacity")
        self._fade_anim.setDuration(200)
        self._fade_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._fade_anim.finished.connect(self._on_fade_finished)
        self.currentChanged.connect(self._on_current_changed)

    def _on_current_changed(self, index):
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
        self.setBackground('#1e1e1e')
        self.showGrid(x=True, y=True, alpha=0.25)
        self.plotItem.hideAxis('top')
        self.plotItem.hideAxis('right')
        self.apply_theme_custom()

    def set_theme(self, is_dark: bool):
        self.is_dark = is_dark
        self.apply_theme_custom()

    def apply_theme_custom(self):
        self.setBackground('#1e1e1e' if self.is_dark else '#ffffff')
        ax_pen = pg.mkPen(color='#555555' if self.is_dark else '#dddddd', width=1)
        text_pen = pg.mkPen('#aaaaaa' if self.is_dark else '#666666')
        for ax_name in ('left', 'bottom'):
            ax = self.getAxis(ax_name)
            ax.setPen(ax_pen)
            ax.setTextPen(text_pen)
        self.setLabel('left', self.y_label, color='#aaaaaa' if self.is_dark else '#666666', size='9pt')
        self.setLabel('bottom', self.x_label, color='#aaaaaa' if self.is_dark else '#666666', size='9pt')


class BaseWidget(QWidget):
    """アプリ全体の共通ウィジェット基底クラス"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_dark = True
        self.settings = load_settings()
        self.timer = QTimer(self)

    def setup_timer(self, interval_minutes: int, timeout_slot):
        self.timer.timeout.connect(timeout_slot)
        self.update_timer_interval(interval_minutes)
        self.timer.start()

    def update_timer_interval(self, interval_minutes: int):
        self.timer.setInterval(interval_minutes * 60 * 1000)

    def apply_settings(self):
        self.settings = load_settings()
        self.apply_settings_custom()

    def apply_settings_custom(self):
        pass

    def set_theme(self, is_dark: bool):
        self.is_dark = is_dark
        self.apply_theme_custom()

    def apply_theme_custom(self):
        pass

    def check_online_status(self) -> bool:
        if not getattr(QApplication.instance(), 'is_online', True):
            if hasattr(self, 'status_label'):
                self.status_label.setText("オフライン (待機中)")
                self.status_label.setStyleSheet("color: #ff5252; font-weight: bold;")
            return False
        return True
