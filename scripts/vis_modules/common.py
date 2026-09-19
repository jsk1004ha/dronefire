import pathlib
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = ["Malgun Gothic", "Gulim", "DejaVu Sans", "Arial"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.size"] = 10
plt.rcParams["axes.labelsize"] = 11
plt.rcParams["axes.titlesize"] = 12
plt.rcParams["xtick.labelsize"] = 9
plt.rcParams["ytick.labelsize"] = 9
plt.rcParams["legend.fontsize"] = 9
plt.rcParams["figure.titlesize"] = 14

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "reports" / "visualizations"
OUT_DIR.mkdir(parents=True, exist_ok=True)

COLORS = {
    "M1": "#0284c7",  # Sky Blue
    "M2": "#4f46e5",  # Indigo
    "M3": "#0d9488",  # Teal
    "M4": "#d97706",  # Amber
    "M5": "#7c3aed",  # Violet
    "C0": "#64748b",  # Slate Gray
    "ctrl": "#059669", # Emerald
    "unctrl": "#ea580c" # Orange-Red
}

METHOD_LABELS = {
    "M1": "M1 (음향 정재파)",
    "M2": "M2 (공기 와류륜)",
    "M3": "M3 (미세 수분무)",
    "M4": "M4 (건식 에어로졸)",
    "M5": "M5 (전도성 EHD 와류)"
}
