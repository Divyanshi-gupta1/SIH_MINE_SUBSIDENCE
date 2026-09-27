"""
Task 2: break down subsidence_precursor recall by buildup sub-phase --
early buildup (first <=2h since the episode's start_timestamp, signal
still close to baseline) vs. later buildup (>2h since start, closer to
peak, signal clearly elevated).

Uses the CURRENTLY SAVED model (model/random_forest_model.joblib) and the
CURRENT synthetic/simulated_mesh_data.csv + events_log.csv, reconstructing
the exact same labeling/split/feature pipeline as build_model.py, so the
result matches the 0.667 overall recall already reported. Run this BEFORE
any dataset extension so it reflects the current model, not a new one.
"""
import joblib
import pandas as pd
from pathlib import Path

SYN_DIR = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\synthetic")
MODEL_DIR = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\model")

SPLIT_TIMESTAMP = pd.Timestamp("2026-10-15 00:00:00")
EARLY_CUTOFF_HOURS = 2.0

FEATURES = [
    "tilt_deg", "vibration_rms", "displacement_mm", "crack_signal",
    "vibration_duration", "tilt_vibration_correlation", "displacement_persistence",
    "tilt_deviation_from_node_baseline",
]

# ---------------------------------------------------------------------------
# Rebuild the exact same labeled dataset build_model.py used
# ---------------------------------------------------------------------------
df = pd.read_csv(SYN_DIR / "simulated_mesh_data.csv", parse_dates=["timestamp"])
events = pd.read_csv(
    SYN_DIR / "events_log.csv",
    parse_dates=["start_timestamp", "subsidence_event_timestamp", "end_timestamp"],
)

df["event_type"] = "normal"
df["_exclude_tail"] = False
df["_event_id"] = ""
df["_buildup_start"] = pd.NaT

for _, ev in events.iterrows():
    node = ev["node_id"]
    start, peak, end = ev["start_timestamp"], ev["subsidence_event_timestamp"], ev["end_timestamp"]
    if ev["event_type"] == "subsidence_precursor":
        buildup_mask = (df.node_id == node) & (df.timestamp >= start) & (df.timestamp <= peak)
        tail_mask = (df.node_id == node) & (df.timestamp > peak) & (df.timestamp <= end)
        df.loc[buildup_mask, "event_type"] = "subsidence_precursor"
        df.loc[buildup_mask, "_event_id"] = ev["event_id"]
        df.loc[buildup_mask, "_buildup_start"] = start
        df.loc[tail_mask, "_exclude_tail"] = True
    elif ev["event_type"] == "decoy_seismic":
        spike_mask = (df.node_id == node) & (df.timestamp >= start) & (df.timestamp <= end)
        df.loc[spike_mask, "event_type"] = "decoy_seismic"

df_model = df[~df["_exclude_tail"]].copy()
df_model = df_model.sort_values(["timestamp", "node_id"]).reset_index(drop=True)

test_mask = df_model["timestamp"] >= SPLIT_TIMESTAMP
df_test = df_model[test_mask].copy()

X_test = df_test[FEATURES]
y_test = df_test["event_type"]

# ---------------------------------------------------------------------------
# Predict with the currently-saved Random Forest
# ---------------------------------------------------------------------------
rf = joblib.load(MODEL_DIR / "random_forest_model.joblib")
y_pred = rf.predict(X_test)
df_test["_pred"] = y_pred

true_precursor = df_test[df_test["event_type"] == "subsidence_precursor"].copy()
true_precursor["elapsed_hours_since_buildup_start"] = (
    (true_precursor["timestamp"] - true_precursor["_buildup_start"]).dt.total_seconds() / 3600.0
)
true_precursor["correct"] = true_precursor["_pred"] == "subsidence_precursor"
true_precursor["phase"] = true_precursor["elapsed_hours_since_buildup_start"].apply(
    lambda h: "early (<=2h since start)" if h <= EARLY_CUTOFF_HOURS else "late (>2h since start)"
)

overall_recall = true_precursor["correct"].mean()
print(f"Overall subsidence_precursor recall on test set: {overall_recall:.3f} "
      f"({true_precursor['correct'].sum()}/{len(true_precursor)})")

print("\nBy buildup sub-phase:")
summary = true_precursor.groupby("phase").agg(
    rows=("correct", "size"), correct=("correct", "sum"), recall=("correct", "mean")
)
print(summary.to_string())

print("\nPer-episode breakdown (test set only):")
per_ep = true_precursor.groupby("_event_id").agg(
    rows=("correct", "size"), correct=("correct", "sum"), recall=("correct", "mean"),
    min_elapsed_h=("elapsed_hours_since_buildup_start", "min"),
    max_elapsed_h=("elapsed_hours_since_buildup_start", "max"),
)
print(per_ep.to_string())

print("\nRow-level detail (timestamp, event, elapsed hours since buildup start, predicted, correct):")
detail = true_precursor[["_event_id", "timestamp", "elapsed_hours_since_buildup_start", "_pred", "correct"]].sort_values(
    ["_event_id", "timestamp"])
print(detail.to_string(index=False))
