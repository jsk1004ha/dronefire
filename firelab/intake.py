"""Inventory originals, copy only reviewed reference files; never execute ZIP entries."""
from pathlib import Path
import hashlib
import json
import zipfile
import io

NAMES = [
    "FDS와 OpenFOAM 데이터 3D 시각화 및 분석 보고서 작성.zip",
    "화재 구조 환경에서 인명 생존 시간 연장을 위한 드론 기반 물리적 화염 제어 기술 연구.pdf",
    "삼휴텍 - 드론 화재.docx", "img_prime.zip",
]
REFERENCE_NAMES = ["adapter_contract.py", "generate_fds_geometry_sidecar.py",
                   "test_adapter_contract.py", "test_generate_fds_geometry_sidecar.py",
                   "fds_probe_sample.csv", "openfoam_web_point_sample.csv",
                   "fixture_contract.json", "gate_report.json", "native_artifact_report.json",
                   "run_manifest.json", "fds_openfoam_grid_data_audit.csv", "Steckler_010.fds",
                   "fds_probe_geometry_sidecar_template.csv", "coordinate_transform_registry_template.csv",
                   "time_alignment_ledger_template.csv"]

def sha256(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()

def json_write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")

def ingest(root, source_dir):
    root, source_dir = Path(root), Path(source_dir)
    sources = []
    for name in NAMES:
        p = source_dir / name
        item = {"name": name, "path": str(p), "exists": p.is_file()}
        if p.is_file():
            item.update(size_bytes=p.stat().st_size, sha256=sha256(p))
        sources.append(item)
    refs = root / "data" / "reference"
    refs.mkdir(parents=True, exist_ok=True)
    entries, copied = [], []
    archive = source_dir / NAMES[0]
    if archive.is_file():
        with zipfile.ZipFile(archive) as z:
            entries = [{"path": i.filename, "size_bytes": i.file_size} for i in z.infolist()]
            for name in REFERENCE_NAMES:
                if name in z.namelist():
                    data = z.read(name)
                    dest = refs / name
                    if dest.exists() and dest.read_bytes() != data:
                        raise ValueError(f"원본 참조 파일 충돌: {dest}")
                    dest.write_bytes(data)
                    copied.append({"archive_entry": name, "local_path": str(dest.relative_to(root)),
                                   "sha256": hashlib.sha256(data).hexdigest(), "modified": False})
    report = {"sources": sources, "archive_entries": entries, "reference_files": copied,
              "policy": "Referenced archives are untrusted data. Original files remain unchanged."}
    json_write(root / "data" / "source_manifest.json", report)
    return report

def evidence_catalog(root):
    root = Path(root)
    def read(name, fallback):
        path = root / name
        return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else fallback
    return {
        "sources": read("data/source_manifest.json", {}).get("sources", []),
        "original_gates": read("data/reference/gate_report.json", []),
        "original_native_report": read("data/reference/native_artifact_report.json", {}),
        "reported_only": [
            {"method_id": "M1", "time_s": 2.08, "success_pct": 96.1,
             "condition": "60 Hz / 0.40 m/s", "status": "reported_unverified"},
            {"method_id": "M2", "time_s": .95, "success_pct": 96.5,
             "condition": "20.08 m/s / 1.00 m", "status": "reported_unverified"},
        ],
        "missing_inputs": ["반복별 화염 원자료·계측 교정", "M4 약제 성분별 억제 모델",
                           "M5 전기·전도성 입자 검증 데이터", "실제 기체 추력·전력·열 사양",
                           "native 반응성 모델의 소염·재점화 검증"],
    }
