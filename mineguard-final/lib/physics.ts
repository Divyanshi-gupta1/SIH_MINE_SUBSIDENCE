/**
 * MineGuard Engineering Physics Module
 * Ground subsidence calculations based on empirical Peck / Gaussian trough theory
 * for longwall coal mining panels.
 *
 * S(x) = S_max * exp(-x^2 / (2 * i^2))
 * where:
 *   S_max = maximum predicted center trough subsidence (mm)
 *   i     = distance from trough center to inflection point (m)
 *   x     = distance from panel center / extraction corridor (m)
 */

export interface PanelGeotechnicalProfile {
  panelId: string;
  overburdenDepthM: number;       // H (depth of seam)
  miningHeightM: number;          // m (extracted seam thickness)
  subsidenceFactor: number;       // a (empirical subsidence factor, typically 0.60 - 0.75 for caved longwall)
  troughAngleDeg: number;         // draw angle / inflection parameter
  inflectionDistanceM: number;    // i = H / (sqrt(2*pi) * tan(beta)) ~ 0.35 - 0.45 * H
}

export const DEFAULT_PANEL_PROFILE: PanelGeotechnicalProfile = {
  panelId: "PANEL_A_COAL",
  overburdenDepthM: 110,
  miningHeightM: 2.2,
  subsidenceFactor: 0.65,
  troughAngleDeg: 62,
  inflectionDistanceM: 44.0 // i in meters
};

/**
 * Calculates empirical Peck subsidence expected at distance x (meters) from subsidence center.
 */
export function calculatePeckSubsidence(
  distanceFromCenterM: number,
  stage: number,
  profile: PanelGeotechnicalProfile = DEFAULT_PANEL_PROFILE
): {
  expectedSubsidenceMm: number;
  expectedTiltMrad: number;
  expectedStrainMmPerM: number;
} {
  // S_max evolves with active panel extraction advance (stage 0 to 5)
  // Stage 0: undisturbed baseline (0 mm)
  // Stage 1: initial roof convergence (0.8 mm)
  // Stage 2: goaf compaction initiation (1.8 mm)
  // Stage 3: main roof sag (3.5 mm)
  // Stage 4: periodic weighting / caving (5.2 mm)
  // Stage 5: full surface trough development (7.0 mm)
  const stageScaling = [0.0, 0.8, 1.8, 3.5, 5.2, 7.0];
  const sMaxMm = stageScaling[Math.min(stage, 5)];

  const i = profile.inflectionDistanceM;
  const x = Math.abs(distanceFromCenterM);

  // Peck Gaussian profile: S(x) = S_max * exp(-x^2 / (2 * i^2))
  const expectedSubsidenceMm = sMaxMm * Math.exp(-(x * x) / (2 * i * i));

  // Slope / Tilt: T(x) = - (x / i^2) * S(x)
  const expectedTiltMrad = (x / (i * i)) * expectedSubsidenceMm * 1000; // in mm/m (mrad)

  // Curvature / Horizontal strain approximation
  const expectedStrainMmPerM = ((x * x - i * i) / (i * i * i * i)) * expectedSubsidenceMm * 1000;

  return {
    expectedSubsidenceMm: Number(expectedSubsidenceMm.toFixed(2)),
    expectedTiltMrad: Number(expectedTiltMrad.toFixed(2)),
    expectedStrainMmPerM: Number(expectedStrainMmPerM.toFixed(3))
  };
}

/**
 * Computes observed vs physics-expected residual:
 * Residual = |Observed - Physics Expected|
 * A high residual indicates non-standard behavior (geological faulting, anomalous shear, sensor drift).
 */
export function calculatePhysicsResidual(
  observedMm: number,
  expectedMm: number
): {
  residualMm: number;
  agreementStatus: "EXCELLENT" | "NOMINAL" | "ANOMALOUS_SHEAR" | "EVIDENCE_DIVERGENCE";
  notes: string;
} {
  const residualMm = Number(Math.abs(observedMm - expectedMm).toFixed(2));

  if (residualMm <= 0.3) {
    return {
      residualMm,
      agreementStatus: "EXCELLENT",
      notes: "Observed movement matches Peck trough profile within ±0.30mm."
    };
  }
  if (residualMm <= 1.2) {
    return {
      residualMm,
      agreementStatus: "NOMINAL",
      notes: "Deformation follows expected elastic subsidence curvature."
    };
  }
  if (residualMm <= 2.5) {
    return {
      residualMm,
      agreementStatus: "ANOMALOUS_SHEAR",
      notes: "Observed displacement exceeds standard Gaussian trough; possible joint slip."
    };
  }
  return {
    residualMm,
    agreementStatus: "EVIDENCE_DIVERGENCE",
    notes: "Significant divergence between empirical model and sensor readings. Physical inspection recommended."
  };
}

// Re-export isolated physics-intelligence module for unified access
export * from "./physics/index";

