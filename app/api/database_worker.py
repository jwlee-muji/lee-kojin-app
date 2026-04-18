"""
データ保存期間管理ワーカー

core/database.py は Qt に依存しないため、QThread ワーカーをここに分離。
"""
import logging
from PySide6.QtCore import QThread, Signal

from app.core.database import run_retention_policy

logger = logging.getLogger(__name__)


class DataRetentionWorker(QThread):
    """データ保存期間管理 (run_retention_policy) をバックグラウンドで実行するワーカー。"""
    finished = Signal()
    error    = Signal(str)

    def __init__(self, retention_days: int):
        super().__init__()
        self.retention_days = retention_days

    def run(self):
        try:
            run_retention_policy(self.retention_days)
            self.finished.emit()
        except Exception as e:
            logger.error(f"データ保存期間管理の実行中にエラーが発生しました: {e}", exc_info=True)
            self.error.emit(str(e))
