"""Bundle build + check.

Bundle layout:
  <out>/PRIMER.md       the starter pack (facts, code slice, memory)
  <out>/manifest.json   GhostSlice-schema files + memory items + totals
  <out>/files/<rel>     sliced code files

The manifest follows the GhostSlice bundle schema (per-file
original_tokens / sliced_tokens / sha256, top-level integer totals,
token_method) so a Primer bundle validates under `ghostslice check`
when built with the GhostSlice estimator. Memory items are extra
manifest data; Slice's checker only validates the files section.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, memory as memory_mod, scan, secrets as secrets_mod
from . import handoff as handoff_mod
from . import tokens
from .slicer import slice_source

DEFAULT_BUDGET = 6000
MEMORY_SHARE = 0.40

TEMPLATE_NOTE = ("(template) This pack was built by GhostPrimer from "
                 "project-local files only. Framing lines marked "
                 "(template) are fixed template text; everything else is "
                 "extracted from the project files named as provenance.")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_bundle(project, out, budget: int = DEFAULT_BUDGET,
                 recall_bundle=None, task: str = "",
                 handoff_pack=None) -> dict:
    root = Path(project)
    if not root.is_dir():
        raise ValueError(f"project not found: {project}")
    if scan.is_private_memory(root):
        raise ValueError("refused: project root is a private memory location")
    root = root.resolve()
    out = Path(out)

    facts = scan.project_facts(root)
    entries = scan.find_entry_points(root, facts)
    fan_in = scan.import_fan_in(root)
    mix = scan.language_mix(root)
    layout = scan.top_level_layout(root)

    # --- memory first, capped at MEMORY_SHARE of the budget ---
    blocked: list[dict] = []
    if recall_bundle:
        mem_items, blocked = memory_mod.recall_bundle_memory(
            root, Path(recall_bundle))
        memory_path = "recall-bundle"
    else:
        mem_items, blocked = memory_mod.fallback_memory(root)
        memory_path = "fallback"
    # An explicitly supplied GhostHandoff pack is another memory
    # source, not a separate budget: its state / open-loop / next-step
    # items enter the same capped pool below and compete for the same
    # memory share. They are considered first because the caller opted
    # into carrying the previous session forward.
    handoff_items: list[dict] = []
    handoff_blocked: list[dict] = []
    handoff_meta: dict | None = None
    if handoff_pack:
        handoff_items, handoff_blocked, handoff_meta = \
            handoff_mod.load_handoff_pack(root, handoff_pack)
        blocked.extend(handoff_blocked)
    memory_cap = int(budget * MEMORY_SHARE)
    kept_mem: list[dict] = []
    dropped_mem: list[dict] = []
    mem_tokens = 0
    for item in handoff_items + mem_items:
        est = tokens.estimate(item["text"], "markdown")
        item["estimated_tokens"] = est
        if mem_tokens + est <= memory_cap or not kept_mem:
            kept_mem.append(item)
            mem_tokens += est
        else:
            dropped_mem.append({"path": item["provenance"]["path"],
                                "reason": "memory budget share spent"})
    mem_items = kept_mem

    # --- code candidates: entry points, then fan-in rank ---
    all_code: list[str] = []
    for rel, _p in scan.iter_project_files(root):
        ext = Path(rel).suffix.lower()
        if ext in scan.CODE_EXTS and not rel.startswith(("tests/", "test/")):
            all_code.append(rel)
    entry_set = set(entries)
    rest = [r for r in all_code if r not in entry_set]
    rest.sort(key=lambda r: (-fan_in.get(r, 0), r))
    candidates = [(r, True) for r in entries if r in set(all_code)]
    not_included: list[dict] = []
    for rel in rest:
        # Starter selection is entry points plus highest fan-in only
        # (PLAN.md). A file the import graph knows (it is a key in
        # fan_in) with zero fan-in is referenced by nothing and is not
        # an entry point: leave it out of the slice and name it in the
        # not-included list instead of including everything that fits.
        # The graph covers Python (ast) and JS/TS (parser-lite). Files
        # absent from fan_in are other languages, where no import graph
        # is built: their fan-in is unknown, not zero, so they stay
        # candidates under the budget as before.
        if rel in fan_in and fan_in.get(rel, 0) == 0:
            not_included.append({
                "path": rel,
                "reason": "unreferenced: no project file imports it "
                          "and it is not an entry point; left out of "
                          "the starter slice"})
        else:
            candidates.append((rel, False))

    code_budget = budget - mem_tokens
    files_out: list[dict] = []
    code_tokens = 0
    budget_unmet = False
    sliced_texts: dict[str, str] = {}
    for rel, is_entry in candidates:
        source = (root / rel).read_text(encoding="utf-8", errors="replace")
        findings = secrets_mod.scan_text(source)
        if findings:
            not_included.append({
                "path": rel,
                "reason": "secret-shaped literal found ("
                          + ", ".join(sorted({f['type'] for f in findings}))
                          + "); excluded, value not recorded"})
            continue
        original_tokens = tokens.estimate(source, tokens.language_for(rel))
        chosen = None
        for mode in ("signatures", "outline"):
            text, confidence = slice_source(rel, source, mode)
            est = tokens.estimate(text, tokens.language_for(rel))
            if code_tokens + est <= code_budget:
                chosen = (mode, text, confidence, est)
                break
            if is_entry and mode == "outline":
                # Entry points are never dropped below outline; include
                # and report the budget as unmet instead.
                chosen = (mode, text, confidence, est)
                budget_unmet = True
                break
        if chosen is None:
            not_included.append({"path": rel,
                                 "reason": "code budget spent"})
            continue
        mode, text, confidence, est = chosen
        code_tokens += est
        sliced_texts[rel] = text
        files_out.append({
            "path": rel,
            "mode": mode,
            "language": tokens.language_for(rel),
            "confidence": confidence,
            "entry_point": is_entry,
            "fan_in": fan_in.get(rel, 0),
            "fan_in_method": scan.fan_in_method(rel),
            "original_tokens": original_tokens,
            "sliced_tokens": est,
            "sha256": sha256_text(text),
        })

    # --- README extract (into PRIMER.md, not files/) ---
    readme = scan.readme_path(root)
    readme_text = ""
    if readme is not None:
        raw = readme.read_text(encoding="utf-8", errors="replace")
        if not secrets_mod.scan_text(raw):
            readme_text = memory_mod.readme_extract(raw)
        else:
            blocked.append({"path": readme.name,
                            "reason": "secret-shaped literal in README; "
                                      "extract blocked"})

    # --- write files/ ---
    files_dir = out / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    for rel, text in sliced_texts.items():
        dest = files_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")

    total_original = sum(f["original_tokens"] for f in files_out)
    total_sliced = sum(f["sliced_tokens"] for f in files_out)

    # --- PRIMER.md from the labelled template ---
    primer_text = _render_primer(facts, layout, mix, entries, files_out,
                                 sliced_texts, mem_items, readme_text,
                                 not_included, blocked, memory_path,
                                 budget, budget_unmet, task)

    manifest = {
        "tool": "ghostprimer",
        "version": __version__,
        "generated_at": _now(),
        "root": str(root),
        "token_method": tokens.METHOD,
        "task": task,
        "budget_tokens": budget,
        "budget_unmet": budget_unmet,
        "memory_path": memory_path,
        "template_text": [TEMPLATE_NOTE],
        "facts": {**facts, "language_mix": mix, "layout": layout},
        "entry_points": entries,
        "files": files_out,
        "memory_items": [
            {k: item[k] for k in ("id", "source_type", "title",
                                  "provenance", "status", "estimated_tokens")}
            for item in mem_items
        ],
        "memory_blocked": blocked,
        "not_included": not_included + dropped_mem,
        "total_original_tokens": total_original,
        "total_sliced_tokens": total_sliced,
        "total_saved_tokens": total_original - total_sliced,
        "memory_tokens_estimate": mem_tokens,
    }
    if handoff_meta is not None:
        kept_handoff = [item for item in mem_items
                        if item.get("source_type") == "handoff"]
        manifest["handoff_input"] = {
            **handoff_meta,
            "items_considered": len(handoff_items) + len(handoff_blocked),
            "items_included": len(kept_handoff),
            "items_blocked": len(handoff_blocked),
            "estimated_tokens": sum(item["estimated_tokens"]
                                    for item in kept_handoff),
        }
    (out / "PRIMER.md").write_text(primer_text, encoding="utf-8")
    manifest["primer_sha256"] = sha256_text(primer_text)
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _render_primer(facts, layout, mix, entries, files_out, sliced_texts,
                   mem_items, readme_text, not_included, blocked,
                   memory_path, budget, budget_unmet, task) -> str:
    lines: list[str] = []
    name = facts.get("name") or "(name not found in project files)"
    lines.append(f"# GhostPrimer starter pack: {name}")
    lines.append("")
    lines.append(TEMPLATE_NOTE)
    lines.append("")
    lines.append("## Project facts (extracted)")
    lines.append(f"- Name: {facts.get('name') or 'not found'}")
    lines.append(f"- Version: {facts.get('version') or 'not found'}")
    lines.append(f"- Description: {facts.get('description') or 'not found'}")
    if facts.get("requires_python"):
        lines.append(f"- Requires Python: {facts['requires_python']}")
    if facts.get("scripts"):
        for key, val in sorted(facts["scripts"].items()):
            lines.append(f"- Script `{key}`: {val}")
    if mix:
        mix_str = ", ".join(f"{ext} x{count}" for ext, count in mix.items())
        lines.append(f"- Code files by extension: {mix_str}")
    if layout:
        lines.append("- Top level: " + ", ".join(layout))
    lines.append("")
    lines.append("## Start here (template: entry points first)")
    for rel in entries:
        lines.append(f"- {rel}")
    if not entries:
        lines.append("- (no entry points detected)")
    lines.append("")
    if readme_text:
        lines.append("## README extract (verbatim headings + first paragraphs)")
        lines.append("")
        lines.append(readme_text.rstrip())
        lines.append("")
    lines.append("## Code slice")
    for entry in files_out:
        rel = entry["path"]
        lines.append("")
        lines.append(f"### {rel} (mode: {entry['mode']}, {entry['confidence']})")
        lines.append("")
        lines.append("```")
        lines.append(sliced_texts[rel].rstrip())
        lines.append("```")
    handoff_items = [item for item in mem_items
                     if item.get("source_type") == "handoff"]
    regular_items = [item for item in mem_items
                     if item.get("source_type") != "handoff"]
    if handoff_items:
        lines.append("")
        lines.append("## Previous session handoff (source: GhostHandoff pack)")
        for item in handoff_items:
            prov = item["provenance"]
            lines.append("")
            lines.append(f"### {item['title']} [{prov['path']}:{prov['line']}]")
            lines.append("")
            lines.append(item["text"].rstrip())
        lines.append("")
    else:
        lines.append("")
    lines.append(f"## Project memory primer (source: {memory_path})")
    if not regular_items:
        lines.append("")
        lines.append("(template) No project memory items were found in "
                     "project-local sources.")
    for item in regular_items:
        prov = item["provenance"]
        lines.append("")
        lines.append(f"### {item['title']} [{prov['path']}:{prov['line']}]")
        lines.append("")
        lines.append(item["text"].rstrip())
    lines.append("")
    lines.append("## Not included (template: the pack is a starter, not the project)")
    for entry in not_included:
        lines.append(f"- {entry['path']}: {entry['reason']}")
    for entry in blocked:
        lines.append(f"- {entry['path']}: BLOCKED, {entry['reason']}")
    if not not_included and not blocked:
        lines.append("- (nothing recorded)")
    lines.append("")
    lines.append("## Limits (template)")
    lines.append("- Extractive facts only; nothing here was summarised by a model.")
    lines.append("- Facts can be wrong where the project record is wrong; provenance is given for every memory item.")
    lines.append(f"- Budget: {budget} estimated tokens"
                 + (" (UNMET: entry points were kept at outline anyway)" if budget_unmet else ""))
    lines.append("")
    return "\n".join(lines)


def check_bundle(bundle_dir) -> tuple[int, dict]:
    """Return (exit_code, report). 0 pass, 1 fail, 2 could not check."""
    bundle = Path(bundle_dir)
    manifest_path = bundle / "manifest.json"
    if not manifest_path.exists():
        return 2, {"ok": False, "errors": ["manifest.json missing"]}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return 2, {"ok": False, "errors": [f"manifest unreadable: {exc}"]}
    errors: list[str] = []
    root = Path(str(manifest.get("root", "")))
    files_checked = 0
    total_sliced = 0
    for entry in manifest.get("files", []):
        rel = entry.get("path", "")
        on_disk = bundle / "files" / rel
        if not on_disk.exists():
            errors.append(f"{rel}: exported file missing")
            continue
        text = on_disk.read_text(encoding="utf-8", errors="replace")
        if sha256_text(text) != entry.get("sha256"):
            errors.append(f"{rel}: sha256 mismatch")
        recomputed = tokens.estimate(text, tokens.language_for(rel))
        if recomputed != entry.get("sliced_tokens"):
            errors.append(f"{rel}: sliced_tokens {entry.get('sliced_tokens')} "
                          f"!= recomputed {recomputed}")
        total_sliced += recomputed
        files_checked += 1
    if total_sliced != manifest.get("total_sliced_tokens"):
        errors.append(f"total_sliced_tokens {manifest.get('total_sliced_tokens')} "
                      f"!= recomputed {total_sliced}")
    primer_path = bundle / "PRIMER.md"
    if not primer_path.exists():
        errors.append("PRIMER.md missing")
    elif sha256_text(primer_path.read_text(encoding="utf-8", errors="replace")) \
            != manifest.get("primer_sha256"):
        errors.append("PRIMER.md: sha256 mismatch (tampered or stale)")
    for item in manifest.get("memory_items", []):
        prov = (item.get("provenance") or {}).get("path", "")
        if not prov:
            errors.append(f"{item.get('id')}: memory item without provenance")
            continue
        candidate = root / prov
        if scan.is_private_memory(candidate):
            errors.append(f"{prov}: memory item sourced from a private "
                          "memory location")
            continue
        try:
            scan.assert_project_local(root, candidate)
        except ValueError as exc:
            errors.append(str(exc))
    report = {"ok": not errors, "errors": errors,
              "files_checked": files_checked,
              "total_sliced_tokens": total_sliced}
    return (0 if not errors else 1), report
