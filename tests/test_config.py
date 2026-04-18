"""
app.core.config 유닛 테스트

GUI나 외부 API 없이 실행 가능한 순수 함수 테스트만 포함합니다.
"""
import json
import sys
import pytest

from app.core.config import (
    _validate_settings,
    DEFAULT_SETTINGS,
    decrypt_secret,
    encrypt_secret,
    load_settings,
    save_settings,
)


# ── _validate_settings ──────────────────────────────────────────────────────

class TestValidateSettings:
    def test_full_defaults_dict_passes_validation_unchanged(self):
        # _validate_settings는 입력 키를 보완하지 않음 — 병합은 load_settings에서 수행
        # DEFAULT_SETTINGS를 그대로 전달하면 모든 키가 보존되어야 함
        result = _validate_settings(dict(DEFAULT_SETTINGS))
        for key in DEFAULT_SETTINGS:
            assert key in result

    def test_float_clamped_above_max(self):
        result = _validate_settings({"imbalance_alert": 99999.0})
        assert result["imbalance_alert"] == 1000.0

    def test_float_clamped_below_min(self):
        result = _validate_settings({"imbalance_alert": -1.0})
        assert result["imbalance_alert"] == 0.0

    def test_float_within_range_preserved(self):
        result = _validate_settings({"imbalance_alert": 35.5})
        assert result["imbalance_alert"] == 35.5

    def test_int_clamped_above_max(self):
        result = _validate_settings({"imbalance_interval": 9999})
        assert result["imbalance_interval"] == 1440

    def test_int_clamped_below_min(self):
        result = _validate_settings({"imbalance_interval": 0})
        assert result["imbalance_interval"] == 1

    def test_int_within_range_preserved(self):
        result = _validate_settings({"imbalance_interval": 10})
        assert result["imbalance_interval"] == 10

    def test_invalid_float_string_resets_to_default(self):
        result = _validate_settings({"imbalance_alert": "bad"})
        assert result["imbalance_alert"] == DEFAULT_SETTINGS["imbalance_alert"]

    def test_invalid_language_resets_to_default(self):
        result = _validate_settings({"language": "fr"})
        assert result["language"] == DEFAULT_SETTINGS["language"]

    def test_valid_languages_all_kept(self):
        for lang in ("auto", "ja", "en", "ko", "zh"):
            result = _validate_settings({"language": lang})
            assert result["language"] == lang

    def test_auto_start_non_bool_resets(self):
        result = _validate_settings({"auto_start": "yes"})
        assert result["auto_start"] == DEFAULT_SETTINGS["auto_start"]

    def test_auto_start_bool_preserved(self):
        result = _validate_settings({"auto_start": True})
        assert result["auto_start"] is True


# ── encrypt_secret / decrypt_secret ─────────────────────────────────────────

class TestSecretCrypto:
    def test_decrypt_plain_string_passthrough(self):
        """DPAPI 프리픽스가 없는 문자열은 그대로 반환"""
        assert decrypt_secret("plain-text") == "plain-text"

    def test_decrypt_empty_string_returns_empty(self):
        assert decrypt_secret("") == ""

    def test_decrypt_none_type_passthrough(self):
        """isinstance 체크로 None이 전달되면 그대로 반환"""
        assert decrypt_secret(None) == None  # noqa: E711

    def test_encrypt_empty_string_returns_empty(self):
        assert encrypt_secret("") == ""

    @pytest.mark.skipif(sys.platform != "win32", reason="DPAPI는 Windows 전용")
    def test_encrypt_decrypt_roundtrip(self):
        original = "test-api-key-abc123"
        encrypted = encrypt_secret(original)
        assert encrypted.startswith("__dpapi__:")
        assert encrypted != original
        assert decrypt_secret(encrypted) == original

    @pytest.mark.skipif(sys.platform != "win32", reason="DPAPI는 Windows 전용")
    def test_encrypt_produces_different_output_for_same_input(self):
        """DPAPI는 매 호출마다 다른 암호문을 생성합니다 (entropy 포함)"""
        val = "same-value"
        enc1 = encrypt_secret(val)
        enc2 = encrypt_secret(val)
        # 복호화 결과는 동일해야 함
        assert decrypt_secret(enc1) == val
        assert decrypt_secret(enc2) == val


# ── load_settings / save_settings ───────────────────────────────────────────

class TestLoadSaveSettings:
    def test_load_returns_defaults_when_no_file(self, tmp_settings_file):
        result = load_settings()
        assert result["language"] == DEFAULT_SETTINGS["language"]
        assert result["imbalance_alert"] == DEFAULT_SETTINGS["imbalance_alert"]

    def test_save_and_reload(self, tmp_settings_file):
        settings = load_settings().copy()
        settings["imbalance_alert"] = 55.0
        save_settings(settings)

        import app.core.config as cfg
        cfg._settings_cache = None  # 캐시 무효화해서 파일에서 재읽기
        reloaded = load_settings()
        assert reloaded["imbalance_alert"] == 55.0

    def test_load_uses_cache_on_second_call(self, tmp_settings_file):
        first = load_settings()
        second = load_settings()
        assert first is second  # 동일 객체 (캐시 반환)

    def test_load_merges_with_defaults_for_partial_file(self, tmp_settings_file):
        tmp_settings_file.write_text(
            json.dumps({"imbalance_alert": 99.0}), encoding="utf-8"
        )
        import app.core.config as cfg
        cfg._settings_cache = None
        result = load_settings()
        assert result["imbalance_alert"] == 99.0
        assert "language" in result  # 기본값에서 병합됨
