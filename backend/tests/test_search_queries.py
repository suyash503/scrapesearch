"""Unit tests for the ES query builders: pure dicts in, pure dicts out, no Elasticsearch needed."""
from search.queries import PAGE_SIZE, build_search_body, build_suggest_body


def test_no_text_query_matches_all_and_sorts_by_rating():
    body = build_search_body()
    assert body["query"]["bool"]["must"] == [{"match_all": {}}]
    assert body["sort"][0] == {"rating": "desc"}
    assert "post_filter" not in body


def test_text_query_is_fuzzy_multi_match_with_title_boost():
    body = build_search_body(q="harry poter")
    mm = body["query"]["bool"]["must"][0]["multi_match"]
    assert mm["query"] == "harry poter"
    assert mm["fields"] == ["title^3", "description"]
    assert mm["fuzziness"] == "AUTO"
    assert "sort" not in body  # relevance order when there's text


def test_exact_matches_get_a_bonus_over_fuzzy_ones():
    bool_query = build_search_body(q="mystery")["query"]["bool"]
    [bonus] = bool_query["should"]
    assert "fuzziness" not in bonus["multi_match"]  # exact (well, analyzed) terms only
    assert bonus["multi_match"]["boost"] > 1


def test_price_range_is_a_bool_filter():
    body = build_search_body(min_price=10, max_price=20)
    assert {"range": {"price": {"gte": 10, "lte": 20}}} in body["query"]["bool"]["filter"]


def test_facet_selections_go_to_post_filter_so_other_facet_values_stay_visible():
    body = build_search_body(category="Poetry", min_rating=4)
    category = {"term": {"category": "Poetry"}}
    rating = {"range": {"rating": {"gte": 4}}}

    assert body["query"]["bool"]["filter"] == []            # not in the main query...
    assert body["post_filter"]["bool"]["filter"] == [category, rating]  # ...only applied to the hits
    # each facet's counts apply the OTHER selection, not its own
    assert body["aggs"]["categories"]["filter"] == rating
    assert body["aggs"]["ratings"]["filter"] == category


def test_pagination_offsets():
    assert build_search_body(page=1)["from"] == 0
    assert build_search_body(page=3)["from"] == 2 * PAGE_SIZE
    assert build_search_body(page=3)["size"] == PAGE_SIZE


def test_highlights_are_html_escaped():
    # Without encoder=html, a scraped title containing <script> would come back raw (XSS in the UI).
    assert build_search_body(q="x")["highlight"]["encoder"] == "html"


def test_suggest_requires_every_word():
    mm = build_suggest_body("harry pot")["query"]["multi_match"]
    assert mm["type"] == "bool_prefix"
    assert mm["operator"] == "and"
