/**
 * MineGuard Physics Intelligence Module — Main Entry Point
 *
 * Provides a clean interface for computing physics snapshots, expected deformation grids,
 * and residuals for the MineGuard dashboard.
 */

export * from "./types";
export * from "./parameters";
export * from "./knothe";
export * from "./pim";
export * from "./residual";

import type { NodeState, ZoneState } from "../types";
import type { PhysicsIntelligenceSnapshot, PhysicsParameters } from "./types";
import { PROTOTYPE_PARAMETERS, STAGE_TEMPORAL_FACTORS } from "./parameters";
import { SENSOR_LAYOUT } from "../demo";
import { generatePhysicsGrid } from "./pim";
import { calculateSensorResiduals, enrichZonesWithPhysics } from "./residual";

/**
 * Computes a complete physics intelligence snapshot for a given stage, sensor observations,
 * and optional custom parameters.
 */
export function computePhysicsSnapshot(
  stage: number,
  nodes: NodeState[],
  zones: ZoneState[],
  customParams?: Partial<PhysicsParameters>
): {
  snapshot: PhysicsIntelligenceSnapshot;
  enrichedZones: ZoneState[];
} {
  // 1. Resolve parameters: merge defaults, custom parameters, and stage-dependent temporal factor
  const temporalFactor = STAGE_TEMPORAL_FACTORS[Math.min(stage, 5)] ?? (stage / 5);
  const params: PhysicsParameters = {
    ...PROTOTYPE_PARAMETERS,
    ...customParams,
    temporalFactor: customParams?.temporalFactor ?? temporalFactor,
  };

  // 2. Generate expected deformation grid via Knothe-style PIM
  const grid = generatePhysicsGrid(params);

  // 3. Node layout map
  const nodePositions = Object.fromEntries(
    [
      { id: "SN-001", x: 18, y: 28 },
      { id: "SN-002", x: 48, y: 41 },
      { id: "SN-003", x: 76, y: 53 },
    ].map((s) => [s.id, { x: s.x, y: s.y }])
  );

  // 4. Calculate sensor residuals (observed - expected)
  const sensorOutputs = calculateSensorResiduals(nodes, grid, nodePositions);

  // 5. Enrich zones for UI without modifying ML predictions
  const enrichedZones = enrichZonesWithPhysics(zones, sensorOutputs, nodes);

  const snapshot: PhysicsIntelligenceSnapshot = {
    params,
    grid,
    sensorOutputs,
    computedAt: new Date().toISOString(),
    modelVersion: "SIMPLIFIED_KNOTHE_PROTOTYPE_v1",
  };

  return { snapshot, enrichedZones };
}
