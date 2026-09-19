# WP5 드론 탑재 연구 모듈

`firelab.drone_study.run_drone_study`는 `implement.md`의 D0~D5 비교를 실행한다. 결과의 비행·전력·반동·센서·열 계산은 설계 탐색용이며 실제 기체 인증이나 소화 성능 증거가 아니다.

## API

```python
from firelab.drone_study import run_drone_study, write_drone_study_exports

study = run_drone_study(config, method_results, imported_losses=None)
paths = write_drone_study_exports(study, "runs/wp5")
```

`method_results`는 `firelab.physics.simulate_method` 결과의 목록 또는 `method_id`별 매핑이다. 각 방법에 `material_ids`를 추가하면 약제·소모품의 배치 ID를 보존한다. 소모품이 있는데 ID가 없으면 `material_identity_status=missing_for_consumable`로 남는다.

내보내는 파일은 다음과 같다.

- `drone_study.json`: 모든 조건, 시계열, 제약 스윕, 가정과 제한
- `drone_feasibility.csv`: D2~D5 상태와 주요 비행 지표
- `drone_mission_series.csv`: 실제 적분된 위치·자세·전력·잔량 시계열
- `drone_requirements.csv`: 질량·추력·전력·배터리·횡풍·센서·반동 모멘트암·열유속 스윕

## D0~D5

- D0: 장치와 드론이 없는 동일 화재의 자리표시자다. 외부 화재 계산 또는 실험이 필요하다.
- D1: 고정 장치의 전달 계산을 보존한다. 전달장만으로 소화 손실을 만들지 않는다.
- D2: 같은 초기 장착 질량을 유지하고 장치를 끈 비행이다.
- D3: 장치를 켜고 기본 자세 루프만 사용한다. 외란 위치 보정은 끈다.
- D4: 장치를 켜고 위치·자세 보정을 사용한다.
- D5: 횡풍, 센서 열화, 높은 탑재율, 열 노출, 이들을 합친 조건을 각각 실행한다.

D1~D4에는 동일한 허용 예산 벡터와 물질 ID를 복사한다. D2는 장치를 끄므로 실제 소비는 0이지만, 비교에 사용할 수 있었던 장착 자원과 질량 조건은 같은 벡터로 남긴다.

## 센서, 무게중심과 후류

센서 모델은 갱신률, 지연, 위치·속도 표준편차, 관측 가능 비율과 난수 seed를 입력받는다. 지연된 상태를 표본화하고 관측 실패 시 마지막 표본을 유지한다. 같은 seed에서는 결과가 재현된다. 연기 영상 인식 자체를 계산하는 모델은 아니다.

`drone.airframe_cg_m`, `device_mount_position_m`, `consumable_position_m`가 모두 주어지면 소모품 질량 감소에 따라 무게중심을 다시 계산하고 실제 장착점과 현재 무게중심 사이 모멘트암으로 반동 토크를 계산한다. 위치가 없으면 기존 `reaction_lever_arm_m`을 사용하며 CG 평가는 N/A다.

로터 후류는 이상 호버 actuator-disk 운동량 이론의 disk loading, disk 유도속도, 이상 far-wake 속도만 출력한다. 국부 속도장은 `null`이며 회전자 해석이나 측정값이 없다는 이유가 함께 저장된다. 이 결과를 CFD 후류로 표시하면 안 된다.

## 열 입력과 D5 기본값

명목 config에 `thermal`이 없으면 `thermal_assessment_status=insufficient_evidence`다. D5 열 민감도 계산은 아래 값을 명시적 가정으로 넣고 `declared_screening_assumption`으로 표시한다.

현재 제공 자료에는 기체·후류·센서·부품 열·화재효과를 모두 독립 검증한 입력이 없으므로 `practical_effectiveness_status`는 `insufficient_evidence`를 유지한다. 개별 비행의 `feasible_in_model`은 입력한 가정 안에서 수치 제약을 통과했다는 뜻이며 실기체 실효성 판정이 아니다.

| 입력 | 기본값 |
| --- | ---: |
| 횡풍 | 3.0 m/s |
| 센서 | 5 Hz, 0.20 s 지연, 위치 0.10 m, 속도 0.05 m/s 표준편차, 관측률 0.80 |
| 높은 탑재 조건 | payload capacity의 90% |
| 열 | 5 kW/m², 노출면적 0.08 m², 열용량 4 kJ/K, 냉각 8 W/K, 한계 333.15 K |

이는 제조사 한계나 실측 범위가 아니다. `config.drone_study.d5_assumptions`로 교체할 수 있으며, 실제 판정에는 기체 사양서와 부품별 열 시험값을 사용해야 한다.

## 화재 효과 유지율 입력 계약

비행 모델은 D0~D4의 열손실을 생성하지 않는다. `imported_losses`에 동일 블록의 다섯 조건이 모두 있어야 다음 값을 계산한다.

```python
{
  "method_id": "M3",
  "block_id": "B01",
  "condition_id": "D0",
  "loss_J_m2": 100000.0,
  "match": {
    "distance_m": 1.0,
    "start_time_s": 0.0,
    "observation_window_s": 10.0,
    "budget": {"electrical_energy_J": 350.0},
    "material_ids": ["water:batch-001"]
  },
  "provenance": {"evidence_type": "experimental"}
}
```

한 블록 안에서 거리, 시작시각, 관측창이 D0~D4에 일치해야 한다. D1~D4의 예산과 물질 ID도 정확히 일치해야 한다. 허용 증거는 `measured`, `experimental`, `validated_simulation`이다. 조건 누락, 예산·물질 불일치, 약한 증거에서는 유지율을 `null`로 두고 이유를 반환한다.

고정 장치 이득 `L_D0-L_D1`이 양수일 때만

`R_D3=(L_D2-L_D3)/(L_D0-L_D1)`, `R_D4=(L_D2-L_D4)/(L_D0-L_D1)`

을 계산한다. 전체 순효과 `L_D0-L_D3`, `L_D0-L_D4`는 별도로 보존한다.
블록이 여러 개면 블록 대응을 유지한 bootstrap 500회(seed 42)로 95% 구간을 함께 출력한다.

## 제약 스윕

기본 스윕은 횡풍 0~5 m/s, 센서 지연 0~0.5 s, 명목 payload·추력·전력·배터리의 0.75~1.5배, 반동 모멘트암 0~0.3 m, 열유속 1~10 kW/m²다. 모두 연구용 탐색 범위이며 제조사 검증 범위가 아니다. 각 점은 동일한 적분 모델을 다시 실행하고 상태, 실패 원인, 위치 오차, 잔량, 온도, 추력 여유를 저장한다.
