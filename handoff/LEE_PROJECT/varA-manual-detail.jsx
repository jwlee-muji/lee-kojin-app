/* global React */
// ============================================================
// LEE — Manual Detail (共有マニュアル / Wiki)
// 多ユーザーが書き込み・編集・コメントできる社内 Wiki
// ============================================================
const { useState: mdS, useMemo: mdM, useRef: mdR, useEffect: mdE } = React;
const { DetailHeader: MD_DH } = window.varA_detail_atoms;

const MD_ACCENT = "#5856D6";
const MD_CURRENT_USER = "tanaka@shirokumapower.com";
const MD_ADMIN = "admin@shirokumapower.com";

// ── サンプルデータ (実装では SQLite 共有 DB から取得) ──
const MD_CATEGORIES = [
  "業務マニュアル",
  "システム操作",
  "トラブル対応",
  "新人向け",
  "FAQ",
  "未分類",
];

const MD_MANUALS = [
  {
    id: "m001",
    title: "JEPX スポット入札の手順",
    category: "業務マニュアル",
    tags: "スポット, JEPX, 入札",
    author: "tanaka@shirokumapower.com",
    updated: "2025-01-22 14:32",
    sections: [
      {
        subtitle: "事前準備",
        image: "https://images.unsplash.com/photo-1551836022-deb4988cc6c0?w=900&h=400&fit=crop",
        desc: "毎営業日 9:30 までに JEPX 会員サイトへログインし、当日のシステムプライス参考値を確認します。\n\n- 前日終値の確認\n- 燃料費・気温予報のチェック\n- 社内需給バランスの最新値を取得",
      },
      {
        subtitle: "入札画面の操作",
        image: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=900&h=400&fit=crop",
        desc: "JEPX サイトの「スポット入札」メニューから、30分コマごとに入札数量と価格を入力します。\n\n注意: 一度送信した入札は 10:00 のゲートクローズまでしか取り消せません。",
      },
      {
        subtitle: "送信後のチェック",
        image: "",
        desc: "10:00 ゲートクローズ後、約 10 分以内に約定結果が公表されます。LEE のスポット市場ウィジェットで自動更新されるので、社内 Slack チャンネルへ転送してください。",
      },
    ],
    comments: [
      { id: "c1", author: "yamada@shirokumapower.com", time: "2025-01-22 15:10", text: "9:30 → 9:00 に変更されました。次回更新時に修正お願いします。" },
      { id: "c2", author: "tanaka@shirokumapower.com", time: "2025-01-22 15:30", text: "確認しました。次回反映します！" },
    ],
  },
  {
    id: "m002",
    title: "OCCTO 予備率アラート対応フロー",
    category: "業務マニュアル",
    tags: "予備率, OCCTO, アラート",
    author: "yamada@shirokumapower.com",
    updated: "2025-01-20 09:11",
    sections: [
      {
        subtitle: "アラート受信時",
        image: "",
        desc: "予備率が 8% を下回ると LEE から自動通知が送られます。受信したら速やかに対象エリアと時間帯を確認します。",
      },
      {
        subtitle: "対応判断基準",
        image: "https://images.unsplash.com/photo-1473341304170-971dccb5ac1e?w=900&h=400&fit=crop",
        desc: "**8% 未満:** 注意喚起。需給状況を 30 分毎にモニタリング。\n**5% 未満:** 警報。揚水ポンプアップ、地域間融通の手配を即時開始。\n**3% 未満:** 緊急。需給ひっ迫警報を全社展開。",
      },
    ],
    comments: [],
  },
  {
    id: "m003",
    title: "LEE のインストール方法",
    category: "システム操作",
    tags: "セットアップ, インストール",
    author: "admin@shirokumapower.com",
    updated: "2025-01-15 11:00",
    sections: [
      {
        subtitle: "ダウンロード",
        image: "",
        desc: "社内ポータル → 業務システム → LEE 配布ページから最新版インストーラ (LEE-Setup-3.4.0.exe) をダウンロードします。",
      },
      {
        subtitle: "Google アカウント連携",
        image: "https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?w=900&h=400&fit=crop",
        desc: "起動後、社用 Google アカウント (xxx@shirokumapower.com) でログインしてください。カレンダーと Gmail の連携が自動で完了します。",
      },
    ],
    comments: [
      { id: "c3", author: "suzuki@shirokumapower.com", time: "2025-01-16 10:00", text: "Mac でも動きますか？" },
    ],
  },
  {
    id: "m004",
    title: "システムが起動しない時のチェックリスト",
    category: "トラブル対応",
    tags: "トラブル, 起動エラー",
    author: "tanaka@shirokumapower.com",
    updated: "2025-01-18 16:45",
    sections: [
      {
        subtitle: "1. ネットワーク確認",
        image: "",
        desc: "VPN に接続されているか確認してください。社外からのアクセスは VPN 必須です。",
      },
      {
        subtitle: "2. キャッシュクリア",
        image: "",
        desc: "%APPDATA%/LEE/cache フォルダを手動で削除してから再起動してみてください。",
      },
    ],
    comments: [],
  },
  {
    id: "m005",
    title: "新人向けクイックスタート",
    category: "新人向け",
    tags: "入社, 新人, ガイド",
    author: "yamada@shirokumapower.com",
    updated: "2025-01-10 09:00",
    sections: [
      {
        subtitle: "ようこそ！",
        image: "https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=900&h=400&fit=crop",
        desc: "LEE 電力モニターは、JEPX、OCCTO、気象データなどを統合した社内ダッシュボードです。本ドキュメントでは初日に必要な操作のみを抜粋しています。",
      },
      {
        subtitle: "最初に開く 3 つのウィジェット",
        image: "",
        desc: "1. **スポット市場** — 当日のシステムプライス確認\n2. **電力予備率** — 需給ひっ迫の有無\n3. **AI ブリーフィング** — 朝礼ネタを 1 分で把握",
      },
    ],
    comments: [],
  },
  {
    id: "m006",
    title: "Gmail 連携が切れた時の再認証",
    category: "FAQ",
    tags: "Gmail, 認証",
    author: "admin@shirokumapower.com",
    updated: "2025-01-08 13:20",
    sections: [
      {
        subtitle: "再認証手順",
        image: "",
        desc: "設定 → アカウント → Google 連携 から「再認証」をクリックしてください。ブラウザが起動するので社用アカウントでログインし直します。",
      },
    ],
    comments: [],
  },
];

// ── markdown もどき (太字 / 改行 / リスト / 見出し) のレンダリング ──
const md_renderText = (txt) => {
  if (!txt) return null;
  return txt.split("\n").map((line, i) => {
    let l = line;
    // bold
    l = l.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
    if (l.trim().startsWith("- ")) {
      return <div key={i} style={{ paddingLeft: 18, position: "relative", marginBottom: 4 }}>
        <span style={{ position: "absolute", left: 4, color: MD_ACCENT, fontWeight: 800 }}>•</span>
        <span dangerouslySetInnerHTML={{ __html: l.slice(2) }} />
      </div>;
    }
    if (/^\d+\.\s/.test(l.trim())) {
      return <div key={i} style={{ paddingLeft: 18, marginBottom: 4 }} dangerouslySetInnerHTML={{ __html: l }} />;
    }
    return l.trim() === ""
      ? <div key={i} style={{ height: 8 }} />
      : <div key={i} style={{ marginBottom: 6 }} dangerouslySetInnerHTML={{ __html: l }} />;
  });
};

// ── Tag chip ──
const MdTagChip = ({ text }) => (
  <span style={{
    display: "inline-flex", alignItems: "center", gap: 3,
    padding: "3px 9px", borderRadius: 999,
    background: `${MD_ACCENT}15`, color: MD_ACCENT,
    fontSize: 10, fontWeight: 800,
    border: `1px solid ${MD_ACCENT}30`,
    marginRight: 5,
  }}>
    <span style={{ opacity: 0.6 }}>#</span>{text}
  </span>
);

// ── 좌측 트리 ──
const ManualTree = ({ manuals, categories, currentId, onSelect, query }) => {
  const grouped = mdM(() => {
    const g = {};
    categories.forEach(c => { g[c] = []; });
    const q = query.trim().toLowerCase();
    manuals.forEach(m => {
      if (q && !(m.title.toLowerCase().includes(q) || (m.tags || "").toLowerCase().includes(q))) return;
      const cat = m.category || "未分類";
      (g[cat] = g[cat] || []).push(m);
    });
    return g;
  }, [manuals, categories, query]);

  const [collapsed, setCollapsed] = mdS({});
  const tog = (cat) => setCollapsed(c => ({ ...c, [cat]: !c[cat] }));

  return (
    <div style={{ overflow: "auto", flex: 1, padding: "0 4px" }}>
      {categories.map(cat => {
        const items = grouped[cat] || [];
        if (items.length === 0 && query.trim()) return null;
        const isCollapsed = collapsed[cat];
        return (
          <div key={cat} style={{ marginBottom: 4 }}>
            <button onClick={() => tog(cat)} style={{
              width: "100%", display: "flex", alignItems: "center", gap: 4,
              padding: "5px 6px", border: 0, background: "transparent",
              color: "var(--fg-secondary)", fontFamily: "inherit",
              fontSize: 10.5, fontWeight: 800, cursor: "pointer",
              letterSpacing: "0.04em", textTransform: "uppercase",
            }}>
              <span style={{
                display: "inline-block",
                transform: isCollapsed ? "rotate(-90deg)" : "rotate(0)",
                transition: "transform 0.15s", color: "var(--fg-tertiary)",
              }}>▾</span>
              <span style={{ flex: 1, textAlign: "left" }}>{cat}</span>
              <span style={{ fontSize: 9, color: "var(--fg-tertiary)", fontWeight: 700 }}>{items.length}</span>
            </button>
            {!isCollapsed && items.map(m => (
              <button key={m.id} onClick={() => onSelect(m.id)}
                style={{
                  width: "100%", display: "block", textAlign: "left",
                  padding: "6px 10px 6px 22px", border: 0, borderRadius: 6,
                  marginBottom: 1,
                  background: currentId === m.id ? `${MD_ACCENT}1f` : "transparent",
                  color: currentId === m.id ? MD_ACCENT : "var(--fg-primary)",
                  fontFamily: "inherit", fontSize: 11.5,
                  fontWeight: currentId === m.id ? 700 : 500,
                  cursor: "pointer",
                }}>
                {m.title}
              </button>
            ))}
          </div>
        );
      })}
    </div>
  );
};

// ── ビューア ──
const ManualViewer = ({ manual, onCommentAdd }) => {
  const [comment, setComment] = mdS("");
  const send = () => {
    if (!comment.trim()) return;
    onCommentAdd(comment);
    setComment("");
  };

  return (
    <div style={{ flex: 1, overflow: "auto", padding: "24px 36px" }}>
      {/* タグ */}
      {manual.tags && (
        <div style={{ marginBottom: 12 }}>
          {manual.tags.split(",").map(t => t.trim()).filter(Boolean).map(t => <MdTagChip key={t} text={t} />)}
        </div>
      )}

      {/* タイトル */}
      <h1 style={{
        fontSize: 26, fontWeight: 800, margin: "0 0 6px",
        color: MD_ACCENT, paddingBottom: 8,
        borderBottom: `2px solid ${MD_ACCENT}`,
        letterSpacing: "-0.02em",
      }}>{manual.title}</h1>

      <div style={{
        display: "flex", alignItems: "center", gap: 10,
        fontSize: 11, color: "var(--fg-tertiary)", marginBottom: 22,
      }}>
        <span>👤 {manual.author.split("@")[0]}</span>
        <span>•</span>
        <span>📅 {manual.updated}</span>
        <span>•</span>
        <span style={{
          padding: "2px 8px", borderRadius: 4,
          background: "var(--bg-surface-2)", fontWeight: 700,
        }}>{manual.category}</span>
      </div>

      {/* セクション */}
      {manual.sections.map((sec, i) => (
        <div key={i} style={{ marginBottom: 28 }}>
          {sec.subtitle && (
            <h2 style={{
              fontSize: 17, fontWeight: 700, margin: "0 0 10px",
              paddingLeft: 12, borderLeft: `4px solid ${MD_ACCENT}`,
              color: "var(--fg-primary)",
            }}>
              <span style={{ color: MD_ACCENT, marginRight: 6 }}>{i + 1}.</span>
              {sec.subtitle}
            </h2>
          )}
          {sec.image && (
            <div style={{ marginBottom: 10, borderRadius: 10, overflow: "hidden", border: "1px solid var(--border-subtle)" }}>
              <img src={sec.image} alt="" style={{ width: "100%", display: "block", maxHeight: 280, objectFit: "cover" }} />
            </div>
          )}
          {sec.desc && (
            <div style={{ fontSize: 13.5, color: "var(--fg-primary)", lineHeight: 1.75 }}>
              {md_renderText(sec.desc)}
            </div>
          )}
          {i < manual.sections.length - 1 && (
            <div style={{ height: 1, background: "var(--border-subtle)", margin: "20px 0 0" }} />
          )}
        </div>
      ))}

      {/* コメント */}
      <div style={{
        marginTop: 32, paddingTop: 18,
        borderTop: "1px solid var(--border-subtle)",
      }}>
        <div style={{
          fontSize: 11, fontWeight: 800, color: "var(--fg-tertiary)",
          letterSpacing: "0.06em", marginBottom: 12,
          display: "flex", alignItems: "center", gap: 6,
        }}>
          💬 コメント
          <span style={{
            padding: "1px 8px", borderRadius: 999,
            background: "var(--bg-surface-2)", color: "var(--fg-secondary)",
            fontSize: 10, fontWeight: 800,
          }}>{manual.comments.length}</span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 14 }}>
          {manual.comments.length === 0 ? (
            <div style={{
              padding: 20, textAlign: "center", borderRadius: 10,
              background: "var(--bg-surface-2)", color: "var(--fg-tertiary)",
              fontSize: 11.5, border: "1px dashed var(--border-subtle)",
            }}>まだコメントはありません</div>
          ) : manual.comments.map(c => {
            const isMine = c.author === MD_CURRENT_USER;
            return (
              <div key={c.id} style={{
                padding: "10px 14px", borderRadius: 10,
                background: isMine ? `${MD_ACCENT}10` : "var(--bg-surface-2)",
                border: `1px solid ${isMine ? `${MD_ACCENT}30` : "var(--border-subtle)"}`,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <div style={{
                    width: 22, height: 22, borderRadius: 999,
                    background: isMine ? MD_ACCENT : "var(--bg-surface)",
                    color: isMine ? "#fff" : "var(--fg-secondary)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 10, fontWeight: 800,
                    border: "1px solid var(--border-subtle)",
                  }}>{c.author[0].toUpperCase()}</div>
                  <span style={{ fontSize: 11.5, fontWeight: 700, color: "var(--fg-primary)" }}>
                    {c.author.split("@")[0]}
                  </span>
                  <span style={{ fontSize: 10, color: "var(--fg-tertiary)", fontFamily: "var(--font-mono)" }}>
                    {c.time}
                  </span>
                </div>
                <div style={{ fontSize: 12, color: "var(--fg-primary)", lineHeight: 1.6, paddingLeft: 30 }}>
                  {c.text}
                </div>
              </div>
            );
          })}
        </div>

        <div style={{
          display: "flex", gap: 6, alignItems: "stretch",
          padding: 4, borderRadius: 10,
          border: "1px solid var(--border-subtle)",
          background: "var(--bg-surface-2)",
        }}>
          <input
            value={comment}
            onChange={e => setComment(e.target.value)}
            onKeyDown={e => e.key === "Enter" && send()}
            placeholder="コメントを入力..."
            style={{
              flex: 1, border: 0, outline: 0,
              background: "transparent", color: "var(--fg-primary)",
              fontFamily: "inherit", fontSize: 12, padding: "6px 10px",
            }}
          />
          <button onClick={send} style={{
            padding: "0 16px", border: 0, borderRadius: 7,
            background: MD_ACCENT, color: "#fff",
            fontFamily: "inherit", fontSize: 11, fontWeight: 800,
            cursor: "pointer",
          }}>送信</button>
        </div>
      </div>
    </div>
  );
};

// ── セクション編集行 ──
const SectionEditor = ({ sec, idx, onChange, onRemove, onMove, onPickImage }) => {
  return (
    <div style={{
      padding: 12, borderRadius: 10,
      background: "var(--bg-surface-2)",
      border: "1px solid var(--border-subtle)",
      marginBottom: 10,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
        <span style={{
          width: 22, height: 22, borderRadius: 6,
          background: MD_ACCENT, color: "#fff",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 11, fontWeight: 800,
        }}>{idx + 1}</span>
        <input
          value={sec.subtitle}
          onChange={e => onChange("subtitle", e.target.value)}
          placeholder="項目の見出し..."
          style={{
            flex: 1, padding: "6px 10px", borderRadius: 7,
            border: "1px solid var(--border-subtle)",
            background: "var(--bg-surface)", color: "var(--fg-primary)",
            fontFamily: "inherit", fontSize: 12.5, fontWeight: 700,
          }}
        />
        <button onClick={() => onMove(-1)} title="上へ" style={iconBtn}>▲</button>
        <button onClick={() => onMove(1)} title="下へ" style={iconBtn}>▼</button>
        <button onClick={onRemove} title="削除" style={{ ...iconBtn, color: "#FF453A" }}>✕</button>
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
        <button onClick={onPickImage} style={{
          padding: "6px 12px", borderRadius: 7,
          border: "1px dashed var(--border-subtle)",
          background: sec.image ? `${MD_ACCENT}10` : "var(--bg-surface)",
          color: sec.image ? MD_ACCENT : "var(--fg-secondary)",
          fontFamily: "inherit", fontSize: 11, fontWeight: 700, cursor: "pointer",
        }}>📷 {sec.image ? "画像を変更" : "画像を選択"}</button>
        {sec.image && (
          <>
            <span style={{ flex: 1, fontSize: 10.5, color: "var(--fg-tertiary)", fontFamily: "var(--font-mono)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {sec.image.split("/").pop().split("?")[0]}
            </span>
            <button onClick={() => onChange("image", "")} style={iconBtn}>🗑</button>
          </>
        )}
      </div>

      {sec.image && (
        <div style={{ marginBottom: 8, borderRadius: 8, overflow: "hidden", maxHeight: 140 }}>
          <img src={sec.image} alt="" style={{ width: "100%", display: "block", maxHeight: 140, objectFit: "cover" }} />
        </div>
      )}

      <textarea
        value={sec.desc}
        onChange={e => onChange("desc", e.target.value)}
        placeholder="詳細説明 (Markdown 対応: **太字**, - リスト)..."
        style={{
          width: "100%", minHeight: 90, padding: 10, borderRadius: 7,
          border: "1px solid var(--border-subtle)",
          background: "var(--bg-surface)", color: "var(--fg-primary)",
          fontFamily: "inherit", fontSize: 12, lineHeight: 1.6,
          resize: "vertical", boxSizing: "border-box",
        }}
      />
    </div>
  );
};

const iconBtn = {
  width: 26, height: 26, borderRadius: 6,
  border: "1px solid var(--border-subtle)",
  background: "var(--bg-surface)", color: "var(--fg-secondary)",
  fontFamily: "inherit", fontSize: 10, fontWeight: 800, cursor: "pointer",
};

// ── エディタ ──
const ManualEditor = ({ manual, categories, isNew, onSave, onCancel, onShowImageEdit }) => {
  const [title, setTitle] = mdS(manual?.title || "");
  const [category, setCategory] = mdS(manual?.category || "未分類");
  const [tags, setTags] = mdS(manual?.tags || "");
  const [sections, setSections] = mdS(
    manual?.sections?.length ? manual.sections : [{ subtitle: "", image: "", desc: "" }]
  );

  const updateSec = (i, field, val) => {
    setSections(s => s.map((sec, idx) => idx === i ? { ...sec, [field]: val } : sec));
  };
  const moveSec = (i, dir) => {
    const j = i + dir;
    if (j < 0 || j >= sections.length) return;
    const ns = [...sections];
    [ns[i], ns[j]] = [ns[j], ns[i]];
    setSections(ns);
  };
  const removeSec = (i) => setSections(s => s.length > 1 ? s.filter((_, idx) => idx !== i) : s);
  const addSec = () => setSections(s => [...s, { subtitle: "", image: "", desc: "" }]);

  return (
    <div style={{ flex: 1, overflow: "auto", padding: "20px 28px" }}>
      <div style={{ display: "grid", gridTemplateColumns: "180px 1fr 220px", gap: 8, marginBottom: 14 }}>
        <select value={category} onChange={e => setCategory(e.target.value)} style={inpStyle}>
          {categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <input value={title} onChange={e => setTitle(e.target.value)} placeholder="タイトル..." style={{ ...inpStyle, fontWeight: 700 }} />
        <input value={tags} onChange={e => setTags(e.target.value)} placeholder="タグ (カンマ区切り)" style={inpStyle} />
      </div>

      <div style={{ marginBottom: 12 }}>
        {sections.map((sec, i) => (
          <SectionEditor
            key={i} sec={sec} idx={i}
            onChange={(f, v) => updateSec(i, f, v)}
            onRemove={() => removeSec(i)}
            onMove={(dir) => moveSec(i, dir)}
            onPickImage={() => onShowImageEdit((url) => updateSec(i, "image", url))}
          />
        ))}
      </div>

      <button onClick={addSec} style={{
        width: "100%", padding: "10px 12px", borderRadius: 9,
        border: "1px dashed var(--border)",
        background: "var(--bg-surface)", color: MD_ACCENT,
        fontFamily: "inherit", fontSize: 12, fontWeight: 800, cursor: "pointer",
        marginBottom: 14,
      }}>＋ 項目を追加</button>

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <button onClick={onCancel} style={btnSecondary}>キャンセル</button>
        <button onClick={() => onSave({ title, category, tags, sections })} style={btnPrimary}>
          {isNew ? "作成" : "保存"}
        </button>
      </div>
    </div>
  );
};

const inpStyle = {
  padding: "8px 12px", borderRadius: 8,
  border: "1px solid var(--border)",
  background: "var(--bg-surface-2)", color: "var(--fg-primary)",
  fontFamily: "inherit", fontSize: 12.5,
  boxSizing: "border-box", width: "100%",
};
const btnSecondary = {
  padding: "8px 16px", borderRadius: 8,
  border: "1px solid var(--border)",
  background: "var(--bg-surface-2)", color: "var(--fg-secondary)",
  fontFamily: "inherit", fontSize: 12, fontWeight: 700, cursor: "pointer",
};
const btnPrimary = {
  padding: "8px 18px", borderRadius: 8, border: 0,
  background: MD_ACCENT, color: "#fff",
  fontFamily: "inherit", fontSize: 12, fontWeight: 800, cursor: "pointer",
};

// ── カテゴリ管理ダイアログ ──
const CategoryManagerDialog = ({ cats, onClose, onUpdate }) => {
  const [list, setList] = mdS(cats);
  const [newCat, setNewCat] = mdS("");

  const move = (i, dir) => {
    const j = i + dir;
    if (j < 0 || j >= list.length) return;
    const n = [...list]; [n[i], n[j]] = [n[j], n[i]]; setList(n);
  };
  const rename = (i) => {
    const v = prompt("新しいカテゴリ名:", list[i]);
    if (v && v.trim()) setList(list.map((c, idx) => idx === i ? v.trim() : c));
  };
  const remove = (i) => setList(list.filter((_, idx) => idx !== i));
  const add = () => {
    if (newCat.trim() && !list.includes(newCat.trim())) {
      setList([...list, newCat.trim()]); setNewCat("");
    }
  };

  return (
    <div style={dialogBg} onClick={onClose}>
      <div style={dialogBox} onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", marginBottom: 14 }}>
          <div style={{ flex: 1, fontSize: 16, fontWeight: 800 }}>⚙️ カテゴリ管理</div>
          <button onClick={onClose} style={iconBtn}>✕</button>
        </div>

        <div style={{
          maxHeight: 320, overflow: "auto", marginBottom: 12,
          border: "1px solid var(--border-subtle)", borderRadius: 8,
        }}>
          {list.map((c, i) => (
            <div key={c} style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "8px 10px",
              borderBottom: i < list.length - 1 ? "1px solid var(--border-subtle)" : 0,
            }}>
              <span style={{ flex: 1, fontSize: 12.5, fontWeight: 600 }}>{c}</span>
              <button onClick={() => move(i, -1)} style={iconBtn}>▲</button>
              <button onClick={() => move(i, 1)} style={iconBtn}>▼</button>
              <button onClick={() => rename(i)} style={iconBtn}>✎</button>
              <button onClick={() => remove(i)} style={{ ...iconBtn, color: "#FF453A" }}>🗑</button>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
          <input
            value={newCat} onChange={e => setNewCat(e.target.value)}
            onKeyDown={e => e.key === "Enter" && add()}
            placeholder="新しいカテゴリ名..."
            style={{ ...inpStyle, fontSize: 12 }}
          />
          <button onClick={add} style={btnPrimary}>＋ 追加</button>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button onClick={onClose} style={btnSecondary}>キャンセル</button>
          <button onClick={() => onUpdate(list)} style={btnPrimary}>適用</button>
        </div>
      </div>
    </div>
  );
};

// ── 画像エディタダイアログ (ペン/矩形/チェック/テキスト/クロップ) ──
const ImageEditDialog = ({ onCancel, onConfirm }) => {
  const [tool, setTool] = mdS("pen");
  const [color, setColor] = mdS("#FF453A");
  const [width, setWidth] = mdS(4);
  // sample image
  const sampleUrl = "https://images.unsplash.com/photo-1551836022-deb4988cc6c0?w=900&h=400&fit=crop";

  const tools = [
    { id: "pen", label: "✎", name: "ペン" },
    { id: "rect", label: "▢", name: "矩形" },
    { id: "check", label: "✓", name: "チェック" },
    { id: "text", label: "T", name: "テキスト" },
    { id: "crop", label: "⌗", name: "クロップ" },
    { id: "move", label: "✥", name: "移動" },
  ];

  return (
    <div style={dialogBg} onClick={onCancel}>
      <div style={{
        ...dialogBox, width: "min(92vw, 800px)", maxHeight: "90vh",
        display: "flex", flexDirection: "column",
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", marginBottom: 12 }}>
          <div style={{ flex: 1, fontSize: 16, fontWeight: 800 }}>🎨 画像エディタ</div>
          <button onClick={onCancel} style={iconBtn}>✕</button>
        </div>

        {/* ツールバー */}
        <div style={{
          display: "flex", alignItems: "center", gap: 6, padding: 8, marginBottom: 10,
          background: "var(--bg-surface-2)", borderRadius: 9,
          border: "1px solid var(--border-subtle)",
        }}>
          {tools.map(t => (
            <button key={t.id} onClick={() => setTool(t.id)} title={t.name} style={{
              width: 32, height: 32, borderRadius: 7,
              border: "1px solid var(--border-subtle)",
              background: tool === t.id ? MD_ACCENT : "var(--bg-surface)",
              color: tool === t.id ? "#fff" : "var(--fg-primary)",
              fontFamily: "inherit", fontSize: 14, fontWeight: 800, cursor: "pointer",
            }}>{t.label}</button>
          ))}
          <div style={{ width: 1, height: 20, background: "var(--border-subtle)", margin: "0 4px" }} />
          {["#FF453A", "#FF9F0A", "#34C759", "#0A84FF", "#5856D6", "#000", "#fff"].map(c => (
            <button key={c} onClick={() => setColor(c)} style={{
              width: 22, height: 22, borderRadius: 999,
              background: c, border: color === c ? `2px solid var(--fg-primary)` : "1px solid var(--border-subtle)",
              cursor: "pointer",
            }} />
          ))}
          <div style={{ width: 1, height: 20, background: "var(--border-subtle)", margin: "0 4px" }} />
          <input type="range" min="1" max="20" value={width} onChange={e => setWidth(+e.target.value)}
            style={{ width: 90 }} />
          <span style={{ fontSize: 10, color: "var(--fg-tertiary)", fontFamily: "var(--font-mono)", width: 24 }}>{width}px</span>
          <div style={{ flex: 1 }} />
          <button style={btnSecondary}>↶ 元に戻す</button>
          <button style={btnSecondary}>🗑 全削除</button>
        </div>

        {/* キャンバス (モック) */}
        <div style={{
          flex: 1, minHeight: 320, borderRadius: 10, overflow: "hidden",
          background: "var(--bg-surface-2)",
          border: "1px solid var(--border-subtle)",
          display: "flex", alignItems: "center", justifyContent: "center",
          position: "relative",
        }}>
          <img src={sampleUrl} alt="" style={{ maxWidth: "100%", maxHeight: 380, display: "block" }} />
          {/* オーバーレイ注釈モック */}
          <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}>
            <path d="M120 100 Q 200 80, 280 110 T 420 130" stroke="#FF453A" strokeWidth="3" fill="none" strokeLinecap="round" />
            <rect x="380" y="180" width="160" height="80" stroke="#FF9F0A" strokeWidth="3" fill="none" rx="4" />
            <text x="395" y="220" fill="#FF453A" fontSize="20" fontWeight="800" fontFamily="sans-serif">重要！</text>
          </svg>
        </div>

        <div style={{
          fontSize: 10, color: "var(--fg-tertiary)", textAlign: "center",
          padding: "8px 0",
        }}>Ctrl+ホイール: ズーム — ドラッグで描画</div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 6 }}>
          <button onClick={onCancel} style={btnSecondary}>キャンセル</button>
          <button onClick={() => onConfirm(sampleUrl)} style={btnPrimary}>挿入</button>
        </div>
      </div>
    </div>
  );
};

const dialogBg = {
  position: "fixed", inset: 0, zIndex: 9999,
  background: "rgba(0,0,0,0.5)", backdropFilter: "blur(4px)",
  display: "flex", alignItems: "center", justifyContent: "center",
};
const dialogBox = {
  background: "var(--bg-surface)", color: "var(--fg-primary)",
  width: "min(92vw, 480px)", padding: 20, borderRadius: 14,
  border: "1px solid var(--border-subtle)",
  boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
};

// ============================================================
// Main: ManualDetail
// ============================================================
const ManualDetail = ({ onBack }) => {
  const [manuals, setManuals] = mdS(MD_MANUALS);
  const [categories, setCategories] = mdS(MD_CATEGORIES);
  const [currentId, setCurrentId] = mdS(MD_MANUALS[0].id);
  const [query, setQuery] = mdS("");
  const [mode, setMode] = mdS("view"); // 'view' | 'edit' | 'new'
  const [showCatMgr, setShowCatMgr] = mdS(false);
  const [imageEditCb, setImageEditCb] = mdS(null);
  const [historyStack, setHistoryStack] = mdS([]);

  const current = mdM(() => manuals.find(m => m.id === currentId), [manuals, currentId]);

  const canEdit = current && (current.author === MD_CURRENT_USER || MD_CURRENT_USER === MD_ADMIN);

  const handleSelect = (id) => {
    if (mode !== "view") {
      if (!confirm("編集中の内容は失われます。よろしいですか？")) return;
    }
    if (currentId && currentId !== id) {
      setHistoryStack(s => [...s, currentId]);
    }
    setCurrentId(id);
    setMode("view");
  };

  const handleSave = (data) => {
    if (mode === "new") {
      const id = "m" + Date.now();
      const newM = {
        id, ...data,
        author: MD_CURRENT_USER,
        updated: new Date().toISOString().slice(0, 16).replace("T", " "),
        comments: [],
      };
      setManuals(ms => [newM, ...ms]);
      setCurrentId(id);
    } else {
      setManuals(ms => ms.map(m => m.id === currentId ? {
        ...m, ...data,
        updated: new Date().toISOString().slice(0, 16).replace("T", " "),
      } : m));
    }
    setMode("view");
  };

  const handleDelete = () => {
    if (!current) return;
    if (!confirm(`「${current.title}」を削除しますか？`)) return;
    setManuals(ms => ms.filter(m => m.id !== currentId));
    setCurrentId(manuals[0]?.id || null);
  };

  const handleCommentAdd = (text) => {
    setManuals(ms => ms.map(m => m.id === currentId ? {
      ...m,
      comments: [...m.comments, {
        id: "c" + Date.now(),
        author: MD_CURRENT_USER,
        time: new Date().toISOString().slice(0, 16).replace("T", " "),
        text,
      }],
    } : m));
  };

  const handleCopyLink = () => {
    if (!current) return;
    const link = `lee://manual/${current.id}`;
    if (navigator.clipboard) navigator.clipboard.writeText(link);
    alert(`リンクをコピーしました:\n${link}`);
  };

  const handleBack = () => {
    if (historyStack.length === 0) return;
    const prev = historyStack[historyStack.length - 1];
    setHistoryStack(s => s.slice(0, -1));
    setCurrentId(prev);
    setMode("view");
  };

  const handleNew = () => {
    setMode("new");
  };

  return (
    <div style={{ padding: 24, maxWidth: 1280, height: "100%", display: "flex", flexDirection: "column" }}>
      <MD_DH title="共有マニュアル (Wiki)" subtitle="社内ナレッジ共有 — 全ユーザーが閲覧可能" accent={MD_ACCENT} icon="manual" onBack={onBack} />

      <div style={{
        flex: 1, minHeight: 0,
        display: "grid", gridTemplateColumns: "260px 1fr",
        gap: 12,
        background: "var(--bg-surface)", borderRadius: 16,
        border: "1px solid var(--border-subtle)",
        boxShadow: "var(--shadow-sm)",
        overflow: "hidden",
      }}>
        {/* ─── 左: ツリー ─── */}
        <div style={{
          display: "flex", flexDirection: "column",
          background: "var(--bg-surface-2)",
          borderRight: "1px solid var(--border-subtle)",
          padding: 10,
        }}>
          <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
            <div style={{
              flex: 1, display: "flex", alignItems: "center", gap: 4,
              padding: "5px 9px", borderRadius: 7,
              background: "var(--bg-surface)",
              border: "1px solid var(--border-subtle)",
            }}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--fg-tertiary)" strokeWidth="2.5"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              <input value={query} onChange={e => setQuery(e.target.value)}
                placeholder="検索..."
                style={{
                  flex: 1, border: 0, outline: 0,
                  background: "transparent", color: "var(--fg-primary)",
                  fontFamily: "inherit", fontSize: 11,
                }} />
            </div>
            <button onClick={() => setShowCatMgr(true)} title="カテゴリ管理" style={iconBtn}>⚙</button>
            <button title="更新" style={iconBtn}>↻</button>
          </div>

          <ManualTree
            manuals={manuals} categories={categories}
            currentId={currentId} onSelect={handleSelect} query={query}
          />

          <button onClick={handleNew} style={{
            marginTop: 8, padding: "9px 12px", borderRadius: 9, border: 0,
            background: MD_ACCENT, color: "#fff",
            fontFamily: "inherit", fontSize: 12, fontWeight: 800, cursor: "pointer",
          }}>＋ 新規マニュアル作成</button>
        </div>

        {/* ─── 右: ビューア / エディタ ─── */}
        <div style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
          {/* ツールバー */}
          <div style={{
            display: "flex", alignItems: "center", gap: 6,
            padding: "10px 14px",
            borderBottom: "1px solid var(--border-subtle)",
            background: "var(--bg-surface)",
          }}>
            {historyStack.length > 0 && mode === "view" && (
              <button onClick={handleBack} style={btnSecondary}>◀ 戻る</button>
            )}
            <div style={{ flex: 1 }} />
            {mode === "view" && current && (
              <>
                <button style={btnSecondary} onClick={() => alert("PDF エクスポート (mock)")}>📄 PDF</button>
                <button style={btnSecondary} onClick={handleCopyLink}>🔗 リンクコピー</button>
                {canEdit && (
                  <>
                    <button style={btnSecondary} onClick={() => setMode("edit")}>✏️ 編集</button>
                    <button style={{ ...btnSecondary, color: "#FF453A" }} onClick={handleDelete}>🗑 削除</button>
                  </>
                )}
                {!canEdit && (
                  <span style={{
                    padding: "5px 10px", borderRadius: 999,
                    background: "var(--bg-surface-2)", color: "var(--fg-tertiary)",
                    fontSize: 10, fontWeight: 700,
                  }}>👁 閲覧のみ</span>
                )}
              </>
            )}
            {mode !== "view" && (
              <span style={{
                padding: "5px 10px", borderRadius: 999,
                background: `${MD_ACCENT}1f`, color: MD_ACCENT,
                fontSize: 10, fontWeight: 800,
              }}>{mode === "new" ? "新規作成中" : "編集中"}</span>
            )}
          </div>

          {/* コンテンツ */}
          {mode === "view" && current && (
            <ManualViewer manual={current} onCommentAdd={handleCommentAdd} />
          )}
          {mode === "view" && !current && (
            <div style={{
              flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
              color: "var(--fg-tertiary)", fontSize: 13,
            }}>マニュアルを選択してください</div>
          )}
          {(mode === "edit" || mode === "new") && (
            <ManualEditor
              manual={mode === "edit" ? current : null}
              categories={categories}
              isNew={mode === "new"}
              onSave={handleSave}
              onCancel={() => setMode("view")}
              onShowImageEdit={(cb) => setImageEditCb(() => cb)}
            />
          )}
        </div>
      </div>

      {showCatMgr && (
        <CategoryManagerDialog
          cats={categories}
          onClose={() => setShowCatMgr(false)}
          onUpdate={(newList) => { setCategories(newList); setShowCatMgr(false); }}
        />
      )}
      {imageEditCb && (
        <ImageEditDialog
          onCancel={() => setImageEditCb(null)}
          onConfirm={(url) => { imageEditCb(url); setImageEditCb(null); }}
        />
      )}
    </div>
  );
};

window.varA_manual_detail = { ManualDetail };
