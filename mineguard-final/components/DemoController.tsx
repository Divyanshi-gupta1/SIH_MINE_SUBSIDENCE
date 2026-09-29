import React from "react";
import type { OperationMode, ScenarioKey } from "../lib/types";
import { stageDescriptions, stageLabels } from "../lib/demo";

interface DemoControllerProps {
  operationMode: OperationMode;
  onModeChange: (mode: OperationMode) => void;
  scenario: ScenarioKey;
  onScenarioChange: (scenario: ScenarioKey) => void;
  stage: number;
  onStageChange: (stage: number) => void;
  running: boolean;
  onStart: () => void;
  onPause: () => void;
  onReset: () => void;
  speed: 1 | 2 | 4;
  onSpeedChange: (speed: 1 | 2 | 4) => void;
}

export function DemoController({
  operationMode,
  onModeChange,
  scenario,
  onScenarioChange,
  stage,
  onStageChange,
  running,
  onStart,
  onPause,
  onReset,
  speed,
  onSpeedChange
}: DemoControllerProps) {
  const scenarioOptions: { key: ScenarioKey; label: string; desc: string }[] = [
    {
      key: "normal",
      label: "NORMAL BASELINE",
      desc: "All sensor nodes report nominal baseline readings. No material ground movement."
    },
    {
      key: "false_local",
      label: "LOCAL DISTURBANCE",
      desc: "Single-node vibration spike (surface equipment/blasting). RF classifier detects decoy_seismic; no false escalation."
    },
    {
      key: "persistent",
      label: "PERSISTENT DEFORMATION",
      desc: "Slow sustained ground movement across multiple observation windows in Western corridor."
    },
    {
      key: "progressive",
      label: "PROGRESSIVE SUBSIDENCE",
      desc: "Multi-node accelerating ground displacement front propagating toward protected asset A-001."
    },
    {
      key: "offline_gap",
      label: "OFFLINE / RECONNECT",
      desc: "Node SN-002 loses signal (>30s silence). Demonstrates monitoring gap & reduced data confidence without zero-fill assumption."
    }
  ];

  return (
    <div className="demoCard">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "8px" }}>
        <div>
          <strong style={{ fontSize: "12px", textTransform: "uppercase" }}>
            Operational Demonstration Controller
          </strong>
          <div style={{ fontSize: "9px", color: "var(--muted)" }}>
            SIMULATE OPERATIONAL STAGES CONSUMING THE CANONICAL MINEGUARD DATA CONTRACT
          </div>
        </div>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            background: "#f1f5f9",
            border: "1px solid var(--border)",
            padding: "2px 8px",
            borderRadius: "3px"
          }}
        >
          STAGE {stage} / 5
        </span>
      </div>

      {/* Data Source Selector */}
      <div className="demoSectionGroup">
        <label className="demoSectionLabel">Data Source Profile</label>
        <div className="segmentedCtrl">
          {(["DEMO", "LIVE_TESTBED", "LIVE_MINE"] as OperationMode[]).map((mode) => (
            <button
              key={mode}
              className={`segmentedBtn ${operationMode === mode ? "active" : ""}`}
              onClick={() => onModeChange(mode)}
            >
              {mode === "DEMO"
                ? "DEMO MODE"
                : mode === "LIVE_TESTBED"
                ? "LIVE TESTBED (USB/LORA)"
                : "LIVE MINE (INTEGRATION)"}
            </button>
          ))}
        </div>
        {operationMode !== "DEMO" && (
          <div style={{ fontSize: "9px", color: "var(--muted)", marginTop: "4px" }}>
            * Stage buttons are disabled in live modes because telemetry is driven by physical hardware or integration streams.
          </div>
        )}
      </div>

      {/* Scenario Selector */}
      <div className="demoSectionGroup">
        <label className="demoSectionLabel">Demonstration Scenario</label>
        <div className="segmentedCtrl">
          {scenarioOptions.map((opt) => (
            <button
              key={opt.key}
              disabled={operationMode !== "DEMO"}
              className={`segmentedBtn ${scenario === opt.key ? "active" : ""}`}
              onClick={() => onScenarioChange(opt.key)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <div style={{ fontSize: "9px", color: "var(--ink-secondary)", background: "#f8fafc", padding: "6px 8px", border: "1px solid var(--border-subtle)", marginTop: "4px", borderRadius: "2px" }}>
          {scenarioOptions.find((s) => s.key === scenario)?.desc}
        </div>
      </div>

      {/* Playback Controls & Speed */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
        <div className="demoSectionGroup">
          <label className="demoSectionLabel">Playback Controls</label>
          <div className="segmentedCtrl">
            <button
              className="btnPrimary"
              disabled={operationMode !== "DEMO" || running}
              onClick={onStart}
            >
              ▶ START
            </button>
            <button
              className="btnOutline"
              disabled={operationMode !== "DEMO" || !running}
              onClick={onPause}
            >
              ⏸ PAUSE
            </button>
            <button
              className="btnOutline"
              disabled={operationMode !== "DEMO"}
              onClick={onReset}
            >
              ↺ RESET
            </button>
          </div>
        </div>

        <div className="demoSectionGroup">
          <label className="demoSectionLabel">Playback Speed</label>
          <div className="segmentedCtrl">
            {([1, 2, 4] as const).map((s) => (
              <button
                key={s}
                disabled={operationMode !== "DEMO"}
                className={`segmentedBtn ${speed === s ? "active" : ""}`}
                onClick={() => onSpeedChange(s)}
              >
                {s}×
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Progress Track & Stage Summary */}
      <div>
        <div style={{ height: "4px", background: "#e2e8f0", borderRadius: "2px", overflow: "hidden", margin: "8px 0" }}>
          <div
            style={{
              height: "100%",
              background: "#0284c7",
              width: `${(stage / 5) * 100}%`,
              transition: "width 0.25s ease"
            }}
          />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <strong style={{ fontSize: "11px", fontFamily: "var(--font-mono)" }}>
            Current Stage: {stageLabels[stage]}
          </strong>
          <span style={{ fontSize: "9px", color: "var(--muted)" }}>
            {stageDescriptions[stage]}
          </span>
        </div>
      </div>
    </div>
  );
}
