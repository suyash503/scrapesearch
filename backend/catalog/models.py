"""MySQL tables, the source of truth. Django migrations own the schema.

The scrapers write to these tables with raw SQL (fast bulk upserts, no Django dependency),
so timestamps get *database* defaults (db_default) and not just Python-side ones.
"""
from django.db import models
from django.db.models.functions import Now


class Book(models.Model):
    url = models.URLField(max_length=500, unique=True)  # natural key, the scraper's upsert dedupes on it
    title = models.CharField(max_length=500)
    price = models.DecimalField(max_digits=8, decimal_places=2)  # DECIMAL for money, never float
    rating = models.PositiveSmallIntegerField(null=True, blank=True)  # 1-5 stars
    availability = models.PositiveIntegerField(default=0)  # copies in stock
    category = models.CharField(max_length=100, db_index=True)
    description = models.TextField(null=True, blank=True)
    image_url = models.URLField(max_length=500, null=True, blank=True)

    # auto_now_add / auto_now: set by Django when the ORM saves (e.g. edits in the admin).
    # db_default: set by MySQL when the scraper inserts with raw SQL.
    # updated_at also gets ON UPDATE CURRENT_TIMESTAMP in migration 0002, so raw-SQL upserts bump it too.
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    updated_at = models.DateTimeField(auto_now=True, db_default=Now(), db_index=True)  # indexed for sync_es --since

    class Meta:
        db_table = "books"  # a short, stable name shared with the scraper's SQL
        ordering = ["id"]

    def __str__(self):
        return self.title


class Quote(models.Model):
    # A TEXT column can't be UNIQUE in MySQL, so the scraper dedupes on SHA-256(author + text).
    quote_hash = models.CharField(max_length=64, unique=True)
    text = models.TextField()
    author = models.CharField(max_length=200, db_index=True)
    tags = models.JSONField(default=list)  # ["love", "life"]

    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    updated_at = models.DateTimeField(auto_now=True, db_default=Now(), db_index=True)

    class Meta:
        db_table = "quotes"
        ordering = ["id"]

    def __str__(self):
        return f"{self.author}: {self.text[:50]}"
