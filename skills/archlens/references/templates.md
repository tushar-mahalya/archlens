# Authoring frames

Replace every placeholder with evidence or an explicit unknown.
Do not create empty pages for every heading.
Put machine-readable metadata in `map.json`, as defined in the configuration reference.

## Shared page

1. **Question and scope**: what this page explains and excludes.
2. **Summary**: two or three short sentences.
3. **Diagram**: one main question.
4. **Explanation**: steps, rules, or a small fact table.
5. **Failure and tradeoffs**: relevant limitations.
6. **Evidence and gaps**: source, tests, decisions, and unknowns.
7. **Related pages**: a clear next step.

## Handbook index

File: `README.md`, so code hosts show it for the folder. Title: Understand this system

- Purpose, users, and non-goals.
- Read first: context and deployable units.
- Trace a request: priority runtime scenarios.
- Understand data: owner, lifecycle, and contracts.
- Understand choices: decisions and quality goals.
- Operate the system: deployment, recovery, and runbook links.
- Coverage table, element catalog, glossary, owners, and known gaps.

## Context and containers

Separate the system boundary view from the deployable-unit view.
Use a context diagram for people and external systems.
Use a container diagram for applications, workers, and stores.

| Unit | Responsibility | Technology | Owner | Interface | Source |
|---|---|---|---|---|---|
| Actual name | One clear purpose | Verified value | Team or unknown | Contract link | Implementation |

Do not put every class in the container diagram.

## Runtime scenario

Title: What happens when [trigger]?

- Trigger, preconditions, permissions, and outcome.
- Primary path, alternatives, and failure paths.
- State changes, transaction boundaries, retries, and duplicates.
- Observable signals and recovery links.

Use a numbered sequence diagram, followed by:

| Step | Component | Condition and action | Data or side effect | Source and test |
|---|---|---|---|---|
| Diagram number | Actual unit | Evidence-backed rule | Read, write, event, or none | Real links |

For complex branch logic:

| Priority | Condition | Result | Side effect | Source |
|---|---|---|---|---|
| Explicit precedence | Actual expression in plain words | Output | State or event | Real link |

State whether the first matching rule wins. Include the default case.

## Data flow and lifecycle

Start with source, transformation, store, consumer, and external boundary.
Use labeled arrows. Use a separate ER view only when relationships help.

| Data | Source and owner | Validation | Store and consumers | Retention and deletion | Evidence |
|---|---|---|---|---|---|
| Entity or event | Accountable team | Actual constraints | Real boundary | Verified policy or unknown | Contract and code |

Also cover access, sensitivity, consistency, schema evolution, replay, and backups.
Use a state diagram for actual states, transition guards, actors, and recovery paths.

## Quality and operations

| Goal | Stimulus | Environment | Required response | Measure | Evidence and owner |
|---|---|---|---|---|---|
| Named quality | Specific event | Load and failure conditions | Observable outcome | Agreed threshold | Test, benchmark, or unknown |

Distinguish a requirement from a measured result.
Explain which quality loses when another improves. Link this tradeoff to a decision.
Show deployment zones, replicas, external dependencies, and rollout constraints.
Link operator procedures instead of duplicating runbooks.

## Decision record

Title: ADR-NNN - Specific decision

- **Status**: proposed / accepted / rejected / deprecated / superseded.
- **Date and deciders**: verified values, or unknown.
- **Evidence basis**: recorded intent / inferred reconstruction.
- **Context**: problem, constraints, and quality drivers.
- **Options**: feasible alternatives, including no change when relevant.
- **Decision**: selected option and scope.
- **Rationale**: why the option fits the stated drivers.
- **Consequences**: benefits, costs, risks, and negative effects.
- **Reversal cost**: what a replacement requires.
- **Validation**: evidence, experiment, or unresolved question.
- **Revisit when**: measurable change that triggers another review.
- **Links**: affected views, implementation, proposal, and superseded decision.

| Option | Benefits | Costs and risks | Evidence | Outcome |
|---|---|---|---|---|
| Real candidate | Concrete gain | Concrete loss | Link or unknown | Selected / rejected / not evaluated |

Never invent rejected alternatives or historical approval.
If history is unavailable, state that the comparison is a present-day analysis.
