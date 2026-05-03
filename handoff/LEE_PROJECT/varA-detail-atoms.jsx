/* global React, Ic */
// ============================================================
// Variation A — Detail screen building blocks
// 카드 클릭 시 펼쳐지는 상세 화면용 차트와 컴포넌트
// ============================================================

const { useState: dS, useEffect: dE, useMemo: dM, useRef: dR } = React;
const DATA = window.LEE_DATA;

// ── Big chart with axes + grid + crosshair ───────────────────
const BigChart = ({ data, color, label = "", w = 880, h = 280, yUnit = "", animate = true }) => {
  const min = Math.min(...data) * 0.9;
  const max = Math.max(...data) * 1.1;
  const range = max - min || 1;
  const padL = 44, padR = 12, padT = 14, padB = 30;
  const cw = w - padL - padR;
  const ch = h - padT - padB;
  const pts = data.map((v, i) => [
    padL + (i / (data.length - 1)) * cw,
    padT + ch - ((v - min) / range) * ch,
  ]);
  const path = pts.map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`)).join(" ");
  const area = path + ` L${pts[pts.length-1][0]},${padT+ch} L${pts[0][0]},${padT+ch} Z`;
  const yTicks = 5;
  const xTicks = 6;
  const [hover, setHover] = dS(null);
  const ref = dR();

  const handleMove = (e) => {
    const rect = ref.current.getBoundingClientRect();
    const x = e.clientX - rect.left - padL;
    const idx = Math.round((x / cw) * (data.length - 1));
    if (idx >= 0 && idx < data.length) setHover(idx);
  };

  return (
    <svg ref={ref} width={w} height={h}
      onMouseMove={handleMove} onMouseLeave={() => setHover(null)}
      style={{ display: "block", cursor: "crosshair" }}>
      <defs>
        <linearGradient id={`big-${label}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35"/>
          <stop offset="100%" stopColor={color} stopOpacity="0"/>
        </linearGradient>
      </defs>

      {/* Y grid */}
      {Array.from({ length: yTicks }).map((_, i) => {
        const y = padT + (i / (yTicks - 1)) * ch;
        const v = max - (i / (yTicks - 1)) * range;
        return (
          <g key={`y-${i}`}>
            <line x1={padL} y1={y} x2={w - padR} y2={y}
              stroke="var(--grid-line)" strokeWidth="1"
              strokeDasharray={i === yTicks - 1 ? "" : "3,4"}/>
            <text x={padL - 8} y={y + 3} fill="var(--fg-tertiary)" fontSize="10"
              fontFamily="var(--font-mono)" textAnchor="end">
              {v.toFixed(yUnit === "%" ? 1 : 1)}
            </text>
          </g>
        );
      })}

      {/* X grid + labels */}
      {Array.from({ length: xTicks }).map((_, i) => {
        const x = padL + (i / (xTicks - 1)) * cw;
        const labelIdx = Math.round((i / (xTicks - 1)) * (data.length - 1));
        const hour = Math.round((labelIdx / data.length) * 24);
        return (
          <g key={`x-${i}`}>
            <line x1={x} y1={padT} x2={x} y2={padT + ch}
              stroke="var(--grid-line)" strokeWidth="1" strokeDasharray="3,4"/>
            <text x={x} y={h - 10} fill="var(--fg-tertiary)" fontSize="10"
              fontFamily="var(--font-mono)" textAnchor="middle">
              {String(hour).padStart(2, "0")}:00
            </text>
          </g>
        );
      })}

      {/* Area + Line */}
      <path d={area} fill={`url(#big-${label})`}
        style={animate ? { animation: "fadeIn 0.6s ease-out" } : {}}/>
      <path d={path} fill="none" stroke={color} strokeWidth="2"
        strokeLinecap="round" strokeLinejoin="round"
        style={animate ? {
          strokeDasharray: 2000,
          strokeDashoffset: 2000,
          animation: "drawLine 1.2s ease-out forwards",
        } : {}}/>

      {/* Hover */}
      {hover != null && (
        <g>
          <line x1={pts[hover][0]} y1={padT} x2={pts[hover][0]} y2={padT + ch}
            stroke={color} strokeWidth="1" strokeDasharray="3,3" opacity="0.5"/>
          <circle cx={pts[hover][0]} cy={pts[hover][1]} r="5" fill={color}/>
          <circle cx={pts[hover][0]} cy={pts[hover][1]} r="9" fill={color} opacity="0.25"/>
          <g transform={`translate(${pts[hover][0]},${pts[hover][1] - 12})`}>
            <rect x="-32" y="-22" width="64" height="20" rx="4"
              fill="var(--bg-surface)" stroke={color} strokeWidth="1"/>
            <text x="0" y="-8" fill="var(--fg-primary)" fontSize="11"
              fontFamily="var(--font-mono)" textAnchor="middle" fontWeight="700">
              {data[hover].toFixed(2)} {yUnit}
            </text>
          </g>
        </g>
      )}
    </svg>
  );
};

// ── KPI tile ────────────────────────────────────────────────
const KPI = ({ label, value, unit, color, delta, sub }) => (
  <div style={{
    background: "var(--bg-surface)",
    borderRadius: 16, padding: 18,
    border: "1px solid var(--border-subtle)",
    boxShadow: "var(--shadow-sm)",
  }}>
    <div style={{ fontSize: 11, fontWeight: 600, color: "var(--fg-tertiary)", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 8 }}>{label}</div>
    <div style={{ display: "flex", alignItems: "baseline", gap: 5 }}>
      <span style={{
        fontSize: 28, fontWeight: 800, color: color || "var(--fg-primary)",
        letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums",
      }}>{value}</span>
      {unit && <span style={{ fontSize: 12, color: "var(--fg-tertiary)", fontWeight: 600 }}>{unit}</span>}
      {delta != null && (
        <span style={{
          marginLeft: "auto", fontSize: 12, fontWeight: 700,
          color: delta > 0 ? "var(--c-bad)" : "var(--c-ok)",
        }}>{delta > 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}%</span>
      )}
    </div>
    {sub && <div style={{ fontSize: 11, color: "var(--fg-secondary)", marginTop: 6 }}>{sub}</div>}
  </div>
);

// ── Detail page wrapper ─────────────────────────────────────
const DetailHeader = ({ title, subtitle, accent, icon, onBack, badge, actions }) => (
  <div style={{
    display: "flex", alignItems: "center", gap: 14, marginBottom: 20,
    paddingBottom: 18, borderBottom: "1px solid var(--border-subtle)",
  }}>
    <button onClick={onBack} style={{
      width: 36, height: 36, borderRadius: 10, border: "1px solid var(--border)",
      background: "var(--bg-surface)", color: "var(--fg-secondary)", cursor: "pointer",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <Ic name="arrow-left" size={16}/>
    </button>
    <div style={{
      width: 44, height: 44, borderRadius: 12,
      background: `${accent}1F`, color: accent,
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <Ic name={icon} size={22}/>
    </div>
    <div style={{ flex: 1 }}>
      <h1 style={{ fontSize: 24, fontWeight: 800, letterSpacing: "-0.015em", color: "var(--fg-primary)" }}>{title}</h1>
      <div style={{ fontSize: 13, color: "var(--fg-secondary)", marginTop: 2 }}>{subtitle}</div>
    </div>
    {actions}
    {badge && (
      <span style={{
        padding: "6px 12px", borderRadius: 999, fontSize: 11, fontWeight: 700,
        background: `${accent}1F`, color: accent, letterSpacing: "0.02em",
      }}>{badge}</span>
    )}
    <button style={{
      padding: "8px 14px", borderRadius: 10, border: "1px solid var(--border)",
      background: "var(--bg-surface)", color: "var(--fg-primary)",
      fontFamily: "inherit", fontSize: 12, fontWeight: 600, cursor: "pointer",
      display: "flex", alignItems: "center", gap: 6,
    }}>
      <Ic name="download" size={13}/>
      エクスポート
    </button>
  </div>
);

// ── Chart frame: 「크게 보기」 + コピー ─────────────────────
const ChartFrame = ({ title, subtitle, accent = "var(--c-spot)", actions, children, modalContent }) => {
  const [open, setOpen] = dS(false);
  const [copied, setCopied] = dS(false);
  const ref = dR(null);

  const copyChart = async () => {
    try {
      const node = ref.current?.querySelector("svg");
      if (!node) return;
      const xml = new XMLSerializer().serializeToString(node);
      // try image copy first
      const svgBlob = new Blob([xml], { type: "image/svg+xml" });
      const url = URL.createObjectURL(svgBlob);
      const img = new Image();
      img.onload = async () => {
        const canvas = document.createElement("canvas");
        canvas.width = node.viewBox.baseVal.width || node.clientWidth;
        canvas.height = node.viewBox.baseVal.height || node.clientHeight;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#fff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0);
        canvas.toBlob(async (blob) => {
          try {
            await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
          } catch {
            // fallback: copy SVG XML as text
            await navigator.clipboard.writeText(xml);
          }
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        });
        URL.revokeObjectURL(url);
      };
      img.src = url;
    } catch (e) {
      console.warn("copy failed", e);
    }
  };

  return (
    <>
      <div ref={ref} style={{
        background: "var(--bg-surface)", borderRadius: 18, padding: 22,
        border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
      }}>
        <div style={{ display: "flex", alignItems: "center", marginBottom: 14, gap: 10 }}>
          <div style={{ flex: 1 }}>
            {title && <div style={{ fontSize: 16, fontWeight: 700, color: "var(--fg-primary)" }}>{title}</div>}
            {subtitle && <div style={{ fontSize: 12, color: "var(--fg-secondary)" }}>{subtitle}</div>}
          </div>
          {actions}
          <button onClick={copyChart} title="グラフをコピー" style={iconBtn}>
            {copied ? <span style={{ fontSize: 11, fontWeight: 700, color: "var(--c-ok)" }}>✓ コピー</span>
                    : <Ic name="copy" size={14}/>}
          </button>
          <button onClick={() => setOpen(true)} title="拡大表示" style={iconBtn}>
            <Ic name="expand" size={14}/>
          </button>
        </div>
        {children}
      </div>

      {open && (
        <div onClick={() => setOpen(false)} style={modalOverlay}>
          <div onClick={e => e.stopPropagation()} style={modalBox}>
            <div style={{
              display: "flex", alignItems: "center", padding: "16px 22px",
              borderBottom: "1px solid var(--border-subtle)",
            }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 18, fontWeight: 800 }}>{title}</div>
                {subtitle && <div style={{ fontSize: 12, color: "var(--fg-secondary)", marginTop: 2 }}>{subtitle}</div>}
              </div>
              <button onClick={copyChart} style={modalBtn}>
                {copied ? "✓ コピー済み" : "📋 グラフをコピー"}
              </button>
              <button onClick={() => setOpen(false)} style={{ ...modalBtn, marginLeft: 8 }}>
                ✕ 閉じる
              </button>
            </div>
            <div style={{ padding: 24, overflow: "auto", flex: 1 }}>
              {modalContent || children}
            </div>
          </div>
        </div>
      )}
    </>
  );
};

const iconBtn = {
  width: 32, height: 32, borderRadius: 8, border: "1px solid var(--border)",
  background: "var(--bg-surface-2)", color: "var(--fg-secondary)", cursor: "pointer",
  display: "flex", alignItems: "center", justifyContent: "center",
  padding: "0 10px", minWidth: 32,
};
const modalOverlay = {
  position: "fixed", inset: 0, zIndex: 1000,
  background: "rgba(0,0,0,0.5)", backdropFilter: "blur(8px)",
  display: "flex", alignItems: "center", justifyContent: "center",
  animation: "fadeIn 0.2s ease",
};
const modalBox = {
  width: "92vw", maxWidth: 1480, height: "88vh",
  background: "var(--bg-surface)", borderRadius: 18,
  display: "flex", flexDirection: "column",
  boxShadow: "0 20px 60px rgba(0,0,0,0.4)",
  border: "1px solid var(--border-subtle)",
  animation: "scaleIn 0.22s ease",
};
const modalBtn = {
  padding: "8px 14px", borderRadius: 10, border: "1px solid var(--border)",
  background: "var(--bg-surface-2)", color: "var(--fg-primary)",
  fontFamily: "inherit", fontSize: 12, fontWeight: 600, cursor: "pointer",
};

window.varA_detail_atoms = { BigChart, KPI, DetailHeader, ChartFrame };
