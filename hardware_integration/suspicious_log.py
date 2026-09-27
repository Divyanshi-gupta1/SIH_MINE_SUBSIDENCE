"""
Save only the suspicious predictions to a CSV. Normal readings are never written.

Real hardware and replay/simulation are logged to two different files in two different folders, never mixed:
    logs/real/suspicious_readings.csv      readings from a real serial device (COM5, /dev/ttyUSB0)
    logs/replay/suspicious_readings.csv    replayed logs and the simulator (fake_serial.py, socket://, loop://)
log_path_for(port) picks the right one. There is deliberately no default that points at "real": a caller that
does not say where its data comes from lands in logs/replay/. The old single logs/suspicious_readings.csv is no
longer written by this module.

Pure logging: it reads the pipeline's output and never changes it (no model, guardrail or conversion logic
is touched). One row is appended per model sample that is suspicious, meaning either
  * the predicted class is not "normal" (a vibration-only decoy counts: it is a non-normal prediction), or
  * the guardrail status is POSSIBLE or CONFIRMED.

    timestamp, node_id, raw_serial_line, tilt, vibration, displacement, predicted_class, confidence, guardrail_status

  timestamp        wall-clock time the row was written (local, ISO 8601, ms)
  node_id          e.g. NODE_02
  raw_serial_line  the last serial line received from that node inside the window that made the prediction
                   (a prediction is built from ~10 lines, so no single line "produced" it)
  tilt, vibration, displacement   the model-frame values the model was fed for this sample (degrees, g scale, mm),
                   i.e. after unit conversion and the noise-floor gate, so the row explains the prediction
  predicted_class, confidence     the model's top class and its probability
  guardrail_status NORMAL | DECOY | POSSIBLE | CONFIRMED (per sample; guardrails.py)

Hook it into a live pipeline with one call:      pipe = attach(pipe, log_path_for(port))
Or call the function yourself after each output: log_if_suspicious(sample, raw_line, log_path_for(port))

The folder and file are created on first use, rows are appended (never overwritten), and a failed write
(for example the CSV is open in Excel on Windows) never raises into the live loop: it warns once on stderr,
keeps the rows and retries on the next suspicious sample.
"""
from __future__ import annotations

import atexit
import csv
import sys
import threading
from datetime import datetime
from pathlib import Path

from config import HERE, PipelineConfig
from sensor_conversion import LineParser

REAL_LOG_PATH = HERE / "logs" / "real" / "suspicious_readings.csv"
REPLAY_LOG_PATH = HERE / "logs" / "replay" / "suspicious_readings.csv"
COLUMNS = ("timestamp", "node_id", "raw_serial_line", "tilt", "vibration", "displacement",
           "predicted_class", "confidence", "guardrail_status")
SUSPICIOUS_STATUSES = ("POSSIBLE", "CONFIRMED")
MAX_PENDING = 1000          # rows held in memory while the file cannot be written


def log_path_for(port: str | None) -> Path:
    """Where suspicious rows for this input go. Only a plain serial device name (COM5, \\\\.\\COM12,
    /dev/ttyUSB0) is real hardware -> logs/real/. No port (a --replay file) and any pyserial URL
    (socket://, loop://, rfc2217://, ...) -> logs/replay/: URLs are how the simulator is reached, and when in
    doubt the real folder must stay clean."""
    return REAL_LOG_PATH if port and "://" not in port else REPLAY_LOG_PATH


def is_suspicious(sample, normal_class: str = "normal") -> bool:
    """True if the prediction is not `normal` or the guardrail is in POSSIBLE / CONFIRMED."""
    return sample.top_class != normal_class or sample.status in SUSPICIOUS_STATUSES


def to_row(sample, raw_line: str = "", now: datetime | None = None) -> dict:
    f = sample.features
    return {
        "timestamp": (now or datetime.now()).isoformat(timespec="milliseconds"),
        "node_id": sample.node,
        "raw_serial_line": raw_line,
        "tilt": f["tilt_deg"],
        "vibration": f["vibration_rms"],
        "displacement": f["displacement_mm"],
        "predicted_class": sample.top_class,
        "confidence": round(sample.top_p, 4),
        "guardrail_status": sample.status,
    }


class SuspiciousLog:
    def __init__(self, path=REPLAY_LOG_PATH, normal_class: str = "normal", cfg: PipelineConfig | None = None):
        self.path = Path(path)
        self.normal_class = normal_class
        self.cfg = cfg or PipelineConfig()
        self.n_written = 0
        self._parser = LineParser(self.cfg)      # own instance: sees the same lines, never touches the pipeline's counters
        self._lines: dict[str, dict[int, str]] = {}   # node -> window index -> last raw line in that window
        self._pending: list[dict] = []
        self._lock = threading.Lock()
        self._warned = False

    # ---------------- raw-line memory ----------------
    def observe(self, t: float, line: str):
        """Remember the latest raw line per node per window. Call for every line fed to the pipeline."""
        r = self._parser.parse(line, t)
        if r is None:
            return
        idx = int(t // self.cfg.sample_period_s)
        seen = self._lines.setdefault(r.node, {})
        seen[idx] = line.strip()
        for k in [k for k in seen if k < idx - 3]:
            del seen[k]

    def raw_line_for(self, sample) -> str:
        return self._lines.get(sample.node, {}).get(sample.window_idx, "")

    # ---------------- logging ----------------
    def log(self, sample, raw_line: str | None = None) -> bool:
        """Append a row if `sample` is suspicious. Returns True if a row was queued for writing."""
        if not is_suspicious(sample, self.normal_class):
            return False
        raw = self.raw_line_for(sample) if raw_line is None else raw_line
        with self._lock:
            self._pending.append(to_row(sample, raw))
            del self._pending[:-MAX_PENDING]
        self.flush()
        return True

    def log_all(self, samples) -> int:
        return sum(self.log(s) for s in samples)

    def flush(self):
        with self._lock:
            if not self._pending:
                return
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                new_file = not self.path.exists() or self.path.stat().st_size == 0
                with open(self.path, "a", newline="", encoding="utf-8") as fh:
                    w = csv.DictWriter(fh, fieldnames=COLUMNS)
                    if new_file:
                        w.writeheader()
                    w.writerows(self._pending)
                self.n_written += len(self._pending)
                self._pending = []
                self._warned = False
            except OSError as e:
                self.warn(f"cannot write {self.path}: {e}. Keeping {len(self._pending)} row(s) and retrying "
                          f"(close the file if it is open in another program)")

    def warn(self, msg: str):
        if not self._warned:
            print(f"suspicious_log: {msg}", file=sys.stderr)
            self._warned = True


# ------------------------------------------------------------------------------------
_default_logs: dict[str, SuspiciousLog] = {}


def log_if_suspicious(sample, raw_line: str = "", path=REPLAY_LOG_PATH, normal_class: str = "normal") -> bool:
    """Call after every prediction. Writes a CSV row if the sample is suspicious, does nothing otherwise."""
    key = str(Path(path))
    lg = _default_logs.get(key)
    if lg is None or lg.normal_class != normal_class:
        lg = _default_logs[key] = SuspiciousLog(path, normal_class)
    return lg.log(sample, raw_line)


def attach(pipe, path=REPLAY_LOG_PATH):
    """Hook a MineGuardPipeline: every SampleOutput it returns from feed_line() / flush() is passed to the
    logger. The outputs are returned unchanged, and a logging error can never reach the live loop."""
    if hasattr(pipe, "suspicious_log"):
        return pipe                                          # already attached, do not log twice
    lg = SuspiciousLog(path, pipe.cfg.normal_class, pipe.cfg)
    feed_line, flush = pipe.feed_line, pipe.flush

    def guarded(fn, *args):
        try:
            return fn(*args)
        except Exception as e:                               # a logging bug must not stop live monitoring
            lg.warn(f"{fn.__name__} failed: {e!r}")

    def feed_line_logged(t, line):
        guarded(lg.observe, t, line)
        outs = feed_line(t, line)
        guarded(lg.log_all, outs)
        return outs

    def flush_logged(now):
        outs = flush(now)
        guarded(lg.log_all, outs)
        return outs

    pipe.feed_line, pipe.flush, pipe.suspicious_log = feed_line_logged, flush_logged, lg
    atexit.register(lg.flush)                                # last try for rows held back by a locked file
    return pipe
