"""
app.api.google.auth 토큰 파일 I/O 유닛 테스트

실제 OAuth 인증 없이 토큰 파일 읽기/쓰기 경로만 검증합니다.
"""
import json
import pytest
from unittest.mock import patch, MagicMock


# ── _load_token_json ─────────────────────────────────────────────────────────

class TestLoadTokenJson:
    def _call(self, tmp_path, content: str | None):
        """_load_token_json을 tmp_path 기준으로 호출합니다."""
        from app.api.google import auth as auth_mod
        token_file = tmp_path / "google_token.json"
        if content is not None:
            token_file.write_text(content, encoding="utf-8")
        with patch.object(auth_mod, "_token_path", return_value=token_file):
            return auth_mod._load_token_json()

    def test_returns_none_when_file_missing(self, tmp_path):
        result = self._call(tmp_path, content=None)
        assert result is None

    def test_returns_none_when_file_empty(self, tmp_path):
        result = self._call(tmp_path, content="")
        assert result is None

    def test_returns_none_when_file_only_whitespace(self, tmp_path):
        result = self._call(tmp_path, content="   \n  ")
        assert result is None

    def test_plain_json_returned_as_is(self, tmp_path):
        payload = json.dumps({"token": "abc", "refresh_token": "xyz"})
        result = self._call(tmp_path, content=payload)
        assert result == payload

    def test_dpapi_prefix_triggers_decrypt(self, tmp_path):
        from app.api.google import auth as auth_mod
        token_file = tmp_path / "google_token.json"
        token_file.write_text("__dpapi__:deadbeef", encoding="utf-8")
        # lazy import 경로이므로 정의 모듈(app.core.config)에서 패치
        with patch.object(auth_mod, "_token_path", return_value=token_file), \
             patch("app.core.config.decrypt_secret",
                   return_value='{"token":"decrypted"}') as mock_dec:
            result = auth_mod._load_token_json()
        mock_dec.assert_called_once_with("__dpapi__:deadbeef")
        assert result == '{"token":"decrypted"}'

    def test_dpapi_decrypt_failure_returns_none(self, tmp_path):
        from app.api.google import auth as auth_mod
        token_file = tmp_path / "google_token.json"
        token_file.write_text("__dpapi__:badbytes", encoding="utf-8")
        with patch.object(auth_mod, "_token_path", return_value=token_file), \
             patch("app.core.config.decrypt_secret", return_value=None):
            result = auth_mod._load_token_json()
        assert result is None


# ── _save_token ──────────────────────────────────────────────────────────────

class TestSaveToken:
    def test_returns_false_when_encrypt_fails(self, tmp_path):
        from app.api.google import auth as auth_mod
        creds = MagicMock()
        creds.to_json.return_value = '{"token":"x"}'
        with patch("app.core.config.encrypt_secret", return_value=None), \
             patch.object(auth_mod, "_token_path", return_value=tmp_path / "tok.json"):
            result = auth_mod._save_token(creds)
        assert result is False

    def test_returns_true_and_writes_file_on_success(self, tmp_path):
        from app.api.google import auth as auth_mod
        creds = MagicMock()
        creds.to_json.return_value = '{"token":"x"}'
        token_file = tmp_path / "tok.json"
        with patch("app.core.config.encrypt_secret", return_value="__dpapi__:enc"), \
             patch.object(auth_mod, "_token_path", return_value=token_file):
            result = auth_mod._save_token(creds)
        assert result is True
        assert token_file.read_text(encoding="utf-8") == "__dpapi__:enc"
