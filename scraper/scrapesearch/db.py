"""MySQL helpers shared by the Scrapy pipeline and the Selenium script.

The tables themselves are created by Django migrations (backend/catalog/models.py).
The scrapers only read and write rows, so they stay fast and don't depend on Django.
"""
import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]

# Loads .env from the repo root. Variables already set in the environment win,
# so on the server systemd/cron can supply them instead of a file.
load_dotenv(REPO_ROOT / ".env")


def get_connection():
    """Open a connection using MYSQL_* env vars. autocommit=True: each statement is its own transaction."""
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
        charset="utf8mb4",
        autocommit=True,
    )


def require_tables(conn, *tables):
    """Fail fast with a helpful message if migrations haven't been run yet."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name IN %s",
            (tables,),
        )
        found = {row[0] for row in cur.fetchall()}
    missing = sorted(set(tables) - found)
    if missing:
        raise RuntimeError(f"missing tables {missing}: run `python backend/manage.py migrate` first")
