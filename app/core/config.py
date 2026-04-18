import os
import sys
import json
import ctypes
import base64
import logging
import threading
from pathlib import Path

_cfg_logger = logging.getLogger(__name__)

# ── Windows DPAPI によるシークレット暗号化 ────────────────────────────────
# ユーザーアカウントの資格情報で暗号化するため、同一ユーザーのみ復号可能。
# OS 再インストール (プロファイル移行なし) の場合は復号不可になるため、
# 復号失敗時は空文字にフォールバックし、ユーザーに再入力を促す。

class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _dpapi_protect(data: bytes) -> bytes:
    buf = (ctypes.c_ubyte * len(data))(*data)
    blob_in  = _DataBlob(len(data), buf)
    blob_out = _DataBlob()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise OSError(f"CryptProtectData 失敗 (err={ctypes.GetLastError()})")
    try:
        return bytes(blob_out.pbData[:blob_out.cbData])
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    buf = (ctypes.c_ubyte * len(data))(*data)
    blob_in  = _DataBlob(len(data), buf)
    blob_out = _DataBlob()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise OSError(f"CryptUnprotectData 失敗 (err={ctypes.GetLastError()})")
    try:
        return bytes(blob_out.pbData[:blob_out.cbData])
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


_DPAPI_PREFIX = "__dpapi__:"


def encrypt_secret(value: str) -> str:
    """文字列を DPAPI で暗号化し '__dpapi__:<base64>' 形式の文字列を返す。
    失敗時は空文字を返す (平文保存を避けるため)。呼び出し元は空文字を「保存しない」として扱うこと。"""
    if not value:
        return value
    try:
        encrypted = _dpapi_protect(value.encode("utf-8"))
        return _DPAPI_PREFIX + base64.b64encode(encrypted).decode("ascii")
    except Exception as e:
        _cfg_logger.warning(f"シークレット暗号化に失敗しました (値は保存されません。再入力が必要です): {e}")
        return ""


def decrypt_secret(value: str) -> str:
    """'__dpapi__:<base64>' 形式の文字列を復号して返す。
    非暗号化文字列はそのまま返す。復号失敗時は空文字を返す。"""
    if not isinstance(value, str) or not value.startswith(_DPAPI_PREFIX):
        return value  # 未暗号化: そのまま返す (初回移行時など)
    try:
        encrypted = base64.b64decode(value[len(_DPAPI_PREFIX):])
        return _dpapi_unprotect(encrypted).decode("utf-8")
    except Exception as e:
        _cfg_logger.warning(f"シークレット復号に失敗しました (空文字返却): {e}")
        return ""


# 暗号化対象の設定キー
_SENSITIVE_KEYS: frozenset[str] = frozenset({
    "user_gemini_keys",
    "user_groq_key",
    "user_smtp_password",
})

# ── パス設定 ─────────────────────────────────────────────────────────────────
ADMIN_EMAIL = "jw.lee@shirokumapower.com"

# ── セッション中のログインメール (ファイル I/O を介さないインメモリ管理) ─────
_session_email: str = ""


def set_session_email(email: str) -> None:
    global _session_email
    _session_email = email.strip().lower()


def get_session_email() -> str:
    return _session_email

APP_NAME = 'LEE電力モニター'
APP_DIR  = Path(os.environ.get('APPDATA', Path.home())) / APP_NAME

# PyInstaller frozen 환경과 개발 환경 모두에서 프로젝트 루트를 안전하게 반환
BASE_DIR: Path = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).parent.parent.parent
APP_DIR.mkdir(parents=True, exist_ok=True)

from version import __version__  # noqa: E402 — アプリバージョンをここで一元管理

LOG_FILE             = APP_DIR / 'app.log'
INSTALL_FILE         = APP_DIR / 'install_path.txt'
SETTINGS_FILE        = APP_DIR / 'settings.json'
GOOGLE_TOKEN_FILE    = APP_DIR / 'google_token.json'
SERVICE_ACCOUNT_FILE = APP_DIR / 'service_account.json'
USER_EMAIL_FILE      = APP_DIR / 'current_user.json'

# ── データベースファイルパス ──────────────────────────────────────────────────
DB_IMBALANCE  = APP_DIR / 'imbalance_data.db'
DB_HJKS       = APP_DIR / 'hjks_data.db'
DB_JKM        = APP_DIR / 'jkm_data.db'
DB_JEPX_SPOT  = APP_DIR / 'jepx_spot.db'

BACKUP_DIR   = APP_DIR / 'backups'
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# ── 外部 API エンドポイント ────────────────────────────────────────────────────
API_IMBALANCE_BASE  = "https://www.imbalanceprices-cs.jp"
API_OCCTO_RESERVE   = "https://web-kohyo.occto.or.jp/kks-web-public/home/dailyData"
API_OPEN_METEO      = "https://api.open-meteo.com/v1/forecast"
API_HJKS_MAIN       = "https://hjks.jepx.or.jp/hjks/unit_status"
API_HJKS_AJAX       = "https://hjks.jepx.or.jp/hjks/unit_status_ajax"
API_JEPX_SPOT_BASE  = "https://www.jepx.jp/market/excel"

# ── ウィジェット定数 ──────────────────────────────────────────────────────────
JKM_TICKER = 'JKM=F'

JEPX_SPOT_START_FY = 2005   # 収集開始会計年度
JEPX_SPOT_AREAS = [          # (表示名, DBカラム名)
    ("システム",  "system_price"),
    ("北海道",    "hokkaido"),
    ("東北",      "tohoku"),
    ("東京",      "tokyo"),
    ("中部",      "chubu"),
    ("北陸",      "hokuriku"),
    ("関西",      "kansai"),
    ("中国",      "chugoku"),
    ("四国",      "shikoku"),
    ("九州",      "kyushu"),
]

WEATHER_REGIONS = [
    {"name": "北海道 (札幌)", "lat": 43.0642, "lon": 141.3469},
    {"name": "東北 (仙台)",   "lat": 38.2682, "lon": 140.8694},
    {"name": "東京",          "lat": 35.6895, "lon": 139.6917},
    {"name": "中部 (名古屋)", "lat": 35.1815, "lon": 136.9064},
    {"name": "北陸 (新潟)",   "lat": 37.9161, "lon": 139.0364},
    {"name": "関西 (大阪)",   "lat": 34.6937, "lon": 135.5023},
    {"name": "中国 (広島)",   "lat": 34.3853, "lon": 132.4553},
    {"name": "四国 (高松)",   "lat": 34.3401, "lon": 134.0434},
    {"name": "九州 (福岡)",   "lat": 33.5902, "lon": 130.4017},
]

HJKS_REGIONS = ["北海道", "東北", "東京", "中部", "北陸", "関西", "中国", "四国", "九州", "沖縄"]
HJKS_METHODS = ["火力（石炭）", "火力（ガス）", "火力（石油）", "原子力", "水力", "その他"]
HJKS_COLORS = {
    "火力（石炭）": "#795548", "火力（ガス）": "#EF5350", "火力（石油）": "#FF9800",
    "原子力": "#9C27B0",       "水力": "#42A5F5",         "その他": "#9E9E9E"
}

IMBALANCE_COLORS = [
    '#2196F3', '#F44336', '#4CAF50', '#FF9800', '#9C27B0',
    '#00BCD4', '#FF5722', '#8BC34A', '#FFC107', '#3F51B5',
    '#E91E63', '#009688', '#96CEB4', '#673AB7', '#795548',
    '#607D8B', '#FF6B6B', '#4ECDC4', '#45B7D1', '#CDDC39',
]

# ── インバランス CSV カラムインデックス ───────────────────────────────────────
DATE_COL_IDX         = 1
TIME_COL_IDX         = 3
YOJO_START_COL_IDX   = 5
YOJO_END_COL_IDX     = 21
FUSOKU_START_COL_IDX = 23

# ── 設定管理 ──────────────────────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    "imbalance_alert": 40.0,
    "reserve_low": 8.0,
    "reserve_warn": 10.0,
    "imbalance_interval": 5,
    "reserve_interval": 5,
    "weather_interval": 60,
    "hjks_interval": 180,
    "jkm_interval": 180,
    "retention_days": 1460,
    "auto_start": False,
    "language": "auto",
    "gemini_model": "gemini-2.5-flash",
    "ai_temperature": 0.7,
    "ai_max_tokens": 2048,
    "chat_history_limit": 20,
    # ユーザーが設定画面で登録した独自 API キー (空文字はスキップ)
    "user_gemini_keys": [],
    "user_groq_key": "",
    "user_smtp_user": "",
    "user_smtp_password": "",
    # Google カレンダー設定
    "calendar_poll_interval": 5,
    "calendar_enabled_ids": [],
    # Gmail 設定
    "gmail_poll_interval": 5,
    "gmail_alarm_labels": ["INBOX"],
    "gmail_max_results": 50,
    # ユーザー登録 Google Sheets ID
    "sheets_registry_id": "",
}

def _validate_settings(settings: dict) -> dict:
    """設定値の型と範囲を検証し、不正な値はデフォルトにリセットします。"""
    validated = dict(settings)

    _float_ranges = {
        "imbalance_alert": (0.0, 1000.0),
        "reserve_low":     (0.0, 100.0),
        "reserve_warn":    (0.0, 100.0),
        "ai_temperature":  (0.0, 2.0),
    }
    for key, (lo, hi) in _float_ranges.items():
        try:
            v = float(validated.get(key, DEFAULT_SETTINGS[key]))
            validated[key] = max(lo, min(hi, v))
        except (ValueError, TypeError):
            validated[key] = DEFAULT_SETTINGS[key]

    _int_ranges = {
        "imbalance_interval":  (1, 1440),
        "reserve_interval":    (1, 1440),
        "weather_interval":    (1, 1440),
        "hjks_interval":       (1, 1440),
        "jkm_interval":        (1, 1440),
        "retention_days":      (1, 36500),
        "ai_max_tokens":       (128, 8192),
        "chat_history_limit":  (1, 200),
        "calendar_poll_interval": (1, 1440),
        "gmail_poll_interval":    (1, 1440),
        "gmail_max_results":      (10, 500),
    }
    for key, (lo, hi) in _int_ranges.items():
        try:
            v = int(validated.get(key, DEFAULT_SETTINGS[key]))
            validated[key] = max(lo, min(hi, v))
        except (ValueError, TypeError):
            validated[key] = DEFAULT_SETTINGS[key]

    if not isinstance(validated.get("auto_start"), bool):
        validated["auto_start"] = DEFAULT_SETTINGS["auto_start"]

    if validated.get("language") not in ('auto', 'ja', 'en', 'ko', 'zh'):
        validated["language"] = DEFAULT_SETTINGS["language"]

    return validated


_settings_cache: dict | None = None
_settings_lock = threading.Lock()   # _settings_cache 동시 접근 보호


def load_settings() -> dict:
    """設定ファイルを読み込んで返す。2回目以降はメモリキャッシュを返す。"""
    global _settings_cache
    with _settings_lock:
        if _settings_cache is not None:
            return _settings_cache

        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for key in _SENSITIVE_KEYS:
                    if key not in data:
                        continue
                    val = data[key]
                    if key == "user_gemini_keys":
                        data[key] = [decrypt_secret(k) for k in val if isinstance(k, str)]
                    elif isinstance(val, str):
                        data[key] = decrypt_secret(val)
                _settings_cache = _validate_settings({**DEFAULT_SETTINGS, **data})
                return _settings_cache
            except (json.JSONDecodeError, OSError, ValueError) as e:
                _cfg_logger.warning(f"設定ファイルの読み込みに失敗しました。デフォルト設定を使用します: {e}")

        _settings_cache = DEFAULT_SETTINGS.copy()
        return _settings_cache


def save_settings(settings: dict) -> None:
    """設定を保存し、キャッシュを新しい値で更新する。"""
    global _settings_cache

    # 暗号化失敗時のフォールバック用に既存ファイルの暗号化済み値を読んでおく
    existing_raw: dict = {}
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            existing_raw = json.load(f)
    except Exception:
        pass

    to_save = dict(settings)
    for key in _SENSITIVE_KEYS:
        if key not in to_save:
            continue
        val = to_save[key]
        if key == "user_gemini_keys":
            # 暗号化失敗したキー (空文字) はリストから除外して平文保存を防ぐ
            to_save[key] = [enc for k in val if isinstance(k, str) and k
                            for enc in [encrypt_secret(k)] if enc]
        elif isinstance(val, str):
            enc = encrypt_secret(val)
            if enc:
                to_save[key] = enc
            elif existing_raw.get(key):
                # 暗号化失敗 — 既存の暗号化済み値をそのまま維持してユーザーキーの消失を防ぐ
                to_save[key] = existing_raw[key]
            else:
                to_save.pop(key, None)

    # ファイル書き込みとキャッシュ更新を同一ロック内で行い競合状態を防ぐ
    with _settings_lock:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(to_save, f, indent=4)
        _settings_cache = dict(settings)  # 平文をキャッシュ (次回 load_settings がファイルを再読しない)


def invalidate_settings_cache() -> None:
    """キャッシュを破棄して次回 load_settings でファイルを再読みさせる。"""
    global _settings_cache
    with _settings_lock:
        _settings_cache = None

def get_theme_qss(theme_name: str) -> str:
    """분리된 .qss 파일에서 테마 데이터를 읽어옵니다."""
    import sys
    if getattr(sys, 'frozen', False):
        base_dir = Path(sys._MEIPASS) / "app"
    else:
        base_dir = Path(__file__).parent.parent
        
    qss_file = base_dir / "ui" / "themes" / f"{theme_name}.qss"
        
    try:
        return qss_file.read_text(encoding='utf-8')
    except OSError as e:
        print(f"Theme load error: {e}")
        return ""