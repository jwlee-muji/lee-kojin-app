"""
バグレポート送信ウィジェット
概要・分類・詳細・ログを入力して開発者へ送信。
メール設定はユーザー不要 — 内蔵認証情報を使用。
"""
import logging
from pathlib import Path
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QComboBox, QFrame, QWidget,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from app.ui.common import BaseWidget
from app.core.i18n import tr
from app.api.email_api import SendBugReportWorker, BUG_REPORT_TO

logger = logging.getLogger(__name__)

_MAX_LOG_LINES  = 80
_SUMMARY_LIMIT  = 100
_BTN_H          = 32

_CATEGORIES_JA = [
    "🐛  バグ・エラー",
    "🖥️  UI表示の問題",
    "📡  データ取得エラー",
    "⚡  パフォーマンス問題",
    "💡  機能要望",
    "❓  その他",
]


class BugReportWidget(BaseWidget):
    def __init__(self):
        super().__init__()
        self._worker = None
        self._build_ui()
        self._load_log()

    # ── UI 構築 ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── ヘッダー ────────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("bugHeader")
        header.setStyleSheet("QFrame#bugHeader { border-bottom: 1px solid #333; }")
        hrow = QHBoxLayout(header)
        hrow.setContentsMargins(16, 10, 16, 10)

        title_lbl = QLabel(tr("バグレポート"))
        title_lbl.setStyleSheet("font-weight: bold; font-size: 15px;")

        try:
            from version import __version__
            ver = f"v{__version__}"
        except Exception:
            ver = ""

        dest_lbl = QLabel(f"{BUG_REPORT_TO}  {ver}")
        dest_lbl.setStyleSheet("color: #666; font-size: 10px;")

        hrow.addWidget(title_lbl)
        hrow.addStretch()
        hrow.addWidget(dest_lbl)
        root.addWidget(header)

        # ── フォームエリア ────────────────────────────────────────────────
        form_widget = QWidget()
        form_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        fl = QVBoxLayout(form_widget)
        fl.setContentsMargins(20, 16, 20, 12)
        fl.setSpacing(14)

        # 分類
        fl.addWidget(self._field_label(tr("分類")))
        self.cmb_category = QComboBox()
        self.cmb_category.addItems([tr(c) for c in _CATEGORIES_JA])
        self.cmb_category.setFixedHeight(32)
        self.cmb_category.setStyleSheet(
            "QComboBox { border: 1px solid #3d3d3d; border-radius: 6px;"
            " padding: 0 10px; font-size: 13px; }"
            "QComboBox:focus { border-color: #0078d4; }"
            "QComboBox::drop-down { border: none; width: 24px; }"
        )
        fl.addWidget(self.cmb_category)

        # 概要
        summary_header = QHBoxLayout()
        summary_header.addWidget(self._field_label(tr("概要")))
        summary_header.addStretch()
        self.summary_count = QLabel("0 / 100")
        self.summary_count.setStyleSheet("color: #555; font-size: 10px;")
        summary_header.addWidget(self.summary_count)
        fl.addLayout(summary_header)

        self.edt_summary = QLineEdit()
        self.edt_summary.setPlaceholderText(tr("例: ダッシュボードが起動時にクラッシュする"))
        self.edt_summary.setMaxLength(_SUMMARY_LIMIT)
        self.edt_summary.setFixedHeight(34)
        self.edt_summary.setStyleSheet(
            "QLineEdit { border: 1px solid #3d3d3d; border-radius: 6px;"
            " padding: 0 10px; font-size: 13px; }"
            "QLineEdit:focus { border-color: #0078d4; }"
        )
        self.edt_summary.textChanged.connect(self._on_summary_changed)
        fl.addWidget(self.edt_summary)

        # 詳細
        fl.addWidget(self._field_label(tr("詳細・再現手順  (任意)")))
        self.edt_detail = QTextEdit()
        self.edt_detail.setPlaceholderText(
            tr("1. アプリを起動する\n2. ○○をクリックする\n3. エラーが発生する")
        )
        self.edt_detail.setMinimumHeight(100)
        self.edt_detail.setMaximumHeight(160)
        self.edt_detail.setStyleSheet(
            "QTextEdit { border: 1px solid #3d3d3d; border-radius: 6px;"
            " padding: 8px 10px; font-size: 13px; }"
            "QTextEdit:focus { border-color: #0078d4; }"
        )
        fl.addWidget(self.edt_detail)

        # ログセクション (折りたたみ可)
        log_header = QHBoxLayout()
        self.btn_toggle_log = QPushButton("▶  " + tr("ログ (自動取得)"))
        self.btn_toggle_log.setCheckable(True)
        self.btn_toggle_log.setChecked(False)
        self.btn_toggle_log.setStyleSheet(
            "QPushButton { border: none; text-align: left; color: #888;"
            " font-size: 12px; padding: 0; background: transparent; }"
            "QPushButton:hover { color: #bbb; }"
            "QPushButton:checked { color: #ccc; }"
        )
        self.btn_toggle_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_log.toggled.connect(self._toggle_log_section)

        self.btn_reload_log = QPushButton("↺")
        self.btn_reload_log.setFixedSize(24, 24)
        self.btn_reload_log.setStyleSheet(
            "QPushButton { border: 1px solid #3d3d3d; border-radius: 4px;"
            " color: #888; background: transparent; font-size: 13px; }"
            "QPushButton:hover { color: #ccc; background: #2a2a2a; }"
        )
        self.btn_reload_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reload_log.clicked.connect(self._load_log)
        self.btn_reload_log.setVisible(False)

        log_header.addWidget(self.btn_toggle_log)
        log_header.addWidget(self.btn_reload_log)
        log_header.addStretch()
        fl.addLayout(log_header)

        self.log_container = QWidget()
        self.log_container.setVisible(False)
        lc_layout = QVBoxLayout(self.log_container)
        lc_layout.setContentsMargins(0, 4, 0, 0)
        lc_layout.setSpacing(0)

        self.edt_log = QTextEdit()
        self.edt_log.setReadOnly(True)
        self.edt_log.setMinimumHeight(120)
        self.edt_log.setMaximumHeight(200)
        self.edt_log.setStyleSheet(
            "QTextEdit { border: 1px solid #3d3d3d; border-radius: 6px;"
            " padding: 6px 8px; font-family: 'Consolas', monospace; font-size: 11px;"
            " color: #aaa; background: #161616; }"
        )
        lc_layout.addWidget(self.edt_log)
        fl.addWidget(self.log_container)

        fl.addStretch()
        root.addWidget(form_widget, 1)

        # ── ステータス + ボタン行 ─────────────────────────────────────────
        footer = QFrame()
        footer.setObjectName("bugFooter")
        footer.setStyleSheet("QFrame#bugFooter { border-top: 1px solid #333; }")
        frow = QHBoxLayout(footer)
        frow.setContentsMargins(20, 10, 20, 10)
        frow.setSpacing(10)

        self.status_lbl = QLabel()
        self.status_lbl.setStyleSheet("font-size: 12px;")
        self.status_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.btn_clear = QPushButton(tr("クリア"))
        self.btn_clear.setObjectName("secondaryActionBtn")
        self.btn_clear.setFixedHeight(_BTN_H)
        self.btn_clear.setMinimumWidth(72)
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.clicked.connect(self._clear_form)

        self.btn_send = QPushButton(tr("送信  →"))
        self.btn_send.setObjectName("primaryActionBtn")
        self.btn_send.setFixedHeight(_BTN_H)
        self.btn_send.setMinimumWidth(100)
        self.btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send.clicked.connect(self._send_report)

        frow.addWidget(self.status_lbl, 1)
        frow.addWidget(self.btn_clear)
        frow.addWidget(self.btn_send)
        root.addWidget(footer)

    # ── 内部メソッド ─────────────────────────────────────────────────────

    @staticmethod
    def _field_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 12px; color: #999; font-weight: 600;")
        return lbl

    def _on_summary_changed(self, text: str):
        n = len(text)
        self.summary_count.setText(f"{n} / {_SUMMARY_LIMIT}")
        color = "#e05050" if n >= _SUMMARY_LIMIT else "#555"
        self.summary_count.setStyleSheet(f"color: {color}; font-size: 10px;")

    def _toggle_log_section(self, checked: bool):
        self.btn_toggle_log.setText(
            ("▼  " if checked else "▶  ") + tr("ログ (自動取得)")
        )
        self.log_container.setVisible(checked)
        self.btn_reload_log.setVisible(checked)

    def _load_log(self):
        from app.core.config import LOG_FILE
        try:
            lines = Path(LOG_FILE).read_text(encoding="utf-8", errors="replace").splitlines()
            self.edt_log.setPlainText("\n".join(lines[-_MAX_LOG_LINES:]))
            cursor = self.edt_log.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.edt_log.setTextCursor(cursor)
        except Exception as e:
            self.edt_log.setPlainText(tr("[ログ読込失敗: {0}]").format(e))

    def _send_report(self):
        summary = self.edt_summary.text().strip()
        if not summary:
            self._set_status(f"⚠️  {tr('概要を入力してください。')}", error=True)
            return

        try:
            from version import __version__
            ver_str = f"v{__version__}"
        except Exception:
            ver_str = ""

        category = self.cmb_category.currentText().split("  ", 1)[-1].strip()
        subject  = f"[LEE {ver_str}] {category}: {summary}"
        body     = (
            f"{tr('【分類】')}{category}\n"
            f"{tr('【概要】')}{summary}\n\n"
            f"{tr('【詳細・再現手順】\n')}{self.edt_detail.toPlainText() or tr('(未記入)')}\n\n"
            f"{tr('【ログ (直近 {0} 行)】\n').format(_MAX_LOG_LINES)}{self.edt_log.toPlainText()}"
        )

        self.btn_send.setEnabled(False)
        self.btn_send.setText(tr("送信中..."))
        self._set_status("")

        self._worker = SendBugReportWorker(subject, body)
        self._worker.success.connect(self._on_send_success)
        self._worker.error.connect(self._on_send_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()
        self.track_worker(self._worker)

    def _on_send_success(self):
        self.btn_send.setEnabled(True)
        self.btn_send.setText(tr("送信  →"))
        self._set_status(f"✅  {tr('レポートを送信しました。ありがとうございます。')}")
        self.edt_summary.clear()
        self.edt_detail.clear()
        self.cmb_category.setCurrentIndex(0)

    def _on_send_error(self, err: str):
        self.btn_send.setEnabled(True)
        self.btn_send.setText(tr("送信  →"))
        self._set_status(f"❌  {tr('送信に失敗しました:')} {err}", error=True)

    def _clear_form(self):
        self.edt_summary.clear()
        self.edt_detail.clear()
        self.cmb_category.setCurrentIndex(0)
        self._load_log()
        self._set_status("")

    def _set_status(self, msg: str, error: bool = False):
        self.status_lbl.setText(msg)
        color = "#e05050" if error else "#4caf50"
        self.status_lbl.setStyleSheet(f"font-size: 12px; color: {color};")
        if msg and not error:
            QTimer.singleShot(6000, lambda: self.status_lbl.setText(""))
