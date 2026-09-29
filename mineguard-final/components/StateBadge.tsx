import React from "react";
import type { RiskState } from "../lib/types";

export function StateBadge({ state }: { state: RiskState }) {
  const normalized = state.toLowerCase();
  return (
    <span className={`badge badge-${normalized}`}>
      <span className={`dot ${getDotColor(state)}`} />
      {state.replaceAll("_", " ")}
    </span>
  );
}

function getDotColor(state: RiskState): string {
  switch (state) {
    case "NORMAL":
      return "green";
    case "LOCAL_ANOMALY":
    case "PERSISTENT":
      return "yellow";
    case "CORRELATED":
    case "PROGRESSIVE":
      return "orange";
    case "HIGH_RISK":
    case "CRITICAL":
      return "red";
    default:
      return "gray";
  }
}
