# Check architecture documents

Scope: the relevant part of the user's request

Read `<skill-dir>/references/contract.md`.
Do not edit files, install tools, or run commands that update snapshots.

Use the checker to resolve configuration. Read the index, then the requested pages and evidence.
If Python 3.10+ exists, run:
`python "<skill-dir>/scripts/archlens.py" check --root <project> --summary`.
The script checks the whole mapped handbook; keep semantic review within the requested scope.
If Python is absent, read the configuration reference and perform manual structural checks.
State which automated checks were unavailable.
Report a failed checker explicitly.
If records are omitted, save full `--json` output locally and inspect relevant batches.

Inspect source and tests to check important claims. Rendering is not semantic validation.
Check runtime branches, data ownership, recovery paths, decision provenance, and source links.
Render locally with an existing renderer when available. Do not upload private diagrams.
Read the "80% target" section of the writing reference only for a requested style audit.
Apply it only with a real, declared audit count. Otherwise report style as not measured.

Return findings ordered by impact, page links, evidence, coverage gaps, and checks actually run.
Never report "fully documented", formal STE compliance, or a passing render that did not occur.
