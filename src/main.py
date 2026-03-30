"""
main.py — Orchestrator for the Crypto Daily Brief pipeline.

Steps:
  1. Collect newsletters from Gmail
  2. Generate per-source digests + TWO podcast scripts via Claude
  3. Save both scripts as text files to output/
  4. Convert selected script to MP3 via Kokoro TTS
  5. Send email with script + MP3 attachment

Usage:
  python src/main.py                          # full run, briefing format
  python src/main.py --format debate          # use debate format for audio/email
  python src/main.py --dry-run                # skip email send (still generates MP3)
  python src/main.py --skip-tts               # skip TTS, email text only
  python src/main.py --dry-run --skip-tts     # generate scripts only, no audio/email
"""

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

import argparse
import logging
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


def save_scripts(scripts: dict[str, str], output_dir: Path, date: datetime) -> None:
    """Save both script formats as .txt files to output/."""
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = date.strftime("%Y-%m-%d")
    for fmt, text in scripts.items():
        path = output_dir / f"script_{fmt}_{date_str}.txt"
        path.write_text(text, encoding="utf-8")
        logger.info(f"Saved {fmt} script → {path}")


def run(dry_run: bool = False, skip_tts: bool = False, fmt: str = "briefing") -> None:
    today = datetime.now()
    logger.info(f"=== Crypto Daily Brief — {today.strftime('%A, %B %d, %Y')} ===")
    logger.info(f"Format: {fmt}")

    # 1. Collect
    logger.info("Step 1: Collecting newsletters")
    articles = collect_all()
    total = sum(len(v) for v in articles.values())
    if total == 0:
        logger.error("No newsletters collected from any source. Aborting.")
        sys.exit(1)
    logger.info(f"Collected {total} newsletter(s) total")

    # 2. Process — generates both formats
    logger.info("Step 2: Processing with Claude (generating both script formats)")
    digests, scripts = process(articles)
    for name, script in scripts.items():
        logger.info(f"  {name}: {len(script.split())} words")

    # 3. Save both scripts to output/
    output_dir = Path(__file__).parent.parent / "output"
    save_scripts(scripts, output_dir, today)

    # Select the chosen format for audio + email
    if fmt not in scripts:
        logger.error(f"Unknown format '{fmt}'. Falling back to 'briefing'.")
        fmt = "briefing"
    selected_script = scripts[fmt]

    # 4. TTS
    mp3_path = None
    if not skip_tts:
        logger.info(f"Step 3: Generating audio for '{fmt}' format via Kokoro TTS")
        mp3_path = script_to_mp3(selected_script, output_dir=str(output_dir), date=today, fmt=fmt)
    else:
        logger.info("Step 3: Skipping TTS (--skip-tts)")

    # 5. Email
    logger.info("Step 4: Sending email")
    send(selected_script, mp3_path=mp3_path, date=today, dry_run=dry_run, fmt=fmt)

    logger.info("=== Pipeline complete ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crypto Daily Brief pipeline")
    parser.add_argument(
        "--format",
        choices=["briefing", "debate"],
        default="briefing",
        help="Which script format to use for TTS and email (default: briefing)",
    )
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
    run(dry_run=args.dry_run, skip_tts=args.skip_tts, fmt=args.format)
