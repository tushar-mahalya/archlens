---
name: archlens
description: "Create or maintain evidence-based architecture documentation, trace execution and data flows, explain design tradeoffs, or audit a handbook. Use when asked for architecture views, Mermaid diagrams, decisions, or a code-backed system explanation."
license: MIT
---

# Archlens

Select one operation from the user's request:

| Request | Operation |
|---|---|
| Create or extend an architecture handbook | [setup](workflows/setup.md) |
| Update the handbook for local changes | [update](workflows/update.md) |
| Audit existing documents without editing | [check](workflows/check.md) |
| Explain one execution or data scenario without editing | [explain](workflows/explain.md) |
| Draft an architecture decision record | [decide](workflows/decide.md) |

If the intended operation is unclear, ask the user. Do not create a handbook
or decision record merely because the user asked for an explanation.
Use any supplied scenario, local base ref, or decision evidence in that operation.

The skill directory is the folder containing this `SKILL.md`, not the user's
project directory. In bundled instructions, replace `<skill-dir>` with its
actual absolute path and use the host's path separator and quoting.
Read [the task contract](references/contract.md) once, then read only the
selected workflow. If that workflow also names the contract, do not read it again.
Read detailed references or template sections only when the workflow requires them.

Keep all work inside the selected project. Respect host permissions and project
instructions. Do not install tools, publish, or change global settings as part
of a documentation task. Report missing evidence and unavailable checks.
Do not claim official ASD-STE100 compliance or an unmeasured style score.
