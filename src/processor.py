"""
processor.py — Two-step pipeline using the local `claude -p` CLI:
  1. Per-source digest: summarise each source's newsletter into ~200 words
  2. Script generation: produce TWO formats from the same digests
       - "briefing": solo host, Briefing + Hot Take structure
       - "debate":   two hosts (HOST 1 / HOST 2) debate-style

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

def _run_claude(prompt: str, timeout: int = 180) -> str:
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
        parts.append(f"--- Newsletter {i}: {a.title} ---\n{a.text[:3000]}")
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
# Step 2a: Briefing + Hot Take script
# ---------------------------------------------------------------------------

SCRIPT_SYSTEM_BRIEFING = """You are the host of "Crypto Daily Brief" — a sharp, no-fluff daily podcast
for people who already follow crypto and want the signal without the noise.

Write the full spoken script for today's episode. Target: 750-800 words total. No headers,
no bullet points, no stage directions, no labels. Write only what the host speaks out loud.

────────────────────────────────────────────────────────
STRUCTURE
────────────────────────────────────────────────────────

SEGMENT 1 — THE BRIEFING (≈ 500 words)

Cold open: Start with the single most interesting thing from today — no intro, no "welcome",
no "today on the show". Drop the listener straight into the story. The first sentence should
create a reason to keep listening.

Then cover one story from each source in this order:
  • Messari — the analytical or macro angle
  • The Defiant — the DeFi or on-chain angle
  • CoinTelegraph — the market or news angle

For each story: state what happened, include one concrete detail (a number, a name, a date),
then close with a "so what" — why it matters right now, not in the abstract.

End Segment 1 with a single short bridge sentence that sets up The Take.
Example: "Which brings me to the part of today I can't stop thinking about."

SEGMENT 2 — THE TAKE (≈ 200 words)

One bold opinion. Connect today's stories into a single clear thesis. Take a side.
Use "my read is", "I think", "here's what this actually means" — be direct.
Not a summary. Not a hedge. A genuine point of view the listener can agree or argue with.

OUTRO (≈ 50 words)

End with: "That's your Crypto Daily Brief for [today's date].
Stay sharp, stay informed — see you tomorrow."

────────────────────────────────────────────────────────
STYLE RULES — follow all of these
────────────────────────────────────────────────────────

RHYTHM: Vary sentence length deliberately. Short sentences create emphasis.
After a long setup sentence, cut it short. Then expand again.
This is what makes speech feel alive rather than read.

SPECIFICITY: Real numbers over vague language.
"$2.1 billion in 24 hours" beats "significant volume".
"Down 12% since Monday" beats "recent weakness".

TRANSITIONS: Use verbal pivots —
"Now —", "Here's the thing.", "But here's what nobody's saying.",
"What that actually means is...", "Think about it this way."

BANNED PHRASES — never use any of these:
"In today's episode", "Don't forget to subscribe", "Let's dive in",
"Stay tuned", "It's important to note", "In conclusion", "As we can see",
"Welcome to", "Today we will", "First up".

TONE: Confident, dry, occasionally sardonic. Not hype. Not doom.
Sounds like someone who has been in crypto long enough to not be impressed
by the noise, but still finds the signal genuinely interesting.
────────────────────────────────────────────────────────
"""


# ---------------------------------------------------------------------------
# Step 2b: Two Hosts (Debate Style) script
# ---------------------------------------------------------------------------

SCRIPT_SYSTEM_DEBATE = """You are writing the script for "Crypto Daily Brief" — a sharp daily podcast
where two hosts react to the day's crypto news in real conversation.

Write the full spoken script. Target: 750-800 words total. Format every line as either
HOST 1: [spoken text]
HOST 2: [spoken text]
No other text. No stage directions. No headers. Only HOST 1 and HOST 2 lines.

────────────────────────────────────────────────────────
STRUCTURE
────────────────────────────────────────────────────────

COLD OPEN: HOST 1 jumps straight into the most interesting story of the day.
No "welcome", no "today on the show". Start mid-thought.

STORY COVERAGE — cover all 3 sources, in any order that flows naturally:
  • Messari — analytical or macro angle
  • The Defiant — DeFi or on-chain angle
  • CoinTelegraph — market or broader news angle

For each story: one host introduces it, the other responds with a different angle,
pushback, or a follow-up question. Cover 3-5 exchanges per story before moving on.

THE TAKE — both hosts land on a conclusion. They can agree, disagree, or split.
Make it feel like they actually worked it out through the conversation.

OUTRO — HOST 1 closes:
"That's your Crypto Daily Brief for [today's date].
Stay sharp, stay informed — see you tomorrow."

────────────────────────────────────────────────────────
HOST PERSONALITIES — keep these consistent throughout
────────────────────────────────────────────────────────

HOST 1: Analytical lean. Thinks in macro trends, protocol fundamentals, risk.
More likely to be skeptical, ask "but what's the actual driver here?"
Dry humor. Measured. Will say "I'm not convinced" or "that reads more like..."

HOST 2: On-chain data lean. Thinks in flows, user activity, momentum signals.
More willing to be bullish when the data supports it.
More direct. Will say "yeah but look at the numbers" or "the chain doesn't lie."

────────────────────────────────────────────────────────
DIALOGUE RULES — follow all of these
────────────────────────────────────────────────────────

PACING: No monologues. Max 3 sentences before the other host responds.
This keeps it feeling like a real conversation, not a scripted reading.

REACTIONS: Use natural dialogue connectors —
"Right, but —", "Yeah, fair —", "Okay so here's my issue with that:",
"That's the part that surprised me.", "Exactly. And that's why..."

SPECIFICITY: Real numbers over vague language.
"$2.1 billion in 24 hours" beats "significant volume".

BANNED PHRASES — never use any of these:
"In today's episode", "Don't forget to subscribe", "Let's dive in",
"Stay tuned", "It's important to note", "Welcome to", "Today we will",
"As we can see", "In conclusion".

TONE: Smart, fast, confident. No hype. No doom.
Like two people who actually know crypto arguing about what matters today.
────────────────────────────────────────────────────────
"""


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_digests_block(digests: dict[str, str], date_str: str) -> str:
    return (
        f"Today is {date_str}. Here are today's digests from each source:\n\n"
        f"## MESSARI\n{digests.get('messari', 'No content.')}\n\n"
        f"## THE DEFIANT\n{digests.get('defiant', 'No content.')}\n\n"
        f"## COINTELEGRAPH\n{digests.get('cointelegraph', 'No content.')}\n\n"
        "Write the full podcast script now."
    )


def generate_script(
    digests: dict[str, str],
    date: datetime | None = None,
) -> dict[str, str]:
    """
    Generate both script formats from the same source digests.
    Returns {"briefing": str, "debate": str}.
    """
    date = date or datetime.now()
    date_str = date.strftime("%A, %B %d")
    digests_block = _build_digests_block(digests, date_str)

    logger.info("Generating BRIEFING script via claude CLI")
    briefing = _run_claude(f"{SCRIPT_SYSTEM_BRIEFING}\n\n{digests_block}")

    logger.info("Generating DEBATE script via claude CLI")
    debate = _run_claude(f"{SCRIPT_SYSTEM_DEBATE}\n\n{digests_block}")

    return {"briefing": briefing, "debate": debate}


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

def process(articles_by_source: dict[str, list[Article]]) -> tuple[dict[str, str], dict[str, str]]:
    """
    Run the full two-step pipeline.
    Returns (digests_dict, scripts_dict).
    scripts_dict has keys "briefing" and "debate".
    """
    # Step 1: generate all digests
    digests = {}
    for source, articles in articles_by_source.items():
        digests[source] = generate_digest(source, articles)

    # Step 2: generate both scripts
    scripts = generate_script(digests)
    return digests, scripts


if __name__ == "__main__":
    import sys
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from collector import collect_all
    data = collect_all()
    digests, scripts = process(data)

    for fmt, script in scripts.items():
        print(f"\n{'='*60}")
        print(f"FORMAT: {fmt.upper()}")
        print(f"{'='*60}\n")
        print(script)
        print(f"\nWord count: {len(script.split())}")
