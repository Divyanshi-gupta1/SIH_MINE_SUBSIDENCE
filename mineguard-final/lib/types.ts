export type RiskState = "NORMAL" | "LOCAL_ANOMALY" | "PERSISTENT" | "CORRELATED" | "PROGRESSIVE" | "HIGH_RISK" | "CRITICAL";
export type ViewKey = "command" | "map" | "zones" | "sensors" | "alerts" | "history" | "network" | "physics" | "settings" | "demo";
export type AlertLifecycle = "NEW" | "ACKNOWLEDGED" | "VERIFICATION_PENDING" | "CONFIRMED" | "DISMISSED" | "SENSOR_ISSUE";
export type OperationMode = "DEMO" | "LIVE_TESTBED" | "LIVE_MINE";
export type ScenarioKey = "progressive" | "false_local" | "normal" | "persistent" | "offline_gap";
export type LayerKey = "grid" | "sensors" | "risk" | "assets" | "impact" | "network" | "physics" | "vectors" | "heatmap" | "residual" | "history";

export type NodeState = {
  id: string;
  zoneId: string;
  battery: number;
  rssi: number;
  lastSeen: string;
  tilt: number;
  displacement: number;
  deformationRate: number;
  vibration: number;
  healthy: boolean;
  quality: "GOOD" | "DEGRADED" | "UNAVAILABLE";
  modelClass: "normal" | "decoy_seismic" | "subsidence_precursor";
  modelConfidence: number;
  healthMessage?: string;
  baselineTilt?: number;
  baselineDisp?: number;
  deviationMm?: number;
  trend?: string;
  monitoringGap?: boolean;
};

export type ZoneState = {
  id: string;
  name: string;
  state: RiskState;
  trend: string;
  direction: string;
  confidence: "HIGH" | "MEDIUM" | "LOW";
  evidence: string[];
  assetDistanceM: number;
  physicsExpectedMm?: number;
  observedMm?: number;
  physicsResidualMm?: number;
  physicsStatus?: string;
  temporalStatus?: string;
  modelVerdict?: string;
  assetImpact?: string;
};

export type Alert = {
  id: string;
  zoneId: string;
  nodeId?: string;
  severity: "WATCH" | "HIGH" | "CRITICAL";
  title: string;
  summary: string;
  evidence: string[];
  confidence: "HIGH" | "MEDIUM" | "LOW";
  lifecycle: AlertLifecycle;
  created: string;
  recommendedAction: string;
  assetId?: string;
  assetContext?: string;
};

export type Asset = {
  id: string;
  label: string;
  type: string;
  x: number;
  y: number;
  impactStatus: "NO CURRENT IMPACT" | "NEAR IMPACT ZONE" | "AT RISK";
  nearestZoneId: string;
  distanceM: number;
  context: string;
};
