"""AI ブリーフィング ウィジェット — Phase 5.8 リニューアル.

데이터 소스: app/briefings.db (기존 그대로)
Worker: app.api.briefing_api.BriefingWorker (기존 그대로 사용)

디자인 출처: handoff/LEE_PROJECT/varA-misc-detail2.jsx BriefDetail
            handoff/LEE_PROJECT/varA-widgets.jsx BriefCard

[Card]
    BriefCard (대시보드)
        - LeeCard accent="ai" (#5856D6)
        - LeeIconTile + "AI 朝のブリーフィング" + 생성 시각 sub + LeePill "NEW" (최신 24h 내)
        - 본문 — 최신 daily 브리핑의 첫 문단/요약 markdown 렌더 (3-4 줄)
        - 하단 KPI strip (3 cards): 予備率 / スポット平均 / JKM
          dashboard 가 setter 로 값 주입

[Detail page]
    BriefingWidget
        - DetailHeader (← back, 인디고 액센트 #5856D6, "AI 生成" badge)
        - 생성 컨트롤 카드:
            · 期間 segment (今日 / 今週 / 今月 / 来月)
            · 言語 dropdown (日 / 韓 / 英 / 中)
            · 생성 버튼 (#5856D6 fill)
            · 가중치 표시 (過去/現在/将来 %)
            · 상태 라벨 (생성 중 / 완료 / 에러)
        - 분할 패널:
            · 좌 260px 履歴: 검색 + 期間/言語 filter + 履歴 list + 削除
            · 우 flex 内容: period pill + lang + 시각 + markdown body
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QIcon, QTextOption
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QScrollArea, QSplitter, QTextEdit,
    QVBoxLayout, QWidget,
)

from app.api.briefing_api import BriefingWorker, calc_weights
from app.core.events import bus
from app.core.i18n import tr
from app.ui.common import BaseWidget
from app.ui.components import (
    LeeCard, LeeDetailHeader, LeeDialog, LeeIconTile, LeePill, LeeSegment,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 토큰 / 정수
# ──────────────────────────────────────────────────────────────────────
_C_AI       = "#5856D6"   # --c-ai (인디고)
_C_AI_SOFT  = "rgba(88,86,214,0.14)"
_C_OK       = "#30D158"
_C_BAD      = "#FF453A"
_C_IMB      = "#F25C7A"   # --c-imb (핑크)
_C_SPOT     = "#FF7A45"   # --c-spot (오렌지)
_C_JKM      = "#F4B740"   # --c-jkm (옐로)

_PERIODS = [
    ("daily",      {"ja": "今日", "ko": "오늘",   "en": "Today",      "zh": "今天",
                    "pja": "デイリー"}),
    ("weekly",     {"ja": "今週", "ko": "이번 주","en": "This Week",  "zh": "本周",
                    "pja": "週間"}),
    ("monthly",    {"ja": "今月", "ko": "이번 달","en": "This Month", "zh": "本月",
                    "pja": "今月"}),
    ("next_month", {"ja": "来月", "ko": "다음 달","en": "Next Month", "zh": "下月",
                    "pja": "来月"}),
]

_LANG_OPTIONS = [
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("en", "English"),
    ("zh", "中文"),
]

_GEN_LABEL = {
    "ja": "ブリーフィング生成",
    "ko": "브리핑 생성",
    "en": "Generate Briefing",
    "zh": "生成简报",
}
_RUNNING_LABEL = {
    "ja": "生成中...", "ko": "생성 중...", "en": "Generating...", "zh": "生成中...",
}
_WEIGHT_LABEL = {
    "ja": ("過去分析", "現在状況", "将来予測"),
    "ko": ("과거 분석", "현재 상황", "미래 예측"),
    "en": ("Past", "Current", "Future"),
    "zh": ("历史", "当前", "未来"),
}
_PLACEHOLDER = {
    "ja": "期間を選択して「ブリーフィング生成」をクリックしてください。\nAI が日本電力市場の過去・現在・将来を分析します。",
    "ko": "기간을 선택하고 「브리핑 생성」을 클릭하세요.\nAI가 일본 전력 시장의 과거・현재・미래를 분석합니다.",
    "en": "Select a period and click 'Generate Briefing'.\nAI will analyse past, present, and future trends in the Japanese power market.",
    "zh": "选择时间段后点击「生成简报」。\nAI 将分析日本电力市场的历史、现状与未来。",
}


# ──────────────────────────────────────────────────────────────────────
# DB 레이어 (briefings.db) — 기존 보존
# ──────────────────────────────────────────────────────────────────────
def _briefing_db() -> Path:
    from app.core.config import APP_DIR
    return APP_DIR / "briefings.db"


def _init_db() -> None:
    db = _briefing_db()
    try:
        with sqlite3.connect(str(db)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS briefings (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    period     TEXT NOT NULL,
                    lang       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_briefings_created ON briefings(created_at)"
            )
    except sqlite3.Error as e:
        logger.error(f"briefing DB 초기화 실패: {e}")


def _save_to_db(period: str, lang: str, content: str, created_at: str) -> int:
    with sqlite3.connect(str(_briefing_db())) as conn:
        cur = conn.execute(
            "INSERT INTO briefings (period, lang, content, created_at) VALUES (?,?,?,?)",
            (period, lang, content, created_at),
        )
        return cur.lastrowid or -1


def _load_list(period_f: str = "", lang_f: str = "", text_f: str = "") -> list[tuple]:
    db = _briefing_db()
    if not db.exists():
        return []
    conds, params = [], []
    if period_f:
        conds.append("period = ?"); params.append(period_f)
    if lang_f:
        conds.append("lang = ?");   params.append(lang_f)
    if text_f:
        conds.append("content LIKE ?"); params.append(f"%{text_f}%")
    where = f"WHERE {' AND '.join(conds)}" if conds else ""
    try:
        with sqlite3.connect(str(db)) as conn:
            return conn.execute(
                f"SELECT id, period, lang, created_at FROM briefings {where} "
                "ORDER BY created_at DESC LIMIT 300",
                params,
            ).fetchall()
    except sqlite3.Error as e:
        logger.warning(f"briefing list 失敗: {e}")
        return []


def _load_content(row_id: int) -> str:
    db = _briefing_db()
    if not db.exists():
        return ""
    try:
        with sqlite3.connect(str(db)) as conn:
            row = conn.execute(
                "SELECT content FROM briefings WHERE id = ?", (row_id,)
            ).fetchone()
        return row[0] if row else ""
    except sqlite3.Error:
        return ""


def _delete_from_db(row_id: int) -> None:
    db = _briefing_db()
    if not db.exists(): return
    try:
        with sqlite3.connect(str(db)) as conn:
            conn.execute("DELETE FROM briefings WHERE id = ?", (row_id,))
    except sqlite3.Error as e:
        logger.warning(f"briefing 삭제 실패: {e}")


def latest_briefing(period: str, lang: str = "ja") -> Optional[dict]:
    """해당 period+lang 의 최신 브리핑 (없으면 lang 무관 최신)."""
    db = _briefing_db()
    if not db.exists(): return None
    try:
        with sqlite3.connect(str(db)) as conn:
            row = conn.execute(
                "SELECT id, content, created_at, lang FROM briefings "
                "WHERE period=? AND lang=? ORDER BY created_at DESC LIMIT 1",
                (period, lang),
            ).fetchone()
            if not row:
                # fallback — period only
                row = conn.execute(
                    "SELECT id, content, created_at, lang FROM briefings "
                    "WHERE period=? ORDER BY created_at DESC LIMIT 1",
                    (period,),
                ).fetchone()
        if not row:
            return None
        return {
            "id":         row[0],
            "content":    row[1],
            "created_at": row[2],
            "lang":       row[3],
        }
    except sqlite3.Error:
        return None


# ──────────────────────────────────────────────────────────────────────
# A. BriefCard — 대시보드 카드
# ──────────────────────────────────────────────────────────────────────
class BriefCard(LeeCard):
    """AI 朝のブリーフィング 카드 — mockup BriefCard 1:1.

    레이아웃:
        ┌─────────────────────────────────────────────────────┐
        │ [icon] AI 朝のブリーフィング              [NEW]     │
        │        2025-05-03 06:00 自動生成                     │
        │                                                      │
        │ おはようございます。本日は **東京エリア予備率 6.2%**  │
        │ ...                                                  │
        │                                                      │
        ├──────────────────────────────────────────────────────┤
        │   6.2 %       10.78        14.32                     │
        │   予備率      スポット平均  JKM                       │
        └─────────────────────────────────────────────────────┘
    """

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(accent_color="ai", interactive=True, parent=parent)
        self.setMinimumHeight(260)
        self._is_dark = True
        self._latest: Optional[dict] = None
        self._kpis: dict = {"reserve": None, "spot": None, "jkm": None}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(0)

        # 헤더
        header = QHBoxLayout(); header.setSpacing(12); header.setContentsMargins(0, 0, 0, 12)
        self._icon = LeeIconTile(
            icon=QIcon(":/img/brief.svg"),
            color=_C_AI, size=40, radius=12,
        )
        header.addWidget(self._icon, 0, Qt.AlignTop)

        title_box = QVBoxLayout(); title_box.setSpacing(2); title_box.setContentsMargins(0, 0, 0, 0)
        self._title_lbl = QLabel(tr("AI 朝のブリーフィング"))
        self._title_lbl.setObjectName("briefCardTitle")
        self._sub_lbl = QLabel(tr("未生成"))
        self._sub_lbl.setObjectName("briefCardSub")
        title_box.addWidget(self._title_lbl)
        title_box.addWidget(self._sub_lbl)
        header.addLayout(title_box, 1)

        self._pill = LeePill("NEW", variant="accent")
        header.addWidget(self._pill, 0, Qt.AlignTop)
        self._pill.setVisible(False)   # setVisible 은 반드시 layout 추가 후 (top-level window 깜빡임 방지)

        layout.addLayout(header)

        # 본문 (markdown 렌더)
        self._body = QTextEdit()
        self._body.setObjectName("briefCardBody")
        self._body.setReadOnly(True)
        self._body.setFrameShape(QFrame.NoFrame)
        self._body.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._body.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._body.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self._body.setMinimumHeight(110)
        self._body.setMaximumHeight(140)
        layout.addWidget(self._body, 1)

        # KPI strip — 3 columns
        self._kpi_wrap = QFrame()
        self._kpi_wrap.setObjectName("briefCardKpiWrap")
        kpi_lay = QHBoxLayout(self._kpi_wrap)
        kpi_lay.setContentsMargins(0, 12, 0, 0); kpi_lay.setSpacing(6)
        self._kpi_widgets: dict[str, _BriefKpiCol] = {}
        for key, label, color in [
            ("reserve", tr("予備率"),     _C_BAD),
            ("spot",    tr("スポット平均"), _C_SPOT),
            ("jkm",     tr("JKM"),       _C_JKM),
        ]:
            col = _BriefKpiCol(label, color)
            kpi_lay.addWidget(col, 1)
            self._kpi_widgets[key] = col
        layout.addWidget(self._kpi_wrap)

        self._apply_local_qss()
        self.set_briefing(None)

    # ── 외부 API ─────────────────────────────────────────────
    def set_briefing(self, b: Optional[dict]) -> None:
        """daily 브리핑 최신본을 카드에 표시."""
        self._latest = b
        if not b:
            self._sub_lbl.setText(tr("未生成 — 詳細から生成してください"))
            self._body.setMarkdown(tr(
                "AI ブリーフィングはまだ生成されていません。\n\n"
                "詳細画面の「ブリーフィング生成」から作成できます。"
            ))
            self._pill.setVisible(False)
            return

        self._sub_lbl.setText(
            tr("{0} 自動生成").format(b.get("created_at", "")[:16])
        )
        # NEW pill: 24 시간 내 생성된 경우
        try:
            dt = datetime.strptime(b.get("created_at", "")[:19], "%Y-%m-%d %H:%M:%S")
            is_new = (datetime.now() - dt).total_seconds() < 24 * 3600
        except Exception:
            is_new = False
        self._pill.setVisible(is_new)

        # 본문 — 마크다운 렌더 (헤더 # 한 줄 + 본문 처음 ~200 자)
        content = b.get("content", "") or ""
        self._body.setMarkdown(self._excerpt(content))

    def set_kpis(self, *, reserve: Optional[float] = None,
                 spot: Optional[float] = None,
                 jkm: Optional[float] = None) -> None:
        """대시보드가 시장 데이터 받을 때마다 호출. None 은 변경 없음."""
        if reserve is not None:
            self._kpis["reserve"] = reserve
            self._kpi_widgets["reserve"].set_value(f"{reserve:.1f}", unit="%")
        if spot is not None:
            self._kpis["spot"] = spot
            self._kpi_widgets["spot"].set_value(f"{spot:.2f}")
        if jkm is not None:
            self._kpis["jkm"] = jkm
            self._kpi_widgets["jkm"].set_value(f"{jkm:.2f}")

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        for col in self._kpi_widgets.values():
            col.set_theme(is_dark)
        self._apply_local_qss()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    @staticmethod
    def _excerpt(md: str, max_chars: int = 220) -> str:
        """마크다운 본문 첫 헤더 1 + 첫 문단 일부 발췌."""
        lines = md.split("\n")
        out: list[str] = []
        char_count = 0
        for ln in lines:
            stripped = ln.strip()
            if not stripped:
                if out:
                    out.append("")
                continue
            out.append(ln)
            char_count += len(stripped)
            if char_count >= max_chars:
                break
        return "\n".join(out).rstrip()

    def _apply_local_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        border_subtle = "rgba(255,255,255,0.06)" if is_dark else "rgba(11,18,32,0.06)"
        self.setStyleSheet(f"""
            QLabel#briefCardTitle {{
                font-size: 13px; font-weight: 600;
                color: {fg_secondary}; background: transparent;
            }}
            QLabel#briefCardSub {{
                font-size: 11px; color: {fg_tertiary};
                background: transparent;
            }}
            QTextEdit#briefCardBody {{
                background: transparent;
                color: {fg_primary};
                border: none;
                font-size: 13px; line-height: 1.65;
                selection-background-color: rgba(88,86,214,0.30);
            }}
            QFrame#briefCardKpiWrap {{
                background: transparent;
                border-top: 1px solid {border_subtle};
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# A1. _BriefKpiCol — BriefCard 하단 KPI 컬럼
# ──────────────────────────────────────────────────────────────────────
class _BriefKpiCol(QWidget):
    """단일 KPI: 큰 컬러 값 + 라벨."""

    def __init__(self, label: str, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self._is_dark = True

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 4, 0, 0); v.setSpacing(2)
        v.setAlignment(Qt.AlignCenter)

        self._val_lbl = QLabel("--")
        self._val_lbl.setObjectName("briefKpiVal")
        self._val_lbl.setAlignment(Qt.AlignCenter)
        v.addWidget(self._val_lbl)

        self._label_lbl = QLabel(label)
        self._label_lbl.setObjectName("briefKpiLabel")
        self._label_lbl.setAlignment(Qt.AlignCenter)
        v.addWidget(self._label_lbl)

        self._apply_qss()

    def set_value(self, text: str, *, unit: str = "") -> None:
        self._val_lbl.setText(f"{text}{unit}" if unit else text)

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    def _apply_qss(self) -> None:
        fg_tertiary = "#6B7280" if self._is_dark else "#8A93A6"
        self.setStyleSheet(f"""
            QLabel#briefKpiVal {{
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 18px; font-weight: 800;
                color: {self._color}; background: transparent;
                letter-spacing: -0.01em;
            }}
            QLabel#briefKpiLabel {{
                font-size: 10px;
                color: {fg_tertiary}; background: transparent;
            }}
        """)


# ──────────────────────────────────────────────────────────────────────
# B. BriefingWidget — 디테일 페이지 (생성 + 履歴)
# ──────────────────────────────────────────────────────────────────────
class BriefingWidget(BaseWidget):
    """AI ブリーフィング 디테일 — DetailHeader + 생성 컨트롤 + 履歴 + 内容."""

    # 새 브리핑 생성 시 카드/대시보드 동기화 트리거
    briefing_generated = Signal(str)   # period

    def __init__(self, parent=None):
        super().__init__(parent)
        _init_db()
        self._is_generating = False
        self._worker: Optional[BriefingWorker] = None
        self._current_period = "daily"
        self._current_lang   = "ja"
        self._selected_id: Optional[int] = None

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self._rebuild_list)

        self._build_ui()
        self._rebuild_list()

    # ──────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setObjectName("briefPageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer.addWidget(scroll, 1)

        content = QWidget()
        content.setObjectName("briefPageContent")
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(28, 22, 28, 22); root.setSpacing(14)

        # 1) DetailHeader
        self._header = LeeDetailHeader(
            title=tr("AI ブリーフィング"),
            subtitle=tr("過去・現在・将来を AI が分析"),
            accent=_C_AI,
            icon_qicon=QIcon(":/img/brief.svg"),
            badge=tr("AI 生成"),
            show_export=False,
        )
        self._header.back_clicked.connect(lambda: bus.page_requested.emit(0))
        root.addWidget(self._header)

        # 2) 생성 컨트롤 카드
        root.addWidget(self._build_control_card())

        # 3) 분할 패널 (Splitter)
        root.addWidget(self._build_splitter(), 1)

        self._apply_page_qss()
        self._refresh_period_btn_labels()
        self._refresh_weights()

    def _build_control_card(self) -> QFrame:
        card = QFrame(); card.setObjectName("briefControlCard")
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 12, 16, 12); v.setSpacing(8)

        # Row 1: period segment + lang + generate
        row1 = QHBoxLayout(); row1.setSpacing(10)
        # LeeSegment 사용 — 4 옵션 (今日/今週/今月/来月)
        self._segment = LeeSegment(
            [(p, labels["ja"]) for p, labels in _PERIODS],
            value="daily",
            accent=_C_AI,
        )
        self._segment.value_changed.connect(self._on_period_changed)
        row1.addWidget(self._segment)

        row1.addStretch()

        lang_lbl = QLabel(tr("言語:"))
        lang_lbl.setObjectName("briefCtrlLabel")
        row1.addWidget(lang_lbl)

        self._lang_combo = QComboBox()
        self._lang_combo.setObjectName("briefLangCombo")
        self._lang_combo.setFixedHeight(30)
        self._lang_combo.setMinimumWidth(105)
        for code, name in _LANG_OPTIONS:
            self._lang_combo.addItem(name, code)
        self._lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        row1.addWidget(self._lang_combo)

        self._gen_btn = QPushButton(_GEN_LABEL["ja"])
        self._gen_btn.setObjectName("briefGenBtn")
        self._gen_btn.setFixedHeight(30)
        self._gen_btn.setMinimumWidth(160)
        self._gen_btn.setCursor(Qt.PointingHandCursor)
        self._gen_btn.clicked.connect(self._on_generate)
        row1.addWidget(self._gen_btn)
        v.addLayout(row1)

        # Row 2: weight + status
        row2 = QHBoxLayout(); row2.setSpacing(10)
        self._weight_lbl = QLabel("")
        self._weight_lbl.setObjectName("briefWeightLbl")
        row2.addWidget(self._weight_lbl)
        row2.addStretch()
        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("briefStatusLbl")
        row2.addWidget(self._status_lbl)
        v.addLayout(row2)

        self._control_card = card
        self._apply_control_qss()
        return card

    def _build_splitter(self) -> QSplitter:
        sp = QSplitter(Qt.Horizontal)
        sp.setObjectName("briefSplitter")
        sp.setHandleWidth(1)

        # 왼쪽 — 履歴
        left = QFrame(); left.setObjectName("briefLeftPane")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(12, 12, 12, 12); ll.setSpacing(8)

        hist_title = QLabel(tr("履歴"))
        hist_title.setObjectName("briefHistTitle")
        ll.addWidget(hist_title)

        self._search_edit = QLineEdit()
        self._search_edit.setObjectName("briefSearch")
        self._search_edit.setPlaceholderText("🔍  " + tr("検索..."))
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setFixedHeight(32)
        self._search_edit.textChanged.connect(lambda _: self._search_timer.start())
        ll.addWidget(self._search_edit)

        # 期間 / 言語 mini select
        filter_row = QHBoxLayout(); filter_row.setSpacing(6)
        self._filter_period = QComboBox()
        self._filter_period.setObjectName("briefMiniSel")
        self._filter_period.setFixedHeight(28)
        self._filter_period.addItem(tr("期間: 全て"), "")
        for k, labels in _PERIODS:
            self._filter_period.addItem(labels["pja"], k)
        self._filter_period.currentIndexChanged.connect(self._rebuild_list)
        filter_row.addWidget(self._filter_period, 1)

        self._filter_lang = QComboBox()
        self._filter_lang.setObjectName("briefMiniSel")
        self._filter_lang.setFixedHeight(28)
        self._filter_lang.addItem(tr("言語: 全て"), "")
        for code, name in _LANG_OPTIONS:
            self._filter_lang.addItem(name, code)
        self._filter_lang.currentIndexChanged.connect(self._rebuild_list)
        filter_row.addWidget(self._filter_lang, 1)
        ll.addLayout(filter_row)

        self._hist_list = QListWidget()
        self._hist_list.setObjectName("briefHistList")
        self._hist_list.currentItemChanged.connect(self._on_history_selected)
        ll.addWidget(self._hist_list, 1)

        # 풋터
        foot = QHBoxLayout(); foot.setContentsMargins(0, 0, 0, 0); foot.setSpacing(6)
        self._count_lbl = QLabel("0 件")
        self._count_lbl.setObjectName("briefCountLbl")
        foot.addWidget(self._count_lbl)
        foot.addStretch()
        self._del_btn = QPushButton(tr("削除"))
        self._del_btn.setObjectName("briefDelBtn")
        self._del_btn.setFixedHeight(28)
        self._del_btn.setCursor(Qt.PointingHandCursor)
        self._del_btn.setEnabled(False)
        self._del_btn.clicked.connect(self._on_delete)
        foot.addWidget(self._del_btn)
        ll.addLayout(foot)

        sp.addWidget(left)

        # 오른쪽 — 内容
        right = QFrame(); right.setObjectName("briefRightPane")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(20, 20, 20, 20); rl.setSpacing(10)

        # 메타 헤더 — period pill + lang + 시각
        meta_row = QHBoxLayout(); meta_row.setSpacing(8)
        self._meta_period = QLabel("")
        self._meta_period.setObjectName("briefMetaPeriod")
        self._meta_lang = QLabel("")
        self._meta_lang.setObjectName("briefMetaLang")
        self._meta_time = QLabel("")
        self._meta_time.setObjectName("briefMetaTime")
        meta_row.addWidget(self._meta_period)
        meta_row.addWidget(self._meta_lang)
        meta_row.addStretch()
        meta_row.addWidget(self._meta_time)
        rl.addLayout(meta_row)

        # 본문
        self._content_view = QTextEdit()
        self._content_view.setObjectName("briefContentView")
        self._content_view.setReadOnly(True)
        self._content_view.setFrameShape(QFrame.NoFrame)
        self._content_view.setPlaceholderText(_PLACEHOLDER["ja"])
        self._content_view.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        rl.addWidget(self._content_view, 1)

        sp.addWidget(right)
        sp.setStretchFactor(0, 0)
        sp.setStretchFactor(1, 1)
        sp.setSizes([260, 760])

        # 첫 fetch 동안 본문 영역에 shimmer skeleton
        from app.ui.components.skeleton import install_skeleton_overlay
        self._content_skel = install_skeleton_overlay(self._content_view)

        return sp

    # ──────────────────────────────────────────────────────────
    # 스타일
    # ──────────────────────────────────────────────────────────
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
        sel_bg        = _C_AI
        self.setStyleSheet(f"""
            BriefingWidget {{ background: {bg_app}; }}
            QScrollArea#briefPageScroll {{ background: {bg_app}; border: none; }}
            QWidget#briefPageContent {{ background: {bg_app}; }}
            QFrame#briefLeftPane, QFrame#briefRightPane {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 14px;
            }}
            QSplitter#briefSplitter::handle {{ background: transparent; }}
            QLabel#briefHistTitle {{
                font-size: 13px; font-weight: 800;
                color: {fg_primary}; background: transparent;
            }}
            QLabel#briefCountLbl {{
                font-size: 10px; color: {fg_tertiary};
                background: transparent;
            }}
            QLineEdit#briefSearch {{
                background: {bg_surface_2};
                color: {fg_primary};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 0 10px;
                font-size: 12px;
            }}
            QLineEdit#briefSearch:focus {{ border-color: {_C_AI}; }}
            QComboBox#briefMiniSel {{
                background: {bg_surface_2};
                color: {fg_primary};
                border: 1px solid {border_subtle};
                border-radius: 6px;
                padding: 0 8px;
                font-size: 11px;
            }}
            QComboBox#briefMiniSel:focus {{ border-color: {_C_AI}; }}
            QListWidget#briefHistList {{
                background: transparent;
                border: none;
                outline: 0;
                font-size: 11px;
            }}
            QListWidget#briefHistList::item {{
                background: transparent;
                color: {fg_primary};
                border-radius: 8px;
                padding: 8px 10px;
                margin: 2px 0;
            }}
            QListWidget#briefHistList::item:hover {{
                background: rgba(88,86,214,0.08);
            }}
            QListWidget#briefHistList::item:selected {{
                background: {sel_bg};
                color: white;
            }}
            QPushButton#briefDelBtn {{
                background: rgba(255,69,58,0.12);
                color: #FF453A;
                border: 1px solid rgba(255,69,58,0.30);
                border-radius: 6px;
                padding: 0 12px;
                font-size: 11px; font-weight: 700;
            }}
            QPushButton#briefDelBtn:hover {{
                background: rgba(255,69,58,0.22);
            }}
            QPushButton#briefDelBtn:disabled {{
                background: {bg_surface_2};
                color: {fg_tertiary};
                border-color: {border_subtle};
            }}
            QLabel#briefMetaPeriod {{
                background: {_C_AI_SOFT};
                color: {_C_AI};
                border-radius: 999px;
                padding: 3px 12px;
                font-size: 10px; font-weight: 800;
            }}
            QLabel#briefMetaLang {{
                color: {fg_tertiary};
                background: transparent;
                font-size: 10px; font-weight: 600;
            }}
            QLabel#briefMetaTime {{
                color: {fg_tertiary};
                background: transparent;
                font-size: 10px;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QTextEdit#briefContentView {{
                background: transparent;
                color: {fg_primary};
                border: none;
                font-size: 13px;
                line-height: 1.7;
                selection-background-color: rgba(88,86,214,0.30);
            }}
        """)

    def _apply_control_qss(self) -> None:
        is_dark = self.is_dark
        fg_primary    = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary  = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary   = "#6B7280" if is_dark else "#8A93A6"
        bg_surface    = "#14161C" if is_dark else "#FFFFFF"
        bg_surface_2  = "#1B1E26" if is_dark else "#F0F2F5"
        border_subtle = "rgba(255,255,255,0.06)" if is_dark else "rgba(11,18,32,0.06)"
        border        = "rgba(255,255,255,0.10)" if is_dark else "rgba(11,18,32,0.10)"
        self._control_card.setStyleSheet(f"""
            QFrame#briefControlCard {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 12px;
            }}
            QLabel#briefCtrlLabel {{
                font-size: 11px; color: {fg_tertiary};
                background: transparent;
            }}
            QComboBox#briefLangCombo {{
                background: {bg_surface_2};
                color: {fg_primary};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 0 10px;
                font-size: 12px;
            }}
            QComboBox#briefLangCombo:focus {{ border-color: {_C_AI}; }}
            QPushButton#briefGenBtn {{
                background: {_C_AI};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 0 16px;
                font-size: 12px; font-weight: 800;
            }}
            QPushButton#briefGenBtn:hover {{ background: #6361DC; }}
            QPushButton#briefGenBtn:disabled {{
                background: {bg_surface_2};
                color: {fg_tertiary};
            }}
            QLabel#briefWeightLbl {{
                font-size: 11px; color: {fg_secondary};
                background: transparent;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QLabel#briefStatusLbl {{
                font-size: 11px; color: {fg_tertiary};
                background: transparent;
            }}
        """)

    # ──────────────────────────────────────────────────────────
    # BaseWidget hooks
    # ──────────────────────────────────────────────────────────
    def apply_theme_custom(self) -> None:
        d = self.is_dark
        self._header.set_theme(d)
        self._segment.set_theme(d)
        self._apply_page_qss()
        self._apply_control_qss()

    def apply_settings_custom(self) -> None:
        pass

    # ──────────────────────────────────────────────────────────
    # 컨트롤
    # ──────────────────────────────────────────────────────────
    def _on_period_changed(self, key: str) -> None:
        self._current_period = key
        self._refresh_weights()

    def _on_lang_changed(self, idx: int) -> None:
        self._current_lang = self._lang_combo.itemData(idx)
        self._refresh_period_btn_labels()
        self._refresh_weights()
        self._gen_btn.setText(_GEN_LABEL.get(self._current_lang, _GEN_LABEL["ja"]))
        self._content_view.setPlaceholderText(
            _PLACEHOLDER.get(self._current_lang, _PLACEHOLDER["ja"])
        )

    def _refresh_period_btn_labels(self) -> None:
        # LeeSegment 의 라벨 갱신 — i18n 별 디스플레이 변경
        # LeeSegment 인터페이스가 단순 (생성자에서만 라벨 입력) 이라 직접 재구성 대신
        # 현재 값 유지하고 추후 풀 재빌드. (간단히 ja 라벨 고정)
        pass

    def _refresh_weights(self) -> None:
        now = datetime.now()
        p, c, f = calc_weights(self._current_period, now)
        t = _WEIGHT_LABEL.get(self._current_lang, _WEIGHT_LABEL["ja"])
        self._weight_lbl.setText(f"{t[0]}: {p}%  |  {t[1]}: {c}%  |  {t[2]}: {f}%")

    # ──────────────────────────────────────────────────────────
    # 생성
    # ──────────────────────────────────────────────────────────
    def _on_generate(self) -> None:
        if self._is_generating:
            return
        self._is_generating = True
        self._gen_btn.setEnabled(False)
        self._gen_btn.setText(_RUNNING_LABEL.get(self._current_lang, _RUNNING_LABEL["ja"]))
        self._set_status(tr("⏳ 準備中..."), busy=True)
        self._content_view.clear()
        self._content_view.setPlaceholderText("")

        worker = BriefingWorker(self._current_period, self._current_lang)
        worker.result.connect(self._on_result)
        worker.error.connect(self._on_error)
        worker.status.connect(lambda m: self._set_status(m, busy=True))
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()
        self.track_worker(worker)

    def _on_result(self, text: str) -> None:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            _save_to_db(self._current_period, self._current_lang, text, created_at)
        except sqlite3.Error as e:
            logger.error(f"briefing save error: {e}")
        if getattr(self, "_content_skel", None) is not None:
            self._content_skel.stop(); self._content_skel.deleteLater(); self._content_skel = None
        self._content_view.setMarkdown(text)
        self._set_status(tr("✅ 生成完了 {0}").format(created_at[:16]))
        self._rebuild_list(select_latest=True)
        self.briefing_generated.emit(self._current_period)
        # 글로벌 bus — 대시보드 카드 미리보기 자동 갱신 트리거
        bus.briefing_generated.emit(self._current_period)

    def _on_error(self, msg: str) -> None:
        self._content_view.setPlainText(tr("❌ エラー: {0}").format(msg))
        self._set_status(tr("⚠ エラー発生"))
        logger.error(f"briefing error: {msg}")

    def _on_worker_finished(self) -> None:
        self._is_generating = False
        self._gen_btn.setEnabled(True)
        self._gen_btn.setText(_GEN_LABEL.get(self._current_lang, _GEN_LABEL["ja"]))
        w = self._worker; self._worker = None
        if w is not None:
            try: w.deleteLater()
            except RuntimeError: pass

    # ──────────────────────────────────────────────────────────
    # 履歴 패널
    # ──────────────────────────────────────────────────────────
    def _rebuild_list(self, select_latest: bool = False) -> None:
        period_f = self._filter_period.currentData() or ""
        lang_f   = self._filter_lang.currentData()   or ""
        text_f   = self._search_edit.text().strip()

        rows = _load_list(period_f, lang_f, text_f)

        self._hist_list.blockSignals(True)
        self._hist_list.clear()
        period_name_map = {p: labels["pja"] for p, labels in _PERIODS}
        lang_name_map = dict(_LANG_OPTIONS)

        for row_id, period, lang, created_at in rows:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, row_id)
            period_name = period_name_map.get(period, period)
            lang_name = lang_name_map.get(lang, lang)
            item.setText(f"{created_at[:16]}\n{period_name} · {lang_name}")
            item.setSizeHint(QSize(0, 50))
            self._hist_list.addItem(item)
        self._hist_list.blockSignals(False)
        self._count_lbl.setText(tr("{0} 件").format(len(rows)))

        if select_latest and self._hist_list.count() > 0:
            self._hist_list.setCurrentRow(0)
        elif self._selected_id is not None:
            for i in range(self._hist_list.count()):
                if self._hist_list.item(i).data(Qt.UserRole) == self._selected_id:
                    self._hist_list.setCurrentRow(i)
                    break

    def _on_history_selected(self, current: QListWidgetItem, _prev) -> None:
        if current is None:
            self._selected_id = None
            self._del_btn.setEnabled(False)
            self._meta_period.setText(""); self._meta_lang.setText(""); self._meta_time.setText("")
            return
        row_id = current.data(Qt.UserRole)
        self._selected_id = row_id
        self._del_btn.setEnabled(True)
        # 메타 + 본문
        try:
            with sqlite3.connect(str(_briefing_db())) as conn:
                meta = conn.execute(
                    "SELECT period, lang, created_at, content FROM briefings WHERE id=?",
                    (row_id,),
                ).fetchone()
        except sqlite3.Error:
            meta = None
        if meta:
            period, lang, created_at, content = meta
            period_name_map = {p: labels["pja"] for p, labels in _PERIODS}
            lang_name_map = dict(_LANG_OPTIONS)
            self._meta_period.setText(period_name_map.get(period, period))
            self._meta_lang.setText(lang_name_map.get(lang, lang))
            self._meta_time.setText(created_at[:19])
            if getattr(self, "_content_skel", None) is not None:
                self._content_skel.stop(); self._content_skel.deleteLater(); self._content_skel = None
            self._content_view.setMarkdown(content)

    def _on_delete(self) -> None:
        if self._selected_id is None:
            return
        item = self._hist_list.currentItem()
        label = item.text().split("\n")[0] if item else ""
        if not LeeDialog.confirm(
            tr("削除の確認"),
            tr("このブリーフィングを削除しますか?\n{0}").format(label),
            ok_text=tr("削除"),
            destructive=True,
            parent=self,
        ):
            return
        _delete_from_db(self._selected_id)
        self._selected_id = None
        self._del_btn.setEnabled(False)
        self._content_view.clear()
        self._content_view.setPlaceholderText(_PLACEHOLDER.get(self._current_lang, _PLACEHOLDER["ja"]))
        self._meta_period.setText(""); self._meta_lang.setText(""); self._meta_time.setText("")
        self._rebuild_list()

    # ──────────────────────────────────────────────────────────
    # 상태
    # ──────────────────────────────────────────────────────────
    def _set_status(self, msg: str, *, busy: bool = False) -> None:
        self._status_lbl.setText(msg)
        is_dark = self.is_dark
        if busy:
            color = _C_AI
        elif msg.startswith("✅"):
            color = _C_OK
        elif msg.startswith("⚠") or msg.startswith("❌"):
            color = _C_BAD
        else:
            color = "#A8B0BD" if is_dark else "#4A5567"
        self._status_lbl.setStyleSheet(
            f"QLabel#briefStatusLbl {{ font-size: 11px; color: {color}; "
            f"background: transparent; font-weight: 600; }}"
        )


__all__ = [
    "BriefCard",
    "BriefingWidget",
    "latest_briefing",
]
