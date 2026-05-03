# 05\. Claude Code Prompts — 지시 가이드

> ⭐ \*\*이 문서가 핵심입니다.\*\* VS Code의 Claude Code 익스텐션에 어떤 프롬프트를 넣어야 효과적으로 마이그레이션할 수 있는지.

\---

## 🎯 기본 원칙

### 1\. Phase 단위로 끊어서 시킨다

한번에 "다 바꿔줘" 하면 너무 큰 변경이 한꺼번에 들어가서 검증이 어렵고 회귀 위험이 큼. **Phase 0 → 1 → 2 ...** 순서대로.

### 2\. 매 프롬프트에 핸드오프 문서를 첨부한다

Claude Code는 첨부된 파일을 정확히 읽음. 매번:

* `01-design-tokens.md`
* `02-components.md`
* (해당 Phase에 필요한 것만 추가로)

VS Code Claude Code에서는 `@파일명` 으로 참조하거나 사이드바에서 첨부 가능.

### 3\. "한 작업 = 한 프롬프트"

컴포넌트 1개 만들기 / 다이얼로그 N개 마이그레이션 / 한 위젯 리뉴얼 — 단위로 자르기.

### 4\. 변경 후 매번 실행 확인

"실행해서 동작 확인하고, 이상 있으면 알려줘" 로 마무리. Claude Code는 코드 리딩 + 실행 + 디버깅 가능.

\---

## 📝 Phase 0 — 인프라 셋업

### 프롬프트 ①

```
디자인 핸드오프 패키지를 받았습니다. 첨부 파일을 모두 읽고, 다음 작업을
"Phase 0: 인프라 셋업"으로 진행해주세요.

\[첨부]
- handoff/README.md
- handoff/01-design-tokens.md
- handoff/02-components.md
- handoff/04-migration-plan.md

\[작업 내용]
1. app/ui/theme.py 를 확장해서 TOKENS\_DARK, TOKENS\_LIGHT 딕셔너리를
   01-design-tokens.md 의 모든 값으로 정의해주세요.
2. QSS\_TEMPLATE 을 작성하고 get\_global\_qss(theme) 가 그걸 .format() 해서
   리턴하도록 수정해주세요.
3. Pretendard 와 JetBrains Mono 폰트를 다운받아 resources/fonts/ 에 넣고,
   resources.qrc 에 등록해주세요. (라이선스: 둘 다 OFL)
4. main.py 에서 QFontDatabase.addApplicationFont 로 등록 후 폰트 적용해주세요.
5. ThemeManager(QObject) 싱글턴을 만들어, set\_theme(theme) 시 앱 전체 QSS를
   교체하고 theme\_changed 시그널을 emit 하도록 해주세요.

\[제약]
- 기존 동작 (로그인 → 메인 → 위젯들) 이 깨지지 않게.
- 토큰 값은 핸드오프 문서 그대로 사용. 임의 수정 금지.

작업 완료 후 앱을 실행해서 폰트가 Pretendard로 적용됐는지 확인해주세요.
```

\---

## 🧩 Phase 1 — 베이스 컴포넌트

### 프롬프트 ②

```
Phase 1: 베이스 컴포넌트 작성.

\[첨부]
- handoff/02-components.md
- (이미 작업한 app/ui/theme.py)

\[작업 내용]
app/ui/components/ 디렉토리를 만들고, 다음 5개 파일을 생성해주세요:

1. components/\_\_init\_\_.py — 모든 클래스 export
2. components/button.py — LeeButton(text, variant, size, parent)
   - variant: primary | secondary | destructive | ghost
   - size: sm | md | lg
   - 02-components.md §1 참조해서 정확히 구현
3. components/card.py — LeeCard(accent\_color=None, interactive=False)
   - QFrame + drop shadow effect (QGraphicsDropShadowEffect)
4. components/dialog.py — LeeDialog 베이스 + classmethod 4개
   - confirm(title, message, \*, ok\_text, cancel\_text, destructive, parent) -> bool
   - info(title, message, parent)
   - error(title, message, \*, details, parent)
   - warning(title, message, parent)
   - 02-components.md §3 참조
5. components/pill.py — LeePill(text, variant) (QLabel 베이스)

각 파일에:
- QSS는 theme.py 의 토큰을 .format()로 주입
- docstring 으로 사용 예시 작성
- 타입 힌트 적용

작업 후 임시 테스트 윈도우 (app/ui/\_dev\_components.py 같이) 만들어서
모든 컴포넌트의 모든 variant/size 를 한 화면에 렌더해 시각 확인 가능하게 해주세요.
```

\---

## 💬 Phase 2 — 다이얼로그 마이그레이션

### 프롬프트 ③ (한 파일씩)

```
Phase 2-A: app/core/updater.py 의 다이얼로그를 새 디자인으로 교체.

\[첨부]
- handoff/02-components.md
- handoff/03-screen-specs.md
- 디자인 모킹업: LEE 電力モニター - 2 Variations.html 의 "システム ダイアログ" 섹션
  (브라우저로 열어서 확인 가능)

\[작업 내용]
app/ui/dialogs/update\_dialogs.py 를 신설하고 4개 클래스 작성:

1. UpdateAvailableDialog(LeeDialog)
   - 제목 "アップデートのお知らせ"
   - 현재 버전 → NEW 버전 비교 카드
   - "後で" / "今すぐ更新" 버튼
   - exec() → bool

2. UpdateProgressDialog(LeeDialog)
   - 스피너 + 프로그레스 바 (0\~100)
   - update\_progress(downloaded\_mb, total\_mb) 메서드
   - 닫기 버튼 없음 (모달)

3. UpdateReadyDialog(LeeDialog)
   - 성공 아이콘 + "OK · インストールを開始"

4. DownloadErrorDialog(LeeDialog)
   - 에러 메시지 + 모노 트레이스 박스
   - "閉じる" / "再試行"
   - retry signal

그리고 updater.py 의 UpdateManager 클래스에서:
- QMessageBox.question() → UpdateAvailableDialog
- QProgressDialog → UpdateProgressDialog
- QMessageBox.information(...) → UpdateReadyDialog
- QMessageBox.warning(...) → DownloadErrorDialog
모두 교체. 동작 흐름은 동일하게 유지.

\[검증]
실행 후 자동 업데이트 흐름을 강제로 트리거하는 dev 단축키
(예: Ctrl+Shift+U → 가짜 업데이트 정보로 흐름 시뮬레이션)
를 추가하면 좋겠습니다.
```

### 프롬프트 ④ (일반 QMessageBox 일괄)

```
Phase 2-B: 앱 전반의 QMessageBox 호출을 LeeDialog로 일괄 마이그레이션.

\[첨부]
- handoff/02-components.md
- handoff/03-screen-specs.md §4

\[작업 내용]
1. `grep -r "QMessageBox" app/` 로 모든 호출 사이트 찾아주세요.
2. 다음 패턴으로 일괄 치환:

   QMessageBox.warning(self, title, msg)
   → LeeDialog.error(title, msg, parent=self)

   QMessageBox.information(self, title, msg)
   → LeeDialog.info(title, msg, parent=self)

   QMessageBox.question(self, title, msg, Yes|No) == Yes
   → LeeDialog.confirm(title, msg, parent=self)

   삭제 확인은 destructive=True 추가:
   → LeeDialog.confirm(title, msg, ok\_text="削除", destructive=True, parent=self)

3. 단, 다음은 전용 다이얼로그로 (이미 만든 거):
   - main\_window.py:879 終了の確認 → QuitConfirmDialog (3 버튼) 신설
   - main\_window.py:911 ログアウト → 그대로 LeeDialog.confirm + 사용자 카드 슬롯

4. 작업 결과를 변경 파일 리스트로 알려주세요.

\[제약]
- 기존 흐름 깨지지 않게.
- 다국어 (tr()) 함수는 그대로 유지.
- 임포트 정리 (불필요한 QMessageBox import 제거).
```

\---

## 🔐 Phase 3 — Login Window

### 프롬프트 ⑤

```
Phase 3: 로그인 윈도우를 A+ Refined Dark 디자인으로 리뉴얼.

\[첨부]
- handoff/03-screen-specs.md §3
- 디자인 모킹업: LEE 電力モニター - 2 Variations.html 의 "ログイン Window" 섹션 → A+ Refined
- 현재 코드: app/ui/login\_window.py

\[작업 내용]
app/ui/login\_window.py 를 다음과 같이 리뉴얼:

1. QMainWindow → 프레임리스 + 커스텀 그라데이션 배경
   - setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
   - 480 × 580 고정 크기
   - paintEvent에서:
     a. 베이스 라디얼 (#2a1410 → #160c0a → #14161C)
     b. 우상단 오렌지 글로우 (FF7A45 18%)
     c. 좌하단 큰 빛무리 (FF9F0A 22% → FF7A45 0%)
     d. 미세 그리드 (white 4%)
     e. vignette (black 25%)

2. 좌상단 브랜드 헤더 (32x32 아이콘 + "LEE 電力モニター" + "POWER MARKET INTEL · v3.4.2")

3. 3 페이지 (QStackedWidget):
   - 페이지 0: SECURE ACCESS / ようこそ / Google 버튼 / "アクセスを申請" 링크
   - 페이지 1: 未登録 (warning 아이콘 + 이메일 칩 + 申請 버튼)
   - 페이지 2: 認証中 (스피너 + 캔슬)

4. 푸터: "© Shirokuma Power" / "jw.lee@shirokumapower.com" (모노)

5. 윈도우 드래그 가능 (mousePressEvent / mouseMoveEvent)

6. \_AccessRequestDialog 도 새 디자인 적용 (LeeDialog 베이스 + 폼 스타일)

\[검증]
- 로그인 → 성공 → 메인 윈도우 정상
- 로그인 → 未登録 → アクセス申請 → SMTP 송신 흐름
- 인증중 캔슬 → 페이지 0 복귀
- 윈도우 드래그 가능 + 종료 (X 버튼은 우상단에 추가)
```

\---

## 🪟 Phase 4 — Main Window

### 프롬프트 ⑥

```
Phase 4: Main Window 리뉴얼 (TopBar + Sidebar + Top Tabs + 위젯 그룹 접기).

\[첨부]
- handoff/02-components.md
- handoff/03-screen-specs.md §1
- 디자인 모킹업: 메인 화면 (Variation A)

\[작업 내용]
app/ui/main\_window.py 를 다음과 같이 리뉴얼:

1. TopBar (높이 48px) — components/topbar.py 신규
   - 좌: 로고 + "LEE 電力モニター"
   - 중: 글로벌 검색 (Spotlight 풍, Ctrl+K)
   - 우: 3개 탭 \[Market▾] \[Operation▾] \[Tool▾]
   - Top Tab 클릭 시 사이드바 위젯 그룹 필터

2. Sidebar (240px) — components/sidebar.py 신규
   - 카테고리 그룹별 (Market / Operation / Tool / System)
   - 그룹 헤더 클릭 시 접기/펴기 (▾/▸) — QSettings 보존
   - 위젯 항목 active 인디케이터 (좌측 3px accent bar)
   - 하단: 사용자 아바타 + 설정 버튼

3. Stage (QStackedWidget) — 모든 페이지 등록
   - 라우팅: sidebar.item\_clicked → stage.setCurrentWidget

4. closeEvent → QuitConfirmDialog (3 버튼: 트레이 / 종료 / 취소)

5. 트레이 통합 유지

\[제약]
- 기존 페이지 (대시보드, 모든 디테일) 가 그대로 동작
- 자동 업데이트 흐름 유지
- 트레이 동작 유지

\[검증]
- 모든 위젯 페이지 진입 가능
- 사이드바 접기 상태가 다음 실행 시 보존
- Top Tab 필터 동작
- closeEvent 3 버튼 분기 동작
```

\---

## 📊 Phase 5 — 위젯 디자인 적용

### 프롬프트 ⑦ (한 위젯씩)

```
Phase 5-A: power\_reserve.py 위젯에 새 디자인 적용.

\[첨부]
- handoff/01-design-tokens.md
- handoff/02-components.md
- 디자인 모킹업: 메인 화면 (Variation A) → "予備率" 카드 + Reserve Detail 화면
- 현재 코드: app/widgets/power\_reserve.py

\[작업 내용]
1. 대시보드 카드 (PowerReserveCard) — LeeCard 사용 + accent\_color="#5B8DEF"
   - 좌측 3px 액센트 바
   - 헤더: 아이콘 + 라벨
   - 본문: 큰 숫자 (--font-mono) + delta + sparkline
   - 클릭 시 detail로 이동

2. Detail 화면:
   - 상단 툴바 (← 戻る + 자동갱신 표시)
   - 좌측: 상세 KPI 그리드
   - 우측: 라인 차트 (QtCharts)
   - 차트 컬러: --c-power (#5B8DEF)

3. 모든 색상을 토큰 기반으로 (하드코딩 제거)

4. 자동 갱신 주기를 settings 와 연동

\[검증]
- 데이터 로드 정상
- 클릭 → detail → 戻る 흐름
- 컬러 톤 모킹업과 일치

```

위 프롬프트를 위젯마다 반복 (총 16개 위젯).

순서 추천:

1. power\_reserve (단순, 패턴 학습용)
2. jepx\_spot
3. imbalance
4. jkm
5. weather
6. hjks
7. dashboard (KPI 그리드 + 보조 위젯 합성)
8. settings (가장 복잡)
9. google\_calendar (드래그앤드롭 등)
10. gmail
11. 나머지

\---

## ✨ Phase 6 — 폴리싱

### 프롬프트 ⑧

```
Phase 6: 최종 폴리싱.

\[작업 내용]
1. components/toast.py — LeeToast 시스템 (전역 호출 가능)
   - LeeToast.show(message, kind="info", duration=4000, parent=None)
   - 우상단 슬라이드 인 + 자동 페이드
   - 큐 시스템 (여러 토스트 누적 시 세로 스택)

2. components/mini\_calendar.py — QDateEdit 의 popup을 통일된 디자인으로
   - QCalendarWidget 서브클래스 + 헤더/푸터 커스텀
   - 모든 QDateEdit 에 setCalendarWidget(MiniCalendar()) 적용

3. 모던 스크롤바 — 모든 QAbstractScrollArea 자식의 QSS 스타일 강제
   - app 레벨 QSS에 추가하면 자동 전파

4. 애니메이션:
   - 카드 등장: QGraphicsOpacityEffect + QPropertyAnimation 240ms (OutBack)
   - 페이지 전환: 컨텐츠 페이드 180ms
   - 사이드바 접기: 높이 애니메이션

5. 스켈레톤 로더 — 데이터 로딩 동안 shimmer
   - components/skeleton.py — LeeSkeleton(width, height)
   - shimmer keyframe (QPropertyAnimation으로 그라데이션 위치 이동)

\[검증]
- 전체 앱 사용
- 60 FPS 유지
- Windows/Mac 빌드 시각 확인
```

\---

## 🛠️ 일반 팁

### Claude Code에게 먹히는 패턴

✅ **좋은 프롬프트**

```
Phase 2-A: app/core/updater.py 의 4개 다이얼로그 마이그레이션.

첨부: 02-components.md §3, 03-screen-specs.md §4

요구:
1. update\_dialogs.py 신설하고 UpdateAvailableDialog 등 4개 클래스
2. updater.py 의 호출 사이트 교체
3. 동작 흐름 동일 유지

검증: 가짜 업데이트 트리거 단축키 추가
```

❌ **나쁜 프롬프트**

```
디자인 입혀줘
```

### 중간에 막히면

```
이 작업 중 \[구체적 이슈] 가 발생합니다.
관련 파일: \[경로]
에러: \[메시지]

해결 방안 제안 + 적용해주세요.
```

### 검증 요청

```
방금 변경 후 실제로 동작 확인해주세요:
- python main.py 실행
- 콘솔 에러 확인
- \[구체적 시나리오] 수동 테스트
```

### 회귀 위험 체크

```
이 변경이 다음 기능에 영향이 없는지 확인해주세요:
- 자동 업데이트 흐름
- Google OAuth
- 트레이 통합
- 데이터베이스 보존

각 항목 grep + 코드 분석으로 검증.
```

\---

## 📂 첨부 파일 빠른 참조

|시점|첨부할 파일|
|-|-|
|Phase 0|README, 01-tokens, 04-plan|
|Phase 1|01-tokens, 02-components|
|Phase 2|02-components, 03-screens (§4)|
|Phase 3|03-screens (§3), 모킹업 HTML|
|Phase 4|02-components, 03-screens (§1)|
|Phase 5|01-tokens, 02-components, 모킹업 HTML (해당 위젯)|
|Phase 6|01-tokens, 02-components|

\---

## 🚦 시작 가이드

### 지금 바로 해볼 것 (5분)

1. VS Code에서 `Lee` 프로젝트 열기
2. Claude Code 익스텐션 사이드바 열기
3. 다음 프롬프트 복사해서 붙여넣기:

```
이 프로젝트의 디자인 마이그레이션을 시작합니다.

handoff/ 폴더의 README.md 와 04-migration-plan.md 를 먼저 읽고,
현재 프로젝트 구조를 파악한 뒤,
Phase 0 작업 계획을 제시해주세요.

아직 코드는 작성하지 마시고, 계획만 + 질문만 정리해주세요.
```

4. 응답 받은 후 Phase 0 프롬프트 (위 ①)로 진행

\---

## 🎓 핵심 원칙 다시

1. **한 번에 한 Phase**
2. **매번 핸드오프 문서 첨부** (Claude Code가 정확히 읽음)
3. **변경 후 실행 + 검증 명시적으로 요청**
4. **회귀 위험을 항상 의식**
5. **막히면 작게 잘라서 재시도**

화이팅! 🚀

