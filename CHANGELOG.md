# Changelog

## Unreleased

- Add a Code of Conduct, support and governance guides, issue and pull request templates, and CODEOWNERS.
- Add pre-commit hooks for formatting, secrets, workflows, commit messages, portable-skill drift, prompt budgets, and handbooks. CI runs them too.
- Add versioned rulesets for `main` and release tags, a single `CI passed` required check, Dependabot, and OpenSSF Scorecard.
- Include community files in release archives.

## 0.2.0 - 2026-11-06

- Add one portable Agent Skill for setup, update, check, explanation, and decisions.
- Generate its resources from the native Claude plugin and check for distribution drift.
- Support a shared cross-agent user configuration with the existing Claude location as a fallback.
- Test isolated project and global installations with ten skills CLI adapters.
- Add portable prompt budgets and include the skill in release archives.

Portable host discovery, context isolation, and model behavior vary by agent.
Installer tests do not establish end-to-end model reliability.

## 0.1.1 - 2026-11-06

- Include the MIT notice inside the plugin so it remains present when the host copies only that directory.
- Add distribution tests for the installed license and release archive.

## 0.1.0 - 2026-11-06

- Five manual Claude Code commands for setup, update, check, explanation, and decisions.
- User and project preferences, evidence rules, and a JSON document map.
- Optional dependency-free Python checks and Git change-impact reports.
- Bounded summaries, conditional prompt loading, and prompt-size regression tests.
- Working order example with a six-page handbook.
- Cross-platform tests, Mermaid rendering checks, and reproducible release packaging.

Limits: model-task token savings and semantic output quality have not been benchmarked.
The checker does not certify STE compliance or prove architecture accuracy.
