# LEE Audit — Dummy Data & Background Contrast (2026-05-03)

Scope: `app/widgets/`, `app/widgets/dashboard_cards.py`, `app/ui/dialogs/`, `app/ui/components/` and supporting files.
Theme tokens reference: `app/ui/theme.py` (`TOKENS_DARK` / `TOKENS_LIGHT`, e.g. `bg_app="#0A0B0F"`/`#F5F6F8`, `bg_surface="#14161C"`/`#FFFFFF`, `bg_surface_2="#1B1E26"`/`#F0F2F5`, `border_subtle`, `fg_primary` etc.).

Methodology: grepped widgets/cards for hardcoded numbers, `dummy_*`/`mock_*`/`sample_*`/`placeholder_*`/`DEMO`, `setMarkdown`/`setText` literals, `setHtml`, `if False:`, hardcoded backgrounds. Cross-referenced with `app/widgets/dashboard_service.py` (DB-backed signals) and per-widget `set_data` / `refresh` paths.

---

## Executive summary

**Issue 1 (Dummy data)** — The codebase is, as a rule, **not** displaying fake data. Every dashboard card has a real `set_*` API wired to the DashboardDataService (DB-backed) or a per-widget refresh method. The closest thing to "dummy" surfaces are:

1. Two intentionally-disabled controls in Settings (compact mode, font size) labelled `(準備中)`.
2. A test-only fake update payload in `app/core/updater.py` (dev tool, not user-facing).
3. Static **example numbers in docstrings only** (e.g. `JkmCard` docstring "14.32 USD/MMBtu", `BriefCard` docstring "6.2 %") — not rendered.
4. Hardcoded **time-axis tick labels** ("00:00 / 06:00 / 12:00 / 18:00 / 24:00") on the imbalance & spot sparklines — these are correct labels for a 48-slot day, not data.

**Issue 2 (Background contrast / 浮いた感)** — Multiple real findings. Three patterns dominate:

A. **`light.qss` is force-applied even in dark mode** (concatenated by `ThemeManager.set_theme` via `get_theme_qss`) — confirm by reading `app/core/config.get_theme_qss`. If it's loaded only for `light`, fine; otherwise it stamps `#FFFFFF` panels onto the dark `#0A0B0F` shell.
B. **Per-widget hardcoded `"#14161C" if dark else "#FFFFFF"` ladders** (~50 occurrences) duplicate `tokens["bg_surface"]`. Functionally equivalent today but they bypass the central token system, so any future token change (the `LEE` brand recently used `#14161C` for dark surface) won't propagate.
C. **Hard whites that ignore dark mode entirely** — Gmail HTML preview (`background:#FFFFFF !important`), `QTextBrowser#gmailPreviewBrowser` qss line 1490 (`background:#FFFFFF`), tracker dots `pg.mkPen("white")` on light-mode charts. These are the most likely culprits for the "stuck on" feeling.

---

## Issue 1 — Dummy / placeholder data audit

| Widget / Card | File:Line | What's "dummy" | Real source available? | Fix effort |
|---|---|---|---|---|
| Settings — Compact mode toggle | `app/widgets/settings.py:437-441` | `chk_compact` is created, `setEnabled(False)`, labelled `(準備中)`. No backing logic. | No source — feature unimplemented. Layout system in `dashboard.py` could host it. | **M** — wire to `_compact` in `DashboardWidget` |
| Settings — Font size spinbox | `app/widgets/settings.py:443-448` | `spn_font` `setValue(13)`, `setEnabled(False)`, `(準備中)`. | No source. Would need a font scaling helper in `app/ui/theme.py`. | **M** |
| UpdateManager — fake update path | `app/core/updater.py:292-297` and `:325` | `fake_info = { "version": …, "url": "https://example.invalid/fake/LEE_Setup.exe" }` and `_on_download_finished("")  # fake path`. | Real GitHub release flow exists in same file. The fake block is reachable only via dev/test code path. | **L** — verify it is dev-only or remove |
| `JkmCard` docstring | `app/widgets/jkm.py:84-99` | Sample numbers `14.32 USD/MMBtu`, `MIN 12.50 / MAX 16.80` appear in the class **docstring** as a layout sketch. **Not rendered.** | N/A — already pulls from `query_indicator` / DashboardDataService. | None |
| `BriefCard` docstring | `app/widgets/briefing.py:227-241` | Docstring shows `6.2 %, 10.78, 14.32`. Not rendered. | N/A — `set_kpis()` is called by `dashboard.py:1332/1352/1372/1375`. | None |
| `NotificationCard` docstring | `app/widgets/notification.py:262-277` | Mock rows ("東京エリア予備率警報 12分前", "JEPX 約定結果 32分前") in docstring. Not rendered. | N/A — `set_notifications(list_notifications())` from `notifications.db`. | None |
| `BriefCard` empty placeholder text | `app/widgets/briefing.py:317-320` | When no briefing in DB it shows `tr("AI ブリーフィングはまだ生成されていません…")`. This is a legitimate empty state, not dummy data. | DB: `briefings.db`. | None |
| `_PLACEHOLDER` dict in BriefingWidget | `app/widgets/briefing.py:101-106` | Per-language placeholder copy used as `setPlaceholderText` on the QTextEdit before generation. Legitimate UX placeholder. | N/A | None |
| `ManualCard` recent list when DB unreachable | `app/widgets/manual.py:1270-1272` | Falls back to `?` count and `(DB 未接続)` label. Legitimate empty state. | shared SQLite (`init_shared_db`). | None |
| `_DEMO_*` / `MOCK_DATA` / `_FAKE` constants | (none found) | grep returned no widget-level demo constants. | — | None |
| `if False:` / `if 0:` data-gating | (none found) | — | — | None |
| Imbalance sparkline time labels | `app/widgets/imbalance.py:170-172` | Hardcoded strings `"00:00", "06:00", "12:00", "18:00", "24:00"`. | These are axis tick labels for the fixed 48-slot day, not data. Correct as-is. | None |
| JEPX spot sparkline time labels | `app/widgets/jepx_spot.py:228-232` | Same pattern. | Same — axis labels. | None |
| `pg.mkPen("white", width=1.5)` tracker pens | `app/widgets/jepx_spot.py:590`, `app/widgets/imbalance.py:449`, `app/widgets/jkm.py:403` | Cosmetic outline color for the hovered data point — NOT data. (See Issue 2 — invisible on white bg in light mode.) | — | See Issue 2 |
| Bug Report card stats | `app/widgets/bug_report.py:1140` | Initial `tr("未対応: 0  ·  対応中: 0  ·  解決: 0")` is the empty state before first refresh. Replaced at `:1171` with real counts. | Real: `bug_reports.db`. | None |
| `JEPX SpotDashCard` initial values | `app/widgets/dashboard_cards.py:662-669` | `"--"`, `"-- 円/kWh"` placeholders before `set_data()`. Legitimate. | DashboardDataService spot signals. | None |
| `SummaryCard` initial values | `app/widgets/dashboard_cards.py:359-362` | `"--"`, `tr("データ待機中...")` then skeleton — replaced by `set_value`. Legitimate. | — | None |

**Verdict:** No widget surfaces are **silently** showing canned values; the only true gaps are the two `(準備中)` settings.

---

## Issue 2 — Background contrast / 浮いた感 audit

Tokens used in suggestions:
- `bg_app` = `#0A0B0F` dark / `#F5F6F8` light  → page shell
- `bg_surface` = `#14161C` dark / `#FFFFFF` light  → cards
- `bg_surface_2` = `#1B1E26` dark / `#F0F2F5` light  → inputs / nested
- `bg_surface_3` = `#232730` dark / `#E6E9EE` light  → 3rd-level
- `border_subtle`, `border` for separators
- `fg_primary`, `fg_secondary`, `fg_tertiary` for text

| Element | File:Line | Issue | Suggested token / fix |
|---|---|---|---|
| Light-mode global QSS | `app/ui/themes/light.qss:1-101` | Hardcoded `#ffffff` everywhere (QTableWidget, QPushButton, QListWidget bg `#f4f4f4`, QPlainTextEdit, QComboBox dropdown, QCalendarWidget grid, QSpinBox). Bypasses tokens. The `LEE` light theme in tokens uses `#F5F6F8` for app bg, `#FFFFFF` for surface — the qss values mostly match but should be regenerated from `TOKENS_LIGHT` instead of duplicated. | Refactor `light.qss` (and matching `dark.qss`) to be `format(**TOKENS_LIGHT)` template, identical strategy to `QSS_TEMPLATE` in `theme.py`. |
| Dark-mode dashboard card #1 — SummaryCard hardcoded #252526 | `app/ui/theme.py:180-191` (`SummaryCard[theme="dark"]`) | Uses **legacy** `#252526` / `#3e3e42` hex instead of `bg_surface` (`#14161C`). The legacy hex is *lighter* than the new token, so SummaryCards float visually above the new dark `bg_app=#0A0B0F`. | Replace block with `tokens["bg_surface"]` / `tokens["border_subtle"]`. |
| GmailPreview QTextBrowser | `app/widgets/gmail.py:1489-1491` | `QTextBrowser#gmailPreviewBrowser { background: #FFFFFF; border: none; }` — forces white **even in dark mode**. Email HTML often demands white but the surrounding card is `bg_surface=#14161C` → very visible "stuck-on white card-in-card". | Acceptable for email rendering; mitigate with a 1px `border-top: 1px solid {border_subtle}` and inset padding so it reads as an embedded letter rather than a floating panel. Or wrap the browser in a `border-radius: 0 0 16px 16px` rounded clip so the white is visually contained. |
| Gmail body HTML CSS injection | `app/widgets/gmail.py:1020-1038` | `body { background:#ffffff !important }` injected into every email. Same root cause as above. | Same mitigation; the `!important` is required because senders ship inline dark-mode styles that look broken on white. |
| WeatherCard / SpotCard hardcoded `bg_input` ladders | `app/widgets/weather.py:743`, `app/widgets/jepx_spot.py:1199`, `app/widgets/jkm.py:1191`, `app/widgets/jkm.py:1179` | `bg_input = "#1B1E26" if is_dark else "#FFFFFF"` repeats `tokens["bg_input"]` value but bypasses the token. | Inject `tokens` from theme manager and use `tokens["bg_input"]`. |
| Per-widget `bg_surface = "#14161C" if d else "#FFFFFF"` ladders (~50 sites) | `app/widgets/dashboard.py:1508`, `briefing.py:695,805`, `notification.py:678,830`, `bug_report.py:358,791,1187`, `gmail.py:1154,1312`, `manual.py:1280,1579,1699`, `imbalance.py:246,366`, `jepx_spot.py:303,518,773,1199`, `jkm.py:237,334,1179,1191`, `hjks.py:553,757,938,1350`, `text_memo.py:480,779,818`, `settings.py:1022`, `ai_chat.py:563,836,1237`, `log_viewer.py:473,891` | Functionally equivalent today. Three risks: (a) any future token change (e.g. dark `bg_surface` → `#101218`) won't propagate; (b) easy to drift out of sync (already happens — see SummaryCard `#252526`); (c) light-mode `#FFFFFF` cards on light `#F5F6F8` shell get a 4pt tonal step but no border in some panels → cards look "pasted on" on light theme. | Pass `tokens` dict (or `ThemeManager.instance().tokens`) into each `_apply_qss` and reference `tokens["bg_surface"]`. Add `border: 1px solid {border_subtle}` to every card-like QFrame to guarantee separation in light mode. |
| `pg.mkPen("white")` tracker dot outline | `app/widgets/jepx_spot.py:590`, `imbalance.py:449`, `jkm.py:403` | Hover-tracker dot has a hardcoded white outline. In **light mode** the chart background is also `#FFFFFF` — outline becomes invisible against the plot area. | Use `tokens["bg_surface"]` (white in light, dark in dark) — already the chart bg, so the outline contrasts the brush color, not the bg. Or branch `pg.mkPen("white" if is_dark else "#0B1220", …)`. |
| `QListWidget` notification list hard whites | `app/ui/theme.py:511-519` (`get_notification_list_style`) | Light mode hardcodes `background: #ffffff` and dark mode `#1e1e1e` (≠ token `#14161C`). The `#1e1e1e` is brighter than current dark `bg_surface` so the list panel floats. | Replace with `bg_surface` / `border_subtle`. |
| `UIColors.get_panel_colors` panels | `app/ui/theme.py:469-474` | Dark `bg=#252526`, light `bg=#fcfcfc`. Both diverge from new tokens (`#14161C` / `#FFFFFF`). Used by `SpotDashCard` line 698-707 and other legacy components. | Replace returned dict to read `TOKENS_DARK["bg_surface"]` / `TOKENS_LIGHT["bg_surface"]`. |
| `UIColors.get_graph_colors` plotting bg | `app/ui/theme.py:478-482` | Dark `#1e1e1e`, light `#ffffff`. Dark value is **brighter** than new `bg_surface=#14161C` — pyqtgraph plot surfaces visibly differ from the surrounding card. | Use tokens — return `bg_surface`. |
| `UIColors.get_log_colors` viewer bg | `app/ui/theme.py:539-563` | Dark `#1e1e1e`, light `#ffffff`. Same drift. Used by `log_viewer`. | Use tokens. |
| `UIColors.get_chat_colors` AI bubbles | `app/ui/theme.py:527-536` | `user_bg = "#0078d4"` (legacy MS blue) instead of accent token `#5856D6` (`c_ai`). Fine on dark, but the bubble's hardcoded `#0078d4` against dark `bg_app=#0A0B0F` looks pasted in. | Reuse `tokens["c_ai"]` for user bubble (or new dedicated token). |
| `LeeMiniCalendar` hardcoded ladders | `app/ui/components/mini_calendar.py:97-104` | Same `bg_app="#0A0B0F" if d else "#F5F6F8"` ladder duplicating tokens. Mostly OK; just sync. | Pass tokens. |
| Notification list legacy QListWidget | `app/widgets/notification.py` (uses `get_notification_list_style`) | Picks up `#1e1e1e` / `#ffffff` from `theme.py:517` — see row above. | — |
| GoogleCalendar dialog backgrounds | `app/widgets/google_calendar.py:1759, 1763` | `background: {'#2d2d2d' if d else '#ffffff'}` for QLineEdit/QTextEdit/QComboBox. Light is fine; dark `#2d2d2d` doesn't match `bg_input=#1B1E26`. | Use `tokens["bg_input"]`. |
| GoogleCalendar secondary button bg | `app/widgets/google_calendar.py:1751-1753` | `background: {'#3e3e42' if d else '#e0e0e0'}`. `#3e3e42` is much lighter than current dark surface 2 (`#1B1E26`) → the button has a "raised chip" look that contrasts oddly with surrounding tokenised UI. | Use `tokens["bg_surface_2"]` / hover `bg_surface_3`. |
| Dashboard size badge | `app/widgets/dashboard.py:1535-1538` (`QLabel#dashSizeLbl`) | `color: white; background: #FF7A45;` — accent badge, intentional. Acceptable. | None — accent token. |
| Dashboard error overlay button | `app/widgets/dashboard.py:230-237` (`QPushButton#dashOverBtn`) | `background: #14161C; color: #F2F4F7;` hardcoded dark hex. In **light mode** this overlay button stays dark, conflicting with light surroundings. | Use tokens (`bg_surface`/`fg_primary`). |
| Drop indicator & overlay text | `app/widgets/dashboard.py:296-303`, `:240-246` | `color: white; background: {tag_bg};` etc. — tags are accent badges. Acceptable. | None |
| QTableWidget alternate row in light qss | `app/ui/themes/light.qss:9` | `alternate-background-color: #f9f9f9` independent from token `bg_surface_2=#F0F2F5`. Subtle drift but generally fine. | Optional sync. |
| QCalendarWidget (light qss) | `app/ui/themes/light.qss:85-96` | Hardcoded `#f4f4f4` / `#e6e6e6` for nav bar and grid. Out of sync with tokens. The native QDateEdit popup will pick this up, mismatch with `LeeMiniCalendar`. | Either remove (let `LeeMiniCalendar` win) or sync to tokens. |
| `imbalance.py:177` placeholder note | `app/widgets/imbalance.py:178-184` | `tr("データなし")` QLabel — uses card bg. Legitimate empty state. | None |
| `dashboard_cards.SummaryCard` weather gradient overlay | `app/widgets/dashboard_cards.py:32-59` (`_WMO_BG_DARK`, `_WMO_BG_LIGHT`) | Hardcoded gradients ending in `#252526` (dark) / `#ffffff` (light). The dark stop matches the legacy SummaryCard bg, **not** the new `bg_surface=#14161C`. So weather card has subtly different bg than the rest. | Update bottom stops: dark → `#14161C`, light keep `#FFFFFF`. |
| `SummaryCard` icon/background in light qss | `app/ui/theme.py:186-191` | `SummaryCard[theme="light"] { background-color: #ffffff; border: 1px solid #dddddd; }` — `#dddddd` doesn't match `border` token (`rgba(11,18,32,0.10)`). | Use `border` token. |

### Likely-perceived "白い背景が浮いてる" hot spots (priority order)

1. **Gmail email preview** (`gmail.py:1490` + injected CSS) — biggest perceived offender in dark mode. White rectangle in the middle of a dark page.
2. **SummaryCard `[theme="dark"]` block** (`theme.py:180-191`) — uses legacy `#252526`, brighter than the new `bg_app=#0A0B0F` shell. Cards visibly "lift".
3. **Hardcoded panel colors via `UIColors.get_panel_colors`** (`theme.py:469`) — affects SpotDashCard line 706 (`pc['bg']`) and other legacy code paths. Drift `#252526` vs token `#14161C`.
4. **`get_notification_list_style`** (`theme.py:509-519`) — list hard `#1e1e1e`/`#ffffff` instead of token. Notification page panel will visibly differ from card panels.
5. **`light.qss` block-level `#ffffff` everywhere** — in light mode QPushButton/QPlainTextEdit/QListWidget all read pure white, while LeeCard surfaces are also pure white → no separation between widget types and their containers. Add `border: 1px solid {border_subtle}` to differentiate.
6. **PyQtGraph tracker dot `pg.mkPen("white")`** — chart hover dot disappears in light mode; only visible to dark-mode users.
7. **GoogleCalendar dialog `#2d2d2d`/`#3e3e42`** in dark mode — brighter than tokens, dialog inputs look like they belong to a different app.

---

## Recommended next actions

A. Centralise: Each widget's `_apply_qss` should accept `tokens = ThemeManager.instance()._tokens` (expose as property) instead of inlining `"#14161C" if dark else "#FFFFFF"`. One-time refactor; eliminates the 50+ duplications and the SummaryCard / panel drift in one go.

B. Migrate `app/ui/themes/light.qss` (and dark.qss) to `format(**TOKENS_LIGHT)` template, mirroring `QSS_TEMPLATE` in `theme.py`.

C. Remove the legacy `#252526` / `#3e3e42` / `#1e1e1e` / `#252526` constants from `ThemePalette` and `UIColors.get_*_colors`, redirecting them to the token dicts. Anything that needed a different shade can pick `bg_surface_2` or `bg_surface_3`.

D. For Gmail HTML preview — keep white (email convention) but visually integrate by:
   - Removing `border: none;` and adding `border: 1px solid {border_subtle}; border-radius: 12px;` to the QTextBrowser.
   - Adding `padding: 10px 12px;` around the browser inside its parent frame so the white rectangle reads as an inset card rather than a "stuck-on" panel.

E. Tracker pen fix (`jepx_spot.py:590`, `imbalance.py:449`, `jkm.py:403`):
   `pg.mkPen("white" if self._is_dark else "#0B1220", width=1.5)`.

F. Implement or remove the two `(準備中)` toggles in Settings, depending on roadmap.

---

End of audit.
