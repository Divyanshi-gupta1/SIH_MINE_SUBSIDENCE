"use client";

import { useEffect, useMemo, useState } from "react";
import {
  alertsFor,
  getAssetStatus,
  nodesFor,
  overallState,
  zonesFor
} from "../lib/demo";
import type {
  Alert,
  AlertLifecycle,
  LayerKey,
  NodeState,
  OperationMode,
  RiskState,
  ScenarioKey,
  ViewKey,
  ZoneState
} from "../lib/types";

import { SysHeader } from "../components/SysHeader";
import { SituationSummary } from "../components/SituationSummary";
import { GisCommandMap } from "../components/GisCommandMap";
import { OperationalPanel } from "../components/OperationalPanel";
import { SensorAnalyticsView } from "../components/SensorAnalyticsView";
import { ZoneAnalyticsView } from "../components/ZoneAnalyticsView";
import { DemoController } from "../components/DemoController";
import { HistoryReplayView } from "../components/HistoryReplayView";
import { NetworkHealthView } from "../components/NetworkHealthView";
import { StateBadge } from "../components/StateBadge";
import { PhysicsIntelPanel } from "../components/PhysicsIntelPanel";

const navTabs: { key: ViewKey; label: string; icon: string }[] = [
  { key: "command", label: "Command Center", icon: "▦" },
  { key: "map", label: "Primary GIS Map", icon: "⌖" },
  { key: "physics", label: "Physics Intelligence", icon: "⌬" },
  { key: "zones", label: "Zone Analytics", icon: "◇" },
  { key: "sensors", label: "Sensor Analytics", icon: "⌁" },
  { key: "alerts", label: "Alerts & Actions", icon: "!" },
  { key: "history", label: "Event Replay", icon: "↺" },
  { key: "network", label: "Network Health", icon: "⌁" },
  { key: "demo", label: "Demo Controller", icon: "▶" },
  { key: "settings", label: "Engineering Settings", icon: "⚙" }
];

export default function Home() {
  const [view, setView] = useState<ViewKey>("command");
  const [operationMode, setOperationMode] = useState<OperationMode>("DEMO");
  const [stage, setStage] = useState(0);
  const [scenario, setScenario] = useState<ScenarioKey>("progressive");
  const [demoRunning, setDemoRunning] = useState(false);
  const [demoSpeed, setDemoSpeed] = useState<1 | 2 | 4>(1);
  const [alertLifecycle, setAlertLifecycle] = useState<AlertLifecycle>("NEW");
  const [cloud, setCloud] = useState(true);

  // Selected entity for detailed GIS and inspector view
  const [selectedEntity, setSelectedEntity] = useState<{
    type: "node" | "zone" | "asset";
    id: string;
  } | null>(null);

  // Map layer controls
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>({
    grid: true,
    sensors: true,
    risk: true,
    vectors: true,
    assets: true,
    impact: true,
    physics: false,
    network: true,
    heatmap: true,
    residual: false,
    history: true
  });

  // Live telemetry state from /api/state
  const [liveData, setLiveData] = useState<any>(null);

  // Polling backend state every second
  useEffect(() => {
    let mounted = true;
    const poll = async () => {
      try {
        const res = await fetch("/api/state?mode=" + operationMode, { cache: "no-store" });
        if (res.ok && mounted) {
          const data = await res.json();
          setLiveData(data);
        }
      } catch {
        // network exception handled gracefully
      }
    };
    poll();
    const interval = setInterval(poll, 1000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [operationMode]);

  // Determine if live hardware telemetry stream is currently active
  const isLiveActive = operationMode !== "DEMO" && Boolean(liveData?.is_live);

  // Synchronized zones
  const zones: ZoneState[] = useMemo(() => {
    if (isLiveActive && liveData?.zones) return liveData.zones as ZoneState[];
    return zonesFor(stage, scenario);
  }, [stage, scenario, isLiveActive, liveData]);

  // Synchronized nodes
  const nodes: NodeState[] = useMemo(() => {
    if (isLiveActive && liveData?.nodes) return liveData.nodes as NodeState[];
    return nodesFor(stage, scenario);
  }, [stage, scenario, isLiveActive, liveData]);

  // Synchronized alerts
  const alerts: Alert[] = useMemo(() => {
    if (isLiveActive && liveData?.alerts) return liveData.alerts as Alert[];
    return alertsFor(zones, stage, scenario);
  }, [zones, stage, scenario, isLiveActive, liveData]);

  // Effective operational stage (0 to 5)
  const effectiveStage = useMemo(() => {
    if (isLiveActive && typeof liveData?.stage === "number") return liveData.stage;
    return stage;
  }, [stage, isLiveActive, liveData]);

  // Overall ground risk condition
  const overall = useMemo(() => {
    if (isLiveActive && liveData?.overall_state) return liveData.overall_state as RiskState;
    return overallState(zones);
  }, [zones, isLiveActive, liveData]);

  // Synchronized asset state
  const asset = useMemo(() => {
    return getAssetStatus(effectiveStage, scenario);
  }, [effectiveStage, scenario]);

  const currentAlert = alerts[0];

  // Automated demonstration timer
  useEffect(() => {
    if (!demoRunning || operationMode !== "DEMO") return;
    const timer = window.setInterval(() => {
      setStage((curr) => {
        if (curr >= 5) {
          setDemoRunning(false);
          return curr;
        }
        return curr + 1;
      });
    }, 8000 / demoSpeed);
    return () => window.clearInterval(timer);
  }, [demoRunning, demoSpeed, operationMode]);

  function handleModeChange(nextMode: OperationMode) {
    setOperationMode(nextMode);
    if (nextMode !== "DEMO") {
      setDemoRunning(false);
    }
  }

  function handleScenarioChange(nextScenario: ScenarioKey) {
    setScenario(nextScenario);
    setStage(nextScenario === "normal" ? 0 : 1);
    setAlertLifecycle("NEW");
    setDemoRunning(false);
  }

  function handleResetDemo() {
    setStage(0);
    setScenario("progressive");
    setAlertLifecycle("NEW");
    setDemoRunning(false);
  }

  function toggleLayer(key: LayerKey) {
    setLayers((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  const activeAlertsCount = alerts.filter(
    (a) => a.lifecycle !== "DISMISSED" && a.lifecycle !== "SENSOR_ISSUE" && a.lifecycle !== "CONFIRMED"
  ).length;

  return (
    <div className="shell">
      {/* 1. TOP SYSTEM HEADER */}
      <SysHeader
        operationMode={operationMode}
        onModeChange={handleModeChange}
        isLiveActive={isLiveActive}
        monitoringState={isLiveActive ? "ACTIVE" : operationMode === "DEMO" ? "ACTIVE" : "STANDBY"}
        gatewayState={isLiveActive ? "CONNECTED" : "STANDBY"}
        lastUpdate={isLiveActive ? "just now" : "live clock"}
        cloudConnected={cloud}
        onToggleCloud={() => setCloud((c) => !c)}
      />

      {/* SECONDARY VIEW / WORKSPACE NAVIGATION */}
      <nav className="viewNav" aria-label="Command Center Views">
        {navTabs.map((tab) => (
          <button
            key={tab.key}
            className={`navTab ${view === tab.key ? "active" : ""}`}
            onClick={() => setView(tab.key)}
          >
            <span>{tab.icon}</span>
            <span>{tab.label}</span>
            {tab.key === "alerts" && activeAlertsCount > 0 && (
              <span className="alertBadgeCount">{activeAlertsCount}</span>
            )}
          </button>
        ))}
      </nav>

      {/* OPERATIONAL WORKSPACE */}
      <main className="workspace">
        {/* 2. COMPACT OPERATIONAL SITUATION SUMMARY */}
        <SituationSummary
          overallState={overall}
          alerts={alerts}
          zones={zones}
          nodes={nodes}
          gatewayStatus="GW-001 (CONNECTED)"
          dataFreshness={isLiveActive ? "< 1.0s (Live LoRa)" : "Synthetic Sync (1.0s)"}
        />

        {/* Live Stream / Deployment Status Notices */}
        {operationMode === "LIVE_MINE" && (
          <div className="streamNotice warning">
            <div>
              <strong>LIVE MINE PROFILE ACTIVE: </strong>
              <span>
                Commercial longwall telemetry interface enabled. Currently operating with local engineering testbed coordinates; no commercial mine stream connected.
              </span>
            </div>
            <span className="badge badge-unavailable">DISCLAIMER: TESTBED MODE ACTIVE</span>
          </div>
        )}

        {operationMode === "LIVE_TESTBED" && (
          <div className="streamNotice">
            <div>
              <strong>LIVE TESTBED STREAM: </strong>
              <span>
                {isLiveActive
                  ? "Continuous hardware stream receiving at /api/ingest · Random Forest inference active."
                  : "Integration boundary READY at POST /api/ingest · Awaiting USB serial LoRa gateway packets."}
              </span>
            </div>
            <span className={`badge ${isLiveActive ? "badge-normal" : "badge-persistent"}`}>
              {isLiveActive ? "HARDWARE STREAMING" : "WAITING FOR GATEWAY"}
            </span>
          </div>
        )}

        {/* 3 & 4. MAIN COMMAND CENTER VIEW (DOMINANT GIS MAP + PERSISTENT OPERATIONAL PANEL) */}
        {view === "command" && (
          <div className="commandSplit">
            {/* Primary GIS Command Map */}
            <GisCommandMap
              stage={effectiveStage}
              mode={scenario}
              layers={layers}
              onToggleLayer={toggleLayer}
              nodes={nodes}
              zones={zones}
              asset={asset}
              selectedEntity={selectedEntity}
              onSelectEntity={setSelectedEntity}
              isLiveActive={isLiveActive}
            />

            {/* Persistent Right-Side Operational Panel */}
            <OperationalPanel
              alerts={alerts}
              currentAlert={currentAlert}
              alertLifecycle={alertLifecycle}
              onAcknowledge={() => setAlertLifecycle("ACKNOWLEDGED")}
              onVerify={() => setAlertLifecycle("VERIFICATION_PENDING")}
              onConfirm={() => setAlertLifecycle("CONFIRMED")}
              onDismiss={(reason) => setAlertLifecycle(reason)}
              overallState={overall}
              selectedEntity={selectedEntity}
              onSelectEntity={setSelectedEntity}
              nodes={nodes}
              zones={zones}
              asset={asset}
              onNavigateView={setView}
            />
          </div>
        )}

        {/* DEDICATED FULL PRIMARY GIS MAP VIEW */}
        {view === "map" && (
          <GisCommandMap
            stage={effectiveStage}
            mode={scenario}
            layers={layers}
            onToggleLayer={toggleLayer}
            nodes={nodes}
            zones={zones}
            asset={asset}
            selectedEntity={selectedEntity}
            onSelectEntity={setSelectedEntity}
            isLiveActive={isLiveActive}
          />
        )}

        {/* 6. SENSOR ANALYTICS */}
        {view === "sensors" && (
          <SensorAnalyticsView nodes={nodes} stage={effectiveStage} />
        )}

        {/* 7. ZONE ANALYTICS */}
        {view === "zones" && (
          <ZoneAnalyticsView zones={zones} />
        )}

        {/* 5. COMPREHENSIVE ALERTS & ACTIONS CENTER */}
        {view === "alerts" && (
          <div className="engPanel">
            <div className="engPanelHeader">
              <div className="engPanelTitle">
                <span>!</span>
                <span>Audit-Friendly Alert &amp; Operational Action Center</span>
              </div>
              <div className="engPanelSub">
                HUMAN-IN-THE-LOOP CONTROL: DETECT → ACKNOWLEDGE → VERIFY → CONFIRM
              </div>
            </div>
            <div className="engPanelBody">
              <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: "12px" }}>
                {/* Active Alerts List */}
                <div>
                  <div style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase", marginBottom: "8px" }}>
                    Active Subsidence Alerts ({alerts.length})
                  </div>
                  {alerts.length > 0 ? (
                    alerts.map((al) => (
                      <div key={al.id} className={`alertOpCard ${al.severity.toLowerCase()}`} style={{ marginBottom: "10px" }}>
                        <div className="alertOpHeader">
                          <div>
                            <span className="alertLocation">WHERE: {al.zoneId}</span>
                            <div className="alertTitle">{al.title}</div>
                          </div>
                          <StateBadge state={overall} />
                        </div>
                        <div className="alertSummaryText">{al.summary}</div>
                        <div className="evidenceSection">
                          <div className="evidenceHeader">Corroborating Evidence:</div>
                          <ul className="evidenceUl">
                            {al.evidence.map((ev, i) => (
                              <li key={i}>• {ev}</li>
                            ))}
                          </ul>
                        </div>
                        <div style={{ display: "flex", gap: "6px", marginTop: "6px" }}>
                          <button className="btnPrimary" onClick={() => setAlertLifecycle("ACKNOWLEDGED")}>
                            Acknowledge
                          </button>
                          <button className="btnOutline" onClick={() => setAlertLifecycle("VERIFICATION_PENDING")}>
                            Mark Verification
                          </button>
                          <button className="btnOutline" onClick={() => setAlertLifecycle("CONFIRMED")}>
                            Confirm
                          </button>
                          <button className="btnDangerOutline" onClick={() => setAlertLifecycle("DISMISSED")}>
                            Dismiss
                          </button>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div style={{ padding: "24px", textAlign: "center", color: "var(--muted)", background: "#f8fafc", border: "1px dashed var(--border)" }}>
                      ✓ No active geotechnical alerts. Sensor baselines nominal.
                    </div>
                  )}
                </div>

                {/* Audit-Friendly Decision Standard (WHERE, WHAT, HOW SERIOUS, WHAT NEXT) */}
                <div style={{ background: "#ffffff", border: "1px solid var(--border)", borderRadius: "3px", padding: "12px" }}>
                  <div style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase", marginBottom: "8px" }}>
                    Operational Decision Standard
                  </div>
                  <div className="semGrid" style={{ marginBottom: "12px" }}>
                    <div className="semItem">
                      <label>WHERE</label>
                      <strong>{currentAlert?.zoneId ?? "—"}</strong>
                    </div>
                    <div className="semItem">
                      <label>WHAT</label>
                      <strong>{currentAlert ? currentAlert.title : "System nominal"}</strong>
                    </div>
                    <div className="semItem">
                      <label>HOW SERIOUS</label>
                      <strong style={{ color: currentAlert?.severity === "CRITICAL" ? "#b91c1c" : "var(--ink)" }}>
                        {currentAlert ? currentAlert.severity : "LOW"}
                      </strong>
                    </div>
                    <div className="semItem">
                      <label>WHAT NEXT</label>
                      <strong style={{ fontSize: "9px" }}>
                        {currentAlert ? currentAlert.recommendedAction : "Continue nominal monitoring"}
                      </strong>
                    </div>
                  </div>
                  <div style={{ fontSize: "9px", color: "var(--muted)", lineHeight: 1.5 }}>
                    <strong>Control Room Protocol:</strong> Operator acknowledgement documents human review and does not alter underlying sensor readings or Random Forest classification results.
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 9. HISTORY / EVENT REPLAY */}
        {view === "history" && (
          <HistoryReplayView
            stage={effectiveStage}
            onStageChange={(s) => {
              setStage(s);
              setAlertLifecycle("NEW");
            }}
            overallState={overall}
            asset={asset}
            nodes={nodes}
            zones={zones}
            alerts={alerts}
          />
        )}

        {/* 10. NETWORK HEALTH */}
        {view === "network" && (
          <NetworkHealthView
            nodes={nodes}
            gatewayStatus="CONNECTED (GW-001)"
            isLiveActive={isLiveActive}
          />
        )}

        {/* PHYSICS INTELLIGENCE MODULE */}
        {view === "physics" && (
          <div style={{ display: "grid", gridTemplateColumns: "1.1fr 0.9fr", gap: "12px" }}>
            <PhysicsIntelPanel
              stage={effectiveStage}
              nodes={nodes}
              zones={zones}
            />
            <div className="engPanel">
              <div className="engPanelHeader">
                <div className="engPanelTitle">
                  <span>⌖</span>
                  <span>Spatial Verification (Knothe PIM vs Sensor Ground Truth)</span>
                </div>
              </div>
              <GisCommandMap
                stage={effectiveStage}
                mode={scenario}
                layers={layers}
                onToggleLayer={toggleLayer}
                nodes={nodes}
                zones={zones}
                asset={asset}
                selectedEntity={selectedEntity}
                onSelectEntity={setSelectedEntity}
                isLiveActive={isLiveActive}
              />
            </div>
          </div>
        )}

        {/* 8. DEMO CONTROLLER */}
        {view === "demo" && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
            <DemoController
              operationMode={operationMode}
              onModeChange={handleModeChange}
              scenario={scenario}
              onScenarioChange={handleScenarioChange}
              stage={stage}
              onStageChange={setStage}
              running={demoRunning}
              onStart={() => setDemoRunning(true)}
              onPause={() => setDemoRunning(false)}
              onReset={handleResetDemo}
              speed={demoSpeed}
              onSpeedChange={setDemoSpeed}
            />

            <div className="engPanel">
              <div className="engPanelHeader">
                <div className="engPanelTitle">
                  <span>▦</span>
                  <span>Synchronized Demo Spatial Preview</span>
                </div>
              </div>
              <GisCommandMap
                stage={stage}
                mode={scenario}
                layers={layers}
                onToggleLayer={toggleLayer}
                nodes={nodes}
                zones={zones}
                asset={asset}
                selectedEntity={selectedEntity}
                onSelectEntity={setSelectedEntity}
                isLiveActive={isLiveActive}
              />
            </div>
          </div>
        )}

        {/* ENGINEERING SETTINGS */}
        {view === "settings" && (
          <div className="engPanel">
            <div className="engPanelHeader">
              <div className="engPanelTitle">
                <span>⚙</span>
                <span>Engineering &amp; Geotechnical Site Configuration</span>
              </div>
              <div className="engPanelSub">
                CALIBRATED LONGWALL PANEL ATTRIBUTES &amp; TARP THRESHOLDS
              </div>
            </div>
            <div className="engPanelBody">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                <table className="networkTable">
                  <tbody>
                    <tr><th>Mine Site</th><td style={{ fontFamily: "var(--font-mono)" }}>Coal Mine Colliery · Panel A</td></tr>
                    <tr><th>Extraction Method</th><td style={{ fontFamily: "var(--font-mono)" }}>Caved Longwall Retreat (Seam H = 110m)</td></tr>
                    <tr><th>Peck Trough Radius (i)</th><td style={{ fontFamily: "var(--font-mono)" }}>44.0 meters (inflection point)</td></tr>
                    <tr><th>Coordinate Datum</th><td style={{ fontFamily: "var(--font-mono)" }}>Local Engineering Metric Grid</td></tr>
                    <tr><th>Protected Infrastructure</th><td style={{ fontFamily: "var(--font-mono)" }}>A-001 (Ventilation Shaft Headframe &amp; Substation)</td></tr>
                  </tbody>
                </table>
                <table className="networkTable">
                  <tbody>
                    <tr><th>Rate Threshold 1 (WATCH)</th><td style={{ fontFamily: "var(--font-mono)" }}>&gt; 0.05 mm/min sustained</td></tr>
                    <tr><th>Rate Threshold 2 (HIGH)</th><td style={{ fontFamily: "var(--font-mono)" }}>&gt; 0.15 mm/min with multi-node agreement</td></tr>
                    <tr><th>Rate Threshold 3 (CRITICAL)</th><td style={{ fontFamily: "var(--font-mono)" }}>&gt; 0.30 mm/min encroaching asset buffer</td></tr>
                    <tr><th>Radio Timeout</th><td style={{ fontFamily: "var(--font-mono)" }}>30 seconds (Watchdog Gap Trigger)</td></tr>
                    <tr><th>False Alarm Guardrail</th><td style={{ fontFamily: "var(--font-mono)" }}>RF v6 Decoy Seismic / Vibration Dissipation</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* SYSTEM FOOTER */}
      <footer className="sysFooter">
        <div>
          MineGuard v1.2 · Industrial Geotechnical Decision Support System · Colliery Engineering Deployment
        </div>
        <div>
          Status: {isLiveActive ? "LIVE TELEMETRY STREAMING" : "CANONICAL MODEL STANDBY"} · Datum: Metric Local
        </div>
      </footer>
    </div>
  );
}
