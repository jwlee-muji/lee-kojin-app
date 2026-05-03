/* global React */
// ============================================================
// LEE — SF Symbols-inspired inline SVG icons
// All icons are 24×24 viewBox, currentColor stroke 1.8
// ============================================================

const Ic = ({ name, size = 18, stroke = 1.8, fill = "none" }) => {
  const props = {
    width: size, height: size, viewBox: "0 0 24 24",
    fill, stroke: "currentColor", strokeWidth: stroke,
    strokeLinecap: "round", strokeLinejoin: "round",
  };
  switch (name) {
    case "board":   return <svg {...props}><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 10h18M9 4v16"/></svg>;
    case "spot":    return <svg {...props}><path d="M3 17l5-7 4 4 6-8 3 4"/><path d="M3 21h18"/></svg>;
    case "power":   return <svg {...props}><path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z"/></svg>;
    case "won":     return <svg {...props}><circle cx="12" cy="12" r="9"/><path d="M8 9l1.5 6h1L12 11l1.5 4h1L16 9M7 11h10M7 13h10"/></svg>;
    case "fire":    return <svg {...props}><path d="M12 3c0 4-4 5-4 9a4 4 0 008 0c0-2-1-3-2-4 0-2 1-4-2-5z"/><path d="M10 17a2 2 0 004 0"/></svg>;
    case "weather": return <svg {...props}><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4 12H2M22 12h-2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4"/></svg>;
    case "plant":   return <svg {...props}><path d="M3 21h18M5 21V8h4v13M11 21V4h6v17M5 11h4M11 8h6M11 13h6M11 17h6"/></svg>;
    case "calendar":return <svg {...props}><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M8 3v4M16 3v4M3 10h18"/></svg>;
    case "gmail":   return <svg {...props}><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 7 9-7"/></svg>;
    case "notice":  return <svg {...props}><path d="M6 8a6 6 0 1112 0c0 7 3 8 3 8H3s3-1 3-8z"/><path d="M10 20a2 2 0 004 0"/></svg>;
    case "chat":    return <svg {...props}><path d="M21 15a2 2 0 01-2 2H8l-5 4V5a2 2 0 012-2h14a2 2 0 012 2v10z"/><circle cx="9" cy="11" r=".7" fill="currentColor"/><circle cx="13" cy="11" r=".7" fill="currentColor"/><circle cx="17" cy="11" r=".7" fill="currentColor"/></svg>;
    case "brief":   return <svg {...props}><path d="M14 3v5h5M19 3l-5 5M5 12h14M5 16h14M5 20h14M5 8h5"/></svg>;
    case "manual":  return <svg {...props}><path d="M4 4h10a4 4 0 014 4v12a3 3 0 00-3-3H4V4z"/><path d="M14 4v13"/></svg>;
    case "memo":    return <svg {...props}><path d="M14 3H6a2 2 0 00-2 2v14a2 2 0 002 2h12a2 2 0 002-2V9z"/><path d="M14 3v6h6M9 14h6M9 17h4"/></svg>;
    case "log":     return <svg {...props}><path d="M4 6h12M4 12h16M4 18h10"/><path d="M19 6h.01M19 18h.01"/></svg>;
    case "bug":     return <svg {...props}><rect x="8" y="6" width="8" height="14" rx="4"/><path d="M12 6V4M9 4l-2-2M15 4l2-2M8 12H4M20 12h-4M8 16l-3 3M16 16l3 3M8 8l-3-3M16 8l3-3"/></svg>;
    case "setting": return <svg {...props}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"/></svg>;
    case "search":  return <svg {...props}><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>;
    case "moon":    return <svg {...props}><path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"/></svg>;
    case "sun":     return <svg {...props}><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4 12H2M22 12h-2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4"/></svg>;
    case "user":    return <svg {...props}><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0116 0"/></svg>;
    case "logout":  return <svg {...props}><path d="M16 17l5-5-5-5M21 12H9M9 4H5a2 2 0 00-2 2v12a2 2 0 002 2h4"/></svg>;
    case "online":  return <svg {...props}><circle cx="12" cy="12" r="4" fill="currentColor"/><circle cx="12" cy="12" r="9" strokeOpacity="0.3"/></svg>;
    case "chevron-down":  return <svg {...props}><path d="M6 9l6 6 6-6"/></svg>;
    case "chevron-right": return <svg {...props}><path d="M9 6l6 6-6 6"/></svg>;
    case "chevron-up":    return <svg {...props}><path d="M6 15l6-6 6 6"/></svg>;
    case "arrow-up":      return <svg {...props}><path d="M12 19V5M5 12l7-7 7 7"/></svg>;
    case "arrow-down":    return <svg {...props}><path d="M12 5v14M5 12l7 7 7-7"/></svg>;
    case "arrow-right":   return <svg {...props}><path d="M5 12h14M12 5l7 7-7 7"/></svg>;
    case "plus":          return <svg {...props}><path d="M12 5v14M5 12h14"/></svg>;
    case "x":             return <svg {...props}><path d="M18 6L6 18M6 6l12 12"/></svg>;
    case "check":         return <svg {...props}><path d="M5 12l5 5L20 7"/></svg>;
    case "send":          return <svg {...props}><path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/></svg>;
    case "sparkle":       return <svg {...props}><path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/></svg>;
    case "zap":           return <svg {...props} fill="currentColor" stroke="none"><path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z"/></svg>;
    case "filter":        return <svg {...props}><path d="M3 5h18M6 12h12M10 19h4"/></svg>;
    case "refresh":       return <svg {...props}><path d="M21 12a9 9 0 11-3-6.7L21 8M21 3v5h-5"/></svg>;
    case "more":          return <svg {...props}><circle cx="5" cy="12" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/><circle cx="19" cy="12" r="1.5" fill="currentColor"/></svg>;
    case "star":          return <svg {...props}><path d="M12 3l3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1z"/></svg>;
    case "pin":           return <svg {...props}><path d="M12 2l3 6 6 1-4.5 4.5L18 20l-6-3-6 3 1.5-6.5L3 9l6-1z"/></svg>;
    case "expand":        return <svg {...props}><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>;
    case "command":       return <svg {...props}><path d="M9 6V4a2 2 0 00-4 0v2m4 0H5m4 0v12m0-12h6m-6 12v2a2 2 0 01-4 0v-2m4 0H5m4 0h6m0 0v2a2 2 0 004 0v-2m-4 0h4m0 0V6m0 0v0a2 2 0 014 0v0a2 2 0 01-4 0z"/></svg>;
    case "dot":           return <svg {...props} fill="currentColor" stroke="none"><circle cx="12" cy="12" r="4"/></svg>;
    case "cloud":         return <svg {...props}><path d="M18 19a4 4 0 000-8 5 5 0 00-9.5-1A4 4 0 006 19h12z"/></svg>;
    case "trending-up":   return <svg {...props}><path d="M22 7l-8.5 8.5L9 11l-7 7M16 7h6v6"/></svg>;
    case "trending-down": return <svg {...props}><path d="M22 17l-8.5-8.5L9 13l-7-7M16 17h6v-6"/></svg>;
    case "alert":         return <svg {...props}><path d="M12 9v4M12 17h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z"/></svg>;
    default: return <svg {...props}><circle cx="12" cy="12" r="9"/></svg>;
  }
};

window.Ic = Ic;
