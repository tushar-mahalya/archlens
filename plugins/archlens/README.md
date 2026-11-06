# Archlens

Create and maintain architecture documents that explain execution, data flow, and design decisions.
Use Mermaid diagrams, source evidence, and concise STE-inspired prose.
This plugin does not claim formal ASD-STE100 compliance.

Commands: `/archlens:setup`, `/archlens:update`, `/archlens:check`,
`/archlens:explain`, and `/archlens:decide`.
All commands are explicit and use isolated task context.
There are no automatic hooks, MCP servers, or additional API credentials.
Python 3.10+ enables optional local checks; it is not required for the skills.

Install inside Claude Code:

```text
/plugin marketplace add tushar-mahalya/archlens
/plugin install archlens@archlens
```

The commands load references only when needed and return a bounded summary.
Normal Claude Code permissions and usage charges apply.
See the [project documentation](https://github.com/tushar-mahalya/archlens).
