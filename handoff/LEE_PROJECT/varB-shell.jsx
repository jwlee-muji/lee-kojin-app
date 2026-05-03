/* global React, Ic, WeatherIllust */
// ============================================================
// Variation B — Trading-grade dense layout
// 다중 컬럼, 정밀 그리드, 멀티 액센트, 긴장감 있는 정보 밀도
// ============================================================
const { useState: vbS, useEffect: vbE, useMemo: vbM } = React;
const DD = window.LEE_DATA;

/* ---------- Mini chart helpers ---------- */
const VBSpark = ({ data, color, w = 100, h = 28, area = true }) => {
  if (!data || data.length === 0) return null;
  const min = Math.min(...data), max = Math.max(...data), range = max - min || 1;
  const pts = data.map((v, i) => [
    (i / (data.length - 1)) * w,
    h - ((v - min) / range) * h,
  ]);
  const path = pts.map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`)).join(" ");
  const areaPath = `${path} L${w},${h} L0,${h} Z`;
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      {area && <path d={areaPath} fill={color} opacity="0.15"/>}
      <path d={path} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
};

const VBPrecisionChart = ({ data, color, w = 480, h = 160, label }) => {
  const min = Math.min(...data) * 0.95, max = Math.max(...data) * 1.05, range = max - min || 1;
  const pts = data.map((v, i) => [
    (i / (data.length - 1)) * w,
    h - ((v - min) / range) * h,
  ]);
  const path = pts.map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`)).join(" ");
  const areaPath = `${path} L${w},${h} L0,${h} Z`;
  const yTicks = 5;
  const xTicks = 6;
  return (
    <svg width={w} height={h + 24} style={{ display: "block" }}>
      <defs>
        <linearGradient id={`g-${label}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25"/>
          <stop offset="100%" stopColor={color} stopOpacity="0"/>
        </linearGradient>
      </defs>
      {/* Grid */}
      {Array.from({ length: yTicks }).map((_, i) => (
        <line key={`y-${i}`} x1="0" y1={(i / (yTicks - 1)) * h} x2={w} y2={(i / (yTicks - 1)) * h}
          stroke="var(--grid-line)" strokeWidth="1" strokeDasharray={i === yTicks - 1 ? "" : "2,3"}/>
      ))}
      {Array.from({ length: xTicks }).map((_, i) => (
        <line key={`x-${i}`} x1={(i / (xTicks - 1)) * w} y1="0" x2={(i / (xTicks - 1)) * w} y2={h}
          stroke="var(--grid-line)" strokeWidth="1" strokeDasharray="2,3"/>
      ))}
      {/* Area + Line */}
      <path d={areaPath} fill={`url(#g-${label})`}/>
      <path d={path} fill="none" stroke={color} strokeWidth="1.5"/>
      {/* Y labels */}
      {Array.from({ length: yTicks }).map((_, i) => {
        const v = max - (i / (yTicks - 1)) * range;
        return (
          <text key={`yl-${i}`} x="4" y={(i / (yTicks - 1)) * h + 4}
            fill="var(--fg-tertiary)" fontSize="9" fontFamily="var(--font-mono)">
            {v.toFixed(1)}
          </text>
        );
      })}
      {/* X labels */}
      {["00", "06", "12", "18", "24"].map((t, i) => (
        <text key={`xl-${i}`} x={(i / 4) * w} y={h + 14}
          fill="var(--fg-tertiary)" fontSize="9" fontFamily="var(--font-mono)" textAnchor={i === 0 ? "start" : i === 4 ? "end" : "middle"}>
          {t}:00
        </text>
      ))}
    </svg>
  );
};

/* ---------- Atoms ---------- */
const VBPanel = ({ title, accent, children, badge, action, dense, onClick }) => (
  <div onClick={onClick} style={{
    background: "var(--bg-surface)",
    border: "1px solid var(--border-subtle)",
    borderRadius: 8,
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    cursor: onClick ? "pointer" : "default",
    transition: "border-color 0.15s",
  }}>
    <div style={{
      display: "flex", alignItems: "center", gap: 8,
      padding: "8px 12px",
      borderBottom: "1px solid var(--border-subtle)",
      background: "var(--bg-surface-2)",
    }}>
      <span style={{ width: 3, height: 14, background: accent, borderRadius: 2 }}/>
      <span style={{ fontSize: 11, fontWeight: 700, color: "var(--fg-primary)", letterSpacing: "0.04em", textTransform: "uppercase" }}>{title}</span>
      {badge && (
        <span style={{
          fontSize: 9, fontWeight: 700, padding: "1px 6px", borderRadius: 4,
          background: `color-mix(in srgb, ${accent} 18%, transparent)`,
          color: accent, letterSpacing: "0.03em",
        }}>{badge}</span>
      )}
      <div style={{ flex: 1 }}/>
      {action}
    </div>
    <div style={{ padding: dense ? "10px 12px" : "14px 14px", flex: 1 }}>
      {children}
    </div>
  </div>
);

const VBStat = ({ label, value, unit, color, delta, deltaPositive, mono = true }) => (
  <div>
    <div style={{ fontSize: 9, fontWeight: 700, color: "var(--fg-tertiary)", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 4 }}>{label}</div>
    <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
      <span style={{
        fontSize: 22, fontWeight: 700, color: color || "var(--fg-primary)",
        fontFamily: mono ? "var(--font-mono)" : "inherit",
        fontVariantNumeric: "tabular-nums", letterSpacing: "-0.01em",
      }}>{value}</span>
      {unit && <span style={{ fontSize: 11, color: "var(--fg-tertiary)", fontWeight: 600 }}>{unit}</span>}
      {delta != null && (
        <span style={{ fontSize: 11, fontWeight: 700, color: deltaPositive ? "var(--c-bad)" : "var(--c-ok)", marginLeft: 2 }}>
          {deltaPositive ? "▲" : "▼"} {delta}%
        </span>
      )}
    </div>
  </div>
);

/* ---------- Top Bar ---------- */
const VBTopBar = ({ isDark, onThemeToggle, activeTab, onTab }) => {
  const tabs = ["MARKET", "OPERATIONS", "TOOLS"];
  return (
    <div style={{
      height: 48, padding: "0 16px",
      background: "var(--bg-surface)",
      borderBottom: "1px solid var(--border)",
      display: "flex", alignItems: "center", gap: 18, flexShrink: 0,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{
          width: 26, height: 26, borderRadius: 6,
          background: "var(--c-spot)",
          display: "flex", alignItems: "center", justifyContent: "center", color: "#fff",
        }}>
          <Ic name="zap" size={14} stroke={2.5}/>
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.06em" }}>LEE TERMINAL</div>
        </div>
      </div>

      <div style={{ width: 1, height: 22, background: "var(--border)" }}/>

      <div style={{ display: "flex", gap: 1 }}>
        {tabs.map(t => (
          <button key={t} onClick={() => onTab(t)}
            style={{
              border: "none", padding: "6px 14px",
              background: activeTab === t ? "var(--bg-surface-2)" : "transparent",
              color: activeTab === t ? "var(--c-spot)" : "var(--fg-secondary)",
              fontFamily: "inherit", fontSize: 11, fontWeight: 700, cursor: "pointer",
              letterSpacing: "0.06em",
              borderBottom: activeTab === t ? "2px solid var(--c-spot)" : "2px solid transparent",
              borderRadius: 0,
            }}>{t}</button>
        ))}
      </div>

      {/* Live ticker */}
      <div style={{
        flex: 1, display: "flex", alignItems: "center", gap: 18, overflow: "hidden",
        fontFamily: "var(--font-mono)", fontSize: 11,
      }}>
        {[
          { l: "TYO", v: "15.42", d: +2.1, c: "var(--c-spot)" },
          { l: "RES", v: "6.2%", d: -0.4, c: "var(--c-bad)" },
          { l: "IMB", v: "38.50", d: +12.4, c: "var(--c-imb)" },
          { l: "JKM", v: "14.32", d: -1.2, c: "var(--c-jkm)" },
          { l: "USD/JPY", v: "157.84", d: +0.3, c: "var(--fg-primary)" },
        ].map((t, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 5, whiteSpace: "nowrap" }}>
            <span style={{ color: "var(--fg-tertiary)", fontSize: 10, fontWeight: 700 }}>{t.l}</span>
            <span style={{ color: t.c, fontWeight: 700 }}>{t.v}</span>
            <span style={{ color: t.d > 0 ? "var(--c-bad)" : "var(--c-ok)", fontSize: 10, fontWeight: 600 }}>
              {t.d > 0 ? "▲" : "▼"}{Math.abs(t.d)}%
            </span>
          </div>
        ))}
      </div>

      <div style={{
        padding: "4px 8px", border: "1px solid var(--border)", borderRadius: 4,
        fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-secondary)",
        display: "flex", alignItems: "center", gap: 6,
      }}>
        <span style={{ width: 6, height: 6, borderRadius: 999, background: "var(--c-ok)" }}/>
        LIVE · 09:14:32 JST
      </div>

      <button onClick={onThemeToggle} style={{
        width: 28, height: 28, borderRadius: 6, border: "1px solid var(--border)",
        background: "var(--bg-surface-2)", color: "var(--fg-secondary)", cursor: "pointer",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <Ic name={isDark ? "sun" : "moon"} size={13}/>
      </button>
    </div>
  );
};

/* ---------- Sidebar ---------- */
const VBSidebar = ({ active, onSelect }) => {
  const groups = [
    { g: "ELECTRICITY", items: [
      ["dashboard", "Dashboard", "board", "var(--fg-primary)"],
      ["spot", "JEPX Spot", "spot", "var(--c-spot)"],
      ["reserve", "Reserve Margin", "power", "var(--c-power)"],
      ["imb", "Imbalance", "won", "var(--c-imb)"],
      ["jkm", "JKM LNG", "fire", "var(--c-jkm)"],
      ["weather", "Weather", "weather", "var(--c-weather)"],
      ["hjks", "Generation", "plant", "var(--c-hjks)"],
    ]},
    { g: "WORKSPACE", items: [
      ["calendar", "Calendar", "calendar", "var(--c-cal)"],
      ["gmail", "Gmail", "gmail", "var(--c-mail)"],
      ["notice", "Notifications", "notice", "var(--c-notice)"],
    ]},
    { g: "AI", items: [
      ["ai", "Chat", "chat", "var(--c-ai)"],
      ["brief", "Briefing", "brief", "var(--c-ai)"],
      ["memo", "Memo", "memo", "var(--c-memo)"],
    ]},
  ];
  return (
    <aside style={{
      width: 200, flexShrink: 0,
      background: "var(--bg-surface)",
      borderRight: "1px solid var(--border)",
      display: "flex", flexDirection: "column",
      padding: "10px 8px",
      overflow: "auto",
    }} className="lee-scroll">
      {groups.map((gr, gi) => (
        <div key={gi} style={{ marginBottom: 12 }}>
          <div style={{
            padding: "6px 8px", fontSize: 9, fontWeight: 800,
            color: "var(--fg-tertiary)", letterSpacing: "0.1em",
          }}>{gr.g}</div>
          {gr.items.map(([id, label, icon, color]) => {
            const isActive = active === id;
            return (
              <button key={id} onClick={() => onSelect(id)}
                style={{
                  width: "100%", display: "flex", alignItems: "center", gap: 8,
                  padding: "6px 8px", borderRadius: 4, border: "none",
                  background: isActive ? "var(--bg-surface-2)" : "transparent",
                  color: isActive ? color : "var(--fg-secondary)",
                  borderLeft: isActive ? `2px solid ${color}` : "2px solid transparent",
                  fontFamily: "inherit", fontSize: 12, fontWeight: 600,
                  cursor: "pointer", textAlign: "left", marginBottom: 1,
                }}>
                <Ic name={icon} size={13} stroke={2}/>
                <span>{label}</span>
              </button>
            );
          })}
        </div>
      ))}
      <div style={{ flex: 1 }}/>
      <div style={{
        borderTop: "1px solid var(--border)", paddingTop: 8,
        fontSize: 10, color: "var(--fg-tertiary)", padding: 8,
        fontFamily: "var(--font-mono)",
      }}>
        v 2.0.0<br/>
        李 田中 · ANALYST
      </div>
    </aside>
  );
};

window.VarB_parts = { VBSpark, VBPrecisionChart, VBPanel, VBStat, VBTopBar, VBSidebar };
