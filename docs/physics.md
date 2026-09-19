# 물리 수송 모델 API와 가정

`firelab.physics.simulate_method(config, method_id)`는 M1–M5 장치가 만드는 유동 또는 물질 전달을 계산하는 스크리닝 모델이다. 출력은 JSON으로 직렬화할 수 있다. 이 모듈에는 반응성 연소, 화염 소염, 재점화 또는 실험 보정 응답식이 없으므로 `suppression`은 언제나 `insufficient_evidence`와 `null` 성능값을 반환한다. 수치 계산이 성공해도 FDS/OpenFOAM 반응성 CFD나 실험 검증을 완료했다는 뜻이 아니다.

## 공통 호출과 반환값

```python
from firelab.physics import simulate_method

result = simulate_method(
    {
        "scenario": {"duration_s": 4, "dt_s": 0.02, "distance_m": 1.0, "crosswind_m_s": 0.2},
        "methods": {"M3": {"flow_kg_s": 0.005, "diameter_um": 100}},
    },
    "M3",
)
```

입력의 누락값은 `CONTRACT.md`의 공학 기본값으로 채우고 반환값의 `assumptions`에 모두 기록한다. 값은 유한성과 물리적 범위를 검사하며 잘못된 입력은 `ValueError`로 중단한다. `field.points`와 `field.velocity`는 SI 단위의 3차원 벡터이고 최대 1,000개다. `series`는 짧게 샘플링한 시간 이력이다. `reaction_force_N`, `device_power_W`, `device_mass_kg`, `consumable_kg`는 드론 모델에 전달할 공통 자원·반력 계약이다. M3–M5에서 `loaded_consumable_kg`는 이륙 시 전체 탑재량이고 `consumable_kg`는 계산 중 실제 방출량이다.

## M1 저주파 음향

배플 원형 방출부의 축대칭 기하 확산과 선형 진행파 관계 `p_rms = rho*c*u_rms`를 사용한다. 근거리 크기는 방출부 반경으로 유한하게 두고, Rayleigh 거리 이후 빔 폭이 퍼지는 근사로 횡방향 장을 만든다. 입력 속도는 RMS이며 위상 평균 제곱 속도를 직접 계산한다. 표시 벡터의 +x 방향은 크기를 보여 주는 관례일 뿐, 한 주기 평균 유속은 0이다. 시계열의 순간 속도는 `sqrt(2)*u_rms*sin(2*pi*f*t)`다. 벽 반사, 비선형 음향, 실제 스피커 근접 유동과 화염 결합은 없다. `reaction_force_N`는 주기 평균 0이고, 구조 진동 입력은 `vibration_force_rms_N`과 `vibration_force_peak_N`으로 분리한다.

## M2 공기 와류 링

slug 길이 `L=U*T`와 `Gamma=eta*0.5*U*L`로 초기 순환을 정한다. `eta=0.35`는 측정값이 아닌 명시적 노즐 순환 효율 가정이다. 핵 반경은 `a(t)^2=a0^2+4*nu*t`로 성장하고, 링 자체 속도는 얇은 핵 근사식으로 계산한다. 공간 유동장은 유한 핵으로 정규화한 원형 와선의 Biot–Savart 적분을 수치 계산한다. 각 링 중심은 자체 속도와 균일 횡풍으로 대류한다. 벽, 난류 붕괴, 링 간 상호작용 및 화염 반응은 없다. `reaction_force_N`는 작동 중 최대 제트 반력이며 `reaction_pulse`가 펄스 폭·주기·duty와 정상력을 구분한다. 최소 공압 에너지는 출구 유동의 운동에너지 `0.5*rho*A*U^3*T`를 펄스별로 합산한다. 이는 압축기 손실을 제외한 낙관적 하한이다. 저장 에너지가 부족하면 감당할 수 없는 펄스를 생성하지 않고 `resource_status.status="insufficient"`로 남긴다.

## M3 지향 수분무

단분산 물방울 parcel의 항력, 중력, 횡풍, 원형 자유제트 운반과 증발을 시간 적분한다. 항력 완화시간에는 Reynolds 수 보정을 적용한다. 증발은 주변 온도와 상대습도로 제한한 Maxwell `d^2` 법칙의 스크리닝 계수이며 열·증기 피드백은 풀지 않는다. 표적 전달은 지정 거리의 원형 평면을 가로지른 액적 질량이다. 매 실행에서

`방출 = 표적 도달 + 증발 + 침착 + 영역 유출 + 종료 시 공중 잔류`

질량 수지를 반환한다. 분열, 충돌, 난류 분산과 화염 냉각·희석 반응은 없다. `delivered_kg`는 소화량이 아니다.

## M4 응축 에어로졸

M3와 같은 Lagrangian 수송 골격을 사용하지만 입자는 증발하지 않는 수동 고체로 취급한다. 기본 입자 밀도 1,800 kg/m³와 원형 운반 제트는 성분 자료가 없어서 둔 공학 가정이다. 응축 소화약제의 조성, radical 억제 반응, 생성기 고온 방출, 복사, 독성 및 잔류물은 계산하지 않는다. 따라서 출력은 전달·침착 질량뿐이며 화학적 소화효율은 비어 있다.

## M5 전도성 에어로졸 와류 / EHD

기본 `variant="CV"`는 M2의 와류장 안에서 M4와 같은 수동 전도성 입자를 운반하며 전기력을 전혀 더하지 않는다. `EHD` 또는 `COMBINED`를 선택하려면 `charge_density_C_m3`와 `electric_field_V_m`를 둘 다 0이 아닌 값으로 직접 제공해야 한다. 이 경우에만 사용자 입력의 균일 체적력 `f=qE`와 `a=f/rho_air`를 `ehd_length_m` 구간에 적용한다. 이 계산은 전극, Poisson 방정식, 전하 이동도, 절연 파괴와 결합하지 않은 미검증 상한 근사다. 전도성 자체에는 성능 가점을 주지 않는다. `reaction_pulse.peak_jet_force_N`은 펄스 제트 반력, `steady_force_N`은 입력장으로 계산한 EHD 정상 반력으로 따로 반환한다. M5 공압 하한에는 공기 펄스와 방출 입자의 출구 운동에너지를 모두 포함하며, 저장량이 부족하면 펄스 수와 실제 방출 입자 질량을 제한한다.

## 지표 해석과 검증 범위

- 속도장, 표적 속도, 순환, 질량 전달, 반력, 장치 에너지와 질량 수지는 수치 모델 출력이다.
- `evidence_type="unvalidated_physics"`는 모델이 계측 또는 native solver로 검증되지 않았음을 뜻한다.
- 장치 전력은 임무 시간 동안의 전기 에너지로 적분한다. M2/M5의 `stored_energy_capacity_J`는 저장 용량을 별도 표시하며 전기 에너지에 중복 합산하지 않는다.
- M3–M5의 입자 질량 수지는 소프트웨어 수준 보존 검증이다. 실제 분무 또는 에어로졸 성능 검증이 아니다.
- 화재 진압, HRR 감소, 소화시간과 성공률을 얻으려면 동일 연료·환기 조건의 반응성 모델과 독립 실험 검증이 추가로 필요하다.
