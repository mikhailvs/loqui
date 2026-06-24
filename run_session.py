#!/usr/bin/env python3
"""Run a simulated teaching session and print a trace + summary.

    python run_session.py            # default: 6 sessions, trace session 1
    python run_session.py 10 2       # 10 sessions, trace session 2

Demonstrates: drives proposing moves, invariants vetoing illegal ones, and the
learner model evolving — with mastery written only from retrieval outcomes
(learning) kept separate from session-return (retention).
"""
from __future__ import annotations
import sys
from collections import Counter

from harness import config as C
from harness.model import LearnerModel, Declarative
from harness.arbiter import Arbiter
from harness.sim import SimLearner, demo_curriculum
from harness import invariants


def run(n_sessions: int = 6, trace_session: int = 1):
    curriculum = demo_curriculum()
    lm = LearnerModel(curriculum)
    sim = SimLearner(curriculum)
    arb = Arbiter()

    veto_counter = Counter()
    move_counter = Counter()
    emitted_total = 0

    for _ in range(n_sessions):
        lm.new_session()
        tracing = (lm.session == trace_session)
        if tracing:
            print(f"\n=== SESSION {lm.session} "
                  f"(trace; '·' = a candidate vetoed before this one) ===")
        for _t in range(C.SESSION_CAP):
            lm.errors_flagged_this_turn = 0
            trace = arb.select(lm)

            # core safety property: the emitted move violates NO invariant
            assert not invariants.validate(trace.move, lm), \
                f"emitted illegal move {trace.move}"

            for _cand, viols in trace.vetoes:
                for name, _reason in viols:
                    veto_counter[name] += 1
            move_counter[trace.move.type.value] += 1
            emitted_total += 1

            arb.apply_emit(lm, trace.move)
            text = arb.realizer.realize(trace.move, lm)
            resp = sim.respond(trace.move, lm)
            arb.ingest(lm, trace.move, resp)

            if tracing:
                pend = len(trace.vetoes)
                outcome = ""
                if resp.success is not None:
                    outcome = "✓" if resp.success else "✗"
                elif resp.produced_item:
                    outcome = f"→produced {resp.produced_item}"
                top = max(trace.scores, key=trace.scores.get)
                print(f"  t{lm.turn:>2} {'·'*pend:<3} [{trace.move.drive:<11}] "
                      f"{str(trace.move):<28} {outcome:<14} {text[:46]}")
            lm.tick()

    # ---- summary ----
    print("\n" + "=" * 64)
    print(f"SUMMARY — {n_sessions} sessions, {emitted_total} moves emitted")
    print("-" * 64)

    print("\nMoves emitted:")
    for mv, c in move_counter.most_common():
        print(f"  {mv:<14} {c}")

    print("\nInvariant vetoes (candidates blocked before a legal move was found):")
    if veto_counter:
        for name, c in veto_counter.most_common():
            print(f"  {name:<18} {c}")
    else:
        print("  (none)")

    print("\nLearner model — final knowledge states:")
    dec_names = {d: d.name for d in Declarative}
    for it in curriculum:
        st = lm.states[it.id]
        prod = "PRODUCTION" if st.production_known else "—"
        print(f"  {it.id:<12} decl={dec_names[st.declarative]:<11} "
              f"recall={lm.recall(it.id):.2f} mastery={lm.mastery(it.id):.2f} "
              f"prod_events={len(st.production_events)} [{prod}]")

    learned = sum(1 for it in curriculum if lm.states[it.id].declarative_known)
    produced = sum(1 for it in curriculum if lm.states[it.id].production_known)
    print(f"\nLearning vs retention separation (INV-DOSAGE):")
    print(f"  learning_log entries (retrieval/probe ONLY): {len(lm.learning_log)}")
    print(f"  return_log entries (sessions completed):     {len(lm.return_log)}")
    print(f"  declarative-known: {learned}/{len(curriculum)}   "
          f"production-known: {produced}/{len(curriculum)}")
    return lm


if __name__ == "__main__":
    ns = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    ts = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    run(ns, ts)
