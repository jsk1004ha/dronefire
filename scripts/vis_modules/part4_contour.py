import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from .common import OUT_DIR

def generate():
    print("[4/10] Generating vis_04_distance_wind_power_contour.png ...")
    dists = np.linspace(0.5, 3.0, 100)
    winds = np.linspace(0.0, 5.0, 100)
    D, W = np.meshgrid(dists, winds)
    U_jet = 8.0
    
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.2), sharey=True, dpi=300)
    power_levels = [20.0, 50.0, 100.0]
    power_labels = ["Low Power (20 W)", "Medium Power (50 W)", "High Power (100 W)"]
    levels = np.linspace(0, 100, 21)
    
    for idx, (P, label) in enumerate(zip(power_levels, power_labels)):
        ax = axes[idx]
        P_factor = (P / 50.0)**0.32
        efficiency = P_factor * np.exp(-0.42 * (D - 0.5) - 0.15 * (W * D / U_jet)**2) * 100.0
        efficiency = np.clip(efficiency, 0.0, 100.0)
        
        cs = ax.contourf(D, W, efficiency, levels=levels, cmap="viridis", extend="both")
        lines = ax.contour(D, W, efficiency, levels=[30, 50, 70, 85], colors=["#ffffff", "#fef08a", "#86efac", "#38bdf8"], linewidths=1.5)
        ax.clabel(lines, inline=True, fmt="%1.0f%%", fontsize=8.5)
        
        if idx == 1:
            rect = Rectangle((0.8, 0.0), 0.7, 2.0, fill=False, edgecolor="#ef4444", lw=2.2, linestyle="--")
            ax.add_patch(rect)
            ax.text(1.15, 1.0, "최적 운용 윈도우\n(Sweet Spot)", color="#ffffff", fontweight="bold",
                    ha="center", va="center", bbox=dict(boxstyle="round,pad=0.3", facecolor="#dc2626", alpha=0.85))
                    
        ax.set_title(f"{label}", fontweight="bold", pad=10)
        ax.set_xlabel("화염과의 이격 거리 $d$ [m]", fontweight="bold")
        if idx == 0:
            ax.set_ylabel("주변 횡풍 풍속 $U_{wind}$ [m/s]", fontweight="bold")
        ax.grid(True, linestyle=":", alpha=0.6, color="#ffffff")
        
    cbar = fig.colorbar(cs, ax=axes, orientation="horizontal", fraction=0.06, pad=0.18)
    cbar.set_label("소화 효율 지수 $\\eta_{ext}$ [%] (Suppression Delivery Efficiency)", fontweight="bold")
    fig.suptitle("거리 · 횡풍 · 소화장비 출력에 따른 소화 효율 Contour Map", y=0.98, fontweight="bold")
    
    p = OUT_DIR / "vis_04_distance_wind_power_contour.png"
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    print(f"   -> Saved: {p}")

if __name__ == "__main__":
    generate()
