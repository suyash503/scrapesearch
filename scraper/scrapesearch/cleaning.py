"""Pure functions that turn raw scraped strings into clean, typed values.

No Scrapy imports here on purpose: plain functions are easy to unit-test (Phase 6).
"""
import re
from decimal import Decimal, InvalidOperation

RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


def clean_text(value):
    """Collapse runs of whitespace/newlines into single spaces and trim. Empty -> None."""
    if value is None:
        return None
    return " ".join(value.split()) or None


def parse_price(raw):
    """'£51.77' -> Decimal('51.77'). Raises ValueError if there's no number in it."""
    number = re.sub(r"[^\d.]", "", raw or "")  # keep digits and the decimal point only
    try:
        return Decimal(number)
    except InvalidOperation:
        raise ValueError(f"unparseable price: {raw!r}") from None


def parse_rating(raw):
    """'star-rating Three' (the CSS class) -> 3. Returns None if no rating word is found."""
    for word in (raw or "").split():
        if word in RATING_WORDS:
            return RATING_WORDS[word]
    return None


def parse_availability(raw):
    """'In stock (22 available)' -> 22. Anything without a count (e.g. 'Out of stock') -> 0."""
    match = re.search(r"(\d+)\s+available", raw or "")
    return int(match.group(1)) if match else 0


def clean_quote_text(raw):
    """'“Be yourself.”' -> 'Be yourself.' (the site wraps every quote in curly quote marks)."""
    text = clean_text(raw)
    return text.strip("“”\"") if text else None


def clean_description(raw):
    """Trim whitespace and drop the '...more' the site appends to long descriptions."""
    text = clean_text(raw)
    if text is None:
        return None
    return re.sub(r"\s*\.\.\.more$", "", text) or None
