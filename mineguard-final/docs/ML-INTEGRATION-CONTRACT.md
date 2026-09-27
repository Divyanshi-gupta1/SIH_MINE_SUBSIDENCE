# MineGuard ML Integration Contract

## Responsibility split

### Hardware team
Produces validated sensor packets:

- `node_id`
- `timestamp`
- `sequence`
- `tilt_x_deg`
- `tilt_y_deg`
- `relative_displacement_mm`
- `vibration_level`
- `crack_detected`
- `battery_percent`
- `rssi`
- `quality`

### ML team
Consumes validated observations and returns model evidence:

- `anomaly`
- `trend`
- `persistence`
- `deformation_rate`
- `confidence`
- `evidence[]`
- `model_version`

Do not label an output `collapse_probability` unless the model is genuinely calibrated and validated for that interpretation.

### MineGuard software
Combines ML evidence with temporal persistence, spatial correlation, sensor health, asset context and operator workflow to produce an operational state and alert lifecycle.

## Example request

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
  "quality": "good"
}
```

## Example response

```json
{
  "anomaly": true,
  "trend": "increasing",
  "persistence": true,
  "deformation_rate": 0.34,
  "confidence": 0.91,
  "evidence": [
    "3 neighbouring nodes corroborate movement",
    "Relative displacement is increasing",
    "Sensor health is good"
  ],
  "model_version": "team-model-v1"
}
```
