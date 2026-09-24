"""Make MySQL bump updated_at on every row change, including raw-SQL upserts from the scrapers.

Django's auto_now only runs when Django itself saves a model. The scrapers bypass the ORM, so without
this their upserts would never change updated_at, and `sync_es --since` would miss updated books.
MySQL only bumps the column when some value actually changes, so a no-op upsert leaves it alone.
"""
from django.db import migrations

ON_UPDATE = "ALTER TABLE {table} MODIFY updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"
PLAIN = "ALTER TABLE {table} MODIFY updated_at DATETIME(6) NOT NULL DEFAULT (CURRENT_TIMESTAMP(6))"


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]

    operations = [
        migrations.RunSQL(sql=ON_UPDATE.format(table=t), reverse_sql=PLAIN.format(table=t))
        for t in ("books", "quotes")
    ]
