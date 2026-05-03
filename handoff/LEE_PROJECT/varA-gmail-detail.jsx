/* global React */
// ============================================================
// LEE — Gmail Detail (full-featured)
//   • Search + label filter (multi-select via labels[])
//   • Multi-select via row checkboxes
//   • Bulk actions: 全て既読, 削除, アーカイブ
//   • Star / important / attachments badges
//   • Unread count per label, total counts
//   • Reading pane with reply/forward/archive
// ============================================================
const { useState: gmS, useMemo: gmM } = React;
const { DetailHeader: GM_DH } = window.varA_detail_atoms;
const GM_D = window.LEE_DATA;

// ── icons ──────────────────────────────────────────────────
const Star = ({ on, ...p }) => (
  <svg viewBox="0 0 24 24" width="14" height="14"
    fill={on ? "#FF9F0A" : "transparent"}
    stroke={on ? "#FF9F0A" : "currentColor"} strokeWidth="2"
    strokeLinejoin="round" {...p}>
    <polygon points="12 2 15.1 8.6 22 9.5 17 14.5 18.3 21.5 12 18 5.7 21.5 7 14.5 2 9.5 8.9 8.6 12 2"/>
  </svg>
);

const Paperclip = (p) => (
  <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" {...p}>
    <path d="M21.44 11.05L12.25 20.24a6 6 0 1 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 1 1-2.83-2.83l8.49-8.48"/>
  </svg>
);

const ImportantTag = () => (
  <svg viewBox="0 0 24 24" width="11" height="11" fill="#FFCC00" stroke="#FFCC00" strokeWidth="2" strokeLinejoin="round">
    <path d="M12 2L1 21h22L12 2z"/>
    <line x1="12" y1="9" x2="12" y2="14" stroke="#000" strokeWidth="1.5"/>
    <circle cx="12" cy="17" r="0.8" fill="#000"/>
  </svg>
);

// ── Compose (modal) — minimal for demo ─────────────────────
const ComposeModal = ({ onClose }) => (
  <div onClick={onClose} style={{
    position: "fixed", inset: 0, background: "rgba(0,0,0,.4)", zIndex: 100,
    display: "flex", alignItems: "center", justifyContent: "center",
  }}>
    <div onClick={(e) => e.stopPropagation()} style={{
      width: 540, background: "var(--bg-surface)", borderRadius: 16,
      border: "1px solid var(--border)", boxShadow: "0 12px 40px rgba(0,0,0,.3)",
      padding: 20,
    }}>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 14 }}>
        <div style={{ fontSize: 14, fontWeight: 800 }}>新規メール</div>
        <button onClick={onClose} style={{ marginLeft: "auto", border: 0, background: "transparent", cursor: "pointer", color: "var(--fg-tertiary)" }}>✕</button>
      </div>
      {[
        ["宛先", "山田 課長 <yamada@enex.co.jp>"],
        ["件名", "週次レポート ドラフト送付の件"],
      ].map(([lbl, val], i) => (
        <div key={i} style={{
          display: "flex", padding: "8px 0",
          borderBottom: "1px solid var(--border-subtle)",
        }}>
          <div style={{ width: 56, fontSize: 11, color: "var(--fg-tertiary)" }}>{lbl}</div>
          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--fg-primary)" }}>{val}</div>
        </div>
      ))}
      <textarea defaultValue="お疲れ様です。週次レポートのドラフトを送付します。ご確認の上、コメント等ございましたらご連絡ください。" style={{
        width: "100%", height: 140, marginTop: 12,
        padding: 12, borderRadius: 8, border: "1px solid var(--border-subtle)",
        background: "var(--bg-surface-2)", color: "var(--fg-primary)",
        fontFamily: "inherit", fontSize: 12, lineHeight: 1.6, resize: "vertical",
      }} />
      <div style={{ display: "flex", marginTop: 14, gap: 8 }}>
        <button style={{
          padding: "9px 18px", borderRadius: 10, border: 0,
          background: "#FF7A45", color: "#fff",
          fontFamily: "inherit", fontSize: 12, fontWeight: 800, cursor: "pointer",
        }}>送信</button>
        <button onClick={onClose} style={{
          padding: "9px 14px", borderRadius: 10, border: "1px solid var(--border)",
          background: "transparent", color: "var(--fg-secondary)",
          fontFamily: "inherit", fontSize: 12, fontWeight: 600, cursor: "pointer",
        }}>キャンセル</button>
      </div>
    </div>
  </div>
);

// ── Main ───────────────────────────────────────────────────
const GmailDetailV2 = ({ onBack }) => {
  const allLabels = GM_D.gmailLabels;
  const labelColor = (id) => (allLabels.find((l) => l.id === id) || {}).color || "#888";

  const [emails, setEmails] = gmS(GM_D.gmail.map((m) => ({ ...m, labels: m.labels || (m.label ? [m.label] : []) })));
  const [activeLabel, setActiveLabel] = gmS("all"); // "all" | "starred" | "unread" | "important" | <labelId>
  const [search, setSearch] = gmS("");
  const [selectedIds, setSelectedIds] = gmS(new Set());
  const [openId, setOpenId] = gmS(emails[0]?.id);
  const [composeOpen, setComposeOpen] = gmS(false);

  // Filtered list
  const filtered = gmM(() => {
    let l = emails;
    if (activeLabel === "starred") l = l.filter((m) => m.starred);
    else if (activeLabel === "unread") l = l.filter((m) => m.unread);
    else if (activeLabel === "important") l = l.filter((m) => m.important);
    else if (activeLabel !== "all") l = l.filter((m) => m.labels.includes(activeLabel));
    if (search.trim()) {
      const q = search.toLowerCase();
      l = l.filter((m) =>
        m.subject.toLowerCase().includes(q) ||
        m.from.toLowerCase().includes(q) ||
        (m.preview || "").toLowerCase().includes(q)
      );
    }
    return l;
  }, [emails, activeLabel, search]);

  const cur = emails.find((m) => m.id === openId) || filtered[0] || emails[0];

  // ── Counts per label ──
  const counts = gmM(() => {
    const total = emails.length;
    const unread = emails.filter((m) => m.unread).length;
    const starred = emails.filter((m) => m.starred).length;
    const important = emails.filter((m) => m.important).length;
    const byLabel = {};
    allLabels.forEach((l) => {
      byLabel[l.id] = emails.filter((m) => m.labels.includes(l.id) && m.unread).length;
    });
    return { total, unread, starred, important, byLabel };
  }, [emails]);

  // ── Actions ──
  const toggleSel = (id) => setSelectedIds((s) => {
    const n = new Set(s);
    if (n.has(id)) n.delete(id); else n.add(id);
    return n;
  });
  const selectAll = () => {
    if (selectedIds.size === filtered.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(filtered.map((m) => m.id)));
  };
  const markAllRead = () => {
    setEmails((es) => es.map((m) => filtered.find((f) => f.id === m.id) ? { ...m, unread: false } : m));
  };
  const markSelectedRead = () => {
    setEmails((es) => es.map((m) => selectedIds.has(m.id) ? { ...m, unread: false } : m));
    setSelectedIds(new Set());
  };
  const deleteSelected = () => {
    setEmails((es) => es.filter((m) => !selectedIds.has(m.id)));
    setSelectedIds(new Set());
  };
  const toggleStar = (id) => {
    setEmails((es) => es.map((m) => m.id === id ? { ...m, starred: !m.starred } : m));
  };
  const openMail = (id) => {
    setOpenId(id);
    setEmails((es) => es.map((m) => m.id === id ? { ...m, unread: false } : m));
  };

  // ── Layout ──
  const navItems = [
    { id: "all",       label: "すべて",   icon: "📥", count: counts.total },
    { id: "unread",    label: "未読",     icon: "●",  count: counts.unread, badge: true },
    { id: "starred",   label: "スター付き", icon: "★", count: counts.starred },
    { id: "important", label: "重要",     icon: "!",  count: counts.important },
  ];

  return (
    <div style={{ padding: 28 }}>
      <GM_DH
        title="Gmail"
        subtitle={`${GM_D.user.email} · 受信箱`}
        accent="#FF7A45"
        icon="gmail"
        onBack={onBack}
        badge={`${counts.unread} 未読`}
      />

      <div style={{ display: "grid", gridTemplateColumns: "200px 1fr 1.4fr", gap: 14 }}>
        {/* ── Sidebar ──────────────────── */}
        <div style={{
          background: "var(--bg-surface)", borderRadius: 16, padding: 14,
          border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
          display: "flex", flexDirection: "column", gap: 14,
        }}>
          <button onClick={() => setComposeOpen(true)} style={{
            padding: "10px 14px", borderRadius: 10, border: 0,
            background: "#FF7A45", color: "#fff",
            fontFamily: "inherit", fontSize: 12, fontWeight: 800, cursor: "pointer",
            display: "flex", alignItems: "center", gap: 8, justifyContent: "center",
            boxShadow: "0 2px 6px rgba(255,122,69,.3)",
          }}>
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            作成
          </button>

          <div>
            <div style={{ fontSize: 10, fontWeight: 800, color: "var(--fg-tertiary)", letterSpacing: "0.08em", marginBottom: 8, padding: "0 6px" }}>受信箱</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {navItems.map((n) => {
                const on = activeLabel === n.id;
                return (
                  <button key={n.id} onClick={() => setActiveLabel(n.id)} style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "7px 8px", borderRadius: 7,
                    border: 0, background: on ? "#FF7A4514" : "transparent",
                    color: on ? "#FF7A45" : "var(--fg-secondary)",
                    fontFamily: "inherit", fontSize: 12, fontWeight: on ? 800 : 600,
                    cursor: "pointer", textAlign: "left",
                  }}>
                    <span style={{ width: 16, textAlign: "center", fontSize: n.icon.length > 1 ? 13 : 11 }}>{n.icon}</span>
                    <span style={{ flex: 1 }}>{n.label}</span>
                    {n.count > 0 && (
                      <span style={{
                        fontSize: 10, fontWeight: 700, padding: "1px 6px", borderRadius: 999,
                        background: n.badge && n.count > 0 ? "#FF7A45" : "var(--bg-surface-2)",
                        color: n.badge && n.count > 0 ? "#fff" : "var(--fg-tertiary)",
                      }}>{n.count}</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <div style={{ fontSize: 10, fontWeight: 800, color: "var(--fg-tertiary)", letterSpacing: "0.08em", marginBottom: 8, padding: "0 6px" }}>ラベル</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {allLabels.map((l) => {
                const on = activeLabel === l.id;
                return (
                  <button key={l.id} onClick={() => setActiveLabel(l.id)} style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "7px 8px", borderRadius: 7,
                    border: 0, background: on ? `${l.color}1f` : "transparent",
                    color: on ? l.color : "var(--fg-secondary)",
                    fontFamily: "inherit", fontSize: 12, fontWeight: on ? 800 : 600,
                    cursor: "pointer", textAlign: "left",
                  }}>
                    <span style={{ width: 10, height: 10, borderRadius: 3, background: l.color, flexShrink: 0 }} />
                    <span style={{ flex: 1 }}>{l.id}</span>
                    {counts.byLabel[l.id] > 0 && (
                      <span style={{ fontSize: 10, fontWeight: 800, color: l.color }}>{counts.byLabel[l.id]}</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* ── List pane ──────────────────── */}
        <div style={{
          background: "var(--bg-surface)", borderRadius: 16,
          border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
          display: "flex", flexDirection: "column", overflow: "hidden",
          maxHeight: 620,
        }}>
          {/* Search bar */}
          <div style={{ padding: 12, borderBottom: "1px solid var(--border-subtle)" }}>
            <div style={{
              display: "flex", alignItems: "center", gap: 8,
              padding: "7px 12px", borderRadius: 10,
              background: "var(--bg-surface-2)",
              border: "1px solid var(--border-subtle)",
            }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--fg-tertiary)" strokeWidth="2.5">
                <circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
              <input value={search} onChange={(e) => setSearch(e.target.value)}
                placeholder="メールを検索" style={{
                flex: 1, border: 0, background: "transparent", outline: "none",
                color: "var(--fg-primary)", fontFamily: "inherit", fontSize: 12,
              }} />
              {search && (
                <button onClick={() => setSearch("")} style={{
                  border: 0, background: "transparent", cursor: "pointer",
                  color: "var(--fg-tertiary)", fontSize: 14, padding: 0,
                }}>✕</button>
              )}
            </div>
          </div>

          {/* Toolbar */}
          <div style={{
            display: "flex", alignItems: "center", gap: 6,
            padding: "8px 12px", borderBottom: "1px solid var(--border-subtle)",
            background: "var(--bg-surface-2)",
          }}>
            <label style={{ display: "flex", alignItems: "center", padding: "0 6px", cursor: "pointer" }}>
              <input type="checkbox"
                checked={filtered.length > 0 && selectedIds.size === filtered.length}
                onChange={selectAll}
                style={{ width: 14, height: 14, accentColor: "#FF7A45", cursor: "pointer" }} />
            </label>
            {selectedIds.size > 0 ? (
              <>
                <span style={{ fontSize: 11, fontWeight: 700, color: "var(--fg-secondary)" }}>{selectedIds.size} 件選択中</span>
                <div style={{ flex: 1 }} />
                <button onClick={markSelectedRead} style={tbBtn}>既読</button>
                <button onClick={deleteSelected} style={{ ...tbBtn, color: "#FF453A" }}>削除</button>
                <button onClick={() => setSelectedIds(new Set())} style={tbBtn}>キャンセル</button>
              </>
            ) : (
              <>
                <div style={{ flex: 1 }} />
                {counts.unread > 0 && (
                  <button onClick={markAllRead} style={{ ...tbBtn, color: "#FF7A45", fontWeight: 700 }}>
                    全て既読にする ({counts.unread})
                  </button>
                )}
              </>
            )}
          </div>

          {/* List */}
          <div className="lee-scroll" style={{ flex: 1, overflow: "auto" }}>
            {filtered.length === 0 && (
              <div style={{ padding: 30, textAlign: "center", color: "var(--fg-tertiary)", fontSize: 12 }}>
                該当するメールがありません
              </div>
            )}
            {filtered.map((m) => {
              const sel = selectedIds.has(m.id);
              const active = openId === m.id;
              return (
                <div key={m.id} onClick={() => openMail(m.id)} style={{
                  display: "flex", gap: 8, padding: "10px 12px",
                  borderBottom: "1px solid var(--border-subtle)",
                  background: active ? "#FF7A4510" : sel ? "#FF7A4506" : "transparent",
                  borderLeft: active ? "3px solid #FF7A45" : "3px solid transparent",
                  cursor: "pointer",
                  fontWeight: m.unread ? 700 : 500,
                }}>
                  <input type="checkbox" checked={sel}
                    onClick={(e) => e.stopPropagation()}
                    onChange={() => toggleSel(m.id)}
                    style={{ width: 13, height: 13, accentColor: "#FF7A45", cursor: "pointer", flexShrink: 0, marginTop: 2 }} />
                  <button onClick={(e) => { e.stopPropagation(); toggleStar(m.id); }} style={{
                    border: 0, background: "transparent", cursor: "pointer", padding: 0, marginTop: 1,
                    color: m.starred ? "#FF9F0A" : "var(--fg-tertiary)",
                  }}>
                    <Star on={m.starred} />
                  </button>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                      <span style={{
                        width: 24, height: 24, borderRadius: 999,
                        background: m.color, color: "#fff",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: 11, fontWeight: 700, flexShrink: 0,
                      }}>{m.initial}</span>
                      <span style={{
                        fontSize: 12, color: "var(--fg-primary)",
                        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                        fontWeight: m.unread ? 800 : 600,
                      }}>{m.from}</span>
                      {m.important && <ImportantTag />}
                      <div style={{ flex: 1 }} />
                      <span style={{ fontSize: 10, color: m.unread ? "#FF7A45" : "var(--fg-tertiary)", fontWeight: 700, flexShrink: 0 }}>{m.time}</span>
                    </div>
                    <div style={{
                      fontSize: 12, color: "var(--fg-primary)", marginBottom: 2,
                      whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                    }}>
                      {m.unread && <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: 999, background: "#FF7A45", marginRight: 6, verticalAlign: "middle" }} />}
                      {m.subject}
                    </div>
                    <div style={{
                      fontSize: 11, color: "var(--fg-secondary)", lineHeight: 1.4,
                      whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                      display: "flex", alignItems: "center", gap: 6,
                    }}>
                      {m.attachments > 0 && (
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 2, color: "var(--fg-tertiary)" }}>
                          <Paperclip /><span style={{ fontSize: 10 }}>{m.attachments}</span>
                        </span>
                      )}
                      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>{m.preview}</span>
                    </div>
                    {/* Labels */}
                    {m.labels.length > 0 && (
                      <div style={{ display: "flex", gap: 4, marginTop: 4, flexWrap: "wrap" }}>
                        {m.labels.map((lid) => (
                          <span key={lid} style={{
                            fontSize: 9, fontWeight: 700,
                            padding: "1px 6px", borderRadius: 4,
                            background: `${labelColor(lid)}1f`,
                            color: labelColor(lid),
                            border: `1px solid ${labelColor(lid)}33`,
                          }}>{lid}</span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ── Reading pane ──────────────────── */}
        <div style={{
          background: "var(--bg-surface)", borderRadius: 16, padding: 22,
          border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
          maxHeight: 620, overflow: "auto", position: "relative",
        }}>
          {!cur ? (
            <div style={{ padding: 30, textAlign: "center", color: "var(--fg-tertiary)" }}>メールを選択してください</div>
          ) : (
            <>
              {/* Header */}
              <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 14, paddingBottom: 14, borderBottom: "1px solid var(--border-subtle)" }}>
                <div style={{
                  width: 44, height: 44, borderRadius: 999,
                  background: cur.color, color: "#fff",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 16, fontWeight: 700, flexShrink: 0,
                }}>{cur.initial}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 800, marginBottom: 2 }}>{cur.from}</div>
                  <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>
                    {cur.email} · 受信: {cur.date}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--fg-tertiary)", marginTop: 2 }}>
                    宛先: {GM_D.user.email}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 4 }}>
                  <button onClick={() => toggleStar(cur.id)} style={{
                    width: 28, height: 28, borderRadius: 7, border: "1px solid var(--border-subtle)",
                    background: cur.starred ? "#FF9F0A1f" : "var(--bg-surface-2)",
                    color: cur.starred ? "#FF9F0A" : "var(--fg-tertiary)",
                    cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
                  }}>
                    <Star on={cur.starred} />
                  </button>
                </div>
              </div>

              {/* Subject */}
              <div style={{ fontSize: 22, fontWeight: 800, color: "var(--fg-primary)", marginBottom: 10, letterSpacing: "-0.01em", lineHeight: 1.3 }}>
                {cur.subject}
              </div>
              {/* Labels chips */}
              {cur.labels.length > 0 && (
                <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
                  {cur.labels.map((lid) => (
                    <span key={lid} style={{
                      fontSize: 10, fontWeight: 800,
                      padding: "3px 9px", borderRadius: 999,
                      background: `${labelColor(lid)}1f`,
                      color: labelColor(lid),
                      border: `1px solid ${labelColor(lid)}33`,
                      letterSpacing: "0.04em",
                    }}>{lid}</span>
                  ))}
                </div>
              )}

              {/* Body */}
              <div style={{ fontSize: 13, color: "var(--fg-primary)", lineHeight: 1.7, marginBottom: 16 }}>
                <p style={{ marginBottom: 10 }}>{GM_D.user.name}様、いつもお世話になっております。</p>
                <p style={{ marginBottom: 10 }}>{cur.preview} 詳細は以下の通りです。引き続きの監視と必要な対応のご検討をお願いいたします。</p>
                <div style={{ margin: "12px 0", padding: 14, background: "var(--bg-surface-2)", borderRadius: 8, fontFamily: "var(--font-mono)", fontSize: 11, lineHeight: 1.8, border: "1px solid var(--border-subtle)" }}>
                  本日 18:30<br/>
                  東京エリア 予備率: 6.2%<br/>
                  想定需要: 49.3 GW / 供給力: 52.4 GW<br/>
                  インバランス単価最大: 38.50 円/kWh
                </div>
                <p>何卒よろしくお願いいたします。</p>
                <p style={{ marginTop: 14, color: "var(--fg-tertiary)", fontSize: 12 }}>
                  --<br/>
                  {cur.from}<br/>
                  {cur.email}
                </p>
              </div>

              {/* Attachments */}
              {cur.attachments > 0 && (
                <div style={{ marginBottom: 16, paddingBottom: 16, borderBottom: "1px solid var(--border-subtle)" }}>
                  <div style={{ fontSize: 10, fontWeight: 800, color: "var(--fg-tertiary)", letterSpacing: "0.08em", marginBottom: 8 }}>
                    添付ファイル ({cur.attachments})
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {Array.from({ length: cur.attachments }, (_, i) => (
                      <div key={i} style={{
                        display: "flex", alignItems: "center", gap: 8,
                        padding: "8px 12px", borderRadius: 8,
                        background: "var(--bg-surface-2)",
                        border: "1px solid var(--border-subtle)",
                        cursor: "pointer",
                      }}>
                        <div style={{
                          width: 28, height: 32, borderRadius: 4,
                          background: ["#FF7A45", "#5B8DEF", "#34C759"][i % 3],
                          color: "#fff", fontSize: 8, fontWeight: 800,
                          display: "flex", alignItems: "center", justifyContent: "center",
                        }}>{["PDF", "XLSX", "DOCX"][i % 3]}</div>
                        <div>
                          <div style={{ fontSize: 11, fontWeight: 700 }}>添付ファイル{i + 1}.{["pdf", "xlsx", "docx"][i % 3]}</div>
                          <div style={{ fontSize: 9, color: "var(--fg-tertiary)" }}>{(120 + i * 50).toFixed(0)} KB</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Action buttons */}
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {[["返信", "#FF7A45", "primary"], ["全員に返信", null], ["転送", null], ["アーカイブ", null], ["削除", "#FF453A"]].map(([l, color, kind], i) => (
                  <button key={i} onClick={kind === "primary" ? () => setComposeOpen(true) : undefined} style={{
                    padding: "8px 14px", borderRadius: 9,
                    border: kind === "primary" ? 0 : "1px solid var(--border)",
                    background: kind === "primary" ? color : "transparent",
                    color: kind === "primary" ? "#fff" : (color || "var(--fg-secondary)"),
                    fontFamily: "inherit", fontSize: 12, fontWeight: 700, cursor: "pointer",
                  }}>{l}</button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {composeOpen && <ComposeModal onClose={() => setComposeOpen(false)} />}
    </div>
  );
};

const tbBtn = {
  padding: "5px 10px", borderRadius: 7,
  border: "1px solid var(--border-subtle)",
  background: "var(--bg-surface)", color: "var(--fg-secondary)",
  fontFamily: "inherit", fontSize: 11, fontWeight: 600, cursor: "pointer",
};

window.varA_gmail_detail = { GmailDetail: GmailDetailV2 };
