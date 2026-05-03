/* global React, Ic, varA_atoms, varA_cards */
// ============================================================
// Variation A — Full app shell (sidebar + topbar + dashboard)
// Apple Energy / iOS widget style
// ============================================================

const { useState: useS, useMemo: useM } = React;
const { Card, IconTile, Pill } = window.varA_atoms;
const { ImbCard, ReserveCard, SpotCard, JkmCard, HjksCard, WeatherCard } = window.varA_cards;

const NAV = [
  { group: "電力データ", items: [
    { id: "dashboard", label: "ダッシュボード", icon: "board",   color: "var(--fg-primary)" },
    { id: "spot",      label: "スポット市場",   icon: "spot",    color: "var(--c-spot)" },
    { id: "reserve",   label: "電力予備率",     icon: "power",   color: "var(--c-power)" },
    { id: "imb",       label: "インバランス",   icon: "won",     color: "var(--c-imb)" },
    { id: "jkm",       label: "エネルギー指標", icon: "fire",    color: "var(--c-jkm)" },
    { id: "weather",   label: "全国天気",       icon: "weather", color: "var(--c-weather)" },
    { id: "hjks",      label: "発電稼働状況",   icon: "plant",   color: "var(--c-hjks)" },
  ]},
  { group: "Google", items: [
    { id: "calendar",  label: "カレンダー",     icon: "calendar", color: "var(--c-cal)" },
    { id: "gmail",     label: "Gmail",          icon: "gmail",    color: "var(--c-mail)" },
  ]},
  { group: "ツール", items: [
    { id: "notice",    label: "通知センター",   icon: "notice",   color: "var(--c-notice)" },
    { id: "ai",        label: "AI チャット",    icon: "chat",     color: "var(--c-ai)" },
    { id: "brief",     label: "AI ブリーフィング", icon: "brief", color: "var(--c-ai)" },
    { id: "memo",      label: "テキストメモ",   icon: "memo",     color: "var(--c-memo)" },
  ]},
];

const TOP_TABS = [
  { id: "market",  label: "マーケット",  hint: "電力・燃料",   groups: ["電力データ"] },
  { id: "ops",     label: "オペレーション", hint: "Google",      groups: ["Google"] },
  { id: "tools",   label: "ツール",      hint: "AI・メモ",     groups: ["ツール"] },
];

// id → top tab id 매핑 (자동 그룹 전환용)
const ITEM_TO_TAB = {};
NAV.forEach(g => {
  const tab = TOP_TABS.find(t => t.groups.includes(g.group));
  g.items.forEach(it => { if (tab) ITEM_TO_TAB[it.id] = tab.id; });
});

const Sidebar = ({ active, onSelect, activeGroup, onGroupChange }) => {
  const [collapsed, setCollapsed] = useS(() => {
    try {
      const saved = localStorage.getItem("lee.sidebar.collapsed");
      return saved ? JSON.parse(saved) : {};
    } catch { return {}; }
  });
  const toggle = (g) => setCollapsed((c) => {
    const n = { ...c, [g]: !c[g] };
    try { localStorage.setItem("lee.sidebar.collapsed", JSON.stringify(n)); } catch {}
    return n;
  });

  return (
  <aside style={{
    width: 240, flexShrink: 0,
    background: "var(--bg-surface)",
    borderRight: "1px solid var(--border-subtle)",
    display: "flex", flexDirection: "column",
    padding: "16px 12px",
    gap: 4,
    overflow: "auto",
  }}>
    {NAV.filter(g => {
      const tab = TOP_TABS.find(t => t.groups.includes(g.group));
      return !activeGroup || !tab || tab.id === activeGroup;
    }).map((g, gi) => {
      const isCollapsed = !!collapsed[g.group];
      // count badge for group (e.g. notice unread)
      const noticeIn = g.items.find((i) => i.id === "notice");
      return (
      <div key={g.group}>
        <button onClick={() => toggle(g.group)} style={{
          width: "100%", display: "flex", alignItems: "center", gap: 6,
          padding: "12px 8px 6px 12px", border: 0, background: "transparent",
          fontSize: 11, fontWeight: 800, color: "var(--fg-tertiary)",
          letterSpacing: "0.06em", textTransform: "uppercase",
          cursor: "pointer", fontFamily: "inherit",
        }}>
          <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" style={{
            transform: isCollapsed ? "rotate(-90deg)" : "rotate(0deg)",
            transition: "transform 0.15s ease",
            opacity: 0.7,
          }}>
            <polyline points="6 9 12 15 18 9"/>
          </svg>
          <span style={{ flex: 1, textAlign: "left" }}>{g.group}</span>
          {isCollapsed && noticeIn && (
            <span style={{
              fontSize: 9, fontWeight: 700,
              background: "var(--c-bad)", color: "#fff",
              padding: "1px 5px", borderRadius: 999,
            }}>3</span>
          )}
        </button>
        <div style={{
          maxHeight: isCollapsed ? 0 : "none",
          overflow: "hidden",
          transition: "max-height 0.2s ease",
        }}>
        {g.items.map(item => {
          const isActive = active === item.id;
          return (
            <button key={item.id} onClick={()=>onSelect(item.id)}
              className="varA-nav-btn"
              style={{
                width: "100%", display: "flex", alignItems: "center", gap: 10,
                padding: "9px 12px", borderRadius: 12, border: "none",
                background: isActive ? `${getColorVar(item.color, 0.12)}` : "transparent",
                color: isActive ? item.color : "var(--fg-secondary)",
                fontFamily: "inherit", fontSize: 13, fontWeight: 600,
                cursor: "pointer", textAlign: "left",
                transition: "all 0.15s ease",
              }}>
              <span style={{
                width: 28, height: 28, borderRadius: 8,
                background: isActive ? item.color : "var(--bg-surface-2)",
                color: isActive ? "#fff" : "var(--fg-secondary)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <Ic name={item.icon} size={15} stroke={2}/>
              </span>
              <span>{item.label}</span>
              {item.id === "notice" && (
                <span style={{
                  marginLeft: "auto", fontSize: 10, fontWeight: 700,
                  background: "var(--c-bad)", color: "#fff",
                  padding: "1px 6px", borderRadius: 999,
                }}>3</span>
              )}
            </button>
          );
        })}
        </div>
      </div>
      );
    })}
    <div style={{ flex: 1 }}/>
    <div style={{
      borderTop: "1px solid var(--border-subtle)", marginTop: 8, paddingTop: 12,
      display: "flex", flexDirection: "column", gap: 4,
    }}>
      {[
        { id: "log",     label: "ログ",     icon: "log" },
        { id: "bug",     label: "バグ報告", icon: "bug" },
        { id: "manual",  label: "マニュアル", icon: "manual" },
        { id: "setting", label: "設定",     icon: "setting" },
      ].map(item => (
        <button key={item.id} onClick={()=>onSelect(item.id)}
          style={{
            display: "flex", alignItems: "center", gap: 10, padding: "8px 12px",
            border: "none", background: active === item.id ? "var(--bg-surface-2)" : "transparent",
            color: "var(--fg-secondary)", borderRadius: 10, fontFamily: "inherit", fontSize: 12, fontWeight: 600,
            cursor: "pointer", textAlign: "left",
          }}>
          <Ic name={item.icon} size={15} stroke={2}/>
          <span>{item.label}</span>
        </button>
      ))}
    </div>
  </aside>
  );
};

function getColorVar(c, alpha) {
  // c is a CSS variable like var(--c-spot). Use rgba via color-mix if possible
  return `color-mix(in srgb, ${c} ${alpha*100}%, transparent)`;
}

const TopBar = ({ activeGroup, onGroupChange, onThemeToggle, isDark }) => (
  <div style={{
    height: 60, padding: "0 28px",
    background: "var(--bg-surface)",
    borderBottom: "1px solid var(--border-subtle)",
    display: "flex", alignItems: "center", gap: 24, flexShrink: 0,
  }}>
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <div style={{
        width: 32, height: 32, borderRadius: 10,
        background: "linear-gradient(135deg, var(--c-jkm) 0%, var(--c-spot) 60%, var(--c-imb) 100%)",
        display: "flex", alignItems: "center", justifyContent: "center", color: "#fff",
      }}>
        <Ic name="zap" size={16}/>
      </div>
      <div>
        <div style={{ fontSize: 14, fontWeight: 800, letterSpacing: "-0.01em" }}>LEE</div>
        <div style={{ fontSize: 9, color: "var(--fg-tertiary)", letterSpacing: "0.1em", fontWeight: 700 }}>電力モニター</div>
      </div>
    </div>

    <div style={{ display: "flex", gap: 4, padding: 4, background: "var(--bg-surface-2)", borderRadius: 12 }}>
      {TOP_TABS.map(t => (
        <button key={t.id} onClick={()=>onGroupChange(t.id)}
          className="lee-tab-btn"
          style={{
            border: "none", padding: "7px 14px", borderRadius: 9, cursor: "pointer",
            background: activeGroup === t.id ? "var(--bg-surface)" : "transparent",
            color: activeGroup === t.id ? "var(--fg-primary)" : "var(--fg-secondary)",
            fontFamily: "inherit", fontSize: 13, fontWeight: 600,
            boxShadow: activeGroup === t.id ? "var(--shadow-sm)" : "none",
            display: "flex", alignItems: "center", gap: 6,
          }}>
          {t.label}
          <span style={{ fontSize: 10, color: "var(--fg-tertiary)", fontWeight: 500 }}>{t.hint}</span>
        </button>
      ))}
    </div>

    <div style={{ flex: 1, position: "relative", maxWidth: 420 }}>
      <span style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--fg-tertiary)" }}>
        <Ic name="search" size={15}/>
      </span>
      <input placeholder="検索 (⌘K)..." style={{
        width: "100%", padding: "8px 12px 8px 36px", borderRadius: 10,
        border: "1px solid var(--border)", background: "var(--bg-surface-2)",
        fontFamily: "inherit", fontSize: 13, color: "var(--fg-primary)",
        outline: "none",
      }}/>
      <span style={{
        position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)",
        fontSize: 10, color: "var(--fg-tertiary)", border: "1px solid var(--border)",
        padding: "2px 5px", borderRadius: 4, background: "var(--bg-surface)",
      }}>⌘K</span>
    </div>

    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <Pill color="var(--c-ok)"><span style={{ width: 5, height: 5, borderRadius: 999, background: "var(--c-ok)" }}/>オンライン</Pill>
      <button onClick={onThemeToggle} style={{
        width: 36, height: 36, borderRadius: 10, border: "none",
        background: "var(--bg-surface-2)", color: "var(--fg-secondary)", cursor: "pointer",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <Ic name={isDark ? "sun" : "moon"} size={16}/>
      </button>
      <div style={{
        display: "flex", alignItems: "center", gap: 8, padding: "4px 12px 4px 4px",
        background: "var(--bg-surface-2)", borderRadius: 999,
      }}>
        <div style={{
          width: 28, height: 28, borderRadius: 999,
          background: "linear-gradient(135deg, var(--c-ai), var(--c-power))",
          display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 11, fontWeight: 700,
        }}>李</div>
        <span style={{ fontSize: 12, fontWeight: 600 }}>李 田中</span>
      </div>
    </div>
  </div>
);

window.varA_shell = { Sidebar, TopBar, NAV, TOP_TABS, ITEM_TO_TAB };
