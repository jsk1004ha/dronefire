import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from .common import OUT_DIR

def generate():
    print("[10/10] Generating vis_10_operational_envelope_3d_surface.png ...")
    d = np.linspace(0.5, 3.0, 50)
    w = np.linspace(0.0, 5.0, 50)
    D, W = np.meshgrid(d, w)
    
    S_flight = np.exp(-0.25 * W) * (1.0 - np.exp(-3.0 * (D - 0.4)))
    S_ext = np.exp(-0.45 * (D - 0.5) - 0.18 * (W * D / 8.0)**2)
    S_energy = 0.95 - 0.08 * W - 0.05 * D
    
    Phi = 0.40 * S_flight + 0.40 * S_ext + 0.20 * S_energy
    Phi = np.clip(Phi, 0.0, 1.0)
    
    fig = plt.figure(figsize=(12, 8.5), dpi=300)
    ax = fig.add_subplot(1, 1, 1, projection="3d")
    
    surf = ax.plot_surface(D, W, Phi, cmap="plasma", edgecolor="none", alpha=0.88, antialiased=True)
    ax.contour(D, W, Phi, zdir="z", offset=-0.1, cmap="plasma", linewidths=1.5)
    
    max_idx = np.unravel_index(np.argmax(Phi), Phi.shape)
    opt_d = D[max_idx]
    opt_w = W[max_idx]
    opt_phi = Phi[max_idx]
    
    ax.scatter([opt_d], [opt_w], [opt_phi], color="#22c55e", s=180, edgecolor="#ffffff", lw=2.0, label=f"최적 운용점 (d={opt_d:.2f} m, W={opt_w:.1f} m/s, Φ={opt_phi:.2f})")
    
    ax.set_title("비행 안정성 · 소화 효율 · 에너지 마진 통합 드론 운용 가능 영역 3D Surface", pad=20, fontweight="bold")
    ax.set_xlabel("화염과의 이격 거리 $d$ [m]", labelpad=12, fontweight="bold")
    ax.set_ylabel("주변 횡풍 $U_{wind}$ [m/s]", labelpad=12, fontweight="bold")
    ax.set_zlabel("통합 운용 적합도 지수 $\\Phi$ (0~1.0)", labelpad=12, fontweight="bold")
    ax.set_zlim(-0.1, 1.0)
    
    cbar = fig.colorbar(surf, ax=ax, shrink=0.55, aspect=10, pad=0.08)
    cbar.set_label("통합 운용 적합도 지수 $\\Phi$", fontweight="bold")
    ax.legend(loc="upper right", framealpha=0.92)
    ax.view_init(elev=28, azim=-50)
    
    plt.tight_layout()
    p = OUT_DIR / "vis_10_operational_envelope_3d_surface.png"
    fig.savefig(p)
    plt.close(fig)
    print(f"   -> Saved: {p}")

if __name__ == "__main__":
    generate()
