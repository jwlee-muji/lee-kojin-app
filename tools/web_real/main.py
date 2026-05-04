"""LEE Web (QWebEngine + ECharts) — PowerReserve 페이지 실 데이터 prototype.

목적:
    QML 과 동일한 PowerReserve 페이지를 웹 기반으로 재현하여 비교:
        - 차트 품질 / 부드러움 (ECharts 의 GPU 가속 vs QtCharts QML)
        - 480 cell 그리드 (CSS Grid) 의 색상 갱신
        - 테마 전환 (CSS 변수 + transition) 의 부드러움
        - Python ↔ JS QWebChannel bridge 의 IPC 비용

QML 과의 비교:
    동일한 mock 데이터 / 동일한 KPI / 동일한 pivot shape / 동일한 chart.

실행:
    python tools/web_real/main.py
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    Property, QObject, QUrl, Signal, Slot,
)
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication


_AREAS = ["北海道", "東北", "東京", "中部", "北陸", "関西", "中国", "四国", "九州", "沖縄"]


def _gen_reserve_rows(seed: int | None = None) -> list[list[Any]]:
    if seed is not None:
        random.seed(seed)
    rows = []
    for h in range(24):
        for m in (0, 30):
            time_str = f"{h:02d}:{m:02d}"
            cells: list[Any] = [time_str]
            for _ in _AREAS:
                base = random.uniform(8.0, 25.0)
                cells.append(round(base, 1))
            rows.append(cells)
    return rows


class Bridge(QObject):
    """JS 측에서 호출 가능한 Python API + signal."""

    # JS 측 markRefreshEnd 호출 시 Python 으로 elapsed ms 통보
    refreshFinished = Signal(float)
    toggleFinished = Signal(float)

    # 데이터 갱신 시 JS 로 새 rows 푸시
    dataPushed = Signal(str)   # JSON string (QVariant 직렬화 회피)

    def __init__(self):
        super().__init__()
        self._refresh_start_ns = 0
        self._toggle_start_ns = 0

    @Slot(result=str)
    def initial_data(self) -> str:
        rows = _gen_reserve_rows(seed=42)
        return json.dumps({"areas": _AREAS, "rows": rows})

    @Slot()
    def refresh(self) -> None:
        self._refresh_start_ns = time.perf_counter_ns()
        rows = _gen_reserve_rows(seed=None)
        self.dataPushed.emit(json.dumps({"areas": _AREAS, "rows": rows}))

    @Slot()
    def markRefreshEnd(self) -> None:
        if self._refresh_start_ns == 0:
            return
        elapsed_ms = (time.perf_counter_ns() - self._refresh_start_ns) / 1_000_000.0
        self._refresh_start_ns = 0
        self.refreshFinished.emit(elapsed_ms)

    @Slot()
    def toggleStart(self) -> None:
        self._toggle_start_ns = time.perf_counter_ns()

    @Slot()
    def markToggleEnd(self) -> None:
        if self._toggle_start_ns == 0:
            return
        elapsed_ms = (time.perf_counter_ns() - self._toggle_start_ns) / 1_000_000.0
        self._toggle_start_ns = 0
        self.toggleFinished.emit(elapsed_ms)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("LEE Web — PowerReserve Real")

    view = QWebEngineView()
    view.setWindowTitle("LEE Web — PowerReserve Real")
    view.resize(1200, 760)

    # WebChannel 셋업 — JS 의 qt.webChannelTransport 와 연결
    bridge = Bridge()
    bridge.refreshFinished.connect(
        lambda ms: print(f"[Web] refresh elapsed: {ms:.1f}ms", flush=True)
    )
    bridge.toggleFinished.connect(
        lambda ms: print(f"[Web] theme toggle elapsed: {ms:.1f}ms", flush=True)
    )

    channel = QWebChannel()
    channel.registerObject("bridge", bridge)
    view.page().setWebChannel(channel)

    # local file 권한 — qwebchannel.js 자동 inject
    settings = view.settings()
    settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
    settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
    settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)

    html_file = Path(__file__).parent / "index.html"
    view.load(QUrl.fromLocalFile(str(html_file)))
    view.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
