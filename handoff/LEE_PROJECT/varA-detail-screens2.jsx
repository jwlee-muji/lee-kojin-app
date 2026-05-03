/* global React, Ic */
// ============================================================
// Variation A — Detail screens part 2 (Reserve, Energy Indicators)
// 表は上、グラフは下。
// ============================================================

const { useState: rjS, useMemo: rjM } = React;
const { BigChart, KPI, DetailHeader, ChartFrame } = window.varA_detail_atoms;
const { Pill } = window.varA_atoms;
const { PivotTable, AREAS, AREA_COLORS, buildAreaMatrix } = window.varA_pivot;
const { DateInput: DI_S2 } = window.varA_datepicker;
const RJ = window.LEE_DATA;

// =========================================================
// 1) RESERVE (予備率) DETAIL — 表 上 + グラフ 下
// =========================================================
const ReserveDetail = ({ onBack }) => {
  const [date, setDate] = rjS("2026-05-01");
  const matrix = rjM(() => buildAreaMatrix("reserve", 17), [date]);

  // 各エリアの最小予備率
  const stats = AREAS.map(a => {
    const arr = matrix[a] || [];
    const minV = Math.min(...arr);
    const avg = arr.reduce((s, v) => s + v, 0) / arr.length;
    const status = minV < 3 ? "bad" : minV < 8 ? "warn" : "ok";
    return { area: a, min: minV, avg, status };
  });
  const worst = stats.reduce((a, b) => a.min < b.min ? a : b);

  return (
    <div style={{ padding: 28 }}>
      <DetailHeader
        title="電力予備率"
        subtitle="OCCTO 全国 10エリア · 30分単位"
        accent="var(--c-power)"
        icon="power"
        onBack={onBack}
        badge={`${worst.area} ${worst.min.toFixed(1)}% 警戒`}
      />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
        <KPI label="最低予備率" value={worst.min.toFixed(1)} unit="%" color="var(--c-bad)" sub={`${worst.area}エリア (警戒水準)`}/>
        <KPI label="全国平均" value={(stats.reduce((s,x) => s + x.avg, 0) / stats.length).toFixed(1)} unit="%" color="var(--c-power)" sub="安定圏内"/>
        <KPI label="最大供給力" value="174.8" unit="GW" sub="火力 + 原子力 + 再エネ"/>
        <KPI label="想定需要ピーク" value="163.9" unit="GW" sub="18:30 想定"/>
      </div>

      <div style={{
        display: "flex", alignItems: "center", gap: 8, marginBottom: 14,
        flexWrap: "wrap",
      }}>
        <DI_S2 value={date} onChange={setDate} accent="var(--c-power)" />
        <div style={{ width: 1, height: 22, background: "var(--border-subtle)" }}/>
        <Pill color="var(--c-bad)">⚠ 危険 〜3%</Pill>
        <Pill color="var(--c-warn)">注意 3〜8%</Pill>
        <Pill color="var(--c-power)">通常 8〜15%</Pill>
        <Pill color="var(--c-ok)">安定 15%+</Pill>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button style={btnStyle}>📋 コピー</button>
          <button style={btnStyle}>⬇ CSV</button>
        </div>
      </div>

      {/* === 表 (上) — 統計行なし === */}
      <div style={{ marginBottom: 20 }}>
        <PivotTable matrix={matrix} mode="reserve" height={400} accent="var(--c-power)" statsPosition="none"/>
      </div>

      {/* === グラフ (下) === */}
      <div style={{
        display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 16, marginBottom: 20,
      }}>
        <ChartFrame
          title="10エリア 予備率比較 (現在値)"
          subtitle={`${date}`}
          accent="var(--c-power)"
          modalContent={<ReserveBars stats={stats} large/>}
        >
          <ReserveBars stats={stats}/>
        </ChartFrame>

        <ChartFrame
          title="需給バランス予測"
          subtitle="東京エリア"
          accent="var(--c-power)"
          modalContent={<ReserveTokyoChart data={matrix["東京"]} h={Math.max(540, window.innerHeight - 280)}/>}
        >
          <ReserveTokyoChart data={matrix["東京"]}/>
          <div style={{ display: "flex", justifyContent: "space-around", marginTop: 12, fontSize: 11, color: "var(--fg-tertiary)" }}>
            <div>00:00</div><div>06:00</div><div>12:00</div><div>18:00</div><div>23:30</div>
          </div>
        </ChartFrame>
      </div>
    </div>
  );
};

// Reserve bars helper
const ReserveBars = ({ stats, large = false }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: large ? 14 : 11 }}>
    {stats.map((s, i) => {
      const c = s.status === "bad" ? "var(--c-bad)" : s.status === "warn" ? "var(--c-warn)" : "var(--c-power)";
      return (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: large ? 80 : 56, fontSize: large ? 14 : 12, fontWeight: 600 }}>{s.area}</div>
          <div style={{ flex: 1, height: large ? 22 : 14, background: "var(--bg-surface-2)", borderRadius: 999, overflow: "hidden", position: "relative" }}>
            <div style={{
              width: `${Math.min(100, (s.avg / 25) * 100)}%`, height: "100%", background: c, borderRadius: 999,
              transition: "width 0.6s ease-out",
            }}/>
            <div style={{ position: "absolute", top: -2, height: large ? 26 : 18, left: `${(8 / 25) * 100}%`, width: 2, background: "var(--c-warn)", opacity: 0.6 }}/>
            <div style={{ position: "absolute", top: -2, height: large ? 26 : 18, left: `${(3 / 25) * 100}%`, width: 2, background: "var(--c-bad)", opacity: 0.6 }}/>
          </div>
          <div style={{ width: 80, fontSize: large ? 14 : 12, fontVariantNumeric: "tabular-nums", fontWeight: 700, textAlign: "right" }}>
            {s.avg.toFixed(1)} <span style={{ fontSize: 10, color: "var(--fg-tertiary)", fontWeight: 500 }}>%</span>
          </div>
        </div>
      );
    })}
  </div>
);

const ReserveTokyoChart = ({ data, h = 200 }) => (
  <div style={{ height: h, position: "relative" }}>
    <BigChart data={data || []} color="var(--c-power)" w={520} h={h} label="rs" yUnit="%"/>
  </div>
);

// =========================================================
// 2) ENERGY INDICATORS (旧 JKM) — LNG / 原油 / 石炭 / 為替
// =========================================================
const INDICATORS = [
  { id: "jkm",    label: "JKM (LNG)",  unit: "USD/MMBtu", base: 14.20, color: "var(--c-jkm)" },
  { id: "henry",  label: "Henry Hub",  unit: "USD/MMBtu", base:  3.45, color: "#34A853" },
  { id: "brent",  label: "Brent 原油", unit: "USD/bbl",   base: 84.50, color: "#1A73E8" },
  { id: "wti",    label: "WTI 原油",   unit: "USD/bbl",   base: 81.20, color: "#0B8043" },
  { id: "coal",   label: "豪州炭",      unit: "USD/t",     base: 142.30, color: "#5F6368" },
  { id: "usdjpy", label: "USD/JPY",    unit: "JPY",       base: 156.40, color: "#EA4335" },
  { id: "eurjpy", label: "EUR/JPY",    unit: "JPY",       base: 168.90, color: "#7986CB" },
  { id: "ttf",    label: "TTF (欧州ガス)", unit: "EUR/MWh", base: 35.20, color: "#FF6D00" },
];

const PERIODS = [
  ["1m", "1ヶ月"], ["3m", "3ヶ月"], ["6m", "6ヶ月"],
  ["1y", "1年"], ["3y", "3年"], ["all", "全期間"],
];

// 期間 → ポイント数
const periodPoints = (p) => ({ "1m": 30, "3m": 90, "6m": 180, "1y": 250, "3y": 750, "all": 1500 }[p] || 90);

// 価格系列生成
const buildSeries = (id, n, baseSeed) => {
  let s = baseSeed;
  const rng = () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
  const ind = INDICATORS.find(x => x.id === id);
  const out = [];
  let v = ind.base;
  for (let i = 0; i < n; i++) {
    v += (rng() - 0.5) * (ind.base * 0.025);
    v = Math.max(ind.base * 0.5, Math.min(ind.base * 1.6, v));
    out.push(v);
  }
  return out;
};

const EnergyIndicatorsDetail = ({ onBack }) => {
  const [active, setActive] = rjS("jkm");
  const [period, setPeriod] = rjS("3m");
  const ind = INDICATORS.find(x => x.id === active);
  const series = rjM(() => buildSeries(active, periodPoints(period), 41), [active, period]);

  const cur = series[series.length - 1];
  const first = series[0];
  const change = cur - first;
  const changePct = (change / first) * 100;
  const high = Math.max(...series);
  const low = Math.min(...series);
  const avg = series.reduce((a, b) => a + b, 0) / series.length;

  return (
    <div style={{ padding: 28 }}>
      <DetailHeader
        title="エネルギー指標"
        subtitle="LNG · 原油 · 石炭 · 為替 · 欧州ガス"
        accent={ind.color}
        icon="jkm"
        onBack={onBack}
        badge={`${ind.label} ${cur.toFixed(2)}`}
      />

      {/* 指標タイル選択 */}
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10,
        marginBottom: 18,
      }}>
        {INDICATORS.map(x => {
          const sample = buildSeries(x.id, 30, 41);
          const last = sample[sample.length - 1];
          const fst = sample[0];
          const ch = ((last - fst) / fst) * 100;
          const on = active === x.id;
          return (
            <button key={x.id} onClick={() => setActive(x.id)} style={{
              textAlign: "left", border: "1px solid",
              borderColor: on ? x.color : "var(--border-subtle)",
              background: on
                ? `color-mix(in srgb, ${x.color} 10%, var(--bg-surface))`
                : "var(--bg-surface)",
              borderRadius: 14, padding: "12px 14px", cursor: "pointer",
              fontFamily: "inherit", transition: "all 0.18s",
              boxShadow: on ? "var(--shadow-md)" : "var(--shadow-sm)",
              transform: on ? "translateY(-1px)" : "none",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--fg-secondary)" }}>{x.label}</div>
                <div style={{
                  fontSize: 10, fontWeight: 700,
                  color: ch >= 0 ? "var(--c-bad)" : "var(--c-ok)",
                }}>{ch >= 0 ? "▲" : "▼"} {Math.abs(ch).toFixed(1)}%</div>
              </div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 4, marginTop: 6 }}>
                <div style={{ fontSize: 18, fontWeight: 800, color: "var(--fg-primary)", fontVariantNumeric: "tabular-nums" }}>{last.toFixed(2)}</div>
                <div style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>{x.unit}</div>
              </div>
              {/* sparkline */}
              <Sparkline data={sample} color={x.color} w={180} h={28}/>
            </button>
          );
        })}
      </div>

      {/* 期間 + アクション */}
      <div style={{
        display: "flex", alignItems: "center", gap: 12, marginBottom: 16,
      }}>
        <div style={{
          display: "inline-flex", background: "var(--bg-surface-2)",
          borderRadius: 12, padding: 3, gap: 2,
        }}>
          {PERIODS.map(([k, l]) => (
            <button key={k} onClick={() => setPeriod(k)} style={{
              border: "none", padding: "8px 14px", borderRadius: 9,
              background: period === k ? ind.color : "transparent",
              color: period === k ? "#fff" : "var(--fg-secondary)",
              fontFamily: "inherit", fontSize: 12, fontWeight: 600,
              cursor: "pointer", transition: "all 0.18s",
            }}>{l}</button>
          ))}
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button style={btnStyle}>📋 コピー</button>
          <button style={btnStyle}>⬇ CSV</button>
        </div>
      </div>

      {/* KPI */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
        <KPI label="現在値" value={cur.toFixed(2)} unit={ind.unit} color={ind.color} delta={changePct} sub={ind.label}/>
        <KPI label="期間最高" value={high.toFixed(2)} unit={ind.unit} color="var(--c-bad)" sub="High"/>
        <KPI label="期間最安" value={low.toFixed(2)} unit={ind.unit} color="var(--c-ok)" sub="Low"/>
        <KPI label="期間平均" value={avg.toFixed(2)} unit={ind.unit} sub={`${PERIODS.find(([k]) => k === period)?.[1] || ""} avg`}/>
      </div>

      {/* === 表 (上) === */}
      <div style={{ marginBottom: 20 }}>
        <IndicatorTable indicator={ind} series={series} period={period}/>
      </div>

      {/* === グラフ (下) === */}
      <div style={{ marginBottom: 20 }}>
        <ChartFrame
          title={`${ind.label} 推移`}
          subtitle={`${PERIODS.find(([k]) => k === period)?.[1]} · ${series.length} ポイント`}
          accent={ind.color}
          modalContent={<BigChart data={series} color={ind.color} w={1400} h={Math.max(560, window.innerHeight - 240)} label={active} yUnit={ind.unit}/>}
        >
          <BigChart data={series} color={ind.color} w={880} h={300} label={active} yUnit={ind.unit}/>
        </ChartFrame>
      </div>
    </div>
  );
};

// 指標表 — 日付 × 価格 (新しい順)
const IndicatorTable = ({ indicator, series, period }) => {
  const today = new Date(2026, 4, 1);
  const rows = [...series].reverse().slice(0, 60).map((v, i) => {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const prev = i + 1 < series.length ? series[series.length - 1 - i - 1] : v;
    const ch = v - prev;
    const chPct = (ch / prev) * 100;
    return {
      date: `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`,
      v, ch, chPct,
    };
  });

  return (
    <div style={{
      background: "var(--bg-surface)", borderRadius: 18,
      border: "1px solid var(--border-subtle)",
      boxShadow: "var(--shadow-sm)", overflow: "hidden",
    }}>
      <div style={{
        display: "flex", alignItems: "center", padding: "14px 18px",
        borderBottom: "1px solid var(--border-subtle)",
      }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>{indicator.label} 履歴データ</div>
        <div style={{ marginLeft: "auto", fontSize: 11, color: "var(--fg-tertiary)" }}>直近 {rows.length} 日 (新しい順)</div>
      </div>
      <div style={{ maxHeight: 360, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0, fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
          <thead style={{ position: "sticky", top: 0, background: "var(--bg-surface-2)", zIndex: 2 }}>
            <tr>
              <th style={th()}>日付</th>
              <th style={th()}>{indicator.label} ({indicator.unit})</th>
              <th style={th()}>前日比</th>
              <th style={th()}>変化率</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const up = r.ch >= 0;
              return (
                <tr key={i} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  <td style={td()}>{r.date}</td>
                  <td style={{ ...td(), fontWeight: 700, color: indicator.color }}>{r.v.toFixed(2)}</td>
                  <td style={{ ...td(), color: up ? "var(--c-bad)" : "var(--c-ok)", fontWeight: 600 }}>
                    {up ? "+" : ""}{r.ch.toFixed(2)}
                  </td>
                  <td style={{ ...td(), color: up ? "var(--c-bad)" : "var(--c-ok)", fontWeight: 600 }}>
                    {up ? "▲" : "▼"} {Math.abs(r.chPct).toFixed(2)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const Sparkline = ({ data, color, w = 180, h = 28 }) => {
  const max = Math.max(...data), min = Math.min(...data);
  const r = max - min || 1;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / r) * h}`).join(" ");
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} style={{ marginTop: 8 }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5"/>
    </svg>
  );
};

const th = () => ({
  textAlign: "left", padding: "10px 16px", fontSize: 11, fontWeight: 700,
  color: "var(--fg-secondary)", borderBottom: "1px solid var(--border-subtle)",
});
const td = () => ({ padding: "9px 16px", color: "var(--fg-primary)" });

const btnStyle = {
  padding: "8px 14px", borderRadius: 10,
  border: "1px solid var(--border)",
  background: "var(--bg-surface)", color: "var(--fg-secondary)",
  fontFamily: "inherit", fontSize: 12, fontWeight: 600, cursor: "pointer",
};

window.varA_detail_screens2 = { ReserveDetail, EnergyIndicatorsDetail, JKMDetail: EnergyIndicatorsDetail };
