/* global React */
// ============================================================
// Variation A — Shared pivot table (30min × area)
// 単価別カラーグラデーション付き
// ============================================================

const { useMemo: pvM, useState: pvS } = React;

// ── 10エリア + 各種カラーパレット ───────────────────────────────
const AREAS = ["北海道", "東北", "東京", "中部", "北陸", "関西", "中国", "四国", "九州", "沖縄"];

const AREA_COLORS = {
  "北海道": "#4285F4", "東北": "#EA4335", "東京": "#FBBC05", "中部": "#34A853",
  "北陸": "#FF6D00", "関西": "#7986CB", "中国": "#E67C73", "四国": "#0B8043",
  "九州": "#8E24AA", "沖縄": "#D50000",
};

// 30分 × 48コマのタイムスロット文字列
const buildTimeSlots = () => {
  const slots = [];
  for (let h = 0; h < 24; h++) {
    for (let m of [0, 30]) {
      const hh = String(h).padStart(2, "0");
      const mm = String(m).padStart(2, "0");
      slots.push(`${hh}:${mm}`);
    }
  }
  return slots;
};
const TIME_SLOTS_48 = buildTimeSlots();

// ── 単価による色決定 (青→緑→黄→橙→赤) ─────────────────────────
// JEPXスポットの一般的なレンジ: 0〜50円/kWh
const priceColor = (v, mode = "spot") => {
  if (v == null || isNaN(v)) return null;
  if (mode === "spot") {
    if (v < 5)   return { bg: "rgba(52,168,83,0.18)",  fg: "#0b8043" };
    if (v < 10)  return { bg: "rgba(251,188,5,0.16)",  fg: "#a87100" };
    if (v < 15)  return { bg: "rgba(255,109,0,0.18)",  fg: "#bf4f00" };
    if (v < 25)  return { bg: "rgba(234,67,53,0.18)",  fg: "#c5221f" };
    return         { bg: "rgba(213,0,0,0.25)",         fg: "#9b0000" };
  }
  if (mode === "imb") {
    if (v < 0)   return { bg: "rgba(52,168,83,0.16)",  fg: "#0b8043" };
    if (v < 8)   return { bg: "rgba(251,188,5,0.14)",  fg: "#a87100" };
    if (v < 16)  return { bg: "rgba(255,109,0,0.18)",  fg: "#bf4f00" };
    return         { bg: "rgba(234,67,53,0.22)",       fg: "#c5221f" };
  }
  if (mode === "reserve") {
    // 予備率 % — 低いほど危険 (赤)、高いほど安全 (緑)
    if (v < 3)   return { bg: "rgba(213,0,0,0.25)",    fg: "#9b0000" };
    if (v < 8)   return { bg: "rgba(234,67,53,0.18)",  fg: "#c5221f" };
    if (v < 15)  return { bg: "rgba(255,109,0,0.18)",  fg: "#bf4f00" };
    if (v < 25)  return { bg: "rgba(251,188,5,0.14)",  fg: "#a87100" };
    return         { bg: "rgba(52,168,83,0.18)",       fg: "#0b8043" };
  }
  return null;
};

// ── 48コマ × エリア の擬似データ生成 (再現性ある乱数) ─────────────
const seededRand = (seed) => {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
};

const buildAreaMatrix = (mode = "spot", baseSeed = 7) => {
  const rng = seededRand(baseSeed);
  const matrix = {};
  AREAS.forEach((area, ai) => {
    matrix[area] = TIME_SLOTS_48.map((_, i) => {
      // 朝夕ピーク, 深夜安値の擬似カーブ
      const hour = i / 2;
      let base = 8 + 4 * Math.sin((hour - 6) / 24 * Math.PI * 2);
      const morningPeak = Math.exp(-Math.pow((hour - 8.5) / 1.5, 2)) * 6;
      const eveningPeak = Math.exp(-Math.pow((hour - 18.5) / 1.8, 2)) * 8;
      const nightLow = -Math.exp(-Math.pow((hour - 3.5) / 2.5, 2)) * 3;
      base += morningPeak + eveningPeak + nightLow;
      base += (rng() - 0.5) * 2.5;
      base += (ai - 4) * 0.2; // エリアごとに少しずらす
      if (mode === "imb") base = base - 6 + (rng() - 0.5) * 4;
      if (mode === "reserve") base = 8 + (rng() - 0.5) * 18;
      return Math.max(mode === "reserve" ? 0 : 0.5, base);
    });
  });
  return matrix;
};

// ── 汎用 行データ生成 (mode別) ────────────────────────────────
// rowCount 行 × 10 エリア の擬似データを生成
// pattern: "intraday" (時間帯依存) | "trend" (緩やかな波) | "yearly" (年次低変動)
const buildSpotRows = (rowCount, baseSeed = 7, pattern = "intraday") => {
  const rng = seededRand(baseSeed);
  const matrix = {};
  AREAS.forEach((area, ai) => {
    matrix[area] = [];
    for (let i = 0; i < rowCount; i++) {
      let v;
      if (pattern === "intraday") {
        // 30分単位の朝夕ピーク (0..47 想定)
        const hour = (i / rowCount) * 24;
        let base = 8 + 4 * Math.sin((hour - 6) / 24 * Math.PI * 2);
        base += Math.exp(-Math.pow((hour - 8.5) / 1.5, 2)) * 6;
        base += Math.exp(-Math.pow((hour - 18.5) / 1.8, 2)) * 8;
        base -= Math.exp(-Math.pow((hour - 3.5) / 2.5, 2)) * 3;
        base += (rng() - 0.5) * 2.5 + (ai - 4) * 0.2;
        v = Math.max(0.5, base);
      } else if (pattern === "trend") {
        // 季節性 + ノイズ
        const phase = (i / Math.max(1, rowCount - 1)) * Math.PI * 2;
        let base = 11 + 3.5 * Math.sin(phase + ai * 0.3) + 2 * Math.cos(phase * 2);
        base += (rng() - 0.5) * 3;
        v = Math.max(0.5, base);
      } else {
        // yearly: 緩やかな上昇トレンド
        let base = 8 + i * 0.6 + (ai - 4) * 0.4 + (rng() - 0.5) * 1.8;
        v = Math.max(2, base);
      }
      matrix[area].push(v);
    }
  });
  return matrix;
};

// ── PivotTable コンポーネント ─────────────────────────────────
// columns: AREAS, rows: 48 time slots
// statsPosition: "top" | "bottom" | "none"
const PivotTable = ({ matrix, mode = "spot", height = 360, accent = "var(--c-spot)", statsPosition = "bottom", rowLabels = null, rowHeaderLabel = "時刻" }) => {
  const [hoverCol, setHoverCol] = pvS(null);
  const [hoverRow, setHoverRow] = pvS(null);

  const slots = rowLabels || TIME_SLOTS_48;
  // 統計行
  const stats = pvM(() => {
    return Object.keys(matrix).map(area => {
      const arr = matrix[area] || [];
      const avg = arr.reduce((a, b) => a + b, 0) / arr.length;
      const max = Math.max(...arr);
      const min = Math.min(...arr);
      return { area, avg, max, min };
    });
  }, [matrix]);

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
        <div style={{ fontSize: 14, fontWeight: 700, color: "var(--fg-primary)" }}>
          30分単位 × エリア別 一覧
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 12, alignItems: "center" }}>
          <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>単価別カラー</div>
          <div style={{ display: "flex", gap: 3 }}>
            {[2, 7, 12, 20, 30].map(v => {
              const c = priceColor(v, mode);
              return <div key={v} title={`${v}〜`} style={{
                width: 22, height: 14, borderRadius: 3,
                background: c?.bg, border: `1px solid ${c?.fg}33`,
              }}/>;
            })}
          </div>
          <button style={{
            padding: "6px 12px", borderRadius: 10,
            border: "1px solid var(--border)",
            background: "var(--bg-surface-2)",
            fontSize: 11, color: "var(--fg-secondary)", cursor: "pointer",
            fontFamily: "inherit", fontWeight: 600,
          }} title="表をコピー">コピー</button>
        </div>
      </div>

      <div style={{ maxHeight: height, overflow: "auto" }}>
        <table style={{
          width: "100%", borderCollapse: "separate", borderSpacing: 0,
          fontSize: 11, fontVariantNumeric: "tabular-nums",
        }}>
          <thead style={{ position: "sticky", top: 0, zIndex: 2 }}>
            <tr>
              <th style={hCellStyle(true)}>{rowHeaderLabel}</th>
              {Object.keys(matrix).map((a, i) => (
                <th key={a} style={{
                  ...hCellStyle(false),
                  background: hoverCol === i ? "var(--bg-surface-3)" : "var(--bg-surface-2)",
                  borderBottom: `2px solid ${AREA_COLORS[a] || accent}`,
                }}>{a}</th>
              ))}
            </tr>
          </thead>
          {statsPosition === "top" && (
            <thead style={{ position: "sticky", top: 36, zIndex: 2 }}>
              {[["平均", "avg"], ["最高", "max"], ["最低", "min"]].map(([label, k]) => (
                <tr key={k}>
                  <td style={{ ...cellStyle(true), background: "var(--bg-surface-2)", fontWeight: 700 }}>{label}</td>
                  {stats.map(s => (
                    <td key={s.area} style={{
                      ...cellStyle(false), background: "var(--bg-surface-2)",
                      fontWeight: 700, color: "var(--fg-primary)",
                    }}>{s[k].toFixed(2)}</td>
                  ))}
                </tr>
              ))}
            </thead>
          )}
          <tbody>
            {slots.map((t, ri) => (
              <tr key={t}
                  onMouseEnter={() => setHoverRow(ri)}
                  onMouseLeave={() => setHoverRow(null)}>
                <td style={{
                  ...cellStyle(true),
                  background: hoverRow === ri ? "var(--bg-surface-3)" : "var(--bg-surface)",
                  fontWeight: ri % 4 === 0 ? 700 : 500,
                }}>{t}</td>
                {Object.keys(matrix).map((a, ci) => {
                  const v = matrix[a]?.[ri];
                  const c = priceColor(v, mode);
                  const isHover = hoverRow === ri || hoverCol === ci;
                  return (
                    <td key={a}
                        onMouseEnter={() => setHoverCol(ci)}
                        onMouseLeave={() => setHoverCol(null)}
                        style={{
                          ...cellStyle(false),
                          background: c?.bg || (isHover ? "var(--bg-surface-2)" : "transparent"),
                          color: c?.fg || "var(--fg-primary)",
                          fontWeight: 600,
                          outline: isHover ? `1px solid ${accent}55` : "none",
                          outlineOffset: -1,
                        }}>
                      {v != null ? v.toFixed(2) : "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
          {statsPosition === "bottom" && (
            <tfoot style={{ position: "sticky", bottom: 0 }}>
              {[
                ["平均", "avg"], ["最高", "max"], ["最安", "min"],
              ].map(([label, k]) => (
                <tr key={k}>
                  <td style={{ ...cellStyle(true), background: "var(--bg-surface-2)", fontWeight: 700 }}>{label}</td>
                  {stats.map(s => (
                    <td key={s.area} style={{
                      ...cellStyle(false), background: "var(--bg-surface-2)",
                      fontWeight: 700, color: "var(--fg-primary)",
                    }}>{s[k].toFixed(2)}</td>
                  ))}
                </tr>
              ))}
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
};

const hCellStyle = (sticky) => ({
  padding: "10px 8px", textAlign: sticky ? "left" : "center",
  fontWeight: 700, fontSize: 11, letterSpacing: 0.3,
  color: "var(--fg-secondary)", background: "var(--bg-surface-2)",
  borderBottom: "1px solid var(--border-subtle)",
  position: sticky ? "sticky" : "static",
  left: sticky ? 0 : "auto", zIndex: sticky ? 3 : 1,
  minWidth: sticky ? 60 : 64,
});

const cellStyle = (sticky) => ({
  padding: "5px 8px", textAlign: sticky ? "left" : "center",
  borderBottom: "1px solid var(--border-subtle)",
  position: sticky ? "sticky" : "static",
  left: sticky ? 0 : "auto", zIndex: sticky ? 1 : 0,
  whiteSpace: "nowrap",
});

window.varA_pivot = { PivotTable, AREAS, AREA_COLORS, buildAreaMatrix, buildSpotRows, TIME_SLOTS_48, priceColor };
