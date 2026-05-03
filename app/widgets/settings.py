"""設定画面 — Phase 5.16 リニューアル.

レイアウト: 좌측 탭 (220px) + 우측 패널 (가변).

7 カテゴリ:
    一般 / 表示 / 自動更新 / 言語 / アカウント / 通知 / 高度な設定
    + ユーザー管理 (관리자 전용)

설정 변경:
    - 컨트롤 변경 → 즉시 메모리 반영
    - 우측 하단 "保存" / "初期化" 버튼
    - 저장 시 bus.settings_saved.emit() → 모든 위젯이 자동 갱신 주기 재구독

기존 settings.py 의 모든 기능 보존:
    - 임계값 (imbalance_alert, reserve_low/warn)
    - 자동 갱신 주기 (8 위젯)
    - 데이터 보존 (retention)
    - AI 챗 (모델, 온도, 토큰, 히스토리)
    - 자동 시작
    - 다국어
    - 관리자 사용자 관리
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QPropertyAnimation, QTimer, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFrame,
    QGraphicsOpacityEffect, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.api.database_worker import DataRetentionWorker
from app.core.config import load_settings, save_settings
from app.core.events import bus
from app.core.i18n import LANG_OPTIONS, tr
from app.core.platform import set_autostart
from app.ui.common import BaseWidget
from app.ui.components import (
    LeeButton, LeeDetailHeader, LeeDialog, LeeIconTile, LeePill, LeeSegment,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 토큰
# ──────────────────────────────────────────────────────────────────────
_C_SETTINGS = "#A8B0BD"
_C_OK       = "#30D158"
_C_BAD      = "#FF453A"
_C_INFO     = "#0A84FF"
_C_WARN     = "#FF9F0A"

_LANG_CODES = [code for _, code in LANG_OPTIONS]

_GEMINI_MODELS = [
    ("gemini-2.5-flash  (推奨)",       "gemini-2.5-flash"),
    ("gemini-2.5-pro  (高精度・低速)", "gemini-2.5-pro"),
    ("gemini-2.0-flash",               "gemini-2.0-flash"),
    ("gemini-2.0-flash-lite  (軽量)",  "gemini-2.0-flash-lite"),
]
_GEMINI_MODEL_CODES = [v for _, v in _GEMINI_MODELS]
_MAX_TOKENS_OPTIONS = [512, 1024, 2048, 4096]


# ──────────────────────────────────────────────────────────────────────
# Admin Workers (기존 그대로)
# ──────────────────────────────────────────────────────────────────────
class FetchUsersWorker(QThread):
    success = Signal(list); error = Signal(str)
    def run(self):
        try:
            from app.api.google.sheets import get_all_users
            self.success.emit(get_all_users())
        except Exception as e:
            self.error.emit(str(e))


class RemoveUserWorker(QThread):
    success = Signal(); error = Signal(str)
    def __init__(self, email):
        super().__init__(); self.email = email
    def run(self):
        try:
            from app.api.google.sheets import remove_user
            remove_user(self.email); self.success.emit()
        except Exception as e:
            self.error.emit(str(e))


class AddUserWorker(QThread):
    success = Signal(); error = Signal(str)
    def __init__(self, email, name):
        super().__init__(); self.email = email; self.name = name
    def run(self):
        try:
            from app.api.google.sheets import add_user
            add_user(self.email, self.name); self.success.emit()
        except Exception as e:
            self.error.emit(str(e))


# ──────────────────────────────────────────────────────────────────────
# _SettingsRow — 단일 설정 행 (아이콘 + 라벨 + 설명 + 컨트롤)
# ──────────────────────────────────────────────────────────────────────
class _SettingsRow(QFrame):
    """좌: 28px 아이콘 + 라벨 + 서브텍스트  /  우: 컨트롤."""

    def __init__(self, glyph: str, label: str, description: str = "",
                 control: Optional[QWidget] = None,
                 accent: str = _C_SETTINGS, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsRow")
        self._is_dark = True
        self._control = control
        self._build_ui(glyph, label, description, accent)
        self._apply_qss()

    def _build_ui(self, glyph, label, description, accent) -> None:
        h = QHBoxLayout(self); h.setContentsMargins(14, 12, 14, 12); h.setSpacing(12)

        # 아이콘 타일 (28px)
        tile = LeeIconTile(glyph=glyph, color=accent, size=28, radius=8)
        h.addWidget(tile, 0, Qt.AlignTop)

        # 텍스트 (라벨 + 설명)
        text_box = QVBoxLayout(); text_box.setSpacing(2); text_box.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label); lbl.setObjectName("settingsRowLabel")
        text_box.addWidget(lbl)
        if description:
            sub = QLabel(description); sub.setObjectName("settingsRowSub")
            sub.setWordWrap(True)
            text_box.addWidget(sub)
        h.addLayout(text_box, 1)

        # 컨트롤 (우측)
        if self._control is not None:
            self._control.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
            h.addWidget(self._control, 0, Qt.AlignVCenter)

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    def _apply_qss(self) -> None:
        d = self._is_dark
        bg_hover    = "rgba(255,255,255,0.04)" if d else "rgba(11,18,32,0.03)"
        fg_primary  = "#F2F4F7" if d else "#0B1220"
        fg_tertiary = "#6B7280" if d else "#8A93A6"
        bs          = "rgba(255,255,255,0.06)" if d else "rgba(11,18,32,0.06)"
        self.setStyleSheet(f"""
            QFrame#settingsRow {{
                background: transparent;
                border-bottom: 1px solid {bs};
            }}
            QFrame#settingsRow:hover {{
                background: {bg_hover};
            }}
            QLabel#settingsRowLabel {{
                color: {fg_primary}; background: transparent;
                font-size: 13px; font-weight: 700;
            }}
            QLabel#settingsRowSub {{
                color: {fg_tertiary}; background: transparent;
                font-size: 11px;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# _CategoryTab — 좌측 카테고리 버튼
# ──────────────────────────────────────────────────────────────────────
class _CategoryTab(QPushButton):
    def __init__(self, key: str, glyph: str, label: str, parent=None):
        super().__init__(parent)
        self._key = key
        self.setObjectName("settingsTab")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setText(f"{glyph}    {label}")
        self.setMinimumHeight(40)
        self.setProperty("active", "false")

    def set_active(self, active: bool) -> None:
        self.setChecked(active)
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self); self.style().polish(self)


# ──────────────────────────────────────────────────────────────────────
# 카테고리 메타
# ──────────────────────────────────────────────────────────────────────
_CATEGORIES = [
    ("general",  "⚙",  "一般"),
    ("display",  "🎨",  "表示"),
    ("update",   "⏱",  "自動更新"),
    ("language", "🌐",  "言語"),
    ("account",  "👤",  "アカウント"),
    ("notify",   "🔔",  "通知"),
    ("advanced", "🛠",  "高度な設定"),
]


# ──────────────────────────────────────────────────────────────────────
# SettingsWidget
# ──────────────────────────────────────────────────────────────────────
class SettingsWidget(BaseWidget):
    """設定画面 — 좌측 탭 + 우측 패널."""

    def __init__(self):
        super().__init__()
        self._current_settings: dict = {}
        self._tabs: dict[str, _CategoryTab] = {}
        self._panels: dict[str, QWidget] = {}
        self._rows: list[_SettingsRow] = []
        self._is_admin = self._check_admin()
        self._build_ui()
        self._load_data()
        self.apply_theme_custom()

    @staticmethod
    def _check_admin() -> bool:
        try:
            from app.core.config import get_session_email, ADMIN_EMAIL
            return (get_session_email() or "").lower() == ADMIN_EMAIL.lower()
        except Exception:
            return False

    # ── UI 빌드 ───────────────────────────────────────────────
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 22); outer.setSpacing(14)

        # 1) DetailHeader
        from app.core.config import __version__
        self._header = LeeDetailHeader(
            title=tr("設定"),
            subtitle=tr("各機能のカスタマイズ · v{0}").format(__version__),
            accent=_C_SETTINGS,
            icon_qicon=QIcon(":/img/setting.svg"),
            badge=tr("ADMIN") if self._is_admin else None,
            show_export=False,
        )
        self._header.back_clicked.connect(lambda: bus.page_requested.emit(0))
        outer.addWidget(self._header)

        # 2) 외곽 카드 (좌 220 + 우 가변)
        outer_card = QFrame(); outer_card.setObjectName("settingsOuterCard")
        oc = QHBoxLayout(outer_card); oc.setContentsMargins(0, 0, 0, 0); oc.setSpacing(0)
        outer.addWidget(outer_card, 1)
        self._outer_card = outer_card

        # 좌측 — 카테고리 탭
        left = QFrame(); left.setObjectName("settingsLeftPane")
        left.setFixedWidth(220)
        ll = QVBoxLayout(left); ll.setContentsMargins(10, 12, 10, 12); ll.setSpacing(4)

        for key, glyph, label in _CATEGORIES:
            t = _CategoryTab(key, glyph, tr(label))
            t.clicked.connect(lambda _=False, k=key: self._switch_tab(k))
            ll.addWidget(t)
            self._tabs[key] = t

        if self._is_admin:
            t = _CategoryTab("admin", "👑", tr("ユーザー管理"))
            t.clicked.connect(lambda _=False, k="admin": self._switch_tab(k))
            ll.addWidget(t)
            self._tabs["admin"] = t

        ll.addStretch()
        oc.addWidget(left)

        # 좌-우 구분선
        sep = QFrame(); sep.setObjectName("settingsVSep"); sep.setFixedWidth(1)
        oc.addWidget(sep)

        # 우측 — 패널 stack
        right = QFrame(); right.setObjectName("settingsRightPane")
        rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)
        oc.addWidget(right, 1)

        self._stack = QStackedWidget()
        rl.addWidget(self._stack, 1)

        # 패널 빌드
        self._panels["general"]  = self._build_panel_general()
        self._panels["display"]  = self._build_panel_display()
        self._panels["update"]   = self._build_panel_update()
        self._panels["language"] = self._build_panel_language()
        self._panels["account"]  = self._build_panel_account()
        self._panels["notify"]   = self._build_panel_notify()
        self._panels["advanced"] = self._build_panel_advanced()
        if self._is_admin:
            self._panels["admin"] = self._build_panel_admin()

        for key, _, _ in _CATEGORIES:
            self._stack.addWidget(self._panels[key])
        if self._is_admin:
            self._stack.addWidget(self._panels["admin"])

        # 첫 탭 active
        self._switch_tab("general")

        # 3) 푸터 — 토스트 + 초기화 + 저장
        footer = QFrame(); footer.setObjectName("settingsFooter")
        footer.setFixedHeight(56)
        fl = QHBoxLayout(footer); fl.setContentsMargins(14, 10, 14, 10); fl.setSpacing(8)
        outer.addWidget(footer)

        self._toast_lbl = QLabel(""); self._toast_lbl.setObjectName("settingsToast")
        self._toast_effect = QGraphicsOpacityEffect(self._toast_lbl)
        self._toast_lbl.setGraphicsEffect(self._toast_effect)
        self._toast_anim = QPropertyAnimation(self._toast_effect, b"opacity")
        self._toast_anim.setDuration(280)
        self._toast_lbl.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._hide_toast)
        fl.addWidget(self._toast_lbl, 1)

        self.btn_reset = LeeButton(tr("初期化"), variant="ghost", size="md")
        self.btn_reset.clicked.connect(self._reset_to_defaults)
        fl.addWidget(self.btn_reset)
        self.btn_save = LeeButton(tr("保存"), variant="primary", size="md")
        self.btn_save.clicked.connect(self._save_data)
        fl.addWidget(self.btn_save)

    def _switch_tab(self, key: str) -> None:
        for k, tab in self._tabs.items():
            tab.set_active(k == key)
        if key in self._panels:
            self._stack.setCurrentWidget(self._panels[key])

    # ── 패널 빌더 헬퍼 ───────────────────────────────────────
    def _make_panel_scroll(self) -> tuple[QScrollArea, QVBoxLayout]:
        """카테고리 패널 — 스크롤 가능한 컨테이너."""
        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget(); inner.setObjectName("settingsPanelInner")
        v = QVBoxLayout(inner); v.setContentsMargins(20, 18, 20, 18); v.setSpacing(0)
        scroll.setWidget(inner)
        return scroll, v

    def _add_row(self, vlay: QVBoxLayout, glyph: str, label: str, desc: str,
                 control: QWidget, accent: str = _C_SETTINGS) -> _SettingsRow:
        row = _SettingsRow(glyph, label, desc, control, accent=accent)
        self._rows.append(row)
        vlay.addWidget(row)
        return row

    def _section_title(self, vlay: QVBoxLayout, text: str) -> None:
        lbl = QLabel(text); lbl.setObjectName("settingsSectionTitle")
        vlay.addWidget(lbl)

    @staticmethod
    def _spn_int(lo: int, hi: int, suffix: str, tip: str = "",
                 step: int = 1) -> QSpinBox:
        w = QSpinBox(); w.setRange(lo, hi); w.setSuffix(suffix)
        w.setSingleStep(step); w.setMinimumWidth(120); w.setFixedHeight(32)
        if tip: w.setToolTip(tip)
        return w

    @staticmethod
    def _spn_float(lo: float, hi: float, suffix: str, tip: str = "",
                   step: float = 1.0, decimals: int = 1) -> QDoubleSpinBox:
        w = QDoubleSpinBox(); w.setRange(lo, hi); w.setSuffix(suffix)
        w.setSingleStep(step); w.setDecimals(decimals)
        w.setMinimumWidth(120); w.setFixedHeight(32)
        if tip: w.setToolTip(tip)
        return w

    @staticmethod
    def _toggle() -> QCheckBox:
        c = QCheckBox(); c.setObjectName("settingsToggle")
        c.setCursor(Qt.PointingHandCursor)
        return c

    # ── 一般 ─────────────────────────────────────────────────
    def _build_panel_general(self) -> QWidget:
        scroll, v = self._make_panel_scroll()
        self._section_title(v, tr("起動と動作"))

        self.chk_auto_start = self._toggle()
        self._add_row(v, "🚀", tr("自動起動"),
                      tr("Windows 起動時にバックグラウンドで自動実行"),
                      self.chk_auto_start)

        self.chk_tray = self._toggle()
        self.chk_tray.setEnabled(False)
        self._add_row(v, "📌", tr("トレイ常駐"),
                      tr("ウィンドウを閉じても通知トレイに常駐 (準備中)"),
                      self.chk_tray)

        self.chk_quit_confirm = self._toggle()
        self.chk_quit_confirm.setEnabled(False)
        self._add_row(v, "🛑", tr("終了確認ダイアログ"),
                      tr("アプリ終了前に確認ダイアログを表示 (準備中)"),
                      self.chk_quit_confirm)

        self._section_title(v, tr("データ保存"))
        from app.core.config import APP_DIR
        path_lbl = QLabel(str(APP_DIR)); path_lbl.setObjectName("settingsPath")
        path_btn = LeeButton(tr("フォルダを開く"), variant="secondary", size="sm")
        path_btn.clicked.connect(lambda: self._open_folder(APP_DIR))
        path_box = QHBoxLayout(); path_box.setSpacing(8)
        path_box.addWidget(path_lbl); path_box.addWidget(path_btn)
        path_w = QWidget(); path_w.setLayout(path_box)
        self._add_row(v, "📁", tr("データフォルダ"),
                      tr("設定ファイル・キャッシュ・ログの保存場所"), path_w)

        v.addStretch()
        return scroll

    # ── 表示 ─────────────────────────────────────────────────
    def _build_panel_display(self) -> QWidget:
        scroll, v = self._make_panel_scroll()
        self._section_title(v, tr("テーマ"))

        self.seg_theme = LeeSegment(
            [("dark", tr("ダーク")), ("light", tr("ライト"))],
            value="dark" if self.is_dark else "light",
            accent=_C_INFO,
        )
        self.seg_theme.value_changed.connect(self._on_theme_changed)
        self._add_row(v, "🌓", tr("テーマ"),
                      tr("ダーク / ライト テーマ切替"), self.seg_theme)

        # 컴팩트 모드 (placeholder)
        self.chk_compact = self._toggle()
        self.chk_compact.setEnabled(False)
        self._add_row(v, "📐", tr("コンパクトモード"),
                      tr("カードや行の余白を縮小 (準備中)"), self.chk_compact)

        # 폰트 크기 (placeholder)
        self.spn_font = self._spn_int(10, 18, "  pt", "", step=1)
        self.spn_font.setValue(13)
        self.spn_font.setEnabled(False)
        self._add_row(v, "🔤", tr("フォントサイズ"),
                      tr("本文の基本サイズ (10〜18 pt) (準備中)"), self.spn_font)

        v.addStretch()
        return scroll

    # ── 自動更新 ─────────────────────────────────────────────
    def _build_panel_update(self) -> QWidget:
        scroll, v = self._make_panel_scroll()
        self._section_title(v, tr("ウィジェット別の自動更新間隔"))

        # (key, label, desc, default min, max min, accent)
        intervals = [
            ("imb_int",   "imbalance_interval",     tr("インバランス"),
             tr("インバランス単価のデータ取得間隔"), 1,    1440, "#F25C7A"),
            ("res_int",   "reserve_interval",       tr("電力予備率"),
             tr("OCCTO 予備率の取得間隔"),          1,    1440, "#5B8DEF"),
            ("wea_int",   "weather_interval",       tr("全国天気"),
             tr("Open-Meteo 天気予報の取得間隔"),    1,    1440, "#2EC4B6"),
            ("hjks_int",  "hjks_interval",          tr("発電稼働状況 (HJKS)"),
             tr("発電所停止情報の取得間隔"),         1,    1440, "#A78BFA"),
            ("jkm_int",   "jkm_interval",           tr("JKM LNG 価格"),
             tr("LNG スポット価格の取得間隔"),       1,    1440, "#F4B740"),
            ("cal_int",   "calendar_poll_interval", tr("カレンダー"),
             tr("Google カレンダー イベント取得間隔"), 1,  1440, "#34C759"),
            ("gmail_int", "gmail_poll_interval",    tr("Gmail"),
             tr("Gmail 受信確認間隔"),                1,  1440, "#EA4335"),
        ]
        self._interval_widgets: dict[str, tuple[str, QSpinBox]] = {}
        for attr, key, label, desc, lo, hi, color in intervals:
            spn = self._spn_int(lo, hi, "  " + tr("分"), tip=desc)
            self._interval_widgets[attr] = (key, spn)
            setattr(self, f"spn_{attr}", spn)
            self._add_row(v, "⏱", label, desc, spn, accent=color)

        v.addStretch()
        return scroll

    # ── 言語 ─────────────────────────────────────────────────
    def _build_panel_language(self) -> QWidget:
        scroll, v = self._make_panel_scroll()
        self._section_title(v, tr("表示言語"))

        # LANG_OPTIONS = [(display, code), ...]
        seg_options = [(code, name) for name, code in LANG_OPTIONS]
        self.seg_language = LeeSegment(
            seg_options, value="auto", accent=_C_INFO,
        )
        self._add_row(v, "🌐", tr("言語"),
                      tr("アプリの表示言語 (再起動後に完全反映)"),
                      self.seg_language)

        note = QLabel("※ " + tr("一部の項目は再起動後に反映されます。"))
        note.setObjectName("settingsNote"); note.setWordWrap(True)
        v.addWidget(note)
        v.addStretch()
        return scroll

    # ── アカウント ───────────────────────────────────────────
    def _build_panel_account(self) -> QWidget:
        scroll, v = self._make_panel_scroll()
        self._section_title(v, tr("ログイン中のユーザー"))

        # 사용자 정보 카드
        user_card = QFrame(); user_card.setObjectName("settingsUserCard")
        ucl = QHBoxLayout(user_card); ucl.setContentsMargins(16, 14, 16, 14); ucl.setSpacing(12)
        try:
            from app.api.google.auth import get_current_user_email
            email = get_current_user_email() or "(未認証)"
        except Exception:
            email = "(未認証)"
        name = email.split("@", 1)[0] if "@" in email else email
        avatar = QLabel(name[0].upper() if name else "?")
        avatar.setObjectName("settingsAvatar")
        avatar.setFixedSize(48, 48); avatar.setAlignment(Qt.AlignCenter)
        ucl.addWidget(avatar)

        nbox = QVBoxLayout(); nbox.setContentsMargins(0, 0, 0, 0); nbox.setSpacing(2)
        n_lbl = QLabel(name); n_lbl.setObjectName("settingsUserName")
        e_lbl = QLabel(email); e_lbl.setObjectName("settingsUserEmail")
        nbox.addWidget(n_lbl); nbox.addWidget(e_lbl)
        ucl.addLayout(nbox, 1)

        # Google 연동 상태 pill
        self.acc_status_pill = LeePill(tr("認証済"), variant="success")
        ucl.addWidget(self.acc_status_pill, 0, Qt.AlignTop)
        v.addWidget(user_card)

        # 로그아웃 행
        btn_logout = LeeButton(tr("ログアウト"), variant="destructive", size="sm")
        btn_logout.clicked.connect(self._on_logout)
        self._add_row(v, "🚪", tr("ログアウト"),
                      tr("Google アカウントから連携解除"), btn_logout)

        # Google 재인증 행
        btn_reauth = LeeButton(tr("再認証"), variant="secondary", size="sm")
        btn_reauth.clicked.connect(self._on_reauth)
        self._add_row(v, "🔑", tr("Google 連携"),
                      tr("OAuth トークンを再発行"), btn_reauth)

        v.addStretch()
        return scroll

    def _on_logout(self) -> None:
        if not LeeDialog.confirm(
            tr("ログアウトの確認"),
            tr("Google アカウントから連携解除しますか?\n再ログインが必要になります。"),
            ok_text=tr("ログアウト"), destructive=True, parent=self,
        ):
            return
        try:
            from app.api.google.auth import revoke_credentials
            revoke_credentials()
            bus.user_logged_out.emit()
        except Exception as e:
            LeeDialog.error(tr("エラー"), str(e), parent=self)

    def _on_reauth(self) -> None:
        try:
            from app.api.google.auth import run_oauth_flow
            ok = run_oauth_flow()
            if ok:
                LeeDialog.info(tr("認証完了"), tr("Google 連携が完了しました。"), parent=self)
            else:
                LeeDialog.error(tr("認証失敗"), tr("OAuth フローが中断されました。"), parent=self)
        except Exception as e:
            LeeDialog.error(tr("エラー"), str(e), parent=self)

    # ── 通知 ─────────────────────────────────────────────────
    def _build_panel_notify(self) -> QWidget:
        scroll, v = self._make_panel_scroll()
        self._section_title(v, tr("デスクトップ通知"))

        self.chk_desktop_notif = self._toggle()
        self.chk_desktop_notif.setChecked(True)
        self.chk_desktop_notif.setEnabled(False)
        self._add_row(v, "💬", tr("デスクトップ通知"),
                      tr("重要なアラートをトレイから通知 (準備中)"),
                      self.chk_desktop_notif)

        self.chk_sound = self._toggle()
        self.chk_sound.setEnabled(False)
        self._add_row(v, "🔊", tr("通知音"),
                      tr("通知時にサウンドを再生 (準備中)"), self.chk_sound)

        self._section_title(v, tr("アラートしきい値"))

        self.spn_imb_alert = self._spn_float(
            0, 1000, "  " + tr("円"),
            tip=tr("インバランス単価がこの値を超過した場合、警告"),
            step=1.0, decimals=1,
        )
        self._add_row(v, "💴", tr("インバランス単価"),
                      tr("この値を超過 → 警告通知"),
                      self.spn_imb_alert, accent="#F25C7A")

        self.spn_res_low = self._spn_float(
            0, 100, "  %",
            tip=tr("予備率がこの値を下回った場合、赤色警告"),
            step=0.5, decimals=1,
        )
        self._add_row(v, "🔴", tr("電力予備率 警告 (赤)"),
                      tr("この値を下回ると赤色警告"),
                      self.spn_res_low, accent="#FF453A")

        self.spn_res_warn = self._spn_float(
            0, 100, "  %",
            tip=tr("予備率がこの値を下回った場合、黄色注意"),
            step=0.5, decimals=1,
        )
        self._add_row(v, "🟡", tr("電力予備率 注意 (黄)"),
                      tr("この値を下回ると黄色注意"),
                      self.spn_res_warn, accent="#FF9F0A")

        v.addStretch()
        return scroll

    # ── 高度な設定 ──────────────────────────────────────────
    def _build_panel_advanced(self) -> QWidget:
        scroll, v = self._make_panel_scroll()
        self._section_title(v, tr("AI チャット"))

        self.cmb_gemini_model = QComboBox()
        for display, _ in _GEMINI_MODELS:
            self.cmb_gemini_model.addItem(display)
        self.cmb_gemini_model.setMinimumWidth(220); self.cmb_gemini_model.setFixedHeight(32)
        self._add_row(v, "🤖", tr("フォールバックモデル"),
                      tr("Gemini 2.5 Flash Lite の次に試みるモデル"),
                      self.cmb_gemini_model)

        self.spn_temperature = self._spn_float(
            0.1, 2.0, "", tip=tr("低: 一貫 / 高: 多様"), step=0.1, decimals=1,
        )
        self._add_row(v, "🌡", tr("応答の温度"),
                      tr("AIの回答の多様性 (推奨 0.7)"), self.spn_temperature)

        self.cmb_max_tokens = QComboBox()
        for tok in _MAX_TOKENS_OPTIONS:
            self.cmb_max_tokens.addItem(f"{tok:,} tokens", tok)
        self.cmb_max_tokens.setMinimumWidth(160); self.cmb_max_tokens.setFixedHeight(32)
        self._add_row(v, "📏", tr("最大トークン数"),
                      tr("一回の回答で生成する最大トークン (推奨 2048)"),
                      self.cmb_max_tokens)

        self.spn_history = self._spn_int(4, 100, "  " + tr("件"),
                                          step=2, tip=tr("会話履歴 上限"))
        self._add_row(v, "📚", tr("会話履歴の保持数"),
                      tr("AI に渡す過去メッセージの上限"), self.spn_history)

        self._section_title(v, tr("Gmail"))
        self.spn_gmail_max = self._spn_int(10, 500, "  " + tr("件"),
                                            tip=tr("一度に取得する Gmail メール件数"))
        self._add_row(v, "📥", tr("メール取得件数"),
                      tr("一度に取得する最大メール件数"),
                      self.spn_gmail_max, accent="#EA4335")

        self._section_title(v, tr("データ管理"))
        self.spn_retention = self._spn_int(30, 3650, "  " + tr("日"),
                                            tip=tr("古いデータの自動バックアップ"))
        self._add_row(v, "💾", tr("データ保持期間"),
                      tr("この日数以上の古いデータは backups へ自動移動"),
                      self.spn_retention)

        self.btn_run_retention = LeeButton("🗂  " + tr("今すぐ整理実行"),
                                            variant="secondary", size="sm")
        self.btn_run_retention.clicked.connect(self._manual_retention)
        self._add_row(v, "🧹", tr("手動でデータ整理"),
                      tr("古いデータを今すぐバックアップ + 削除"),
                      self.btn_run_retention)

        self.btn_clear_cache = LeeButton("🗑  " + tr("キャッシュ削除"),
                                          variant="secondary", size="sm")
        self.btn_clear_cache.clicked.connect(self._clear_cache)
        self._add_row(v, "🧽", tr("キャッシュ削除"),
                      tr("一時ファイル・サムネイル等を削除"), self.btn_clear_cache)

        self._section_title(v, tr("デバッグ / リセット"))
        self.chk_debug = self._toggle(); self.chk_debug.setEnabled(False)
        self._add_row(v, "🐛", tr("デバッグモード"),
                      tr("詳細なログを出力 (準備中)"), self.chk_debug)

        self.btn_factory = LeeButton("⚠  " + tr("初期化"),
                                      variant="destructive", size="sm")
        self.btn_factory.clicked.connect(self._factory_reset)
        self._add_row(v, "🔄", tr("ファクトリーリセット"),
                      tr("全ての設定を初期値に戻す (確認あり)"),
                      self.btn_factory)

        v.addStretch()
        return scroll

    def _clear_cache(self) -> None:
        if not LeeDialog.confirm(
            tr("キャッシュ削除"),
            tr("一時ファイルとサムネイルを削除しますか?\n再生成されます。"),
            ok_text=tr("削除"), destructive=True, parent=self,
        ):
            return
        try:
            from app.core.config import APP_DIR
            import shutil
            cache_dir = APP_DIR / "cache"
            if cache_dir.exists():
                shutil.rmtree(cache_dir, ignore_errors=True)
            self._show_toast("✅  " + tr("キャッシュを削除しました"))
        except Exception as e:
            LeeDialog.error(tr("エラー"), str(e), parent=self)

    def _factory_reset(self) -> None:
        if not LeeDialog.confirm(
            tr("ファクトリーリセット"),
            tr("全ての設定を初期値に戻しますか?\nこの操作は元に戻せません。"),
            ok_text=tr("リセット"), destructive=True, parent=self,
        ):
            return
        from app.core.config import DEFAULT_SETTINGS, save_settings
        save_settings(dict(DEFAULT_SETTINGS))
        self._load_data()
        self._show_toast("✅  " + tr("初期値に戻しました"))
        bus.settings_saved.emit()

    # ── 관리자 패널 (사용자 관리) ────────────────────────────
    def _build_panel_admin(self) -> QWidget:
        scroll, v = self._make_panel_scroll()
        self._section_title(v, tr("Google Sheets ID"))
        from app.core.config import SHEETS_REGISTRY_ID
        sid = QLineEdit(); sid.setObjectName("settingsLineEdit")
        sid.setText(SHEETS_REGISTRY_ID); sid.setDisabled(True)
        sid.setFixedHeight(32)
        self._add_row(v, "📊", tr("レジストリ ID"),
                      tr("(.env で管理 — 読み取り専用)"), sid)

        self._section_title(v, tr("登録ユーザー"))
        self.lbl_users_status = QLabel("")
        self.lbl_users_status.setObjectName("settingsNote")
        v.addWidget(self.lbl_users_status)

        self.tbl_users = QTableWidget(0, 3)
        self.tbl_users.setHorizontalHeaderLabels([
            tr("メールアドレス"), tr("名前"), tr("登録日"),
        ])
        self.tbl_users.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_users.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tbl_users.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tbl_users.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_users.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_users.setMinimumHeight(200)
        self.tbl_users.verticalHeader().setVisible(False)
        v.addWidget(self.tbl_users)

        # 액션 행
        ar = QHBoxLayout(); ar.setSpacing(8)
        b_refresh = LeeButton("↻  " + tr("更新"), variant="secondary", size="sm")
        b_refresh.clicked.connect(self._refresh_user_list)
        ar.addWidget(b_refresh)
        b_remove = LeeButton(tr("選択ユーザー削除"), variant="destructive", size="sm")
        b_remove.clicked.connect(self._remove_selected_user)
        ar.addWidget(b_remove); ar.addStretch()
        ar_w = QWidget(); ar_w.setLayout(ar); v.addWidget(ar_w)

        self._section_title(v, tr("ユーザー追加"))
        add_box = QHBoxLayout(); add_box.setSpacing(8)
        self.edt_add_email = QLineEdit(); self.edt_add_email.setObjectName("settingsLineEdit")
        self.edt_add_email.setPlaceholderText(tr("メールアドレス"))
        self.edt_add_email.setFixedHeight(32)
        self.edt_add_name = QLineEdit(); self.edt_add_name.setObjectName("settingsLineEdit")
        self.edt_add_name.setPlaceholderText(tr("名前 (任意)"))
        self.edt_add_name.setFixedWidth(160); self.edt_add_name.setFixedHeight(32)
        b_add = LeeButton("＋ " + tr("追加"), variant="primary", size="sm")
        b_add.clicked.connect(self._add_user)
        add_box.addWidget(self.edt_add_email, 1)
        add_box.addWidget(self.edt_add_name)
        add_box.addWidget(b_add)
        add_w = QWidget(); add_w.setLayout(add_box); v.addWidget(add_w)

        v.addStretch()
        return scroll

    # ── 관리자 액션 ───────────────────────────────────────────
    def _refresh_user_list(self) -> None:
        self.lbl_users_status.setText(tr("取得中..."))
        self._users_worker = FetchUsersWorker()
        self._users_worker.success.connect(self._on_users_fetched)
        self._users_worker.error.connect(lambda e: self.lbl_users_status.setText(str(e)[:80]))
        self._users_worker.finished.connect(self._users_worker.deleteLater)
        self._users_worker.start()
        self.track_worker(self._users_worker)

    def _on_users_fetched(self, users) -> None:
        self.tbl_users.setRowCount(0)
        for u in users:
            r = self.tbl_users.rowCount()
            self.tbl_users.insertRow(r)
            self.tbl_users.setItem(r, 0, QTableWidgetItem(u["email"]))
            self.tbl_users.setItem(r, 1, QTableWidgetItem(u["name"]))
            self.tbl_users.setItem(r, 2, QTableWidgetItem(u["added"]))
        self.lbl_users_status.setText(tr("{0} 件").format(len(users)))

    def _remove_selected_user(self) -> None:
        if not self.tbl_users.selectedItems(): return
        email = self.tbl_users.item(self.tbl_users.currentRow(), 0).text()
        if not LeeDialog.confirm(
            tr("確認"), tr("{0} を削除しますか?").format(email),
            ok_text=tr("削除"), destructive=True, parent=self,
        ):
            return
        self.lbl_users_status.setText(tr("削除中..."))
        self._rm_worker = RemoveUserWorker(email)
        self._rm_worker.success.connect(self._refresh_user_list)
        self._rm_worker.error.connect(
            lambda e: LeeDialog.error(tr("エラー"), str(e), parent=self))
        self._rm_worker.finished.connect(self._rm_worker.deleteLater)
        self._rm_worker.start()
        self.track_worker(self._rm_worker)

    def _add_user(self) -> None:
        email = self.edt_add_email.text().strip()
        name = self.edt_add_name.text().strip()
        if not email:
            self.edt_add_email.setFocus(); return
        self.lbl_users_status.setText(tr("追加中..."))
        self._add_worker = AddUserWorker(email, name)
        self._add_worker.success.connect(self._on_user_added)
        self._add_worker.error.connect(
            lambda e: LeeDialog.error(tr("エラー"), str(e), parent=self))
        self._add_worker.finished.connect(self._add_worker.deleteLater)
        self._add_worker.start()
        self.track_worker(self._add_worker)

    def _on_user_added(self) -> None:
        self.edt_add_email.clear(); self.edt_add_name.clear()
        self._refresh_user_list()
        self._show_toast("✅  " + tr("ユーザーを追加しました"))

    # ── 데이터 정리 ───────────────────────────────────────────
    def _manual_retention(self) -> None:
        days = int(self.spn_retention.value())
        if not LeeDialog.confirm(
            tr("確認"),
            tr("保持期間 ({0}日) より古いデータを\nバックアップして削除しますか?").format(days),
            ok_text=tr("実行"), parent=self,
        ):
            return
        self.btn_run_retention.setEnabled(False)
        self.btn_run_retention.setText(tr("整理中..."))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self._retention_worker = DataRetentionWorker(days)
        self._retention_worker.finished.connect(self._on_retention_finished)
        self._retention_worker.error.connect(self._on_retention_error)
        self._retention_worker.finished.connect(self._retention_worker.deleteLater)
        self._retention_worker.start()
        self.track_worker(self._retention_worker)

    def _on_retention_finished(self) -> None:
        QApplication.restoreOverrideCursor()
        self.btn_run_retention.setEnabled(True)
        self.btn_run_retention.setText("🗂  " + tr("今すぐ整理実行"))
        LeeDialog.info(tr("完了"),
                       tr("古いデータのバックアップと削除が完了しました。"), parent=self)

    def _on_retention_error(self, err: str) -> None:
        QApplication.restoreOverrideCursor()
        self.btn_run_retention.setEnabled(True)
        self.btn_run_retention.setText("🗂  " + tr("今すぐ整理実行"))
        LeeDialog.error(tr("エラー"),
                        tr("処理中にエラー:") + f"\n{err}", parent=self)

    # ── 테마 & 테마 토글 ──────────────────────────────────────
    def _on_theme_changed(self, key: str) -> None:
        is_dark = (key == "dark")
        # 즉시 전체 앱 테마 적용
        try:
            for w in QApplication.topLevelWidgets():
                if hasattr(w, "_toggle_theme"):
                    if w.is_dark != is_dark:
                        w._toggle_theme()
                    break
        except Exception:
            pass

    def _open_folder(self, path) -> None:
        try:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except Exception as e:
            logger.warning(f"폴더 열기 실패: {e}")

    # ── 데이터 로드/저장 ──────────────────────────────────────
    def _load_data(self) -> None:
        self._current_settings = load_settings()
        s = self._current_settings

        # 一般
        self.chk_auto_start.setChecked(bool(s.get("auto_start", False)))

        # 表示 — theme segment 는 _on_theme_changed 가 즉시 적용하므로 초기 set_value
        self.seg_theme.set_value("dark" if self.is_dark else "light")

        # 自動更新
        self.spn_imb_int.setValue(int(s.get("imbalance_interval", 5)))
        self.spn_res_int.setValue(int(s.get("reserve_interval", 5)))
        self.spn_wea_int.setValue(int(s.get("weather_interval", 60)))
        self.spn_hjks_int.setValue(int(s.get("hjks_interval", 180)))
        self.spn_jkm_int.setValue(int(s.get("jkm_interval", 180)))
        self.spn_cal_int.setValue(int(s.get("calendar_poll_interval", 5)))
        self.spn_gmail_int.setValue(int(s.get("gmail_poll_interval", 5)))

        # 言語
        lang = s.get("language", "auto")
        if lang in [c for _, c in LANG_OPTIONS]:
            self.seg_language.set_value(lang)

        # 通知
        self.spn_imb_alert.setValue(float(s.get("imbalance_alert", 40.0)))
        self.spn_res_low.setValue(float(s.get("reserve_low", 8.0)))
        self.spn_res_warn.setValue(float(s.get("reserve_warn", 10.0)))

        # 高度な設定
        model = s.get("gemini_model", "gemini-2.5-flash")
        if model in _GEMINI_MODEL_CODES:
            self.cmb_gemini_model.setCurrentIndex(_GEMINI_MODEL_CODES.index(model))
        self.spn_temperature.setValue(float(s.get("ai_temperature", 0.7)))
        max_tok = int(s.get("ai_max_tokens", 2048))
        if max_tok in _MAX_TOKENS_OPTIONS:
            self.cmb_max_tokens.setCurrentIndex(_MAX_TOKENS_OPTIONS.index(max_tok))
        self.spn_history.setValue(int(s.get("chat_history_limit", 20)))
        self.spn_gmail_max.setValue(int(s.get("gmail_max_results", 50)))
        self.spn_retention.setValue(int(s.get("retention_days", 1460)))

    def _get_ui_settings(self) -> dict:
        return {
            "auto_start":             self.chk_auto_start.isChecked(),
            "imbalance_interval":     int(self.spn_imb_int.value()),
            "reserve_interval":       int(self.spn_res_int.value()),
            "weather_interval":       int(self.spn_wea_int.value()),
            "hjks_interval":          int(self.spn_hjks_int.value()),
            "jkm_interval":           int(self.spn_jkm_int.value()),
            "calendar_poll_interval": int(self.spn_cal_int.value()),
            "gmail_poll_interval":    int(self.spn_gmail_int.value()),
            "language":               self.seg_language.value(),
            "imbalance_alert":        float(self.spn_imb_alert.value()),
            "reserve_low":            float(self.spn_res_low.value()),
            "reserve_warn":           float(self.spn_res_warn.value()),
            "gemini_model":           _GEMINI_MODEL_CODES[self.cmb_gemini_model.currentIndex()],
            "ai_temperature":         round(float(self.spn_temperature.value()), 1),
            "ai_max_tokens":          _MAX_TOKENS_OPTIONS[self.cmb_max_tokens.currentIndex()],
            "chat_history_limit":     int(self.spn_history.value()),
            "gmail_max_results":      int(self.spn_gmail_max.value()),
            "retention_days":         int(self.spn_retention.value()),
        }

    def _save_data(self) -> None:
        new_ui = self._get_ui_settings()
        has_changes = any(self._current_settings.get(k) != v for k, v in new_ui.items())
        if not has_changes:
            self._show_toast(tr("変更がありません"))
            return
        if self._current_settings.get("auto_start") != new_ui["auto_start"]:
            try: set_autostart(new_ui["auto_start"])
            except Exception as e: logger.warning(f"autostart 토글 실패: {e}")
        language_changed = self._current_settings.get("language") != new_ui.get("language")
        new_settings = {**self._current_settings, **new_ui}
        save_settings(new_settings)
        self._current_settings = new_settings
        if language_changed:
            self._show_toast("✅  " + tr("再起動後に完全反映されます"))
        else:
            self._show_toast("✅  " + tr("保存しました"))
        bus.settings_saved.emit()

    def _reset_to_defaults(self) -> None:
        if not LeeDialog.confirm(
            tr("確認"), tr("設定を初期値に戻しますか?"),
            ok_text=tr("リセット"), destructive=True, parent=self,
        ):
            return
        from app.core.config import DEFAULT_SETTINGS
        # 메모리 cfg 만 reset (저장은 따로 하지 않음 — save 버튼 누르면 commit)
        self._current_settings = dict(DEFAULT_SETTINGS)
        # UI 갱신
        try:
            self._load_data()
        except Exception as e:
            logger.warning(f"reset 후 _load_data 실패: {e}")
        self._show_toast(tr("初期値を読み込みました — 「保存」で確定"))

    # ── 토스트 ────────────────────────────────────────────────
    def _show_toast(self, msg: str) -> None:
        self._toast_lbl.setText(msg); self._toast_lbl.show()
        self._toast_anim.stop()
        self._toast_anim.setStartValue(0.0); self._toast_anim.setEndValue(1.0)
        try: self._toast_anim.finished.disconnect()
        except (RuntimeError, TypeError): pass
        self._toast_anim.start()
        self._toast_timer.start(3500)

    def _hide_toast(self) -> None:
        self._toast_anim.stop()
        self._toast_anim.setStartValue(1.0); self._toast_anim.setEndValue(0.0)
        self._toast_anim.finished.connect(self._toast_lbl.hide)
        self._toast_anim.start()

    # ── 테마 ─────────────────────────────────────────────────
    def apply_theme_custom(self) -> None:
        is_dark = self.is_dark
        self._header.set_theme(is_dark)
        self.seg_theme.set_theme(is_dark)
        self.seg_language.set_theme(is_dark)
        for r in self._rows:
            r.set_theme(is_dark)
        self._apply_qss(is_dark)

    def _apply_qss(self, d: bool) -> None:
        bg_app        = "#0A0B0F" if d else "#F5F6F8"
        bg_surface    = "#14161C" if d else "#FFFFFF"
        bg_surface_2  = "#1B1E26" if d else "#F0F2F5"
        bg_surface_3  = "#232730" if d else "#E6E9EE"
        fg_primary    = "#F2F4F7" if d else "#0B1220"
        fg_secondary  = "#A8B0BD" if d else "#4A5567"
        fg_tertiary   = "#6B7280" if d else "#8A93A6"
        bs            = "rgba(255,255,255,0.06)" if d else "rgba(11,18,32,0.06)"
        accent_bg     = "rgba(168,176,189,0.18)" if d else "rgba(168,176,189,0.10)"

        self.setStyleSheet(f"""
            QFrame#settingsOuterCard {{
                background: {bg_surface};
                border: 1px solid {bs};
                border-radius: 16px;
            }}
            QFrame#settingsLeftPane {{
                background: {bg_surface_2};
                border-top-left-radius: 16px;
                border-bottom-left-radius: 16px;
            }}
            QFrame#settingsVSep {{ background: {bs}; }}
            QFrame#settingsRightPane {{ background: {bg_surface}; }}

            QPushButton#settingsTab {{
                background: transparent;
                color: {fg_secondary};
                border: none; border-radius: 8px;
                text-align: left; padding: 8px 14px;
                font-size: 12.5px; font-weight: 600;
            }}
            QPushButton#settingsTab:hover {{
                background: {bg_surface_3}; color: {fg_primary};
            }}
            QPushButton#settingsTab[active="true"] {{
                background: {accent_bg};
                color: {fg_primary};
                font-weight: 800;
            }}

            QScrollArea#settingsScroll {{
                background: transparent; border: none;
            }}
            QWidget#settingsPanelInner {{ background: transparent; }}

            QLabel#settingsSectionTitle {{
                color: {fg_secondary}; background: transparent;
                font-size: 11px; font-weight: 800;
                letter-spacing: 0.06em;
                padding: 16px 0 6px 4px;
                text-transform: uppercase;
            }}
            QLabel#settingsNote {{
                color: {fg_tertiary}; background: transparent;
                font-size: 11px;
                padding: 4px 0 4px 4px;
            }}
            QLabel#settingsPath {{
                color: {fg_secondary}; background: transparent;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 10.5px;
            }}

            QFrame#settingsUserCard {{
                background: {bg_surface_2};
                border: 1px solid {bs};
                border-radius: 12px;
            }}
            QLabel#settingsAvatar {{
                background: {_C_INFO}; color: white;
                border-radius: 24px;
                font-size: 18px; font-weight: 800;
            }}
            QLabel#settingsUserName {{
                color: {fg_primary}; background: transparent;
                font-size: 14px; font-weight: 800;
            }}
            QLabel#settingsUserEmail {{
                color: {fg_tertiary}; background: transparent;
                font-size: 11px;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}

            QFrame#settingsFooter {{
                background: {bg_surface};
                border: 1px solid {bs};
                border-radius: 10px;
            }}
            QLabel#settingsToast {{
                color: {_C_OK}; background: transparent;
                font-size: 12.5px; font-weight: 700;
                padding: 0 8px;
            }}

            /* 컨트롤들 — 통일된 다크 톤 */
            QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit#settingsLineEdit, QLineEdit {{
                background: {bg_surface_2}; color: {fg_primary};
                border: 1px solid {bs}; border-radius: 8px;
                padding: 4px 10px;
                font-size: 12px;
            }}
            QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QLineEdit:focus {{
                border: 1px solid {_C_INFO};
            }}
            QComboBox QAbstractItemView {{
                background: {bg_surface_2}; color: {fg_primary};
                border: 1px solid {bs};
                selection-background-color: {accent_bg};
                outline: none;
            }}

            QCheckBox#settingsToggle {{ background: transparent; }}
            QCheckBox#settingsToggle::indicator {{
                width: 36px; height: 20px;
                background: {bg_surface_3};
                border: 1px solid {bs}; border-radius: 10px;
            }}
            QCheckBox#settingsToggle::indicator:checked {{
                background: {_C_OK}; border-color: {_C_OK};
            }}

            QTableWidget {{
                background: {bg_surface}; color: {fg_primary};
                border: 1px solid {bs}; border-radius: 10px;
                gridline-color: {bs};
                font-size: 12px;
            }}
            QHeaderView::section {{
                background: {bg_surface_2}; color: {fg_secondary};
                border: none; border-bottom: 1px solid {bs};
                padding: 6px 10px;
                font-size: 11px; font-weight: 800;
            }}

            QScrollBar:vertical {{ background: transparent; width: 8px; }}
            QScrollBar::handle:vertical {{
                background: rgba(168,176,189,0.4);
                border-radius: 4px; min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(168,176,189,0.7);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)


__all__ = ["SettingsWidget"]
