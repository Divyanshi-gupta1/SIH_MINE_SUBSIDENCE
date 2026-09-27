"""
Fake receiver Arduino: streams the assumed serial format  node,ax,ay,az,gx,gy,gz,dist  for scripted
scenarios, so run_live.py / the bench harnesses / audit_format.py can be exercised end-to-end
(serial layer -> conversion -> guardrails -> model) with no hardware.

Backends
  --listen HOST:PORT   TCP server. Connect with any pyserial URL:  socket://127.0.0.1:9000
                       (pyserial's own loop:// is private to one Serial object -- two processes cannot
                       share it -- so socket:// is the zero-driver way to get a real serial_for_url path)
  --port COM7          write into a real/virtual serial port, e.g. one end of a com0com (Windows) or
                       `socat -d -d pty,raw,echo=0 pty,raw,echo=0` (Linux) pair; read the other end.
                       NOT tested here (no virtual-COM driver installed) -- the socket backend is.
  --out-file PATH      write the whole scenario to a log instantly (for audit_format.py --file,
                       run_live.py --replay); --style arduino-ts mimics Serial Monitor timestamps.

Scenarios (see --list):  normal | vibration | precursor | mixed | faults | lossy
Timeline is anchored after the pipeline's calibration span (--calib-s, default 60 s = 40 s calibration
+ margin at the bench profile); keep nodes "still" until then.

Examples
  python fake_serial.py --scenario mixed --listen 127.0.0.1:9000 --speed 10
  python run_live.py --port socket://127.0.0.1:9000 --time-scale 10 --calib-file NUL
  python fake_serial.py --scenario mixed --out-file sim_log.txt --style arduino-ts
  python audit_format.py --file sim_log.txt

--speed N plays the timeline N times faster than real time; the reader must then use --time-scale N
so the pipeline still sees sample_period_s of *simulated* time per window.
Everything here is simulated sensors under my noise assumptions, not evidence about real hardware.
"""
from __future__ import annotations

import argparse
import random
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterator

from sim_source import SimSensors

# ------------------------------------------------------------------------------------
# Scenarios
# ------------------------------------------------------------------------------------


@dataclass
class Scenario:
    name: str
    description: str
    total_s: float
    sim: SimSensors
    expect: dict                      # node number -> "quiet" | "decoy" | "alert" | "faulty"
    timeline: list = field(default_factory=list)
    marks: dict = field(default_factory=dict)   # named times in simulated seconds
    loss: float = 0.0                 # default LoRa packet loss
    corrupt: float = 0.0              # default fraction of garbled lines

    def raw_lines(self) -> Iterator[tuple[float, str]]:
        return self.sim.lines(self.total_s)


def _hook(table: dict, node: int, fn: Callable, combine: Callable):
    prev = table.get(node)
    table[node] = fn if prev is None else (lambda t, p=prev, f=fn: combine(p(t), f(t)))


def add_burst(sim, node, t0, dur, factor):
    _hook(sim.vib_factor, node, lambda t: factor if t0 <= t < t0 + dur else 1.0, lambda a, b: a * b)


def add_ramp(sim, node, t0, ramp_s, dtilt, ddisp, vmult, hold_s=20.0):
    """Accelerating (t^2) buildup shaped like the training precursors, then held at its peak."""
    f = lambda t: min(1.0, max(0.0, (t - t0) / ramp_s)) ** 2
    _hook(sim.tilt_extra_deg, node, lambda t: dtilt * f(t), lambda a, b: a + b)
    _hook(sim.disp_extra_mm, node, lambda t: ddisp * f(t), lambda a, b: a + b)
    _hook(sim.vib_factor, node, lambda t: 1 + (vmult - 1) * f(t), lambda a, b: a * b)


class FaultPlan:
    """Field-level faults on the raw fields [node,ax,ay,az,gx,gy,gz,dist], each active in [t0, t1)."""

    def __init__(self, seed=0):
        self.items: list = []
        self.rng = random.Random(seed)

    def add(self, node: int, t0: float, t1: float, fn: Callable):
        self.items.append((node, t0, t1, fn))

    def __call__(self, node, t, fields):
        for n, t0, t1, fn in self.items:
            if n == node and t0 <= t < t1:
                fields = fn(fields, self.rng)
        return fields


def _flip_upside_down(f, rng):
    f[3] = str(-int(f[3]))
    return f


def _target_5cm_closer(f, rng):
    f[7] = f"{float(f[7]) - 5.0:.2f}"
    return f


def _bad_ultrasonic(f, rng):                # 40 % no-echo, 8 % stray echoes
    u = rng.random()
    if u < 0.40:
        f[7] = "0.00"
    elif u < 0.48:
        f[7] = f"{rng.uniform(5, 300):.2f}"
    return f


def build_scenario(name: str, **kw) -> Scenario:
    p = dict(calib_s=60.0, period_s=2.0, seed=0, nodes=(1, 2, 3), raw_rate_hz=5.0, tilt=3.8, disp=33.0,
             vib=7.8, ramp_windows=34, burst_factor=8.0, burst_windows=3, accel_noise_g=0.004,
             dist_noise_cm=0.15, dist_step_cm=0.0)
    unknown = set(kw) - set(p)
    if unknown:
        raise ValueError(f"unknown scenario options: {sorted(unknown)}")
    p.update(kw)
    if name not in SCENARIOS:
        raise ValueError(f"unknown scenario {name!r}; choose from {sorted(SCENARIOS)}")
    sim = SimSensors(nodes=p["nodes"], raw_rate_hz=p["raw_rate_hz"], seed=p["seed"],
                     accel_noise_g=p["accel_noise_g"], dist_noise_cm=p["dist_noise_cm"],
                     dist_step_cm=p["dist_step_cm"])
    sc = SCENARIOS[name](sim, p)
    sc.name = name
    return sc


def _ramp_s(p):
    return p["ramp_windows"] * p["period_s"]


def _burst_s(p):
    return p["burst_windows"] * p["period_s"]


def _sc_normal(sim, p):
    C = p["calib_s"]
    return Scenario("", "all nodes perfectly still; every model sample must be `normal`", C + 150, sim,
                    {n: "quiet" for n in p["nodes"]}, [f"0-{C:g}s calibration (still)", f"{C:g}s+ still"])


def _sc_vibration(sim, p):
    C, b, F = p["calib_s"], _burst_s(p), p["burst_factor"]
    nodes = p["nodes"]
    shaken = nodes[:2]
    for n in shaken:
        add_burst(sim, n, C + 40, b, F)
    add_burst(sim, shaken[0], C + 100, b, F)
    return Scenario("", f"vibration only (x{F:g} for {b:g}s) on nodes {list(shaken)}; tilt/displacement stay put; "
                        f"other nodes are controls", C + 150, sim,
                    {n: ("decoy" if n in shaken else "quiet") for n in nodes},
                    [f"{C + 40:g}s burst on {list(shaken)}", f"{C + 100:g}s second burst on node {shaken[0]}"],
                    {"burst_1": C + 40, "burst_2": C + 100})


def _sc_precursor(sim, p):
    C, R = p["calib_s"], _ramp_s(p)
    nodes = p["nodes"]
    victim = nodes[1] if len(nodes) > 1 else nodes[0]
    add_ramp(sim, victim, C + 30, R, p["tilt"], p["disp"], p["vib"])
    return Scenario("", f"accelerating precursor on node {victim}: dtilt {p['tilt']:g} deg, ddisp {p['disp']:g} mm, "
                        f"vibration x{p['vib']:g} over {R:g}s; others still", C + 30 + R + 25, sim,
                    {n: ("alert" if n == victim else "quiet") for n in nodes},
                    [f"{C + 30:g}s ramp starts on node {victim}", f"{C + 30 + R:g}s ramp peak"],
                    {"ramp_start": C + 30, "ramp_peak": C + 30 + R})


def _sc_mixed(sim, p):
    C, R, b = p["calib_s"], _ramp_s(p), _burst_s(p)
    nodes = p["nodes"]
    victim = nodes[1] if len(nodes) > 1 else nodes[0]
    add_ramp(sim, victim, C + 30, R, p["tilt"], p["disp"], p["vib"])
    shaken = [n for n in nodes if n != victim]
    for n in shaken:
        add_burst(sim, n, C + 100, b, p["burst_factor"])
    return Scenario("", f"precursor on node {victim} while nodes {shaken} see a vibration-only burst: the alert "
                        f"must fire once, on {victim} only", C + 30 + R + 25, sim,
                    {n: ("alert" if n == victim else "decoy") for n in nodes},
                    [f"{C + 30:g}s ramp on node {victim}", f"{C + 100:g}s vibration burst on {shaken}"],
                    {"ramp_start": C + 30, "burst_1": C + 100})


def _sc_faults(sim, p):
    C = p["calib_s"]
    nodes = p["nodes"]
    a, b, c = nodes[0], nodes[1], nodes[2] if len(nodes) > 2 else nodes[-1]
    plan = FaultPlan(p["seed"])
    plan.add(a, C + 20, C + 60, _flip_upside_down)            # 40 s upside down  -> tilt > 90 deg
    plan.add(b, C + 30, C + 70, _target_5cm_closer)           # 40 s, -50 mm      -> negative displacement
    plan.add(c, C + 20, C + 70, _bad_ultrasonic)              # noisy ultrasonic  -> median filter copes
    sim.fault = plan
    return Scenario("", "physically impossible readings + garbled lines: node A flipped 40 s, node B target "
                        "-50 mm 40 s, node C 40 % no-echo ultrasonic; nothing impossible may reach the model",
                    C + 120, sim, {a: "faulty", b: "faulty", c: "quiet"},
                    [f"{C + 20:g}-{C + 60:g}s node {a} upside down", f"{C + 30:g}-{C + 70:g}s node {b} -50 mm",
                     f"{C + 20:g}-{C + 70:g}s node {c} 40% no-echo + stray echoes", "1% garbled lines throughout"],
                    {"fault_a_start": C + 20, "fault_a_end": C + 60, "fault_b_start": C + 30,
                     "fault_b_end": C + 70}, corrupt=0.01)


def _sc_lossy(sim, p):
    C = p["calib_s"]
    return Scenario("", "still nodes over a lossy LoRa link (25 % of packets dropped); must calibrate, keep "
                        "producing samples and stay `normal`", C + 150, sim,
                    {n: "quiet" for n in p["nodes"]}, ["25% packet loss throughout"], loss=0.25)


SCENARIOS: dict[str, Callable] = {
    "normal": _sc_normal, "vibration": _sc_vibration, "precursor": _sc_precursor,
    "mixed": _sc_mixed, "faults": _sc_faults, "lossy": _sc_lossy,
}

# ------------------------------------------------------------------------------------
# Line formatting: make the stream look like a real receiver's serial output
# ------------------------------------------------------------------------------------
STYLES = ("csv", "header", "kv", "tabs", "arduino-ts")
BANNER = ["", "LoRa receiver v1.2 (433 MHz SX1278)", "SF=7 BW=125k CR=4/5", "init OK", "TDM slots: 3",
          "waiting for nodes..."]
HEADER = "node,ax,ay,az,gx,gy,gz,dist"


class LineFormatter:
    def __init__(self, style="csv", corrupt=0.0, loss=0.0, banner=True, seed=0, clock0_s=13 * 3600 + 45 * 60):
        if style not in STYLES:
            raise ValueError(f"style must be one of {STYLES}")
        self.style, self.corrupt, self.loss, self.banner = style, corrupt, loss, banner
        self.rng = random.Random(seed)
        self.clock0 = clock0_s

    def _fmt(self, t: float, line: str) -> str:
        f = line.split(",")
        if self.style == "kv":
            return "N=%s ax=%s ay=%s az=%s gx=%s gy=%s gz=%s dist=%s" % tuple(f)
        if self.style == "tabs":
            return "\t".join(f)
        if self.style == "arduino-ts":
            s = self.clock0 + t
            return f"{int(s // 3600) % 24:02d}:{int(s % 3600 // 60):02d}:{int(s % 60):02d}.{int(s % 1 * 1000):03d} -> {line}"
        return line

    def _garble(self, line: str) -> str:
        r = self.rng.random()
        if r < 0.4 and len(line) > 6:                           # truncated mid-line (dropped serial bytes)
            return line[: self.rng.randrange(3, len(line) - 1)]
        if r < 0.7:                                             # corrupted character
            i = self.rng.randrange(len(line))
            return line[:i] + self.rng.choice("#?%;$") + line[i + 1:]
        return line + line                                      # lost newline -> two records glued

    def stream(self, raw: Iterator[tuple[float, str]]) -> Iterator[tuple[float, str]]:
        if self.banner:
            for b in BANNER:
                yield 0.0, b
        if self.style == "header":
            yield 0.0, HEADER
        for t, line in raw:
            if self.loss and self.rng.random() < self.loss:
                continue
            out = self._fmt(t, line)
            if self.corrupt and self.rng.random() < self.corrupt:
                out = self._garble(out)
            yield t, out


# ------------------------------------------------------------------------------------
# Backends
# ------------------------------------------------------------------------------------
def _emit(scenario: Scenario, write: Callable[[bytes], None], speed: float, fmt: LineFormatter, crlf: bool,
          stop: threading.Event | None = None):
    eol = b"\r\n" if crlf else b"\n"
    start = time.monotonic()
    for t, text in fmt.stream(scenario.raw_lines()):
        if stop is not None and stop.is_set():
            return
        if speed > 0:                                  # absolute schedule: sleep overshoot never accumulates
            delay = start + t / speed - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        write(text.encode("utf-8") + eol)


class FakeSerialServer:
    """TCP server that plays a scenario to the first client that connects, then closes (a closed
    socket makes pyserial raise SerialException -> serial_source ends cleanly, like an unplugged port).
    Use as a context manager; `.url` is a pyserial URL (socket://127.0.0.1:<port>)."""

    def __init__(self, scenario: Scenario, speed: float = 1.0, host: str = "127.0.0.1", port: int = 0,
                 style: str = "csv", crlf: bool = True, banner: bool = True, loss: float | None = None,
                 corrupt: float | None = None, seed: int = 0, forever: bool = False, accept_timeout: float = 60.0):
        self.scenario, self.speed, self.host, self.port = scenario, speed, host, port
        self.fmt_args = dict(style=style, banner=banner, seed=seed,
                             loss=scenario.loss if loss is None else loss,
                             corrupt=scenario.corrupt if corrupt is None else corrupt)
        self.crlf, self.forever, self.accept_timeout = crlf, forever, accept_timeout
        self._stop = threading.Event()
        self.done = threading.Event()
        self.error: Exception | None = None
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"socket://{self.host}:{self.port}"

    def start(self) -> "FakeSerialServer":
        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(1)
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return self

    def _serve(self):
        try:
            while not self._stop.is_set():
                self._sock.settimeout(self.accept_timeout)
                conn, _ = self._sock.accept()
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                try:
                    _emit(self.scenario, conn.sendall, self.speed, LineFormatter(**self.fmt_args), self.crlf,
                          self._stop)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    pass                                    # client went away early -- fine
                finally:
                    conn.close()
                if not self.forever:
                    break
        except (socket.timeout, OSError) as e:
            self.error = e
        finally:
            self.done.set()

    def stop(self):
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        if self._thread:
            self._thread.join(timeout=5)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


def write_log(scenario: Scenario, path, style="csv", crlf=True, banner=True, loss=None, corrupt=None, seed=0,
              encoding="utf-8"):
    """Whole scenario to a file instantly (no pacing)."""
    fmt = LineFormatter(style=style, banner=banner, seed=seed,
                        loss=scenario.loss if loss is None else loss,
                        corrupt=scenario.corrupt if corrupt is None else corrupt)
    eol = "\r\n" if crlf else "\n"
    n = 0
    with open(path, "w", encoding=encoding, newline="") as fh:
        for _, text in fmt.stream(scenario.raw_lines()):
            fh.write(text + eol)
            n += 1
    return n


def serve_serial_port(scenario: Scenario, port: str, baud: int, speed: float, **fmt_args):
    import serial                                        # pyserial; needed only for this backend
    ser = serial.Serial(port, baud)
    try:
        _emit(scenario, ser.write, speed, LineFormatter(**fmt_args), True)
    finally:
        ser.close()


# ------------------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="list scenarios and exit")
    ap.add_argument("--scenario", default="mixed", choices=sorted(SCENARIOS))
    out = ap.add_mutually_exclusive_group()
    out.add_argument("--listen", metavar="HOST:PORT", help="TCP server; connect with socket://HOST:PORT")
    out.add_argument("--port", help="write into this serial port (one end of a virtual COM pair)")
    out.add_argument("--out-file", help="write the whole scenario to this log instantly")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--speed", type=float, default=1.0, help="playback speed vs real time (0 = flat out)")
    ap.add_argument("--style", default="csv", choices=STYLES)
    ap.add_argument("--lf", action="store_true", help="use \\n instead of \\r\\n line endings")
    ap.add_argument("--no-banner", action="store_true")
    ap.add_argument("--loss", type=float, help="override packet-loss fraction")
    ap.add_argument("--corrupt", type=float, help="override garbled-line fraction")
    ap.add_argument("--forever", action="store_true", help="--listen: serve a fresh run to each new client")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--calib-s", type=float, default=60.0)
    ap.add_argument("--period-s", type=float, default=2.0, help="pipeline sample period (sets burst/ramp lengths)")
    ap.add_argument("--nodes", default="1,2,3")
    ap.add_argument("--tilt", type=float, default=3.8, help="precursor: total tilt change, deg")
    ap.add_argument("--disp", type=float, default=33.0, help="precursor: total displacement change, mm")
    ap.add_argument("--vib", type=float, default=7.8, help="precursor: final vibration multiplier")
    ap.add_argument("--ramp-windows", type=int, default=34)
    ap.add_argument("--burst-factor", type=float, default=8.0)
    ap.add_argument("--burst-windows", type=int, default=3)
    ap.add_argument("--accel-noise-g", type=float, default=0.004)
    ap.add_argument("--dist-noise-cm", type=float, default=0.15)
    ap.add_argument("--dist-step-cm", type=float, default=0.0, help="ultrasonic quantisation (1.0 = integer cm)")
    args = ap.parse_args(argv)

    if args.list:
        for n in sorted(SCENARIOS):
            sc = build_scenario(n)
            print(f"{n:10s} {sc.total_s:5.0f}s  {sc.description}")
            for line in sc.timeline:
                print(f"{'':10s}   - {line}")
            print(f"{'':10s}   expect: {sc.expect}")
        return 0

    sc = build_scenario(args.scenario, calib_s=args.calib_s, period_s=args.period_s, seed=args.seed,
                        nodes=tuple(int(x) for x in args.nodes.split(",")), tilt=args.tilt, disp=args.disp,
                        vib=args.vib, ramp_windows=args.ramp_windows, burst_factor=args.burst_factor,
                        burst_windows=args.burst_windows, accel_noise_g=args.accel_noise_g,
                        dist_noise_cm=args.dist_noise_cm, dist_step_cm=args.dist_step_cm)
    print(f"scenario {sc.name}: {sc.description}\n  total {sc.total_s:g} simulated s "
          f"({sc.total_s / max(args.speed, 1e-9):.0f} s at speed {args.speed:g}); expect {sc.expect}")
    for line in sc.timeline:
        print("   -", line)
    fmt_args = dict(style=args.style, banner=not args.no_banner, seed=args.seed,
                    loss=sc.loss if args.loss is None else args.loss,
                    corrupt=sc.corrupt if args.corrupt is None else args.corrupt)

    if args.out_file:
        n = write_log(sc, args.out_file, args.style, not args.lf, not args.no_banner, fmt_args["loss"],
                      fmt_args["corrupt"], args.seed)
        print(f"wrote {n} lines -> {args.out_file}")
        return 0
    if args.port:
        print(f"writing to {args.port} @ {args.baud}; read the paired port with run_live.py --port <other end>")
        serve_serial_port(sc, args.port, args.baud, args.speed, **fmt_args)
        return 0
    host, _, port = (args.listen or "127.0.0.1:9000").rpartition(":")
    srv = FakeSerialServer(sc, args.speed, host or "127.0.0.1", int(port), args.style, not args.lf,
                           not args.no_banner, fmt_args["loss"], fmt_args["corrupt"], args.seed, args.forever,
                           accept_timeout=3600)
    srv.start()
    scale = f" --time-scale {args.speed:g}" if args.speed != 1 else ""
    print(f"listening on {srv.url}\n  connect:  python run_live.py --port {srv.url}{scale}   "
          f"(or the test_*.py harnesses with --source serial --port {srv.url}{scale})")
    try:
        while not srv.done.is_set():
            srv.done.wait(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        srv.stop()
    print("scenario finished" if srv.error is None else f"stopped: {srv.error}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
