"""Tests for section queries, the pre-commit gate, mechanical style, and diagram checks."""

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

from test_archlens import Fixture, archlens, page, write_json


FLOW = """# What happens when the caller submits an order?

## Summary

The library validates the input before it starts a write.

## Sequence

```mermaid
sequenceDiagram
    autonumber
    participant C as Caller
    participant S as Service
    participant D as Database
    C->>S: submit_order(key, sku)
    S->>S: Validate the input
    Note over S: A note is not a message
    loop Until stored
        S->>+D: INSERT order
        D-->>-S: Row ID
    end
    S-->>C: Order ID
```

Text equivalent: the caller submits an order.
The service validates it and stores it.

| Step | Component | Action | Source |
|---|---|---|---|
| 1 | Caller | Sends the key. | [submit](../../../src/orders.py#L1-L3) |
| 2-3 | `Service` | Rejects an empty key. | [validate](../../../src/orders.py#L5-L7) |
| 4, 5 | Database | Stores one row. | [store](../../../src/store.py) |

## Failure behavior

The worker retries a failed write three times. The retry limit is fixed.

```text
# This is not a heading
```

## Related pages

- Back: [index](../README.md).
"""

INDEX = """# Understand the system

Orders move from the caller to the database.

```mermaid
flowchart LR
    Caller["Caller"] -->|"submit"| Service["Service"]
    Service -->|"write"| Store[("Database")]
```

| Unit | Responsibility |
|---|---|
| `Service` | Validates and stores orders. |
| Database | Keeps one row for each key. |

See the [flow](runtime/submit.md) and the [module](../../src/orders.py).
"""


class HandbookFixture(Fixture):
    def setUp(self):
        super().setUp()
        self.docs = self.handbook(INDEX, pages=[
            page(covers=["src/**"]),
            page("runtime/submit.md", id="FLOW-001", kind="runtime", covers=["src/orders.py", "tests/**"]),
        ])
        (self.docs / "runtime").mkdir()
        (self.docs / "runtime/submit.md").write_text(FLOW, encoding="utf-8")
        (self.root / "src").mkdir()
        (self.root / "tests").mkdir()
        (self.root / "src/orders.py").write_text(
            "def submit_order(key):\n    validate(key)\n    return 1\n\n"
            "def validate(key):\n    if not key:\n        raise ValueError('key')\n", encoding="utf-8")
        (self.root / "src/store.py").write_text("def store(row):\n    return row\n", encoding="utf-8")
        (self.root / "tests/test_orders.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
        (self.root / "README.md").write_text("# Project\n\n[Architecture](docs/architecture/README.md)\n", encoding="utf-8")

    def query(self, *terms, **options):
        return archlens.query_handbook(self.root, self.config, list(terms), **options)

    def text(self, report):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            archlens.print_query(report)
        return out.getvalue()


class StructureTests(unittest.TestCase):
    def test_sections_have_exact_line_ranges_and_ignore_fenced_headings(self):
        sections = archlens.page_sections(FLOW)
        lines = FLOW.splitlines()
        self.assertEqual([s["heading"] for s in sections], [
            "What happens when the caller submits an order?", "Summary", "Sequence", "Failure behavior", "Related pages"])
        for section in sections:
            self.assertTrue(lines[section["lines"][0] - 1].lstrip("# ").startswith(section["heading"][:10]))
        self.assertEqual(sections[-1]["lines"][1], len(lines))
        self.assertEqual([d["type"] for d in sections[2]["diagrams"]], ["sequenceDiagram"])
        first, last = sections[2]["diagrams"][0]["lines"]
        self.assertEqual((lines[first - 1], lines[last - 1]), ("```mermaid", "```"))
        self.assertEqual(sections[2]["trail"], ["What happens when the caller submits an order?"])

    def test_text_before_the_first_heading_is_a_section(self):
        sections = archlens.page_sections("Intro line.\n\n## First\n\nBody.\n\n### Deep\n\nMore.\n")
        self.assertEqual([(s["heading"], s["level"], s["lines"]) for s in sections],
                         [("", 0, [1, 2]), ("First", 2, [3, 6]), ("Deep", 3, [7, 9])])
        self.assertEqual(sections[2]["trail"], ["First"])
        self.assertEqual(archlens.page_sections(""), [])

    def test_diagram_counters(self):
        prose, blocks, _ = archlens.markdown_sections(FLOW)
        self.assertEqual(archlens.sequence_messages(blocks[0][2]), 5, "notes, loops, and participants do not count")
        flow = ("flowchart LR\n A[One] -- text --> B(Two)\n B --> C{Three} & D((Four))\n"
                " subgraph S[\"Zone\"]\n  E[(Store)] -.->|x| F\n end\n classDef hot fill:#f00\n class A hot\n A:::hot ==> G\n"
                " %% a comment --> H\n")
        self.assertEqual(archlens.flowchart_nodes(flow), 7)
        self.assertEqual(archlens.flowchart_nodes('flowchart TB\n Web["A --> B (not an edge)"] --> Api\n'), 2)

    def test_step_numbers_and_cells(self):
        self.assertEqual(archlens.step_numbers("4-5"), {4, 5})
        self.assertEqual(archlens.step_numbers("11–13"), {11, 12, 13})
        self.assertEqual(archlens.step_numbers("1, 3"), {1, 3})
        self.assertEqual(archlens.step_numbers("**7**"), {7})
        self.assertEqual(archlens.step_numbers("none"), set())
        self.assertEqual(archlens.cell_text("[`ledgerctl`](x.md) **tool**"), "ledgerctl tool")
        tables = archlens.page_tables(archlens.markdown_sections(FLOW)[0])
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]["header"][0], "Step")
        self.assertEqual(len(tables[0]["rows"]), 3)

    def test_search_tokens_split_identifiers_and_stem(self):
        self.assertEqual(archlens.search_tokens("RagService"), ["rag", "service", "ragservice"])
        self.assertIn("submitorder", archlens.search_tokens("submit_order"))
        self.assertEqual(archlens.search_tokens("the retries"), archlens.search_tokens("retry"))
        self.assertEqual(archlens.search_tokens("what is the"), [])


class QueryTests(HandbookFixture):
    def test_outline_lists_every_section_with_readable_ranges(self):
        report = self.query(page_name="FLOW-001")
        self.assertEqual(report["mode"], "outline")
        lines = FLOW.splitlines()
        for record in report["results"]:
            first, last = record["lines"]
            self.assertTrue(lines[first - 1].startswith("#"))
            self.assertTrue(lines[last - 1].strip(), "trailing blank lines are trimmed")
        sequence = next(r for r in report["results"] if r["heading"] == "Sequence")
        self.assertEqual(sequence["diagrams"], ["sequenceDiagram"])
        self.assertIn("docs/architecture/runtime/submit.md:", self.text(report))
        for name in ("flow-001", "runtime/submit.md", "docs/architecture/runtime/submit.md", "submit.md", "submit"):
            self.assertEqual(self.query(page_name=name)["page"], "docs/architecture/runtime/submit.md")

    def test_search_ranks_the_section_that_answers(self):
        report = self.query("retry", "limit")
        self.assertEqual(report["results"][0]["heading"], "Failure behavior")
        self.assertIn("retry limit", report["results"][0]["snippet"])
        self.assertEqual(self.query("submitOrder")["results"][0]["page"], "docs/architecture/runtime/submit.md")
        self.assertEqual(self.query("unit", "responsibility")["results"][0]["id"], "INDEX")
        limited = self.query("order", limit=1)
        self.assertEqual(len(limited["results"]), 1)
        self.assertGreater(limited["matches"], 1)
        self.assertIn("more; raise --limit", self.text(limited))
        self.assertEqual(self.query("zebra")["results"], [])
        self.assertIn("No matching section.", self.text(self.query("zebra")))
        scoped = self.query("order", page_name="INDEX")
        self.assertEqual({r["id"] for r in scoped["results"]}, {"INDEX"})

    def test_file_mode_names_citing_sections_and_line_ranges(self):
        report = self.query(file="src/orders.py")
        cited = {(r["id"], r["heading"]): r.get("cites") for r in report["results"]}
        self.assertEqual(cited[("FLOW-001", "Sequence")], ["L1-L3", "L5-L7"])
        self.assertEqual(cited[("INDEX", "Understand the system")], [])
        self.assertEqual(report["coveredBy"], [])
        other = self.query(file=str(self.root / "tests/test_orders.py"))
        self.assertEqual(other["results"], [])
        self.assertEqual(other["coveredBy"], ["docs/architecture/runtime/submit.md"])
        self.assertIn("Covered without a citation", self.text(other))
        self.assertIn("cites L1-L3, L5-L7", self.text(report))

    def test_step_and_row_return_one_table_row(self):
        for step in (2, 3):
            rows = self.query(page_name="FLOW-001", step=step)["results"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["cells"]["Component"], "`Service`")
            self.assertIn("orders.py#L5-L7", rows[0]["cells"]["Source"])
        self.assertEqual(self.query(page_name="FLOW-001", step=5)["results"][0]["cells"]["Component"], "Database")
        self.assertEqual(self.query(page_name="FLOW-001", step=9)["results"], [])
        row = self.query(page_name="INDEX", row="service")["results"]
        self.assertEqual(row[0]["cells"]["Responsibility"], "Validates and stores orders.")
        self.assertEqual(self.query(page_name="INDEX", step=1)["results"], [], "the index has no step table")
        self.assertIn("  Component: `Service`", self.text(self.query(page_name="FLOW-001", step=2)))

    def test_diagram_returns_source_and_text_equivalent(self):
        result = self.query(page_name="FLOW-001", diagram=1)["results"][0]
        self.assertEqual(result["type"], "sequenceDiagram")
        self.assertTrue(result["source"].startswith("```mermaid\nsequenceDiagram"))
        self.assertTrue(result["source"].endswith("The service validates it and stores it."))
        lines = FLOW.splitlines()
        self.assertEqual(lines[result["lines"][1] - 1], "The service validates it and stores it.")
        plain = self.query(page_name="INDEX", diagram=1)["results"][0]
        self.assertTrue(plain["source"].endswith("```"), "no text equivalent follows this diagram")
        with self.assertRaises(archlens.ArchlensError):
            self.query(page_name="INDEX", diagram=2)

    def test_errors_are_explicit(self):
        for options in ({"step": 1}, {"row": "x"}, {"diagram": 1}):
            with self.assertRaises(archlens.ArchlensError):
                self.query(**options)
        with self.assertRaises(archlens.ArchlensError):
            self.query(page_name="missing")
        with self.assertRaises(archlens.ArchlensError):
            self.query()
        with self.assertRaises(archlens.ArchlensError):
            self.query("the")
        with self.assertRaises(archlens.ArchlensError):
            self.query(file="../outside.py")
        (self.docs / "other").mkdir()
        (self.docs / "other/submit.md").write_text("# Other\n", encoding="utf-8")
        write_json(self.docs / "map.json", {"version": 1, "pages": [
            page(), page("runtime/submit.md", id="FLOW-001", kind="runtime"),
            page("other/submit.md", id="FLOW-002", kind="runtime")]})
        with self.assertRaises(archlens.ArchlensError):
            self.query(page_name="submit.md")
        self.assertEqual(self.query(page_name="FLOW-002")["page"], "docs/architecture/other/submit.md")

    def test_stale_pages_are_flagged_in_results(self):
        archlens.sync_pages(self.root, self.config, [], True)
        self.assertNotIn("state", self.query("retry")["results"][0])
        (self.root / "src/orders.py").write_text(
            "def submit_order(key):\n    validate(key)\n    return 2\n\n"
            "def validate(key):\n    if not key:\n        raise ValueError('key')\n", encoding="utf-8")
        report = self.query("retry")
        self.assertEqual(report["results"][0]["state"], "stale")
        self.assertIn("STALE", self.text(report))

    def test_output_is_bounded_and_the_command_is_read_only(self):
        big = "# Big\n\n" + "".join(f"## Section {n}\n\nThe order {n} moves to the database store.\n\n" for n in range(400))
        (self.docs / "runtime/submit.md").write_text(big, encoding="utf-8")
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        text = self.text(self.query(page_name="FLOW-001"))
        self.assertLessEqual(len(text.encode("utf-8")), 6100)
        self.assertIn("truncated", text)
        code, output, _ = self.run_cli("query", "database", "--summary")
        self.assertEqual(code, 0)
        self.assertLessEqual(len(output.encode("utf-8").rstrip()), 6000)
        self.assertEqual(json.loads(output)["command"], "query")
        code, output, _ = self.run_cli("query", "database", "--limit", "2")
        self.assertEqual((code, output.count("docs/architecture/")), (0, 2))
        self.assertEqual(self.run_cli("query", "--step", "1")[0], 2)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_file_pointer_names_the_citing_sections(self):
        payload = {"session_id": "p", "tool_input": {"file_path": str(self.root / "src/orders.py")}}
        with patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": str(self.root / ".data")}):
            text = archlens.hook_file_pointer(self.root, self.config, payload)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("`docs/architecture/runtime/submit.md` (Sequence L7-32)", text)
            self.assertIn("`docs/architecture/README.md` (Understand the system L1-16)", text)
            self.assertLess(len(text), 400)
            covered = {"session_id": "q", "tool_input": {"file_path": str(self.root / "tests/test_orders.py")}}
            text = archlens.hook_file_pointer(self.root, self.config, covered)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("(What happens when the caller submits an order?)", text, "a covered file keeps the page title")


class MapDensityTests(Fixture):
    def handbook_with_decisions(self, decisions, working=6):
        docs = self.handbook("# Understand this system\n\nOrders move from the API to the database.\n")
        entries = [page()]
        for n in range(working):
            (docs / f"flow{n}.md").write_text(f"# Flow {n}\n\n" + f"The flow {n} moves one order through many careful steps. " * 3 + "\n", encoding="utf-8")
            entries.append(page(f"flow{n}.md", id=f"FLOW-{n}", kind="runtime", covers=[f"src/f{n}/**"]))
        (self.root / "docs/adr").mkdir(parents=True, exist_ok=True)
        for n in range(decisions):
            name = f"{n:04d}-a-long-decision-record-name-number-{n}"
            (self.root / f"docs/adr/{name}.md").write_text(f"# ADR {n:04d}: A decision title that takes many bytes in the map\n", encoding="utf-8")
            entries.append(page(f"../adr/{name}.md", id=f"ADR-{n}", kind="decision", decisionStatus="accepted", covers=[f"src/d{n}.py"]))
        write_json(docs / "map.json", {"version": 1, "pages": entries})

    def test_decision_folder_collapses_only_when_summaries_do_not_fit(self):
        self.handbook_with_decisions(3)
        roomy = archlens.build_context(self.root, self.config, 3000)
        self.assertNotIn("decision records:", roomy, "everything fits: one line per record")
        self.assertEqual(roomy.count("ADR 000"), 3)
        self.handbook_with_decisions(12)
        tight = archlens.build_context(self.root, self.config, 1700)
        self.assertLessEqual(len(tight.encode("utf-8")), 1700)
        self.assertIn("- `../adr/` 12 decision records: 0000-a-long-decision-record-name-number-0, ", tight)
        self.assertEqual(tight.count("moves one order through many careful steps."), 6, "every working page keeps its summary")
        self.assertNotIn("A decision title", tight)
        self.assertEqual(archlens.build_context(self.root, self.config, 20000).count("A decision title"), 12)

    def test_a_stale_decision_keeps_its_own_line(self):
        self.handbook_with_decisions(12)
        (self.root / "src").mkdir()
        (self.root / "src/d3.py").write_text("def a():\n    return 1\n", encoding="utf-8")
        adr = next((self.root / "docs/adr").glob("0003-*"))
        adr.write_text(adr.read_text() + "\nSee [code](../../src/d3.py#L1-L2).\n", encoding="utf-8")
        archlens.sync_pages(self.root, self.config, [], True)
        (self.root / "src/d3.py").write_text("def a():\n    return 2\n", encoding="utf-8")
        tight = archlens.build_context(self.root, self.config, 1700)
        self.assertIn("11 decision records:", tight)
        self.assertIn("ADR 0003: A decision title that takes many bytes in the map STALE: 1 cited change", tight)

    def test_map_never_exceeds_the_budget_for_any_install_path(self):
        self.handbook_with_decisions(12, working=14)
        for length in range(20, 260, 7):
            with patch.object(archlens, "script_path", return_value="/" + "p" * length):
                for budget in (1500, 1900, 2400, 3000):
                    text = archlens.build_context(self.root, self.config, budget)
                    self.assertLessEqual(len(text.encode("utf-8")), budget, (length, budget))
                    self.assertTrue(text.endswith("\n"))
        with patch.object(archlens, "script_path", return_value="/" + "p" * 190):
            tight = archlens.build_context(self.root, self.config, 1500)
            self.assertNotIn("query --root", tight, "the hint goes before any page title")
            self.assertIn("`flow13.md` Flow 13", tight)
            self.assertNotIn("more pages", tight)
        with patch.object(archlens, "script_path", return_value="/" + "p" * 201):
            self.assertNotIn("query --root", archlens.build_context(self.root, self.config, 3000))

    def test_query_hint_needs_room_and_a_larger_handbook(self):
        self.handbook_with_decisions(3, working=2)
        self.assertNotIn("query --root", archlens.build_context(self.root, self.config, 3000), "6 pages: read them whole")
        self.handbook_with_decisions(3, working=6)
        self.assertIn('archlens.py" query --root . <words>`', archlens.build_context(self.root, self.config, 3000))
        self.assertNotIn("query --root", archlens.build_context(self.root, self.config, 1400))
        self.assertNotIn("query --root", archlens.build_context(self.root, self.config, 3000, live=False),
                         "a committed block must not hold a machine path")


class HookEntryTests(HandbookFixture):
    ENTRY = Path(archlens.__file__).with_name("hook.py")

    def hook(self, event, payload, cwd=None, raw=None, extra=None):
        env = {key: value for key, value in os.environ.items() if key not in {"ARCHLENS_CONFIG", "XDG_CONFIG_HOME"}}
        env.update({"CLAUDE_PROJECT_DIR": str(cwd or self.root), "CLAUDE_PLUGIN_DATA": str(self.root / ".data"),
                    "HOME": str(self.root / "home"), "CLAUDE_CONFIG_DIR": str(self.root / "user"), **(extra or {})})
        done = subprocess.run([sys.executable, str(self.ENTRY), event], env=env, capture_output=True,
                              input=(raw if raw is not None else json.dumps(payload)).encode(), timeout=30, check=False)
        return done.returncode, done.stdout.decode(), done.stderr.decode()

    def test_entry_runs_the_checker_in_a_handbook_project(self):
        code, out, err = self.hook("session-start", {"session_id": "a"})
        self.assertEqual((code, err), (0, ""))
        self.assertIn("## Architecture handbook (Archlens)", out)
        payload = {"session_id": "a", "tool_input": {"file_path": str(self.root / "src/orders.py")}}
        self.assertIn("Sequence L7-32", json.loads(self.hook("file-pointer", payload)[1])["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.hook("commit-gate", {"tool_input": {"command": "ls -la"}}), (0, "", ""))
        self.assertEqual(self.hook("stop", {"session_id": "a"}), (0, "", ""))

    def test_entry_is_silent_without_a_handbook_and_never_fails(self):
        empty = self.root / "elsewhere"
        empty.mkdir()
        for event in ("session-start", "stop", "file-pointer", "commit-gate"):
            self.assertEqual(self.hook(event, {"tool_input": {"command": "git commit -m x"}}, cwd=empty), (0, "", ""))
        for raw in ("", "not json", "[1, 2]", '{"cwd": 5}'):
            self.assertEqual(self.hook("session-start", None, raw=raw)[0], 0)
            self.assertEqual(self.hook("stop", None, cwd=empty, raw=raw), (0, "", ""))
        self.assertEqual(self.hook("unknown-event", {}), (0, "", ""))
        self.assertEqual(self.hook("session-start", {}, cwd=self.root / "missing"), (0, "", ""))

    def test_entry_defers_to_the_checker_for_custom_layouts(self):
        moved = self.root / "moved"
        (moved / "handbook").mkdir(parents=True)
        (moved / "handbook/README.md").write_text("# Moved\n\nA handbook in another folder.\n", encoding="utf-8")
        write_json(moved / "handbook/map.json", {"version": 1, "pages": [page()]})
        self.assertEqual(self.hook("session-start", {}, cwd=moved), (0, "", ""), "no config names the folder")
        write_json(moved / ".archlens.json", {"docsRoot": "handbook"})
        self.assertIn("Pages live in `handbook/`", self.hook("session-start", {}, cwd=moved)[1])
        (moved / ".archlens.json").unlink()
        write_json(self.root / "user/archlens.json", {"docsRoot": "handbook"})
        self.assertIn("Pages live in `handbook/`", self.hook("session-start", {}, cwd=moved)[1], "a user preference file")

    def test_hooks_file_uses_the_entry(self):
        hooks = json.loads((Path(archlens.__file__).parents[1] / "hooks/hooks.json").read_text())["hooks"]
        events = {hook["args"][1] for groups in hooks.values() for group in groups for hook in group["hooks"]}
        self.assertEqual(events, {"session-start", "stop", "file-pointer", "commit-gate"})
        for groups in hooks.values():
            for group in groups:
                for hook in group["hooks"]:
                    self.assertEqual(hook["args"][0], "${CLAUDE_PLUGIN_ROOT}/scripts/hook.py")


class FingerprintTests(Fixture):
    PY = ("import os\n\nLIMIT = 3\n# about the timeout\nTIMEOUT = 10\n\n\n"
          "def first(value):\n    if value > LIMIT:\n        return 1\n    return 0\n\n\n"
          "def second(value):\n    total = value + 1\n    return total\n")

    def setUp(self):
        super().setUp()
        (self.root / "src").mkdir()
        self.write("src/m.py", self.PY)
        self.write("deploy.yaml", "limits:\n  # how many\n  workers: 4\n  timeout: 30\nname: api\n")

    def write(self, name, text):
        (self.root / name).write_text(text, encoding="utf-8")

    def verdict(self, record, name, text):
        self.write(name, text)
        change = archlens.check_anchor(self.root, record)
        return (change["change"], change.get("newLines")) if change else None

    def test_range_with_a_trailing_blank_line_belongs_to_its_function(self):
        record = archlens.fingerprint_anchor(self.root, "src/m.py", 8, 12)
        self.assertEqual((record["symbol"], record["symbolLines"], record["spanKind"]), ("first", [8, 11], 2))
        self.assertIsNone(archlens.check_anchor(self.root, record))
        self.assertEqual(self.verdict(record, "src/m.py", "# header\n" + self.PY), ("evidence-moved", [9, 13]))
        commented = self.PY.replace("    if value > LIMIT:\n", "    # a note\n    if value > LIMIT:  # inline\n")
        self.assertEqual(self.verdict(record, "src/m.py", commented), ("evidence-moved", [8, 13]))
        self.assertEqual(self.verdict(record, "src/m.py", self.PY.replace("return 1", "return 2"))[0], "evidence-changed")
        self.assertIsNone(self.verdict(record, "src/m.py", self.PY.replace("value + 1", "value + 2")), "another function")

    def test_range_over_several_symbols_or_module_code_ignores_comments(self):
        both = archlens.fingerprint_anchor(self.root, "src/m.py", 8, 16)
        constants = archlens.fingerprint_anchor(self.root, "src/m.py", 3, 5)
        for record in (both, constants):
            self.assertNotIn("symbol", record)
            self.assertEqual(record["spanKind"], 2)
        self.assertIsNone(self.verdict(constants, "src/m.py", self.PY.replace("# about the timeout", "# reworded; longer")))
        self.assertIsNone(self.verdict(constants, "src/m.py", self.PY.replace("TIMEOUT = 10", "TIMEOUT = 10  # seconds")))
        self.assertEqual(self.verdict(constants, "src/m.py", self.PY.replace("TIMEOUT = 10", "TIMEOUT = 11"))[0], "evidence-changed")
        self.assertEqual(self.verdict(both, "src/m.py", "# header\n\n" + self.PY), ("evidence-moved", [10, 18]))
        spaced = self.PY.replace("    total = value + 1\n", "\n    # why\n    total = value + 1   \n")
        self.assertEqual(self.verdict(both, "src/m.py", spaced), ("evidence-moved", [8, 18]))
        self.assertEqual(self.verdict(both, "src/m.py", self.PY.replace("value + 1", "value + 2"))[0], "evidence-changed")

    def test_python_reindent_is_a_change(self):
        record = archlens.fingerprint_anchor(self.root, "src/m.py", 9, 11)
        self.assertEqual(record["symbol"], "first")
        moved_out = self.PY.replace("        return 1\n    return 0\n", "        return 1\n        return 0\n")
        self.assertEqual(self.verdict(record, "src/m.py", moved_out)[0], "evidence-changed")
        nested = self.PY.replace("def first(value):\n    if value > LIMIT:\n        return 1\n    return 0\n",
                                 "def first(value):\n    if True:\n        if value > LIMIT:\n            return 1\n        return 0\n")
        self.assertEqual(self.verdict(record, "src/m.py", nested), ("evidence-moved", [10, 12]),
                         "a sub-range follows its own lines: a new wrapper is an edit elsewhere in the function")
        self.write("src/m.py", self.PY)
        whole = archlens.fingerprint_anchor(self.root, "src/m.py", 8, 11)
        self.assertEqual(self.verdict(whole, "src/m.py", nested)[0], "evidence-changed", "the whole function sees it")

    def test_config_files_ignore_comments_and_keep_indent(self):
        record = archlens.fingerprint_anchor(self.root, "deploy.yaml", 1, 4)
        self.assertEqual(record["spanLines"], 3)
        text = "limits:\n  # how many\n  workers: 4\n  timeout: 30\nname: api\n"
        self.assertIsNone(self.verdict(record, "deploy.yaml", text.replace("# how many", "# reworded")))
        self.assertIsNone(self.verdict(record, "deploy.yaml", text.replace("workers: 4", "workers: 4  # per host")))
        self.assertEqual(self.verdict(record, "deploy.yaml", "version: 1\n" + text), ("evidence-moved", [2, 5]))
        self.assertEqual(self.verdict(record, "deploy.yaml", text.replace("  timeout: 30", "timeout: 30"))[0], "evidence-changed")
        self.assertEqual(self.verdict(record, "deploy.yaml", text.replace("workers: 4", "workers: 5"))[0], "evidence-changed")
        quoted = archlens.content_lines("a.yaml", 'color: "#fff"  # white\nurl: http://x/#frag\nnote: don\'t # cut\n')
        self.assertEqual([code for _, code, _ in quoted], ['color: "#fff"', "url: http://x/#frag", "note: don't # cut"])

    def test_records_from_before_this_version_still_compare(self):
        inside = {"path": "src/m.py", "lines": [9, 10], "symbol": "first", "symbolLines": [8, 11],
                  "digest": archlens.code_symbols("src/m.py", self.PY)[0][3],
                  "span": archlens.span_digest([line for line in archlens.code_lines("src/m.py", self.PY) if 9 <= line[0] <= 10]),
                  "spanLines": 2, "spanPad": [0, 0]}
        self.assertIsNone(archlens.check_anchor(self.root, inside))
        self.assertEqual(self.verdict(inside, "src/m.py", "# header\n" + self.PY), ("evidence-moved", [10, 11]))
        self.assertEqual(self.verdict(inside, "src/m.py", self.PY.replace("return 1", "return 2"))[0], "evidence-changed")
        self.write("src/m.py", self.PY)
        plain = {"path": "deploy.yaml", "lines": [3, 4], "digest": archlens.text_digest(["  workers: 4", "  timeout: 30"])}
        self.assertIsNone(archlens.check_anchor(self.root, plain))
        self.assertEqual(self.verdict(plain, "deploy.yaml", "limits:\n  workers: 5\n  timeout: 30\n")[0], "evidence-changed")

    def test_sync_fresh_upgrades_fingerprints_without_approving_changes(self):
        docs = self.handbook("# Orders\n\nSee [limits](../../src/m.py#L3-L5).\n", pages=[
            page(covers=["src/**"]), page("b.md", id="B", kind="runtime", covers=["deploy.yaml"])])
        (docs / "b.md").write_text("# B\n\nSee [limits](../../deploy.yaml#L3-L4).\n", encoding="utf-8")
        archlens.sync_pages(self.root, self.config, [], True)
        state = json.loads((docs / ".archlens-state.json").read_text())
        for record in state["pages"].values():   # as an earlier version wrote them
            old_anchor = record["anchors"][0]
            lines = (self.root / old_anchor["path"]).read_text().splitlines()
            first, last = old_anchor["lines"]
            record["anchors"] = [{"path": old_anchor["path"], "lines": [first, last],
                                  "digest": archlens.text_digest(lines[first - 1:last])}]
        (docs / ".archlens-state.json").write_text(json.dumps(state), encoding="utf-8")
        self.write("deploy.yaml", "limits:\n  # how many\n  workers: 5\n  timeout: 30\nname: api\n")
        report = archlens.sync_pages(self.root, self.config, [], False, fresh=True)
        self.assertEqual(report["synced"], ["INDEX"], "the stale page is left for a reviewer")
        state = json.loads((docs / ".archlens-state.json").read_text())["pages"]
        self.assertEqual(state["INDEX"]["anchors"][0]["spanKind"], 2)
        self.assertNotIn("spanKind", state["B"]["anchors"][0])
        self.assertEqual(archlens.freshness(self.root, self.config)["counts"]["stale"], 1)
        self.assertEqual(self.run_cli("sync", "--fresh")[0], 0)
        self.assertEqual(self.run_cli("sync")[0], 2)

    def test_status_skips_the_parse_of_unchanged_files(self):
        docs = self.handbook("# Orders\n\nSee [first](../../src/m.py#L8-L11).\n", pages=[page(covers=["src/**"])])
        archlens.sync_pages(self.root, self.config, [], True)
        with patch.object(archlens, "check_anchor", side_effect=AssertionError("parsed an unchanged file")):
            self.assertEqual(archlens.freshness(self.root, self.config)["counts"]["fresh"], 1)
        self.write("src/m.py", self.PY.replace("return 1", "return 2"))
        entry = archlens.freshness(self.root, self.config)["needsSync"][0]
        self.assertEqual((entry["state"], entry["changed"][0]["change"]), ("stale", "evidence-changed"))


def prose(text):
    return archlens.markdown_sections(text)[0]


class StyleTests(Fixture):
    def reasons(self, text):
        return [sentence["reasons"] for sentence in archlens.style_sentences(prose(text))]

    def test_sentences_join_wrapped_lines_and_skip_fragments(self):
        text = ("# Title\n\nThe service validates\nthe input. It stores one row, e.g. the\nfirst order. Done.\n\n"
                "| Unit | Role |\n|---|---|\n| API | Python 3.11, FastAPI |\n| Store | Keeps one row for each key. |\n\n"
                "- A fragment without a stop\n- The worker retries the request.\n")
        sentences = archlens.style_sentences(prose(text))
        self.assertEqual([s["words"] for s in sentences], [5, 9, 6, 5])
        self.assertEqual([s["line"] for s in sentences], [3, 4, 10, 13], "a sentence reports the line it starts on")
        wrapped = "Read [the long\nlink text](x.md) now. Then stop; go home\nat once.\n"
        found = archlens.style_sentences(prose(wrapped))
        self.assertEqual([(s["line"], s["reasons"]) for s in found], [(1, []), (2, ["semicolon"])])
        self.assertFalse(any(s["reasons"] for s in sentences))

    def test_each_mechanical_rule(self):
        long_sentence = "The service " + "really " * 24 + "works.\n"
        self.assertEqual(self.reasons(long_sentence), [["long"]])
        self.assertEqual(self.reasons("The service " + "really " * 22 + "works.\n"), [[]], "25 words pass")
        self.assertEqual(self.reasons("1. Run " + "the " * 19 + "command.\n"), [["long"]], "a procedure allows 20 words")
        self.assertEqual(self.reasons("- Run " + "the " * 19 + "command.\n"), [[]], "a bullet is a description")
        self.assertEqual(self.reasons("The API starts; the worker waits.\n"), [["semicolon"]])
        self.assertEqual(self.reasons("A retry is performed by the worker.\n"), [["passive"]])
        self.assertEqual(self.reasons("The row is always written by the service.\n"), [["passive"]])
        self.assertEqual(self.reasons("The service is ready by noon.\n"), [[]], "an adjective is not a passive")
        self.assertEqual(self.reasons("The API waits in order to save time.\n"), [["wordy"]])
        self.assertEqual(self.reasons("Run `a; b; c` and read [the page; all of it](x.md#a) now.\n"), [["semicolon"]],
                         "code is ignored, link text is prose")
        self.assertEqual(self.reasons("Run `a; b; c` and then read the page.\n"), [[]])
        code_heavy = "Set `LEDGER_A`, `LEDGER_B`, `LEDGER_C` " + "`X_Y` " * 30 + "before the first start.\n"
        self.assertEqual(self.reasons(code_heavy), [[]], "identifiers do not count as words")

    def test_rate_covers_handbook_pages_only_and_needs_twenty_sentences(self):
        good = "The service validates the input.\n\n"
        bad = "The API starts; the worker waits.\n\n"
        docs = self.handbook("# Overview\n\n" + good * 19, pages=[page(), page("../OLD.md", id="OLD", kind="containers")])
        (self.root / "docs/OLD.md").write_text("# Old\n\n" + bad * 40, encoding="utf-8")
        report = archlens.check_documents(self.root, self.config)
        self.assertIsNone(report["stylePassRate"], "19 sentences: counts only")
        self.assertEqual(report["style"], {"sentences": 19, "passing": 19, "target": 0.8})
        (docs / "README.md").write_text("# Overview\n\n" + good * 16 + bad * 4, encoding="utf-8")
        report = archlens.check_documents(self.root, self.config)
        self.assertEqual(report["stylePassRate"], 0.8)
        notes = {f["path"]: f for f in report["findings"] if f["code"] == "style"}
        self.assertEqual((notes["docs/OLD.md"]["sentences"], notes["docs/OLD.md"]["passing"]), (40, 0))
        self.assertIn("16 of 20 sentences pass", notes["docs/architecture/README.md"]["message"])
        self.assertTrue(all(f["severity"] == "info" for f in notes.values()))

    def test_style_gate_is_opt_in(self):
        good = "The service validates the input.\n\n"
        bad = "The API starts; the worker waits.\n\n"
        docs = self.handbook("# Overview\n\n" + good * 15 + bad * 5)
        self.assertEqual(self.run_cli("check", "--strict")[0], 0, "style never fails strict")
        code, output, _ = self.run_cli("check", "--style")
        self.assertEqual(code, 1)
        self.assertIn("[style-target] Mechanical style pass rate 0.75 is below styleTarget 0.8", output)
        self.assertIn("15 of 20 sentences pass; 75%; target 80%", output)
        write_json(self.root / ".archlens.json", {"styleTarget": 0.7})
        self.assertEqual(self.run_cli("check", "--style")[0], 0)
        (self.root / ".archlens.json").unlink()
        (docs / "README.md").write_text("# Overview\n\n" + good * 16 + bad * 4, encoding="utf-8")
        self.assertEqual(self.run_cli("check", "--style")[0], 0, "the target itself passes")
        (docs / "README.md").write_text("# Overview\n\n" + bad * 5, encoding="utf-8")
        self.assertEqual(self.run_cli("check", "--style")[0], 0, "too few sentences to rate")


class DiagramCheckTests(Fixture):
    SEQUENCE = ("```mermaid\nsequenceDiagram\n    autonumber\n    A->>B: One\n    B-->>A: Two\n    A->>B: Three\n```\n\n")

    def codes(self, path=None):
        return [(f["code"], f["severity"]) for f in archlens.check_documents(self.root, self.config)["findings"]
                if f["code"] != "style" and (path is None or f["path"] == path)]

    def test_step_table_must_match_the_diagram(self):
        table = "| Step | Action |\n|---|---|\n| 1 | Sends one. |\n| 2-3 | Replies. |\n"
        self.handbook("# Flow\n\n" + self.SEQUENCE + table)
        self.assertEqual(self.codes(), [])
        self.handbook("# Flow\n\n" + self.SEQUENCE + table + "| 4 | Does not exist. |\n")
        findings = archlens.check_documents(self.root, self.config)["findings"]
        self.assertEqual([(f["code"], f["severity"], f["line"]) for f in findings], [("sequence-steps", "warning", 15)])
        self.assertIn("step 4, but the diagram has 3", findings[0]["message"])
        self.handbook("# Flow\n\n" + self.SEQUENCE + "| Step | Action |\n|---|---|\n| 1 | Sends one. |\n")
        findings = archlens.check_documents(self.root, self.config)["findings"]
        self.assertEqual([(f["code"], f["severity"]) for f in findings], [("sequence-steps", "info")])
        self.assertIn("without a step row: 2, 3", findings[0]["message"])
        self.assertEqual(self.run_cli("check", "--strict")[0], 0, "an uncovered message is a note")

    def test_step_table_belongs_to_the_diagram_before_it(self):
        other = "| Step | Action |\n|---|---|\n| 9 | Belongs to nothing numbered. |\n"
        unnumbered = self.SEQUENCE.replace("    autonumber\n", "")
        self.handbook("# Flow\n\n" + unnumbered + other)
        self.assertEqual(self.codes(), [("sequence-numbers", "warning")], "no numbers, so no step check")
        self.handbook("# Flow\n\n" + self.SEQUENCE + "```mermaid\nflowchart LR\n A --> B\n```\n\n" + other)
        self.assertEqual(self.codes(), [], "the table follows a flowchart, not the sequence")

    def test_density_uses_the_configured_limit(self):
        nodes = "".join(f"    N{n} --> N{n + 1}\n" for n in range(13))
        self.handbook("# Units\n\n```mermaid\nflowchart LR\n" + nodes + "```\n")
        findings = archlens.check_documents(self.root, self.config)["findings"]
        self.assertEqual([(f["code"], f["severity"]) for f in findings], [("diagram-density", "warning")])
        self.assertIn("14 nodes exceed maxDiagramNodes (12)", findings[0]["message"])
        self.assertEqual(archlens.check_documents(self.root, dict(self.config, maxDiagramNodes=14))["findings"], [])

    def test_adopted_documents_get_notes_not_warnings(self):
        nodes = "".join(f"    N{n} --> N{n + 1}\n" for n in range(13))
        old = ("Old document without a title.\n\n```mermaid\nflowchart LR\n" + nodes + "```\n\n"
               "```mermaid\nsequenceDiagram\n    A->>B: One\n```\n\n[Handbook](architecture/README.md)\n")
        self.handbook(pages=[page(), page("../OLD.md", id="OLD", kind="containers")])
        (self.root / "docs/OLD.md").write_text(old, encoding="utf-8")
        self.assertEqual(sorted(self.codes("docs/OLD.md")), [
            ("diagram-density", "info"), ("missing-title", "info"), ("sequence-numbers", "info")])
        self.assertEqual(self.run_cli("check", "--strict")[0], 0)


class PlacementTests(Fixture):
    def decisions(self, own, adopted):
        docs = self.handbook()
        entries = [page()]
        for n in range(own):
            (docs / f"ADR-{n}.md").write_text(f"# ADR {n}\n", encoding="utf-8")
            entries.append(page(f"ADR-{n}.md", id=f"OWN-{n}", kind="decision", decisionStatus="accepted"))
        (self.root / "docs/adr").mkdir(parents=True, exist_ok=True)
        for n in range(adopted):
            (self.root / f"docs/adr/{n}.md").write_text(f"# Old {n}\n", encoding="utf-8")
            entries.append(page(f"../adr/{n}.md", id=f"OLD-{n}", kind="decision", decisionStatus="accepted"))
        write_json(docs / "map.json", {"version": 1, "pages": entries})
        return [f["path"] for f in archlens.check_documents(self.root, self.config)["findings"] if f["code"] == "decision-split"]

    def test_decision_home_is_where_most_records_live(self):
        self.assertEqual(self.decisions(1, 3), ["docs/architecture/ADR-0.md"])
        self.assertEqual(self.decisions(2, 2), ["docs/architecture/ADR-0.md", "docs/architecture/ADR-1.md"])
        self.assertEqual(self.decisions(3, 1), [], "the handbook is the decision home")
        self.assertEqual(self.decisions(2, 0), [])

    def test_handbook_entry_points(self):
        self.handbook()
        (self.root / "README.md").write_text("# Project\n", encoding="utf-8")

        def unlinked():
            return any(f["code"] == "unlinked-handbook" for f in archlens.check_documents(self.root, self.config)["findings"])

        self.assertTrue(unlinked())
        (self.root / "docs/README.md").write_text("# Docs\n\n[Architecture](architecture/README.md)\n", encoding="utf-8")
        self.assertFalse(unlinked(), "a parent README links it")
        (self.root / "docs/README.md").write_text("# Docs\n\nArchitecture is described elsewhere.\n", encoding="utf-8")
        self.assertTrue(unlinked(), "a bare word is not a pointer")
        (self.root / "AGENTS.md").write_text("# Agents\n\nPages live in `docs/architecture/`.\n", encoding="utf-8")
        self.assertFalse(unlinked(), "a root file names the folder")
        (self.root / "AGENTS.md").unlink()
        (self.root / "mkdocs.yml").write_text("nav:\n  - Architecture: docs/architecture/README.md\n", encoding="utf-8")
        self.assertFalse(unlinked())
        (self.root / "mkdocs.yml").write_bytes(b"\xff\xfe broken")
        self.assertTrue(unlinked(), "an unreadable file is skipped, not fatal")

    def test_commit_ids_need_a_digit(self):
        self.handbook("# Overview\n\nWe commit defaced files never. Observed at commit `c640576`.\n")
        notes = [f for f in archlens.check_documents(self.root, self.config)["findings"] if f["code"] == "prose-metadata"]
        self.assertEqual(len(notes), 1)
        self.handbook("# Overview\n\nWe commit defaced files never. Each commit accedes to the rule.\n")
        self.assertFalse([f for f in archlens.check_documents(self.root, self.config)["findings"] if f["code"] == "prose-metadata"])


@unittest.skipUnless(shutil.which("git"), "Git is required for pre-commit tests")
class PrecommitTests(Fixture):
    SOURCE = ("import os\n\n\ndef validate(order):\n    if order.quantity < 1:\n        raise ValueError('quantity')\n"
              "    return order\n\n\ndef unrelated():\n    return 1\n")

    def setUp(self):
        super().setUp()
        (self.root / "src").mkdir()
        (self.root / "src/svc.py").write_text(self.SOURCE, encoding="utf-8")
        (self.root / "src/other.py").write_text("x = 1\n", encoding="utf-8")
        self.docs = self.handbook("# Orders\n\nThe [validator](../../src/svc.py#L4-L7) rejects bad input.\n",
                                  pages=[page(covers=["src/svc.py"])])
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Archlens Test")
        self.git("config", "user.email", "test@example.invalid")
        archlens.sync_pages(self.root, self.config, [], True)
        self.git("add", ".")
        self.git("commit", "-qm", "baseline")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args]).decode()

    def gate(self, **options):
        return archlens.precommit(self.root, self.config, **options)

    def text(self, report):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            archlens.print_precommit(report)
        return out.getvalue()

    def test_clean_commit_passes(self):
        (self.root / "src/other.py").write_text("x = 2\n", encoding="utf-8")
        self.git("add", ".")
        report = self.gate()
        self.assertFalse(report["failed"])
        self.assertEqual(self.text(report), "Archlens pre-commit: PASS\n")
        self.assertEqual(self.run_cli("precommit")[0], 0)

    def test_moved_code_is_fixed_then_the_commit_is_retried(self):
        (self.root / "src/svc.py").write_text("# header\n" + self.SOURCE, encoding="utf-8")
        self.git("add", ".")
        report = self.gate()
        self.assertTrue(report["failed"])
        self.assertEqual([(item["from"], item["to"]) for item in report["fixed"]], [([4, 7], [5, 8])])
        self.assertIn("svc.py#L5-L8", (self.docs / "README.md").read_text())
        self.assertIn("Stage those pages and docs/architecture/.archlens-state.json", self.text(report))
        self.git("add", ".")
        self.assertFalse(self.gate()["failed"], "the second attempt passes with no model")

    def test_changed_cited_code_blocks_until_the_page_is_synced(self):
        (self.root / "src/svc.py").write_text(self.SOURCE.replace("< 1", "< 2"), encoding="utf-8")
        self.git("add", ".")
        report = self.gate()
        self.assertTrue(report["failed"])
        self.assertEqual([(entry["id"], entry["changed"][0]["symbol"]) for entry in report["stale"]], [("INDEX", "validate")])
        text = self.text(report)
        self.assertIn("STALE docs/architecture/README.md [INDEX] evidence-changed src/svc.py#L4-L7 (validate)", text)
        self.assertIn("sync --root . --page INDEX", text)
        self.assertEqual(self.run_cli("precommit")[0], 1)
        warned = self.gate(stale_mode="warn")
        self.assertFalse(warned["failed"])
        self.assertIn("WARN docs/architecture/README.md", self.text(warned))
        self.assertEqual(self.gate(stale_mode="off")["stale"], [])
        self.assertEqual(self.run_cli("precommit", "--stale", "warn")[0], 0)
        archlens.sync_pages(self.root, self.config, ["INDEX"], False)
        self.git("add", ".")
        self.assertFalse(self.gate()["failed"])

    def test_old_stale_pages_do_not_block_an_unrelated_commit(self):
        (self.root / "src/svc.py").write_text(self.SOURCE.replace("< 1", "< 2"), encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "change without docs", "--no-verify")
        (self.root / "src/other.py").write_text("x = 3\n", encoding="utf-8")
        self.git("add", "src/other.py")
        report = self.gate()
        self.assertFalse(report["failed"])
        self.assertEqual((report["stale"], report["alreadyStale"]), ([], 1))
        self.assertIn("1 other page(s) were stale before this commit", self.text(report))
        self.git("commit", "-qm", "other")
        self.assertTrue(self.gate()["failed"], "with nothing staged (CI), every stale page counts")

    def test_structure_errors_and_new_pages_block(self):
        (self.docs / "README.md").write_text(
            "# Orders\n\nThe [validator](../../src/svc.py#L4-L7) rejects bad input. [Gone](gone.md)\n", encoding="utf-8")
        self.git("add", ".")
        report = self.gate()
        self.assertTrue(report["failed"])
        self.assertEqual([f["code"] for f in report["findings"]], ["local-link"])
        self.assertIn("ERROR docs/architecture/README.md:3 [local-link]", self.text(report))
        (self.docs / "README.md").write_text("# Orders\n\nThe [validator](../../src/svc.py#L4-L7) rejects bad input.\n", encoding="utf-8")
        (self.docs / "new.md").write_text("# New\n\nSee [svc](../../src/svc.py).\n", encoding="utf-8")
        write_json(self.docs / "map.json", {"version": 1, "pages": [
            page(covers=["src/svc.py"]), page("new.md", id="NEW", kind="runtime", covers=["src/other.py"])]})
        self.git("add", ".")
        report = self.gate()
        self.assertEqual([(entry["id"], entry["state"]) for entry in report["stale"]], [("NEW", "unsynced")])
        self.assertIn("STALE docs/architecture/new.md [NEW] never synced", self.text(report))

    def test_style_gate_and_fix_anchors_setting(self):
        bad = "The API starts; the worker waits.\n\n" * 20
        (self.docs / "README.md").write_text("# Orders\n\nThe [validator](../../src/svc.py#L4-L7) rejects bad input.\n\n" + bad, encoding="utf-8")
        self.git("add", ".")
        self.assertFalse(self.gate()["failed"], "style is not gated by default")
        report = self.gate(style_gate=True)
        self.assertTrue(report["failed"])
        self.assertEqual([f["code"] for f in report["findings"]], ["style-target"])
        (self.root / "src/svc.py").write_text("# header\n" + self.SOURCE, encoding="utf-8")
        self.git("add", ".")
        off = archlens.precommit(self.root, dict(self.config, fixAnchors=False))
        self.assertEqual(off["fixed"], [])
        self.assertTrue(off["failed"], "a moved citation stays stale when fixing is off")

    def test_works_without_git(self):
        shutil.rmtree(self.root / ".git")
        self.assertFalse(self.gate()["failed"])
        (self.root / "src/svc.py").write_text(self.SOURCE.replace("< 1", "< 2"), encoding="utf-8")
        self.assertTrue(self.gate()["failed"])


if __name__ == "__main__":
    unittest.main()
