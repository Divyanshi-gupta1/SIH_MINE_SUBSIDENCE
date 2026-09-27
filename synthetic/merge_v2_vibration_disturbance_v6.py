"""
v6: merge Divyanshi's v2 `vibration_disturbance` rows into training.

CONTEXT: Divyanshi confirmed `vibration_disturbance` in
external/v2_engineered.csv is a seismic/noise-type disturbance used for
false-alarm testing -- the same semantic role as our `decoy_seismic`
class. This resolves the pending conflict flagged in v5 / external/README.
Our model had already independently classified 93% of these rows as
`decoy_seismic`, which is now confirmed correct.

  - MERGE : the 104 `vibration_disturbance` rows (5 v2 nodes:
            NODE_V2_01/03/04/06/08), all mapped to `decoy_seismic`.
  - Built ON TOP OF simulated_mesh_data_v5_with_external.csv (which
            already carries the 176 escalation rows -> subsidence_precursor).
  - v2 `normal` rows: still NOT merged here -- see
            analyze_v2_normal_merge_v6.py for the merge-vs-not analysis
            that informs that decision.

FEATURE RECOMPUTE CHECK (task step 2):
  The v5 interaction risk was: v2 escalation episodes have ELEVATED tilt
  that reverts to baseline afterward, so naively recomputing
  `tilt_deviation_from_node_baseline` over only the imported (elevated)
  rows understates it.

  That risk DOES NOT APPLY to `vibration_disturbance`: tilt never rises
  during one. Checked from external/v2_raw.csv -- per-node mean tilt_deg
  before / during / after each disturbance is flat to within ~0.01 deg
  (e.g. NODE_V2_01: 0.241 / 0.242 / 0.239), and displacement is flat too.
  It is a vibration-only event by construction. So
  `tilt_deviation_from_node_baseline` sits at ~0 (noise) regardless of how
  it is computed: anchored recompute median = -0.0005, naive
  episode-only recompute median = 0.0000.

  We still take the anchored value (rolling median seeded from each v2
  node's full external/v2_raw.csv series, baseline rows used as a
  computation reference only, NOT added to training), identical to v5, so
  the pipeline stays uniform. It is asserted equal to the standalone
  external/v2_engineered.csv value. The other three derived features are
  carried from external/v2_engineered.csv, same rationale as v5.

Reads (no modification):
  synthetic/simulated_mesh_data_v5_with_external.csv
  external/v2_engineered.csv
  external/v2_raw.csv                      (full v2 raw, baseline reference only)

Writes:
  synthetic/simulated_mesh_data_v6_with_external.csv   (103,960 rows)
"""
import numpy as np
import pandas as pd
from pathlib import Path

SYN = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\synthetic")
EXT = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\external")

V5_PATH = SYN / "simulated_mesh_data_v5_with_external.csv"
V6_PATH = SYN / "simulated_mesh_data_v6_with_external.csv"

SAMPLES_PER_7D = 7 * 24 * 4
TILT_DEV_MIN_PERIODS = 4
MERGE_SCENARIO = "vibration_disturbance"
MAP_TO = "decoy_seismic"

# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
v5 = pd.read_csv(V5_PATH, parse_dates=["timestamp"], dtype={"merged_label": "string"})
v5["merged_label"] = v5["merged_label"].fillna("").astype(str)
V5_COLS = list(v5.columns)                      # includes merged_label
BASE_COLS = [c for c in V5_COLS if c != "merged_label"]

v2eng = pd.read_csv(EXT / "v2_engineered.csv", parse_dates=["timestamp"])
v2raw = pd.read_csv(EXT / "v2_raw.csv", parse_dates=["timestamp"])

vd = v2eng[v2eng["scenario"] == MERGE_SCENARIO].copy()
assert len(vd) == 104, f"expected 104 vibration_disturbance rows, got {len(vd)}"
assert sorted(vd["node_id"].unique()) == ["NODE_V2_01", "NODE_V2_03", "NODE_V2_04", "NODE_V2_06", "NODE_V2_08"]
assert (vd["node_id"].isin(v5["node_id"].unique())).sum() == 0, "v2 disturbance nodes must be new"

# ---------------------------------------------------------------------------
# Step 2 check: does tilt revert / is there an interaction risk?  (No.)
# ---------------------------------------------------------------------------
print("--- Step 2: tilt_deg before / during / after each vibration_disturbance (from v2_raw) ---")
for nid in sorted(vd["node_id"].unique()):
    na = v2raw[v2raw.node_id == nid].sort_values("timestamp")
    dts = set(vd[vd.node_id == nid].timestamp)
    b = na[na.timestamp < min(dts)]["tilt_deg"].mean()
    d = na[na.timestamp.isin(dts)]["tilt_deg"].mean()
    a = na[na.timestamp > max(dts)]["tilt_deg"].mean()
    print(f"  {nid}: before={b:.3f}  during={d:.3f}  after={a:.3f}  (flat -> no elevated-then-revert risk)")

# ---------------------------------------------------------------------------
# tilt_deviation_from_node_baseline: anchored recompute (== standalone)
# ---------------------------------------------------------------------------
def rolling_dev(frame):
    out = pd.Series(index=frame.index, dtype="float64")
    for _, g in frame.sort_values(["node_id", "timestamp"]).groupby("node_id", sort=False):
        rm = g["tilt_deg"].rolling(window=SAMPLES_PER_7D, min_periods=TILT_DEV_MIN_PERIODS).median()
        out.loc[g.index] = (g["tilt_deg"] - rm).to_numpy()
    return out.fillna(0.0).round(4)

naive_dev = rolling_dev(vd.copy())

v2raw_full = v2raw.sort_values(["node_id", "timestamp"]).reset_index(drop=True)
v2raw_full["_anchored"] = rolling_dev(v2raw_full)
anchored = vd[["node_id", "timestamp"]].merge(
    v2raw_full[["node_id", "timestamp", "_anchored"]], on=["node_id", "timestamp"],
    how="left", validate="1:1")["_anchored"].to_numpy()

standalone = vd[["node_id", "timestamp"]].merge(
    v2eng[["node_id", "timestamp", "tilt_deviation_from_node_baseline"]],
    on=["node_id", "timestamp"], how="left", validate="1:1"
)["tilt_deviation_from_node_baseline"].to_numpy()

assert np.allclose(anchored, standalone, atol=1e-9), "anchored != standalone v2_engineered value"
vd["tilt_deviation_from_node_baseline"] = anchored

print("\n--- tilt_deviation_from_node_baseline for the 104 rows: naive vs anchored ---")
print(f"  naive (episode-only) : median={np.median(naive_dev):.4f}  min={naive_dev.min():.4f}  max={naive_dev.max():.4f}")
print(f"  anchored (used)      : median={np.median(anchored):.4f}  min={anchored.min():.4f}  max={anchored.max():.4f}")
print("  -> both ~0: tilt does not move during a vibration disturbance, so the v5 "
      "interaction risk is immaterial here. Anchored value taken anyway for uniformity.")

# ---------------------------------------------------------------------------
# Assemble in our schema
# ---------------------------------------------------------------------------
vd["merged_label"] = MAP_TO
v6_new = vd.reindex(columns=BASE_COLS + ["merged_label"])
assert v6_new[BASE_COLS].isna().sum().sum() == 0, "missing values in mapped v2 rows"

v6 = pd.concat([v5, v6_new], ignore_index=True)
v6 = v6.sort_values(["timestamp", "node_id"]).reset_index(drop=True)

# ---------------------------------------------------------------------------
# Assert the existing 103,856 rows stay byte-identical
# ---------------------------------------------------------------------------
prev_mask = ~((v6["merged_label"] == MAP_TO) & (v6["node_id"].isin(vd["node_id"].unique())))
# safer: identify carried rows as everything present in v5 by (timestamp,node_id,merged_label)
v5_keys = set(map(tuple, v5[["timestamp", "node_id", "merged_label"]].itertuples(index=False, name=None)))
carried = v6[[tuple(r) in v5_keys for r in v6[["timestamp", "node_id", "merged_label"]].itertuples(index=False, name=None)]]
carried_sorted = carried[V5_COLS].sort_values(["timestamp", "node_id", "merged_label"]).reset_index(drop=True)
v5_sorted = v5[V5_COLS].sort_values(["timestamp", "node_id", "merged_label"]).reset_index(drop=True)
assert len(carried_sorted) == len(v5_sorted) == 103856, f"carried {len(carried_sorted)} vs v5 {len(v5_sorted)}"
assert carried_sorted.equals(v5_sorted), "existing v5 rows changed -- must be additive only"

v6.to_csv(V6_PATH, index=False)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
print(f"\nWrote {V6_PATH}")
print(f"Rows: {len(v6)}  (was {len(v5)}, +{len(v6_new)} vibration_disturbance rows -> {MAP_TO})")
print(f"New rows by node: {v6_new['node_id'].value_counts().to_dict()}")
print("Existing 103,856 rows byte-identical: True")
print("\nmerged_label counts in v6:")
print(v6["merged_label"].value_counts(dropna=False).to_string())
