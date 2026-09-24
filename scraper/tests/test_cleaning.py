from decimal import Decimal

import pytest

from scrapesearch import cleaning


@pytest.mark.parametrize("raw, expected", [
    ("£51.77", Decimal("51.77")),
    ("Â£51.77", Decimal("51.77")),     # mis-decoded pound sign, still parses
    ("  £1,234.50 ", Decimal("1234.50")),
    ("10", Decimal("10")),
])
def test_parse_price(raw, expected):
    assert cleaning.parse_price(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "free", "£"])
def test_parse_price_rejects_garbage(raw):
    with pytest.raises(ValueError):
        cleaning.parse_price(raw)


@pytest.mark.parametrize("raw, expected", [
    ("star-rating Three", 3),
    ("star-rating One", 1),
    ("Five star-rating", 5),   # order of classes doesn't matter
    ("star-rating", None),
    ("star-rating Zero", None),
    (None, None),
])
def test_parse_rating(raw, expected):
    assert cleaning.parse_rating(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("In stock (22 available)", 22),
    ("\n    In stock (1 available)\n", 1),
    ("Out of stock", 0),
    ("", 0),
    (None, 0),
])
def test_parse_availability(raw, expected):
    assert cleaning.parse_availability(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("  hello \n  world  ", "hello world"),
    ("   ", None),
    (None, None),
])
def test_clean_text(raw, expected):
    assert cleaning.clean_text(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("A great book. ...more", "A great book."),
    ("A great book...more", "A great book"),
    ("No suffix here.", "No suffix here."),
    ("...more", None),
    (None, None),
])
def test_clean_description(raw, expected):
    assert cleaning.clean_description(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("“Be yourself.”", "Be yourself."),
    ('"Plain quotes"', "Plain quotes"),
    ("  “Spaced”  ", "Spaced"),
    (None, None),
])
def test_clean_quote_text(raw, expected):
    assert cleaning.clean_quote_text(raw) == expected
