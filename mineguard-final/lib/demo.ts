import type { Alert, NodeState, RiskState, ZoneState } from "./types";

export const stageLabels = ["Normal", "Local anomaly", "Persistent", "Correlated", "Progressive", "High risk"];
export const rank: Record<RiskState, number> = {
  NORMAL: 0, LOCAL_ANOMALY: 1, PERSISTENT: 2, CORRELATED: 3, PROGRESSIVE: 4, HIGH_RISK: 5, CRITICAL: 6
};

export function zonesFor(stage: number, mode: "progressive" | "false_local" | "normal"): ZoneState[] {
  const names = ["Initial deformation", "Developing deformation", "Impact-direction zone"];
  const base: ZoneState[] = [0, 1, 2].map((i) => ({
    id: `Z${i + 1}`,
    name: names[i],
    state: "NORMAL",
    trend: "Stable",
    direction: "—",
    confidence: "HIGH",
    evidence: ["No material deformation evidence"],
    assetDistanceM: 120 - i * 36
  }));

  if (mode === "normal") return base;
  if (mode === "false_local") {
    if (stage >= 1) {
      base[1] = { ...base[1], state: "LOCAL_ANOMALY", trend: "Local spike", direction: "Local", confidence: "MEDIUM", evidence: ["N2 deviates from baseline", "Neighbour agreement is low"] };
    }
    return base;
  }
  if (stage >= 1) base[0] = { ...base[0], state: "LOCAL_ANOMALY", trend: "Rising", direction: "East", confidence: "HIGH", evidence: ["Tilt deviation detected", "Displacement above baseline"] };
  if (stage >= 2) base[0] = { ...base[0], state: "PERSISTENT", trend: "Increasing", evidence: ["Abnormality persists", "Displacement rate increasing"] };
  if (stage >= 3) {
    base[0] = { ...base[0], state: "CORRELATED", trend: "Increasing", evidence: ["3-node spatial correlation", "Tilt and displacement agree"] };
    base[1] = { ...base[1], state: "CORRELATED", trend: "Rising", direction: "East", evidence: ["Neighbour node agreement", "Rate increasing"] };
  }
  if (stage >= 4) {
    base[0] = { ...base[0], state: "PROGRESSIVE", trend: "Accelerating", direction: "East / SE", evidence: ["3-node correlation", "Rate increasing", "Directional progression assessed"] };
    base[1] = { ...base[1], state: "PROGRESSIVE", trend: "Accelerating", direction: "East", evidence: ["Progression consistent with neighbouring nodes", "Deformation front moving toward asset"] };
  }
  if (stage >= 5) {
    base[0] = { ...base[0], state: "HIGH_RISK", trend: "Strong increase", confidence: "HIGH", evidence: ["3-node corroboration", "Persistent abnormality", "Rate increasing", "Sensor health normal"] };
    base[1] = { ...base[1], state: "HIGH_RISK", trend: "Strong increase", confidence: "HIGH", evidence: ["Multi-node progression", "Impact geometry expanding toward asset", "Sensor health normal"] };
    base[2] = { ...base[2], state: "PROGRESSIVE", trend: "Emerging", confidence: "MEDIUM", evidence: ["Early deformation signature", "Spatial progression assessed"] };
  }
  return base;
}

export function nodesFor(stage: number, mode: "progressive" | "false_local" | "normal"): NodeState[] {
  const movement = mode === "normal" ? [0.03, 0.02, 0.02] : mode === "false_local" ? [0.03, stage >= 1 ? 0.48 : 0.02, 0.02] : [stage * 0.10 + 0.02, stage * 0.08 + 0.02, stage * 0.04 + 0.02];
  return ["N1", "N2", "N3"].map((id, i) => ({
    id,
    battery: 92 - i * 5,
    rssi: -64 - i * 4,
    lastSeen: "just now",
    tilt: Number(movement[i].toFixed(2)),
    displacement: Number((movement[i] * 10 + (stage > 3 && i < 2 ? 1.2 : 0)).toFixed(2)),
    vibration: Number((0.14 + movement[i] * 0.7).toFixed(2)),
    healthy: true
  }));
}

export function alertsFor(zones: ZoneState[], stage: number): Alert[] {
  const z = zones.find((x) => rank[x.state] >= rank.PROGRESSIVE);
  if (!z) return [];
  return [{
    id: "ALT-001",
    zoneId: z.id,
    severity: z.state === "HIGH_RISK" || z.state === "CRITICAL" ? "CRITICAL" : "HIGH",
    title: `${z.id}: progressive deformation assessed`,
    summary: "Multi-node evidence indicates persistent and increasing deformation. Review the affected zone and verify site conditions.",
    evidence: z.evidence,
    confidence: z.confidence,
    lifecycle: stage >= 5 ? "NEW" : "ACKNOWLEDGED",
    created: `+${stage * 10} min`
  }];
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
