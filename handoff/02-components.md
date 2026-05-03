# 02. Components — 컴포넌트 스펙 시트

> 모든 재사용 컴포넌트의 시각·동작 사양. PySide6 위젯 클래스로 1:1 매핑.

---

## 🔘 1. Button

### 1.1 Variants

| Variant | 용도 | 배경 | 텍스트 | 보더 |
|---|---|---|---|---|
| `primary` | 주요 액션 | `var(--accent)` | white | accent 60% |
| `secondary` | 부수 액션 | `var(--bg-surface)` | `var(--fg-primary)` | `var(--border)` |
| `destructive` | 삭제, 종료 | `#FF453A` | white | `#FF453A` |
| `ghost` | 취소, 부정적 | transparent | `var(--fg-secondary)` | transparent |

### 1.2 Sizes

| Size | Height | Padding-X | Font | Radius |
|---|---|---|---|---|
| `sm` | 28 | 12 | 11/700 | 6 |
| `md` | 36 | 18 | 12/700 | 8 |
| `lg` | 44 | 22 | 14/700 | 10 |

### 1.3 States

- **hover**: `filter: brightness(1.1)` (단색) 또는 background tint shift
- **pressed**: `filter: brightness(0.95)` + 1px translateY
- **disabled**: `opacity: 0.4` + `cursor: not-allowed`
- **focus**: `outline: 2px var(--accent)` (키보드 포커스)
- **loading**: 텍스트 → 스피너 + "送信中..." 등

### 1.4 PySide6 매핑

```python
class LeeButton(QPushButton):
    def __init__(self, text="", variant="secondary", size="md", parent=None):
        super().__init__(text, parent)
        self.setProperty("variant", variant)
        self.setProperty("size", size)
        self.setCursor(Qt.PointingHandCursor)

# QSS
"""
QPushButton[variant="primary"][size="md"] {
  background: #FF7A45;
  color: white;
  border: 1px solid rgba(255,122,69,0.6);
  border-radius: 8px;
  padding: 0 18px;
  min-height: 36px;
  font-size: 12px;
  font-weight: 700;
}
QPushButton[variant="primary"]:hover { background: #FF8A55; }
QPushButton[variant="primary"]:pressed { background: #E66C3D; }
QPushButton[variant="primary"]:disabled { color: rgba(255,255,255,0.4); background: rgba(255,122,69,0.4); }

QPushButton[variant="destructive"]  { background: #FF453A; color: white; ... }
QPushButton[variant="secondary"]    { background: var-bg; color: var-fg; border: 1px solid var-border; }
QPushButton[variant="ghost"]        { background: transparent; color: var-fg-secondary; border: 0; }
"""
```

---

## 🃏 2. Card (lee-card)

### 2.1 Spec

```css
.lee-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: 20px;     /* var(--r-lg) */
  box-shadow: var(--shadow-sm);
  padding: 20px 24px;       /* default */
}
```

### 2.2 변형

- **카드 (강조)** — 좌측에 4px wide accent bar (`border-left: 4px solid var(--c-power)`)
- **interactive 카드** — hover 시 `box-shadow → md`, `transform: translateY(-1px)`, transition `120ms`
- **빈 상태 (empty)** — `border: 1px dashed var(--border)`, 패턴 텍스처 또는 일러스트

### 2.3 PySide6

```python
class LeeCard(QFrame):
    def __init__(self, accent_color=None, interactive=False, parent=None):
        super().__init__(parent)
        self.setObjectName("leeCard")
        if accent_color:
            self.setProperty("accentColor", accent_color)
        if interactive:
            self.setProperty("interactive", "true")
            self.setCursor(Qt.PointingHandCursor)

# QSS
"""
QFrame#leeCard {
  background: #14161C;
  border: 1px solid rgba(255,255,255,0.04);
  border-radius: 20px;
}
QFrame#leeCard[interactive="true"]:hover {
  border-color: rgba(255,255,255,0.10);
}
"""
```

⚠️ **box-shadow** 는 QSS 미지원 → `QGraphicsDropShadowEffect` 사용:
```python
shadow = QGraphicsDropShadowEffect()
shadow.setBlurRadius(24); shadow.setOffset(0, 4)
shadow.setColor(QColor(0, 0, 0, 60))
card.setGraphicsEffect(shadow)
```

---

## 💬 3. Dialog (LeeDialog)

### 3.1 Spec (HTML 모킹업의 DLGFrame)

- **width**: 가변 (400~680)
- **타이틀바**: 32px, sunken bg, 가운데 제목 (10pt, weight 600)
- **traffic lights**: 좌측 3개 점 (시각 장식만 — Windows에서는 숨겨도 OK)
- **본문**: 패딩 24px, 좌측 아이콘 (56px) + 우측 텍스트
- **푸터**: 16/24 패딩, sunken bg, 우측 정렬 버튼들

### 3.2 종류

| 종류 | 아이콘 색 | 글리프 | 사용처 |
|---|---|---|---|
| info | `#2C7BE5` | i | 정보 |
| warning | `#FF9F0A` | ! | 경고 |
| error | `#FF453A` | ✕ | 에러 |
| success | `#30D158` | ✓ | 완료 |
| question | `#FF7A45` | ? | confirm |
| update | `#FF7A45` | ↑ | 업데이트 |

### 3.3 PySide6 베이스 클래스 (권장)

```python
class LeeDialog(QDialog):
    """모든 커스텀 다이얼로그의 베이스. QMessageBox 대체."""

    def __init__(self, title: str, kind: str = "info", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._kind = kind
        self._setup_ui(title)

    def _setup_ui(self, title: str):
        # 타이틀바 + 본문 컨테이너 + 푸터 컨테이너 구성
        ...

    @classmethod
    def confirm(cls, title: str, message: str, *, kind="question",
                ok_text="OK", cancel_text="キャンセル",
                destructive=False, parent=None) -> bool:
        """간단한 confirm 대체. QMessageBox.question 대신 사용."""
        dlg = cls(title, kind, parent)
        dlg.set_message(message)
        dlg.add_button(cancel_text, "secondary", role="reject")
        dlg.add_button(ok_text, "destructive" if destructive else "primary", role="accept")
        return dlg.exec() == QDialog.Accepted

    @classmethod
    def info(cls, title: str, message: str, parent=None):
        dlg = cls(title, "info", parent)
        dlg.set_message(message)
        dlg.add_button("OK", "primary", role="accept")
        dlg.exec()

    @classmethod
    def error(cls, title: str, message: str, *, details: str = "", parent=None):
        dlg = cls(title, "error", parent)
        dlg.set_message(message, details=details)
        dlg.add_button("閉じる", "secondary", role="reject")
        dlg.exec()
```

### 3.4 기존 코드 마이그레이션

**Before:**
```python
reply = QMessageBox.question(self, "削除の確認", "削除しますか？",
    QMessageBox.Yes | QMessageBox.No)
if reply == QMessageBox.Yes:
    ...
```

**After:**
```python
if LeeDialog.confirm("削除の確認", "削除しますか？",
                      ok_text="削除", destructive=True, parent=self):
    ...
```

---

## ⌨️ 4. Input (LeeLineEdit / LeeTextEdit)

### 4.1 Spec

```css
input {
  height: 36px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg-input);
  color: var(--fg-primary);
  font-size: 12px;
  font-family: var(--font-mono);  /* 메일/숫자/ID 류 */
  font-weight: 600;
}
input:focus {
  outline: 2px solid var(--accent);
  outline-offset: -1px;
}
input:invalid {
  border-color: var(--c-bad);
}
```

### 4.2 PySide6 QSS

```css
QLineEdit, QTextEdit {
  background: #1B1E26;
  color: #F2F4F7;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px;
  padding: 0 12px;
  selection-background-color: rgba(255,122,69,0.3);
}
QLineEdit:focus { border: 2px solid #FF7A45; padding: 0 11px; }
```

---

## 📋 5. ListItem (좌측 사이드바, 카테고리 리스트 등)

### 5.1 Spec

```css
.lee-list-item {
  padding: 10px 14px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 10px;
  border-left: 3px solid transparent;
  color: var(--fg-primary);
}
.lee-list-item:hover {
  background: var(--bg-surface-2);
}
.lee-list-item.active {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  color: var(--accent);
  border-left-color: var(--accent);
  font-weight: 700;
}
```

### 5.2 PySide6

`QListWidget` + custom delegate, 또는 `QPushButton` 들의 `QButtonGroup`. 후자가 단순.

---

## 🏷️ 6. Pill / Badge

### 6.1 Spec

```css
.lee-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}
```

### 6.2 변형

| 종류 | bg | color |
|---|---|---|
| `subtle` | `var(--bg-surface-2)` | `var(--fg-secondary)` |
| `accent` | `color-mix(in srgb, var(--accent) 15%, transparent)` | `var(--accent)` |
| `success` | `color-mix(in srgb, var(--c-ok) 15%, transparent)` | `var(--c-ok)` |
| `danger` | `color-mix(in srgb, var(--c-bad) 15%, transparent)` | `var(--c-bad)` |

### 6.3 PySide6

`QLabel` + objectName + dynamic property 로 처리. 심플.

---

## 📊 7. KPI / Metric Card

### 7.1 Anatomy

```
┌──────────────────┐
│ 〇 ICON  予備率    │  ← 22px header (icon + label)
│                  │
│ 87%              │  ← 36~44px display number (mono, tnum)
│ ↑ 3.2 vs 昨日    │  ← 12px delta (color-coded)
│                  │
│ ─── 미니차트 ───  │  ← 28~40px sparkline
└──────────────────┘
```

### 7.2 컬러 코드

- **Up (좋음)**: `--c-ok` + ↑ 글리프
- **Down (나쁨)**: `--c-bad` + ↓ 글리프
- **Up (나쁨; 임밸런스/가격)**: `--c-warn` + ↑
- 의미는 지표마다 다름 — config로 정의

---

## 🎚️ 8. Toggle / Segmented Control

### 8.1 Segmented (탭형)

```css
.lee-segment {
  display: inline-flex;
  background: var(--bg-surface-2);
  border-radius: 10px;
  padding: 3px;
}
.lee-segment > button {
  height: 28px;
  padding: 0 14px;
  border-radius: 7px;
  font-size: 11px;
  font-weight: 700;
  background: transparent;
  color: var(--fg-secondary);
  border: 0;
}
.lee-segment > button.active {
  background: var(--bg-surface);
  color: var(--fg-primary);
  box-shadow: var(--shadow-sm);
}
```

PySide6: `QButtonGroup` + checkable QPushButton들 + custom QSS.

### 8.2 Switch

iOS 스타일 토글 — `QCheckBox` 를 QSS로 위장하거나 커스텀 `LeeSwitch` 위젯.

---

## 🔔 9. Toast / Notification

### 9.1 Spec

- 우상단 (또는 우하단) 고정 위치
- max-width: 360px
- 슬라이드 인 / 페이드 아웃
- 4초 후 자동 dismiss
- 아이콘 + 제목 + 메시지 + (옵션) action button

### 9.2 PySide6

`QFrame` (popup window flag) + `QGraphicsOpacityEffect` + `QPropertyAnimation`. 또는 시스템 트레이 알림.

---

## 📅 10. MiniCalendar (date picker 공통)

이미 모킹업에서 만든 미니 캘린더. 모든 `QDateEdit` 의 popup을 이 디자인으로 통일.

PySide6: `QCalendarWidget` 서브클래스 + 헤더/푸터 커스텀. 또는 자체 위젯.

---

## ⚙️ 11. Settings Row

### 11.1 Spec

```
┌─────────────────────────────────────┐
│  ICON   ラベル                       │
│         サブテキスト (옵션)            │  ──── control ────  │
└─────────────────────────────────────┘
```

- 좌측 아이콘 (28px tile)
- 중앙 라벨 + 서브텍스트
- 우측 컨트롤 (toggle, dropdown, button)
- separator: `1px solid var(--border-subtle)`
- hover: `bg-surface-2`

---

## 🎬 12. Animation Curves

| Curve | Duration | 용도 |
|---|---|---|
| `cubic-bezier(0.4, 0, 0.2, 1)` | 120ms | 일반 hover, color change |
| `cubic-bezier(0.34, 1.56, 0.64, 1)` | 240ms | 카드 등장, drawer (overshoot) |
| `cubic-bezier(0.4, 0, 0.6, 1)` | 180ms | 페이지 전환 |
| `linear` | 1000ms | 스피너, shimmer |

PySide6: `QPropertyAnimation.setEasingCurve(QEasingCurve.OutCubic)` 등.

---

## ✅ 컴포넌트 작업 우선순위

핸드오프에서 만들어야 할 순서:

1. **`app/ui/components/button.py`** — `LeeButton` (모든 곳에서 사용)
2. **`app/ui/components/card.py`** — `LeeCard` (대시보드 위젯의 컨테이너)
3. **`app/ui/components/dialog.py`** — `LeeDialog` + `confirm/info/warn/error` classmethods
4. **`app/ui/components/input.py`** — `LeeLineEdit`, `LeeTextEdit` (또는 그냥 QSS만)
5. **`app/ui/components/pill.py`** — `LeePill` 헬퍼
6. **`app/ui/components/sidebar.py`** — 사이드바 + ListItem
7. **`app/ui/components/segment.py`** — Segmented control
8. **`app/ui/components/toast.py`** — Toast notification
