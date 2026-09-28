"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ASSET,
  GATEWAY,
  SENSOR_LAYOUT,
  stageDescriptions,
  stageLabels,
  alertsFor,
  nodesFor,
  overallState,
  rank,
  timelineFor,
  zonesFor
} from "../lib/demo";
import type { Alert, AlertLifecycle, LayerKey, NodeState, OperationMode, RiskState, ScenarioKey, ViewKey, ZoneState } from "../lib/types";

type LayerState = Record<LayerKey, boolean>;

const nav: { key: ViewKey; label: string; icon: string }[] = [
  { key: "command", label: "Command Center", icon: "▦" },
  { key: "map", label: "Live GIS", icon: "⌖" },
  { key: "zones", label: "Zone Intelligence", icon: "◇" },
  { key: "sensors", label: "Sensor Analytics", icon: "⌁" },
  { key: "alerts", label: "Alerts & Actions", icon: "!" },
  { key: "history", label: "History / Replay", icon: "↺" },
  { key: "network", label: "Network Health", icon: "⌁" },
  { key: "settings", label: "Engineering Settings", icon: "⚙" },
  { key: "demo", label: "Demo Mode", icon: "▶" }
];

const riskColors: Record<RiskState, string> = {
  NORMAL: "#1f7a52",
  LOCAL_ANOMALY: "#9b6b11",
  PERSISTENT: "#9b6b11",
  CORRELATED: "#8c5b14",
  PROGRESSIVE: "#b25b1f",
  HIGH_RISK: "#a63f2b",
  CRITICAL: "#8d2525"
};

function StateBadge({ state }: { state: RiskState }) {
  return <span className={`badge badge-${state.toLowerCase()}`} style={{ color: riskColors[state] }}>{state.replaceAll("_", " ")}</span>;
}

function Confidence({ value }: { value: number }) {
  return <span>{Math.round(value * 100)}%</span>;
}

function LineChart({ values, label, unit }: { values: number[]; label: string; unit: string }) {
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const points = values.map((v, i) => {
    const x = values.length === 1 ? 50 : (i / (values.length - 1)) * 100;
    const y = 94 - ((v - min) / (max - min || 1)) * 78;
    return `${x},${y}`;
  }).join(" ");
  return (
    <div className="chartCard">
      <div className="chartTop"><span>{label}</span><strong>{values[values.length - 1].toFixed(2)} {unit}</strong></div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="chart">
        <line x1="0" x2="100" y1="94" y2="94" stroke="#dbe2e7" strokeWidth="0.8" vectorEffect="non-scaling-stroke" />
        <polyline points={points} fill="none" stroke="#1f5d7a" strokeWidth="2.4" vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  );
}

function MapView({
  stage,
  mode,
  layers,
  onNodeHover,
  selectedNode,
  nodes: customNodes,
  zones: customZones
}: {
  stage: number;
  mode: ScenarioKey;
  layers: LayerState;
  onNodeHover: (id: string | null) => void;
  selectedNode: string | null;
  nodes?: NodeState[];
  zones?: ZoneState[];
}) {
  const zones = customZones || zonesFor(stage, mode);
  const nodes = customNodes || nodesFor(stage, mode);
  const nodePositions: Record<string, { x: number; y: number }> = Object.fromEntries(SENSOR_LAYOUT.map((node) => [node.id, { x: node.x, y: node.y }]));
  const assetState = stage >= 5 && mode === "progressive" ? "AT RISK" : stage >= 4 && mode === "progressive" ? "NEAR IMPACT ZONE" : "NO CURRENT IMPACT";

  return (
    <div className="mapFrame">
      <svg viewBox="0 0 1000 620" className="mapSvg" role="img" aria-label="Mine engineering monitoring map">
        <defs>
          <pattern id="mapGrid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M40 0H0V40" fill="none" stroke="#dde4e8" strokeWidth="1" />
          </pattern>
          <pattern id="fineGrid" width="10" height="10" patternUnits="userSpaceOnUse">
            <path d="M10 0H0V10" fill="none" stroke="#eef2f4" strokeWidth="1" />
          </pattern>
        </defs>
        <rect x="0" y="0" width="1000" height="620" fill="#f7f9fa" />
        {layers.grid && <rect x="18" y="18" width="964" height="584" rx="16" fill="url(#mapGrid)" />}
        <rect x="28" y="28" width="944" height="564" rx="18" fill="none" stroke="#8d9ba5" strokeWidth="2" />
        <rect x="45" y="55" width="910" height="520" fill="url(#fineGrid)" opacity="0.65" />

        <text x="52" y="52" className="mapLabelStrong">PANEL A / SURFACE MONITORING AREA</text>
        <text x="52" y="73" className="mapLabel">LOCAL ENGINEERING COORDINATES · TESTBED GEOMETRY</text>

        <path d="M85 140 H310 M85 140 V330 H310 M310 140 V330 H525 M525 140 V330 H760 M760 140 V410 H905" fill="none" stroke="#60727e" strokeWidth="9" strokeLinecap="round" strokeLinejoin="round" opacity="0.38" />
        <path d="M90 470 C220 395 330 420 455 345 S700 215 900 190" fill="none" stroke="#9aa8b1" strokeWidth="3" strokeDasharray="12 8" />
        <text x="92" y="459" className="mapLabel">PANEL ACCESS / MONITORING CORRIDOR</text>

        <path d="M120 165 C245 116 330 156 430 205 S655 318 790 360" fill="none" stroke="#2f6179" strokeWidth="2.5" strokeDasharray="6 6" />
        <text x="138" y="128" className="mapVectorLabel">ASSESSED DEFORMATION DIRECTION</text>

        {layers.risk && zones.map((z, i) => {
          const x = [95, 350, 625][i];
          const y = [135, 220, 310][i];
          const width = [250, 290, 270][i];
          const height = [150, 175, 185][i];
          const opacity = z.state === "NORMAL" ? 0.04 : Math.min(0.28, 0.08 + rank[z.state] * 0.035);
          return (
            <g key={z.id}>
              <rect x={x} y={y} width={width} height={height} rx="36" fill={riskColors[z.state]} opacity={opacity} stroke={riskColors[z.state]} strokeWidth="2" strokeDasharray="10 6" />
              <text x={x + 18} y={y + 26} className="zoneId">{z.id}</text>
              <text x={x + 18} y={y + 44} className="mapLabel">{z.name}</text>
              {z.state !== "NORMAL" && <text x={x + 18} y={y + 64} className="zoneState">{z.state.replaceAll("_", " ")}</text>}
            </g>
          );
        })}

        {layers.network && (
          <path d="M850 88 L180 174 M850 88 L480 255 M850 88 L760 360" stroke="#8a9aa4" strokeWidth="1.8" strokeDasharray="5 6" opacity="0.9" />
        )}

        {layers.impact && stage >= 4 && mode === "progressive" && (
          <path d="M205 175 C350 198 540 255 798 372" fill="none" stroke="#b25b1f" strokeWidth="4" strokeDasharray="11 9" />
        )}

        {layers.impact && stage >= 5 && mode === "progressive" && (
          <ellipse cx="842" cy="430" rx="106" ry="68" fill="#8d2525" opacity="0.12" stroke="#8d2525" strokeWidth="2" strokeDasharray="8 7" />
        )}

        {layers.assets && (
          <g>
            <circle cx="840" cy="430" r="22" fill="#ffffff" stroke="#40515c" strokeWidth="2" />
            <path d="M828 434 L840 422 L852 434 V446 H828 Z" fill="none" stroke="#40515c" strokeWidth="2" />
            <text x="871" y="426" className="mapLabelStrong">A-001</text>
            <text x="871" y="444" className={assetState === "AT RISK" ? "assetRisk" : "mapLabel"}>{assetState}</text>
          </g>
        )}

        {layers.network && (
          <g>
            <rect x="825" y="48" width="72" height="44" rx="10" fill="#ffffff" stroke="#40515c" strokeWidth="2" />
            <path d="M842 72 h38 M842 64 h38 M854 56 v25" stroke="#2f6179" strokeWidth="2" />
            <text x="905" y="57" className="mapLabelStrong">GW-001</text>
            <text x="905" y="74" className="mapLabel">Gateway</text>
          </g>
        )}

        {layers.sensors && nodes.map((node) => {
          const pos = nodePositions[node.id];
          const active = selectedNode === node.id;
          return (
            <g
              key={node.id}
              role="button"
              tabIndex={0}
              onMouseEnter={() => onNodeHover(node.id)}
              onMouseLeave={() => onNodeHover(null)}
              onFocus={() => onNodeHover(node.id)}
              onBlur={() => onNodeHover(null)}
              className="sensorMarker"
            >
              <circle cx={`${pos.x}%`} cy={`${pos.y}%`} r={active ? 18 : 15} fill="#ffffff" stroke="#1f5d7a" strokeWidth={active ? 4 : 3} />
              <circle cx={`${pos.x}%`} cy={`${pos.y}%`} r="6" fill={node.healthy ? "#1f7a52" : "#8d2525"} />
              <text x={`${pos.x + 2}%`} y={`${pos.y - 3}%`} className="nodeText">{node.id}</text>
            </g>
          );
        })}

        <text x="52" y="552" className="mapLabel">North ↑</text>
        <line x1="94" y1="550" x2="94" y2="515" stroke="#40515c" strokeWidth="2" />
        <polygon points="94,508 88,520 100,520" fill="#40515c" />
      </svg>
    </div>
  );
}

function NodePopover({ nodeId, stage, mode, nodes: customNodes }: { nodeId: string; stage: number; mode: ScenarioKey; nodes?: NodeState[] }) {
  const node = (customNodes || nodesFor(stage, mode)).find((item) => item.id === nodeId);
  if (!node) return null;
  return (
    <div className="nodePopover">
      <div className="popoverHeader"><div><span className="eyebrow">SURFACE SENSOR NODE</span><strong>{node.id}</strong></div><span className="healthPill"><span className={`dot ${node.healthy ? "green" : "red"}`}/> {node.healthy ? "HEALTHY" : "CHECK NODE"}</span></div>
      {node.healthMessage && !node.healthy && (
        <div style={{ fontSize: "11px", color: "#a63f2b", marginTop: "4px", padding: "4px 8px", background: "#fdf0ed", borderRadius: "4px" }}>
          ⚠️ {node.healthMessage}
        </div>
      )}
      <div className="popoverGrid">
        <Metric label="Current tilt" value={`${node.tilt.toFixed(2)}°`} />
        <Metric label="Displacement" value={`${node.displacement.toFixed(2)} mm`} />
        <Metric label="Deformation rate" value={`${node.deformationRate.toFixed(2)} mm/min`} />
        <Metric label="Vibration" value={`${node.vibration.toFixed(2)} g`} />
        <Metric label="Battery" value={`${node.battery}%`} />
        <Metric label="RSSI" value={`${node.rssi} dBm`} />
      </div>
      <div className="modelStrip"><span>Model class</span><strong>{node.modelClass.replaceAll("_", " ")}</strong><span>Confidence <Confidence value={node.modelConfidence} /></span></div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

export default function Home() {
  const [view, setView] = useState<ViewKey>("command");
  const [operationMode, setOperationMode] = useState<OperationMode>("DEMO");
  const [stage, setStage] = useState(0);
  const [scenario, setScenario] = useState<ScenarioKey>("progressive");
  const [demoRunning, setDemoRunning] = useState(false);
  const [demoSpeed, setDemoSpeed] = useState<1 | 2 | 4>(1);
  const [alertLifecycle, setAlertLifecycle] = useState<AlertLifecycle>("NEW");
  const [cloud, setCloud] = useState(true);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [layers, setLayers] = useState<LayerState>({ grid: true, sensors: true, risk: true, assets: true, impact: true, network: true });

  const [liveData, setLiveData] = useState<any>(null);

  // Poll live backend state from /api/state
  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch("/api/state?mode=" + operationMode, { cache: "no-store" });
        if (res.ok) {
          const data = await res.json();
          setLiveData(data);
        }
      } catch {
        // offline / network handling
      }
    };
    poll();
    const interval = setInterval(poll, 1000);
    return () => clearInterval(interval);
  }, [operationMode]);

  const isLiveActive = operationMode !== "DEMO" && Boolean(liveData?.is_live);

  const zones: ZoneState[] = useMemo(() => {
    if (isLiveActive && liveData?.zones) return liveData.zones as ZoneState[];
    return zonesFor(stage, scenario);
  }, [stage, scenario, isLiveActive, liveData]);

  const nodes: NodeState[] = useMemo(() => {
    if (isLiveActive && liveData?.nodes) return liveData.nodes as NodeState[];
    return nodesFor(stage, scenario);
  }, [stage, scenario, isLiveActive, liveData]);

  const alerts: Alert[] = useMemo(() => {
    if (isLiveActive && liveData?.alerts) return liveData.alerts as Alert[];
    return alertsFor(zones, stage, scenario);
  }, [zones, stage, scenario, isLiveActive, liveData]);

  const effectiveStage = useMemo(() => {
    if (isLiveActive && typeof liveData?.stage === "number") return liveData.stage;
    return stage;
  }, [stage, isLiveActive, liveData]);

  const timeline = useMemo(() => timelineFor(effectiveStage), [effectiveStage]);
  const overall = useMemo(() => {
    if (isLiveActive && liveData?.overall_state) return liveData.overall_state as RiskState;
    return overallState(zones);
  }, [zones, isLiveActive, liveData]);
  const currentAlert = alerts[0];
  const effectiveAlertLifecycle = currentAlert ? alertLifecycle : "NEW";
  const overallConfidence = overall === "NORMAL" ? "HIGH" : effectiveStage >= 3 ? "HIGH" : "MEDIUM";
  const viewTitle = nav.find((item) => item.key === view)?.label ?? "Command Center";
  const reportingNodes = nodes.filter((node: any) => node.quality !== "UNAVAILABLE").length;

  useEffect(() => {
    if (!demoRunning || operationMode !== "DEMO") return;
    const timer = window.setInterval(() => {
      setStage((current) => {
        if (current >= 5) {
          setDemoRunning(false);
          return current;
        }
        return current + 1;
      });
    }, 8000 / demoSpeed);
    return () => window.clearInterval(timer);
  }, [demoRunning, demoSpeed, operationMode]);

  function chooseScenario(next: ScenarioKey) {
    setScenario(next);
    setStage(next === "normal" ? 0 : 1);
    setAlertLifecycle("NEW");
    setDemoRunning(false);
  }

  function resetDemo() {
    setStage(0);
    setScenario("progressive");
    setAlertLifecycle("NEW");
    setDemoRunning(false);
    setCloud(true);
  }

  function acknowledge() { setAlertLifecycle("ACKNOWLEDGED"); }
  function verify() { setAlertLifecycle("VERIFICATION_PENDING"); }
  function confirmAlert() { setAlertLifecycle("CONFIRMED"); }
  function dismiss(reason: "DISMISSED" | "SENSOR_ISSUE") { setAlertLifecycle(reason); }

  function toggleLayer(key: LayerKey) {
    setLayers((current) => ({ ...current, [key]: !current[key] }));
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brandBlock">
          <div className="brandMark">MG</div>
          <div><div className="brand">MineGuard</div><div className="brandSub">MINE SUBSIDENCE CONTROL</div></div>
        </div>
        <div className="sideLabel">OPERATIONS</div>
        {nav.map((item) => (
          <button key={item.key} className={`nav ${view === item.key ? "active" : ""}`} onClick={() => setView(item.key)}>
            <span>{item.icon}</span>{item.label}{item.key === "alerts" && alerts.length > 0 && effectiveAlertLifecycle !== "DISMISSED" && effectiveAlertLifecycle !== "SENSOR_ISSUE" ? <em>1</em> : null}
          </button>
        ))}
        <div className="spacer" />
        <div className="sidebarStatus">
          <div className="sideLabel">LOCAL MONITORING</div>
          <div className="statusLine"><span className="dot green" /> ACTIVE</div>
          <div className="muted small">Gateway path ready · {reportingNodes}/3 nodes reporting</div>
          <div className="muted small">Cloud {cloud ? "connected" : "offline · buffering locally"}</div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <div className="eyebrow">COAL MINE · PANEL A · TESTBED DEPLOYMENT</div>
            <h1>{viewTitle}</h1>
          </div>
          <div className="topControls">
            <div className="modeSwitcher">
              {(["DEMO", "LIVE_TESTBED", "LIVE_MINE"] as OperationMode[]).map((mode) => (
                <button key={mode} className={operationMode === mode ? "modeActive" : ""} onClick={() => { setOperationMode(mode); if (mode !== "DEMO") setDemoRunning(false); }}>
                  {mode === "DEMO" ? "Demo" : mode === "LIVE_TESTBED" ? "Live Testbed" : "Live Mine"}
                </button>
              ))}
            </div>
            <div className="statusPill"><span className="dot green"/> LOCAL ACTIVE</div>
            <button className="statusPill clickable" onClick={() => setCloud((current) => !current)}><span className={`dot ${cloud ? "green" : "amber"}`}/> CLOUD {cloud ? "CONNECTED" : "OFFLINE"}</button>
          </div>
        </header>

        {operationMode !== "DEMO" && (
          <div className="modeNotice">
            <div><strong>{operationMode === "LIVE_TESTBED" ? "Live Testbed Mode" : "Live Mine Mode"}</strong><span>{operationMode === "LIVE_TESTBED" ? "Physical node stream is expected at POST /api/ingest. No manual demo stage controls are shown." : "Scalable deployment profile. MineGuard uses the same data model; live field geometry and sensor streams are supplied by integration services."}</span></div>
            <span className="integrationBadge">{isLiveActive ? "● LIVE TELEMETRY STREAMING" : "INTEGRATION READY · WAITING FOR HARDWARE STREAM"}</span>
          </div>
        )}

        <section className="kpis">
          <div className="kpi"><span className="kpiLabel">Overall operational state</span><strong><StateBadge state={overall}/></strong><span className="kpiMeta">Highest assessed zone state</span></div>
          <div className="kpi"><span className="kpiLabel">Open alerts</span><strong>{alerts.length && !["DISMISSED", "SENSOR_ISSUE", "CONFIRMED"].includes(effectiveAlertLifecycle) ? alerts.length : 0}</strong><span className="kpiMeta">Human-in-the-loop lifecycle</span></div>
          <div className="kpi"><span className="kpiLabel">Sensor network</span><strong>{reportingNodes} / {nodes.length}</strong><span className="kpiMeta">Reporting nodes</span></div>
          <div className="kpi"><span className="kpiLabel">Evidence confidence</span><strong>{overallConfidence}</strong><span className="kpiMeta">Data quality + corroboration</span></div>
          <div className="kpi"><span className="kpiLabel">Data source</span><strong>{isLiveActive ? "LIVE HARDWARE" : operationMode === "DEMO" ? "SIMULATED" : "INTEGRATION READY"}</strong><span className="kpiMeta">Same logical dashboard model</span></div>
        </section>

        {view === "command" && (
          <div className="grid2">
            <section className="panel">
              <PanelHead title="Live deformation map" subtitle="Engineering-style spatial view for sensors, deformation zones, assets and assessed impact." action={<StateBadge state={overall}/>}/>
              <MapView stage={effectiveStage} mode={scenario} layers={layers} onNodeHover={setHoveredNode} selectedNode={hoveredNode} nodes={nodes} zones={zones}/>
              {hoveredNode && <NodePopover nodeId={hoveredNode} stage={effectiveStage} mode={scenario} nodes={nodes}/>} 
              <LayerBar layers={layers} toggleLayer={toggleLayer}/>
            </section>
            <div className="stack">
              <section className="panel important">
                <PanelHead title="Most important now" subtitle="Operational decision support" />
                {currentAlert && !["DISMISSED", "SENSOR_ISSUE"].includes(effectiveAlertLifecycle) ? (
                  <>
                    <div className="alertTitleRow"><span className={`severityDot severity-${currentAlert.severity.toLowerCase()}`}/><h2>{currentAlert.title}</h2></div>
                    <div className="answerGrid">
                      <div><span>WHERE</span><strong>{currentAlert.zoneId}</strong></div>
                      <div><span>WHAT</span><strong>{currentAlert.severity === "WATCH" ? "Local anomaly" : "Progressive deformation"}</strong></div>
                      <div><span>HOW SERIOUS</span><strong>{overall.replaceAll("_", " ")}</strong></div>
                      <div><span>WHAT NEXT</span><strong>{currentAlert.recommendedAction}</strong></div>
                    </div>
                    <div className="evidenceList">{currentAlert.evidence.map((item: string) => <div className="evidence" key={item}>✓ {item}</div>)}</div>
                    <div className="importantMeta">Created {currentAlert.created} · Confidence {currentAlert.confidence} · Lifecycle {effectiveAlertLifecycle.replaceAll("_", " ")}</div>
                    <div className="actions">
                      <button className="primary" onClick={acknowledge}>Acknowledge</button>
                      <button className="ghost" onClick={verify}>Mark for verification</button>
                      <button className="ghost dangerGhost" onClick={() => dismiss("SENSOR_ISSUE")}>Sensor issue</button>
                    </div>
                  </>
                ) : (
                  <div className="resolvedState">
                    <div className="resolvedIcon">✓</div>
                    <div><strong>{overall === "NORMAL" ? "System operating within baseline" : effectiveAlertLifecycle === "CONFIRMED" ? "Alert confirmed by operator" : "Alert cleared from active queue"}</strong><p>{overall === "NORMAL" ? "Continue continuous monitoring. No material deformation evidence is currently assessed." : "The event remains in the audit trail. Review history for the full progression."}</p></div>
                  </div>
                )}
              </section>
              {operationMode === "DEMO" ? <section className="panel"><DemoControl stage={stage} scenario={scenario} running={demoRunning} speed={demoSpeed} onScenario={chooseScenario} onStart={() => setDemoRunning(true)} onPause={() => setDemoRunning(false)} onReset={resetDemo} onSpeed={setDemoSpeed}/></section> : <LiveIntegrationCard mode={operationMode}/>} 
            </div>
          </div>
        )}

        {view === "map" && (
          <section className="panel full">
            <PanelHead title="Live GIS" subtitle="The prototype uses a local engineering coordinate system so the same layers can later bind to mine GIS geometry." />
            <MapView stage={effectiveStage} mode={scenario} layers={layers} onNodeHover={setHoveredNode} selectedNode={hoveredNode} nodes={nodes} zones={zones}/>
            {hoveredNode && <NodePopover nodeId={hoveredNode} stage={effectiveStage} mode={scenario} nodes={nodes}/>} 
            <LayerBar layers={layers} toggleLayer={toggleLayer}/>
          </section>
        )}

        {view === "zones" && (
          <section className="panel full"><PanelHead title="Zone intelligence" subtitle="State is assessed from deformation evidence, temporal progression, spatial corroboration, confidence and asset context." />
            <div className="zoneGrid">{zones.map((zone) => <section className="zoneCard" key={zone.id}>
              <div className="zoneHead"><div><span className="eyebrow">MONITORING ZONE</span><h2>{zone.id}</h2><p>{zone.name}</p></div><StateBadge state={zone.state}/></div>
              <div className="metricGrid"><Metric label="Trend" value={zone.trend}/><Metric label="Direction" value={zone.direction}/><Metric label="Confidence" value={zone.confidence}/><Metric label="Asset distance" value={`${zone.assetDistanceM} m`}/></div>
              <div className="evidenceList">{zone.evidence.map((item) => <div className="evidence" key={item}>• {item}</div>)}</div>
              <div className="actions"><button className="ghost" onClick={() => setView("sensors")}>View sensor data</button><button className="ghost" onClick={() => setView("alerts")}>View actions</button></div>
            </section>)}</div>
          </section>
        )}

        {view === "sensors" && (
          <section className="grid2">
            <section className="panel"><PanelHead title="Sensor Analytics" subtitle="Trend charts show current demonstration values; ground-risk state remains separate from sensor health." />
              <div className="chartGrid">
                <LineChart label="Relative displacement" unit="mm" values={[0.4, 0.8, 1.5, 2.7, 4.4, 6.2].map((v, i) => v + stage * 0.12 * i)} />
                <LineChart label="Deformation rate" unit="mm/min" values={[0.02, 0.05, 0.08, 0.14, 0.22, 0.34].map((v, i) => v + stage * 0.01 * i)} />
                <LineChart label="Tilt" unit="deg" values={[0.03, 0.08, 0.14, 0.22, 0.34, 0.48].map((v, i) => v + stage * 0.04 * i)} />
              </div>
            </section>
            <section className="panel"><PanelHead title="Node status" subtitle="Current packet health and model output." />{nodes.map((node: any) => <div className="nodeRow" key={node.id}>
              <div><strong>{node.id}</strong><span className="muted small">{node.zoneId} · last seen {node.lastSeen}</span></div><div>tilt {node.tilt.toFixed(2)}°</div><div>disp {node.displacement.toFixed(2)} mm</div><div>rate {node.deformationRate.toFixed(2)} mm/min</div>
              <div><span className={`dot ${node.healthy ? "green" : "red"}`}/> {node.modelClass.replaceAll("_", " ")}</div>
              {node.healthMessage && !node.healthy && <div style={{ gridColumn: "1 / -1", fontSize: "11px", color: "#a63f2b", background: "#fdf0ed", padding: "4px 8px", borderRadius: "4px", marginTop: "4px" }}>⚠️ {node.healthMessage}</div>}
            </div>)}</section>
          </section>
        )}

        {view === "alerts" && (
          <section className="grid2">
            <section className="panel"><PanelHead title="Alert & Action Center" subtitle="Detect → acknowledge → verify → confirm or dismiss. Human review remains explicit." />
              {currentAlert ? <div className="alertCard">
                <div className="alertTop"><div><span className={`severityChip ${currentAlert.severity.toLowerCase()}`}>{currentAlert.severity}</span><span className="quiet"> {currentAlert.id}</span></div><StateBadge state={overall}/></div>
                <h2>{currentAlert.title}</h2><p>{currentAlert.summary}</p>
                <div className="evidenceList">{currentAlert.evidence.map((e: string) => <div className="evidence" key={e}>✓ {e}</div>)}</div>
                <div className="lifecycle"><span className={effectiveAlertLifecycle !== "NEW" ? "done" : "current"}>NEW</span><span className={rankLifecycle(effectiveAlertLifecycle) >= 1 ? "done" : ""}>ACKNOWLEDGED</span><span className={effectiveAlertLifecycle === "VERIFICATION_PENDING" ? "current" : rankLifecycle(effectiveAlertLifecycle) > 2 ? "done" : ""}>VERIFICATION PENDING</span><span className={effectiveAlertLifecycle === "CONFIRMED" ? "current" : ""}>CONFIRMED</span><span className={effectiveAlertLifecycle === "DISMISSED" ? "current dismissed" : effectiveAlertLifecycle === "SENSOR_ISSUE" ? "current dismissed" : ""}>{effectiveAlertLifecycle === "SENSOR_ISSUE" ? "SENSOR ISSUE" : "DISMISSED"}</span></div>
                <div className="actions"><button className="primary" onClick={acknowledge}>Acknowledge</button><button className="ghost" onClick={verify}>Mark for verification</button><button className="ghost" onClick={confirmAlert}>Confirm</button><button className="ghost dangerGhost" onClick={() => dismiss("DISMISSED")}>Dismiss</button><button className="ghost dangerGhost" onClick={() => dismiss("SENSOR_ISSUE")}>Sensor issue</button></div>
              </div> : <Empty text="No active alerts. Continue monitoring." />}
            </section>
            <section className="panel"><PanelHead title="Audit-friendly answer" subtitle="A serious control-room alert should answer four questions clearly." /><div className="answerGrid large"><div><span>WHERE</span><strong>{currentAlert?.zoneId ?? "—"}</strong></div><div><span>WHAT</span><strong>{currentAlert ? currentAlert.title : "System normal"}</strong></div><div><span>HOW SERIOUS</span><strong>{currentAlert ? overall.replaceAll("_", " ") : "LOW"}</strong></div><div><span>WHAT NEXT</span><strong>{currentAlert ? currentAlert.recommendedAction : "Continue monitoring"}</strong></div></div></section>
          </section>
        )}

        {view === "history" && (
          <section className="panel full"><PanelHead title="History / Event Replay" subtitle="Demo timeline synchronizes map state, zone state, asset context and alerts." action={<span className="quiet">Current run · synthetic observations</span>} />
            <div className="replay"><input type="range" min="0" max="5" value={stage} onChange={(event: { target: { value: string } }) => { setStage(Number(event.target.value)); setAlertLifecycle("NEW"); }}/><div className="replayLabels">{timeline.map((item, index) => <button key={item.minute} className={index === stage ? "replayPoint active" : "replayPoint"} onClick={() => { setStage(index); setAlertLifecycle("NEW"); }}><span>+{item.minute} min</span><strong>{item.state}</strong></button>)}</div></div>
            <div className="historyGrid"><div className="panel inset"><MapView stage={stage} mode={scenario} layers={layers} onNodeHover={setHoveredNode} selectedNode={hoveredNode}/></div><div className="panel inset"><div className="timelineRow"><span>Relative displacement</span><strong>{timeline[stage].displacement} mm</strong></div><div className="timelineRow"><span>Deformation rate</span><strong>{timeline[stage].rate} mm/min</strong></div><div className="timelineRow"><span>Zone state</span><StateBadge state={overall}/></div><div className="timelineRow"><span>Asset context</span><strong>{stage >= 5 ? "AT RISK" : stage >= 4 ? "NEAR IMPACT ZONE" : "NO CURRENT IMPACT"}</strong></div><div className="note">Demo time is compressed. It is not equivalent to real mine elapsed time.</div></div></div>
          </section>
        )}

        {view === "network" && (
          <section className="grid2"><section className="panel"><PanelHead title="Network Health" subtitle="Communication quality is separate from ground-risk state." />{nodes.map((node: any) => <div className="nodeRow" key={node.id}>
            <div><strong>{node.id}</strong><span className="muted small">{node.zoneId}</span></div>
            <div>RSSI {node.rssi} dBm</div>
            <div>battery {node.battery}%</div>
            <div>last seen {node.lastSeen}</div>
            <div><span className={`dot ${node.quality === "UNAVAILABLE" ? "red" : node.quality === "DEGRADED" ? "amber" : "green"}`}/> {node.quality?.toLowerCase() || "good"}</div>
            {node.healthMessage && !node.healthy && (
              <div style={{ gridColumn: "1 / -1", fontSize: "11px", color: "#a63f2b", background: "#fdf0ed", padding: "4px 8px", borderRadius: "4px", marginTop: "4px" }}>⚠️ {node.healthMessage}</div>
            )}
          </div>)}</section><section className="panel"><PanelHead title="System path" subtitle="Data source changes; the logical MineGuard dashboard stays the same." /><div className="flow"><div className="flowNode">Sensor Nodes</div><div>↓</div><div className="flowNode">Wireless Mesh</div><div>↓</div><div className="flowNode">Gateway GW-001</div><div>↓</div><div className="flowNode">MQTT / API</div><div>↓</div><div className="flowNode">ML + Risk Services</div><div>↓</div><div className="flowNode">MineGuard UI</div></div><div className="adapter"><span className={`dot ${isLiveActive ? "green" : "amber"}`}/> {isLiveActive ? "Live hardware stream ACTIVE" : "Integration boundary READY"} <span className="quiet">POST /api/ingest · POST /api/ml</span></div></section></section>
        )}

        {view === "settings" && (
          <section className="grid2"><section className="panel"><PanelHead title="Engineering Settings" subtitle="Prototype configuration. Site thresholds must be validated before field deployment." /><div className="settingsGrid"><label>Deployment profile<input value="Mine Panel A / Testbed" readOnly/></label><label>Coordinate system<input value="Local engineering coordinates" readOnly/></label><label>Sensor IDs<input value="SN-001, SN-002, SN-003" readOnly/></label><label>Gateway<input value="GW-001" readOnly/></label><label>Protected asset<input value="A-001 · placeholder asset" readOnly/></label><label>Risk thresholds<input value="Demo configuration only" readOnly/></label></div></section><section className="panel"><PanelHead title="Integration readiness" subtitle="What can be connected without changing the dashboard architecture." /><div className="contractRow"><span>Hardware packet schema</span><strong>READY</strong></div><div className="contractRow"><span>ML inference adapter</span><strong>READY</strong></div><div className="contractRow"><span>Data-source separation</span><strong>READY</strong></div><div className="contractRow"><span>Alert lifecycle</span><strong>READY</strong></div><div className="contractRow"><span>Local-first UI</span><strong>READY</strong></div><div className="note">This build deliberately avoids claims of calibrated collapse probability or automatic evacuation decisions.</div></section></section>
        )}

        {view === "demo" && (
          <section className="grid2"><section className="panel"><DemoControl stage={stage} scenario={scenario} running={demoRunning} speed={demoSpeed} onScenario={chooseScenario} onStart={() => setDemoRunning(true)} onPause={() => setDemoRunning(false)} onReset={resetDemo} onSpeed={setDemoSpeed}/><div className="demoMap"><MapView stage={stage} mode={scenario} layers={layers} onNodeHover={setHoveredNode} selectedNode={hoveredNode}/></div></section><section className="panel"><PanelHead title="Demo acceptance path" subtitle="The virtual simulator is a data source, not a hardcoded screen animation." /><Check text="Normal baseline is visible before the event begins"/><Check text="Single-node disturbance stays local and requires verification"/><Check text="Persistence changes the state before spatial escalation"/><Check text="Multi-node progression changes zone and asset context"/><Check text="Alert actions are human-controlled and auditable"/><Check text="Reset returns the run to a clean baseline"/><Check text="Live Testbed / Live Mine modes hide manual stage controls"/></section></section>
        )}

        <footer>MineGuard software prototype · decision-support system · synthetic/demo values are not field safety limits.</footer>
      </main>
    </div>
  );
}

function PanelHead({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return <div className="panelHead"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>;
}

function LayerBar({ layers, toggleLayer }: { layers: LayerState; toggleLayer: (key: LayerKey) => void }) {
  const labels: Record<LayerKey, string> = { grid: "Grid", sensors: "Sensors", risk: "Risk", assets: "Assets", impact: "Impact", network: "Network" };
  return <div className="layerBar">{(Object.keys(labels) as LayerKey[]).map((key) => <button key={key} className={layers[key] ? "layerActive" : ""} onClick={() => toggleLayer(key)}>{labels[key]}</button>)}</div>;
}

function DemoControl({ stage, scenario, running, speed, onScenario, onStart, onPause, onReset, onSpeed }: { stage: number; scenario: ScenarioKey; running: boolean; speed: 1 | 2 | 4; onScenario: (scenario: ScenarioKey) => void; onStart: () => void; onPause: () => void; onReset: () => void; onSpeed: (speed: 1 | 2 | 4) => void; }) {
  return <div>
    <PanelHead title="Demo Mode" subtitle="Virtual observations are used to exercise the same dashboard logic without physical hardware." action={<span className="stageChip">Stage {stage}/5</span>} />
    <div className="demoControlGrid">
      <div className="controlGroup"><span className="controlLabel">Scenario</span><div className="segmented">{(["progressive", "false_local", "normal"] as ScenarioKey[]).map((item) => <button key={item} className={scenario === item ? "selected" : ""} onClick={() => onScenario(item)}>{item === "progressive" ? "Progressive" : item === "false_local" ? "False local disturbance" : "Normal"}</button>)}</div></div>
      <div className="controlGroup"><span className="controlLabel">Playback</span><div className="segmented"><button onClick={onStart} disabled={running}>▶ Start</button><button onClick={onPause} disabled={!running}>Ⅱ Pause</button><button onClick={onReset}>↻ Reset</button></div></div>
      <div className="controlGroup"><span className="controlLabel">Speed</span><div className="segmented">{([1, 2, 4] as const).map((item) => <button key={item} className={speed === item ? "selected" : ""} onClick={() => onSpeed(item)}>{item}×</button>)}</div></div>
    </div>
    <div className="progressTrack"><div className="progressFill" style={{ width: `${(stage / 5) * 100}%` }}/></div>
    <div className="stageSummary"><strong>{stageLabels[stage]}</strong><span>{stageDescriptions[stage]}</span></div>
    <p className="note">The run advances one operational stage every 8 seconds at 1× in this prototype. Demo time is compressed and does not represent real mine time.</p>
  </div>;
}

function LiveIntegrationCard({ mode }: { mode: Exclude<OperationMode, "DEMO"> }) {
  return <section className="panel integrationCard"><PanelHead title={mode === "LIVE_TESTBED" ? "Live Testbed Input" : "Live Mine Input"} subtitle="No physical stream is connected in this package; the integration seam is ready."/><div className="integrationSteps"><div><strong>1</strong><span>Sensor packet</span><small>POST /api/ingest</small></div><div><strong>2</strong><span>Validation</span><small>health + quality</small></div><div><strong>3</strong><span>ML adapter</span><small>POST /api/ml</small></div><div><strong>4</strong><span>Risk engine</span><small>spatial + temporal context</small></div></div><div className="offlineBanner"><span className="dot amber"/> Live stream not connected · dashboard remains in integration-ready standby.</div></section>;
}

function Check({ text }: { text: string }) { return <div className="check"><span>✓</span>{text}</div>; }
function Empty({ text }: { text: string }) { return <div className="empty">{text}</div>; }

function rankLifecycle(lifecycle: AlertLifecycle): number {
  if (lifecycle === "NEW") return 0;
  if (lifecycle === "ACKNOWLEDGED") return 1;
  if (lifecycle === "VERIFICATION_PENDING") return 2;
  if (lifecycle === "CONFIRMED") return 3;
  return 4;
}
