import * as assert from "node:assert/strict";

import {
  calculateExpectedDeformation,
  calculateSmax,
  deriveInfluenceRadius,
  gaussianInfluence,
} from "./knothe";
import { PROTOTYPE_PARAMETERS, EXTRACTION_CENTROID } from "./parameters";
import { generatePhysicsGrid } from "./pim";
import { calculateSensorResiduals } from "./residual";
import type { NodeState } from "../types";

console.log("=== RUNNING PHYSICS MODULE VALIDATION TESTS ===");

// 1. Zero extraction -> approximately zero expected deformation
{
  const zeroParams = {
    ...PROTOTYPE_PARAMETERS,
    temporalFactor: 0.0,
    extractedThicknessM: 0.0,
  };
  const sMax = calculateSmax(zeroParams);
  assert.equal(sMax, 0, "Smax must be 0 for zero extraction thickness");

  const pt = calculateExpectedDeformation(
    EXTRACTION_CENTROID.x,
    EXTRACTION_CENTROID.y,
    EXTRACTION_CENTROID.x,
    EXTRACTION_CENTROID.y,
    zeroParams
  );
  assert.equal(pt.expectedDeformationMm, 0, "Expected deformation must be 0 for zero extraction");
  console.log("✔ Test 1 Passed: Zero extraction -> zero expected deformation");
}

// 2. Increased extraction thickness -> increased predicted deformation
{
  const baseParams = {
    ...PROTOTYPE_PARAMETERS,
    temporalFactor: 1.0,
    extractedThicknessM: 1.5,
  };
  const thickerParams = {
    ...PROTOTYPE_PARAMETERS,
    temporalFactor: 1.0,
    extractedThicknessM: 3.0,
  };

  const sMax1 = calculateSmax(baseParams);
  const sMax2 = calculateSmax(thickerParams);

  assert.ok(sMax2 > sMax1, `Thicker seam (${sMax2}mm) must yield higher Smax than base (${sMax1}mm)`);

  const pt1 = calculateExpectedDeformation(250, 230, 250, 230, baseParams);
  const pt2 = calculateExpectedDeformation(250, 230, 250, 230, thickerParams);

  assert.ok(
    pt2.expectedDeformationMm > pt1.expectedDeformationMm,
    "Expected deformation must scale directly with seam thickness"
  );
  console.log("✔ Test 2 Passed: Increased extraction thickness -> increased predicted deformation");
}

// 3. Increased distance from influence center -> reduced influence
{
  const R = deriveInfluenceRadius(PROTOTYPE_PARAMETERS);
  assert.ok(R > 100, "Influence radius must be realistic (>100m)");

  const i0 = gaussianInfluence(0, R);
  const i50 = gaussianInfluence(50, R);
  const i150 = gaussianInfluence(150, R);
  const i300 = gaussianInfluence(300, R);

  assert.equal(i0, 1.0, "Influence at centroid must be exactly 1.0");
  assert.ok(i0 > i50, "Influence at 0m must be greater than at 50m");
  assert.ok(i50 > i150, "Influence at 50m must be greater than at 150m");
  assert.ok(i150 > i300, "Influence at 150m must be greater than at 300m");
  console.log("✔ Test 3 Passed: Increased distance from influence center -> reduced influence");
}

// 4. Calibration factor scales prediction
{
  const activeParams = {
    ...PROTOTYPE_PARAMETERS,
    temporalFactor: 1.0,
    calibrationFactor: 1.0,
  };
  const scaledParams = {
    ...PROTOTYPE_PARAMETERS,
    temporalFactor: 1.0,
    calibrationFactor: 1.25,
  };

  const ptUnscaled = calculateExpectedDeformation(250, 230, 250, 230, activeParams);
  const ptScaled = calculateExpectedDeformation(250, 230, 250, 230, scaledParams);

  const expectedRatio = ptScaled.expectedDeformationMm / ptUnscaled.expectedDeformationMm;
  assert.ok(
    Math.abs(expectedRatio - 1.25) < 0.01,
    `Scaled deformation ratio (${expectedRatio}) must equal calibrationFactor (1.25)`
  );
  console.log("✔ Test 4 Passed: Calibration factor scales prediction");
}

// 5. Residual = observed - expected
{
  const grid = generatePhysicsGrid({ ...PROTOTYPE_PARAMETERS, temporalFactor: 0.5 });
  const dummyNodes: NodeState[] = [
    {
      id: "SN-001",
      zoneId: "Z-001",
      battery: 90,
      rssi: -65,
      lastSeen: "now",
      tilt: 0.1,
      displacement: 3.5,
      deformationRate: 0.05,
      vibration: 0.02,
      healthy: true,
      quality: "GOOD",
      modelClass: "subsidence_precursor",
      modelConfidence: 0.88,
    },
  ];

  const nodePositions = { "SN-001": { x: 18, y: 28 } };
  const outputs = calculateSensorResiduals(dummyNodes, grid, nodePositions);

  assert.equal(outputs.length, 1);
  const so = outputs[0];
  const expectedResidual = Number((so.observedMm - so.expectedMm).toFixed(2));
  assert.equal(
    so.residualMm,
    expectedResidual,
    `Calculated residual (${so.residualMm}) must equal observed (${so.observedMm}) - expected (${so.expectedMm})`
  );
  console.log("✔ Test 5 Passed: Residual = observed - expected");
}

// 6. Physics module does not modify ML output
{
  const originalNode: NodeState = {
    id: "SN-002",
    zoneId: "Z-002",
    battery: 85,
    rssi: -70,
    lastSeen: "now",
    tilt: 0.25,
    displacement: 2.1,
    deformationRate: 0.12,
    vibration: 0.28,
    healthy: true,
    quality: "GOOD",
    modelClass: "decoy_seismic", // Random forest output
    modelConfidence: 0.94,
  };

  const originalClass = originalNode.modelClass;
  const originalConfidence = originalNode.modelConfidence;

  const grid = generatePhysicsGrid(PROTOTYPE_PARAMETERS);
  const outputs = calculateSensorResiduals([originalNode], grid, { "SN-002": { x: 48, y: 41 } });

  // Assert original ML properties remain completely unmodified
  assert.equal(originalNode.modelClass, originalClass, "Node modelClass must not be modified by physics");
  assert.equal(originalNode.modelConfidence, originalConfidence, "Node modelConfidence must not be modified by physics");
  assert.ok(outputs[0].physicsAgreement !== undefined, "Physics produces parallel agreement output");
  console.log("✔ Test 6 Passed: Physics module does not modify ML output");
}

console.log("=== ALL 6 PHYSICS UNIT TESTS COMPLETED SUCCESSFULLY ===");
