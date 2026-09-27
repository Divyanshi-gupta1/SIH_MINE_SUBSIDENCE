import { NextResponse } from "next/server";
import { getLiveSystemState } from "../../../lib/liveState";

export async function GET() {
  const state = getLiveSystemState();
  return NextResponse.json({
    schema_version: state.schema_version,
    generated_at: new Date().toISOString(),
    is_live: state.is_live,
    stage: state.stage,
    mode: state.mode,
    nodes: state.nodes,
    zones: state.zones,
    alerts: state.alerts,
    last_packet: state.last_packet,
    last_ml: state.last_ml,
    local_monitoring: state.local_monitoring,
    cloud: state.cloud,
    ml_adapter: state.ml_adapter
  });
}
