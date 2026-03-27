"""
collector.py — Fetch and clean articles from RSS feeds.

Sources:
  - CoinTelegraph: summaries only in RSS; fetches full article body from URL
  - The Defiant: full HTML in <content:encoded>
  - Messari: full HTML in <content:encoded>

Returns a list of Article dicts per source, filtered to the last 24 hours.
"""

import time
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

import feedparser
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

FEEDS = {
    "cointelegraph": "https://cointelegraph.com/rss",
    "defiant": "https://thedefiant.io/feed",
    "messari": "https://messari.io/rss",
}

MAX_ARTICLES_PER_SOURCE = 5
LOOKBACK_HOURS = 24
REQUEST_TIMEOUT = 10
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CryptoPodcastBot/1.0)"}


@dataclass
class Article:
    source: str
    title: str
    url: str
    published: datetime
    text: str  # plain text body


def _html_to_text(html: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    soup = BeautifulSoup(html, "lxml")
    # Remove script/style noise
    for tag in soup(["script", "style", "figure", "img"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    # Collapse whitespace
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(lines)


def _parse_published(entry) -> datetime | None:
    """Return a timezone-aware datetime from an RSS entry, or None."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return None


def _is_recent(dt: datetime | None, hours: int = LOOKBACK_HOURS) -> bool:
    if dt is None:
        return True  # include if we can't determine age
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return dt >= cutoff


def _fetch_full_article(url: str) -> str:
    """Fetch a webpage and return its main text content."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        # Try common article content selectors
        for selector in ["article", "main", '[class*="article"]', '[class*="content"]']:
            container = soup.select_one(selector)
            if container:
                return _html_to_text(str(container))
        return _html_to_text(resp.text)
    except Exception as e:
        logger.warning(f"Failed to fetch full article from {url}: {e}")
        return ""


def _get_content(entry, source: str) -> str:
    """Extract text content from a feed entry."""
    # Prefer content:encoded (full HTML)
    if hasattr(entry, "content") and entry.content:
        return _html_to_text(entry.content[0].value)
    # For CoinTelegraph: only summary available, fetch full article
    if source == "cointelegraph":
        text = _fetch_full_article(entry.link)
        if text:
            return text
    # Fall back to summary
    if hasattr(entry, "summary") and entry.summary:
        return _html_to_text(entry.summary)
    return ""


def fetch_source(name: str, url: str) -> list[Article]:
    """Parse one RSS feed and return recent articles."""
    logger.info(f"Fetching {name} from {url}")
    try:
        feed = feedparser.parse(url)
    except Exception as e:
        logger.error(f"Failed to parse {name} feed: {e}")
        return []

    articles = []
    for entry in feed.entries[:20]:  # check up to 20 entries
        published = _parse_published(entry)
        if not _is_recent(published):
            continue

        text = _get_content(entry, name)
        if not text:
            continue

        articles.append(Article(
            source=name,
            title=getattr(entry, "title", "Untitled"),
            url=getattr(entry, "link", ""),
            published=published or datetime.now(timezone.utc),
            text=text[:4000],  # cap per-article text to keep tokens reasonable
        ))

        if len(articles) >= MAX_ARTICLES_PER_SOURCE:
            break

        # Small delay between article fetches to be polite
        if name == "cointelegraph":
            time.sleep(0.5)

    logger.info(f"{name}: found {len(articles)} recent articles")
    return articles


def collect_all() -> dict[str, list[Article]]:
    """Fetch all sources. Returns dict keyed by source name."""
    results = {}
    for name, url in FEEDS.items():
        results[name] = fetch_source(name, url)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    data = collect_all()
    for source, articles in data.items():
        print(f"\n=== {source.upper()} ({len(articles)} articles) ===")
        for a in articles:
            print(f"  [{a.published.strftime('%H:%M')}] {a.title} (~{len(a.text)} chars)")
