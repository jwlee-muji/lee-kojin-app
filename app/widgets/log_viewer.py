import logging
import re
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QComboBox
)
from PySide6.QtCore import QFileSystemWatcher, QTimer
from PySide6.QtGui import QFont
from app.core.config import LOG_FILE

logger = logging.getLogger(__name__)


class LogViewerWidget(QWidget):
    """
    앱의 백그라운드 동작 상태(app.log)를 실시간으로 보여주는 시스템 로그 뷰어
    """
    def __init__(self):
        super().__init__()
        self.is_dark = True
        self._log_file = LOG_FILE
        self._last_pos = 0  # 마지막으로 읽은 파일 위치 캐싱
        self._log_buffer = []  # 대량 로그 처리용 버퍼
        
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
        title = QLabel(self.tr("システムログ (System Logs)"))
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        top.addWidget(title)
        top.addSpacing(15)
        
        self.module_combo = QComboBox()
        self.module_combo.addItems([
            self.tr("すべての機能"),
            self.tr("システム起動・終了"),
            self.tr("発電停止状況 (HJKS)"),
            self.tr("インバランス単価"),
            self.tr("JKM LNG 価格"),
            self.tr("全国天気予報"),
            self.tr("電力予備率 (OCCTO)")
        ])
        self.module_combo.currentIndexChanged.connect(self._on_filter_changed)
        top.addWidget(self.module_combo)
        
        self.level_combo = QComboBox()
        self.level_combo.addItems([self.tr("すべてのログレベル"), "INFO", "WARNING", "ERROR"])
        self.level_combo.currentIndexChanged.connect(self._on_filter_changed)
        top.addWidget(self.level_combo)
        
        top.addStretch()
        
        self.clear_btn = QPushButton(self.tr("ログ消去"))
        self.clear_btn.clicked.connect(self._clear_logs)
        
        refresh_btn = QPushButton(self.tr("手動更新"))
        refresh_btn.clicked.connect(self._load_logs)
        
        top.addWidget(self.clear_btn)
        top.addWidget(refresh_btn)
        layout.addLayout(top)
        
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 11))  # 텍스트 크기 키움
        self.log_text.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; padding: 10px; border: none;")
        self.log_text.setLineWrapMode(QPlainTextEdit.NoWrap)  # 줄바꿈 끄기 (가로 스크롤 허용)
        self.log_text.document().setMaximumBlockCount(1000)   # 메모리 누수 방지 (최대 1000줄 유지)
        layout.addWidget(self.log_text)

    def apply_theme_custom(self):
        is_dark = self.is_dark
        self.clear_btn.setStyleSheet(
            f"background-color: {'#5c1111' if is_dark else '#ffcccc'}; "
            f"color: {'#ffffff' if is_dark else '#cc0000'}; "
            f"border: 1px solid {'#801515' if is_dark else '#ff9999'};"
        )
        self.log_text.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; padding: 10px; border: none;")
        self._on_filter_changed()

    def _on_filter_changed(self):
        self.log_text.clear()
        self._last_pos = 0
        self._load_logs()

    def _load_logs(self):
        if not self._log_file.exists():
            return
            
        try:
            current_size = self._log_file.stat().st_size
            if current_size < self._last_pos:
                # 파일이 비워졌거나 잘린 경우 초기화
                self.log_text.clear()
                self._last_pos = 0

            if current_size == self._last_pos:
                return  # 추가된 변경 내용 없음
                
            with open(self._log_file, 'r', encoding='utf-8') as f:
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
            self._log_buffer.extend(lines)
            
            if not self._process_timer.isActive():
                self._process_timer.start()
                
        except (IOError, OSError) as e:
            self.log_text.appendHtml(f"<span style='color: #ff5555;'>ログの読み込みに失敗しました: {e}</span>")
        except Exception as e:
            self.log_text.appendHtml(f"<span style='color: #ff5555;'>予期せぬエラーが発生しました: {e}</span>")
            logger.error(f"Log viewer error: {e}", exc_info=True)
            
    def _process_log_buffer(self):
        if not self._log_buffer:
            self._process_timer.stop()
            return
            
        chunk = self._log_buffer[:200]  # 한 번에 200줄씩만 처리하여 UI 방어
        self._log_buffer = self._log_buffer[200:]
        
        bar = self.log_text.verticalScrollBar()
        at_bottom = bar.value() == bar.maximum()
        
        lvl_filter = self.level_combo.currentText()
        mod_filter = self.module_combo.currentText()
        
        self.log_text.setUpdatesEnabled(False)
        for line in chunk:
            safe_line = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
            if lvl_filter != "すべてのログレベル" and f"[{lvl_filter}]" not in safe_line: continue
                
            if mod_filter != "すべての機能":
                if mod_filter == "システム起動・終了" and "__main__" not in safe_line: continue
                elif mod_filter == "発電停止状況 (HJKS)" and "hjks" not in safe_line: continue
                elif mod_filter == "インバランス単価" and "imbalance" not in safe_line: continue
                elif mod_filter == "JKM LNG 価格" and "jkm" not in safe_line: continue
                elif mod_filter == "全国天気予報" and "weather" not in safe_line: continue
                elif mod_filter == "電力予備率 (OCCTO)" and "power_reserve" not in safe_line: continue

            match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - \[(.*?)\] (.*?)\s*:\s*(.*)", safe_line)
            if match:
                time_str, level_str, module_str, msg_str = match.groups()
                module_short = module_str.replace('app.widgets.', '').replace('app.', '')
                level_html = f"<span>[{level_str}]</span>"
                if level_str == 'ERROR': level_html = f"<span style='color: #ff5555; font-weight: bold;'>[{level_str}]</span>"
                elif level_str == 'WARNING': level_html = f"<span style='color: #ffb86c; font-weight: bold;'>[{level_str}]</span>"
                elif level_str == 'INFO': level_html = f"<span style='color: #8be9fd;'>[{level_str}]</span>"
                html_line = f"<span style='color: #777777;'>{time_str}</span> - {level_html} <span style='color: #bd93f9;'>[{module_short}]</span> <span style='color: #d4d4d4;'>{msg_str}</span>"
            else:
                html_line = f"<span style='color: #d4d4d4;'>{safe_line}</span>"
                
            self.log_text.appendHtml(html_line)
            
        self.log_text.setUpdatesEnabled(True)
        if at_bottom:
            bar.setValue(bar.maximum())

    def _clear_logs(self):
        try:
            with open(self._log_file, 'w', encoding='utf-8') as f:
                f.write("")
            self.log_text.clear()
            self._last_pos = 0
            self._load_logs()
        except (IOError, OSError):
            pass