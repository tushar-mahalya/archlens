---
name: update
description: "Update only the architecture pages affected by code, contract, data, or deployment changes."
argument-hint: "[local base ref, such as main]"
disable-model-invocation: true
context: fork
agent: general-purpose
background: false
metadata:
  internal: true
---

# Update architecture documents

Comparison ref: $ARGUMENTS

Read `${CLAUDE_PLUGIN_ROOT}/references/contract.md`.
Use the checker below to resolve config and select candidate pages.
Read `${CLAUDE_PLUGIN_ROOT}/references/configuration.md` only without Python,
or when changing map metadata. Read only the relevant template section for a new page.

Require an existing handbook or project `.archlens.json`. Otherwise suggest `/archlens:setup`.
Use the supplied ref's merge base with HEAD, plus staged, unstaged, and untracked changes.
Without a ref, inspect working-tree changes only and state that limit.
Do not assume a branch name, fetch a remote, or run shell text from arguments.

If Python 3.10+ exists, run the bundled script as a normal shell command:
`python "${CLAUDE_PLUGIN_ROOT}/scripts/archlens.py" impact --root <project> --base <ref> --summary`.
Omit `--base` when none was supplied. Quote paths and refs as distinct arguments.
If Python is absent, use local Git and the document map manually; disclose that limitation.
A checker failure is not permission to silently use a fallback.

Trace affected contracts and consumers. Path matches are review candidates, not proof of stale prose.
Update only affected views and map entries. Include deleted and renamed source references.
If no architecture content changed, give an evidence-based no-impact reason.
Do not mark documents reviewed or decisions accepted without authorized evidence.
If the report omits records, save full `--json` output locally and inspect it in batches.
For uncertain execution, read only "Trace execution and data" in the workflow reference.
Validate the update and return the contract's concise handoff.
