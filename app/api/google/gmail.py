"""
Gmail API QThread Workers
- 모든 반복 API 호출은 new_batch_http_request() 로 단일 HTTP 요청으로 묶음
- 429 레이트 리밋 시 지수 백오프로 재시도
"""
import base64
import logging
import time
from email import message_from_bytes
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)

# 표시 순서 고정용 시스템 라벨
SYSTEM_LABELS = ["INBOX", "STARRED", "IMPORTANT", "SENT", "SPAM", "TRASH"]

_BATCH_CHUNK  = 20   # 배치당 최대 요청 수 (429 방지를 위해 축소)
_MAX_RETRIES  = 4    # 429 재시도 최대 횟수


class _BaseGmailWorker(QThread):
    error = Signal(str)

    def _service(self):
        from app.api.google.auth import build_service
        return build_service("gmail", "v1")


def _execute_single(req, max_retries: int = _MAX_RETRIES):
    """
    단일 API 요청을 실행하고 429 레이트 리밋 시 지수 백오프로 재시도.
    """
    for attempt in range(max_retries):
        try:
            return req.execute()
        except Exception as e:
            s = str(e)
            if "429" in s or "rateLimitExceeded" in s:
                if attempt < max_retries - 1:
                    delay = min(30, 2 ** attempt)
                    logger.warning(
                        f"Rate limit (single), retry in {delay}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                    continue
            raise
    raise Exception("Max retries exceeded")


def _execute_batch_chunks(svc, requests_map: dict, global_cb):
    """
    requests_map: {request_id_str: request_obj}
    global_cb: callable(request_id, response, exception)
    20개씩 나누어 실행하고, 429 응답 시 지수 백오프(1→2→4→8초)로 재시도.
    """
    items = list(requests_map.items())
    for chunk_start in range(0, len(items), _BATCH_CHUNK):
        chunk = dict(items[chunk_start:chunk_start + _BATCH_CHUNK])
        remaining = dict(chunk)

        for attempt in range(_MAX_RETRIES):
            if not remaining:
                break

            rate_limited: list[str] = []

            def _cb(rid, resp, exc, _rl=rate_limited):
                if exc is not None:
                    s = str(exc)
                    if "429" in s or "rateLimitExceeded" in s:
                        _rl.append(rid)
                        return
                global_cb(rid, resp, exc)

            batch = svc.new_batch_http_request(callback=_cb)
            for rid, req in remaining.items():
                batch.add(req, request_id=rid)
            batch.execute()

            if not rate_limited:
                break
            remaining = {rid: remaining[rid] for rid in rate_limited if rid in remaining}
            if attempt < _MAX_RETRIES - 1:
                delay = min(30, 2 ** attempt)
                logger.warning(
                    f"Rate limit hit, retrying {len(remaining)} requests "
                    f"in {delay}s (attempt {attempt + 1}/{_MAX_RETRIES})"
                )
                time.sleep(delay)


class FetchLabelsWorker(_BaseGmailWorker):
    """라벨 목록 + 각 라벨의 미읽 수 — 배치 조회."""
    data_fetched = Signal(list)

    def run(self):
        try:
            svc = self._service()
            result = _execute_single(svc.users().labels().list(userId="me"))
            labels = result.get("labels", [])
            if not labels:
                self.data_fetched.emit([])
                return

            # 배치로 label detail (messagesUnread 포함) 조회
            # label id 는 "INBOX", "Label_xxxxx" 형식 — 배치 ID로 안전하게 사용
            detailed: dict[str, dict] = {}

            def _cb(request_id, response, exception):
                if exception is None and response:
                    detailed[request_id] = response
                else:
                    logger.warning(f"Label detail fetch failed [{request_id}]: {exception}")

            req_map = {
                lbl["id"]: svc.users().labels().get(userId="me", id=lbl["id"])
                for lbl in labels
            }
            _execute_batch_chunks(svc, req_map, _cb)

            # 순서 보전 + 실패 시 기본 lbl 폴백
            detail_list = [detailed.get(lbl["id"], lbl) for lbl in labels]

            sys_order = {name: i for i, name in enumerate(SYSTEM_LABELS)}
            detail_list.sort(key=lambda x: (
                0 if x.get("type") == "system" else 1,
                sys_order.get(x.get("id", ""), 99),
                x.get("name", ""),
            ))
            self.data_fetched.emit(detail_list)
        except Exception as e:
            logger.error(f"FetchLabels error: {e}", exc_info=True)
            self.error.emit(str(e))


class FetchMailListWorker(_BaseGmailWorker):
    """라벨별 메일 목록 (헤더 정보만) — 배치 조회.

    Gmail 검색 쿼리 (q) 파라미터를 지원합니다 ("from:foo subject:bar" 등).
    """
    data_fetched = Signal(list, str)   # (mails, nextPageToken)

    def __init__(self, label_ids: list, max_results: int = 50,
                 page_token: str = "", q: str = ""):
        super().__init__()
        self.label_ids   = label_ids
        self.max_results = max_results
        self.page_token  = page_token
        self.q           = q

    def run(self):
        try:
            svc = self._service()
            kwargs = dict(
                userId="me",
                labelIds=self.label_ids,
                maxResults=self.max_results,
            )
            if self.page_token:
                kwargs["pageToken"] = self.page_token
            if self.q:
                kwargs["q"] = self.q

            result   = _execute_single(svc.users().messages().list(**kwargs))
            messages = result.get("messages", [])
            next_token = result.get("nextPageToken", "")

            if not messages:
                self.data_fetched.emit([], next_token)
                return

            # 배치로 메타데이터 일괄 조회
            # message id 는 hex 문자열 — 배치 ID로 안전
            mails_dict: dict[str, dict] = {}

            def _cb(request_id, response, exception):
                if exception is None and response:
                    mails_dict[request_id] = _parse_metadata(response)
                else:
                    logger.warning(f"Mail metadata failed [{request_id}]: {exception}")

            req_map = {
                msg["id"]: svc.users().messages().get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                for msg in messages
            }
            _execute_batch_chunks(svc, req_map, _cb)

            # 원래 순서 보전
            mails = [mails_dict[msg["id"]] for msg in messages if msg["id"] in mails_dict]
            self.data_fetched.emit(mails, next_token)
        except Exception as e:
            logger.error(f"FetchMailList error: {e}", exc_info=True)
            self.error.emit(str(e))


class FetchMailDetailWorker(_BaseGmailWorker):
    """단일 메일 전체 내용 조회 (HTML 본문 포함)."""
    data_fetched = Signal(dict)

    def __init__(self, message_id: str):
        super().__init__()
        self.message_id = message_id

    def run(self):
        try:
            svc = self._service()
            detail = svc.users().messages().get(
                userId="me",
                id=self.message_id,
                format="full",
            ).execute()
            mail = _parse_full(detail)
            self.data_fetched.emit(mail)
        except Exception as e:
            logger.error(f"FetchMailDetail error: {e}", exc_info=True)
            self.error.emit(str(e))


class MarkReadWorker(_BaseGmailWorker):
    """UNREAD 라벨 제거."""
    success = Signal(str)

    def __init__(self, message_id: str):
        super().__init__()
        self.message_id = message_id

    def run(self):
        try:
            svc = self._service()
            svc.users().messages().modify(
                userId="me",
                id=self.message_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
            self.success.emit(self.message_id)
        except Exception as e:
            logger.error(f"MarkRead error: {e}", exc_info=True)
            self.error.emit(str(e))


class MarkAllReadWorker(_BaseGmailWorker):
    """선택 라벨의 모든 미읽 메일을 한 번에 읽음 처리."""
    success = Signal(int)   # 처리된 메일 수

    def __init__(self, label_id: str):
        super().__init__()
        self.label_id = label_id

    def run(self):
        try:
            svc = self._service()
            all_ids: list[str] = []
            page_token = None
            while True:
                kwargs: dict = dict(
                    userId="me",
                    labelIds=[self.label_id, "UNREAD"],
                    maxResults=500,
                    fields="messages/id,nextPageToken",
                )
                if page_token:
                    kwargs["pageToken"] = page_token
                result = svc.users().messages().list(**kwargs).execute()
                msgs = result.get("messages", [])
                all_ids.extend(msg["id"] for msg in msgs)
                page_token = result.get("nextPageToken")
                if not page_token or not msgs:
                    break

            if not all_ids:
                self.success.emit(0)
                return

            # batchModify — 最大 1000 件ずつ
            for start in range(0, len(all_ids), 1000):
                chunk = all_ids[start:start + 1000]
                svc.users().messages().batchModify(
                    userId="me",
                    body={"ids": chunk, "removeLabelIds": ["UNREAD"]},
                ).execute()

            self.success.emit(len(all_ids))
        except Exception as e:
            logger.error(f"MarkAllRead error: {e}", exc_info=True)
            self.error.emit(str(e))


class BatchModifyWorker(_BaseGmailWorker):
    """다중 메일 일괄 수정 — read/archive/delete/label 변경 등 범용."""
    success = Signal(int)   # 처리된 메일 수

    def __init__(self, message_ids: list, *,
                 add_labels: list | None = None,
                 remove_labels: list | None = None):
        super().__init__()
        self.message_ids = list(message_ids)
        self.add_labels    = list(add_labels or [])
        self.remove_labels = list(remove_labels or [])

    def run(self):
        if not self.message_ids:
            self.success.emit(0); return
        try:
            svc = self._service()
            body = {"ids": [], "addLabelIds": self.add_labels,
                    "removeLabelIds": self.remove_labels}
            for start in range(0, len(self.message_ids), 1000):
                body["ids"] = self.message_ids[start:start + 1000]
                svc.users().messages().batchModify(userId="me", body=body).execute()
            self.success.emit(len(self.message_ids))
        except Exception as e:
            logger.error(f"BatchModify error: {e}", exc_info=True)
            self.error.emit(str(e))


class BatchDeleteWorker(_BaseGmailWorker):
    """다중 메일 휴지통 이동 — TRASH 라벨 추가."""
    success = Signal(int)

    def __init__(self, message_ids: list):
        super().__init__()
        self.message_ids = list(message_ids)

    def run(self):
        if not self.message_ids:
            self.success.emit(0); return
        try:
            svc = self._service()
            for start in range(0, len(self.message_ids), 1000):
                chunk = self.message_ids[start:start + 1000]
                svc.users().messages().batchModify(
                    userId="me",
                    body={"ids": chunk,
                          "addLabelIds": ["TRASH"],
                          "removeLabelIds": ["INBOX"]},
                ).execute()
            self.success.emit(len(self.message_ids))
        except Exception as e:
            logger.error(f"BatchDelete error: {e}", exc_info=True)
            self.error.emit(str(e))


class PollNewMailWorker(_BaseGmailWorker):
    """
    경량 폴링 Worker — 배치로 알람 라벨의 미읽 수 확인.
    증가 시 new_mail 시그널 발행.
    """
    new_mail = Signal(str, int)   # (label_name, unread_count)

    def __init__(self, label_ids: list, prev_counts: dict):
        super().__init__()
        self.label_ids   = label_ids
        self.prev_counts = dict(prev_counts)

    def run(self):
        try:
            svc = self._service()
            results: dict[str, dict] = {}

            def _cb(request_id, response, exception):
                if exception is None and response:
                    results[request_id] = response
                else:
                    logger.warning(f"Poll label [{request_id}]: {exception}")

            req_map = {
                lid: svc.users().labels().get(userId="me", id=lid)
                for lid in self.label_ids
            }
            _execute_batch_chunks(svc, req_map, _cb)

            for label_id, detail in results.items():
                current = detail.get("messagesUnread", 0)
                prev    = self.prev_counts.get(label_id, 0)
                if current > prev:
                    self.new_mail.emit(detail.get("name", label_id), current)
        except Exception as e:
            logger.error(f"PollNewMail error: {e}", exc_info=True)
            self.error.emit(str(e))


# ── 파싱 헬퍼 ────────────────────────────────────────────────────────────────

def _get_header(headers: list, name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _parse_metadata(msg: dict) -> dict:
    headers   = msg.get("payload", {}).get("headers", [])
    label_ids = msg.get("labelIds", [])
    return {
        "id":        msg.get("id", ""),
        "thread_id": msg.get("threadId", ""),
        "snippet":   msg.get("snippet", ""),
        "from":      _get_header(headers, "From"),
        "subject":   _get_header(headers, "Subject") or "(件名なし)",
        "date":      _get_header(headers, "Date"),
        "is_unread":  "UNREAD"  in label_ids,
        "is_starred": "STARRED" in label_ids,
        "label_ids":  label_ids,
    }


def _decode_b64(data: str) -> bytes:
    """base64url → bytes (パディング補正付き)"""
    data = data.replace("-", "+").replace("_", "/")
    pad  = 4 - len(data) % 4
    if pad != 4:
        data += "=" * pad
    return base64.b64decode(data)


def _extract_body(payload: dict) -> tuple:
    """MIME ペイロードから (html_body, plain_body) を再帰抽出。"""
    mime       = payload.get("mimeType", "")
    html_body  = ""
    plain_body = ""

    if mime.startswith("multipart/"):
        for part in payload.get("parts", []):
            h, p = _extract_body(part)
            if h: html_body  = html_body  or h
            if p: plain_body = plain_body or p
    elif mime == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            try:
                html_body = _decode_b64(data).decode("utf-8", errors="replace")
            except Exception:
                pass
    elif mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            try:
                plain_body = _decode_b64(data).decode("utf-8", errors="replace")
            except Exception:
                pass

    return html_body, plain_body


def _extract_attachments(payload: dict) -> list[dict]:
    """MIME 페이로드에서 첨부 파일 메타 (filename, size, mime, part_id) 추출."""
    out: list[dict] = []
    def _walk(p: dict):
        fn = (p.get("filename") or "").strip()
        body = p.get("body", {}) or {}
        att_id = body.get("attachmentId")
        if fn and att_id:
            out.append({
                "filename":      fn,
                "mime":          p.get("mimeType", ""),
                "size":          body.get("size", 0),
                "attachment_id": att_id,
                "part_id":       p.get("partId", ""),
            })
        for child in p.get("parts", []) or []:
            _walk(child)
    _walk(payload)
    return out


def _parse_full(msg: dict) -> dict:
    base = _parse_metadata(msg)
    payload   = msg.get("payload", {})
    html_body, plain_body = _extract_body(payload)

    if not html_body and plain_body:
        import html as html_mod
        html_body = (
            f"<pre style='white-space:pre-wrap;font-family:sans-serif'>"
            f"{html_mod.escape(plain_body)}</pre>"
        )
    elif not html_body:
        html_body = "<p style='color:#888'>(本文なし)</p>"

    base["body_html"] = html_body
    base["attachments"] = _extract_attachments(payload)
    return base
