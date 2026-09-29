import React from "react";
import type { Alert, Asset, NodeState, RiskState, ZoneState } from "../lib/types";
import { stageLabels, timelineFor } from "../lib/demo";
import { StateBadge } from "./StateBadge";

interface HistoryReplayViewProps {
  stage: number;
  onStageChange: (stage: number) => void;
  overallState: RiskState;
  asset: Asset;
  nodes: NodeState[];
  zones: ZoneState[];
  alerts: Alert[];
}

export function HistoryReplayView({
  stage,
  onStageChange,
  overallState,
  asset,
  nodes,
  zones,
  alerts
}: HistoryReplayViewProps) {
  const timeline = timelineFor(stage);

  return (
    <div className="engPanel">
      <div className="engPanelHeader">
        <div className="engPanelTitle">
          <span>↺</span>
          <span>Event Replay &amp; Synchronized Timeline</span>
        </div>
        <div className="engPanelSub">
          AVAILABLE HISTORY · DEMO TIMELINE · CURRENT RUN OBSERVATION AUDIT TRAIL
        </div>
      </div>

      <div className="engPanelBody">
        {/* Timeline Slider and synchronized step buttons */}
        <div className="timelineControlBar">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "11px", fontWeight: 700, fontFamily: "var(--font-mono)" }}>
              Current Run Timeline Scrub (+{stage * 10} min compressed simulation)
            </span>
            <span style={{ fontSize: "9px", color: "var(--muted)", fontFamily: "var(--font-mono)" }}>
              Data Source: Current Execution Buffer (Prototype History)
            </span>
          </div>

          <input
            type="range"
            min="0"
            max="5"
            value={stage}
            onChange={(e) => onStageChange(Number(e.target.value))}
            className="timelineSlider"
          />

          <div className="timelineSteps">
            {timeline.map((item, index) => (
              <button
                key={item.minute}
                className={`timelineStepBtn ${index === stage ? "active" : ""}`}
                onClick={() => onStageChange(index)}
              >
                <span className="stepTime">+{item.minute} min</span>
                <span className="stepName">{stageLabels[index]}</span>
                <span style={{ fontSize: "8px", fontFamily: "var(--font-mono)", color: "var(--muted)" }}>
                  Disp: {item.displacement}mm
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Synchronized State Display Grid */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1.2fr 1fr",
            gap: "12px",
            marginTop: "14px"
          }}
        >
          {/* Left: Synchronized Zone & Asset Snapshot */}
          <div style={{ background: "#ffffff", border: "1px solid var(--border)", borderRadius: "3px", padding: "12px" }}>
            <div style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase", marginBottom: "8px" }}>
              Synchronized Event Snapshot at +{stage * 10} min
            </div>

            <table className="networkTable">
              <tbody>
                <tr>
                  <th>Overall Geotechnical State</th>
                  <td><StateBadge state={overallState} /></td>
                </tr>
                <tr>
                  <th>Center Trough Displacement</th>
                  <td style={{ fontFamily: "var(--font-mono)", fontWeight: 800 }}>
                    {timeline[stage].displacement} mm
                  </td>
                </tr>
                <tr>
                  <th>Max Deformation Rate</th>
                  <td style={{ fontFamily: "var(--font-mono)", fontWeight: 800 }}>
                    {timeline[stage].rate} mm/min
                  </td>
                </tr>
                <tr>
                  <th>Protected Asset A-001 Proximity</th>
                  <td style={{ fontWeight: 700, color: asset.impactStatus === "AT RISK" ? "#b91c1c" : "var(--ink)" }}>
                    {asset.impactStatus} ({asset.distanceM}m to Z-003)
                  </td>
                </tr>
                <tr>
                  <th>Corroborating Active Alerts</th>
                  <td style={{ fontFamily: "var(--font-mono)" }}>
                    {alerts.length > 0 ? `${alerts.length} active alert(s)` : "None (Nominal)"}
                  </td>
                </tr>
              </tbody>
            </table>

            <div style={{ marginTop: "12px", fontSize: "9px", color: "var(--muted)", lineHeight: 1.45 }}>
              * Time in this replay reflects the compressed evaluation run (+10 min intervals). MineGuard maintains full chronological telemetry history without fabricating unobserved intermediate events.
            </div>
          </div>

          {/* Right: Node Snapshot at Timeline Step */}
          <div style={{ background: "#ffffff", border: "1px solid var(--border)", borderRadius: "3px", padding: "12px" }}>
            <div style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase", marginBottom: "8px" }}>
              Multi-Node Telemetry Snapshot
            </div>

            <table className="inspectTable">
              <thead>
                <tr>
                  <th>Node</th>
                  <th>Tilt</th>
                  <th>Disp</th>
                  <th>Rate</th>
                  <th>Class</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map((n) => (
                  <tr key={n.id}>
                    <td><strong>{n.id}</strong></td>
                    <td className="val">{n.tilt.toFixed(2)}°</td>
                    <td className="val">{n.displacement.toFixed(2)}mm</td>
                    <td className="val">{n.deformationRate.toFixed(2)}</td>
                    <td className="val" style={{ color: "#0284c7" }}>{n.modelClass}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div style={{ marginTop: "12px" }}>
              <div style={{ fontSize: "8px", textTransform: "uppercase", color: "var(--muted)", fontWeight: 700, fontFamily: "var(--font-mono)" }}>
                Auditable Record Verification
              </div>
              <p style={{ fontSize: "9px", margin: "4px 0", color: "var(--ink-secondary)" }}>
                Recorded packets are verified with CRC16 and timestamped at Gateway GW-001 before entering the Random Forest inference engine.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
