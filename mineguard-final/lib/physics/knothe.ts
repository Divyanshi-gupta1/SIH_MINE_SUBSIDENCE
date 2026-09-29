/**
 * MineGuard Physics Intelligence Module — Knothe-style Influence Function
 *
 * Implements a SIMPLIFIED KNOTHE-STYLE INFLUENCE APPROXIMATION.
 *
 * ─── SCIENTIFIC SCOPE NOTICE ─────────────────────────────────────────────────
 * This is NOT a complete implementation of Knothe's original geomechanical
 * formulation. It is a simplified, calibrated approximation suitable for
 * prototype demonstration purposes only.
 *
 * The full Knothe model involves:
 *   - Integral formulation over the extraction face geometry
 *   - Site-specific trough parameter calibration
 *   - Time-dependent consolidation (Knothe time function)
 *   - Horizontal displacement and strain components
 *
 * This prototype implements only the vertical subsidence component using
 * a Gaussian influence function approximation.
 *
 * "The prototype uses a simplified calibrated physics model; field deployment
 * requires site-specific calibration using mining, geological and
 * survey/InSAR observations."
 * ─────────────────────────────────────────────────────────────────────────────
 *
 * Mathematical formulation used:
 *
 *   S(x,y,t) = Smax(t) × I(r)
 *
 * where:
 *   Smax(t) = q × m × a × τ(t)
 *     q = extraction ratio
 *     m = extracted thickness (m)
 *     a = subsidence coefficient
 *     τ(t) = temporal factor [0,1]
 *
 *   I(r) = exp( -(r/R)² )   [Gaussian influence approximation]
 *     r = distance from influence centroid to surface point (m)
 *     R = influence radius = panelDepth / tan(influenceAngle)
 *
 *   expected(x,y,t) = Smax(t) × I(r) × calibrationFactor
 *
 * Reference conceptual basis:
 *   Knothe (1957), Salamon (1963), Whittaker & Reddish (1989)
 */

import type { PhysicsParameters, PhysicsPoint } from "./types";

// ─── Influence radius derivation ─────────────────────────────────────

/**
 * Derives the influence radius R from panel depth and influence angle.
 * R = H / tan(influenceAngleDeg × π/180)
 *
 * For influenceAngleDeg = 27°, H = 110m → R ≈ 216m
 */
export function deriveInfluenceRadius(params: PhysicsParameters): number {
  const angleRad = (params.influenceAngleDeg * Math.PI) / 180;
  return params.panelDepthM / Math.tan(angleRad);
}

// ─── Maximum subsidence derivation ───────────────────────────────────

/**
 * Calculates Smax(t) — the maximum expected surface subsidence at the
 * trough centre for the current temporal extraction state.
 *
 *   Smax(t) = q × m × a × τ(t) × 1000   [result in mm]
 *
 * where:
 *   q = extraction ratio
 *   m = extracted thickness (m)
 *   a = subsidence coefficient
 *   τ = temporal factor [0,1]
 */
export function calculateSmax(params: PhysicsParameters): number {
  const { extractionRatio, extractedThicknessM, subsidenceCoefficient, temporalFactor } = params;
  const sMaxMetres = extractionRatio * extractedThicknessM * subsidenceCoefficient * temporalFactor;
  return sMaxMetres * 1000; // convert to mm
}

// ─── Gaussian influence function ─────────────────────────────────────

/**
 * Evaluates the Gaussian influence function I(r) at a given distance r.
 *
 *   I(r) = exp( -(r/R)² )
 *
 * Returns value in [0,1].
 * I(0) = 1.0 (maximum at centroid)
 * I(R) ≈ 0.368 (at influence radius)
 */
export function gaussianInfluence(r: number, influenceRadius: number): number {
  if (influenceRadius <= 0) return 0;
  return Math.exp(-((r * r) / (influenceRadius * influenceRadius)));
}

// ─── Single-point expected deformation ───────────────────────────────

/**
 * Calculates expected surface deformation at a single local-coordinate point.
 *
 *   S_expected(x,y,t) = Smax(t) × I(r) × calibrationFactor
 *
 * @param px - surface point local easting (m)
 * @param py - surface point local northing (m)
 * @param centroidX - extraction influence centroid easting (m)
 * @param centroidY - extraction influence centroid northing (m)
 * @param params - prototype mining parameters
 * @returns PhysicsPoint with all intermediate values
 */
export function calculateExpectedDeformation(
  px: number,
  py: number,
  centroidX: number,
  centroidY: number,
  params: PhysicsParameters
): PhysicsPoint {
  const R = deriveInfluenceRadius(params);
  const sMaxMm = calculateSmax(params);

  const r = Math.sqrt((px - centroidX) ** 2 + (py - centroidY) ** 2);
  const influenceValue = gaussianInfluence(r, R);
  const rawPredictionMm = sMaxMm * influenceValue;
  const expectedDeformationMm = rawPredictionMm * params.calibrationFactor;

  return {
    x: px,
    y: py,
    influenceValue: Number(influenceValue.toFixed(4)),
    rawPredictionMm: Number(rawPredictionMm.toFixed(3)),
    expectedDeformationMm: Number(expectedDeformationMm.toFixed(3)),
  };
}
