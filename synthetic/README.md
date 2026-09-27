# synthetic/ — simulated ESP32/LoRa mesh data

## What this is

**This is 100% synthetic, computer-generated data. It is NOT a real sensor
reading from any hardware.** It was produced by
`synthetic/generate_synthetic_data.py` to have the exact same shape/schema
that our real ESP32/Arduino mesh nodes will output — timestamp, node_id,
tilt_deg, vibration_rms, displacement_mm, crack_signal — so we can build
and test the anomaly-detection model architecture (Part 4) before the
physical hardware exists. Once real nodes are deployed, **this file must
be replaced with actual logged sensor data in the same schema**, and the
model retrained/recalibrated on real readings — the numbers here are
plausible, not measured.

## Files

- `simulated_mesh_data.csv` — **103,680 rows**: **10 simulated nodes**
  (`NODE_01`…`NODE_10`), one reading every 15 minutes, over **120 days**
  (2026-08-01 to 2026-11-28). Built up in five passes:
  `generate_synthetic_data.py` produced the original 21-day/16,128-row run
  (8 nodes, 3 precursor episodes); `add_decoy_episodes.py` patched in the
  first 2 decoy episodes and the 3 derived feature columns;
  `extend_dataset.py` extended to 60 days and added 6 more precursor + 6
  more decoy episodes; `extend_dataset_v2.py` extended to 120 days,
  introduced 2 brand-new nodes (`NODE_09`, `NODE_10`), and added 9 more
  precursor + 7 more decoy episodes; finally `add_tilt_baseline_feature.py`
  appended one more derived column, `tilt_deviation_from_node_baseline`,
  **without adding rows or touching any existing column**. Each pass
  verified programmatically that it left every previously-existing row's
  values byte-identical before saving — see "Extending the dataset" below.
- `events_log.csv` — **33 rows**, one per injected episode (**18** real
  precursor episodes + **15** decoy episodes): which node, event type,
  when it started, when it peaked, when it ends, and the magnitudes used.

## Columns in simulated_mesh_data.csv

| Column | Meaning |
|---|---|
| `timestamp` | Reading time, 15-minute resolution |
| `node_id` | Which of the 8 simulated mesh nodes |
| `tilt_deg` | Simulated tilt/inclination reading, in degrees |
| `vibration_rms` | Simulated vibration sensor RMS reading (unitless MEMS accelerometer RMS, "g"-scale — arbitrary but consistent units since no real accelerometer has been selected/calibrated yet) |
| `displacement_mm` | Simulated cumulative ground displacement at that node, in millimeters, since the start of the record |
| `crack_signal` | 0/1 — simulated binary crack-detection sensor reading |
| `vibration_duration` | Derived feature: length (in samples) of the current consecutive run where `vibration_rms` is above that node's robust baseline threshold (median + 4×scaled-MAD), reset to 0 the moment a reading drops back below it. See "Derived features" below. |
| `tilt_vibration_correlation` | Derived feature: rolling 2-hour (8-sample) Pearson correlation between `tilt_deg` and `vibration_rms` for that node. NaN for the first 7 samples of a node's series is filled with 0. |
| `displacement_persistence` | Derived feature: 0/1 flag, **causal** — at each row, checks whether a vibration spike started in the last ~2 hours *and* `displacement_mm` right now (no future lookup) is more than 0.5mm above that spike's pre-spike baseline. Note: earlier in this project this column briefly held a retrospective/future-peeking version built only for a verification plot; `extend_dataset.py` replaced it with this causal version everywhere, since the retrospective version would leak future information if used as a model feature (see `model/README.md`). |
| `tilt_deviation_from_node_baseline` | Derived feature, **causal**: `tilt_deg` minus that node's trailing **7-day rolling median** of `tilt_deg` (672 samples; `min_periods=4`, warm-up rows filled with `0.0`). Near zero when a node is simply parked on a **stale permanent tilt offset** left by an old precursor episode (the median has caught up to the new level), and clearly positive only while tilt is **actively climbing** faster than a 7-day median can track — i.e. during a real buildup. Added by `add_tilt_baseline_feature.py` after the Part 4 diagnosis (`model/diagnose_offset_node.py`) traced a decoy→precursor misclassification on `NODE_03` to the model reading that node's stale +4.9° offset (from `EVT_06` + `EVT_21`) as a fresh rise, because every other feature fed `tilt_deg` only as a raw absolute value. |

## How the magnitudes were grounded (and where they were NOT)

You asked for these numbers to be grounded in real Indian coalfield rates
rather than picked arbitrarily. Here's exactly what was and wasn't
grounded, and why — please don't cite the tilt/burst numbers below as if
they came from the InSAR papers; they didn't.

### Directly grounded: `displacement_mm` background trend

Each node was assigned a **regional annual subsidence rate** drawn from
the ranges you gave me:

- Raniganj coalfield: roughly **21 mm/year**
- Jharia coalfield: roughly **29 mm/year** typical, **80–120 mm/year** in
  hotspots

| Node | Assigned annual rate | Rationale |
|---|---|---|
| NODE_01 | 21 mm/yr | Raniganj-typical |
| NODE_02 | 29 mm/yr | Jharia-typical |
| NODE_03 | 25 mm/yr | Raniganj/Jharia blend |
| NODE_04 | 29 mm/yr | Jharia-typical |
| NODE_05 | 80 mm/yr | Jharia hotspot (lower end) |
| NODE_06 | 21 mm/yr | Raniganj-typical |
| NODE_07 | 120 mm/yr | Jharia hotspot (upper end) |
| NODE_08 | 29 mm/yr | Jharia-typical |
| NODE_09 | 29 mm/yr | Jharia-typical (added in the 120-day extension, node installed 2026-09-30) |
| NODE_10 | 100 mm/yr | Jharia hotspot range (added in the 120-day extension, node installed 2026-09-30) |

Each node's annual rate was converted to a small **daily background
drift** (rate ÷ 365 ≈ 0.06–0.33 mm/day) with realistic Gaussian sensor
noise layered on top. This is why the non-anomalous displacement values
in the CSV stay small and slow-moving — that's the actual physical scale
implied by the cited studies over a 21-day window (roughly 1–7 mm of
"normal" background creep, depending on the node).

**These exact numbers are still [VERIFY]** — see `reference/` (Part 3)
for the placeholder tracking where the source papers need to be linked
and the precise figures confirmed. The 21/29/80/120 mm/yr figures used
here came directly from what you specified in this conversation, not
from a paper I looked up myself.

### NOT directly grounded — explicit engineering assumptions

- **Anomaly burst magnitudes** (`added_tilt_deg`: 1.8–3.6°;
  `added_displacement_mm`: 17–31mm per episode; vibration multiplier:
  4.5–7.5×): the InSAR studies report *regional annual averages*, not the
  size of a single localized precursor burst over a few hours. The burst
  sizes here are a reasoned assumption — that an accelerating local
  failure precursor could plausibly release on the order of 15–30mm of
  displacement in a matter of hours (a meaningful fraction of even a
  hotspot node's annual budget, concentrated into one episodic event
  rather than spread evenly across the year). This is a modeling choice
  for demo purposes, not a cited figure.
- **`tilt_deg` values in general**: InSAR measures vertical surface
  displacement, not inclinometer/tilt-sensor readings, so tilt has no
  direct InSAR analog. Baseline resting tilt (0.05–0.30°) and the
  anomaly-episode tilt increase (1.8–3.6°) instead follow common
  geotechnical monitoring convention, where tiltmeter changes of roughly
  1–2° are treated as a "watch" threshold and several degrees as
  "critical" — a standard-practice assumption, not a citation.
- **`vibration_rms` baseline and multiplier**: no reference cited; picked
  to give a clearly separable but not cartoonish signal (ambient noise
  floor vs. a 4.5–7.5× rise during the precursor buildup).

## How the real precursor episodes work

18 episodes total (the original 3 + 6 from `extend_dataset.py` + 9 from
`extend_dataset_v2.py`), spread across all 10 nodes (`NODE_09`/`NODE_10`
included) and varied in magnitude/duration so a model can't overfit to
one episode's exact shape, `event_type = subsidence_precursor` in
`events_log.csv`:

| event_id | node | buildup starts | subsidence_event (peak) | tail ends | Δtilt | Δdisplacement | vib. multiplier |
|---|---|---|---|---|---|---|---|
| EVT_01 | NODE_02 | 2026-08-07 08:00 | 2026-08-07 14:00 | 2026-08-07 16:00 | 2.4° | 22.0mm | 6.0× |
| EVT_02 | NODE_05 | 2026-08-12 20:00 | 2026-08-13 03:00 | 2026-08-13 05:00 | 3.6° | 31.0mm | 7.5× |
| EVT_03 | NODE_07 | 2026-08-19 15:00 | 2026-08-19 20:00 | 2026-08-19 23:00 | 1.8° | 17.0mm | 4.5× |
| EVT_06 | NODE_03 | 2026-08-25 05:00 | 2026-08-25 10:00 | 2026-08-25 12:00 | 2.0° | 19.0mm | 5.5× |
| EVT_07 | NODE_06 | 2026-08-30 08:00 | 2026-08-30 16:00 | 2026-08-30 19:00 | 3.0° | 26.0mm | 6.8× |
| EVT_08 | NODE_08 | 2026-09-04 18:00 | 2026-09-04 22:00 | 2026-09-04 23:30 | 1.5° | 14.0mm | 4.0× |
| EVT_09 | NODE_01 | 2026-09-10 00:30 | 2026-09-10 07:00 | 2026-09-10 09:00 | 2.8° | 24.0mm | 7.0× |
| EVT_10 | NODE_04 | 2026-09-18 05:30 | 2026-09-18 13:00 | 2026-09-18 15:30 | 3.3° | 29.0mm | 6.0× |
| EVT_11 | NODE_02 | 2026-09-25 12:30 | 2026-09-25 18:00 | 2026-09-25 20:00 | 2.2° | 20.0mm | 5.0× |
| EVT_18 | NODE_09 (new node) | 2026-10-03 03:00 | 2026-10-03 09:00 | 2026-10-03 11:00 | 2.3° | 21.0mm | 5.8× |
| EVT_19 | NODE_10 (new node) | 2026-10-06 06:30 | 2026-10-06 15:00 | 2026-10-06 18:00 | 3.8° | 33.0mm | 7.8× |
| EVT_20 | NODE_01 | 2026-10-09 16:30 | 2026-10-09 21:00 | 2026-10-09 22:30 | 1.6° | 15.0mm | 4.2× |
| EVT_21 | NODE_03 | 2026-10-12 23:00 | 2026-10-13 06:00 | 2026-10-13 08:30 | 2.9° | 25.0mm | 6.3× |
| EVT_22 | NODE_05 | 2026-10-17 07:00 | 2026-10-17 12:00 | 2026-10-17 14:00 | 2.0° | 18.0mm | 5.0× |
| EVT_23 | NODE_07 | 2026-10-21 11:30 | 2026-10-21 18:00 | 2026-10-21 20:00 | 2.6° | 23.0mm | 6.6× |
| EVT_24 | NODE_02 | 2026-10-27 04:00 | 2026-10-27 08:00 | 2026-10-27 09:30 | 1.3° | 12.0mm | 3.8× |
| EVT_25 | NODE_04 | 2026-11-01 06:00 | 2026-11-01 14:00 | 2026-11-01 17:00 | 3.4° | 30.0mm | 7.2× |
| EVT_26 | NODE_06 | 2026-11-06 14:30 | 2026-11-06 20:00 | 2026-11-06 22:00 | 2.2° | 20.0mm | 5.4× |

Buildup durations range 4–8.5 hours and burst magnitudes range Δtilt
1.3–3.8°, Δdisplacement 12–33mm, vibration ×3.8–7.8 across the 18
episodes — deliberately varied rather than reusing one fixed shape for
every episode. `NODE_09` and `NODE_10` are simulated as newly-installed
mesh nodes with no data before 2026-09-30 (their displacement trend is
measured relative to their own installation date, not backdated) — see
"Extending the dataset" below. During the buildup window, tilt/vibration/displacement all ramp up along
an *accelerating* (squared, not linear) curve — meant to mimic the
tertiary-creep-style acceleration described in real precursor-detection
literature, where movement speeds up rather than increasing steadily.
`crack_signal`'s probability of flipping to 1 also rises non-linearly as
the peak approaches, and is forced to 1 at the peak sample itself. After
the peak, vibration and cracking partially relax back toward baseline
over the tail window, but `tilt_deg` and `displacement_mm` keep their
full added offset permanently — because real ground movement doesn't
reverse itself once it's happened.

## Decoy false-alarm episodes — why they exist

A model trained only on the 3 real episodes above could learn the wrong
lesson: "high `vibration_rms` = subsidence risk." In practice, mines see
plenty of vibration spikes that have nothing to do with subsidence —
nearby earthquakes, blasting from an adjacent panel or quarry, heavy
equipment passing. A model that alarms on vibration magnitude alone would
false-positive constantly on these. **The decoy episodes exist to force
the model to learn the actual distinguishing pattern**: a real precursor
is a *slow, multi-hour, accelerating, multi-sensor* buildup with a
lasting displacement/tilt offset; a decoy is a *short, sharp, single-sensor*
vibration spike that leaves no lasting trace. That's also what the 3
derived feature columns are for — they make this distinction explicit and
queryable instead of leaving it implicit in the raw waveform.

15 decoy episodes total (the original 2 + 6 from `extend_dataset.py` + 7
from `extend_dataset_v2.py`), `event_type = decoy_seismic` in
`events_log.csv`, mixing sharp (earthquake-like) and broader
(blasting-like) shapes with varied peak magnitude and duration:

| event_id | node | shape | spike window | peak | vibration multiplier | tilt/displacement added |
|---|---|---|---|---|---|---|
| EVT_04 | NODE_01 | sharp | 2026-08-04 08:45–09:15 (30 min, 3 samples) | 09:00 | ×9.0 | 0 (flat) |
| EVT_05 | NODE_04 | broad | 2026-08-15 10:45–11:30 (45 min, 4 samples) | 11:00 | ×6.5 | 0 (flat) |
| EVT_12 | NODE_05 | sharp | 2026-08-24 08:45–09:15 (30 min, 3 samples) | 09:00 | ×8.0 | 0 (flat) |
| EVT_13 | NODE_07 | broad | 2026-08-29 13:30–14:15 (45 min, 4 samples) | 14:00 | ×5.8 | 0 (flat) |
| EVT_14 | NODE_03 | sharp | 2026-09-02 10:45–11:15 (30 min, 3 samples) | 11:00 | ×7.2 | 0 (flat) |
| EVT_15 | NODE_06 | broad | 2026-09-07 15:45–16:30 (45 min, 4 samples) | 16:15 | ×6.2 | 0 (flat) |
| EVT_16 | NODE_08 | sharp | 2026-09-14 07:45–08:15 (30 min, 3 samples) | 08:00 | ×9.4 | 0 (flat) |
| EVT_17 | NODE_01 | broad | 2026-09-22 18:30–19:15 (45 min, 4 samples) | 19:00 | ×5.2 | 0 (flat) |
| EVT_27 | NODE_08 | sharp | 2026-10-11 09:45–10:15 (30 min, 3 samples) | 10:00 | ×8.5 | 0 (flat) |
| EVT_28 | NODE_09 (new node) | broad | 2026-10-20 13:30–14:15 (45 min, 4 samples) | 14:00 | ×6.0 | 0 (flat) |
| EVT_29 | NODE_10 (new node) | very sharp | 2026-10-24 08:45–09:00 (15 min, 2 samples) | 09:00 | ×9.8 | 0 (flat) |
| EVT_30 | NODE_01 | broad | 2026-10-29 15:30–16:15 (45 min, 4 samples) | 16:00 | ×5.5 | 0 (flat) |
| EVT_31 | NODE_03 | sharp | 2026-11-05 10:45–11:15 (30 min, 3 samples) | 11:00 | ×7.6 | 0 (flat) |
| EVT_32 | NODE_05 | broad | 2026-11-09 16:30–17:15 (45 min, 4 samples) | 17:00 | ×6.4 | 0 (flat) |
| EVT_33 | NODE_07 | sharp | 2026-11-13 07:45–08:15 (30 min, 3 samples) | 08:00 | ×9.0 | 0 (flat) |

Peak vibration multipliers range ×5.2–9.8 across the 15 decoys, including
one deliberately even-sharper 2-sample/15-minute spike (EVT_29) to widen
the shape variety beyond the original sharp/broad pair. All decoys only
ever scale that node's *existing* `vibration_rms`
reading at each spike timestamp (so the natural sensor-noise shape is
preserved, just amplified) — `tilt_deg` and `displacement_mm` are left
completely untouched (no buildup, no offset), `crack_signal` is forced to
`0` throughout, and every row outside the spike window is untouched, so
`vibration_rms` jumps back to baseline on the very next 15-minute sample
— no gradual relaxation tail like the real episodes have. In the derived
columns, this shows up as a short `vibration_duration` streak (2–4
samples, vs. episodes that build for tens of samples), no sustained rise
in `tilt_vibration_correlation`, and `displacement_persistence` staying
at `0`.

The `events_log.csv` schema wasn't changed to accommodate decoys — for a
`decoy_seismic` row, `subsidence_event_timestamp` means "the peak of the
vibration spike" (not an actual subsidence event), `buildup_hours` means
"total spike duration" (there's no separate buildup phase), and
`added_tilt_deg`/`added_displacement_mm` are `0.0` since decoys add
neither.

Every one of the 10 nodes now carries at least one episode (several carry
two or three, of mixed types, at well-separated times) — there is no
subset of nodes that are pure baseline for the whole record. See the two
tables above for exactly which node has which episode(s) and when.

## Derived features — how they're computed

Recomputed by `extend_dataset_v2.py` across the **whole** 120-day,
103,680-row dataset (all 10 nodes), per node — including the original 21
and 60 days, so the robust thresholds below reflect each node's full
history, not just an earlier slice of it:

- **`vibration_duration`**: each node's baseline vibration threshold is
  `median(vibration_rms) + 4 × scaled_MAD(vibration_rms)` (robust to the
  handful of spike/episode rows). The column counts how many consecutive
  samples (including the current one) have stayed above that threshold,
  resetting to 0 as soon as a reading drops back below it.
- **`tilt_vibration_correlation`**: rolling Pearson correlation between
  `tilt_deg` and `vibration_rms` over the trailing 8 samples (2 hours).
  Real episodes rise together on both sensors, so this trends positive
  during a buildup; decoys move vibration alone, so this stays low/noisy.
- **`displacement_persistence`**: **causal.** At each vibration-spike
  start (a rising edge above the threshold), records the pre-spike
  baseline (mean `displacement_mm` in the hour before). For every row up
  to ~2 hours after that spike start, flags `1` if *current* displacement
  (never a future value) is more than 0.5mm above that baseline, `0`
  otherwise — decays back to `0` once 2 hours have passed since the last
  spike start. True (and staying true past the 2-hour window, since the
  offset is permanent) for real episodes; false for decoys, by
  construction, since decoys never move `displacement_mm` at all.
- **`tilt_deviation_from_node_baseline`**: **causal.** Added later by
  `add_tilt_baseline_feature.py` (not `extend_dataset_v2.py`). Per node,
  `tilt_deg` minus its **trailing 7-day rolling median** of `tilt_deg`
  (window = 672 samples at 15-min cadence; `min_periods=4`, so the first
  hour of a node's series — with no usable window — is filled with `0.0`,
  the same warm-up convention `tilt_vibration_correlation` uses). The
  rolling window at row *t* uses only rows ≤ *t* for that node, so no
  future data leaks in. It sits near `0` when a node just carries a stale
  permanent tilt offset (the 7-day median has risen to meet it) and goes
  clearly positive only during an **active** multi-hour tilt climb —
  giving the model a way to tell "still elevated from an old event" from
  "rising right now." On this dataset: median ≈ 0.00 on decoy-spike rows,
  ≈ 0.6 (90th pct ≈ 2.2) on real precursor-buildup rows.

**Note on old rows:** because the first three derived columns are
recomputed over the full extended series each time, all previously-existing
rows' raw sensor columns (`tilt_deg`, `vibration_rms`, `displacement_mm`,
`crack_signal`) stay byte-identical across every extension, but those three
*derived* columns for the same rows may differ very slightly between file
versions — a longer history shifts each node's robust threshold
marginally. `tilt_deviation_from_node_baseline` was instead added in a
single additive pass that recomputed nothing else, so it did not perturb
any existing column. All of this is expected, not a bug, and has been
verified programmatically after every pass.

## Extending the dataset

Two row-appending extension passes plus one additive-column pass, all
verified programmatically (asserted and printed) to leave every
previously-existing row's raw sensor values byte-identical:

- **`extend_dataset.py`** (21 days -> 60 days): appended 39 more days
  (2026-08-22 to 2026-09-29). Each of the original 8 nodes' new baseline
  was calibrated from the **last 2 clean days (2026-08-20 to 2026-08-21)
  of its own existing data**: resting tilt/vibration level and noise
  scale from the median/std of that window, and the displacement trend
  continued using the same regional mm/yr rate (see table above) plus a
  fitted offset from that window — which automatically carries forward
  any permanent tilt/displacement offset already left by a node's earlier
  episode, with no special-casing needed.
- **`extend_dataset_v2.py`** (60 days -> 120 days): appended another 60
  days (2026-09-30 to 2026-11-28) using the same calibration approach for
  `NODE_01`–`NODE_08` (this time from their last 2 clean days,
  2026-09-27 to 2026-09-29), and introduced **`NODE_09`/`NODE_10`** as
  brand-new nodes with no data before 2026-09-30 — simulating two mesh
  nodes installed partway through the deployment, rather than fabricating
  60 days of history for hardware that didn't exist yet. Their fresh
  baseline parameters (resting tilt/vibration, noise scale) were drawn in
  the same ranges the original generator used, and their
  `displacement_mm` trend is measured relative to *their own* 2026-09-30
  installation date, not backdated to the project's original 2026-08-01
  start. They were assigned regional rates of 29 mm/yr (`NODE_09`,
  Jharia-typical) and 100 mm/yr (`NODE_10`, within the Jharia hotspot
  range) — see `reference/indian_subsidence_context.md` for the same
  `[VERIFY]` caveat that applies to all these regional-rate figures.
- **`add_tilt_baseline_feature.py`** (additive column, no new rows):
  appended `tilt_deviation_from_node_baseline` (causal per-node 7-day
  rolling-median tilt deviation — see "Derived features" above) and
  asserted all 9 pre-existing columns were byte-identical afterwards. This
  pass was motivated by the Part 4 offset-node diagnosis
  (`model/diagnose_offset_node.py` / `model/README.md`): a decoy on
  `NODE_03` was being read as a precursor because the node's stale +4.9°
  tilt offset from `EVT_06` + `EVT_21` looked, to a model fed only raw
  `tilt_deg`, like an active rise.

## When real hardware exists

1. Replace `simulated_mesh_data.csv` with real logs from the ESP32/LoRa
   mesh, in the same 6 raw-sensor columns (the 4 derived feature columns
   can be recomputed on real data using the same logic in
   `add_decoy_episodes.py` and `add_tilt_baseline_feature.py`).
2. Replace `events_log.csv` with real, manually- or sensor-confirmed
   subsidence-precursor AND decoy/false-alarm event timestamps once any
   occur (or leave empty if none have been observed yet) — keeping both
   event types is important, not just the real ones, so the model keeps
   learning the distinction on real-world data too.
3. Re-run/retrain the Part 4 model on the real data — the synthetic
   magnitudes here are a reasonable placeholder for demoing the pipeline,
   not a substitute for calibration against actual sensor behavior.
4. Revisit the assumptions above (especially the un-cited burst
   magnitudes and tilt thresholds) once real precursor events are
   captured, since those numbers were never meant to be final.
