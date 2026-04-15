"""
バグレポート送信モジュール
内蔵 SMTP 認証情報を使用して jw.lee@shirokumapower.com へ送信。
ユーザーによるメール設定は不要。
"""
import json
import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from PySide6.QtCore import QThread, Signal
from app.api.base import BaseWorker

logger = logging.getLogger(__name__)

BUG_REPORT_TO   = "jw.lee@shirokumapower.com"
_SMTP_HOST      = "smtp.gmail.com"
_SMTP_PORT      = 587


def _get_smtp_creds() -> tuple[str, str]:
    """SMTP 認証情報を返す (優先順位: 環境変数 → 設定ファイル → 内蔵キー)"""
    import os
    # 1. 環境変数
    env_user = os.environ.get("SMTP_USER", "").strip()
    env_pw   = os.environ.get("SMTP_PASSWORD", "").strip()
    if env_user and env_pw:
        return env_user, env_pw
    # 2. 設定ファイル
    try:
        from app.core.config import load_settings
        s = load_settings()
        cfg_user = s.get("user_smtp_user", "").strip()
        cfg_pw   = s.get("user_smtp_password", "").strip()
        if cfg_user and cfg_pw:
            return cfg_user, cfg_pw
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"設定ファイルからSMTP認証情報を読み込めませんでした: {e}")
    # 3. 内蔵キー (フォールバック)
    try:
        from app.core._secrets import get_smtp_user, get_smtp_password
        return get_smtp_user(), get_smtp_password()
    except (ImportError, AttributeError):
        return "", ""


def is_smtp_ready() -> bool:
    """送信可能かどうか (認証情報が取得できるか)"""
    user, pw = _get_smtp_creds()
    return bool(user and pw)


class SendBugReportWorker(BaseWorker):
    """バグレポートをバックグラウンドでメール送信するワーカー"""
    success = Signal()

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
