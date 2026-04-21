"""
app.api.user_registry.is_user_registered 유닛 테스트

Google Sheets 연결 없이 등록 판정 로직만 검증합니다.
"""
import pytest
from unittest.mock import patch
from app.api.user_registry import is_user_registered


ADMIN = "jw.lee@shirokumapower.com"


class TestIsUserRegistered:
    # ── 관리자 메일 ──────────────────────────────────────────────────────────

    def test_admin_email_always_true(self):
        assert is_user_registered(ADMIN) is True

    def test_admin_email_uppercase_normalized(self):
        assert is_user_registered(ADMIN.upper()) is True

    def test_admin_email_mixed_case_normalized(self):
        assert is_user_registered("JW.LEE@Shirokumapower.com") is True

    # ── sheet_id 미설정 ──────────────────────────────────────────────────────

    def test_non_admin_no_sheet_id_returns_false(self):
        # lazy import이므로 정의 모듈(app.core.config)에서 패치
        with patch("app.core.config.load_settings", return_value={"sheets_registry_id": ""}):
            assert is_user_registered("other@example.com") is False

    def test_non_admin_missing_sheet_id_key_returns_false(self):
        with patch("app.core.config.load_settings", return_value={}):
            assert is_user_registered("other@example.com") is False

    # ── Sheets 화이트리스트 ──────────────────────────────────────────────────

    def test_registered_user_returns_true(self):
        with patch("app.core.config.load_settings",
                   return_value={"sheets_registry_id": "fake_id"}), \
             patch("app.api.google.sheets.get_registered_users",
                   return_value={"user@example.com", "other@corp.jp"}):
            assert is_user_registered("user@example.com") is True

    def test_unregistered_user_returns_false(self):
        with patch("app.core.config.load_settings",
                   return_value={"sheets_registry_id": "fake_id"}), \
             patch("app.api.google.sheets.get_registered_users",
                   return_value={"other@corp.jp"}):
            assert is_user_registered("unknown@example.com") is False

    def test_registered_user_case_insensitive(self):
        with patch("app.core.config.load_settings",
                   return_value={"sheets_registry_id": "fake_id"}), \
             patch("app.api.google.sheets.get_registered_users",
                   return_value={"user@example.com"}):
            assert is_user_registered("USER@EXAMPLE.COM") is True

    def test_sheets_exception_returns_false(self):
        with patch("app.core.config.load_settings",
                   return_value={"sheets_registry_id": "fake_id"}), \
             patch("app.api.google.sheets.get_registered_users",
                   side_effect=RuntimeError("network error")):
            assert is_user_registered("user@example.com") is False
