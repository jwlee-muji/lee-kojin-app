/* global React, Ic */
// ============================================================
// Variation A — Detail screens (Spot, Imbalance)
// 表は上、グラフは下。各種モード切替対応
// ============================================================

const { useState: scS, useMemo: scM } = React;
const { BigChart, KPI, DetailHeader, ChartFrame } = window.varA_detail_atoms;
const { Pill } = window.varA_atoms;
const { PivotTable, AREAS, AREA_COLORS, buildAreaMatrix, buildSpotRows } = window.varA_pivot;
const { DateInput: DI_S1 } = window.varA_datepicker;
const SD = window.LEE_DATA;

// =========================================================
// 共通: モード切替セグメント
// =========================================================
const SegTabs = ({ value, onChange, options, accent = "var(--c-spot)" }) => (
  <div style={{
    display: "inline-flex", background: "var(--bg-surface-2)",
    borderRadius: 12, padding: 3, gap: 2,
  }}>
    {options.map(([k, l]) => (
      <button key={k} onClick={() => onChange(k)} style={{
        border: "none", padding: "8px 14px", borderRadius: 9,
        background: value === k ? accent : "transparent",
        color: value === k ? "#fff" : "var(--fg-secondary)",
        fontFamily: "inherit", fontSize: 12, fontWeight: 600,
        cursor: "pointer", transition: "all 0.18s",
      }}>{l}</button>
    ))}
  </div>
);

// =========================================================
// 1) SPOT DETAIL — 5モード × 10エリア
// =========================================================
const SPOT_MODES = [
  ["today",        "当日"],
  ["daily_avg",    "日次平均"],
  ["monthly_avg",  "月次平均"],
  ["yearly_avg",   "年次平均"],
  ["weekday_avg",  "曜日別"],
];
const WEEKDAYS = [
  ["1", "月"], ["2", "火"], ["3", "水"], ["4", "木"],
  ["5", "金"], ["6", "土"], ["0", "日"],
];
// FY 옵션 (로컬: JEPX_SPOT_START_FY=2005 ~ current)
const _today = new Date();
const _curFY = _today.getMonth() + 1 >= 4 ? _today.getFullYear() : _today.getFullYear() - 1;
const FY_OPTIONS = [];
for (let y = 2005; y <= _curFY; y++) FY_OPTIONS.push(y);

// 日付列挙 (ISO YYYY-MM-DD, 包含)
const enumerateDates = (s, e) => {
  const out = [];
  const d0 = new Date(s); const d1 = new Date(e);
  if (d0 > d1) return out;
  // 너무 많으면 잘라냄 (UI 성능)
  const cap = 400;
  let cur = new Date(d0);
  while (cur <= d1 && out.length < cap) {
    out.push(cur.toISOString().slice(0, 10));
    cur.setDate(cur.getDate() + 1);
  }
  return out;
};

// 会計年度 (4月始まり) 月列挙: FY {fyStart} ~ FY {fyEnd}
const enumerateMonthsFY = (fyStart, fyEnd) => {
  const a = Math.min(fyStart, fyEnd), b = Math.max(fyStart, fyEnd);
  const out = [];
  for (let y = a; y <= b; y++) {
    for (let mo = 4; mo <= 15; mo++) {
      const yy = y + (mo > 12 ? 1 : 0);
      const mm = ((mo - 1) % 12) + 1;
      out.push(`${yy}-${String(mm).padStart(2,"0")}`);
    }
  }
  return out;
};
// 当年度 期間 (会計年度 4月始まり)
const _curFYStart = `${_curFY}-04-01`;
const _curFYEnd = _today.toISOString().slice(0, 10);

const SpotDetail = ({ onBack }) => {
  const [mode, setMode] = scS("today");
  const [weekday, setWeekday] = scS("1");
  const [fyStart, setFyStart] = scS(_curFY - 2);
  const [fyEnd, setFyEnd] = scS(_curFY);
  const [date, setDate] = scS(_curFYEnd);
  const [drStart, setDrStart] = scS(_curFYStart);
  const [drEnd, setDrEnd] = scS(_curFYEnd);

  const resetToCurrentFY = () => {
    setDrStart(_curFYStart);
    setDrEnd(_curFYEnd);
  };

  // ── 모드별 데이터 생성 ─────────────────────────────────
  // daily        → 48 slots (00:00 ~ 23:30)
  // daily_avg    → drStart~drEnd 일수
  // monthly_avg  → fyStart 4월 ~ fyEnd 3월 (월수)
  // yearly_avg   → DB 全期間 = 2005 ~ _curFY (年数)
  // weekday_avg  → drStart~drEnd 중 해당 요일에 한정 (대략 일수/7)
  const { matrix, rowLabels, rowHeaderLabel, xLabel } = scM(() => {
    if (mode === "today") {
      const slots = [];
      for (let h = 0; h < 24; h++) {
        for (const m of [0, 30]) {
          slots.push(`${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}`);
        }
      }
      const seed = (parseInt(date.replaceAll("-",""), 10) % 97) + 5;
      return {
        matrix: buildSpotRows(48, seed, "intraday"),
        rowLabels: slots,
        rowHeaderLabel: "時刻",
        xLabel: "時刻 (30分単位)",
      };
    }
    if (mode === "daily_avg") {
      const labels = enumerateDates(drStart, drEnd);
      const seed = 11 + (parseInt(drStart.replaceAll("-",""), 10) % 13);
      return {
        matrix: buildSpotRows(labels.length, seed, "trend"),
        rowLabels: labels,
        rowHeaderLabel: "日付",
        xLabel: "日付",
      };
    }
    if (mode === "monthly_avg") {
      const labels = enumerateMonthsFY(fyStart, fyEnd);
      const seed = 19 + ((fyStart * 7 + fyEnd) % 17);
      return {
        matrix: buildSpotRows(labels.length, seed, "trend"),
        rowLabels: labels,
        rowHeaderLabel: "月",
        xLabel: "年月",
      };
    }
    if (mode === "yearly_avg") {
      const labels = [];
      for (let y = 2005; y <= _curFY; y++) labels.push(String(y));
      return {
        matrix: buildSpotRows(labels.length, 23, "yearly"),
        rowLabels: labels,
        rowHeaderLabel: "年",
        xLabel: "年",
      };
    }
    // weekday_avg
    const wd = parseInt(weekday, 10);
    const labels = enumerateDates(drStart, drEnd).filter(s => new Date(s).getDay() === wd);
    const seed = 31 + wd * 7;
    return {
      matrix: buildSpotRows(Math.max(1, labels.length), seed, "trend"),
      rowLabels: labels.length ? labels : ["—"],
      rowHeaderLabel: "日付",
      xLabel: "日付",
    };
  }, [mode, weekday, fyStart, fyEnd, date, drStart, drEnd]);

  // 全エリア・全コマの平均
  const allValues = scM(() => Object.values(matrix).flat(), [matrix]);
  const avg = allValues.reduce((a, b) => a + b, 0) / allValues.length;
  const max = Math.max(...allValues);
  const min = Math.min(...allValues);

  return (
    <div style={{ padding: 28 }}>
      <DetailHeader
        title="JEPX スポット市場"
        subtitle="日本卸電力取引所 · 30分単位 · 10エリア"
        accent="var(--c-spot)"
        icon="spot"
        onBack={onBack}
        badge="LIVE · 09:14"
      />

      {/* モード + 期間/曜日選択 */}
      <div style={{
        display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
        marginBottom: 20,
      }}>
        <SegTabs value={mode} onChange={setMode} options={SPOT_MODES} accent="var(--c-spot)"/>

        {/* 当日: 単一日付ピッカー */}
        {mode === "today" && (
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <button style={navBtnStyle} onClick={() => {
              const d = new Date(date); d.setDate(d.getDate() - 1);
              setDate(d.toISOString().slice(0, 10));
            }}>◀</button>
            <DI_S1 value={date} onChange={setDate} accent="var(--c-spot)" />
            <button style={navBtnStyle} onClick={() => {
              const d = new Date(date); d.setDate(d.getDate() + 1);
              setDate(d.toISOString().slice(0, 10));
            }}>▶</button>
            <button style={btnStyle} onClick={() => setDate(_curFYEnd)}>今日</button>
          </div>
        )}

        {/* 日次平均 / 曜日別: 期間ピッカー + 今年度 ボタン */}
        {(mode === "daily_avg" || mode === "weekday_avg") && (
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={periodLabelStyle}>期間:</span>
            <DI_S1 value={drStart} onChange={setDrStart} accent="var(--c-spot)" />
            <span style={{ color: "var(--fg-tertiary)", fontSize: 12 }}>〜</span>
            <DI_S1 value={drEnd} onChange={setDrEnd} accent="var(--c-spot)" />
            <button style={btnStyle} onClick={resetToCurrentFY}>今年度</button>
          </div>
        )}

        {/* 曜日別: 曜日コンボ */}
        {mode === "weekday_avg" && (
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={periodLabelStyle}>曜日:</span>
            <select value={weekday} onChange={e => setWeekday(e.target.value)} style={inputStyle}>
              {WEEKDAYS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
        )}

        {/* 月次平均: 年度範囲 */}
        {mode === "monthly_avg" && (
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={periodLabelStyle}>年度:</span>
            <select value={fyStart} onChange={e => setFyStart(parseInt(e.target.value, 10))} style={inputStyle}>
              {FY_OPTIONS.map(y => <option key={y} value={y}>{y}年度</option>)}
            </select>
            <span style={{ color: "var(--fg-tertiary)", fontSize: 12 }}>〜</span>
            <select value={fyEnd} onChange={e => setFyEnd(parseInt(e.target.value, 10))} style={inputStyle}>
              {FY_OPTIONS.map(y => <option key={y} value={y}>{y}年度</option>)}
            </select>
          </div>
        )}

        {/* 年次平均: コントロールなし (DB全期間) */}
        {mode === "yearly_avg" && (
          <span style={{ fontSize: 12, color: "var(--fg-tertiary)", fontStyle: "italic" }}>
            DB 全期間集計
          </span>
        )}

        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button style={btnStyle}>📋 コピー</button>
          <button style={btnStyle}>⬇ CSV</button>
        </div>
      </div>

      {/* KPI strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
        <KPI label="システム平均" value={avg.toFixed(2)} unit="円/kWh" color="var(--c-spot)" delta={+0.8} sub={modeLabel(mode, weekday, fyStart, fyEnd, date, drStart, drEnd)}/>
        <KPI label="最高値" value={max.toFixed(2)} unit="円" color="var(--c-imb)" sub="ピーク帯"/>
        <KPI label="最安値" value={min.toFixed(2)} unit="円" color="var(--c-ok)" sub="深夜帯"/>
        <KPI label="取引量" value="487.2" unit="GWh" sub="前日比 +3.4%"/>
      </div>

      {/* === 表 (上) — 統計を上部に固定 === */}
      <div style={{ marginBottom: 20 }}>
        <PivotTable matrix={matrix} mode="spot" height={420} accent="var(--c-spot)" statsPosition="top"
          rowLabels={rowLabels} rowHeaderLabel={rowHeaderLabel}/>
      </div>

      {/* === グラフ (下) === */}
      <div style={{ marginBottom: 20 }}>
        <SpotChart matrix={matrix} mode={mode} weekday={weekday} fyStart={fyStart} fyEnd={fyEnd} date={date} drStart={drStart} drEnd={drEnd} rowLabels={rowLabels} xLabel={xLabel}/>
      </div>

      {/* エリア別 平均価格 比較バー */}
      <div style={{
        background: "var(--bg-surface)", borderRadius: 18, padding: 22,
        border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
      }}>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 14 }}>エリア別 平均価格</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px 24px" }}>
          {AREAS.map(a => {
            const arr = matrix[a] || [];
            const av = arr.reduce((s, b) => s + b, 0) / arr.length;
            const pct = (av / 18) * 100;
            return (
              <div key={a} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 56, fontSize: 12, fontWeight: 600, color: "var(--fg-secondary)" }}>{a}</div>
                <div style={{ flex: 1, height: 10, background: "var(--bg-surface-2)", borderRadius: 999, overflow: "hidden" }}>
                  <div style={{ width: `${pct}%`, height: "100%", background: AREA_COLORS[a], borderRadius: 999, transition: "width 0.6s ease-out" }}/>
                </div>
                <div style={{ width: 70, fontSize: 12, fontVariantNumeric: "tabular-nums", fontWeight: 700, textAlign: "right" }}>
                  {av.toFixed(2)} <span style={{ color: "var(--fg-tertiary)", fontWeight: 500, fontSize: 10 }}>円</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

// =========================================================
// SpotChart — エリア on/off + ChartFrame ラッパー
// =========================================================
const SpotChart = ({ matrix, mode, weekday, fyStart, fyEnd, date, drStart, drEnd, rowLabels, xLabel }) => {
  const [visible, setVisible] = scS(() => Object.fromEntries(AREAS.map(a => [a, true])));
  const filtered = scM(() => {
    const m = {};
    AREAS.forEach(a => { if (visible[a]) m[a] = matrix[a]; });
    return m;
  }, [matrix, visible]);
  const toggle = (a) => setVisible(v => ({ ...v, [a]: !v[a] }));
  const allOn = AREAS.every(a => visible[a]);

  const legend = (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap", maxWidth: 540, justifyContent: "flex-end" }}>
      <button onClick={() => setVisible(Object.fromEntries(AREAS.map(a => [a, !allOn])))}
        style={{
          padding: "3px 8px", fontSize: 10, fontWeight: 700, borderRadius: 6,
          border: "1px solid var(--border)", background: "var(--bg-surface-2)",
          color: "var(--fg-secondary)", cursor: "pointer", fontFamily: "inherit",
        }}>{allOn ? "クリア" : "全選択"}</button>
      {AREAS.map(a => (
        <button key={a} onClick={() => toggle(a)} style={{
          display: "inline-flex", alignItems: "center", gap: 4,
          fontSize: 10, fontWeight: 600,
          color: visible[a] ? AREA_COLORS[a] : "var(--fg-tertiary)",
          padding: "3px 8px", borderRadius: 6,
          background: visible[a] ? `color-mix(in srgb, ${AREA_COLORS[a]} 14%, transparent)` : "var(--bg-surface-2)",
          border: `1px solid ${visible[a] ? AREA_COLORS[a] : "var(--border)"}`,
          cursor: "pointer", fontFamily: "inherit",
          textDecoration: visible[a] ? "none" : "line-through",
          opacity: visible[a] ? 1 : 0.55,
        }}>
          <span style={{ width: 7, height: 7, borderRadius: 2, background: AREA_COLORS[a] }}/>
          {a}
        </button>
      ))}
    </div>
  );

  return (
    <ChartFrame
      title={chartTitle(mode, xLabel)}
      subtitle={`${modeLabel(mode, weekday, fyStart, fyEnd, date, drStart, drEnd)} · ${Object.keys(filtered).length} エリア表示中`}
      accent="var(--c-spot)"
      actions={legend}
      modalContent={<MultiAreaChart matrix={filtered} h={Math.max(560, window.innerHeight - 240)} rowLabels={rowLabels}/>}
    >
      <MultiAreaChart matrix={filtered} h={300} rowLabels={rowLabels}/>
    </ChartFrame>
  );
};

// =========================================================
// 2) IMBALANCE DETAIL — エリアチェック + 表 上 + グラフ 下
// =========================================================
const ImbalanceDetail = ({ onBack }) => {
  const [selected, setSelected] = scS(["東京", "東北", "関西"]);
  const [date, setDate] = scS("2026-05-01");
  const matrix = scM(() => buildAreaMatrix("imb", 13), []);
  const filtered = scM(() => {
    const m = {};
    selected.forEach(a => { if (matrix[a]) m[a] = matrix[a]; });
    return m;
  }, [matrix, selected]);

  const toggle = (a) => setSelected(s => s.includes(a) ? s.filter(x => x !== a) : [...s, a]);

  return (
    <div style={{ padding: 28 }}>
      <DetailHeader
        title="インバランス単価"
        subtitle="OCCTO リアルタイム · 系統需給差から算定"
        accent="var(--c-imb)"
        icon="won"
        onBack={onBack}
        badge="⚠ 警戒"
      />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
        <KPI label="本日 最大" value="38.50" unit="円/kWh" color="var(--c-imb)" delta={12.4} sub="18:30 / 東京"/>
        <KPI label="本日 平均" value="14.82" unit="円/kWh" sub="基準価格 +1.7σ"/>
        <KPI label="累計 不足" value="124.3" unit="MWh" color="var(--c-warn)" sub="前日比 +18%"/>
        <KPI label="次回 集計" value="09:30" sub="あと 16 分"/>
      </div>

      {/* エリアチェックボックス + 日付 + アクション */}
      <div style={{
        background: "var(--bg-surface)", borderRadius: 16, padding: "14px 18px",
        border: "1px solid var(--border-subtle)", marginBottom: 14,
        display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
      }}>
        <DI_S1 value={date} onChange={setDate} accent="var(--c-imb)" />
        <div style={{ width: 1, height: 22, background: "var(--border-subtle)" }}/>
        <div style={{ fontSize: 12, fontWeight: 700, color: "var(--fg-secondary)" }}>表示エリア</div>
        {AREAS.map(a => {
          const on = selected.includes(a);
          return (
            <label key={a} style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "5px 10px", borderRadius: 8, cursor: "pointer",
              background: on ? `color-mix(in srgb, ${AREA_COLORS[a]} 14%, transparent)` : "transparent",
              border: `1px solid ${on ? AREA_COLORS[a] : "var(--border)"}`,
              fontSize: 12, fontWeight: 600,
              color: on ? AREA_COLORS[a] : "var(--fg-secondary)",
              transition: "all 0.15s",
            }}>
              <input type="checkbox" checked={on} onChange={() => toggle(a)}
                     style={{ accentColor: AREA_COLORS[a], width: 13, height: 13 }}/>
              {a}
            </label>
          );
        })}
        <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
          <button onClick={() => setSelected([...AREAS])} style={btnSmStyle}>全選択</button>
          <button onClick={() => setSelected([])} style={btnSmStyle}>クリア</button>
          <button style={btnSmStyle}>📋 コピー</button>
        </div>
      </div>

      {/* === 表 (上) === */}
      <div style={{ marginBottom: 20 }}>
        <PivotTable matrix={filtered} mode="imb" height={400} accent="var(--c-imb)" statsPosition="top"/>
      </div>

      {/* === グラフ (下) === */}
      <div style={{ marginBottom: 20 }}>
        <ChartFrame
          title="30分単位 インバランス単価"
          subtitle={`${date} · 選択中 ${selected.length} エリア`}
          accent="var(--c-imb)"
          actions={
            <div style={{ display: "flex", gap: 6 }}>
              <Pill color="var(--c-imb)">⚠ 30+</Pill>
              <Pill color="var(--c-warn)">15-30</Pill>
              <Pill color="var(--c-ok)">〜15</Pill>
            </div>
          }
          modalContent={<MultiAreaChart matrix={filtered} h={Math.max(560, window.innerHeight - 240)}/>}
        >
          <MultiAreaChart matrix={filtered} h={300}/>
        </ChartFrame>
      </div>

      {/* アラート履歴 */}
      <div style={{
        background: "var(--bg-surface)", borderRadius: 18, padding: 22,
        border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
      }}>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 14 }}>本日のアラート発令履歴</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {[
            { t: "18:30", level: "緊急", msg: "東京エリア 38.50円/kWh — 緊急対応水準", c: "var(--c-imb)" },
            { t: "17:00", level: "警戒", msg: "東京エリア 22.80円/kWh — 警戒水準を超過", c: "var(--c-warn)" },
            { t: "08:15", level: "情報", msg: "OCCTO より系統需給ひっ迫の事前通知", c: "var(--c-info)" },
          ].map((a, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", gap: 14,
              padding: "12px 16px", borderRadius: 12,
              background: `color-mix(in srgb, ${a.c} 8%, var(--bg-surface-2))`,
              borderLeft: `3px solid ${a.c}`,
            }}>
              <div style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: 14, color: a.c }}>{a.t}</div>
              <Pill color={a.c}>{a.level}</Pill>
              <div style={{ fontSize: 13, color: "var(--fg-primary)" }}>{a.msg}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// =========================================================
// MultiAreaChart — 複数エリア重ね描き + ホバーインタラクション
// =========================================================
const MultiAreaChart = ({ matrix, h = 300, rowLabels = null }) => {
  const w = 880;
  const padL = 50, padR = 16, padT = 16, padB = 28;
  const series = Object.entries(matrix);
  const [hover, setHover] = scS(null);
  const svgRef = React.useRef(null);

  if (series.length === 0) {
    return <div style={{ height: h, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--fg-tertiary)" }}>エリアを選択してください</div>;
  }
  const all = series.flatMap(([, arr]) => arr);
  const yMax = Math.max(...all) * 1.05;
  const yMin = Math.min(0, Math.min(...all) * 1.1);
  const N = series[0][1].length;
  const xAt = (i) => padL + (i / Math.max(1, N - 1)) * (w - padL - padR);
  const yAt = (v) => padT + (1 - (v - yMin) / (yMax - yMin)) * (h - padT - padB);

  const yTicks = 5;
  const ticks = Array.from({ length: yTicks + 1 }, (_, i) => yMin + (i / yTicks) * (yMax - yMin));

  const handleMove = (e) => {
    const rect = svgRef.current.getBoundingClientRect();
    const xPx = ((e.clientX - rect.left) / rect.width) * w;
    if (xPx < padL || xPx > w - padR) { setHover(null); return; }
    const idx = Math.round(((xPx - padL) / (w - padL - padR)) * (N - 1));
    if (idx >= 0 && idx < N) setHover(idx);
  };

  // X軸目盛り: rowLabels の長さに応じて等間隔に表示
  const xTickIndices = (() => {
    if (!N) return [];
    const target = N <= 12 ? N : N <= 48 ? 6 : 8;
    const step = Math.max(1, Math.round((N - 1) / (target - 1)) || 1);
    const out = [];
    for (let i = 0; i < N; i += step) out.push(i);
    if (out[out.length - 1] !== N - 1) out.push(N - 1);
    return out;
  })();
  const labelAt = (i) => {
    if (rowLabels && rowLabels[i] != null) return rowLabels[i];
    // 48 コマ既定
    const h2 = Math.floor(i / 2), m = (i % 2) * 30;
    return `${String(h2).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  };
  // 표시용: 너무 길면 잘라내기 (YYYY-MM-DD → MM-DD)
  const shortLabel = (s) => {
    if (typeof s !== "string") return String(s);
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s.slice(5);   // MM-DD
    if (/^\d{4}-\d{2}$/.test(s))       return s;            // YYYY-MM
    return s;
  };

  return (
    <div style={{ position: "relative" }}>
      <svg ref={svgRef} width="100%" height={h} viewBox={`0 0 ${w} ${h}`}
        onMouseMove={handleMove} onMouseLeave={() => setHover(null)}
        style={{ display: "block", cursor: "crosshair" }}>
        {/* grid */}
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={w - padR} y1={yAt(t)} y2={yAt(t)} stroke="var(--border-subtle)" strokeWidth="1"/>
            <text x={padL - 8} y={yAt(t) + 4} textAnchor="end" fontSize="10" fill="var(--fg-tertiary)">{t.toFixed(0)}</text>
          </g>
        ))}
        {[0, 6, 12, 18, 24].map(h2 => {
          // 48コマモード以外では rowLabels の方を使用
          if (rowLabels) return null;
          const i = h2 * 2;
          return (
            <g key={h2}>
              <line x1={xAt(i)} x2={xAt(i)} y1={padT} y2={h - padB} stroke="var(--border-subtle)" strokeDasharray="2 3"/>
              <text x={xAt(i)} y={h - 10} textAnchor="middle" fontSize="10" fill="var(--fg-tertiary)">{String(h2).padStart(2,"0")}:00</text>
            </g>
          );
        })}
        {/* dynamic x ticks (rowLabels モード) */}
        {rowLabels && xTickIndices.map((i) => (
          <g key={`xt-${i}`}>
            <line x1={xAt(i)} x2={xAt(i)} y1={padT} y2={h - padB} stroke="var(--border-subtle)" strokeDasharray="2 3"/>
            <text x={xAt(i)} y={h - 10} textAnchor="middle" fontSize="10" fill="var(--fg-tertiary)">{shortLabel(labelAt(i))}</text>
          </g>
        ))}
        {/* series lines */}
        {series.map(([area, arr]) => {
          const d = arr.map((v, i) => `${i === 0 ? "M" : "L"} ${xAt(i)} ${yAt(v)}`).join(" ");
          const dim = hover != null;
          return <path key={area} d={d} stroke={AREA_COLORS[area]} strokeWidth={dim ? "1.4" : "1.8"}
                  fill="none" strokeLinejoin="round" strokeLinecap="round"
                  style={{ opacity: dim ? 0.55 : 1, transition: "opacity 0.15s, stroke-width 0.15s" }}/>;
        })}
        {/* hover line + dots */}
        {hover != null && (
          <g>
            <line x1={xAt(hover)} x2={xAt(hover)} y1={padT} y2={h - padB}
                  stroke="var(--fg-secondary)" strokeWidth="1" strokeDasharray="3 3" opacity="0.6"/>
            {series.map(([area, arr]) => {
              const v = arr[hover];
              return (
                <g key={area}>
                  <circle cx={xAt(hover)} cy={yAt(v)} r="6"
                          fill={AREA_COLORS[area]} fillOpacity="0.18"/>
                  <circle cx={xAt(hover)} cy={yAt(v)} r="3.2"
                          fill={AREA_COLORS[area]} stroke="#fff" strokeWidth="1.2"/>
                </g>
              );
            })}
          </g>
        )}
      </svg>
      {/* tooltip */}
      {hover != null && (() => {
        const xPct = (xAt(hover) / w) * 100;
        const onLeft = xPct > 65;
        return (
          <div style={{
            position: "absolute",
            top: 12,
            left: onLeft ? "auto" : `calc(${xPct}% + 14px)`,
            right: onLeft ? `calc(${100 - xPct}% + 14px)` : "auto",
            background: "var(--bg-surface)",
            border: "1px solid var(--border-subtle)",
            borderRadius: 10, padding: "8px 12px",
            boxShadow: "var(--shadow-md)",
            fontSize: 11, fontVariantNumeric: "tabular-nums",
            pointerEvents: "none", minWidth: 132, zIndex: 5,
          }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--fg-primary)", marginBottom: 6 }}>
              {labelAt(hover)}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              {series.map(([area, arr]) => (
                <div key={area} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: AREA_COLORS[area] }}/>
                  <span style={{ color: "var(--fg-secondary)", fontWeight: 600, minWidth: 36 }}>{area}</span>
                  <span style={{ marginLeft: "auto", color: AREA_COLORS[area], fontWeight: 700 }}>
                    {arr[hover].toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        );
      })()}
    </div>
  );
};

// ──────────────────────────────────────────────────
const inputStyle = {
  padding: "8px 12px", borderRadius: 10,
  border: "1px solid var(--border)",
  background: "var(--bg-surface)", color: "var(--fg-primary)",
  fontFamily: "inherit", fontSize: 12, fontWeight: 600,
};
const btnStyle = {
  padding: "8px 14px", borderRadius: 10,
  border: "1px solid var(--border)",
  background: "var(--bg-surface)", color: "var(--fg-secondary)",
  fontFamily: "inherit", fontSize: 12, fontWeight: 600, cursor: "pointer",
};
const btnSmStyle = {
  padding: "5px 10px", borderRadius: 8,
  border: "1px solid var(--border)",
  background: "var(--bg-surface-2)", color: "var(--fg-secondary)",
  fontFamily: "inherit", fontSize: 11, fontWeight: 600, cursor: "pointer",
};

const modeLabel = (mode, wd, fyStart, fyEnd, date, drStart, drEnd) => {
  if (mode === "today")        return `${date} 48 コマ`;
  if (mode === "daily_avg")    return `${drStart} 〜 ${drEnd} 日次平均`;
  if (mode === "monthly_avg")  return `${fyStart}年度 〜 ${fyEnd}年度 月次平均`;
  if (mode === "yearly_avg")   return `DB 全期間 年次平均`;
  if (mode === "weekday_avg") {
    const lbl = WEEKDAYS.find(([k]) => k === wd)?.[1] || "月";
    return `${lbl}曜日 ${drStart} 〜 ${drEnd}`;
  }
  return "";
};

const chartTitle = (mode, xLabel) => {
  if (mode === "today")       return "30分単位 価格推移";
  if (mode === "daily_avg")   return "日次平均 価格推移";
  if (mode === "monthly_avg") return "月次平均 価格推移";
  if (mode === "yearly_avg")  return "年次平均 価格推移";
  if (mode === "weekday_avg") return "曜日別 日次平均 推移";
  return "価格推移";
};

const navBtnStyle = {
  width: 30, height: 34, borderRadius: 8,
  border: "1px solid var(--border)",
  background: "var(--bg-surface-2)", color: "var(--fg-secondary)",
  fontFamily: "inherit", fontSize: 11, fontWeight: 700, cursor: "pointer",
  display: "inline-flex", alignItems: "center", justifyContent: "center",
};
const periodLabelStyle = {
  fontSize: 12, fontWeight: 700, color: "var(--fg-secondary)",
  marginRight: 2,
};

window.varA_detail_screens = { SpotDetail, ImbalanceDetail };
