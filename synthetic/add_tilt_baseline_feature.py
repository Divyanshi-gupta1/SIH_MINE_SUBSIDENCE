"""
Task 2: add an offset-aware tilt feature to simulated_mesh_data.csv.

WHY (see model/diagnose_offset_node.py for the full diagnosis):
The current feature set feeds `tilt_deg` as a RAW ABSOLUTE value. When a
node has already accumulated a permanent tilt offset from an earlier real
precursor episode (NODE_03: +4.9 deg from EVT_06 + EVT_21), a later decoy
on that node sits on a ~5 deg baseline, and the model reads that stale
elevation as if tilt were actively rising -- the single decoy ->
subsidence_precursor misclassification (EVT_31, NODE_03, 2026-11-05).

THE FEATURE:
`tilt_deviation_from_node_baseline` = tilt_deg minus that node's causal
7-day rolling median of tilt_deg. This is ~0 when a node is simply parked
on an old offset (the median has caught up to the new level) and clearly
positive only while tilt is actively climbing faster than a 7-day median
can track -- i.e. during a real buildup.

CAUSAL: the rolling median at row t uses only rows <= t for that node
(pandas trailing window). No future data. The first hour of each node's
series (< 4 samples) has no window and is filled with 0.0, matching how
`tilt_vibration_correlation`'s warm-up NaNs are already handled.

This script is ADDITIVE ONLY. It appends one column and rewrites the CSV;
it asserts all 9 pre-existing columns are byte-identical afterwards.
"""
import numpy as np
import pandas as pd
from pathlib import Path

DIR = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\synthetic")
DATA_PATH = DIR / "simulated_mesh_data.csv"

SAMPLES_PER_7D = 7 * 24 * 4      # 672 samples at 15-min cadence
MIN_PERIODS = 4                   # 1 hour; earlier rows -> 0.0
NEW_COL = "tilt_deviation_from_node_baseline"

df = pd.read_csv(DATA_PATH, parse_dates=["timestamp"])
existing_cols = list(df.columns)
assert NEW_COL not in existing_cols, f"{NEW_COL} already present -- nothing to do."
backup = df.copy()

# ---------------------------------------------------------------------------
# Causal per-node 7-day rolling-median deviation
# ---------------------------------------------------------------------------
dev = pd.Series(index=df.index, dtype="float64")
for node, g in df.sort_values(["node_id", "timestamp"]).groupby("node_id", sort=False):
    roll_med = g["tilt_deg"].rolling(window=SAMPLES_PER_7D, min_periods=MIN_PERIODS).median()
    dev.loc[g.index] = (g["tilt_deg"] - roll_med).to_numpy()

df[NEW_COL] = dev.fillna(0.0).round(4)

# keep the same row order the file already had
df = df.sort_values(["timestamp", "node_id"]).reset_index(drop=True)
backup = backup.sort_values(["timestamp", "node_id"]).reset_index(drop=True)

# ---------------------------------------------------------------------------
# Verify: every pre-existing column byte-identical
# ---------------------------------------------------------------------------
identical = backup[existing_cols].equals(df[existing_cols])
print(f"All {len(existing_cols)} pre-existing columns byte-identical after adding "
      f"'{NEW_COL}': {identical}")
if not identical:
    raise AssertionError("A pre-existing column changed -- this script must be additive only.")

df.to_csv(DATA_PATH, index=False)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\nColumns now: {list(df.columns)}")
print(f"Rows: {len(df)}")
print(f"\n{NEW_COL} distribution:")
print(df[NEW_COL].describe().to_string())

evt31 = df[(df.node_id == "NODE_03") & (df.timestamp == pd.Timestamp("2026-11-05 11:00:00"))]
if len(evt31):
    r = evt31.iloc[0]
    print(f"\nEVT_31 misclassified row (NODE_03 2026-11-05 11:00): "
          f"tilt_deg={r['tilt_deg']:.3f}  {NEW_COL}={r[NEW_COL]:.3f}")
