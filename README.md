# loqui

> *loqui* — Latin, "to speak."

An **agent harness for teaching a spoken language**, where the pedagogy lives in
the harness — *not* in the model's prompt. The LLM only realizes moves; the
harness owns scheduling, learner state, and a set of **falsifiable invariants**
that veto any move violating good pedagogy. The invariant set *is* the auditable
curriculum.

It runs as a **push-to-talk voice tutor**: you speak, it transcribes you, the
harness decides what to teach next, an LLM writes the line, and it speaks back —
in a few seconds, fully local.

The whole design is grounded in an evidence sweep of second-language-acquisition,
cognitive-science-of-learning, and intelligent-tutoring-systems research, with
every claim adversarially fact-checked (effect sizes, replication status,
engagement-vs-learning confounds). See **[DESIGN.md](DESIGN.md)** and the
**[EVIDENCE.md](EVIDENCE.md)** appendix.

## How it works

```
 you speak ─▶ Whisper (STT) ─▶ HARNESS ─▶ LLM realizes ─▶ edge-tts ─▶ it speaks
                                  │          the move          back
              drives + invariants ┘   (claude -p or local Ollama)
```

- **The harness decides** every turn: which of five drives (Repair / Review /
  Progress / Engage / Consolidate) wins, and which concrete move it becomes —
  then **vetoes** any move that breaks an invariant (e.g. "never quiz an
  un-taught word", "never mass an item", "grade only delayed production").
- **The LLM only writes** the chosen move's text and grades free speech. Swap the
  brain freely: a `claude -p` CLI fallback, or a local/LAN Ollama model.
- **Languages are data.** A target language is just a curriculum file plus
  STT/TTS/brain language settings — switch between *learning* one (Portuguese)
  and *QA-ing the system* in one you speak natively (Russian).

## Run

```bash
pip install --user faster-whisper edge-tts          # STT + TTS
# a brain: either the `claude` CLI on PATH, or an Ollama endpoint:
export BRAIN_URL=http://localhost:11434/api/chat BRAIN_MODEL=qwen3:8b

# voice tutor (HTTPS, self-signed — needed for mic access in the browser)
openssl req -x509 -newkey rsa:2048 -keyout .key.pem -out .cert.pem -days 365 \
  -nodes -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
python voiceserver.py            # open https://localhost:8443

# or, no audio/LLM needed — watch the harness drive a simulated learner:
python run_session.py            # text trace of drives + invariant vetoes
python tests/test_harness.py     # prove the invariants fire
```

## Layout

| path | role |
|---|---|
| `harness/model.py` | learner model — declarative-vs-production states, retrievability |
| `harness/scheduler.py` | forgetting curve + spaced scheduling |
| `harness/drives.py` | the five drives: score + propose candidate moves |
| `harness/invariants.py` | the veto layer (the auditable pedagogy) |
| `harness/arbiter.py` | per-turn loop: propose → veto → select → ingest |
| `harness/curricula/{pt,ru}.json` + `curricula.py` | frequency-ordered curricula (data) + loader |
| `harness/languages.py` | language profiles (curriculum + STT/TTS/brain language) |
| `brain.py` | LLM seam (Ollama / `claude -p`), structured-output JSON |
| `voice.py` / `voiceserver.py` | edge-tts + the push-to-talk web app |
| `tutor.py` / `run_session.py` | CLI tutor / simulated-learner runner |

## Status

Research prototype. The harness, learner model, and a representative subset of the
invariants are implemented and tested; the voice loop works end-to-end (~2–3s/turn
on a warm local model). It is **not** validated as *effective* — that needs real
learners and delayed post-tests; the design's instrumentation is built to collect
exactly that. See `DESIGN.md §5` for the open empirical questions.

## License

MIT — see [LICENSE](LICENSE).
