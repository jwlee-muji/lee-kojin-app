"""
AI チャット API 通信モジュール
優先順位: Gemini 3.1 Flash Lite (3キー) → Gemini 2.5 Flash (3キー) → Groq フォールバック
"""
import json
import logging
import urllib.request
import urllib.error
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)

GEMINI_API_URL     = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
GEMINI_LITE_MODEL  = "gemini-3.1-flash-lite-preview"   # 無料枠が多い (プライマリ)
GEMINI_DEFAULT_MODEL = "gemini-2.5-flash"              # フォールバック

GROQ_API_URL       = "https://api.groq.com/openai/v1/chat/completions"
GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"


class RateLimitError(Exception):
    """429 レート制限 / クォータ超過"""
    pass


class ServiceUnavailableError(Exception):
    """503 サービス不可 — このモデルは現在利用不可。別モデルに切替を促す"""
    pass


def get_all_gemini_keys() -> list[str]:
    """有効な Gemini API キー一覧 (空文字除外)"""
    try:
        from app.core._secrets import get_gemini_key1, get_gemini_key2, get_gemini_key3
        return [k for k in (get_gemini_key1(), get_gemini_key2(), get_gemini_key3()) if k]
    except (ImportError, AttributeError):
        logger.warning("_secrets.py が見つかりません。Gemini API キーが設定されていません。")
        return []


def get_builtin_api_key() -> str:
    """後方互換: 最初の Gemini キーを返す"""
    keys = get_all_gemini_keys()
    return keys[0] if keys else ""


def get_builtin_groq_key() -> str:
    """組み込み Groq API キーを返す"""
    try:
        from app.core._secrets import get_groq_key
        return get_groq_key()
    except (ImportError, AttributeError):
        return ""


SYSTEM_PROMPT = (
    "あなたはLEE電力モニターアプリに組み込まれたAIアシスタントです。"
    "日本の電力市場、インバランス単価、電力予備率、LNG価格、気象情報などについて"
    "専門的かつ分かりやすく回答します。"
    "回答は簡潔で実用的にしてください。"
)


class AiChatWorker(QThread):
    """
    3段フォールバックで AI 応答を取得するワーカー
    Gemini Lite (全キー) → Gemini 2.5 Flash (全キー) → Groq
    """
    response_received = Signal(str)
    error             = Signal(str)
    rate_limited      = Signal()

    def __init__(
        self,
        messages: list[dict],
        gemini_keys: list[str],
        groq_key: str,
        model: str = GEMINI_DEFAULT_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ):
        super().__init__()
        self.messages     = messages
        self.gemini_keys  = gemini_keys
        self.groq_key     = groq_key
        self.model        = model or GEMINI_DEFAULT_MODEL
        self.temperature  = max(0.1, min(2.0, float(temperature)))
        self.max_tokens   = max(128, min(8192, int(max_tokens)))

    # ── エントリポイント ──────────────────────────────────────────────────

    def run(self):
        all_rate_limited = True
        last_err = ""

        # Tier 1: Gemini Lite (3.1-flash-lite)
        # Tier 2: Gemini Default (2.5-flash)
        for gemini_model in [GEMINI_LITE_MODEL, self.model]:
            try:
                reply = self._try_gemini_tier(gemini_model)
                self.response_received.emit(reply)
                return
            except ServiceUnavailableError:
                logger.debug(f"{gemini_model}: 503 — skip to next model")
                all_rate_limited = False        # 503 は quota 問題ではない
            except RateLimitError:
                logger.debug(f"{gemini_model}: all keys 429 — next model")
            except Exception as e:
                all_rate_limited = False
                last_err = str(e)
                logger.debug(f"{gemini_model}: error ({e}) — next model")

        # Tier 3: Groq
        if self.groq_key:
            try:
                reply = self._call_groq(self.groq_key)
                self.response_received.emit(reply)
                return
            except RateLimitError:
                logger.debug("Groq: 429")
            except Exception as e:
                all_rate_limited = False
                last_err = str(e)
                logger.error(f"Groq error: {e}")

        if all_rate_limited:
            self.rate_limited.emit()
        else:
            self.error.emit(last_err or "Unknown error")

    # ── Gemini モデルティア (全キーをローテーション) ───────────────────────

    def _try_gemini_tier(self, model: str) -> str:
        """
        指定モデルで全キーを試みる。
        - 503 → ServiceUnavailableError (呼び出し元がモデルをスキップ)
        - 全キー 429 → RateLimitError
        - その他エラー → 次のキーへ
        """
        any_rate_limited = False
        last_exc = RuntimeError("no keys")

        for idx, key in enumerate(self.gemini_keys, 1):
            try:
                return self._call_gemini(key, model)
            except ServiceUnavailableError:
                raise           # 503 はモデル全体の問題、即座に上位へ
            except RateLimitError:
                any_rate_limited = True
                last_exc = RateLimitError()
                logger.debug(f"{model} key{idx}: 429 — rotating")
            except Exception as e:
                last_exc = e
                logger.debug(f"{model} key{idx}: {e} — rotating")

        if any_rate_limited and not isinstance(last_exc, RateLimitError):
            # 一部 429 + 一部その他エラーの場合は RateLimitError として扱う
            raise RateLimitError()
        raise last_exc

    # ── API 呼び出し ─────────────────────────────────────────────────────

    def _call_gemini(self, api_key: str, model: str) -> str:
        url = GEMINI_API_URL.format(model=model, key=api_key)

        contents = []
        for msg in self.messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": contents,
            "generationConfig": {"temperature": self.temperature, "maxOutputTokens": self.max_tokens},
        }

        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RateLimitError()
            if e.code == 503:
                raise ServiceUnavailableError()
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini HTTP {e.code}: {body[:300]}")

        try:
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise RuntimeError(f"Unexpected Gemini response: {result}")

    def _call_groq(self, api_key: str) -> str:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in self.messages:
            role = "user" if msg["role"] == "user" else "assistant"
            messages.append({"role": role, "content": msg["content"]})

        payload = {
            "model": GROQ_DEFAULT_MODEL,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(
            GROQ_API_URL, data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "LEE-Monitor/2.0",
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RateLimitError()
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Groq HTTP {e.code}: {body[:300]}")

        try:
            return result["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            raise RuntimeError(f"Unexpected Groq response: {result}")
