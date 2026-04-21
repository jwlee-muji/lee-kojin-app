"""
app.api.market.imbalance._parse_imbalance_csv 유닛 테스트

외부 API·DB·GUI 없이 순수 CSV 파싱 로직만 검증합니다.
"""
import pytest
from app.api.market.imbalance import _parse_imbalance_csv


def _make_csv(*data_rows: str, header: str = "日付,時刻,価格") -> str:
    """테스트용 CSV 문자열 생성 (앞 3행은 스킵 대상 메타데이터)."""
    lines = ["skip1", "skip2", "skip3", header] + list(data_rows)
    return "\n".join(lines)


class TestParseImbalanceCsv:
    def test_normal_rows_parsed(self):
        csv = _make_csv("2024-01-01,00:30,10.50", "2024-01-01,01:00,11.00")
        headers, rows = _parse_imbalance_csv(csv)
        assert headers == ["日付", "時刻", "価格"]
        assert len(rows) == 2
        assert rows[0] == ["2024-01-01", "00:30", "10.50"]

    def test_duplicate_columns_get_suffix(self):
        csv = _make_csv("v1,v2", header="日付,変更S,変更S")
        headers, _ = _parse_imbalance_csv(csv)
        assert headers == ["日付", "変更S", "変更S_1"]

    def test_triple_duplicate_columns(self):
        csv = _make_csv("1,2,3", header="A,A,A")
        headers, _ = _parse_imbalance_csv(csv)
        assert headers == ["A", "A_1", "A_2"]

    def test_rows_with_wrong_column_count_skipped(self):
        csv = _make_csv("2024-01-01,00:30", "2024-01-01,01:00,11.00")
        _, rows = _parse_imbalance_csv(csv)
        assert len(rows) == 1
        assert rows[0][1] == "01:00"

    def test_empty_rows_skipped(self):
        csv = _make_csv("2024-01-01,00:30,10.50", "", "2024-01-01,01:00,11.00")
        _, rows = _parse_imbalance_csv(csv)
        assert len(rows) == 2

    def test_commas_in_numbers_stripped(self):
        # CSV 규격에서 쉼표 포함 값은 따옴표로 감싸야 한다
        csv = _make_csv('2024-01-01,00:30,"1,234.5"')
        _, rows = _parse_imbalance_csv(csv)
        assert rows[0][2] == "1234.5"

    def test_values_stripped_of_whitespace(self):
        csv = _make_csv("  2024-01-01  , 00:30 , 10.50 ")
        _, rows = _parse_imbalance_csv(csv)
        assert rows[0][0] == "2024-01-01"
        assert rows[0][1] == "00:30"

    def test_bom_stripped_from_first_header(self):
        csv = _make_csv("v", header="\ufeff日付,時刻")
        headers, _ = _parse_imbalance_csv(csv)
        assert headers[0] == "日付"

    def test_missing_header_raises(self):
        # 4행 모두 비어 있어 헤더를 찾을 수 없는 경우
        with pytest.raises(ValueError, match="ヘッダー"):
            _parse_imbalance_csv("\n\n\n")

    def test_no_data_rows_returns_empty_list(self):
        csv = _make_csv()  # 데이터 행 없음
        headers, rows = _parse_imbalance_csv(csv)
        assert headers == ["日付", "時刻", "価格"]
        assert rows == []
