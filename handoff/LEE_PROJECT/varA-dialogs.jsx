/* ============================================================
 * LEE Dialogs — 시스템 다이얼로그 모킹업 모음
 *  - 업데이트 4종: 안내 / 다운로드 진행 / 준비완료 / 다운로드 에러
 *  - 종료 확인 (3 버튼)
 *  - 로그아웃 확인
 *  - 起動エラー
 *  - 一般 confirm / info / warning / error
 *  - アクセス申請 (SMTP 送信 폼)
 *  - カテゴリ管理
 *  - 画像 편집 (赤ペン)
 *  - 画像 미리보기
 *
 *  공통 스펙:
 *   - 타이틀바 (macOS 풍 traffic lights + 아이콘 + 제목)
 *   - 본문 + 버튼 풋터
 *   - 다크 베이스 + 액센트 컬러
 * ============================================================ */
const { useState: dlg_S } = React;

/* ---------- Dialog Frame ---------- */
const DLGFrame = ({ children, title = "", icon = null, width = 480, height, theme = "dark", style }) => (
  <div data-theme={theme} style={{
    width, height,
    background: "var(--bg-surface)",
    color: "var(--fg-primary)",
    border: "1px solid var(--border-subtle)",
    borderRadius: 12,
    fontFamily: "var(--font-sans)",
    boxShadow: "var(--shadow-lg, 0 24px 80px -16px rgba(0,0,0,0.6))",
    overflow: "hidden",
    display: "flex", flexDirection: "column",
    ...(style || {}),
  }}>
    {/* macOS 風 타이틀바 */}
    <div style={{
      height: 32,
      background: "var(--bg-surface-2)",
      borderBottom: "1px solid var(--border-subtle)",
      display: "flex", alignItems: "center", padding: "0 12px",
      gap: 8,
      flexShrink: 0,
    }}>
      <span style={{ width: 11, height: 11, borderRadius: 999, background: "#FF5F57" }}/>
      <span style={{ width: 11, height: 11, borderRadius: 999, background: "#FEBC2E" }}/>
      <span style={{ width: 11, height: 11, borderRadius: 999, background: "#28C840" }}/>
      <div style={{ flex: 1, textAlign: "center", fontSize: 11, color: "var(--fg-tertiary)", fontWeight: 600, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
        {icon}
        {title}
      </div>
      <span style={{ width: 33 }}/>
    </div>
    <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
      {children}
    </div>
  </div>
);

/* ---------- 공통 atoms ---------- */
const DLGIcon = ({ kind = "info", size = 56 }) => {
  // info(blue) / warning(amber) / error(red) / success(green) / question(blue)
  const tone = {
    info:    { bg: "#2C7BE5", glyph: "i" },
    warning: { bg: "#FF9F0A", glyph: "!" },
    error:   { bg: "#FF453A", glyph: "✕" },
    success: { bg: "#30D158", glyph: "✓" },
    question:{ bg: "#FF7A45", glyph: "?" },
    update:  { bg: "#FF7A45", glyph: "↑" },
  }[kind];
  return (
    <div style={{
      width: size, height: size, borderRadius: size * 0.28,
      background: `color-mix(in srgb, ${tone.bg} 16%, transparent)`,
      color: tone.bg,
      border: `1px solid color-mix(in srgb, ${tone.bg} 30%, transparent)`,
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      fontSize: size * 0.5, fontWeight: 800, fontFamily: "var(--font-mono)",
      flexShrink: 0,
    }}>
      {tone.glyph}
    </div>
  );
};

const DLGBtn = ({ children, variant = "secondary", onClick, style, fullWidth = false }) => {
  const styles = {
    primary: {
      background: "var(--accent)",
      color: "#fff",
      border: "1px solid color-mix(in srgb, var(--accent) 60%, transparent)",
      boxShadow: "0 6px 18px -6px color-mix(in srgb, var(--accent) 60%, transparent)",
    },
    secondary: {
      background: "var(--bg-surface)",
      color: "var(--fg-primary)",
      border: "1px solid var(--border)",
    },
    destructive: {
      background: "#FF453A",
      color: "#fff",
      border: "1px solid #FF453A",
      boxShadow: "0 6px 18px -6px rgba(255,69,58,0.5)",
    },
    ghost: {
      background: "transparent",
      color: "var(--fg-secondary)",
      border: "1px solid transparent",
    },
  }[variant];
  return (
    <button onClick={onClick} style={{
      height: 36, padding: "0 18px",
      borderRadius: 8,
      fontSize: 12, fontWeight: 700,
      cursor: "pointer",
      fontFamily: "inherit",
      transition: "filter .15s",
      flexShrink: 0,
      ...(fullWidth ? { width: "100%" } : {}),
      ...styles,
      ...(style || {}),
    }}
    onMouseEnter={e => e.currentTarget.style.filter = "brightness(1.1)"}
    onMouseLeave={e => e.currentTarget.style.filter = "none"}
    >
      {children}
    </button>
  );
};

const DLGFooter = ({ children, justify = "flex-end" }) => (
  <div style={{
    padding: "16px 24px",
    background: "var(--bg-surface-2)",
    borderTop: "1px solid var(--border-subtle)",
    display: "flex", justifyContent: justify, gap: 10,
  }}>
    {children}
  </div>
);

const DLGBody = ({ children, style }) => (
  <div style={{ padding: "24px 24px 20px", flex: 1, ...(style || {}) }}>{children}</div>
);

/* ============================================================
 * 1. アップデートのお知らせ
 * ============================================================ */
const DlgUpdateAvailable = () => (
  <DLGFrame title="アップデートのお知らせ" width={460}>
    <DLGBody>
      <div style={{ display: "flex", gap: 18 }}>
        <DLGIcon kind="update"/>
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: 16, fontWeight: 800, margin: "2px 0 4px", letterSpacing: "-0.01em" }}>
            新しいバージョンが利用可能です
          </h2>
          <div style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.6 }}>
            最新バージョンへの更新を行いますか？<br/>
            ダウンロード後、インストーラーが自動実行されアプリが再起動します。
          </div>
          <div style={{
            marginTop: 14, padding: "12px 14px",
            borderRadius: 8,
            background: "var(--bg-surface-2)",
            border: "1px solid var(--border-subtle)",
            display: "flex", justifyContent: "space-between", alignItems: "center",
            fontSize: 12,
          }}>
            <div>
              <div style={{ color: "var(--fg-tertiary)", fontSize: 10, fontWeight: 700, letterSpacing: "0.06em" }}>現在</div>
              <div style={{ fontFamily: "var(--font-mono)", color: "var(--fg-secondary)", fontWeight: 700 }}>v3.4.2</div>
            </div>
            <div style={{ color: "var(--fg-tertiary)", fontSize: 18 }}>→</div>
            <div style={{ textAlign: "right" }}>
              <div style={{ color: "var(--accent)", fontSize: 10, fontWeight: 700, letterSpacing: "0.06em" }}>NEW</div>
              <div style={{ fontFamily: "var(--font-mono)", color: "var(--accent)", fontWeight: 800 }}>v3.5.0</div>
            </div>
          </div>
        </div>
      </div>
    </DLGBody>
    <DLGFooter>
      <DLGBtn variant="secondary">後で</DLGBtn>
      <DLGBtn variant="primary">今すぐ更新</DLGBtn>
    </DLGFooter>
  </DLGFrame>
);

/* ============================================================
 * 2. アップデートをダウンロード中
 * ============================================================ */
const DlgUpdateProgress = () => {
  const pct = 47;
  const downloaded = 12.8;
  const total = 27.3;
  return (
    <DLGFrame title="アップデートをダウンロード中" width={420}>
      <DLGBody style={{ paddingBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 18 }}>
          <div style={{
            width: 40, height: 40, borderRadius: 999,
            border: "3px solid var(--border-subtle)",
            borderTopColor: "var(--accent)",
            animation: "lw-spin 1s linear infinite",
            flexShrink: 0,
          }}/>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 2 }}>v3.5.0 をダウンロード中</div>
            <div style={{ fontSize: 11, color: "var(--fg-tertiary)", fontFamily: "var(--font-mono)" }}>
              {downloaded.toFixed(1)} MB / {total.toFixed(1)} MB
            </div>
          </div>
          <div style={{ fontSize: 18, fontWeight: 800, fontFamily: "var(--font-mono)", color: "var(--accent)" }}>
            {pct}%
          </div>
        </div>
        {/* progress bar */}
        <div style={{
          height: 6, borderRadius: 999,
          background: "var(--bg-surface-2)",
          border: "1px solid var(--border-subtle)",
          overflow: "hidden",
          position: "relative",
        }}>
          <div style={{
            position: "absolute", inset: 0,
            width: `${pct}%`,
            background: "linear-gradient(90deg, var(--accent), #FF9F0A)",
            borderRadius: 999,
            transition: "width .3s",
          }}/>
        </div>
        <div style={{ marginTop: 12, fontSize: 10, color: "var(--fg-tertiary)", textAlign: "center", lineHeight: 1.5 }}>
          ダウンロード完了後、自動的にインストーラーが起動します。<br/>
          ネットワーク接続を維持してください。
        </div>
      </DLGBody>
    </DLGFrame>
  );
};

/* ============================================================
 * 3. アップデート準備完了
 * ============================================================ */
const DlgUpdateReady = () => (
  <DLGFrame title="アップデート準備完了" width={460}>
    <DLGBody>
      <div style={{ display: "flex", gap: 18 }}>
        <DLGIcon kind="success"/>
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: 16, fontWeight: 800, margin: "2px 0 4px" }}>
            ダウンロードが完了しました
          </h2>
          <div style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.6 }}>
            インストーラーを起動します。<br/>
            アプリは自動的に再起動されます。<br/><br/>
            <span style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>
              編集中のメモがある場合は事前に保存してください。
            </span>
          </div>
        </div>
      </div>
    </DLGBody>
    <DLGFooter justify="flex-end">
      <DLGBtn variant="primary">OK · インストールを開始</DLGBtn>
    </DLGFooter>
  </DLGFrame>
);

/* ============================================================
 * 4. ダウンロードエラー
 * ============================================================ */
const DlgDownloadError = () => (
  <DLGFrame title="ダウンロードエラー" width={460}>
    <DLGBody>
      <div style={{ display: "flex", gap: 18 }}>
        <DLGIcon kind="error"/>
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: 16, fontWeight: 800, margin: "2px 0 4px", color: "#FF453A" }}>
            ダウンロードに失敗しました
          </h2>
          <div style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.6 }}>
            アップデートのダウンロード中にエラーが発生しました。
          </div>
          <div style={{
            marginTop: 12, padding: "10px 12px",
            borderRadius: 6,
            background: "var(--bg-surface-2)",
            border: "1px solid var(--border-subtle)",
            fontFamily: "var(--font-mono)", fontSize: 11,
            color: "#FF8A80",
            lineHeight: 1.5,
          }}>
            通信エラー: HTTPSConnectionPool(host='api.github.com', port=443):<br/>
            Read timed out. (read timeout=120)
          </div>
          <div style={{ marginTop: 10, fontSize: 11, color: "var(--fg-tertiary)" }}>
            ネットワーク接続を確認して再度お試しください。
          </div>
        </div>
      </div>
    </DLGBody>
    <DLGFooter>
      <DLGBtn variant="secondary">閉じる</DLGBtn>
      <DLGBtn variant="primary">再試行</DLGBtn>
    </DLGFooter>
  </DLGFrame>
);

/* ============================================================
 * 5. 終了の確認 (3 버튼)
 * ============================================================ */
const DlgQuitConfirm = () => (
  <DLGFrame title="終了の確認" width={480}>
    <DLGBody>
      <div style={{ display: "flex", gap: 18 }}>
        <DLGIcon kind="question"/>
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: 16, fontWeight: 800, margin: "2px 0 4px" }}>
            アプリケーションを完全に終了しますか？
          </h2>
          <div style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.6 }}>
            それともトレイ（バックグラウンド）に最小化しますか？
          </div>
          <div style={{
            marginTop: 14, padding: "10px 12px",
            borderRadius: 8,
            background: "color-mix(in srgb, #FF7A45 8%, transparent)",
            border: "1px solid color-mix(in srgb, #FF7A45 20%, transparent)",
            fontSize: 11, color: "var(--fg-secondary)",
            display: "flex", gap: 8, alignItems: "flex-start",
          }}>
            <span style={{ color: "var(--accent)", fontSize: 14, lineHeight: 1 }}>ⓘ</span>
            <div>
              トレイに最小化すれば、バックグラウンドで自動更新・通知を継続できます。
            </div>
          </div>
        </div>
      </div>
    </DLGBody>
    <DLGFooter>
      <DLGBtn variant="ghost">キャンセル</DLGBtn>
      <div style={{ flex: 1 }}/>
      <DLGBtn variant="secondary">トレイに最小化</DLGBtn>
      <DLGBtn variant="destructive">完全に終了</DLGBtn>
    </DLGFooter>
  </DLGFrame>
);

/* ============================================================
 * 6. ログアウト確認
 * ============================================================ */
const DlgLogoutConfirm = () => (
  <DLGFrame title="ログアウト" width={420}>
    <DLGBody>
      <div style={{ display: "flex", gap: 18 }}>
        <DLGIcon kind="warning"/>
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: 16, fontWeight: 800, margin: "2px 0 4px" }}>
            ログアウトしますか？
          </h2>
          <div style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.6 }}>
            Google アカウントの認証は解除されます。<br/>
            次回ログイン時に再度サインインが必要です。
          </div>
          <div style={{
            marginTop: 12,
            display: "flex", alignItems: "center", gap: 8,
            padding: "8px 10px",
            borderRadius: 6,
            background: "var(--bg-surface-2)",
            border: "1px solid var(--border-subtle)",
          }}>
            <div style={{ width: 22, height: 22, borderRadius: 999, background: "var(--accent)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 800 }}>T</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 11, fontWeight: 700, lineHeight: 1.2 }}>田中 太郎</div>
              <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--fg-tertiary)", lineHeight: 1.2 }}>tanaka@shirokumapower.com</div>
            </div>
          </div>
        </div>
      </div>
    </DLGBody>
    <DLGFooter>
      <DLGBtn variant="secondary">キャンセル</DLGBtn>
      <DLGBtn variant="destructive">ログアウト</DLGBtn>
    </DLGFooter>
  </DLGFrame>
);

/* ============================================================
 * 7. 起動エラー (Critical)
 * ============================================================ */
const DlgStartupError = () => (
  <DLGFrame title="起動エラー" width={520}>
    <DLGBody>
      <div style={{ display: "flex", gap: 18 }}>
        <DLGIcon kind="error"/>
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: 16, fontWeight: 800, margin: "2px 0 4px", color: "#FF453A" }}>
            メインウィンドウの起動に失敗しました
          </h2>
          <div style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.6 }}>
            アプリの初期化中にエラーが発生しました。<br/>
            ログファイルを確認してください。
          </div>
          <div style={{
            marginTop: 12, padding: "12px 14px",
            borderRadius: 6,
            background: "#1a0a0a",
            border: "1px solid color-mix(in srgb, #FF453A 30%, transparent)",
            fontFamily: "var(--font-mono)", fontSize: 11,
            color: "#FF8A80",
            lineHeight: 1.6,
          }}>
            <div style={{ fontWeight: 800, marginBottom: 4 }}>ConnectionError:</div>
            <div>HTTPSConnectionPool(host='accounts.google.com', port=443):</div>
            <div>Max retries exceeded with url: /o/oauth2/token</div>
          </div>
          <div style={{ marginTop: 12, padding: "8px 12px", borderRadius: 6, background: "var(--bg-surface-2)", fontSize: 10, color: "var(--fg-tertiary)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontFamily: "var(--font-mono)" }}>%APPDATA%/LEE/lee.log</span>
            <button style={{ background: "transparent", border: 0, color: "var(--accent)", fontSize: 10, fontWeight: 700, cursor: "pointer" }}>ログを開く</button>
          </div>
        </div>
      </div>
    </DLGBody>
    <DLGFooter>
      <DLGBtn variant="secondary">ログを開く</DLGBtn>
      <DLGBtn variant="primary">OK</DLGBtn>
    </DLGFooter>
  </DLGFrame>
);

/* ============================================================
 * 8. 共通 confirm (削除の確認 등)
 * ============================================================ */
const DlgConfirmDelete = () => (
  <DLGFrame title="削除の確認" width={420}>
    <DLGBody>
      <div style={{ display: "flex", gap: 18 }}>
        <DLGIcon kind="warning"/>
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: 16, fontWeight: 800, margin: "2px 0 4px" }}>
            削除してもよろしいですか？
          </h2>
          <div style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.6 }}>
            「<span style={{ fontWeight: 700, color: "var(--fg-primary)" }}>業務マニュアル_v2.pdf</span>」を削除します。<br/>
            この操作は取り消せません。
          </div>
        </div>
      </div>
    </DLGBody>
    <DLGFooter>
      <DLGBtn variant="secondary">キャンセル</DLGBtn>
      <DLGBtn variant="destructive">削除</DLGBtn>
    </DLGFooter>
  </DLGFrame>
);

/* ============================================================
 * 9. アクセス申請 (login_window.py 의 _AccessRequestDialog)
 * ============================================================ */
const DlgAccessRequest = () => {
  const [status, setStatus] = dlg_S(""); // ""(idle) | "sending" | "success" | "error"
  return (
    <DLGFrame title="アクセスを申請する" width={440} icon={<span style={{ fontSize: 12 }}>📝</span>}>
      <DLGBody style={{ paddingTop: 20 }}>
        <div style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.6, marginBottom: 14 }}>
          管理者 (<span style={{ fontFamily: "var(--font-mono)", color: "var(--accent)", fontWeight: 700 }}>jw.lee@shirokumapower.com</span>) へ<br/>アクセス申請メールを送信します。
        </div>

        <label style={{ fontSize: 11, fontWeight: 700, color: "var(--fg-secondary)", display: "block", marginBottom: 6 }}>申請メールアドレス</label>
        <input defaultValue="tanaka@example.com" style={{
          width: "100%", height: 36,
          padding: "0 12px",
          borderRadius: 8,
          border: "1px solid var(--border)",
          background: "var(--bg-input)",
          color: "var(--fg-primary)",
          fontSize: 12, fontFamily: "var(--font-mono)",
          fontWeight: 600,
          outline: "none",
          boxSizing: "border-box",
        }}/>

        <label style={{ fontSize: 11, fontWeight: 700, color: "var(--fg-secondary)", display: "block", marginTop: 12, marginBottom: 6 }}>メッセージ <span style={{ color: "var(--fg-tertiary)", fontWeight: 500 }}>(任意)</span></label>
        <textarea defaultValue="新規入社しました。アクセス権を発行してください。" style={{
          width: "100%", height: 64,
          padding: "8px 12px",
          borderRadius: 8,
          border: "1px solid var(--border)",
          background: "var(--bg-input)",
          color: "var(--fg-primary)",
          fontSize: 12,
          outline: "none",
          resize: "none",
          boxSizing: "border-box",
          fontFamily: "inherit",
          lineHeight: 1.5,
        }}/>

        {status === "success" && (
          <div style={{
            marginTop: 12, padding: "8px 12px",
            borderRadius: 6,
            background: "color-mix(in srgb, #30D158 12%, transparent)",
            border: "1px solid color-mix(in srgb, #30D158 30%, transparent)",
            fontSize: 12, color: "#30D158",
            display: "flex", gap: 8, alignItems: "center",
          }}>
            <span>✅</span> 申請メールを送信しました。管理者の承認をお待ちください。
          </div>
        )}
        {status === "error" && (
          <div style={{
            marginTop: 12, padding: "8px 12px",
            borderRadius: 6,
            background: "color-mix(in srgb, #FF453A 12%, transparent)",
            border: "1px solid color-mix(in srgb, #FF453A 30%, transparent)",
            fontSize: 12, color: "#FF453A",
            display: "flex", gap: 8, alignItems: "center",
          }}>
            <span>❌</span> 送信失敗: SMTP authentication failed.
          </div>
        )}
      </DLGBody>
      <DLGFooter>
        {/* dummy state cycle (mockup demo) */}
        <DLGBtn variant="ghost" onClick={() => setStatus(status === "" ? "success" : status === "success" ? "error" : "")}>
          {status === "" ? "(プレビュー)" : status === "success" ? "→ エラー状態" : "→ 初期状態"}
        </DLGBtn>
        <div style={{ flex: 1 }}/>
        <DLGBtn variant="secondary">キャンセル</DLGBtn>
        <DLGBtn variant="primary">メールを送信</DLGBtn>
      </DLGFooter>
    </DLGFrame>
  );
};

/* ============================================================
 * 10. カテゴリ管理 (manual.py)
 * ============================================================ */
const DlgCategoryManager = () => {
  const [items, setItems] = dlg_S([
    "市場関連業務",
    "発電所運転",
    "需給予測",
    "メンテナンス",
    "システム運用",
    "未分類",
  ]);
  const [sel, setSel] = dlg_S(0);
  return (
    <DLGFrame title="カテゴリ管理" width={500} height={420}>
      <div style={{ flex: 1, display: "flex", padding: 24, gap: 16, minHeight: 0 }}>
        {/* 좌: 리스트 */}
        <div style={{
          flex: 1,
          background: "var(--bg-surface-2)",
          border: "1px solid var(--border-subtle)",
          borderRadius: 10,
          overflow: "hidden",
          display: "flex", flexDirection: "column",
        }}>
          <div style={{
            padding: "10px 14px", fontSize: 10, fontWeight: 700, letterSpacing: "0.08em",
            color: "var(--fg-tertiary)",
            borderBottom: "1px solid var(--border-subtle)",
          }}>
            カテゴリ ({items.length})
          </div>
          <div style={{ flex: 1, overflowY: "auto" }}>
            {items.map((it, i) => (
              <div key={i} onClick={() => setSel(i)} style={{
                padding: "10px 14px",
                fontSize: 12, fontWeight: sel === i ? 700 : 500,
                background: sel === i ? "color-mix(in srgb, var(--accent) 12%, transparent)" : "transparent",
                color: sel === i ? "var(--accent)" : "var(--fg-primary)",
                borderLeft: sel === i ? "3px solid var(--accent)" : "3px solid transparent",
                cursor: "pointer",
                display: "flex", alignItems: "center", gap: 8,
              }}>
                <span style={{ fontSize: 10, color: "var(--fg-tertiary)", fontFamily: "var(--font-mono)", width: 18 }}>{String(i+1).padStart(2,"0")}</span>
                {it}
                {it === "未分類" && <span style={{ marginLeft: "auto", fontSize: 9, color: "var(--fg-tertiary)", fontWeight: 600 }}>SYSTEM</span>}
              </div>
            ))}
          </div>
        </div>
        {/* 우: 액션 */}
        <div style={{ width: 140, display: "flex", flexDirection: "column", gap: 8 }}>
          <DLGBtn variant="primary" fullWidth>+ 新規</DLGBtn>
          <DLGBtn variant="secondary" fullWidth>名前変更</DLGBtn>
          <DLGBtn variant="secondary" fullWidth>↑ 上へ</DLGBtn>
          <DLGBtn variant="secondary" fullWidth>↓ 下へ</DLGBtn>
          <div style={{ flex: 1 }}/>
          <DLGBtn variant="destructive" fullWidth>削除</DLGBtn>
        </div>
      </div>
      <DLGFooter>
        <DLGBtn variant="secondary">キャンセル</DLGBtn>
        <DLGBtn variant="primary">保存</DLGBtn>
      </DLGFooter>
    </DLGFrame>
  );
};

/* ============================================================
 * 11. 画像の簡単な編集 (赤ペン) — manual.py
 * ============================================================ */
const DlgImageEdit = () => {
  const [tool, setTool] = dlg_S("pen");
  const [color, setColor] = dlg_S("#FF453A");
  const tools = [
    { id: "pen",   label: "ペン",       glyph: "✎" },
    { id: "rect",  label: "□",        glyph: "□" },
    { id: "arrow", label: "→",        glyph: "→" },
    { id: "text",  label: "T",         glyph: "T" },
    { id: "erase", label: "消去",       glyph: "⌫" },
  ];
  const colors = ["#FF453A", "#FF9F0A", "#FFD60A", "#30D158", "#0A84FF", "#000000"];
  return (
    <DLGFrame title="画像の簡単な編集 (赤ペン)" width={680} height={520}>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: "16px 20px 0", minHeight: 0 }}>
        {/* 툴바 */}
        <div style={{
          display: "flex", gap: 6, alignItems: "center",
          padding: "8px 10px",
          background: "var(--bg-surface-2)",
          border: "1px solid var(--border-subtle)",
          borderRadius: 8,
          marginBottom: 12,
        }}>
          {tools.map(t => (
            <button key={t.id} onClick={() => setTool(t.id)} style={{
              width: 36, height: 32, borderRadius: 6,
              background: tool === t.id ? "var(--accent)" : "transparent",
              color: tool === t.id ? "#fff" : "var(--fg-primary)",
              border: "1px solid " + (tool === t.id ? "var(--accent)" : "transparent"),
              fontSize: 14, fontWeight: 700, cursor: "pointer", fontFamily: "inherit",
            }} title={t.label}>{t.glyph}</button>
          ))}
          <div style={{ width: 1, height: 22, background: "var(--border-subtle)", margin: "0 6px" }}/>
          {colors.map(c => (
            <button key={c} onClick={() => setColor(c)} style={{
              width: 22, height: 22, borderRadius: 999,
              background: c,
              border: c === color ? "2px solid var(--fg-primary)" : "1px solid var(--border-subtle)",
              cursor: "pointer",
              outline: c === color ? "1px solid var(--bg-surface)" : "none",
              outlineOffset: c === color ? -3 : 0,
            }}/>
          ))}
          <div style={{ width: 1, height: 22, background: "var(--border-subtle)", margin: "0 6px" }}/>
          <span style={{ fontSize: 11, color: "var(--fg-secondary)", fontWeight: 600 }}>太さ</span>
          <input type="range" min="1" max="10" defaultValue="3" style={{ width: 80 }}/>
          <div style={{ flex: 1 }}/>
          <button style={{ background: "transparent", border: 0, color: "var(--fg-secondary)", fontSize: 12, fontWeight: 700, cursor: "pointer", padding: "6px 10px", fontFamily: "inherit" }}>↶ 元に戻す</button>
          <button style={{ background: "transparent", border: 0, color: "var(--fg-secondary)", fontSize: 12, fontWeight: 700, cursor: "pointer", padding: "6px 10px", fontFamily: "inherit" }}>↷ やり直し</button>
        </div>
        {/* 캔버스 미리보기 */}
        <div style={{
          flex: 1,
          background: "var(--bg-surface-2)",
          border: "1px dashed var(--border)",
          borderRadius: 10,
          display: "flex", alignItems: "center", justifyContent: "center",
          position: "relative", overflow: "hidden",
        }}>
          {/* 모의 스크린샷 */}
          <div style={{
            width: "85%", height: "85%",
            background: "linear-gradient(135deg, #2a3441 0%, #1a2028 100%)",
            borderRadius: 6,
            position: "relative",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 13, color: "#ffffff44", fontFamily: "var(--font-mono)",
          }}>
            screenshot.png — 1280 × 720
            {/* 빨간펜 데모 마크업 */}
            <svg style={{ position: "absolute", inset: 0, pointerEvents: "none" }} width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none">
              <circle cx="30" cy="40" r="8" stroke="#FF453A" strokeWidth="0.6" fill="none"/>
              <path d="M 38 40 L 55 35" stroke="#FF453A" strokeWidth="0.6" fill="none" markerEnd="url(#dlge-arrow)"/>
              <text x="58" y="36" fill="#FF453A" fontSize="3" fontWeight="700" fontFamily="sans-serif">ここを修正</text>
              <defs>
                <marker id="dlge-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                  <path d="M0,0 L6,3 L0,6 z" fill="#FF453A"/>
                </marker>
              </defs>
            </svg>
          </div>
        </div>
      </div>
      <DLGFooter>
        <span style={{ fontSize: 10, color: "var(--fg-tertiary)", alignSelf: "center", marginRight: "auto" }}>マニュアルに挿入される画像</span>
        <DLGBtn variant="secondary">キャンセル</DLGBtn>
        <DLGBtn variant="primary">適用して挿入</DLGBtn>
      </DLGFooter>
    </DLGFrame>
  );
};

/* ============================================================
 * 12. 画像プレビュー (manual.py)
 * ============================================================ */
const DlgImagePreview = () => (
  <DLGFrame title="画像プレビュー" width={620} height={460}>
    <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: 20, minHeight: 0 }}>
      <div style={{
        flex: 1,
        background: "var(--bg-surface-2)",
        border: "1px solid var(--border-subtle)",
        borderRadius: 10,
        display: "flex", alignItems: "center", justifyContent: "center",
        position: "relative", overflow: "hidden",
      }}>
        <div style={{
          width: "75%", height: "85%",
          background: "linear-gradient(135deg, #1a2028 0%, #0f1419 100%)",
          borderRadius: 6,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 12, color: "#ffffff55", fontFamily: "var(--font-mono)",
          flexDirection: "column", gap: 8,
        }}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#ffffff44" strokeWidth="1.5">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <circle cx="9" cy="9" r="2"/>
            <path d="M21 15l-5-5L5 21"/>
          </svg>
          screenshot_2024-12-15.png
        </div>
        {/* 줌 컨트롤 */}
        <div style={{
          position: "absolute",
          bottom: 12, right: 12,
          display: "flex", gap: 4,
          background: "rgba(0,0,0,0.6)", backdropFilter: "blur(8px)",
          padding: 4, borderRadius: 8,
          border: "1px solid rgba(255,255,255,0.1)",
        }}>
          <button style={{ width: 28, height: 28, borderRadius: 5, border: 0, background: "transparent", color: "#fff", fontSize: 16, cursor: "pointer", fontFamily: "inherit" }}>−</button>
          <span style={{ alignSelf: "center", fontSize: 11, color: "#fff", fontWeight: 700, padding: "0 6px", fontFamily: "var(--font-mono)" }}>100%</span>
          <button style={{ width: 28, height: 28, borderRadius: 5, border: 0, background: "transparent", color: "#fff", fontSize: 16, cursor: "pointer", fontFamily: "inherit" }}>+</button>
          <div style={{ width: 1, background: "rgba(255,255,255,0.15)", margin: "4px 2px" }}/>
          <button style={{ width: 28, height: 28, borderRadius: 5, border: 0, background: "transparent", color: "#fff", fontSize: 11, fontWeight: 700, cursor: "pointer", fontFamily: "inherit" }}>1:1</button>
        </div>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 10, fontSize: 10, color: "var(--fg-tertiary)", fontFamily: "var(--font-mono)" }}>
        <span>1920 × 1080 · 248 KB · PNG</span>
        <span>2024-12-15 14:32</span>
      </div>
    </div>
    <DLGFooter>
      <DLGBtn variant="secondary">↓ 保存</DLGBtn>
      <DLGBtn variant="secondary">クリップボードにコピー</DLGBtn>
      <div style={{ flex: 1 }}/>
      <DLGBtn variant="primary">閉じる</DLGBtn>
    </DLGFooter>
  </DLGFrame>
);

/* ============================================================
 * 13. 通用 information / warning toast-like
 * ============================================================ */
const DlgInfoNotice = () => (
  <DLGFrame title="通知" width={400}>
    <DLGBody>
      <div style={{ display: "flex", gap: 16 }}>
        <DLGIcon kind="info" size={48}/>
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: 14, fontWeight: 800, margin: "4px 0 4px" }}>
            データを保存しました
          </h2>
          <div style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.6 }}>
            予備率データを <span style={{ fontFamily: "var(--font-mono)", color: "var(--fg-primary)", fontWeight: 700 }}>reserve_2024-12-15.csv</span> として保存しました。
          </div>
        </div>
      </div>
    </DLGBody>
    <DLGFooter>
      <DLGBtn variant="secondary">フォルダを開く</DLGBtn>
      <DLGBtn variant="primary">OK</DLGBtn>
    </DLGFooter>
  </DLGFrame>
);

/* expose */
Object.assign(window, {
  DlgUpdateAvailable, DlgUpdateProgress, DlgUpdateReady, DlgDownloadError,
  DlgQuitConfirm, DlgLogoutConfirm, DlgStartupError,
  DlgConfirmDelete, DlgAccessRequest,
  DlgCategoryManager, DlgImageEdit, DlgImagePreview,
  DlgInfoNotice,
});
