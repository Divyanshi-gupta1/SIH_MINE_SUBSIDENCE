import React, { useState } from "react";
import type { ZoneState } from "../lib/types";
import { StateBadge } from "./StateBadge";

interface ZoneAnalyticsViewProps {
  zones: ZoneState[];
}

export function ZoneAnalyticsView({ zones }: ZoneAnalyticsViewProps) {
  const [selectedZoneId, setSelectedZoneId] = useState<string>(zones[0]?.id || "Z-001");

  const selectedZone = zones.find((z) => z.id === selectedZoneId) || zones[0];

  return (
    <div className="engPanel">
      <div className="engPanelHeader">
        <div className="engPanelTitle">
          <span>◇</span>
          <span>Zone Intelligence &amp; Geotechnical Physics Analytics</span>
        </div>
        <div className="engPanelSub">
          SECTOR-BY-SECTOR COMPARISON: OBSERVED SENSOR MOVEMENT VS. PECK EMPIRICAL PROFILE RESIDUALS
        </div>
      </div>

      <div className="engPanelBody">
        {/* Zone selection buttons */}
        <div style={{ display: "flex", gap: "6px", marginBottom: "12px" }}>
          {zones.map((zone) => (
            <button
              key={zone.id}
              className={`segmentedBtn ${selectedZoneId === zone.id ? "active" : ""}`}
              onClick={() => setSelectedZoneId(zone.id)}
            >
              {zone.id} — {zone.name}
            </button>
          ))}
        </div>

        {selectedZone && (
          <div>
            {/* Zone Headline Banner */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                background: "#f8fafc",
                border: "1px solid var(--border)",
                padding: "10px 14px",
                borderRadius: "3px",
                marginBottom: "12px"
              }}
            >
              <div>
                <strong style={{ fontSize: "14px", fontFamily: "var(--font-mono)" }}>
                  Zone {selectedZone.id}: {selectedZone.name}
                </strong>
                <div style={{ fontSize: "10px", color: "var(--muted)", marginTop: "2px" }}>
                  Spatial Direction: {selectedZone.direction} · Distance to Protected Asset A-001: {selectedZone.assetDistanceM}m
                </div>
              </div>
              <StateBadge state={selectedZone.state} />
            </div>

            {/* Geotechnical Physics Comparison Grid */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(3, 1fr)",
                gap: "8px",
                marginBottom: "14px"
              }}
            >
              <div className="summaryCard" style={{ background: "#ffffff", padding: "10px", border: "1px solid var(--border)", borderRadius: "3px" }}>
                <span className="summaryLabel">Observed Deformation</span>
                <div style={{ fontSize: "16px", fontWeight: 800, fontFamily: "var(--font-mono)", color: "var(--ink)" }}>
                  {selectedZone.observedMm?.toFixed(2) ?? "0.00"} mm
                </div>
                <span className="summarySub">Direct composite sensor telemetry</span>
              </div>

              <div className="summaryCard" style={{ background: "#ffffff", padding: "10px", border: "1px solid var(--border)", borderRadius: "3px" }}>
                <span className="summaryLabel">Peck Physics Expected</span>
                <div style={{ fontSize: "16px", fontWeight: 800, fontFamily: "var(--font-mono)", color: "#0284c7" }}>
                  {selectedZone.physicsExpectedMm?.toFixed(2) ?? "0.00"} mm
                </div>
                <span className="summarySub">Empirical Gaussian subsidence profile</span>
              </div>

              <div className="summaryCard" style={{ background: "#ffffff", padding: "10px", border: "1px solid var(--border)", borderRadius: "3px" }}>
                <span className="summaryLabel">Physics Residual (|Obs - Exp|)</span>
                <div
                  style={{
                    fontSize: "16px",
                    fontWeight: 800,
                    fontFamily: "var(--font-mono)",
                    color: (selectedZone.physicsResidualMm ?? 0) > 1.0 ? "#c2410c" : "#15803d"
                  }}
                >
                  {selectedZone.physicsResidualMm?.toFixed(2) ?? "0.00"} mm
                </div>
                <span className="summarySub">Status: {selectedZone.physicsStatus ?? "NOMINAL"}</span>
              </div>
            </div>

            {/* Comprehensive Detail Table */}
            <div style={{ background: "#ffffff", border: "1px solid var(--border)", borderRadius: "3px", overflow: "hidden", marginBottom: "12px" }}>
              <table className="networkTable">
                <tbody>
                  <tr>
                    <th style={{ width: "240px" }}>Assessed Operational State</th>
                    <td><StateBadge state={selectedZone.state} /></td>
                  </tr>
                  <tr>
                    <th>Observed Deformation Trend</th>
                    <td style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}>{selectedZone.trend}</td>
                  </tr>
                  <tr>
                    <th>Spatial Movement Vector Direction</th>
                    <td style={{ fontFamily: "var(--font-mono)" }}>{selectedZone.direction}</td>
                  </tr>
                  <tr>
                    <th>Machine Learning Classifier Verdict</th>
                    <td style={{ fontFamily: "var(--font-mono)", fontWeight: 700, color: "#0284c7" }}>
                      {selectedZone.modelVerdict ?? "normal"}
                    </td>
                  </tr>
                  <tr>
                    <th>Multi-Sensor Corroboration Confidence</th>
                    <td>
                      <span className={`badge ${selectedZone.confidence === "HIGH" ? "badge-normal" : "badge-persistent"}`}>
                        {selectedZone.confidence} CONFIDENCE
                      </span>
                    </td>
                  </tr>
                  <tr>
                    <th>Temporal Progression Phase</th>
                    <td style={{ fontFamily: "var(--font-mono)" }}>{selectedZone.temporalStatus ?? "Nominal baseline"}</td>
                  </tr>
                  <tr>
                    <th>Protected Infrastructure Impact</th>
                    <td style={{ fontWeight: 600 }}>{selectedZone.assetImpact ?? "None"}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Evidence List */}
            <div className="evidenceSection">
              <div className="evidenceHeader">Sensor &amp; Analytical Evidence for {selectedZone.id}:</div>
              <ul className="evidenceUl">
                {selectedZone.evidence.map((item, idx) => (
                  <li key={idx}>• {item}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
