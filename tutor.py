#!/usr/bin/env python3
"""Interactive tutor wrapper — the harness drives, an external LLM (me, Claude,
in the chat) realizes moves and assesses replies.

The CODE owns every pedagogical decision (which move, which item, all invariant
vetoes). The LLM only (a) turns the chosen move into Brazilian Portuguese and
(b) grades the learner's reply into the signals the harness ingests. State
persists to JSON between calls so this is a real, resumable tutor.

  python tutor.py reset                       # start fresh
  python tutor.py next                         # harness picks the next move -> I realize it
  python tutor.py ingest [--success true|false] [--produced ID] [--error ID]
  python tutor.py status                        # learner-model snapshot
"""
from __future__ import annotations
import argparse
import json
import os
import sys

from harness import config as C
from harness.model import LearnerModel, ItemState, Declarative, PendingError
from harness.moves import Move, MoveType
from harness.arbiter import Arbiter
from harness.brazilian import brazilian_curriculum
from harness.sim import Response
from harness import invariants

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "learner_state.json")
CURRICULUM = brazilian_curriculum()


# ---------- (de)serialization ----------
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


def save(lm: LearnerModel, pending_move, path: str = STATE_PATH) -> None:
    blob = {
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
    with open(path, "w") as f:
        json.dump(blob, f, indent=2)


def load():
    lm = LearnerModel(CURRICULUM)
    if not os.path.exists(STATE_PATH):
        return lm, None
    blob = json.load(open(STATE_PATH))
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
        lm.states[i] = _state_from_dict(sd)
    return lm, _move_from_dict(blob["pending_move"])


# ---------- commands ----------
def cmd_reset(_args):
    lm = LearnerModel(CURRICULUM)
    lm.new_session()
    save(lm, None)
    print(json.dumps({"ok": True, "msg": "fresh learner; session 1 started",
                      "items": len(CURRICULUM)}))


def cmd_next(_args):
    lm, pending = load()
    if lm.session == 0:
        lm.new_session()
    if pending is not None:
        print(json.dumps({"error": "a move is awaiting ingest; run ingest first",
                          "pending": _move_to_dict(pending)}))
        return
    if lm.turn >= C.SESSION_CAP:
        lm.new_session()
    lm.errors_flagged_this_turn = 0
    trace = arb_select(lm)
    move = trace.move
    arb = Arbiter()
    arb.apply_emit(lm, move)
    save(lm, move)

    it = lm.items.get(move.target)
    blocked = sorted({name for _c, viols in trace.vetoes for name, _r in viols})
    out = {
        "session": lm.session, "turn": lm.turn,
        "move": move.type.value, "variant": move.variant, "drive": move.drive,
        "rationale": move.rationale,
        "target": move.target,
        "lemma": it.lemma if it else None,
        "gloss": it.gloss if it else None,
        "hint": it.hint if it else None,
        "kind": it.kind if it else None,
        "phonological": it.is_phonological if it else None,
        "blocked_first": blocked,
        "expecting": _expecting(move),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def _expecting(move) -> str:
    if move.type in (MoveType.ELICIT, MoveType.PROBE, MoveType.REVIEW,
                     MoveType.PROMPT, MoveType.DRILL):
        return "ingest --success true|false  (did the learner produce/recognize it?)"
    if move.type == MoveType.CHAT:
        return "ingest [--produced ID]  (did they spontaneously use a target item?)"
    return "ingest   (exposure move; no judgment needed)"


def cmd_ingest(args):
    lm, pending = load()
    if pending is None:
        print(json.dumps({"error": "nothing to ingest; run next first"}))
        return
    success = None
    if args.success is not None:
        success = args.success.lower() in ("true", "t", "1", "yes", "y")
    resp = Response(success=success, produced_item=args.produced,
                    comprehended=True if args.produced is None else None)
    arb = Arbiter()
    arb.ingest(lm, pending, resp)
    if args.error:  # a free-production error the LLM caught during chat/input
        st = lm.states[args.error]
        lm.pending_error = PendingError(args.error, "production", st.encoded)
    lm.tick()
    save(lm, None)
    tgt = pending.target
    snap = None
    if tgt:
        st = lm.states[tgt]
        snap = {"item": tgt, "declarative": st.declarative.name,
                "declarative_known": st.declarative_known,
                "production_known": st.production_known,
                "recall": round(lm.recall(tgt), 2), "mastery": round(lm.mastery(tgt), 2),
                "production_events": len(st.production_events)}
    print(json.dumps({"ok": True, "ingested": _move_to_dict(pending),
                      "now": snap,
                      "pending_error": (lm.pending_error.item_id if lm.pending_error else None)},
                     ensure_ascii=False, indent=2))


def cmd_status(_args):
    lm, pending = load()
    rows = []
    for it in CURRICULUM:
        st = lm.states[it.id]
        if st.total_exposures == 0:
            continue
        rows.append({"id": it.id, "lemma": it.lemma, "gloss": it.gloss,
                     "declarative": st.declarative.name,
                     "recall": round(lm.recall(it.id), 2),
                     "mastery": round(lm.mastery(it.id), 2),
                     "prod_events": len(st.production_events),
                     "production_known": st.production_known})
    print(json.dumps({
        "session": lm.session, "turn": lm.turn,
        "introduced": len(rows), "of": len(CURRICULUM),
        "declarative_known": sum(1 for r in rows if r["declarative"] != "UNSEEN"),
        "production_known": sum(1 for r in rows if r["production_known"]),
        "learning_events": len(lm.learning_log),
        "pending_move": _move_to_dict(pending),
        "items": rows,
    }, ensure_ascii=False, indent=2))


_ARB = Arbiter()
def arb_select(lm):
    return _ARB.select(lm)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("reset")
    sub.add_parser("next")
    ing = sub.add_parser("ingest")
    ing.add_argument("--success", default=None)
    ing.add_argument("--produced", default=None)
    ing.add_argument("--error", default=None)
    sub.add_parser("status")
    args = p.parse_args()
    {"reset": cmd_reset, "next": cmd_next, "ingest": cmd_ingest,
     "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    main()
