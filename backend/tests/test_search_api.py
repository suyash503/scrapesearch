"""API tests for /api/search and /api/suggest with a fake Elasticsearch client (no ES needed)."""
import pytest
from elasticsearch import ConnectionError as ESConnectionError

ES_RESPONSE = {
    "took": 7,
    "hits": {
        "total": {"value": 1, "relation": "eq"},
        "hits": [{
            "_id": "42",
            "_score": 3.2,
            "_source": {"title": "Harry Potter", "category": "Fantasy", "price": 14.74, "rating": 4,
                        "availability": 3, "image_url": "https://example.com/hp.jpg"},
            "highlight": {"title": ["<mark>Harry</mark> Potter"]},
        }],
    },
    "aggregations": {
        "categories": {"doc_count": 1, "values": {"buckets": [{"key": "Fantasy", "doc_count": 1}]}},
        "ratings": {"doc_count": 1, "values": {"buckets": [{"key": float(r), "doc_count": int(r == 4)}
                                                           for r in range(1, 6)]}},
        "price": {"doc_count": 1, "values": {"min": 14.74, "max": 14.74}},
    },
}


def test_search_shapes_the_es_response(api, fake_es):
    es = fake_es(response=ES_RESPONSE)
    res = api.get("/api/search", {"q": "harry", "category": "Fantasy", "page": 2})

    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1 and data["page"] == 2 and data["took_ms"] == 7
    assert data["results"][0] == {
        "id": 42, "score": 3.2, "title": "Harry Potter", "category": "Fantasy", "price": 14.74,
        "rating": 4, "availability": 3, "image_url": "https://example.com/hp.jpg",
        "highlight": {"title": "<mark>Harry</mark> Potter", "description": None},
    }
    assert data["facets"]["categories"] == [{"value": "Fantasy", "count": 1}]
    assert [r["value"] for r in data["facets"]["ratings"]] == [1, 2, 3, 4, 5]
    # and the query we sent to ES
    sent = es.calls[0]
    assert sent["index"] == "books"
    assert sent["from"] == 20
    assert sent["post_filter"]["bool"]["filter"] == [{"term": {"category": "Fantasy"}}]


@pytest.mark.parametrize("params, field", [
    ({"min_rating": 9}, "min_rating"),
    ({"min_price": -1}, "min_price"),
    ({"page": 0}, "page"),
    ({"page": 999}, "page"),
    ({"min_price": "abc"}, "min_price"),
    ({"min_price": 50, "max_price": 10}, "non_field_errors"),
])
def test_search_rejects_bad_params_with_400(api, fake_es, params, field):
    es = fake_es(response=ES_RESPONSE)
    res = api.get("/api/search", params)
    assert res.status_code == 400
    assert field in res.json()
    assert es.calls == []  # never reached Elasticsearch


def test_search_returns_503_when_es_is_down(api, fake_es):
    fake_es(error=ESConnectionError("connection refused"))
    res = api.get("/api/search", {"q": "harry"})
    assert res.status_code == 503
    assert res.json() == {"detail": "Search is temporarily unavailable."}


def test_suggest_returns_titles(api, fake_es):
    es = fake_es(response={"hits": {"hits": [{"_id": "7", "_source": {"title": "Harry Potter"}}]}})
    res = api.get("/api/suggest", {"q": "har"})
    assert res.json() == {"suggestions": [{"id": 7, "title": "Harry Potter"}]}
    assert es.calls[0]["query"]["multi_match"]["query"] == "har"


def test_suggest_skips_es_for_one_character(api, fake_es):
    es = fake_es(response=None)
    assert api.get("/api/suggest", {"q": "h"}).json() == {"suggestions": []}
    assert es.calls == []


def test_health(api):
    assert api.get("/api/health").json() == {"status": "ok"}
