import React, { useState } from "react";
import type { Alert, AlertLifecycle, Asset, NodeState, RiskState, ViewKey, ZoneState } from "../lib/types";
import { StateBadge } from "./StateBadge";

interface OperationalPanelProps {
  alerts: Alert[];
  currentAlert: Alert | undefined;
  alertLifecycle: AlertLifecycle;
  onAcknowledge: () => void;
  onVerify: () => void;
  onConfirm: () => void;
  onDismiss: (reason: "DISMISSED" | "SENSOR_ISSUE") => void;
  overallState: RiskState;
  selectedEntity: { type: "node" | "zone" | "asset"; id: string } | null;
  onSelectEntity: (entity: { type: "node" | "zone" | "asset"; id: string } | null) => void;
  nodes: NodeState[];
  zones: ZoneState[];
  asset: Asset;
  onNavigateView: (view: ViewKey) => void;
}

export function OperationalPanel({
  alerts,
  currentAlert,
  alertLifecycle,
  onAcknowledge,
  onVerify,
  onConfirm,
  onDismiss,
  overallState,
  selectedEntity,
  onSelectEntity,
  nodes,
  zones,
  asset,
  onNavigateView
}: OperationalPanelProps) {
  const [inspectorTab, setInspectorTab] = useState<"alert" | "selected" | "actions">("alert");

  const activeAlert = currentAlert;

  // Selected entities
  const selNode = selectedEntity?.type === "node" ? nodes.find((n) => n.id === selectedEntity.id) : null;
  const selZone = selectedEntity?.type === "zone" ? zones.find((z) => z.id === selectedEntity.id) : null;
  const isAssetSel = selectedEntity?.type === "asset" || selectedEntity?.id === asset.id;

  return (
    <div className="opPanelStack">
      {/* Tab bar for operational inspector */}
      <div className="engPanel">
        <div className="inspectorTabs">
          <button
            className={`inspectorTab ${inspectorTab === "alert" ? "active" : ""}`}
            onClick={() => setInspectorTab("alert")}
          >
            ACTIVE ALERT ({alerts.filter((a) => a.lifecycle !== "DISMISSED" && a.lifecycle !== "SENSOR_ISSUE").length})
          </button>
          <button
            className={`inspectorTab ${inspectorTab === "selected" ? "active" : ""}`}
            onClick={() => setInspectorTab("selected")}
          >
            INSPECTOR ({selectedEntity ? selectedEntity.id : "NONE"})
          </button>
          <button
            className={`inspectorTab ${inspectorTab === "actions" ? "active" : ""}`}
            onClick={() => setInspectorTab("actions")}
          >
            OPERATOR ACTIONS
          </button>
        </div>

        {/* TAB 1: STRUCTURED ACTIVE ALERT */}
        {inspectorTab === "alert" && (
          <div className="engPanelBody">
            {activeAlert && !["DISMISSED", "SENSOR_ISSUE"].includes(alertLifecycle) ? (
              <div className={`alertOpCard ${activeAlert.severity.toLowerCase()}`}>
                <div className="alertOpHeader">
                  <div>
                    <span className="alertLocation">WHERE: {activeAlert.zoneId}</span>
                    <div className="alertTitle">{activeAlert.title}</div>
                  </div>
                  <StateBadge state={overallState} />
                </div>

                <div className="alertSummaryText">{activeAlert.summary}</div>

                {/* Structured SITUATION / LOCATION / EVIDENCE matrix */}
                <div className="semGrid">
                  <div className="semItem">
                    <label>Where (Sector)</label>
                    <strong>{activeAlert.zoneId}</strong>
                  </div>
                  <div className="semItem">
                    <label>What (Event)</label>
                    <strong>{activeAlert.severity === "WATCH" ? "Local Anomaly" : "Ground Subsidence"}</strong>
                  </div>
                  <div className="semItem">
                    <label>How Serious</label>
                    <strong style={{ color: activeAlert.severity === "CRITICAL" ? "#b91c1c" : "#c2410c" }}>
                      {activeAlert.severity}
                    </strong>
                  </div>
                  <div className="semItem">
                    <label>Model Confidence</label>
                    <strong>{activeAlert.confidence}</strong>
                  </div>
                  <div className="semItem" style={{ gridColumn: "1 / -1" }}>
                    <label>Protected Asset Context</label>
                    <strong>{activeAlert.assetId ?? "A-001"} · {activeAlert.assetContext ?? "Surface structure"}</strong>
                  </div>
                </div>

                {/* Evidence bullets (WHY) */}
                <div className="evidenceSection">
                  <div className="evidenceHeader">Corroborating Evidence (Why):</div>
                  <ul className="evidenceUl">
                    {activeAlert.evidence.map((item, idx) => (
                      <li key={idx}>• {item}</li>
                    ))}
                  </ul>
                </div>

                {/* Explicit Alert Lifecycle Tracker */}
                <div>
                  <div className="evidenceHeader" style={{ marginBottom: "2px" }}>
                    Alert Lifecycle (Human-in-the-Loop):
                  </div>
                  <div className="lifecycleTrack">
                    <div className={`lifecycleStep ${alertLifecycle === "NEW" ? "active" : "passed"}`}>
                      DETECTED
                    </div>
                    <div
                      className={`lifecycleStep ${
                        alertLifecycle === "ACKNOWLEDGED"
                          ? "active"
                          : ["VERIFICATION_PENDING", "CONFIRMED"].includes(alertLifecycle)
                          ? "passed"
                          : ""
                      }`}
                    >
                      ACKNOWLEDGED
                    </div>
                    <div
                      className={`lifecycleStep ${
                        alertLifecycle === "VERIFICATION_PENDING"
                          ? "active"
                          : alertLifecycle === "CONFIRMED"
                          ? "passed"
                          : ""
                      }`}
                    >
                      VERIFYING
                    </div>
                    <div className={`lifecycleStep ${alertLifecycle === "CONFIRMED" ? "active" : ""}`}>
                      CONFIRMED
                    </div>
                  </div>
                  <div style={{ fontSize: "8px", color: "var(--muted)", marginTop: "3px", fontFamily: "var(--font-mono)" }}>
                    * Operator disposition does not overwrite underlying Random Forest telemetry.
                  </div>
                </div>

                {/* Recommended Operator Action */}
                <div style={{ background: "#f8fafc", padding: "6px 8px", border: "1px solid var(--border-subtle)", borderRadius: "3px" }}>
                  <span style={{ fontSize: "8px", textTransform: "uppercase", color: "var(--muted)", fontWeight: 700, fontFamily: "var(--font-mono)" }}>
                    Recommended Action:
                  </span>
                  <div style={{ fontSize: "10px", fontWeight: 600, color: "var(--ink)", marginTop: "2px" }}>
                    {activeAlert.recommendedAction}
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="opActionRow">
                  <button className="btnPrimary" onClick={onAcknowledge}>
                    ACKNOWLEDGE
                  </button>
                  <button className="btnOutline" onClick={onVerify}>
                    MARK VERIFICATION
                  </button>
                  <button className="btnOutline" onClick={onConfirm}>
                    CONFIRM ALERT
                  </button>
                  <button className="btnDangerOutline" onClick={() => onDismiss("SENSOR_ISSUE")}>
                    SENSOR ISSUE
                  </button>
                  <button
                    className="btnOutline"
                    style={{ gridColumn: "1 / -1" }}
                    onClick={() => onNavigateView("sensors")}
                  >
                    VIEW SENSOR DATA →
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ padding: "16px", textAlign: "center", color: "var(--muted)", background: "#f8fafc", border: "1px dashed var(--border)" }}>
                <span className="dot green" style={{ marginRight: "6px" }} />
                <strong style={{ fontSize: "11px", color: "var(--ink)" }}>All Zones Nominal</strong>
                <p style={{ fontSize: "9px", margin: "4px 0 0" }}>
                  No active critical subsidence alerts. Continue continuous engineering monitoring.
                </p>
              </div>
            )}
          </div>
        )}

        {/* TAB 2: SELECTED ENTITY INSPECTOR */}
        {inspectorTab === "selected" && (
          <div className="inspectorBody">
            {selNode && (
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <strong style={{ fontFamily: "var(--font-mono)", fontSize: "12px" }}>Sensor Node {selNode.id}</strong>
                  <span className={`badge ${selNode.healthy ? "badge-normal" : "badge-critical"}`}>
                    {selNode.healthy ? "ONLINE" : "OFFLINE"}
                  </span>
                </div>
                <div style={{ fontSize: "9px", color: "var(--muted)", marginTop: "2px" }}>
                  Assigned Sector: {selNode.zoneId} · Gateway GW-001
                </div>

                <table className="inspectTable" style={{ marginTop: "8px" }}>
                  <tbody>
                    <tr><th>Current Tilt</th><td className="val">{selNode.tilt.toFixed(2)}°</td></tr>
                    <tr><th>Baseline Tilt</th><td className="val">{selNode.baselineTilt?.toFixed(2) ?? "0.02"}°</td></tr>
                    <tr><th>Relative Displacement</th><td className="val">{selNode.displacement.toFixed(2)} mm</td></tr>
                    <tr><th>Deformation Rate</th><td className="val">{selNode.deformationRate.toFixed(2)} mm/min</td></tr>
                    <tr><th>Vibration RMS</th><td className="val">{selNode.vibration.toFixed(2)} g</td></tr>
                    <tr><th>RF Model Class</th><td className="val">{selNode.modelClass.replaceAll("_", " ")}</td></tr>
                    <tr><th>Model Confidence</th><td className="val">{Math.round(selNode.modelConfidence * 100)}%</td></tr>
                    <tr><th>Battery / RSSI</th><td className="val">{selNode.battery}% · {selNode.rssi} dBm</td></tr>
                    <tr><th>Quality</th><td className="val">{selNode.quality}</td></tr>
                    <tr><th>Last Packet</th><td className="val">{selNode.lastSeen}</td></tr>
                  </tbody>
                </table>

                {selNode.healthMessage && (
                  <div style={{ fontSize: "9px", color: selNode.healthy ? "#15803d" : "#b91c1c", marginTop: "6px", background: "#f8fafc", padding: "4px 6px", border: "1px solid var(--border-subtle)" }}>
                    Telemetry Note: {selNode.healthMessage}
                  </div>
                )}

                <div style={{ marginTop: "8px", display: "flex", gap: "6px" }}>
                  <button className="btnPrimary" style={{ flex: 1 }} onClick={() => onNavigateView("sensors")}>
                    Open Sensor Analytics
                  </button>
                  <button className="btnOutline" onClick={() => onSelectEntity(null)}>
                    Clear
                  </button>
                </div>
              </div>
            )}

            {selZone && (
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <strong style={{ fontFamily: "var(--font-mono)", fontSize: "12px" }}>Zone {selZone.id}</strong>
                    <div style={{ fontSize: "9px", color: "var(--muted)" }}>{selZone.name}</div>
                  </div>
                  <StateBadge state={selZone.state} />
                </div>

                <table className="inspectTable" style={{ marginTop: "8px" }}>
                  <tbody>
                    <tr><th>Trend</th><td className="val">{selZone.trend}</td></tr>
                    <tr><th>Spatial Direction</th><td className="val">{selZone.direction}</td></tr>
                    <tr><th>Observed Movement</th><td className="val">{selZone.observedMm?.toFixed(2) ?? "—"} mm</td></tr>
                    <tr><th>Peck Physics Expected</th><td className="val">{selZone.physicsExpectedMm?.toFixed(2) ?? "—"} mm</td></tr>
                    <tr><th>Physics Residual</th><td className="val">{selZone.physicsResidualMm?.toFixed(2) ?? "—"} mm</td></tr>
                    <tr><th>Agreement Status</th><td className="val">{selZone.physicsStatus ?? "NOMINAL"}</td></tr>
                    <tr><th>Distance to Asset</th><td className="val">{selZone.assetDistanceM} m</td></tr>
                    <tr><th>Temporal State</th><td className="val">{selZone.temporalStatus ?? "Nominal"}</td></tr>
                  </tbody>
                </table>

                <div style={{ marginTop: "8px", display: "flex", gap: "6px" }}>
                  <button className="btnPrimary" style={{ flex: 1 }} onClick={() => onNavigateView("zones")}>
                    Open Zone Intelligence
                  </button>
                  <button className="btnOutline" onClick={() => onSelectEntity(null)}>
                    Clear
                  </button>
                </div>
              </div>
            )}

            {isAssetSel && (
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <strong style={{ fontFamily: "var(--font-mono)", fontSize: "12px" }}>Asset {asset.id}</strong>
                    <div style={{ fontSize: "9px", color: "var(--muted)" }}>{asset.label}</div>
                  </div>
                  <span className={`badge ${asset.impactStatus === "AT RISK" ? "badge-critical" : "badge-normal"}`}>
                    {asset.impactStatus}
                  </span>
                </div>

                <table className="inspectTable" style={{ marginTop: "8px" }}>
                  <tbody>
                    <tr><th>Asset Type</th><td className="val">{asset.type}</td></tr>
                    <tr><th>Nearest Zone</th><td className="val">{asset.nearestZoneId}</td></tr>
                    <tr><th>Buffer Distance</th><td className="val">{asset.distanceM} m</td></tr>
                    <tr><th>Impact Status</th><td className="val">{asset.impactStatus}</td></tr>
                  </tbody>
                </table>

                <div style={{ fontSize: "9px", color: "var(--ink-secondary)", background: "#f8fafc", padding: "6px", border: "1px solid var(--border-subtle)", marginTop: "6px" }}>
                  {asset.context}
                </div>

                <div style={{ marginTop: "8px" }}>
                  <button className="btnOutline" style={{ width: "100%" }} onClick={() => onSelectEntity(null)}>
                    Clear Inspector
                  </button>
                </div>
              </div>
            )}

            {!selectedEntity && (
              <div style={{ padding: "20px", textAlign: "center", color: "var(--muted)" }}>
                Click any sensor node (SN-001/002/003), risk zone (Z-001/002/003), or protected asset (A-001) on the GIS map to inspect live engineering telemetry.
              </div>
            )}
          </div>
        )}

        {/* TAB 3: AUDIT & RECOMMENDED OPERATOR ACTION */}
        {inspectorTab === "actions" && (
          <div className="inspectorBody">
            <div style={{ background: "#f8fafc", border: "1px solid var(--border-subtle)", padding: "8px", borderRadius: "3px" }}>
              <div style={{ fontSize: "8px", fontFamily: "var(--font-mono)", textTransform: "uppercase", color: "var(--muted)", fontWeight: 700 }}>
                Audit-Ready Decision Standard
              </div>
              <p style={{ fontSize: "10px", margin: "4px 0", color: "var(--ink-secondary)", lineHeight: 1.4 }}>
                MineGuard provides objective sensor telemetry, Random Forest classifications, and Peck trough physics residuals. Control-room responses must adhere to established colliery TARP (Trigger Action Response Plan).
              </p>
            </div>

            <table className="inspectTable">
              <tbody>
                <tr>
                  <th>Level 1: WATCH</th>
                  <td className="val">Verification &amp; visual corridor check</td>
                </tr>
                <tr>
                  <th>Level 2: HIGH</th>
                  <td className="val">Restrict heavy machinery within 100m</td>
                </tr>
                <tr>
                  <th>Level 3: CRITICAL</th>
                  <td className="val">Initiate geotechnical evacuation protocol</td>
                </tr>
              </tbody>
            </table>

            <div style={{ marginTop: "6px" }}>
              <button className="btnPrimary" style={{ width: "100%" }} onClick={() => onNavigateView("alerts")}>
                View Full Alert &amp; Action Center →
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
