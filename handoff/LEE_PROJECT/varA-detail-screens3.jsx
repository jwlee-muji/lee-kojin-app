/* global React, Ic */
// ============================================================
// Weather Detail — 強化版
// 気温・降水確率・雲量・風速・湿度・5日間予報・10地域マップ
// ============================================================
const { useState: w3S, useMemo: w3M } = React;
const { KPI, DetailHeader, ChartFrame } = window.varA_detail_atoms;
const { Pill } = window.varA_atoms;
const W3 = window.LEE_DATA;
const { DateInput: DI_S3 } = window.varA_datepicker;
const WI = ({ kind, size, isDark }) => window.WeatherIllust
  ? React.createElement(window.WeatherIllust, { category: kind, isDark, w: size, h: size })
  : null;

// 24時間データ生成
const buildHourly = (cur) => Array.from({ length: 24 }, (_, i) => {
  const t = cur.temp + Math.sin((i - 14) / 4) * 5 - (i < 6 || i > 20 ? 3 : 0);
  // 降水確率 (朝夕に高い)
  const morning = Math.exp(-Math.pow((i - 8) / 4, 2)) * 30;
  const evening = Math.exp(-Math.pow((i - 19) / 3.5, 2)) * 50;
  const precip = Math.max(0, Math.min(100, morning + evening + (Math.sin(i * 0.7) * 15)));
  // 雲量
  const cloud = Math.max(0, Math.min(100, 40 + Math.sin(i * 0.4) * 35 + Math.cos(i * 0.6) * 15));
  // 風速 m/s
  const wind = Math.max(0.5, 3.5 + Math.sin((i - 13) / 3) * 2.5 + Math.random() * 0.4 - 0.2);
  // 湿度
  const humidity = Math.max(40, Math.min(95, 70 - Math.sin((i - 14) / 5) * 20));
  return {
    h: i, t: +t.toFixed(1),
    precip: Math.round(precip),
    cloud: Math.round(cloud),
    wind: +wind.toFixed(1),
    humidity: Math.round(humidity),
  };
});

const WeatherDetail = ({ onBack, isDark }) => {
  const [region, setRegion] = w3S("東京");
  const [date, setDate] = w3S("2026-05-01");
  const cur = W3.weather.find(w => w.region === region) || W3.weather[2];
  const hourly = w3M(() => buildHourly(cur), [cur]);

  const tMax = Math.max(...hourly.map(x => x.t));
  const tMin = Math.min(...hourly.map(x => x.t));
  const precipMax = Math.max(...hourly.map(x => x.precip));
  const cloudAvg = Math.round(hourly.reduce((s, x) => s + x.cloud, 0) / 24);
  const windAvg = (hourly.reduce((s, x) => s + x.wind, 0) / 24).toFixed(1);

  return (
    <div style={{ padding: 28 }}>
      <DetailHeader
        title="全国天気"
        subtitle="Open-Meteo · 10地域 · 1時間ごと更新"
        accent={cur.accent}
        icon="weather"
        onBack={onBack}
        badge={`${cur.region} ${cur.temp}° · ${cur.text}`}
      />

      {/* Hero — アニメーション付き */}
      <div style={{
        background: `linear-gradient(135deg, ${cur.accent}33, ${cur.accent}0A)`,
        borderRadius: 22, padding: 28, marginBottom: 20,
        border: "1px solid var(--border-subtle)",
        display: "flex", alignItems: "center", gap: 28,
        position: "relative", overflow: "hidden",
        animation: "weatherFadeIn 0.5s ease",
      }}>
        {/* 背景の動くドット */}
        <div style={{ position: "absolute", inset: 0, opacity: 0.4, pointerEvents: "none" }}>
          {[...Array(20)].map((_, i) => (
            <div key={i} style={{
              position: "absolute",
              left: `${(i * 13) % 100}%`,
              top: `${(i * 17) % 100}%`,
              width: 4, height: 4, borderRadius: "50%",
              background: cur.accent,
              animation: `weatherFloat ${3 + (i % 3)}s ease-in-out ${i * 0.2}s infinite alternate`,
            }}/>
          ))}
        </div>

        <div style={{ width: 200, height: 200, flexShrink: 0,
                      filter: `drop-shadow(0 8px 24px ${cur.accent}66)`,
                      animation: "weatherIcon 4s ease-in-out infinite alternate" }}>
          <WI kind={cur.wmo} size={200} isDark={isDark}/>
        </div>
        <div style={{ flex: 1, position: "relative", zIndex: 1 }}>
          <div style={{ fontSize: 13, color: "var(--fg-secondary)", fontWeight: 600, marginBottom: 4 }}>
            {cur.region} · {date} · 09:14 更新
          </div>
          <div style={{ fontSize: 96, fontWeight: 800, lineHeight: 1, letterSpacing: "-0.04em" }}>
            {cur.temp}<span style={{ fontSize: 36, fontWeight: 600, color: "var(--fg-secondary)" }}>°C</span>
          </div>
          <div style={{ fontSize: 22, fontWeight: 700, marginTop: 6, color: cur.accent }}>{cur.text}</div>
          <div style={{ display: "flex", gap: 22, marginTop: 16, fontSize: 13, color: "var(--fg-secondary)" }}>
            <span>↑ 最高 <b style={{ color: "var(--c-bad)" }}>{tMax.toFixed(0)}°</b></span>
            <span>↓ 最低 <b style={{ color: "var(--c-info)" }}>{tMin.toFixed(0)}°</b></span>
            <span>体感 <b>{cur.temp - 1}°</b></span>
            <span>降水確率 <b style={{ color: "#3B82F6" }}>{precipMax}%</b></span>
            <span>湿度 <b>62%</b></span>
            <span>風 <b>{windAvg} m/s</b> NE</span>
          </div>
        </div>
      </div>

      {/* 日付選択 + 地域ピッカー */}
      <div style={{
        display: "flex", alignItems: "center", gap: 10, marginBottom: 16, flexWrap: "wrap",
      }}>
        <DI_S3 value={date} onChange={setDate} accent="var(--c-weather)" />
        <div style={{ width: 1, height: 22, background: "var(--border-subtle)" }}/>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", flex: 1 }}>
          {W3.weather.map(w => (
            <button key={w.region} onClick={() => setRegion(w.region)}
              style={{
                padding: "7px 11px", borderRadius: 10,
                border: "1px solid",
                borderColor: region === w.region ? w.accent : "var(--border)",
                background: region === w.region ? `${w.accent}1F` : "var(--bg-surface)",
                color: region === w.region ? w.accent : "var(--fg-primary)",
                fontFamily: "inherit", fontSize: 11, fontWeight: 700, cursor: "pointer",
                display: "flex", alignItems: "center", gap: 6,
                transition: "all 0.15s",
              }}>
              <span style={{ width: 16, height: 16, display: "inline-flex" }}>
                <WI kind={w.wmo} size={16} isDark={isDark}/>
              </span>
              {w.region}
              <span style={{ fontVariantNumeric: "tabular-nums", color: "var(--fg-tertiary)" }}>{w.temp}°</span>
            </button>
          ))}
        </div>
      </div>

      {/* KPI 4個 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
        <KPI label="気温レンジ" value={`${tMin.toFixed(0)}〜${tMax.toFixed(0)}`} unit="°C" color={cur.accent} sub="今日"/>
        <KPI label="最大降水確率" value={`${precipMax}`} unit="%" color="#3B82F6" sub={`${hourly.findIndex(h => h.precip === precipMax)}時頃`}/>
        <KPI label="雲量平均" value={`${cloudAvg}`} unit="%" color="#94A3B8" sub={cloudAvg > 60 ? "曇りがち" : cloudAvg > 30 ? "やや曇り" : "晴れ"}/>
        <KPI label="平均風速" value={windAvg} unit="m/s" color="#14B8A6" sub="NE 北東風"/>
      </div>

      {/* 24時間 マルチ指標チャート */}
      <div style={{ marginBottom: 20 }}>
        <ChartFrame
          title={`${cur.region} · 24時間 詳細予報`}
          subtitle="気温 / 降水確率 / 雲量 / 風速"
          accent={cur.accent}
          modalContent={<HourlyMultiChart hourly={hourly} accent={cur.accent} h={Math.max(560, window.innerHeight - 240)}/>}
        >
          <HourlyMultiChart hourly={hourly} accent={cur.accent} h={320}/>
        </ChartFrame>
      </div>

      {/* 5日間予報 + 10地域マップ */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1.4fr", gap: 16, marginBottom: 20 }}>
        <div style={{
          background: "var(--bg-surface)", borderRadius: 18, padding: 22,
          border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
        }}>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 14 }}>5日間 予報</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {[
              ["明日", "clear",         21, 12, "#FBBF24", 10],
              ["木",   "partly_cloudy", 19, 11, "#FCD34D", 30],
              ["金",   "rainy",         15,  9, "#3B82F6", 80],
              ["土",   "cloudy",        17, 10, "#9CA3AF", 40],
              ["日",   "clear",         22, 13, "#FBBF24",  5],
            ].map((r, i) => (
              <div key={i} style={{
                display: "flex", alignItems: "center", gap: 12,
                padding: "10px 4px",
                borderTop: i > 0 ? "1px solid var(--border-subtle)" : "none",
              }}>
                <div style={{ width: 36, fontSize: 13, fontWeight: 700 }}>{r[0]}</div>
                <div style={{ width: 32, height: 32 }}>
                  <WI kind={r[1]} size={32} isDark={isDark}/>
                </div>
                <div style={{ flex: 1, height: 6, background: "var(--bg-surface-2)", borderRadius: 999, position: "relative" }}>
                  <div style={{
                    position: "absolute",
                    left: `${(r[3] / 30) * 100}%`,
                    width: `${((r[2] - r[3]) / 30) * 100}%`,
                    height: "100%",
                    background: `linear-gradient(90deg, ${r[4]}88, ${r[4]})`,
                    borderRadius: 999,
                  }}/>
                </div>
                <div style={{ display: "flex", gap: 10, fontSize: 12, fontWeight: 700, fontVariantNumeric: "tabular-nums", minWidth: 70, justifyContent: "flex-end" }}>
                  <span style={{ color: "var(--fg-tertiary)" }}>{r[3]}°</span>
                  <span>{r[2]}°</span>
                </div>
                <div style={{ width: 38, fontSize: 11, color: "#3B82F6", fontWeight: 700, textAlign: "right" }}>
                  ☔ {r[5]}%
                </div>
              </div>
            ))}
          </div>
        </div>

        <div style={{
          background: "var(--bg-surface)", borderRadius: 18, padding: 22,
          border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
        }}>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 14 }}>10地域 一覧</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10 }}>
            {W3.weather.map((w, i) => (
              <div key={i} onClick={() => setRegion(w.region)} style={{
                padding: 12, borderRadius: 12, cursor: "pointer",
                background: region === w.region ? `${w.accent}1F` : "var(--bg-surface-2)",
                border: `1px solid ${region === w.region ? w.accent : "var(--border-subtle)"}`,
                transition: "all 0.15s",
                display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
                transform: region === w.region ? "translateY(-2px)" : "none",
              }}>
                <div style={{ width: 40, height: 40 }}>
                  <WI kind={w.wmo} size={40} isDark={isDark}/>
                </div>
                <div style={{ fontSize: 11, fontWeight: 700 }}>{w.region}</div>
                <div style={{ fontSize: 18, fontWeight: 800, color: w.accent, fontVariantNumeric: "tabular-nums" }}>
                  {w.temp}°
                </div>
                <div style={{ fontSize: 9, color: "var(--fg-tertiary)" }}>{w.text}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* CSS animations */}
      <style>{`
        @keyframes weatherFadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
        @keyframes weatherFloat { from { transform: translate(0, 0); opacity: 0.3; } to { transform: translate(8px, -8px); opacity: 0.7; } }
        @keyframes weatherIcon { from { transform: translateY(-4px) rotate(-2deg); } to { transform: translateY(4px) rotate(2deg); } }
      `}</style>
    </div>
  );
};

// =========================================================
// HourlyMultiChart — 4軸: 気温, 降水確率, 雲量, 風速
// =========================================================
const HourlyMultiChart = ({ hourly, accent, h = 320 }) => {
  const [hover, setHover] = w3S(null);
  const [vis, setVis] = w3S({ temp: true, precip: true, cloud: true, wind: true });
  const ref = React.useRef(null);
  const w = 880;
  const padL = 50, padR = 60, padT = 16, padB = 32;

  const N = hourly.length;
  const xAt = (i) => padL + (i / (N - 1)) * (w - padL - padR);

  // 気温スケール (左軸, 0〜35)
  const tMin = Math.min(...hourly.map(x => x.t)) - 2;
  const tMax = Math.max(...hourly.map(x => x.t)) + 2;
  const yAtT = (v) => padT + (1 - (v - tMin) / (tMax - tMin)) * (h - padT - padB);
  // 降水/雲量スケール (右軸, 0〜100%)
  const yAtP = (v) => padT + (1 - v / 100) * (h - padT - padB);
  // 風速スケール (右軸補助, 0〜10)
  const yAtW = (v) => padT + (1 - v / 10) * (h - padT - padB);

  const handleMove = (e) => {
    const r = ref.current.getBoundingClientRect();
    const xp = ((e.clientX - r.left) / r.width) * w;
    if (xp < padL || xp > w - padR) { setHover(null); return; }
    const idx = Math.round(((xp - padL) / (w - padL - padR)) * (N - 1));
    if (idx >= 0 && idx < N) setHover(idx);
  };

  const SERIES = [
    { id: "temp",   label: "気温",     color: accent,    unit: "°C",  yAt: yAtT },
    { id: "precip", label: "降水確率", color: "#3B82F6", unit: "%",   yAt: yAtP },
    { id: "cloud",  label: "雲量",     color: "#94A3B8", unit: "%",   yAt: yAtP },
    { id: "wind",   label: "風速",     color: "#14B8A6", unit: "m/s", yAt: yAtW },
  ];

  return (
    <div style={{ position: "relative" }}>
      {/* legend toggles */}
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        {SERIES.map(s => (
          <button key={s.id} onClick={() => setVis(v => ({ ...v, [s.id]: !v[s.id] }))}
            style={{
              fontFamily: "inherit", fontSize: 11, fontWeight: 700,
              padding: "4px 10px", borderRadius: 6, cursor: "pointer",
              border: `1px solid ${vis[s.id] ? s.color : "var(--border)"}`,
              background: vis[s.id] ? `color-mix(in srgb, ${s.color} 14%, transparent)` : "var(--bg-surface-2)",
              color: vis[s.id] ? s.color : "var(--fg-tertiary)",
              opacity: vis[s.id] ? 1 : 0.55,
              textDecoration: vis[s.id] ? "none" : "line-through",
              display: "inline-flex", alignItems: "center", gap: 5,
            }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: s.color }}/>
            {s.label}
          </button>
        ))}
      </div>

      <svg ref={ref} width="100%" height={h} viewBox={`0 0 ${w} ${h}`}
        onMouseMove={handleMove} onMouseLeave={() => setHover(null)}
        style={{ display: "block", cursor: "crosshair" }}>
        {/* grid (左: 気温) */}
        {[0, 0.25, 0.5, 0.75, 1].map((p, i) => {
          const v = tMin + p * (tMax - tMin);
          const y = padT + (1 - p) * (h - padT - padB);
          return (
            <g key={i}>
              <line x1={padL} x2={w - padR} y1={y} y2={y} stroke="var(--border-subtle)"/>
              <text x={padL - 8} y={y + 4} textAnchor="end" fontSize="10" fill={accent} fontWeight="600">{v.toFixed(0)}°</text>
              <text x={w - padR + 8} y={y + 4} fontSize="10" fill="var(--fg-tertiary)">{(p * 100).toFixed(0)}%</text>
            </g>
          );
        })}
        {/* x ticks 3h */}
        {[0, 3, 6, 9, 12, 15, 18, 21].map(t => {
          const x = xAt(t);
          return (
            <g key={t}>
              <line x1={x} x2={x} y1={padT} y2={h - padB} stroke="var(--border-subtle)" strokeDasharray="2 3"/>
              <text x={x} y={h - 10} textAnchor="middle" fontSize="10" fill="var(--fg-tertiary)">{String(t).padStart(2, "0")}:00</text>
            </g>
          );
        })}

        {/* 雲量 (薄い面) */}
        {vis.cloud && (() => {
          const pts = hourly.map((p, i) => `${xAt(i)},${yAtP(p.cloud)}`);
          const last = xAt(N - 1), first = xAt(0), bot = h - padB;
          return <polygon points={`${first},${bot} ${pts.join(" ")} ${last},${bot}`}
                          fill="#94A3B8" fillOpacity="0.15"/>;
        })()}
        {/* 降水確率 (バー) */}
        {vis.precip && hourly.map((p, i) => {
          if (p.precip < 2) return null;
          const x = xAt(i), y = yAtP(p.precip), bar = (h - padB) - y;
          return <rect key={i} x={x - 6} y={y} width="12" height={bar}
                       fill="#3B82F6" fillOpacity="0.55" rx="2"/>;
        })}
        {/* 風速 (細い線) */}
        {vis.wind && (() => {
          const d = hourly.map((p, i) => `${i === 0 ? "M" : "L"} ${xAt(i)} ${yAtW(p.wind)}`).join(" ");
          return <path d={d} fill="none" stroke="#14B8A6" strokeWidth="1.5"
                       strokeDasharray="4 3" strokeLinecap="round"/>;
        })()}
        {/* 気温 (太い線) */}
        {vis.temp && (() => {
          const d = hourly.map((p, i) => `${i === 0 ? "M" : "L"} ${xAt(i)} ${yAtT(p.t)}`).join(" ");
          return (
            <g>
              <path d={d} fill="none" stroke={accent} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"/>
              {hourly.filter((_, i) => i % 3 === 0).map((p, i) => (
                <circle key={i} cx={xAt(i * 3)} cy={yAtT(p.t)} r="3.5" fill={accent} stroke="#fff" strokeWidth="1.2"/>
              ))}
            </g>
          );
        })()}

        {/* hover guide */}
        {hover != null && (
          <g>
            <line x1={xAt(hover)} x2={xAt(hover)} y1={padT} y2={h - padB}
                  stroke="var(--fg-secondary)" strokeWidth="1" strokeDasharray="3 3" opacity="0.7"/>
            {SERIES.filter(s => vis[s.id]).map(s => (
              <circle key={s.id} cx={xAt(hover)} cy={s.yAt(hourly[hover][s.id === "temp" ? "t" : s.id])}
                      r="4" fill={s.color} stroke="#fff" strokeWidth="1.2"/>
            ))}
          </g>
        )}
      </svg>

      {/* tooltip */}
      {hover != null && (() => {
        const xPct = (xAt(hover) / w) * 100;
        const onLeft = xPct > 65;
        const p = hourly[hover];
        return (
          <div style={{
            position: "absolute", top: 32,
            left: onLeft ? "auto" : `calc(${xPct}% + 14px)`,
            right: onLeft ? `calc(${100 - xPct}% + 14px)` : "auto",
            background: "var(--bg-surface)", border: "1px solid var(--border-subtle)",
            borderRadius: 10, padding: "10px 14px", boxShadow: "var(--shadow-md)",
            fontSize: 11, fontVariantNumeric: "tabular-nums",
            pointerEvents: "none", minWidth: 150, zIndex: 5,
          }}>
            <div style={{ fontSize: 12, fontWeight: 800, marginBottom: 8 }}>
              {String(p.h).padStart(2, "0")}:00
            </div>
            <Row color={accent}    label="気温"     value={`${p.t.toFixed(1)} °C`}/>
            <Row color="#3B82F6"   label="降水確率" value={`${p.precip}%`}/>
            <Row color="#94A3B8"   label="雲量"     value={`${p.cloud}%`}/>
            <Row color="#14B8A6"   label="風速"     value={`${p.wind} m/s`}/>
            <Row color="#A855F7"   label="湿度"     value={`${p.humidity}%`}/>
          </div>
        );
      })()}
    </div>
  );
};

const Row = ({ color, label, value }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
    <span style={{ width: 8, height: 8, borderRadius: 2, background: color }}/>
    <span style={{ color: "var(--fg-secondary)", fontWeight: 600, minWidth: 56 }}>{label}</span>
    <span style={{ marginLeft: "auto", color, fontWeight: 700 }}>{value}</span>
  </div>
);

const dateInputStyle = {
  padding: "7px 11px", borderRadius: 9,
  border: "1px solid var(--border)",
  background: "var(--bg-surface)", color: "var(--fg-primary)",
  fontFamily: "inherit", fontSize: 12, fontWeight: 600,
};

window.varA_detail_screens3 = { WeatherDetail };
