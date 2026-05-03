/* global React */
// Variation B — Dashboard composition (trading-grade dense)
const { useState: vbAS, useEffect: vbAE } = React;
const { VBSpark, VBPrecisionChart, VBPanel, VBStat, VBTopBar, VBSidebar } = window.VarB_parts;
const D2 = window.LEE_DATA;

const VarBDashboard = ({ isDark, onCardClick }) => {
  return (
    <div className="lee-scroll" style={{
      flex: 1, overflow: "auto", padding: 12,
      background: "var(--bg-app)",
      display: "grid",
      gridTemplateColumns: "1.6fr 1fr 1fr",
      gridAutoRows: "min-content",
      gap: 8,
      gridAutoFlow: "row dense",
    }}>
      {/* SPOT — wide hero with precision chart */}
      <div style={{ gridColumn: "1 / 2", gridRow: "1 / 3" }}>
        <VBPanel title="JEPX SPOT — TYO" accent="var(--c-spot)" badge="LIVE" onClick={() => onCardClick("spot")}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 12 }}>
            <div style={{ display: "flex", gap: 24 }}>
              <VBStat label="AVG" value="15.42" unit="¥/kWh" color="var(--c-spot)" delta={2.1} deltaPositive={true}/>
              <VBStat label="HIGH" value="33.20" unit="¥" color="var(--c-imb)"/>
              <VBStat label="LOW" value="5.80" unit="¥"/>
              <VBStat label="VOL" value="487.2" unit="GWh"/>
            </div>
            <div style={{ display: "flex", gap: 1, padding: 1, background: "var(--bg-surface-2)", borderRadius: 4 }}>
              {["TODAY","TOMORROW","WEEK"].map((p, i) => (
                <button key={p} style={{
                  border: "none", padding: "3px 9px", borderRadius: 3,
                  background: i === 0 ? "var(--c-spot)" : "transparent",
                  color: i === 0 ? "#fff" : "var(--fg-secondary)",
                  fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 700, cursor: "pointer", letterSpacing: "0.05em",
                }}>{p}</button>
              ))}
            </div>
          </div>
          <VBPrecisionChart data={D2.spotCurve.map(d=>d.price)} color="var(--c-spot)" w={520} h={170} label="spot"/>
        </VBPanel>
      </div>

      {/* RESERVE */}
      <VBPanel title="RESERVE MARGIN" accent="var(--c-power)" badge="WARN" onClick={() => onCardClick("reserve")}>
        <VBStat label="MIN" value="6.2" unit="%" color="var(--c-bad)" delta={0.4} deltaPositive={false}/>
        <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "repeat(10, 1fr)", gap: 1, alignItems: "end", height: 52 }}>
          {D2.reserve.map((r, i) => {
            const c = r.status === "bad" ? "var(--c-bad)" : r.status === "warn" ? "var(--c-warn)" : "var(--c-power)";
            return <div key={i} style={{ height: `${(r.value/16)*100}%`, background: c }}/>;
          })}
        </div>
        <div style={{ marginTop: 4, display: "grid", gridTemplateColumns: "repeat(10, 1fr)", gap: 1, fontSize: 8, fontFamily: "var(--font-mono)", color: "var(--fg-tertiary)", textAlign: "center" }}>
          {D2.reserve.map((r, i) => <div key={i}>{r.area.slice(0,2)}</div>)}
        </div>
      </VBPanel>

      {/* IMBALANCE */}
      <VBPanel title="IMBALANCE" accent="var(--c-imb)" badge="ALERT" onClick={() => onCardClick("imb")}>
        <VBStat label="MAX TODAY" value="38.50" unit="¥/kWh" color="var(--c-imb)" delta={12.4} deltaPositive={true}/>
        <div style={{ marginTop: 8, fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--fg-secondary)", display: "flex", justifyContent: "space-between" }}>
          <span>18:30 / TYO</span><span>+3σ ABOVE BAND</span>
        </div>
        <div style={{ marginTop: 6 }}>
          <VBSpark data={D2.imbalance.slice(0, 36).map(d=>d.value)} color="var(--c-imb)" w={220} h={36}/>
        </div>
      </VBPanel>

      {/* JKM */}
      <VBPanel title="JKM LNG" accent="var(--c-jkm)" badge="USD" onClick={() => onCardClick("jkm")}>
        <VBStat label="LAST" value="14.32" unit="USD" color="var(--c-jkm)" delta={1.2} deltaPositive={false}/>
        <div style={{ marginTop: 8, fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--fg-secondary)" }}>
          7D RANGE: 13.85 — 15.20
        </div>
        <div style={{ marginTop: 6 }}>
          <VBSpark data={D2.jkmHistory.map(d=>d.v)} color="var(--c-jkm)" w={220} h={40}/>
        </div>
      </VBPanel>

      {/* HJKS */}
      <VBPanel title="GENERATION CAPACITY" accent="var(--c-hjks)" badge="NATIONAL" onClick={() => onCardClick("hjks")}>
        <VBStat label="OPERATING" value="172.3" unit="GW"/>
        <div style={{ marginTop: 10, display: "flex", height: 6, borderRadius: 2, overflow: "hidden", background: "var(--bg-surface-2)" }}>
          {D2.hjks.map((s, i) => (
            <div key={i} style={{ flex: s.operating, background: s.color }} title={s.source}/>
          ))}
        </div>
        <div style={{ marginTop: 8, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 4, fontSize: 9 }}>
          {D2.hjks.slice(0, 6).map((s, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 4, fontFamily: "var(--font-mono)" }}>
              <span style={{ width: 6, height: 6, background: s.color, borderRadius: 1 }}/>
              <span style={{ color: "var(--fg-secondary)" }}>{s.source}</span>
              <span style={{ color: "var(--fg-primary)", fontWeight: 600, marginLeft: "auto" }}>{(s.operating/1000).toFixed(1)}</span>
            </div>
          ))}
        </div>
      </VBPanel>

      {/* WEATHER */}
      <VBPanel title="WEATHER 10-AREA" accent="var(--c-weather)" onClick={() => onCardClick("weather")}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, fontSize: 10, fontFamily: "var(--font-mono)" }}>
          {D2.weather.slice(0, 8).map((w, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, padding: "3px 6px", background: "var(--bg-surface-2)", borderRadius: 3 }}>
              <span style={{ width: 6, height: 6, background: w.accent, borderRadius: 1 }}/>
              <span style={{ color: "var(--fg-secondary)" }}>{w.region}</span>
              <span style={{ marginLeft: "auto", color: "var(--fg-primary)", fontWeight: 700 }}>{w.temp}°</span>
            </div>
          ))}
        </div>
      </VBPanel>

      {/* CALENDAR */}
      <VBPanel title="SCHEDULE" accent="var(--c-cal)" badge="3 TODAY" onClick={() => onCardClick("calendar")}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {D2.calendar.slice(0, 3).map((e, i) => (
            <div key={i} style={{ display: "flex", gap: 8, padding: 6, background: "var(--bg-surface-2)", borderRadius: 3, alignItems: "center" }}>
              <div style={{ width: 2, height: 22, background: e.color, borderRadius: 1 }}/>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: "var(--fg-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.title}</div>
                <div style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--fg-tertiary)" }}>{e.time}</div>
              </div>
            </div>
          ))}
        </div>
      </VBPanel>

      {/* GMAIL */}
      <VBPanel title="INBOX" accent="var(--c-mail)" badge="12 UNREAD" onClick={() => onCardClick("gmail")}>
        <div style={{ display: "flex", flexDirection: "column" }}>
          {D2.gmail.slice(0, 4).map((m, i) => (
            <div key={i} style={{
              display: "flex", gap: 6, padding: "4px 0",
              borderBottom: i < 3 ? "1px dashed var(--border-subtle)" : "none",
              alignItems: "center",
            }}>
              <div style={{ width: 14, height: 14, borderRadius: 3, background: m.color, color: "#fff", fontSize: 8, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>{m.initial}</div>
              <span style={{ fontSize: 10, fontWeight: m.unread ? 700 : 500, color: "var(--fg-primary)", whiteSpace: "nowrap" }}>{m.from}</span>
              <span style={{ fontSize: 10, color: "var(--fg-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{m.subject}</span>
              <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--fg-tertiary)" }}>{m.time}</span>
            </div>
          ))}
        </div>
      </VBPanel>

      {/* NOTIFICATIONS */}
      <VBPanel title="ALERTS" accent="var(--c-notice)" badge="3 NEW" onClick={() => onCardClick("notice")}>
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          {D2.notices.slice(0, 4).map((n, i) => (
            <div key={i} style={{
              display: "flex", gap: 6, padding: "4px 6px", alignItems: "center",
              background: n.unread ? `color-mix(in srgb, ${n.color} 10%, transparent)` : "transparent",
              borderLeft: `2px solid ${n.color}`,
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: "var(--fg-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{n.title}</div>
                <div style={{ fontSize: 9, color: "var(--fg-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{n.body}</div>
              </div>
              <span style={{ fontSize: 8, fontFamily: "var(--font-mono)", color: "var(--fg-tertiary)" }}>{n.time}</span>
            </div>
          ))}
        </div>
      </VBPanel>

      {/* AI BRIEFING — wide */}
      <div style={{ gridColumn: "1 / 3" }}>
        <VBPanel title="AI BRIEFING" accent="var(--c-ai)" badge="06:00 GENERATED" onClick={() => onCardClick("brief")}>
          <div style={{ fontSize: 12, lineHeight: 1.65, color: "var(--fg-primary)" }}>
            おはようございます。本日は <b style={{color:"var(--c-imb)"}}>東京エリアの予備率が 6.2%</b> と警戒水準に近づいています。スポット価格は前日比 <b style={{color:"var(--c-bad)"}}>+8.4%</b>、特に夕方ピーク帯の上昇が顕著。LNG (JKM) は 14.32 USD で <b style={{color:"var(--c-ok)"}}>下落基調</b>。9:00 のチーム MTG 前にご確認ください。
          </div>
        </VBPanel>
      </div>

      {/* AI CHAT */}
      <VBPanel title="AI CHAT" accent="var(--c-ai)" onClick={() => onCardClick("ai")}>
        <div style={{
          padding: "6px 8px", background: "var(--c-ai)", color: "#fff",
          fontSize: 10, borderRadius: 3, marginBottom: 4, alignSelf: "flex-end",
          maxWidth: "85%", marginLeft: "auto",
        }}>明日 TYO のスポット予測は?</div>
        <div style={{
          padding: "6px 8px", background: "var(--bg-surface-2)", color: "var(--fg-primary)",
          fontSize: 10, borderRadius: 3, lineHeight: 1.5,
        }}>明日 TYO 平均 <b style={{color:"var(--c-spot)"}}>11.42 円/kWh</b> 予測。最高 18-19 時 <b style={{color:"var(--c-imb)"}}>16.8 円</b>。</div>
      </VBPanel>
    </div>
  );
};

const VarBApp = () => {
  const [active, setActive] = vbAS("dashboard");
  const [topTab, setTopTab] = vbAS("MARKET");
  const [isDark, setIsDark] = vbAS(true);

  vbAE(() => {
    document.documentElement.setAttribute("data-theme", isDark ? "dark" : "light");
  }, [isDark]);

  return (
    <div style={{
      width: "100%", height: "100%", display: "flex", flexDirection: "column",
      background: "var(--bg-app)", color: "var(--fg-primary)",
      fontFamily: "var(--font-sans)",
    }}>
      <VBTopBar isDark={isDark} onThemeToggle={() => setIsDark(d => !d)} activeTab={topTab} onTab={setTopTab}/>
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        <VBSidebar active={active} onSelect={setActive}/>
        <VarBDashboard isDark={isDark} onCardClick={setActive}/>
      </div>
    </div>
  );
};

window.VarBApp = VarBApp;
