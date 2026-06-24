#!/usr/bin/env python3
"""Text-to-speech for move realization (any target language).

Audio is part of realizing a move. Uses edge-tts neural voices — free, no API key.
The VOICES map below is a convenience for the pt-BR CLI; the voice server selects
the voice per target language via `Lang.voice` (harness/languages.py), passing a
full edge-tts voice name straight through — it does NOT use this map.

  python voice.py "oi" audio/oi.mp3                  # normal speed, default (pt-BR f)
  python voice.py "да" audio/da.mp3 --voice ru-RU-SvetlanaNeural   # any edge-tts voice
"""
from __future__ import annotations
import argparse
import asyncio
import edge_tts

VOICES = {"f": "pt-BR-FranciscaNeural", "m": "pt-BR-AntonioNeural"}


async def _synth(text: str, out: str, voice: str, rate: str) -> None:
    # bound the third-party network call so a hung edge-tts can't freeze a turn
    await asyncio.wait_for(edge_tts.Communicate(text, voice, rate=rate).save(out), timeout=20)


def synth(text: str, out: str, voice: str = "f", rate: str = "+0%") -> str:
    asyncio.run(_synth(text, out, VOICES.get(voice, voice), rate))
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("text")
    p.add_argument("out")
    p.add_argument("--voice", default="f", help="f|m or a full edge-tts voice name")
    p.add_argument("--rate", default="+0%", help='slower e.g. -30 percent')
    a = p.parse_args()
    print(synth(a.text, a.out, a.voice, a.rate))
