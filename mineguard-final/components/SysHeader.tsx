import React from "react";
import type { OperationMode } from "../lib/types";

interface SysHeaderProps {
  operationMode: OperationMode;
  onModeChange: (mode: OperationMode) => void;
  isLiveActive: boolean;
  monitoringState: "ACTIVE" | "STANDBY" | "CALIBRATING";
  gatewayState: "CONNECTED" | "STANDBY" | "OFFLINE";
  lastUpdate: string;
  cloudConnected: boolean;
  onToggleCloud: () => void;
}

export function SysHeader({
  operationMode,
  onModeChange,
  isLiveActive,
  monitoringState,
  gatewayState,
  lastUpdate,
  cloudConnected,
  onToggleCloud
}: SysHeaderProps) {
  return (
    <header className="sysHeader">
      <div className="sysHeaderBrand">
        <div className="brandBadge">MG-ENG</div>
        <div>
          <div className="sysTitle">MineGuard · Geotechnical Command</div>
          <div className="sysSub">Mine Subsidence Monitoring &amp; Early Warning System</div>
        </div>
      </div>

      <div className="sysHeaderMeta">
        <div className="sysMetaGroup">
          <label>Monitoring State</label>
          <div className="sysMetaVal">
            <span className={`dot ${monitoringState === "ACTIVE" ? "green" : "amber"}`} />
            {monitoringState}
          </div>
        </div>

        <div className="sysMetaGroup">
          <label>Data Source</label>
          <div className="modeSelector">
            {(["DEMO", "LIVE_TESTBED", "LIVE_MINE"] as OperationMode[]).map((mode) => (
              <button
                key={mode}
                className={`modeBtn ${operationMode === mode ? "active" : ""}`}
                onClick={() => onModeChange(mode)}
              >
                {mode === "DEMO"
                  ? "DEMO"
                  : mode === "LIVE_TESTBED"
                  ? "LIVE TESTBED"
                  : "LIVE MINE"}
              </button>
            ))}
          </div>
        </div>

        <div className="sysMetaGroup">
          <label>Gateway (GW-001)</label>
          <div className="sysMetaVal">
            <span
              className={`dot ${
                gatewayState === "CONNECTED"
                  ? "green"
                  : gatewayState === "STANDBY"
                  ? "amber"
                  : "red"
              }`}
            />
            {gatewayState}
          </div>
        </div>

        <div className="sysMetaGroup">
          <label>Last Update</label>
          <div className="sysMetaVal">{lastUpdate}</div>
        </div>

        <div className="sysMetaGroup">
          <label>Mesh &amp; Cloud</label>
          <div className="sysMetaVal">
            <span>LoRa 915MHz</span>
            <span>·</span>
            <button
              onClick={onToggleCloud}
              style={{
                border: 0,
                background: "transparent",
                color: cloudConnected ? "#22c55e" : "#f59e0b",
                fontFamily: "var(--font-mono)",
                fontSize: "10px",
                fontWeight: 600,
                padding: 0,
                cursor: "pointer"
              }}
              title="Click to toggle cloud link simulation"
            >
              {cloudConnected ? "Cloud Synced" : "Cloud Offline"}
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
