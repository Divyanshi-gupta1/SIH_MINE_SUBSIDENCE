"""
Static (no-movement) bench test.

Leave every node completely still (bolted down, nothing touching the table, no one walking
nearby). The harness calibrates, then records `--duration-s` (default 300 = 5 min) of
predictions and ASSERTS the model says "normal" on every single sample.

    python test_static_no_movement.py --source serial --port COM5 --nodes 1,2,3
    python test_static_no_movement.py --source sim            # logic check only, no hardware

Any non-normal vote is flagged. Two knobs, both default 0 (strict, as required):
  --max-risk-votes N     tolerated votes for a risk class (subsidence_precursor, ...)
  --allow-decoy-blips N  tolerated lone votes for the benign decoy class
Exit code: 0 PASS, 1 FAIL, 2 INVALID (not enough valid data / setup problem -- says nothing
about the model).
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from config import PipelineConfig
from harness_common import (EXIT_FAIL, EXIT_INVALID, EXIT_PASS, SIM_BANNER, add_common_args, build_config,
                            build_pipeline, calib_span_s, collect, expected_nodes, fmt_feats, line_source,
                            make_sim, write_reports)


def evaluate_static(records: dict, want: set, duration_s: float, cfg: PipelineConfig,
                    max_risk_votes: int = 0, allow_decoy_blips: int = 0, min_coverage: float = 0.5,
                    drops: dict | None = None) -> dict:
    """Pure function (unit-testable). records: node -> [SampleOutput]."""
    expected_n = duration_s / cfg.sample_period_s
    nodes, overall = {}, "PASS"
    for node in sorted(want):
        recs = records.get(node, [])
        classes = Counter(o.top_class for o in recs)
        risk = [o for o in recs if o.top_class != cfg.normal_class and o.top_class not in cfg.decoy_classes]
        decoy = [o for o in recs if o.top_class in cfg.decoy_classes]
        flagged = [o for o in recs if o.status in ("POSSIBLE", "CONFIRMED")]
        cov = len(recs) / expected_n if expected_n else 0.0
        if cov < min_coverage:
            status, why = "INVALID", (f"only {len(recs)} valid samples, expected ~{expected_n:.0f} "
                                      f"({cov:.0%}); window drops: {(drops or {}).get(node, {})}")
        elif len(risk) > max_risk_votes:
            status, why = "FAIL", f"{len(risk)} samples voted a RISK class (allowed {max_risk_votes})"
        elif len(decoy) > allow_decoy_blips:
            status, why = "FAIL", f"{len(decoy)} samples voted decoy_seismic (allowed {allow_decoy_blips})"
        else:
            status, why = "PASS", "every sample normal" if not (risk or decoy) else "within tolerance"
        nodes[node] = {
            "status": status, "why": why, "samples": len(recs), "expected_samples": round(expected_n),
            "class_counts": dict(classes), "risk_votes": len(risk), "decoy_votes": len(decoy),
            "guardrail_flagged_samples": len(flagged),
            "alerts_fired": sum(o.alert_fired for o in recs),
            "max_nonnormal_p": round(max((o.top_p for o in recs if o.top_class != cfg.normal_class),
                                         default=0.0), 4),
            "max_tilt_raw_deg": round(max((o.diag["tilt_raw_deg"] for o in recs), default=0.0), 4),
            "max_disp_raw_mm": round(max((abs(o.diag["disp_raw_mm"]) for o in recs), default=0.0), 3),
            "violations": [{"t": round(o.t, 2), "class": o.top_class, "p": round(o.top_p, 3),
                            "status": o.status, "features": o.features}
                           for o in recs if o.top_class != cfg.normal_class],
        }
    for r in nodes.values():
        if r["status"] == "FAIL":
            overall = "FAIL"
        elif r["status"] == "INVALID" and overall == "PASS":
            overall = "INVALID"
    return {"overall": overall, "nodes": nodes}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    ap.add_argument("--duration-s", type=float, default=300.0, help="static observation after calibration")
    ap.add_argument("--max-risk-votes", type=int, default=0)
    ap.add_argument("--allow-decoy-blips", type=int, default=0)
    args = ap.parse_args(argv)
    cfg = build_config(args)
    want = expected_nodes(args)
    if args.source == "sim":
        print(SIM_BANNER)
        want = want or {"NODE_01", "NODE_02", "NODE_03"}

    pipe = build_pipeline(args, cfg)
    print(f"STATIC TEST: keep all nodes still. calibrating ~{calib_span_s(cfg):.0f}s, then observing "
          f"{args.duration_s:.0f}s (sample every {cfg.sample_period_s:g}s, persistence {cfg.persist_n} "
          f"samples = {cfg.persist_n * cfg.sample_period_s:g}s)")
    total = calib_span_s(cfg) + args.duration_s + 30
    lines = line_source(args, cfg, total, make_sim(args, cfg) if args.source == "sim" else None)
    records, t_cal = collect(pipe, lines, want, args.duration_s)
    if args.calib_file and not Path(args.calib_file).exists():
        pipe.save_calibrations(args.calib_file)

    summary = pipe.summary()
    drops = {n: v["window_drops"] for n, v in summary["nodes"].items()}
    want = want or set(records)
    ev = evaluate_static(records, want, args.duration_s, cfg, args.max_risk_votes, args.allow_decoy_blips,
                         drops=drops)
    report = {"test": "static_no_movement", "source": args.source, "config": vars(cfg) | {"persist_n": cfg.persist_n},
              "duration_s": args.duration_s, "pipeline_summary": summary, "result": ev}
    base = write_reports("static", report, records, args.report_dir)

    print("\n" + "=" * 78)
    for node, r in ev["nodes"].items():
        print(f"{node}: {r['status']:8s} {r['samples']:4d} samples  classes={r['class_counts']}  "
              f"max non-normal p={r['max_nonnormal_p']}  alerts={r['alerts_fired']}")
        print(f"          {r['why']}   (max tilt {r['max_tilt_raw_deg']} deg, max |disp| {r['max_disp_raw_mm']} mm)")
        for v in r["violations"][:10]:
            print(f"          !! t={v['t']:.1f}s {v['class']} p={v['p']} status={v['status']}  {v['features']}")
    print(f"drops: parser={summary['parser']} readings={summary['reading_drops']} "
          f"windows={drops}")
    print(f"report: {base}.json / .csv")
    print(f"\nOVERALL: {ev['overall']}" + ("   <-- FLAGGED: model produced non-normal output on static data"
                                          if ev["overall"] == "FAIL" else ""))
    return {"PASS": EXIT_PASS, "FAIL": EXIT_FAIL, "INVALID": EXIT_INVALID}[ev["overall"]]


if __name__ == "__main__":
    sys.exit(main())
