"""The per-turn loop: propose -> veto -> select; then ingest the learner's
response and update the learner model.

Selection emits the first candidate (best drive first) that survives every
invariant. `apply_emit` updates the transient bookkeeping the invariants read.
`ingest` updates the durable learner model from the learner's response — with
the hard rule (INV-DOSAGE) that mastery is written ONLY from retrieval/probe
outcomes, never from exposure, chat volume, or time-on-task.
"""
from __future__ import annotations
from dataclasses import dataclass

from . import config as C
from . import scheduler
from . import invariants
from .model import LearnerModel, Declarative, PendingError
from .moves import Move, MoveType, RETRIEVAL_MOVES
from .drives import generate_candidates
from .realizer import MockRealizer

EXPOSURE_TYPES = {MoveType.INTRODUCE, MoveType.INPUT, MoveType.RECAST,
                  MoveType.CORRECT, MoveType.EXPLAIN}


@dataclass
class TurnTrace:
    move: Move
    scores: dict
    vetoes: list          # [(candidate_str, [(inv, reason)...])] for rejected candidates


class Arbiter:
    def __init__(self, realizer=None):
        self.realizer = realizer or MockRealizer()

    def select(self, lm: LearnerModel) -> TurnTrace:
        candidates, scores = generate_candidates(lm)
        vetoes = []
        for cand in candidates:
            violations = invariants.validate(cand, lm)
            if not violations:
                return TurnTrace(cand, scores, vetoes)
            vetoes.append((str(cand), violations))
        # _fallbacks guarantees a legal move; reaching here is a bug
        raise RuntimeError("no legal move — invariant set over-constrained")

    def apply_emit(self, lm: LearnerModel, m: Move) -> None:
        if m.target is not None:
            st = lm.states[m.target]
            if lm.last_emitted is not None and lm.last_emitted.target == m.target:
                st.consecutive_count += 1
            else:
                st.consecutive_count = 1
            st.session_exposures += 1
            st.total_exposures += 1
            st.last_seen_session = lm.session
        if m.flags_error:
            lm.errors_flagged_this_turn += 1
        if m.variant == "pushed":
            lm.pushed_elicit_this_session += 1
        if m.type == MoveType.RECAST:
            lm.states[m.target].pending_recast_turn = lm.global_time
        lm.last_emitted = m
        lm.event_log.append((lm.session, lm.turn, str(m), m.drive))

    def ingest(self, lm: LearnerModel, m: Move, resp) -> None:
        now = lm.global_time
        st = lm.states[m.target] if m.target is not None else None

        if m.type in RETRIEVAL_MOVES and st is not None:
            success = bool(resp.success)
            scheduler.update_after_retrieval(st, success, now)
            # ONLY retrieval/probe outcomes are valid learning signal (INV-DOSAGE)
            lm.learning_log.append((now, m.target, m.type.value, success))
            if success:
                if m.variant == "recognition":
                    st.declarative = max(st.declarative, Declarative.RECOGNITION)
                else:
                    st.declarative = Declarative.RECALL
                st.declarative_known = True
            elif m.type != MoveType.PROMPT:
                lm.pending_error = PendingError(m.target, "production", st.encoded)
                st.awaiting_feedback = True

        elif m.type in EXPOSURE_TYPES and st is not None:
            scheduler.update_after_exposure(st, now)
            st.encounters += 1
            if st.declarative == Declarative.UNSEEN:
                st.declarative = Declarative.ENCODING
            # INV-EXPOSURE: a single encounter sets no recognition flag
            if st.encounters >= C.RECOGNITION_ENCOUNTER_MIN and st.declarative < Declarative.RECOGNITION:
                st.declarative = Declarative.RECOGNITION

        elif m.type == MoveType.CHAT and resp.produced_item is not None:
            p = lm.states[resp.produced_item]
            p.production_events.append(lm.turn)
            # INV-PRODUCTION: communicative-known only after >=N free-production events
            if len(p.production_events) >= C.PRODUCTION_EVENTS_MIN:
                p.production_known = True

        # any feedback move (or a prompt) discharges the owed repair
        if m.is_feedback or m.type == MoveType.PROMPT:
            lm.pending_error = None
            if st is not None:
                st.awaiting_feedback = False
