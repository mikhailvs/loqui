"""Drive scoring + candidate generation.

The arbiter asks this module for an ordered list of candidate moves (best drive
first). It then emits the first candidate that survives the invariant veto. In a
full system the LLM would *propose* the realization inside the winning drive;
here candidate generation is deterministic code, which is enough to exercise the
veto layer (the actual contribution).
"""
from __future__ import annotations
from typing import Optional

from . import config as C
from .model import LearnerModel
from .moves import Move, MoveType


def arc_bias(lm: LearnerModel) -> dict:
    """A light lesson arc biases drive WEIGHTS only (INV-ARC: it may not fade
    support on a schedule nor veto Repair)."""
    if lm.turn <= 2:                       # warm-up: resurface + easy win
        return {"Review": 1.4, "Engage": 1.2, "Progress": 0.7}
    if lm.turn >= C.SESSION_CAP - 3:       # cool-down: batch repair / review
        return {"Repair": 1.3, "Review": 1.3, "Progress": 0.5}
    return {"Progress": 1.2, "Consolidate": 1.15}   # mid-session: do the work


def score_drives(lm: LearnerModel) -> dict:
    bias = arc_bias(lm)
    due = lm.due_items()
    shaky = lm.shaky_items()
    unseen = lm.unseen_items()

    review = max((1.0 - lm.recall(i) for i in due), default=0.0)
    consolidate = min(len(shaky) / 3.0, 1.0)
    progress = 0.6 if (unseen and not shaky) else 0.0
    engage = 0.3
    repair = 1.0 if lm.pending_error is not None else 0.0

    raw = {"Repair": repair, "Review": review, "Consolidate": consolidate,
           "Progress": progress, "Engage": engage}
    return {k: v * bias.get(k, 1.0) for k, v in raw.items()}


def _lowest_recall_due(lm: LearnerModel) -> Optional[str]:
    due = lm.due_items()
    return min(due, key=lm.recall) if due else None


def _repair_candidates(lm: LearnerModel) -> list:
    err = lm.pending_error
    if err is None:
        return []
    st = lm.states[err.item_id]
    prompt = Move(MoveType.PROMPT, err.item_id, drive="Repair", flags_error=True,
                  rationale="withhold form; learner self-repairs")
    recast = Move(MoveType.RECAST, err.item_id, variant="marked", drive="Repair",
                  flags_error=True, rationale="model correct form, salience-marked")
    correct = Move(MoveType.CORRECT, err.item_id, drive="Repair", flags_error=True,
                   rationale="brief explicit correction, one feature")
    # routed policy: prompt when the learner plausibly can self-repair, else recast
    if err.encoded and st.declarative_known:
        return [prompt, recast, correct]
    return [recast, correct, prompt]


def _review_candidate(lm: LearnerModel) -> list:
    tgt = _lowest_recall_due(lm)
    if tgt is None:
        return []
    if lm.can_retrieve(tgt):
        variant = "production" if lm.mastery(tgt) >= C.THETA_MASTERY else "recognition"
        return [Move(MoveType.REVIEW, tgt, variant=variant, drive="Review",
                     rationale="spaced retrieval of due item")]
    # decayed below the backfire floor -> re-encode instead of retrieve
    return [Move(MoveType.INPUT, tgt, variant="inference", drive="Review",
                 rationale="due but sub-floor: re-encode via inference")]


def _consolidate_candidates(lm: LearnerModel) -> list:
    shaky = lm.shaky_items()
    out = []
    for tgt in sorted(shaky, key=lm.mastery):
        if not lm.can_retrieve(tgt):
            out.append(Move(MoveType.INPUT, tgt, variant="inference", drive="Consolidate",
                            rationale="shaky + sub-floor: re-encode"))
            continue
        # elicit first; INV-BANDS will route to probe if it's too hard
        out.append(Move(MoveType.ELICIT, tgt, variant="production", drive="Consolidate",
                        rationale="production retrieval of shaky item"))
        out.append(Move(MoveType.PROBE, tgt, variant="recognition", drive="Consolidate",
                        rationale="recognition retrieval (band-routed)"))
    return out


def _progress_candidate(lm: LearnerModel) -> list:
    unseen = lm.unseen_items()
    if not unseen:
        return []
    tgt = min(unseen, key=lambda i: lm.items[i].difficulty)
    return [Move(MoveType.INTRODUCE, tgt, drive="Progress",
                 rationale="introduce next item by readiness")]


def _engage_candidate(lm: LearnerModel) -> list:
    return [Move(MoveType.CHAT, drive="Engage", rationale="learner-steerable chat")]


def _fallbacks(lm: LearnerModel) -> list:
    """Always-legal moves so the arbiter never dead-ends."""
    out = []
    encoding = [i for i, st in lm.states.items()
                if st.encoded and not st.production_known]
    if encoding:
        tgt = max(encoding, key=lm.recall)
        out.append(Move(MoveType.INPUT, tgt, variant="inference", drive="Input",
                        rationale="fallback comprehensible input"))
    # last-resort chat: drive 'Fallback' (not 'Engage') so INV-DOSAGE doesn't read
    # it as Engage *preempting* — it is only reached when nothing actionable is legal.
    out.append(Move(MoveType.CHAT, drive="Fallback", rationale="last-resort chat"))
    return out


def generate_candidates(lm: LearnerModel) -> tuple:
    """Return (ordered_candidates, scores). Drives are tried in score order, but
    Repair is forced to the front whenever it has fired."""
    scores = score_drives(lm)
    builders = {
        "Repair": _repair_candidates,
        "Review": _review_candidate,
        "Consolidate": _consolidate_candidates,
        "Progress": _progress_candidate,
        "Engage": _engage_candidate,
    }
    order = sorted(scores, key=lambda d: scores[d], reverse=True)
    if lm.pending_error is not None:
        order = ["Repair"] + [d for d in order if d != "Repair"]

    candidates = []
    for drive in order:
        candidates.extend(builders[drive](lm))
    candidates.extend(_fallbacks(lm))
    return candidates, scores
