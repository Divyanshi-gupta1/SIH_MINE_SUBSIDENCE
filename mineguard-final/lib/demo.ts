import type { Alert, Asset, NodeState, RiskState, ScenarioKey, ZoneState } from "./types";
import { calculatePeckSubsidence, calculatePhysicsResidual } from "./physics";

export const stageLabels = [
  "Normal",
  "Local anomaly",
  "Persistent",
  "Correlated",
  "Progressive",
  "High risk"
];

export const stageDescriptions = [
  "Baseline monitoring. No material deformation evidence is present.",
  "A localized deviation is visible; verification is appropriate before escalation.",
  "The abnormality persists and the deformation rate is increasing.",
  "Neighbouring nodes show corroborating movement across the monitoring area.",
  "Progression is spatially consistent and the assessed deformation front is moving toward the protected asset.",
  "Multiple lines of evidence support a high operational risk state. Verify conditions and follow site procedures."
];

export const rank: Record<RiskState, number> = {
  NORMAL: 0,
  LOCAL_ANOMALY: 1,
  PERSISTENT: 2,
  CORRELATED: 3,
  PROGRESSIVE: 4,
  HIGH_RISK: 5,
  CRITICAL: 6
};

export const SENSOR_LAYOUT = [
  { id: "SN-001", zoneId: "Z-001", x: 18, y: 28 },
  { id: "SN-002", zoneId: "Z-002", x: 48, y: 41 },
  { id: "SN-003", zoneId: "Z-003", x: 76, y: 53 }
] as const;

export const ZONE_LAYOUT = [
  { id: "Z-001", x: 10, y: 20, w: 25, h: 25 },
  { id: "Z-002", x: 34, y: 31, w: 29, h: 27 },
  { id: "Z-003", x: 63, y: 42, w: 27, h: 28 }
] as const;

export const ASSET: Asset = {
  id: "A-001",
  label: "Protected Structure",
  type: "Ventilation Shaft Headframe & Surface Substation",
  x: 84,
  y: 70,
  impactStatus: "NO CURRENT IMPACT",
  nearestZoneId: "Z-003",
  distanceM: 46,
  context: "High-value asset located 46m from monitoring perimeter. Requires early warning before deformation exceeds 5.0mm."
};

export const GATEWAY = { id: "GW-001", x: 86, y: 14 } as const;

export function getAssetStatus(stage: number, mode: ScenarioKey): Asset {
  let impactStatus: Asset["impactStatus"] = "NO CURRENT IMPACT";
  let context = "High-value asset located 46m from monitoring perimeter. Ground conditions stable.";

  if (mode === "progressive") {
    if (stage >= 5) {
      impactStatus = "AT RISK";
      context = "Assessed deformation front has reached the 50m buffer. Structural inspection recommended.";
    } else if (stage >= 4) {
      impactStatus = "NEAR IMPACT ZONE";
      context = "Deformation vector projecting toward A-001 at 0.22 mm/min. Buffer proximity: 46m.";
    }
  }

  return {
    ...ASSET,
    impactStatus,
    context
  };
}

export function zonesFor(stage: number, mode: ScenarioKey): ZoneState[] {
  // Baseline distances from trough center (corridor origin at Z-001)
  const zoneDistancesM = [0, 42, 88];

  const base: ZoneState[] = [
    {
      id: "Z-001",
      name: "Western panel edge",
      state: "NORMAL",
      trend: "Stable",
      direction: "—",
      confidence: "HIGH",
      evidence: ["Observed deformation within noise floor", "Three-node baseline intact"],
      assetDistanceM: 120,
      temporalStatus: "Baseline (undisturbed)",
      modelVerdict: "normal",
      assetImpact: "None"
    },
    {
      id: "Z-002",
      name: "Central convergence corridor",
      state: "NORMAL",
      trend: "Stable",
      direction: "—",
      confidence: "HIGH",
      evidence: ["Observed deformation within noise floor", "No tilt departure"],
      assetDistanceM: 84,
      temporalStatus: "Baseline (undisturbed)",
      modelVerdict: "normal",
      assetImpact: "None"
    },
    {
      id: "Z-003",
      name: "Asset-side monitoring area",
      state: "NORMAL",
      trend: "Stable",
      direction: "—",
      confidence: "HIGH",
      evidence: ["Observed deformation within noise floor", "Buffer zone intact"],
      assetDistanceM: 46,
      temporalStatus: "Baseline (undisturbed)",
      modelVerdict: "normal",
      assetImpact: "Protected structure buffer clear"
    }
  ];

  if (mode === "normal") {
    return enrichWithPhysics(base, stage, zoneDistancesM);
  }

  if (mode === "offline_gap") {
    base[0] = {
      ...base[0],
      state: "NORMAL",
      trend: "Stable",
      confidence: "HIGH",
      evidence: ["SN-001 active and nominal"]
    };
    base[1] = {
      ...base[1],
      state: "LOCAL_ANOMALY",
      trend: "Monitoring Gap (Telemetry Lost)",
      direction: "Unknown",
      confidence: "LOW",
      evidence: [
        "MONITORING GAP: SN-002 offline for >30 seconds",
        "DATA CONFIDENCE REDUCED: missing telemetry must NOT be treated as zero deformation",
        "Mesh gateway checking signal path"
      ],
      temporalStatus: "Telemetry gap detected",
      modelVerdict: "DATA_UNAVAILABLE",
      assetImpact: "Unknown due to coverage gap"
    };
    base[2] = {
      ...base[2],
      state: "NORMAL",
      trend: "Stable",
      confidence: "MEDIUM",
      evidence: ["SN-003 nominal", "Spatial corridor validation degraded due to Z-002 gap"]
    };
    return enrichWithPhysics(base, stage, zoneDistancesM);
  }

  if (mode === "false_local") {
    if (stage >= 1) {
      base[1] = {
        ...base[1],
        state: "LOCAL_ANOMALY",
        trend: "Local vibration spike",
        direction: "Localized surface vibration",
        confidence: "MEDIUM",
        evidence: [
          "SN-002 transient vibration spike (0.28g)",
          "RF v6 classifier: decoy_seismic (vehicle / surface blast)",
          "Neighbour nodes SN-001 & SN-003 show zero displacement corroboration"
        ],
        temporalStatus: "Transient surface disturbance",
        modelVerdict: "decoy_seismic",
        assetImpact: "No ground displacement threat"
      };
    }
    if (stage >= 3) {
      base[1] = {
        ...base[1],
        state: "PERSISTENT",
        trend: "Attenuating vibration",
        confidence: "HIGH",
        evidence: [
          "Vibration decayed back toward baseline",
          "Tilt and displacement remain flat (<0.10mm)",
          "Spatial corroboration absent: non-geotechnical event confirmed"
        ],
        temporalStatus: "Dissipating local decoy",
        modelVerdict: "decoy_seismic",
        assetImpact: "None"
      };
    }
    return enrichWithPhysics(base, stage, zoneDistancesM);
  }

  if (mode === "persistent") {
    if (stage >= 1) {
      base[0] = {
        ...base[0],
        state: "LOCAL_ANOMALY",
        trend: "Slight departure",
        direction: "East",
        confidence: "HIGH",
        evidence: ["Tilt departure +0.12°", "Displacement 0.45mm above baseline"],
        temporalStatus: "Early departure",
        modelVerdict: "subsidence_precursor"
      };
    }
    if (stage >= 2) {
      base[0] = {
        ...base[0],
        state: "PERSISTENT",
        trend: "Sustained elevation",
        direction: "East",
        confidence: "HIGH",
        evidence: ["Abnormality persists across 3 consecutive evaluation windows", "Deformation rate 0.08 mm/min"],
        temporalStatus: "Persistent slow creep",
        modelVerdict: "subsidence_precursor"
      };
      base[1] = {
        ...base[1],
        state: "LOCAL_ANOMALY",
        trend: "Early response",
        direction: "East",
        confidence: "MEDIUM",
        evidence: ["Incipient strain detected at corridor boundary"],
        temporalStatus: "Corridor boundary transition"
      };
    }
    return enrichWithPhysics(base, stage, zoneDistancesM);
  }

  // Progressive subsidence scenario
  if (stage >= 1) {
    base[0] = {
      ...base[0],
      state: "LOCAL_ANOMALY",
      trend: "Rising",
      direction: "East",
      confidence: "HIGH",
      evidence: ["Tilt departure detected (+0.18°)", "Displacement above local baseline (+0.80mm)"],
      temporalStatus: "Initial trough sag",
      modelVerdict: "subsidence_precursor"
    };
  }
  if (stage >= 2) {
    base[0] = {
      ...base[0],
      state: "PERSISTENT",
      trend: "Increasing",
      direction: "East / SE",
      confidence: "HIGH",
      evidence: ["Abnormality persists over 4 observation windows", "Deformation rate increasing (0.08 mm/min)"],
      temporalStatus: "Persistent displacement",
      modelVerdict: "subsidence_precursor"
    };
  }
  if (stage >= 3) {
    base[0] = {
      ...base[0],
      state: "CORRELATED",
      trend: "Increasing",
      direction: "East / SE",
      confidence: "HIGH",
      evidence: ["Three-node spatial correlation", "Tilt and displacement corroborate", "RF v6 confidence: 84%"],
      temporalStatus: "Multi-node spatial correlation",
      modelVerdict: "subsidence_precursor"
    };
    base[1] = {
      ...base[1],
      state: "CORRELATED",
      trend: "Rising",
      direction: "East",
      confidence: "HIGH",
      evidence: ["Neighbour node agreement", "Deformation rate increasing (0.14 mm/min)"],
      temporalStatus: "Corridor convergence active",
      modelVerdict: "subsidence_precursor"
    };
  }
  if (stage >= 4) {
    base[0] = {
      ...base[0],
      state: "PROGRESSIVE",
      trend: "Accelerating",
      direction: "East / SE",
      confidence: "HIGH",
      evidence: ["Three-node correlation", "Rate accelerating (0.22 mm/min)", "Directional progression assessed toward asset"],
      temporalStatus: "Active deformation front",
      modelVerdict: "subsidence_precursor",
      assetImpact: "Front 84m from asset A-001"
    };
    base[1] = {
      ...base[1],
      state: "PROGRESSIVE",
      trend: "Accelerating",
      direction: "East",
      confidence: "HIGH",
      evidence: ["Progression consistent with neighbouring nodes", "Deformation front moving toward asset corridor"],
      temporalStatus: "Active deformation front",
      modelVerdict: "subsidence_precursor",
      assetImpact: "Deformation corridor advancing"
    };
  }
  if (stage >= 5) {
    base[0] = {
      ...base[0],
      state: "HIGH_RISK",
      trend: "Strong increase",
      direction: "East / SE",
      confidence: "HIGH",
      evidence: ["Three-node corroboration", "Persistent abnormality", "Rate 0.34 mm/min", "Sensor health normal"],
      temporalStatus: "Critical ground displacement",
      modelVerdict: "subsidence_precursor",
      assetImpact: "Corridor boundary impacted"
    };
    base[1] = {
      ...base[1],
      state: "HIGH_RISK",
      trend: "Strong increase",
      direction: "East / SE",
      confidence: "HIGH",
      evidence: ["Multi-node progression", "Impact geometry expanding toward asset", "Sensor health normal"],
      temporalStatus: "Critical ground displacement",
      modelVerdict: "subsidence_precursor",
      assetImpact: "Deformation front 46m from A-001"
    };
    base[2] = {
      ...base[2],
      state: "PROGRESSIVE",
      trend: "Emerging front",
      direction: "East / SE",
      confidence: "MEDIUM",
      evidence: ["Early deformation signature at asset perimeter", "Spatial progression assessed"],
      temporalStatus: "Boundary encroachment",
      modelVerdict: "subsidence_precursor",
      assetImpact: "Buffer perimeter reached (A-001 at risk)"
    };
  }

  return enrichWithPhysics(base, stage, zoneDistancesM);
}

function enrichWithPhysics(zones: ZoneState[], stage: number, zoneDistancesM: number[]): ZoneState[] {
  return zones.map((zone, idx) => {
    const distM = zoneDistancesM[idx] ?? idx * 40;
    const peck = calculatePeckSubsidence(distM, stage);
    // Observed displacement for the zone
    const observedMm = zone.state === "NORMAL"
      ? 0.15
      : zone.state === "LOCAL_ANOMALY"
        ? 0.75
        : zone.state === "PERSISTENT"
          ? 1.65
          : zone.state === "CORRELATED"
            ? 2.80
            : zone.state === "PROGRESSIVE"
              ? 4.60
              : 6.45;

    const res = calculatePhysicsResidual(observedMm, peck.expectedSubsidenceMm);

    return {
      ...zone,
      physicsExpectedMm: peck.expectedSubsidenceMm,
      observedMm,
      physicsResidualMm: res.residualMm,
      physicsStatus: res.agreementStatus
    };
  });
}

export function nodesFor(stage: number, mode: ScenarioKey): NodeState[] {
  const normal = [0.03, 0.02, 0.02];
  const movement = mode === "normal"
    ? normal
    : mode === "false_local"
      ? [0.03, stage >= 1 ? 0.48 : 0.02, 0.02]
      : mode === "persistent"
        ? [stage * 0.06 + 0.02, stage * 0.04 + 0.02, 0.02]
        : [stage * 0.10 + 0.02, stage * 0.08 + 0.02, stage * 0.04 + 0.02];

  return SENSOR_LAYOUT.map((sensor, i) => {
    const base = movement[i];
    const deformationRate = mode === "normal" ? 0.02 + i * 0.01 : Number((0.03 + base * (0.45 + stage * 0.05)).toFixed(2));
    const precursor = (mode === "progressive" || mode === "persistent") && stage >= 2 && i < 2;
    const localDisturbance = mode === "false_local" && i === 1 && stage >= 1;
    const isOfflineGap = mode === "offline_gap" && i === 1;

    const modelClass: NodeState["modelClass"] = precursor
      ? "subsidence_precursor"
      : localDisturbance
        ? "decoy_seismic"
        : "normal";

    const confidence = precursor
      ? Math.min(0.97, 0.68 + stage * 0.05)
      : localDisturbance
        ? 0.94
        : 0.96;

    if (isOfflineGap) {
      return {
        id: sensor.id,
        zoneId: sensor.zoneId,
        battery: 82,
        rssi: -105,
        lastSeen: ">30s ago",
        tilt: 0.14,
        displacement: 1.10,
        deformationRate: 0.08,
        vibration: 0.04,
        healthy: false,
        quality: "UNAVAILABLE",
        modelClass: "normal",
        modelConfidence: 0.50,
        healthMessage: "Monitoring gap detected: no signal for >30s (reduced data confidence)",
        baselineTilt: 0.02,
        baselineDisp: 0.00,
        deviationMm: 1.10,
        trend: "Offline Gap",
        monitoringGap: true
      };
    }

    const baselineTilt = 0.02;
    const baselineDisp = 0.00;
    const currentTilt = Number(base.toFixed(2));
    const currentDisp = Number((base * 10 + (stage > 3 && i < 2 ? 1.2 : 0)).toFixed(2));

    return {
      id: sensor.id,
      zoneId: sensor.zoneId,
      battery: 92 - i * 5,
      rssi: -64 - i * 4,
      lastSeen: "just now",
      tilt: currentTilt,
      displacement: currentDisp,
      deformationRate,
      vibration: Number((0.03 + (localDisturbance ? 0.25 : 0.05) + base * 0.42).toFixed(2)),
      healthy: true,
      quality: "GOOD",
      modelClass,
      modelConfidence: confidence,
      baselineTilt,
      baselineDisp,
      deviationMm: Number((currentDisp - baselineDisp).toFixed(2)),
      trend: precursor ? "Progressive escalation" : localDisturbance ? "Transient vibration" : "Nominal baseline",
      monitoringGap: false
    };
  });
}

export function alertsFor(zones: ZoneState[], stage: number, mode: ScenarioKey): Alert[] {
  if (mode === "offline_gap") {
    return [
      {
        id: "ALT-GAP-001",
        zoneId: "Z-002",
        nodeId: "SN-002",
        severity: "WATCH",
        title: "Z-002 / SN-002: Monitoring gap detected (>30s silence)",
        summary: "Node SN-002 has ceased reporting telemetry. Missing data is NOT treated as zero deformation. Data confidence is reduced for the central corridor.",
        evidence: [
          "No radio packet received from SN-002 for >30 seconds",
          "Mesh gateway GW-001 RSSI dropped below threshold",
          "Spatial coverage incomplete for corridor convergence analysis",
          "Sensor health marked UNAVAILABLE"
        ],
        confidence: "LOW",
        lifecycle: "NEW",
        created: "just now",
        recommendedAction: "Check node power supply, radio line-of-sight, or gateway mesh connectivity.",
        assetId: "A-001",
        assetContext: "Corridor monitoring interrupted; buffer assessment degraded."
      }
    ];
  }

  if (mode === "false_local") {
    const localZone = zones.find((zone) => zone.id === "Z-002" && zone.state !== "NORMAL");
    if (!localZone) return [];
    return [
      {
        id: "ALT-LOCAL-001",
        zoneId: localZone.id,
        nodeId: "SN-002",
        severity: "WATCH",
        title: "Z-002 / SN-002: Local transient disturbance requires verification",
        summary: "Single-node vibration spike classified as decoy_seismic (vehicle / surface blast). Spatial agreement across neighbouring nodes is zero.",
        evidence: [
          "SN-002 vibration spike (0.28g) without sustained tilt change",
          "Zero movement corroboration from SN-001 (0.02 mm) or SN-003 (0.02 mm)",
          "Random Forest v6 model confidence: 94% (decoy_seismic)",
          "Sensor health normal; no geotechnical displacement assessed"
        ],
        confidence: localZone.confidence,
        lifecycle: "NEW",
        created: `Demo +${stage * 10} min`,
        recommendedAction: "Inspect node location to confirm surface equipment activity before any evacuation decision.",
        assetId: "A-001",
        assetContext: "Protected structure buffer unaffected."
      }
    ];
  }

  const z = zones.find((x) => rank[x.state] >= rank.PROGRESSIVE);
  if (!z) return [];
  const isCritical = z.state === "HIGH_RISK" || z.state === "CRITICAL";

  return [
    {
      id: "ALT-001",
      zoneId: z.id,
      nodeId: z.id === "Z-001" ? "SN-001" : "SN-002",
      severity: isCritical ? "CRITICAL" : "HIGH",
      title: `${z.id}: Persistent ground deformation detected`,
      summary: "Multiple corroborating lines of evidence confirm progressive ground movement advancing toward the protected surface asset corridor.",
      evidence: [
        "3-node spatial correlation across Western panel edge and Central corridor",
        "Increasing relative displacement (up to " + (z.observedMm?.toFixed(2) ?? "4.60") + " mm)",
        "Increasing deformation rate (0.22 - 0.34 mm/min)",
        "Persistent anomaly across multiple observation windows",
        "Sensor health normal across all reporting nodes",
        "Empirical Peck subsidence model confirms trough inflection advance"
      ],
      confidence: z.confidence,
      lifecycle: "NEW",
      created: `Demo +${stage * 10} min`,
      recommendedAction: stage >= 5
        ? "Verify field conditions immediately and follow site geotechnical control procedure."
        : "Conduct visual inspection of the Western panel boundary and verify rate progression.",
      assetId: "A-001",
      assetContext: stage >= 5 ? "A-001 protected structure buffer reached (<50m proximity)" : "Approaching A-001 protected structure corridor"
    }
  ];
}

export function timelineFor(stage: number) {
  return Array.from({ length: 6 }, (_, i) => ({
    minute: i * 10,
    state: stageLabels[Math.min(i, 5)],
    active: i <= stage,
    displacement: [0.4, 0.8, 1.5, 2.7, 4.4, 6.2][i],
    rate: [0.02, 0.05, 0.08, 0.14, 0.22, 0.34][i]
  }));
}

export function overallState(zones: ZoneState[]): RiskState {
  return zones.reduce((state, zone) => rank[zone.state] > rank[state] ? zone.state : state, "NORMAL" as RiskState);
}
