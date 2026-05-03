/* global React */
// ============================================================
// LEE — Settings / Briefing / Bug Report
// 実コード (app/widgets/settings.py, briefing.py, bug_report.py) 反映版
// ============================================================
const { useState: m2S, useMemo: m2M, useEffect: m2E, useRef: m2R } = React;
const { DetailHeader: M2_DH } = window.varA_detail_atoms;
const M2_D = window.LEE_DATA;

// ============================================================
// 共通プリミティブ — モダンなカード + フォーム要素
// ============================================================
// 各セクションのアイコン (絵文字を 小さなカラーチップ + Unicode に置換)
const SECTION_TONES = {
  alert:    { color: "#FF453A", bg: "#FF453A18" },
  refresh:  { color: "#0A84FF", bg: "#0A84FF18" },
  google:   { color: "#34C759", bg: "#34C75918" },
  ai:       { color: "#AF52DE", bg: "#AF52DE18" },
  data:     { color: "#FF9F0A", bg: "#FF9F0A18" },
  app:      { color: "#5E5CE6", bg: "#5E5CE618" },
  users:    { color: "#FF2D92", bg: "#FF2D9218" },
};

const PyGroup = ({ title, tone = "app", anchor, children, style }) => {
  const t = SECTION_TONES[tone] || SECTION_TONES.app;
  return (
    <section id={anchor} style={{
      background: "var(--bg-surface)",
      border: "1px solid var(--border-subtle)",
      borderRadius: 14,
      padding: "18px 20px 16px",
      boxShadow: "var(--shadow-sm)",
      marginBottom: 14,
      scrollMarginTop: 28,
      ...(style || {}),
    }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 10,
        marginBottom: 14, paddingBottom: 12,
        borderBottom: "1px solid var(--border-subtle)",
      }}>
        <span style={{
          width: 28, height: 28, borderRadius: 8,
          background: t.bg, color: t.color,
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          fontSize: 13, fontWeight: 800,
          flexShrink: 0,
        }}>
          <SectionIcon tone={tone}/>
        </span>
        <div style={{ fontSize: 14, fontWeight: 800, color: "var(--fg-primary)", letterSpacing: 0.2 }}>
          {title}
        </div>
      </div>
      {children}
    </section>
  );
};

const SectionIcon = ({ tone }) => {
  // 단순한 라인 SVG 아이콘
  const stroke = "currentColor";
  const sw = 1.8;
  switch (tone) {
    case "alert":   return <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 4l9 16H3z" stroke={stroke} strokeWidth={sw} strokeLinejoin="round"/><path d="M12 11v4" stroke={stroke} strokeWidth={sw} strokeLinecap="round"/><circle cx="12" cy="17.5" r="0.7" fill={stroke}/></svg>;
    case "refresh": return <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M4 12a8 8 0 0 1 14.6-4.5L21 5" stroke={stroke} strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"/><path d="M21 5v4h-4" stroke={stroke} strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"/><path d="M20 12a8 8 0 0 1-14.6 4.5L3 19" stroke={stroke} strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"/><path d="M3 19v-4h4" stroke={stroke} strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"/></svg>;
    case "google":  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke={stroke} strokeWidth={sw}/><path d="M8 12l3 3 5-6" stroke={stroke} strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"/></svg>;
    case "ai":      return <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 3l1.8 4.2L18 9l-4.2 1.8L12 15l-1.8-4.2L6 9l4.2-1.8z" stroke={stroke} strokeWidth={sw} strokeLinejoin="round"/><path d="M18 16l.9 2.1L21 19l-2.1.9L18 22l-.9-2.1L15 19l2.1-.9z" stroke={stroke} strokeWidth={sw} strokeLinejoin="round"/></svg>;
    case "data":    return <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><ellipse cx="12" cy="6" rx="8" ry="3" stroke={stroke} strokeWidth={sw}/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6" stroke={stroke} strokeWidth={sw}/><path d="M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" stroke={stroke} strokeWidth={sw}/></svg>;
    case "app":     return <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="3" stroke={stroke} strokeWidth={sw}/><path d="M19.4 14a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V20a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H4a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 5.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H10a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" stroke={stroke} strokeWidth={1.4}/></svg>;
    case "users":   return <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="9" cy="8" r="3.2" stroke={stroke} strokeWidth={sw}/><path d="M3.5 19c.7-3 3-4.5 5.5-4.5s4.8 1.5 5.5 4.5" stroke={stroke} strokeWidth={sw} strokeLinecap="round"/><circle cx="17" cy="9" r="2.4" stroke={stroke} strokeWidth={sw}/><path d="M15 19c.5-2 1.7-3 3.5-3 1.4 0 2.6.7 3 2" stroke={stroke} strokeWidth={sw} strokeLinecap="round"/></svg>;
    default:        return null;
  }
};

const PyFormRow = ({ label, hint, children, dirty = false }) => (
  <div style={{
    padding: "10px 0",
    borderBottom: "1px solid var(--border-subtle)",
  }}>
    <div style={{
      display: "grid",
      gridTemplateColumns: "minmax(180px, 240px) 1fr",
      columnGap: 20,
      alignItems: "center",
    }}>
      <label style={{
        fontSize: 12, fontWeight: 600, color: "var(--fg-secondary)",
        display: "inline-flex", alignItems: "center", gap: 6,
      }}>
        {label}
        {dirty && <span title="未保存" style={{ width: 6, height: 6, borderRadius: 999, background: "#FF9F0A", display: "inline-block" }}/>}
      </label>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        {children}
      </div>
    </div>
    {hint && (
      <div style={{
        fontSize: 11, color: "var(--fg-tertiary)",
        marginTop: 6, marginLeft: 0, lineHeight: 1.5,
        gridColumn: "1 / -1",
      }}>{hint}</div>
    )}
  </div>
);

// モダン Spinner: ステッパー + 数値入力
const PySpin = ({ value, onChange, min = 0, max = 9999, step = 1, suffix = "", width = 144 }) => {
  const inc = () => onChange(Math.min(max, +(value + step).toFixed(2)));
  const dec = () => onChange(Math.max(min, +(value - step).toFixed(2)));
  return (
    <div style={{
      display: "inline-flex", alignItems: "stretch",
      border: "1px solid var(--border)",
      borderRadius: 8,
      background: "var(--bg-surface-2)",
      height: 34,
      width,
      overflow: "hidden",
      transition: "border-color .15s",
    }}
    onFocus={(e) => e.currentTarget.style.borderColor = "var(--accent)"}
    onBlur={(e) => e.currentTarget.style.borderColor = "var(--border)"}
    >
      <button type="button" onClick={dec} style={pySpinBtn} aria-label="-">−</button>
      <input
        type="number"
        value={value}
        onChange={(e) => {
          const v = e.target.value === "" ? min : +e.target.value;
          onChange(Math.max(min, Math.min(max, v)));
        }}
        style={{
          flex: 1, minWidth: 0, textAlign: "center",
          border: 0, outline: "none",
          background: "transparent", color: "var(--fg-primary)",
          fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700,
          padding: "0 4px",
          MozAppearance: "textfield",
        }}
      />
      {suffix && (
        <div style={{
          display: "flex", alignItems: "center",
          padding: "0 8px",
          fontSize: 10, color: "var(--fg-tertiary)",
          fontFamily: "inherit", whiteSpace: "nowrap",
          fontWeight: 600,
          borderLeft: "1px solid var(--border-subtle)",
        }}>{suffix}</div>
      )}
      <button type="button" onClick={inc} style={pySpinBtn} aria-label="+">+</button>
    </div>
  );
};
const pySpinBtn = {
  width: 28,
  border: 0, background: "transparent",
  color: "var(--fg-secondary)",
  fontSize: 14, cursor: "pointer", padding: 0,
  fontFamily: "inherit", fontWeight: 700,
  transition: "background .15s, color .15s",
};

// QComboBox に相当
const PyCombo = ({ value, onChange, options, width = 180 }) => (
  <select value={value} onChange={(e) => onChange(e.target.value)} style={{
    height: 34, padding: "0 32px 0 12px", width,
    border: "1px solid var(--border)",
    borderRadius: 8,
    background: "var(--bg-surface-2)", color: "var(--fg-primary)",
    fontFamily: "inherit", fontSize: 12, fontWeight: 600,
    cursor: "pointer", outline: "none",
    appearance: "none",
    backgroundImage: "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path d='M1 1l4 4 4-4' fill='none' stroke='%238E8E93' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/></svg>\")",
    backgroundRepeat: "no-repeat",
    backgroundPosition: "right 12px center",
  }}>
    {options.map((o) => (
      <option key={o.value} value={o.value}>{o.label}</option>
    ))}
  </select>
);

// トグルスイッチ + label
const PyCheck = ({ checked, onChange, label }) => (
  <label style={{
    display: "inline-flex", alignItems: "center", gap: 12,
    cursor: "pointer", fontSize: 12, color: "var(--fg-primary)",
    userSelect: "none", padding: "4px 0",
  }}>
    <span style={{
      position: "relative",
      width: 38, height: 22, borderRadius: 999,
      background: checked ? "#34C759" : "var(--border)",
      transition: "background 0.18s",
      flexShrink: 0,
      boxShadow: "inset 0 1px 2px rgba(0,0,0,.08)",
    }}>
      <span style={{
        position: "absolute",
        left: checked ? 18 : 2, top: 2,
        width: 18, height: 18, borderRadius: 999,
        background: "#fff",
        boxShadow: "0 2px 4px rgba(0,0,0,.18)",
        transition: "left 0.18s",
      }}/>
    </span>
    <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)}
      style={{ position: "absolute", opacity: 0, width: 0, height: 0, pointerEvents: "none" }} />
    <span style={{ fontWeight: 600 }}>{label}</span>
  </label>
);

// ボタン (primary / secondary / danger)
const PyBtn = ({ children, onClick, primary, danger, disabled, style, type = "button" }) => {
  const bg = disabled ? "var(--bg-surface-2)"
    : primary ? "var(--accent)"
    : danger ? "color-mix(in srgb, #FF453A 12%, transparent)"
    : "var(--bg-surface-2)";
  const fg = disabled ? "var(--fg-tertiary)"
    : primary ? "#fff"
    : danger ? "#FF453A"
    : "var(--fg-primary)";
  const border = disabled ? "var(--border-subtle)"
    : primary ? "transparent"
    : danger ? "color-mix(in srgb, #FF453A 22%, transparent)"
    : "var(--border)";
  return (
    <button type={type} onClick={onClick} disabled={disabled} style={{
      height: 34, padding: "0 16px",
      borderRadius: 8,
      border: `1px solid ${border}`,
      background: bg, color: fg,
      fontFamily: "inherit", fontSize: 12, fontWeight: 700,
      cursor: disabled ? "not-allowed" : "pointer",
      transition: "all 0.15s",
      whiteSpace: "nowrap",
      boxShadow: primary ? "0 1px 0 rgba(0,0,0,.06), 0 4px 10px color-mix(in srgb, var(--accent) 25%, transparent)" : "0 1px 0 rgba(0,0,0,.04)",
      ...(style || {}),
    }}>{children}</button>
  );
};

const PyInput = ({ value, onChange, placeholder, disabled, width, type = "text", maxLength }) => (
  <input
    type={type}
    value={value}
    onChange={(e) => onChange(e.target.value)}
    placeholder={placeholder}
    disabled={disabled}
    maxLength={maxLength}
    style={{
      height: 34, padding: "0 12px",
      border: "1px solid var(--border)",
      borderRadius: 8,
      background: disabled ? "var(--bg-surface)" : "var(--bg-surface-2)",
      color: disabled ? "var(--fg-tertiary)" : "var(--fg-primary)",
      fontFamily: "inherit", fontSize: 12, fontWeight: 600,
      outline: "none",
      width: width || "100%",
      boxSizing: "border-box",
      transition: "border-color .15s",
    }}
    onFocus={(e) => !disabled && (e.currentTarget.style.borderColor = "var(--accent)")}
    onBlur={(e) => !disabled && (e.currentTarget.style.borderColor = "var(--border)")}
  />
);

const PyNote = ({ children }) => (
  <div style={{
    fontSize: 11, color: "var(--fg-tertiary)",
    lineHeight: 1.5, padding: "8px 12px",
    background: "color-mix(in srgb, var(--accent) 4%, transparent)",
    borderRadius: 8,
    borderLeft: "3px solid color-mix(in srgb, var(--accent) 30%, transparent)",
    marginTop: 8,
  }}>{children}</div>
);

// セパレータ
const PySep = () => (
  <div style={{ height: 1, background: "var(--border-subtle)", margin: "10px 0" }} />
);

// Toast — モダンなチップ
const PyToast = ({ msg, onDone }) => {
  m2E(() => {
    if (!msg) return;
    const t = setTimeout(onDone, 3000);
    return () => clearTimeout(t);
  }, [msg]);
  if (!msg) return null;
  const isError = msg.includes("⚠") || msg.includes("❌");
  const isInfo = msg.includes("変更がありません");
  const color = isError ? "#FF453A" : isInfo ? "#8E8E93" : "#34C759";
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 8,
      padding: "5px 12px", borderRadius: 999,
      background: `color-mix(in srgb, ${color} 14%, transparent)`,
      color, fontSize: 12, fontWeight: 700,
      animation: "fadeIn 0.3s",
      letterSpacing: 0.2,
    }}>{msg}</span>
  );
};

// 左サイドナビ (sticky)
const SettingsNav = ({ isAdmin, dirty }) => {
  const items = [
    { id: "alert",   tone: "alert",   label: "アラート" },
    { id: "refresh", tone: "refresh", label: "自動更新" },
    { id: "google",  tone: "google",  label: "Google 連携" },
    { id: "ai",      tone: "ai",      label: "AI チャット" },
    { id: "data",    tone: "data",    label: "データ管理" },
    { id: "app",     tone: "app",     label: "アプリ" },
  ];
  if (isAdmin) items.push({ id: "users", tone: "users", label: "ユーザー管理" });

  const goTo = (id) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <nav style={{
      position: "sticky", top: 28,
      background: "var(--bg-surface)",
      border: "1px solid var(--border-subtle)",
      borderRadius: 14,
      padding: 10,
      boxShadow: "var(--shadow-sm)",
      display: "flex", flexDirection: "column", gap: 2,
    }}>
      {items.map(it => {
        const tone = SECTION_TONES[it.tone] || SECTION_TONES.app;
        return (
          <button key={it.id} onClick={() => goTo(it.id)} style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "9px 11px", borderRadius: 9,
            border: 0, background: "transparent",
            cursor: "pointer", fontFamily: "inherit",
            fontSize: 12, fontWeight: 700, color: "var(--fg-primary)",
            textAlign: "left",
            transition: "background .12s",
          }}
          onMouseEnter={(e) => e.currentTarget.style.background = "var(--bg-surface-2)"}
          onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
          >
            <span style={{
              width: 22, height: 22, borderRadius: 6,
              background: tone.bg, color: tone.color,
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              flexShrink: 0,
            }}>
              <SectionIcon tone={it.tone}/>
            </span>
            <span style={{ flex: 1 }}>{it.label}</span>
          </button>
        );
      })}
      <div style={{ height: 1, background: "var(--border-subtle)", margin: "8px 4px" }}/>
      <div style={{
        padding: "8px 11px",
        fontSize: 10, color: "var(--fg-tertiary)",
        display: "flex", alignItems: "center", gap: 8,
      }}>
        <span style={{
          width: 7, height: 7, borderRadius: 999,
          background: dirty ? "#FF9F0A" : "#34C759",
          boxShadow: dirty ? "0 0 0 3px color-mix(in srgb, #FF9F0A 24%, transparent)" : "0 0 0 3px color-mix(in srgb, #34C759 18%, transparent)",
        }}/>
        <span style={{ fontWeight: 700 }}>{dirty ? "未保存" : "保存済"}</span>
      </div>
    </nav>
  );
};

// ============================================================
// Settings Detail (settings.py 完全反映)
// ============================================================
const _LANG_OPTIONS = [
  { value: "auto", label: "自動 (System)" },
  { value: "ja",   label: "日本語" },
  { value: "ko",   label: "한국어" },
  { value: "en",   label: "English" },
  { value: "zh",   label: "中文" },
];

const _GEMINI_MODELS = [
  { value: "gemini-2.5-flash",      label: "gemini-2.5-flash  (推奨)" },
  { value: "gemini-2.5-pro",        label: "gemini-2.5-pro  (高精度・低速)" },
  { value: "gemini-2.0-flash",      label: "gemini-2.0-flash" },
  { value: "gemini-2.0-flash-lite", label: "gemini-2.0-flash-lite  (軽量)" },
];

const _MAX_TOKENS = [512, 1024, 2048, 4096].map((v) => ({
  value: v, label: `${v.toLocaleString()}  トークン`,
}));

// 管理者用ダミーデータ
const _ADMIN_USERS = [
  { email: "lee.tanaka@enex.co.jp",   name: "李 田中",       added: "2024-04-01" },
  { email: "k.suzuki@enex.co.jp",     name: "鈴木 健太",     added: "2024-04-12" },
  { email: "h.yamada@enex.co.jp",     name: "山田 春樹",     added: "2024-06-15" },
  { email: "n.kim@enex.co.jp",        name: "金 ナム",       added: "2024-09-01" },
  { email: "jw.lee@shirokumapower.com", name: "Jaewon Lee",  added: "2023-11-08" },
];

const _DEFAULTS = {
  imbalance_alert: 40.0,
  reserve_low: 8.0,
  reserve_warn: 10.0,
  imbalance_interval: 5,
  reserve_interval: 5,
  weather_interval: 60,
  hjks_interval: 180,
  jkm_interval: 180,
  retention_days: 1460,
  auto_start: false,
  language: "auto",
  gemini_model: "gemini-2.5-flash",
  ai_temperature: 0.7,
  ai_max_tokens: 2048,
  chat_history_limit: 20,
  calendar_poll_interval: 5,
  gmail_poll_interval: 5,
  gmail_max_results: 50,
};

const SettingsDetail = ({ onBack, isAdmin = true }) => {
  const [s, setS] = m2S({ ..._DEFAULTS });
  const [saved, setSaved] = m2S({ ..._DEFAULTS });
  const [toast, setToast] = m2S("");
  const [usersStatus, setUsersStatus] = m2S(`${_ADMIN_USERS.length} 件`);
  const [users, setUsers] = m2S(_ADMIN_USERS);
  const [selectedUserIdx, setSelectedUserIdx] = m2S(0);
  const [newEmail, setNewEmail] = m2S("");
  const [newName, setNewName] = m2S("");

  const set = (k, v) => setS((p) => ({ ...p, [k]: v }));
  const isDirty = m2M(() => Object.keys(_DEFAULTS).some((k) => s[k] !== saved[k]), [s, saved]);

  const onSave = () => {
    if (!isDirty) {
      setToast("変更がありません");
      return;
    }
    const langChanged = s.language !== saved.language;
    setSaved({ ...s });
    setToast(langChanged ? "変更は再起動後に適用されます" : "✅  保存しました");
  };

  const onReset = () => {
    if (!confirm("設定を初期値に戻しますか？")) return;
    setS({ ..._DEFAULTS });
  };

  const onManualRetention = () => {
    if (!confirm(`保持期間 (${s.retention_days} 日) より古いデータを\nバックアップして削除しますか？`)) return;
    setToast("✅  整理処理が完了しました (デモ)");
  };

  const onAddUser = () => {
    if (!newEmail.trim()) return;
    setUsersStatus("追加中...");
    setTimeout(() => {
      const today = new Date().toISOString().slice(0, 10);
      setUsers((u) => [...u, { email: newEmail, name: newName || "—", added: today }]);
      setNewEmail("");
      setNewName("");
      setUsersStatus(`${users.length + 1} 件`);
      setToast("✅  ユーザーを追加しました");
    }, 500);
  };

  const onRemoveUser = () => {
    if (selectedUserIdx == null || !users[selectedUserIdx]) return;
    const target = users[selectedUserIdx];
    if (!confirm(`${target.email} を削除しますか？`)) return;
    setUsers((u) => u.filter((_, i) => i !== selectedUserIdx));
    setSelectedUserIdx(0);
    setToast("✅  ユーザーを削除しました");
  };

  return (
    <div style={{ padding: "28px 28px 0", maxWidth: 1280, fontFamily: "inherit" }}>
      <M2_DH title="設定" subtitle={`v${M2_D.version || "3.4.2"} · 全 ${Object.keys(_DEFAULTS).length} 項目`} accent="#8E8E93" icon="setting" onBack={onBack} />

      <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 24, alignItems: "start" }}>
        {/* === 左サイドナビ === */}
        <SettingsNav isAdmin={isAdmin} dirty={isDirty} />

        {/* === メイン === */}
        <div style={{ minWidth: 0 }}>
          {/* ⚠️ アラートしきい値 */}
          <PyGroup title="アラートしきい値" tone="alert" anchor="alert">
            <PyFormRow label="インバランス単価 警告" hint="この値を超過した場合、警告を通知します。" dirty={s.imbalance_alert !== saved.imbalance_alert}>
              <PySpin value={s.imbalance_alert} onChange={(v) => set("imbalance_alert", v)} min={0} max={1000} step={1} suffix="円" />
            </PyFormRow>
            <PyFormRow label="電力予備率 警告 (赤)" hint="この値を下回った場合、赤色の警告を通知します。" dirty={s.reserve_low !== saved.reserve_low}>
              <PySpin value={s.reserve_low} onChange={(v) => set("reserve_low", v)} min={0} max={100} step={0.5} suffix="%" />
            </PyFormRow>
            <PyFormRow label="電力予備率 注意 (黄)" hint="この値を下回った場合、黄色の注意を通知します。" dirty={s.reserve_warn !== saved.reserve_warn}>
              <PySpin value={s.reserve_warn} onChange={(v) => set("reserve_warn", v)} min={0} max={100} step={0.5} suffix="%" />
            </PyFormRow>
          </PyGroup>

          {/* ⏱️ 自動更新間隔 */}
          <PyGroup title="自動更新間隔" tone="refresh" anchor="refresh">
            {[
              ["imbalance_interval", "インバランス単価",   "分"],
              ["reserve_interval",   "電力予備率",         "分"],
              ["weather_interval",   "全国天気予報",       "分"],
              ["hjks_interval",      "発電停止状況 (HJKS)", "分"],
              ["jkm_interval",       "JKM LNG 価格",       "分"],
            ].map(([k, l, u]) => (
              <PyFormRow key={k} label={l} dirty={s[k] !== saved[k]}>
                <PySpin value={s[k]} onChange={(v) => set(k, v)} min={1} max={1440} suffix={u} />
              </PyFormRow>
            ))}
          </PyGroup>

          {/* 🔗 Google 連携 */}
          <PyGroup title="Google 連携" tone="google" anchor="google">
            <PyFormRow label="アカウント">
              <span style={{
                display: "inline-flex", alignItems: "center", gap: 8,
                background: "color-mix(in srgb, #34C759 12%, transparent)",
                color: "#34C759", padding: "6px 12px",
                borderRadius: 999, fontSize: 12, fontWeight: 700,
              }}>
                <span style={{ width: 6, height: 6, borderRadius: 999, background: "#34C759" }}/>
                {M2_D.user.email}
              </span>
            </PyFormRow>
            <PyFormRow label="カレンダー更新" dirty={s.calendar_poll_interval !== saved.calendar_poll_interval}>
              <PySpin value={s.calendar_poll_interval} onChange={(v) => set("calendar_poll_interval", v)} min={1} max={1440} suffix="分" />
            </PyFormRow>
            <PyFormRow label="Gmail 更新" dirty={s.gmail_poll_interval !== saved.gmail_poll_interval}>
              <PySpin value={s.gmail_poll_interval} onChange={(v) => set("gmail_poll_interval", v)} min={1} max={1440} suffix="分" />
            </PyFormRow>
            <PyFormRow label="メール取得件数" dirty={s.gmail_max_results !== saved.gmail_max_results}>
              <PySpin value={s.gmail_max_results} onChange={(v) => set("gmail_max_results", v)} min={10} max={500} suffix="件" />
            </PyFormRow>
          </PyGroup>

          {/* 🤖 AI チャット */}
          <PyGroup title="AI チャット" tone="ai" anchor="ai">
            <PyFormRow label="フォールバックモデル" dirty={s.gemini_model !== saved.gemini_model}>
              <PyCombo value={s.gemini_model} onChange={(v) => set("gemini_model", v)} options={_GEMINI_MODELS} width={280} />
            </PyFormRow>
            <PyFormRow label="応答の温度" hint="低い値: 正確・一貫 / 高い値: 多様・創造的 / 推奨 0.7" dirty={s.ai_temperature !== saved.ai_temperature}>
              <PySpin value={s.ai_temperature} onChange={(v) => set("ai_temperature", v)} min={0.1} max={2.0} step={0.1} width={130} />
            </PyFormRow>
            <PyFormRow label="最大トークン数" dirty={s.ai_max_tokens !== saved.ai_max_tokens}>
              <PyCombo value={s.ai_max_tokens} onChange={(v) => set("ai_max_tokens", +v)} options={_MAX_TOKENS} width={200} />
            </PyFormRow>
            <PyFormRow label="会話履歴の保持数" hint="多いほどコンテキスト保持 / API 使用量が増加 / 推奨 20" dirty={s.chat_history_limit !== saved.chat_history_limit}>
              <PySpin value={s.chat_history_limit} onChange={(v) => set("chat_history_limit", v)} min={4} max={100} step={2} suffix="件" />
            </PyFormRow>
            <PyNote>優先順位: Gemini 2.5 Flash Lite → 上記モデル → Groq (llama-3.3-70b)</PyNote>
          </PyGroup>

          {/* 💾 データ管理 */}
          <PyGroup title="データ管理" tone="data" anchor="data">
            <PyFormRow label="データ保持期間" hint="この日数を超えた古いデータは backups フォルダへ自動退避されます。" dirty={s.retention_days !== saved.retention_days}>
              <PySpin value={s.retention_days} onChange={(v) => set("retention_days", v)} min={30} max={3650} suffix="日" />
            </PyFormRow>
            <PyFormRow label="手動整理">
              <PyBtn onClick={onManualRetention}>今すぐ整理実行</PyBtn>
            </PyFormRow>
          </PyGroup>

          {/* ⚙️ アプリ設定 */}
          <PyGroup title="アプリ設定" tone="app" anchor="app">
            <PyFormRow label="表示言語" hint="言語変更は再起動後に適用されます。" dirty={s.language !== saved.language}>
              <PyCombo value={s.language} onChange={(v) => set("language", v)} options={_LANG_OPTIONS} width={200} />
            </PyFormRow>
            <PyFormRow label="自動起動" dirty={s.auto_start !== saved.auto_start}>
              <PyCheck checked={s.auto_start} onChange={(v) => set("auto_start", v)} label="Windows 起動時にバックグラウンドで自動実行する" />
            </PyFormRow>
          </PyGroup>

          {/* 👑 ユーザー管理 (管理者専用) */}
          {isAdmin && (
            <PyGroup title="ユーザー管理 (管理者専用)" tone="users" anchor="users">
              <div style={{ fontSize: 12, fontWeight: 800, marginBottom: 8, color: "var(--fg-secondary)" }}>Google Sheets ID</div>
              <PyInput value="1A2bCdEfGh...ZxYwVuTsRqPo (.env で管理)" onChange={() => {}} disabled />
              <PyNote>Sheets ID は環境変数 (.env) で一元管理されているため、ここでは読み取り専用です。</PyNote>
              <PySep />

              <div style={{ display: "flex", alignItems: "center", marginBottom: 10 }}>
                <span style={{ fontSize: 12, fontWeight: 800, color: "var(--fg-secondary)" }}>登録ユーザー</span>
                <span style={{ flex: 1 }} />
                <span style={{
                  fontSize: 11, color: "var(--fg-secondary)", fontWeight: 700,
                  background: "var(--bg-surface-2)", padding: "3px 10px", borderRadius: 999,
                }}>{usersStatus}</span>
              </div>

              {/* user table */}
              <div style={{
                border: "1px solid var(--border-subtle)",
                borderRadius: 10,
                overflow: "hidden",
                maxHeight: 240,
                overflowY: "auto",
                background: "var(--bg-surface-2)",
              }}>
                <div style={{
                  display: "grid", gridTemplateColumns: "1fr 140px 110px",
                  padding: "10px 14px", gap: 10,
                  background: "var(--bg-surface-3)",
                  borderBottom: "1px solid var(--border-subtle)",
                  fontSize: 10, fontWeight: 800, color: "var(--fg-tertiary)",
                  letterSpacing: "0.08em", textTransform: "uppercase",
                  position: "sticky", top: 0, zIndex: 1,
                }}>
                  <span>メールアドレス</span>
                  <span>名前</span>
                  <span>登録日</span>
                </div>
                {users.map((u, i) => {
                  const sel = selectedUserIdx === i;
                  return (
                    <div key={u.email} onClick={() => setSelectedUserIdx(i)} style={{
                      display: "grid", gridTemplateColumns: "1fr 140px 110px",
                      padding: "10px 14px", gap: 10, cursor: "pointer",
                      background: sel ? "color-mix(in srgb, var(--accent) 12%, transparent)" : "transparent",
                      borderLeft: sel ? "3px solid var(--accent)" : "3px solid transparent",
                      borderBottom: i < users.length - 1 ? "1px solid var(--border-subtle)" : "none",
                      fontSize: 11, color: "var(--fg-primary)",
                      fontFamily: "var(--font-mono)",
                      transition: "background .12s",
                    }}>
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: sel ? 700 : 500 }}>{u.email}</span>
                      <span style={{ fontFamily: "inherit", fontWeight: 600 }}>{u.name}</span>
                      <span style={{ color: "var(--fg-tertiary)" }}>{u.added}</span>
                    </div>
                  );
                })}
              </div>

              <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                <PyBtn onClick={() => { setUsersStatus("取得中..."); setTimeout(() => setUsersStatus(`${users.length} 件`), 600); }}>一覧を更新</PyBtn>
                <PyBtn danger onClick={onRemoveUser}>選択ユーザーを削除</PyBtn>
              </div>
              <PySep />

              <div style={{ fontSize: 12, fontWeight: 800, marginBottom: 10, color: "var(--fg-secondary)" }}>ユーザーを追加</div>
              <div style={{ display: "flex", gap: 8 }}>
                <div style={{ flex: 1 }}>
                  <PyInput value={newEmail} onChange={setNewEmail} placeholder="メールアドレス" />
                </div>
                <div style={{ width: 180 }}>
                  <PyInput value={newName} onChange={setNewName} placeholder="名前 (任意)" />
                </div>
                <PyBtn primary onClick={onAddUser}>＋ 追加</PyBtn>
              </div>
            </PyGroup>
          )}

          {/* 末尾 余白 (footer 重ならないよう) */}
          <div style={{ height: 80 }} />
        </div>
      </div>

      {/* Footer (固定 - 全幅, ガラス風) */}
      <div style={{
        position: "sticky", bottom: 0,
        marginLeft: -28, marginRight: -28, marginTop: 12,
        padding: "14px 28px",
        background: "color-mix(in srgb, var(--bg-base, #fff) 88%, transparent)",
        borderTop: "1px solid var(--border-subtle)",
        display: "flex", alignItems: "center", gap: 12,
        backdropFilter: "blur(14px)",
        WebkitBackdropFilter: "blur(14px)",
        zIndex: 5,
      }}>
        <div style={{ flex: 1, minHeight: 18 }}>
          <PyToast msg={toast} onDone={() => setToast("")} />
          {!toast && isDirty && (
            <span style={{ fontSize: 12, color: "var(--fg-secondary)", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 8, height: 8, borderRadius: 999, background: "#FF9F0A", boxShadow: "0 0 0 4px color-mix(in srgb, #FF9F0A 24%, transparent)" }}/>
              未保存の変更があります
            </span>
          )}
          {!toast && !isDirty && (
            <span style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>すべて保存済み</span>
          )}
        </div>
        <PyBtn onClick={onReset} disabled={!isDirty}>初期化</PyBtn>
        <PyBtn primary onClick={onSave} disabled={!isDirty}>設定を保存</PyBtn>
      </div>
    </div>
  );
};

// ============================================================
// Briefing Detail (briefing.py 完全反映)
// ============================================================
const _PERIODS = [
  { id: "daily",      ja: "今日", ko: "오늘", en: "Today",      zh: "今天",   pja: "デイリー" },
  { id: "weekly",     ja: "今週", ko: "이번 주", en: "This Week",  zh: "本周",   pja: "週間" },
  { id: "monthly",    ja: "今月", ko: "이번 달", en: "This Month", zh: "本月",   pja: "今月" },
  { id: "next_month", ja: "来月", ko: "다음 달", en: "Next Month", zh: "下月",   pja: "来月" },
];
const _BRIEF_LANGS = [
  { value: "ja", label: "日本語" },
  { value: "ko", label: "한국어" },
  { value: "en", label: "English" },
  { value: "zh", label: "中文" },
];
const _GEN_LABEL = { ja: "ブリーフィング生成", ko: "브리핑 생성", en: "Generate Briefing", zh: "生成简报" };
const _RUN_LABEL = { ja: "生成中...", ko: "생성 중...", en: "Generating...", zh: "生成中..." };
const _W_LABEL   = {
  ja: ["過去分析", "現在状況", "将来予測"],
  ko: ["과거 분석", "현재 상황", "미래 예측"],
  en: ["Past", "Current", "Future"],
  zh: ["历史", "当前", "未来"],
};
const _PLACEHOLDER = {
  ja: "期間を選択して「ブリーフィング生成」をクリックしてください。\nAI が日本電力市場の過去・現在・将来を分析します。",
  ko: "기간을 선택하고 「브리핑 생성」을 클릭하세요.\nAI가 일본 전력 시장의 과거・현재・미래를 분석합니다.",
  en: "Select a period and click 'Generate Briefing'.\nAI will analyse past, present, and future trends in the Japanese power market.",
  zh: "选择时间段后点击「生成简报」。\nAI 将分析日本电力市场的历史、现状与未来。",
};

// briefing_api.py の calc_weights を JS で再現
const _calcWeights = (period) => {
  switch (period) {
    case "daily":      return [20, 60, 20];
    case "weekly":     return [40, 40, 20];
    case "monthly":    return [50, 30, 20];
    case "next_month": return [30, 10, 60];
    default:           return [33, 34, 33];
  }
};

// 模擬コンテンツ生成
const _genContent = (period, lang) => {
  const today = new Date().toLocaleDateString("ja-JP");
  const heads = {
    daily: {
      ja: `# デイリーブリーフィング (${today})\n\n## 📊 マーケットサマリー\n- **スポット**: 12.84 円/kWh (+1.2)\n- **予備率**: 6.2 % (-1.8) ⚠ 東京エリア OCCTO 注意発令中\n- **インバランス**: 38.5 円/kWh (+4.3)\n- **JKM LNG**: $14.32 (-1.2)\n\n## 🔍 注目ポイント\n東京エリアでは予備率が **6.2%** まで低下し、夕方 18:00-19:30 のピーク帯で最もタイトな状況が見込まれます。揚水発電・地域間融通の活用を推奨。\n\n一方、**LNG 市場は弱含み** (JKM $14.32, -1.2%) で、調達タイミングとしては有利な局面です。Q1 計画に対するスポット比率を 10-15% 引き上げる余地があります。\n\n## 🌤 気象\n九州地域で雷雨警報。明日午後にかけて鹿児島県を中心に太陽光発電量に -30% 程度の影響が見込まれます。\n\n## 📈 24 時間予測\n| 時間帯 | 想定価格 | 区分 |\n|---|---|---|\n| 18:00-22:00 | 18.5 円/kWh | ピーク |\n| 03:00-06:00 | 8.2 円/kWh  | ボトム |\n| 翌 18:00-20:00 | 16.0 円/kWh | ピーク |\n`,
      ko: `# 데일리 브리핑 (${today})\n\n## 📊 마켓 요약\n- **스팟**: 12.84 엔/kWh (+1.2)\n- **예비율**: 6.2 % (-1.8) ⚠ 도쿄지역 OCCTO 주의 발령중\n- **임밸런스**: 38.5 엔/kWh (+4.3)\n- **JKM LNG**: $14.32 (-1.2)\n\n## 🔍 포커스\n도쿄 권역 예비율이 **6.2%** 까지 하락했습니다. 저녁 18-20시 피크대 타이트 예상.\n`,
      en: `# Daily Briefing (${today})\n\n## 📊 Market Summary\n- **Spot**: ¥12.84/kWh (+1.2)\n- **Reserve**: 6.2 % (-1.8) ⚠ Tokyo OCCTO Alert\n- **Imbalance**: ¥38.5/kWh (+4.3)\n- **JKM LNG**: $14.32 (-1.2)\n\n## 🔍 Focus\nTokyo reserve margin tightening to **6.2%**. Peak 18-20:00 will be the tightest window.\n`,
      zh: `# 每日简报 (${today})\n\n## 📊 市场概览\n- **现货**: 12.84 日元/kWh (+1.2)\n- **备用率**: 6.2 % (-1.8) ⚠ 东京地区 OCCTO 提醒\n- **不平衡**: 38.5 日元/kWh (+4.3)\n- **JKM LNG**: $14.32 (-1.2)\n`,
    },
    weekly: {
      ja: `# ウィークリーブリーフィング\n\n今週は寒波の影響により、平均スポット価格が **14.2 円/kWh** と前週比 +18% で推移しました。\n\n## 主要動向\n- 月～火: 寒気流入により東京・東北の予備率が 7% を割り込み\n- 水: 太陽光が比較的安定し平均価格は緩和\n- 木～金: 翌週への先物クロスで上昇\n\n## 来週の見通し\n寒波は徐々に和らぐ予想ですが、暖房需要は依然として平年比 +12% で推移する見込み。`,
      ko: `# 주간 브리핑\n\n이번 주는 한파의 영향으로 평균 스팟 가격이 **14.2엔/kWh** 로 전주 대비 +18% 추이.\n`,
      en: `# Weekly Briefing\n\nCold spell pushed average spot prices to **¥14.2/kWh**, +18% W/W.`,
      zh: `# 每周简报\n\n寒潮影响下，平均现货价格 **14.2 日元/kWh**, 环比 +18%。`,
    },
    monthly: {
      ja: `# マンスリーブリーフィング\n\n今月は暖冬気味で需要は前年同月比 -4% に推移したものの、**LNG スポット価格の高止まり** によりスポット価格は前年同月比 +6% で着地見通し。\n\n## ハイライト\n- 月平均スポット: **13.1 円/kWh** (前月比 -2.4%)\n- インバランス発生件数: 28 回 (前月 35 回)\n- JKM 月平均: $14.55 (前月 $13.92)\n\n## 来月への引継ぎ\n2 月は寒波襲来予想あり。需給ひっ迫イベントへの備えを推奨。`,
      ko: `# 월간 브리핑\n\n이달은 따뜻한 겨울 영향으로 수요가 전년 대비 -4%, 그러나 **LNG 스팟 가격 고공행진** 으로 스팟 가격은 +6% 마감 전망.\n`,
      en: `# Monthly Briefing\n\nMild winter softened demand by 4% Y/Y, but **firm LNG prices** lifted spot +6% Y/Y.`,
      zh: `# 本月简报\n\n暖冬使需求同比 -4%, 但 **LNG 现货高位** 使现货价格同比 +6%。`,
    },
    next_month: {
      ja: `# 来月ブリーフィング (予測)\n\n気象庁・OCCTO 中期予測を踏まえ、**来月の電力市場は相場の中央値が 11.5-13.0 円/kWh のレンジ** を見込みます。\n\n## 主要シナリオ\n- **基本**: 平年並み気温 + LNG 弱含み → 平均 12.0 円/kWh\n- **上振れ**: 寒波襲来 + LNG 反発 → 平均 14.5 円/kWh\n- **下振れ**: 暖冬 + 太陽光好天 → 平均 10.0 円/kWh\n\n## 推奨アクション\n- 2/上旬: スポット買い比率 +5%\n- 2/中旬: 寒波シナリオに備え調整力電源の確保\n`,
      ko: `# 다음달 브리핑 (예측)\n\n기상청·OCCTO 중기 전망 기반, **다음달 전력시장 중앙값은 11.5-13.0 엔/kWh 레인지** 예상.\n`,
      en: `# Next-Month Briefing (Forecast)\n\nMidterm forecasts suggest **¥11.5-13.0/kWh range** for next month's median price.`,
      zh: `# 下月简报 (预测)\n\n基于气象厅/OCCTO 中期预报，**下月电价中位数 11.5-13.0 日元/kWh 区间** 预测。`,
    },
  };
  return heads[period][lang] || heads[period].ja;
};

// 簡易マークダウン
const _renderMarkdown = (md) => {
  if (!md) return null;
  const lines = md.split("\n");
  const out = [];
  let inTable = false;
  let tableHeader = null;
  let tableRows = [];
  let inList = false;
  let listItems = [];

  const flushList = () => {
    if (inList && listItems.length) {
      out.push(<ul key={`ul-${out.length}`} style={{ paddingLeft: 22, margin: "8px 0" }}>{listItems.map((it, j) => (
        <li key={j} style={{ marginBottom: 4, lineHeight: 1.7 }} dangerouslySetInnerHTML={{ __html: _inline(it) }} />
      ))}</ul>);
      listItems = [];
    }
    inList = false;
  };
  const flushTable = () => {
    if (inTable && tableHeader) {
      out.push(
        <div key={`tb-${out.length}`} style={{ overflow: "auto", margin: "10px 0" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead><tr style={{ background: "var(--bg-surface-2)" }}>
              {tableHeader.map((h, i) => (
                <th key={i} style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)", textAlign: "left", fontWeight: 800 }}>{h}</th>
              ))}
            </tr></thead>
            <tbody>{tableRows.map((r, ri) => (
              <tr key={ri} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                {r.map((c, ci) => <td key={ci} style={{ padding: "7px 12px", fontFamily: ci > 0 ? "var(--font-mono)" : "inherit" }} dangerouslySetInnerHTML={{ __html: _inline(c) }} />)}
              </tr>
            ))}</tbody>
          </table>
        </div>
      );
      tableHeader = null; tableRows = [];
    }
    inTable = false;
  };

  lines.forEach((ln, i) => {
    if (ln.startsWith("# ")) {
      flushList(); flushTable();
      out.push(<h1 key={i} style={{ fontSize: 22, fontWeight: 800, margin: "0 0 14px", letterSpacing: "-0.02em" }}>{ln.slice(2)}</h1>);
    } else if (ln.startsWith("## ")) {
      flushList(); flushTable();
      out.push(<h2 key={i} style={{ fontSize: 16, fontWeight: 800, margin: "16px 0 8px", color: "var(--fg-primary)" }}>{ln.slice(3)}</h2>);
    } else if (ln.startsWith("- ")) {
      flushTable();
      inList = true;
      listItems.push(ln.slice(2));
    } else if (ln.startsWith("|") && ln.includes("|")) {
      flushList();
      const cells = ln.split("|").slice(1, -1).map((c) => c.trim());
      if (!inTable) { inTable = true; tableHeader = cells; }
      else if (cells.every((c) => /^[-:]+$/.test(c))) { /* separator */ }
      else { tableRows.push(cells); }
    } else if (ln.trim() === "") {
      flushList(); flushTable();
    } else {
      flushList(); flushTable();
      out.push(<p key={i} style={{ margin: "6px 0", lineHeight: 1.75 }} dangerouslySetInnerHTML={{ __html: _inline(ln) }} />);
    }
  });
  flushList(); flushTable();
  return out;
};
const _inline = (s) => s
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
  .replace(/`([^`]+)`/g, "<code style=\"background:var(--bg-surface-2);padding:1px 6px;border-radius:4px;font-size:0.92em;font-family:var(--font-mono);\">$1</code>");

// 履歴サンプル
const _seedHistory = () => {
  const now = new Date();
  const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")} ${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`;
  const off = (m) => new Date(now.getTime() - m * 60000);
  return [
    { id: 9, period: "daily",      lang: "ja", created_at: fmt(off(0)),       content: _genContent("daily","ja") },
    { id: 8, period: "daily",      lang: "ko", created_at: fmt(off(60*22)),   content: _genContent("daily","ko") },
    { id: 7, period: "weekly",     lang: "ja", created_at: fmt(off(60*30)),   content: _genContent("weekly","ja") },
    { id: 6, period: "monthly",    lang: "ja", created_at: fmt(off(60*72)),   content: _genContent("monthly","ja") },
    { id: 5, period: "next_month", lang: "ja", created_at: fmt(off(60*120)),  content: _genContent("next_month","ja") },
    { id: 4, period: "daily",      lang: "en", created_at: fmt(off(60*168)),  content: _genContent("daily","en") },
    { id: 3, period: "daily",      lang: "ja", created_at: fmt(off(60*192)),  content: _genContent("daily","ja") },
    { id: 2, period: "weekly",     lang: "ko", created_at: fmt(off(60*240)),  content: _genContent("weekly","ko") },
    { id: 1, period: "monthly",    lang: "zh", created_at: fmt(off(60*720)),  content: _genContent("monthly","zh") },
  ];
};

const BriefDetail = ({ onBack }) => {
  const [period, setPeriod] = m2S("daily");
  const [lang, setLang]     = m2S("ja");
  const [history, setHistory] = m2S(_seedHistory());
  const [selectedId, setSelectedId] = m2S(history[0]?.id ?? null);
  const [search, setSearch] = m2S("");
  const [filterP, setFilterP] = m2S("");
  const [filterL, setFilterL] = m2S("");
  const [generating, setGenerating] = m2S(false);
  const [genStatus, setGenStatus] = m2S("");
  const [streamText, setStreamText] = m2S(null);
  const genTimerRef = m2R(null);

  const [pPast, pCur, pFut] = _calcWeights(period);
  const wlbl = _W_LABEL[lang];

  const filtered = m2M(() => history.filter((h) =>
    (!filterP || h.period === filterP) &&
    (!filterL || h.lang === filterL) &&
    (!search.trim() || h.content.toLowerCase().includes(search.toLowerCase()))
  ), [history, filterP, filterL, search]);

  const selected = streamText != null
    ? { id: -1, period, lang, created_at: "—", content: streamText }
    : history.find((h) => h.id === selectedId);

  const onGenerate = () => {
    if (generating) return;
    setGenerating(true);
    setStreamText("");
    setGenStatus("⏳ 過去データ集計中...");
    let progress = 0;
    const target = _genContent(period, lang);
    const stages = [
      { msg: "⏳ 過去データ集計中...",        delay: 800 },
      { msg: "⏳ 現在指標を分析中...",        delay: 800 },
      { msg: "⏳ 将来予測モデルを実行中...",  delay: 800 },
      { msg: "✦ Gemini 2.5 Flash で生成中...", delay: 600 },
    ];
    let stage = 0;
    const advance = () => {
      if (stage >= stages.length) {
        // ストリーム
        let i = 0;
        const stream = () => {
          if (i >= target.length) {
            const created_at = new Date().toLocaleString("ja-JP", {
              year: "numeric", month: "2-digit", day: "2-digit",
              hour: "2-digit", minute: "2-digit", second: "2-digit",
            }).replace(/\//g, "-");
            const newRow = {
              id: Math.max(...history.map((h) => h.id)) + 1,
              period, lang, created_at, content: target,
            };
            setHistory((h) => [newRow, ...h]);
            setSelectedId(newRow.id);
            setGenerating(false);
            setStreamText(null);
            setGenStatus(`✅ 生成完了 ${created_at.slice(0, 16)}`);
            return;
          }
          const chunk = Math.min(15 + Math.floor(Math.random() * 30), target.length - i);
          i += chunk;
          setStreamText(target.slice(0, i));
          genTimerRef.current = setTimeout(stream, 30);
        };
        stream();
        return;
      }
      setGenStatus(stages[stage].msg);
      genTimerRef.current = setTimeout(() => { stage++; advance(); }, stages[stage].delay);
    };
    advance();
  };

  m2E(() => () => clearTimeout(genTimerRef.current), []);

  const onDelete = () => {
    if (selectedId == null) return;
    if (!confirm("このブリーフィングを削除しますか?")) return;
    const next = history.filter((h) => h.id !== selectedId);
    setHistory(next);
    setSelectedId(next[0]?.id ?? null);
  };

  const periodMap = Object.fromEntries(_PERIODS.map((p) => [p.id, p]));
  const langMap   = Object.fromEntries(_BRIEF_LANGS.map((l) => [l.value, l.label]));

  return (
    <div style={{ padding: 28, height: "calc(100vh - 56px)", display: "flex", flexDirection: "column", overflow: "hidden", boxSizing: "border-box" }}>
      <M2_DH title="AI ブリーフィング" subtitle="過去・現在・将来を AI が分析" accent="#5856D6" icon="brief" onBack={onBack} badge="AI 生成" />

      {/* 生成コントロール (briefing.py の header フレーム) */}
      <div style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border-subtle)",
        borderRadius: 12,
        padding: "12px 14px",
        marginBottom: 12,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
          {_PERIODS.map((p) => {
            const on = period === p.id;
            return (
              <button key={p.id} onClick={() => setPeriod(p.id)} style={{
                height: 30, padding: "0 14px",
                border: `1px solid ${on ? "#5856D6" : "var(--border)"}`,
                borderRadius: 6,
                background: on ? "#5856D6" : "var(--bg-surface-2)",
                color: on ? "#fff" : "var(--fg-primary)",
                fontFamily: "inherit", fontSize: 12, fontWeight: 700,
                cursor: "pointer",
              }}>{p[lang] || p.ja}</button>
            );
          })}
          <span style={{ flex: 1 }} />
          <span style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>言語:</span>
          <PyCombo value={lang} onChange={setLang} options={_BRIEF_LANGS} width={110} />
          <PyBtn primary onClick={onGenerate} disabled={generating} style={{ background: "#5856D6", borderColor: "#5856D6", height: 30, minWidth: 130 }}>
            {generating ? _RUN_LABEL[lang] : _GEN_LABEL[lang]}
          </PyBtn>
        </div>
        <div style={{ display: "flex", marginTop: 6, fontSize: 11, color: "var(--fg-tertiary)", alignItems: "center" }}>
          <span style={{ fontFamily: "var(--font-mono)" }}>
            {wlbl[0]}: <b>{pPast}%</b>  |  {wlbl[1]}: <b>{pCur}%</b>  |  {wlbl[2]}: <b>{pFut}%</b>
          </span>
          <span style={{ flex: 1 }} />
          <span style={{ color: generating ? "#5856D6" : "var(--fg-tertiary)", fontWeight: 600 }}>{genStatus}</span>
        </div>
      </div>

      {/* 履歴 + 内容 (briefing.py の splitter) */}
      <div style={{
        flex: 1, minHeight: 0,
        display: "grid", gridTemplateColumns: "260px 1fr",
        gap: 12,
      }}>
        {/* 履歴パネル */}
        <div style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border-subtle)",
          borderRadius: 12, padding: 10,
          display: "flex", flexDirection: "column", minHeight: 0,
        }}>
          <div style={{ fontSize: 12, fontWeight: 800, marginBottom: 8 }}>履歴</div>
          <PyInput value={search} onChange={setSearch} placeholder="🔍  検索..." />
          <div style={{ display: "flex", gap: 4, marginTop: 6 }}>
            <select value={filterP} onChange={(e) => setFilterP(e.target.value)} style={miniSel}>
              <option value="">期間: 全て</option>
              {_PERIODS.map((p) => <option key={p.id} value={p.id}>{p.pja}</option>)}
            </select>
            <select value={filterL} onChange={(e) => setFilterL(e.target.value)} style={miniSel}>
              <option value="">言語: 全て</option>
              {_BRIEF_LANGS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
            </select>
          </div>
          <div style={{ flex: 1, minHeight: 0, overflowY: "auto", marginTop: 8 }}>
            {filtered.length === 0 && (
              <div style={{ padding: "30px 10px", textAlign: "center", color: "var(--fg-tertiary)", fontSize: 11 }}>
                履歴がありません
              </div>
            )}
            {filtered.map((h) => {
              const sel = !streamText && selectedId === h.id;
              return (
                <div key={h.id} onClick={() => { setSelectedId(h.id); setStreamText(null); }} style={{
                  padding: "8px 10px", borderRadius: 6, marginBottom: 2,
                  background: sel ? "#5856D6" : "transparent",
                  color: sel ? "#fff" : "var(--fg-primary)",
                  cursor: "pointer",
                  fontSize: 11, lineHeight: 1.4,
                }}>
                  <div style={{ fontFamily: "var(--font-mono)", fontWeight: sel ? 700 : 600 }}>{h.created_at}</div>
                  <div style={{ fontSize: 10, color: sel ? "rgba(255,255,255,.85)" : "var(--fg-tertiary)", marginTop: 2 }}>
                    {periodMap[h.period]?.pja || h.period} · {langMap[h.lang] || h.lang}
                  </div>
                </div>
              );
            })}
          </div>
          <div style={{ display: "flex", alignItems: "center", marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--border-subtle)", gap: 6 }}>
            <span style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>{filtered.length} 件</span>
            <span style={{ flex: 1 }} />
            <PyBtn danger onClick={onDelete} disabled={!selectedId || streamText != null} style={{ height: 28, padding: "0 10px" }}>削除</PyBtn>
          </div>
        </div>

        {/* 内容パネル */}
        <div style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border-subtle)",
          borderRadius: 12, padding: "20px 24px",
          overflowY: "auto",
          minHeight: 0,
          fontSize: 13, color: "var(--fg-primary)",
        }}>
          {selected ? (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, paddingBottom: 10, borderBottom: "1px solid var(--border-subtle)" }}>
                <span style={{
                  fontSize: 10, fontWeight: 800, padding: "3px 10px", borderRadius: 999,
                  background: "#5856D61f", color: "#5856D6",
                }}>{periodMap[selected.period]?.pja || selected.period}</span>
                <span style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>{langMap[selected.lang] || selected.lang}</span>
                <span style={{ flex: 1 }} />
                <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--fg-tertiary)" }}>{selected.created_at}</span>
              </div>
              <div className="brief-md">{_renderMarkdown(selected.content)}</div>
              {streamText != null && (
                <span style={{ display: "inline-block", width: 8, height: 14, background: "#5856D6", marginLeft: 2, animation: "blink 1s steps(2) infinite" }} />
              )}
            </>
          ) : (
            <div style={{
              padding: 60, textAlign: "center",
              color: "var(--fg-tertiary)",
              whiteSpace: "pre-wrap",
              fontSize: 13,
            }}>{_PLACEHOLDER[lang]}</div>
          )}
        </div>
      </div>
    </div>
  );
};
const miniSel = {
  flex: 1, height: 26, padding: "0 6px",
  border: "1px solid var(--border-subtle)",
  borderRadius: 4,
  background: "var(--bg-surface-2)", color: "var(--fg-primary)",
  fontFamily: "inherit", fontSize: 11,
  cursor: "pointer", outline: "none",
};

// ============================================================
// Bug Report (bug_report.py 完全反映)
// ============================================================
const _CATEGORIES = [
  "🐛  バグ・エラー",
  "🖥️  UI表示の問題",
  "📡  データ取得エラー",
  "⚡  パフォーマンス問題",
  "💡  機能要望",
  "❓  その他",
];
const _SUMMARY_LIMIT = 100;
const _MAX_LOG_LINES = 80;

// 模擬ログ
const _SAMPLE_LOG = [
  "[2025-01-22 14:08:24] INFO  occto: reserve fetch ok (10/10 areas)",
  "[2025-01-22 14:08:23] WARN  occto: tokyo reserve 6.2% < threshold 8.0%",
  "[2025-01-22 13:48:12] INFO  jepx: spot fetched, system_avg=12.84",
  "[2025-01-22 13:35:01] INFO  weather: open-meteo sync done (10 prefectures)",
  "[2025-01-22 13:20:55] INFO  jkm: closed at 14.32 (-1.2%)",
  "[2025-01-22 12:14:30] DEBUG auth: token refresh ok (lee.tanaka@enex.co.jp)",
  "[2025-01-22 11:30:18] INFO  eia: weekly petroleum status report imported",
  "[2025-01-22 11:00:09] ERROR plant_api: timeout on plant #324 (北海道苫東)",
  "[2025-01-22 10:42:00] INFO  plant_api: retry success #324",
  "[2025-01-22 09:42:18] WARN  weather: kyushu thunderstorm warning",
  "[2025-01-22 09:20:44] INFO  hjks: full sync ok (10/10)",
  "[2025-01-22 09:14:00] INFO  calendar: google sync ok (12 events)",
  "[2025-01-22 09:00:01] INFO  system: daily backup snapshot_20250122",
  "[2025-01-22 08:42:33] DEBUG ai: model v2.3 loaded",
  "[2025-01-22 08:30:00] INFO  system: lee v3.4.2 startup",
];

// 管理者用 — 既存の蓄積バグレポート
const _BUG_REPORTS = [
  { id: "B-1042", status: "open",     priority: "high",   category: "📡  データ取得エラー", title: "JKM チャートのツールチップが部分的に表示されない", reporter: "鈴木健太",   email: "k.suzuki@enex.co.jp",  date: "2025-01-22 10:42", area: "Chart" },
  { id: "B-1038", status: "fixed",    priority: "medium", category: "🖥️  UI表示の問題",    title: "サイドバー Gmail バッジが既読後も残る",         reporter: "田中李",     email: "lee.tanaka@enex.co.jp", date: "2025-01-21 17:08", area: "UI" },
  { id: "B-1031", status: "open",     priority: "low",    category: "🖥️  UI表示の問題",    title: "天気アイコンのアニメーションが iPhone で停止",   reporter: "山田春樹",   email: "h.yamada@enex.co.jp",  date: "2025-01-20 12:30", area: "Animation" },
  { id: "B-1029", status: "wip",      priority: "high",   category: "📡  データ取得エラー", title: "予備率 API レスポンスが時々 500 を返す",          reporter: "金ナム",     email: "n.kim@enex.co.jp",     date: "2025-01-19 19:14", area: "Backend" },
  { id: "B-1024", status: "wontfix",  priority: "low",    category: "🖥️  UI表示の問題",    title: "PWA インストール時にアイコンが暗い",              reporter: "佐藤美奈",   email: "m.sato@enex.co.jp",    date: "2025-01-18 08:55", area: "PWA" },
  { id: "B-1018", status: "fixed",    priority: "medium", category: "💡  機能要望",          title: "Gmail に未読のみフィルタを追加してほしい",         reporter: "高橋誠",    email: "m.takahashi@enex.co.jp", date: "2025-01-15 11:22", area: "Gmail" },
];
const _BUG_STATUS = {
  open:    { label: "未対応",   color: "#FF453A" },
  wip:     { label: "対応中",   color: "#FF9F0A" },
  fixed:   { label: "解決",     color: "#34C759" },
  wontfix: { label: "対応せず", color: "#8E8E93" },
};
const _BUG_PRIORITY = { high: "#FF453A", medium: "#FF9F0A", low: "#0A84FF" };

// 一般ユーザー: 送信フォームのみ (bug_report.py そのまま)
const BugSendForm = ({ onSent }) => {
  const [category, setCategory] = m2S(_CATEGORIES[0]);
  const [summary, setSummary]   = m2S("");
  const [detail, setDetail]     = m2S("");
  const [logOpen, setLogOpen]   = m2S(false);
  const [logText, setLogText]   = m2S(_SAMPLE_LOG.slice(-_MAX_LOG_LINES).join("\n"));
  const [sending, setSending]   = m2S(false);
  const [status, setStatus]     = m2S({ msg: "", error: false });

  const onSend = () => {
    const sm = summary.trim();
    if (!sm) {
      setStatus({ msg: "⚠️  概要を入力してください。", error: true });
      return;
    }
    setSending(true);
    setStatus({ msg: "", error: false });
    setTimeout(() => {
      setSending(false);
      setStatus({ msg: "✅  レポートを送信しました。ありがとうございます。", error: false });
      setSummary("");
      setDetail("");
      setCategory(_CATEGORIES[0]);
      onSent && onSent({ category, summary: sm, detail });
      setTimeout(() => setStatus({ msg: "", error: false }), 6000);
    }, 1200);
  };

  const onClear = () => {
    setSummary(""); setDetail(""); setCategory(_CATEGORIES[0]);
    setLogText(_SAMPLE_LOG.slice(-_MAX_LOG_LINES).join("\n"));
    setStatus({ msg: "", error: false });
  };

  return (
    <div style={{
      background: "var(--bg-surface)",
      border: "1px solid var(--border-subtle)",
      borderRadius: 12,
      overflow: "hidden",
      display: "flex", flexDirection: "column",
    }}>
      {/* header */}
      <div style={{
        padding: "12px 16px",
        borderBottom: "1px solid var(--border-subtle)",
        display: "flex", alignItems: "center",
      }}>
        <span style={{ fontSize: 15, fontWeight: 800 }}>バグレポート</span>
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--fg-tertiary)" }}>jw.lee@shirokumapower.com  v{M2_D.version || "3.4.2"}</span>
      </div>

      {/* form */}
      <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 14 }}>
        <div>
          <div style={fieldLbl}>分類</div>
          <PyCombo value={category} onChange={setCategory} options={_CATEGORIES.map((c) => ({ value: c, label: c }))} width="100%" />
        </div>

        <div>
          <div style={{ display: "flex", alignItems: "center" }}>
            <span style={fieldLbl}>概要</span>
            <span style={{ flex: 1 }} />
            <span style={{ fontSize: 10, color: summary.length >= _SUMMARY_LIMIT ? "#FF453A" : "var(--fg-tertiary)" }}>
              {summary.length} / {_SUMMARY_LIMIT}
            </span>
          </div>
          <PyInput value={summary} onChange={setSummary} placeholder="例: ダッシュボードが起動時にクラッシュする" maxLength={_SUMMARY_LIMIT} />
        </div>

        <div>
          <div style={fieldLbl}>詳細・再現手順  (任意)</div>
          <textarea value={detail} onChange={(e) => setDetail(e.target.value)} placeholder={"1. アプリを起動する\n2. ○○をクリックする\n3. エラーが発生する"} style={{
            width: "100%", boxSizing: "border-box",
            minHeight: 110, resize: "vertical",
            border: "1px solid var(--border)",
            borderRadius: 6, padding: "10px 12px",
            background: "var(--bg-surface-2)", color: "var(--fg-primary)",
            fontFamily: "inherit", fontSize: 12, fontWeight: 600,
            outline: "none", lineHeight: 1.6,
          }} />
        </div>

        {/* log section */}
        <div>
          <button onClick={() => setLogOpen((v) => !v)} style={{
            background: "transparent", border: 0, padding: 0,
            color: "var(--fg-tertiary)", fontSize: 12, fontWeight: 600,
            cursor: "pointer", fontFamily: "inherit",
          }}>
            {logOpen ? "▼" : "▶"}  ログ (自動取得)
          </button>
          {logOpen && (
            <div style={{ marginTop: 6 }}>
              <div style={{ display: "flex", marginBottom: 4 }}>
                <PyBtn onClick={() => setLogText(_SAMPLE_LOG.slice(-_MAX_LOG_LINES).join("\n"))} style={{ height: 24, padding: "0 8px", fontSize: 10 }}>↺  再読込</PyBtn>
                <span style={{ flex: 1 }} />
                <span style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>直近 {_MAX_LOG_LINES} 行</span>
              </div>
              <textarea value={logText} readOnly style={{
                width: "100%", boxSizing: "border-box",
                minHeight: 130, maxHeight: 200, resize: "vertical",
                border: "1px solid var(--border)",
                borderRadius: 6, padding: "8px 10px",
                background: "#161616", color: "#aaa",
                fontFamily: "var(--font-mono)", fontSize: 10,
                outline: "none", lineHeight: 1.5,
              }} />
            </div>
          )}
        </div>
      </div>

      {/* footer */}
      <div style={{
        padding: "10px 20px",
        borderTop: "1px solid var(--border-subtle)",
        display: "flex", alignItems: "center", gap: 10,
      }}>
        <div style={{ flex: 1, fontSize: 12, color: status.error ? "#FF453A" : "#34C759", fontWeight: 600 }}>{status.msg}</div>
        <PyBtn onClick={onClear} disabled={sending}>クリア</PyBtn>
        <PyBtn primary onClick={onSend} disabled={sending}>{sending ? "送信中..." : "送信  →"}</PyBtn>
      </div>
    </div>
  );
};

// 管理者: 既存のリスト + 詳細ビュー + 送信フォーム
const BugAdminView = () => {
  const [filter, setFilter]     = m2S("all");
  const [openId, setOpenId]     = m2S(_BUG_REPORTS[0].id);
  const [reports, setReports]   = m2S(_BUG_REPORTS);
  const [tab, setTab]           = m2S("list"); // list | new

  const filtered = filter === "all" ? reports : reports.filter((b) => b.status === filter);
  const cur = reports.find((b) => b.id === openId) || filtered[0];

  const setStatus = (id, st) => setReports((rs) => rs.map((r) => r.id === id ? { ...r, status: st } : r));

  const onSent = (sub) => {
    const today = new Date().toLocaleString("ja-JP", {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    }).replace(/\//g, "-");
    const nextId = `B-${1043 + reports.length - _BUG_REPORTS.length}`;
    setReports((rs) => [{
      id: nextId, status: "open", priority: "medium",
      category: sub.category, title: sub.summary,
      reporter: M2_D.user.name, email: M2_D.user.email,
      date: today, area: "Misc",
    }, ...rs]);
    setOpenId(nextId);
    setTab("list");
  };

  if (tab === "new") {
    return (
      <div>
        <div style={{ display: "flex", alignItems: "center", marginBottom: 12 }}>
          <PyBtn onClick={() => setTab("list")}>← 一覧に戻る</PyBtn>
        </div>
        <BugSendForm onSent={onSent} />
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1.4fr", gap: 14, minHeight: 500 }}>
      {/* List */}
      <div style={{
        background: "var(--bg-surface)", borderRadius: 12, padding: 8,
        border: "1px solid var(--border-subtle)",
        maxHeight: 620, overflow: "auto",
      }}>
        <div style={{
          display: "flex", gap: 4, padding: "8px 8px 6px",
          borderBottom: "1px solid var(--border-subtle)", marginBottom: 4,
          position: "sticky", top: 0, background: "var(--bg-surface)", zIndex: 1,
          flexWrap: "wrap",
        }}>
          {[["all","すべて"],["open","未対応"],["wip","対応中"],["fixed","解決"],["wontfix","対応せず"]].map(([k,l]) => {
            const on = filter === k;
            return (
              <button key={k} onClick={() => setFilter(k)} style={{
                padding: "5px 11px", borderRadius: 6, border: 0,
                background: on ? "#FF453A1f" : "transparent",
                color: on ? "#FF453A" : "var(--fg-secondary)",
                fontFamily: "inherit", fontSize: 11, fontWeight: 700, cursor: "pointer",
              }}>{l}</button>
            );
          })}
          <span style={{ flex: 1 }} />
          <PyBtn primary onClick={() => setTab("new")} style={{ background: "#FF453A", borderColor: "#FF453A", height: 26, padding: "0 10px" }}>+ 新規</PyBtn>
        </div>
        {filtered.length === 0 && (
          <div style={{ padding: 30, textAlign: "center", color: "var(--fg-tertiary)", fontSize: 11 }}>該当するレポートがありません</div>
        )}
        {filtered.map((b) => {
          const active = openId === b.id;
          const st = _BUG_STATUS[b.status];
          return (
            <div key={b.id} onClick={() => setOpenId(b.id)} style={{
              padding: "10px 12px", borderRadius: 8, cursor: "pointer",
              background: active ? "#FF453A12" : "transparent",
              borderLeft: active ? "3px solid #FF453A" : "3px solid transparent",
              marginBottom: 2,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", fontWeight: 800, color: "var(--fg-tertiary)" }}>{b.id}</span>
                <span style={{
                  fontSize: 9, fontWeight: 800, padding: "2px 7px", borderRadius: 999,
                  background: `${st.color}1f`, color: st.color, border: `1px solid ${st.color}33`,
                }}>{st.label}</span>
                <span title={b.priority} style={{ width: 6, height: 6, borderRadius: 999, background: _BUG_PRIORITY[b.priority] }} />
                <span style={{ flex: 1 }} />
                <span style={{ fontSize: 9, color: "var(--fg-tertiary)" }}>{b.area}</span>
              </div>
              <div style={{ fontSize: 12, fontWeight: 700, color: "var(--fg-primary)", lineHeight: 1.4, marginBottom: 4 }}>{b.title}</div>
              <div style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>
                {b.reporter} · {b.date}
              </div>
            </div>
          );
        })}
      </div>

      {/* Detail */}
      <div style={{
        background: "var(--bg-surface)", borderRadius: 12, padding: 22,
        border: "1px solid var(--border-subtle)",
      }}>
        {cur ? (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
              <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 800, color: "var(--fg-tertiary)" }}>{cur.id}</span>
              <span style={{
                fontSize: 10, fontWeight: 800, padding: "3px 10px", borderRadius: 999,
                background: `${_BUG_STATUS[cur.status].color}1f`, color: _BUG_STATUS[cur.status].color,
                border: `1px solid ${_BUG_STATUS[cur.status].color}33`,
              }}>{_BUG_STATUS[cur.status].label}</span>
              <span style={{
                fontSize: 10, fontWeight: 800, padding: "3px 10px", borderRadius: 999,
                background: `${_BUG_PRIORITY[cur.priority]}1f`, color: _BUG_PRIORITY[cur.priority],
                textTransform: "uppercase", letterSpacing: "0.06em",
              }}>{cur.priority}</span>
              <span style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>{cur.category}</span>
            </div>
            <div style={{ fontSize: 18, fontWeight: 800, marginBottom: 14, lineHeight: 1.4 }}>{cur.title}</div>
            <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "8px 14px", marginBottom: 18, fontSize: 11 }}>
              <span style={{ color: "var(--fg-tertiary)" }}>報告者</span>
              <span style={{ fontWeight: 700 }}>{cur.reporter}  <span style={{ color: "var(--fg-tertiary)", fontWeight: 500, fontFamily: "var(--font-mono)", fontSize: 10 }}>{cur.email}</span></span>
              <span style={{ color: "var(--fg-tertiary)" }}>報告日</span>
              <span style={{ fontFamily: "var(--font-mono)" }}>{cur.date}</span>
              <span style={{ color: "var(--fg-tertiary)" }}>領域</span>
              <span>{cur.area}</span>
              <span style={{ color: "var(--fg-tertiary)" }}>環境</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10 }}>Windows 11 / LEE v3.4.2</span>
            </div>

            <div style={{ fontSize: 11, fontWeight: 800, color: "var(--fg-tertiary)", marginBottom: 6, letterSpacing: "0.06em" }}>再現手順</div>
            <ol style={{ paddingLeft: 18, fontSize: 12, lineHeight: 1.7, color: "var(--fg-primary)", marginBottom: 14 }}>
              <li>ダッシュボードを開く</li>
              <li>JKM ウィジェットの「30 日」タブをクリック</li>
              <li>チャート上にホバーするとツールチップが描画されない</li>
            </ol>

            <div style={{ fontSize: 11, fontWeight: 800, color: "var(--fg-tertiary)", marginBottom: 6, letterSpacing: "0.06em" }}>添付</div>
            <div style={{ display: "flex", gap: 8, marginBottom: 18 }}>
              <div style={{
                width: 120, height: 80, borderRadius: 8,
                background: "linear-gradient(135deg, #FF453A22, #FF7A4522)",
                border: "1px solid var(--border-subtle)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 10, color: "var(--fg-tertiary)",
              }}>screenshot.png</div>
            </div>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <span style={{ fontSize: 11, color: "var(--fg-tertiary)", alignSelf: "center" }}>状態を変更:</span>
              {Object.entries(_BUG_STATUS).map(([k, v]) => (
                <PyBtn key={k} onClick={() => setStatus(cur.id, k)} style={{
                  background: cur.status === k ? `${v.color}33` : "var(--bg-surface-2)",
                  borderColor: cur.status === k ? v.color : "var(--border)",
                  color: cur.status === k ? v.color : "var(--fg-secondary)",
                  height: 28, padding: "0 10px", fontSize: 11,
                }}>{v.label}</PyBtn>
              ))}
            </div>
          </>
        ) : (
          <div style={{ padding: 60, textAlign: "center", color: "var(--fg-tertiary)" }}>レポートを選択してください</div>
        )}
      </div>
    </div>
  );
};

const BugDetail = ({ onBack, isAdmin: isAdminProp }) => {
  // Default: admin (主人公の李さん). Toggle persists for session.
  const [isAdmin, setIsAdmin] = m2S(isAdminProp !== undefined ? isAdminProp : true);
  return (
    <div style={{ padding: 28 }}>
      <M2_DH
        title="バグ報告"
        subtitle={isAdmin ? `${_BUG_REPORTS.length} 件 · 未対応 ${_BUG_REPORTS.filter((b) => b.status === "open").length} 件` : "問題を開発者に送信"}
        accent="#FF453A" icon="bug" onBack={onBack}
        badge={isAdmin ? "管理者" : null}
        actions={
          <div style={{
            display: "inline-flex", alignItems: "center",
            background: "var(--bg-surface-2)",
            border: "1px solid var(--border-subtle)",
            borderRadius: 8, padding: 2,
            fontSize: 11, fontWeight: 700,
          }}>
            <button onClick={() => setIsAdmin(false)} style={{
              border: 0, padding: "5px 10px", borderRadius: 6, cursor: "pointer",
              background: !isAdmin ? "var(--fg-primary)" : "transparent",
              color: !isAdmin ? "var(--bg-base, #fff)" : "var(--fg-secondary)",
              fontFamily: "inherit", fontSize: 11, fontWeight: 700,
            }}>一般</button>
            <button onClick={() => setIsAdmin(true)} style={{
              border: 0, padding: "5px 10px", borderRadius: 6, cursor: "pointer",
              background: isAdmin ? "#FF453A" : "transparent",
              color: isAdmin ? "#fff" : "var(--fg-secondary)",
              fontFamily: "inherit", fontSize: 11, fontWeight: 700,
            }}>管理者</button>
          </div>
        }
      />
      {isAdmin ? <BugAdminView /> : <BugSendForm />}
    </div>
  );
};

const fieldLbl = {
  fontSize: 11, fontWeight: 700, color: "var(--fg-secondary)",
  marginBottom: 4, display: "block", letterSpacing: "0.02em",
};

// Override
window.varA_misc_detail = { ...(window.varA_misc_detail || {}), SettingsDetail, BriefDetail, BugDetail };
