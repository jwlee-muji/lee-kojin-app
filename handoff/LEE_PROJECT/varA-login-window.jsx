/* ============================================================
 * LEE LoginWindow — login_window.py 의 디자인 모킹업
 * Pages: LOGIN (0) / NOT_REGISTERED (1) / LOADING (2)
 *  - Window: 480 × 580
 *  - 3 안 (A/B/C): 톤 다른 레이아웃 변형
 * ============================================================ */
const { useState: lw_S } = React;

/* ---------- Common building blocks ---------- */
const LWFrame = ({ children, theme = "light", style }) => (
  <div data-theme={theme} style={{
    width: 480, height: 580,
    background: "var(--bg-surface)",
    color: "var(--fg-primary)",
    border: "1px solid var(--border-subtle)",
    borderRadius: 14,
    fontFamily: "var(--font-sans)",
    overflow: "hidden",
    position: "relative",
    boxShadow: "var(--shadow-md)",
    display: "flex", flexDirection: "column",
    ...(style || {}),
  }}>
    {/* macOS 風 타이틀바 */}
    <div style={{
      height: 28,
      background: "var(--bg-surface-2)",
      borderBottom: "1px solid var(--border-subtle)",
      display: "flex", alignItems: "center", padding: "0 12px",
      gap: 6,
      flexShrink: 0,
    }}>
      <span style={{ width: 11, height: 11, borderRadius: 999, background: "#FF5F57" }}/>
      <span style={{ width: 11, height: 11, borderRadius: 999, background: "#FEBC2E" }}/>
      <span style={{ width: 11, height: 11, borderRadius: 999, background: "#28C840" }}/>
      <div style={{ flex: 1, textAlign: "center", fontSize: 11, color: "var(--fg-tertiary)", fontWeight: 600 }}>
        LEE 電力モニター  v3.4.2
      </div>
    </div>
    {children}
  </div>
);

/* LEE 앱 아이콘 (orange tile + bolt) */
const LWIcon = ({ size = 88 }) => (
  <div style={{
    width: size, height: size, borderRadius: size * 0.27,
    background: "linear-gradient(135deg, #FF7A45 0%, #FF9F0A 100%)",
    display: "inline-flex", alignItems: "center", justifyContent: "center",
    boxShadow: "0 12px 32px -8px #FF7A4566, 0 0 0 1px #ffffff10 inset",
    color: "#fff",
  }}>
    <svg width={size * 0.44} height={size * 0.44} viewBox="0 0 24 24" fill="currentColor">
      <path d="M13 2L4.5 13.5h6L9 22l9-12h-6.5L13 2z"/>
    </svg>
  </div>
);

const LWGoogleBtn = ({ onClick, label = "Google アカウントでサインイン" }) => (
  <button onClick={onClick} style={{
    width: "100%", height: 48,
    border: "1px solid var(--border)",
    borderRadius: 10,
    background: "var(--bg-surface)",
    color: "var(--fg-primary)",
    fontSize: 14, fontWeight: 700,
    cursor: "pointer",
    display: "inline-flex", alignItems: "center", justifyContent: "center",
    gap: 12,
    fontFamily: "inherit",
    transition: "background .12s, border-color .12s",
  }}
  onMouseEnter={e => { e.currentTarget.style.background = "var(--bg-surface-2)"; e.currentTarget.style.borderColor = "var(--accent)"; }}
  onMouseLeave={e => { e.currentTarget.style.background = "var(--bg-surface)"; e.currentTarget.style.borderColor = "var(--border)"; }}
  >
    <svg width="18" height="18" viewBox="0 0 24 24">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
    </svg>
    {label}
  </button>
);

/* ============================================================
 * 1) Variation A — クラシック / 中央寄せ (login_window.py 거의 1:1)
 * ============================================================ */
const LoginWindowA = () => {
  const [page, setPage] = lw_S(0);

  return (
    <LWFrame>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: "0 56px 40px" }}>
        {page === 0 && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 0 }}>
            <div style={{ flex: 2 }}/>
            <LWIcon/>
            <div style={{ height: 18 }}/>
            <h1 style={{
              fontSize: 24, fontWeight: 800, margin: 0, letterSpacing: "-0.02em",
              color: "var(--fg-primary)",
            }}>LEE 電力モニター</h1>
            <div style={{ height: 6 }}/>
            <div style={{ fontSize: 12, color: "var(--fg-secondary)", fontWeight: 500 }}>承認済みアカウントでサインイン</div>
            <div style={{ height: 32 }}/>
            <div style={{ width: "100%", height: 1, background: "var(--border-subtle)" }}/>
            <div style={{ height: 28 }}/>
            <div style={{ width: "100%" }}>
              <LWGoogleBtn onClick={() => setPage(2)}/>
            </div>
            <div style={{ height: 28 }}/>
            <div style={{ width: "100%", display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ flex: 1, height: 1, background: "var(--border-subtle)" }}/>
              <span style={{ fontSize: 11, color: "var(--fg-tertiary)", fontWeight: 600 }}>または</span>
              <div style={{ flex: 1, height: 1, background: "var(--border-subtle)" }}/>
            </div>
            <div style={{ height: 16 }}/>
            <button onClick={() => setPage(1)} style={{
              border: 0, background: "transparent",
              fontSize: 12, fontWeight: 700,
              color: "var(--accent)",
              cursor: "pointer",
              fontFamily: "inherit",
            }}>アクセスを申請する  →</button>
            <div style={{ flex: 3 }}/>
          </div>
        )}

        {page === 1 && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
            <div style={{ flex: 2 }}/>
            <div style={{
              width: 76, height: 76, borderRadius: 22,
              background: "color-mix(in srgb, #FF9F0A 16%, transparent)",
              color: "#FF9F0A",
              display: "inline-flex", alignItems: "center", justifyContent: "center",
            }}>
              <svg width="38" height="38" viewBox="0 0 24 24" fill="none">
                <path d="M12 4l9 16H3z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/>
                <path d="M12 11v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                <circle cx="12" cy="17.5" r="1" fill="currentColor"/>
              </svg>
            </div>
            <div style={{ height: 20 }}/>
            <h1 style={{ fontSize: 22, fontWeight: 800, margin: 0, color: "var(--fg-primary)" }}>登録されていません</h1>
            <div style={{ height: 8 }}/>
            <div style={{ fontSize: 12, color: "var(--fg-secondary)", fontWeight: 600 }}>tanaka@example.com</div>
            <div style={{ height: 16 }}/>
            <div style={{ fontSize: 12, color: "var(--fg-tertiary)", textAlign: "center", lineHeight: 1.7 }}>
              このアカウントはアクセス権がありません。<br/>
              管理者にアクセスを申請してください。
            </div>
            <div style={{ height: 32 }}/>
            <div style={{ width: "100%", height: 1, background: "var(--border-subtle)" }}/>
            <div style={{ height: 24 }}/>
            <div style={{ display: "flex", gap: 12, width: "100%" }}>
              <button onClick={() => setPage(0)} style={{
                flex: 1, height: 40, borderRadius: 10,
                border: "1px solid var(--border)",
                background: "var(--bg-surface)",
                color: "var(--fg-primary)",
                fontSize: 13, fontWeight: 700, cursor: "pointer",
                fontFamily: "inherit",
              }}>← 戻る</button>
              <button style={{
                flex: 1, height: 40, borderRadius: 10,
                border: "none",
                background: "var(--accent)",
                color: "var(--bg-base)",
                fontSize: 13, fontWeight: 800, cursor: "pointer",
                fontFamily: "inherit",
              }}>アクセスを申請</button>
            </div>
            <div style={{ flex: 3 }}/>
          </div>
        )}

        {page === 2 && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
            <div style={{
              width: 64, height: 64, borderRadius: 999,
              border: "3px solid var(--border-subtle)",
              borderTopColor: "var(--accent)",
              animation: "lw-spin 1s linear infinite",
            }}/>
            <div style={{ height: 20 }}/>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--fg-primary)" }}>認証中...</div>
            <div style={{ height: 10 }}/>
            <div style={{ fontSize: 12, color: "var(--fg-secondary)" }}>ブラウザでサインインを完了してください</div>
            <div style={{ height: 4 }}/>
            <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>(2 分後に自動キャンセル)</div>
            <div style={{ height: 28 }}/>
            <button onClick={() => setPage(0)} style={{
              height: 34, padding: "0 24px", borderRadius: 8,
              border: "1px solid var(--border)",
              background: "var(--bg-surface)",
              color: "var(--fg-primary)",
              fontSize: 12, fontWeight: 700, cursor: "pointer",
              fontFamily: "inherit",
            }}>キャンセル</button>
          </div>
        )}
      </div>

      {/* page nav (mockup전용) */}
      <LWPageDots page={page} setPage={setPage}/>
    </LWFrame>
  );
};

/* ============================================================
 * 2) Variation B — Split Hero / 좌측 브랜드 패널 + 우측 폼
 *    (480 × 580 같은 사이즈인데 좌측에 컬러 hero 영역)
 * ============================================================ */
const LoginWindowB = () => {
  const [page, setPage] = lw_S(0);
  return (
    <LWFrame>
      <div style={{ flex: 1, display: "flex", flexDirection: "row" }}>
        {/* 좌측 브랜드 패널 */}
        <div style={{
          width: 180,
          background: "linear-gradient(160deg, #FF7A45 0%, #FF5F57 100%)",
          color: "#fff",
          padding: "32px 22px 24px",
          display: "flex", flexDirection: "column",
          position: "relative",
          overflow: "hidden",
        }}>
          {/* 장식 */}
          <div style={{ position: "absolute", inset: 0, opacity: 0.12, pointerEvents: "none" }}>
            <svg width="100%" height="100%" viewBox="0 0 180 552" preserveAspectRatio="none">
              <circle cx="160" cy="50" r="60" fill="#fff"/>
              <circle cx="20" cy="500" r="80" fill="#fff"/>
              <path d="M0 300 Q90 250 180 320" stroke="#fff" strokeWidth="2" fill="none"/>
            </svg>
          </div>
          <LWIcon size={56}/>
          <div style={{ height: 24 }}/>
          <div style={{ fontSize: 18, fontWeight: 800, lineHeight: 1.3, letterSpacing: "-0.01em", color: "#fff" }}>
            日本電力市場の<br/>すべてを一画面で
          </div>
          <div style={{ flex: 1 }}/>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 16 }}>
            {[
              ["JEPX スポット", "リアルタイム"],
              ["OCCTO 予備率", "10 エリア"],
              ["AI ブリーフィング", "毎朝 06:00"],
            ].map(([k, v]) => (
              <div key={k} style={{
                display: "flex", flexDirection: "column",
                fontSize: 11, lineHeight: 1.4,
              }}>
                <span style={{ fontWeight: 800, opacity: 0.95 }}>{k}</span>
                <span style={{ opacity: 0.7, fontSize: 10 }}>{v}</span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 18, fontSize: 9, opacity: 0.5, fontFamily: "var(--font-mono)" }}>v3.4.2</div>
        </div>

        {/* 우측 폼 */}
        <div style={{ flex: 1, padding: "36px 28px 32px", display: "flex", flexDirection: "column" }}>
          {page === 0 && (
            <>
              <div style={{ fontSize: 11, fontWeight: 700, color: "var(--accent)", letterSpacing: "0.1em" }}>WELCOME</div>
              <h1 style={{ fontSize: 22, fontWeight: 800, margin: "8px 0 6px", letterSpacing: "-0.02em" }}>サインイン</h1>
              <div style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.6 }}>
                承認済みアカウントで Google にサインインしてください。
              </div>
              <div style={{ flex: 1 }}/>

              <LWGoogleBtn onClick={() => setPage(2)} label="Google で続行"/>
              <div style={{ height: 12 }}/>
              <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--fg-tertiary)", fontSize: 11, fontWeight: 600 }}>
                <div style={{ flex: 1, height: 1, background: "var(--border-subtle)" }}/>
                <span>または</span>
                <div style={{ flex: 1, height: 1, background: "var(--border-subtle)" }}/>
              </div>
              <div style={{ height: 12 }}/>
              <button onClick={() => setPage(1)} style={{
                height: 40, borderRadius: 10,
                border: "1px dashed var(--border)",
                background: "transparent",
                color: "var(--fg-secondary)",
                fontSize: 12, fontWeight: 700, cursor: "pointer",
                fontFamily: "inherit",
              }}>アクセスを申請  →</button>

              <div style={{ height: 16 }}/>
              <div style={{ fontSize: 10, color: "var(--fg-tertiary)", lineHeight: 1.6 }}>
                サインインすることで <a href="#" style={{ color: "var(--accent)", textDecoration: "none" }}>利用規約</a> と <a href="#" style={{ color: "var(--accent)", textDecoration: "none" }}>プライバシーポリシー</a> に同意したものとみなされます。
              </div>
            </>
          )}

          {page === 1 && (
            <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
              <div style={{
                width: 56, height: 56, borderRadius: 16,
                background: "color-mix(in srgb, #FF9F0A 14%, transparent)",
                color: "#FF9F0A",
                display: "inline-flex", alignItems: "center", justifyContent: "center",
              }}>
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                  <path d="M12 4l9 16H3z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/>
                  <path d="M12 11v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  <circle cx="12" cy="17.5" r="1" fill="currentColor"/>
                </svg>
              </div>
              <div style={{ height: 16 }}/>
              <h1 style={{ fontSize: 20, fontWeight: 800, margin: 0, letterSpacing: "-0.02em" }}>登録されていません</h1>
              <div style={{ height: 6 }}/>
              <div style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--fg-secondary)", fontWeight: 700 }}>tanaka@example.com</div>
              <div style={{ height: 14 }}/>
              <div style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.7 }}>
                このアカウントはアクセス権がありません。管理者にアクセスを申請してください。
              </div>
              <div style={{ flex: 1 }}/>
              <div style={{ display: "flex", gap: 10 }}>
                <button onClick={() => setPage(0)} style={{
                  flex: 1, height: 40, borderRadius: 10,
                  border: "1px solid var(--border)",
                  background: "var(--bg-surface)",
                  color: "var(--fg-primary)",
                  fontSize: 12, fontWeight: 700, cursor: "pointer",
                  fontFamily: "inherit",
                }}>← 戻る</button>
                <button style={{
                  flex: 1.4, height: 40, borderRadius: 10,
                  border: "none",
                  background: "var(--accent)",
                  color: "#fff",
                  fontSize: 12, fontWeight: 800, cursor: "pointer",
                  fontFamily: "inherit",
                }}>アクセスを申請</button>
              </div>
            </div>
          )}

          {page === 2 && (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
              <div style={{
                width: 56, height: 56, borderRadius: 999,
                border: "3px solid var(--border-subtle)",
                borderTopColor: "var(--accent)",
                animation: "lw-spin 1s linear infinite",
              }}/>
              <div style={{ height: 16 }}/>
              <div style={{ fontSize: 13, fontWeight: 700 }}>認証中...</div>
              <div style={{ height: 8 }}/>
              <div style={{ fontSize: 11, color: "var(--fg-tertiary)", textAlign: "center", lineHeight: 1.6 }}>
                ブラウザでサインインを<br/>完了してください
              </div>
              <div style={{ height: 24 }}/>
              <button onClick={() => setPage(0)} style={{
                height: 32, padding: "0 18px", borderRadius: 8,
                border: "1px solid var(--border)",
                background: "transparent",
                color: "var(--fg-primary)",
                fontSize: 11, fontWeight: 700, cursor: "pointer",
                fontFamily: "inherit",
              }}>キャンセル</button>
            </div>
          )}
        </div>
      </div>
      <LWPageDots page={page} setPage={setPage}/>
    </LWFrame>
  );
};

/* ============================================================
 * 3) Variation C — Glass / 다크 + 그래픽 BG
 * ============================================================ */
const LoginWindowC = () => {
  const [page, setPage] = lw_S(0);
  return (
    <LWFrame theme="dark" style={{
      background: "radial-gradient(120% 90% at 0% 0%, #2a1410 0%, #0a0a0a 50%), #0a0a0a",
    }}>
      {/* 배경 그래픽 */}
      <div style={{ position: "absolute", inset: 0, pointerEvents: "none", overflow: "hidden" }}>
        <svg width="100%" height="100%" viewBox="0 0 480 580" preserveAspectRatio="none">
          <defs>
            <radialGradient id="lwc-glow" cx="80%" cy="20%" r="60%">
              <stop offset="0%" stopColor="#FF7A45" stopOpacity="0.4"/>
              <stop offset="100%" stopColor="#FF7A45" stopOpacity="0"/>
            </radialGradient>
            <radialGradient id="lwc-glow2" cx="20%" cy="100%" r="50%">
              <stop offset="0%" stopColor="#5B8DEF" stopOpacity="0.3"/>
              <stop offset="100%" stopColor="#5B8DEF" stopOpacity="0"/>
            </radialGradient>
          </defs>
          <rect width="480" height="580" fill="url(#lwc-glow)"/>
          <rect width="480" height="580" fill="url(#lwc-glow2)"/>
          {/* 그리드 */}
          <g stroke="#ffffff08" strokeWidth="1">
            {Array.from({length: 12}).map((_,i)=><line key={"h"+i} x1="0" x2="480" y1={i*48} y2={i*48}/>)}
            {Array.from({length: 10}).map((_,i)=><line key={"v"+i} x1={i*48} x2={i*48} y1="0" y2="580"/>)}
          </g>
        </svg>
      </div>

      <div style={{ flex: 1, padding: "0 36px 32px", display: "flex", flexDirection: "column", position: "relative", zIndex: 1 }}>
        {/* 상단 헤더 */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 22 }}>
          <LWIcon size={36}/>
          <div>
            <div style={{ fontSize: 13, fontWeight: 800, color: "#fff", letterSpacing: "-0.01em" }}>LEE 電力モニター</div>
            <div style={{ fontSize: 9, color: "#ffffff80", fontFamily: "var(--font-mono)", letterSpacing: "0.06em" }}>POWER MARKET INTEL · v3.4.2</div>
          </div>
        </div>

        <div style={{ flex: 1 }}/>

        {page === 0 && (
          <>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#FF7A45", letterSpacing: "0.16em" }}>SECURE ACCESS</div>
            <div style={{ height: 8 }}/>
            <h1 style={{ fontSize: 30, fontWeight: 800, color: "#fff", margin: 0, letterSpacing: "-0.03em", lineHeight: 1.1 }}>
              ようこそ。<br/>
              <span style={{ color: "#FF9F0A" }}>サインインしてください。</span>
            </h1>
            <div style={{ height: 14 }}/>
            <div style={{ fontSize: 12, color: "#ffffffaa", lineHeight: 1.6 }}>
              承認済み Google アカウントで認証してください。<br/>未承認の場合はアクセス申請が可能です。
            </div>
            <div style={{ height: 32 }}/>

            <button onClick={() => setPage(2)} style={{
              height: 50, borderRadius: 12,
              border: "1px solid #ffffff20",
              background: "linear-gradient(135deg, rgba(255,255,255,0.10), rgba(255,255,255,0.02))",
              backdropFilter: "blur(12px)",
              WebkitBackdropFilter: "blur(12px)",
              color: "#fff",
              fontSize: 14, fontWeight: 700, cursor: "pointer",
              display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 12,
              fontFamily: "inherit",
              transition: "background .15s",
            }}
            onMouseEnter={e => e.currentTarget.style.background = "linear-gradient(135deg, rgba(255,122,69,0.20), rgba(255,255,255,0.04))"}
            onMouseLeave={e => e.currentTarget.style.background = "linear-gradient(135deg, rgba(255,255,255,0.10), rgba(255,255,255,0.02))"}
            >
              <svg width="18" height="18" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
              Google で続行
            </button>
            <div style={{ height: 12 }}/>
            <div style={{ display: "flex", justifyContent: "center", gap: 4 }}>
              <button onClick={() => setPage(1)} style={{
                background: "transparent", border: 0, padding: "8px 14px",
                color: "#ffffffaa", fontSize: 11, fontWeight: 700,
                cursor: "pointer", fontFamily: "inherit",
                letterSpacing: "0.04em",
              }}>アクセスを申請する  →</button>
            </div>
          </>
        )}

        {page === 1 && (
          <>
            <div style={{
              width: 56, height: 56, borderRadius: 16,
              background: "rgba(255,159,10,0.16)",
              color: "#FF9F0A",
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              border: "1px solid rgba(255,159,10,0.3)",
            }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                <path d="M12 4l9 16H3z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/>
                <path d="M12 11v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                <circle cx="12" cy="17.5" r="1" fill="currentColor"/>
              </svg>
            </div>
            <div style={{ height: 18 }}/>
            <h1 style={{ fontSize: 24, fontWeight: 800, color: "#fff", margin: 0, letterSpacing: "-0.02em" }}>登録されていません</h1>
            <div style={{ height: 8 }}/>
            <div style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "#FF9F0A", fontWeight: 700 }}>tanaka@example.com</div>
            <div style={{ height: 14 }}/>
            <div style={{ fontSize: 12, color: "#ffffffaa", lineHeight: 1.7 }}>
              このアカウントはアクセス権がありません。管理者にアクセスを申請してください。
            </div>
            <div style={{ height: 28 }}/>
            <div style={{ display: "flex", gap: 10 }}>
              <button onClick={() => setPage(0)} style={{
                flex: 1, height: 42, borderRadius: 10,
                border: "1px solid #ffffff20",
                background: "rgba(255,255,255,0.05)",
                color: "#fff",
                fontSize: 12, fontWeight: 700, cursor: "pointer",
                fontFamily: "inherit",
              }}>← 戻る</button>
              <button style={{
                flex: 1.4, height: 42, borderRadius: 10,
                border: "none",
                background: "linear-gradient(135deg, #FF7A45, #FF9F0A)",
                color: "#fff",
                fontSize: 12, fontWeight: 800, cursor: "pointer",
                fontFamily: "inherit",
                boxShadow: "0 8px 24px -8px #FF7A4566",
              }}>アクセスを申請</button>
            </div>
          </>
        )}

        {page === 2 && (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
            <div style={{
              width: 64, height: 64, borderRadius: 999,
              border: "3px solid #ffffff20",
              borderTopColor: "#FF7A45",
              animation: "lw-spin 1s linear infinite",
            }}/>
            <div style={{ height: 18 }}/>
            <div style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>認証中...</div>
            <div style={{ height: 8 }}/>
            <div style={{ fontSize: 11, color: "#ffffff88", textAlign: "center", lineHeight: 1.6 }}>
              ブラウザでサインインを完了してください<br/>
              <span style={{ fontSize: 10, color: "#ffffff55" }}>(2 分後に自動キャンセル)</span>
            </div>
            <div style={{ height: 24 }}/>
            <button onClick={() => setPage(0)} style={{
              height: 34, padding: "0 22px", borderRadius: 8,
              border: "1px solid #ffffff20",
              background: "rgba(255,255,255,0.05)",
              color: "#fff",
              fontSize: 11, fontWeight: 700, cursor: "pointer",
              fontFamily: "inherit",
            }}>キャンセル</button>
          </div>
        )}

        <div style={{ flex: 1 }}/>
        <div style={{ fontSize: 9, color: "#ffffff44", textAlign: "center", letterSpacing: "0.08em", fontFamily: "var(--font-mono)" }}>
          © Shirokuma Power · jw.lee@shirokumapower.com
        </div>
      </div>
      <LWPageDots page={page} setPage={setPage} dark/>
    </LWFrame>
  );
};

/* page navigator (mockup demo only) */
const LWPageDots = ({ page, setPage, dark = false }) => {
  const labels = ["Sign In", "Not Reg", "Loading"];
  return (
    <div style={{
      position: "absolute",
      bottom: 8, right: 10,
      display: "flex", gap: 4,
      background: dark ? "rgba(255,255,255,0.06)" : "var(--bg-surface-2)",
      borderRadius: 999,
      padding: 3,
      backdropFilter: "blur(8px)",
      WebkitBackdropFilter: "blur(8px)",
      zIndex: 10,
      border: dark ? "1px solid rgba(255,255,255,0.1)" : "1px solid var(--border-subtle)",
    }}>
      {labels.map((l, i) => (
        <button key={i} onClick={() => setPage(i)} style={{
          border: 0, padding: "3px 9px", borderRadius: 999,
          background: page === i ? (dark ? "#FF7A45" : "var(--accent)") : "transparent",
          color: page === i ? "#fff" : (dark ? "#ffffffaa" : "var(--fg-secondary)"),
          fontSize: 9, fontWeight: 700, cursor: "pointer",
          fontFamily: "inherit",
          letterSpacing: "0.04em",
        }}>{l}</button>
      ))}
    </div>
  );
};

/* keyframes via injected style */
if (typeof document !== "undefined" && !document.getElementById("lw-anim-style")) {
  const st = document.createElement("style");
  st.id = "lw-anim-style";
  st.textContent = `@keyframes lw-spin { to { transform: rotate(360deg); } }`;
  document.head.appendChild(st);
}

/* ============================================================
 * 4) Variation A+ — Classic 베이스 + Glass의 브랜드 헤더 흡수
 *    - Light 톤 (메인 앱과 통일)
 *    - 좌상단 브랜드 헤더: LEE 電力モニター / POWER MARKET INTEL · v3.4.2
 *    - 미세 그리드 배경 텍스처 (정밀感)
 *    - 푸터: ©Shirokuma Power · jw.lee@...
 *    - 中央寄せ 폼 (A의 단순함 유지)
 * ============================================================ */
const LoginWindowAPlus = () => {
  const [page, setPage] = lw_S(0);
  return (
    <LWFrame theme="dark" style={{
      background: "radial-gradient(140% 100% at 100% 0%, #2a1410 0%, #160c0a 35%, var(--bg-surface) 70%)",
    }}>
      {/* 미세 그리드 배경 텍스처 */}
      <div style={{ position: "absolute", inset: 28, pointerEvents: "none", opacity: 0.6 }}>
        <svg width="100%" height="100%" viewBox="0 0 480 552" preserveAspectRatio="none">
          <defs>
            <pattern id="lwap-grid" x="0" y="0" width="32" height="32" patternUnits="userSpaceOnUse">
              <path d="M 32 0 L 0 0 0 32" fill="none" stroke="#ffffff" strokeOpacity="0.04" strokeWidth="1"/>
            </pattern>
            <radialGradient id="lwap-fade" cx="50%" cy="40%" r="60%">
              <stop offset="0%" stopColor="#000" stopOpacity="0"/>
              <stop offset="100%" stopColor="#000" stopOpacity="0.25"/>
            </radialGradient>
            <radialGradient id="lwap-glow" cx="100%" cy="0%" r="80%">
              <stop offset="0%" stopColor="#FF7A45" stopOpacity="0.18"/>
              <stop offset="60%" stopColor="#FF7A45" stopOpacity="0"/>
            </radialGradient>
            <radialGradient id="lwap-glow2" cx="0%" cy="100%" r="70%">
              <stop offset="0%" stopColor="#FF9F0A" stopOpacity="0.22"/>
              <stop offset="55%" stopColor="#FF7A45" stopOpacity="0.06"/>
              <stop offset="100%" stopColor="#FF7A45" stopOpacity="0"/>
            </radialGradient>
            <radialGradient id="lwap-glow3" cx="50%" cy="50%" r="40%">
              <stop offset="0%" stopColor="#FF7A45" stopOpacity="0.05"/>
              <stop offset="100%" stopColor="#FF7A45" stopOpacity="0"/>
            </radialGradient>
          </defs>
          <rect width="480" height="552" fill="url(#lwap-grid)"/>
          <rect width="480" height="552" fill="url(#lwap-glow)"/>
          <rect width="480" height="552" fill="url(#lwap-glow2)"/>
          <rect width="480" height="552" fill="url(#lwap-glow3)"/>
          <rect width="480" height="552" fill="url(#lwap-fade)"/>
        </svg>
      </div>

      {/* 좌상단 브랜드 헤더 (Glass C에서 흡수) */}
      <div style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "20px 28px 0",
        position: "relative", zIndex: 1,
      }}>
        <LWIcon size={32}/>
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.15 }}>
          <span style={{ fontSize: 12, fontWeight: 800, color: "var(--fg-primary)", letterSpacing: "-0.01em" }}>
            LEE 電力モニター
          </span>
          <span style={{ fontSize: 9, color: "var(--fg-tertiary)", fontFamily: "var(--font-mono)", letterSpacing: "0.08em", fontWeight: 600 }}>
            POWER MARKET INTEL · v3.4.2
          </span>
        </div>
      </div>

      <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: "0 56px 0", position: "relative", zIndex: 1 }}>
        {page === 0 && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
            <div style={{ flex: 1 }}/>
            {/* 큰 아이콘 대신 헤더에 작은 것이 있으니 타이포로 임팩트 */}
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--accent)", letterSpacing: "0.18em" }}>SECURE ACCESS</div>
            <div style={{ height: 10 }}/>
            <h1 style={{
              fontSize: 28, fontWeight: 800, margin: 0, letterSpacing: "-0.025em",
              color: "var(--fg-primary)", textAlign: "center", lineHeight: 1.15,
            }}>
              ようこそ。
            </h1>
            <div style={{ height: 8 }}/>
            <div style={{ fontSize: 12, color: "var(--fg-secondary)", textAlign: "center", lineHeight: 1.6, maxWidth: 280 }}>
              承認済み Google アカウントで<br/>サインインしてください。
            </div>
            <div style={{ height: 32 }}/>

            <div style={{ width: "100%" }}>
              <LWGoogleBtn onClick={() => setPage(2)}/>
            </div>
            <div style={{ height: 14 }}/>
            <div style={{ width: "100%", display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ flex: 1, height: 1, background: "var(--border-subtle)" }}/>
              <span style={{ fontSize: 10, color: "var(--fg-tertiary)", fontWeight: 700, letterSpacing: "0.06em" }}>または</span>
              <div style={{ flex: 1, height: 1, background: "var(--border-subtle)" }}/>
            </div>
            <div style={{ height: 14 }}/>
            <button onClick={() => setPage(1)} style={{
              border: 0, background: "transparent",
              fontSize: 12, fontWeight: 700,
              color: "var(--accent)",
              cursor: "pointer",
              fontFamily: "inherit",
              padding: "8px 14px",
            }}>アクセスを申請する  →</button>
            <div style={{ flex: 1 }}/>
          </div>
        )}

        {page === 1 && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
            <div style={{ flex: 1 }}/>
            <div style={{
              width: 72, height: 72, borderRadius: 22,
              background: "color-mix(in srgb, #FF9F0A 14%, transparent)",
              color: "#FF9F0A",
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              border: "1px solid color-mix(in srgb, #FF9F0A 30%, transparent)",
            }}>
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none">
                <path d="M12 4l9 16H3z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/>
                <path d="M12 11v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                <circle cx="12" cy="17.5" r="1" fill="currentColor"/>
              </svg>
            </div>
            <div style={{ height: 18 }}/>
            <h1 style={{ fontSize: 22, fontWeight: 800, margin: 0, color: "var(--fg-primary)", letterSpacing: "-0.02em" }}>登録されていません</h1>
            <div style={{ height: 8 }}/>
            <div style={{
              fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--fg-secondary)",
              fontWeight: 700, padding: "4px 10px", borderRadius: 6,
              background: "var(--bg-surface-2)", border: "1px solid var(--border-subtle)",
            }}>tanaka@example.com</div>
            <div style={{ height: 14 }}/>
            <div style={{ fontSize: 12, color: "var(--fg-secondary)", textAlign: "center", lineHeight: 1.7, maxWidth: 320 }}>
              このアカウントはアクセス権がありません。<br/>
              管理者にアクセスを申請してください。
            </div>
            <div style={{ height: 28 }}/>
            <div style={{ display: "flex", gap: 10, width: "100%" }}>
              <button onClick={() => setPage(0)} style={{
                flex: 1, height: 42, borderRadius: 10,
                border: "1px solid var(--border)",
                background: "var(--bg-surface)",
                color: "var(--fg-primary)",
                fontSize: 12, fontWeight: 700, cursor: "pointer",
                fontFamily: "inherit",
              }}>← 戻る</button>
              <button style={{
                flex: 1.4, height: 42, borderRadius: 10,
                border: "none",
                background: "var(--accent)",
                color: "#fff",
                fontSize: 12, fontWeight: 800, cursor: "pointer",
                fontFamily: "inherit",
                boxShadow: "0 6px 18px -6px color-mix(in srgb, var(--accent) 60%, transparent)",
              }}>アクセスを申請</button>
            </div>
            <div style={{ flex: 1 }}/>
          </div>
        )}

        {page === 2 && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
            <div style={{
              width: 64, height: 64, borderRadius: 999,
              border: "3px solid var(--border-subtle)",
              borderTopColor: "var(--accent)",
              animation: "lw-spin 1s linear infinite",
            }}/>
            <div style={{ height: 20 }}/>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--fg-primary)" }}>認証中...</div>
            <div style={{ height: 8 }}/>
            <div style={{ fontSize: 11, color: "var(--fg-secondary)", textAlign: "center", lineHeight: 1.6 }}>
              ブラウザでサインインを完了してください<br/>
              <span style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>(2 分後に自動キャンセル)</span>
            </div>
            <div style={{ height: 24 }}/>
            <button onClick={() => setPage(0)} style={{
              height: 34, padding: "0 22px", borderRadius: 8,
              border: "1px solid var(--border)",
              background: "var(--bg-surface)",
              color: "var(--fg-primary)",
              fontSize: 11, fontWeight: 700, cursor: "pointer",
              fontFamily: "inherit",
            }}>キャンセル</button>
          </div>
        )}
      </div>

      {/* 푸터 */}
      <div style={{
        padding: "0 28px 18px",
        display: "flex", justifyContent: "space-between", alignItems: "center",
        position: "relative", zIndex: 1,
      }}>
        <div style={{ fontSize: 9, color: "var(--fg-tertiary)", fontFamily: "var(--font-mono)", letterSpacing: "0.06em", fontWeight: 600 }}>
          © Shirokuma Power
        </div>
        <div style={{ fontSize: 9, color: "var(--fg-tertiary)", fontFamily: "var(--font-mono)", letterSpacing: "0.06em", fontWeight: 600 }}>
          jw.lee@shirokumapower.com
        </div>
      </div>

      <LWPageDots page={page} setPage={setPage}/>
    </LWFrame>
  );
};

/* expose */
Object.assign(window, { LoginWindowA, LoginWindowB, LoginWindowC, LoginWindowAPlus });
