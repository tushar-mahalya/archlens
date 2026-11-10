# Keep the handbook current automatically

Archlens separates two jobs:

1. **Detect drift.** This is deterministic, needs no model, and costs no tokens.
   `status` compares each page's covered and linked files with the content
   recorded at its last `sync`.
2. **Rewrite prose.** This needs a coding agent. The `update` operation reviews only
   stale pages, edits what changed, and syncs the pages it verified.

Pick the automation level that matches your workflow.

| Where | Detects drift | Rewrites prose | Setup |
|---|---|---|---|
| Claude Code plugin | Stop hook after each turn; commit gate before each agent commit | `commit` (default) or `auto` runs the isolated update | Install the plugin |
| Any agent that reads `AGENTS.md` | The map block tells the agent to run `status`; pair it with pre-commit or CI | Ask the agent to run the Archlens update operation | `contextFile` |
| Git (any editor or agent) | `pre-push` hook | Developer or agent | pre-commit |
| CI | Pull request check | Optional agent job | Workflow below |

## Claude Code

The plugin hooks work after installation. Choose when stale pages are refreshed in
`.archlens.json` or your user preferences:

```json
{ "autoUpdate": "commit" }
```

| Mode | After each turn | When Claude runs `git commit` | Model tokens |
|---|---|---|---|
| `off` | Nothing | Nothing | None |
| `remind` | One message per new set of stale pages | Nothing | None |
| `commit` (default) | One message | Holds the commit once, runs the isolated update, then commits code and docs together | One update per commit that leaves pages stale |
| `auto` | Runs the isolated update | Same as `commit` | One update per turn that leaves pages stale |

In every mode except `off`, the hooks first rewrite line links whose cited code only moved (`fixAnchors`).
`commit` is the best default for most work: code that changes over several turns is
documented once, when it is done, and the docs ship in the same commit.
Use `auto` when you want pages rewritten as you go, and `remind` when you never want
the agent to spend tokens on docs without asking. Commits you make yourself in a terminal
are not held; the turn-end message and the `archlens-stale` pre-push hook still catch them.

A held commit tells the agent which pages are stale and how to finish. If the user said not to
touch documentation, the agent runs the same commit again and Archlens lets it through.
There is no need to add update instructions to `CLAUDE.md`: the hooks run deterministically
and cost no context until a page is actually stale.

## Other agents: Codex, Cursor, Copilot, Gemini CLI, OpenCode, and more

Set a context file and write it once:

```json
{ "contextFile": "AGENTS.md" }
```

```text
python <skill-dir>/scripts/archlens.py context --root . --write
```

The agent then sees the page map in every session. Every `sync` refreshes the block.
The block has no stale flags, because freshness changes between commits. It tells the
agent to run the Archlens `status` check before relying on a page, and to update stale
pages before it commits code, in the same commit. If you also use Claude Code with `CLAUDE.md` containing `@AGENTS.md`,
the plugin skips its own session map to avoid duplication.

## Git hooks with pre-commit

Add Archlens to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/tushar-mahalya/archlens
    rev: v0.3.0
    hooks:
      - id: archlens-check
      - id: archlens-stale
```

`archlens-check` runs on every commit and fails on structural errors.
`archlens-stale` runs on `pre-push` and fails while covered source changed
after the last sync. Install both stages with `pre-commit install --hook-type pre-commit --hook-type pre-push`.

## CI

This GitHub Actions job fails a pull request whose code changes leave pages stale.
Copy `archlens.py` into your repository first, for example as `tools/archlens.py`, or
check out this repository in the job.

```yaml
name: architecture-docs
on: pull_request
permissions:
  contents: read
jobs:
  freshness:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.13"
      - run: python tools/archlens.py check --root . --summary
      - run: python tools/archlens.py status --root . --fail-on-stale
```

To rewrite stale pages in CI, run your coding agent's headless mode with the
Archlens update operation, and open a pull request for human review.
Never let an automated job mark pages `reviewed` or decisions `accepted`.

## Limits

- A stale flag means "review this page". It does not prove the prose is wrong.
- Files outside a page's `covers` patterns and links are not tracked for that page.
- `sync` trusts the caller. Sync only pages that someone checked against current source.
