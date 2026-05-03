/* global React */
// ============================================================
// Mini Calendar — 共通の日付ピッカー
// 単日 (DateInput) と 期間 (DateRangeInput)
// ============================================================
const { useState: dpS, useEffect: dpE, useRef: dpR } = React;

const PAD = (n) => String(n).padStart(2, "0");
const fmtISO = (d) => `${d.getFullYear()}-${PAD(d.getMonth() + 1)}-${PAD(d.getDate())}`;
const fmtJP = (s) => {
  if (!s) return "";
  const d = new Date(s);
  return `${d.getFullYear()}/${PAD(d.getMonth() + 1)}/${PAD(d.getDate())}`;
};
const parseISO = (s) => {
  if (!s) return new Date();
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
};
const sameDay = (a, b) => a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
const inRange = (d, s, e) => {
  if (!s || !e) return false;
  const t = d.getTime();
  return t >= s.getTime() && t <= e.getTime();
};

// 月のセル (前後グレー含む 6週)
const monthCells = (year, month) => {
  const first = new Date(year, month, 1);
  const startOffset = first.getDay(); // 0=日
  const cells = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(year, month, 1 - startOffset + i);
    cells.push({ d, inMonth: d.getMonth() === month });
  }
  return cells;
};

const WEEKDAYS = ["日", "月", "火", "水", "木", "金", "土"];

// =========================================================
// Calendar popup (内部用)
// =========================================================
const CalendarPopup = ({ value, range, onSelect, onClose, accent = "var(--c-spot)" }) => {
  const initial = range
    ? (range[0] ? parseISO(range[0]) : new Date(2026, 4, 1))
    : (value ? parseISO(value) : new Date(2026, 4, 1));
  const [view, setView] = dpS({ y: initial.getFullYear(), m: initial.getMonth() });
  const [hoverEnd, setHoverEnd] = dpS(null); // 範囲選択 中の end プレビュー

  const cells = monthCells(view.y, view.m);
  const valDate = value ? parseISO(value) : null;
  const start = range && range[0] ? parseISO(range[0]) : null;
  const end = range && range[1] ? parseISO(range[1]) : null;

  const goM = (delta) => {
    const m2 = view.m + delta;
    setView({ y: view.y + Math.floor(m2 / 12), m: ((m2 % 12) + 12) % 12 });
  };
  const goY = (delta) => setView({ ...view, y: view.y + delta });

  const handleClick = (d) => {
    if (range) {
      // 範囲モード: 1回目=start, 2回目=end
      if (!start || (start && end)) {
        onSelect([fmtISO(d), null]);
      } else {
        if (d < start) {
          onSelect([fmtISO(d), fmtISO(start)]);
        } else {
          onSelect([fmtISO(start), fmtISO(d)]);
        }
        onClose();
      }
    } else {
      onSelect(fmtISO(d));
      onClose();
    }
  };

  const today = new Date();

  return (
    <div style={{
      position: "absolute", top: "calc(100% + 6px)", left: 0, zIndex: 100,
      background: "var(--bg-surface)", borderRadius: 14, padding: 14,
      boxShadow: "0 10px 36px rgba(0,0,0,0.18), 0 2px 8px rgba(0,0,0,0.08)",
      border: "1px solid var(--border-subtle)",
      minWidth: 280,
      animation: "calPop 0.15s ease-out",
    }}
    onClick={(e) => e.stopPropagation()}>
      {/* header */}
      <div style={{ display: "flex", alignItems: "center", marginBottom: 10 }}>
        <button onClick={() => goY(-1)} style={navBtn} title="前年">«</button>
        <button onClick={() => goM(-1)} style={navBtn} title="前月">‹</button>
        <div style={{ flex: 1, textAlign: "center", fontSize: 13, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>
          {view.y}年 {view.m + 1}月
        </div>
        <button onClick={() => goM(1)} style={navBtn} title="次月">›</button>
        <button onClick={() => goY(1)} style={navBtn} title="次年">»</button>
      </div>

      {/* weekday header */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2, marginBottom: 4 }}>
        {WEEKDAYS.map((w, i) => (
          <div key={w} style={{
            fontSize: 10, textAlign: "center", fontWeight: 700,
            color: i === 0 ? "#EF4444" : i === 6 ? "#3B82F6" : "var(--fg-tertiary)",
            paddingBottom: 4,
          }}>{w}</div>
        ))}
      </div>

      {/* day cells */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2 }}>
        {cells.map((c, i) => {
          const isToday = sameDay(c.d, today);
          const isSelected = !range && valDate && sameDay(c.d, valDate);
          const isStart = range && start && sameDay(c.d, start);
          const isEnd = range && end && sameDay(c.d, end);
          const previewEnd = range && start && !end && hoverEnd && sameDay(c.d, hoverEnd);
          const inSel = range && start && (end || hoverEnd) && inRange(c.d, start, end || hoverEnd);
          const dim = !c.inMonth;
          const dow = c.d.getDay();

          let bg = "transparent";
          let color = dim ? "var(--fg-tertiary)" : (dow === 0 ? "#EF4444" : dow === 6 ? "#3B82F6" : "var(--fg-primary)");
          let weight = 600;

          if (isSelected || isStart || isEnd || previewEnd) {
            bg = accent; color = "#fff"; weight = 800;
          } else if (inSel) {
            bg = `color-mix(in srgb, ${accent} 18%, transparent)`;
            weight = 700;
          }

          return (
            <button key={i}
              onClick={() => handleClick(c.d)}
              onMouseEnter={() => range && start && !end && setHoverEnd(c.d)}
              onMouseLeave={() => setHoverEnd(null)}
              style={{
                aspectRatio: "1", border: 0, borderRadius: 7, cursor: "pointer",
                fontFamily: "inherit", fontSize: 11, fontWeight: weight,
                fontVariantNumeric: "tabular-nums",
                background: bg, color,
                opacity: dim ? 0.4 : 1,
                position: "relative",
                outline: isToday && !isSelected && !isStart && !isEnd ? `1.5px solid ${accent}` : "none",
                outlineOffset: -2,
                transition: "background 0.1s",
              }}
              onMouseDown={(e) => e.preventDefault()}>
              {c.d.getDate()}
            </button>
          );
        })}
      </div>

      {/* footer shortcuts */}
      <div style={{ display: "flex", gap: 6, marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border-subtle)", flexWrap: "wrap" }}>
        <button style={shortcut(accent)} onClick={() => {
          const t = new Date();
          if (range) { onSelect([fmtISO(t), fmtISO(t)]); onClose(); }
          else { onSelect(fmtISO(t)); onClose(); }
        }}>今日</button>
        {range && (
          <>
            <button style={shortcut(accent)} onClick={() => {
              const e = new Date();
              const s = new Date(); s.setDate(s.getDate() - 6);
              onSelect([fmtISO(s), fmtISO(e)]); onClose();
            }}>過去7日</button>
            <button style={shortcut(accent)} onClick={() => {
              const e = new Date();
              const s = new Date(); s.setDate(s.getDate() - 29);
              onSelect([fmtISO(s), fmtISO(e)]); onClose();
            }}>過去30日</button>
            <button style={shortcut(accent)} onClick={() => {
              const t = new Date();
              const s = new Date(t.getFullYear(), t.getMonth(), 1);
              const e = new Date(t.getFullYear(), t.getMonth() + 1, 0);
              onSelect([fmtISO(s), fmtISO(e)]); onClose();
            }}>今月</button>
          </>
        )}
        <div style={{ flex: 1 }}/>
        <button style={shortcut(accent, true)} onClick={onClose}>閉じる</button>
      </div>

      <style>{`@keyframes calPop { from { opacity: 0; transform: translateY(-4px) scale(0.97); } to { opacity: 1; transform: none; } }`}</style>
    </div>
  );
};

const navBtn = {
  border: 0, background: "transparent", cursor: "pointer",
  fontFamily: "inherit", fontSize: 13, fontWeight: 700,
  color: "var(--fg-secondary)", padding: "4px 8px", borderRadius: 6,
};
const shortcut = (accent, ghost) => ({
  fontFamily: "inherit", fontSize: 10, fontWeight: 700,
  padding: "4px 9px", borderRadius: 6, cursor: "pointer",
  border: ghost ? "1px solid var(--border)" : 0,
  background: ghost ? "transparent" : `color-mix(in srgb, ${accent} 14%, transparent)`,
  color: ghost ? "var(--fg-secondary)" : accent,
});

// =========================================================
// DateInput — 単日
// =========================================================
const DateInput = ({ value, onChange, accent = "var(--c-spot)", placeholder = "日付を選択", style = {} }) => {
  const [open, setOpen] = dpS(false);
  const ref = dpR(null);

  dpE(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button onClick={() => setOpen(o => !o)} style={{
        padding: "7px 12px", borderRadius: 9,
        border: `1px solid ${open ? accent : "var(--border)"}`,
        background: "var(--bg-surface)", color: "var(--fg-primary)",
        fontFamily: "inherit", fontSize: 12, fontWeight: 600,
        cursor: "pointer",
        display: "inline-flex", alignItems: "center", gap: 8,
        fontVariantNumeric: "tabular-nums",
        transition: "border-color 0.15s",
        ...style,
      }}>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={accent} strokeWidth="2.4">
          <rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>
        </svg>
        {value ? fmtJP(value) : placeholder}
        <span style={{ color: "var(--fg-tertiary)", fontSize: 9 }}>▾</span>
      </button>
      {open && <CalendarPopup value={value} onSelect={onChange} onClose={() => setOpen(false)} accent={accent}/>}
    </div>
  );
};

// =========================================================
// DateRangeInput — 期間
// =========================================================
const DateRangeInput = ({ value = [null, null], onChange, accent = "var(--c-spot)", style = {} }) => {
  const [open, setOpen] = dpS(false);
  const ref = dpR(null);

  dpE(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const display = value[0] && value[1]
    ? `${fmtJP(value[0])} 〜 ${fmtJP(value[1])}`
    : value[0] ? `${fmtJP(value[0])} 〜 ?` : "期間を選択";

  // 日数
  let days = null;
  if (value[0] && value[1]) {
    days = Math.round((parseISO(value[1]) - parseISO(value[0])) / 86400000) + 1;
  }

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button onClick={() => setOpen(o => !o)} style={{
        padding: "7px 12px", borderRadius: 9,
        border: `1px solid ${open ? accent : "var(--border)"}`,
        background: "var(--bg-surface)", color: "var(--fg-primary)",
        fontFamily: "inherit", fontSize: 12, fontWeight: 600,
        cursor: "pointer",
        display: "inline-flex", alignItems: "center", gap: 8,
        fontVariantNumeric: "tabular-nums",
        transition: "border-color 0.15s",
        ...style,
      }}>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={accent} strokeWidth="2.4">
          <rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>
        </svg>
        {display}
        {days != null && (
          <span style={{
            padding: "1px 7px", borderRadius: 999,
            background: `color-mix(in srgb, ${accent} 18%, transparent)`,
            color: accent, fontSize: 10, fontWeight: 700,
          }}>{days}日</span>
        )}
        <span style={{ color: "var(--fg-tertiary)", fontSize: 9 }}>▾</span>
      </button>
      {open && <CalendarPopup range={value} onSelect={onChange} onClose={() => setOpen(false)} accent={accent}/>}
    </div>
  );
};

window.varA_datepicker = { DateInput, DateRangeInput, fmtISO, fmtJP, parseISO };
