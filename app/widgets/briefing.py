"""
AI ブリーフィングウィジェット
- 期間 (今日/今週/今月/来月) × 言語 (日/韓/英/中) でブリーフィングを生成
- 生成履歴を SQLite に保存・閲覧・削除
- 週次 / 月次 / 来月はデータカバレッジを自動チェックし JKM を必要に応じて自動取得
"""
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QComboBox, QLabel, QTextEdit, QFrame, QSplitter,
    QListWidget, QListWidgetItem, QLineEdit, QApplication,
)
from app.api.briefing_api import BriefingWorker, calc_weights, PERIOD_LABELS
from app.ui.theme import ThemePalette, UIColors

logger = logging.getLogger(__name__)

# ── 定数 ──────────────────────────────────────────────────────────────────────

_PERIODS = [
    ("daily",      {"ja": "今日",  "ko": "오늘",    "en": "Today",      "zh": "今天"}),
    ("weekly",     {"ja": "今週",  "ko": "이번 주", "en": "This Week",  "zh": "本周"}),
    ("monthly",    {"ja": "今月",  "ko": "이번 달", "en": "This Month", "zh": "本月"}),
    ("next_month", {"ja": "来月",  "ko": "다음 달", "en": "Next Month", "zh": "下月"}),
]

_LANG_OPTIONS = [
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("en", "English"),
    ("zh", "中文"),
]

_PERIOD_LABEL_JA = {
    "daily": "デイリー", "weekly": "週間", "monthly": "今月", "next_month": "来月",
}

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


# ── 履歴 DB ────────────────────────────────────────────────────────────────────

def _briefing_db() -> Path:
    from app.core.config import APP_DIR
    return APP_DIR / "briefings.db"


def _init_db():
    db = _briefing_db()
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


def _save_to_db(period: str, lang: str, content: str, created_at: str) -> int:
    with sqlite3.connect(str(_briefing_db())) as conn:
        cur = conn.execute(
            "INSERT INTO briefings (period, lang, content, created_at) VALUES (?,?,?,?)",
            (period, lang, content, created_at),
        )
        return cur.lastrowid


def _load_list(period_f: str = "", lang_f: str = "", text_f: str = "") -> list[tuple]:
    """(id, period, lang, created_at) の一覧を新しい順で返す。"""
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
    with sqlite3.connect(str(db)) as conn:
        return conn.execute(
            f"SELECT id, period, lang, created_at FROM briefings {where} "
            "ORDER BY created_at DESC LIMIT 300",
            params,
        ).fetchall()


def _load_content(row_id: int) -> str:
    db = _briefing_db()
    if not db.exists():
        return ""
    with sqlite3.connect(str(db)) as conn:
        row = conn.execute(
            "SELECT content FROM briefings WHERE id = ?", (row_id,)
        ).fetchone()
    return row[0] if row else ""


def _delete_from_db(row_id: int):
    db = _briefing_db()
    if db.exists():
        with sqlite3.connect(str(db)) as conn:
            conn.execute("DELETE FROM briefings WHERE id = ?", (row_id,))


# ── メインウィジェット ─────────────────────────────────────────────────────────

class BriefingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark        = True
        self._is_generating  = False   # C++ 削除済みワーカー参照を避けるためフラグ管理
        self._worker: BriefingWorker | None = None
        self._current_period = "daily"
        self._current_lang   = "ja"
        self._selected_id: int | None = None

        _init_db()
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._rebuild_list)

        self._setup_ui()
        self._rebuild_list()

    # ── UI 構築 ────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── ヘッダーフレーム (生成コントロール) ──────────────────────────────
        self._header = QFrame()
        self._header.setObjectName("briefHeader")
        hlay = QVBoxLayout(self._header)
        hlay.setContentsMargins(14, 10, 14, 8)
        hlay.setSpacing(6)

        # 行1: 期間ボタン + 言語 + 生成
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self._period_btns: list[tuple[str, QPushButton]] = []
        for period_key, labels in _PERIODS:
            btn = QPushButton(labels["ja"])
            btn.setCheckable(True)
            btn.setObjectName("briefPeriodBtn")
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _, p=period_key: self._on_period_clicked(p))
            top_row.addWidget(btn)
            self._period_btns.append((period_key, btn))

        top_row.addStretch()

        top_row.addWidget(QLabel("言語:"))

        self._lang_combo = QComboBox()
        self._lang_combo.setObjectName("briefLangCombo")
        self._lang_combo.setFixedHeight(30)
        self._lang_combo.setMinimumWidth(85)
        for code, name in _LANG_OPTIONS:
            self._lang_combo.addItem(name, code)
        self._lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        top_row.addWidget(self._lang_combo)

        self._gen_btn = QPushButton(_GEN_LABEL["ja"])
        self._gen_btn.setObjectName("briefGenBtn")
        self._gen_btn.setFixedHeight(30)
        self._gen_btn.setMinimumWidth(130)
        self._gen_btn.clicked.connect(self._on_generate)
        top_row.addWidget(self._gen_btn)

        hlay.addLayout(top_row)

        # 行2: 重み表示 + ステータス
        info_row = QHBoxLayout()
        self._weight_lbl = QLabel()
        self._weight_lbl.setObjectName("briefWeightLabel")
        info_row.addWidget(self._weight_lbl)
        info_row.addStretch()
        self._status_lbl = QLabel()
        self._status_lbl.setObjectName("briefStatusLabel")
        info_row.addWidget(self._status_lbl)
        hlay.addLayout(info_row)

        root.addWidget(self._header)

        # ── 区切り線 ──────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("briefTopSep")
        root.addWidget(sep)

        # ── スプリッター (左: 履歴, 右: 内容) ────────────────────────────────
        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setHandleWidth(1)

        # 左パネル ─────────────────────────────────────────────────────────────
        left = QWidget()
        left.setObjectName("briefLeftPanel")
        left.setMinimumWidth(160)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 10, 6, 10)
        ll.setSpacing(6)

        hist_title = QLabel("履歴")
        hist_title.setObjectName("briefHistTitle")
        ll.addWidget(hist_title)

        self._search_edit = QLineEdit()
        self._search_edit.setObjectName("briefSearch")
        self._search_edit.setPlaceholderText("🔍  検索...")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setFixedHeight(28)
        self._search_edit.textChanged.connect(lambda _: self._search_timer.start())
        ll.addWidget(self._search_edit)

        # フィルター (期間 / 言語)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(4)
        self._filter_period = QComboBox()
        self._filter_period.setObjectName("briefFilter")
        self._filter_period.setFixedHeight(26)
        self._filter_period.addItem("期間: 全て", "")
        for k, labels in _PERIODS:
            self._filter_period.addItem(labels["ja"], k)
        self._filter_period.currentIndexChanged.connect(self._rebuild_list)
        filter_row.addWidget(self._filter_period, 1)

        self._filter_lang = QComboBox()
        self._filter_lang.setObjectName("briefFilter")
        self._filter_lang.setFixedHeight(26)
        self._filter_lang.addItem("言語: 全て", "")
        for code, name in _LANG_OPTIONS:
            self._filter_lang.addItem(name, code)
        self._filter_lang.currentIndexChanged.connect(self._rebuild_list)
        filter_row.addWidget(self._filter_lang, 1)
        ll.addLayout(filter_row)

        # 履歴リスト
        self._hist_list = QListWidget()
        self._hist_list.setObjectName("briefHistList")
        self._hist_list.currentItemChanged.connect(self._on_history_selected)
        ll.addWidget(self._hist_list, 1)

        # フッター (件数 + 削除)
        foot_row = QHBoxLayout()
        self._count_lbl = QLabel()
        self._count_lbl.setObjectName("briefCountLabel")
        foot_row.addWidget(self._count_lbl)
        foot_row.addStretch()
        self._del_btn = QPushButton("削除")
        self._del_btn.setObjectName("briefDelBtn")
        self._del_btn.setFixedHeight(26)
        self._del_btn.setEnabled(False)
        self._del_btn.clicked.connect(self._on_delete)
        foot_row.addWidget(self._del_btn)
        ll.addLayout(foot_row)

        self._splitter.addWidget(left)

        # 右パネル ─────────────────────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 10, 10, 10)
        rl.setSpacing(0)

        self._text_area = QTextEdit()
        self._text_area.setReadOnly(True)
        self._text_area.setObjectName("briefTextArea")
        self._text_area.setFont(QFont("Meiryo UI", 10))
        self._text_area.setPlaceholderText(_PLACEHOLDER["ja"])
        rl.addWidget(self._text_area)

        self._splitter.addWidget(right)
        self._splitter.setSizes([200, 600])

        root.addWidget(self._splitter, 1)

        self._select_period("daily")
        self._refresh_weights()

    # ── 生成コントロール ──────────────────────────────────────────────────────

    def _on_period_clicked(self, period: str):
        self._select_period(period)
        self._refresh_weights()

    def _on_lang_changed(self, idx: int):
        self._current_lang = self._lang_combo.itemData(idx)
        self._refresh_period_btn_labels()
        self._refresh_weights()
        self._gen_btn.setText(_GEN_LABEL.get(self._current_lang, _GEN_LABEL["ja"]))
        self._text_area.setPlaceholderText(
            _PLACEHOLDER.get(self._current_lang, _PLACEHOLDER["ja"])
        )

    def _select_period(self, period: str):
        self._current_period = period
        for p, btn in self._period_btns:
            btn.setChecked(p == period)

    def _refresh_weights(self):
        now = datetime.now()
        p, c, f = calc_weights(self._current_period, now)
        t = _WEIGHT_LABEL.get(self._current_lang, _WEIGHT_LABEL["ja"])
        self._weight_lbl.setText(f"{t[0]}: {p}%  |  {t[1]}: {c}%  |  {t[2]}: {f}%")

    def _refresh_period_btn_labels(self):
        lang = self._current_lang
        for (_, labels), (_, btn) in zip(_PERIODS, self._period_btns):
            btn.setText(labels.get(lang, labels["ja"]))

    # ── 生成 ──────────────────────────────────────────────────────────────────

    def _on_generate(self):
        if self._is_generating:
            return
        self._is_generating = True
        self._gen_btn.setEnabled(False)
        self._gen_btn.setText(_RUNNING_LABEL.get(self._current_lang, _RUNNING_LABEL["ja"]))
        self._status_lbl.setText("⏳ 準備中...")
        self._text_area.clear()
        self._text_area.setPlaceholderText("")

        worker = BriefingWorker(self._current_period, self._current_lang)
        worker.result.connect(self._on_result)
        worker.error.connect(self._on_error)
        worker.status.connect(self._status_lbl.setText)
        worker.finished.connect(self._on_worker_finished)
        # deleteLater は finished より先に self._worker を None にしてから呼ぶ
        self._worker = worker
        worker.start()

    def _on_result(self, text: str):
        self._text_area.setMarkdown(text)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            _save_to_db(self._current_period, self._current_lang, text, created_at)
        except Exception as e:
            logger.error(f"briefing save error: {e}")
        self._status_lbl.setText(f"✅ 生成完了 {created_at[:16]}")
        self._rebuild_list(select_latest=True)

    def _on_error(self, msg: str):
        self._text_area.setPlainText(f"❌ エラー: {msg}")
        self._text_area.setPlaceholderText(_PLACEHOLDER.get(self._current_lang, _PLACEHOLDER["ja"]))
        self._status_lbl.setText("⚠ エラー発生")
        logger.error(f"briefing error: {msg}")

    def _on_worker_finished(self):
        """finished シグナルは必ず result/error の後で呼ばれる。"""
        self._is_generating = False
        self._gen_btn.setEnabled(True)
        self._gen_btn.setText(_GEN_LABEL.get(self._current_lang, _GEN_LABEL["ja"]))
        # C++ オブジェクトを安全に削除してから参照を解放
        w = self._worker
        self._worker = None
        if w is not None:
            try:
                w.deleteLater()
            except RuntimeError:
                pass

    # ── 履歴パネル ────────────────────────────────────────────────────────────

    def _rebuild_list(self, select_latest: bool = False):
        period_f = self._filter_period.currentData() or ""
        lang_f   = self._filter_lang.currentData()   or ""
        text_f   = self._search_edit.text().strip()

        rows = _load_list(period_f, lang_f, text_f)

        self._hist_list.blockSignals(True)
        self._hist_list.clear()

        for row_id, period, lang, created_at in rows:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, row_id)
            # 言語コードを表示名に変換
            lang_name = dict(_LANG_OPTIONS).get(lang, lang)
            period_name = _PERIOD_LABEL_JA.get(period, period)
            # 表示テキスト: 日時 + 種別/言語
            item.setText(f"{created_at[:16]}\n{period_name}  /  {lang_name}")
            item.setSizeHint(QSize(0, 44))
            self._hist_list.addItem(item)

        self._hist_list.blockSignals(False)
        self._count_lbl.setText(f"{len(rows)} 件")

        if select_latest and self._hist_list.count() > 0:
            self._hist_list.setCurrentRow(0)
        elif self._selected_id is not None:
            # 再描画後に以前の選択を復元
            for i in range(self._hist_list.count()):
                if self._hist_list.item(i).data(Qt.UserRole) == self._selected_id:
                    self._hist_list.setCurrentRow(i)
                    break

    def _on_history_selected(self, current: QListWidgetItem, _prev):
        if current is None:
            self._selected_id = None
            self._del_btn.setEnabled(False)
            return
        row_id = current.data(Qt.UserRole)
        self._selected_id = row_id
        self._del_btn.setEnabled(True)
        content = _load_content(row_id)
        if content:
            self._text_area.setMarkdown(content)

    def _on_delete(self):
        if self._selected_id is None:
            return
        item = self._hist_list.currentItem()
        label = item.text().split("\n")[0] if item else ""
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "削除の確認",
            f"このブリーフィングを削除しますか？\n{label}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            _delete_from_db(self._selected_id)
        except Exception as e:
            logger.error(f"briefing delete error: {e}")
        self._selected_id = None
        self._del_btn.setEnabled(False)
        self._text_area.clear()
        self._text_area.setPlaceholderText(_PLACEHOLDER.get(self._current_lang, _PLACEHOLDER["ja"]))
        self._rebuild_list()

    # ── テーマ ────────────────────────────────────────────────────────────────

    def set_theme(self, is_dark: bool):
        self._is_dark = is_dark
        self._apply_theme()

    def _apply_theme(self):
        d = self._is_dark
        bg      = ThemePalette.bg_primary(d)
        panel   = ThemePalette.bg_secondary(d)
        hover   = ThemePalette.bg_tertiary(d)
        fg      = UIColors.text_primary(d)
        accent  = UIColors.ACTION_BLUE_DARK if d else UIColors.ACTION_BLUE_LIGHT
        border  = UIColors.BORDER_DARK if d else UIColors.BORDER_LIGHT
        muted   = UIColors.TEXT_MUTED
        sel_bg  = accent
        del_bg  = "#6e2020"
        del_fg  = "#ffaaaa"

        self.setStyleSheet(f"""
            BriefingWidget {{
                background: {bg};
            }}
            QFrame#briefHeader {{
                background: {panel};
                border-bottom: 1px solid {border};
            }}
            QFrame#briefTopSep {{
                background: {border};
                max-height: 1px;
            }}
            QLabel {{
                color: {fg};
                font-size: 12px;
                background: transparent;
            }}
            QLabel#briefHistTitle {{
                font-weight: bold;
                font-size: 13px;
            }}
            QLabel#briefWeightLabel, QLabel#briefStatusLabel,
            QLabel#briefCountLabel {{
                color: {muted};
                font-size: 11px;
            }}
            QPushButton#briefPeriodBtn {{
                background: {hover};
                color: {fg};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 2px 12px;
                font-size: 12px;
            }}
            QPushButton#briefPeriodBtn:checked {{
                background: {accent};
                color: #ffffff;
                border: 1px solid {accent};
            }}
            QPushButton#briefPeriodBtn:hover:!checked {{
                background: {ThemePalette.bg_tertiary(d)};
            }}
            QPushButton#briefGenBtn {{
                background: {accent};
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 2px 16px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton#briefGenBtn:disabled {{
                background: {border};
                color: {muted};
            }}
            QPushButton#briefDelBtn {{
                background: {del_bg};
                color: {del_fg};
                border: 1px solid #8b2222;
                border-radius: 4px;
                font-size: 11px;
                padding: 2px 8px;
            }}
            QPushButton#briefDelBtn:disabled {{
                background: {hover};
                color: {muted};
                border-color: {border};
            }}
            QComboBox#briefLangCombo,
            QComboBox#briefFilter {{
                background: {panel};
                color: {fg};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 11px;
            }}
            QComboBox#briefLangCombo::drop-down,
            QComboBox#briefFilter::drop-down {{
                border: none;
            }}
            QLineEdit#briefSearch {{
                background: {panel};
                color: {fg};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 0 8px;
                font-size: 12px;
            }}
            QLineEdit#briefSearch:focus {{
                border-color: {accent};
            }}
            QWidget#briefLeftPanel {{
                background: {panel};
                border-right: 1px solid {border};
            }}
            QListWidget#briefHistList {{
                background: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 4px;
                outline: none;
                font-size: 12px;
            }}
            QListWidget#briefHistList::item {{
                border-radius: 3px;
                margin: 1px 2px;
                padding: 3px 6px;
            }}
            QListWidget#briefHistList::item:selected {{
                background: {sel_bg};
                color: #ffffff;
            }}
            QListWidget#briefHistList::item:hover:!selected {{
                background: {hover};
            }}
            QTextEdit#briefTextArea {{
                background: {panel};
                color: {fg};
                border: none;
                border-radius: 0px;
                padding: 14px;
                font-size: 13px;
                selection-background-color: {accent};
            }}
            QSplitter::handle {{
                background: {border};
            }}
        """)
