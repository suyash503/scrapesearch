"""Scrape quotes.toscrape.com/js with headless Chrome and upsert them into MySQL.

Why Selenium here: on this page the quotes are written into the DOM by JavaScript while the page loads.
The raw HTML that Scrapy would download contains zero quotes, so we need a real browser to run the JS.

Run from scraper/ with the venv active:
    python quotes_selenium.py                 # headless, all pages
    python quotes_selenium.py --headed        # show the browser window so you can watch
    python quotes_selenium.py --max-pages 2   # quick test
"""
import argparse
import hashlib
import json
import logging
import sys
import time
from collections import Counter
from urllib import robotparser
from urllib.parse import urljoin

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from scrapesearch import cleaning, db
from scrapesearch.settings import LOG_DIR, USER_AGENT

START_URL = "https://quotes.toscrape.com/js/"
WAIT_TIMEOUT = 10  # seconds an explicit wait keeps polling before raising TimeoutException
PAGE_DELAY = 1.0   # politeness pause between pages (rate limiting, see note in main())

log = logging.getLogger("quotes")

# Only tags can change for an existing quote: text and author are what the hash is made of.
UPSERT_QUOTE_SQL = """
INSERT INTO quotes (quote_hash, text, author, tags)
VALUES (%(quote_hash)s, %(text)s, %(author)s, %(tags)s)
AS new
ON DUPLICATE KEY UPDATE tags = new.tags
"""


def setup_logging():
    """Log to the terminal and to scraper/logs/quotes.log (the file is what you read after a cron run)."""
    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    file_handler = logging.FileHandler(LOG_DIR / "quotes.log", encoding="utf-8")
    console = logging.StreamHandler()
    for handler in (file_handler, console):
        handler.setFormatter(fmt)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def allowed_by_robots(url):
    """Selenium doesn't check robots.txt the way Scrapy does, so we do it ourselves."""
    parser = robotparser.RobotFileParser(urljoin(url, "/robots.txt"))
    parser.read()  # a 404 counts as "no rules", i.e. everything is allowed
    return parser.can_fetch(USER_AGENT, url)


def make_driver(headless=True):
    options = webdriver.ChromeOptions()
    if headless:
        # Full Chrome without a window. "new" headless is the real browser engine, so pages behave
        # exactly as they do on screen (the old headless mode was a separate, subtly different build).
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,900")  # some sites render a mobile layout in a tiny window
    options.add_argument(f"--user-agent={USER_AGENT}")  # same honest UA as the Scrapy spider
    # Don't download images: we only read text, so pages load faster and we use less bandwidth.
    options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})
    # Selenium Manager finds a chromedriver matching the installed Chrome (downloading it if needed).
    return webdriver.Chrome(options=options)


def scrape_page(driver):
    """Wait for the JS-rendered quotes, then read them. Returns a list of dicts."""
    # Explicit wait: poll the DOM (every 0.5s by default) until at least one div.quote exists,
    # or raise TimeoutException after WAIT_TIMEOUT seconds. It returns as soon as the quotes appear,
    # so it's both faster and more reliable than a fixed time.sleep().
    quote_elements = WebDriverWait(driver, WAIT_TIMEOUT).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.quote"))
    )
    quotes = []
    for el in quote_elements:
        quotes.append({
            "text": cleaning.clean_quote_text(el.find_element(By.CSS_SELECTOR, "span.text").text),
            "author": cleaning.clean_text(el.find_element(By.CSS_SELECTOR, "small.author").text),
            "tags": [tag.text for tag in el.find_elements(By.CSS_SELECTOR, "a.tag")],
        })
    return quotes


def go_to_next_page(driver):
    """Click 'Next' and wait until the old page is gone. Returns False on the last page."""
    # find_elements (plural) returns [] instead of raising, which is a clean way to check "is it there?"
    next_links = driver.find_elements(By.CSS_SELECTOR, "li.next a")
    if not next_links:
        return False

    old_quote = driver.find_element(By.CSS_SELECTOR, "div.quote")
    next_links[0].click()
    # The click starts a navigation, but click() can return before the old DOM is torn down.
    # Wait until the old element is detached ("stale"). Otherwise scrape_page's presence check could
    # match the OLD page's quotes and we'd scrape page 1 twice.
    WebDriverWait(driver, WAIT_TIMEOUT).until(EC.staleness_of(old_quote))
    return True


def save_quotes(conn, quotes, counts):
    with conn.cursor() as cur:
        for q in quotes:
            quote_hash = hashlib.sha256(f"{q['author']}\n{q['text']}".encode("utf-8")).hexdigest()
            cur.execute(UPSERT_QUOTE_SQL, {**q, "quote_hash": quote_hash, "tags": json.dumps(q["tags"])})
            # Same affected-rows convention as the books pipeline: 1 = inserted, 2 = updated, 0 = identical.
            counts[{1: "inserted", 2: "updated"}.get(cur.rowcount, "unchanged")] += 1


def parse_args():
    parser = argparse.ArgumentParser(description="Scrape quotes.toscrape.com/js into MySQL.")
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    parser.add_argument("--max-pages", type=int, default=None, help="stop after N pages (default: all)")
    return parser.parse_args()


def main():
    args = parse_args()
    setup_logging()

    if not allowed_by_robots(START_URL):
        log.error("robots.txt disallows %s, not scraping", START_URL)
        return 1

    conn = db.get_connection()
    db.require_tables(conn, "quotes")
    driver = make_driver(headless=not args.headed)
    counts = Counter()
    page = 1
    try:
        driver.get(START_URL)
        while True:
            quotes = scrape_page(driver)
            save_quotes(conn, quotes, counts)
            log.info("page %d: %d quotes (%s)", page, len(quotes), driver.current_url)

            if args.max_pages and page >= args.max_pages:
                break
            # This sleep is rate limiting (be gentle with the server), NOT waiting for the page to load.
            # Every "wait until X is on the page" above is an explicit WebDriverWait.
            time.sleep(PAGE_DELAY)
            if not go_to_next_page(driver):
                break
            page += 1
    except TimeoutException:
        # Save what the browser actually showed. For a headless run it's the only way to "see" the failure.
        shot = LOG_DIR / f"quotes_timeout_page{page}.png"
        driver.save_screenshot(str(shot))
        log.exception("timed out on page %d (%s), screenshot saved to %s", page, driver.current_url, shot)
        return 1
    finally:
        # Always quit, even after an error. Otherwise orphaned Chrome processes pile up, which on a
        # server under cron eventually eats all the RAM.
        driver.quit()
        conn.close()

    log.info("done: %d pages, %d quotes (inserted=%d, updated=%d, unchanged=%d)",
             page, sum(counts.values()), counts["inserted"], counts["updated"], counts["unchanged"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
