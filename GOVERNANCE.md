# Governance

## Roles

| Role | Who | Responsibilities |
| --- | --- | --- |
| Maintainer | [@tushar-mahalya](https://github.com/tushar-mahalya) | Sets direction, reviews and merges pull requests, publishes releases, enforces the [Code of Conduct](CODE_OF_CONDUCT.md). |
| Contributor | Anyone | Opens issues, discussions, and pull requests under [CONTRIBUTING.md](CONTRIBUTING.md). |

The maintainer listed in [CODEOWNERS](.github/CODEOWNERS) reviews every change to `main`.

## Decisions

- Small changes are decided in the pull request.
- Changes to workflows, loaded instructions, distribution, or the documentation contract need an issue or discussion first.
  Record significant decisions as an ADR in [docs/architecture/decisions](docs/architecture/decisions).
- The maintainer makes the final decision when consensus is not reached and records the reason.

## Becoming a maintainer

Contributors with a sustained record of high-quality reviews and pull requests may be invited.
New maintainers are added to CODEOWNERS and this file in a pull request.

## Repository protection

`main` and release tags are protected by repository rulesets. Their definitions are versioned in
[.github/rulesets](.github/rulesets). See [CONTRIBUTING.md](CONTRIBUTING.md#repository-rulesets) for how to apply them.
