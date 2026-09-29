/**
 * MineGuard Physics Intelligence Module — Type Definitions
 *
 * SCOPE: Simplified prototype physics model for the MineGuard testbed.
 * These types define the data contracts between the physics engine and
 * the dashboard visualization layer.
 *
 * IMPORTANT DISCLAIMER:
 * "The prototype uses a simplified calibrated physics model; field deployment
 * requires site-specific calibration using mining, geological and
 * survey/InSAR observations."
 */

// ─── Input parameter types ──────────────────────────────────────────

/**
 * All configurable mining geometry and geotechnical parameters for the
 * prototype physics model. Every field is explicitly labelled as a
 * "Prototype assumption" in the UI.
 */
export interface PhysicsParameters {
  /** Prototype assumption: longwall panel width along strike (meters) */
  panelWidthM: number;
  /** Prototype assumption: longwall panel length along dip (meters) */
  panelLengthM: number;
  /** Prototype assumption: seam depth below surface (meters) */
  panelDepthM: number;
  /** Prototype assumption: extracted seam thickness (meters) */
  extractedThicknessM: number;
  /** Prototype assumption: panel extraction ratio (0–1, ~0.85 for caved longwall) */
  extractionRatio: number;
  /** Prototype assumption: empirical subsidence coefficient 'a' (0–1) */
  subsidenceCoefficient: number;
  /** Prototype assumption: angle of influence from vertical (degrees) */
  influenceAngleDeg: number;
  /**
   * Prototype calibration factor applied to raw physics prediction.
   * Scaled result = raw_physics × calibrationFactor.
   * Distinct from subsidenceCoefficient — this is an explicit site calibration multiplier.
   */
  calibrationFactor: number;
  /**
   * Temporal extraction factor [0,1] representing the fraction of panel
   * currently extracted. Advances monotonically as mining progresses.
   */
  temporalFactor: number;
  /** Reference surface elevation for local coordinate datum (m) */
  surfaceReferenceLevelM: number;
}

// ─── Output types ───────────────────────────────────────────────────

/** Expected deformation at a single spatial point */
export interface PhysicsPoint {
  /** Local easting coordinate (m) */
  x: number;
  /** Local northing coordinate (m) */
  y: number;
  /** Knothe-style influence function value I(r) at this point [0,1] */
  influenceValue: number;
  /** Smax(t) × I(r) — raw before calibration (mm) */
  rawPredictionMm: number;
  /** rawPredictionMm × calibrationFactor (mm) */
  expectedDeformationMm: number;
}

/** Full spatial expected-deformation grid */
export interface PhysicsGrid {
  /** Grid cells (flattened row-major) */
  points: PhysicsPoint[];
  /** Grid columns */
  cols: number;
  /** Grid rows */
  rows: number;
  /** Max expected deformation in the grid (mm) */
  sMaxMm: number;
  /** Influence radius R (m) derived from depth + angle */
  influenceRadiusM: number;
  /** Centroid of extraction influence (local coords, m) */
  influenceCentroidX: number;
  influenceCentroidY: number;
}

/** Physics computation output for a single sensor observation point */
export interface SensorPhysicsOutput {
  nodeId: string;
  /** Observed displacement from existing sensor data (mm) */
  observedMm: number;
  /** Expected deformation from Knothe-style model at this node location (mm) */
  expectedMm: number;
  /** signed residual = observedMm − expectedMm */
  residualMm: number;
  /**
   * Agreement category.
   * HIGH    → |residual| ≤ 0.30 mm
   * MODERATE → |residual| ≤ 1.20 mm
   * LOW     → |residual| > 1.20 mm
   */
  physicsAgreement: "HIGH" | "MODERATE" | "LOW";
  /** Human-readable note about residual status */
  residualNote: string;
}

/**
 * Full physics intelligence snapshot — passed to UI components.
 * The ML pipeline output is attached here alongside physics output so
 * the UI can render both WITHOUT the physics layer modifying the ML verdict.
 */
export interface PhysicsIntelligenceSnapshot {
  /** Input parameters used to generate this snapshot */
  params: PhysicsParameters;
  /** Full spatial expected-deformation grid */
  grid: PhysicsGrid;
  /** Per-sensor physics analysis */
  sensorOutputs: SensorPhysicsOutput[];
  /** Timestamp of this computation (ISO 8601) */
  computedAt: string;
  /** Model version tag */
  modelVersion: "SIMPLIFIED_KNOTHE_PROTOTYPE_v1";
}
