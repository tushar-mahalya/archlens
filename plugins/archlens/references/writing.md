# Clear writing and diagrams

## STE-inspired language

This is a local software-writing profile inspired by ASD-STE100.
It is not the standard, its dictionary, or a certification.

1. Name the actor and prefer active voice.
2. Keep procedural sentences to 20 words and descriptions to 25 words.
3. Give one action per instruction.
4. Use one term for one concept. Define technical terms in a glossary.
5. Prefer direct verbs and familiar words. Avoid idioms and vague qualifiers.
6. State the condition before its action when this helps the reader.
7. Replace ambiguous references such as "it" with the actual name.
8. Keep paragraphs short. Use lists for independent facts.
9. Preserve identifiers, protocol names, qualifications, and exact guarantees.
10. Use a short summary, then a diagram, then evidence-backed detail.

Do not replace "at-least-once delivery" with "reliable delivery".
Do not mechanically remove every "-ing" word.
The glossary is a local terminology policy, not an official approved-word list.

Before: "In the event of a failure, a retry is performed by the worker."
After: "If the request fails, the worker retries it."
Then state the actual retry limit, delay, and duplicate-handling rule.

## The 80% target

Call the result a **local STE-inspired style pass rate**.
Never call it an official ASD-STE100 compliance percentage.
For each complete prose sentence in the declared scope, review:

- The applicable word limit.
- A clear actor and action, with active voice where practical.
- One unambiguous instruction, if procedural.
- Consistent terminology and explicit references.
- Direct wording without unnecessary jargon.

A sentence passes only when it passes all applicable checks.
The rate is passing sentences divided by reviewed sentences.
Use `styleTarget`, normally 0.8.
Report the scope, total, failures, exclusions, and counting method.
Review all changed prose when feasible. Label a sample as a sample.
For fewer than 20 sentences, report counts, not a precise overall percentage.
With no eligible sentences, report "not applicable". Without an audit, report "not measured".

Exclude code, raw identifiers, URLs, frontmatter, and headings.
Include complete sentences in captions and table cells.
Review diagram labels, fragments, and paragraph structure separately.
Automated word counting may differ from the standard's counting rules.

The Python checker does not calculate this score. It flags long paragraphs and
semicolons as editorial candidates, without pretending to evaluate meaning.
Wrong facts, invented evidence, and ambiguous access rules are not acceptable at any score.

## Choose the diagram by the question

| Question | View |
|---|---|
| Who uses the system? What is outside it? | Context flowchart |
| Which units run and store data? | C4-style container view |
| What happens, and in what order? | Sequence diagram with `autonumber` |
| Which rule selects a branch? | Decision table or flowchart |
| Who owns and transforms the data? | Data flow and contract table |
| Which entities relate? | ER diagram |
| Which transitions are legal? | State diagram |
| What runs where? | Deployment view |
| Why did people choose this option? | ADR and option table |

Use Mermaid flowcharts, sequences, states, and ER diagrams by default.
C4 concepts do not require Mermaid's native C4 syntax.
A C4 container means a deployable application or store, not necessarily a Docker container.

## Readability and rendering

- One view answers one main question at one abstraction level.
- Reuse element names and IDs across pages.
- Label important arrows with actions or data, plus protocol when useful.
- Define arrow meanings. A dashed arrow does not universally mean asynchronous.
- Show relevant trust boundaries, persistence, and ownership.
- Include failure branches and retry limits in runtime coverage.
- Use the configured density limits as soft prompts to split a crowded view.
- Add a caption or equivalent table. Do not rely on color alone.
- Prefer a table over a tangled branch graph.
- Do not add a diagram when three sentences explain the point better.

Each important sequence needs a step table with source and test links.
Each data view needs ownership, validation, consistency, retention, and deletion rules.
Each decision table needs precedence and a default case.

Render private diagrams locally. Do not use a remote render API.
Pin the renderer in CI using the project's normal dependency tools.
GitHub controls its own Mermaid version; a local pin does not pin GitHub.
For stable published output, export SVG locally and keep its editable source.
When repeated elements become hard to maintain, consider Structurizr DSL or LikeC4.
Their shared model still needs evidence and review to stay current.
