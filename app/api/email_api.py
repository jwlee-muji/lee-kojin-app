"""
バグレポート送信モジュール
内蔵 SMTP 認証情報を使用して jw.lee@shirokumapower.com へ送信。
ユーザーによるメール設定は不要。
"""
import json
import smtplib
import ssl
import time
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from PySide6.QtCore import QThread, Signal
from app.api.base import BaseWorker
from app.core.config import APP_DIR

logger = logging.getLogger(__name__)

BUG_REPORT_TO   = "jw.lee@shirokumapower.com"
_SMTP_HOST      = "smtp.gmail.com"
_SMTP_PORT      = 587

# P1-15 — 송신 실패 시 로컬 큐 (다음 앱 시작 시 flush_pending_bug_reports() 로 재송신)
_PENDING_QUEUE_FILE = APP_DIR / "pending_bug_reports.json"
# Exponential backoff between attempts (총 4 시도 = 1s / 2s / 4s sleep + 첫 시도)
_RETRY_SLEEPS_SEC = (1.0, 2.0, 4.0)


# ──────────────────────────────────────────────────────────────────────
# Pending queue I/O
# ──────────────────────────────────────────────────────────────────────
def _load_pending_queue() -> list[dict]:
    """로컬 큐 파일 로드. 파일이 없거나 깨졌으면 빈 list 반환."""
    try:
        if _PENDING_QUEUE_FILE.exists():
            return json.loads(_PENDING_QUEUE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"pending bug-report queue 로드 실패: {e}", exc_info=True)
    return []


def _save_pending_queue(items: list[dict]) -> None:
    try:
        _PENDING_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PENDING_QUEUE_FILE.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning(f"pending bug-report queue 저장 실패: {e}", exc_info=True)


def _enqueue_pending(subject: str, body: str) -> None:
    """송신 실패한 항목을 큐에 추가."""
    items = _load_pending_queue()
    items.append({
        "subject":   subject,
        "body":      body,
        "queued_at": time.time(),
    })
    _save_pending_queue(items)
    logger.info(f"bug report queued (총 {len(items)} 건 대기 중)")


def _send_once_blocking(subject: str, body: str, user: str, password: str) -> bool:
    """단일 SMTP 송신 시도 (예외 raise X, bool 반환)."""
    try:
        msg              = MIMEMultipart("alternative")
        msg["From"]      = user
        msg["To"]        = BUG_REPORT_TO
        msg["Subject"]   = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        ctx = ssl.create_default_context()
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.login(user, password)
            server.send_message(msg)
        return True
    except smtplib.SMTPAuthenticationError as e:
        # 인증 오류는 재시도 의미 없음 — caller 가 처리
        logger.error(f"SMTP 認証エラー: {e}")
        raise
    except Exception as e:
        logger.warning(f"SMTP 단일 송신 실패: {e}")
        return False


def flush_pending_bug_reports() -> int:
    """큐에 쌓인 bug report 들을 재송신. 성공한 항목은 큐에서 제거.

    앱 시작 후 네트워크 가용 시점에 호출. 인증 정보 없으면 즉시 0 반환.

    Returns
    -------
    int : 재송신 성공 건수.
    """
    items = _load_pending_queue()
    if not items:
        return 0
    user, password = _get_smtp_creds()
    if not user or not password:
        logger.info("flush_pending: SMTP 미설정 — 큐 유지")
        return 0
    sent = 0
    remaining: list[dict] = []
    for it in items:
        try:
            ok = _send_once_blocking(it["subject"], it["body"], user, password)
        except smtplib.SMTPAuthenticationError:
            # 인증 실패 = 큐 보존
            remaining.append(it)
            continue
        if ok:
            sent += 1
        else:
            remaining.append(it)
    _save_pending_queue(remaining)
    if sent:
        logger.info(f"pending bug reports 재송신 성공: {sent}/{len(items)}")
    return sent


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
        """4 회 시도 (sleep 1s / 2s / 4s) → 모두 실패 시 로컬 큐에 보존.

        P1-15 — 인증 오류는 재시도 의미 없으므로 즉시 큐에 저장.
        """
        user, password = _get_smtp_creds()
        if not user or not password:
            # SMTP 미설정 — 큐에 저장 (다음 시작 시 재송신)
            _enqueue_pending(self.subject, self.body)
            self.error.emit(
                "SMTP 認証情報が未設定 — レポートをローカルに保存しました "
                "(次回起動時に再送信)"
            )
            return

        last_err = ""
        for attempt in range(4):   # 시도 1 + 재시도 3 = 총 4 회
            if attempt > 0:
                # exponential backoff: 1s → 2s → 4s
                time.sleep(_RETRY_SLEEPS_SEC[attempt - 1])
            try:
                if _send_once_blocking(self.subject, self.body, user, password):
                    logger.info(
                        f"Bug report sent to {BUG_REPORT_TO} "
                        f"(attempt {attempt + 1}/4)"
                    )
                    self.success.emit()
                    return
                # _send_once_blocking 가 False 반환 — 일반 SMTP/네트워크 오류, retry 대상
                last_err = "SMTP/네트워크 오류"
            except smtplib.SMTPAuthenticationError as e:
                # 인증 오류는 재시도 의미 없음 — 즉시 종료 (큐 저장 X)
                self.error.emit(
                    f"認証失敗: ユーザー名またはパスワードが正しくありません。({e})"
                )
                return

        # 4 회 모두 실패 — 큐에 보존
        _enqueue_pending(self.subject, self.body)
        logger.error(f"Bug report 4 회 시도 모두 실패 — 큐 저장: {last_err}")
        self.error.emit(
            f"送信失敗 (4 回試行) — レポートをローカルに保存しました "
            f"(次回起動時に再送信): {last_err}"
        )
