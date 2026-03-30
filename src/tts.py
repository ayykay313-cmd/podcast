"""
tts.py — Convert podcast script to MP3 using Kokoro via DeepInfra.

Single-host (briefing format):
  - One voice: af_heart
  - Script is split at sentence boundaries and synthesized in chunks

Two-host (debate format):
  - HOST 1 lines → voice: af_heart
  - HOST 2 lines → voice: am_michael
  - Lines are synthesized in order and concatenated into one MP3

Output: output/podcast_{format}_{YYYY-MM-DD}.mp3
"""

import logging
import os
import re
from datetime import datetime
from pathlib import Path

from openai import OpenAI

logger = logging.getLogger(__name__)

MODEL = "hexgrad/Kokoro-82M"
VOICE_HOST1 = "af_heart"   # briefing host / debate HOST 1
VOICE_HOST2 = "am_michael" # debate HOST 2 only
RESPONSE_FORMAT = "mp3"

# DeepInfra has a per-request character limit; chunk longer single-host scripts.
CHUNK_SIZE = 4500  # characters


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def _get_client() -> OpenAI:
    """Build OpenAI-compatible client pointed at DeepInfra."""
    api_key = os.environ.get("DEEPINFRA_API_KEY")
    if not api_key:
        raise ValueError("DEEPINFRA_API_KEY environment variable is not set")
    return OpenAI(
        api_key=api_key,
        base_url="https://api.deepinfra.com/v1/openai",
    )


# ---------------------------------------------------------------------------
# Single-host helpers (briefing format)
# ---------------------------------------------------------------------------

def _split_into_chunks(text: str, size: int = CHUNK_SIZE) -> list[str]:
    """Split text at sentence boundaries to stay under API limit."""
    if len(text) <= size:
        return [text]

    chunks = []
    while text:
        if len(text) <= size:
            chunks.append(text)
            break
        boundary = text.rfind(". ", 0, size)
        if boundary == -1:
            boundary = size
        else:
            boundary += 1  # include the period
        chunks.append(text[:boundary].strip())
        text = text[boundary:].strip()
    return chunks


# ---------------------------------------------------------------------------
# Debate-format helpers
# ---------------------------------------------------------------------------

def _is_debate_format(script: str) -> bool:
    """Return True if the script uses HOST 1 / HOST 2 labels."""
    return bool(re.search(r"^HOST [12]:", script, re.MULTILINE))


def _split_by_speaker(script: str) -> list[tuple[str, str]]:
    """
    Parse a debate script into ordered (voice, text) tuples.
    Each HOST 1 / HOST 2 label maps to its configured voice.
    """
    # Match lines like "HOST 1: ..." or "HOST 2: ..."
    pattern = re.compile(r"^(HOST [12]):\s*(.+?)(?=^HOST [12]:|$)", re.MULTILINE | re.DOTALL)
    segments = []
    for match in pattern.finditer(script):
        speaker = match.group(1).strip()   # "HOST 1" or "HOST 2"
        text = match.group(2).strip()
        if not text:
            continue
        voice = VOICE_HOST1 if speaker == "HOST 1" else VOICE_HOST2
        segments.append((voice, text))
    return segments


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------

def _synthesize(client: OpenAI, text: str, voice: str) -> bytes:
    """Synthesize text with the given voice and return raw MP3 bytes."""
    response = client.audio.speech.create(
        model=MODEL,
        voice=voice,
        input=text,
        response_format=RESPONSE_FORMAT,
    )
    return response.content


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def script_to_mp3(
    script: str,
    output_dir: str = "output",
    date: datetime | None = None,
    fmt: str = "briefing",
) -> str:
    """
    Convert a podcast script to MP3 and return the output file path.

    For debate-format scripts (HOST 1 / HOST 2 labels):
      - Each speaker line is synthesized with its own voice
      - Audio is interleaved in script order

    For briefing-format scripts (plain prose):
      - Script is chunked at sentence boundaries
      - All chunks use VOICE_HOST1
    """
    date = date or datetime.now()
    filename = f"podcast_{fmt}_{date.strftime('%Y-%m-%d')}.mp3"
    output_path = Path(output_dir) / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Synthesizing '{fmt}' script ({len(script)} chars) → {output_path}")
    client = _get_client()

    audio_parts: list[bytes] = []

    if _is_debate_format(script):
        # Two-voice synthesis: one API call per HOST line
        segments = _split_by_speaker(script)
        logger.info(f"Debate format: {len(segments)} speaker segment(s)")
        for i, (voice, text) in enumerate(segments, 1):
            label = "HOST 1" if voice == VOICE_HOST1 else "HOST 2"
            logger.info(f"  Segment {i}/{len(segments)}: {label} ({len(text)} chars)")
            audio_parts.append(_synthesize(client, text, voice))
    else:
        # Single-voice synthesis: chunk at sentence boundaries
        chunks = _split_into_chunks(script)
        logger.info(f"Single-host format: {len(chunks)} chunk(s)")
        for i, chunk in enumerate(chunks, 1):
            logger.info(f"  Chunk {i}/{len(chunks)} ({len(chunk)} chars)")
            audio_parts.append(_synthesize(client, chunk, VOICE_HOST1))

    # MP3 frames are self-contained — safe to concatenate directly
    with open(output_path, "wb") as f:
        for part in audio_parts:
            f.write(part)

    size_kb = output_path.stat().st_size // 1024
    logger.info(f"MP3 written: {output_path} ({size_kb} KB)")
    return str(output_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # Quick briefing test
    briefing_sample = (
        "Bitcoin just crossed ninety-four thousand dollars. Not because of retail — "
        "because three separate ETF filings landed on the same morning. "
        "That's not a coincidence. Here's what that actually means for where we go next. "
        "That's your Crypto Daily Brief for today. Stay sharp, stay informed — see you tomorrow."
    )
    path = script_to_mp3(briefing_sample, output_dir="../output", fmt="briefing")
    print(f"Briefing output: {path}")

    # Quick debate test
    debate_sample = (
        "HOST 1: Bitcoin dominance is at sixty-two percent. That's the highest since 2021.\n"
        "HOST 2: Yeah but look at the stablecoin inflows — that tells a different story.\n"
        "HOST 1: Fair point. If it was pure rotation we wouldn't see USDC supply up eight percent.\n"
        "HOST 2: Exactly. People aren't moving into alts yet. They're waiting.\n"
        "HOST 1: That's your Crypto Daily Brief for today. Stay sharp, stay informed — see you tomorrow."
    )
    path = script_to_mp3(debate_sample, output_dir="../output", fmt="debate")
    print(f"Debate output: {path}")
