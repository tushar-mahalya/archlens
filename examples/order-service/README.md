# Try Archlens on a small project

This fictional Python library accepts an order and stores it in SQLite.
It has no HTTP server, payment service, background jobs, or production deployment.

Run the demo with Python 3.10+:

```text
python order_service.py
```

It prints the same order ID for a repeated request.
The default database lives in memory and disappears when the process exits.

Read the [handbook](docs/architecture/README.md).
Then open Claude Code in this folder and run:

```text
/archlens:explain what happens when the same request key is used twice?
/archlens:check
```

To try setup from an empty handbook, copy only `order_service.py` into a new folder.
Open that folder in Claude Code and run `/archlens:setup`.
Do not delete the sample handbook merely to test setup.
