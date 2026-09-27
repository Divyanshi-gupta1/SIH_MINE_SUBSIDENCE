/* TeraSense Live Demo: browser side.
   Renders what the backend pushes over /ws and sends slider / preset input to the REST endpoints.
   No model logic lives here: every class, confidence and status shown comes from the backend. */
"use strict";
(() => {
  const NODES = [1, 2, 3];
  const NODE_COLOR = { 1: "#59a6ff", 2: "#b18cff", 3: "#f28ab8" };
  const TILT_VIS = 2.0;      // scene exaggeration: degrees drawn per degree measured
  const SINK_VIS = 1.2;      // scene exaggeration: pixels drawn per mm
  const WINDOW_S = 60;
  const KEEP_S = 130;

  const FIELDS = [
    // dec: slider readout decimals, mdec: decimals for the measured value in the detail panel
    { key: "tilt", label: "Tilt", unit: "°", min: 0, max: 5, step: 0.1, dec: 1, mdec: 2 },
    { key: "vib", label: "Vibration", unit: " g", min: 0, max: 1, step: 0.01, dec: 2, mdec: 3 },
    { key: "disp", label: "Displacement", unit: " mm", min: 0, max: 50, step: 0.5, dec: 1, mdec: 1 },
  ];
  const STATE_TEXT = { normal: "Normal", warning: "Warning", critical: "Critical", offline: "No data", fault: "Sensor fault", starting: "Starting" };
  const STATUS_TEXT = { NORMAL: "Normal", DECOY: "Vibration only", POSSIBLE: "Possible", CONFIRMED: "Confirmed" };
  const FEATURE_NAMES = {
    tilt_deg: "Tilt, after noise floor (°)",
    vibration_rms: "Vibration RMS (g scale)",
    displacement_mm: "Displacement, after noise floor (mm)",
    crack_signal: "Crack signal (no sensor, fixed 0)",
    vibration_duration: "Vibration duration (samples)",
    tilt_vibration_correlation: "Tilt and vibration correlation",
    displacement_persistence: "Displacement persistence (0 or 1)",
    tilt_deviation_from_node_baseline: "Tilt deviation from baseline (°)",
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const store = {
    info: null, snap: null, selected: 1,
    history: { 1: [], 2: [], 3: [] }, events: [],
    eventsDirty: true, dragging: new Set(), lastInput: {}, pending: {},
  };

  /* ------------------------------------------------------------------ helpers */
  const mmss = (s) => {
    s = Math.max(0, Math.floor(s));
    return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
  };
  const fmt = (v, d) => (v === null || v === undefined || Number.isNaN(v) ? "--" : Number(v).toFixed(d));
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  };
  const classLabel = (c) => (store.info && store.info.class_labels[c]) || c;
  const nodeData = (id) => store.snap && store.snap.nodes.find((n) => n.id === id);

  let toastTimer = 0;
  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.hidden = true), 3500);
  }

  async function post(path, body) {
    try {
      const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!r.ok) throw new Error(await r.text());
      return await r.json();
    } catch (e) {
      toast("Could not reach the simulator. Check that the server is still running.");
      return null;
    }
  }

  /* ------------------------------------------------------------------ controls */
  const ctl = {};      // ctl[node][key] = { input, out }

  function buildControls() {
    const host = $("#node-controls");
    NODES.forEach((n) => {
      ctl[n] = {};
      const card = el("div", "ncard");
      card.dataset.node = n;
      const h = el("h3", null, "N" + n);
      h.append(el("span", null, "Zone " + n));
      card.append(h);
      FIELDS.forEach((f) => {
        const label = el("label", "slider");
        const top = el("span", "slider-top");
        top.append(el("span", null, f.label));
        const out = el("output", null, fmt(0, f.dec) + f.unit);
        top.append(out);
        const input = document.createElement("input");
        Object.assign(input, { type: "range", min: f.min, max: f.max, step: f.step, value: 0 });
        input.setAttribute("aria-label", `Node N${n} ${f.label.toLowerCase()}`);
        label.append(top, input);
        card.append(label);
        ctl[n][f.key] = { input, out, f };
        paintSlider(ctl[n][f.key]);

        const id = n + f.key;
        input.addEventListener("pointerdown", () => store.dragging.add(id));
        const release = () => store.dragging.delete(id);
        input.addEventListener("pointerup", release);
        input.addEventListener("pointercancel", release);
        input.addEventListener("blur", release);
        input.addEventListener("input", () => {
          paintSlider(ctl[n][f.key]);
          store.lastInput[id] = performance.now();
          (store.pending[n] = store.pending[n] || {})[f.key] = parseFloat(input.value);
        });
      });
      host.append(card);
    });
    // send slider input at most every 60 ms per node
    setInterval(() => {
      for (const n of Object.keys(store.pending)) {
        const body = store.pending[n];
        delete store.pending[n];
        post("/api/set", { node: Number(n), ...body });
      }
    }, 60);
  }

  function paintSlider(c) {
    const v = parseFloat(c.input.value);
    c.out.textContent = fmt(v, c.f.dec) + c.f.unit;
    c.input.style.setProperty("--fill", ((v - c.f.min) / (c.f.max - c.f.min)) * 100 + "%");
  }

  function syncControls() {
    const now = performance.now();
    NODES.forEach((n) => {
      const nd = nodeData(n);
      if (!nd) return;
      FIELDS.forEach((f) => {
        const id = n + f.key, c = ctl[n][f.key];
        if (store.dragging.has(id) || now - (store.lastInput[id] || 0) < 700) return;   // don't fight the user's hand
        c.input.value = nd.target[f.key];
        paintSlider(c);
      });
    });
  }

  /* ------------------------------------------------------------------ scene */
  function renderScene() {
    NODES.forEach((n) => {
      const nd = nodeData(n);
      if (!nd) return;
      const zone = $(`.zone[data-node="${n}"]`);
      zone.style.setProperty("--sink", (nd.actual.disp * SINK_VIS).toFixed(2));
      zone.style.setProperty("--tilt", (nd.actual.tilt * TILT_VIS).toFixed(2));
      $(`[data-readout="${n}"]`).textContent = `${fmt(nd.actual.tilt, 1)}° tilt, ${Math.round(nd.actual.disp)} mm down`;
      const state = nd.health.state;
      $$(`.node-dot[data-node="${n}"], .map-dot[data-node="${n}"]`).forEach((d) => {
        d.dataset.state = state;
        d.classList.toggle("is-selected", n === store.selected);
      });
    });
  }

  /* ------------------------------------------------------------------ health tiles */
  const tiles = {};

  function buildHealth() {
    const host = $("#health");
    NODES.forEach((n) => {
      const b = el("button", "htile");
      b.type = "button";
      b.dataset.node = n;
      const top = el("div", "htile-top");
      top.append(el("i"), document.createTextNode("N" + n + " "), el("span", null, "Zone " + n));
      const st = el("div", "htile-state");
      const dot = el("i", "health-dot");
      const stText = el("span", null, "Starting");
      st.append(dot, stText);
      const sub = el("div", "htile-sub", "Waiting for data");
      b.append(top, st, sub);
      b.addEventListener("click", () => select(n));
      host.append(b);
      tiles[n] = { b, dot, stText, sub };
    });
  }

  function renderHealth() {
    NODES.forEach((n) => {
      const nd = nodeData(n);
      if (!nd) return;
      const t = tiles[n], h = nd.health, s = nd.sample;
      t.b.dataset.state = h.state;
      t.dot.dataset.state = h.state;
      t.stText.textContent = STATE_TEXT[h.state] || h.label;
      t.b.classList.toggle("is-selected", n === store.selected);
      t.b.setAttribute("aria-pressed", String(n === store.selected));
      t.sub.textContent = s ? `${classLabel(s.top_class)}, ${Math.round(s.top_p * 100)}%` : "Waiting for data";
    });
  }

  /* ------------------------------------------------------------------ alerts */
  function renderAlerts() {
    const active = store.snap ? store.snap.nodes.filter((n) => n.alert_active).map((n) => "N" + n.id) : [];
    const count = $("#alert-count");
    count.dataset.active = String(active.length);
    count.textContent = active.length ? `${active.length} active: ${active.join(", ")}` : "None active";

    if (!store.eventsDirty) return;
    store.eventsDirty = false;
    const list = $("#alerts");
    list.replaceChildren();
    if (!store.events.length) {
      list.append(el("li", "empty", "No alerts yet. Move a slider or run a preset."));
      return;
    }
    store.events.forEach((ev) => {
      const li = el("li", "alert");
      li.dataset.level = ev.level;
      li.append(el("span", "alert-t", mmss(ev.t)));
      const body = el("div");
      const title = el("div", "alert-title");
      if (ev.node) {
        const tag = el("span", "alert-node", "N" + ev.node);
        tag.style.setProperty("--nc", NODE_COLOR[ev.node]);
        title.append(tag);
      }
      title.append(document.createTextNode(ev.title));
      body.append(title, el("div", "alert-detail", ev.detail));
      li.append(body);
      list.append(li);
    });
  }

  /* ------------------------------------------------------------------ node detail */
  const d = {};

  function buildDetail() {
    const host = $("#detail-body");
    host.innerHTML = `
      <div class="verdict-label" id="d-label">Waiting for the first sample</div>
      <div class="verdict-row"><span class="tag" id="d-status">Starting</span><span class="tag" data-tone="critical" id="d-latch" hidden>Alert latched</span></div>
      <div class="conf"><b id="d-conf">--</b><div class="bar" aria-hidden="true"><i id="d-conf-bar" style="width:0"></i></div></div>
      <p class="guard-line" id="d-guard">Model confidence in its top class</p>
      <div class="metrics">
        ${FIELDS.map((f) => `<div class="metric"><div class="metric-name">${f.label}</div>
          <div class="metric-val"><span id="m-${f.key}">--</span><small>${f.unit.trim()}</small></div>
          <div class="metric-set" id="g-${f.key}"></div></div>`).join("")}
      </div>
      <div class="probs" id="d-probs"></div>
      <div class="raw-label">Raw serial line (node, ax, ay, az, gx, gy, gz, dist)</div>
      <code class="raw" id="d-raw">--</code>
      <details class="model-inputs"><summary>What the model was fed</summary><dl id="d-feats"></dl></details>`;
    ["label", "status", "latch", "conf", "conf-bar", "guard", "probs", "raw", "feats"].forEach((k) => (d[k] = $("#d-" + k)));
    FIELDS.forEach((f) => { d["m" + f.key] = $("#m-" + f.key); d["g" + f.key] = $("#g-" + f.key); });
  }

  function buildProbRows() {
    d.probs.replaceChildren();
    d.rows = {};
    store.info.classes.forEach((c) => {
      const row = el("div", "prob");
      const bar = el("div", "bar");
      const fill = el("i");
      fill.style.width = "0";
      bar.append(fill);
      const val = el("span", null, "--");
      row.append(el("span", null, classLabel(c)), bar, val);
      d.probs.append(row);
      d.rows[c] = { fill, val };
    });
  }

  function renderDetail() {
    const n = store.selected, nd = nodeData(n);
    if (!nd) return;
    $$("#detail-tabs button").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.node) === n)));
    const s = nd.sample;
    d.raw.textContent = nd.raw || "--";
    FIELDS.forEach((f) => {
      d["m" + f.key].textContent = s ? fmt(s[f.key], f.mdec) : "--";
      d["g" + f.key].textContent = `Ground ${fmt(nd.actual[f.key], f.dec)}${f.unit}, slider ${fmt(nd.target[f.key], f.dec)}${f.unit}`;
    });
    if (!s) return;

    d.label.textContent = classLabel(s.top_class);
    d.conf.textContent = Math.round(s.top_p * 100) + "%";
    d["conf-bar"].style.width = s.top_p * 100 + "%";
    d.status.textContent = "Latest sample: " + STATUS_TEXT[s.status];
    d.status.dataset.tone = { NORMAL: "ok", DECOY: "warning", POSSIBLE: "warning", CONFIRMED: "critical" }[s.status];
    d.latch.hidden = !nd.alert_active;
    const thr = Math.round(store.info.confirm_confidence * 100);
    if (s.status === "NORMAL") d.guard.textContent = "No risk class is voting.";
    else if (s.status === "DECOY") d.guard.textContent = "Vibration only. Tilt and displacement are inside their noise floor, so this cannot raise a subsidence alert.";
    else if (s.streak === 0) d.guard.textContent = `Risk class voting, but below ${thr}% confidence, so it does not count toward an alert.`;
    else d.guard.textContent = `Guardrail: ${s.streak} of ${s.need} samples in a row at ${thr}% or more (one sample every ${store.info.sample_period_s} s).`;
    if (nd.alert_active && s.status !== "CONFIRMED") d.guard.textContent += " The alert stays latched until 3 samples in a row show no risk.";

    Object.entries(d.rows || {}).forEach(([c, r]) => {
      const p = s.probs[c] || 0;
      r.fill.style.width = p * 100 + "%";
      r.val.textContent = Math.round(p * 100) + "%";
    });
    d.feats.replaceChildren();
    Object.entries(s.features).forEach(([k, v]) => {
      d.feats.append(el("dt", null, FEATURE_NAMES[k] || k), el("dd", null, String(v)));
    });
  }

  function select(n) {
    store.selected = n;
    schedule();
  }

  /* ------------------------------------------------------------------ charts */
  const CHARTS = {
    tilt: { floor: 1, dec: 1, min: 0 },
    vib: { floor: 0.2, dec: 2, min: 0 },
    disp: { floor: 5, dec: 0, min: null },
  };

  // Axis with about 4 intervals and round tick steps (1, 2, 2.5, 5 x 10^k) that always covers the data.
  function axis(lo, hi, floor, allowNegative) {
    const top = Math.max(hi * 1.08, floor);
    const raw = top / 4, p = Math.pow(10, Math.floor(Math.log10(raw))), n = raw / p;
    const step = (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
    const max = Math.ceil(top / step - 1e-9) * step;
    const min = allowNegative && lo < -0.5 ? -Math.ceil((-lo * 1.1) / step) * step : 0;
    return { min, max, step };
  }

  function drawChart(canvas) {
    const key = canvas.dataset.chart, cfg = CHARTS[key];
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const tNow = store.snap ? store.snap.t : 0, t0 = tNow - WINDOW_S;
    const series = NODES.map((n) => store.history[n].filter((r) => r.t >= t0 - 2));
    let lo = Infinity, hi = -Infinity;
    series.forEach((s) => s.forEach((r) => { lo = Math.min(lo, r[key]); hi = Math.max(hi, r[key]); }));
    if (!Number.isFinite(hi)) { hi = 0; lo = 0; }
    const ax = axis(lo, hi, cfg.floor, cfg.min === null);
    const yMin = ax.min, yMax = ax.max;

    const pad = { l: 40, r: 10, t: 8, b: 22 };
    const pw = w - pad.l - pad.r, ph = h - pad.t - pad.b;
    const X = (t) => pad.l + ((t - t0) / WINDOW_S) * pw;
    const Y = (v) => pad.t + (1 - (v - yMin) / (yMax - yMin)) * ph;

    ctx.font = "11px 'Segoe UI', system-ui, sans-serif";
    ctx.fillStyle = "#94a0b2";
    ctx.strokeStyle = "#2a3441";
    ctx.lineWidth = 1;
    const decs = ax.step < 0.1 ? 3 : ax.step < 1 ? (Math.abs(ax.step * 10 - Math.round(ax.step * 10)) < 1e-6 ? 1 : 2) : ax.step % 1 ? 1 : 0;
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let v = yMin; v <= yMax + ax.step / 2; v += ax.step) {
      const y = Math.round(Y(v)) + 0.5;
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke();
      ctx.fillText(v.toFixed(decs), pad.l - 6, y);
    }
    if (yMin < 0) {                       // zero line for signed ranges
      ctx.strokeStyle = "#3a4657";
      const y0 = Math.round(Y(0)) + 0.5;
      ctx.beginPath(); ctx.moveTo(pad.l, y0); ctx.lineTo(w - pad.r, y0); ctx.stroke();
    }
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    [[0, "-60 s"], [0.5, "-30 s"], [1, "now"]].forEach(([f, txt]) => {
      ctx.textAlign = f === 0 ? "left" : f === 1 ? "right" : "center";
      ctx.fillText(txt, pad.l + pw * f, h - pad.b + 6);
    });

    if (!series.some((s) => s.length)) {
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText("Waiting for the first samples", pad.l + pw / 2, pad.t + ph / 2);
      return;
    }
    ctx.save();
    ctx.beginPath(); ctx.rect(pad.l, pad.t - 2, pw + 2, ph + 4); ctx.clip();
    series.forEach((s, i) => {
      if (!s.length) return;
      ctx.strokeStyle = NODE_COLOR[NODES[i]];
      ctx.lineWidth = 1.8;
      ctx.lineJoin = "round";
      ctx.beginPath();
      s.forEach((r, j) => (j ? ctx.lineTo(X(r.t), Y(r[key])) : ctx.moveTo(X(r.t), Y(r[key]))));
      ctx.stroke();
      const last = s[s.length - 1];
      ctx.fillStyle = NODE_COLOR[NODES[i]];
      ctx.beginPath(); ctx.arc(X(last.t), Y(last[key]), 3, 0, Math.PI * 2); ctx.fill();
    });
    ctx.restore();
  }

  function renderGraphs() {
    $$("canvas[data-chart]").forEach(drawChart);
    Object.keys(CHARTS).forEach((key) => {
      const box = $(`[data-now="${key}"]`);
      box.replaceChildren();
      NODES.forEach((n) => {
        const h = store.history[n], last = h[h.length - 1];
        const span = el("span");
        span.dataset.node = n;
        span.append(el("i"), document.createTextNode(last ? fmt(last[key], CHARTS[key].dec === 0 ? 1 : CHARTS[key].dec + 1) : "--"));
        box.append(span);
      });
    });
  }

  /* ------------------------------------------------------------------ top bar / presets */
  function renderTop() {
    const s = store.snap;
    $("#clock").textContent = mmss(s.t);
    $$("#speed button").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.speed) === s.speed)));
    const box = $("#script-status");
    const running = s.script;
    box.hidden = !running;
    $$("[data-preset]").forEach((b) => b.classList.toggle("is-running", !!running && !running.done && b.dataset.preset === running.name));
    if (running) {
      $("#script-label").textContent = running.label;
      $("#script-bar").style.width = running.progress * 100 + "%";
    }
  }

  /* ------------------------------------------------------------------ render loop */
  let raf = 0;
  function schedule() {
    if (!raf) raf = requestAnimationFrame(() => { raf = 0; render(); });
  }
  function render() {
    if (!store.snap || !store.info) return;
    renderTop();
    renderScene();
    renderHealth();
    renderAlerts();
    renderDetail();
    renderGraphs();
    syncControls();
  }

  /* ------------------------------------------------------------------ websocket */
  function setConn(state, text) {
    const c = $("#conn");
    c.dataset.state = state;
    c.lastElementChild.textContent = text;
  }

  function onHello(m) {
    store.info = m.info;
    store.snap = m.snapshot;
    NODES.forEach((n) => (store.history[n] = (m.history[n] || []).slice()));
    store.events = m.events.slice();
    store.eventsDirty = true;
    buildProbRows();
    schedule();
  }

  function onState(m) {
    store.snap = m;
    m.samples.forEach((r) => store.history[r.node].push(r));
    NODES.forEach((n) => {
      const h = store.history[n];
      while (h.length && h[0].t < m.t - KEEP_S) h.shift();
    });
    // ids are unique and increasing; skip any the hello snapshot already delivered (reset and first-load races)
    const fresh = m.events.filter((ev) => !store.events.some((e) => e.id === ev.id));
    if (fresh.length) {
      fresh.forEach((ev) => store.events.unshift(ev));
      store.events.length = Math.min(store.events.length, 60);
      store.eventsDirty = true;
    }
    schedule();
  }

  function connect() {
    const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
    ws.onopen = () => setConn("live", "Live");
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.type === "hello") onHello(m);
      else if (m.type === "state") onState(m);
    };
    ws.onclose = () => { setConn("down", "Disconnected, retrying"); setTimeout(connect, 1000); };
    ws.onerror = () => ws.close();
  }

  /* ------------------------------------------------------------------ wiring */
  function init() {
    buildControls();
    buildHealth();
    buildDetail();

    $$("[data-preset]").forEach((b) => b.addEventListener("click", async () => {
      store.lastInput = {};                                 // let sliders follow the preset at once
      await post("/api/preset", { name: b.dataset.preset });
    }));
    $$("#speed button").forEach((b) => b.addEventListener("click", () => post("/api/speed", { speed: Number(b.dataset.speed) })));
    $$("#detail-tabs button").forEach((b) => b.addEventListener("click", () => select(Number(b.dataset.node))));
    $$(".node-dot, .map-dot").forEach((b) => b.addEventListener("click", () => select(Number(b.dataset.node))));
    window.addEventListener("resize", schedule);
    connect();
  }

  init();
})();
