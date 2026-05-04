# Web (QWebEngine + ECharts) 실 워크로드 prototype — PowerReserve 페이지

옵션 B 결정을 위한 **PyWebView 패턴** 검증. PySide6 의 QWebEngine 으로
Chromium 임베딩 + 단일 HTML 파일 (React 없이 vanilla JS + ECharts CDN)
로 PowerReserve 페이지 재현.

## 아키텍처

```
┌─────────────────────────────────────────────┐
│  Python (main.py)                           │
│  - QApplication + QWebEngineView            │
│  - Bridge (QObject, Slot/Signal)            │
│  - mock 데이터 generator                     │
└─────────┬───────────────────────────────────┘
          │ QWebChannel (Python ↔ JS)
┌─────────▼───────────────────────────────────┐
│  index.html (Chromium webview)              │
│  - CSS Grid 480 cell pivot                  │
│  - ECharts line chart                       │
│  - CSS variables 기반 dark/light            │
│  - bridge.refresh() / bridge.toggleStart()  │
└─────────────────────────────────────────────┘
```

## 재현 대상

QML prototype 과 동일 — 직접 비교 가능:

- **48 × 10 pivot** — CSS Grid 로 480 cell DOM
- **24h line chart** — ECharts (GPU 가속, smooth 보간)
- **3 KPI 카드**
- **테마 토글** — `<html data-theme="dark">` 변경 + CSS transition 250ms
- **Refresh** — Python 이 새 데이터 푸시 → JS 가 렌더 → elapsed 측정
- **회전 spinner** (CSS animation) + **FPS 카운터** (requestAnimationFrame)

## 실행

```powershell
python tools/web_real/main.py
```

ECharts 는 CDN 로드 (인터넷 필요 — 처음 1회). QWebEngine 캐시되면 오프라인 동작.

## 비교 포인트 vs QML

| 항목 | QML 예상 | Web 예상 |
|---|---|---|
| 차트 품질 | Qt Charts (단순) | ECharts (smooth animation, tooltip, zoom) |
| 480 cell 갱신 | TableView + Behavior | CSS Grid + transition |
| 테마 토글 시간 | 보간 250ms | CSS transition 250ms |
| 메모리 사용 | ~150 MB | ~250 MB (Chromium) |
| 코드 양 (이 prototype) | QML ~270 줄 | HTML+CSS+JS ~250 줄 |
| 학습 곡선 | QML / JS | HTML / CSS / JS (이미 익숙할 가능성 큼) |

## 측정 출력

콘솔:
```
[Web] theme toggle elapsed: NN.Nms
[Web] refresh elapsed: NN.Nms
```

화면 우하단:
```
FPS: NN.N  |  refresh: NN ms  |  toggle: NN ms
```

## 결정 가이드

QML prototype 과 양쪽 다 실행해서 비교:

1. **차트의 부드러움** — ECharts 가 더 좋다는 게 거의 확실. 정도 차이만 확인.
2. **pivot 테이블 갱신 elapsed** — QML 이 native 인 만큼 더 빠를 수도 / DOM 도 충분히 빠를 수도.
3. **테마 토글 끊김 없음** — 양쪽 다 60fps 유지 기대.
4. **코드 가독성** — 본인이 더 편한 쪽 선택.
5. **메모리** — Chromium 무거움 감수 가능한지.
