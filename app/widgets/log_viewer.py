import logging
import re
from pathlib import Path
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QComboBox
)
from PySide6.QtCore import QFileSystemWatcher, QTimer
from PySide6.QtGui import QFont
from app.core.config import LOG_FILE
from app.core.i18n import tr
from app.ui.theme import UIColors
from app.ui.common import BaseWidget

logger = logging.getLogger(__name__)


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
        self._process_timer.setInterval(50)  # 50ms 간격으로 Chunk 처리
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
        self.log_text.setFont(QFont("Consolas", 11))  # 텍스트 크기 키움
        _lc = UIColors.get_log_colors(self.is_dark)
        self.log_text.setStyleSheet(
            f"background-color: {_lc['bg']}; color: {_lc['text']}; padding: 10px; border: none;"
        )
        self.log_text.setLineWrapMode(QPlainTextEdit.NoWrap)  # 줄바꿈 끄기 (가로 스크롤 허용)
        self.log_text.document().setMaximumBlockCount(1000)   # 메모리 누수 방지 (최대 1000줄 유지)
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
        # テーマ変更: ディスク再読み込みなしにキャッシュから再描画
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
                MAX_READ_BYTES = 500 * 1024
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
                self._all_lines = self._all_lines[-1000:]
            self._log_buffer.extend(lines)
            
            if not self._process_timer.isActive():
                self._process_timer.start()
                
        except (IOError, OSError) as e:
            err_c = UIColors.get_log_colors(self.is_dark)['error']
            self.log_text.appendHtml(f"<span style='color: {err_c};'>{tr('ログの読み込みに失敗しました: {0}').format(e)}</span>")
        except Exception as e:
            err_c = UIColors.get_log_colors(self.is_dark)['error']
            self.log_text.appendHtml(f"<span style='color: {err_c};'>{tr('予期せぬエラーが発生しました: {0}').format(e)}</span>")
            logger.error(f"Log viewer error: {e}", exc_info=True)
            
    def _process_log_buffer(self):
        if not self._log_buffer:
            self._process_timer.stop()
            return
            
        chunk = self._log_buffer[:200]  # 한 번에 200줄씩만 처리하여 UI 방어
        self._log_buffer = self._log_buffer[200:]
        
        bar = self.log_text.verticalScrollBar()
        at_bottom = bar.value() == bar.maximum()
        
        lvl_idx = self.level_combo.currentIndex()
        lvl_filter = self.level_combo.currentText()
        mod_idx = self.module_combo.currentIndex()
        lc = UIColors.get_log_colors(self.is_dark)

        html_parts = []
        for line in chunk:
            safe_line = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

            # Level filter (index 0 = all)
            if lvl_idx != 0 and f"[{lvl_filter}]" not in safe_line:
                continue

            # Module filter (index 0 = all) — index-based to avoid translation mismatch
            if mod_idx == 1 and "__main__" not in safe_line: continue
            elif mod_idx == 2 and "hjks" not in safe_line: continue
            elif mod_idx == 3 and "imbalance" not in safe_line: continue
            elif mod_idx == 4 and "jkm" not in safe_line: continue
            elif mod_idx == 5 and "weather" not in safe_line: continue
            elif mod_idx == 6 and "power_reserve" not in safe_line: continue

            match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - \[(.*?)\] (.*?)\s*:\s*(.*)", safe_line)
            if match:
                time_str, level_str, module_str, msg_str = match.groups()
                module_short = module_str.replace('app.widgets.', '').replace('app.', '')
                if level_str == 'ERROR':
                    level_html = f"<span style='color: {lc['error']}; font-weight: bold;'>[{level_str}]</span>"
                elif level_str == 'WARNING':
                    level_html = f"<span style='color: {lc['warning']}; font-weight: bold;'>[{level_str}]</span>"
                elif level_str == 'INFO':
                    level_html = f"<span style='color: {lc['info']};'>[{level_str}]</span>"
                else:
                    level_html = f"<span>[{level_str}]</span>"
                html_parts.append(
                    f"<span style='color: {lc['time']};'>{time_str}</span> - "
                    f"{level_html} "
                    f"<span style='color: {lc['module']};'>[{module_short}]</span> "
                    f"<span style='color: {lc['text']};'>{msg_str}</span>"
                )
            else:
                html_parts.append(f"<span style='color: {lc['text']};'>{safe_line}</span>")

        if html_parts:
            # 全行を <p> で包んで一度に挿入 — appendHtml の N 回呼び出しを 1 回に削減
            combined = "".join(
                f"<p style='margin:0; padding:0; white-space:pre;'>{h}</p>"
                for h in html_parts
            )
            self.log_text.appendHtml(combined)
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