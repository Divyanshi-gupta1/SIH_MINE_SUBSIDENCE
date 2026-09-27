# virtual_simulator/: TeraSense Live Demo

A local web app that plays the part of the three-node hardware, so the model pipeline can be demonstrated
and tested when the physical testbed is not on the table. Move a slider or press a preset; the zones sink and
tilt on screen, and the real MineGuard pipeline says what it thinks.

## What this is, and what it is not

* **It is** a virtual stand-in for the sensors. You set tilt, vibration and displacement per node; the backend
  converts those into raw MPU int16 counts and ultrasonic centimetres in the serial format the hardware is
  assumed to send, and feeds those lines to the existing pipeline exactly as `run_live.py` would.
* **It is not** a model, and it changes none. Every class, confidence, POSSIBLE / CONFIRMED status and alert on
  screen comes from `hardware_integration/` (`sensor_conversion.py` -> `feature_engine.py` -> RF v6 ->
  `guardrails.py`). Nothing here re-implements or tunes prediction logic.
* **It is not evidence about real hardware.** The sensor noise is the simulator assumption from
  `hardware_integration/sim_source.py`, not a measurement. A good run here means the demo and the pipeline
  logic work, not that the physical testbed will read the same.

## Team boundary

```
hardware_integration/   model team      untouched, only imported
synthetic/ model/ clean_data/ reference/ external/         untouched
virtual_simulator/      simulator team  everything below
  backend/
    app.py        FastAPI server: REST for controls, WebSocket for live push, serves the frontend
    engine.py     slider state, virtual clock, presets, alert log; imports the pipeline
    selftest.py   headless checks (see "Checking it")
  frontend/       index.html, style.css, main.js, assets/house.svg  (no CDN, works offline)
  requirements.txt
```

`engine.py` imports three things from `hardware_integration/` and copies none of them:

| import | used for |
|---|---|
| `MineGuardPipeline` (`inference_pipeline.py`) | serial line -> unit conversion, calibration and sanity gate -> streaming features -> RF v6 -> persistence and confidence guardrails |
| `SimSensors` (`sim_source.py`) | physical values -> raw counts in the serial format `node,ax,ay,az,gx,gy,gz,dist` |
| `PipelineConfig`, `TRAIN` (`config.py`) | the same bench settings and the model's resting vibration level |

## Run it

From the project root (the folder that contains `hardware_integration/`):

```bash
# Windows, using the project's existing environment (scikit-learn, pandas, numpy, joblib already in it)
.venv\Scripts\python.exe -m pip install -r virtual_simulator\requirements.txt
.venv\Scripts\python.exe virtual_simulator\backend\app.py
```

It prints `Loading model...`, then `Ready: http://127.0.0.1:8000`, and opens your browser. The first start takes
about 15 s (model load plus its self-check); later starts are quicker. Options:

```
--port 8080        another port          --no-browser   do not open a browser
--seed 3           different sensor noise; the same seed replays the same demo exactly
```

Stop it with Ctrl+C in that terminal.

## Using it

* **Sliders**, per node: Tilt 0 to 5 degrees, Vibration 0 to 1 g, Displacement 0 to 50 mm. Dragging one cancels
  a running preset. The ground changes gradually (tilt 0.6 deg/s, displacement 8 mm/s) because the ground does not
  jump, and the pipeline's own sanity gate rejects displacement steps above 50 mm per sample.
* **Vibration** is the extra vibration on top of a quiet node, in the model's g scale (a quiet node reads 0.031).
  The reading is not an exact readback: each 2 s sample is noisy, and it lands roughly at the slider value plus
  the quiet level (0.19 g on the slider read anywhere from about 0.19 to 0.29 in my runs).
* **Presets**
  * *Normal*: all sliders ease back to zero.
  * *Vibration only*: a 15 s vibration burst (0.25 g) on all three nodes; tilt and displacement never move.
  * *Full progression*: accelerating build-up, Zone 1, then Zone 1 and 2 from 35 s, then Zone 1, 2 and 3 from
    70 s (each ramp 68 s to 3.8 deg, 33 mm, 0.21 g extra vibration; the shape of the training precursors and of
    the positive control in `hardware_integration/README.md`). About 2.5 minutes at 1x.
  * *Reset*: back to a fresh calibrated start; clears alerts and graphs and re-arms the model's per-node state.
* **1x / 2x / 4x** plays simulated time faster. The pipeline still sees one 2 s window per sample, so results do
  not change, only how long you wait.
* **Node detail** (click a node dot, a health card, or the tabs): measured tilt, vibration and displacement, the
  model's class and confidence, the three class probabilities, the guardrail count, the raw serial line, and the
  eight features the model was fed.
* **Colours**: green normal, amber anomaly (vibration-only or a possible risk vote), red high-risk with the
  alert confirmed. The scene exaggerates movement (tilt x2, 1.2 px per mm) and says so on screen.

## What to expect, and what surprises people

Measured on the real RF v6 with the simulated stream (`python virtual_simulator/backend/selftest.py`, seed 0):

| run | result |
|---|---|
| 4 min, nothing moving | 360 samples, 0 risk votes, 0 alerts |
| Vibration only | every node reads *Vibration-only event* (about 99% confidence), 0 risk votes |
| Full progression | alerts confirm at about T+55 s (Zone 1), T+103 s (Zone 2), T+119 s (Zone 3) |

Things worth knowing before you present:

1. **The model has three classes, not seven**: `normal`, `decoy_seismic`, `subsidence_precursor`. The dashboard
   shows what the model really outputs; "high risk" is `subsidence_precursor`. (Same finding as
   `hardware_integration/FORMAT_AUDIT.md`.)
2. **Sliders do not map linearly to classes.** The model was trained on precursors that combine rising tilt and
   displacement *with* raised vibration. So: a large tilt and displacement with no vibration reads `normal`
   (a static offset is exactly what the static test requires to be normal); tilt 3.8 deg, 33 mm and 0.21 g reads
   as a precursor within about 20 s; vibration at or near the 1 g maximum reads as *vibration only*, because heavy
   shaking hides tilt and displacement by design (that is the false-alarm guardrail); mid-range values can flip
   between *vibration only* and *possible*. **Full progression is the dependable route to red.**
3. **The alert shown is the guardrail's latched alert.** The guardrail latches a confirmed alert until 3 samples
   in a row show no risk, but the per-sample status still dips to POSSIBLE on a single low-confidence vote. The
   dashboard shows the latched state (so nodes do not blink red and amber) and shows the per-sample verdict in
   Node detail. The latch rule is the guardrail's own, using its `is_risk()` and `clear_n`; it does not feed back
   into the model.
4. **Time is compressed.** One 2 s window plays the role of a 15-minute training sample, so the model's 672-sample
   tilt baseline is about 22 minutes of simulated time. If you hold a deformed state for long, the baseline
   catches up and an alert can clear while the ground is still deformed. See limitation 2 in
   `hardware_integration/README.md`.
5. **Measured is not the same as set.** Node detail shows both ("Ground" and "slider"). Vibration adds noise to
   the accelerometer's tilt estimate, so measured tilt wanders more when vibration is high.

## Checking it

```bash
.venv\Scripts\python.exe virtual_simulator\backend\selftest.py
```

Runs the engine headless in fast-forward and checks the three runs above, plus that `hardware_integration/`,
`synthetic/`, `model/`, `clean_data/`, `reference/` and `external/` are unchanged afterwards (same files, sizes
and modification times, including `__pycache__`). Exit code 0 means all pass. Importing the pipeline is done
with bytecode writing switched off so nothing is written into `hardware_integration/`.

## Troubleshooting

* *Port already in use*: `--port 8080`.
* *`Disconnected, retrying` in the top bar*: the server stopped; the page reconnects by itself once it is back.
* *`ModuleNotFoundError: fastapi`*: run with the project's `.venv` Python, after the `pip install` above.
