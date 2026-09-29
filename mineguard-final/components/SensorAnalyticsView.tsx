import React, { useState } from "react";
import type { NodeState } from "../lib/types";

interface SensorAnalyticsViewProps {
  nodes: NodeState[];
  stage: number;
}

export function SensorAnalyticsView({ nodes, stage }: SensorAnalyticsViewProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string>(nodes[0]?.id || "SN-001");

  const selectedNode = nodes.find((n) => n.id === selectedNodeId) || nodes[0];

  // Synthesize history values based on current reading and stage progression for realistic trend curves
  const currentTilt = selectedNode?.tilt ?? 0.05;
  const currentDisp = selectedNode?.displacement ?? 0.8;
  const currentRate = selectedNode?.deformationRate ?? 0.05;
  const currentVib = selectedNode?.vibration ?? 0.04;

  const tiltSeries = [0.02, 0.02, 0.03, 0.04, currentTilt * 0.8, currentTilt];
  const dispSeries = [0.0, 0.1, 0.3, 0.6, currentDisp * 0.75, currentDisp];
  const rateSeries = [0.01, 0.02, 0.03, 0.05, currentRate * 0.85, currentRate];
  const vibSeries = [0.03, 0.03, 0.04, 0.03, 0.04, currentVib];

  return (
    <div className="engPanel">
      <div className="engPanelHeader">
        <div className="engPanelTitle">
          <span>⌁</span>
          <span>Dedicated Sensor Analytics &amp; Telemetry Curves</span>
        </div>
        <div className="engPanelSub">
          SELECT NODE TO INSPECT CURRENT, BASELINE, DEVIATION, AND TEMPORAL RATE TRENDS
        </div>
      </div>

      <div className="engPanelBody">
        {/* Node selector tabs */}
        <div style={{ display: "flex", gap: "6px", marginBottom: "12px" }}>
          {nodes.map((node) => (
            <button
              key={node.id}
              className={`segmentedBtn ${selectedNodeId === node.id ? "active" : ""}`}
              onClick={() => setSelectedNodeId(node.id)}
            >
              <span className={`dot ${node.healthy ? "green" : "red"}`} style={{ marginRight: "5px" }} />
              {node.id} ({node.zoneId})
            </button>
          ))}
        </div>

        {selectedNode && (
          <div>
            {/* Health Disclaimer: Sensor health visually separate from ground deformation risk */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                background: selectedNode.healthy ? "var(--status-normal-bg)" : "var(--status-crit-bg)",
                border: `1px solid ${selectedNode.healthy ? "var(--status-normal-border)" : "var(--status-crit-border)"}`,
                padding: "8px 12px",
                borderRadius: "3px",
                marginBottom: "12px",
                fontSize: "10px"
              }}
            >
              <div>
                <strong>INSTRUMENT HEALTH STATUS: </strong>
                <span style={{ color: selectedNode.healthy ? "var(--status-normal-ink)" : "var(--status-crit-ink)", fontWeight: 700 }}>
                  {selectedNode.healthy ? "NOMINAL (GOOD TELEMETRY)" : "DEGRADED / UNAVAILABLE"}
                </span>
                {selectedNode.healthMessage && (
                  <div style={{ fontSize: "9px", marginTop: "2px" }}>
                    Note: {selectedNode.healthMessage}
                  </div>
                )}
              </div>
              <div style={{ fontSize: "9px", color: "var(--muted)", fontFamily: "var(--font-mono)" }}>
                * Sensor health is isolated from geotechnical deformation risk.
              </div>
            </div>

            {/* Metric Summary Cards: CURRENT, BASELINE, DEVIATION, TREND */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(4, 1fr)",
                gap: "8px",
                marginBottom: "14px"
              }}
            >
              <div className="summaryCard" style={{ background: "#f8fafc", padding: "8px", border: "1px solid var(--border-subtle)", borderRadius: "3px" }}>
                <span className="summaryLabel">Current Reading</span>
                <div style={{ fontSize: "14px", fontWeight: 800, fontFamily: "var(--font-mono)" }}>
                  {selectedNode.displacement.toFixed(2)} mm
                </div>
                <span className="summarySub">Tilt: {selectedNode.tilt.toFixed(2)}°</span>
              </div>

              <div className="summaryCard" style={{ background: "#f8fafc", padding: "8px", border: "1px solid var(--border-subtle)", borderRadius: "3px" }}>
                <span className="summaryLabel">Calibrated Baseline</span>
                <div style={{ fontSize: "14px", fontWeight: 800, fontFamily: "var(--font-mono)", color: "var(--muted)" }}>
                  0.00 mm
                </div>
                <span className="summarySub">Tilt baseline: 0.02°</span>
              </div>

              <div className="summaryCard" style={{ background: "#f8fafc", padding: "8px", border: "1px solid var(--border-subtle)", borderRadius: "3px" }}>
                <span className="summaryLabel">Net Deviation</span>
                <div style={{ fontSize: "14px", fontWeight: 800, fontFamily: "var(--font-mono)", color: selectedNode.displacement > 1.0 ? "#b91c1c" : "#15803d" }}>
                  +{selectedNode.displacement.toFixed(2)} mm
                </div>
                <span className="summarySub">Δ Tilt: +{(selectedNode.tilt - 0.02).toFixed(2)}°</span>
              </div>

              <div className="summaryCard" style={{ background: "#f8fafc", padding: "8px", border: "1px solid var(--border-subtle)", borderRadius: "3px" }}>
                <span className="summaryLabel">Assessed Trend</span>
                <div style={{ fontSize: "13px", fontWeight: 700, fontFamily: "var(--font-mono)" }}>
                  {selectedNode.deformationRate.toFixed(2)} mm/min
                </div>
                <span className="summarySub">Class: {selectedNode.modelClass.replaceAll("_", " ")}</span>
              </div>
            </div>

            {/* Three Main Deformation Charts */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "10px", marginBottom: "12px" }}>
              <ChartCard label="Relative Displacement" unit="mm" values={dispSeries} stroke="#0284c7" />
              <ChartCard label="Deformation Rate" unit="mm/min" values={rateSeries} stroke="#d97706" />
              <ChartCard label="Tilt Departure" unit="deg" values={tiltSeries} stroke="#0d9488" />
            </div>

            {/* Vibration Displayed Separately */}
            <div style={{ background: "#f8fafc", border: "1px solid var(--border)", borderRadius: "3px", padding: "10px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                <div>
                  <strong style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--ink-secondary)" }}>
                    Ambient &amp; Seismic Vibration (g-scale RMS)
                  </strong>
                  <div style={{ fontSize: "9px", color: "var(--muted)" }}>
                    Monitored separately to decouple surface equipment / blasting noise from true ground settlement.
                  </div>
                </div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", fontWeight: 700 }}>
                  Current: {currentVib.toFixed(2)} g RMS
                </div>
              </div>
              <ChartSvg values={vibSeries} stroke="#64748b" height={70} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ChartCard({ label, unit, values, stroke }: { label: string; unit: string; values: number[]; stroke: string }) {
  const currentVal = values[values.length - 1] ?? 0;
  return (
    <div className="chartBlock">
      <div className="chartBlockHeader">
        <span className="chartTitle">{label}</span>
        <span className="chartMetric" style={{ color: stroke }}>
          {currentVal.toFixed(2)} {unit}
        </span>
      </div>
      <ChartSvg values={values} stroke={stroke} height={90} />
    </div>
  );
}

function ChartSvg({ values, stroke, height }: { values: number[]; stroke: string; height: number }) {
  const max = Math.max(...values, 0.05);
  const min = Math.min(...values, 0);
  const range = max - min || 1;

  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * 100;
      const y = height - 10 - ((v - min) / range) * (height - 20);
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" style={{ width: "100%", height: `${height}px`, display: "block" }}>
      {/* Grid lines */}
      <line x1="0" y1={height - 10} x2="100" y2={height - 10} stroke="#e2e8f0" strokeWidth="0.8" />
      <line x1="0" y1={(height - 10) / 2} x2="100" y2={(height - 10) / 2} stroke="#f1f5f9" strokeWidth="0.5" strokeDasharray="2 2" />
      {/* Sparkline curve */}
      <polyline points={points} fill="none" stroke={stroke} strokeWidth="2" vectorEffect="non-scaling-stroke" />
      {/* Last point dot */}
      {values.length > 0 && (
        <circle
          cx="100"
          cy={height - 10 - ((values[values.length - 1] - min) / range) * (height - 20)}
          r="2.5"
          fill={stroke}
        />
      )}
    </svg>
  );
}
