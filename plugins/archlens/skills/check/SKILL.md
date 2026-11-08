---
name: check
description: "Audit architecture documents for evidence, missing scenarios, broken links, diagram clarity, and plain language. Does not edit files."
argument-hint: "[page or scenario]"
disable-model-invocation: true
context: fork
agent: general-purpose
background: false
metadata:
  internal: true
---

# Check architecture documents

Scope: $ARGUMENTS

Read `${CLAUDE_PLUGIN_ROOT}/references/contract.md`.
Do not edit files, install tools, or run commands that update snapshots.

Use the checker to resolve configuration. Read the index, then the requested pages and evidence.
If Python 3.9+ exists, run:
`python "${CLAUDE_PLUGIN_ROOT}/scripts/archlens.py" check --root <project> --summary`.
The script checks the whole mapped handbook; keep semantic review within the requested scope.
Also run `status --root <project> --summary` and report stale or unsynced pages.
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
