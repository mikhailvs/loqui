#!/usr/bin/env python3
"""Interactive tutor wrapper (CLI) — the harness drives, an external LLM realizes
moves and assesses replies. State persistence lives in harness.persistence (the
core), so this CLI and the voice server share one model<->JSON implementation.

  python tutor.py reset                       # start fresh
  python tutor.py next                         # harness picks the next move
  python tutor.py ingest [--success true|false] [--produced ID] [--error ID]
  python tutor.py status                        # learner-model snapshot
"""
from __future__ import annotations
import argparse
import json
import os

from harness import config as C
from harness.model import PendingError
from harness.moves import MoveType
from harness.arbiter import Arbiter
from harness.brazilian import brazilian_curriculum
from harness.sim import Response
from harness.persistence import save, load, _move_to_dict

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "learner_state.json")
CURRICULUM = brazilian_curriculum()


def cmd_reset(_args):
    from harness.model import LearnerModel
    lm = LearnerModel(CURRICULUM)
    lm.new_session()
    save(lm, None, STATE_PATH)
    print(json.dumps({"ok": True, "msg": "fresh learner; session 1 started",
                      "items": len(CURRICULUM)}))


def cmd_next(_args):
    lm, pending = load(CURRICULUM, STATE_PATH)
    if lm.session == 0:
        lm.new_session()
    if pending is not None:
        print(json.dumps({"error": "a move is awaiting ingest; run ingest first",
                          "pending": _move_to_dict(pending)}))
        return
    if lm.turn >= C.SESSION_CAP:
        lm.new_session()
    lm.errors_flagged_this_turn = 0
    arb = Arbiter()
    trace = arb.select(lm)
    move = trace.move
    arb.apply_emit(lm, move)
    save(lm, move, STATE_PATH)

    it = lm.items.get(move.target)
    blocked = sorted({name for _c, viols in trace.vetoes for name, _r in viols})
    print(json.dumps({
        "session": lm.session, "turn": lm.turn,
        "move": move.type.value, "variant": move.variant, "drive": move.drive,
        "rationale": move.rationale, "target": move.target,
        "lemma": it.lemma if it else None, "gloss": it.gloss if it else None,
        "hint": it.hint if it else None, "kind": it.kind if it else None,
        "phonological": it.is_phonological if it else None,
        "blocked_first": blocked, "expecting": _expecting(move),
    }, ensure_ascii=False, indent=2))


def _expecting(move) -> str:
    if move.type in (MoveType.ELICIT, MoveType.PROBE, MoveType.REVIEW,
                     MoveType.PROMPT, MoveType.DRILL):
        return "ingest --success true|false  (did the learner produce/recognize it?)"
    if move.type == MoveType.CHAT:
        return "ingest [--produced ID]  (did they spontaneously use a target item?)"
    return "ingest   (exposure move; no judgment needed)"


def cmd_ingest(args):
    lm, pending = load(CURRICULUM, STATE_PATH)
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
    if args.error:  # a free-production error caught during chat/input
        st = lm.states[args.error]
        lm.pending_error = PendingError(args.error, "production", st.encoded)
    lm.tick()
    save(lm, None, STATE_PATH)
    tgt = pending.target
    snap = None
    if tgt:
        st = lm.states[tgt]
        snap = {"item": tgt, "declarative": st.declarative.name,
                "declarative_known": st.declarative_known,
                "production_known": st.production_known,
                "recall": round(lm.recall(tgt), 2), "mastery": round(lm.mastery(tgt), 2),
                "production_events": len(st.production_events)}
    print(json.dumps({"ok": True, "ingested": _move_to_dict(pending), "now": snap,
                      "pending_error": (lm.pending_error.item_id if lm.pending_error else None)},
                     ensure_ascii=False, indent=2))


def cmd_status(_args):
    lm, pending = load(CURRICULUM, STATE_PATH)
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
        "pending_move": _move_to_dict(pending), "items": rows,
    }, ensure_ascii=False, indent=2))


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
