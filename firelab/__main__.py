from pathlib import Path
import argparse
import json

def main():
    parser = argparse.ArgumentParser(description="Firefield 연구용 시뮬레이션")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)
    intake = sub.add_parser("intake")
    intake.add_argument("--source", type=Path, default=Path.home() / "Documents" / "카카오톡 받은 파일")
    sub.add_parser("audit")
    run = sub.add_parser("run")
    run.add_argument("--config", type=Path)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    campaign = sub.add_parser("campaign")
    campaign.add_argument("--config", type=Path)
    sub.add_parser("campaign-defaults")
    reanalysis=sub.add_parser("reanalyze-campaign")
    reanalysis.add_argument("campaign_id")
    fields = sub.add_parser("fields")
    fields.add_argument("run_directory", type=Path)
    fields.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "intake":
        from .intake import ingest
        result = ingest(args.root, args.source)
        print(json.dumps({"sources": len(result["sources"]), "references": len(result["reference_files"])}, ensure_ascii=False))
    elif args.command == "audit":
        from .contracts import audit_reference
        result = audit_reference(args.root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "run":
        from .lab import run_study
        config = json.loads(args.config.read_text(encoding="utf-8-sig")) if args.config else None
        result = run_study(args.root, config, lambda _, msg: print(msg, flush=True))
        print(json.dumps({"run_id": result["run_id"], "status": "completed", "scope": result["scope"]}, ensure_ascii=False))
    elif args.command == "campaign-defaults":
        from .campaign import defaults
        print(json.dumps(defaults(), ensure_ascii=False, indent=2))
    elif args.command == "campaign":
        from .campaign import run_campaign
        config = json.loads(args.config.read_text(encoding="utf-8-sig")) if args.config else None
        result = run_campaign(args.root, config, lambda f, s: print(f"{f:.0%} {s}", flush=True))
        print(json.dumps({"campaign_id": result['campaign_id'], "status": result['status']}, ensure_ascii=False))
    elif args.command == "reanalyze-campaign":
        from .campaign import reanalyze_campaign
        result=reanalyze_campaign(args.root,args.campaign_id)
        print(json.dumps({'campaign_id':result['campaign_id'],'records':len(result['records'])}))
    elif args.command == "fields":
        from .fields import export_fds_fields
        result = export_fds_fields(args.run_directory,args.output)
        print(json.dumps({"fields":result['field_count']}))
    else:
        from .server import serve
        serve(args.root, args.port)

if __name__ == "__main__":
    main()
