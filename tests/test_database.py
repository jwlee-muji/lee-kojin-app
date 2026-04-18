"""
app.core.database 유닛 테스트

SQLite 연결 없이 순수 유효성 검사 함수만 테스트합니다.
"""
import pytest

from app.core.database import validate_column_name, _validate_table_name


# ── validate_column_name ─────────────────────────────────────────────────────

class TestValidateColumnName:
    def test_simple_english_passes(self):
        assert validate_column_name("date") == "date"

    def test_with_spaces_passes(self):
        assert validate_column_name("date col") == "date col"

    def test_japanese_chars_pass(self):
        assert validate_column_name("日付") == "日付"

    def test_mixed_alphanumeric_passes(self):
        assert validate_column_name("col_123") == "col_123"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="不正なカラム名"):
            validate_column_name("")

    def test_semicolon_raises(self):
        with pytest.raises(ValueError, match="不正なカラム名"):
            validate_column_name("col; DROP TABLE users--")

    def test_single_quote_raises(self):
        with pytest.raises(ValueError, match="不正なカラム名"):
            validate_column_name("col' OR '1'='1")

    def test_double_dash_allowed_in_column_name(self):
        # '--' SQL 주석은 컬럼명이 큰따옴표로 감싸이므로 위험하지 않음
        # 정규식은 이를 허용하며, SQL 인젝션 방어는 쿼리 파라미터 바인딩으로 처리
        assert validate_column_name("col--note") == "col--note"


# ── _validate_table_name ─────────────────────────────────────────────────────

class TestValidateTableName:
    def test_simple_lowercase_passes(self):
        assert _validate_table_name("imbalance_prices") == "imbalance_prices"

    def test_mixed_case_passes(self):
        assert _validate_table_name("HjksCapacity") == "HjksCapacity"

    def test_underscore_prefix_passes(self):
        assert _validate_table_name("_internal_table") == "_internal_table"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="不正なテーブル名"):
            _validate_table_name("")

    def test_starts_with_digit_raises(self):
        with pytest.raises(ValueError, match="不正なテーブル名"):
            _validate_table_name("1table")

    def test_hyphen_raises(self):
        with pytest.raises(ValueError, match="不正なテーブル名"):
            _validate_table_name("my-table")

    def test_semicolon_injection_raises(self):
        with pytest.raises(ValueError, match="不正なテーブル名"):
            _validate_table_name("users; DROP TABLE users--")

    def test_space_raises(self):
        with pytest.raises(ValueError, match="不正なテーブル名"):
            _validate_table_name("my table")

    def test_single_quote_raises(self):
        with pytest.raises(ValueError, match="不正なテーブル名"):
            _validate_table_name("table'name")
