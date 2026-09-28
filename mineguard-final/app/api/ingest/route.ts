import { NextResponse } from "next/server";
import { ingestHardwarePacket } from "../../../lib/liveState";

export async function POST(request: Request) {
  try {
    const packet = await request.json();
    const required = [
      "node_id", "timestamp", "sequence", "tilt_x_deg", "tilt_y_deg",
      "relative_displacement_mm", "vibration_level", "crack_detected",
      "battery_percent", "rssi", "quality"
    ];
    const missing = required.filter((key) => !(key in packet));

    if (missing.length) {
      return NextResponse.json({ accepted: false, missing }, { status: 400 });
    }

    const result = ingestHardwarePacket(packet);

    return NextResponse.json({
      accepted: true,
      schema_version: "1.1",
      node_id: packet.node_id,
      sequence: packet.sequence,
      received_at: new Date().toISOString(),
      health_status: result.accepted ? "OK" : "WARNING",
      pipeline: ["validate", "sensor-health", "ml-adapter", "temporal-correlation", "spatial-risk", "alert-lifecycle"]
    });
  } catch (error: any) {
    return NextResponse.json({ accepted: false, error: error.message }, { status: 500 });
  }
}
