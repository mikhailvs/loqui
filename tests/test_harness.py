#!/usr/bin/env python3
"""Tests that prove the invariants actually fire — and that the arbiter never
emits a move any invariant would veto, across a whole multi-session run.

Run:  python tests/test_harness.py     (no pytest dependency)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import config as C
from harness.model import LearnerModel, Item, Declarative, PendingError
from harness.moves import Move, MoveType
from harness.arbiter import Arbiter
from harness.sim import SimLearner, demo_curriculum
from harness import invariants


def _names(violations):
    return {n for n, _ in violations}


def _model(items):
    return LearnerModel(items)


def _encode(lm, item_id, now=None, stability=None):
    """Mark an item as encoded at the current time (recall ~1.0)."""
    st = lm.states[item_id]
    st.successful_exposures = 1
    st.last_seen_time = lm.global_time if now is None else now
    if stability is not None:
        st.stability = stability
    st.declarative = Declarative.ENCODING


# --- individual invariants ---------------------------------------------

def test_encode():
    lm = _model([Item("x", "x", "vocab", 0.3)])
    v = invariants.validate(Move(MoveType.ELICIT, "x"), lm)
    assert "INV-ENCODE" in _names(v), "elicit on unseen item must be vetoed"
    _encode(lm, "x")
    v = invariants.validate(Move(MoveType.ELICIT, "x"), lm)
    assert "INV-ENCODE" not in _names(v), "encoded item should be retrievable"


def test_inference():
    lm = _model([Item("x", "x", "vocab", 0.3)])
    v = invariants.validate(Move(MoveType.INPUT, "x", variant="cloze"), lm)
    assert "INV-INFERENCE" in _names(v), "cloze on un-encoded item must be vetoed"


def test_nomass_consecutive():
    lm = _model([Item("x", "x", "vocab", 0.3)])
    _encode(lm, "x")
    lm.states["x"].consecutive_count = C.K_CONSEC
    lm.last_emitted = Move(MoveType.ELICIT, "x")
    v = invariants.validate(Move(MoveType.ELICIT, "x"), lm)
    assert "INV-NOMASS" in _names(v), "exceeding k_consec must be vetoed"


def test_nomass_session():
    lm = _model([Item("x", "x", "vocab", 0.3)])
    _encode(lm, "x")
    lm.states["x"].session_exposures = C.K_SESSION
    v = invariants.validate(Move(MoveType.REVIEW, "x"), lm)
    assert "INV-NOMASS" in _names(v), "exceeding k_session must be vetoed"


def test_novel_shaky():
    lm = _model([Item("a", "a", "vocab", 0.3), Item("b", "b", "vocab", 0.3)])
    _encode(lm, "a")                       # a is encoded but shaky (mastery < theta)
    assert "a" in lm.shaky_items()
    v = invariants.validate(Move(MoveType.INTRODUCE, "b"), lm)
    assert "INV-NOVEL" in _names(v), "introduce while shaky must be vetoed"


def test_novel_interactivity():
    lm = _model([Item("subj", "subj", "grammar", 0.8, interactivity=3)])
    v = invariants.validate(Move(MoveType.INTRODUCE, "subj"), lm)
    assert "INV-NOVEL" in _names(v), "high-interactivity introduce must be vetoed"


def test_oneerror_count():
    lm = _model([Item("x", "x", "vocab", 0.3)])
    _encode(lm, "x")
    lm.errors_flagged_this_turn = 1
    v = invariants.validate(Move(MoveType.CORRECT, "x", flags_error=True), lm)
    assert "INV-ONEERROR" in _names(v), "second flagged error must be vetoed"


def test_oneerror_consecutive_correct():
    lm = _model([Item("x", "x", "vocab", 0.3)])
    _encode(lm, "x")
    lm.last_emitted = Move(MoveType.CORRECT, "x")
    v = invariants.validate(Move(MoveType.CORRECT, "x"), lm)
    assert "INV-ONEERROR" in _names(v), "two consecutive explicit corrects must be vetoed"


def test_bands_routes_elicit_to_probe():
    lm = _model([Item("x", "x", "vocab", 0.9)])   # hard item
    lm.global_time = 200
    st = lm.states["x"]
    st.successful_exposures = 1
    st.stability = 120.0
    st.last_seen_time = 117          # recall ~ exp(-83/120) ~ 0.50
    st.declarative = Declarative.ENCODING
    assert lm.recall("x") >= C.RETRIEVAL_FLOOR             # passes INV-ENCODE
    assert lm.predicted_success("x") < C.SUCCESS_LOW
    v = invariants.validate(Move(MoveType.ELICIT, "x"), lm)
    assert "INV-BANDS" in _names(v), "sub-band elicit must be re-routed"
    v2 = invariants.validate(Move(MoveType.PROBE, "x", variant="recognition"), lm)
    assert "INV-BANDS" not in _names(v2), "recognition probe should be allowed"


def test_recast_marked():
    lm = _model([Item("x", "x", "vocab", 0.3)])
    _encode(lm, "x")
    assert "INV-RECAST" in _names(invariants.validate(Move(MoveType.RECAST, "x"), lm))
    assert "INV-RECAST" not in _names(
        invariants.validate(Move(MoveType.RECAST, "x", variant="marked"), lm))


def test_dosage_engage_preempt():
    lm = _model([Item("x", "x", "vocab", 0.3)])
    lm.pending_error = PendingError("x", "production", True)
    v = invariants.validate(Move(MoveType.CHAT, drive="Engage"), lm)
    assert "INV-DOSAGE" in _names(v), "Engage cannot preempt fired Repair"


def test_production_requires_two_events():
    lm = _model([Item("x", "x", "vocab", 0.3)])
    _encode(lm, "x")
    arb = Arbiter()
    chat = Move(MoveType.CHAT, drive="Engage")

    class R:
        produced_item = "x"
    arb.ingest(lm, chat, R())
    assert not lm.states["x"].production_known, "one production event is not enough"
    arb.ingest(lm, chat, R())
    assert lm.states["x"].production_known, "two events should set production_known"


def test_constrained_success_is_not_production():
    lm = _model([Item("x", "x", "vocab", 0.3)])
    _encode(lm, "x")
    arb = Arbiter()
    elicit = Move(MoveType.ELICIT, "x", variant="production")

    class R:
        success = True
        produced_item = None
    arb.apply_emit(lm, elicit)
    arb.ingest(lm, elicit, R())
    assert lm.states["x"].declarative_known, "a passed elicit sets declarative_known"
    assert not lm.states["x"].production_known, \
        "constrained success must NOT set production_known"


# --- whole-session safety + scheduling property ------------------------

def test_session_never_emits_illegal_move_and_spaces_reviews():
    curriculum = demo_curriculum()
    lm = LearnerModel(curriculum)
    sim = SimLearner(curriculum)
    arb = Arbiter()
    for _s in range(8):
        lm.new_session()
        reviews_this_session = []
        for _t in range(C.SESSION_CAP):
            lm.errors_flagged_this_turn = 0
            trace = arb.select(lm)
            # the emitted move violates no invariant
            assert not invariants.validate(trace.move, lm), \
                f"emitted illegal move: {trace.move}"
            if trace.move.type == MoveType.REVIEW:
                # INV-SPACE: no two reviews of the same item in one session
                assert trace.move.target not in reviews_this_session, \
                    f"two reviews of {trace.move.target} in one session"
                reviews_this_session.append(trace.move.target)
            arb.apply_emit(lm, trace.move)
            resp = sim.respond(trace.move, lm)
            arb.ingest(lm, trace.move, resp)
            lm.tick()
    # and the learner actually learned something
    produced = sum(1 for it in curriculum if lm.states[it.id].production_known)
    assert produced >= 1, "expected at least one item to reach production-known"


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} tests passed")


if __name__ == "__main__":
    main()
