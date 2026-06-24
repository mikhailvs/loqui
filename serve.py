#!/usr/bin/env python3
"""Tiny mobile-friendly web view of the harness simulation.

    python serve.py            # serves on 0.0.0.0:8000

Open from your phone's browser (same Wi-Fi):  http://<computer-lan-ip>:8000
Each load runs a fresh simulated session; "Run again" reshuffles the learner.
No dependencies — Python standard library only.
"""
from __future__ import annotations
import html
import random
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from harness import config as C
from harness.model import LearnerModel, Declarative
from harness.arbiter import Arbiter
from harness.sim import SimLearner, demo_curriculum
from harness import invariants
import app_settings

PORT = app_settings.SIM_PORT

DRIVE_COLOR = {
    "Repair": "#ff6b6b", "Review": "#4dabf7", "Progress": "#51cf66",
    "Consolidate": "#ffd43b", "Engage": "#adb5bd", "Input": "#868e96",
    "Fallback": "#495057",
}


def simulate(n_sessions: int, seed: int) -> dict:
    curriculum = demo_curriculum()
    lm = LearnerModel(curriculum)
    sim = SimLearner(curriculum, seed=seed)
    arb = Arbiter()

    veto_counter, move_counter = Counter(), Counter()
    sessions = []
    for _ in range(n_sessions):
        lm.new_session()
        turns = []
        for _t in range(C.SESSION_CAP):
            lm.errors_flagged_this_turn = 0
            trace = arb.select(lm)
            assert not invariants.validate(trace.move, lm)
            blocked = [name for _c, viols in trace.vetoes for name, _r in viols]
            for name in blocked:
                veto_counter[name] += 1
            move_counter[trace.move.type.value] += 1

            arb.apply_emit(lm, trace.move)
            text = arb.realizer.realize(trace.move, lm)
            resp = sim.respond(trace.move, lm)
            arb.ingest(lm, trace.move, resp)

            outcome = ""
            if resp.success is True:
                outcome = "correct"
            elif resp.success is False:
                outcome = "wrong"
            elif resp.produced_item:
                outcome = f"said “{lm.items[resp.produced_item].lemma}”"
            turns.append({
                "turn": lm.turn, "drive": trace.move.drive,
                "move": str(trace.move), "outcome": outcome,
                "text": text, "blocked": blocked,
            })
            lm.tick()
        sessions.append({"n": lm.session, "turns": turns})

    states = []
    for it in curriculum:
        st = lm.states[it.id]
        states.append({
            "id": it.id, "decl": st.declarative.name,
            "recall": lm.recall(it.id), "mastery": lm.mastery(it.id),
            "prod": len(st.production_events),
            "production_known": st.production_known,
            "lemma": lm.items[it.id].lemma,
        })
    return {
        "seed": seed, "n_sessions": n_sessions, "sessions": sessions,
        "moves": move_counter.most_common(), "vetoes": veto_counter.most_common(),
        "states": states,
        "learning_n": len(lm.learning_log), "return_n": len(lm.return_log),
        "declarative_known": sum(1 for s in states if s["decl"] != "UNSEEN" and s["recall"] > 0),
        "production_known": sum(1 for s in states if s["production_known"]),
        "total": len(states),
    }


def pill(text, color):
    return (f'<span style="background:{color};color:#111;border-radius:10px;'
            f'padding:1px 7px;font-size:11px;font-weight:600">{html.escape(text)}</span>')


def render(d: dict) -> str:
    out = []
    out.append(f'''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>language harness</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; background:#0d0f12; color:#e6e6e6;
         font:15px/1.45 -apple-system,system-ui,sans-serif; }}
  header {{ position:sticky; top:0; background:#15181d; padding:14px 16px;
           border-bottom:1px solid #262a30; }}
  h1 {{ font-size:17px; margin:0 0 2px; }}
  .sub {{ color:#8a929c; font-size:12px; }}
  .btn {{ display:inline-block; margin-top:10px; background:#2b6cb0; color:#fff;
         text-decoration:none; padding:9px 16px; border-radius:9px; font-weight:600; }}
  section {{ padding:8px 12px 4px; }}
  .sh {{ color:#8a929c; font-size:12px; text-transform:uppercase;
        letter-spacing:.06em; margin:14px 2px 6px; }}
  .turn {{ display:flex; gap:8px; align-items:baseline; padding:7px 8px;
          border-bottom:1px solid #1c2027; }}
  .tn {{ color:#5b626b; font-size:11px; min-width:22px; }}
  .body {{ flex:1; min-width:0; }}
  .mv {{ font-family:ui-monospace,Menlo,monospace; font-size:12.5px; color:#cbd3dc; }}
  .txt {{ color:#9aa3ad; font-size:12.5px; margin-top:1px; }}
  .oc-correct {{ color:#51cf66; }} .oc-wrong {{ color:#ff8787; }}
  .oc-said {{ color:#b197fc; }}
  .blocked {{ font-size:10.5px; color:#6b7280; margin-top:2px; }}
  table {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
  td,th {{ text-align:left; padding:5px 6px; border-bottom:1px solid #1c2027; }}
  th {{ color:#8a929c; font-weight:600; }}
  .good {{ color:#51cf66; }} .dim {{ color:#6b7280; }}
  .cards {{ display:flex; flex-wrap:wrap; gap:6px; }}
  .card {{ background:#15181d; border:1px solid #262a30; border-radius:9px;
          padding:7px 11px; font-size:12.5px; }}
  .big {{ font-size:18px; font-weight:700; }}
</style></head><body>''')

    out.append(f'''<header>
  <h1>🌐 language harness — live simulation</h1>
  <div class="sub">{d["n_sessions"]} sessions · seed {d["seed"]} ·
     a fake student, taught by the harness</div>
  <a class="btn" href="/">↻ Run again</a>
</header>''')

    # scoreboard
    out.append('<section><div class="cards">')
    out.append(f'<div class="card"><span class="big good">{d["declarative_known"]}'
               f'</span>/{d["total"]}<br><span class="dim">words recognised</span></div>')
    out.append(f'<div class="card"><span class="big" style="color:#b197fc">'
               f'{d["production_known"]}</span>/{d["total"]}<br>'
               f'<span class="dim">used in free speech</span></div>')
    out.append(f'<div class="card"><span class="big">{d["learning_n"]}</span><br>'
               f'<span class="dim">quiz results logged</span></div>')
    out.append('</div></section>')

    # vetoes — the harness blocking bad moves
    out.append('<section><div class="sh">Rules that blocked a bad move</div><div class="cards">')
    for name, c in d["vetoes"]:
        out.append(f'<div class="card">{html.escape(name)} <span class="dim">×{c}</span></div>')
    out.append('</div></section>')

    # per-session trace
    for s in d["sessions"]:
        out.append(f'<section><div class="sh">Session {s["n"]}</div>')
        for t in s["turns"]:
            color = DRIVE_COLOR.get(t["drive"], "#868e96")
            oc = ""
            if t["outcome"] == "correct":
                oc = '<span class="oc-correct">✓</span>'
            elif t["outcome"] == "wrong":
                oc = '<span class="oc-wrong">✗</span>'
            elif t["outcome"].startswith("said"):
                oc = f'<span class="oc-said">{html.escape(t["outcome"])}</span>'
            blocked = ""
            if t["blocked"]:
                uniq = ", ".join(sorted(set(t["blocked"])))
                blocked = f'<div class="blocked">⊘ tried first, blocked by: {html.escape(uniq)}</div>'
            out.append(f'''<div class="turn">
  <span class="tn">t{t["turn"]}</span>
  <div class="body">
    {pill(t["drive"], color)} <span class="mv">{html.escape(t["move"])}</span> {oc}
    <div class="txt">{html.escape(t["text"])}</div>{blocked}
  </div></div>''')
        out.append('</section>')

    # knowledge table
    out.append('<section><div class="sh">What the student knows now</div><table>')
    out.append('<tr><th>word</th><th>recognises</th><th>recall</th><th>free use</th></tr>')
    for s in d["states"]:
        prod = '<span class="good">✓ yes</span>' if s["production_known"] else '<span class="dim">—</span>'
        out.append(f'<tr><td>{html.escape(s["lemma"])}</td>'
                    f'<td>{html.escape(s["decl"].lower())}</td>'
                    f'<td>{s["recall"]:.2f}</td><td>{prod}</td></tr>')
    out.append('</table></section>')

    out.append('<section><div class="blocked" style="padding:14px 2px 30px">'
               'Each turn the harness picks ONE teaching move; greyed rules show '
               'moves it tried first but its own pedagogy invariants vetoed. '
               'The AI would only write the sentence — the harness makes the call.'
               '</div></section>')
    out.append('</body></html>')
    return "".join(out)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        if urlparse(self.path).path not in ("/", ""):
            self.send_response(404); self.end_headers(); return
        seed = int(q["seed"][0]) if "seed" in q else random.randint(1, 10**6)
        n = int(q["n"][0]) if "n" in q else 6
        page = render(simulate(n, seed))
        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"serving on http://0.0.0.0:{PORT}")
    srv.serve_forever()
