class ThemePalette:
    """アプリ全体の背景色パレット。散在していたハードコードを一元管理します。"""

    # ── ダークテーマ背景 ──────────────────────────────────────────────────────
    BG_PRIMARY_DARK   = "#1e1e1e"   # メインウィンドウ背景
    BG_SECONDARY_DARK = "#252526"   # カード・パネル背景
    BG_TERTIARY_DARK  = "#2d2d30"   # ホバー・強調背景
    BG_INPUT_DARK     = "#3c3c3c"   # 入力フィールド背景

    # ── ライトテーマ背景 ─────────────────────────────────────────────────────
    BG_PRIMARY_LIGHT   = "#f4f4f4"
    BG_SECONDARY_LIGHT = "#ffffff"
    BG_TERTIARY_LIGHT  = "#f0f0f0"
    BG_INPUT_LIGHT     = "#ffffff"

    @staticmethod
    def bg_primary(is_dark: bool) -> str:
        return ThemePalette.BG_PRIMARY_DARK if is_dark else ThemePalette.BG_PRIMARY_LIGHT

    @staticmethod
    def bg_secondary(is_dark: bool) -> str:
        return ThemePalette.BG_SECONDARY_DARK if is_dark else ThemePalette.BG_SECONDARY_LIGHT

    @staticmethod
    def bg_tertiary(is_dark: bool) -> str:
        return ThemePalette.BG_TERTIARY_DARK if is_dark else ThemePalette.BG_TERTIARY_LIGHT


class UIColors:
    """앱 전체에서 사용되는 하드코딩 색상을 중앙 집중화합니다."""

    # --- 아이콘 틴팅 색상 ---
    ICON_TINT_DARK  = "#cccccc"
    ICON_TINT_LIGHT = "#555555"

    # --- 기본 텍스트 색상 ---
    TEXT_PRIMARY_DARK    = "#d4d4d4"
    TEXT_PRIMARY_LIGHT   = "#333333"
    # WCAG AA 기준 4.5:1 이상 대비도
    # #bbbbbb on #1e1e1e ≈ 8.0:1 (AAA), #555555 on #f4f4f4 ≈ 6.6:1 (AA)
    TEXT_SECONDARY_DARK  = "#bbbbbb"
    TEXT_SECONDARY_LIGHT = "#555555"
    TEXT_EMPHASIS_DARK   = "#eeeeee"
    TEXT_EMPHASIS_LIGHT  = "#111111"

    # --- 汎用テキスト色 (カード値・本文テキストの最も一般的な色) ---
    TEXT_DEFAULT_DARK  = "#eeeeee"
    TEXT_DEFAULT_LIGHT = "#333333"

    # --- テーマ共通の補助テキスト色 ---
    TEXT_MUTED = "#888888"

    # --- 강조 색상 ---
    ACCENT_DARK  = "#094771"
    ACCENT_LIGHT = "#1565c0"

    # --- 네트워크 상태 색상 (테마 무관 시맨틱 색상) ---
    ONLINE_COLOR  = "#4caf50"
    OFFLINE_COLOR = "#ff5252"

    @staticmethod
    def icon_tint(is_dark: bool) -> str:
        return UIColors.ICON_TINT_DARK if is_dark else UIColors.ICON_TINT_LIGHT

    @staticmethod
    def text_primary(is_dark: bool) -> str:
        return UIColors.TEXT_PRIMARY_DARK if is_dark else UIColors.TEXT_PRIMARY_LIGHT

    @staticmethod
    def text_secondary(is_dark: bool) -> str:
        return UIColors.TEXT_SECONDARY_DARK if is_dark else UIColors.TEXT_SECONDARY_LIGHT

    @staticmethod
    def text_emphasis(is_dark: bool) -> str:
        return UIColors.TEXT_EMPHASIS_DARK if is_dark else UIColors.TEXT_EMPHASIS_LIGHT

    @staticmethod
    def text_default(is_dark: bool) -> str:
        """カード値・本文テキストに最も広く使われる汎用テキスト色。"""
        return UIColors.TEXT_DEFAULT_DARK if is_dark else UIColors.TEXT_DEFAULT_LIGHT

    @staticmethod
    def get_imbalance_alert_colors(is_dark: bool, level: int):
        """인밸런스 단가 레벨: 1(Normal) ~ 5(Critical)"""
        if is_dark:
            return {
                1: ("#113344", "#d4d4d4"), 2: ("#1e401e", "#d4d4d4"),
                3: ("#804000", "#d4d4d4"), 4: ("#801515", "#d4d4d4"), 5: ("#5c1111", "#ffffff"),
            }.get(level, ("transparent", "#d4d4d4"))
        else:
            return {
                1: ("#e1f5fe", "#333333"), 2: ("#dcf0dc", "#333333"),
                3: ("#fff0cc", "#333333"), 4: ("#ffdddd", "#333333"), 5: ("#ffcccc", "#ff0000"),
            }.get(level, ("transparent", "#333333"))

    @staticmethod
    def get_reserve_alert_colors(is_dark: bool, status: str):
        """예비율 경고 상태"""
        if is_dark:
            return {
                'low': ("#7f1d1d", "#ffffff"), 'warning': ("#785b0d", "#ffffff"), 'past': ("#2d2d30", "#777777")
            }.get(status, ("transparent", "#d4d4d4"))
        else:
            return {
                'low': ("#ff6666", "#000000"), 'warning': ("#ffeb3b", "#000000"), 'past': ("#e0e0e0", "#888888")
            }.get(status, ("transparent", "#333333"))

    @staticmethod
    def get_panel_colors(is_dark: bool):
        """패널 및 リスト 아이템, 툴팁 등에 사용되는 배경/텍스트 색상 모듈화"""
        if is_dark:
            return {"bg": "#252526", "border": "#3e3e42", "text": "#d4d4d4", "text_dim": "#888888", "hover": "#333333"}
        else:
            return {"bg": "#fcfcfc", "border": "#cccccc", "text": "#333333", "text_dim": "#666666", "hover": "#e8e8e8"}

    @staticmethod
    def get_graph_colors(is_dark: bool):
        """PyQtGraph 배경 및 축, 그리드에 사용되는 색상 모듈화"""
        if is_dark:
            return {"bg": "#1e1e1e", "axis": "#555555", "text": "#aaaaaa"}
        else:
            return {"bg": "#ffffff", "axis": "#dddddd", "text": "#666666"}

    @staticmethod
    def get_chat_colors(is_dark: bool) -> dict:
        """AI チャットウィジェットのバブル・アバター配色"""
        return {
            "user_bg":   "#0078d4",
            "user_fg":   "#ffffff",
            "asst_bg":   "#2a2d2e" if is_dark else "#e4e4e4",
            "asst_fg":   "#d4d4d4" if is_dark else "#1a1a1a",
            "avatar_bg": "#5c6bc0",
            "time_fg":   "#888888" if is_dark else "#aaaaaa",
        }

    @staticmethod
    def get_log_colors(is_dark: bool) -> dict:
        """システムログビューアに使用するログレベル別の配色"""
        if is_dark:
            return {
                "bg":      "#1e1e1e",
                "text":    "#d4d4d4",
                "error":   "#ff5555",
                "warning": "#ffb86c",
                "info":    "#8be9fd",
                "module":  "#bd93f9",
                "time":    "#777777",
            }
        else:
            return {
                "bg":      "#ffffff",
                "text":    "#333333",
                "error":   "#cc0000",
                "warning": "#e65100",
                "info":    "#1565c0",
                "module":  "#6a1b9a",
                "time":    "#888888",
            }


# ---------------------------------------------------------------------------
# タイポグラフィ定数
# フォントサイズを一元管理して UI 全体の一貫性を維持します。
# ---------------------------------------------------------------------------
class Typography:
    """アプリ全体のフォントサイズ定数"""
    DISPLAY = "32px"   # ダッシュボードカード 数値表示
    H1      = "18px"   # ページタイトル
    H2      = "15px"   # セクションタイトル / ウィジェットヘッダー
    BODY    = "13px"   # 本文・テーブル
    SMALL   = "11px"   # キャプション・補助テキスト
    BUTTON  = "12px"   # ボタンラベル
    CHART   = "9pt"    # グラフ軸ラベル (pyqtgraph は pt 単位)


def get_global_qss(theme: str) -> str:
    """
    앱 전체에서 공통으로 사용되는 커스텀 위젯들의 스타일시트(QSS)를 반환합니다.
    """
    is_dark = (theme == "dark")

    bc           = "#555555" if is_dark else "#cccccc"
    tc           = UIColors.text_primary(is_dark)
    primary_bg   = UIColors.ACCENT_DARK if is_dark else "#0d47a1"
    primary_hover= "#0b5a8e" if is_dark else UIColors.ACCENT_LIGHT
    secondary_bg = "#444444" if is_dark else "#dddddd"
    secondary_hover = "#555555" if is_dark else "#cccccc"
    toast_color  = UIColors.ONLINE_COLOR if is_dark else "#388e3c"
    main_bg      = ThemePalette.bg_primary(is_dark)
    card_bg      = ThemePalette.bg_secondary(is_dark)
    card_hover   = ThemePalette.bg_tertiary(is_dark)
    grp_border   = "#303030" if is_dark else "#dedede"
    grp_title    = "#b0b0b0" if is_dark else "#444444"

    return f"""
    /* 앱 전체 공통 툴팁 스타일 */
    QToolTip {{
        background-color: {card_bg};
        color: {tc};
        border: 1px solid {bc};
        border-radius: 4px;
        padding: 5px;
    }}

    /* SettingsWidget - QGroupBox (배경 없음 → 자식 위젯 가시성 확보) */
    QGroupBox#settingsGroup {{
        font-weight: bold;
        border: 1px solid {grp_border};
        border-radius: 8px;
        margin-top: 14px;
        padding-top: 6px;
        color: {tc};
    }}
    QGroupBox#settingsGroup::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 14px;
        top: -1px;
        padding: 2px 8px;
        background-color: {main_bg};
        color: {grp_title};
        font-size: 12px;
        font-weight: bold;
        border-radius: 4px;
    }}

    /* 공통 버튼 액션 스타일 */
    QPushButton#primaryActionBtn {{
        font-weight: bold; background-color: {primary_bg}; color: white; border: none; padding: 8px; border-radius: 4px;
    }}
    QPushButton#primaryActionBtn:hover {{ background-color: {primary_hover}; }}

    QPushButton#secondaryActionBtn {{
        font-weight: bold; background-color: {secondary_bg}; color: {tc}; border: 1px solid {bc}; padding: 8px; border-radius: 4px;
    }}
    QPushButton#secondaryActionBtn:hover {{ background-color: {secondary_hover}; }}

    /* 공통 토스트 알림 라벨 */
    QLabel#successToast {{
        color: {toast_color};
        font-weight: bold;
    }}

    /* 설정 화면 체크박스 */
    QCheckBox#settingsCheckbox {{
        border: none; padding: 6px 10px; border-radius: 6px; background: transparent;
        color: {tc}; font-size: 13px;
    }}
    QCheckBox#settingsCheckbox:hover {{
        background-color: {card_hover};
    }}

    /* SummaryCard Dynamic Property 적용 (하드코딩 제거) */
    SummaryCard[theme="dark"] {{
        background-color: {ThemePalette.BG_SECONDARY_DARK};
        border: 1px solid #3e3e42;
        border-radius: 8px;
    }}
    SummaryCard[theme="dark"]:hover {{ background-color: {ThemePalette.BG_TERTIARY_DARK}; }}

    SummaryCard[theme="light"] {{
        background-color: {ThemePalette.BG_SECONDARY_LIGHT};
        border: 1px solid #dddddd;
        border-radius: 8px;
    }}
    SummaryCard[theme="light"]:hover {{ background-color: #f4f8ff; }}
    """
