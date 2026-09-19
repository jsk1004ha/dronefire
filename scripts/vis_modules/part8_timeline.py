import numpy as np
import matplotlib.pyplot as plt
from .common import OUT_DIR

def generate():
    print("[8/10] Generating vis_08_mission_timeline_dashboard.png ...")
    t = np.linspace(0, 34, 341)
    x_pos = np.zeros_like(t)
    z_pos = np.zeros_like(t)
    
    for i, ti in enumerate(t):
        if ti < 3.0:
            x_pos[i] = 0.0
            z_pos[i] = 2.0 * (ti / 3.0)
        elif ti < 15.0:
            prog = (ti - 3.0) / 12.0
            shape = 10*prog**3 - 15*prog**4 + 6*prog**5
            x_pos[i] = 1.0 * shape
            z_pos[i] = 2.0
        elif ti < 25.0:
            x_pos[i] = 1.0
            z_pos[i] = 2.0
        else:
            prog = (ti - 25.0) / 9.0
            shape = 10*prog**3 - 15*prog**4 + 6*prog**5
            x_pos[i] = 1.0 * (1.0 - shape)
            z_pos[i] = 2.0 * (1.0 - 0.2*prog)
            
    hrr = np.zeros_like(t)
    for i, ti in enumerate(t):
        if ti < 15.0:
            hrr[i] = 16.2 + 0.4 * np.sin(ti * 2.5)
        elif ti < 19.0:
            hrr[i] = 16.2 * np.exp(-1.2 * (ti - 15.0))
        elif ti < 25.0:
            hrr[i] = 0.08 + 0.02 * np.sin(ti)
        else:
            hrr[i] = 0.05
            
    power = np.zeros_like(t)
    for i, ti in enumerate(t):
        if ti < 3.0:
            power[i] = 340.0
        elif ti < 15.0:
            power[i] = 315.0 + 15.0 * np.sin(ti)
        elif ti < 19.0:
            power[i] = 315.0 + 35.0
        else:
            power[i] = 315.0
            
    dt = t[1] - t[0]
    consumed_Wh = np.cumsum(power * dt) / 3600.0
    soc = 100.0 * (1.0 - consumed_Wh / 120.0)
    
    fig, (ax_gantt, ax_pos, ax_hrr, ax_pwr) = plt.subplots(4, 1, figsize=(13, 11), sharex=True,
                                                           gridspec_kw={"height_ratios": [0.8, 1.4, 1.4, 1.4]}, dpi=300)
    phases = [
        (0.0, 3.0, "1. 감지·이륙", "#94a3b8"),
        (3.0, 15.0, "2. 화원 정밀 접근 (0→1m)", "#38bdf8"),
        (15.0, 19.0, "3. 호버링·약제분사", "#ef4444"),
        (19.0, 25.0, "4. 화원 잔염·재발화 관측", "#f59e0b"),
        (25.0, 34.0, "5. 안전 복귀 (RTL)", "#10b981"),
    ]
    for start, end, label, col in phases:
        ax_gantt.barh(0, end - start, left=start, height=0.6, color=col, edgecolor="#ffffff", lw=1.5)
        ax_gantt.text((start + end)/2, 0, label, ha="center", va="center", color="#ffffff", fontweight="bold", fontsize=9.0)
        
    ax_gantt.set_yticks([])
    ax_gantt.set_title("드론 소화 미션 전주기(화재감지 · 접근 · 위치고정 · 소화 · 재발화관측 · 복귀) 통합 Timeline 대시보드", pad=15, fontweight="bold")
    ax_gantt.grid(False)
    
    ax_pos.plot(t, x_pos, color="#0284c7", lw=2.2, label="수평 거리 $X(t)$ [m] (화원 상대거리)")
    ax_pos.plot(t, z_pos, color="#6366f1", lw=2.0, ls="--", label="비행 고도 $Z(t)$ [m]")
    ax_pos.axhline(1.0, color="#94a3b8", ls=":", lw=1.2, label="목표 소화 이격거리 (1.0 m)")
    ax_pos.set_ylim(-0.15, 2.75)
    ax_pos.set_ylabel("드론 위치 [m]\n(Drone Position)", fontweight="bold")
    ax_pos.legend(loc="upper right", framealpha=0.92)
    ax_pos.grid(True, linestyle="--", alpha=0.5, color="#cbd5e1")
    
    ax_hrr.plot(t, hrr, color="#dc2626", lw=2.2, label="화재 발열량 $\\dot{Q}_{HRR}(t)$ [kW]")
    ax_hrr.axhline(0.1, color="#16a34a", ls=":", lw=1.5, label="소화 성공 판정선 (0.1 kW)")
    ax_hrr.set_ylim(-0.8, 20.5)
    ax_hrr.set_ylabel("화재 발열량 [kW]\n(Fire HRR)", fontweight="bold")
    ax_hrr.legend(loc="upper right", framealpha=0.92)
    ax_hrr.grid(True, linestyle="--", alpha=0.5, color="#cbd5e1")
    
    ax_pwr.plot(t, power, color="#d97706", lw=2.0, label="순간 소비전력 $P(t)$ [W]")
    ax_pwr_r = ax_pwr.twinx()
    ax_pwr_r.plot(t, soc, color="#059669", lw=2.0, ls="-.", label="배터리 잔여용량 SOC [%]")
    ax_pwr.set_ylim(285, 410)
    ax_pwr_r.set_ylim(95.0, 103.5)
    ax_pwr.set_ylabel("소비전력 [W]\n(Power)", fontweight="bold", color="#d97706")
    ax_pwr_r.set_ylabel("배터리 잔여량 [%]\n(Battery SOC)", fontweight="bold", color="#059669")
    ax_pwr.set_xlabel("미션 경과 시간 $t$ [s]", fontweight="bold")
    ax_pwr.grid(True, linestyle="--", alpha=0.5, color="#cbd5e1")
    
    lines1, labels1 = ax_pwr.get_legend_handles_labels()
    lines2, labels2 = ax_pwr_r.get_legend_handles_labels()
    ax_pwr.legend(lines1 + lines2, labels1 + labels2, loc="upper right", framealpha=0.92)
    
    for ax in [ax_pos, ax_hrr, ax_pwr]:
        ax.axvspan(15.0, 19.0, color="#fee2e2", alpha=0.45)
        ax.set_xlim(0, 34)
        
    plt.tight_layout()
    p = OUT_DIR / "vis_08_mission_timeline_dashboard.png"
    fig.savefig(p)
    plt.close(fig)
    print(f"   -> Saved: {p}")

if __name__ == "__main__":
    generate()
