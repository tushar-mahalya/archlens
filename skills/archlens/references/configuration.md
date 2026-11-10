# Configuration contract

These settings belong to Archlens, not to the agent host.
They load only when a command runs. They do not schedule tasks or override permissions.

## Resolve the project and preferences

Use the selected project's Git root. Outside Git, use the explicitly selected folder.
If several projects are possible, ask which one to use.
Read these JSON objects, in order:

1. The bundled `defaults.json` in the installed Archlens directory.
2. One user preference file, selected in this order:
   - Use the file named by `ARCHLENS_CONFIG`, if set.
   - Otherwise use `archlens.json` in `CLAUDE_CONFIG_DIR`, if set.
   - Otherwise use `archlens/config.json` under `XDG_CONFIG_HOME`, or
     `~/.config/archlens/config.json` if `XDG_CONFIG_HOME` is not set, when that file exists.
   - Otherwise use the legacy `~/.claude/archlens.json`.
3. `.archlens.json` at the project root.

Later keys replace earlier keys. Missing default user/project files are normal.
An explicit `ARCHLENS_CONFIG` file must exist.
Reject malformed JSON, duplicate keys, unknown keys, and invalid values.
Do not hide errors behind defaults.
If Python 3.9+ exists, `scripts/archlens.py config --root <project> --json`
returns validated effective preferences. Run it from the installed bundle's absolute path.
Use the available Python 3.9+ command for your platform.

| Key | Allowed values | Default |
|---|---|---|
| `docsRoot` | Relative path inside the project, no parent traversal | `docs/architecture` |
| `styleTarget` | Number from 0 to 1 | `0.8` |
| `maxDiagramNodes` | Integer from 2 to 30 | `12` |
| `maxSequenceParticipants` | Integer from 2 to 15 | `7` |
| `contextBudget` | Integer from 600 to 20000 bytes | `3000` |
| `contextFile` | `null` or a project-relative Markdown file, such as `AGENTS.md` | `null` |
| `sessionContext` | `true` or `false`: Claude plugin loads the map at session start | `true` |
| `fixAnchors` | `true` or `false`: stop hook rewrites line links whose code only moved | `true` |
| `filePointers` | `true` or `false`: Claude plugin names the page for a file the agent opens | `true` |
| `autoUpdate` | `off`, `remind`, `commit`, or `auto`: when Claude refreshes stale pages | `commit` |

Use either slash style in JSON paths. Normalize for the host OS.
Resolve symlinks before access. Do not read or write through paths outside the project.
If an existing handbook uses another layout, reuse it or ask before moving it.
An empty project config `{}` opts the project in with the effective defaults.
Setup is also an explicit opt-in. Installation alone does not create project files.

## Document map

Store `map.json` in the configured document root. This is the machine-readable metadata.
Do not duplicate it in page frontmatter. Prose may show additional review context.

```json
{
  "version": 1,
  "pages": [
    {
      "path": "runtime/submit-order.md",
      "id": "FLOW-001",
      "kind": "runtime",
      "owner": "unknown",
      "reviewState": "draft",
      "verifiedCommit": null,
      "covers": ["src/orders/**", "tests/orders/**"]
    }
  ]
}
```

Replace the example paths with actual paths. Page paths are relative to the document root.
A path may start with `../` to map an existing document in place, such as `../ARCHITECTURE.md`.
It must stay inside the project. Only pages under the document root must all be mapped.
Coverage patterns are relative to the project root and use forward slashes:
`*` matches within one segment, `?` matches one non-slash character,
and a full `**` segment matches zero or more segments.
No brace expansion, character classes, negation, or backslash escaping is supported.
`src/**` covers everything below `src`; `**/*.py` includes root-level Python files.

Every Markdown page under the document root must appear once in the map.
Paths and IDs must be unique. At least one page must exist.
Use these `kind` values: `index`, `context`, `containers`, `component`, `runtime`,
`data`, `deployment`, `quality`, `glossary`, `decision`.
Use `reviewState`: `draft`, `reviewed`, or `needs-review`.
Only an authorized reviewer can establish `reviewed`.
Set `verifiedCommit` to a full commit ID only after verification against that clean source revision.
For working-tree evidence, leave it null and explain the reviewed state on the page.

Decision pages also require `decisionStatus`: `proposed`, `accepted`, `rejected`,
`deprecated`, or `superseded`. Evidence basis is prose, not a lifecycle state.
The map checker validates structure, not the truth of review or approval claims.

## Freshness and agent context

`sync` stores Git-compatible content IDs of each page's covered and linked files in
`.archlens-state.json` beside `map.json`. Commit it with the handbook.
`sync` also fingerprints cited line ranges: the enclosing function or class in Python and
C-family languages (JavaScript, TypeScript, Go, Rust, Java, C#, and others), else the text.
Comments and formatting do not count. A range inside a function tracks only its own lines.
`status` reports `stale` when cited evidence changed or moved, and `review` when only
other covered files changed. A whole-file link to code goes stale when the file's
declared names change; body edits mark it for review. Committed changes also count.
Sync a page only after you verify it against current source.
If the state file has a merge conflict, take either side and sync the reviewed pages again.

`context` prints a compact map of pages, summaries, coverage, and stale flags,
limited to `contextBudget` bytes. With `contextFile`, sync also replaces the
managed `archlens:context` block in that file. Do not edit inside the block.

An impact report includes all changed files, candidate pages, and uncovered files.
It does not prove that the handbook is complete or that a mapped page is stale.
