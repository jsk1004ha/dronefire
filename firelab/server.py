"""Loopback-only workbench. No arbitrary native solver or shell execution over HTTP."""
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote
import json
import mimetypes
import re
import threading
import uuid
import traceback
from .config import DEFAULTS, METHODS, validate_config
from .intake import evidence_catalog, json_write
from .lab import run_study, latest

def make_server(root, port=8765):
    root = Path(root).resolve()
    jobs = {}
    cancellations = {}
    lock = threading.Lock()
    max_body = 8 * 1024 * 1024

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def allowed_host(self):
            actual_port = self.server.server_address[1]
            allowed = {f"127.0.0.1:{actual_port}", f"localhost:{actual_port}"}
            return self.headers.get("Host") in allowed

        def json_response(self, status, obj):
            raw = json.dumps(obj, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)

        def send_file(self, path, download=False):
            if not path.is_file():
                return self.json_response(404, {"error": "파일을 찾을 수 없습니다."})
            raw = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", (mimetypes.guess_type(str(path))[0] or "application/octet-stream") +
                             ("; charset=utf-8" if path.suffix in (".html", ".js", ".css", ".md") else ""))
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-cache")
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if not self.allowed_host():
                return self.json_response(403, {"error": "Loopback host required"})
            path = unquote(urlparse(self.path).path)
            if path == "/api/catalog":
                from .analysis import generate_matrix
                return self.json_response(200, {"defaults": DEFAULTS, "methods": METHODS,
                    "evidence": evidence_catalog(root), "matrix": generate_matrix()})
            if path == "/api/latest":
                return self.json_response(200, latest(root))
            if path == "/api/native":
                manifests = []
                for folder in (root / "cases", root / "runs", root / "reports"):
                    if folder.exists():
                        for file in folder.rglob("*manifest*.json"):
                            if len(manifests) >= 30:
                                break
                            try:
                                obj = json.loads(file.read_text(encoding="utf-8-sig"))
                                manifests.append({"path": str(file.relative_to(root)), "data": obj})
                            except (OSError, ValueError):
                                continue
                return self.json_response(200, {"manifests": manifests})
            if path == "/api/health":
                return self.json_response(200, {"status": "ok", "app": "Firefield", "version": "0.1.0"})
            if path == "/api/campaign/defaults":
                from .campaign import defaults
                return self.json_response(200, defaults())
            if path == "/api/campaign/latest":
                from .campaign import latest_campaign
                return self.json_response(200, latest_campaign(root))
            if path == "/api/fieldsets":
                folder = root / "reports" / "fields"
                return self.json_response(200, [{'id':p.stem,'bytes':p.stat().st_size} for p in sorted(folder.glob('*.json'))])
            field_match = re.fullmatch(r"/api/fieldsets/([A-Za-z0-9_-]+)", path)
            if field_match:
                return self.send_file(root / "reports" / "fields" / (field_match[1]+'.json'))
            study_match = re.fullmatch(r"/api/campaign/(study_[A-Za-z0-9_]+)/([A-Za-z0-9_-]+\.(?:json|csv|html|md|png|zip))", path)
            if study_match:
                return self.send_file(root / 'runs' / study_match[1] / study_match[2], study_match[2].endswith('.zip'))
            if path.startswith("/api/jobs/"):
                with lock:
                    job = jobs.get(path.rsplit("/", 1)[-1])
                    snapshot = dict(job) if job else None
                return self.json_response(200 if snapshot else 404, snapshot or {"error": "unknown job"})
            match = re.fullmatch(r"/api/results/([A-Za-z0-9_-]{1,80})/(result\.json|metrics\.csv|report\.md|report\.html|results\.zip|config\.json)", path)
            if match:
                return self.send_file(root / "runs" / match[1] / match[2], match[2] != "report.html")
            if path == "/implement.md":
                return self.send_file(root / "implement.md", True)
            if path == "/physics.md":
                return self.send_file(root / "docs" / "physics_derivation.md")
            if path in ("/transport-physics.md", "/transport_derivation.md"):
                return self.send_file(root / "docs" / "transport_derivation.md")
            if path.startswith("/visualizations/"):
                img_name = path.replace("/visualizations/", "")
                img_path = root / "reports" / "visualizations" / img_name
                if img_path.is_file():
                    return self.send_file(img_path)
            if path in ("/firefield_research_results.zip", "/download/research_results"):
                return self.send_file(root / "firefield_research_results.zip", download=True)
            if path == "/api/visualizations":
                vis_dir = root / "reports" / "visualizations"
                files = [f.name for f in sorted(vis_dir.glob("*.png"))] if vis_dir.exists() else []
                return self.json_response(200, {"visualizations": files})
            static = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css", "/campaign.js":"campaign.js"}
            if path in static:
                return self.send_file(root / "web" / static[path])
            return self.json_response(404, {"error": "not found"})

        def do_POST(self):
            if not self.allowed_host():
                return self.json_response(403, {"error": "Loopback host required"})
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{self.headers['Host']}":
                return self.json_response(403, {"error": "Same origin required"})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.json_response(415, {"error": "application/json required"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > max_body:
                    return self.json_response(413, {"error": "JSON 크기는 8MB 이하여야 합니다."})
                def invalid_constant(value):
                    raise ValueError(f"Non-finite JSON: {value}")
                body = json.loads(self.rfile.read(length), parse_constant=invalid_constant)
                if not isinstance(body, dict):
                    raise ValueError("JSON 객체가 필요합니다.")
                path = urlparse(self.path).path
                if path == "/api/validate":
                    return self.json_response(200, validate_config(body))
                if path == "/api/campaign/run":
                    from .campaign import run_campaign, validate_campaign
                    config = validate_campaign(body)
                    with lock:
                        if any(j['status'] in ('queued','running') for j in jobs.values()):
                            return self.json_response(409, {'error':'진행 중인 계산이 있습니다.'})
                        job_id=uuid.uuid4().hex
                        jobs[job_id]={'status':'queued','progress':0.,'message':'연구 실행 대기'}
                        cancel=threading.Event();cancellations[job_id]=cancel
                    def campaign_worker():
                        try:
                            def progress(fraction,message):
                                with lock:jobs[job_id].update(status='running',progress=fraction,message=message)
                            result=run_campaign(root,config,progress,cancel)
                            with lock:jobs[job_id].update(status='completed',campaign_id=result['campaign_id'],progress=1.,message=result['status'])
                        except Exception as exc:
                            traceback.print_exc()
                            with lock:jobs[job_id].update(status='failed',message=str(exc))
                    threading.Thread(target=campaign_worker,daemon=True).start()
                    return self.json_response(202,{'job_id':job_id})
                if path == "/api/campaign/cancel":
                    cancel=cancellations.get(body.get('job_id'))
                    if cancel is None:return self.json_response(404,{'error':'unknown campaign job'})
                    cancel.set()
                    return self.json_response(200,{'status':'stop_after_current_case'})
                if path == "/api/study/analyze":
                    from .study_analysis import analyze_study
                    from .exposure import summarize_exposure
                    records=body.get('records')
                    if not isinstance(records,list) or not 1<=len(records)<=1000:
                        raise ValueError('1..1000 native time-series records required')
                    prereg=body['preregistration']
                    result={'analysis':analyze_study(records,prereg,synergy_specs=body.get('synergy_specs',[]))}
                    if body.get('exposure_criteria'):
                        result['exposure']=summarize_exposure(records,body['exposure_criteria'],prereg['tau_s'])
                    json_write(root/'reports'/'study_imports'/(uuid.uuid4().hex+'.json'),result)
                    return self.json_response(200,result)
                if path == "/api/run":
                    config = validate_config(body.get("config", body))
                    with lock:
                        if any(job["status"] in ("queued", "running") for job in jobs.values()):
                            return self.json_response(409, {"error": "진행 중인 계산이 있습니다."})
                        job_id = uuid.uuid4().hex
                        jobs[job_id] = {"status": "queued", "progress": 0, "message": "대기 중"}
                    def worker():
                        try:
                            def progress(fraction, message):
                                with lock:
                                    jobs[job_id].update(status="running", progress=fraction, message=message)
                            result = run_study(root, config, progress)
                            with lock:
                                jobs[job_id].update(status="completed", run_id=result["run_id"], progress=1.)
                        except Exception as exc:
                            traceback.print_exc()
                            with lock:
                                jobs[job_id].update(status="failed", message=str(exc))
                    threading.Thread(target=worker, daemon=True).start()
                    return self.json_response(202, {"job_id": job_id})
                if path == "/api/analyze":
                    from .analysis import analyze_outcomes
                    records = body.get("records")
                    if not isinstance(records, list) or len(records) > 10000:
                        raise ValueError("records 배열은 10,000개 이하여야 합니다.")
                    tau = body.get("tau_s", 10.)
                    result = analyze_outcomes(records, tau, bootstrap_samples=500, seed=42)
                    import_id = uuid.uuid4().hex
                    json_write(root / "data" / "imports" / f"{import_id}.json", body)
                    json_write(root / "reports" / "outcomes" / f"{import_id}.json", result)
                    return self.json_response(200, result)
                if path == "/api/synergy":
                    from .analysis import compute_synergy
                    records = body.get("records")
                    if not isinstance(records, list) or len(records) > 10000:
                        raise ValueError("records 배열은 10,000개 이하여야 합니다.")
                    options = body.get("synergy")
                    if not isinstance(options, dict):
                        raise ValueError("synergy 비교 조건 객체가 필요합니다.")
                    allowed_options = {"control_id", "combination_id", "partial_single_ids",
                                       "equal_budget_single_ids", "preselected_single_id", "selection_provenance"}
                    if set(options) - allowed_options:
                        raise ValueError("지원하지 않는 synergy 옵션입니다.")
                    result = compute_synergy(records, **options)
                    import_id = uuid.uuid4().hex
                    json_write(root / "data" / "imports" / f"{import_id}.json", body)
                    json_write(root / "reports" / "synergy" / f"{import_id}.json", result)
                    return self.json_response(200, result)
                if path == "/api/optimize":
                    from .optimizer import run_optimization
                    result = run_optimization(body)
                    return self.json_response(200, result)
                if path == "/api/montecarlo":
                    from .uncertainty import run_monte_carlo
                    method_id = body.get("method_id", "M3")
                    num_samples = body.get("num_samples", 50)
                    uncertainty_spec = body.get("uncertainty_spec")
                    base_cfg = body.get("base_cfg")
                    result = run_monte_carlo(method_id, num_samples, uncertainty_spec, base_cfg)
                    return self.json_response(200, result)
                return self.json_response(404, {"error": "not found"})
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                return self.json_response(400, {"error": str(exc)})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)

def serve(root, port=8765):
    server = make_server(root, port)
    print(f"Firefield: http://127.0.0.1:{server.server_address[1]} - Ctrl+C to stop", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
