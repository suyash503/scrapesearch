"""Compare Elasticsearch vs MySQL LIKE on relevance and latency. The results go in the README.

    python scripts/compare_search.py              # relevance + latency on the real 1,000 books
    python scripts/compare_search.py --scale 100  # also build a 100x copy (100,000 books) and time both

Latency is measured client-side, the same way for both engines: the full round trip of the query from
Python, median of RUNS runs after one warm-up. The --scale copies (MySQL table `bench_books`,
ES index `bench_books`) are deleted at the end.
"""
import argparse
import os
import statistics
import time
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from elasticsearch import Elasticsearch, helpers

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

QUERIES = ["harry poter", "mystery", "running", "art", "poetry", "the great"]
RUNS = 15


def mysql():
    return pymysql.connect(host=os.environ.get("MYSQL_HOST", "127.0.0.1"), port=int(os.environ.get("MYSQL_PORT", 3306)),
                           user=os.environ["MYSQL_USER"], password=os.environ["MYSQL_PASSWORD"],
                           database=os.environ["MYSQL_DATABASE"], charset="utf8mb4", autocommit=True)


def es():
    return Elasticsearch(os.environ.get("ES_URL", "http://localhost:9200"), request_timeout=60)


def like_search(cur, table, q):
    """The same thing /api/search-sql does: count + first 20 rows, LIKE '%q%' on title and description."""
    pattern = f"%{q}%"
    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE title LIKE %s OR description LIKE %s", (pattern, pattern))
    total = cur.fetchone()[0]
    cur.execute(f"SELECT title FROM {table} WHERE title LIKE %s OR description LIKE %s ORDER BY id LIMIT 20",
                (pattern, pattern))
    return total, [r[0] for r in cur.fetchall()]


def es_search(client, index, q):
    """The core of /api/search (backend/search/queries.py): fuzzy multi_match on title^3 + description
    decides what matches, a non-fuzzy copy adds an exact-match bonus. Exact total, first 20 hits."""
    fields = ["title^3", "description"]
    res = client.search(index=index, size=20, track_total_hits=True, _source=["title"], query={"bool": {
        "must": [{"multi_match": {"query": q, "fields": fields, "fuzziness": "AUTO", "prefix_length": 1,
                                  "minimum_should_match": "2<75%"}}],
        "should": [{"multi_match": {"query": q, "fields": fields, "boost": 2}}],
    }})
    return res["hits"]["total"]["value"], [h["_source"]["title"] for h in res["hits"]["hits"]]


def median_ms(fn):
    fn()  # warm-up: first run pays for cold caches
    samples = []
    for _ in range(RUNS):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.median(samples)


def short(title, n=45):
    return title if len(title) <= n else title[: n - 1] + "…"


def relevance_table(cur, client):
    print("\n### Relevance (1,000 books): total hits and top 3\n")
    print("| Query | MySQL `LIKE` hits | MySQL top 3 (id order) | ES hits | ES top 3 (BM25 score) |")
    print("|---|---:|---|---:|---|")
    for q in QUERIES:
        like_total, like_top = like_search(cur, "books", q)
        es_total, es_top = es_search(client, "books", q)
        fmt = lambda titles: "<br>".join(short(t) for t in titles[:3]) or "(none)"  # noqa: E731
        print(f"| `{q}` | {like_total} | {fmt(like_top)} | {es_total} | {fmt(es_top)} |")


def latency_table(cur, client, table, index, label):
    print(f"\n### Latency, {label} (median of {RUNS} runs, ms)\n")
    print("| Query | MySQL `LIKE` | Elasticsearch |")
    print("|---|---:|---:|")
    for q in QUERIES:
        like_ms = median_ms(lambda: like_search(cur, table, q))
        es_ms = median_ms(lambda: es_search(client, index, q))
        print(f"| `{q}` | {like_ms:.1f} | {es_ms:.1f} |")


def build_scaled_copies(cur, client, factor):
    """bench_books in MySQL and ES: every book repeated `factor` times (unique url/id per copy)."""
    print(f"\n(building {factor}x copies: {factor * 1000:,} rows in MySQL + ES...)", flush=True)
    cur.execute("DROP TABLE IF EXISTS bench_books")
    cur.execute("CREATE TABLE bench_books (id BIGINT PRIMARY KEY, title VARCHAR(500), description LONGTEXT)"
                " DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
    for copy in range(factor):
        cur.execute("INSERT INTO bench_books SELECT id + %s, title, description FROM books", (copy * 100_000,))

    if client.indices.exists(index="bench_books"):
        client.indices.delete(index="bench_books")
    client.indices.create(index="bench_books", settings={"number_of_shards": 1, "number_of_replicas": 0,
                                                         "refresh_interval": "-1"},
                          mappings={"properties": {"title": {"type": "text", "analyzer": "english"},
                                                   "description": {"type": "text", "analyzer": "english"}}})
    cur.execute("SELECT id, title, description FROM bench_books")
    helpers.bulk(client, ({"_index": "bench_books", "_id": i, "_source": {"title": t, "description": d or ""}}
                          for i, t, d in cur.fetchall()), chunk_size=2000)
    client.indices.put_settings(index="bench_books", settings={"refresh_interval": "1s"})
    client.indices.refresh(index="bench_books")
    client.indices.forcemerge(index="bench_books", max_num_segments=1)  # a steady-state index, not mid-bulk-load


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scale", type=int, default=0, help="also benchmark on N copies of the data")
    args = parser.parse_args()

    conn, client = mysql(), es()
    with conn.cursor() as cur:
        relevance_table(cur, client)
        latency_table(cur, client, "books", "books", "1,000 books")
        if args.scale:
            try:
                build_scaled_copies(cur, client, args.scale)
                latency_table(cur, client, "bench_books", "bench_books", f"{args.scale * 1000:,} books")
            finally:
                cur.execute("DROP TABLE IF EXISTS bench_books")
                if client.indices.exists(index="bench_books"):
                    client.indices.delete(index="bench_books")
    conn.close()


if __name__ == "__main__":
    main()
