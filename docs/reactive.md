# 반응성 FDS 소형 화염 실험 생성기

`firelab.reactive`는 FDS 6.11.1용 작은 반응성 화염 입력을 만든다. 모든 결과는 FDS가 계산한 시간별 HRR·온도·산소 농도를 읽어야 한다. 이 생성기는 소화율, 소화 성공 여부, 생존시간을 계산하거나 넣지 않는다.

## API

```python
from firelab.reactive import build_reactive_case, default_reactive_conditions

condition = next(item for item in default_reactive_conditions() if item["id"] == "S_M3")
manifest = build_reactive_case(None, condition, "runs/reactive_S_M3")
```

`status: ready`는 FDS 입력으로 표현 가능한 M1–M3만 사용했다는 뜻이다. 실행 성공이나 소화 효과를 뜻하지 않는다. `status: needs_model`은 M4 또는 M5가 포함되어 입력을 쓰지 않았다는 뜻이다.

M1은 60 Hz 음파가 아니라 낮은 마하수의 기계적 강제기류 외피다. 입력에 기록한 60 Hz는 장치 후보 메타데이터일 뿐, FDS가 음압파나 왕복 유동을 푼다는 뜻이 아니다. M2는 펄스 노즐 유동이며, 와류 링의 형성과 전달은 FDS 출력으로 확인하고 별도 검증해야 한다. M3은 액적 증발·열전달·표면 냉각을 계산하는 수분무 전달 경우다. 이 소형 사례의 불꽃은 일정 질량유속 프로판 기체원으로 만든 것으로, 응축연료 수분무 소화 검증 사례가 아니다. C0 원시 실행은 16초를 완료했고 개입 전 HRR 약 16.6 kW를 기록했다. M4의 응축 에어로졸 화학 억제와 M5의 이온풍/전도성 와류는 FDS 기본 해석 범위를 벗어나므로, 구성·반응 또는 전하 수송·검증 자료가 제공되기 전에는 `needs_model`로 막는다.

## 설계

36개 조건은 C0 1개, 단독 5개, 동시 2조합 10개, 순차 순서쌍 20개다. 동시 조합은 각 방법이 4초 창에서 설정량의 0.5배를 사용하고, 순차 조합은 각 방법이 2초 창에서 설정량의 1배를 사용한다. 이 규칙은 방법 간 자원 동등성 또는 효과 동등성을 의미하지 않는다. `metadata.partial_single_id`는 사후 분석에서 각 조합 성분과 같은 일정·용량의 단독 비교군을 생성하도록 식별한다.

## FDS 근거와 한계

* [FDS 6.11.1 공식 릴리스](https://github.com/firemodels/fds/releases/tag/FDS-6.11.1)와 [NIST FDS 매뉴얼](https://pages.nist.gov/fds/manuals.html)을 기준으로 한다.
* FDS 기술참조의 [연소·소염 모델](https://github.com/firemodels/fds/blob/master/Manuals/FDS_Technical_Reference_Guide/Combustion_Chapter.tex)은 `EXTINCTION 1/2`가 세포 수준 산소·온도 또는 연료·산소 기준임을 설명한다. 격자, 연료와 검증 범위를 벗어난 일반 소화 성능식이 아니다.
* [입자 장](https://github.com/firemodels/fds/blob/master/Manuals/FDS_Technical_Reference_Guide/Particle_Chapter.tex)은 수분무의 액적·열전달·표면 냉각이 중요하고, 복잡한 연료에서 억제율을 단순 상관식으로 일반화하기 어렵다고 명시한다.

따라서 각 실행 뒤에는 `*_hrr.csv`, `*_devc.csv`, 완료 시간, 격자 민감도와 실험 대조 자료를 함께 보관해야 한다. 개입 전 1초에 HRR 표본 2개 이상이 0.01 kW를 넘지 않으면 소화 판단에서 제외한다. 소화 사건의 사전 등록 기준은 유효한 개입 전 화염을 전제로 HRR이 0.1 kW 이하로 1초 이상 유지되는 것이다. CO 수율 근거가 없어 `CO_YIELD`와 CO 채널은 입력하지 않았으며 0으로 간주하지 않는다. 입력에 지정한 프로판 질량유속과 노즐·액적 설정은 공개한 연구 가정이며 실험 보정값이 아니다.

## 2026-09-19 소스 활성화 수정

초기 입력은 `x=0` 전체를 `OPEN`으로 선언한 뒤 같은 영역에 소스 `VENT`를 중첩했다. FDS는 입력을 실행했지만, C0·M1·M2·M3의 HRR 배열이 사실상 같았고 소스 활성화를 입증할 수 없었다. 따라서 초기 결과는 개입 효과 자료로 사용할 수 없다.

수정 입력은 `x=0`의 `OPEN` 경계를 세 개의 0.1 m × 0.1 m 소스 패치를 제외하도록 분할하고, 모든 조건에 같은 M1·M2·M3 패치를 둔다. M3의 공기 운반류와 물방울 질량유속도 같은 RAMP로 함께 켜고 끈다. `SOURCE_M1_U`, `SOURCE_M2_U`, `SOURCE_M3_U`, `SOURCE_M3_DVF`를 시간별로 저장한다. 수정한 16초 FDS 6.11.1 실행은 `runs/reactive_C0_corrected` 등 네 폴더에 보관했다. 6–10초 창에서 M1의 속도 최대값은 0.393 m/s, M2는 3.108 m/s, M3는 3.232 m/s와 물방울 체적분율 8.25e-5였다. 이는 소스가 켜졌다는 증거일 뿐 소화 성능 증거가 아니다.
