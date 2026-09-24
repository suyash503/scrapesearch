"""Elasticsearch-backed endpoints: /api/search and /api/suggest."""
import logging

from django.conf import settings
from elasticsearch import ApiError, TransportError
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .es import get_client
from .queries import MAX_PAGE, PAGE_SIZE, build_search_body, build_suggest_body

logger = logging.getLogger(__name__)

SLOW_QUERY_MS = 500  # searches slower than this are logged as WARNING instead of INFO


class SearchParams(serializers.Serializer):
    """Validates query-string params. Bad input -> 400 with a clear message instead of an ES error."""

    q = serializers.CharField(required=False, allow_blank=True, max_length=200)
    category = serializers.CharField(required=False, allow_blank=True, max_length=100)
    min_price = serializers.DecimalField(required=False, max_digits=8, decimal_places=2, min_value=0)
    max_price = serializers.DecimalField(required=False, max_digits=8, decimal_places=2, min_value=0)
    min_rating = serializers.IntegerField(required=False, min_value=1, max_value=5)
    page = serializers.IntegerField(required=False, default=1, min_value=1, max_value=MAX_PAGE)

    def validate(self, data):
        lo, hi = data.get("min_price"), data.get("max_price")
        if lo is not None and hi is not None and lo > hi:
            raise serializers.ValidationError("min_price must be <= max_price")
        return data


def _es_unavailable(exc):
    logger.error("Elasticsearch request failed: %s", exc)
    return Response({"detail": "Search is temporarily unavailable."}, status=503)


@api_view(["GET"])
def search(request):
    """GET /api/search?q=&category=&min_price=&max_price=&min_rating=&page="""
    params = SearchParams(data=request.query_params)
    params.is_valid(raise_exception=True)
    p = params.validated_data

    body = build_search_body(
        q=(p.get("q") or "").strip() or None,
        category=p.get("category") or None,
        min_price=float(p["min_price"]) if p.get("min_price") is not None else None,
        max_price=float(p["max_price"]) if p.get("max_price") is not None else None,
        min_rating=p.get("min_rating"),
        page=p["page"],
    )
    try:
        res = get_client().search(index=settings.ES_BOOKS_ALIAS, **body)
    except (ApiError, TransportError) as exc:
        return _es_unavailable(exc)

    hits = res["hits"]
    aggs = res["aggregations"]
    # One line per search: what was asked, how many hits, how long ES took. Slow ones stand out in the logs.
    log = logger.warning if res["took"] > SLOW_QUERY_MS else logger.info
    log("search q=%r category=%r page=%d -> %d hits in %dms",
        p.get("q", ""), p.get("category", ""), p["page"], hits["total"]["value"], res["took"])
    return Response({
        "total": hits["total"]["value"],
        "page": p["page"],
        "page_size": PAGE_SIZE,
        "took_ms": res["took"],  # time ES spent on the query (excludes network + Django)
        "results": [
            {
                "id": int(hit["_id"]),
                "score": hit["_score"],
                **hit["_source"],
                "highlight": {
                    "title": hit.get("highlight", {}).get("title", [None])[0],
                    "description": hit.get("highlight", {}).get("description", [None])[0],
                },
            }
            for hit in hits["hits"]
        ],
        # Each facet is a `filter` agg wrapping the real agg (named "values"), see queries.py.
        "facets": {
            "categories": [{"value": b["key"], "count": b["doc_count"]}
                           for b in aggs["categories"]["values"]["buckets"]],
            "ratings": [{"value": int(b["key"]), "count": b["doc_count"]}
                        for b in aggs["ratings"]["values"]["buckets"]],
            "price": {"min": aggs["price"]["values"]["min"], "max": aggs["price"]["values"]["max"]},
        },
    })


@api_view(["GET"])
def suggest(request):
    """GET /api/suggest?q=har -> up to 8 {id, title} matches for autocomplete."""
    prefix = request.query_params.get("q", "").strip()[:100]
    if len(prefix) < 2:
        return Response({"suggestions": []})  # 1 letter matches half the catalogue, not useful
    try:
        res = get_client().search(index=settings.ES_BOOKS_ALIAS, **build_suggest_body(prefix))
    except (ApiError, TransportError) as exc:
        return _es_unavailable(exc)
    return Response({
        "suggestions": [{"id": int(h["_id"]), "title": h["_source"]["title"]} for h in res["hits"]["hits"]],
    })
