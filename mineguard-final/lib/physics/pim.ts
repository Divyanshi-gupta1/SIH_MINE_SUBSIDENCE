/**
 * MineGuard Physics Intelligence Module — Prediction Influence Model (PIM)
 *
 * The PIM distributes the expected effect of underground panel extraction
 * onto a surface grid using the Knothe-style influence function.
 *
 * Output: a spatial grid of expected surface deformation values that can
 * be rendered on the GIS as an "Expected Deformation" layer.
 *
 * This is SEPARATE from and does NOT modify the ML pipeline.
 */

import type { PhysicsGrid, PhysicsParameters } from "./types";
import { calculateExpectedDeformation, deriveInfluenceRadius, calculateSmax } from "./knothe";
import { EXTRACTION_CENTROID } from "./parameters";

// ─── Grid generation ─────────────────────────────────────────────────

/**
 * Generates a spatial expected-deformation grid over the local coordinate
 * domain of the GIS map viewport.
 *
 * Grid domain:
 *   X: 0 → gridWidthM (meters)
 *   Y: 0 → gridHeightM (meters)
 *
 * The grid is sampled at every `stepM` meters, matching the spatial
 * resolution needed by the GIS canvas renderer.
 *
 * @param params - prototype mining parameters (with temporalFactor set)
 * @param gridWidthM - local coordinate width of map viewport (m)
 * @param gridHeightM - local coordinate height of map viewport (m)
 * @param stepM - grid sampling resolution (m)
 * @param centroidX - extraction influence centroid X (m), defaults to EXTRACTION_CENTROID
 * @param centroidY - extraction influence centroid Y (m), defaults to EXTRACTION_CENTROID
 */
export function generatePhysicsGrid(
  params: PhysicsParameters,
  gridWidthM = 900,
  gridHeightM = 530,
  stepM = 10,
  centroidX = EXTRACTION_CENTROID.x,
  centroidY = EXTRACTION_CENTROID.y
): PhysicsGrid {
  const cols = Math.ceil(gridWidthM / stepM);
  const rows = Math.ceil(gridHeightM / stepM);

  const points = [];
  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      const px = col * stepM;
      const py = row * stepM;
      const pt = calculateExpectedDeformation(px, py, centroidX, centroidY, params);
      points.push(pt);
    }
  }

  return {
    points,
    cols,
    rows,
    sMaxMm: Number(calculateSmax(params).toFixed(3)),
    influenceRadiusM: Number(deriveInfluenceRadius(params).toFixed(1)),
    influenceCentroidX: centroidX,
    influenceCentroidY: centroidY,
  };
}

/**
 * Looks up the expected deformation at a specific (x,y) coordinate
 * by interpolating from the pre-computed grid.
 *
 * Uses nearest-grid-cell lookup (no re-interpolation).
 *
 * @param grid - pre-computed physics grid
 * @param px - query x (m)
 * @param py - query y (m)
 * @param stepM - grid resolution used during generatePhysicsGrid
 * @returns expected deformation in mm
 */
export function lookupGridDeformation(
  grid: PhysicsGrid,
  px: number,
  py: number,
  stepM = 10
): number {
  const col = Math.min(grid.cols - 1, Math.max(0, Math.round(px / stepM)));
  const row = Math.min(grid.rows - 1, Math.max(0, Math.round(py / stepM)));
  const idx = row * grid.cols + col;
  return grid.points[idx]?.expectedDeformationMm ?? 0;
}

/**
 * Samples the grid at node pixel positions (converting from SVG percentage
 * coordinates to local meters) and returns expected deformation per node.
 *
 * @param grid - pre-computed physics grid
 * @param nodePctPositions - map of nodeId → {x: pct, y: pct}
 * @param svgWidthM - viewport width in meters (default 900)
 * @param svgHeightM - viewport height in meters (default 530)
 * @param stepM - grid resolution
 */
export function sampleGridAtNodes(
  grid: PhysicsGrid,
  nodePctPositions: Record<string, { x: number; y: number }>,
  svgWidthM = 900,
  svgHeightM = 530,
  stepM = 10
): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [nodeId, pct] of Object.entries(nodePctPositions)) {
    const mx = (pct.x / 100) * svgWidthM;
    const my = (pct.y / 100) * svgHeightM;
    out[nodeId] = lookupGridDeformation(grid, mx, my, stepM);
  }
  return out;
}
