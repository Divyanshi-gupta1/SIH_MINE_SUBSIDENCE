"""
Live pipeline: receiver Arduino (serial) -> conversion + sanity gate -> RF v6 -> persistence /
confidence guardrails -> console + CSV log.

    python run_live.py --port COM5
    python run_live.py --replay logs/raw_20260923.txt       # re-run a saved raw log
    python run_live.py --port COM5 --recalibrate            # node was re-installed / moved

Each node calibrates itself once (held still ~calib_windows x sample_period_s), then the
calibration (unit scales, tilt/displacement zero, noise floors) is saved to --calib-file and reused
on the next start, so "displacement since install" survives restarts.

Status per sample:  NORMAL | DECOY (vibration-only, benign) | POSSIBLE (risk vote, low confidence or
not yet N in a row) | CONFIRMED (N consecutive confident votes -> alert fires once).
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

from config import HERE, PipelineConfig
from inference_pipeline import MineGuardPipeline
from sources import file_source, serial_source
from suspicious_log import attach as log_suspicious, log_path_for
from dashboard_sync import DashboardSync


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--port")
    src.add_argument("--replay")
    ap.add_argument("--baud", type=int)
    ap.add_argument("--config")
    ap.add_argument("--profile", default="bench", choices=["bench", "field"])
    ap.add_argument("--sample-period-s", type=float)
    ap.add_argument("--persist-window-s", type=float)
    ap.add_argument("--calib-file", default=str(HERE / "calibration.json"))
    ap.add_argument("--recalibrate", action="store_true", help="ignore/overwrite the saved calibration")
    ap.add_argument("--log-csv", default=None, help="per-sample log (default logs/live_<time>.csv)")
    ap.add_argument("--raw-log", default=None, help="save raw serial lines here (replayable)")
    ap.add_argument("--time-scale", type=float, default=1.0,
                    help="ONLY for an accelerated simulator: fake_serial.py --speed N pairs with --time-scale N")
    ap.add_argument("--quiet", action="store_true", help="only print non-NORMAL samples and events")
    ap.add_argument("--stale-after-s", type=float, default=30.0)
    ap.add_argument("--no-dashboard", action="store_true", help="disable automatic sync to mineguard-final dashboard")
    ap.add_argument("--dashboard-url", default="http://localhost:3000", help="mineguard-final dashboard URL")
    args = ap.parse_args(argv)

    cfg = PipelineConfig.load(args.config, args.profile)
    if args.sample_period_s:
        cfg.sample_period_s = args.sample_period_s
    if args.persist_window_s:
        cfg.persist_window_s = args.persist_window_s
    if args.baud:
        cfg.baud = args.baud

    calib_path = Path(args.calib_file)
    cals = None
    if calib_path.exists() and not args.recalibrate:
        cals = MineGuardPipeline.load_calibrations(calib_path)
        print(f"using saved calibration for {sorted(cals)} ({calib_path})")
    need_save = {"flag": False}

    def on_event(t, node, kind, msg):
        print(f"[{datetime.now():%H:%M:%S}] {node} {kind}: {msg}")
        if kind == "calibrated":
            need_save["flag"] = True

    pipe = MineGuardPipeline(cfg, calibrations=cals, on_event=on_event)
    pipe = log_suspicious(pipe, log_path_for(args.port))    # real COM port -> logs/real/, replay or simulator -> logs/replay/
    print(f"suspicious readings -> {pipe.suspicious_log.path}")
    log_path = Path(args.log_csv) if args.log_csv else HERE / "logs" / f"live_{datetime.now():%Y%m%d_%H%M%S}.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"sample every {cfg.sample_period_s:g}s; alert after {cfg.persist_n} consecutive samples "
          f"(~{cfg.persist_n * cfg.sample_period_s:g}s) with p >= {cfg.confirm_confidence:.2f}; log -> {log_path}")

    dash_sync = None if args.no_dashboard else DashboardSync(args.dashboard_url)
    if dash_sync:
        print(f"dashboard live sync active -> {dash_sync.dashboard_url} & mineguard-final/data/live_state.json")

    it = (serial_source(args.port, cfg.baud, raw_log=args.raw_log, time_scale=args.time_scale) if args.port else file_source(args.replay))
    n_alerts, last_stale_check, t = 0, 0.0, 0.0
    writer = None
    with open(log_path, "w", newline="") as fh:
        try:
            for t, line in it:
                for o in pipe.feed_line(t, line):
                    if dash_sync:
                        dash_sync.update_sample(o)
                    row = o.to_row()
                    if writer is None:
                        writer = csv.DictWriter(fh, fieldnames=list(row))
                        writer.writeheader()
                    writer.writerow(row)
                    fh.flush()
                    n_alerts += o.alert_fired
                    if o.status != "NORMAL" or not args.quiet:
                        f = o.features
                        flag = "!!! ALERT " if o.alert_fired else ("    " if o.status == "NORMAL" else "  * ")
                        print(f"{flag}{datetime.now():%H:%M:%S} {o.node} {o.status:9s} {o.top_class:20s} p={o.top_p:.2f} "
                              f"| tdev={f['tilt_deviation_from_node_baseline']:+.2f} vib={f['vibration_rms']:.3f} "
                              f"vdur={f['vibration_duration']} disp={f['displacement_mm']:.1f}mm "
                              f"{o.note}")
                if need_save["flag"]:
                    pipe.save_calibrations(calib_path)
                    need_save["flag"] = False
                    print(f"calibration saved -> {calib_path}")
                if t - last_stale_check > 10:
                    last_stale_check = t
                    for n in pipe.stale_nodes(t, args.stale_after_s):
                        print(f"[{datetime.now():%H:%M:%S}] {n} WARNING: no data for >{args.stale_after_s:g}s "
                              f"(radio / TDM slot / power?)")
        except KeyboardInterrupt:
            print("\nstopped")
        for o in pipe.flush(t):
            if o.status != "NORMAL":
                print(f"  * {o.node} {o.status} {o.top_class} p={o.top_p:.2f}")

    s = pipe.summary()
    print(f"\nalerts fired: {n_alerts}")
    print(f"parser rejects: {s['parser']}   reading drops: {s['reading_drops']}")
    for n, v in s["nodes"].items():
        print(f"  {n}: {v['samples']} model samples, window drops {v['window_drops']}"
              f"{'  (SENSOR_FAULT)' if v['faulted'] else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
