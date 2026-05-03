# =============================================================================
# Phase 0 — 디자인 토큰 시스템 (handoff/01-design-tokens.md 기준)
# =============================================================================
from PySide6.QtCore import QObject, Signal

# ── 인디케이터 컬러 (라이트/다크 공통) ─────────────────────────────────────
_INDICATOR_TOKENS = {
    "c_power":        "#5B8DEF",
    "c_power_soft":   "#DCE7FB",
    "c_spot":         "#FF7A45",
    "c_spot_soft":    "#FFE4D6",
    "c_imb":          "#F25C7A",
    "c_imb_soft":     "#FFE0E6",
    "c_jkm":          "#F4B740",
    "c_jkm_soft":     "#FFEFD0",
    "c_weather":      "#2EC4B6",
    "c_weather_soft": "#D2F4F0",
    "c_hjks":         "#A78BFA",
    "c_hjks_soft":    "#EBE3FE",
    "c_cal":          "#34C759",
    "c_cal_soft":     "#DAF6E1",
    "c_mail":         "#EA4335",
    "c_mail_soft":    "#FCE0DD",
    "c_ai":           "#5856D6",
    "c_ai_soft":      "#E1E0F8",
    "c_memo":         "#FFCC00",
    "c_memo_soft":    "#FFF4C2",
    "c_notice":       "#FF9500",
    "c_notice_soft":  "#FFE7C7",
    # 시맨틱 (테마 공통)
    "c_ok":    "#30D158",
    "c_warn":  "#FF9F0A",
    "c_bad":   "#FF453A",
    "c_info":  "#0A84FF",
    "accent":  "#FF7A45",
    # 스페이싱
    "s1": "4",  "s2": "8",  "s3": "12", "s4": "16",
    "s5": "20", "s6": "24", "s8": "32", "s10": "40", "s12": "48",
    # 라디우스
    "r_xs": "6",  "r_sm": "10", "r_md": "14", "r_lg": "20",
    "r_xl": "28", "r_2xl": "36", "r_pill": "999",
    # accent 위 텍스트
    "fg_on_accent": "#FFFFFF",
}

TOKENS_DARK: dict = {
    **_INDICATOR_TOKENS,
    # Surface
    "bg_app":       "#0A0B0F",
    "bg_surface":   "#14161C",
    "bg_surface_2": "#1B1E26",
    "bg_surface_3": "#232730",
    "bg_elevated":  "#1B1E26",
    "bg_input":     "#1B1E26",
    # Foreground
    "fg_primary":    "#F2F4F7",
    "fg_secondary":  "#A8B0BD",
    "fg_tertiary":   "#6B7280",
    "fg_quaternary": "#3D424D",
    # Border
    "border_subtle": "rgba(255,255,255,0.04)",
    "border":        "rgba(255,255,255,0.08)",
    "border_strong": "rgba(255,255,255,0.14)",
    # QSS 헬퍼 (기존 get_global_qss 호환)
    "scroll_handle":        "#555555",
    "scroll_hover":         "#777777",
    "grp_border":           "#303030",
    "grp_title":            "#b0b0b0",
    "primary_btn_bg":       "#0e639c",
    "primary_btn_hover":    "#0b5a8e",
    "secondary_btn_bg":     "#444444",
    "secondary_btn_hover":  "#555555",
    "toast_ok":             "#4caf50",
    "selection_bg":         "rgba(255,122,69,0.3)",
}

TOKENS_LIGHT: dict = {
    **_INDICATOR_TOKENS,
    # Surface
    "bg_app":       "#F5F6F8",
    "bg_surface":   "#FFFFFF",
    "bg_surface_2": "#F0F2F5",
    "bg_surface_3": "#E6E9EE",
    "bg_elevated":  "#FFFFFF",
    "bg_input":     "#FFFFFF",
    # Foreground
    "fg_primary":    "#0B1220",
    "fg_secondary":  "#4A5567",
    "fg_tertiary":   "#8A93A6",
    "fg_quaternary": "#C2C8D2",
    # Border
    "border_subtle": "rgba(11,18,32,0.06)",
    "border":        "rgba(11,18,32,0.10)",
    "border_strong": "rgba(11,18,32,0.18)",
    # QSS 헬퍼
    "scroll_handle":        "#c0c0c0",
    "scroll_hover":         "#a0a0a0",
    "grp_border":           "#dedede",
    "grp_title":            "#444444",
    "primary_btn_bg":       "#1a73e8",
    "primary_btn_hover":    "#1565c0",
    "secondary_btn_bg":     "#dddddd",
    "secondary_btn_hover":  "#cccccc",
    "toast_ok":             "#388e3c",
    "selection_bg":         "rgba(11,18,32,0.15)",
}


QSS_TEMPLATE = """
/* ── 공통 툴팁 ─────────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {bg_surface};
    color: {fg_primary};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 5px;
}}

/* ── SettingsWidget QGroupBox ──────────────────────────────────────────── */
QGroupBox#settingsGroup {{
    font-weight: bold;
    border: 1px solid {grp_border};
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 6px;
    color: {fg_primary};
}}
QGroupBox#settingsGroup::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    top: -1px;
    padding: 2px 8px;
    background-color: {bg_app};
    color: {grp_title};
    font-size: 12px;
    font-weight: bold;
    border-radius: 4px;
}}

/* ── 공통 액션 버튼 ────────────────────────────────────────────────────── */
QPushButton#primaryActionBtn {{
    font-weight: bold;
    background-color: {primary_btn_bg};
    color: white;
    border: none;
    padding: 8px;
    border-radius: 4px;
}}
QPushButton#primaryActionBtn:hover {{ background-color: {primary_btn_hover}; }}

QPushButton#secondaryActionBtn {{
    font-weight: bold;
    background-color: {secondary_btn_bg};
    color: {fg_primary};
    border: 1px solid {border};
    padding: 8px;
    border-radius: 4px;
}}
QPushButton#secondaryActionBtn:hover {{ background-color: {secondary_btn_hover}; }}

/* ── 토스트 알림 ────────────────────────────────────────────────────────── */
QLabel#successToast {{
    color: {toast_ok};
    font-weight: bold;
}}

/* ── 설정 체크박스 ─────────────────────────────────────────────────────── */
QCheckBox#settingsCheckbox {{
    border: none;
    padding: 6px 10px;
    border-radius: 6px;
    background: transparent;
    color: {fg_primary};
    font-size: 13px;
}}
QCheckBox#settingsCheckbox:hover {{ background-color: {bg_surface_2}; }}

/* ── SummaryCard (dynamic property) ───────────────────────────────────── */
SummaryCard[theme="dark"] {{
    background-color: {bg_surface};
    border: 1px solid {border_subtle};
    border-radius: 8px;
}}
SummaryCard[theme="dark"]:hover {{ background-color: {bg_surface_3}; }}
SummaryCard[theme="light"] {{
    background-color: {bg_surface};
    border: 1px solid {border};
    border-radius: 8px;
}}
SummaryCard[theme="light"]:hover {{ background-color: {bg_surface_2}; }}

/* ── QScrollBar ────────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {bg_app};
    width: 8px;
    border: none;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {scroll_handle};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {scroll_hover}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; border: none; }}
QScrollBar::add-page:vertical,  QScrollBar::sub-page:vertical  {{ background: none; }}

QScrollBar:horizontal {{
    background: {bg_app};
    height: 8px;
    border: none;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {scroll_handle};
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: {scroll_hover}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; border: none; }}
QScrollBar::add-page:horizontal,  QScrollBar::sub-page:horizontal  {{ background: none; }}

/* ── QComboBox ─────────────────────────────────────────────────────────── */
QComboBox {{
    background: {bg_input};
    color: {fg_primary};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 24px;
}}
QComboBox:hover {{ border-color: {accent}; }}
QComboBox::drop-down {{ border: none; width: 22px; subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox QAbstractItemView {{
    background: {bg_surface};
    color: {fg_primary};
    border: 1px solid {border};
    selection-background-color: {accent};
    selection-color: #ffffff;
    outline: none;
}}

/* ── QLineEdit ─────────────────────────────────────────────────────────── */
QLineEdit {{
    background: {bg_input};
    color: {fg_primary};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: {selection_bg};
}}
QLineEdit:focus {{ border-color: {accent}; }}
QLineEdit:disabled {{ color: {fg_tertiary}; background: {bg_surface}; }}

/* ── QTextEdit / QPlainTextEdit ────────────────────────────────────────── */
QTextEdit, QPlainTextEdit {{
    background: {bg_input};
    color: {fg_primary};
    border: 1px solid {border};
    border-radius: 4px;
    selection-background-color: {selection_bg};
}}
QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {accent}; }}

/* ── QTableWidget / QHeaderView ────────────────────────────────────────── */
QTableWidget {{
    background: {bg_app};
    color: {fg_primary};
    gridline-color: {border};
    border: 1px solid {border};
    border-radius: 4px;
}}
QTableWidget::item {{ padding: 4px; }}
QTableWidget::item:selected {{
    background: {accent};
    color: #ffffff;
}}
QHeaderView::section {{
    background: {bg_surface};
    color: {fg_primary};
    border: none;
    border-right: 1px solid {border};
    border-bottom: 1px solid {border};
    padding: 6px 8px;
    font-weight: bold;
    font-size: 12px;
}}
QHeaderView::section:first {{ border-left: none; }}

/* ── QDialog ────────────────────────────────────────────────────────────── */
QDialog {{
    background: {bg_surface};
}}
"""


def get_global_qss(theme: str = "dark") -> str:
    """토큰 딕셔너리를 QSS_TEMPLATE에 format()해서 반환."""
    tokens = TOKENS_DARK if theme == "dark" else TOKENS_LIGHT
    return QSS_TEMPLATE.format(**tokens)


class ThemeManager(QObject):
    """앱 전체 테마를 관리하는 싱글턴. set_theme() 호출 시 QSS를 교체하고 시그널을 emit."""

    theme_changed = Signal(str)
    _instance: "ThemeManager | None" = None

    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_theme = "dark"

    def set_theme(self, theme: str) -> None:
        self._current_theme = theme
        from PySide6.QtWidgets import QApplication
        from app.core.config import get_theme_qss
        from app.ui.components import components_qss
        from app.ui.dialogs import dialogs_qss
        tokens = TOKENS_DARK if theme == "dark" else TOKENS_LIGHT
        full_qss = "\n".join([
            get_theme_qss(theme),
            get_global_qss(theme),
            components_qss(tokens),
            dialogs_qss(tokens),
        ])
        app = QApplication.instance()
        if app:
            app.setStyleSheet(full_qss)
        self.theme_changed.emit(theme)

    @property
    def current_theme(self) -> str:
        return self._current_theme

    def is_dark(self) -> bool:
        return self._current_theme == "dark"


# =============================================================================
# 기존 코드 (하위 호환 유지 — Phase 5 이후 점진적으로 토큰으로 교체)
# =============================================================================
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

    # --- ネットワーク状態・共通セマンティック色 (テーマ非依存) ---
    ONLINE_COLOR  = "#4caf50"
    OFFLINE_COLOR = "#ff5252"

    # --- アクションボタン色 ---
    ACTION_BLUE_DARK  = "#0e639c"    # ダーク: VSCode スタイルブルー
    ACTION_BLUE_LIGHT = "#1a73e8"    # ライト: Google スタイルブルー

    # --- ログアウト・破壊的操作色 ---
    LOGOUT_COLOR    = "#ff5252"
    LOGOUT_HOVER_BG = "rgba(255,82,82,0.12)"

    # --- ボーダー色 ---
    BORDER_DARK  = "#3e3e42"
    BORDER_LIGHT = "#e0e0e0"

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
        """패널 및 リスト 아이템, 툴팁 등에 사용되는 배경/텍스트 색상.

        Phase 6 — 디자인 토큰 (TOKENS_DARK/LIGHT) 으로 리다이렉트.
        """
        t = TOKENS_DARK if is_dark else TOKENS_LIGHT
        return {
            "bg":       t["bg_surface"],
            "border":   t["border_subtle"],
            "text":     t["fg_primary"],
            "text_dim": t["fg_tertiary"],
            "hover":    t["bg_surface_3"],
        }

    @staticmethod
    def get_graph_colors(is_dark: bool) -> dict:
        """PyQtGraph 배경 및 축, 그리드에 사용되는 색상. 토큰 기반."""
        t = TOKENS_DARK if is_dark else TOKENS_LIGHT
        return {
            "bg":   t["bg_surface"],
            "axis": t["fg_quaternary"],
            "text": t["fg_secondary"],
        }

    @staticmethod
    def get_sidebar_header_color(is_dark: bool) -> str:
        """サイドバーグループヘッダーのテキスト色"""
        return "#e0e0e0" if is_dark else "#1a1a1a"

    @staticmethod
    def get_util_strip_colors(is_dark: bool) -> dict:
        """ユーティリティストリップ (サイドバー下部ボタンバー) の配色. 토큰 기반."""
        t = TOKENS_DARK if is_dark else TOKENS_LIGHT
        return {
            "bg":       t["bg_surface_2"],
            "border":   t["border_subtle"],
            "text":     t["fg_secondary"],
            "active":   t["accent"],
            "hover_bg": "rgba(255,255,255,0.08)" if is_dark else "rgba(0,0,0,0.07)",
        }

    @staticmethod
    def get_notification_list_style(is_dark: bool) -> str:
        """通知センター QListWidget のスタイル文字列. 토큰 기반."""
        t = TOKENS_DARK if is_dark else TOKENS_LIGHT
        return (
            f"QListWidget {{ background: {t['bg_surface']}; color: {t['fg_primary']}; }}"
            f"QListWidget::item {{ border-bottom: 1px solid {t['border_subtle']}; "
            f"padding: 15px; font-size: 13px; }}"
        )

    @staticmethod
    def action_blue(is_dark: bool) -> str:
        """テーマに応じたアクションボタン色"""
        return UIColors.ACTION_BLUE_DARK if is_dark else UIColors.ACTION_BLUE_LIGHT

    @staticmethod
    def get_chat_colors(is_dark: bool) -> dict:
        """AI チャットウィジェットのバブル・アバター配色. 토큰 기반 (c_ai)."""
        t = TOKENS_DARK if is_dark else TOKENS_LIGHT
        return {
            "user_bg":   t["c_ai"],          # #5856D6 — design AI accent
            "user_fg":   "#FFFFFF",
            "asst_bg":   t["bg_surface_2"],
            "asst_fg":   t["fg_primary"],
            "avatar_bg": t["c_ai"],
            "time_fg":   t["fg_tertiary"],
        }

    @staticmethod
    def get_log_colors(is_dark: bool) -> dict:
        """システムログビューアに使用するログレベル別の配色. bg/text/time 만 토큰화."""
        t = TOKENS_DARK if is_dark else TOKENS_LIGHT
        if is_dark:
            return {
                "bg":       t["bg_surface"],
                "text":     t["fg_primary"],
                "error":    "#ff5555",
                "warning":  "#ffb86c",
                "info":     "#8be9fd",
                "module":   "#bd93f9",
                "time":     t["fg_tertiary"],
                "error_bg": "#3b1111",
                "warn_bg":  "#2e2000",
            }
        else:
            return {
                "bg":       t["bg_surface"],
                "text":     t["fg_primary"],
                "error":    "#cc0000",
                "warning":  "#e65100",
                "info":     "#1565c0",
                "module":   "#6a1b9a",
                "time":     t["fg_tertiary"],
                "error_bg": "#fff0f0",
                "warn_bg":  "#fff8e1",
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


