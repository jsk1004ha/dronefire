# 드론 임무 시뮬레이션

`firelab.drone.simulate_mission(config, method_result, controller_enabled=True)`는 접근, 장치 작동, 복귀를 한 번의 강체 적분으로 계산한다. 출력의 `feasible_in_model`, `conditional`, `infeasible`는 입력한 가정 모델 안의 비행·자원 가능성이다. 실제 화재 진압 성능, 기체 안전 인증, 인명 안전성을 뜻하지 않는다.

## 계산 모델

상태는 위치·속도, 단위 quaternion `q=[w,x,y,z]`, body 각속도, 배터리 에너지, 소모품 질량이다. `q`는 body 좌표를 world 좌표로 회전하며 다음 식을 정규화해 적분한다.

```text
r_dot = v
m v_dot = R(q) [0,0,T] + F_reaction - m g e_z
q_dot = 1/2 q ⊗ [0,omega]
I omega_dot = tau_control + r_mount × F_reaction - omega × (I omega)
```

표시용 roll/pitch/yaw는 매 시점의 quaternion 회전행렬에서 ZYX Euler 각으로 변환한다. 내부 적분에는 Euler 각을 사용하지 않으므로 pitch 부근의 표시 특이점이 자세 상태를 손상시키지 않는다.

기준 궤적은 x 방향 minimum-jerk 접근, 표적 위치 정지, minimum-jerk 복귀로 구성된다. 위치 제어가 켜지면 PD 보정이 기준 가속도에 더해지고, 자세 제어기는 요구 합력 방향으로 기체 z축을 정렬한다. `controller_enabled=False`는 위치·속도 외란 보정과 반동 재조준을 끄지만 기준 궤적 비행 및 hover에 필요한 기본 자세 안정화는 유지한다. 따라서 고정된 기준 자세로 비행하면서 반동에 밀리는 D3 조건이며 모터 정지 시험이 아니다.

`simulate_controls`는 같은 입력에서 `off`, `uncorrected`, `corrected`를 반환한다. OFF는 장치와 약제를 포함한 **같은 시작 탑재질량**을 유지하지만 장치 전력, 반동, 약제 소비를 0으로 둔다. `uncorrected`는 장치를 작동하되 위치 외란 보정이 없고, `corrected`는 위치 피드백까지 켠 조건이다.

## 반력, 추력, 전력, 자원

`method_result.reaction_force_N`은 기본적으로 body 좌표의 기체 반력이다. `reaction_frame: "world"`로 world 좌표를 선택할 수 있다. 부호는 장치가 유체에 가한 힘이 아니라 **기체가 받은 힘**이어야 한다. 장착점은 `drone.reaction_lever_arm_m`이며 `r × F` 모멘트를 적용한다.

펄스 장치는 다음처럼 peak jet과 steady 반력을 분리한다. 적분 스텝과 펄스 경계가 일치하지 않아도 각 스텝 구간에서 실제 ON 시간이 차지하는 비율을 계산해 평균 반력을 적용하므로 충격량의 격자 alias 편향을 줄인다.

```python
method_result["reaction_pulse"] = {
    "peak_force_N": [4.0, 0.0, 0.0],
    "peak_jet_force_N": [4.0, 0.0, 0.0],
    "steady_force_N": [0.0, 0.0, 0.0],
    "period_s": 1.0,
    "pulse_duration_s": 0.05,
}
```

또는 `method_result.series` 각 행에 `time_s`와 `reaction_force_N`을 넣으면 선형 보간한 시간별 반력을 사용한다. 두 입력이 모두 있으면 시계열을 우선한다.

`loaded_consumable_kg`는 출발 시 실은 약제 전체이고 `consumable_kg`는 이번 임무에서 방출할 양이다. 방출하지 않은 차이는 복귀 때까지 ballast로 남는다. `resource_status.status`가 `insufficient`이면 전기 배터리가 충분해도 압축가스 등 장치 자체 저장 에너지 부족으로 임무를 `infeasible` 처리한다.

`reaction_pulse.simulated_pulses`가 있으면 저장 에너지로 실제 가능한 펄스 수까지만 반동을 적용한다. 따라서 자원 부족 케이스는 실패 사유만 붙이는 것이 아니라 제한된 실제 충격량도 궤적에 반영한다.

로터 전력은 총 원판면적 `A`를 사용하는 운동량 이론으로 계산한다.

```text
P_induced = T^(3/2) / (efficiency sqrt(2 rho A))
```

가용 총전력에서 avionics와 작동 중 장치 전력을 뺀 뒤 역산한 추력과 `max_thrust_N` 중 작은 값을 실제 한계로 사용한다. 배터리는 실제 시간 적분 전력을 차감한다. 소모품은 작동 구간에 균등 소비되어 질량과 필요한 hover 추력이 함께 감소한다. 작동 종료 시점에는 예상 복귀 hover 에너지와 사용자가 지정한 `reserve_fraction`을 모두 남겨야 하며, 최종 시점에도 예비에너지가 남아야 한다.

`scenario.crosswind_m_s`는 world +y 방향 바람이며, `drone.drag_coefficient`와 `drone.drag_area_m2`의 lumped quadratic drag로 상대풍 힘을 계산한다. 출력에는 peak 상대풍, peak 항력, 원판하중, hover 유도속도가 포함된다. 이는 로터-resolved 후류나 화염-후류 결합 계산이 아니며 limitation에 그 범위가 명시된다.

## 열 모델과 판정

열 안전성은 기본값으로 추정하지 않는다. 아래 값을 모두 제공할 때만 1절점 lumped thermal 모델을 계산한다.

```json
{
  "thermal": {
    "incident_flux_W_m2": 2500,
    "exposed_area_m2": 0.08,
    "heat_capacity_J_K": 12000,
    "cooling_W_K": 18,
    "max_temperature_K": 343.15,
    "initial_temperature_K": 293.15
  }
}
```

이 입력이 있어도 독립 계측으로 보정하기 전에는 선별용 계산이다. 열 입력이 없으면 `peak_temperature_K`는 `null`이고 limitation에 미평가 사유가 남는다.

- `infeasible`: 배터리 고갈, 출력/추력 부족, 탑재용량 초과, 복귀 예비에너지 부족, 명시한 열 한계 초과가 발생했다.
- `conditional`: 하드 실패는 없으나 추력/전력 포화 또는 위치 추종 허용오차 초과가 관찰됐다.
- `feasible_in_model`: 위 제약을 이 가정 모델 안에서 통과했다. 실험 검증 상태는 여전히 `unvalidated_physics`다.

`series`에는 실제와 기준 궤적, roll/pitch/yaw, 전력, 배터리, 위치 오차, 소모품과 선택적 온도가 들어 있어 3D 궤적과 D2 OFF/D3·D4 탑재 비교 그래프에 직접 사용할 수 있다.

## 추가 설정 키

공유 계약의 기본 키 외에 상위 오케스트레이터가 선택적으로 넘길 수 있는 값은 다음과 같다. 모두 SI 단위이며 미지정 값은 보정값이 아닌 가정값이다.

- `drone.payload_capacity_kg`, `initial_altitude_m`: 탑재 한계와 기준 비행 고도
- `drone.position_kp_s2`, `position_kd_s`, `attitude_kp_Nm`, `attitude_kd_Nms`, `max_torque_Nm`: 제어기와 토크 포화
- `drone.tracking_tolerance_m`, `reaction_lever_arm_m`: 조건부 판정 오차와 장치 장착점
- `drone.drag_coefficient`, `drag_area_m2`, `scenario.crosswind_m_s`: lumped 상대풍 항력
- top-level `thermal`: 보정이 필요한 선택적 열 입력 묶음
