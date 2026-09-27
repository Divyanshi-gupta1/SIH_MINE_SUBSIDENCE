import { NextResponse } from "next/server";
import { updateStateFromHardwareAndML, type LiveHardwarePacket, type LiveMLEvidence } from "../../../lib/liveState";

export async function POST(request: Request) {
  try {
    const body = await request.json();

    // Check required fields per HARDWARE-INTEGRATION-CONTRACT.md
    const required = [
      "node_id", "timestamp", "sequence", "tilt_x_deg", "tilt_y_deg",
      "relative_displacement_mm", "vibration_level", "crack_detected",
      "battery_percent", "rssi", "quality"
    ];
    const missing = required.filter((key) => !(key in body));

    if (missing.length) {
      return NextResponse.json({ accepted: false, missing }, { status: 400 });
    }

    const packet: LiveHardwarePacket = {
      node_id: String(body.node_id),
      timestamp: body.timestamp || new Date().toISOString(),
      sequence: Number(body.sequence || 1),
      tilt_x_deg: Number(body.tilt_x_deg || 0),
      tilt_y_deg: Number(body.tilt_y_deg || 0),
      relative_displacement_mm: Number(body.relative_displacement_mm || 0),
      vibration_level: Number(body.vibration_level || 0),
      crack_detected: Boolean(body.crack_detected),
      battery_percent: Number(body.battery_percent || 90),
      rssi: Number(body.rssi || -45),
      quality: String(body.quality || "good"),
      temperature_c: body.temperature_c ? Number(body.temperature_c) : undefined,
      distance_cm: body.distance_cm ? Number(body.distance_cm) : undefined
    };

    const mlEvidence: LiveMLEvidence | undefined = body.ml ? {
      event_type: body.ml.event_type || (body.ml.anomaly ? "subsidence_precursor" : "normal"),
      anomaly: Boolean(body.ml.anomaly),
      confidence: Number(body.ml.confidence || 90),
      probabilities: body.ml.probabilities,
      danger_level: Number(body.ml.danger_level || (body.ml.anomaly ? 85 : 15)),
      danger_category: body.ml.danger_category || (body.ml.anomaly ? "Critical" : "Safe"),
      trend: body.ml.trend || "stable",
      persistence: Boolean(body.ml.persistence),
      deformation_rate: Number(body.ml.deformation_rate || 0),
      evidence: Array.isArray(body.ml.evidence) ? body.ml.evidence : [],
      model_version: body.ml.model_version || "random_forest_v6"
    } : undefined;

    const updatedState = updateStateFromHardwareAndML(packet, mlEvidence);

    return NextResponse.json({
      accepted: true,
      schema_version: "1.0",
      node_id: packet.node_id,
      sequence: packet.sequence,
      received_at: new Date().toISOString(),
      live_nodes_count: updatedState.nodes.length,
      current_stage: updatedState.stage,
      status: "INGESTED_AND_APPLIED_TO_DASHBOARD"
    });
  } catch (error: any) {
    return NextResponse.json({ accepted: false, error: error.message }, { status: 500 });
  }
}
