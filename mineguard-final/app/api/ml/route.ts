import { NextResponse } from "next/server";
import { ingestMLEvidence } from "../../../lib/liveState";

export async function POST(request: Request) {
  try {
    const payload = await request.json();
    ingestMLEvidence(payload);

    return NextResponse.json({
      accepted: true,
      schema_version: "1.1",
      model_version: payload?.model_version ?? "random_forest_v6",
      received_at: new Date().toISOString(),
      status: "APPLIED_TO_STATE"
    });
  } catch (error: any) {
    return NextResponse.json({ accepted: false, error: error.message }, { status: 500 });
  }
}
