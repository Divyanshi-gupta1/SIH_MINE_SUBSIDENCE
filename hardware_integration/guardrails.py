"""
False-alarm guardrails on top of the raw per-sample model output.

The model votes once per sample. An alert must NOT fire on one vote. Rules:

  * A "risk" class = any class that is neither `normal` nor a benign decoy class
    (today: `subsidence_precursor`; if the model is retrained with more risk classes
    they are picked up automatically, config.decoy_classes / normal_class decide).
  * CONFIRMED  -- the SAME risk class is the top vote with probability >= confirm_confidence
                  for `persist_n` consecutive samples (persist_n = ceil(persist_window_s /
                  sample_period_s); 8 s / 2 s = 4 on the bench). Fires the alert once.
  * POSSIBLE   -- the top vote is a risk class but either p < confirm_confidence (low
                  confidence never counts toward a streak and resets it) or the streak is
                  still shorter than persist_n. Logged, never alerts.
  * DECOY      -- top vote is a benign decoy class (vibration-only event). Informational.
  * NORMAL     -- top vote is `normal`.
  * A gap of more than `max_missing_windows` dropped/missing windows resets the streak
    (consecutive means consecutive); a CONFIRMED alert stays latched until `clear_n`
    non-risk samples in a row, so it neither re-fires nor flaps.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config import PipelineConfig


@dataclass
class Verdict:
    status: str                  # NORMAL | DECOY | POSSIBLE | CONFIRMED
    top_class: str
    top_p: float
    risk_class: Optional[str]
    streak: int
    need: int
    alert_fired: bool
    note: str


class AlertGuard:
    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg
        self.need = cfg.persist_n
        self._streak = 0
        self._streak_class: Optional[str] = None
        self._latched: Optional[str] = None
        self._clear = 0
        self._last_idx: Optional[int] = None

    def is_risk(self, cls: str) -> bool:
        return cls != self.cfg.normal_class and cls not in self.cfg.decoy_classes

    def reset_streak(self):
        self._streak, self._streak_class = 0, None

    def update(self, window_idx: int, probs: dict) -> Verdict:
        cfg = self.cfg
        top = max(probs, key=probs.get)
        p = float(probs[top])

        if self._last_idx is not None and (window_idx - self._last_idx - 1) > cfg.max_missing_windows:
            self.reset_streak()
        self._last_idx = window_idx

        if not self.is_risk(top):
            self.reset_streak()
            self._clear += 1
            if self._clear >= cfg.clear_n:
                self._latched = None
            if top == cfg.normal_class:
                return Verdict("NORMAL", top, p, None, 0, self.need, False, "")
            return Verdict("DECOY", top, p, None, 0, self.need, False,
                           "benign vibration event -- no subsidence alert")

        self._clear = 0
        if p < cfg.confirm_confidence:
            self.reset_streak()
            return Verdict("POSSIBLE", top, p, top, 0, self.need, False,
                           f"low confidence {p:.2f} < {cfg.confirm_confidence:.2f}")

        self._streak = self._streak + 1 if self._streak_class == top else 1
        self._streak_class = top
        if self._streak < self.need:
            return Verdict("POSSIBLE", top, p, top, self._streak, self.need, False,
                           f"{self._streak}/{self.need} consecutive")
        fired = self._latched != top
        self._latched = top
        return Verdict("CONFIRMED", top, p, top, self._streak, self.need, fired,
                       f"{self._streak} consecutive >= {cfg.confirm_confidence:.2f}")
