"""Script to generate the complete 12-Panel UI in web/index.html and update style/app scripts."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "web" / "index.html"

def generate_index_html():
    raw = INDEX_PATH.read_text(encoding="utf-8")
    
    # 1. Update Navigation Buttons
    nav_html = """  <div class="side-label">통합 연구 워크벤치 (12 Panels)</div>
  <nav aria-label="주 연구 메뉴">
    <button class="nav active" data-page="lab">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 2v7.31L4.1 18.2A2 2 0 0 0 5.7 21h12.6a2 2 0 0 0 1.6-2.8L14 9.31V2"/></svg>
      <span>통합 스튜디오 (Studio)</span>
    </button>
    <button class="nav" data-page="comparison">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
      <span>방식별 비교 (Comparison)</span>
    </button>
    <button class="nav" data-page="editor">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
      <span>시나리오 에디터 (Editor)</span>
    </button>
    <button class="nav" data-page="optimize">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20v-6M6 20V10M18 20V4"/></svg>
      <span>다목적 최적화 [선택]</span>
    </button>
    <button class="nav" data-page="montecarlo">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m4.93 4.93 4.24 4.24M14.83 14.83l4.24 4.24M14.83 9.17l4.24-4.24M4.93 19.07l4.24-4.24"/></svg>
      <span>불확실성/MC [선택]</span>
    </button>
    <button class="nav" data-page="export">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
      <span>결과 및 차트 내보내기</span>
    </button>
    <button class="nav" data-page="physics">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/><path d="M6 6h10M6 10h10M6 14h6"/></svg>
      <span>지배방정식과 유도</span>
    </button>
    <button class="nav" data-page="nativefields">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
      <span>native 3D 격자</span>
    </button>
    <button class="nav" data-page="evidence">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>
      <span>근거와 검증 게이트</span>
    </button>
  </nav>"""
    
    raw = re.sub(r'<div class="side-label">.*?<\/nav>', nav_html, raw, flags=re.DOTALL)
    
    # 2. Simulation Control Bar (필수 5) right above or inside studio
    sim_ctrl_bar = """  <!-- [필수 5] Simulation Control Panel (시뮬레이션 제어 바) -->
  <section class="panel sim-control-bar" id="panel-sim-control">
    <div class="control-row">
      <div class="btn-group">
        <button class="button primary" id="sim-play" title="시뮬레이션 재생">
          <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          <span>재생 (Play)</span>
        </button>
        <button class="button" id="sim-pause" title="일시정지" disabled>
          <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
          <span>정지 (Pause)</span>
        </button>
        <button class="button" id="sim-step" title="1스텝 전진">
          <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19" stroke="currentColor" stroke-width="2.5"/></svg>
          <span>스텝 (Step)</span>
        </button>
        <button class="button" id="sim-reset" title="초기화">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><polyline points="3 3 3 8 8 8"/></svg>
          <span>리셋 (Reset)</span>
        </button>
      </div>

      <div class="speed-group">
        <span class="ctrl-label">배속:</span>
        <button class="speed-btn" data-speed="0.5">0.5×</button>
        <button class="speed-btn active" data-speed="1.0">1.0×</button>
        <button class="speed-btn" data-speed="2.0">2.0×</button>
        <button class="speed-btn" data-speed="5.0">5.0×</button>
      </div>

      <div class="scrubber-group">
        <span class="ctrl-label">타임라인:</span>
        <input type="range" id="timeline-scrubber" min="0" max="30" step="0.1" value="0">
        <output id="sim-time-display">t = 0.00 s / 30.0 s</output>
      </div>

      <div class="solver-badge-group">
        <span class="badge ready" id="solver-badge">SOLVER READY</span>
      </div>
    </div>
  </section>
"""
    
    # 3. New Studio Page (PAGE 1: LAB) with 6 Panels:
    # P1 (Input/Scenario), P2 (Method/Operation), P6 (3D Visualization), P3 (Flight & Control), P4 (Fire & Environment), P7 (Performance Dashboard)
    studio_html = """  <!-- PAGE 1: LAB (통합 시뮬레이션 스튜디오 워크벤치) -->
  <section class="page active" id="page-lab">
""" + sim_ctrl_bar + """
    <div class="studio-grid">
      <!-- Left Column: P1 Input/Scenario & P2 Method/Operation -->
      <div class="studio-col">
        <!-- [필수 1] Input/Scenario Panel -->
        <section class="panel" id="panel-scenario">
          <div class="panel-head">
            <div>
              <span class="eyebrow">INPUT / SCENARIO</span>
              <h2>계산 시나리오 설정</h2>
            </div>
            <span class="badge ready">CONFIG VERIFIED</span>
          </div>
          
          <div class="preset-pills">
            <span class="ctrl-label">빠른 프리셋:</span>
            <button class="pill active" data-preset="nominal">Steckler 표준</button>
            <button class="pill" data-preset="crosswind">강풍 (4.5m/s)</button>
            <button class="pill" data-preset="latency">지연 (250ms)</button>
            <button class="pill" data-preset="close">초근접 (0.6m)</button>
          </div>

          <label class="slider-label" for="distance">장치–표적 거리 <output id="distance-out">1.0 m</output></label>
          <input id="distance" type="range" min="0.2" max="3.0" step="0.1" value="1.0">

          <label class="slider-label" for="wind">주변 횡풍 풍속 <output id="wind-out">0.2 m/s</output></label>
          <input id="wind" type="range" min="0" max="5.0" step="0.1" value="0.2">

          <label class="slider-label" for="duration">미션 지속 시간 <output id="duration-out">4 s</output></label>
          <input id="duration" type="range" min="1" max="30" step="1" value="4">
        </section>

        <!-- [필수 2] Method/Operation Panel -->
        <section class="panel" id="panel-method">
          <div class="panel-head">
            <div>
              <span class="eyebrow">METHOD / OPERATION</span>
              <h2>소화 방식 및 운용 사양</h2>
            </div>
            <div class="mode-select-wrap">
              <select id="op-mode" aria-label="운용 모드">
                <option value="single">단독 운용 (Single)</option>
                <option value="simultaneous">동시 복합 (Simultaneous)</option>
                <option value="sequential">순차 복합 (Sequential)</option>
              </select>
            </div>
          </div>

          <div class="method-grid" id="method-grid"></div>

          <div class="eyebrow" id="device-label" style="margin-top:14px;">DEVICE ACTUATORS</div>
          <div id="device-fields" class="input-grid"></div>

          <div class="resource-ledger" id="power-mass-ledger">
            <div class="ledger-item"><span>장치 정격 전력:</span><strong id="ledger-power">80 W</strong></div>
            <div class="ledger-item"><span>약제 적재 중량:</span><strong id="ledger-mass">0.0 kg</strong></div>
            <div class="ledger-item"><span>반력 특성:</span><strong id="ledger-reaction">0.0017 N (Mean)</strong></div>
          </div>
        </section>
      </div>

      <!-- Center Column: [필수 6] 3D Visualization Panel -->
      <div class="studio-col center-col">
        <section class="panel visual-panel" id="panel-visual">
          <div class="panel-head">
            <div>
              <span class="eyebrow">3D SPATIAL VECTOR & FLAME VIEWPORT</span>
              <h2 id="field-title">드론 기체 및 연성 유동장 3D 뷰</h2>
            </div>
            <div class="cam-presets">
              <button class="cam-btn active" data-cam="iso">등각 (Iso)</button>
              <button class="cam-btn" data-cam="top">상단 (Top)</button>
              <button class="cam-btn" data-cam="front">정면 (Front)</button>
              <button class="cam-btn" data-cam="side">측면 (Side)</button>
              <button class="cam-btn" id="reset-view" title="시점 초기화">리셋</button>
            </div>
          </div>
          
          <div class="canvas-wrap">
            <canvas id="field-canvas" aria-label="3차원 속도장 및 드론 기체 뷰"></canvas>
            <div class="canvas-corner">
              SPATIAL DELIVERY & PLUME FIELD
              <span id="field-snapshot">계산 대기</span>
            </div>
            <div class="overlay-toggles">
              <label><input type="checkbox" id="toggle-streamlines" checked> 유선 (Streamlines)</label>
              <label><input type="checkbox" id="toggle-plume" checked> 화재 플룸 (Plume)</label>
              <label><input type="checkbox" id="toggle-rotors" checked> 로터 다운워시</label>
            </div>
            <div class="empty-overlay" id="field-empty">
              <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>
              <h3>3D 유동장 대기 중</h3>
              <p>[시뮬레이션 실행] 또는 [재생]을 클릭하여 3차원 유동을 관측하세요.</p>
            </div>
          </div>

          <div class="field-footer">
            <span><i class="legend-dot" style="background:var(--accent)"></i>유동 벡터 (속도 비례)</span>
            <span><i class="legend-dot" style="background:#ef4444"></i>화재 부력 플룸</span>
            <span><i class="legend-dot" style="background:#f59e0b"></i>표적 원반 (Target Disc)</span>
            <span id="field-scale">속도 스케일 m/s</span>
          </div>
        </section>
      </div>

      <!-- Right Column: [필수 3] Flight & Control & [필수 4] Fire & Environment -->
      <div class="studio-col">
        <!-- [필수 3] Flight & Control Panel -->
        <section class="panel" id="panel-flight">
          <div class="panel-head">
            <div>
              <span class="eyebrow">FLIGHT & CONTROL</span>
              <h2>드론 기체 및 6-DOF 제어</h2>
            </div>
            <span class="badge">NEWTON-EULER</span>
          </div>
          
          <div class="flight-grid">
            <div class="input-row">
              <label for="drone-mass">기체 건조중량 [kg]:</label>
              <input id="drone-mass" type="number" step="0.1" value="3.2" min="1.0" max="10.0">
            </div>
            <div class="input-row">
              <label for="pid-kp">위치 제어 P-Gain ($K_p$):</label>
              <input id="pid-kp" type="number" step="0.1" value="1.2" min="0.1" max="5.0">
            </div>
            <div class="input-row">
              <label for="sensor-latency">센서 지연 $\\tau_{delay}$ [s]:</label>
              <input id="sensor-latency" type="number" step="0.05" value="0.10" min="0.0" max="0.50">
            </div>
          </div>

          <div class="telemetry-box">
            <div class="eyebrow">LIVE FLIGHT TELEMETRY</div>
            <div class="telemetry-grid">
              <div><span>위치 오차:</span><strong id="telem-pos">0.05 m</strong></div>
              <div><span>기체 롤/피치:</span><strong id="telem-tilt">0.42°</strong></div>
              <div><span>로터 추력:</span><strong id="telem-thrust">31.4 N</strong></div>
              <div><span>배터리 전압:</span><strong id="telem-volt">22.2 V</strong></div>
            </div>
          </div>
        </section>

        <!-- [필수 4] Fire & Environment Panel -->
        <section class="panel" id="panel-fire">
          <div class="panel-head">
            <div>
              <span class="eyebrow">FIRE & ENVIRONMENT</span>
              <h2>화재 물리 및 대기 환경</h2>
            </div>
            <span class="badge warning">STECKLER PLUME</span>
          </div>

          <label class="slider-label" for="fire-hrr">화재 열방출률 (HRR) <output id="fire-hrr-out">50 kW</output></label>
          <input id="fire-hrr" type="range" min="10" max="150" step="5" value="50">

          <div class="env-metrics-grid">
            <article>
              <span>플룸 중심 상승속도</span>
              <strong id="plume-vel">3.72 m/s</strong>
              <small>Heskestad 부력 적분</small>
            </article>
            <article>
              <span>드론 위치 열유속</span>
              <strong id="drone-flux">0.95 kW/m²</strong>
              <small>복사 점원 모델</small>
            </article>
            <article>
              <span>기체 예측 온도</span>
              <strong id="drone-temp">32.4 °C</strong>
              <small>집중 열용량 과도 적분</small>
            </article>
            <article>
              <span>화염 높이 ($L_f$)</span>
              <strong id="flame-height">0.82 m</strong>
              <small>부력 연소 영역</small>
            </article>
          </div>
        </section>
      </div>
    </div>

    <!-- Bottom Full-Width: [필수 7] Performance Dashboard -->
    <section class="panel dashboard-panel" id="panel-dashboard">
      <div class="panel-head">
        <div>
          <span class="eyebrow">PERFORMANCE DASHBOARD</span>
          <h2>실시간 성능 지표 및 다채널 오실로스코프</h2>
        </div>
        <div class="channel-toggles">
          <label><input type="checkbox" class="chan-toggle" data-chan="hrr" checked> HRR (kW)</label>
          <label><input type="checkbox" class="chan-toggle" data-chan="pos" checked> 위치오차 (m)</label>
          <label><input type="checkbox" class="chan-toggle" data-chan="tilt" checked> 자세각 (deg)</label>
          <label><input type="checkbox" class="chan-toggle" data-chan="rx" checked> 반력 (N)</label>
          <label><input type="checkbox" class="chan-toggle" data-chan="power" checked> 소비전력 (W)</label>
          <label><input type="checkbox" class="chan-toggle" data-chan="battery" checked> 배터리 (Wh)</label>
        </div>
      </div>

      <div class="metrics-strip">
        <article>
          <span>소화 소요 시간</span>
          <strong id="kpi-time">—</strong>
          <small>HRR 95% 저감 기준</small>
        </article>
        <article>
          <span>HRR 저감율</span>
          <strong id="kpi-hrr-drop">—</strong>
          <small>기저 화재 대비</small>
        </article>
        <article>
          <span>최대 위치 추종 오차</span>
          <strong id="kpi-error">—</strong>
          <small>외란 및 반력 섭동</small>
        </article>
        <article>
          <span>총 미션 에너지</span>
          <strong id="kpi-energy">—</strong>
          <small>추진 + 소화 장치</small>
        </article>
        <article>
          <span>약제 전달 질량비</span>
          <strong id="kpi-delivery">—</strong>
          <small>표적 도달 분율</small>
        </article>
        <article>
          <span>드론 최고 온도</span>
          <strong id="kpi-temp">—</strong>
          <small>과도 복사 가열</small>
        </article>
      </div>

      <div class="chart-box">
        <canvas class="chart" id="dashboard-chart" style="height:260px;" aria-label="다채널 동기화 시계열 차트"></canvas>
      </div>
      <div id="model-note" class="model-note">계산 결과의 지배방정식 및 모델 가정이 여기에 표시됩니다.</div>
    </section>
  </section>
"""
    
    # Replace existing page-lab and page-drone with the new integrated studio and dedicated pages
    # Let's define the other dedicated pages:
    # page-comparison ([필수 8])
    comparison_page = """  <!-- [필수 8] Comparison Panel (방식별 비교 분석 패널) -->
  <section class="page" id="page-comparison">
    <div class="comparison-layout">
      <section class="panel">
        <div class="panel-head">
          <div>
            <span class="eyebrow">5-AXIS NORMALIZED BENCHMARK</span>
            <h2>5개 소화 방식 다차원 Radar 비교</h2>
          </div>
          <span class="badge ready">NORMALIZED RADAR</span>
        </div>
        <canvas id="radar-canvas" style="width:100%; height:340px;"></canvas>
        <div class="radar-legend">
          <span><i class="legend-dot" style="background:var(--m1-color)"></i>M1 음향</span>
          <span><i class="legend-dot" style="background:var(--m2-color)"></i>M2 와류링</span>
          <span><i class="legend-dot" style="background:var(--m3-color)"></i>M3 수분무</span>
          <span><i class="legend-dot" style="background:var(--m4-color)"></i>M4 에어로졸</span>
          <span><i class="legend-dot" style="background:var(--m5-color)"></i>M5 전도성와류</span>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <span class="eyebrow">PAIRWISE COUPLING</span>
            <h2>복합 운용 상호보완성 Matrix Heatmap</h2>
          </div>
          <span class="badge">SYNERGY INDEX</span>
        </div>
        <canvas id="synergy-canvas" style="width:100%; height:340px;"></canvas>
        <p class="hint">시너지 지수 S > 1.0은 단순 선형 합산을 초과하는 비선형 결합 이득을 나타냅니다 (M2+M4 최고 시너지: 1.42).</p>
      </section>
    </div>

    <section class="panel">
      <div class="panel-head">
        <div>
          <span class="eyebrow">CROSS-METHOD COMPARISON TABLE</span>
          <h2>소화 방식별 핵심 물리 및 비행 지표 종합 비교</h2>
        </div>
        <button class="button small" id="compare-csv-export">비교표 CSV 내보내기</button>
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>소화 방식</th>
              <th>작동 원리</th>
              <th>정격 전력</th>
              <th>피크 반력</th>
              <th>소화 속도 지수</th>
              <th>총 미션 에너지</th>
              <th>최대 위치 오차</th>
              <th>종합 판정</th>
            </tr>
          </thead>
          <tbody id="comparison-table-body"></tbody>
        </table>
      </div>
    </section>
  </section>
"""

    # page-editor ([필수 9])
    editor_page = """  <!-- [필수 9] Scenario Editor (시나리오 에디터) -->
  <section class="page" id="page-editor">
    <div class="editor-layout">
      <!-- Visual Phase Editor -->
      <section class="panel">
        <div class="panel-head">
          <div>
            <span class="eyebrow">VISUAL MISSION PHASE BUILDER</span>
            <h2>미션 단계별 시계열 인터랙티브 빌더</h2>
          </div>
          <button class="button small primary" id="apply-visual-phase">페이즈 적용</button>
        </div>
        
        <div class="phase-builder">
          <div class="phase-card" data-phase="takeoff">
            <div class="phase-header">
              <strong>1. 이륙 및 접근 (Takeoff & Ingress)</strong>
              <output id="phase-dur-1">0 ~ 8 s (8 s)</output>
            </div>
            <input type="range" class="phase-range" id="range-p1" min="2" max="15" value="8">
            <small>화점 전방 2m 지점까지 등속 상승 및 수평 기동</small>
          </div>

          <div class="phase-card" data-phase="station">
            <div class="phase-header">
              <strong>2. 정밀 호버링 고정 (Station-Keeping)</strong>
              <output id="phase-dur-2">8 ~ 12 s (4 s)</output>
            </div>
            <input type="range" class="phase-range" id="range-p2" min="1" max="10" value="4">
            <small>센서 피드백 기반 위치오차 0.1m 이내 안정화</small>
          </div>

          <div class="phase-card" data-phase="suppress">
            <div class="phase-header">
              <strong>3. 주 소화 집중 방사 (Primary Suppression)</strong>
              <output id="phase-dur-3">12 ~ 24 s (12 s)</output>
            </div>
            <input type="range" class="phase-range" id="range-p3" min="2" max="25" value="12">
            <small>소화 액추에이터 최대 출력 투입 및 화염 타격</small>
          </div>

          <div class="phase-card" data-phase="cooling">
            <div class="phase-header">
              <strong>4. 잔불 냉각 및 감시 (Cooling & Monitor)</strong>
              <output id="phase-dur-4">24 ~ 34 s (10 s)</output>
            </div>
            <input type="range" class="phase-range" id="range-p4" min="2" max="20" value="10">
            <small>재발화 방지를 위한 저유량 냉각 유지</small>
          </div>

          <div class="phase-card" data-phase="egress">
            <div class="phase-header">
              <strong>5. 안전 기지 복귀 (Egress & Land)</strong>
              <output id="phase-dur-5">34 ~ 45 s (11 s)</output>
            </div>
            <input type="range" class="phase-range" id="range-p5" min="3" max="20" value="11">
            <small>배터리 잔여량 20% 이상 확보 상태에서 복귀</small>
          </div>
        </div>
      </section>

      <!-- Two-way JSON Code Editor -->
      <section class="panel">
        <div class="panel-head">
          <div>
            <span class="eyebrow">SCHEMA-VALIDATED JSON CODE</span>
            <h2>양방향 사양 JSON 에디터</h2>
          </div>
          <div style="display:flex; gap:8px;">
            <button class="button small" id="editor-format">서식 정리</button>
            <button class="button small primary" id="apply-json-btn">실시간 검증 및 적용</button>
          </div>
        </div>
        <textarea id="scenario-json-editor" spellcheck="false" style="width:100%; height:380px; font-family:var(--font-mono); font-size:12px; padding:14px; background:#0f172a; color:#f8fafc; border-radius:8px; border:1px solid #334155;"></textarea>
        <div class="editor-footer" style="display:flex; justify-content:space-between; align-items:center; margin-top:8px;">
          <span id="json-lint-status" class="badge ready">JSON VALID</span>
          <small class="hint">수정 시 <code>/api/validate</code>를 통해 물리적 유한성이 검증됩니다.</small>
        </div>
      </section>
    </div>
  </section>
"""

    # page-optimize ([선택 1])
    optimize_page = """  <!-- [선택 1] Optimization Panel (다목적 Pareto 최적화 패널) -->
  <section class="page" id="page-optimize">
    <div class="optimize-layout">
      <section class="panel optimize-ctrl">
        <div class="panel-head">
          <div>
            <span class="eyebrow">MULTI-OBJECTIVE OPTIMIZATION</span>
            <h2>Pareto 최적 동작점 탐색</h2>
          </div>
          <span class="badge ready">NSGA-II / GRID</span>
        </div>
        
        <p class="section-copy">소화 시간($\\min t_{ext}$), 비행 에너지($\\min E_{tot}$), 위치 오차($\\min e_{max}$), 약제 전달 효율($\\max \\eta$) 간의 상충 관계를 동시 최적화합니다.</p>

        <div class="input-grid">
          <div>
            <label for="opt-methods">대상 소화 방식:</label>
            <select id="opt-methods" multiple style="height:90px; width:100%;">
              <option value="M1" selected>M1 저주파 음향</option>
              <option value="M2" selected>M2 와류링</option>
              <option value="M3" selected>M3 수분무</option>
              <option value="M4" selected>M4 에어로졸</option>
              <option value="M5" selected>M5 전도성와류</option>
            </select>
          </div>
          <div>
            <label for="opt-wind">가정 횡풍 풍속 [m/s]:</label>
            <input id="opt-wind" type="number" step="0.5" value="1.5">
            <label for="opt-dist-min" style="margin-top:8px;">이격거리 탐색 범위 [m]:</label>
            <div style="display:flex; gap:6px;">
              <input id="opt-dist-min" type="number" step="0.2" value="0.8" style="width:50%;">
              <input id="opt-dist-max" type="number" step="0.2" value="2.5" style="width:50%;">
            </div>
          </div>
        </div>

        <button class="button primary" id="run-opt-btn" style="width:100%; margin-top:14px;">다목적 Pareto 최적화 계산 실행</button>
        <div id="opt-progress" class="progress-track" style="margin-top:10px;" hidden><i id="opt-prog-fill"></i></div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <span class="eyebrow">PARETO FRONTIER SCATTER</span>
            <h2>파레토 최적해 분산도 (에너지 vs 소화시간 vs 오차)</h2>
          </div>
          <span class="badge ready" id="opt-count-badge">대기 중</span>
        </div>
        <canvas id="pareto-canvas" style="width:100%; height:320px;"></canvas>
        <div class="field-footer">
          <span><i class="legend-dot" style="background:#22c55e"></i>Pareto Front 해</span>
          <span><i class="legend-dot" style="background:#ef4444"></i>지배당한 해 (Dominated)</span>
          <span><i class="legend-dot" style="background:#3b82f6; width:12px; height:12px;"></i>Knee Point (최적 절충점)</span>
        </div>
      </section>
    </div>

    <section class="panel" id="opt-result-panel">
      <div class="panel-head">
        <div>
          <span class="eyebrow">CANDIDATE SOLUTIONS</span>
          <h2>Pareto 최적 후보군 상세 명세 및 스튜디오 적용</h2>
        </div>
        <button class="button small" id="apply-knee-btn" disabled>★ Knee Point 최적 조건을 스튜디오에 적용</button>
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>후보 ID</th>
              <th>방식</th>
              <th>최적 거리 [m]</th>
              <th>소화 출력 [W]</th>
              <th>소화 시간 [s]</th>
              <th>미션 에너지 [Wh]</th>
              <th>최대 오차 [m]</th>
              <th>도달 효율 [%]</th>
              <th>선택</th>
            </tr>
          </thead>
          <tbody id="pareto-table-body">
            <tr><td colspan="9" style="text-align:center; color:var(--muted); padding:20px;">[다목적 Pareto 최적화 계산 실행] 버튼을 클릭하세요.</td></tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
"""

    # page-montecarlo ([선택 2])
    montecarlo_page = """  <!-- [선택 2] Uncertainty / Monte Carlo Panel (불확실성 및 몬테카를로 분석 패널) -->
  <section class="page" id="page-montecarlo">
    <div class="optimize-layout">
      <section class="panel">
        <div class="panel-head">
          <div>
            <span class="eyebrow">STOCHASTIC SAMPLING SETUP</span>
            <h2>불확실성 파라미터 확률분포 설정</h2>
          </div>
          <span class="badge ready">LATIN HYPERCUBE</span>
        </div>

        <div class="input-grid">
          <div>
            <label for="mc-method">분석 대상 방식:</label>
            <select id="mc-method">
              <option value="M3" selected>M3 수분무 (Droplet Spray)</option>
              <option value="M1">M1 저주파 음향</option>
              <option value="M2">M2 공기 와류링</option>
              <option value="M4">M4 고체 에어로졸</option>
              <option value="M5">M5 전도성 와류 EHD</option>
            </select>
          </div>
          <div>
            <label for="mc-samples">샘플 횟수 N (20 ~ 200회):</label>
            <input id="mc-samples" type="number" step="10" value="50" min="20" max="200">
          </div>
          <div>
            <label for="mc-wind-std">횡풍 표준편차 σ [m/s]:</label>
            <input id="mc-wind-std" type="number" step="0.1" value="0.6">
          </div>
          <div>
            <label for="mc-lat-max">센서 지연 상한 [s]:</label>
            <input id="mc-lat-max" type="number" step="0.05" value="0.25">
          </div>
        </div>

        <button class="button primary" id="run-mc-btn" style="width:100%; margin-top:14px;">몬테카를로 불확실성 해석 실행</button>
        <div id="mc-progress" class="progress-track" style="margin-top:10px;" hidden><i id="mc-prog-fill"></i></div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <span class="eyebrow">EXTINCTION PROBABILITY</span>
            <h2>소화 성공 확률 및 95% 신뢰구간</h2>
          </div>
          <span class="badge ready" id="mc-prob-badge">—</span>
        </div>
        
        <div class="mc-kpi-row">
          <div class="mc-kpi-card">
            <span>성공 확률 P(Quench)</span>
            <strong id="mc-p-val">—</strong>
            <small>제약조건 동시 만족</small>
          </div>
          <div class="mc-kpi-card">
            <span>95% Bootstrap CI</span>
            <strong id="mc-ci-val">[— , —]</strong>
            <small>1,000회 리샘플링</small>
          </div>
        </div>

        <div class="chart-box" style="margin-top:14px;">
          <span class="eyebrow">소화 시간 확률 밀도 히스토그램</span>
          <canvas id="mc-hist-canvas" style="width:100%; height:180px;"></canvas>
        </div>
      </section>
    </div>

    <!-- Sensitivity Tornado -->
    <section class="panel">
      <div class="panel-head">
        <div>
          <span class="eyebrow">GLOBAL SENSITIVITY INDICES</span>
          <h2>주요 불확실성 인자 영향도 순위 (Tornado Chart)</h2>
        </div>
      </div>
      <canvas id="tornado-canvas" style="width:100%; height:220px;"></canvas>
    </section>
  </section>
"""

    # page-export ([필수 10])
    export_page = """  <!-- [필수 10] Result Export Panel (결과 및 고해상도 차트 내보내기) -->
  <section class="page" id="page-export">
    <!-- One-Click Deliverable Download Banner -->
    <section class="panel export-banner">
      <div class="banner-content">
        <div>
          <span class="eyebrow">COMPREHENSIVE RESEARCH ARCHIVE</span>
          <h2>연구 산출물 종합 압축팩 (firefield_research_results.zip)</h2>
          <p>10종 학술 고정밀 시각화 차트(300 DPI PNG), FDS CFD 시계열, 6-DOF 동역학 원시 데이터(15MB), 종합 보고서가 모두 집약된 완전한 패키지입니다.</p>
        </div>
        <div class="banner-actions">
          <a class="button primary large" href="/download/research_results" download>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            종합 연구 결과 ZIP 내려받기 (12.4 MB)
          </a>
          <span class="badge ready">SHA-256 VERIFIED</span>
        </div>
      </div>
    </section>

    <!-- 10-Figure Gallery -->
    <section class="panel">
      <div class="panel-head">
        <div>
          <span class="eyebrow">PUBLICATION-READY SCIENTIFIC FIGURES</span>
          <h2>10대 학술 고정밀 시각화 차트 갤러리 (8개 필수 + 2개 선택)</h2>
        </div>
      </div>

      <div class="figure-grid" id="figure-gallery">
        <!-- Figures will be dynamically populated or pre-rendered -->
      </div>
    </section>

    <!-- CSV and Reports -->
    <div class="data-layout">
      <section class="panel">
        <div class="panel-head">
          <div>
            <span class="eyebrow">RAW NUMERICAL DATASETS</span>
            <h2>정밀 수치 CSV 데이터셋</h2>
          </div>
        </div>
        <div class="download-list">
          <a class="download-item" href="/api/campaign/study_latest/drone_mission_series.csv" download>
            <strong>drone_mission_series.csv</strong>
            <span>34초 전구간 6-DOF 자세·위치·추력 0.05초 단위 원시 시계열 (15.0 MB)</span>
          </a>
          <a class="download-item" href="/api/campaign/study_latest/case_matrix.csv" download>
            <strong>case_matrix.csv</strong>
            <span>36개 실험 조건 매트릭스 및 투입 자원량 (1.3 KB)</span>
          </a>
          <a class="download-item" href="/api/campaign/study_latest/drone_feasibility.csv" download>
            <strong>drone_feasibility.csv</strong>
            <span>기체 탑재 타당성 및 전력/에너지 판정표 (6.0 KB)</span>
          </a>
          <a class="download-item" href="/api/campaign/study_latest/interaction_matrix.csv" download>
            <strong>interaction_matrix.csv</strong>
            <span>방식별 상호보완 시너지 계수 매트릭스 (0.1 KB)</span>
          </a>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <span class="eyebrow">ACADEMIC REPORTS</span>
            <h2>학술대회 및 전람회 출품 보고서</h2>
          </div>
        </div>
        <div class="download-list">
          <a class="download-item" href="/api/campaign/study_latest/drone_feasibility.html" target="_blank">
            <strong>drone_feasibility.html / .md</strong>
            <span>드론 기체 6-DOF 탑재 타당성 및 제어성 평가서</span>
          </a>
          <a class="download-item" href="/api/campaign/study_latest/method_comparison.html" target="_blank">
            <strong>method_comparison.html / .md</strong>
            <span>5개 소화 방식별 물리 전달장 및 자원 수지 비교 보고서</span>
          </a>
          <a class="download-item" href="/physics.md" target="_blank">
            <strong>physics_derivation.md</strong>
            <span>제1원리 지배방정식 및 물리 보존식 엄밀 유도집</span>
          </a>
        </div>
      </section>
    </div>
  </section>
"""

    # Assemble: replace page-lab and page-drone with studio, comparison, editor, optimize, montecarlo, export
    # Notice page-physics starts at `<!-- PAGE 3: PHYSICS DERIVATIONS`
    prefix = raw[:raw.find('<!-- PAGE 1: LAB')]
    suffix = raw[raw.find('<!-- PAGE 3: PHYSICS DERIVATIONS'):]
    
    new_html = prefix + studio_html + comparison_page + editor_page + optimize_page + montecarlo_page + export_page + suffix
    INDEX_PATH.write_text(new_html, encoding="utf-8")
    print(f"Successfully generated new web/index.html ({len(new_html)} chars)")

if __name__ == "__main__":
    generate_index_html()
