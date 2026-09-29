import { NextResponse } from "next/server";
import { getLiveSystemState } from "../../../lib/liveState";
import { alertsFor, nodesFor, overallState, zonesFor } from "../../../lib/demo";
import type { ScenarioKey } from "../../../lib/types";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const mode = url.searchParams.get("mode");
  const liveState = getLiveSystemState();

  // If live stream is active or client explicitly requests live mode
  if (liveState.is_live || mode === "LIVE_TESTBED" || mode === "LIVE_MINE") {
    return NextResponse.json(liveState);
  }

  // Otherwise fallback to demo parameters
  const rawStage = Number(url.searchParams.get("stage") ?? 0);
  const stage = Number.isFinite(rawStage) ? Math.max(0, Math.min(5, rawStage)) : 0;
  const scenario = (url.searchParams.get("scenario") ?? "progressive") as ScenarioKey;
  const safeScenario: ScenarioKey = (["progressive", "false_local", "normal", "persistent", "offline_gap"] as ScenarioKey[]).includes(scenario) ? scenario : "progressive";
  const zones = zonesFor(stage, safeScenario);

  return NextResponse.json({
    schema_version: "1.1",
    generated_at: new Date().toISOString(),
    is_live: false,
    stage,
    scenario: safeScenario,
    overall_state: overallState(zones),
    nodes: nodesFor(stage, safeScenario),
    zones,
    alerts: alertsFor(zones, stage, safeScenario),
    local_monitoring: "ACTIVE",
    cloud: "CONNECTED",
    ml_adapter: "READY",
    data_source: "DEMO"
  });
}
