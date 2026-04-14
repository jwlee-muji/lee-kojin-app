"""
バグレポート送信モジュール
内蔵 SMTP 認証情報を使用して jw.lee@shirokumapower.com へ送信。
ユーザーによるメール設定は不要。
"""
import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)

BUG_REPORT_TO   = "jw.lee@shirokumapower.com"
_SMTP_HOST      = "smtp.gmail.com"
_SMTP_PORT      = 587


def _get_smtp_creds() -> tuple[str, str]:
    """内蔵 SMTP 認証情報を返す (user, password)"""
    try:
        from app.core._secrets import get_smtp_user, get_smtp_password
        return get_smtp_user(), get_smtp_password()
    except (ImportError, AttributeError):
        return "", ""


def is_smtp_ready() -> bool:
    """送信可能かどうか (認証情報が取得できるか)"""
    user, pw = _get_smtp_creds()
    return bool(user and pw)


class SendBugReportWorker(QThread):
    """バグレポートをバックグラウンドでメール送信するワーカー"""
    success = Signal()
    error   = Signal(str)

    def __init__(self, subject: str, body: str):
        super().__init__()
        self.subject = subject
        self.body    = body

    def run(self):
        user, password = _get_smtp_creds()
        if not user or not password:
            self.error.emit("SMTP credentials not configured.")
            return
        try:
            msg              = MIMEMultipart("alternative")
            msg["From"]      = user
            msg["To"]        = BUG_REPORT_TO
            msg["Subject"]   = self.subject
            msg.attach(MIMEText(self.body, "plain", "utf-8"))

            ctx = ssl.create_default_context()
            with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=30) as server:
                server.ehlo()
                server.starttls(context=ctx)
                server.login(user, password)
                server.send_message(msg)

            logger.info(f"Bug report sent to {BUG_REPORT_TO}")
            self.success.emit()

        except Exception as e:
            logger.error(f"Bug report send failed: {e}")
            self.error.emit(str(e))
