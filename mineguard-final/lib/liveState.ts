import fs from "fs";
import path from "path";
import type { Alert, NodeState, RiskState, ZoneState } from "./types";
import { nodesFor, zonesFor, alertsFor, rank } from "./demo";

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
  event_type: "normal" | "decoy_seismic" | "subsidence_precursor";
  anomaly: boolean;
  confidence: number;
  probabilities?: Record<string, number>;
  danger_level: number;
  danger_category: "Safe" | "Caution" | "Critical";
  trend: "stable" | "increasing" | "accelerating";
  persistence: boolean;
  deformation_rate: number;
  evidence: string[];
  model_version: string;
}

export interface LiveSystemState {
  schema_version: string;
  last_updated: string;
  is_live: boolean;
  last_packet?: LiveHardwarePacket;
  last_ml?: LiveMLEvidence;
  nodes: NodeState[];
  zones: ZoneState[];
  alerts: Alert[];
  stage: number;
  mode: "progressive" | "false_local" | "normal";
  local_monitoring: "ACTIVE" | "STANDBY";
  cloud: "CONNECTED" | "OFFLINE";
  ml_adapter: "READY" | "PROCESSING" | "OFFLINE";
}

// In-memory global store so API routes share state across invocations
declare global {
  var __mineguard_live_state__: LiveSystemState | undefined;
}

function getInitialState(): LiveSystemState {
  const initialStage = 0;
  const initialMode = "normal" as const;
  const zones = zonesFor(initialStage, initialMode);
  return {
    schema_version: "1.0",
    last_updated: new Date().toISOString(),
    is_live: false,
    nodes: nodesFor(initialStage, initialMode),
    zones,
    alerts: alertsFor(zones, initialStage),
    stage: initialStage,
    mode: initialMode,
    local_monitoring: "ACTIVE",
    cloud: "CONNECTED",
    ml_adapter: "READY"
  };
}

if (!globalThis.__mineguard_live_state__) {
  globalThis.__mineguard_live_state__ = getInitialState();
}

const DATA_FILE = path.join(process.cwd(), "data", "live_state.json");

export function getLiveSystemState(): LiveSystemState {
  // If file exists, try reading to sync with Python bridge
  if (fs.existsSync(DATA_FILE)) {
    try {
      const content = fs.readFileSync(DATA_FILE, "utf-8");
      const diskState = JSON.parse(content);
      if (diskState && diskState.last_updated) {
        return diskState;
      }
    } catch {
      // Fallback to in-memory state
    }
  }
  return globalThis.__mineguard_live_state__ || getInitialState();
}

export function updateStateFromHardwareAndML(
  packet: LiveHardwarePacket,
  ml?: LiveMLEvidence
): LiveSystemState {
  const state = getLiveSystemState();
  state.is_live = true;
  state.last_updated = new Date().toISOString();
  state.last_packet = packet;
  state.local_monitoring = "ACTIVE";
  state.cloud = "CONNECTED";
  state.ml_adapter = "READY";

  // Map node_id: NODE_1 / NODE_01 -> N1
  const rawId = packet.node_id.toUpperCase().replace("NODE_", "N").replace("NODE", "N");
  const normalizedId = rawId.startsWith("N") ? rawId : `N${rawId}`;

  const netTilt = Number(Math.sqrt(packet.tilt_x_deg ** 2 + packet.tilt_y_deg ** 2).toFixed(2));
  const disp = Number(packet.relative_displacement_mm.toFixed(2));
  const vib = Number(packet.vibration_level.toFixed(2));

  // 1. Update Node in node list
  const nodeIndex = state.nodes.findIndex((n) => n.id === normalizedId);
  const updatedNode: NodeState = {
    id: normalizedId,
    battery: packet.battery_percent || 90,
    rssi: packet.rssi || -45,
    lastSeen: "just now",
    tilt: netTilt,
    displacement: disp,
    vibration: vib,
    healthy: packet.quality === "good"
  };

  if (nodeIndex >= 0) {
    state.nodes[nodeIndex] = updatedNode;
  } else {
    state.nodes.push(updatedNode);
  }

  // 2. Update ML Evidence & Risk State
  if (ml) {
    state.last_ml = ml;

    let targetRisk: RiskState = "NORMAL";
    let targetStage = 0;

    if (ml.event_type === "subsidence_precursor") {
      if (ml.danger_level >= 75 || disp > 15 || packet.crack_detected) {
        targetRisk = "CRITICAL";
        targetStage = 5;
      } else if (ml.danger_level >= 50 || disp > 5) {
        targetRisk = "HIGH_RISK";
        targetStage = 4;
      } else {
        targetRisk = "PROGRESSIVE";
        targetStage = 3;
      }
    } else if (ml.event_type === "decoy_seismic") {
      targetRisk = "LOCAL_ANOMALY";
      targetStage = 1;
    } else {
      // Normal
      targetRisk = "NORMAL";
      targetStage = 0;
    }

    state.stage = targetStage;

    // Update Zone 1 (Initial deformation zone for N1)
    const z1 = state.zones[0];
    if (z1) {
      z1.state = targetRisk;
      z1.trend = ml.trend === "accelerating" ? "Accelerating" : ml.trend === "increasing" ? "Rising" : "Stable";
      z1.confidence = ml.confidence > 80 ? "HIGH" : "MEDIUM";
      z1.evidence = ml.evidence && ml.evidence.length ? ml.evidence : [
        `ML Model (${ml.model_version}): ${ml.event_type.replace("_", " ")} (${ml.confidence}% conf)`,
        `Tilt: ${netTilt}° | Displacement: ${disp} mm | Vibration: ${vib} g`,
        `Danger Level: ${ml.danger_level}/100 (${ml.danger_category})`
      ];
    }

    // Update alerts if precursor detected
    if (targetRisk === "CRITICAL" || targetRisk === "HIGH_RISK") {
      const existingAlert = state.alerts.find((a) => a.zoneId === "Z1");
      const newAlert: Alert = {
        id: existingAlert ? existingAlert.id : `ALT-${Date.now().toString().slice(-4)}`,
        zoneId: "Z1",
        severity: targetRisk === "CRITICAL" ? "CRITICAL" : "HIGH",
        title: `Z1 (${normalizedId}): Subsidence Precursor Buildup Detected`,
        summary: `ML Model (${ml.model_version}) detected progressive rock mass deformation with ${ml.confidence}% confidence. Risk score: ${ml.danger_level}/100.`,
        evidence: z1.evidence,
        confidence: "HIGH",
        lifecycle: "NEW",
        created: "just now"
      };

      if (!existingAlert) {
        state.alerts.unshift(newAlert);
      } else {
        state.alerts[0] = newAlert;
      }
    }
  }

  // Save to disk cache for live persistence
  try {
    const dir = path.dirname(DATA_FILE);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(DATA_FILE, JSON.stringify(state, null, 2), "utf-8");
  } catch {
    // ignore filesystem write errors
  }

  globalThis.__mineguard_live_state__ = state;
  return state;
}
