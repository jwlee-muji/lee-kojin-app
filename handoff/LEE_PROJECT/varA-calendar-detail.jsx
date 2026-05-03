/* global React */
// ============================================================
// LEE — Calendar Detail (full-featured)
//   • Month grid with day boxes
//   • Multi-day event spans (rendered as bars across cells)
//   • Drag & drop to move events
//   • Edge-resize to extend / shrink span
//   • Ghost preview while dragging / resizing
//   • Calendar visibility filters, week-start setting,
//     view switcher (month / week / day stub), toolbar
// ============================================================
const { useState: calS, useMemo: calM, useRef: calR, useEffect: calE } = React;
const { DetailHeader: CAL_DH } = window.varA_detail_atoms;
const CAL_D = window.LEE_DATA;

// ── Date helpers ────────────────────────────────────────────
const ymd = (d) => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
};
const parseYMD = (s) => {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
};
const addDays = (d, n) => {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
};
const diffDays = (a, b) => Math.round((parseYMD(b) - parseYMD(a)) / 86400000);

// Build month-grid (weeks × 7 days). startWeekday: 0=Sun, 1=Mon
const buildGrid = (year, month, startWeekday) => {
  const first = new Date(year, month, 1);
  const offset = (first.getDay() - startWeekday + 7) % 7;
  const start = addDays(first, -offset);
  const cells = [];
  for (let i = 0; i < 42; i++) {
    const d = addDays(start, i);
    cells.push({
      date: d,
      ymd: ymd(d),
      day: d.getDate(),
      month: d.getMonth(),
      isCurMonth: d.getMonth() === month,
      isToday: ymd(d) === ymd(new Date(2025, 0, 22)), // pinned "today"
      weekday: d.getDay(),
    });
  }
  return cells;
};

// Compute, for each visible week, the list of event-bars to render with
// their start column, span (days), and assigned row (lane) — using a
// simple greedy lane-packer so overlapping events stack vertically.
const layoutWeek = (weekCells, events) => {
  const weekStart = weekCells[0].ymd;
  const weekEnd = weekCells[6].ymd;
  // Filter events that intersect this week
  const visible = events
    .filter((e) => e.end >= weekStart && e.start <= weekEnd)
    .map((e) => {
      const startCol = Math.max(0, diffDays(weekStart, e.start));
      const endCol = Math.min(6, diffDays(weekStart, e.end));
      return { ...e, startCol, span: endCol - startCol + 1 };
    })
    .sort((a, b) => {
      if (a.startCol !== b.startCol) return a.startCol - b.startCol;
      return b.span - a.span;
    });

  // Greedy lane assignment
  const lanes = []; // each lane: array of { startCol, endCol }
  visible.forEach((ev) => {
    let lane = 0;
    while (true) {
      const used = lanes[lane] || [];
      const conflict = used.some(
        (u) => !(ev.startCol > u.endCol || ev.startCol + ev.span - 1 < u.startCol)
      );
      if (!conflict) {
        if (!lanes[lane]) lanes[lane] = [];
        lanes[lane].push({ startCol: ev.startCol, endCol: ev.startCol + ev.span - 1 });
        ev.lane = lane;
        break;
      }
      lane++;
    }
  });
  return visible;
};

// ── Mini header with view tabs / nav ────────────────────────
const CalToolbar = ({ year, month, view, setView, onPrev, onNext, onToday, onAdd }) => (
  <div style={{
    display: "flex", alignItems: "center", gap: 12, padding: "14px 18px",
    background: "var(--bg-surface)", borderRadius: 14,
    border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
    marginBottom: 14,
  }}>
    <div style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.01em" }}>
      {year}年 {month + 1}月
    </div>

    <div style={{ display: "flex", gap: 4, marginLeft: 12 }}>
      {[["<", onPrev], ["今日", onToday], [">", onNext]].map(([lbl, fn], i) => (
        <button key={i} onClick={fn} style={{
          padding: i === 1 ? "6px 14px" : "6px 10px",
          borderRadius: 8, border: "1px solid var(--border)",
          background: i === 1 ? "#34C759" : "var(--bg-surface)",
          color: i === 1 ? "#fff" : "var(--fg-primary)",
          fontFamily: "inherit", fontSize: 12, fontWeight: 700, cursor: "pointer",
        }}>{lbl}</button>
      ))}
    </div>

    <div style={{ flex: 1 }} />

    <div style={{
      display: "flex", padding: 3, gap: 2,
      background: "var(--bg-surface-2)", borderRadius: 10,
      border: "1px solid var(--border-subtle)",
    }}>
      {["月", "週", "日"].map((v, i) => {
        const k = ["month", "week", "day"][i];
        const on = view === k;
        return (
          <button key={k} onClick={() => setView(k)} style={{
            padding: "5px 14px", borderRadius: 7, border: 0,
            background: on ? "#34C759" : "transparent",
            color: on ? "#fff" : "var(--fg-secondary)",
            fontFamily: "inherit", fontSize: 11, fontWeight: 700, cursor: "pointer",
          }}>{v}</button>
        );
      })}
    </div>

    <button onClick={onAdd} style={{
      padding: "8px 14px", borderRadius: 10, border: 0,
      background: "#34C759", color: "#fff",
      fontFamily: "inherit", fontSize: 12, fontWeight: 800, cursor: "pointer",
      display: "flex", alignItems: "center", gap: 6,
    }}>
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round">
        <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
      </svg>
      予定を追加
    </button>
  </div>
);

// ── Sidebar: calendar visibility + settings ─────────────────
const CalSidebar = ({ calendars, toggleCal, weekStart, setWeekStart, showWeek, setShowWeek, eventsToday }) => (
  <div style={{
    background: "var(--bg-surface)", borderRadius: 18, padding: 18,
    border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
    display: "flex", flexDirection: "column", gap: 18,
  }}>
    <div>
      <div style={{ fontSize: 11, fontWeight: 800, color: "var(--fg-tertiary)", letterSpacing: "0.08em", marginBottom: 10 }}>
        マイカレンダー
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {calendars.map((c) => (
          <label key={c.id} style={{
            display: "flex", alignItems: "center", gap: 10, padding: "6px 8px",
            borderRadius: 8, cursor: "pointer",
            background: c.visible ? "transparent" : "var(--bg-surface-2)",
          }}>
            <span style={{
              width: 16, height: 16, borderRadius: 5,
              background: c.visible ? c.color : "transparent",
              border: `2px solid ${c.color}`,
              display: "flex", alignItems: "center", justifyContent: "center",
              flexShrink: 0,
            }}>
              {c.visible && (
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
              )}
            </span>
            <span style={{
              fontSize: 12, fontWeight: 600,
              color: c.visible ? "var(--fg-primary)" : "var(--fg-tertiary)",
            }}>{c.id}</span>
            <input type="checkbox" checked={c.visible} onChange={() => toggleCal(c.id)} style={{ display: "none" }} />
          </label>
        ))}
      </div>
    </div>

    <div>
      <div style={{ fontSize: 11, fontWeight: 800, color: "var(--fg-tertiary)", letterSpacing: "0.08em", marginBottom: 10 }}>
        表示設定
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 12, fontWeight: 600 }}>週の開始</span>
          <div style={{
            display: "flex", padding: 2, gap: 1,
            background: "var(--bg-surface-2)", borderRadius: 7,
            border: "1px solid var(--border-subtle)",
          }}>
            {[["日", 0], ["月", 1]].map(([lbl, v]) => (
              <button key={v} onClick={() => setWeekStart(v)} style={{
                padding: "4px 12px", borderRadius: 5, border: 0,
                background: weekStart === v ? "#34C759" : "transparent",
                color: weekStart === v ? "#fff" : "var(--fg-secondary)",
                fontFamily: "inherit", fontSize: 11, fontWeight: 700, cursor: "pointer",
              }}>{lbl}</button>
            ))}
          </div>
        </div>
        <label style={{ display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer" }}>
          <span style={{ fontSize: 12, fontWeight: 600 }}>週番号を表示</span>
          <span onClick={() => setShowWeek(!showWeek)} style={{
            width: 34, height: 20, borderRadius: 999, padding: 2,
            background: showWeek ? "#34C759" : "var(--bg-surface-2)",
            border: "1px solid var(--border-subtle)",
            display: "flex", alignItems: "center",
            transition: "background 0.18s",
          }}>
            <span style={{
              width: 14, height: 14, borderRadius: 999, background: "#fff",
              boxShadow: "0 1px 2px rgba(0,0,0,.2)",
              transform: showWeek ? "translateX(14px)" : "translateX(0)",
              transition: "transform 0.18s",
            }} />
          </span>
        </label>
      </div>
    </div>

    <div>
      <div style={{ fontSize: 11, fontWeight: 800, color: "var(--fg-tertiary)", letterSpacing: "0.08em", marginBottom: 10 }}>
        本日の予定 ({eventsToday.length})
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 220, overflow: "auto" }}>
        {eventsToday.length === 0 && (
          <div style={{ fontSize: 11, color: "var(--fg-tertiary)", padding: "8px 0" }}>本日の予定はありません</div>
        )}
        {eventsToday.map((e) => (
          <div key={e.id} style={{
            padding: "8px 10px", borderRadius: 8,
            background: "var(--bg-surface-2)",
            borderLeft: `3px solid ${e.color}`,
          }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: e.color, marginBottom: 2, fontFamily: "var(--font-mono)" }}>
              {e.allDay ? "終日" : `${e.time}${e.endTime ? "-" + e.endTime : ""}`}
            </div>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--fg-primary)", lineHeight: 1.3 }}>{e.title}</div>
          </div>
        ))}
      </div>
    </div>
  </div>
);

// ── Event bar component ────────────────────────────────────
// Renders inside a week row, absolutely-positioned, spanning N columns
const EventBar = ({ ev, weekRow, totalLanes, onMouseDown, ghost, ghostCopy, selected, onClick, isContinuationLeft, isContinuationRight }) => {
  const top = 28 + ev.lane * 22; // below day-number row
  const left = `calc(${(ev.startCol / 7) * 100}% + 3px)`;
  const width = `calc(${(ev.span / 7) * 100}% - 6px)`;
  const showTime = !ev.allDay && ev.span === 1;

  return (
    <div
      onMouseDown={onMouseDown}
      onClick={(e) => { e.stopPropagation(); onClick && onClick(ev); }}
      style={{
        position: "absolute",
        top, left, width, height: 19,
        background: ghost ? `${ev.color}55` : ev.color,
        border: ghost ? `1.5px dashed ${ghostCopy ? "#34C759" : ev.color}` : "none",
        borderRadius: 4,
        borderTopLeftRadius: isContinuationLeft ? 0 : 4,
        borderBottomLeftRadius: isContinuationLeft ? 0 : 4,
        borderTopRightRadius: isContinuationRight ? 0 : 4,
        borderBottomRightRadius: isContinuationRight ? 0 : 4,
        color: "#fff", fontSize: 10, fontWeight: 700,
        padding: "2px 7px", cursor: "grab",
        display: "flex", alignItems: "center", gap: 4,
        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        boxShadow: selected ? "0 0 0 2px var(--fg-primary), 0 2px 6px rgba(0,0,0,.18)" : "0 1px 2px rgba(0,0,0,.08)",
        transition: ghost ? "none" : "transform 0.12s, box-shadow 0.12s",
        opacity: ghost ? 0.7 : 1,
        zIndex: ghost ? 100 : selected ? 50 : 10,
        userSelect: "none",
      }}
    >
      {/* Left resize handle (only for span start) */}
      {!isContinuationLeft && (
        <span data-handle="left" style={{
          position: "absolute", left: 0, top: 0, width: 5, height: "100%",
          cursor: "ew-resize", borderTopLeftRadius: 4, borderBottomLeftRadius: 4,
        }} />
      )}
      {showTime && <span style={{ opacity: 0.85, fontFamily: "var(--font-mono)" }}>{ev.time}</span>}
      <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{ev.title}</span>
      {ev.allDay && ev.span > 1 && (
        <span style={{ marginLeft: "auto", opacity: 0.8, fontSize: 9 }}>
          {isContinuationLeft ? "←" : ""}{isContinuationRight ? "→" : ""}
        </span>
      )}
      {ghost && ghostCopy && (
        <span style={{
          position: "absolute", right: -6, top: -6,
          width: 14, height: 14, borderRadius: 999,
          background: "#34C759", color: "#fff",
          fontSize: 10, fontWeight: 800,
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 1px 3px rgba(0,0,0,.25)",
          pointerEvents: "none",
        }}>+</span>
      )}
      {/* Right resize handle (only for span end) */}
      {!isContinuationRight && (
        <span data-handle="right" style={{
          position: "absolute", right: 0, top: 0, width: 5, height: "100%",
          cursor: "ew-resize", borderTopRightRadius: 4, borderBottomRightRadius: 4,
        }} />
      )}
    </div>
  );
};

// ── Main Calendar Detail ────────────────────────────────────
const tipKey = {
  display: "inline-block",
  padding: "1px 6px",
  borderRadius: 4,
  background: "var(--bg-surface-2)",
  border: "1px solid var(--border-subtle)",
  color: "var(--fg-secondary)",
  fontFamily: "var(--font-mono)",
  fontSize: 9, fontWeight: 700,
  letterSpacing: "0.02em",
};

const CalendarDetail = ({ onBack }) => {
  const meta = CAL_D.calendarMeta;
  const [year, setYear] = calS(2025);
  const [month, setMonth] = calS(0);
  const [view, setView] = calS(meta.defaultView);
  const [calendars, setCalendars] = calS(meta.calendars);
  const [weekStart, setWeekStart] = calS(meta.weekStart);
  const [showWeek, setShowWeek] = calS(meta.showWeekNumbers);
  const [events, setEvents] = calS(CAL_D.calendarEvents);
  const [selected, setSelected] = calS(null);
  const [drag, setDrag] = calS(null); // { id, mode, originX, originStart, originEnd, ghostStart, ghostEnd }
  const gridRef = calR(null);

  const visibleCals = calendars.filter((c) => c.visible).map((c) => c.id);
  const visibleEvents = events.filter((e) => visibleCals.includes(e.cal));

  const grid = calM(() => buildGrid(year, month, weekStart), [year, month, weekStart]);
  const weeks = calM(() => {
    const ws = [];
    for (let i = 0; i < 6; i++) ws.push(grid.slice(i * 7, i * 7 + 7));
    return ws;
  }, [grid]);

  const todayYMD = ymd(new Date(2025, 0, 22));
  const eventsToday = visibleEvents.filter((e) => e.start <= todayYMD && e.end >= todayYMD)
    .sort((a, b) => (a.allDay ? "00:00" : a.time).localeCompare(b.allDay ? "00:00" : b.time));

  const dayHeaders = ["日", "月", "火", "水", "木", "金", "土"];
  const orderedHeaders = [...dayHeaders.slice(weekStart), ...dayHeaders.slice(0, weekStart)];

  const toggleCal = (id) => setCalendars((cs) => cs.map((c) => c.id === id ? { ...c, visible: !c.visible } : c));

  const goPrev = () => { if (month === 0) { setMonth(11); setYear(year - 1); } else setMonth(month - 1); };
  const goNext = () => { if (month === 11) { setMonth(0); setYear(year + 1); } else setMonth(month + 1); };
  const goToday = () => { setYear(2025); setMonth(0); };

  // ── Drag / resize handlers ──
  const startDrag = (e, ev, mode) => {
    e.stopPropagation();
    e.preventDefault();
    if (!gridRef.current) return;
    const cellW = gridRef.current.getBoundingClientRect().width / 7;
    // Ctrl/Cmd + drag (only for "move") = copy
    const copyMode = mode === "move" && (e.ctrlKey || e.metaKey || e.altKey);
    setDrag({
      id: ev.id,
      mode, // "move" | "resize-left" | "resize-right"
      copy: copyMode,
      originX: e.clientX,
      originStart: ev.start,
      originEnd: ev.end,
      cellW,
      ghostStart: ev.start,
      ghostEnd: ev.end,
      moved: false,
    });
    setSelected(ev.id);
  };

  calE(() => {
    if (!drag) return;
    const onMove = (e) => {
      const dx = e.clientX - drag.originX;
      const dDays = Math.round(dx / drag.cellW);
      let newStart = drag.originStart;
      let newEnd = drag.originEnd;
      if (drag.mode === "move") {
        newStart = ymd(addDays(parseYMD(drag.originStart), dDays));
        newEnd = ymd(addDays(parseYMD(drag.originEnd), dDays));
      } else if (drag.mode === "resize-left") {
        newStart = ymd(addDays(parseYMD(drag.originStart), dDays));
        if (newStart > drag.originEnd) newStart = drag.originEnd;
      } else if (drag.mode === "resize-right") {
        newEnd = ymd(addDays(parseYMD(drag.originEnd), dDays));
        if (newEnd < drag.originStart) newEnd = drag.originStart;
      }
      setDrag((d) => ({ ...d, ghostStart: newStart, ghostEnd: newEnd, moved: newStart !== d.originStart || newEnd !== d.originEnd, copy: d.mode === "move" && (e.ctrlKey || e.metaKey || e.altKey) }));
    };
    const onUp = () => {
      setDrag((d) => {
        if (!d) return null;
        const moved = d.ghostStart !== d.originStart || d.ghostEnd !== d.originEnd;
        if (moved) {
          if (d.copy) {
            // Insert a duplicate at the new position; keep the original where it was
            setEvents((evs) => {
              const orig = evs.find((e) => e.id === d.id);
              if (!orig) return evs;
              const newId = `${orig.id}-copy-${Date.now()}`;
              const dup = { ...orig, id: newId, start: d.ghostStart, end: d.ghostEnd };
              return [...evs, dup];
            });
          } else {
            setEvents((evs) => evs.map((e) => e.id === d.id ? { ...e, start: d.ghostStart, end: d.ghostEnd } : e));
          }
        }
        return null;
      });
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [drag]);

  // ── Render ──
  const cellW100 = `calc(100% / 7)`;

  return (
    <div style={{ padding: 28 }}>
      <CAL_DH
        title="Google カレンダー"
        subtitle="今月の予定 · 同期 09:14"
        accent="#34C759"
        icon="calendar"
        onBack={onBack}
        badge={`${visibleEvents.length} 件`}
      />

      <div style={{ display: "grid", gridTemplateColumns: "230px 1fr", gap: 16 }}>
        {/* Left sidebar */}
        <CalSidebar
          calendars={calendars}
          toggleCal={toggleCal}
          weekStart={weekStart}
          setWeekStart={setWeekStart}
          showWeek={showWeek}
          setShowWeek={setShowWeek}
          eventsToday={eventsToday}
        />

        {/* Right: toolbar + grid */}
        <div>
          <CalToolbar
            year={year} month={month} view={view} setView={setView}
            onPrev={goPrev} onNext={goNext} onToday={goToday}
            onAdd={() => alert("予定追加 (デモ)")}
          />

          {/* Tip strip — drag/resize/copy hints */}
          <div style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "6px 4px 10px",
            fontSize: 10, color: "var(--fg-tertiary)",
            flexWrap: "wrap",
          }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <span style={tipKey}>Drag</span> 移動
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <span style={tipKey}>左右端 Drag</span> 期間調整
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <span style={tipKey}>{navigator.platform?.startsWith("Mac") ? "⌥" : "Ctrl"} + Drag</span> 複製
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <span style={tipKey}>Click</span> 選択
            </span>
            {drag && drag.copy && (
              <span style={{ marginLeft: "auto", color: "#34C759", fontWeight: 700, display: "inline-flex", alignItems: "center", gap: 4 }}>
                <span style={{ width: 12, height: 12, borderRadius: 999, background: "#34C759", color: "#fff", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 9, fontWeight: 800 }}>+</span>
                複製モード
              </span>
            )}
          </div>

          {view === "month" && (
            <div ref={gridRef} style={{
              background: "var(--bg-surface)", borderRadius: 14,
              border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
              overflow: "hidden",
            }}>
              {/* Day-of-week header */}
              <div style={{
                display: "grid", gridTemplateColumns: showWeek ? "32px repeat(7, 1fr)" : "repeat(7, 1fr)",
                background: "var(--bg-surface-2)",
                borderBottom: "1px solid var(--border-subtle)",
              }}>
                {showWeek && <div style={{ borderRight: "1px solid var(--border-subtle)" }} />}
                {orderedHeaders.map((d, i) => {
                  const realIdx = (i + weekStart) % 7;
                  return (
                    <div key={i} style={{
                      fontSize: 11, fontWeight: 800,
                      color: realIdx === 0 ? "#FF453A" : realIdx === 6 ? "#0A84FF" : "var(--fg-tertiary)",
                      textAlign: "center", padding: "9px 0", letterSpacing: "0.08em",
                      borderRight: i < 6 ? "1px solid var(--border-subtle)" : 0,
                    }}>{d}</div>
                  );
                })}
              </div>

              {/* Week rows */}
              {weeks.map((week, wi) => {
                const layout = layoutWeek(week, visibleEvents);
                const ghost = drag && (() => {
                  const ev = events.find((e) => e.id === drag.id);
                  if (!ev) return null;
                  return { ...ev, start: drag.ghostStart, end: drag.ghostEnd };
                })();
                const ghostInWeek = ghost && ghost.end >= week[0].ymd && ghost.start <= week[6].ymd;
                let ghostBar = null;
                if (ghostInWeek) {
                  const startCol = Math.max(0, diffDays(week[0].ymd, ghost.start));
                  const endCol = Math.min(6, diffDays(week[0].ymd, ghost.end));
                  ghostBar = { ...ghost, startCol, span: endCol - startCol + 1, lane: 0 };
                }

                const maxLane = Math.max(2, ...layout.map((l) => l.lane), ghostBar ? ghostBar.lane : 0);
                const rowHeight = Math.max(110, 28 + (maxLane + 1) * 22 + 12);

                // Compute ISO-ish week number from first day in row
                const firstDate = week[0].date;
                const onejan = new Date(firstDate.getFullYear(), 0, 1);
                const weekNum = Math.ceil((((firstDate - onejan) / 86400000) + onejan.getDay() + 1) / 7);

                return (
                  <div key={wi} style={{
                    display: "grid",
                    gridTemplateColumns: showWeek ? "32px repeat(7, 1fr)" : "repeat(7, 1fr)",
                    borderBottom: wi < 5 ? "1px solid var(--border-subtle)" : 0,
                    position: "relative",
                  }}>
                    {showWeek && (
                      <div style={{
                        fontSize: 9, fontWeight: 700, color: "var(--fg-tertiary)",
                        fontFamily: "var(--font-mono)",
                        display: "flex", alignItems: "flex-start", justifyContent: "center",
                        paddingTop: 8, background: "var(--bg-surface-2)",
                        borderRight: "1px solid var(--border-subtle)",
                      }}>W{String(weekNum).padStart(2, "0")}</div>
                    )}
                    {/* Day cells */}
                    {week.map((c, di) => (
                      <div key={di} style={{
                        minHeight: rowHeight,
                        padding: "6px 6px 4px",
                        background: c.isToday ? "#34C75909" : c.isCurMonth ? "var(--bg-surface)" : "var(--bg-surface-2)",
                        borderRight: di < 6 ? "1px solid var(--border-subtle)" : 0,
                        opacity: c.isCurMonth ? 1 : 0.55,
                        position: "relative",
                      }}>
                        <div style={{
                          fontSize: 11, fontWeight: c.isToday ? 800 : 600,
                          color: c.isToday ? "#fff" : c.weekday === 0 ? "#FF453A" : c.weekday === 6 ? "#0A84FF" : "var(--fg-primary)",
                          width: c.isToday ? 22 : "auto", height: c.isToday ? 22 : "auto",
                          background: c.isToday ? "#34C759" : "transparent",
                          borderRadius: 999,
                          display: "flex", alignItems: "center", justifyContent: "center",
                          padding: c.isToday ? 0 : "0 4px",
                        }}>{c.day}</div>
                      </div>
                    ))}

                    {/* Event-bar overlay layer (positioned absolutely over the row) */}
                    <div style={{
                      position: "absolute",
                      left: showWeek ? 32 : 0, top: 0, right: 0, bottom: 0,
                      pointerEvents: "none",
                    }}>
                      {layout.map((ev) => {
                        // hide original while dragging-move (not copy); resize also keeps it hidden
                        if (drag && drag.id === ev.id && !drag.copy) return null;
                        const isContLeft = ev.start < week[0].ymd;
                        const isContRight = ev.end > week[6].ymd;
                        return (
                          <div key={ev.id} style={{ pointerEvents: "auto" }}>
                            <EventBar
                              ev={ev}
                              selected={selected === ev.id}
                              onClick={(e) => setSelected(e.id)}
                              onMouseDown={(e) => {
                                const handle = e.target.getAttribute("data-handle");
                                if (handle === "left") startDrag(e, ev, "resize-left");
                                else if (handle === "right") startDrag(e, ev, "resize-right");
                                else startDrag(e, ev, "move");
                              }}
                              isContinuationLeft={isContLeft}
                              isContinuationRight={isContRight}
                            />
                          </div>
                        );
                      })}
                      {ghostBar && (
                        <EventBar
                          ev={ghostBar}
                          ghost
                          ghostCopy={drag?.copy}
                          isContinuationLeft={ghost.start < week[0].ymd}
                          isContinuationRight={ghost.end > week[6].ymd}
                        />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {view === "week" && (
            <WeekView
              year={year} month={month} weekStart={weekStart}
              events={visibleEvents} setEvents={setEvents} todayYMD={todayYMD}
            />
          )}

          {view === "day" && (
            <DayView events={visibleEvents} setEvents={setEvents} todayYMD={todayYMD} />
          )}
        </div>
      </div>
    </div>
  );
};

// ── 時間グリッド (Week / Day 共通) ────────────────────────────
// HOUR_PX: 1時間 = 56px, SNAP_MIN: 30分スナップ
const HOUR_PX = 56;
const SNAP_MIN = 15;
const HOUR_START = 7;
const HOUR_END = 21;
const HOURS = Array.from({ length: HOUR_END - HOUR_START }, (_, i) => i + HOUR_START);

const minToTime = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const timeToMin = (t) => { const [h, m] = t.split(":").map(Number); return h * 60 + m; };

// 時間ブロック (events overlay) — 마우스다운으로 드래그/리사이즈
const TimedEventBlock = ({ ev, top, height, onMouseDown, ghost = false, ghostCopy = false, hidden = false, leftPx, widthPx }) => {
  if (hidden) return null;
  return (
    <div
      onMouseDown={onMouseDown}
      style={{
        position: "absolute",
        left: leftPx, width: widthPx,
        top, height,
        background: ev.color, color: "#fff",
        borderRadius: 6,
        padding: "4px 6px",
        fontSize: 10, fontWeight: 700,
        boxShadow: ghost ? "0 0 0 2px rgba(255,255,255,.6), 0 4px 14px rgba(0,0,0,.25)" : "0 2px 6px rgba(0,0,0,.15)",
        opacity: ghost ? 0.9 : 1,
        outline: ghost ? "2px dashed rgba(255,255,255,.85)" : "none",
        outlineOffset: ghost ? -2 : 0,
        cursor: ghost ? "grabbing" : "grab",
        userSelect: "none",
        overflow: "hidden",
        zIndex: ghost ? 4 : 2,
      }}
    >
      {/* リサイズハンドル (上) */}
      <div data-handle="top" style={{
        position: "absolute", top: 0, left: 0, right: 0, height: 6,
        cursor: "ns-resize",
        background: "linear-gradient(to bottom, rgba(255,255,255,.35), transparent)",
      }}/>
      {/* リサイズハンドル (下) */}
      <div data-handle="bottom" style={{
        position: "absolute", bottom: 0, left: 0, right: 0, height: 6,
        cursor: "ns-resize",
        background: "linear-gradient(to top, rgba(255,255,255,.35), transparent)",
      }}/>
      {ghostCopy && (
        <div style={{
          position: "absolute", top: 4, right: 4,
          width: 16, height: 16, borderRadius: 999, background: "#34C759",
          color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 11, fontWeight: 800, lineHeight: 1,
        }}>+</div>
      )}
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, opacity: 0.85, pointerEvents: "none" }}>
        {ev.time}{ev.endTime ? `-${ev.endTime}` : ""}
      </div>
      <div style={{ marginTop: 2, lineHeight: 1.3, pointerEvents: "none" }}>{ev.title}</div>
    </div>
  );
};

// ── Week view (timed grid + drag/resize) ───────────────────
const WeekView = ({ year, month, weekStart, events, setEvents, todayYMD }) => {
  const today = parseYMD(todayYMD);
  const offset = (today.getDay() - weekStart + 7) % 7;
  const weekFirst = addDays(today, -offset);
  const days = Array.from({ length: 7 }, (_, i) => addDays(weekFirst, i));
  const dayYMDs = days.map(ymd);

  const gridRef = calR(null);
  const [drag, setDrag] = calS(null);

  // 시작 드래그
  const startDrag = (e, ev, mode) => {
    e.stopPropagation();
    e.preventDefault();
    if (!gridRef.current) return;
    const rect = gridRef.current.getBoundingClientRect();
    const colW = (rect.width - 44) / 7; // 44 = 시간 컬럼
    setDrag({
      id: ev.id, mode,
      originX: e.clientX, originY: e.clientY,
      originStart: ev.start,
      originTime: ev.time,
      originEndTime: ev.endTime || minToTime(timeToMin(ev.time) + 60),
      colW,
      ghostStart: ev.start, ghostTime: ev.time,
      ghostEndTime: ev.endTime || minToTime(timeToMin(ev.time) + 60),
      copy: false, moved: false,
    });
  };

  calE(() => {
    if (!drag) return;
    const onMove = (e) => {
      const dx = e.clientX - drag.originX;
      const dy = e.clientY - drag.originY;
      const dDays = Math.round(dx / drag.colW);
      const dMin = Math.round((dy / HOUR_PX) * 60 / SNAP_MIN) * SNAP_MIN;
      let ghostStart = drag.originStart;
      let ghostTime = drag.originTime;
      let ghostEndTime = drag.originEndTime;
      const sMin = timeToMin(drag.originTime);
      const eMin = timeToMin(drag.originEndTime);
      if (drag.mode === "move") {
        // 일자 이동 (단, 주 범위 밖이면 클램핑)
        const startD = parseYMD(drag.originStart);
        const newD = addDays(startD, dDays);
        const newYMD = ymd(newD);
        // 주 범위 안으로 클램핑
        ghostStart = newYMD < dayYMDs[0] ? dayYMDs[0] : newYMD > dayYMDs[6] ? dayYMDs[6] : newYMD;
        // 시간 이동
        let nS = sMin + dMin, nE = eMin + dMin;
        const minStart = HOUR_START * 60, maxEnd = HOUR_END * 60;
        if (nS < minStart) { const off = minStart - nS; nS += off; nE += off; }
        if (nE > maxEnd) { const off = nE - maxEnd; nS -= off; nE -= off; }
        ghostTime = minToTime(nS);
        ghostEndTime = minToTime(nE);
      } else if (drag.mode === "resize-top") {
        let nS = sMin + dMin;
        if (nS < HOUR_START * 60) nS = HOUR_START * 60;
        if (nS >= eMin) nS = eMin - SNAP_MIN;
        ghostTime = minToTime(nS);
      } else if (drag.mode === "resize-bottom") {
        let nE = eMin + dMin;
        if (nE > HOUR_END * 60) nE = HOUR_END * 60;
        if (nE <= sMin) nE = sMin + SNAP_MIN;
        ghostEndTime = minToTime(nE);
      }
      setDrag(d => ({
        ...d, ghostStart, ghostTime, ghostEndTime,
        moved: ghostStart !== d.originStart || ghostTime !== d.originTime || ghostEndTime !== d.originEndTime,
        copy: d.mode === "move" && (e.ctrlKey || e.metaKey || e.altKey),
      }));
    };
    const onUp = () => {
      setDrag(d => {
        if (!d) return null;
        if (d.moved && setEvents) {
          if (d.copy) {
            // 복제
            setEvents(evs => {
              const orig = evs.find(x => x.id === d.id);
              if (!orig) return evs;
              const newId = Math.max(...evs.map(x => x.id)) + 1;
              return [...evs, { ...orig, id: newId, start: d.ghostStart, end: d.ghostStart, time: d.ghostTime, endTime: d.ghostEndTime }];
            });
          } else {
            setEvents(evs => evs.map(x => x.id === d.id ? { ...x, start: d.ghostStart, end: d.ghostStart, time: d.ghostTime, endTime: d.ghostEndTime } : x));
          }
        }
        return null;
      });
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [drag, setEvents]);

  // 終日イベント을 헤더에 표시
  const allDayInWeek = events.filter(e => e.allDay && e.start <= dayYMDs[6] && e.end >= dayYMDs[0]);

  return (
    <div style={{
      background: "var(--bg-surface)", borderRadius: 14,
      border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
      overflow: "hidden",
    }}>
      <div style={{
        display: "grid", gridTemplateColumns: "44px repeat(7, 1fr)",
        background: "var(--bg-surface-2)", borderBottom: "1px solid var(--border-subtle)",
      }}>
        <div />
        {days.map((d, i) => (
          <div key={i} style={{
            padding: "8px 0", textAlign: "center",
            borderRight: i < 6 ? "1px solid var(--border-subtle)" : 0,
          }}>
            <div style={{ fontSize: 10, color: "var(--fg-tertiary)", fontWeight: 700 }}>
              {["日", "月", "火", "水", "木", "金", "土"][d.getDay()]}
            </div>
            <div style={{
              fontSize: 16, fontWeight: 800, marginTop: 2,
              color: ymd(d) === todayYMD ? "#34C759" : "var(--fg-primary)",
            }}>{d.getDate()}</div>
          </div>
        ))}
      </div>
      {/* 終日行 */}
      {allDayInWeek.length > 0 && (
        <div style={{
          display: "grid", gridTemplateColumns: "44px repeat(7, 1fr)",
          borderBottom: "1px solid var(--border-subtle)",
          background: "var(--bg-surface)",
          padding: "4px 0",
          minHeight: 24,
        }}>
          <div style={{ fontSize: 8, color: "var(--fg-tertiary)", textAlign: "right", padding: "4px 6px 0 0" }}>終日</div>
          <div style={{ gridColumn: "2 / span 7", position: "relative", height: allDayInWeek.length * 18 + 4 }}>
            {allDayInWeek.map((ev, idx) => {
              const sIdx = Math.max(0, dayYMDs.indexOf(ev.start));
              const eIdx = Math.min(6, dayYMDs.indexOf(ev.end) >= 0 ? dayYMDs.indexOf(ev.end) : 6);
              return (
                <div key={ev.id} style={{
                  position: "absolute",
                  left: `calc(${(sIdx / 7) * 100}% + 2px)`,
                  width: `calc(${((eIdx - sIdx + 1) / 7) * 100}% - 4px)`,
                  top: idx * 18 + 2,
                  height: 16, lineHeight: "16px",
                  background: ev.color, color: "#fff",
                  borderRadius: 4, padding: "0 6px",
                  fontSize: 9, fontWeight: 700,
                  boxShadow: "0 1px 3px rgba(0,0,0,.12)",
                  whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                }}>{ev.title}</div>
              );
            })}
          </div>
        </div>
      )}
      <div ref={gridRef} style={{ position: "relative", maxHeight: 540, overflow: "auto" }}>
        <div style={{
          display: "grid", gridTemplateColumns: "44px repeat(7, 1fr)",
          gridTemplateRows: `repeat(${HOURS.length}, ${HOUR_PX}px)`,
        }}>
          {HOURS.map((h, hi) => (
            <React.Fragment key={hi}>
              <div style={{
                fontSize: 9, color: "var(--fg-tertiary)",
                fontFamily: "var(--font-mono)", fontWeight: 700,
                textAlign: "right", padding: "2px 6px 0 0",
                borderTop: "1px solid var(--border-subtle)",
                gridColumn: "1", gridRow: hi + 1,
              }}>{String(h).padStart(2, "0")}:00</div>
              {days.map((_, di) => (
                <div key={di} style={{
                  borderTop: "1px solid var(--border-subtle)",
                  borderRight: di < 6 ? "1px solid var(--border-subtle)" : 0,
                  gridColumn: di + 2, gridRow: hi + 1,
                }} />
              ))}
            </React.Fragment>
          ))}
        </div>
        {/* Event overlay (시간 이벤트) */}
        {days.map((d, di) => {
          const ds = ymd(d);
          const dayEvs = events.filter((e) => e.start === ds && !e.allDay);
          return dayEvs.map((ev) => {
            const [sh, sm] = ev.time.split(":").map(Number);
            const eTime = ev.endTime || minToTime(timeToMin(ev.time) + 60);
            const [eh, em] = eTime.split(":").map(Number);
            const startMin = (sh - HOUR_START) * 60 + sm;
            const endMin = (eh - HOUR_START) * 60 + em;
            const top = (startMin / 60) * HOUR_PX;
            const height = Math.max(20, ((endMin - startMin) / 60) * HOUR_PX);
            // 7개 컬럼 너비 — 44px label + di번째
            const leftPx = `calc(44px + ${di} * ((100% - 44px) / 7) + 3px)`;
            const widthPx = `calc((100% - 44px) / 7 - 6px)`;
            const isDragging = drag && drag.id === ev.id && !drag.copy;
            return (
              <TimedEventBlock
                key={ev.id} ev={ev} top={top} height={height}
                leftPx={leftPx} widthPx={widthPx}
                hidden={isDragging}
                onMouseDown={(e) => {
                  const handle = e.target.getAttribute("data-handle");
                  if (handle === "top") startDrag(e, ev, "resize-top");
                  else if (handle === "bottom") startDrag(e, ev, "resize-bottom");
                  else startDrag(e, ev, "move");
                }}
              />
            );
          });
        })}
        {/* Ghost (드래그 미리보기) */}
        {drag && (() => {
          const ev = events.find(x => x.id === drag.id);
          if (!ev) return null;
          const di = dayYMDs.indexOf(drag.ghostStart);
          if (di < 0) return null;
          const sMin = timeToMin(drag.ghostTime) - HOUR_START * 60;
          const eMin = timeToMin(drag.ghostEndTime) - HOUR_START * 60;
          const top = (sMin / 60) * HOUR_PX;
          const height = Math.max(20, ((eMin - sMin) / 60) * HOUR_PX);
          const leftPx = `calc(44px + ${di} * ((100% - 44px) / 7) + 3px)`;
          const widthPx = `calc((100% - 44px) / 7 - 6px)`;
          return (
            <TimedEventBlock
              ev={{ ...ev, time: drag.ghostTime, endTime: drag.ghostEndTime }}
              top={top} height={height}
              leftPx={leftPx} widthPx={widthPx}
              ghost ghostCopy={drag.copy}
            />
          );
        })()}
      </div>
    </div>
  );
};

// ── Day view (시간 그리드 + 드래그/리사이즈) ──────────────────
const DayView = ({ events, setEvents, todayYMD }) => {
  const gridRef = calR(null);
  const [drag, setDrag] = calS(null);
  const dayD = parseYMD(todayYMD);
  const wkLabel = ["日", "月", "火", "水", "木", "金", "土"][dayD.getDay()];

  const allDayEvs = events.filter(e => e.allDay && e.start <= todayYMD && e.end >= todayYMD);
  const timedEvs = events.filter(e => e.start === todayYMD && !e.allDay)
    .sort((a, b) => a.time.localeCompare(b.time));

  const startDrag = (e, ev, mode) => {
    e.stopPropagation(); e.preventDefault();
    setDrag({
      id: ev.id, mode,
      originY: e.clientY,
      originTime: ev.time,
      originEndTime: ev.endTime || minToTime(timeToMin(ev.time) + 60),
      ghostTime: ev.time,
      ghostEndTime: ev.endTime || minToTime(timeToMin(ev.time) + 60),
      copy: false, moved: false,
    });
  };

  calE(() => {
    if (!drag) return;
    const onMove = (e) => {
      const dy = e.clientY - drag.originY;
      const dMin = Math.round((dy / HOUR_PX) * 60 / SNAP_MIN) * SNAP_MIN;
      const sMin = timeToMin(drag.originTime);
      const eMin = timeToMin(drag.originEndTime);
      let ghostTime = drag.originTime;
      let ghostEndTime = drag.originEndTime;
      if (drag.mode === "move") {
        let nS = sMin + dMin, nE = eMin + dMin;
        const minStart = HOUR_START * 60, maxEnd = HOUR_END * 60;
        if (nS < minStart) { const off = minStart - nS; nS += off; nE += off; }
        if (nE > maxEnd) { const off = nE - maxEnd; nS -= off; nE -= off; }
        ghostTime = minToTime(nS); ghostEndTime = minToTime(nE);
      } else if (drag.mode === "resize-top") {
        let nS = sMin + dMin;
        if (nS < HOUR_START * 60) nS = HOUR_START * 60;
        if (nS >= eMin) nS = eMin - SNAP_MIN;
        ghostTime = minToTime(nS);
      } else if (drag.mode === "resize-bottom") {
        let nE = eMin + dMin;
        if (nE > HOUR_END * 60) nE = HOUR_END * 60;
        if (nE <= sMin) nE = sMin + SNAP_MIN;
        ghostEndTime = minToTime(nE);
      }
      setDrag(d => ({
        ...d, ghostTime, ghostEndTime,
        moved: ghostTime !== d.originTime || ghostEndTime !== d.originEndTime,
        copy: d.mode === "move" && (e.ctrlKey || e.metaKey || e.altKey),
      }));
    };
    const onUp = () => {
      setDrag(d => {
        if (!d) return null;
        if (d.moved && setEvents) {
          if (d.copy) {
            setEvents(evs => {
              const orig = evs.find(x => x.id === d.id);
              if (!orig) return evs;
              const newId = Math.max(...evs.map(x => x.id)) + 1;
              return [...evs, { ...orig, id: newId, time: d.ghostTime, endTime: d.ghostEndTime }];
            });
          } else {
            setEvents(evs => evs.map(x => x.id === d.id ? { ...x, time: d.ghostTime, endTime: d.ghostEndTime } : x));
          }
        }
        return null;
      });
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [drag, setEvents]);

  return (
    <div style={{
      background: "var(--bg-surface)", borderRadius: 14,
      border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
      overflow: "hidden",
    }}>
      <div style={{
        padding: "12px 16px", borderBottom: "1px solid var(--border-subtle)",
        background: "var(--bg-surface-2)",
        display: "flex", alignItems: "baseline", gap: 10,
      }}>
        <div style={{ fontSize: 18, fontWeight: 800, color: "#34C759" }}>{dayD.getFullYear()}年 {dayD.getMonth() + 1}月 {dayD.getDate()}日</div>
        <div style={{ fontSize: 12, fontWeight: 700, color: "var(--fg-tertiary)" }}>({wkLabel})</div>
        <div style={{ marginLeft: "auto", fontSize: 11, color: "var(--fg-secondary)", fontWeight: 700 }}>
          {allDayEvs.length + timedEvs.length} 件
        </div>
      </div>

      {/* 終日 */}
      {allDayEvs.length > 0 && (
        <div style={{ padding: "8px 16px", borderBottom: "1px solid var(--border-subtle)", display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ fontSize: 9, fontWeight: 700, color: "var(--fg-tertiary)", letterSpacing: 0.4 }}>終日</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {allDayEvs.map(ev => (
              <div key={ev.id} style={{
                background: ev.color, color: "#fff",
                padding: "3px 8px", borderRadius: 4,
                fontSize: 10, fontWeight: 700,
              }}>{ev.title}</div>
            ))}
          </div>
        </div>
      )}

      <div ref={gridRef} style={{ position: "relative", maxHeight: 540, overflow: "auto" }}>
        <div style={{
          display: "grid", gridTemplateColumns: "60px 1fr",
          gridTemplateRows: `repeat(${HOURS.length}, ${HOUR_PX}px)`,
        }}>
          {HOURS.map((h, hi) => (
            <React.Fragment key={hi}>
              <div style={{
                fontSize: 10, color: "var(--fg-tertiary)",
                fontFamily: "var(--font-mono)", fontWeight: 700,
                textAlign: "right", padding: "2px 8px 0 0",
                borderTop: "1px solid var(--border-subtle)",
                gridColumn: "1", gridRow: hi + 1,
              }}>{String(h).padStart(2, "0")}:00</div>
              <div style={{
                borderTop: "1px solid var(--border-subtle)",
                gridColumn: "2", gridRow: hi + 1,
                position: "relative",
              }}>
                {/* half-hour line */}
                <div style={{
                  position: "absolute", top: HOUR_PX / 2, left: 0, right: 0,
                  borderTop: "1px dashed var(--border-subtle)", opacity: 0.5,
                }}/>
              </div>
            </React.Fragment>
          ))}
        </div>
        {/* Events */}
        {timedEvs.map(ev => {
          const sMin = timeToMin(ev.time) - HOUR_START * 60;
          const eMin = timeToMin(ev.endTime || minToTime(timeToMin(ev.time) + 60)) - HOUR_START * 60;
          const top = (sMin / 60) * HOUR_PX;
          const height = Math.max(20, ((eMin - sMin) / 60) * HOUR_PX);
          const isDragging = drag && drag.id === ev.id && !drag.copy;
          return (
            <TimedEventBlock
              key={ev.id} ev={ev} top={top} height={height}
              leftPx="calc(60px + 8px)"
              widthPx="calc(100% - 60px - 16px)"
              hidden={isDragging}
              onMouseDown={(e) => {
                const handle = e.target.getAttribute("data-handle");
                if (handle === "top") startDrag(e, ev, "resize-top");
                else if (handle === "bottom") startDrag(e, ev, "resize-bottom");
                else startDrag(e, ev, "move");
              }}
            />
          );
        })}
        {/* Ghost */}
        {drag && (() => {
          const ev = events.find(x => x.id === drag.id);
          if (!ev) return null;
          const sMin = timeToMin(drag.ghostTime) - HOUR_START * 60;
          const eMin = timeToMin(drag.ghostEndTime) - HOUR_START * 60;
          const top = (sMin / 60) * HOUR_PX;
          const height = Math.max(20, ((eMin - sMin) / 60) * HOUR_PX);
          return (
            <TimedEventBlock
              ev={{ ...ev, time: drag.ghostTime, endTime: drag.ghostEndTime }}
              top={top} height={height}
              leftPx="calc(60px + 8px)"
              widthPx="calc(100% - 60px - 16px)"
              ghost ghostCopy={drag.copy}
            />
          );
        })()}
      </div>
    </div>
  );
};

window.varA_calendar_detail = { CalendarDetail };
