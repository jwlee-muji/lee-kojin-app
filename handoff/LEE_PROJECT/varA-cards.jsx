/* global React, Ic, varA_atoms, WeatherIllust */
// Variation A — Dashboard cards
const { Card, IconTile, Pill, Trend, Sparkline, CountValue } = window.varA_atoms;
const { useState: useStateVA, useEffect: useEffectVA } = React;
const DD = window.LEE_DATA;

// 1) Imbalance card
const ImbCard = ({ onClick }) => (
  <Card onClick={onClick}>
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
      <IconTile name="won" color="var(--c-imb)"/>
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-secondary)" }}>本日の最大インバランス</div>
        <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>OCCTO リアルタイム</div>
      </div>
    </div>
    <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 4 }}>
      <CountValue target={38.50} format={(v)=>v.toFixed(2)}
        style={{ fontSize: 38, fontWeight: 800, color: "var(--c-imb)", letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums" }}/>
      <span style={{ fontSize: 14, color: "var(--fg-tertiary)", fontWeight: 600 }}>円/kWh</span>
    </div>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <span style={{ fontSize: 12, color: "var(--fg-secondary)" }}>18:30 / 東京エリア</span>
      <Pill color="var(--c-imb)">⚠ 警戒</Pill>
    </div>
    <div style={{ marginTop: 14 }}>
      <Sparkline data={DD.imbalance.slice(0, 36).map(d=>d.value)} color="var(--c-imb)" w={260} h={36}/>
    </div>
  </Card>
);

// 2) Reserve card — 가로 정렬형: エリア / 막대 / 값을 한 row에
const ReserveCard = ({ onClick }) => {
  const sorted = [...DD.reserve].sort((a, b) => a.value - b.value);
  const worst = sorted[0];
  const colorFor = (status) =>
    status === "bad" ? "var(--c-bad)" : status === "warn" ? "var(--c-warn)" : "var(--c-power)";
  // 카드는 경고 영역만 (warn + bad) 표시 → "주의가 필요한 에리어"에 집중
  const focus = sorted.filter(r => r.status !== "ok").slice(0, 5);
  const display = focus.length >= 3 ? focus : sorted.slice(0, 5);
  const maxV = Math.max(...display.map(r => r.value), 16);

  return (
    <Card onClick={onClick}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
        <IconTile name="power" color="var(--c-power)"/>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-secondary)" }}>本日の最低予備率</div>
          <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>
            {worst.area}エリア · OCCTO {worst.status === "bad" ? "注意喚起" : "監視中"}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 3 }}>
          <CountValue target={worst.value} format={(v)=>v.toFixed(1)}
            style={{ fontSize: 34, fontWeight: 800, color: colorFor(worst.status), letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums", lineHeight: 1 }}/>
          <span style={{ fontSize: 13, color: "var(--fg-tertiary)", fontWeight: 600 }}>%</span>
        </div>
      </div>

      {/* Sub label for chart */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "44px 1fr 56px",
        columnGap: 10,
        fontSize: 9, fontWeight: 700, color: "var(--fg-tertiary)",
        letterSpacing: "0.08em", textTransform: "uppercase",
        marginBottom: 6, paddingBottom: 4,
        borderBottom: "1px solid var(--border-subtle)",
      }}>
        <span>エリア</span>
        <span>予備率</span>
        <span style={{ textAlign: "right" }}>値 (%)</span>
      </div>

      {/* Rows: エリア / bar / 값 가 정확히 정렬됨 */}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {display.map((r) => {
          const c = colorFor(r.status);
          const w = Math.min(100, (r.value / maxV) * 100);
          return (
            <div key={r.area} style={{
              display: "grid",
              gridTemplateColumns: "44px 1fr 56px",
              columnGap: 10,
              alignItems: "center",
              fontSize: 12,
            }}>
              <span style={{
                fontWeight: 700,
                color: r.status === "bad" ? "var(--c-bad)" : "var(--fg-primary)",
              }}>{r.area}</span>
              <div style={{
                position: "relative",
                height: 8,
                background: "var(--bg-surface-2)",
                borderRadius: 999,
                overflow: "hidden",
              }}>
                <div style={{
                  position: "absolute", inset: 0, right: "auto",
                  width: `${w}%`,
                  background: c,
                  borderRadius: 999,
                  transition: "width 0.5s ease",
                  boxShadow: r.status === "bad" ? `0 0 0 1px ${c}` : "none",
                }}/>
              </div>
              <span style={{
                textAlign: "right",
                fontFamily: "var(--font-mono)",
                fontVariantNumeric: "tabular-nums",
                fontWeight: 700,
                color: c,
              }}>{r.value.toFixed(1)}</span>
            </div>
          );
        })}
      </div>
    </Card>
  );
};

// 3) Spot card with toggle
const SpotCard = ({ onClick }) => {
  const [mode, setMode] = useStateVA("today");
  const [idx, setIdx] = useStateVA(0);
  useEffectVA(() => {
    const t = setInterval(() => setIdx(i => (i + 1) % DD.spotAreas.length), 2500);
    return () => clearInterval(t);
  }, []);
  const cur = DD.spotAreas[idx];
  return (
    <Card onClick={onClick}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
        <IconTile name="spot" color="var(--c-spot)"/>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-secondary)" }}>JEPX スポット平均</div>
        </div>
        <div style={{ display: "flex", background: "var(--bg-surface-2)", borderRadius: 999, padding: 2 }}>
          {["today","tomorrow"].map(m => (
            <button key={m} onClick={(e)=>{e.stopPropagation(); setMode(m);}}
              style={{
                border: "none", padding: "5px 12px", borderRadius: 999, fontSize: 11, fontWeight: 600, cursor: "pointer",
                background: mode === m ? "var(--c-spot)" : "transparent",
                color: mode === m ? "#fff" : "var(--fg-secondary)",
                fontFamily: "inherit",
              }}>
              {m === "today" ? "今日" : "明日"}
            </button>
          ))}
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12 }}>
        <span style={{ fontSize: 22, fontWeight: 700, color: "var(--c-spot)" }}>{cur.area}</span>
        <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
          <span style={{ fontSize: 32, fontWeight: 800, color: "var(--fg-primary)", letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums" }}>
            {cur.avg.toFixed(2)}
          </span>
          <span style={{ fontSize: 12, color: "var(--fg-tertiary)", fontWeight: 600 }}>円/kWh</span>
          <Trend v={cur.trend}/>
        </div>
      </div>
      <Sparkline data={DD.spotCurve.map(d=>d.price)} color="var(--c-spot)" w={300} h={48}/>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6, fontSize: 11, color: "var(--fg-tertiary)" }}>
        <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span>
      </div>
    </Card>
  );
};

// 4) Energy Indicators card (旧 JKM)
const JkmCard = ({ onClick }) => (
  <Card onClick={onClick}>
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
      <IconTile name="fire" color="var(--c-jkm)"/>
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-secondary)" }}>エネルギー指標</div>
        <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>LNG · 原油 · 石炭 · 為替</div>
      </div>
    </div>
    <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 6 }}>
      <CountValue target={14.32} format={(v)=>v.toFixed(2)}
        style={{ fontSize: 38, fontWeight: 800, color: "var(--c-jkm)", letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums" }}/>
      <span style={{ fontSize: 14, color: "var(--fg-tertiary)", fontWeight: 600 }}>USD</span>
      <span style={{ marginLeft: "auto", color: "var(--c-ok)", fontSize: 13, fontWeight: 700 }}>▼ 1.2%</span>
    </div>
    <div style={{ marginTop: 8 }}>
      <Sparkline data={DD.jkmHistory.map(d=>d.v)} color="var(--c-jkm)" w={260} h={50}/>
    </div>
  </Card>
);

// 5) HJKS card
const HjksCard = ({ onClick }) => {
  const total = DD.hjks.reduce((a,b)=>a+b.operating, 0);
  return (
    <Card onClick={onClick}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
        <IconTile name="plant" color="var(--c-hjks)"/>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-secondary)" }}>本日の発電稼働容量</div>
          <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>HJKS · 全国合計</div>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 14 }}>
        <CountValue target={total/1000} format={(v)=>v.toFixed(1)}
          style={{ fontSize: 38, fontWeight: 800, color: "var(--fg-primary)", letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums" }}/>
        <span style={{ fontSize: 14, color: "var(--fg-tertiary)", fontWeight: 600 }}>GW</span>
      </div>
      <div style={{ display: "flex", height: 8, borderRadius: 999, overflow: "hidden", background: "var(--bg-surface-2)" }}>
        {DD.hjks.map((s, i) => (
          <div key={i} style={{ flex: s.operating, background: s.color }} title={`${s.source} ${s.operating}MW`}/>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginTop: 12 }}>
        {DD.hjks.slice(0, 6).map((s, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: s.color }}/>
            <span style={{ color: "var(--fg-secondary)" }}>{s.source}</span>
          </div>
        ))}
      </div>
    </Card>
  );
};

// 6) Weather card
const WeatherCard = ({ onClick, isDark }) => {
  const [idx, setIdx] = useStateVA(0);
  useEffectVA(() => {
    const t = setInterval(() => setIdx(i => (i + 1) % DD.weather.length), 3000);
    return () => clearInterval(t);
  }, []);
  const cur = DD.weather[idx];
  return (
    <Card onClick={onClick} padding={0}>
      <div style={{
        background: `linear-gradient(180deg, ${cur.accent}33 0%, transparent 60%)`,
        padding: 24, height: "100%", display: "flex", flexDirection: "column",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
          <IconTile name="weather" color="var(--c-weather)"/>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-secondary)" }}>全国天気</div>
            <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>Open-Meteo · 10地域</div>
          </div>
        </div>
        <div style={{ flex: 1, display: "flex", justifyContent: "center", alignItems: "center" }}>
          <WeatherIllust category={cur.wmo} isDark={isDark} w={160} h={120}/>
        </div>
        <div style={{ marginTop: 8 }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: cur.accent }}>{cur.region}</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 4, marginTop: 2 }}>
            <span style={{ fontSize: 36, fontWeight: 800, color: "var(--fg-primary)", letterSpacing: "-0.02em" }}>{cur.temp}</span>
            <span style={{ fontSize: 16, color: "var(--fg-tertiary)" }}>°C</span>
          </div>
          <div style={{ fontSize: 12, color: "var(--fg-secondary)", marginTop: 2 }}>{cur.text}</div>
          <div style={{ display: "flex", gap: 4, marginTop: 12 }}>
            {DD.weather.map((_, i) => (
              <div key={i} style={{
                width: i === idx ? 16 : 4, height: 4, borderRadius: 2,
                background: i === idx ? cur.accent : "var(--border)",
                transition: "all 0.3s ease",
              }}/>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
};

window.varA_cards = { ImbCard, ReserveCard, SpotCard, JkmCard, HjksCard, WeatherCard };
