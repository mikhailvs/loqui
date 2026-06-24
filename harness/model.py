"""The learner model — the state the invariants read and write.

Two knowledge axes, kept deliberately separate (DESIGN.md, the headline finding
from Nakata & Elgort 2021): a *declarative* graded state (recognition/recall,
driven by spaced retrieval of explicit form-meaning mappings) and a *production*
flag (set only by free-production evidence). Only production retires an item for
communicative use; spaced-retrieval success advances declarative only.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

from . import config as C
from . import scheduler


class Declarative(IntEnum):
    UNSEEN = 0
    ENCODING = 1        # seen, not yet reliably recognized
    RECOGNITION = 2     # recognises form-meaning
    RECALL = 3          # recalls meaning/form on cue


@dataclass(frozen=True)
class Item:
    id: str
    lemma: str
    kind: str                       # 'vocab' | 'grammar' | 'chunk'
    difficulty: float               # 0..1 from frequency band + clause count + CEFR
    interactivity: int = 1          # element-interactivity contribution (INV-NOVEL)
    confusable: tuple = ()          # ids this item is confusable with (INV-INTERLEAVE)
    is_phonological: bool = False   # routes modality (INV-NOSTYLE)
    gloss: str = ""                 # English meaning (for the realizer)
    hint: str = ""                  # usage note for the realizer


@dataclass
class ItemState:
    successful_exposures: int = 0
    total_exposures: int = 0
    recall_history: list = field(default_factory=list)
    stability: float = C.INIT_STABILITY
    last_seen_time: Optional[int] = None
    last_seen_session: Optional[int] = None
    declarative: Declarative = Declarative.UNSEEN
    declarative_known: bool = False
    production_events: list = field(default_factory=list)   # turns of free-production
    production_known: bool = False
    encounters: int = 0                  # spaced encounters (INV-EXPOSURE)
    # transient bookkeeping for massing / feedback invariants
    session_exposures: int = 0
    consecutive_count: int = 0
    awaiting_feedback: bool = False      # set after an elicit/probe the learner failed
    pending_recast_turn: Optional[int] = None  # set when a recast was delivered

    @property
    def encoded(self) -> bool:
        return self.successful_exposures >= 1


@dataclass
class PendingError:
    item_id: str
    kind: str            # 'production' | 'comprehension'
    encoded: bool


class LearnerModel:
    def __init__(self, items: list):
        self.items: dict = {it.id: it for it in items}
        self.states: dict = {it.id: ItemState() for it in items}
        self.session: int = 0
        self.turn: int = 0               # within-session
        self.global_time: int = 0
        self.course_horizon: int = 4000  # total expected time budget
        self.pending_error: Optional[PendingError] = None
        # per-turn transient context the invariants read
        self.errors_flagged_this_turn: int = 0
        self.last_emitted = None         # Move
        self.pushed_elicit_this_session: int = 0
        # logs (INV-DOSAGE: retention and learning are SEPARATE)
        self.event_log: list = []
        self.learning_log: list = []     # (global_time, item, success) from probe/review ONLY
        self.return_log: list = []       # (session, turns) — dosage, never credited as mastery

    # --- time ----------------------------------------------------------
    def tick(self) -> None:
        self.turn += 1
        self.global_time += 1

    def new_session(self) -> None:
        if self.session > 0:
            self.return_log.append((self.session, self.turn))
        self.session += 1
        self.turn = 0
        self.global_time += C.SESSION_GAP
        self.pushed_elicit_this_session = 0
        for st in self.states.values():
            st.session_exposures = 0
            st.consecutive_count = 0

    @property
    def remaining_horizon(self) -> int:
        return max(1, self.course_horizon - self.global_time)

    # --- estimates (harness's view, never the sim's latent skill) ------
    def recall(self, item_id: str) -> float:
        return scheduler.estimated_recall(self.states[item_id], self.global_time)

    def mastery(self, item_id: str) -> float:
        """Harness estimate in [0,1], blended from observable signals only."""
        st = self.states[item_id]
        if st.production_known:
            return 1.0
        enc = min(st.successful_exposures / C.ENCODING_TARGET, 1.0)
        return 0.5 * enc + 0.3 * self.recall(item_id) + 0.2 * (st.declarative / 3)

    # --- queries the drives use ----------------------------------------
    def is_encoded(self, item_id: str) -> bool:
        return self.states[item_id].encoded

    def can_retrieve(self, item_id: str) -> bool:
        """INV-ENCODE precondition: encoded AND recall above the backfire floor."""
        return self.is_encoded(item_id) and self.recall(item_id) >= C.RETRIEVAL_FLOOR

    def due_items(self) -> list:
        return [i for i, st in self.states.items()
                if st.encoded and scheduler.is_due(st, self.global_time)]

    def shaky_items(self) -> list:
        """Encoded, not yet solid, not production-known — these block introduce."""
        out = []
        for i, st in self.states.items():
            if st.encoded and not st.production_known and 0 < self.mastery(i) < C.THETA_SHAKY:
                out.append(i)
        return out

    def unseen_items(self) -> list:
        return [i for i, st in self.states.items() if st.successful_exposures == 0
                and st.total_exposures == 0]

    def predicted_success(self, item_id: str) -> float:
        """Crude success predictor for band selection (INV-BANDS): blends recall
        and (1 - difficulty)."""
        it = self.items[item_id]
        return max(0.0, min(1.0, 0.6 * self.recall(item_id) + 0.4 * (1 - it.difficulty)))
