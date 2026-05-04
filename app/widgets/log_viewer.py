"""システムログビューア — Phase 5.12 リニューアル.

機能:
    - 上部툴바: 레벨 segment / 검색 / 期間 segment / 새로고침 / 실시간 토글 /
      ダウンロード / クリア
    - 본문: QTableView + LogTableModel (가상 스크롤, 10万+ 행 OK)
      · Time (mono) / Level (color pill 텍스트) / Module / Message
      · 행 클릭 → 하단 상세 패널 (전체 텍스트 + 멀티라인 traceback)
      · 우클릭 → 行をコピー / モジュールでフィルタ / 즐겨찾기
    - 데이터: app.log + app.log.1 + app.log.2 (RotatingFileHandler 출력)
    - 다운로드: 현재 필터된 로그를 .txt / .csv 로 내보내기

레벨 색상 (handoff/01-design-tokens.md):
    DEBUG → --fg-tertiary, INFO → --c-info, WARN → --c-warn, ERROR → --c-bad

기존 호환성:
    - main_window.py 가 import 하는 LogViewerWidget 클래스명 보존
"""
from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QAbstractTableModel, QFileSystemWatcher, QModelIndex, QPoint, QTimer,
    Qt, Signal,
)
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QIcon, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMenu, QSplitter, QStyle,
    QStyledItemDelegate, QTableView, QTextEdit, QVBoxLayout, QWidget,
)

from app.core.config import LOG_FILE
from app.core.events import bus
from app.core.i18n import tr
from app.ui.common import BaseWidget
from app.ui.components import (
    LeeButton, LeeDetailHeader, LeeDialog, LeePill, LeeSegment,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 토큰 (모듈 로컬)
# ──────────────────────────────────────────────────────────────────────
_C_LOG     = "#A8B0BD"   # 시스템 로그 accent (그레이)
_C_DEBUG   = "#6B7280"   # fg-tertiary
_C_INFO    = "#0A84FF"   # info
_C_WARN    = "#FF9F0A"   # warn
_C_ERROR   = "#FF453A"   # bad

_LEVEL_COLOR = {
    "DEBUG":   _C_DEBUG,
    "INFO":    _C_INFO,
    "WARNING": _C_WARN,
    "WARN":    _C_WARN,
    "ERROR":   _C_ERROR,
    "CRITICAL": _C_ERROR,
}

# 로그 라인 정규식: "2026-05-03 10:30:45 - [INFO] app.widgets.weather : message"
_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*-\s*\[(\w+)\]\s*([^\s:]+)\s*:\s*(.*)$"
)

_PERIOD_DELTA = {
    "1h":  timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d":  timedelta(days=7),
    "all": None,
}


# ──────────────────────────────────────────────────────────────────────
# 1. LogRecord — 파싱된 로그 1 레코드
# ──────────────────────────────────────────────────────────────────────
@dataclass
class LogRecord:
    ts: datetime          # 파싱된 시각
    ts_str: str           # 원본 시각 문자열
    level: str            # INFO / WARNING / ERROR / DEBUG
    module: str           # app.widgets.weather 등
    message: str          # 단일 행 메시지
    extra: list[str]      # 후행 라인 (traceback 등) — message 의 멀티라인 보충
    raw_lines: list[str]  # 디스크에서 읽은 원본 행들 (복사·내보내기용)


# ──────────────────────────────────────────────────────────────────────
# 2. LogParser — 회전 로그 파일 통합 파싱
# ──────────────────────────────────────────────────────────────────────
def _ordered_log_files(base: Path) -> list[Path]:
    """app.log + app.log.1 + app.log.2 를 시간순 (오래된 → 최신) 으로."""
    files: list[Path] = []
    for ext in (".2", ".1", ""):
        p = Path(str(base) + ext)
        if p.exists() and p.stat().st_size > 0:
            files.append(p)
    return files


def _parse_log_text(text: str) -> list[LogRecord]:
    """텍스트 → LogRecord 리스트. 멀티라인 (traceback) 은 직전 레코드의 extra 에 합침."""
    out: list[LogRecord] = []
    cur: Optional[LogRecord] = None
    for raw in text.splitlines():
        if not raw:
            continue
        m = _LINE_RE.match(raw)
        if m:
            ts_str, level, module, msg = m.groups()
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                ts = datetime.min
            cur = LogRecord(
                ts=ts, ts_str=ts_str, level=level.upper(),
                module=module, message=msg,
                extra=[], raw_lines=[raw],
            )
            out.append(cur)
        else:
            # 후속 라인 (traceback 등) → 직전 레코드에 추가
            if cur is not None:
                cur.extra.append(raw)
                cur.raw_lines.append(raw)
            else:
                # 첫 줄부터 매치 안 되면 별도 placeholder 레코드로
                cur = LogRecord(
                    ts=datetime.min, ts_str="", level="DEBUG",
                    module="?", message=raw,
                    extra=[], raw_lines=[raw],
                )
                out.append(cur)
    return out


def load_all_records(base: Path, max_records: int = 100_000) -> list[LogRecord]:
    """app.log* 전체 파싱 — 시간순 오래된 → 최신. 최신 max_records 만 유지."""
    text_parts: list[str] = []
    for p in _ordered_log_files(base):
        try:
            text_parts.append(p.read_text(encoding="utf-8", errors="replace"))
        except OSError as e:
            logger.warning(f"log file 읽기 실패: {p.name} {e}")
    if not text_parts:
        return []
    records = _parse_log_text("\n".join(text_parts))
    if len(records) > max_records:
        records = records[-max_records:]
    return records


# ──────────────────────────────────────────────────────────────────────
# 3. LogTableModel — QAbstractTableModel (가상 스크롤)
# ──────────────────────────────────────────────────────────────────────
COL_TIME, COL_LEVEL, COL_MODULE, COL_MESSAGE = range(4)
_HEADERS = ["時刻", "レベル", "モジュール", "メッセージ"]


class _LogRowDelegate(QStyledItemDelegate):
    """완전 커스텀 paint — QSS ::item:selected cascade 잔존 highlight 버그 회피.

    why custom paint:
        QSS 의 `::item:selected` + `setAlternatingRowColors(True)` 조합에서
        Qt stylesheet 엔진이 deselect 시 paint invalidation 을 누락 → 새 행
        클릭 후에도 이전 행 하이라이트가 잠시 남아있는 버그가 보고됨.
        delegate 가 bg/text 를 painter 로 직접 그려 Qt 의 cascade 우회.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark = True
        # 색상 — set_theme 에서 갱신
        self._bg_surface = QColor("#14161C")
        self._bg_alt     = QColor("#1F2128")
        self._fg_primary = QColor("#F2F4F7")
        self._sel_bg     = QColor("#2C313D")
        self._border     = QColor(255, 255, 255, 12)

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        if is_dark:
            self._bg_surface = QColor("#14161C")   # row 0 — 그대로 (블랙)
            self._bg_alt     = QColor("#1F2128")   # row 1 — 거의 블랙인 그레이
            self._fg_primary = QColor("#F2F4F7")
            self._sel_bg     = QColor("#2C313D")
            self._border     = QColor(255, 255, 255, 12)
        else:
            self._bg_surface = QColor("#FFFFFF")
            self._bg_alt     = QColor("#F7F8FA")
            self._fg_primary = QColor("#0B1220")
            self._sel_bg     = QColor("#DDE3EC")
            self._border     = QColor(11, 18, 32, 16)

    def paint(self, painter, option, index):
        rect = option.rect
        is_selected = bool(option.state & QStyle.State_Selected)
        is_alt = (index.row() % 2 == 1)

        # 1. Background — 선택 우선, 그 외 alt/surface
        if is_selected:
            bg = self._sel_bg
        elif is_alt:
            bg = self._bg_alt
        else:
            bg = self._bg_surface
        painter.fillRect(rect, bg)

        # 2. Text
        text = index.data(Qt.DisplayRole)
        if text is not None and str(text) != "":
            painter.save()
            font = index.data(Qt.FontRole)
            painter.setFont(font if font is not None else option.font)
            fg = index.data(Qt.ForegroundRole)
            if isinstance(fg, QBrush):
                painter.setPen(QPen(fg.color()))
            else:
                painter.setPen(QPen(self._fg_primary))
            text_rect = rect.adjusted(8, 0, -8, 0)
            painter.drawText(
                text_rect, int(Qt.AlignVCenter | Qt.AlignLeft), str(text),
            )
            painter.restore()

        # 3. row 하단 구분선 (subtle)
        painter.save()
        painter.setPen(QPen(self._border, 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.restore()


class LogTableModel(QAbstractTableModel):
    """가상 스크롤 모델. 전체 records + 표시용 인덱스 리스트 분리."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._records: list[LogRecord] = []
        self._visible_idx: list[int] = []
        self._is_dark = True
        # 글로벌 setStyleSheet cascade 시 hidden LogViewer 의 model.data() 가
        # 5+ 초간 polling 되어 테마 토글 freeze 의 30% 이상을 차지하던 문제 회피.
        # 위젯 hidden 시 set_active(False) 호출하면 rowCount=0 → Qt cascade 가
        # data() 를 호출하지 않음. 다시 show 시 set_active(True) 로 복원.
        # 초기값 False — 위젯이 처음 생성될 때는 hidden 상태이므로.
        self._active = False

    # ── 데이터 설정 / 필터 ─────────────────────────────────────
    def set_records(self, records: list[LogRecord]) -> None:
        self.beginResetModel()
        self._records = records
        self._visible_idx = list(range(len(records)))
        self.endResetModel()

    def append_records(self, new_records: list[LogRecord], max_total: int) -> None:
        """auto-tail — 새 레코드만 추가."""
        if not new_records:
            return
        if len(self._records) + len(new_records) > max_total:
            # 오래된 레코드 절단
            keep = max_total - len(new_records)
            if keep <= 0:
                self._records = list(new_records[-max_total:])
            else:
                self._records = self._records[-keep:] + list(new_records)
        else:
            self._records.extend(new_records)

    def all_records(self) -> list[LogRecord]:
        return self._records

    def set_visible(self, indices: list[int]) -> None:
        self.beginResetModel()
        self._visible_idx = list(indices)
        self.endResetModel()

    def visible_records(self) -> list[LogRecord]:
        return [self._records[i] for i in self._visible_idx if 0 <= i < len(self._records)]

    def record_at(self, row: int) -> Optional[LogRecord]:
        if 0 <= row < len(self._visible_idx):
            i = self._visible_idx[row]
            if 0 <= i < len(self._records):
                return self._records[i]
        return None

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        # 비활성 (hidden) 상태면 dataChanged emit 생략 — 어차피 view 가 paint
        # 안 하고 다음 set_active(True) 에서 endResetModel 이 view 를 새로 그림
        if self._records and self._active:
            top = self.index(0, 0)
            bot = self.index(self.rowCount() - 1, self.columnCount() - 1)
            self.dataChanged.emit(top, bot, [Qt.ForegroundRole, Qt.BackgroundRole])

    def set_active(self, active: bool) -> None:
        """위젯 visible 상태 동기화 — hidden 동안 rowCount=0 으로 cascade 차단.

        Qt 의 setStyleSheet 글로벌 cascade 가 모든 QTableView (hidden 포함) 의
        model 을 polling 하는 문제 회피. hidden→active=False 시 rowCount() 가
        0 을 반환하여 data() 호출이 발생하지 않음 → 테마 토글 5+ 초 회수.
        """
        if active == self._active:
            return
        self.beginResetModel()
        self._active = active
        self.endResetModel()

    # ── Qt overrides ───────────────────────────────────────────
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        if not self._active:
            return 0   # hidden 상태 — Qt cascade 가 data() 안 부르도록
        return len(self._visible_idx)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 4

    def headerData(self, section: int, orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return tr(_HEADERS[section]) if 0 <= section < 4 else ""
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        rec = self.record_at(index.row())
        if rec is None:
            return None
        col = index.column()
        if role == Qt.DisplayRole:
            if col == COL_TIME:    return rec.ts_str or "—"
            if col == COL_LEVEL:   return rec.level
            if col == COL_MODULE:  return rec.module
            if col == COL_MESSAGE:
                # 멀티라인 표시는 한 행만 — extra 가 있으면 +N 표기
                msg = rec.message
                if rec.extra:
                    msg = f"{msg}   …(+{len(rec.extra)} {tr('行')})"
                return msg
        if role == Qt.FontRole:
            if col == COL_TIME:
                return QFont("JetBrains Mono", 10)
            if col == COL_LEVEL:
                f = QFont("Inter", 10); f.setBold(True); return f
            if col == COL_MODULE:
                return QFont("JetBrains Mono", 10)
        if role == Qt.ForegroundRole:
            if col == COL_LEVEL:
                return QBrush(QColor(_LEVEL_COLOR.get(rec.level, _C_DEBUG)))
            if col == COL_TIME or col == COL_MODULE:
                return QBrush(QColor("#6B7280" if self._is_dark else "#8A93A6"))
        if role == Qt.ToolTipRole:
            if rec.extra:
                return "\n".join(rec.raw_lines)
            return rec.message
        return None


# ──────────────────────────────────────────────────────────────────────
# 4. LogViewerWidget — 메인 페이지
# ──────────────────────────────────────────────────────────────────────
_AUTO_TAIL_INTERVAL_MS = 1000   # 1초 polling
_MAX_RECORDS           = 100_000


class LogViewerWidget(BaseWidget):
    """システムログ — 시스템 로그 뷰어 (Phase 5.12)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_file: Path = LOG_FILE if isinstance(LOG_FILE, Path) else Path(LOG_FILE)
        if not self._log_file.exists():
            try:
                self._log_file.touch()
            except OSError:
                pass

        self._level_filter = "ALL"     # ALL / DEBUG / INFO / WARN / ERROR
        self._period_filter = "24h"    # 1h / 24h / 7d / all
        self._search = ""
        self._auto_tail = False
        self._favorites: set[str] = set()   # 즐겨찾기 message 시그니처
        self._last_sizes: dict[str, int] = {}  # 파일별 마지막 크기 (auto-tail 변화 감지)

        self._build_ui()

        # 모델
        self._model = LogTableModel(self)
        self._model.set_theme(self.is_dark)
        self.table.setModel(self._model)
        sm = self.table.selectionModel()
        if sm:
            sm.selectionChanged.connect(lambda *_: self._on_selection_changed())

        # 컬럼 폭
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(COL_TIME, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_LEVEL, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_MODULE, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_MESSAGE, QHeaderView.Stretch)

        # 파일 변화 감지 (즉시 반영 — auto-tail 켜져있을 때)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.addPath(str(self._log_file.absolute()))
        self._watcher.fileChanged.connect(self._on_file_changed)

        # auto-tail 폴링 (watcher 가 일부 환경에서 누락하므로 보조)
        self._tail_timer = QTimer(self)
        self._tail_timer.setInterval(_AUTO_TAIL_INTERVAL_MS)
        self._tail_timer.timeout.connect(self._on_tail_tick)

        # 검색 디바운스
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._apply_filters)

        QTimer.singleShot(50, self._reload_all)

    # ── UI 빌드 ───────────────────────────────────────────────
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 22); outer.setSpacing(14)

        # 1) DetailHeader
        self._header = LeeDetailHeader(
            title=tr("システムログ"),
            subtitle=tr("アプリのバックグラウンド動作ログをリアルタイム表示"),
            accent=_C_LOG,
            icon_qicon=QIcon(":/img/log.svg"),
            badge=None,
            show_export=False,
        )
        self._header.back_clicked.connect(lambda: bus.page_requested.emit(0))
        outer.addWidget(self._header)

        # 2) 툴바 카드
        toolbar = QFrame(); toolbar.setObjectName("logToolbar")
        tlb = QVBoxLayout(toolbar); tlb.setContentsMargins(14, 12, 14, 12); tlb.setSpacing(8)
        outer.addWidget(toolbar)

        # 첫 행 — 레벨 segment + 期間 segment + 새로고침 + auto-tail + export + clear
        row1 = QHBoxLayout(); row1.setSpacing(8)
        row1.addWidget(self._field_lbl(tr("レベル")))
        self.level_seg = LeeSegment(
            [("ALL", tr("全て")),
             ("DEBUG", "DEBUG"), ("INFO", "INFO"),
             ("WARN", "WARN"),  ("ERROR", "ERROR")],
            value="ALL", accent=_C_INFO,
        )
        self.level_seg.value_changed.connect(self._on_level_changed)
        row1.addWidget(self.level_seg)

        row1.addSpacing(10)
        row1.addWidget(self._field_lbl(tr("期間")))
        self.period_seg = LeeSegment(
            [("1h", "1h"), ("24h", "24h"), ("7d", "7d"), ("all", tr("全て"))],
            value="24h", accent=_C_LOG,
        )
        self.period_seg.value_changed.connect(self._on_period_changed)
        row1.addWidget(self.period_seg)

        row1.addStretch()

        self.btn_refresh = LeeButton("↻  " + tr("更新"), variant="secondary", size="sm")
        self.btn_refresh.clicked.connect(self._reload_all)
        row1.addWidget(self.btn_refresh)

        # auto-tail 토글
        self.btn_autotail = LeeButton("⏸  " + tr("リアルタイム OFF"), variant="secondary", size="sm")
        self.btn_autotail.setCheckable(True)
        self.btn_autotail.clicked.connect(self._toggle_autotail)
        row1.addWidget(self.btn_autotail)

        self.btn_export = LeeButton("⬇  " + tr("エクスポート"), variant="secondary", size="sm")
        self.btn_export.clicked.connect(self._export_filtered)
        row1.addWidget(self.btn_export)

        self.btn_clear = LeeButton("🗑  " + tr("クリア"), variant="destructive", size="sm")
        self.btn_clear.clicked.connect(self._clear_logs)
        row1.addWidget(self.btn_clear)

        tlb.addLayout(row1)

        # 둘째 행 — 검색 input + count pill
        row2 = QHBoxLayout(); row2.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("logSearch")
        self.search_input.setPlaceholderText("🔍  " + tr("検索 (メッセージ / モジュール)"))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedHeight(30)
        self.search_input.textChanged.connect(self._on_search_changed)
        row2.addWidget(self.search_input, 1)

        self._count_pill = LeePill("0 / 0", variant="info")
        row2.addWidget(self._count_pill)

        tlb.addLayout(row2)

        # 3) 본문 — 분할 (테이블 위 / 상세 아래)
        self._splitter = QSplitter(Qt.Vertical)
        self._splitter.setHandleWidth(1)
        outer.addWidget(self._splitter, 1)

        # 테이블
        self.table = QTableView()
        self.table.setObjectName("logTable")
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # setAlternatingRowColors(True) 미사용 — _LogRowDelegate 가 row index
        # 기준으로 alt color 직접 paint (QSS cascade 우회로 잔존 highlight 버그 fix)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        # row delegate — QSS ::item:selected cascade 우회 (잔존 highlight 버그 fix)
        self._row_delegate = _LogRowDelegate(self.table)
        self._row_delegate.set_theme(self.is_dark)
        self.table.setItemDelegate(self._row_delegate)
        self._splitter.addWidget(self.table)

        # 상세 패널
        detail_wrap = QFrame(); detail_wrap.setObjectName("logDetailWrap")
        dl = QVBoxLayout(detail_wrap); dl.setContentsMargins(14, 10, 14, 10); dl.setSpacing(6)

        head = QHBoxLayout(); head.setSpacing(8)
        self._detail_head = QLabel(tr("行を選択してください"))
        self._detail_head.setObjectName("logDetailHead")
        head.addWidget(self._detail_head, 1)
        self._level_pill = LeePill("—", variant="info")
        head.addWidget(self._level_pill)
        dl.addLayout(head)

        self.detail_view = QTextEdit()
        self.detail_view.setObjectName("logDetailView")
        self.detail_view.setReadOnly(True)
        self.detail_view.setLineWrapMode(QTextEdit.NoWrap)
        dl.addWidget(self.detail_view, 1)

        self._splitter.addWidget(detail_wrap)
        self._splitter.setStretchFactor(0, 4)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([580, 200])

    def _field_lbl(self, text: str) -> QLabel:
        lbl = QLabel(text); lbl.setObjectName("logFieldLbl")
        return lbl

    # ── 테마 ─────────────────────────────────────────────────
    def apply_theme_custom(self) -> None:
        self._header.set_theme(self.is_dark)
        self.level_seg.set_theme(self.is_dark)
        self.period_seg.set_theme(self.is_dark)
        self._model.set_theme(self.is_dark)
        self._row_delegate.set_theme(self.is_dark)
        self.table.viewport().update()   # delegate 색 즉시 반영
        self._apply_qss()

    def _apply_qss(self) -> None:
        d = self.is_dark
        bg_app        = "#0A0B0F" if d else "#F5F6F8"
        bg_surface    = "#14161C" if d else "#FFFFFF"
        bg_surface_2  = "#1B1E26" if d else "#F0F2F5"
        # 행 구분색 / 선택 색 → _LogRowDelegate 가 직접 paint
        # (QSS ::item:selected 잔존 highlight 버그 회피).
        # 다크: row=#14161C(블랙) / row_alt=#1F2128(거의 블랙 그레이)
        fg_primary    = "#F2F4F7" if d else "#0B1220"
        fg_secondary  = "#A8B0BD" if d else "#4A5567"
        fg_tertiary   = "#6B7280" if d else "#8A93A6"
        border_subtle = "rgba(255,255,255,0.06)" if d else "rgba(11,18,32,0.06)"
        border        = "rgba(255,255,255,0.10)" if d else "rgba(11,18,32,0.10)"

        self.setStyleSheet(f"""
            QFrame#logToolbar {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 14px;
            }}
            QLabel#logFieldLbl {{
                color: {fg_tertiary}; background: transparent;
                font-size: 11px; font-weight: 700;
                letter-spacing: 0.04em;
            }}
            QLineEdit#logSearch {{
                background: {bg_surface_2}; color: {fg_primary};
                border: 1px solid {border_subtle}; border-radius: 8px;
                padding: 0 12px; font-size: 12px;
            }}
            QLineEdit#logSearch:focus {{ border: 1px solid {_C_INFO}; }}

            QTableView#logTable {{
                background: {bg_surface};
                color: {fg_primary};
                border: 1px solid {border_subtle}; border-radius: 14px;
                gridline-color: transparent;
                font-size: 11.5px;
            }}
            /* alternate-background-color / ::item:selected 는 _LogRowDelegate
               가 직접 paint — QSS cascade 잔존 highlight 버그 회피 */
            QHeaderView::section {{
                background: {bg_surface_2};
                color: {fg_secondary};
                border: none;
                border-bottom: 1px solid {border_subtle};
                padding: 8px 10px;
                font-size: 11px; font-weight: 800;
                letter-spacing: 0.04em;
            }}

            QFrame#logDetailWrap {{
                background: {bg_surface};
                border: 1px solid {border_subtle}; border-radius: 14px;
            }}
            QLabel#logDetailHead {{
                color: {fg_secondary}; background: transparent;
                font-size: 12px; font-weight: 700;
            }}
            QTextEdit#logDetailView {{
                background: {bg_surface_2}; color: {fg_primary};
                border: 1px solid {border_subtle}; border-radius: 10px;
                padding: 10px 12px;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 11px;
                selection-background-color: {sel_bg};
            }}

            QSplitter::handle {{ background: transparent; }}
        """)

    # ── 데이터 로드 / 필터 ────────────────────────────────────
    def _reload_all(self) -> None:
        records = load_all_records(self._log_file, max_records=_MAX_RECORDS)
        self._model.set_records(records)
        # 마지막 파일 사이즈 캐싱
        self._last_sizes = {
            str(p): p.stat().st_size for p in _ordered_log_files(self._log_file)
        }
        self._apply_filters()
        # 기본 스크롤은 최신 로그 (하단) 로 — 모델 reset 직후엔 view 가 아직
        # row 위치를 잡지 못하므로 다음 event loop 에서 호출
        QTimer.singleShot(0, self.table.scrollToBottom)

    def _apply_filters(self) -> None:
        records = self._model.all_records()
        # 期間 필터
        delta = _PERIOD_DELTA.get(self._period_filter)
        cutoff = datetime.now() - delta if delta else None
        # 레벨 매핑
        lvl_set: Optional[set[str]] = None
        lf = self._level_filter.upper()
        if lf == "WARN":
            lvl_set = {"WARN", "WARNING"}
        elif lf == "ERROR":
            lvl_set = {"ERROR", "CRITICAL"}
        elif lf in ("DEBUG", "INFO"):
            lvl_set = {lf}
        # 검색어
        q = self._search.lower().strip()

        visible = []
        for i, r in enumerate(records):
            if cutoff and r.ts != datetime.min and r.ts < cutoff:
                continue
            if lvl_set is not None and r.level not in lvl_set:
                continue
            if q:
                if (q not in r.message.lower() and q not in r.module.lower()
                        and not any(q in e.lower() for e in r.extra)):
                    continue
            visible.append(i)

        self._model.set_visible(visible)
        self._count_pill.setText(f"{len(visible):,} / {len(records):,}")
        self._on_selection_changed()

        # 자동 스크롤 (auto-tail 이면 맨 아래)
        if self._auto_tail and self._model.rowCount() > 0:
            self.table.scrollToBottom()

    # ── 핸들러 ───────────────────────────────────────────────
    def _on_level_changed(self, key: str) -> None:
        self._level_filter = key
        self._apply_filters()

    def _on_period_changed(self, key: str) -> None:
        self._period_filter = key
        self._apply_filters()

    def _on_search_changed(self, text: str) -> None:
        self._search = text
        self._search_timer.start()

    def _toggle_autotail(self) -> None:
        self._auto_tail = self.btn_autotail.isChecked()
        if self._auto_tail:
            self.btn_autotail.setText("▶  " + tr("リアルタイム ON"))
            self._tail_timer.start()
            QTimer.singleShot(0, self.table.scrollToBottom)
        else:
            self.btn_autotail.setText("⏸  " + tr("リアルタイム OFF"))
            self._tail_timer.stop()

    def _on_file_changed(self, _path: str) -> None:
        # 파일 swap 후에는 watcher 가 트래킹을 잃을 수 있어 재등록
        if str(self._log_file) not in self._watcher.files():
            try:
                self._watcher.addPath(str(self._log_file.absolute()))
            except Exception:
                pass
        if self._auto_tail:
            self._poll_new_records()

    def _on_tail_tick(self) -> None:
        if self._auto_tail:
            self._poll_new_records()

    def _poll_new_records(self) -> None:
        """현재 app.log 의 변경분만 incremental 로 읽어 추가."""
        files = _ordered_log_files(self._log_file)
        any_new = False
        new_records: list[LogRecord] = []
        for p in files:
            key = str(p)
            try:
                size = p.stat().st_size
            except OSError:
                continue
            last = self._last_sizes.get(key, 0)
            if size < last:
                # 회전됨 — 전체 재로딩 안전 경로
                self._reload_all()
                return
            if size == last:
                continue
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(last)
                    chunk = f.read()
                self._last_sizes[key] = size
                if chunk:
                    new_records.extend(_parse_log_text(chunk))
                    any_new = True
            except OSError as e:
                logger.warning(f"log tail 실패 {p.name}: {e}")
        if any_new and new_records:
            self._model.append_records(new_records, max_total=_MAX_RECORDS)
            self._apply_filters()

    def _on_selection_changed(self) -> None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            self._detail_head.setText(tr("行を選択してください"))
            self._level_pill.setText("—")
            self.detail_view.clear()
            return
        rec = self._model.record_at(rows[0].row())
        if rec is None:
            return
        self._detail_head.setText(f"{rec.ts_str}  ·  {rec.module}")
        self._level_pill.setText(rec.level)
        # detail = message + extra (traceback 등)
        body = rec.message
        if rec.extra:
            body += "\n" + "\n".join(rec.extra)
        self.detail_view.setPlainText(body)

    def _on_context_menu(self, pos: QPoint) -> None:
        idx = self.table.indexAt(pos)
        if not idx.isValid():
            return
        rec = self._model.record_at(idx.row())
        if rec is None:
            return

        menu = QMenu(self)
        a_copy = QAction(tr("行をコピー"), menu)
        a_copy.triggered.connect(lambda: self._copy_to_clipboard("\n".join(rec.raw_lines)))
        menu.addAction(a_copy)

        a_copy_msg = QAction(tr("メッセージのみコピー"), menu)
        a_copy_msg.triggered.connect(lambda: self._copy_to_clipboard(rec.message))
        menu.addAction(a_copy_msg)

        menu.addSeparator()

        a_filter_mod = QAction(tr("「{0}」 でフィルタ").format(rec.module), menu)
        a_filter_mod.triggered.connect(lambda: self._set_search(rec.module))
        menu.addAction(a_filter_mod)

        a_filter_lvl = QAction(tr("レベル {0} のみ").format(rec.level), menu)
        a_filter_lvl.triggered.connect(lambda lv=rec.level: self._set_level(lv))
        menu.addAction(a_filter_lvl)

        menu.addSeparator()

        sig = self._fav_sig(rec)
        if sig in self._favorites:
            a_unfav = QAction("★  " + tr("お気に入り解除"), menu)
            a_unfav.triggered.connect(lambda: self._toggle_favorite(rec))
            menu.addAction(a_unfav)
        else:
            a_fav = QAction("☆  " + tr("お気に入りに追加"), menu)
            a_fav.triggered.connect(lambda: self._toggle_favorite(rec))
            menu.addAction(a_fav)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _copy_to_clipboard(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        bus.toast_requested.emit(tr("クリップボードにコピーしました"), "success")

    def _set_search(self, text: str) -> None:
        self.search_input.setText(text)

    def _set_level(self, level: str) -> None:
        # WARN / ERROR / INFO / DEBUG → segment key
        key = "WARN" if level in ("WARN", "WARNING") else level
        if key in ("DEBUG", "INFO", "WARN", "ERROR", "ALL"):
            self.level_seg.set_value(key, emit=True)

    @staticmethod
    def _fav_sig(rec: LogRecord) -> str:
        return f"{rec.module}|{rec.level}|{rec.message}"

    def _toggle_favorite(self, rec: LogRecord) -> None:
        sig = self._fav_sig(rec)
        if sig in self._favorites:
            self._favorites.discard(sig)
            bus.toast_requested.emit(tr("お気に入りから削除しました"), "info")
        else:
            self._favorites.add(sig)
            bus.toast_requested.emit(tr("お気に入りに追加しました"), "success")

    # ── 내보내기 / 클리어 ────────────────────────────────────
    def _export_filtered(self) -> None:
        records = self._model.visible_records()
        if not records:
            LeeDialog.info(tr("エクスポート"), tr("エクスポートするログがありません。"), parent=self)
            return
        path, ftype = QFileDialog.getSaveFileName(
            self, tr("ログをエクスポート"),
            f"lee_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            f"Text (*.txt);;CSV (*.csv)",
        )
        if not path:
            return
        try:
            if path.lower().endswith(".csv") or "csv" in ftype.lower():
                with open(path, "w", encoding="utf-8", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(["time", "level", "module", "message", "extra"])
                    for r in records:
                        w.writerow([r.ts_str, r.level, r.module, r.message,
                                    "\n".join(r.extra)])
            else:
                with open(path, "w", encoding="utf-8") as f:
                    for r in records:
                        f.write("\n".join(r.raw_lines))
                        f.write("\n")
            bus.toast_requested.emit(
                tr("✅ {0} 件をエクスポートしました").format(f"{len(records):,}"),
                "success",
            )
        except OSError as e:
            LeeDialog.error(tr("エラー"), tr("エクスポートに失敗しました: {0}").format(e), parent=self)

    def _clear_logs(self) -> None:
        if not LeeDialog.confirm(
            tr("ログのクリア"),
            tr("現在のログファイル ({0}) を空にします。よろしいですか?\n"
               "(回転バックアップ .1 .2 は残ります)").format(self._log_file.name),
            ok_text=tr("クリア"), destructive=True, parent=self,
        ):
            return
        try:
            with open(self._log_file, "w", encoding="utf-8") as f:
                f.write("")
            self._reload_all()
            bus.toast_requested.emit(tr("ログをクリアしました"), "info")
        except OSError as e:
            LeeDialog.error(tr("エラー"), str(e), parent=self)

    # ── 라이프사이클 ─────────────────────────────────────────
    def showEvent(self, event):
        super().showEvent(event)
        # hidden 동안 비활성이었던 model 재활성 — rowCount 정상 복원
        try:
            self._model.set_active(True)
        except Exception:
            pass
        # 표시될 때 selection 시그널 재연결 (model 이 reset 되면 selectionModel 이 교체될 수 있음)
        sm = self.table.selectionModel()
        if sm:
            try:
                sm.selectionChanged.disconnect()
            except (RuntimeError, TypeError):
                pass
            sm.selectionChanged.connect(lambda *_: self._on_selection_changed())

    def hideEvent(self, event):
        # 다른 페이지로 이동 시 model 비활성 — 글로벌 setStyleSheet cascade 시
        # data() polling 으로 인한 5+ 초 freeze 차단 (테마 토글 30% 이상 회수)
        try:
            self._model.set_active(False)
        except Exception:
            pass
        super().hideEvent(event)


# ──────────────────────────────────────────────────────────────────────
# LogViewerCard — 대시보드용 (시스템 상태 미니 카드)
# ──────────────────────────────────────────────────────────────────────
class LogViewerCard(QFrame):
    """대시보드 — 최근 ERROR/WARN 카운트 + 마지막 로그 1줄."""
    open_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logDashCard")
        self.setCursor(Qt.PointingHandCursor)
        self._is_dark = True
        self._build_ui()
        self._apply_qss()

    def _build_ui(self) -> None:
        v = QVBoxLayout(self); v.setContentsMargins(18, 16, 18, 16); v.setSpacing(10)

        head = QHBoxLayout(); head.setSpacing(10)
        from PySide6.QtGui import QIcon as _QI
        from app.ui.components import LeeIconTile as _LIT
        head.addWidget(_LIT(icon=_QI(":/img/log.svg"), color=_C_LOG, size=40, radius=10))
        title_box = QVBoxLayout(); title_box.setSpacing(2); title_box.setContentsMargins(0, 0, 0, 0)
        t = QLabel(tr("システムログ")); t.setObjectName("logDashTitle")
        s = QLabel(tr("バックグラウンド動作ログ")); s.setObjectName("logDashSub"); s.setWordWrap(True)
        title_box.addWidget(t); title_box.addWidget(s)
        head.addLayout(title_box, 1)

        self._lvl_pill = LeePill("OK", variant="info")
        head.addWidget(self._lvl_pill, 0, Qt.AlignTop)
        v.addLayout(head)

        self._stats_lbl = QLabel(tr("ERROR 0  ·  WARN 0"))
        self._stats_lbl.setObjectName("logDashStats")
        v.addWidget(self._stats_lbl)
        self._last_lbl = QLabel(tr("最終: —"))
        self._last_lbl.setObjectName("logDashLast")
        self._last_lbl.setWordWrap(True)
        v.addWidget(self._last_lbl)

    def refresh(self) -> None:
        """app.log* 에서 최근 통계 + 마지막 로그 1줄 표시."""
        try:
            from app.core.config import LOG_FILE
            base = LOG_FILE if isinstance(LOG_FILE, Path) else Path(LOG_FILE)
            records = load_all_records(base, max_records=2000)
        except Exception:
            records = []
        if not records:
            self._stats_lbl.setText(tr("ERROR 0  ·  WARN 0"))
            self._last_lbl.setText(tr("最終: —"))
            self._set_pill("OK", "info")
            return
        # 최근 24시간 통계
        cutoff = datetime.now() - timedelta(hours=24)
        recent = [r for r in records if r.ts >= cutoff]
        n_err  = sum(1 for r in recent if r.level in ("ERROR", "CRITICAL"))
        n_warn = sum(1 for r in recent if r.level in ("WARN", "WARNING"))
        self._stats_lbl.setText(f"ERROR {n_err}  ·  WARN {n_warn}  ·  ({tr('過去24時間')})")
        last = records[-1]
        self._last_lbl.setText(f"{last.ts_str[-8:]}  {last.module[:24]}  {last.message[:50]}")
        if n_err > 0:
            self._set_pill(tr("異常"), "error")
        elif n_warn > 0:
            self._set_pill(tr("注意"), "warning")
        else:
            self._set_pill("OK", "success")

    def _set_pill(self, text: str, variant: str) -> None:
        # LeePill variant 변경 — destructive/error/warning/info/success 중 매핑
        self._lvl_pill.setText(text)
        # variant 직접 세팅 (LeePill 내부 property)
        try:
            self._lvl_pill.setProperty("variant", variant)
            self._lvl_pill.style().unpolish(self._lvl_pill)
            self._lvl_pill.style().polish(self._lvl_pill)
        except Exception:
            pass

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    def _apply_qss(self) -> None:
        d = self._is_dark
        bg = "#14161C" if d else "#FFFFFF"
        fg_p = "#F2F4F7" if d else "#0B1220"
        fg_t = "#6B7280" if d else "#8A93A6"
        bs = "rgba(255,255,255,0.06)" if d else "rgba(11,18,32,0.06)"
        self.setStyleSheet(f"""
            QFrame#logDashCard {{
                background: {bg}; border: 1px solid {bs};
                border-left: 4px solid {_C_LOG};
                border-radius: 14px;
            }}
            QFrame#logDashCard:hover {{ border-color: {_C_LOG}; }}
            QLabel#logDashTitle {{
                color: {fg_p}; background: transparent;
                font-size: 14px; font-weight: 800;
            }}
            QLabel#logDashSub {{
                color: {fg_t}; background: transparent; font-size: 11px;
            }}
            QLabel#logDashStats {{
                color: {fg_p}; background: transparent;
                font-size: 12px; font-weight: 700;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QLabel#logDashLast {{
                color: {fg_t}; background: transparent;
                font-size: 10.5px;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
        """)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.open_requested.emit()
        super().mouseReleaseEvent(event)


__all__ = ["LogViewerWidget", "LogViewerCard", "LogRecord", "LogTableModel",
           "load_all_records"]
