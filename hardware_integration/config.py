"""
Central config for the hardware -> model bridge.

Two kinds of constants live here:

  TRAIN  -- values copied verbatim from the synthetic-data pipeline
            (synthetic/extend_dataset_v2.py, synthetic/add_tilt_baseline_feature.py).
            Changing these means the streaming features no longer match what
            the model was trained on. Don't, unless the model is retrained.

  PipelineConfig -- everything that depends on the actual hardware / sketch
            (serial column order, sensor units, sample period, thresholds).
            Override per deployment with a JSON file (see README.md).
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
MODEL_PATH = PROJECT_ROOT / "model" / "random_forest_model_v6.joblib"
TRAIN_CSV = PROJECT_ROOT / "synthetic" / "simulated_mesh_data_v6_with_external.csv"
REPORT_DIR = HERE / "reports"

# Order the RF was fitted with (model.feature_names_in_). Re-checked at load time.
FEATURES = (
    "tilt_deg", "vibration_rms", "displacement_mm", "crack_signal",
    "vibration_duration", "tilt_vibration_correlation", "displacement_persistence",
    "tilt_deviation_from_node_baseline",
)


class TRAIN:
    """Constants of the training-time feature pipeline (one model sample = 15 min)."""
    WINDOW = 8                    # rolling-corr window, samples
    PERSIST_N = 8                 # displacement_persistence: samples after a spike start
    PERSIST_LOOKBACK = 4          # ... samples used for the pre-spike displacement mean
    PERSIST_THRESHOLD_MM = 0.5
    SAMPLES_PER_7D = 672          # tilt-baseline rolling-median length, samples
    TILT_DEV_MIN_PERIODS = 4
    VIB_K = 4.0                   # vib threshold = median + K * 1.4826 * MAD
    MAD_SCALE = 1.4826
    # Resting levels of the *normal* class, used to put a freshly-zeroed real node
    # on the same footing as a day-0 training node (see FORMAT_AUDIT.md §3).
    VIB_BASELINE_MEDIAN = 0.031   # median vibration_rms of normal rows (0.0309)
    TILT_REST_DEG = 0.175         # midpoint of generator's resting tilt U(0.05, 0.30)
    SAMPLE_PERIOD_S = 900         # training cadence


@dataclass
class PipelineConfig:
    # ---- serial line format (ASSUMED -- confirm with audit_format.py --probe) ----
    columns: tuple = ("node", "ax", "ay", "az", "gx", "gy", "gz", "dist")
    accel_units: str = "auto"      # auto | g | m/s2 | counts
    accel_fs_g: float = 2.0        # only used when accel_units == "counts"
    gyro_units: str = "counts"     # counts | dps  (scale can't be inferred like accel's; only used to
    gyro_fs_dps: float = 250.0     # detect "node being handled", so a wrong FS is a mild error)
    dist_unit: str = "cm"          # cm | mm | m | us (HC-SR04 echo width)
    baud: int = 115200

    # ---- timing: one model sample = one aggregation window per node ----
    sample_period_s: float = 2.0
    persist_window_s: float = 8.0          # 5-10 s per requirement
    min_readings_per_sample: int = 3
    max_missing_windows: int = 1           # LoRa loss tolerated inside a streak
    fault_after_dropped_windows: int = 15  # consecutive drops -> SENSOR_FAULT

    # ---- calibration (node held still) ----
    calib_windows: int = 20
    calib_gyro_max_dps: float = 5.0
    calib_tilt_jitter_deg: float = 0.5     # window-to-window direction spread

    # ---- physical sanity limits (drop, never feed the model) ----
    tilt_max_deg: float = 90.0
    gravity_tol_g: float = 0.20            # |mean accel| must be 1 g +/- this
    gyro_motion_max_dps: float = 15.0      # node being handled
    dist_min_cm: float = 2.0
    dist_max_cm: float = 400.0
    disp_max_mm: float = 500.0
    disp_max_step_mm: float = 50.0         # per sample; ground cannot jump this fast
    disp_min_deadband_mm: float = 1.0
    tilt_min_deadband_deg: float = 0.05
    noise_k_tilt: float = 5.0              # deadband = k x sensor noise sigma (Rayleigh tail: 5 sigma ~ 4e-6/sample)
    noise_k_disp: float = 4.0
    disp_neg_tol_mm: float | None = None   # None -> max(2*deadband, 2 mm)
    displacement_sign: int = 1             # +1: distance grows == subsidence

    # ---- guardrails ----
    confirm_confidence: float = 0.70
    clear_n: int = 3                       # non-risk samples that release a latched alert
    normal_class: str = "normal"
    decoy_classes: tuple = ("decoy_seismic",)   # benign anomalies; every other non-normal class is "risk"

    # ---- unit/scale mapping into the model's frame ----
    vib_normalization: str = "baseline"    # baseline | none
    tilt_rest_offset_deg: float = TRAIN.TILT_REST_DEG

    @property
    def persist_n(self) -> int:
        return max(2, math.ceil(self.persist_window_s / self.sample_period_s))

    @classmethod
    def profile(cls, name: str) -> "PipelineConfig":
        if name == "bench":
            return cls()
        if name == "field":
            # Same cadence as the training data: 1 sample / 15 min. Persistence of 3
            # samples = 45 min -- the 5-10 s window only makes sense on the bench.
            return cls(sample_period_s=900.0, persist_window_s=2700.0,
                       min_readings_per_sample=10, calib_windows=8)
        raise ValueError(f"unknown profile {name!r} (bench | field)")

    @classmethod
    def load(cls, path: str | Path | None, profile: str = "bench") -> "PipelineConfig":
        cfg = cls.profile(profile)
        if path:
            data = json.loads(Path(path).read_text())
            known = {f.name for f in fields(cls)}
            unknown = set(data) - known
            if unknown:
                raise ValueError(f"unknown config keys: {sorted(unknown)}")
            if "columns" in data:
                data["columns"] = tuple(data["columns"])
            if "decoy_classes" in data:
                data["decoy_classes"] = tuple(data["decoy_classes"])
            for k, v in data.items():
                setattr(cfg, k, v)
        return cfg

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=list)
