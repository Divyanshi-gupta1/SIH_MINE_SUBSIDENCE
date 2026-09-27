# MineGuard Dashboard — Runnable SIH Prototype

This folder is the **actual runnable dashboard application** for the MineGuard concept. It replaces the earlier placeholder/prototype-only package.

## Requirements

- Node.js 18+ (Node 20+ recommended)
- npm 9+

## Run locally

```bash
npm install
npm run build
npm start
```

Then open the local URL shown by Next.js (normally `http://localhost:3000`).

For development:

```bash
npm run dev
```

Optional type check:

```bash
npm run typecheck
```

## What is implemented

- Command Center
- Live GIS testbed visualization using SVG/local engineering coordinates
- Zone Intelligence
- Sensor Analytics
- Alert & Action lifecycle
- Event Replay / History
- Network Health
- Engineering Settings
- Demo Scenario Simulator
- Local-first/cloud status indicator
- Asset impact context
- Explainable evidence
- ML adapter endpoint at `POST /api/ml`
- State snapshot endpoint at `GET /api/state`

## Important integration boundary

The dashboard does **not** contain your ML team's trained model. It provides the integration seam for the model/service.

Expected model output fields include:

```json
{
  "anomaly": true,
  "trend": "increasing",
  "persistence": true,
  "deformation_rate": 0.34,
  "confidence": 0.91,
  "evidence": [
    "3 neighbouring nodes corroborate movement",
    "Relative displacement is increasing"
  ],
  "model_version": "team-model-v1"
}
```

Replace the demo adapter with the ML team's real inference service after their actual schema is confirmed.

## Demo scenarios

Use the **Scenario simulator** in Command Center or Demo view:

1. Progressive — Normal → Local anomaly → Persistent → Correlated → Progressive → High risk.
2. False local — a single node disturbance should remain a local anomaly and not become critical.
3. Normal — clears the event and returns the system to normal.

The prototype deliberately uses demonstration thresholds and does **not** claim a calibrated collapse probability.
