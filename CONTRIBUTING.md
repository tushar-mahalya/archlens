# Contributing

Use Python 3.10+ for tests. The runtime checker uses only the standard library.

```text
python -m unittest discover -s tests -v
python tools/prompt_budget.py
python plugins/archlens/scripts/archlens.py check --root examples/order-service --strict
python plugins/archlens/scripts/archlens.py check --root . --strict
python tools/package_release.py
```

If Claude Code is available:

```text
claude plugin validate . --strict
claude plugin validate ./plugins/archlens --strict
```

For diagram checks, use Node 22.13+:

```text
npm ci
npm run test:diagrams
```

Node dependencies are development-only. They must not become requirements for plugin users.

## Changes

- Keep command prompts small. Run the budget test after instruction changes.
- Add regression tests for config, path, report, or Git behavior.
- Do not add a custom YAML parser.
- Do not label heuristics as official STE compliance.
- Keep evidence-based claims separate from inference.
- Do not add hooks, MCP servers, nested agents, or automatic commands without a context-cost review.
- Update the relevant reference and user documentation.

## Release

1. Update the plugin version and marketplace metadata version together.
2. Add release notes.
3. Pass CI and review the [evaluation plan](docs/context-efficiency.md).
4. Run the package tool. It creates a deterministic, allowlisted ZIP and SHA-256 checksum.
5. Publish the release from a tested commit.

The release archive includes the marketplace, plugin, docs, example, tests, and development scripts.
It excludes installed dependencies, temporary tools, and local configuration.
