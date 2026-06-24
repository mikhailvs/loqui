"""Tunable parameters for the harness.

Every value here is a hyperparameter the DESIGN.md invariants reference by name.
None are empirical constants — they are defaults to be calibrated per population
(see the open empirical questions in DESIGN.md and INV-INSTRUMENT).
"""

# --- time model ---------------------------------------------------------
# Global time accumulates +1 per turn and +SESSION_GAP between sessions, so a
# cross-session gap dwarfs a within-session one. This is what makes "space it"
# mechanically different from "repeat it now".
SESSION_GAP = 60          # between-session jump; >> within-session per-turn +1
SESSION_CAP = 20          # INV-DOSAGE: cap session length to protect return-rate

# --- retrievability / scheduling (scheduler.py) -------------------------
INIT_STABILITY = 120.0    # stability (in time units) of a just-encoded item
STABILITY_GROWTH = 2.1    # multiplier per successful spaced review
MAX_STABILITY = 6000.0
HORIZON_FRACTION = 0.2    # INV-SPACE: next-gap targets ~20% of remaining horizon

# --- the three reconciled bands (INV-BANDS) -----------------------------
RETRIEVAL_FLOOR = 0.30    # below this estimated recall, retrieval backfires -> re-encode
REVIEW_FIRE = 0.85        # Review fires when predicted_recall <= this
SUCCESS_LOW = 0.70        # elicit/probe predicted-success target band (low edge)
SUCCESS_HIGH = 0.85       # ...high edge. No hard floor that vetoes useful difficulty.
RETENTION_TARGET = 0.88   # FSRS retention target for interval-setting

# --- mastery / load gates ----------------------------------------------
THETA_SHAKY = 0.50        # below this an encoded item is "shaky" (blocks introduce)
THETA_MASTERY = 0.85      # at/above this, fade scaffolds; item is solid
ENCODING_TARGET = 4       # successful exposures that saturate the encoding proxy

# --- exposure / massing caps -------------------------------------------
K_CONSEC = 2              # INV-NOMASS: max consecutive same-item exposures
K_SESSION = 5             # INV-NOMASS: max total same-item exposures per session
RECOGNITION_ENCOUNTER_MIN = 3   # INV-EXPOSURE: spaced encounters before recognition flag
PRODUCTION_EVENTS_MIN = 2       # INV-PRODUCTION: free-production events to be production_known

# --- repair -------------------------------------------------------------
RECAST_ELICIT_WINDOW = 3  # INV-RECAST: an elicit must follow a recast within K turns

# --- pushed elicit ------------------------------------------------------
PUSHED_ELICIT_CAP = 1     # INV-PUSHEDELICIT: per session
