"""
Task 1 -- format audit.

  python audit_format.py --training
      Feature columns / units / value ranges the RF v6 was trained on (per class), computed from
      synthetic/simulated_mesh_data_v6_with_external.csv -> training_feature_stats.json

  python audit_format.py --probe COM5 [--lines 300]      (live receiver Arduino)
  python audit_format.py --probe path/to/serial_log.txt   (saved Serial Monitor output / raw log)
      Reads real lines and reports what they actually are: column count, numeric ranges, accel /
      gyro / ultrasonic units, ultrasonic resolution, per-node packet rate, and every mismatch
      against what the model + conversion layer expect. Run this FIRST on the real hardware --
      the serial format assumed in config.py is a guess until this says otherwise.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from config import FEATURES, HERE, TRAIN, TRAIN_CSV, PipelineConfig
from sensor_conversion import (ACCEL_LSB_PER_G, CalibrationError, LineParser, infer_accel_scale)
from sources import file_source, serial_source

UNITS = {
    "tilt_deg": "degrees (inclination; resting 0.05-0.30, permanent offsets up to ~5-7 after events)",
    "vibration_rms": "unitless 'g-scale' MEMS RMS (README: arbitrary but consistent; resting median 0.031)",
    "displacement_mm": "mm, cumulative since start of record (drift 0.06-0.33 mm/day + event steps)",
    "crack_signal": "0/1 binary crack sensor",
    "vibration_duration": "samples above per-node threshold; run counts 2,3,4.. (off-by-one quirk)",
    "tilt_vibration_correlation": "Pearson r over trailing 8 samples, -1..1",
    "displacement_persistence": "0/1 causal flag",
    "tilt_deviation_from_node_baseline": "degrees; tilt - trailing 672-sample median",
}


def label_training_rows(df: pd.DataFrame) -> pd.Series:
    """Same ground-truth rule as model/build_model_v6.py (buildup rows only, tails excluded upstream)."""
    ev = pd.read_csv(TRAIN_CSV.parent / "events_log.csv",
                     parse_dates=["start_timestamp", "subsidence_event_timestamp", "end_timestamp"])
    y = pd.Series("normal", index=df.index)
    for _, e in ev.iterrows():
        m = df.node_id == e.node_id
        if e.event_type == "subsidence_precursor":
            y[m & (df.timestamp >= e.start_timestamp) & (df.timestamp <= e.subsidence_event_timestamp)] = e.event_type
        else:
            y[m & (df.timestamp >= e.start_timestamp) & (df.timestamp <= e.end_timestamp)] = e.event_type
    for lbl in ("subsidence_precursor", "decoy_seismic"):
        y[df["merged_label"].fillna("") == lbl] = lbl
    return y


def training_audit() -> dict:
    df = pd.read_csv(TRAIN_CSV, parse_dates=["timestamp"], low_memory=False)
    df["y"] = label_training_rows(df)
    out = {"rows": len(df), "sample_period_s": TRAIN.SAMPLE_PERIOD_S, "class_counts": df.y.value_counts().to_dict(),
           "features": {}}
    for f in FEATURES:
        entry = {"unit": UNITS[f], "overall": _q(df[f]), "by_class": {c: _q(g[f]) for c, g in df.groupby("y")}}
        out["features"][f] = entry
    (HERE / "training_feature_stats.json").write_text(json.dumps(out, indent=2))
    print(f"training rows: {len(df)}   sample period: {TRAIN.SAMPLE_PERIOD_S}s   classes: {out['class_counts']}\n")
    print(f"{'feature':36s} {'min':>9s} {'p1':>9s} {'median':>9s} {'p99':>9s} {'max':>9s}   unit")
    for f, e in out["features"].items():
        o = e["overall"]
        print(f"{f:36s} {o['min']:9.3f} {o['p1']:9.3f} {o['median']:9.3f} {o['p99']:9.3f} {o['max']:9.3f}   {e['unit']}")
    print("\nmedians by class (normal / decoy_seismic / subsidence_precursor):")
    for f, e in out["features"].items():
        bc = e["by_class"]
        print(f"  {f:36s} " + " / ".join(f"{bc[c]['median']:8.3f}" if c in bc else "     n/a" for c in
                                          ("normal", "decoy_seismic", "subsidence_precursor")))
    print(f"\nwritten: {HERE / 'training_feature_stats.json'}")
    return out


def _q(s: pd.Series) -> dict:
    return {"min": float(s.min()), "p1": float(s.quantile(.01)), "median": float(s.median()),
            "p99": float(s.quantile(.99)), "max": float(s.max())}


# ------------------------------------------------------------------------------------
def probe(source: str, n_lines: int, cfg: PipelineConfig, baud: int) -> list[str]:
    it = file_source(source) if Path(source).exists() else serial_source(source, baud, max_seconds=120)
    parser = LineParser(cfg)
    raw, unparsed, total = [], [], 0
    for t, line in it:
        total += 1
        r = parser.parse(line, t)
        if r is not None:
            raw.append(r)
        elif line.strip() and not line.strip().startswith(("#", "//")) and len(unparsed) < 5:
            unparsed.append(line)
        if total >= n_lines:
            break
    print(f"read {total} lines, parsed {len(raw)} with columns {parser.columns}; parser rejects: {dict(parser.stats)}")
    problems: list[str] = []
    if unparsed:
        print("  unparsed examples:", *unparsed[:3], sep="\n    ")
    if len(raw) < 20:
        problems.append("too few parseable lines -- set PipelineConfig.columns to match the sketch's Serial.print order")
        return _report(problems)

    by_node = defaultdict(list)
    for r in raw:
        by_node[r.node].append(r)
    print(f"nodes seen: {sorted(by_node)}")
    for node, rs in sorted(by_node.items()):
        ts = np.array([r.t for r in rs])
        dt = np.diff(ts)
        rate = 1.0 / np.median(dt) if len(dt) and np.median(dt) > 0 else float("nan")
        print(f"  {node}: {len(rs)} readings, median interval {np.median(dt) if len(dt) else float('nan'):.3f}s "
              f"(~{rate:.2f} Hz), max gap {dt.max() if len(dt) else 0:.2f}s")
        if rate == rate and rate * cfg.sample_period_s < cfg.min_readings_per_sample:
            problems.append(f"{node}: ~{rate:.2f} readings/s -> only {rate * cfg.sample_period_s:.1f} per "
                            f"{cfg.sample_period_s:g}s window (< min_readings_per_sample={cfg.min_readings_per_sample}); "
                            f"use sample_period_s >= {cfg.min_readings_per_sample / rate:.1f}")

    A = np.array([r.a for r in raw], float)
    G = np.array([r.g for r in raw], float)
    D = np.array([r.dist for r in raw], float)
    mag = np.linalg.norm(A, axis=1)
    print(f"\naccel raw: per-axis min {A.min(0)}, max {A.max(0)}, |a| median {np.median(mag):.4g}")
    try:
        per_g, counts = infer_accel_scale(mag, cfg)
        print(f"  -> reads as {'int16 counts' if counts else 'g / m/s^2'}; 1 g = {per_g:g} raw units"
              + (f"  (MPU full-scale +-{[fs for fs, v in ACCEL_LSB_PER_G.items() if v == per_g][0]} g)" if counts else ""))
        if counts and not np.allclose(A, np.round(A)):
            problems.append("accel looks like counts by magnitude but has fractional values -- check sketch scaling")
    except CalibrationError as e:
        problems.append(f"accel units: {e}")
    if np.abs(A).max() >= 32700:
        problems.append("accel hits int16 full scale (clipping/saturation) -- raise the MPU range or expect drops")

    if not np.isnan(G).all():
        print(f"gyro raw: median {np.nanmedian(G, 0)}, |max| {np.nanmax(np.abs(G)):.4g}  "
              f"(at rest expect ~0 +- bias; +-250 dps FS = 131 LSB/dps, so bias of tens of counts is normal)")
        if np.nanmax(np.abs(G)) <= 2000 and np.nanmedian(np.abs(G)) < 3:
            print("  -> small values: could be dps already; set gyro_units='dps' if so")
    else:
        problems.append("no gyro column: 'node being handled' guard is disabled")

    d = D[~np.isnan(D)]
    if len(d) == 0:
        problems.append("no ultrasonic column parsed -- displacement cannot be computed")
    else:
        med = float(np.median(d))
        cands = {u: med * f for u, f in (("cm", 1.0), ("mm", 0.1), ("us", 1 / 58.0)) }
        ok = [u for u, cm in cands.items() if cfg.dist_min_cm <= cm <= cfg.dist_max_cm]
        print(f"ultrasonic raw: median {med:.4g}, min {d.min():.4g}, max {d.max():.4g}; "
              f"plausible units for the 2-400 cm range: {ok or 'NONE'}  (config says {cfg.dist_unit})")
        if cfg.dist_unit not in ok:
            problems.append(f"ultrasonic median {med:.4g} is not a plausible distance if dist_unit={cfg.dist_unit!r}; "
                            f"candidates: {ok}")
        zeros = float(np.mean(d <= 0))
        if zeros > 0.02:
            print(f"  {zeros:.1%} zero/negative readings (no echo) -> dropped per reading, median-filtered per window")
        # resolution: look only at the central cluster (stray echoes / dropouts would corrupt the step)
        to_mm = {"cm": 10.0, "mm": 1.0, "us": 10.0 / 58.0}[cfg.dist_unit]
        central = d[(d > 0) & (np.abs(d - med) <= 0.1 * abs(med))]
        u = np.unique(np.round(central, 4))
        whole = bool(len(central) and np.allclose(central, np.round(central), atol=1e-6))
        if whole and cfg.dist_unit in ("cm", "mm"):
            res_mm = 1.0 * to_mm
            print(f"  central readings are all whole {cfg.dist_unit} -> resolution {res_mm:g} mm")
        elif len(u) > 1:
            res_mm = float(np.diff(u).min()) * to_mm
            print(f"  finest distinct step in the central cluster: {res_mm:.3g} mm")
        else:
            res_mm = None
            print("  central readings are constant (resolution coarser than the noise?)")
        if res_mm is not None and res_mm >= 5:
            problems.append(f"ultrasonic resolution is ~{res_mm:.0f} mm (integer cm?). Training displacement noise is "
                            f"0.05 mm and real precursors are 12-33 mm total: print float cm / raw echo microseconds "
                            f"from the sketch (calibration will set a deadband of at least this step)")
    return _report(problems)


def _report(problems: list[str]) -> list[str]:
    print("\n" + ("MISMATCHES / WARNINGS:" if problems else "no format problems found"))
    for p in problems:
        print("  - " + p)
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--training", action="store_true")
    ap.add_argument("--probe", metavar="PORT_OR_FILE")
    ap.add_argument("--lines", type=int, default=300)
    ap.add_argument("--config")
    ap.add_argument("--profile", default="bench")
    ap.add_argument("--baud", type=int, default=115200)
    args = ap.parse_args(argv)
    if not (args.training or args.probe):
        ap.error("give --training and/or --probe")
    cfg = PipelineConfig.load(args.config, args.profile)
    if args.training:
        training_audit()
    if args.probe:
        if args.training:
            print("\n" + "=" * 78)
        probe(args.probe, args.lines, cfg, args.baud)
    return 0


if __name__ == "__main__":
    sys.exit(main())
