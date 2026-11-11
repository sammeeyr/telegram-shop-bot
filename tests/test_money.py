from shopbot.money import cents_to_decimal_str, format_money, parse_money, parse_signed_money
from shopbot.services.inventory import parse_stock_payload, serialize_items


def test_parse_money():
    assert parse_money("12") == 1200
    assert parse_money("12.5") == 1250
    assert parse_money("12,50") == 1250
    assert parse_money("$1,000.99") == 100099
    assert parse_money("0.005") == 1  # rounds half up
    assert parse_money("0") is None
    assert parse_money("-5") is None
    assert parse_money("abc") is None
    assert parse_money("nan") is None
    assert parse_money("1e20") is None


def test_parse_signed_money():
    assert parse_signed_money("+10") == 1000
    assert parse_signed_money("-2.5") == -250
    assert parse_signed_money("7") == 700
    assert parse_signed_money("-x") is None


def test_formatting():
    assert format_money(123456) == "$1,234.56"
    assert format_money(-5) == "-$0.05"
    assert cents_to_decimal_str(1005) == "10.05"


def test_parse_stock_lines():
    assert parse_stock_payload("KEY-1\r\n\nKEY-2\n  KEY-3  \n") == ["KEY-1", "KEY-2", "KEY-3"]


def test_parse_stock_blocks_roundtrip():
    text = "login: a\npass: 1\n---\nlogin: b\npass: 2\n-----\n"
    items = parse_stock_payload(text)
    assert items == ["login: a\npass: 1", "login: b\npass: 2"]
    assert parse_stock_payload(serialize_items(items)) == items
