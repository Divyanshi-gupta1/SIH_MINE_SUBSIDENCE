import fs from "fs";
import path from "path";
import type { Alert, NodeState, RiskState, ZoneState } from "./types";
import { nodesFor, zonesFor, alertsFor, overallState, SENSOR_LAYOUT } from "./demo";

export interface LiveHardwarePacket {
  node_id: string;
  timestamp: string;
  sequence: number;
  tilt_x_deg: number;
  tilt_y_deg: number;
  relative_displacement_mm: number;
  vibration_level: number;
  crack_detected: boolean;
  battery_percent: number;
  rssi: number;
  quality: string;
  temperature_c?: number;
  distance_cm?: number;
}

export interface LiveMLEvidence {
  node_id?: string;
  event_type: "normal" | "decoy_seismic" | "subsidence_precursor";
  anomaly: boolean;
  confidence: number;
  probabilities?: Record<string, number>;
  danger_level?: number;
  danger_category?: "Safe" | "Caution" | "Critical";
  trend?: string;
  persistence?: boolean;
  deformation_rate?: number;
  evidence?: string[];
  model_version?: string;
}

export interface LiveSystemState {
  schema_version: string;
  generated_at: string;
  is_live: boolean;
  stage: number;
  scenario: "progressive" | "false_local" | "normal";
  overall_state: RiskState;
  nodes: NodeState[];
  zones: ZoneState[];
  alerts: Alert[];
  local_monitoring: "ACTIVE" | "STANDBY";
  cloud: "CONNECTED" | "OFFLINE";
  ml_adapter: "READY" | "PROCESSING" | "OFFLINE";
  data_source: "LIVE_HARDWARE" | "DEMO";
  last_updated: string;
  node_last_times: Record<string, number>;
}

declare global {
  var __mineguard_live_state__: LiveSystemState | undefined;
}

const DATA_FILE = path.join(process.cwd(), "data", "live_state.json");

function normalizeNodeId(raw: string): { id: string; zoneId: string } {
  const clean = raw.trim().toUpperCase().replace(/[-_]/g, "");
  if (clean.includes("1") || clean.includes("01")) {
    return { id: "SN-001", zoneId: "Z-001" };
  }
  if (clean.includes("2") || clean.includes("02")) {
    return { id: "SN-002", zoneId: "Z-002" };
  }
  if (clean.includes("3") || clean.includes("03")) {
    return { id: "SN-003", zoneId: "Z-003" };
  }
  return { id: "SN-001", zoneId: "Z-001" };
}

function getInitialState(): LiveSystemState {
  const initialStage = 0;
  const initialScenario = "normal" as const;
  const zones = zonesFor(initialStage, initialScenario);
  const nodes = nodesFor(initialStage, initialScenario);
  const node_last_times: Record<string, number> = {};
  for (const n of nodes) {
    node_last_times[n.id] = Date.now();
  }

  return {
    schema_version: "1.1",
    generated_at: new Date().toISOString(),
    is_live: false,
    stage: initialStage,
    scenario: initialScenario,
    overall_state: overallState(zones),
    nodes,
    zones,
    alerts: alertsFor(zones, initialStage, initialScenario),
    local_monitoring: "ACTIVE",
    cloud: "CONNECTED",
    ml_adapter: "READY",
    data_source: "DEMO",
    last_updated: new Date().toISOString(),
    node_last_times
  };
}

if (!globalThis.__mineguard_live_state__) {
  globalThis.__mineguard_live_state__ = getInitialState();
}

/** Check staleness (no signal for >30s) and update node health messages */
function applyHealthChecks(state: LiveSystemState) {
  const now = Date.now();
  for (const node of state.nodes) {
    const lastSeenTime = state.node_last_times[node.id];
    if (lastSeenTime) {
      const elapsedSeconds = (now - lastSeenTime) / 1000;
      if (elapsedSeconds > 30) {
        node.healthy = false;
        node.quality = "UNAVAILABLE";
        node.lastSeen = `>30s ago (no signal: ${Math.round(elapsedSeconds)}s)`;
        node.healthMessage = `Node is not sending signals (>30s silence)`;
      }
    }
  }
}

export function getLiveSystemState(): LiveSystemState {
  const state = globalThis.__mineguard_live_state__ || getInitialState();

  // Try syncing from disk if live_state.json exists
  if (fs.existsSync(DATA_FILE)) {
    try {
      const content = fs.readFileSync(DATA_FILE, "utf-8");
      const diskData = JSON.parse(content);
      if (diskData && (diskData.is_live || diskData.last_updated)) {
        state.is_live = Boolean(diskData.is_live);
        state.stage = typeof diskData.stage === "number" ? diskData.stage : state.stage;
        state.data_source = diskData.is_live ? "LIVE_HARDWARE" : state.data_source;
        state.last_updated = diskData.last_updated || new Date().toISOString();

        if (Array.isArray(diskData.nodes)) {
          for (const dNode of diskData.nodes) {
            const { id } = normalizeNodeId(dNode.id);
            const target = state.nodes.find((n) => n.id === id);
            if (target) {
              target.tilt = typeof dNode.tilt === "number" ? dNode.tilt : target.tilt;
              target.displacement = typeof dNode.displacement === "number" ? dNode.displacement : target.displacement;
              target.vibration = typeof dNode.vibration === "number" ? dNode.vibration : target.vibration;
              if (dNode.battery !== undefined) target.battery = dNode.battery;
              if (dNode.rssi !== undefined) target.rssi = dNode.rssi;
              if (dNode.lastSeen) target.lastSeen = dNode.lastSeen;
              if (dNode.healthMessage) target.healthMessage = dNode.healthMessage;
              if (typeof dNode.healthy === "boolean") target.healthy = dNode.healthy;
              if (dNode.healthy) {
                state.node_last_times[id] = Date.now();
              }
            }
          }
        }

        if (Array.isArray(diskData.zones)) {
          state.zones = diskData.zones;
        }
        if (Array.isArray(diskData.alerts)) {
          state.alerts = diskData.alerts;
        }
        state.overall_state = overallState(state.zones);
      }
    } catch {
      // Non-fatal disk read fallback
    }
  }

  applyHealthChecks(state);
  state.overall_state = overallState(state.zones);
  state.generated_at = new Date().toISOString();
  return state;
}

export function ingestHardwarePacket(packet: LiveHardwarePacket): { accepted: boolean; message?: string } {
  const state = globalThis.__mineguard_live_state__ || getInitialState();
  state.is_live = true;
  state.data_source = "LIVE_HARDWARE";
  state.last_updated = new Date().toISOString();

  const { id, zoneId } = normalizeNodeId(packet.node_id);
  const now = Date.now();
  state.node_last_times[id] = now;

  let targetNode = state.nodes.find((n) => n.id === id);
  if (!targetNode) {
    targetNode = {
      id,
      zoneId,
      battery: packet.battery_percent || 90,
      rssi: packet.rssi || -45,
      lastSeen: "just now",
      tilt: 0,
      displacement: 0,
      deformationRate: 0.02,
      vibration: 0.03,
      healthy: true,
      quality: "GOOD",
      modelClass: "normal",
      modelConfidence: 0.95,
      healthMessage: "Nominal telemetry"
    };
    state.nodes.push(targetNode);
  }

  // Check for unrealistic measurements
  const netTilt = Math.sqrt((packet.tilt_x_deg || 0) ** 2 + (packet.tilt_y_deg || 0) ** 2);
  const disp = packet.relative_displacement_mm;
  const vib = packet.vibration_level;

  let isUnrealistic = false;
  let unrealisticReason = "";

  if (Number.isNaN(netTilt) || netTilt > 90.0) {
    isUnrealistic = true;
    unrealisticReason = `Tilt ${netTilt.toFixed(1)}° out of physical limits (max 90°)`;
  } else if (Number.isNaN(disp) || Math.abs(disp) > 500.0) {
    isUnrealistic = true;
    unrealisticReason = `Displacement ${disp}mm out of physical bounds`;
  } else if (Number.isNaN(vib) || vib > 15.0) {
    isUnrealistic = true;
    unrealisticReason = `Vibration level ${vib}g exceeds sensor saturation`;
  }

  targetNode.lastSeen = "just now";
  targetNode.battery = packet.battery_percent || targetNode.battery;
  targetNode.rssi = packet.rssi || targetNode.rssi;

  if (isUnrealistic) {
    targetNode.healthy = false;
    targetNode.quality = "DEGRADED";
    targetNode.healthMessage = `Unrealistic measurement: ${unrealisticReason}`;
  } else {
    targetNode.healthy = true;
    targetNode.quality = "GOOD";
    targetNode.tilt = Number(netTilt.toFixed(2));
    targetNode.displacement = Number(disp.toFixed(2));
    targetNode.vibration = Number(vib.toFixed(2));
    targetNode.healthMessage = "Nominal telemetry · All checks passed";
  }

  applyHealthChecks(state);
  return { accepted: true };
}

export function ingestMLEvidence(ml: LiveMLEvidence): { accepted: boolean } {
  const state = globalThis.__mineguard_live_state__ || getInitialState();
  state.is_live = true;
  state.data_source = "LIVE_HARDWARE";
  state.last_updated = new Date().toISOString();

  const { id } = normalizeNodeId(ml.node_id || "NODE_01");
  const node = state.nodes.find((n) => n.id === id);
  if (node) {
    node.modelClass = ml.event_type;
    node.modelConfidence = ml.confidence > 1 ? ml.confidence / 100 : ml.confidence;
    if (ml.deformation_rate !== undefined) {
      node.deformationRate = ml.deformation_rate;
    }
  }

  // Update Zone 1 (or appropriate zone)
  let stage = 0;
  let riskState: RiskState = "NORMAL";

  if (ml.event_type === "subsidence_precursor") {
    if (ml.confidence >= 75 || (ml.danger_level && ml.danger_level >= 75)) {
      stage = 5;
      riskState = "CRITICAL";
    } else if (ml.confidence >= 50 || (ml.danger_level && ml.danger_level >= 50)) {
      stage = 4;
      riskState = "HIGH_RISK";
    } else {
      stage = 3;
      riskState = "PROGRESSIVE";
    }
  } else if (ml.event_type === "decoy_seismic") {
    stage = 1;
    riskState = "LOCAL_ANOMALY";
  }

  state.stage = stage;
  const z1 = state.zones[0];
  if (z1) {
    z1.state = riskState;
    z1.trend = stage >= 4 ? "Accelerating" : stage >= 1 ? "Rising" : "Stable";
    z1.confidence = ml.confidence >= 75 ? "HIGH" : "MEDIUM";
    if (ml.evidence && ml.evidence.length) {
      z1.evidence = ml.evidence;
    }
  }

  if (stage >= 4) {
    state.alerts = [
      {
        id: `ALT-LIVE-${Date.now() % 1000}`,
        zoneId: "Z-001",
        nodeId: id,
        severity: stage === 5 ? "CRITICAL" : "HIGH",
        title: `${z1.id} (${id}): progressive subsidence precursor confirmed`,
        summary: `Random Forest v6 detected continuous ground deformation (confidence: ${Math.round(node ? node.modelConfidence * 100 : 80)}%).`,
        evidence: z1.evidence,
        confidence: "HIGH",
        lifecycle: "NEW",
        created: "just now",
        recommendedAction: stage === 5 ? "Verify field conditions and trigger site response protocol." : "Inspect the affected zone."
      }
    ];
  } else if (stage === 0) {
    state.alerts = [];
  }

  state.overall_state = overallState(state.zones);
  return { accepted: true };
}
