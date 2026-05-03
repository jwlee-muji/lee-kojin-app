# 03. Screen Specs — 주요 화면 명세

> 각 주요 화면의 레이아웃, 인터랙션, PySide6 위젯 매핑.
> 디자인 모킹업은 `LEE 電力モニター - 2 Variations.html` 참조.

---

## 🪟 1. Main Window (메인 윈도우)

### 1.1 레이아웃

```
┌─────────────────────────────────────────────────────────────┐
│ [LOGO] LEE 電力モニター   [🔍] [Market▾] [Ops▾] [Tool▾]      │ ← TopBar 48px
├──────────────┬──────────────────────────────────────────────┤
│              │                                              │
│   Sidebar    │   Main Stage (QStackedWidget)                │
│              │                                              │
│   ┌─────┐    │   - Dashboard (default)                      │
│   │Tab A│    │   - Spot Detail                              │
│   ├─────┤    │   - Reserve Detail                           │
│   │Tab B│    │   - ...                                      │
│   └─────┘    │                                              │
│              │                                              │
│   • 위젯1     │                                              │
│   • 위젯2     │                                              │
│   • 위젯3     │                                              │
│              │                                              │
│   [User⚙]    │                                              │
└──────────────┴──────────────────────────────────────────────┘
   240px              가변
```

### 1.2 PySide6 구조

```python
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"LEE 個人アプリ v{__version__}")

        # Central
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # TopBar
        self.topbar = TopBar()
        root.addWidget(self.topbar)

        # Body: sidebar + stage
        body = QHBoxLayout(); body.setContentsMargins(0,0,0,0); body.setSpacing(0)
        self.sidebar = Sidebar()
        self.stage = QStackedWidget()
        body.addWidget(self.sidebar)
        body.addWidget(self.stage, 1)
        root.addLayout(body)

        # Pages
        self.pages = {
            "dashboard": DashboardPage(),
            "spot": SpotDetailPage(),
            ...
        }
        for p in self.pages.values():
            self.stage.addWidget(p)

        self.sidebar.item_clicked.connect(self._navigate)
```

### 1.3 인터랙션

- **사이드바 위젯 클릭** → 해당 detail page로 navigate (stage.setCurrentWidget)
- **Back 버튼** → dashboard로 복귀
- **TopBar 검색** → 글로벌 검색 (Spotlight 풍)
- **Top Tabs (Market/Ops/Tool)** → 해당 카테고리 위젯 그룹 표시 (사이드바 필터)

### 1.4 closeEvent

`LeeDialog` 의 3-button 변형 (커스텀):
- 트레이에 최소화 (default, ActionRole)
- 完全に終了 (DestructiveRole)
- キャンセル (RejectRole)

---

## 🏠 2. Dashboard

### 2.1 레이아웃 (Variation A — 채택)

```
┌──────────────────────────────────────────────────┐
│ ようこそ、田中さん                                │
│ 2024年12月15日(日) · 7:30 AM JST                  │
├──────────────────────────────────────────────────┤
│ [Reserve Card][Spot Card][Imbalance Card][JKM]   │ ← KPI Row (4 cards)
├──────────────────────────────────────────────────┤
│ ┌─Weather─┐ ┌──────HJKS──────┐ ┌──Calendar──┐    │
│ │  ☀️    │ │   chart        │ │  [mini]    │    │
│ │  18°C  │ │                │ │            │    │
│ └────────┘ └────────────────┘ └────────────┘    │
├──────────────────────────────────────────────────┤
│ ┌──Gmail──┐ ┌──Notice──┐ ┌──Memo──┐ ┌──AI──┐    │
│ │ • mail1 │ │ • notice │ │ memo   │ │ chat │    │
│ │ • mail2 │ │          │ │        │ │      │    │
│ └─────────┘ └──────────┘ └────────┘ └──────┘    │
└──────────────────────────────────────────────────┘
```

### 2.2 카드별 동작

| 카드 | 클릭 시 | 자동 갱신 |
|---|---|---|
| Reserve | → reserve_detail | 5분 |
| Spot | → spot_detail | 5분 |
| Imbalance | → imbalance_detail | 1분 |
| JKM | → jkm_detail | 30분 |
| Weather | → weather_detail | 15분 |
| HJKS | → hjks_detail | 30분 |
| Calendar | → calendar_detail | onLoad + manual |
| Gmail | → gmail_detail | 5분 (push 옵션) |

각 주기는 settings에서 사용자 변경 가능.

---

## 🔐 3. Login Window (A+ Refined Dark)

### 3.1 Spec

- **480 × 580** 고정 윈도우
- **다크 베이스** + 우상단 오렌지 글로우 + 좌하단 오렌지 빛무리
- 좌상단 브랜드 헤더: `[icon] LEE 電力モニター / POWER MARKET INTEL · v3.4.2`
- 미세 그리드 텍스처 (4% 투명도)
- 푸터: `© Shirokuma Power · jw.lee@shirokumapower.com`

### 3.2 페이지

1. **로그인** — Google OAuth 버튼 + "アクセスを申請" 링크
2. **未登録** — 경고 아이콘 + 이메일 칩 + 申請 버튼
3. **인증중** — 스피너 + 캔슬 버튼

### 3.3 PySide6

`QMainWindow` 서브클래스 (현행). 윈도우 외곽선 제거 + paintEvent 로 그라데이션 그리기:

```python
class LoginWindow(QMainWindow):
    def paintEvent(self, ev):
        p = QPainter(self)
        # 1. 베이스 라디얼 그라데이션 (어두운 갈색 → 표면색)
        grad = QRadialGradient(self.width(), 0, self.width()*1.4)
        grad.setColorAt(0, QColor("#2a1410"))
        grad.setColorAt(0.35, QColor("#160c0a"))
        grad.setColorAt(0.7, QColor("#14161C"))
        p.fillRect(self.rect(), grad)
        # 2. 좌하단 오렌지 빛무리
        glow = QRadialGradient(0, self.height(), self.width()*0.7)
        glow.setColorAt(0, QColor(255,159,10,56))
        glow.setColorAt(1, QColor(255,159,10,0))
        p.fillRect(self.rect(), glow)
```

---

## 🪟 4. System Dialogs (모두 LeeDialog 베이스)

### 4.1 매핑 표

| 모킹업 다이얼로그 | 기존 코드 위치 | 새 코드 |
|---|---|---|
| アップデートのお知らせ | updater.py:201 `QMessageBox.question` | `LeeDialog.confirm()` 또는 전용 `UpdateAvailableDialog` |
| ダウンロード中 | updater.py:215 `QProgressDialog` | 전용 `UpdateProgressDialog` (LeeDialog 베이스) |
| 準備完了 | updater.py:245 `QMessageBox.information` | `LeeDialog.info()` |
| ダウンロードエラー | updater.py:260 `QMessageBox.warning` | `LeeDialog.error(details=...)` |
| 終了の確認 | main_window.py:879 `QMessageBox` | 전용 `QuitConfirmDialog` (3 버튼) |
| ログアウト | main_window.py:911 `QMessageBox` | `LeeDialog.confirm(destructive=True)` |
| 起動エラー | main.py:108 `QMessageBox.critical` | `LeeDialog.error(details=traceback)` |
| 削除の確認 (manual/cal/etc) | 多数 | `LeeDialog.confirm(destructive=True)` |
| アクセスを申請 | login_window.py:73 (커스텀 QDialog) | 디자인 적용해 리뉴얼 |
| カテゴリ管理 | manual.py:412 | 디자인 적용해 리뉴얼 |
| 画像編集 | manual.py:259 | 디자인 적용해 리뉴얼 |
| 画像プレビュー | manual.py:1578 | 디자인 적용해 리뉴얼 |

### 4.2 일반 메시지박스 변환 우선순위

가장 많이 사용된 패턴부터:

1. `QMessageBox.warning(self, "エラー", err_msg)` (10+곳) → `LeeDialog.error()`
2. `QMessageBox.question(...) Yes/No` (5+곳) → `LeeDialog.confirm()`
3. `QMessageBox.information(...)` (3+곳) → `LeeDialog.info()`

---

## 🎚️ 5. Settings (リニューアル 완료)

### 5.1 좌측 카테고리 + 우측 패널 구조

```
┌────────┬─────────────────────────────┐
│        │  [Section Title]            │
│ Tab A  │  ─────────────────          │
│ Tab B  │   ICON  Setting label       │
│ Tab C  │         description         │
│ ...    │                  [control]  │
│        │  ─────────────────          │
│        │                             │
└────────┴─────────────────────────────┘
```

탭들: 一般 / 表示 / 自動更新 / 言語 / アカウント / 通知 / 高度な設定

### 5.2 자동 갱신 주기

각 위젯별 주기를 슬라이더 + presets (1m / 5m / 15m / 30m / 1h)로 노출. 디자인 모킹업의 settings detail 참조.

---

## 📅 6. Calendar Detail

### 6.1 뷰

- **月** (default) — 6 row x 7 col grid
- **週** — 24h timeline x 7일
- **日** — 24h timeline x 1일

### 6.2 인터랙션

- 드래그로 이동 (시간/날짜 변경)
- Ctrl+드래그로 복사
- 우측 모서리 잡고 리사이즈 (지속시간 변경)
- 빈 영역 드래그 → 새 이벤트 ghost box → 릴리즈 시 다이얼로그
- 멀티-day 이벤트 가능

### 6.3 PySide6

`QGraphicsView` + `QGraphicsScene` 가 가장 자연스러움. QCalendarWidget는 표시 전용으로 부족.

---

## 📧 7. Gmail Detail

### 7.1 3-pane 레이아웃

```
┌────────┬───────────────┬──────────────────┐
│ Labels │ Mail List     │ Detail (preview) │
│        │               │                  │
│ INBOX  │ □ subject 1   │  Subject         │
│ SENT   │ □ subject 2   │  From / To       │
│ STAR   │ ▣ subject 3   │  ───             │
│ ...    │               │  body            │
└────────┴───────────────┴──────────────────┘
```

- 검색 바 (상단)
- 라벨 멀티 토글
- 다중 선택 + 일괄 처리
- "전부 기독" 버튼 (모든 메일 읽음 처리)

---

## 📝 8. Notes for Migration

### 8.1 기존 화면 → 새 디자인 차이

| 항목 | As-is | To-be |
|---|---|---|
| 로그인 | 일반 폼 | A+ Refined Dark (브랜드 헤더 + 글로우) |
| 다이얼로그 | QMessageBox 기본 | LeeDialog (커스텀 프레임 + 컬러 아이콘) |
| 사이드바 | 단일 리스트 | 상단 탭 (Market/Ops/Tool) + 카테고리별 그룹 + 그룹 접기 |
| 캘린더 | 기본 표시 | 풀피처 드래그앤드롭 + 다중뷰 |
| 설정 | 1열 폼 | 좌측 탭 + 우측 행 + 자동 갱신 주기 슬라이더 |

### 8.2 새로 추가할 동작

- ☑ Top tabs로 위젯 카테고리 필터링
- ☑ 사이드바 위젯 그룹 접기 (▾/▸)
- ☑ 모던 스크롤바 (자체 그림)
- ☑ 모든 date input에 공통 미니 캘린더 popup
- ☑ 토스트 알림 시스템 (QGraphicsOpacityEffect 애니메이션)

---

## 📝 PySide6 위젯 매핑 치트시트

| 디자인 컴포넌트 | PySide6 위젯 |
|---|---|
| Card | `QFrame` + objectName + QSS |
| Button | `QPushButton` + dynamic property |
| Dialog | `QDialog` 서브클래스 (`LeeDialog`) |
| List Item | `QPushButton` (checkable) in `QButtonGroup` |
| Pill / Badge | `QLabel` + objectName |
| Tab | `QStackedWidget` + 커스텀 탭 헤더 (`QButtonGroup`) |
| Toast | `QFrame` (popup) + `QGraphicsOpacityEffect` |
| Mini Calendar | `QCalendarWidget` 또는 커스텀 |
| Segmented Control | `QButtonGroup` + checkable QPushButton |
| Sparkline / Chart | `QChartView` (QtCharts) 또는 `QPainter` 직접 |
| Animation | `QPropertyAnimation` + easing curve |
