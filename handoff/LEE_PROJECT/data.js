/* global React */
// ============================================================
// LEE Mock Data — リアルな日本電力市場データの模倣
// ============================================================

window.LEE_DATA = {
  user: {
    email: "lee.tanaka@enex.co.jp",
    name: "李 田中",
    role: "市場アナリスト",
  },

  // ── JEPX スポット価格 (10エリア) ──
  spotAreas: [
    { area: "システム", avg: 12.84, max: 28.50, min: 4.21, trend: +1.2 },
    { area: "北海道",   avg: 14.20, max: 31.00, min: 5.10, trend: +0.8 },
    { area: "東北",     avg: 13.10, max: 27.80, min: 4.55, trend: +1.5 },
    { area: "東京",     avg: 15.42, max: 33.20, min: 5.80, trend: +2.1 },
    { area: "中部",     avg: 12.20, max: 26.10, min: 4.10, trend: -0.4 },
    { area: "北陸",     avg: 11.80, max: 25.50, min: 3.90, trend: -0.2 },
    { area: "関西",     avg: 12.55, max: 26.80, min: 4.20, trend: +0.5 },
    { area: "中国",     avg: 11.40, max: 24.90, min: 3.85, trend: -0.7 },
    { area: "四国",     avg: 11.95, max: 25.40, min: 4.00, trend: +0.1 },
    { area: "九州",     avg: 10.80, max: 23.50, min: 3.50, trend: -1.1 },
  ],

  // ── 30分単位 スポット価格 (48コマ) ──
  spotCurve: Array.from({ length: 48 }, (_, i) => {
    const h = i / 2;
    // モーニング・夕方ピーク
    const morning = Math.exp(-Math.pow((h - 8) / 2, 2)) * 8;
    const evening = Math.exp(-Math.pow((h - 19) / 2.5, 2)) * 14;
    const base = 8 + morning + evening + Math.sin(i * 0.3) * 1.2;
    return { i, h, price: +base.toFixed(2) };
  }),

  // ── 電力予備率 (10エリア) ──
  reserve: [
    { area: "北海道", value: 12.4, status: "ok" },
    { area: "東北",   value: 9.8,  status: "warn" },
    { area: "東京",   value: 6.2,  status: "bad" },
    { area: "中部",   value: 11.5, status: "ok" },
    { area: "北陸",   value: 14.2, status: "ok" },
    { area: "関西",   value: 8.9,  status: "warn" },
    { area: "中国",   value: 13.0, status: "ok" },
    { area: "四国",   value: 10.4, status: "ok" },
    { area: "九州",   value: 7.5,  status: "warn" },
    { area: "沖縄",   value: 15.8, status: "ok" },
  ],

  // ── インバランス単価 (24時間, 円/kWh) ──
  imbalance: Array.from({ length: 48 }, (_, i) => {
    const h = i / 2;
    const peak = Math.exp(-Math.pow((h - 18) / 2.2, 2)) * 35;
    const base = 8 + peak + Math.sin(i * 0.4) * 2.5;
    return { h, value: +base.toFixed(2) };
  }),

  // ── JKM LNG 価格 (60日推移) ──
  jkmHistory: (() => {
    let v = 13.5;
    return Array.from({ length: 60 }, (_, i) => {
      v += (Math.random() - 0.48) * 0.6;
      v = Math.max(11, Math.min(17, v));
      return { d: i, v: +v.toFixed(3) };
    });
  })(),

  // ── 全国天気 (10地域) ──
  weather: [
    { region: "札幌",   temp: 8,   wmo: "snowy",        text: "雪のち曇り",    accent: "#7AB8E0" },
    { region: "仙台",   temp: 14,  wmo: "cloudy",       text: "曇り",         accent: "#9CA3AF" },
    { region: "東京",   temp: 19,  wmo: "clear",        text: "晴れ",         accent: "#FBBF24" },
    { region: "名古屋", temp: 21,  wmo: "partly_cloudy",text: "晴れ時々曇り", accent: "#FCD34D" },
    { region: "大阪",   temp: 22,  wmo: "clear",        text: "快晴",         accent: "#F59E0B" },
    { region: "広島",   temp: 20,  wmo: "drizzle",      text: "弱い雨",       accent: "#60A5FA" },
    { region: "高松",   temp: 19,  wmo: "rainy",        text: "雨",           accent: "#3B82F6" },
    { region: "福岡",   temp: 23,  wmo: "clear",        text: "晴れ",         accent: "#F59E0B" },
    { region: "鹿児島", temp: 24,  wmo: "stormy",       text: "雷雨",         accent: "#A78BFA" },
    { region: "那覇",   temp: 27,  wmo: "mostly_clear", text: "概ね晴れ",     accent: "#FBBF24" },
  ],

  // ── HJKS 発電稼働状況 (電源種別) ──
  hjks: [
    { source: "原子力",     operating: 8200,  stopped: 2100,  color: "#A78BFA" },
    { source: "石炭火力",   operating: 18400, stopped: 4800,  color: "#475569" },
    { source: "LNG火力",    operating: 32100, stopped: 6200,  color: "#F4B740" },
    { source: "石油火力",   operating: 1200,  stopped: 8400,  color: "#F25C7A" },
    { source: "水力",       operating: 14800, stopped: 2400,  color: "#2EC4B6" },
    { source: "太陽光",     operating: 22400, stopped: 0,     color: "#FF9500" },
    { source: "風力",       operating: 4100,  stopped: 800,   color: "#5B8DEF" },
  ],

  // ── Google カレンダー予定 ──
  // Legacy short list — kept for any legacy reference
  calendar: [
    { day: 28, time: "09:00", title: "JEPX スポット入札締切",  cal: "市場", color: "#FF7A45" },
    { day: 28, time: "11:00", title: "需給バランス会議",      cal: "社内", color: "#5B8DEF" },
    { day: 29, time: "14:00", title: "OCCTO レポート提出",    cal: "業務", color: "#34C759" },
    { day: 30, time: "10:00", title: "LNG 調達契約レビュー",  cal: "取引", color: "#A78BFA" },
    { day: 30, time: "16:30", title: "週次マーケット報告",    cal: "社内", color: "#5B8DEF" },
    { day: 1,  time: "09:30", title: "月次クローズ",          cal: "業務", color: "#34C759" },
    { day: 2,  time: "13:00", title: "AI 予測モデル定例",      cal: "技術", color: "#5856D6" },
  ],

  // Rich calendar events (multi-day spans, all-day flag, time range, calendar)
  // start/end are ISO YYYY-MM-DD; for single-day events end === start
  calendarEvents: [
    { id: "e1",  start: "2025-01-06", end: "2025-01-08", allDay: true,  title: "ASEAN エネルギーサミット 出張",  cal: "出張", color: "#A78BFA" },
    { id: "e2",  start: "2025-01-09", end: "2025-01-09", time: "09:00", endTime: "10:00", title: "週次 マーケットレビュー", cal: "社内", color: "#5B8DEF" },
    { id: "e3",  start: "2025-01-10", end: "2025-01-10", time: "14:00", endTime: "15:30", title: "JEPX 月例説明会",          cal: "市場", color: "#FF7A45" },
    { id: "e4",  start: "2025-01-13", end: "2025-01-15", allDay: true,  title: "OCCTO 監査対応週間",            cal: "業務", color: "#34C759" },
    { id: "e5",  start: "2025-01-14", end: "2025-01-14", time: "11:00", endTime: "12:00", title: "LNG 調達契約レビュー",     cal: "取引", color: "#FF453A" },
    { id: "e6",  start: "2025-01-16", end: "2025-01-16", time: "10:00", endTime: "11:30", title: "AI 予測モデル定例",         cal: "技術", color: "#5856D6" },
    { id: "e7",  start: "2025-01-17", end: "2025-01-17", time: "16:30", endTime: "17:30", title: "週次マーケット報告",        cal: "社内", color: "#5B8DEF" },
    { id: "e8",  start: "2025-01-20", end: "2025-01-22", allDay: true,  title: "新人研修 (講師)",                 cal: "社内", color: "#5B8DEF" },
    { id: "e9",  start: "2025-01-21", end: "2025-01-21", time: "09:00", endTime: "10:00", title: "JEPX スポット入札締切",     cal: "市場", color: "#FF7A45" },
    { id: "e10", start: "2025-01-22", end: "2025-01-22", time: "11:00", endTime: "12:00", title: "需給バランス会議",          cal: "社内", color: "#5B8DEF" },
    { id: "e11", start: "2025-01-22", end: "2025-01-22", time: "14:00", endTime: "16:00", title: "OCCTO レポート提出",        cal: "業務", color: "#34C759" },
    { id: "e12", start: "2025-01-22", end: "2025-01-22", time: "18:00", endTime: "19:00", title: "夕食 / 部内会食",           cal: "個人", color: "#FF9F0A" },
    { id: "e13", start: "2025-01-23", end: "2025-01-24", allDay: true,  title: "経営会議 (本社)",                 cal: "社内", color: "#5B8DEF" },
    { id: "e14", start: "2025-01-27", end: "2025-01-27", time: "10:00", endTime: "11:30", title: "Q1 戦略レビュー",            cal: "業務", color: "#34C759" },
    { id: "e15", start: "2025-01-28", end: "2025-01-30", allDay: true,  title: "東京エネルギー展示会",            cal: "出張", color: "#A78BFA" },
    { id: "e16", start: "2025-01-30", end: "2025-01-30", time: "15:00", endTime: "17:00", title: "月末クローズ",              cal: "業務", color: "#34C759" },
    { id: "e17", start: "2025-01-31", end: "2025-01-31", allDay: true,  title: "月次レポート 提出期限",            cal: "業務", color: "#FF453A" },
  ],

  // Calendar visibility / settings
  calendarMeta: {
    calendars: [
      { id: "市場", color: "#FF7A45", visible: true },
      { id: "社内", color: "#5B8DEF", visible: true },
      { id: "業務", color: "#34C759", visible: true },
      { id: "取引", color: "#FF453A", visible: true },
      { id: "技術", color: "#5856D6", visible: true },
      { id: "出張", color: "#A78BFA", visible: true },
      { id: "個人", color: "#FF9F0A", visible: true },
    ],
    weekStart: 0, // 0 = 日曜, 1 = 月曜
    showWeekNumbers: true,
    defaultView: "month", // "month" | "week" | "day"
  },

  // ── Gmail (受信箱) ──
  gmail: [
    { id: "g1",  from: "OCCTO 通知",         email: "alert@occto.or.jp",         subject: "[緊急] 東京エリア予備率 6.2% — 注意喚起", snippet: "本日 18:30 における東京エリアの予備率が...", time: "12分前", date: "2025-01-22 14:08", unread: true,  starred: true,  important: true,  attachments: 0, labels: ["緊急", "市場"] },
    { id: "g2",  from: "JEPX システム",      email: "no-reply@jepx.org",         subject: "スポット市場 約定結果通知 (4/30)",       snippet: "システムプライス平均 12.84 円/kWh、最高...", time: "32分前", date: "2025-01-22 13:48", unread: true,  starred: false, important: false, attachments: 1, labels: ["市場"] },
    { id: "g3",  from: "Bloomberg Energy",   email: "newsletter@bloomberg.net",  subject: "JKM Asia LNG closes at $14.32",          snippet: "Asian LNG benchmark Japan Korea Marker...",  time: "1時間前", date: "2025-01-22 13:20", unread: true,  starred: true,  important: false, attachments: 0, labels: ["ニュース"] },
    { id: "g4",  from: "田中 部長",           email: "tanaka@enex.co.jp",         subject: "Re: 来週のマーケット報告について",       snippet: "了解です。木曜の資料は前回フォーマットで...", time: "2時間前", date: "2025-01-22 12:14", unread: false, starred: false, important: true,  attachments: 0, labels: ["社内"] },
    { id: "g5",  from: "EIA Update",         email: "alerts@eia.gov",            subject: "Weekly Petroleum Status Report",         snippet: "Crude oil inventories increased by 2.8M...",   time: "3時間前", date: "2025-01-22 11:30", unread: false, starred: false, important: false, attachments: 2, labels: ["ニュース"] },
    { id: "g6",  from: "Open-Meteo Alert",   email: "alerts@open-meteo.com",     subject: "九州地域 雷雨警報",                     snippet: "鹿児島県を中心に雷を伴う激しい雨が予想...",     time: "5時間前", date: "2025-01-22 09:42", unread: false, starred: false, important: false, attachments: 0, labels: ["天気"] },
    { id: "g7",  from: "鈴木 アナリスト",      email: "suzuki@enex.co.jp",         subject: "需要予測モデル v2.3 リリースノート",      snippet: "新バージョンで関西エリアの予測精度が...",      time: "8時間前", date: "2025-01-22 06:11", unread: false, starred: false, important: false, attachments: 3, labels: ["技術", "社内"] },
    { id: "g8",  from: "OCCTO 通知",         email: "alert@occto.or.jp",         subject: "週間需給見通し (1/27 - 2/2)",            snippet: "来週は寒気の影響で東日本中心に需要増...",      time: "昨日",   date: "2025-01-21 17:03", unread: false, starred: true,  important: false, attachments: 1, labels: ["市場"] },
    { id: "g9",  from: "山田 課長",           email: "yamada@enex.co.jp",         subject: "Q1 戦略レビュー 議事録",                 snippet: "本日の会議で確認された事項と次回までの...",     time: "昨日",   date: "2025-01-21 15:45", unread: false, starred: false, important: true,  attachments: 1, labels: ["社内"] },
    { id: "g10", from: "Reuters Energy",     email: "newsalert@reuters.com",     subject: "Asian LNG demand expected to rise 4% in Q1", snippet: "Industry analysts expect strong winter...",     time: "昨日",   date: "2025-01-21 11:22", unread: false, starred: false, important: false, attachments: 0, labels: ["ニュース"] },
    { id: "g11", from: "JEPX システム",      email: "no-reply@jepx.org",         subject: "[週次] スポット市場サマリー",             snippet: "1/13-1/19 週: 平均価格 13.20 円/kWh...",       time: "2日前",  date: "2025-01-20 09:00", unread: false, starred: false, important: false, attachments: 1, labels: ["市場"] },
    { id: "g12", from: "IT サポート",         email: "it-support@enex.co.jp",     subject: "セキュリティ更新のお知らせ",              snippet: "1/25 (土) 22:00-24:00 に定期メンテ...",         time: "2日前",  date: "2025-01-20 08:30", unread: false, starred: false, important: false, attachments: 0, labels: ["社内"] },
  ],

  // Gmail label palette (configurable)
  gmailLabels: [
    { id: "緊急",     color: "#FF453A" },
    { id: "市場",     color: "#FF7A45" },
    { id: "社内",     color: "#5B8DEF" },
    { id: "ニュース", color: "#A78BFA" },
    { id: "天気",     color: "#0A84FF" },
    { id: "技術",     color: "#5856D6" },
  ],

  // ── AI チャット ──
  aiChat: [
    { role: "user", text: "本日の東京エリアの需給状況を要約して" },
    { role: "ai",   text: "東京エリアは現在 **予備率 6.2%** とタイトな状況です。18:30 のピーク時間帯にかけてさらに低下する見込みで、OCCTO から注意喚起が出ています。\n\n• スポット価格平均: **15.42 円/kWh** (前日比 +2.1)\n• インバランス単価: 高値圏 (最大 38.5 円/kWh)\n• 主因: 暖房需要増 + 太陽光発電の早期低下\n\n対策として揚水発電の活用と地域間融通の強化が想定されます。" },
    { role: "user", text: "明日のスポット価格はどう動きそう?" },
    { role: "ai",   text: "気象データと過去パターンから、明日の東京エリアスポット価格は **14-17 円/kWh** のレンジで推移すると予測します。\n\n注意点:\n• 朝 8 時台のランプアップ時に瞬間的な高値\n• 夕方 18-19 時台のピークで最高値想定\n• LNG 価格 (JKM $14.32) が高止まりで下値を支える可能性\n\n[詳細レポートを見る →]" },
  ],

  notifications: [
    { time: "12分前",  title: "東京エリア予備率警報",    message: "予備率が 6.2% に低下しました", level: "bad",  read: false },
    { time: "32分前",  title: "JEPX 約定結果",            message: "システムプライス 12.84 円/kWh", level: "info", read: false },
    { time: "1時間前", title: "JKM 価格更新",             message: "$14.32 (前日比 -1.2%)",         level: "info", read: false },
    { time: "2時間前", title: "Gmail 新着メール 3件",      message: "市場ラベルで未読が増えました",  level: "info", read: true  },
    { time: "5時間前", title: "九州 雷雨警報",            message: "Open-Meteo より天候警告",        level: "warn", read: true  },
    { time: "昨日",    title: "週次バックアップ完了",      message: "DB スナップショット作成完了",    level: "ok",   read: true  },
  ],
};

// ── Derived/adapter fields for cards ──────────────────────────
(() => {
  const D = window.LEE_DATA;
  const palette = ["#FF7A45", "#5B8DEF", "#F4B740", "#34C759", "#A78BFA", "#F25C7A", "#2EC4B6", "#5856D6"];
  const levelColor = { bad: "#FF453A", warn: "#FF9F0A", ok: "#30D158", info: "#0A84FF" };
  const levelIcon  = { bad: "alert", warn: "alert", ok: "check", info: "notice" };

  // Gmail: derive initial + preview + color
  D.gmail = D.gmail.map((m, i) => ({
    ...m,
    initial: (m.from || "?").trim().charAt(0),
    preview: m.snippet || "",
    color: palette[i % palette.length],
  }));

  // Notices alias from notifications + derive icon/color/body/unread
  D.notices = D.notifications.map(n => ({
    time: n.time,
    title: n.title,
    body: n.message,
    color: levelColor[n.level] || levelColor.info,
    icon: levelIcon[n.level] || "notice",
    unread: !n.read,
  }));

  // Calendar: provide a `time` string already exists; nothing extra needed.

  // Memos
  D.memos = [
    { title: "需給ひっ迫の対応案",  body: "夕方ピーク帯における揚水発電活用と、関西エリアからの融通調整について議事録に記載。次回 MTG で要検討。", date: "1/22 09:10", color: "#FFCC00" },
    { title: "LNG 長期契約レビュー", body: "Q2 のスポット LNG 比率を 15% → 12% に引き下げ、長期契約での安定調達を強化する方向で。", date: "1/21 16:42", color: "#A78BFA" },
    { title: "AI 予測モデル v3",      body: "天候 + 需給 + JKM の 3 入力モデル、東京エリアの MAPE 4.2% まで改善。来週デプロイ予定。", date: "1/20 18:08", color: "#5856D6" },
  ];
})();
