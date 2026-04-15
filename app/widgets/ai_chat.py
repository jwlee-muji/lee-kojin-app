"""
AI チャットウィジェット
Gemini 3.1 Lite → Gemini 2.5 Flash → Groq の 3段フォールバック
"""
import html
import logging
import re
from datetime import datetime
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QTextEdit, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent
from app.ui.common import BaseWidget
from app.ui.theme import UIColors
from app.core.i18n import tr
from app.api.ai_api import (
    AiChatWorker, GEMINI_LITE_MODEL, GEMINI_DEFAULT_MODEL, GROQ_DEFAULT_MODEL,
    get_all_gemini_keys, get_builtin_groq_key,
)

logger = logging.getLogger(__name__)

_MAX_HISTORY  = 20
_COOLDOWN_SEC = 60

# カラー定義は UIColors.get_chat_colors() に集約 (theme.py)


class AiChatWidget(BaseWidget):
    def __init__(self):
        super().__init__()
        self._messages: list[dict] = []
        self._worker        = None
        self._is_dark       = True
        self._history_limit = 20
        self._cooldown_remaining = 0
        self._cooldown_timer = QTimer(self)
        self._cooldown_timer.setInterval(1000)
        self._cooldown_timer.timeout.connect(self._tick_cooldown)
        self._build_ui()

    # ── UI 構築 ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── ヘッダー ────────────────────────────────────────────────────
        self._header_frame = QFrame()
        self._header_frame.setObjectName("chatHeader")
        hrow = QHBoxLayout(self._header_frame)
        hrow.setContentsMargins(16, 9, 12, 9)
        hrow.setSpacing(12)

        title = QLabel(tr("AI アシスタント"))
        title.setStyleSheet("font-weight: bold; font-size: 15px;")

        self.model_lbl = QLabel()
        self.model_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.btn_clear = QPushButton(tr("クリア"))
        self.btn_clear.setFixedHeight(26)
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.clicked.connect(self._clear_history)

        hrow.addWidget(title)
        hrow.addWidget(self.model_lbl, 1)
        hrow.addWidget(self.btn_clear, 0)
        root.addWidget(self._header_frame)

        # ── API 警告バナー ────────────────────────────────────────────────
        self.api_warning = QLabel()
        self.api_warning.setWordWrap(True)
        self.api_warning.hide()
        root.addWidget(self.api_warning)

        # ── チャットエリア ────────────────────────────────────────────────
        self.chat_area = _ChatArea(self._is_dark, self._on_suggestion)
        root.addWidget(self.chat_area, 1)

        # ── 入力エリア ────────────────────────────────────────────────────
        self._input_frame = QFrame()
        self._input_frame.setObjectName("chatInputFrame")
        irow = QHBoxLayout(self._input_frame)
        irow.setContentsMargins(12, 8, 12, 8)
        irow.setSpacing(8)

        self.edt_input = _EnterTextEdit(self)
        self.edt_input.setPlaceholderText(
            tr("メッセージを入力...  (Enter 送信 / Shift+Enter 改行)")
        )
        self.edt_input.setMinimumHeight(52)
        self.edt_input.setMaximumHeight(120)

        self.btn_send = QPushButton(tr("送信"))
        self.btn_send.setObjectName("primaryActionBtn")
        self.btn_send.setFixedSize(60, 52)
        self.btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send.clicked.connect(self._send_message)

        irow.addWidget(self.edt_input)
        irow.addWidget(self.btn_send, 0, Qt.AlignmentFlag.AlignBottom)
        root.addWidget(self._input_frame)

        self._apply_chat_styles()
        self._refresh_api_status()
        self._update_model_label()

    # ── テーマ適用 ────────────────────────────────────────────────────────

    def _apply_chat_styles(self):
        d = self._is_dark

        # ヘッダー / 入力フレーム の区切り線
        border_c = "#333" if d else "#ddd"
        self._header_frame.setStyleSheet(
            f"QFrame#chatHeader {{ border-bottom: 1px solid {border_c}; }}"
        )
        self._input_frame.setStyleSheet(
            f"QFrame#chatInputFrame {{ border-top: 1px solid {border_c}; }}"
        )

        # モデルラベル
        self.model_lbl.setStyleSheet(
            f"color: {'#777' if d else '#999'}; font-size: 10px;"
        )

        # クリアボタン (inline style でテーマ上書き)
        if d:
            cb_bg, cb_border, cb_fg, cb_hov, cb_press = "#333", "#555", "#ccc", "#444", "#222"
        else:
            cb_bg, cb_border, cb_fg, cb_hov, cb_press = "#ebebeb", "#ccc", "#444", "#d8d8d8", "#c8c8c8"
        self.btn_clear.setStyleSheet(
            f"QPushButton {{ padding: 3px 14px; border: 1px solid {cb_border}; border-radius: 4px;"
            f" color: {cb_fg}; background: {cb_bg}; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {cb_hov}; }}"
            f"QPushButton:pressed {{ background: {cb_press}; }}"
        )

        # API 警告バナー
        if d:
            aw_bg, aw_fg = "#1a3a5c", "#90caf9"
        else:
            aw_bg, aw_fg = "#dff0ff", "#0055aa"
        self.api_warning.setStyleSheet(
            f"background: {aw_bg}; color: {aw_fg}; padding: 8px 16px; font-size: 12px;"
        )

        # テキスト入力フィールド
        inp_border = "#3d3d3d" if d else "#d0d0d0"
        self.edt_input.setStyleSheet(
            "QTextEdit {"
            f"  border: 1px solid {inp_border}; border-radius: 10px;"
            "  padding: 8px 12px; font-size: 13px;"
            "}"
            "QTextEdit:focus { border-color: #0078d4; }"
        )

    # ── ヘルパー ─────────────────────────────────────────────────────────

    def _refresh_api_status(self):
        has_gemini = bool(get_all_gemini_keys())
        has_groq   = bool(get_builtin_groq_key())
        if not has_gemini and not has_groq:
            self.api_warning.setText(
                tr("⚠️ API キーが取得できませんでした。\nアプリを再インストールするか、管理者にお問い合わせください。")
            )
            self.api_warning.show()
            self.btn_send.setEnabled(False)
        else:
            self.api_warning.hide()
            self.btn_send.setEnabled(True)

    def _update_model_label(self):
        n = len(get_all_gemini_keys())
        has_groq = bool(get_builtin_groq_key())
        parts = []
        if n:
            parts.append(f"Gemini 3.1 Lite › 2.5 Flash  ({n}key)")
        if has_groq:
            parts.append("Groq")
        self.model_lbl.setText("  |  ".join(parts) if parts else "")

    def _on_suggestion(self, text: str):
        self.edt_input.setPlainText(text)
        self.edt_input.setFocus()

    # ── 送受信 ───────────────────────────────────────────────────────────

    def _send_message(self):
        text = self.edt_input.toPlainText().strip()
        if not text:
            return

        gemini_keys = get_all_gemini_keys()
        groq_key    = get_builtin_groq_key()
        if not gemini_keys and not groq_key:
            self._refresh_api_status()
            return

        self.edt_input.clear()
        self.chat_area.add_bubble("user", text)
        self._messages.append({"role": "user", "content": text})

        self.chat_area.add_thinking()
        self.btn_send.setEnabled(False)

        from app.core.config import load_settings
        s = load_settings()
        model       = s.get("gemini_model", GEMINI_DEFAULT_MODEL).strip()
        temperature = float(s.get("ai_temperature", 0.7))
        max_tokens  = int(s.get("ai_max_tokens", 2048))
        self._history_limit = int(s.get("chat_history_limit", _MAX_HISTORY))

        self._worker = AiChatWorker(
            list(self._messages), gemini_keys, groq_key, model,
            temperature=temperature, max_tokens=max_tokens,
        )
        self._worker.response_received.connect(self._on_response)
        self._worker.error.connect(self._on_error)
        self._worker.rate_limited.connect(self._on_rate_limited)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()
        self.track_worker(self._worker)

    def _on_response(self, reply: str):
        self.chat_area.remove_thinking()
        self._messages.append({"role": "assistant", "content": reply})
        self.chat_area.add_bubble("assistant", reply)
        self.btn_send.setEnabled(True)
        if len(self._messages) > self._history_limit:
            self._messages = self._messages[-self._history_limit:]

    def _on_error(self, err: str):
        self.chat_area.remove_thinking()
        self.chat_area.add_system(f"❌ {tr('AIサービスに接続できません。')}\n{err}")
        self.btn_send.setEnabled(True)

    def _on_rate_limited(self):
        self.chat_area.remove_thinking()
        self.chat_area.add_system(
            tr("⏳ 全APIのリクエスト上限に達しました。\n{0}秒後に再試行できます。（無料枠リセット: UTC 0:00）").format(_COOLDOWN_SEC)
        )
        self._start_cooldown()

    # ── クールダウン ─────────────────────────────────────────────────────

    def _start_cooldown(self):
        self._cooldown_remaining = _COOLDOWN_SEC
        self.btn_send.setEnabled(False)
        self._cooldown_timer.start()
        self._update_cooldown_btn()

    def _tick_cooldown(self):
        self._cooldown_remaining -= 1
        if self._cooldown_remaining <= 0:
            self._cooldown_timer.stop()
            self.btn_send.setText(tr("送信"))
            self.btn_send.setEnabled(True)
        else:
            self._update_cooldown_btn()

    def _update_cooldown_btn(self):
        self.btn_send.setText(f"{self._cooldown_remaining}s")

    def _clear_history(self):
        self._messages.clear()
        self.chat_area.clear_messages()

    def set_theme(self, is_dark: bool):
        self._is_dark = is_dark
        self._apply_chat_styles()
        self.chat_area.set_theme(is_dark)
        super().set_theme(is_dark)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_api_status()
        self._update_model_label()


# ── チャットエリア ────────────────────────────────────────────────────────

class _ChatArea(QScrollArea):
    """スクロール可能なバブルコンテナ。空のときはウェルカム画面を表示。"""

    @staticmethod
    def _get_suggestions():
        return [
            tr("インバランス単価の最近の動向を教えて"),
            tr("電力予備率が低下するとどうなりますか？"),
            tr("LNG価格と電力価格の関係を説明して"),
        ]

    def __init__(self, is_dark: bool, on_suggestion):
        super().__init__()
        self._is_dark        = is_dark
        self._on_suggestion  = on_suggestion
        self._thinking_widget = None
        self._msg_count      = 0
        self._bubbles: list["_BubbleWidget"] = []

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._layout    = QVBoxLayout(self._container)
        self._layout.setSpacing(8)
        self._layout.setContentsMargins(14, 14, 14, 14)

        self._welcome = self._build_welcome()
        self._layout.addWidget(self._welcome, 0, Qt.AlignmentFlag.AlignTop)
        self._layout.addStretch()

        self.setWidget(self._container)

    # ── ウェルカム ────────────────────────────────────────────────────────

    def _build_welcome(self) -> QWidget:
        d = self._is_dark

        card = QWidget()
        card.setObjectName("welcomeCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 32, 24, 24)
        layout.setSpacing(10)

        # アイコン + タイトル
        icon_row = QHBoxLayout()
        icon_row.setSpacing(10)

        avatar = QLabel("AI")
        avatar.setFixedSize(40, 40)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"background: {UIColors.get_chat_colors(True)["avatar_bg"]}; color: white;"
            "border-radius: 20px; font-weight: bold; font-size: 14px;"
        )

        title_lbl = QLabel(tr("AI アシスタント"))
        title_lbl.setStyleSheet("font-size: 17px; font-weight: bold;")

        icon_row.addWidget(avatar)
        icon_row.addWidget(title_lbl)
        icon_row.addStretch()
        layout.addLayout(icon_row)

        desc_fg = "#888" if d else "#666"
        desc = QLabel(tr("日本の電力市場・インバランス単価・LNG価格などについて質問できます。"))
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {desc_fg}; font-size: 12px;")
        layout.addWidget(desc)

        chip_lbl_fg = "#666" if d else "#888"
        chip_label = QLabel(tr("試してみてください:"))
        chip_label.setStyleSheet(f"color: {chip_lbl_fg}; font-size: 11px; margin-top: 8px;")
        layout.addWidget(chip_label)

        # テーマ別チップスタイル
        if d:
            chip_border, chip_fg   = "#3a3a3a", "#bbb"
            chip_hov_bg, chip_hov_fg = "#2a2d2e", "#fff"
        else:
            chip_border, chip_fg   = "#d0d0d0", "#444"
            chip_hov_bg, chip_hov_fg = "#e8e8e8", "#111"

        for suggestion in self._get_suggestions():
            chip = QPushButton(suggestion)
            chip.setStyleSheet(
                f"QPushButton {{ text-align: left; padding: 7px 12px;"
                f" border: 1px solid {chip_border}; border-radius: 8px;"
                f" color: {chip_fg}; background: transparent; font-size: 12px; }}"
                f"QPushButton:hover {{ background: {chip_hov_bg};"
                f" border-color: #0078d4; color: {chip_hov_fg}; }}"
            )
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _, s=suggestion: self._on_suggestion(s))
            layout.addWidget(chip)

        return card

    # ── public API ───────────────────────────────────────────────────────

    def add_bubble(self, role: str, text: str):
        if self._msg_count == 0:
            self._layout.removeWidget(self._welcome)
            self._welcome.hide()
        self._msg_count += 1
        time_str = datetime.now().strftime("%H:%M")
        bubble = _BubbleWidget(role, text, time_str, self._is_dark)
        self._bubbles.append(bubble)
        self._insert(bubble)

    def add_thinking(self):
        w = _ThinkingWidget(self._is_dark)
        self._thinking_widget = w
        self._insert(w)

    def remove_thinking(self):
        if self._thinking_widget is not None:
            self._layout.removeWidget(self._thinking_widget)
            self._thinking_widget.deleteLater()
            self._thinking_widget = None

    def add_system(self, text: str):
        d = self._is_dark
        if d:
            sys_bg, sys_fg = "#2a1f00", "#e0a030"
        else:
            sys_bg, sys_fg = "#fff8e1", "#bf6000"
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            f"color: {sys_fg}; font-size: 12px; padding: 8px 16px;"
            f"background: {sys_bg}; border-radius: 8px; margin: 0 20px;"
        )
        self._insert(lbl)

    def clear_messages(self):
        """全メッセージ削除してウェルカム画面を復元"""
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._thinking_widget = None
        self._msg_count = 0
        self._bubbles.clear()

        self._welcome = self._build_welcome()
        self._layout.insertWidget(0, self._welcome, 0, Qt.AlignmentFlag.AlignTop)

    def set_theme(self, is_dark: bool):
        self._is_dark = is_dark
        # ウェルカム表示中のみ再構築 (テーマ切替でチップ色を更新)
        if self._msg_count == 0:
            self._layout.removeWidget(self._welcome)
            self._welcome.deleteLater()
            self._welcome = self._build_welcome()
            self._layout.insertWidget(0, self._welcome, 0, Qt.AlignmentFlag.AlignTop)
        # 既存バブルのテーマを動的に更新
        for bubble in self._bubbles:
            try:
                bubble.set_theme(is_dark)
            except RuntimeError:
                pass  # 既に削除済みのウィジェットはスキップ
        self._bubbles = [b for b in self._bubbles if not b.isHidden() or True]

    # ── private ──────────────────────────────────────────────────────────

    def _insert(self, widget: QWidget):
        self._layout.insertWidget(self._layout.count() - 1, widget)
        QTimer.singleShot(30, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())


# ── バブルウィジェット ────────────────────────────────────────────────────

class _BubbleWidget(QWidget):
    """メッセージバブル — QHBoxLayout で左右位置を確実に固定"""

    def __init__(self, role: str, text: str, time_str: str, is_dark: bool):
        super().__init__()
        self._is_user   = role == "user"
        self._is_dark   = is_dark

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        if not self._is_user:
            av = QLabel("AI")
            av.setFixedSize(28, 28)
            av.setAlignment(Qt.AlignmentFlag.AlignCenter)
            av.setStyleSheet(
                f"background: {UIColors.get_chat_colors(True)["avatar_bg"]}; color: #fff;"
                "border-radius: 14px; font-weight: bold; font-size: 10px;"
            )
            outer.addWidget(av, 0, Qt.AlignmentFlag.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(3)
        col.setContentsMargins(0, 0, 0, 0)

        self._lbl = QLabel(_format_message(text))
        self._lbl.setTextFormat(Qt.TextFormat.RichText)
        self._lbl.setWordWrap(True)
        self._lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._lbl.setMaximumWidth(520)
        self._lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        self._time_lbl = QLabel(time_str)
        self._time_lbl.setStyleSheet(f"color: {'#888' if is_dark else '#aaa'}; font-size: 10px;")

        self._apply_bubble_style(is_dark)

        col.addWidget(self._lbl)
        col.addWidget(
            self._time_lbl, 0,
            Qt.AlignmentFlag.AlignRight if self._is_user else Qt.AlignmentFlag.AlignLeft,
        )

        if self._is_user:
            outer.addStretch(1)
            outer.addLayout(col)
        else:
            outer.addLayout(col)
            outer.addStretch(1)

    def _apply_bubble_style(self, is_dark: bool):
        cc = UIColors.get_chat_colors(is_dark)
        if self._is_user:
            self._lbl.setStyleSheet(
                f"background: {cc['user_bg']}; color: {cc['user_fg']};"
                "border-radius: 16px 16px 4px 16px;"
                "padding: 9px 14px; font-size: 13px; line-height: 1.5;"
            )
        else:
            self._lbl.setStyleSheet(
                f"background: {cc['asst_bg']}; color: {cc['asst_fg']};"
                "border-radius: 4px 16px 16px 16px;"
                "padding: 9px 14px; font-size: 13px; line-height: 1.5;"
            )
        self._time_lbl.setStyleSheet(
            f"color: {cc['time_fg']}; font-size: 10px;"
        )

    def set_theme(self, is_dark: bool):
        """テーマ変更時に既存バブルの色を動的に更新します。"""
        self._is_dark = is_dark
        self._apply_bubble_style(is_dark)


# ── 「考え中」アニメーション ──────────────────────────────────────────────

class _ThinkingWidget(QWidget):
    _FRAMES = ["   ", ".  ", ".. ", "..."]

    def __init__(self, is_dark: bool = True):
        super().__init__()
        self._step = 0
        fg = "#777" if is_dark else "#888"

        row = QHBoxLayout(self)
        row.setContentsMargins(36, 0, 0, 0)
        row.setSpacing(0)

        self._lbl = QLabel()
        self._lbl.setStyleSheet(
            f"color: {fg}; font-size: 12px; font-style: italic; padding: 4px 0;"
        )
        row.addWidget(self._lbl)
        row.addStretch()

        self._timer = QTimer(self)
        self._timer.setInterval(450)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._tick()

    def _tick(self):
        self._lbl.setText(f"⏳ {tr('考え中')}{self._FRAMES[self._step]}")
        self._step = (self._step + 1) % len(self._FRAMES)

    def deleteLater(self):
        self._timer.stop()
        super().deleteLater()


# ── テキストフォーマッター ────────────────────────────────────────────────

def _format_message(text: str) -> str:
    """
    マークダウン風テキストを QLabel RichText 用 HTML に変換。
    コードブロック・インラインコード・太字・改行 を処理。
    """
    def replace_codeblock(m: re.Match) -> str:
        code = html.escape(m.group(2).strip())
        return (
            '<div style="background:#1a1a1a; color:#c8d3da; border-radius:6px;'
            ' padding:8px 10px; margin:4px 0; font-family:Consolas,monospace;'
            f' font-size:12px; white-space:pre-wrap;">{code}</div>'
        )

    text = re.sub(r"```(\w*)\n?(.*?)\n?```", replace_codeblock, text, flags=re.DOTALL)

    parts = re.split(r'(<div[^>]*>.*?</div>)', text, flags=re.DOTALL)
    escaped = []
    for p in parts:
        if p.startswith("<div"):
            escaped.append(p)
        else:
            p = html.escape(p)
            p = re.sub(
                r"`([^`]+)`",
                r'<code style="background:#2a2a2a; padding:1px 5px;'
                r' border-radius:3px; font-family:Consolas,monospace; font-size:12px;">\1</code>',
                p,
            )
            p = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", p)
            p = p.replace("\n", "<br>")
            escaped.append(p)

    return "".join(escaped)


# ── カスタムテキスト入力 ──────────────────────────────────────────────────

class _EnterTextEdit(QTextEdit):
    """Enter 送信 / Shift+Enter 改行"""

    def __init__(self, parent_widget: AiChatWidget):
        super().__init__()
        self._parent_widget = parent_widget

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self._parent_widget._send_message()
        else:
            super().keyPressEvent(event)
