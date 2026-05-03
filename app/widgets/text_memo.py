"""テキストメモ ウィジェット — Phase 5.7 リニューアル.

데이터 소스: app/memos.json (기존 JSON 보존, SQLite 미사용)

디자인 출처: handoff/LEE_PROJECT/varA-detail-screens6.jsx MemoDetail
            handoff/LEE_PROJECT/varA-widgets.jsx MemoCard

[Card]
    MemoCard (대시보드)
        - LeeCard accent="memo" (#FFCC00)
        - LeeIconTile + 타이틀 + "X 件のメモ" sub
        - 최근 3 개 메모 미리보기 (제목 굵게 + 본문 2줄 클램프 + 날짜)
        - 우측 상단 + 버튼 (새 메모 추가)

[Detail page]
    TextMemoWidget
        - DetailHeader (← back, 노란 액센트, badge "X件")
        - 좌 300px: 검색 input + "+ 새 메모" + 메모 카드 리스트
        - 우 flex: 제목 input + 날짜 + 툴바 + 본문 QTextEdit (markdown 토글)
        - 자동 저장 (3 초 debounce)
        - Ctrl+N 새 메모 / Ctrl+S 저장 / Ctrl+F 검색 / Delete 삭제 (확인 다이얼로그)
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QPoint, QSize, QTimer, Signal
from PySide6.QtGui import (
    QAction, QIcon, QKeySequence, QPainter, QShortcut, QTextOption,
)
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QPushButton, QScrollArea, QSizePolicy, QTextEdit, QVBoxLayout,
    QWidget,
)

from app.core.events import bus
from app.core.i18n import tr
from app.ui.common import BaseWidget
from app.ui.components import (
    LeeCard, LeeDetailHeader, LeeDialog, LeeIconTile,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 토큰 / 정수
# ──────────────────────────────────────────────────────────────────────
_C_MEMO   = "#FFCC00"
_C_OK     = "#30D158"
_AUTOSAVE_DELAY_MS = 3000   # 3초 debounce

# 메모 색상 팔레트 (생성 순서대로 순환)
_COLOR_POOL = [
    "#FFCC00",  # yellow
    "#A78BFA",  # purple
    "#5856D6",  # indigo
    "#34C759",  # green
    "#5B8DEF",  # blue
    "#FF7A45",  # orange
    "#F25C7A",  # pink
    "#2EC4B6",  # teal
]


# ──────────────────────────────────────────────────────────────────────
# 데이터 레이어 (JSON)
# ──────────────────────────────────────────────────────────────────────
def _memo_file() -> Path:
    from app.core.config import APP_DIR
    return APP_DIR / "memos.json"


def _gen_id() -> str:
    """timestamp + 6자리 hash 로 안정적인 메모 id 생성."""
    raw = datetime.now().isoformat() + str(id(object()))
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _normalize_memo(m: dict) -> dict:
    """기존 JSON 메모를 새 스키마 (id, color) 로 정규화."""
    if "id" not in m:
        m["id"] = _gen_id()
    if "color" not in m or not m.get("color"):
        m["color"] = _COLOR_POOL[hash(m["id"]) % len(_COLOR_POOL)]
    if "updated" not in m:
        m["updated"] = m.get("created", datetime.now().strftime("%Y-%m-%d %H:%M"))
    return m


def _load_memos() -> list[dict]:
    f = _memo_file()
    if not f.exists():
        return []
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        return [_normalize_memo(dict(m)) for m in raw if isinstance(m, dict)]
    except (json.JSONDecodeError, ValueError, OSError) as e:
        logger.warning(f"메모 파일 읽기 실패: {e}")
        return []


def _save_memos(memos: list[dict]) -> None:
    try:
        _memo_file().write_text(
            json.dumps(memos, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        logger.error(f"메모 저장 실패: {e}")


# ──────────────────────────────────────────────────────────────────────
# A. MemoCard — 대시보드 카드
# ──────────────────────────────────────────────────────────────────────
class MemoCard(LeeCard):
    """テキストメモ 카드 — 최근 3 메모 미리보기.

    레이아웃:
        ┌─────────────────────────────────────────────────────┐
        │ [icon] テキストメモ                         [ + ]   │
        │        X 件のメモ                                   │
        │                                                      │
        │ ┃ メモ 1 タイトル                                    │
        │ ┃ 본문 2줄 클램프...                                  │
        │ ┃ 1/22 09:10                                         │
        │ ─────────────────                                    │
        │ ┃ メモ 2 タイトル ...                                │
        └─────────────────────────────────────────────────────┘
    """

    clicked    = Signal()
    new_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(accent_color="memo", interactive=True, parent=parent)
        self.setMinimumHeight(280)
        self._is_dark = True
        self._memos: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(0)

        # 헤더
        header = QHBoxLayout(); header.setSpacing(12); header.setContentsMargins(0, 0, 0, 12)
        self._icon = LeeIconTile(
            icon=QIcon(":/img/memo.svg"),
            color=_C_MEMO, size=40, radius=12,
        )
        header.addWidget(self._icon, 0, Qt.AlignTop)

        title_box = QVBoxLayout(); title_box.setSpacing(2); title_box.setContentsMargins(0, 0, 0, 0)
        self._title_lbl = QLabel(tr("テキストメモ"))
        self._title_lbl.setObjectName("memoCardTitle")
        self._sub_lbl = QLabel("")
        self._sub_lbl.setObjectName("memoCardSub")
        title_box.addWidget(self._title_lbl)
        title_box.addWidget(self._sub_lbl)
        header.addLayout(title_box, 1)

        # + 버튼
        self._btn_new = QPushButton("＋")
        self._btn_new.setObjectName("memoCardNewBtn")
        self._btn_new.setFixedSize(28, 28)
        self._btn_new.setCursor(Qt.PointingHandCursor)
        self._btn_new.setToolTip(tr("新しいメモ"))
        self._btn_new.clicked.connect(self._on_new_clicked)
        header.addWidget(self._btn_new, 0, Qt.AlignTop)

        layout.addLayout(header)

        # 미리보기 슬롯 (3개 고정)
        self._slots: list[_MemoCardSlot] = []
        for _ in range(3):
            slot = _MemoCardSlot()
            layout.addWidget(slot)
            layout.addSpacing(8)
            self._slots.append(slot)

        # 데이터 없을 때
        self._empty = QLabel(tr("メモがまだありません"))
        self._empty.setObjectName("memoCardEmpty")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setMinimumHeight(80)
        layout.addWidget(self._empty)
        self._empty.setVisible(False)   # setVisible 은 layout 추가 후

        layout.addStretch()
        self._apply_local_qss()
        self.set_memos([])

    # ── 외부 API ─────────────────────────────────────────────
    def set_memos(self, memos: list[dict]) -> None:
        """전체 메모 목록을 받아 최근 3개만 표시."""
        self._memos = list(memos) if memos else []
        # 수정일 기준 정렬 (내림차순)
        sorted_memos = sorted(
            self._memos,
            key=lambda m: m.get("updated", m.get("created", "")),
            reverse=True,
        )
        top3 = sorted_memos[:3]

        self._sub_lbl.setText(
            tr("{0} 件のメモ").format(len(self._memos))
        )

        if not top3:
            for slot in self._slots:
                slot.setVisible(False)
            self._empty.setVisible(True)
            return

        self._empty.setVisible(False)
        for i, slot in enumerate(self._slots):
            if i < len(top3):
                slot.set_memo(top3[i], is_dark=self._is_dark)
                slot.setVisible(True)
            else:
                slot.setVisible(False)

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        for slot in self._slots:
            slot.set_theme(is_dark)
        self._apply_local_qss()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            # + 버튼 영역 클릭은 별도 처리
            child = self.childAt(event.pos())
            if child is self._btn_new:
                return  # 버튼 자체에서 처리
            self.clicked.emit()
        super().mousePressEvent(event)

    def _on_new_clicked(self) -> None:
        self.new_clicked.emit()

    def _apply_local_qss(self) -> None:
        is_dark = self._is_dark
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        bg_surface_2 = "#1B1E26" if is_dark else "#F0F2F5"
        border       = "rgba(255,255,255,0.10)" if is_dark else "rgba(11,18,32,0.10)"
        self.setStyleSheet(f"""
            QLabel#memoCardTitle {{
                font-size: 13px; font-weight: 600;
                color: {fg_secondary}; background: transparent;
            }}
            QLabel#memoCardSub {{
                font-size: 11px; color: {fg_tertiary};
                background: transparent;
            }}
            QPushButton#memoCardNewBtn {{
                background: {bg_surface_2};
                color: {_C_MEMO};
                border: 1px solid {border};
                border-radius: 8px;
                font-size: 16px; font-weight: 700;
            }}
            QPushButton#memoCardNewBtn:hover {{
                background: rgba(255,204,0,0.18);
                border: 1px solid {_C_MEMO};
            }}
            QLabel#memoCardEmpty {{
                font-size: 11px; color: {fg_tertiary};
                background: transparent; font-style: italic;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# A1. _MemoCardSlot — 대시보드 카드 안 단일 미리보기 슬롯
# ──────────────────────────────────────────────────────────────────────
class _MemoCardSlot(QFrame):
    """3 줄 미리보기 (제목 + 본문 클램프 + 날짜) + 좌측 색상 보더."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("memoCardSlot")
        self._is_dark = True
        self._color = _C_MEMO

        self.setFixedHeight(64)
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 6, 10, 6); v.setSpacing(2)

        self._title_lbl = QLabel("")
        self._title_lbl.setObjectName("slotTitle")
        v.addWidget(self._title_lbl)

        self._body_lbl = QLabel("")
        self._body_lbl.setObjectName("slotBody")
        self._body_lbl.setWordWrap(True)
        v.addWidget(self._body_lbl, 1)

        self._date_lbl = QLabel("")
        self._date_lbl.setObjectName("slotDate")
        v.addWidget(self._date_lbl)

        self._apply_qss()

    def set_memo(self, memo: dict, *, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._color = memo.get("color", _C_MEMO)
        self._title_lbl.setText(self._elide(memo.get("title") or tr("(無題)"), 40))
        body = (memo.get("content") or "").replace("\n", " ").strip()
        self._body_lbl.setText(self._elide(body, 90))
        self._date_lbl.setText(
            self._fmt_date(memo.get("updated") or memo.get("created", ""))
        )
        self._apply_qss()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    @staticmethod
    def _elide(text: str, n: int) -> str:
        return text if len(text) <= n else text[:n] + "…"

    @staticmethod
    def _fmt_date(iso_or_str: str) -> str:
        if not iso_or_str:
            return ""
        # "2026-05-02 09:10" → "5/2 09:10"
        try:
            dt = datetime.strptime(iso_or_str[:16], "%Y-%m-%d %H:%M")
            return dt.strftime("%-m/%-d %H:%M") if hasattr(datetime, "strftime") else iso_or_str
        except Exception:
            try:
                dt = datetime.strptime(iso_or_str[:16], "%Y-%m-%d %H:%M")
                # Windows 호환: %-m 미지원 → 수동 포맷
                return f"{dt.month}/{dt.day} {dt.strftime('%H:%M')}"
            except Exception:
                return iso_or_str[:16]

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        bg_surface_2 = "#1B1E26" if is_dark else "#F0F2F5"
        # color soft 배경 = color @ 10%
        r, g, b = self._hex_to_rgb(self._color)
        bg = f"rgba({r},{g},{b},0.10)"
        self.setStyleSheet(f"""
            QFrame#memoCardSlot {{
                background: {bg};
                border: none;
                border-left: 3px solid {self._color};
                border-radius: 10px;
            }}
            QLabel#slotTitle {{
                font-size: 12px; font-weight: 700;
                color: {fg_primary}; background: transparent;
            }}
            QLabel#slotBody {{
                font-size: 11px;
                color: {fg_secondary}; background: transparent;
            }}
            QLabel#slotDate {{
                font-size: 9px;
                font-family: "JetBrains Mono", "Consolas", monospace;
                color: {fg_tertiary}; background: transparent;
            }}
        """)

    @staticmethod
    def _hex_to_rgb(s: str) -> tuple[int, int, int]:
        h = s.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# ──────────────────────────────────────────────────────────────────────
# B. _MemoListItem — 디테일 페이지 좌측 리스트 카드
# ──────────────────────────────────────────────────────────────────────
class _MemoListItem(QFrame):
    """좌측 리스트의 단일 메모 카드 (color dot + title + date + body 클램프).

    Signals
    -------
    clicked(memo_id: str)
    context_requested(memo_id: str, global_pos: QPoint)
    """

    clicked           = Signal(str)
    context_requested = Signal(str, QPoint)

    def __init__(self, memo: dict, *, is_dark: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("memoListItem")
        self._is_dark = is_dark
        self._memo = memo
        self._active = False
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)

        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12); v.setSpacing(4)

        head = QHBoxLayout(); head.setContentsMargins(0, 0, 0, 0); head.setSpacing(8)
        self._dot = QLabel("●")
        self._dot.setObjectName("liDot")
        self._dot.setFixedWidth(10)
        head.addWidget(self._dot)
        self._title_lbl = QLabel(memo.get("title") or tr("(無題)"))
        self._title_lbl.setObjectName("liTitle")
        head.addWidget(self._title_lbl, 1)
        v.addLayout(head)

        self._date_lbl = QLabel(memo.get("updated") or memo.get("created", ""))
        self._date_lbl.setObjectName("liDate")
        v.addWidget(self._date_lbl)

        body = (memo.get("content") or "").replace("\n", " ").strip()
        self._body_lbl = QLabel(self._elide(body, 80))
        self._body_lbl.setObjectName("liBody")
        self._body_lbl.setWordWrap(True)
        v.addWidget(self._body_lbl)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        self._apply_qss()

    @staticmethod
    def _elide(text: str, n: int) -> str:
        return text if len(text) <= n else text[:n] + "…"

    def update_memo(self, memo: dict) -> None:
        self._memo = memo
        self._title_lbl.setText(memo.get("title") or tr("(無題)"))
        self._date_lbl.setText(memo.get("updated") or memo.get("created", ""))
        body = (memo.get("content") or "").replace("\n", " ").strip()
        self._body_lbl.setText(self._elide(body, 80))
        self._apply_qss()

    def memo_id(self) -> str:
        return self._memo.get("id", "")

    def color(self) -> str:
        return self._memo.get("color", _C_MEMO)

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self._apply_qss()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.memo_id())
        super().mousePressEvent(event)

    def _on_context_menu(self, pos: QPoint) -> None:
        self.context_requested.emit(self.memo_id(), self.mapToGlobal(pos))

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        bg_surface   = "#14161C" if is_dark else "#FFFFFF"
        bg_surface_2 = "#1B1E26" if is_dark else "#F0F2F5"
        border_subtle = "rgba(255,255,255,0.06)" if is_dark else "rgba(11,18,32,0.06)"
        color = self.color()

        if self._active:
            bg = bg_surface
            border = f"1.5px solid {color}"
        else:
            bg = bg_surface_2
            border = f"1px solid {border_subtle}"
        self.setStyleSheet(f"""
            QFrame#memoListItem {{
                background: {bg};
                border: {border};
                border-radius: 12px;
            }}
            QFrame#memoListItem:hover {{
                border: 1px solid {color};
            }}
            QLabel#liDot {{
                color: {color}; background: transparent;
                font-size: 10px;
            }}
            QLabel#liTitle {{
                font-size: 12px; font-weight: 800;
                color: {fg_primary}; background: transparent;
            }}
            QLabel#liDate {{
                font-size: 10px;
                font-family: "JetBrains Mono", "Consolas", monospace;
                color: {fg_tertiary}; background: transparent;
            }}
            QLabel#liBody {{
                font-size: 11px;
                color: {fg_secondary}; background: transparent;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# C. TextMemoWidget — 디테일 페이지
# ──────────────────────────────────────────────────────────────────────
class TextMemoWidget(BaseWidget):
    """텍스트메모 디테일 — DetailHeader + 좌 리스트 + 우 에디터 + 자동 저장."""

    # 외부 동기화 시그널 (대시보드 카드용)
    memos_changed = Signal(list)

    def __init__(self):
        super().__init__()
        self._memos: list[dict] = []
        self._selected_id: Optional[str] = None
        self._dirty = False
        self._suppress_dirty = False

        # 자동 저장 타이머 (3초 debounce)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(_AUTOSAVE_DELAY_MS)
        self._autosave_timer.timeout.connect(self._auto_save)

        # 검색 debounce
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(150)
        self._search_timer.timeout.connect(self._on_search_changed)

        # 리스트 row id → 위젯 lookup
        self._items: dict[str, _MemoListItem] = {}

        self._build_ui()
        # 모든 위젯 생성 후 초기 비활성화 적용
        self._set_editor_enabled(False)
        self._load_all()
        self._install_shortcuts()

    # ──────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        scroll_outer = QVBoxLayout()
        scroll_outer.setContentsMargins(0, 0, 0, 0); scroll_outer.setSpacing(0)

        content = QWidget()
        content.setObjectName("memoPageContent")
        outer.addWidget(content, 1)

        root = QVBoxLayout(content)
        root.setContentsMargins(28, 22, 28, 22); root.setSpacing(16)

        # 1) DetailHeader
        self._header = LeeDetailHeader(
            title=tr("メモ"),
            subtitle=tr("テキスト・プロンプトを保存"),
            accent=_C_MEMO,
            icon_qicon=QIcon(":/img/memo.svg"),
            badge="",
            show_export=False,
        )
        self._header.back_clicked.connect(lambda: bus.page_requested.emit(0))
        root.addWidget(self._header)

        # 2) 본문 (2 col)
        body = QHBoxLayout(); body.setSpacing(16)
        body.addWidget(self._build_left_pane(), 0)
        body.addWidget(self._build_right_pane(), 1)
        root.addLayout(body, 1)

        # 3) 상태바
        st_row = QHBoxLayout(); st_row.setSpacing(10)
        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("memoStatusLbl")
        st_row.addWidget(self._status_lbl)
        st_row.addStretch()
        self._char_lbl = QLabel("")
        self._char_lbl.setObjectName("memoCharLbl")
        st_row.addWidget(self._char_lbl)
        root.addLayout(st_row)

    def _build_left_pane(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("memoLeftPane")
        wrap.setFixedWidth(300)
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(10)

        # 검색
        self._search_input = QLineEdit()
        self._search_input.setObjectName("memoSearch")
        self._search_input.setPlaceholderText("🔍  " + tr("検索..."))
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setFixedHeight(36)
        self._search_input.textChanged.connect(lambda _: self._search_timer.start())
        v.addWidget(self._search_input)

        # + 새 메모
        self._btn_new = QPushButton("＋  " + tr("新しいメモ"))
        self._btn_new.setObjectName("memoNewBtn")
        self._btn_new.setFixedHeight(40)
        self._btn_new.setCursor(Qt.PointingHandCursor)
        self._btn_new.clicked.connect(self._new_memo)
        v.addWidget(self._btn_new)

        # 리스트 (ScrollArea)
        self._list_scroll = QScrollArea()
        self._list_scroll.setObjectName("memoListScroll")
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setFrameShape(QFrame.NoFrame)
        self._list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._list_inner = QWidget()
        self._list_layout = QVBoxLayout(self._list_inner)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(8)
        self._list_layout.addStretch()  # 마지막에 stretch (위에서 insertWidget)
        self._list_scroll.setWidget(self._list_inner)
        v.addWidget(self._list_scroll, 1)

        self._left_pane = wrap
        self._apply_left_qss()
        return wrap

    def _build_right_pane(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("memoEditor")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(28, 22, 28, 22); v.setSpacing(14)

        # 헤더 (color dot + title + date)
        head = QHBoxLayout(); head.setContentsMargins(0, 0, 0, 0); head.setSpacing(12)
        self._color_dot = QLabel("")
        self._color_dot.setObjectName("editorDot")
        self._color_dot.setFixedSize(16, 16)
        head.addWidget(self._color_dot, 0, Qt.AlignVCenter)

        self._title_input = QLineEdit()
        self._title_input.setObjectName("editorTitle")
        self._title_input.setPlaceholderText(tr("タイトル"))
        self._title_input.textChanged.connect(self._mark_dirty)
        head.addWidget(self._title_input, 1)

        self._date_lbl = QLabel("")
        self._date_lbl.setObjectName("editorDate")
        head.addWidget(self._date_lbl, 0, Qt.AlignRight | Qt.AlignVCenter)
        v.addLayout(head)

        # 툴바 (rich-text WYSIWYG 헬퍼 + 액션) — 모든 상황에서 서식이 보이도록
        toolbar = QHBoxLayout(); toolbar.setContentsMargins(0, 0, 0, 0); toolbar.setSpacing(6)
        for label, action_id, tooltip in [
            ("H1",   "h1",     tr("見出し 1")),
            ("H2",   "h2",     tr("見出し 2")),
            ("B",    "bold",   tr("太字 (Ctrl+B)")),
            ("I",    "italic", tr("斜体 (Ctrl+I)")),
            ("U",    "under",  tr("下線 (Ctrl+U)")),
            ("S",    "strike", tr("打消し線")),
            ("•",    "ul",     tr("箇条書き")),
            ("1.",   "ol",     tr("番号付きリスト")),
            ("🔗",   "link",   tr("リンク")),
            ("</>",  "code",   tr("インライン コード")),
        ]:
            b = QPushButton(label)
            b.setObjectName("editorToolBtn")
            b.setFixedSize(38, 32)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(tooltip)
            b.clicked.connect(lambda _=False, aid=action_id: self._apply_format(aid))
            toolbar.addWidget(b)

        toolbar.addStretch()

        self._btn_copy = QPushButton(tr("📋 コピー"))
        self._btn_copy.setObjectName("editorActionBtn")
        self._btn_copy.setFixedHeight(32)
        self._btn_copy.setCursor(Qt.PointingHandCursor)
        self._btn_copy.clicked.connect(self._copy_content)
        toolbar.addWidget(self._btn_copy)

        self._btn_save = QPushButton(tr("保存"))
        self._btn_save.setObjectName("editorSaveBtn")
        self._btn_save.setFixedHeight(32)
        self._btn_save.setCursor(Qt.PointingHandCursor)
        self._btn_save.clicked.connect(self._save_now)
        toolbar.addWidget(self._btn_save)

        self._btn_delete = QPushButton(tr("削除"))
        self._btn_delete.setObjectName("editorDeleteBtn")
        self._btn_delete.setFixedHeight(32)
        self._btn_delete.setCursor(Qt.PointingHandCursor)
        self._btn_delete.clicked.connect(self._delete_selected)
        toolbar.addWidget(self._btn_delete)

        v.addLayout(toolbar)

        # 태그 입력
        self._tags_input = QLineEdit()
        self._tags_input.setObjectName("editorTags")
        self._tags_input.setPlaceholderText(tr("タグ (カンマ区切り)"))
        self._tags_input.setFixedHeight(28)
        self._tags_input.textChanged.connect(self._mark_dirty)
        v.addWidget(self._tags_input)

        # 본문 (QTextEdit, rich-text WYSIWYG: Markdown 으로 로드/저장하지만
        # 편집/표시는 모두 렌더링된 서식 상태)
        self._body = QTextEdit()
        self._body.setObjectName("editorBody")
        self._body.setPlaceholderText(tr("テキストを入力 — 書式がそのまま表示されます"))
        self._body.setAcceptRichText(True)
        self._body.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self._body.textChanged.connect(self._mark_dirty)
        v.addWidget(self._body, 1)

        self._right_pane = wrap
        self._apply_editor_qss()
        return wrap

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._new_memo)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._save_now)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self._search_input.setFocus())
        QShortcut(QKeySequence(Qt.Key_Delete), self._body,
                  context=Qt.WidgetShortcut, activated=lambda: None)  # body 안 Delete 는 텍스트
        # Delete 키는 list 가 포커스를 갖고 있을 때만 발화
        QShortcut(QKeySequence(Qt.Key_Delete), self._list_inner,
                  context=Qt.WidgetWithChildrenShortcut, activated=self._delete_selected)

    # ──────────────────────────────────────────────────────────
    # 스타일 / 테마
    # ──────────────────────────────────────────────────────────
    def _apply_page_qss(self) -> None:
        bg_app = "#0A0B0F" if self.is_dark else "#F5F6F8"
        self.setStyleSheet(f"""
            TextMemoWidget {{ background: {bg_app}; }}
            QWidget#memoPageContent {{ background: {bg_app}; }}
            QLabel#memoStatusLbl {{
                font-size: 11px; font-weight: 600;
                color: {_C_OK};
                background: rgba(48,209,88,0.10);
                border: 1px solid rgba(48,209,88,0.25);
                border-radius: 999px;
                padding: 3px 10px;
            }}
            QLabel#memoCharLbl {{
                font-size: 11px;
                color: {"#A8B0BD" if self.is_dark else "#4A5567"};
                background: transparent;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
        """)

    def _apply_left_qss(self) -> None:
        is_dark = self.is_dark
        fg_primary    = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary  = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary   = "#6B7280" if is_dark else "#8A93A6"
        bg_surface    = "#14161C" if is_dark else "#FFFFFF"
        bg_surface_2  = "#1B1E26" if is_dark else "#F0F2F5"
        border        = "rgba(255,255,255,0.10)" if is_dark else "rgba(11,18,32,0.10)"
        self._left_pane.setStyleSheet(f"""
            QFrame#memoLeftPane {{ background: transparent; }}
            QLineEdit#memoSearch {{
                background: {bg_surface};
                color: {fg_primary};
                border: 1px solid {border};
                border-radius: 12px;
                padding: 0 12px;
                font-size: 12px;
            }}
            QLineEdit#memoSearch:focus {{
                border: 1px solid {_C_MEMO};
            }}
            QPushButton#memoNewBtn {{
                background: transparent;
                color: {fg_secondary};
                border: 1px dashed {border};
                border-radius: 12px;
                font-size: 12px; font-weight: 700;
            }}
            QPushButton#memoNewBtn:hover {{
                color: {_C_MEMO};
                border: 1px dashed {_C_MEMO};
                background: rgba(255,204,0,0.08);
            }}
            QScrollArea#memoListScroll {{
                background: transparent;
                border: none;
            }}
        """)

    def _apply_editor_qss(self) -> None:
        is_dark = self.is_dark
        fg_primary    = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary  = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary   = "#6B7280" if is_dark else "#8A93A6"
        bg_surface    = "#14161C" if is_dark else "#FFFFFF"
        bg_surface_2  = "#1B1E26" if is_dark else "#F0F2F5"
        border_subtle = "rgba(255,255,255,0.06)" if is_dark else "rgba(11,18,32,0.06)"
        border        = "rgba(255,255,255,0.10)" if is_dark else "rgba(11,18,32,0.10)"
        self._right_pane.setStyleSheet(f"""
            QFrame#memoEditor {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 18px;
            }}
            QLabel#editorDot {{
                background: {_C_MEMO};
                border-radius: 4px;
            }}
            QLineEdit#editorTitle {{
                background: transparent;
                color: {fg_primary};
                border: none;
                font-size: 22px; font-weight: 800;
                letter-spacing: -0.015em;
            }}
            QLineEdit#editorTitle:disabled {{
                color: {fg_tertiary};
            }}
            QLabel#editorDate {{
                font-size: 11px;
                font-family: "JetBrains Mono", "Consolas", monospace;
                color: {fg_tertiary}; background: transparent;
            }}
            QLineEdit#editorTags {{
                background: {bg_surface_2};
                color: {"#5B8DEF"};
                border: 1px solid {border_subtle};
                border-radius: 8px;
                padding: 0 10px;
                font-size: 11px; font-weight: 600;
            }}
            QLineEdit#editorTags:focus {{
                border: 1px solid #5B8DEF;
            }}
            QPushButton#editorToolBtn {{
                background: {bg_surface_2};
                color: {fg_secondary};
                border: 1px solid {border_subtle};
                border-radius: 8px;
                font-size: 12px; font-weight: 700;
            }}
            QPushButton#editorToolBtn:hover {{
                color: {_C_MEMO};
                border: 1px solid {_C_MEMO};
            }}
            QPushButton#editorActionBtn {{
                background: {bg_surface_2};
                color: {fg_secondary};
                border: 1px solid {border_subtle};
                border-radius: 8px;
                padding: 0 12px;
                font-size: 11px; font-weight: 700;
            }}
            QPushButton#editorActionBtn:hover {{
                background: {border};
            }}
            QPushButton#editorSaveBtn {{
                background: {_C_MEMO};
                color: #1A1300;
                border: none;
                border-radius: 8px;
                padding: 0 14px;
                font-size: 11px; font-weight: 800;
            }}
            QPushButton#editorSaveBtn:hover {{ background: #FFD933; }}
            QPushButton#editorSaveBtn:disabled {{
                background: {bg_surface_2};
                color: {fg_tertiary};
            }}
            QPushButton#editorDeleteBtn {{
                background: rgba(255,69,58,0.12);
                color: #FF453A;
                border: 1px solid rgba(255,69,58,0.30);
                border-radius: 8px;
                padding: 0 12px;
                font-size: 11px; font-weight: 700;
            }}
            QPushButton#editorDeleteBtn:hover {{
                background: rgba(255,69,58,0.22);
            }}
            QPushButton#editorDeleteBtn:disabled {{
                background: {bg_surface_2};
                color: {fg_tertiary};
                border: 1px solid {border_subtle};
            }}
            QTextEdit#editorBody {{
                background: {bg_surface};
                color: {fg_primary};
                border: 1px solid {border_subtle};
                border-radius: 12px;
                padding: 12px 14px;
                font-size: 14px;
                selection-background-color: rgba(255,204,0,0.25);
            }}
            QTextEdit#editorBody:focus {{
                border: 1px solid {_C_MEMO};
            }}
            QTextEdit#editorBody:disabled {{
                color: {fg_tertiary};
                background: {bg_surface_2};
            }}
        """)

    # ──────────────────────────────────────────────────────────
    # BaseWidget hooks
    # ──────────────────────────────────────────────────────────
    def apply_theme_custom(self) -> None:
        d = self.is_dark
        self._header.set_theme(d)
        for it in self._items.values():
            it.set_theme(d)
        self._apply_page_qss()
        self._apply_left_qss()
        self._apply_editor_qss()

    def apply_settings_custom(self) -> None:
        # 메모는 외부 설정 의존 X
        pass

    # ──────────────────────────────────────────────────────────
    # 데이터 로드
    # ──────────────────────────────────────────────────────────
    def _load_all(self) -> None:
        self._memos = _load_memos()
        # 수정일 내림차순 정렬
        self._memos.sort(
            key=lambda m: m.get("updated", m.get("created", "")),
            reverse=True,
        )
        self._rebuild_list()
        self.memos_changed.emit(list(self._memos))

    def _rebuild_list(self, filter_text: str = "") -> None:
        # 기존 위젯 제거
        for it in list(self._items.values()):
            self._list_layout.removeWidget(it)
            it.setParent(None)
            it.deleteLater()
        self._items.clear()

        ft = filter_text.strip().lower()
        displayed = 0
        for memo in self._memos:
            if ft:
                hay = " ".join([
                    memo.get("title", ""),
                    memo.get("tags", ""),
                    memo.get("content", ""),
                ]).lower()
                if ft not in hay:
                    continue
            item = _MemoListItem(memo, is_dark=self.is_dark)
            item.clicked.connect(self._on_item_clicked)
            item.context_requested.connect(self._on_item_context)
            self._list_layout.insertWidget(displayed, item)
            self._items[memo["id"]] = item
            displayed += 1

        # 헤더 badge
        self._header.set_badge(tr("{0}件").format(len(self._memos)))

        # 활성 항목 설정
        if self._selected_id and self._selected_id in self._items:
            self._items[self._selected_id].set_active(True)
        elif self._selected_id and self._selected_id not in self._items:
            # 검색으로 가려진 경우 — 활성 유지하지만 list 에는 안 보임
            pass

    def _on_search_changed(self) -> None:
        self._rebuild_list(self._search_input.text())

    # ──────────────────────────────────────────────────────────
    # 선택
    # ──────────────────────────────────────────────────────────
    def _on_item_clicked(self, memo_id: str) -> None:
        # 미저장 변경 있으면 자동 저장 후 전환
        if self._dirty:
            self._save_now()
        self._select(memo_id)

    def _select(self, memo_id: str) -> None:
        # 활성 시각 갱신
        if self._selected_id and self._selected_id in self._items:
            self._items[self._selected_id].set_active(False)
        self._selected_id = memo_id
        if memo_id in self._items:
            self._items[memo_id].set_active(True)

        memo = self._find_memo(memo_id)
        if memo is None:
            self._set_editor_enabled(False)
            return

        self._suppress_dirty = True
        self._title_input.setText(memo.get("title", ""))
        self._tags_input.setText(memo.get("tags", ""))
        self._suppress_dirty = False
        # 본문 — HTML / Markdown / plain 자동 판별 후 렌더
        self._load_body_content(memo.get("content", ""))

        self._color_dot.setStyleSheet(
            f"background: {memo.get('color', _C_MEMO)}; border-radius: 4px;"
        )
        self._date_lbl.setText(memo.get("updated") or memo.get("created", ""))
        self._dirty = False
        self._set_editor_enabled(True)
        self._update_char_count()

    def _set_editor_enabled(self, enabled: bool) -> None:
        self._title_input.setEnabled(enabled)
        self._tags_input.setEnabled(enabled)
        self._body.setReadOnly(not enabled)
        self._btn_save.setEnabled(enabled)
        self._btn_delete.setEnabled(enabled)
        self._btn_copy.setEnabled(enabled)
        if not enabled:
            self._suppress_dirty = True
            self._title_input.clear()
            self._tags_input.clear()
            self._body.clear()
            self._date_lbl.clear()
            self._color_dot.setStyleSheet("background: transparent; border-radius: 4px;")
            self._suppress_dirty = False
            self._dirty = False
            self._char_lbl.setText("")

    def _find_memo(self, memo_id: str) -> Optional[dict]:
        return next((m for m in self._memos if m.get("id") == memo_id), None)

    # ──────────────────────────────────────────────────────────
    # CRUD
    # ──────────────────────────────────────────────────────────
    def _new_memo(self) -> None:
        # 미저장 변경 자동 저장
        if self._dirty:
            self._save_now()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_id = _gen_id()
        memo = {
            "id":      new_id,
            "title":   tr("新しいメモ"),
            "tags":    "",
            "content": "",
            "color":   _COLOR_POOL[len(self._memos) % len(_COLOR_POOL)],
            "created": now,
            "updated": now,
        }
        self._memos.insert(0, memo)
        _save_memos(self._memos)
        self._rebuild_list(self._search_input.text())
        self._select(new_id)
        self._title_input.setFocus()
        self._title_input.selectAll()
        self.memos_changed.emit(list(self._memos))
        self._show_status(tr("メモを作成しました"))

    def _save_now(self) -> None:
        """수동 저장 (Ctrl+S 또는 저장 버튼). rich-text → Markdown 변환 후 저장."""
        self._autosave_timer.stop()
        if not self._selected_id:
            return
        memo = self._find_memo(self._selected_id)
        if memo is None:
            return
        title   = self._title_input.text().strip() or tr("無題のメモ")
        tags    = self._tags_input.text().strip()
        content = self._body_markdown()
        # 변경된 경우만 updated 갱신
        if (memo.get("title") != title or memo.get("tags") != tags
                or memo.get("content") != content):
            memo["title"]   = title
            memo["tags"]    = tags
            memo["content"] = content
            memo["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        _save_memos(self._memos)
        self._dirty = False
        # 리스트 카드 미리보기 갱신
        if self._selected_id in self._items:
            self._items[self._selected_id].update_memo(memo)
        self._date_lbl.setText(memo.get("updated", ""))
        self.memos_changed.emit(list(self._memos))
        self._show_status(tr("保存しました"))

    def _auto_save(self) -> None:
        """3초 debounce 자동 저장 — 조용히 동작 (status 토스트 없음)."""
        if not self._dirty or not self._selected_id:
            return
        memo = self._find_memo(self._selected_id)
        if memo is None:
            return
        title   = self._title_input.text().strip() or tr("無題のメモ")
        tags    = self._tags_input.text().strip()
        content = self._body_markdown()
        if (memo.get("title") == title and memo.get("tags") == tags
                and memo.get("content") == content):
            self._dirty = False
            return
        memo["title"]   = title
        memo["tags"]    = tags
        memo["content"] = content
        memo["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        _save_memos(self._memos)
        self._dirty = False
        if self._selected_id in self._items:
            self._items[self._selected_id].update_memo(memo)
        self._date_lbl.setText(memo.get("updated", ""))
        self.memos_changed.emit(list(self._memos))
        self._show_status(tr("自動保存"))

    def _delete_selected(self) -> None:
        if not self._selected_id:
            return
        memo = self._find_memo(self._selected_id)
        if memo is None:
            return
        title = memo.get("title", tr("無題のメモ"))
        ok = LeeDialog.confirm(
            tr("削除の確認"),
            tr("「{0}」を削除しますか?").format(title),
            ok_text=tr("削除"),
            destructive=True,
            parent=self,
        )
        if not ok:
            return
        self._memos = [m for m in self._memos if m.get("id") != self._selected_id]
        _save_memos(self._memos)
        self._selected_id = None
        self._rebuild_list(self._search_input.text())
        self._set_editor_enabled(False)
        self.memos_changed.emit(list(self._memos))
        self._show_status(tr("削除しました"))

    # ──────────────────────────────────────────────────────────
    # 컨텍스트 메뉴
    # ──────────────────────────────────────────────────────────
    def _on_item_context(self, memo_id: str, global_pos: QPoint) -> None:
        menu = QMenu(self)
        act_edit   = QAction(tr("編集"), menu)
        act_delete = QAction(tr("削除"), menu)
        act_edit.triggered.connect(lambda: self._select(memo_id))
        def _del():
            self._select(memo_id)
            self._delete_selected()
        act_delete.triggered.connect(_del)
        menu.addAction(act_edit)
        menu.addSeparator()
        menu.addAction(act_delete)
        menu.exec(global_pos)

    # ──────────────────────────────────────────────────────────
    # Rich-text WYSIWYG 헬퍼
    # ──────────────────────────────────────────────────────────
    def _body_markdown(self) -> str:
        """본문 직렬화 — Qt 의 toMarkdown 은 inline 서식 보존 한계가 있어
        rich-text 는 HTML 로, 빈 본문은 빈 문자열로 직렬화한다.
        (HTML 마커가 있는 콘텐츠는 자동 감지되어 setHtml 으로 재로드된다.)"""
        plain = self._body.toPlainText().strip()
        if not plain:
            return ""
        try:
            html = self._body.toHtml()
        except Exception:
            return plain
        return html

    @staticmethod
    def _is_html(text: str) -> bool:
        """저장된 content 가 HTML rich-text 인지 (구 markdown/plain 과 구분)."""
        if not text:
            return False
        s = text.lstrip()[:200].lower()
        return s.startswith("<!doctype") or s.startswith("<html") or "<body" in s

    def _load_body_content(self, content: str) -> None:
        """메모 content 를 본문에 로드 (HTML / Markdown / plain 자동 판별)."""
        self._suppress_dirty = True
        if not content:
            self._body.clear()
        elif self._is_html(content):
            self._body.setHtml(content)
        else:
            # 기존 markdown/plain 텍스트 — setMarkdown 으로 렌더 시도
            self._body.setMarkdown(content)
        self._suppress_dirty = False

    def _apply_format(self, action_id: str) -> None:
        """툴바 버튼 → rich-text 서식 토글/삽입 (Markdown 으로 round-trip 가능한 것만)."""
        if self._body.isReadOnly():
            return
        from PySide6.QtGui import QTextCharFormat, QTextListFormat, QFont, QTextBlockFormat

        cur = self._body.textCursor()
        if action_id == "bold":
            fmt = QTextCharFormat()
            new_w = QFont.Bold if cur.charFormat().fontWeight() != QFont.Bold else QFont.Normal
            fmt.setFontWeight(new_w)
            self._merge_char_format(fmt)
        elif action_id == "italic":
            fmt = QTextCharFormat()
            fmt.setFontItalic(not cur.charFormat().fontItalic())
            self._merge_char_format(fmt)
        elif action_id == "under":
            fmt = QTextCharFormat()
            fmt.setFontUnderline(not cur.charFormat().fontUnderline())
            self._merge_char_format(fmt)
        elif action_id == "strike":
            fmt = QTextCharFormat()
            fmt.setFontStrikeOut(not cur.charFormat().fontStrikeOut())
            self._merge_char_format(fmt)
        elif action_id == "h1":
            self._set_heading(1)
        elif action_id == "h2":
            self._set_heading(2)
        elif action_id == "ul":
            cur.createList(QTextListFormat.Style.ListDisc)
        elif action_id == "ol":
            cur.createList(QTextListFormat.Style.ListDecimal)
        elif action_id == "link":
            self._insert_link()
        elif action_id == "code":
            fmt = QTextCharFormat()
            # 인라인 코드 — 모노스페이스 + 옅은 배경
            from PySide6.QtGui import QColor
            cur_family = cur.charFormat().fontFamilies() or []
            is_mono = any("Mono" in f or "Consolas" in f for f in cur_family) \
                if cur_family else False
            if is_mono:
                fmt.setFontFamilies(["Sans Serif"])
                fmt.setBackground(Qt.transparent)
            else:
                fmt.setFontFamilies(["JetBrains Mono", "Consolas", "monospace"])
                fmt.setBackground(QColor(255, 204, 0, 40))
            self._merge_char_format(fmt)
        self._body.setFocus()

    def _merge_char_format(self, fmt) -> None:
        cur = self._body.textCursor()
        if not cur.hasSelection():
            cur.select(cur.SelectionType.WordUnderCursor)
        cur.mergeCharFormat(fmt)
        self._body.mergeCurrentCharFormat(fmt)

    def _set_heading(self, level: int) -> None:
        """현재 블록을 heading 또는 일반 단락으로 토글."""
        from PySide6.QtGui import QTextCharFormat, QTextBlockFormat, QFont
        cur = self._body.textCursor()
        block_fmt = cur.blockFormat()
        char_fmt = QTextCharFormat()
        # 현재 heading 인지 확인 (heading level 프로퍼티)
        cur_level = block_fmt.headingLevel() if hasattr(block_fmt, "headingLevel") else 0
        new_level = 0 if cur_level == level else level
        # 폰트 크기 매핑
        size_map = {1: 22, 2: 18, 3: 16, 0: 14}
        char_fmt.setFontPointSize(size_map.get(new_level, 14))
        char_fmt.setFontWeight(QFont.Bold if new_level > 0 else QFont.Normal)
        new_block_fmt = QTextBlockFormat(block_fmt)
        if hasattr(new_block_fmt, "setHeadingLevel"):
            new_block_fmt.setHeadingLevel(new_level)
        cur.beginEditBlock()
        # 블록 전체 선택
        cur.movePosition(cur.MoveOperation.StartOfBlock)
        cur.movePosition(cur.MoveOperation.EndOfBlock, cur.MoveMode.KeepAnchor)
        cur.mergeBlockFormat(new_block_fmt)
        cur.mergeCharFormat(char_fmt)
        cur.endEditBlock()

    def _insert_link(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        from PySide6.QtGui import QTextCharFormat
        cur = self._body.textCursor()
        sel = cur.selectedText() if cur.hasSelection() else ""
        text, ok = QInputDialog.getText(
            self, tr("リンク挿入"), tr("表示テキスト:"),
            text=sel,
        )
        if not ok or not text:
            return
        url, ok = QInputDialog.getText(self, tr("リンク挿入"), tr("URL:"))
        if not ok or not url:
            return
        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(url)
        fmt.setForeground(Qt.blue)
        fmt.setFontUnderline(True)
        cur.insertText(text, fmt)

    # ──────────────────────────────────────────────────────────
    # 마크다운 헬퍼 — 커서 위치 삽입 (legacy, 일부 기능에서 호출 가능)
    # ──────────────────────────────────────────────────────────
    def _insert_at_cursor(self, snippet: str) -> None:
        c = self._body.textCursor()
        if c.hasSelection():
            sel = c.selectedText()
            # snippet 안 ** 또는 * 사이에 selection 끼우기
            if "**" in snippet:
                c.insertText(f"**{sel}**")
            elif snippet.startswith("*"):
                c.insertText(f"*{sel}*")
            else:
                c.insertText(snippet)
        else:
            c.insertText(snippet)
        self._body.setFocus()

    # ──────────────────────────────────────────────────────────
    # 더티 추적 / 자동 저장
    # ──────────────────────────────────────────────────────────
    def _mark_dirty(self) -> None:
        if self._suppress_dirty:
            return
        if self._selected_id is None:
            return
        self._dirty = True
        self._update_char_count()
        # 자동 저장 debounce 재시작
        self._autosave_timer.start()

    def _update_char_count(self) -> None:
        n = len(self._body.toPlainText())
        self._char_lbl.setText(tr("{0} 文字").format(f"{n:,}"))

    def _copy_content(self) -> None:
        if not self._selected_id:
            return
        # 클립보드에는 plain text 와 markdown 양쪽 다 — Markdown 우선 (round-trip)
        text = self._body_markdown()
        if text:
            QApplication.clipboard().setText(text)
            self._show_status(tr("クリップボードにコピーしました"))

    def _show_status(self, msg: str, ms: int = 2200) -> None:
        self._status_lbl.setText(msg)
        QTimer.singleShot(ms, lambda: self._status_lbl.setText(""))

    # ──────────────────────────────────────────────────────────
    # Cleanup
    # ──────────────────────────────────────────────────────────
    def closeEvent(self, event):  # noqa: N802
        # 종료 시 미저장 변경 자동 저장
        if self._dirty:
            self._auto_save()
        super().closeEvent(event)
