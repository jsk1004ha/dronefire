import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from .common import OUT_DIR

def generate():
    print("[9/10] Generating vis_09_suppression_phase_map.png ...")
    q_fire = np.linspace(5.0, 100.0, 150)
    u_wind = np.linspace(0.0, 8.0, 150)
    Q, W = np.meshgrid(q_fire, u_wind)
    
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5), sharey=True, dpi=300)
    distances = [0.8, 1.2, 2.0]
    d_labels = ["근접 이격 거리 (d = 0.8 m)", "기준 이격 거리 (d = 1.2 m)", "원거리 이격 거리 (d = 2.0 m)"]
    
    for idx, (dist, label) in enumerate(zip(distances, d_labels)):
        ax = axes[idx]
        P_eff = 50.0
        psi = (P_eff / Q)**0.45 - 0.12 * W * (dist / 1.0)**1.2
        
        regimes = np.zeros_like(psi)
        regimes[psi >= 0.15] = 2
        regimes[(psi >= 0.0) & (psi < 0.15)] = 1
        regimes[psi < 0.0] = 0
        
        cmap_phase = LinearSegmentedColormap.from_list("phase", ["#fca5a5", "#fde047", "#86efac"], N=3)
        ax.contourf(Q, W, regimes, levels=[-0.5, 0.5, 1.5, 2.5], cmap=cmap_phase, alpha=0.85)
        ax.contour(Q, W, psi, levels=[0.0, 0.15], colors=["#dc2626", "#16a34a"], linewidths=2.0)
        
        ax.set_title(label, fontweight="bold", pad=10)
        ax.set_xlabel("화재 규모 $\\dot{Q}_{HRR}$ [kW]", fontweight="bold")
        if idx == 0:
            ax.set_ylabel("주변 풍속 $U_{wind}$ [m/s]", fontweight="bold")
        ax.grid(True, linestyle=":", color="#334155", alpha=0.4)
        ax.text(20, 1.5, "확실 진압 영역\n(Feasible)", color="#14532d", fontweight="bold", ha="center", fontsize=9.5)
        ax.text(50, 4.5, "진압 실패 영역\n(Failure)", color="#7f1d1d", fontweight="bold", ha="center", fontsize=9.5)
        
    fig.suptitle("화재 규모 · 풍속 · 이격 거리에 따른 진압 가능/실패 영역 Phase Map (소화출력 50W 기준)", y=0.98, fontweight="bold")
    plt.tight_layout()
    p = OUT_DIR / "vis_09_suppression_phase_map.png"
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    print(f"   -> Saved: {p}")

if __name__ == "__main__":
    generate()
