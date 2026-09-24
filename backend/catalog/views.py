"""MySQL-backed endpoints: book detail, and a LIKE search to compare against Elasticsearch."""
import logging
import time

from django.db.models import Q
from rest_framework.decorators import api_view
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response

from .models import Book
from .serializers import BookListSerializer, BookSerializer

logger = logging.getLogger(__name__)

PAGE_SIZE = 20


class BookDetail(RetrieveAPIView):
    """GET /api/books/<id>: read straight from MySQL, the source of truth (ES may lag behind)."""

    queryset = Book.objects.all()
    serializer_class = BookSerializer


@api_view(["GET"])
def sql_search(request):
    """GET /api/search-sql?q=&page=: the naive way, for comparison with /api/search.

    WHERE title LIKE '%q%' OR description LIKE '%q%'
    The leading % means no B-tree index can help: MySQL scans every row and substring-matches the text.
    - No relevance ranking: results come back in id order, a title match is no better than a passing mention.
    - Substring, not words: "art" also matches "heart" and "start".
    - No stemming: "mysteries" doesn't match "mystery".
    - No typo tolerance: "poter" finds nothing.
    """
    q = request.query_params.get("q", "").strip()[:200]
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except ValueError:
        page = 1

    qs = Book.objects.all()
    if q:
        # icontains -> LIKE '%q%' (case-insensitive thanks to the _ci collation)
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

    start = time.perf_counter()
    total = qs.count()
    rows = list(qs.order_by("id")[(page - 1) * PAGE_SIZE: page * PAGE_SIZE])
    took_ms = (time.perf_counter() - start) * 1000
    logger.info("sql search q=%r -> %d rows in %.1fms", q, total, took_ms)

    return Response({
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
        "took_ms": round(took_ms, 2),  # both queries, measured in Django (includes the DB round-trip)
        "sql": str(qs.order_by("id")[:PAGE_SIZE].query),  # show the SQL Django generated
        "results": BookListSerializer(rows, many=True).data,
    })
