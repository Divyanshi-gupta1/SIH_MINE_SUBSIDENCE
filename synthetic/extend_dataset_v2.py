"""
Second extension: 60 days -> 120 days, +9 subsidence_precursor episodes,
+7 decoy_seismic episodes, introducing 2 NEW nodes (NODE_09, NODE_10) in
addition to reusing the existing 8 -- satisfying "mix of existing and new
nodes." Does NOT touch any of the existing 46,080 rows or 16 episodes
(raw sensor columns verified byte-identical at the end, as before).

NODE_09/NODE_10 are simulated as newly-installed mesh nodes: they have NO
data before 2026-09-30 (their "installation date"), and their
displacement_mm trend is measured relative to THEIR OWN installation date
-- not backdated to the original 2026-08-01 deployment. This is more
realistic than fabricating history for hardware that didn't exist yet,
and is the reason total rows aren't a round number (8 nodes x 120 days +
2 nodes x 60 days, not 10 nodes x 120 days).

Same continuity approach as extend_dataset.py for the 8 existing nodes:
new baseline calibrated from the last 2 clean days of each node's most
recent existing data (now 2026-09-27 to 2026-09-29).
"""
import numpy as np
import pandas as pd
from pathlib import Path

DIR = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\synthetic")
DATA_PATH = DIR / "simulated_mesh_data.csv"
EVENTS_PATH = DIR / "events_log.csv"

ORIGINAL_START = pd.Timestamp("2026-08-01 00:00:00")
INTERVAL_MIN = 15

EXISTING_NODE_RATE_MM_YEAR = {
    "NODE_01": 21, "NODE_02": 29, "NODE_03": 25, "NODE_04": 29,
    "NODE_05": 80, "NODE_06": 21, "NODE_07": 120, "NODE_08": 29,
}
NEW_NODE_RATE_MM_YEAR = {"NODE_09": 29, "NODE_10": 100}  # Jharia-typical / Jharia hotspot-range
NEW_NODE_DEPLOY_DATE = pd.Timestamp("2026-09-30 00:00:00")

rng = np.random.default_rng(44)  # separate seed from both prior generation passes (42, 43)

# ---------------------------------------------------------------------------
# Load existing data verbatim
# ---------------------------------------------------------------------------
orig = pd.read_csv(DATA_PATH, parse_dates=["timestamp"])
orig_raw_cols = ["timestamp", "node_id", "tilt_deg", "vibration_rms", "displacement_mm", "crack_signal"]
orig_backup = orig[orig_raw_cols].copy()
orig_max_ts = orig["timestamp"].max()

NEW_END = pd.Timestamp("2026-11-28 23:45:00")  # 120 days from 2026-08-01
full_grid_8node = pd.date_range(ORIGINAL_START, NEW_END, freq=f"{INTERVAL_MIN}min")
new_grid_8node = full_grid_8node[full_grid_8node > orig_max_ts]
new_grid_2node = pd.date_range(NEW_NODE_DEPLOY_DATE, NEW_END, freq=f"{INTERVAL_MIN}min")

print(f"Original range: {ORIGINAL_START} -> {orig_max_ts} ({len(orig) // 8} samples/node, 8 nodes)")
print(f"Extension range for NODE_01..08: {new_grid_8node.min()} -> {new_grid_8node.max()} ({len(new_grid_8node)} samples/node)")
print(f"NODE_09/NODE_10 (new nodes): {new_grid_2node.min()} -> {new_grid_2node.max()} ({len(new_grid_2node)} samples/node)")

# ---------------------------------------------------------------------------
# Calibrate NODE_01..08 extension baseline from their last 2 clean days
# ---------------------------------------------------------------------------
CLEAN_START = orig_max_ts - pd.Timedelta(days=2) + pd.Timedelta(minutes=INTERVAL_MIN)
CLEAN_END = orig_max_ts

calib = {}
for nid, rate_yr in EXISTING_NODE_RATE_MM_YEAR.items():
    clean = orig[(orig.node_id == nid) & (orig.timestamp >= CLEAN_START) & (orig.timestamp <= CLEAN_END)]
    rate = rate_yr / 365.0
    elapsed = (clean["timestamp"] - ORIGINAL_START).dt.total_seconds() / 86400.0
    residual = clean["displacement_mm"] - elapsed * rate
    calib[nid] = {
        "resting_tilt_deg": clean["tilt_deg"].median(), "tilt_noise_std": clean["tilt_deg"].std(),
        "resting_vibration_rms": clean["vibration_rms"].median(), "vibration_noise_std": clean["vibration_rms"].std(),
        "background_mm_per_day": rate, "displacement_offset_mm": residual.mean(),
        "displacement_noise_std_mm": residual.std(),
    }

new_rows = []
for nid in EXISTING_NODE_RATE_MM_YEAR:
    c = calib[nid]
    n = len(new_grid_8node)
    elapsed_days = (new_grid_8node - ORIGINAL_START).total_seconds().to_numpy() / 86400.0
    tilt = c["resting_tilt_deg"] + rng.normal(0, c["tilt_noise_std"], n)
    vib = np.abs(c["resting_vibration_rms"] + rng.normal(0, c["vibration_noise_std"], n))
    disp = elapsed_days * c["background_mm_per_day"] + c["displacement_offset_mm"] + rng.normal(0, c["displacement_noise_std_mm"], n)
    crack = (rng.random(n) < 0.001).astype(int)
    new_rows.append(pd.DataFrame({"timestamp": new_grid_8node, "node_id": nid, "tilt_deg": tilt,
                                    "vibration_rms": vib, "displacement_mm": disp, "crack_signal": crack}))

# ---------------------------------------------------------------------------
# Fresh baseline params for the 2 brand-new nodes (no history to calibrate from)
# ---------------------------------------------------------------------------
for nid, rate_yr in NEW_NODE_RATE_MM_YEAR.items():
    n = len(new_grid_2node)
    resting_tilt = rng.uniform(0.05, 0.30)
    tilt_noise_std = rng.uniform(0.015, 0.03)
    resting_vib = rng.uniform(0.015, 0.05)
    vib_noise_std_frac = rng.uniform(0.15, 0.30)
    disp_noise_std = rng.uniform(0.03, 0.08)
    rate = rate_yr / 365.0

    elapsed_days = (new_grid_2node - NEW_NODE_DEPLOY_DATE).total_seconds().to_numpy() / 86400.0
    tilt = resting_tilt + rng.normal(0, tilt_noise_std, n)
    vib = np.abs(resting_vib + rng.normal(0, resting_vib * vib_noise_std_frac, n))
    disp = elapsed_days * rate + rng.normal(0, disp_noise_std, n)
    crack = (rng.random(n) < 0.001).astype(int)
    new_rows.append(pd.DataFrame({"timestamp": new_grid_2node, "node_id": nid, "tilt_deg": tilt,
                                    "vibration_rms": vib, "displacement_mm": disp, "crack_signal": crack}))

new_df = pd.concat(new_rows, ignore_index=True)

# ---------------------------------------------------------------------------
# New episodes
# ---------------------------------------------------------------------------
new_precursor_episodes = [
    {"event_id": "EVT_18", "node_id": "NODE_09", "peak": pd.Timestamp("2026-10-03 09:00:00"),
     "buildup_hours": 6.0, "tail_hours": 2.0, "added_tilt_deg": 2.3, "added_displacement_mm": 21.0, "vibration_multiplier": 5.8},
    {"event_id": "EVT_19", "node_id": "NODE_10", "peak": pd.Timestamp("2026-10-06 15:00:00"),
     "buildup_hours": 8.5, "tail_hours": 3.0, "added_tilt_deg": 3.8, "added_displacement_mm": 33.0, "vibration_multiplier": 7.8},
    {"event_id": "EVT_20", "node_id": "NODE_01", "peak": pd.Timestamp("2026-10-09 21:00:00"),
     "buildup_hours": 4.5, "tail_hours": 1.5, "added_tilt_deg": 1.6, "added_displacement_mm": 15.0, "vibration_multiplier": 4.2},
    {"event_id": "EVT_21", "node_id": "NODE_03", "peak": pd.Timestamp("2026-10-13 06:00:00"),
     "buildup_hours": 7.0, "tail_hours": 2.5, "added_tilt_deg": 2.9, "added_displacement_mm": 25.0, "vibration_multiplier": 6.3},
    {"event_id": "EVT_22", "node_id": "NODE_05", "peak": pd.Timestamp("2026-10-17 12:00:00"),
     "buildup_hours": 5.0, "tail_hours": 2.0, "added_tilt_deg": 2.0, "added_displacement_mm": 18.0, "vibration_multiplier": 5.0},
    {"event_id": "EVT_23", "node_id": "NODE_07", "peak": pd.Timestamp("2026-10-21 18:00:00"),
     "buildup_hours": 6.5, "tail_hours": 2.0, "added_tilt_deg": 2.6, "added_displacement_mm": 23.0, "vibration_multiplier": 6.6},
    {"event_id": "EVT_24", "node_id": "NODE_02", "peak": pd.Timestamp("2026-10-27 08:00:00"),
     "buildup_hours": 4.0, "tail_hours": 1.5, "added_tilt_deg": 1.3, "added_displacement_mm": 12.0, "vibration_multiplier": 3.8},
    {"event_id": "EVT_25", "node_id": "NODE_04", "peak": pd.Timestamp("2026-11-01 14:00:00"),
     "buildup_hours": 8.0, "tail_hours": 3.0, "added_tilt_deg": 3.4, "added_displacement_mm": 30.0, "vibration_multiplier": 7.2},
    {"event_id": "EVT_26", "node_id": "NODE_06", "peak": pd.Timestamp("2026-11-06 20:00:00"),
     "buildup_hours": 5.5, "tail_hours": 2.0, "added_tilt_deg": 2.2, "added_displacement_mm": 20.0, "vibration_multiplier": 5.4},
]
for ep in new_precursor_episodes:
    ep["start"] = ep["peak"] - pd.Timedelta(hours=ep["buildup_hours"])
    ep["end"] = ep["peak"] + pd.Timedelta(hours=ep["tail_hours"])

new_decoy_episodes = [
    {"event_id": "EVT_27", "node_id": "NODE_08",
     "spike": [(pd.Timestamp("2026-10-11 09:45:00"), 3.0), (pd.Timestamp("2026-10-11 10:00:00"), 8.5), (pd.Timestamp("2026-10-11 10:15:00"), 2.2)],
     "peak": pd.Timestamp("2026-10-11 10:00:00")},
    {"event_id": "EVT_28", "node_id": "NODE_09",
     "spike": [(pd.Timestamp("2026-10-20 13:30:00"), 2.7), (pd.Timestamp("2026-10-20 13:45:00"), 4.3), (pd.Timestamp("2026-10-20 14:00:00"), 6.0), (pd.Timestamp("2026-10-20 14:15:00"), 3.4)],
     "peak": pd.Timestamp("2026-10-20 14:00:00")},
    {"event_id": "EVT_29", "node_id": "NODE_10",
     "spike": [(pd.Timestamp("2026-10-24 08:45:00"), 4.0), (pd.Timestamp("2026-10-24 09:00:00"), 9.8)],
     "peak": pd.Timestamp("2026-10-24 09:00:00")},
    {"event_id": "EVT_30", "node_id": "NODE_01",
     "spike": [(pd.Timestamp("2026-10-29 15:30:00"), 2.5), (pd.Timestamp("2026-10-29 15:45:00"), 4.0), (pd.Timestamp("2026-10-29 16:00:00"), 5.5), (pd.Timestamp("2026-10-29 16:15:00"), 3.0)],
     "peak": pd.Timestamp("2026-10-29 16:00:00")},
    {"event_id": "EVT_31", "node_id": "NODE_03",
     "spike": [(pd.Timestamp("2026-11-05 10:45:00"), 3.4), (pd.Timestamp("2026-11-05 11:00:00"), 7.6), (pd.Timestamp("2026-11-05 11:15:00"), 2.0)],
     "peak": pd.Timestamp("2026-11-05 11:00:00")},
    {"event_id": "EVT_32", "node_id": "NODE_05",
     "spike": [(pd.Timestamp("2026-11-09 16:30:00"), 2.9), (pd.Timestamp("2026-11-09 16:45:00"), 4.5), (pd.Timestamp("2026-11-09 17:00:00"), 6.4), (pd.Timestamp("2026-11-09 17:15:00"), 3.6)],
     "peak": pd.Timestamp("2026-11-09 17:00:00")},
    {"event_id": "EVT_33", "node_id": "NODE_07",
     "spike": [(pd.Timestamp("2026-11-13 07:45:00"), 3.6), (pd.Timestamp("2026-11-13 08:00:00"), 9.0), (pd.Timestamp("2026-11-13 08:15:00"), 2.5)],
     "peak": pd.Timestamp("2026-11-13 08:00:00")},
]

# sanity: no overlap between any two NEW episodes on the same node
all_windows = [(ep["node_id"], ep["start"], ep["end"]) for ep in new_precursor_episodes]
all_windows += [(ep["node_id"], ep["spike"][0][0], ep["spike"][-1][0]) for ep in new_decoy_episodes]
for i in range(len(all_windows)):
    for j in range(i + 1, len(all_windows)):
        n1, s1, e1 = all_windows[i]
        n2, s2, e2 = all_windows[j]
        if n1 == n2 and not (e1 < s2 or e2 < s1):
            raise ValueError(f"Overlapping episodes on {n1}: {all_windows[i]} vs {all_windows[j]}")

# ---------------------------------------------------------------------------
# Inject precursor episodes
# ---------------------------------------------------------------------------
for ep in new_precursor_episodes:
    node_mask = new_df["node_id"] == ep["node_id"]
    t = new_df.loc[node_mask, "timestamp"]

    in_buildup = (t >= ep["start"]) & (t <= ep["peak"])
    if in_buildup.any():
        idx = t[in_buildup].index
        frac = ((t[in_buildup] - ep["start"]) / (ep["peak"] - ep["start"])).astype(float)
        accel = frac ** 2
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
# Inject decoy episodes
# ---------------------------------------------------------------------------
for ep in new_decoy_episodes:
    for ts, mult in ep["spike"]:
        mask = (new_df["node_id"] == ep["node_id"]) & (new_df["timestamp"] == ts)
        if not mask.any():
            raise ValueError(f"Timestamp {ts} not found for {ep['node_id']}.")
        new_df.loc[mask, "vibration_rms"] = new_df.loc[mask, "vibration_rms"] * mult
        new_df.loc[mask, "crack_signal"] = 0

new_df["tilt_deg"] = new_df["tilt_deg"].round(4)
new_df["vibration_rms"] = new_df["vibration_rms"].round(4)
new_df["displacement_mm"] = new_df["displacement_mm"].round(3)
new_df["crack_signal"] = new_df["crack_signal"].astype(int)

# ---------------------------------------------------------------------------
# Combine + recompute derived features over the full series
# ---------------------------------------------------------------------------
full = pd.concat([orig[orig_raw_cols], new_df[orig_raw_cols]], ignore_index=True)
full = full.sort_values(["node_id", "timestamp"]).reset_index(drop=True)

WINDOW = 8
PERSIST_N = 8
PERSIST_LOOKBACK = 4
PERSIST_THRESHOLD_MM = 0.5

vib_duration = pd.Series(index=full.index, dtype="int64")
tilt_vib_corr = pd.Series(index=full.index, dtype="float64")
disp_persist = pd.Series(0, index=full.index, dtype="int64")

for node, g in full.groupby("node_id", sort=False):
    idx = g.index
    vib = g["vibration_rms"].to_numpy()
    tilt = g["tilt_deg"]
    disp = g["displacement_mm"].to_numpy()

    med = np.median(vib)
    mad = np.median(np.abs(vib - med)) * 1.4826
    threshold = med + 4 * mad
    above = vib > threshold

    above_s = pd.Series(above, index=g.index)
    run_id = (~above_s).cumsum()
    streak = above_s.groupby(run_id).cumcount() + 1
    streak = streak.where(above_s, 0)
    vib_duration.loc[idx] = streak.to_numpy()

    corr = tilt.rolling(WINDOW).corr(g["vibration_rms"]).fillna(0.0)
    tilt_vib_corr.loc[idx] = corr.to_numpy()

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
    disp_persist.loc[idx] = out

full["vibration_duration"] = vib_duration
full["tilt_vibration_correlation"] = tilt_vib_corr.round(4)
full["displacement_persistence"] = disp_persist

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
# Verify + summary
# ---------------------------------------------------------------------------
check = full[full["timestamp"] <= orig_max_ts][orig_raw_cols].sort_values(["timestamp", "node_id"]).reset_index(drop=True)
orig_sorted = orig_backup.sort_values(["timestamp", "node_id"]).reset_index(drop=True)
identical = orig_sorted.equals(check)
print(f"\nOriginal 46,080 rows' raw sensor columns byte-identical after extension: {identical}")
if not identical:
    raise AssertionError("Original rows were modified -- this should never happen.")

print(f"\nTotal rows: {len(full)} (was {len(orig)})")
print(f"Date range: {full['timestamp'].min()} -> {full['timestamp'].max()}")
print(f"Nodes: {sorted(full['node_id'].unique())}")
print(f"Total episodes in events_log.csv: {len(events)} (was 17)")
print(events["event_type"].value_counts().to_string())
