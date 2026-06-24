#!/usr/bin/env python3
"""Push-to-talk voice tutor server.

Loop:  mic --> media.transcribe (Whisper) --> harness (assess + pick next move,
invariants enforced) --> brain.realize (LLM) --> media.synth_turn (edge-tts) --> play.

This module is the HTTP/TLS shell + the turn engine. Speech I/O lives in media.py,
the LLM seam in brain.py, the page in index.html, persistence in harness. Serves
HTTPS (self-signed) because browsers require a secure context for mic access.
Run:  python voiceserver.py   then open https://<lan-ip>:8443 .
"""
from __future__ import annotations
import json
import os
import ssl
import threading
import time
import unicodedata
import difflib
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import app_settings
import brain
import media
from harness import config as C
from harness.model import LearnerModel
from harness.moves import MoveType, RETRIEVAL_MOVES
from harness.arbiter import Arbiter
from harness.sim import Response
from harness.languages import LANGS
from harness import persistence

log = logging.getLogger("loqui.server")
HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(HERE, "audio")
PAGE_PATH = os.path.join(HERE, "index.html")
os.makedirs(AUDIO_DIR, exist_ok=True)
LOCK = threading.Lock()                 # serializes whole turns (single-user prototype)


class Session:
    def __init__(self):
        self.lm = None
        self.pending = None
        self.arb = Arbiter()
        self.lang = LANGS["pt"]
        self.curriculum = self.lang.curriculum()

    def reset(self, lang_id="pt"):
        self.lang = LANGS.get(lang_id, LANGS["pt"])
        self.curriculum = self.lang.curriculum()
        self.lm = LearnerModel(self.curriculum)
        self.lm.new_session()
        self.pending = None


S = Session()


# ---------- pure helpers (no IO / no globals) ----------
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s if c.isalnum() or c.isspace()).strip()


def local_match(transcript: str, lemma: str) -> bool:
    """Did the learner say the target word/phrase? Accent-insensitive, fuzzy."""
    t, l = _norm(transcript), _norm(lemma)
    if not l:
        return False
    if l in t:
        return True
    ltoks, ttoks = l.split(), t.split()
    if len(ltoks) > 1:                       # multiword: all tokens present
        return all(any(difflib.SequenceMatcher(None, lt, tt).ratio() > 0.8 for tt in ttoks)
                   for lt in ltoks)
    return any(difflib.SequenceMatcher(None, l, tt).ratio() > 0.8 for tt in ttoks)


def assess_response(pending, transcript: str, lm, curriculum):
    """(pending_move, transcript, model, curriculum) -> (Response, correct, produced).
    Pure and testable. Covers BOTH grading branches: a RETRIEVAL move graded by
    local_match, and a CHAT move scanned for a spontaneously-used taught word."""
    if pending is not None and pending.type in RETRIEVAL_MOVES and pending.target:
        correct = local_match(transcript, lm.items[pending.target].lemma)
        return Response(success=correct), correct, None
    if pending is not None and pending.type == MoveType.CHAT:
        hits = [it.id for it in curriculum
                if lm.states[it.id].total_exposures > 0 and local_match(transcript, it.lemma)]
        produced = hits[0] if hits else None
        return Response(produced_item=produced), None, produced
    return Response(), None, None             # exposure move: learner just repeated


# ---------- engine (reads the module-global Session under LOCK) ----------
def _item_dict(item):
    if item is None:
        return None
    return {"id": item.id, "lemma": item.lemma, "gloss": item.gloss,
            "hint": item.hint, "kind": item.kind}


def _known_lemmas():
    return [it.lemma for it in S.curriculum if S.lm.states[it.id].total_exposures > 0]


def _progress():
    intro = [it for it in S.curriculum if S.lm.states[it.id].total_exposures > 0]
    prod = sum(1 for it in S.curriculum if S.lm.states[it.id].production_known)
    return {"introduced": len(intro), "of": len(S.curriculum), "production": prod,
            "words": [it.lemma for it in intro], "language": S.lang.name}


def _emit_next(ctx: dict) -> dict:
    """Select the next move, realize + speak it, persist, return the payload."""
    if S.lm.turn >= C.SESSION_CAP:
        S.lm.new_session()
    S.lm.errors_flagged_this_turn = 0
    trace = S.arb.select(S.lm)
    move = trace.move
    S.arb.apply_emit(S.lm, move)
    S.pending = move
    item = S.lm.items.get(move.target)

    tr = time.time()
    r = brain.realize({"type": move.type.value, "variant": move.variant, "drive": move.drive},
                      _item_dict(item), ctx)
    realize_ms = int((time.time() - tr) * 1000)
    tv = time.time()
    audio_url = media.synth_turn(r.get("say", ""), AUDIO_DIR, S.lang.voice)
    tts_ms = int((time.time() - tv) * 1000)

    persistence.save(S.lm, move, os.path.join(HERE, f".learner_{S.lang.id}.json"))
    blocked = sorted({n for _c, vs in trace.vetoes for n, _r in vs})
    return {
        "say": r.get("say", ""), "display": r.get("display", ""), "audio": audio_url,
        "move": move.type.value, "drive": move.drive, "target": move.target,
        "lemma": item.lemma if item else None,
        "blocked_first": blocked, "progress": _progress(),
        "timing": {"realize_ms": realize_ms, "tts_ms": tts_ms, "via": r.get("_via")},
    }


def do_start(lang_id: str = "pt") -> dict:
    with LOCK:
        S.reset(lang_id)
        return _emit_next({"transcript": None, "correct": None, "known": [],
                           "lang": S.lang.adjective})


def do_turn(audio_bytes: bytes) -> dict:
    with LOCK:
        t0 = time.time()
        transcript = media.transcribe(audio_bytes, S.lang.whisper)
        stt_ms = int((time.time() - t0) * 1000)
        # nothing intelligible heard -> re-ask; DON'T grade it wrong or advance the turn
        if not transcript.strip():
            return {"say": "", "display": "🔇 I didn't catch that — tap 🎤 and try again.",
                    "audio": None, "transcript": "", "you_were": None,
                    "progress": _progress(), "timing": {"stt_ms": stt_ms}, "noinput": True}
        resp, correct, _produced = assess_response(S.pending, transcript, S.lm, S.curriculum)
        if S.pending is not None:
            S.arb.ingest(S.lm, S.pending, resp)
            S.lm.tick()
        payload = _emit_next({"transcript": transcript, "correct": correct,
                              "known": _known_lemmas(), "lang": S.lang.adjective})
        payload["transcript"] = transcript
        payload["you_were"] = ("correct" if correct else
                               "not quite" if correct is False else None)
        payload["timing"]["stt_ms"] = stt_ms
        return payload


# ---------- web ----------
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", ""):
            with open(PAGE_PATH, encoding="utf-8") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if path.startswith("/audio/"):
            fp = os.path.join(AUDIO_DIR, os.path.basename(path))
            if os.path.exists(fp):
                with open(fp, "rb") as f:
                    return self._send(200, f.read(), "audio/mpeg")
        self._send(404, "not found", "text/plain")

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/start":
                q = parse_qs(urlparse(self.path).query)
                lang_id = q.get("lang", ["pt"])[0]
                return self._send(200, json.dumps(do_start(lang_id), ensure_ascii=False),
                                  "application/json")
            if path == "/turn":
                n = int(self.headers.get("Content-Length", 0) or 0)
                if n <= 0 or n > 25_000_000:    # guard a stuck recorder / bad length
                    return self._send(400, json.dumps({"error": "bad audio body size"}),
                                      "application/json")
                data = self.rfile.read(n)
                return self._send(200, json.dumps(do_turn(data), ensure_ascii=False),
                                  "application/json")
        except Exception as e:
            log.exception("request %s failed", path)
            return self._send(500, json.dumps({"error": str(e)}), "application/json")
        self._send(404, "not found", "text/plain")

    def log_message(self, *a):
        pass


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(os.path.join(HERE, ".cert.pem"), os.path.join(HERE, ".key.pem"))
    srv = ThreadingHTTPServer(("0.0.0.0", app_settings.VOICE_PORT), Handler)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    log.info("warming whisper model (once)...")
    media.warm()
    log.info("voice tutor on https://0.0.0.0:%d", app_settings.VOICE_PORT)
    srv.serve_forever()


if __name__ == "__main__":
    main()
