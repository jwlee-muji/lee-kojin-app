"""ユーザー登録確認 (Google Sheets 経由)。管理者は常に通過。"""
import logging

logger = logging.getLogger(__name__)


class RegistryCheckError(Exception):
    """シート接続や認証ファイルに起因する確認エラー。"""


def is_user_registered(email: str) -> bool:
    """
    メールアドレスが登録済みかどうかを確認します。

    - 管理者メール (ADMIN_EMAIL) は常に True。
    - sheets_registry_id 未設定の場合は管理者のみ許可。
    - Sheets 接続失敗時は RegistryCheckError を送出します。
      (呼び出し元で未登録と区別して処理してください)
    """
    from app.core.config import ADMIN_EMAIL, load_settings

    email = email.lower().strip()
    if email == ADMIN_EMAIL.lower():
        return True

    sheet_id = load_settings().get("sheets_registry_id", "").strip()
    if not sheet_id:
        logger.warning("sheets_registry_id が未設定です。管理者のみアクセス可能。")
        raise RegistryCheckError("sheets_registry_id が設定されていません。")

    try:
        from app.api.google.sheets import get_registered_users
        registered = get_registered_users()
        return email in registered
    except RegistryCheckError:
        raise
    except FileNotFoundError as e:
        logger.error(f"サービスアカウントファイルが見つかりません: {e}")
        raise RegistryCheckError(f"認証ファイルが見つかりません: {e}") from e
    except Exception as e:
        logger.error(f"ユーザー登録確認エラー: {e}")
        raise RegistryCheckError(str(e)) from e
