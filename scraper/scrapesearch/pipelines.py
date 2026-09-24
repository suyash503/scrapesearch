"""Item pipelines: every item the spider yields passes through these, in ITEM_PIPELINES order."""
import logging

from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem

from scrapesearch import cleaning, db

logger = logging.getLogger(__name__)


class CleanBookPipeline:
    """Turn the raw strings from the page into typed values. Drops items we can't store."""

    REQUIRED = ("url", "title", "price", "category")

    # Recent Scrapy (2.19 here) deprecated the `spider` argument on pipeline methods.
    # If a pipeline needs the spider, keep the crawler from from_crawler() and use crawler.spider.
    def process_item(self, item):
        a = ItemAdapter(item)
        try:
            a["title"] = cleaning.clean_text(a.get("title"))
            a["price"] = cleaning.parse_price(a.get("price"))
            a["rating"] = cleaning.parse_rating(a.get("rating"))
            a["availability"] = cleaning.parse_availability(a.get("availability"))
            a["category"] = cleaning.clean_text(a.get("category"))
            a["description"] = cleaning.clean_description(a.get("description"))
        except ValueError as exc:
            raise DropItem(f"{exc} ({a.get('url')})")

        missing = [field for field in self.REQUIRED if not a.get(field)]
        if missing:
            # DropItem stops this item here; later pipelines never see it. Scrapy logs and counts it.
            raise DropItem(f"missing {missing} ({a.get('url')})")
        return item


# Upsert: insert a new row, or update the existing one if the url (UNIQUE key) is already there.
# `AS new` names the incoming row (MySQL 8.0.19+). It replaces the deprecated VALUES(col) syntax.
UPSERT_BOOK_SQL = """
INSERT INTO books (url, title, price, rating, availability, category, description, image_url)
VALUES (%(url)s, %(title)s, %(price)s, %(rating)s, %(availability)s, %(category)s, %(description)s, %(image_url)s)
AS new
ON DUPLICATE KEY UPDATE
    title = new.title,
    price = new.price,
    rating = new.rating,
    availability = new.availability,
    category = new.category,
    description = new.description,
    image_url = new.image_url
"""


class MySQLUpsertPipeline:
    """Save each cleaned book to MySQL, deduplicating on url."""

    def __init__(self, stats):
        self.stats = stats
        self.conn = None

    @classmethod
    def from_crawler(cls, crawler):
        # Scrapy calls this to build the pipeline. It's how components get access to settings, stats, signals.
        return cls(crawler.stats)

    def open_spider(self):
        self.conn = db.get_connection()
        db.require_tables(self.conn, "books")
        logger.info("Connected to MySQL")

    def close_spider(self):
        if self.conn:
            self.conn.close()

    def process_item(self, item):
        # Note: PyMySQL is blocking, so while this query runs Scrapy's event loop waits.
        # At ~1000 items that's fine. At larger scale you'd batch inserts (executemany every N items)
        # or move the DB writes off the event loop.
        with self.conn.cursor() as cur:
            cur.execute(UPSERT_BOOK_SQL, ItemAdapter(item).asdict())
            affected = cur.rowcount

        # MySQL's affected-rows for an upsert: 1 = inserted, 2 = existing row changed, 0 = identical, nothing written.
        outcome = {1: "inserted", 2: "updated"}.get(affected, "unchanged")
        self.stats.inc_value(f"mysql/books_{outcome}")
        return item
