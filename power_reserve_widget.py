from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidgetItem, QPushButton, QHBoxLayout, QMessageBox, QHeaderView, QDateEdit
from PySide6.QtCore import QTimer, QThread, Signal, QDate, Qt
from PySide6.QtGui import QBrush, QColor
from datetime import datetime, timedelta
from widgets import ExcelCopyTableWidget, get_chrome_driver_path
import time

# バックグラウンドでデータを収集するスレッド
class FetchWorker(QThread):
    data_fetched = Signal(list, list)  # ヘッダーリスト、データ（行）リスト
    error_occurred = Signal(str)

    def __init__(self, target_date_str):
        super().__init__()
        self.target_date_str = target_date_str # 포맷: YYYY-MM-DD

    def run(self):
        driver = None
        try:
            url = "https://web-kohyo.occto.or.jp/kks-web-public/"

            # Selenium WebDriver 설정
            options = webdriver.ChromeOptions()
            options.add_argument('--headless')  # 브라우저 창을 띄우지 않음
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080') # UI 요소가 숨겨지지 않도록 창 크기 지정
            options.add_argument('--no-sandbox') # 리소스 제한 우회 (메모리 최적화)
            options.add_argument('--disable-dev-shm-usage') # 메모리 부족 문제 방지 (최적화)
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")
            
            service = Service(get_chrome_driver_path())
            driver = webdriver.Chrome(service=service, options=options)

            driver.get(url)

            # --- 데이터 갱신 및 날짜 지정 처리 ---
            # 1. 일단 기본 페이지(당일 데이터)가 완전히 로딩될 때까지 대기
            WebDriverWait(driver, 15).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "#area-table-container table tr")) > 5
            )

            today_str = datetime.now().strftime("%Y-%m-%d")
            if self.target_date_str != today_str:
                # 1. 날짜 입력칸 찾기
                date_inputs = driver.find_elements(By.XPATH, "//input[@id='text-today'] | //input[contains(@class, 'hasDatepicker')] | //input[@type='date']")
                
                if not date_inputs:
                    raise Exception("カレンダー(日付入力)要素が見つかりません。")
                
                target_el = next((inp for inp in date_inputs if inp.is_displayed()), date_inputs[0])
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
                WebDriverWait(driver, 5).until(EC.visibility_of(target_el)) # 스크롤 후 요소가 보일 때까지 대기

                # 2. 업데이트 전의 테이블 HTML 전체를 저장 (변화 감지용)
                try:
                    old_table_html = driver.find_element(By.CSS_SELECTOR, "#area-table-container table").get_attribute('innerHTML')
                except:
                    old_table_html = ""

                # 3. 날짜 설정 (jQuery UI Datepicker 및 일반 Input 대응)
                target_date_slash = self.target_date_str.replace("-", "/")
                
                driver.execute_script("""
                    var el = arguments[0];
                    var valSlash = arguments[1];
                    
                    el.removeAttribute('readonly');
                    
                    var setValue = function(val) {
                        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
                        if (setter && setter.set) {
                            setter.set.call(el, val);
                        } else {
                            el.value = val;
                        }
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    };
                    
                    setValue(valSlash);
                    
                    // 사이트가 jQuery UI Datepicker를 사용한다면 내장 함수로 확실히 변경
                    if (typeof jQuery !== 'undefined' && jQuery(el).data('datepicker')) {
                        jQuery(el).datepicker('setDate', valSlash);
                    }
                    
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                """, target_el, target_date_slash)
                time.sleep(0.5)

                # ActionChains 백업 타이핑 (JS가 실패할 경우 대비하여 사람의 타이핑 흉내)
                try:
                    actions = ActionChains(driver)
                    actions.move_to_element(target_el).click()
                    actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).send_keys(Keys.BACKSPACE)
                    actions.send_keys(target_date_slash)
                    actions.send_keys(Keys.ENTER)
                    actions.perform()
                except:
                    pass

                WebDriverWait(driver, 5).until(EC.any_of(EC.staleness_of(target_el), EC.element_to_be_clickable(target_el)))

                # 4. 검색 버튼 찾아서 클릭
                search_btns = driver.find_elements(By.XPATH, "//button[contains(text(), '表示') or contains(text(), '検索') or contains(text(), '更新')] | //input[@type='button' or @type='submit'][contains(@value, '表示') or contains(@value, '検索') or contains(@value, '更新')]")
                if search_btns:
                    btn = next((b for b in search_btns if b.is_displayed()), search_btns[0])
                    driver.execute_script("arguments[0].click();", btn)
                else:
                    target_el.send_keys(Keys.ENTER) # 버튼이 없으면 엔터키로 폼 제출
                
                # 5. 새로운 데이터 로딩 대기 (HTML의 변화를 직접 감지)
                try:
                    WebDriverWait(driver, 15).until(
                        lambda d: (
                            len(d.find_elements(By.CSS_SELECTOR, "#area-table-container table tr")) > 5 
                            and d.find_element(By.CSS_SELECTOR, "#area-table-container table").get_attribute('innerHTML') != old_table_html
                        )
                    )
                    # time.sleep(0.5) # WebDriverWait으로 충분하므로 제거
                except TimeoutException:
                    raise Exception("日付を変更して検索しましたが、データの更新に失敗したか、該当するデータが存在しません。")
            # -----------------------------------

            # JavaScript가 실행된 후의 페이지 소스를 가져옴
            page_source = driver.page_source

            soup = BeautifulSoup(page_source, 'html.parser')
            
            container = soup.find(id="area-table-container")
            if not container:
                raise ValueError("'area-table-container' 要素が見つかりません。")
                
            table = container.find('table')
            if not table:
                raise ValueError("データテーブルが見つかりません。")

            tr_elements = table.find_all('tr')
            if not tr_elements or len(tr_elements) < 2: # 이 부분은 이제 통과될 것입니다.
                raise ValueError("テーブルのデータが不十分です。")

            # 1. 1行目2列目以降からエリア名（ヘッダー）を抽出
            original_header_cells = tr_elements[0].find_all(['th', 'td'])
            area_headers = [cell.get_text(strip=True) for cell in original_header_cells[1:]]
            
            # 2. 最終的に表示するテーブルのヘッダーを生成（時間 + エリア名）
            final_headers = ["時間"] + area_headers

            # 3. 2行目以降から各行のデータを抽出
            final_rows = []
            for tr in tr_elements[1:]:
                row_data = [cell.get_text(strip=True) for cell in tr.find_all(['th', 'td'])]
                if row_data:
                    final_rows.append(row_data)

            self.data_fetched.emit(final_headers, final_rows)

        except TimeoutException:
            self.error_occurred.emit("データの読み込みがタイムアウトしました。")
        except Exception as e:
            self.error_occurred.emit(f"エラーが発生しました: {str(e)}")
        finally:
            # 예외 발생 여부와 상관없이 브라우저를 반드시 종료하여 좀비 프로세스(메모리 누수) 방지
            if driver:
                driver.quit()

# 画面に表示されるウィジェット
class PowerReserveWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # 上部レイアウト（タイトル + 更新ボタン）
        top_layout = QHBoxLayout()
        self.title_label = QLabel("エリア別 予備率 (5分自動更新)")

        # 날짜 선택용 캘린더 위젯
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate()) # 디폴트는 오늘
        self.date_edit.setDisplayFormat("yyyy-MM-dd")

        # 스테이터스 표시용 라벨 추가
        self.status_label = QLabel("待機中")
        self.status_label.setStyleSheet("color: gray; font-weight: bold;")

        self.refresh_btn = QPushButton("表示")
        self.refresh_btn.clicked.connect(self.fetch_data)
        
        top_layout.addWidget(self.title_label)
        top_layout.addWidget(self.date_edit)
        top_layout.addWidget(self.status_label)
        top_layout.addStretch()
        top_layout.addWidget(self.refresh_btn)
        layout.addLayout(top_layout)

        # データを表示するテーブル
        self.table = ExcelCopyTableWidget()
        self.table.setAlternatingRowColors(True) # 行の背景色を交互に変更して見やすくする
        self.table.setStyleSheet("alternate-background-color: #f5f5f5; background-color: #ffffff;")
        layout.addWidget(self.table)

        self.worker = None

        # 新しい低予備率コマを追跡するセット（セッション中の重複通知防止）
        self._alerted_low_reserve = set()

        # 5分（300,000 ms）ごとに自動更新するタイマーを設定
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.fetch_data)
        self.timer.start(300000)

        self.fetch_data()

    def fetch_data(self):
        # 이미 데이터 갱신 작업이 진행 중이라면 중복 실행 방지
        if self.worker and self.worker.isRunning():
            return
            
        selected_date = self.date_edit.date().toString("yyyy-MM-dd")
        self.refresh_btn.setEnabled(False) # 重複クリック防止
        self.status_label.setText("更新中...")
        self.status_label.setStyleSheet("color: blue; font-weight: bold;")
        self.worker = FetchWorker(selected_date)
        self.worker.data_fetched.connect(self.update_table)
        self.worker.error_occurred.connect(self.handle_error)
        self.worker.start()

    def handle_error(self, err):
        self.status_label.setText("更新失敗")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        QMessageBox.warning(self, "エラー", f"データの取得中にエラーが発生しました:\n{err}")
        self.refresh_btn.setEnabled(True)

    def update_table(self, headers, rows):
        self.table.setUpdatesEnabled(False) # UI 업데이트 일시 중지 (렌더링 속도 최적화 및 깜빡임 방지)
        
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(0) 

        # テーブルの列幅をウィンドウサイズに合わせて自動調整
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch) # 全体を均等に伸ばす
        if len(headers) > 0:
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents) # 時間列だけは文字幅に合わせる

        now = datetime.now()
        selected_qdate = self.date_edit.date()
        selected_date = datetime(selected_qdate.year(), selected_qdate.month(), selected_qdate.day())
        
        is_today = selected_date.date() == now.date()
        is_past_day = selected_date.date() < now.date()
        threshold_time = now - timedelta(minutes=30)

        for row_idx, row_data in enumerate(rows):
            self.table.insertRow(row_idx)
            
            is_past = False
            if is_past_day:
                is_past = True # 선택한 날짜가 과거면 전부 회색 처리
            elif is_today and row_data:
                try:
                    row_time = datetime.strptime(row_data[0], "%H:%M").time()
                    row_datetime = datetime.combine(now.date(), row_time)
                    if row_datetime < threshold_time:
                        is_past = True
                except ValueError:
                    pass

            for col_idx, cell_data in enumerate(row_data):
                item = QTableWidgetItem(cell_data)
                item.setTextAlignment(Qt.AlignCenter) # 가운데 정렬
                
                reserve_level = None
                if col_idx > 0: # 시간 열(0번째)은 검사에서 제외
                    try:
                        val = float(cell_data.replace('%', '').strip())
                        if val <= 8.0:
                            reserve_level = 'low'
                        elif val <= 10.0:
                            reserve_level = 'warning'
                    except ValueError:
                        pass

                if reserve_level == 'low':
                    item.setBackground(QBrush(QColor("#ff6666"))) # 8%以下は赤
                elif reserve_level == 'warning':
                    item.setBackground(QBrush(QColor("#ffeb3b"))) # 8%超10%以下は黄
                elif is_past:
                    item.setBackground(QBrush(QColor("#e0e0e0"))) # 過去の時間は薄いグレーで塗りつぶす
                self.table.setItem(row_idx, col_idx, item)
                
            self.refresh_btn.setEnabled(True)
        self.status_label.setText("更新完了")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")

        self.table.setUpdatesEnabled(True)

        # 今日のデータのみ低予備率アラートをチェック
        if is_today:
            self._check_low_reserve_alerts(headers, rows)

    def _check_low_reserve_alerts(self, headers, rows):
        """現在時刻以降のコマで新たに予備率8%以下が出現した場合に警告する"""
        now = datetime.now()
        new_alerts = []

        for row_data in rows:
            if not row_data:
                continue
            try:
                row_time_obj = datetime.strptime(row_data[0], "%H:%M").time()
                row_dt = datetime.combine(now.date(), row_time_obj)
                if row_dt <= now:
                    continue  # 現在時刻以前のコマは無視
            except ValueError:
                continue

            for col_idx in range(1, len(row_data)):
                try:
                    val = float(row_data[col_idx].replace('%', '').strip())
                    if val <= 8.0:
                        area = headers[col_idx] if col_idx < len(headers) else f"エリア{col_idx}"
                        key = (row_data[0], area)
                        if key not in self._alerted_low_reserve:
                            self._alerted_low_reserve.add(key)
                            new_alerts.append((row_data[0], area, row_data[col_idx]))
                except ValueError:
                    pass

        if new_alerts:
            lines = "\n".join(f"  {t}  |  {area}:  {val}" for t, area, val in new_alerts)
            QMessageBox.warning(
                self, "⚠ 予備率警告",
                f"現在時刻以降に予備率8%以下のコマが発生しています。\n\n{lines}"
            )