"""GhostPrimer CLI: build | check | doctor | mcp."""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .bundle import DEFAULT_BUDGET, build_bundle, check_bundle
from .doctor import doctor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ghostprimer",
        description="First-session starter bundle for a project: minimal "
                    "code slice plus project-memory primer, extractive "
                    "facts only, project-local sources only.")
    parser.add_argument("--version", action="version",
                        version=f"ghostprimer {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="build a starter bundle")
    p_build.add_argument("project")
    p_build.add_argument("-o", "--out", required=True)
    p_build.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    p_build.add_argument("--recall-bundle", default=None,
                         help="consume a GhostRecall bundle for the "
                              "memory section instead of the fallback pass")
    p_build.add_argument("--handoff-pack", default=None,
                         help="consume a GhostHandoff pack (pack directory "
                              "or its handoff.json file) as an additional "
                              "previous-session source")
    p_build.add_argument("--task", default="")
    p_build.add_argument("--json", action="store_true")

    p_check = sub.add_parser("check", help="verify a starter bundle")
    p_check.add_argument("bundle")

    p_doctor = sub.add_parser("doctor", help="report primer sources on a project")
    p_doctor.add_argument("project")

    sub.add_parser("mcp", help="run the stdio MCP server")

    args = parser.parse_args(argv)

    if args.command == "build":
        try:
            manifest = build_bundle(args.project, args.out,
                                    budget=args.budget,
                                    recall_bundle=args.recall_bundle,
                                    task=args.task,
                                    handoff_pack=args.handoff_pack)
        except ValueError as exc:
            print(f"ghostprimer: {exc}", file=sys.stderr)
            return 2
        if args.json:
            summary = {k: manifest[k] for k in (
                "root", "budget_tokens", "budget_unmet", "memory_path",
                "total_original_tokens", "total_sliced_tokens",
                "memory_tokens_estimate")}
            if "handoff_input" in manifest:
                summary["handoff_input"] = manifest["handoff_input"]
            print(json.dumps(summary, indent=2))
        else:
            print(f"GhostPrimer bundle: {args.out}")
            print(f"  files: {len(manifest['files'])} "
                  f"({manifest['total_sliced_tokens']} sliced tokens, "
                  f"was {manifest['total_original_tokens']})")
            print(f"  memory: {len(manifest['memory_items'])} items "
                  f"via {manifest['memory_path']} "
                  f"({manifest['memory_tokens_estimate']} tokens)")
            if "handoff_input" in manifest:
                handoff = manifest["handoff_input"]
                print(f"  handoff: {handoff['items_included']} items "
                      f"from {handoff['json_path']} "
                      f"({handoff['estimated_tokens']} tokens)")
            print(f"  not included: {len(manifest['not_included'])}, "
                  f"blocked: {len(manifest['memory_blocked'])}")
            if manifest["budget_unmet"]:
                print(f"  WARNING: budget {args.budget} unmet; entry "
                      "points kept at outline (see PRIMER.md limits)")
        return 0
    if args.command == "check":
        code, report = check_bundle(args.bundle)
        print(json.dumps(report, indent=2))
        return code
    if args.command == "doctor":
        report = doctor(args.project)
        print(json.dumps(report, indent=2))
        return 0 if report.get("ok") else 2
    if args.command == "mcp":
        from .mcp_server import serve
        return serve()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
