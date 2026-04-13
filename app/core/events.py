from PySide6.QtCore import QObject, Signal

class GlobalEventBus(QObject):
    """컴포넌트 간 결합도를 낮추기 위한 전역 이벤트 버스 (Pub/Sub)"""
    occto_updated = Signal(str, str, float)  # time_str, area_str, min_val
    imbalance_updated = Signal()
    jkm_updated = Signal()
    hjks_updated = Signal()
    weather_updated = Signal(list)           # weather_summary
    
    settings_saved = Signal()
    page_requested = Signal(int)             # page_index
    app_quitting = Signal()                  # 앱 종료 시 워커 스레드 일괄 안전 종료 통지

bus = GlobalEventBus()