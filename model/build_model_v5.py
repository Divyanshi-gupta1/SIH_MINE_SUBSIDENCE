"""
v5 model build: same pipeline as build_model.py, trained on the
partial-merge dataset synthetic/simulated_mesh_data_v5_with_external.csv
(our 103,680 rows + 176 v2 escalation rows mapped to subsidence_precursor).

Differences from build_model.py:
  - reads the v5 CSV
  - labels our rows from events_log.csv exactly as before, AND labels the
    176 imported v2 rows directly from their `merged_label` column (v2 has
    no events_log entry)
  - FRESH split: chronological split is re-tallied on the new row
    composition. The split DATE is unchanged (2026-10-15) because it is
    still principled (no future leakage, both anomaly classes present on
    both sides). All 176 v2 rows are dated August 2026 -> they all fall in
    the TRAIN partition, so the TEST set is identical to v4's. That is
    deliberate: it makes the v4 -> v5 comparison a clean isolation of
    "what does adding v2's escalation episodes to training do to our model
    on our own held-out data".
  - writes v5-suffixed artifacts; does NOT overwrite the v4 model files
    (v4 stays the current primary pending the team decision).
"""
import json
import pandas as pd
import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix, ConfusionMatrixDisplay

SYN_DIR = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\synthetic")
MODEL_DIR = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\model")

RANDOM_STATE = 42
SPLIT_TIMESTAMP = pd.Timestamp("2026-10-15 00:00:00")

FEATURES = [
    "tilt_deg", "vibration_rms", "displacement_mm", "crack_signal",
    "vibration_duration", "tilt_vibration_correlation", "displacement_persistence",
    "tilt_deviation_from_node_baseline",
]
TARGET = "event_type"
CLASS_ORDER = ["normal", "decoy_seismic", "subsidence_precursor"]

# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
df = pd.read_csv(SYN_DIR / "simulated_mesh_data_v5_with_external.csv",
                parse_dates=["timestamp"], dtype={"merged_label": "string"})
df["merged_label"] = df["merged_label"].fillna("").astype(str)
events = pd.read_csv(
    SYN_DIR / "events_log.csv",
    parse_dates=["start_timestamp", "subsidence_event_timestamp", "end_timestamp"],
)

# ---------------------------------------------------------------------------
# Row-level ground truth
# ---------------------------------------------------------------------------
df["event_type"] = "normal"
df["_exclude_tail"] = False

for _, ev in events.iterrows():
    node = ev["node_id"]
    start, peak, end = ev["start_timestamp"], ev["subsidence_event_timestamp"], ev["end_timestamp"]
    if ev["event_type"] == "subsidence_precursor":
        buildup_mask = (df.node_id == node) & (df.timestamp >= start) & (df.timestamp <= peak)
        tail_mask = (df.node_id == node) & (df.timestamp > peak) & (df.timestamp <= end)
        df.loc[buildup_mask, "event_type"] = "subsidence_precursor"
        df.loc[tail_mask, "_exclude_tail"] = True
    elif ev["event_type"] == "decoy_seismic":
        spike_mask = (df.node_id == node) & (df.timestamp >= start) & (df.timestamp <= end)
        df.loc[spike_mask, "event_type"] = "decoy_seismic"

# imported v2 escalation rows -- labelled directly (no events_log entry)
n_merged = int((df["merged_label"] == "subsidence_precursor").sum())
df.loc[df["merged_label"] == "subsidence_precursor", "event_type"] = "subsidence_precursor"

n_excluded = int(df["_exclude_tail"].sum())
df_model = df[~df["_exclude_tail"]].copy()
df_model = df_model.sort_values(["timestamp", "node_id"]).reset_index(drop=True)

train_mask = df_model["timestamp"] < SPLIT_TIMESTAMP
test_mask = ~train_mask

X_train, y_train = df_model.loc[train_mask, FEATURES], df_model.loc[train_mask, TARGET]
X_test, y_test = df_model.loc[test_mask, FEATURES], df_model.loc[test_mask, TARGET]

merged_in_train = int((df_model.loc[train_mask, "merged_label"] == "subsidence_precursor").sum())
merged_in_test = int((df_model.loc[test_mask, "merged_label"] == "subsidence_precursor").sum())

# ---------------------------------------------------------------------------
# Train
# ---------------------------------------------------------------------------
log_reg = Pipeline([
    ("scaler", StandardScaler()),
    ("clf", LogisticRegression(class_weight="balanced", max_iter=2000, random_state=RANDOM_STATE)),
])
log_reg.fit(X_train, y_train)

rf = RandomForestClassifier(
    n_estimators=200, max_depth=6, class_weight="balanced", random_state=RANDOM_STATE
)
rf.fit(X_train, y_train)

joblib.dump(log_reg, MODEL_DIR / "logistic_regression_model_v5.joblib")
joblib.dump(rf, MODEL_DIR / "random_forest_model_v5.joblib")

# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------
def evaluate(model, name):
    y_pred = model.predict(X_test)
    report = classification_report(y_test, y_pred, labels=CLASS_ORDER, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_test, y_pred, labels=CLASS_ORDER)
    fig, ax = plt.subplots(figsize=(6, 5))
    ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=CLASS_ORDER).plot(
        ax=ax, cmap="Blues", colorbar=False, values_format="d")
    ax.set_title(f"Confusion matrix (test set) \u2014 {name} (v5)")
    plt.tight_layout()
    plt.savefig(MODEL_DIR / f"confusion_matrix_{name.lower().replace(' ', '_')}_v5.png", dpi=150)
    plt.close(fig)
    return report, cm.tolist()

report_lr, cm_lr = evaluate(log_reg, "Logistic Regression")
report_rf, cm_rf = evaluate(rf, "Random Forest")

importances = pd.Series(rf.feature_importances_, index=FEATURES).sort_values(ascending=False)
fig, ax = plt.subplots(figsize=(8, 4.5))
importances.plot(kind="barh", ax=ax, color="#1E5F8C")
ax.invert_yaxis()
ax.set_xlabel("Random Forest feature importance")
ax.set_title("Feature importances \u2014 Random Forest (v5)")
plt.tight_layout()
plt.savefig(MODEL_DIR / "feature_importances_v5.png", dpi=150)
plt.close(fig)

metrics = {
    "dataset": "synthetic/simulated_mesh_data_v5_with_external.csv",
    "split_timestamp": str(SPLIT_TIMESTAMP),
    "split_note": "fresh split re-tallied on v5 row composition; date unchanged; "
                  "all 176 merged v2 rows fall in TRAIN (dated Aug 2026), test set == v4 test set",
    "train_rows": int(train_mask.sum()),
    "test_rows": int(test_mask.sum()),
    "excluded_tail_rows": n_excluded,
    "merged_v2_escalation_rows_total": n_merged,
    "merged_v2_rows_in_train": merged_in_train,
    "merged_v2_rows_in_test": merged_in_test,
    "train_class_counts": y_train.value_counts().to_dict(),
    "test_class_counts": y_test.value_counts().to_dict(),
    "features": FEATURES,
    "logistic_regression": {
        "classification_report": report_lr, "confusion_matrix": cm_lr, "class_order": CLASS_ORDER,
    },
    "random_forest": {
        "classification_report": report_rf, "confusion_matrix": cm_rf, "class_order": CLASS_ORDER,
        "feature_importances": importances.to_dict(),
    },
}
with open(MODEL_DIR / "metrics_v5.json", "w") as f:
    json.dump(metrics, f, indent=2, default=str)

# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------
print(f"Dataset: simulated_mesh_data_v5_with_external.csv  ({len(df)} rows)")
print(f"Merged v2 escalation rows: {n_merged}  (train: {merged_in_train}, test: {merged_in_test})")
print(f"Train rows: {int(train_mask.sum())}   Test rows: {int(test_mask.sum())}")
print(f"Train class counts: {y_train.value_counts().to_dict()}")
print(f"Test  class counts: {y_test.value_counts().to_dict()}")
for name, report, cm in [("Logistic Regression", report_lr, cm_lr), ("Random Forest", report_rf, cm_rf)]:
    print(f"\n=== {name} \u2014 v5 test set ===")
    for cls in CLASS_ORDER:
        r = report[cls]
        print(f"  {cls:22s} P={r['precision']:.4f} R={r['recall']:.4f} F1={r['f1-score']:.4f} n={int(r['support'])}")
    print(f"  {'accuracy':22s} {report['accuracy']:.5f}")
    print(f"  confusion matrix [{CLASS_ORDER}]: {cm}")
print("\nRF feature importances (v5):")
print(importances.round(4).to_string())
print(f"\nSaved: {MODEL_DIR / 'random_forest_model_v5.joblib'}")
print(f"Saved: {MODEL_DIR / 'logistic_regression_model_v5.joblib'}")
print(f"Saved: {MODEL_DIR / 'metrics_v5.json'}")
