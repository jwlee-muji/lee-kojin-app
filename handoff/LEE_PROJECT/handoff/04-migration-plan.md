# 04. Migration Plan — PySide6 마이그레이션 단계별 로드맵

> 한꺼번에 다 바꾸지 말고 **Phase 단위**로 진행. 각 Phase 끝에 동작 검증 후 다음으로.

---

## 🎯 목표

기존 동작을 깨뜨리지 않으면서 디자인 시스템을 단계적으로 입히기.

## 📋 Phase Overview

| Phase | 내용 | 예상 LOC | 위험도 |
|---|---|---|---|
| **Phase 0** | 토큰 + 폰트 인프라 | +200 | 낮음 |
| **Phase 1** | LeeButton, LeeCard, LeeDialog 등 베이스 컴포넌트 | +400 | 낮음 |
| **Phase 2** | 다이얼로그 일괄 마이그레이션 (`QMessageBox` → `LeeDialog`) | ±300 | 중간 |
| **Phase 3** | 로그인 윈도우 리뉴얼 (A+ Refined Dark) | ±200 | 낮음 |
| **Phase 4** | Main Window — TopBar / Sidebar / TopTabs / 위젯 그룹 접기 | ±500 | 높음 |
| **Phase 5** | 위젯 디자인 적용 (Dashboard cards, Settings, Calendar, Gmail, ...) | ±2000 | 중간 |
| **Phase 6** | 최종 폴리싱 (애니메이션, 토스트, 미니 캘린더) | +500 | 낮음 |

---

## 🚀 Phase 0 — 인프라

### 작업
1. `app/ui/theme.py` 에 `TOKENS_DARK`, `TOKENS_LIGHT` 딕셔너리 정의
2. `QSS_TEMPLATE` 작성 (베이스 + 공통 컴포넌트)
3. Pretendard, JetBrains Mono `.qrc` 등록 + `main.py` 에서 폰트 로드
4. `ThemeManager` 싱글턴 (테마 토글 + signal)

### 산출물
- `app/ui/theme.py` (확장)
- `resources/fonts/` + `resources.qrc` 갱신
- `main.py` 폰트 로딩 코드 추가

### 검증
- 앱 실행 → 폰트가 Pretendard로 표시되는지 확인
- 다크/라이트 테마 토글 동작 확인 (DevTool 또는 임시 단축키)

---

## 🧩 Phase 1 — 베이스 컴포넌트

### 작업

`app/ui/components/` 디렉토리 신설 후 각 파일 생성:

1. `components/button.py` — `LeeButton(text, variant, size)`
2. `components/card.py` — `LeeCard(accent_color=None)` + drop shadow effect
3. `components/dialog.py` — `LeeDialog` 베이스 + `confirm/info/error/warning` classmethods
4. `components/input.py` — `LeeLineEdit`, `LeeTextEdit` (QSS만으로도 OK)
5. `components/pill.py` — `LeePill` (label + variant)

### 검증
- 임시 테스트 윈도우에서 각 컴포넌트 렌더 확인
- 각 variant/size/state 작동 확인

---

## 💬 Phase 2 — 다이얼로그 마이그레이션

### 작업

`grep -r "QMessageBox" app/` 로 발견된 모든 호출 사이트 치환:

```python
# Before
QMessageBox.warning(self, "エラー", err)

# After
LeeDialog.error("エラー", err, parent=self)
```

### 우선순위

1. `app/core/updater.py` — 4종 (안내/진행/완료/에러) → 전용 다이얼로그 클래스
2. `app/ui/main_window.py` — 終了の確認, ログアウト
3. `app/ui/login_window.py` — `_AccessRequestDialog` 리뉴얼
4. `app/widgets/manual.py` — カテゴリ管理, 画像編集, 画像プレビュー
5. 나머지 일반 메시지박스들

### 검증
- 각 다이얼로그 트리거 액션 수행 → 디자인 일치 확인
- 키보드 ESC/Enter 동작 확인
- 모달성 (parent window 비활성) 확인

---

## 🔐 Phase 3 — Login Window

### 작업

기존 `app/ui/login_window.py` 리뉴얼:

1. `setWindowFlags(Qt.FramelessWindowHint)` + 커스텀 타이틀바
2. `paintEvent` 에서 그라데이션 + 글로우 + 그리드 텍스처 그리기
3. 좌상단 브랜드 헤더 + 푸터 추가
4. 3 페이지 (로그인/未登録/인증중) `QStackedWidget`

### 검증
- 로그인 흐름 전체 (성공/未登録/실패) 작동 확인
- 윈도우 드래그 (커스텀 타이틀바) 동작 확인
- DPI 스케일 확인

---

## 🪟 Phase 4 — Main Window

### 작업

1. **TopBar** 컴포넌트 (로고 + 검색 + Top Tabs Market/Ops/Tool)
2. **Sidebar** 리뉴얼 — 카테고리 그룹 + 접기/펴기 + active 인디케이터
3. **Top Tabs 필터** — 클릭 시 사이드바 그룹 가시성 토글
4. **Stage** (`QStackedWidget`) 라우팅 정리
5. **closeEvent** → `QuitConfirmDialog` 사용

### 검증
- 페이지 전환 부드러움 확인
- 사이드바 접기/펴기 + 상태 보존 확인 (`QSettings`)
- 트레이 통합 확인

---

## 📊 Phase 5 — 위젯 디자인 적용

### 작업 (위젯별)

| 위젯 | 작업 |
|---|---|
| `dashboard.py` | KPI 카드 4 + 보조 위젯 그리드 |
| `dashboard_cards.py` | LeeCard 적용 + 좌측 accent bar + sparkline |
| `power_reserve.py` | 차트 색상 토큰화 + 카드 정렬 |
| `jepx_spot.py` | 일/월/연/요일별 탭 (Segment) |
| `imbalance.py` | 차트 + 테이블 토큰화 |
| `jkm.py` | 카드 + 차트 |
| `weather.py` | 일러스트 컨테이너 + 카드 |
| `hjks.py` | 차트 + KPI |
| `google_calendar.py` | 풀피처 캘린더 (QGraphicsView 베이스) |
| `gmail.py` | 3-pane + 검색 + 라벨 + 다중선택 |
| `ai_chat.py` | 메시지 버블 디자인 |
| `text_memo.py` | 메모 에디터 |
| `bug_report.py` | 폼 (일반) / 관리자 뷰 |
| `manual.py` | 매뉴얼 viewer + 카테고리 매니저 |
| `settings.py` | 좌측 탭 + 우측 패널 + 자동 갱신 슬라이더 |
| `log_viewer.py` | 로그 테이블 + 필터 |

각 위젯은 **독립적으로** 마이그레이션 가능. 한번에 1~2개씩.

### 검증
- 각 위젯 단독 실행 (테스트 하네스) → 시각 비교
- 데이터 로딩 + 인터랙션 정상 동작 확인

---

## ✨ Phase 6 — 최종 폴리싱

### 작업
1. **토스트 시스템** — `LeeToast(message, kind, duration)` + 슬라이드/페이드
2. **미니 캘린더** 공통화 — 모든 `QDateEdit` 의 popup 대체
3. **모던 스크롤바** — 모든 `QScrollArea` + `QListWidget` 등에 자체 그림 스타일
4. **애니메이션** — 카드 등장, 페이지 전환, hover, 사이드바 접기
5. **스켈레톤 로더** — 데이터 로딩 동안 shimmer
6. **다국어** — i18n 키 검증

### 검증
- 전체 앱 사용성 테스트
- 60 FPS 유지 확인
- 윈도우/맥 양쪽 빌드 확인

---

## ⚠️ 주의사항

### 깨지면 안되는 것들

| 항목 | 확인 방법 |
|---|---|
| Google OAuth 흐름 | 로그아웃 → 재로그인 |
| 자동 업데이트 | 강제 새 버전 publish 후 동작 확인 |
| 백그라운드 트레이 | 닫기 → 트레이 → 다시 열기 |
| 데이터베이스 (캘린더, 메모, etc) | 기존 데이터 보존 확인 |
| 자동 갱신 주기 | 사용자 설정 보존 |
| 단축키 | 모든 글로벌/위젯 단축키 |

### 회귀 테스트 우선순위

1. 로그인 + 토큰 갱신
2. 메인 윈도우 → 트레이 → 종료 흐름
3. 자동 업데이트 다이얼로그 흐름
4. 모든 위젯의 데이터 로딩
5. 다이얼로그 ESC/Enter 키 동작

---

## 📦 폴더 구조 (To-be)

```
app/
├── core/
│   ├── theme.py         # 토큰 + ThemeManager
│   └── ...
├── ui/
│   ├── components/      # ⭐ 신규
│   │   ├── __init__.py
│   │   ├── button.py
│   │   ├── card.py
│   │   ├── dialog.py
│   │   ├── input.py
│   │   ├── pill.py
│   │   ├── sidebar.py
│   │   ├── topbar.py
│   │   ├── segment.py
│   │   ├── toast.py
│   │   └── mini_calendar.py
│   ├── dialogs/         # ⭐ 신규 — 도메인 특화
│   │   ├── update_dialogs.py     # 4종
│   │   ├── quit_dialog.py
│   │   └── access_request_dialog.py
│   ├── login_window.py  # 리뉴얼
│   ├── main_window.py   # 리뉴얼
│   └── theme.py         # 확장
├── widgets/
│   └── (각 위젯 — 디자인 적용)
└── ...
resources/
├── fonts/               # ⭐ 신규
│   ├── Pretendard-*.otf
│   └── JetBrainsMono-*.ttf
└── ...
```
