# Archlens

Architecture documents that stay in sync with your code, give coding agents a
compact map of the project, and help you learn the codebase while you work.
Mermaid diagrams, source evidence, decision records, and plain STE-inspired prose.
This plugin does not claim formal ASD-STE100 compliance.

Commands: `/archlens:setup`, `/archlens:update`, `/archlens:check`,
`/archlens:explain`, `/archlens:decide`, and `/archlens:learn`.
Five commands run in an isolated task. `learn` runs inline for follow-up questions.
Only `update` can be chosen by the model, and it also runs isolated.

Two hooks run the bundled Python script. In a project with an Archlens handbook,
the session-start hook loads a compact page map (3,000 bytes at most by default).
The stop hook reminds you once when your edits make pages stale.
In other projects, both hooks print nothing. There are no MCP servers or API credentials.
The hooks and checks need Python 3.9+ as `python3` on `PATH`; the skills work without it.

Install inside Claude Code:

```text
/plugin marketplace add tushar-mahalya/archlens
/plugin install archlens@archlens
```

Normal Claude Code permissions and usage charges apply.
See the [project documentation](https://github.com/tushar-mahalya/archlens).
