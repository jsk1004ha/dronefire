# -*- coding: utf-8 -*-
"""
삼성휴먼테크 33회 Extended Abstract - 본론(Body) 전용 빌더
- 서론 및 결론 제외, 본론(2장 이론 및 수치 모델 + 3장 결과 및 고찰)만 심층 작성
- 시각자료 7번(시너지 매트릭스 / 복사열유속 비교) 완전 제외
- Table 1 + Fig. 1 (D4 제어 응답) + Fig. 2 (횡풍·센서지연 매트릭스) + Fig. 3 (FDS HRR)
- 2단 편집 (간격 ~7.05 mm), 바탕체 / Times New Roman, A4 규격 여백
- 분량: 정확히 약 1.5페이지 (Page 2에서 종료, 2페이지 이내 엄수)
"""
import os, sys, shutil
from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


def make_rFonts(kr="바탕체", en="Times New Roman"):
    rf = OxmlElement('w:rFonts')
    rf.set(qn('w:ascii'), en)
    rf.set(qn('w:hAnsi'), en)
    rf.set(qn('w:eastAsia'), kr)
    rf.set(qn('w:cs'), en)
    return rf


def add_run(p, text, size=10, bold=False, italic=False,
            kr="바탕체", en="Times New Roman"):
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    run.font.name = en
    rPr = run._element.get_or_add_rPr()
    for old in rPr.findall(qn('w:rFonts')):
        rPr.remove(old)
    rPr.insert(0, make_rFonts(kr, en))
    return run


def fmt(p, align=WD_ALIGN_PARAGRAPH.JUSTIFY, sb=0, sa=0, ls=1.0):
    pf = p.paragraph_format
    pf.alignment = align
    pf.space_before = Pt(sb)
    pf.space_after = Pt(sa)
    pf.line_spacing = ls
    pPr = p._element.get_or_add_pPr()
    sp = pPr.find(qn('w:spacing'))
    if sp is None:
        sp = OxmlElement('w:spacing')
        pPr.append(sp)
    sp.set(qn('w:line'), str(int(ls * 240)))
    sp.set(qn('w:lineRule'), 'auto')


def heading(doc, text, level=1):
    p = doc.add_paragraph()
    sb = 4 if level == 1 else 2.5
    sa = 1.0
    fmt(p, align=WD_ALIGN_PARAGRAPH.LEFT, sb=sb, sa=sa)
    add_run(p, text, size=11, bold=True)
    return p


def body(doc, text):
    p = doc.add_paragraph()
    fmt(p, align=WD_ALIGN_PARAGRAPH.JUSTIFY, sb=0, sa=0)
    add_run(p, text, size=10)
    return p


def caption(doc, text):
    """표(상단) 및 그림(하단) 캡션: 9pt 굵게, 왼쪽 정렬"""
    p = doc.add_paragraph()
    fmt(p, align=WD_ALIGN_PARAGRAPH.LEFT, sb=1.0, sa=1.5)
    add_run(p, text, size=9, bold=True)
    return p


def set_cols(section, num=2, space_twips=400):
    sectPr = section._sectPr
    for c in sectPr.findall(qn('w:cols')):
        sectPr.remove(c)
    cols = OxmlElement('w:cols')
    cols.set(qn('w:num'), str(num))
    cols.set(qn('w:space'), str(space_twips))
    sectPr.append(cols)


def set_cell_font(cell, text, size=8.0, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.bold = bold
    run.font.name = "Times New Roman"
    rPr = run._element.get_or_add_rPr()
    for old in rPr.findall(qn('w:rFonts')):
        rPr.remove(old)
    rPr.insert(0, make_rFonts("바탕체", "Times New Roman"))
    tcPr = cell._element.get_or_add_tcPr()
    mar = OxmlElement('w:tcMar')
    for side in ['top', 'bottom', 'left', 'right']:
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:w'), '15')
        el.set(qn('w:type'), 'dxa')
        mar.append(el)
    tcPr.append(mar)


def shade_cell(cell, color):
    tcPr = cell._element.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:fill'), color)
    shd.set(qn('w:val'), 'clear')
    tcPr.append(shd)


def add_figure(doc, img_path, width_cm=7.0):
    p = doc.add_paragraph()
    fmt(p, align=WD_ALIGN_PARAGRAPH.CENTER, sb=1.5, sa=0)
    run = p.add_run()
    run.add_picture(img_path, width=Cm(width_cm))
    return p


def build_body_document(out_path=None):
    if out_path is None:
        base = r"C:\Users\js100\Desktop\학교\서B전람회"
        out_path = os.path.join(base, "삼성휴먼테크_33회_본론.docx")

    fig_dir = r"C:\Users\js100\Desktop\학교\서B전람회\paper_figs"

    doc = Document()

    # 기본 문서 스타일
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(10)
    style.paragraph_format.space_before = Pt(0)
    style.paragraph_format.space_after = Pt(0)
    style.paragraph_format.line_spacing = 1.0
    rPr = style.element.get_or_add_rPr()
    for old in rPr.findall(qn('w:rFonts')):
        rPr.remove(old)
    rPr.insert(0, make_rFonts())

    # 페이지 설정 (A4: 21.0 x 29.7 cm, 규격 여백)
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(3.0)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(1.5)
    section.right_margin = Cm(1.5)
    section.header_distance = Cm(2.0)
    section.footer_distance = Cm(1.0)

    # 2단 편집 (단간 간격 400 twips ≈ 7.05 mm)
    set_cols(section, 2, 400)

    # 머리글: "33rd Humantech Paper Awards" (9pt, 오른쪽 정렬)
    header = section.header
    header.is_linked_to_previous = False
    hp = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    hp.clear()
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    add_run(hp, "33rd Humantech Paper Awards", size=9)

    # ════════════════════════════════════════════════════════
    # 2. 이론 및 수치 모델
    # ════════════════════════════════════════════════════════
    heading(doc, "2. 이론 및 수치 모델", level=1)

    heading(doc, "2.1. 저주파 음향 화염 교란 메커니즘 (M1)", level=2)
    body(doc,
        "저주파 음향 소화는 개구 면적 A = π(D/2)² (D = 0.15 m), 주파수 f = 60 Hz 피스톤 음원에서 방사된 "
        "주기적 압력파가 화염 기저에 음향류(acoustic streaming)를 형성하여 혼합층을 기계적으로 교란·소멸시키는 "
        "원리에 기반한다. 유효 방사 음향 출력은 장치 인가 전력 P_device = 80 W를 초과할 수 없으므로 "
        "P_acoustic = min(ρ₀ c u²_req A, P_device)로 상한을 제한한다(ρ₀ = 1.204 kg/m³, c = 343.0 m/s). "
        "이격거리 r에서의 표적 유도 입자 속도는 원점 특이점을 개구 면적 A로 정규화한 Rayleigh 구면파 전이 모델 "
        "u_rms(r) = u_source √(A / (A + 2πr²))로 산출하며, 화염 스트레인율 a = |∇u| ≥ a_crit ≈ 250 s⁻¹ 조건에서 "
        "국부 소멸이 유도된다. 기체 반력은 반구 운동량 수지로부터 F_rad = P_acoustic / (2c) = 0.0017 N으로 도출된다.")

    heading(doc, "2.2. 고속 공기 와류 링 사출 및 궤적 역학 (M2)", level=2)
    body(doc,
        "펄스 와류 링은 노즐 반경 R = 0.05 m, 사출 속도 U₀ = 8.0 m/s, 펄스 시간 T = 0.05 s 슬러그 유동의 "
        "전단층 롤업으로 생성된다. 무차원 스트로크 비 L/D = U₀T/(2R) = 4.0은 Gharib의 핀치오프 상한에 정합한다. "
        "슬러그 순환 Γ_slug = ½U₀²T에 롤업 효율 η_circ = 0.35를 적용한 유효 순환 Γ = η_circ Γ_slug와 "
        "Saffman의 점성 코어 모델로부터 병진 속도 U_ring(t) = [Γ/(4πR)][ln(8R/a(t)) − 0.558]을 적분한다. "
        "점성 코어 반경은 a(t) = √(a₀² + 4νt) (ν = 1.51×10⁻⁵ m²/s)이며, 링 운동에너지는 슬러그 에너지 "
        "E = ½ρ₀πR²U₀³T 이하로 제한된다. 횡풍 편향(y = U_cross · t)을 연립한 궤적에서 사출 피크 반력은 "
        "F_peak = ρ₀ A U₀² = 0.605 N이며, 1.0 m 도달 속도 2.01 m/s로 층류 연소속도를 압도하여 대류 소염을 달성한다.")

    heading(doc, "2.3. 이상(Two-Phase) 입자 수송 및 증발 냉각 (M3, M4, M5)", level=2)
    body(doc,
        "수분무(M3, d₃₂ = 100 μm), 에어로졸(M4, d = 5 μm), 전도성 와류(M5, d = 10 μm)의 입자군은 "
        "Lagrangian 운동량 방정식으로 추적한다. 항력 계수는 Schiller-Naumann 식 C_D = (24/Re_p)(1 + 0.15Re_p^0.687)를 "
        "적용하고, 해석적 완화 적분기 v_p(t+Δt) = u_g + [v_p(t) − u_g]exp(−Δt / τ_p)로 수치 강성을 제거하였다. "
        "수분무 증발은 Maxwell d²-법칙 d²(t+Δt) = d²(t) − KΔt로 모사하고 기화 잠열 Q̇ = ṁ_evap · 2.45×10⁶ J/kg를 "
        "에너지 장부에 연계하였다. M4는 칼륨 분해물의 라디칼 포획(K+OH→KOH)으로 연쇄 반응을 차단하며, "
        "M5는 Poisson 전위식 ∇²φ = −ρ_e/ε₀과 체적력 f_e = ρ_e E로 전계 유도 와류 안정화를 모사한다.")

    heading(doc, "2.4. 쿼드콥터 6자유도 비행 동역학 및 외란 보정 제어", level=2)
    body(doc,
        "쿼드콥터(자중 2.0 kg, 로터 반경 0.12 m × 4)는 쿼터니언 기반 Newton-Euler 식 "
        "m(t)p̈ = TR(q)e₃ + F_reaction + F_drag − m(t)ge₃ 및 Iω̇ + ω×(Iω) = τ_ctrl + τ_reaction으로 기술된다. "
        "항력 계수는 C_D A_D = 0.05 m², 로터 전력은 Actuator Disk 이론 P_aero = T^(3/2)/√(2ρ₀ A_rotor) "
        "(유도 효율 0.60)을 적용한다. 하부 레버암 r_arm = [0, 0, −0.10]ᵀ m에서의 외란 토크 τ_reaction = r_arm × F_reaction에 대해 "
        "적응형 피드포워드 역토크 보상기(D4: u_ff = −F_reaction)와 PD 제어기를 결합하였다. "
        "센서 지연 τ_delay는 버퍼 큐로 모사하며, 배터리(120 Wh)는 항전 12 W → 소화장치 → 로터 순으로 전력을 분배한다.")

    heading(doc, "2.5. 수치해석 체계 및 격자 수렴성 검증", level=2)
    body(doc,
        "화재 유동장은 NIST FDS 6.11.1 LES(Deardorff 난류 모델, 5 cm 등방 격자, 16.5 kW 프로판 버너)로 해석하였다. "
        "OpenFOAM v2412의 Taylor-Green 와류 해석을 통한 격자 민감도 검증에서 80×80 격자의 상대 L₂ 오차 0.046%, "
        "GCI = 0.052%, 점근 차수 p = 1.98로 2차 공간 수렴성을 확인하였다. "
        "음향 FDTD(64셀, CFL = 0.50) L₂ 오차 0.189%, EHD Poisson 수렴 차수 1.995, 질량 잔차 < 10⁻¹⁶ kg으로 물리적 신뢰도를 입증하였다.")

    # ════════════════════════════════════════════════════════
    # Table 1: 소화 방식별 핵심 물리 지표 종합 비교
    # ════════════════════════════════════════════════════════
    caption(doc, "Table 1. 5대 소화 전달 방식별 물리 파라미터, 외란 반력 및 비행 소비 특성 종합 비교")

    table = doc.add_table(rows=6, cols=7)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = 'Table Grid'

    headers = ["소화 방식", "출력(W)", "피크반력(N)", "위치오차(m)", "탑재중량(kg)", "소비에너지(Wh)", "주요 기제 특성"]
    for j, h in enumerate(headers):
        set_cell_font(table.cell(0, j), h, size=7.5, bold=True)
        shade_cell(table.cell(0, j), "D9E2F3")

    data = [
        ["M1 저주파음향", "80.0", "0.0017", "0.0010", "0.50", "3.07", "비소모성 유도기류 전단교란"],
        ["M2 공기와류링", "15.0", "0.6052", "0.0039", "0.60", "3.17", "펄스 운동량 집중 대류소염"],
        ["M3 미세수분무", "35.0", "0.0841", "0.0069", "0.60", "3.18", "연속분사 잠열흡수 질식냉각"],
        ["M4 건성에어로졸","10.0", "0.0115", "0.0012", "0.45", "2.91", "초경량 라디칼 화학적 연쇄차단"],
        ["M5 전도성EHD",  "20.0", "0.6132", "0.0047", "0.75", "3.44", "전계유도 집중수송 사거리증대"],
    ]
    for i, row in enumerate(data):
        for j, val in enumerate(row):
            align = WD_ALIGN_PARAGRAPH.LEFT if j in [0, 6] else WD_ALIGN_PARAGRAPH.CENTER
            set_cell_font(table.cell(i+1, j), val, size=7.5, bold=False, align=align)

    # ════════════════════════════════════════════════════════
    # 3. 결과 및 고찰
    # ════════════════════════════════════════════════════════
    heading(doc, "3. 결과 및 고찰", level=1)

    heading(doc, "3.1. 소화 방식별 물리 전달 특성 및 비행 영향 비교", level=2)
    body(doc,
        "Table 1의 해석 결과는 5대 방식의 뚜렷한 성능-비행 트레이드오프를 규명한다. "
        "M1은 반력이 1.7 mN에 불과해 위치오차 0.0010 m의 극저외란 비행을 보장하나 유효 사거리가 1.5 m 이내로 제약된다. "
        "M2는 도달 속도 2.01 m/s, 순환 0.560 m²/s로 우수한 화염 전단 분리 성능을 발휘하지만, 펄스 사출 시 0.605 N의 반력 충격을 유발한다. "
        "M3는 4초간 분사된 0.020 kg 중 42%가 기화하며 20,571 J의 강력한 열흡수를 제공하나, 연속 반력 누적으로 위치오차가 0.0069 m까지 증가하였다. "
        "M4는 탑재량 0.45 kg, 소비에너지 2.91 Wh로 초소형 플랫폼에 가장 부합한다.")

    heading(doc, "3.2. 반력 보정 및 횡풍·센서 지연 비행 안정성", level=2)
    body(doc,
        "34초 전주기 비행(접근 15 s → 방출 4 s → 복귀 15 s, 이격 1.0 m, 횡풍 0.2 m/s) 시뮬레이션 결과, "
        "적응형 외란 보상(D4) 적용 시 펄스 반력(M2, M5)에 의한 자세각 변동은 0.55° 이내로 0.5초 내에 수렴하였다(Fig. 1). "
        "반면 무보정 기본 PD 제어(D3)에서는 M3 연속 분사 시 위치 오차가 0.957 m까지 폭증하여 보상 제어의 당위성을 입증하였다. "
        "Fig. 2의 횡풍(0~5 m/s) 및 지연(0~500 ms) 매트릭스 분석에서 횡풍에 따른 오차는 이차 회귀 e_max = aU² + bU + c (R² = 1.000)로 "
        "안정 제어되었으나, 센서 지연 τ_delay ≥ 250 ms 구간에서는 위상 마진 상실로 리미트 사이클 발산(오차 > 2.5 m, 500 ms 시 13.14 m)이 "
        "발생하였다. 따라서 실시간 온보드 피드백 지연은 200 ms 이하로 유지되어야 한다.")

    # Fig. 1: D4 제어 응답
    add_figure(doc, os.path.join(fig_dir, "05_D4_controller_response.png"), width_cm=7.0)
    caption(doc, "Fig. 1. 적응형 외란 보상(D4) 제어기 적용 시 5대 소화 방식별 34초 전주기 목표 위치오차 시계열. "
                 "펄스 방식(M2, M5)의 충격 완충과 연속 분사(M3)의 점진적 오차 거동이 대조된다.")

    # Fig. 2: 횡풍 vs 센서 지연 히트맵
    add_figure(doc, os.path.join(fig_dir, "vis_01_crosswind_latency_heatmap.png"), width_cm=7.0)
    caption(doc, "Fig. 2. 횡풍 풍속 및 센서 피드백 지연시간 매트릭스에 따른 드론 6-DOF 최대 위치오차 Heatmap. "
                 "τ_delay ≤ 0.20 s 정밀 호버링 안정권과 τ_delay ≥ 0.25 s 제어 이탈 위험 영역 간의 임계선이 특정된다.")

    heading(doc, "3.3. FDS 기반 화재 플룸 및 복사열유속 저감 해석", level=2)
    body(doc,
        "FDS 6.11.1 수치해석에서 기저 화재 C0는 16.5 kW의 준정상 HRR을 유지하였다. "
        "Fig. 3의 과도 응답 곡선과 같이 M3(수분무) 분사 시 액적 기화 열흡수율이 −3.06 kW에 달하고 수증기 발생률이 1.20×10⁻³ kg/s로 "
        "급증하여 전방 복사열유속을 1.50 kW/m²에서 0.05 kW/m² 미만으로 96.7% 저감하였다(흡광계수 κ_ext ≈ 4.2 m⁻¹). "
        "화원 전방 1.0 m에서 기체 표면 복사열유속 q'' = 5,000 W/m² 수열 시 34초간 드론 동체 피크 온도 상승은 0.40 K에 불과하여 "
        "열적 안전 한계를 충분히 확보하였다. 5 cm 격자 조건에서 10초 이내 완전 소염(HRR < 1 kW) 판정은 화학 반응 속도 제약으로 "
        "우측 검열(censored) 데이터로 관측되었다.")

    # Fig. 3: FDS HRR 시계열
    add_figure(doc, os.path.join(fig_dir, "08_hrr_comparison_revised.png"), width_cm=6.8)
    caption(doc, "Fig. 3. FDS 6.11.1 화재 해석 결과. 상: 소화 방식별 HRR 과도 곡선, "
                 "중: 무개입 대조군(C0) 대비 순 열방출률 변화량(ΔHRR), 하: 누적 열량 적분 차이.")

    heading(doc, "3.4. 다중 소화 방식 상호보완 및 최적 운용 영역", level=2)
    body(doc,
        "단독 물리 기제의 한계를 보완하기 위한 복합 운용 분석 결과, 공기 와류 링(M2)과 에어로졸(M4)의 조합이 "
        "시너지 계수 S = 1.42로 최우수 상호보완성을 기록하였다. 이는 와류 링 중심부 환상 유동(Re ≈ 12,000)이 "
        "에어로졸 미립자를 포획하여 드론 하강풍에 의한 비산 손실 없이 화염 심부로 직접 수송하는 "
        "'공기역학적 캐리어' 역할을 수행하기 때문이다. M1–M3 (S = 1.35), M2–M3 (S = 1.30) 역시 유의미한 효율 상승을 나타내었다. "
        "비행 안정성(오차 ≤ 0.05 m), 소화 효율(≥ 80%), 배터리 마진(≥ 78%)을 동시 충족하는 다차원 운용 허용 공간(Trade Space) "
        "도출 결과, 최적 운용 조건은 주변 횡풍 1.0~2.0 m/s, 이격거리 1.5~2.2 m의 능선 영역으로 규명되었다.")

    # 저장
    doc.save(out_path)
    print(f"Generated docx at: {out_path}")

    # Artifact 디렉토리에도 복사
    art_dir = r"C:\Users\js100\.gemini\antigravity\brain\41fbe8b3-15a8-4109-9dd7-fbc90083c1d4"
    if os.path.exists(art_dir):
        shutil.copy2(out_path, os.path.join(art_dir, "삼성휴먼테크_33회_본론.docx"))
        print(f"Copied to artifact dir: {art_dir}")

    return out_path


if __name__ == "__main__":
    build_body_document()
