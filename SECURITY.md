# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.2.x (latest release) | Yes |
| Earlier releases | No. Upgrade to the latest release. |

## Report a vulnerability

Report privately through [GitHub private vulnerability reporting](https://github.com/tushar-mahalya/archlens/security/advisories/new).
Include the affected version, distribution (plugin, portable skill, or checker), steps to reproduce, and impact.
Do not post exploit details, credentials, or private repository content in a public issue or discussion.

What to expect:

- Acknowledgement within 7 days.
- An initial assessment within 14 days.
- A fix, advisory, and credit (if you want it) for confirmed issues. Coordinated disclosure after a fix is released.

These are goals of a volunteer project, not contractual commitments.

## Scope and design

Archlens adds instructions and an optional read-only local checker.
It has no telemetry, remote renderer, automatic hook, or permission bypass.
Your coding agent still processes selected content under its normal provider policy.

Review generated documents before publication. Source links and diagrams can disclose internal design.
Do not include credentials, private customer data, or sensitive configuration values.
The sample is fictional.

The checker rejects configured paths and local links that escape the project.
These checks do not turn an agent or the local filesystem into a sandbox.
Keep normal permission prompts and organizational policies in place.

## Repository safeguards

- Secret scanning and push protection are enabled.
- Dependabot security and version updates cover GitHub Actions, npm, and pre-commit hooks.
- CodeQL code scanning and OpenSSF Scorecard run on the default branch.
- Workflow actions are pinned to full commit SHAs and use least-privilege permissions.
