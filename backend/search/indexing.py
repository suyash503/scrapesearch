"""The `books` index: its explicit mapping, how a Book becomes a document, and reindexing.

Zero-downtime reindex with an alias:
    "books" is an ALIAS, not a real index. A full reindex builds a brand-new index (books_20260923_141500_123456),
    fills it, then atomically moves the alias to it and deletes the old one. Searches never see
    a half-filled or missing index, and a failed reindex leaves the old index serving traffic.
"""
import logging
from datetime import datetime, timezone

from django.conf import settings
from elasticsearch import NotFoundError, helpers

from catalog.models import Book

from .es import get_client

logger = logging.getLogger(__name__)

BOOKS_SETTINGS = {
    "number_of_shards": 1,    # ~1000 small docs: one shard is plenty (aim for 10-50 GB per shard)
    "number_of_replicas": 0,  # single node, a replica could never be placed (health would stay yellow)
}

# Explicit mapping: we decide each field's type instead of letting ES guess from the first document.
# (A guessed mapping can't be changed later without a reindex, and ES guesses strings as text + keyword.)
BOOKS_MAPPINGS = {
    "dynamic": "strict",  # reject documents with fields not listed here, which catches typos in book_to_doc
    "properties": {
        "title": {
            # "text" = analyzed for full-text search. The english analyzer lowercases, removes stop words
            # ("the", "a") and stems ("running" -> "run"), so "run" matches "Running".
            "type": "text",
            "analyzer": "english",
            "fields": {
                # title.keyword: the exact, unanalyzed string. Used for sorting, aggregations, exact match.
                "keyword": {"type": "keyword", "ignore_above": 256},
                # title.suggest: indexed as edge n-grams ("har", "harr", "harry"...) for autocomplete.
                "suggest": {"type": "search_as_you_type"},
            },
        },
        "description": {"type": "text", "analyzer": "english"},
        # keyword = one exact token. Filter with `term`, count with `terms` aggregations (facets).
        "category": {"type": "keyword"},
        # scaled_float stores price * 100 as a long: exact to the penny and compresses well.
        "price": {"type": "scaled_float", "scaling_factor": 100},
        "rating": {"type": "integer"},
        "availability": {"type": "integer"},
        # Stored and returned, but not searchable ("index": false saves disk and indexing time).
        "url": {"type": "keyword", "index": False},
        "image_url": {"type": "keyword", "index": False},
        "updated_at": {"type": "date"},
    },
}


def book_to_doc(book):
    """MySQL row -> ES document (_source). The ES _id is the MySQL primary key, so re-indexing overwrites."""
    return {
        "title": book.title,
        "description": book.description or "",
        "category": book.category,
        "price": float(book.price),
        "rating": book.rating,
        "availability": book.availability,
        "url": book.url,
        "image_url": book.image_url,
        "updated_at": book.updated_at.isoformat(),
    }


def _actions(queryset, index):
    """Generator of bulk actions. .iterator() streams rows from MySQL instead of loading them all into RAM."""
    for book in queryset.iterator(chunk_size=500):
        # "_op_type" defaults to "index" = create or replace, which makes re-running the sync idempotent.
        yield {"_index": index, "_id": book.pk, "_source": book_to_doc(book)}


def _bulk(queryset, index):
    # helpers.bulk batches actions into _bulk requests of chunk_size docs: one HTTP call per
    # 500 books instead of 1000 separate calls. raise_on_error=True raises BulkIndexError listing failures.
    ok, _ = helpers.bulk(get_client(), _actions(queryset, index), chunk_size=500)
    return ok


def alias_targets(alias=None):
    """Names of the concrete indices the alias currently points to ([] if the alias doesn't exist)."""
    try:
        return list(get_client().indices.get_alias(name=alias or settings.ES_BOOKS_ALIAS).keys())
    except NotFoundError:
        return []


def full_reindex():
    """Build a new index from every book, then atomically swap the alias to it. Returns (index, count)."""
    es = get_client()
    alias = settings.ES_BOOKS_ALIAS
    # Microseconds too: with second precision, two reindexes in the same second would collide.
    new_index = f"{alias}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S_%f}"

    # refresh_interval -1: don't make docs searchable during the bulk load. Refreshing every second while
    # writing creates lots of tiny segments. We refresh once at the end instead.
    es.indices.create(
        index=new_index,
        settings={**BOOKS_SETTINGS, "refresh_interval": "-1"},
        mappings=BOOKS_MAPPINGS,
    )
    try:
        count = _bulk(Book.objects.all(), new_index)
        es.indices.put_settings(index=new_index, settings={"refresh_interval": "1s"})
        es.indices.refresh(index=new_index)
    except Exception:
        es.indices.delete(index=new_index)  # don't leave a half-built index lying around
        raise

    old_indices = alias_targets(alias)
    # One update_aliases call = one atomic cluster-state change. There's no moment where
    # "books" points at nothing or at both indices.
    es.indices.update_aliases(actions=[
        *({"remove": {"index": old, "alias": alias}} for old in old_indices),
        {"add": {"index": new_index, "alias": alias}},
    ])
    for old in old_indices:
        es.indices.delete(index=old)

    logger.info("full reindex: %d books into %s (replaced %s)", count, new_index, old_indices or "nothing")
    return new_index, count


def incremental_sync(since):
    """Re-index only books changed since `since`, writing through the alias. Returns the count.

    Limitation: rows DELETED from MySQL aren't removed from ES here. The periodic full reindex cleans those up.
    """
    if not alias_targets():
        raise RuntimeError("alias 'books' doesn't exist yet: run a full `sync_es` first")
    count = _bulk(Book.objects.filter(updated_at__gte=since), settings.ES_BOOKS_ALIAS)
    logger.info("incremental sync: %d books changed since %s", count, since.isoformat())
    return count
