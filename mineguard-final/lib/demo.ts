import type { Alert, NodeState, RiskState, ScenarioKey, ZoneState } from "./types";

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

export const ASSET = { id: "A-001", x: 84, y: 70, label: "Protected asset" } as const;
export const GATEWAY = { id: "GW-001", x: 86, y: 14 } as const;

export function zonesFor(stage: number, mode: ScenarioKey): ZoneState[] {
  const base: ZoneState[] = [
    {
      id: "Z-001",
      name: "Western panel edge",
      state: "NORMAL",
      trend: "Stable",
      direction: "—",
      confidence: "HIGH",
      evidence: ["No material deformation evidence"],
      assetDistanceM: 120
    },
    {
      id: "Z-002",
      name: "Central convergence corridor",
      state: "NORMAL",
      trend: "Stable",
      direction: "—",
      confidence: "HIGH",
      evidence: ["No material deformation evidence"],
      assetDistanceM: 84
    },
    {
      id: "Z-003",
      name: "Asset-side monitoring area",
      state: "NORMAL",
      trend: "Stable",
      direction: "—",
      confidence: "HIGH",
      evidence: ["No material deformation evidence"],
      assetDistanceM: 46
    }
  ];

  if (mode === "normal") return base;

  if (mode === "false_local") {
    if (stage >= 1) {
      base[1] = {
        ...base[1],
        state: "LOCAL_ANOMALY",
        trend: "Local spike",
        direction: "Local",
        confidence: "MEDIUM",
        evidence: ["SN-002 deviates from baseline", "Neighbour agreement is low", "Other nodes remain nominal"]
      };
    }
    if (stage >= 3) {
      base[1] = {
        ...base[1],
        state: "PERSISTENT",
        trend: "Still elevated",
        confidence: "MEDIUM",
        evidence: ["SN-002 remains elevated", "Spatial corroboration is still limited"]
      };
    }
    return base;
  }

  if (stage >= 1) {
    base[0] = {
      ...base[0],
      state: "LOCAL_ANOMALY",
      trend: "Rising",
      direction: "East",
      confidence: "HIGH",
      evidence: ["Tilt deviation detected", "Displacement above local baseline"]
    };
  }
  if (stage >= 2) {
    base[0] = {
      ...base[0],
      state: "PERSISTENT",
      trend: "Increasing",
      evidence: ["Abnormality persists", "Deformation rate increasing"]
    };
  }
  if (stage >= 3) {
    base[0] = {
      ...base[0],
      state: "CORRELATED",
      trend: "Increasing",
      evidence: ["Three-node spatial correlation", "Tilt and displacement agree"]
    };
    base[1] = {
      ...base[1],
      state: "CORRELATED",
      trend: "Rising",
      direction: "East",
      evidence: ["Neighbour node agreement", "Deformation rate increasing"]
    };
  }
  if (stage >= 4) {
    base[0] = {
      ...base[0],
      state: "PROGRESSIVE",
      trend: "Accelerating",
      direction: "East / SE",
      evidence: ["Three-node correlation", "Rate increasing", "Directional progression assessed"]
    };
    base[1] = {
      ...base[1],
      state: "PROGRESSIVE",
      trend: "Accelerating",
      direction: "East",
      evidence: ["Progression consistent with neighbouring nodes", "Deformation front moving toward asset"]
    };
  }
  if (stage >= 5) {
    base[0] = {
      ...base[0],
      state: "HIGH_RISK",
      trend: "Strong increase",
      confidence: "HIGH",
      evidence: ["Three-node corroboration", "Persistent abnormality", "Rate increasing", "Sensor health normal"]
    };
    base[1] = {
      ...base[1],
      state: "HIGH_RISK",
      trend: "Strong increase",
      confidence: "HIGH",
      evidence: ["Multi-node progression", "Impact geometry expanding toward asset", "Sensor health normal"]
    };
    base[2] = {
      ...base[2],
      state: "PROGRESSIVE",
      trend: "Emerging",
      confidence: "MEDIUM",
      evidence: ["Early deformation signature", "Spatial progression assessed"]
    };
  }

  return base;
}

export function nodesFor(stage: number, mode: ScenarioKey): NodeState[] {
  const normal = [0.03, 0.02, 0.02];
  const movement = mode === "normal"
    ? normal
    : mode === "false_local"
      ? [0.03, stage >= 1 ? 0.48 : 0.02, 0.02]
      : [stage * 0.10 + 0.02, stage * 0.08 + 0.02, stage * 0.04 + 0.02];

  return SENSOR_LAYOUT.map((sensor, i) => {
    const base = movement[i];
    const deformationRate = mode === "normal" ? 0.02 + i * 0.01 : Number((0.03 + base * (0.45 + stage * 0.05)).toFixed(2));
    const precursor = mode === "progressive" && stage >= 3 && i < 2;
    const localDisturbance = mode === "false_local" && i === 1 && stage >= 1;
    const modelClass: NodeState["modelClass"] = precursor ? "subsidence_precursor" : localDisturbance ? "decoy_seismic" : "normal";
    const confidence = precursor ? Math.min(0.97, 0.68 + stage * 0.05) : localDisturbance ? 0.94 : 0.96;
    return {
      id: sensor.id,
      zoneId: sensor.zoneId,
      battery: 92 - i * 5,
      rssi: -64 - i * 4,
      lastSeen: "just now",
      tilt: Number(base.toFixed(2)),
      displacement: Number((base * 10 + (stage > 3 && i < 2 ? 1.2 : 0)).toFixed(2)),
      deformationRate,
      vibration: Number((0.03 + (localDisturbance ? 0.25 : 0.05) + base * 0.42).toFixed(2)),
      healthy: true,
      quality: "GOOD",
      modelClass,
      modelConfidence: confidence
    };
  });
}

export function alertsFor(zones: ZoneState[], stage: number, mode: ScenarioKey): Alert[] {
  if (mode === "false_local") {
    const localZone = zones.find((zone) => zone.id === "Z-002" && zone.state !== "NORMAL");
    if (!localZone) return [];
    return [
      {
        id: "ALT-LOCAL-001",
        zoneId: localZone.id,
        nodeId: "SN-002",
        severity: "WATCH",
        title: "SN-002: local anomaly requires verification",
        summary: "A single node has departed from baseline without sufficient spatial corroboration. Treat this as a verification event, not a zone-wide critical condition.",
        evidence: localZone.evidence,
        confidence: localZone.confidence,
        lifecycle: "NEW",
        created: `Demo +${stage * 10} min`,
        recommendedAction: "Inspect the node and verify the local disturbance before escalation."
      }
    ];
  }

  const z = zones.find((x) => rank[x.state] >= rank.PROGRESSIVE);
  if (!z) return [];
  return [
    {
      id: "ALT-001",
      zoneId: z.id,
      severity: z.state === "HIGH_RISK" || z.state === "CRITICAL" ? "CRITICAL" : "HIGH",
      title: `${z.id}: progressive deformation assessed`,
      summary: "Multiple lines of evidence indicate persistent and increasing deformation. Review the affected zone and verify site conditions.",
      evidence: z.evidence,
      confidence: z.confidence,
      lifecycle: "NEW",
      created: `Demo +${stage * 10} min`,
      recommendedAction: stage >= 5 ? "Verify field conditions and follow the mine's established response procedure." : "Inspect the affected zone and verify the observed progression."
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
