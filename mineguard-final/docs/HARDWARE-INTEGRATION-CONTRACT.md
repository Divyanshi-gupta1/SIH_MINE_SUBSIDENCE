# MineGuard Hardware Integration Contract

Send a JSON packet to `POST /api/ingest` during the software integration phase.

Required fields:

```json
{
  "node_id": "N3",
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

The current route validates packet shape only. In the integrated stack, the packet then feeds the ingestion service, sensor-health logic, ML adapter, risk engine and UI stream.
