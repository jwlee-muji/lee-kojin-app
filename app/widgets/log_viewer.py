import logging
import re
from pathlib import Path
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QComboBox
)
from PySide6.QtCore import QFileSystemWatcher, QTimer
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from app.core.config import LOG_FILE
from app.core.i18n import tr
from app.core.constants import Timers, Cache
from app.ui.theme import UIColors
from app.ui.common import BaseWidget

logger = logging.getLogger(__name__)


class _LogHighlighter(QSyntaxHighlighter):
    """ログ行をパターンマッチで色分けする QSyntaxHighlighter。
    appendPlainText と組み合わせることで appendHtml より大幅に高速になる。"""

    def __init__(self, document, colors: dict):
        super().__init__(document)
        self._rules: list[tuple[re.Pattern, QTextCharFormat]] = []
        self._build_rules(colors)

    def update_colors(self, colors: dict):
        """テーマ切替時に色を更新して再ハイライトする。"""
        self._build_rules(colors)
        self.rehighlight()

    def _build_rules(self, c: dict):
        def _fmt(color_str: str, bold: bool = False,
                 bg: str | None = None) -> QTextCharFormat:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color_str))
            if bold:
                fmt.setFontWeight(QFont.Bold)
            if bg:
                fmt.setBackground(QColor(bg))
            return fmt

        # 順序が重要: 後のルールが前のルールを上書きする
        # モジュール名パターンを先に置き、ログレベルキーワードを後に置くことで
        # レベルキーワードが必ずモジュール色を上書きする
        self._rules = [
            (re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'), _fmt(c['time'])),
            # モジュール名: app.xxx.yyy または __main__ (括弧なし)
            (re.compile(r'\b(?:app(?:\.\w+)+|__main__)'), _fmt(c['module'])),
            # ログレベルは後に置いて優先度を最高にする
            (re.compile(r'\[INFO\]'),    _fmt(c['info'])),
            (re.compile(r'\[WARNING\]'), _fmt(c['warning'], bold=True)),
            (re.compile(r'\[ERROR\]'),   _fmt(c['error'],   bold=True)),
        ]
        # 行全体の背景色用フォーマット (ERROR / WARNING)
        self._error_line_fmt   = _fmt(c['error'],   bold=True, bg=c.get('error_bg'))
        self._warning_line_fmt = _fmt(c['warning'], bold=True, bg=c.get('warn_bg'))

    def highlightBlock(self, text: str):
        # ERROR / WARNING 行は行全体に背景色を適用してから前景ルールを重ねる
        if '[ERROR]' in text:
            self.setFormat(0, len(text), self._error_line_fmt)
        elif '[WARNING]' in text:
            self.setFormat(0, len(text), self._warning_line_fmt)

        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


class LogViewerWidget(BaseWidget):
    """
    앱의 백그라운드 동작 상태(app.log)를 실시간으로 보여주는 시스템 로그 뷰어
    BaseWidget 継承により set_theme() / apply_theme_custom() / showEvent() を統一管理します。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # is_dark は BaseWidget.__init__ で True に初期化済み
        self._log_file = LOG_FILE
        self._last_pos = 0        # 마지막으로 읽은 파일 위치 캐싱
        self._all_lines: list[str] = []  # 読込済み行のインメモリキャッシュ (最大1000行)
        self._log_buffer = []     # 대량 로그 처리용 버퍼

        self._process_timer = QTimer(self)
        self._process_timer.setInterval(Timers.LOG_PROCESS_INTERVAL_MS)
        self._process_timer.timeout.connect(self._process_log_buffer)

        self._build_ui()

        # OS 이벤트 기반 로그 파일 변경 감지 (I/O 최적화 / 즉시 반영)
        if not self._log_file.exists():
            self._log_file.touch()

        self.watcher = QFileSystemWatcher(self)
        self.watcher.addPath(str(self._log_file.absolute()))
        self.watcher.fileChanged.connect(self._load_logs)

        self._load_logs()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        top = QHBoxLayout()
        title = QLabel(tr("システムログ (System Logs)"))
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        top.addWidget(title)
        top.addSpacing(15)

        self.module_combo = QComboBox()
        self.module_combo.addItems([
            tr("すべての機能"),
            tr("システム起動・終了"),
            tr("発電停止状況 (HJKS)"),
            tr("インバランス単価"),
            tr("JKM LNG 価格"),
            tr("全国天気予報"),
            tr("電力予備率 (OCCTO)")
        ])
        self.module_combo.currentIndexChanged.connect(self._on_filter_changed)
        top.addWidget(self.module_combo)

        self.level_combo = QComboBox()
        self.level_combo.addItems([tr("すべてのログレベル"), "INFO", "WARNING", "ERROR"])
        self.level_combo.currentIndexChanged.connect(self._on_filter_changed)
        top.addWidget(self.level_combo)

        top.addStretch()

        self.clear_btn = QPushButton(tr("ログ消去"))
        self.clear_btn.clicked.connect(self._clear_logs)

        refresh_btn = QPushButton(tr("手動更新"))
        refresh_btn.clicked.connect(self._load_logs)
        
        top.addWidget(self.clear_btn)
        top.addWidget(refresh_btn)
        layout.addLayout(top)
        
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 11))
        _lc = UIColors.get_log_colors(self.is_dark)
        self.log_text.setStyleSheet(
            f"background-color: {_lc['bg']}; color: {_lc['text']}; padding: 10px; border: none;"
        )
        self.log_text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.log_text.document().setMaximumBlockCount(Cache.LOG_MAX_LINES)
        # QSyntaxHighlighter を文書に接続 (appendPlainText より高速な色付け)
        self._highlighter = _LogHighlighter(self.log_text.document(), _lc)
        layout.addWidget(self.log_text)

    def apply_theme_custom(self):
        is_dark = self.is_dark
        lc = UIColors.get_log_colors(is_dark)
        self.clear_btn.setStyleSheet(
            f"background-color: {'#5c1111' if is_dark else '#ffcccc'}; "
            f"color: {'#ffffff' if is_dark else '#cc0000'}; "
            f"border: 1px solid {'#801515' if is_dark else '#ff9999'};"
        )
        self.log_text.setStyleSheet(
            f"background-color: {lc['bg']}; color: {lc['text']}; padding: 10px; border: none;"
        )
        # ハイライトカラーを更新してキャッシュから再描画
        self._highlighter.update_colors(lc)
        self._rerender_from_cache()

    def _on_filter_changed(self):
        # フィルタ変更: ディスク再読み込みなしにキャッシュから再描画
        self._rerender_from_cache()

    def _rerender_from_cache(self):
        """_all_lines キャッシュから表示を再構築。ディスクアクセスなし。"""
        self.log_text.clear()
        if self._all_lines:
            self._log_buffer = list(self._all_lines)
            if not self._process_timer.isActive():
                self._process_timer.start()

    def _load_logs(self):
        if not self._log_file.exists():
            return
            
        try:
            current_size = self._log_file.stat().st_size
            if current_size < self._last_pos:
                # ファイルが切り詰められた (ログ消去等): キャッシュをリセット
                self.log_text.clear()
                self._last_pos = 0
                self._all_lines.clear()

            if current_size == self._last_pos:
                return  # 추가된 변경 내용 없음
                
            with open(self._log_file, 'r', encoding='utf-8', errors='replace') as f:
                # 처음 읽을 때 파일이 500KB를 넘으면 뒤에서부터 읽음 (OOM/프리징 방지)
                MAX_READ_BYTES = Cache.LOG_MAX_READ_BYTES
                if self._last_pos == 0 and current_size > MAX_READ_BYTES:
                    f.seek(current_size - MAX_READ_BYTES)
                    # 잘린 첫 줄은 버리기 위해 readlines 대신 부분 읽기 후 첫 줄 컷
                    f.readline()
                    new_content = f.read()
                    self._last_pos = f.tell()
                else:
                    f.seek(self._last_pos)
                    new_content = f.read()
                    self._last_pos = f.tell()
                
            if not new_content:
                return

            lines = new_content.splitlines()
            # インメモリキャッシュを更新 (最大1000行に制限)
            self._all_lines.extend(lines)
            if len(self._all_lines) > 1000:
                self._all_lines = self._all_lines[-Cache.LOG_MAX_LINES:]
            self._log_buffer.extend(lines)
            
            if not self._process_timer.isActive():
                self._process_timer.start()
                
        except (IOError, OSError) as e:
            self.log_text.appendPlainText(f"[ERROR] {tr('ログの読み込みに失敗しました: {0}').format(e)}")
        except Exception as e:
            self.log_text.appendPlainText(f"[ERROR] {tr('予期せぬエラーが発生しました: {0}').format(e)}")
            logger.error(f"Log viewer error: {e}", exc_info=True)
            
    def _process_log_buffer(self):
        if not self._log_buffer:
            self._process_timer.stop()
            return

        chunk = self._log_buffer[:Cache.LOG_CHUNK_SIZE]
        self._log_buffer = self._log_buffer[Cache.LOG_CHUNK_SIZE:]

        bar = self.log_text.verticalScrollBar()
        at_bottom = bar.value() == bar.maximum()

        lvl_idx    = self.level_combo.currentIndex()
        lvl_filter = self.level_combo.currentText()
        mod_idx    = self.module_combo.currentIndex()

        lines_to_add = []
        for line in chunk:
            # Level filter (index 0 = all)
            if lvl_idx != 0 and f"[{lvl_filter}]" not in line:
                continue
            # Module filter (index 0 = all) — index-based to avoid translation mismatch
            if   mod_idx == 1 and "__main__"      not in line: continue
            elif mod_idx == 2 and "hjks"           not in line: continue
            elif mod_idx == 3 and "imbalance"      not in line: continue
            elif mod_idx == 4 and "jkm"            not in line: continue
            elif mod_idx == 5 and "weather"        not in line: continue
            elif mod_idx == 6 and "power_reserve"  not in line: continue
            lines_to_add.append(line)

        if lines_to_add:
            # appendPlainText + QSyntaxHighlighter は appendHtml より大幅に高速
            # \n 結合で 1 回の呼び出しに集約してブロック生成コストを最小化する
            self.log_text.appendPlainText("\n".join(lines_to_add))

        if at_bottom:
            bar.setValue(bar.maximum())

    def _clear_logs(self):
        try:
            with open(self._log_file, 'w', encoding='utf-8') as f:
                f.write("")
            self.log_text.clear()
            self._last_pos = 0
            self._all_lines.clear()
            self._load_logs()
        except (IOError, OSError):
            pass