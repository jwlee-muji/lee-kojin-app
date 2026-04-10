from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QListWidget, QStackedWidget, QSplitter
from PySide6.QtCore import Qt
from power_reserve_widget import PowerReserveWidget
from imbalance_widget import ImbalanceWidget
from jkm_widget import JkmWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LEE 個人アプリ")
        self.resize(900, 600)

        # 메인 레이아웃 (사이드바 + 콘텐츠 영역)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0) # 메인 윈도우 여백을 없애서 화면에 꽉 차게 만듦

        # 화면 분할 및 사용자가 직접 크기 조절을 할 수 있도록 QSplitter 적용
        self.main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # 1. サイドバー (サイドバーメニュー)
        self.sidebar = QListWidget()
        self.sidebar.setMinimumWidth(180) # 텍스트가 잘리지 않도록 최소 너비 강제 고정
        self.main_splitter.addWidget(self.sidebar)

        # 2. スタック領域 (画面切り替え用)
        self.content_stack = QStackedWidget()
        self.main_splitter.addWidget(self.content_stack)
        self.sidebar.currentRowChanged.connect(self.content_stack.setCurrentIndex)
        
        # 사이드바와 콘텐츠 영역의 초기 크기 및 창 크기 조절 시 반응형 비율 설정
        self.main_splitter.setSizes([200, 700])
        self.main_splitter.setStretchFactor(0, 0) # 창을 키울 때 사이드바는 가급적 원래 크기 유지
        self.main_splitter.setStretchFactor(1, 1) # 창을 키울 때 우측 콘텐츠 영역이 넓어지도록 설정

        # 3. 電力予備率ウィジェットの接続
        self.content_stack.addWidget(PowerReserveWidget())
        self.sidebar.addItem("電力予備率 (OCCTO)")

        # 4. インバランス単価ウィジェットの接続
        self.content_stack.addWidget(ImbalanceWidget())
        self.sidebar.addItem("インバランス単価")

        # 5. JKM LNG スポット価格ウィジェットの接続
        self.content_stack.addWidget(JkmWidget())
        self.sidebar.addItem("JKM LNG 価格")
