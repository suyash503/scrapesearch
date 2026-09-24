"""Scrapy settings for ScrapeSearch.

Only the settings we change are listed; everything else is a Scrapy default.
Reference: https://docs.scrapy.org/en/latest/topics/settings.html
"""
from pathlib import Path

SCRAPER_DIR = Path(__file__).resolve().parent.parent  # .../scraper

BOT_NAME = "scrapesearch"
SPIDER_MODULES = ["scrapesearch.spiders"]
NEWSPIDER_MODULE = "scrapesearch.spiders"

# --- Politeness -------------------------------------------------------------
# Say honestly who we are instead of pretending to be a browser.
USER_AGENT = "ScrapeSearchBot/1.0 (student learning project; polite crawler)"

# Fetch /robots.txt first and skip any URL it disallows.
ROBOTSTXT_OBEY = True

# At most 2 requests in flight to this site at a time.
CONCURRENT_REQUESTS_PER_DOMAIN = 2

# Minimum wait between requests to the same site. Scrapy randomizes it to 0.5x-1.5x
# (RANDOMIZE_DOWNLOAD_DELAY) so the traffic doesn't look like a metronome.
DOWNLOAD_DELAY = 0.5

# AutoThrottle adjusts the delay based on how fast the server responds: slow responses
# mean a busy server, so it backs off. DOWNLOAD_DELAY stays the floor.
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1.0
AUTOTHROTTLE_MAX_DELAY = 10.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0  # aim for ~1 request in flight on average

# --- Pipelines ----------------------------------------------------------------
# Every item goes through these in ascending order: clean first, then save.
ITEM_PIPELINES = {
    "scrapesearch.pipelines.CleanBookPipeline": 300,
    "scrapesearch.pipelines.MySQLUpsertPipeline": 800,
}

# --- Logging ------------------------------------------------------------------
# Log to a file so cron runs leave a trail. To see output in the terminal while
# developing, run:  scrapy crawl books -s LOG_FILE=
LOG_LEVEL = "INFO"
LOG_DIR = SCRAPER_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = str(LOG_DIR / "scrapy.log")
LOG_FILE_APPEND = True

FEED_EXPORT_ENCODING = "utf-8"
