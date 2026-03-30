from app.services.normalize import clean_text, normalize_time, parse_cn_number


def test_parse_cn_number() -> None:
    assert parse_cn_number("1.2万") == 12000
    assert parse_cn_number("35") == 35
    assert parse_cn_number(None) == 0


def test_clean_text() -> None:
    assert clean_text("  a \n b\t") == "a b"


def test_normalize_time() -> None:
    assert normalize_time("2025-10-01") == "2025-10-01T00:00:00"
