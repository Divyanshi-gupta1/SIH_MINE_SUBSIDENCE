# MineGuard: Hardware-to-Dashboard Live Integration

Real-time subsidence early-warning system connecting ESP32 LoRa wireless mesh nodes (MPU-9250 + HC-SR04 ultrasonic) to a Random Forest ML model (v6) and streaming live predictions to the MineGuard Command Center dashboard.

---

## 🏗️ Architecture Overview

```
[ Physical Sensors on Mine Model ]
  ├─ Node 1 (MPU9250 + HC-SR04) ──┐
  ├─ Node 2 (MPU9250 + HC-SR04) ──┼──> [ LoRa Wireless Mesh ] ──> [ ESP32 USB Gateway ]
  └─ Node 3 (MPU9250 + HC-SR04) ──┘                                        │
                                                                           │ Serial (115200 baud)
                                                                           ▼
                                                              [ hardware_integration/run_live.py ]
                                                                 ├─ Sensor Conversion & Zeroing
                                                                 ├─ Rolling Buffer Feature Engine
                                                                 ├─ Random Forest v6 Inference
                                                                 └─ False-Alarm Guardrails
                                                                           │
                                                                           │ (live_state.json & HTTP)
                                                                           ▼
                                                              [ mineguard-final Dashboard (Next.js) ]
                                                                 ├─ Live GIS Deformation Map
                                                                 ├─ Zone Status (Z1, Z2, Z3)
                                                                 └─ Real-Time Risk & Alert Actions
```

---

## 🚀 Quick Start (Running in 2 Steps)

### Step 1: Start the MineGuard Dashboard
Open your first terminal window:
```bash
cd mineguard-final
npm run dev
```
Open **[http://localhost:3000](http://localhost:3000)** in your browser. The dashboard will launch in **Local Active** mode.

---

### Step 2: Connect Hardware & Start the Live Pipeline
Plug in your ESP32 Gateway via USB. Find your serial port (e.g. `COM9` on Windows or `/dev/cu.usbserial-*` on Mac/Linux).

Open your second terminal window:
```bash
cd hardware_integration
python run_live.py --port COM9
```
*(Replace `COM9` with your actual port. Default baud rate is 115200).*

---

## 🧪 Prototype Testing & Demo Walkthrough (5–10 Min)

During your demonstration, follow this exact sequence:

### Phase 1: Startup & Baseline Calibration (~40 seconds)
1. Place all 3 nodes still on your coal mine physical model.
2. Start `run_live.py`.
3. The script collects 20 sample windows (~40s) while held quiet to calibrate resting tilt angles and distance zeros.
4. **Dashboard View**: Displays `Calibrating baseline...` then turns **🟢 NORMAL (Safe)** once complete.
5. The calibration is automatically saved to `hardware_integration/calibration.json` so you do not need to recalibrate if restarted.

### Phase 2: Decoy / False Alarm Demonstration (Vibration Motor)
1. Turn on your vibration motor near the nodes for 5–10 seconds without physically tilting or moving the ground.
2. **Model Behavior**: High vibration is detected, but tilt and displacement remain zeroed.
3. **Dashboard View**: Categorized as **🟡 LOCAL ANOMALY / DECOY (Vibration-Only)**. No false subsidence evacuation alert is triggered!

### Phase 3: Subsidence Precursor Demonstration (Ground Movement)
1. Slowly apply mechanical tilt (1° to 3°) and open a distance gap (5 mm to 20 mm) on Node 1 (Zone 1).
2. Ground deformation starts accelerating and correlates with displacement.
3. **Model Behavior**: Identifies persistent deformation exceeding the confidence threshold ($p \ge 0.70$) across consecutive samples.
4. **Dashboard View**:
   - Stage advances to **🟠 PROGRESSIVE** then **🔴 CRITICAL**.
   - The **Live GIS Map** automatically draws directional progression vectors from Node 1 towards Protected Asset A01.
   - The **Alert Center** fires a critical action banner with a complete ML evidence trail.

---

## 🛠️ Helpful Commands

| Task | Command |
|---|---|
| Run with custom baud rate | `python run_live.py --port COM9 --baud 115200` |
| Force re-calibration after moving nodes | `python run_live.py --port COM9 --recalibrate` |
| Check serial line format from Arduino | `python audit_format.py --probe COM9 --lines 100` |
| Run all automated pipeline unit tests | `python -m unittest test_pipeline_units` |
| Offline simulation mode (without hardware) | `cd ../virtual_simulator/backend && python app.py` |

---

## 📋 Serial Data Format Reference

The pipeline automatically parses the standard Arduino Serial output from your ESP32 LoRa Gateway:
```text
-> [From NODE 1] Data: NODE_1|P:-75.39|R:-6.25|V:0.07|D:20.0 | RSSI: -33 dBm
```
* `P:` Pitch (MPU-9250, degrees)
* `R:` Roll (MPU-9250, degrees)
* `V:` Vibration RMS (g)
* `D:` Distance (HC-SR04 ultrasonic, cm)
* `RSSI:` LoRa signal strength (dBm)
# SIH_MINE_SUBSIDENCE
