"""LearnerModel <-> dict <-> JSON.

Lives in the core and imports ONLY harness.model / harness.moves, so both the
CLI (tutor.py) and the server depend on the core — not the other way round.
`load()` takes (curriculum, path) explicitly rather than reading globals, so it
is usable by any caller. Saves are atomic; loads fall back to a fresh model on
any corruption or schema drift (logged, never silent).
"""
from __future__ import annotations
import json
import logging
import os

from .model import LearnerModel, ItemState, Declarative, PendingError
from .moves import Move, MoveType

log = logging.getLogger("loqui.persistence")
SCHEMA_VERSION = 1


def _state_to_dict(st: ItemState) -> dict:
    return {
        "successful_exposures": st.successful_exposures,
        "total_exposures": st.total_exposures,
        "recall_history": st.recall_history,
        "stability": st.stability,
        "last_seen_time": st.last_seen_time,
        "last_seen_session": st.last_seen_session,
        "declarative": int(st.declarative),
        "declarative_known": st.declarative_known,
        "production_events": st.production_events,
        "production_known": st.production_known,
        "encounters": st.encounters,
        "session_exposures": st.session_exposures,
        "consecutive_count": st.consecutive_count,
        "awaiting_feedback": st.awaiting_feedback,
        "pending_recast_turn": st.pending_recast_turn,
    }


def _state_from_dict(d: dict) -> ItemState:
    st = ItemState()
    for k, v in d.items():
        setattr(st, k, v)
    st.declarative = Declarative(d["declarative"])
    return st


def _move_to_dict(m):
    if m is None:
        return None
    return {"type": m.type.value, "target": m.target, "variant": m.variant,
            "drive": m.drive, "flags_error": m.flags_error, "rationale": m.rationale}


def _move_from_dict(d):
    if not d:
        return None
    return Move(MoveType(d["type"]), d["target"], d["variant"], d["drive"],
                d["flags_error"], d["rationale"])


def save(lm: LearnerModel, pending_move, path: str) -> None:
    """Atomic write (tmp + os.replace) so a crash mid-save can't corrupt state."""
    blob = {
        "schema_version": SCHEMA_VERSION,
        "session": lm.session, "turn": lm.turn, "global_time": lm.global_time,
        "course_horizon": lm.course_horizon,
        "pending_error": (None if lm.pending_error is None else
                          {"item_id": lm.pending_error.item_id,
                           "kind": lm.pending_error.kind,
                           "encoded": lm.pending_error.encoded}),
        "pushed_elicit_this_session": lm.pushed_elicit_this_session,
        "last_emitted": _move_to_dict(lm.last_emitted),
        "event_log": lm.event_log, "learning_log": lm.learning_log,
        "return_log": lm.return_log,
        "states": {i: _state_to_dict(st) for i, st in lm.states.items()},
        "pending_move": _move_to_dict(pending_move),
    }
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(blob, f, indent=2)
    os.replace(tmp, path)


def load(curriculum: list, path: str):
    """Return (LearnerModel, pending_move). On a missing/corrupt/out-of-date file,
    start fresh (logged) rather than crash — a research artifact must not be lost
    silently, but a schema change must not brick startup either."""
    lm = LearnerModel(curriculum)
    if not os.path.exists(path):
        return lm, None
    try:
        blob = json.load(open(path))
        lm.session = blob["session"]
        lm.turn = blob["turn"]
        lm.global_time = blob["global_time"]
        lm.course_horizon = blob["course_horizon"]
        lm.pushed_elicit_this_session = blob["pushed_elicit_this_session"]
        pe = blob["pending_error"]
        lm.pending_error = None if pe is None else PendingError(pe["item_id"], pe["kind"], pe["encoded"])
        lm.last_emitted = _move_from_dict(blob["last_emitted"])
        lm.event_log = blob["event_log"]
        lm.learning_log = blob["learning_log"]
        lm.return_log = blob["return_log"]
        for i, sd in blob["states"].items():
            if i in lm.states:
                lm.states[i] = _state_from_dict(sd)
        return lm, _move_from_dict(blob["pending_move"])
    except Exception as e:
        log.warning("could not load learner state from %s (%r); starting fresh", path, e)
        return LearnerModel(curriculum), None
