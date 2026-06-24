"""Move realizer — the seam where the LLM turns a selected move into learner-
facing text. Q4: the LLM realizes *under constraint*; the harness has already
chosen the move and the invariants have already vetoed illegal ones.

`MockRealizer` is a deterministic stub so the loop runs with no API dependency.
A real `LLMRealizer` would implement the same `realize(move, model) -> str`
contract, prompting the model with the move, the target item, and the learner
state — and its output would itself be re-checked against any output-level
invariants before being shown.
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
