from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QListWidget, QStackedWidget, QSplitter
from PySide6.QtCore import Qt
from .widgets.power_reserve import PowerReserveWidget
from .widgets.imbalance import ImbalanceWidget
from .widgets.jkm import JkmWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LEE 個人アプリ")
        self.resize(900, 600)

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # 사이드바
        self.sidebar = QListWidget()
        self.sidebar.setMinimumWidth(180)
        self.main_splitter.addWidget(self.sidebar)

        # 컨텐츠 영역
        self.content_stack = QStackedWidget()
        self.main_splitter.addWidget(self.content_stack)
        self.sidebar.currentRowChanged.connect(self.content_stack.setCurrentIndex)

        self.main_splitter.setSizes([200, 700])
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)

        self._add_page(PowerReserveWidget(), "電力予備率 (OCCTO)")
        self._add_page(ImbalanceWidget(),    "インバランス単価")
        self._add_page(JkmWidget(),          "JKM LNG 価格")

    def _add_page(self, widget, label: str):
        """위젯과 사이드바 항목을 한 번에 등록. 새 페이지 추가 시 이 메서드만 호출."""
        self.content_stack.addWidget(widget)
        self.sidebar.addItem(label)
