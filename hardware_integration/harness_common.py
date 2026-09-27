"""Shared plumbing for the two bench-test harnesses: argument parsing, line sources
(live serial / replay / simulator), data collection, report files."""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from config import REPORT_DIR, PipelineConfig
from inference_pipeline import MineGuardPipeline, SampleOutput
from sensor_conversion import normalize_node
from sim_source import SimSensors
from sources import file_source, serial_source

EXIT_PASS, EXIT_FAIL, EXIT_INVALID = 0, 1, 2

SIM_BANNER = ("*** SIMULATED DATA ***  This exercises the harness/pipeline logic only. A pass here is NOT "
              "evidence about real hardware -- rerun with --source serial --port COMx on the bench.")


def add_common_args(ap: argparse.ArgumentParser):
    ap.add_argument("--source", choices=["sim", "serial", "replay"], default="sim")
    ap.add_argument("--port", help="serial port (COM5, /dev/ttyUSB0, loop://) for --source serial")
    ap.add_argument("--baud", type=int)
    ap.add_argument("--replay", help="raw log file for --source replay")
    ap.add_argument("--raw-log", help="with --source serial: also save every raw line here (replayable)")
    ap.add_argument("--time-scale", type=float, default=1.0,
                    help="ONLY for an accelerated simulator: fake_serial.py --speed N pairs with --time-scale N")
    ap.add_argument("--nodes", default=None, help="comma list of node numbers to wait for, e.g. 1,2,3")
    ap.add_argument("--config", help="JSON overrides for PipelineConfig")
    ap.add_argument("--profile", default="bench", choices=["bench", "field"])
    ap.add_argument("--sample-period-s", type=float)
    ap.add_argument("--persist-window-s", type=float)
    ap.add_argument("--calib-file", help="load calibration from here if it exists, else save after calibrating")
    ap.add_argument("--report-dir", default=str(REPORT_DIR))
    ap.add_argument("--seed", type=int, default=0, help="simulator seed")
    ap.add_argument("--sim-accel-noise-g", type=float, default=0.004)
    ap.add_argument("--sim-dist-noise-cm", type=float, default=0.15)


def build_config(args) -> PipelineConfig:
    cfg = PipelineConfig.load(args.config, args.profile)
    if args.sample_period_s:
        cfg.sample_period_s = args.sample_period_s
    if args.persist_window_s:
        cfg.persist_window_s = args.persist_window_s
    if args.baud:
        cfg.baud = args.baud
    return cfg


def expected_nodes(args) -> set | None:
    if not args.nodes:
        return None
    return {normalize_node(x) for x in args.nodes.split(",") if x.strip()}


def build_pipeline(args, cfg, log=print) -> MineGuardPipeline:
    cals = None
    if args.calib_file and Path(args.calib_file).exists():
        cals = MineGuardPipeline.load_calibrations(args.calib_file)
        log(f"loaded calibration for {sorted(cals)} from {args.calib_file}")

    def on_event(t, node, kind, msg):
        log(f"  [{t:8.1f}s] {node} {kind}: {msg}")

    return MineGuardPipeline(cfg, calibrations=cals, on_event=on_event)


def make_sim(args, cfg) -> SimSensors:
    nodes = sorted(int(n.split("_")[-1]) for n in (expected_nodes(args) or {"NODE_01", "NODE_02", "NODE_03"}))
    return SimSensors(nodes=nodes, seed=args.seed, accel_noise_g=args.sim_accel_noise_g,
                      dist_noise_cm=args.sim_dist_noise_cm)


def calib_span_s(cfg) -> float:
    return cfg.calib_windows * cfg.sample_period_s


def line_source(args, cfg, sim_total_s: float, sim: SimSensors | None = None):
    if args.source == "sim":
        return (sim or make_sim(args, cfg)).lines(sim_total_s)
    if args.source == "serial":
        if not args.port:
            raise SystemExit("--source serial needs --port")
        # wall-clock cap so a silent radio ends as INVALID instead of hanging forever
        return serial_source(args.port, cfg.baud, max_seconds=sim_total_s / args.time_scale + 90,
                             raw_log=args.raw_log, time_scale=args.time_scale)
    if not args.replay:
        raise SystemExit("--source replay needs --replay FILE")
    return file_source(args.replay)


def collect(pipe: MineGuardPipeline, lines, want: set | None, duration_s: float,
            log=print, on_calibrated=None, progress_every_s: float = 30.0):
    """Feed lines until every wanted node has produced `duration_s` seconds of predictions after
    its own calibration finished. Returns (records_by_node, t_calibrated_by_node)."""
    records: dict[str, list[SampleOutput]] = defaultdict(list)
    t_cal: dict[str, float] = {}
    last_t: dict[str, float] = {}
    seen_events = 0
    next_progress = None
    t = 0.0

    def done() -> bool:
        nodes = want if want is not None else set(pipe.nodes)
        return bool(nodes) and all(n in t_cal and last_t.get(n, 0) - t_cal[n] >= duration_s for n in nodes)

    for t, line in lines:
        for o in pipe.feed_line(t, line):
            records[o.node].append(o)
            last_t[o.node] = o.t
        while seen_events < len(pipe.events):
            et, en, ek, _ = pipe.events[seen_events]
            seen_events += 1
            if ek == "calibrated":
                t_cal[en] = et
                if on_calibrated:
                    on_calibrated(en, et, len(t_cal))
        if next_progress is None and t_cal:
            next_progress = t + progress_every_s
        if next_progress is not None and t >= next_progress:
            next_progress = t + progress_every_s
            log("  progress: " + ", ".join(
                f"{n}: {len(records[n])} samples" for n in sorted(pipe.nodes)))
        if done():
            break
    for o in pipe.flush(t):
        records[o.node].append(o)
        last_t[o.node] = o.t
    return records, t_cal


def write_reports(name: str, report: dict, records: dict, report_dir: str) -> Path:
    d = Path(report_dir)
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = d / f"{name}_{report['source']}_{stamp}"
    base.with_suffix(".json").write_text(json.dumps(report, indent=2, default=str))
    rows = [o.to_row() for n in sorted(records) for o in records[n]]
    if rows:
        with open(base.with_suffix(".csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    return base


def fmt_feats(o: SampleOutput) -> str:
    f = o.features
    return (f"tilt={f['tilt_deg']:.3f} vib={f['vibration_rms']:.3f} disp={f['displacement_mm']:.2f} "
            f"vdur={f['vibration_duration']} corr={f['tilt_vibration_correlation']:+.2f} "
            f"persist={f['displacement_persistence']} tdev={f['tilt_deviation_from_node_baseline']:+.3f}")
