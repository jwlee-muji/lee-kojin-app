"""通知センター ウィジェット — Phase 5.8 リニューアル.

데이터 소스: app/notifications.db (기존 + level 컬럼 ALTER)

디자인 출처: handoff/LEE_PROJECT/varA-detail-screens6.jsx NoticeDetail
            handoff/LEE_PROJECT/varA-widgets.jsx NoticeCard

[Card]
    NotificationCard (대시보드)
        - LeeCard accent="notice" (#FF9500)
        - LeeIconTile + 타이틀 + "今日 X件 / 未読 Y" sub + LeePill (Y NEW, 빨강)
        - 최근 4 개 미리보기 (좌측 컬러 아이콘 26x26 + title + body 1줄 + time)

[Detail page]
    NotificationWidget
        - DetailHeader (← back, 주황 액센트, "未読 X件" badge)
        - 필터 pill 버튼: 全て / 未読 / 既読 (선택 시 #FF9500 fill)
          + 우측 "全て既読にする" 버튼
        - 알림 카드 리스트 (큰 색 아이콘 40x40 + title + read dot + time + body)
        - 자동 새로고침 30 초

브리핑은 별도 widget (app/widgets/briefing.py) 에서 처리.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from app.core.events import bus
from app.core.i18n import tr
from app.ui.common import BaseWidget
from app.ui.components import (
    LeeCard, LeeDetailHeader, LeeIconTile, LeePill,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 토큰
# ──────────────────────────────────────────────────────────────────────
_C_NOTICE = "#FF9500"   # --c-notice (iOS 오렌지)
_C_INFO   = "#0A84FF"   # --c-info
_C_OK     = "#30D158"   # --c-ok
_C_WARN   = "#FF9F0A"   # --c-warn
_C_BAD    = "#FF453A"   # --c-bad

# 레벨별 색/글리프 매핑 (mockup 의 levelColor/levelIcon)
_LEVEL_META: dict[str, dict] = {
    "info":    {"color": _C_INFO, "glyph": "ℹ", "label": "情報"},
    "success": {"color": _C_OK,   "glyph": "✓", "label": "完了"},
    "warning": {"color": _C_WARN, "glyph": "▲", "label": "注意"},
    "error":   {"color": _C_BAD,  "glyph": "!", "label": "重要"},
}
# 별칭 — 외부에서 들어오는 다양한 표기 정규화
_LEVEL_ALIAS = {
    "ok":    "success", "warn": "warning", "bad": "error", "alert": "error",
    "":      "info",    None:  "info",
}

_DB_RETENTION_DAYS = 30


# ──────────────────────────────────────────────────────────────────────
# DB 레이어 (notifications.db)
# ──────────────────────────────────────────────────────────────────────
def _notif_db_path() -> Path:
    from app.core.config import APP_DIR
    return APP_DIR / "notifications.db"


# 모듈 단위 캐시 — 한 세션 내 단 1 회만 schema/cleanup 수행
_db_initialized = False


def ensure_notification_db() -> None:
    """테이블 + level 컬럼 (alter) + 보존 정리.

    프로세스 1 회만 실행 (모듈 캐시) — `add_notification` 마다 호출되어도
    무거운 ALTER/DELETE 가 반복되지 않도록 보장.
    """
    global _db_initialized
    if _db_initialized:
        return
    p = _notif_db_path()
    try:
        with sqlite3.connect(p) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    title     TEXT,
                    message   TEXT,
                    timestamp TEXT,
                    is_read   INTEGER DEFAULT 0
                )
            """)
            cols = {row[1] for row in con.execute("PRAGMA table_info(notifications)").fetchall()}
            if "level" not in cols:
                con.execute("ALTER TABLE notifications ADD COLUMN level TEXT DEFAULT 'info'")
            con.execute(
                f"DELETE FROM notifications "
                f"WHERE date(timestamp) < date('now', '-{_DB_RETENTION_DAYS} days')"
            )
        _db_initialized = True
    except sqlite3.Error as e:
        logger.error(f"通知DB初期化失敗: {e}")


def _normalize_level(level: Optional[str]) -> str:
    if level in _LEVEL_META:
        return level
    return _LEVEL_ALIAS.get(level, "info")


def add_notification(title: str, message: str, level: str = "info") -> int:
    ensure_notification_db()
    level = _normalize_level(level)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with sqlite3.connect(_notif_db_path()) as con:
            cur = con.execute(
                "INSERT INTO notifications (title, message, timestamp, level) "
                "VALUES (?, ?, ?, ?)",
                (title, message, ts, level),
            )
            new_id = cur.lastrowid or -1
    except sqlite3.Error as e:
        logger.error(f"通知DB保存失敗: {e}")
        return -1
    # 글로벌 알림 갱신 시그널 — 대시보드 카드 + sidebar 배지 자동 갱신
    try:
        bus.notifications_changed.emit()
    except Exception:
        pass
    return new_id


def list_notifications() -> list[dict]:
    ensure_notification_db()
    try:
        with sqlite3.connect(_notif_db_path()) as con:
            rows = con.execute(
                "SELECT id, title, message, timestamp, is_read, "
                "       COALESCE(level, 'info') AS level "
                "FROM notifications ORDER BY id DESC"
            ).fetchall()
    except sqlite3.Error as e:
        logger.error(f"通知DB読込失敗: {e}")
        return []
    return [
        {
            "id":        r[0],
            "title":     r[1] or "",
            "message":   r[2] or "",
            "timestamp": r[3] or "",
            "is_read":   bool(r[4]),
            "level":     _normalize_level(r[5]),
        }
        for r in rows
    ]


def _emit_changed() -> None:
    try:
        bus.notifications_changed.emit()
    except Exception:
        pass


def mark_read(notif_id: int) -> None:
    try:
        with sqlite3.connect(_notif_db_path()) as con:
            con.execute("UPDATE notifications SET is_read=1 WHERE id=?", (notif_id,))
    except sqlite3.Error as e:
        logger.error(f"通知既読更新失敗: {e}")
    _emit_changed()


def mark_all_read() -> None:
    try:
        with sqlite3.connect(_notif_db_path()) as con:
            con.execute("UPDATE notifications SET is_read=1 WHERE is_read=0")
    except sqlite3.Error as e:
        logger.error(f"通知全件既読失敗: {e}")
    _emit_changed()


def delete_notification(notif_id: int) -> None:
    try:
        with sqlite3.connect(_notif_db_path()) as con:
            con.execute("DELETE FROM notifications WHERE id=?", (notif_id,))
    except sqlite3.Error as e:
        logger.error(f"通知DB削除失敗: {e}")
    _emit_changed()


def count_unread() -> int:
    try:
        with sqlite3.connect(_notif_db_path()) as con:
            row = con.execute(
                "SELECT COUNT(*) FROM notifications WHERE is_read=0"
            ).fetchone()
            return int(row[0]) if row else 0
    except sqlite3.Error:
        return 0


def count_today() -> int:
    try:
        with sqlite3.connect(_notif_db_path()) as con:
            row = con.execute(
                "SELECT COUNT(*) FROM notifications "
                "WHERE date(timestamp) = date('now')"
            ).fetchone()
            return int(row[0]) if row else 0
    except sqlite3.Error:
        return 0


# ──────────────────────────────────────────────────────────────────────
# 시각 표기 헬퍼 (모킹업 "12分前" 같은 상대 시각)
# ──────────────────────────────────────────────────────────────────────
def _fmt_relative(ts: str) -> str:
    if not ts:
        return ""
    try:
        dt = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts[11:16] if len(ts) >= 16 else ts
    delta = datetime.now() - dt
    if delta.days >= 2:
        return f"{delta.days}日前"
    if delta.days == 1:
        return tr("昨日")
    if delta.seconds >= 3600:
        return f"{delta.seconds // 3600}時間前"
    if delta.seconds >= 60:
        return f"{delta.seconds // 60}分前"
    return tr("今")


def _hex_to_rgb(s: str) -> tuple[int, int, int]:
    h = s.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# ──────────────────────────────────────────────────────────────────────
# A. NotificationCard — 대시보드 카드
# ──────────────────────────────────────────────────────────────────────
class NotificationCard(LeeCard):
    """通知センター 카드 — mockup 1:1.

    레이아웃:
        ┌─────────────────────────────────────────────────────┐
        │ [icon] 通知センター                       [3 NEW]   │
        │        本日 8 件 / 未読 3                            │
        │                                                      │
        │ ┃ [!]  東京エリア予備率警報         12分前           │
        │ ┃     予備率が 6.2% に低下しました                    │
        │ ─                                                    │
        │ ┃ [i]  JEPX 約定結果                32分前           │
        │ ┃     システムプライス 12.84 円/kWh                  │
        │ (4 rows)                                             │
        └─────────────────────────────────────────────────────┘
    """

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(accent_color="notice", interactive=True, parent=parent)
        self.setMinimumHeight(280)
        self._is_dark = True
        self._notifications: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(0)

        # 헤더
        header = QHBoxLayout(); header.setSpacing(12); header.setContentsMargins(0, 0, 0, 12)
        self._icon = LeeIconTile(
            icon=QIcon(":/img/notice.svg"),
            color=_C_NOTICE, size=40, radius=12,
        )
        header.addWidget(self._icon, 0, Qt.AlignTop)

        title_box = QVBoxLayout(); title_box.setSpacing(2); title_box.setContentsMargins(0, 0, 0, 0)
        self._title_lbl = QLabel(tr("通知センター"))
        self._title_lbl.setObjectName("notifCardTitle")
        self._sub_lbl = QLabel(tr("待機中..."))
        self._sub_lbl.setObjectName("notifCardSub")
        title_box.addWidget(self._title_lbl)
        title_box.addWidget(self._sub_lbl)
        header.addLayout(title_box, 1)

        # 미읽음 NEW pill
        self._pill = LeePill("0 NEW", variant="error")
        header.addWidget(self._pill, 0, Qt.AlignTop)
        self._pill.setVisible(False)   # setVisible 은 layout 추가 후

        layout.addLayout(header)

        # 4 행 미리보기
        self._slots: list[_NotifPreviewRow] = []
        for _ in range(4):
            slot = _NotifPreviewRow()
            layout.addWidget(slot)
            layout.addSpacing(4)
            self._slots.append(slot)

        self._empty = QLabel(tr("通知はありません"))
        self._empty.setObjectName("notifCardEmpty")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setMinimumHeight(80)
        layout.addWidget(self._empty)
        self._empty.setVisible(False)   # setVisible 은 layout 추가 후

        layout.addStretch()
        self._apply_local_qss()
        self.set_notifications([])

    def set_notifications(self, items: list[dict]) -> None:
        self._notifications = list(items) if items else []
        unread = sum(1 for n in self._notifications if not n.get("is_read"))
        today = sum(
            1 for n in self._notifications
            if n.get("timestamp", "")[:10] == datetime.now().strftime("%Y-%m-%d")
        )
        self._sub_lbl.setText(
            tr("本日 {0} 件 / 未読 {1}").format(today, unread)
        )
        if unread > 0:
            self._pill.setText(f"{unread} NEW")
            self._pill.setVisible(True)
        else:
            self._pill.setVisible(False)

        top4 = self._notifications[:4]
        if not top4:
            for s in self._slots:
                s.setVisible(False)
            self._empty.setVisible(True)
            return
        self._empty.setVisible(False)
        for i, slot in enumerate(self._slots):
            if i < len(top4):
                slot.set_notification(top4[i], is_dark=self._is_dark)
                slot.setVisible(True)
            else:
                slot.setVisible(False)

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        for s in self._slots:
            s.set_theme(is_dark)
        self._apply_local_qss()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def _apply_local_qss(self) -> None:
        is_dark = self._is_dark
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        self.setStyleSheet(f"""
            QLabel#notifCardTitle {{
                font-size: 13px; font-weight: 600;
                color: {fg_secondary}; background: transparent;
            }}
            QLabel#notifCardSub {{
                font-size: 11px; color: {fg_tertiary};
                background: transparent;
            }}
            QLabel#notifCardEmpty {{
                font-size: 11px; color: {fg_tertiary};
                background: transparent; font-style: italic;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# A1. _NotifPreviewRow — 카드 안 한 행 (모킹업 NoticeCard 행 1:1)
# ──────────────────────────────────────────────────────────────────────
class _NotifPreviewRow(QFrame):
    """좌측 26×26 컬러 아이콘 + 제목/본문 + 우측 상대 시각."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("notifPreviewRow")
        self.setFixedHeight(48)
        self._is_dark = True
        self._color = _C_NOTICE
        self._unread = False

        h = QHBoxLayout(self)
        h.setContentsMargins(10, 5, 10, 5); h.setSpacing(10)

        self._icon_lbl = QLabel("●")
        self._icon_lbl.setObjectName("rowIcon")
        self._icon_lbl.setFixedSize(26, 26)
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        h.addWidget(self._icon_lbl)

        text_box = QVBoxLayout(); text_box.setContentsMargins(0, 0, 0, 0); text_box.setSpacing(0)
        self._title_lbl = QLabel("")
        self._title_lbl.setObjectName("rowTitle")
        text_box.addWidget(self._title_lbl)
        self._body_lbl = QLabel("")
        self._body_lbl.setObjectName("rowBody")
        text_box.addWidget(self._body_lbl)
        h.addLayout(text_box, 1)

        self._time_lbl = QLabel("")
        self._time_lbl.setObjectName("rowTime")
        self._time_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        h.addWidget(self._time_lbl)

        self._apply_qss()

    def set_notification(self, n: dict, *, is_dark: bool) -> None:
        self._is_dark = is_dark
        meta = _LEVEL_META.get(n.get("level", "info"), _LEVEL_META["info"])
        self._color = meta["color"]
        self._unread = not n.get("is_read")
        self._icon_lbl.setText(meta["glyph"])
        self._title_lbl.setText(self._elide(n.get("title", ""), 36))
        self._body_lbl.setText(self._elide(n.get("message", ""), 56))
        self._time_lbl.setText(_fmt_relative(n.get("timestamp", "")))
        self._apply_qss()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    @staticmethod
    def _elide(s: str, n: int) -> str:
        return s if len(s) <= n else s[:n] + "…"

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        border_subtle = "rgba(255,255,255,0.04)" if is_dark else "rgba(11,18,32,0.06)"
        r, g, b = _hex_to_rgb(self._color)
        # 카드 root 와 융화 — bg transparent, 구분은 border 만으로
        # unread 는 강조된 컬러 border, read 는 옅은 surface border
        if self._unread:
            bg = "transparent"
            border = f"1px solid rgba({r},{g},{b},0.30)"
        else:
            bg = "transparent"
            border = f"1px solid {border_subtle}"
        self.setStyleSheet(f"""
            QFrame#notifPreviewRow {{
                background: {bg};
                border: {border};
                border-radius: 10px;
            }}
            QLabel#rowIcon {{
                background: {self._color};
                color: white;
                border-radius: 8px;
                font-size: 13px; font-weight: 800;
            }}
            QLabel#rowTitle {{
                font-size: 11px; font-weight: 700;
                color: {fg_primary}; background: transparent;
            }}
            QLabel#rowBody {{
                font-size: 10px;
                color: {fg_secondary}; background: transparent;
            }}
            QLabel#rowTime {{
                font-size: 9px;
                font-family: "JetBrains Mono", "Consolas", monospace;
                color: {fg_tertiary}; background: transparent;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# B. _NotifListItem — 디테일 페이지 알림 카드 행
# ──────────────────────────────────────────────────────────────────────
class _NotifListItem(QFrame):
    """디테일 리스트의 단일 알림 (40x40 큰 아이콘, 미읽음 강조 좌측 보더)."""

    clicked        = Signal(int)
    delete_clicked = Signal(int)

    def __init__(self, n: dict, *, is_dark: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("notifListItem")
        self._is_dark = is_dark
        self._n = n
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)

        meta = _LEVEL_META.get(n.get("level", "info"), _LEVEL_META["info"])
        self._color = meta["color"]
        self._unread = not n.get("is_read")

        h = QHBoxLayout(self)
        h.setContentsMargins(18, 14, 14, 14); h.setSpacing(14)

        # 좌 큰 아이콘 (color soft bg)
        self._icon_lbl = QLabel(meta["glyph"])
        self._icon_lbl.setObjectName("itemIcon")
        self._icon_lbl.setFixedSize(40, 40)
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        h.addWidget(self._icon_lbl, 0, Qt.AlignTop)

        # 본문
        body_box = QVBoxLayout()
        body_box.setContentsMargins(0, 0, 0, 0); body_box.setSpacing(4)

        head = QHBoxLayout(); head.setContentsMargins(0, 0, 0, 0); head.setSpacing(8)
        self._title_lbl = QLabel(n.get("title", ""))
        self._title_lbl.setObjectName("itemTitle")
        head.addWidget(self._title_lbl)

        self._dot = QLabel("●")
        self._dot.setObjectName("itemDot")
        head.addWidget(self._dot)
        self._dot.setVisible(self._unread)   # setVisible 은 layout 추가 후
        head.addStretch()

        self._time_lbl = QLabel(_fmt_relative(n.get("timestamp", "")))
        self._time_lbl.setObjectName("itemTime")
        self._time_lbl.setToolTip(n.get("timestamp", ""))
        head.addWidget(self._time_lbl)
        body_box.addLayout(head)

        self._body_lbl = QLabel(n.get("message", ""))
        self._body_lbl.setObjectName("itemBody")
        self._body_lbl.setWordWrap(True)
        body_box.addWidget(self._body_lbl)

        h.addLayout(body_box, 1)

        self._del_btn = QPushButton("×")
        self._del_btn.setObjectName("itemDelBtn")
        self._del_btn.setFixedSize(24, 24)
        self._del_btn.setCursor(Qt.PointingHandCursor)
        self._del_btn.setToolTip(tr("削除"))
        self._del_btn.clicked.connect(lambda: self.delete_clicked.emit(self._n.get("id", -1)))
        h.addWidget(self._del_btn, 0, Qt.AlignTop)

        self._apply_qss()

    def notif_id(self) -> int:
        return int(self._n.get("id", -1))

    def is_unread(self) -> bool:
        return self._unread

    def mark_read_local(self) -> None:
        self._unread = False
        self._n["is_read"] = True
        self._dot.setVisible(False)
        self._apply_qss()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            child = self.childAt(event.pos())
            if child is not self._del_btn:
                self.clicked.emit(self._n.get("id", -1))
        super().mousePressEvent(event)

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        r, g, b = _hex_to_rgb(self._color)
        if self._unread:
            bg = f"rgba({r},{g},{b},0.05)"
            border_left = f"3px solid {self._color}"
        else:
            bg = "transparent"
            border_left = "3px solid transparent"
        self.setStyleSheet(f"""
            QFrame#notifListItem {{
                background: {bg};
                border: 1px solid transparent;
                border-left: {border_left};
                border-radius: 12px;
            }}
            QFrame#notifListItem:hover {{
                background: rgba({r},{g},{b},0.08);
            }}
            QLabel#itemIcon {{
                background: rgba({r},{g},{b},0.18);
                color: {self._color};
                border-radius: 12px;
                font-size: 18px; font-weight: 800;
            }}
            QLabel#itemTitle {{
                font-size: 13px; font-weight: 800;
                color: {fg_primary}; background: transparent;
            }}
            QLabel#itemDot {{
                color: {self._color};
                font-size: 8px; background: transparent;
            }}
            QLabel#itemTime {{
                font-size: 11px;
                font-family: "JetBrains Mono", "Consolas", monospace;
                color: {fg_tertiary}; background: transparent;
            }}
            QLabel#itemBody {{
                font-size: 12px;
                color: {fg_secondary}; background: transparent;
            }}
            QPushButton#itemDelBtn {{
                background: transparent;
                color: {fg_tertiary};
                border: none;
                border-radius: 12px;
                font-size: 16px;
            }}
            QPushButton#itemDelBtn:hover {{
                background: rgba(255,69,58,0.18);
                color: #FF453A;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# C. _FilterPill — 디테일 상단 필터 버튼 (모킹업 정확 매핑)
# ──────────────────────────────────────────────────────────────────────
class _FilterPill(QPushButton):
    """필터 pill — 선택 시 #FF9500 fill, 비선택 시 surface bg."""

    def __init__(self, label: str, key: str, parent=None):
        super().__init__(label, parent)
        self._key = key
        self._active = False
        self._is_dark = True
        self.setObjectName("notifFilterPill")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(36)
        self.setMinimumWidth(82)
        self._apply_qss()

    def key(self) -> str:
        return self._key

    def set_active(self, active: bool) -> None:
        self._active = active
        self.setChecked(active)
        self._apply_qss()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        bg_surface   = "#14161C" if is_dark else "#FFFFFF"
        border       = "rgba(255,255,255,0.10)" if is_dark else "rgba(11,18,32,0.10)"
        if self._active:
            self.setStyleSheet(f"""
                QPushButton#notifFilterPill {{
                    background: {_C_NOTICE};
                    color: white;
                    border: 1px solid {_C_NOTICE};
                    border-radius: 10px;
                    padding: 0 16px;
                    font-size: 12px; font-weight: 700;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton#notifFilterPill {{
                    background: {bg_surface};
                    color: {fg_primary};
                    border: 1px solid {border};
                    border-radius: 10px;
                    padding: 0 16px;
                    font-size: 12px; font-weight: 700;
                }}
                QPushButton#notifFilterPill:hover {{
                    border-color: {_C_NOTICE};
                    color: {_C_NOTICE};
                }}
            """)


# ──────────────────────────────────────────────────────────────────────
# D. NotificationWidget — 디테일 페이지
# ──────────────────────────────────────────────────────────────────────
class NotificationWidget(BaseWidget):
    """通知センター — DetailHeader + 필터 pill + 알림 리스트 (자동 갱신)."""

    notifications_changed = Signal(list)

    def __init__(self):
        super().__init__()
        ensure_notification_db()
        self._filter = "all"   # all / unread / read
        self._notifications: list[dict] = []
        self._items: dict[int, _NotifListItem] = {}
        # 본 위젯이 직접 mark_read 등 호출 시 bus 시그널이 자기 자신에게 돌아오는 것 방지
        self._local_mutating = False

        # 외부 알림 (gmail / 인밸런스 alert 등) 변경 시 debounce 후 재로드
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(250)
        self._reload_timer.timeout.connect(self._reload_list)
        bus.notifications_changed.connect(self._on_external_changed)

        # 자동 새로고침 30 초 (시간 라벨 재계산용)
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(30_000)
        self._auto_timer.timeout.connect(self._reload_list)
        self._auto_timer.start()

        self._build_ui()
        self._reload_list()

    def _on_external_changed(self) -> None:
        """bus.notifications_changed 발화 시 — 자체 mutation 이면 무시, 외부면 debounce 재로드."""
        if self._local_mutating:
            return
        self._reload_timer.start()  # singleshot — 다중 emit 도 1 회만 처리

    # ──────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setObjectName("notifPageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer.addWidget(scroll, 1)

        content = QWidget()
        content.setObjectName("notifPageContent")
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(28, 22, 28, 22); root.setSpacing(14)

        # 1) DetailHeader
        self._header = LeeDetailHeader(
            title=tr("通知センター"),
            subtitle=tr("システム + 市場 + 業務 全通知"),
            accent=_C_NOTICE,
            icon_qicon=QIcon(":/img/notice.svg"),
            badge="",
            show_export=False,
        )
        self._header.back_clicked.connect(lambda: bus.page_requested.emit(0))
        root.addWidget(self._header)

        # 2) 필터 pill 행 + 全て既読
        filter_row = QHBoxLayout(); filter_row.setSpacing(6)
        self._pill_all    = _FilterPill(tr("全て"),  "all")
        self._pill_unread = _FilterPill(tr("未読"),  "unread")
        self._pill_read   = _FilterPill(tr("既読"),  "read")
        for p in (self._pill_all, self._pill_unread, self._pill_read):
            p.clicked.connect(lambda _=False, key=p.key(): self._on_filter_changed(key))
            filter_row.addWidget(p)
        self._pill_all.set_active(True)
        filter_row.addStretch()

        self._btn_mark_all = QPushButton(tr("全て既読にする"))
        self._btn_mark_all.setObjectName("notifMarkAllBtn")
        self._btn_mark_all.setCursor(Qt.PointingHandCursor)
        self._btn_mark_all.setFixedHeight(36)
        self._btn_mark_all.clicked.connect(self._on_mark_all_read)
        filter_row.addWidget(self._btn_mark_all)
        root.addLayout(filter_row)

        # 3) 리스트 카드
        self._list_card = QFrame()
        self._list_card.setObjectName("notifListCard")
        list_lay = QVBoxLayout(self._list_card)
        list_lay.setContentsMargins(8, 8, 8, 8); list_lay.setSpacing(4)
        self._list_layout = list_lay

        self._empty_lbl = QLabel(tr("通知はありません"))
        self._empty_lbl.setObjectName("notifEmpty")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setMinimumHeight(120)
        list_lay.addWidget(self._empty_lbl)
        root.addWidget(self._list_card)

        # 4) 상태 라벨 (조용한 토스트)
        st_row = QHBoxLayout(); st_row.setSpacing(10)
        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("notifStatusLbl")
        st_row.addWidget(self._status_lbl)
        st_row.addStretch()
        root.addLayout(st_row)

        root.addStretch()
        self._apply_page_qss()

    def _apply_page_qss(self) -> None:
        is_dark = self.is_dark
        bg_app        = "#0A0B0F" if is_dark else "#F5F6F8"
        fg_secondary  = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary   = "#6B7280" if is_dark else "#8A93A6"
        bg_surface    = "#14161C" if is_dark else "#FFFFFF"
        border_subtle = "rgba(255,255,255,0.06)" if is_dark else "rgba(11,18,32,0.06)"
        border        = "rgba(255,255,255,0.10)" if is_dark else "rgba(11,18,32,0.10)"
        self.setStyleSheet(f"""
            NotificationWidget {{ background: {bg_app}; }}
            QScrollArea#notifPageScroll {{ background: {bg_app}; border: none; }}
            QWidget#notifPageContent {{ background: {bg_app}; }}
            QFrame#notifListCard {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 18px;
            }}
            QLabel#notifEmpty {{
                font-size: 12px; color: {fg_tertiary};
                background: transparent; font-style: italic;
                padding: 24px 0;
            }}
            QPushButton#notifMarkAllBtn {{
                background: {bg_surface};
                color: {fg_secondary};
                border: 1px solid {border};
                border-radius: 10px;
                padding: 0 16px;
                font-size: 12px; font-weight: 700;
            }}
            QPushButton#notifMarkAllBtn:hover {{
                color: {_C_NOTICE};
                border-color: {_C_NOTICE};
                background: rgba(255,149,0,0.08);
            }}
            QLabel#notifStatusLbl {{
                font-size: 11px; font-weight: 600;
                color: {_C_OK};
                background: rgba(48,209,88,0.10);
                border: 1px solid rgba(48,209,88,0.25);
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
        for p in (self._pill_all, self._pill_unread, self._pill_read):
            p.set_theme(d)
        for it in self._items.values():
            it.set_theme(d)
        self._apply_page_qss()

    def apply_settings_custom(self) -> None:
        pass

    # ──────────────────────────────────────────────────────────
    # 데이터 로드 / 갱신
    # ──────────────────────────────────────────────────────────
    def _reload_list(self) -> None:
        self._notifications = list_notifications()
        self._rebuild_list()
        self.notifications_changed.emit(list(self._notifications))

    def _rebuild_list(self) -> None:
        for it in list(self._items.values()):
            self._list_layout.removeWidget(it)
            it.setParent(None); it.deleteLater()
        self._items.clear()

        if self._filter == "unread":
            visible = [n for n in self._notifications if not n["is_read"]]
        elif self._filter == "read":
            visible = [n for n in self._notifications if n["is_read"]]
        else:
            visible = list(self._notifications)

        unread = sum(1 for n in self._notifications if not n["is_read"])
        self._header.set_badge(tr("未読 {0}件").format(unread))

        if not visible:
            self._empty_lbl.setVisible(True)
        else:
            self._empty_lbl.setVisible(False)
            for n in visible:
                item = _NotifListItem(n, is_dark=self.is_dark)
                item.clicked.connect(self._on_item_clicked)
                item.delete_clicked.connect(self._on_item_delete)
                self._list_layout.insertWidget(self._list_layout.count() - 1, item)
                self._items[n["id"]] = item

    def _on_filter_changed(self, key: str) -> None:
        self._filter = key
        for p in (self._pill_all, self._pill_unread, self._pill_read):
            p.set_active(p.key() == key)
        self._rebuild_list()

    def _on_mark_all_read(self) -> None:
        if not any(not n["is_read"] for n in self._notifications):
            self._show_status(tr("未読の通知がありません"))
            return
        self._local_mutating = True
        try:
            mark_all_read()
            self._reload_list()
        finally:
            self._local_mutating = False
        self._show_status(tr("全て既読にしました"))

    def _on_item_clicked(self, notif_id: int) -> None:
        item = self._items.get(notif_id)
        if item is None: return
        if item.is_unread():
            self._local_mutating = True
            try:
                mark_read(notif_id)
            finally:
                self._local_mutating = False
            item.mark_read_local()
            for n in self._notifications:
                if n["id"] == notif_id:
                    n["is_read"] = True
            unread = sum(1 for n in self._notifications if not n["is_read"])
            self._header.set_badge(tr("未読 {0}件").format(unread))
            self.notifications_changed.emit(list(self._notifications))

    def _on_item_delete(self, notif_id: int) -> None:
        self._local_mutating = True
        try:
            delete_notification(notif_id)
            self._reload_list()
        finally:
            self._local_mutating = False
        self._show_status(tr("通知を削除しました"))

    def _show_status(self, msg: str, ms: int = 2200) -> None:
        self._status_lbl.setText(msg)
        QTimer.singleShot(ms, lambda: self._status_lbl.setText(""))


__all__ = [
    "NotificationCard",
    "NotificationWidget",
    "ensure_notification_db",
    "add_notification",
    "list_notifications",
    "mark_read",
    "mark_all_read",
    "delete_notification",
    "count_unread",
    "count_today",
]
