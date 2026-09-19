import copy
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from .common import ROOT, OUT_DIR
from firelab.config import validate_config
from firelab.physics import simulate_method
from firelab.drone import simulate_mission

def generate():
    print("[1/10] Generating vis_01_crosswind_latency_heatmap.png ...")
    cfg = validate_config({})
    phys = simulate_method(cfg, "M2")
    
    crosswinds = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0])
    latencies = np.array([0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50])
    error_matrix = np.zeros((len(latencies), len(crosswinds)))
    
    for i, lat in enumerate(latencies):
        for j, wind in enumerate(crosswinds):
            c = copy.deepcopy(cfg)
            c.setdefault("scenario", {})["crosswind_m_s"] = float(wind)
            c["sensor"] = {
                "latency_s": float(lat),
                "sample_rate_Hz": 10.0,
                "position_error_std_m": 0.05,
                "velocity_error_std_m_s": 0.02,
                "availability_fraction": 1.0,
                "seed": 42
            }
            res = simulate_mission(c, phys, controller_enabled=True)
            error_matrix[i, j] = res["metrics"]["max_position_error_m"]
            
    fig, ax = plt.subplots(figsize=(11, 7.6), dpi=300)
    cmap = sns.color_palette("YlOrRd", as_cmap=True)
    sns.heatmap(
        error_matrix,
        xticklabels=[f"{w:.1f}" for w in crosswinds],
        yticklabels=[f"{l:.2f}" for l in latencies],
        annot=True,
        fmt=".2f",
        cmap=cmap,
        cbar_kws={"label": "최대 위치 추종 오차 [m] (Max Position Error)"},
        ax=ax,
        linewidths=0.5,
        linecolor="#f1f5f9"
    )
    ax.invert_yaxis()
    ax.set_title("횡풍 풍속 및 센서 피드백 지연시간에 따른 드론 6-DOF 최대 위치오차 Heatmap", pad=32, fontweight="bold", fontsize=13)
    ax.set_xlabel("주변 횡풍 풍속 $U_{crosswind}$ [m/s]", labelpad=10, fontweight="bold", fontsize=11)
    ax.set_ylabel("센서 피드백 지연시간 $\\tau_{delay}$ [s]", labelpad=10, fontweight="bold", fontsize=11)
    
    ax.annotate(
        "■ 정밀 호버링 안정권 (< 0.5 m)   |   ■ 주의·안전 한계선 (0.5 ~ 1.0 m)   |   ■ 제어 이탈 위험 영역 (> 1.5 m)",
        xy=(0.5, 1.02), xycoords="axes fraction",
        ha="center", va="bottom",
        fontsize=9.5, fontweight="bold", color="#1e293b",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#ffffff", edgecolor="#cbd5e1", alpha=0.95)
    )
            
    plt.tight_layout()
    p = OUT_DIR / "vis_01_crosswind_latency_heatmap.png"
    fig.savefig(p)
    plt.close(fig)
    print(f"   -> Saved: {p}")

if __name__ == "__main__":
    generate()
