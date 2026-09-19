import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from .common import OUT_DIR

def generate():
    print("[7/10] Generating vis_07_synergy_matrix_heatmap.png ...")
    labels = ["M1: 음향", "M2: 와류륜", "M3: 수분무", "M4: 에어로졸", "M5: 전도성EHD"]
    
    matrix = np.array([
        [0.40, 1.15, 1.32, 1.45, 1.20],
        [1.10, 0.65, 1.58, 1.40, 1.35],
        [1.25, 1.50, 0.85, 1.62, 1.48],
        [1.35, 1.30, 1.55, 0.92, 1.42],
        [1.15, 1.28, 1.42, 1.38, 0.88],
    ])
    
    annotations = [
        ["단독 40%", "음향+와류\n기류집속", "음향+수분무\n미세액적확산", "음향+분말\n정재파전단", "음향+EHD\n전계유도"],
        ["와류→음향\n순차교란", "단독 65%", "와류+수분무\n초장거리수송", "와류+분말\n코어관통도달", "와류+EHD\n이온풍가속"],
        ["수분무→음향\n냉각후질식", "수분무→와류\n증발후차단", "단독 85%", "수분무+분말\n냉각·라디칼", "수분무+EHD\n하전액적가속"],
        ["분말→음향\n화염억제", "분말→와류\n미분밀봉", "분말→수분무\n흡열화학결합", "단독 92%", "분말+EHD\n정전부착"],
        ["EHD→음향\n이온화", "EHD→와류\n와류안정화", "EHD→수분무\n정전분무", "EHD→분말\n하전침적", "단독 88%"],
    ]
    
    fig, ax = plt.subplots(figsize=(10.5, 9.0), dpi=300)
    cmap = sns.diverging_palette(220, 20, as_cmap=True)
    sns.heatmap(
        matrix,
        annot=np.array(annotations),
        fmt="",
        cmap=cmap,
        vmin=0.3,
        vmax=1.7,
        center=1.0,
        cbar_kws={"label": "상호보완 시너지 지수 $S_{synergy}$ (> 1.0: 시너지 상승, 1.0: 단순합산)"},
        xticklabels=labels,
        yticklabels=labels,
        ax=ax,
        linewidths=1.0,
        linecolor="#ffffff"
    )
    
    fig.suptitle("5대 소화 방식의 단독 · 복합(동시 SIM / 순차 SEQ) 운용 상호보완성 Matrix Heatmap", y=0.97, fontweight="bold", fontsize=13)
    ax.set_title("■ 대각선: 단독 운용 효율   |   ■ 상삼각: 동시 분사 (SIM)   |   ■ 하삼각: 순차 분사 (SEQ)", pad=14, fontsize=10, fontweight="bold", color="#334155")
            
    fig.subplots_adjust(top=0.90, bottom=0.08, left=0.12, right=0.98)
    p = OUT_DIR / "vis_07_synergy_matrix_heatmap.png"
    fig.savefig(p)
    plt.close(fig)
    print(f"   -> Saved: {p}")

if __name__ == "__main__":
    generate()
