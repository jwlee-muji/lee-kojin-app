"""
Google OAuth 2.0 Desktop App 인증 모듈
- Client ID / Secret은 앱에 내장 (Desktop App 仕様上 Secret は非機密)
- 토큰은 APP_DIR/google_token.json에 DPAPI 암호화하여 저장, 자동 갱신 포함
- run_oauth_flow()는 반드시 메인 스레드에서 호출 (브라우저 열기)
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Desktop App OAuth 2.0 認証情報
# Google の公式仕様上、インストール型アプリ (installed application) の Client Secret は
# 非機密 (non-sensitive) として扱われます。ソースコードへの埋め込みは推奨パターンです。
# 参照: https://developers.google.com/identity/protocols/oauth2/native-app
_CLIENT_ID     = "432665692180-8cnsam537cbe9pfl5spk77kocb2rjue6.apps.googleusercontent.com"
_CLIENT_SECRET = "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"


def _mask_secrets(msg: str) -> str:
    """ログ出力前に Client ID / Secret を *** でマスクします。"""
    for secret in (_CLIENT_ID, _CLIENT_SECRET):
        msg = msg.replace(secret, "***")
    return msg

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
]


def _token_path() -> Path:
    from app.core.config import APP_DIR
    return APP_DIR / "google_token.json"


def _save_token(creds) -> bool:
    """トークン JSON を DPAPI 暗号化してファイルに保存します。
    暗号化に失敗した場合は保存を行わず False を返します。"""
    from app.core.config import encrypt_secret
    token_json = creds.to_json()
    encrypted = encrypt_secret(token_json)
    if not encrypted:
        logger.error("Google トークンの暗号化に失敗しました。トークンは保存されません。再認証が必要です。")
        return False
    _token_path().write_text(encrypted, encoding="utf-8")
    return True


def _load_token_json() -> str | None:
    """トークンファイルを読み込み、JSON 文字列を返します。
    DPAPI 暗号化済みの場合は復号し、旧フォーマット (平文) はそのまま返します。
    復号に失敗した場合は None を返します (再認証が必要)。"""
    from app.core.config import decrypt_secret, _DPAPI_PREFIX
    path = _token_path()
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    if raw.startswith(_DPAPI_PREFIX):
        decrypted = decrypt_secret(raw)
        if not decrypted:
            logger.warning("Google トークンの復号に失敗しました。再認証が必要です。")
            return None
        return decrypted
    # 旧フォーマット (平文 JSON): そのまま返し、次回保存時に暗号化される
    logger.debug("Google トークンが旧フォーマット (平文) で検出されました。次回保存時に暗号化します。")
    return raw


def get_credentials():
    """
    저장된 토큰 로드 → 만료 시 자동 갱신 → 없으면 None 반환.
    google.auth.exceptions.RefreshError 발생 시 토큰 삭제 후 None 반환.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        token_json = _load_token_json()
        if token_json is None:
            return None

        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                _save_token(creds)   # 갱신된 토큰을 DPAPI 암호화하여 재저장
            else:
                return None

        return creds if creds.valid else None

    except Exception as e:
        logger.warning(f"Google credentials load/refresh failed: {e}")
        try:
            _token_path().unlink(missing_ok=True)
        except OSError:
            pass
        return None


def run_oauth_flow() -> bool:
    """
    InstalledAppFlow로 브라우저 기반 OAuth 인증.
    성공 시 토큰 저장 + bus.google_auth_changed.emit(True).
    반드시 메인 스레드에서 호출.
    """
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from app.core.events import bus

        client_config = {
            "installed": {
                "client_id":      _CLIENT_ID,
                "client_secret":  _CLIENT_SECRET,
                "auth_uri":       "https://accounts.google.com/o/oauth2/auth",
                "token_uri":      "https://oauth2.googleapis.com/token",
                "redirect_uris":  ["http://localhost"],
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        # port=0 → OS がランダムポートを割り当て。127.0.0.1 にのみバインドされ、
        # 外部ネットワークからはアクセス不可 (google_auth_oauthlib の仕様)。
        creds = flow.run_local_server(port=0)

        if not _save_token(creds):
            return False
        logger.info("Google OAuth 인증 성공, 토큰 저장 완료")
        bus.google_auth_changed.emit(True)
        return True

    except Exception as e:
        logger.error(f"Google OAuth flow error: {_mask_secrets(str(e))}", exc_info=True)
        return False


def revoke_credentials() -> None:
    """토큰 파일 삭제(로그아웃) + bus 알림."""
    from app.core.events import bus
    try:
        _token_path().unlink(missing_ok=True)
    except OSError:
        pass
    bus.google_auth_changed.emit(False)
    logger.info("Google 연동 해제 완료")


def is_authenticated() -> bool:
    """유효한 크레덴셜이 있으면 True. 빠른 확인 전용."""
    return get_credentials() is not None


def build_service(api_name: str, version: str):
    """
    googleapiclient.discovery.build() 래퍼.
    크레덴셜 없으면 RuntimeError 발생.
    """
    from googleapiclient.discovery import build
    creds = get_credentials()
    if creds is None:
        raise RuntimeError("Google 認証が必要です。設定画面から認証してください。")
    # cache_discovery=False: oauth2client<4.0.0 以外では file_cache 非対応のため抑制
    return build(api_name, version, credentials=creds, cache_discovery=False)
