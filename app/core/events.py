from typing import NamedTuple
from PySide6.QtCore import QObject, Signal


class WeatherSummaryEntry(NamedTuple):
    """weather_updated シグナルのペイロード型。地域ごとの当日天気サマリー。"""
    region:       str   # 地域名 (翻訳済み)
    weather_text: str   # 天気テキスト (例: "晴れ")
    temp_str:     str   # 気温文字列 (例: "28℃ / 18℃")
    accent_color: str   # WMO テーマカラー (例: "#FF9800")
    wmo_code:     int = 0  # WMO 天気コード (背景演出用)


class GlobalEventBus(QObject):
    """컴포넌트 간 결합도를 낮추기 위한 전역 이벤트 버스 (Pub/Sub)"""

    # ── データ更新通知 ────────────────────────────────────────────────────────
    # occto_updated:     (time_str: str, area_str: str, min_reserve: float)
    occto_updated     = Signal(str, str, float)
    imbalance_updated = Signal()
    jkm_updated       = Signal()
    hjks_updated      = Signal()
    # weather_updated:  list[WeatherSummaryEntry]
    weather_updated   = Signal(list)

    # ── アプリ制御 ────────────────────────────────────────────────────────────
    settings_saved  = Signal()
    page_requested  = Signal(int)   # page_index
    app_quitting    = Signal()      # 全ワーカースレッドへの安全終了通知

    # ── Google 連携 ──────────────────────────────────────────────────────────
    google_auth_changed = Signal(bool)       # 認証状態変化 (True=認証済, False=未認証)
    gmail_new_mail      = Signal(str, int)   # (label_name, unread_count)
    calendar_updated    = Signal(list)       # イベントリスト更新

    # ── 認証・セッション ──────────────────────────────────────────────────────
    user_authenticated  = Signal(str)        # ログイン成功 (email)
    user_logged_out     = Signal()           # ログアウト


bus = GlobalEventBus()