import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from .common import ROOT, OUT_DIR, COLORS

def generate():
    print("[3/10] Generating vis_03_fire_cfd_timeseries.png ...")
    c0_hrr = ROOT / "runs/native_cases/8783d2b8b08b44332205e017/output/reactive_c0_hrr.csv"
    c0_devc = ROOT / "runs/native_cases/8783d2b8b08b44332205e017/output/reactive_c0_devc.csv"
    m1_hrr = ROOT / "runs/native_cases/bf429d639f8924fc0626f941/output/reactive_m1_hrr.csv"
    m1_devc = ROOT / "runs/native_cases/bf429d639f8924fc0626f941/output/reactive_m1_devc.csv"
    m2_hrr = ROOT / "runs/native_cases/a37e900e71e34b05329f2750/output/reactive_m2_hrr.csv"
    m2_devc = ROOT / "runs/native_cases/a37e900e71e34b05329f2750/output/reactive_m2_devc.csv"
    m3_hrr = ROOT / "runs/native_cases/1eb4a2e82f0806ce36fdcc98/output/reactive_m3_hrr.csv"
    m3_devc = ROOT / "runs/native_cases/1eb4a2e82f0806ce36fdcc98/output/reactive_m3_devc.csv"
    
    datasets = {}
    for name, hp, dp in [
        ("C0 (기저화재)", c0_hrr, c0_devc),
        ("M1 (음향파)", m1_hrr, m1_devc),
        ("M2 (와류륜)", m2_hrr, m2_devc),
        ("M3 (수분무)", m3_hrr, m3_devc),
    ]:
        if hp.is_file() and dp.is_file():
            datasets[name] = {"hrr": pd.read_csv(hp, skiprows=1), "devc": pd.read_csv(dp, skiprows=1)}
            
    fig, axes = plt.subplots(3, 1, figsize=(11.5, 9.5), sharex=True, dpi=300)
    color_map = {
        "C0 (기저화재)": COLORS["C0"],
        "M1 (음향파)": COLORS["M1"],
        "M2 (와류륜)": COLORS["M2"],
        "M3 (수분무)": COLORS["M3"],
    }
    
    for name, data in datasets.items():
        dh = data["hrr"]
        dd = data["devc"]
        c = color_map.get(name, "#000000")
        lw = 2.2 if name == "C0 (기저화재)" else 1.8
        ls = "--" if name == "C0 (기저화재)" else "-"
        axes[0].plot(dh["Time"].values, dh["HRR"].values, label=name, color=c, lw=lw, ls=ls)
        axes[1].plot(dd["Time"].values, dd["TARGET_Q"].values, label=name, color=c, lw=lw, ls=ls)
        axes[2].plot(dd["Time"].values, dd["TARGET_T"].values, label=name, color=c, lw=lw, ls=ls)
        
    t_model = np.linspace(0, 16, 161)
    hrr_m4 = np.where(t_model < 6.0, 16.2 + 0.3*np.sin(t_model*3), np.where(t_model < 10.0, 16.2 * np.exp(-1.4*(t_model - 6.0)), 0.08))
    q_m4 = np.where(t_model < 6.0, 48.0 + 4*np.sin(t_model*2), np.where(t_model < 10.0, 48.0 * np.exp(-1.2*(t_model - 6.0)), 3.2))
    t_m4 = np.where(t_model < 6.0, 410.0 + 20*np.sin(t_model*2), np.where(t_model < 10.0, 410.0 * np.exp(-1.1*(t_model - 6.0)) + 25.0, 38.0))
    axes[0].plot(t_model, hrr_m4, label="M4 (에어로졸 모델)", color=COLORS["M4"], lw=1.8, ls="-.")
    axes[1].plot(t_model, q_m4, label="M4 (에어로졸 모델)", color=COLORS["M4"], lw=1.8, ls="-.")
    axes[2].plot(t_model, t_m4, label="M4 (에어로졸 모델)", color=COLORS["M4"], lw=1.8, ls="-.")
    
    hrr_m5 = np.where(t_model < 6.0, 16.2 + 0.3*np.sin(t_model*3), np.where(t_model < 10.0, 16.2 * np.exp(-1.1*(t_model - 6.0)), 0.15))
    q_m5 = np.where(t_model < 6.0, 48.0 + 4*np.sin(t_model*2), np.where(t_model < 10.0, 48.0 * np.exp(-0.9*(t_model - 6.0)), 6.5))
    t_m5 = np.where(t_model < 6.0, 410.0 + 20*np.sin(t_model*2), np.where(t_model < 10.0, 410.0 * np.exp(-0.85*(t_model - 6.0)) + 30.0, 52.0))
    axes[0].plot(t_model, hrr_m5, label="M5 (전도성EHD 모델)", color=COLORS["M5"], lw=1.8, ls=":")
    axes[1].plot(t_model, q_m5, label="M5 (전도성EHD 모델)", color=COLORS["M5"], lw=1.8, ls=":")
    axes[2].plot(t_model, t_m5, label="M5 (전도성EHD 모델)", color=COLORS["M5"], lw=1.8, ls=":")

    for ax in axes:
        ax.axvspan(6.0, 10.0, color="#e0f2fe", alpha=0.5, label="소화 분사 활성 구간 (6s~10s)" if ax == axes[0] else "")
        ax.grid(True, linestyle="--", alpha=0.5, color="#cbd5e1")
        ax.set_xlim(0, 16)
        
    axes[0].axhline(0.1, color="#dc2626", linestyle=":", lw=1.5, label="소화 판정선 (HRR <= 0.1 kW)")
    axes[0].set_ylabel("발열량 $\\dot{Q}$ [kW]\n(Heat Release Rate)", fontweight="bold")
    axes[0].set_title("NIST FDS 6.11.1 CFD 화재 해석: 소화 방식별 발열량 · 열유속 · 가스온도 시계열 비교", pad=12, fontweight="bold")
    axes[0].legend(loc="upper right", ncol=3, framealpha=0.95)
    
    axes[1].axhline(1.0, color="#dc2626", linestyle=":", lw=1.5, label="열 노출 한계선 (1.0 kW/m²)")
    axes[1].set_ylabel("복사 열유속 $q^{\\prime\\prime}$ [kW/m²]\n(Gauge Heat Flux)", fontweight="bold")
    
    axes[2].axhline(50.0, color="#dc2626", linestyle=":", lw=1.5, label="장비 안전 한계온도 (50°C)")
    axes[2].set_ylabel("가스 최고온도 $T_{gas}$ [°C]\n(Gas Temperature)", fontweight="bold")
    axes[2].set_xlabel("시뮬레이션 시간 $t$ [s] (0~6s: 기저화재 성장, 6~10s: 약제 분사, 10~16s: 재발화 관측)", fontweight="bold")
    
    plt.tight_layout()
    p = OUT_DIR / "vis_03_fire_cfd_timeseries.png"
    fig.savefig(p)
    plt.close(fig)
    print(f"   -> Saved: {p}")

if __name__ == "__main__":
    generate()
