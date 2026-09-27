"""
Adds 2 "decoy" false-alarm episodes (vibration spikes that are NOT
subsidence precursors -- e.g. earthquake / nearby blasting) to the
existing synthetic mesh dataset, plus 3 derived features to help a model
later distinguish true precursors from harmless vibration spikes.

SAFETY: this script loads the EXISTING simulated_mesh_data.csv and only
overwrites vibration_rms/crack_signal cells on the specific decoy rows
(2 nodes, a handful of timestamps each). Every other cell -- including
all 3 real subsidence episodes and their rows -- is left byte-identical.
Row order is preserved exactly as in the original file.

Decoy nodes chosen: NODE_01, NODE_04 -- neither appears in the existing
3 real episodes (events_log.csv: NODE_02, NODE_05, NODE_07).
"""
import numpy as np
import pandas as pd
from pathlib import Path

DIR = Path(r"C:\Users\Krishna\Desktop\sih-mine-subsidence\sih-mine-subsidence\synthetic")
DATA_PATH = DIR / "simulated_mesh_data.csv"
EVENTS_PATH = DIR / "events_log.csv"

rng = np.random.default_rng(42)

# ---------------------------------------------------------------------------
# Load existing data, remember original row order
# ---------------------------------------------------------------------------
df = pd.read_csv(DATA_PATH, parse_dates=["timestamp"])
df["_orig_order"] = np.arange(len(df))

# ---------------------------------------------------------------------------
# Decoy episode definitions
# ---------------------------------------------------------------------------
# Each spike is a list of (timestamp, multiplier) applied to that row's
# EXISTING vibration_rms value (so the natural sensor noise shape is kept,
# just scaled up) -- tilt_deg and displacement_mm are left untouched.
decoys = [
    {
        "event_id": "EVT_04",
        "node_id": "NODE_01",
        "event_type": "decoy_seismic",
        "label": "earthquake-like (sharp, short)",
        "spike": [
            (pd.Timestamp("2026-08-04 08:45:00"), 3.0),
            (pd.Timestamp("2026-08-04 09:00:00"), 9.0),   # peak
            (pd.Timestamp("2026-08-04 09:15:00"), 2.5),
        ],
        "peak_timestamp": pd.Timestamp("2026-08-04 09:00:00"),
    },
    {
        "event_id": "EVT_05",
        "node_id": "NODE_04",
        "event_type": "decoy_seismic",
        "label": "blasting-like (broader, still short)",
        "spike": [
            (pd.Timestamp("2026-08-15 10:45:00"), 3.0),
            (pd.Timestamp("2026-08-15 11:00:00"), 6.5),   # peak
            (pd.Timestamp("2026-08-15 11:15:00"), 5.0),
            (pd.Timestamp("2026-08-15 11:30:00"), 2.5),
        ],
        "peak_timestamp": pd.Timestamp("2026-08-15 11:00:00"),
    },
]

decoy_row_keys = []  # (node_id, timestamp) touched, for the summary count

for ep in decoys:
    node = ep["node_id"]
    for ts, mult in ep["spike"]:
        mask = (df["node_id"] == node) & (df["timestamp"] == ts)
        if not mask.any():
            raise ValueError(f"Timestamp {ts} not found for {node} -- check the time grid.")
        df.loc[mask, "vibration_rms"] = df.loc[mask, "vibration_rms"] * mult
        df.loc[mask, "crack_signal"] = 0  # decoys must never trip the crack sensor
        decoy_row_keys.append((node, ts))
    # tilt_deg and displacement_mm are intentionally left untouched for
    # these rows -- requirement 3: no accelerating trend, no permanent
    # offset. Rows before/after the spike are also untouched -- requirement
    # 5: vibration returns to baseline immediately, no relaxation tail.

df["vibration_rms"] = df["vibration_rms"].round(4)

# ---------------------------------------------------------------------------
# Derived features (computed per node, over the FULL updated series)
# ---------------------------------------------------------------------------
WINDOW = 8          # 8 samples * 15 min = 2 hours
PERSIST_N = 8        # look 2 hours after a spike start
PERSIST_LOOKBACK = 4  # 1 hour of pre-spike baseline
PERSIST_THRESHOLD_MM = 0.5  # real episodes add 17-31mm; decoys add ~0mm

df = df.sort_values(["node_id", "timestamp"]).reset_index(drop=True)

vib_duration = pd.Series(index=df.index, dtype="int64")
tilt_vib_corr = pd.Series(index=df.index, dtype="float64")
disp_persist = pd.Series(0, index=df.index, dtype="int64")

for node, g in df.groupby("node_id", sort=False):
    idx = g.index
    vib = g["vibration_rms"]
    tilt = g["tilt_deg"]
    disp = g["displacement_mm"]

    # Robust per-node baseline threshold: median + 4x scaled MAD.
    med = vib.median()
    mad = (vib - med).abs().median() * 1.4826
    threshold = med + 4 * mad

    # vibration_duration: length of the current consecutive run of samples
    # above threshold (resets to 0 as soon as a sample drops below it).
    above = vib > threshold
    run_id = (~above).cumsum()
    streak = above.groupby(run_id).cumcount() + 1
    streak = streak.where(above, 0)
    vib_duration.loc[idx] = streak.to_numpy()

    # tilt_vibration_correlation: rolling Pearson correlation between tilt
    # and vibration over a 2-hour window. NaN for the first WINDOW-1
    # samples (not enough history yet) -> filled with 0 (i.e. "no evidence
    # of co-movement yet"), not treated as a strong signal either way.
    corr = tilt.rolling(WINDOW).corr(vib).fillna(0.0)
    tilt_vib_corr.loc[idx] = corr.to_numpy()

    # displacement_persistence: for each rising-edge spike start (above
    # threshold now, below on the previous sample), compare mean
    # displacement in the PERSIST_N samples after the spike to the mean
    # displacement in the PERSIST_LOOKBACK samples before it. If it's
    # meaningfully higher, flag every row in [spike_start, spike_start +
    # PERSIST_N] as persistent (1); otherwise 0. All other rows stay 0.
    above_arr = above.to_numpy()
    disp_arr = disp.to_numpy()
    n = len(g)
    rising_edges = np.where(above_arr & ~np.r_[False, above_arr[:-1]])[0]
    flag = np.zeros(n, dtype="int64")
    for i in rising_edges:
        pre_start = max(0, i - PERSIST_LOOKBACK)
        pre_baseline = disp_arr[pre_start:i].mean() if i > pre_start else disp_arr[i]
        future_end = min(n, i + PERSIST_N + 1)
        future_val = disp_arr[future_end - 1]
        persistent = int((future_val - pre_baseline) > PERSIST_THRESHOLD_MM)
        flag[i:future_end] = np.maximum(flag[i:future_end], persistent)
    disp_persist.loc[idx] = flag

df["vibration_duration"] = vib_duration
df["tilt_vibration_correlation"] = tilt_vib_corr.round(4)
df["displacement_persistence"] = disp_persist

# restore original row order (timestamp, node_id)
df = df.sort_values("_orig_order").drop(columns="_orig_order").reset_index(drop=True)

df.to_csv(DATA_PATH, index=False)

# ---------------------------------------------------------------------------
# Update events_log.csv
# ---------------------------------------------------------------------------
events = pd.read_csv(EVENTS_PATH)
events["event_type"] = "subsidence_precursor"  # the 3 existing real episodes

new_rows = []
for ep in decoys:
    spikes = ep["spike"]
    start_ts = spikes[0][0]
    end_ts = spikes[-1][0]
    duration_hours = round((end_ts - start_ts).total_seconds() / 3600 + 0.25, 2)  # + one sample width
    max_mult = max(m for _, m in spikes)
    new_rows.append({
        "event_id": ep["event_id"],
        "node_id": ep["node_id"],
        "start_timestamp": start_ts,
        "subsidence_event_timestamp": ep["peak_timestamp"],  # peak of the SPIKE, not a real subsidence event -- see README
        "end_timestamp": end_ts,
        "buildup_hours": duration_hours,  # total spike duration for decoys (no separate buildup phase) -- see README
        "added_tilt_deg": 0.0,
        "added_displacement_mm": 0.0,
        "vibration_multiplier_at_peak": max_mult,
        "event_type": ep["event_type"],
    })

events = pd.concat([events, pd.DataFrame(new_rows)], ignore_index=True)
events.to_csv(EVENTS_PATH, index=False)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"Total rows in simulated_mesh_data.csv: {len(df)}")
print(f"Decoy-affected rows (vibration_rms modified): {len(decoy_row_keys)}")
for node, ts in decoy_row_keys:
    print(f"  {node} @ {ts}")
print(f"Rows with crack_signal == 1: {(df['crack_signal'] == 1).sum()}")
print("\nevents_log.csv event_type distribution:")
print(events["event_type"].value_counts().to_string())
print("\nFull events_log.csv:")
print(events.to_string(index=False))
print("\nSample: decoy NODE_01 spike window (EVT_04):")
w = df[(df.node_id == "NODE_01") & (df.timestamp >= "2026-08-04 08:15:00") & (df.timestamp <= "2026-08-04 09:45:00")]
print(w.to_string(index=False))
print("\nSample: decoy NODE_04 spike window (EVT_05):")
w2 = df[(df.node_id == "NODE_04") & (df.timestamp >= "2026-08-15 10:00:00") & (df.timestamp <= "2026-08-15 12:00:00")]
print(w2.to_string(index=False))
