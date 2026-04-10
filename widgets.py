from PySide6.QtWidgets import QTableWidget, QApplication
from PySide6.QtGui import QKeySequence

_chrome_driver_path = None


def get_chrome_driver_path():
    global _chrome_driver_path
    if _chrome_driver_path is None:
        from webdriver_manager.chrome import ChromeDriverManager
        _chrome_driver_path = ChromeDriverManager().install()
    return _chrome_driver_path


# Excelへコピペ可能にするカスタムテーブルクラス
class ExcelCopyTableWidget(QTableWidget):
    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
        else:
            super().keyPressEvent(event)

    def copy_selection(self):
        selection = self.selectedIndexes()
        if not selection:
            return
        top_row = min(index.row() for index in selection)
        bottom_row = max(index.row() for index in selection)
        left_col = min(index.column() for index in selection)
        right_col = max(index.column() for index in selection)

        copy_text = ""

        # 선택된 범위의 헤더(열 이름)도 함께 복사
        header_data = []
        for col in range(left_col, right_col + 1):
            header_item = self.horizontalHeaderItem(col)
            header_data.append(header_item.text() if header_item else "")
        copy_text += "\t".join(header_data) + "\n"

        for row in range(top_row, bottom_row + 1):
            row_data = []
            for col in range(left_col, right_col + 1):
                item = self.item(row, col)
                row_data.append(item.text() if item else "")
            copy_text += "\t".join(row_data) + "\n"

        QApplication.clipboard().setText(copy_text)
