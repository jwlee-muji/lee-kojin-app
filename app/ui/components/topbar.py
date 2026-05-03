"""LeeTopBar — 메인 윈도우 상단 60px 바.

레이아웃 (디자인: handoff/LEE_PROJECT/varA-shell.jsx TopBar):
    [LOGO] LEE        [ Market 電力・燃料 | Operation Google | Tools AI・メモ ]
            電力モニター                                  [Search ⌘K]  [● オンライン] [☀] [李 田中]

- 좌: 32×32 로고 (기존 앱 아이콘) + "LEE" big + "電力モニター" 작게 letterspaced
- 중-좌: top tabs in sunken pill 컨테이너 (라벨 + 작은 hint)
- 중-우: 검색 (⌘K kbd 배지 내장, max 420px)
- 우: 온라인 pill + 테마 토글 + 유저 아바타 pill

Signals:
    search_text_changed(str)
    search_submitted(str)
    top_tab_changed(str)            — 활성 탭 키 (단일, "market" | "ops" | "tools")
    theme_toggle_clicked()
    user_clicked()
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

# 카테고리 키 + 라벨 + 힌트 (Sidebar 그룹 키와 일치해야 함)
TAB_KEYS = ("market", "ops", "tools")

_TAB_DEFS = [
    ("market", "マーケット",      "電力・燃料"),
    ("ops",    "オペレーション",   "Google"),
    ("tools",  "ツール",          "AI・メモ"),
]


class LeeTopBar(QFrame):
    """60px 상단 바 — 디자인 모킹업 1:1.

    Frameless MainWindow 의 타이틀바 역할도 겸함:
        - 우측에 min / max / close 버튼
        - 빈 영역은 드래그 zone (MainWindow 의 nativeEvent 가 hit-test 시 사용)
    """

    search_text_changed   = Signal(str)
    search_submitted      = Signal(str)
    top_tab_changed       = Signal(str)
    theme_toggle_clicked  = Signal()
    user_clicked          = Signal()
    minimize_clicked         = Signal()
    maximize_toggle_clicked  = Signal()
    close_clicked            = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("leeTopBar")
        self.setFixedHeight(60)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._tabs: dict[str, QPushButton] = {}
        # 초기 활성 탭 = None (모두 표시 상태). Top 탭 직접 클릭 시에만 활성화
        self._active_tab: Optional[str] = None
        self._is_dark = True

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 28, 0)
        layout.setSpacing(20)

        # ── 좌: macOS 풍 traffic light 도트 (red/yellow/green) ──
        # 로그인 윈도우와 동일 스타일. 좌측 끝에 배치.
        layout.addWidget(self._build_window_controls())

        # ── 좌: 로고 + 타이틀 (브랜드 아이콘은 기존 앱 아이콘) ───
        layout.addWidget(self._build_brand())

        # ── 중-좌: top tabs ────────────────────────────────────
        layout.addWidget(self._build_tabs())

        # ── 중-우: 검색 (확장) ─────────────────────────────────
        layout.addWidget(self._build_search(), 1)

        # ── 우: 온라인 pill + 테마 + 유저 ─────────────────────
        layout.addWidget(self._build_right())

        self._apply_qss()

    # ──────────────────────────────────────────────────────────
    # 빌더
    # ──────────────────────────────────────────────────────────
    def _build_brand(self) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)

        # 32×32 로고 — 기존 앱 아이콘 (의도적으로 모킹업의 그라데이션 대신 유지)
        self._logo = QLabel()
        self._logo.setObjectName("topBarLogo")
        self._logo.setFixedSize(32, 32)
        self._logo.setAlignment(Qt.AlignCenter)
        try:
            qicon = QApplication.instance().windowIcon()
            if not qicon.isNull():
                self._logo.setPixmap(qicon.pixmap(32, 32))
            else:
                self._logo.setText("⚡")
                self._logo.setStyleSheet("font-size: 22px; color: #FF7A45;")
        except Exception:
            self._logo.setText("⚡")
        h.addWidget(self._logo, 0, Qt.AlignVCenter)

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(0)
        title_top = QLabel("LEE")
        title_top.setObjectName("topBarTitleTop")
        title_sub = QLabel("電力モニター")
        title_sub.setObjectName("topBarTitleSub")
        text_box.addWidget(title_top)
        text_box.addWidget(title_sub)
        h.addLayout(text_box)

        return box

    def _build_tabs(self) -> QWidget:
        # sunken pill 컨테이너 안에 3 버튼
        wrap = QFrame()
        wrap.setObjectName("topBarTabWrap")
        h = QHBoxLayout(wrap)
        h.setContentsMargins(4, 4, 4, 4)
        h.setSpacing(2)

        for key, label, hint in _TAB_DEFS:
            btn = QPushButton()
            btn.setObjectName("topTabBtn")
            # 초기 모두 unchecked (active_tab = None)
            is_active = (self._active_tab is not None and key == self._active_tab)
            btn.setProperty("tabActive", is_active)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(is_active)
            btn.setFixedHeight(36)
            # 내부 레이아웃: 라벨 + hint
            inner = QHBoxLayout(btn)
            inner.setContentsMargins(14, 0, 14, 0)
            inner.setSpacing(6)
            lbl = QLabel(label); lbl.setObjectName("topTabLabel")
            hnt = QLabel(hint);  hnt.setObjectName("topTabHint")
            inner.addWidget(lbl)
            inner.addWidget(hnt)
            btn.clicked.connect(lambda _checked=False, k=key: self._on_tab_clicked(k))
            # QPushButton 의 sizeHint 가 inner layout 자식을 따라가지 않음 →
            # 라벨+힌트 폭에 맞춰 명시적으로 최소폭 지정
            label_metrics = lbl.fontMetrics().horizontalAdvance(label)
            hint_metrics  = hnt.fontMetrics().horizontalAdvance(hint)
            btn.setMinimumWidth(label_metrics + hint_metrics + 14 * 2 + 6 + 4)
            h.addWidget(btn)
            self._tabs[key] = btn

        return wrap

    def _build_search(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("topBarSearchWrap")
        wrap.setMaximumWidth(420)
        wrap.setFixedHeight(36)
        h = QHBoxLayout(wrap)
        h.setContentsMargins(10, 0, 6, 0)
        h.setSpacing(8)

        # 검색 아이콘
        search_icon = QLabel("🔍")
        search_icon.setObjectName("topBarSearchIcon")
        search_icon.setFixedWidth(16)
        h.addWidget(search_icon)

        # 입력 필드
        self._search = QLineEdit()
        self._search.setObjectName("topBarSearch")
        self._search.setPlaceholderText("検索...")
        self._search.setFrame(False)
        self._search.textChanged.connect(self.search_text_changed.emit)
        self._search.returnPressed.connect(
            lambda: self.search_submitted.emit(self._search.text())
        )
        h.addWidget(self._search, 1)

        # ⌘K kbd 배지
        kbd = QLabel("⌘K")
        kbd.setObjectName("topBarKbdBadge")
        kbd.setAlignment(Qt.AlignCenter)
        h.addWidget(kbd)

        return wrap

    def _build_window_controls(self) -> QWidget:
        """macOS 풍 traffic light 3 도트 — red(close) / yellow(min) / green(max).
        로그인 윈도우와 동일한 시각 언어."""
        wrap = QFrame()
        wrap.setObjectName("topBarWindowControls")
        h = QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0); h.setSpacing(8)

        # 1) Close (red, leftmost — macOS 관행)
        self._btn_close = QPushButton()
        self._btn_close.setObjectName("topBarTrafficDot")
        self._btn_close.setProperty("dotColor", "#FF5F57")
        self._btn_close.setFixedSize(12, 12)
        self._btn_close.setCursor(Qt.PointingHandCursor)
        self._btn_close.setFocusPolicy(Qt.NoFocus)
        self._btn_close.setToolTip("閉じる")
        self._btn_close.clicked.connect(self.close_clicked.emit)
        h.addWidget(self._btn_close)

        # 2) Minimize (yellow)
        self._btn_min = QPushButton()
        self._btn_min.setObjectName("topBarTrafficDot")
        self._btn_min.setProperty("dotColor", "#FEBC2E")
        self._btn_min.setFixedSize(12, 12)
        self._btn_min.setCursor(Qt.PointingHandCursor)
        self._btn_min.setFocusPolicy(Qt.NoFocus)
        self._btn_min.setToolTip("最小化")
        self._btn_min.clicked.connect(self.minimize_clicked.emit)
        h.addWidget(self._btn_min)

        # 3) Maximize / Restore (green)
        self._btn_max = QPushButton()
        self._btn_max.setObjectName("topBarTrafficDot")
        self._btn_max.setProperty("dotColor", "#28C840")
        self._btn_max.setFixedSize(12, 12)
        self._btn_max.setCursor(Qt.PointingHandCursor)
        self._btn_max.setFocusPolicy(Qt.NoFocus)
        self._btn_max.setToolTip("最大化")
        self._btn_max.clicked.connect(self.maximize_toggle_clicked.emit)
        h.addWidget(self._btn_max)

        return wrap

    def _build_right(self) -> QWidget:
        wrap = QFrame()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        # 온라인 pill
        self._online_pill = QLabel("●  オンライン")
        self._online_pill.setObjectName("topBarOnlinePill")
        h.addWidget(self._online_pill)

        # 테마 토글 버튼
        self._theme_btn = QPushButton("☀")
        self._theme_btn.setObjectName("topBarThemeBtn")
        self._theme_btn.setFixedSize(36, 36)
        self._theme_btn.setCursor(Qt.PointingHandCursor)
        self._theme_btn.clicked.connect(self.theme_toggle_clicked.emit)
        h.addWidget(self._theme_btn)

        # 유저 아바타 pill
        self._user_pill = QPushButton()
        self._user_pill.setObjectName("topBarUserPill")
        self._user_pill.setCursor(Qt.PointingHandCursor)
        self._user_pill.setFixedHeight(36)
        user_layout = QHBoxLayout(self._user_pill)
        user_layout.setContentsMargins(4, 4, 12, 4)
        user_layout.setSpacing(8)
        self._user_avatar = QLabel("?")
        self._user_avatar.setObjectName("topBarUserAvatar")
        self._user_avatar.setFixedSize(28, 28)
        self._user_avatar.setAlignment(Qt.AlignCenter)
        self._user_name = QLabel("Guest")
        self._user_name.setObjectName("topBarUserName")
        user_layout.addWidget(self._user_avatar)
        user_layout.addWidget(self._user_name)
        self._user_pill.clicked.connect(self.user_clicked.emit)
        h.addWidget(self._user_pill)

        return wrap

    # ──────────────────────────────────────────────────────────
    # 외부 API
    # ──────────────────────────────────────────────────────────
    def focus_search(self) -> None:
        """Ctrl+K → 검색창 포커스 + 전체 선택."""
        self._search.setFocus()
        self._search.selectAll()

    def search_text(self) -> str:
        return self._search.text()

    def clear_search(self) -> None:
        self._search.clear()

    def active_tab(self) -> Optional[str]:
        return self._active_tab

    def set_active_tab(self, key: Optional[str]) -> None:
        """key 가 None / 빈 문자열이면 모든 탭 해제 (필터 해제)."""
        norm = key if (key in self._tabs) else None
        if norm == self._active_tab:
            return
        self._active_tab = norm
        for k, btn in self._tabs.items():
            checked = (k == norm)
            btn.setChecked(checked)
            btn.setProperty("tabActive", checked)
            btn.style().unpolish(btn); btn.style().polish(btn)
            self._apply_tab_shadow(btn, checked)

    def _apply_tab_shadow(self, btn: QPushButton, active: bool) -> None:
        """활성 탭에 부드러운 drop shadow — QSS box-shadow 미지원 보완."""
        if active:
            eff = QGraphicsDropShadowEffect(btn)
            eff.setBlurRadius(12)
            eff.setOffset(0, 2)
            eff.setColor(QColor(0, 0, 0, 70))
            btn.setGraphicsEffect(eff)
        else:
            btn.setGraphicsEffect(None)

    def set_user(self, email: str = "", name: Optional[str] = None) -> None:
        """우상단 유저 아바타 + 이름 표시."""
        if not name:
            name = email.split("@", 1)[0] if "@" in email else (email or "Guest")
        initial = (name[:1] or "?").upper()
        self._user_avatar.setText(initial)
        self._user_name.setText(name)

    def set_online(self, online: bool) -> None:
        if online:
            self._online_pill.setText("●  オンライン")
            self._online_pill.setProperty("net", "online")
        else:
            self._online_pill.setText("●  オフライン")
            self._online_pill.setProperty("net", "offline")
        self._online_pill.style().unpolish(self._online_pill)
        self._online_pill.style().polish(self._online_pill)

    def set_theme_glyph(self, is_dark: bool) -> None:
        # 다크면 "Light 로 전환" 아이콘 (☀), 라이트면 "Dark 로 전환" 아이콘 (☾)
        self._theme_btn.setText("☀" if is_dark else "☾")
        self._is_dark = is_dark

    def set_maximized(self, maximized: bool) -> None:
        """최대화 상태 변경 — traffic dot 은 시각상 같지만 툴팁 갱신."""
        self._btn_max.setToolTip("元に戻す" if maximized else "最大化")

    def is_drag_zone(self, local_pos) -> bool:
        """topbar 좌표계 local_pos 가 드래그 가능 영역인지 판정.
        QPushButton/QLineEdit 같은 인터랙티브 자식 위면 False."""
        child = self.childAt(local_pos)
        if child is None or child is self:
            return True
        # 부모 체인을 따라 올라가며 인터랙티브 위젯 검사
        cur = child
        while cur is not None and cur is not self:
            if isinstance(cur, (QPushButton, QLineEdit)):
                return False
            cur = cur.parent()
        return True

    # ──────────────────────────────────────────────────────────
    # 내부
    # ──────────────────────────────────────────────────────────
    def _on_tab_clicked(self, key: str) -> None:
        # 같은 탭 다시 클릭 → 필터 해제 (None 으로 토글)
        if key == self._active_tab:
            self.set_active_tab(None)
            self.top_tab_changed.emit("")  # empty = filter off
            return
        self.set_active_tab(key)
        self.top_tab_changed.emit(key)

    def _apply_qss(self) -> None:
        # QSS 자체는 components_qss 에서 토큰 주입으로 적용됨.
        # 여기서는 동적 styling 없음.
        pass


# ──────────────────────────────────────────────────────────────
# QSS — components_qss 에서 결합 적용
# ──────────────────────────────────────────────────────────────
_QSS = """
QFrame#leeTopBar {{
    background: {bg_surface};
    border-bottom: 1px solid {border_subtle};
}}

/* ── 브랜드 ── */
QLabel#topBarLogo {{ background: transparent; }}
QLabel#topBarTitleTop {{
    font-size: 14px;
    font-weight: 800;
    color: {fg_primary};
    background: transparent;
    letter-spacing: -0.01em;
}}
QLabel#topBarTitleSub {{
    font-size: 9px;
    font-weight: 700;
    color: {fg_tertiary};
    background: transparent;
    letter-spacing: 0.1em;
}}

/* ── Top tabs (sunken pill 컨테이너) ── */
QFrame#topBarTabWrap {{
    background: {bg_surface_2};
    border-radius: 12px;
}}
QPushButton#topTabBtn {{
    background: transparent;
    border: none;
    border-radius: 9px;
    padding: 0;
}}
QPushButton#topTabBtn[tabActive="true"] {{
    background: {bg_surface};
}}
QPushButton#topTabBtn:hover[tabActive="false"] {{
    background: rgba(255,255,255,0.04);
}}
QLabel#topTabLabel {{
    font-size: 13px;
    font-weight: 600;
    color: {fg_secondary};
    background: transparent;
}}
QPushButton#topTabBtn[tabActive="true"] QLabel#topTabLabel {{
    color: {fg_primary};
}}
QLabel#topTabHint {{
    font-size: 10px;
    font-weight: 500;
    color: {fg_tertiary};
    background: transparent;
}}

/* ── 검색 ── */
QFrame#topBarSearchWrap {{
    background: {bg_surface_2};
    border: 1px solid {border};
    border-radius: 10px;
}}
QFrame#topBarSearchWrap:focus-within {{
    border-color: {accent};
}}
QLabel#topBarSearchIcon {{
    color: {fg_tertiary};
    background: transparent;
    font-size: 14px;
}}
QLineEdit#topBarSearch {{
    background: transparent;
    color: {fg_primary};
    border: none;
    font-size: 13px;
    selection-background-color: {selection_bg};
}}
QLabel#topBarKbdBadge {{
    background: {bg_surface};
    color: {fg_tertiary};
    border: 1px solid {border};
    border-radius: 4px;
    font-family: "JetBrains Mono", "Consolas", monospace;
    font-size: 10px;
    font-weight: 700;
    padding: 2px 6px;
}}

/* ── 우측 ── */
QLabel#topBarOnlinePill {{
    color: {c_ok};
    background: rgba(48,209,88,0.12);
    border: 1px solid rgba(48,209,88,0.25);
    border-radius: 999px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#topBarOnlinePill[net="offline"] {{
    color: {c_bad};
    background: rgba(255,69,58,0.12);
    border-color: rgba(255,69,58,0.25);
}}

QPushButton#topBarThemeBtn {{
    background: {bg_surface_2};
    color: {fg_secondary};
    border: 1px solid {border};
    border-radius: 10px;
    font-size: 16px;
}}
QPushButton#topBarThemeBtn:hover {{
    background: rgba(255,122,69,0.10);
    color: {accent};
    border-color: rgba(255,122,69,0.30);
}}

QPushButton#topBarUserPill {{
    background: {bg_surface_2};
    border: 1px solid {border};
    border-radius: 18px;
    padding: 0;
}}
QPushButton#topBarUserPill:hover {{
    background: rgba(255,255,255,0.06);
}}
QLabel#topBarUserAvatar {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 {c_ai},
        stop:1 {c_power}
    );
    color: #ffffff;
    border-radius: 14px;
    font-size: 11px;
    font-weight: 800;
}}
QLabel#topBarUserName {{
    color: {fg_primary};
    background: transparent;
    font-size: 12px;
    font-weight: 600;
}}

/* ── 윈도우 컨트롤 (macOS traffic light 도트) ── */
QFrame#topBarWindowControls {{
    background: transparent;
}}
QPushButton#topBarTrafficDot {{
    border: none;
    border-radius: 6px;
    padding: 0;
}}
QPushButton#topBarTrafficDot[dotColor="#FF5F57"] {{ background: #FF5F57; }}
QPushButton#topBarTrafficDot[dotColor="#FEBC2E"] {{ background: #FEBC2E; }}
QPushButton#topBarTrafficDot[dotColor="#28C840"] {{ background: #28C840; }}
QPushButton#topBarTrafficDot:hover {{
    /* hover 시 살짝 밝아지는 inner glow (Qt QSS 한계로 box-shadow 대신 border 사용) */
}}
QPushButton#topBarTrafficDot[dotColor="#FF5F57"]:hover {{ background: #FF7068; }}
QPushButton#topBarTrafficDot[dotColor="#FEBC2E"]:hover {{ background: #FFC944; }}
QPushButton#topBarTrafficDot[dotColor="#28C840"]:hover {{ background: #34D659; }}
QPushButton#topBarTrafficDot[dotColor="#FF5F57"]:pressed {{ background: #E84A42; }}
QPushButton#topBarTrafficDot[dotColor="#FEBC2E"]:pressed {{ background: #E6A91D; }}
QPushButton#topBarTrafficDot[dotColor="#28C840"]:pressed {{ background: #22B432; }}
"""


def qss(tokens: dict) -> str:
    return _QSS.format(**tokens)
