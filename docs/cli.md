# Optional checker CLI

Requires Python 3.9+. No packages are required.
Run `plugins/archlens/scripts/archlens.py` from a clone or an extracted release.
The installed skills locate this script through the plugin root.

## Commands

```text
python plugins/archlens/scripts/archlens.py config --root <project> --json
python plugins/archlens/scripts/archlens.py check --root <project> --strict
python plugins/archlens/scripts/archlens.py impact --root <project> --base <local-ref> --fail-on-impact
python plugins/archlens/scripts/archlens.py status --root <project> --fail-on-stale
python plugins/archlens/scripts/archlens.py sync --root <project> --page FLOW-001 --page DATA
python plugins/archlens/scripts/archlens.py context --root <project> --write AGENTS.md
python plugins/archlens/scripts/archlens.py fix-anchors --root <project>
```

Replace angle-bracket arguments. Quote paths containing spaces.
The default root is the current folder.
For `impact`, root must be the exact Git root, not a nested project.
`check`, `config`, `status`, `sync`, and `context` also work in a nested folder or outside Git.

### config

Validates and prints effective preferences and their sources.
It does not create or modify any file.

### check

Checks:

- Map schema, IDs, page kinds, review states, decision states, and coverage patterns.
- Missing mapped pages and unmapped Markdown pages.
- Local inline link targets and reference definitions.
- Unclosed fences or metadata blocks and empty Mermaid blocks.
- Heading anchors (`page.md#section`, warning) and line anchors past the end of a file (`#L120`, error).
- Unknown Mermaid diagram types, such as a misspelled `flowchat`.
- Backticked prose references that no longer exist: paths with a slash, `name()` symbols, and `npm run` scripts (warning).
- Missing titles, semicolons, long prose lines, missing sequence numbering, and explicit participant counts.

Limits:

- Not a complete CommonMark parser. Complex nested syntax, reference-use resolution, and HTML links are outside scope.
- Does not check remote URLs, full Mermaid syntax, diagram layout, or source semantics.
- Does not validate that a human really approved a decision.
- Writing warnings are editorial candidates, not an STE score.
- Expects ordinary UTF-8 Markdown; frontmatter is skipped, not parsed.

### impact

With `--base`, compares the merge base of the local ref and HEAD to HEAD.
It also includes staged, unstaged, and untracked non-ignored files.
Without `--base`, it considers only working-tree changes.
An unborn repository supports working-tree mode.

Reports both sides of renames as changed paths.
Includes deleted files. Does not fetch, execute diffs, or mutate the repository.
Ignores documentation-root changes and `.archlens.json` only when selecting source candidates.
All changed files still appear in the full report.

Matched pages remain candidates even if those pages also changed.
Uncovered files need triage; they are not necessarily architecture changes.
The tool does not discover indirect dependencies or enforce periodic reviews.

### status

Reports each page as `fresh`, `stale`, `review`, or `unsynced`.
A page covers files that match its `covers` patterns, plus project files and folders it links to.
`sync` records Git-compatible content IDs of those files and fingerprints of cited line ranges.
Committed, staged, unstaged, and untracked changes all count, without a base ref.

| State | Meaning |
|---|---|
| `stale` | Evidence the page cites changed: a linked file, a Python function or class, or a cited line range |
| `review` | Only other covered files changed. The page may still be right |
| `unsynced` | The page has no recorded baseline yet |

A line-range link such as `orders.py#L40-L62` is an anchor. In a Python file, Archlens
records the smallest function or class around the range and compares its syntax tree,
so comments, blank lines, and formatting do not count, and a moved function is reported
with its new lines. In other files it compares the normalized text and searches for moved text.
A page with no evidence links treats every covered change as `stale`.

`--fail-on-stale` exits 1 for stale or unsynced pages. `--fail-on-review` also fails on review pages.

### fix-anchors

Rewrites line links whose cited code moved but did not change, then re-records those anchors.
For example, `orders.py#L20-L38` becomes `orders.py#L21-L39` after a line is added above.
It edits only the link fragments in handbook pages. Changed evidence still needs a person or agent.
The Claude stop hook runs it automatically when `fixAnchors` is true.

### sync

Records the current content of each named page's covered files in `.archlens-state.json`.
Use `--page ID` (repeatable) after you review those pages, or `--all` after setup.
It writes only the state file, plus the managed block in `contextFile` when configured.
Syncing a page you did not review hides real drift.

### context

Prints a compact, freshness-aware page map within `contextBudget` bytes.
Pages appear in reading order with their title, first sentence, coverage, and stale flag.
When the budget is tight, it drops summaries, then coverage, then lists the remaining count.
A written block has no stale flags, because freshness changes between commits; it tells
the agent to run `status` instead.
`--write FILE` (or `--write` with `contextFile` set) replaces only the managed
`archlens:context` block in that file and keeps all other text.

### hook

`hook session-start`, `hook file-pointer`, and `hook stop` are the Claude Code plugin hooks.
They read hook JSON on standard input, print nothing outside an Archlens project, and always exit 0.
`file-pointer` names the page that documents a file the agent read or edited, once per page per session.

## Output and exits

- No output flag: human-readable report.
- `--json`: complete machine-readable report.
- `--summary`: valid JSON of at most 6,000 UTF-8 bytes, excluding its final newline.
  Includes totals, whole preview records, and exact omission counts.
  Preview order follows report order, not a severity ranking.

| Exit | Meaning |
|---|---|
| `0` | Check passed, or report generated successfully |
| `1` | Structural findings, strict warnings, or a requested impact or stale gate |
| `2` | Invalid input, config, map, Git failure, or file-access error |

By default, warnings do not fail `check`, and review candidates do not fail `impact`.
Use `--strict` or `--fail-on-impact` to request those gates.
`ok` describes the selected exit policy. It does not certify architecture accuracy.

Save large reports to a local file, then query relevant records.
Do not paste complete large reports into an agent conversation.
