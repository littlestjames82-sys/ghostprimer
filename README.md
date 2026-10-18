# GhostPrimer

The first-session starter pack for a project. GhostSlice slices context
for a known task; GhostPrimer builds the small bundle a brand new agent
session, or a new hire driving one, should read before there is a task:
what the project is, where it starts, the handful of files everything
else leans on, and the project memory that is already written down.

One pack, sized to be read whole, with an honest list of what it left
out.

## What goes in the pack

- **Project facts, extracted**: name, version, description, entry
  points, language mix, and top-level layout, read from the project's
  own metadata and tree. A field that cannot be found is recorded as not
  found. Nothing is invented.
- **A code starter slice**: entry points at signature depth, then the
  highest fan-in modules (the files the rest of the project imports
  most), fitted to a token budget by a downgrade ladder (signatures,
  then outline, then excluded, largest first). Entry points never drop
  below outline.
- **A README extract**: the title, the headings, and the first paragraph
  under each heading, capped.
- **A memory primer**: standing rules and decisions from project-local
  files. When a GhostRecall bundle is supplied, its current items are
  used verbatim with their provenance. Otherwise a shallow fallback pass
  reads the well-known files (`AGENTS.md`, `CLAUDE.md`, `DECISIONS.md`,
  `docs/decisions/`, the latest `CHANGELOG.md` entry, `CONTRIBUTING.md`,
  `PLAN.md`, roadmap files), headings plus capped extracts, each item
  with file and line provenance. Memory is capped at 40 percent of the
  budget by default so it cannot crowd out the code.
- **An optional previous-session handoff**: when a GhostHandoff pack is
  supplied with `--handoff-pack`, its recorded state, open loops, and
  next steps are added as a separately labelled section. The input may
  be the pack directory or its `handoff.json` file. Handoff items pass
  through the same secret scan and compete for the same 40 percent
  memory share; the manifest records the input as `handoff_input`.
- **A not-included list**: the pack names what it left out. It is a
  starter, not the project, and it says so.

## Hard rules

- **Project-local sources only.** Every code file and project-memory
  item must resolve inside the project root. Anything resolving outside,
  symlinks included, is refused by path check. A GhostRecall bundle or
  GhostHandoff pack is read only when the caller supplies it explicitly;
  a handoff pack that names a different project is refused.
- **Private memory is never read.** The user's own assistant memory
  (`~/MEMORY.md`, `~/memory/`) is excluded by rule, even if a project
  file points straight at it. Primer primes from the project's record,
  not the assistant's.
- **Extractive only.** No model is called, no prose is generated about
  your code. The only written text is fixed template framing, marked as
  template in the manifest. Everything else is copied or structurally
  derived from project files: metadata fields, signatures, docstring
  first lines, headings, verbatim extracts.
- **Secrets guard.** Memory extracts, handoff items, and code files are
  scanned for secret-shaped literals. A flagged memory or handoff item
  is blocked and recorded, never included; a flagged code file is
  excluded and named.
- **Local only.** Python standard library only. No network, no
  accounts, no telemetry.

## Commands

```bash
ghostprimer build <project> -o <bundle> [--budget N] [--recall-bundle <dir>] [--handoff-pack <dir-or-handoff.json>] [--task "..."]
ghostprimer check <bundle>
ghostprimer doctor <project>
ghostprimer mcp
```

- `build` writes `PRIMER.md`, `manifest.json`, and `files/` into the
  bundle folder. Default budget is 6,000 estimated tokens. If the budget
  cannot be met, the bundle is still written and the unmet budget is
  reported, never hidden.
- `check` verifies a bundle against its manifest: file hashes and
  totals recomputed, `PRIMER.md` verified against its recorded hash,
  every recorded source path confirmed inside the project root, and no
  memory item sourced from the excluded private locations. Exit 0 pass,
  1 fail with reasons, 2 could not check.
- `doctor` is read-only: which primer sources exist or are missing, the
  estimator in use, and the expected budget outcome on this project.
- `mcp` serves `primer_build` and `primer_check` over stdio with capped
  summary payloads and no raw file bodies by default.

The bundle follows the GhostSlice bundle schema (per-file token counts
and sha256, integer top-level totals, token method recorded), so a
Primer bundle can also be validated with `ghostslice check` when
GhostSlice is installed or a sibling checkout is present.

## Honest limits

- The shallow memory fallback is deliberately dumb. Headings plus capped
  extracts will miss decisions buried mid-paragraph. That is exactly why
  the Recall bundle path exists; the manifest records which path
  produced the memory section.
- Fan-in is a proxy for importance, not importance itself. A generated
  or vendored file can rank high; the not-included list keeps every
  starter choice auditable.
- Fan-in itself is exact for Python (real AST) and parser-lite for
  JS/TS: relative `import`, `export ... from`, `require`, and dynamic
  `import()` specifiers are resolved statically, including
  extensionless imports, directory index files, and `.js` specifiers
  that name `.ts` sources. Comments and string contents are masked
  before scanning, so import-shaped text inside them never counts.
  Languages other than Python and JS/TS get no import graph yet:
  their files rank after files with known fan-in, and the manifest
  records their `fan_in` as 0 with `fan_in_method` "none", meaning
  unknown, not zero. Every file entry records its `fan_in_method`
  ("ast", "parser-lite", or "none") next to the count.
- Non-Python outlines are parser-lite estimates and are labelled as
  such in the manifest.
- Extractive facts can still be wrong when the project record is wrong:
  a stale README, a changelog that lies. Every item carries provenance
  so a reader can check the source in one hop.
- Token counts are estimates from the calibrated estimator, not exact
  tokenizer counts, and the estimator in use is stamped in the manifest.

## Where it sits

Primer is the front door. After session one, per-task work belongs to
GhostSlice (code) and GhostRecall (memory), GhostVerify checks the
bundle was enough, and GhostAtlas remains the full map for humans.
GhostHandoff can close a session, and a later Primer build can carry
that pack's recorded state, open loops, and next steps into the next
session when the pack is supplied explicitly. Primer does not replace
any of them, does not set anything up, and never runs your project. It
produces reading material only.
