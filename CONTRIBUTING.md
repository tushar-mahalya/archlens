# Contributing

Thank you for helping improve Archlens. By taking part, you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md). For questions, use
[Discussions](https://github.com/tushar-mahalya/archlens/discussions) and see [SUPPORT.md](SUPPORT.md).

## Workflow

1. For a non-trivial change, open an issue or discussion first. See [GOVERNANCE.md](GOVERNANCE.md).
2. Fork the repository and create a branch from `main`, for example `fix/config-precedence`.
3. Install the Git hooks (below) and make focused commits.
4. Use [Conventional Commits](https://www.conventionalcommits.org/) for commit messages and the PR title:
   `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `perf:`, `build:`, `ci:`, `chore:`, or `revert:`.
5. Open a pull request and complete the template. A code owner review and the `CI passed` check are required.
6. Pull requests are merged by squash or rebase. `main` keeps a linear history.

## Git hooks

The repository uses [pre-commit](https://pre-commit.com/). Hooks check formatting, line endings,
JSON and YAML, GitHub workflows, secrets (gitleaks), commit messages, portable-skill drift, prompt
budgets, and the handbooks. Unit tests run before each push.

```text
pipx install pre-commit        # or: uv tool install pre-commit, or: pip install pre-commit
pre-commit install             # installs pre-commit, commit-msg, and pre-push hooks
pre-commit run --all-files     # optional: check the whole tree
```

CI runs the same hooks, so a skipped hook still fails the pull request.
Update hook versions with `pre-commit autoupdate --freeze`. Dependabot also proposes updates.

## Tests

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

For diagram and portable installer checks, use Node 22.20+:

```text
npm ci
npm run test:diagrams
npm run test:skills
```

Set `DISABLE_TELEMETRY=1` and `DO_NOT_TRACK=1` for isolated installer tests.
The tests use temporary project and home directories, not your personal agent settings.
Node dependencies are development-only for the plugin. The portable installer's
own CLI separately requires Node.

## Portable skill

The native Claude plugin is the source of truth for shared references, defaults,
the checker, and the five workflows. After changing one of those resources, run:

```text
python tools/sync_portable.py
python tools/sync_portable.py --check
python tools/prompt_budget.py
```

Commit the generated files under `skills/archlens` with the source changes.
Do not edit generated workflows or bundled resources independently.
Edit the portable router `skills/archlens/SKILL.md` directly when its routing changes.
The generator reports unexpected generated files instead of deleting them.

## Changes

- Keep command prompts small. Run the budget test after instruction changes.
- Add regression tests for config, path, report, or Git behavior.
- Do not add a custom YAML parser.
- Do not label heuristics as official STE compliance.
- Keep evidence-based claims separate from inference.
- Do not add hooks, MCP servers, nested agents, or automatic commands without a context-cost review.
- Update the relevant reference and user documentation.

## Release

1. Update the plugin, marketplace metadata, and development package versions together.
2. Add release notes.
3. Pass CI and review the [evaluation plan](docs/context-efficiency.md).
4. Run the package tool. It creates a deterministic, allowlisted ZIP and SHA-256 checksum.
5. Publish the release from a tested commit.

The release archive includes the marketplace, plugin, portable skill, docs, example, tests, and development scripts.
It excludes installed dependencies, temporary tools, and local configuration.

Release tags (`v*`) are protected: they cannot be moved or deleted after publication.
Publish a new patch version instead of replacing a release.

## Repository rulesets

Branch and tag protection is defined as code in [.github/rulesets](.github/rulesets):

- `main.json` protects the default branch. It blocks deletion and force pushes, requires linear
  history, a pull request with one code owner approval, resolved review threads, and the `CI passed` check.
  Repository administrators can bypass these rules only through a pull request.
- `release-tags.json` blocks moving or deleting `v*` tags. Administrators can bypass it for recovery.

A maintainer applies a changed definition with the GitHub CLI:

```text
gh api repos/tushar-mahalya/archlens/rulesets --method POST --input .github/rulesets/main.json
gh api repos/tushar-mahalya/archlens/rulesets/<id> --method PUT --input .github/rulesets/main.json
```

Use `POST` for a new ruleset and `PUT` with the existing ID (`gh api repos/tushar-mahalya/archlens/rulesets`) to update one.
