"use client";

import React, { useState } from "react";
import type { NodeState, ZoneState } from "../lib/types";
import { computePhysicsSnapshot } from "../lib/physics";
import type { PhysicsParameters, SensorPhysicsOutput } from "../lib/physics/types";

interface PhysicsIntelPanelProps {
  stage: number;
  nodes: NodeState[];
  zones: ZoneState[];
  onParametersChange?: (params: PhysicsParameters) => void;
}

export function PhysicsIntelPanel({ stage, nodes, zones }: PhysicsIntelPanelProps) {
  const [showAssumptions, setShowAssumptions] = useState(false);
  const [calibrationFactor, setCalibrationFactor] = useState(1.0);

  // Compute physics snapshot using current stage and calibration factor
  const { snapshot } = computePhysicsSnapshot(stage, nodes, zones, {
    calibrationFactor,
  });

  const { params, grid, sensorOutputs } = snapshot;

  return (
    <div className="engPanel" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* ── PANEL HEADER ── */}
      <div className="engPanelHeader">
        <div className="engPanelTitle">
          <span>⌬</span>
          <span>Physics Intelligence &amp; Prediction Influence Model (PIM)</span>
          <span style={{ fontSize: "9px", background: "#fef3c7", color: "#92400e", padding: "1px 6px", borderRadius: "3px", marginLeft: "6px", fontWeight: 700 }}>
            SIMPLIFIED PROTOTYPE
          </span>
        </div>
        <div className="engPanelSub">
          KNOTHE-STYLE INFLUENCE FUNCTION · DUAL EVIDENCE COUPLING (PHYSICS + RANDOM FOREST)
        </div>
      </div>

      {/* ── MANDATORY PROTOTYPE DISCLAIMER ── */}
      <div style={{
        background: "#eff6ff",
        borderLeft: "4px solid #3b82f6",
        padding: "10px 14px",
        borderRadius: "0 4px 4px 0",
        fontSize: "11px",
        lineHeight: 1.5,
        color: "#1e3a8a",
      }}>
        <strong>Scientific Scope Notice:</strong> &ldquo;The prototype uses a simplified calibrated physics model; field deployment requires site-specific calibration using mining, geological and survey/InSAR observations.&rdquo;
      </div>

      {/* ── WORKFLOW / PIPELINE DIAGRAM ── */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        background: "#f8fafc",
        border: "1px solid var(--border)",
        borderRadius: "4px",
        padding: "10px 14px",
        fontSize: "10px",
        fontFamily: "var(--font-mono)",
      }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ color: "var(--muted)", fontSize: "9px" }}>INPUT</div>
          <strong style={{ color: "#0f766e" }}>Mining Parameters</strong>
        </div>
        <span style={{ color: "#94a3b8" }}>→</span>
        <div style={{ textAlign: "center" }}>
          <div style={{ color: "var(--muted)", fontSize: "9px" }}>PIM</div>
          <strong style={{ color: "#0f766e" }}>Knothe S(x,y,t)</strong>
        </div>
        <span style={{ color: "#94a3b8" }}>→</span>
        <div style={{ textAlign: "center" }}>
          <div style={{ color: "var(--muted)", fontSize: "9px" }}>DEFORMATION</div>
          <strong style={{ color: "#0284c7" }}>Expected Field</strong>
        </div>
        <span style={{ color: "#94a3b8" }}>→</span>
        <div style={{ textAlign: "center" }}>
          <div style={{ color: "var(--muted)", fontSize: "9px" }}>HARDWARE</div>
          <strong style={{ color: "#166534" }}>Sensor Observed</strong>
        </div>
        <span style={{ color: "#94a3b8" }}>→</span>
        <div style={{ textAlign: "center" }}>
          <div style={{ color: "var(--muted)", fontSize: "9px" }}>RESIDUAL</div>
          <strong style={{ color: "#7c3aed" }}>Obs − Exp</strong>
        </div>
        <span style={{ color: "#94a3b8" }}>→</span>
        <div style={{ textAlign: "center" }}>
          <div style={{ color: "var(--muted)", fontSize: "9px" }}>RANDOM FOREST</div>
          <strong style={{ color: "#b91c1c" }}>ML Decision</strong>
        </div>
      </div>

      {/* ── SIDE-BY-SIDE: PHYSICS MODEL VS ML MODEL EVIDENCE ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
        
        {/* LEFT: PHYSICS MODEL EVIDENCE */}
        <div style={{ background: "#ffffff", border: "1px solid var(--border)", borderRadius: "4px", padding: "12px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "6px" }}>
            <strong style={{ fontSize: "11px", textTransform: "uppercase", color: "#0f766e" }}>
              ⌬ Physics Model (Knothe PIM)
            </strong>
            <span style={{ fontSize: "9px", color: "var(--muted)", fontFamily: "var(--font-mono)" }}>
              Smax = {grid.sMaxMm.toFixed(2)} mm
            </span>
          </div>

          <table className="inspectTable" style={{ width: "100%" }}>
            <tbody>
              <tr>
                <th>Influence Radius (R)</th>
                <td className="val">{grid.influenceRadiusM} m</td>
              </tr>
              <tr>
                <th>Temporal Advance</th>
                <td className="val">{Math.round(params.temporalFactor * 100)}% (Stage {stage}/5)</td>
              </tr>
              <tr>
                <th>Calibration Factor</th>
                <td className="val">
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <input
                      type="range"
                      min="0.5"
                      max="1.5"
                      step="0.05"
                      value={calibrationFactor}
                      onChange={(e) => setCalibrationFactor(parseFloat(e.target.value))}
                      style={{ width: "70px" }}
                    />
                    <span>{calibrationFactor.toFixed(2)}×</span>
                  </div>
                </td>
              </tr>
              <tr>
                <th>Global Agreement</th>
                <td className="val">
                  {sensorOutputs.every((s: SensorPhysicsOutput) => s.physicsAgreement === "HIGH") ? (
                    <span style={{ color: "#166534", fontWeight: 700 }}>HIGH</span>
                  ) : sensorOutputs.some((s: SensorPhysicsOutput) => s.physicsAgreement === "LOW") ? (
                    <span style={{ color: "#b91c1c", fontWeight: 700 }}>LOW (RESIDUAL DIVERGENCE)</span>
                  ) : (
                    <span style={{ color: "#d97706", fontWeight: 700 }}>MODERATE</span>
                  )}
                </td>
              </tr>
            </tbody>
          </table>

          <div style={{ marginTop: "10px", fontSize: "9px", color: "var(--muted)", lineHeight: 1.4 }}>
            * Expected deformation is calculated independently from the mechanical extraction geometry. Does not alter ML features.
          </div>
        </div>

        {/* RIGHT: ML MODEL VERDICT (PRESERVED RANDOM FOREST OUTPUT) */}
        <div style={{ background: "#ffffff", border: "1px solid var(--border)", borderRadius: "4px", padding: "12px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "6px" }}>
            <strong style={{ fontSize: "11px", textTransform: "uppercase", color: "#1e3a8a" }}>
              ⌁ Machine Learning (Random Forest v6)
            </strong>
            <span style={{ fontSize: "9px", background: "#e0e7ff", color: "#3730a3", padding: "1px 6px", borderRadius: "3px", fontWeight: 700 }}>
              PROTECTED
            </span>
          </div>

          <table className="inspectTable" style={{ width: "100%" }}>
            <tbody>
              <tr>
                <th>Primary Classification</th>
                <td className="val" style={{ fontWeight: 700 }}>
                  {nodes[0]?.modelClass.replaceAll("_", " ").toUpperCase() ?? "NORMAL"}
                </td>
              </tr>
              <tr>
                <th>Mean Confidence</th>
                <td className="val">
                  {Math.round(
                    (nodes.reduce((acc, n) => acc + n.modelConfidence, 0) / (nodes.length || 1)) * 100
                  )}%
                </td>
              </tr>
              <tr>
                <th>Anomaly Progression</th>
                <td className="val" style={{ color: stage >= 4 ? "#b91c1c" : stage >= 2 ? "#d97706" : "#166534", fontWeight: 700 }}>
                  {stage >= 4 ? "PROGRESSIVE ADVANCE" : stage >= 2 ? "PERSISTENT ANOMALY" : "STABLE BASELINE"}
                </td>
              </tr>
              <tr>
                <th>System Assessment</th>
                <td className="val" style={{ fontWeight: 700, color: "var(--ink)" }}>
                  EXISTING ML DECISION
                </td>
              </tr>
            </tbody>
          </table>

          <div style={{ marginTop: "10px", fontSize: "9px", color: "var(--muted)", lineHeight: 1.4 }}>
            * ML inference relies on live sensor pre-processing, vibration guardrails, and temporal correlation windows.
          </div>
        </div>
      </div>

      {/* ── SENSOR-BY-SENSOR RESIDUAL MATRIX ── */}
      <div style={{ background: "#ffffff", border: "1px solid var(--border)", borderRadius: "4px", padding: "12px" }}>
        <div style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase", marginBottom: "8px" }}>
          Sensor Physics Residual Breakdown (Observed − Expected)
        </div>

        <table className="networkTable" style={{ width: "100%" }}>
          <thead>
            <tr>
              <th>Node ID</th>
              <th>Observed Disp (mm)</th>
              <th>Knothe Expected (mm)</th>
              <th>Residual (mm)</th>
              <th>Agreement</th>
              <th>Diagnostic Evidence</th>
            </tr>
          </thead>
          <tbody>
            {sensorOutputs.map((so: SensorPhysicsOutput) => {
              const node = nodes.find((n) => n.id === so.nodeId);
              return (
                <tr key={so.nodeId}>
                  <td style={{ fontWeight: 700, fontFamily: "var(--font-mono)" }}>{so.nodeId}</td>
                  <td style={{ fontFamily: "var(--font-mono)" }}>{so.observedMm.toFixed(2)}</td>
                  <td style={{ fontFamily: "var(--font-mono)" }}>{so.expectedMm.toFixed(2)}</td>
                  <td style={{
                    fontFamily: "var(--font-mono)",
                    fontWeight: 700,
                    color: Math.abs(so.residualMm) > 1.2 ? "#b91c1c" : Math.abs(so.residualMm) > 0.3 ? "#d97706" : "#166534"
                  }}>
                    {so.residualMm >= 0 ? "+" : ""}{so.residualMm.toFixed(2)}
                  </td>
                  <td>
                    <span className={`badge ${
                      so.physicsAgreement === "HIGH"
                        ? "badge-normal"
                        : so.physicsAgreement === "MODERATE"
                        ? "badge-watch"
                        : "badge-critical"
                    }`}>
                      {so.physicsAgreement}
                    </span>
                  </td>
                  <td style={{ fontSize: "9px", color: "var(--muted)" }}>
                    {so.residualNote} {node?.modelClass === "decoy_seismic" ? " (Vibration decoy confirmed by ML)" : ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* ── EXPANDABLE: MODEL ASSUMPTIONS & PARAMETERS ── */}
      <div style={{ background: "#ffffff", border: "1px solid var(--border)", borderRadius: "4px", padding: "12px" }}>
        <div
          onClick={() => setShowAssumptions(!showAssumptions)}
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            cursor: "pointer",
            fontWeight: 700,
            fontSize: "11px",
            textTransform: "uppercase"
          }}
        >
          <span>⌬ Model Assumptions &amp; Geotechnical Parameters</span>
          <span>{showAssumptions ? "▲ Collapse" : "▼ Expand (8 Parameters)"}</span>
        </div>

        {showAssumptions && (
          <div style={{ marginTop: "12px" }}>
            <table className="networkTable" style={{ width: "100%" }}>
              <thead>
                <tr>
                  <th>Parameter</th>
                  <th>Configured Value</th>
                  <th>Classification</th>
                  <th>Description / Justification</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Panel Width</td>
                  <td style={{ fontFamily: "var(--font-mono)" }}>{params.panelWidthM} m</td>
                  <td><span style={{ fontSize: "8px", background: "#f1f5f9", padding: "2px 4px", borderRadius: "2px" }}>Prototype assumption</span></td>
                  <td style={{ fontSize: "9px", color: "var(--muted)" }}>Typical transverse width along strike for medium retreat panel</td>
                </tr>
                <tr>
                  <td>Panel Length</td>
                  <td style={{ fontFamily: "var(--font-mono)" }}>{params.panelLengthM} m</td>
                  <td><span style={{ fontSize: "8px", background: "#f1f5f9", padding: "2px 4px", borderRadius: "2px" }}>Prototype assumption</span></td>
                  <td style={{ fontSize: "9px", color: "var(--muted)" }}>Total panel dimension along retreat face direction</td>
                </tr>
                <tr>
                  <td>Seam Depth (H)</td>
                  <td style={{ fontFamily: "var(--font-mono)" }}>{params.panelDepthM} m</td>
                  <td><span style={{ fontSize: "8px", background: "#f1f5f9", padding: "2px 4px", borderRadius: "2px" }}>Prototype assumption</span></td>
                  <td style={{ fontSize: "9px", color: "var(--muted)" }}>Overburden depth from surface reference level to coal roof</td>
                </tr>
                <tr>
                  <td>Extracted Thickness (m)</td>
                  <td style={{ fontFamily: "var(--font-mono)" }}>{params.extractedThicknessM} m</td>
                  <td><span style={{ fontSize: "8px", background: "#f1f5f9", padding: "2px 4px", borderRadius: "2px" }}>Prototype assumption</span></td>
                  <td style={{ fontSize: "9px", color: "var(--muted)" }}>Average working seam extraction height</td>
                </tr>
                <tr>
                  <td>Extraction Ratio (q)</td>
                  <td style={{ fontFamily: "var(--font-mono)" }}>{params.extractionRatio}</td>
                  <td><span style={{ fontSize: "8px", background: "#f1f5f9", padding: "2px 4px", borderRadius: "2px" }}>Prototype assumption</span></td>
                  <td style={{ fontSize: "9px", color: "var(--muted)" }}>Net void recovery fraction in total extraction caving</td>
                </tr>
                <tr>
                  <td>Subsidence Coefficient (a)</td>
                  <td style={{ fontFamily: "var(--font-mono)" }}>{params.subsidenceCoefficient}</td>
                  <td><span style={{ fontSize: "8px", background: "#f1f5f9", padding: "2px 4px", borderRadius: "2px" }}>Prototype assumption</span></td>
                  <td style={{ fontSize: "9px", color: "var(--muted)" }}>Empirical maximum subsidence ratio (Salamon 1963 / Whittaker 1989)</td>
                </tr>
                <tr>
                  <td>Angle of Influence (θ)</td>
                  <td style={{ fontFamily: "var(--font-mono)" }}>{params.influenceAngleDeg}°</td>
                  <td><span style={{ fontSize: "8px", background: "#f1f5f9", padding: "2px 4px", borderRadius: "2px" }}>Prototype assumption</span></td>
                  <td style={{ fontSize: "9px", color: "var(--muted)" }}>Angle from vertical defining the subsidence trough limit radius R</td>
                </tr>
                <tr>
                  <td>Calibration Factor</td>
                  <td style={{ fontFamily: "var(--font-mono)" }}>{params.calibrationFactor.toFixed(2)}×</td>
                  <td><span style={{ fontSize: "8px", background: "#dbeafe", color: "#1e40af", padding: "2px 4px", borderRadius: "2px", fontWeight: 700 }}>Prototype calibration factor</span></td>
                  <td style={{ fontSize: "9px", color: "var(--muted)" }}>Explicit user-adjustable scaling factor for prototype validation</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
