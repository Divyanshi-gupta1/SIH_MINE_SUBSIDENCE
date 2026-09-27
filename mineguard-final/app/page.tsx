"use client";

import { useEffect, useMemo, useState } from "react";
import { alertsFor, nodesFor, rank, stageLabels, timelineFor, zonesFor } from "../lib/demo";
import type { AlertLifecycle, RiskState, ViewKey } from "../lib/types";

const nav: { key: ViewKey; label: string; icon: string }[] = [
  { key: "command", label: "Command Center", icon: "⌁" },
  { key: "map", label: "Live GIS", icon: "⌖" },
  { key: "zones", label: "Zone Intelligence", icon: "◈" },
  { key: "sensors", label: "Sensor Analytics", icon: "◌" },
  { key: "alerts", label: "Alerts & Actions", icon: "!" },
  { key: "history", label: "History", icon: "↺" },
  { key: "network", label: "Network Health", icon: "⌁" },
  { key: "settings", label: "Settings", icon: "⚙" }
];

const colors: Record<string, string> = { NORMAL: "#41c889", LOCAL_ANOMALY: "#e8bf51", PERSISTENT: "#e8bf51", CORRELATED: "#e8bf51", PROGRESSIVE: "#e58a49", HIGH_RISK: "#ef655d", CRITICAL: "#ef4f59" };

function StateBadge({ state }: { state: RiskState }) {
  return <span className="badge" style={{ color: colors[state], borderColor: `${colors[state]}55`, background: `${colors[state]}12` }}>{state.replaceAll("_", " ")}</span>;
}

function LineChart({ values, color = "#8ec4ff" }: { values: number[]; color?: string }) {
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const points = values.map((v, i) => `${(i / (values.length - 1)) * 100},${100 - ((v - min) / (max - min || 1)) * 88 - 6}`).join(" ");
  return <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="chart"><polyline points={points} fill="none" stroke={color} strokeWidth="2.3" vectorEffect="non-scaling-stroke" /><line x1="0" x2="100" y1="92" y2="92" stroke="#263545" strokeWidth="0.8" /></svg>;
}

function Map({ stage, mode }: { stage: number; mode: "progressive" | "false_local" | "normal" }) {
  const zones = zonesFor(stage, mode);
  const positions = [[90, 185, 225, 120], [310, 215, 235, 125], [535, 250, 250, 145]];
  return <div className="mapWrap"><svg viewBox="0 0 900 500" className="mapSvg">
    <defs><pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="#21303d" strokeWidth="1" /></pattern></defs>
    <rect x="22" y="22" width="856" height="456" rx="18" fill="#0d141c" stroke="#2a3948" /><rect x="22" y="22" width="856" height="456" rx="18" fill="url(#grid)" opacity=".45" />
    <text x="42" y="52" fill="#8090a0" fontSize="12">TESTBED / MINE PANEL A · ENGINEERING COORDINATES</text>
    <text x="755" y="52" fill="#8090a0" fontSize="12">G1 · GATEWAY</text>
    {zones.map((z, i) => { const [x,y,w,h] = positions[i]; const c = colors[z.state]; return <g key={z.id}>
      <rect x={x} y={y} width={w} height={h} rx="24" fill={`${c}18`} stroke={`${c}70`} strokeWidth="2" />
      <text x={x + 16} y={y + 24} fill="#d7e2ea" fontSize="12">{z.id}</text><text x={x + 16} y={y + 42} fill="#8696a4" fontSize="10">{z.state.replaceAll("_", " ")}</text>
    </g>; })}
    {[{id:"N1",x:145,y:165},{id:"N2",x:405,y:196},{id:"N3",x:670,y:234}].map(n => <g key={n.id}><circle cx={n.x} cy={n.y} r="11" fill="#111a23" stroke="#8ec4ff" strokeWidth="3" /><circle cx={n.x} cy={n.y} r="4" fill="#8ec4ff" /><text x={n.x + 16} y={n.y + 4} fill="#d7e2ea" fontSize="11">{n.id}</text></g>)}
    <circle cx="800" cy="92" r="14" fill="#111a23" stroke="#8ec4ff" strokeWidth="3"/><circle cx="800" cy="92" r="5" fill="#8ec4ff"/>
    {stage >= 4 && <path d="M190 165 C 350 175 520 210 720 320" fill="none" stroke="#e58a49" strokeDasharray="8 6" strokeWidth="2.4" />}
    {stage >= 5 && <ellipse cx="762" cy="324" rx="94" ry="54" fill="#ef655d18" stroke="#ef655d88" strokeDasharray="7 5" />}
    <rect x="758" y="298" width="38" height="38" rx="9" fill="#172430" stroke="#a2b0bc"/><text x="777" y="323" textAnchor="middle" fill="#eff4f7" fontSize="17">⌂</text><text x="805" y="314" fill="#d7e2ea" fontSize="11">A01</text><text x="805" y="329" fill={stage >= 5 ? "#ef655d" : "#82929f"} fontSize="9">{stage >= 5 ? "AT RISK" : "NO CURRENT IMPACT"}</text>
    <text x="60" y="445" fill="#677684" fontSize="10">Layers: sensors · labels · deformation · risk · assets · gateway · vectors · assessed impact · trail</text>
  </svg></div>;
}

export default function Home() {
  const [view, setView] = useState<ViewKey>("command");
  const [stage, setStage] = useState(0);
  const [mode, setMode] = useState<"progressive" | "false_local" | "normal">("progressive");
  const [acked, setAcked] = useState(false);
  const [lifecycle, setLifecycle] = useState<AlertLifecycle>("NEW");
  const [cloud, setCloud] = useState(true);
  const [liveData, setLiveData] = useState<any>(null);
  const [liveActive, setLiveActive] = useState(true);

  // Poll live hardware + ML predictions from /api/state
  useEffect(() => {
    if (!liveActive) return;
    const poll = async () => {
      try {
        const res = await fetch("/api/state", { cache: "no-store" });
        if (res.ok) {
          const json = await res.json();
          setLiveData(json);
        }
      } catch {
        // network / offline handling
      }
    };
    poll();
    const id = setInterval(poll, 1000);
    return () => clearInterval(id);
  }, [liveActive]);

  const zones = useMemo(() => {
    if (liveActive && liveData?.is_live && liveData?.zones) {
      return liveData.zones;
    }
    return zonesFor(stage, mode);
  }, [stage, mode, liveActive, liveData]);

  const nodes = useMemo(() => {
    if (liveActive && liveData?.is_live && liveData?.nodes) {
      return liveData.nodes;
    }
    return nodesFor(stage, mode);
  }, [stage, mode, liveActive, liveData]);

  const alerts = useMemo(() => {
    if (liveActive && liveData?.is_live && liveData?.alerts) {
      return liveData.alerts;
    }
    return alertsFor(zones, stage);
  }, [zones, stage, liveActive, liveData]);

  const effectiveStage = useMemo(() => {
    if (liveActive && liveData?.is_live && typeof liveData?.stage === "number") {
      return liveData.stage;
    }
    return stage;
  }, [stage, liveActive, liveData]);

  const timeline = useMemo(() => timelineFor(effectiveStage), [effectiveStage]);
  const overall = zones.reduce((a, z) => rank[z.state] > rank[a] ? z.state : a, "NORMAL" as RiskState);
  const activeAlert = alerts[0];
  const progressSeries = [0.35, 0.7, 1.3, 2.2, 3.6, 5.8].map((v, i) => v + effectiveStage * 0.15 * i);
  const rateSeries = [0.02, 0.04, 0.08, 0.13, 0.2, 0.3].map((v, i) => v + effectiveStage * 0.01 * i);
  const viewTitle = nav.find((x) => x.key === view)?.label ?? "Command Center";

  function selectScenario(nextMode: typeof mode) { setLiveActive(false); setMode(nextMode); setStage(nextMode === "normal" ? 0 : nextMode === "false_local" ? 2 : Math.max(stage, 1)); setLifecycle("NEW"); setAcked(false); }
  function advance() { setLiveActive(false); setStage((s) => Math.min(5, s + 1)); setLifecycle("NEW"); setAcked(false); }
  function acknowledge() { setAcked(true); setLifecycle("ACKNOWLEDGED"); }
  function verify() { setLifecycle("VERIFICATION_PENDING"); }

  return <div className="shell">
    <aside className="sidebar">
      <div className="brand">MineGuard<div>SUBSIDENCE CONTROL</div></div>
      <div className="sideLabel">OPERATIONS</div>
      {nav.map(n => <button key={n.key} className={`nav ${view === n.key ? "active" : ""}`} onClick={() => setView(n.key)}><span>{n.icon}</span>{n.label}{n.key === "alerts" && alerts.length > 0 ? <em>1</em> : null}</button>)}
      <div className="spacer" />
      <div className="localCard"><div className="sideLabel">LOCAL MONITORING</div><div className="statusLine"><span className="dot green" />ACTIVE</div><div className="muted">Cloud {cloud ? "connected" : "offline"}</div></div>
    </aside>

    <main className="main">
      <header className="topbar"><div><div className="eyebrow">Mine Panel A · Testbed deployment</div><h1>{viewTitle}</h1></div><div className="topPills"><button className={`pill buttonPill`} onClick={() => setLiveActive(l => !l)}><span className={`dot ${liveData?.is_live ? "green" : "orange"}`}/> {liveData?.is_live ? (liveActive ? "LIVE HARDWARE STREAM" : "STREAM PAUSED") : "LIVE STREAM WAITING"}</button><span className="pill"><span className="dot green"/> LOCAL ACTIVE</span><button className="pill buttonPill" onClick={() => setCloud((c) => !c)}><span className={`dot ${cloud ? "green" : "red"}`}/> CLOUD {cloud ? "CONNECTED" : "OFFLINE"}</button></div></header>

      <section className="kpis">
        <div className="kpi"><span className="kpiLabel">Overall state</span><strong><StateBadge state={overall}/></strong><span className="kpiMeta">Highest assessed zone state</span></div>
        <div className="kpi"><span className="kpiLabel">Active alerts</span><strong>{alerts.length && !acked ? alerts.length : 0}</strong><span className="kpiMeta">{acked ? "Operator acknowledged" : "Awaiting action"}</span></div>
        <div className="kpi"><span className="kpiLabel">Sensor network</span><strong>3 / 3</strong><span className="kpiMeta">Reporting nodes</span></div>
        <div className="kpi"><span className="kpiLabel">Evidence confidence</span><strong>{overall === "NORMAL" ? "HIGH" : stage >= 3 ? "HIGH" : "MEDIUM"}</strong><span className="kpiMeta">Data quality + corroboration</span></div>
        <div className="kpi"><span className="kpiLabel">Cloud sync</span><strong>{cloud ? "CONNECTED" : "BUFFERING"}</strong><span className="kpiMeta">{cloud ? "Up to date" : "Local-first mode"}</span></div>
      </section>

      {view === "command" && <div className="grid2"><section className="panel"><div className="panelHead"><div><h2>Live deformation map</h2><p>One shared spatial model for sensors, zones, assets and assessed impact.</p></div><StateBadge state={overall}/></div><Map stage={stage} mode={mode}/></section><div className="stack"><section className="panel important"><div className="panelHead"><h2>Most important now</h2><span className="quiet">Decision support</span></div>{activeAlert && !acked ? <><h3>{activeAlert.title}</h3><p className="lead">{activeAlert.summary}</p><div className="evidenceList">{activeAlert.evidence.map((e) => <div className="evidence" key={e}>✓ {e}</div>)}</div><div className="importantMeta">Confidence {activeAlert.confidence} · Asset context {stage >= 5 ? "AT RISK" : "NEAR IMPACT ZONE"}</div><div className="actions"><button className="primary" onClick={acknowledge}>Acknowledge</button><button className="ghost" onClick={() => setView("zones")}>Open zone</button></div></> : <><h3>{overall === "NORMAL" ? "System normal" : acked ? "Alert acknowledged" : "Local observation"}</h3><p className="lead">{overall === "NORMAL" ? "No significant deformation evidence detected." : "Operator workflow is active; inspect the affected zone and evidence before verification."}</p><div className="actions"><button className="primary" onClick={() => setView("map")}>Open live map</button></div></>}</section><section className="panel"><ScenarioPanel stage={stage} mode={mode} setStage={setStage} selectScenario={selectScenario} advance={advance}/></section></div></div>}

      {view === "map" && <section className="panel full"><div className="panelHead"><div><h2>Live GIS</h2><p>Prototype engineering coordinate system. Real mine geometry plugs into the same layer model.</p></div><div className="row"><span className="chip activeChip">Sensors</span><span className="chip activeChip">Risk</span><span className="chip activeChip">Assets</span><span className="chip activeChip">Impact</span></div></div><Map stage={stage} mode={mode}/><div className="mapLegend"><div><span className="dot blue"/> Sensor/gateway</div><div><span className="dot orange"/> Progression</div><div><span className="dot red"/> Assessed impact</div><div><span className="dot gray"/> Asset</div></div></section>}

      {view === "zones" && <section className="grid3">{zones.map(z => <section key={z.id} className="panel zonePanel"><div className="panelHead"><div><h2>{z.id}</h2><p>{z.name}</p></div><StateBadge state={z.state}/></div><div className="metric"><span>Trend</span><strong>{z.trend}</strong></div><div className="metric"><span>Direction</span><strong>{z.direction}</strong></div><div className="metric"><span>Confidence</span><strong>{z.confidence}</strong></div><div className="metric"><span>Asset context</span><strong>{z.assetDistanceM} m</strong></div><div className="evidenceList">{z.evidence.map(e => <div className="evidence" key={e}>• {e}</div>)}</div><div className="actions"><button className="ghost" onClick={() => setView("sensors")}>Sensor data</button><button className="ghost" onClick={() => setView("alerts")}>Actions</button></div></section>)}</section>}

      {view === "sensors" && <section className="grid2"><section className="panel"><div className="panelHead"><div><h2>Sensor Analytics</h2><p>Ground-risk state is separate from sensor health.</p></div><span className="quiet">3 nodes</span></div><div className="chartGrid"><div className="chartCard"><div className="chartTop"><span>Relative displacement</span><strong>{nodes[1].displacement} mm</strong></div><LineChart values={progressSeries}/></div><div className="chartCard"><div className="chartTop"><span>Deformation rate</span><strong>{rateSeries[stage].toFixed(2)} mm/min</strong></div><LineChart values={rateSeries} color="#e58a49"/></div><div className="chartCard"><div className="chartTop"><span>Tilt deviation</span><strong>{nodes[1].tilt}°</strong></div><LineChart values={nodes.map(n => n.tilt + 0.05)}/></div></div></section><section className="panel"><div className="panelHead"><div><h2>Node status</h2><p>Current packet health and measurements.</p></div></div>{nodes.map(n => <div className="nodeRow" key={n.id}><div><strong>{n.id}</strong><span className="muted">last seen {n.lastSeen}</span></div><div>tilt {n.tilt}°</div><div>disp {n.displacement} mm</div><div>battery {n.battery}%</div><div className="health"><span className="dot green"/> healthy</div></div>)}</section></section>}

      {view === "alerts" && <section className="grid2"><section className="panel"><div className="panelHead"><div><h2>Alert & Action Center</h2><p>Human-in-the-loop lifecycle: detect → acknowledge → verify.</p></div></div>{alerts.length ? <div className="alertCard"><div className="alertTop"><StateBadge state={overall}/><span className="quiet">{activeAlert?.id}</span></div><h3>{activeAlert?.title}</h3><p>{activeAlert?.summary}</p><div className="evidenceList">{activeAlert?.evidence.map(e => <div className="evidence" key={e}>✓ {e}</div>)}</div><div className="lifecycle"><span className={lifecycle === "NEW" ? "current" : "done"}>NEW</span><span className={lifecycle !== "NEW" ? "done" : ""}>ACKNOWLEDGED</span><span className={lifecycle === "VERIFICATION_PENDING" ? "current" : lifecycle === "CONFIRMED" ? "done" : ""}>VERIFICATION PENDING</span><span className={lifecycle === "CONFIRMED" ? "current" : ""}>CONFIRMED</span></div><div className="actions"><button className="primary" onClick={acknowledge}>Acknowledge</button><button className="ghost" onClick={verify}>Mark for verification</button><button className="ghost" onClick={() => setLifecycle("CONFIRMED")}>Confirm</button></div></div> : <Empty text="No active alerts."/>}</section><section className="panel"><h2>Required answer</h2><div className="answerGrid"><div><span>WHERE</span><strong>{alerts.length ? activeAlert?.zoneId : "—"}</strong></div><div><span>WHAT</span><strong>{alerts.length ? "Progressive deformation" : "Normal"}</strong></div><div><span>HOW SERIOUS</span><strong>{alerts.length ? overall.replaceAll("_", " ") : "LOW"}</strong></div><div><span>WHAT NEXT</span><strong>{alerts.length ? "Inspect + verify" : "Continue monitoring"}</strong></div></div></section></section>}

      {view === "history" && <section className="panel full"><div className="panelHead"><div><h2>History / Event Replay</h2><p>Demo timeline synchronizes map state, zone state, asset context and alerts.</p></div><span className="quiet">Current run · synthetic observations</span></div><div className="replay"><input type="range" min="0" max="5" value={stage} onChange={(e) => setStage(Number(e.target.value))}/><div className="replayLabels">{timeline.map((t, i) => <button key={t.minute} className={i === stage ? "replayPoint active" : "replayPoint"} onClick={() => setStage(i)}><span>+{t.minute}m</span><strong>{t.state}</strong></button>)}</div></div><div className="historyGrid"><div className="panel inner"><Map stage={stage} mode={mode}/></div><div className="panel inner"><div className="timelineRow"><span>Relative displacement</span><strong>{timeline[stage].displacement} mm</strong></div><div className="timelineRow"><span>Deformation rate</span><strong>{timeline[stage].rate} mm/min</strong></div><div className="timelineRow"><span>Zone state</span><StateBadge state={overall}/></div><div className="timelineRow"><span>Asset state</span><strong>{stage >= 5 ? "AT RISK" : stage >= 4 ? "NEAR IMPACT ZONE" : "NO CURRENT IMPACT"}</strong></div></div></div></section>}

      {view === "network" && <section className="grid2"><section className="panel"><div className="panelHead"><div><h2>Network Health</h2><p>Communication confidence is separate from ground risk.</p></div></div>{nodes.map(n => <div className="nodeRow" key={n.id}><div><strong>{n.id}</strong><span className="muted">last seen {n.lastSeen}</span></div><div>RSSI {n.rssi} dBm</div><div>battery {n.battery}%</div><div className="health"><span className="dot green"/> reporting</div></div>)}</section><section className="panel"><div className="panelHead"><div><h2>System path</h2><p>Local-first operational flow.</p></div></div><div className="flow"><div>Sensor Nodes</div><div>↓</div><div>Wireless Mesh</div><div>↓</div><div>Gateway G1</div><div>↓</div><div>MQTT / API</div><div>↓</div><div>Risk + ML adapters</div><div>↓</div><div>MineGuard UI</div></div><div className="adapter"><span className="dot green"/> ML adapter READY <span className="quiet">POST /api/ml</span></div></section></section>}

      {view === "settings" && <section className="grid2"><section className="panel"><div className="panelHead"><div><h2>Engineering Settings</h2><p>Prototype configuration; field thresholds require site validation.</p></div></div><div className="settingsGrid"><label>Deployment profile<input value="Mine Panel A / Testbed" readOnly/></label><label>Coordinate system<input value="Local engineering coordinates" readOnly/></label><label>Sensor nodes<input value="N1, N2, N3" readOnly/></label><label>Gateway<input value="G1" readOnly/></label><label>Protected asset<input value="A01 · School / House placeholder" readOnly/></label><label>Risk thresholds<input value="Demo configuration" readOnly/></label></div></section><section className="panel"><div className="panelHead"><div><h2>Integration status</h2><p>Interfaces ready for hardware and ML teams.</p></div></div><div className="contractRow"><span>Hardware packet schema</span><strong>READY</strong></div><div className="contractRow"><span>ML inference adapter</span><strong>READY</strong></div><div className="contractRow"><span>Historical replay model</span><strong>READY</strong></div><div className="contractRow"><span>Local/offline mode</span><strong>READY</strong></div><div className="note">Do not treat prototype labels as calibrated field safety limits or exact collapse probabilities.</div></section></section>}

      {view === "demo" && <section className="grid2"><section className="panel"><ScenarioPanel stage={stage} mode={mode} setStage={setStage} selectScenario={selectScenario} advance={advance}/><div className="demoMap"><Map stage={stage} mode={mode}/></div></section><section className="panel"><h2>Demo acceptance</h2><div className="check"><span>✓</span> Multi-node progression changes zone state</div><div className="check"><span>✓</span> Asset impact is spatially assessed</div><div className="check"><span>✓</span> One noisy node does not become critical</div><div className="check"><span>✓</span> Alert lifecycle requires human action</div><div className="check"><span>✓</span> Cloud outage does not stop local monitoring</div><div className="check"><span>✓</span> AI outputs have a defined adapter boundary</div></section></section>}

      <footer>MineGuard software prototype · decision-support system · prototype thresholds are demonstration settings only.</footer>
    </main>
  </div>;
}

function ScenarioPanel({ stage, mode, setStage, selectScenario, advance }: { stage: number; mode: "progressive" | "false_local" | "normal"; setStage: (n:number) => void; selectScenario: (m:"progressive"|"false_local"|"normal") => void; advance: () => void; }) {
  return <><div className="panelHead"><div><h2>Scenario simulator</h2><p>Same observation pipeline as real data.</p></div><span className="quiet">Stage {stage}/5</span></div><div className="scenarioBtns"><button className={mode === "progressive" ? "selected" : ""} onClick={() => selectScenario("progressive")}>Progressive</button><button className={mode === "false_local" ? "selected" : ""} onClick={() => selectScenario("false_local")}>False local</button><button className={mode === "normal" ? "selected" : ""} onClick={() => selectScenario("normal")}>Normal</button></div><div className="stageGrid"><button onClick={() => setStage(0)}>0</button><button onClick={() => setStage(1)}>1</button><button onClick={() => setStage(2)}>2</button><button onClick={() => setStage(3)}>3</button><button onClick={() => setStage(4)}>4</button><button onClick={() => setStage(5)}>5</button></div><div className="stageName">{stageLabels[stage]}</div><button className="primary wide" onClick={advance}>Advance scenario</button><p className="note">Simulation feeds synthetic observations into the same frontend state model. Replace the adapter with the hardware gateway and ML service for integrated deployment.</p></>;
}

function Empty({ text }: { text: string }) { return <div className="empty">{text}</div>; }
