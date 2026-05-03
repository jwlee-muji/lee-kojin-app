/* global React */
// ============================================================
// LEE — Misc detail screens: Settings / Log / Bug / Manual / Brief
// ============================================================
const { useState: msS, useMemo: msM } = React;
const { DetailHeader: MS_DH } = window.varA_detail_atoms;
const MS_D = window.LEE_DATA;

// ── Common section frame ───────────────────────────────────
const Section = ({ title, children, accent = "var(--fg-primary)" }) => (
  <div style={{
    background: "var(--bg-surface)", borderRadius: 16, padding: 20,
    border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
    marginBottom: 14,
  }}>
    {title && (
      <div style={{
        fontSize: 11, fontWeight: 800, color: "var(--fg-tertiary)",
        letterSpacing: "0.08em", marginBottom: 14,
        display: "flex", alignItems: "center", gap: 8,
      }}>
        <span style={{ width: 3, height: 12, background: accent, borderRadius: 2 }} />
        {title}
      </div>
    )}
    {children}
  </div>
);

const Toggle = ({ on, onChange, accent = "#FF7A45" }) => (
  <button onClick={onChange} style={{
    width: 38, height: 22, borderRadius: 999, padding: 2,
    background: on ? accent : "var(--bg-surface-2)",
    border: "1px solid var(--border-subtle)",
    display: "flex", alignItems: "center", cursor: "pointer",
    transition: "background 0.18s",
  }}>
    <span style={{
      width: 16, height: 16, borderRadius: 999, background: "#fff",
      boxShadow: "0 1px 2px rgba(0,0,0,.2)",
      transform: on ? "translateX(16px)" : "translateX(0)",
      transition: "transform 0.18s",
    }} />
  </button>
);

const Row = ({ label, hint, children }) => (
  <div style={{
    display: "flex", alignItems: "center", gap: 12,
    padding: "12px 0", borderBottom: "1px solid var(--border-subtle)",
  }}>
    <div style={{ flex: 1 }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: "var(--fg-primary)" }}>{label}</div>
      {hint && <div style={{ fontSize: 10, color: "var(--fg-tertiary)", marginTop: 3 }}>{hint}</div>}
    </div>
    {children}
  </div>
);

// ============================================================
// Settings Detail
// ============================================================
const SettingsDetail = ({ onBack }) => {
  const [tab, setTab] = msS("general");
  const [settings, setSettings] = msS({
    notifications: { reserve: true, spot: true, imbalance: true, weather: true, mail: false },
    refresh: 30,
    theme: "auto",
    lang: "ja",
    soundOn: true,
    showBadges: true,
    twoFA: true,
    autoLogin: false,
    accentColor: "#FF7A45",
  });
  const set = (path, v) => setSettings((s) => {
    const ns = JSON.parse(JSON.stringify(s));
    const ks = path.split(".");
    let o = ns;
    for (let i = 0; i < ks.length - 1; i++) o = o[ks[i]];
    o[ks[ks.length - 1]] = v;
    return ns;
  });

  const tabs = [
    { id: "general",  label: "一般",     icon: "⚙" },
    { id: "notif",    label: "通知",     icon: "🔔" },
    { id: "account",  label: "アカウント", icon: "👤" },
    { id: "security", label: "セキュリティ", icon: "🔒" },
    { id: "data",     label: "データ",   icon: "📊" },
  ];

  return (
    <div style={{ padding: 28, maxWidth: 1100 }}>
      <MS_DH title="設定" subtitle="アカウント · 通知 · データ" accent="#8E8E93" icon="setting" onBack={onBack} />

      <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 16 }}>
        <div style={{
          background: "var(--bg-surface)", borderRadius: 14, padding: 8,
          border: "1px solid var(--border-subtle)",
          height: "fit-content",
        }}>
          {tabs.map((t) => {
            const on = tab === t.id;
            return (
              <button key={t.id} onClick={() => setTab(t.id)} style={{
                width: "100%", display: "flex", alignItems: "center", gap: 10,
                padding: "10px 12px", borderRadius: 9, border: 0,
                background: on ? "var(--bg-surface-2)" : "transparent",
                color: on ? "var(--fg-primary)" : "var(--fg-secondary)",
                fontFamily: "inherit", fontSize: 12, fontWeight: on ? 800 : 600,
                cursor: "pointer", textAlign: "left", marginBottom: 1,
              }}>
                <span style={{ fontSize: 14 }}>{t.icon}</span>
                <span>{t.label}</span>
              </button>
            );
          })}
        </div>

        <div>
          {tab === "general" && (
            <>
              <Section title="表示">
                <Row label="テーマ" hint="ダーク / ライト / システムに合わせる">
                  <div style={{ display: "flex", padding: 3, gap: 1, background: "var(--bg-surface-2)", borderRadius: 8, border: "1px solid var(--border-subtle)" }}>
                    {[["ライト", "light"], ["ダーク", "dark"], ["自動", "auto"]].map(([l, v]) => (
                      <button key={v} onClick={() => set("theme", v)} style={{
                        padding: "5px 14px", borderRadius: 5, border: 0,
                        background: settings.theme === v ? "#FF7A45" : "transparent",
                        color: settings.theme === v ? "#fff" : "var(--fg-secondary)",
                        fontFamily: "inherit", fontSize: 11, fontWeight: 700, cursor: "pointer",
                      }}>{l}</button>
                    ))}
                  </div>
                </Row>
                <Row label="言語">
                  <select value={settings.lang} onChange={(e) => set("lang", e.target.value)} style={selectStyle}>
                    <option value="ja">日本語</option>
                    <option value="en">English</option>
                    <option value="ko">한국어</option>
                  </select>
                </Row>
                <Row label="アクセントカラー">
                  <div style={{ display: "flex", gap: 6 }}>
                    {["#FF7A45", "#0A84FF", "#34C759", "#A78BFA", "#FF453A", "#FFCC00"].map((c) => (
                      <button key={c} onClick={() => set("accentColor", c)} style={{
                        width: 22, height: 22, borderRadius: 999, border: 0,
                        background: c, cursor: "pointer",
                        boxShadow: settings.accentColor === c ? `0 0 0 2px var(--bg-surface), 0 0 0 4px ${c}` : "none",
                      }} />
                    ))}
                  </div>
                </Row>
                <Row label="バッジを表示" hint="メニュー項目に未読数を表示">
                  <Toggle on={settings.showBadges} onChange={() => set("showBadges", !settings.showBadges)} />
                </Row>
              </Section>
              <Section title="動作">
                <Row label="自動更新間隔" hint={`${settings.refresh} 秒ごとに最新データを取得`}>
                  <input type="range" min="10" max="300" step="10"
                    value={settings.refresh}
                    onChange={(e) => set("refresh", +e.target.value)}
                    style={{ width: 180, accentColor: "#FF7A45" }} />
                  <span style={{ fontSize: 11, fontWeight: 700, fontFamily: "var(--font-mono)", minWidth: 36, textAlign: "right" }}>{settings.refresh}s</span>
                </Row>
                <Row label="効果音" hint="アラート時にビープ音を鳴らす">
                  <Toggle on={settings.soundOn} onChange={() => set("soundOn", !settings.soundOn)} />
                </Row>
              </Section>
            </>
          )}

          {tab === "notif" && (
            <Section title="通知設定">
              {[
                ["reserve", "予備率アラート", "予備率が閾値を下回ったとき"],
                ["spot", "スポット価格アラート", "急騰・急落時"],
                ["imbalance", "インバランス単価アラート", "30 円/kWh を超過"],
                ["weather", "気象警報", "Open-Meteo より天候警告"],
                ["mail", "メール通知 (Push)", "未読メール 3 件以上"],
              ].map(([k, lbl, hint]) => (
                <Row key={k} label={lbl} hint={hint}>
                  <Toggle on={settings.notifications[k]} onChange={() => set(`notifications.${k}`, !settings.notifications[k])} />
                </Row>
              ))}
            </Section>
          )}

          {tab === "account" && (
            <>
              <Section title="プロフィール">
                <div style={{ display: "flex", gap: 16, alignItems: "center", padding: "8px 0 16px" }}>
                  <div style={{
                    width: 64, height: 64, borderRadius: 999,
                    background: "linear-gradient(135deg, #FF7A45, #5856D6)",
                    color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 24, fontWeight: 800,
                  }}>李</div>
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 800 }}>{MS_D.user.name}</div>
                    <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>{MS_D.user.email}</div>
                    <div style={{ fontSize: 10, color: "var(--fg-tertiary)", marginTop: 4 }}>{MS_D.user.role} · 在籍 2.3 年</div>
                  </div>
                </div>
                <Row label="表示名"><input defaultValue={MS_D.user.name} style={inputStyle} /></Row>
                <Row label="役割"><input defaultValue={MS_D.user.role} style={inputStyle} /></Row>
                <Row label="部署"><input defaultValue="エネルギートレーディング部" style={inputStyle} /></Row>
              </Section>
              <Section title="連携">
                {[
                  ["Google", "lee.tanaka@enex.co.jp", true, "#5B8DEF"],
                  ["Microsoft 365", "未連携", false, "#0078D4"],
                  ["Slack", "@lee.tanaka", true, "#4A154B"],
                ].map(([name, val, on, color]) => (
                  <Row key={name} label={name} hint={val}>
                    <button style={{
                      padding: "6px 14px", borderRadius: 8, border: "1px solid",
                      borderColor: on ? color : "var(--border)",
                      background: on ? `${color}1f` : "transparent",
                      color: on ? color : "var(--fg-secondary)",
                      fontFamily: "inherit", fontSize: 11, fontWeight: 700, cursor: "pointer",
                    }}>{on ? "接続中" : "接続"}</button>
                  </Row>
                ))}
              </Section>
            </>
          )}

          {tab === "security" && (
            <>
              <Section title="認証">
                <Row label="2 段階認証" hint="ログイン時にコードを要求"><Toggle on={settings.twoFA} onChange={() => set("twoFA", !settings.twoFA)} /></Row>
                <Row label="自動ログイン" hint="このデバイスで再ログインを省略"><Toggle on={settings.autoLogin} onChange={() => set("autoLogin", !settings.autoLogin)} /></Row>
                <Row label="パスワード変更">
                  <button style={btnSm}>変更する</button>
                </Row>
              </Section>
              <Section title="セッション">
                {[
                  ["macOS · Chrome 126", "東京 (現在)", true],
                  ["iOS · Safari 17",     "東京 · 12 分前", false],
                  ["Windows · Edge 124",  "大阪 · 昨日", false],
                ].map(([dev, where, cur]) => (
                  <Row key={dev} label={dev} hint={where}>
                    {cur ? (
                      <span style={{ fontSize: 10, fontWeight: 800, padding: "3px 10px", borderRadius: 999, background: "#34C7591f", color: "#34C759" }}>このセッション</span>
                    ) : (
                      <button style={{ ...btnSm, color: "#FF453A" }}>ログアウト</button>
                    )}
                  </Row>
                ))}
              </Section>
            </>
          )}

          {tab === "data" && (
            <>
              <Section title="ストレージ">
                <Row label="ローカルキャッシュ" hint="ブラウザに保存されたデータ">
                  <span style={{ fontSize: 12, fontWeight: 700, fontFamily: "var(--font-mono)" }}>42.3 MB</span>
                  <button style={{ ...btnSm, marginLeft: 10 }}>クリア</button>
                </Row>
                <Row label="設定エクスポート"><button style={btnSm}>JSON をダウンロード</button></Row>
                <Row label="設定インポート"><button style={btnSm}>ファイルを選択</button></Row>
              </Section>
              <Section title="危険ゾーン">
                <Row label="全データのリセット" hint="設定・ローカルメモを全て削除します">
                  <button style={{ ...btnSm, background: "#FF453A1f", color: "#FF453A", borderColor: "#FF453A33" }}>リセット</button>
                </Row>
              </Section>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

// ============================================================
// Log Detail
// ============================================================
const LOG_ENTRIES = [
  { time: "14:08:24", level: "WARN",  src: "OCCTO",     msg: "東京エリア予備率 6.2% — しきい値 8% を下回る" },
  { time: "13:48:12", level: "INFO",  src: "JEPX",      msg: "スポット市場約定: システム平均 12.84 円/kWh" },
  { time: "13:35:01", level: "INFO",  src: "Sync",      msg: "気象データ同期完了 (Open-Meteo)" },
  { time: "13:20:55", level: "INFO",  src: "JKM",       msg: "JKM Asia LNG closed at $14.32 (-1.2%)" },
  { time: "12:14:30", level: "DEBUG", src: "Auth",      msg: "Token refreshed (user=lee.tanaka@enex.co.jp)" },
  { time: "11:30:18", level: "INFO",  src: "EIA",       msg: "Weekly Petroleum Status Report imported" },
  { time: "11:00:09", level: "ERROR", src: "Plant API", msg: "発電所 #324 (北海道苫東) からの取得失敗 (Timeout)" },
  { time: "10:42:00", level: "INFO",  src: "Plant API", msg: "リトライ成功 — #324 接続復旧" },
  { time: "09:42:18", level: "WARN",  src: "Weather",   msg: "九州地域 雷雨警報を取得" },
  { time: "09:20:44", level: "INFO",  src: "Sync",      msg: "全エリア HJKS データ同期完了 (10/10)" },
  { time: "09:14:00", level: "INFO",  src: "Calendar",  msg: "Google カレンダー同期完了 (12 件)" },
  { time: "09:00:01", level: "INFO",  src: "System",    msg: "日次バックアップ完了 (snapshot_20250122)" },
  { time: "08:42:33", level: "DEBUG", src: "AI",        msg: "予測モデル v2.3 をロード" },
  { time: "08:30:00", level: "INFO",  src: "System",    msg: "アプリ起動 — LEE v3.4.2" },
];
const LOG_LEVEL_COLOR = { ERROR: "#FF453A", WARN: "#FF9F0A", INFO: "#0A84FF", DEBUG: "#8E8E93" };

const LogDetail = ({ onBack }) => {
  const [filterLvl, setFilterLvl] = msS(new Set(["ERROR", "WARN", "INFO", "DEBUG"]));
  const [filterSrc, setFilterSrc] = msS("all");
  const [search, setSearch] = msS("");
  const [autoScroll, setAutoScroll] = msS(true);

  const sources = ["all", ...Array.from(new Set(LOG_ENTRIES.map((l) => l.src)))];
  const counts = msM(() => {
    const c = { ERROR: 0, WARN: 0, INFO: 0, DEBUG: 0 };
    LOG_ENTRIES.forEach((l) => { c[l.level]++; });
    return c;
  }, []);

  const filtered = LOG_ENTRIES.filter((l) =>
    filterLvl.has(l.level) &&
    (filterSrc === "all" || l.src === filterSrc) &&
    (search.trim() === "" || `${l.src} ${l.msg}`.toLowerCase().includes(search.toLowerCase()))
  );

  const toggleLvl = (l) => setFilterLvl((s) => {
    const n = new Set(s);
    if (n.has(l)) n.delete(l); else n.add(l);
    return n;
  });

  return (
    <div style={{ padding: 28 }}>
      <MS_DH title="ログ" subtitle="システムイベント · リアルタイム監視" accent="#8E8E93" icon="log" onBack={onBack} badge={`${LOG_ENTRIES.length} 件`} />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16 }}>
        {[
          ["ERROR", "#FF453A"], ["WARN", "#FF9F0A"], ["INFO", "#0A84FF"], ["DEBUG", "#8E8E93"],
        ].map(([l, c]) => (
          <button key={l} onClick={() => toggleLvl(l)} style={{
            background: filterLvl.has(l) ? `${c}1f` : "var(--bg-surface)",
            border: `1px solid ${filterLvl.has(l) ? c : "var(--border-subtle)"}`,
            borderRadius: 12, padding: 14, cursor: "pointer", textAlign: "left",
            opacity: filterLvl.has(l) ? 1 : 0.55,
          }}>
            <div style={{ fontSize: 10, fontWeight: 800, color: c, letterSpacing: "0.08em" }}>{l}</div>
            <div style={{ fontSize: 22, fontWeight: 800, fontFamily: "var(--font-mono)", color: "var(--fg-primary)", marginTop: 4 }}>{counts[l]}</div>
            <div style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>{filterLvl.has(l) ? "表示中" : "非表示"}</div>
          </button>
        ))}
      </div>

      <div style={{
        background: "var(--bg-surface)", borderRadius: 14,
        border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
        padding: 12, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
        marginBottom: 12,
      }}>
        <div style={{
          display: "flex", alignItems: "center", gap: 6, padding: "5px 10px",
          borderRadius: 8, background: "var(--bg-surface-2)",
          border: "1px solid var(--border-subtle)", flex: 1, minWidth: 200,
        }}>
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--fg-tertiary)" strokeWidth="2.5"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="メッセージを検索..." style={{
            flex: 1, border: 0, outline: 0, background: "transparent",
            color: "var(--fg-primary)", fontFamily: "var(--font-mono)", fontSize: 11,
          }} />
        </div>

        <select value={filterSrc} onChange={(e) => setFilterSrc(e.target.value)} style={selectStyle}>
          {sources.map((s) => <option key={s} value={s}>{s === "all" ? "すべてのソース" : s}</option>)}
        </select>

        <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
          <Toggle on={autoScroll} onChange={() => setAutoScroll(!autoScroll)} accent="#34C759" />
          <span style={{ fontSize: 11, fontWeight: 600 }}>自動スクロール</span>
        </label>

        <button style={btnSm}>エクスポート</button>
      </div>

      <div style={{
        background: "#0F1116", borderRadius: 14, padding: 14,
        border: "1px solid var(--border-subtle)",
        fontFamily: "var(--font-mono)", fontSize: 11, lineHeight: 1.65,
        color: "#E5E7EB", maxHeight: 480, overflow: "auto",
      }}>
        {filtered.length === 0 && (
          <div style={{ padding: 30, textAlign: "center", color: "#6B7280" }}>該当するログはありません</div>
        )}
        {filtered.map((l, i) => (
          <div key={i} style={{ display: "flex", gap: 12, padding: "3px 4px", borderRadius: 4 }}>
            <span style={{ color: "#6B7280" }}>{l.time}</span>
            <span style={{
              color: LOG_LEVEL_COLOR[l.level], fontWeight: 800,
              minWidth: 50, letterSpacing: "0.04em",
            }}>{l.level}</span>
            <span style={{ color: "#A78BFA", minWidth: 90 }}>[{l.src}]</span>
            <span style={{ color: "#E5E7EB" }}>{l.msg}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

// ============================================================
// Bug Report Detail
// ============================================================
const BUG_REPORTS = [
  { id: "B-1042", status: "open",     priority: "high",   title: "JKM チャートのツールチップが部分的に表示されない", reporter: "鈴木", date: "2025-01-22 10:42", area: "Chart" },
  { id: "B-1038", status: "fixed",    priority: "medium", title: "サイドバー Gmail バッジが既読後も残る",         reporter: "田中", date: "2025-01-21 17:08", area: "UI" },
  { id: "B-1031", status: "open",     priority: "low",    title: "天気アイコンのアニメーションが iPhone で停止",   reporter: "山田", date: "2025-01-20 12:30", area: "Animation" },
  { id: "B-1029", status: "wip",      priority: "high",   title: "予備率 API レスポンスが時々 500 を返す",          reporter: "李",   date: "2025-01-19 19:14", area: "Backend" },
  { id: "B-1024", status: "wontfix",  priority: "low",    title: "PWA インストール時にアイコンが暗い",              reporter: "佐藤", date: "2025-01-18 08:55", area: "PWA" },
];
const BUG_STATUS = {
  open:    { label: "未対応", color: "#FF453A" },
  wip:     { label: "対応中", color: "#FF9F0A" },
  fixed:   { label: "解決",   color: "#34C759" },
  wontfix: { label: "対応せず", color: "#8E8E93" },
};
const BUG_PRIORITY = { high: "#FF453A", medium: "#FF9F0A", low: "#0A84FF" };

const BugDetail = ({ onBack }) => {
  const [filter, setFilter] = msS("all");
  const [openId, setOpenId] = msS(BUG_REPORTS[0].id);
  const filtered = filter === "all" ? BUG_REPORTS : BUG_REPORTS.filter((b) => b.status === filter);
  const cur = BUG_REPORTS.find((b) => b.id === openId) || filtered[0];

  return (
    <div style={{ padding: 28 }}>
      <MS_DH title="バグ報告" subtitle={`${BUG_REPORTS.length} 件 · 未対応 ${BUG_REPORTS.filter(b => b.status === "open").length} 件`} accent="#FF453A" icon="bug" onBack={onBack} badge={`${BUG_REPORTS.filter(b => b.status === "open").length} 件未対応`} />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1.4fr", gap: 14 }}>
        {/* List */}
        <div style={{
          background: "var(--bg-surface)", borderRadius: 16, padding: 8,
          border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
          maxHeight: 580, overflow: "auto",
        }}>
          <div style={{
            display: "flex", gap: 4, padding: "8px 8px 4px",
            borderBottom: "1px solid var(--border-subtle)", marginBottom: 4,
            position: "sticky", top: 0, background: "var(--bg-surface)", zIndex: 1,
          }}>
            {[["all", "すべて"], ["open", "未対応"], ["wip", "対応中"], ["fixed", "解決"]].map(([k, l]) => {
              const on = filter === k;
              return (
                <button key={k} onClick={() => setFilter(k)} style={{
                  padding: "5px 11px", borderRadius: 7, border: 0,
                  background: on ? "#FF453A1f" : "transparent",
                  color: on ? "#FF453A" : "var(--fg-secondary)",
                  fontFamily: "inherit", fontSize: 11, fontWeight: 700, cursor: "pointer",
                }}>{l}</button>
              );
            })}
            <div style={{ flex: 1 }} />
            <button style={{ ...btnSm, background: "#FF453A", color: "#fff", borderColor: "#FF453A" }}>+ 新規報告</button>
          </div>
          {filtered.map((b) => {
            const active = openId === b.id;
            const st = BUG_STATUS[b.status];
            return (
              <div key={b.id} onClick={() => setOpenId(b.id)} style={{
                padding: "11px 12px", borderRadius: 9, cursor: "pointer",
                background: active ? "#FF453A12" : "transparent",
                borderLeft: active ? "3px solid #FF453A" : "3px solid transparent",
                marginBottom: 2,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                  <span style={{
                    fontSize: 10, fontFamily: "var(--font-mono)", fontWeight: 800,
                    color: "var(--fg-tertiary)",
                  }}>{b.id}</span>
                  <span style={{
                    fontSize: 9, fontWeight: 800, padding: "2px 7px", borderRadius: 999,
                    background: `${st.color}1f`, color: st.color,
                    border: `1px solid ${st.color}33`,
                  }}>{st.label}</span>
                  <span style={{
                    width: 6, height: 6, borderRadius: 999, background: BUG_PRIORITY[b.priority],
                  }} title={`Priority: ${b.priority}`} />
                  <div style={{ flex: 1 }} />
                  <span style={{ fontSize: 9, color: "var(--fg-tertiary)" }}>{b.area}</span>
                </div>
                <div style={{
                  fontSize: 12, fontWeight: 700, color: "var(--fg-primary)",
                  lineHeight: 1.4, marginBottom: 4,
                }}>{b.title}</div>
                <div style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>
                  {b.reporter} · {b.date}
                </div>
              </div>
            );
          })}
        </div>

        {/* Detail */}
        <div style={{
          background: "var(--bg-surface)", borderRadius: 16, padding: 22,
          border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
        }}>
          {cur && (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 800, color: "var(--fg-tertiary)" }}>{cur.id}</span>
                <span style={{
                  fontSize: 10, fontWeight: 800, padding: "3px 10px", borderRadius: 999,
                  background: `${BUG_STATUS[cur.status].color}1f`, color: BUG_STATUS[cur.status].color,
                  border: `1px solid ${BUG_STATUS[cur.status].color}33`,
                }}>{BUG_STATUS[cur.status].label}</span>
                <span style={{
                  fontSize: 10, fontWeight: 800, padding: "3px 10px", borderRadius: 999,
                  background: `${BUG_PRIORITY[cur.priority]}1f`, color: BUG_PRIORITY[cur.priority],
                  textTransform: "uppercase", letterSpacing: "0.06em",
                }}>{cur.priority}</span>
              </div>
              <div style={{ fontSize: 18, fontWeight: 800, marginBottom: 14, lineHeight: 1.4 }}>{cur.title}</div>
              <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "8px 14px", marginBottom: 18, fontSize: 11 }}>
                <span style={{ color: "var(--fg-tertiary)" }}>報告者</span>
                <span style={{ fontWeight: 700 }}>{cur.reporter}</span>
                <span style={{ color: "var(--fg-tertiary)" }}>報告日</span>
                <span style={{ fontFamily: "var(--font-mono)" }}>{cur.date}</span>
                <span style={{ color: "var(--fg-tertiary)" }}>領域</span>
                <span>{cur.area}</span>
                <span style={{ color: "var(--fg-tertiary)" }}>環境</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10 }}>macOS 14.5 / Chrome 126 / LEE v3.4.2</span>
              </div>

              <div style={{ fontSize: 11, fontWeight: 800, color: "var(--fg-tertiary)", marginBottom: 8, letterSpacing: "0.08em" }}>再現手順</div>
              <ol style={{ paddingLeft: 18, fontSize: 12, lineHeight: 1.8, color: "var(--fg-primary)", marginBottom: 18 }}>
                <li>ダッシュボードを開く</li>
                <li>JKM ウィジェットの「30 日」タブをクリック</li>
                <li>チャート上にホバーするとツールチップが描画されない</li>
              </ol>

              <div style={{ fontSize: 11, fontWeight: 800, color: "var(--fg-tertiary)", marginBottom: 8, letterSpacing: "0.08em" }}>添付</div>
              <div style={{ display: "flex", gap: 8, marginBottom: 18 }}>
                <div style={{
                  width: 120, height: 80, borderRadius: 8,
                  background: "linear-gradient(135deg, #FF453A22, #FF7A4522)",
                  border: "1px solid var(--border-subtle)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 10, color: "var(--fg-tertiary)",
                }}>screenshot.png</div>
              </div>

              <div style={{ display: "flex", gap: 8 }}>
                <button style={{ ...btnSm, background: "#FF453A", color: "#fff", borderColor: "#FF453A" }}>状態を変更</button>
                <button style={btnSm}>担当者を割り当て</button>
                <button style={btnSm}>コメント追加</button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

// ============================================================
// Manual Detail — 移動済 → varA-manual-detail.jsx
// ============================================================
const ManualDetail = window.varA_manual_detail?.ManualDetail || (() => null);

// ── (旧) 静的マニュアル — 互換のため未使用フラグ付きで残置 ──
// eslint-disable-next-line no-unused-vars
const _OLD_ManualDetail = ({ onBack }) => {
  const [section, setSection] = msS("intro");
  const [item, setItem] = msS("LEE について");
  const cur = MANUAL_SECTIONS.find((s) => s.id === section);

  return (
    <div style={{ padding: 28, maxWidth: 1100 }}>
      <MS_DH title="マニュアル" subtitle="LEE 電力モニター ユーザーガイド v3.4" accent="#5856D6" icon="manual" onBack={onBack} />

      <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 16 }}>
        <div style={{
          background: "var(--bg-surface)", borderRadius: 14, padding: 12,
          border: "1px solid var(--border-subtle)", height: "fit-content",
        }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 6, padding: "5px 10px",
            borderRadius: 8, background: "var(--bg-surface-2)",
            border: "1px solid var(--border-subtle)", marginBottom: 10,
          }}>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--fg-tertiary)" strokeWidth="2.5"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input placeholder="検索..." style={{
              flex: 1, border: 0, outline: 0, background: "transparent",
              color: "var(--fg-primary)", fontFamily: "inherit", fontSize: 11,
            }} />
          </div>
          {MANUAL_SECTIONS.map((s) => (
            <div key={s.id} style={{ marginBottom: 6 }}>
              <button onClick={() => { setSection(s.id); setItem(s.items[0]); }} style={{
                width: "100%", padding: "7px 10px", border: 0, borderRadius: 7,
                background: section === s.id ? "#5856D61f" : "transparent",
                color: section === s.id ? "#5856D6" : "var(--fg-primary)",
                fontFamily: "inherit", fontSize: 12, fontWeight: 800,
                cursor: "pointer", textAlign: "left",
              }}>{s.title}</button>
              {section === s.id && (
                <div style={{ paddingLeft: 12, marginTop: 2 }}>
                  {s.items.map((it) => (
                    <button key={it} onClick={() => setItem(it)} style={{
                      width: "100%", padding: "5px 10px", border: 0, borderRadius: 6,
                      background: item === it ? "var(--bg-surface-2)" : "transparent",
                      color: item === it ? "#5856D6" : "var(--fg-secondary)",
                      fontFamily: "inherit", fontSize: 11, fontWeight: item === it ? 700 : 500,
                      cursor: "pointer", textAlign: "left", marginBottom: 1,
                    }}>{it}</button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        <div style={{
          background: "var(--bg-surface)", borderRadius: 16, padding: 28,
          border: "1px solid var(--border-subtle)", boxShadow: "var(--shadow-sm)",
        }}>
          <div style={{ fontSize: 10, color: "var(--fg-tertiary)", fontWeight: 700, letterSpacing: "0.06em", marginBottom: 6 }}>
            {cur?.title} →
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 800, marginBottom: 14, letterSpacing: "-0.02em" }}>{item}</h1>
          <div style={{ fontSize: 13, color: "var(--fg-primary)", lineHeight: 1.8 }}>
            <p style={{ marginBottom: 14 }}>
              <b>LEE 電力モニター</b> は、JEPX スポット市場、OCCTO 予備率、インバランス、JKM LNG、気象データ、発電稼働状況など日本電力市場のリアルタイム監視を一元化するダッシュボードアプリです。
            </p>
            <h3 style={{ fontSize: 14, fontWeight: 800, marginTop: 18, marginBottom: 8 }}>主な機能</h3>
            <ul style={{ paddingLeft: 18, marginBottom: 14 }}>
              <li style={{ marginBottom: 4 }}>スポット価格・予備率・インバランス単価のリアルタイム表示</li>
              <li style={{ marginBottom: 4 }}>10 エリア別、30 分単位の詳細グラフ</li>
              <li style={{ marginBottom: 4 }}>LNG・原油・石炭・為替などエネルギー指標の追跡</li>
              <li style={{ marginBottom: 4 }}>発電所別・電源種別の稼働状況可視化</li>
              <li style={{ marginBottom: 4 }}>Google カレンダー・Gmail との連携</li>
              <li style={{ marginBottom: 4 }}>AI による要約・予測ブリーフィング</li>
            </ul>
            <h3 style={{ fontSize: 14, fontWeight: 800, marginTop: 18, marginBottom: 8 }}>関連リンク</h3>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {["クイックスタート", "API リファレンス", "サポートに連絡"].map((l) => (
                <span key={l} style={{
                  padding: "6px 12px", borderRadius: 999,
                  background: "#5856D61f", color: "#5856D6",
                  fontSize: 11, fontWeight: 700, cursor: "pointer",
                }}>→ {l}</span>
              ))}
            </div>
            <div style={{ marginTop: 20, padding: 14, background: "var(--bg-surface-2)", borderRadius: 10, border: "1px solid var(--border-subtle)" }}>
              <div style={{ fontSize: 10, fontWeight: 800, color: "var(--fg-tertiary)", marginBottom: 6, letterSpacing: "0.06em" }}>💡 Tips</div>
              <div style={{ fontSize: 11, color: "var(--fg-secondary)", lineHeight: 1.6 }}>
                各ウィジェットをクリックすると詳細画面に遷移します。詳細画面では時間単位・エリア別・期間別など多次元での分析が可能です。
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// ============================================================
// AI Brief Detail
// ============================================================
const BRIEF_SECTIONS = [
  {
    id: "summary",
    icon: "📊",
    title: "本日のマーケットサマリー",
    accent: "#FF7A45",
    items: [
      { label: "スポット価格", value: "12.84 円/kWh", delta: "+1.2", note: "前日比、東京エリアは 15.42 と高値圏" },
      { label: "予備率",       value: "6.2 %",        delta: "-1.8", note: "東京エリア、OCCTO 注意喚起発令中" },
      { label: "インバランス", value: "38.5 円/kWh",  delta: "+4.3", note: "夕方ピーク帯で最高値を記録" },
      { label: "JKM LNG",      value: "$14.32",       delta: "-1.2", note: "アジアスポット、4 営業日連続下落" },
    ],
  },
];

const BRIEF_INSIGHTS = [
  { title: "東京エリアの需給ひっ迫が継続中", detail: "暖房需要の増加と太陽光発電の早期低下が重なり、夕方 18:00-19:30 の時間帯で予備率が 6% を下回る見通し。揚水発電・地域間融通の活用が必要。", priority: "high" },
  { title: "LNG 価格は下落基調 — 調達タイミング有利", detail: "JKM Asia LNG が $14.32 まで下落 (前日比 -1.2%)。Q1 調達計画に対しスポット比率を 10-15% 引き上げる余地あり。", priority: "medium" },
  { title: "九州エリアで雷雨警報", detail: "鹿児島県を中心に明日午後にかけて雷雨が予想され、太陽光発電量に -30% 程度の影響見込み。", priority: "medium" },
  { title: "週末は需要減少", detail: "土日は気温が比較的高めで需要は前週比 -8% と推定。スポット価格は 10-12 円/kWh で安定。", priority: "low" },
];

const BriefDetail = ({ onBack }) => {
  return (
    <div style={{ padding: 28, maxWidth: 1100 }}>
      <MS_DH title="AI ブリーフィング" subtitle="2025年1月22日 (水) — 自動生成 09:14" accent="#5856D6" icon="brief" onBack={onBack} badge="AI 生成" />

      <div style={{
        background: "linear-gradient(135deg, #5856D612, #FF7A4512)",
        borderRadius: 18, padding: 24, marginBottom: 16,
        border: "1px solid var(--border-subtle)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: "linear-gradient(135deg, #5856D6, #FF7A45)",
            color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 18, fontWeight: 800,
          }}>✦</div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 800 }}>本日の要点</div>
            <div style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>過去 24 時間のデータを基に AI が要約</div>
          </div>
          <div style={{ flex: 1 }} />
          <button style={{
            padding: "7px 14px", borderRadius: 9, border: 0,
            background: "#5856D6", color: "#fff",
            fontFamily: "inherit", fontSize: 11, fontWeight: 800, cursor: "pointer",
          }}>↻ 再生成</button>
        </div>
        <div style={{ fontSize: 14, color: "var(--fg-primary)", lineHeight: 1.8 }}>
          東京エリアでは <b style={{ color: "#FF453A" }}>予備率が 6.2%</b> まで低下し OCCTO から注意喚起が発令中。夕方 18:00-19:30 のピーク帯で最もタイトな状況が見込まれます。一方、<b style={{ color: "#34C759" }}>LNG 市場は弱含み</b> (JKM $14.32, -1.2%) で、調達タイミングとしては有利な局面。九州地域では雷雨警報により太陽光発電に影響が出る可能性があります。
        </div>
      </div>

      <Section title="主要指標" accent="#FF7A45">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
          {BRIEF_SECTIONS[0].items.map((it) => {
            const up = it.delta.startsWith("+");
            return (
              <div key={it.label} style={{
                padding: 14, borderRadius: 10,
                background: "var(--bg-surface-2)",
                border: "1px solid var(--border-subtle)",
              }}>
                <div style={{ fontSize: 10, color: "var(--fg-tertiary)", fontWeight: 700, marginBottom: 6 }}>{it.label}</div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 4 }}>
                  <div style={{ fontSize: 18, fontWeight: 800, fontFamily: "var(--font-mono)" }}>{it.value}</div>
                  <div style={{ fontSize: 11, fontWeight: 800, color: up ? "#34C759" : "#FF453A", fontFamily: "var(--font-mono)" }}>{it.delta}</div>
                </div>
                <div style={{ fontSize: 10, color: "var(--fg-tertiary)", lineHeight: 1.4 }}>{it.note}</div>
              </div>
            );
          })}
        </div>
      </Section>

      <Section title="AI インサイト" accent="#5856D6">
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {BRIEF_INSIGHTS.map((ins, i) => {
            const colors = { high: "#FF453A", medium: "#FF9F0A", low: "#0A84FF" };
            return (
              <div key={i} style={{
                padding: 14, borderRadius: 12,
                background: "var(--bg-surface-2)",
                border: "1px solid var(--border-subtle)",
                borderLeft: `4px solid ${colors[ins.priority]}`,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                  <span style={{
                    fontSize: 9, fontWeight: 800, padding: "2px 8px", borderRadius: 999,
                    background: `${colors[ins.priority]}1f`, color: colors[ins.priority],
                    letterSpacing: "0.06em", textTransform: "uppercase",
                  }}>{ins.priority}</span>
                  <span style={{ fontSize: 13, fontWeight: 800 }}>{ins.title}</span>
                </div>
                <div style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.6 }}>{ins.detail}</div>
              </div>
            );
          })}
        </div>
      </Section>

      <Section title="今後 24 時間の予測" accent="#0A84FF">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
          {[
            { time: "今夜 18:00-22:00", label: "ピーク帯", value: "18.5 円/kWh 想定", color: "#FF453A" },
            { time: "明日 03:00-06:00", label: "ボトム",   value: "8.2 円/kWh 想定",  color: "#34C759" },
            { time: "明日 18:00-20:00", label: "ピーク帯", value: "16.0 円/kWh 想定", color: "#FF9F0A" },
          ].map((p, i) => (
            <div key={i} style={{
              padding: 14, borderRadius: 12,
              background: "var(--bg-surface-2)",
              border: "1px solid var(--border-subtle)",
            }}>
              <div style={{ fontSize: 10, color: "var(--fg-tertiary)", fontWeight: 700, marginBottom: 4, fontFamily: "var(--font-mono)" }}>{p.time}</div>
              <div style={{ fontSize: 11, fontWeight: 800, color: p.color, marginBottom: 6 }}>{p.label}</div>
              <div style={{ fontSize: 14, fontWeight: 800, fontFamily: "var(--font-mono)" }}>{p.value}</div>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
};

// ── shared button styles ──
const btnSm = {
  padding: "6px 12px", borderRadius: 8,
  border: "1px solid var(--border)",
  background: "var(--bg-surface-2)", color: "var(--fg-secondary)",
  fontFamily: "inherit", fontSize: 11, fontWeight: 700, cursor: "pointer",
};
const inputStyle = {
  padding: "6px 10px", borderRadius: 8,
  border: "1px solid var(--border)",
  background: "var(--bg-surface-2)", color: "var(--fg-primary)",
  fontFamily: "inherit", fontSize: 12, fontWeight: 600, minWidth: 200,
};
const selectStyle = { ...inputStyle, minWidth: 140, cursor: "pointer" };

window.varA_misc_detail = { SettingsDetail, LogDetail, BugDetail, ManualDetail, BriefDetail };
