# MineGuard Dashboard — SIH 26025 Runnable Prototype

This is the updated MineGuard software layer for the SIH 26025 mine-subsidence monitoring concept.

## What changed in this build

- Professional light engineering / mine-control visual design instead of the previous dark prototype theme.
- GIS-style engineering map with panel/corridor geometry, layers, gateway, asset, deformation direction and assessed impact zone.
- Hover/focus inspection card for each sensor node with live readings, health, communication quality and ML status.
- Scalable sensor IDs (`SN-001`, `SN-002`, `SN-003`) driven by data/configuration instead of UI-specific hardcoding.
- Dedicated **Demo Mode** with scenario selection, Start, Pause, Reset and 1×/2×/4× playback speed.
- Demo mode advances through operational states instead of exposing raw manual stage buttons to the operator.
- Explicit separation of **Demo**, **Live Testbed**, and **Live Mine** data-source modes.
- Alert workflow supports Acknowledge, Mark for Verification, Confirm, Dismiss and Sensor Issue.
- False-local disturbance scenario remains a verification/watch event rather than escalating directly to critical.
- Interactive GIS layer controls for grid, sensors, risk, assets, impact and mesh/network.
- History / event replay remains synchronized with map and zone state.
- Local-first/cloud status remains visible; cloud outage is represented without implying local monitoring has stopped.
- API contracts updated for hardware ingestion and ML integration readiness.

## Important scope boundary

The dashboard package does **not** contain the ML team's trained model or the physical LoRa/ESP32 gateway service. The package provides the application architecture and integration seams for those components.

Expected real deployment flow:

```text
Physical sensor nodes
        ↓
Wireless surface mesh
        ↓
Gateway
        ↓
Validated sensor packet
        ↓
ML / temporal / spatial processing
        ↓
MineGuard operational state
        ↓
Dashboard + alert lifecycle
```

Demo Mode uses synthetic observations to exercise the same logical dashboard state model. It does not claim to reproduce field sensor noise or calibrated mine safety thresholds.

## Run locally

```bash
npm install
npm run typecheck
npm run build
npm start
```

Development mode:

```bash
npm run dev
```

Default local URL:

`http://localhost:3000`

## Integration endpoints

### Hardware packet

`POST /api/ingest`

Required fields:

```json
{
  "node_id": "SN-003",
  "timestamp": "2026-09-25T04:00:00Z",
  "sequence": 1842,
  "tilt_x_deg": 0.34,
  "tilt_y_deg": 0.12,
  "relative_displacement_mm": 4.8,
  "vibration_level": 0.63,
  "crack_detected": false,
  "battery_percent": 82,
  "rssi": -71,
  "quality": "good"
}
```

### ML adapter

`POST /api/ml`

The dashboard contract expects anomaly/trend/persistence/rate/confidence/evidence/model-version outputs. It should not be presented as a calibrated collapse probability unless the external model has actually been validated for that interpretation.

### State snapshot

`GET /api/state?stage=4&scenario=progressive`

Supported scenarios:

- `progressive`
- `false_local`
- `normal`

## Verification

See `docs/FINAL-VERIFICATION.md` for the browser and SIH acceptance checklist.
