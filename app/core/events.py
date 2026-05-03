from typing import NamedTuple
from PySide6.QtCore import QObject, Signal


class WeatherSummaryEntry(NamedTuple):
    """weather_updated シグナルのペイロード型。地域ごとの当日天気サマリー."""
    region:       str   # 地域名 (翻訳済み)
    weather_text: str   # 天気テキスト (例: "晴れ")
    temp_str:     str   # 最高/最低 文字列 (例: "28℃ / 18℃")
    accent_color: str   # WMO テーマカラー (例: "#FF9800")
    wmo_code:     int   = 0      # WMO 天気コード (背景演出용)
    current_temp:  float | None = None   # 現在気温 ℃
    apparent_temp: float | None = None   # 体感温度 ℃
    humidity:      int   | None = None   # 相対湿度 %
    wind_speed:    float | None = None   # 風速 km/h
    temp_max:      float | None = None   # 当日 最高 ℃
    temp_min:      float | None = None   # 当日 最低 ℃


class GlobalEventBus(QObject):
    """컴포넌트 간 결합도를 낮추기 위한 전역 이벤트 버스 (Pub/Sub)"""

    # ── データ更新通知 ────────────────────────────────────────────────────────
    # occto_updated:     (time_str: str, area_str: str, min_reserve: float)
    occto_updated     = Signal(str, str, float)
    # occto_baseline:    (today_min: float, yesterday_min: float)
    # NaN を渡すと「不明」を意味し、Card 側で delta 表示をクリアする。
    occto_baseline    = Signal(float, float)
    # occto_areas:       全エリアの統計 [{area, min, max, avg, cur, status}, ...]
    # ReserveCard が 5 行の比較バーを描画するために使用。
    occto_areas       = Signal(list)
    imbalance_updated = Signal()
    jkm_updated       = Signal()
    jepx_spot_updated = Signal()
    hjks_updated      = Signal()
    # hjks_card_result: rich payload dict (latest, total_op_mw, total_st_mw, methods[], sparkline)
    hjks_card_result  = Signal(dict)
    # briefing_generated(period: str) — BriefingWidget 가 새 브리핑 저장 직후 emit
    briefing_generated = Signal(str)
    # notifications_changed — 알림 추가/읽음/삭제 시 dashboard / sidebar 갱신
    notifications_changed = Signal()
    # app_ready — MainWindow 가 처음 화면에 표시된 직후 emit
    # 위젯 자동 fetch 는 이 시그널 후에 시작하도록 게이팅 가능
    app_ready = Signal()
    # ai_chat_changed — AI 채팅 세션/메시지 변경 시 emit (대시보드 카드 동기화용)
    ai_chat_changed = Signal()
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

    # ── UI 通知 ───────────────────────────────────────────────────────────────
    # toast_requested: (message: str, level: str)  level = "info"|"success"|"warning"|"error"
    toast_requested     = Signal(str, str)

    # ── 周期タイマー (P1-8 — refresh storm 抑制用マスター timer) ─────────────
    # MainWindow 가 60 초마다 emit. 위젯들이 1 분 주기 polling 을 직접 만드는
    # 대신 이 시그널을 구독. (현재는 인프라만 — 위젯별 마이그레이션 점진)
    tick_minute = Signal()


bus = GlobalEventBus()