# LEE 電力モニター — Design Handoff Package

PySide6 마이그레이션을 위한 디자인 → 코드 핸드오프 패키지.

## 📦 포함 문서

| 파일 | 내용 | 대상 |
|---|---|---|
| **[01-design-tokens.md](01-design-tokens.md)** | 컬러, 스페이싱, 타이포, 라디우스, 섀도 토큰 | 개발자 + Claude Code |
| **[02-components.md](02-components.md)** | Button, Card, Dialog, Input, ListItem 등 컴포넌트 스펙 | Claude Code |
| **[03-screen-specs.md](03-screen-specs.md)** | 주요 화면별 레이아웃 + 인터랙션 명세 | 개발자 |
| **[04-migration-plan.md](04-migration-plan.md)** | PySide6 매핑 전략 + Phase 로드맵 | 개발자 (PM) |
| **[05-claude-code-prompts.md](05-claude-code-prompts.md)** | ⭐ **Claude Code에게 어떻게 지시할지** 가이드 + Phase 0~6 프롬프트 | 사용자 (당신) |
| **[05b-phase5-widget-prompts.md](05b-phase5-widget-prompts.md)** | ⭐ **Phase 5 위젯 16개** 개별 프롬프트 | 사용자 (당신) |

## 🎯 빠른 시작 (사용자 워크플로우)

1. **[05-claude-code-prompts.md](05-claude-code-prompts.md)** 를 먼저 열어서 **Phase 0** 의 Initial 프롬프트를 복사
2. VS Code에서 Claude Code 사이드바 열고 → 프롬프트 붙여넣기 → 첨부 파일로 `01~04` md 들도 같이 첨부
3. Phase 1부터 순서대로 진행 (각 Phase 끝에 검증 후 다음 Phase로)

## 📐 디자인 진화 흐름 요약

```
현재 (As-is)                  →  새 디자인 (To-be)
─────────────────────────────────────────────────────
Fusion 스타일 + 직접 QSS         디자인 토큰 시스템 (Light/Dark)
하드코딩된 컬러 (#fff 등)          var(--accent), 의미 기반 변수
QMessageBox 기본                커스텀 다이얼로그 (DLGFrame)
파편화된 위젯 스타일              공통 lee-card / lee-pill
단일 레이아웃                    Variation A (캐주얼) / B (프로) 선택
일반 로그인                      Refined Dark 로그인
```

## 🗂️ 디자인 모킹업 위치

브라우저에서 `LEE 電力モニター - 2 Variations.html` 열어서 확인.

| Section | 내용 |
|---|---|
| **Overview** | Variation A (캐주얼 iOS) / Variation B (Trading) 두 안 풀스크린 |
| **ログイン Window** | A+ Refined Dark (⭐최종 채택) + A/B/C 비교 |
| **システム ダイアログ** | 13종 (업데이트 4종 + 종료/로그아웃/起動エラー + 공통 + manual용) |
| **비교 포인트** | A vs B 결정적 차이 |

## 🤝 핸드오프 원칙

1. **One source of truth** — 토큰 값은 `01-design-tokens.md` 가 진실. 코드에서 하드코딩 금지.
2. **점진적 마이그레이션** — Phase 0~5 단계별. 한번에 다 바꾸지 않음.
3. **테마 변수화** — `[data-theme="..."]` 패턴을 PySide6 QPalette + dynamic property로 매핑.
4. **다이얼로그 → 커스텀** — `QMessageBox.question()` 직접 호출 ❌ → `LeeDialog.confirm()` 같은 래퍼 ⭕

---

작성: 2024-12 | Designer: Claude (via Manager) | 구현: Claude Code (via VS Code)
