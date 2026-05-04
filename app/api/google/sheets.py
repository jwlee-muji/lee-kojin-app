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
ACCESS_REQUEST_SHEET = "AccessRequests"

# AccessRequests 시트 컬럼 (header 자동 생성):
#   A: request_id  (예: 20260504-153022-user_example.com)
#   B: email
#   C: message
#   D: app_version
#   E: requested_at  (YYYY-MM-DD HH:MM:SS)
#   F: status        (open / wip / fixed / deleted)
_ACCESS_REQUEST_HEADERS = [
    "request_id", "email", "message", "app_version", "requested_at", "status",
]


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


def _ensure_access_request_sheet(svc, sheet_id: str) -> None:
    """AccessRequests 시트가 없으면 생성하고 헤더 행 기록.

    어드민 측 별도 셋업 없이 첫 신청에서 자동 초기화 → 운영 편의성.
    """
    info = svc.spreadsheets().get(spreadsheetId=sheet_id).execute()
    titles = [s["properties"]["title"] for s in info.get("sheets", [])]
    if ACCESS_REQUEST_SHEET in titles:
        return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{
            "addSheet": {"properties": {"title": ACCESS_REQUEST_SHEET}}
        }]},
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"{ACCESS_REQUEST_SHEET}!A1:F1",
        valueInputOption="RAW",
        body={"values": [_ACCESS_REQUEST_HEADERS]},
    ).execute()
    logger.info(f"AccessRequests シート初期化: {sheet_id}")


def submit_access_request(email: str, message: str, app_version: str = "") -> str:
    """アクセス申請を AccessRequests シートに追加。request_id を返す。"""
    sheet_id = _get_sheet_id()
    if not sheet_id:
        raise RuntimeError("Sheets ID 未設定 — 設定画面で登録してください。")
    svc = _get_service()
    _ensure_access_request_sheet(svc, sheet_id)

    now = datetime.now()
    safe_local = email.split("@")[0][:20].replace(".", "_")
    request_id = f"{now.strftime('%Y%m%d-%H%M%S')}-{safe_local}"
    row = [
        request_id,
        email.lower().strip(),
        message.strip(),
        app_version,
        now.strftime("%Y-%m-%d %H:%M:%S"),
        "open",
    ]
    svc.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"{ACCESS_REQUEST_SHEET}!A:F",
        valueInputOption="RAW",
        body={"values": [row]},
    ).execute()
    logger.info(f"アクセス申請追加: {email} ({request_id})")
    return request_id


def get_access_requests(include_deleted: bool = False) -> list[dict]:
    """全アクセス申請を取得 (header 行除外)。"""
    sheet_id = _get_sheet_id()
    if not sheet_id:
        return []
    svc = _get_service()
    try:
        result = (
            svc.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range=f"{ACCESS_REQUEST_SHEET}!A2:F")
            .execute()
        )
    except Exception as e:
        # 시트 미생성 / 권한 등 → 빈 결과로 graceful
        logger.warning(f"AccessRequests 取得失敗: {e}")
        return []

    out = []
    for r in result.get("values", []):
        if not r or not r[0].strip():
            continue
        status = r[5].strip() if len(r) > 5 else "open"
        if not include_deleted and status == "deleted":
            continue
        out.append({
            "request_id":   r[0].strip(),
            "email":        r[1].strip() if len(r) > 1 else "",
            "message":      r[2].strip() if len(r) > 2 else "",
            "app_version":  r[3].strip() if len(r) > 3 else "",
            "requested_at": r[4].strip() if len(r) > 4 else "",
            "status":       status or "open",
        })
    return out


def update_access_request_status(request_id: str, status: str) -> bool:
    """指定 request_id の status 列 (F) を更新。"""
    sheet_id = _get_sheet_id()
    if not sheet_id:
        return False
    svc = _get_service()
    result = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=f"{ACCESS_REQUEST_SHEET}!A:A")
        .execute()
    )
    rows = result.get("values", [])
    target = request_id.strip()
    row_idx = next(
        (i for i, r in enumerate(rows) if r and r[0].strip() == target),
        None,
    )
    if row_idx is None:
        return False
    # F 열 (status) 업데이트 — sheets 1-based row index
    svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"{ACCESS_REQUEST_SHEET}!F{row_idx + 1}",
        valueInputOption="RAW",
        body={"values": [[status]]},
    ).execute()
    logger.info(f"アクセス申請 status 更新: {request_id} → {status}")
    return True


def delete_access_request(request_id: str) -> bool:
    """論理削除 — status='deleted' に設定 (実際の行は保持)."""
    return update_access_request_status(request_id, "deleted")


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
