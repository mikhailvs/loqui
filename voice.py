#!/usr/bin/env python3
"""Brazilian Portuguese text-to-speech for move realization.

Audio is part of realizing a move (the design routes audio to phonological
targets). Uses edge-tts neural voices — free, no API key.

  python voice.py "oi" audio/oi.mp3                 # normal speed, female voice
  python voice.py "não" audio/nao_slow.mp3 --rate -30%   # slower, for tricky sounds
  python voice.py "bom dia" audio/x.mp3 --voice m   # male voice (Antônio)
"""
from __future__ import annotations
import argparse
import asyncio
import edge_tts

VOICES = {"f": "pt-BR-FranciscaNeural", "m": "pt-BR-AntonioNeural"}


async def _synth(text: str, out: str, voice: str, rate: str) -> None:
    await edge_tts.Communicate(text, voice, rate=rate).save(out)


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
