"""Target-language profiles. The harness is language-agnostic — a language is
just a curriculum (data) plus the STT/TTS/brain language settings. Switch the
target to QA the SYSTEM in a language you speak natively (Russian) vs actually
learn one (Portuguese).
"""
from dataclasses import dataclass
from functools import partial
from typing import Callable

from .curricula import load_curriculum


@dataclass(frozen=True)
class Lang:
    id: str
    name: str          # display name
    adjective: str     # used in the brain's "you are a <adjective> tutor" prompt
    whisper: str       # Whisper language code
    voice: str         # edge-tts voice
    flag: str
    curriculum: Callable   # () -> list[Item]


LANGS = {
    "pt": Lang("pt", "Português (BR)", "Brazilian Portuguese", "pt",
               "pt-BR-FranciscaNeural", "🇧🇷", partial(load_curriculum, "pt")),
    "ru": Lang("ru", "Русский", "Russian", "ru",
               "ru-RU-SvetlanaNeural", "🇷🇺", partial(load_curriculum, "ru")),
}
