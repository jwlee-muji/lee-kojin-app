"""アプリ全体で使用するマジックナンバー・定数を一元管理します。

各クラスはネームスペースとして機能し、直接インスタンス化は不要です。
  from app.core.constants import Timers, Animations, Layout, Cache, Notifications
"""


class Timers:
    """QTimer interval / singleShot 遅延定数 (ミリ秒)"""
    STARTUP_DELAY_MS        = 2250   # 起動時データ取得遅延 (UI 描画完了待ち)
    WEATHER_CYCLE_MS        = 3000   # 天気カード地域循環間隔
    SPOT_CYCLE_MS           = 3000   # JEPXスポット地域循環間隔
    LOG_PROCESS_INTERVAL_MS = 50     # ログバッファ処理間隔
    CHART_THROTTLE_MS       = 50     # チャート更新スロットル
    TOAST_VISIBLE_MS        = 3500   # トースト通知表示時間
    TRAY_MESSAGE_MS         = 4000   # トレイ通知表示時間
    NETWORK_TIMEOUT_MS      = 10_000 # ネットワークリクエストタイムアウト
    RATE_LIMIT_COOLDOWN_MS  = 60_000 # AI チャットレートリミット後クールダウン
    PREFETCH_DELAY_MS       = 5_000  # 起動後プリフェッチ開始遅延
    PREFETCH_INTERVAL_MS    = 400    # プリフェッチ間隔 (ウィジェット間)


class Animations:
    """アニメーション持続時間定数 (ミリ秒)"""
    THEME_FADE_MS           = 300    # テーマ切替オーバーレイフェード
    PAGE_FADE_MS            = 200    # ページ切替フェードイン
    WINDOW_SHOW_MS          = 500    # ウィンドウ表示フェード
    WINDOW_SLIDE_MS         = 800    # ウィンドウ位置スライド
    SKELETON_CYCLE_MS       = 800    # スケルトンローディング点滅
    VALUE_COUNT_UP_MS       = 1000   # ダッシュボードカード数値カウントアップ
    HOVER_MS                = 150    # ホバーエフェクト
    WEATHER_FADE_MS         = 300    # 天気カード切替フェード
    LOGIN_FADE_MS           = 400    # ログイン画面フェード
    STARTUP_ANIM_DELAY_MS   = 100    # 起動アニメーション開始遅延 (UI 描画安定待ち)


class Layout:
    """ウィンドウ・サイドバーレイアウト定数"""
    WINDOW_WIDTH_RATIO      = 0.78   # 画面幅に対するウィンドウ幅比率
    WINDOW_HEIGHT_RATIO     = 0.82   # 画面高さに対するウィンドウ高さ比率
    WINDOW_MIN_WIDTH        = 820    # ウィンドウ最小幅 (px)
    WINDOW_MIN_HEIGHT       = 560    # ウィンドウ最小高さ (px)
    WINDOW_ABSOLUTE_MIN_W   = 680    # ウィンドウ絶対最小幅 (px)
    WINDOW_ABSOLUTE_MIN_H   = 420    # ウィンドウ絶対最小高さ (px)
    SIDEBAR_WIDTH_RATIO     = 0.12   # 画面幅に対するサイドバー幅比率
    SIDEBAR_MIN_WIDTH       = 160    # サイドバー最小幅 (px)
    SIDEBAR_MAX_WIDTH       = 210    # サイドバー最大幅 (px)
    LOGIN_WINDOW_WIDTH      = 480    # ログインウィンドウ幅 (px)
    LOGIN_WINDOW_HEIGHT     = 580    # ログインウィンドウ高さ (px)


class Cache:
    """キャッシュ・バッファサイズ制限定数"""
    LOG_MAX_LINES           = 1000   # ログビューア最大保持行数
    LOG_CHUNK_SIZE          = 200    # 1回のバッファ処理最大行数
    LOG_MAX_READ_BYTES      = 512_000  # 初期ログ読込最大サイズ (500 KB)
    ICON_MAX_ENTRIES        = 200    # アイコンキャッシュ最大エントリ数


class Notifications:
    """通知センター定数"""
    DB_RETENTION_DAYS       = 30     # 通知DB自動削除期間 (日)


class AiChat:
    """AI チャット定数"""
    MAX_HISTORY_DEFAULT     = 20     # デフォルト履歴保持件数
