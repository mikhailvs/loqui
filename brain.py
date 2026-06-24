"""The LLM seam — realizes moves and grades free speech.

Primary backend: a local/LAN LLM served by Ollama (OpenAI-/native API) with
STRUCTURED OUTPUT (format=schema) and thinking disabled — fast, valid JSON
guaranteed. Configure via env: BRAIN_URL (Ollama /api/chat endpoint) and
BRAIN_MODEL. Falls back to the local `claude -p` CLI if the endpoint is
unreachable. (A Qwen3-30B-A3B MoE on a LAN Apple-Silicon box gives ~0.9s warm.)

The harness has already CHOSEN the move and enforced every invariant; the brain
only turns it into language. 'say' is the TARGET LANGUAGE ONLY (read by a native
voice — English there would be mangled); all English scaffolding goes in 'display'.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import urllib.request

# Default to a local Ollama; point at a LAN box with e.g.
#   BRAIN_URL=http://192.168.1.50:11434/api/chat BRAIN_MODEL=qwen3:30b-a3b
BRAIN_URL = os.environ.get("BRAIN_URL", "http://localhost:11434/api/chat")
BRAIN_MODEL = os.environ.get("BRAIN_MODEL", "qwen3:8b")
HTTP_TIMEOUT = 30
CLAUDE_TIMEOUT = 60

SAY_SCHEMA = {"type": "object", "required": ["say", "display"],
              "properties": {"say": {"type": "string"}, "display": {"type": "string"}}}
# 'note' before 'produced_item' so the model reasons before committing the id
ASSESS_SCHEMA = {"type": "object", "required": ["note", "produced_item"],
                 "properties": {"note": {"type": "string"},
                                "produced_item": {"type": ["string", "null"]}}}

GUIDE = {
    "introduce": "Introduce the new word/phrase. 'say' = ONLY the word/phrase in the target language, clearly. 'display' = the word, its English meaning, and a 3-6 word usage tip.",
    "input": "Give ONE short EASY sentence in the target language using mostly already-known words plus the target, that the learner can understand. 'say' = the target-language sentence only. 'display' = its English meaning.",
    "elicit": "Ask the learner to SAY something themselves. Do NOT reveal the answer. 'say' = a brief natural cue in the target language, or empty. 'display' = the English instruction of what to say (e.g. \"Say: 'I want water'\").",
    "prompt": "The learner just erred. Withhold the answer; nudge a retry. 'say' = a short encouraging cue in the target language. 'display' = a small hint in English, NOT the full answer.",
    "recast": "The learner erred. Give the CORRECT form naturally. 'say' = the correct form in the target language only. 'display' = a brief English note of the fix.",
    "correct": "Briefly correct ONE thing. 'say' = the correct target-language form. 'display' = one short English note.",
    "review": "Prompt recall of a previously-learned item WITHOUT revealing it. 'say' = a short cue in the target language or empty. 'display' = English, e.g. 'How do you say \"water\"?'.",
    "drill": "Quick varied practice of the target. 'say' = a short cue in the target language. 'display' = the English instruction.",
    "chat": "Have a tiny real conversation at the learner's level. 'say' = ONE short friendly line in the target language using mostly known words. 'display' = English gist + 'reply in the target language'.",
}


def _system_realize(lang: str) -> str:
    return (
        f"You are a warm, patient {lang} tutor for an absolute beginner. "
        "Output ONLY the JSON object, nothing else. "
        f"'say' MUST be {lang} ONLY — it is read aloud by a native {lang} voice; "
        "NEVER put English in 'say' (it may be empty if no spoken target language is needed). "
        "Put ALL English (meaning, instructions, hints) in 'display', 1-2 short lines. Keep it short.")


def _ollama(system: str, user: str, schema: dict, fallback: dict) -> dict:
    body = json.dumps({
        "model": BRAIN_MODEL, "think": False, "stream": False, "format": schema,
        "keep_alive": "30m",                       # keep the model warm on the Mac
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "options": {"num_predict": 220, "temperature": 0.4},
    }).encode()
    req = urllib.request.Request(BRAIN_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        d = json.loads(r.read())
    content = d["message"]["content"]
    m = re.search(r"\{.*\}", content, re.DOTALL)
    return json.loads(m.group(0)) if m else fallback


def _claude(prompt: str, fallback: dict) -> dict:
    p = subprocess.run(["claude", "-p", prompt], capture_output=True,
                       text=True, timeout=CLAUDE_TIMEOUT)
    m = re.search(r"\{.*\}", p.stdout.strip(), re.DOTALL)
    return json.loads(m.group(0)) if m else fallback


def _brain(system: str, user: str, schema: dict, fallback: dict) -> dict:
    """Mac/Ollama first; claude -p as fallback; static fallback last."""
    try:
        return _ollama(system, user, schema, fallback)
    except Exception:
        try:
            return _claude(system + "\n\n" + user + "\n\nOutput ONLY the JSON object.",
                           fallback)
        except Exception:
            return fallback


def realize(move: dict, item: dict | None, ctx: dict) -> dict:
    lang = ctx.get("lang", "Brazilian Portuguese")
    guide = GUIDE.get(move["type"], "Deliver the move naturally for a beginner.")
    known = ", ".join(ctx.get("known", [])) or "(nothing yet)"
    lastline = ""
    if ctx.get("transcript"):
        verdict = {True: "correct", False: "incorrect", None: "unscored"}[ctx.get("correct")]
        lastline = (f"\nThe learner just said (imperfect speech-to-text): "
                    f"\"{ctx['transcript']}\" — judged {verdict}. React in ONE short warm phrase first.")
    itemline = ""
    if item:
        itemline = (f"\nTarget item: '{item['lemma']}' = \"{item['gloss']}\""
                    + (f" (note: {item['hint']})" if item.get("hint") else ""))
    user = (f"Move: {move['type']}{('/' + move['variant']) if move.get('variant') else ''}. "
            f"{guide}{itemline}\nWords the learner already knows: {known}.{lastline}")
    fb = {"say": item["lemma"] if item else "",
          "display": (f"{item['lemma']} — {item['gloss']}" if item else "Let's keep going.")}
    return _brain(_system_realize(lang), user, SAY_SCHEMA, fb)


def assess_chat(transcript: str, candidates: list) -> dict:
    cand = "; ".join(f"{c['id']}='{c['lemma']}' ({c['gloss']})" for c in candidates) or "(none)"
    system = ("You grade a beginner's free Brazilian Portuguese. Output ONLY JSON. "
              "'note' = <=4 words. 'produced_item' = the id of a listed item they used "
              "correctly and meaningfully, or null.")
    user = f"Learner said (imperfect STT): \"{transcript}\".\nKnown items: {cand}."
    return _brain(system, user, ASSESS_SCHEMA, {"note": "", "produced_item": None})
