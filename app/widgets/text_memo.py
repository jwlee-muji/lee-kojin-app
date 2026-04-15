"""
テキストメモ管理ウィジェット
よく使うテキスト・プロンプトを登録し、クリップボードへ即コピーできる機能。
データは JSON ファイルに保存。
"""
import json
import logging
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QListWidget, QListWidgetItem,
    QSplitter, QWidget, QFrame, QSizePolicy, QApplication,
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QKeySequence, QShortcut
from app.ui.common import BaseWidget
from app.core.i18n import tr

logger = logging.getLogger(__name__)

_BTN_H = 30   # ボタン統一高さ


def _memo_file() -> Path:
    from app.core.config import APP_DIR
    return APP_DIR / "memos.json"


def _load_memos() -> list[dict]:
    f = _memo_file()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError) as e:
            logger.warning(f"メモファイルの読み込みに失敗しました。空リストで続行します: {e}")
    return []


def _save_memos(memos: list[dict]) -> None:
    _memo_file().write_text(
        json.dumps(memos, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class TextMemoWidget(BaseWidget):
    def __init__(self):
        super().__init__()
        self._memos: list[dict] = []
        self._selected_idx: int = -1
        self._dirty = False          # 未保存の変更フラグ
        self._rebuilding = False     # リスト再構築中フラグ (シグナル制御用)
        self._is_dark = True         # テーマフラグ
        self._build_ui()
        self._load_all()

    # ── UI 構築 ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── ヘッダー ────────────────────────────────────────────────────
        self._header_frame = QFrame()
        self._header_frame.setObjectName("memoHeader")
        hrow = QHBoxLayout(self._header_frame)
        hrow.setContentsMargins(16, 10, 16, 10)

        title_lbl = QLabel(tr("テキストメモ"))
        title_lbl.setStyleSheet("font-weight: bold; font-size: 15px;")

        self.status_lbl = QLabel()
        self.status_lbl.setStyleSheet("font-size: 12px; color: #888;")

        hrow.addWidget(title_lbl)
        hrow.addStretch()
        hrow.addWidget(self.status_lbl)
        root.addWidget(self._header_frame)

        # ── メインスプリッター ───────────────────────────────────────────
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(1)

        # ── 左パネル ────────────────────────────────────────────────────
        left = QWidget()
        left.setMinimumWidth(180)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 10, 8, 10)
        ll.setSpacing(8)

        # 検索
        self.edt_search = QLineEdit()
        self.edt_search.setPlaceholderText("🔍  " + tr("検索..."))
        self.edt_search.setClearButtonEnabled(True)
        self.edt_search.setFixedHeight(30)
        self.edt_search.setStyleSheet(
            "QLineEdit { border: 1px solid #3d3d3d; border-radius: 6px;"
            " padding: 0 8px; font-size: 12px; }"
            "QLineEdit:focus { border-color: #0078d4; }"
        )
        self.edt_search.textChanged.connect(self._filter_list)
        ll.addWidget(self.edt_search)

        # メモリスト
        self.memo_list = QListWidget()
        self.memo_list.setStyleSheet(
            "QListWidget { border: 1px solid #3d3d3d; border-radius: 6px;"
            " background: #1e1e1e; outline: 0; }"
            "QListWidget::item { border-radius: 4px; margin: 1px 3px; }"
            "QListWidget::item:selected { background: #094771; }"
            "QListWidget::item:hover:!selected { background: #2a2d2e; }"
        )
        self.memo_list.currentRowChanged.connect(self._on_select)
        ll.addWidget(self.memo_list, 1)

        # メモ数ラベル
        self.count_lbl = QLabel()
        self.count_lbl.setStyleSheet("color: #666; font-size: 10px; padding: 0 2px;")
        ll.addWidget(self.count_lbl)

        # 新規 / 削除 ボタン
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_new = QPushButton("＋ " + tr("新規追加"))
        self.btn_new.setObjectName("primaryActionBtn")
        self.btn_new.setFixedHeight(_BTN_H)
        self.btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new.clicked.connect(self._new_memo)

        self.btn_delete = QPushButton(tr("削除"))
        self.btn_delete.setFixedHeight(_BTN_H)
        self.btn_delete.setFixedWidth(60)
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setEnabled(False)
        self.btn_delete.setStyleSheet(
            f"QPushButton {{ background: #6e2020; color: #ffaaaa;"
            f" border: 1px solid #8b2222; border-radius: 4px; font-size: 12px; }}"
            "QPushButton:hover { background: #8b2020; }"
            "QPushButton:disabled { background: #2d2d2d; color: #666; border-color: #444; }"
        )
        self.btn_delete.clicked.connect(self._delete_memo)

        btn_row.addWidget(self.btn_new, 1)
        btn_row.addWidget(self.btn_delete, 0)
        ll.addLayout(btn_row)
        self._splitter.addWidget(left)

        # ── 右パネル ────────────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(10, 10, 10, 10)
        rl.setSpacing(8)

        # タイトル
        self.edt_title = QLineEdit()
        self.edt_title.setPlaceholderText(tr("タイトルを入力..."))
        self.edt_title.setFixedHeight(34)
        self.edt_title.setStyleSheet(
            "QLineEdit { border: 1px solid #3d3d3d; border-radius: 6px;"
            " padding: 0 10px; font-size: 14px; font-weight: 600; }"
            "QLineEdit:focus { border-color: #0078d4; }"
            "QLineEdit:disabled { color: #555; background: #1a1a1a; }"
        )
        self.edt_title.textChanged.connect(self._mark_dirty)
        rl.addWidget(self.edt_title)

        # タグ
        self.edt_tags = QLineEdit()
        self.edt_tags.setPlaceholderText(tr("タグ (カンマ区切り)  例: AI, プロンプト"))
        self.edt_tags.setFixedHeight(28)
        self.edt_tags.setStyleSheet(
            "QLineEdit { border: 1px solid #3d3d3d; border-radius: 6px;"
            " padding: 0 10px; font-size: 11px; color: #5c8bc0; }"
            "QLineEdit:focus { border-color: #5c8bc0; }"
            "QLineEdit:disabled { color: #444; background: #1a1a1a; }"
        )
        self.edt_tags.textChanged.connect(self._mark_dirty)
        rl.addWidget(self.edt_tags)

        # 内容エリア
        self.edt_content = QTextEdit()
        self.edt_content.setPlaceholderText(
            tr("テキスト・プロンプトをここに入力...\n「コピー」ボタンでクリップボードへコピーできます。")
        )
        self.edt_content.setStyleSheet(
            "QTextEdit { border: 1px solid #3d3d3d; border-radius: 6px;"
            " padding: 8px 10px; font-size: 13px; }"
            "QTextEdit:focus { border-color: #0078d4; }"
            "QTextEdit:disabled { color: #555; background: #1a1a1a; }"
        )
        self.edt_content.textChanged.connect(self._mark_dirty)
        self.edt_content.textChanged.connect(self._update_char_count)
        rl.addWidget(self.edt_content, 1)

        # 文字数 / 作成日時 行
        meta_row = QHBoxLayout()
        self.date_lbl = QLabel()
        self.date_lbl.setStyleSheet("color: #555; font-size: 10px;")
        self.char_lbl = QLabel()
        self.char_lbl.setStyleSheet("color: #555; font-size: 10px;")
        meta_row.addWidget(self.date_lbl)
        meta_row.addStretch()
        meta_row.addWidget(self.char_lbl)
        rl.addLayout(meta_row)

        # アクションボタン行
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self.btn_copy = QPushButton("📋  " + tr("コピー"))
        self.btn_copy.setObjectName("secondaryActionBtn")
        self.btn_copy.setFixedHeight(_BTN_H)
        self.btn_copy.setMinimumWidth(90)
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.setEnabled(False)
        self.btn_copy.clicked.connect(self._copy_content)

        self.btn_save = QPushButton(tr("保存"))
        self.btn_save.setObjectName("primaryActionBtn")
        self.btn_save.setFixedHeight(_BTN_H)
        self.btn_save.setMinimumWidth(80)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._save_memo)

        action_row.addWidget(self.btn_copy)
        action_row.addStretch()
        action_row.addWidget(self.btn_save)
        rl.addLayout(action_row)

        self._splitter.addWidget(right)
        self._splitter.setSizes([220, 580])

        root.addWidget(self._splitter, 1)

        # Ctrl+S ショートカット
        sc = QShortcut(QKeySequence.StandardKey.Save, self)
        sc.activated.connect(self._save_memo)

        self._set_edit_enabled(False)
        self.set_theme(self._is_dark)   # 初回スタイル適用

    # ── データ操作 ───────────────────────────────────────────────────────

    def _load_all(self):
        self._memos = _load_memos()
        self._rebuild_list()

    def _rebuild_list(self, filter_text: str = "", restore_idx: int = -1):
        """
        リストを再構築する。
        restore_idx が指定されていれば、その _memos インデックスのアイテムを再選択する。
        blockSignals を使って clear() 時のシグナル発火を防ぐ。
        """
        self._rebuilding = True
        self.memo_list.blockSignals(True)
        self.memo_list.clear()
        self.memo_list.blockSignals(False)

        ft = filter_text.lower()
        displayed = 0
        restore_row = -1

        for i, memo in enumerate(self._memos):
            title   = memo.get("title", "(無題)")
            tags    = memo.get("tags", "")
            content = memo.get("content", "")

            if ft and ft not in title.lower() and ft not in tags.lower() and ft not in content.lower():
                continue

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, i)

            # ツールチップ
            tt = title
            if tags:
                tt += "\n" + tr("タグ: {0}").format(tags)
            if content:
                tt += f"\n{content[:80]}..."
            item.setToolTip(tt)

            self.memo_list.addItem(item)
            widget = _MemoItemWidget(title, tags, content)
            item.setSizeHint(QSize(0, widget.sizeHint().height()))
            self.memo_list.setItemWidget(item, widget)

            if i == restore_idx:
                restore_row = self.memo_list.count() - 1
            displayed += 1

        if displayed == 0:
            ph = QListWidgetItem(tr("メモが見つかりません"))
            ph.setFlags(Qt.ItemFlag.NoItemFlags)
            ph.setForeground(Qt.GlobalColor.gray)
            self.memo_list.addItem(ph)

        # 件数ラベル更新
        total = len(self._memos)
        if ft:
            self.count_lbl.setText(tr("{0} / {1} 件").format(displayed, total))
        else:
            self.count_lbl.setText(tr("{0} 件").format(total))

        self._rebuilding = False

        # 選択を復元
        if restore_row >= 0:
            self.memo_list.setCurrentRow(restore_row)
        elif restore_idx < 0:
            self._set_edit_enabled(False)

    def _filter_list(self, text: str):
        self._rebuild_list(text, self._selected_idx)

    def _on_select(self, row: int):
        if self._rebuilding:
            return

        item = self.memo_list.item(row)
        if item is None or not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            self._selected_idx = -1
            self._set_edit_enabled(False)
            return

        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(self._memos):
            return

        self._selected_idx = idx
        memo = self._memos[idx]

        # シグナルを一時ブロックして _dirty をトリガーさせない
        for w in (self.edt_title, self.edt_tags, self.edt_content):
            w.blockSignals(True)

        self.edt_title.setText(memo.get("title", ""))
        self.edt_tags.setText(memo.get("tags", ""))
        self.edt_content.setPlainText(memo.get("content", ""))

        for w in (self.edt_title, self.edt_tags, self.edt_content):
            w.blockSignals(False)

        created = memo.get("created", "")
        self.date_lbl.setText(tr("作成: {0}").format(created) if created else "")
        self._update_char_count()
        self._dirty = False
        self._set_edit_enabled(True)
        self._refresh_save_btn()

    def _set_edit_enabled(self, enabled: bool):
        self.btn_delete.setEnabled(enabled)
        self.btn_copy.setEnabled(enabled)
        self.btn_save.setEnabled(enabled)
        self.edt_title.setEnabled(enabled)
        self.edt_tags.setEnabled(enabled)
        self.edt_content.setEnabled(enabled)
        if not enabled:
            for w in (self.edt_title, self.edt_tags, self.edt_content):
                w.blockSignals(True)
            self.edt_title.clear()
            self.edt_tags.clear()
            self.edt_content.clear()
            for w in (self.edt_title, self.edt_tags, self.edt_content):
                w.blockSignals(False)
            self.date_lbl.clear()
            self.char_lbl.clear()
            self._dirty = False

    def _mark_dirty(self):
        if not self._dirty:
            self._dirty = True
            self._refresh_save_btn()

    def _refresh_save_btn(self):
        if self._dirty and self._selected_idx >= 0:
            self.btn_save.setText(f"● {tr('保存')}")
        else:
            self.btn_save.setText(tr("保存"))

    def _update_char_count(self):
        n = len(self.edt_content.toPlainText())
        self.char_lbl.setText(tr("{0} 文字").format(f"{n:,}"))

    # ── CRUD ─────────────────────────────────────────────────────────────

    def _new_memo(self):
        now  = datetime.now().strftime("%Y-%m-%d %H:%M")
        memo = {"title": tr("新しいメモ"), "tags": "", "content": "", "created": now}
        self._memos.append(memo)
        new_idx = len(self._memos) - 1
        _save_memos(self._memos)
        self._rebuild_list(self.edt_search.text(), restore_idx=new_idx)
        self.edt_title.setFocus()
        self.edt_title.selectAll()

    def _save_memo(self):
        if self._selected_idx < 0 or self._selected_idx >= len(self._memos):
            return
        self._memos[self._selected_idx].update({
            "title":   self.edt_title.text().strip() or tr("無題のメモ"),
            "tags":    self.edt_tags.text().strip(),
            "content": self.edt_content.toPlainText(),
        })
        _save_memos(self._memos)
        self._dirty = False
        self._refresh_save_btn()
        # リスト表示を更新しつつ選択を維持
        self._rebuild_list(self.edt_search.text(), restore_idx=self._selected_idx)
        self._show_status(f"✅  {tr('保存しました')}")

    def _delete_memo(self):
        if self._selected_idx < 0 or self._selected_idx >= len(self._memos):
            return
        title = self._memos[self._selected_idx].get("title", tr("無題のメモ"))

        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, tr("削除の確認"),
            tr("「{0}」を削除しますか？").format(title),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._memos.pop(self._selected_idx)
        _save_memos(self._memos)
        self._selected_idx = -1
        self._dirty = False
        self._set_edit_enabled(False)
        self._rebuild_list(self.edt_search.text())
        self._show_status(f"🗑  {tr('削除しました。')}")

    def _copy_content(self):
        content = self.edt_content.toPlainText()
        if content:
            QApplication.clipboard().setText(content)
            self._show_status(f"📋  {tr('クリップボードにコピーしました')}")

    def _show_status(self, msg: str, ms: int = 2500):
        self.status_lbl.setText(msg)
        QTimer.singleShot(ms, lambda: self.status_lbl.setText(""))

    # ── テーマ適用 ───────────────────────────────────────────────────────

    def set_theme(self, is_dark: bool):
        self._is_dark = is_dark
        d = is_dark

        border_c = "#3d3d3d" if d else "#d0d0d0"
        border_h = "#333"    if d else "#ddd"
        list_bg  = "#1e1e1e" if d else "#ffffff"
        sel_bg   = "#094771" if d else "#e3f2fd"
        sel_fg   = "#ffffff" if d else "#0d47a1"
        hov_bg   = "#2a2d2e" if d else "#f0f0f0"
        dis_fg   = "#555"    if d else "#aaa"
        dis_bg   = "#1a1a1a" if d else "#f5f5f5"
        dim_c    = "#555"    if d else "#999"
        del_dis_bg = "#2d2d2d" if d else "#e8e8e8"
        del_dis_fg = "#666"    if d else "#aaa"
        del_dis_border = "#444" if d else "#ccc"

        self._header_frame.setStyleSheet(
            f"QFrame#memoHeader {{ border-bottom: 1px solid {border_h}; }}"
        )
        self._splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {border_h}; }}"
        )
        self.edt_search.setStyleSheet(
            f"QLineEdit {{ border: 1px solid {border_c}; border-radius: 6px;"
            " padding: 0 8px; font-size: 12px; }"
            "QLineEdit:focus { border-color: #0078d4; }"
        )
        self.memo_list.setStyleSheet(
            f"QListWidget {{ border: 1px solid {border_c}; border-radius: 6px;"
            f" background: {list_bg}; outline: 0; }}"
            "QListWidget::item { border-radius: 4px; margin: 1px 3px; }"
            f"QListWidget::item:selected {{ background: {sel_bg}; color: {sel_fg}; }}"
            f"QListWidget::item:hover:!selected {{ background: {hov_bg}; }}"
        )
        self.edt_title.setStyleSheet(
            f"QLineEdit {{ border: 1px solid {border_c}; border-radius: 6px;"
            " padding: 0 10px; font-size: 14px; font-weight: 600; }"
            "QLineEdit:focus { border-color: #0078d4; }"
            f"QLineEdit:disabled {{ color: {dis_fg}; background: {dis_bg}; }}"
        )
        self.edt_tags.setStyleSheet(
            f"QLineEdit {{ border: 1px solid {border_c}; border-radius: 6px;"
            " padding: 0 10px; font-size: 11px; color: #5c8bc0; }"
            "QLineEdit:focus { border-color: #5c8bc0; }"
            f"QLineEdit:disabled {{ color: {dis_fg}; background: {dis_bg}; }}"
        )
        self.edt_content.setStyleSheet(
            f"QTextEdit {{ border: 1px solid {border_c}; border-radius: 6px;"
            " padding: 8px 10px; font-size: 13px; }"
            "QTextEdit:focus { border-color: #0078d4; }"
            f"QTextEdit:disabled {{ color: {dis_fg}; background: {dis_bg}; }}"
        )
        self.date_lbl.setStyleSheet(f"color: {dim_c}; font-size: 10px;")
        self.char_lbl.setStyleSheet(f"color: {dim_c}; font-size: 10px;")
        self.btn_delete.setStyleSheet(
            "QPushButton { background: #6e2020; color: #ffaaaa;"
            " border: 1px solid #8b2222; border-radius: 4px; font-size: 12px; }"
            "QPushButton:hover { background: #8b2020; }"
            f"QPushButton:disabled {{ background: {del_dis_bg}; color: {del_dis_fg};"
            f" border-color: {del_dis_border}; }}"
        )
        super().set_theme(is_dark)


# ── カスタムリストアイテム ─────────────────────────────────────────────────

class _MemoItemWidget(QWidget):
    """タイトル + コンテンツプレビュー + タグ を表示する 2〜3行リストアイテム"""

    def __init__(self, title: str, tags: str, content: str):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)

        from app.core.i18n import tr as _tr
        t = QLabel(title or f"({_tr('無題のメモ')})")
        t.setStyleSheet(
            "font-size: 13px; font-weight: 600; background: transparent;"
        )
        t.setMaximumWidth(999)
        lay.addWidget(t)

        preview = content.replace("\n", " ").strip()
        if preview:
            short = preview[:48] + ("…" if len(preview) > 48 else "")
            p = QLabel(short)
            p.setStyleSheet("font-size: 11px; color: #777; background: transparent;")
            lay.addWidget(p)

        if tags.strip():
            tg = QLabel(tags)
            tg.setStyleSheet("font-size: 10px; color: #5c8bc0; background: transparent;")
            lay.addWidget(tg)
