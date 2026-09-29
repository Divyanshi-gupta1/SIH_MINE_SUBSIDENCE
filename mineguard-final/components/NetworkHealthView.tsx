import React from "react";
import type { NodeState } from "../lib/types";

interface NetworkHealthViewProps {
  nodes: NodeState[];
  gatewayStatus: string;
  isLiveActive: boolean;
}

export function NetworkHealthView({
  nodes,
  gatewayStatus,
  isLiveActive
}: NetworkHealthViewProps) {
  const offlineNodes = nodes.filter(
    (n) => !n.healthy || n.quality === "UNAVAILABLE" || n.monitoringGap
  );

  return (
    <div className="engPanel">
      <div className="engPanelHeader">
        <div className="engPanelTitle">
          <span>⌁</span>
          <span>Mesh Network Health &amp; Gateway Connectivity</span>
        </div>
        <div className="engPanelSub">
          WIRELESS LORA 915MHZ TELEMETRY · SENSOR HEALTH SEPARATE FROM GEOTECHNICAL RISK
        </div>
      </div>

      <div className="engPanelBody">
        {/* Monitoring Gap Warning Banner if any node is offline */}
        {offlineNodes.length > 0 && (
          <div
            style={{
              background: "#fffbeb",
              border: "1px solid #fde68a",
              borderRadius: "3px",
              padding: "10px 14px",
              marginBottom: "14px",
              display: "flex",
              alignItems: "flex-start",
              gap: "10px"
            }}
          >
            <span style={{ fontSize: "16px" }}>⚠️</span>
            <div>
              <strong style={{ fontSize: "11px", color: "#92400e", fontFamily: "var(--font-mono)" }}>
                MONITORING GAP DETECTED · DATA CONFIDENCE REDUCED
              </strong>
              <div style={{ fontSize: "10px", color: "#78350f", marginTop: "3px", lineHeight: 1.45 }}>
                One or more sensor nodes ({offlineNodes.map((n) => n.id).join(", ")}) are offline or have not transmitted within the 30-second timeout window.
                <br />
                <strong>ENGINEERING PROTOCOL:</strong> Missing telemetry is <em>NEVER</em> treated as zero deformation. Coverage across flagged sectors is degraded.
              </div>
            </div>
          </div>
        )}

        {/* Gateway Specification Card */}
        <div
          style={{
            background: "#f8fafc",
            border: "1px solid var(--border)",
            borderRadius: "3px",
            padding: "10px 14px",
            marginBottom: "14px",
            display: "grid",
            gridTemplateColumns: "repeat(5, 1fr)",
            gap: "10px"
          }}
        >
          <div>
            <span className="summaryLabel">Gateway Unit</span>
            <div style={{ fontSize: "12px", fontWeight: 800, fontFamily: "var(--font-mono)" }}>
              GW-001 (Base Station)
            </div>
          </div>
          <div>
            <span className="summaryLabel">Hardware Status</span>
            <div style={{ fontSize: "12px", fontWeight: 700, display: "flex", alignItems: "center", gap: "5px" }}>
              <span className="dot green" />
              {gatewayStatus}
            </div>
          </div>
          <div>
            <span className="summaryLabel">Radio Link</span>
            <div style={{ fontSize: "11px", fontFamily: "var(--font-mono)" }}>
              LoRa 915 MHz · SF7/BW125
            </div>
          </div>
          <div>
            <span className="summaryLabel">Host Interface</span>
            <div style={{ fontSize: "11px", fontFamily: "var(--font-mono)" }}>
              USB CDC Serial (115200 baud)
            </div>
          </div>
          <div>
            <span className="summaryLabel">Pipeline Seam</span>
            <div style={{ fontSize: "11px", fontFamily: "var(--font-mono)", color: isLiveActive ? "#15803d" : "#0284c7" }}>
              {isLiveActive ? "LIVE HARDWARE STREAM" : "LOCAL READY"}
            </div>
          </div>
        </div>

        {/* Detailed Node Table */}
        <table className="networkTable">
          <thead>
            <tr>
              <th>Node Identifier</th>
              <th>Sector / Zone</th>
              <th>Hardware Health</th>
              <th>Quality State</th>
              <th>Battery State</th>
              <th>RF Signal (RSSI)</th>
              <th>Last Contact</th>
              <th>Coverage Condition</th>
            </tr>
          </thead>
          <tbody>
            {nodes.map((node) => {
              const isGap = !node.healthy || node.quality === "UNAVAILABLE" || node.monitoringGap;
              return (
                <tr key={node.id} className={isGap ? "gapWarningRow" : ""}>
                  <td style={{ fontFamily: "var(--font-mono)", fontWeight: 800 }}>{node.id}</td>
                  <td style={{ fontFamily: "var(--font-mono)" }}>{node.zoneId}</td>
                  <td>
                    <span className={`badge ${node.healthy ? "badge-normal" : "badge-critical"}`}>
                      <span className={`dot ${node.healthy ? "green" : "red"}`} />
                      {node.healthy ? "HEALTHY" : "CHECK NODE"}
                    </span>
                  </td>
                  <td style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}>
                    {node.quality}
                  </td>
                  <td style={{ fontFamily: "var(--font-mono)" }}>
                    {node.battery}% {node.battery > 50 ? "🔋" : "⚠️"}
                  </td>
                  <td style={{ fontFamily: "var(--font-mono)" }}>
                    {node.rssi} dBm
                  </td>
                  <td style={{ fontFamily: "var(--font-mono)" }}>
                    {node.lastSeen}
                  </td>
                  <td>
                    {isGap ? (
                      <span style={{ color: "#991b1b", fontWeight: 700, fontFamily: "var(--font-mono)", fontSize: "9px" }}>
                        MONITORING GAP (CONFIDENCE REDUCED)
                      </span>
                    ) : (
                      <span style={{ color: "#166534", fontWeight: 600, fontSize: "9px" }}>
                        Continuous Telemetry Active
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {/* System Pipeline Path Diagram */}
        <div style={{ marginTop: "16px", background: "#f8fafc", border: "1px solid var(--border-subtle)", borderRadius: "3px", padding: "12px" }}>
          <div style={{ fontSize: "10px", fontWeight: 700, textTransform: "uppercase", marginBottom: "8px", fontFamily: "var(--font-mono)" }}>
            Telemetry Ingestion Architecture:
          </div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "6px", overflowX: "auto" }}>
            {[
              { title: "Sensor Nodes", desc: "MPU9250 + LoRa TX" },
              { title: "Wireless Mesh", desc: "915MHz RF Packet" },
              { title: "Gateway GW-001", desc: "USB RX (115200)" },
              { title: "Python Sync", desc: "POST /api/ingest" },
              { title: "ML Classifier", desc: "Random Forest v6" },
              { title: "Command UI", desc: "Real-time Dispatch" }
            ].map((step, idx) => (
              <React.Fragment key={step.title}>
                <div style={{ background: "#ffffff", border: "1px solid var(--border)", padding: "6px 10px", borderRadius: "3px", minWidth: "120px", textAlign: "center" }}>
                  <div style={{ fontSize: "10px", fontWeight: 700, color: "var(--ink)" }}>{step.title}</div>
                  <div style={{ fontSize: "8px", color: "var(--muted)", fontFamily: "var(--font-mono)" }}>{step.desc}</div>
                </div>
                {idx < 5 && <span style={{ color: "var(--muted)", fontWeight: 700 }}>→</span>}
              </React.Fragment>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
