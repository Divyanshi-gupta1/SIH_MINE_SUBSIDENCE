"""
Step 3 analysis (NOT a merge): should v2's 15,848 `normal` rows be merged
into training too, now that both v2 anomaly classes are resolved?

Earlier finding (external/README.md): the v4 model, run on v2 normal rows,
predicted `subsidence_precursor` for 1.5% of them and `decoy_seismic` for
a few more -- a distribution shift concentrated in
`tilt_vibration_correlation` (v2's generator produces mildly positive
tilt/vibration correlation on ordinary normal rows more often than ours).

This script quantifies merge-vs-not so a decision can be made. It trains
extra models -- it does NOT write any canonical dataset or model artifact.

Design
------
Base training data = v6 (escalation -> subsidence_precursor,
vibration_disturbance -> decoy_seismic already merged).

v2 normal rows (15,848) are split 75/25 (random, seed 42):
  - `pool`   (75%, ~11,886) -- available to merge into training
  - `holdout`(25%, ~3,962)  -- NEVER trained on, used to score the
                               v2-normal false-alarm rate honestly

Scenarios (LR + RF each):
  A  NOT merged      : train = v6 base
  B  partial merge   : train = v6 base + `pool`
  C  full merge      : train = v6 base + `pool` + `holdout`  (all 15,848)
                       -> for C the holdout is in-sample, flagged as such

Each model scored on:
  1. our standard test set (>= 2026-10-15) -- per-class P/R/F1
  2. the v2-normal `holdout` -- % predicted normal / decoy_seismic /
     subsidence_precursor  (want ~100% normal)
"""
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report

SYN = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\synthetic")
EXT = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\external")

RANDOM_STATE = 42
SPLIT_TS = pd.Timestamp("2026-10-15 00:00:00")
FEATURES = [
    "tilt_deg", "vibration_rms", "displacement_mm", "crack_signal",
    "vibration_duration", "tilt_vibration_correlation", "displacement_persistence",
    "tilt_deviation_from_node_baseline",
]
CLASS_ORDER = ["normal", "decoy_seismic", "subsidence_precursor"]

# ---------------------------------------------------------------------------
# v6 base training frame (reuse build_model_v6 labelling logic, inline)
# ---------------------------------------------------------------------------
df = pd.read_csv(SYN / "simulated_mesh_data_v6_with_external.csv",
                parse_dates=["timestamp"], dtype={"merged_label": "string"})
df["merged_label"] = df["merged_label"].fillna("").astype(str)
events = pd.read_csv(SYN / "events_log.csv",
                     parse_dates=["start_timestamp", "subsidence_event_timestamp", "end_timestamp"])
df["event_type"] = "normal"
df["_excl"] = False
for _, ev in events.iterrows():
    n = ev["node_id"]; s, p, e = ev["start_timestamp"], ev["subsidence_event_timestamp"], ev["end_timestamp"]
    if ev["event_type"] == "subsidence_precursor":
        df.loc[(df.node_id == n) & (df.timestamp >= s) & (df.timestamp <= p), "event_type"] = "subsidence_precursor"
        df.loc[(df.node_id == n) & (df.timestamp > p) & (df.timestamp <= e), "_excl"] = True
    elif ev["event_type"] == "decoy_seismic":
        df.loc[(df.node_id == n) & (df.timestamp >= s) & (df.timestamp <= e), "event_type"] = "decoy_seismic"
for lbl in ("subsidence_precursor", "decoy_seismic"):
    df.loc[df["merged_label"] == lbl, "event_type"] = lbl
df = df[~df["_excl"]].copy()

base_train = df[df.timestamp < SPLIT_TS]
our_test = df[df.timestamp >= SPLIT_TS]
Xte, yte = our_test[FEATURES], our_test["event_type"]

# ---------------------------------------------------------------------------
# v2 normal rows + 75/25 split
# ---------------------------------------------------------------------------
v2eng = pd.read_csv(EXT / "v2_engineered.csv", parse_dates=["timestamp"])
v2norm = v2eng[v2eng.scenario == "normal"].copy()
v2norm["event_type"] = "normal"
pool = v2norm.sample(frac=0.75, random_state=RANDOM_STATE)
holdout = v2norm.drop(pool.index)
print(f"v2 normal rows: {len(v2norm)}  ->  pool(train-eligible)={len(pool)}  holdout(eval-only)={len(holdout)}")
Xho = holdout[FEATURES]

def make_models():
    lr = Pipeline([("scaler", StandardScaler()),
                   ("clf", LogisticRegression(class_weight="balanced", max_iter=2000, random_state=RANDOM_STATE))])
    rf = RandomForestClassifier(n_estimators=200, max_depth=6, class_weight="balanced", random_state=RANDOM_STATE)
    return {"LR": lr, "RF": rf}

SCENARIOS = {
    "A_not_merged": base_train,
    "B_partial_merge_75pct": pd.concat([base_train, pool], ignore_index=True),
    "C_full_merge_all": pd.concat([base_train, pool, holdout], ignore_index=True),
}

rows_test, rows_holdout = [], []
for scen, train_df in SCENARIOS.items():
    Xtr, ytr = train_df[FEATURES], train_df["event_type"]
    for mname, model in make_models().items():
        model.fit(Xtr, ytr)

        rep = classification_report(yte, model.predict(Xte), labels=CLASS_ORDER,
                                    output_dict=True, zero_division=0)
        for cls in CLASS_ORDER:
            rows_test.append({
                "scenario": scen, "model": mname, "class": cls,
                "precision": round(rep[cls]["precision"], 4),
                "recall": round(rep[cls]["recall"], 4),
                "f1": round(rep[cls]["f1-score"], 4),
            })

        pred_ho = pd.Series(model.predict(Xho)).value_counts(normalize=True)
        in_sample = scen == "C_full_merge_all"
        rows_holdout.append({
            "scenario": scen, "model": mname,
            "holdout_in_sample": in_sample,
            "pct_normal": round(100 * pred_ho.get("normal", 0.0), 2),
            "pct_decoy_seismic": round(100 * pred_ho.get("decoy_seismic", 0.0), 2),
            "pct_subsidence_precursor": round(100 * pred_ho.get("subsidence_precursor", 0.0), 2),
        })

test_tbl = pd.DataFrame(rows_test)
ho_tbl = pd.DataFrame(rows_holdout)

print("\n================ (1) our standard test set  (>= 2026-10-15) ================")
for mname in ("LR", "RF"):
    print(f"\n--- {mname} ---")
    piv = test_tbl[test_tbl.model == mname].pivot(index="class", columns="scenario",
                                                  values=["precision", "recall", "f1"])
    print(piv.reindex(CLASS_ORDER).to_string())

print("\n================ (2) v2-normal holdout: predicted-class mix (want ~100% normal) ================")
print(ho_tbl.to_string(index=False))
print("\n(C rows are in-sample on the holdout -- optimistic; A vs B is the honest comparison.)")

ho_tbl.to_csv(SYN / "_v2_normal_merge_analysis_holdout.csv", index=False)
test_tbl.to_csv(SYN / "_v2_normal_merge_analysis_ourtest.csv", index=False)
print(f"\nSaved: {SYN / '_v2_normal_merge_analysis_holdout.csv'}")
print(f"Saved: {SYN / '_v2_normal_merge_analysis_ourtest.csv'}")
