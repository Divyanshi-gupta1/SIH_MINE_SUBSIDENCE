"""
Unit + end-to-end checks for the hardware bridge (stdlib unittest, no extra deps):

    python -m unittest test_pipeline_units -v          (from hardware_integration/)

  1. Feature parity   streaming features == the training CSV's derived columns (103,680 rows)
  2. Parser           formats accepted / rejected
  3. Sanity gate      impossible values are DROPPED and never reach the model
  4. Guardrails       persistence + confidence logic
  5. Harness logic    evaluate_static / evaluate_vibration can really PASS, FAIL and INVALID
  6. End-to-end       simulator through the real RF: static, vibration-only, precursor ramp
The simulator is my own model of the sensors -- tests 3 and 6 verify logic, not real hardware.
"""
from __future__ import annotations

import math
import unittest
import warnings
from collections import Counter

import numpy as np
import pandas as pd

from config import FEATURES, TRAIN, TRAIN_CSV, PipelineConfig
from feature_engine import NodeFeatureEngine, vib_threshold
from guardrails import AlertGuard
from inference_pipeline import MineGuardPipeline, RFPredictor, SampleOutput
from sensor_conversion import (LineParser, WindowStats, convert, make_sample, normalize_node, Scales)
from sim_source import SimSensors
from test_static_no_movement import evaluate_static
from test_vibration_only import evaluate_vibration

warnings.filterwarnings("ignore")
_PRED = None


def predictor():
    global _PRED
    if _PRED is None:
        _PRED = RFPredictor()
    return _PRED


class StubPredictor:
    """Records every feature row the pipeline hands to the model."""

    def __init__(self, probs=None):
        self.calls = []
        self.probs = probs or {"decoy_seismic": 0.0, "normal": 1.0, "subsidence_precursor": 0.0}

    def predict(self, features):
        self.calls.append(dict(features))
        return dict(self.probs)


def run_sim(sim: SimSensors, pipe: MineGuardPipeline, duration_s: float):
    outs = []
    for t, line in sim.lines(duration_s):
        outs += pipe.feed_line(t, line)
    return outs + pipe.flush(duration_s)


# ------------------------------------------------------------------------------------
class TestFeatureParity(unittest.TestCase):
    def test_streaming_features_match_training_csv(self):
        df = pd.read_csv(TRAIN_CSV, parse_dates=["timestamp"], low_memory=False)
        df = df[df.node_id.str.match(r"NODE_\d\d$")]          # our 10 nodes (all 103,680 rows)
        cols = ["vibration_duration", "tilt_vibration_correlation", "displacement_persistence",
                "tilt_deviation_from_node_baseline"]
        n_rows = n_off = 0
        for node, g in df.groupby("node_id"):
            g = g.sort_values("timestamp")
            eng = NodeFeatureEngine(vib_threshold(g.vibration_rms.to_numpy()))
            out = pd.DataFrame([eng.update(t, v, d) for t, v, d in
                                zip(g.tilt_deg, g.vibration_rms, g.displacement_mm)], index=g.index)
            for c in cols:
                n_off += int(((out[c] - g[c]).abs() > 2e-3).sum())
            n_rows += len(g)
        self.assertEqual(n_rows, 103680)
        self.assertEqual(n_off, 0, "streaming feature engine diverges from the training pipeline")

    def test_vibration_duration_starts_at_two(self):
        """Training quirk: a run that follows a below-threshold sample counts 2,3,4..."""
        eng = NodeFeatureEngine(1.0)
        seq = [eng.update(0.1, v, 0.0)["vibration_duration"] for v in (0.5, 0.5, 2, 2, 2, 0.5, 2)]
        self.assertEqual(seq, [0, 0, 2, 3, 4, 0, 2])


class TestParser(unittest.TestCase):
    def setUp(self):
        self.p = LineParser(PipelineConfig())

    def test_default_csv(self):
        r = self.p.parse("2,100,-200,16384,5,6,7,101.25", 1.0)
        self.assertEqual((r.node, r.a, r.g, r.dist), ("NODE_02", (100, -200, 16384), (5, 6, 7), 101.25))

    def test_node_formats(self):
        for tok in ("3", "NODE_03", "node3", "N3", "NODE-3"):
            self.assertEqual(normalize_node(tok), "NODE_03")

    def test_header_then_reordered_columns(self):
        self.assertIsNone(self.p.parse("node,az,ay,ax,dist,gx,gy,gz", 0))
        r = self.p.parse("1,16384,2,3,55.5,0,0,0", 0)
        self.assertEqual((r.a, r.dist), ((3, 2, 16384), 55.5))

    def test_key_value(self):
        r = self.p.parse("N=2 ax=1 ay=2 az=16000 gx=0 gy=0 gz=0 dist=80.5", 0)
        self.assertEqual((r.node, r.a, r.dist), ("NODE_02", (1, 2, 16000), 80.5))

    def test_current_lora_serial_monitor_format_is_parsed_without_inventing_distance(self):
        r = self.p.parse("-> [From NODE 1] Data: NODE_1|P:-75.39|R:-6.25|V:0.07 | RSSI: -33 dBm", 1)
        self.assertEqual(r.node, "NODE_01")
        self.assertAlmostEqual(float(np.linalg.norm(r.a)), 1.0)
        self.assertEqual(r.vib, 0.07)
        self.assertTrue(math.isnan(r.dist), "the photographed packet has no HC-SR04 reading")

    def test_extended_lora_packet_uses_echo_and_temperature(self):
        r = self.p.parse("-> [From NODE 2] Data: NODE_2|P:-1.2|R:0.4|V:0.012|E:5800|T:25.0|GX:0.1|GY:0.2|GZ:0.3 | RSSI: -32 dBm", 1)
        self.assertEqual((r.node, r.dist, r.temp_c, r.g), ("NODE_02", 5800.0, 25.0, (0.1, 0.2, 0.3)))
        cfg = PipelineConfig(dist_unit="us", accel_units="g", gyro_units="dps")
        c = convert(r, Scales(1.0, 1.0, 1 / 58.0), cfg)
        self.assertAlmostEqual(c.dist_cm, 5800 * (331.3 + .606 * 25.0) / 20000.0)

    def test_lora_node_spoof_is_rejected(self):
        self.assertIsNone(self.p.parse("-> [From NODE 1] Data: NODE_2|P:0|R:0|V:0.01", 1))

    def test_rejects_garbage_never_guesses(self):
        for bad in ("", "# comment", "1,2,3", "1,a,b,c,d,e,f,g", "1,1,2,3,4,5,6,7,8", "\x00\xff garbage"):
            self.assertIsNone(self.p.parse(bad, 0), bad)
        self.assertGreaterEqual(sum(self.p.stats.values()), 3)

    def test_nan_accel_rejected(self):
        self.assertIsNone(self.p.parse("1,nan,0,16384,0,0,0,50", 0))


# ------------------------------------------------------------------------------------
def calibrated_pipeline(stub=None, seed=0, cfg=None):
    cfg = cfg or PipelineConfig()
    pipe = MineGuardPipeline(cfg, predictor=stub or predictor())
    sim = SimSensors(nodes=(1,), seed=seed)
    span = cfg.calib_windows * cfg.sample_period_s
    for t, line in sim.lines(span + 1):
        pipe.feed_line(t, line)
    assert pipe.is_calibrated("NODE_01"), pipe.events
    return pipe, sim, span


def good_stats(cal, **kw) -> WindowStats:
    base = dict(idx=100, t=1000.0, n_accel=10, n_dist=10, mean_a_g=np.array(cal.a_ref_g), gravity_g=cal.g_mag,
                vib_g=cal.vib_median_g, gyro_motion_dps=0.2, dist_cm=cal.dist_ref_cm, tilt_deg=0.02,
                tilt_sigma_deg=0.02, dist_se_mm=0.1)
    base.update(kw)
    return WindowStats(**base)


class TestSanityGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = PipelineConfig()
        pipe, _, _ = calibrated_pipeline(StubPredictor())
        cls.cal = pipe.nodes["NODE_01"].cal

    def check(self, reason, **kw):
        smp, why = make_sample(good_stats(self.cal, **kw), self.cal, self.cfg, last_disp_mm=0.0)
        self.assertIsNone(smp, f"{reason}: should be dropped")
        self.assertEqual(why, reason)

    def test_valid_window_passes_and_noise_is_floored(self):
        smp, why = make_sample(good_stats(self.cal), self.cal, self.cfg, 0.0)
        self.assertIsNone(why)
        self.assertAlmostEqual(smp["tilt"], self.cfg.tilt_rest_offset_deg)     # 0.02 deg << deadband
        self.assertEqual(smp["disp"], 0.0)

    def test_tilt_over_90_dropped(self):
        self.check("tilt_out_of_range", tilt_deg=91.0)
        self.check("tilt_out_of_range", tilt_deg=175.0)          # node flipped over

    def test_negative_displacement_dropped(self):
        d = self.cal.dist_ref_cm - 5.0                            # 50 mm closer = displacement -50 mm
        self.check("negative_displacement", dist_cm=d)

    def test_small_negative_within_noise_is_not_dropped(self):
        d = self.cal.dist_ref_cm - 0.05                           # -0.5 mm, inside tolerance
        smp, why = make_sample(good_stats(self.cal, dist_cm=d), self.cal, self.cfg, 0.0)
        self.assertIsNone(why)
        self.assertEqual(smp["disp"], 0.0)

    def test_other_impossible_windows(self):
        self.check("gravity_magnitude_bad", gravity_g=1.6)
        self.check("node_moving", gyro_motion_dps=90.0)
        self.check("no_valid_distance", n_dist=1)
        self.check("no_valid_distance", dist_cm=float("nan"))
        self.check("too_few_readings", n_accel=1)
        self.check("vibration_invalid", vib_g=float("nan"))
        self.check("displacement_out_of_range", dist_cm=self.cal.dist_ref_cm + 60.0)

    def test_displacement_jump_dropped(self):
        smp, why = make_sample(good_stats(self.cal, dist_cm=self.cal.dist_ref_cm + 8.0), self.cal, self.cfg,
                               last_disp_mm=0.0)                 # +80 mm in one sample
        self.assertEqual(why, "displacement_jump")

    def test_reading_level_drops(self):
        cfg, cnt = self.cfg, Counter()
        sc = Scales(16384.0, 131.0, 1.0, accel_is_counts=True)
        from sensor_conversion import RawReading
        ok = RawReading(0, "NODE_01", (0, 0, 16384), (0, 0, 0), 100.0)
        self.assertIsNotNone(convert(ok, sc, cfg, None, cnt))
        for dist in (0.0, -1.0, 999.0, 1.0, 450.0):               # no echo / sentinel / out of range
            c = convert(RawReading(0, "NODE_01", (0, 0, 16384), (0, 0, 0), dist), sc, cfg, None, cnt)
            self.assertTrue(math.isnan(c.dist_cm), dist)
        self.assertIsNone(convert(RawReading(0, "NODE_01", (0, 0, 32767), (0, 0, 0), 100.0), sc, cfg, None, cnt))
        self.assertEqual(cnt["reading_dist_out_of_range"], 5)
        self.assertEqual(cnt["reading_accel_saturated"], 1)

    def test_impossible_values_never_reach_model_end_to_end(self):
        stub = StubPredictor()
        pipe, sim, span = calibrated_pipeline(stub)
        stub.calls.clear()
        cfg = pipe.cfg
        t1, t2, t3 = span + 20, span + 40, span + 60
        n_before = None

        def fault(node, t, f):
            if t1 <= t < t2:                                      # node flipped upside down
                f[3] = str(-int(f[3]))
            elif t2 <= t < t3:                                    # target 50 mm closer -> negative displacement
                f[7] = f"{float(f[7]) - 5.0:.2f}"
            return f

        sim.fault = fault
        outs = []
        for t, line in sim.lines(span + 80, t0=span + 1):
            outs += pipe.feed_line(t, line)
        outs += pipe.flush(span + 80)
        drops = pipe.nodes["NODE_01"].drops
        self.assertGreater(drops["tilt_out_of_range"] + drops["gravity_magnitude_bad"], 5)
        self.assertGreater(drops["negative_displacement"], 5)
        # nothing in the faulted intervals produced a model call
        bad_t = [o for o in outs if t1 <= o.t < t3]
        self.assertEqual(bad_t, [], "windows inside the faulted intervals must not produce predictions")
        for row in stub.calls:                                    # and no impossible feature ever reached the model
            self.assertLessEqual(row["tilt_deg"], 90.0)
            self.assertGreaterEqual(row["displacement_mm"], 0.0)
        self.assertTrue(any(e[2] == "SENSOR_FAULT" for e in pipe.events))


# ------------------------------------------------------------------------------------
def P(risk=0.0, decoy=0.0):
    return {"decoy_seismic": decoy, "normal": 1.0 - risk - decoy, "subsidence_precursor": risk}


class TestGuardrails(unittest.TestCase):
    def setUp(self):
        self.cfg = PipelineConfig()                # N = 4, thr 0.70, clear_n 3
        self.g = AlertGuard(self.cfg)

    def feed(self, seq, start=0):
        return [self.g.update(start + i, p) for i, p in enumerate(seq)]

    def test_single_high_confidence_reading_never_alerts(self):
        v = self.feed([P(0.99)])[0]
        self.assertEqual((v.status, v.alert_fired), ("POSSIBLE", False))

    def test_n_consecutive_confident_fires_once(self):
        vs = self.feed([P(0.9)] * 8)
        self.assertEqual([v.status for v in vs], ["POSSIBLE"] * 3 + ["CONFIRMED"] * 5)
        self.assertEqual([v.alert_fired for v in vs], [False] * 3 + [True] + [False] * 4)

    def test_low_confidence_is_possible_never_confirmed_and_resets_streak(self):
        vs = self.feed([P(0.9), P(0.9), P(0.9), P(0.65), P(0.9), P(0.9), P(0.9)])
        self.assertEqual(vs[3].status, "POSSIBLE")
        self.assertIn("low confidence", vs[3].note)
        self.assertNotIn("CONFIRMED", [v.status for v in vs])       # streak was broken at index 3
        self.assertFalse(any(v.alert_fired for v in vs))
        vs = AlertGuard(self.cfg)
        self.assertEqual([vs.update(i, P(0.69)).status for i in range(20)], ["POSSIBLE"] * 20)

    def test_exactly_threshold_counts(self):
        vs = self.feed([P(0.70)] * 4)
        self.assertEqual(vs[-1].status, "CONFIRMED")

    def test_normal_in_the_middle_resets(self):
        vs = self.feed([P(0.9)] * 3 + [P(0.0)] + [P(0.9)] * 3)
        self.assertNotIn("CONFIRMED", [v.status for v in vs])

    def test_decoy_never_alerts(self):
        vs = self.feed([P(0.0, 0.95)] * 10)
        self.assertEqual({v.status for v in vs}, {"DECOY"})
        self.assertFalse(any(v.alert_fired for v in vs))

    def test_missing_windows_reset_streak_but_one_loss_is_tolerated(self):
        g = AlertGuard(self.cfg)
        for i in (0, 1, 2):
            g.update(i, P(0.9))
        self.assertEqual(g.update(4, P(0.9)).status, "CONFIRMED")   # one lost window (3) tolerated
        g = AlertGuard(self.cfg)
        for i in (0, 1, 2):
            g.update(i, P(0.9))
        v = g.update(6, P(0.9))                                     # 3 lost windows
        self.assertEqual((v.status, v.streak), ("POSSIBLE", 1))

    def test_latch_no_refire_until_cleared(self):
        vs = self.feed([P(0.9)] * 4 + [P(0.0)] * 2 + [P(0.9)] * 4)   # only 2 clear samples < clear_n
        self.assertEqual(sum(v.alert_fired for v in vs), 1)
        vs2 = self.feed([P(0.0)] * 3 + [P(0.9)] * 4, start=100)      # now cleared -> can fire again
        self.assertEqual(sum(v.alert_fired for v in vs2), 1)

    def test_extra_risk_classes_are_picked_up(self):
        """If the model is retrained with the 7-class scheme, every non-normal/non-decoy class is risk."""
        g = AlertGuard(self.cfg)
        probs = {"normal": 0.05, "decoy_seismic": 0.0, "high_risk": 0.95, "progressive": 0.0}
        vs = [g.update(i, probs) for i in range(4)]
        self.assertEqual((vs[-1].status, vs[-1].risk_class, vs[-1].alert_fired), ("CONFIRMED", "high_risk", True))

    def test_class_change_resets_streak(self):
        g = AlertGuard(self.cfg)
        a = {"normal": 0.05, "decoy_seismic": 0.0, "persistent": 0.95}
        b = {"normal": 0.05, "decoy_seismic": 0.0, "progressive": 0.95}
        for i in range(3):
            g.update(i, a)
        v = g.update(3, b)
        self.assertEqual((v.status, v.streak), ("POSSIBLE", 1))


# ------------------------------------------------------------------------------------
def out(node="NODE_01", t=0.0, cls="normal", p=0.99, status=None, vib_x=1.0, tilt=0.0, disp=0.0, vdur=0,
        fired=False, cfg=None):
    cfg = cfg or PipelineConfig()
    feats = {"tilt_deg": cfg.tilt_rest_offset_deg + tilt, "vibration_rms": vib_x * TRAIN.VIB_BASELINE_MEDIAN,
             "displacement_mm": disp, "crack_signal": 0, "vibration_duration": vdur,
             "tilt_vibration_correlation": 0.0, "displacement_persistence": 0,
             "tilt_deviation_from_node_baseline": 0.0}
    status = status or ("NORMAL" if cls == "normal" else "DECOY" if cls == "decoy_seismic" else "POSSIBLE")
    return SampleOutput(node, t, int(t), feats, {"tilt_raw_deg": tilt, "disp_raw_mm": disp},
                        {cls: p}, cls, p, status, None, 0, 4, fired, "")


class TestHarnessEvaluators(unittest.TestCase):
    cfg = PipelineConfig()

    def test_static_pass(self):
        recs = {"NODE_01": [out(t=2 * i) for i in range(150)]}
        r = evaluate_static(recs, {"NODE_01"}, 300, self.cfg)
        self.assertEqual(r["overall"], "PASS")

    def test_static_fails_on_single_risk_vote(self):
        recs = {"NODE_01": [out(t=2 * i) for i in range(150)]}
        recs["NODE_01"][70] = out(t=140, cls="subsidence_precursor", p=0.55)
        r = evaluate_static(recs, {"NODE_01"}, 300, self.cfg)
        self.assertEqual(r["overall"], "FAIL")
        self.assertEqual(r["nodes"]["NODE_01"]["violations"][0]["class"], "subsidence_precursor")
        self.assertEqual(evaluate_static(recs, {"NODE_01"}, 300, self.cfg, max_risk_votes=1)["overall"], "PASS")

    def test_static_decoy_blip_strict_by_default_with_knob(self):
        recs = {"NODE_01": [out(t=2 * i) for i in range(150)]}
        recs["NODE_01"][10] = out(t=20, cls="decoy_seismic", p=0.6)
        self.assertEqual(evaluate_static(recs, {"NODE_01"}, 300, self.cfg)["overall"], "FAIL")
        self.assertEqual(evaluate_static(recs, {"NODE_01"}, 300, self.cfg, allow_decoy_blips=1)["overall"], "PASS")

    def test_static_invalid_when_data_missing(self):
        recs = {"NODE_01": [out(t=2 * i) for i in range(20)]}                # 13% coverage
        self.assertEqual(evaluate_static(recs, {"NODE_01"}, 300, self.cfg)["overall"], "INVALID")
        self.assertEqual(evaluate_static({}, {"NODE_02"}, 300, self.cfg)["overall"], "INVALID")

    def _vib_run(self, burst_cls="decoy_seismic", n_burst=3, tilt_quiet=0.0, burst_status=None):
        recs = [out(t=2 * i) for i in range(60)]
        for k in range(n_burst):
            recs[30 + k] = out(t=2 * (30 + k), cls=burst_cls, p=0.9, vib_x=8, vdur=2 + k, status=burst_status)
        if tilt_quiet:
            recs[5] = out(t=10, tilt=tilt_quiet)
        return {"NODE_01": recs}

    def test_vibration_pass(self):
        r = evaluate_vibration(self._vib_run(), {"NODE_01"}, self.cfg, 120)
        self.assertEqual((r["overall"], r["nodes"]["NODE_01"]["status"]), ("PASS", "PASS"))

    def test_vibration_fails_when_read_as_subsidence(self):
        r = evaluate_vibration(self._vib_run("subsidence_precursor"), {"NODE_01"}, self.cfg, 120)
        self.assertEqual(r["overall"], "FAIL")

    def test_vibration_fails_when_read_as_normal(self):
        r = evaluate_vibration(self._vib_run("normal"), {"NODE_01"}, self.cfg, 120)
        self.assertEqual(r["overall"], "FAIL")
        self.assertIn("not recognised", r["nodes"]["NODE_01"]["why"])

    def test_vibration_invalid_when_node_was_tilted(self):
        r = evaluate_vibration(self._vib_run(tilt_quiet=2.0), {"NODE_01"}, self.cfg, 120)
        self.assertEqual(r["overall"], "INVALID")

    def test_vibration_no_burst_is_not_a_pass(self):
        recs = {"NODE_01": [out(t=2 * i) for i in range(60)]}
        r = evaluate_vibration(recs, {"NODE_01"}, self.cfg, 120)
        self.assertEqual((r["overall"], r["nodes"]["NODE_01"]["status"]), ("INVALID", "NO_BURST"))


# ------------------------------------------------------------------------------------
class TestEndToEndSimulated(unittest.TestCase):
    def test_extended_lora_envelope_reaches_pipeline_with_measured_echo_only(self):
        """The photo's receiver wrapper plus P/R/V/E/T/G payload must work end-to-end.

        This uses a stub predictor so it proves the hardware adapter and guards, not a
        synthetic RF outcome. The echo is supplied in every packet; omitting it is covered
        by the parser test above and must never be silently replaced.
        """
        cfg = PipelineConfig(dist_unit="us", accel_units="g", gyro_units="dps")
        stub = StubPredictor()
        pipe = MineGuardPipeline(cfg, predictor=stub)
        for k in range(100):
            t = k * 0.5
            line = ("-> [From NODE 1] Data: NODE_1|P:0.00|R:0.00|V:0.01000|"
                    "E:5800|T:25.00|GX:0.00|GY:0.00|GZ:0.00 | RSSI: -33 dBm")
            pipe.feed_line(t, line)
        pipe.flush(50.0)
        self.assertTrue(pipe.is_calibrated("NODE_01"), pipe.events)
        self.assertGreater(len(stub.calls), 0)
        self.assertTrue(all(row["displacement_mm"] == 0.0 for row in stub.calls))

    def test_static_all_normal(self):
        pipe = MineGuardPipeline(PipelineConfig(), predictor=predictor())
        outs = run_sim(SimSensors(seed=0), pipe, 240)
        self.assertGreaterEqual(len(outs), 290)
        self.assertEqual(Counter(o.top_class for o in outs), Counter(normal=len(outs)))
        self.assertFalse(any(o.alert_fired for o in outs))

    def test_vibration_only_reads_as_decoy_never_subsidence(self):
        cfg = PipelineConfig()
        pipe = MineGuardPipeline(cfg, predictor=predictor())
        sim = SimSensors(seed=3)
        span = cfg.calib_windows * cfg.sample_period_s
        for n in (1, 2, 3):
            sim.vib_factor[n] = lambda t: 8.0 if span + 40 <= t < span + 46 else 1.0
        outs = run_sim(sim, pipe, span + 120)
        self.assertFalse([o for o in outs if o.top_class == "subsidence_precursor"])
        self.assertFalse([o for o in outs if o.status in ("POSSIBLE", "CONFIRMED")])
        burst = [o for o in outs if o.features["vibration_rms"] > 3 * TRAIN.VIB_BASELINE_MEDIAN]
        self.assertGreaterEqual(len(burst), 6)
        self.assertGreaterEqual(sum(o.top_class == "decoy_seismic" for o in burst) / len(burst), 0.8)
        # tilt / displacement stayed at their noise floor while vibration spiked
        self.assertLess(max(o.features["displacement_mm"] for o in outs), 1.0)
        self.assertLess(max(o.features["tilt_deg"] - cfg.tilt_rest_offset_deg for o in outs), 0.3)

    def test_strong_precursor_ramp_is_still_confirmed(self):
        """Guardrails must not blind the pipeline: a training-sized buildup ends in exactly one alert."""
        cfg = PipelineConfig()
        pipe = MineGuardPipeline(cfg, predictor=predictor())
        sim = SimSensors(nodes=(1,), seed=0)
        span = cfg.calib_windows * cfg.sample_period_s
        t0, R = span + 30, 34 * cfg.sample_period_s
        f = lambda t: min(1.0, max(0.0, (t - t0) / R)) ** 2
        sim.tilt_extra_deg[1] = lambda t: 3.8 * f(t)
        sim.disp_extra_mm[1] = lambda t: 33.0 * f(t)
        sim.vib_factor[1] = lambda t: 1 + 6.8 * f(t)
        outs = run_sim(sim, pipe, t0 + R + 20)
        alerts = [o for o in outs if o.alert_fired]
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].risk_class, "subsidence_precursor")
        self.assertFalse([o for o in outs if o.t < t0 and o.top_class != "normal"], "no false vote before the ramp")


if __name__ == "__main__":
    unittest.main(verbosity=2)
