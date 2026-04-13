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