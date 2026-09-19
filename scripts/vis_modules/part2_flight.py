import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from .common import ROOT, OUT_DIR, COLORS, METHOD_LABELS
from firelab.config import validate_config
from firelab.physics import simulate_method

def generate():
    print("[2/10] Generating vis_02_flight_dynamics_timeseries.png ...")
    series_path = ROOT / "runs" / "study_20260919T132411_7c18048d" / "drone_mission_series.csv"
    if not series_path.is_file():
        found = list((ROOT / "runs").glob("study_*/drone_mission_series.csv"))
        if found:
            series_path = found[-1]
            
    df = pd.read_csv(series_path)
    df_d4 = df[df["condition_id"] == "D4"]
    
    fig, axes = plt.subplots(4, 1, figsize=(12, 11), sharex=True, dpi=300)
    methods = ["M1", "M2", "M3", "M4", "M5"]
    
    for m in methods:
        sub = df_d4[df_d4["method_id"] == m].sort_values("time_s")
        t = sub["time_s"].values
        axes[0].plot(t, sub["target_error_m"].values, label=METHOD_LABELS[m], color=COLORS[m], lw=1.8)
        tilt = np.sqrt(sub["roll_deg"]**2 + sub["pitch_deg"]**2).values
        axes[1].plot(t, tilt, label=METHOD_LABELS[m], color=COLORS[m], lw=1.8)
        axes[3].plot(t, sub["power_W"].values, label=METHOD_LABELS[m], color=COLORS[m], lw=1.8)
        
    cfg = validate_config({})
    t_span = np.linspace(0, 34, 341)
    for m in methods:
        phys = simulate_method(cfg, m)
        f_vec = np.array(phys.get("reaction_force_N", [0., 0., 0.]))
        f_mag = float(np.linalg.norm(f_vec))
        f_series = np.zeros_like(t_span)
        active = (t_span >= 15.0) & (t_span <= 19.0)
        f_series[active] = f_mag
        axes[2].plot(t_span, f_series, label=METHOD_LABELS[m], color=COLORS[m], lw=1.8)

    for ax in axes:
        ax.axvspan(15.0, 19.0, color="#fef3c7", alpha=0.6, label="소화 약제 방출 구간 (15s~19s)" if ax == axes[0] else "")
        ax.grid(True, linestyle="--", alpha=0.5, color="#cbd5e1")
        ax.set_xlim(0, 34)
        
    # Set generous y-limits so no data ever touches borders or annotations
    axes[0].set_ylim(-0.0003, 0.0075)
    axes[1].set_ylim(-0.02, 0.65)
    axes[2].set_ylim(-0.03, 0.70)
    axes[3].set_ylim(0, 440)
        
    axes[0].set_ylabel("위치 추종 오차 [m]\n(Position Error)", fontweight="bold")
    axes[1].set_ylabel("기체 틸트각 [deg]\n(Attitude Tilt)", fontweight="bold")
    axes[2].set_ylabel("반력 크기 [N]\n(Reaction Force)", fontweight="bold")
    axes[3].set_ylabel("소비 전력 [W]\n(Power Demand)", fontweight="bold")
    axes[3].set_xlabel("비행 시간 $t$ [s] (0~15s: 정밀접근, 15~19s: 소화분사, 19~34s: 기지복귀)", fontweight="bold")
    
    fig.suptitle("소화 방식별 드론 6-DOF 비행 동역학 및 제어 시계열 비교 (D4 능동제어)", y=0.98, fontweight="bold", fontsize=13)
    
    # Unified top legend placed outside all subplots to prevent any occlusion
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.945), ncol=6,
               frameon=True, facecolor="#ffffff", edgecolor="#cbd5e1", fontsize=9.5)
    
    fig.subplots_adjust(top=0.88, bottom=0.07, left=0.09, right=0.97, hspace=0.18)
    p = OUT_DIR / "vis_02_flight_dynamics_timeseries.png"
    fig.savefig(p)
    plt.close(fig)
    print(f"   -> Saved: {p}")

if __name__ == "__main__":
    generate()

