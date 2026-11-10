---
name: setup
description: "Create an evidence-based architecture handbook for a project. Use when the user wants an overview, execution flows, data flows, or architecture documentation."
argument-hint: "[adopt | new] [project folder or priority scenario]"
disable-model-invocation: true
context: fork
agent: general-purpose
background: false
metadata:
  internal: true
---

# Set up Archlens

Task context: $ARGUMENTS

Read `${CLAUDE_PLUGIN_ROOT}/references/contract.md`. Read only the "Document map" and
"Freshness and agent context" sections of `${CLAUDE_PLUGIN_ROOT}/references/configuration.md`.
With Python 3.9+, run the bundled `scripts/archlens.py config --root <project> --summary`.
Without Python, also read that reference's first section.
Read only "Initial coverage" and "Trace execution and data" in `${CLAUDE_PLUGIN_ROOT}/references/workflow.md`.
Read a `${CLAUDE_PLUGIN_ROOT}/references/templates.md` section only when you create that page kind.

The user explicitly requests documentation setup. Work in the current project unless
the argument selects another folder. Do not assume conversation history is available.

1. Inspect existing docs, entrypoints, contracts, configuration, and tests.
2. Select a bounded scope: context, main units, and one important journey.
3. Trace the journey: branch conditions, data changes, and failure behavior.
4. Create or extend the handbook. Never move or duplicate existing documents.
   Follow "Existing documents" in the workflow reference for `adopt` or `new`.
5. Add an index, coverage gaps, glossary terms, and a `map.json` document map.
6. Draft decisions only when evidence supports a significant design choice.
   Mark missing historical rationale as unknown.
7. Fix errors that `check --root <project> --summary` reports. Check diagrams locally.
8. With Python 3.9+, run `sync --root <project> --all` to record the freshness baseline.
   Without it, state that freshness is not tracked.
9. Claude Code loads a short handbook map at session start. For other agents,
   offer to set `"contextFile": "AGENTS.md"` in `.archlens.json`, then run
   `context --root <project> --write`. Ask before you edit any agent instruction file.
   Follow the contract's handoff.

Do not install packages, change application source, commit, or publish.
If the project contains multiple systems, ask which to document first.
If permissions or evidence block work, report the exact blocker.
