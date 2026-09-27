"""
Part 2: synthetic ESP32/LoRa mesh sensor dataset, shaped exactly like the
real hardware's output schema, so an anomaly-detection model can be built
and tested before hardware exists.

Output:
  synthetic/simulated_mesh_data.csv  -- columns: timestamp, node_id,
      tilt_deg, vibration_rms, displacement_mm, crack_signal
  synthetic/events_log.csv           -- one row per injected anomaly
      episode, marking start/peak (subsidence_event) timestamps and node

MAGNITUDE GROUNDING (see synthetic/README.md for the full explanation):
  - Each node is assigned a regional annual subsidence rate drawn from the
    cited Indian coalfield InSAR ranges (Raniganj ~21 mm/yr; Jharia
    ~29 mm/yr typical, 80-120 mm/yr in hotspots). This directly sets the
    BACKGROUND daily displacement drift for that node.
  - Anomaly-episode burst magnitudes (extra tilt, extra displacement,
    vibration multiplier) are a SEPARATE, explicitly-flagged engineering
    assumption, not derived from the InSAR annual-rate papers -- InSAR
    measures regional annual averages, not single-event burst sizes or
    inclinometer tilt. See README for exact numbers and reasoning.

Reproducible: fixed random seed (42).
"""
import numpy as np
import pandas as pd
from pathlib import Path

OUT_DIR = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\synthetic")
OUT_DIR.mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(42)

# ---------------------------------------------------------------------------
# Time grid
# ---------------------------------------------------------------------------
START = pd.Timestamp("2026-08-01 00:00:00")
INTERVAL_MIN = 15
DURATION_DAYS = 21
n_steps = int(DURATION_DAYS * 24 * 60 / INTERVAL_MIN)
timestamps = pd.date_range(START, periods=n_steps, freq=f"{INTERVAL_MIN}min")

NODE_IDS = [f"NODE_{i:02d}" for i in range(1, 9)]  # 8 nodes

# Regional annual subsidence rate (mm/year) assigned per node, drawn from
# the cited Jharia/Raniganj InSAR ranges -- see README for citations.
REGIONAL_RATE_MM_YEAR = {
    "NODE_01": 21,   # Raniganj-typical
    "NODE_02": 29,   # Jharia-typical
    "NODE_03": 25,   # Raniganj/Jharia-typical blend
    "NODE_04": 29,   # Jharia-typical
    "NODE_05": 80,   # Jharia hotspot (lower end)
    "NODE_06": 21,   # Raniganj-typical
    "NODE_07": 120,  # Jharia hotspot (upper end)
    "NODE_08": 29,   # Jharia-typical
}

# ---------------------------------------------------------------------------
# Per-node baseline sensor characteristics
# ---------------------------------------------------------------------------
node_params = {}
for nid in NODE_IDS:
    node_params[nid] = {
        "resting_tilt_deg": rng.uniform(0.05, 0.30),
        "tilt_noise_std": rng.uniform(0.015, 0.03),
        "resting_vibration_rms": rng.uniform(0.015, 0.05),  # g, ambient MEMS noise floor
        "vibration_noise_std_frac": rng.uniform(0.15, 0.30),  # fraction of resting value
        "background_mm_per_day": REGIONAL_RATE_MM_YEAR[nid] / 365.0,
        "displacement_noise_std_mm": rng.uniform(0.03, 0.08),
    }

# ---------------------------------------------------------------------------
# Anomaly episodes: 3 total, on 3 different nodes, at different times.
# Each: buildup_hours before peak (the "subsidence_event"), then a shorter
# tail where vibration/cracking partially relax but tilt/displacement keep
# a permanent offset (ground movement doesn't reverse).
# ---------------------------------------------------------------------------
episodes = [
    {
        "event_id": "EVT_01",
        "node_id": "NODE_02",
        "peak": START + pd.Timedelta(days=6, hours=14),
        "buildup_hours": 6,
        "tail_hours": 2,
        "added_tilt_deg": 2.4,
        "added_displacement_mm": 22.0,
        "vibration_multiplier": 6.0,
    },
    {
        "event_id": "EVT_02",
        "node_id": "NODE_05",
        "peak": START + pd.Timedelta(days=12, hours=3),
        "buildup_hours": 7,
        "tail_hours": 2,
        "added_tilt_deg": 3.6,
        "added_displacement_mm": 31.0,
        "vibration_multiplier": 7.5,
    },
    {
        "event_id": "EVT_03",
        "node_id": "NODE_07",
        "peak": START + pd.Timedelta(days=18, hours=20),
        "buildup_hours": 5,
        "tail_hours": 3,
        "added_tilt_deg": 1.8,
        "added_displacement_mm": 17.0,
        "vibration_multiplier": 4.5,
    },
]

for ep in episodes:
    ep["start"] = ep["peak"] - pd.Timedelta(hours=ep["buildup_hours"])
    ep["end"] = ep["peak"] + pd.Timedelta(hours=ep["tail_hours"])

# ---------------------------------------------------------------------------
# Build per-node time series
# ---------------------------------------------------------------------------
rows = []
for nid in NODE_IDS:
    p = node_params[nid]
    n = len(timestamps)

    elapsed_days = (timestamps - START).total_seconds().to_numpy() / 86400.0

    tilt = p["resting_tilt_deg"] + rng.normal(0, p["tilt_noise_std"], n)
    vib = np.abs(p["resting_vibration_rms"] + rng.normal(
        0, p["resting_vibration_rms"] * p["vibration_noise_std_frac"], n))
    disp = elapsed_days * p["background_mm_per_day"] + rng.normal(
        0, p["displacement_noise_std_mm"], n)
    crack = (rng.random(n) < 0.001).astype(int)  # rare baseline false positive

    df = pd.DataFrame({
        "timestamp": timestamps,
        "node_id": nid,
        "tilt_deg": tilt,
        "vibration_rms": vib,
        "displacement_mm": disp,
        "crack_signal": crack,
    })

    # Inject any episodes belonging to this node
    for ep in episodes:
        if ep["node_id"] != nid:
            continue
        t = df["timestamp"]

        in_buildup = (t >= ep["start"]) & (t <= ep["peak"])
        if in_buildup.any():
            frac = ((t[in_buildup] - ep["start"]) / (ep["peak"] - ep["start"])).astype(float)
            accel = frac ** 2  # accelerating (non-linear) precursor buildup
            df.loc[in_buildup, "tilt_deg"] += accel * ep["added_tilt_deg"]
            df.loc[in_buildup, "vibration_rms"] *= (1 + accel * (ep["vibration_multiplier"] - 1))
            df.loc[in_buildup, "displacement_mm"] += accel * ep["added_displacement_mm"]
            crack_prob = np.clip(accel ** 3 * 0.9, 0, 0.9)
            flips = rng.random(in_buildup.sum()) < crack_prob
            idx = df.index[in_buildup]
            df.loc[idx[flips], "crack_signal"] = 1
            # force crack signal on right at the peak sample itself
            df.loc[t == ep["peak"], "crack_signal"] = 1

        in_tail = (t > ep["peak"]) & (t <= ep["end"])
        if in_tail.any():
            tail_frac = ((ep["end"] - t[in_tail]) / (ep["end"] - ep["peak"])).astype(float)
            # tilt/displacement keep the full offset (permanent ground movement);
            # vibration and cracking relax back toward baseline over the tail
            df.loc[in_tail, "tilt_deg"] += ep["added_tilt_deg"]
            df.loc[in_tail, "displacement_mm"] += ep["added_displacement_mm"]
            df.loc[in_tail, "vibration_rms"] *= (1 + tail_frac * (ep["vibration_multiplier"] - 1))
            crack_prob = np.clip(tail_frac * 0.5, 0, 0.5)
            flips = rng.random(in_tail.sum()) < crack_prob
            idx = df.index[in_tail]
            df.loc[idx[flips], "crack_signal"] = 1

        after = t > ep["end"]
        if after.any():
            # permanent step offset persists for the rest of the record
            df.loc[after, "tilt_deg"] += ep["added_tilt_deg"]
            df.loc[after, "displacement_mm"] += ep["added_displacement_mm"]

    rows.append(df)

full = pd.concat(rows, ignore_index=True).sort_values(["timestamp", "node_id"]).reset_index(drop=True)
full["tilt_deg"] = full["tilt_deg"].round(4)
full["vibration_rms"] = full["vibration_rms"].round(4)
full["displacement_mm"] = full["displacement_mm"].round(3)
full["crack_signal"] = full["crack_signal"].astype(int)

full.to_csv(OUT_DIR / "simulated_mesh_data.csv", index=False)

# ---------------------------------------------------------------------------
# Events log
# ---------------------------------------------------------------------------
events_log = pd.DataFrame([{
    "event_id": ep["event_id"],
    "node_id": ep["node_id"],
    "start_timestamp": ep["start"],
    "subsidence_event_timestamp": ep["peak"],
    "end_timestamp": ep["end"],
    "buildup_hours": ep["buildup_hours"],
    "added_tilt_deg": ep["added_tilt_deg"],
    "added_displacement_mm": ep["added_displacement_mm"],
    "vibration_multiplier_at_peak": ep["vibration_multiplier"],
} for ep in episodes])
events_log.to_csv(OUT_DIR / "events_log.csv", index=False)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"Nodes: {len(NODE_IDS)} ({', '.join(NODE_IDS)})")
print(f"Sampling interval: {INTERVAL_MIN} min, duration: {DURATION_DAYS} days")
print(f"Total rows: {len(full)}")
print(f"Date range: {full['timestamp'].min()} -> {full['timestamp'].max()}")
print(f"Anomaly episodes: {len(episodes)}")
print(f"Rows with crack_signal == 1: {(full['crack_signal'] == 1).sum()}")
print("\nEvents log:")
print(events_log.to_string(index=False))
print("\nSample rows (baseline, NODE_01):")
print(full[full.node_id == "NODE_01"].head(5).to_string(index=False))
print("\nSample rows during EVT_01 buildup (NODE_02, around peak):")
peak1 = episodes[0]["peak"]
window = full[(full.node_id == "NODE_02") & (full.timestamp >= peak1 - pd.Timedelta(hours=2)) & (full.timestamp <= peak1 + pd.Timedelta(hours=1))]
print(window.to_string(index=False))
