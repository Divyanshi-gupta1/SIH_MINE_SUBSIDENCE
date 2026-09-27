# hardware_integration/ — real sensor readings → RF v6 → false-alarm-guarded alerts

Bridges the 3-node hardware (MPU-9250/6500 + ultrasonic, LoRa 433 MHz TDM, receiver on the laptop's serial port)
to `model/random_forest_model_v6.joblib`. Nothing outside this folder was modified (the old synthetic datasets,
`model/`, `external/`, `clean_data/` are untouched). Read **`FORMAT_AUDIT.md`** first — it lists the format
mismatches, and two things I could not verify (the sketch's serial format; the model has 3 classes, not 7).

## Files

| file | role |
|---|---|
| `FORMAT_AUDIT.md`, `audit_format.py` | **Task 1.** Training-feature audit (`--training`) and a probe that reads real serial lines / a saved log and reports units, rate, resolution, mismatches (`--probe COM5`) |
| `sensor_conversion.py` | **Task 2.** Parse → int16 counts / cm → g / dps / cm → per-node windows → calibration (unit scales, tilt & displacement zero, noise floors) → **sanity gate** → model-frame sample |
| `feature_engine.py` | Streaming version of the 4 derived features, bit-exact vs the training CSV |
| `guardrails.py` | **Task 3.** Persistence + confidence logic |
| `inference_pipeline.py` | Ties it together: `MineGuardPipeline.feed_line(t, line)`; fast verified RF inference (1 ms vs 130 ms) |
| `run_live.py` | Live/replay runner: console status, per-sample CSV, alerts, calibration save/load |
| `test_static_no_movement.py` | **Task 4a.** 5-min static test, asserts `normal` on every sample |
| `test_vibration_only.py` | **Task 4b.** Vibration-only test, asserts `decoy_seismic`, never a subsidence class |
| `test_pipeline_units.py` | 38 unit/end-to-end checks (`python -m unittest test_pipeline_units`) |
| `sim_source.py`, `sources.py`, `harness_common.py`, `config.py` | simulator of the raw stream, serial/replay sources, shared harness code, all tunables |

## Run order on the bench

```bash
cd hardware_integration
pip install pyserial                                   # already installed in ../.venv
python audit_format.py --probe COM5 --lines 300        # 1. what does the sketch really send? fix config.py / a JSON override
python test_static_no_movement.py --source serial --port COM5 --nodes 1,2,3            # 2. keep still, ~6 min
python test_vibration_only.py    --source serial --port COM5 --nodes 1,2,3             # 3. shake table when prompted, don't tilt
python run_live.py --port COM5                          # 4. live, alerts, calibration saved to calibration.json
```
Anything wrong in the assumed format is a JSON override, not a code change:
`--config my.json` with e.g. `{"columns": ["node","ax","ay","az","gx","gy","gz","dist"], "accel_fs_g": 4, "dist_unit": "mm", "displacement_sign": -1, "sample_period_s": 3}`.
`--source sim` (default) runs the same harness on a simulated stream — it prints a banner, and its pass means
"the logic works", **not** "the hardware is fine". Exit codes: 0 PASS · 1 FAIL · 2 INVALID (no usable data / node was
moved / no vibration burst — says nothing about the model). Reports go to `reports/*.json|csv` (every sample, features, class probabilities).

## Guardrails (Task 3)

* **No single-reading alert.** A model sample = one `sample_period_s` window of readings (bench: 2 s). An alert needs the
  **same risk class as top vote, p ≥ 0.70, for N consecutive samples**, N = ⌈`persist_window_s` / `sample_period_s`⌉ = 4 (= 8 s, inside the 5–10 s window).
* **Status per sample:** `NORMAL` · `DECOY` (vibration-only, benign, logged) · `POSSIBLE` (risk vote that is below 0.70 — never counts toward the streak and resets it — or above but < N in a row) · `CONFIRMED` (fires the alert **once**, latched until 3 non-risk samples).
* A gap of > 1 missing window (LoRa loss) breaks "consecutive"; a class change breaks it.
* **Vibration-only defence is upstream of the model**, in the conversion layer: tilt and displacement are soft-thresholded at each node's *measured* noise floor, and that floor widens with the window's own scatter, because vibration makes accel-derived tilt and the ultrasonic mount noisier — exactly when the model would otherwise see "vibration + a bit of tilt/displacement".
* **Risk class = anything not `normal` and not in `decoy_classes`**, so a retrained 7-class model works without code changes.

## Evidence — all on *simulated* sensors (my noise model), through the real RF v6

`sim_source.py` emits raw int16 counts and ultrasonic cm with MPU-9250-class noise (4 mg/reading, 1.5 mm ultrasonic, 1 % no-echo, 0.5 % stray echoes).
It is my assumption of real sensor behaviour, not a measurement.

**1. Why the noise-floor handling exists** (6 seeds × 3 nodes × 120 s = 1,350 samples per row; vibration ×8 for 6 s):

| conversion | static: risk votes | vibration-only: risk votes | burst samples read as `decoy_seismic` |
|---|---|---|---|
| no deadband (naive unit conversion) | **307** (23 %) | **338** | 2 % |
| fixed deadband, not widened per window | 0 | **36** | 33 % |
| **adopted** (calibrated + per-window adaptive) | **0** | **0** | **100 %** |

**2. Noise robustness** (3 seeds × 3 nodes each): accel noise 4 / 12 / 30 mg, ultrasonic 1.5 / 5 mm, integer-cm ultrasonic, and combinations → **0 risk votes, 0 lone decoy votes, 100 % of burst samples `decoy_seismic`** in all 6 conditions.

**3. Burst length** (training decoys last 2–4 samples): bursts of 4 s … 40 s (2–20 samples, `vibration_duration` up to 21) → 100 % `decoy_seismic`, 0 risk votes, 0 POSSIBLE.

**4. The guardrails cost sensitivity — positive control** (accelerating ramps shaped like the training precursors, 5 seeds each):

| Δtilt / Δdisp / vibration | POSSIBLE first at (% of ramp) | CONFIRMED |
|---|---|---|
| 3.8° / 33 mm / ×7.8 | 34–51 % | 5/5, at 78–90 % |
| 2.4° / 22 mm / ×6.0 | 46–70 % | 3/5, at 110–122 % (after the peak) |
| 1.8° / 17 mm / ×4.5 | 52–72 % | 3/5, at 107–142 % |
| 1.3° / 12 mm / ×3.8 | 72–90 % | **0/5** (POSSIBLE only) |

Large events are confirmed before the peak; mild ones only reach `POSSIBLE`. That is the price of a ~0.4° tilt / ~2 mm displacement
noise floor + 4-in-a-row + 0.70. Knobs: `noise_k_tilt` / `noise_k_disp`, `persist_window_s`, `confirm_confidence`. For calibration: an earlier build with tighter floors (tilt 4σ, displacement 3σ, `1.5×p95`) confirmed the 2.4° case 5/5 but let 1 lone risk vote (POSSIBLE, never CONFIRMED) through in 1 of 18 high-noise runs (12 / 30 mg); I chose the wider floors because false alarms were the stated priority.

**5. Unit/logic tests: 38/38 pass**, including: streaming features == training CSV on all 103,680 rows; impossible values (tilt 91°/175°, −50 mm displacement, gravity 1.6 g, moving node, no-echo, saturation) are dropped and a stub model records **zero** calls for them; guardrail sequences (single 0.99 vote → POSSIBLE; 4×0.9 → one alert; 0.65 in the middle resets; exactly 0.70 counts; latch/re-arm); both harness evaluators can PASS, FAIL and INVALID (the FAIL path was also run end-to-end: exit 1 with the offending samples printed).

## Limitations you should know about

1. **No real-hardware run has happened.** Every number above is simulated. The serial format, MPU full-scale, ultrasonic unit, mount direction (`displacement_sign`) and TDM rate are assumptions until `--probe` says otherwise. The serial reader was tested only over a pyserial `loop://` port.
2. **Time compression is untested extrapolation.** The model was trained at 1 sample / 15 min; on the bench one 2-s window plays that role, so "8 s persistence" is 4 model samples. The 7-day tilt baseline becomes ~22 min. Use `--profile field` (900 s samples, N = 3 → 45 min) for a real deployment; the 5–10 s window is a bench-demo setting.
3. **Recall is inherited from the model** (`model/README.md`: 57 % of buildup rows, first quarter of a buildup is inherently invisible) and reduced further by the guardrails (table 4).
4. **Static test strictness:** every non-normal vote fails it, including a lone benign `decoy_seismic` (seen ~1 per 1,350 static samples — one event, rough). With 3 nodes × 5 min (≈450 samples) that is roughly a 28 % chance of a spurious FAIL. Use `--allow-decoy-blips 1` if you decide that is acceptable; risk-class votes stay at 0 by default.
5. **Vibration scaling is an assumption:** the node's own rest vibration is mapped to the training rest level (0.031) because the synthetic README calls the unit arbitrary. If real vibration should be compared in absolute g, set `vib_normalization: "none"` and retrain.
6. **Slow drift is not handled:** ultrasonic temperature drift (~1.7 mm/°C at 1 m) and MPU zero-g drift (~0.09°/°C) look like creeping displacement/tilt; sketch-side temperature compensation is needed (see FORMAT_AUDIT §4).
7. `calibration.json` holds the zero references — delete it (or `--recalibrate`) when a node is re-installed; keep it across restarts so accumulated displacement isn't reset.
8. The real fix for all of this is retraining on real logs (`--raw-log` saves replayable lines; `reports/*.csv` has the model-frame features) — the synthetic README already says so.
