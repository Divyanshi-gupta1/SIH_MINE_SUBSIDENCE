# Task 1 — Format audit: synthetic training data vs real hardware readings

Model audited: `model/random_forest_model_v6.joblib` (RF, 200 trees, depth 6, 8 features) trained on
`synthetic/simulated_mesh_data_v6_with_external.csv` (103,960 rows). Numbers below come from
`python audit_format.py --training` (→ `training_feature_stats.json`); nothing in `synthetic/`, `external/`
or `model/` was modified.

## 0. Two things to confirm before trusting anything below

1. **The model in this repo has 3 classes, not 7.** `rf.classes_ = [decoy_seismic, normal, subsidence_precursor]`.
   I found no trace of `local_anomaly / persistent / correlated / progressive / high_risk` anywhere in the repo
   (grep over all code, READMEs and notebooks; the project docx only lists Elk Creek URLs). "High-risk" therefore maps to
   `subsidence_precursor`. If a 7-class model exists elsewhere, point `MODEL_PATH` in `config.py` at it: the
   guardrails treat *every class that is neither `normal` nor in `decoy_classes` as a risk class*
   (`test_extra_risk_classes_are_picked_up`), and the feature order is re-checked against
   `model.feature_names_in_` at load, so a model with different features fails loudly instead of silently.
2. **I could not see your Arduino sketch or any real serial output** (no `.ino`, no log on this machine). The
   serial format in §2 is an **assumption**. `python audit_format.py --probe COM5` reads real lines and prints
   exactly which of the mismatches below apply. Run it before anything else.

## 1. What the model was trained on

One row = one node, one **15-minute** sample. 8 model inputs (order = `model.feature_names_in_`):

| # | feature | unit / meaning | min | p1 | median | p99 | max |
|---|---|---|---|---|---|---|---|
| 1 | `tilt_deg` | degrees, absolute inclination. Rest 0.05–0.30°; nodes carry permanent offsets after events (median 3.0°, up to 6.9°) | −0.04 | 0.07 | 3.04 | 6.81 | 6.89 |
| 2 | `vibration_rms` | "g-scale", **arbitrary but consistent units** (synthetic README: no real accelerometer was selected). Rest median 0.031 (0.015–0.05); decoy/precursor peaks ×4–10 | 0.000 | 0.010 | 0.031 | 0.073 | 0.527 |
| 3 | `displacement_mm` | mm, **cumulative since start of record** (0.06–0.33 mm/day drift + 12–33 mm event steps) | −0.19 | 0.09 | 29.2 | 75.9 | 79.5 |
| 4 | `crack_signal` | 0/1 crack sensor | 0 | 0 | 0 | 0 | 1 |
| 5 | `vibration_duration` | samples above per-node threshold `median+4·1.4826·MAD` | 0 | 0 | 0 | 0 | 55 |
| 6 | `tilt_vibration_correlation` | Pearson r, trailing 8 samples | −0.99 | −0.79 | 0.00 | 0.80 | 0.99 |
| 7 | `displacement_persistence` | 0/1: displacement > pre-spike mean + 0.5 mm within 8 samples of a vibration spike | 0 | 0 | 0 | 0 | 1 |
| 8 | `tilt_deviation_from_node_baseline` | degrees; `tilt − trailing 672-sample median` | −0.13 | −0.06 | 0.00 | 3.30 | 3.85 |

Class medians (normal / decoy / precursor): `vibration_rms` 0.031 / 0.161 / 0.076 · `tilt_vibration_correlation`
−0.004 / 0.175 / 0.635 · `tilt_deviation` 0.003 / −0.002 / 0.771 · `vibration_duration` 0 / 5 / 4.
Synthetic noise: tilt σ 0.015–0.03°, displacement σ 0.03–0.08 mm. A decoy = 2–4 samples of ×5–10 vibration with
tilt/displacement untouched; a precursor = 4–8.5 h accelerating ramp of Δtilt 1.3–3.8°, Δdisp 12–33 mm, vibration ×3.8–7.8.
`node_id` and `timestamp` are **not** model inputs.

## 2. What the hardware sends (assumed — confirm with `--probe`)

Per node, over LoRa/TDM to the receiver, printed on serial. Assumed line (`config.PipelineConfig.columns`, editable;
a header line or `key=value` lines are also parsed):

```
node,ax,ay,az,gx,gy,gz,dist        e.g.  2,-59,839,16384,-28,42,19,100.03
```
MPU-9250/6500 raw = int16 counts (1 g = 16384 counts at ±2 g, 8192/4096/2048 at ±4/8/16 g; gyro 131 LSB/dps at ±250);
ultrasonic = distance in cm (mm / metres / echo-µs also supported via `dist_unit`).

## 3. Mismatches and how the conversion layer resolves each

| # | Mismatch | Effect if ignored | Handling (file) |
|---|---|---|---|
| 1 | **Cadence**: 15 min/sample in training vs a reading every second or so | All 4 derived features are counted *in samples* (8-sample correlation, 672-sample baseline, 2–5-sample decoys). Raw 1 Hz readings would make them meaningless | Readings are aggregated per node into one model sample per `sample_period_s` (bench 2 s; `field` profile 900 s = training cadence). Time-compressed bench mode = each window plays the role of a 15-min sample. `sensor_conversion.WindowAggregator` |
| 2 | **Units**: raw counts vs degrees / "g-scale" / mm | Nonsense features | Accel scale is read off gravity (a still node must read 1 g → detects g / m/s² / counts+FS, else calibration is refused). Tilt = angle between window-mean gravity vector and the install reference (mount-orientation independent, always 0–180°). `calibrate()`, `summarize()` |
| 3 | **Tilt zero**: training = absolute, resting 0.05–0.30°; hardware = whatever the mount is | An arbitrary mount angle looks like a stale offset | Zeroed at calibration, then `+0.175°` (midpoint of the generator's resting range) so a fresh node looks like a day-0 training node |
| 4 | **Tilt noise**: training σ ≈ 0.02°; accel-only tilt over ~10 readings ≈ 0.07° (MPU-9250 300 µg/√Hz) and ×N under vibration | Model trees split on `tilt_deviation ≈ 0.1°`: **5 % of static samples voted `subsidence_precursor`** in my simulation; vibration-only runs voted precursor | Noise-floor soft-threshold on tilt (`noise_k_tilt`=5σ), σ measured at calibration **and** from each window's own scatter, so it widens during vibration. `make_sample()` |
| 5 | **Vibration units**: `vibration_rms` is arbitrary "g-scale" | Real MPU rest RMS is ~4 mg, training rest is 0.031 | RMS of `|a|` about calibrated gravity, rescaled so the node's own rest level = 0.031 (`vib_scale`). This *assumes* the model reads vibration relative to baseline — justified only because the synthetic README calls the unit arbitrary; check on real data |
| 6 | **Displacement**: training = cumulative mm, noise 0.05 mm; hardware = ultrasonic distance, noise ≈ 1–3 mm, possibly integer-cm (10 mm steps) | Ping jitter trips `displacement_persistence` (0.5 mm rule) → "vibration + displacement" = precursor | Per-window median (rejects no-echo `0` and stray echoes), zero = calibration distance, `displacement_sign=+1` (distance grows = subsidence — **confirm mount direction**), soft-threshold deadband = max(4σ, resolution step, 1 mm) widened by each window's scatter |
| 7 | **`crack_signal`**: no crack sensor on the 3-node hardware | Missing column | Constant 0. RF importance 0.9 %; forcing 0 on the v6 test set leaves the v6 test-set confusion matrix identical (rows = true, cols = `[normal, decoy_seismic, subsidence_precursor]`: `[43014,3,0] [1,19,0] [52,0,69]`, matching `model/README.md`) and precursor recall on all 632 precursor rows 0.837 → 0.837 |
| 8 | **Derived-feature logic** | Recomputing them "sensibly" would drift from what the trees learned | `feature_engine.py` re-implements the training code streaming; verified **bit-exact on all 103,680 rows** (max diff 1e-4 = CSV rounding). Includes a training quirk: `vibration_duration` counts **2,3,4…** for a run (the pre-run row falls in the group, `cumcount()+1`), not 1,2,3 — the model was fitted on that, so it is replicated, not fixed |
| 9 | **Vibration spike threshold** is a per-node constant from full history | No history on a new node | Frozen from the calibration windows (training rule), floored at 1.5× median (training thresholds are 1.6–2.2×; a quantised MAD would otherwise sit on the median) |
| 10 | **Tilt baseline** = 672-sample median (7 days) | On the bench 672 samples = 22 min at 2 s, so the baseline chases a slow ramp faster than in training | Not fixable without changing time scale; documented limitation. `field` profile restores 7 days |
| 11 | **Extra hardware fields** (temperature, RSSI/SNR, seq) | — | Ignored (not model inputs) |
| 12 | **Physically impossible readings** | Garbage in → confident wrong answer | Dropped, never fed to the model, counted by reason: tilt outside 0–90°, negative displacement beyond noise, gravity ≠ 1 g ± 0.2, gyro > 15 dps (node being handled), distance ≤ 2 cm / ≥ 400 cm / no echo, int16 saturation, > 50 mm jump per sample, wrong field count / non-numeric. 15 consecutive dropped windows → `SENSOR_FAULT` event |

## 4. Hardware-side risks I can name but cannot fix in software

* **Ultrasonic temperature drift** ≈ 0.17 %/°C of range (≈ 1.7 mm/°C at 1 m) — larger than the 0.5 mm persistence rule and slow, so it looks like creeping displacement. Needs a temperature-compensated distance (speed of sound) in the sketch.
* **MPU zero-g offset drift** ≈ ±1.5 mg/°C (≈ 0.09°/°C; datasheet order of magnitude, verify for your part): a day/night swing of 10 °C moves tilt by ~1°. Log the MPU temperature and compensate, or the 7-day-median feature will chase it.
* **Integer-cm ultrasonic output** (`pulseIn()/58` with `int`) gives 10 mm resolution vs 12–33 mm total precursor displacement. Print floats or raw echo µs. `--probe` flags this.
* **Reading rate**: a window needs ≥ 3 readings/node (`min_readings_per_sample`); `--probe` prints the achievable `sample_period_s` from the measured TDM rate.
