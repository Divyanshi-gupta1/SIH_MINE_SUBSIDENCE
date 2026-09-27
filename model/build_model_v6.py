"""
v6 model build: same pipeline as build_model.py / build_model_v5.py,
trained on synthetic/simulated_mesh_data_v6_with_external.csv
  = our 103,680 rows
  + 176 v2 escalation rows      -> subsidence_precursor   (added in v5)
  + 104 v2 vibration_disturbance -> decoy_seismic          (added in v6)

vibration_disturbance is now confirmed by Divyanshi to be the same
semantic role as our decoy_seismic (seismic/noise false-alarm testing),
so the earlier pending conflict is resolved and these rows are merged.

Differences from build_model.py:
  - reads the v6 CSV
  - labels our rows from events_log.csv as before, AND labels every
    imported v2 row directly from its `merged_label` column
  - FRESH split, same principled date (2026-10-15). Every v2 row is dated
    August 2026, so all merged rows fall in TRAIN and the TEST set is
    identical to v4's / v5's -> the v5 -> v6 comparison is a clean
    isolation of "what does adding the 104 decoy_seismic rows do".
  - writes v6-suffixed artifacts; v4 (current primary) and v5 files untouched.
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
df = pd.read_csv(SYN_DIR / "simulated_mesh_data_v6_with_external.csv",
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

# imported v2 rows -- labelled directly from merged_label (no events_log entry)
for lbl in ("subsidence_precursor", "decoy_seismic"):
    df.loc[df["merged_label"] == lbl, "event_type"] = lbl
n_merged_prec = int((df["merged_label"] == "subsidence_precursor").sum())
n_merged_decoy = int((df["merged_label"] == "decoy_seismic").sum())

n_excluded = int(df["_exclude_tail"].sum())
df_model = df[~df["_exclude_tail"]].copy()
df_model = df_model.sort_values(["timestamp", "node_id"]).reset_index(drop=True)

train_mask = df_model["timestamp"] < SPLIT_TIMESTAMP
test_mask = ~train_mask

X_train, y_train = df_model.loc[train_mask, FEATURES], df_model.loc[train_mask, TARGET]
X_test, y_test = df_model.loc[test_mask, FEATURES], df_model.loc[test_mask, TARGET]

merged_in_test = int((df_model.loc[test_mask, "merged_label"] != "").sum())

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

joblib.dump(log_reg, MODEL_DIR / "logistic_regression_model_v6.joblib")
joblib.dump(rf, MODEL_DIR / "random_forest_model_v6.joblib")

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
    ax.set_title(f"Confusion matrix (test set) \u2014 {name} (v6)")
    plt.tight_layout()
    plt.savefig(MODEL_DIR / f"confusion_matrix_{name.lower().replace(' ', '_')}_v6.png", dpi=150)
    plt.close(fig)
    return report, cm.tolist()

report_lr, cm_lr = evaluate(log_reg, "Logistic Regression")
report_rf, cm_rf = evaluate(rf, "Random Forest")

importances = pd.Series(rf.feature_importances_, index=FEATURES).sort_values(ascending=False)
fig, ax = plt.subplots(figsize=(8, 4.5))
importances.plot(kind="barh", ax=ax, color="#1E5F8C")
ax.invert_yaxis()
ax.set_xlabel("Random Forest feature importance")
ax.set_title("Feature importances \u2014 Random Forest (v6)")
plt.tight_layout()
plt.savefig(MODEL_DIR / "feature_importances_v6.png", dpi=150)
plt.close(fig)

metrics = {
    "dataset": "synthetic/simulated_mesh_data_v6_with_external.csv",
    "split_timestamp": str(SPLIT_TIMESTAMP),
    "split_note": "fresh split re-tallied on v6 row composition; date unchanged; "
                  "all merged v2 rows (176 escalation + 104 vibration_disturbance) "
                  "fall in TRAIN (dated Aug 2026), test set == v4/v5 test set",
    "train_rows": int(train_mask.sum()),
    "test_rows": int(test_mask.sum()),
    "excluded_tail_rows": n_excluded,
    "merged_v2_escalation_rows": n_merged_prec,
    "merged_v2_vibration_disturbance_rows": n_merged_decoy,
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
with open(MODEL_DIR / "metrics_v6.json", "w") as f:
    json.dump(metrics, f, indent=2, default=str)

# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------
print(f"Dataset: simulated_mesh_data_v6_with_external.csv  ({len(df)} rows)")
print(f"Merged v2 rows -> subsidence_precursor: {n_merged_prec}  |  -> decoy_seismic: {n_merged_decoy}")
print(f"Merged rows in test: {merged_in_test}  (0 expected -- all dated Aug)")
print(f"Train rows: {int(train_mask.sum())}   Test rows: {int(test_mask.sum())}")
print(f"Train class counts: {y_train.value_counts().to_dict()}")
print(f"Test  class counts: {y_test.value_counts().to_dict()}")
for name, report, cm in [("Logistic Regression", report_lr, cm_lr), ("Random Forest", report_rf, cm_rf)]:
    print(f"\n=== {name} \u2014 v6 test set ===")
    for cls in CLASS_ORDER:
        r = report[cls]
        print(f"  {cls:22s} P={r['precision']:.4f} R={r['recall']:.4f} F1={r['f1-score']:.4f} n={int(r['support'])}")
    print(f"  {'accuracy':22s} {report['accuracy']:.5f}")
    print(f"  confusion matrix [{CLASS_ORDER}]: {cm}")
print("\nRF feature importances (v6):")
print(importances.round(4).to_string())
print(f"\nSaved: {MODEL_DIR / 'random_forest_model_v6.joblib'}")
print(f"Saved: {MODEL_DIR / 'logistic_regression_model_v6.joblib'}")
print(f"Saved: {MODEL_DIR / 'metrics_v6.json'}")
