'use strict';
const $ = id => document.getElementById(id);
const state = {catalog:null, config:null, result:null, method:'M1', page:'lab', filter:'all', yaw:-.62, pitch:.48, zoom:1, analysis:null, busy:false};

const labels = {
  lab: ['5가지 진압 방식의 전달장 계산', '동일한 거리·횡풍·작동 시간에서 실제 물리 지배방정식에 따른 유동 및 자원 수지를 비교합니다.'],
  drone: ['드론 탑재 비행 동역학 비교', '장치 OFF · 비제어(무보정) · 6-DOF 위치 보정을 동일 기체 조건에서 비교 적분합니다.'],
  physics: ['지배방정식과 물리 유도', '질량·운동량·에너지 보존 법칙 및 각 진압 방식의 수학적 유도와 소스 코드 매핑을 열람합니다.'],
  design: ['상호보완성 실험 설계', '동시 작동 이득과 작동 순서 효과를 분리해 검정하는 36개 사전 등록 매트릭스입니다.'],
  data: ['반복별 화염 결과 분석', '관측 종료·수치 실패·우측 검열을 엄격히 구분하여 RMST 및 95% 신뢰구간을 산출합니다.'],
  evidence: ['원본·가정·검증 게이트', '자료 해시 무결성, 호환성 판정 게이트, native FDS 솔버 실행 기록을 검증합니다.']
};

const canvasFont = (size, mono=true) => `${size}px ${mono ? '"JetBrains Mono", "Berkeley Mono", "D2Coding", Consolas, monospace' : '"Pretendard", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'}`;
const format = (v, digits=3) => v === null || v === undefined || !Number.isFinite(Number(v)) ? '—' : Number(v).toLocaleString('ko-KR',{maximumFractionDigits:digits});
const el = (tag, text, cls) => {const node=document.createElement(tag); if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;};

function toast(message, error=false){
  const n = $('toast');
  n.textContent = message;
  n.classList.toggle('error', error);
  n.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => n.hidden = true, 6500);
}

async function api(path, body){
  const r = await fetch(path, body === undefined ? {} : {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const data = await r.json();
  if(!r.ok) throw new Error(data?.error || `HTTP ${r.status}`);
  return data;
}

function download(name, data, type='application/json'){
  const blob = new Blob([typeof data === 'string' ? data : JSON.stringify(data, null, 2)], {type});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

function page(name){
  state.page = name;
  document.querySelectorAll('.page').forEach(n => n.classList.toggle('active', n.id === `page-${name}`));
  document.querySelectorAll('.nav').forEach(n => n.classList.toggle('active', n.dataset.page === name));
  if(labels[name]){
    $('page-title').textContent = labels[name][0];
    $('page-description').textContent = labels[name][1];
  }
  requestAnimationFrame(renderCharts);
  if(name === 'evidence') loadNative();
}

function markDirty(){
  syncEditor();
  if(state.result) $('run-id').textContent = '입력 변경됨 · 표시 중인 결과는 이전 계산입니다';
}

function syncEditor(){
  $('config-editor').value = JSON.stringify(state.config, null, 2);
}

function sliders(){
  const items = [
    ['distance', 'distance_m', 'm', 1],
    ['wind', 'crosswind_m_s', 'm/s', 1],
    ['duration', 'duration_s', 's', 0]
  ];
  for(const [id, key, unit, digits] of items){
    $(id).value = state.config.scenario[key];
    $(`${id}-out`).textContent = `${Number(state.config.scenario[key]).toFixed(digits)} ${unit}`;
    $(id).oninput = () => {
      state.config.scenario[key] = Number($(id).value);
      $(`${id}-out`).textContent = `${Number($(id).value).toFixed(digits)} ${unit}`;
      markDirty();
    };
  }
}

const deviceSpecs = {
  M1: [
    ['frequency_hz', '주파수 / Hz', 1, 200, 1],
    ['velocity_rms_m_s', '출구 RMS / m/s', 0, 2, .01],
    ['power_W', '전기 출력 / W', 0, 1000, 1],
    ['mass_kg', '장치 질량 / kg', .01, 20, .05]
  ],
  M2: [
    ['exit_velocity_m_s', '출구 유속 / m/s', 0, 30, .5],
    ['diameter_m', '출구 직경 / m', .01, .5, .01],
    ['pulse_duration_s', '펄스 폭 / s', .002, .5, .01],
    ['stored_energy_J', '저장 공압 / J', 0, 10000, 10]
  ],
  M3: [
    ['flow_kg_s', '질량유량 / kg/s', 0, .1, .001],
    ['diameter_um', '액적 직경 / μm', 1, 1000, 5],
    ['payload_kg', '적재량 / kg', 0, 5, .01],
    ['power_W', '전기 출력 / W', 0, 1000, 1]
  ],
  M4: [
    ['flow_kg_s', '질량유량 / kg/s', 0, .1, .001],
    ['diameter_um', '입자 직경 / μm', 1, 1000, 1],
    ['payload_kg', '적재량 / kg', 0, 5, .01],
    ['power_W', '전기 출력 / W', 0, 1000, 1]
  ],
  M5: [
    ['exit_velocity_m_s', '출구 유속 / m/s', 0, 30, .5],
    ['diameter_um', '입자 직경 / μm', 1, 1000, 1],
    ['payload_kg', '적재량 / kg', 0, 5, .01],
    ['power_W', '전기 출력 / W', 0, 1000, 1]
  ]
};

function numberFields(container, specs, object, prefix){
  const parent = $(container);
  parent.replaceChildren();
  for(const [key, label, min, max, step] of specs){
    const wrap = el('label', label);
    const input = el('input');
    input.type = 'number';
    input.id = `${prefix}-${key}`;
    input.value = object[key];
    input.min = min;
    input.max = max;
    input.step = step;
    input.addEventListener('change', () => {
      if(input.value === '' || !input.checkValidity()){
        toast(`${label}: 입력 범위를 확인하세요.`, true);
        input.value = object[key];
        return;
      }
      object[key] = Number(input.value);
      markDirty();
    });
    wrap.append(input);
    parent.append(wrap);
  }
}

function renderSettings(){
  sliders();
  const methodNames = {
    M1: 'M1 저주파 음향 방출기',
    M2: 'M2 공기 와류 링 노즐',
    M3: 'M3 지향 수분무 인젝터',
    M4: 'M4 응축 에어로졸 디스펜서',
    M5: 'M5 전도성 와류 / EHD 방출기'
  };
  $('device-label').textContent = `${state.method} DEVICE · ${methodNames[state.method] || '장치 사양'}`;
  numberFields('device-fields', deviceSpecs[state.method], state.config.methods[state.method], 'device');
  numberFields('drone-fields', [
    ['mass_kg', '기체 자체 건조중량 / kg', .01, 20, .1],
    ['battery_Wh', '배터리 용량 / Wh', 0, 2000, 5],
    ['max_thrust_N', '최대 합산 추력 / N', 0, 1000, 1],
    ['max_power_W', '최대 추진 전력 / W', 0, 10000, 10],
    ['approach_s', '목표점 접근 시간 / s', 0, 120, 1],
    ['return_s', '안전기지 복귀 시간 / s', 0, 120, 1]
  ], state.config.drone, 'airframe');
  syncEditor();
}

function methodSelect(mid){
  state.method = mid;
  document.documentElement.style.setProperty('--accent', state.catalog.methods[mid].color);
  renderMethods();
  renderSettings();
  renderResult();
}

function renderMethods(){
  const parent = $('method-grid');
  parent.replaceChildren();
  for(const [mid, m] of Object.entries(state.catalog.methods)){
    const b = el('button', undefined, `method-card${state.method === mid ? ' selected' : ''}`);
    b.style.setProperty('--method-color', m.color);
    b.dataset.method = mid;
    b.setAttribute('aria-pressed', String(state.method === mid));
    
    const header = el('div', undefined, 'method-header');
    header.append(el('span', mid, 'method-id'), el('span', undefined, 'method-indicator'));
    
    b.append(header, el('strong', m.name), el('small', m.subtitle));
    b.onclick = () => methodSelect(mid);
    parent.append(b);
  }
}

function methodData(){
  return state.result?.methods[state.method];
}

function renderResult(){
  const data = methodData();
  $('field-title').textContent = `${state.catalog.methods[state.method].name} 유동 전달장`;
  $('field-empty').hidden = !!data;
  if(!data){
    renderCharts();
    return;
  }

  const p = data.physics, m = p.metrics;
  const speed = m.target_velocity_rms_m_s ?? m.target_speed_rms_m_s ?? m.peak_target_speed_m_s ?? m.target_peak_speed_m_s;

  const metricDefs = [
    [
      '표적 도달 유속',
      speed !== undefined ? `${format(speed)} m/s` : '—',
      state.method === 'M1' ? '주기 RMS (선형 구면파 근사)' : '순간 최고 속도 크기'
    ],
    [
      '표적 전달 질량',
      m.delivered_kg !== undefined ? `${format(m.delivered_kg * 1000)} g` : '해당 없음',
      m.delivery_fraction !== undefined ? `방출량 대비 ${format(m.delivery_fraction * 100, 1)}% 도달` : '질량 미방출 방식'
    ],
    [
      '장치 입력 에너지',
      `${format(m.device_energy_J ?? m.electrical_energy_J)} J`,
      m.minimum_pneumatic_energy_demand_J !== undefined ? `공압 요구량 ${format(m.minimum_pneumatic_energy_demand_J)} J 별도` : '추진 전력은 드론 탭 참조'
    ],
    [
      '소화 성능 평가',
      '데이터 필요',
      '화염 화학반응·냉각 모델 요구'
    ]
  ];

  $('transport-metrics').replaceChildren(...metricDefs.map((d, i) => {
    const a = el('article');
    a.append(el('span', d[0]), el('strong', d[1], i === 3 ? 'small-value' : ''), el('small', d[2]));
    return a;
  }));

  $('field-snapshot').textContent = state.method === 'M1' ? 'RMS 진폭장 (주기 평균치)' : `t = ${format(state.result.config.scenario.duration_s, 1)} s · 최종 분포장`;
  $('field-scale').textContent = '벡터 상대 길이 · 속도 m/s';

  const notes = {
    M1: '선형 파동방정식과 개구부 음향 인텐시티 보존에 기초한 RMS 유속장입니다. 스피커 근접 비선형 박리 및 화염과의 직접 반응은 포함되지 않습니다.',
    M2: '유한 핵(Lamb-Oseen)을 갖는 얇은 와류 링의 Biot-Savart 유도 속도장입니다. 점성 확산에 따른 Saffman 자기유도 감속을 시간 적분합니다.',
    M3: 'Schiller-Naumann 항력과 등온 Maxwell d² 증발 법칙을 결합한 Lagrangian 액적 수송 모델입니다. 화염 잠열 흡열 피드백은 별도 솔버가 필요합니다.',
    M4: '화학 반응성이 없는 수동 입자 수송 모델입니다. 응축 소화약제의 라디칼 소거, 고온 가스 발생기 효과는 포함되지 않습니다.',
    M5: '기본 CV 모드는 공기 와류 링 내 전도성 입자 동반 수송입니다. EHD 모드는 1D Poisson-Coulomb 체적력 qE 기반 속도 증가분을 계산합니다.'
  };

  $('model-note').textContent = notes[state.method];
  $('run-id').textContent = JSON.stringify(state.config) !== JSON.stringify(state.result.config)
    ? '입력 변경됨 · 표시 중인 결과는 이전 계산입니다'
    : `${state.result.run_id} · ${state.result.evidence_type} (검증 완료)`;

  $('export-btn').disabled = false;
  renderDrone();
  renderCharts();
}

function canvasContext(id){
  const canvas = $(id);
  if(!canvas) return null;
  const rect = canvas.getBoundingClientRect();
  if(!rect.width || !rect.height) return null;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, rect.width, rect.height);
  return {ctx, w: rect.width, h: rect.height};
}

function drawField(){
  const box = canvasContext('field-canvas');
  if(!box) return;
  const {ctx, w, h} = box;
  const data = methodData()?.physics;
  const scenario = state.result?.config.scenario ?? state.config?.scenario ?? {distance_m: 1, target_radius_m: .2};
  const distance = scenario.distance_m;
  const width = Math.max(.3, scenario.target_radius_m * 2.5);
  const center = distance * .55;
  const scale = Math.min(w / (distance * 1.8 + width * 2), h / (width * 3.8 + distance * .45)) * state.zoom;

  const project = ([x, y, z]) => {
    x -= center;
    const a = x * Math.cos(state.yaw) - y * Math.sin(state.yaw);
    const b = x * Math.sin(state.yaw) + y * Math.cos(state.yaw);
    return [
      w * .50 + a * scale,
      h * .54 + (b * Math.sin(state.pitch) - z * Math.cos(state.pitch)) * scale,
      b * Math.cos(state.pitch) + z * Math.sin(state.pitch)
    ];
  };

  const line = (a, b, color, widthLine=1) => {
    const p = project(a), q = project(b);
    ctx.strokeStyle = color;
    ctx.lineWidth = widthLine;
    ctx.beginPath();
    ctx.moveTo(p[0], p[1]);
    ctx.lineTo(q[0], q[1]);
    ctx.stroke();
  };

  // Subtle floor grid lines
  const gridColor = 'rgba(148, 163, 184, 0.15)';
  for(let i = 0; i <= 10; i++){
    const x = distance * 1.3 * i / 10;
    line([x, -width, -width], [x, width, -width], gridColor, 1);
  }
  for(let i = 0; i <= 8; i++){
    const y = -width + width * 2 * i / 8;
    line([0, y, -width], [distance * 1.3, y, -width], gridColor, 1);
  }

  // Coordinate axes
  line([0, 0, 0], [distance * 1.35, 0, 0], 'rgba(239, 68, 68, 0.6)', 1.5); // X: Red
  line([0, 0, 0], [0, width * 1.2, 0], 'rgba(34, 197, 94, 0.6)', 1.5);    // Y: Green
  line([0, 0, 0], [0, 0, width * 1.15], 'rgba(59, 130, 246, 0.6)', 1.5);  // Z: Blue

  ctx.font = canvasFont(10, true);
  const axes = [
    ['+X (전진/거리)', [distance * 1.38, 0, 0], '#ef4444'],
    ['+Y (횡풍/측면)', [0, width * 1.26, 0], '#22c55e'],
    ['+Z (연직)', [0, 0, width * 1.22], '#3b82f6']
  ];
  for(const [label, p, color] of axes){
    const q = project(p);
    ctx.fillStyle = color;
    ctx.fillText(label, q[0] + 4, q[1] + 3);
  }

  // Target Disc (Circular target plane with dashed border and subtle fill)
  const radius = scenario.target_radius_m;
  ctx.fillStyle = 'rgba(245, 158, 11, 0.08)';
  ctx.beginPath();
  for(let i = 0; i <= 60; i++){
    const a = i * Math.PI / 30;
    const q = project([distance, Math.cos(a) * radius, Math.sin(a) * radius]);
    i === 0 ? ctx.moveTo(q[0], q[1]) : ctx.lineTo(q[0], q[1]);
  }
  ctx.closePath();
  ctx.fill();

  ctx.strokeStyle = '#f59e0b';
  ctx.lineWidth = 1.6;
  ctx.setLineDash([4, 4]);
  ctx.stroke();
  ctx.setLineDash([]);

  const tq = project([distance, 0, radius]);
  ctx.fillStyle = '#fbbf24';
  ctx.font = canvasFont(10, true);
  ctx.fillText(`TARGET PLANE (r = ${radius}m)`, tq[0] - 30, tq[1] - 12);

  // Source Nozzle Symbol
  const source = project([0, 0, 0]);
  const activeColor = state.catalog?.methods[state.method]?.color ?? '#0284c7';
  ctx.fillStyle = activeColor;
  ctx.beginPath();
  ctx.arc(source[0], source[1], 6, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth = 1.5;
  ctx.stroke();
  ctx.font = canvasFont(10, true);
  ctx.fillText('NOZZLE / SOURCE', source[0] - 36, source[1] + 20);

  if(!data?.field?.points?.length) return;
  const points = data.field.points, vel = data.field.velocity;
  const norms = vel.map(v => Math.hypot(...v)), max = Math.max(...norms, 1e-12);

  // Depth-sorted velocity vectors
  const order = points.map((p, i) => ({p, i, depth: project(p)[2]})).sort((a, b) => b.depth - a.depth);
  for(const {p, i} of order){
    const n = norms[i];
    if(n < max * .002) continue;
    const relSpeed = n / max;
    const length = width * .24 * Math.sqrt(relSpeed);
    const v = vel[i];
    const q = p.map((x, k) => x + v[k] / n * length);
    const a = project(p), b = project(q);

    // Color gradient from cyan (slow) to warm amber/white (fast)
    ctx.strokeStyle = activeColor;
    ctx.globalAlpha = 0.20 + 0.80 * Math.sqrt(relSpeed);
    ctx.lineWidth = 1 + relSpeed * 1.2;
    ctx.beginPath();
    ctx.moveTo(a[0], a[1]);
    ctx.lineTo(b[0], b[1]);
    ctx.stroke();

    // Arrowhead
    const angle = Math.atan2(b[1] - a[1], b[0] - a[0]);
    const arrowLen = 3.5 + relSpeed * 2.5;
    ctx.beginPath();
    ctx.moveTo(b[0] - arrowLen * Math.cos(angle - .40), b[1] - arrowLen * Math.sin(angle - .40));
    ctx.lineTo(b[0], b[1]);
    ctx.lineTo(b[0] - arrowLen * Math.cos(angle + .40), b[1] - arrowLen * Math.sin(angle + .40));
    ctx.stroke();
  }
  ctx.globalAlpha = 1;

  ctx.fillStyle = '#cbd5e1';
  ctx.font = canvasFont(10, true);
  ctx.fillText(`최고 유속 |u|_max = ${format(max)} m/s`, w - 180, 24);
}

function lineChart(id, curves, yLabel){
  const box = canvasContext(id);
  if(!box) return;
  const {ctx, w, h} = box;
  const L = 68, R = 30, T = 32, B = 38;
  const all = curves.flatMap(c => c.values).filter(p => Number.isFinite(p[0]) && Number.isFinite(p[1]));

  if(!all.length){
    ctx.fillStyle = '#94a3b8';
    ctx.font = canvasFont(12, false);
    ctx.fillText('시뮬레이션 실행 후 과도 시간 이력이 표시됩니다.', L, h / 2);
    return;
  }

  const xmax = Math.max(...all.map(p => p[0]), .1);
  const ymin = Math.min(0, ...all.map(p => p[1]));
  const ymax0 = Math.max(...all.map(p => p[1]), 1e-9);
  const ymax = ymax0 * 1.12;

  const py = y => T + (ymax - y) / (ymax - ymin) * (h - T - B);
  const px = x => L + x / xmax * (w - L - R);

  // Grid and Y ticks
  ctx.font = canvasFont(9.5, true);
  ctx.textAlign = 'right';
  for(let i = 0; i <= 4; i++){
    const y = ymin + (ymax - ymin) * i / 4;
    const yy = py(y);
    ctx.strokeStyle = 'rgba(15, 23, 42, 0.08)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(L, yy);
    ctx.lineTo(w - R, yy);
    ctx.stroke();

    ctx.fillStyle = '#64748b';
    ctx.fillText(format(y, Math.abs(ymax) < .1 ? 4 : 2), L - 8, yy + 3.5);
  }

  // X ticks
  ctx.textAlign = 'center';
  for(let i = 0; i <= 5; i++){
    const x = xmax * i / 5;
    ctx.fillText(format(x, 1), px(x), h - 14);
  }

  ctx.textAlign = 'left';
  ctx.fillStyle = '#0f172a';
  ctx.font = canvasFont(10, false);
  ctx.fillText(yLabel, 16, 16);

  ctx.textAlign = 'right';
  ctx.fillStyle = '#64748b';
  ctx.font = canvasFont(10, false);
  ctx.fillText('시간 / s', w - 16, h - 3);

  // Curves & Legends
  ctx.textAlign = 'left';
  let legendX = L;
  for(const curve of curves){
    ctx.fillStyle = curve.color;
    ctx.beginPath();
    ctx.arc(legendX + 4, 13, 4, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#334155';
    ctx.font = canvasFont(10.5, false);
    ctx.fillText(curve.label, legendX + 13, 17);
    legendX += ctx.measureText(curve.label).width + 32;

    ctx.beginPath();
    ctx.strokeStyle = curve.color;
    ctx.lineWidth = 2.0;
    let begun = false;
    for(const p of curve.values){
      if(!Number.isFinite(p[1])) continue;
      if(!begun){
        ctx.moveTo(px(p[0]), py(p[1]));
        begun = true;
      } else {
        ctx.lineTo(px(p[0]), py(p[1]));
      }
    }
    ctx.stroke();
  }
}

function renderTrace(){
  const data = methodData()?.physics;
  if(!data){
    lineChart('trace-chart', [], '');
    return;
  }
  const series = data.series ?? [];
  if(state.method === 'M1' || state.method === 'M2'){
    $('trace-title').textContent = '표적 도달 유속의 과도 시간 이력';
    $('trace-unit').textContent = state.method === 'M1' ? '주기 RMS · m/s' : '유속 크기 · m/s';
    lineChart('trace-chart', [{
      label: state.method === 'M1' ? 'RMS 진폭 속도' : '표적 도달 유속',
      color: state.catalog.methods[state.method].color,
      values: series.map(r => [r.time_s, r.target_speed_m_s])
    }], '유속 / m/s');
  } else {
    $('trace-title').textContent = '약제 방출·도달·잔류 질량의 과도 시간 이력';
    $('trace-unit').textContent = '누적 질량 · g';
    lineChart('trace-chart', [
      ['emitted_kg', '총 방출량', '#3b82f6'],
      ['delivered_kg', '표적 도달량', '#0d9488'],
      ['airborne_kg', '공중 체류량', '#f59e0b']
    ].map(([key, label, color]) => ({
      label,
      color,
      values: series.map(r => [r.time_s, r[key] * 1000])
    })), '질량 / g');
  }
}

function renderDrone(){
  const tb = $('drone-table');
  tb.replaceChildren();
  const mid = $('drone-method').value || state.method;
  const data = state.result?.methods[mid];
  if(!data){
    const row = el('tr');
    const cell = el('td', '시뮬레이션을 실행하면 드론 탑재 동역학 결과가 표시됩니다.');
    cell.colSpan = 6;
    row.append(cell);
    tb.append(row);
    return;
  }
  const statusLabels = {
    feasible_in_model: '제약 충족 (Feasible)',
    conditional: '조건부 충족',
    infeasible: '제약 초과 (Infeasible)'
  };
  for(const [key, name] of [['off', '장치 OFF (자체 비행)'], ['uncorrected', '작동 · 비제어(무보정)'], ['corrected', '작동 · 6-DOF 위치 보정']]){
    const d = data.drone[key], m = d.metrics, row = el('tr');
    for(const value of [
      name,
      `${format(m.energy_J / 3600, 2)} Wh`,
      `${format(m.max_position_error_m, 3)} m`,
      `${format(m.peak_tilt_deg, 2)}°`,
      `${format(m.remaining_Wh, 2)} Wh`,
      statusLabels[d.status] ?? d.status
    ]){
      row.append(el('td', value));
    }
    tb.append(row);
  }
  $('drone-note').textContent = '공학 가정 사양 기반의 강체 6-DOF 및 배터리 전력 모델 결과입니다. ' +
    (data.drone.corrected.failures.length ? '제약 초과 항목: ' + data.drone.corrected.failures.join(', ') : '모든 기체 한계(추력, 자세, 배터리) 내에서 비행 가능합니다.');
}

function energyChart(){
  const box = canvasContext('energy-chart');
  if(!box) return;
  const {ctx, w, h} = box;
  if(!state.result){
    ctx.fillStyle = '#94a3b8';
    ctx.font = canvasFont(12, false);
    ctx.fillText('계산 결과 대기 중', 35, 100);
    return;
  }
  const entries = Object.entries(state.result.methods);
  const max = Math.max(...entries.map(([, d]) => d.drone.corrected.metrics.energy_J / 3600), 1);
  ctx.font = canvasFont(11, true);

  entries.forEach(([mid, d], i) => {
    const y = 24 + i * (h - 40) / 5;
    const value = d.drone.corrected.metrics.energy_J / 3600;
    ctx.fillStyle = '#64748b';
    ctx.fillText(mid, 18, y + 12);

    ctx.fillStyle = '#f1f5f9';
    ctx.beginPath();
    ctx.roundRect(55, y, w - 150, 16, 4);
    ctx.fill();

    ctx.fillStyle = d.identity.color;
    ctx.beginPath();
    ctx.roundRect(55, y, Math.max(4, (w - 150) * value / max), 16, 4);
    ctx.fill();

    ctx.fillStyle = '#0f172a';
    ctx.fillText(`${format(value, 2)} Wh`, w - 85, y + 12);
  });
}

function renderCharts(){
  drawField();
  renderTrace();
  energyChart();
  const data = state.result?.methods[$('drone-method').value || state.method];
  lineChart('drone-chart', data ? [
    ['off', '장치 OFF', '#94a3b8'],
    ['uncorrected', '비제어(무보정)', '#f59e0b'],
    ['corrected', '6-DOF 위치 보정', '#0d9488']
  ].map(([key, label, color]) => ({
    label,
    color,
    values: data.drone[key].series.map(r => [r.time_s, r.target_error_m])
  })) : [], '위치 오차 / m');
}

function renderMatrix(){
  const tb = $('matrix-table');
  tb.replaceChildren();
  const modes = {control: '무개입 대조군', single: '단독 작동', simultaneous: '동시 복합', sequential: '순차 복합'};
  for(const row of state.catalog.matrix){
    if(state.filter !== 'all' && row.mode !== state.filter) continue;
    const tr = el('tr');
    for(const v of [
      row.id,
      row.methods.join(row.mode === 'sequential' ? ' → ' : ' + ') || '대조군 (None)',
      modes[row.mode] || row.mode,
      'SI 자원 명세 완료',
      '화염 관측 대기'
    ]){
      tr.append(el('td', v));
    }
    tb.append(tr);
  }
}

function renderEvidence(){
  const ev = state.catalog.evidence;
  $('source-list').replaceChildren(...ev.sources.map(s => {
    const d = el('div', undefined, 'source-row');
    d.append(
      el('span', s.exists ? '원본 확인' : '원본 누락', `badge ${s.exists ? 'ready' : 'blocked'}`),
      el('strong', s.name),
      el('small', `${format(s.size_bytes / 1024 / 1024, 2)} MB · SHA-256 ${s.sha256 ?? '없음'}`)
    );
    return d;
  }));

  const gateClass = {
    ready: 'ready',
    conditional: 'conditional',
    warning: 'warning',
    blocked: 'blocked'
  };

  $('gate-list').replaceChildren(...ev.original_gates.map(g => {
    const row = el('div', undefined, 'gate-row');
    row.append(
      el('span', `${g.stage}. ${g.name}`),
      el('span', g.status, `badge ${gateClass[g.status] ?? 'conditional'}`)
    );
    return row;
  }));

  $('missing-list').replaceChildren(...ev.missing_inputs.map(x => {
    const item = el('li');
    item.append(el('span', '✕', 'bullet'), document.createTextNode(' ' + x));
    return item;
  }));
}

async function loadNative(){
  try {
    const result = await api('/api/native');
    const list = $('native-list');
    list.replaceChildren();
    if(!result.manifests.length){
      list.textContent = 'native 실행 기록이 아직 없습니다. 전달장 결과와 구분하여 표시합니다.';
      return;
    }
    for(const item of result.manifests){
      const row = el('div', undefined, 'native-entry'), d = item.data;
      row.append(el('strong', item.path));
      const status = d.status ?? d.run_status ?? d.validation_status ?? '기록 있음';
      row.append(el('p', `${item.path.startsWith('cases') ? '첨부/입력 기록' : '실제 솔버 실행'} · 상태: ${status}`));
      if(d.completion){
        row.append(el('p', `해석 시간 ${format(d.completion.achieved_time_s)} / ${format(d.completion.configured_t_end_s)} s (완료율 ${format(d.completion.completion_fraction * 100, 1)}%)`));
      }
      const detail = el('details');
      const summary = el('summary', '실행 명세 JSON 보기');
      const pre = el('pre', JSON.stringify(d, null, 2));
      detail.append(summary, pre);
      row.append(detail);
      list.append(row);
    }
  } catch(e) {
    $('native-list').textContent = e.message;
  }
}

async function run(){
  if(state.busy) return;
  state.busy = true;
  $('run-btn').disabled = true;
  $('run-status').hidden = false;
  try {
    const j = await api('/api/run', {config: state.config});
    for(;;){
      const status = await api(`/api/jobs/${j.job_id}`);
      $('run-message').textContent = status.message;
      $('progress-fill').style.width = `${status.progress * 100}%`;
      if(status.status === 'failed') throw new Error(status.message);
      if(status.status === 'completed'){
        state.result = await api('/api/latest');
        renderResult();
        toast('5가지 방식의 전달장 및 드론 6-DOF 동역학 계산이 완료되었습니다.');
        break;
      }
      await new Promise(r => setTimeout(r, 700));
    }
  } catch(e) {
    toast(e.message, true);
    $('run-message').textContent = `계산 중단: ${e.message}`;
  } finally {
    state.busy = false;
    $('run-btn').disabled = false;
  }
}

async function analyze(body){
  try {
    state.analysis = await api(body.preregistration ? '/api/study/analyze' : body.synergy ? '/api/synergy' : '/api/analyze', body);
    $('outcome-summary').hidden = false;
    const g = state.analysis.groups;
    const groups = Array.isArray(g) ? g : Object.values(g ?? {});
    $('outcome-summary').textContent = body.preregistration
      ? `시계열 ${body.records.length}건 분석 완료 · 소화·재점화·노출 상태 확인`
      : body.synergy
        ? `상호보완성 분석 완료 · ${state.analysis.eligible ? '비교 요건 충족' : '비교 요건 미충족'}`
        : `${groups.length}개 조건 통계 분석 완료 · τ = ${state.analysis.tau_s} s`;
    $('outcome-summary').style.padding = '18px 24px';
    $('outcome-result').hidden = false;
    $('outcome-result').textContent = JSON.stringify(state.analysis, null, 2);
    $('analysis-export').disabled = false;
    toast('반입 데이터의 통계 분석이 완료되었습니다.');
  } catch(e) {
    toast(e.message, true);
  }
}

function wire(){
  document.querySelectorAll('.nav').forEach(n => n.onclick = () => page(n.dataset.page));
  $('see-evidence').onclick = () => page('evidence');
  $('see-physics').onclick = () => page('physics');
  $('run-btn').onclick = run;
  $('export-btn').onclick = () => {
    if(state.result) location.href = `/api/results/${state.result.run_id}/results.zip`;
  };
  $('reset-config').onclick = () => {
    state.config = structuredClone(state.catalog.defaults);
    renderSettings();
    markDirty();
  };
  $('apply-json').onclick = async () => {
    try {
      const next = JSON.parse($('config-editor').value);
      if(!next.scenario || !next.methods || !next.drone) throw new Error('scenario, methods, drone 항목이 필수입니다.');
      state.config = await api('/api/validate', next);
      renderSettings();
      markDirty();
      toast('설정을 적용했습니다. 물리적 상한 범위가 확인되었습니다.');
    } catch(e) {
      toast(e.message, true);
    }
  };
  $('drone-method').onchange = () => {
    renderDrone();
    renderCharts();
  };
  $('matrix-export').onclick = () => download('experiment_matrix.json', state.catalog.matrix);
  $('matrix-filters').onclick = e => {
    if(!e.target.dataset.mode) return;
    state.filter = e.target.dataset.mode;
    document.querySelectorAll('#matrix-filters button').forEach(b => b.classList.toggle('selected', b === e.target));
    renderMatrix();
  };
  $('refresh-native').onclick = loadNative;
  $('template-export').onclick = () => download('outcome_input_template.json', {
    tau_s: 10,
    records: [{
      case_id: 'sample-case-01',
      block_id: 'block-ambient-seed-1',
      condition_id: 'M1',
      run_status: 'solver_failure',
      observation_end_s: 0,
      event: false,
      event_time_s: null,
      loss_J_m2: null,
      input_energy_J: null,
      provenance: {source: 'manifest.json', evidence_type: 'unvalidated_physics'}
    }]
  });
  $('outcome-file').onchange = async e => {
    try {
      const f = e.target.files[0];
      if(!f) return;
      if(f.size > 8 * 1024 * 1024) throw new Error('파일 크기는 8MB 이하여야 합니다.');
      const body = JSON.parse(await f.text());
      $('outcome-editor').value = JSON.stringify(body, null, 2);
      await analyze(body);
    } catch(e) {
      toast(e.message, true);
    }
  };
  $('analyze-btn').onclick = () => {
    try {
      analyze(JSON.parse($('outcome-editor').value));
    } catch(e) {
      toast(e.message, true);
    }
  };
  $('analysis-export').onclick = () => download('outcome_analysis.json', state.analysis);

  // 3D Canvas Orbit Interaction
  const canvas = $('field-canvas');
  let drag = null;
  canvas.onpointerdown = e => {
    drag = [e.clientX, e.clientY];
    canvas.setPointerCapture(e.pointerId);
  };
  canvas.onpointermove = e => {
    if(!drag) return;
    state.yaw += (e.clientX - drag[0]) * .008;
    state.pitch = Math.max(-1.2, Math.min(1.2, state.pitch + (e.clientY - drag[1]) * .008));
    drag = [e.clientX, e.clientY];
    drawField();
  };
  canvas.onpointerup = () => drag = null;
  canvas.onpointercancel = () => drag = null;
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    state.zoom = Math.min(2.5, Math.max(.5, state.zoom * Math.exp(-e.deltaY * .001)));
    drawField();
  }, {passive: false});

  $('reset-view').onclick = () => {
    state.yaw = -.62;
    state.pitch = .48;
    state.zoom = 1;
    drawField();
  };

  new ResizeObserver(() => renderCharts()).observe(document.querySelector('main'));
}

async function init(){
  try {
    state.catalog = await api('/api/catalog');
    state.config = structuredClone(state.catalog.defaults);
    for(const [mid, m] of Object.entries(state.catalog.methods)){
      const opt = el('option', `${mid} · ${m.name}`);
      opt.value = mid;
      $('drone-method').append(opt);
    }
    wire();
    renderMethods();
    renderSettings();
    renderMatrix();
    renderEvidence();
    state.result = await api('/api/latest');
    if(state.result){
      state.config = structuredClone(state.result.config);
      renderSettings();
    }
    renderResult();
    loadNative();
    $('run-btn').disabled = false;
  } catch(e) {
    toast(`시작 오류: ${e.message}`, true);
  }
}

init();
