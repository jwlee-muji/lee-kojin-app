from PySide6.QtWidgets import QTableWidget, QApplication
from PySide6.QtGui import QKeySequence

_chrome_driver_path = None


def get_chrome_driver_path():
    global _chrome_driver_path
    if _chrome_driver_path is None:
        from webdriver_manager.chrome import ChromeDriverManager
        _chrome_driver_path = ChromeDriverManager().install()
    return _chrome_driver_path


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
