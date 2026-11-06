# Configuration

Preferences load in this order:

1. [Bundled defaults](../plugins/archlens/defaults.json).
2. `ARCHLENS_CONFIG`, if set; otherwise `archlens.json` under `CLAUDE_CONFIG_DIR` or `~/.claude`.
3. `.archlens.json` in the selected project root.

Later keys replace earlier keys. These are Archlens preferences, not Claude Code settings.
An explicitly named config file must exist.
Default optional files may be absent.
Unknown keys, duplicate keys, invalid types, and malformed JSON are errors.

| Key | Default | Meaning |
|---|---|---|
| `docsRoot` | `docs/architecture` | Relative handbook directory inside the project |
| `styleTarget` | `0.8` | Target for a declared human or agent style audit |
| `maxDiagramNodes` | `12` | Soft authoring limit for a flowchart |
| `maxSequenceParticipants` | `7` | Soft sequence limit; checker counts explicit declarations |

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
