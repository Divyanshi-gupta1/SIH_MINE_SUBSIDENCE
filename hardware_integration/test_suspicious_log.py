"""
Checks for suspicious_log.py: only suspicious predictions reach the CSV, normal ones never do.

    python test_suspicious_log.py            (from hardware_integration/; or: python -m unittest test_suspicious_log -v)

All CSV files are written to a temporary folder, never to the project's logs/ folder.

  1. Decision      normal is skipped; decoy, POSSIBLE and CONFIRMED are kept
  2. CSV file      folder + header created, exact columns, appends without overwriting, survives a locked file
  3. Pipeline hook fake normal / fake suspicious model output through MineGuardPipeline: only suspicious rows saved,
                   the raw line belongs to the right node and window, outputs identical with and without the hook
  4. Real RF v6    simulated still nodes + a vibration burst + a precursor ramp: rows only for the non-normal samples
  5. Paths         real hardware -> logs/real/, replay and simulator -> logs/replay/, distinct folders, no default
                   that can reach "real", the old single logs/suspicious_readings.csv is gone
  6. run_live.py   end to end (stub model, faked serial port): a replay file, COM5 and socket:// each write to the
                   right file and to no other; every logged raw line is in the file of the run that fed it
"""
from __future__ import annotations

import contextlib
import csv
import inspect
import io
import shutil
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

import run_live
import suspicious_log
from config import HERE, MODEL_PATH, PipelineConfig
from inference_pipeline import MineGuardPipeline, RFPredictor
from sim_source import SimSensors
from suspicious_log import (COLUMNS, REAL_LOG_PATH, REPLAY_LOG_PATH, SuspiciousLog, attach, is_suspicious,
                            log_if_suspicious, log_path_for)
from test_pipeline_units import StubPredictor, out

warnings.filterwarnings("ignore")

NORMAL = {"decoy_seismic": 0.0, "normal": 1.0, "subsidence_precursor": 0.0}
RISK = {"decoy_seismic": 0.0, "normal": 0.02, "subsidence_precursor": 0.98}
DECOY = {"decoy_seismic": 0.97, "normal": 0.03, "subsidence_precursor": 0.0}


def read_rows(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="suspicious_log_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = self.tmp / "nested" / "logs" / "suspicious_readings.csv"     # folder does not exist yet


# ------------------------------------------------------------------------------------
class TestDecision(unittest.TestCase):
    def test_which_samples_are_suspicious(self):
        self.assertFalse(is_suspicious(out(cls="normal", status="NORMAL")))
        self.assertTrue(is_suspicious(out(cls="decoy_seismic", status="DECOY")))
        self.assertTrue(is_suspicious(out(cls="subsidence_precursor", p=0.55, status="POSSIBLE")))
        self.assertTrue(is_suspicious(out(cls="subsidence_precursor", p=0.95, status="CONFIRMED")))

    def test_guardrail_state_alone_is_enough(self):
        self.assertTrue(is_suspicious(out(cls="normal", status="POSSIBLE")))
        self.assertTrue(is_suspicious(out(cls="normal", status="CONFIRMED")))

    def test_normal_class_name_comes_from_config(self):
        self.assertFalse(is_suspicious(out(cls="ok", status="NORMAL"), normal_class="ok"))
        self.assertTrue(is_suspicious(out(cls="normal", status="NORMAL"), normal_class="ok"))


# ------------------------------------------------------------------------------------
class TestCsvFile(TempDirCase):
    def test_only_suspicious_rows_are_saved(self):
        for i in range(5):
            log_if_suspicious(out(t=i, cls="normal", status="NORMAL"), "1,0,0,16384,0,0,0,100.00", self.path)
        self.assertFalse(self.path.exists(), "normal readings alone must not even create the file")

        log_if_suspicious(out(node="NODE_02", cls="decoy_seismic", p=0.97, status="DECOY", vib_x=8), "2,5,-3,16384,0,0,0,100.10", self.path)
        log_if_suspicious(out(t=9, cls="normal", status="NORMAL"), "1,0,0,16384,0,0,0,100.00", self.path)
        log_if_suspicious(out(node="NODE_03", cls="subsidence_precursor", p=0.55, status="POSSIBLE", tilt=2.0, disp=15), "3,1,2,16384,0,0,0,101.50", self.path)
        log_if_suspicious(out(node="NODE_03", cls="subsidence_precursor", p=0.93, status="CONFIRMED", tilt=3.5, disp=30), "3,2,3,16384,0,0,0,103.00", self.path)

        rows = read_rows(self.path)
        self.assertEqual([r["guardrail_status"] for r in rows], ["DECOY", "POSSIBLE", "CONFIRMED"])
        self.assertNotIn("normal", [r["predicted_class"] for r in rows])
        r = rows[2]
        self.assertEqual((r["node_id"], r["predicted_class"], r["confidence"]), ("NODE_03", "subsidence_precursor", "0.93"))
        self.assertEqual(float(r["displacement"]), 30.0)
        self.assertEqual(r["raw_serial_line"], "3,2,3,16384,0,0,0,103.00")       # commas survive CSV quoting

    def test_folder_and_header_are_created_and_columns_are_exact(self):
        self.assertFalse(self.path.parent.exists())
        log_if_suspicious(out(cls="decoy_seismic", status="DECOY"), "1,1,1,16384,0,0,0,100", self.path)
        with open(self.path, encoding="utf-8") as fh:
            self.assertEqual(fh.readline().strip(),
                             "timestamp,node_id,raw_serial_line,tilt,vibration,displacement,predicted_class,confidence,guardrail_status")
        self.assertEqual(tuple(read_rows(self.path)[0]), COLUMNS)
        self.assertRegex(read_rows(self.path)[0]["timestamp"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}$")

    def test_new_entries_append_and_old_ones_survive(self):
        first = SuspiciousLog(self.path)
        first.log(out(node="NODE_01", cls="decoy_seismic", status="DECOY"), "1,a")
        first.log(out(node="NODE_01", cls="decoy_seismic", status="DECOY"), "1,b")
        second = SuspiciousLog(self.path)                       # a later run of the program
        second.log(out(node="NODE_02", cls="subsidence_precursor", status="POSSIBLE"), "2,c")
        rows = read_rows(self.path)
        self.assertEqual([r["raw_serial_line"] for r in rows], ["1,a", "1,b", "2,c"])
        self.assertEqual(self.path.read_text(encoding="utf-8").count("timestamp,node_id"), 1, "header written once")

    def test_locked_file_never_raises_and_rows_are_kept_and_retried(self):
        self.path.mkdir(parents=True)                           # a directory where the file should be: open() fails
        lg = SuspiciousLog(self.path)
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertTrue(lg.log(out(cls="decoy_seismic", status="DECOY"), "1,first"))     # must not raise
        self.assertIn("cannot write", err.getvalue())            # ...but it does say so, once
        self.path.rmdir()                                       # "Excel closed the file"
        lg.log(out(cls="decoy_seismic", status="DECOY"), "1,second")
        self.assertEqual([r["raw_serial_line"] for r in read_rows(self.path)], ["1,first", "1,second"])


# ------------------------------------------------------------------------------------
class SwitchingStub(StubPredictor):
    """normal for the first `n_normal` predictions, then `later` for the rest."""

    def __init__(self, n_normal, later):
        super().__init__()
        self.n_normal, self.later = n_normal, later

    def predict(self, features):
        self.calls.append(dict(features))
        return dict(NORMAL if len(self.calls) <= self.n_normal else self.later)


def run(pipe, sim, seconds, t0=0.0):
    """Feed simulated lines; returns (all outputs, {node: {window: [lines]}}) so tests can check raw lines."""
    outs, fed = [], {}
    period = pipe.cfg.sample_period_s
    for t, line in sim.lines(seconds, t0):
        node = f"NODE_{int(line.split(',')[0]):02d}"
        fed.setdefault(node, {}).setdefault(int(t // period), []).append(line)
        outs += pipe.feed_line(t, line)
    return outs, fed


class TestPipelineHook(TempDirCase):
    def test_only_suspicious_samples_are_saved_and_raw_line_is_right(self):
        cfg = PipelineConfig()
        stub = SwitchingStub(n_normal=60, later=DECOY)
        pipe = attach(MineGuardPipeline(cfg, predictor=stub), self.path)
        outs, fed = run(pipe, SimSensors(nodes=(1, 2, 3), seed=0), 160)

        normal = [o for o in outs if o.status == "NORMAL"]
        suspicious = [o for o in outs if o.status != "NORMAL"]
        self.assertGreater(len(normal), 10)
        self.assertGreater(len(suspicious), 10)
        rows = read_rows(self.path)
        self.assertEqual(len(rows), len(suspicious), "exactly the suspicious samples, none of the normal ones")
        self.assertEqual({r["guardrail_status"] for r in rows}, {"DECOY"})
        for row, o in zip(rows, suspicious):
            self.assertEqual(row["node_id"], o.node)
            self.assertEqual(float(row["confidence"]), round(o.top_p, 4))
            node_no = int(o.node.split("_")[1])
            self.assertIn(row["raw_serial_line"], fed[o.node][o.window_idx],
                          "logged line must be one this node sent inside the window that made the prediction")
            self.assertTrue(row["raw_serial_line"].startswith(f"{node_no},"))

    def test_all_normal_writes_nothing(self):
        pipe = attach(MineGuardPipeline(PipelineConfig(), predictor=StubPredictor(NORMAL)), self.path)
        outs, _ = run(pipe, SimSensors(nodes=(1, 2), seed=1), 120)
        self.assertGreater(len(outs), 20)
        self.assertFalse(self.path.exists())

    def test_hook_does_not_change_pipeline_output(self):
        def go(hooked):
            stub = SwitchingStub(n_normal=40, later=RISK)
            pipe = MineGuardPipeline(PipelineConfig(), predictor=stub)
            if hooked:
                attach(pipe, self.path)
            outs, _ = run(pipe, SimSensors(nodes=(1, 2, 3), seed=2), 150)
            return [o.to_row() for o in outs], stub.calls

        plain_rows, plain_calls = go(False)
        hooked_rows, hooked_calls = go(True)
        self.assertEqual(hooked_rows, plain_rows)
        self.assertEqual(hooked_calls, plain_calls, "the model saw exactly the same feature rows")
        self.assertEqual(len(read_rows(self.path)), sum(r["status"] != "NORMAL" for r in plain_rows))

    def test_attach_twice_does_not_double_log(self):
        pipe = MineGuardPipeline(PipelineConfig(), predictor=SwitchingStub(n_normal=8, later=DECOY))
        attach(attach(pipe, self.path), self.path)
        outs, _ = run(pipe, SimSensors(nodes=(1,), seed=0), 100)       # 40 s calibration, then ~30 samples
        n_suspicious = sum(o.status != "NORMAL" for o in outs)
        self.assertGreater(n_suspicious, 10)                            # so the equality below cannot pass vacuously
        self.assertEqual(len(read_rows(self.path)), n_suspicious)


# ------------------------------------------------------------------------------------
@unittest.skipUnless(MODEL_PATH.exists(), "RF v6 model file not found")
class TestRealModel(TempDirCase):
    """The real RF through the real guardrails, on the simulator: 3 nodes, one vibration burst on node 1,
    one accelerating precursor on node 2, node 3 stays still."""

    def test_rows_only_for_the_non_normal_samples(self):
        cfg = PipelineConfig()
        pipe = attach(MineGuardPipeline(cfg, predictor=RFPredictor()), self.path)
        sim = SimSensors(nodes=(1, 2, 3), seed=0)
        sim.vib_factor[1] = lambda t: 8.0 if 80 <= t < 92 else 1.0
        ramp = lambda t: min(1.0, max(0.0, (t - 70) / 68)) ** 2
        sim.tilt_extra_deg[2] = lambda t: 3.8 * ramp(t)
        sim.disp_extra_mm[2] = lambda t: 33.0 * ramp(t)
        sim.vib_factor[2] = lambda t: 1 + 6.8 * ramp(t)
        outs, _ = run(pipe, sim, 190)

        by_node = {n: [o for o in outs if o.node == n] for n in ("NODE_01", "NODE_02", "NODE_03")}
        rows = read_rows(self.path)
        non_normal = [o for o in outs if o.top_class != "normal" or o.status != "NORMAL"]
        self.assertEqual(len(rows), len(non_normal))
        self.assertTrue(all(r["predicted_class"] != "normal" or r["guardrail_status"] != "NORMAL" for r in rows))
        self.assertTrue(all(r["guardrail_status"] in ("DECOY", "POSSIBLE", "CONFIRMED") for r in rows))
        self.assertTrue(any(r["node_id"] == "NODE_01" and r["predicted_class"] == "decoy_seismic" for r in rows), "burst was logged")
        self.assertTrue(any(r["node_id"] == "NODE_02" and r["guardrail_status"] == "CONFIRMED" for r in rows), "precursor was logged")
        self.assertFalse([r for r in rows if r["node_id"] == "NODE_03"], "the node that never moved has no rows")
        self.assertGreater(sum(o.status == "NORMAL" for o in by_node["NODE_03"]), 20)


# ------------------------------------------------------------------------------------
class TestRealVsReplayPaths(TempDirCase):
    """Two destinations, different folders, and nothing defaults to (or falls back on) the real one."""

    def test_port_decides_the_folder(self):
        for port in ("COM5", "COM12", r"\\.\COM12", "/dev/ttyUSB0", "/dev/cu.usbserial-1410"):
            self.assertEqual(log_path_for(port), REAL_LOG_PATH, port)
        for port in (None, "", "socket://127.0.0.1:9000", "loop://", "rfc2217://host:2217", "spy://COM5"):
            self.assertEqual(log_path_for(port), REPLAY_LOG_PATH, repr(port))

    def test_two_separate_folders_and_the_old_single_path_is_gone(self):
        self.assertEqual(REAL_LOG_PATH, HERE / "logs" / "real" / "suspicious_readings.csv")
        self.assertEqual(REPLAY_LOG_PATH, HERE / "logs" / "replay" / "suspicious_readings.csv")
        self.assertNotEqual(REAL_LOG_PATH.parent, REPLAY_LOG_PATH.parent)
        self.assertFalse(hasattr(suspicious_log, "LOG_PATH"), "the old single-file constant must not exist any more")
        self.assertNotIn(HERE / "logs" / "suspicious_readings.csv", (REAL_LOG_PATH, REPLAY_LOG_PATH))

    def test_nothing_defaults_to_the_real_folder(self):
        for fn in (suspicious_log.attach, suspicious_log.log_if_suspicious, suspicious_log.SuspiciousLog.__init__):
            self.assertEqual(inspect.signature(fn).parameters["path"].default, REPLAY_LOG_PATH, fn.__qualname__)

    def test_each_function_writes_only_to_the_path_it_is_given(self):
        real, replay = self.tmp / "real" / "s.csv", self.tmp / "replay" / "s.csv"
        log_if_suspicious(out(cls="decoy_seismic", status="DECOY"), "1,real-line", real)
        self.assertTrue(real.exists())
        self.assertFalse(replay.exists())
        pipe = attach(MineGuardPipeline(PipelineConfig(), predictor=SwitchingStub(n_normal=8, later=DECOY)), replay)
        run(pipe, SimSensors(nodes=(1,), seed=0), 100)
        self.assertTrue(replay.exists())
        self.assertEqual([r["raw_serial_line"] for r in read_rows(real)], ["1,real-line"],
                         "the replay pipeline wrote nothing to the real file")


class TestRunLiveRouting(TempDirCase):
    """run_live.main() end to end: the port argument alone decides which file gets the rows. The model is a stub and
    the serial port is faked, so neither the RF nor the project's real logs/ folder is involved."""

    def setUp(self):
        super().setUp()
        self.real = self.tmp / "logs" / "real" / "suspicious_readings.csv"
        self.replay = self.tmp / "logs" / "replay" / "suspicious_readings.csv"
        self.old = HERE / "logs" / "suspicious_readings.csv"             # the retired single file
        self.old_mtime = self.old.stat().st_mtime_ns if self.old.exists() else None
        self.n_runs = 0
        for patcher in (mock.patch.object(suspicious_log, "REAL_LOG_PATH", self.real),
                        mock.patch.object(suspicious_log, "REPLAY_LOG_PATH", self.replay),
                        mock.patch.object(run_live, "MineGuardPipeline", self._pipeline)):
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def _pipeline(cfg, calibrations=None, on_event=None):
        return MineGuardPipeline(cfg, predictor=SwitchingStub(n_normal=15, later=DECOY),
                                 calibrations=calibrations, on_event=on_event)

    def go(self, source_args, seed):
        """One run_live.main() call fed by simulated lines. Returns (stdout, the raw lines that were fed)."""
        lines = list(SimSensors(nodes=(1, 2, 3), seed=seed).lines(150))
        self.n_runs += 1
        n = self.n_runs
        argv = [*source_args, "--calib-file", str(self.tmp / f"calib{n}.json"),
                "--log-csv", str(self.tmp / f"live{n}.csv"), "--quiet"]
        if source_args[0] == "--replay":                                  # a saved log in the raw-log format
            log = self.tmp / f"replay{n}.log"
            log.write_text("".join(f"{t:.3f}\t{line}\n" for t, line in lines), encoding="utf-8")
            argv[1] = str(log)
            source = contextlib.nullcontext()
        else:                                                             # a port: fake the serial reader
            source = mock.patch.object(run_live, "serial_source", lambda *a, **k: iter(lines))
        buf = io.StringIO()
        with source, contextlib.redirect_stdout(buf):
            self.assertEqual(run_live.main(argv), 0)
        return buf.getvalue(), {line for _, line in lines}

    def test_port_decides_which_file_run_live_writes(self):
        out_a, fed_replay = self.go(["--replay", "-"], seed=10)
        self.assertIn(str(self.replay), out_a, "run_live must say where it is logging")
        self.assertTrue(self.replay.exists())
        self.assertFalse(self.real.exists(), "a replay run must not create the real file")
        n_replay = len(read_rows(self.replay))

        out_b, fed_real = self.go(["--port", "COM5"], seed=11)
        self.assertIn(str(self.real), out_b)
        self.assertTrue(self.real.exists())
        self.assertEqual(len(read_rows(self.replay)), n_replay, "a real-hardware run must not touch the replay file")
        n_real = len(read_rows(self.real))

        out_c, fed_sim = self.go(["--port", "socket://127.0.0.1:9000"], seed=12)      # the simulator's port
        self.assertIn(str(self.replay), out_c)
        self.assertEqual(len(read_rows(self.real)), n_real, "a simulator port must not touch the real file")
        self.assertGreater(len(read_rows(self.replay)), n_replay)

        # provenance: every raw line is in the file of the run that fed it, and in no other
        self.assertFalse(fed_real & (fed_replay | fed_sim), "premise: the three runs share no raw line")
        real_lines = {r["raw_serial_line"] for r in read_rows(self.real)}
        replay_lines = {r["raw_serial_line"] for r in read_rows(self.replay)}
        self.assertTrue(real_lines and real_lines <= fed_real)
        self.assertTrue(replay_lines and replay_lines <= (fed_replay | fed_sim))
        self.assertFalse(real_lines & (fed_replay | fed_sim))
        self.assertFalse(replay_lines & fed_real)

        # nothing was written to the retired single file, and no third file appeared beside the two folders
        self.assertEqual(self.old.stat().st_mtime_ns if self.old.exists() else None, self.old_mtime)
        self.assertFalse((self.tmp / "logs" / "suspicious_readings.csv").exists())
        self.assertEqual(sorted(p.name for p in (self.tmp / "logs").iterdir()), ["real", "replay"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
