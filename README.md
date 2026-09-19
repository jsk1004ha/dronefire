# Firefield · 드론 기반 화재 제어 연구실

제공된 PDF·DOCX·FDS/OpenFOAM 자료와 이미지 묶음을 바탕으로 작성한
[구현 계획](implement.md)을 실행 가능한 연구 소프트웨어로 옮긴 프로젝트입니다.
사용자가 선택한 다섯 후보인 저주파 음향, 공기 와류 링, 지향 수분무,
응축 에어로졸, 이온풍/전도성 에어로졸 와류를 같은 데이터 계약으로 다룹니다.

WP0~WP7에 걸친 실행·분석 기능을 구현했습니다. 반응성 모델과 연성 검증의
미완료 항목은 [구현 상태](IMPLEMENTATION_STATUS.md)에 명시했습니다. 현재 실제
반응성 FDS 경로는 C0·M1·M2·M3의 소형 연구 케이스를 계산하며, M1/M2는
각각 저마하 송풍과 펄스 노즐 근사입니다. M4/M5의 화학 억제·전기장 연성
화염 모델은 필요한 물성·검증자료가 없어 `needs_model`로 남습니다.

## 앱 실행

Windows에서 [실행.cmd](실행.cmd)를 더블클릭하면 로컬 앱
`http://127.0.0.1:8765`가 열립니다. 이미 실행 중이면 기존 서버를 사용합니다.
서버는 loopback에만 바인딩하며 PID와 로그는 `reports/server/`에 기록됩니다.

다른 PC에서는 Python 3.12 이상과 NumPy를 준비한 뒤 실행합니다.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -X utf8 -m firelab serve
```

앱의 기본 **시뮬레이션**은 다섯 방법의 전달장과 드론 6자유도 운동·전력
계산입니다. 화염 반응을 임의 점수로 만들지 않습니다. **캠페인** 경로는 실제
FDS 출력의 HRR·열유속·온도·산소 시계열을 반입해 소화 기준, 재점화,
검열/RMST, 노출 기준 시간을 계산합니다. 결과 화면의 `completed`는 해당
수치 실행의 완료 상태이며 실험 검증 완료 표시는 아닙니다.

## 명령줄 실행

### 전달장·드론 계산

```powershell
python -X utf8 -m firelab run
python -X utf8 -m firelab run --config configs\my_config.json
```

`run`은 M1~M5 비반응성 전달장, 반동, 질량·에너지 장부와 가정 사양 드론의
OFF/무보정/보정 비행을 계산합니다. 결과는 `runs/<run_id>/`에 저장됩니다.

### 반응성 캠페인

현재 기본값을 확인합니다.

```powershell
python -X utf8 -m firelab campaign-defaults
```

기본 36조건과 부분 투입량 대조군·sham·M5 분해군을 포함한 전체 설계를
실행하려면 다음 명령을 사용합니다. 지원되지 않는 M4/M5 조건은 다른 모델로
대체하지 않고 `needs_model`로 기록됩니다. 실제 실행 시간은 조건 수와
`native_timeout_s`에 따라 길어질 수 있습니다.

```powershell
python -X utf8 -m firelab campaign
```

우선 단독 조건만 확인하려면 아래 내용을 `configs\campaign_singles.json`으로
저장해 실행합니다.

```json
{
  "supplemental": false,
  "condition_ids": ["C0", "M1", "M2", "M3", "M4", "M5"]
}
```

```powershell
python -X utf8 -m firelab campaign --config configs\campaign_singles.json
```

캠페인 설정은 셀 수·시간·스레드·조건 수를 검증합니다. 기본 소화 및 노출
기준은 코드에 공개된 **screening 가정**이며 실험 보정 기준이나 인체
tenability 기준이 아닙니다. 사용자가 확정한 것은 다섯 연구 후보와 원격
진압의 범위이며, 장치 출력·입도·전력·열한계 같은 기본 수치는 명시적 가정입니다.

### 저장 결과 재분석

native solver를 다시 돌리지 않고 저장된 record로 최신 소화·시너지·노출
분석과 보고서를 다시 생성합니다.

```powershell
$study = Get-Content runs\campaign_latest.json | ConvertFrom-Json
python -X utf8 -m firelab reanalyze-campaign $study.campaign_id
```

입력 에너지가 확인되지 않은 방법도 HRR 소화 이벤트와 검열/RMST는 분석할 수
있습니다. 에너지 효율과 동일 예산 이득은 계속 `null` 또는 `incomplete`로
남으며 0 J로 치환하지 않습니다. 재점화 관측창이 부족하면 `unknown`입니다.

### FDS 공간장 내보내기

Smokeview 메타데이터와 native slice 파일이 있는 실행 디렉터리를 지정합니다.

```powershell
python -X utf8 -m firelab fields runs\native_cases\<case-key>\output --output runs\field_exports\<name>
```

내보내기는 실제 slice 격자·시간·물리량과 출처 해시를 보존합니다. 희소 CSV나
비반응성 전달 벡터를 반응성 3D 화염장으로 바꾸지 않습니다.

## WP0~WP7 구현 범위

| 단계 | 구현된 실행 경로 | 근거 한계 |
|---|---|---|
| WP0 입력·출처 | 첨부 해시, 단위·좌표·시간 계약, 가정/미지원 상태 | 원고 수치는 `reported_unverified` |
| WP1 native 기준 | FDS 안전 실행·완료/캐시 검증, OpenFOAM Taylor–Green 공간·시간 수렴 | 원본 1,800초 FDS는 아직 실행 중 |
| WP2 전달·결합 | M1~M5 전달장, 음향 수치검증, EHD Poisson/전하수송, 보존 remap | 장치 계측 및 화염 양방향 결합 미검증 |
| WP3 단독 화염 | C0/M1/M2/M3 소형 FDS 케이스, HRR 소화·재점화·RMST | proxy·가정 화원이며 실험 효율 아님 |
| WP4 조합 | 36조건·부분대조군, 순서효과, Holm 보정, 시너지/동일예산 gate, Pareto | 반복 검증자료와 SI 에너지 장부 필요 |
| WP5 드론 | D0~D5, 6자유도·반동·CG·센서·배터리·열·제약 스윕 | 로터–화염 CFD와 실제 기체 보정 없음 |
| WP6 노출·견고성 | 위치별 구간 검열/RMST, LHS, casewise train/holdout | 생존시간/FED로 자동 변환하지 않음 |
| WP7 산출물 | 캠페인 JSON/CSV/PNG/Markdown/HTML/ZIP, 재분석, 로컬 앱 | 보고서는 provenance와 evidence gate를 유지 |

자세한 계약은 [분석 문서](docs/study_analysis.md),
[드론 연구 문서](docs/drone_study.md), [native 실행 문서](docs/native.md),
[구현 상태](IMPLEMENTATION_STATUS.md)를 참고하세요.

## 현재 실제 실행 증거

`runs/reactive_C0_corrected/`부터 `runs/reactive_M3_corrected/`까지 16초 소형 native FDS
C0·M1·M2·M3가 solver 완료, 개입 전 연소 확인, HRR/DEVC 반입을 통과했습니다.
M4와 M5는 `needs_model`입니다. 이 실행은 실제 FDS 반응성 계산이지만 소형
가정 시나리오이며 M1/M2 장치 자체를 충실히 재현하거나 실험 소화 효율을
검증한 결과는 아닙니다.

이전 캠페인의 노즐 경계 중첩 문제는 수정했으며, 작동 진단이 없는 이전 개입
실행은 효과 분석에서 제외했습니다. 자세한 근거는 [작동 검증 기록](docs/source_activation.md)에 있습니다.

원본 Steckler 1,800초 입력은 별도 WSL ext4 실행이 진행 중입니다.
`status: running`인 manifest를 완료 결과로 인용하지 마세요. 앞선 900초 벽시계
제한 실행은 native 시간 180/1,800초에서 `timed_out`됐으며 별도 기록입니다.

## 화면과 물리식

화면은 제공된 디자인 자료를 참고해 크림색 바탕, 검은 글자, 얇은 구분선과
고정폭 글꼴 중심으로 구성했습니다. 그래프의 색은 실제 데이터 구분에 사용합니다.

[물리식 유도와 적용 범위](docs/physics_derivation.md),
[5개 방법의 전달 모델](docs/transport_derivation.md),
[드론 운동·동력·열 모델](docs/drone_derivation.md)에 지배방정식, 단위,
수치 적분 방법과 경험적 가정을 기록했습니다. 배터리 에너지 상한, 작동 구간의
질량·충격량, 열 방정식의 닫힌형 적분을 검사하며, 전달 모델도 음향 출력·와류
에너지·입자 질량 장부를 검사합니다. 이 검사는 실제 장치 성능 검증을 대신하지 않습니다.

보조 계산 결과에는 입력·소스·출력 해시를 저장해 모델 변경 전 결과의 재사용을 방지합니다.

## 2026-09-19 물리·수치 감사

[수정 내역과 재현 조건](docs/physics_audit_2026-09-19.md)에 순간 출력 제한, 약제 방출·반동·무게중심, 반력 적분 및 native 분사 경계 검증을 기록했습니다. 기존 결과는 변경하지 않았으며, 모델 변경 전 결과를 새 결과로 재사용하지 마세요.

## 검증 명령

```powershell
python -X utf8 -m unittest discover -s tests -v
node --check web\app.js
python -X utf8 -m firelab audit
python -X utf8 scripts\native_fds.py status
python -X utf8 scripts\native_openfoam.py status
```

테스트 개수는 개발 중 바뀔 수 있으므로 문서에 고정하지 않습니다. `audit`의
차단 항목은 필요한 원자료·검증이 없다는 증거이며 임의 값으로 통과시키지 않습니다.
