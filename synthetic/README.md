# Synthetic Dataset — MineGuard

## Overview

This directory contains synthetic sensor data used to develop, test, and evaluate MineGuard's machine-learning pipeline for mine-subsidence anomaly detection.

The dataset simulates observations from a distributed wireless sensor network. It allows the team to develop and test data processing, temporal feature engineering, anomaly classification, and false-alarm discrimination before sufficient labelled field measurements are available.

**The dataset is simulated, not collected from physical mine sensors.** Its results demonstrate software and model behaviour under the generated scenarios; they do not establish real-world subsidence prediction accuracy.

## Files

- `simulated_mesh_data.csv` — synthetic sensor observations and derived features for 10 simulated nodes over a 120-day period, at 15-minute intervals.
- `events_log.csv` — event annotations describing the simulated subsidence-precursor and decoy disturbance episodes.
- `generate_synthetic_data.py` — generates the initial synthetic dataset.
- `add_decoy_episodes.py` — introduces simulated non-subsidence disturbances and derived features.
- `extend_dataset.py` — extends the dataset to a longer simulated period.
- `extend_dataset_v2.py` — adds further simulated observations and additional nodes.
- `add_tilt_baseline_feature.py` — adds the causal tilt-deviation feature.

Check the corresponding scripts and current CSV files before relying on row counts, event counts, or date ranges, because these values depend on the latest dataset version.

## Data fields

The dataset includes the following raw or derived fields, depending on the current dataset version:

| Field | Description |
|---|---|
| `timestamp` | Simulated observation timestamp |
| `node_id` | Identifier of the simulated sensor node |
| `tilt_deg` | Simulated tilt or inclination |
| `vibration_rms` | Simulated vibration magnitude |
| `displacement_mm` | Simulated displacement trend |
| `crack_signal` | Simulated binary crack indication |
| `vibration_duration` | Duration of a sustained vibration-threshold exceedance |
| `tilt_vibration_correlation` | Rolling relationship between tilt and vibration |
| `displacement_persistence` | Feature representing displacement persistence around a vibration event |
| `tilt_deviation_from_node_baseline` | Tilt deviation from a trailing node-specific baseline |

Derived features are calculated from the simulated observations. Their usefulness on synthetic data does not guarantee equivalent performance with physical sensors.

## Scenario design

The dataset includes two broad scenario types:

- **Subsidence-precursor scenarios:** simulated multi-sensor changes intended to represent progressively developing deformation.
- **Decoy disturbance scenarios:** simulated vibration events without the corresponding sustained tilt or displacement changes.

These scenarios help test whether the pipeline distinguishes a persistent, multi-sensor pattern from a short-lived vibration disturbance.

The generated magnitudes, event shapes, noise levels, and thresholds are modelling assumptions. They must not be treated as measured mine behaviour or as validated safety thresholds.

## Regional context and assumptions

Some background displacement trends were chosen using proposed regional subsidence-rate ranges. These values must be independently checked against the original geological or remote-sensing sources before being cited as established measurements for a specific coalfield.

In particular, regional annual subsidence rates do not directly validate the simulated magnitude of an individual precursor event or a tilt-sensor threshold.

See the project's reference documentation for source tracking and any outstanding verification notes.

## Using the dataset

Use this dataset to:

1. Develop and test preprocessing and feature-engineering logic.
2. Train and evaluate candidate anomaly-detection models.
3. Test discrimination between simulated precursor and decoy scenarios.
4. Reproduce software experiments and inspect model behaviour.
5. Prepare the pipeline for subsequent calibration and evaluation with physical sensor logs.

Follow the instructions in the relevant model and training scripts for the exact commands, dependencies, and output locations. Do not assume that every script listed above is a standalone training entry point.

## Transition to physical sensor data

When physical sensor logs are available, they should be stored and documented separately from the synthetic dataset. Before using them for training or validation:

1. Verify sensor units, calibration, timestamps, node identifiers, and missing-value handling.
2. Apply the same feature definitions where they are appropriate for real observations.
3. Obtain reliable labels for observed deformation events and non-subsidence disturbances.
4. Retrain or recalibrate the model as necessary.
5. Evaluate it on held-out real measurements and report the test conditions and limitations.

Synthetic and physical datasets must remain distinguishable in documentation, plots, and reported metrics.

## Interpretation of results

Performance measured on this dataset describes performance on the generated scenarios and labels. It must not be presented as field-validated accuracy, proven advance warning of mine collapse, or evidence of operational safety.

The physical monitoring prototype, software pipeline, and synthetic-data experiments are complementary parts of MineGuard, but evidence from one does not automatically validate the others.
