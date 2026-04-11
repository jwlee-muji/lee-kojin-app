from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidgetItem,
    QPushButton, QMessageBox, QHeaderView, QDateEdit,
)
from PySide6.QtCore import QTimer, QThread, Signal, QDate, Qt
from PySide6.QtGui import QBrush, QColor
from datetime import datetime, timedelta
from .common import ExcelCopyTableWidget, get_chrome_driver_path
import time


class FetchWorker(QThread):
    data_fetched   = Signal(list, list)
    error_occurred = Signal(str)

    def __init__(self, target_date_str):
        super().__init__()
        self.target_date_str = target_date_str

    def run(self):
        driver = None
        try:
            url = "https://web-kohyo.occto.or.jp/kks-web-public/"

            options = webdriver.ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument(
                "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36"
            )

            service = Service(get_chrome_driver_path())
            driver  = webdriver.Chrome(service=service, options=options)
            driver.get(url)

            WebDriverWait(driver, 15).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "#area-table-container table tr")) > 5
            )

            today_str = datetime.now().strftime("%Y-%m-%d")
            if self.target_date_str != today_str:
                date_inputs = driver.find_elements(
                    By.XPATH,
                    "//input[@id='text-today'] | //input[contains(@class, 'hasDatepicker')] | //input[@type='date']"
                )
                if not date_inputs:
                    raise Exception("カレンダー(日付入力)要素が見つかりません。")

                target_el = next((inp for inp in date_inputs if inp.is_displayed()), date_inputs[0])
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
                WebDriverWait(driver, 5).until(EC.visibility_of(target_el))

                try:
                    old_table_html = driver.find_element(
                        By.CSS_SELECTOR, "#area-table-container table"
                    ).get_attribute('innerHTML')
                except Exception:
                    old_table_html = ""

                target_date_slash = self.target_date_str.replace("-", "/")
                driver.execute_script("""
                    var el = arguments[0], valSlash = arguments[1];
                    el.removeAttribute('readonly');
                    var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
                    if (setter && setter.set) setter.set.call(el, valSlash);
                    else el.value = valSlash;
                    el.dispatchEvent(new Event('input',  { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    if (typeof jQuery !== 'undefined' && jQuery(el).data('datepicker'))
                        jQuery(el).datepicker('setDate', valSlash);
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                """, target_el, target_date_slash)
                time.sleep(0.5)

                try:
                    actions = ActionChains(driver)
                    actions.move_to_element(target_el).click()
                    actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).send_keys(Keys.BACKSPACE)
                    actions.send_keys(target_date_slash).send_keys(Keys.ENTER)
                    actions.perform()
                except Exception:
                    pass

                WebDriverWait(driver, 5).until(
                    EC.any_of(EC.staleness_of(target_el), EC.element_to_be_clickable(target_el))
                )

                search_btns = driver.find_elements(
                    By.XPATH,
                    "//button[contains(text(),'表示') or contains(text(),'検索') or contains(text(),'更新')]"
                    " | //input[@type='button' or @type='submit']"
                    "[contains(@value,'表示') or contains(@value,'検索') or contains(@value,'更新')]"
                )
                if search_btns:
                    btn = next((b for b in search_btns if b.is_displayed()), search_btns[0])
                    driver.execute_script("arguments[0].click();", btn)
                else:
                    target_el.send_keys(Keys.ENTER)

                try:
                    WebDriverWait(driver, 15).until(
                        lambda d: (
                            len(d.find_elements(By.CSS_SELECTOR, "#area-table-container table tr")) > 5
                            and d.find_element(By.CSS_SELECTOR, "#area-table-container table")
                               .get_attribute('innerHTML') != old_table_html
                        )
                    )
                except TimeoutException:
                    raise Exception("日付を変更して検索しましたが、データの更新に失敗したか、該当するデータが存在しません。")

            page_source = driver.page_source
            soup        = BeautifulSoup(page_source, 'html.parser')
            container   = soup.find(id="area-table-container")
            if not container:
                raise ValueError("'area-table-container' 要素が見つかりません。")

            table = container.find('table')
            if not table:
                raise ValueError("データテーブルが見つかりません。")

            tr_elements = table.find_all('tr')
            if not tr_elements or len(tr_elements) < 2:
                raise ValueError("テーブルのデータが不十分です。")

            original_header_cells = tr_elements[0].find_all(['th', 'td'])
            area_headers  = [cell.get_text(strip=True) for cell in original_header_cells[1:]]
            final_headers = ["時間"] + area_headers
            final_rows    = [
                [cell.get_text(strip=True) for cell in tr.find_all(['th', 'td'])]
                for tr in tr_elements[1:]
                if tr.find_all(['th', 'td'])
            ]

            self.data_fetched.emit(final_headers, final_rows)

        except TimeoutException:
            self.error_occurred.emit("データの読み込みがタイムアウトしました。")
        except Exception as e:
            self.error_occurred.emit(f"エラーが発生しました: {str(e)}")
        finally:
            if driver:
                driver.quit()


class PowerReserveWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        top_layout = QHBoxLayout()
        self.title_label  = QLabel("エリア別 予備率 (5分自動更新)")
        self.date_edit    = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.status_label = QLabel("待機中")
        self.status_label.setStyleSheet("color: gray; font-weight: bold;")
        self.refresh_btn  = QPushButton("表示")
        self.refresh_btn.clicked.connect(self.fetch_data)

        top_layout.addWidget(self.title_label)
        top_layout.addWidget(self.date_edit)
        top_layout.addWidget(self.status_label)
        top_layout.addStretch()
        top_layout.addWidget(self.refresh_btn)
        layout.addLayout(top_layout)

        self.table = ExcelCopyTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("alternate-background-color: #f5f5f5; background-color: #ffffff;")
        layout.addWidget(self.table)

        self.worker = None
        self._alerted_low_reserve = set()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.fetch_data)
        self.timer.start(300_000)

        self.fetch_data()

    def fetch_data(self):
        if self.worker and self.worker.isRunning():
            return
        selected_date = self.date_edit.date().toString("yyyy-MM-dd")
        self.refresh_btn.setEnabled(False)
        self.status_label.setText("更新中...")
        self.status_label.setStyleSheet("color: blue; font-weight: bold;")
        self.worker = FetchWorker(selected_date)
        self.worker.data_fetched.connect(self._update_table)
        self.worker.error_occurred.connect(self._handle_error)
        self.worker.start()

    def _handle_error(self, err):
        self.status_label.setText("更新失敗")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        QMessageBox.warning(self, "エラー", f"データの取得中にエラーが発生しました:\n{err}")
        self.refresh_btn.setEnabled(True)

    def _update_table(self, headers, rows):
        self.table.setUpdatesEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(0)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        if headers:
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)

        now           = datetime.now()
        selected_qd   = self.date_edit.date()
        selected_date = datetime(selected_qd.year(), selected_qd.month(), selected_qd.day())
        is_today      = selected_date.date() == now.date()
        is_past_day   = selected_date.date() <  now.date()
        threshold     = now - timedelta(minutes=30)
        new_alerts    = []

        for row_idx, row_data in enumerate(rows):
            self.table.insertRow(row_idx)

            is_past = is_past_day
            if not is_past and is_today and row_data:
                try:
                    row_dt = datetime.combine(now.date(), datetime.strptime(row_data[0], "%H:%M").time())
                    is_past = row_dt < threshold
                except ValueError:
                    pass

            for col_idx, cell_data in enumerate(row_data):
                item = QTableWidgetItem(cell_data)
                item.setTextAlignment(Qt.AlignCenter)
                val = None

                reserve_level = None
                if col_idx > 0:
                    try:
                        val = float(cell_data.replace('%', '').strip())
                        if   val <= 8.0:  reserve_level = 'low'
                        elif val <= 10.0: reserve_level = 'warning'
                    except ValueError:
                        pass

                if   reserve_level == 'low':     item.setBackground(QBrush(QColor("#ff6666")))
                elif reserve_level == 'warning':  item.setBackground(QBrush(QColor("#ffeb3b")))
                elif is_past:                     item.setBackground(QBrush(QColor("#e0e0e0")))
                self.table.setItem(row_idx, col_idx, item)
                
                # 현재 시간 이후 & 예비율 8% 이하인 경우 알림 목록에 추가 (중복 검사 방지)
                if is_today and not is_past and reserve_level == 'low' and val is not None:
                    area = headers[col_idx] if col_idx < len(headers) else f"エリア{col_idx}"
                    key  = (row_data[0], area)
                    if key not in self._alerted_low_reserve:
                        self._alerted_low_reserve.add(key)
                        new_alerts.append((row_data[0], area, val))

            self.refresh_btn.setEnabled(True)

        self.status_label.setText("更新完了")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")
        self.table.setUpdatesEnabled(True)

        if new_alerts:
            lines = "\n".join(f"  {t}  |  {area}:  {val}" for t, area, val in new_alerts)
            QMessageBox.warning(
                self, "⚠ 予備率警告",
                f"現在時刻以降に予備率8%以下のコマが発生しています。\n\n{lines}"
            )
