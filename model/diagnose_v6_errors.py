"""
Final quality pass: deep-dive every remaining RF v6 error on OUR OWN test
set (the 43,158 rows from synthetic/simulated_mesh_data_v6_with_external.csv
dated >= 2026-10-15; all merged v2 rows are in TRAIN, so the test set is
our own data only, identical to v4/v5).

NO retraining, NO dataset change. Diagnosis only.

RF v6 test confusion matrix (rows = true, cols = pred [normal, decoy_seismic, subsidence_precursor]):
    normal               [43014,  3,  0]
    decoy_seismic        [    1, 19,  0]
    subsidence_precursor [   52,  0, 69]

So there are exactly four error buckets to explain:
  (A) decoy_seismic -> normal        : 1 row   (decoy recall 0.95)
  (B) subsidence_precursor -> normal : 52 rows (precursor recall 0.57)  <-- weakest class
  (C) normal -> decoy_seismic        : 3 rows  (decoy precision 0.864)
  (D) normal -> subsidence_precursor : 0 rows  (precursor precision 1.000)  -- nothing to explain
  decoy_seismic <-> subsidence_precursor : 0 in both directions

For each bucket: which rows/nodes/times, the full feature vector next to
per-class medians, and whether it looks like a fixable pattern (an
offset-bug-style systematic error) or an irreducible near-baseline edge
case.
"""
import joblib
import numpy as np
import pandas as pd
from pathlib import Path

SYN_DIR = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\synthetic")
MODEL_DIR = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\model")

DATA = SYN_DIR / "simulated_mesh_data_v6_with_external.csv"
RF_PATH = MODEL_DIR / "random_forest_model_v6.joblib"

SPLIT_TIMESTAMP = pd.Timestamp("2026-10-15 00:00:00")
EARLY_CUTOFF_HOURS = 2.0

FEATURES = [
    "tilt_deg", "vibration_rms", "displacement_mm", "crack_signal",
    "vibration_duration", "tilt_vibration_correlation", "displacement_persistence",
    "tilt_deviation_from_node_baseline",
]
CLASS_ORDER = ["normal", "decoy_seismic", "subsidence_precursor"]
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)


# ---------------------------------------------------------------------------
# Rebuild the exact v6 labeled dataset + split (mirrors build_model_v6.py),
# additionally tracking _event_id / _buildup_start / _peak for phase work.
# ---------------------------------------------------------------------------
df = pd.read_csv(DATA, parse_dates=["timestamp"], dtype={"merged_label": "string"})
df["merged_label"] = df["merged_label"].fillna("").astype(str)
events = pd.read_csv(
    SYN_DIR / "events_log.csv",
    parse_dates=["start_timestamp", "subsidence_event_timestamp", "end_timestamp"],
)

df["event_type"] = "normal"
df["_exclude_tail"] = False
df["_event_id"] = ""
df["_buildup_start"] = pd.NaT
df["_peak"] = pd.NaT

for _, ev in events.iterrows():
    node = ev["node_id"]
    start, peak, end = ev["start_timestamp"], ev["subsidence_event_timestamp"], ev["end_timestamp"]
    if ev["event_type"] == "subsidence_precursor":
        buildup = (df.node_id == node) & (df.timestamp >= start) & (df.timestamp <= peak)
        tail = (df.node_id == node) & (df.timestamp > peak) & (df.timestamp <= end)
        df.loc[buildup, "event_type"] = "subsidence_precursor"
        df.loc[buildup, "_event_id"] = ev["event_id"]
        df.loc[buildup, "_buildup_start"] = start
        df.loc[buildup, "_peak"] = peak
        df.loc[tail, "_exclude_tail"] = True
    elif ev["event_type"] == "decoy_seismic":
        spike = (df.node_id == node) & (df.timestamp >= start) & (df.timestamp <= end)
        df.loc[spike, "event_type"] = "decoy_seismic"
        df.loc[spike, "_event_id"] = ev["event_id"]

for lbl in ("subsidence_precursor", "decoy_seismic"):
    df.loc[df["merged_label"] == lbl, "event_type"] = lbl

df_model = df[~df["_exclude_tail"]].copy().sort_values(["timestamp", "node_id"]).reset_index(drop=True)

# per-class medians (whole modelling frame) -- reference for feature-vector comparisons
med = {c: df_model.loc[df_model.event_type == c, FEATURES].median() for c in CLASS_ORDER}

test = df_model[df_model["timestamp"] >= SPLIT_TIMESTAMP].copy()
rf = joblib.load(RF_PATH)
test["_pred"] = rf.predict(test[FEATURES])
proba = rf.predict_proba(test[FEATURES])
for i, c in enumerate(rf.classes_):
    test[f"p_{c}"] = proba[:, i]

print("=" * 92)
print("RF v6 -- test set confusion matrix (rows=true, cols=pred)")
print("=" * 92)
cm = pd.crosstab(test["event_type"], test["_pred"]).reindex(index=CLASS_ORDER, columns=CLASS_ORDER, fill_value=0)
print(cm.to_string())
print(f"\ntest class counts: {test['event_type'].value_counts().to_dict()}")


def show_rows(rows, cols_extra=()):
    cols = ["node_id", "timestamp", "_event_id", "event_type", "_pred"] + list(cols_extra) + \
           [f"p_{c}" for c in CLASS_ORDER] + FEATURES
    with pd.option_context("display.float_format", lambda x: f"{x:.4f}"):
        print(rows[cols].to_string(index=False))


def feature_table(row):
    t = pd.DataFrame({
        "row_value": row[FEATURES].astype(float),
        "median_normal": med["normal"],
        "median_decoy": med["decoy_seismic"],
        "median_precursor": med["subsidence_precursor"],
    })
    with pd.option_context("display.float_format", lambda x: f"{x:9.4f}"):
        print(t.to_string())


# ===========================================================================
# (A) decoy_seismic -> normal   (1 row)
# ===========================================================================
print("\n" + "=" * 92)
print("(A) decoy_seismic MISSED as normal  -- decoy recall 0.95 (19/20)")
print("=" * 92)
A = test[(test.event_type == "decoy_seismic") & (test._pred == "normal")]
print(f"count: {len(A)}\n")
for _, r in A.iterrows():
    print(f"--- {r['_event_id']}  {r['node_id']}  {r['timestamp']} ---")
    feature_table(r)
    print()
# context: show the full decoy episode this row belongs to
if len(A):
    eid = A.iloc[0]["_event_id"]
    print(f"Full episode {eid} (all its test rows, to see if neighbours were caught):")
    show_rows(test[test._event_id == eid].sort_values("timestamp"))
# how close was it? margin between top-2 probs
if len(A):
    r = A.iloc[0]
    print(f"\nclass probabilities: normal={r['p_normal']:.3f}  decoy={r['p_decoy_seismic']:.3f}  "
          f"precursor={r['p_subsidence_precursor']:.3f}")

# ===========================================================================
# (B) subsidence_precursor -> normal   (52 rows)  -- weakest class
# ===========================================================================
print("\n" + "=" * 92)
print("(B) subsidence_precursor MISSED as normal -- precursor recall 0.57 (69/121)")
print("=" * 92)
prec = test[test.event_type == "subsidence_precursor"].copy()
prec["elapsed_h"] = (prec["timestamp"] - prec["_buildup_start"]).dt.total_seconds() / 3600.0
prec["frac_through_buildup"] = (
    (prec["timestamp"] - prec["_buildup_start"]) / (prec["_peak"] - prec["_buildup_start"])
).astype(float)
prec["correct"] = prec["_pred"] == "subsidence_precursor"
prec["phase"] = np.where(prec["elapsed_h"] <= EARLY_CUTOFF_HOURS, "early (<=2h)", "late (>2h)")

print(f"overall recall: {prec['correct'].mean():.3f}  ({prec['correct'].sum()}/{len(prec)})\n")

print("by buildup sub-phase (elapsed hours since start_timestamp):")
print(prec.groupby("phase").agg(rows=("correct", "size"), caught=("correct", "sum"),
                                recall=("correct", "mean")).to_string())

print("\nby fraction through the buildup window (start->peak):")
prec["frac_bin"] = pd.cut(prec["frac_through_buildup"], [0, 0.25, 0.5, 0.75, 1.0001],
                          labels=["0-25%", "25-50%", "50-75%", "75-100%"], include_lowest=True)
print(prec.groupby("frac_bin", observed=False).agg(rows=("correct", "size"), caught=("correct", "sum"),
                                                   recall=("correct", "mean")).to_string())

print("\nper-episode (test set):")
print(prec.groupby("_event_id").agg(
    node=("node_id", "first"), rows=("correct", "size"), caught=("correct", "sum"),
    recall=("correct", "mean"), min_h=("elapsed_h", "min"), max_h=("elapsed_h", "max"),
).to_string())

print("\nfeature medians: MISSED precursor rows vs CAUGHT precursor rows vs class refs")
missed = prec[~prec.correct]
caught = prec[prec.correct]
cmpt = pd.DataFrame({
    "missed_median": missed[FEATURES].median(),
    "caught_median": caught[FEATURES].median(),
    "ref_normal": med["normal"],
    "ref_precursor": med["subsidence_precursor"],
})
with pd.option_context("display.float_format", lambda x: f"{x:9.4f}"):
    print(cmpt.to_string())

print("\nmissed vs caught, split by phase (medians):")
for ph in ["early (<=2h)", "late (>2h)"]:
    sub = prec[prec.phase == ph]
    if len(sub) and (~sub.correct).any() and sub.correct.any():
        tt = pd.DataFrame({"missed": sub[~sub.correct][FEATURES].median(),
                           "caught": sub[sub.correct][FEATURES].median()})
        print(f"\n  [{ph}]  (missed n={int((~sub.correct).sum())}, caught n={int(sub.correct.sum())})")
        with pd.option_context("display.float_format", lambda x: f"{x:9.4f}"):
            print(tt.to_string().replace("\n", "\n  "))

print("\nALL missed precursor rows (row-level):")
show_rows(missed.sort_values(["_event_id", "timestamp"]), cols_extra=["elapsed_h", "frac_through_buildup"])

print("\nLATE-phase misses only (the surprising ones -- signal should be clearly up by now):")
late_missed = missed[missed.phase == "late (>2h)"]
if len(late_missed):
    show_rows(late_missed.sort_values(["_event_id", "timestamp"]), cols_extra=["elapsed_h", "frac_through_buildup"])
else:
    print("  (none -- every late-buildup row was caught)")

# ===========================================================================
# (C) normal -> decoy_seismic   (3 rows)
# ===========================================================================
print("\n" + "=" * 92)
print("(C) normal MISCLASSIFIED as decoy_seismic -- decoy precision 0.864 (19/22)")
print("=" * 92)
C = test[(test.event_type == "normal") & (test._pred == "decoy_seismic")].copy()
print(f"count: {len(C)}\n")
for _, r in C.sort_values("p_decoy_seismic", ascending=False).iterrows():
    print(f"--- {r['node_id']}  {r['timestamp']}  (p_decoy={r['p_decoy_seismic']:.3f}) ---")
    feature_table(r)
    print()
# is each near a real seismic-ish event on that node? show +/- 1h window
for _, r in C.iterrows():
    w = test[(test.node_id == r.node_id) &
             (test.timestamp.between(r.timestamp - pd.Timedelta(hours=1), r.timestamp + pd.Timedelta(hours=1)))]
    print(f"context around {r.node_id} {r.timestamp}:")
    show_rows(w.sort_values("timestamp"))
    print()

# ===========================================================================
# (D) normal <-> subsidence_precursor
# ===========================================================================
print("\n" + "=" * 92)
print("(D) normal <-> subsidence_precursor confusions")
print("=" * 92)
d1 = test[(test.event_type == "normal") & (test._pred == "subsidence_precursor")]
d2 = test[(test.event_type == "subsidence_precursor") & (test._pred == "decoy_seismic")]
print(f"normal -> subsidence_precursor : {len(d1)}   (precursor precision on test = 1.000)")
print(f"subsidence_precursor -> decoy_seismic : {len(d2)}")
print("=> the model NEVER raises a false subsidence alarm on this test set, and never")
print("   confuses the two anomaly classes with each other. All error mass is anomaly<->normal.")

# ===========================================================================
# Worst-N single rows by how confidently wrong they are
# ===========================================================================
print("\n" + "=" * 92)
print("WORST 10 ERRORS by confidence-in-the-wrong-class")
print("=" * 92)
err = test[test.event_type != test._pred].copy()
err["p_pred"] = err.apply(lambda r: r[f"p_{r['_pred']}"], axis=1)
err["p_true"] = err.apply(lambda r: r[f"p_{r['event_type']}"], axis=1)
err["wrongness"] = err["p_pred"] - err["p_true"]
show_rows(err.sort_values("wrongness", ascending=False).head(10), cols_extra=["p_true", "p_pred", "wrongness"])

print("\n" + "=" * 92)
print("SUMMARY NUMBERS (for the README findings section)")
print("=" * 92)
print(f"A  decoy->normal      : {len(A)}")
print(f"B  precursor->normal  : {len(missed)}   (early<=2h: {int((~prec[prec.phase=='early (<=2h)'].correct).sum())}"
      f"/{int((prec.phase=='early (<=2h)').sum())},  late>2h: {int((~prec[prec.phase=='late (>2h)'].correct).sum())}"
      f"/{int((prec.phase=='late (>2h)').sum())})")
print(f"C  normal->decoy      : {len(C)}")
print(f"D  normal->precursor  : {len(d1)}   precursor<->decoy: {len(d2)}")
