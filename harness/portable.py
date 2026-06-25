"""Portable progress codes.

Encode the *essential* learner state (only items actually touched, only the fields
needed to resume — knowledge states + SRS timing) into a compact, gzipped,
URL-safe string the learner can carry to any device. Transient per-session
bookkeeping is dropped. Lang-agnostic; the app prefixes the code with a language
tag so import knows which curriculum to rebuild against.
"""
from __future__ import annotations
import base64
import gzip
import json

from .model import LearnerModel, Declarative

SCHEMA = 1


def to_blob(lm: LearnerModel) -> dict:
    items = {}
    for i, st in lm.states.items():
        if st.total_exposures == 0:
            continue
        items[i] = [
            st.successful_exposures, round(st.stability, 1),
            st.last_seen_time, st.last_seen_session,
            int(st.declarative), int(st.declarative_known),
            len(st.production_events), int(st.production_known),
            st.encounters, st.total_exposures,
        ]
    return {"v": SCHEMA, "g": lm.global_time, "s": lm.session,
            "h": lm.course_horizon, "items": items}


def from_blob(curriculum: list, blob: dict) -> LearnerModel:
    lm = LearnerModel(curriculum)
    lm.global_time = blob.get("g", 0)
    lm.session = blob.get("s", 0)
    lm.course_horizon = blob.get("h", lm.course_horizon)
    for i, v in blob.get("items", {}).items():
        if i not in lm.states:           # item id not in this curriculum -> skip
            continue
        st = lm.states[i]
        (st.successful_exposures, st.stability, st.last_seen_time, st.last_seen_session,
         dec, dk, pe_count, pk, st.encounters, st.total_exposures) = v
        st.declarative = Declarative(dec)
        st.declarative_known = bool(dk)
        st.production_events = [0] * pe_count
        st.production_known = bool(pk)
    return lm


def encode(lm: LearnerModel) -> str:
    raw = json.dumps(to_blob(lm), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(gzip.compress(raw, 9)).decode("ascii")


def decode(curriculum: list, code: str) -> LearnerModel:
    raw = gzip.decompress(base64.urlsafe_b64decode(code.encode("ascii")))
    return from_blob(curriculum, json.loads(raw))
