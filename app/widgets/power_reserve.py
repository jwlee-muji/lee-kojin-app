"""電力予備率 ウィジェット — Phase 5.1 リニューアル v2.

디자인 출처: handoff/LEE_PROJECT/varA-detail-screens2.jsx ReserveDetail
디자인 1:1 구현 — Phase 1 atom 들 (LeeDetailHeader / LeeKPI / LeeDateInput /
LeePivotTable / LeeChartFrame / LeeReserveBars / LeeBigChart / LeePill) 활용.

레이아웃:
    ┌──────────────────────────────────────────────────────────────────┐
    │ [←] [icon] 電力予備率   OCCTO 全国 10エリア·30分単位      [badge] │  DetailHeader
    ├──────────────────────────────────────────────────────────────────┤
    │ KPI: 最低予備率 / 全国平均 / 最大供給力 / 想定需要ピーク (4 cards) │
    ├──────────────────────────────────────────────────────────────────┤
    │ [日付] | [危険] [注意] [通常] [安定]            [📋コピー][CSV] │
    ├──────────────────────────────────────────────────────────────────┤
    │ PivotTable (30분 × 10에리어, 컬러 셀)                              │
    ├──────────────────────────────────────────────────────────────────┤
    │ [10エリア 予備率比較 (Bars 1.4fr)]    [需給バランス予測 東京 (Big 1fr)]│
    └──────────────────────────────────────────────────────────────────┘

[기존 기능 보존]
  - FetchPowerReserveWorker / FetchPowerReserveHistoryWorker
  - DB 저장 + 인덱스 + 자동 history fetch (100일 미만 시)
  - bus.occto_updated.emit (대시보드 동기화)
  - 알림 (低予備率) → MainWindow.add_notification + 트레이
  - 자동 갱신 (settings.reserve_interval)
  - CSV 내보내기 + 그래프/테이블 코피
  - 날짜 선택 (◀ ▶ 今日)
  - 30분×에리어 매트릭스 (PivotTable 가 ヒートマップ 대체)
"""
from __future__ import annotations

import re
import csv
import logging
from datetime import datetime, timedelta
from typing import Optional

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal, QTimer, QDate
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QScrollArea,
    QSizePolicy, QSplitter, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from app.api.market.power_reserve import (
    FetchPowerReserveWorker, FetchPowerReserveHistoryWorker,
)
from app.core.events import bus
from app.core.i18n import tr
from app.ui.common import BaseWidget
from app.ui.components import (
    LeeButton, LeeCard, LeeDialog, LeePill,
    LeeIconTile, LeeKPI, LeeDetailHeader, LeeChartFrame,
    LeeBigChart, LeePivotTable, LeeReserveBars, LeeDateInput,
    LeeCountValue,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 영역 매핑 / DB 스키마 / 토큰 (기존 보존)
# ──────────────────────────────────────────────────────────────────────
_AREA_COL = {
    "北海道": "hokkaido", "東北": "tohoku",   "東京": "tokyo",
    "中部":   "chubu",    "北陸": "hokuriku", "関西": "kansai",
    "中国":   "chugoku",  "四国": "shikoku",  "九州": "kyushu",  "沖縄": "okinawa",
}
_ALL_AREA_COLS = list(_AREA_COL.values())

_CREATE_POWER_RESERVE = """
    CREATE TABLE IF NOT EXISTS power_reserve (
        date     TEXT NOT NULL,
        time     TEXT NOT NULL,
        hokkaido REAL, tohoku REAL, tokyo   REAL,
        chubu    REAL, hokuriku REAL, kansai REAL,
        chugoku  REAL, shikoku  REAL, kyushu REAL, okinawa REAL,
        PRIMARY KEY (date, time)
    )
"""

# 디자인 토큰
_C_POWER = "#5B8DEF"
_C_OK    = "#30D158"
_C_WARN  = "#FF9F0A"
_C_BAD   = "#FF453A"

_DEFAULT_LOW   = 8.0
_DEFAULT_WARN  = 10.0


# ──────────────────────────────────────────────────────────────────────
# 데이터 처리 헬퍼
# ──────────────────────────────────────────────────────────────────────
def _parse_time_minutes(time_str: str) -> int:
    try:
        m = re.search(r'(\d{1,2}):(\d{2})', time_str or "")
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))
    except (ValueError, AttributeError):
        pass
    return -1


def _parse_value(cell) -> Optional[float]:
    try:
        return float(str(cell).replace('%', '').replace(',', '').strip())
    except (ValueError, AttributeError):
        return None


def _extract_areas(headers, rows):
    """rows → ({area: [val_at_each_slot]}, [time_str])."""
    area_names = headers[1:] if headers else []
    areas = {a: [] for a in area_names}
    times = []
    for row in rows:
        if not row or len(row) < 2:
            continue
        time_str = str(row[0]) if row[0] else ""
        times.append(time_str)
        for ci, area in enumerate(area_names, 1):
            v = _parse_value(row[ci]) if ci < len(row) else None
            areas[area].append(v)
    return areas, times


def _area_stats(areas: dict[str, list]) -> list[dict]:
    """{area: [vals]} → [{area, min, max, avg, cur, status}]."""
    stats = []
    for area, vals in areas.items():
        valid = [v for v in vals if v is not None]
        if not valid:
            continue
        mn = min(valid); mx = max(valid); avg = sum(valid) / len(valid)
        # 최신 (None 아닌 마지막)
        cur = next((v for v in reversed(vals) if v is not None), None)
        if mn < 3:
            status = "bad"
        elif mn < 8:
            status = "warn"
        else:
            status = "ok"
        stats.append({"area": area, "min": mn, "max": mx, "avg": avg, "cur": cur, "status": status})
    return stats


def _alert_kind(value: Optional[float], low_th: float, warn_th: float) -> str:
    if value is None:
        return "unknown"
    if value <= low_th:
        return "critical"
    if value <= warn_th:
        return "warn"
    return "normal"


# ──────────────────────────────────────────────────────────────────────
# A. PowerReserveCard — 대시보드용 카드 (모킹업 1:1, varA-cards.jsx ReserveCard)
# ──────────────────────────────────────────────────────────────────────
class _ReserveBarRow(QWidget):
    """단일 가로 바 행 — 라벨 / 컬러 트랙 / 값 (3 컬럼 그리드)."""

    def __init__(self, area: str, value: float, max_value: float, status: str, *, is_dark: bool):
        super().__init__()
        self._area = area
        self._value = value
        self._max_value = max(max_value, 1.0)
        self._status = status
        self._is_dark = is_dark
        self.setFixedHeight(20)

    def _color(self) -> str:
        if self._status == "bad":
            return _C_BAD
        if self._status == "warn":
            return _C_WARN
        return _C_POWER

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QColor, QFont
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width(); h = self.height()
        # 그리드 컬럼: 44 / flex / 56  (column-gap 10)
        col_label_w  = 44
        col_value_w  = 56
        gap = 10
        bar_x0 = col_label_w + gap
        bar_x1 = w - col_value_w - gap
        bar_h = 8
        bar_y = h // 2 - bar_h // 2

        # 라벨 (에리어명) — bad 면 빨강, 그 외는 fg_primary
        if self._status == "bad":
            label_color = QColor(_C_BAD)
        else:
            label_color = QColor("#F2F4F7" if self._is_dark else "#0B1220")
        p.setPen(label_color)
        f = p.font(); f.setPointSize(9); f.setWeight(QFont.Weight.Bold); p.setFont(f)
        p.drawText(0, 0, col_label_w, h, Qt.AlignVCenter | Qt.AlignLeft, self._area)

        # 트랙 배경
        track_qc = QColor("#1B1E26") if self._is_dark else QColor("#F0F2F5")
        p.setPen(Qt.NoPen)
        p.setBrush(track_qc)
        p.drawRoundedRect(bar_x0, bar_y, bar_x1 - bar_x0, bar_h, bar_h / 2, bar_h / 2)

        # 채움
        c = self._color()
        pct = max(0.0, min(1.0, self._value / self._max_value))
        fill_w = int((bar_x1 - bar_x0) * pct)
        if fill_w > 0:
            p.setBrush(QColor(c))
            p.drawRoundedRect(bar_x0, bar_y, fill_w, bar_h, bar_h / 2, bar_h / 2)

        # 값 (mono, 컬러)
        p.setPen(QColor(c))
        f2 = p.font(); f2.setFamily("JetBrains Mono"); f2.setPointSize(9); f2.setWeight(QFont.Weight.Bold)
        p.setFont(f2)
        p.drawText(bar_x1 + gap, 0, col_value_w, h, Qt.AlignVCenter | Qt.AlignRight, f"{self._value:.1f}")
        p.end()


class PowerReserveCard(LeeCard):
    """予備率 카드 — varA-cards.jsx ReserveCard 1:1.

    레이아웃:
        ┌─────────────────────────────────────────────────────┐
        │ [icon] 本日の最低予備率              [worst.value %]│
        │        東京エリア · 監視中                            │
        ├─────────────────────────────────────────────────────┤
        │ エリア   予備率                                  値 (%)│
        │ ─────────────────────────────────────────────────── │
        │ 東京   ████████████░░░░░░░░░░░░░░               7.2 │
        │ 北海道 ██████████░░░░░░░░░░░░░░░░░               5.8 │
        │ ...                                                  │
        └─────────────────────────────────────────────────────┘
    """

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(accent_color="power", interactive=True, parent=parent)
        # 헤더 (~50) + 컬럼헤더 (~22) + sep (1) + rows 5 × (20+6) - 6 + padding (16+16) ≈ 235
        # 여유 있게 260
        self.setMinimumHeight(260)
        from PySide6.QtWidgets import QSizePolicy as _QSP
        self.setSizePolicy(_QSP.Expanding, _QSP.MinimumExpanding)
        self._is_dark = True
        self._stats: list[dict] = []  # 마지막으로 받은 area stats

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(0)

        # ── 헤더: icon + (title/sub) + 큰 숫자 ───────────────────
        header = QHBoxLayout()
        header.setSpacing(12)
        header.setContentsMargins(0, 0, 0, 12)

        self._icon = LeeIconTile(
            icon=QIcon(":/img/power.svg"),
            color=_C_POWER, size=40, radius=12,
        )
        header.addWidget(self._icon, 0, Qt.AlignTop)

        title_box = QVBoxLayout(); title_box.setSpacing(2); title_box.setContentsMargins(0, 0, 0, 0)
        self._title_lbl = QLabel(tr("本日の最低予備率"))
        self._title_lbl.setObjectName("prCardTitle")
        self._sub_lbl = QLabel(tr("OCCTO 監視中"))
        self._sub_lbl.setObjectName("prCardSub")
        title_box.addWidget(self._title_lbl)
        title_box.addWidget(self._sub_lbl)
        header.addLayout(title_box, 1)

        # 큰 숫자 + 단위
        num_box = QHBoxLayout(); num_box.setSpacing(3); num_box.setAlignment(Qt.AlignBaseline)
        self._value_lbl = LeeCountValue(formatter=lambda v: f"{v:.1f}")
        self._value_lbl.setObjectName("prCardValue")
        self._unit_lbl = QLabel("%"); self._unit_lbl.setObjectName("prCardUnit")
        num_box.addWidget(self._value_lbl, 0, Qt.AlignBaseline)
        num_box.addWidget(self._unit_lbl, 0, Qt.AlignBaseline)
        header.addLayout(num_box, 0)

        layout.addLayout(header)

        # ── 컬럼 헤더 ─────────────────────────────────────────────
        col_hdr = QWidget()
        col_hdr_layout = QHBoxLayout(col_hdr)
        col_hdr_layout.setContentsMargins(0, 0, 0, 4)
        col_hdr_layout.setSpacing(10)
        lbl_area  = QLabel(tr("エリア"));   lbl_area.setObjectName("prColHdr"); lbl_area.setFixedWidth(44)
        lbl_pct   = QLabel(tr("予備率"));   lbl_pct.setObjectName("prColHdr")
        lbl_value = QLabel(tr("値 (%)"));   lbl_value.setObjectName("prColHdr"); lbl_value.setFixedWidth(56)
        lbl_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        col_hdr_layout.addWidget(lbl_area)
        col_hdr_layout.addWidget(lbl_pct, 1)
        col_hdr_layout.addWidget(lbl_value)
        layout.addWidget(col_hdr)

        # 헤더 아래 1px 라인
        sep = QFrame(); sep.setObjectName("prColSep"); sep.setFixedHeight(1)
        layout.addWidget(sep)
        self._sep = sep

        # ── Bar rows 컨테이너 ─────────────────────────────────────
        self._rows_box = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_box)
        self._rows_layout.setContentsMargins(0, 5, 0, 0)
        self._rows_layout.setSpacing(4)
        layout.addWidget(self._rows_box, 1)

        self._apply_local_qss()
        self._render_empty()

    # ── 외부 API ─────────────────────────────────────────────
    def set_areas(self, stats: list[dict]) -> None:
        """stats: [{area, min, max, avg, cur, status}, ...] (PowerReserveWidget._area_stats)"""
        if not stats:
            self.set_no_data()
            return
        self._stats = list(stats)
        # 정렬: min 값 오름차순 (가장 낮은 = 가장 위험)
        sorted_stats = sorted(self._stats, key=lambda s: s["min"])
        worst = sorted_stats[0]

        # 헤더 갱신
        self._value_lbl.set_value(float(worst["min"]))
        self._sub_lbl.setText(self._sub_text(worst))
        self._apply_value_color(worst["status"])

        # 표시 대상 5개: warn/bad 가 3개 이상이면 그것 우선, 아니면 worst 5
        focus = [s for s in sorted_stats if s["status"] != "ok"][:5]
        display = focus if len(focus) >= 3 else sorted_stats[:5]

        # 막대의 max 값 — 표시 대상 중 가장 큰 min 값 또는 16 (모킹업과 동일)
        max_v = max(max((s["min"] for s in display), default=16.0), 16.0)

        # 기존 행 제거
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

        # 새 행 추가
        for s in display:
            row = _ReserveBarRow(
                area=tr(str(s["area"])),
                value=float(s["min"]),
                max_value=max_v,
                status=str(s["status"]),
                is_dark=self._is_dark,
            )
            self._rows_layout.addWidget(row)

    def set_no_data(self) -> None:
        self._stats = []
        self._value_lbl.set_value(0.0, animate=False)
        self._value_lbl.setText("--")
        self._sub_lbl.setText(tr("データなし"))
        self._render_empty()
        self._apply_value_color("ok")  # 회색

    # 하위호환: 기존 dashboard.update_occto 가 호출하던 시그너처
    def set_value(self, current: Optional[float], sub_text: str = "") -> None:
        if current is None:
            self.set_no_data(); return
        # set_areas 가 이미 호출됐으면 큰 숫자만 갱신, 아니면 fallback
        self._value_lbl.set_value(float(current))
        if sub_text:
            self._sub_lbl.setText(sub_text)

    # 하위호환: dashboard.update_occto_baseline 의 delta 호출 — 카드에 delta 영역이 없으므로 무시
    def set_delta(self, delta: Optional[float]) -> None:
        return  # 새 디자인은 delta 미사용 (worst area 정보로 대체)

    def set_sparkline(self, values: list[float]) -> None:
        return  # 새 디자인은 sparkline 미사용

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_local_qss()
        # 행도 다시 그리기
        if self._stats:
            self.set_areas(self._stats)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    # ── 내부 ─────────────────────────────────────────────────
    @staticmethod
    def _sub_text(worst: dict) -> str:
        area = tr(str(worst["area"]))
        if worst["status"] == "bad":
            return tr("{0}エリア · OCCTO 注意喚起").format(area)
        if worst["status"] == "warn":
            return tr("{0}エリア · OCCTO 監視中").format(area)
        return tr("{0}エリア · OCCTO 監視中").format(area)

    def _apply_value_color(self, status: str) -> None:
        color = _C_POWER
        if status == "bad":
            color = _C_BAD
        elif status == "warn":
            color = _C_WARN
        self._value_lbl.setStyleSheet(
            f"QLabel#prCardValue {{"
            f"  font-family: 'JetBrains Mono', 'Consolas', monospace;"
            f"  font-size: 32px; font-weight: 800;"
            f"  color: {color}; background: transparent;"
            f"  letter-spacing: -0.02em;"
            f"}}"
        )

    def _render_empty(self) -> None:
        # rows 비우기
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

    def _apply_local_qss(self) -> None:
        is_dark = self._is_dark
        fg_primary   = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary  = "#6B7280" if is_dark else "#8A93A6"
        border_subtle = "rgba(255,255,255,0.06)" if is_dark else "rgba(11,18,32,0.06)"
        self.setStyleSheet(f"""
            QLabel#prCardTitle {{
                font-size: 13px; font-weight: 600;
                color: {fg_secondary}; background: transparent;
            }}
            QLabel#prCardSub {{
                font-size: 11px;
                color: {fg_tertiary}; background: transparent;
            }}
            QLabel#prCardUnit {{
                font-size: 13px; font-weight: 600;
                color: {fg_tertiary}; background: transparent;
                padding-bottom: 4px;
            }}
            QLabel#prColHdr {{
                font-size: 9px; font-weight: 700;
                color: {fg_tertiary}; background: transparent;
                letter-spacing: 0.08em;
            }}
            QFrame#prColSep {{
                background: {border_subtle};
                border: none;
            }}
        """)
        # 큰 숫자 색상은 _apply_value_color 가 별도로 적용


# ──────────────────────────────────────────────────────────────────────
# B. PowerReserveWidget — 디테일 페이지 (디자인 1:1)
# ──────────────────────────────────────────────────────────────────────
class PowerReserveWidget(BaseWidget):
    """予備率 디테일 페이지 — varA-detail-screens2.jsx ReserveDetail 1:1 구현."""

    def __init__(self):
        super().__init__()
        self.worker: Optional[FetchPowerReserveWorker] = None
        self._history_worker: Optional[FetchPowerReserveHistoryWorker] = None
        self._alerted_low_reserve: set = set()
        self._last_headers: list[str] = []
        self._last_rows: list[list[str]] = []
        self._yesterday_min: Optional[float] = None

        self._build_ui()

        interval = int(self.settings.get("reserve_interval", 5))
        self.setup_timer(interval, self.fetch_data)
        QTimer.singleShot(2250, self.fetch_data)
        QTimer.singleShot(13000, self._auto_fetch_history)

    # ──────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        # 페이지 자체는 ScrollArea 만 담는 빈 컨테이너 (배경 토큰화)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setObjectName("prPageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer.addWidget(scroll, 1)

        content = QWidget()
        content.setObjectName("prPageContent")
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(18)

        # 1) DetailHeader
        from PySide6.QtGui import QIcon as _QIcon
        self._header = LeeDetailHeader(
            title=tr("電力予備率"),
            subtitle=tr("OCCTO 全国 10エリア · 30分単位"),
            accent=_C_POWER,
            icon_qicon=_QIcon(":/img/power.svg"),
            badge="",
            show_export=True,
        )
        self._header.back_clicked.connect(lambda: bus.page_requested.emit(0))
        self._header.export_clicked.connect(self._export_csv)
        root.addWidget(self._header)

        # 2) KPI Row (4 cards)
        kpi_row = QHBoxLayout(); kpi_row.setSpacing(12)
        self._kpi_min    = LeeKPI(tr("最低予備率"),    value="--", unit="%",  color=_C_BAD,    sub="")
        self._kpi_avg    = LeeKPI(tr("全国平均"),      value="--", unit="%",  color=_C_POWER,  sub=tr("安定圏内"))
        self._kpi_supply = LeeKPI(tr("最大供給力"),    value="174.8", unit="GW", sub=tr("火力 + 原子力 + 再エネ"))
        self._kpi_demand = LeeKPI(tr("想定需要ピーク"), value="163.9", unit="GW", sub=tr("18:30 想定"))
        kpi_row.addWidget(self._kpi_min, 1)
        kpi_row.addWidget(self._kpi_avg, 1)
        kpi_row.addWidget(self._kpi_supply, 1)
        kpi_row.addWidget(self._kpi_demand, 1)
        root.addLayout(kpi_row)

        # 3) 필터 row
        root.addWidget(self._build_filter_row())

        # 4) PivotTable (고정 min) — splitter 제거, 페이지 ScrollArea 가 처리
        self._pivot = LeePivotTable(
            mode="reserve", accent=_C_POWER, height=320,
            show_stats=False, row_header_label=tr("時刻"),
        )
        self._pivot.setMinimumHeight(360)
        root.addWidget(self._pivot)

        # 5) Charts row (Bars + BigChart, 가로) — 고정 min height
        charts_wrap = QWidget()
        charts_wrap.setLayout(self._build_charts_row())
        charts_wrap.setMinimumHeight(320)
        root.addWidget(charts_wrap)

        # 첫 fetch 동안 pivot 영역에 shimmer skeleton
        from app.ui.components.skeleton import install_skeleton_overlay
        self._pivot_skel = install_skeleton_overlay(self._pivot)

    def _build_filter_row(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("prFilterBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        # 날짜 선택
        self._date_input = LeeDateInput(accent=_C_POWER, show_today_btn=True)
        self._date_input.date_changed.connect(self.fetch_data)
        h.addWidget(self._date_input)

        # 세퍼레이터
        sep = QFrame()
        sep.setObjectName("prFilterSep")
        sep.setFixedSize(1, 22)
        h.addWidget(sep)

        # threshold pills
        h.addWidget(LeePill(tr("⚠ 危険 〜3%"),  variant="danger"))
        h.addWidget(LeePill(tr("注意 3〜8%"),   variant="warn"))
        h.addWidget(LeePill(tr("通常 8〜15%"),  variant="info"))
        h.addWidget(LeePill(tr("安定 15%+"),    variant="success"))

        h.addStretch()

        # 액션 버튼들
        self._refresh_indicator = QLabel(self._refresh_indicator_text(int(self.settings.get("reserve_interval", 5))))
        self._refresh_indicator.setObjectName("prRefreshIndicator")
        h.addWidget(self._refresh_indicator)

        self.refresh_btn = LeeButton(tr("更新"), variant="secondary", size="sm")
        self.refresh_btn.clicked.connect(self.fetch_data)
        h.addWidget(self.refresh_btn)

        self.history_btn = LeeButton(tr("履歴取得"), variant="secondary", size="sm")
        self.history_btn.clicked.connect(self.fetch_history)
        h.addWidget(self.history_btn)

        self.copy_btn = LeeButton(tr("📋 コピー"), variant="secondary", size="sm")
        self.copy_btn.clicked.connect(self._copy_summary)
        h.addWidget(self.copy_btn)

        self.csv_btn = LeeButton(tr("⬇ CSV"), variant="secondary", size="sm")
        self.csv_btn.clicked.connect(self._export_csv)
        h.addWidget(self.csv_btn)

        # 상태 라벨
        self.status_label = QLabel(tr("待機中"))
        self.status_label.setObjectName("prStatusLabel")
        h.addWidget(self.status_label)

        self._filter_bar = bar
        self._apply_filter_qss()
        return bar

    def _build_charts_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(14)

        # Left: 10エリア 比較 (Bars)
        self._bars_frame = LeeChartFrame(
            tr("10エリア 予備率比較 (現在値)"),
            subtitle="",
            accent=_C_POWER,
        )
        self._bars = LeeReserveBars(
            max_value=25.0,
            thresholds=[(_DEFAULT_LOW, _C_WARN), (3.0, _C_BAD)],
        )
        self._bars_frame.set_content(self._bars)

        # Right: 需給バランス予測 東京 (BigChart)
        self._tokyo_frame = LeeChartFrame(
            tr("需給バランス予測"),
            subtitle=tr("東京エリア"),
            accent=_C_POWER,
        )
        self._tokyo_chart = LeeBigChart(
            color=_C_POWER, y_unit="%", x_label=tr("時刻"),
            guide_lines=[(_DEFAULT_LOW, _C_WARN), (3.0, _C_BAD)],
        )
        self._tokyo_chart.setMinimumHeight(160)  # splitter 가 동적 조정 가능하게
        self._tokyo_frame.set_content(self._tokyo_chart)

        row.addWidget(self._bars_frame, 14)
        row.addWidget(self._tokyo_frame, 10)
        return row

    @staticmethod
    def _refresh_indicator_text(interval_min: int) -> str:
        return f"●  {interval_min}{tr('分ごと')}"

    def _apply_filter_qss(self) -> None:
        is_dark = self.is_dark
        fg_secondary = "#A8B0BD" if is_dark else "#4A5567"
        sep_color    = "rgba(255,255,255,0.10)" if is_dark else "rgba(11,18,32,0.10)"
        self._filter_bar.setStyleSheet(f"""
            QFrame#prFilterBar {{ background: transparent; }}
            QFrame#prFilterSep {{ background: {sep_color}; border: none; }}
            QLabel#prRefreshIndicator {{
                font-size: 11px; font-weight: 600;
                color: {_C_OK};
                background: rgba(48,209,88,0.10);
                border: 1px solid rgba(48,209,88,0.25);
                border-radius: 999px;
                padding: 3px 10px;
            }}
            QLabel#prStatusLabel {{
                font-size: 11px;
                color: {fg_secondary};
                background: transparent;
                min-width: 60px;
            }}
        """)

    # ──────────────────────────────────────────────────────────
    # BaseWidget hooks
    # ──────────────────────────────────────────────────────────
    def apply_theme_custom(self) -> None:
        d = self.is_dark
        self._header.set_theme(d)
        for k in (self._kpi_min, self._kpi_avg, self._kpi_supply, self._kpi_demand):
            k.set_theme(d)
        self._date_input.set_theme(d)
        self._pivot.set_theme(d)
        self._bars_frame.set_theme(d)
        self._tokyo_frame.set_theme(d)
        self._bars.set_theme(d)
        self._tokyo_chart.set_theme(d)
        self._apply_page_qss()
        self._apply_filter_qss()

    def _apply_page_qss(self) -> None:
        """ScrollArea / page content 의 배경을 bg_app 토큰으로 정렬."""
        bg_app = "#0A0B0F" if self.is_dark else "#F5F6F8"
        self.setStyleSheet(f"""
            PowerReserveWidget {{ background: {bg_app}; }}
            QScrollArea#prPageScroll {{
                background: {bg_app};
                border: none;
            }}
            QWidget#prPageContent {{ background: {bg_app}; }}
        """)

    def apply_settings_custom(self) -> None:
        interval = int(self.settings.get("reserve_interval", 5))
        self.update_timer_interval(interval)
        if hasattr(self, "_refresh_indicator"):
            self._refresh_indicator.setText(self._refresh_indicator_text(interval))
        if self._last_headers and self._last_rows:
            self._render(self._last_headers, self._last_rows)

    def set_loading(self, is_loading: bool) -> None:
        super().set_loading(is_loading, self._pivot)

    # ──────────────────────────────────────────────────────────
    # 데이터 취득
    # ──────────────────────────────────────────────────────────
    def fetch_data(self) -> None:
        if not self.check_online_status():
            return
        try:
            if self.worker and self.worker.isRunning():
                return
        except RuntimeError:
            self.worker = None

        selected_date = self._date_input.date().toString("yyyy-MM-dd")
        self.refresh_btn.setEnabled(False)
        self.set_loading(True)
        self.status_label.setText(tr("更新中..."))
        self.worker = FetchPowerReserveWorker(selected_date)
        self.worker.data_fetched.connect(self._on_data_fetched)
        self.worker.error.connect(self._handle_error)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()
        self.track_worker(self.worker)

    def _handle_error(self, err) -> None:
        self.set_loading(False)
        self.status_label.setText(tr("更新失敗: {0}").format(err))
        self.refresh_btn.setEnabled(True)
        bus.toast_requested.emit(tr("⚠ 予備率 取得失敗"), "error")

    def _on_data_fetched(self, headers: list[str], rows: list[list[str]]) -> None:
        self.set_loading(False)
        self._last_headers = headers
        self._last_rows = rows
        self.refresh_btn.setEnabled(True)
        self.status_label.setText(tr("更新完了"))
        self._render(headers, rows)
        date_str = self._date_input.date().toString("yyyy-MM-dd")
        self._save_to_db(date_str, headers, rows)
        QTimer.singleShot(0, self._refresh_yesterday_baseline)

    # ──────────────────────────────────────────────────────────
    # 렌더링 (PivotTable + Bars + BigChart + KPI + DetailHeader)
    # ──────────────────────────────────────────────────────────
    def _render(self, headers: list[str], rows: list[list[str]]) -> None:
        low_th  = float(self.settings.get("reserve_low",  _DEFAULT_LOW))
        warn_th = float(self.settings.get("reserve_warn", _DEFAULT_WARN))

        # 첫 데이터 도착 시 skeleton 제거
        if rows and getattr(self, "_pivot_skel", None) is not None:
            self._pivot_skel.stop(); self._pivot_skel.deleteLater(); self._pivot_skel = None

        # 1) PivotTable
        self._pivot.set_data(headers, rows)

        # 2) 데이터 통계
        areas, _times = _extract_areas(headers, rows)
        stats = _area_stats(areas)
        if not stats:
            self._kpi_min.set_value("--", unit="%", sub="", color=_C_BAD)
            self._kpi_avg.set_value("--", unit="%", sub="", color=_C_POWER)
            self._header.set_badge(None)
            self._bars.set_data([])
            self._tokyo_chart.set_data([], [])
            return

        # 3) Worst (최저 예비율) → KPI 最低 + DetailHeader badge
        worst = min(stats, key=lambda s: s["min"])
        self._kpi_min.set_value(
            f"{worst['min']:.1f}", unit="%",
            color=_C_BAD if worst["status"] == "bad" else (_C_WARN if worst["status"] == "warn" else _C_POWER),
            sub=tr("{0}エリア (警戒水準)").format(tr(worst["area"])) if worst["status"] == "bad"
                else tr("{0}エリア").format(tr(worst["area"])),
        )

        # 4) 全国 평균
        national_avg = sum(s["avg"] for s in stats) / len(stats)
        self._kpi_avg.set_value(
            f"{national_avg:.1f}", unit="%", color=_C_POWER,
            sub=tr("安定圏内") if national_avg > 12 else tr("注意水準"),
        )

        # 5) DetailHeader badge
        if worst["status"] in ("warn", "bad"):
            self._header.set_badge(
                f"{tr(worst['area'])} {worst['min']:.1f}% {tr('警戒')}"
            )
        else:
            self._header.set_badge(None)

        # 6) ReserveBars (각 에리어 현재값으로 비교)
        bars_data = []
        for s in stats:
            cur = s.get("cur") or s["avg"]
            bars_data.append((tr(s["area"]), cur, s["status"]))
        self._bars.set_data(bars_data)

        # 7) BigChart — 도쿄 시계열
        tokyo_vals = areas.get("東京", [])
        x_minutes, y_values = [], []
        for time_str, val in zip(_times, tokyo_vals):
            tmin = _parse_time_minutes(time_str)
            if tmin >= 0 and val is not None:
                x_minutes.append(tmin)
                y_values.append(val)
        self._tokyo_chart.set_data(x_minutes, y_values)

        # 8) bus.occto_updated emit (대시보드 동기화 — 본일 최저)
        today_min_info = self._find_today_min(headers, rows)
        if today_min_info:
            min_time, min_area, min_val = today_min_info
            bus.occto_updated.emit(min_time, tr(min_area), min_val)
            # delta 표시용 baseline (오늘 최저 vs 어제 최저)
            yest = self._yesterday_min if self._yesterday_min is not None else float("nan")
            bus.occto_baseline.emit(float(min_val), float(yest))

        # 8') 全エリア 통계 — ReserveCard 의 5-row bars 용
        # stats: [{area, min, max, avg, cur, status}, ...]
        bus.occto_areas.emit([dict(s) for s in stats])

        # 9) 알림 (低予備率)
        new_alerts = self._collect_new_alerts(headers, rows, low_th)
        self._raise_alerts_if_any(new_alerts, low_th)

    def _find_today_min(self, headers, rows) -> Optional[tuple[str, str, float]]:
        """본일 최저값이 발생한 슬롯 (time_str, area_name, value)."""
        selected_qd = self._date_input.date()
        is_today = selected_qd == QDate.currentDate()
        if not is_today:
            return None
        best: Optional[tuple[str, str, float]] = None
        area_names = headers[1:] if headers else []
        for row in rows:
            if not row or len(row) < 2:
                continue
            time_str = str(row[0]) if row[0] else ""
            for ci, area in enumerate(area_names, 1):
                v = _parse_value(row[ci]) if ci < len(row) else None
                if v is None:
                    continue
                if best is None or v < best[2]:
                    best = (time_str, area, v)
        return best

    def _collect_new_alerts(
        self, headers, rows, low_th: float,
    ) -> list[tuple[str, str, float]]:
        selected_qd = self._date_input.date()
        is_today = selected_qd == QDate.currentDate()
        if not is_today:
            return []
        new_alerts = []
        area_names = headers[1:] if headers else []
        for row in rows:
            if not row or len(row) < 2:
                continue
            time_str = str(row[0]) if row[0] else ""
            for ci, area in enumerate(area_names, 1):
                v = _parse_value(row[ci]) if ci < len(row) else None
                if v is None or v > low_th:
                    continue
                key = (time_str, area)
                if key not in self._alerted_low_reserve:
                    self._alerted_low_reserve.add(key)
                    new_alerts.append((time_str, area, v))
        return new_alerts

    def _raise_alerts_if_any(self, new_alerts: list[tuple[str, str, float]], low_th: float) -> None:
        if not new_alerts:
            return
        timestamp   = datetime.now().strftime("%H:%M:%S")
        total_count = len(new_alerts)
        display     = new_alerts[:5]
        lines = "\n".join(f"  {t}  |  {tr(a)}:  {v:.1f}%" for t, a, v in display)
        if len(new_alerts) > 5:
            lines += "\n  " + tr("...他 {0}件の警告があります").format(len(new_alerts) - 5)
        prefix = tr("本日のデータに予備率{0}%以下のコマが 【計 {1}件】 発生しています。").format(low_th, total_count)
        plain  = prefix + f"\n\n{lines}"
        title  = tr("⚠ 予備率警告 (計 {0}件) - {1}").format(total_count, timestamp)

        main_window = next(
            (w for w in QApplication.topLevelWidgets() if w.inherits("QMainWindow")), None
        )
        if main_window and hasattr(main_window, 'add_notification'):
            main_window.add_notification(title, plain)
        # 트레이 balloon — 메인 윈도우 숨김 + cooldown 통과 시만
        if (main_window and main_window.isHidden()
                and hasattr(main_window, 'tray_icon')
                and getattr(main_window, '_can_show_tray_balloon', lambda: True)()):
            main_window.tray_icon.showMessage(
                title, plain, QApplication.instance().windowIcon(), 10000
            )

    # ──────────────────────────────────────────────────────────
    # CSV / 코피
    # ──────────────────────────────────────────────────────────
    def _copy_summary(self) -> None:
        """전체 PivotTable 데이터를 TSV 로 클립보드에 복사 (Excel paste 가능)."""
        if not self._last_headers or not self._last_rows:
            return
        lines = ["\t".join(self._last_headers)]
        for r in self._last_rows:
            lines.append("\t".join(str(c) for c in r))
        QApplication.clipboard().setText("\n".join(lines))
        bus.toast_requested.emit(tr("テーブルをコピーしました"), "success")

    def _export_csv(self) -> None:
        if not self._last_rows:
            LeeDialog.error(tr("エラー"), tr("保存するデータがありません。"), parent=self)
            return
        date_str = self._date_input.date().toString('yyyyMMdd')
        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("CSV保存"), f"OCCTO_予備率_{date_str}.csv", "CSV Files (*.csv)"
        )
        if not file_path:
            return
        try:
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(self._last_headers)
                for row in self._last_rows:
                    writer.writerow(row)
            LeeDialog.info(
                tr("完了"),
                tr("CSVファイルとして保存しました。\nExcelで開くことができます。"),
                parent=self,
            )
        except (IOError, csv.Error) as e:
            LeeDialog.error(tr("エラー"), tr("保存に失敗しました:\n{0}").format(e), parent=self)

    # ──────────────────────────────────────────────────────────
    # DB / 履歴 (기존 보존)
    # ──────────────────────────────────────────────────────────
    def _save_to_db(self, date_str: str, headers: list[str], rows: list[list[str]]) -> None:
        try:
            from app.core.config import DB_POWER_RESERVE
            from app.core.database import get_db_connection
            col_indices: dict[str, int] = {}
            for i, h in enumerate(headers[1:], 1):
                col = _AREA_COL.get(h)
                if col:
                    col_indices[col] = i
            records = []
            for row in rows:
                if not row:
                    continue
                rec = [date_str, row[0]]
                for col in _ALL_AREA_COLS:
                    idx = col_indices.get(col)
                    val = None
                    if idx is not None and idx < len(row):
                        val = _parse_value(row[idx])
                    rec.append(val)
                records.append(rec)
            cols_sql = "date, time, " + ", ".join(_ALL_AREA_COLS)
            ph = ", ".join(["?"] * (2 + len(_ALL_AREA_COLS)))
            with get_db_connection(DB_POWER_RESERVE) as conn:
                conn.execute(_CREATE_POWER_RESERVE)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_pr_date ON power_reserve(date)")
                conn.executemany(
                    f"INSERT OR REPLACE INTO power_reserve ({cols_sql}) VALUES ({ph})",
                    records,
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"予備率DB保存エラー: {e}")

    def _refresh_yesterday_baseline(self) -> None:
        try:
            from app.core.config import DB_POWER_RESERVE
            from app.core.database import get_db_connection
            if not DB_POWER_RESERVE.exists():
                return
            yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
            cols = ", ".join(_ALL_AREA_COLS)
            with get_db_connection(DB_POWER_RESERVE) as conn:
                rows = conn.execute(
                    f"SELECT {cols} FROM power_reserve WHERE date = ?",
                    (yesterday,),
                ).fetchall()
            vals = [v for row in rows for v in row if v is not None]
            self._yesterday_min = min(vals) if vals else None
            # baseline 갱신 후 today min 이 이미 있으면 카드에 delta 재emit
            today_info = self._find_today_min(self._last_headers, self._last_rows)
            if today_info and self._yesterday_min is not None:
                _, _, today_min = today_info
                bus.occto_baseline.emit(float(today_min), float(self._yesterday_min))
        except Exception as e:
            logger.debug(f"昨日 baseline fetch error (무시): {e}")

    def _auto_fetch_history(self) -> None:
        try:
            from app.core.config import DB_POWER_RESERVE
            from app.core.database import get_db_connection
            if not DB_POWER_RESERVE.exists():
                self.fetch_history(); return
            with get_db_connection(DB_POWER_RESERVE) as conn:
                count = conn.execute("SELECT COUNT(DISTINCT date) FROM power_reserve").fetchone()[0]
            if count < 100:
                self.fetch_history()
        except Exception as e:
            logger.debug(f"予備率履歴自動取得チェックエラー: {e}")

    def fetch_history(self) -> None:
        if not self.check_online_status():
            return
        try:
            if self._history_worker and self._history_worker.isRunning():
                return
        except RuntimeError:
            self._history_worker = None
        self.history_btn.setEnabled(False)
        self.status_label.setText(tr("履歴取得中..."))
        self._history_worker = FetchPowerReserveHistoryWorker()
        self._history_worker.progress.connect(lambda m: self.status_label.setText(m))
        self._history_worker.finished.connect(self._on_history_success)
        self._history_worker.error.connect(self._on_history_error)
        self._history_worker.finished.connect(self._history_worker.deleteLater)
        self._history_worker.start()
        self.track_worker(self._history_worker)

    def _on_history_success(self, msg: str) -> None:
        self.history_btn.setEnabled(True)
        self.status_label.setText(msg)

    def _on_history_error(self, err: str) -> None:
        self.history_btn.setEnabled(True)
        self.status_label.setText(tr("履歴取得失敗"))
        LeeDialog.error(tr("エラー"), err, parent=self)
