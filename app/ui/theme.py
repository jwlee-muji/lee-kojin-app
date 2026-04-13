class UIColors:
    """앱 전체에서 사용되는 하드코딩 색상을 중앙 집중화합니다."""
    
    @staticmethod
    def get_imbalance_alert_colors(is_dark: bool, level: int):
        """인밸런스 단가 레벨: 1(Normal) ~ 5(Critical)"""
        if is_dark:
            return {
                1: ("#113344", "#d4d4d4"), 2: ("#1e401e", "#d4d4d4"),
                3: ("#804000", "#d4d4d4"), 4: ("#801515", "#d4d4d4"), 5: ("#5c1111", "#ffffff"),
            }.get(level, ("transparent", "#d4d4d4"))
        else:
            return {
                1: ("#e1f5fe", "#333333"), 2: ("#dcf0dc", "#333333"),
                3: ("#fff0cc", "#333333"), 4: ("#ffdddd", "#333333"), 5: ("#ffcccc", "#ff0000"),
            }.get(level, ("transparent", "#333333"))

    @staticmethod
    def get_reserve_alert_colors(is_dark: bool, status: str):
        """예비율 경고 상태"""
        if is_dark:
            return {
                'low': ("#7f1d1d", "#ffffff"), 'warning': ("#785b0d", "#ffffff"), 'past': ("#2d2d30", "#777777")
            }.get(status, ("transparent", "#d4d4d4"))
        else:
            return {
                'low': ("#ff6666", "#000000"), 'warning': ("#ffeb3b", "#000000"), 'past': ("#e0e0e0", "#888888")
            }.get(status, ("transparent", "#333333"))

def get_global_qss(theme: str) -> str:
    """
    앱 전체에서 공통으로 사용되는 커스텀 위젯들의 스타일시트(QSS)를 반환합니다.
    """
    is_dark = (theme == "dark")
    
    bc = "#555555" if is_dark else "#cccccc"
    tc = "#d4d4d4" if is_dark else "#333333"
    primary_bg = "#094771" if is_dark else "#0d47a1"
    primary_hover = "#0b5a8e" if is_dark else "#1565c0"
    secondary_bg = "#444444" if is_dark else "#dddddd"
    secondary_hover = "#555555" if is_dark else "#cccccc"
    toast_color = "#4caf50" if is_dark else "#388e3c"
    
    return f"""
    /* 앱 전체 공통 툴팁 스타일 */
    QToolTip {{
        background-color: {'#252526' if is_dark else '#ffffff'};
        color: {tc};
        border: 1px solid {bc};
        border-radius: 4px;
        padding: 5px;
    }}

    /* SettingsWidget - QGroupBox 공통 설정 */
    QGroupBox#settingsGroup {{
        font-weight: bold;
        border: 1px solid {bc};
        border-radius: 5px;
        margin-top: 12px;
        padding-top: 10px;
        color: {tc};
    }}
    QGroupBox#settingsGroup::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px;
        top: 0px;
    }}
    
    /* 공통 버튼 액션 스타일 */
    QPushButton#primaryActionBtn {{
        font-weight: bold; background-color: {primary_bg}; color: white; border: none; padding: 8px; border-radius: 4px;
    }}
    QPushButton#primaryActionBtn:hover {{ background-color: {primary_hover}; }}
    
    QPushButton#secondaryActionBtn {{
        font-weight: bold; background-color: {secondary_bg}; color: {tc}; border: 1px solid {bc}; padding: 8px; border-radius: 4px;
    }}
    QPushButton#secondaryActionBtn:hover {{ background-color: {secondary_hover}; }}
    
    /* 공통 토스트 알림 라벨 */
    QLabel#successToast {{
        color: {toast_color};
        font-weight: bold;
    }}
    
    /* 설정 화면 체크박스 */
    QCheckBox#settingsCheckbox {{
        border: none; padding: 6px 10px; border-radius: 6px; background: transparent; 
        color: {tc}; font-size: 13px;
    }}
    QCheckBox#settingsCheckbox:hover {{
        background-color: {'#333333' if is_dark else '#e8e8e8'};
    }}
    """