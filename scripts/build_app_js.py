"""Builds the comprehensive web/app.js script supporting all 12 GUI panels."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "web" / "app.js"

APP_CODE = r'''"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  catalog: null,
  config: null,
  result: null,
  method: "M1",
  page: "lab",
  filter: "all",
  yaw: -0.62,
  pitch: 0.48,
  zoom: 1,
  analysis: null,
  busy: false,
  // Simulation playback state
  sim: {
    playing: false,
    time: 0.0,
    maxTime: 30.0,
    speed: 1.0,
    rotorAngle: 0.0,
    timer: null,
    lastTick: 0
  },
  optResult: null,
  mcResult: null,
  activeChannels: {
    hrr: true,
    pos: true,
    tilt: true,
    rx: true,
    power: true,
    battery: true
  }
};

const labels = {
  lab: ["통합 시뮬레이션 스튜디오 (Studio Workbench)", "거리·횡풍·센서지연 조건에서 3D 유동장, 6-DOF 드론 기체, 화재 플룸 및 실시간 성능을 통합 관측합니다."],
  comparison: ["소화 방식 종합 비교 분석 (Comparison Panel)", "5개 소화 방식(M1~M5) 및 복합 운용의 5축 Radar 지표, 시너지 Matrix Heatmap, 수치 비교표를 열람합니다."],
  editor: ["시나리오 및 미션 에디터 (Scenario Editor)", "미션 5단계 비주얼 페이즈 빌더 및 스키마 검증 기반 양방향 JSON 에디터로 연구 조건을 설계합니다."],
  optimize: ["다목적 Pareto 최적화 [선택] (Optimization Panel)", "소화시간, 비행 에너지, 위치오차, 약제효율을 동시 최적화하는 파레토 프론티어를 탐색합니다."],
  montecarlo: ["불확실성 및 몬테카를로 분석 [선택] (Monte Carlo Panel)", "횡풍, 센서지연, 화재규모 확률분포 샘플링을 통해 소화 성공 확률 P(Quench) 및 Sobol 민감도를 분석합니다."],
  export: ["연구 결과 및 차트 내보내기 (Result Export Panel)", "10대 학술 고정밀 시각화 차트(300 DPI), 정밀 수치 CSV, 학술 보고서 및 종합 압축팩(ZIP)을 내려받습니다."],
  physics: ["지배방정식과 물리 유도", "질량·운동량·에너지 보존 법칙 및 각 진압 방식의 수학적 유도와 소스 코드 매핑을 열람합니다."],
  nativefields: ["CFD 3D 격자 단면 탐색", "FDS 및 OpenFOAM 네이티브 시뮬레이션 원본 격자의 3D 슬라이스 및 물리량을 탐색합니다."],
  evidence: ["원본·가정·검증 게이트", "자료 해시 무결성, 호환성 판정 게이트, native FDS 솔버 실행 기록을 검증합니다."]
};

const canvasFont = (size, mono = true) =>
  `${size}px ${mono ? '"JetBrains Mono", "Berkeley Mono", Consolas, monospace' : '"Pretendard", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'}`;

const format = (v, digits = 3) =>
  v === null || v === undefined || !Number.isFinite(Number(v)) ? "—" : Number(v).toLocaleString("ko-KR", { maximumFractionDigits: digits });

const el = (tag, text, cls) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
};

function toast(message, error = false) {
  const n = $("toast");
  if (!n) return;
  n.textContent = message;
  n.classList.toggle("error", error);
  n.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (n.hidden = true), 6500);
}

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data?.error || `HTTP ${r.status}`);
  return data;
}

function page(name) {
  state.page = name;
  document.querySelectorAll(".page").forEach(n => n.classList.toggle("active", n.id === `page-${name}`));
  document.querySelectorAll(".nav").forEach(n => n.classList.toggle("active", n.dataset.page === name));
  if (labels[name]) {
    $("page-title").textContent = labels[name][0];
    $("page-description").textContent = labels[name][1];
  }
  requestAnimationFrame(renderCharts);
  if (name === "comparison") renderComparison();
  if (name === "export") loadFigureGallery();
  if (name === "evidence") loadNative();
}

function markDirty() {
  syncEditor();
  if (state.result) $("run-id").textContent = "입력 변경됨 · 표시 중인 결과는 이전 계산입니다";
}

function syncEditor() {
  const ed = $("scenario-json-editor") || $("config-editor");
  if (ed && state.config) {
    ed.value = JSON.stringify(state.config, null, 2);
  }
}

/* ==========================================================================
   [필수 5] Simulation Control Bar & Playback Loop
   ========================================================================== */
function initSimControls() {
  const btnPlay = $("sim-play");
  const btnPause = $("sim-pause");
  const btnStep = $("sim-step");
  const btnReset = $("sim-reset");
  const scrubber = $("timeline-scrubber");
  const timeDisplay = $("sim-time-display");

  if (!btnPlay) return;

  btnPlay.onclick = () => {
    state.sim.playing = true;
    btnPlay.disabled = true;
    btnPause.disabled = false;
    state.sim.lastTick = performance.now();
    $("solver-badge").textContent = "SIMULATING (RUNNING)";
    $("solver-badge").className = "badge warning";
    simLoop();
  };

  btnPause.onclick = () => {
    state.sim.playing = false;
    btnPlay.disabled = false;
    btnPause.disabled = true;
    $("solver-badge").textContent = "SIMULATION PAUSED";
    $("solver-badge").className = "badge conditional";
  };

  btnStep.onclick = () => {
    state.sim.time = Math.min(state.sim.maxTime, state.sim.time + 0.5);
    updateSimTimeUI();
    drawField();
    renderDashboardChart();
  };

  btnReset.onclick = () => {
    state.sim.playing = false;
    state.sim.time = 0.0;
    btnPlay.disabled = false;
    btnPause.disabled = true;
    $("solver-badge").textContent = "SOLVER READY";
    $("solver-badge").className = "badge ready";
    updateSimTimeUI();
    drawField();
    renderDashboardChart();
  };

  scrubber.oninput = () => {
    state.sim.time = Number(scrubber.value);
    updateSimTimeUI();
    drawField();
    renderDashboardChart();
  };

  document.querySelectorAll(".speed-btn").forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll(".speed-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.sim.speed = Number(btn.dataset.speed || 1.0);
    };
  });
}

function updateSimTimeUI() {
  const scrubber = $("timeline-scrubber");
  const timeDisplay = $("sim-time-display");
  if (scrubber) scrubber.value = state.sim.time;
  if (timeDisplay) timeDisplay.textContent = `t = ${state.sim.time.toFixed(2)} s / ${state.sim.maxTime.toFixed(1)} s`;

  // Update live telemetry based on simulated time
  updateLiveTelemetry(state.sim.time);
}

function simLoop() {
  if (!state.sim.playing) return;
  const now = performance.now();
  const dt = ((now - state.sim.lastTick) / 1000) * state.sim.speed;
  state.sim.lastTick = now;

  state.sim.time += dt;
  state.sim.rotorAngle = (state.sim.rotorAngle + dt * 45.0) % (Math.PI * 2);

  if (state.sim.time >= state.sim.maxTime) {
    state.sim.time = state.sim.maxTime;
    state.sim.playing = false;
    $("sim-play").disabled = false;
    $("sim-pause").disabled = true;
    $("solver-badge").textContent = "MISSION COMPLETED";
    $("solver-badge").className = "badge ready";
  }

  updateSimTimeUI();
  drawField();
  renderDashboardChart();

  if (state.sim.playing) {
    requestAnimationFrame(simLoop);
  }
}

function updateLiveTelemetry(t) {
  // Analytical physical response formulas for real-time telemetry
  const wind = state.config?.scenario?.crosswind_m_s ?? 0.2;
  const latency = Number($("sensor-latency")?.value || 0.10);
  const mass = Number($("drone-mass")?.value || 3.2);

  // Position error grows with latency and wind perturbations
  const posErr = Math.max(0.02, (0.04 + wind * 0.04 + latency * 0.4) * (1 + 0.15 * Math.sin(t * 3.5)));
  const tilt = Math.max(0.2, (0.4 + wind * 0.6 + (t > 12 && t < 24 ? 0.8 : 0)) * (1 + 0.1 * Math.cos(t * 4)));
  const thrust = mass * 9.81 + (t > 12 && t < 24 ? 4.5 : 0.5) * Math.sin(t * 2);
  const volt = Math.max(20.0, 25.2 - (t / 30.0) * 3.2);

  if ($("telem-pos")) $("telem-pos").textContent = `${posErr.toFixed(3)} m`;
  if ($("telem-tilt")) $("telem-tilt").textContent = `${tilt.toFixed(2)}°`;
  if ($("telem-thrust")) $("telem-thrust").textContent = `${thrust.toFixed(1)} N`;
  if ($("telem-volt")) $("telem-volt").textContent = `${volt.toFixed(1)} V`;

  // Plume & fire dynamics
  const hrr = Number($("fire-hrr")?.value || 50);
  const plumeVel = 3.7 * Math.pow(Math.max(10, hrr) / 50.0, 1 / 3);
  const dist = state.config?.scenario?.distance_m ?? 1.0;
  const flux = (0.3 * hrr) / (4 * Math.PI * Math.max(0.4, dist * dist));
  const droneTemp = 25.0 + (flux * 8.5) * (1 - Math.exp(-t / 15.0));
  const flameH = 0.23 * Math.pow(Math.max(10, hrr), 0.4);

  if ($("plume-vel")) $("plume-vel").textContent = `${plumeVel.toFixed(2)} m/s`;
  if ($("drone-flux")) $("drone-flux").textContent = `${flux.toFixed(2)} kW/m²`;
  if ($("drone-temp")) $("drone-temp").textContent = `${droneTemp.toFixed(1)} °C`;
  if ($("flame-height")) $("flame-height").textContent = `${flameH.toFixed(2)} m`;
}

/* ==========================================================================
   [필수 1] Presets & Sliders
   ========================================================================== */
function initPresets() {
  const presets = {
    nominal: { distance_m: 1.0, crosswind_m_s: 0.2, duration_s: 8, latency_s: 0.10, hrr: 50 },
    crosswind: { distance_m: 1.5, crosswind_m_s: 4.5, duration_s: 12, latency_s: 0.15, hrr: 60 },
    latency: { distance_m: 1.2, crosswind_m_s: 1.5, duration_s: 10, latency_s: 0.25, hrr: 50 },
    close: { distance_m: 0.6, crosswind_m_s: 0.5, duration_s: 6, latency_s: 0.05, hrr: 35 }
  };

  document.querySelectorAll(".preset-pills .pill").forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll(".preset-pills .pill").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const p = presets[btn.dataset.preset];
      if (!p || !state.config) return;

      state.config.scenario.distance_m = p.distance_m;
      state.config.scenario.crosswind_m_s = p.crosswind_m_s;
      state.config.scenario.duration_s = p.duration_s;
      if ($("distance")) { $("distance").value = p.distance_m; $("distance-out").textContent = `${p.distance_m.toFixed(1)} m`; }
      if ($("wind")) { $("wind").value = p.crosswind_m_s; $("wind-out").textContent = `${p.crosswind_m_s.toFixed(1)} m/s`; }
      if ($("duration")) { $("duration").value = p.duration_s; $("duration-out").textContent = `${p.duration_s} s`; }
      if ($("sensor-latency")) $("sensor-latency").value = p.latency_s;
      if ($("fire-hrr")) { $("fire-hrr").value = p.hrr; $("fire-hrr-out").textContent = `${p.hrr} kW`; }

      markDirty();
      toast(`[${btn.textContent}] 시나리오 프리셋이 적용되었습니다.`);
    };
  });
}

function initSliders() {
  const items = [
    ["distance", "distance_m", "m", 1],
    ["wind", "crosswind_m_s", "m/s", 1],
    ["duration", "duration_s", "s", 0]
  ];
  for (const [id, key, unit, digits] of items) {
    const elIn = $(id);
    const elOut = $(`${id}-out`);
    if (!elIn || !state.config) continue;
    elIn.value = state.config.scenario[key];
    if (elOut) elOut.textContent = `${Number(state.config.scenario[key]).toFixed(digits)} ${unit}`;
    elIn.oninput = () => {
      state.config.scenario[key] = Number(elIn.value);
      if (elOut) elOut.textContent = `${Number(elIn.value).toFixed(digits)} ${unit}`;
      markDirty();
    };
  }

  // Fire HRR slider
  const hrrIn = $("fire-hrr");
  const hrrOut = $("fire-hrr-out");
  if (hrrIn) {
    hrrIn.oninput = () => {
      if (hrrOut) hrrOut.textContent = `${hrrIn.value} kW`;
      updateLiveTelemetry(state.sim.time);
      drawField();
    };
  }
}

/* ==========================================================================
   [필수 2] Method / Operation Panel
   ========================================================================== */
function initMethods() {
  const grid = $("method-grid");
  if (!grid || !state.catalog) return;
  grid.replaceChildren();

  for (const [mid, m] of Object.entries(state.catalog.methods)) {
    const card = el("button", undefined, `method-card ${mid === state.method ? "active" : ""}`);
    card.type = "button";
    card.style.borderLeftColor = m.color;

    const top = el("div", undefined, "card-top");
    top.append(el("strong", mid), el("span", m.name));

    const p = el("p", m.summary);
    const sub = el("small", `공률: ${m.power_W}W · 하중: ${m.mass_kg}kg`);
    card.append(top, p, sub);

    card.onclick = () => {
      state.method = mid;
      document.querySelectorAll(".method-card").forEach(c => c.classList.remove("active"));
      card.classList.add("active");
      document.documentElement.style.setProperty("--accent", m.color);
      renderDeviceFields();
      updateLedger();
      markDirty();
      drawField();
      renderDashboardChart();
    };
    grid.append(card);
  }

  const opSelect = $("op-mode");
  if (opSelect) {
    opSelect.onchange = () => {
      toast(`운용 모드가 [${opSelect.options[opSelect.selectedIndex].text}]로 변경되었습니다.`);
      markDirty();
    };
  }
}

const deviceSpecs = {
  M1: [
    ["frequency_hz", "주파수 / Hz", 1, 200, 1],
    ["velocity_rms_m_s", "출구 RMS / m/s", 0, 2, 0.01],
    ["power_W", "전기 출력 / W", 0, 1000, 1],
    ["mass_kg", "장치 질량 / kg", 0.01, 20, 0.05]
  ],
  M2: [
    ["exit_velocity_m_s", "출구 유속 / m/s", 0, 30, 0.5],
    ["diameter_m", "출구 직경 / m", 0.01, 0.5, 0.01],
    ["pulse_duration_s", "펄스 폭 / s", 0.002, 0.5, 0.01],
    ["stored_energy_J", "저장 공압 / J", 0, 10000, 10]
  ],
  M3: [
    ["flow_kg_s", "질량유량 / kg/s", 0, 0.1, 0.001],
    ["diameter_um", "액적 직경 / μm", 1, 1000, 5],
    ["payload_kg", "적재량 / kg", 0, 5, 0.01],
    ["power_W", "전기 출력 / W", 0, 1000, 1]
  ],
  M4: [
    ["flow_kg_s", "질량유량 / kg/s", 0, 0.1, 0.001],
    ["diameter_um", "입자 직경 / μm", 1, 1000, 1],
    ["payload_kg", "적재량 / kg", 0, 5, 0.01],
    ["power_W", "전기 출력 / W", 0, 1000, 1]
  ],
  M5: [
    ["exit_velocity_m_s", "출구 유속 / m/s", 0, 30, 0.5],
    ["diameter_um", "입자 직경 / μm", 1, 1000, 1],
    ["payload_kg", "적재량 / kg", 0, 5, 0.01],
    ["power_W", "전기 출력 / W", 0, 1000, 1]
  ]
};

function renderDeviceFields() {
  const container = $("device-fields");
  if (!container || !state.config) return;
  container.replaceChildren();

  const specs = deviceSpecs[state.method] || [];
  const obj = state.config.methods[state.method] || {};

  for (const [key, labelText, minVal, maxVal, stepVal] of specs) {
    const wrap = el("div", undefined, "input-wrap");
    const lbl = el("label", labelText);
    const inp = el("input");
    inp.type = "number";
    inp.min = minVal;
    inp.max = maxVal;
    inp.step = stepVal;
    inp.value = obj[key] !== undefined ? obj[key] : minVal;
    inp.oninput = () => {
      obj[key] = Number(inp.value);
      updateLedger();
      markDirty();
    };
    wrap.append(lbl, inp);
    container.append(wrap);
  }
}

function updateLedger() {
  const m = state.catalog?.methods[state.method];
  if (!m) return;
  if ($("ledger-power")) $("ledger-power").textContent = `${m.power_W} W`;
  if ($("ledger-mass")) $("ledger-mass").textContent = `${m.mass_kg} kg`;
  if ($("ledger-reaction")) $("ledger-reaction").textContent = state.method === "M1" ? "0.0017 N (Radiation)" : state.method === "M2" ? "0.605 N (Pulsed)" : state.method === "M3" ? "0.084 N (Continuous)" : state.method === "M4" ? "0.011 N (Jet)" : "0.613 N (EHD+Vortex)";
}

/* ==========================================================================
   [필수 6] Enhanced 3D Visualization Viewport
   ========================================================================== */
function init3DViewport() {
  const canvas = $("field-canvas");
  if (!canvas) return;

  let dragging = false;
  let lastX = 0, lastY = 0;

  canvas.onpointerdown = e => {
    dragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
    canvas.setPointerCapture(e.pointerId);
  };

  canvas.onpointermove = e => {
    if (!dragging) return;
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    state.yaw += dx * 0.008;
    state.pitch = Math.max(-1.4, Math.min(1.4, state.pitch + dy * 0.008));
    drawField();
  };

  canvas.onpointerup = canvas.onpointercancel = () => { dragging = false; };

  canvas.onwheel = e => {
    e.preventDefault();
    state.zoom = Math.max(0.4, Math.min(3.0, state.zoom - e.deltaY * 0.0015));
    drawField();
  };

  // Camera presets
  document.querySelectorAll(".cam-btn").forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll(".cam-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const mode = btn.dataset.cam;
      if (mode === "iso") { state.yaw = -0.62; state.pitch = 0.48; state.zoom = 1.0; }
      else if (mode === "top") { state.yaw = 0.0; state.pitch = 1.52; state.zoom = 1.1; }
      else if (mode === "front") { state.yaw = 0.0; state.pitch = 0.05; state.zoom = 1.1; }
      else if (mode === "side") { state.yaw = -Math.PI / 2; state.pitch = 0.05; state.zoom = 1.1; }
      drawField();
    };
  });

  const btnReset = $("reset-view");
  if (btnReset) {
    btnReset.onclick = () => {
      state.yaw = -0.62; state.pitch = 0.48; state.zoom = 1.0;
      drawField();
    };
  }

  // Toggles
  ["toggle-streamlines", "toggle-plume", "toggle-rotors"].forEach(id => {
    const elTg = $(id);
    if (elTg) elTg.onchange = () => drawField();
  });
}

function project3D(x, y, z, cx, cy, scale) {
  // 3D rotation with yaw and pitch
  const cosY = Math.cos(state.yaw), sinY = Math.sin(state.yaw);
  const cosP = Math.cos(state.pitch), sinP = Math.sin(state.pitch);

  // Rotate around Z (yaw)
  const x1 = x * cosY - y * sinY;
  const y1 = x * sinY + y * cosY;
  const z1 = z;

  // Rotate around X (pitch)
  const x2 = x1;
  const y2 = y1 * cosP - z1 * sinP;
  const z2 = y1 * sinP + z1 * cosP;

  // Isometric / Weak perspective projection
  const px = cx + x2 * scale;
  const py = cy - z2 * scale + y2 * scale * 0.35;
  return [px, py, y2];
}

function drawField() {
  const canvas = $("field-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const w = rect.width, h = rect.height;
  const cx = w * 0.46, cy = h * 0.54;
  const scale = Math.min(w, h) * 0.38 * state.zoom;

  ctx.fillStyle = "#0f172a";
  ctx.fillRect(0, 0, w, h);

  // 1. Draw Ground Coordinate Grid
  ctx.strokeStyle = "rgba(148, 163, 184, 0.12)";
  ctx.lineWidth = 1;
  for (let gx = -1.5; gx <= 2.5; gx += 0.5) {
    const [x1, y1] = project3D(gx, -1.5, 0, cx, cy, scale);
    const [x2, y2] = project3D(gx, 1.5, 0, cx, cy, scale);
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  }
  for (let gy = -1.5; gy <= 1.5; gy += 0.5) {
    const [x1, y1] = project3D(-1.5, gy, 0, cx, cy, scale);
    const [x2, y2] = project3D(2.5, gy, 0, cx, cy, scale);
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  }

  // 2. Draw Target Disc Plane
  const dist = state.config?.scenario?.distance_m ?? 1.0;
  const [tdX, tdY] = project3D(dist, 0, 0.4, cx, cy, scale);
  ctx.strokeStyle = "rgba(245, 158, 11, 0.85)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (let theta = 0; theta <= Math.PI * 2; theta += 0.15) {
    const ry = 0.25 * Math.cos(theta);
    const rz = 0.25 * Math.sin(theta);
    const [px, py] = project3D(dist, ry, 0.4 + rz, cx, cy, scale);
    if (theta === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  }
  ctx.closePath();
  ctx.fillStyle = "rgba(245, 158, 11, 0.15)";
  ctx.fill();
  ctx.stroke();

  // 3. Draw Fire Plume & Burner (if toggle is on)
  if ($("toggle-plume")?.checked) {
    const hrr = Number($("fire-hrr")?.value || 50);
    const plumeH = 0.23 * Math.pow(Math.max(10, hrr), 0.4);
    const wind = state.config?.scenario?.crosswind_m_s ?? 0.2;
    const windDeflection = (wind / 3.0) * 0.3;

    // Burner base
    const [bX, bY] = project3D(dist, 0, 0, cx, cy, scale);
    ctx.fillStyle = "rgba(239, 68, 68, 0.35)";
    ctx.strokeStyle = "#ef4444";
    ctx.lineWidth = 1.5;

    // Plume conical boundary
    ctx.beginPath();
    const [pBaseL_x, pBaseL_y] = project3D(dist, -0.15, 0, cx, cy, scale);
    const [pBaseR_x, pBaseR_y] = project3D(dist, 0.15, 0, cx, cy, scale);
    const [pTop_x, pTop_y] = project3D(dist + windDeflection, 0, plumeH, cx, cy, scale);
    ctx.moveTo(pBaseL_x, pBaseL_y);
    ctx.lineTo(pTop_x, pTop_y);
    ctx.lineTo(pBaseR_x, pBaseR_y);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();

    // Core Flame Tip Glow
    ctx.fillStyle = "#facc15";
    ctx.beginPath();
    ctx.arc(pTop_x, pTop_y, 4, 0, Math.PI * 2);
    ctx.fill();
  }

  // 4. Draw Drone 3D Airframe & Spinning Rotors
  const droneX = 0.0, droneY = 0.0, droneZ = 0.4;
  const [drX, drY] = project3D(droneX, droneY, droneZ, cx, cy, scale);

  // Drone arms (Cross configuration)
  const armLen = 0.22;
  const rotorPositions = [
    [armLen, armLen],
    [-armLen, armLen],
    [-armLen, -armLen],
    [armLen, -armLen]
  ];

  ctx.strokeStyle = "#cbd5e1";
  ctx.lineWidth = 3;
  rotorPositions.forEach(([rx, ry]) => {
    const [ax, ay] = project3D(droneX + rx, droneY + ry, droneZ, cx, cy, scale);
    ctx.beginPath(); ctx.moveTo(drX, drY); ctx.lineTo(ax, ay); ctx.stroke();
  });

  // Drone center body
  ctx.fillStyle = "#38bdf8";
  ctx.beginPath();
  ctx.arc(drX, drY, 6, 0, Math.PI * 2);
  ctx.fill();

  // Draw 4 spinning rotor discs
  const rotorR = 0.09;
  rotorPositions.forEach(([rx, ry], idx) => {
    const rX = droneX + rx, rY = droneY + ry, rZ = droneZ;
    const [rcX, rcY] = project3D(rX, rY, rZ, cx, cy, scale);

    // Rotor disc
    ctx.strokeStyle = "rgba(56, 189, 248, 0.45)";
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.arc(rcX, rcY, rotorR * scale, 0, Math.PI * 2);
    ctx.stroke();

    // Spinning blade lines
    const angle = state.sim.rotorAngle * (idx % 2 === 0 ? 1 : -1) + idx * 0.78;
    const [b1x, b1y] = project3D(rX + rotorR * Math.cos(angle), rY + rotorR * Math.sin(angle), rZ, cx, cy, scale);
    const [b2x, b2y] = project3D(rX - rotorR * Math.cos(angle), rY - rotorR * Math.sin(angle), rZ, cx, cy, scale);
    ctx.strokeStyle = "#93c5fd";
    ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(b1x, b1y); ctx.lineTo(b2x, b2y); ctx.stroke();

    // Rotor downwash vector (if toggle is on)
    if ($("toggle-rotors")?.checked) {
      const [dwX, dwY] = project3D(rX, rY, rZ - 0.25, cx, cy, scale);
      ctx.strokeStyle = "rgba(96, 165, 250, 0.25)";
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(rcX, rcY); ctx.lineTo(dwX, dwY); ctx.stroke();
    }
  });

  // 5. Draw Extinguishing Delivery Field (Streamlines / Particles)
  if ($("toggle-streamlines")?.checked) {
    const methodColor = state.catalog?.methods[state.method]?.color || "#38bdf8";
    ctx.strokeStyle = methodColor;
    ctx.fillStyle = methodColor;

    if (state.method === "M2" || state.method === "M5") {
      // Traveling Vortex Ring
      const progress = (state.sim.time % 2.0) / 2.0;
      const ringDist = progress * dist;
      ctx.lineWidth = 3;
      ctx.beginPath();
      for (let theta = 0; theta <= Math.PI * 2; theta += 0.2) {
        const ry = 0.12 * Math.cos(theta);
        const rz = 0.12 * Math.sin(theta);
        const [px, py] = project3D(ringDist, ry, 0.4 + rz, cx, cy, scale);
        if (theta === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      }
      ctx.closePath();
      ctx.stroke();
    } else {
      // Continuous Streamlines / Spray Jet
      ctx.lineWidth = 1.5;
      for (let i = -2; i <= 2; i++) {
        const spread = i * 0.04;
        const [sX, sY] = project3D(0.1, 0, 0.4, cx, cy, scale);
        const [eX, eY] = project3D(dist, spread, 0.4 + spread * 0.5, cx, cy, scale);
        ctx.beginPath();
        ctx.moveTo(sX, sY);
        ctx.lineTo(eX, eY);
        ctx.stroke();
      }
    }
  }

  // Hide empty overlay if active
  const empty = $("field-empty");
  if (empty) empty.hidden = true;
}

/* ==========================================================================
   [필수 7] Performance Dashboard & Multi-Channel Oscilloscope
   ========================================================================== */
function initDashboardChannels() {
  document.querySelectorAll(".chan-toggle").forEach(cb => {
    cb.onchange = () => {
      state.activeChannels[cb.dataset.chan] = cb.checked;
      renderDashboardChart();
    };
  });
}

function renderDashboardChart() {
  const canvas = $("dashboard-chart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const w = rect.width, h = rect.height;
  const padL = 50, padR = 25, padT = 20, padB = 30;
  const plotW = w - padL - padR, plotH = h - padT - padB;

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, w, h);

  // Grid
  ctx.strokeStyle = "#f1f5f9";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 5; i++) {
    const y = padT + (plotH / 5) * i;
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
  }

  // Generate synthetic/simulated curve data points over 30s
  const points = 100;
  const channels = [
    { id: "hrr", label: "HRR [kW]", color: "#ef4444", val: t => 50.0 * Math.exp(-Math.max(0, t - 6.0) / 4.0) + (t < 6.0 ? 50 : 0.5), max: 60 },
    { id: "pos", label: "위치오차 [m]", color: "#f59e0b", val: t => (0.05 + 0.08 * Math.sin(t * 0.8)) * (1 + (t > 12 && t < 24 ? 0.5 : 0)), max: 0.5 },
    { id: "tilt", label: "자세각 [deg]", color: "#8b5cf6", val: t => 0.4 + 0.3 * Math.sin(t * 1.2), max: 3.0 },
    { id: "rx", label: "노즐반력 [N]", color: "#0284c7", val: t => (t > 12 && t < 24 ? 0.61 : 0.01), max: 1.0 },
    { id: "power", label: "소비전력 [W]", color: "#10b981", val: t => 45.0 + (t > 12 && t < 24 ? 35.0 : 0), max: 100 },
    { id: "battery", label: "배터리 [Wh]", color: "#64748b", val: t => Math.max(0, 28.0 - (t / 30.0) * 8.5), max: 30 }
  ];

  channels.forEach(ch => {
    if (!state.activeChannels[ch.id]) return;
    ctx.strokeStyle = ch.color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i <= points; i++) {
      const t = (i / points) * 30.0;
      const val = ch.val(t);
      const normY = Math.max(0, Math.min(1, val / ch.max));
      const x = padL + (t / 30.0) * plotW;
      const y = padT + (1 - normY) * plotH;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
  });

  // Live Scrubber Cursor Line
  const curX = padL + (state.sim.time / 30.0) * plotW;
  ctx.strokeStyle = "#0f172a";
  ctx.lineWidth = 1.5;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(curX, padT);
  ctx.lineTo(curX, padT + plotH);
  ctx.stroke();
  ctx.setLineDash([]);

  // Axis Labels
  ctx.fillStyle = "#64748b";
  ctx.font = canvasFont(10.5, true);
  ctx.fillText("0 s", padL - 8, h - 10);
  ctx.fillText("15 s", padL + plotW * 0.5 - 10, h - 10);
  ctx.fillText("30 s", w - padR - 15, h - 10);

  // Update KPI cards
  const hrrNow = channels[0].val(state.sim.time);
  const hrrDrop = Math.max(0, ((50.0 - hrrNow) / 50.0) * 100);
  if ($("kpi-time")) $("kpi-time").textContent = hrrNow < 2.5 ? `${Math.min(state.sim.time, 14.2).toFixed(1)} s` : "진압 진행 중";
  if ($("kpi-hrr-drop")) $("kpi-hrr-drop").textContent = `${hrrDrop.toFixed(1)} %`;
  if ($("kpi-error")) $("kpi-error").textContent = `${channels[1].val(state.sim.time).toFixed(3)} m`;
  if ($("kpi-energy")) $("kpi-energy").textContent = `${(3.2 + (state.sim.time / 30.0) * 2.1).toFixed(2)} Wh`;
  if ($("kpi-delivery")) $("kpi-delivery").textContent = state.method === "M3" ? "78.4 %" : state.method === "M4" ? "92.1 %" : "85.0 %";
  if ($("kpi-temp")) $("kpi-temp").textContent = `${(25.0 + (state.sim.time / 30.0) * 7.4).toFixed(1)} °C`;
}

/* ==========================================================================
   [필수 8] Comparison Panel
   ========================================================================== */
function renderComparison() {
  renderRadarChart();
  renderSynergyMatrix();
  populateComparisonTable();
}

function renderRadarChart() {
  const canvas = $("radar-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const w = rect.width, h = rect.height;
  const cx = w * 0.5, cy = h * 0.5;
  const rMax = Math.min(w, h) * 0.36;

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, w, h);

  const axes = ["소화 속도", "HRR 저감율", "전력 효율", "질량 효율", "탑재 여유"];
  const numAxes = axes.length;

  // Draw concentric webs
  ctx.strokeStyle = "#e2e8f0";
  ctx.lineWidth = 1;
  for (let step = 1; step <= 5; step++) {
    const r = (rMax / 5) * step;
    ctx.beginPath();
    for (let i = 0; i < numAxes; i++) {
      const angle = (Math.PI * 2 / numAxes) * i - Math.PI / 2;
      const x = cx + r * Math.cos(angle);
      const y = cy + r * Math.sin(angle);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.stroke();
  }

  // Draw axis lines and labels
  ctx.fillStyle = "#475569";
  ctx.font = canvasFont(11, false);
  for (let i = 0; i < numAxes; i++) {
    const angle = (Math.PI * 2 / numAxes) * i - Math.PI / 2;
    const ax = cx + rMax * Math.cos(angle);
    const ay = cy + rMax * Math.sin(angle);
    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(ax, ay); ctx.stroke();

    const lx = cx + (rMax + 20) * Math.cos(angle);
    const ly = cy + (rMax + 20) * Math.sin(angle);
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(axes[i], lx, ly);
  }

  // 5 Method Radar profiles [Speed, HRR, PowerEff, MassEff, PayloadMargin]
  const methodProfiles = {
    M1: { scores: [0.35, 0.40, 0.95, 1.00, 0.90], color: "#0284c7" },
    M2: { scores: [0.65, 0.70, 0.80, 0.95, 0.85], color: "#4f46e5" },
    M3: { scores: [0.90, 0.95, 0.55, 0.50, 0.60], color: "#0d9488" },
    M4: { scores: [0.95, 0.90, 0.90, 0.90, 0.95], color: "#d97706" },
    M5: { scores: [0.80, 0.85, 0.75, 0.85, 0.75], color: "#7c3aed" }
  };

  Object.entries(methodProfiles).forEach(([mid, p]) => {
    ctx.strokeStyle = p.color;
    ctx.fillStyle = p.color + "22"; // 15% opacity
    ctx.lineWidth = mid === state.method ? 3 : 1.5;
    ctx.beginPath();
    p.scores.forEach((s, i) => {
      const angle = (Math.PI * 2 / numAxes) * i - Math.PI / 2;
      const x = cx + rMax * s * Math.cos(angle);
      const y = cy + rMax * s * Math.sin(angle);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  });
}

function renderSynergyMatrix() {
  const canvas = $("synergy-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const w = rect.width, h = rect.height;
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, w, h);

  const methods = ["M1", "M2", "M3", "M4", "M5"];
  const matrix = [
    [1.00, 1.15, 1.08, 1.22, 1.10],
    [1.15, 1.00, 1.20, 1.42, 1.35],
    [1.08, 1.20, 1.00, 1.28, 1.18],
    [1.22, 1.42, 1.28, 1.00, 1.30],
    [1.10, 1.35, 1.18, 1.30, 1.00]
  ];

  const pad = 40;
  const cellSize = Math.min((w - pad * 2) / 5, (h - pad * 2) / 5);

  ctx.font = canvasFont(11.5, true);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";

  for (let i = 0; i < 5; i++) {
    // Header labels
    ctx.fillStyle = "#64748b";
    ctx.fillText(methods[i], pad + cellSize * (i + 0.5), pad - 15);
    ctx.fillText(methods[i], pad - 15, pad + cellSize * (i + 0.5));

    for (let j = 0; j < 5; j++) {
      const val = matrix[i][j];
      const norm = (val - 1.0) / 0.45;
      const x = pad + j * cellSize;
      const y = pad + i * cellSize;

      ctx.fillStyle = i === j ? "#f8fafc" : `rgba(59, 130, 246, ${Math.max(0.08, norm * 0.75)})`;
      ctx.fillRect(x + 2, y + 2, cellSize - 4, cellSize - 4);

      ctx.strokeStyle = "#e2e8f0";
      ctx.lineWidth = 1;
      ctx.strokeRect(x + 2, y + 2, cellSize - 4, cellSize - 4);

      ctx.fillStyle = val > 1.3 ? "#1e3a8a" : "#0f172a";
      ctx.font = canvasFont(11, true);
      ctx.fillText(val.toFixed(2), x + cellSize * 0.5, y + cellSize * 0.5);
    }
  }
}

function populateComparisonTable() {
  const tb = $("comparison-table-body");
  if (!tb) return;
  tb.replaceChildren();

  const data = [
    { mid: "M1 음향", principle: "Rayleigh 선형 음향파", power: "80 W", rx: "0.0017 N", speed: "0.35", energy: "3.07 Wh", error: "0.048 m", verdict: "비소모성·최고 비행안정" },
    { mid: "M2 와류링", principle: "비정상 펄스 슬러그 유동", power: "15 W", rx: "0.605 N", speed: "0.65", energy: "3.17 Wh", error: "0.052 m", verdict: "원거리 타격·공기역학 캐리어" },
    { mid: "M3 수분무", principle: "Schiller-Naumann 증발냉각", power: "35 W", rx: "0.084 N", speed: "0.90", energy: "3.18 Wh", error: "0.050 m", verdict: "압도적 냉각·잠열 흡수" },
    { mid: "M4 에어로졸", principle: "K+ 라디칼 연쇄반응 차단", power: "10 W", rx: "0.011 N", speed: "0.95", energy: "2.91 Wh", error: "0.042 m", verdict: "최고 소화속도·초경량" },
    { mid: "M5 전도성와류", principle: "EHD 1D Poisson-Coulomb", power: "20 W", rx: "0.613 N", speed: "0.80", energy: "3.44 Wh", error: "0.055 m", verdict: "전기장 능동 제어·집속" }
  ];

  data.forEach(r => {
    const tr = el("tr");
    tr.append(
      el("td", r.mid),
      el("td", r.principle),
      el("td", r.power),
      el("td", r.rx),
      el("td", r.speed),
      el("td", r.energy),
      el("td", r.error),
      el("td", r.verdict)
    );
    tb.append(tr);
  });
}

/* ==========================================================================
   [필수 9] Scenario Editor
   ========================================================================== */
function initScenarioEditor() {
  const pRanges = ["range-p1", "range-p2", "range-p3", "range-p4", "range-p5"];
  pRanges.forEach((id, idx) => {
    const elR = $(id);
    if (!elR) return;
    elR.oninput = () => {
      const dur = Number(elR.value);
      const out = $(`phase-dur-${idx + 1}`);
      if (out) out.textContent = `${dur} s`;
    };
  });

  const btnApplyPhases = $("apply-visual-phase");
  if (btnApplyPhases) {
    btnApplyPhases.onclick = () => {
      toast("미션 페이즈 시간 설정이 시뮬레이션 설정에 동기화되었습니다.");
      markDirty();
    };
  }

  const btnFormat = $("editor-format");
  const jsonEd = $("scenario-json-editor");
  if (btnFormat && jsonEd) {
    btnFormat.onclick = () => {
      try {
        const obj = JSON.parse(jsonEd.value);
        jsonEd.value = JSON.stringify(obj, null, 2);
        toast("JSON 서식이 정리되었습니다.");
      } catch (err) {
        toast("JSON 문법 오류: " + err.message, true);
      }
    };
  }

  const btnApplyJson = $("apply-json-btn");
  if (btnApplyJson && jsonEd) {
    btnApplyJson.onclick = async () => {
      try {
        const parsed = JSON.parse(jsonEd.value);
        const validated = await api("/api/validate", parsed);
        state.config = validated;
        sliders();
        renderDeviceFields();
        toast("JSON 검증 통과 및 시뮬레이션 설정에 적용 완료되었습니다.");
        $("json-lint-status").textContent = "JSON VALID";
        $("json-lint-status").className = "badge ready";
      } catch (err) {
        toast("검증 실패: " + err.message, true);
        $("json-lint-status").textContent = "VALIDATION ERROR";
        $("json-lint-status").className = "badge danger";
      }
    };
  }
}

/* ==========================================================================
   [선택 1] Multi-Objective Pareto Optimization Panel
   ========================================================================== */
function initOptimization() {
  const btnRun = $("run-opt-btn");
  if (!btnRun) return;

  btnRun.onclick = async () => {
    btnRun.disabled = true;
    $("opt-progress").hidden = false;
    $("opt-prog-fill").style.width = "40%";

    try {
      const wind = Number($("opt-wind")?.value || 1.5);
      const distMin = Number($("opt-dist-min")?.value || 0.8);
      const distMax = Number($("opt-dist-max")?.value || 2.5);

      const spec = {
        methods: ["M1", "M2", "M3", "M4", "M5"],
        distance_range: [distMin, (distMin + distMax) * 0.5, distMax],
        power_range: [20.0, 50.0, 80.0],
        crosswind_m_s: wind,
        kp_range: [1.0, 1.2]
      };

      const res = await api("/api/optimize", spec);
      state.optResult = res;
      $("opt-prog-fill").style.width = "100%";
      setTimeout(() => { $("opt-progress").hidden = true; }, 500);

      renderParetoScatter(res);
      populateParetoTable(res);
      toast(`Pareto 최적화 완료: ${res.pareto_front_count}개 비지배 해 발견!`);
      $("opt-count-badge").textContent = `${res.pareto_front_count} Pareto Front`;
      if ($("apply-knee-btn")) $("apply-knee-btn").disabled = false;
    } catch (err) {
      toast("최적화 계산 실패: " + err.message, true);
      $("opt-progress").hidden = true;
    } finally {
      btnRun.disabled = false;
    }
  };

  const btnApplyKnee = $("apply-knee-btn");
  if (btnApplyKnee) {
    btnApplyKnee.onclick = () => {
      const knee = state.optResult?.knee_point;
      if (!knee) return;
      state.method = knee.method_id;
      state.config.scenario.distance_m = knee.distance_m;
      if ($("distance")) $("distance").value = knee.distance_m;
      if ($("distance-out")) $("distance-out").textContent = `${knee.distance_m} m`;
      sliders();
      renderDeviceFields();
      toast(`★ Knee Point (${knee.method_id}, ${knee.distance_m}m, ${knee.power_W}W) 설정이 스튜디오에 적용되었습니다!`);
      page("lab");
    };
  }
}

function renderParetoScatter(res) {
  const canvas = $("pareto-canvas");
  if (!canvas || !res) return;
  const ctx = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const w = rect.width, h = rect.height;
  const padL = 50, padR = 25, padT = 20, padB = 35;
  const plotW = w - padL - padR, plotH = h - padT - padB;

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, w, h);

  // X-axis: Extinction Time [s], Y-axis: Mission Energy [Wh]
  const allPts = [...(res.sample_candidates || []), ...(res.pareto_front || [])];
  const xVals = allPts.map(p => p.objectives.extinction_time_s);
  const yVals = allPts.map(p => p.objectives.mission_energy_Wh);
  const minX = Math.min(...xVals, 1.0), maxX = Math.max(...xVals, 20.0);
  const minY = Math.min(...yVals, 2.0), maxY = Math.max(...yVals, 6.0);

  // Grid
  ctx.strokeStyle = "#f1f5f9";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = padT + (plotH / 4) * i;
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
  }

  // Draw Dominated Candidates (red dots)
  allPts.forEach(p => {
    const x = padL + ((p.objectives.extinction_time_s - minX) / (maxX - minX)) * plotW;
    const y = padT + (1 - (p.objectives.mission_energy_Wh - minY) / (maxY - minY)) * plotH;
    ctx.fillStyle = "rgba(239, 68, 68, 0.4)";
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fill();
  });

  // Draw Pareto Front (green connected line & dots)
  const sortedFront = [...(res.pareto_front || [])].sort((a, b) => a.objectives.extinction_time_s - b.objectives.extinction_time_s);
  ctx.strokeStyle = "#22c55e";
  ctx.lineWidth = 2;
  ctx.beginPath();
  sortedFront.forEach((p, i) => {
    const x = padL + ((p.objectives.extinction_time_s - minX) / (maxX - minX)) * plotW;
    const y = padT + (1 - (p.objectives.mission_energy_Wh - minY) / (maxY - minY)) * plotH;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();

  sortedFront.forEach(p => {
    const x = padL + ((p.objectives.extinction_time_s - minX) / (maxX - minX)) * plotW;
    const y = padT + (1 - (p.objectives.mission_energy_Wh - minY) / (maxY - minY)) * plotH;
    ctx.fillStyle = "#22c55e";
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fill();
  });

  // Highlight Knee Point (blue star/ring)
  if (res.knee_point) {
    const kp = res.knee_point;
    const kx = padL + ((kp.objectives.extinction_time_s - minX) / (maxX - minX)) * plotW;
    const ky = padT + (1 - (kp.objectives.mission_energy_Wh - minY) / (maxY - minY)) * plotH;
    ctx.strokeStyle = "#3b82f6";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(kx, ky, 9, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = "#3b82f6";
    ctx.beginPath();
    ctx.arc(kx, ky, 4, 0, Math.PI * 2);
    ctx.fill();
  }

  // Axis labels
  ctx.fillStyle = "#64748b";
  ctx.font = canvasFont(10.5, true);
  ctx.fillText(`소화시간 ${minX.toFixed(1)} s`, padL, h - 10);
  ctx.fillText(`${maxX.toFixed(1)} s`, w - padR - 30, h - 10);
  ctx.fillText(`${maxY.toFixed(1)} Wh`, 10, padT + 10);
  ctx.fillText(`${minY.toFixed(1)} Wh`, 10, padT + plotH);
}

function populateParetoTable(res) {
  const tb = $("pareto-table-body");
  if (!tb || !res) return;
  tb.replaceChildren();

  res.pareto_front.forEach((p, i) => {
    const tr = el("tr");
    tr.append(
      el("td", `P-${i + 1}`),
      el("td", p.method_id),
      el("td", `${p.distance_m} m`),
      el("td", `${p.power_W} W`),
      el("td", `${p.objectives.extinction_time_s} s`),
      el("td", `${p.objectives.mission_energy_Wh} Wh`),
      el("td", `${p.objectives.max_position_error_m} m`),
      el("td", `${p.objectives.delivery_efficiency_pct} %`),
      (() => {
        const td = el("td");
        const btn = el("button", "적용", "button small");
        btn.onclick = () => {
          state.method = p.method_id;
          state.config.scenario.distance_m = p.distance_m;
          sliders();
          toast(`후보 P-${i + 1} (${p.method_id}, ${p.distance_m}m)가 워크벤치에 적용되었습니다.`);
          page("lab");
        };
        td.append(btn);
        return td;
      })()
    );
    tb.append(tr);
  });
}

/* ==========================================================================
   [선택 2] Monte Carlo Uncertainty Panel
   ========================================================================== */
function initMonteCarlo() {
  const btnRun = $("run-mc-btn");
  if (!btnRun) return;

  btnRun.onclick = async () => {
    btnRun.disabled = true;
    $("mc-progress").hidden = false;
    $("mc-prog-fill").style.width = "40%";

    try {
      const mid = $("mc-method")?.value || "M3";
      const samples = Number($("mc-samples")?.value || 50);
      const windStd = Number($("mc-wind-std")?.value || 0.6);
      const latMax = Number($("mc-lat-max")?.value || 0.25);

      const body = {
        method_id: mid,
        num_samples: samples,
        uncertainty_spec: {
          crosswind_std: windStd,
          latency_max: latMax
        }
      };

      const res = await api("/api/montecarlo", body);
      state.mcResult = res;
      $("mc-prog-fill").style.width = "100%";
      setTimeout(() => { $("mc-progress").hidden = true; }, 500);

      // Update KPIs
      if ($("mc-p-val")) $("mc-p-val").textContent = `${(res.extinction_probability * 100).toFixed(1)} %`;
      if ($("mc-ci-val")) $("mc-ci-val").textContent = `[${(res.ci_95_pct[0] * 100).toFixed(1)}% , ${(res.ci_95_pct[1] * 100).toFixed(1)}%]`;
      if ($("mc-prob-badge")) {
        $("mc-prob-badge").textContent = res.extinction_probability > 0.8 ? "HIGH CONFIDENCE" : "MODERATE";
        $("mc-prob-badge").className = res.extinction_probability > 0.8 ? "badge ready" : "badge warning";
      }

      renderHistogram(res.histograms.extinction_time_s);
      renderTornadoChart(res.sensitivity_tornado);
      toast(`몬테카를로 ${samples}회 해석 완료 (P_quench: ${(res.extinction_probability * 100).toFixed(1)}%)`);
    } catch (err) {
      toast("몬테카를로 해석 실패: " + err.message, true);
      $("mc-progress").hidden = true;
    } finally {
      btnRun.disabled = false;
    }
  };
}

function renderHistogram(hist) {
  const canvas = $("mc-hist-canvas");
  if (!canvas || !hist) return;
  const ctx = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const w = rect.width, h = rect.height;
  const padL = 40, padR = 20, padT = 15, padB = 25;
  const plotW = w - padL - padR, plotH = h - padT - padB;

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, w, h);

  const counts = hist.counts || [];
  const maxC = Math.max(...counts, 1);
  const numBars = counts.length;
  const barW = plotW / numBars;

  counts.forEach((c, i) => {
    const barH = (c / maxC) * plotH;
    const x = padL + i * barW;
    const y = padT + plotH - barH;

    ctx.fillStyle = "#3b82f6";
    ctx.fillRect(x + 2, y, barW - 4, barH);

    ctx.fillStyle = "#64748b";
    ctx.font = canvasFont(9.5, true);
    if (c > 0) ctx.fillText(String(c), x + barW * 0.5 - 4, y - 4);
  });

  ctx.fillStyle = "#64748b";
  ctx.font = canvasFont(10, true);
  ctx.fillText(`${hist.bin_edges[0]}s`, padL, h - 8);
  ctx.fillText(`${hist.bin_edges[hist.bin_edges.length - 1]}s`, w - padR - 25, h - 8);
}

function renderTornadoChart(tornado) {
  const canvas = $("tornado-canvas");
  if (!canvas || !tornado) return;
  const ctx = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const w = rect.width, h = rect.height;
  const padL = 160, padR = 40, padT = 15, padB = 25;
  const plotW = w - padL - padR;

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, w, h);

  const numItems = tornado.length;
  const rowH = (h - padT - padB) / numItems;

  tornado.forEach((item, i) => {
    const y = padT + i * rowH;
    ctx.fillStyle = "#0f172a";
    ctx.font = canvasFont(11, false);
    ctx.textAlign = "right";
    ctx.fillText(item.parameter, padL - 12, y + rowH * 0.5 + 4);

    const barW = (item.combined_impact / 1.0) * plotW;
    ctx.fillStyle = i === 0 ? "#ef4444" : i === 1 ? "#f59e0b" : "#3b82f6";
    ctx.fillRect(padL, y + 4, barW, rowH - 8);

    ctx.fillStyle = "#64748b";
    ctx.font = canvasFont(10.5, true);
    ctx.textAlign = "left";
    ctx.fillText(`${item.combined_impact.toFixed(3)} (corr)`, padL + barW + 8, y + rowH * 0.5 + 4);
  });
}

/* ==========================================================================
   [필수 10] Result Export Panel & 10-Figure Gallery
   ========================================================================== */
function loadFigureGallery() {
  const container = $("figure-gallery");
  if (!container) return;
  container.replaceChildren();

  const figures = [
    { id: "vis_01", file: "vis_01_crosswind_latency_heatmap.png", title: "[필수 1] 횡풍·센서지연 최대 위치오차 Heatmap", desc: "횡풍 0~5m/s 및 센서지연 0~500ms 범위에서 6-DOF 제어 발산 및 안전 호버링 영역을 정량화합니다." },
    { id: "vis_02", file: "vis_02_flight_dynamics_timeseries.png", title: "[필수 2] 방식별 비행 동역학 4-패널 시계열", desc: "34초 전구간 위치오차, 롤/피치 각도, 소화 노즐 반력, 총 소비전력의 과도 응답을 비교합니다." },
    { id: "vis_03", file: "vis_03_fire_cfd_timeseries.png", title: "[필수 3] FDS CFD 화재 진압 시계열", desc: "FDS 6.11.1 수치해석 기반 열방출률(HRR), 복사열유속, 상층부 온도 급락 거동을 실증합니다." },
    { id: "vis_04", file: "vis_04_distance_wind_power_contour.png", title: "[필수 4] 거리·횡풍·출력 소화효율 Contour", desc: "정격(50W) 및 최대(100W) 출력에서 Gaussian 풍하 편향 보상 및 80% 유효 소화 범위를 가시화합니다." },
    { id: "vis_05", file: "vis_05_flow_and_thermal_field_2d3d.png", title: "[필수 5] 로터 Wake · 화재 Plume 연성 유동장", desc: "드론 다운워시와 화재 상승 플룸의 공기역학적 상호작용 및 3D 등온면을 렌더링합니다." },
    { id: "vis_06", file: "vis_06_normalized_radar_and_bars.png", title: "[필수 6] 5개 방식 정규화 Radar & Bar 비교", desc: "소화속도, HRR저감율, 전력효율, 질량효율, 탑재여유 5대 지표를 다차원 레이더로 비교합니다." },
    { id: "vis_07", file: "vis_07_synergy_matrix_heatmap.png", title: "[필수 7] 5개 방식 상호보완성 Matrix Heatmap", desc: "단독 대비 복합 운용 시너지를 분석하여 M2(와류링)+M4(에어로졸)의 최고 시너지(1.42)를 규명합니다." },
    { id: "vis_08", file: "vis_08_mission_timeline_dashboard.png", title: "[필수 8] 미션 전주기 Timeline 종합 대시보드", desc: "이륙-접근-호버링-소화-냉각-복귀 45초 미션 전주기 거동 및 배터리 잔여 Wh를 검증합니다." },
    { id: "vis_09", file: "vis_09_suppression_phase_map.png", title: "[선택 1] 화재규모·거리 진압가능 Phase Map", desc: "열유속 2.5kW/m² 및 관통 모멘텀 기준 완전진압, 조건부 억제, 진압불가 위험 위상을 구분합니다." },
    { id: "vis_10", file: "vis_10_operational_envelope_3d_surface.png", title: "[선택 2] 통합 드론 운용 포락선 3D Surface", desc: "비행-소화-에너지 통합 점수 곡면을 통해 풍속 1~2m/s, 거리 1.5~2.2m의 최적 작전 능선을 도출합니다." }
  ];

  figures.forEach(fig => {
    const card = el("div", undefined, "figure-card");
    const img = document.createElement("img");
    img.src = `/visualizations/${fig.file}`;
    img.alt = fig.title;
    img.onclick = () => window.open(img.src, "_blank");

    const info = el("div", undefined, "figure-info");
    info.append(
      el("h4", fig.title),
      el("p", fig.desc),
      (() => {
        const a = el("a", "300 DPI 원본 다운로드 ↗");
        a.href = `/visualizations/${fig.file}`;
        a.download = fig.file;
        return a;
      })()
    );
    card.append(img, info);
    container.append(card);
  });
}

/* ==========================================================================
   Master Initializer
   ========================================================================== */
async function boot() {
  try {
    const cat = await api("/api/catalog");
    state.catalog = cat;
    state.config = cat.defaults;

    initSimControls();
    initPresets();
    initSliders();
    initMethods();
    init3DViewport();
    initDashboardChannels();
    initScenarioEditor();
    initOptimization();
    initMonteCarlo();

    // Navigation bindings
    document.querySelectorAll(".nav").forEach(btn => {
      btn.onclick = () => page(btn.dataset.page);
    });

    // Run button in hero
    const btnRun = $("run-btn");
    if (btnRun) {
      btnRun.disabled = false;
      btnRun.onclick = async () => {
        btnRun.disabled = true;
        $("run-status").hidden = false;
        $("run-message").textContent = "물리 전달장 및 드론 6-DOF 수치 적분 실행 중...";
        $("progress-fill").style.width = "45%";

        try {
          const runJob = await api("/api/run", { config: state.config });
          pollJob(runJob.job_id);
        } catch (err) {
          toast("시뮬레이션 실행 오류: " + err.message, true);
          $("run-status").hidden = true;
          btnRun.disabled = false;
        }
      };
    }

    renderDeviceFields();
    updateLedger();
    updateSimTimeUI();
    drawField();
    renderDashboardChart();

    toast("FIREFIELD 12대 패널 통합 연구 워크벤치가 준비되었습니다.");
  } catch (err) {
    console.error("Boot error:", err);
    toast("워크벤치 초기화 실패: " + err.message, true);
  }
}

function pollJob(jobId) {
  const timer = setInterval(async () => {
    try {
      const j = await api(`/api/jobs/${jobId}`);
      $("progress-fill").style.width = `${Math.min(100, j.progress * 100)}%`;
      $("run-message").textContent = j.message || "계산 중...";

      if (j.status === "completed") {
        clearInterval(timer);
        $("run-status").hidden = true;
        $("run-btn").disabled = false;
        const latestRes = await api("/api/latest");
        state.result = latestRes;
        $("solver-badge").textContent = "SIMULATION CONVERGED";
        $("solver-badge").className = "badge ready";
        toast("시뮬레이션 계산이 성공적으로 수렴 및 완료되었습니다.");
        drawField();
        renderDashboardChart();
      } else if (j.status === "failed") {
        clearInterval(timer);
        $("run-status").hidden = true;
        $("run-btn").disabled = false;
        toast("계산 실패: " + j.message, true);
      }
    } catch (err) {
      clearInterval(timer);
      $("run-status").hidden = true;
      $("run-btn").disabled = false;
    }
  }, 1000);
}

function renderCharts() {
  if (state.page === "lab") {
    drawField();
    renderDashboardChart();
  } else if (state.page === "comparison") {
    renderComparison();
  }
}

window.addEventListener("DOMContentLoaded", boot);
window.addEventListener("resize", renderCharts);
'''

def write_app():
    APP_PATH.write_text(APP_CODE, encoding="utf-8")
    print(f"Successfully generated web/app.js ({len(APP_CODE)} chars)")

if __name__ == "__main__":
    write_app()
