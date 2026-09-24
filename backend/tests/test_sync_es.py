"""sync_es: --since parsing (unit) + full and incremental sync against a real, throwaway ES index."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from django.core.management import CommandError, call_command

from catalog.models import Book
from search.management.commands.sync_es import parse_since

# ---------- --since parsing (no ES, no DB) ----------


@pytest.mark.parametrize("value, delta", [
    ("26h", timedelta(hours=26)),
    ("30m", timedelta(minutes=30)),
    ("7d", timedelta(days=7)),
])
def test_parse_since_relative(value, delta):
    expected = datetime.now(timezone.utc) - delta
    assert abs(parse_since(value) - expected) < timedelta(seconds=5)


def test_parse_since_iso_defaults_to_utc():
    assert parse_since("2026-09-23T10:00") == datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc)


def test_parse_since_rejects_garbage():
    with pytest.raises(CommandError):
        parse_since("yesterday")


# ---------- Full + incremental sync against real Elasticsearch ----------


def make_book(n, **overrides):
    fields = dict(url=f"https://example.com/b/{n}", title=f"Book number {n}", price=Decimal("12.34"),
                  rating=3, availability=1, category="Fiction", description="Test book.")
    fields.update(overrides)
    return Book.objects.create(**fields)


def es_docs(es, alias):
    es.indices.refresh(index=alias)
    hits = es.search(index=alias, size=100, query={"match_all": {}})["hits"]["hits"]
    return {int(h["_id"]): h["_source"] for h in hits}


@pytest.mark.es
@pytest.mark.django_db
def test_full_reindex_builds_index_and_points_alias(es_client, es_test_alias):
    books = [make_book(n) for n in range(3)]

    call_command("sync_es")

    docs = es_docs(es_client, es_test_alias)
    assert set(docs) == {b.id for b in books}
    assert docs[books[0].id]["price"] == 12.34
    # the alias points at exactly one concrete, timestamped index with our explicit mapping
    [index] = es_client.indices.get_alias(name=es_test_alias).keys()
    assert index.startswith(f"{es_test_alias}_")
    mapping = es_client.indices.get_mapping(index=index)[index]["mappings"]
    assert mapping["properties"]["title"]["fields"]["keyword"]["type"] == "keyword"
    assert mapping["properties"]["price"]["type"] == "scaled_float"


@pytest.mark.es
@pytest.mark.django_db
def test_second_full_reindex_swaps_alias_and_deletes_old_index(es_client, es_test_alias):
    make_book(1)
    call_command("sync_es")
    [first] = es_client.indices.get_alias(name=es_test_alias).keys()

    make_book(2)
    call_command("sync_es")  # immediately after the first one

    [second] = es_client.indices.get_alias(name=es_test_alias).keys()
    assert second != first
    assert not es_client.indices.exists(index=first)
    assert len(es_docs(es_client, es_test_alias)) == 2


@pytest.mark.es
@pytest.mark.django_db
def test_incremental_sync_only_sends_recent_changes(es_client, es_test_alias):
    old = make_book(1)
    call_command("sync_es")

    # Simulate: `old` was last touched 2 days ago, a new book arrived, and old's price changed in MySQL
    # WITHOUT touching updated_at (update() skips auto_now). --since must skip it.
    Book.objects.filter(pk=old.pk).update(updated_at=datetime.now(timezone.utc) - timedelta(days=2),
                                          price=Decimal("99.99"))
    new = make_book(2)

    call_command("sync_es", since="1h")

    docs = es_docs(es_client, es_test_alias)
    assert set(docs) == {old.id, new.id}
    assert docs[old.id]["price"] == 12.34  # not re-synced: its updated_at is outside the window


@pytest.mark.es
@pytest.mark.django_db
def test_incremental_sync_needs_an_existing_alias(es_client, es_test_alias):
    with pytest.raises(CommandError, match="run a full"):
        call_command("sync_es", since="1h")
