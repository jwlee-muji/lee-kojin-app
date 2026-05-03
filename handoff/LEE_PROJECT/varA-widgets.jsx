/* global React, Ic, varA_atoms */
// Variation A — secondary widgets: Calendar, Gmail, AI Chat, Notice, Memo, Brief, Settings
const { Card, IconTile, Pill } = window.varA_atoms;
const DD = window.LEE_DATA;
const { useState: uS } = React;

// Calendar mini
const CalendarCard = ({ onClick }) => {
  const today = 22;
  const days = Array.from({ length: 35 }, (_, i) => i - 2); // padded
  return (
    <Card onClick={onClick}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
        <IconTile name="calendar" color="var(--c-cal)"/>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-secondary)" }}>カレンダー</div>
          <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>2025年 1月</div>
        </div>
        <Pill color="var(--c-cal)">3 件</Pill>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2, fontSize: 10, marginBottom: 4 }}>
        {["日","月","火","水","木","金","土"].map((d,i) => (
          <div key={i} style={{ textAlign: "center", color: i === 0 ? "var(--c-bad)" : i === 6 ? "var(--c-spot)" : "var(--fg-tertiary)", fontWeight: 700, padding: 3 }}>{d}</div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2 }}>
        {days.map((d, i) => {
          const valid = d > 0 && d <= 31;
          const isToday = d === today;
          const hasEvent = [3, 8, 15, 22, 28].includes(d);
          return (
            <div key={i} style={{
              aspectRatio: "1", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
              borderRadius: 8, fontSize: 11, fontWeight: isToday ? 800 : 500,
              color: !valid ? "transparent" : isToday ? "#fff" : "var(--fg-secondary)",
              background: isToday ? "var(--c-cal)" : "transparent",
              position: "relative",
            }}>
              {valid && d}
              {hasEvent && !isToday && <div style={{ width: 4, height: 4, borderRadius: 999, background: "var(--c-cal)", marginTop: 1 }}/>}
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border-subtle)", display: "flex", flexDirection: "column", gap: 6 }}>
        {DD.calendar.slice(0, 2).map((e, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 3, height: 28, background: e.color, borderRadius: 2 }}/>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--fg-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.title}</div>
              <div style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>{e.time}</div>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};

// Gmail
const GmailCard = ({ onClick }) => {
  const { useState: _gS, useMemo: _gM } = React;
  const labels = DD.gmailLabels || [];
  const [search, setSearch]   = _gS("");
  const [activeLbl, setActiveLbl] = _gS(null);
  const [showUnread, setShowUnread] = _gS(false);
  const [selected, setSelected] = _gS(new Set()); // ids
  const [emails, setEmails]     = _gS(DD.gmail);
  const [toast, setToast]       = _gS("");

  const lblColor = _gM(() => Object.fromEntries(labels.map((l) => [l.id, l.color])), [labels]);

  const filtered = _gM(() => {
    const q = search.trim().toLowerCase();
    return emails.filter((m) => {
      if (showUnread && !m.unread) return false;
      if (activeLbl && !(m.labels || []).includes(activeLbl)) return false;
      if (q && !(`${m.from} ${m.subject} ${m.snippet}`).toLowerCase().includes(q)) return false;
      return true;
    });
  }, [emails, search, showUnread, activeLbl]);

  const unreadCount = _gM(() => emails.filter((m) => m.unread).length, [emails]);
  const allSelected = filtered.length > 0 && filtered.every((m) => selected.has(m.id));
  const anySelected = selected.size > 0;

  const stop = (e) => e.stopPropagation();
  const fire = (msg) => { setToast(msg); setTimeout(() => setToast(""), 1800); };

  const toggleOne = (id) => setSelected((s) => {
    const n = new Set(s);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });
  const toggleAll = () => {
    if (allSelected) setSelected(new Set());
    else setSelected(new Set(filtered.map((m) => m.id)));
  };
  const markRead = () => {
    setEmails((es) => es.map((m) => selected.has(m.id) ? { ...m, unread: false } : m));
    fire(`✓ ${selected.size} 件を既読にしました`);
    setSelected(new Set());
  };
  const removeSel = () => {
    setEmails((es) => es.filter((m) => !selected.has(m.id)));
    fire(`✓ ${selected.size} 件を削除しました`);
    setSelected(new Set());
  };
  const archiveSel = () => {
    setEmails((es) => es.filter((m) => !selected.has(m.id)));
    fire(`✓ ${selected.size} 件をアーカイブしました`);
    setSelected(new Set());
  };
  const starOne = (e, id) => {
    e.stopPropagation();
    setEmails((es) => es.map((m) => m.id === id ? { ...m, starred: !m.starred } : m));
  };
  const markAllRead = () => {
    setEmails((es) => es.map((m) => m.unread ? { ...m, unread: false } : m));
    fire("✓ すべて既読にしました");
  };

  return (
    <Card onClick={onClick}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
        <IconTile name="gmail" color="var(--c-mail)"/>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-secondary)" }}>Gmail 受信トレイ</div>
          <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>未読 {unreadCount} 件 / 全 {emails.length} 件</div>
        </div>
        {unreadCount > 0 && <Pill color="var(--c-mail)">{unreadCount}</Pill>}
      </div>

      {/* Search + bulk action bar */}
      <div onClick={stop} style={{ display: "flex", gap: 6, marginBottom: 8 }}>
        <div style={{
          flex: 1, display: "flex", alignItems: "center", gap: 6,
          padding: "5px 10px", borderRadius: 8,
          background: "var(--bg-surface-2)",
          border: "1px solid var(--border-subtle)",
          height: 30, boxSizing: "border-box",
        }}>
          <span style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>🔍</span>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="検索…"
            style={{
              flex: 1, minWidth: 0, border: 0, outline: "none",
              background: "transparent", color: "var(--fg-primary)",
              fontFamily: "inherit", fontSize: 11, fontWeight: 500,
            }}
          />
          {search && (
            <button onClick={() => setSearch("")} style={miniBtn}>✕</button>
          )}
        </div>
        <button onClick={(e) => { stop(e); setShowUnread((v) => !v); }} title="未読のみ" style={{
          ...miniBtn, padding: "0 8px", height: 30,
          background: showUnread ? "var(--c-mail)" : "var(--bg-surface-2)",
          color: showUnread ? "#fff" : "var(--fg-secondary)",
          borderColor: showUnread ? "var(--c-mail)" : "var(--border-subtle)",
        }}>未読</button>
      </div>

      {/* Labels strip */}
      <div onClick={stop} style={{ display: "flex", gap: 4, marginBottom: 8, overflowX: "auto", paddingBottom: 2 }}>
        <button onClick={() => setActiveLbl(null)} style={{
          ...lblChip,
          background: activeLbl === null ? "var(--fg-primary)" : "transparent",
          color: activeLbl === null ? "var(--bg-base, #fff)" : "var(--fg-secondary)",
          borderColor: activeLbl === null ? "var(--fg-primary)" : "var(--border-subtle)",
        }}>すべて</button>
        {labels.map((l) => {
          const on = activeLbl === l.id;
          return (
            <button key={l.id} onClick={() => setActiveLbl(on ? null : l.id)} style={{
              ...lblChip,
              background: on ? l.color : "transparent",
              color: on ? "#fff" : "var(--fg-secondary)",
              borderColor: on ? l.color : "var(--border-subtle)",
            }}>
              <span style={{
                display: "inline-block",
                width: 7, height: 7, borderRadius: 999,
                background: on ? "rgba(255,255,255,.9)" : l.color,
                marginRight: 5,
              }} />
              {l.id}
            </button>
          );
        })}
      </div>

      {/* Bulk action bar */}
      <div onClick={stop} style={{
        display: "flex", alignItems: "center", gap: 4,
        padding: "6px 8px", marginBottom: 6,
        borderRadius: 8,
        background: anySelected ? "var(--c-mail-soft, #FF7A4515)" : "var(--bg-surface-2)",
        border: `1px solid ${anySelected ? "#FF7A4533" : "var(--border-subtle)"}`,
        height: 30, boxSizing: "border-box",
      }}>
        <CheckBox checked={allSelected} onChange={toggleAll} indeterminate={anySelected && !allSelected} />
        {anySelected ? (
          <>
            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--fg-primary)", marginLeft: 4 }}>
              {selected.size} 件選択
            </span>
            <span style={{ flex: 1 }} />
            <button onClick={markRead}    style={bulkBtn} title="既読">📖 既読</button>
            <button onClick={archiveSel}  style={bulkBtn} title="アーカイブ">📥 ア</button>
            <button onClick={removeSel}   style={{ ...bulkBtn, color: "#FF453A" }} title="削除">🗑</button>
          </>
        ) : (
          <>
            <span style={{ fontSize: 10, color: "var(--fg-tertiary)", marginLeft: 4 }}>
              {filtered.length} 件 {showUnread || activeLbl || search ? "(フィルタ中)" : ""}
            </span>
            <span style={{ flex: 1 }} />
            <button onClick={markAllRead} style={bulkBtn}>すべて既読</button>
          </>
        )}
      </div>

      {/* Toast */}
      {toast && (
        <div style={{
          fontSize: 11, color: "#34C759", fontWeight: 700,
          padding: "0 4px 6px",
        }}>{toast}</div>
      )}

      {/* List */}
      <div style={{ display: "flex", flexDirection: "column", maxHeight: 320, overflowY: "auto" }}>
        {filtered.length === 0 && (
          <div style={{
            padding: "30px 10px", textAlign: "center",
            fontSize: 11, color: "var(--fg-tertiary)",
          }}>
            メールが見つかりません
          </div>
        )}
        {filtered.slice(0, 8).map((m, i) => {
          const sel = selected.has(m.id);
          return (
            <div key={m.id} onClick={(e) => { stop(e); toggleOne(m.id); }} style={{
              padding: "8px 4px", display: "flex", gap: 8, alignItems: "flex-start",
              borderTop: i > 0 ? "1px solid var(--border-subtle)" : "none",
              background: sel ? "var(--c-mail-soft, #FF7A4512)" : "transparent",
              borderRadius: 6,
              cursor: "pointer",
              position: "relative",
            }}>
              <div style={{ paddingTop: 4 }}>
                <CheckBox checked={sel} onChange={() => toggleOne(m.id)} small />
              </div>
              <button onClick={(e) => starOne(e, m.id)} style={{
                background: "transparent", border: 0, padding: "4px 0 0", cursor: "pointer",
                color: m.starred ? "#FF9F0A" : "var(--fg-tertiary)",
                fontSize: 12,
              }}>{m.starred ? "★" : "☆"}</button>
              <div style={{
                width: 26, height: 26, borderRadius: 999, flexShrink: 0,
                background: m.color, color: "#fff", display: "flex", alignItems: "center",
                justifyContent: "center", fontSize: 10, fontWeight: 700, marginTop: 2,
              }}>{m.initial}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                  <span style={{
                    fontSize: 12, fontWeight: m.unread ? 800 : 500,
                    color: "var(--fg-primary)",
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  }}>{m.from}</span>
                  {m.important && <span style={{ color: "#FFCC00", fontSize: 10 }} title="重要">❗</span>}
                  {m.attachments > 0 && <span style={{ fontSize: 9, color: "var(--fg-tertiary)" }} title={`${m.attachments} 件添付`}>📎{m.attachments}</span>}
                  <span style={{ flex: 1 }} />
                  <span style={{ fontSize: 10, color: "var(--fg-tertiary)", flexShrink: 0 }}>{m.time}</span>
                </div>
                <div style={{
                  fontSize: 11, color: m.unread ? "var(--fg-primary)" : "var(--fg-secondary)",
                  fontWeight: m.unread ? 600 : 400,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                }}>{m.subject}</div>
                <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 2 }}>
                  {(m.labels || []).map((lid) => (
                    <span key={lid} style={{
                      fontSize: 8, fontWeight: 700,
                      padding: "1px 6px", borderRadius: 999,
                      background: `${lblColor[lid] || "#888"}1f`,
                      color: lblColor[lid] || "#888",
                      border: `1px solid ${lblColor[lid] || "#888"}33`,
                      letterSpacing: "0.04em",
                    }}>{lid}</span>
                  ))}
                  <span style={{
                    fontSize: 10, color: "var(--fg-tertiary)",
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                    flex: 1, minWidth: 0,
                  }}>{m.snippet}</span>
                </div>
              </div>
              {m.unread && (
                <span style={{
                  position: "absolute", left: -2, top: 14,
                  width: 3, height: 3 * 5, borderRadius: 999,
                  background: "var(--c-mail)",
                }} />
              )}
            </div>
          );
        })}
        {filtered.length > 8 && (
          <div style={{
            padding: "8px 0 4px", textAlign: "center",
            fontSize: 10, color: "var(--fg-tertiary)",
          }}>
            … 他 {filtered.length - 8} 件 (詳細画面で表示)
          </div>
        )}
      </div>
    </Card>
  );
};

// ── Local helpers (Gmail card) ──────────────────────────────
const CheckBox = ({ checked, onChange, small, indeterminate }) => (
  <span
    onClick={(e) => { e.stopPropagation(); onChange && onChange(!checked); }}
    style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      width: small ? 14 : 16, height: small ? 14 : 16,
      borderRadius: 4,
      border: `1.5px solid ${checked || indeterminate ? "var(--c-mail)" : "var(--border)"}`,
      background: checked ? "var(--c-mail)" : indeterminate ? "var(--c-mail)" : "transparent",
      color: "#fff", fontSize: small ? 9 : 11, fontWeight: 800,
      cursor: "pointer",
      flexShrink: 0,
      transition: "all 0.15s",
    }}
  >
    {checked ? "✓" : indeterminate ? "—" : ""}
  </span>
);
const miniBtn = {
  height: 22, padding: "0 8px",
  borderRadius: 6, border: "1px solid var(--border-subtle)",
  background: "var(--bg-surface-2)", color: "var(--fg-secondary)",
  fontFamily: "inherit", fontSize: 10, fontWeight: 700, cursor: "pointer",
};
const lblChip = {
  display: "inline-flex", alignItems: "center",
  height: 22, padding: "0 9px",
  borderRadius: 999,
  border: "1px solid var(--border-subtle)",
  background: "transparent",
  fontFamily: "inherit", fontSize: 10, fontWeight: 700,
  cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0,
  letterSpacing: "0.02em",
};
const bulkBtn = {
  height: 22, padding: "0 8px",
  borderRadius: 6, border: 0,
  background: "var(--bg-surface)",
  color: "var(--fg-secondary)",
  fontFamily: "inherit", fontSize: 10, fontWeight: 700, cursor: "pointer",
};

// AI chat
const AiChatCard = ({ onClick }) => (
  <Card onClick={onClick}>
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
      <IconTile name="chat" color="var(--c-ai)"/>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-secondary)" }}>AI チャット</div>
        <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>Claude · 電力データ接続済</div>
      </div>
      <Pill color="var(--c-ok)"><span style={{ width: 5, height: 5, borderRadius: 999, background: "var(--c-ok)" }}/>オン</Pill>
    </div>
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{
        alignSelf: "flex-end", maxWidth: "82%",
        background: "var(--c-ai)", color: "#fff",
        padding: "8px 12px", borderRadius: "16px 16px 4px 16px",
        fontSize: 12, lineHeight: 1.5,
      }}>明日のスポット価格、東京エリアの予測は?</div>
      <div style={{
        alignSelf: "flex-start", maxWidth: "82%",
        background: "var(--bg-surface-2)", color: "var(--fg-primary)",
        padding: "8px 12px", borderRadius: "16px 16px 16px 4px",
        fontSize: 12, lineHeight: 1.5,
      }}>明日 (1/23) の東京エリア平均は <b style={{color: "var(--c-spot)"}}>11.42 円/kWh</b> 予測。最高値は 18-19時台に <b style={{color: "var(--c-imb)"}}>16.8 円/kWh</b> に達する見込みです。</div>
    </div>
    <div style={{
      marginTop: 12, padding: "8px 12px", background: "var(--bg-surface-2)",
      borderRadius: 12, display: "flex", alignItems: "center", gap: 8, color: "var(--fg-tertiary)", fontSize: 12,
    }}>
      <Ic name="chat" size={14}/>
      質問を入力...
      <span style={{ marginLeft: "auto", fontSize: 10, padding: "2px 5px", border: "1px solid var(--border)", borderRadius: 4 }}>↵</span>
    </div>
  </Card>
);

// Notice
const NoticeCard = ({ onClick }) => (
  <Card onClick={onClick}>
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
      <IconTile name="notice" color="var(--c-notice)"/>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-secondary)" }}>通知センター</div>
        <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>本日 8 件 / 未読 3</div>
      </div>
      <Pill color="var(--c-bad)">3 NEW</Pill>
    </div>
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {DD.notices.slice(0, 4).map((n, i) => (
        <div key={i} style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "8px 10px", background: n.unread ? `color-mix(in srgb, ${n.color} 8%, transparent)` : "var(--bg-surface-2)",
          borderRadius: 10, border: n.unread ? `1px solid color-mix(in srgb, ${n.color} 30%, transparent)` : "1px solid transparent",
        }}>
          <div style={{
            width: 26, height: 26, borderRadius: 8, flexShrink: 0,
            background: n.color, color: "#fff",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <Ic name={n.icon} size={13}/>
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--fg-primary)" }}>{n.title}</div>
            <div style={{ fontSize: 10, color: "var(--fg-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{n.body}</div>
          </div>
          <div style={{ fontSize: 9, color: "var(--fg-tertiary)" }}>{n.time}</div>
        </div>
      ))}
    </div>
  </Card>
);

// Memo
const MemoCard = ({ onClick }) => (
  <Card onClick={onClick}>
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
      <IconTile name="memo" color="var(--c-memo)"/>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-secondary)" }}>テキストメモ</div>
        <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>3 件のメモ</div>
      </div>
    </div>
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {DD.memos.map((m, i) => (
        <div key={i} style={{
          padding: 12, background: `color-mix(in srgb, ${m.color} 10%, var(--bg-surface-2))`,
          borderRadius: 12, borderLeft: `3px solid ${m.color}`,
        }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--fg-primary)", marginBottom: 2 }}>{m.title}</div>
          <div style={{ fontSize: 11, color: "var(--fg-secondary)", lineHeight: 1.5, overflow: "hidden", textOverflow: "ellipsis", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>{m.body}</div>
          <div style={{ fontSize: 9, color: "var(--fg-tertiary)", marginTop: 4 }}>{m.date}</div>
        </div>
      ))}
    </div>
  </Card>
);

// AI Briefing card (large)
const BriefCard = ({ onClick }) => (
  <Card onClick={onClick}>
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
      <IconTile name="brief" color="var(--c-ai)"/>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-secondary)" }}>AI 朝のブリーフィング</div>
        <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>2025/01/22 06:00 自動生成</div>
      </div>
      <Pill color="var(--c-ai)">NEW</Pill>
    </div>
    <div style={{ fontSize: 13, lineHeight: 1.65, color: "var(--fg-primary)" }}>
      おはようございます。本日は <b style={{color:"var(--c-imb)"}}>東京エリアの予備率が 6.2%</b> と警戒水準に近づいています。スポット価格は前日比 <b style={{color:"var(--c-bad)"}}>+8.4%</b>、特に夕方ピーク帯の上昇が顕著です。LNG (JKM) は 14.32 USD で <b style={{color:"var(--c-ok)"}}>下落基調</b>。9:00 のチーム MTG 前にご確認ください。
    </div>
    <div style={{
      display: "flex", gap: 8, marginTop: 14, paddingTop: 12,
      borderTop: "1px solid var(--border-subtle)",
    }}>
      {[
        { label: "予備率", v: "6.2%", c: "var(--c-bad)" },
        { label: "スポット平均", v: "10.78", c: "var(--c-spot)" },
        { label: "JKM", v: "14.32", c: "var(--c-jkm)" },
      ].map((s, i) => (
        <div key={i} style={{ flex: 1, textAlign: "center" }}>
          <div style={{ fontSize: 16, fontWeight: 800, color: s.c, fontVariantNumeric: "tabular-nums" }}>{s.v}</div>
          <div style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>{s.label}</div>
        </div>
      ))}
    </div>
  </Card>
);

// Toast
const Toast = ({ toast, onClose }) => {
  if (!toast) return null;
  return (
    <div style={{
      position: "fixed", bottom: 24, right: 24, zIndex: 1000,
      background: "var(--bg-surface)",
      border: "1px solid var(--border)",
      borderRadius: 16, padding: 14, minWidth: 320, maxWidth: 380,
      boxShadow: "var(--shadow-lg)",
      display: "flex", gap: 12, alignItems: "flex-start",
      animation: "slideUp 0.3s ease-out",
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: 10, flexShrink: 0,
        background: toast.color, color: "#fff",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <Ic name={toast.icon} size={17}/>
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "var(--fg-primary)" }}>{toast.title}</div>
        <div style={{ fontSize: 11, color: "var(--fg-secondary)", marginTop: 2, lineHeight: 1.5 }}>{toast.body}</div>
      </div>
      <button onClick={onClose} style={{
        border: "none", background: "transparent", color: "var(--fg-tertiary)", cursor: "pointer", padding: 0,
      }}>
        <Ic name="x" size={14}/>
      </button>
    </div>
  );
};

window.varA_widgets = { CalendarCard, GmailCard, AiChatCard, NoticeCard, MemoCard, BriefCard, Toast };
