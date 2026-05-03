# Phase 5 — 위젯 마이그레이션 프롬프트 16종

> 위젯마다 독립 프롬프트. **순서대로 진행 권장** (단순 → 복잡 → 통합).
> 각 프롬프트는 "복사 → Claude Code에 붙여넣기 → 첨부 명시" 흐름으로 사용.

## 📑 진행 순서

| # | 위젯 | 난이도 | 시간 | 의존성 |
|---|---|---|---|---|
| 5.1 | `power_reserve` | ★ | 1h | — (패턴 학습용) |
| 5.2 | `jepx_spot` | ★★ | 2h | 5.1 패턴 |
| 5.3 | `imbalance` | ★★ | 2h | 5.1 패턴 |
| 5.4 | `jkm` | ★ | 1h | 5.1 패턴 |
| 5.5 | `weather` | ★★ | 2h | — |
| 5.6 | `hjks` | ★★ | 2h | 5.1 패턴 |
| 5.7 | `text_memo` | ★ | 1h | — |
| 5.8 | `notification` | ★ | 1h | — |
| 5.9 | `ai_chat` | ★★ | 2h | — |
| 5.10 | `bug_report` | ★★ | 2h | — |
| 5.11 | `manual` | ★★★ | 3h | — |
| 5.12 | `log_viewer` | ★★ | 2h | — |
| 5.13 | `gmail` | ★★★★ | 4h | — |
| 5.14 | `google_calendar` | ★★★★★ | 6h | — |
| 5.15 | `dashboard` | ★★★ | 3h | **5.1~5.14 모두** (16개 카드 통합) |
| 5.16 | `settings` | ★★★ | 3h | 모두 (자동갱신 주기 hook) |

총 예상: **약 37시간**

> 💡 **순서 변경 사항**: dashboard를 마지막에서 두 번째로 미뤘습니다.
> 모든 *Card 컴포넌트가 먼저 완성되어야 통합 레이아웃을 깔끔하게 짤 수 있어서.

---

## 공통 첨부 파일 (모든 프롬프트에)

```
@handoff/01-design-tokens.md
@handoff/02-components.md
@handoff/03-screen-specs.md
LEE 電力モニター - 2 Variations.html  ← 모킹업 참조
```

각 프롬프트의 [첨부] 섹션은 **추가**로 필요한 것만 표기.

---

## 5.1 ─ power_reserve (예비율) ★

```
Phase 5.1: app/widgets/power_reserve.py 에 새 디자인 적용.

[첨부]
- handoff/01-design-tokens.md
- handoff/02-components.md (§2 Card, §7 KPI Card)
- 모킹업: 메인 화면 → "予備率" 카드 + Reserve Detail 화면

[작업 내용]
1. PowerReserveCard (대시보드용, 작은 카드)
   - LeeCard(accent_color="#5B8DEF") 사용 (--c-power)
   - 좌측 3px 액센트 바 (border-left)
   - 헤더: 24px icon tile + "予備率" (--font-sans, 12pt, 600)
   - 본문: 큰 숫자 (--font-mono, 36pt, tnum) + 단위 "%"
   - delta: "↓ 1.2 vs 昨日" (color = --c-bad if 악화, --c-ok if 호전)
   - sparkline: 28px height, --c-power 라인 + 0.15 opacity fill
   - 클릭 시 detail page로 이동 (signal: card_clicked)

2. PowerReserveDetailPage (상세 화면)
   - 상단: ← 戻る + "予備率" 타이틀 + 자동갱신 인디케이터 ("● 5分ごと")
   - 좌측 (320px): 수직 KPI 스택
     · 現在の予備率 (큰 숫자)
     · 本日最低 / 最高 / 平均
     · 警報レベル pill (緑/橙/赤)
   - 우측 (가변): QChart 라인 차트 (24h)
     · X축: 시간, Y축: %
     · 라인 컬러: --c-power
     · 영역 fill: --c-power-soft (라이트), 라인 + opacity (다크)
     · 그리드: --grid-line
     · 8% / 5% / 3% 가로 가이드 라인 (warn / bad)

3. 토큰 적용
   - 모든 색상 tokens.py 의 변수 사용 (#5B8DEF 직접 X)
   - QSS는 theme.py 의 get_qss(component="power_reserve")로 분리

4. 자동 갱신 주기
   - settings_manager.get("auto_refresh.power_reserve", default=300)
   - QTimer 적용. 사용자 변경 즉시 반영 (signal 구독).

[제약]
- 데이터 로딩 로직은 그대로 유지 (PowerReserveWorker 등)
- API 시그니처 (signal/slot) 유지

[검증]
- python main.py → 대시보드 → 카드 표시 확인
- 카드 클릭 → detail → ← 戻る → 대시보드 복귀
- 데이터 fresh load 정상
- 라이트/다크 토글 시 차트 컬러도 정상 전환
```

---

## 5.2 ─ jepx_spot (スポット価格) ★★

```
Phase 5.2: app/widgets/jepx_spot.py 에 새 디자인 적용.

[첨부]
- handoff/01-design-tokens.md
- handoff/02-components.md (§2 Card, §7 KPI, §8 Segmented)
- 모킹업: Spot Detail (일별/月間/年間/曜日別 4탭)

[작업 내용]
1. JepxSpotCard (대시보드용)
   - LeeCard(accent_color="#FF7A45") (--c-spot)
   - "JEPXスポット" + システムプライス 큰 숫자 (¥/kWh)
   - 24h sparkline (30분 코마)
   - 본일 평균 / 최고 / 최저 mini 표시

2. JepxSpotDetailPage
   - 상단 툴바: ← 戻る + 타이틀 + 자동갱신 + 다운로드 버튼
   - 4탭 SegmentedControl: [日別] [月間] [年間] [曜日別]
   - 각 탭의 차트 + 테이블:

     a. 日別: 30분 코마 (48 포인트) 라인 차트 + 시간대별 테이블
     b. 月間: 월 일별 평균 막대 차트 + 통계 카드 (월평균/최고/최저/표준편차)
     c. 年間: 12개월 박스플롯 또는 라인 + 연간 통계
     d. 曜日別: 7개 막대 (월~일) + 평균 비교 (전월/전년)

   - 차트 컬러 모두 --c-spot 계열
   - 데이터 로딩은 jepx_spot.py 의 fetch_* 함수 그대로 사용

3. 컬러 코딩
   - 가격 상승 → --c-warn (오렌지, 경계)
   - 가격 하락 → --c-ok (초록, 호재)

4. 다운로드 버튼: CSV export (기존 함수 있으면 reuse)

[검증]
- 4탭 모두 진입 + 차트 렌더 + 데이터 정상
- 다운로드 → CSV 파일 정상 생성
- 자동 갱신 동작
```

---

## 5.3 ─ imbalance (インバランス) ★★

```
Phase 5.3: app/widgets/imbalance.py 에 새 디자인 적용.

[첨부]
- handoff/01-design-tokens.md
- handoff/02-components.md
- 모킹업: Imbalance Detail

[작업 내용]
1. ImbalanceCard (대시보드)
   - LeeCard(accent_color="#F25C7A") (--c-imb)
   - "インバランス" + 直近30분 가격 (¥/kWh)
   - 30분 코마 sparkline (1시간 = 2점)
   - 알림 pill: "急騰" (--c-bad) / "安定" (--c-ok)

2. ImbalanceDetailPage
   - 상단 툴바
   - 좌측 KPI (320px):
     · 直近30분
     · 本日平均
     · ピーク (시간 + 가격)
     · 異常검출 pill
   - 우측: 라인 차트 (당일 30분 코마, 48 포인트)
     · 라인 컬러: --c-imb
     · 임계값 가이드라인: --c-warn (warn 임계) / --c-bad (bad)
     · X축: 30분 슬롯, Y축: ¥/kWh

3. 알림 임계값 설정 (간이)
   - 카드 우상단 ⚙ → 임계값 다이얼로그 (LeeDialog 베이스)
   - 임계값 변경 시 즉시 반영

4. 異常검출
   - 임계값 초과 시 LeeToast.show("インバランス急騰", kind="warning") (Phase 6 이후)

[검증]
- 데이터 로드, 차트 렌더링
- 임계값 설정 다이얼로그 동작
- 자동 갱신 (1분 또는 사용자 설정)
```

---

## 5.4 ─ jkm (JKM LNG) ★

```
Phase 5.4: app/widgets/jkm.py 에 새 디자인 적용.

[첨부]
- handoff/01-design-tokens.md
- handoff/02-components.md
- 모킹업: JKM Detail

[작업 내용]
1. JkmCard (대시보드)
   - LeeCard(accent_color="#F4B740") (--c-jkm)
   - "JKM LNG" + 最新値 ($/MMBtu)
   - 30일 sparkline
   - 전주/전월 대비 delta (%)

2. JkmDetailPage
   - 상단 툴바
   - 좌측 KPI:
     · 最新値 / 前日比 / 前週比 / 前月比
     · 4-week MA / 12-week MA
   - 우측 라인 차트:
     · 단위: 30D / 90D / 1Y / All (Segment 토글)
     · MA 4w / MA 12w 추가 라인 (옵션 토글)
     · 라인 컬러: --c-jkm

3. 데이터 source (기존 jkm.py 함수 reuse)

[검증]
- 4단위 모두 차트 정상
- MA 토글 동작
- 자동 갱신 (30분)
```

---

## 5.5 ─ weather (天気) ★★

```
Phase 5.5: app/widgets/weather.py 에 새 디자인 적용.

[첨부]
- handoff/01-design-tokens.md
- handoff/02-components.md
- 모킹업: Weather 카드 + Detail (일러스트 컨테이너 포함)

[작업 내용]
1. WeatherCard (대시보드)
   - LeeCard(accent_color="#2EC4B6") (--c-weather)
   - 좌: 큰 일러스트 컨테이너 (60x60 — 날씨 코드별 SVG/QPainter 일러스트)
     · sunny / cloudy / rain / snow / thunder / fog / partly cloudy
     · 모킹업의 SVG 그대로 QSvgWidget로 임베드 (또는 QIcon)
   - 우: 도시명 / 현재 기온 / 体感温度 / 습도 / 풍속

2. WeatherDetailPage
   - 상단: 도시 selector (Tokyo / Osaka / 사용자 추가)
   - 큰 현재 날씨 카드 (일러스트 + 큰 기온)
   - 시간별 예보 (24h 가로 스크롤, 1h 단위)
   - 주간 예보 (7일 카드)
   - 지도 (옵션, 추후)

3. 일러스트 시스템
   - app/ui/components/weather_illust.py 신설
   - WeatherIllust(code, size) → QSvgWidget 또는 QPainter custom
   - 모킹업의 SVG 8종 그대로 (sunny/cloudy/rain/snow/thunder/fog/partly/clear-night)

4. 데이터 source (OpenWeatherMap 등 기존 사용)

[검증]
- 도시 변경 동작
- 24h / 7day 예보 렌더
- 자동 갱신 (15분)
- 일러스트 8종 모두 표시 가능
```

---

## 5.6 ─ hjks (発電稼働) ★★

```
Phase 5.6: app/widgets/hjks.py 에 새 디자인 적용.

[첨부]
- handoff/01-design-tokens.md
- handoff/02-components.md
- 모킹업: HJKS Detail

[작업 내용]
1. HjksCard (대시보드)
   - LeeCard(accent_color="#A78BFA") (--c-hjks)
   - "発電稼働" + 가동률 (%) 큰 숫자
   - 24h sparkline (가동률 추이)
   - 발전소별 가동/정지 카운트 ("稼働 X / 停止 Y")

2. HjksDetailPage
   - 상단 툴바
   - 좌측 KPI:
     · 全体稼働率 / 火力 / 原子力 / 再エネ
     · 計画停止 / 突発停止 카운트
   - 우측:
     · 24h 영역 차트 (gen mix - 종목별 stacked area)
     · 컬러: 火力(amber), 原子力(red), 再エネ(green), 水力(blue)
   - 하단 테이블: 발전소 리스트 (이름 / 종목 / 출력 / 상태 pill / 시작시각)

3. 상태 pill
   - 稼働中 → --c-ok
   - 停止 → --c-bad
   - 計画停止 → --c-warn
   - 不明 → --fg-tertiary

[검증]
- 차트 렌더 + 테이블 데이터
- 정렬/필터 (테이블 기본 기능)
- 자동 갱신 (30분)
```

---

## 5.7 ─ text_memo (메모) ★

```
Phase 5.7: app/widgets/text_memo.py 에 새 디자인 적용.

[첨부]
- handoff/01-design-tokens.md
- handoff/02-components.md
- 모킹업: Memo 위젯 + Detail

[작업 내용]
1. MemoCard (대시보드)
   - LeeCard(accent_color="#FFCC00") (--c-memo)
   - "メモ" + 최근 3개 메모 미리보기 (제목만)
   - 우측 + 버튼 (새 메모)

2. MemoDetailPage
   - 좌측 (240px): 메모 리스트
     · 검색 input (상단)
     · 카드 리스트 (제목 + 미리보기 1줄 + 수정일)
     · 클릭 시 우측에 표시
     · 우클릭 → 컨텍스트 메뉴 (편집/삭제)
   - 우측: 에디터
     · 제목 input (--t-h2)
     · 본문 QTextEdit (markdown 미리보기 토글)
     · 하단 툴바: 저장 / 삭제 / 태그 / 마크다운 토글
   - 자동 저장 (3초 debounce)

3. 데이터 (SQLite — 기존 그대로)

4. 단축키
   - Ctrl+N: 새 메모
   - Ctrl+S: 저장
   - Ctrl+F: 검색 포커스
   - Delete: 선택 메모 삭제 (LeeDialog.confirm destructive)

[검증]
- CRUD 정상
- 검색 동작
- 자동 저장
- 마크다운 미리보기 토글
```

---

## 5.8 ─ notification (お知らせ) ★

```
Phase 5.8: app/widgets/notification.py 에 새 디자인 적용.

[첨부]
- handoff/01-design-tokens.md
- handoff/02-components.md
- 모킹업: Notice 카드 + Detail (브리핑 포함)

[작업 내용]
1. NotificationCard (대시보드)
   - LeeCard(accent_color="#FF9500") (--c-notice)
   - "お知らせ" + 안 읽은 알림 카운트 badge
   - 최근 3개 미리보기 (icon + title + 시각)

2. NotificationDetailPage
   - 상단: 필터 Segment [全て] [未読] [重要]
   - 리스트 (카드 형태)
     · 좌: 종류별 아이콘 (info/warn/error/success)
     · 중: title + 본문 1~2줄 + 시각
     · 우: 읽음 표시 dot
   - 하단: "全て既読にする" 버튼

3. 브리핑 영역 (특별 섹션)
   - 今週 / 今月 / 来月 브리핑 카드 3개
   - 각 카드: AI 생성 텍스트 + "再読み込み" / "削除" 버튼
   - 보존 (DB) — 사용자가 삭제하지 않으면 재방문 시 그대로

4. 데이터
   - notification_db.py (기존)
   - briefing_db.py (기존 또는 신설)

[검증]
- 알림 표시 + 읽음 처리
- 브리핑 3종 보존 + 재읽기 + 삭제
- 자동 갱신
```

---

## 5.9 ─ ai_chat (AI チャット) ★★

```
Phase 5.9: app/widgets/ai_chat.py 에 새 디자인 적용.

[첨부]
- handoff/01-design-tokens.md
- handoff/02-components.md
- 모킹업: AI Chat Detail (메시지 버블 디자인)

[작업 내용]
1. AiChatCard (대시보드)
   - LeeCard(accent_color="#5856D6") (--c-ai)
   - "AI アシスタント" + 최근 질문 1줄 미리보기
   - + 버튼 (새 채팅)

2. AiChatDetailPage
   - 좌측 (240px): 대화 세션 리스트
     · "新規チャット" 버튼
     · 세션 카드 (제목 + 마지막 메시지 + 시각)
     · 우클릭 → 이름변경 / 삭제
   - 우측: 채팅 영역
     · 상단 헤더 (세션 제목 + 모델 selector)
     · 메시지 리스트 (스크롤)
       - User 버블: 우측 정렬, --c-ai 배경, white text
       - AI 버블: 좌측 정렬, --bg-surface-2 배경, --fg-primary
       - 코드 블록: --font-mono + --bg-surface-3 + 복사 버튼
     · 하단 입력
       - QTextEdit (자동 높이 1~5줄)
       - 우측: 보내기 버튼 (Enter / Shift+Enter for newline)

3. 스트리밍 응답
   - 기존 LLM 호출 함수 그대로
   - 토큰 단위로 메시지 버블 업데이트 (애니메이션)

4. 모델 selector
   - GPT-4 / Claude / Gemini 등 (기존 설정 유지)

[검증]
- 메시지 송수신
- 스트리밍 표시
- 코드 블록 복사
- 세션 CRUD
- 모델 변경
```

---

## 5.10 ─ bug_report (バグ報告) ★★

```
Phase 5.10: app/widgets/bug_report.py 에 새 디자인 적용.

[첨부]
- handoff/01-design-tokens.md
- handoff/02-components.md
- 모킹업: Bug 위젯 (일반 사용자 / 관리자 분기)

[작업 내용]
1. 권한 분기
   - is_admin = user.role == "admin" 등으로 체크
   - 일반 사용자 → 송신 폼만
   - 관리자 → 전체 화면 (보고 리스트 + 처리)

2. 일반 사용자 화면 (BugReportFormPage)
   - 상단 인포 카드 ("불편한 점이나 버그를 알려주세요")
   - 폼:
     · カテゴリ (selector: バグ/要望/質問/その他)
     · 件名 (LeeLineEdit)
     · 詳細 (LeeTextEdit, 큰 영역)
     · スクリーンショット 첨부 (드래그앤드롭 + 클릭)
     · 자동 첨부 정보 미리보기 (앱 버전, OS, 화면 정보 — toggle)
   - 하단: "送信する" 버튼 (LeeButton primary)
   - 송신 결과: 성공/에러 토스트 (Phase 6 이후 임시 LeeDialog)

3. 관리자 화면 (BugReportAdminPage)
   - 상단: 통계 (전체/미처리/처리중/완료 카운트 카드)
   - 좌측: 필터 패널 (상태/카테고리/기간)
   - 중앙: 보고 테이블 (ID / 件名 / 신고자 / 상태 / 우선도 / 일자)
   - 우측 (선택 시): 상세 패널 (본문 + 스크린샷 + 댓글 + 상태 변경)

4. 데이터
   - 기존 bug DB (SQLite 또는 Google Sheets)

[검증]
- 일반 사용자: 폼 송신 정상
- 관리자: 전체 화면 + 상태 변경
- 스크린샷 첨부 동작
```

---

## 5.11 ─ manual (업무 매뉴얼) ★★★

```
Phase 5.11: app/widgets/manual.py 에 새 디자인 적용.

[첨부]
- handoff/01-design-tokens.md
- handoff/02-components.md
- 모킹업: Manual Detail (카테고리 매니저, 이미지 편집, 프리뷰 다이얼로그 포함)

[작업 내용]
1. ManualCard (대시보드 — 옵션, 보통은 사이드바 항목)
   - 가벼운 카드 — "業務マニュアル" + 최근 본 항목

2. ManualDetailPage
   - 좌측 (280px): 카테고리 트리
     · 카테고리별 매뉴얼 리스트
     · 검색 (전체 텍스트)
     · 관리자: + 카테고리 / + 매뉴얼 버튼
   - 중앙: 매뉴얼 viewer
     · 제목 + 메타 (작성자/일자/태그)
     · 본문 (마크다운 렌더 또는 리치텍스트)
     · 이미지 인라인 표시 — 클릭 시 ImagePreviewDialog
   - 우측 (옵션, 관리자만): 편집 패널

3. ImageEditDialog (LeeDialog 베이스)
   - 5 툴 (포인터/펜/사각형/원/텍스트)
   - 6 컬러 선택 (--c-power, --c-ok, --c-warn, --c-bad, white, black)
   - 굵기 슬라이더 (1~10)
   - 캔버스 (QGraphicsScene)
   - 하단: 저장 / 취소

4. ImagePreviewDialog (LeeDialog 베이스)
   - 줌 컨트롤 (+ / − / fit / 100%)
   - 메타데이터 (파일명/크기/해상도)
   - 휠 줌, 드래그 팬

5. CategoryManageDialog (LeeDialog 베이스)
   - 좌측 카테고리 리스트
   - 우측 액션 (이름변경/삭제/이동)
   - SYSTEM 카테고리는 보호 (편집/삭제 불가, 라벨 표시)

6. 데이터
   - Google Drive 동기화 (기존 manual_sync.py 등)
   - 모든 사용자 공통 열람 / 관리자만 편집

[검증]
- 일반 사용자: 열람 + 검색
- 관리자: CRUD + 카테고리 관리 + 이미지 편집/프리뷰
- Google Drive 동기화
```

---

## 5.12 ─ log_viewer (로그) ★★

```
Phase 5.12: app/widgets/log_viewer.py 에 새 디자인 적용.

[첨부]
- handoff/01-design-tokens.md
- handoff/02-components.md
- 모킹업: Log Detail

[작업 내용]
1. LogViewerPage (사이드바 항목)
   - 상단 툴바:
     · 레벨 필터 (Segment: ALL / DEBUG / INFO / WARN / ERROR)
     · 검색 input
     · 기간 selector (1h / 24h / 7d / Custom)
     · 새로고침 버튼
     · 실시간 토글 (auto-tail)
   - 본문: 로그 테이블 (가상 스크롤 — QTableView + Model)
     · 컬럼: 시각 (mono) / 레벨 (pill) / 모듈 / 메시지
     · 행 클릭 → 하단 상세 패널 (전체 traceback + context)
     · 우클릭 → 복사 / 필터 추가 / 즐겨찾기
   - 레벨별 컬러
     · DEBUG → --fg-tertiary
     · INFO → --c-info
     · WARN → --c-warn
     · ERROR → --c-bad

2. 데이터
   - logs/ 폴더 + 회전 로그 (logging.handlers.RotatingFileHandler 등)
   - 또는 SQLite log DB

3. 다운로드 버튼
   - 현재 필터된 로그를 .txt 또는 .csv로 export

[검증]
- 필터 동작 (레벨/검색/기간)
- 실시간 토글 (1초 polling 또는 watchdog)
- 가상 스크롤 (10만+ 행도 부드럽게)
- 다운로드 정상
```

---

## 5.13 ─ gmail (Gmail) ★★★★

```
Phase 5.13: app/widgets/gmail.py 에 새 디자인 적용.

[첨부]
- handoff/01-design-tokens.md
- handoff/02-components.md
- handoff/03-screen-specs.md (§7 Gmail 3-pane)
- 모킹업: Gmail Detail (3-pane + 검색 + 라벨 + 다중선택)

[작업 내용]
1. GmailCard (대시보드)
   - LeeCard(accent_color="#EA4335") (--c-mail)
   - "Gmail" + 안 읽은 메일 카운트
   - 최근 3개 메일 미리보기 (보낸이 + 제목)
   - 클릭 시 detail로

2. GmailDetailPage — 3-pane 레이아웃
   - 좌측 (200px): 라벨 + 카운트
     · INBOX / STARRED / SENT / DRAFTS / SPAM / TRASH
     · 사용자 라벨 (Gmail API에서 fetch)
     · 멀티 토글 (Ctrl+클릭으로 다중)
     · 라벨 컬러는 Gmail 라벨 컬러 그대로 (또는 토큰 매핑)
   - 중앙 (380px): 메일 리스트
     · 검색 input (상단, Ctrl+F 포커스)
     · 일괄 액션 툴바 (전체 선택 / 既読 / アーカイブ / 削除)
     · 메일 항목:
       - 체크박스
       - 별표 (스타)
       - 보낸이 (--t-body-strong)
       - 제목 + 미리보기 (--fg-secondary)
       - 라벨 칩들
       - 시각 (오늘=시각 / 어제="昨日" / 그외=日付)
     · 안읽음 = bold + 좌측 dot
     · 무한 스크롤 (다음 페이지 fetch)
   - 우측 (가변): 메일 본문
     · 헤더 (제목 / 보낸이 / 받는이 / 시각)
     · 본문 (QWebEngineView 또는 QTextEdit HTML 모드)
     · 첨부 파일 칩들
     · 하단 액션 (返信 / 全員に返信 / 転送)

3. "전부 기독" 기능
   - 좌측 라벨 우클릭 → "이 라벨 전부 기독" → 일괄 markRead

4. 검색
   - Gmail 검색 쿼리 그대로 ("from:foo subject:bar 등")
   - 즉시 검색 (300ms debounce)

5. 다중 선택
   - 체크박스 클릭 → 멀티 선택
   - Shift+클릭 → 범위 선택
   - 일괄 액션 툴바 활성화

6. 데이터
   - Gmail API (기존 OAuth credentials 그대로)
   - 로컬 캐시 (SQLite)

[검증]
- 라벨 필터 + 다중 토글
- 검색 동작
- 메일 열람 (HTML 렌더)
- 일괄 액션 (既読 / 削除 / 라벨 변경)
- 무한 스크롤
- 자동 갱신 (5분, 또는 push)
```

---

## 5.14 ─ google_calendar (캘린더) ★★★★★

```
Phase 5.14: app/widgets/google_calendar.py 에 풀피처 캘린더 구현.

[첨부]
- handoff/01-design-tokens.md
- handoff/02-components.md
- handoff/03-screen-specs.md (§6 Calendar)
- 모킹업: Calendar Detail (월/주/일 뷰 + 드래그앤드롭 + Ctrl+드래그 복사)

[작업 내용]
1. CalendarCard (대시보드)
   - LeeCard(accent_color="#34C759") (--c-cal)
   - 미니 월 뷰 (이번 달)
   - 오늘의 이벤트 3개
   - 클릭 시 detail로

2. CalendarDetailPage
   - 상단 툴바
     · ← / → / Today
     · 현재 보기 라벨 ("2024年12月")
     · Segment: [月] [週] [日]
     · 우측: + 새 이벤트 / 캘린더 selector / 새로고침

   - 좌측 패널 (220px)
     · 미니 캘린더 (위)
     · "내 캘린더" 리스트 (체크박스 + 컬러 dot)
     · 즐겨찾는 일정

   - 중앙: 메인 캘린더 뷰 (QGraphicsView 베이스 강력 추천)

3. **월 뷰**
   - 6 row x 7 col 그리드
   - 각 셀: 일자 + 이벤트 칩들 (3개까지 + "他N件")
   - 오늘 셀 highlight
   - 드래그로 이벤트 day 변경 (다른 날짜로 drop)
   - 빈 영역 클릭 → 새 이벤트 다이얼로그

4. **주 뷰**
   - 24h x 7day 그리드
   - 시간 가이드라인 (--grid-line)
   - 이벤트 박스 (높이 = duration, 컬러 = 캘린더 색)
   - 드래그로 시간/날짜 이동
   - 우측 모서리 잡고 리사이즈 = duration 변경
   - **Ctrl+드래그 = 복사**
   - 빈 영역 드래그 = 새 이벤트 ghost box → 릴리즈 시 다이얼로그
   - 멀티-day 이벤트 (상단 all-day 영역에 가로 막대)

5. **일 뷰**
   - 24h x 1day (주 뷰의 1일 버전)

6. EventDialog (LeeDialog 베이스)
   - 제목 / 일정 (시작/종료) / 캘린더 selector / 위치 / 메모
   - 반복 설정 (없음/매일/매주/매월/사용자 정의)
   - 알림 (10분 전/30분 전/1시간 전)
   - 색상 (캘린더 색 또는 사용자 지정)
   - 삭제 (반복 시 "이 이벤트만/이후 모두/전체" LeeDialog confirm)

7. 데이터
   - Google Calendar API (기존)
   - 로컬 캐시 + 옵티미스틱 업데이트

8. 인터랙션 디테일
   - 호버 시 이벤트 강조 (border + shadow)
   - 다른 day로 drop 시 ghost preview
   - 시간 그리드 스냅 (15분 단위)

[검증]
- 3 뷰 모두 정상 렌더
- 드래그 이동 + 리사이즈 + Ctrl 복사
- 빈 영역 드래그 → 새 이벤트
- 반복 이벤트 처리 (특히 삭제)
- 멀티-day 이벤트 표시
- Google API 동기화 (생성/수정/삭제 양방향)
```

---

## 5.15 ─ dashboard (대시보드 통합) ★★★

```
Phase 5.15: app/widgets/dashboard.py — 16개 카드 모두를 통합한 대시보드 레이아웃.

[첨부]
- handoff/01-design-tokens.md
- handoff/02-components.md
- handoff/03-screen-specs.md (§2 Dashboard)
- 모킹업: 메인 대시보드 (Variation A)

[전제 — 매우 중요]
- 5.1 ~ 5.14 위젯의 *Card 컴포넌트가 모두 완성되어 있어야 함:
  PowerReserveCard / JepxSpotCard / ImbalanceCard / JkmCard /
  WeatherCard / HjksCard / MemoCard / NotificationCard /
  AiChatCard / BugReportCard / ManualCard / LogViewerCard /
  GmailCard / CalendarCard
- 각 카드는 동일한 인터페이스를 따라야 함:
  · clicked = Signal()  (detail로 이동)
  · refresh()           (수동 갱신)
  · set_data(...)       (데이터 갱신)

[작업 내용]
1. 상단 헤더 영역
   - "ようこそ、田中さん" (--t-h1)
   - 일자/시각 (--t-body, --fg-secondary)
   - 우측: 빠른 액션 버튼 (날씨/메일/설정 — Ghost variant)

2. KPI Row — 시장 주요 지표 (4 카드, equal width)
   - PowerReserveCard | JepxSpotCard | ImbalanceCard | JkmCard
   - QGridLayout (1 row, 4 col)
   - gap: var(--s-4) = 16px

3. Row 2 — 운영 정보 (3 컬럼, 다른 비율)
   - WeatherCard (1) | HjksCard (1.5) | CalendarCard (1.5)
   - QHBoxLayout + stretch factor

4. Row 3 — 소통/메모 (4 컬럼)
   - GmailCard | NotificationCard | MemoCard | AiChatCard
   - 각각 동일 폭

5. Row 4 — 시스템/관리 (컴팩트, 권한 분기)
   - 일반 사용자: ManualCard | LogViewerCard | (자리 없음)
   - 관리자: ManualCard | LogViewerCard | BugReportCard
   - Row 1보다 작은 하이트 (~70%)

   ⚠️ 모킹업 재확인 필요:
   - 만약 manual/log/bug가 사이드바에서만 접근하는 게 깔끔하다면
     Row 4를 빼고 사이드바에만 두는 것도 검토.
   - 모킹업의 최종 구성을 우선 따르기.

6. 카드 클릭 → 해당 detail page navigation
   - 모든 카드는 clicked signal 발산
   - DashboardPage가 받아서 main_window.navigate(page_name) 호출

7. 빈 상태 / 로딩 상태
   - 데이터 로딩 동안 skeleton (Phase 6에서 본격, 일단 placeholder OK)

8. 레이아웃 반응형 대응 (옵션 — Phase 6에서 강화)
   - 작은 윈도우 width 시 KPI Row를 2x2로 wrap
   - Row 4는 좋은 자리로 (하단 고정)

9. 자동 갱신 통합
   - 각 카드는 자체 QTimer로 자동 갱신 (Phase 5.1~5.14에서 구현)
   - 대시보드는 "全て更新" 버튼만 노출 (헤더 우측)

[검증]
- 14~16개 (권한별 조정된) 카드 모두 정상 렌더
- 카드 클릭 → 해당 detail 진입 (모든 라우팅 동작)
- 윈도우 리사이즈 시 레이아웃 깨짐 없음
- 관리자/일반 사용자 권한별 카드 가시성 차이
- 라이트/다크 토글 일관성
- 데이터 로딩 동안 placeholder 표시
- "全て更新" 버튼 → 모든 카드 동시 refresh()
```

---

## 5.16 ─ settings (설정) ★★★

```
Phase 5.16: app/widgets/settings.py 에 새 디자인 적용 (마지막 위젯).

[첨부]
- handoff/01-design-tokens.md
- handoff/02-components.md
- handoff/03-screen-specs.md (§5 Settings)
- 모킹업: Settings Detail (좌측 탭 + 우측 패널)

[전제]
- 5.1 ~ 5.15 위젯이 모두 settings_manager 의 자동 갱신 주기를 구독해야 함

[작업 내용]
1. SettingsPage 레이아웃 (좌측 탭 + 우측 패널)
   - 좌측 (220px): 카테고리 리스트
     · 一般 / 表示 / 自動更新 / 言語 / アカウント / 通知 / 高度な設定
   - 우측 (가변): 패널 (각 카테고리별)

2. 各 카테고리 별 SettingsRow 들
   - SettingsRow(icon, label, description, control_widget)
   - 좌: 28px 아이콘 타일 + 라벨 + 서브텍스트
   - 우: 컨트롤 (Toggle / Selector / Slider / Button)
   - hover: --bg-surface-2

3. 카테고리별 내용:

   a. **一般**
      - 起動時に自動起動 (Toggle)
      - トレイに常駐 (Toggle)
      - 終了確認 (Toggle)
      - データフォルダ (path + 변경 버튼)

   b. **表示**
      - テーマ (Light / Dark / System) Segment
      - 강조색 (--accent 변경) — color picker
      - 폰트 크기 (Slider 12~18pt)
      - 컴팩트 모드 (Toggle)

   c. **自動更新** ⭐ 핵심
      - 위젯별 갱신 주기 행 (각각 Slider + Preset chips)
        · 予備率: 1m / 5m / 15m / 30m / 1h
        · スポット: 5m / 15m / 30m
        · インバランス: 1m / 5m / 10m
        · JKM: 30m / 1h / 6h
        · 天気: 15m / 30m / 1h
        · HJKS: 30m / 1h
        · Gmail: 5m / 15m / 30m / Push
        · Calendar: 1m / 5m / 30m
      - 변경 시 settings_manager.set 호출 + 해당 위젯에 signal

   d. **言語**
      - 日本語 / English / 한국어 (Segment)
      - 변경 시 i18n 재로드 (앱 재시작 권유 또는 즉시 반영)

   e. **アカウント**
      - 사용자 정보 카드 (아바타 + 이름 + 이메일)
      - Google 연동 상태
      - 로그아웃 버튼 (LeeDialog.confirm destructive)

   f. **通知**
      - 데스크톱 알림 (Toggle)
      - 사운드 (Toggle)
      - 알림 항목 토글 (각 위젯별)
      - 임밸런스 임계값 (¥/kWh)

   g. **高度な設定**
      - 디버그 모드 (Toggle)
      - 캐시 지우기 (버튼)
      - 데이터 export (버튼)
      - 데이터 import (버튼)
      - factory reset (LeeDialog.confirm destructive)

4. 변경 사항 즉시 적용
   - settings_manager.set(key, value) → signal value_changed(key, value)
   - 각 위젯이 자기 키만 구독

5. 데이터
   - QSettings 또는 JSON 파일

[검증]
- 모든 설정 변경 → 즉시 적용 + 재시작 후 보존
- 자동 갱신 주기 변경 → 해당 위젯이 즉시 새 주기로 동작
- 다국어 전환
- 라이트/다크 토글
- 로그아웃 흐름
```

---

## 🏁 Phase 5 마무리

모든 위젯 마이그레이션 완료 후, 다음 검증 프롬프트를 사용:

```
Phase 5 완료 검증을 진행해주세요.

[작업 내용]
1. grep -r "QMessageBox" app/widgets/ — 잔존 0개 확인
2. grep -rE "(#[0-9A-Fa-f]{6}|background:\s*#)" app/widgets/ —
   하드코딩 컬러 잔존 확인 (있으면 토큰으로 치환)
3. 모든 위젯 진입 → 데이터 로드 → 자동 갱신 동작 확인
4. 라이트/다크 토글이 모든 위젯에서 일관성 있게 동작
5. 윈도우 리사이즈 (1280x800 ~ 1920x1080) 시 깨짐 없음
6. 회귀 테스트:
   - 로그인 흐름
   - 자동 업데이트 흐름
   - 트레이 종료
   - 데이터 보존 (메모/캘린더/채팅 세션)

각 항목 결과를 표로 정리해서 알려주세요.
```

---

## 🎯 다음 단계

Phase 5 완료 → **Phase 6 (폴리싱)** 으로 진행. `05-claude-code-prompts.md` 의 프롬프트 ⑧ 사용.
