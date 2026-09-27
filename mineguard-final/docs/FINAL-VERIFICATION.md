# Final verification gate

## Commands

```bash
npm install
npm run typecheck
npm run build
npm start
```

## Browser smoke test

- Command Center loads.
- Live GIS renders.
- Zone states change with scenario stage.
- Sensor Analytics renders.
- Alert lifecycle buttons work.
- History slider changes the map/state.
- Network Health shows 3 nodes.
- Settings loads.
- Demo scenarios work.
- Cloud button toggles local-first/offline state.

## SIH acceptance scenarios

### Progressive
Normal → Local anomaly → Persistent → Correlated → Progressive → High risk → Asset at risk.

### False local disturbance
Single-node disturbance remains local anomaly / verification and does not directly become critical.

### Offline
Cloud offline indicator changes but local monitoring remains active.

## Handoff

After this dashboard is verified locally, connect the ML team's real inference service and the hardware gateway using the documented integration contract.
