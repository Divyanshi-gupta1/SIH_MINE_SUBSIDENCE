"""
Dashboard Synchronizer for MineGuard
Translates SampleOutput from inference_pipeline into the live state schema
consumed by mineguard-final dashboard (mineguard-final/data/live_state.json).
"""
import os
import json
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
DATA_FILE = PROJECT_ROOT / "mineguard-final" / "data" / "live_state.json"

class DashboardSync:
    def __init__(self, dashboard_url: str = "http://localhost:3000"):
        self.dashboard_url = dashboard_url.rstrip("/")
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.cached_state = None
        self._load_initial_state()

    def _load_initial_state(self):
        if DATA_FILE.exists():
            try:
                self.cached_state = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                return
            except Exception:
                pass

        self.cached_state = {
            "schema_version": "1.0",
            "is_live": True,
            "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "stage": 0,
            "nodes": [
                {"id": "N1", "battery": 92, "rssi": -33, "lastSeen": "calibrating", "tilt": 0.0, "displacement": 0.0, "vibration": 0.03, "healthy": True},
                {"id": "N2", "battery": 88, "rssi": -45, "lastSeen": "calibrating", "tilt": 0.0, "displacement": 0.0, "vibration": 0.03, "healthy": True},
                {"id": "N3", "battery": 85, "rssi": -52, "lastSeen": "calibrating", "tilt": 0.0, "displacement": 0.0, "vibration": 0.03, "healthy": True}
            ],
            "zones": [
                {"id": "Z1", "name": "Initial deformation", "state": "NORMAL", "trend": "Stable", "direction": "East", "confidence": "HIGH", "evidence": ["Calibrating baseline..."], "assetDistanceM": 120},
                {"id": "Z2", "name": "Developing deformation", "state": "NORMAL", "trend": "Stable", "direction": "—", "confidence": "HIGH", "evidence": ["No material deformation evidence"], "assetDistanceM": 84},
                {"id": "Z3", "name": "Impact-direction zone", "state": "NORMAL", "trend": "Stable", "direction": "—", "confidence": "HIGH", "evidence": ["No material deformation evidence"], "assetDistanceM": 48}
            ],
            "alerts": []
        }

    def update_sample(self, o):
        """Called whenever inference_pipeline emits a SampleOutput o."""
        try:
            # Map node: NODE_01 / NODE_1 -> N1
            raw_id = o.node.upper().replace("NODE_", "N").replace("NODE", "N")
            node_id = f"N{int(raw_id[1:])}" if raw_id.startswith("N") and raw_id[1:].isdigit() else raw_id

            f = o.features
            tilt = round(float(f.get("tilt_deg", 0.0)), 2)
            disp = round(float(f.get("displacement_mm", 0.0)), 2)
            vib = round(float(f.get("vibration_rms", 0.0)), 3)

            # Update node in state
            nodes = self.cached_state.get("nodes", [])
            node_found = False
            for n in nodes:
                if n["id"] == node_id:
                    n["tilt"] = tilt
                    n["displacement"] = disp
                    n["vibration"] = vib
                    n["lastSeen"] = "just now"
                    n["healthy"] = True
                    node_found = True
                    break
            if not node_found:
                nodes.append({
                    "id": node_id, "battery": 90, "rssi": -35,
                    "lastSeen": "just now", "tilt": tilt, "displacement": disp, "vibration": vib, "healthy": True
                })

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
            self.cached_state["is_live"] = True
            self.cached_state["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            # Update Zone state
            zones = self.cached_state.get("zones", [])
            if zones:
                # Update Zone 1 (or corresponding zone)
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
                    "id": f"ALT-{int(time.time()) % 1000:03d}",
                    "zoneId": "Z1",
                    "severity": "CRITICAL" if stage == 5 else "HIGH",
                    "title": f"Z1 ({node_id}): Subsidence precursor confirmed by RF model",
                    "summary": f"Persistent ground deformation detected (top class: {top_class}, conf: {top_p}%, status: {status}).",
                    "evidence": z1["evidence"],
                    "confidence": "HIGH",
                    "lifecycle": "NEW",
                    "created": "just now"
                }]
            elif stage == 0 and not o.alert_fired:
                self.cached_state["alerts"] = []

            # Save state atomically to file
            temp_file = DATA_FILE.with_suffix(".tmp")
            temp_file.write_text(json.dumps(self.cached_state, indent=2), encoding="utf-8")
            temp_file.replace(DATA_FILE)

            # Optional HTTP sync if dashboard API is listening
            self._post_http(node_id, o, stage, risk_state)

        except Exception as e:
            # Non-fatal sync error
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
