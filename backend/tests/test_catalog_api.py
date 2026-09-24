"""MySQL-backed endpoints. @pytest.mark.django_db gives each test the (empty) test database,
rolled back afterwards, so tests never see or change the real data."""
from decimal import Decimal

import pytest

from catalog.models import Book

pytestmark = pytest.mark.django_db


def make_book(**overrides):
    fields = dict(url="https://example.com/b/1", title="The Art of War", price=Decimal("10.50"), rating=4,
                  availability=5, category="History", description="Ancient strategy.")
    fields.update(overrides)
    return Book.objects.create(**fields)


def test_book_detail(api):
    book = make_book()
    res = api.get(f"/api/books/{book.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "The Art of War"
    assert data["price"] == 10.5  # a JSON number (COERCE_DECIMAL_TO_STRING=False)


def test_book_detail_404(api):
    assert api.get("/api/books/999999").status_code == 404


def test_sql_search_is_substring_matching(api):
    make_book(url="https://example.com/1", title="The Art of War")
    make_book(url="https://example.com/2", title="Heart of Darkness", description="A river journey.")
    make_book(url="https://example.com/3", title="Dune", description="Desert planet.")

    data = api.get("/api/search-sql", {"q": "art"}).json()

    # LIKE '%art%' also matches "Heart": the false positive ES's word-based matching avoids
    assert sorted(r["title"] for r in data["results"]) == ["Heart of Darkness", "The Art of War"]
    assert "LIKE" in data["sql"]
