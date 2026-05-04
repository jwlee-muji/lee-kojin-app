"""LEE QtQuick (QML) UI 프로토타입 — 옵션 B 검증.

목적:
    현재 Qt Widgets 기반 앱의 setStyleSheet cascade 한계 (테마 토글 ~7s)
    가 QtQuick / QML 의 GPU scenegraph 에서 어느 정도 개선되는지 직접 비교.

비교 포인트:
    1) 테마 토글 시간      — Widgets 7s → QML <100ms 기대
    2) 토글 중 FPS 유지    — Widgets 0fps freeze → QML 60fps 유지 기대
    3) 호버/스케일 애니메이션 — Widgets 짤짤이 → QML 부드럽게 기대

실행:
    python tools/qml_prototype/main.py

화면 구성:
    - 상단 헤더 (브랜드 + 테마 토글)
    - 3 KPI 카드 (Spot / Reserve / Imbalance — 더미 데이터)
    - 알림 리스트 (5건)
    - 우측 하단 FPS / 마지막 토글 시간 카운터
    - 좌측 하단 회전 애니메이션 (continuous — freeze 즉각 감지)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import (
    Property, QObject, QUrl, Signal, Slot,
)
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine


class ThemeBridge(QObject):
    """QML 에 노출되는 테마 상태 + 측정 헬퍼.

    QML 측에서 ``themeBridge.theme``, ``themeBridge.toggle()`` 등으로 접근.
    """

    themeChanged = Signal(str)
    toggleStarted = Signal()           # toggle 시작 시각 기록 트리거
    toggleFinished = Signal(float)     # ms 단위 elapsed

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
        """테마 토글 + 측정 시작."""
        self._toggle_start_ns = time.perf_counter_ns()
        self.toggleStarted.emit()
        self.theme = "light" if self._theme == "dark" else "dark"

    @Slot()
    def markToggleEnd(self) -> None:
        """QML 의 transition 완료 시점 (Behavior 애니메이션 끝) 호출."""
        if self._toggle_start_ns == 0:
            return
        elapsed_ms = (time.perf_counter_ns() - self._toggle_start_ns) / 1_000_000.0
        self._toggle_start_ns = 0
        self.toggleFinished.emit(elapsed_ms)


def main() -> int:
    app = QGuiApplication(sys.argv)
    app.setApplicationName("LEE QML Prototype")

    engine = QQmlApplicationEngine()

    bridge = ThemeBridge()
    # 디버그 — 콘솔에 토글 시간 출력
    bridge.toggleFinished.connect(
        lambda ms: print(f"[QML] theme toggle elapsed: {ms:.1f}ms", flush=True)
    )
    engine.rootContext().setContextProperty("themeBridge", bridge)

    qml_file = Path(__file__).parent / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        print("QML 로드 실패", file=sys.stderr)
        return 1

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
