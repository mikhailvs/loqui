"""Move realizer — the seam where the LLM turns a selected move into learner-
facing text. Q4: the LLM realizes *under constraint*; the harness has already
chosen the move and the invariants have already vetoed illegal ones.

There are intentionally TWO realization paths with DIFFERENT contracts:

  - `MockRealizer.realize(move, lm) -> str` (here): a deterministic, no-dependency
    stub used ONLY by the simulation viewers (run_session.py, serve.py).
  - `brain.realize(move, item, ctx) -> {"say", "display"}`: the PRODUCTION path,
    called directly by the voice app. It returns structured text (target-language
    audio + English scaffold), not a bare string.

They are not unified on purpose — there is one consumer of each. If you ever add a
second *production* realizer, unify on the brain.realize signature then (and inject
it via `Arbiter(realizer=...)`); until then, do not build an ABC/registry for two
implementations.
"""
from __future__ import annotations
from .moves import Move, MoveType
from .model import LearnerModel


class MockRealizer:
    def realize(self, m: Move, lm: LearnerModel) -> str:
        lemma = lm.items[m.target].lemma if m.target else ""
        if m.type == MoveType.INTRODUCE:
            return f"New word: '{lemma}'. Here's what it means, in context."
        if m.type == MoveType.INPUT:
            if m.variant == "inference":
                return f"Read this — '{lemma}' is guessable from the context."
            return f"Listen/read: a passage featuring '{lemma}'."
        if m.type == MoveType.ELICIT:
            return f"Your turn — produce a sentence using '{lemma}'."
        if m.type == MoveType.PROBE:
            return f"Which of these means '{lemma}'?  (recognition)"
        if m.type == MoveType.PROMPT:
            return f"Hmm — how would you say that again? (think about '{lemma}')"
        if m.type == MoveType.RECAST:
            return f"Ah, you mean: …**{lemma}**… (corrected, marked)."
        if m.type == MoveType.CORRECT:
            return f"Small fix: it's '{lemma}', not what you wrote."
        if m.type == MoveType.EXPLAIN:
            return f"Quick rule about '{lemma}': …"
        if m.type == MoveType.DRILL:
            return f"Quick reps with '{lemma}' in varied contexts."
        if m.type == MoveType.REVIEW:
            return f"Remember '{lemma}'? Use it now."
        if m.type == MoveType.CHAT:
            return "So, tell me about your day — your topic."
        if m.type == MoveType.TASK_REPEAT:
            return "Let's run that task once more, a bit faster."
        return str(m)
