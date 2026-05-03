/* global React, Ic */
// Calendar + Gmail detail screens
const { useState: c5S } = React;
const { KPI, DetailHeader } = window.varA_detail_atoms;
const { Pill } = window.varA_atoms;
const C5 = window.LEE_DATA;

// ── Calendar Detail ──────────────────────────────────────
const CalendarDetail = ({ onBack }) => {
  const today = 22;
  const events = C5.calendar;
  // Build a 5-week mini month grid starting from prev month's days
  const startWeekday = 3; // Jan 1 2025 was Wed; offset
  const totalDays = 31;
  const cells = [];
  for (let i = 0; i < startWeekday; i++) cells.push({ day: 28 + i, dim: true });
  for (let d = 1; d <= totalDays; d++) cells.push({ day: d, dim: false });
  while (cells.length < 35) cells.push({ day: cells.length - totalDays - startWeekday + 1, dim: true });

  return (
    <div style={{ padding: 28 }}>
      <DetailHeader
        title="Google カレンダー"
        subtitle="今月の予定 · 同期 09:14"
        accent="#34C759"
        icon="calendar"
        onBack={onBack}
        badge={`${events.length} 件`}
      />

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 16 }}>
        {/* Month grid */}
        <div style={{
          background: "var(--bg-surface)", borderRadius: 18, padding: 22,
          border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
        }}>
          <div style={{ display: "flex", alignItems: "center", marginBottom: 16 }}>
            <div style={{ fontSize: 18, fontWeight: 800 }}>2025年 1月</div>
            <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
              {["<", "今日", ">"].map((b, i) => (
                <button key={i} style={{
                  padding: "6px 12px", borderRadius: 8, border: "1px solid var(--border)",
                  background: i === 1 ? "#34C759" : "var(--bg-surface)",
                  color: i === 1 ? "#fff" : "var(--fg-primary)",
                  fontFamily: "inherit", fontSize: 12, fontWeight: 700, cursor: "pointer",
                }}>{b}</button>
              ))}
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4 }}>
            {["日", "月", "火", "水", "木", "金", "土"].map((d, i) => (
              <div key={i} style={{
                fontSize: 11, fontWeight: 700, color: i === 0 ? "#FF453A" : i === 6 ? "#0A84FF" : "var(--fg-tertiary)",
                textAlign: "center", padding: "6px 0", letterSpacing: "0.06em",
              }}>{d}</div>
            ))}
            {cells.map((c, i) => {
              const dayEvents = events.filter(e => e.day === c.day && !c.dim);
              const isToday = !c.dim && c.day === today;
              return (
                <div key={i} style={{
                  minHeight: 78, padding: 6, borderRadius: 8,
                  background: isToday ? "#34C75914" : "var(--bg-surface-2)",
                  border: isToday ? "1.5px solid #34C759" : "1px solid var(--border-subtle)",
                  opacity: c.dim ? 0.35 : 1,
                  display: "flex", flexDirection: "column", gap: 3,
                }}>
                  <div style={{
                    fontSize: 12, fontWeight: isToday ? 800 : 600,
                    color: isToday ? "#34C759" : "var(--fg-primary)",
                  }}>{c.day}</div>
                  {dayEvents.slice(0, 2).map((e, j) => (
                    <div key={j} style={{
                      fontSize: 9, padding: "2px 5px", borderRadius: 4,
                      background: `${e.color}22`, color: e.color, fontWeight: 700,
                      whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                    }}>{e.time} {e.title}</div>
                  ))}
                  {dayEvents.length > 2 && (
                    <div style={{ fontSize: 9, color: "var(--fg-tertiary)" }}>+{dayEvents.length - 2}件</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Upcoming list */}
        <div style={{
          background: "var(--bg-surface)", borderRadius: 18, padding: 22,
          border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
        }}>
          <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 14 }}>今後の予定</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {events.map((e, i) => (
              <div key={i} style={{
                padding: 14, borderRadius: 12,
                background: "var(--bg-surface-2)",
                borderLeft: `3px solid ${e.color}`,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <span style={{
                    fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                    background: e.color, color: "#fff", letterSpacing: "0.04em",
                  }}>{e.cal}</span>
                  <span style={{ fontSize: 11, color: "var(--fg-tertiary)", fontFamily: "var(--font-mono)" }}>
                    1/{String(e.day).padStart(2, "0")} · {e.time}
                  </span>
                </div>
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--fg-primary)" }}>{e.title}</div>
              </div>
            ))}
          </div>
          <button style={{
            marginTop: 14, width: "100%", padding: "10px",
            border: "1px dashed var(--border)", borderRadius: 10,
            background: "transparent", color: "var(--fg-secondary)",
            fontFamily: "inherit", fontSize: 12, fontWeight: 700, cursor: "pointer",
          }}>+ 予定を追加</button>
        </div>
      </div>
    </div>
  );
};

// ── Gmail Detail ──────────────────────────────────────
const GmailDetail = ({ onBack }) => {
  const [sel, setSel] = c5S(0);
  const cur = C5.gmail[sel];
  const labels = ["全て", "緊急", "市場", "ニュース", "社内", "天気"];
  const [activeLabel, setActiveLabel] = c5S("全て");
  const filtered = activeLabel === "全て" ? C5.gmail : C5.gmail.filter(m => m.label === activeLabel);

  return (
    <div style={{ padding: 28 }}>
      <DetailHeader
        title="Gmail"
        subtitle="lee.tanaka@enex.co.jp · 受信箱"
        accent="#FF7A45"
        icon="gmail"
        onBack={onBack}
        badge={`${C5.gmail.filter(m => m.unread).length} 未読`}
      />

      {/* Label tabs */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
        {labels.map(l => (
          <button key={l} onClick={() => setActiveLabel(l)}
            style={{
              padding: "8px 14px", borderRadius: 10, border: "1px solid",
              borderColor: activeLabel === l ? "#FF7A45" : "var(--border)",
              background: activeLabel === l ? "#FF7A45" : "var(--bg-surface)",
              color: activeLabel === l ? "#fff" : "var(--fg-secondary)",
              fontFamily: "inherit", fontSize: 12, fontWeight: 700, cursor: "pointer",
            }}>{l}</button>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1.4fr", gap: 16 }}>
        {/* List */}
        <div style={{
          background: "var(--bg-surface)", borderRadius: 18, padding: 8,
          border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
          maxHeight: 540, overflow: "auto",
        }}>
          {filtered.map((m, i) => {
            const idx = C5.gmail.indexOf(m);
            const isActive = sel === idx;
            return (
              <div key={i} onClick={() => setSel(idx)} style={{
                padding: "12px 14px", borderRadius: 12, cursor: "pointer",
                background: isActive ? "#FF7A4514" : "transparent",
                borderLeft: isActive ? "3px solid #FF7A45" : "3px solid transparent",
                marginBottom: 2,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                  <div style={{
                    width: 32, height: 32, borderRadius: 999,
                    background: m.color, color: "#fff",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 13, fontWeight: 700,
                  }}>{m.initial}</div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12, fontWeight: m.unread ? 800 : 600, color: "var(--fg-primary)" }}>{m.from}</div>
                    <div style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>{m.time} · {m.label}</div>
                  </div>
                  {m.unread && <span style={{ width: 8, height: 8, borderRadius: 999, background: "#FF7A45" }}/>}
                </div>
                <div style={{ fontSize: 12, fontWeight: m.unread ? 700 : 500, color: "var(--fg-primary)", marginBottom: 2, lineHeight: 1.4 }}>{m.subject}</div>
                <div style={{ fontSize: 11, color: "var(--fg-secondary)", lineHeight: 1.4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{m.preview}</div>
              </div>
            );
          })}
        </div>

        {/* Reading pane */}
        <div style={{
          background: "var(--bg-surface)", borderRadius: 18, padding: 24,
          border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, paddingBottom: 16, borderBottom: "1px solid var(--border-subtle)" }}>
            <div style={{
              width: 44, height: 44, borderRadius: 999,
              background: cur.color, color: "#fff",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 16, fontWeight: 700,
            }}>{cur.initial}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>{cur.from}</div>
              <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>受信: 2025年1月22日 · {cur.time}</div>
            </div>
            <Pill color="#FF7A45">{cur.label}</Pill>
          </div>
          <div style={{ fontSize: 20, fontWeight: 800, color: "var(--fg-primary)", marginBottom: 14, letterSpacing: "-0.01em" }}>{cur.subject}</div>
          <div style={{ fontSize: 13, color: "var(--fg-primary)", lineHeight: 1.7, marginBottom: 18 }}>
            <p style={{ marginBottom: 12 }}>{cur.from}様、いつもお世話になっております。</p>
            <p style={{ marginBottom: 12 }}>{cur.preview} 詳細は以下の通りです。引き続きの監視と必要な対応のご検討をお願いいたします。</p>
            <p style={{ marginBottom: 12, padding: 12, background: "var(--bg-surface-2)", borderRadius: 8, fontFamily: "var(--font-mono)", fontSize: 11 }}>
              本日 18:30<br/>
              東京エリア 予備率: 6.2%<br/>
              想定需要: 49.3 GW / 供給力: 52.4 GW<br/>
              インバランス単価最大: 38.50 円/kWh
            </p>
            <p>何卒よろしくお願いいたします。</p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {[["返信", "#FF7A45"], ["転送", "var(--bg-surface-2)"], ["アーカイブ", "var(--bg-surface-2)"]].map(([l, bg], i) => (
              <button key={i} style={{
                padding: "8px 16px", borderRadius: 10, border: "none",
                background: bg, color: i === 0 ? "#fff" : "var(--fg-primary)",
                fontFamily: "inherit", fontSize: 12, fontWeight: 700, cursor: "pointer",
              }}>{l}</button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

window.varA_detail_screens5 = { CalendarDetail, GmailDetail };
