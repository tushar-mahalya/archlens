<!--
PR title = the squash commit on main. Use Conventional Commits, 72 characters or fewer:
  type(scope)!: imperative subject      e.g. "fix(checker): reject links that escape the root"
Types and scopes: see CONTRIBUTING.md#commit-and-pull-request-conventions
-->

## Summary

<!-- What changes, in one to three sentences. -->

## Why

<!-- The problem or motivation. Link the issue or discussion: "Closes #12", "Refs #34". -->

## Type of change

- [ ] `fix` - bug fix
- [ ] `feat` - new feature or behavior
- [ ] `docs` - documentation only
- [ ] `refactor` / `perf` / `test` - no user-facing behavior change
- [ ] `build` / `ci` / `chore` - tooling, dependencies, or maintenance

## How tested

<!-- Commands you ran and what you checked by hand, such as an agent host and version. -->

## Checklist

- [ ] The PR title follows [Conventional Commits](https://www.conventionalcommits.org/) and the [project conventions](https://github.com/tushar-mahalya/archlens/blob/main/CONTRIBUTING.md#commit-and-pull-request-conventions).
- [ ] `pre-commit run --all-files` passes.
- [ ] `python -m unittest discover -s tests` passes.
- [ ] If I changed native plugin resources, I ran `python tools/sync_portable.py` and committed the generated portable files.
- [ ] If I changed instructions, `python tools/prompt_budget.py` passes and the documented budgets are current.
- [ ] Handbook freshness passes: `python plugins/archlens/scripts/archlens.py status --root . --fail-on-stale`.
- [ ] I updated user documentation and the `Unreleased` section of `CHANGELOG.md` where relevant.
- [ ] I did not include secrets, credentials, private source code, or customer data.

## Breaking changes

<!-- "None", or what breaks and how users migrate. Mark the title with "!", for example
"feat(checker)!: ...". The squash commit gets a "BREAKING CHANGE:" footer with this text. -->

None

## Context-cost impact

<!-- Does this add or grow loaded instructions, hooks, automatic commands, MCP servers,
or dependencies? If yes, give the prompt-budget change and explain why it is worth it. -->

None
