/* global React */
// ============================================================
// HJKS 詳細 — 発電稼働状況
// 9エリア × 7電源種別 × 日次 (期間指定)
// ============================================================
const { useState: h4S, useMemo: h4M } = React;
const { KPI, DetailHeader, ChartFrame } = window.varA_detail_atoms;
const { DateRangeInput, fmtISO, parseISO } = window.varA_datepicker;
const H4 = window.LEE_DATA;

const HJKS_AREAS = [
  { id: "hokkaido", name: "北海道", color: "#5B8DEF" },
  { id: "tohoku",   name: "東北",   color: "#34C759" },
  { id: "tokyo",    name: "東京",   color: "#FF7A45" },
  { id: "chubu",    name: "中部",   color: "#A78BFA" },
  { id: "hokuriku", name: "北陸",   color: "#2EC4B6" },
  { id: "kansai",   name: "関西",   color: "#F25C7A" },
  { id: "chugoku",  name: "中国",   color: "#F59E0B" },
  { id: "shikoku",  name: "四国",   color: "#10B981" },
  { id: "kyushu",   name: "九州",   color: "#EF4444" },
];

const HJKS_AREA_CAPACITY = {
  hokkaido: { 原子力: 0,    石炭火力: 1800, LNG火力: 1200, 石油火力: 600,  水力: 1200, 太陽光: 1800, 風力: 1100 },
  tohoku:   { 原子力: 800,  石炭火力: 3200, LNG火力: 3800, 石油火力: 800,  水力: 2400, 太陽光: 3400, 風力: 1300 },
  tokyo:    { 原子力: 0,    石炭火力: 4800, LNG火力: 12200,石油火力: 2200, 水力: 2200, 太陽光: 4200, 風力: 200  },
  chubu:    { 原子力: 0,    石炭火力: 2400, LNG火力: 6800, 石油火力: 600,  水力: 2200, 太陽光: 3200, 風力: 300  },
  hokuriku: { 原子力: 0,    石炭火力: 800,  LNG火力: 1400, 石油火力: 200,  水力: 1900, 太陽光: 700,  風力: 200  },
  kansai:   { 原子力: 4700, 石炭火力: 2200, LNG火力: 3800, 石油火力: 800,  水力: 1700, 太陽光: 2800, 風力: 400  },
  chugoku:  { 原子力: 1300, 石炭火力: 2400, LNG火力: 1200, 石油火力: 600,  水力: 1100, 太陽光: 2400, 風力: 200  },
  shikoku:  { 原子力: 900,  石炭火力: 800,  LNG火力: 800,  石油火力: 200,  水力: 800,  太陽光: 1100, 風力: 200  },
  kyushu:   { 原子力: 4500, 石炭火力: 0,    LNG火力: 900,  石油火力: 0,    水力: 1300, 太陽光: 4000, 風力: 200  },
};

const HJKS_FUELS = ["原子力", "石炭火力", "LNG火力", "石油火力", "水力", "太陽光", "風力"];
const HJKS_FUEL_COLOR = Object.fromEntries(H4.hjks.map(h => [h.source, h.color]));

// 日次 平均稼働率 (季節 + 曜日 + 微ノイズ)
const dailyUtil = (fuel, dayIdx) => {
  // dayIdx: 2026-01-01 起点
  const d = new Date(2026, 0, 1);
  d.setDate(d.getDate() + dayIdx);
  const month = d.getMonth(); // 0-11
  const dow = d.getDay();

  // 季節係数 (夏冬高需要)
  const summer = Math.exp(-Math.pow((month - 7) / 2, 2));  // 8月ピーク
  const winter = Math.exp(-Math.pow((month - 0) / 2, 2)) + Math.exp(-Math.pow((month - 11) / 2, 2));
  const seasonHi = Math.max(summer, winter * 0.85);

  const noise = (Math.sin(dayIdx * 0.7) + Math.cos(dayIdx * 1.3)) * 0.04;
  const weekend = (dow === 0 || dow === 6) ? -0.05 : 0;

  if (fuel === "太陽光") {
    // 春~初夏ピーク, 冬低
    const solar = 0.42 + 0.28 * Math.exp(-Math.pow((month - 4) / 3, 2)) - 0.1 * winter * 0.3;
    return Math.max(0.18, solar + noise);
  }
  if (fuel === "風力") {
    // 冬高
    return Math.max(0.25, 0.42 + 0.18 * winter * 0.4 + noise);
  }
  if (fuel === "原子力") return 0.92 + noise * 0.3;
  if (fuel === "石炭火力") return Math.min(0.92, 0.7 + 0.15 * seasonHi + weekend + noise);
  if (fuel === "LNG火力") return Math.min(0.95, 0.62 + 0.22 * seasonHi + weekend + noise);
  if (fuel === "石油火力") return Math.max(0.05, 0.12 + 0.25 * seasonHi + noise);
  if (fuel === "水力") return 0.55 + 0.18 * Math.exp(-Math.pow((month - 5) / 3, 2)) + noise; // 梅雨~夏
  return 0.6;
};

const dayIdxFromISO = (s) => {
  const d = parseISO(s);
  const base = new Date(2026, 0, 1);
  return Math.round((d - base) / 86400000);
};

// 期間内の日次集計 (各日 各電源 各エリア → MW平均)
const buildDaily = (areas, fuels, startISO, endISO) => {
  if (!startISO || !endISO) return [];
  const s = dayIdxFromISO(startISO);
  const e = dayIdxFromISO(endISO);
  const N = e - s + 1;
  if (N <= 0 || N > 400) return [];
  return Array.from({ length: N }, (_, i) => {
    const dayIdx = s + i;
    const d = new Date(2026, 0, 1);
    d.setDate(d.getDate() + dayIdx);
    const row = { dayIdx, date: fmtISO(d), label: `${d.getMonth() + 1}/${d.getDate()}` };
    let total = 0;
    fuels.forEach(f => {
      let v = 0;
      areas.forEach(a => {
        v += (HJKS_AREA_CAPACITY[a]?.[f] || 0) * dailyUtil(f, dayIdx);
      });
      row[f] = v;
      total += v;
    });
    row.total = total;
    return row;
  });
};

const HjksDetail = ({ onBack }) => {
  const [selAreas, setSelAreas] = h4S(HJKS_AREAS.map(a => a.id));
  const [selFuels, setSelFuels] = h4S([...HJKS_FUELS]);
  const [range, setRange] = h4S(["2026-04-25", "2026-05-01"]);

  const daily = h4M(() => buildDaily(selAreas, selFuels, range[0], range[1]),
    [selAreas, selFuels, range]);

  const N = daily.length;
  const lastRow = daily[N - 1] || { total: 0 };
  const peakRow = N ? daily.reduce((m, x) => x.total > m.total ? x : m, daily[0]) : { total: 0, label: "" };
  const minRow  = N ? daily.reduce((m, x) => x.total < m.total ? x : m, daily[0]) : { total: 0, label: "" };
  const avgTotal = N ? daily.reduce((s, x) => s + x.total, 0) / N : 0;

  const totalCap = selAreas.reduce((s, a) =>
    s + selFuels.reduce((ss, f) => ss + (HJKS_AREA_CAPACITY[a]?.[f] || 0), 0), 0);

  const renewableAvg = ["太陽光", "風力", "水力"]
    .filter(f => selFuels.includes(f))
    .reduce((s, f) => s + (N ? daily.reduce((ss, x) => ss + (x[f] || 0), 0) / N : 0), 0);

  const toggleArea = (id) => setSelAreas(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);
  const toggleFuel = (id) => setSelFuels(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);

  return (
    <div style={{ padding: 28 }}>
      <DetailHeader
        title="HJKS 発電稼働状況"
        subtitle="広域機関 公表電源稼働情報 · エリア × 電源種別 (日次)"
        accent="var(--c-hjks)"
        icon="plant"
        onBack={onBack}
        badge={`${selAreas.length}/9エリア · ${selFuels.length}/7電源 · ${N}日`}
      />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16 }}>
        <KPI label="期間 平均出力" value={(avgTotal / 1000).toFixed(1)} unit="GW" color="var(--c-hjks)" sub={`容量比 ${totalCap > 0 ? (avgTotal / totalCap * 100).toFixed(0) : 0}%`}/>
        <KPI label="期間ピーク" value={(peakRow.total / 1000).toFixed(1)} unit="GW" color="#FF7A45" sub={peakRow.label || "-"}/>
        <KPI label="期間ボトム" value={(minRow.total / 1000).toFixed(1)} unit="GW" color="var(--c-info)" sub={minRow.label || "-"}/>
        <KPI label="再エネ比率" value={avgTotal > 0 ? (renewableAvg / avgTotal * 100).toFixed(1) : "0"} unit="%" color="#34C759" sub="水力+太陽光+風力"/>
      </div>

      {/* Filter */}
      <div style={{
        background: "var(--bg-surface)", borderRadius: 14, padding: 16,
        border: "1px solid var(--border-subtle)", marginBottom: 16,
        display: "flex", flexDirection: "column", gap: 12,
      }}>
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <span style={hjksChipLabel}>期間</span>
          <DateRangeInput value={range} onChange={setRange} accent="var(--c-hjks)"/>
          <div style={{ display: "flex", gap: 6, marginLeft: 4 }}>
            {[
              ["7日", () => { const s = new Date(2026, 4, 1); const e = new Date(s); e.setDate(e.getDate() + 6); setRange([fmtISO(s), fmtISO(e)]); }],
              ["30日", () => { const s = new Date(2026, 4, 1); const e = new Date(s); e.setDate(e.getDate() + 29); setRange([fmtISO(s), fmtISO(e)]); }],
              ["90日", () => { const s = new Date(2026, 4, 1); const e = new Date(s); e.setDate(e.getDate() + 89); setRange([fmtISO(s), fmtISO(e)]); }],
            ].map(([l, fn]) => (
              <button key={l} onClick={fn} style={hjksMiniBtn}>{l}</button>
            ))}
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={hjksChipLabel}>エリア</span>
          <button style={hjksMiniBtn} onClick={() => setSelAreas(HJKS_AREAS.map(a => a.id))}>全選択</button>
          <button style={hjksMiniBtn} onClick={() => setSelAreas([])}>解除</button>
          {HJKS_AREAS.map(a => {
            const on = selAreas.includes(a.id);
            return (
              <label key={a.id} style={hjksChipStyle(on, a.color)}>
                <input type="checkbox" checked={on} onChange={() => toggleArea(a.id)} style={hjksHideBox}/>
                <span style={hjksDotS(a.color, on)}/>{a.name}
              </label>
            );
          })}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={hjksChipLabel}>電源種別</span>
          <button style={hjksMiniBtn} onClick={() => setSelFuels([...HJKS_FUELS])}>全選択</button>
          <button style={hjksMiniBtn} onClick={() => setSelFuels([])}>解除</button>
          {HJKS_FUELS.map(f => {
            const on = selFuels.includes(f);
            return (
              <label key={f} style={hjksChipStyle(on, HJKS_FUEL_COLOR[f])}>
                <input type="checkbox" checked={on} onChange={() => toggleFuel(f)} style={hjksHideBox}/>
                <span style={hjksDotS(HJKS_FUEL_COLOR[f], on)}/>{f}
              </label>
            );
          })}
        </div>
      </div>

      <div style={{ marginBottom: 16 }}>
        <ChartFrame
          title="期間内 日次出力"
          subtitle={`${range[0] || "?"} 〜 ${range[1] || "?"} · 電源種別の累積 (各日 平均出力)`}
          accent="var(--c-hjks)"
          modalContent={<StackedBar rows={daily} fuels={selFuels} h={Math.max(540, window.innerHeight - 240)}/>}
        >
          <StackedBar rows={daily} fuels={selFuels} h={340}/>
        </ChartFrame>
      </div>

      {/* エリア + 電源構成 */}
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 16, marginBottom: 16 }}>
        <div style={hjksPanelStyle}>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 14 }}>エリア別 平均出力</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {HJKS_AREAS.map(a => {
              const inSel = selAreas.includes(a.id);
              const v = N === 0 ? 0 : selFuels.reduce((s, f) =>
                s + (HJKS_AREA_CAPACITY[a.id]?.[f] || 0) *
                  (daily.reduce((ss, row) => {
                    const dayIdx = row.dayIdx;
                    return ss + dailyUtil(f, dayIdx);
                  }, 0) / N), 0);
              const cap = selFuels.reduce((s, f) => s + (HJKS_AREA_CAPACITY[a.id]?.[f] || 0), 0);
              const pct = cap > 0 ? v / cap * 100 : 0;
              const max = Math.max(1, ...HJKS_AREAS.map(aa => {
                if (N === 0) return 0;
                return selFuels.reduce((s, f) =>
                  s + (HJKS_AREA_CAPACITY[aa.id]?.[f] || 0) *
                    (daily.reduce((ss, row) => ss + dailyUtil(f, row.dayIdx), 0) / N), 0);
              }));
              return (
                <div key={a.id} style={{ opacity: inSel ? 1 : 0.35 }}>
                  <div style={{ display: "flex", alignItems: "center", marginBottom: 4 }}>
                    <span style={{ width: 10, height: 10, borderRadius: 2, background: a.color, marginRight: 8 }}/>
                    <span style={{ fontSize: 12, fontWeight: 700, flex: 1 }}>{a.name}</span>
                    <span style={{ fontSize: 11, fontVariantNumeric: "tabular-nums", color: "var(--fg-secondary)" }}>
                      {(v / 1000).toFixed(2)} GW
                    </span>
                    <span style={{ marginLeft: 10, fontSize: 10, color: "var(--fg-tertiary)", fontWeight: 700, minWidth: 36, textAlign: "right" }}>
                      {pct.toFixed(0)}%
                    </span>
                  </div>
                  <div style={{ height: 8, background: "var(--bg-surface-2)", borderRadius: 4, overflow: "hidden" }}>
                    <div style={{
                      width: `${(v / max) * 100}%`,
                      height: "100%",
                      background: `linear-gradient(90deg, ${a.color}AA, ${a.color})`,
                      transition: "width 0.4s",
                    }}/>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div style={hjksPanelStyle}>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>期間 平均 電源構成</div>
          <div style={{ display: "flex", justifyContent: "center", padding: "4px 0" }}>
            <svg width="200" height="200" viewBox="0 0 220 220">
              <circle cx="110" cy="110" r="80" fill="none" stroke="var(--bg-surface-2)" strokeWidth="22"/>
              {(() => {
                let acc = 0; const C = 502;
                const totals = {};
                selFuels.forEach(f => {
                  totals[f] = N === 0 ? 0 : daily.reduce((s, x) => s + (x[f] || 0), 0) / N;
                });
                const sum = Object.values(totals).reduce((a, b) => a + b, 0) || 1;
                return selFuels.map((f, i) => {
                  const pct = totals[f] / sum;
                  if (!pct) return null;
                  const len = pct * C;
                  const off = -acc * C;
                  acc += pct;
                  return (
                    <circle key={i} cx="110" cy="110" r="80" fill="none"
                      stroke={HJKS_FUEL_COLOR[f]} strokeWidth="22"
                      strokeDasharray={`${len} ${C}`}
                      strokeDashoffset={off}
                      transform="rotate(-90 110 110)"
                      style={{ transition: "stroke-dasharray 0.6s" }}/>
                  );
                });
              })()}
              <text x="110" y="100" textAnchor="middle" fontSize="11" fill="var(--fg-tertiary)" fontWeight="700" letterSpacing="0.06em">平均</text>
              <text x="110" y="124" textAnchor="middle" fontSize="24" fill="var(--fg-primary)" fontWeight="800" style={{ letterSpacing: "-0.02em" }}>{(avgTotal / 1000).toFixed(1)}</text>
              <text x="110" y="142" textAnchor="middle" fontSize="10" fill="var(--fg-tertiary)" fontWeight="600">GW</text>
            </svg>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 5, marginTop: 8, fontSize: 11 }}>
            {selFuels.map((f, i) => {
              const v = N === 0 ? 0 : daily.reduce((s, x) => s + (x[f] || 0), 0) / N;
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: HJKS_FUEL_COLOR[f] }}/>
                  <span style={{ flex: 1, color: "var(--fg-secondary)" }}>{f}</span>
                  <span style={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                    {avgTotal > 0 ? (v / avgTotal * 100).toFixed(0) : 0}%
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* 停止中設備 */}
      <div style={hjksPanelStyle}>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 14 }}>停止中の主要設備</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          {[
            { plant: "柏崎刈羽 7号機", area: "東京",   source: "原子力",   status: "計画停止",     until: "2026/06/15" },
            { plant: "鹿島火力 6号機", area: "東京",   source: "石油火力", status: "トラブル停止", until: "復旧調整中"  },
            { plant: "扇島 1号機",     area: "東京",   source: "LNG火力",  status: "定期検査",     until: "2026/05/28" },
            { plant: "苫東厚真 4号機", area: "北海道", source: "石炭火力", status: "計画停止",     until: "2026/05/10" },
            { plant: "玄海 3号機",     area: "九州",   source: "原子力",   status: "定期検査",     until: "2026/07/02" },
            { plant: "舞鶴 2号機",     area: "関西",   source: "石炭火力", status: "計画停止",     until: "2026/05/20" },
          ].map((p, i) => {
            const c = HJKS_FUEL_COLOR[p.source] || "#999";
            return (
              <div key={i} style={{
                padding: "12px 14px", borderRadius: 12,
                background: "var(--bg-surface-2)",
                borderLeft: `3px solid ${c}`,
                display: "flex", alignItems: "center", gap: 12,
              }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 700 }}>{p.plant}</div>
                  <div style={{ fontSize: 11, color: "var(--fg-secondary)", marginTop: 2 }}>
                    {p.area} · {p.source} · {p.status}
                  </div>
                </div>
                <div style={{ fontSize: 11, color: "var(--fg-tertiary)", fontFamily: "var(--font-mono)" }}>~ {p.until}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

// =========================================================
// StackedBar — 日次の積み上げ
// =========================================================
const StackedBar = ({ rows, fuels, h = 340 }) => {
  const [hover, setHover] = h4S(null);
  const ref = React.useRef(null);
  const w = 880;
  const padL = 60, padR = 28, padT = 14, padB = 32;

  const N = rows.length;
  if (N === 0) {
    return <div style={{ height: h, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--fg-tertiary)", fontSize: 13 }}>期間を選択してください</div>;
  }

  const max = Math.max(1, ...rows.map(r => fuels.reduce((s, f) => s + (r[f] || 0), 0)));
  const yAt = v => padT + (1 - v / max) * (h - padT - padB);
  const bandW = (w - padL - padR) / N;
  const barW = Math.max(2, bandW * 0.72);
  const xCenter = i => padL + bandW * (i + 0.5);

  const handleMove = (e) => {
    const r = ref.current.getBoundingClientRect();
    const xp = ((e.clientX - r.left) / r.width) * w;
    if (xp < padL || xp > w - padR) { setHover(null); return; }
    const i = Math.floor((xp - padL) / bandW);
    if (i >= 0 && i < N) setHover(i);
  };

  const labelStep = N <= 14 ? 1 : N <= 35 ? 5 : N <= 60 ? 7 : Math.ceil(N / 14);

  return (
    <div style={{ position: "relative" }}>
      <svg ref={ref} width="100%" height={h} viewBox={`0 0 ${w} ${h}`}
        onMouseMove={handleMove} onMouseLeave={() => setHover(null)}
        style={{ display: "block", cursor: "crosshair" }}>
        {[0, 0.25, 0.5, 0.75, 1].map((p, i) => {
          const v = max * p;
          const y = padT + (1 - p) * (h - padT - padB);
          return (
            <g key={i}>
              <line x1={padL} x2={w - padR} y1={y} y2={y} stroke="var(--border-subtle)"/>
              <text x={padL - 8} y={y + 4} textAnchor="end" fontSize="10" fill="var(--fg-tertiary)">
                {(v / 1000).toFixed(1)} GW
              </text>
            </g>
          );
        })}

        {rows.map((r, i) => {
          let acc = 0;
          return (
            <g key={i}>
              {fuels.map((f, fi) => {
                const v = r[f] || 0;
                if (v === 0) return null;
                const yTop = yAt(acc + v);
                const height = yAt(acc) - yTop;
                acc += v;
                return (
                  <rect key={fi}
                    x={xCenter(i) - barW / 2} y={yTop}
                    width={barW} height={Math.max(0.6, height)}
                    fill={HJKS_FUEL_COLOR[f]}
                    opacity={hover != null && hover !== i ? 0.55 : 1}/>
                );
              })}
              {(i % labelStep === 0 || i === N - 1) && (
                <text x={xCenter(i)} y={h - 10} textAnchor="middle" fontSize="10"
                  fill={hover === i ? "var(--c-hjks)" : "var(--fg-tertiary)"}
                  fontWeight={hover === i ? 700 : 400}>
                  {r.label}
                </text>
              )}
            </g>
          );
        })}

        {hover != null && (
          <rect x={xCenter(hover) - barW / 2 - 2} y={padT - 2}
            width={barW + 4} height={h - padT - padB + 4}
            fill="none" stroke="var(--fg-secondary)" strokeWidth="1.2" strokeDasharray="3 3"/>
        )}
      </svg>

      <div style={{ display: "flex", gap: 10, justifyContent: "center", marginTop: 4, flexWrap: "wrap", fontSize: 10 }}>
        {fuels.map(f => (
          <span key={f} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: HJKS_FUEL_COLOR[f] }}/>
            <span style={{ color: "var(--fg-secondary)", fontWeight: 600 }}>{f}</span>
          </span>
        ))}
      </div>

      {hover != null && (() => {
        const r = rows[hover];
        const xPct = (xCenter(hover) / w) * 100;
        const onLeft = xPct > 60;
        const total = fuels.reduce((s, f) => s + (r[f] || 0), 0);
        return (
          <div style={{
            position: "absolute", top: 24,
            left: onLeft ? "auto" : `calc(${xPct}% + 18px)`,
            right: onLeft ? `calc(${100 - xPct}% + 18px)` : "auto",
            background: "var(--bg-surface)", border: "1px solid var(--border-subtle)",
            borderRadius: 10, padding: "10px 14px", boxShadow: "var(--shadow-md)",
            fontSize: 11, fontVariantNumeric: "tabular-nums",
            pointerEvents: "none", minWidth: 180, zIndex: 5,
          }}>
            <div style={{ fontSize: 12, fontWeight: 800, marginBottom: 6 }}>{r.date} ({r.label})</div>
            {fuels.map(f => {
              const v = r[f] || 0;
              if (!v) return null;
              return (
                <div key={f} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: HJKS_FUEL_COLOR[f] }}/>
                  <span style={{ color: "var(--fg-secondary)", flex: 1 }}>{f}</span>
                  <span style={{ fontWeight: 700 }}>{(v / 1000).toFixed(2)} GW</span>
                </div>
              );
            })}
            <div style={{ borderTop: "1px solid var(--border-subtle)", marginTop: 6, paddingTop: 6, display: "flex" }}>
              <span style={{ color: "var(--fg-secondary)", fontWeight: 700, flex: 1 }}>合計</span>
              <span style={{ fontWeight: 800, color: "var(--c-hjks)" }}>{(total / 1000).toFixed(2)} GW</span>
            </div>
          </div>
        );
      })()}
    </div>
  );
};

const hjksChipLabel = { fontSize: 11, fontWeight: 700, color: "var(--fg-tertiary)", letterSpacing: "0.04em" };
const hjksMiniBtn = {
  fontFamily: "inherit", fontSize: 10, fontWeight: 700,
  padding: "4px 9px", borderRadius: 7, cursor: "pointer",
  border: "1px solid var(--border)", background: "var(--bg-surface-2)", color: "var(--fg-secondary)",
};
const hjksChipStyle = (on, c) => ({
  display: "inline-flex", alignItems: "center", gap: 6,
  padding: "5px 10px", borderRadius: 999,
  border: `1px solid ${on ? c : "var(--border)"}`,
  background: on ? `color-mix(in srgb, ${c} 14%, transparent)` : "var(--bg-surface-2)",
  color: on ? c : "var(--fg-tertiary)",
  fontSize: 11, fontWeight: 700, cursor: "pointer",
  userSelect: "none", transition: "all 0.15s",
});
const hjksDotS = (c, on) => ({
  width: 8, height: 8, borderRadius: 2,
  background: on ? c : "transparent",
  border: `1.5px solid ${c}`,
});
const hjksHideBox = { position: "absolute", opacity: 0, pointerEvents: "none", width: 0, height: 0 };
const hjksPanelStyle = {
  background: "var(--bg-surface)", borderRadius: 18, padding: 22,
  border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
};

window.varA_detail_screens4 = { HjksDetail };
