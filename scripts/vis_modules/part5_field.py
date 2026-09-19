import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from .common import OUT_DIR

def generate():
    print("[5/10] Generating vis_05_flow_and_thermal_field_2d3d.png ...")
    x = np.linspace(-0.5, 2.5, 120)
    z = np.linspace(0.0, 3.0, 100)
    X, Z = np.meshgrid(x, z)
    
    # 2D Field equations
    v_rotor_z = -7.4 * np.exp(-((X - 0.0) / 0.4)**2) * (1.0 + np.tanh((2.0 - Z) / 0.5)) * (Z <= 2.1)
    v_rotor_x = 0.5 * np.sign(X) * np.exp(-((X - 0.0) / 0.5)**2) * (Z <= 0.8)
    w_plume = 3.5 * np.exp(-((X - 1.5) / 0.28)**2) * (Z >= 0.0) * (1.0 - np.exp(-Z / 0.3))
    
    dx = 1.3
    dz = -1.5
    dist_jet = np.sqrt(dx**2 + dz**2)
    dir_x, dir_z = dx / dist_jet, dz / dist_jet
    
    jet_spread = 0.08 + 0.15 * (X - 0.2)
    jet_active = (X >= 0.2) & (X <= 1.8)
    u_jet_x = 8.0 * dir_x * np.exp(-((Z - (1.8 + dir_z/dir_x * (X - 0.2))) / jet_spread)**2) * jet_active
    u_jet_z = 8.0 * dir_z * np.exp(-((Z - (1.8 + dir_z/dir_x * (X - 0.2))) / jet_spread)**2) * jet_active
    
    U = v_rotor_x + u_jet_x + 0.4
    W = v_rotor_z + w_plume + u_jet_z
    
    T = 20.0 + 650.0 * np.exp(-((X - 1.5) / 0.25)**2 - (Z / 0.6)**2) * np.exp(-0.25 * Z)
    cooling = 0.75 * np.exp(-((X - 1.4) / 0.3)**2 - ((Z - 0.35) / 0.3)**2)
    T = T * (1.0 - cooling)
    
    fig = plt.figure(figsize=(15, 7.5), dpi=300)
    
    # 2D Panel
    ax1 = fig.add_subplot(1, 2, 1)
    tc = ax1.contourf(X, Z, T, levels=np.linspace(20, 650, 20), cmap="inferno", alpha=0.85)
    cbar1 = plt.colorbar(tc, ax=ax1, fraction=0.046, pad=0.04)
    cbar1.set_label("국소 온도장 $T(x,z)$ [°C]", fontweight="bold")
    ax1.streamplot(X, Z, U, W, color="#ffffff", density=1.4, linewidth=0.9, arrowsize=1.1)
    
    z_flame = np.linspace(0, 1.8, 50)
    x_flame = 1.5 + 0.35 * (z_flame / 1.5)**1.6
    ax1.plot(x_flame, z_flame, color="#facc15", lw=3.0, ls="--", label="화염 중심선 편향 궤적")
    
    ax1.plot([-0.25, 0.25], [2.0, 2.0], color="#38bdf8", lw=4.5)
    ax1.plot([-0.25, -0.25], [2.0, 2.08], color="#38bdf8", lw=2.5)
    ax1.plot([0.25, 0.25], [2.0, 2.08], color="#38bdf8", lw=2.5)
    ax1.text(0.0, 2.18, "드론 기체 (z=2.0m)", color="#38bdf8", fontweight="bold", ha="center", fontsize=9.5)
    ax1.plot(0.2, 1.8, marker=">", color="#38bdf8", markersize=10)
    ax1.plot([1.3, 1.7], [0.0, 0.0], color="#dc2626", lw=5.0)
    ax1.text(1.5, -0.15, "화원 버너 (x=1.5m)", color="#dc2626", fontweight="bold", ha="center", fontsize=9.5)
    
    ax1.set_title("(a) 2D 단면 상호작용 속도장 · 온도장 및 화염 편향", pad=12, fontweight="bold")
    ax1.set_xlabel("수평 거리 $x$ [m]", fontweight="bold")
    ax1.set_ylabel("수직 고도 $z$ [m]", fontweight="bold")
    ax1.set_xlim(-0.4, 2.3)
    ax1.set_ylim(-0.1, 2.6)
    ax1.legend(loc="upper right", framealpha=0.9)
    
    # 3D Panel
    ax2 = fig.add_subplot(1, 2, 2, projection="3d")
    X3, Y3 = np.meshgrid(np.linspace(1.2, 1.8, 18), np.linspace(-0.3, 0.3, 18))
    Z3 = 1.2 * np.exp(-((X3 - 1.5)/0.25)**2 - (Y3/0.25)**2)
    ax2.plot_surface(X3, Y3, Z3, cmap="inferno", alpha=0.75, rstride=1, cstride=1)
    
    ax2.scatter([0.0], [0.0], [2.0], color="#0284c7", s=120, label="소화 드론 위치")
    for rx, ry in [(-0.25, -0.25), (-0.25, 0.25), (0.25, -0.25), (0.25, 0.25)]:
        theta = np.linspace(0, 2*np.pi, 20)
        ax2.plot(rx + 0.12*np.cos(theta), ry + 0.12*np.sin(theta), 2.0, color="#38bdf8", lw=1.5)
        ax2.quiver(rx, ry, 2.0, 0, 0, -0.6, color="#38bdf8", arrow_length_ratio=0.3, lw=1.5)
        
    s_t = np.linspace(0, 1, 20)
    jet_x = 0.2 + 1.2 * s_t
    jet_y = 0.0 + 0.0 * s_t
    jet_z = 1.8 - 1.4 * s_t
    ax2.plot(jet_x, jet_y, jet_z, color="#0d9488", lw=3.2, label="소화 제트 궤적")
    ax2.scatter([1.5], [0.0], [0.0], color="#dc2626", s=150, marker="s", label="화원 중심")
    
    ax2.set_title("(b) 3D 입체 하향류 · 열플룸 · 소화 제트 상호작용", pad=12, fontweight="bold")
    ax2.set_xlabel("X [m]", fontweight="bold")
    ax2.set_ylabel("Y [m]", fontweight="bold")
    ax2.set_zlabel("Z [m]", fontweight="bold")
    ax2.set_xlim(-0.2, 2.0)
    ax2.set_ylim(-0.8, 0.8)
    ax2.set_zlim(0.0, 2.3)
    ax2.legend(loc="upper left", framealpha=0.85)
    ax2.view_init(elev=26, azim=-55)
    
    plt.tight_layout()
    p = OUT_DIR / "vis_05_flow_and_thermal_field_2d3d.png"
    fig.savefig(p)
    plt.close(fig)
    print(f"   -> Saved: {p}")

if __name__ == "__main__":
    generate()
