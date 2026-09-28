# Final verification gate — updated dashboard

## Local commands

```bash
npm install
npm run typecheck
npm run build
npm start
```

## Browser smoke test

- Command Center loads in a professional light engineering UI.
- Mode switch exposes Demo / Live Testbed / Live Mine.
- Demo Mode provides Start / Pause / Reset and 1×/2×/4× controls.
- Live Testbed and Live Mine modes do not expose demo stage buttons.
- GIS renders a map-like engineering view rather than simple zone rectangles.
- Hover/focus on `SN-001`, `SN-002`, or `SN-003` opens the node inspection card.
- Node cards show tilt, displacement, deformation rate, vibration, battery, RSSI and model class/confidence.
- GIS layer toggles work.
- Alert actions support acknowledgement, verification, confirmation, dismissal and sensor issue.
- False-local scenario generates a watch/verification alert rather than a critical zone-wide state.
- History slider updates map/zone/asset context.
- Network Health shows node communication details and the data path.
- Cloud toggle changes the UI to local-first/offline wording without disabling local monitoring.
- Settings uses scalable node IDs and documents integration readiness.

## SIH acceptance scenarios

### Progressive scenario

Normal → Local anomaly → Persistent → Correlated → Progressive → High risk → assessed asset impact.

### False local disturbance

SN-002 deviates while neighbouring nodes remain nominal. The system surfaces a watch/verification event and does not directly label the whole area critical.

### Reset

Demo Reset returns the simulator to stage 0 and clears the active demo workflow.

### Live modes

Live Testbed and Live Mine modes show the integration seam and deliberately do not pretend that physical hardware is connected when it is not.

## Integration boundary

The next software integration step is to connect the actual ML team's inference pipeline and the physical gateway to the documented packet contracts. The dashboard architecture should remain unchanged; only the data source / adapter path should change.
