#!/usr/bin/env python3
"""Fully-conversational voice tutor (push-to-talk).

Loop:  phone mic --> Whisper STT --> harness (assess + pick next move, all
invariants enforced) --> claude CLI realizes the move --> edge-tts speaks -->
phone plays it.

Serves HTTPS (self-signed) because browsers require a secure context for mic
access. Run:  python voiceserver.py   then open https://<lan-ip>:8443 on phone.
"""
from __future__ import annotations
import json
import os
import ssl
import subprocess
import threading
import unicodedata
import difflib
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import brain
import voice
from harness import config as C
from harness.model import LearnerModel, PendingError
from harness.moves import MoveType, RETRIEVAL_MOVES
from harness.arbiter import Arbiter
from harness.sim import Response
from harness.languages import LANGS
import tutor  # reuse save()/serialization

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(HERE, "audio")
TMP = os.path.join(HERE, ".voicetmp")
PORT = 8443
os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(TMP, exist_ok=True)

LOCK = threading.Lock()


class Session:
    def __init__(self):
        self.lm = None
        self.pending = None
        self.arb = Arbiter()
        self.counter = 0
        self.lang = LANGS["pt"]
        self.curriculum = self.lang.curriculum()

    def reset(self, lang_id="pt"):
        self.lang = LANGS.get(lang_id, LANGS["pt"])
        self.curriculum = self.lang.curriculum()
        self.lm = LearnerModel(self.curriculum)
        self.lm.new_session()
        self.pending = None
        self.counter = 0


S = Session()


# ---------- helpers ----------
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


_WMODEL = None


def _whisper():
    """Load the model ONCE and keep it in memory (the CLI reloaded it every turn).
    faster-whisper: int8 on CPU, with built-in VAD to drop silence."""
    global _WMODEL
    if _WMODEL is None:
        from faster_whisper import WhisperModel
        _WMODEL = WhisperModel(os.environ.get("WHISPER_MODEL", "base"),
                               device="cpu", compute_type="int8")
    return _WMODEL


def _duration(path: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def stt(audio_bytes: bytes, lang: str = "pt") -> str:
    raw = os.path.join(TMP, "in.bin")
    wav = os.path.join(TMP, "in.wav")
    with open(raw, "wb") as f:
        f.write(audio_bytes)
    # normalize any browser format (webm/opus, mp4/aac) to 16k mono wav
    subprocess.run(["ffmpeg", "-y", "-i", raw, "-ar", "16000", "-ac", "1", wav],
                   capture_output=True)
    if _duration(wav) < 0.35:           # too short = silence/accidental tap; don't hallucinate
        return ""
    try:
        segs, _info = _whisper().transcribe(
            wav, language=lang, beam_size=1, temperature=0,
            vad_filter=True,                     # drop non-speech -> no silence hallucination
            condition_on_previous_text=False)    # stop runaway repetition loops
        return " ".join(s.text.strip() for s in segs).strip()
    except Exception:
        return ""


def tts(text: str) -> str | None:
    if not text or not text.strip():
        return None
    S.counter += 1
    name = f"turn_{S.counter}.mp3"
    voice.synth(text, os.path.join(AUDIO_DIR, name), voice=S.lang.voice)
    return f"/audio/{name}"


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
    """Select the next move, realize+speak it, return the payload."""
    if S.lm.turn >= C.SESSION_CAP:
        S.lm.new_session()
    S.lm.errors_flagged_this_turn = 0
    trace = S.arb.select(S.lm)
    move = trace.move
    S.arb.apply_emit(S.lm, move)
    S.pending = move
    item = S.lm.items.get(move.target)
    tr = time.time()
    r = brain.realize(
        {"type": move.type.value, "variant": move.variant, "drive": move.drive},
        _item_dict(item), ctx)
    realize_ms = int((time.time() - tr) * 1000)
    tv = time.time()
    audio_url = tts(r.get("say", ""))
    tts_ms = int((time.time() - tv) * 1000)
    tutor.save(S.lm, move, os.path.join(HERE, f".learner_{S.lang.id}.json"))
    blocked = sorted({n for _c, vs in trace.vetoes for n, _r in vs})
    return {
        "say": r.get("say", ""), "display": r.get("display", ""),
        "audio": audio_url,
        "move": move.type.value, "drive": move.drive, "target": move.target,
        "lemma": item.lemma if item else None,
        "blocked_first": blocked, "progress": _progress(),
        "timing": {"realize_ms": realize_ms, "tts_ms": tts_ms},
    }


def do_start(lang_id: str = "pt") -> dict:
    with LOCK:
        S.reset(lang_id)
        return _emit_next({"transcript": None, "correct": None, "known": [],
                           "lang": S.lang.adjective})


def do_turn(audio_bytes: bytes) -> dict:
    with LOCK:
        t0 = time.time()
        transcript = stt(audio_bytes, S.lang.whisper)
        stt_ms = int((time.time() - t0) * 1000)
        # nothing intelligible heard -> re-ask, DON'T grade it as wrong or advance
        if not transcript.strip():
            return {"say": "", "display": "🔇 I didn't catch that — tap 🎤 and try again.",
                    "audio": None, "transcript": "", "you_were": None,
                    "progress": _progress(), "timing": {"stt_ms": stt_ms}, "noinput": True}
        pend = S.pending
        correct = None
        produced = None
        assess_ms = 0
        if pend is not None and pend.type in RETRIEVAL_MOVES and pend.target:
            correct = local_match(transcript, S.lm.items[pend.target].lemma)
            resp = Response(success=correct)
        elif pend is not None and pend.type == MoveType.CHAT:
            # detect a spontaneously-used taught word LOCALLY (no LLM call -> ~4s saved)
            hits = [it.id for it in S.curriculum
                    if S.lm.states[it.id].total_exposures > 0
                    and local_match(transcript, it.lemma)]
            produced = hits[0] if hits else None
            resp = Response(produced_item=produced)
        else:
            resp = Response()                # exposure move: learner just repeated
        if pend is not None:
            S.arb.ingest(S.lm, pend, resp)
            S.lm.tick()
        payload = _emit_next({"transcript": transcript, "correct": correct,
                              "produced": produced, "known": _known_lemmas(),
                              "lang": S.lang.adjective})
        payload["transcript"] = transcript
        payload["you_were"] = ("correct" if correct else
                               "not quite" if correct is False else None)
        payload["timing"]["stt_ms"] = stt_ms
        if assess_ms:
            payload["timing"]["assess_ms"] = assess_ms
        return payload


# ---------- web ----------
PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>fala! — portuguese tutor</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;background:#0d0f12;color:#e9edf2;font:16px/1.5 -apple-system,system-ui,sans-serif;
 display:flex;flex-direction:column;height:100dvh}
header{padding:12px 16px;background:#15181d;border-bottom:1px solid #262a30}
h1{font-size:16px;margin:0}.prog{font-size:12px;color:#8a929c;margin-top:2px}
#log{flex:1;overflow-y:auto;padding:14px 14px 4px}
.msg{margin:0 0 14px;max-width:90%}
.tutor .disp{background:#1b2330;border:1px solid #29384d;border-radius:14px 14px 14px 4px;padding:10px 13px}
.tutor .say{font-size:20px;font-weight:600;color:#fff;margin-bottom:3px}
.you{margin-left:auto;text-align:right}
.you .b{display:inline-block;background:#2b6cb0;border-radius:14px 14px 4px 14px;padding:8px 13px}
.tag{font-size:11px;color:#6b7280;margin-top:3px}
.ok{color:#51cf66}.no{color:#ffa94d}
.play{background:none;border:1px solid #3a4150;color:#9aa3ad;border-radius:8px;
 font-size:12px;padding:3px 9px;margin-top:6px;cursor:pointer}
footer{padding:14px;background:#15181d;border-top:1px solid #262a30;text-align:center}
#mic{width:84px;height:84px;border-radius:50%;border:none;font-size:30px;color:#fff;
 background:#2b6cb0;transition:.15s;cursor:pointer}
#mic.rec{background:#e03131;transform:scale(1.08);box-shadow:0 0 0 6px rgba(224,49,49,.25)}
#mic:disabled{background:#3a4150}
#hint{font-size:12px;color:#8a929c;margin-top:8px;min-height:16px}
#langsel{display:flex;gap:8px;justify-content:center;margin-bottom:10px}
.lang{background:#1b2330;border:1px solid #29384d;color:#cbd3dc;border-radius:18px;padding:6px 14px;font-size:13px;cursor:pointer}
.lang.active{background:#2b6cb0;color:#fff;border-color:#2b6cb0}
</style></head><body>
<header><h1>🗣️ loqui <span style="color:#8a929c;font-weight:400">— voice tutor</span></h1>
<div class="prog" id="prog">pick a language &amp; start</div></header>
<div id="log"></div>
<footer>
<div id="langsel">
<button class="lang active" data-l="pt">🇧🇷 Português</button>
<button class="lang" data-l="ru">🇷🇺 Русский</button>
</div>
<button id="mic" disabled>🎤</button>
<div id="hint">pick a language, then start</div>
<button id="start" class="play" style="margin-top:10px">▶ start</button>
</footer>
<audio id="player"></audio>
<script>
const log=document.getElementById('log'),player=document.getElementById('player'),
 mic=document.getElementById('mic'),hint=document.getElementById('hint'),
 prog=document.getElementById('prog'),startBtn=document.getElementById('start');
let rec,chunks=[],busy=false,unlocked=false,lang='pt';
window.addEventListener('error',function(e){if(hint)hint.textContent='⚠ '+e.message;});
function add(html,cls){const d=document.createElement('div');d.className='msg '+cls;
 d.innerHTML=html;log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function play(url){if(!url)return;player.src=url;player.play().catch(()=>{});}
function showTutor(d){
 let h='';if(d.say)h+='<div class="say">'+esc(d.say)+'</div>';
 h+='<div class="disp">'+esc(d.display||'')+'</div>';
 if(d.audio)h+='<button class="play">🔊 again</button>';
 if(d.timing){const t=d.timing;let s=[];
  if(t.stt_ms)s.push('heard '+(t.stt_ms/1000).toFixed(1)+'s');
  if(t.assess_ms)s.push('grade '+(t.assess_ms/1000).toFixed(1)+'s');
  if(t.realize_ms)s.push('brain '+(t.realize_ms/1000).toFixed(1)+'s');
  if(t.tts_ms)s.push('voice '+(t.tts_ms/1000).toFixed(1)+'s');
  if(s.length)h+='<div class="tag">⏱ '+s.join(' · ')+'</div>';}
 const el=add(h,'tutor');
 if(d.audio){const b=el.querySelector('.play');if(b)b.onclick=function(){play(d.audio);};}
 play(d.audio);
 prog.textContent=d.progress?((d.progress.language?d.progress.language+'  ·  ':'')+'words: '+d.progress.introduced+'/'+d.progress.of+
   '  ·  speaking: '+d.progress.production):'';
}
async function start(){
 startBtn.style.display='none';unlocked=true;
 try{player.play().catch(function(){});}catch(e){}   // unlock audio, never block on it
 hint.textContent='thinking…';
 try{
  const r=await fetch('/start?lang='+lang,{method:'POST'});
  showTutor(await r.json());
  mic.disabled=false;hint.textContent='tap 🎤 and speak';
 }catch(e){hint.textContent='start failed: '+e.message;startBtn.style.display='';}
}
async function send(blob){
 busy=true;mic.disabled=true;hint.textContent='🤔 listening + thinking…';
 const r=await fetch('/turn',{method:'POST',body:blob});
 const d=await r.json();
 if(d.transcript!==undefined){
  let tag=d.you_were?('<div class="tag '+(d.you_were=='correct'?'ok':'no')+'">'+d.you_were+'</div>'):'';
  add('<div class="b">'+esc(d.transcript||'…')+'</div>'+tag,'you');
 }
 showTutor(d);busy=false;mic.disabled=false;hint.textContent='tap 🎤 and speak';
}
async function toggle(){
 if(busy)return;
 if(rec&&rec.state==='recording'){rec.stop();mic.classList.remove('rec');hint.textContent='…';return;}
 try{const s=await navigator.mediaDevices.getUserMedia({audio:true});
  rec=new MediaRecorder(s);chunks=[];
  rec.ondataavailable=e=>chunks.push(e.data);
  rec.onstop=()=>{send(new Blob(chunks));s.getTracks().forEach(t=>t.stop());};
  rec.start();mic.classList.add('rec');hint.textContent='● recording — tap to send';
 }catch(e){hint.textContent='mic blocked — allow microphone access';}
}
document.querySelectorAll('.lang').forEach(function(b){b.onclick=function(){lang=b.dataset.l;document.querySelectorAll('.lang').forEach(x=>x.classList.remove('active'));b.classList.add('active');};});
startBtn.onclick=start;mic.onclick=toggle;
</script></body></html>"""


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
            return self._send(200, PAGE, "text/html; charset=utf-8")
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
                n = int(self.headers.get("Content-Length", 0))
                data = self.rfile.read(n)
                return self._send(200, json.dumps(do_turn(data), ensure_ascii=False),
                                  "application/json")
        except Exception as e:
            return self._send(500, json.dumps({"error": str(e)}), "application/json")
        self._send(404, "not found", "text/plain")

    def log_message(self, *a):
        pass


def main():
    cert = os.path.join(HERE, ".cert.pem")
    key = os.path.join(HERE, ".key.pem")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    print("warming whisper model (once)...", flush=True)
    _whisper()
    print(f"voice tutor on https://0.0.0.0:{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
