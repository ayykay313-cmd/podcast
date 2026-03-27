"""
main.py — Orchestrator for the Crypto Daily Brief pipeline.

Steps:
  1. Collect articles from all RSS feeds
  2. Generate per-source digests + podcast script via Claude
  3. Convert script to MP3 via Google Cloud TTS
  4. Send email with script + MP3 attachment

Usage:
  python src/main.py              # full run
  python src/main.py --dry-run    # skip email send (still generates MP3)
  python src/main.py --skip-tts   # skip TTS, email text only
"""

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

import argparse
import logging
import os
import sys
from datetime import datetime

# Allow running from repo root or src/
sys.path.insert(0, str(Path(__file__).parent))

from collector import collect_all
from processor import process
from tts import script_to_mp3
from emailer import send

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def run(dry_run: bool = False, skip_tts: bool = False) -> None:
    today = datetime.now()
    logger.info(f"=== Crypto Daily Brief — {today.strftime('%A, %B %d, %Y')} ===")

    # 1. Collect
    logger.info("Step 1: Collecting articles")
    articles = collect_all()
    total = sum(len(v) for v in articles.values())
    if total == 0:
        logger.error("No articles collected from any source. Aborting.")
        sys.exit(1)
    logger.info(f"Collected {total} articles total")

    # 2. Process
    logger.info("Step 2: Processing with Claude")
    digests, script = process(articles)
    word_count = len(script.split())
    logger.info(f"Script generated: {word_count} words")

    # 3. TTS
    mp3_path = None
    if not skip_tts:
        logger.info("Step 3: Generating audio via Google TTS")
        output_dir = Path(__file__).parent.parent / "output"
        mp3_path = script_to_mp3(script, output_dir=str(output_dir), date=today)
    else:
        logger.info("Step 3: Skipping TTS (--skip-tts)")

    # 4. Email
    logger.info("Step 4: Sending email")
    send(script, mp3_path=mp3_path, date=today, dry_run=dry_run)

    logger.info("=== Pipeline complete ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crypto Daily Brief pipeline")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate everything but skip sending the email",
    )
    parser.add_argument(
        "--skip-tts",
        action="store_true",
        help="Skip TTS generation, email text script only",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run, skip_tts=args.skip_tts)
