# Understand the order example

The library stores an order and returns its ID.
A repeated request returns the same ID when its data matches.
This is a teaching example, not a production design.

## Read in this order

1. [Context](context.md): caller, library, and store.
2. [Submit an order](runtime/submit-order.md): branches and transaction behavior.
3. [Data](data.md): ownership, constraints, and lifetime.
4. [Decision proposal](decisions/ADR-001.md): why a request key may help.
5. [Glossary](glossary.md): terms used in these pages.

## Coverage

| Concern | Page | Evidence | Gaps |
|---|---|---|---|
| New and repeated requests | [Flow](runtime/submit-order.md) | [Implementation](../../order_service.py) | Concurrent callers are not demonstrated |
| Conflicting request key | [Flow](runtime/submit-order.md) | [Implementation](../../order_service.py) | No network error mapping |
| Storage and lifetime | [Data](data.md) | [Schema](../../order_service.py) | No production retention policy |

All pages are drafts. No human approval or production verification is claimed.
The example excludes authentication, payments, stock checks, and recovery operations.
