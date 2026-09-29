import React from "react";
import type { Alert, NodeState, RiskState, ZoneState } from "../lib/types";
import { StateBadge } from "./StateBadge";

interface SituationSummaryProps {
  overallState: RiskState;
  alerts: Alert[];
  zones: ZoneState[];
  nodes: NodeState[];
  gatewayStatus: string;
  dataFreshness: string;
}

export function SituationSummary({
  overallState,
  alerts,
  zones,
  nodes,
  gatewayStatus,
  dataFreshness
}: SituationSummaryProps) {
  // Zones that require attention (any zone not in NORMAL state)
  const attentionZones = zones.filter((z) => z.state !== "NORMAL");
  const attentionZonesText =
    attentionZones.length > 0
      ? attentionZones.map((z) => z.id).join(", ")
      : "None (All Nominal)";

  const activeAlertsCount = alerts.filter(
    (a) => a.lifecycle !== "DISMISSED" && a.lifecycle !== "SENSOR_ISSUE" && a.lifecycle !== "CONFIRMED"
  ).length;

  const onlineNodes = nodes.filter((n) => n.quality !== "UNAVAILABLE").length;
  const totalNodes = nodes.length;

  return (
    <section className="situationSummary" aria-label="Operational Situation Summary">
      <div className="summaryCard">
        <span className="summaryLabel">System Condition</span>
        <div className="summaryValue">
          <StateBadge state={overallState} />
        </div>
        <span className="summarySub">Assessed panel state</span>
      </div>

      <div className="summaryCard">
        <span className="summaryLabel">Active Alerts</span>
        <div className="summaryValue">
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "14px",
              color: activeAlertsCount > 0 ? "#b91c1c" : "#15803d"
            }}
          >
            {activeAlertsCount}
          </span>
          <span style={{ fontSize: "10px", color: "var(--muted)", fontWeight: 500 }}>
            {activeAlertsCount === 1 ? "action required" : activeAlertsCount > 1 ? "actions required" : "nominal"}
          </span>
        </div>
        <span className="summarySub">Operator disposition pending</span>
      </div>

      <div className="summaryCard">
        <span className="summaryLabel">Zones Requiring Attention</span>
        <div className="summaryValue" title={attentionZonesText}>
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "12px",
              color: attentionZones.length > 0 ? "#c2410c" : "#15803d"
            }}
          >
            {attentionZonesText}
          </span>
        </div>
        <span className="summarySub">
          {attentionZones.length === 0
            ? "No boundary deformation"
            : `${attentionZones.length} sector${attentionZones.length > 1 ? "s" : ""} flagged`}
        </span>
      </div>

      <div className="summaryCard">
        <span className="summaryLabel">Sensors Online</span>
        <div className="summaryValue">
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "13px",
              color: onlineNodes < totalNodes ? "#c2410c" : "var(--ink)"
            }}
          >
            {onlineNodes} / {totalNodes} ONLINE
          </span>
        </div>
        <span className="summarySub">
          {onlineNodes < totalNodes ? "Monitoring gap detected" : "Full mesh reporting"}
        </span>
      </div>

      <div className="summaryCard">
        <span className="summaryLabel">Gateway</span>
        <div className="summaryValue">
          <span className="dot green" />
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "12px" }}>
            {gatewayStatus}
          </span>
        </div>
        <span className="summarySub">USB / LoRa RX Active</span>
      </div>

      <div className="summaryCard">
        <span className="summaryLabel">Data Freshness</span>
        <div className="summaryValue">
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--ink-secondary)" }}>
            {dataFreshness}
          </span>
        </div>
        <span className="summarySub">Sync cycle: 1.0s</span>
      </div>
    </section>
  );
}
