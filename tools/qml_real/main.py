"""LEE QtQuick (QML) — PowerReserve 페이지 실 데이터 prototype.

목적:
    실제 LEE 앱의 PowerReserve 페이지를 QML 로 재현하여 다음을 검증:
        1) 48×10 pivot 테이블의 색상 갱신 부드러움
        2) 24h line chart 의 렌더링 / 갱신 성능
        3) 5분 주기 refresh 시뮬레이션 (Python ↔ QML 데이터 bridge)
        4) 테마 전환 시 모든 셀이 동시에 색 보간되는지

비교:
    Qt Widgets PowerReserveWidget — 데이터 렌더 ~150ms + 테마 토글 7s freeze
    QML 기대 — 렌더 <50ms + 테마 토글 60fps 유지

실행:
    python tools/qml_real/main.py
"""
from __future__ import annotations

import random
import sys
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    Property, QObject, QUrl, Signal, Slot,
)
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine


# ── mock 데이터 — 실 앱의 PivotTable shape (48 slot × 10 area) ───────
_AREAS = ["北海道", "東北", "東京", "中部", "北陸", "関西", "中国", "四国", "九州", "沖縄"]


def _gen_reserve_rows(seed: int | None = None) -> list[list[Any]]:
    """48 slot × 10 area 의 예비율 % 데이터.

    실 PowerReserve 데이터 형태와 동일 — 시간 + 10 에리어 % 값.
    """
    if seed is not None:
        random.seed(seed)
    rows = []
    for h in range(24):
        for m in (0, 30):
            time_str = f"{h:02d}:{m:02d}"
            cells: list[Any] = [time_str]
            for _ in _AREAS:
                # 5~30% 사이 + 약간의 노이즈
                base = random.uniform(8.0, 25.0)
                cells.append(round(base, 1))
            rows.append(cells)
    return rows


class ThemeBridge(QObject):
    themeChanged = Signal(str)
    toggleStarted = Signal()
    toggleFinished = Signal(float)

    def __init__(self):
        super().__init__()
        self._theme = "dark"
        self._toggle_start_ns = 0

    @Property(str, notify=themeChanged)
    def theme(self) -> str:
        return self._theme

    @theme.setter
    def theme(self, value: str) -> None:
        if self._theme == value:
            return
        self._theme = value
        self.themeChanged.emit(value)

    @Slot()
    def toggle(self) -> None:
        self._toggle_start_ns = time.perf_counter_ns()
        self.toggleStarted.emit()
        self.theme = "light" if self._theme == "dark" else "dark"

    @Slot()
    def markToggleEnd(self) -> None:
        if self._toggle_start_ns == 0:
            return
        elapsed_ms = (time.perf_counter_ns() - self._toggle_start_ns) / 1_000_000.0
        self._toggle_start_ns = 0
        self.toggleFinished.emit(elapsed_ms)


class DataBridge(QObject):
    """Reserve 데이터 + refresh 갱신 시간 측정."""

    rowsChanged = Signal()
    refreshStarted = Signal()
    refreshFinished = Signal(float)   # ms

    def __init__(self):
        super().__init__()
        self._rows: list[list[Any]] = _gen_reserve_rows(seed=42)
        self._refresh_start_ns = 0

    @Property("QVariantList", notify=rowsChanged)
    def rows(self) -> list[list[Any]]:
        return self._rows

    @Property("QStringList", constant=True)
    def areas(self) -> list[str]:
        return _AREAS

    @Slot()
    def refresh(self) -> None:
        """랜덤 데이터 재생성 → rowsChanged 시그널 → QML 갱신 트리거."""
        self._refresh_start_ns = time.perf_counter_ns()
        self.refreshStarted.emit()
        self._rows = _gen_reserve_rows(seed=None)
        self.rowsChanged.emit()

    @Slot()
    def markRefreshEnd(self) -> None:
        if self._refresh_start_ns == 0:
            return
        elapsed_ms = (time.perf_counter_ns() - self._refresh_start_ns) / 1_000_000.0
        self._refresh_start_ns = 0
        self.refreshFinished.emit(elapsed_ms)


def main() -> int:
    app = QGuiApplication(sys.argv)
    app.setApplicationName("LEE QML — PowerReserve Real")

    engine = QQmlApplicationEngine()

    theme = ThemeBridge()
    data = DataBridge()
    theme.toggleFinished.connect(
        lambda ms: print(f"[QML] theme toggle elapsed: {ms:.1f}ms", flush=True)
    )
    data.refreshFinished.connect(
        lambda ms: print(f"[QML] refresh elapsed: {ms:.1f}ms", flush=True)
    )

    ctx = engine.rootContext()
    ctx.setContextProperty("themeBridge", theme)
    ctx.setContextProperty("dataBridge", data)

    qml_file = Path(__file__).parent / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))
    if not engine.rootObjects():
        print("QML 로드 실패", file=sys.stderr)
        return 1

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
