"""
Serial line -> convert -> sanity gate -> streaming features -> RF v6 -> guardrails.

    pipe = MineGuardPipeline(cfg)
    for t, line in source:
        for out in pipe.feed_line(t, line):      # one SampleOutput per closed window
            ...

Per node: CALIBRATING (still node, no predictions) -> RUNNING. Calibration is what zeroes
tilt/displacement and fixes unit scales; persist it (save_calibrations) or every restart
would reset "displacement since install" to zero.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import joblib
import numpy as np
import pandas as pd

from config import FEATURES, MODEL_PATH, TRAIN_CSV, PipelineConfig
from feature_engine import NodeFeatureEngine
from guardrails import AlertGuard
from sensor_conversion import (CalibrationError, ConvReading, LineParser, NodeCalibration, RawReading,
                               WindowAggregator, calibrate, convert, make_sample, summarize)


class RFPredictor:
    """RF v6 wrapper. sklearn's predict_proba costs ~130 ms per single-row call (200 trees of
    per-call overhead), so probabilities are computed by walking the fitted trees directly;
    at load the walk is checked against sklearn on real training rows and, if it disagrees
    by more than 1e-9, sklearn is used instead."""

    def __init__(self, path: Path = MODEL_PATH, fast: bool = True):
        self.model = joblib.load(path)
        names = tuple(getattr(self.model, "feature_names_in_", ()))
        if names != FEATURES:
            raise ValueError(f"model expects {names}, pipeline builds {FEATURES}")
        self.classes = [str(c) for c in self.model.classes_]
        self._trees = None
        if fast:
            self._trees = self._extract_trees()
            if not self._self_check():
                self._trees = None

    def _extract_trees(self):
        out = []
        for est in self.model.estimators_:
            t = est.tree_
            v = t.value[:, 0, :]
            v = v / v.sum(axis=1, keepdims=True)
            out.append((t.children_left.tolist(), t.children_right.tolist(), t.feature.tolist(),
                        t.threshold.tolist(), v))
        return out

    def _walk(self, x) -> np.ndarray:
        x32 = [float(np.float32(u)) for u in x]          # sklearn compares float32 X to float64 thresholds
        acc = np.zeros(len(self.classes))
        for left, right, feat, thr, val in self._trees:
            n = 0
            while left[n] != -1:
                n = left[n] if x32[feat[n]] <= thr[n] else right[n]
            acc += val[n]
        return acc / len(self._trees)

    def _self_check(self, n: int = 200) -> bool:
        try:
            df = pd.read_csv(TRAIN_CSV, usecols=list(FEATURES), nrows=20000).sample(n, random_state=0)
            ref = self.model.predict_proba(df[list(FEATURES)])
            got = np.stack([self._walk(r) for r in df[list(FEATURES)].to_numpy()])
            return bool(np.abs(ref - got).max() < 1e-9)
        except Exception:
            return False

    def predict(self, features: dict) -> dict:
        row = [features[k] for k in FEATURES]
        if self._trees is not None:
            p = self._walk(row)
        else:
            p = self.model.predict_proba(pd.DataFrame([row], columns=list(FEATURES)))[0]
        return dict(zip(self.classes, (float(u) for u in p)))


@dataclass
class SampleOutput:
    node: str
    t: float
    window_idx: int
    features: dict
    diag: dict
    probs: dict
    top_class: str
    top_p: float
    status: str
    risk_class: Optional[str]
    streak: int
    need: int
    alert_fired: bool
    note: str

    def to_row(self) -> dict:
        row = {"node": self.node, "t": round(self.t, 3), "window_idx": self.window_idx}
        row.update(self.features)
        row.update({f"diag_{k}": v for k, v in self.diag.items()})
        row.update({f"p_{k}": round(v, 4) for k, v in self.probs.items()})
        row.update(top_class=self.top_class, top_p=round(self.top_p, 4), status=self.status,
                   streak=self.streak, alert_fired=int(self.alert_fired), note=self.note)
        return row


@dataclass
class NodeState:
    node: str
    calib_buf: list = field(default_factory=list)
    cal: Optional[NodeCalibration] = None
    agg: Optional[WindowAggregator] = None
    engine: Optional[NodeFeatureEngine] = None
    guard: Optional[AlertGuard] = None
    last_disp_raw: Optional[float] = None
    consec_drops: int = 0
    faulted: bool = False
    last_t: float = 0.0
    drops: Counter = field(default_factory=Counter)
    n_samples: int = 0


class MineGuardPipeline:
    def __init__(self, cfg: PipelineConfig | None = None, predictor=None,
                 calibrations: dict | None = None, on_event: Callable | None = None):
        self.cfg = cfg or PipelineConfig()
        self.predictor = predictor if predictor is not None else RFPredictor()
        self.parser = LineParser(self.cfg)
        self.on_event = on_event
        self.events: list[tuple] = []
        self.nodes: dict[str, NodeState] = {}
        self.reading_counters: Counter = Counter()
        for node, cal in (calibrations or {}).items():
            self._activate(self._state(node), cal, seed=[])

    # ---------------- public API ----------------
    def feed_line(self, t: float, line: str) -> list[SampleOutput]:
        r = self.parser.parse(line, t)
        return self.feed_reading(r) if r is not None else []

    def feed_reading(self, r: RawReading) -> list[SampleOutput]:
        st = self._state(r.node)
        st.last_t = r.t
        if st.cal is None:
            self._calibrating(st, r)
            return []
        c = convert(r, st.cal.scales, self.cfg, st.cal.gyro_bias, self.reading_counters)
        if c is None:
            return []
        return self._emit(st, st.agg.add(c))

    def flush(self, now: float) -> list[SampleOutput]:
        out = []
        for st in self.nodes.values():
            if st.agg is not None:
                out += self._emit(st, st.agg.flush(now))
        return out

    def is_calibrated(self, node: str) -> bool:
        return node in self.nodes and self.nodes[node].cal is not None

    def stale_nodes(self, now: float, after_s: float) -> list[str]:
        return [n for n, s in self.nodes.items() if now - s.last_t > after_s]

    def summary(self) -> dict:
        return {
            "parser": dict(self.parser.stats),
            "reading_drops": dict(self.reading_counters),
            "nodes": {n: {"samples": s.n_samples, "window_drops": dict(s.drops),
                          "calibrated": s.cal is not None, "faulted": s.faulted}
                      for n, s in self.nodes.items()},
        }

    def save_calibrations(self, path: str | Path):
        Path(path).write_text(json.dumps(
            {n: s.cal.to_dict() for n, s in self.nodes.items() if s.cal}, indent=2))

    @staticmethod
    def load_calibrations(path: str | Path) -> dict:
        return {n: NodeCalibration.from_dict(d) for n, d in json.loads(Path(path).read_text()).items()}

    # ---------------- internals ----------------
    def _event(self, t, node, kind, msg):
        self.events.append((t, node, kind, msg))
        if self.on_event:
            self.on_event(t, node, kind, msg)

    def _state(self, node: str) -> NodeState:
        if node not in self.nodes:
            self.nodes[node] = NodeState(node)
        return self.nodes[node]

    def _calibrating(self, st: NodeState, r: RawReading):
        st.calib_buf.append(r)
        span = r.t - st.calib_buf[0].t
        if span < self.cfg.calib_windows * self.cfg.sample_period_s:
            return
        try:
            cal, seed = calibrate(st.node, st.calib_buf, self.cfg, self.reading_counters)
        except CalibrationError as e:
            self._event(r.t, st.node, "calibration_rejected", f"{e} -- restarting calibration")
            st.calib_buf = []
            return
        self._activate(st, cal, seed)
        self._event(r.t, st.node, "calibrated",
                    f"accel {'counts' if cal.accel_is_counts else 'g/m/s2'} (1 g = {cal.accel_per_g:g}), "
                    f"|g|={cal.g_mag:.3f}, dist zero={cal.dist_ref_cm:.2f} cm, "
                    f"tilt noise floor={cal.tilt_deadband_deg:.2f} deg, "
                    f"disp noise sigma={cal.disp_sigma_mm:.2f} mm, deadband={cal.deadband_mm:.2f} mm, "
                    f"ultrasonic step={cal.quant_mm:.2f} mm, vib baseline={cal.vib_median_g * 1000:.2f} mg "
                    f"(x{cal.vib_scale:.1f} to model units), {cal.n_windows} windows")
        if cal.tilt_deadband_deg > 1.0 or cal.deadband_mm > 10.0:
            self._event(r.t, st.node, "WARNING",
                        f"high noise floor (tilt {cal.tilt_deadband_deg:.2f} deg, displacement "
                        f"{cal.deadband_mm:.1f} mm): movement below these is invisible to the model -- "
                        f"check mounting, raise readings per window, or use a longer sample_period_s")

    def _activate(self, st: NodeState, cal: NodeCalibration, seed: list):
        st.cal = cal
        st.calib_buf = []
        st.agg = WindowAggregator(self.cfg.sample_period_s)
        st.engine = NodeFeatureEngine(cal.vib_threshold_model)
        st.guard = AlertGuard(self.cfg)
        for s in seed:                          # warm the causal state; no predictions
            st.engine.update(round(s["tilt"], 4), round(s["vib"], 4), round(s["disp"], 3))
            st.last_disp_raw = s["disp_raw_mm"]

    def _emit(self, st: NodeState, groups) -> list[SampleOutput]:
        outs = []
        for idx, conv in groups:
            if idx < 0:
                st.drops["late_reading"] += 1
                continue
            o = self._process_window(st, idx, conv)
            if o is not None:
                outs.append(o)
        return outs

    def _process_window(self, st: NodeState, idx: int, conv: list[ConvReading]) -> Optional[SampleOutput]:
        stats = summarize(idx, conv, st.cal.g_mag, np.asarray(st.cal.a_ref_g))
        smp, reason = make_sample(stats, st.cal, self.cfg, st.last_disp_raw)
        if smp is None:
            st.drops[reason] += 1
            st.consec_drops += 1
            if st.consec_drops == self.cfg.fault_after_dropped_windows:
                st.faulted = True
                self._event(stats.t, st.node, "SENSOR_FAULT",
                            f"{st.consec_drops} consecutive windows dropped (last reason: {reason}); "
                            f"no predictions until readings are valid again -- recalibrate if the node was moved")
            return None
        if st.faulted:
            st.faulted = False
            self._event(stats.t, st.node, "sensor_recovered", "valid readings again")
        st.consec_drops = 0
        st.last_disp_raw = smp["disp_raw_mm"]

        feats = st.engine.update(smp["tilt"], smp["vib"], smp["disp"])
        probs = self.predictor.predict(feats)
        v = st.guard.update(idx, probs)
        st.n_samples += 1
        if v.alert_fired:
            self._event(stats.t, st.node, "ALERT", f"{v.risk_class} CONFIRMED: {v.note}")
        return SampleOutput(st.node, stats.t, idx, feats, smp["diag"], probs, v.top_class, v.top_p,
                            v.status, v.risk_class, v.streak, v.need, v.alert_fired, v.note)
