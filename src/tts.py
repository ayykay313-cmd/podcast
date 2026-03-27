"""
tts.py — Convert podcast script to MP3 using Kokoro via DeepInfra.

Voice: af_heart (Kokoro-82M, hexgrad/Kokoro-82M on DeepInfra).
Output: output/podcast_YYYY-MM-DD.mp3
"""

import logging
import os
from datetime import datetime
from pathlib import Path

from openai import OpenAI

logger = logging.getLogger(__name__)

MODEL = "hexgrad/Kokoro-82M"
VOICE = "af_heart"
RESPONSE_FORMAT = "mp3"

# DeepInfra has a per-request limit; chunk longer scripts at sentence boundaries.
CHUNK_SIZE = 4500  # characters


def _get_client() -> OpenAI:
    """Build OpenAI-compatible client pointed at DeepInfra."""
    api_key = os.environ.get("DEEPINFRA_API_KEY")
    if not api_key:
        raise ValueError("DEEPINFRA_API_KEY environment variable is not set")
    return OpenAI(
        api_key=api_key,
        base_url="https://api.deepinfra.com/v1/openai",
    )


def _split_into_chunks(text: str, size: int = CHUNK_SIZE) -> list[str]:
    """Split text at sentence boundaries to stay under API limit."""
    if len(text) <= size:
        return [text]

    chunks = []
    while text:
        if len(text) <= size:
            chunks.append(text)
            break
        # Find last sentence end within the limit
        boundary = text.rfind(". ", 0, size)
        if boundary == -1:
            boundary = size
        else:
            boundary += 1  # include the period
        chunks.append(text[:boundary].strip())
        text = text[boundary:].strip()
    return chunks


def _synthesize_chunk(client: OpenAI, text: str) -> bytes:
    """Synthesize one chunk of text and return raw MP3 bytes."""
    response = client.audio.speech.create(
        model=MODEL,
        voice=VOICE,
        input=text,
        response_format=RESPONSE_FORMAT,
    )
    return response.content


def script_to_mp3(script: str, output_dir: str = "output", date: datetime | None = None) -> str:
    """
    Convert script text to MP3. Returns the output file path.
    Handles chunking for scripts exceeding the API's per-request limit.
    """
    date = date or datetime.now()
    filename = f"podcast_{date.strftime('%Y-%m-%d')}.mp3"
    output_path = Path(output_dir) / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Synthesizing speech ({len(script)} chars) → {output_path}")
    client = _get_client()
    chunks = _split_into_chunks(script)
    logger.info(f"Split into {len(chunks)} chunk(s)")

    audio_parts = []
    for i, chunk in enumerate(chunks, 1):
        logger.info(f"  Synthesizing chunk {i}/{len(chunks)} ({len(chunk)} chars)")
        audio_parts.append(_synthesize_chunk(client, chunk))

    # Concatenate MP3 parts (MP3 frames are self-contained, safe to concatenate)
    with open(output_path, "wb") as f:
        for part in audio_parts:
            f.write(part)

    size_kb = output_path.stat().st_size // 1024
    logger.info(f"MP3 written: {output_path} ({size_kb} KB)")
    return str(output_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sample = (
        "Welcome to Crypto Daily Brief. Today in the world of crypto, Bitcoin has surged past "
        "ninety thousand dollars as institutional demand continues to accelerate. "
        "Meanwhile, Ethereum's DeFi ecosystem processed over five billion dollars in volume "
        "in the last twenty-four hours alone. That's a wrap on today's brief — stay sharp, "
        "stay informed, and we'll see you tomorrow."
    )
    path = script_to_mp3(sample, output_dir="../output")
    print(f"Output: {path}")
