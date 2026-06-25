"""Load a curriculum from a JSON data file (frequency-ordered).

A curriculum is just data: harness/curricula/<lang>.json is a list of item dicts.
Falls back to the small hand-written demo curriculum if no data file is present,
so the system runs before the real content is generated.
"""
from __future__ import annotations
import json
import os

from .model import Item

DIR = os.path.join(os.path.dirname(__file__), "curricula")


def _demo(lang_id: str):
    if lang_id == "pt":
        from .brazilian import brazilian_curriculum
        return brazilian_curriculum()
    if lang_id == "ru":
        from .russian import russian_curriculum
        return russian_curriculum()
    raise FileNotFoundError(f"no curriculum for {lang_id!r}")


def load_curriculum(lang_id: str) -> list:
    path = os.path.join(DIR, f"{lang_id}.json")
    if not os.path.exists(path):
        return _demo(lang_id)
    data = json.load(open(path, encoding="utf-8"))
    return [Item(
        id=d["id"], lemma=d["lemma"], kind=d["kind"], difficulty=d["difficulty"],
        interactivity=d.get("interactivity", 1), confusable=tuple(d.get("confusable", [])),
        is_phonological=d.get("is_phonological", False),
        gloss=d.get("gloss", ""), hint=d.get("hint", ""),
    ) for d in data]
