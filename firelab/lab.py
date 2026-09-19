"""Reproducible local study orchestration and export."""
from pathlib import Path
from datetime import datetime, timezone
from copy import deepcopy
import csv
import hashlib
import io
import json
import uuid
import zipfile
import html
import platform
import sys

from .config import validate_config, METHODS
from .intake import json_write

def run_study(root, overrides=None, progress=None):
    from .physics import simulate_method
    from .drone import simulate_mission
    from .analysis import generate_matrix
    root = Path(root)
    config = validate_config(overrides)
    start = datetime.now(timezone.utc)
    run_id = start.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    methods = {}
    for index, mid in enumerate(METHODS):
        if progress:
            progress(index / 5, f"{METHODS[mid]['name']} 전달장·드론 계산")
        physical = simulate_method(config, mid)
        from . import drone
        if hasattr(drone, "simulate_controls"):
            controls = drone.simulate_controls(config, physical)
        else:
            off = deepcopy(physical)
            off.update(reaction_force_N=[0., 0., 0.], device_power_W=0., consumable_kg=0.)
            controls = {"off": simulate_mission(config, off, True),
                        "uncorrected": simulate_mission(config, physical, False),
                        "corrected": simulate_mission(config, physical, True)}
        methods[mid] = {"identity": METHODS[mid], "physics": physical, "drone": controls}
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    source_hashes = {}
    for file in (root / "firelab").glob("*.py"):
        source_hashes[file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
    result = {
        "schema_version": "1.0", "run_id": run_id, "created_utc": start.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(), "config": config,
        "config_sha256": config_hash, "code_sha256": source_hashes,
        "runtime": {"python": sys.version, "platform": platform.platform()},
        "evidence_type": "unvalidated_physics", "validation": "software_tests_only",
        "scope": "비반응성 전달장과 가정 사양 기체 계산. 소화·생존시간 검증 결과가 아닙니다.",
        "methods": methods, "experiment_matrix": generate_matrix(),
        "suppression_comparison": {"status": "insufficient_evidence", "ranking": None,
            "reason": "검증된 반응성 모델 또는 반복별 화염 결과를 반입해야 효율·시너지를 계산합니다."},
    }
    dest = root / "runs" / run_id
    json_write(dest / "result.json", result)
    json_write(dest / "config.json", config)
    write_exports(dest, result)
    json_write(root / "runs" / "latest.json", {"run_id": run_id})
    if progress:
        progress(1., "결과·보고서 저장 완료")
    return result

def flat_metrics(result):
    rows = []
    for mid, data in result["methods"].items():
        for area, metrics in [("transport", data["physics"].get("metrics", {}))] + [
            (f"drone_{name}", value.get("metrics", {})) for name, value in data["drone"].items()
        ]:
            for key, value in metrics.items():
                if isinstance(value, (str, float, int)) or value is None:
                    rows.append({"run_id": result["run_id"], "method_id": mid, "scope": area,
                                 "metric": key, "value": value,
                                 "evidence_type": "unvalidated_physics"})
    return rows

def write_exports(dest, result):
    rows = flat_metrics(result)
    with (dest / "metrics.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["run_id", "method_id", "scope", "metric", "value", "evidence_type"])
        writer.writeheader()
        writer.writerows(rows)
    lines = ["# Firefield 계산 보고서", "", f"실행: {result['run_id']}", "", result["scope"], "",
             "## 검증 상태", "", "입력 사양은 가정값입니다. 전달장과 기체 운동을 계산했지만, 소화 성공률·소화시간·생존시간은 미산출입니다.",
             "", "## 방법별 결과", "", "| 방법 | 범주 | 지표 | 값 |", "|---|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['method_id']} | {row['scope']} | {row['metric']} | {row['value']} |")
    lines.extend(["", "## 모델 제한", ""])
    for mid, data in result["methods"].items():
        lines.append(f"### {mid} {data['identity']['name']}")
        lines.extend(f"- {item}" for item in data["physics"].get("limitations", []))
        lines.extend(f"- {item}" for item in data["drone"].get("corrected", {}).get("limitations", []))
        lines.append("")
    lines.extend(["## 재현", "", "동봉 config.json을 CLI run --config로 입력합니다. result.json에 코드·설정 hash와 실행 환경이 있습니다."])
    report = "\n".join(lines)
    (dest / "report.md").write_text(report, encoding="utf-8")
    (dest / "report.html").write_text(
        '<!doctype html><html lang="ko"><meta charset="utf-8"><title>Firefield 계산 보고서</title>'
        '<style>body{background:#fdfcfc;color:#201d1d;font:15px/1.8 ui-monospace,Consolas,monospace;margin:40px auto;max-width:1080px;padding:24px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
        + '<pre>' + html.escape(report) + '</pre></html>', encoding="utf-8")
    with zipfile.ZipFile(dest / "results.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for filename in ("result.json", "config.json", "metrics.csv", "report.md", "report.html"):
            archive.write(dest / filename, filename)

def latest(root):
    root = Path(root)
    pointer = root / "runs" / "latest.json"
    if not pointer.is_file():
        return None
    run_id = json.loads(pointer.read_text(encoding="utf-8"))["run_id"]
    import re
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
        raise ValueError("Invalid run id")
    return json.loads((root / "runs" / run_id / "result.json").read_text(encoding="utf-8"))
