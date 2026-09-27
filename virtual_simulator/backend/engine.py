"""
Virtual mine-subsidence simulator engine.

This module owns NO model or prediction logic. Everything that turns a reading into a verdict is
imported from hardware_integration/ and used as-is:

    SimSensors            (sim_source.py)         physical values  -> raw int16 MPU counts + ultrasonic cm
                                                  in the assumed serial format  node,ax,ay,az,gx,gy,gz,dist
    MineGuardPipeline     (inference_pipeline.py) serial line -> sensor_conversion (units, calibration,
                                                  sanity gate) -> feature_engine -> RF v6 -> guardrails
                                                  (persistence + confidence -> POSSIBLE / CONFIRMED)

What lives here is only the simulator around them: the slider state, a virtual clock, the preset
scripts and the bookkeeping the dashboard needs (history, alert log, node health).

Time is virtual. The pipeline takes an explicit timestamp with every line, so the simulator can
calibrate the three nodes instantly at start-up and can play at 1x / 2x / 4x. One model sample is
still one `sample_period_s` (2 s) window of simulated time, exactly as on the bench.
"""
from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

sys.dont_write_bytecode = True          # importing must not write __pycache__ into hardware_integration/

ROOT = Path(__file__).resolve().parents[2]
HI_DIR = ROOT / "hardware_integration"
if str(HI_DIR) not in sys.path:
    sys.path.insert(0, str(HI_DIR))

from config import MODEL_PATH, TRAIN, PipelineConfig                       # noqa: E402  (hardware_integration)
from inference_pipeline import MineGuardPipeline, RFPredictor, SampleOutput   # noqa: E402
from sim_source import SimSensors                                          # noqa: E402

NODES = (1, 2, 3)                       # N1..N3 == Zone 1..3
RAW_HZ = 5.0                            # raw readings per node per simulated second (as sim_source.py)
CALIB_S = 60.0                          # still time fed at start-up: 40 s calibration + margin

# slider ranges (spec)
LIMITS = {"tilt": (0.0, 5.0), "vib": (0.0, 1.0), "disp": (0.0, 50.0)}
# How fast the ground may change, per simulated second. Ground does not jump, and the pipeline's own
# sanity gate rejects displacement steps > 50 mm per sample; this keeps a slider slam physical.
SLEW = {"tilt": 0.6, "vib": 4.0, "disp": 8.0}

AMBIENT_VIB = TRAIN.VIB_BASELINE_MEDIAN   # 0.031 -- the model-frame level of a quiet node
SPEEDS = (1.0, 2.0, 4.0)

CLASS_LABELS = {
    "normal": "Normal",
    "decoy_seismic": "Vibration-only event",
    "subsidence_precursor": "Subsidence precursor",
}


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _ramp(tau: float, start: float, length: float) -> float:
    """Accelerating (t^2) build-up, the shape of the training precursors; 0 before `start`, 1 after."""
    return _clamp((tau - start) / length, 0.0, 1.0) ** 2


# ------------------------------------------------------------------------------------------------
# Preset scripts: functions of script time tau (simulated s) -> {node: {field: value}}
# ------------------------------------------------------------------------------------------------
VIB_ONLY_LEVEL = 0.25          # ~8x the resting level, what the decoy tests use
VIB_ONLY_SECONDS = 15.0

PROGRESSION_STARTS = {1: 0.0, 2: 35.0, 3: 70.0}    # Zone 1 -> Zone 1+2 -> Zone 1+2+3
PROGRESSION_RAMP_S = 68.0                          # 34 model samples, like the pipeline's positive control
PROGRESSION_HOLD_S = 20.0
PROGRESSION_PEAK = {"tilt": 3.8, "disp": 33.0, "vib": AMBIENT_VIB * (7.8 - 1.0)}   # dtilt 3.8 deg, 33 mm, x7.8


def _vibration_only(tau: float) -> dict:
    v = VIB_ONLY_LEVEL if tau < VIB_ONLY_SECONDS else 0.0
    return {n: {"tilt": 0.0, "disp": 0.0, "vib": v} for n in NODES}


def _full_progression(tau: float) -> dict:
    out = {}
    for n, t0 in PROGRESSION_STARTS.items():
        f = _ramp(tau, t0, PROGRESSION_RAMP_S)
        out[n] = {k: PROGRESSION_PEAK[k] * f for k in ("tilt", "disp", "vib")}
    return out


def _progression_label(tau: float) -> str:
    if tau >= max(PROGRESSION_STARTS.values()) + PROGRESSION_RAMP_S + PROGRESSION_HOLD_S:
        return "Sequence complete. Press Normal or Reset."
    if tau < PROGRESSION_STARTS[2]:
        return "Stage 1 of 3: Zone 1 subsiding"
    if tau < PROGRESSION_STARTS[3]:
        return "Stage 2 of 3: Zone 1 and 2 subsiding"
    return "Stage 3 of 3: Zone 1, 2 and 3 subsiding"


class Script:
    def __init__(self, name: str, fn, duration: float, label_fn=None, title: str = ""):
        self.name, self.fn, self.duration, self.label_fn, self.title = name, fn, duration, label_fn, title
        self.tau = 0.0

    @property
    def done(self) -> bool:
        return self.tau >= self.duration

    def label(self) -> str:
        return self.label_fn(self.tau) if self.label_fn else self.title


def _vibration_only_label(tau: float) -> str:
    if tau >= VIB_ONLY_SECONDS:
        return "Burst finished. Tilt and displacement never moved."
    return "Vibration burst on all nodes. Tilt and displacement stay put."


PRESETS = {
    "vibration_only": lambda: Script("vibration_only", _vibration_only, VIB_ONLY_SECONDS, _vibration_only_label),
    "full_progression": lambda: Script(
        "full_progression", _full_progression,
        max(PROGRESSION_STARTS.values()) + PROGRESSION_RAMP_S + PROGRESSION_HOLD_S, _progression_label),
}


# ------------------------------------------------------------------------------------------------
class Simulator:
    """Slider state + virtual clock + the imported MineGuard pipeline. Not thread-safe: drive it from
    one event loop (app.py does)."""

    def __init__(self, seed: int = 0, predictor: RFPredictor | None = None):
        self.cfg = PipelineConfig.load(None, "bench")
        self.predictor = predictor if predictor is not None else RFPredictor()
        self.seed = seed
        self.speed = 1.0
        self._acc = 0.0
        self._event_id = 0
        self.reset()

    # ---------------- lifecycle ----------------
    def reset(self):
        """Back to a clean, calibrated, all-quiet start (also re-arms the model's per-node state)."""
        self.targets = {n: {"tilt": 0.0, "vib": 0.0, "disp": 0.0} for n in NODES}
        self.actual = {n: dict(v) for n, v in self.targets.items()}
        self.script: Script | None = None
        self.history = {n: deque(maxlen=200) for n in NODES}
        self.events: deque = deque(maxlen=60)
        self.latest: dict = {}
        self.raw_last: dict = {}
        self.last_status: dict = {}
        self.alert_active = {n: False for n in NODES}    # display copy of the guardrail's latch (see _latch)
        self._nonrisk_run = {n: 0 for n in NODES}
        self.pending_samples: list = []
        self.pending_events: list = []
        self._live = False
        self._acc = 0.0

        self.pipe = MineGuardPipeline(self.cfg, predictor=self.predictor, on_event=self._pipe_event)
        self.sim = SimSensors(nodes=NODES, raw_rate_hz=RAW_HZ, seed=self.seed)
        for n in NODES:                       # physical values -> raw counts, read live at every reading
            self.sim.vib_factor[n] = lambda t, n=n: 1.0 + self.actual[n]["vib"] / AMBIENT_VIB
            self.sim.tilt_extra_deg[n] = lambda t, n=n: self.actual[n]["tilt"]
            self.sim.disp_extra_mm[n] = lambda t, n=n: self.actual[n]["disp"]

        self.t = 0.0
        self._k = 0
        for _ in range(int(CALIB_S * RAW_HZ)):           # installed and held still: instant, not real-time
            self._cycle(script_and_ease=False)
        missing = [n for n in NODES if not self.pipe.is_calibrated(f"NODE_{n:02d}")]
        if missing:
            raise RuntimeError(f"start-up calibration failed for nodes {missing}: {self.pipe.events[-3:]}")
        self.t_live0 = self.t
        self._live = True
        self._log(0.0, None, "info", "Simulator ready", "3 nodes calibrated. Move a slider or pick a preset.")

    # ---------------- controls ----------------
    def set_values(self, node: int, **vals):
        """Manual slider input. Takes over from any running preset."""
        if node not in NODES:
            raise ValueError(f"node must be one of {NODES}")
        for k, v in vals.items():
            if k not in LIMITS:
                raise ValueError(f"unknown field {k!r}")
            lo, hi = LIMITS[k]
            self.targets[node][k] = _clamp(float(v), lo, hi)
        self.script = None

    def apply_preset(self, name: str):
        if name == "reset":
            self.reset()
        elif name == "normal":
            self.script = None
            for n in NODES:
                self.targets[n] = {"tilt": 0.0, "vib": 0.0, "disp": 0.0}
        elif name in PRESETS:
            self.script = PRESETS[name]()
        else:
            raise ValueError(f"unknown preset {name!r}; choose from normal, reset, {', '.join(PRESETS)}")

    def set_speed(self, speed: float):
        if speed not in SPEEDS:
            raise ValueError(f"speed must be one of {SPEEDS}")
        self.speed = speed

    # ---------------- time ----------------
    @property
    def t_live(self) -> float:
        return self.t - self.t_live0

    def advance_wall(self, wall_dt: float) -> int:
        """Advance by a wall-clock interval (scaled by speed). Returns raw cycles run."""
        self._acc += min(wall_dt, 0.5) * self.speed * RAW_HZ     # cap: a stalled laptop must not fast-forward
        n = int(self._acc)
        self._acc -= n
        for _ in range(n):
            self._cycle()
        return n

    def advance_virtual(self, seconds: float):
        """Advance by simulated seconds with no wall-clock wait (self-test, fast-forward)."""
        for _ in range(int(round(seconds * RAW_HZ))):
            self._cycle()

    def _cycle(self, script_and_ease: bool = True):
        dt = 1.0 / RAW_HZ
        if script_and_ease:
            self._script_step(dt)
            self._ease(dt)
        for tt, line in self.sim.lines(1.0001 / RAW_HZ, t0=self._k * dt):    # one TDM cycle: N1, N2, N3
            self.raw_last[int(line.split(",", 1)[0])] = line
            for o in self.pipe.feed_line(tt, line):
                self._on_sample(o)
        self._k += 1
        self.t = self._k * dt

    def _script_step(self, dt: float):
        s = self.script
        if s is None or s.done:
            return
        s.tau += dt
        for n, vals in s.fn(min(s.tau, s.duration)).items():
            for k, v in vals.items():
                lo, hi = LIMITS[k]
                self.targets[n][k] = _clamp(v, lo, hi)

    def _ease(self, dt: float):
        for n in NODES:
            for k, slew in SLEW.items():
                a, tgt = self.actual[n][k], self.targets[n][k]
                self.actual[n][k] = a + _clamp(tgt - a, -slew * dt, slew * dt)

    # ---------------- results ----------------
    def _pipe_event(self, t, node, kind, msg):
        if not self._live or kind in ("calibrated", "ALERT"):    # ALERT is logged from the sample below
            return
        n = int(node.split("_")[-1])
        level = {"SENSOR_FAULT": "critical", "WARNING": "warning"}.get(kind, "info")
        self._log(t - self.t_live0, n, level, kind.replace("_", " ").capitalize(), msg)

    def _on_sample(self, o: SampleOutput):
        if not self._live:
            return
        n = int(o.node.split("_")[-1])
        self._latch(n, o)
        rec = {
            "node": n, "t": round(o.t - self.t_live0, 2),
            # what the sensor chain measured, after unit conversion (charts)
            "tilt": o.diag["tilt_raw_deg"], "vib": o.features["vibration_rms"], "disp": o.diag["disp_raw_mm"],
            # what the model was actually fed (after the noise-floor gate)
            "features": o.features,
            "probs": {k: round(v, 4) for k, v in o.probs.items()},
            "top_class": o.top_class, "top_p": round(o.top_p, 4), "status": o.status,
            "risk_class": o.risk_class, "streak": o.streak, "need": o.need,
            "alert_fired": o.alert_fired, "note": o.note, "alert_active": self.alert_active[n],
        }
        self.history[n].append(rec)
        self.latest[n] = rec
        self.pending_samples.append(rec)
        self._track_status(n, rec)

    def _latch(self, n: int, o: SampleOutput):
        """Display copy of the guardrail's latch. guardrails.AlertGuard documents that a CONFIRMED alert
        stays latched until `clear_n` non-risk samples in a row (it neither re-fires nor flaps), but the
        per-sample status it returns still dips to POSSIBLE on a single low-confidence vote. The dashboard
        shows the latched state so a node does not blink red/yellow. Same rule, same config, same
        is_risk() as the guard; nothing here feeds back into the model or the guard."""
        if o.status == "CONFIRMED":
            self.alert_active[n], self._nonrisk_run[n] = True, 0
        elif self.alert_active[n]:
            guard = self.pipe.nodes[o.node].guard
            self._nonrisk_run[n] = 0 if guard.is_risk(o.top_class) else self._nonrisk_run[n] + 1
            if self._nonrisk_run[n] >= self.cfg.clear_n:
                self.alert_active[n] = False

    def _track_status(self, n: int, rec: dict):
        prev = self.last_status.get(n)
        cur = "CONFIRMED" if rec["alert_active"] else rec["status"]
        self.last_status[n] = cur
        if cur == prev or (prev is None and cur == "NORMAL"):
            return
        label = CLASS_LABELS.get(rec["top_class"], rec["top_class"])
        p = f"{rec['top_p'] * 100:.0f}%"
        if cur == "CONFIRMED":
            self._log(rec["t"], n, "critical", "Alert confirmed",
                      f"{label}, {p} confidence, {rec['streak']} samples in a row")
        elif prev == "CONFIRMED":
            self._log(rec["t"], n, "ok", "Alert cleared", f"{self.cfg.clear_n} samples in a row without a risk vote")
        elif cur == "POSSIBLE":
            why = "confidence below threshold" if rec["streak"] == 0 else f"{rec['streak']} of {rec['need']} in a row"
            self._log(rec["t"], n, "warning", "Possible subsidence", f"{label}, {p} confidence, {why}")
        elif cur == "DECOY":
            self._log(rec["t"], n, "warning", "Vibration only",
                      f"{label}, {p} confidence. Tilt and displacement are normal, so no alert")
        else:
            self._log(rec["t"], n, "ok", "Back to normal", f"{p} confidence")

    def _log(self, t, node, level, title, detail):
        self._event_id += 1
        ev = {"id": self._event_id, "t": round(t, 1), "node": node, "level": level, "title": title, "detail": detail}
        self.events.appendleft(ev)
        self.pending_events.append(ev)

    # ---------------- views for the UI ----------------
    def info(self) -> dict:
        c = self.cfg
        return {
            "model": Path(MODEL_PATH).name, "classes": self.predictor.classes, "class_labels": CLASS_LABELS,
            "sample_period_s": c.sample_period_s, "persist_n": c.persist_n,
            "confirm_confidence": c.confirm_confidence, "limits": LIMITS, "speeds": SPEEDS,
            "ambient_vibration": AMBIENT_VIB, "raw_columns": list(c.columns),
        }

    def _health(self, n: int) -> dict:
        s = self.latest.get(n)
        ns = self.pipe.nodes.get(f"NODE_{n:02d}")
        if ns is not None and ns.faulted:
            return {"state": "fault", "label": "Sensor fault", "online": False}
        if s is None:
            return {"state": "starting", "label": "Starting", "online": True}
        if self.t_live - s["t"] > 4 * self.cfg.sample_period_s:
            return {"state": "offline", "label": "No data", "online": False}
        state = "critical" if self.alert_active[n] else {"POSSIBLE": "warning", "DECOY": "warning"}.get(s["status"], "normal")
        return {"state": state, "label": {"critical": "Critical", "warning": "Warning", "normal": "Normal"}[state],
                "online": True}

    def snapshot(self) -> dict:
        r3 = lambda d: {k: round(v, 3) for k, v in d.items()}
        return {
            "t": round(self.t_live, 2), "speed": self.speed,
            "script": None if self.script is None else {
                "name": self.script.name, "label": self.script.label(), "done": self.script.done,
                "progress": round(min(1.0, self.script.tau / self.script.duration), 3)},
            "nodes": [{"id": n, "target": r3(self.targets[n]), "actual": r3(self.actual[n]),
                       "sample": self.latest.get(n), "health": self._health(n), "raw": self.raw_last.get(n),
                       "alert_active": self.alert_active[n]}
                      for n in NODES],
        }

    def history_snapshot(self, last_s: float = 130.0) -> dict:
        lo = self.t_live - last_s
        return {n: [r for r in self.history[n] if r["t"] >= lo] for n in NODES}

    def drain(self) -> tuple[list, list]:
        s, e = self.pending_samples, self.pending_events
        self.pending_samples, self.pending_events = [], []
        return s, e
