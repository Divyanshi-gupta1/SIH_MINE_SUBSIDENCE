"""
Dashboard Synchronizer for MineGuard
Translates SampleOutput from inference_pipeline into the live state schema
consumed by mineguard-final dashboard (mineguard-final/data/live_state.json).
Includes 30-second silence watchdog and unrealistic measurement filtering.
"""
import os
import json
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
DATA_FILE = PROJECT_ROOT / "mineguard-final" / "data" / "live_state.json"

NODE_MAPPING = {
    "NODE_01": ("SN-001", "Z-001"),
    "NODE_1": ("SN-001", "Z-001"),
    "N1": ("SN-001", "Z-001"),
    "SN-001": ("SN-001", "Z-001"),
    "NODE_02": ("SN-002", "Z-002"),
    "NODE_2": ("SN-002", "Z-002"),
    "N2": ("SN-002", "Z-002"),
    "SN-002": ("SN-002", "Z-002"),
    "NODE_03": ("SN-003", "Z-003"),
    "NODE_3": ("SN-003", "Z-003"),
    "N3": ("SN-003", "Z-003"),
    "SN-003": ("SN-003", "Z-003"),
}

def map_node(raw_id: str) -> tuple[str, str]:
    clean = raw_id.strip().upper().replace(" ", "_")
    if clean in NODE_MAPPING:
        return NODE_MAPPING[clean]
    for key, val in NODE_MAPPING.items():
        if key in clean:
            return val
    return ("SN-001", "Z-001")


class DashboardSync:
    def __init__(self, dashboard_url: str = "http://localhost:3000"):
        self.dashboard_url = dashboard_url.rstrip("/")
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.node_last_seen: dict[str, float] = {}
        self.cached_state = None
        self._load_initial_state()

    def _load_initial_state(self):
        if DATA_FILE.exists():
            try:
                self.cached_state = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                for n in self.cached_state.get("nodes", []):
                    self.node_last_seen[n["id"]] = time.time()
                return
            except Exception:
                pass

        self.cached_state = {
            "schema_version": "1.1",
            "is_live": True,
            "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "stage": 0,
            "scenario": "normal",
            "overall_state": "NORMAL",
            "nodes": [
                {
                    "id": "SN-001", "zoneId": "Z-001", "battery": 92, "rssi": -33,
                    "lastSeen": "just now", "tilt": 0.0, "displacement": 0.0, "deformationRate": 0.02,
                    "vibration": 0.03, "healthy": True, "quality": "GOOD",
                    "modelClass": "normal", "modelConfidence": 0.95,
                    "healthMessage": "Nominal telemetry · Calibrating baseline"
                },
                {
                    "id": "SN-002", "zoneId": "Z-002", "battery": 87, "rssi": -45,
                    "lastSeen": "just now", "tilt": 0.0, "displacement": 0.0, "deformationRate": 0.02,
                    "vibration": 0.03, "healthy": True, "quality": "GOOD",
                    "modelClass": "normal", "modelConfidence": 0.95,
                    "healthMessage": "Nominal telemetry · Calibrating baseline"
                },
                {
                    "id": "SN-003", "zoneId": "Z-003", "battery": 82, "rssi": -52,
                    "lastSeen": "just now", "tilt": 0.0, "displacement": 0.0, "deformationRate": 0.02,
                    "vibration": 0.03, "healthy": True, "quality": "GOOD",
                    "modelClass": "normal", "modelConfidence": 0.95,
                    "healthMessage": "Nominal telemetry · Calibrating baseline"
                }
            ],
            "zones": [
                {
                    "id": "Z-001", "name": "Western panel edge", "state": "NORMAL",
                    "trend": "Stable", "direction": "East", "confidence": "HIGH",
                    "evidence": ["Calibrating baseline..."], "assetDistanceM": 120
                },
                {
                    "id": "Z-002", "name": "Central convergence corridor", "state": "NORMAL",
                    "trend": "Stable", "direction": "—", "confidence": "HIGH",
                    "evidence": ["No material deformation evidence"], "assetDistanceM": 84
                },
                {
                    "id": "Z-003", "name": "Asset-side monitoring area", "state": "NORMAL",
                    "trend": "Stable", "direction": "—", "confidence": "HIGH",
                    "evidence": ["No material deformation evidence"], "assetDistanceM": 46
                }
            ],
            "alerts": [],
            "local_monitoring": "ACTIVE",
            "cloud": "CONNECTED",
            "ml_adapter": "READY",
            "data_source": "LIVE_HARDWARE"
        }
        for n in self.cached_state["nodes"]:
            self.node_last_seen[n["id"]] = time.time()

    def update_sample(self, o):
        """Called whenever inference_pipeline emits a SampleOutput o."""
        try:
            node_id, zone_id = map_node(o.node)
            now = time.time()
            self.node_last_seen[node_id] = now

            f = o.features
            tilt = round(float(f.get("tilt_deg", 0.0)), 2)
            disp = round(float(f.get("displacement_mm", 0.0)), 2)
            vib = round(float(f.get("vibration_rms", 0.0)), 3)
            def_rate = round(disp * 0.05, 2)

            # Check for unrealistic measurements
            is_unrealistic = False
            unrealistic_reason = ""
            if tilt > 90.0:
                is_unrealistic = True
                unrealistic_reason = f"Tilt {tilt}° exceeds 90° physical limit"
            elif abs(disp) > 500.0:
                is_unrealistic = True
                unrealistic_reason = f"Displacement {disp}mm exceeds 500mm physical limit"
            elif vib > 15.0:
                is_unrealistic = True
                unrealistic_reason = f"Vibration {vib}g exceeds sensor saturation"

            # Update node in cached state
            nodes = self.cached_state.get("nodes", [])
            target = None
            for n in nodes:
                if n["id"] == node_id:
                    target = n
                    break
            if not target:
                target = {
                    "id": node_id, "zoneId": zone_id, "battery": 90, "rssi": -35,
                    "lastSeen": "just now", "tilt": tilt, "displacement": disp,
                    "deformationRate": def_rate, "vibration": vib, "healthy": True,
                    "quality": "GOOD", "modelClass": o.top_class, "modelConfidence": round(o.top_p, 2),
                    "healthMessage": "Nominal telemetry"
                }
                nodes.append(target)

            target["tilt"] = tilt
            target["displacement"] = disp
            target["deformationRate"] = def_rate
            target["vibration"] = vib
            target["modelClass"] = o.top_class
            target["modelConfidence"] = round(o.top_p, 2)

            if is_unrealistic:
                target["healthy"] = False
                target["quality"] = "DEGRADED"
                target["healthMessage"] = f"Unrealistic measurement: {unrealistic_reason}"
            else:
                target["healthy"] = True
                target["quality"] = "GOOD"
                target["lastSeen"] = "just now"
                target["healthMessage"] = "Nominal telemetry · All checks passed"

            # Check 30-second silence for ALL nodes
            for n in nodes:
                nid = n["id"]
                last_time = self.node_last_seen.get(nid, now)
                elapsed = now - last_time
                if elapsed > 30.0:
                    n["healthy"] = False
                    n["quality"] = "UNAVAILABLE"
                    n["lastSeen"] = f">30s ago (no signal: {int(elapsed)}s)"
                    n["healthMessage"] = "Node is not sending signals (>30s silence)"

            # Determine risk stage and category
            top_class = o.top_class
            status = o.status
            top_p = round(float(o.top_p) * 100.0, 1)

            stage = 0
            risk_state = "NORMAL"
            trend = "Stable"

            if top_class == "subsidence_precursor":
                if status == "CONFIRMED" or o.alert_fired:
                    stage = 5
                    risk_state = "CRITICAL"
                    trend = "Accelerating"
                elif status == "POSSIBLE" or top_p >= 70.0:
                    stage = 4
                    risk_state = "HIGH_RISK"
                    trend = "Accelerating"
                else:
                    stage = 3
                    risk_state = "PROGRESSIVE"
                    trend = "Rising"
            elif top_class == "decoy_seismic" or status == "DECOY":
                stage = 1
                risk_state = "LOCAL_ANOMALY"
                trend = "Local spike"
            else:
                stage = 0
                risk_state = "NORMAL"
                trend = "Stable"

            self.cached_state["stage"] = stage
            self.cached_state["overall_state"] = risk_state
            self.cached_state["is_live"] = True
            self.cached_state["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            # Update Zones
            zones = self.cached_state.get("zones", [])
            if zones:
                z1 = zones[0]
                z1["state"] = risk_state
                z1["trend"] = trend
                z1["confidence"] = "HIGH" if top_p > 75 else "MEDIUM"
                z1["evidence"] = [
                    f"Model: RF v6 -> {top_class.upper()} ({top_p}% conf, status: {status})",
                    f"Tilt: {tilt}° | Disp: {disp} mm | Vib: {vib} g | TiltDev: {f.get('tilt_deviation_from_node_baseline', 0.0):+.2f}",
                    f"Persistence: {'YES' if f.get('displacement_persistence', 0) == 1 else 'NO'} | Crack: {'YES' if f.get('crack_signal', 0) == 1 else 'NO'}"
                ]

                if stage >= 5:
                    zones[1]["state"] = "HIGH_RISK"
                    zones[1]["trend"] = "Accelerating"
                    zones[2]["state"] = "PROGRESSIVE"
                elif stage >= 4:
                    zones[1]["state"] = "PROGRESSIVE"
                    zones[1]["trend"] = "Rising"
                    zones[2]["state"] = "NORMAL"
                else:
                    zones[1]["state"] = "NORMAL"
                    zones[2]["state"] = "NORMAL"

            # Update alerts
            if stage >= 4 or o.alert_fired:
                self.cached_state["alerts"] = [{
                    "id": f"ALT-{int(now) % 1000:03d}",
                    "zoneId": zone_id,
                    "nodeId": node_id,
                    "severity": "CRITICAL" if stage == 5 else "HIGH",
                    "title": f"{zone_id} ({node_id}): Subsidence precursor confirmed by RF model",
                    "summary": f"Persistent ground deformation detected (top class: {top_class}, conf: {top_p}%, status: {status}).",
                    "evidence": z1["evidence"],
                    "confidence": "HIGH",
                    "lifecycle": "NEW",
                    "created": "just now",
                    "recommendedAction": "Verify field conditions and trigger site response protocol." if stage >= 5 else "Inspect the affected zone."
                }]
            elif stage == 0 and not o.alert_fired:
                self.cached_state["alerts"] = []

            # Save state atomically to file
            temp_file = DATA_FILE.with_suffix(".tmp")
            temp_file.write_text(json.dumps(self.cached_state, indent=2), encoding="utf-8")
            temp_file.replace(DATA_FILE)

            # Optional HTTP sync if dashboard API is listening
            self._post_http(node_id, o, stage, risk_state)

        except Exception:
            pass

    def _post_http(self, node_id, o, stage, risk_state):
        try:
            payload = {
                "node_id": node_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "sequence": o.window_idx,
                "tilt_x_deg": o.diag.get("tilt_raw_deg", 0.0),
                "tilt_y_deg": 0.0,
                "relative_displacement_mm": o.features.get("displacement_mm", 0.0),
                "vibration_level": o.features.get("vibration_rms", 0.0),
                "crack_detected": bool(o.features.get("crack_signal", 0) == 1),
                "battery_percent": 90,
                "rssi": -33,
                "quality": "good"
            }
            req = urllib.request.Request(
                f"{self.dashboard_url}/api/ingest",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=0.1) as resp:
                pass
        except Exception:
            pass
