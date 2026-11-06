# Optional checker CLI

Requires Python 3.10+. No packages are required.
Run `plugins/archlens/scripts/archlens.py` from a clone or an extracted release.
The installed skills locate this script through the plugin root.

## Commands

```text
python plugins/archlens/scripts/archlens.py config --root <project> --json
python plugins/archlens/scripts/archlens.py check --root <project> --strict
python plugins/archlens/scripts/archlens.py impact --root <project> --base <local-ref> --fail-on-impact
```

Replace angle-bracket arguments. Quote paths containing spaces.
The default root is the current folder.
For `impact`, root must be the exact Git root, not a nested project.
`check` and `config` also work outside Git.

### config

Validates and prints effective preferences and their sources.
It does not create or modify any file.

### check

Checks:

- Map schema, IDs, page kinds, review states, decision states, and coverage patterns.
- Missing mapped pages and unmapped Markdown pages.
- Local inline link targets and reference definitions.
- Unclosed fences or metadata blocks and empty Mermaid blocks.
- Missing titles, semicolons, long prose lines, missing sequence numbering, and explicit participant counts.

Limits:

- Not a complete CommonMark parser. Complex nested syntax, reference-use resolution, and HTML links are outside scope.
- Does not check anchors, remote URLs, Mermaid syntax, diagram layout, or source semantics.
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

## Output and exits

- No output flag: human-readable report.
- `--json`: complete machine-readable report.
- `--summary`: valid JSON of at most 6,000 UTF-8 bytes, excluding its final newline.
  Includes totals, whole preview records, and exact omission counts.
  Preview order follows report order, not a severity ranking.

| Exit | Meaning |
|---|---|
| `0` | Check passed, or report generated successfully |
| `1` | Structural findings, strict warnings, or requested impact gate |
| `2` | Invalid input, config, map, Git failure, or file-access error |

By default, warnings do not fail `check`, and review candidates do not fail `impact`.
Use `--strict` or `--fail-on-impact` to request those gates.
`ok` describes the selected exit policy. It does not certify architecture accuracy.

Save large reports to a local file, then query relevant records.
Do not paste complete large reports into an agent conversation.
