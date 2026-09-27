"""
Simulated 3-node LoRa/TDM stream in the ASSUMED raw serial format
    node,ax,ay,az,gx,gy,gz,dist
with MPU-9250-style int16 counts (+-2 g -> 16384 LSB/g, +-250 dps -> 131 LSB/dps) and an
ultrasonic distance in cm. Purpose: exercise the pipeline/harness logic without hardware.

It is NOT evidence about real-sensor behaviour -- the noise levels are my assumptions
(MPU-9250 accel noise density 300 ug/rtHz -> ~4 mg rms; HC-SR04-class ultrasonic ~1-3 mm)
and real installs will be noisier and non-Gaussian.

Scenario hooks (per node, functions of time t in seconds):
    vib_factor(t)      multiplies accel/gyro noise (1.0 = quiet)
    tilt_extra_deg(t)  extra rotation of the gravity vector about x
    disp_extra_mm(t)   extra distance to the target
"""
from __future__ import annotations

import math
from typing import Callable, Iterator

import numpy as np


class SimSensors:
    def __init__(self, nodes=(1, 2, 3), raw_rate_hz: float = 5.0, seed: int = 0,
                 accel_lsb_per_g: float = 16384.0, gyro_lsb_per_dps: float = 131.0,
                 accel_noise_g: float = 0.004, gyro_noise_dps: float = 0.1,
                 dist_cm: float = 100.0, dist_noise_cm: float = 0.15, dist_step_cm: float = 0.0,
                 dropout_p: float = 0.01, spike_p: float = 0.005):
        self.nodes = list(nodes)
        self.rate = raw_rate_hz
        self.rng = np.random.default_rng(seed)
        self.alsb, self.glsb = accel_lsb_per_g, gyro_lsb_per_dps
        self.a_noise, self.g_noise = accel_noise_g, gyro_noise_dps
        self.dist0, self.d_noise, self.d_step = dist_cm, dist_noise_cm, dist_step_cm
        self.dropout_p, self.spike_p = dropout_p, spike_p
        self.vib_factor: dict[int, Callable[[float], float]] = {}
        self.tilt_extra_deg: dict[int, Callable[[float], float]] = {}
        self.disp_extra_mm: dict[int, Callable[[float], float]] = {}
        self._mount = {n: self._mount_vec(1.0 + 0.7 * i, 40.0 * i) for i, n in enumerate(self.nodes)}
        self._gbias = {n: self.rng.normal(0, 0.4, 3) for n in self.nodes}
        self.fault: Callable[[int, float, list], list] | None = None   # (node, t, fields) -> fields

    @staticmethod
    def _mount_vec(tilt_deg: float, az_deg: float) -> np.ndarray:
        t, p = math.radians(tilt_deg), math.radians(az_deg)
        return np.array([math.sin(t) * math.cos(p), math.sin(t) * math.sin(p), math.cos(t)])

    def _reading(self, node: int, t: float) -> str:
        vf = self.vib_factor.get(node, lambda _t: 1.0)(t)
        te = math.radians(self.tilt_extra_deg.get(node, lambda _t: 0.0)(t))
        de = self.disp_extra_mm.get(node, lambda _t: 0.0)(t)
        c, s = math.cos(te), math.sin(te)
        R = np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
        a = R @ self._mount[node] + self.rng.normal(0, self.a_noise * vf, 3)
        g = self._gbias[node] + self.rng.normal(0, self.g_noise * vf, 3)
        d = self.dist0 + de / 10.0 + self.rng.normal(0, self.d_noise)
        if self.d_step > 0:
            d = round(d / self.d_step) * self.d_step
        u = self.rng.random()
        if u < self.dropout_p:
            d = 0.0                                             # no echo
        elif u < self.dropout_p + self.spike_p:
            d = float(self.rng.uniform(5, 300))                 # stray echo
        fields = [str(node)] + [str(int(np.clip(round(x * self.alsb), -32767, 32767))) for x in a] \
            + [str(int(round(x * self.glsb))) for x in g] + [f"{d:.2f}"]
        if self.fault:
            fields = self.fault(node, t, fields)
        return ",".join(fields)

    def lines(self, duration_s: float, t0: float = 0.0) -> Iterator[tuple[float, str]]:
        n_cycles = int(duration_s * self.rate)
        slot = 1.0 / self.rate / len(self.nodes)              # TDM: one slot per node per cycle
        for k in range(n_cycles):
            for i, node in enumerate(self.nodes):
                t = t0 + k / self.rate + i * slot
                yield t, self._reading(node, t)
