# Project: ScrapeSearch — Scraping → MySQL → Elasticsearch → Django → React, deployed on a Linux VPS

Paste everything below into Claude Code (or save it as `CLAUDE.md` in an empty repo and say "read CLAUDE.md and start Phase 0").

---

## Context

I'm a final-year CS student preparing for a backend internship interview. The role uses Python/Django, MySQL, Elasticsearch, React, Scrapy, Selenium, Linux, bash, and production servers. I'm building this project to **learn** these tools, not just to have them.

**Rules for you (Claude Code):**
- Work **one phase at a time**. At the end of each phase, stop, summarize what you built, explain the key concepts in 5–10 bullet points (interview-style), and wait for me to say "next".
- Keep code simple and readable. No over-engineering. Comment the non-obvious parts, especially ES queries and bash.
- For Linux/deploy phases, **give me the commands to run myself** with a one-line explanation of each. Don't run them silently.
- Use env vars for all secrets (`.env` + `.env.example`). Never hardcode credentials.
- Only scrape the practice sites listed below. Respect robots.txt, add a download delay, and set a user agent.

## Stack

- **Scraping:** Scrapy (static pages), Selenium with headless Chrome (JS-rendered page)
- **DB:** MySQL 8 (source of truth)
- **Search:** Elasticsearch 8.x, using the official `elasticsearch` Python client directly. Don't use django-elasticsearch-dsl; I want to write raw queries.
- **Backend:** Django + Django REST Framework, served by gunicorn
- **Frontend:** React (Vite) + plain CSS or Tailwind
- **Local infra:** docker-compose (MySQL, Elasticsearch, Kibana)
- **Prod:** Ubuntu VPS, nginx, systemd, cron, bash scripts

## Data sources (scrape-friendly sandboxes)

- `https://books.toscrape.com`: Scrapy spider. Fields: title, price, rating, availability, category, description, url, image_url
- `https://quotes.toscrape.com/js/`: Selenium scraper (JS-rendered). Fields: text, author, tags

## Repo structure

```
scrapesearch/
├── docker-compose.yml
├── .env.example
├── scraper/            # Scrapy project + selenium script
├── backend/            # Django project (apps: catalog, search)
├── frontend/           # React (Vite)
├── deploy/
│   ├── nginx.conf
│   ├── gunicorn.service
│   ├── scraper.cron
│   └── scripts/
│       ├── deploy.sh
│       ├── backup_mysql.sh
│       ├── check_logs.sh
│       └── healthcheck.sh
└── README.md
```

## Phases

### Phase 0: Local infra
- Write a docker-compose file for MySQL 8, Elasticsearch 8 (single-node, security disabled for local, `ES_JAVA_OPTS=-Xms512m -Xmx512m`), and Kibana.
- Add `.env.example`.
- Verify with `curl localhost:9200` and a MySQL connection check.
- Explain: what a node, index, shard and replica are, and why ES needs a heap setting.

### Phase 1: Scrapy → MySQL
- Write a Scrapy spider for books.toscrape.com that crawls all categories and paginates.
- Add an item pipeline that cleans data (price → decimal, rating words → int) and **upserts** into MySQL (dedupe on url).
- Settings: `DOWNLOAD_DELAY`, `ROBOTSTXT_OBEY=True`, `AUTOTHROTTLE`, and logging to a file.
- Explain: spider lifecycle, items, pipelines, middlewares, and how to avoid getting blocked.

### Phase 2: Selenium scraper
- Write a headless Chrome script for quotes.toscrape.com/js that uses explicit waits (`WebDriverWait`, no `time.sleep`), paginates, and saves to MySQL.
- Explain: when to use Selenium vs Scrapy, explicit vs implicit waits, and headless mode.

### Phase 3: Django models + MySQL → ES sync
- Create Django models matching the tables (use `managed=True` and migrations as the schema source going forward).
- Define an **explicit ES mapping** for a `books` index: `text` for title/description with the English analyzer, `keyword` for category, `scaled_float` for price, `integer` for rating, and a `title.keyword` subfield.
- Write a management command `python manage.py sync_es` that does a full reindex using the `bulk` helper, with a `--since` flag for incremental sync based on `updated_at`.
- Explain: mapping, analyzers/tokenizers, text vs keyword, the inverted index, and ways to keep MySQL and ES in sync (bulk reindex, signals, CDC) with their tradeoffs.

### Phase 4: Search API (DRF)
- Build `GET /api/search?q=&category=&min_price=&max_price=&min_rating=&page=`:
  - `bool` query: `must` → `multi_match` on title^3 and description, with `fuzziness: AUTO`; `filter` → term, range
  - Aggregations: category counts and a rating histogram (for facets)
  - Highlighting on title/description
  - Pagination with `from/size`. Add a note and a comment on `search_after` for deep pagination.
- Build `GET /api/suggest?q=`: prefix autocomplete (use `match_phrase_prefix` or a `search_as_you_type` field).
- Build `GET /api/books/<id>`: read from MySQL.
- Add a MySQL `LIKE` search endpoint too, so I can compare speed and relevance in the README.
- Explain: match vs term, must vs filter (scoring vs no scoring, caching), BM25 basics, why ES beats `LIKE '%x%'`.

### Phase 5: React frontend
- Search box with debounced autocomplete, a results list with highlights, sidebar facets from aggregations, a price range filter, and pagination.
- Keep it clean and responsive. No component library needed.

### Phase 6: Tests + quality
- Pytest tests for the pipeline cleaning functions, the search API (mock ES or use a test index), and the sync command.
- Add basic logging throughout.
- Explain what I should say in a code review about the tradeoffs.

### Phase 7: Deploy to Ubuntu VPS (I run the commands)
Walk me step by step through:
1. SSH key setup, creating a non-root user, `ufw` (allow 22, 80, 443 only), and why ES and MySQL ports must **not** be public
2. Installing MySQL, Elasticsearch (heap 512m–1g), Python venv, Node, nginx, and Chrome/chromedriver for Selenium
3. Running Django with gunicorn using a `gunicorn.service` **systemd unit** (restart on failure)
4. nginx: serve the React build as static files, reverse proxy `/api` to gunicorn, gzip, and optionally HTTPS with certbot
5. Cron: run the scraper nightly and `sync_es --since` afterwards, with output going to log files
6. Bash scripts, each with `set -euo pipefail`, usage messages and comments:
   - `deploy.sh`: git pull → pip install → migrate → collectstatic → build frontend → restart service → health check
   - `backup_mysql.sh`: mysqldump plus gzip, keeping the last 7 days
   - `check_logs.sh`: count ERRORs in the last N hours from journalctl and the scraper logs
   - `healthcheck.sh`: curl the API and ES health, and exit non-zero if either is down
7. Debugging drill: break something on purpose (stop ES, fill the disk, wrong permissions) and show me how to diagnose it with `systemctl status`, `journalctl -u`, `df -h`, `free -m`, `lsof -i`, `tail -f`

### Phase 8: README
- Architecture diagram (Mermaid), setup instructions, and a sample ES query with an explanation
- ES vs MySQL `LIKE` comparison (latency and relevance on a few queries)
- A "What I learned" section and a live demo link

## Definition of done
- One command (`docker compose up`) plus the scraper gives a working local search.
- The VPS runs everything behind nginx, and cron scraping + sync works unattended.
- I can explain every file in an interview.
