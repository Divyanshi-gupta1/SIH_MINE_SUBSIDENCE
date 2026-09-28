"""Line sources: yield (t_seconds, line). Live serial (any pyserial URL), or replay of a saved log."""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Iterator

# Arduino IDE 2.x Serial Monitor with "Show timestamp" prefixes every line: "13:45:02.123 -> <line>"
_ARDUINO_TS = re.compile(r"^\s*(\d{1,2}):(\d{2}):(\d{2})(?:[.,](\d{1,6}))?\s*->\s?(.*)$")
# our own raw-log format (serial_source(raw_log=...)): "<t with exactly 3 decimals><TAB><line>".
# Deliberately strict so a tab-delimited data line starting with a node number is not mistaken for it.
_RAWLOG_TS = re.compile(r"^(\d+\.\d{3})\t(.*)$")


def split_timestamp(raw: str) -> tuple[float | None, str]:
    """(seconds or None, remaining line)."""
    m = _ARDUINO_TS.match(raw)
    if m:
        h, mi, s, frac, rest = m.groups()
        return int(h) * 3600 + int(mi) * 60 + int(s) + (float("0." + frac) if frac else 0.0), rest
    m = _RAWLOG_TS.match(raw)
    if m:
        return float(m.group(1)), m.group(2)
    return None, raw


def _open_text(path):
    """Text reader that copes with what a Windows capture tool may have produced:
    UTF-8 (+BOM) or UTF-16 (PowerShell `>` redirection). Bad bytes are replaced, never fatal."""
    head = Path(path).read_bytes()[:4]
    enc = "utf-16" if head[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
    return open(path, encoding=enc, errors="replace", newline=None)


def log_has_timestamps(path: str | Path, n: int = 200) -> bool:
    """True if most of the first `n` non-empty lines carry a usable timestamp prefix."""
    seen = with_ts = 0
    with _open_text(path) as fh:
        for raw in fh:
            raw = raw.rstrip("\r\n")
            if not raw.strip():
                continue
            seen += 1
            with_ts += split_timestamp(raw)[0] is not None
            if seen >= n:
                break
    return seen > 0 and with_ts / seen >= 0.5


def file_source(path: str | Path, dt: float = 0.05) -> Iterator[tuple[float, str]]:
    """Replay a log. Understands Arduino Serial Monitor timestamps ('HH:MM:SS.mmm -> line'), our raw-log
    format ('t<TAB>line'), and bare serial lines. Bare lines get a synthetic clock advancing `dt` s per
    line -- so per-node rates are NOT measurable from them (see log_has_timestamps)."""
    t_syn, day, prev = 0.0, 0.0, None
    with _open_text(path) as fh:
        for raw in fh:
            raw = raw.rstrip("\r\n")
            ts, line = split_timestamp(raw)
            if ts is None:
                t_syn += dt
                yield t_syn, line
                continue
            if prev is not None and ts + day < prev - 43200:      # wall clock wrapped past midnight
                day += 86400.0
            prev = ts + day
            yield prev, line


def resolve_serial_port(port: str | None = None) -> str:
    """Auto-resolves serial port across Mac, Windows, and Linux if port is None or 'auto'."""
    try:
        import serial
        import serial.tools.list_ports
    except ImportError as e:
        raise SystemExit("pyserial is required for live serial input:  pip install pyserial") from e

    if port and port.lower() != "auto":
        return port

    comports = list(serial.tools.list_ports.comports())
    if not comports:
        print("[MineGuard Port Warning] No active serial ports found.", file=sys.stderr)
        print("Please check USB cable connection to ESP32 Gateway.", file=sys.stderr)
        raise SystemExit(1)

    # Filter for USB serial adapters (CH340, CP2102, FTDI, CDC ACM, etc.)
    usb_ports = []
    for p in comports:
        desc = (p.description or "").lower()
        dev = (p.device or "").lower()
        hwid = (p.hwid or "").lower()
        if any(term in desc or term in dev or term in hwid for term in (
            "usb", "cp210", "ch340", "ch341", "ftdi", "uart", "serial", "acm", "modem"
        )):
            usb_ports.append(p)

    selected = usb_ports[0] if usb_ports else comports[0]
    print(f"[MineGuard Port Auto-Detect] Auto-selected: {selected.device} ({selected.description})")
    return selected.device


def serial_source(port: str | None = "auto", baud: int = 115200, max_seconds: float | None = None,
                  raw_log: str | Path | None = None, time_scale: float = 1.0) -> Iterator[tuple[float, str]]:
    """Read lines from the receiver Arduino. `port` is COM5, /dev/ttyUSB0 or any pyserial URL.
    Supports 'auto' for automatic cross-platform port detection on Mac, Windows, and Linux."""
    try:
        import serial
    except ImportError as e:
        raise SystemExit("pyserial is required for live serial input:  pip install pyserial") from e

    resolved_port = resolve_serial_port(port)
    ser = serial.serial_for_url(resolved_port, baudrate=baud, timeout=0.5)
    log = open(raw_log, "a", encoding="utf-8") if raw_log else None
    t_start = time.monotonic()
    try:
        while max_seconds is None or time.monotonic() - t_start < max_seconds:
            try:
                raw = ser.readline()
            except serial.SerialException as e:
                print(f"serial port lost: {e}", file=sys.stderr)
                return
            if not raw:
                continue
            t = (time.monotonic() - t_start) * time_scale
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if log:
                log.write(f"{t:.3f}\t{line}\n")
                log.flush()
            yield t, line
    finally:
        ser.close()
        if log:
            log.close()
