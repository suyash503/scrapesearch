"""Elasticsearch query bodies, kept apart from the views so they're easy to read, test and paste into Kibana.

Paste any of these into Kibana Dev Tools as `GET books/_search { ... }` to try them by hand.
"""

PAGE_SIZE = 20
MAX_PAGE = 50  # from + size is capped at 10,000 by ES (index.max_result_window). 50 x 20 = 1000 stays well under.

MATCH_ALL = {"match_all": {}}


def build_search_body(q=None, category=None, min_price=None, max_price=None, min_rating=None, page=1):
    """The main search: full-text query + filters + facets + highlighting + pagination."""
    # bool query: `must` clauses decide relevance (they're scored), `filter` clauses only
    # include/exclude docs (no scoring, and ES caches their results, so they're cheap to repeat).
    must = []
    should = []
    filters = []

    if q:
        must.append({
            "multi_match": {
                "query": q,
                # title^3: a match in the title is worth 3x a match in the description.
                "fields": ["title^3", "description"],
                # Typo tolerance by Levenshtein edit distance. AUTO = 0 edits for 1-2 char terms,
                # 1 edit for 3-5 chars, 2 edits for longer ones. "harry poter" still finds Harry Potter.
                "fuzziness": "AUTO",
                "prefix_length": 1,  # the first letter must match exactly: far fewer candidates, and faster
                # By default the words are OR-ed: "harry poter" matched 219 books (anything with "harry"
                # or a fuzzy cousin like "hardy"). "2<75%" = up to 2 words: all must match,
                # 3+ words: 75% of them must. Recall for long queries, precision for short ones.
                "minimum_should_match": "2<75%",
                # best_fields (default): the score comes from the single best-matching field
                # (+ a little from the others via tie_breaker), so long descriptions don't drown the title.
                "type": "best_fields",
                "tie_breaker": 0.3,
            }
        })
        # Exact-match bonus. `should` clauses are optional when there's a `must`: they don't change WHICH
        # docs match, only add score to those that also match them. Without this, fuzzy matches on short
        # titles could outrank real matches: "mystery" ranked "Misery" (2 edits away) above
        # "The Mysterious Affair at Styles" (an exact match after stemming: mysterious -> mysteri).
        should.append({
            "multi_match": {"query": q, "fields": ["title^3", "description"], "boost": 2},
        })
    else:
        must.append(MATCH_ALL)  # no text: return everything (filters still apply), sorted below

    # Price range narrows everything (hits AND facet counts), so it's a plain bool filter.
    price_range = {}
    if min_price is not None:
        price_range["gte"] = min_price
    if max_price is not None:
        price_range["lte"] = max_price
    if price_range:
        filters.append({"range": {"price": price_range}})

    # Category and rating are *facets* the user clicks in the sidebar. They go in post_filter instead:
    # aggregations are computed from `query`, and post_filter is applied afterwards, to the hits only.
    # If category were in bool.filter, picking "Romance" would shrink the category facet to a single
    # bucket and the user couldn't see or switch to other categories. With post_filter plus the
    # per-facet `filter` aggs below, each facet is counted with every OTHER selection applied, but not
    # its own. Tradeoff: post_filter can't skip docs early like a query filter, so keep it to facets.
    # term = exact match on the un-analyzed keyword field. Never use `term` on a `text` field.
    category_filter = {"term": {"category": category}} if category else None
    rating_filter = {"range": {"rating": {"gte": min_rating}}} if min_rating is not None else None
    facet_filters = [f for f in (category_filter, rating_filter) if f]

    body = {
        "query": {"bool": {"must": must, "should": should, "filter": filters}},
        # Pagination with from/size. Fine for "page 3 of results", but cost grows with depth: to serve
        # from=9000 every shard must collect and sort 9020 hits. For deep paging / infinite scroll use
        # `search_after` (pass the last hit's sort values, e.g. [score, id]) with a point-in-time (PIT)
        # for a consistent snapshot. That's constant cost per page, but no jumping to page N.
        "from": (page - 1) * PAGE_SIZE,
        "size": PAGE_SIZE,
        # Facets. Aggregations run over ALL matching docs (not just this page), in the same request.
        "aggs": {
            # Category counts respect the rating selection, but not the category selection.
            "categories": {
                "filter": rating_filter or MATCH_ALL,
                "aggs": {"values": {"terms": {"field": "category", "size": 50}}},
            },
            # Rating counts respect the category selection, but not the rating selection.
            "ratings": {
                "filter": category_filter or MATCH_ALL,
                "aggs": {"values": {"histogram": {"field": "rating", "interval": 1, "min_doc_count": 0,
                                                  "extended_bounds": {"min": 1, "max": 5}}}},  # always 5 buckets
            },
            # Min/max price of what's currently shown, for the price inputs' placeholders.
            "price": {
                "filter": {"bool": {"filter": facet_filters}},
                "aggs": {"values": {"stats": {"field": "price"}}},
            },
        },
        # Wrap matching words in <mark>...</mark> so the UI can show why a result matched.
        "highlight": {
            # encoder=html: HTML-escape the original text and only add our <mark> tags. Without it, a
            # scraped title containing "<script>" would come back raw and run in the browser (XSS),
            # because the frontend renders highlights as HTML.
            "encoder": "html",
            "pre_tags": ["<mark>"],
            "post_tags": ["</mark>"],
            "fields": {
                "title": {"number_of_fragments": 0},  # 0 = highlight the whole title, not a fragment
                "description": {"fragment_size": 160, "number_of_fragments": 1},
            },
        },
        # Only send the fields the UI needs, not the whole description for 20 results.
        "_source": ["title", "category", "price", "rating", "availability", "image_url"],
        "track_total_hits": True,  # exact total (ES stops counting at 10,000 by default)
    }
    if facet_filters:
        body["post_filter"] = {"bool": {"filter": facet_filters}}
    if not q:
        # Without a text query every score is 1.0, so give the list a meaningful order.
        body["sort"] = [{"rating": "desc"}, {"title.keyword": "asc"}]
    return body


def build_suggest_body(prefix, size=8):
    """Autocomplete on the search_as_you_type field.

    title.suggest is indexed with shingles + edge n-grams (subfields ._2gram, ._3gram, ._index_prefix).
    bool_prefix treats every word as a full term except the last, which is matched as a prefix:
    "harry pot" -> "harry" AND a word starting with "pot".
    """
    return {
        "query": {
            "multi_match": {
                "query": prefix,
                "type": "bool_prefix",
                "fields": ["title.suggest", "title.suggest._2gram", "title.suggest._3gram"],
                # Every word must match. With the default OR, "the ha" matched every title containing "the".
                "operator": "and",
            }
        },
        "size": size,
        "_source": ["title"],
    }
