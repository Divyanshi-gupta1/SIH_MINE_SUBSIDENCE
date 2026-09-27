"""
Streaming (one-sample-at-a-time) re-implementation of the 4 derived features the
model was trained with. Logic mirrors, line for line:

  vibration_duration / tilt_vibration_correlation / displacement_persistence
      -> synthetic/extend_dataset_v2.py  (also external/engineer_v2_features.py)
  tilt_deviation_from_node_baseline
      -> synthetic/add_tilt_baseline_feature.py

The batch pipeline computes these with pandas over a node's whole history; here the
same numbers must come out sample by sample, causally. test_pipeline_units.py
replays training rows through this class and diffs against the CSV columns.

A "sample" is whatever the caller decides one model sample is (15 min in training;
`sample_period_s` on the bench) -- every window below is counted in samples.
"""
from __future__ import annotations

from collections import deque

import numpy as np

from config import FEATURES, TRAIN


def vib_threshold(vib_history) -> float:
    """Per-node robust spike threshold: median + 4 * 1.4826 * MAD (training definition)."""
    v = np.asarray(vib_history, dtype=float)
    med = float(np.median(v))
    mad = float(np.median(np.abs(v - med))) * TRAIN.MAD_SCALE
    return med + TRAIN.VIB_K * mad


class NodeFeatureEngine:
    def __init__(self, threshold: float):
        self.threshold = float(threshold)
        self._tilt_hist = deque(maxlen=TRAIN.SAMPLES_PER_7D)
        self._win_tilt = deque(maxlen=TRAIN.WINDOW)
        self._win_vib = deque(maxlen=TRAIN.WINDOW)
        self._prev_disp = deque(maxlen=TRAIN.PERSIST_LOOKBACK)
        self._streak = 0
        self._prev_above = False
        self._j = 0
        self._last_spike_start = None
        self._pre_baseline = 0.0

    def update(self, tilt: float, vib: float, disp: float) -> dict:
        above = vib > self.threshold

        # vibration_duration: consecutive samples above threshold, reset on drop-out.
        # QUIRK REPLICATED ON PURPOSE: the training code is
        #   run_id = (~above).cumsum(); streak = above.groupby(run_id).cumcount() + 1
        # in which the below-threshold row that precedes a run belongs to that run's
        # group, so a run counts 2, 3, 4, ... (not 1, 2, 3) -- except a run that opens
        # the series (no preceding row), which counts 1, 2, 3. The model was fitted on
        # these values (decoys: length-4 spike -> max 5), so the stream must match.
        if not above:
            self._streak = 0
        elif self._prev_above:
            self._streak += 1
        else:
            self._streak = 2 if self._j > 0 else 1

        # tilt_vibration_correlation: rolling 8-sample Pearson; incomplete/degenerate -> 0.0
        self._win_tilt.append(tilt)
        self._win_vib.append(vib)
        corr = 0.0
        if len(self._win_tilt) == TRAIN.WINDOW:
            x = np.asarray(self._win_tilt)
            y = np.asarray(self._win_vib)
            sx, sy = x.std(), y.std()
            if sx > 1e-12 and sy > 1e-12:
                corr = float(np.mean((x - x.mean()) * (y - y.mean())) / (sx * sy))

        # displacement_persistence (causal): armed at a spike's rising edge
        if above and not self._prev_above:
            self._pre_baseline = float(np.mean(self._prev_disp)) if self._prev_disp else disp
            self._last_spike_start = self._j
        if (self._last_spike_start is not None
                and (self._j - self._last_spike_start) <= TRAIN.PERSIST_N):
            persist = int((disp - self._pre_baseline) > TRAIN.PERSIST_THRESHOLD_MM)
        else:
            persist = 0

        # tilt_deviation_from_node_baseline: tilt - trailing-median (incl. current), warm-up 0
        self._tilt_hist.append(tilt)
        if len(self._tilt_hist) >= TRAIN.TILT_DEV_MIN_PERIODS:
            tilt_dev = tilt - float(np.median(self._tilt_hist))
        else:
            tilt_dev = 0.0

        self._prev_above = above
        self._prev_disp.append(disp)
        self._j += 1

        return {
            "tilt_deg": round(tilt, 4),
            "vibration_rms": round(vib, 4),
            "displacement_mm": round(disp, 3),
            # No crack sensor on the 3-node hardware. RF importance 0.9 %; forcing it
            # to 0 leaves the v6 test-set confusion matrix unchanged (FORMAT_AUDIT.md).
            "crack_signal": 0,
            "vibration_duration": self._streak,
            "tilt_vibration_correlation": round(corr, 4),
            "displacement_persistence": persist,
            "tilt_deviation_from_node_baseline": round(tilt_dev, 4),
        }

    @staticmethod
    def row(features: dict) -> list:
        return [features[k] for k in FEATURES]
