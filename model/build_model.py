"""
Part 4: baseline interpretable ML model for subsidence-precursor
early warning, trained on synthetic/simulated_mesh_data.csv.

Reads (does not modify):
  synthetic/simulated_mesh_data.csv
  synthetic/events_log.csv

Writes:
  model/random_forest_model.joblib
  model/logistic_regression_model.joblib
  model/metrics.json
  model/confusion_matrix_random_forest.png
  model/confusion_matrix_logistic_regression.png
  model/feature_importances.png
  model/README.md   (written separately, not by this script)

--------------------------------------------------------------------------
LABEL DEFINITION (ground truth from events_log.csv event_type)
--------------------------------------------------------------------------
Per row (node_id, timestamp), the label is:
  - "subsidence_precursor": row falls in [start_timestamp, subsidence_
    event_timestamp] (buildup THROUGH the peak, inclusive) of a
    subsidence_precursor event. This is deliberately the buildup+peak
    window, not the post-peak tail -- the task is to predict the
    buildup phase BEFORE the labeled peak, not to recognize the
    aftermath.
  - "decoy_seismic": row falls in [start_timestamp, end_timestamp] of a
    decoy_seismic event (decoys have no buildup/tail distinction --
    they're a short spike, so the full window is used).
  - EXCLUDED from train/test: rows in (peak, end_timestamp] of a
    subsidence_precursor event (the post-peak tail). These rows are
    genuinely a different regime (settling after the event) that isn't
    "normal" and isn't the "buildup phase" target -- mislabeling them
    either way would corrupt the target definition, so they're dropped.
  - "normal": everything else.

--------------------------------------------------------------------------
NO-TIME-LEAKAGE: displacement_persistence
--------------------------------------------------------------------------
As of the dataset extension (synthetic/extend_dataset.py), the CSV's
displacement_persistence column IS the causal version: at each row it
only asks "was there a vibration spike start in the last ~2 hours, and is
displacement elevated right now vs. that spike's pre-spike baseline" --
using only the current and past rows, never the future. (Earlier in this
project it briefly held a retrospective/future-peeking version built only
for a verification plot; that version has been fully replaced in the CSV
and is no longer used anywhere, including here.) All three derived
columns -- vibration_duration, tilt_vibration_correlation,
displacement_persistence -- are therefore read directly from the CSV with
no recomputation needed in this script.

--------------------------------------------------------------------------
OFFSET-AWARE TILT FEATURE: tilt_deviation_from_node_baseline
--------------------------------------------------------------------------
Added by synthetic/add_tilt_baseline_feature.py (also read straight from
the CSV). It is tilt_deg minus that node's causal 7-day rolling median of
tilt_deg -- near zero when a node merely carries a stale permanent tilt
offset from an old real episode, clearly positive only during an active
rise. It was added specifically to resolve the NODE_03 case where a decoy
landing on an already-offset node was misread as a fresh precursor. See
model/diagnose_offset_node.py for the diagnosis and model/README.md for
the before/after result.
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
MODEL_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_STATE = 42
# Chosen so both decoy_seismic and subsidence_precursor episodes are well
# represented on both sides of the split, given the full 120-day range now
# spans 2026-08-01 -> 2026-11-28 with 33 total episodes spread across it
# (across 10 nodes -- NODE_09/NODE_10 were added partway through).
SPLIT_TIMESTAMP = pd.Timestamp("2026-10-15 00:00:00")

# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
df = pd.read_csv(SYN_DIR / "simulated_mesh_data.csv", parse_dates=["timestamp"])
events = pd.read_csv(
    SYN_DIR / "events_log.csv",
    parse_dates=["start_timestamp", "subsidence_event_timestamp", "end_timestamp"],
)

# ---------------------------------------------------------------------------
# Row-level ground-truth label
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

n_excluded = int(df["_exclude_tail"].sum())
df_model = df[~df["_exclude_tail"]].copy()

# ---------------------------------------------------------------------------
# Feature set (node_id and timestamp deliberately excluded from features --
# see model/README.md for why: including node_id would let the model
# memorize which physical node historically had an event rather than
# learn from generalizable sensor patterns)
# ---------------------------------------------------------------------------
FEATURES = [
    "tilt_deg", "vibration_rms", "displacement_mm", "crack_signal",
    "vibration_duration", "tilt_vibration_correlation", "displacement_persistence",
    # Offset-aware tilt feature (synthetic/add_tilt_baseline_feature.py): current
    # tilt_deg minus this node's causal 7-day rolling median of tilt_deg. ~0 when a
    # node is parked on a stale permanent offset from an old episode; clearly
    # positive only while tilt is actively climbing. Added to fix the single
    # decoy -> subsidence_precursor misclassification on NODE_03 (a decoy landing
    # on a node that already carried a +4.9 deg permanent offset -- the model was
    # reading raw elevated tilt_deg as an active rise). Causal: no future data.
    "tilt_deviation_from_node_baseline",
]
TARGET = "event_type"

df_model = df_model.sort_values(["timestamp", "node_id"]).reset_index(drop=True)

train_mask = df_model["timestamp"] < SPLIT_TIMESTAMP
test_mask = ~train_mask

X_train, y_train = df_model.loc[train_mask, FEATURES], df_model.loc[train_mask, TARGET]
X_test, y_test = df_model.loc[test_mask, FEATURES], df_model.loc[test_mask, TARGET]

CLASS_ORDER = ["normal", "decoy_seismic", "subsidence_precursor"]

# ---------------------------------------------------------------------------
# Train models
# ---------------------------------------------------------------------------
log_reg = Pipeline([
    ("scaler", StandardScaler()),  # derived features (e.g. vibration_duration) live on a very
                                    # different scale than raw sensor values -- without scaling,
                                    # the linear model's decision boundary is dominated by
                                    # whichever feature happens to have the largest raw magnitude
    ("clf", LogisticRegression(class_weight="balanced", max_iter=2000, random_state=RANDOM_STATE)),
])
log_reg.fit(X_train, y_train)

rf = RandomForestClassifier(
    n_estimators=200, max_depth=6, class_weight="balanced", random_state=RANDOM_STATE
)
rf.fit(X_train, y_train)

joblib.dump(log_reg, MODEL_DIR / "logistic_regression_model.joblib")
joblib.dump(rf, MODEL_DIR / "random_forest_model.joblib")

# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------
def evaluate(model, name):
    y_pred = model.predict(X_test)
    report = classification_report(y_test, y_pred, labels=CLASS_ORDER, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_test, y_pred, labels=CLASS_ORDER)

    fig, ax = plt.subplots(figsize=(6, 5))
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=CLASS_ORDER)
    disp.plot(ax=ax, cmap="Blues", colorbar=False, values_format="d")
    ax.set_title(f"Confusion matrix (test set) \u2014 {name}")
    plt.tight_layout()
    fname = MODEL_DIR / f"confusion_matrix_{name.lower().replace(' ', '_')}.png"
    plt.savefig(fname, dpi=150)
    plt.close(fig)

    return report, cm.tolist()


report_lr, cm_lr = evaluate(log_reg, "Logistic Regression")
report_rf, cm_rf = evaluate(rf, "Random Forest")

# ---------------------------------------------------------------------------
# Feature importances (Random Forest) -- interpretability artifact
# ---------------------------------------------------------------------------
importances = pd.Series(rf.feature_importances_, index=FEATURES).sort_values(ascending=False)
fig, ax = plt.subplots(figsize=(8, 4.5))
importances.plot(kind="barh", ax=ax, color="#1E5F8C")
ax.invert_yaxis()
ax.set_xlabel("Random Forest feature importance")
ax.set_title("Feature importances \u2014 Random Forest baseline")
plt.tight_layout()
plt.savefig(MODEL_DIR / "feature_importances.png", dpi=150)
plt.close(fig)

# ---------------------------------------------------------------------------
# Metrics summary (saved + printed)
# ---------------------------------------------------------------------------
metrics = {
    "split_timestamp": str(SPLIT_TIMESTAMP),
    "train_rows": int(train_mask.sum()),
    "test_rows": int(test_mask.sum()),
    "excluded_tail_rows": n_excluded,
    "train_class_counts": y_train.value_counts().to_dict(),
    "test_class_counts": y_test.value_counts().to_dict(),
    "features": FEATURES,
    "logistic_regression": {
        "classification_report": report_lr,
        "confusion_matrix": cm_lr,
        "class_order": CLASS_ORDER,
    },
    "random_forest": {
        "classification_report": report_rf,
        "confusion_matrix": cm_rf,
        "class_order": CLASS_ORDER,
        "feature_importances": importances.to_dict(),
    },
}
with open(MODEL_DIR / "metrics.json", "w") as f:
    json.dump(metrics, f, indent=2, default=str)

# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------
print(f"Train rows: {train_mask.sum()}  (before {SPLIT_TIMESTAMP})")
print(f"Test rows:  {test_mask.sum()}  (on/after {SPLIT_TIMESTAMP})")
print(f"Excluded post-peak tail rows: {n_excluded}")
print(f"\nTrain class counts: {y_train.value_counts().to_dict()}")
print(f"Test class counts:  {y_test.value_counts().to_dict()}")

for name, report in [("Logistic Regression", report_lr), ("Random Forest", report_rf)]:
    print(f"\n=== {name} \u2014 test set ===")
    for cls in CLASS_ORDER:
        r = report[cls]
        print(f"  {cls:22s} precision={r['precision']:.3f}  recall={r['recall']:.3f}  "
              f"f1={r['f1-score']:.3f}  support={int(r['support'])}")
    print(f"  {'accuracy':22s} {report['accuracy']:.3f}")

print("\n=== decoy_seismic vs subsidence_precursor, Random Forest (the headline check) ===")
print(f"  decoy_seismic:        precision={report_rf['decoy_seismic']['precision']:.3f}  "
      f"recall={report_rf['decoy_seismic']['recall']:.3f}")
print(f"  subsidence_precursor: precision={report_rf['subsidence_precursor']['precision']:.3f}  "
      f"recall={report_rf['subsidence_precursor']['recall']:.3f}")

print("\nRandom Forest feature importances:")
print(importances.to_string())

print(f"\nSaved: {MODEL_DIR / 'random_forest_model.joblib'}")
print(f"Saved: {MODEL_DIR / 'logistic_regression_model.joblib'}")
print(f"Saved: {MODEL_DIR / 'metrics.json'}")
print(f"Saved: {MODEL_DIR / 'confusion_matrix_random_forest.png'}")
print(f"Saved: {MODEL_DIR / 'confusion_matrix_logistic_regression.png'}")
print(f"Saved: {MODEL_DIR / 'feature_importances.png'}")
