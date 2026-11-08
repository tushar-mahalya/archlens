# Configuration

Preferences load in this order:

1. [Bundled defaults](../plugins/archlens/defaults.json).
2. One user preference file, selected in this order:
   - The file named by `ARCHLENS_CONFIG`, if set.
   - Otherwise, `archlens.json` under `CLAUDE_CONFIG_DIR`, if set.
   - Otherwise, `archlens/config.json` under `XDG_CONFIG_HOME`, or
     `~/.config/archlens/config.json` when `XDG_CONFIG_HOME` is not set, if that file exists.
   - Otherwise, the legacy `~/.claude/archlens.json`.
3. `.archlens.json` in the selected project root.

Later keys replace earlier keys. Only one user file is read; the files are not merged.
These are Archlens preferences, not agent-host settings.
An explicitly named config file must exist.
Default optional files may be absent.
Unknown keys, duplicate keys, invalid types, and malformed JSON are errors.

On Windows, `~` refers to your user home directory. For example, the shared
default is `C:\Users\you\.config\archlens\config.json` unless `XDG_CONFIG_HOME`
is set. If `CLAUDE_CONFIG_DIR` is set, its file takes precedence even when absent;
clear it or set `ARCHLENS_CONFIG` explicitly to choose another file.

| Key | Default | Meaning |
|---|---|---|
| `docsRoot` | `docs/architecture` | Relative handbook directory inside the project |
| `styleTarget` | `0.8` | Target for a declared human or agent style audit |
| `maxDiagramNodes` | `12` | Soft authoring limit for a flowchart |
| `maxSequenceParticipants` | `7` | Soft sequence limit; checker counts explicit declarations |
| `contextBudget` | `3000` | Maximum bytes of the page map given to agents (600 to 20000) |
| `contextFile` | `null` | Agent instruction file, such as `AGENTS.md`, that receives the managed map block |
| `sessionContext` | `true` | Claude plugin: load the map at session start |
| `fixAnchors` | `true` | Claude plugin stop hook: rewrite line links whose cited code only moved |
| `filePointers` | `true` | Claude plugin: when the agent reads or edits a documented file, name its page once per session |
| `autoUpdate` | `remind` | Claude plugin stop hook: `off`, `remind` (one message), or `auto` (ask the agent to run update) |

The checker does not calculate the style score or count implicit flowchart nodes.
These limits guide authors; they are not universal readability thresholds.

Example:

```json
{
  "docsRoot": "engineering/architecture",
  "maxSequenceParticipants": 6
}
```

Use forward slashes or escaped backslashes in JSON paths.
Absolute paths, parent traversal, and symlinks outside the project are rejected.
No preference overrides repository instructions or permission policy.

## Map existing documents

Place `map.json` in your document root.
Every Markdown page there needs one entry.
Use [the configuration contract](../plugins/archlens/references/configuration.md) for all fields and glob semantics.
See the [sample map](../examples/order-service/docs/architecture/map.json).

The map uses JSON so the optional checker needs no YAML parser.
Keep approval provenance on the page. The map stores review state, not proof of approval.
Do not set `verifiedCommit` merely because a document changed.

Coverage patterns select review candidates. They do not model all dependencies.
Always review indirect consumers when an interface or data contract changes.

## Keep agents informed

The Claude plugin loads the map at session start. It skips this if `CLAUDE.md`
already contains the block, or imports the configured `contextFile` with `@AGENTS.md`.
For Codex, Cursor, Copilot, Gemini CLI, and other agents that read `AGENTS.md`:

```json
{ "contextFile": "AGENTS.md" }
```

Then run `context --write` once. Every later `sync` refreshes the block.
Use `autoUpdate: "auto"` only if you accept an extra isolated update task after
turns that change documented code. See [automation](automation.md).
