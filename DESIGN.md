# Language Harness — Design Doc (v2, evidence-grounded)

> Status: **control-loop design settled against the literature; parameters open.**
> Target: teaching a **natural human language** (learner-facing tutor agent).
> This pass replaced intuition with evidence: a 14-dimension sweep of SLA /
> cognitive-science / intelligent-tutoring-systems research, each finding
> adversarially fact-checked (effect sizes, replication status, engagement-vs-
> learning confounds), then synthesized into the loop below. Citations are
> compressed inline; see `EVIDENCE.md` for the full verified findings per claim.

---

## 0. Thesis (unchanged, now evidenced)

Pedagogy belongs **in the harness, not the prompt**. The LLM is a *move realizer*;
the harness owns scheduling, state, gates, and a set of **falsifiable invariants**
that the LLM's proposed move must pass. The invariant set **is** the auditable
pedagogy. This is the resolution of **Q4** and it's well-supported: the model will
not reliably self-supply spacing, encoding-before-retrieval gating, declarative-vs-
production skepticism, or exposure budgeting — exactly the places unstructured
systems underperform (Wang et al. 2025; VanLehn 2011; Beck & Chang 2007).

**Reality calibration (this reframes everything below).** The honest ceiling for a
deployed adaptive tutor is **d ≈ 0.2–0.6**, *not* Bloom's 2-sigma (never replicated;
Pane et al. 2014 found ~0.2 SD at scale, null in year 1). And at scale the **binding
constraint is dosage/retention** — whether the learner comes back — not cleverness.
So "keep them returning" is a first-class engineering objective with its own positive
mechanism, separate from and never confused with learning.

---

## 1. What the evidence changed (vs. v1 intuitions)

| v1 intuition | Verdict | What the evidence says |
|---|---|---|
| Favor gentle **recasts** (correct without flagging) | **Overturned** | Recasts are the *weakest* feedback; **prompts** that withhold the form beat them on free production (Lyster & Saito 2010). Recast-only is now an anti-pattern. |
| Two-layer: arc biases weights + arbiter decides | **Kept, constrained** | Arc may bias drive weights but may **not** fade support or veto Repair on a schedule — schedule-based fading is null (Belland 2017); fading must be *mastery*-contingent. |
| "LLM proposes, harness vetoes via invariants" | **Strongly endorsed** | This is the Q4 answer. Pedagogy-in-code for scheduler/gates/state/invariants; LLM realizes under constraint. |
| `i+1` / affective filter as design dials | **Overturned** | Both unfalsifiable (Gregg 1984; McLaughlin 1987). Replaced by a *novel-item cap + comprehension check*. Never appear in the loop. |
| SRS with expanding intervals (SM-2 style) | **Demoted** | Expanding-vs-equal is *contested* (Karpicke & Roediger 2007); the big lever is "space at all," and the optimal-gap ridgeline is broad/flat (Cepeda 2008) — **do not over-engineer interval precision.** |
| Gamify engagement | **Partly harmful** | Leaderboards *lowered* exam grades (Hanus & Fox 2015); expected rewards undermine motivation (Deci 1999). Build engagement from autonomy + earned competence only. |

Two findings that weren't on my radar and now shape the spine:

- **Spacing/retrieval validate *explicit* knowledge, not communicative competence**
  (Nakata & Elgort 2021). So the learner model must split **declarative-known** from
  **production-known**, and only production evidence retires an item for real use.
- **The mastery model can be degenerate** — best-fit BKT params can imply you're
  *more* likely correct when you *don't* know the skill (Beck & Chang 2007). The whole
  gating spine depends on a **validation gate** before any mastery score controls
  anything.

---

## 2. The control loop

### 2.1 Spine (Q1): a **drive-arbiter difficulty-controller**

Not a phase-machine (fixed simple→complex is weakly grounded; scheduled fading is
null) and not pure-SRS (that optimizes explicit item-recall and starves input/output/
interaction). The arbiter is a **difficulty controller** targeting a calibrated success
band, with three coded subsystems wired in:

1. **FSRS/DSR retrievability scheduler** *inside* the Review drive — weights items by
   `1 − estimated_recall`.
2. **BKT/PFA per-item mastery model** feeding the introduce/elicit/probe gates — *only
   after* it passes the validation gate (§3, INV-MASTERY).
3. **Coded difficulty estimator** (frequency band + clause count + CEFR-tagged grammar)
   that pre-scores candidate realizations.

A **light lesson arc** gently biases drive weights (warm-up resurfaces prior-session
items and engineers an early in-band success; cool-down batches delayed repair) but
never vetoes Repair and never fades support on a schedule.

### 2.2 The five drives

| Drive | Fires when… | Realized as | Evidence anchor |
|---|---|---|---|
| **Repair** (pre-emptive) | production error *or* comprehension breakdown | routed policy — see §2.4 | Li 2010 (CF d≈0.61); Lyster & Saito 2010 |
| **Review** | predicted recall ≤ fire-threshold | retrieval move for encoded discrete items; meaning-focused resurfacing for communicative ones (tracked separately) | Cepeda 2006/2008; Adesope 2017 (g=0.51) |
| **Progress** | mastery validated + load budget free | `introduce`, ≤1 novel element, soft-gated | Cowan 2001; Shintani 2013 |
| **Engage** | affect/return-rate dropping | autonomy (steerable chat) + earned competence; never preempts Repair/Review | Alamer 2025; Pane 2014 |
| **Consolidate** | item shaky but encoded | *enqueue spaced retrieval* + form-meaning fluency drill (double-capped) | Nakata 2015; Liu & Tang 2025 |

> **Consolidate was reframed**: from "massed drill now" to "schedule spaced
> retrieval." Massing is the worst option for durable retention.

### 2.3 The move set

`prompt` (output-withholding repair/elicit) · `probe`(recognition) / `elicit`(production)
· `input`/`introduce` (+ **inference** and **structured-input** variants) · `recast`
(salience-marked) · `correct` (focused, one feature) · `explain` (rationed) · `drill`
(form-meaning, double-capped) + `task-repeat` (fluency only) · `chat` (acquisition
channel) · `decode` (conditional script/grapheme move).

### 2.4 Repair is **routed, not a fixed ladder**

Only `prompt > recast` is empirically ranked; explicit correction is *larger* short-term
but implicit is *better maintained*, so a fixed 4-rung order is unsupported. Route instead:

- **`prompt`** when the item is encoded and the learner plausibly has declarative
  knowledge to self-repair (default).
- **salient `recast`** when shaky / low-confidence.
- **brief `correct`** for a discrete slip needing an immediate fix.
- **`explain`** rationed — behind a request or repeated lighter-feedback failure.

### 2.5 Per-turn cycle

```
1. INGEST    parse learner utterance → signals (correct? error? clarification? affect proxy?)
2. UPDATE    learner model — mastery ONLY from delayed-probe/review accuracy;
             retention (return/dosage) logged SEPARATELY; never credit one as the other
3. SCORE     drive pressures (FSRS retrievability · validated mastery gates · difficulty estimator)
4. PROPOSE   LLM proposes a move + realization given state + arc bias
5. VETO      harness checks the proposal against the invariants (§3); reject → re-propose
6. REALIZE   emit the move text under Mayer realization constraints
7. LOG       record exposure/outcome + instrumentation for contested forks (§5)
```

Steps 1–3, 5, 7 are harness code. Steps 4 and 6 are the LLM — on rails.

---

## 3. The invariants (the auditable pedagogy)

23 falsifiable rules, grouped. Each is checkable in code; each cites its basis.

**A — Memory & scheduling**
- **INV-SPACE**: every introduced item is scheduled for spaced *cross-session*
  re-exposure; no two reviews of one item in the same session; `gap = clamp(stability-
  derived, 1 session, horizon_fraction·remaining_horizon)`, `horizon_fraction ≈ 0.2`.
  Don't tune below order-of-magnitude (ridgeline flat). *(Cepeda 2006/2008)*
- **INV-NOMASS**: never mass an item — two named caps: `k_consec` (≈2–3 consecutive)
  and `k_session` (≈4–6 total/session). *(Nakata 2015; Kim & Webb 2022)*
- **INV-FIRSTREV**: the first *effortful* retrieval is scheduled only once
  `encoding_strength ≥ encoding_threshold`; below threshold the next exposure is an
  easy `input`/`recast` re-encounter. *(reconciles Karpicke-Roediger Exp 3 with Rowland/Schwieren)*
- **INV-EXPOSURE**: a single input encounter sets **no** knowledge flag;
  `recognition_known` needs ≥ `recognition_encounter_min` (≈3) spaced encounters;
  `meaning_recall_known` needs a passed recall probe. *(Webb 2023: 6–17% per-word yield)*

**B — Retrieval & feedback**
- **INV-ENCODE**: never `elicit`/`probe`/`drill`/`review` an item with zero successful
  prior exposures or below `encoding_threshold` — fall back to input/recast/inference.
  *(Rowland 2014; Schwieren 2018 — retrieval backfires below retrievability)*
- **INV-FEEDBACK**: every `elicit`/`probe` is followed by feedback within the same/next
  turn; a *failed* retrieval supplies the form (not "try again"). *(Rowland: g=0.73 vs 0.39)*
- **INV-BANDS** (reconciles three previously-conflated numbers): (a) per-turn predicted-
  success target for elicit/probe ∈ `[0.70, 0.85]`, **no hard floor** that vetoes useful
  difficulty; (b) Review fires when `predicted_recall ≤ 0.85–0.90`; (c) FSRS retention
  target ≈ `0.85–0.90`. Three distinct quantities; no code path substitutes one for another.

**C — Knowledge states & promotion**
- **INV-PRODUCTION**: an event counts as free-production evidence iff (i) the target form
  was absent from the immediately preceding harness turn, (ii) it's not a constrained
  drill/cloze/MC, (iii) it meets a min-length/own-construction bar. `production_known`
  needs ≥2 such events on distinct turns. Constrained success advances only the separate
  `declarative_known` flag, which never retires an item for communicative use. *(Goo 2015; Nakata & Elgort 2021)*
- **INV-MASTERY** (hard precondition): no BKT/PFA/scheduler output may gate anything until
  it passes — (i) hierarchical fit, (ii) `p_guess<0.5 ∧ p_slip<0.5`, (iii) semantic-validity
  (p-known must *monotonically raise* p-correct), (iv) AUC/log-loss > trivial baseline on
  held-out logs. Until then, gates fall back to `successful_exposures + time-since-seen`.
  *(Beck & Chang 2007; Papousek AUC≈0.537)*

**D — Introduce & load**
- **INV-NOVEL**: `novel_element_count(turn) ≤ 1`, where the count derives from countable
  features (a chunk taught as one unanalyzed unit = 1; an analytic pattern needing co-
  attention to N slots = N); no `introduce` while `min(mastery over live_set) < theta_shaky`.
  *(Cowan 2001; CLT element-interactivity)*
- **INV-INTERLEAVE**: don't interleave/contrast *first exposures* of novel isolated vocab
  (block early). Interleaving applies only to pairs with `confusability_links`, only across
  sessions, only after both are introduced. *(Brunmair & Richter 2019: vocab g=−0.39; Pan 2019)*
- **INV-EXPECTEDERR**: an error on an above-threshold item currently interleaved with a
  confusable counterpart is `expected_interleaving_error` → must **not** trigger Repair
  escalation or fallback-to-blocking; score interleaved items on *delayed-probe* history,
  not same-session accuracy. *(Nakata & Suzuki 2019)*

**E — Repair**
- **INV-ONEERROR**: ≤1 error flagged per learner turn; flagging suppressed during chat/
  free-production (queued to cool-down); never two consecutive explicit corrections.
  *(Lyster & Saito 2010; Nakata 2015 timing d=0.14)*
- **INV-RECAST**: a recast must (i) reproduce the corrected form, (ii) emit a machine-
  detectable token-level marker on the changed token, (iii) be followed within K turns by
  an `elicit` on that form — else it logs as `input`, not repair. *(Rassaei 2022: recasts ambiguous)*
- **INV-FOCUSCORRECT**: focused correction targets ≤1 treatable rule-based feature/turn,
  skips idiosyncratic/lexical errors, and is re-verified on a *fresh* later production
  (≥3 turns later, different lexical context — not an immediate revision). *(Bitchener & Knoch 2010)*

**F — Input realization**
- **INV-COVERAGE**: input keeps `known_token_ratio ≥ coverage_target` (default 0.95,
  *tunable, not a cliff*) **and** `novel_token_count ≤ novel_token_cap` (≈1–2) **and** is
  paired with a comprehension check; `coverage_target` recalibrated from observed
  comprehension per learner/language. *(Kremmel 2023: 95/98% cliff didn't replicate)*
- **INV-INFERENCE**: for un-encoded items prefer a transparent-rich-context **inference**
  variant; never gap/cloze an un-encoded item. *(van den Broek 2022: inference ≥ retrieval)*

**G — Affect, engagement, dosage**
- **INV-NOLEADERBOARD**: no comparative ranking by default; rewards phrased as skill-
  referenced competence feedback, never currency; content never gated on points.
  *(Hanus & Fox 2015 — demonstrated harm; Deci 1999)*
- **INV-DOSAGE**: retention (session-return, turns/session) and learning (delayed-probe
  accuracy) are logged separately; the arbiter never credits retention/time-on-task/chat
  volume as mastery; `Engage < priority(Repair | overdue-Review)`. **Positive mechanism**:
  the arc schedules ≥1 early in-band success each session; `session_length ≤ session_cap`;
  return-rate is an explicit arc objective. *(Pane 2014 — dosage binds at scale)*
- **INV-NOSTYLE**: the learner model carries no "learning style" field; modality is chosen
  from `target.linguistic_feature` + comprehension history (default text; audio when target
  is phonological); Mayer scaffolds (transcripts/glosses/redundancy) **fade** once
  `mastery > theta_mastery` (expertise reversal). *(Pashler 2008; Cromley & Chen 2025)*
- **INV-ARC**: the arc may bias drive weights but may not fade support on a schedule nor
  veto Repair by phase; fading is mastery-contingent; Repair is reachable in every phase.
  *(Belland 2017 — scheduled fading null)*
- **INV-NOSILENCE**: no hard-coded silent/no-elicit early phase; low-stakes production is
  offered early, gated per-item by `encoding_strength`, not a session-age gate. *(silent period weakly evidenced)*

**H — Self-correcting instrumentation**
- **INV-INSTRUMENT**: the harness MUST log, with delayed-outcome linkage, every contested
  fork — (a) MC vs short-answer format, (b) prompt-vs-recast uptake in-modality,
  (c) block-then-interleave vs pure-interleave by item-type, (d) pushed-elicit outcomes,
  (e) chat-embedded review vs SRS-spine review. No contested policy is frozen as a constant
  before its own log beats a trivial baseline. *(Adesope vs Schwieren; Lyster-Saito oral-only; Hwang vs Nakata-Suzuki)*
- **INV-PUSHEDELICIT**: pushed-elicit (target above stable mastery) is capped
  (`≤ pushed_elicit_cap`/session), always paired with an input/recast fallback within N
  turns, never fires below `encoding_threshold`, logged as an A/B variant. *(Izumi 2002 — single weak study)*

---

## 4. Anti-patterns — do NOT do these (evidence over tradition)

- Recast-only as the default correction policy. *(weakest feedback type)*
- Massed "drill until perfect" / cramming. *(worst for durable retention)*
- Literal `i+1`, a hard 95/98% coverage cliff, or invoking the affective filter to lower
  difficulty. *(unfalsifiable / didn't replicate)*
- Learning-styles / VARK modality matching. *(neuromyth)*
- Leaderboards and XP-as-currency. *(demonstrated harm)*
- Chasing Bloom's 2-sigma with baroque personalization. *(never replicated; calibrate to d≈0.2–0.6)*
- Always-expanding SRS ladders + over-precise interval tuning. *(contested; ridgeline flat)*
- Forced cloze on un-encoded words "for the testing effect." *(inference wins; van den Broek 2022)*
- Strict target-language-only / banning L1; a fixed universal grammar syllabus. *(L1 is a permitted tool; no canonical order)*
- Crediting in-session accuracy / time-on-task / chat volume / return as acquisition. *(engagement ≠ learning)*

---

## 5. Open empirical questions (the harness resolves these on its own population)

The design is deliberately *self-correcting*: each contested fork ships as an A/B with
mandated logging (INV-INSTRUMENT), not a hard-coded guess. The live questions:

1. Does **prompts > recasts** (established oral/human/classroom) hold for a 1:1 **text** LLM?
2. Do human-interaction effect sizes transfer to an LLM interlocutor, or is the ceiling the
   **chatbot g ≈ 0.48** (bias-corrected lower, novelty-confounded)?
3. Correct **success-band edges** and Review/FSRS thresholds for this population/modality?
4. Does **worked-model-before-production** beat output-first for L2 items? (no L2-specific evidence)
5. Does **declarative → procedural** conversion actually happen in this loop, on what timescale?
6. **Block-then-interleave vs pure interleave** — by item-type and proficiency? (Hwang vs Nakata-Suzuki conflict)
7. Does spacing's advantage (shown on explicit recall) **transfer to communicative production**?
8. Does **chat-embedded spaced review** preserve the spacing benefit, or degrade it?
9. Can the **WTC/affect proxy** be validly mapped, and is holding difficulty in-band (not
   lowering it) the right low-affect response? (achievement → lower anxiety)
10. Which **scheduler** predicts recall best here — and does better calibration mean more
    *learning* per turn, or just fewer reviews?
11. **Format effect** — MC vs short-answer — for this population? (metas contradict)
12. Is **dosage/retention** the binding constraint here, and does the positive arc mechanism
    raise return without sliding into engagement-as-learning?
13. Per-language `coverage_target`, `novel_token_cap`, `recognition_encounter_min`?
14. When does the conditional **`decode`** move pay off for opaque-script languages (adults)?

---

## 6. Parked for later passes

- Learner-model **schema** (the concrete fields the invariants read/write).
- **Tool/environment** layer (SRS store, difficulty estimator, comprehension checker, TTS).
- **Content** sourcing/generation pipeline and the CEFR-tagged prerequisite DAG (EVP/EGP).
- Persistence, onboarding/placement, multi-session.
