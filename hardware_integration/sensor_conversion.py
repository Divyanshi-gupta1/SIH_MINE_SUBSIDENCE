"""
Raw Arduino/LoRa serial reading  ->  the physical units and scales the model was trained on.

    serial line --parse--> RawReading --convert--> ConvReading (g, dps, cm)
        --aggregate per node per sample_period_s--> WindowStats
        --sanity gate + zeroing--> model-frame sample {tilt_deg, vibration_rms, displacement_mm}

Nothing here calls the model. A reading/window that fails a check is DROPPED with a
reason code (returned to the caller, which counts it); it never becomes a model input.

Everything about the sketch is an assumption until confirmed with
`audit_format.py --probe` -- see FORMAT_AUDIT.md.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Optional

import numpy as np

from config import TRAIN, PipelineConfig
from feature_engine import vib_threshold

G_MS2 = 9.80665
ACCEL_LSB_PER_G = {2: 16384.0, 4: 8192.0, 8: 4096.0, 16: 2048.0}   # MPU-9250/6500, 16-bit
GYRO_LSB_PER_DPS = {250: 131.0, 500: 65.5, 1000: 32.8, 2000: 16.4}
DIST_TO_CM = {"cm": 1.0, "mm": 0.1, "m": 100.0, "us": 1.0 / 58.0}  # HC-SR04: cm = echo_us / 58
INT16_SATURATION = 32700

NaN = float("nan")


class CalibrationError(Exception):
    """Calibration data unusable (node moving, wrong units, ...). Never proceed silently."""


# ----------------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------------
_ALIASES = {
    "node": {"node", "nodeid", "node_id", "id", "n", "src"},
    "ax": {"ax", "accx", "acx", "accel_x", "acc_x", "a_x"},
    "ay": {"ay", "accy", "acy", "accel_y", "acc_y", "a_y"},
    "az": {"az", "accz", "acz", "accel_z", "acc_z", "a_z"},
    "gx": {"gx", "gyrx", "gyx", "gyro_x", "gyr_x", "g_x"},
    "gy": {"gy", "gyry", "gyy", "gyro_y", "gyr_y", "g_y"},
    "gz": {"gz", "gyrz", "gyz", "gyro_z", "gyr_z", "g_z"},
    "dist": {"dist", "distance", "dist_cm", "dist_mm", "range", "ultrasonic", "us", "echo", "d"},
    "vib": {"vib", "vib_rms", "vibration", "vibration_rms", "rms"},
    "temp": {"temp", "temperature", "temp_c", "ds18b20", "t"},
}
_ALIAS_LOOKUP = {a: canon for canon, names in _ALIASES.items() for a in names}
_SPLIT = re.compile(r"[,\s;\t]+")
# Receiver output visible in the supplied serial-monitor photograph, for example:
# -> [From NODE 1] Data: NODE_1|P:-75.39|R:-6.25|V:0.07 | RSSI: -33 dBm
# The payload may additionally contain E (HC-SR04 echo time in microseconds),
# D (already-converted distance), T (DS18B20 degrees C), and GX/GY/GZ (dps).
_LORA_MONITOR = re.compile(
    r"^\s*(?:-+>\s*)?\[\s*from\s+node\s+(?P<source>[^\]]+)\]\s*"
    r"data\s*:\s*(?P<payload>.*)$", re.IGNORECASE)
_LORA_FIELDS = {
    "p": "pitch", "pitch": "pitch", "r": "roll", "roll": "roll",
    "v": "vib", "vib": "vib", "vibration": "vib",
    "d": "dist", "dist": "dist", "distance": "dist",
    "e": "echo", "echo": "echo", "echo_us": "echo",
    "t": "temp", "temp": "temp", "temp_c": "temp",
    "gx": "gx", "gy": "gy", "gz": "gz",
}


def normalize_node(tok: str) -> str:
    tok = tok.strip()
    m = re.search(r"(\d+)\s*$", tok)
    return f"NODE_{int(m.group(1)):02d}" if m else tok.upper()


@dataclass
class RawReading:
    t: float
    node: str
    a: tuple            # accel as printed by the sketch (counts, g or m/s^2)
    g: tuple            # gyro as printed (NaN x3 if absent)
    dist: float         # ultrasonic as printed (NaN if absent)
    vib: float = NaN    # node-computed vibration RMS in g, if the sketch sends one
    temp_c: float = NaN # DS18B20; used only to compensate a raw HC-SR04 echo time


class LineParser:
    """CSV (optionally with a header line) or key=value lines. Strict: a line with the
    wrong number of fields is rejected, never guessed at."""

    def __init__(self, cfg: PipelineConfig):
        self.columns = list(cfg.columns)
        self.stats: Counter = Counter()

    def _make(self, t: float, vals: dict) -> Optional[RawReading]:
        try:
            node = normalize_node(vals["node"]) if "node" in vals else "NODE_01"
            f = lambda k: float(vals[k]) if k in vals else NaN
            r = RawReading(t=t, node=node, a=(f("ax"), f("ay"), f("az")),
                           g=(f("gx"), f("gy"), f("gz")), dist=f("dist"), vib=f("vib"))
        except (ValueError, KeyError):
            self.stats["non_numeric"] += 1
            return None
        flat = (*r.a, *r.g, r.dist)
        if any(math.isinf(x) for x in flat) or any(math.isnan(x) for x in r.a):
            self.stats["non_finite"] += 1
            return None
        return r

    def _make_pitch_roll(self, t: float, vals: dict, source: str) -> Optional[RawReading]:
        """Turn genuine MPU pitch/roll output into a unit gravity vector.

        This is a coordinate transform, not a fabricated sensor reading: the downstream
        conversion code needs a gravity vector solely to calculate inclination relative to
        the installation reference. Missing HC-SR04 data intentionally stays NaN and is
        rejected by calibration/model gating later in the pipeline.
        """
        try:
            pitch = math.radians(float(vals["pitch"]))
            roll = math.radians(float(vals["roll"]))
            node = normalize_node(vals.get("node", source))
            # Standard pitch/roll gravity components. Yaw is irrelevant to inclination.
            a = (-math.sin(pitch), math.sin(roll) * math.cos(pitch),
                 math.cos(roll) * math.cos(pitch))
            dist = float(vals["echo"]) if "echo" in vals else float(vals.get("dist", NaN))
            gyro = tuple(float(vals.get(k, NaN)) for k in ("gx", "gy", "gz"))
            r = RawReading(t=t, node=node, a=a, g=gyro, dist=dist,
                           vib=float(vals.get("vib", NaN)), temp_c=float(vals.get("temp", NaN)))
        except (KeyError, ValueError):
            self.stats["bad_lora_payload"] += 1
            return None
        if (not all(math.isfinite(x) for x in (*r.a, r.vib))
                or any(math.isinf(x) for x in (*r.g, r.dist, r.temp_c))):
            self.stats["non_finite"] += 1
            return None
        return r

    def _parse_lora_monitor(self, s: str, t: float) -> Optional[RawReading] | bool:
        """Parse the existing human-readable LoRa receiver envelope, if present.

        ``False`` means this is not that envelope and callers should continue with the
        CSV/key-value parser. ``None`` is a recognised but invalid LoRa packet.
        """
        m = _LORA_MONITOR.match(s)
        if not m:
            return False
        source, payload = m.group("source"), m.group("payload")
        vals = {"node": source}
        for field in payload.split("|"):
            field = field.strip()
            if not field or field.lower().startswith("rssi") or field.lower().startswith("snr"):
                continue
            if ":" not in field:
                # The current firmware emits NODE_1 as a bare first payload field.
                if re.fullmatch(r"(?:node[_ -]?)?\d+", field, re.IGNORECASE):
                    vals["node"] = field
                continue
            key, value = (part.strip() for part in field.split(":", 1))
            canon = _LORA_FIELDS.get(key.lower())
            if canon:
                vals[canon] = value
        if "pitch" not in vals or "roll" not in vals or "vib" not in vals:
            self.stats["lora_missing_prv"] += 1
            return None
        if normalize_node(vals["node"]) != normalize_node(source):
            self.stats["lora_node_mismatch"] += 1
            return None
        self.stats["lora_monitor"] += 1
        return self._make_pitch_roll(t, vals, source)

    def parse(self, line: str, t: float) -> Optional[RawReading]:
        s = line.strip()
        if not s or s.startswith(("#", "//")):
            return None
        lora = self._parse_lora_monitor(s, t)
        if lora is not False:
            return lora
        if "=" in s:
            vals = {}
            for tok in _SPLIT.split(s):
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    canon = _ALIAS_LOOKUP.get(k.strip().lower())
                    if canon:
                        vals[canon] = v
            if not {"ax", "ay", "az"} <= vals.keys():
                self.stats["bad_kv"] += 1
                return None
            return self._make(t, vals)

        toks = [x for x in _SPLIT.split(s) if x]
        canon_toks = [_ALIAS_LOOKUP.get(x.lower()) for x in toks]
        if sum(c is not None for c in canon_toks) >= 3 and not _looks_numeric(toks[1:]):
            self.columns = [c or f"_x{i}" for i, c in enumerate(canon_toks)]   # header line
            self.stats["header"] += 1
            return None
        if len(toks) != len(self.columns):
            self.stats["bad_field_count"] += 1
            return None
        return self._make(t, dict(zip(self.columns, toks)))


def _looks_numeric(toks) -> bool:
    try:
        [float(x) for x in toks]
        return True
    except ValueError:
        return False


# ----------------------------------------------------------------------------------
# Unit conversion
# ----------------------------------------------------------------------------------
@dataclass
class Scales:
    accel_per_g: float     # a_g = raw / accel_per_g
    gyro_per_dps: float
    dist_to_cm: float
    accel_is_counts: bool = False


@dataclass
class ConvReading:
    t: float
    a_g: np.ndarray
    gyro_dps: np.ndarray       # bias-corrected
    dist_cm: float             # NaN if invalid/out of range
    vib_g: float


def convert(r: RawReading, sc: Scales, cfg: PipelineConfig, gyro_bias=None, counters: Counter | None = None
            ) -> Optional[ConvReading]:
    """One raw reading -> physical units. Returns None (and counts why) if the accelerometer
    part is unusable; an unusable distance only blanks the distance."""
    if sc.accel_is_counts and max(abs(x) for x in r.a) >= INT16_SATURATION:
        if counters is not None:
            counters["reading_accel_saturated"] += 1
        return None
    a = np.asarray(r.a) / sc.accel_per_g
    gyro = np.asarray(r.g) / sc.gyro_per_dps
    if gyro_bias is not None:
        gyro = gyro - gyro_bias
    # HC-SR04's usual /58 conversion assumes roughly 20 C. If the sketch sends
    # raw echo duration and the measured DS18B20 temperature, use actual sound
    # speed. A pre-converted centimetre value cannot be corrected safely.
    if math.isnan(r.dist):
        d = NaN
    elif cfg.dist_unit == "us" and math.isfinite(r.temp_c):
        if not (-55.0 <= r.temp_c <= 125.0):
            if counters is not None:
                counters["reading_temperature_out_of_range"] += 1
            d = NaN
        else:
            d = r.dist * (331.3 + 0.606 * r.temp_c) / 20000.0
    else:
        d = r.dist * sc.dist_to_cm
    if not math.isnan(d) and not (cfg.dist_min_cm <= d <= cfg.dist_max_cm):
        if counters is not None:
            counters["reading_dist_out_of_range"] += 1     # 0 = no echo, >max = no target
        d = NaN
    return ConvReading(r.t, a, gyro, d, r.vib)


# ----------------------------------------------------------------------------------
# Aggregation
# ----------------------------------------------------------------------------------
class WindowAggregator:
    """Groups one node's readings into fixed windows floor(t / period). A window is emitted
    when the first reading of a later window arrives."""

    def __init__(self, period_s: float):
        self.period = period_s
        self.cur_idx: Optional[int] = None
        self.buf: list = []

    def add(self, r) -> list[tuple[int, list]]:
        idx = int(r.t // self.period)
        out = []
        if self.cur_idx is None:
            self.cur_idx = idx
        elif idx < self.cur_idx:
            return [(-1, [r])]            # late / out-of-order: caller drops it
        elif idx > self.cur_idx:
            out.append((self.cur_idx, self.buf))
            self.buf, self.cur_idx = [], idx
        self.buf.append(r)
        return out

    def flush(self, now: float) -> list[tuple[int, list]]:
        if self.cur_idx is not None and self.buf and now >= (self.cur_idx + 1) * self.period:
            out = [(self.cur_idx, self.buf)]
            self.buf, self.cur_idx = [], None
            return out
        return []


@dataclass
class WindowStats:
    idx: int
    t: float
    n_accel: int
    n_dist: int
    mean_a_g: np.ndarray
    gravity_g: float
    vib_g: float
    gyro_motion_dps: float
    dist_cm: float
    tilt_deg: float          # angle of the window-mean gravity vector from the install reference
    tilt_sigma_deg: float    # standard error of that estimate, from the in-window spread
    dist_se_mm: float        # standard error of the window-median distance, from in-window spread


def _angle_deg(u: np.ndarray, v: np.ndarray) -> float:
    return math.degrees(math.atan2(float(np.linalg.norm(np.cross(u, v))), float(np.dot(u, v))))


def summarize(idx: int, conv: list[ConvReading], g_mag: float, a_ref: np.ndarray) -> WindowStats:
    A = np.stack([c.a_g for c in conv])
    n = len(conv)
    mean_a = A.mean(axis=0)
    vibs = [c.vib_g for c in conv if not math.isnan(c.vib_g)]
    if len(vibs) == n:                               # sketch supplies RMS itself
        vib = math.sqrt(float(np.mean(np.square(vibs))))
    else:                                            # RMS of |a| about calibrated gravity
        vib = math.sqrt(float(np.mean((np.linalg.norm(A, axis=1) - g_mag) ** 2)))
    gy = np.stack([c.gyro_dps for c in conv])
    gyro_motion = float(np.nanmean(np.linalg.norm(gy, axis=1))) if not np.isnan(gy).all() else 0.0

    # tilt noise from the window itself: spread of the readings perpendicular to gravity.
    # Vibration inflates this, which is exactly when accel-derived tilt gets unreliable.
    ref = np.asarray(a_ref, dtype=float) / np.linalg.norm(a_ref)
    e1 = np.cross(ref, [1.0, 0.0, 0.0] if abs(ref[0]) < 0.9 else [0.0, 1.0, 0.0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(ref, e1)
    D = A - mean_a
    var_axis = 0.5 * (np.var(D @ e1, ddof=1) + np.var(D @ e2, ddof=1)) if n > 1 else 0.0
    tilt_sigma = math.degrees(math.sqrt(var_axis / n) / max(g_mag, 1e-9))

    d = np.array([c.dist_cm for c in conv if not math.isnan(c.dist_cm)])
    if len(d) >= 3:
        med = float(np.median(d))
        dist_se = 1.2533 * TRAIN.MAD_SCALE * float(np.median(np.abs(d - med))) * 10.0 / math.sqrt(len(d))
    else:
        med, dist_se = (float(np.median(d)) if len(d) else NaN), 0.0
    return WindowStats(
        idx=idx, t=float(np.mean([c.t for c in conv])), n_accel=n, n_dist=len(d),
        mean_a_g=mean_a, gravity_g=float(np.linalg.norm(mean_a)), vib_g=vib,
        gyro_motion_dps=gyro_motion, dist_cm=med, tilt_deg=_angle_deg(mean_a, ref),
        tilt_sigma_deg=tilt_sigma, dist_se_mm=dist_se)


# ----------------------------------------------------------------------------------
# Calibration (node installed, held still)
# ----------------------------------------------------------------------------------
@dataclass
class NodeCalibration:
    node: str
    accel_per_g: float
    accel_is_counts: bool
    gyro_per_dps: float
    dist_to_cm: float
    gyro_bias: list
    a_ref_g: list                 # mean gravity vector at install (tilt is measured from this)
    g_mag: float
    dist_ref_cm: float            # ultrasonic zero -> displacement 0
    quant_mm: float               # ultrasonic resolution seen in the data
    disp_sigma_mm: float
    deadband_mm: float
    tilt_deadband_deg: float      # tilt noise floor (angle from reference below this reads as 0)
    vib_median_g: float
    vib_scale: float              # g-RMS -> model vibration units
    vib_threshold_model: float    # spike threshold in model units (feeds NodeFeatureEngine)
    n_windows: int

    @property
    def scales(self) -> Scales:
        return Scales(self.accel_per_g, self.gyro_per_dps, self.dist_to_cm, self.accel_is_counts)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "NodeCalibration":
        return cls(**d)


def infer_accel_scale(raw_mags: np.ndarray, cfg: PipelineConfig) -> tuple[float, bool]:
    """(raw units per g, is_counts). 'auto' reads it off gravity: a still node must read 1 g."""
    m = float(np.median(raw_mags))
    if cfg.accel_units == "g":
        return 1.0, False
    if cfg.accel_units == "m/s2":
        return G_MS2, False
    if cfg.accel_units == "counts":
        return 32768.0 / cfg.accel_fs_g, True
    # auto
    if 0.7 <= m <= 1.3:
        return 1.0, False
    if 8.0 <= m <= 11.5:
        return G_MS2, False
    best = min(ACCEL_LSB_PER_G.values(), key=lambda c: abs(math.log(max(m, 1e-9) / c)))
    if m > 500 and abs(m / best - 1) < 0.25:
        return best, True
    raise CalibrationError(
        f"cannot infer accelerometer units: median |a| = {m:.4g} at rest is not ~1 (g), ~9.8 (m/s^2) "
        f"or ~2048-16384 (counts). Set accel_units / accel_fs_g explicitly.")


def calibrate(node: str, readings: list[RawReading], cfg: PipelineConfig,
              counters: Counter | None = None) -> tuple[NodeCalibration, list[dict]]:
    """Derive scale factors + zero references from a still-node recording.
    Returns (calibration, model-frame calibration samples used to warm up the feature engine)."""
    if len(readings) < cfg.min_readings_per_sample * 3:
        raise CalibrationError(f"only {len(readings)} readings")
    raw_a = np.array([r.a for r in readings], dtype=float)
    accel_per_g, is_counts = infer_accel_scale(np.linalg.norm(raw_a, axis=1), cfg)
    gyro_per_dps = 1.0 if cfg.gyro_units == "dps" else 32768.0 / cfg.gyro_fs_dps
    dist_to_cm = DIST_TO_CM[cfg.dist_unit]

    a_g = raw_a / accel_per_g
    g_mag = float(np.median(np.linalg.norm(a_g, axis=1)))
    if abs(g_mag - 1.0) > cfg.gravity_tol_g:
        raise CalibrationError(f"gravity reads {g_mag:.3f} g at rest (want 1 +/- {cfg.gravity_tol_g}): "
                               f"wrong accel units / full-scale range?")
    gy_raw = np.array([r.g for r in readings], dtype=float) / gyro_per_dps
    bias = np.nanmedian(gy_raw, axis=0) if not np.isnan(gy_raw).all() else np.zeros(3)
    if np.isnan(bias).any():
        bias = np.zeros(3)
    a_ref = np.median(a_g, axis=0)

    scales = Scales(accel_per_g, gyro_per_dps, dist_to_cm, is_counts)
    conv = [c for c in (convert(r, scales, cfg, bias, counters) for r in readings) if c is not None]

    agg = WindowAggregator(cfg.sample_period_s)
    groups = []
    for c in conv:
        groups += agg.add(c)
    groups += agg.flush(float("inf"))
    stats = [summarize(i, g, g_mag, a_ref) for i, g in groups if len(g) >= cfg.min_readings_per_sample]
    if len(stats) < max(5, int(0.6 * cfg.calib_windows)):
        raise CalibrationError(f"only {len(stats)} usable calibration windows "
                               f"(need >= {max(5, int(0.6 * cfg.calib_windows))}); "
                               f"readings/window may be below min_readings_per_sample")
    motion = float(np.median([s.gyro_motion_dps for s in stats]))
    if motion > cfg.calib_gyro_max_dps:
        raise CalibrationError(f"node is moving during calibration (gyro {motion:.1f} dps > {cfg.calib_gyro_max_dps})")
    tilts = np.array([s.tilt_deg for s in stats])
    tilt_sigma = float(np.median([s.tilt_sigma_deg for s in stats]))
    # steadiness is judged against the sensor's own noise: a noisy-but-still node has p95 ~ 2.5 sigma
    jitter_limit = max(cfg.calib_tilt_jitter_deg, 4.0 * tilt_sigma)
    if np.percentile(tilts, 95) > jitter_limit:
        raise CalibrationError(f"tilt not steady during calibration (p95 {np.percentile(tilts, 95):.2f} deg "
                               f"> {jitter_limit:.2f}; noise-only expectation ~{2.5 * tilt_sigma:.2f})")
    dist_stats = [s for s in stats if s.n_dist >= cfg.min_readings_per_sample]
    if len(dist_stats) < len(stats) * 0.6:
        raise CalibrationError("ultrasonic has too few valid readings during calibration "
                               f"({len(dist_stats)}/{len(stats)} windows): check wiring / dist_unit / range")

    d_med = np.array([s.dist_cm for s in dist_stats])
    dist_ref = float(np.median(d_med))
    sigma_mm = float(np.median(np.abs(d_med - dist_ref))) * TRAIN.MAD_SCALE * 10.0
    raw_d = np.array(sorted({round(c.dist_cm, 4) for c in conv if not math.isnan(c.dist_cm)}))
    gaps = np.diff(raw_d)
    quant_mm = float(gaps[gaps > 1e-6].min() * 10.0) if (gaps > 1e-6).any() else 0.0
    deadband = max(cfg.noise_k_disp * sigma_mm, quant_mm, cfg.disp_min_deadband_mm)
    tilt_db = max(cfg.tilt_min_deadband_deg, cfg.noise_k_tilt * tilt_sigma, 2.0 * float(np.percentile(tilts, 95)))

    vib_g = np.array([s.vib_g for s in stats])
    vib_med = float(np.median(vib_g))
    vib_scale = TRAIN.VIB_BASELINE_MEDIAN / max(vib_med, 1e-6) if cfg.vib_normalization == "baseline" else 1.0
    vib_model = vib_g * vib_scale
    # training-rule threshold, with a floor at 1.5x median: training thresholds sit at 1.6-2.2x
    # median, and a quantised/degenerate MAD would otherwise put the threshold ON the median
    # and make vibration_duration climb forever.
    thr = max(vib_threshold(vib_model), 1.5 * float(np.median(vib_model)))

    cal = NodeCalibration(
        node=node, accel_per_g=accel_per_g, accel_is_counts=is_counts, gyro_per_dps=gyro_per_dps,
        dist_to_cm=dist_to_cm, gyro_bias=bias.tolist(), a_ref_g=a_ref.tolist(), g_mag=g_mag,
        dist_ref_cm=dist_ref, quant_mm=quant_mm, disp_sigma_mm=sigma_mm, deadband_mm=deadband,
        tilt_deadband_deg=tilt_db,
        vib_median_g=vib_med, vib_scale=vib_scale, vib_threshold_model=thr, n_windows=len(stats))

    seed = []
    for s in stats:
        smp, _ = make_sample(s, cal, cfg, last_disp_mm=None, check_step=False)
        if smp is not None:
            seed.append(smp)
    return cal, seed


# ----------------------------------------------------------------------------------
# Sanity gate + model-frame sample
# ----------------------------------------------------------------------------------
def make_sample(s: WindowStats, cal: NodeCalibration, cfg: PipelineConfig,
                last_disp_mm: Optional[float], check_step: bool = True
                ) -> tuple[Optional[dict], Optional[str]]:
    """WindowStats -> ({tilt, vib, disp (model frame), diagnostics}, None)
    or (None, reason) when the window is physically impossible / unusable."""
    if s.n_accel < cfg.min_readings_per_sample:
        return None, "too_few_readings"
    if s.n_dist < cfg.min_readings_per_sample or math.isnan(s.dist_cm):
        return None, "no_valid_distance"
    if abs(s.gravity_g - 1.0) > cfg.gravity_tol_g:
        return None, "gravity_magnitude_bad"          # shaken/dropped/saturated/wrong scale
    if s.gyro_motion_dps > cfg.gyro_motion_max_dps:
        return None, "node_moving"                     # being handled, not ground movement
    if not (0.0 <= s.tilt_deg <= cfg.tilt_max_deg):
        return None, "tilt_out_of_range"               # > 90 deg: flipped node / bad axis
    if not math.isfinite(s.vib_g) or s.vib_g < 0:
        return None, "vibration_invalid"

    # Noise floors, widened by this window's own scatter: vibration shakes the accelerometer
    # AND the ultrasonic mount, so tilt/distance estimates get noisier exactly when a
    # vibration-only event happens. A deviation must clear the noise to count as movement.
    tilt_db = max(cal.tilt_deadband_deg, cfg.noise_k_tilt * s.tilt_sigma_deg)
    disp_db = max(cal.deadband_mm, cfg.noise_k_disp * s.dist_se_mm)

    disp_raw = cfg.displacement_sign * (s.dist_cm - cal.dist_ref_cm) * 10.0
    neg_tol = cfg.disp_neg_tol_mm if cfg.disp_neg_tol_mm is not None else max(2 * disp_db, 2.0)
    if disp_raw < -neg_tol:
        return None, "negative_displacement"          # ground cannot rise / target moved / wrong sign
    if disp_raw > cfg.disp_max_mm:
        return None, "displacement_out_of_range"
    if check_step and last_disp_mm is not None and abs(disp_raw - last_disp_mm) > cfg.disp_max_step_mm:
        return None, "displacement_jump"

    # soft-threshold at the noise floor: +/- noise reads exactly 0 instead of feeding a model
    # trained on 0.02 deg / 0.05 mm noise (its trees split at ~0.1 deg / 0.5 mm)
    tilt_model = cfg.tilt_rest_offset_deg + max(0.0, s.tilt_deg - tilt_db)
    disp_model = max(0.0, disp_raw - disp_db)
    return {
        "t": s.t, "window_idx": s.idx,
        "tilt": tilt_model,
        "vib": s.vib_g * cal.vib_scale,
        "disp": disp_model,
        "diag": {"tilt_raw_deg": round(s.tilt_deg, 4), "tilt_db_deg": round(tilt_db, 4),
                 "vib_g": round(s.vib_g, 6), "disp_raw_mm": round(disp_raw, 3), "disp_db_mm": round(disp_db, 3),
                 "dist_cm": round(s.dist_cm, 3), "gyro_dps": round(s.gyro_motion_dps, 2),
                 "gravity_g": round(s.gravity_g, 4), "n": s.n_accel},
        "disp_raw_mm": disp_raw,
    }, None
