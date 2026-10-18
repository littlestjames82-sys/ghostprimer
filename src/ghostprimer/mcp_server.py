"""Stdio MCP server (JSON-RPC, newline-delimited), local only.

Tools: primer_build, primer_check. Payloads are capped summaries;
no raw file bodies are returned.
"""
from __future__ import annotations

import json
import sys

from . import __version__
from .bundle import DEFAULT_BUDGET, build_bundle, check_bundle

TOOLS = [
    {"name": "primer_build",
     "description": "Build a GhostPrimer starter bundle for a project "
                    "(summary only, no file bodies).",
     "inputSchema": {"type": "object",
                     "properties": {
                         "project": {"type": "string"},
                         "out": {"type": "string"},
                         "budget": {"type": "integer"},
                         "recall_bundle": {"type": "string"},
                         "handoff_pack": {"type": "string"}},
                     "required": ["project", "out"]}},
    {"name": "primer_check",
     "description": "Verify a GhostPrimer bundle (hashes, totals, "
                    "provenance, exclusion rule).",
     "inputSchema": {"type": "object",
                     "properties": {"bundle": {"type": "string"}},
                     "required": ["bundle"]}},
]


def _call_tool(name: str, args: dict) -> dict:
    if name == "primer_build":
        manifest = build_bundle(args["project"], args["out"],
                                budget=int(args.get("budget", DEFAULT_BUDGET)),
                                recall_bundle=args.get("recall_bundle"),
                                handoff_pack=args.get("handoff_pack"))
        result = {"files": len(manifest["files"]),
                  "memory_items": len(manifest["memory_items"]),
                  "memory_path": manifest["memory_path"],
                  "total_sliced_tokens": manifest["total_sliced_tokens"],
                  "budget_unmet": manifest["budget_unmet"],
                  "not_included": len(manifest["not_included"])}
        if "handoff_input" in manifest:
            result["handoff_input"] = manifest["handoff_input"]
        return result
    if name == "primer_check":
        code, report = check_bundle(args["bundle"])
        return {"exit_code": code, **report}
    raise ValueError(f"unknown tool: {name}")


def serve(stdin=None, stdout=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        method = req.get("method", "")
        rid = req.get("id")
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05",
                      "capabilities": {"tools": {}},
                      "serverInfo": {"name": "ghostprimer",
                                     "version": __version__}}
            resp = {"jsonrpc": "2.0", "id": rid, "result": result}
        elif method == "tools/list":
            resp = {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
        elif method == "tools/call":
            params = req.get("params", {})
            try:
                payload = _call_tool(params.get("name", ""),
                                     params.get("arguments", {}))
                resp = {"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text",
                                 "text": json.dumps(payload)}]}}
            except Exception as exc:
                resp = {"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text",
                                 "text": json.dumps({"error": str(exc)})}],
                    "isError": True}}
        elif rid is not None:
            resp = {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32601, "message": f"unknown method {method}"}}
        else:
            continue
        stdout.write(json.dumps(resp) + "\n")
        stdout.flush()
    return 0
