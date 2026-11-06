# Understand Archlens

Archlens provides a Claude Code plugin, a portable Agent Skill, and an optional local checker.
Claude Code runs five explicit plugin commands in isolated task contexts.
The portable skill routes the same operations in other hosts. Isolation depends on the host.
The checker reads local files and Git state without calling a model.

## Context and main units

```mermaid
flowchart LR
    U["User"] -->|"Architecture request"| C["Coding-agent host"]
    C -->|"Native command or portable skill"| S["Archlens workflow"]
    S -->|"Conditional reads"| R["Shared references"]
    S -->|"Inspect and document"| P["User project"]
    S -->|"Optional local command"| K["Python checker"]
    K -->|"Read files and Git state"| P
    S -->|"Short result"| U
```

The coding agent and the user's project are outside Archlens's implementation boundary.
The skill is instructions, not a separate security sandbox.
There is no Archlens server or database.

| Unit | Responsibility | Source |
|---|---|---|
| Marketplace | Locate the installable plugin | [Catalog](../../.claude-plugin/marketplace.json) |
| Plugin manifest | Name, version, and distribution metadata | [Manifest](../../plugins/archlens/.claude-plugin/plugin.json) |
| Native skills | Select one isolated Claude workflow | [Commands](../../plugins/archlens/skills) |
| Portable skill | Route one operation for compatible hosts | [Portable skill](../../skills/archlens/SKILL.md) |
| Generator | Keep portable resources aligned with the native plugin | [Sync tool](../../tools/sync_portable.py) |
| References | Evidence, config, writing, and page conventions | [References](../../plugins/archlens/references) |
| Checker | Config validation, structural checks, impact reports | [Python tool](../../plugins/archlens/scripts/archlens.py) |
| Budget check | Prevent instruction growth and eager-loading additions | [Budget tool](../../tools/prompt_budget.py) |

## Reading path and coverage

| Question | Page | Known limit |
|---|---|---|
| How does update select pages? | [Update runtime](runtime.md) | Indirect dependencies require agent review |
| Where do settings and reports go? | [Data](data.md) | The host's internal data handling is outside this project |
| Why manual isolated commands? | [ADR-001](decisions/ADR-001.md) | Real model token savings remain unmeasured |
| Why JSON metadata? | [ADR-002](decisions/ADR-002.md) | Authors must maintain coverage patterns |
| What does prompt loading cost? | [Context budgets](../context-efficiency.md) | Byte estimates are not exact tokens |

**Implementation observed:** links above.
**Test evidence:** [checker tests](../../tests/test_archlens.py),
[distribution tests](../../tests/test_distribution.py), and
[installer tests](../../tests/test-skills-install.mjs).
These documents are drafts. No human review is claimed.
