"use client";
import React, { useEffect, useRef, useState } from "react";
import type { Asset, LayerKey, NodeState, ZoneState } from "../lib/types";
import type { ScenarioKey } from "../lib/types";
import { SENSOR_LAYOUT, rank } from "../lib/demo";
import { StateBadge } from "./StateBadge";
import { computePhysicsSnapshot, lookupGridDeformation } from "../lib/physics";

/* ─── Colour helpers ──────────────────────────────────────────────── */

function lerpRGB(
  a: [number, number, number],
  b: [number, number, number],
  t: number
): [number, number, number] {
  return [
    Math.round(a[0] + (b[0] - a[0]) * t),
    Math.round(a[1] + (b[1] - a[1]) * t),
    Math.round(a[2] + (b[2] - a[2]) * t),
  ];
}

/**
 * Deformation intensity → vivid heatmap matching reference image
 *  0 mm  → dark green (#1a4a1a)
 *  ~2 mm → bright green (#22c55e)
 *  ~3 mm → yellow (#eab308)
 *  ~5 mm → orange (#f97316)
 *  7 mm+ → deep red (#991b1b)
 */
function deformRGB(mm: number, maxMm = 7): [number, number, number] {
  const t = Math.max(0, Math.min(1, mm / maxMm));
  const stops: [number, [number, number, number]][] = [
    [0.00, [15,  60,  15]],  // very dark green (background mine terrain)
    [0.15, [34, 197,  94]],  // bright green
    [0.38, [234, 179,  8]],  // yellow
    [0.60, [249, 115, 22]],  // orange
    [0.80, [220,  38,  38]],  // red
    [1.00, [100,   5,   5]],  // deep crimson
  ];
  for (let i = 0; i < stops.length - 1; i++) {
    const [t0, c0] = stops[i];
    const [t1, c1] = stops[i + 1];
    if (t >= t0 && t <= t1) return lerpRGB(c0, c1, (t - t0) / (t1 - t0));
  }
  return stops[stops.length - 1][1];
}

function expectedDeformRGB(mm: number, maxMm = 7): [number, number, number] {
  const t = Math.max(0, Math.min(1, mm / maxMm));
  const stops: [number, [number, number, number]][] = [
    [0.00, [240, 253, 250]],
    [0.40, [45,  212, 191]],
    [1.00, [15,  118, 110]],
  ];
  for (let i = 0; i < stops.length - 1; i++) {
    const [t0, c0] = stops[i];
    const [t1, c1] = stops[i + 1];
    if (t >= t0 && t <= t1) return lerpRGB(c0, c1, (t - t0) / (t1 - t0));
  }
  return stops[stops.length - 1][1];
}

function residualRGB(res: number, half = 5): [number, number, number] {
  if (res < 0) return lerpRGB([248, 250, 252], [29, 78, 216], Math.min(1, -res / half));
  return lerpRGB([248, 250, 252], [185, 28, 28], Math.min(1, res / half));
}

/** IDW interpolation at a single point */
function idwAt(
  qx: number, qy: number,
  samples: { px: number; py: number; val: number }[],
  p = 2
): number {
  const eps = 1e-4;
  let wSum = 0, vSum = 0;
  for (const s of samples) {
    const d = Math.sqrt((qx - s.px) ** 2 + (qy - s.py) ** 2);
    const w = 1 / (Math.pow(d, p) + eps);
    wSum += w; vSum += w * s.val;
  }
  return wSum < eps ? 0 : vSum / wSum;
}

/* ─── Types ───────────────────────────────────────────────────────── */

interface GisCommandMapProps {
  stage: number;
  mode: ScenarioKey;
  layers: Record<LayerKey, boolean>;
  onToggleLayer: (key: LayerKey) => void;
  nodes: NodeState[];
  zones: ZoneState[];
  asset: Asset;
  selectedEntity: { type: "node" | "zone" | "asset"; id: string } | null;
  onSelectEntity: (e: { type: "node" | "zone" | "asset"; id: string } | null) => void;
  /** True when live hardware data is actually streaming */
  isLiveActive?: boolean;
}

const LAYER_DEFS: { key: LayerKey; label: string; group: "base" | "overlay" | "analysis" }[] = [
  { key: "grid",     label: "Mine Boundary",        group: "base"     },
  { key: "risk",     label: "Underground Panels",   group: "overlay"  },
  { key: "sensors",  label: "Sensor Network",       group: "overlay"  },
  { key: "assets",   label: "Infrastructure",       group: "overlay"  },
  { key: "network",  label: "Mesh Links",           group: "overlay"  },
  { key: "vectors",  label: "Movement Vectors",     group: "overlay"  },
  { key: "heatmap",  label: "Observed Heatmap",     group: "analysis" },
  { key: "physics",  label: "Expected (PIM)",       group: "analysis" },
  { key: "residual", label: "Physics Residual",     group: "analysis" },
  { key: "impact",   label: "Asset Buffer",         group: "overlay"  },
];

/* ─── Node positions (% of 1000×580 viewBox) ─────────────────────── */
// SN-001 = N12-style (western), SN-002 = N38 (central, active), SN-003 = N39 (eastern)
// We map the 3 hardware nodes + 2 synthetic display nodes for mesh visualisation
const DISPLAY_NODES = [
  { id: "SN-001", x: 18, y: 28, label: "N12" },
  { id: "SN-002", x: 48, y: 52, label: "N38" },  // centre of bowl
  { id: "SN-003", x: 76, y: 58, label: "N39" },
];

const EXTRA_MESH_NODES = [
  { id: "N13", x: 38, y: 20 },
  { id: "N14", x: 66, y: 20 },
  { id: "N24", x: 27, y: 50 },
  { id: "N35", x: 40, y: 72 },
  { id: "N36", x: 55, y: 78 },
  { id: "N47", x: 74, y: 74 },
  { id: "N19", x: 80, y: 38 },
];

// Underground panel polygons (% coords, clockwise)
const PANELS = [
  {
    id: "Panel A-11",
    points: [[5,15],[40,8],[40,50],[5,55]],
    color: "#f0b429",
    fill: "rgba(240,180,41,0.06)",
  },
  {
    id: "Panel B-14",
    points: [[38,14],[70,14],[70,70],[38,70]],
    color: "#ef4444",
    fill: "rgba(239,68,68,0.09)",
  },
  {
    id: "Panel C-07",
    points: [[68,14],[96,18],[96,62],[68,70]],
    color: "#f0b429",
    fill: "rgba(240,180,41,0.06)",
  },
  {
    id: "Panel D-09",
    points: [[38,68],[68,68],[68,94],[38,94]],
    color: "#f0b429",
    fill: "rgba(240,180,41,0.06)",
  },
];

// Outer mine boundary (% coords)
const BOUNDARY = [
  [8,8],[50,4],[92,10],[96,30],[93,65],[80,88],
  [55,94],[30,92],[8,75],[4,40],
];

// Mesh triangulation edges between node IDs
const MESH_EDGES: [string, string][] = [
  ["SN-001","N13"],["N13","N14"],["N14","SN-003"],
  ["SN-001","N24"],["N24","SN-002"],["SN-002","N14"],
  ["SN-002","N47"],["N47","SN-003"],["SN-002","N35"],
  ["N35","N36"],["N36","N47"],["N24","N35"],
  ["N13","SN-002"],["SN-003","N19"],["N19","N14"],
];

/* ─── Main component ──────────────────────────────────────────────── */

export function GisCommandMap({
  stage, mode, layers, onToggleLayer,
  nodes, zones, asset, selectedEntity, onSelectEntity,
  isLiveActive = false,
}: GisCommandMapProps) {
  const [hovered, setHovered] = useState<{ type: "node" | "zone" | "asset"; id: string } | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const vbW = 1000, vbH = 580;
  const active = selectedEntity || hovered;

  // Build a lookup for hardware node positions (% → px in viewBox)
  const nodePosPct: Record<string, { x: number; y: number }> = {};
  for (const s of DISPLAY_NODES) nodePosPct[s.id] = { x: s.x, y: s.y };
  for (const s of EXTRA_MESH_NODES) nodePosPct[s.id] = { x: s.x, y: s.y };

  const allMeshNodes = [
    ...DISPLAY_NODES.map(n => ({ id: n.id, x: n.x, y: n.y })),
    ...EXTRA_MESH_NODES,
  ];

  function toSvg(pctX: number, pctY: number) {
    return { x: (pctX / 100) * vbW, y: (pctY / 100) * vbH };
  }

  const activeNode = active?.type === "node" ? nodes.find(n => n.id === active.id) : null;
  const activeZone = active?.type === "zone" ? zones.find(z => z.id === active.id) : null;
  const isAssetActive = active?.type === "asset" || active?.id === asset.id;

  /* ─── Canvas heatmap render ─────────────────────────────────────── */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, vbW, vbH);

    const showObs = layers.heatmap;
    const showExp = layers.physics;
    const showRes = layers.residual;
    if (!showObs && !showExp && !showRes) return;

    // Compute physics grid for expected deformation
    const { snapshot } = computePhysicsSnapshot(stage, nodes, zones);
    const pimGrid = snapshot.grid;

    // Build IDW sample set from actual hardware nodes
    const samples: { px: number; py: number; val: number }[] = [];
    for (const n of nodes) {
      if (n.quality === "UNAVAILABLE") continue;
      const pos = nodePosPct[n.id];
      if (!pos) continue;
      samples.push({
        px: (pos.x / 100) * vbW,
        py: (pos.y / 100) * vbH,
        val: n.displacement,
      });
    }

    const step = 4; // pixels per cell
    const imgData = ctx.createImageData(vbW, vbH);
    const d = imgData.data;

    // Radial influence from the subsidence bowl centre for smooth blending
    const cx = (48 / 100) * vbW;  // SN-002 is bowl centre
    const cy = (52 / 100) * vbH;

    for (let gy = 0; gy < vbH; gy += step) {
      for (let gx = 0; gx < vbW; gx += step) {
        const expVal = lookupGridDeformation(pimGrid, (gx / vbW) * 900, (gy / vbH) * 530);
        const obsVal = samples.length > 0 ? idwAt(gx, gy, samples) : 0;

        let r = 20, g = 20, b = 20;
        let alpha = 190;

        if (showRes) {
          [r, g, b] = residualRGB(obsVal - expVal, 5);
          alpha = 170;
        } else if (showExp && !showObs) {
          [r, g, b] = expectedDeformRGB(expVal, 7);
          alpha = 170;
        } else {
          // Primary vivid heatmap (matching reference)
          // Use IDW observed + Gaussian bowl blend for smooth radial effect
          const distFromCentre = Math.sqrt((gx - cx) ** 2 + (gy - cy) ** 2);
          const maxR = Math.max(vbW, vbH) * 0.55;
          const radialWeight = Math.exp(-((distFromCentre / maxR) ** 2));
          const stageMax = [0, 1, 2.5, 4, 5.5, 7][Math.min(stage, 5)];
          const blended = samples.length > 0
            ? obsVal
            : stageMax * radialWeight; // fallback pure radial for demo
          [r, g, b] = deformRGB(blended, 7);
          // More transparent at periphery for satellite effect
          alpha = Math.round(130 + 80 * radialWeight);
        }

        for (let dy = 0; dy < step && gy + dy < vbH; dy++) {
          for (let dx = 0; dx < step && gx + dx < vbW; dx++) {
            const idx = ((gy + dy) * vbW + (gx + dx)) * 4;
            d[idx]     = r;
            d[idx + 1] = g;
            d[idx + 2] = b;
            d[idx + 3] = alpha;
          }
        }
      }
    }
    ctx.putImageData(imgData, 0, 0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, zones, stage, layers.heatmap, layers.physics, layers.residual]);

  /* ─── Node colour by severity ───────────────────────────────────── */
  function nodeRingColor(n: NodeState) {
    if (n.quality === "UNAVAILABLE") return "#6b7280";
    if (n.modelClass === "subsidence_precursor") {
      if (n.modelConfidence > 0.7) return "#ef4444"; // critical red
      return "#f97316"; // warning orange
    }
    if (n.displacement > 2) return "#eab308"; // watch yellow
    return "#22c55e"; // normal green
  }

  function nodeLabel(n: NodeState) {
    const disp = DISPLAY_NODES.find(d => d.id === n.id);
    return disp?.label ?? n.id;
  }

  return (
    <div className="engPanel" style={{ display: "flex", flexDirection: "column", gap: 0, minHeight: 0 }}>
      {/* Header */}
      <div className="engPanelHeader">
        <div className="engPanelTitle">
          <span>⌖</span>
          <span>MineGuard GIS — Subsidence Deformation Map</span>
          {layers.residual && (
            <span style={{ fontSize: "9px", background: "#3b82f6", color: "#fff", padding: "1px 6px", borderRadius: "3px", marginLeft: 6, fontWeight: 700 }}>
              RESIDUAL FIELD
            </span>
          )}
          {layers.physics && !layers.residual && (
            <span style={{ fontSize: "9px", background: "#0f766e", color: "#ccfbf1", padding: "1px 6px", borderRadius: "3px", marginLeft: 6, fontWeight: 700 }}>
              EXPECTED (KNOTHE PIM)
            </span>
          )}
          {layers.heatmap && !layers.residual && !layers.physics && (
            <span style={{ fontSize: "9px", background: "#dc2626", color: "#fff", padding: "1px 6px", borderRadius: "3px", marginLeft: 6, fontWeight: 700 }}>
              DEFORMATION HEATMAP
            </span>
          )}
        </div>
        <div className="engPanelSub">
          MINE LOCAL ENGINEERING GRID · PANEL B-14 ACTIVE SUBSIDENCE ZONE · DATUM: COLLIERY GRID 2026
        </div>
      </div>

      {/* Map workspace — dark satellite-style */}
      <div className="gisContainer" style={{ position: "relative", flex: 1, background: "#111827" }}>

        {/* Canvas heatmap layer behind SVG */}
        <canvas
          ref={canvasRef}
          width={vbW}
          height={vbH}
          style={{
            position: "absolute", inset: 0,
            width: "100%", height: "100%",
            pointerEvents: "none",
            opacity: layers.heatmap || layers.physics || layers.residual ? 1 : 0,
            transition: "opacity 0.3s",
          }}
        />

        {/* SVG interactive overlay */}
        <svg
          viewBox={`0 0 ${vbW} ${vbH}`}
          className="gisSvg"
          aria-label="Subsidence deformation map"
          style={{ position: "relative", zIndex: 1 }}
        >
          <defs>
            {/* Satellite-style dark terrain texture via gradient */}
            <radialGradient id="terrainGrad" cx="48%" cy="52%" r="55%">
              <stop offset="0%" stopColor="#1f2d1f" />
              <stop offset="40%" stopColor="#1a2e1a" />
              <stop offset="100%" stopColor="#0f1a0f" />
            </radialGradient>
            <marker id="vec" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
              <path d="M0 0 L7 3.5 L0 7 Z" fill="#60a5fa" />
            </marker>
            <marker id="vecCrit" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
              <path d="M0 0 L7 3.5 L0 7 Z" fill="#ef4444" />
            </marker>
            <filter id="glow">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>

          {/* Dark terrain background */}
          {!(layers.heatmap || layers.physics || layers.residual) && (
            <rect x="0" y="0" width={vbW} height={vbH} fill="url(#terrainGrad)" />
          )}

          {/* ── OUTER MINE BOUNDARY ── */}
          {layers.grid && (
            <g>
              <polygon
                points={BOUNDARY.map(([px, py]) => `${(px/100)*vbW},${(py/100)*vbH}`).join(" ")}
                fill="none"
                stroke="#94a3b8"
                strokeWidth="2"
                strokeDasharray="10 5"
              />
              <text x="40" y="36" fill="#94a3b8" fontSize="11" fontFamily="var(--font-mono)" fontWeight="700">
                MINE BOUNDARY — COLLIERY PANEL SYSTEM
              </text>
              {/* Metric scale bar */}
              <g transform="translate(40,545)">
                <line x1="0" y1="0" x2="180" y2="0" stroke="#94a3b8" strokeWidth="1.5" />
                <line x1="0" y1="-5" x2="0" y2="5" stroke="#94a3b8" strokeWidth="1.5" />
                <line x1="60" y1="-5" x2="60" y2="5" stroke="#94a3b8" strokeWidth="1.5" />
                <line x1="120" y1="-5" x2="120" y2="5" stroke="#94a3b8" strokeWidth="1.5" />
                <line x1="180" y1="-5" x2="180" y2="5" stroke="#94a3b8" strokeWidth="1.5" />
                <text x="0"   y="-9" textAnchor="middle" fill="#94a3b8" fontSize="8" fontFamily="var(--font-mono)">0</text>
                <text x="60"  y="-9" textAnchor="middle" fill="#94a3b8" fontSize="8" fontFamily="var(--font-mono)">500</text>
                <text x="120" y="-9" textAnchor="middle" fill="#94a3b8" fontSize="8" fontFamily="var(--font-mono)">1,000</text>
                <text x="180" y="-9" textAnchor="middle" fill="#94a3b8" fontSize="8" fontFamily="var(--font-mono)">1,500 m</text>
              </g>
            </g>
          )}

          {/* ── UNDERGROUND PANELS ── */}
          {layers.risk && PANELS.map(panel => (
            <g key={panel.id}>
              <polygon
                points={panel.points.map(([px,py]) => `${(px/100)*vbW},${(py/100)*vbH}`).join(" ")}
                fill={panel.fill}
                stroke={panel.color}
                strokeWidth="1.8"
                strokeDasharray={panel.id === "Panel B-14" ? "none" : "7 4"}
              />
              {(() => {
                const xs = panel.points.map(([px]) => (px/100)*vbW);
                const ys = panel.points.map(([,py]) => (py/100)*vbH);
                const cx = xs.reduce((a,b)=>a+b,0)/xs.length;
                const cy = ys.reduce((a,b)=>a+b,0)/ys.length;
                const isActive = panel.id === "Panel B-14";
                return (
                  <g>
                    {isActive && (
                      <rect x={cx-46} y={cy-10} width={92} height={18} rx="3"
                        fill="#991b1b" opacity="0.9" />
                    )}
                    <text x={cx} y={cy+5} textAnchor="middle"
                      fill={isActive ? "#fff" : panel.color}
                      fontSize={isActive ? "11" : "10"}
                      fontFamily="var(--font-mono)" fontWeight="700">
                      {panel.id}
                    </text>
                  </g>
                );
              })()}
            </g>
          ))}

          {/* ── MESH TRIANGULATION LINES ── */}
          {layers.network && MESH_EDGES.map(([a, b], i) => {
            const posA = nodePosPct[a]; const posB = nodePosPct[b];
            if (!posA || !posB) return null;
            const svgA = toSvg(posA.x, posA.y); const svgB = toSvg(posB.x, posB.y);
            return (
              <line key={i}
                x1={svgA.x} y1={svgA.y} x2={svgB.x} y2={svgB.y}
                stroke="rgba(255,255,255,0.30)"
                strokeWidth="1"
                strokeDasharray="5 4"
              />
            );
          })}

          {/* ── MOVEMENT VECTORS on live nodes ── */}
          {layers.vectors && stage >= 1 && nodes.map(n => {
            if (n.quality === "UNAVAILABLE") return null;
            const pos = nodePosPct[n.id]; if (!pos) return null;
            const sv = toSvg(pos.x, pos.y);
            const mag = Math.min(55, n.displacement * 8 + 10);
            const isCrit = n.modelClass === "subsidence_precursor" && n.modelConfidence > 0.7;
            return (
              <line key={n.id}
                x1={sv.x} y1={sv.y}
                x2={sv.x + mag * 0.7} y2={sv.y + mag * 0.5}
                stroke={isCrit ? "#ef4444" : "#60a5fa"}
                strokeWidth="2"
                markerEnd={isCrit ? "url(#vecCrit)" : "url(#vec)"}
              />
            );
          })}

          {/* ── ASSET IMPACT BUFFER ── */}
          {layers.impact && (() => {
            const sv = toSvg(84, 72);
            return (
              <circle cx={sv.x} cy={sv.y} r="62"
                fill={asset.impactStatus === "AT RISK" ? "rgba(239,68,68,0.15)" : "rgba(148,163,184,0.10)"}
                stroke={asset.impactStatus === "AT RISK" ? "#ef4444" : "#64748b"}
                strokeWidth="1.5" strokeDasharray="6 4"
              />
            );
          })()}

          {/* ── PROTECTED ASSET ── */}
          {layers.assets && (() => {
            const sv = toSvg(84, 72);
            const isActive = isAssetActive && !activeNode && !activeZone;
            return (
              <g onClick={() => onSelectEntity({ type: "asset", id: asset.id })}
                onMouseEnter={() => setHovered({ type: "asset", id: asset.id })}
                onMouseLeave={() => setHovered(null)}
                style={{ cursor: "pointer" }}>
                <rect x={sv.x - 32} y={sv.y - 20} width={64} height={38} rx="4"
                  fill="#1e293b"
                  stroke={asset.impactStatus === "AT RISK" ? "#ef4444" : isActive ? "#60a5fa" : "#475569"}
                  strokeWidth={isActive ? 2.5 : 1.5}
                />
                <text x={sv.x} y={sv.y - 4} textAnchor="middle"
                  fill="#e2e8f0" fontSize="9" fontFamily="var(--font-mono)" fontWeight="800">
                  {asset.id}
                </text>
                <text x={sv.x} y={sv.y + 10} textAnchor="middle"
                  fill={asset.impactStatus === "AT RISK" ? "#f87171" : "#94a3b8"}
                  fontSize="8" fontFamily="var(--font-mono)">
                  {asset.impactStatus}
                </text>
              </g>
            );
          })()}

          {/* ── GATEWAY (shown only when live/connected) ── */}
          {(() => {
            const sv = toSvg(87, 12);
            const connected = isLiveActive;
            return (
              <g>
                {/* Dashed lines to nodes when connected */}
                {connected && layers.network && DISPLAY_NODES.map(dn => {
                  const ns = toSvg(dn.x, dn.y);
                  return (
                    <line key={dn.id}
                      x1={sv.x} y1={sv.y} x2={ns.x} y2={ns.y}
                      stroke="rgba(96,165,250,0.4)" strokeWidth="1"
                      strokeDasharray="4 4" />
                  );
                })}
                <rect x={sv.x - 32} y={sv.y - 18} width={64} height={36} rx="3"
                  fill="#0f172a"
                  stroke={connected ? "#3b82f6" : "#ef4444"}
                  strokeWidth={connected ? 2 : 1.5}
                />
                <text x={sv.x} y={sv.y - 2} textAnchor="middle"
                  fill={connected ? "#60a5fa" : "#f87171"}
                  fontSize="9" fontFamily="var(--font-mono)" fontWeight="800">
                  GW-001
                </text>
                <text x={sv.x} y={sv.y + 12} textAnchor="middle"
                  fill={connected ? "#3b82f6" : "#ef4444"}
                  fontSize="7" fontFamily="var(--font-mono)" fontWeight="700">
                  {connected ? "● LIVE" : "○ OFFLINE"}
                </text>
              </g>
            );
          })()}

          {/* ── EXTRA MESH NODES (display only, not hardware) ── */}
          {layers.sensors && EXTRA_MESH_NODES.map(en => {
            const sv = toSvg(en.x, en.y);
            return (
              <g key={en.id}>
                <circle cx={sv.x} cy={sv.y} r="9"
                  fill="#1e293b" stroke="#22c55e" strokeWidth="1.5" />
                <circle cx={sv.x} cy={sv.y} r="4" fill="#22c55e" />
                <text x={sv.x} y={sv.y - 14} textAnchor="middle"
                  fill="#e2e8f0" fontSize="8" fontFamily="var(--font-mono)" fontWeight="700">
                  {en.id}
                </text>
              </g>
            );
          })}

          {/* ── LIVE HARDWARE SENSOR NODES (SN-001/002/003) ── */}
          {layers.sensors && nodes.map(n => {
            const pos = nodePosPct[n.id]; if (!pos) return null;
            const sv = toSvg(pos.x, pos.y);
            const ringCol = nodeRingColor(n);
            const isSelected = selectedEntity?.type === "node" && selectedEntity.id === n.id;
            const isHov = hovered?.type === "node" && hovered.id === n.id;
            const lbl = nodeLabel(n);
            const isActive = n.quality !== "UNAVAILABLE";
            return (
              <g key={n.id}
                onClick={() => onSelectEntity({ type: "node", id: n.id })}
                onMouseEnter={() => setHovered({ type: "node", id: n.id })}
                onMouseLeave={() => setHovered(null)}
                style={{ cursor: "pointer" }}>
                {/* Outer ring */}
                <circle cx={sv.x} cy={sv.y} r={isSelected || isHov ? 20 : 16}
                  fill="rgba(15,23,42,0.85)"
                  stroke={isSelected || isHov ? "#fff" : ringCol}
                  strokeWidth={isSelected || isHov ? 2.5 : 2}
                  filter={isActive && n.modelClass === "subsidence_precursor" ? "url(#glow)" : undefined}
                />
                {/* Inner dot */}
                <circle cx={sv.x} cy={sv.y} r="6" fill={ringCol} />
                {/* Crosshair on critical */}
                {n.modelClass === "subsidence_precursor" && n.modelConfidence > 0.7 && (
                  <>
                    <circle cx={sv.x} cy={sv.y} r="11" fill="none" stroke={ringCol} strokeWidth="1.5" />
                    <line x1={sv.x - 16} y1={sv.y} x2={sv.x + 16} y2={sv.y} stroke={ringCol} strokeWidth="0.8" />
                    <line x1={sv.x} y1={sv.y - 16} x2={sv.x} y2={sv.y + 16} stroke={ringCol} strokeWidth="0.8" />
                  </>
                )}
                {/* Node ID label */}
                <rect x={sv.x - 18} y={sv.y - 30} width="36" height="13" rx="2" fill="#1e293b" opacity="0.95" />
                <text x={sv.x} y={sv.y - 20}
                  textAnchor="middle" fill="#f1f5f9"
                  fontSize="9" fontFamily="var(--font-mono)" fontWeight="800">
                  {lbl}
                </text>
                {/* Displacement readout */}
                <text x={sv.x} y={sv.y + 32}
                  textAnchor="middle"
                  fill={isActive ? ringCol : "#6b7280"}
                  fontSize="9" fontFamily="var(--font-mono)">
                  {isActive ? `${n.displacement.toFixed(1)}mm` : "OFFLINE"}
                </text>
              </g>
            );
          })}

          {/* ── COMPASS ROSE ── */}
          <g transform="translate(940,48)">
            <circle cx="0" cy="0" r="20" fill="#0f172a" stroke="#475569" strokeWidth="1.5" />
            <path d="M0 -15 L4 4 L0 1 L-4 4 Z" fill="#f1f5f9" />
            <path d="M0 15 L4 -4 L0 -1 L-4 -4 Z" fill="#475569" />
            <text x="0" y="-22" textAnchor="middle" fill="#f1f5f9"
              fontSize="10" fontFamily="var(--font-mono)" fontWeight="800">N</text>
          </g>

          {/* ── DEFORMATION LEGEND (floating card, bottom left) ── */}
          {(layers.heatmap || layers.physics || layers.residual) && (
            <g transform="translate(28, 440)">
              <rect x="0" y="0" width="155" height={layers.residual ? 90 : 110} rx="4"
                fill="rgba(15,23,42,0.92)" stroke="#334155" strokeWidth="1" />
              <text x="10" y="18" fill="#e2e8f0" fontSize="9" fontFamily="var(--font-mono)" fontWeight="800">
                {layers.residual ? "Physics Residual" : layers.physics ? "Expected Deformation" : "Deformation Level"}
              </text>
              {layers.heatmap && !layers.residual && !layers.physics && (
                <>
                  {[
                    { col: "#22c55e", lbl: "Normal  (0–1 mm)" },
                    { col: "#eab308", lbl: "Watch   (1–3 mm)" },
                    { col: "#f97316", lbl: "Warning (3–5 mm)" },
                    { col: "#ef4444", lbl: "Critical (>5 mm)"  },
                  ].map(({ col, lbl }, i) => (
                    <g key={col} transform={`translate(10,${28 + i * 20})`}>
                      <circle cx="7" cy="7" r="7" fill={col} />
                      <text x="20" y="11" fill="#e2e8f0" fontSize="8" fontFamily="var(--font-mono)">{lbl}</text>
                    </g>
                  ))}
                </>
              )}
              {layers.residual && (
                <>
                  {[
                    { col: "#1d4ed8", lbl: "Obs < Expected" },
                    { col: "#f8fafc", lbl: "Near agreement" },
                    { col: "#b91c1c", lbl: "Obs > Expected" },
                  ].map(({ col, lbl }, i) => (
                    <g key={lbl} transform={`translate(10,${28 + i * 20})`}>
                      <rect x="0" y="0" width="14" height="12" fill={col} rx="2" stroke="#334155" strokeWidth="0.5" />
                      <text x="20" y="10" fill="#e2e8f0" fontSize="8" fontFamily="var(--font-mono)">{lbl}</text>
                    </g>
                  ))}
                </>
              )}
              {layers.physics && !layers.residual && (
                <>
                  {[
                    { col: "#f0fdf4", lbl: "Low   (0 mm)" },
                    { col: "#2dd4bf", lbl: "Mod (~3 mm)" },
                    { col: "#0f766e", lbl: "High (Smax)"  },
                  ].map(({ col, lbl }, i) => (
                    <g key={lbl} transform={`translate(10,${28 + i * 20})`}>
                      <rect x="0" y="0" width="14" height="12" fill={col} rx="2" stroke="#0d9488" strokeWidth="0.5" />
                      <text x="20" y="10" fill="#e2e8f0" fontSize="8" fontFamily="var(--font-mono)">{lbl}</text>
                    </g>
                  ))}
                </>
              )}
            </g>
          )}

          {/* ── COORDINATE LABELS ── */}
          <text x="32" y="560" fill="#475569" fontSize="8" fontFamily="var(--font-mono)">
            E 412,800m
          </text>
          <text x="480" y="560" fill="#475569" fontSize="8" fontFamily="var(--font-mono)">
            E 413,250m
          </text>
          <text x="880" y="560" fill="#475569" fontSize="8" fontFamily="var(--font-mono)">
            E 413,700m
          </text>
        </svg>

        {/* ── Hover / Click Flyout Card ── */}
        {active && (
          <div className="mapFloatCard">
            {activeNode && (() => {
              const zone = zones.find(z => z.id === activeNode.zoneId);
              const expected = zone?.physicsExpectedMm ?? 0;
              const residual = activeNode.displacement - expected;
              return (
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-subtle)", paddingBottom: 4 }}>
                    <strong style={{ fontFamily: "var(--font-mono)", fontSize: "11px" }}>
                      {nodeLabel(activeNode)} ({activeNode.id})
                    </strong>
                    <span className={`badge ${activeNode.healthy ? "badge-normal" : "badge-critical"}`}>
                      {activeNode.quality}
                    </span>
                  </div>
                  {activeNode.healthMessage && !activeNode.healthy && (
                    <div style={{ color: "#b91c1c", fontSize: "9px", margin: "4px 0", background: "#fee2e2", padding: "3px 6px", borderRadius: 2 }}>
                      ⚠️ {activeNode.healthMessage}
                    </div>
                  )}
                  <table className="inspectTable" style={{ marginTop: 6 }}>
                    <tbody>
                      <tr><th>Zone</th><td className="val">{activeNode.zoneId}</td></tr>
                      <tr><th>Tilt</th><td className="val">{activeNode.tilt.toFixed(2)}°</td></tr>
                      <tr><th>Displacement</th><td className="val">{activeNode.displacement.toFixed(2)} mm</td></tr>
                      <tr><th>Deform Rate</th><td className="val">{activeNode.deformationRate.toFixed(2)} mm/min</td></tr>
                      <tr><th>Vibration</th><td className="val">{activeNode.vibration.toFixed(2)} g</td></tr>
                      <tr><th>Knothe Expected</th><td className="val">{expected.toFixed(2)} mm</td></tr>
                      <tr><th>Physics Residual</th>
                        <td className="val" style={{ color: Math.abs(residual) > 1.2 ? "#b91c1c" : "#15803d", fontWeight: 700 }}>
                          {residual >= 0 ? "+" : ""}{residual.toFixed(2)} mm
                        </td>
                      </tr>
                      <tr><th>ML Verdict</th><td className="val">{activeNode.modelClass.replaceAll("_", " ")}</td></tr>
                      <tr><th>ML Confidence</th><td className="val">{Math.round(activeNode.modelConfidence * 100)}%</td></tr>
                      <tr><th>Battery / RSSI</th><td className="val">{activeNode.battery}% · {activeNode.rssi} dBm</td></tr>
                      <tr><th>Last Seen</th><td className="val">{activeNode.lastSeen}</td></tr>
                    </tbody>
                  </table>
                </div>
              );
            })()}

            {activeZone && (
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-subtle)", paddingBottom: 4 }}>
                  <div>
                    <strong style={{ fontFamily: "var(--font-mono)", fontSize: "11px" }}>{activeZone.id}</strong>
                    <div style={{ fontSize: "9px", color: "var(--muted)" }}>{activeZone.name}</div>
                  </div>
                  <StateBadge state={activeZone.state} />
                </div>
                <table className="inspectTable" style={{ marginTop: 6 }}>
                  <tbody>
                    <tr><th>Trend</th><td className="val">{activeZone.trend}</td></tr>
                    <tr><th>Observed Disp</th><td className="val">{activeZone.observedMm?.toFixed(2) ?? "—"} mm</td></tr>
                    <tr><th>Knothe Expected</th><td className="val">{activeZone.physicsExpectedMm?.toFixed(2) ?? "—"} mm</td></tr>
                    <tr><th>Physics Residual</th><td className="val">{activeZone.physicsResidualMm?.toFixed(2) ?? "—"} mm</td></tr>
                    <tr><th>Agreement</th><td className="val">{activeZone.physicsStatus ?? "—"}</td></tr>
                    <tr><th>Asset Dist</th><td className="val">{activeZone.assetDistanceM} m</td></tr>
                  </tbody>
                </table>
              </div>
            )}

            {isAssetActive && !activeNode && !activeZone && (
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-subtle)", paddingBottom: 4 }}>
                  <div>
                    <strong style={{ fontFamily: "var(--font-mono)", fontSize: "11px" }}>{asset.id}</strong>
                    <div style={{ fontSize: "9px", color: "var(--muted)" }}>{asset.label}</div>
                  </div>
                  <span className={`badge ${asset.impactStatus === "AT RISK" ? "badge-critical" : "badge-normal"}`}>
                    {asset.impactStatus}
                  </span>
                </div>
                <table className="inspectTable" style={{ marginTop: 6 }}>
                  <tbody>
                    <tr><th>Structure</th><td className="val">{asset.type}</td></tr>
                    <tr><th>Nearest Zone</th><td className="val">{asset.nearestZoneId} ({asset.distanceM}m)</td></tr>
                    <tr><th>Impact State</th><td className="val">{asset.impactStatus}</td></tr>
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Layer Toggles Toolbar ── */}
      <div className="gisLayerToolbar">
        <span className="gisLayerLabel">Layers:</span>
        {LAYER_DEFS.map(item => (
          <button
            key={item.key}
            className={`layerToggle ${layers[item.key] ? "active" : ""} ${item.group === "analysis" ? "layerToggleAnalysis" : ""}`}
            onClick={() => onToggleLayer(item.key)}
          >
            {item.label}
          </button>
        ))}
      </div>
    </div>
  );
}
