"""
Headless self-test for the virtual simulator: no server, no browser, no wall-clock waiting.

    python virtual_simulator/backend/selftest.py

Drives engine.Simulator in fast-forward through the same code path the server uses and checks that
  1. a quiet installation never raises a risk vote or an alert,
  2. the "Vibration only" preset is read as a benign vibration event on every node, never as subsidence,
  3. the "Full progression" preset ends with a confirmed alert on all three zones, in zone order,
  4. hardware_integration/ (and the other model-team folders) are unchanged afterwards: same files, sizes and
     modification times, including __pycache__ (so importing them did not write bytecode there).
Exit code 0 = all pass, 1 = a check failed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import NODES, ROOT, Simulator   # noqa: E402

GUARDED = ["hardware_integration", "synthetic", "model", "clean_data", "reference", "external"]
SKIP_DIRS = {"logs", "reports"}                     # only written by hardware_integration's own CLI tools


def fingerprint() -> dict:
    out = {}
    for name in GUARDED:
        base = ROOT / name
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if f.is_file() and not (SKIP_DIRS & set(f.relative_to(ROOT).parts)):
                st = f.stat()
                out[str(f.relative_to(ROOT))] = (st.st_size, st.st_mtime_ns)   # size+mtime: cheap on big CSVs
    return out


results = []


def check(name: str, ok: bool, detail: str = ""):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


def samples(sim, n):
    return list(sim.history[n])


def main() -> int:
    before = fingerprint()
    print(f"guarding {len(before)} files in {', '.join(GUARDED)}")
    sim = Simulator()
    print(f"model classes: {sim.predictor.classes}")

    print("\n1. quiet installation, 4 simulated minutes")
    sim.advance_virtual(240)
    risk = {n: [s for s in samples(sim, n) if s["status"] in ("POSSIBLE", "CONFIRMED")] for n in NODES}
    total = sum(len(samples(sim, n)) for n in NODES)
    check("no risk votes, no alerts", not any(risk.values()) and not any(sim.alert_active.values()),
          f"{total} samples, risk votes per node: {[len(v) for v in risk.values()]}")

    print("\n2. Vibration only preset")
    sim.apply_preset("reset")
    sim.apply_preset("vibration_only")
    sim.advance_virtual(40)
    for n in NODES:
        s = samples(sim, n)
        decoy = sum(x["status"] == "DECOY" for x in s)
        risky = sum(x["status"] in ("POSSIBLE", "CONFIRMED") for x in s)
        check(f"N{n}: read as vibration-only, never subsidence", decoy >= 3 and risky == 0 and not sim.alert_active[n],
              f"{decoy} decoy samples, {risky} risk samples")
    check("tilt and displacement never moved", all(sim.actual[n]["tilt"] == 0 and sim.actual[n]["disp"] == 0 for n in NODES))

    print("\n3. Full progression preset")
    sim.apply_preset("reset")
    sim.apply_preset("full_progression")
    first = {}
    for _ in range(180):
        sim.advance_virtual(1)
        for n in NODES:
            if sim.alert_active[n] and n not in first:
                first[n] = sim.t_live
    check("all three zones raise a confirmed alert", set(first) == set(NODES), f"first alert at T+{ {n: round(t) for n, t in first.items()} } s")
    check("zones alert in order N1, N2, N3", len(first) == 3 and first[1] < first[2] < first[3])
    check("no alert before the ground has moved (N1 first alert after T+30 s)", first.get(1, 0) > 30)
    events = [e["title"] for e in sim.events]
    check("alert log has confirmed alerts", events.count("Alert confirmed") >= 3, f"{events.count('Alert confirmed')} logged")

    print("\n4. model-team folders untouched")
    after = fingerprint()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    check("hardware_integration/, synthetic/, model/, clean_data/, reference/, external/ unchanged (files, sizes, mtimes)", not changed,
          f"changed: {changed[:5]}" if changed else f"{len(after)} files identical")

    ok = all(results)
    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
