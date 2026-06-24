"""The invariant veto layer — the auditable pedagogy.

Each invariant is a pure predicate over (proposed move, learner model). It
returns None if the move is permitted, or a short reason string if the move
must be vetoed. The arbiter never emits a move that any invariant vetoes; the
tests assert that property holds across a whole session.

This is a representative subset of the 23 invariants in DESIGN.md — the ones
checkable without the full ML stack. Each carries its DESIGN.md tag.
"""
from __future__ import annotations
from typing import Optional, Callable

from . import config as C
from .moves import Move, MoveType
from .model import LearnerModel


def inv_encode(m: Move, lm: LearnerModel) -> Optional[str]:
    """INV-ENCODE: never run a retrieval move on an un-encoded / sub-floor item."""
    if m.is_retrieval and m.target is not None:
        if not lm.can_retrieve(m.target):
            return f"INV-ENCODE: {m.target} not retrievable (recall={lm.recall(m.target):.2f})"
    return None


def inv_inference(m: Move, lm: LearnerModel) -> Optional[str]:
    """INV-INFERENCE: never gap/cloze an un-encoded item; use the inference variant."""
    if m.type == MoveType.INPUT and m.variant == "cloze" and m.target is not None:
        if not lm.is_encoded(m.target):
            return f"INV-INFERENCE: cannot cloze un-encoded {m.target}; use inference"
    return None


def inv_space(m: Move, lm: LearnerModel) -> Optional[str]:
    """INV-SPACE: no two reviews of one item in the same session (spacing must be
    cross-session). Enforced, not left to emergent decay — a failed review can
    otherwise drop stability enough to re-qualify the item as due same session."""
    if m.type == MoveType.REVIEW and m.target is not None:
        if lm.states[m.target].last_seen_session == lm.session:
            return f"INV-SPACE: {m.target} already resurfaced this session"
    return None


def inv_nomass(m: Move, lm: LearnerModel) -> Optional[str]:
    """INV-NOMASS: never mass an item (k_consec consecutive, k_session total).

    A single corrective feedback (or a repair prompt discharging an owed error)
    is not a practice repetition, so it is exempt — otherwise it can collide
    with INV-FEEDBACK when the item has already hit the cap."""
    if m.target is None:
        return None
    owed = lm.pending_error is not None and lm.pending_error.item_id == m.target
    if m.is_feedback or (m.type == MoveType.PROMPT and owed):
        return None
    st = lm.states[m.target]
    last = lm.last_emitted
    if last is not None and last.target == m.target:
        if st.consecutive_count >= C.K_CONSEC:
            return f"INV-NOMASS: {m.target} hit k_consec={C.K_CONSEC}"
    if st.session_exposures >= C.K_SESSION:
        return f"INV-NOMASS: {m.target} hit k_session={C.K_SESSION}"
    return None


def inv_novel(m: Move, lm: LearnerModel) -> Optional[str]:
    """INV-NOVEL: <=1 novel element/turn; no introduce while an item is shaky."""
    if m.type == MoveType.INTRODUCE:
        shaky = lm.shaky_items()
        if shaky:
            return f"INV-NOVEL: cannot introduce while shaky items exist {shaky}"
        if m.target is not None and lm.items[m.target].interactivity > 1:
            # a high-interactivity element counts as >1 novel element
            return f"INV-NOVEL: {m.target} interactivity>1 must be decomposed"
    return None


def inv_oneerror(m: Move, lm: LearnerModel) -> Optional[str]:
    """INV-ONEERROR: <=1 flagged error/turn; no two consecutive explicit corrects;
    no error-flagging inside chat."""
    if m.flags_error and lm.errors_flagged_this_turn >= 1:
        return "INV-ONEERROR: already flagged an error this turn"
    last = lm.last_emitted
    if m.is_explicit_correct and last is not None and last.is_explicit_correct:
        return "INV-ONEERROR: two consecutive explicit corrections"
    if m.type == MoveType.CHAT and m.flags_error:
        return "INV-ONEERROR: no error-flagging inside chat"
    return None


def inv_bands(m: Move, lm: LearnerModel) -> Optional[str]:
    """INV-BANDS: an ELICIT (production) should land in the success band; if the
    item is too weak, a recognition PROBE is the right realization instead.
    (No hard floor that vetoes useful difficulty — only re-routes elicit->probe.)"""
    if m.type == MoveType.ELICIT and m.target is not None:
        ps = lm.predicted_success(m.target)
        if ps < C.SUCCESS_LOW:
            return f"INV-BANDS: predicted_success {ps:.2f}<{C.SUCCESS_LOW}; route to probe"
    return None


def inv_feedback(m: Move, lm: LearnerModel) -> Optional[str]:
    """INV-FEEDBACK: a failed retrieval must be answered with feedback, not a
    fresh non-feedback move. If feedback is owed, only feedback may be emitted."""
    if lm.pending_error is not None and lm.pending_error.kind == "production":
        # repair is owed: the only legal moves are feedback / prompt
        if not (m.is_feedback or m.type == MoveType.PROMPT):
            return "INV-FEEDBACK: feedback owed before a non-feedback move"
    return None


def inv_recast(m: Move, lm: LearnerModel) -> Optional[str]:
    """INV-RECAST: a recast must be salience-marked (variant carries the marker)."""
    if m.type == MoveType.RECAST and m.variant != "marked":
        return "INV-RECAST: recast must be salience-marked (variant='marked')"
    return None


def inv_dosage(m: Move, lm: LearnerModel) -> Optional[str]:
    """INV-DOSAGE: Engage may never preempt a fired Repair or an overdue Review."""
    if m.drive == "Engage":
        if lm.pending_error is not None:
            return "INV-DOSAGE: Engage cannot preempt fired Repair"
        if lm.due_items():
            return "INV-DOSAGE: Engage cannot preempt overdue Review"
    return None


def inv_pushed_elicit(m: Move, lm: LearnerModel) -> Optional[str]:
    """INV-PUSHEDELICIT: pushed elicit (above stable mastery) is capped/session
    and never fires below encoding threshold."""
    if m.variant == "pushed":
        if m.target is not None and not lm.is_encoded(m.target):
            return "INV-PUSHEDELICIT: pushed elicit below encoding threshold"
        if lm.pushed_elicit_this_session >= C.PUSHED_ELICIT_CAP:
            return f"INV-PUSHEDELICIT: cap {C.PUSHED_ELICIT_CAP}/session reached"
    return None


def inv_silence(m: Move, lm: LearnerModel) -> Optional[str]:
    """INV-NOSILENCE: production eligibility is per-item (encoding), never a
    session-age gate. (Enforced by INV-ENCODE; this is a placeholder asserting
    we never gate elicit on session age — always returns None by construction.)"""
    return None


# ordered registry — name -> predicate
INVARIANTS: list = [
    ("INV-ENCODE", inv_encode),
    ("INV-INFERENCE", inv_inference),
    ("INV-SPACE", inv_space),
    ("INV-NOMASS", inv_nomass),
    ("INV-NOVEL", inv_novel),
    ("INV-ONEERROR", inv_oneerror),
    ("INV-BANDS", inv_bands),
    ("INV-FEEDBACK", inv_feedback),
    ("INV-RECAST", inv_recast),
    ("INV-DOSAGE", inv_dosage),
    ("INV-PUSHEDELICIT", inv_pushed_elicit),
    ("INV-NOSILENCE", inv_silence),
]


def validate(m: Move, lm: LearnerModel) -> list:
    """Return list of (invariant_name, reason) violations; empty == permitted."""
    out = []
    for name, fn in INVARIANTS:
        reason = fn(m, lm)
        if reason is not None:
            out.append((name, reason))
    return out
