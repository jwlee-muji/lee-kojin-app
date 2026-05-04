# LEE QtQuick (QML) Prototype — 옵션 B 검증

현재 LEE 앱의 Qt Widgets 기반 UI 가 갖는 구조적 한계 (테마 토글 약 7초 freeze)
가 QtQuick / QML 의 GPU scenegraph 에서 어느 정도 개선되는지 직접 비교하기
위한 단일 화면 프로토타입.

## 실행

```powershell
python tools/qml_prototype/main.py
```

PySide6 만 있으면 됨 (이 프로젝트의 기존 의존성).

## 비교 포인트

| 항목 | Qt Widgets 측정값 | QML 기대 / 측정 |
|---|---|---|
| 테마 토글 시간 | **6,936 ms** (옵션 A 적용 후) | <100 ms (250ms 보간 포함) |
| 토글 중 FPS | 0 fps freeze | 60 fps 유지 |
| 카드 호버 애니메이션 | 단발성 paint | smooth scale + color transition |

화면 우하단에 실시간 메트릭 표시:
- **FPS** — 16ms tick 기반. main thread freeze 시 즉시 0 으로 떨어짐
- **last** — 마지막 테마 토글 elapsed (ms)
- **avg** — 누적 평균
- **theme** — 현재 테마 (dark/light)

좌하단의 회전하는 사각형은 continuous 애니메이션 — main thread 가 멈추면
즉시 멈춰 보이므로 freeze 검출용.

## 실험 절차

1. 앱 실행 → 우상단 ☀ / ☾ 버튼 클릭으로 테마 토글
2. 콘솔에 `[QML] theme toggle elapsed: XX.Xms` 출력
3. 화면 우하단의 `last` / `avg` 갱신 확인
4. 좌하단 회전 사각형이 토글 중에도 계속 돌고 있는지 확인
5. 카드를 마우스로 호버 시 scale up 부드러움 / 멈춤 없는지 확인

## 결과 해석

- **avg < 300ms 이고 회전 멈추지 않음** → QML 마이그레이션이 smooth UI 의 답
- **avg > 1000ms 이거나 회전 멈춤** → QML 도 이 워크로드에서 한계 있음. 다른
  접근 (Tauri/Web) 검토 필요

## 확장 가능

이 프로토타입에 차트 / 데이터 바인딩 / 실제 LEE Python 백엔드 연결을
추가해보면, 마이그레이션 시 어떤 패턴을 쓸지 더 명확해짐. 우선 최소 단위로
"smooth 가 가능한가" 만 검증.
