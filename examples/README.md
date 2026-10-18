# GhostPrimer walkthrough

A five minute tour on a tiny sample project. Everything runs locally;
nothing here needs an account or a network.

## 1. Look at the project first

`examples/sample_project/` is a four file Python package called demoapp:
an entry point (`src/demoapp/main.py`), a greeter module it imports, an
unused module nothing imports, plus the project memory files a real repo
accumulates (`AGENTS.md`, `DECISIONS.md`, `CHANGELOG.md`, `README.md`).

## 2. Ask what a primer would find

```bash
ghostprimer doctor examples/sample_project
```

Doctor is read-only. It reports the project facts it can extract (name,
version, description), the entry points it found, which memory sources
exist and which are missing, and which token estimator is in use.

## 3. Build the starter pack

```bash
ghostprimer build examples/sample_project -o /tmp/demo-primer
```

The bundle is a folder, not an archive:

- `PRIMER.md` is the pack itself: extracted project facts, a start-here
  list, the README extract, the code slice (entry points and the modules
  they lean on, at signature depth), the memory primer, and a list of
  what was not included.
- `manifest.json` records every file and memory item with its token
  counts, sha256, mode, and provenance, plus the bundle totals.
- `files/` holds the sliced code at its original relative paths.

Read `PRIMER.md` top to bottom. That is the whole point of the tool:
one small pack a new session, human or agent, reads whole on day one.

## 4. Check the pack

```bash
ghostprimer check /tmp/demo-primer
```

Check recomputes the file hashes and totals, verifies `PRIMER.md`
against the hash recorded in the manifest, and confirms every recorded
source path sits inside the project root. Edit one line of `PRIMER.md`
and run it again: it fails, with the reason named.

## 5. Feed it a GhostRecall bundle instead

Without one, the memory section comes from a shallow fallback pass over
the well-known files (headings plus capped extracts), and the bundle
says so. When a project has a real GhostRecall bundle, pass it:

```bash
ghostprimer build <project> -o <bundle> --recall-bundle <recall-bundle-dir>
```

Primer then takes the bundle's current memory items verbatim, with
Recall's provenance, and records that path in the manifest. Superseded,
excluded, and blocked items in the Recall bundle are never carried in.

## 6. Undo

There is nothing to undo. A bundle is just a folder the tool wrote where
you told it to; delete it and the project is exactly as it was. Primer
never modifies the project it primes from.
