"""
Vibration-only bench test: tilt and displacement stay put, only vibration spikes.
Expected model behaviour: `decoy_seismic` -- never a subsidence/risk class.

    python test_vibration_only.py --source serial --port COM5 --nodes 1,2,3

Procedure (serial): keep still while the nodes calibrate; then, when prompted, shake the table /
tap next to the node for ~2-4 sample periods (bench default 4-8 s) WITHOUT tilting or sliding the
node, then keep still again. Training decoys last 2-4 samples, so a much longer burst is outside
what the model has seen -- use --burst-s in the simulator to explore that.

How a node is judged (evaluate_vibration):
  * burst samples  = samples whose model-frame vibration is >= --burst-ratio x the training
                     resting level (vibration_rms / 0.031). No burst seen -> NO_BURST (not a pass).
  * setup check    = during the QUIET samples tilt/displacement must stay inside their noise floor
                     (<= --max-tilt-deg / --max-disp-mm). Otherwise the node was moved -> INVALID.
  * FAIL           = ANY sample of the whole run voted a risk class, or a POSSIBLE/CONFIRMED status
                     appeared, or < --min-decoy-fraction of burst samples voted decoy_seismic.
  * PASS           = no risk vote at all AND the burst is recognised as decoy_seismic.
Exit code: 0 PASS, 1 FAIL, 2 INVALID (no usable burst / node was moved / no data).
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter

from config import TRAIN, PipelineConfig
from harness_common import (EXIT_FAIL, EXIT_INVALID, EXIT_PASS, SIM_BANNER, add_common_args, build_config,
                            build_pipeline, calib_span_s, collect, expected_nodes, fmt_feats, line_source,
                            make_sim, write_reports)


def evaluate_vibration(records: dict, want: set, cfg: PipelineConfig, duration_s: float,
                       burst_ratio: float = 3.0, min_decoy_fraction: float = 0.5,
                       max_tilt_deg: float = 0.5, max_disp_mm: float = 3.0, min_coverage: float = 0.5,
                       drops: dict | None = None) -> dict:
    """Pure function (unit-testable). records: node -> [SampleOutput]."""
    is_risk = lambda c: c != cfg.normal_class and c not in cfg.decoy_classes
    expected_n = duration_s / cfg.sample_period_s
    nodes = {}
    for node in sorted(want):
        recs = records.get(node, [])
        ratio = lambda o: o.features["vibration_rms"] / TRAIN.VIB_BASELINE_MEDIAN
        burst = [o for o in recs if ratio(o) >= burst_ratio]
        quiet = [o for o in recs if ratio(o) < burst_ratio]
        # model-frame tilt/displacement are already noise-floored, so > 0 means real movement
        q_tilt = max((o.features["tilt_deg"] - cfg.tilt_rest_offset_deg for o in quiet), default=0.0)
        q_disp = max((o.features["displacement_mm"] for o in quiet), default=0.0)
        risk = [o for o in recs if is_risk(o.top_class)]
        flagged = [o for o in recs if o.status in ("POSSIBLE", "CONFIRMED")]
        dec_burst = [o for o in burst if o.top_class in cfg.decoy_classes]
        frac = len(dec_burst) / len(burst) if burst else 0.0
        info = {
            "samples": len(recs), "burst_samples": len(burst), "quiet_samples": len(quiet),
            "burst_class_counts": dict(Counter(o.top_class for o in burst)),
            "run_class_counts": dict(Counter(o.top_class for o in recs)),
            "decoy_fraction_in_burst": round(frac, 3), "risk_votes": len(risk),
            "guardrail_flagged_samples": len(flagged), "alerts_fired": sum(o.alert_fired for o in recs),
            "peak_vibration_ratio": round(max((ratio(o) for o in recs), default=0.0), 2),
            "quiet_max_tilt_deg": round(q_tilt, 3), "quiet_max_disp_mm": round(q_disp, 3),
            "burst_max_tilt_deg": round(max((o.features["tilt_deg"] - cfg.tilt_rest_offset_deg for o in burst),
                                            default=0.0), 3),
            "burst_max_disp_mm": round(max((o.features["displacement_mm"] for o in burst), default=0.0), 3),
            "burst_timeline": [{"t": round(o.t, 1), "class": o.top_class, "p": round(o.top_p, 2),
                                "status": o.status, "vib_x": round(ratio(o), 1),
                                "vdur": o.features["vibration_duration"]} for o in burst],
            "violations": [{"t": round(o.t, 2), "class": o.top_class, "p": round(o.top_p, 3), "status": o.status,
                            "features": o.features} for o in recs if is_risk(o.top_class)],
        }
        if len(recs) < min_coverage * expected_n:
            status, why = "INVALID", (f"only {len(recs)} valid samples (expected ~{expected_n:.0f}); "
                                      f"window drops: {(drops or {}).get(node, {})}")
        elif q_tilt > max_tilt_deg or q_disp > max_disp_mm:
            status, why = "INVALID", (f"node moved outside the vibration burst (tilt {q_tilt:.2f} deg, "
                                      f"disp {q_disp:.1f} mm) -- not a vibration-only setup")
        elif risk or flagged:
            status, why = "FAIL", (f"vibration-only data produced {len(risk)} risk-class vote(s) and "
                                   f"{len(flagged)} POSSIBLE/CONFIRMED status(es)")
        elif not burst:
            status, why = "NO_BURST", "no vibration spike seen on this node (control node?) -- stayed non-risk"
        elif frac < min_decoy_fraction:
            status, why = "FAIL", (f"burst not recognised as decoy_seismic: {frac:.0%} decoy "
                                   f"(need {min_decoy_fraction:.0%}), got {info['burst_class_counts']}")
        else:
            status, why = "PASS", f"{len(dec_burst)}/{len(burst)} burst samples = decoy_seismic, 0 risk votes"
        nodes[node] = {"status": status, "why": why, **info}

    st = [r["status"] for r in nodes.values()]
    if "FAIL" in st:
        overall = "FAIL"
    elif "PASS" in st and "INVALID" not in st:
        overall = "PASS"
    elif "PASS" in st:
        overall = "INVALID"          # a node with unusable data: don't claim a clean pass
    else:
        overall = "INVALID"
    return {"overall": overall, "nodes": nodes}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    ap.add_argument("--duration-s", type=float, default=120.0, help="observation after calibration")
    ap.add_argument("--burst-ratio", type=float, default=3.0)
    ap.add_argument("--min-decoy-fraction", type=float, default=0.5)
    ap.add_argument("--max-tilt-deg", type=float, default=0.5)
    ap.add_argument("--max-disp-mm", type=float, default=3.0)
    ap.add_argument("--burst-s", type=float, default=None, help="simulator: burst length (default 3 sample periods)")
    ap.add_argument("--burst-factor", type=float, default=8.0, help="simulator: noise multiplier during the burst")
    ap.add_argument("--burst-nodes", default="1,2", help="simulator: nodes that get shaken (others are controls)")
    args = ap.parse_args(argv)
    cfg = build_config(args)
    want = expected_nodes(args)
    sim = None
    span = calib_span_s(cfg)
    if args.source == "sim":
        print(SIM_BANNER)
        want = want or {"NODE_01", "NODE_02", "NODE_03"}
        sim = make_sim(args, cfg)
        burst_s = args.burst_s or 3 * cfg.sample_period_s
        t0 = span + 0.4 * args.duration_s
        for n in (int(x) for x in args.burst_nodes.split(",") if x):
            sim.vib_factor[n] = lambda t, t0=t0, b=burst_s: args.burst_factor if t0 <= t < t0 + b else 1.0
        print(f"  sim: {args.burst_nodes} shaken x{args.burst_factor:g} for {burst_s:g}s at t={t0:g}s; other nodes = controls")

    pipe = build_pipeline(args, cfg)
    print(f"VIBRATION-ONLY TEST: nodes calibrate for ~{span:.0f}s (keep still), then a {args.duration_s:.0f}s window.")

    def prompt(node, t, n_done):
        if want is not None and n_done < len(want):
            return
        if args.source == "serial":
            print(f"\n>>> CALIBRATED. Stay still ~{0.3 * args.duration_s:.0f}s, then SHAKE/TAP for ~{3 * cfg.sample_period_s:g}s "
                  f"(no tilting/sliding), then stay still again.\n")

    lines = line_source(args, cfg, span + args.duration_s + 30, sim)
    records, t_cal = collect(pipe, lines, want, args.duration_s, on_calibrated=prompt)

    summary = pipe.summary()
    drops = {n: v["window_drops"] for n, v in summary["nodes"].items()}
    want = want or set(records)
    ev = evaluate_vibration(records, want, cfg, args.duration_s, args.burst_ratio, args.min_decoy_fraction,
                            args.max_tilt_deg, args.max_disp_mm, drops=drops)
    report = {"test": "vibration_only", "source": args.source, "config": vars(cfg) | {"persist_n": cfg.persist_n},
              "duration_s": args.duration_s, "pipeline_summary": summary, "result": ev}
    base = write_reports("vibration", report, records, args.report_dir)

    print("\n" + "=" * 78)
    for node, r in ev["nodes"].items():
        print(f"{node}: {r['status']:8s} {r['samples']:4d} samples, {r['burst_samples']} burst  "
              f"burst={r['burst_class_counts']}  run={r['run_class_counts']}")
        print(f"          {r['why']}")
        print(f"          peak vibration x{r['peak_vibration_ratio']}, quiet tilt<={r['quiet_max_tilt_deg']} deg "
              f"disp<={r['quiet_max_disp_mm']} mm, during burst tilt<={r['burst_max_tilt_deg']} disp<={r['burst_max_disp_mm']}")
        for b in r["burst_timeline"][:12]:
            print(f"            t={b['t']:7.1f}s vib x{b['vib_x']:<5} vdur={b['vdur']} -> {b['class']} "
                  f"p={b['p']} [{b['status']}]")
        for v in r["violations"][:5]:
            print(f"          !! t={v['t']:.1f}s {v['class']} p={v['p']} {v['features']}")
    print(f"drops: parser={summary['parser']} readings={summary['reading_drops']} windows={drops}")
    print(f"report: {base}.json / .csv")
    print(f"\nOVERALL: {ev['overall']}" + ("   <-- FLAGGED: vibration-only data must never read as subsidence"
                                          if ev["overall"] == "FAIL" else ""))
    return {"PASS": EXIT_PASS, "FAIL": EXIT_FAIL, "INVALID": EXIT_INVALID}[ev["overall"]]


if __name__ == "__main__":
    sys.exit(main())
