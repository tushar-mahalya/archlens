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
python plugins/archlens/scripts/archlens.py cite --root <project> src/orders.py submit_order --from docs/architecture/runtime/submit.md
python plugins/archlens/scripts/archlens.py query --root <project> retry limit
python plugins/archlens/scripts/archlens.py precommit --root <project>
```

Replace angle-bracket arguments. Quote paths containing spaces.
The default root is the current folder.
For `impact`, root must be the exact Git root, not a nested project.
`check`, `config`, `status`, `sync`, `context`, `query`, and `precommit` also work in a nested folder or outside Git.

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
  Paths that Git ignores, extension-less names that never existed in Git history (such as the
  MCP method `tools/list`), and names in accepted or past decision records are not reported.
- Line ranges that cut off the first or last code line of a function or class by one or two lines,
  ignoring blank and comment lines (warning). These are almost always off-by-one citations.
- Missing titles, missing sequence numbering, and explicit participant counts (warning).
- Flowcharts with more nodes than `maxDiagramNodes` (`diagram-density`, warning). The node count is a heuristic.
- Step tables that do not match their diagram (`sequence-steps`). A table whose first column is "Step"
  belongs to the numbered sequence diagram before it. A step number above the diagram's message
  count is a warning. A message without a step row is a note.
- In an adopted document (a page mapped with `../`), presentation advice is a note, not a warning:
  titles, sequence numbering, and density. Archlens does not restyle documents it did not write.
- Placement (warning): a handbook decision record while the project keeps decisions in another
  mapped folder, such as `docs/adr/` (`decision-split`), and a handbook that no root Markdown
  file or mapped existing document links to, when the project has a `README.md` (`unlinked-handbook`).
- Handbook-owned pages only (info): commit IDs in prose, which duplicate `map.json` and the sync
  state (`prose-metadata`), and table columns that say unknown in every row (`unknown-column`).
- Mechanical style: one `style` note per page with counts and line numbers (info).
  The checker reads complete sentences in paragraphs, list items, and table cells. A sentence fails
  with more than 25 words (20 in a numbered procedure), a semicolon, a passive with "by", or a
  listed wordy phrase such as "in order to". Code spans and link targets do not count.
  Notes never fail `--strict`.
- `stylePassRate`: passing sentences divided by all sentences in handbook-owned pages, reported
  from 20 sentences up. `--style` fails the check when the rate is below `styleTarget`.
  This rate is a mechanical floor. It is not an STE score: the checker cannot judge actors,
  terminology, or ambiguity.

Findings are sorted by severity, then broken links and missing references before
presentation advice, so a `--summary` preview shows the most important records first.

Limits:

- Not a complete CommonMark parser. Complex nested syntax, reference-use resolution, and HTML links are outside scope.
- Does not check remote URLs, full Mermaid syntax, diagram layout, or source semantics.
- Does not validate that a human really approved a decision.
- Style notes and `stylePassRate` are mechanical, not an STE score or ASD-STE100 compliance.
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

A line-range link such as `orders.py#L40-L62` is an anchor. Archlens records the smallest
function or class around the range: by syntax tree in Python, and with a comment- and
string-aware brace reader in C-family files (`.js`, `.ts`, `.tsx`, `.go`, `.rs`, `.java`,
`.kt`, `.cs`, `.c`, `.cpp`, `.swift`, `.php`, `.dart`, and similar). Comments, blank lines,
and formatting do not count, and a moved function is reported with its new lines.
A range that is not exactly one function or class also records its own content lines, so an edit
elsewhere in that function does not flag it. Content lines leave out blank lines and comments, and
keep indentation where it has meaning (Python, YAML, plain text). The same fingerprint serves a
range that no single symbol holds: module-level code, several functions, or a file without symbol
support, such as YAML. Blank and comment lines at either end of a range do not decide which symbol
it belongs to, so `#L96-L110` still follows a function that ends on line 109.
`status` does not parse a cited file whose content is unchanged since the last sync.

Limits: a cited sub-range follows its own lines. A new condition wrapped around it is an edit
elsewhere in the function, so the citation moves and is not flagged; cite the whole function to
catch that. When identical code exists twice in a file, a deleted copy can report as moved.

A whole-file link to a code file goes `stale` when one of the file's declared names (a function,
class, or top-level constant) is removed or renamed, and `review` when names are only added or
only bodies change. Cite line ranges for claims about behavior, limits, and defaults.
A link to another document (`.md`, `.rst`, and similar) is a cross-reference: an edit marks the
page for `review`. A link to any other file goes `stale` when the file changes.
Deleting any linked file makes the page `stale`.
A page with no evidence links treats every covered change as `stale`.

`--fail-on-stale` exits 1 for stale or unsynced pages. `--fail-on-review` also fails on review pages.

### fix-anchors

Rewrites links to files that Git reports as renamed (in the working tree or since the page's
last sync), including exact-path `covers` entries in `map.json`. Then rewrites line links whose
cited code moved but did not change, and re-records those anchors.
For example, `orders.py#L20-L38` becomes `orders.py#L21-L39` after a line is added above.
It edits only the link fragments in handbook pages. Changed evidence still needs a person or agent.
The Claude stop hook runs it automatically when `fixAnchors` is true.

### cite

Prints link-ready line ranges for functions and classes in a source file, for Python and
C-family languages. Name symbols to cite (qualified, such as `Queue.push`, or bare), or
omit them to list the file's main symbols. `--from <page>` prints links relative to that page.
Exits 1 when a named symbol does not exist. Read-only.

```text
$ archlens.py cite --root . src/orders.py submit_order --from docs/architecture/runtime/submit.md
[submit_order](../../../src/orders.py#L20-L38)
```

### sync

Records the current content of each named page's covered files in `.archlens-state.json`.
Use `--page ID` (repeatable) after you review those pages, or `--all` after setup.
`--fresh` records every page that `status` reports fresh. No change is waiting on such a page,
so this approves nothing. Run it once after an upgrade to move fingerprints to the current format:
records from 0.4.0 still compare correctly, but they keep that version's false alarms until then.
It writes only the state file, plus the managed block in `contextFile` when configured.
Syncing a page you did not review hides real drift.

### context

Prints a compact, freshness-aware page map within `contextBudget` bytes.
Pages appear in reading order with their title, first sentence, coverage, and stale flag.
Index and glossary pages omit coverage, because their patterns span the project.
When page summaries do not all fit, a folder of four or more decision records becomes one line
that lists the records by file name. A stale decision keeps its own line.
The live map (not a written block) names the `query` command when the handbook has eight or more pages.
When the budget is tight, it keeps summaries before coverage, page by page in reading order,
and lists the remaining count only when titles alone do not fit.
A written block has no stale flags, because freshness changes between commits; it tells
the agent to run `status` instead.
`--write FILE` (or `--write` with `contextFile` set) replaces only the managed
`archlens:context` block in that file and keeps all other text.

### query

Finds the smallest part of the handbook that answers a need. It reads only mapped pages, uses no
model, and prints one line per section: `page:first-last  heading  (bytes)`. Open those lines
with your editor or the agent's file reader instead of the whole page.

| Form | Returns |
|---|---|
| `query <words>` | Sections ranked by word match (BM25). Headings count more. `RagService` also matches `rag` and `service` |
| `query --file <path>` | Sections that link to the file, with the cited line ranges, then pages that cover it without a link |
| `query --page <page>` | The page outline: every section with its line range, size, and diagram types |
| `query --page <page> <words>` | The same ranking, inside one page |
| `query --page <page> --diagram [N]` | Diagram N (default 1) as Mermaid source, plus a following "Text equivalent:" paragraph |
| `query --page <page> --step <n>` | The step-table rows for message `n` of a numbered sequence diagram |
| `query --page <page> --row <text>` | Table rows whose first cell contains the text, such as a unit name |

`<page>` is a map ID, a map path, a project path, or a unique file name. `--limit` sets the number
of ranked sections (default 5). A result from a stale or never-synced page ends with `STALE` or `UNSYNCED`.
Text output stops at 6,000 bytes. `--json` and `--summary` work as for other commands.

This design uses a diagram as an index. Read the diagram first, because it is the shortest complete
view of a flow. Then ask for one step or one unit, and follow that row's source links.

Limits: word match only, with light stemming. It knows no synonyms. Section boundaries are
headings. On a small handbook, reading a whole page costs little more; see [benchmarks](benchmarks.md).

### precommit

One deterministic gate for a commit. It needs no model and no network. It runs three steps:

1. Rewrites line links whose cited code only moved, and links to renamed files (`fixAnchors`).
   If it changed a page, it fails once so that you stage the rewrite and commit again.
2. Runs `check` and fails on errors. With `--style`, it also fails below `styleTarget`.
3. Fails when a staged file changes code that a page cites, or when a staged page was never synced.

A page that was already stale for another reason does not block the commit. The report counts
those pages in a note. With nothing staged, such as a CI run, every stale page counts.

`--stale warn` reports step 3 without failing. `--stale off` skips it.
To pass step 3, check the page against the change and edit the page if needed. Then run
`sync --page <ID>` and stage the page and `.archlens-state.json`. A coding agent can do this
with the Archlens update operation.

Limits: the gate reads the working tree. The pre-commit framework stashes unstaged changes first,
so the two match. A plain Git hook sees unstaged edits too.

### hook

`hook session-start`, `hook file-pointer`, `hook stop`, and `hook commit-gate` are the Claude Code plugin hooks.
The plugin starts them through `scripts/hook.py`. That entry exits in a few milliseconds when the
command is not a commit or the project has no handbook, and loads the checker as a cached module otherwise.
The pointer hook keeps a small index of each page's links in the plugin data folder until a page changes.
`commit-gate` runs before each Bash call. It exits at once unless the command is a `git commit`,
and with `autoUpdate` set to `commit` or `auto` it holds a commit once while it would leave pages stale.
They read hook JSON on standard input, print nothing outside an Archlens project, and always exit 0.
`file-pointer` names the page that documents a file the agent read or edited, once per page per session.
When the page cites the file, the pointer names up to two citing sections with their line ranges.

## Output and exits

- No output flag: human-readable report.
- `--json`: complete machine-readable report.
- `--summary`: valid JSON of at most 6,000 UTF-8 bytes, excluding its final newline.
  Includes totals, whole preview records, and exact omission counts.
  `check` previews errors first, then warnings, then style notes.

| Exit | Meaning |
|---|---|
| `0` | Check passed, or report generated successfully |
| `1` | Structural findings, strict warnings, a requested impact, stale, or style gate, a failed `precommit`, or a missing `cite` symbol |
| `2` | Invalid input, config, map, Git failure, or file-access error |

By default, warnings do not fail `check`, and review candidates do not fail `impact`.
Use `--strict` or `--fail-on-impact` to request those gates.
`ok` describes the selected exit policy. It does not certify architecture accuracy.

Save large reports to a local file, then query relevant records.
Do not paste complete large reports into an agent conversation.
