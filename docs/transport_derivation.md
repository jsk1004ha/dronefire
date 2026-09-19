# 5개 원격 화재 제어 수송 모델의 물리식 유도와 적용 한계

## 문서의 범위

`firelab/physics.py`는 장치에서 표적까지 음향, 와류, 물방울 또는 입자가 **어떻게 전달되는지**를 계산하는 축약 모델이다. 연소 반응식, 화염 소염 한계, 약제 반응속도는 포함하지 않는다. 따라서 모든 결과의 `suppression.status`는 `insufficient_evidence`이며, 전달률을 소화 성공률로 바꾸지 않는다.

기본 단위는 SI이다. 위치는 m, 시간은 s, 속도는 m/s, 질량은 kg, 힘은 N, 에너지는 J, 압력은 Pa, 체적 전하밀도는 C/m³이다. 공기는 293 K 부근의 일정 물성 `rho_air = 1.204 kg/m³`, `mu_air = 1.81e-5 Pa·s`, `c = 343 m/s`로 둔다. 이 가정은 고온 화재 플룸에서 성립하지 않으며, 그 영역은 FDS/OpenFOAM 해석으로 넘겨야 한다.

## M1 저주파 음향

### 지배식과 에너지 경계

정지한 균일 유체의 연속방정식과 운동량방정식을 작은 섭동에 대해 선형화하면

```text
∂rho'/∂t + rho0 div(u') = 0
rho0 ∂u'/∂t = -grad(p')
p' = c² rho'
```

이고, 이를 결합하면 `∂²p'/∂t² - c² laplacian(p') = 0`을 얻는다. 진행 평면파에서는 RMS 압력과 입자속도가 `p_rms = rho0 c u_rms`, 시간평균 강도가 `I = p_rms u_rms = rho0 c u_rms²`이다.

개구 면적을 `A = pi(D/2)²`라 하면 사용자가 요구한 음향 출력은

```text
P_requested = rho0 c u_requested² A
P_acoustic = min(P_requested, P_device)
u_source = sqrt(P_acoustic / (rho0 c A))
```

로 제한한다. 이 경계는 전기-음향 효율을 1로 둔 최댓값이므로 실제 장치는 이보다 약하다. 이전 모델처럼 입력 속도와 장치 전력을 서로 독립적으로 사용할 경우 `P_acoustic > P_device`가 가능했는데, 현재 구현은 이를 허용하지 않는다.

정확한 피스톤 방사 임피던스와 지향성 대신, 배플 앞 반구에 보존적으로 퍼지는 선별식을 쓴다.

```text
u_rms(r) = u_source sqrt[A / (A + 2 pi r²)]
u(t,r) = sqrt(2) u_rms(r) sin[2 pi f (t - r/c)]
```

`A` 항은 원점 특이점을 없애고 `r = 0`에서 입력 RMS 속도를 회복한다. 멀리서는 `u_rms ~ 1/r`가 되어 반구를 지나는 음향 출력이 유한하다. 이 `A + 2 pi r²` 전이는 정확한 Rayleigh 적분 해가 아니라 에너지 보존형 근사다. 코드에는 `ka = 2 pi f(D/2)/c`, 파장, Rayleigh 거리도 함께 기록하여, 개구가 파장과 비슷해져 지향성이 중요해지는 조건을 식별할 수 있게 했다.

반구가 운반하는 축방향 운동량을 각도 적분하면 평균 반작용의 상한은 `F_rad = P_acoustic/(2c)`이다. 진동력 표시는 `p_rms A`와 `sqrt(2) p_rms A`로 남겨 두었지만, 이는 평면파 등가값이며 구조 공진 계산이 아니다.

코드 위치: `_simulate_m1`.

## M2 공기 와류 링

### 슬러그 유동, 순환, 충격량과 에너지

노즐 반지름을 `R`, 출구속도를 `U`, 펄스 시간을 `T`, 스트로크를 `L = UT`라 한다. 균일 슬러그 유동의 기본량은

```text
Gamma_slug = (1/2) U L
I_slug = rho pi R² U L
E_slug = (1/2) rho pi R² U³ T
```

이다. 실제 박리 전단층의 롤업은 노즐 형상에 의존하므로 `Gamma_raw = eta Gamma_slug`를 쓰며, `eta`는 측정되지 않은 폐쇄계수다. 얇은 점성 코어 링에 대해

```text
I_ring = rho pi Gamma R²
E_ring = (1/2) rho Gamma² R [ln(8R/a) - 1.558]
```

을 계산하고, `E_ring <= E_slug`가 되도록 순환을 제한한다. 이 제한은 축약 링이 노즐 슬러그보다 많은 운동에너지를 갖는 비물리적 상태를 막는다. `L/D`도 `formation_number_L_over_D`로 출력한다. 큰 `L/D`에서 뒤따르는 제트와 pinch-off가 생기는 현상은 현재 한 개의 링으로 재현하지 않는다.

점성 확산은 Gaussian/Lamb-Oseen 코어의

```text
a²(t) = a0² + 4 nu t
U_ring(t) = Gamma/(4 pi R) [ln(8R/a(t)) - 0.558]
```

을 사용한다. 링 중심은 과거 구현의 `U(t)t`가 아니라 `x(t) = integral U_ring(tau) d tau`를 사다리꼴 적분한다. 횡풍은 `y(t) = U_cross t`로 더한다.

공간 속도장은 유한 코어 정규화 Biot-Savart 적분

```text
u(x) = Gamma/(4 pi) line_integral dl cross (x-X) / (|x-X|²+a²)^(3/2)
```

으로 계산한다. 이 정규화 커널과 Gaussian 코어의 적분 상수는 완전히 동일한 코어 모형이 아니므로, 공간장은 시각화·전달 선별용이다. 벽, 난류 전이, 링 붕괴와 화염의 baroclinic vorticity는 포함하지 않는다.

노즐 펄스의 최고 반작용은 운동량 유속 `F = rho A U²`, 한 주기 평균은 `F T/period`이다. 공기 슬러그의 최소 운동에너지보다 저장 공압에너지가 작으면 가능한 펄스 수를 줄인다.

코드 위치: `_ring_parameters`, `_ring_speed`, `_ring_travel`, `_ring_velocity`, `_pneumatic_budget`, `_simulate_m2`.

## M3 지향 수분무와 M4 응축 에어로졸

### 입자 운동량방정식

각 계산 parcel은 같은 지름을 갖는 많은 실제 방울 또는 입자를 대표한다. 희박 구형 입자의 운동은

```text
m_p dv/dt = (m_p/tau_p)(u_g-v) + m_p(1-rho_g/rho_p) g
Re_p = rho_g d |v-u_g| / mu_g
tau_p = rho_p d² / [18 mu_g (1 + 0.15 Re_p^0.687)]       (Re_p < 1000)
Cd = 24(1 + 0.15 Re_p^0.687)/Re_p
Cd = 0.44                                                   (Re_p >= 1000)
```

으로 둔다. 한 시간 단계 동안 공기속도와 `tau_p`를 고정하면 종단속도 `v_inf = u_g + tau_p g_eff`에 대한 해는

```text
v(t+dt) = v_inf + [v(t)-v_inf] exp(-dt/tau_p)
x(t+dt) = x(t) + v_inf dt
          + [v(t)-v_inf] tau_p [1-exp(-dt/tau_p)]
```

이다. 속도만 지수 완화한 뒤 새 속도로 위치를 전진하던 방식보다 Stokes 한계, 작은 `dt`, 큰 `dt`에서 일관된다. 부력 보정도 중력항에 포함했다. 공기장은 측정되지 않은 원형 자유제트의 자기유사 Gaussian 폐쇄식이며, 횡풍을 단순 중첩한다. 난류 분산, 충돌, breakup, coalescence와 벽막은 없다.

### 물방울 증발

M3은 등온 Maxwell `d²` 법칙을 쓴다.

```text
d²(t+dt) = max[d²(t) - K dt, 0]
K = (8 rho_g D_v/rho_l) ln[(1-Y_inf)/(1-Y_s)]
```

`Y_s`는 Buck 포화수증기압식으로 얻은 표면 수증기 질량분율, `Y_inf`는 상대습도를 곱한 주위 질량분율이다. `D_v = 2.5e-5 (T/293.15)^1.8 m²/s`는 확산계수 폐쇄식이다. Buck 식의 적용 범위를 벗어나지 않도록 포화압 계산 온도는 253.15–323.15 K로 제한하며, 그 이상은 결과 제한사항에 표시한다.

증발 질량에 필요한 잠열 `Q_latent = m_evap 2.45e6 J/kg`을 별도 장부로 기록한다. 현재 유동의 온도·엔탈피에서 이 열을 빼지 않으므로, 이것은 화염 냉각량 계산이 아니다. M4는 조성이 없으므로 증발·열분해·라디칼 억제를 모두 0으로 두고 수동 고체 입자로만 계산한다.

### 질량·에너지 장부

각 단계에서

```text
m_emitted = m_delivered + m_evaporated + m_deposited + m_escaped + m_airborne
```

를 확인한다. `delivered`는 표적 원판을 기하학적으로 통과한 질량일 뿐 소화에 사용된 질량이 아니다. 입자 발사만 계산하면 carrier air jet의 에너지가 장부에서 빠진다. 현재 구현은 요청 질량 `m`과 carrier 면적 `A_c`에 대해

```text
E_ideal(U) = (1/2) rho_air A_c U³ duration + (1/2) m U²
```

를 함께 계산한다. 첫 항은 carrier air의 운동에너지 유량 적분이고 둘째 항은 입자 발사 운동에너지다. 총 에너지뿐 아니라 실제 방출 중의 `P_ideal(U) = (1/2) rho_air A_c U³ + (1/2) mass_flow U² <= P_device`도 만족해야 한다. 약제가 일찍 소진될 경우 전체 시간으로 평균낸 에너지 제약만으로는 순간 출력 초과를 막지 못한다. 현재 구현은 순간 출력식을 이분법으로 풀어 유효 출구속도 `U_effective`를 제한한다. 따라서 순간 이상 출력과 전체 이상 운동에너지 모두 가용 장치 자원을 넘지 않는다. 펌프 효율을 1로 둔 상한이며, 실제 압축가스 탱크가 있다면 그 저장에너지를 입력 계약에 추가한 뒤 별도 장부로 계산해야 한다.

M3/M4/M5는 `consumable_release`에 실제 유량, 방출 지속시간, 기체 기준 배출속도 벡터를 기록한다. 드론은 이 구간의 배출량으로 질량과 입자 반동 `F_particle = -mass_flow * exhaust_velocity`를 함께 계산한다. M5 공기 펄스와 입자 방출은 독립 항으로 합산하며, 공기 펄스 선택 때문에 입자 반동이 누락되지 않는다. `reaction_force_N`은 기존 요약값이고, `nonconsumable_reaction_force_N`과 펄스 정보는 입자 반동을 제외한 시간해석용 항이다.

코드 위치: `_water_evaporation_coefficient`, `_particle_transport`, `_simulate_m3_or_m4`.

## M5 전도성 에어로졸 와류와 이온풍

M5-CV의 공기 와류는 M2 식, 입자는 M4 식을 그대로 사용한다. 따라서 와류 공기 슬러그와 입자 발사 운동에너지를 각각 저장 공압에너지 장부에서 차감한다.

EHD 또는 COMBINED 모드에서 주어진 체적 전하밀도 `rho_q`와 전기장 `E`에 대해 Coulomb 체적력은

```text
f_EHD = rho_q E
a_EHD = f_EHD/rho_air
Delta_u = sign(a) sqrt(2 |a| L_EHD)
F_EHD = f_EHD A L_EHD
```

이다. 기계 출력 `|F_EHD Delta_u|`가 장치 전력보다 클 수 없도록 `|Delta_u| <= P_device/|F_EHD|`를 적용한다. 전기장은 균일하고 주어진 값으로 취급한다. 실제 corona/ionic wind에는 Poisson 방정식, 전하 보존, 이동도, 확산, 전극 경계, breakdown과 중성기체 충돌이 필요하다. 따라서 이 항은 장치 설계값의 차원·에너지 일관성을 확인하는 선별식이며, 이온풍 검증 모델이 아니다. 전도성 입자의 화학적 억제 효과도 계산하지 않는다.

코드 위치: `_simulate_m5`. 별도의 `firelab/ehd.py`는 1차원 Poisson-전하수송 수치 검증용이며, 이 축약 전달장과 자동으로 결합되지 않는다.

## 구현에 남아 있는 경험적 폐쇄

- M1의 `A + 2 pi r²` 전이는 정확한 baffled-piston Rayleigh 적분이 아닌 에너지 보존형 반구 근사다.
- M2/M5의 `circulation_efficiency`와 초기 코어 `a0 = 0.12R`는 실험 보정이 필요하다. 형성수 약 4 이후의 pinch-off를 개별 링/후류 제트로 분리하지 않는다.
- M3/M4의 자유제트 폭 성장률 0.10과 중심선 감쇠식은 보정되지 않은 자기유사 폐쇄다.
- 모든 입자는 단분산 구형이며 one-way coupling이다. parcel 농도장의 Gaussian 폭은 시각화 커널이지 측정 분해능이 아니다.
- M4/M5 입자 밀도 1800 kg/m³는 성분 자료가 없어서 둔 명시적 가정이다.
- 표적 도달은 원판 교차 판정이다. 열방출률, 산소, 온도와 재점화는 네이티브 FDS 결과가 있을 때만 별도 분석한다.

## 검증 가능한 제한 사례

`tests/test_physics.py`는 다음 물리 불변량을 검사한다.

1. M1의 음향 출력·에너지가 장치 출력·에너지를 넘지 않는다.
2. M1 RMS 파형의 최고값은 `sqrt(2) u_rms`이고 거리에 따라 감소한다.
3. M2 링 에너지는 슬러그 에너지를 넘지 않고 `I = rho pi Gamma R²`를 만족한다.
4. 저장 공압에너지가 0이면 M2/M5 펄스와 입자 발사가 0이다.
5. M3/M4/M5 질량 장부 잔차가 수치 오차 범위에서 0이다.
6. M3/M4 carrier air와 입자의 이상 운동에너지 합은 가용 장치 에너지를 넘지 않는다.
7. M5-CV는 전기 입력이 0일 때 이온풍과 전기력을 만들지 않는다.
8. `duration/dt`가 정수가 아니어도 마지막 잔여 시간 단계를 포함하여 `m_emitted = mass_flow × duration`을 만족한다.

## 근거 문헌

- Rayleigh 적분에 기반한 baffled rigid piston 문제: NASA, *The Acoustic Radiation from a Circular Piston in an Infinite Baffle*, NASA CR-1437. https://ntrs.nasa.gov/api/citations/19690031546/downloads/19690031546.pdf
- P. G. Saffman, “The Velocity of Viscous Vortex Rings,” *Studies in Applied Mathematics* 49 (1970), 371–380. https://doi.org/10.1002/sapm1970494371
- Orifice vortex ring의 slug-flow 순환·충격량·에너지 식: *Journal of Fluid Mechanics*, “Formation of an orifice-generated vortex ring.” https://www.cambridge.org/core/journals/journal-of-fluid-mechanics/article/formation-of-an-orificegenerated-vortex-ring/B9F8E5CB0B396AEB19D79D3EA509E02B
- Vortex formation number와 pinch-off: M. Gharib, E. Rambod, K. Shariff, “A universal time scale for vortex ring formation,” *Journal of Fluid Mechanics* 360 (1998). https://www.cambridge.org/core/services/aop-cambridge-core/content/view/8DA34E3C7204D966AC92C5FA1E1A9BBC/S0022112097008410a.pdf
- Schiller–Naumann 구형 입자 항력 상관식의 구현 대조: OpenFOAM 공식 소스. 원 논문의 저자·연도 표기는 서지 데이터베이스 사이에 차이가 있어 여기서는 확정하지 않는다. https://www.openfoam.com/documentation/guides/v2112/api/PlessisMasliyahDragForce_8C_source.html
- Maxwell `d²` 법칙과 질량확산 유도: “Microgravity Spherical Droplet Evaporation and Entropy Effects,” 2023. https://pmc.ncbi.nlm.nih.gov/articles/PMC10453263/
- A. L. Buck, “New Equations for Computing Vapor Pressure and Enhancement Factor,” *Journal of Applied Meteorology* 20 (1981), 1527–1532. https://doi.org/10.1175/1520-0450(1981)020%3C1527:NEFCVP%3E2.0.CO;2
- 물의 열역학 물성: NISTIR 5078, IAPWS-95 표. https://www.nist.gov/srd/nistir-5078
- EHD 체적력 `rho_q E`의 직접 근거: “The creation of electric wind due to the electrohydrodynamic force.” https://doi.org/10.1038/s41467-017-02766-9
- 전하·전기장·중성기체 운동량 결합의 해석모델: “Analytical model of electro-hydrodynamic flow in corona discharge.” https://pmc.ncbi.nlm.nih.gov/articles/PMC6089801/
