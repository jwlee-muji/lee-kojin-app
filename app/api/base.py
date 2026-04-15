"""
全APIワーカーの基底クラス

各ワーカーは BaseWorker を継承することで:
- 共通の error シグナル (Signal(str)) を取得
- _emit_error() ヘルパーで「ログ記録 + シグナル送出」を一括処理
- HTTP_TIMEOUT: 全 API リクエスト共通のタイムアウト秒数 (定数)
- _fetch_with_retry(): 一時的なエラーに対して自動リトライするヘルパー
"""
import logging
import time
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)

# 全 API リクエスト共通のタイムアウト秒数
HTTP_TIMEOUT: int = 30


class BaseWorker(QThread):
    """全APIワーカーの基底クラス"""
    error = Signal(str)

    # リトライ設定 (サブクラスでオーバーライド可)
    MAX_RETRIES: int  = 3
    RETRY_DELAY: float = 2.0  # seconds

    def _emit_error(self, message: str, exc: Exception = None) -> None:
        """エラーをログに記録しシグナルで通知します。

        Args:
            message: ログ/シグナルに含めるエラー説明文
            exc: 発生した例外 (省略可)。指定するとトレースバックもログに出力。
        """
        logger.error(message, exc_info=bool(exc))
        self.error.emit(f"{message}: {exc}" if exc else message)

    def _fetch_with_retry(self, fetch_fn, *args, **kwargs):
        """一時的なネットワークエラーに対して MAX_RETRIES 回まで自動リトライします。

        Args:
            fetch_fn: 呼び出す関数
            *args / **kwargs: fetch_fn に渡す引数

        Returns:
            fetch_fn の戻り値

        Raises:
            最後の試行で発生した例外
        """
        last_exc: Exception = RuntimeError("fetch_fn が呼び出されませんでした")
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return fetch_fn(*args, **kwargs)
            except Exception as e:
                last_exc = e
                if attempt < self.MAX_RETRIES:
                    logger.warning(
                        f"フェッチ失敗 (試行 {attempt}/{self.MAX_RETRIES}): {e}"
                        f" — {self.RETRY_DELAY:.0f}秒後に再試行します..."
                    )
                    time.sleep(self.RETRY_DELAY)
        raise last_exc
