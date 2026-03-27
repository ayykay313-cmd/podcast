"""
collector.py — Fetch today's newsletter edition from each source via Gmail IMAP.

Sources:
  - Messari Unqualified Opinions
  - The Defiant Newsletter
  - CoinTelegraph Newsletter

Each source's newsletter is delivered to the podcast Gmail inbox. This module
connects via IMAP, finds today's email from each newsletter sender, and returns
the cleaned plain-text body as an Article.

Prerequisites:
  - Subscribe to each newsletter using the EMAIL_ADDRESS Gmail account
  - Set MESSARI_SENDER, DEFIANT_SENDER, COINTELEGRAPH_SENDER in .env to the
    exact "From" address of each newsletter (check after first email arrives)
"""

import imaplib
import email
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from email.header import decode_header as _decode_header

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
REQUEST_TIMEOUT = 30


@dataclass
class Article:
    source: str
    title: str
    url: str
    published: datetime
    text: str  # plain text body


# ---------------------------------------------------------------------------
# HTML → plain text
# ---------------------------------------------------------------------------

def _html_to_text(html: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "figure", "img", "head"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(lines)


# ---------------------------------------------------------------------------
# Email body extraction
# ---------------------------------------------------------------------------

def _decode_str(value: str) -> str:
    """Decode an RFC2047-encoded header string."""
    parts = _decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _get_body(msg: email.message.Message) -> str:
    """Extract the best available body from an email message (prefer HTML)."""
    html_body = ""
    text_body = ""

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                content = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if ct == "text/html" and not html_body:
                html_body = content
            elif ct == "text/plain" and not text_body:
                text_body = content
    else:
        charset = msg.get_content_charset() or "utf-8"
        try:
            payload = msg.get_payload(decode=True)
            content = payload.decode(charset, errors="replace") if payload else ""
        except Exception:
            content = ""
        if msg.get_content_type() == "text/html":
            html_body = content
        else:
            text_body = content

    if html_body:
        return _html_to_text(html_body)
    return text_body.strip()


# ---------------------------------------------------------------------------
# IMAP fetch
# ---------------------------------------------------------------------------

def _imap_connect() -> imaplib.IMAP4_SSL:
    """Open an authenticated IMAP connection using env credentials."""
    username = os.environ["EMAIL_FROM"]
    password = os.environ["EMAIL_APP_PASSWORD"]
    conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    conn.login(username, password)
    return conn


def fetch_newsletter(source: str, sender: str) -> "Article | None":
    """
    Find today's newsletter from `sender` in the Gmail inbox and return it
    as an Article. Returns None if no matching email is found today.
    """
    today = datetime.now(timezone.utc).strftime("%d-%b-%Y")  # e.g. "27-Mar-2026"
    logger.info(f"Fetching {source} newsletter from inbox (sender: {sender})")

    try:
        conn = _imap_connect()
        conn.select("INBOX")

        # Search: from this sender, received on or after today
        search_criteria = f'(FROM "{sender}" SINCE "{today}")'
        status, data = conn.search(None, search_criteria)

        if status != "OK" or not data[0]:
            logger.warning(f"{source}: no newsletter found today (sender: {sender})")
            conn.logout()
            return None

        # Take the last (most recent) matching message ID
        msg_ids = data[0].split()
        latest_id = msg_ids[-1]

        # Fetch the full message
        status, msg_data = conn.fetch(latest_id, "(RFC822)")
        conn.logout()

        if status != "OK" or not msg_data:
            logger.warning(f"{source}: failed to fetch email body")
            return None

        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        subject = _decode_str(msg.get("Subject", f"{source} Newsletter"))
        body = _get_body(msg)

        if not body:
            logger.warning(f"{source}: email body was empty")
            return None

        logger.info(f"{source}: fetched newsletter '{subject}' ({len(body)} chars)")

        return Article(
            source=source,
            title=subject,
            url="",  # email source — no URL
            published=datetime.now(timezone.utc),
            text=body[:8000],  # cap to keep tokens reasonable
        )

    except Exception as e:
        logger.error(f"{source}: IMAP error — {e}")
        return None


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def collect_all() -> dict[str, list[Article]]:
    """
    Fetch today's newsletter from each source via Gmail IMAP.
    Returns dict keyed by source name, each value is a list of 0 or 1 Article.
    """
    senders = {
        "messari":       os.environ.get("MESSARI_SENDER", ""),
        "defiant":       os.environ.get("DEFIANT_SENDER", ""),
        "cointelegraph": os.environ.get("COINTELEGRAPH_SENDER", ""),
    }

    results = {}
    for source, sender in senders.items():
        if not sender:
            logger.warning(f"{source}: sender address not configured — skipping")
            results[source] = []
            continue
        article = fetch_newsletter(source, sender)
        results[source] = [article] if article else []

    return results


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    data = collect_all()
    for source, articles in data.items():
        if articles:
            a = articles[0]
            print(f"\n=== {source.upper()} ===")
            print(f"  Title: {a.title}")
            print(f"  Body:  {len(a.text)} chars")
            print(f"  Preview: {a.text[:200]}...")
        else:
            print(f"\n=== {source.upper()} — no newsletter found today ===")
