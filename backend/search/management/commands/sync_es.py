"""python manage.py sync_es [--since WHEN]

    sync_es                          full reindex into a new index + atomic alias swap
    sync_es --since 26h              only books whose updated_at is in the last 26 hours
    sync_es --since 2026-09-23T00:00 only books updated since that UTC time

Cron runs the scraper nightly and then `sync_es --since 26h` (2h of overlap, so a late or slow run
doesn't leave a gap). Re-indexing a book twice is harmless because the ES _id is the MySQL id.
"""
import re
import time
from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand, CommandError

from search import indexing

UNITS = {"m": "minutes", "h": "hours", "d": "days"}


def parse_since(value):
    """'26h' / '30m' / '7d' (relative to now) or an ISO datetime (UTC if no offset) -> aware datetime."""
    match = re.fullmatch(r"(\d+)([mhd])", value.strip())
    if match:
        amount, unit = match.groups()
        return datetime.now(timezone.utc) - timedelta(**{UNITS[unit]: int(amount)})
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise CommandError(f"--since must look like 26h, 30m, 7d or 2026-09-23T00:00, got {value!r}") from None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class Command(BaseCommand):
    help = "Sync books from MySQL into Elasticsearch (full reindex, or incremental with --since)."

    def add_arguments(self, parser):
        parser.add_argument("--since", help="only books updated since: 26h, 30m, 7d, or an ISO datetime (UTC)")

    def handle(self, *args, since=None, **options):
        start = time.monotonic()
        try:
            if since:
                count = indexing.incremental_sync(parse_since(since))
                summary = f"incremental: {count} books re-indexed"
            else:
                index, count = indexing.full_reindex()
                summary = f"full reindex: {count} books into {index}, alias 'books' now points to it"
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"{summary} ({time.monotonic() - start:.1f}s)"))
