"""경량 UI 인터랙션 프로파일러.

활성화:
    LEE_PROFILE=1 python main.py            (Windows: set LEE_PROFILE=1)
    LEE_PROFILE=1 python main.py            (PowerShell: $env:LEE_PROFILE=1)

비활성 시 모든 함수가 no-op 으로 동작 (런타임 비용 0).

출력:
    1) 콘솔: 매 인터랙션 종료 시 한 줄 요약
    2) APP_DIR/profile.log: 동일 내용 + 타임스탬프 누적
    3) (옵션) pyinstrument 가 설치되어 있고 인터랙션이 임계 초과 시 콜 트리 포함

사용 패턴:
    # 컨텍스트 매니저 — 임의의 블록
    from app.core.profiler import measure_block
    with measure_block("my_op"):
        do_heavy_thing()

    # 메서드 데코레이터
    from app.core.profiler import measure_method
    class Foo:
        @measure_method("foo.refresh", slow_ms=80)
        def refresh(self): ...

    # 이벤트 루프 지연 모니터 — main thread 블로킹 자동 감지
    from app.core.profiler import EventLoopLatencyMonitor
    self._latmon = EventLoopLatencyMonitor(self)
    self._latmon.start()

핵심 임계값:
    - 16ms = 60fps 1프레임 budget. 초과 시 ⚠️
    - 64ms = 4프레임 (눈에 띄게 끊김). 초과 시 🐢
    - slow_ms 인자로 케이스별 조정 가능 (단발 작업은 100~200ms 가 정상일 수 있음)
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QElapsedTimer, QObject, QTimer

logger = logging.getLogger(__name__)

ENABLED = os.environ.get("LEE_PROFILE", "0") == "1"

# pyinstrument — 옵션. 설치 시 slow path 의 콜 트리 자동 캡처
try:
    from pyinstrument import Profiler as _PyInst   # type: ignore
    _HAS_PYINST = True
except ImportError:
    _HAS_PYINST = False


_log_file_handle = None


def _log_path() -> Path:
    from app.core.config import APP_DIR
    return APP_DIR / "profile.log"


def _emit(line: str) -> None:
    """콘솔 + 파일에 한 줄 출력."""
    if not ENABLED:
        return
    global _log_file_handle
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    full = f"[{ts}] {line}"
    try:
        print(full, flush=True)
    except Exception:
        pass
    try:
        if _log_file_handle is None:
            p = _log_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            _log_file_handle = open(p, "a", encoding="utf-8")
            _log_file_handle.write(
                f"\n=== profile session start {datetime.now().isoformat()} ===\n"
            )
        _log_file_handle.write(full + "\n")
        _log_file_handle.flush()
    except Exception:
        pass


def _marker(elapsed_ms: float, slow_ms: float) -> str:
    """임계값 대비 elapsed 색상 마커."""
    if elapsed_ms >= slow_ms * 4:
        return "🐢"
    if elapsed_ms >= slow_ms:
        return "⚠️ "
    return "✓ "


@contextmanager
def measure_block(name: str, slow_ms: float = 16.0):
    """블록 단위 시간 측정.

    Args:
        name: 출력에 표시될 식별자
        slow_ms: 이 임계 이상이면 ⚠️ 경고 + (pyinstrument 있으면) 콜 트리 캡처
    """
    if not ENABLED:
        yield
        return

    timer = QElapsedTimer()
    timer.start()
    pyinst = None
    if _HAS_PYINST:
        try:
            pyinst = _PyInst()
            pyinst.start()
        except Exception:
            pyinst = None

    try:
        yield
    finally:
        elapsed = timer.elapsed()
        marker = _marker(elapsed, slow_ms)
        _emit(f"{marker}{name}: {elapsed}ms")

        # 임계 2배 초과 + pyinstrument 가능 시 콜 트리 캡처
        if pyinst is not None:
            try:
                pyinst.stop()
                if elapsed >= slow_ms * 2:
                    txt = pyinst.output_text(unicode=True, color=False, show_all=False)
                    _emit(f"--- pyinstrument [{name}] {elapsed}ms ---\n{txt}\n--- end ---")
            except Exception:
                pass


def measure_method(name: Optional[str] = None, slow_ms: float = 16.0):
    """메서드를 measure_block 으로 감싸는 데코레이터."""
    def deco(fn):
        nm = name or f"{fn.__module__}.{fn.__qualname__}"

        @wraps(fn)
        def wrapper(*args, **kwargs):
            with measure_block(nm, slow_ms=slow_ms):
                return fn(*args, **kwargs)
        return wrapper
    return deco


class EventLoopLatencyMonitor(QObject):
    """메인 스레드 블로킹을 자동 감지.

    매 expected_ms (기본 16ms = 60fps) 마다 QTimer 가 fire 되어야 정상.
    실제 fire 간격이 expected + threshold 를 초과하면 stutter 로 카운트.
    Python / Qt main thread 가 무거운 작업으로 막혔다는 뜻.

    사용:
        mon = EventLoopLatencyMonitor(parent_qobject)
        mon.start()  # LEE_PROFILE=1 일 때만 실제 동작
        ...
        mon.stop()   # 통계 출력
    """

    def __init__(self, parent: Optional[QObject] = None,
                 expected_ms: int = 16,
                 stutter_threshold_ms: int = 50):
        super().__init__(parent)
        self._expected = expected_ms
        self._threshold = stutter_threshold_ms
        self._timer = QTimer(self)
        self._timer.setInterval(expected_ms)
        self._timer.timeout.connect(self._tick)
        self._elapsed = QElapsedTimer()
        self._last = 0
        self._stutter_count = 0
        self._max_jitter = 0
        self._total_jitter = 0
        self._tick_count = 0

    def start(self) -> None:
        if not ENABLED:
            return
        self._elapsed.start()
        self._last = self._elapsed.elapsed()
        self._stutter_count = 0
        self._max_jitter = 0
        self._total_jitter = 0
        self._tick_count = 0
        self._timer.start()
        _emit(f"⏱  EventLoopLatencyMonitor: started ({self._expected}ms tick, "
              f"stutter≥{self._threshold}ms)")

    def stop(self) -> None:
        if not ENABLED:
            return
        self._timer.stop()
        avg = (self._total_jitter / self._tick_count) if self._tick_count else 0.0
        _emit(
            f"⏱  EventLoopLatencyMonitor: stopped — ticks={self._tick_count} "
            f"stutters={self._stutter_count} max_jitter={self._max_jitter}ms "
            f"avg_jitter={avg:.1f}ms"
        )

    def _tick(self) -> None:
        now = self._elapsed.elapsed()
        delta = now - self._last
        jitter = delta - self._expected
        if jitter > 0:
            self._total_jitter += jitter
        self._tick_count += 1
        if jitter > self._threshold:
            self._stutter_count += 1
            if jitter > self._max_jitter:
                self._max_jitter = jitter
            _emit(f"  ⚡ stutter +{jitter}ms (t={now}ms)")
        self._last = now


def section(title: str) -> None:
    """프로파일 로그에 시각적 섹션 구분자 출력."""
    if not ENABLED:
        return
    _emit("─" * 70)
    _emit(f"▶ {title}")
    _emit("─" * 70)


def is_enabled() -> bool:
    return ENABLED
