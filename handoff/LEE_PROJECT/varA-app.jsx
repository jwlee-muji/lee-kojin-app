/* global React */
// Variation A — Full app with router for detail screens
const { useState: rUS, useEffect: rUE } = React;
const { Sidebar, TopBar, ITEM_TO_TAB } = window.varA_shell;
const { ImbCard, ReserveCard, SpotCard, JkmCard, HjksCard, WeatherCard } = window.varA_cards;
const { CalendarCard, GmailCard, AiChatCard, NoticeCard, MemoCard, BriefCard, Toast } = window.varA_widgets;
const { SpotDetail, ImbalanceDetail } = window.varA_detail_screens;
const { ReserveDetail, JKMDetail: JkmDetail } = window.varA_detail_screens2;
const { WeatherDetail } = window.varA_detail_screens3;
const { HjksDetail } = window.varA_detail_screens4;
const { GmailDetail } = window.varA_gmail_detail;
const { CalendarDetail } = window.varA_calendar_detail;
const { AiChatDetail, NoticeDetail, MemoDetail } = window.varA_detail_screens6;
const { SettingsDetail, LogDetail, BugDetail, ManualDetail, BriefDetail } = window.varA_misc_detail;

const Dashboard = ({ isDark, onCardClick }) => (
  <div className="lee-scroll" style={{
    flex: 1, overflow: "auto", padding: 28,
    background: "var(--bg-app)", animation: "fadeIn 0.3s ease",
  }}>
    <div style={{ marginBottom: 24, display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 24 }}>
      <div>
        <div style={{ fontSize: 12, color: "var(--fg-tertiary)", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>
          2025年 1月 22日 (水) · 09:14
        </div>
        <h1 style={{ fontSize: 32, fontWeight: 800, letterSpacing: "-0.02em" }}>
          おはようございます、李さん
        </h1>
        <div style={{ fontSize: 14, color: "var(--fg-secondary)", marginTop: 4 }}>
          本日の電力市場は <b style={{ color: "var(--c-imb)" }}>東京エリア予備率が警戒水準</b>。スポット価格も上昇傾向です。
        </div>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button style={{
          padding: "10px 16px", borderRadius: 12, border: "1px solid var(--border)",
          background: "var(--bg-surface)", color: "var(--fg-primary)",
          fontFamily: "inherit", fontSize: 13, fontWeight: 600, cursor: "pointer",
        }}>レイアウト編集</button>
        <button style={{
          padding: "10px 16px", borderRadius: 12, border: "none",
          background: "linear-gradient(135deg, var(--c-ai), var(--c-power))",
          color: "#fff", fontFamily: "inherit", fontSize: 13, fontWeight: 700, cursor: "pointer",
          boxShadow: "0 4px 14px rgba(88, 86, 214, 0.35)",
        }}>+ ウィジェット追加</button>
      </div>
    </div>

    <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr 1fr", gap: 16, marginBottom: 16 }}>
      <BriefCard onClick={() => onCardClick("brief")}/>
      <ImbCard onClick={() => onCardClick("imb")}/>
      <ReserveCard onClick={() => onCardClick("reserve")}/>
    </div>
    <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr 1fr", gap: 16, marginBottom: 16 }}>
      <SpotCard onClick={() => onCardClick("spot")}/>
      <JkmCard onClick={() => onCardClick("jkm")}/>
      <WeatherCard onClick={() => onCardClick("weather")} isDark={isDark}/>
    </div>
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 16 }}>
      <HjksCard onClick={() => onCardClick("hjks")}/>
      <CalendarCard onClick={() => onCardClick("calendar")}/>
      <GmailCard onClick={() => onCardClick("gmail")}/>
      <NoticeCard onClick={() => onCardClick("notice")}/>
    </div>
    <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 16 }}>
      <AiChatCard onClick={() => onCardClick("ai")}/>
      <MemoCard onClick={() => onCardClick("memo")}/>
    </div>

    <div style={{
      marginTop: 28, padding: "12px 16px",
      background: "var(--bg-surface)", border: "1px solid var(--border-subtle)",
      borderRadius: 12, display: "flex", alignItems: "center", gap: 12,
      fontSize: 12, color: "var(--fg-tertiary)",
    }}>
      <span style={{ width: 6, height: 6, borderRadius: 999, background: "var(--c-ok)" }}/>
      全データ同期中 · 最終更新 09:14:32 · 次回 09:15:00
      <span style={{ marginLeft: "auto" }}>v 2.0.0 · LEE 電力モニター</span>
    </div>
  </div>
);

const Placeholder = ({ name, onBack }) => (
  <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "var(--fg-secondary)" }}>
    <div style={{ fontSize: 14, marginBottom: 12 }}>「{name}」詳細画面 (準備中)</div>
    <button onClick={onBack} style={{
      padding: "8px 16px", borderRadius: 10, border: "1px solid var(--border)",
      background: "var(--bg-surface)", color: "var(--fg-primary)",
      fontFamily: "inherit", fontSize: 12, fontWeight: 600, cursor: "pointer",
    }}>← ダッシュボードに戻る</button>
  </div>
);

const VarAApp = () => {
  const [active, setActiveRaw] = rUS("dashboard");
  const [topGroup, setTopGroup] = rUS("market");
  const setActive = (id) => {
    setActiveRaw(id);
    // Sidebar 항목인 경우 해당 탭으로 자동 전환
    const tabId = ITEM_TO_TAB && ITEM_TO_TAB[id];
    if (tabId) setTopGroup(tabId);
  };
  const onTopGroupChange = (gid) => {
    setTopGroup(gid);
    // 탭 전환시 dashboard로 복귀
    setActiveRaw("dashboard");
  };
  const [isDark, setIsDark] = rUS(true);
  const [toast, setToast] = rUS(null);

  rUE(() => {
    document.documentElement.setAttribute("data-theme", isDark ? "dark" : "light");
  }, [isDark]);

  rUE(() => {
    const t1 = setTimeout(() => {
      setToast({
        title: "東京エリア予備率 警戒",
        body: "18:30 時点で予備率が 6.2% に低下。需給ひっ迫の恐れがあります。",
        icon: "alert", color: "var(--c-bad)",
      });
    }, 1500);
    const t2 = setTimeout(() => setToast(null), 6500);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, []);

  const goBack = () => setActive("dashboard");
  const renderContent = () => {
    switch (active) {
      case "dashboard": return <Dashboard isDark={isDark} onCardClick={setActive}/>;
      case "spot":      return <div className="lee-scroll" style={{ flex: 1, overflow: "auto", animation: "slideInRight 0.35s ease" }}><SpotDetail onBack={goBack}/></div>;
      case "imb":       return <div className="lee-scroll" style={{ flex: 1, overflow: "auto", animation: "slideInRight 0.35s ease" }}><ImbalanceDetail onBack={goBack}/></div>;
      case "reserve":   return <div className="lee-scroll" style={{ flex: 1, overflow: "auto", animation: "slideInRight 0.35s ease" }}><ReserveDetail onBack={goBack}/></div>;
      case "jkm":       return <div className="lee-scroll" style={{ flex: 1, overflow: "auto", animation: "slideInRight 0.35s ease" }}><JkmDetail onBack={goBack}/></div>;
      case "weather":   return <div className="lee-scroll" style={{ flex: 1, overflow: "auto", animation: "slideInRight 0.35s ease" }}><WeatherDetail onBack={goBack} isDark={isDark}/></div>;
      case "hjks":      return <div className="lee-scroll" style={{ flex: 1, overflow: "auto", animation: "slideInRight 0.35s ease" }}><HjksDetail onBack={goBack}/></div>;
      case "calendar":  return <div className="lee-scroll" style={{ flex: 1, overflow: "auto", animation: "slideInRight 0.35s ease" }}><CalendarDetail onBack={goBack}/></div>;
      case "gmail":     return <div className="lee-scroll" style={{ flex: 1, overflow: "auto", animation: "slideInRight 0.35s ease" }}><GmailDetail onBack={goBack}/></div>;
      case "ai":        return <div className="lee-scroll" style={{ flex: 1, overflow: "hidden", animation: "slideInRight 0.35s ease", display: "flex", flexDirection: "column" }}><AiChatDetail onBack={goBack}/></div>;
      case "notice":    return <div className="lee-scroll" style={{ flex: 1, overflow: "auto", animation: "slideInRight 0.35s ease" }}><NoticeDetail onBack={goBack}/></div>;
      case "memo":      return <div className="lee-scroll" style={{ flex: 1, overflow: "auto", animation: "slideInRight 0.35s ease" }}><MemoDetail onBack={goBack}/></div>;
      case "brief":     return <div className="lee-scroll" style={{ flex: 1, overflow: "auto", animation: "slideInRight 0.35s ease" }}><BriefDetail onBack={goBack}/></div>;
      case "setting":   return <div className="lee-scroll" style={{ flex: 1, overflow: "auto", animation: "slideInRight 0.35s ease" }}><SettingsDetail onBack={goBack}/></div>;
      case "log":       return <div className="lee-scroll" style={{ flex: 1, overflow: "auto", animation: "slideInRight 0.35s ease" }}><LogDetail onBack={goBack}/></div>;
      case "bug":       return <div className="lee-scroll" style={{ flex: 1, overflow: "auto", animation: "slideInRight 0.35s ease" }}><BugDetail onBack={goBack}/></div>;
      case "manual":    return <div className="lee-scroll" style={{ flex: 1, overflow: "auto", animation: "slideInRight 0.35s ease" }}><ManualDetail onBack={goBack}/></div>;
      default:          return <Placeholder name={active} onBack={goBack}/>;
    }
  };

  return (
    <div style={{
      width: "100%", height: "100%", display: "flex", flexDirection: "column",
      background: "var(--bg-app)", color: "var(--fg-primary)",
      fontFamily: "var(--font-sans)",
    }}>
      <TopBar activeGroup={topGroup} onGroupChange={onTopGroupChange}
        onThemeToggle={() => setIsDark(d => !d)} isDark={isDark}/>
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        <Sidebar active={active} onSelect={setActive} activeGroup={topGroup} onGroupChange={onTopGroupChange}/>
        {renderContent()}
      </div>
      <Toast toast={toast} onClose={() => setToast(null)}/>
    </div>
  );
};

window.VarAApp = VarAApp;
