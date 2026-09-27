"""
Extends the synthetic mesh dataset from 21 days to 60 days and adds 6 more
subsidence_precursor episodes + 6 more decoy_seismic episodes, WITHOUT
touching the existing 16,128 original rows (raw sensor columns are kept
byte-identical for those rows -- verified at the end of this script).

Strategy: the original rows are preserved verbatim and concatenated with
NEWLY GENERATED rows for 2026-08-22 through the new end date. Continuity
at the boundary is achieved by calibrating each node's new baseline
(resting tilt/vibration level + noise scale, displacement trend offset)
from the last 2 clean days (2026-08-20 to 2026-08-21) of its EXISTING
data, rather than re-deriving the original generator's internal RNG
state. This naturally carries forward any permanent tilt/displacement
offset left by the 3 original precursor episodes (NODE_02/05/07) with no
special-casing, because that offset is already baked into those nodes'
most recent real readings.

All 3 derived feature columns (vibration_duration,
tilt_vibration_correlation, displacement_persistence) are recomputed from
scratch over the FULL 60-day series for every row, per this task's
requirement 4 -- so while the original rows' RAW sensor columns stay
byte-identical, their DERIVED columns may shift slightly (a longer
history marginally changes each node's robust baseline threshold). This
is intentional and expected, not a bug.

IMPORTANT COLUMN-SEMANTICS CHANGE: displacement_persistence in the CSV
now holds the CAUSAL version (only ever looks at the current row and the
past) -- the version previously used internally by model/build_model.py.
This replaces the earlier RETROSPECTIVE version built for the decoy
verification plots (which intentionally looked ~2h into the future and
would leak information if used as a model feature). The verification
plot script never read this column (it only used tilt_deg/vibration_rms),
so this change does not affect it.
"""
import numpy as np
import pandas as pd
from pathlib import Path

DIR = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\synthetic")
DATA_PATH = DIR / "simulated_mesh_data.csv"
EVENTS_PATH = DIR / "events_log.csv"

ORIGINAL_START = pd.Timestamp("2026-08-01 00:00:00")
NEW_TOTAL_DAYS = 60
INTERVAL_MIN = 15

REGIONAL_RATE_MM_YEAR = {
    "NODE_01": 21, "NODE_02": 29, "NODE_03": 25, "NODE_04": 29,
    "NODE_05": 80, "NODE_06": 21, "NODE_07": 120, "NODE_08": 29,
}
NODE_IDS = list(REGIONAL_RATE_MM_YEAR.keys())

rng = np.random.default_rng(43)  # separate seed from the original generator (42), documented

# ---------------------------------------------------------------------------
# Load existing data verbatim
# ---------------------------------------------------------------------------
orig = pd.read_csv(DATA_PATH, parse_dates=["timestamp"])
orig_raw_cols = ["timestamp", "node_id", "tilt_deg", "vibration_rms", "displacement_mm", "crack_signal"]
orig_backup = orig[orig_raw_cols].copy()  # for the byte-identical verification at the end

orig_max_ts = orig["timestamp"].max()

# ---------------------------------------------------------------------------
# New time grid for the extension (2026-08-22 00:00 -> new end date)
# ---------------------------------------------------------------------------
full_grid = pd.date_range(ORIGINAL_START, periods=NEW_TOTAL_DAYS * 24 * 60 // INTERVAL_MIN, freq=f"{INTERVAL_MIN}min")
new_grid = full_grid[full_grid > orig_max_ts]
print(f"Original range: {ORIGINAL_START} -> {orig_max_ts} ({len(orig) // len(NODE_IDS)} samples/node)")
print(f"Extension range: {new_grid.min()} -> {new_grid.max()} ({len(new_grid)} samples/node)")

# ---------------------------------------------------------------------------
# Calibrate each node's extension baseline from its last 2 clean days
# ---------------------------------------------------------------------------
CLEAN_START = pd.Timestamp("2026-08-20 00:00:00")
CLEAN_END = orig_max_ts

calib = {}
for nid in NODE_IDS:
    clean = orig[(orig.node_id == nid) & (orig.timestamp >= CLEAN_START) & (orig.timestamp <= CLEAN_END)]
    rate = REGIONAL_RATE_MM_YEAR[nid] / 365.0
    elapsed = (clean["timestamp"] - ORIGINAL_START).dt.total_seconds() / 86400.0
    residual = clean["displacement_mm"] - elapsed * rate  # noise + any permanent offset baked in
    calib[nid] = {
        "resting_tilt_deg": clean["tilt_deg"].median(),
        "tilt_noise_std": clean["tilt_deg"].std(),
        "resting_vibration_rms": clean["vibration_rms"].median(),
        "vibration_noise_std": clean["vibration_rms"].std(),
        "background_mm_per_day": rate,
        "displacement_offset_mm": residual.mean(),
        "displacement_noise_std_mm": residual.std(),
    }

# ---------------------------------------------------------------------------
# Generate new baseline rows
# ---------------------------------------------------------------------------
new_rows = []
n_new = len(new_grid)
for nid in NODE_IDS:
    c = calib[nid]
    elapsed_days = (new_grid - ORIGINAL_START).total_seconds().to_numpy() / 86400.0

    tilt = c["resting_tilt_deg"] + rng.normal(0, c["tilt_noise_std"], n_new)
    vib = np.abs(c["resting_vibration_rms"] + rng.normal(0, c["vibration_noise_std"], n_new))
    disp = elapsed_days * c["background_mm_per_day"] + c["displacement_offset_mm"] + rng.normal(0, c["displacement_noise_std_mm"], n_new)
    crack = (rng.random(n_new) < 0.001).astype(int)

    new_rows.append(pd.DataFrame({
        "timestamp": new_grid, "node_id": nid, "tilt_deg": tilt,
        "vibration_rms": vib, "displacement_mm": disp, "crack_signal": crack,
    }))

new_df = pd.concat(new_rows, ignore_index=True)

# ---------------------------------------------------------------------------
# New episodes (all within the extension window, no overlaps per node)
# ---------------------------------------------------------------------------
new_precursor_episodes = [
    {"event_id": "EVT_06", "node_id": "NODE_03", "peak": pd.Timestamp("2026-08-25 10:00:00"),
     "buildup_hours": 5.0, "tail_hours": 2.0, "added_tilt_deg": 2.0, "added_displacement_mm": 19.0, "vibration_multiplier": 5.5},
    {"event_id": "EVT_07", "node_id": "NODE_06", "peak": pd.Timestamp("2026-08-30 16:00:00"),
     "buildup_hours": 8.0, "tail_hours": 3.0, "added_tilt_deg": 3.0, "added_displacement_mm": 26.0, "vibration_multiplier": 6.8},
    {"event_id": "EVT_08", "node_id": "NODE_08", "peak": pd.Timestamp("2026-09-04 22:00:00"),
     "buildup_hours": 4.0, "tail_hours": 1.5, "added_tilt_deg": 1.5, "added_displacement_mm": 14.0, "vibration_multiplier": 4.0},
    {"event_id": "EVT_09", "node_id": "NODE_01", "peak": pd.Timestamp("2026-09-10 07:00:00"),
     "buildup_hours": 6.5, "tail_hours": 2.0, "added_tilt_deg": 2.8, "added_displacement_mm": 24.0, "vibration_multiplier": 7.0},
    {"event_id": "EVT_10", "node_id": "NODE_04", "peak": pd.Timestamp("2026-09-18 13:00:00"),
     "buildup_hours": 7.5, "tail_hours": 2.5, "added_tilt_deg": 3.3, "added_displacement_mm": 29.0, "vibration_multiplier": 6.0},
    {"event_id": "EVT_11", "node_id": "NODE_02", "peak": pd.Timestamp("2026-09-25 18:00:00"),
     "buildup_hours": 5.5, "tail_hours": 2.0, "added_tilt_deg": 2.2, "added_displacement_mm": 20.0, "vibration_multiplier": 5.0},
]
for ep in new_precursor_episodes:
    ep["start"] = ep["peak"] - pd.Timedelta(hours=ep["buildup_hours"])
    ep["end"] = ep["peak"] + pd.Timedelta(hours=ep["tail_hours"])

new_decoy_episodes = [
    {"event_id": "EVT_12", "node_id": "NODE_05", "label": "sharp",
     "spike": [(pd.Timestamp("2026-08-24 08:45:00"), 3.0), (pd.Timestamp("2026-08-24 09:00:00"), 8.0), (pd.Timestamp("2026-08-24 09:15:00"), 2.4)],
     "peak": pd.Timestamp("2026-08-24 09:00:00")},
    {"event_id": "EVT_13", "node_id": "NODE_07", "label": "broad",
     "spike": [(pd.Timestamp("2026-08-29 13:30:00"), 2.6), (pd.Timestamp("2026-08-29 13:45:00"), 4.4), (pd.Timestamp("2026-08-29 14:00:00"), 5.8), (pd.Timestamp("2026-08-29 14:15:00"), 3.2)],
     "peak": pd.Timestamp("2026-08-29 14:00:00")},
    {"event_id": "EVT_14", "node_id": "NODE_03", "label": "sharp",
     "spike": [(pd.Timestamp("2026-09-02 10:45:00"), 3.2), (pd.Timestamp("2026-09-02 11:00:00"), 7.2), (pd.Timestamp("2026-09-02 11:15:00"), 2.1)],
     "peak": pd.Timestamp("2026-09-02 11:00:00")},
    {"event_id": "EVT_15", "node_id": "NODE_06", "label": "broad",
     "spike": [(pd.Timestamp("2026-09-07 15:45:00"), 2.8), (pd.Timestamp("2026-09-07 16:00:00"), 4.6), (pd.Timestamp("2026-09-07 16:15:00"), 6.2), (pd.Timestamp("2026-09-07 16:30:00"), 3.8)],
     "peak": pd.Timestamp("2026-09-07 16:15:00")},
    {"event_id": "EVT_16", "node_id": "NODE_08", "label": "sharp",
     "spike": [(pd.Timestamp("2026-09-14 07:45:00"), 3.5), (pd.Timestamp("2026-09-14 08:00:00"), 9.4), (pd.Timestamp("2026-09-14 08:15:00"), 2.0)],
     "peak": pd.Timestamp("2026-09-14 08:00:00")},
    {"event_id": "EVT_17", "node_id": "NODE_01", "label": "broad",
     "spike": [(pd.Timestamp("2026-09-22 18:30:00"), 2.4), (pd.Timestamp("2026-09-22 18:45:00"), 4.0), (pd.Timestamp("2026-09-22 19:00:00"), 5.2), (pd.Timestamp("2026-09-22 19:15:00"), 3.6)],
     "peak": pd.Timestamp("2026-09-22 19:00:00")},
]

# sanity: no overlap between any two episodes on the same node (old + new)
all_windows = [(ep["node_id"], ep["start"], ep["end"]) for ep in new_precursor_episodes]
all_windows += [(ep["node_id"], ep["spike"][0][0], ep["spike"][-1][0]) for ep in new_decoy_episodes]
for i in range(len(all_windows)):
    for j in range(i + 1, len(all_windows)):
        n1, s1, e1 = all_windows[i]
        n2, s2, e2 = all_windows[j]
        if n1 == n2 and not (e1 < s2 or e2 < s1):
            raise ValueError(f"Overlapping episodes on {n1}: {all_windows[i]} vs {all_windows[j]}")

# ---------------------------------------------------------------------------
# Inject precursor episodes (same accelerating-buildup + tail logic as the
# original generator)
# ---------------------------------------------------------------------------
for ep in new_precursor_episodes:
    node = ep["node_id"]
    node_mask = new_df["node_id"] == node
    t = new_df.loc[node_mask, "timestamp"]

    in_buildup = (t >= ep["start"]) & (t <= ep["peak"])
    if in_buildup.any():
        frac = ((t[in_buildup] - ep["start"]) / (ep["peak"] - ep["start"])).astype(float)
        accel = frac ** 2
        idx = t[in_buildup].index
        new_df.loc[idx, "tilt_deg"] += accel.to_numpy() * ep["added_tilt_deg"]
        new_df.loc[idx, "vibration_rms"] *= (1 + accel.to_numpy() * (ep["vibration_multiplier"] - 1))
        new_df.loc[idx, "displacement_mm"] += accel.to_numpy() * ep["added_displacement_mm"]
        crack_prob = np.clip(accel.to_numpy() ** 3 * 0.9, 0, 0.9)
        flips = rng.random(len(idx)) < crack_prob
        new_df.loc[idx[flips], "crack_signal"] = 1
        peak_idx = t[t == ep["peak"]].index
        new_df.loc[peak_idx, "crack_signal"] = 1

    in_tail = (t > ep["peak"]) & (t <= ep["end"])
    if in_tail.any():
        idx = t[in_tail].index
        tail_frac = ((ep["end"] - t[in_tail]) / (ep["end"] - ep["peak"])).astype(float)
        new_df.loc[idx, "tilt_deg"] += ep["added_tilt_deg"]
        new_df.loc[idx, "displacement_mm"] += ep["added_displacement_mm"]
        new_df.loc[idx, "vibration_rms"] *= (1 + tail_frac.to_numpy() * (ep["vibration_multiplier"] - 1))
        crack_prob = np.clip(tail_frac.to_numpy() * 0.5, 0, 0.5)
        flips = rng.random(len(idx)) < crack_prob
        new_df.loc[idx[flips], "crack_signal"] = 1

    after = t > ep["end"]
    if after.any():
        idx = t[after].index
        new_df.loc[idx, "tilt_deg"] += ep["added_tilt_deg"]
        new_df.loc[idx, "displacement_mm"] += ep["added_displacement_mm"]

# ---------------------------------------------------------------------------
# Inject decoy episodes (same simple-multiply logic as add_decoy_episodes.py)
# ---------------------------------------------------------------------------
for ep in new_decoy_episodes:
    node = ep["node_id"]
    for ts, mult in ep["spike"]:
        mask = (new_df["node_id"] == node) & (new_df["timestamp"] == ts)
        if not mask.any():
            raise ValueError(f"Timestamp {ts} not found for {node} in the extension grid.")
        new_df.loc[mask, "vibration_rms"] = new_df.loc[mask, "vibration_rms"] * mult
        new_df.loc[mask, "crack_signal"] = 0

new_df["tilt_deg"] = new_df["tilt_deg"].round(4)
new_df["vibration_rms"] = new_df["vibration_rms"].round(4)
new_df["displacement_mm"] = new_df["displacement_mm"].round(3)
new_df["crack_signal"] = new_df["crack_signal"].astype(int)

# ---------------------------------------------------------------------------
# Combine original (verbatim) + new rows
# ---------------------------------------------------------------------------
full = pd.concat([orig[orig_raw_cols], new_df[orig_raw_cols]], ignore_index=True)
full = full.sort_values(["timestamp", "node_id"]).reset_index(drop=True)

# ---------------------------------------------------------------------------
# Recompute all 3 derived features over the FULL 60-day series (requirement 4)
# ---------------------------------------------------------------------------
WINDOW = 8
PERSIST_N = 8
PERSIST_LOOKBACK = 4
PERSIST_THRESHOLD_MM = 0.5

full = full.sort_values(["node_id", "timestamp"]).reset_index(drop=True)
vib_duration = pd.Series(index=full.index, dtype="int64")
tilt_vib_corr = pd.Series(index=full.index, dtype="float64")
disp_persist_causal = pd.Series(0, index=full.index, dtype="int64")

for node, g in full.groupby("node_id", sort=False):
    idx = g.index
    vib = g["vibration_rms"].to_numpy()
    tilt = g["tilt_deg"]
    disp = g["displacement_mm"].to_numpy()

    med = np.median(vib)
    mad = np.median(np.abs(vib - med)) * 1.4826
    threshold = med + 4 * mad
    above = vib > threshold

    # vibration_duration: consecutive-run length above threshold
    above_s = pd.Series(above, index=g.index)
    run_id = (~above_s).cumsum()
    streak = above_s.groupby(run_id).cumcount() + 1
    streak = streak.where(above_s, 0)
    vib_duration.loc[idx] = streak.to_numpy()

    # tilt_vibration_correlation: trailing rolling correlation (causal)
    corr = tilt.rolling(WINDOW).corr(g["vibration_rms"]).fillna(0.0)
    tilt_vib_corr.loc[idx] = corr.to_numpy()

    # displacement_persistence: CAUSAL (only current + past rows)
    n = len(g)
    out = np.zeros(n, dtype="int64")
    last_spike_start = -10 ** 9
    pre_baseline = 0.0
    for j in range(n):
        if above[j] and (j == 0 or not above[j - 1]):
            i = j
            lb_start = max(0, i - PERSIST_LOOKBACK)
            pre_baseline = disp[lb_start:i].mean() if i > lb_start else disp[i]
            last_spike_start = i
        if last_spike_start >= 0 and (j - last_spike_start) <= PERSIST_N:
            out[j] = int((disp[j] - pre_baseline) > PERSIST_THRESHOLD_MM)
        else:
            out[j] = 0
    disp_persist_causal.loc[idx] = out

full["vibration_duration"] = vib_duration
full["tilt_vibration_correlation"] = tilt_vib_corr.round(4)
full["displacement_persistence"] = disp_persist_causal  # now the CAUSAL version, see module docstring

full = full.sort_values(["timestamp", "node_id"]).reset_index(drop=True)
full.to_csv(DATA_PATH, index=False)

# ---------------------------------------------------------------------------
# Update events_log.csv
# ---------------------------------------------------------------------------
events = pd.read_csv(EVENTS_PATH)

new_event_rows = []
for ep in new_precursor_episodes:
    new_event_rows.append({
        "event_id": ep["event_id"], "node_id": ep["node_id"],
        "start_timestamp": ep["start"], "subsidence_event_timestamp": ep["peak"], "end_timestamp": ep["end"],
        "buildup_hours": ep["buildup_hours"], "added_tilt_deg": ep["added_tilt_deg"],
        "added_displacement_mm": ep["added_displacement_mm"], "vibration_multiplier_at_peak": ep["vibration_multiplier"],
        "event_type": "subsidence_precursor",
    })
for ep in new_decoy_episodes:
    spikes = ep["spike"]
    start_ts, end_ts = spikes[0][0], spikes[-1][0]
    duration_hours = round((end_ts - start_ts).total_seconds() / 3600 + 0.25, 2)
    new_event_rows.append({
        "event_id": ep["event_id"], "node_id": ep["node_id"],
        "start_timestamp": start_ts, "subsidence_event_timestamp": ep["peak"], "end_timestamp": end_ts,
        "buildup_hours": duration_hours, "added_tilt_deg": 0.0, "added_displacement_mm": 0.0,
        "vibration_multiplier_at_peak": max(m for _, m in spikes), "event_type": "decoy_seismic",
    })

events = pd.concat([events, pd.DataFrame(new_event_rows)], ignore_index=True)
events.to_csv(EVENTS_PATH, index=False)

# ---------------------------------------------------------------------------
# Verify: original rows' RAW columns are byte-identical
# ---------------------------------------------------------------------------
check = full[full["timestamp"] <= orig_max_ts][orig_raw_cols].reset_index(drop=True)
check_sorted = check.sort_values(["timestamp", "node_id"]).reset_index(drop=True)
orig_sorted = orig_backup.sort_values(["timestamp", "node_id"]).reset_index(drop=True)
identical = orig_sorted.equals(check_sorted)
print(f"\nOriginal 16,128 rows' raw sensor columns byte-identical after extension: {identical}")
if not identical:
    raise AssertionError("Original rows were modified -- this should never happen.")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\nTotal rows: {len(full)} (was {len(orig)})")
print(f"Date range: {full['timestamp'].min()} -> {full['timestamp'].max()}")
print(f"Total episodes in events_log.csv: {len(events)} (was 5)")
print(events["event_type"].value_counts().to_string())
