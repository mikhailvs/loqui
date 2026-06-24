"""The move set — the action space the arbiter selects from and the LLM realizes."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MoveType(Enum):
    INTRODUCE = "introduce"
    INPUT = "input"          # comprehensible input; variant 'inference'|'structured'
    ELICIT = "elicit"        # production retrieval
    PROBE = "probe"          # recognition retrieval (cheaper)
    PROMPT = "prompt"        # output-WITHHOLDING repair/elicit (default repair)
    RECAST = "recast"        # model correct form, salience-marked
    CORRECT = "correct"      # brief explicit correction, one feature
    EXPLAIN = "explain"      # rationed metalinguistic
    DRILL = "drill"          # form-meaning fluency, double-capped
    REVIEW = "review"        # spaced resurfacing (realized as retrieval for discrete items)
    CHAT = "chat"            # acquisition channel
    TASK_REPEAT = "task_repeat"


# moves that put a retrieval demand on the learner (gated by INV-ENCODE)
RETRIEVAL_MOVES = {MoveType.ELICIT, MoveType.PROBE, MoveType.DRILL,
                   MoveType.REVIEW, MoveType.PROMPT}
# moves that deliver feedback
FEEDBACK_MOVES = {MoveType.RECAST, MoveType.CORRECT, MoveType.EXPLAIN}
# moves that count as a (non-retrieval) exposure
EXPOSURE_MOVES = {MoveType.INTRODUCE, MoveType.INPUT, MoveType.RECAST}


@dataclass
class Move:
    type: MoveType
    target: Optional[str] = None      # item id
    variant: str = ""                 # 'inference'|'structured'|'recognition'|'production'
    drive: str = ""                   # which drive produced it
    flags_error: bool = False         # does this move flag a learner error?
    rationale: str = ""

    @property
    def is_retrieval(self) -> bool:
        return self.type in RETRIEVAL_MOVES

    @property
    def is_feedback(self) -> bool:
        return self.type in FEEDBACK_MOVES

    @property
    def is_explicit_correct(self) -> bool:
        return self.type in (MoveType.CORRECT, MoveType.EXPLAIN)

    def __str__(self) -> str:
        t = f"{self.type.value}"
        if self.variant:
            t += f"/{self.variant}"
        if self.target:
            t += f"({self.target})"
        return t
