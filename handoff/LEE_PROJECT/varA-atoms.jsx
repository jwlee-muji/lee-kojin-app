/* global React, Ic */
// ============================================================
// Variation A — Apple Energy / iOS Widget Style
// Rounded, colorful, soft shadows, friendly
// ============================================================

const { useState, useEffect, useRef, useMemo } = React;
const D = window.LEE_DATA;

// ─────────────────────────────────────────────────────────────
// Shared atoms
// ─────────────────────────────────────────────────────────────

const Card = ({ children, className = "", style = {}, padding = 24, accent, onClick }) => (
  <div
    onClick={onClick}
    className={`varA-card ${className}`}
    style={{
      background: "var(--bg-surface)",
      borderRadius: "var(--r-xl)",
      border: "1px solid var(--border-subtle)",
      padding,
      boxShadow: "var(--shadow-sm)",
      position: "relative",
      overflow: "hidden",
      cursor: onClick ? "pointer" : "default",
      transition: "transform 0.2s ease, box-shadow 0.2s ease",
      ...style,
    }}
  >
    {accent && (
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: 4,
        background: accent, borderRadius: "var(--r-xl) var(--r-xl) 0 0",
      }}/>
    )}
    {children}
  </div>
);

const IconTile = ({ name, color, size = 40, iconSize = 20 }) => (
  <div style={{
    width: size, height: size,
    borderRadius: 12,
    background: `${color}1F`,
    color: color,
    display: "flex", alignItems: "center", justifyContent: "center",
    flexShrink: 0,
  }}>
    <Ic name={name} size={iconSize}/>
  </div>
);

const Pill = ({ children, color, soft = true, style = {} }) => (
  <span style={{
    display: "inline-flex", alignItems: "center", gap: 4,
    padding: "3px 10px",
    borderRadius: 999,
    fontSize: 11, fontWeight: 600,
    background: soft ? `${color}1F` : color,
    color: soft ? color : "#fff",
    letterSpacing: "0.01em",
    ...style,
  }}>{children}</span>
);

const Trend = ({ v }) => {
  const up = v > 0;
  const c = up ? "var(--c-bad)" : "var(--c-ok)";
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 2, color: c, fontSize: 12, fontWeight: 700 }}>
      <Ic name={up ? "arrow-up" : "arrow-down"} size={11} stroke={2.5}/>
      {Math.abs(v).toFixed(1)}
    </span>
  );
};

// Sparkline SVG
const Sparkline = ({ data, color, w = 180, h = 44, fill = true }) => {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => [
    (i / (data.length - 1)) * w,
    h - ((v - min) / range) * (h - 4) - 2,
  ]);
  const d = "M " + pts.map(p => p.join(",")).join(" L ");
  const area = d + ` L ${w},${h} L 0,${h} Z`;
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      <defs>
        <linearGradient id={`spark-${color.slice(1)}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35"/>
          <stop offset="100%" stopColor={color} stopOpacity="0"/>
        </linearGradient>
      </defs>
      {fill && <path d={area} fill={`url(#spark-${color.slice(1)})`}/>}
      <path d={d} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
};

// Animated counter
const useCountUp = (target, duration = 900) => {
  const [v, setV] = useState(0);
  const startRef = useRef(null);
  useEffect(() => {
    let raf;
    const step = (t) => {
      if (!startRef.current) startRef.current = t;
      const p = Math.min(1, (t - startRef.current) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setV(target * eased);
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return v;
};

const CountValue = ({ target, format = (v) => v.toFixed(2), style = {} }) => {
  const v = useCountUp(target);
  return <span style={style}>{format(v)}</span>;
};

window.varA_atoms = { Card, IconTile, Pill, Trend, Sparkline, CountValue, useCountUp };
