"""Package all research deliverables into firefield_research_results.zip with UTF-8 encoding."""
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_ZIP = ROOT / "firefield_research_results.zip"

def build_zip():
    print(f"Packaging research deliverables to {OUT_ZIP} ...")
    
    # 1. Identify source run directory with CSVs and summaries
    campaign_ptr = ROOT / "runs" / "campaign_latest.json"
    if not campaign_ptr.exists():
        raise FileNotFoundError("runs/campaign_latest.json not found")
    cid = json.loads(campaign_ptr.read_text(encoding="utf-8"))["campaign_id"]
    run_dir = ROOT / "runs" / cid
    
    # Files mapping: (source_path, zip_internal_path)
    entries = []
    
    # Root README
    readme_path = run_dir / "README.md"
    if readme_path.exists():
        entries.append((readme_path, "README.md"))
    elif (ROOT / "README.md").exists():
        entries.append((ROOT / "README.md", "README.md"))
        
    # 01_보고서_요약
    for ext in (".md", ".html"):
        for name in ("종합_결과_보고서", "단독_소화방식_요약", "화재진압_연구_총괄보고서"):
            p = run_dir / f"{name}{ext}"
            if p.exists():
                entries.append((p, f"01_보고서_요약/{name}{ext}"))
        for p in run_dir.glob(f"*{ext}"):
            if any(k in p.name for k in ["보고서", "요약", "method", "drone"]):
                rel_name = f"01_보고서_요약/{p.name}"
                if (p, rel_name) not in entries:
                    entries.append((p, rel_name))
                    
    # 02_시각화_그래프
    # Existing legacy plots
    for p in run_dir.glob("*.png"):
        entries.append((p, f"02_시각화_그래프/{p.name}"))
        
    # All 10 newly generated high-res visual plots
    vis_dir = ROOT / "reports" / "visualizations"
    if vis_dir.exists():
        for p in sorted(vis_dir.glob("*.png")):
            entries.append((p, f"02_시각화_그래프/{p.name}"))
            
    # 03_수치_CSV
    for p in sorted(run_dir.glob("*.csv")):
        if "mission" not in p.name.lower():
            entries.append((p, f"03_수치_CSV/{p.name}"))
            
    # 04_수치해석_검증
    for p in (ROOT / "reports" / "verification").glob("*.json"):
        entries.append((p, f"04_수치해석_검증/{p.name}"))
    for p in (ROOT / "reports" / "acoustics").glob("*.json"):
        entries.append((p, f"04_수치해석_검증/{p.name}"))
    for p in (ROOT / "reports").glob("openfoam*.json"):
        entries.append((p, f"04_수치해석_검증/{p.name}"))
    for p in (ROOT / "runs" / "openfoam_v2412_taylor_green_spatial").glob("convergence.*"):
        entries.append((p, f"04_수치해석_검증/openfoam_v2412_{p.name}"))
    if (run_dir / "campaign.json").exists():
        entries.append((run_dir / "campaign.json", "04_수치해석_검증/study_result_summary.json"))

    # 05_원시계열_데이터
    for p in sorted(run_dir.glob("*mission*.csv")):
        entries.append((p, f"05_원시계열_데이터/{p.name}"))
    if (run_dir / "config.json").exists():
        entries.append((run_dir / "config.json", "05_원시계열_데이터/config.json"))
    if (ROOT / "configs").exists():
        for p in (ROOT / "configs").glob("*.json"):
            entries.append((p, f"05_원시계열_데이터/{p.name}"))
            
    # De-duplicate entries by zip path
    seen = set()
    final_entries = []
    for src, zpath in entries:
        if zpath not in seen and src.exists():
            seen.add(zpath)
            final_entries.append((src, zpath))
            
    # Write to ZIP with utf-8 flag
    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for src, zpath in sorted(final_entries, key=lambda x: x[1]):
            zinfo = zipfile.ZipInfo(zpath)
            zinfo.flag_bits |= 0x800  # UTF-8 filename flag
            zinfo.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zinfo, src.read_bytes())
            print(f"  + {zpath} ({src.stat().st_size / 1024:.1f} KB)")
            
    print(f"\nSuccessfully created {OUT_ZIP} ({OUT_ZIP.stat().st_size / 1024 / 1024:.2f} MB)")
    print(f"Total files: {len(final_entries)}")

if __name__ == "__main__":
    build_zip()
