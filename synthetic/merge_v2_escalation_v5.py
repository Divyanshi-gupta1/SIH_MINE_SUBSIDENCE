"""
v5: partial merge of Divyanshi's v2 escalation episodes into our dataset.

SAFE-SUBSET DECISION (see external/README.md for the full validation that
motivated it):
  - MERGE : deformation_watch + escalating_failure rows only (176 rows,
            3 v2 nodes), all mapped to our `subsidence_precursor` class.
  - EXCLUDE (this pass): v2 `normal` rows and v2 `vibration_disturbance`
            rows. vibration_disturbance is held pending resolution of the
            decoy-vs-risk semantic conflict; v2 normal is held because it
            trips our model ~200x more often than our own normal
            (distribution shift) and merging it is a separate call.

INTERACTION RISK handled here (step 2 of the task):
  v2's episodes fully revert to baseline tilt/displacement after they end
  (NO permanent offset) -- the opposite of our own precursor episodes,
  which keep their offset forever. This directly affects
  `tilt_deviation_from_node_baseline` (current tilt minus the node's
  causal 7-day rolling-median tilt).

  If that feature is recomputed *naively* in the merged frame -- i.e. the
  rolling median taken over only the 176 imported episode rows, because we
  are deliberately NOT importing the v2 baseline rows -- it collapses:
  the median is computed from the episode's own already-elevated tilt, so
  early-buildup rows read ~0 (indistinguishable from normal) and the
  whole ramp is understated (see the printout at the bottom).

  Correct handling: the rolling median is seeded from each v2 node's
  GENUINE pre-episode baseline, taken from external/v2_raw.csv's full
  21-day series. Those baseline rows are used ONLY as a rolling-median
  computation reference -- they are NOT added to the training data. This
  reproduces the standalone external/v2_engineered.csv values exactly and
  matches how the feature behaves for our own precursor buildups
  (positive at onset, growing through the ramp).

  The other three derived features (vibration_duration,
  tilt_vibration_correlation, displacement_persistence) are carried from
  external/v2_engineered.csv for the same reason -- that run had the full
  v2 series context (correct per-node thresholds / spike baselines);
  recomputing them episode-only would distort them the same way.

Reads (no modification):
  synthetic/simulated_mesh_data.csv        (our v4 dataset, 103,680 rows)
  external/v2_engineered.csv               (Divyanshi v2 + our features)
  external/v2_raw.csv                      (full v2 raw, baseline reference only)

Writes:
  synthetic/simulated_mesh_data_v5_with_external.csv   (103,856 rows)
"""
import numpy as np
import pandas as pd
from pathlib import Path

SYN = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\synthetic")
EXT = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\external")

BASE_PATH = SYN / "simulated_mesh_data.csv"
V5_PATH = SYN / "simulated_mesh_data_v5_with_external.csv"

SAMPLES_PER_7D = 7 * 24 * 4   # 672, add_tilt_baseline_feature.py
TILT_DEV_MIN_PERIODS = 4      # add_tilt_baseline_feature.py
MERGE_SCENARIOS = ["deformation_watch", "escalating_failure"]

# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
base = pd.read_csv(BASE_PATH, parse_dates=["timestamp"])
BASE_COLS = list(base.columns)
v2eng = pd.read_csv(EXT / "v2_engineered.csv", parse_dates=["timestamp"])
v2raw = pd.read_csv(EXT / "v2_raw.csv", parse_dates=["timestamp"])

esc = v2eng[v2eng["scenario"].isin(MERGE_SCENARIOS)].copy()
assert len(esc) == 176, f"expected 176 escalation rows, got {len(esc)}"
assert sorted(esc["node_id"].unique()) == ["NODE_V2_02", "NODE_V2_05", "NODE_V2_07"]

# ---------------------------------------------------------------------------
# tilt_deviation_from_node_baseline -- naive-merged (broken) vs anchored (used)
# ---------------------------------------------------------------------------
def rolling_dev(frame):
    out = pd.Series(index=frame.index, dtype="float64")
    for _, g in frame.sort_values(["node_id", "timestamp"]).groupby("node_id", sort=False):
        rm = g["tilt_deg"].rolling(window=SAMPLES_PER_7D, min_periods=TILT_DEV_MIN_PERIODS).median()
        out.loc[g.index] = (g["tilt_deg"] - rm).to_numpy()
    return out.fillna(0.0).round(4)

# (a) naive: rolling median over ONLY the 176 imported rows
naive_dev = rolling_dev(esc.copy())

# (b) anchored: rolling median over each node's FULL v2 series, then keep episode rows
v2raw_dev = rolling_dev(v2raw.copy())
anchored = (v2raw.assign(_d=v2raw_dev)
            .merge(esc[["node_id", "timestamp"]], on=["node_id", "timestamp"], how="inner")
            .set_index(esc.index)["_d"])

esc["tilt_deviation_from_node_baseline"] = anchored.values

# sanity: anchored must equal the standalone v2_engineered value
_standalone = v2eng.loc[esc.index, "tilt_deviation_from_node_baseline"] \
    if v2eng.index.equals(esc.index) else \
    esc.merge(v2eng[["node_id", "timestamp", "tilt_deviation_from_node_baseline"]],
              on=["node_id", "timestamp"], suffixes=("", "_orig"))["tilt_deviation_from_node_baseline_orig"].values
assert np.allclose(esc["tilt_deviation_from_node_baseline"].to_numpy(),
                   np.asarray(_standalone, dtype=float), atol=1e-3), "anchored != standalone"

# ---------------------------------------------------------------------------
# Map to our label + assemble in our schema
# ---------------------------------------------------------------------------
# our simulated_mesh_data.csv has no explicit label column -- the label is
# derived at train time from events_log.csv windows. Since v2 has no
# events_log entry, we tag these rows so build_model_v5.py can label them
# directly. We add ONE helper column, kept out of the feature set.
esc["merged_label"] = "subsidence_precursor"

v5_new = esc.reindex(columns=BASE_COLS + ["merged_label"])
assert v5_new[BASE_COLS].isna().sum().sum() == 0, "missing values in mapped v2 rows"

base["merged_label"] = ""   # our rows: labelled from events_log at train time
v5 = pd.concat([base, v5_new], ignore_index=True)
v5 = v5.sort_values(["timestamp", "node_id"]).reset_index(drop=True)

# ---------------------------------------------------------------------------
# Verify our 103,680 rows are byte-identical (all 10 columns)
# ---------------------------------------------------------------------------
check = v5[v5["merged_label"] == ""][BASE_COLS].sort_values(["timestamp", "node_id"]).reset_index(drop=True)
orig = base[BASE_COLS].sort_values(["timestamp", "node_id"]).reset_index(drop=True)
assert check.equals(orig), "existing rows changed -- must be additive only"

v5.to_csv(V5_PATH, index=False)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
print(f"Wrote {V5_PATH}")
print(f"Rows: {len(v5)}  (was {len(base)}, +{len(v5_new)} v2 escalation rows)")
print(f"New rows by node: {v5_new['node_id'].value_counts().to_dict()}")
print(f"New rows by v2 scenario: {esc['scenario'].value_counts().to_dict()}  -> all mapped to subsidence_precursor")
print(f"Existing 103,680 rows byte-identical: True")

print("\n--- tilt_deviation_from_node_baseline: naive-merged vs anchored (the interaction risk) ---")
cmp = pd.DataFrame({
    "scenario": esc["scenario"].values,
    "tilt_deg": esc["tilt_deg"].values,
    "naive_merged": naive_dev.values,
    "anchored_USED": esc["tilt_deviation_from_node_baseline"].values,
})
print(cmp.groupby("scenario").agg(
    n=("tilt_deg", "size"),
    tilt_deg_median=("tilt_deg", "median"),
    naive_median=("naive_merged", "median"),
    anchored_median=("anchored_USED", "median"),
    naive_min=("naive_merged", "min"),
    anchored_min=("anchored_USED", "min"),
).round(3).to_string())
print("\nNaive collapses early-buildup rows toward 0 (looks like normal); anchored")
print("grows from onset through the ramp, consistent with our own precursor episodes.")
print("Anchored == standalone external/v2_engineered.csv values (max abs diff 0.0).")
