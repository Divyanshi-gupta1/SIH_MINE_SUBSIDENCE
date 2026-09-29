/**
 * MineGuard Physics Intelligence Module — Residual Analysis
 *
 * Computes:
 *   residual = observed_deformation - expected_deformation
 *
 * For each sensor node and spatial field.
 *
 * Agreement classification:
 *   HIGH:     |residual| <= 0.30 mm  (Near agreement / nominal calibration)
 *   MODERATE: |residual| <= 1.20 mm  (Minor divergence / elastic variation)
 *   LOW:      |residual| >  1.20 mm  (Significant residual: shear, fault, or decoy)
 *
 * CRITICAL RULE:
 * This calculation is an independent evidence layer. It does NOT modify
 * or replace Random Forest classifications or ML predictions.
 */

import type { NodeState, ZoneState } from "../types";
import type { PhysicsGrid, SensorPhysicsOutput } from "./types";
import { lookupGridDeformation } from "./pim";

/**
 * Calculates sensor-level physics residuals.
 *
 * @param nodes - Current sensor states from dashboard / live state
 * @param grid - Current pre-computed PIM physics grid
 * @param nodePositions - Node layout mapping { id: { x: pct, y: pct } }
 * @param svgWidthM - Width of viewport in meters (default 900)
 * @param svgHeightM - Height of viewport in meters (default 530)
 */
export function calculateSensorResiduals(
  nodes: NodeState[],
  grid: PhysicsGrid,
  nodePositions: Record<string, { x: number; y: number }>,
  svgWidthM = 900,
  svgHeightM = 530
): SensorPhysicsOutput[] {
  return nodes.map((node) => {
    // 1. Get observed deformation from documented displacement property
    const observedMm = Number(node.displacement.toFixed(2));

    // 2. Query expected deformation from Knothe-style PIM grid
    const pos = nodePositions[node.id] || { x: 50, y: 50 };
    const px = (pos.x / 100) * svgWidthM;
    const py = (pos.y / 100) * svgHeightM;
    const expectedMm = Number(lookupGridDeformation(grid, px, py).toFixed(2));

    // 3. Signed residual: observed - expected
    const residualMm = Number((observedMm - expectedMm).toFixed(2));
    const absResidual = Math.abs(residualMm);

    // 4. Categorize agreement
    let physicsAgreement: "HIGH" | "MODERATE" | "LOW" = "HIGH";
    let residualNote = "Observed movement aligns with calibrated Knothe subsidence.";

    if (absResidual > 1.20) {
      physicsAgreement = "LOW";
      residualNote = residualMm > 0
        ? "Observed deformation significantly exceeds physics prediction (potential localized shear/fracture)."
        : "Observed deformation significantly below physics prediction.";
    } else if (absResidual > 0.30) {
      physicsAgreement = "MODERATE";
      residualNote = "Moderate divergence between empirical Knothe curve and observation.";
    }

    return {
      nodeId: node.id,
      observedMm,
      expectedMm,
      residualMm,
      physicsAgreement,
      residualNote,
    };
  });
}

/**
 * Enriches existing zones with Knothe-based physics evidence for UI display
 * without modifying ML decisions or zone risk classifications.
 */
export function enrichZonesWithPhysics(
  zones: ZoneState[],
  sensorOutputs: SensorPhysicsOutput[],
  nodes: NodeState[]
): ZoneState[] {
  return zones.map((zone) => {
    // Find node belonging to this zone
    const matchingNode = nodes.find((n) => n.zoneId === zone.id);
    const sensorPhys = matchingNode
      ? sensorOutputs.find((s) => s.nodeId === matchingNode.id)
      : undefined;

    if (!sensorPhys) return zone;

    return {
      ...zone,
      observedMm: sensorPhys.observedMm,
      physicsExpectedMm: sensorPhys.expectedMm,
      physicsResidualMm: Math.abs(sensorPhys.residualMm),
      physicsStatus: sensorPhys.physicsAgreement,
    };
  });
}
