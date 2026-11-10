---
name: update
description: "Refresh Archlens architecture pages made stale by code, contract, data, or deployment changes. Use when Archlens reports stale pages or the user asks to update architecture docs."
argument-hint: "[local base ref such as main, or page IDs]"
context: fork
agent: general-purpose
background: false
metadata:
  internal: true
---

# Update architecture documents

Request: $ARGUMENTS

Read `${CLAUDE_PLUGIN_ROOT}/references/contract.md`.
Read `${CLAUDE_PLUGIN_ROOT}/references/configuration.md` only without Python or to edit the map.
Read only the relevant template section for a new page.
Require an existing handbook or project `.archlens.json`. Otherwise suggest `/archlens:setup`.
Do not assume a branch name, fetch a remote, or run shell text from arguments.

If Python 3.9+ exists, find candidates with the bundled script:
`python "${CLAUDE_PLUGIN_ROOT}/scripts/archlens.py" status --root <project> --summary`.
It compares cited evidence and covered files with the last sync, including commits.
Fix `stale` pages first: their cited evidence changed. Confirm `review` pages quickly:
only other covered files changed. If the request names page IDs, limit work to them.
Verify a named or `needs-review` page even when fresh: check its main claims against source.
If the request names a local ref, also run `impact --root <project> --base <ref> --summary`
and triage uncovered files. Quote paths and refs as distinct arguments.
Without Python, use local Git and the document map manually; disclose that limit.
A checker failure is not permission to silently use a fallback.

For each candidate, read the page and the changed files' diffs in bounded ranges.
Use `git diff <syncedCommit> -- <file>` when the report gives a commit.
Trace affected contracts and consumers. A path match is not proof of stale prose.
Change only prose that source now contradicts or leaves incomplete. Keep other prose,
and the structure of mapped existing documents, stable. Update links when files moved.
If a page needs no change, give an evidence-based no-impact reason.
For uncertain execution, read only "Trace execution and data" in the workflow reference.

After you verify a page against current source, run `sync --root <project> --page <ID>`.
Repeat `--page` for several pages. Never sync a page you did not review.
Do not mark documents reviewed or decisions accepted without authorized evidence.
Run `check --root <project> --summary` and return the contract's concise handoff.
