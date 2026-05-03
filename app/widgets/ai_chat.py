"""AI チャット ウィジェット — Phase 5.9 リニューアル.

데이터 소스:
    - app/ai_chat.db (신규) — 세션 + 메시지 영속성
    - 기존 AiChatWorker (Gemini 3.1 Lite → Gemini 2.5 Flash → Groq 3 단 fallback)

디자인 출처:
    handoff/LEE_PROJECT/varA-detail-screens6.jsx AiChatDetail
    handoff/LEE_PROJECT/varA-widgets.jsx AiChatCard

[Card]
    AiChatCard (대시보드)
        - LeeCard accent="ai" (#5856D6)
        - LeeIconTile + "AI チャット" + 모델 sub + LeePill (online)
        - 본문: 최근 user 메시지 + AI 응답 미리보기 (버블 스타일)
        - 우측 + 버튼 (새 채팅)

[Detail page]
    AiChatWidget
        - DetailHeader (← back, 인디고 액센트 #5856D6, "online" badge)
        - 좌 240px: 세션 리스트
            · "新規チャット" 버튼
            · 세션 카드 (제목 + 마지막 메시지 + 시각)
            · 우클릭 → 이름변경 / 삭제
        - 우 flex: 채팅 영역
            · 상단 헤더 (세션 제목 + 모델 selector)
            · 메시지 리스트 (User 우측 / AI 좌측 + 아바타)
            · 코드 블록 (--font-mono + 복사 버튼)
            · 하단 입력 (Enter 전송 / Shift+Enter 개행)
"""
from __future__ import annotations

import html
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QPoint, QTimer, Signal
from PySide6.QtGui import QAction, QIcon, QKeyEvent
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMenu, QPushButton, QScrollArea, QSizePolicy, QSplitter, QTextEdit,
    QVBoxLayout, QWidget,
)

from app.api.ai_api import (
    AiChatWorker, GEMINI_LITE_MODEL, GEMINI_DEFAULT_MODEL, GROQ_DEFAULT_MODEL,
    get_all_gemini_keys, get_builtin_groq_key,
)
from app.core.events import bus
from app.core.i18n import tr
from app.ui.common import BaseWidget
from app.ui.components import (
    LeeCard, LeeDetailHeader, LeeDialog, LeeIconTile, LeePill,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 토큰
# ──────────────────────────────────────────────────────────────────────
_C_AI       = "#5856D6"
_C_AI_GRAD  = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #5856D6, stop:1 #0A84FF)"
_C_OK       = "#30D158"
_C_BAD      = "#FF453A"
_C_POWER    = "#5B8DEF"
_C_SPOT     = "#FF7A45"
_C_IMB      = "#F25C7A"

_MAX_HISTORY  = 20
_COOLDOWN_SEC = 60
_MAX_TITLE_LEN = 40

_DEFAULT_SUGGESTIONS = [
    "今日のスポット価格の特徴は?",
    "JKM の今後の見通しは?",
    "東京エリアの需給ひっ迫対策は?",
    "再エネ比率の推移を教えて",
]


# ──────────────────────────────────────────────────────────────────────
# 세션 DB 레이어
# ──────────────────────────────────────────────────────────────────────
def _ai_chat_db() -> Path:
    from app.core.config import APP_DIR
    return APP_DIR / "ai_chat.db"


_db_initialized = False


def _ensure_db() -> None:
    global _db_initialized
    if _db_initialized:
        return
    p = _ai_chat_db()
    try:
        with sqlite3.connect(p) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS ai_sessions (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    title      TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS ai_messages (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    role       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES ai_sessions(id) ON DELETE CASCADE
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_msg_session ON ai_messages(session_id)")
        _db_initialized = True
    except sqlite3.Error as e:
        logger.error(f"AI チャット DB 초기화 실패: {e}")


def list_sessions() -> list[dict]:
    """모든 세션을 updated_at 내림차순으로 반환."""
    _ensure_db()
    try:
        with sqlite3.connect(_ai_chat_db()) as con:
            rows = con.execute(
                "SELECT id, title, created_at, updated_at FROM ai_sessions "
                "ORDER BY updated_at DESC"
            ).fetchall()
        result = []
        for r in rows:
            sid = r[0]
            # 마지막 메시지
            with sqlite3.connect(_ai_chat_db()) as con:
                msg = con.execute(
                    "SELECT content FROM ai_messages WHERE session_id=? "
                    "ORDER BY id DESC LIMIT 1", (sid,)
                ).fetchone()
            last_msg = msg[0] if msg else ""
            result.append({
                "id": sid, "title": r[1] or tr("無題"),
                "created_at": r[2], "updated_at": r[3],
                "last_message": last_msg,
            })
        return result
    except sqlite3.Error as e:
        logger.warning(f"세션 list 실패: {e}")
        return []


def create_session(title: str = "") -> int:
    _ensure_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = title.strip() or tr("新規チャット")
    try:
        with sqlite3.connect(_ai_chat_db()) as con:
            cur = con.execute(
                "INSERT INTO ai_sessions (title, created_at, updated_at) VALUES (?, ?, ?)",
                (title, now, now),
            )
            return cur.lastrowid or -1
    except sqlite3.Error as e:
        logger.error(f"세션 create 실패: {e}")
        return -1


def rename_session(sid: int, new_title: str) -> None:
    new_title = new_title.strip() or tr("無題")
    try:
        with sqlite3.connect(_ai_chat_db()) as con:
            con.execute("UPDATE ai_sessions SET title=? WHERE id=?", (new_title, sid))
    except sqlite3.Error as e:
        logger.warning(f"세션 rename 실패: {e}")


def delete_session(sid: int) -> None:
    try:
        with sqlite3.connect(_ai_chat_db()) as con:
            con.execute("DELETE FROM ai_messages WHERE session_id=?", (sid,))
            con.execute("DELETE FROM ai_sessions WHERE id=?", (sid,))
    except sqlite3.Error as e:
        logger.warning(f"세션 delete 실패: {e}")


def list_messages(sid: int) -> list[dict]:
    _ensure_db()
    try:
        with sqlite3.connect(_ai_chat_db()) as con:
            rows = con.execute(
                "SELECT id, role, content, created_at FROM ai_messages "
                "WHERE session_id=? ORDER BY id ASC", (sid,)
            ).fetchall()
        return [
            {"id": r[0], "role": r[1], "content": r[2], "created_at": r[3]}
            for r in rows
        ]
    except sqlite3.Error as e:
        logger.warning(f"메시지 list 실패: {e}")
        return []


def append_message(sid: int, role: str, content: str) -> int:
    _ensure_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with sqlite3.connect(_ai_chat_db()) as con:
            cur = con.execute(
                "INSERT INTO ai_messages (session_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)", (sid, role, content, now),
            )
            con.execute("UPDATE ai_sessions SET updated_at=? WHERE id=?", (now, sid))
            return cur.lastrowid or -1
    except sqlite3.Error as e:
        logger.error(f"메시지 append 실패: {e}")
        return -1


def latest_user_message(sid: Optional[int] = None) -> Optional[dict]:
    """대시보드 카드용 — 가장 최근 user 메시지 1 건. sid 없으면 전체에서 최근."""
    _ensure_db()
    try:
        with sqlite3.connect(_ai_chat_db()) as con:
            if sid is None:
                row = con.execute(
                    "SELECT id, session_id, content, created_at FROM ai_messages "
                    "WHERE role='user' ORDER BY id DESC LIMIT 1"
                ).fetchone()
            else:
                row = con.execute(
                    "SELECT id, session_id, content, created_at FROM ai_messages "
                    "WHERE session_id=? AND role='user' ORDER BY id DESC LIMIT 1",
                    (sid,),
                ).fetchone()
        if not row:
            return None
        return {"id": row[0], "session_id": row[1],
                "content": row[2], "created_at": row[3]}
    except sqlite3.Error:
        return None


def latest_assistant_after(sid: int, after_msg_id: int) -> Optional[str]:
    """user 메시지 이후의 가장 최근 assistant 응답."""
    _ensure_db()
    try:
        with sqlite3.connect(_ai_chat_db()) as con:
            row = con.execute(
                "SELECT content FROM ai_messages "
                "WHERE session_id=? AND role='assistant' AND id > ? "
                "ORDER BY id ASC LIMIT 1",
                (sid, after_msg_id),
            ).fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None


# ──────────────────────────────────────────────────────────────────────
# A. AiChatCard — 대시보드 카드
# ──────────────────────────────────────────────────────────────────────
class AiChatCard(LeeCard):
    """AI チャット 카드 — 최근 1 쌍 (user + AI) 미리보기 + 새 채팅 버튼."""

    clicked     = Signal()
    new_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(accent_color="ai", interactive=True, parent=parent)
        self.setMinimumHeight(280)
        self._is_dark = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(0)

        # 헤더
        header = QHBoxLayout(); header.setSpacing(12); header.setContentsMargins(0, 0, 0, 12)
        self._icon = LeeIconTile(
            icon=QIcon(":/img/chat.svg"),
            color=_C_AI, size=40, radius=12,
        )
        header.addWidget(self._icon, 0, Qt.AlignTop)

        title_box = QVBoxLayout(); title_box.setSpacing(2); title_box.setContentsMargins(0, 0, 0, 0)
        self._title_lbl = QLabel(tr("AI チャット"))
        self._title_lbl.setObjectName("aiCardTitle")
        self._sub_lbl = QLabel(tr("Gemini · 電力データ接続済"))
        self._sub_lbl.setObjectName("aiCardSub")
        title_box.addWidget(self._title_lbl)
        title_box.addWidget(self._sub_lbl)
        header.addLayout(title_box, 1)

        # online pill
        self._pill = LeePill("オン", variant="success")
        header.addWidget(self._pill, 0, Qt.AlignTop)

        # + 버튼
        self._btn_new = QPushButton("＋")
        self._btn_new.setObjectName("aiCardNewBtn")
        self._btn_new.setFixedSize(28, 28)
        self._btn_new.setCursor(Qt.PointingHandCursor)
        self._btn_new.setToolTip(tr("新しいチャット"))
        self._btn_new.clicked.connect(self.new_clicked.emit)
        header.addWidget(self._btn_new, 0, Qt.AlignTop)

        layout.addLayout(header)

        # 미리보기 — User 버블 + AI 버블
        preview_wrap = QWidget()
        prev_lay = QVBoxLayout(preview_wrap)
        prev_lay.setContentsMargins(0, 0, 0, 0); prev_lay.setSpacing(8)

        self._user_bubble = QLabel("")
        self._user_bubble.setObjectName("aiCardUserBubble")
        self._user_bubble.setWordWrap(True)
        self._user_bubble.setMaximumWidth(380)
        self._user_bubble.setAlignment(Qt.AlignLeft)
        self._user_bubble.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        user_row = QHBoxLayout(); user_row.setContentsMargins(0, 0, 0, 0)
        user_row.addStretch()
        user_row.addWidget(self._user_bubble)
        prev_lay.addLayout(user_row)

        self._ai_bubble = QLabel("")
        self._ai_bubble.setObjectName("aiCardAiBubble")
        self._ai_bubble.setWordWrap(True)
        self._ai_bubble.setMaximumWidth(380)
        self._ai_bubble.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        ai_row = QHBoxLayout(); ai_row.setContentsMargins(0, 0, 0, 0)
        ai_row.addWidget(self._ai_bubble)
        ai_row.addStretch()
        prev_lay.addLayout(ai_row)

        layout.addWidget(preview_wrap, 1)

        # 빈 상태
        self._empty = QLabel(tr("チャットを始めましょう"))
        self._empty.setObjectName("aiCardEmpty")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setMinimumHeight(60)
        layout.addWidget(self._empty)
        self._empty.setVisible(False)

        # 입력 placeholder
        ph = QFrame()
        ph.setObjectName("aiCardPh")
        ph_lay = QHBoxLayout(ph)
        ph_lay.setContentsMargins(12, 8, 12, 8); ph_lay.setSpacing(8)
        ph_icon = QLabel("💬")
        ph_lbl = QLabel(tr("質問を入力..."))
        ph_lbl.setObjectName("aiCardPhLbl")
        ph_kbd = QLabel("↵")
        ph_kbd.setObjectName("aiCardPhKbd")
        ph_lay.addWidget(ph_icon)
        ph_lay.addWidget(ph_lbl, 1)
        ph_lay.addWidget(ph_kbd)
        layout.addSpacing(8)
        layout.addWidget(ph)

        self._apply_local_qss()
        self.set_no_data()

    def set_data(self, *, user_text: str, ai_text: str) -> None:
        if not user_text and not ai_text:
            self.set_no_data(); return
        self._user_bubble.setText(self._truncate(user_text, 80))
        self._ai_bubble.setText(self._truncate(ai_text or tr("(応答待ち...)"), 100))
        self._user_bubble.setVisible(bool(user_text))
        self._ai_bubble.setVisible(True)
        self._empty.setVisible(False)

    def set_no_data(self) -> None:
        self._user_bubble.setText("")
        self._ai_bubble.setText("")
        self._user_bubble.setVisible(False)
        self._ai_bubble.setVisible(False)
        self._empty.setVisible(True)

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_local_qss()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            child = self.childAt(event.pos())
            if child is not self._btn_new:
                self.clicked.emit()
        super().mousePressEvent(event)

    @staticmethod
    def _truncate(s: str, n: int) -> str:
        s = (s or "").replace("\n", " ").strip()
        return s if len(s) <= n else s[:n] + "…"

    def _apply_local_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        bg_surface_2 = "#1B1E26" if is_dark else "#F0F2F5"
        border       = "rgba(255,255,255,0.10)" if is_dark else "rgba(11,18,32,0.10)"
        self.setStyleSheet(f"""
            QLabel#aiCardTitle {{
                font-size: 13px; font-weight: 600;
                color: {fg_secondary}; background: transparent;
            }}
            QLabel#aiCardSub {{
                font-size: 11px; color: {fg_tertiary};
                background: transparent;
            }}
            QPushButton#aiCardNewBtn {{
                background: {bg_surface_2};
                color: {_C_AI};
                border: 1px solid {border};
                border-radius: 8px;
                font-size: 16px; font-weight: 700;
            }}
            QPushButton#aiCardNewBtn:hover {{
                background: rgba(88,86,214,0.14);
                border: 1px solid {_C_AI};
            }}
            QLabel#aiCardUserBubble {{
                background: {_C_AI};
                color: white;
                border-radius: 14px;
                border-top-right-radius: 4px;
                padding: 8px 12px;
                font-size: 12px;
                line-height: 1.5;
            }}
            QLabel#aiCardAiBubble {{
                background: {bg_surface_2};
                color: {fg_primary};
                border-radius: 14px;
                border-top-left-radius: 4px;
                padding: 8px 12px;
                font-size: 12px;
                line-height: 1.5;
            }}
            QLabel#aiCardEmpty {{
                font-size: 11px; color: {fg_tertiary};
                background: transparent; font-style: italic;
            }}
            QFrame#aiCardPh {{
                background: {bg_surface_2};
                border-radius: 12px;
            }}
            QLabel#aiCardPhLbl {{
                color: {fg_tertiary}; background: transparent;
                font-size: 12px;
            }}
            QLabel#aiCardPhKbd {{
                color: {fg_tertiary}; background: transparent;
                border: 1px solid {border};
                border-radius: 4px;
                font-size: 10px;
                padding: 1px 5px;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# B. _SessionItem — 좌측 세션 리스트의 단일 항목
# ──────────────────────────────────────────────────────────────────────
class _SessionItem(QFrame):
    """단일 세션 카드 — 컬러 dot + 제목 + 마지막 메시지 + 시각."""

    clicked           = Signal(int)   # session id
    context_requested = Signal(int, QPoint)

    def __init__(self, sess: dict, *, is_dark: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("aiSessionItem")
        self._is_dark = is_dark
        self._sess = sess
        self._active = False
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10); v.setSpacing(4)

        head = QHBoxLayout(); head.setContentsMargins(0, 0, 0, 0); head.setSpacing(8)
        self._dot = QLabel("●"); self._dot.setObjectName("sessDot"); self._dot.setFixedWidth(10)
        head.addWidget(self._dot)
        self._title_lbl = QLabel(sess.get("title", tr("無題")))
        self._title_lbl.setObjectName("sessTitle")
        head.addWidget(self._title_lbl, 1)
        self._date_lbl = QLabel(self._fmt_date(sess.get("updated_at", "")))
        self._date_lbl.setObjectName("sessDate")
        head.addWidget(self._date_lbl)
        v.addLayout(head)

        last = (sess.get("last_message") or "").replace("\n", " ").strip()
        self._last_lbl = QLabel(self._elide(last, 50) if last else tr("(まだメッセージがありません)"))
        self._last_lbl.setObjectName("sessLast")
        v.addWidget(self._last_lbl)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_ctx)
        self._apply_qss()

    @staticmethod
    def _elide(s: str, n: int) -> str:
        return s if len(s) <= n else s[:n] + "…"

    @staticmethod
    def _fmt_date(iso_str: str) -> str:
        if not iso_str:
            return ""
        try:
            dt = datetime.strptime(iso_str[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            return iso_str[:10]
        delta = datetime.now() - dt
        if delta.days >= 1:
            return f"{dt.month}/{dt.day}"
        if delta.seconds >= 3600:
            return f"{delta.seconds // 3600}時間前"
        if delta.seconds >= 60:
            return f"{delta.seconds // 60}分前"
        return tr("今")

    def session_id(self) -> int:
        return int(self._sess.get("id", -1))

    def set_active(self, active: bool) -> None:
        if self._active == active: return
        self._active = active
        self._apply_qss()

    def update_session(self, sess: dict) -> None:
        self._sess = sess
        self._title_lbl.setText(sess.get("title", tr("無題")))
        self._date_lbl.setText(self._fmt_date(sess.get("updated_at", "")))
        last = (sess.get("last_message") or "").replace("\n", " ").strip()
        self._last_lbl.setText(self._elide(last, 50) if last else tr("(まだメッセージがありません)"))

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.session_id())
        super().mousePressEvent(event)

    def _on_ctx(self, pos: QPoint) -> None:
        self.context_requested.emit(self.session_id(), self.mapToGlobal(pos))

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        bg_surface   = "#14161C" if is_dark else "#FFFFFF"
        bg_surface_2 = "#1B1E26" if is_dark else "#F0F2F5"
        border_subtle = "rgba(255,255,255,0.06)" if is_dark else "rgba(11,18,32,0.06)"

        if self._active:
            bg = bg_surface
            border = f"1.5px solid {_C_AI}"
        else:
            bg = bg_surface_2
            border = f"1px solid {border_subtle}"
        self.setStyleSheet(f"""
            QFrame#aiSessionItem {{
                background: {bg};
                border: {border};
                border-radius: 12px;
            }}
            QFrame#aiSessionItem:hover {{
                border: 1px solid {_C_AI};
            }}
            QLabel#sessDot {{
                color: {_C_AI}; background: transparent;
                font-size: 10px;
            }}
            QLabel#sessTitle {{
                font-size: 12px; font-weight: 700;
                color: {fg_primary}; background: transparent;
            }}
            QLabel#sessDate {{
                font-size: 10px;
                color: {fg_tertiary}; background: transparent;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QLabel#sessLast {{
                font-size: 11px;
                color: {fg_secondary}; background: transparent;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# C. _MessageBubble — 채팅 영역의 단일 메시지 버블
# ──────────────────────────────────────────────────────────────────────
class _MessageBubble(QWidget):
    """User (우측, 인디고 그라데이션) / AI (좌측, surface-2) 버블 + 아바타."""

    def __init__(self, role: str, text: str, *, is_dark: bool, parent=None):
        super().__init__(parent)
        self._is_user = role == "user"
        self._is_dark = is_dark
        self._raw_text = text

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(8)

        # 좌 아바타 (AI 만)
        if not self._is_user:
            av = QLabel("AI")
            av.setObjectName("bubbleAvatarAi")
            av.setFixedSize(32, 32)
            av.setAlignment(Qt.AlignCenter)
            outer.addWidget(av, 0, Qt.AlignTop)

        # 본문 라벨
        self._lbl = QLabel(_format_message(text, is_dark))
        self._lbl.setObjectName("userBubble" if self._is_user else "aiBubble")
        self._lbl.setTextFormat(Qt.RichText)
        self._lbl.setWordWrap(True)
        self._lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._lbl.setMaximumWidth(560)
        self._lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        if self._is_user:
            outer.addStretch(1)
            outer.addWidget(self._lbl, 0, Qt.AlignTop)
            # 우 아바타 — 사용자 이니셜
            av = QLabel(self._user_initial())
            av.setObjectName("bubbleAvatarUser")
            av.setFixedSize(32, 32)
            av.setAlignment(Qt.AlignCenter)
            outer.addWidget(av, 0, Qt.AlignTop)
        else:
            outer.addWidget(self._lbl, 0, Qt.AlignTop)
            outer.addStretch(1)

        self._apply_qss()

    @staticmethod
    def _user_initial() -> str:
        try:
            from app.api.google.auth import get_current_user_email
            email = get_current_user_email() or ""
            if "@" in email:
                return email[0].upper()
        except Exception:
            pass
        return "U"

    def update_text(self, text: str) -> None:
        """스트리밍 시 텍스트 점진적 업데이트."""
        self._raw_text = text
        self._lbl.setText(_format_message(text, self._is_dark))

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()
        self._lbl.setText(_format_message(self._raw_text, is_dark))

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        bg_surface_2 = "#1B1E26" if is_dark else "#F0F2F5"
        border       = "rgba(255,255,255,0.10)" if is_dark else "rgba(11,18,32,0.10)"
        self.setStyleSheet(f"""
            QLabel#bubbleAvatarAi {{
                background: {_C_AI_GRAD};
                color: white;
                border-radius: 10px;
                font-size: 11px; font-weight: 800;
            }}
            QLabel#bubbleAvatarUser {{
                background: {bg_surface_2};
                color: {fg_primary};
                border: 1px solid {border};
                border-radius: 10px;
                font-size: 11px; font-weight: 800;
            }}
            QLabel#userBubble {{
                background: {_C_AI_GRAD};
                color: white;
                border-radius: 16px;
                border-top-right-radius: 4px;
                padding: 12px 16px;
                font-size: 13px;
                line-height: 1.65;
                selection-background-color: rgba(255,255,255,0.25);
            }}
            QLabel#aiBubble {{
                background: {bg_surface_2};
                color: {fg_primary};
                border-radius: 16px;
                border-top-left-radius: 4px;
                padding: 12px 16px;
                font-size: 13px;
                line-height: 1.65;
                selection-background-color: rgba(88,86,214,0.30);
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# D. _ThinkingBubble — AI 응답 대기 표시
# ──────────────────────────────────────────────────────────────────────
class _ThinkingBubble(QWidget):
    _FRAMES = ["·  ", "·· ", "···", " ··", "  ·"]

    def __init__(self, *, is_dark: bool, parent=None):
        super().__init__(parent)
        self._is_dark = is_dark
        self._step = 0
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(8)

        av = QLabel("AI"); av.setObjectName("thinkAv")
        av.setFixedSize(32, 32); av.setAlignment(Qt.AlignCenter)
        outer.addWidget(av, 0, Qt.AlignTop)

        self._lbl = QLabel(""); self._lbl.setObjectName("thinkLbl")
        outer.addWidget(self._lbl, 0, Qt.AlignTop)
        outer.addStretch(1)

        self._timer = QTimer(self); self._timer.setInterval(380)
        self._timer.timeout.connect(self._tick)
        self._timer.start(); self._tick()
        self._apply_qss()

    def _tick(self) -> None:
        self._lbl.setText(f"{tr('考え中')}  {self._FRAMES[self._step]}")
        self._step = (self._step + 1) % len(self._FRAMES)

    def deleteLater(self):  # noqa: N802
        try: self._timer.stop()
        except RuntimeError: pass
        super().deleteLater()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        bg_surface_2 = "#1B1E26" if is_dark else "#F0F2F5"
        self.setStyleSheet(f"""
            QLabel#thinkAv {{
                background: {_C_AI_GRAD};
                color: white;
                border-radius: 10px;
                font-size: 11px; font-weight: 800;
            }}
            QLabel#thinkLbl {{
                background: {bg_surface_2};
                color: {fg_tertiary};
                border-radius: 16px;
                border-top-left-radius: 4px;
                padding: 12px 16px;
                font-size: 13px; font-style: italic;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# E. _Composer — 메시지 입력창
# ──────────────────────────────────────────────────────────────────────
class _Composer(QFrame):
    """Enter 전송 / Shift+Enter 개행. 자동 높이 조정."""

    send_requested = Signal(str)

    def __init__(self, *, is_dark: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("aiComposer")
        self._is_dark = is_dark

        h = QHBoxLayout(self)
        h.setContentsMargins(8, 8, 8, 8); h.setSpacing(6)

        self._input = _ComposerTextEdit(self.send_requested)
        self._input.setPlaceholderText(tr("メッセージを入力...  (Enter 送信 / Shift+Enter 改行)"))
        self._input.setMinimumHeight(40)
        self._input.setMaximumHeight(160)
        h.addWidget(self._input, 1)

        self._btn = QPushButton(tr("送信"))
        self._btn.setObjectName("aiSendBtn")
        self._btn.setFixedHeight(40)
        self._btn.setMinimumWidth(72)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.clicked.connect(self._on_send)
        h.addWidget(self._btn, 0, Qt.AlignBottom)

        self._apply_qss()

    def text(self) -> str:
        return self._input.toPlainText()

    def clear(self) -> None:
        self._input.clear()

    def set_enabled(self, enabled: bool) -> None:
        self._input.setEnabled(enabled)
        self._btn.setEnabled(enabled)

    def set_send_label(self, text: str) -> None:
        self._btn.setText(text)

    def focus_input(self) -> None:
        self._input.setFocus()

    def insert_text(self, text: str) -> None:
        self._input.setPlainText(text)
        self._input.setFocus()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    def _on_send(self) -> None:
        self.send_requested.emit(self._input.toPlainText().strip())

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary    = "#F2F4F7" if is_dark else "#0B1220"
        fg_tertiary   = "#6B7280" if is_dark else "#8A93A6"
        bg_surface    = "#14161C" if is_dark else "#FFFFFF"
        bg_surface_2  = "#1B1E26" if is_dark else "#F0F2F5"
        border_subtle = "rgba(255,255,255,0.06)" if is_dark else "rgba(11,18,32,0.06)"
        border        = "rgba(255,255,255,0.10)" if is_dark else "rgba(11,18,32,0.10)"
        self.setStyleSheet(f"""
            QFrame#aiComposer {{
                background: {bg_surface_2};
                border: 1px solid {border_subtle};
                border-radius: 14px;
            }}
            QTextEdit {{
                background: transparent;
                color: {fg_primary};
                border: none;
                font-size: 13px;
                padding: 6px 8px;
                selection-background-color: rgba(88,86,214,0.30);
            }}
            QPushButton#aiSendBtn {{
                background: {_C_AI_GRAD};
                color: white;
                border: none;
                border-radius: 10px;
                padding: 0 16px;
                font-size: 12px; font-weight: 700;
            }}
            QPushButton#aiSendBtn:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #6361DC, stop:1 #2A94FF);
            }}
            QPushButton#aiSendBtn:disabled {{
                background: {bg_surface};
                color: {fg_tertiary};
            }}
        """)


class _ComposerTextEdit(QTextEdit):
    def __init__(self, send_signal: Signal):
        super().__init__()
        self._send_signal = send_signal

    def keyPressEvent(self, event: QKeyEvent):  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self._send_signal.emit(self.toPlainText().strip())
                return
        else:
            super().keyPressEvent(event)


# ──────────────────────────────────────────────────────────────────────
# F. _ChatArea — 채팅 영역 (메시지 리스트 + welcome)
# ──────────────────────────────────────────────────────────────────────
class _ChatArea(QScrollArea):
    """스크롤 가능한 메시지 컨테이너. 비어있을 때 welcome (suggestion chips)."""

    suggestion_clicked = Signal(str)

    def __init__(self, *, is_dark: bool, parent=None):
        super().__init__(parent)
        self._is_dark = is_dark
        self._bubbles: list[_MessageBubble] = []
        self._thinking: Optional[_ThinkingBubble] = None

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setSpacing(14)
        self._layout.setContentsMargins(22, 22, 22, 22)

        self._welcome = self._build_welcome()
        self._layout.addWidget(self._welcome, 0, Qt.AlignTop)
        self._layout.addStretch()
        self.setWidget(self._container)
        self._apply_qss()

    def _build_welcome(self) -> QWidget:
        card = QFrame(); card.setObjectName("aiWelcome")
        v = QVBoxLayout(card); v.setContentsMargins(28, 32, 28, 24); v.setSpacing(14)

        # 헤더
        head = QHBoxLayout(); head.setSpacing(12); head.setContentsMargins(0, 0, 0, 0)
        av = QLabel("AI"); av.setObjectName("welcomeAv")
        av.setFixedSize(48, 48); av.setAlignment(Qt.AlignCenter)
        head.addWidget(av)
        ttl_box = QVBoxLayout(); ttl_box.setSpacing(2)
        title = QLabel(tr("AI アシスタント")); title.setObjectName("welcomeTitle")
        sub = QLabel(tr("日本の電力市場・LNG・天気などについて質問できます"))
        sub.setObjectName("welcomeSub"); sub.setWordWrap(True)
        ttl_box.addWidget(title); ttl_box.addWidget(sub)
        head.addLayout(ttl_box, 1)
        v.addLayout(head)

        # 추천 chips
        chip_lbl = QLabel(tr("試してみてください:"))
        chip_lbl.setObjectName("welcomeChipsLbl")
        v.addWidget(chip_lbl)

        for s in _DEFAULT_SUGGESTIONS:
            btn = QPushButton(s)
            btn.setObjectName("welcomeChip")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, txt=s: self.suggestion_clicked.emit(txt))
            v.addWidget(btn)
        return card

    def add_bubble(self, role: str, text: str) -> _MessageBubble:
        if not self._bubbles:
            self._welcome.setVisible(False)
        b = _MessageBubble(role, text, is_dark=self._is_dark)
        self._bubbles.append(b)
        # stretch 직전에 삽입
        self._layout.insertWidget(self._layout.count() - 1, b)
        QTimer.singleShot(50, self._scroll_bottom)
        return b

    def add_thinking(self) -> None:
        if self._thinking is not None:
            return
        if not self._bubbles:
            self._welcome.setVisible(False)
        self._thinking = _ThinkingBubble(is_dark=self._is_dark)
        self._layout.insertWidget(self._layout.count() - 1, self._thinking)
        QTimer.singleShot(50, self._scroll_bottom)

    def remove_thinking(self) -> None:
        if self._thinking is None: return
        self._layout.removeWidget(self._thinking)
        self._thinking.setParent(None)
        self._thinking.deleteLater()
        self._thinking = None

    def add_system_error(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setObjectName("aiSystemError")
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignCenter)
        self._layout.insertWidget(self._layout.count() - 1, lbl)
        is_dark = self._is_dark
        bg = "rgba(255,69,58,0.10)" if is_dark else "rgba(255,69,58,0.08)"
        lbl.setStyleSheet(
            f"QLabel#aiSystemError {{ background: {bg}; color: #FF453A; "
            f"border: 1px solid rgba(255,69,58,0.30); border-radius: 12px; "
            f"padding: 12px 16px; font-size: 12px; }}"
        )
        QTimer.singleShot(50, self._scroll_bottom)

    def clear(self) -> None:
        self.remove_thinking()
        for b in self._bubbles:
            self._layout.removeWidget(b)
            b.setParent(None); b.deleteLater()
        self._bubbles.clear()
        self._welcome.setVisible(True)

    def load_messages(self, messages: list[dict]) -> None:
        self.clear()
        if not messages: return
        self._welcome.setVisible(False)
        for m in messages:
            b = _MessageBubble(m["role"], m["content"], is_dark=self._is_dark)
            self._bubbles.append(b)
            self._layout.insertWidget(self._layout.count() - 1, b)
        QTimer.singleShot(50, self._scroll_bottom)

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        for b in self._bubbles:
            try: b.set_theme(is_dark)
            except RuntimeError: pass
        if self._thinking:
            try: self._thinking.set_theme(is_dark)
            except RuntimeError: pass
        self._apply_qss()

    def _scroll_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        bg            = "#0F1117" if is_dark else "#F8F9FB"
        bg_surface_2  = "#1B1E26" if is_dark else "#F0F2F5"
        fg_primary    = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary  = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary   = "#6B7280" if is_dark else "#8A93A6"
        border_subtle = "rgba(255,255,255,0.06)" if is_dark else "rgba(11,18,32,0.06)"
        self.setStyleSheet(f"""
            QScrollArea {{ background: {bg}; border: none; }}
            QWidget#aiWelcome, QFrame#aiWelcome {{
                background: transparent;
            }}
            QLabel#welcomeAv {{
                background: {_C_AI_GRAD};
                color: white;
                border-radius: 14px;
                font-size: 16px; font-weight: 800;
            }}
            QLabel#welcomeTitle {{
                font-size: 20px; font-weight: 800;
                color: {fg_primary}; background: transparent;
            }}
            QLabel#welcomeSub {{
                font-size: 12px;
                color: {fg_secondary}; background: transparent;
            }}
            QLabel#welcomeChipsLbl {{
                font-size: 11px; font-weight: 700;
                color: {fg_tertiary}; background: transparent;
                letter-spacing: 0.04em;
                margin-top: 6px;
            }}
            QPushButton#welcomeChip {{
                text-align: left;
                padding: 10px 14px;
                background: {bg_surface_2};
                color: {fg_primary};
                border: 1px solid {border_subtle};
                border-radius: 10px;
                font-size: 12px; font-weight: 600;
            }}
            QPushButton#welcomeChip:hover {{
                border: 1px solid {_C_AI};
                background: rgba(88,86,214,0.08);
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# G. AiChatWidget — 디테일 페이지
# ──────────────────────────────────────────────────────────────────────
class AiChatWidget(BaseWidget):
    """AI チャット — DetailHeader + 좌 240px 세션 리스트 + 우 채팅 영역."""

    sessions_changed = Signal()   # 카드 동기화용 (외부)

    def __init__(self):
        super().__init__()
        _ensure_db()
        self._sessions: list[dict] = []
        self._session_items: dict[int, _SessionItem] = {}
        self._active_sid: Optional[int] = None
        self._messages: list[dict] = []
        self._worker: Optional[AiChatWorker] = None
        self._cooldown_remaining = 0
        self._cooldown_timer = QTimer(self)
        self._cooldown_timer.setInterval(1000)
        self._cooldown_timer.timeout.connect(self._tick_cooldown)

        self._build_ui()
        self._reload_sessions()

    # ──────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        content = QWidget(); content.setObjectName("aiPageContent")
        outer.addWidget(content, 1)

        root = QVBoxLayout(content)
        root.setContentsMargins(28, 22, 28, 22); root.setSpacing(14)

        # 1) DetailHeader
        self._header = LeeDetailHeader(
            title=tr("AI アシスタント"),
            subtitle=tr("Gemini · 電力市場データ接続"),
            accent=_C_AI,
            icon_qicon=QIcon(":/img/chat.svg"),
            badge=tr("online"),
            show_export=False,
        )
        self._header.back_clicked.connect(lambda: bus.page_requested.emit(0))
        root.addWidget(self._header)

        # 2) 분할: 좌 240px + 우 flex
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)

        splitter.addWidget(self._build_left_pane())
        splitter.addWidget(self._build_right_pane())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 800])
        root.addWidget(splitter, 1)

        # 3) 상태 라벨
        st_row = QHBoxLayout(); st_row.setSpacing(10)
        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("aiStatusLbl")
        st_row.addWidget(self._status_lbl)
        st_row.addStretch()
        # API key 상태
        self._api_warn = QLabel("")
        self._api_warn.setObjectName("aiApiWarn")
        self._api_warn.setVisible(False)
        st_row.addWidget(self._api_warn)
        root.addLayout(st_row)

        self._apply_page_qss()
        self._refresh_api_status()

    def _build_left_pane(self) -> QWidget:
        wrap = QFrame(); wrap.setObjectName("aiLeftPane")
        wrap.setFixedWidth(260)
        v = QVBoxLayout(wrap)
        v.setContentsMargins(12, 12, 12, 12); v.setSpacing(8)

        # "新規チャット" 버튼
        self._btn_new_session = QPushButton("＋  " + tr("新規チャット"))
        self._btn_new_session.setObjectName("aiNewSessionBtn")
        self._btn_new_session.setFixedHeight(40)
        self._btn_new_session.setCursor(Qt.PointingHandCursor)
        self._btn_new_session.clicked.connect(self._on_new_session_clicked)
        v.addWidget(self._btn_new_session)

        # 세션 리스트 (스크롤)
        list_scroll = QScrollArea(); list_scroll.setObjectName("aiListScroll")
        list_scroll.setWidgetResizable(True)
        list_scroll.setFrameShape(QFrame.NoFrame)
        list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._list_inner = QWidget()
        self._list_layout = QVBoxLayout(self._list_inner)
        self._list_layout.setContentsMargins(0, 0, 0, 0); self._list_layout.setSpacing(6)
        self._list_layout.addStretch()
        list_scroll.setWidget(self._list_inner)
        v.addWidget(list_scroll, 1)

        # 빈 상태
        self._sess_empty = QLabel(tr("セッションがまだありません"))
        self._sess_empty.setObjectName("aiSessEmpty")
        self._sess_empty.setAlignment(Qt.AlignCenter)
        self._list_layout.insertWidget(0, self._sess_empty)
        self._sess_empty.setVisible(False)

        self._left_pane = wrap
        return wrap

    def _build_right_pane(self) -> QWidget:
        wrap = QFrame(); wrap.setObjectName("aiRightPane")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        # 헤더 (세션 제목 + 모델 selector)
        header = QFrame(); header.setObjectName("aiChatHeader")
        h = QHBoxLayout(header)
        h.setContentsMargins(18, 12, 18, 12); h.setSpacing(10)

        dot = QLabel("●"); dot.setObjectName("aiChatHeaderDot")
        h.addWidget(dot)
        self._chat_title_lbl = QLabel(tr("セッションを選択"))
        self._chat_title_lbl.setObjectName("aiChatTitle")
        h.addWidget(self._chat_title_lbl, 1)

        # 모델 selector
        self._model_lbl = QLabel("")
        self._model_lbl.setObjectName("aiModelLabel")
        h.addWidget(self._model_lbl)

        # clear 버튼
        self._btn_clear = QPushButton(tr("クリア"))
        self._btn_clear.setObjectName("aiClearBtn")
        self._btn_clear.setCursor(Qt.PointingHandCursor)
        self._btn_clear.setFixedHeight(28)
        self._btn_clear.clicked.connect(self._on_clear_session)
        h.addWidget(self._btn_clear)

        v.addWidget(header)

        # 채팅 영역
        self._chat_area = _ChatArea(is_dark=self.is_dark)
        self._chat_area.suggestion_clicked.connect(self._on_suggestion)
        v.addWidget(self._chat_area, 1)

        # 입력
        composer_wrap = QFrame(); composer_wrap.setObjectName("aiComposerWrap")
        cw = QVBoxLayout(composer_wrap)
        cw.setContentsMargins(18, 12, 18, 14); cw.setSpacing(0)
        self._composer = _Composer(is_dark=self.is_dark)
        self._composer.send_requested.connect(self._on_send)
        cw.addWidget(self._composer)
        v.addWidget(composer_wrap)

        self._right_pane = wrap
        return wrap

    def _apply_page_qss(self) -> None:
        is_dark = self.is_dark
        bg_app        = "#0A0B0F" if is_dark else "#F5F6F8"
        fg_primary    = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary  = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary   = "#6B7280" if is_dark else "#8A93A6"
        bg_surface    = "#14161C" if is_dark else "#FFFFFF"
        bg_surface_2  = "#1B1E26" if is_dark else "#F0F2F5"
        border_subtle = "rgba(255,255,255,0.06)" if is_dark else "rgba(11,18,32,0.06)"
        border        = "rgba(255,255,255,0.10)" if is_dark else "rgba(11,18,32,0.10)"
        self.setStyleSheet(f"""
            AiChatWidget {{ background: {bg_app}; }}
            QWidget#aiPageContent {{ background: {bg_app}; }}

            QFrame#aiLeftPane {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 14px;
            }}
            QFrame#aiRightPane {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 14px;
            }}
            QSplitter::handle {{ background: transparent; }}

            QPushButton#aiNewSessionBtn {{
                background: {_C_AI};
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 12px; font-weight: 700;
            }}
            QPushButton#aiNewSessionBtn:hover {{ background: #6361DC; }}
            QScrollArea#aiListScroll {{ background: transparent; border: none; }}
            QLabel#aiSessEmpty {{
                font-size: 11px; color: {fg_tertiary};
                font-style: italic;
                padding: 20px 0;
                background: transparent;
            }}

            QFrame#aiChatHeader {{
                background: {bg_surface};
                border-bottom: 1px solid {border_subtle};
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }}
            QLabel#aiChatHeaderDot {{
                color: {_C_OK}; background: transparent; font-size: 10px;
            }}
            QLabel#aiChatTitle {{
                font-size: 13px; font-weight: 700;
                color: {fg_primary}; background: transparent;
            }}
            QLabel#aiModelLabel {{
                font-size: 10px; color: {fg_tertiary};
                background: {bg_surface_2};
                border: 1px solid {border_subtle};
                border-radius: 999px;
                padding: 3px 10px;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QPushButton#aiClearBtn {{
                background: {bg_surface_2};
                color: {fg_secondary};
                border: 1px solid {border_subtle};
                border-radius: 8px;
                padding: 0 12px;
                font-size: 11px; font-weight: 600;
            }}
            QPushButton#aiClearBtn:hover {{
                color: #FF453A;
                border-color: rgba(255,69,58,0.30);
            }}

            QFrame#aiComposerWrap {{
                background: {bg_surface};
                border-bottom-left-radius: 14px;
                border-bottom-right-radius: 14px;
                border-top: 1px solid {border_subtle};
            }}

            QLabel#aiStatusLbl {{
                font-size: 11px; font-weight: 600;
                color: {_C_AI};
                background: rgba(88,86,214,0.10);
                border: 1px solid rgba(88,86,214,0.25);
                border-radius: 999px;
                padding: 3px 10px;
            }}
            QLabel#aiApiWarn {{
                font-size: 11px; font-weight: 700;
                color: #FFD000;
                background: rgba(255,159,10,0.14);
                border: 1px solid rgba(255,159,10,0.30);
                border-radius: 999px;
                padding: 3px 10px;
            }}
        """)

    # ──────────────────────────────────────────────────────────
    # BaseWidget hooks
    # ──────────────────────────────────────────────────────────
    def apply_theme_custom(self) -> None:
        d = self.is_dark
        self._header.set_theme(d)
        self._chat_area.set_theme(d)
        self._composer.set_theme(d)
        for it in self._session_items.values():
            it.set_theme(d)
        self._apply_page_qss()

    def apply_settings_custom(self) -> None:
        self._update_model_label()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self._refresh_api_status()
        self._update_model_label()

    # ──────────────────────────────────────────────────────────
    # 세션 관리
    # ──────────────────────────────────────────────────────────
    def _reload_sessions(self) -> None:
        self._sessions = list_sessions()
        # 기존 위젯 제거
        for it in list(self._session_items.values()):
            self._list_layout.removeWidget(it)
            it.setParent(None); it.deleteLater()
        self._session_items.clear()

        if not self._sessions:
            self._sess_empty.setVisible(True)
        else:
            self._sess_empty.setVisible(False)
            for sess in self._sessions:
                item = _SessionItem(sess, is_dark=self.is_dark)
                item.clicked.connect(self._on_session_clicked)
                item.context_requested.connect(self._on_session_context)
                self._list_layout.insertWidget(self._list_layout.count() - 1, item)
                self._session_items[sess["id"]] = item

        # 활성 세션 유지 또는 첫 세션 선택
        if self._active_sid is not None and self._active_sid in self._session_items:
            self._session_items[self._active_sid].set_active(True)
        elif self._sessions:
            self._activate_session(self._sessions[0]["id"])
        else:
            self._active_sid = None
            self._chat_title_lbl.setText(tr("セッションを選択"))
            self._chat_area.clear()

    def _on_new_session_clicked(self) -> None:
        sid = create_session()
        if sid > 0:
            self._reload_sessions()
            self._activate_session(sid)
            self._composer.focus_input()
            self.sessions_changed.emit()
        bus.ai_chat_changed.emit()

    def _on_session_clicked(self, sid: int) -> None:
        self._activate_session(sid)

    def _activate_session(self, sid: int) -> None:
        if self._active_sid is not None and self._active_sid in self._session_items:
            self._session_items[self._active_sid].set_active(False)
        self._active_sid = sid
        if sid in self._session_items:
            self._session_items[sid].set_active(True)
        sess = next((s for s in self._sessions if s["id"] == sid), None)
        if sess:
            self._chat_title_lbl.setText(sess.get("title", tr("無題")))
        # 메시지 로드
        self._messages = list_messages(sid)
        self._chat_area.load_messages(self._messages)

    def _on_session_context(self, sid: int, global_pos: QPoint) -> None:
        menu = QMenu(self)
        act_rename = QAction(tr("名前変更"), menu)
        act_delete = QAction(tr("削除"), menu)
        act_rename.triggered.connect(lambda: self._rename_session(sid))
        act_delete.triggered.connect(lambda: self._delete_session(sid))
        menu.addAction(act_rename); menu.addSeparator(); menu.addAction(act_delete)
        menu.exec(global_pos)

    def _rename_session(self, sid: int) -> None:
        sess = next((s for s in self._sessions if s["id"] == sid), None)
        if sess is None: return
        new_title, ok = QInputDialog.getText(
            self, tr("名前変更"), tr("新しいタイトル:"),
            text=sess.get("title", ""),
        )
        if not ok: return
        rename_session(sid, new_title)
        self._reload_sessions()
        self.sessions_changed.emit()
        bus.ai_chat_changed.emit()

    def _delete_session(self, sid: int) -> None:
        sess = next((s for s in self._sessions if s["id"] == sid), None)
        title = sess.get("title", tr("無題")) if sess else ""
        if not LeeDialog.confirm(
            tr("削除の確認"),
            tr("「{0}」を削除しますか?").format(title),
            ok_text=tr("削除"), destructive=True, parent=self,
        ):
            return
        delete_session(sid)
        if self._active_sid == sid:
            self._active_sid = None
        self._reload_sessions()
        self.sessions_changed.emit()
        bus.ai_chat_changed.emit()

    def _on_clear_session(self) -> None:
        if self._active_sid is None:
            return
        if not LeeDialog.confirm(
            tr("確認"),
            tr("このセッションのメッセージを全て削除しますか?"),
            ok_text=tr("削除"), destructive=True, parent=self,
        ):
            return
        # 메시지만 삭제, 세션은 유지
        try:
            with sqlite3.connect(_ai_chat_db()) as con:
                con.execute("DELETE FROM ai_messages WHERE session_id=?", (self._active_sid,))
        except sqlite3.Error as e:
            logger.warning(f"clear messages failed: {e}")
        self._messages = []
        self._chat_area.clear()
        self._reload_sessions()
        self.sessions_changed.emit()
        bus.ai_chat_changed.emit()

    # ──────────────────────────────────────────────────────────
    # 송수신
    # ──────────────────────────────────────────────────────────
    def _on_suggestion(self, text: str) -> None:
        self._composer.insert_text(text)

    def _on_send(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        gemini_keys = get_all_gemini_keys()
        groq_key = get_builtin_groq_key()
        if not gemini_keys and not groq_key:
            self._refresh_api_status()
            return

        # 활성 세션 없으면 자동 생성 (첫 사용자 메시지로 제목 설정)
        if self._active_sid is None:
            sid = create_session(self._truncate_title(text))
            if sid <= 0: return
            self._reload_sessions()
            self._activate_session(sid)

        # 첫 메시지면 세션 제목을 첫 메시지로 변경
        if not self._messages:
            rename_session(self._active_sid, self._truncate_title(text))

        # UI 즉시 반영
        self._composer.clear()
        self._chat_area.add_bubble("user", text)
        self._messages.append({"role": "user", "content": text})
        append_message(self._active_sid, "user", text)
        self._chat_area.add_thinking()
        self._composer.set_enabled(False)

        from app.core.config import load_settings
        from app.core.app_context import get_current_context
        s = load_settings()
        model = s.get("gemini_model", GEMINI_DEFAULT_MODEL).strip()
        temperature = float(s.get("ai_temperature", 0.7))
        max_tokens = int(s.get("ai_max_tokens", 2048))
        history_limit = int(s.get("chat_history_limit", _MAX_HISTORY))

        # 워커에 전달할 메시지 — content 만
        msgs = [{"role": m["role"], "content": m["content"]} for m in self._messages]
        if len(msgs) > history_limit:
            msgs = msgs[-history_limit:]

        self._worker = AiChatWorker(
            msgs, gemini_keys, groq_key, model,
            temperature=temperature, max_tokens=max_tokens,
            context=get_current_context(),
        )
        self._worker.response_received.connect(self._on_response)
        self._worker.error.connect(self._on_error)
        self._worker.rate_limited.connect(self._on_rate_limited)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()
        self.track_worker(self._worker)
        self._set_status(tr("応答待ち..."))

    def _on_response(self, reply: str) -> None:
        self._chat_area.remove_thinking()
        self._messages.append({"role": "assistant", "content": reply})
        if self._active_sid is not None:
            append_message(self._active_sid, "assistant", reply)
        self._chat_area.add_bubble("assistant", reply)
        self._composer.set_enabled(True)
        self._composer.focus_input()
        self._set_status("")
        # 카드 동기화
        self.sessions_changed.emit()
        bus.ai_chat_changed.emit()
        self._reload_sessions()

    def _on_error(self, err: str) -> None:
        self._chat_area.remove_thinking()
        self._chat_area.add_system_error(f"❌ {tr('AI サービスに接続できません。')}\n{err}")
        self._composer.set_enabled(True)
        self._set_status(tr("エラー"))

    def _on_rate_limited(self) -> None:
        self._chat_area.remove_thinking()
        self._chat_area.add_system_error(
            tr("⏳ 全API のリクエスト上限に達しました。{0} 秒後に再試行できます。").format(_COOLDOWN_SEC)
        )
        self._start_cooldown()

    def _start_cooldown(self) -> None:
        self._cooldown_remaining = _COOLDOWN_SEC
        self._composer.set_enabled(False)
        self._cooldown_timer.start()
        self._update_cooldown_btn()

    def _tick_cooldown(self) -> None:
        self._cooldown_remaining -= 1
        if self._cooldown_remaining <= 0:
            self._cooldown_timer.stop()
            self._composer.set_send_label(tr("送信"))
            self._composer.set_enabled(True)
            self._set_status("")
        else:
            self._update_cooldown_btn()

    def _update_cooldown_btn(self) -> None:
        self._composer.set_send_label(f"{self._cooldown_remaining}s")
        self._set_status(tr("クールダウン中"))

    # ──────────────────────────────────────────────────────────
    # API 상태 / 모델 표시
    # ──────────────────────────────────────────────────────────
    def _refresh_api_status(self) -> None:
        has_gemini = bool(get_all_gemini_keys())
        has_groq = bool(get_builtin_groq_key())
        if not has_gemini and not has_groq:
            self._api_warn.setText(tr("⚠️ API キー未設定"))
            self._api_warn.setVisible(True)
            self._composer.set_enabled(False)
        else:
            self._api_warn.setVisible(False)
            self._composer.set_enabled(True)

    def _update_model_label(self) -> None:
        n = len(get_all_gemini_keys())
        has_groq = bool(get_builtin_groq_key())
        parts = []
        if n:
            parts.append(f"Gemini  ({n}key)")
        if has_groq:
            parts.append("Groq")
        self._model_lbl.setText("  /  ".join(parts) if parts else tr("API 未設定"))

    @staticmethod
    def _truncate_title(text: str, n: int = _MAX_TITLE_LEN) -> str:
        s = text.replace("\n", " ").strip()
        return s if len(s) <= n else s[:n] + "…"

    def _set_status(self, msg: str) -> None:
        self._status_lbl.setText(msg)
        self._status_lbl.setVisible(bool(msg))


# ──────────────────────────────────────────────────────────────────────
# H. 메시지 포맷터 — 마크다운 → RichText (코드블록 / inline / bold / 개행)
# ──────────────────────────────────────────────────────────────────────
def _format_message(text: str, is_dark: bool = True) -> str:
    if is_dark:
        block_bg, block_fg = "#0F1117", "#A8B0BD"
        inline_bg, inline_fg = "#2A2F3A", "#E2E5EA"
    else:
        block_bg, block_fg = "#F0F2F5", "#1A1A1A"
        inline_bg, inline_fg = "#E2E5EA", "#1A1A1A"

    def replace_codeblock(m: re.Match) -> str:
        code = html.escape(m.group(2).strip())
        return (
            f'<div style="background:{block_bg}; color:{block_fg}; border-radius:8px;'
            f' padding:10px 12px; margin:6px 0;'
            f' font-family:JetBrains Mono,Consolas,monospace;'
            f' font-size:12px; white-space:pre-wrap;">{code}</div>'
        )

    text = re.sub(r"```(\w*)\n?(.*?)\n?```", replace_codeblock, text, flags=re.DOTALL)

    parts = re.split(r"(<div[^>]*>.*?</div>)", text, flags=re.DOTALL)
    out = []
    for p in parts:
        if p.startswith("<div"):
            out.append(p)
        else:
            p = html.escape(p)
            p = re.sub(
                r"`([^`]+)`",
                f'<code style="background:{inline_bg}; color:{inline_fg};'
                f' padding:1px 6px; border-radius:4px;'
                f' font-family:JetBrains Mono,Consolas,monospace; font-size:12px;">\\1</code>',
                p,
            )
            p = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", p)
            p = p.replace("\n", "<br>")
            out.append(p)
    return "".join(out)


__all__ = [
    "AiChatCard",
    "AiChatWidget",
    "list_sessions",
    "latest_user_message",
    "latest_assistant_after",
]
