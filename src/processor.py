"""
processor.py — Two-step pipeline using the local `claude -p` CLI:
  1. Per-source digest: summarise each source's newsletter into ~200 words
  2. Script generation: combine digests into an 850-950 word podcast script

Uses `claude -p` (Claude Code CLI) instead of the Anthropic API directly.
No ANTHROPIC_API_KEY needed — Claude Code's own session handles the calls.
"""

import logging
import subprocess
from datetime import datetime

from collector import Article

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Claude CLI helper
# ---------------------------------------------------------------------------

def _run_claude(prompt: str, timeout: int = 120) -> str:
    """Run `claude -p <prompt>` and return the response text."""
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {result.stderr[:300]}")
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Step 1: Per-source digest
# ---------------------------------------------------------------------------

DIGEST_SYSTEM = (
    "You are an expert crypto analyst and editor. "
    "Given newsletter content from a single publication, extract the 2-3 most newsworthy stories. "
    "Write a concise ~200-word editorial digest in plain prose — no bullet points, no headers. "
    "Focus on what matters, why it matters, and any notable opinions or analysis. "
    "Do not pad with filler. Write in present tense."
)


def _articles_to_prompt(articles: list[Article]) -> str:
    parts = []
    for i, a in enumerate(articles, 1):
        parts.append(
            f"--- Newsletter {i}: {a.title} ---\n{a.text[:3000]}"
        )
    return "\n\n".join(parts)


def generate_digest(source_name: str, articles: list[Article]) -> str:
    """Summarise one source's newsletter into a ~200-word digest."""
    if not articles:
        return f"No newsletter from {source_name} today."

    prompt = (
        f"{DIGEST_SYSTEM}\n\n"
        f"Publication: {source_name.title()}\n\n"
        + _articles_to_prompt(articles)
    )

    logger.info(f"Generating digest for {source_name}")
    return _run_claude(prompt)


# ---------------------------------------------------------------------------
# Step 2: Script generation
# ---------------------------------------------------------------------------

SCRIPT_SYSTEM = """You are the host of "Crypto Daily Brief", a sharp, conversational morning podcast
for serious crypto followers. Your style sits between Morning Brew's approachability and Bankless's depth.

Write the full podcast script for today's episode. The script must be 850-950 words of spoken prose -
no stage directions, no section headers, no bullet points. Write exactly what the host says.

Structure (follow this order, seamlessly):
1. HOOK (30s): Open with the single most compelling headline of the day. Make it punchy.
2. DEEP DIVE 1 - MESSARI (90s): Expand on Messari's analytical take. Include context and "so what".
3. DEEP DIVE 2 - THE DEFIANT (90s): DeFi and on-chain angle. Concrete numbers when available.
4. DEEP DIVE 3 - COINTELEGRAPH (90s): Market and broader news angle. Keep it crisp.
5. RAPID FIRE (60s): Three to four quick headlines in 1-2 sentences each. Fast pace.
6. TAKEAWAY (30s): One overarching theme that ties today's stories together. Insightful, not generic.
7. OUTRO (15s): Brief sign-off. Keep it consistent: "That's your Crypto Daily Brief for [date].
   Stay sharp, stay informed - we'll see you tomorrow."

Tone: confident, intelligent, never hype-y, occasionally dry wit. Assume the listener knows the basics."""


def generate_script(
    digests: dict[str, str],
    date: datetime | None = None,
) -> str:
    """Combine source digests into a full podcast script."""
    date = date or datetime.now()
    date_str = date.strftime("%A, %B %d")

    prompt = (
        f"{SCRIPT_SYSTEM}\n\n"
        f"Today is {date_str}. Here are today's digests from each source:\n\n"
        f"## MESSARI\n{digests.get('messari', 'No content.')}\n\n"
        f"## THE DEFIANT\n{digests.get('defiant', 'No content.')}\n\n"
        f"## COINTELEGRAPH\n{digests.get('cointelegraph', 'No content.')}\n\n"
        "Write the full podcast script now."
    )

    logger.info("Generating podcast script via claude CLI")
    return _run_claude(prompt, timeout=180)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def process(articles_by_source: dict[str, list[Article]]) -> tuple[dict[str, str], str]:
    """
    Run the full two-step pipeline.
    Returns (digests_dict, final_script).
    """
    # Step 1: generate all digests
    digests = {}
    for source, articles in articles_by_source.items():
        digests[source] = generate_digest(source, articles)

    # Step 2: generate final script
    script = generate_script(digests)
    return digests, script


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from collector import collect_all
    data = collect_all()
    digests, script = process(data)
    print("\n=== SCRIPT ===\n")
    print(script)
    print(f"\nWord count: {len(script.split())}")
