"""
多言語対応 (i18n) モジュール
日本語をデフォルトとし、英語・韓国語・中国語に対応。
"""
import logging

logger = logging.getLogger(__name__)

class _I18nState:
    """言語設定を安全に保持するカプセル化クラス。
    直接の属性アクセスによる不正な状態変更を防ぎ、
    必ず set_language() を経由させることでバリデーションを保証します。"""
    __slots__ = ('_lang',)
    _VALID: frozenset = frozenset(('ja', 'en', 'ko', 'zh'))

    def __init__(self) -> None:
        self._lang: str = 'ja'

    @property
    def lang(self) -> str:
        return self._lang

    @lang.setter
    def lang(self, value: str) -> None:
        self._lang = value if value in self._VALID else 'ja'


_state = _I18nState()

# 言語選択肢: (表示名, 言語コード)  ← ネイティブ表記で固定 (言語ピッカーなので翻訳しない)
LANG_OPTIONS: list[tuple[str, str]] = [
    ('自動 (Auto)',  'auto'),
    ('日本語',       'ja'),
    ('English',      'en'),
    ('한국어',        'ko'),
    ('中文',          'zh'),
]
_LANG_CODE_TO_IDX = {code: i for i, (_, code) in enumerate(LANG_OPTIONS)}

# キー: 日本語テキスト、値: 各言語の翻訳辞書
TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── 英語 ──────────────────────────────────────────────────────────────
    'en': {
        # Navigation tabs
        'ダッシュボード':       'Dashboard',
        '電力予備率':           'Power Reserve',
        'インバランス':         'Imbalance',
        'JKM LNG 価格':        'JKM LNG Price',
        '全国天気':             'National Weather',
        '発電稼働状況':         'Generation Status',
        '通知センター':         'Notifications',
        '通知センター ({0})':  'Notifications ({0})',
        '設定':                 'Settings',
        'システムログ':         'System Log',
        # Navigation groups / short labels
        '⚡  電力データ':       '⚡  Power Data',
        '🔵  Google':           '🔵  Google',
        '🛠  ツール':           '🛠  Tools',
        'バグ':                 'Bug',
        'ログ':                 'Log',
        # New widget tabs (feature 2,3,4)
        'バグレポート':         'Bug Report',
        'AI チャット':          'AI Chat',
        'テキストメモ':         'Text Memo',
        # Network / theme
        '🟢 オンライン':        '🟢 Online',
        '🔴 オフライン':        '🔴 Offline',
        '☀️ ライトモード':      '☀️ Light Mode',
        '🌙 ダークモード':      '🌙 Dark Mode',
        # Tray / dialogs
        '開く (Open)':          'Open',
        '完全に終了 (Quit)':    'Quit',
        'LEE電力モニター':      'LEE Power Monitor',
        'LEE電力モニター - バックグラウンド実行中':
            'LEE Power Monitor - Running in Background',
        '終了の確認':           'Confirm Exit',
        'アプリケーションを完全に終了しますか？\nそれともトレイ（バックグラウンド）に最小化しますか？':
            'Quit the application completely?\nOr minimize to system tray (background)?',
        'トレイに最小化':       'Minimize to Tray',
        '完全に終了':           'Quit',
        'キャンセル':           'Cancel',
        'バックグラウンドで実行中です。\nアイコンをダブルクリックで開きます。':
            'Running in background.\nDouble-click the tray icon to open.',
        'ネットワーク接続が切断されました。自動更新を一時停止します。':
            'Network connection lost. Auto-update paused.',
        # Settings - group headers
        '⚙️ 設定 (Settings)':              '⚙️ Settings',
        '⚠️ アラートしきい値設定':           '⚠️ Alert Threshold Settings',
        '⏱️ 自動更新間隔 (分)':             '⏱️ Auto Update Interval (min)',
        '💾 データ寿命管理 (バックアップと削除)': '💾 Data Lifecycle (Backup & Delete)',
        '💻 システム設定':                   '💻 System Settings',
        '🌍 言語設定 (Language)':           '🌍 Language Settings',
        # Settings - group header (inline keys used in _make_group calls)
        'アラートしきい値':                 'Alert Threshold',
        '自動更新間隔':                     'Auto Update Interval',
        'データ管理':                       'Data Management',
        'システム':                         'System',
        '言語 (Language)':                  'Language',
        # Settings - form labels
        'インバランス単価 警告:':    'Imbalance Price Alert:',
        '電力予備率 警告 (赤):':     'Reserve Rate Alert (Red):',
        '電力予備率 注意 (黄):':     'Reserve Rate Warning (Yellow):',
        'インバランス単価:':         'Imbalance:',
        '電力予備率:':               'Power Reserve:',
        '全国天気予報:':             'Weather:',
        '発電停止状況 (HJKS):':      'Gen. Status (HJKS):',
        'JKM LNG 価格:':            'JKM LNG:',
        'データの保持期間:':         'Data Retention:',
        '表示言語:':                 'Display Language:',
        # Settings - buttons / suffixes / toasts
        '今すぐ古いデータを整理':                   'Clean Up Old Data',
        'Windows 起動時にバックグラウンドで自動実行する': 'Auto-run on Windows startup (background)',
        '設定を保存':                               'Save Settings',
        '初期化':                                   'Reset',
        '🔄 初期化':                                '🔄 Reset',
        '保存しました':                             'Saved',
        '✅ 保存しました':                           '✅ Saved',
        '変更がありません':                          'No changes',
        '整理中...':                                'Processing...',
        '変更は再起動後に適用されます':              'Restart required to apply changes',
        ' 円': ' ¥',   '  円': '  ¥',
        ' %': ' %',    '  %': '  %',
        ' 日': ' days', '  日': '  days',
        '  分': '  min',
        '  件': '  items',
        # Settings - message boxes
        '確認':     'Confirm',
        '完了':     'Done',
        'エラー':   'Error',
        '設定を初期値に戻しますか？':
            'Reset all settings to defaults?',
        '保持期間({0}日)より古いデータを\nバックアップして削除しますか？':
            'Back up and delete data older than {0} day(s)?',
        '古いデータのバックアップと削除が完了しました。\n(保存先: backups フォルダ)':
            'Old data backup and deletion completed.\n(Saved to: backups folder)',
        '処理中にエラーが発生しました:':
            'An error occurred during processing:',
        # Settings - tooltips
        'インバランス単価がこの値を超過した場合、警告を通知します。':
            'Alert when imbalance price exceeds this value.',
        '電力予備率がこの値を下回った場合、赤色の警告を通知します。':
            'Alert (red) when power reserve falls below this value.',
        '電力予備率がこの値を下回った場合、黄色の注意を通知します。':
            'Warning (yellow) when power reserve falls below this value.',
        'インバランス単価のデータ取得間隔（分）':
            'Imbalance price data fetch interval (minutes)',
        '電力予備率のデータ取得間隔（分）':
            'Power reserve data fetch interval (minutes)',
        '全国天気予報のデータ取得間隔（分）':
            'Weather forecast data fetch interval (minutes)',
        '発電停止状況(HJKS)のデータ取得間隔（分）':
            'HJKS data fetch interval (minutes)',
        'JKM LNG 価格のデータ取得間隔（分）':
            'JKM LNG price data fetch interval (minutes)',
        'この日数を超えた古いデータは自動的にバックアップされ、メインDBから削除されます。':
            'Data older than this many days will be automatically backed up and deleted.',
        '今すぐ手動で古いデータのバックアップと削除処理を実行します。':
            'Manually run backup and deletion of old data now.',
        'PC起動時、自動的にバックグラウンド（トレイアイコン）で実行します。':
            'Automatically run in background (tray icon) at PC startup.',
        # Bug report widget
        'バグレポート送信':             'Submit Bug Report',
        '発生した問題の概要:':          'Issue Summary:',
        '詳細な説明・再現手順:':        'Detailed Description / Steps to Reproduce:',
        '添付ログ (自動取得):':         'Attached Log (auto-fetched):',
        '送信中...':                    'Sending...',
        '送信':                         'Send',
        '送信  →':                      'Send  →',
        'クリア':                       'Clear',
        'レポートを送信しました。':     'Bug report sent successfully.',
        '送信に失敗しました:':          'Failed to send bug report:',
        '概要を入力してください。':     'Please enter a summary.',
        # AI chat widget
        'メッセージを入力...':          'Enter message...',
        'メッセージを入力...  (Enter 送信 / Shift+Enter 改行)':
            'Enter message...  (Enter to send / Shift+Enter for newline)',
        '送信 (Enter)':                 'Send (Enter)',
        'チャット履歴をクリア':         'Clear Chat History',
        'AI アシスタント':              'AI Assistant',
        '考え中':                       'Thinking',
        '考え中...':                    'Thinking...',
        'AIサービスに接続できません。': 'Cannot connect to AI service.',
        'モデル:':                      'Model:',
        # Bug report - field labels
        '分類':                         'Category',
        '概要':                         'Summary',
        '詳細・再現手順  (任意)':        'Details / Steps  (optional)',
        '例: ダッシュボードが起動時にクラッシュする':
            'e.g. Dashboard crashes at startup',
        'ログ (自動取得)':              'Log  (auto-fetched)',
        # Text memo widget
        'テキストメモ管理':             'Text Memo Manager',
        '新規追加':                     'Add New',
        '削除':                         'Delete',
        'コピー':                       'Copy',
        'タイトル:':                    'Title:',
        'タグ:':                        'Tags:',
        '内容:':                        'Content:',
        '保存':                         'Save',
        'クリップボードにコピーしました': 'Copied to clipboard',
        '検索...':                      'Search...',
        'メモが見つかりません':         'No memos found',
        # Text memo - placeholders / status
        'タイトルを入力...':            'Enter title...',
        'タグ (カンマ区切り)  例: AI, プロンプト':
            'Tags (comma-separated)  e.g. AI, Prompt',
        'テキスト・プロンプトをここに入力...\n「コピー」ボタンでクリップボードへコピーできます。':
            'Enter text or prompt here...\nClick "Copy" to copy to clipboard.',
        '新しいメモ':                   'New Memo',
        '無題のメモ':                   'Untitled Memo',
        '削除の確認':                   'Confirm Delete',
        '「{0}」を削除しますか？':      'Delete "{0}"?',
        '削除しました。':               'Deleted.',
        '作成: {0}':                    'Created: {0}',
        'タグ: {0}':                    'Tags: {0}',
        '{0} 件':                       '{0} items',
        '{0} / {1} 件':                 '{0} / {1} items',
        '{0} 文字':                     '{0} chars',
        # Startup splash
        '起動中...':                    'Starting up...',
        # AI chat welcome / API errors
        '⚠️ API キーが取得できませんでした。\nアプリを再インストールするか、管理者にお問い合わせください。':
            '⚠️ Could not retrieve API keys.\nPlease reinstall the app or contact the administrator.',
        '⏳ 全APIのリクエスト上限に達しました。\n{0}秒後に再試行できます。（無料枠リセット: UTC 0:00）':
            '⏳ All API request limits reached.\nRetry in {0} seconds. (Free quota resets at UTC 0:00)',
        '日本の電力市場・インバランス単価・LNG価格などについて質問できます。':
            'You can ask about Japan\'s power market, imbalance prices, LNG prices, and more.',
        '試してみてください:':          'Try asking:',
        'インバランス単価の最近の動向を教えて': 'Tell me about recent imbalance price trends',
        '電力予備率が低下するとどうなりますか？': 'What happens when the power reserve rate drops?',
        'LNG価格と電力価格の関係を説明して': 'Explain the relationship between LNG and electricity prices',
        # Bug report categories
        '🐛  バグ・エラー':             '🐛  Bug / Error',
        '🖥️  UI表示の問題':             '🖥️  UI Display Issue',
        '📡  データ取得エラー':         '📡  Data Fetch Error',
        '⚡  パフォーマンス問題':        '⚡  Performance Issue',
        '💡  機能要望':                 '💡  Feature Request',
        '❓  その他':                   '❓  Other',
        '1. アプリを起動する\n2. ○○をクリックする\n3. エラーが発生する':
            '1. Launch the app\n2. Click on [item]\n3. Error occurs',
        '[ログ読込失敗: {0}]':          '[Log load failed: {0}]',
        'レポートを送信しました。ありがとうございます。': 'Report sent. Thank you!',
        '【分類】':                     '[Category] ',
        '【概要】':                     '[Summary] ',
        '【詳細・再現手順】\n':         '[Details / Steps to Reproduce]\n',
        '(未記入)':                     '(not entered)',
        '【ログ (直近 {0} 行)】\n':     '[Log (last {0} lines)]\n',
        # Settings AI section labels / tooltips
        'フォールバックモデル:':        'Fallback Model:',
        '応答の温度:':                  'Response Temperature:',
        '最大トークン数:':              'Max Tokens:',
        '会話履歴の保持数:':            'Chat History Limit:',
        'Gemini 3.1 Flash Lite の次に試みるフォールバックモデル。\n通常は gemini-2.5-flash (推奨) で十分です。':
            'Fallback model tried after Gemini 3.1 Flash Lite.\ngemini-2.5-flash (recommended) is sufficient in most cases.',
        'AIの回答の多様性を制御します。\n低い値 (0.1〜0.5): 正確・一貫した回答\n高い値 (1.0〜2.0): 多様・創造的な回答\n推奨: 0.7':
            'Controls the diversity of AI responses.\nLow (0.1–0.5): Precise, consistent answers\nHigh (1.0–2.0): Varied, creative answers\nRecommended: 0.7',
        '一回の回答で生成する最大文字数を制御します。\n長い回答が必要な場合は 4096 を選択。\n推奨: 2,048':
            'Controls the maximum tokens per response.\nChoose 4096 for longer answers.\nRecommended: 2,048',
        'AIに渡す過去の会話メッセージ数の上限です。\n多いほどコンテキストが保たれますが API 使用量が増加します。\n推奨: 20':
            'Max past messages passed to the AI.\nMore messages preserve context but increase API usage.\nRecommended: 20',
        '※ 優先順位: Gemini 3.1 Flash Lite → 上記モデル → Groq (llama-3.3-70b)':
            '※ Priority: Gemini 3.1 Flash Lite → Above model → Groq (llama-3.3-70b)',
        # Common status messages
        '更新中...':                    'Updating...',
        '更新完了':                     'Updated',
        '更新失敗':                     'Update failed',
        'データなし':                   'No data',
        '読込エラー':                   'Load error',
        '待機中':                       'Standby',
        '待機中...':                    'Standby...',
        'データ待機中...':              'Awaiting data...',
        'データ取得中...':              'Fetching data...',
        '取得完了':                     'Fetched',
        '取得失敗':                     'Fetch failed',
        # Dashboard card titles / values
        '総合ダッシュボード':            'Overview Dashboard',
        '本日の最大インバランス':        "Today's Max Imbalance",
        '本日の最低電力予備率':          "Today's Min Reserve Rate",
        '全国の天気':                    'National Weather',
        '最新 JKM LNG 価格':            'Latest JKM LNG Price',
        '本日の発電稼働容量':            "Today's Operating Capacity",
        '-- 円':                        '-- ¥',
        '本日のデータなし':             'No data for today',
        '{0} (前日比 {1} {2}%)':        '{0}  ({1}{2}% vs prev day)',
        '-- USD':                       '-- USD',
        '停止中: {0} MW':               'Stopped: {0} MW',
        'コマ {0} / {1}':               'Slot {0} / {1}',
        # Error / dialog messages
        '通知':                         'Notice',
        'データの取得中にエラーが発生しました:\n{0}':
            'An error occurred while fetching data:\n{0}',
        '保存するデータがありません。':  'No data to save.',
        'CSVファイルとして保存しました。\nExcelで開くことができます。':
            'Saved as CSV file.\nYou can open it in Excel.',
        '保存に失敗しました:\n{0}':     'Failed to save:\n{0}',
        'DBにデータがありません。「Yahoo Finance から取込」で取得してください。':
            'No data in DB. Please fetch via "Import from Yahoo Finance".',
        'DBエラー: {0}':                'DB Error: {0}',
        # Notification / alert messages
        '...他 {0}件の警告があります':  '...and {0} more warnings',
        '⚠ 予備率警告 (計 {0}件) - {1}':  '⚠ Reserve Warning ({0} total) - {1}',
        '⚠ インバランス 警告 (計 {0}件) - {1}': '⚠ Imbalance Warning ({0} total) - {1}',
        '本日のデータに予備率{0}%以下のコマが 【計 {1}件】 発生しています。':
            'Today\'s data shows {1} slots with reserve rate ≤{0}%.',
        '本日データに{0}円超の単価が 【計 {1}件】 発生しました。':
            'Today\'s data has {1} slots with price >{0}¥.',
        # Clipboard messages
        'グラフ画像をクリップボードにコピーしました。\n(Excel等に貼り付け可能です)':
            'Graph image copied to clipboard.\n(Can be pasted into Excel, etc.)',
        'グラフ画像をクリップボードにコピーしました。':
            'Graph image copied to clipboard.',
        # Weather status / detail
        '天気データを取得中...':         'Fetching weather data...',
        '📍 {0} の詳細天気 (7日間)':    '📍 {0} - 7-Day Forecast',
        # WMO weather code strings
        '晴れ': 'Sunny', '概ね晴れ': 'Mostly Sunny', '一部曇り': 'Partly Cloudy',
        '曇り': 'Cloudy', '霧': 'Fog', '霧氷': 'Freezing Fog',
        '弱い霧雨': 'Light Drizzle', '霧雨': 'Drizzle', '強い霧雨': 'Heavy Drizzle',
        '弱い着氷性霧雨': 'Light Freezing Drizzle', '強い着氷性霧雨': 'Heavy Freezing Drizzle',
        '弱い雨': 'Light Rain', '雨': 'Rain', '強い雨': 'Heavy Rain',
        '弱い着氷性の雨': 'Light Freezing Rain', '強い着氷性の雨': 'Heavy Freezing Rain',
        '弱い雪': 'Light Snow', '雪': 'Snow', '強い雪': 'Heavy Snow',
        '霧雪': 'Blowing Snow', '弱い小雨': 'Light Shower', '小雨': 'Shower',
        '激しい小雨': 'Heavy Shower', '弱い雪降る': 'Light Snow Shower', '強い雪降る': 'Heavy Snow Shower',
        '雷雨': 'Thunderstorm', '弱い雹の雷雨': 'Thunderstorm w/ Light Hail',
        '強い雹の雷雨': 'Thunderstorm w/ Heavy Hail', '不明': 'Unknown',
        # HJKS plot / tooltip labels
        '稼働可能容量 (MW)':            'Operable Capacity (MW)',
        '停止中':                       'Stopped',
        '【発電方式別】':               'By Generation Type',
        '【選択エリア別】':             'By Selected Area',
        # Imbalance DB / no-data
        '{0} のデータがありません。\n(DBに保存されている期間: {1} ~ {2})':
            'No data for {0}.\n(Data stored in DB: {1} ~ {2})',
        'DBに有効なデータがありません。': 'No valid data in DB.',
        # Log viewer errors
        'ログの読み込みに失敗しました: {0}':   'Failed to load logs: {0}',
        '予期せぬエラーが発生しました: {0}':   'An unexpected error occurred: {0}',
        # Log viewer UI labels
        'システムログ (System Logs)':          'System Logs',
        'すべての機能':                        'All Modules',
        'システム起動・終了':                  'App Start / Stop',
        '発電停止状況 (HJKS)':                 'Gen. Status (HJKS)',
        '全国天気予報':                        'Weather Forecast',
        '電力予備率 (OCCTO)':                  'Power Reserve (OCCTO)',
        'すべてのログレベル':                  'All Levels',
        'ログ消去':                            'Clear Log',
        '手動更新':                            'Refresh',
        # Standalone units / terms
        'コマ': 'Slot',
        '円': '¥',
        # Japan region names (display only — keys remain Japanese for data lookups)
        '北海道': 'Hokkaido', '東北': 'Tohoku', '東京': 'Tokyo',
        '中部': 'Chubu', '北陸': 'Hokuriku', '関西': 'Kansai',
        '中国': 'Chugoku', '四国': 'Shikoku', '九州': 'Kyushu', '沖縄': 'Okinawa',
        '北海道 (札幌)': 'Hokkaido (Sapporo)', '東北 (仙台)': 'Tohoku (Sendai)',
        '中部 (名古屋)': 'Chubu (Nagoya)', '北陸 (新潟)': 'Hokuriku (Niigata)',
        '関西 (大阪)': 'Kansai (Osaka)', '中国 (広島)': 'Chugoku (Hiroshima)',
        '四国 (高松)': 'Shikoku (Takamatsu)', '九州 (福岡)': 'Kyushu (Fukuoka)',
        # Generation methods (display only)
        '火力（石炭）': 'Coal', '火力（ガス）': 'Gas', '火力（石油）': 'Oil',
        '原子力': 'Nuclear', '水力': 'Hydro', 'その他': 'Other',
        # Power reserve widget
        'エリア別 予備率 (5分自動更新)':       'Reserve Rate by Area (5-min Auto Update)',
        'Excel(CSV) 保存':                     'Save Excel (CSV)',
        'CSV保存':                             'Save CSV',
        # HJKS widget
        '発電所 稼働可能容量 推移 (HJKS)':    'Power Plant Operable Capacity (HJKS)',
        'データ更新':                          'Update Data',
        'グラフ画像をコピー':                  'Copy Graph Image',
        'ビュー初期化':                        'Reset View',
        '表示エリア選択':                      'Select Areas',
        '全選択':                              'Select All',
        '全解除':                              'Deselect All',
        '【発電方式 凡例】':                   'Generation Type Legend',
        # Weather widget
        '全国天気予報 (Open-Meteo)':           'National Weather Forecast (Open-Meteo)',
        '更新 (再取得)':                       'Refresh (Re-fetch)',
        '👈 左側の地域を選択してください':     '👈 Select a region on the left',
        '天気':                                'Weather',
        '最高気温':                            'Max Temp',
        '最低気温':                            'Min Temp',
        '降水確率':                            'Rain %',
        '降水量':                              'Rainfall',
        '雲量':                                'Cloud Cover',
        '最大風速':                            'Max Wind',
        # JKM widget
        'JKM LNG スポット価格 (USD/MMBtu)':   'JKM LNG Spot Price (USD/MMBtu)',
        'Yahoo Finance から取込':              'Import from Yahoo Finance',
        '表示期間:':                           'Period:',
        '〜':                                  'to',
        '表示':                                'Show',
        '終値\n(USD/MMBtu)':                   'Close\n(USD/MMBtu)',
        '高値':                                'High',
        '安値':                                'Low',
        '前日比(%)':                           'Change (%)',
        '最新':                                'Latest',
        '表示: {0}件  最新: {1} USD/MMBtu  ({2})':
            'Showing: {0}  Latest: {1} USD/MMBtu  ({2})',
        '日付':                                'Date',
        '終値':                                'Close',
        '開始日は終了日以前である必要があります。':
            'Start date must be on or before the end date.',
        # Imbalance widget
        'インバランス単価':                    'Imbalance Price',
        '今月分 DB更新':                       'Update DB (This Month)',
        '余剰インバランス料金単価':            'Surplus Imbalance Price',
        '不足インバランス料金単価':            'Shortage Imbalance Price',
        '表表示':                              'Show Table',
        'グラフ表示':                          'Show Graph',
        'マップ表示':                          'Show Map',
        'マップ画像をコピー':                  'Copy Map Image',
        '予備率ヒートマップ':                  'Reserve Heatmap',
        '  エリア':                            '  Area',
        'DB更新中...':                         'Updating DB...',
        'データ読込中...':                     'Loading data...',
        '単価 [円/kWh]':                       'Price [¥/kWh]',
        '時刻コード':                          'Time Slot',
        'エリア: {0}\n時刻: {1}\n単価: {2} 円': 'Area: {0}\nTime: {1}\nPrice: {2} ¥',
        # Google Calendar widget
        'Google カレンダー':                    'Google Calendar',
        'イベントを編集':                       'Edit Event',
        'タイトル (必須)':                      'Title (required)',
        'タイトル:':                            'Title:',
        'カレンダー:':                          'Calendar:',
        '終日イベント':                         'All Day',
        '開始:':                               'Start:',
        '終了:':                               'End:',
        'メモ・詳細 (任意)':                   'Memo / Details (optional)',
        'メモ:':                               'Memo:',
        '新規イベント':                         'New Event',
        '読込中...':                           'Loading...',
        '{0}件のイベント':                      '{0} events',
        'イベントなし':                         'No events',
        '  イベントなし':                       '  No events',
        'カレンダー':                           'Calendar',
        '(タイトルなし)':                       '(No title)',
        '終日':                                 'All Day',
        '編集':                                 'Edit',
        'Google 認証が必要です':                'Google Authentication Required',
        '設定画面から Google アカウントで認証してください。':
            'Please authenticate with your Google account in Settings.',
        'タイトルを入力してください。':         'Please enter a title.',
        'イベント詳細':                         'Event Details',
        '閉じる':                               'Close',
        '🔄 更新':                             '🔄 Refresh',
        # Gmail widget
        'Gmail':                                'Gmail',
        '受信トレイ':                           'Inbox',
        'スター付き':                           'Starred',
        '重要':                                 'Important',
        '送信済み':                             'Sent',
        '迷惑メール':                           'Spam',
        'ゴミ箱':                               'Trash',
        '📧  メールを選択してください':         '📧  Select a mail',
        'ブラウザで開く':                        'Open in Browser',
        '(件名なし)':                           '(No Subject)',
        '(本文なし)':                           '(No body)',
        'さらに読み込む':                       'Load More',
        'アラームをオフ':                        'Turn off alarm',
        'アラームをオン':                        'Turn on alarm',
        'ラベル表示設定':                        'Label Display Settings',
        'すべて表示':                            'Show All',
        'すべて非表示':                          'Hide All',
        'すべて既読':                            'Mark All as Read',
        'このラベルにメールはありません':         'No mail in this label',
        '表示するラベルを選択してください。ドラッグで並び替え可能です。':
            'Select labels to display. Drag to reorder.',
        '適用':                                  'Apply',
        '処理中...':                             'Processing...',
        # Settings - Google integration
        '🔗   Google 連携':                     '🔗   Google Integration',
        'Google 連携':                          'Google Integration',
        'Google アカウントで認証':              'Authenticate with Google',
        '認証済 ✅':                            'Authenticated ✅',
        '未認証':                               'Not Authenticated',
        '認証を解除':                           'Revoke Auth',
        'カレンダー 更新間隔:':                 'Calendar Interval:',
        'Gmail 更新間隔:':                      'Gmail Interval:',
        'メール取得件数:':                      'Mail Fetch Count:',
        'Google カレンダー:':                   'Google Calendar:',
        'Gmail:':                               'Gmail:',
        'Client ID と Client Secret は Google Cloud Console から取得できます。\n認証後はカレンダーと Gmail が利用可能になります。':
            'Client ID and Client Secret can be obtained from Google Cloud Console.\nAfter authentication, Calendar and Gmail will be available.',
        # JEPX Spot Market widget
        'JEPXスポット平均価格':                 'JEPX Spot Avg Price',
        '明日':                                 'Tomorrow',
        '平均':                                 'Avg',
        '最高':                                 'Max',
        '最低':                                 'Min',
        'スポット市場':                         'Spot Market',
        '当日スポット価格':                     'Daily Spot Price',
        '日次平均推移':                         'Daily Average Trend',
        '月次平均推移':                         'Monthly Average Trend',
        '年次平均推移':                         'Yearly Average Trend',
        '曜日別日次推移':                       'Weekday Daily Trend',
        '月曜日': 'Monday', '火曜日': 'Tuesday', '水曜日': 'Wednesday',
        '木曜日': 'Thursday', '金曜日': 'Friday', '土曜日': 'Saturday', '日曜日': 'Sunday',
        '期間:':                                'Period:',
        '今年度':                               'Current FY',
        '曜日:':                                'Weekday:',
        '年度:':                                'FY:',
        '更新':                                 'Refresh',
        'ビューリセット':                       'Reset View',
        '表':                                   'Table',
        'グラフ':                               'Chart',
        'グラフコピー':                         'Copy Chart',
        'エリア:':                              'Area:',
        '今日':                                 'Today',
        '価格 (円/kWh)':                        'Price (¥/kWh)',
        '時刻':                                 'Time',
        '年月':                                 'Year/Month',
        '年':                                   'Year',
        'データ取得中…':                        'Fetching data…',
        'データ取得完了':                       'Data fetch complete',
        '当日データ取得完了 ({0})':             "Today's data fetched ({0})",
        '当日データ未公開 — 次回再試行':        "Today's data not yet published — will retry",
        '{0}年 データ取得中… ({1}/{2})':        'Fetching {0} data… ({1}/{2})',
        'エリアが選択されていません':           'No area selected',
        'データ取得エラー: {0}':               'Data fetch error: {0}',
        '{0} ({1} 〜 {2}): {3} 件':            '{0} ({1} – {2}): {3} records',
        '{0} 件のデータを表示中':              'Showing {0} records',
        'グラフをクリップボードにコピーしました': 'Chart copied to clipboard',
        'エラー: {0}':                          'Error: {0}',
        'X':                                    'X',
        # Google notification (tray)
        '📧 新着メール ({0}件) - {1}':          '📧 New Mail ({0}) - {1}',
    },
    # ── 韓国語 ────────────────────────────────────────────────────────────
    'ko': {
        # Navigation tabs
        'ダッシュボード':       '대시보드',
        '電力予備率':           '전력 예비율',
        'インバランス':         '인밸런스',
        'JKM LNG 価格':        'JKM LNG 가격',
        '全国天気':             '전국 날씨',
        '発電稼働状況':         '발전 가동 현황',
        '通知センター':         '알림 센터',
        '通知センター ({0})':  '알림 센터 ({0})',
        '設定':                 '설정',
        'システムログ':         '시스템 로그',
        # Navigation groups / short labels
        '⚡  電力データ':       '⚡  전력 데이터',
        '🔵  Google':           '🔵  Google',
        '🛠  ツール':           '🛠  도구',
        'バグ':                 '버그',
        'ログ':                 '로그',
        # New widget tabs
        'バグレポート':         '버그 리포트',
        'AI チャット':          'AI 채팅',
        'テキストメモ':         '텍스트 메모',
        # Network / theme
        '🟢 オンライン':        '🟢 온라인',
        '🔴 オフライン':        '🔴 오프라인',
        '☀️ ライトモード':      '☀️ 라이트 모드',
        '🌙 ダークモード':      '🌙 다크 모드',
        # Tray / dialogs
        '開く (Open)':          '열기',
        '完全に終了 (Quit)':    '종료',
        'LEE電力モニター':      'LEE 전력 모니터',
        'LEE電力モニター - バックグラウンド実行中':
            'LEE 전력 모니터 - 백그라운드 실행 중',
        '終了の確認':           '종료 확인',
        'アプリケーションを完全に終了しますか？\nそれともトレイ（バックグラウンド）に最小化しますか？':
            '앱을 완전히 종료할까요?\n또는 트레이(백그라운드)로 최소화할까요?',
        'トレイに最小化':       '트레이로 최소화',
        '完全に終了':           '완전 종료',
        'キャンセル':           '취소',
        'バックグラウンドで実行中です。\nアイコンをダブルクリックで開きます。':
            '백그라운드에서 실행 중입니다.\n아이콘을 더블클릭하여 열 수 있습니다.',
        'ネットワーク接続が切断されました。自動更新を一時停止します。':
            '네트워크 연결이 끊겼습니다. 자동 갱신을 일시 중지합니다.',
        # Settings - group headers
        '⚙️ 設定 (Settings)':              '⚙️ 설정',
        '⚠️ アラートしきい値設定':           '⚠️ 알림 임계값 설정',
        '⏱️ 自動更新間隔 (分)':             '⏱️ 자동 갱신 간격 (분)',
        '💾 データ寿命管理 (バックアップと削除)': '💾 데이터 보존 관리 (백업·삭제)',
        '💻 システム設定':                   '💻 시스템 설정',
        '🌍 言語設定 (Language)':           '🌍 언어 설정',
        # Settings - group header (inline keys used in _make_group calls)
        'アラートしきい値':                 '알림 임계값',
        '自動更新間隔':                     '자동 갱신 간격',
        'データ管理':                       '데이터 관리',
        'システム':                         '시스템',
        '言語 (Language)':                  '언어 (Language)',
        # Settings - form labels
        'インバランス単価 警告:':    '인밸런스 단가 경고:',
        '電力予備率 警告 (赤):':     '전력 예비율 경고 (빨강):',
        '電力予備率 注意 (黄):':     '전력 예비율 주의 (노랑):',
        'インバランス単価:':         '인밸런스:',
        '電力予備率:':               '전력 예비율:',
        '全国天気予報:':             '날씨 예보:',
        '発電停止状況 (HJKS):':      '발전 현황 (HJKS):',
        'JKM LNG 価格:':            'JKM LNG:',
        'データの保持期間:':         '데이터 보존 기간:',
        '表示言語:':                 '표시 언어:',
        # Settings - buttons / suffixes / toasts
        '今すぐ古いデータを整理':                   '지금 오래된 데이터 정리',
        'Windows 起動時にバックグラウンドで自動実行する': 'Windows 시작 시 백그라운드로 자동 실행',
        '設定を保存':                               '설정 저장',
        '初期化':                                   '초기화',
        '🔄 初期化':                                '🔄 초기화',
        '保存しました':                             '저장됨',
        '✅ 保存しました':                           '✅ 저장됨',
        '変更がありません':                          '변경 없음',
        '整理中...':                                '정리 중...',
        '変更は再起動後に適用されます':              '변경 사항은 재시작 후 적용됩니다',
        ' 円': ' 엔',   '  円': '  엔',
        ' %': ' %',    '  %': '  %',
        ' 日': ' 일',  '  日': '  일',
        '  分': '  분',
        '  件': '  건',
        # Settings - message boxes
        '確認':     '확인',
        '完了':     '완료',
        'エラー':   '오류',
        '設定を初期値に戻しますか？':
            '설정을 기본값으로 되돌릴까요?',
        '保持期間({0}日)より古いデータを\nバックアップして削除しますか？':
            '보존 기간({0}일)보다 오래된 데이터를\n백업하고 삭제할까요?',
        '古いデータのバックアップと削除が完了しました。\n(保存先: backups フォルダ)':
            '오래된 데이터의 백업 및 삭제가 완료되었습니다.\n(저장 위치: backups 폴더)',
        '処理中にエラーが発生しました:':
            '처리 중 오류가 발생했습니다:',
        # Settings - tooltips
        'インバランス単価がこの値を超過した場合、警告を通知します。':
            '인밸런스 단가가 이 값을 초과하면 경고를 알립니다.',
        '電力予備率がこの値を下回った場合、赤色の警告を通知します。':
            '전력 예비율이 이 값 미만이면 빨간색 경고를 알립니다.',
        '電力予備率がこの値を下回った場合、黄色の注意を通知します。':
            '전력 예비율이 이 값 미만이면 노란색 주의를 알립니다.',
        'インバランス単価のデータ取得間隔（分）':   '인밸런스 단가 취득 간격 (분)',
        '電力予備率のデータ取得間隔（分）':         '전력 예비율 취득 간격 (분)',
        '全国天気予報のデータ取得間隔（分）':        '날씨 예보 취득 간격 (분)',
        '発電停止状況(HJKS)のデータ取得間隔（分）': 'HJKS 취득 간격 (분)',
        'JKM LNG 価格のデータ取得間隔（分）':       'JKM LNG 취득 간격 (분)',
        'この日数を超えた古いデータは自動的にバックアップされ、メインDBから削除されます。':
            '이 일수를 초과한 데이터는 자동으로 백업 후 메인 DB에서 삭제됩니다.',
        '今すぐ手動で古いデータのバックアップと削除処理を実行します。':
            '지금 즉시 오래된 데이터의 백업 및 삭제 처리를 실행합니다.',
        'PC起動時、自動的にバックグラウンド（トレイアイコン）で実行します。':
            'PC 시작 시 자동으로 백그라운드(트레이)로 실행합니다.',
        # Bug report widget
        'バグレポート送信':             '버그 리포트 전송',
        '発生した問題の概要:':          '발생한 문제 요약:',
        '詳細な説明・再現手順:':        '상세 설명 / 재현 단계:',
        '添付ログ (自動取得):':         '첨부 로그 (자동 취득):',
        '送信中...':                    '전송 중...',
        '送信':                         '전송',
        '送信  →':                      '전송  →',
        'クリア':                       '지우기',
        'レポートを送信しました。':     '버그 리포트를 전송했습니다.',
        '送信に失敗しました:':          '전송에 실패했습니다:',
        '概要を入力してください。':     '요약을 입력해 주세요.',
        # AI chat widget
        'メッセージを入力...':          '메시지를 입력하세요...',
        'メッセージを入力...  (Enter 送信 / Shift+Enter 改行)':
            '메시지를 입력하세요...  (Enter 전송 / Shift+Enter 줄바꿈)',
        '送信 (Enter)':                 '전송 (Enter)',
        'チャット履歴をクリア':         '채팅 기록 지우기',
        'AI アシスタント':              'AI 어시스턴트',
        '考え中':                       '생각 중',
        '考え中...':                    '생각 중...',
        'AIサービスに接続できません。': 'AI 서비스에 연결할 수 없습니다.',
        'モデル:':                      '모델:',
        # Bug report - field labels
        '分類':                         '분류',
        '概要':                         '요약',
        '詳細・再現手順  (任意)':        '상세 내용 / 재현 단계  (선택)',
        '例: ダッシュボードが起動時にクラッシュする':
            '예: 대시보드가 시작 시 충돌한다',
        'ログ (自動取得)':              '로그  (자동 취득)',
        # Text memo widget
        'テキストメモ管理':             '텍스트 메모 관리',
        '新規追加':                     '새로 추가',
        '削除':                         '삭제',
        'コピー':                       '복사',
        'タイトル:':                    '제목:',
        'タグ:':                        '태그:',
        '内容:':                        '내용:',
        '保存':                         '저장',
        'クリップボードにコピーしました': '클립보드에 복사됨',
        '検索...':                      '검색...',
        'メモが見つかりません':         '메모를 찾을 수 없습니다',
        # Text memo - placeholders / status
        'タイトルを入力...':            '제목을 입력하세요...',
        'タグ (カンマ区切り)  例: AI, プロンプト':
            '태그 (쉼표 구분)  예: AI, 프롬프트',
        'テキスト・プロンプトをここに入力...\n「コピー」ボタンでクリップボードへコピーできます。':
            '텍스트 또는 프롬프트를 여기에 입력하세요...\n「복사」 버튼으로 클립보드에 복사할 수 있습니다.',
        '新しいメモ':                   '새 메모',
        '無題のメモ':                   '제목 없는 메모',
        '削除の確認':                   '삭제 확인',
        '「{0}」を削除しますか？':      '"{0}"을(를) 삭제할까요?',
        '削除しました。':               '삭제되었습니다.',
        '作成: {0}':                    '작성: {0}',
        'タグ: {0}':                    '태그: {0}',
        '{0} 件':                       '{0}건',
        '{0} / {1} 件':                 '{0} / {1}건',
        '{0} 文字':                     '{0}자',
        # Startup splash
        '起動中...':                    '시작 중...',
        # AI chat welcome / API errors
        '⚠️ API キーが取得できませんでした。\nアプリを再インストールするか、管理者にお問い合わせください。':
            '⚠️ API 키를 가져올 수 없습니다.\n앱을 재설치하거나 관리자에게 문의하세요.',
        '⏳ 全APIのリクエスト上限に達しました。\n{0}秒後に再試行できます。（無料枠リセット: UTC 0:00）':
            '⏳ 모든 API 요청 한도에 도달했습니다.\n{0}초 후 재시도 가능합니다. (무료 할당량 재설정: UTC 0:00)',
        '日本の電力市場・インバランス単価・LNG価格などについて質問できます。':
            '일본 전력 시장, 인밸런스 단가, LNG 가격 등에 대해 질문할 수 있습니다.',
        '試してみてください:':          '이런 질문을 해보세요:',
        'インバランス単価の最近の動向を教えて': '최근 인밸런스 단가 동향을 알려줘',
        '電力予備率が低下するとどうなりますか？': '전력 예비율이 떨어지면 어떻게 되나요?',
        'LNG価格と電力価格の関係を説明して': 'LNG 가격과 전력 가격의 관계를 설명해줘',
        # Bug report categories
        '🐛  バグ・エラー':             '🐛  버그·오류',
        '🖥️  UI表示の問題':             '🖥️  UI 표시 문제',
        '📡  データ取得エラー':         '📡  데이터 취득 오류',
        '⚡  パフォーマンス問題':        '⚡  성능 문제',
        '💡  機能要望':                 '💡  기능 요청',
        '❓  その他':                   '❓  기타',
        '1. アプリを起動する\n2. ○○をクリックする\n3. エラーが発生する':
            '1. 앱을 실행한다\n2. ○○를 클릭한다\n3. 오류가 발생한다',
        '[ログ読込失敗: {0}]':          '[로그 읽기 실패: {0}]',
        'レポートを送信しました。ありがとうございます。': '리포트를 전송했습니다. 감사합니다.',
        '【分類】':                     '【분류】',
        '【概要】':                     '【요약】',
        '【詳細・再現手順】\n':         '【상세 내용·재현 방법】\n',
        '(未記入)':                     '(미입력)',
        '【ログ (直近 {0} 行)】\n':     '【로그 (최근 {0}줄)】\n',
        # Settings AI section labels / tooltips
        'フォールバックモデル:':        '폴백 모델:',
        '応答の温度:':                  '응답 온도:',
        '最大トークン数:':              '최대 토큰 수:',
        '会話履歴の保持数:':            '대화 기록 보존 수:',
        'Gemini 3.1 Flash Lite の次に試みるフォールバックモデル。\n通常は gemini-2.5-flash (推奨) で十分です。':
            'Gemini 3.1 Flash Lite 다음에 시도하는 폴백 모델.\n일반적으로 gemini-2.5-flash(권장)로 충분합니다.',
        'AIの回答の多様性を制御します。\n低い値 (0.1〜0.5): 正確・一貫した回答\n高い値 (1.0〜2.0): 多様・創造的な回答\n推奨: 0.7':
            'AI 응답의 다양성을 제어합니다.\n낮은 값 (0.1~0.5): 정확하고 일관된 응답\n높은 값 (1.0~2.0): 다양하고 창의적인 응답\n권장: 0.7',
        '一回の回答で生成する最大文字数を制御します。\n長い回答が必要な場合は 4096 を選択。\n推奨: 2,048':
            '한 번의 응답에서 생성하는 최대 토큰 수를 제어합니다.\n긴 응답이 필요할 경우 4096을 선택하세요.\n권장: 2,048',
        'AIに渡す過去の会話メッセージ数の上限です。\n多いほどコンテキストが保たれますが API 使用量が増加します。\n推奨: 20':
            'AI에 전달하는 과거 대화 메시지 수의 상한입니다.\n많을수록 컨텍스트가 유지되지만 API 사용량이 증가합니다.\n권장: 20',
        '※ 優先順位: Gemini 3.1 Flash Lite → 上記モデル → Groq (llama-3.3-70b)':
            '※ 우선순위: Gemini 3.1 Flash Lite → 위 모델 → Groq (llama-3.3-70b)',
        # Common status messages
        '更新中...':                    '갱신 중...',
        '更新完了':                     '갱신 완료',
        '更新失敗':                     '갱신 실패',
        'データなし':                   '데이터 없음',
        '読込エラー':                   '읽기 오류',
        '待機中':                       '대기 중',
        '待機中...':                    '대기 중...',
        'データ待機中...':              '데이터 대기 중...',
        'データ取得中...':              '데이터 취득 중...',
        '取得完了':                     '취득 완료',
        '取得失敗':                     '취득 실패',
        # Dashboard card titles / values
        '総合ダッシュボード':            '종합 대시보드',
        '本日の最大インバランス':        '오늘의 최대 인밸런스',
        '本日の最低電力予備率':          '오늘의 최저 전력 예비율',
        '全国の天気':                    '전국 날씨',
        '最新 JKM LNG 価格':            '최신 JKM LNG 가격',
        '本日の発電稼働容量':            '오늘의 발전 가동 용량',
        '-- 円':                        '-- 엔',
        '本日のデータなし':             '오늘 데이터 없음',
        '{0} (前日比 {1} {2}%)':        '{0}  ({1}{2}% 전일 대비)',
        '-- USD':                       '-- USD',
        '停止中: {0} MW':               '정지 중: {0} MW',
        'コマ {0} / {1}':               '구간 {0} / {1}',
        # Error / dialog messages
        '通知':                         '알림',
        'データの取得中にエラーが発生しました:\n{0}':
            '데이터 취득 중 오류가 발생했습니다:\n{0}',
        '保存するデータがありません。':  '저장할 데이터가 없습니다.',
        'CSVファイルとして保存しました。\nExcelで開くことができます。':
            'CSV 파일로 저장했습니다.\nExcel에서 열 수 있습니다.',
        '保存に失敗しました:\n{0}':     '저장에 실패했습니다:\n{0}',
        'DBにデータがありません。「Yahoo Finance から取込」で取得してください。':
            'DB에 데이터가 없습니다. "Yahoo Finance에서 가져오기"로 취득하세요.',
        'DBエラー: {0}':                'DB 오류: {0}',
        # Notification / alert messages
        '...他 {0}件の警告があります':  '...외 {0}건의 경고가 있습니다',
        '⚠ 予備率警告 (計 {0}件) - {1}':  '⚠ 예비율 경고 (계 {0}건) - {1}',
        '⚠ インバランス 警告 (計 {0}件) - {1}': '⚠ 인밸런스 경고 (계 {0}건) - {1}',
        '本日のデータに予備率{0}%以下のコマが 【計 {1}件】 発生しています。':
            '오늘 데이터에 예비율 {0}% 이하인 코마가 【총 {1}건】 발생했습니다.',
        '本日データに{0}円超の単価が 【計 {1}件】 発生しました。':
            '오늘 데이터에 {0}엔 초과 단가가 【총 {1}건】 발생했습니다.',
        # Clipboard messages
        'グラフ画像をクリップボードにコピーしました。\n(Excel等に貼り付け可能です)':
            '그래프 이미지를 클립보드에 복사했습니다.\n(Excel 등에 붙여넣기 가능합니다)',
        'グラフ画像をクリップボードにコピーしました。':
            '그래프 이미지를 클립보드에 복사했습니다.',
        # Weather status / detail
        '天気データを取得中...':         '날씨 데이터 취득 중...',
        '📍 {0} の詳細天気 (7日間)':    '📍 {0} 상세 날씨 (7일간)',
        # WMO weather code strings
        '晴れ': '맑음', '概ね晴れ': '대체로 맑음', '一部曇り': '부분 흐림',
        '曇り': '흐림', '霧': '안개', '霧氷': '서리 안개',
        '弱い霧雨': '약한 이슬비', '霧雨': '이슬비', '強い霧雨': '강한 이슬비',
        '弱い着氷性霧雨': '약한 착빙성 이슬비', '強い着氷性霧雨': '강한 착빙성 이슬비',
        '弱い雨': '약한 비', '雨': '비', '強い雨': '강한 비',
        '弱い着氷性の雨': '약한 착빙성 비', '強い着氷性の雨': '강한 착빙성 비',
        '弱い雪': '약한 눈', '雪': '눈', '強い雪': '강한 눈',
        '霧雪': '눈보라', '弱い小雨': '약한 소나기', '小雨': '소나기',
        '激しい小雨': '강한 소나기', '弱い雪降る': '약한 눈 소나기', '強い雪降る': '강한 눈 소나기',
        '雷雨': '뇌우', '弱い雹の雷雨': '약한 우박 뇌우',
        '強い雹の雷雨': '강한 우박 뇌우', '不明': '불명',
        # HJKS plot / tooltip labels
        '稼働可能容量 (MW)':            '가동 가능 용량 (MW)',
        '停止中':                       '정지 중',
        '【発電方式別】':               '【발전 방식별】',
        '【選択エリア別】':             '【선택 에리어별】',
        # Imbalance DB / no-data
        '{0} のデータがありません。\n(DBに保存されている期間: {1} ~ {2})':
            '{0} 의 데이터가 없습니다.\n(DB에 저장된 기간: {1} ~ {2})',
        'DBに有効なデータがありません。': 'DB에 유효한 데이터가 없습니다.',
        # Log viewer errors
        'ログの読み込みに失敗しました: {0}':   '로그 읽기에 실패했습니다: {0}',
        '予期せぬエラーが発生しました: {0}':   '예기치 않은 오류가 발생했습니다: {0}',
        # Log viewer UI labels
        'システムログ (System Logs)':          '시스템 로그',
        'すべての機能':                        '전체 기능',
        'システム起動・終了':                  '앱 시작·종료',
        '発電停止状況 (HJKS)':                 '발전 현황 (HJKS)',
        '全国天気予報':                        '전국 날씨 예보',
        '電力予備率 (OCCTO)':                  '전력 예비율 (OCCTO)',
        'すべてのログレベル':                  '전체 레벨',
        'ログ消去':                            '로그 삭제',
        '手動更新':                            '수동 갱신',
        # Standalone units / terms
        'コマ': '구간',
        '円': '엔',
        # Japan region names (display only)
        '北海道': '홋카이도', '東北': '도호쿠', '東京': '도쿄',
        '中部': '주부', '北陸': '호쿠리쿠', '関西': '간사이',
        '中国': '주고쿠', '四国': '시코쿠', '九州': '규슈', '沖縄': '오키나와',
        '北海道 (札幌)': '홋카이도 (삿포로)', '東北 (仙台)': '도호쿠 (센다이)',
        '中部 (名古屋)': '주부 (나고야)', '北陸 (新潟)': '호쿠리쿠 (니가타)',
        '関西 (大阪)': '간사이 (오사카)', '中国 (広島)': '주고쿠 (히로시마)',
        '四国 (高松)': '시코쿠 (다카마쓰)', '九州 (福岡)': '규슈 (후쿠오카)',
        # Generation methods (display only)
        '火力（石炭）': '석탄 화력', '火力（ガス）': '가스 화력', '火力（石油）': '석유 화력',
        '原子力': '원자력', '水力': '수력', 'その他': '기타',
        # Power reserve widget
        'エリア別 予備率 (5分自動更新)':       '지역별 예비율 (5분 자동 갱신)',
        'Excel(CSV) 保存':                     'Excel(CSV) 저장',
        'CSV保存':                             'CSV 저장',
        # HJKS widget
        '発電所 稼働可能容量 推移 (HJKS)':    '발전소 가동 가능 용량 추이 (HJKS)',
        'データ更新':                          '데이터 갱신',
        'グラフ画像をコピー':                  '그래프 이미지 복사',
        'ビュー初期化':                        '뷰 초기화',
        '表示エリア選択':                      '표시 지역 선택',
        '全選択':                              '전체 선택',
        '全解除':                              '전체 해제',
        '【発電方式 凡例】':                   '【발전 방식 범례】',
        # Weather widget
        '全国天気予報 (Open-Meteo)':           '전국 날씨 예보 (Open-Meteo)',
        '更新 (再取得)':                       '갱신 (재취득)',
        '👈 左側の地域を選択してください':     '👈 왼쪽에서 지역을 선택하세요',
        '天気':                                '날씨',
        '最高気温':                            '최고 기온',
        '最低気温':                            '최저 기온',
        '降水確率':                            '강수 확률',
        '降水量':                              '강수량',
        '雲量':                                '운량',
        '最大風速':                            '최대 풍속',
        # JKM widget
        'JKM LNG スポット価格 (USD/MMBtu)':   'JKM LNG 현물 가격 (USD/MMBtu)',
        'Yahoo Finance から取込':              'Yahoo Finance에서 가져오기',
        '表示期間:':                           '표시 기간:',
        '〜':                                  '~',
        '表示':                                '표시',
        '終値\n(USD/MMBtu)':                   '종가\n(USD/MMBtu)',
        '高値':                                '고가',
        '安値':                                '저가',
        '前日比(%)':                           '전일 대비(%)',
        '最新':                                '최신',
        '表示: {0}件  最新: {1} USD/MMBtu  ({2})':
            '표시: {0}건  최신: {1} USD/MMBtu  ({2})',
        '日付':                                '날짜',
        '終値':                                '종가',
        '開始日は終了日以前である必要があります。':
            '시작일은 종료일 이전이어야 합니다.',
        # Imbalance widget
        'インバランス単価':                    '인밸런스 단가',
        '今月分 DB更新':                       'DB 갱신 (이번 달)',
        '余剰インバランス料金単価':            '잉여 인밸런스 단가',
        '不足インバランス料金単価':            '부족 인밸런스 단가',
        '表表示':                              '표 표시',
        'グラフ表示':                          '그래프 표시',
        'マップ表示':                          '맵 표시',
        'マップ画像をコピー':                  '맵 이미지 복사',
        '予備率ヒートマップ':                  '예비율 히트맵',
        '  エリア':                            '  지역',
        'DB更新中...':                         'DB 갱신 중...',
        'データ読込中...':                     '데이터 로드 중...',
        '単価 [円/kWh]':                       '단가 [엔/kWh]',
        '時刻コード':                          '시각 코드',
        'エリア: {0}\n時刻: {1}\n単価: {2} 円': '지역: {0}\n시각: {1}\n단가: {2} 엔',
        # Google Calendar widget
        'Google カレンダー':                    '구글 캘린더',
        'イベントを編集':                       '이벤트 편집',
        'タイトル (必須)':                      '제목 (필수)',
        'タイトル:':                            '제목:',
        'カレンダー:':                          '캘린더:',
        '終日イベント':                         '종일 이벤트',
        '開始:':                               '시작:',
        '終了:':                               '종료:',
        'メモ・詳細 (任意)':                   '메모·상세 (선택)',
        'メモ:':                               '메모:',
        '新規イベント':                         '새 이벤트',
        '読込中...':                           '로드 중...',
        '{0}件のイベント':                      '이벤트 {0}건',
        'イベントなし':                         '이벤트 없음',
        '  イベントなし':                       '  이벤트 없음',
        'カレンダー':                           '캘린더',
        '(タイトルなし)':                       '(제목 없음)',
        '終日':                                 '종일',
        '編集':                                 '편집',
        'Google 認証が必要です':                'Google 인증이 필요합니다',
        '設定画面から Google アカウントで認証してください。':
            '설정 화면에서 Google 계정으로 인증해 주세요.',
        'タイトルを入力してください。':         '제목을 입력해 주세요.',
        'イベント詳細':                         '이벤트 상세',
        '閉じる':                               '닫기',
        '🔄 更新':                             '🔄 갱신',
        # Gmail widget
        'Gmail':                                'Gmail',
        '受信トレイ':                           '받은편지함',
        'スター付き':                           '별표 표시됨',
        '重要':                                 '중요',
        '送信済み':                             '보낸편지함',
        '迷惑メール':                           '스팸',
        'ゴミ箱':                               '휴지통',
        '📧  メールを選択してください':         '📧  메일을 선택하세요',
        'ブラウザで開く':                        '브라우저에서 열기',
        '(件名なし)':                           '(제목 없음)',
        '(本文なし)':                           '(본문 없음)',
        'さらに読み込む':                       '더 불러오기',
        'アラームをオフ':                        '알람 끄기',
        'アラームをオン':                        '알람 켜기',
        'ラベル表示設定':                        '라벨 표시 설정',
        'すべて表示':                            '전체 표시',
        'すべて非表示':                          '전체 숨기기',
        'すべて既読':                            '전체 읽음 처리',
        'このラベルにメールはありません':         '이 라벨에 메일이 없습니다',
        '表示するラベルを選択してください。ドラッグで並び替え可能です。':
            '표시할 라벨을 선택하세요. 드래그로 순서를 변경할 수 있습니다.',
        '適用':                                  '적용',
        '処理中...':                             '처리 중...',
        # Settings - Google integration
        '🔗   Google 連携':                     '🔗   Google 연동',
        'Google 連携':                          'Google 연동',
        'Google アカウントで認証':              'Google 계정으로 인증',
        '認証済 ✅':                            '인증됨 ✅',
        '未認証':                               '미인증',
        '認証を解除':                           '인증 해제',
        'カレンダー 更新間隔:':                 '캘린더 갱신 간격:',
        'Gmail 更新間隔:':                      'Gmail 갱신 간격:',
        'メール取得件数:':                      '메일 취득 건수:',
        'Google カレンダー:':                   '구글 캘린더:',
        'Gmail:':                               'Gmail:',
        'Client ID と Client Secret は Google Cloud Console から取得できます。\n認証後はカレンダーと Gmail が利用可能になります。':
            'Client ID와 Client Secret은 Google Cloud Console에서 획득할 수 있습니다.\n인증 후 캘린더와 Gmail을 이용할 수 있습니다.',
        # JEPX Spot Market widget
        'JEPXスポット平均価格':                 'JEPX 스팟 평균가격',
        '明日':                                 '내일',
        '平均':                                 '평균',
        '最高':                                 '최고',
        '最低':                                 '최저',
        'スポット市場':                         '스팟 시장',
        '当日スポット価格':                     '당일 스팟 가격',
        '日次平均推移':                         '일별 평균 추이',
        '月次平均推移':                         '월별 평균 추이',
        '年次平均推移':                         '연별 평균 추이',
        '曜日別日次推移':                       '요일별 일별 추이',
        '月曜日': '월요일', '火曜日': '화요일', '水曜日': '수요일',
        '木曜日': '목요일', '金曜日': '금요일', '土曜日': '토요일', '日曜日': '일요일',
        '期間:':                                '기간:',
        '今年度':                               '현재 회계연도',
        '曜日:':                                '요일:',
        '年度:':                                '회계연도:',
        '更新':                                 '갱신',
        'ビューリセット':                       '뷰 초기화',
        '表':                                   '표',
        'グラフ':                               '그래프',
        'グラフコピー':                         '그래프 복사',
        'エリア:':                              '지역:',
        '今日':                                 '오늘',
        '価格 (円/kWh)':                        '가격 (엔/kWh)',
        '時刻':                                 '시각',
        '年月':                                 '연월',
        '年':                                   '연도',
        'データ取得中…':                        '데이터 취득 중…',
        'データ取得完了':                       '데이터 취득 완료',
        '当日データ取得完了 ({0})':             '당일 데이터 취득 완료 ({0})',
        '当日データ未公開 — 次回再試行':        '당일 데이터 미공개 — 다음 번 재시도',
        '{0}年 データ取得中… ({1}/{2})':        '{0}년 데이터 취득 중… ({1}/{2})',
        'エリアが選択されていません':           '지역이 선택되지 않았습니다',
        'データ取得エラー: {0}':               '데이터 취득 오류: {0}',
        '{0} ({1} 〜 {2}): {3} 件':            '{0} ({1} ~ {2}): {3}건',
        '{0} 件のデータを表示中':              '{0}건 데이터 표시 중',
        'グラフをクリップボードにコピーしました': '그래프를 클립보드에 복사했습니다',
        'エラー: {0}':                          '오류: {0}',
        'X':                                    'X',
        # Google notification (tray)
        '📧 新着メール ({0}件) - {1}':          '📧 새 메일 ({0}건) - {1}',
    },
    # ── 中国語 ────────────────────────────────────────────────────────────
    'zh': {
        # Navigation tabs
        'ダッシュボード':       '控制台',
        '電力予備率':           '电力备用率',
        'インバランス':         '不平衡',
        'JKM LNG 価格':        'JKM LNG 价格',
        '全国天気':             '全国天气',
        '発電稼働状況':         '发电运行状况',
        '通知センター':         '通知中心',
        '通知センター ({0})':  '通知中心 ({0})',
        '設定':                 '设置',
        'システムログ':         '系统日志',
        # Navigation groups / short labels
        '⚡  電力データ':       '⚡  电力数据',
        '🔵  Google':           '🔵  Google',
        '🛠  ツール':           '🛠  工具',
        'バグ':                 '错误',
        'ログ':                 '日志',
        # New widget tabs
        'バグレポート':         '错误报告',
        'AI チャット':          'AI 聊天',
        'テキストメモ':         '文本备忘',
        # Network / theme
        '🟢 オンライン':        '🟢 在线',
        '🔴 オフライン':        '🔴 离线',
        '☀️ ライトモード':      '☀️ 浅色模式',
        '🌙 ダークモード':      '🌙 深色模式',
        # Tray / dialogs
        '開く (Open)':          '打开',
        '完全に終了 (Quit)':    '退出',
        'LEE電力モニター':      'LEE 电力监控',
        'LEE電力モニター - バックグラウンド実行中':
            'LEE 电力监控 - 后台运行中',
        '終了の確認':           '确认退出',
        'アプリケーションを完全に終了しますか？\nそれともトレイ（バックグラウンド）に最小化しますか？':
            '是否完全退出应用？\n还是最小化到系统托盘（后台）？',
        'トレイに最小化':       '最小化到托盘',
        '完全に終了':           '完全退出',
        'キャンセル':           '取消',
        'バックグラウンドで実行中です。\nアイコンをダブルクリックで開きます。':
            '正在后台运行。\n双击托盘图标可打开应用。',
        'ネットワーク接続が切断されました。自動更新を一時停止します。':
            '网络连接已断开。自动更新已暂停。',
        # Settings - group headers
        '⚙️ 設定 (Settings)':              '⚙️ 设置',
        '⚠️ アラートしきい値設定':           '⚠️ 警报阈值设置',
        '⏱️ 自動更新間隔 (分)':             '⏱️ 自动更新间隔（分钟）',
        '💾 データ寿命管理 (バックアップと削除)': '💾 数据生命周期（备份与删除）',
        '💻 システム設定':                   '💻 系统设置',
        '🌍 言語設定 (Language)':           '🌍 语言设置',
        # Settings - group header (inline keys used in _make_group calls)
        'アラートしきい値':                 '警报阈值',
        '自動更新間隔':                     '自动更新间隔',
        'データ管理':                       '数据管理',
        'システム':                         '系统',
        '言語 (Language)':                  '语言 (Language)',
        # Settings - form labels
        'インバランス単価 警告:':    '不平衡单价警告:',
        '電力予備率 警告 (赤):':     '电力备用率警告（红）:',
        '電力予備率 注意 (黄):':     '电力备用率提醒（黄）:',
        'インバランス単価:':         '不平衡:',
        '電力予備率:':               '备用率:',
        '全国天気予報:':             '天气预报:',
        '発電停止状況 (HJKS):':      '发电状况（HJKS）:',
        'JKM LNG 価格:':            'JKM LNG:',
        'データの保持期間:':         '数据保留期限:',
        '表示言語:':                 '显示语言:',
        # Settings - buttons / suffixes / toasts
        '今すぐ古いデータを整理':                   '立即整理旧数据',
        'Windows 起動時にバックグラウンドで自動実行する': '开机时自动在后台运行',
        '設定を保存':                               '保存设置',
        '初期化':                                   '重置',
        '🔄 初期化':                                '🔄 重置',
        '保存しました':                             '已保存',
        '✅ 保存しました':                           '✅ 已保存',
        '変更がありません':                          '无更改',
        '整理中...':                                '处理中...',
        '変更は再起動後に適用されます':              '更改将在重启后生效',
        ' 円': ' 日元',  '  円': '  日元',
        ' %': ' %',     '  %': '  %',
        ' 日': ' 天',   '  日': '  天',
        '  分': '  分钟',
        '  件': '  条',
        # Settings - message boxes
        '確認':     '确认',
        '完了':     '完成',
        'エラー':   '错误',
        '設定を初期値に戻しますか？':
            '将设置重置为默认值？',
        '保持期間({0}日)より古いデータを\nバックアップして削除しますか？':
            '备份并删除超过 {0} 天的旧数据？',
        '古いデータのバックアップと削除が完了しました。\n(保存先: backups フォルダ)':
            '旧数据备份和删除已完成。\n（保存位置：backups 文件夹）',
        '処理中にエラーが発生しました:':
            '处理过程中发生错误：',
        # Settings - tooltips
        'インバランス単価がこの値を超過した場合、警告を通知します。':
            '不平衡单价超过此值时发出警告通知。',
        '電力予備率がこの値を下回った場合、赤色の警告を通知します。':
            '电力备用率低于此值时发出红色警告通知。',
        '電力予備率がこの値を下回った場合、黄色の注意を通知します。':
            '电力备用率低于此值时发出黄色提醒通知。',
        'インバランス単価のデータ取得間隔（分）':   '不平衡单价获取间隔（分钟）',
        '電力予備率のデータ取得間隔（分）':         '电力备用率获取间隔（分钟）',
        '全国天気予報のデータ取得間隔（分）':        '天气预报获取间隔（分钟）',
        '発電停止状況(HJKS)のデータ取得間隔（分）': '发电状况获取间隔（分钟）',
        'JKM LNG 価格のデータ取得間隔（分）':       'JKM LNG价格获取间隔（分钟）',
        'この日数を超えた古いデータは自動的にバックアップされ、メインDBから削除されます。':
            '超过此天数的旧数据将自动备份并从主数据库中删除。',
        '今すぐ手動で古いデータのバックアップと削除処理を実行します。':
            '立即手动执行旧数据的备份和删除操作。',
        'PC起動時、自動的にバックグラウンド（トレイアイコン）で実行します。':
            'PC启动时自动在后台（托盘图标）运行。',
        # Bug report widget
        'バグレポート送信':             '提交错误报告',
        '発生した問題の概要:':          '问题概要：',
        '詳細な説明・再現手順:':        '详细描述 / 复现步骤：',
        '添付ログ (自動取得):':         '附件日志（自动获取）：',
        '送信中...':                    '发送中...',
        '送信':                         '发送',
        '送信  →':                      '发送  →',
        'クリア':                       '清除',
        'レポートを送信しました。':     '错误报告已发送。',
        '送信に失敗しました:':          '发送失败：',
        '概要を入力してください。':     '请输入问题概要。',
        # AI chat widget
        'メッセージを入力...':          '请输入消息...',
        'メッセージを入力...  (Enter 送信 / Shift+Enter 改行)':
            '请输入消息...  (Enter 发送 / Shift+Enter 换行)',
        '送信 (Enter)':                 '发送 (Enter)',
        'チャット履歴をクリア':         '清除聊天记录',
        'AI アシスタント':              'AI 助手',
        '考え中':                       '思考中',
        '考え中...':                    '思考中...',
        'AIサービスに接続できません。': '无法连接到 AI 服务。',
        'モデル:':                      '模型：',
        # Bug report - field labels
        '分類':                         '分类',
        '概要':                         '概要',
        '詳細・再現手順  (任意)':        '详细内容 / 复现步骤  （可选）',
        '例: ダッシュボードが起動時にクラッシュする':
            '例：仪表板在启动时崩溃',
        'ログ (自動取得)':              '日志  （自动获取）',
        # Text memo widget
        'テキストメモ管理':             '文本备忘管理',
        '新規追加':                     '新建',
        '削除':                         '删除',
        'コピー':                       '复制',
        'タイトル:':                    '标题：',
        'タグ:':                        '标签：',
        '内容:':                        '内容：',
        '保存':                         '保存',
        'クリップボードにコピーしました': '已复制到剪贴板',
        '検索...':                      '搜索...',
        'メモが見つかりません':         '未找到备忘',
        # Text memo - placeholders / status
        'タイトルを入力...':            '请输入标题...',
        'タグ (カンマ区切り)  例: AI, プロンプト':
            '标签（逗号分隔）  例：AI, 提示词',
        'テキスト・プロンプトをここに入力...\n「コピー」ボタンでクリップボードへコピーできます。':
            '在此输入文本或提示词...\n点击"复制"按钮可复制到剪贴板。',
        '新しいメモ':                   '新建备忘',
        '無題のメモ':                   '无标题备忘',
        '削除の確認':                   '确认删除',
        '「{0}」を削除しますか？':      '确定删除"{0}"吗？',
        '削除しました。':               '已删除。',
        '作成: {0}':                    '创建时间：{0}',
        'タグ: {0}':                    '标签：{0}',
        '{0} 件':                       '{0} 条',
        '{0} / {1} 件':                 '{0} / {1} 条',
        '{0} 文字':                     '{0} 字',
        # Startup splash
        '起動中...':                    '启动中...',
        # AI chat welcome / API errors
        '⚠️ API キーが取得できませんでした。\nアプリを再インストールするか、管理者にお問い合わせください。':
            '⚠️ 无法获取 API 密钥。\n请重新安装应用或联系管理员。',
        '⏳ 全APIのリクエスト上限に達しました。\n{0}秒後に再試行できます。（無料枠リセット: UTC 0:00）':
            '⏳ 所有 API 请求已达上限。\n{0} 秒后可重试。（免费额度重置时间：UTC 0:00）',
        '日本の電力市場・インバランス単価・LNG価格などについて質問できます。':
            '您可以询问有关日本电力市场、不平衡单价、LNG价格等方面的问题。',
        '試してみてください:':          '试试这些问题：',
        'インバランス単価の最近の動向を教えて': '告诉我最近的不平衡单价动态',
        '電力予備率が低下するとどうなりますか？': '电力备用率下降会发生什么？',
        'LNG価格と電力価格の関係を説明して': '请解释LNG价格与电价的关系',
        # Bug report categories
        '🐛  バグ・エラー':             '🐛  程序错误',
        '🖥️  UI表示の問題':             '🖥️  界面显示问题',
        '📡  データ取得エラー':         '📡  数据获取错误',
        '⚡  パフォーマンス問題':        '⚡  性能问题',
        '💡  機能要望':                 '💡  功能建议',
        '❓  その他':                   '❓  其他',
        '1. アプリを起動する\n2. ○○をクリックする\n3. エラーが発生する':
            '1. 启动应用\n2. 点击○○\n3. 发生错误',
        '[ログ読込失敗: {0}]':          '[日志加载失败：{0}]',
        'レポートを送信しました。ありがとうございます。': '报告已发送，感谢您的反馈！',
        '【分類】':                     '【分类】',
        '【概要】':                     '【概要】',
        '【詳細・再現手順】\n':         '【详细信息·复现步骤】\n',
        '(未記入)':                     '（未填写）',
        '【ログ (直近 {0} 行)】\n':     '【日志（最近 {0} 行）】\n',
        # Settings AI section labels / tooltips
        'フォールバックモデル:':        '备用模型：',
        '応答の温度:':                  '回复温度：',
        '最大トークン数:':              '最大 Token 数：',
        '会話履歴の保持数:':            '对话历史保留数：',
        'Gemini 3.1 Flash Lite の次に試みるフォールバックモデル。\n通常は gemini-2.5-flash (推奨) で十分です。':
            'Gemini 3.1 Flash Lite 之后尝试的备用模型。\n通常 gemini-2.5-flash（推荐）已足够。',
        'AIの回答の多様性を制御します。\n低い値 (0.1〜0.5): 正確・一貫した回答\n高い値 (1.0〜2.0): 多様・創造的な回答\n推奨: 0.7':
            '控制AI回复的多样性。\n低值 (0.1~0.5)：精确、一致的回答\n高值 (1.0~2.0)：多样、有创意的回答\n推荐：0.7',
        '一回の回答で生成する最大文字数を制御します。\n長い回答が必要な場合は 4096 を選択。\n推奨: 2,048':
            '控制每次回答生成的最大 Token 数。\n需要较长回答时请选择 4096。\n推荐：2,048',
        'AIに渡す過去の会話メッセージ数の上限です。\n多いほどコンテキストが保たれますが API 使用量が増加します。\n推奨: 20':
            '传递给AI的历史对话消息数上限。\n越多越能保持上下文，但会增加API用量。\n推荐：20',
        '※ 優先順位: Gemini 3.1 Flash Lite → 上記モデル → Groq (llama-3.3-70b)':
            '※ 优先级：Gemini 3.1 Flash Lite → 上述模型 → Groq (llama-3.3-70b)',
        # Common status messages
        '更新中...':                    '更新中...',
        '更新完了':                     '已更新',
        '更新失敗':                     '更新失败',
        'データなし':                   '无数据',
        '読込エラー':                   '读取错误',
        '待機中':                       '待机',
        '待機中...':                    '待机...',
        'データ待機中...':              '等待数据...',
        'データ取得中...':              '获取数据中...',
        '取得完了':                     '已获取',
        '取得失敗':                     '获取失败',
        # Dashboard card titles / values
        '総合ダッシュボード':            '综合仪表板',
        '本日の最大インバランス':        '今日最大不平衡',
        '本日の最低電力予備率':          '今日最低备用率',
        '全国の天気':                    '全国天气',
        '最新 JKM LNG 価格':            '最新 JKM LNG 价格',
        '本日の発電稼働容量':            '今日发电运行容量',
        '-- 円':                        '-- 日元',
        '本日のデータなし':             '今日无数据',
        '{0} (前日比 {1} {2}%)':        '{0}  ({1}{2}%，较前日)',
        '-- USD':                       '-- USD',
        '停止中: {0} MW':               '停止中：{0} MW',
        'コマ {0} / {1}':               '时段 {0} / {1}',
        # Error / dialog messages
        '通知':                         '通知',
        'データの取得中にエラーが発生しました:\n{0}':
            '获取数据时发生错误：\n{0}',
        '保存するデータがありません。':  '没有可保存的数据。',
        'CSVファイルとして保存しました。\nExcelで開くことができます。':
            '已保存为 CSV 文件。\n可在 Excel 中打开。',
        '保存に失敗しました:\n{0}':     '保存失败：\n{0}',
        'DBにデータがありません。「Yahoo Finance から取込」で取得してください。':
            '数据库中无数据，请通过"从 Yahoo Finance 导入"获取。',
        'DBエラー: {0}':                '数据库错误：{0}',
        # Notification / alert messages
        '...他 {0}件の警告があります':  '...还有 {0} 条警告',
        '⚠ 予備率警告 (計 {0}件) - {1}':  '⚠ 备用率警告（共 {0} 条）- {1}',
        '⚠ インバランス 警告 (計 {0}件) - {1}': '⚠ 不平衡警告（共 {0} 条）- {1}',
        '本日のデータに予備率{0}%以下のコマが 【計 {1}件】 発生しています。':
            '今日数据中有 {1} 个时段备用率 ≤{0}%。',
        '本日データに{0}円超の単価が 【計 {1}件】 発生しました。':
            '今日数据中有 {1} 个时段单价 >{0} 日元。',
        # Clipboard messages
        'グラフ画像をクリップボードにコピーしました。\n(Excel等に貼り付け可能です)':
            '图表已复制到剪贴板。\n（可粘贴到 Excel 等应用中）',
        'グラフ画像をクリップボードにコピーしました。':
            '图表已复制到剪贴板。',
        # Weather status / detail
        '天気データを取得中...':         '正在获取天气数据...',
        '📍 {0} の詳細天気 (7日間)':    '📍 {0} 详细天气（7天）',
        # WMO weather code strings
        '晴れ': '晴', '概ね晴れ': '大部分晴', '一部曇り': '多云',
        '曇り': '阴', '霧': '雾', '霧氷': '冻雾',
        '弱い霧雨': '小毛毛雨', '霧雨': '毛毛雨', '強い霧雨': '大毛毛雨',
        '弱い着氷性霧雨': '轻冻毛毛雨', '強い着氷性霧雨': '重冻毛毛雨',
        '弱い雨': '小雨', '雨': '雨', '強い雨': '大雨',
        '弱い着氷性の雨': '轻冻雨', '強い着氷性の雨': '重冻雨',
        '弱い雪': '小雪', '雪': '雪', '強い雪': '大雪',
        '霧雪': '霰雪', '弱い小雨': '小阵雨', '小雨': '阵雨',
        '激しい小雨': '强阵雨', '弱い雪降る': '小阵雪', '強い雪降る': '大阵雪',
        '雷雨': '雷阵雨', '弱い雹の雷雨': '雷雨伴小冰雹',
        '強い雹の雷雨': '雷雨伴大冰雹', '不明': '未知',
        # HJKS plot / tooltip labels
        '稼働可能容量 (MW)':            '可用容量 (MW)',
        '停止中':                       '停止中',
        '【発電方式別】':               '【发电方式】',
        '【選択エリア別】':             '【选择区域】',
        # Imbalance DB / no-data
        '{0} のデータがありません。\n(DBに保存されている期間: {1} ~ {2})':
            '{0} 无数据。\n（数据库保存期间：{1} ~ {2}）',
        'DBに有効なデータがありません。': '数据库中无有效数据。',
        # Log viewer errors
        'ログの読み込みに失敗しました: {0}':   '日志加载失败：{0}',
        '予期せぬエラーが発生しました: {0}':   '发生意外错误：{0}',
        # Log viewer UI labels
        'システムログ (System Logs)':          '系统日志',
        'すべての機能':                        '全部模块',
        'システム起動・終了':                  '应用启动·退出',
        '発電停止状況 (HJKS)':                 '发电状况（HJKS）',
        '全国天気予報':                        '全国天气预报',
        '電力予備率 (OCCTO)':                  '电力备用率（OCCTO）',
        'すべてのログレベル':                  '全部级别',
        'ログ消去':                            '清除日志',
        '手動更新':                            '手动刷新',
        # Standalone units / terms
        'コマ': '时段',
        '円': '日元',
        # Japan region names (display only)
        '北海道': '北海道', '東北': '东北', '東京': '东京',
        '中部': '中部', '北陸': '北陆', '関西': '关西',
        '中国': '中国地方', '四国': '四国', '九州': '九州', '沖縄': '冲绳',
        '北海道 (札幌)': '北海道（札幌）', '東北 (仙台)': '东北（仙台）',
        '中部 (名古屋)': '中部（名古屋）', '北陸 (新潟)': '北陆（新泻）',
        '関西 (大阪)': '关西（大阪）', '中国 (広島)': '中国地方（广岛）',
        '四国 (高松)': '四国（高松）', '九州 (福岡)': '九州（福冈）',
        # Generation methods (display only)
        '火力（石炭）': '燃煤火力', '火力（ガス）': '燃气火力', '火力（石油）': '燃油火力',
        '原子力': '核能', '水力': '水力', 'その他': '其他',
        # Power reserve widget
        'エリア別 予備率 (5分自動更新)':       '各地区备用率（5分钟自动更新）',
        'Excel(CSV) 保存':                     '保存 Excel（CSV）',
        'CSV保存':                             '保存 CSV',
        # HJKS widget
        '発電所 稼働可能容量 推移 (HJKS)':    '发电站可用容量变化（HJKS）',
        'データ更新':                          '更新数据',
        'グラフ画像をコピー':                  '复制图表图像',
        'ビュー初期化':                        '重置视图',
        '表示エリア選択':                      '选择显示区域',
        '全選択':                              '全选',
        '全解除':                              '取消全选',
        '【発電方式 凡例】':                   '【发电方式图例】',
        # Weather widget
        '全国天気予報 (Open-Meteo)':           '全国天气预报（Open-Meteo）',
        '更新 (再取得)':                       '刷新（重新获取）',
        '👈 左側の地域を選択してください':     '👈 请在左侧选择地区',
        '天気':                                '天气',
        '最高気温':                            '最高气温',
        '最低気温':                            '最低气温',
        '降水確率':                            '降水概率',
        '降水量':                              '降水量',
        '雲量':                                '云量',
        '最大風速':                            '最大风速',
        # JKM widget
        'JKM LNG スポット価格 (USD/MMBtu)':   'JKM LNG 现货价格（USD/MMBtu）',
        'Yahoo Finance から取込':              '从 Yahoo Finance 导入',
        '表示期間:':                           '显示区间：',
        '〜':                                  '至',
        '表示':                                '显示',
        '終値\n(USD/MMBtu)':                   '收盘价\n(USD/MMBtu)',
        '高値':                                '最高价',
        '安値':                                '最低价',
        '前日比(%)':                           '涨跌幅(%)',
        '最新':                                '最新',
        '表示: {0}件  最新: {1} USD/MMBtu  ({2})':
            '显示：{0} 条  最新：{1} USD/MMBtu  ({2})',
        '日付':                                '日期',
        '終値':                                '收盘价',
        '開始日は終了日以前である必要があります。':
            '开始日期必须早于或等于结束日期。',
        # Imbalance widget
        'インバランス単価':                    '不平衡单价',
        '今月分 DB更新':                       '更新数据库（本月）',
        '余剰インバランス料金単価':            '余量不平衡单价',
        '不足インバランス料金単価':            '缺量不平衡单价',
        '表表示':                              '显示表格',
        'グラフ表示':                          '显示图表',
        'マップ表示':                          '显示地图',
        'マップ画像をコピー':                  '复制地图图像',
        '予備率ヒートマップ':                  '备用率热力图',
        '  エリア':                            '  区域',
        'DB更新中...':                         '数据库更新中...',
        'データ読込中...':                     '数据加载中...',
        '単価 [円/kWh]':                       '单价 [日元/kWh]',
        '時刻コード':                          '时段编号',
        'エリア: {0}\n時刻: {1}\n単価: {2} 円': '区域：{0}\n时段：{1}\n单价：{2} 日元',
        # Google Calendar widget
        'Google カレンダー':                    'Google 日历',
        'イベントを編集':                       '编辑日程',
        'タイトル (必須)':                      '标题（必填）',
        'タイトル:':                            '标题：',
        'カレンダー:':                          '日历：',
        '終日イベント':                         '全天日程',
        '開始:':                               '开始：',
        '終了:':                               '结束：',
        'メモ・詳細 (任意)':                   '备注·详情（可选）',
        'メモ:':                               '备注：',
        '新規イベント':                         '新建日程',
        '読込中...':                           '加载中...',
        '{0}件のイベント':                      '{0} 个日程',
        'イベントなし':                         '无日程',
        '  イベントなし':                       '  无日程',
        'カレンダー':                           '日历',
        '(タイトルなし)':                       '（无标题）',
        '終日':                                 '全天',
        '編集':                                 '编辑',
        'Google 認証が必要です':                '需要 Google 认证',
        '設定画面から Google アカウントで認証してください。':
            '请在设置界面进行 Google 账号认证。',
        'タイトルを入力してください。':         '请输入标题。',
        'イベント詳細':                         '日程详情',
        '閉じる':                               '关闭',
        '🔄 更新':                             '🔄 刷新',
        # Gmail widget
        'Gmail':                                'Gmail',
        '受信トレイ':                           '收件箱',
        'スター付き':                           '已加星标',
        '重要':                                 '重要',
        '送信済み':                             '已发送',
        '迷惑メール':                           '垃圾邮件',
        'ゴミ箱':                               '垃圾桶',
        '📧  メールを選択してください':         '📧  请选择邮件',
        'ブラウザで開く':                        '在浏览器中打开',
        '(件名なし)':                           '（无主题）',
        '(本文なし)':                           '（无正文）',
        'さらに読み込む':                       '加载更多',
        'アラームをオフ':                        '关闭通知',
        'アラームをオン':                        '开启通知',
        'ラベル表示設定':                        '标签显示设置',
        'すべて表示':                            '全部显示',
        'すべて非表示':                          '全部隐藏',
        'すべて既読':                            '全部标为已读',
        'このラベルにメールはありません':         '此标签下没有邮件',
        '表示するラベルを選択してください。ドラッグで並び替え可能です。':
            '请选择要显示的标签。可拖拽调整顺序。',
        '適用':                                  '应用',
        '処理中...':                             '处理中...',
        # Settings - Google integration
        '🔗   Google 連携':                     '🔗   Google 集成',
        'Google 連携':                          'Google 集成',
        'Google アカウントで認証':              '使用 Google 账号认证',
        '認証済 ✅':                            '已认证 ✅',
        '未認証':                               '未认证',
        '認証を解除':                           '撤销认证',
        'カレンダー 更新間隔:':                 '日历更新间隔：',
        'Gmail 更新間隔:':                      'Gmail 更新间隔：',
        'メール取得件数:':                      '邮件获取数量：',
        'Google カレンダー:':                   'Google 日历：',
        'Gmail:':                               'Gmail:',
        'Client ID と Client Secret は Google Cloud Console から取得できます。\n認証後はカレンダーと Gmail が利用可能になります。':
            '可从 Google Cloud Console 获取 Client ID 和 Client Secret。\n认证后即可使用日历和 Gmail 功能。',
        # JEPX Spot Market widget
        'JEPXスポット平均価格':                 'JEPX现货均价',
        '明日':                                 '明天',
        '平均':                                 '均',
        '最高':                                 '最高',
        '最低':                                 '最低',
        'スポット市場':                         '现货市场',
        '当日スポット価格':                     '当日现货价格',
        '日次平均推移':                         '日均价趋势',
        '月次平均推移':                         '月均价趋势',
        '年次平均推移':                         '年均价趋势',
        '曜日別日次推移':                       '按星期日均趋势',
        '月曜日': '周一', '火曜日': '周二', '水曜日': '周三',
        '木曜日': '周四', '金曜日': '周五', '土曜日': '周六', '日曜日': '周日',
        '期間:':                                '区间：',
        '今年度':                               '本财年',
        '曜日:':                                '星期：',
        '年度:':                                '财年：',
        '更新':                                 '刷新',
        'ビューリセット':                       '重置视图',
        '表':                                   '表格',
        'グラフ':                               '图表',
        'グラフコピー':                         '复制图表',
        'エリア:':                              '区域：',
        '今日':                                 '今天',
        '価格 (円/kWh)':                        '价格（日元/kWh）',
        '時刻':                                 '时刻',
        '年月':                                 '年月',
        '年':                                   '年份',
        'データ取得中…':                        '获取数据中…',
        'データ取得完了':                       '数据获取完成',
        '当日データ取得完了 ({0})':             '当日数据获取完成（{0}）',
        '当日データ未公開 — 次回再試行':        '当日数据未发布 — 下次重试',
        '{0}年 データ取得中… ({1}/{2})':        '正在获取 {0} 年数据… ({1}/{2})',
        'エリアが選択されていません':           '未选择区域',
        'データ取得エラー: {0}':               '数据获取错误：{0}',
        '{0} ({1} 〜 {2}): {3} 件':            '{0}（{1} 至 {2}）：{3} 条',
        '{0} 件のデータを表示中':              '正在显示 {0} 条数据',
        'グラフをクリップボードにコピーしました': '图表已复制到剪贴板',
        'エラー: {0}':                          '错误：{0}',
        'X':                                    'X',
        # Google notification (tray)
        '📧 新着メール ({0}件) - {1}':          '📧 新邮件（{0} 封）- {1}',
    },
}


def tr(text: str) -> str:
    """テキストを現在の言語に翻訳して返す。翻訳が見つからない場合はそのまま返す。"""
    if _state.lang == 'ja':
        return text
    return TRANSLATIONS.get(_state.lang, {}).get(text, text)


def set_language(lang: str) -> None:
    """言語コードを設定する (ja / en / ko / zh)。不正な値は 'ja' にフォールバック。"""
    _state.lang = lang


def get_language() -> str:
    """現在の言語コードを返す"""
    return _state.lang


def init_language() -> None:
    """設定ファイルから言語を読み込み。'auto' の場合はシステムロケールで推定。"""
    try:
        from app.core.config import load_settings
        lang = load_settings().get('language', 'auto')
    except (OSError, ValueError) as e:
        logger.warning(f"言語設定の読み込みに失敗しました。'auto' を使用します: {e}")
        lang = 'auto'

    if lang == 'auto':
        lang = _detect_system_language()

    set_language(lang)
    logger.debug(f"Language initialized: {_state.lang}")


def _detect_system_language() -> str:
    """システムロケールから言語コードを推定する"""
    try:
        import locale
        sys_locale = locale.getdefaultlocale()[0] or ''
        for prefix, code in (('ja', 'ja'), ('ko', 'ko'), ('zh', 'zh'), ('en', 'en')):
            if sys_locale.startswith(prefix):
                return code
    except (ValueError, LookupError):
        pass
    return 'ja'
