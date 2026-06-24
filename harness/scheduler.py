"""Retrievability + spaced scheduling. Operates on raw ItemState; imports no
model code (keeps the dependency graph acyclic).

Retrievability is the classic exponential forgetting curve
    R(t) = exp(-elapsed / stability)
Stability grows multiplicatively on a *successful, spaced* review (the spacing
effect) and is knocked down on failure. We deliberately do NOT optimize the
interval beyond order-of-magnitude (DESIGN.md INV-SPACE: the temporal ridgeline
is broad and flat near peak; precise tuning is low-ROI).
"""
from __future__ import annotations
import math
from . import config as C


def estimated_recall(state, now: int) -> float:
    """Predicted probability of successful recall at time `now`."""
    if state.last_seen_time is None or state.successful_exposures == 0:
        return 0.0
    elapsed = max(0, now - state.last_seen_time)
    return math.exp(-elapsed / max(state.stability, 1e-6))


def is_due(state, now: int) -> bool:
    """Review fires when predicted recall has decayed to the fire threshold,
    but only for an item that is actually encoded (INV-ENCODE keeps un-encoded
    items out of retrieval entirely)."""
    if state.successful_exposures == 0:
        return False
    return estimated_recall(state, now) <= C.REVIEW_FIRE


def update_after_retrieval(state, success: bool, now: int) -> None:
    """Update stability after a retrieval attempt. A success that came after a
    real gap earns more stability than one that came too soon (spacing)."""
    gap = 0 if state.last_seen_time is None else now - state.last_seen_time
    if success:
        # spacing bonus: a review that lands while recall has decayed a bit is
        # worth more than one stacked on top of a fresh memory.
        decay = estimated_recall(state, now) if state.last_seen_time else 0.0
        spacing_bonus = 1.0 + (1.0 - decay)          # in [1, 2]
        state.stability = min(state.stability * C.STABILITY_GROWTH * 0.5 * spacing_bonus,
                              C.MAX_STABILITY)
        state.successful_exposures += 1
    else:
        state.stability = max(state.stability * 0.5, C.INIT_STABILITY * 0.5)
    state.recall_history.append(success)
    state.last_seen_time = now


def update_after_exposure(state, now: int) -> None:
    """A non-retrieval encounter (input / inference / recast): counts as a
    successful exposure for encoding, sets a modest stability floor."""
    if state.stability < C.INIT_STABILITY:
        state.stability = C.INIT_STABILITY
    state.successful_exposures += 1
    state.last_seen_time = now


def next_review_gap(state, remaining_horizon: int) -> int:
    """Order-of-magnitude gap to the next review, clamped to horizon-tied bounds
    (INV-SPACE). Minimum is one cross-session gap so two reviews never land in
    the same session."""
    stability_gap = int(state.stability * 0.9)
    max_gap = max(C.SESSION_GAP, int(C.HORIZON_FRACTION * max(remaining_horizon, 1)))
    return max(C.SESSION_GAP, min(stability_gap, max_gap))
