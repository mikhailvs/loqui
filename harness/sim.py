"""A simulated learner + a tiny curriculum, so the loop runs end to end and we
can watch the learner model evolve. The sim has a latent `true_skill` per item
that the harness never sees — the harness infers state only from observed
responses, exactly as it would with a person.
"""
from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Optional

from .model import Item
from .moves import Move, MoveType, RETRIEVAL_MOVES


@dataclass
class Response:
    success: Optional[bool] = None       # for retrieval moves
    produced_item: Optional[str] = None  # for chat (free production)
    comprehended: Optional[bool] = None  # for input


def demo_curriculum() -> list:
    """12 items: vocab (incl. a confusable pair), grammar, chunks, one phonological,
    one high-interactivity grammar item that INV-NOVEL must force to be decomposed."""
    return [
        Item("hola", "hola", "vocab", 0.10),
        Item("gracias", "gracias", "vocab", 0.12),
        Item("agua", "agua", "vocab", 0.20, is_phonological=True),
        Item("comer", "comer", "vocab", 0.30),
        Item("beber", "beber", "vocab", 0.32, confusable=("comer",)),
        Item("rojo", "rojo", "vocab", 0.35),
        Item("ser", "ser", "grammar", 0.55),
        Item("estar", "estar", "grammar", 0.58, confusable=("ser",)),
        Item("quiero", "quiero", "chunk", 0.40),
        Item("me_gusta", "me gusta", "chunk", 0.45),
        Item("por_favor", "por favor", "chunk", 0.25),
        Item("subjuntivo", "subjuntivo", "grammar", 0.80, interactivity=3),
    ]


class SimLearner:
    def __init__(self, curriculum, seed: int = 7, aptitude: float = 1.0):
        self.skill = {it.id: 0.0 for it in curriculum}
        self.diff = {it.id: it.difficulty for it in curriculum}
        self.encoded_ids = set()
        self.rng = random.Random(seed)
        self.aptitude = aptitude

    def _bump(self, item_id, amount):
        self.skill[item_id] = min(1.0, self.skill[item_id] + amount * self.aptitude)

    def respond(self, m: Move, lm) -> Response:
        # gentle global forgetting each turn
        for k in self.skill:
            self.skill[k] *= 0.997

        if m.type in RETRIEVAL_MOVES and m.target is not None:
            ease = 0.20 if m.variant == "recognition" else 0.0
            p = 0.12 + self.skill[m.target] * 0.9 - self.diff[m.target] * 0.45 + ease
            p = max(0.02, min(0.98, p))
            success = self.rng.random() < p
            # testing effect: success teaches more, a little more if it was effortful
            self._bump(m.target, 0.09 if success else 0.03)
            return Response(success=success)

        if m.type == MoveType.INTRODUCE and m.target is not None:
            self.skill[m.target] = max(self.skill[m.target], 0.30)
            self.encoded_ids.add(m.target)
            return Response()

        if m.type in (MoveType.INPUT, MoveType.TASK_REPEAT) and m.target is not None:
            self._bump(m.target, 0.11)
            self.encoded_ids.add(m.target)
            return Response(comprehended=True)

        if m.type in (MoveType.RECAST, MoveType.CORRECT, MoveType.EXPLAIN) and m.target is not None:
            self._bump(m.target, 0.13)
            self.encoded_ids.add(m.target)
            return Response()

        if m.type == MoveType.CHAT:
            # free-produce the strongest item the learner is comfortable with
            ready = [i for i in self.encoded_ids if self.skill[i] >= 0.62]
            if ready and self.rng.random() < 0.7:
                produced = max(ready, key=lambda i: self.skill[i])
                self._bump(produced, 0.03)
                return Response(produced_item=produced)
            return Response()

        return Response()
