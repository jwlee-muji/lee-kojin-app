/* global React, Ic */
// ============================================================
// Variation A — Animated Weather Illustration
// (porting the Python QPainter version to SVG)
// ============================================================

const { useEffect, useRef, useState: useStateW } = React;

const WeatherIllust = ({ category, isDark, w = 140, h = 100 }) => {
  const [phase, setPhase] = useStateW(0);
  const [flash, setFlash] = useStateW(0);
  const rafRef = useRef();
  useEffect(() => {
    let last = 0;
    const tick = (t) => {
      if (t - last > 60) {
        setPhase((p) => (p + 0.05) % (Math.PI * 2));
        if (category === "stormy") {
          setFlash((f) => {
            if (Math.random() < 0.04) return 1;
            return Math.max(0, f - 0.18);
          });
        }
        last = t;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [category]);

  const cloudColor = isDark ? "rgba(180,185,200,0.85)" : "rgba(140,150,170,0.65)";
  const heavyCloudColor = isDark ? "rgba(110,125,155,0.95)" : "rgba(80,95,125,0.7)";
  const stormCloudColor = isDark ? "rgba(55,60,78,0.92)" : "rgba(75,80,100,0.8)";

  const cloudPath = (cx, cy, r) => {
    const parts = [
      [0, 0, 1.0, 0.7],
      [-0.6, 0.1, 0.6, 0.55],
      [0.6, 0.1, 0.65, 0.5],
      [-0.2, -0.4, 0.55, 0.5],
      [0.35, -0.28, 0.5, 0.45],
    ];
    return parts.map(([dx, dy, rx, ry], i) => (
      <ellipse key={i} cx={cx + dx * r} cy={cy + dy * r} rx={rx * r} ry={ry * r}/>
    ));
  };

  const renderSun = (sx, sy, r, nRays = 8, rayLen = 0.9, alpha = 0.9) => {
    const ri = r + r * 0.25;
    const ro = r + r * rayLen;
    const rays = [];
    for (let i = 0; i < nRays; i++) {
      const a = phase + i * (Math.PI * 2 / nRays);
      rays.push(
        <line key={i}
          x1={sx + ri * Math.cos(a)} y1={sy + ri * Math.sin(a)}
          x2={sx + ro * Math.cos(a)} y2={sy + ro * Math.sin(a)}
          stroke="rgba(255,200,50,0.65)" strokeWidth={Math.max(2, r * 0.18)} strokeLinecap="round"
        />
      );
    }
    return (
      <g>
        {rays}
        <circle cx={sx} cy={sy} r={r} fill={`rgba(255,210,40,${alpha})`}/>
      </g>
    );
  };

  const renderClear = () => {
    const r = Math.min(w, h) * 0.18;
    return renderSun(w * 0.5, h * 0.5, r, 8, 0.85);
  };

  const renderMostlyClear = () => {
    const r = Math.min(w, h) * 0.16;
    const cr = Math.min(w, h) * 0.14;
    const bob = Math.sin(phase * 0.6) * (h * 0.012);
    return (
      <g>
        {renderSun(w * 0.42, h * 0.42, r, 8, 0.7)}
        <g fill={cloudColor}>{cloudPath(w * 0.67, h * 0.62 + bob, cr)}</g>
      </g>
    );
  };

  const renderPartlyCloudy = () => {
    const r = Math.min(w, h) * 0.14;
    const cr = Math.min(w, h) * 0.22;
    const bob = Math.sin(phase * 0.5) * (h * 0.012);
    return (
      <g>
        {renderSun(w * 0.35, h * 0.34, r, 6, 0.6, 0.75)}
        <g fill={cloudColor}>{cloudPath(w * 0.55, h * 0.5 + bob, cr)}</g>
      </g>
    );
  };

  const renderCloudy = () => {
    const r = Math.min(w, h) * 0.24;
    const sy = h * 0.5 + Math.sin(phase * 0.5) * (h * 0.015);
    return <g fill={cloudColor}>{cloudPath(w * 0.5, sy, r)}</g>;
  };

  const renderRainBase = (n, dropAlpha, cloudAlpha, dropScale = 1, cloudY = 0.36) => {
    const cx = w * 0.5;
    const r = Math.min(w, h) * 0.22;
    const cy = h * cloudY;
    const span = w * 0.55;
    const fall = h - cy - r * 0.6;
    const dlen = h * 0.07 * dropScale;
    const drops = [];
    for (let i = 0; i < n; i++) {
      const t = ((phase * 1.5 + i * (Math.PI * 2 / n)) % (Math.PI * 2)) / (Math.PI * 2);
      const x = cx + ((i / Math.max(n - 1, 1)) - 0.5) * span;
      const y = cy + r * 0.55 + t * fall;
      drops.push(
        <line key={i} x1={x} y1={y} x2={x - dlen * 0.2} y2={y + dlen}
          stroke={`rgba(100,160,225,${dropAlpha})`}
          strokeWidth={Math.max(1.5, r * 0.07) * dropScale}
          strokeLinecap="round"/>
      );
    }
    return (
      <g>
        <g fill={`rgba(${isDark ? "100,120,160" : "85,105,145"},${cloudAlpha})`}>{cloudPath(cx, cy, r)}</g>
        {drops}
      </g>
    );
  };

  const renderSnowBase = (n, alpha, cloudAlpha, flakeScale = 1) => {
    const cx = w * 0.5;
    const r = Math.min(w, h) * 0.22;
    const cy = h * 0.34;
    const span = w * 0.6;
    const fr = Math.max(2, Math.min(w, h) * 0.025 * flakeScale);
    const fall = h - cy - r * 0.5;
    const flakes = [];
    for (let i = 0; i < n; i++) {
      const t = ((phase * 1.1 + i * (Math.PI * 2 / n)) % (Math.PI * 2)) / (Math.PI * 2);
      const x = cx + ((i / Math.max(n - 1, 1)) - 0.5) * span + Math.sin(phase * 0.5 + i * 1.4) * (w * 0.025);
      const y = cy + r * 0.5 + t * fall;
      flakes.push(<circle key={i} cx={x} cy={y} r={fr} fill={`rgba(205,225,248,${alpha})`}/>);
    }
    return (
      <g>
        <g fill={`rgba(${isDark ? "140,155,175" : "120,135,160"},${cloudAlpha})`}>{cloudPath(cx, cy, r)}</g>
        {flakes}
      </g>
    );
  };

  const renderStormy = () => {
    const cx = w * 0.5;
    const r = Math.min(w, h) * 0.24;
    const cy = h * 0.3;
    const bw = w * 0.085;
    const by0 = cy + r * 0.35;
    const bym = h * 0.6;
    const by1 = h * 0.82;
    const path = `M ${cx + bw} ${by0} L ${cx - bw} ${bym} L ${cx + bw * 0.3} ${bym} L ${cx - bw * 1.3} ${by1}`;
    return (
      <g>
        <g fill={stormCloudColor}>{cloudPath(cx, cy, r)}</g>
        {flash > 0.15 && (
          <path d={path} fill="none" stroke={`rgba(255,255,200,${0.7 * flash})`} strokeWidth={Math.max(7, bw * 1.8)} strokeLinejoin="round"/>
        )}
        <path d={path} fill="none" stroke={`rgba(255,235,50,${0.78 + 0.22 * flash})`} strokeWidth={Math.max(2.5, bw * 0.4)} strokeLinejoin="round"/>
      </g>
    );
  };

  const renderers = {
    clear: renderClear,
    mostly_clear: renderMostlyClear,
    partly_cloudy: renderPartlyCloudy,
    cloudy: renderCloudy,
    foggy: renderCloudy,
    drizzle: () => renderRainBase(5, 0.5, 0.7, 0.75),
    rainy:   () => renderRainBase(9, 0.78, 0.85),
    heavy_rain: () => renderRainBase(14, 0.9, 0.92, 1.25, 0.3),
    light_snow: () => renderSnowBase(5, 0.7, 0.7, 0.8),
    snowy:      () => renderSnowBase(8, 0.85, 0.8),
    heavy_snow: () => renderSnowBase(13, 0.9, 0.9, 1.2),
    stormy: renderStormy,
  };
  const render = renderers[category] || renderClear;

  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      {render()}
    </svg>
  );
};

window.WeatherIllust = WeatherIllust;
