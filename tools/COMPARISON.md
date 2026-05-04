# LEE UI 기술 비교 — 옵션 B prototype 가이드

3개 prototype 으로 직접 비교 후 마이그레이션 결정:

```
tools/
  qml_prototype/    — 정적 QML (theme toggle 부드러움 입증, 데이터 없음)
  qml_real/         — PowerReserve QML 재현 (실 워크로드)
  web_real/         — PowerReserve Web 재현 (QWebEngine + ECharts)
```

## 같이 비교할 것

본 LEE 앱의 PowerReserve 페이지를 같이 띄우고:

```powershell
# 4 창 동시 실행
python main.py                          # 현재 Widgets 앱
python tools/qml_real/main.py           # QML prototype
python tools/web_real/main.py           # Web prototype
```

각각에서 동일한 인터랙션 (refresh 5회, theme toggle 5회) 수행 후 비교.

## 비교표 (실측해서 채울 것)

| 항목 | Widgets (현 앱) | QML real | Web real |
|---|---|---|---|
| 테마 토글 elapsed (ms) | ~7,000 | ? | ? |
| Refresh elapsed (ms) | ~150 | ? | ? |
| 토글 중 회전 spinner | 멈춤 | ? | ? |
| 차트 hover/zoom 부드러움 | (제한) | ? | ? |
| 메모리 (MB, 정상 사용 시) | ~180 | ~150 | ~250 |
| 코드 가독성 (1~5) | - | ? | ? |

## 결정 기준 (개인 의견)

- **QML 이 명확히 우세** → Python 그대로 + UI 만 QML 마이그레이션. 한 언어 (Python+QML),
  단일 프로세스, 의존성 추가 없음.

- **Web 이 명확히 우세** → ECharts 의 차트 품질이 결정적. 메모리 +200MB 감수.
  React 도입은 점진적 (먼저 vanilla 로 시작 가능).

- **Widgets 와 격차 미미** → 마이그레이션 비용 회수 안 됨. 옵션 A 회수만 유지.

- **양쪽 prototype 다 일부 한계** → Tauri (Rust + Web) 또는 Flutter 더 검토 필요.
  하지만 이 시점에선 Python 분리 비용이 크므로 사실상 보류.

## 마이그레이션 시 단계 제안 (만약 결정한다면)

1. **새 페이지 1 개를 채택 기술로 작성** (예: PowerReserve)
2. **검증 후 다음 페이지** (Imbalance, JKM 등 — pattern 정착)
3. **차트 컴포넌트 라이브러리화** (재사용)
4. **마지막에 대시보드 / 사이드바 / 테마 시스템** (가장 손 많이 가는 부분)
5. **Widgets 코드 점진 제거** (16 페이지 모두 이전 후 deprecate)

총 예상 기간: 솔로 개발 3~6주 (페이지당 0.5~1주, 인프라 1주).
