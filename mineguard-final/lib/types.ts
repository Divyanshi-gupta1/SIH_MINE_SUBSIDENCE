export type RiskState = "NORMAL" | "LOCAL_ANOMALY" | "PERSISTENT" | "CORRELATED" | "PROGRESSIVE" | "HIGH_RISK" | "CRITICAL";
export type ViewKey = "command" | "map" | "zones" | "sensors" | "alerts" | "history" | "network" | "settings" | "demo";
export type AlertLifecycle = "NEW" | "ACKNOWLEDGED" | "VERIFICATION_PENDING" | "CONFIRMED" | "DISMISSED";

export type NodeState = {
  id: string;
  battery: number;
  rssi: number;
  lastSeen: string;
  tilt: number;
  displacement: number;
  vibration: number;
  healthy: boolean;
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
};

export type Alert = {
  id: string;
  zoneId: string;
  severity: "WATCH" | "HIGH" | "CRITICAL";
  title: string;
  summary: string;
  evidence: string[];
  confidence: "HIGH" | "MEDIUM" | "LOW";
  lifecycle: AlertLifecycle;
  created: string;
};
