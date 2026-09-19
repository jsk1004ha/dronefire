import numpy as np
import matplotlib.pyplot as plt
from .common import OUT_DIR, COLORS, METHOD_LABELS

def generate():
    print("[6/10] Generating vis_06_normalized_radar_and_bars.png ...")
    categories = ["소화 신속성\n(1/Time)", "HRR 감소율\n(HRR Drop %)", "에너지 효율\n(1/Power)", "약제 경량성\n(1/Consumable)", "기체 탑재성\n(1/Device Mass)"]
    N = len(categories)
    
    scores = {
        "M1": [0.45, 0.40, 0.20, 1.00, 0.85],
        "M2": [0.65, 0.65, 0.85, 1.00, 0.75],
        "M3": [0.80, 0.85, 0.55, 0.45, 0.65],
        "M4": [1.00, 0.95, 0.95, 0.60, 0.90],
        "M5": [0.90, 0.90, 0.70, 0.80, 0.55],
    }
    
    fig = plt.figure(figsize=(15.5, 7.5), dpi=300)
    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    angles += angles[:1]
    
    ax1 = fig.add_subplot(1, 2, 1, polar=True)
    ax1.set_theta_offset(np.pi / 2)
    ax1.set_theta_direction(-1)
    
    plt.xticks(angles[:-1], categories, size=9.5, fontweight="bold")
    ax1.set_rlabel_position(0)
    plt.yticks([0.2, 0.4, 0.6, 0.8, 1.0], ["0.2", "0.4", "0.6", "0.8", "1.0"], color="#64748b", size=8)
    plt.ylim(0, 1.05)
    
    for m in ["M1", "M2", "M3", "M4", "M5"]:
        vals = scores[m] + scores[m][:1]
        ax1.plot(angles, vals, lw=2.0, color=COLORS[m], label=METHOD_LABELS[m])
        ax1.fill(angles, vals, color=COLORS[m], alpha=0.12)
        
    ax1.set_title("(a) 5대 소화 방식 성능 다면 평가 (정규화 Radar Chart)", pad=22, fontweight="bold")
    ax1.legend(loc="upper right", bbox_to_anchor=(0.1, 1.15), framealpha=0.92)
    
    ax2 = fig.add_subplot(1, 2, 2)
    y_pos = np.arange(len(categories))
    bar_height = 0.15
    
    for idx, m in enumerate(["M1", "M2", "M3", "M4", "M5"]):
        ax2.barh(y_pos + idx * bar_height, scores[m], height=bar_height,
                 label=METHOD_LABELS[m], color=COLORS[m], alpha=0.88)
        
    ax2.set_yticks(y_pos + 2 * bar_height)
    ax2.set_yticklabels([c.replace("\n", " ") for c in categories], fontweight="bold")
    ax2.set_xlabel("정규화 지수 (1.0 = 최우수)", fontweight="bold")
    ax2.set_title("(b) 지표별 정규화 비교 바 차트", pad=15, fontweight="bold")
    ax2.set_xlim(0, 1.15)
    ax2.grid(True, linestyle="--", alpha=0.5, color="#cbd5e1")
    ax2.legend(loc="lower right", framealpha=0.92)
    
    plt.tight_layout()
    p = OUT_DIR / "vis_06_normalized_radar_and_bars.png"
    fig.savefig(p)
    plt.close(fig)
    print(f"   -> Saved: {p}")

if __name__ == "__main__":
    generate()
