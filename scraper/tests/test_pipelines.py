from decimal import Decimal

import pytest
from scrapy.exceptions import DropItem

from scrapesearch.items import BookItem
from scrapesearch.pipelines import CleanBookPipeline, MySQLUpsertPipeline


def raw_book(**overrides):
    fields = dict(
        url="https://books.toscrape.com/catalogue/x_1/index.html",
        title="  A Light in\n the Attic ",
        price="£51.77",
        rating="star-rating Three",
        availability="In stock (22 available)",
        category=" Poetry ",
        description="Poems. ...more",
        image_url="https://books.toscrape.com/media/x.jpg",
    )
    fields.update(overrides)
    return BookItem(**fields)


# ---------- CleanBookPipeline ----------

def test_clean_pipeline_converts_types():
    item = CleanBookPipeline().process_item(raw_book())

    assert item["title"] == "A Light in the Attic"
    assert item["price"] == Decimal("51.77")
    assert item["rating"] == 3
    assert item["availability"] == 22
    assert item["category"] == "Poetry"
    assert item["description"] == "Poems."


@pytest.mark.parametrize("field", ["title", "price", "category"])
def test_clean_pipeline_drops_items_missing_required_fields(field):
    with pytest.raises(DropItem):
        CleanBookPipeline().process_item(raw_book(**{field: None}))


def test_clean_pipeline_drops_unparseable_price():
    with pytest.raises(DropItem, match="unparseable price"):
        CleanBookPipeline().process_item(raw_book(price="call us"))


# ---------- MySQLUpsertPipeline (with a fake DB, no MySQL needed) ----------

class FakeCursor:
    def __init__(self, rowcount):
        self.rowcount = rowcount
        self.executed = []

    def execute(self, sql, params):
        self.executed.append((sql, params))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConnection:
    def __init__(self, rowcount):
        self.cursor_obj = FakeCursor(rowcount)

    def cursor(self):
        return self.cursor_obj


class FakeStats:
    def __init__(self):
        self.values = {}

    def inc_value(self, key):
        self.values[key] = self.values.get(key, 0) + 1


@pytest.mark.parametrize("rowcount, outcome", [(1, "inserted"), (2, "updated"), (0, "unchanged")])
def test_upsert_pipeline_counts_mysql_outcomes(rowcount, outcome):
    stats = FakeStats()
    pipeline = MySQLUpsertPipeline(stats)
    pipeline.conn = FakeConnection(rowcount)
    item = CleanBookPipeline().process_item(raw_book())

    returned = pipeline.process_item(item)

    assert returned is item  # pipelines must pass the item on
    assert stats.values == {f"mysql/books_{outcome}": 1}
    sql, params = pipeline.conn.cursor_obj.executed[0]
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert params["url"] == item["url"] and params["price"] == Decimal("51.77")
