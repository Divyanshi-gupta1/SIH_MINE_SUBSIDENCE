# MineGuard — Monitoring Dashboard

## Overview

MineGuard is a mine-subsidence monitoring and early-warning prototype developed for Smart India Hackathon problem statement SIH26025.

It brings together surface sensor observations, wireless communication, sensor-data processing, machine-learning-based anomaly assessment, and a GIS-oriented dashboard to support the monitoring of possible ground deformation above underground coal-mining areas.

The dashboard is the operator-facing part of the system. It presents sensor status, deformation-related observations, assessed risk states, spatial context, and alert information according to the data available through the application's configured data source.

## System workflow

The intended system workflow is:

```text
Surface sensor nodes
        |
        v
Wireless communication network
        |
        v
Gateway and sensor-data ingestion
        |
        v
Data validation and feature processing
        |
        v
Machine-learning anomaly assessment
        |
        v
Risk-state and alert processing
        |
        v
MineGuard dashboard
        |
        v
Operator review and response
```

The dashboard provides the visualisation and interaction layer for this workflow. The availability of each live connection depends on the corresponding firmware, gateway, model-inference, and application integration components.

## Dashboard capabilities

The application is designed to support:

- **GIS-oriented monitoring:** visualisation of sensor locations, mining-panel context, risk zones, and protected assets.
- **Sensor inspection:** viewing available sensor readings, node status, and communication information.
- **Zone and risk-state monitoring:** displaying the application state derived from the available observations and processing results.
- **Alert management:** reviewing alerts and recording actions such as acknowledgement, verification, confirmation, dismissal, or reporting a sensor issue, where implemented.
- **Historical review:** examining available event history and replay information.
- **Network and system status:** presenting available gateway, communication, and local/cloud status information.
- **Integration with sensor and model services:** using defined application interfaces for incoming sensor data, machine-learning outputs, and dashboard state.

Displayed risk states and alerts are decision-support outputs from the prototype. They are not, by themselves, proof of an actual subsidence event or a calibrated probability of mine collapse.

## Data interfaces

The application defines interfaces for sensor ingestion, model outputs, and application-state retrieval. Confirm the implementation and expected request schemas in the current API route and service files before integrating another component.

### Sensor ingestion

The application includes a sensor-ingestion interface at:

`POST /api/ingest`

The exact accepted fields, validation rules, and response format should be taken from the current route implementation.

### Machine-learning outputs

The application defines a machine-learning integration interface at:

`POST /api/ml`

The expected model outputs may include anomaly status, trend or persistence indicators, confidence-related information, supporting evidence, and model version, depending on the current implementation.

A model output must not be interpreted as a calibrated collapse probability unless that interpretation has been separately validated.

### Application state

The application includes a state interface at:

`GET /api/state`

Consult the current implementation for supported query parameters and response fields.

## Running locally

From the dashboard directory:

```bash
npm install
npm run dev
```

Open:

`http://localhost:3000`

For a production build, use:

```bash
npm run typecheck
npm run build
npm start
```

These commands assume the corresponding scripts are present in the current `package.json`.

## Configuration and integration

Before connecting the dashboard to physical sensor nodes or a gateway:

1. Confirm the gateway's actual packet format and serial or network transport.
2. Verify that incoming readings are validated and mapped to the application's expected schema.
3. Confirm how model inference is invoked and how its outputs are passed to the application.
4. Check timestamp handling, node identifiers, missing readings, and sensor-health conditions.
5. Verify how alerts are created, updated, acknowledged, and persisted.
6. Test behaviour during sensor disconnection, gateway failure, and network or cloud outages.

The application interfaces provide integration points, but an interface definition alone does not prove that an external gateway or model service is connected and running.

## Verification

Run the project's available type checks, build checks, and tests before deployment. Review the integration and verification documentation alongside the actual application code.

Demonstrations and screenshots should clearly distinguish recorded or simulated observations from readings received live from physical hardware.

## Scope and limitations

MineGuard is a prototype intended to support research and development of low-cost mine-subsidence monitoring and early warning.

Operational deployment requires site-specific sensor calibration, reliable communications, validation against independent ground-movement measurements, evaluation of false alarms and missed detections, and assessment by relevant mining and geotechnical experts.

The dashboard is one part of the complete monitoring system; its visual presentation does not independently establish the accuracy of the sensors, the machine-learning model, or a subsidence warning.
