import os
import sys
import json
import ctypes
import base64
import logging
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
    失敗時は平文のまま返す (暗号化なし・ログに警告記録)。"""
    if not value:
        return value
    try:
        encrypted = _dpapi_protect(value.encode("utf-8"))
        return _DPAPI_PREFIX + base64.b64encode(encrypted).decode("ascii")
    except Exception as e:
        _cfg_logger.warning(f"シークレット暗号化に失敗しました (平文保存): {e}")
        return value


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

# --- 기본 경로 설정 ---
APP_NAME = 'LEE電力モニター'
APP_DIR  = Path(os.environ.get('APPDATA', Path.home())) / APP_NAME

# PyInstaller frozen 환경과 개발 환경 모두에서 프로젝트 루트를 안전하게 반환
BASE_DIR: Path = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).parent.parent.parent
APP_DIR.mkdir(parents=True, exist_ok=True)

from version import __version__  # noqa: E402 — アプリバージョンをここで一元管理

LOG_FILE     = APP_DIR / 'app.log'
INSTALL_FILE = APP_DIR / 'install_path.txt'
SETTINGS_FILE = APP_DIR / 'settings.json'

# --- 데이터베이스 파일 경로 ---
DB_IMBALANCE = APP_DIR / 'imbalance_data.db'
DB_HJKS      = APP_DIR / 'hjks_data.db'
DB_JKM       = APP_DIR / 'jkm_data.db'

BACKUP_DIR   = APP_DIR / 'backups'
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# --- 외부 API 엔드포인트 (API Endpoints) ---
API_IMBALANCE_BASE = "https://www.imbalanceprices-cs.jp"
API_OCCTO_RESERVE  = "https://web-kohyo.occto.or.jp/kks-web-public/home/dailyData"
API_OPEN_METEO     = "https://api.open-meteo.com/v1/forecast"
API_HJKS_MAIN      = "https://hjks.jepx.or.jp/hjks/unit_status"
API_HJKS_AJAX      = "https://hjks.jepx.or.jp/hjks/unit_status_ajax"

# --- 위젯별 설정 (Constants) ---
JKM_TICKER = 'JKM=F'

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

# --- 인밸런스 CSV 컬럼 인덱스 (Imbalance column indices) ---
DATE_COL_IDX         = 1
TIME_COL_IDX         = 3
YOJO_START_COL_IDX   = 5
YOJO_END_COL_IDX     = 21
FUSOKU_START_COL_IDX = 23

# --- 설정 관리 (Settings) ---
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


def load_settings() -> dict:
    """設定ファイルを読み込んで返す。2回目以降はメモリキャッシュを返す。"""
    global _settings_cache
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
    to_save = dict(settings)
    for key in _SENSITIVE_KEYS:
        if key not in to_save:
            continue
        val = to_save[key]
        if key == "user_gemini_keys":
            to_save[key] = [encrypt_secret(k) for k in val if isinstance(k, str)]
        elif isinstance(val, str):
            to_save[key] = encrypt_secret(val)
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(to_save, f, indent=4)
    _settings_cache = dict(settings)  # 平文をキャッシュ (次回 load_settings がファイルを再読しない)


def invalidate_settings_cache() -> None:
    """キャッシュを破棄して次回 load_settings でファイルを再読みさせる。"""
    global _settings_cache
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