# 01. Design Tokens — 디자인 토큰

> 모든 컬러, 간격, 타이포 값의 **단일 진실원**. 코드에서는 항상 이 토큰을 참조해야 함.
> 하드코딩된 `#5B8DEF`, `padding: 12px` 같은 값은 절대 금지.

## 🎨 1. Color Tokens

### 1.1 Indicator Colors (지표별 고유 컬러 — 라이트/다크 공통)

각 지표 위젯의 정체성 컬러. 라이트/다크 모드 둘 다 같은 hex (눈높이 컬러).

| Token | Hex | 의미 | 용도 |
|---|---|---|---|
| `--c-power` | `#5B8DEF` | 電力予備率 — 신뢰의 파랑 | 예비율 카드 left-border, 차트 라인 |
| `--c-power-soft` | `#DCE7FB` | (soft 버전) | 라이트 모드 배지 배경 |
| `--c-spot` | `#FF7A45` | JEPXスポット — 활기 오렌지 | 스팟 카드 + **앱 액센트 (Primary)** |
| `--c-spot-soft` | `#FFE4D6` | | |
| `--c-imb` | `#F25C7A` | インバランス — 알람 빨강 | 임밸런스 카드 |
| `--c-imb-soft` | `#FFE0E6` | | |
| `--c-jkm` | `#F4B740` | JKM LNG — 연료 앰버 | JKM 카드 |
| `--c-jkm-soft` | `#FFEFD0` | | |
| `--c-weather` | `#2EC4B6` | 天気 — 청량 틸 | 날씨 위젯 |
| `--c-weather-soft` | `#D2F4F0` | | |
| `--c-hjks` | `#A78BFA` | 発電稼働 — 보라 | HJKS 위젯 |
| `--c-hjks-soft` | `#EBE3FE` | | |
| `--c-cal` | `#34C759` | カレンダー — iOS 그린 | 캘린더 |
| `--c-cal-soft` | `#DAF6E1` | | |
| `--c-mail` | `#EA4335` | Gmail — 구글 빨강 | Gmail 위젯 |
| `--c-mail-soft` | `#FCE0DD` | | |
| `--c-ai` | `#5856D6` | AI — iOS 인디고 | AI 챗 |
| `--c-ai-soft` | `#E1E0F8` | | |
| `--c-memo` | `#FFCC00` | メモ — 노트 옐로 | 메모 |
| `--c-memo-soft` | `#FFF4C2` | | |
| `--c-notice` | `#FF9500` | 通知 — iOS 오렌지 | 알림 |
| `--c-notice-soft` | `#FFE7C7` | | |

### 1.2 Semantic Colors (의미 기반)

| Token | Hex | 용도 |
|---|---|---|
| `--c-ok` | `#30D158` | 성공, 양호, 정상 |
| `--c-warn` | `#FF9F0A` | 주의, 경고 |
| `--c-bad` | `#FF453A` | 에러, 위험, 삭제 |
| `--c-info` | `#0A84FF` | 정보 |
| `--accent` | `var(--c-spot)` | **앱 전체 액센트** (= JEPX 오렌지) |

### 1.3 Surface (배경)

| Token | Light | Dark | 용도 |
|---|---|---|---|
| `--bg-app` | `#F5F6F8` | `#0A0B0F` | 앱 베이스 배경 |
| `--bg-surface` | `#FFFFFF` | `#14161C` | 카드, 다이얼로그 |
| `--bg-surface-2` | `#F0F2F5` | `#1B1E26` | sunken (인풋, 푸터) |
| `--bg-surface-3` | `#E6E9EE` | `#232730` | deeper sunken (스켈레톤) |
| `--bg-elevated` | `#FFFFFF` | `#1B1E26` | 띄운 면 (메뉴, 토스트) |
| `--bg-input` | `#FFFFFF` | `#1B1E26` | 입력 필드 |

### 1.4 Foreground (전경/텍스트)

| Token | Light | Dark | 용도 |
|---|---|---|---|
| `--fg-primary` | `#0B1220` | `#F2F4F7` | 본문 |
| `--fg-secondary` | `#4A5567` | `#A8B0BD` | 보조 (라벨) |
| `--fg-tertiary` | `#8A93A6` | `#6B7280` | 캡션, 메타 |
| `--fg-quaternary` | `#C2C8D2` | `#3D424D` | placeholder, disabled |
| `--fg-on-accent` | `#FFFFFF` | `#FFFFFF` | accent 위 텍스트 |

### 1.5 Border

| Token | Light | Dark | 용도 |
|---|---|---|---|
| `--border-subtle` | `rgba(11,18,32,.06)` | `rgba(255,255,255,.04)` | 카드 hairline |
| `--border` | `rgba(11,18,32,.10)` | `rgba(255,255,255,.08)` | 일반 보더, 입력 |
| `--border-strong` | `rgba(11,18,32,.18)` | `rgba(255,255,255,.14)` | 강조 보더, 구분선 |

---

## 📏 2. Spacing

| Token | px | 용도 |
|---|---|---|
| `--s-1` | 4 | tight (icon ↔ text) |
| `--s-2` | 8 | small gap |
| `--s-3` | 12 | default gap |
| `--s-4` | 16 | medium |
| `--s-5` | 20 | medium-large |
| `--s-6` | 24 | large (카드 내부 패딩) |
| `--s-8` | 32 | section gap |
| `--s-10` | 40 | large section |
| `--s-12` | 48 | XL |

**규칙**: 모든 패딩/마진은 위 값 사용. 4의 배수 외 사용 금지.

---

## 🔘 3. Radius

| Token | px | 용도 |
|---|---|---|
| `--r-xs` | 6 | 입력, 작은 버튼 |
| `--r-sm` | 10 | 일반 버튼, 칩 |
| `--r-md` | 14 | 작은 카드, 다이얼로그 헤더 |
| `--r-lg` | 20 | **카드 (기본)** |
| `--r-xl` | 28 | 큰 모달, 위젯 |
| `--r-2xl` | 36 | 마케팅 hero |
| `--r-pill` | 999 | pill, dot, avatar |

---

## ✏️ 4. Typography

### 4.1 Fonts

```css
--font-sans:    'Pretendard', 'Noto Sans JP', -apple-system, sans-serif;
--font-mono:    'JetBrains Mono', 'SF Mono', ui-monospace, monospace;
--font-display: 'Pretendard', 'Noto Sans JP', sans-serif;
```

PySide6에서는 `QFont("Pretendard", ...)` + fallback 체인.

### 4.2 Type Scale

| Class / Use | Size | Weight | Letter | Line | 용도 |
|---|---|---|---|---|---|
| `t-display` | 44 | 700 | -2% | 1.1 | hero 숫자 |
| `t-h1` | 28 | 700 | -1.5% | 1.2 | 화면 타이틀 |
| `t-h2` | 20 | 700 | -1% | 1.3 | 섹션 타이틀 |
| `t-h3` | 16 | 600 | 0 | 1.4 | 카드 타이틀 |
| `t-body-strong` | 14 | 600 | 0 | 1.5 | 본문 강조 |
| `t-body` | 14 | 400 | 0 | 1.5 | 본문 |
| `t-small` | 12 | 500 | 0 | 1.4 | 보조 |
| `t-tiny` | 11 | 600 | +4% UPPER | 1.3 | 라벨 (TAG) |
| `t-mono` | (상속) | (상속) | tnum | (상속) | 숫자 표시 |

**중요**: 숫자(가격/델타/시간)는 항상 `font-mono` + `tnum` (등폭 숫자) 적용.

---

## ☁️ 5. Shadow

| Token | Light | Dark | 용도 |
|---|---|---|---|
| `--shadow-sm` | hairline | `0 1px 2px rgba(0,0,0,.5)` | 카드 |
| `--shadow-md` | soft | `0 4px 8px rgba(0,0,0,.3)` | 호버, 떠 있는 면 |
| `--shadow-lg` | strong | `0 8px 16px rgba(0,0,0,.4)` | 모달, 다이얼로그 |
| `--shadow-glow` | accent ring | accent ring | 포커스 |

---

## 🐍 6. PySide6 매핑 가이드

### 6.1 QSS 변수화 전략

PySide6는 CSS variables를 직접 지원하지 않음. 대신 두 가지 방식 권장:

**방식 A — Python에서 QSS 템플릿 치환 (권장)**

```python
# app/ui/theme.py
TOKENS_DARK = {
    "bg_app":      "#0A0B0F",
    "bg_surface":  "#14161C",
    "fg_primary":  "#F2F4F7",
    "accent":      "#FF7A45",
    # ... 전체
}

QSS_TEMPLATE = """
QWidget {{
  background: {bg_app};
  color: {fg_primary};
  font-family: 'Pretendard', 'Noto Sans JP';
}}
QPushButton#primaryActionBtn {{
  background: {accent};
  color: white;
  border-radius: 10px;
  padding: 0 18px;
  min-height: 36px;
  font-weight: 700;
}}
"""

def get_global_qss(theme: str = "dark") -> str:
    tokens = TOKENS_DARK if theme == "dark" else TOKENS_LIGHT
    return QSS_TEMPLATE.format(**tokens)
```

**방식 B — QPalette + dynamic property**

`QApplication.setPalette(palette)` + Property Selector
```python
btn.setProperty("variant", "primary")
btn.style().unpolish(btn); btn.style().polish(btn)
```

QSS:
```css
QPushButton[variant="primary"] { background: #FF7A45; }
```

### 6.2 폰트 로딩

```python
from PySide6.QtGui import QFontDatabase

QFontDatabase.addApplicationFont(":/fonts/Pretendard-Regular.otf")
QFontDatabase.addApplicationFont(":/fonts/Pretendard-Bold.otf")
QFontDatabase.addApplicationFont(":/fonts/JetBrainsMono-Regular.ttf")
app.setFont(QFont("Pretendard", 9))
```

폰트 라이선스: Pretendard (OFL), JetBrains Mono (OFL), Noto Sans JP (OFL) 모두 무료 임베드 가능.

### 6.3 라이트/다크 동적 스위칭

```python
class ThemeManager(QObject):
    theme_changed = Signal(str)
    def set_theme(self, theme: str):  # "light" | "dark"
        QApplication.instance().setStyleSheet(get_global_qss(theme))
        self.theme_changed.emit(theme)
```

### 6.4 컬러 사용 예제

| 디자인 | PySide6 코드 |
|---|---|
| `var(--accent)` | `tokens["accent"]` (`#FF7A45`) |
| `var(--fg-secondary)` | `tokens["fg_secondary"]` |
| `var(--bg-surface)` | 보통 `QFrame` 의 stylesheet `background: ...` |
| `border-radius: var(--r-lg)` | `border-radius: 20px;` (QSS) |

---

## ✅ 체크리스트

- [ ] `app/ui/theme.py` 에 `TOKENS_DARK / TOKENS_LIGHT` 딕셔너리 정의
- [ ] `QSS_TEMPLATE` 작성 — 위 모든 토큰 매핑
- [ ] Pretendard / JetBrains Mono `.qrc` 에 등록
- [ ] `main.py` 에서 폰트 + 테마 적용
- [ ] 기존 하드코딩된 색상 → grep 으로 모두 발견 후 토큰으로 치환
