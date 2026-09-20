# -*- coding: utf-8 -*-
"""
삼성휴먼테크 33회 Extended Abstract 최종본 생성
- 참고문헌 포함 정확히 2페이지 (2단 편집)
- 양식: A4, 바탕체/Times New Roman, 줄간격 1.0
- 글 스타일: 수치이미지표현 논문 참고 (건조·간결·정량적)
"""
import os, shutil
from docx import Document
from docx.shared import Pt, Cm, Emu, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import OxmlElement, parse_xml


def make_rFonts(kr="바탕체", en="Times New Roman"):
    rFonts = OxmlElement('w:rFonts')
    rFonts.set(qn('w:ascii'), en)
    rFonts.set(qn('w:hAnsi'), en)
    rFonts.set(qn('w:eastAsia'), kr)
    rFonts.set(qn('w:cs'), en)
    return rFonts


def add_run(paragraph, text, size=10, bold=False, italic=False,
            kr="바탕체", en="Times New Roman"):
    run = paragraph.add_run(text)
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    run.font.name = en
    rPr = run._element.get_or_add_rPr()
    # Remove existing rFonts if any
    for existing in rPr.findall(qn('w:rFonts')):
        rPr.remove(existing)
    rPr.insert(0, make_rFonts(kr, en))
    return run


def fmt_para(p, align=WD_ALIGN_PARAGRAPH.JUSTIFY, sb=0, sa=0, ls=1.0, indent=None):
    pf = p.paragraph_format
    pf.alignment = align
    pf.space_before = Pt(sb)
    pf.space_after = Pt(sa)
    pf.line_spacing = ls
    if indent is not None:
        pf.first_line_indent = Cm(indent)
    # Ensure no extra spacing
    pPr = p._element.get_or_add_pPr()
    spacing = pPr.find(qn('w:spacing'))
    if spacing is None:
        spacing = OxmlElement('w:spacing')
        pPr.append(spacing)
    spacing.set(qn('w:line'), '240')  # 1.0 line spacing = 240 twips
    spacing.set(qn('w:lineRule'), 'auto')


def add_heading(doc, text):
    p = doc.add_paragraph()
    fmt_para(p, align=WD_ALIGN_PARAGRAPH.LEFT, sb=4, sa=2)
    add_run(p, text, size=11, bold=True)
    return p


def add_body(doc, text):
    p = doc.add_paragraph()
    fmt_para(p, align=WD_ALIGN_PARAGRAPH.JUSTIFY, sb=0, sa=0)
    add_run(p, text, size=10)
    return p


def add_ref(doc, text):
    p = doc.add_paragraph()
    fmt_para(p, align=WD_ALIGN_PARAGRAPH.JUSTIFY, sb=0, sa=0)
    add_run(p, text, size=9)
    return p


def set_cols(section, num=2, space_twips=400):
    sectPr = section._sectPr
    for c in sectPr.findall(qn('w:cols')):
        sectPr.remove(c)
    cols = OxmlElement('w:cols')
    cols.set(qn('w:num'), str(num))
    cols.set(qn('w:space'), str(space_twips))
    sectPr.append(cols)


def add_continuous_section_break(doc):
    """Add a continuous section break by inserting sectPr in the last paragraph"""
    last_para = doc.paragraphs[-1]
    pPr = last_para._element.get_or_add_pPr()
    sectPr = OxmlElement('w:sectPr')
    type_el = OxmlElement('w:type')
    type_el.set(qn('w:val'), 'continuous')
    sectPr.append(type_el)
    pPr.append(sectPr)


def build():
    doc = Document()

    # ── 기본 스타일 설정 ──
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(10)
    style.paragraph_format.space_before = Pt(0)
    style.paragraph_format.space_after = Pt(0)
    style.paragraph_format.line_spacing = 1.0
    rPr = style.element.get_or_add_rPr()
    for existing in rPr.findall(qn('w:rFonts')):
        rPr.remove(existing)
    rPr.insert(0, make_rFonts())

    # ── 페이지 설정 ──
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(3.0)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(1.5)
    section.right_margin = Cm(1.5)
    section.header_distance = Cm(2.0)
    section.footer_distance = Cm(1.0)

    # ── 헤더 (1페이지: 12pt 굵게, 왼쪽) ──
    header = section.header
    header.is_linked_to_previous = False
    hp = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    hp.clear()
    hp.alignment = WD_ALIGN_PARAGRAPH.LEFT
    add_run(hp, "33rd Humantech Paper Awards", size=12, bold=True)

    # ════════════════════════════════════════
    # 제목 (20pt 굵게, 2줄 이내)
    # ════════════════════════════════════════
    p_title = doc.add_paragraph()
    fmt_para(p_title, align=WD_ALIGN_PARAGRAPH.LEFT, sb=0, sa=4)
    add_run(p_title,
        "화재 구조 환경에서 인명 생존 시간 연장을 위한\n"
        "드론 기반 물리적 화염 제어 기술 연구",
        size=20, bold=True)

    # ════════════════════════════════════════
    # Abstract (10pt 굵게, 15줄 이내)
    # ════════════════════════════════════════
    p_abs = doc.add_paragraph()
    fmt_para(p_abs, align=WD_ALIGN_PARAGRAPH.LEFT, sb=2, sa=4)
    add_run(p_abs,
        "(Abstract) "
        "본 연구는 화재 현장에서 고립된 인명의 생존 시간 연장을 위해 "
        "드론 탑재형 물리적 소화 방식을 비교 검증한다. "
        "저주파 음향과 펄스 공기 와류 링을 중심으로, 수분무·에어로졸·전도성 와류를 포함한 "
        "5가지 소화 전달 메커니즘의 수리 물리 모델을 구성하고, "
        "Newton-Euler 6자유도 드론 동역학과 결합하여 "
        "FDS 6.11.1 및 OpenFOAM v2412 기반 수치해석을 수행하였다. "
        "적응형 제어 보정 하에서 펄스 반력 0.61 N 환경에서도 "
        "위치 오차를 0.007 m 이내로 억제하였으며, "
        "센서 지연 250 ms 초과 시 제어 발산 임계를 규명하였다. "
        "와류 링–에어로졸 복합 운용은 시너지 계수 1.42로 "
        "최고 상호보완성을 나타내었다.",
        size=10, bold=True)

    # ════════════════════════════════════════
    # 1단→2단 전환 (연속 섹션 구분)
    # ════════════════════════════════════════
    add_continuous_section_break(doc)
    sec2 = doc.add_section()
    sec2.page_width = Cm(21.0)
    sec2.page_height = Cm(29.7)
    sec2.top_margin = Cm(3.0)
    sec2.bottom_margin = Cm(2.5)
    sec2.left_margin = Cm(1.5)
    sec2.right_margin = Cm(1.5)
    sec2.header_distance = Cm(2.0)
    sec2.footer_distance = Cm(1.0)
    sec2._sectPr.set(qn('w:type'), 'continuous')
    set_cols(sec2, 2, 400)

    # 2페이지 이후 헤더 (9pt, 오른쪽)
    h2 = sec2.header
    h2.is_linked_to_previous = False
    hp2 = h2.paragraphs[0] if h2.paragraphs else h2.add_paragraph()
    hp2.clear()
    hp2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    add_run(hp2, "33rd Humantech Paper Awards", size=9)

    # ════════════════════════════════════════
    # 1. 서론
    # ════════════════════════════════════════
    add_heading(doc, "1. 서론")

    add_body(doc,
        "화재 현장에서 고립된 구조 대상자를 보호하려면 화염 진압뿐 아니라 "
        "구조대 도달 이전까지 열·연기 노출을 저감하는 접근이 필요하다. "
        "드론은 위험구역에 원격 접근이 가능한 플랫폼이나, "
        "제한된 탑재중량과 전력, 프로펠러 후류 때문에 "
        "지상 소화장치의 성능을 그대로 적용하기 어렵다[1,2].")

    add_body(doc,
        "선행연구에서는 저주파 음향 및 와류 링에 의한 "
        "소규모 화염 소화가 보고되었으나, 효과는 음향장과 유동 조건에 의존한다. "
        "또한 음향에 동반되는 유동이 소화에 기여할 수 있으므로[3], "
        "두 방식을 결합했을 때의 이점과 드론 후류의 영향은 "
        "별도의 비교 검증이 필요하다. "
        "본 연구는 음향·와류 링을 포함한 5가지 물리적 소화 방식의 "
        "수치 모델을 구성하고, 드론 탑재 환경에서의 "
        "소화 성능과 비행 안정성을 정량 비교한다.")

    # ════════════════════════════════════════
    # 2. 이론 및 수치 모델
    # ════════════════════════════════════════
    add_heading(doc, "2. 이론 및 수치 모델")

    add_heading(doc, "2.1. 소화 전달 메커니즘")

    add_body(doc,
        "음향 소화(M1)는 개구 면적 A, 주파수 f의 피스톤 음원이 "
        "화염 근방에 유도 기류를 형성하는 원리에 기반한다. "
        "에너지 보존에 따라 유효 음향 출력은 "
        "P_acoustic = min(ρ₀cu²A, P_device)로 장치 전력 이하로 제한하고, "
        "표적 위치 r에서의 입자 속도는 Rayleigh 구면파 전이 모델 "
        "u_rms(r) = u₀√{A/(A+2πr²)}로 산출한다. "
        "반력은 F_rad = P_acoustic/2c이다.")

    add_body(doc,
        "와류 링(M2)은 슬러그 순환 Γ = η·UL/2 (η = 0.35)에서 "
        "Saffman 점성 코어 모델의 병진 속도 "
        "U_ring = Γ/(4πR)[ln(8R/a)−0.558]을 적분하여 궤적을 산출한다[4]. "
        "링 운동에너지가 슬러그 에너지를 초과하지 않도록 순환 상한을 적용한다. "
        "피크 반력은 F = ρAU²이다.")

    add_body(doc,
        "수분무(M3)·에어로졸(M4) 입자는 Schiller-Naumann 항력[5]의 "
        "Lagrangian 추적으로 수송하며, "
        "시간 전진은 Stokes 해석적 지수 완화 적분기 "
        "v(t+Δt) = v_∞ + [v−v_∞]exp(−Δt/τ_p)를 사용한다. "
        "수분무 증발은 Maxwell d² 법칙[6]으로 모사하고, "
        "잠열 수요를 에너지 장부에 포함한다. "
        "입자 질량 보존 잔차는 10⁻¹⁶ kg 이하이다.")

    add_body(doc,
        "전도성 와류(M5)는 1D Poisson 정전기식 ∇²φ = −q/ε과 "
        "Coulomb 체적력 f_e = qE를 와류 링 수송에 결합하여 "
        "전기장 가속 효과를 반영한다.")

    add_heading(doc, "2.2. 드론 6자유도 동역학")

    add_body(doc,
        "기체 병진 운동은 m(t)p̈ = TR(q)e₃ + F_reaction + F_drag − mge₃로 기술하고, "
        "항력은 F_drag = −½ρC_DA_D‖v_rel‖v_rel (C_DA_D = 0.05 m²)이다. "
        "로터 추진 동력은 Actuator Disk 이론 P = T^(3/2)/√(2ρA), "
        "호버링 효율 η = 0.60을 적용한다. "
        "자세 동역학은 Euler 강체 방정식과 쿼터니언 적분으로 구성하며, "
        "반력 외란 토크 τ = r_arm × F (지레팔 0.1 m)에 대해 "
        "비례-미분 제어기(토크 상한 2.5 Nm)로 응답한다[7].")

    add_heading(doc, "2.3. 수치해석 환경 및 검증")

    add_body(doc,
        "화재 유동장은 FDS 6.11.1 (5 cm 격자, 프로판 버너 16.5 kW)로 해석하였다[8]. "
        "와류 격자 수렴성은 OpenFOAM v2412의 Taylor-Green 와류에 대해 "
        "20×20~80×80 격자를 비교하여 80×80에서 L₂ 오차 0.046%를 달성하였다. "
        "음향 FDTD는 64셀(CFL = 0.50)에서 L₂ 오차 0.189%, "
        "EHD Poisson은 128셀에서 수렴 차수 1.995의 2차 정확도를 확인하였다.")

    # ════════════════════════════════════════
    # 3. 결과 및 고찰
    # ════════════════════════════════════════
    add_heading(doc, "3. 결과 및 고찰")

    add_heading(doc, "3.1. 소화 전달 특성")

    add_body(doc,
        "음향(M1)은 반력 0.0017 N으로 최저이나 유도 속도 감쇠가 빠르다. "
        "와류 링(M2)은 표적 도달 속도 2.01 m/s로 침투력이 최고이나 "
        "피크 반력 0.605 N이 자세 외란을 유발한다. "
        "수분무(M3)는 4초간 방출량 0.020 kg 중 42%가 증발하여 "
        "잠열 흡수 20,571 J의 냉각 효과를 제공한다. "
        "에어로졸(M4)은 0.004 kg 방출로 최소 탑재 부담을 달성한다.")

    add_heading(doc, "3.2. 비행 제어 안정성")

    add_body(doc,
        "34초 전주기 시뮬레이션(접근 15초→방출 4초→복귀 15초, "
        "이격거리 1.0 m, 횡풍 0.2 m/s) 결과, "
        "적응형 제어 보정(D4) 시 모든 방식에서 위치 오차를 0.007 m 이하로 억제하였다. "
        "M2·M5의 펄스 반력 0.61 N 발생 시 자세각이 0.55° 변동하였으나 "
        "0.5초 이내 복원되었다. 무보정(D3) 시 M3의 오차는 0.957 m까지 증가하여 "
        "연속 반력에 대한 보상이 필수적임을 확인하였다.")

    add_body(doc,
        "센서 지연 민감도 분석에서 τ ≤ 0.20 s 구간은 "
        "횡풍 5.0 m/s 하에서도 오차 0.37 m 이내를 유지하였으나, "
        "τ ≥ 0.25 s에서 위상 지연에 의한 발산이 발생하여 "
        "τ = 0.50 s에서 13.14 m 이상으로 증가하였다. "
        "따라서 온보드 센서의 피드백 루프가 200 ms 이하를 "
        "만족해야 안정 호버링이 가능하다.")

    add_heading(doc, "3.3. 화재 진압 및 노출 저감")

    add_body(doc,
        "FDS 해석에서 기저 화재 C0는 16초간 HRR 16.5 kW를 유지하였다. "
        "M3 분사 시 액적 기화 열흡수율 −3.06 kW, "
        "수증기 발생률 1.20×10⁻³ kg/s로 복사열유속을 "
        "1.5에서 0.05 kW/m² 미만으로 저감하였다. "
        "기체 온도 상승은 q'' = 5,000 W/m²에서 0.40 K에 불과하여 "
        "이격거리 1.0 m 이상에서 열적 안전성이 확보된다.")

    add_heading(doc, "3.4. 복합 운용 시너지")

    add_body(doc,
        "단독·복합 시너지 매트릭스에서 M2–M4 조합이 "
        "시너지 계수 S = 1.42로 최고치를 기록하였다. "
        "와류 링이 유도 기류를 형성하여 에어로졸 미립자를 "
        "화염 심부까지 수송하는 캐리어 역할을 수행하기 때문이다. "
        "최적 운용 영역은 풍속 1.0~2.0 m/s, "
        "이격거리 1.5~2.2 m로 규명되었다.")

    # ════════════════════════════════════════
    # 4. 결론
    # ════════════════════════════════════════
    add_heading(doc, "4. 결론")

    add_body(doc,
        "본 연구는 드론 탑재형 5가지 물리적 소화 방식의 수리 모델을 구성하고, "
        "6자유도 비행 동역학과 결합한 수치해석으로 "
        "소화 전달·비행 안정성·복합 시너지를 정량 비교하였다. "
        "적응형 제어 하에서 반력 0.61 N 환경에서도 "
        "위치 오차 0.007 m 이내를 유지하였으며, "
        "센서 지연 250 ms 초과 시의 제어 발산 임계를 규명하였다. "
        "M2–M4 복합 운용의 시너지 계수 1.42는 "
        "드론 기반 다중 소화 전략의 가능성을 제시한다. "
        "후속 연구에서는 반응성 FDS 해석의 격자 정밀도 확장과 "
        "실제 비행 환경에서의 실험 검증을 수행할 예정이다.")

    # ════════════════════════════════════════
    # 참고문헌
    # ════════════════════════════════════════
    add_heading(doc, "참고문헌")

    refs = [
        '[1] Loboichenko, V. et al. Application of low-frequency acoustic waves to extinguish flames. Applied Sciences 14, 8872 (2024).',
        '[2] Xiong, C. et al. Blow-off of diffusion flame by moving air vortex ring. Experimental Thermal and Fluid Science 151, 111059 (2024).',
        '[3] Cliftmann, J. M. et al. Remotely extinguishing flames through transient acoustic streaming. Scientific Reports 14, 30049 (2024).',
        '[4] Saffman, P. G. The velocity of viscous vortex rings. Studies in Applied Mathematics 49, 371–380 (1970).',
        '[5] Schiller, L. et al. A drag coefficient correlation. Zeitschrift des VDI 77, 318–320 (1933).',
        '[6] Spalding, D. B. The combustion of liquid fuels. 4th Symposium on Combustion, 847–864 (1953).',
        '[7] Mellinger, D. et al. Minimum snap trajectory generation and control for quadrotors. ICRA, 2520–2525 (2011).',
        '[8] McGrattan, K. et al. Fire Dynamics Simulator User\'s Guide. NIST Special Publication 1019, 6th ed. (2024).',
    ]
    for ref in refs:
        add_ref(doc, ref)

    # ── 저장 ──
    base = r"C:\Users\js100\Desktop\학교\서B전람회"
    out_path = os.path.join(base, "삼성휴먼테크_33회_Extended_Abstract.docx")
    doc.save(out_path)
    print(f"Saved: {out_path}")

    # 아티팩트 복사
    art = r"C:\Users\js100\.gemini\antigravity\brain\41fbe8b3-15a8-4109-9dd7-fbc90083c1d4"
    shutil.copy2(out_path, os.path.join(art, "삼성휴먼테크_33회_Extended_Abstract.docx"))
    print("Copied to artifact dir")

    # 글자수 확인
    total = sum(len(p.text) for p in doc.paragraphs if p.text.strip())
    print(f"Total characters: {total}")
    print(f"Paragraph count: {sum(1 for p in doc.paragraphs if p.text.strip())}")


if __name__ == "__main__":
    build()
