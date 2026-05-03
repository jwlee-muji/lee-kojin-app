/* global React, Ic */
// AI Chat + Notice + Memo detail screens
const { useState: a6S } = React;
const { KPI, DetailHeader } = window.varA_detail_atoms;
const { Pill } = window.varA_atoms;
const A6 = window.LEE_DATA;

// ── AI Chat Detail ────────────────────────────────────────
const AiChatDetail = ({ onBack }) => {
  const [draft, setDraft] = a6S("");
  const [chat, setChat] = a6S(A6.aiChat);

  const send = () => {
    if (!draft.trim()) return;
    setChat([...chat, { role: "user", text: draft }, { role: "ai", text: "(モック応答) ご質問ありがとうございます。データを取得しています…" }]);
    setDraft("");
  };

  const suggestions = [
    "今日のスポット価格の特徴は?",
    "JKM の今後の見通しは?",
    "東京エリアの需給ひっ迫対策は?",
    "再エネ比率の推移を教えて",
  ];

  return (
    <div style={{ padding: 28, height: "calc(100% - 0px)", display: "flex", flexDirection: "column" }}>
      <DetailHeader
        title="AI アシスタント"
        subtitle="GPT-4o + 社内市場データ · リアルタイム接続"
        accent="#5856D6"
        icon="chat"
        onBack={onBack}
        badge="online"
      />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 280px", gap: 16, flex: 1, minHeight: 0 }}>
        {/* Conversation */}
        <div style={{
          background: "var(--bg-surface)", borderRadius: 18,
          border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
          display: "flex", flexDirection: "column", overflow: "hidden",
        }}>
          <div style={{
            padding: "12px 18px", borderBottom: "1px solid var(--border-subtle)",
            display: "flex", alignItems: "center", gap: 10, fontSize: 12,
          }}>
            <span style={{ width: 8, height: 8, borderRadius: 999, background: "#34C759" }}/>
            <span style={{ fontWeight: 700 }}>市場アシスタント</span>
            <span style={{ color: "var(--fg-tertiary)" }}>· 応答中</span>
            <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--fg-tertiary)" }}>セッション 09:00 開始</span>
          </div>

          <div style={{ flex: 1, overflow: "auto", padding: 22, display: "flex", flexDirection: "column", gap: 14 }}>
            {chat.map((m, i) => (
              <div key={i} style={{
                display: "flex",
                justifyContent: m.role === "user" ? "flex-end" : "flex-start",
                animation: "fadeIn 0.3s ease",
              }}>
                {m.role === "ai" && (
                  <div style={{
                    width: 32, height: 32, borderRadius: 10, marginRight: 8,
                    background: "linear-gradient(135deg, #5856D6, #0A84FF)",
                    color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 12, fontWeight: 800, flexShrink: 0,
                  }}>AI</div>
                )}
                <div style={{
                  maxWidth: "78%",
                  padding: "12px 16px", borderRadius: 16,
                  background: m.role === "user"
                    ? "linear-gradient(135deg, #5856D6, #0A84FF)"
                    : "var(--bg-surface-2)",
                  color: m.role === "user" ? "#fff" : "var(--fg-primary)",
                  fontSize: 13, lineHeight: 1.65,
                  borderTopRightRadius: m.role === "user" ? 4 : 16,
                  borderTopLeftRadius: m.role === "user" ? 16 : 4,
                  whiteSpace: "pre-wrap",
                }}>{m.text.split(/\*\*(.+?)\*\*/g).map((part, j) => (
                  j % 2 === 1
                    ? <b key={j} style={{ color: m.role === "user" ? "#fff" : "var(--c-power)" }}>{part}</b>
                    : <span key={j}>{part}</span>
                ))}</div>
                {m.role === "user" && (
                  <div style={{
                    width: 32, height: 32, borderRadius: 10, marginLeft: 8,
                    background: "var(--bg-surface-2)", color: "var(--fg-primary)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 12, fontWeight: 800, flexShrink: 0,
                    border: "1px solid var(--border)",
                  }}>李</div>
                )}
              </div>
            ))}
          </div>

          {/* Composer */}
          <div style={{ padding: 16, borderTop: "1px solid var(--border-subtle)" }}>
            <div style={{
              display: "flex", gap: 8, padding: 6,
              background: "var(--bg-surface-2)", borderRadius: 14,
              border: "1px solid var(--border-subtle)",
            }}>
              <input value={draft} onChange={e => setDraft(e.target.value)}
                onKeyDown={e => e.key === "Enter" && send()}
                placeholder="メッセージを入力..."
                style={{
                  flex: 1, border: "none", background: "transparent",
                  outline: "none", color: "var(--fg-primary)",
                  fontFamily: "inherit", fontSize: 13, padding: "10px 12px",
                }}/>
              <button onClick={send} style={{
                padding: "8px 18px", borderRadius: 10, border: "none",
                background: "linear-gradient(135deg, #5856D6, #0A84FF)",
                color: "#fff", fontFamily: "inherit", fontSize: 12, fontWeight: 700, cursor: "pointer",
              }}>送信</button>
            </div>
          </div>
        </div>

        {/* Side: suggestions + history */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14, minHeight: 0 }}>
          <div style={{
            background: "var(--bg-surface)", borderRadius: 18, padding: 18,
            border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
          }}>
            <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 10, letterSpacing: "0.04em" }}>提案</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {suggestions.map((s, i) => (
                <button key={i} onClick={() => setDraft(s)} style={{
                  textAlign: "left", padding: "10px 12px", borderRadius: 10,
                  background: "var(--bg-surface-2)", border: "1px solid var(--border-subtle)",
                  color: "var(--fg-primary)", fontFamily: "inherit", fontSize: 11.5,
                  fontWeight: 600, cursor: "pointer", lineHeight: 1.4,
                }}>{s}</button>
              ))}
            </div>
          </div>

          <div style={{
            background: "var(--bg-surface)", borderRadius: 18, padding: 18,
            border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)", flex: 1, overflow: "auto", minHeight: 0,
          }}>
            <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 10, letterSpacing: "0.04em" }}>最近のセッション</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {[
                ["LNG 価格分析",     "1/21"],
                ["週次需給レポート",  "1/20"],
                ["再エネ比率予測",    "1/19"],
                ["北海道エリア検証",  "1/18"],
              ].map(([t, d], i) => (
                <div key={i} style={{
                  padding: "10px 12px", borderRadius: 10, cursor: "pointer",
                  display: "flex", alignItems: "center", gap: 8,
                }}>
                  <span style={{ width: 6, height: 6, borderRadius: 999, background: "#5856D6" }}/>
                  <span style={{ flex: 1, fontSize: 12, fontWeight: 600 }}>{t}</span>
                  <span style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>{d}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// ── Notice Detail ──────────────────────────────────────
const NoticeDetail = ({ onBack }) => {
  const [filter, setFilter] = a6S("all");
  const items = filter === "all" ? A6.notices : A6.notices.filter(n => filter === "unread" ? n.unread : !n.unread);

  return (
    <div style={{ padding: 28 }}>
      <DetailHeader
        title="通知センター"
        subtitle="システム + 市場 + 業務 全通知"
        accent="#FF9500"
        icon="notice"
        onBack={onBack}
        badge={`未読 ${A6.notices.filter(n => n.unread).length}`}
      />

      <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
        {[["all", "全て"], ["unread", "未読"], ["read", "既読"]].map(([k, l]) => (
          <button key={k} onClick={() => setFilter(k)} style={{
            padding: "8px 16px", borderRadius: 10, border: "1px solid",
            borderColor: filter === k ? "#FF9500" : "var(--border)",
            background: filter === k ? "#FF9500" : "var(--bg-surface)",
            color: filter === k ? "#fff" : "var(--fg-primary)",
            fontFamily: "inherit", fontSize: 12, fontWeight: 700, cursor: "pointer",
          }}>{l}</button>
        ))}
        <button style={{
          marginLeft: "auto",
          padding: "8px 16px", borderRadius: 10, border: "1px solid var(--border)",
          background: "var(--bg-surface)", color: "var(--fg-secondary)",
          fontFamily: "inherit", fontSize: 12, fontWeight: 700, cursor: "pointer",
        }}>全て既読にする</button>
      </div>

      <div style={{
        background: "var(--bg-surface)", borderRadius: 18, padding: 8,
        border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
      }}>
        {items.map((n, i) => (
          <div key={i} style={{
            display: "flex", alignItems: "flex-start", gap: 14,
            padding: "16px 18px", borderRadius: 12,
            background: n.unread ? `${n.color}0D` : "transparent",
            borderLeft: n.unread ? `3px solid ${n.color}` : "3px solid transparent",
            marginBottom: 4,
          }}>
            <div style={{
              width: 40, height: 40, borderRadius: 12,
              background: `${n.color}1F`, color: n.color,
              display: "flex", alignItems: "center", justifyContent: "center",
              flexShrink: 0,
            }}>
              <Ic name={n.icon} size={20}/>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: 13, fontWeight: 800, color: "var(--fg-primary)" }}>{n.title}</span>
                {n.unread && <span style={{ width: 6, height: 6, borderRadius: 999, background: n.color }}/>}
                <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--fg-tertiary)", fontFamily: "var(--font-mono)" }}>{n.time}</span>
              </div>
              <div style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.5 }}>{n.body}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ── Memo Detail ──────────────────────────────────────
const MemoDetail = ({ onBack }) => {
  const [sel, setSel] = a6S(0);
  const cur = A6.memos[sel];

  return (
    <div style={{ padding: 28 }}>
      <DetailHeader
        title="メモ"
        subtitle={`${A6.memos.length} 件のノート`}
        accent="#FFCC00"
        icon="memo"
        onBack={onBack}
        badge="同期済"
      />

      <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: 16 }}>
        {/* List */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <button style={{
            padding: "10px", borderRadius: 12, border: "1px dashed var(--border)",
            background: "var(--bg-surface)", color: "var(--fg-secondary)",
            fontFamily: "inherit", fontSize: 12, fontWeight: 700, cursor: "pointer",
          }}>+ 新しいメモ</button>
          {A6.memos.map((m, i) => (
            <div key={i} onClick={() => setSel(i)} style={{
              padding: 14, borderRadius: 12, cursor: "pointer",
              background: i === sel ? "var(--bg-surface)" : "var(--bg-surface-2)",
              border: i === sel ? `1.5px solid ${m.color}` : "1px solid var(--border-subtle)",
              boxShadow: i === sel ? "var(--shadow-sm)" : "none",
              transition: "all 0.15s",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <span style={{ width: 10, height: 10, borderRadius: 3, background: m.color }}/>
                <div style={{ fontSize: 12, fontWeight: 800, flex: 1 }}>{m.title}</div>
              </div>
              <div style={{ fontSize: 10, color: "var(--fg-tertiary)", marginBottom: 4, fontFamily: "var(--font-mono)" }}>{m.date}</div>
              <div style={{ fontSize: 11, color: "var(--fg-secondary)", lineHeight: 1.5,
                display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
              }}>{m.body}</div>
            </div>
          ))}
        </div>

        {/* Editor */}
        <div style={{
          background: "var(--bg-surface)", borderRadius: 18, padding: 28,
          border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
          minHeight: 540,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
            <span style={{ width: 16, height: 16, borderRadius: 4, background: cur.color }}/>
            <input defaultValue={cur.title} style={{
              flex: 1, border: "none", outline: "none",
              background: "transparent", color: "var(--fg-primary)",
              fontFamily: "inherit", fontSize: 22, fontWeight: 800,
              letterSpacing: "-0.015em",
            }}/>
            <span style={{ fontSize: 11, color: "var(--fg-tertiary)", fontFamily: "var(--font-mono)" }}>{cur.date}</span>
          </div>
          <div style={{ display: "flex", gap: 6, marginBottom: 16, paddingBottom: 14, borderBottom: "1px solid var(--border-subtle)" }}>
            {["B", "I", "U", "•", "1.", "🔗"].map((b, i) => (
              <button key={i} style={{
                width: 32, height: 32, borderRadius: 8, border: "1px solid var(--border-subtle)",
                background: "var(--bg-surface-2)", color: "var(--fg-secondary)",
                fontFamily: "inherit", fontSize: 12, fontWeight: 700, cursor: "pointer",
              }}>{b}</button>
            ))}
          </div>
          <div style={{ fontSize: 14, color: "var(--fg-primary)", lineHeight: 1.8, whiteSpace: "pre-wrap" }}>
            {cur.body}
            {"\n\n"}
            <span style={{ color: "var(--fg-tertiary)" }}>—</span>
            {"\n\n"}
            関連リンク:
            {"\n"}・OCCTO 公式 (occto.or.jp)
            {"\n"}・JEPX スポット結果 (jepx.org)
            {"\n"}・社内 wiki: 需給対応プロトコル v3.2
          </div>
        </div>
      </div>
    </div>
  );
};

window.varA_detail_screens6 = { AiChatDetail, NoticeDetail, MemoDetail };
