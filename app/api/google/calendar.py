"""
Google Calendar API QThread Workers
- 복수 캘린더 이벤트 조회는 new_batch_http_request() 로 단일 HTTP 요청으로 묶음
"""
import logging
from datetime import datetime, timedelta, timezone
from PySide6.QtCore import QThread, Signal, QDate

logger = logging.getLogger(__name__)


class _BaseCalendarWorker(QThread):
    error = Signal(str)

    def _service(self):
        from app.api.google.auth import build_service
        return build_service("calendar", "v3")


class FetchCalendarListWorker(_BaseCalendarWorker):
    """사용자가 접근 가능한 캘린더 목록 조회."""
    data_fetched = Signal(list)

    def run(self):
        try:
            svc    = self._service()
            result = svc.calendarList().list().execute()
            self.data_fetched.emit(result.get("items", []))
        except Exception as e:
            logger.error(f"FetchCalendarList error: {e}", exc_info=True)
            self.error.emit(str(e))


class FetchEventsWorker(_BaseCalendarWorker):
    """특정 기간의 이벤트 조회.
    - 캘린더 1개: 직접 호출
    - 캘린더 복수: new_batch_http_request() 로 단일 HTTP 요청
    """
    data_fetched = Signal(list)

    def __init__(self, calendar_ids: list, time_min: str, time_max: str):
        super().__init__()
        self.calendar_ids = calendar_ids
        self.time_min = time_min
        self.time_max = time_max

    def run(self):
        try:
            svc = self._service()
            all_events: list = []

            def _make_req(cal_id: str):
                return svc.events().list(
                    calendarId=cal_id,
                    timeMin=self.time_min,
                    timeMax=self.time_max,
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=250,
                )

            if len(self.calendar_ids) == 1:
                # 단일 캘린더 — 직접 실행
                cal_id = self.calendar_ids[0]
                try:
                    result = _make_req(cal_id).execute()
                    for ev in result.get("items", []):
                        ev["_calendar_id"] = cal_id
                        all_events.append(ev)
                except Exception as ce:
                    logger.warning(f"Calendar {cal_id} fetch error: {ce}")
            else:
                # 복수 캘린더 — 배치 요청
                # calendar_id 는 이메일 주소 형식을 포함하므로 숫자 인덱스를 배치 ID로 사용
                id_map = {f"cal_{i}": cid for i, cid in enumerate(self.calendar_ids)}
                batch_results: dict[str, dict] = {}

                def _cb(request_id, response, exception):
                    if exception is None and response:
                        batch_results[request_id] = response
                    else:
                        logger.warning(
                            f"Calendar batch [{id_map.get(request_id, request_id)}]: {exception}"
                        )

                batch = svc.new_batch_http_request(callback=_cb)
                for rid, cal_id in id_map.items():
                    batch.add(_make_req(cal_id), request_id=rid)
                batch.execute()

                for req_id, result in batch_results.items():
                    cal_id = id_map[req_id]
                    for ev in result.get("items", []):
                        ev["_calendar_id"] = cal_id
                        all_events.append(ev)

            # 시간순 정렬 (종일 이벤트: date, 시간 이벤트: dateTime)
            all_events.sort(key=lambda ev: (
                ev.get("start", {}).get("dateTime",
                ev.get("start", {}).get("date", "")) or ""
            ))
            self.data_fetched.emit(all_events)
        except Exception as e:
            logger.error(f"FetchEvents error: {e}", exc_info=True)
            self.error.emit(str(e))


class CreateEventWorker(_BaseCalendarWorker):
    """이벤트 생성."""
    success = Signal(dict)

    def __init__(self, calendar_id: str, event_body: dict):
        super().__init__()
        self.calendar_id = calendar_id
        self.event_body  = event_body

    def run(self):
        try:
            svc   = self._service()
            event = svc.events().insert(
                calendarId=self.calendar_id,
                body=self.event_body,
            ).execute()
            self.success.emit(event)
        except Exception as e:
            logger.error(f"CreateEvent error: {e}", exc_info=True)
            self.error.emit(str(e))


class UpdateEventWorker(_BaseCalendarWorker):
    """이벤트 수정."""
    success = Signal(dict)

    def __init__(self, calendar_id: str, event_id: str, event_body: dict):
        super().__init__()
        self.calendar_id = calendar_id
        self.event_id    = event_id
        self.event_body  = event_body

    def run(self):
        try:
            svc   = self._service()
            event = svc.events().update(
                calendarId=self.calendar_id,
                eventId=self.event_id,
                body=self.event_body,
            ).execute()
            self.success.emit(event)
        except Exception as e:
            logger.error(f"UpdateEvent error: {e}", exc_info=True)
            self.error.emit(str(e))


class DeleteEventWorker(_BaseCalendarWorker):
    """이벤트 삭제."""
    success = Signal(str)

    def __init__(self, calendar_id: str, event_id: str):
        super().__init__()
        self.calendar_id = calendar_id
        self.event_id    = event_id

    def run(self):
        try:
            svc = self._service()
            svc.events().delete(
                calendarId=self.calendar_id,
                eventId=self.event_id,
            ).execute()
            self.success.emit(self.event_id)
        except Exception as e:
            logger.error(f"DeleteEvent error: {e}", exc_info=True)
            self.error.emit(str(e))


def make_time_range(target_date: QDate) -> tuple[str, str]:
    """QDate → (time_min_iso, time_max_iso) — 해당 월 포함 주(月~日) 전체.
    월 첫날이 속한 주의 월요일부터, 월 마지막날이 속한 주의 다음 월요일까지.
    """
    import calendar as _cal
    from datetime import date as _date, timedelta

    y, m = target_date.year(), target_date.month()

    first = _date(y, m, 1)
    # first.weekday(): 0=Mon…6=Sun
    week_start = first - timedelta(days=first.weekday())

    _, last_day = _cal.monthrange(y, m)
    last = _date(y, m, last_day)
    week_end = last + timedelta(days=(6 - last.weekday()) % 7 + 1)

    t_min = datetime(week_start.year, week_start.month, week_start.day, tzinfo=timezone.utc)
    t_max = datetime(week_end.year, week_end.month, week_end.day, tzinfo=timezone.utc)
    return (
        t_min.isoformat().replace("+00:00", "Z"),
        t_max.isoformat().replace("+00:00", "Z"),
    )
