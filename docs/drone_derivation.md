# 드론 탑재 물리 모델 유도와 적용 범위

이 문서는 `firelab/drone.py`가 계산하는 식, 단위, 수치 경계 처리와 한계를 설명한다. 이 모델은 후보 장치의 탑재 가능성을 비교하는 1차 공학 모델이다. 비행 안전 인증이나 실제 화재 진압 성능을 보증하지 않는다.

## 1. 좌표계와 병진 운동

세계 좌표의 위쪽을 \(z\)축으로 두고, 기체 자세 행렬을 \(R(q)\), 기체 \(z\)축 단위벡터를 \(e_3\)라 둔다. 질량중심의 운동량 보존식은 다음과 같다.

\[
m\dot{v}=T R(q)e_3+F_{reaction}+F_{drag}-mg e_3
\]

- \(m\): 기체·장치·남은 약제의 합계 질량 [kg]
- \(T\): 전체 로터 추력 [N]
- \(F_{reaction}\): 분사 장치가 기체에 가하는 반력 [N]
- \(F_{drag}\): 상대풍에 의한 항력 [N]

항력은 일정한 투영면적을 사용하는 집중 모델이다.

\[
F_{drag}=\frac{1}{2}\rho C_D A_D\lVert v_{rel}\rVert v_{rel}
\]

코드에서는 속도를 먼저 갱신한 뒤 위치를 갱신하는 semi-implicit Euler 방법을 쓴다. 이산 시간 오차가 있으므로 `dt_s` 수렴성 확인이 필요하다.

## 2. 로터 추력과 유도동력

[NASA Glenn의 단순 운동량 이론](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/propeller-thrust/)에서 추진 원판의 추력은 질량유량과 유속 변화로부터

\[
T=\dot m(V_e-V_0),\qquad \dot m=\rho A V_p,\qquad
V_p=\frac{V_e+V_0}{2}
\]

로 주어진다. 정지비행에서는 \(V_0=0\), 원판 유도속도를 \(v_i=V_p\)라 두면 \(V_e=2v_i\)이므로

\[
T=2\rho A v_i^2,qquad
v_i=\sqrt{\frac{T}{2\rho A}}
\]

이다. 이상적인 유도동력은

\[
P_{ideal}=T v_i=\frac{T^{3/2}}{\sqrt{2\rho A}}
\]

이고, 손실을 한 개의 효율 \(0<\eta\le 1\)로 묶으면 배터리 쪽 요구동력과 동력으로 가능한 최대 추력은

\[
P_{elec}=\frac{P_{ideal}}{\eta},\qquad
T_{power}=\left(\eta P_{elec}\sqrt{2\rho A}\right)^{2/3}
\]

이 된다. `hover_efficiency`는 이 \(\eta\)이며 1을 넘는 입력은 거부한다. 전체 원판면적은 로터가 겹치지 않는다고 보고 \(A=N\pi r^2\)로 계산한다. 이 식은 이상적인 actuator disk 근사라서 블레이드 끝단 손실, 로터 간 간섭, 전진비행, 지면효과를 포함하지 않는다.

## 3. 회전 운동과 분사 반력 모멘트

[MIT OCW 16.07의 Euler 강체 방정식](https://ocw.mit.edu/courses/16-07-dynamics-fall-2009/resources/mit16_07f09_lec28/)에 따라 기체 좌표에서

\[
I\dot\omega+\omega\times(I\omega)=\tau
\]

를 적분한다. 장치 반력이 질량중심에서 \(r\)만큼 떨어져 작용하면

\[
\tau_{reaction}=r\times F_{reaction}
\]

이다. 자세는 단위 쿼터니언으로 나타내며

\[
\dot q=\frac{1}{2}q\otimes[0,\omega]
\]

를 사용한다. 각 시간구간에서는 갱신된 각속도가 일정하다고 보고 회전 증분

\[
\Delta q=\left[\cos\frac{\lVert\omega\rVert\Delta t}{2},
\frac{\omega}{\lVert\omega\rVert}\sin\frac{\lVert\omega\rVert\Delta t}{2}\right]
\]

을 곱한다. 이 방식은 단순 오일러 쿼터니언 갱신보다 단위 노름을 잘 보존하며, 계산 후에도 유한성과 단위 노름을 확인한다.

자세 제어 모멘트는 \(\tau_c=-K_R e_R-K_\omega\omega\)로 두고 `max_torque_Nm`에서 포화시킨다. 한계가 0이면 제어 모멘트도 정확히 0이다. 분사 반력 모멘트는 외력 모멘트이므로 이 제어기 포화 뒤에 별도로 더한다.

관성모멘트 \(I\)는 대각·고정값이다. 약제 소비에 따른 질량중심 이동은 반력의 지레팔 계산에는 반영하지만, 관성텐서 자체의 변화는 반영하지 않는다.

## 4. 질량과 충격량 보존

전달 모델이 `consumable_release`를 제공하면 실제 유량과 방출 종료 시각을 사용한다.

\[
\Delta m_{emit}=\dot m_{source}\,\left|[t,t+\Delta t]\cap[0,t_{release}]\right|,
\qquad \bar{\boldsymbol F}_{particle}=-\boldsymbol u_{exit}\frac{\Delta m_{emit}}{\Delta t}.
\]

기체 총질량은 방출된 질량만큼만 줄어든다. 방출 종료점을 시간격자에 삽입하고,
남은 약제는 원래 탱크 위치에서 질량과 무게중심에 기여한다. OFF/D2 대조군도
장치와 탱크의 질량을 합쳐 다른 위치로 옮기지 않는다. 방출 정보가 없는 기존
입력만 `m_emit / t_act`의 균일 방출로 해석한다.

반력 시계열은 구간 내 모든 꺾임점을 포함한 조각별 선형 적분으로 평균한다.
펄스는 시간단계와 겹치는 길이를 적분하고 입자 반동을 별도로 더한다.

\[
\bar{\boldsymbol F}=\frac{1}{\Delta t}\int_t^{t+\Delta t}\boldsymbol F(s)\,ds.
\]

이는 명시한 보간 모델의 벡터 충격량을 보존한다. 단, 운동·자세는 여전히 유한
시간단계의 축약 모델이며, 한 단계 안의 자세 변화를 정확 적분한다는 뜻은 아니다.
기존 `reaction_impulse_Ns`는 `sum(dt * norm(F_average))`, `peak_reaction_force_N`은
구간 평균력의 최댓값이다. 단계 내부에서 힘의 방향이 바뀌거나 짧은 펄스가 있으면
이 수치는 실제 절댓값 하중 적분이나 순간 피크보다 작을 수 있어 시간 수렴 검사가 필요하다.

## 5. 배터리 에너지와 무전원 상태

배터리는 저장 에너지 \(E\)와 버스 최대동력 \(P_{max}\)로 나타낸다.

\[
\dot E=-P_{bus},\qquad
0\le P_{bus}\le \min\left(P_{max},\frac{E}{\Delta t}\right)
\]

각 시간구간에서 전력은 항전장비, 작동장치, 추진 순으로 배분한다. 실제 사용에너지는 절대로 남은 저장에너지를 넘지 않는다. 에너지가 0이 되면 이후 구간에서 전기식 장치와 로터 추력은 0이며, 중력·항력·전기와 무관한 외력만 계속 적분한다. 출력의 `electrically_unpowered_s`, `battery_depleted`, `energy_balance_error_J`가 이 상태와 보존 오차를 드러낸다.

이는 전압, 내부저항, 방전율, 모터·ESC 효율곡선을 생략한 에너지 상한 모델이다. 실제 배터리와 모터 자료가 있으면 해당 지도를 추가해야 한다.

## 6. 집중 열용량 모델

열 입력이 \(Q\), 주위온도가 \(T_\infty\), 열용량이 \(C\), 선형 냉각계수가 \(H\)일 때 에너지 보존식은

\[
C\frac{dT}{dt}=Q-H(T-T_\infty)
\]

이다. MIT의 열전달 강의도 [lumped capacitance method](https://ocw.mit.edu/courses/2-051-introduction-to-heat-transfer-fall-2015/pages/readings/)를 과도 열전달의 기본 모델로 다룬다. 한 시간구간에서 \(Q\)가 일정하고 \(H>0\)이면 닫힌형 해는

\[
T(t+\Delta t)=T_{eq}+[T(t)-T_{eq}]e^{-H\Delta t/C},
\qquad T_{eq}=T_\infty+\frac{Q}{H}
\]

이다. \(H=0\)이면 \(T(t+\Delta t)=T(t)+Q\Delta t/C\)를 사용한다. 코드가 이 식을 직접 사용하므로 큰 시간간격에서 명시적 오일러법이 주위온도를 지나쳐 음의 온도를 만드는 문제가 없다.

집중 열용량 모델은 물체 내부 온도가 거의 균일하다는 가정이 필요하다. 열유속, 노출면적, 열용량, 냉각계수는 실측값으로 보정해야 하며, 복사·차폐·배터리 내부 발열과 공간 온도구배는 현재 모델 밖이다.

## 7. 코드 출력의 해석

- `feasible_in_model`: 입력된 가정과 제한 안에서 추력·전력·열·추종 기준을 통과했다는 뜻이다.
- `conditional`: 계산은 가능하지만 추종오차나 포화가 관측되었다.
- `infeasible`: 탑재량, 추력, 전력, 배터리, 귀환 예비량, 열 한계 중 하나 이상을 위반했다.
- `evidence_type: unvalidated_physics`: 실제 기체 시험으로 보정되지 않은 물리 기반 선별 계산임을 뜻한다.

화염 억제율은 이 비행 모델에서 만들지 않는다. 비행 가능성과 화재 진압 효과는 서로 다른 검증 문제이며, FDS/OpenFOAM 계산이나 반복 실험으로 별도 확인해야 한다.
