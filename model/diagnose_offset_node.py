"""
Task 1: diagnose the offset-node misclassification.

Finding under investigation: the current Random Forest misclassifies 1 of
20 test decoy rows as `subsidence_precursor`. That row is EVT_31
(NODE_03, decoy_seismic, 2026-11-05 11:00:00). NODE_03 already carries a
permanent tilt/displacement offset from two earlier real precursor
episodes on that same node (EVT_06 on 2026-08-25, EVT_21 on
2026-10-12/13).

This script does NOT retrain anything. It:
  1. Rebuilds the exact labeling / split / feature pipeline from
     build_model.py.
  2. Loads the currently-saved RF and LR and finds every test decoy row
     predicted `subsidence_precursor`.
  3. For each such row, prints its full feature vector next to the
     per-class medians (normal / decoy / precursor buildup) so we can see
     which features push it toward `subsidence_precursor`.
  4. Prints NODE_03's tilt_deg trajectory (episode by episode) to show
     the permanent +4.9 deg offset explicitly.
  5. Checks whether ANY current feature encodes "tilt relative to this
     node's own recent baseline" (the hypothesis is: none does --
     tilt_deg is fed as a raw absolute value).
  6. Previews what a causal 7-day rolling-median tilt-deviation feature
     WOULD read at the misclassified row vs. during real buildups.
"""
import joblib
import numpy as np
import pandas as pd
from pathlib import Path

SYN_DIR = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\synthetic")
MODEL_DIR = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\model")

SPLIT_TIMESTAMP = pd.Timestamp("2026-10-15 00:00:00")
# Original 7-feature set. After synthetic/add_tilt_baseline_feature.py and a
# retrain this becomes stale; re-run against the pre-fix models, or append
# "tilt_deviation_from_node_baseline" to check the fix held.
FEATURES = [
    "tilt_deg", "vibration_rms", "displacement_mm", "crack_signal",
    "vibration_duration", "tilt_vibration_correlation", "displacement_persistence",
]
try:
    import joblib as _jl
    _n = _jl.load(MODEL_DIR / "random_forest_model.joblib").n_features_in_
    if _n == 8 and "tilt_deviation_from_node_baseline" not in FEATURES:
        FEATURES.append("tilt_deviation_from_node_baseline")
except Exception:
    pass

# ---------------------------------------------------------------------------
# Rebuild the labeled dataset exactly as build_model.py does
# ---------------------------------------------------------------------------
df = pd.read_csv(SYN_DIR / "simulated_mesh_data.csv", parse_dates=["timestamp"])
events = pd.read_csv(
    SYN_DIR / "events_log.csv",
    parse_dates=["start_timestamp", "subsidence_event_timestamp", "end_timestamp"],
)

df["event_type"] = "normal"
df["_exclude_tail"] = False
for _, ev in events.iterrows():
    node = ev["node_id"]
    start, peak, end = ev["start_timestamp"], ev["subsidence_event_timestamp"], ev["end_timestamp"]
    if ev["event_type"] == "subsidence_precursor":
        buildup = (df.node_id == node) & (df.timestamp >= start) & (df.timestamp <= peak)
        tail = (df.node_id == node) & (df.timestamp > peak) & (df.timestamp <= end)
        df.loc[buildup, "event_type"] = "subsidence_precursor"
        df.loc[tail, "_exclude_tail"] = True
    elif ev["event_type"] == "decoy_seismic":
        spike = (df.node_id == node) & (df.timestamp >= start) & (df.timestamp <= end)
        df.loc[spike, "event_type"] = "decoy_seismic"

df_model = df[~df["_exclude_tail"]].copy().sort_values(["timestamp", "node_id"]).reset_index(drop=True)
test = df_model[df_model["timestamp"] >= SPLIT_TIMESTAMP].copy()

rf = joblib.load(MODEL_DIR / "random_forest_model.joblib")
lr = joblib.load(MODEL_DIR / "logistic_regression_model.joblib")
test["_pred_rf"] = rf.predict(test[FEATURES])
test["_pred_lr"] = lr.predict(test[FEATURES])

# ---------------------------------------------------------------------------
# 1. Every test decoy row misclassified as subsidence_precursor
# ---------------------------------------------------------------------------
print("=" * 78)
print("1. TEST DECOY ROWS PREDICTED subsidence_precursor")
print("=" * 78)
decoy_test = test[test["event_type"] == "decoy_seismic"]
print(f"Total test decoy rows: {len(decoy_test)}")
for mdl, col in [("Random Forest", "_pred_rf"), ("Logistic Regression", "_pred_lr")]:
    bad = decoy_test[decoy_test[col] == "subsidence_precursor"]
    print(f"  {mdl:22s}: {len(bad)} misclassified as subsidence_precursor")
    for _, r in bad.iterrows():
        print(f"      {r['node_id']}  {r['timestamp']}")

# ---------------------------------------------------------------------------
# 2. Per-class feature medians vs. the misclassified row(s)
# ---------------------------------------------------------------------------
print("\n" + "=" * 78)
print("2. FEATURE VECTOR OF MISCLASSIFIED ROW vs. PER-CLASS MEDIANS")
print("=" * 78)
med_normal = df_model[df_model.event_type == "normal"][FEATURES].median()
med_decoy = df_model[df_model.event_type == "decoy_seismic"][FEATURES].median()
med_prec = df_model[df_model.event_type == "subsidence_precursor"][FEATURES].median()

bad_rf = decoy_test[decoy_test["_pred_rf"] == "subsidence_precursor"]
for _, r in bad_rf.iterrows():
    print(f"\nRow: {r['node_id']} {r['timestamp']}  (true=decoy_seismic, RF pred=subsidence_precursor)")
    table = pd.DataFrame({
        "row_value": r[FEATURES].astype(float),
        "median_normal": med_normal,
        "median_decoy": med_decoy,
        "median_precursor": med_prec,
    })
    print(table.to_string(float_format=lambda x: f"{x:9.4f}"))

# ---------------------------------------------------------------------------
# 3. NODE_03 tilt_deg trajectory: the permanent offset
# ---------------------------------------------------------------------------
print("\n" + "=" * 78)
print("3. NODE_03 tilt_deg TRAJECTORY (permanent offset from EVT_06, EVT_21)")
print("=" * 78)
n3 = df[df.node_id == "NODE_03"].sort_values("timestamp")
windows = {
    "pre-everything (Aug 1-24)": ("2026-08-01", "2026-08-24"),
    "after EVT_06 (Aug 26 - Oct 11)": ("2026-08-26", "2026-10-11"),
    "after EVT_21 (Oct 14 - Nov 4)": ("2026-10-14", "2026-11-04"),
    "week before EVT_31 decoy (Oct 29 - Nov 5 10:30)": ("2026-10-29", "2026-11-05 10:30"),
    "after EVT_31 (Nov 6 - Nov 28)": ("2026-11-06", "2026-11-28"),
}
for label, (a, b) in windows.items():
    seg = n3[(n3.timestamp >= pd.Timestamp(a)) & (n3.timestamp <= pd.Timestamp(b))]
    seg = seg[seg.event_type == "normal"]  # baseline rows only
    if len(seg):
        print(f"  {label:48s}  median tilt_deg = {seg.tilt_deg.median():6.3f}  "
              f"(n={len(seg)}, min={seg.tilt_deg.min():.3f}, max={seg.tilt_deg.max():.3f})")

evt31_row = n3[n3.timestamp == pd.Timestamp("2026-11-05 11:00:00")]
if len(evt31_row):
    print(f"\n  EVT_31 misclassified sample tilt_deg = {evt31_row.iloc[0].tilt_deg:.3f}")
print(f"  events_log added_tilt: EVT_06 = {events[events.event_id=='EVT_06'].added_tilt_deg.iloc[0]}, "
      f"EVT_21 = {events[events.event_id=='EVT_21'].added_tilt_deg.iloc[0]}  "
      f"(sum = {events[events.event_id.isin(['EVT_06','EVT_21'])].added_tilt_deg.sum()})")

# ---------------------------------------------------------------------------
# 4. Does any current feature encode tilt-relative-to-node-baseline?
# ---------------------------------------------------------------------------
print("\n" + "=" * 78)
print("4. DO ANY CURRENT FEATURES ENCODE 'tilt vs. this node's recent baseline'?")
print("=" * 78)
notes = {
    "tilt_deg": "RAW ABSOLUTE value. No per-node baseline subtraction. "
                "A stale permanent offset looks identical to a fresh rise.",
    "vibration_rms": "raw absolute (vibration, not tilt).",
    "displacement_mm": "raw absolute CUMULATIVE. Also carries NODE_03's permanent offset.",
    "crack_signal": "0/1 sensor, node-agnostic.",
    "vibration_duration": "per-node robust threshold, but on VIBRATION only; "
                          "tilt offset is invisible to it.",
    "tilt_vibration_correlation": "rolling corr -- offset-invariant, so it does NOT "
                                  "flag a stale tilt offset; but it also can't tell "
                                  "the model the offset is stale.",
    "displacement_persistence": "causal, measured vs. PRE-SPIKE baseline -> correctly "
                                "reads 0 for this decoy. This is the one offset-aware "
                                "feature, and it's for displacement, not tilt.",
    "tilt_deviation_from_node_baseline": "THE FIX (added after this diagnosis): tilt_deg "
                                "minus node's causal 7-day rolling median -> ~0 on a "
                                "stale offset, positive only on an active rise.",
}
for f in FEATURES:
    print(f"  - {f:34s}: {notes[f]}")
print("\n  CONCLUSION: no feature tells the model 'NODE_03's tilt is elevated only")
print("  because of an OLD event, not an active rise'. tilt_deg is raw. This matches")
print("  the Task 1 hypothesis.")

# ---------------------------------------------------------------------------
# 5. Preview: causal 7-day rolling-median tilt deviation
# ---------------------------------------------------------------------------
print("\n" + "=" * 78)
print("5. PREVIEW: tilt_deviation_from_node_baseline (tilt_deg - causal 7d rolling median)")
print("=" * 78)
SAMPLES_7D = 7 * 24 * 4  # 672 samples at 15-min cadence
dev = pd.Series(index=df.index, dtype="float64")
for node, g in df.sort_values(["node_id", "timestamp"]).groupby("node_id", sort=False):
    roll_med = g["tilt_deg"].rolling(window=SAMPLES_7D, min_periods=4).median()
    dev.loc[g.index] = (g["tilt_deg"] - roll_med).to_numpy()
df["_tilt_dev_preview"] = dev

evt31_idx = df[(df.node_id == "NODE_03") & (df.timestamp == pd.Timestamp("2026-11-05 11:00:00"))].index
if len(evt31_idx):
    print(f"  At EVT_31 misclassified row: tilt_deg={df.loc[evt31_idx[0],'tilt_deg']:.3f}  "
          f"tilt_deviation_from_node_baseline={df.loc[evt31_idx[0],'_tilt_dev_preview']:.3f}")

# during real buildups (label == subsidence_precursor), how big does the deviation get?
prec_rows = df[df.event_type == "subsidence_precursor"]
print(f"  During real precursor buildups: tilt_deviation median={prec_rows['_tilt_dev_preview'].median():.3f}, "
      f"90th pct={prec_rows['_tilt_dev_preview'].quantile(0.9):.3f}, max={prec_rows['_tilt_dev_preview'].max():.3f}")
decoy_rows_all = df[df.event_type == "decoy_seismic"]
print(f"  During ALL decoy spikes:        tilt_deviation median={decoy_rows_all['_tilt_dev_preview'].median():.3f}, "
      f"90th pct={decoy_rows_all['_tilt_dev_preview'].quantile(0.9):.3f}, max={decoy_rows_all['_tilt_dev_preview'].max():.3f}")
norm_rows = df[df.event_type == "normal"]
print(f"  During normal rows:             tilt_deviation median={norm_rows['_tilt_dev_preview'].median():.3f}, "
      f"90th pct={norm_rows['_tilt_dev_preview'].quantile(0.9):.3f}, max={norm_rows['_tilt_dev_preview'].max():.3f}")
print("\n  If the decoy row's deviation is ~0 while real buildups run clearly positive,")
print("  the feature gives the model a way to separate 'stale offset' from 'active rise'.")
