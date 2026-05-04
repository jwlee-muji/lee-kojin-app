# QML 실 워크로드 prototype — PowerReserve 페이지

옵션 B 결정을 위해 정적 prototype 이 아닌 **실 데이터 워크로드** 로 검증.

## 재현 대상

LEE 앱의 PowerReserveWidget 핵심 요소를 QML 로 재현:

- **48 × 10 pivot 테이블** (480 colored cell)
- **24 h line chart** (Tokyo area, 48 point)
- **3 KPI 카드** (평균 / 최저 / 注意 areas)
- **테마 토글** (전 색상 250ms 보간)
- **Refresh 버튼** — 데이터 재생성 + UI 재바인딩 elapsed 측정
- **회전 spinner** + **FPS 카운터** (freeze 검출)

데이터: random mock (실 DB 미접근 — 순수 렌더링 비교 목적).

## 실행

```powershell
python tools/qml_real/main.py
```

## 측정 항목

콘솔 출력:
```
[QML] theme toggle elapsed: NN.Nms
[QML] refresh elapsed: NN.Nms
```

화면 우하단 메트릭:
```
FPS: NN.N  |  refresh: NN ms  |  toggle: NN ms
```

## 비교 대상

- **현재 LEE 앱 PowerReserveWidget** — 데이터 갱신 ~150ms / 테마 토글 ~7s
- **Web prototype** (tools/web_real) — 동일한 페이지를 ECharts 로 재현

3개 모두 같은 인터랙션을 같은 시점에 수행해 비교하면 어느 기술이 이 워크로드에
가장 부드러운지 정량적으로 판단 가능.
