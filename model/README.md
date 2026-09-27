# model/ — Part 4: baseline precursor-vs-decoy classifier

## What this is

A baseline, interpretable classifier trained on
`synthetic/simulated_mesh_data.csv` that predicts, for each sensor
reading, whether it belongs to a **subsidence-precursor buildup phase**,
a **decoy false alarm** (earthquake/blasting-like vibration spike), or
**normal** baseline behavior — using `event_type` from
`synthetic/events_log.csv` as ground truth. Built by `build_model.py`.

**This is trained entirely on synthetic data** (see `synthetic/README.md`
for what's grounded in real Indian coalfield rates vs. what's an
engineering assumption). It demonstrates that the modeling *pipeline* —
features, split, training, evaluation — works correctly end to end. It is
not a claim about real-world accuracy; that requires retraining on real
hardware logs once available.

## Current Model — Summary (read this first)

**Primary dataset:** `synthetic/simulated_mesh_data_v6_with_external.csv`
(103,960 rows = our 103,680 + 176 v2 escalation rows → `subsidence_precursor`
+ 104 v2 `vibration_disturbance` rows → `decoy_seismic`).

**The model:** `model/random_forest_model_v6.joblib` — Random Forest,
200 trees, `max_depth=6`, `class_weight="balanced"`, 8 causal features
(`tilt_deg`, `vibration_rms`, `displacement_mm`, `crack_signal`,
`vibration_duration`, `tilt_vibration_correlation`,
`displacement_persistence`, `tilt_deviation_from_node_baseline`). Built by
`model/build_model_v6.py`; full numbers in `model/metrics_v6.json`.

**Final metrics — RF v6, held-out test set (our own data, 43,158 rows dated
≥ 2026-10-15; all merged v2 rows are in train):**

| class | precision | recall | F1 | test support |
|---|---|---|---|---|
| `normal` | 0.9988 | 1.0000 | 0.9993 | 43,017 |
| `decoy_seismic` | 0.864 | 0.950 | 0.905 | 20 |
| `subsidence_precursor` | **1.000** | **0.570** | 0.726 | 121 |
| **accuracy** | | | **0.99870** | 43,158 |

Confusion matrix (rows = true, cols = pred `[normal, decoy_seismic, subsidence_precursor]`):
`normal [43014, 3, 0]` · `decoy_seismic [1, 19, 0]` · `subsidence_precursor [52, 0, 69]`.

**What the error profile looks like** (full deep-dive:
`model/diagnose_v6_errors.py` + "v6 error deep-dive" section below):
**zero false subsidence alarms** (0 `normal → subsidence_precursor`),
**zero anomaly-type confusions** (0 `decoy ↔ precursor` either way). Every
error is anomaly ↔ `normal`: 52 precursor misses (44 of them in the first
quarter of the buildup, where the injected signal is mathematically still
at baseline — an inherent detection-lag, not a bug), 1 spent-vibration
decoy tail sample, and 3 harmless `normal → decoy_seismic` sensor-noise
blips. **No further feature engineering is recommended before submission**
— see the deep-dive for the reasoning.

**LR v6** (`logistic_regression_model_v6.joblib`) is kept as the
interpretable cross-check: `normal` 0.999/1.000, `decoy_seismic`
0.826/0.950, `subsidence_precursor` 1.000/0.603, accuracy 0.99877. RF is
primary (better `decoy_seismic` precision and no dependence on
`class_weight` alone for the minority boundary).

## Dataset version note

**v6 is the primary / authoritative dataset and model going forward**
(locked after the final quality pass — see "Current Model — Summary" above
and "v6 error deep-dive" below). **v4 and v5 are retained as historical
comparison artifacts** — their datasets, `*.joblib`, `metrics*.json`, and
`*.png` are left in place, untouched and not deleted, so the v3 → v4 → v5
→ v6 progression stays reproducible. They are **not** the current model.

Version history:

- **v1 → v3**: dataset growth only (21 → 60 → 120 days; 103,680 rows;
  18 precursor + 15 decoy episodes).
- **v4**: no new rows — added the feature
  `tilt_deviation_from_node_baseline` (causal per-node 7-day rolling-median
  tilt deviation, `synthetic/add_tilt_baseline_feature.py`) to close the
  offset-node failure mode found in v3. `model/diagnose_offset_node.py` is
  the diagnosis; `model/diagnose_recall_by_phase.py` the buildup-phase
  breakdown. **Sections below from "Label definition" onward still describe
  the v4 build**; v5/v6 are documented in their own sections and here.
- **v5**: + 176 v2 escalation rows → `subsidence_precursor`.
- **v6** (**primary**): + 104 v2 `vibration_disturbance` rows →
  `decoy_seismic`. v2 `normal` rows deliberately **excluded** (analysis
  recommended against — see "v6" § step 3).

## v5 — partial merge of external (v2) escalation episodes

**Status: superseded by v6 (now primary — see "Current Model — Summary"
above). Retained as a historical comparison artifact.** At the time this
section was written v5 was a comparison build against the then-primary v4;
that framing is kept below for the record. v5 artifacts
(`*_v5.joblib`, `metrics_v5.json`, `*_v5.png`) are left untouched.

### What was merged, and why only this

After validating Divyanshi's independently-built dataset
(`external/README.md`), we merged **only the safe subset**: the
**176 `deformation_watch` + `escalating_failure` rows** from
`external/v2_engineered.csv` (3 v2 nodes: `NODE_V2_02/05/07`), all mapped
to our **`subsidence_precursor`** class. New training dataset:
`synthetic/simulated_mesh_data_v5_with_external.csv` (103,680 → **103,856
rows**), built by `synthetic/merge_v2_escalation_v5.py`. The existing
103,680 rows are byte-identical (asserted).

**Held back this pass** (see `external/README.md` §(b)/(c)):

- **`vibration_disturbance` rows** — our model reads 93 % of them as
  `decoy_seismic` (its *not-risky* class) while v2 labels them risky. That
  decoy-vs-risk semantic conflict has to be resolved with Divyanshi
  before those rows can be used; mapping them either way would corrupt
  the class boundary.
- **v2 `normal` rows** — they trip our model ~200× more often than our own
  normal rows (1.5 % vs 0.007 %), a real distribution-shift signal.
  Merging them is a separate call.

### Interaction risk (task step 2) and how it was handled

v2's episodes **fully revert to baseline tilt/displacement when they end**
(`NODE_V2_02` tilt mean 0.165° before vs 0.164° after; displacement ≈ 0
both sides) — the **opposite** of our own precursor episodes, which keep
their tilt/displacement offset **permanently**. This directly affects
`tilt_deviation_from_node_baseline` (current tilt − node's causal 7-day
rolling-median tilt).

Because we deliberately did **not** import v2's baseline rows, recomputing
that feature *naively* in the merged frame — rolling median over only the
176 imported episode rows — **breaks it**: the median is taken from the
episode's own already-elevated tilt, so early-buildup rows collapse toward
0 (indistinguishable from normal) and the whole ramp is understated:

| v2 scenario | `tilt_deg` median | naive-merged dev (median / min) | anchored dev **(used)** (median / min) |
|---|---|---|---|
| `deformation_watch` | 0.72 | 0.21 / −0.01 | **0.57 / 0.16** |
| `escalating_failure` | 2.39 | 1.44 / 0.36 | **2.22 / 0.97** |

**Handling:** the rolling median is seeded from each v2 node's **genuine
pre-episode baseline**, taken from `external/v2_raw.csv`'s full 21-day
series (those baseline rows are used **only as a computation reference —
they are not added to training**). This reproduces the standalone
`external/v2_engineered.csv` values exactly (max abs diff 0.0) and behaves
like our own precursor buildups — positive at onset, growing through the
ramp. The other three derived features (`vibration_duration`,
`tilt_vibration_correlation`, `displacement_persistence`) are carried from
`external/v2_engineered.csv` for the same reason: that run had the full v2
series context, so its per-node thresholds / spike baselines are the
correct ones; recomputing them episode-only would distort them the same
way.

### Fresh split

Split re-tallied on the new row composition; the **date is unchanged**
(2026-10-15) because it is still principled (no future leakage, both
anomaly classes on both sides). All 176 merged rows are dated **August
2026**, so they **all fall in the TRAIN partition** — the **test set is
identical to v4's** (43,017 normal / 121 precursor / 20 decoy). That is
deliberate: it makes v4 → v5 a clean isolation of *"what does adding v2's
escalation episodes to training do to our model on our own held-out
data."* Train precursor rows: 335 → **511** (+176).

### v4 → v5 comparison (same test set, `metrics.json` vs `metrics_v5.json`)

| | Logistic Regression v4 | **LR v5** | Random Forest v4 | **RF v5** |
|---|---|---|---|---|
| `normal` P / R / F1 | 0.999 / 0.999 / 0.999 | 0.999 / 0.999 / 0.999 | 0.999 / 1.000 / 0.999 | 0.999 / 1.000 / 0.999 |
| `decoy_seismic` P / R / F1 | 0.357 / 1.000 / 0.526 | **0.417** / 1.000 / **0.588** | 0.857 / 0.900 / 0.878 | 0.857 / 0.900 / 0.878 |
| `subsidence_precursor` P / R / F1 | 0.813 / 0.612 / 0.698 | **1.000** / 0.612 / **0.759** | 1.000 / 0.562 / 0.720 | 1.000 / **0.554** / **0.713** |
| accuracy | 0.99768 | **0.99826** | 0.99866 | 0.99863 |

Confusion matrices (test set, `true → predicted`, cols `[normal, decoy_seismic, subsidence_precursor]`):

| | v4 | v5 | change |
|---|---|---|---|
| **LR** `normal` | `[42964, 36, 17]` | `[42989, 28, 0]` | −25 misroutes: −8 to decoy, **−17 to precursor** |
| **LR** `decoy_seismic` | `[0, 20, 0]` | `[0, 20, 0]` | — |
| **LR** `subsidence_precursor` | `[47, 0, 74]` | `[47, 0, 74]` | — (recall unchanged) |
| **RF** `normal` | `[43014, 3, 0]` | `[43014, 3, 0]` | — |
| **RF** `decoy_seismic` | `[2, 18, 0]` | `[2, 18, 0]` | — |
| **RF** `subsidence_precursor` | `[53, 0, 68]` | `[54, 0, 67]` | 1 precursor row → normal |

**Reading:**

- **Logistic Regression improves across the board, no regression.**
  Adding 176 v2 escalation rows to training sharpened its
  `subsidence_precursor` boundary: the **17 `normal → subsidence_precursor`
  false positives in v4 drop to 0** (precision 0.813 → **1.000**),
  `normal → decoy` leakage falls 36 → 28 (decoy precision 0.357 →
  **0.417**), and accuracy rises 0.99768 → 0.99826. Precursor recall is
  unchanged (74/121, precursor row identical).
- **Random Forest is essentially unmoved:** one precursor test row flips
  to `normal` (recall 0.562 → 0.554, 68 → 67 of 121); `normal`,
  `decoy_seismic`, and precursor precision are byte-identical to v4. At
  `max_depth=6` with 200 trees the model is regularised enough that 176
  extra same-class rows don't shift its boundary — the change is within
  run-to-run noise.
- RF feature importances barely move
  (`tilt_deviation_from_node_baseline` 0.286 → 0.298,
  `vibration_duration` 0.225 → 0.231).

**Caveat on scope:** because the split is chronological and every v2 row
is dated August, the **test set contains zero v2 rows** — so this
comparison shows *"merging the safe subset does not harm our model on our
own data"* (confirmed: LR better, RF flat). It does **not** re-measure
generalisation *to* v2-style episodes; that was already answered in
`external/README.md` (v4 already caught v2's escalation rows at 100 %
recall). Testing learned generalisation would need a later pass that puts
some v2 episodes on the test side of the split, or a dedicated v2 holdout.

### v5 files

`build_model_v5.py`, `random_forest_model_v5.joblib`,
`logistic_regression_model_v5.joblib`, `metrics_v5.json`,
`confusion_matrix_{random_forest,logistic_regression}_v5.png`,
`feature_importances_v5.png`, and the dataset
`synthetic/simulated_mesh_data_v5_with_external.csv` (+
`synthetic/merge_v2_escalation_v5.py` that builds it).

---

## v6 — merge of external (v2) `vibration_disturbance` rows

**Status: PRIMARY.** After the final error deep-dive (below), v6 is locked
as the authoritative dataset and `random_forest_model_v6.joblib` as the
model going forward. v4 and v5 artifacts are retained untouched as
historical comparison points. See "Current Model — Summary" at the top for
the headline numbers.

### What was merged, and why

Divyanshi confirmed that v2's `vibration_disturbance` scenario is a
**seismic/noise-type disturbance used for false-alarm testing — the same
semantic role as our `decoy_seismic` class.** That resolves the conflict
that held these rows back in v5 (our model had already classified 93 % of
them as `decoy_seismic` independently; that is now confirmed correct, not
a mismatch).

So v6 adds the **104 `vibration_disturbance` rows** (5 v2 nodes,
`NODE_V2_01/03/04/06/08`), all mapped to **`decoy_seismic`**, on top of
v5. New dataset:
`synthetic/simulated_mesh_data_v6_with_external.csv` (103,856 → **103,960
rows**), built by `synthetic/merge_v2_vibration_disturbance_v6.py`. The
103,856 v5 rows are asserted byte-identical. Train `decoy_seismic` count:
31 → **135**.

### Feature recompute check (task step 2) — interaction risk does *not* apply here

The v5 risk was that v2 escalation episodes have **elevated tilt that
reverts to baseline**, so a naive episode-only recompute of
`tilt_deviation_from_node_baseline` understates it.

For `vibration_disturbance` that pattern is absent: **tilt never rises
during one.** Checked against `external/v2_raw.csv` — per-node mean
`tilt_deg` before / during / after each disturbance is flat to within
~0.01° (e.g. `NODE_V2_01`: 0.241 / 0.242 / 0.239), and displacement is
flat too. It is a vibration-only event by construction, so
`tilt_deviation_from_node_baseline` stays at ~0 (noise) no matter how it
is computed: anchored recompute median −0.0005, naive episode-only median
0.0000, range ≈ ±0.10 for both.

Handling: the value is still taken via the **anchored** method (rolling
median seeded from the node's full `external/v2_raw.csv` series, baseline
rows used as a computation reference only, never added to training),
identical to v5, and asserted equal to the standalone
`external/v2_engineered.csv` value — so the pipeline stays uniform even
though the risk is immaterial here. The other three derived features are
carried from `external/v2_engineered.csv`, same rationale as v5.

### Fresh split

Same principled date (2026-10-15), re-tallied on the new row composition.
Every v2 row is dated August 2026, so all 280 merged rows (176 + 104)
fall in **train**; the **test set is identical to v4's / v5's** (43,017
normal / 20 decoy / 121 precursor). v5 → v6 is therefore a clean
isolation of "what do the 104 `decoy_seismic` rows do."

### v5 → v6 comparison (same test set, `metrics_v5.json` vs `metrics_v6.json`)

| | LR v5 | **LR v6** | RF v5 | **RF v6** |
|---|---|---|---|---|
| `normal` P / R / F1 | 0.999 / 0.999 / 0.999 | 0.999 / **1.000** / 0.999 | 0.999 / 1.000 / 0.999 | 0.999 / 1.000 / 0.999 |
| `decoy_seismic` P / R / F1 | 0.417 / 1.000 / 0.588 | **0.826** / 0.950 / **0.884** | 0.857 / 0.900 / 0.878 | 0.864 / **0.950** / **0.905** |
| `subsidence_precursor` P / R / F1 | 1.000 / 0.612 / 0.759 | 1.000 / 0.603 / 0.753 | 1.000 / 0.554 / 0.713 | 1.000 / **0.570** / **0.726** |
| accuracy | 0.99826 | **0.99877** | 0.99863 | **0.99870** |

Confusion matrices (test set, `true → predicted`, cols `[normal, decoy_seismic, subsidence_precursor]`):

| | v5 | v6 | change |
|---|---|---|---|
| **LR** `normal` | `[42989, 28, 0]` | `[43013, 4, 0]` | **−24 `normal → decoy` false alarms** |
| **LR** `decoy_seismic` | `[0, 20, 0]` | `[1, 19, 0]` | 1 real decoy → normal |
| **LR** `subsidence_precursor` | `[47, 0, 74]` | `[48, 0, 73]` | 1 precursor row → normal |
| **RF** `normal` | `[43014, 3, 0]` | `[43014, 3, 0]` | — |
| **RF** `decoy_seismic` | `[2, 18, 0]` | `[1, 19, 0]` | **1 more decoy caught** (was missed → normal) |
| **RF** `subsidence_precursor` | `[54, 0, 67]` | `[52, 0, 69]` | **2 more precursor rows caught** |

**Reading:**

- **Logistic Regression: large decoy-precision gain.** The 104 real decoy
  examples let LR draw a proper `decoy_seismic` boundary instead of
  leaning on `class_weight` alone — `normal → decoy` false alarms drop
  28 → 4, so decoy precision jumps **0.417 → 0.826** and accuracy rises
  to 0.99877. Cost: one real decoy and one precursor row each slip to
  `normal` (recall −0.05 and −0.008). Clear net win.
- **Random Forest improves on both anomaly classes, no regression.**
  Decoy recall **0.900 → 0.950** (the one decoy it used to miss as
  `normal` is now caught) and precursor recall **0.554 → 0.570**
  (+2 rows); precision stays 1.000 on precursor, `normal` row unchanged.
- RF feature importances shift more than in v5: `displacement_mm`
  0.063 → 0.174 (up), `tilt_vibration_correlation` 0.114 → 0.063 (down).
  The imported decoys are vibration-only with flat displacement, which
  makes `displacement_mm` a sharper decoy-vs-precursor discriminator.

**Scope caveat (same as v5):** all v2 rows are in train, so this shows
"merging the confirmed decoy rows helps (or is neutral) on our own held-out
data" — not a re-measurement of generalisation *to* v2 (already covered in
`external/README.md`).

### Step 3 — should v2's 15,848 `normal` rows also be merged? **Recommendation: no.**

Analysed by `synthetic/analyze_v2_normal_merge_v6.py` (trains extra models,
writes no canonical artifacts). v2 normal rows were split 75 / 25
(seed 42): a `pool` available to merge, and a fixed `holdout` (~3,962
rows) never trained on, used to score the v2-normal false-alarm rate.
Three scenarios per model — **A** not merged, **B** + 75 % pool, **C** +
all 15,848 — each scored on our standard test set and on the holdout.

**The original motivation has already largely dissolved.** The 1.5 %
v2-normal → `subsidence_precursor` rate that prompted this question was
measured on the **v4** model. Run the same check on the **v6-base** RF
(no v2 normal merged) and it is already down to **0.15 %** (24 of 15,848):

| model, on all 15,848 v2 normal rows | → normal | → decoy | → precursor |
|---|---|---|---|
| v4 RF | 98.54 % | 0.00 % | **1.46 %** |
| **v6-base RF (no v2 normal merged)** | **99.85 %** | 0.00 % | **0.15 %** |

The v5 + v6 merges tightened the `normal` boundary enough as a side effect
that v2 normal barely trips it any more.

**What merging would do (A → B → C):**

| | our test set | v2-normal holdout (% → normal) |
|---|---|---|
| **RF** — A not merged | decoy 0.864 / 0.950, precursor 1.000 / **0.570** | **99.82 %** |
| **RF** — B +75 % | decoy 0.864 / 0.950, precursor 1.000 / 0.562 | 100.00 % |
| **RF** — C +all | decoy 0.864 / 0.950, precursor 1.000 / 0.587 | 100.00 % (in-sample) |
| **LR** — A not merged | decoy **0.826** / 0.950, precursor **1.000** / 0.603 | 88.3 % |
| **LR** — B +75 % | decoy **0.426** / 1.000, precursor **0.645** / 0.645 | 94.1 % |
| **LR** — C +all | decoy **0.377** / 1.000, precursor **0.491** / 0.653 | 95.2 % |

- **RF (our primary) gains essentially nothing.** Our-test metrics move
  within run-to-run noise (precursor recall wobbles ±1–2 rows); the
  v2-normal holdout goes 99.82 % → 100 %, i.e. ~7 rows in ~4,000. Not
  worth adding 15,848 single-class rows (+15 % dataset, all `normal`).
- **LR is actively harmed.** 12k–16k extra `normal` rows swamp the
  `class_weight="balanced"` compensation and loosen LR's minority
  boundaries: decoy precision collapses 0.83 → 0.43 → 0.38 and precursor
  precision 1.00 → 0.65 → 0.49 on our own test set. Its v2-normal
  behaviour improves but never becomes good (still 5–6 % misfire).
- If v2-style-noise robustness ever becomes a hard requirement (e.g.
  deploying on hardware whose noise resembles v2's), the better move is a
  **small targeted sample** (a few hundred rows across v2's nodes) to
  anchor the boundary without swamping the split — not all 15,848. No
  current evidence that is needed.

**Held for the follow-up decision, per the task.**

### v6 error deep-dive (final quality pass — `model/diagnose_v6_errors.py`)

Before locking v6 for submission, every remaining RF v6 error on our own
test set was traced row-by-row, to decide whether one more fix (like the
v4 offset-node feature) is worth making. **Conclusion: no — the error
profile is clean and the remaining misses are inherent to the signal, not
a fixable pattern.**

RF v6 test confusion matrix (rows = true, cols = pred):

| | → `normal` | → `decoy_seismic` | → `subsidence_precursor` |
|---|---|---|---|
| **`normal`** | 43,014 | 3 | **0** |
| **`decoy_seismic`** | 1 | 19 | **0** |
| **`subsidence_precursor`** | 52 | **0** | 69 |

**The two cells that would matter most are both zero:** `normal →
subsidence_precursor` = 0 (no false subsidence alarm anywhere in 43,017
test normal rows) and `decoy ↔ precursor` = 0 in both directions (the
model never confuses "harmless seismic noise" with "real precursor"). All
error mass is anomaly ↔ `normal`.

**(A) 1 `decoy_seismic → normal`** (recall 0.95). It is the **third and
last 15-min sample of `EVT_31`** (NODE_03, 2026-11-05 11:15). By that
sample the vibration spike is already spent — `vibration_rms` 0.32 → 0.08,
`vibration_duration` streak broken back to 0 — so the row genuinely reads
as baseline. The two earlier samples of the same decoy (10:45, 11:00) are
caught. This is a **labelling-boundary artifact** (a decoy "tail" sample,
the exact analogue of the precursor post-peak tail rows we *exclude* from
training), not a blind spot — there is no vibration signal left to detect.
Also note: NODE_03's permanent +4.9° tilt offset is correctly ignored here
(`tilt_deviation_from_node_baseline` = 0.0007) — the v4 offset fix is
holding.

**(B) 52 `subsidence_precursor → normal`** (recall 0.57 — the weak class).
The miss is **almost entirely early-buildup**:

| position in buildup | rows | caught | recall |
|---|---|---|---|
| by elapsed time — early (≤ 2 h since start) | 45 | 1 | **0.02** |
| by elapsed time — late (> 2 h) | 76 | 68 | **0.89** |
| by fraction start→peak — 0–25 % | 33 | 0 | **0.00** |
| 25–50 % | 30 | 14 | 0.47 |
| 50–75 % | 28 | 26 | 0.93 |
| 75–100 % | 30 | 29 | 0.97 |

Row-level detail confirms why: at the start of a buildup **every feature
is at baseline** — the injected signal follows an accelerating (squared)
curve, so at 15 % through the window only ≈ 2 % of the eventual magnitude
has appeared. E.g. `EVT_22` at t=0: `tilt_deviation` −0.002, `vibration_rms`
0.036 (baseline), `vibration_duration` 0, `displacement_persistence` 0,
`p_normal` = 0.97. There is objectively nothing there to separate from
`normal`. Missed-vs-caught median features make the threshold visible:
caught rows have `vibration_duration` 6, `displacement_persistence` 1,
`tilt_deviation` 1.17; missed rows have 0, 0, 0.10. The model starts
catching the episode once those derived features fire, around 40–50 %
through the buildup. The 8 *late*-phase misses are all `p_normal` ≈
0.50–0.53 — genuine decision-boundary coin-flips scattered across all five
test episodes, not a shared pattern.

This is the **same accelerating-buildup detection-lag documented for v4**
(see "Recall by buildup sub-phase" below). v5/v6 nudged late-phase recall
from ~0.95 (v4) to 0.89 (v6) — the imported v2 escalation rows added some
lower-amplitude precursor examples — but the early-phase floor is
unchanged and unchangeable with causal features: at frac < 25 % the row
*is* baseline.

**(C) 3 `normal → decoy_seismic`** (precision 0.864). All three share one
signature: a **2-sample `vibration_duration` streak** from an isolated
single-blip noise pop just clearing the node's robust vibration threshold,
with everything else at baseline. Context windows show the sample before
and after each are pure `normal`. The model correctly learned "short
vibration streak + no ground movement = `decoy_seismic`"; these three
`normal` rows accidentally mimic a mini version of it. Operational cost is
~nil — `decoy_seismic` is the *not-risky* class, so this is "flagged
harmless noise as harmless noise" on 3 rows in 43,017 (0.007 %).

**(D) `normal ↔ subsidence_precursor` = 0, `decoy ↔ precursor` = 0.**
Nothing to diagnose — stated explicitly because it is the property that
matters most for an early-warning system.

**Is any of this a fixable pattern like the offset bug?** No. The v4
offset-node bug was a true systematic blind spot — a whole class of inputs
(nodes carrying a stale permanent offset) was misread, and one feature
fixed it cleanly. The remaining v6 errors are different in kind:

- Early-buildup misses (44 of 52): the signal is mathematically absent at
  that point in an accelerating ramp. The only conceivable lever is a
  trend/velocity feature (displacement- or tilt-rate over a few hours),
  but at frac ≈ 0.15 the tilt slope (~0.05°/h) sits inside the sensor
  noise band (~0.1°/h), so it would not cleanly separate either — and it
  is a new feature + retrain + re-validation cycle immediately before
  submission.
- Late-phase near-misses (8), the decoy tail (1), the noise-pop
  `normal→decoy` (3): boundary coin-flips and edge cases, not shared
  structure. Threshold tuning could flip a few at a precision cost; not
  worth it.

**Recommendation: lock v6 / `random_forest_model_v6.joblib` as-is. No
further feature engineering before submission.** The error surface is
defensible as it stands: no false subsidence alarms, no anomaly-type
confusion, and every miss is either in a regime where the signal is not
yet physically present or a low-cost `normal ↔ decoy` boundary case. The
one systematic bug that ever existed is already fixed and confirmed
holding. Effective reliable warning lead time remains "buildup start +
~2 h" to peak (≈ 4 h before the labelled event for a 6 h buildup), which
is the honest claim to make in the slides.

### v6 files

`build_model_v6.py`, `random_forest_model_v6.joblib`,
`logistic_regression_model_v6.joblib`, `metrics_v6.json`,
`confusion_matrix_{random_forest,logistic_regression}_v6.png`,
`feature_importances_v6.png`, `diagnose_v6_errors.py` (the final
quality-pass deep-dive above), the dataset
`synthetic/simulated_mesh_data_v6_with_external.csv` (+
`synthetic/merge_v2_vibration_disturbance_v6.py`), and the analysis
`synthetic/analyze_v2_normal_merge_v6.py` (+ its
`synthetic/_v2_normal_merge_analysis_*.csv` outputs).

---

## Label definition

- **`subsidence_precursor`**: rows from `start_timestamp` through
  `subsidence_event_timestamp` (the peak), inclusive — the buildup phase
  we actually want to predict *before* the event, not the aftermath.
- **`decoy_seismic`**: rows from `start_timestamp` through `end_timestamp`
  of a decoy episode (decoys are a short spike with no buildup/tail
  distinction, so the whole window counts).
- **Excluded from train/test entirely: 158 rows** — the post-peak "tail"
  of the 18 real episodes (`subsidence_event_timestamp` to
  `end_timestamp`). These rows are a genuinely different regime
  (vibration/cracking settling while tilt/displacement stay permanently
  offset) that is neither "normal" nor the "buildup phase" target —
  labeling them either way would corrupt what the model is being asked to
  learn.
- **`normal`**: everything else.

## No-time-leakage: displacement_persistence

`synthetic/simulated_mesh_data.csv`'s `displacement_persistence` column
is **causal** — at each row it only asks "was there a vibration spike
start in the last ~2 hours, and is displacement elevated *right now*
(never a future value) vs. that spike's pre-spike baseline." This model
reads it directly from the CSV. `vibration_duration` and
`tilt_vibration_correlation` are also read directly and were already
causal as originally computed.

`tilt_deviation_from_node_baseline` (added this round) is **causal** too:
per node, `tilt_deg` minus a **trailing** 7-day rolling median of
`tilt_deg` — the window at each row uses only that row and earlier rows
for the same node, never anything later. The first hour of a node's
series has no full window and is filled with `0.0`. It reads ≈ 0 when a
node is merely parked on an old permanent tilt offset and goes clearly
positive only while tilt is actively climbing. Read straight from the
CSV; recomputed for all rows by `synthetic/add_tilt_baseline_feature.py`.

**Not used as a feature: `node_id`.** With 33 total episodes spread
across 10 nodes (several nodes have 2–4 episodes each), including
node_id risks the model partly memorizing "this physical node tends to
have events" instead of learning from generalizable sensor patterns.
`timestamp` is used only to build the chronological split, never as a
model input.

## Chronological train/test split

Split at **2026-10-15 00:00:00** (train = everything before, test =
on/after), chosen so both classes are well represented on both sides
across the full 120-day range:

| | Train (< Oct 15) | Test (≥ Oct 15) |
|---|---|---|
| Rows | 60,364 | 43,158 |
| `normal` | 59,998 | 43,017 |
| `subsidence_precursor` | 335 (13 episodes) | 121 (5 episodes) |
| `decoy_seismic` | 31 (9 episodes) | 20 (6 episodes) |

Substantially more test examples than either previous version (121 vs.
54 vs. 21 precursor rows; 20 vs. 7 vs. 4 decoy rows across the three
dataset versions).

## Features

`tilt_deg`, `vibration_rms`, `displacement_mm`, `crack_signal`,
`vibration_duration`, `tilt_vibration_correlation`,
`displacement_persistence`, `tilt_deviation_from_node_baseline`
(8 features, all causal/no-leakage). The 8th was added this round — see
"No-time-leakage" above and "The headline check" below.

## Models

Two interpretable baselines (no deep learning), both with
`class_weight="balanced"` to compensate for the extreme class imbalance
(~99.7% of rows are `normal`):

- **Logistic Regression**, in a `StandardScaler` + `LogisticRegression`
  pipeline (`logistic_regression_model.joblib`)
- **Random Forest**, `max_depth=6`, 200 trees (`random_forest_model.joblib`)

## Results (test set) — current (120-day) dataset, **8-feature model**

| Class | Logistic Regression P / R | Random Forest P / R | Support |
|---|---|---|---|
| `normal` | 0.999 / 0.999 | 0.999 / 1.000 | 43,017 |
| `decoy_seismic` | 0.357 / 1.000 | **0.857 / 0.900** | 20 |
| `subsidence_precursor` | 0.813 / 0.612 | **1.000 / 0.562** | 121 |

(P = precision, R = recall. Full report incl. F1 in `metrics.json`.
Accuracy: RF 0.9987, LR 0.9977.)

**Random Forest is the primary baseline.** With the offset-aware feature
added, RF now has **perfect `subsidence_precursor` precision (1.000)** and
— the point of this round — **zero decoy rows misclassified as
`subsidence_precursor`** (the v3 regression is gone; see next section).
The trade is a small `subsidence_precursor` recall dip (0.603 → 0.562,
73 → 68 of 121 rows), concentrated in late buildup. Logistic Regression
keeps its own long-standing weakness: `decoy_seismic` precision is still
only 0.357, and it now leaks 17 `normal` rows into `subsidence_precursor`
(was 8), dropping its precursor precision to 0.813.

## The headline check: does either model false-alarm on decoys?

**v3 had one Random Forest decoy → `subsidence_precursor` misclassification
(the first ever). This round it is fixed by adding an offset-aware tilt
feature — not by tuning it away.** Confusion matrices (`true → predicted`,
columns `[normal, decoy_seismic, subsidence_precursor]`), test set:

| | v3 (7 features) | **v4 (8 features, this round)** |
|---|---|---|
| RF `decoy_seismic` row | `[1, 18, 1]` — **1 → precursor** | `[2, 18, 0]` — **0 → precursor** ✅ |
| LR `decoy_seismic` row | `[1, 19, 0]` — 0 → precursor | `[0, 20, 0]` — 0 → precursor |
| RF `subsidence_precursor` row | `[48, 0, 73]` | `[53, 0, 68]` |
| LR `subsidence_precursor` row | `[47, 6, 68]` | `[47, 0, 74]` |

### Task 1 — the diagnosis (`model/diagnose_offset_node.py`)

The v3 false alarm was one 15-minute sample: `EVT_31` (`NODE_03`, decoy,
2026-11-05 11:00:00). Traced cause, confirmed by the script:

- `NODE_03` carries a **permanent +4.9° tilt offset** from two earlier
  real precursor episodes on that node (`EVT_06` +2.0°, `EVT_21` +2.9°).
  Its baseline `tilt_deg` by November sits at ~5.05° (verified: median
  0.145° before any episode → 2.15° after `EVT_06` → 5.05° after
  `EVT_21`), vs. near-zero on a pristine node.
- **No v3 feature encoded "tilt relative to this node's own recent
  baseline."** `tilt_deg` was fed as a **raw absolute value**;
  `displacement_persistence` is offset-aware but only for *displacement*;
  `tilt_vibration_correlation` is offset-invariant (so it doesn't flag a
  stale offset, but also can't tell the model the offset is stale).
- So at that one sample, with tilt noise transiently correlating with the
  decoy's vibration spike (`tilt_vibration_correlation = 0.587`) **on top
  of** an already-~5° `tilt_deg`, RF read the raw elevation as an active
  rise and called it a precursor. The Task 1 hypothesis — "raw `tilt_deg`
  instead of relative-to-node-baseline is the root cause" — is confirmed.

### Task 2 — the fix: `tilt_deviation_from_node_baseline`

Added by `synthetic/add_tilt_baseline_feature.py`: per node, `tilt_deg`
minus its **causal trailing 7-day rolling median** of `tilt_deg`
(672 samples; warm-up rows → 0.0; no future data). On this dataset it
separates the two regimes cleanly:

| Row type | median deviation | 90th pct | max |
|---|---|---|---|
| decoy-spike rows | **−0.00** | 0.03 | 0.04 |
| real precursor-buildup rows | **0.61** | 2.22 | 3.78 |

At the `EVT_31` misclassified sample specifically: `tilt_deg = 5.08` but
`tilt_deviation_from_node_baseline = 0.03` — the 7-day median has fully
absorbed the 23-day-old offset, so the feature correctly says "not
rising."

### Task 3 — result after retraining with the feature

- **Random Forest: the NODE_03-style misclassification is resolved.**
  `EVT_31`'s decoy rows are no longer called `subsidence_precursor`; the
  `decoy_seismic → subsidence_precursor` cell is **0** again (as in v1/v2).
  RF `subsidence_precursor` precision rises to a perfect **1.000** (no
  false positives from any class). Cost: two of `EVT_31`'s three decoy
  rows now fall to `normal` rather than being positively tagged
  `decoy_seismic` (decoy recall holds at 0.900), and late-buildup
  precursor recall dips (see next section). The dangerous error (a decoy
  raising a subsidence alarm) is gone; the remaining error (a decoy
  logged as quiet `normal` noise) is far cheaper.
- **Logistic Regression: still perfectly clean on the decoy → precursor
  cell (0/20), and now catches all 20 decoys (recall 0.95 → 1.00).** But
  its known imbalance problem is **not** fixed by this feature: decoy
  precision only nudges 0.328 → 0.357, and `normal → subsidence_precursor`
  leakage actually rises 8 → 17 rows, pulling precursor precision down to
  0.813 (from 0.895). The feature helps LR's recall, not its precision
  under imbalance.

## Recall by buildup sub-phase (early vs. late) — carried over, re-measured

**Question:** is the ~0.6 `subsidence_precursor` recall concentrated in
the early buildup (signal still close to baseline, genuinely hard) or
spread evenly (which would suggest more data could fix it)?

Computed by `model/diagnose_recall_by_phase.py`, bucketing true
`subsidence_precursor` test rows by elapsed hours since that episode's
`start_timestamp`: **early = ≤2 hours in, late = >2 hours in.**

| Model version | Overall recall | Early (≤2h) recall | Late (>2h) recall |
|---|---|---|---|
| v2 (60 days, 7 features, 54 test rows) | 0.667 | **0.111** (2/18) | **0.944** (34/36) |
| v3 (120 days, 7 features, 121 test rows) | 0.603 | **0.022** (1/45) | **0.947** (72/76) |
| **v4 (120 days, 8 features, 121 test rows)** | **0.562** | **0.022** (1/45) | **0.882** (67/76) |

**The early-phase finding is unchanged: the model essentially never
catches a precursor in its first 2 hours (~2–11% recall) across every
version.** Adding the offset-aware feature did **not** touch the early
number (1/45, identical to v3). What it did cost is **5 late-buildup
detections** (72/76 → 67/76, recall 0.947 → 0.882) — the feature is now
RF's single most important input (0.286), and leaning on it pulled a
handful of mid-buildup rows, where the deviation hasn't ramped yet, back
under the `subsidence_precursor` boundary. This is a real, if modest,
regression in late-phase recall, reported here rather than hidden: it is
the price of closing the offset-node false alarm. A sensitivity check
(`add_tilt_baseline_feature.py`, window length) found a longer rolling
window recovers some of it (14-day → 0.579 overall, 21-day → 0.595) while
keeping the decoy → precursor cell at 0; 7 days is kept as the
task-specified default, with the trade documented.

**Interpretation:** the buildup is generated with an accelerating
(squared) curve — at 2 hours into a 4–8.5 hour buildup, only a small
fraction of the total magnitude has developed (e.g. 2h into a 7.5h
buildup is 27% of the way through in time, but only (0.27)² ≈ 7% of the
way through in signal magnitude, since the curve is squared). That's
close enough to baseline noise that no baseline-vs-signal classifier
should be expected to catch it reliably. **This looks like a genuine
detection-lag tradeoff inherent to an accelerating-buildup precursor
signal, not a fixable data-volume problem** — which is exactly the
"early warning = harder to detect, later warning = easier to detect but
less useful" tension a real early-warning system has to manage. We are
reporting this as-is rather than tuning a threshold to inflate the early
number, per your instruction.

**Practical implication for the pitch:** on this data, the model's
*reliable* effective warning lead time is roughly "buildup start + 2
hours" to "peak," not the full buildup window — e.g. for a 6-hour
buildup, that's still ~4 hours of reliable advance warning before the
labeled event, which is a legitimate and useful claim; claiming the full
buildup window as "detected" would not be.

## Before / after: four versions compared

| | v1 (21d, 3+2, 7f) | v2 (60d, 9+8, 7f) | v3 (120d, 18+15, 7f) | **v4 (120d, 18+15, 8f)** |
|---|---|---|---|---|
| Total rows | 16,128 | 46,080 | 103,680 | 103,680 |
| Features | 7 | 7 | 7 | **8** (+`tilt_deviation_from_node_baseline`) |
| Test rows, `subsidence_precursor` | 21 | 54 | 121 | 121 |
| Test rows, `decoy_seismic` | 4 | 7 | 20 | 20 |
| RF `subsidence_precursor` P / R | 0.588 / 0.476 | 0.973 / 0.667 | 0.986 / 0.603 | **1.000 / 0.562** |
| RF `decoy_seismic` P / R | 0.000 / 0.000 | 0.350 / 1.000 | 0.857 / 0.900 | **0.857 / 0.900** |
| LR `subsidence_precursor` P / R | 0.769 / 0.476 | 1.000 / 0.519 | 0.895 / 0.562 | 0.813 / 0.612 |
| LR `decoy_seismic` P / R | 1.000 / 0.750 | 0.004 / 1.000 | 0.328 / 0.950 | 0.357 / 1.000 |
| Decoys → `subsidence_precursor` (RF) | 0 | 0 | **1 of 20** | **0 of 20** ✅ |
| Decoys → `subsidence_precursor` (LR) | 0 | 0 | 0 | 0 |
| RF late-buildup recall (>2h) | — | 0.944 | 0.947 | 0.882 |

**Honest read of v3 → v4:** the one thing this round set out to fix — RF
misreading a decoy on an offset node as a precursor — is fixed, and RF
`subsidence_precursor` precision went to a perfect 1.000 as a bonus (no
false positives from any class). It was **not** free: RF late-buildup
recall dropped 0.947 → 0.882 (−5 detections), because the new feature is
now the model's top input and a few mid-buildup rows fall on the wrong
side of it. LR gained decoy recall (0.95 → 1.00) but its imbalance-driven
precision problem is untouched — decoy precision still 0.36, and precursor
precision slipped to 0.81 as `normal` rows leaked in. Net: RF trades a
little recall for a cleaner, more trustworthy alarm; LR stays clean on the
one cell that matters but remains imprecise overall.

## Which model is the primary baseline?

> *v4-era analysis. The conclusion (Random Forest over Logistic
> Regression) still holds and carried through v5/v6 — the current locked
> model is `random_forest_model_v6.joblib`; see "Current Model — Summary"
> at the top. The table below is the original v4 comparison.*

**Random Forest.** Side by side:

| | Random Forest (v4) | Logistic Regression (v4) |
|---|---|---|
| `decoy_seismic` → `subsidence_precursor` | **0 / 20** | **0 / 20** |
| `subsidence_precursor` precision | **1.000** | 0.813 |
| `subsidence_precursor` recall | 0.562 | 0.612 |
| `decoy_seismic` precision / recall | **0.857** / 0.900 | 0.357 / 1.000 |
| `normal` rows leaked to an alarm class | 3 (all → decoy) | 53 (36 → decoy, 17 → precursor) |
| Overall accuracy | **0.9987** | 0.9977 |

**One-line reason:** RF gives a near-noise-free alarm — perfect precursor
precision, only 3 false alarms in 43,158 test rows, and the offset-node
decoy miss is now closed — at the cost of ~0.05 lower precursor recall
concentrated in late buildup; LR's decoy separation is equally clean on
the headline cell but it fires ~50 false alarms under the 99.7% `normal`
imbalance, which makes it unusable as the primary.

## What we didn't do

- Did **not** massage the early-buildup recall: no threshold retuning, no
  lookahead features, no oversampling of early rows. The ~2% first-2-hours
  figure is reported as measured, unchanged from v3.
- Did **not** tune the offset-node fix to also recover the lost
  late-buildup recall. A longer rolling window (14–21 days) would recover
  ~half of it while keeping the decoy→precursor cell at 0 — that option is
  documented in the phase-breakdown section, but 7 days (the
  task-specified default) is what ships, and the −5-detection cost is
  reported straight.
- Did **not** special-case `NODE_03` or any node id. The fix is a general
  per-node feature; `node_id` is still not a model input.

## Feature importances (Random Forest, v4)

| Feature | Importance |
|---|---|
| `tilt_deviation_from_node_baseline` | **0.286** |
| `vibration_duration` | 0.225 |
| `vibration_rms` | 0.192 |
| `tilt_vibration_correlation` | 0.115 |
| `displacement_mm` | 0.071 |
| `tilt_deg` | 0.051 |
| `displacement_persistence` | 0.049 |
| `crack_signal` | 0.012 |

See `feature_importances.png`. The four *derived* features
(`tilt_deviation_from_node_baseline`, `vibration_duration`,
`tilt_vibration_correlation`, `displacement_persistence`) now account for
**0.674** of total importance combined (up from 0.606), and the new
offset-aware feature is the single largest at 0.286. Raw `tilt_deg`
importance dropped 0.072 → 0.051 as the model shifted its tilt reasoning
onto the baseline-relative version.

## Files in this folder

- `build_model.py` — the full pipeline (labeling, split, training,
  evaluation, artifact saving); 8-feature model as of this round
- `diagnose_offset_node.py` — **Task 1**: the offset-node diagnosis
  (which decoy row RF misfired on, its feature vector vs. per-class
  medians, `NODE_03`'s tilt trajectory, and the check that no v3 feature
  encoded tilt-vs-node-baseline). Auto-detects whether the saved model is
  7- or 8-feature so it can be re-run pre- or post-fix.
- `diagnose_recall_by_phase.py` — early-vs-late buildup recall breakdown;
  loads the currently-saved Random Forest model, so re-run
  `build_model.py` first if you want the diagnostic to reflect a new model
- `random_forest_model.joblib`, `logistic_regression_model.joblib` —
  trained models
- `metrics.json` — full classification reports, confusion matrices, split
  info, feature importances
- `confusion_matrix_random_forest.png`, `confusion_matrix_logistic_regression.png`
- `feature_importances.png`

The `tilt_deviation_from_node_baseline` column itself is added to the CSV
by `synthetic/add_tilt_baseline_feature.py` (additive-only pass; see
`synthetic/README.md`).

## Limitations / honest caveats

- **Early-buildup detection is genuinely weak (~2–11% recall in the first
  2 hours)**, and this looks like an inherent property of an accelerating
  precursor signal rather than something more data will fix on its own —
  see the phase-breakdown section above. Unchanged by this round's feature.
- **Late-buildup recall regressed this round (0.947 → 0.882 for RF)** as
  the price of the offset-node fix. It is recoverable in part with a
  longer rolling-median window (documented), not pursued here. Worth
  revisiting once there is real data.
- **The offset-node fix is validated on exactly one occurrence.** Only
  one test decoy (`EVT_31`, `NODE_03`) ever landed on a node carrying a
  large stale tilt offset. The feature closes that case cleanly and
  separates the regimes well in aggregate (decoy deviation ≈ 0 vs.
  buildup ≈ 0.6), but "resolved on n=1" is the honest characterisation —
  re-check as more decoys land on previously-active nodes.
- **Still small sample sizes relative to typical ML datasets** — 20 decoy
  and 121 precursor test rows is enough to see clear, consistent patterns
  (as the phase breakdown shows), not enough for tight statistical
  confidence intervals.
- **Derived features were engineered specifically to separate decoy vs.
  precursor**, and `tilt_deviation_from_node_baseline` doubly so — it was
  designed against the exact failure it fixes. Its top-of-table importance
  partly validates the design on this synthetic set by construction; it is
  not yet evidence the same feature separates real earthquakes/blasting on
  a real offset node.
- **Still synthetic data end to end.** Per `synthetic/README.md`, the
  background displacement magnitudes are grounded in the Indian coalfield
  rates you provided (status: `[VERIFY]`), but the anomaly burst sizes and
  decoy shapes are engineering assumptions, not measured. Retraining on
  real hardware logs, in the same schema, is the required next step
  before this model informs any real early-warning decision.
