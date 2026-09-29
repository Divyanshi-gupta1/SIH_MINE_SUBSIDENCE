/**
 * MineGuard Physics Intelligence Module — Prototype Parameters
 *
 * IMPORTANT: Every value below is a PROTOTYPE ASSUMPTION.
 * These are realistic-but-configurable testbed values.
 * They do NOT represent any specific mine site.
 *
 * Field deployment requires site-specific calibration using:
 * - Actual mine survey data
 * - Geological investigations
 * - Surface monitoring (GNSS / InSAR / tiltmeters)
 */

import type { PhysicsParameters } from "./types";

/**
 * Default prototype parameter set for Panel A longwall testbed.
 * Each field comment indicates the basis for the prototype value choice.
 */
export const PROTOTYPE_PARAMETERS: PhysicsParameters = {
  // ─── Panel Geometry ─────────────────────────────────────────────
  /** Prototype assumption: typical longwall panel width for a medium seam (m) */
  panelWidthM: 200,
  /** Prototype assumption: panel retreated length at current extraction advance (m) */
  panelLengthM: 300,
  /** Prototype assumption: seam depth — representative for shallow-to-medium coal seams */
  panelDepthM: 110,
  /** Prototype assumption: typical thin-seam longwall extraction height (m) */
  extractedThicknessM: 2.2,

  // ─── Geotechnical Parameters ─────────────────────────────────────
  /**
   * Prototype assumption: extraction ratio for caved longwall with full goaf
   * (typically 0.80–0.90 for productive longwall panels)
   */
  extractionRatio: 0.85,
  /**
   * Prototype assumption: empirical subsidence coefficient 'a'
   * (0.60–0.75 for fully caved longwall, Salamon 1963, Whittaker & Reddish 1989)
   */
  subsidenceCoefficient: 0.65,
  /**
   * Prototype assumption: angle of draw / influence angle measured from vertical
   * (25–35° is common for UK/Australian coal measures)
   */
  influenceAngleDeg: 27,

  // ─── Calibration ────────────────────────────────────────────────
  /**
   * Prototype calibration factor — applied as a final scalar multiplier.
   * Start at 1.0 (no scaling). Adjust after comparison with reference observations.
   * Do NOT automatically optimize using ML predictions.
   */
  calibrationFactor: 1.0,

  // ─── Temporal Factor ─────────────────────────────────────────────
  /**
   * Prototype assumption: temporal extraction factor [0,1].
   * 0 = mining not yet begun; 1 = full extraction length complete.
   * In demo mode this is derived from the dashboard stage (0–5 mapped to 0–1).
   * In live mode it should be updated from actual face advance records.
   */
  temporalFactor: 0.0,

  // ─── Surface Reference ───────────────────────────────────────────
  /** Prototype assumption: nominal surface level reference (meters above datum) */
  surfaceReferenceLevelM: 245.0,
};

/**
 * Stage-to-temporal-factor mapping.
 * Maps demonstration stages 0–5 to a temporal extraction factor [0,1].
 * Prototype assumption: 5 stages represent 0% → 100% panel advancement.
 */
export const STAGE_TEMPORAL_FACTORS: Record<number, number> = {
  0: 0.00,
  1: 0.18,
  2: 0.36,
  3: 0.56,
  4: 0.76,
  5: 1.00,
};

/**
 * Local coordinate positions of each sensor node (meters from panel datum origin).
 * These must match the SENSOR_LAYOUT % positions in lib/demo.ts after scaling.
 *
 * Coordinate system:
 *   Origin (0,0) = Western panel boundary at surface datum
 *   X = Easting (m)
 *   Y = Northing (m)
 *
 * Prototype assumption: positions derived from 900×530m working grid
 * matching the 1000×580 SVG viewport (scaled by 0.9× in each direction).
 */
export const NODE_LOCAL_COORDS: Record<string, { x: number; y: number }> = {
  "SN-001": { x: 162, y: 149 }, // 18% × 900, 28% × 530
  "SN-002": { x: 432, y: 217 }, // 48% × 900, 41% × 530
  "SN-003": { x: 684, y: 281 }, // 76% × 900, 53% × 530
};

/**
 * Local coordinate position of the protected asset A-001 (meters).
 * Prototype assumption: derived from 84%, 70% SVG position.
 */
export const ASSET_LOCAL_COORD = { x: 756, y: 371 };

/**
 * Extraction influence centroid — the surface projection of the midpoint
 * of the extraction goaf.
 * Prototype assumption: centroid aligns with Panel A corridor midpoint.
 */
export const EXTRACTION_CENTROID = { x: 250, y: 230 };
