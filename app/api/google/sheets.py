"""
Google Sheets サービスアカウント経由でユーザー登録リストを管理します。

セットアップ手順:
  1. Google Cloud Console でサービスアカウントを作成
  2. Sheets API の読み書き権限を付与
  3. 認証 JSON をダウンロードして APP_DIR/service_account.json に配置
  4. 管理用スプレッドシートをサービスアカウントのメールと共有 (編集者)
  5. 設定画面の [Sheets ID] にスプレッドシート ID を入力
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

SHEET_NAME = "Users"


def _get_service():
    from app.core.config import SERVICE_ACCOUNT_FILE
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    if not SERVICE_ACCOUNT_FILE.exists():
        raise FileNotFoundError(
            f"サービスアカウントファイルが見つかりません: {SERVICE_ACCOUNT_FILE}\n"
            "service_account.json を APP_DIR に配置してください。"
        )
    creds = Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_FILE),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _normalize_sheet_id(value: str) -> str:
    """URL またはベア ID から Spreadsheet ID のみを取り出す。
    例: https://docs.google.com/spreadsheets/d/XXXX/edit... → XXXX"""
    import re
    value = value.strip()
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", value)
    return m.group(1) if m else value


def _get_sheet_id() -> str:
    from app.core.config import SHEETS_REGISTRY_ID
    raw = SHEETS_REGISTRY_ID.strip()
    return _normalize_sheet_id(raw) if raw != "ここにデフォルトのシートIDを記述" else ""


def get_registered_users() -> list[str]:
    """登録済みメールアドレス (小文字) のリストを返します。"""
    sheet_id = _get_sheet_id()
    if not sheet_id:
        return []
    svc = _get_service()
    result = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=f"{SHEET_NAME}!A:A")
        .execute()
    )
    values = result.get("values", [])
    return [row[0].strip().lower() for row in values if row and row[0].strip()]


def get_all_users() -> list[dict]:
    """全登録ユーザー {email, name, added} のリストを返します。"""
    sheet_id = _get_sheet_id()
    if not sheet_id:
        return []
    svc = _get_service()
    result = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=f"{SHEET_NAME}!A:C")
        .execute()
    )
    users = []
    for row in result.get("values", []):
        if not row or not row[0].strip():
            continue
        users.append({
            "email": row[0].strip(),
            "name":  row[1].strip() if len(row) > 1 else "",
            "added": row[2].strip() if len(row) > 2 else "",
        })
    return users


def add_user(email: str, display_name: str = "") -> bool:
    """ユーザーをシートに追加します。"""
    sheet_id = _get_sheet_id()
    if not sheet_id:
        return False
    svc = _get_service()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    svc.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"{SHEET_NAME}!A:C",
        valueInputOption="RAW",
        body={"values": [[email.lower().strip(), display_name.strip(), now]]},
    ).execute()
    logger.info(f"ユーザー追加: {email}")
    return True


def remove_user(email: str) -> bool:
    """指定メールの行をシートから削除します。"""
    sheet_id = _get_sheet_id()
    if not sheet_id:
        return False
    svc = _get_service()

    result = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=f"{SHEET_NAME}!A:A")
        .execute()
    )
    values = result.get("values", [])
    target = email.lower().strip()
    row_idx = next(
        (i for i, r in enumerate(values) if r and r[0].strip().lower() == target),
        None,
    )
    if row_idx is None:
        return False

    # シートの数値 ID を取得
    info = svc.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheet_num_id = next(
        s["properties"]["sheetId"]
        for s in info["sheets"]
        if s["properties"]["title"] == SHEET_NAME
    )
    svc.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{
            "deleteDimension": {
                "range": {
                    "sheetId":    sheet_num_id,
                    "dimension":  "ROWS",
                    "startIndex": row_idx,
                    "endIndex":   row_idx + 1,
                }
            }
        }]},
    ).execute()
    logger.info(f"ユーザー削除: {email}")
    return True
