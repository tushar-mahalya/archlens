import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("archlens", ROOT / "plugins/archlens/scripts/archlens.py")
archlens = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archlens)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def page(path="README.md", **changes):
    result = {
        "path": path, "id": "INDEX", "kind": "index", "owner": "test",
        "reviewState": "draft", "verifiedCommit": None, "covers": ["src/**"],
    }
    result.update(changes)
    return result


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="archlens-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.env = {"CLAUDE_CONFIG_DIR": str(self.root / "user")}
        self.environment = patch.dict(os.environ, self.env)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.previous_explicit = os.environ.pop("ARCHLENS_CONFIG", None)
        self.addCleanup(self.restore_explicit)
        self.config = json.loads((archlens.PLUGIN_ROOT / "defaults.json").read_text())

    def restore_explicit(self):
        os.environ.pop("ARCHLENS_CONFIG", None)
        if self.previous_explicit is not None:
            os.environ["ARCHLENS_CONFIG"] = self.previous_explicit

    def handbook(self, text="# Overview\n\nClear text.\n", pages=None):
        docs = self.root / "docs/architecture"
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "README.md").write_text(text, encoding="utf-8")
        write_json(docs / "map.json", {"version": 1, "pages": pages or [page()]})
        return docs

    def run_cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = archlens.main([*args, "--root", str(self.root)])
        return code, stdout.getvalue(), stderr.getvalue()


class ConfigurationTests(Fixture):
    def test_precedence_and_normalization(self):
        write_json(self.root / "user/archlens.json", {"maxDiagramNodes": 9, "styleTarget": 0.9})
        write_json(self.root / ".archlens.json", {"maxDiagramNodes": 7, "docsRoot": "manual\\architecture"})
        config, sources = archlens.load_config(self.root, self.env)
        self.assertEqual(config["maxDiagramNodes"], 7)
        self.assertEqual(config["styleTarget"], 0.9)
        self.assertEqual(config["docsRoot"], "manual/architecture")
        self.assertEqual(len(sources), 3)

    def test_explicit_config_path(self):
        write_json(self.root / "custom.json", {"styleTarget": 0.7})
        config, _ = archlens.load_config(self.root, {"ARCHLENS_CONFIG": str(self.root / "custom.json")})
        self.assertEqual(config["styleTarget"], 0.7)
        with self.assertRaises(archlens.ArchlensError):
            archlens.load_config(self.root, {"ARCHLENS_CONFIG": str(self.root / "missing.json")})

    def test_shared_config_and_legacy_fallback(self):
        home = self.root / "home"
        shared = self.root / "xdg/archlens/config.json"
        legacy = home / ".claude/archlens.json"
        write_json(legacy, {"styleTarget": 0.6})
        with patch.object(Path, "home", return_value=home):
            config, sources = archlens.load_config(self.root, {"XDG_CONFIG_HOME": str(self.root / "xdg")})
            self.assertEqual(config["styleTarget"], 0.6)
            self.assertIn(str(legacy), sources)
            write_json(shared, {"styleTarget": 0.7})
            config, sources = archlens.load_config(self.root, {"XDG_CONFIG_HOME": str(self.root / "xdg")})
            self.assertEqual(config["styleTarget"], 0.7)
            self.assertIn(str(shared), sources)
            self.assertNotIn(str(legacy), sources)
            write_json(home / ".config/archlens/config.json", {"styleTarget": 0.8})
            config, _ = archlens.load_config(self.root, {})
            self.assertEqual(config["styleTarget"], 0.8)

    def test_shared_config_precedence_and_errors(self):
        shared = self.root / "xdg/archlens/config.json"
        claude = self.root / "user/archlens.json"
        explicit = self.root / "custom.json"
        write_json(shared, {"styleTarget": 0.6})
        write_json(claude, {"styleTarget": 0.7})
        write_json(explicit, {"styleTarget": 0.8})
        env = {"XDG_CONFIG_HOME": str(self.root / "xdg"), "CLAUDE_CONFIG_DIR": str(claude.parent)}
        self.assertEqual(archlens.load_config(self.root, env)[0]["styleTarget"], 0.7)
        env["ARCHLENS_CONFIG"] = str(explicit)
        self.assertEqual(archlens.load_config(self.root, env)[0]["styleTarget"], 0.8)
        write_json(self.root / ".archlens.json", {"styleTarget": 0.9})
        self.assertEqual(archlens.load_config(self.root, env)[0]["styleTarget"], 0.9)
        shared.write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(archlens.ArchlensError, "Cannot read JSON"):
            archlens.load_config(self.root, {"XDG_CONFIG_HOME": str(self.root / "xdg")})

    def test_invalid_settings(self):
        cases = [
            {"docsRoot": "../outside"}, {"docsRoot": "C:\\outside"},
            {"docsRoot": "/absolute"}, {"docsRoot": "."}, {"docsRoot": "docs//x"},
            {"styleTarget": True}, {"styleTarget": 1.01}, {"styleTarget": -0.1},
            {"maxDiagramNodes": 1}, {"maxDiagramNodes": 3.5},
            {"maxSequenceParticipants": False}, {"unknown": 1}, [],
        ]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(archlens.ArchlensError):
                archlens.validate_config(value, "test")

    def test_invalid_json_and_duplicate_keys(self):
        target = self.root / ".archlens.json"
        for text in ('{"styleTarget":0.8,"styleTarget":0.9}', "{", '{"styleTarget":NaN}'):
            target.write_text(text, encoding="utf-8")
            with self.subTest(text=text), self.assertRaises(archlens.ArchlensError):
                archlens.load_config(self.root, self.env)

    def test_missing_optional_files_and_json_errors(self):
        code, output, error = self.run_cli("config", "--json")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output)["ok"])
        self.assertEqual(error, "")
        write_json(self.root / ".archlens.json", {"bad": True})
        code, output, _ = self.run_cli("config", "--json")
        self.assertEqual(code, 2)
        self.assertIn("unknown settings", json.loads(output)["error"])

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as outside:
            try:
                (self.root / "escape").symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"Symlinks unavailable: {exc}")
            with self.assertRaises(archlens.ArchlensError):
                archlens.contained(self.root, "escape/file.md", "test")
            outside_config = Path(outside) / "config.json"
            outside_config.write_text("{}")
            (self.root / ".archlens.json").symlink_to(outside_config)
            with self.assertRaises(archlens.ArchlensError):
                archlens.load_config(self.root, self.env)


class MapTests(Fixture):
    def test_valid_map(self):
        self.handbook()
        _, pages = archlens.load_map(self.root, self.config)
        self.assertEqual(pages[0]["id"], "INDEX")

    def test_missing_map_is_error(self):
        code, output, _ = self.run_cli("check", "--json")
        self.assertEqual(code, 2)
        self.assertIn("/archlens:setup", json.loads(output)["error"])

    def test_invalid_page_metadata(self):
        cases = [
            [page(), page("other.md")],
            [page(), page("readme.md", id="OTHER")],
            [page("../escape.md")], [page(kind="other")],
            [page(owner="")], [page(reviewState="approved")],
            [page(verifiedCommit="HEAD")], [page(covers="src/*")],
            [page(covers=["src/[ab].py"])], [page(decisionStatus="accepted")],
            [page(kind="decision")], [page(kind="decision", decisionStatus="inferred")],
            [page(unknown=True)], [page(kind=[])], [page(covers=[False])],
        ]
        for pages in cases:
            self.handbook(pages=pages)
            with self.subTest(pages=pages), self.assertRaises(archlens.ArchlensError):
                archlens.load_map(self.root, self.config)

    def test_valid_decision(self):
        self.handbook(pages=[page(kind="decision", decisionStatus="proposed")])
        archlens.load_map(self.root, self.config)

    def test_version_and_empty_map(self):
        docs = self.handbook()
        for value in ({"version": True, "pages": [page()]}, {"version": 1, "pages": []}, []):
            write_json(docs / "map.json", value)
            with self.subTest(value=value), self.assertRaises(archlens.ArchlensError):
                archlens.load_map(self.root, self.config)


class GlobTests(unittest.TestCase):
    def test_segment_semantics(self):
        cases = [
            ("src/**", "src/a/b.py", True), ("src/*", "src/a/b.py", False),
            ("**/*.py", "a.py", True), ("**/*.py", "src/a.py", True),
            ("src/**/file?.py", "src/file1.py", True),
            ("src/**/file?.py", "src/a/b/file2.py", True),
            ("src/**/file?.py", "src/file22.py", False),
            ("*.py", "src/a.py", False), ("src\\**", "src/a.py", True),
        ]
        for pattern, path, expected in cases:
            with self.subTest(pattern=pattern, path=path):
                self.assertEqual(bool(archlens.glob_regex(pattern).fullmatch(path)), expected)

    def test_invalid_globs(self):
        for pattern in ("", "!src/**", "src/**x", "../**", "src/{a,b}", "**/[ab]"):
            with self.subTest(pattern=pattern), self.assertRaises(archlens.ArchlensError):
                archlens.glob_regex(pattern)


class CheckTests(Fixture):
    def test_links_fences_and_style(self):
        self.handbook(
            "# Overview\n\n[Missing](missing.md)\n\nText; with a semicolon.\n\n"
            "```mermaid\nsequenceDiagram\n participant A\n participant B\n A->>B: Hello\n```\n"
            "```text\n[Ignored](missing-code.md)\n```\n"
        )
        report = archlens.check_documents(self.root, self.config)
        codes = [item["code"] for item in report["findings"]]
        self.assertEqual(codes.count("local-link"), 1)
        self.assertIn("semicolon", codes)
        self.assertIn("sequence-numbers", codes)
        self.assertIsNone(report["stylePassRate"])

    def test_unmapped_and_missing_pages(self):
        docs = self.handbook(pages=[page("missing.md")])
        (docs / "extra.md").write_text("# Extra", encoding="utf-8")
        codes = [item["code"] for item in archlens.check_documents(self.root, self.config)["findings"]]
        self.assertEqual(codes.count("unmapped-page"), 2)
        self.assertIn("missing-page", codes)

    def test_unclosed_and_nested_fences(self):
        self.handbook("# Title\n\n````text\n```mermaid\nignored\n```\n````\n")
        report = archlens.check_documents(self.root, self.config)
        self.assertFalse(report["findings"])
        self.assertEqual(report["mermaidBlocks"], 0)
        self.handbook("# Title\n\n~~~mermaid\nflowchart LR\n")
        self.assertEqual(archlens.check_documents(self.root, self.config)["findings"][0]["code"], "unclosed-block")

    def test_link_paths_reference_definitions_and_escape(self):
        docs = self.handbook()
        (self.root / "source file.py").write_text("", encoding="utf-8")
        (docs / "test(x).md").write_text("# X", encoding="utf-8")
        text = "[A](../../source%20file.py#L1)\n[B](test(x).md)\n[C]: ../../source%20file.py"
        targets = [target for line in text.splitlines() for target in archlens.local_targets(line)]
        self.assertEqual(len(targets), 3)
        for target in targets:
            self.assertIsNone(archlens.check_link(self.root, docs / "README.md", target))
        for target in ("../../../../outside", "file:///private.txt", "javascript:alert"):
            self.assertIsNotNone(archlens.check_link(self.root, docs / "README.md", target))

    def test_default_and_strict_exit_codes(self):
        self.handbook("# Overview\n\nText; with a semicolon.\n")
        self.assertEqual(self.run_cli("check")[0], 0)
        self.assertEqual(self.run_cli("check", "--strict")[0], 1)
        self.handbook("# Overview\n\n[Missing](missing.md)\n")
        code, output, _ = self.run_cli("check", "--json")
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(output)["ok"])

    def test_example_passes(self):
        report = archlens.check_documents(ROOT / "examples/order-service", self.config)
        self.assertFalse([f for f in report["findings"] if f["severity"] == "error"], report)
        self.assertEqual(report["mermaidBlocks"], 4)

    def test_read_only(self):
        docs = self.handbook()
        before = {p: p.read_bytes() for p in docs.rglob("*") if p.is_file()}
        self.run_cli("check", "--summary")
        self.assertEqual(before, {p: p.read_bytes() for p in docs.rglob("*") if p.is_file()})

    def test_summary_error_is_bounded(self):
        write_json(self.root / ".archlens.json", {"x" * 20000: True})
        code, output, _ = self.run_cli("config", "--summary")
        self.assertEqual(code, 2)
        self.assertLessEqual(len(output.encode("utf-8").rstrip()), 6000)
        self.assertTrue(json.loads(output)["errorTruncated"])


@unittest.skipUnless(shutil.which("git"), "Git is required for impact integration tests")
class ImpactTests(Fixture):
    def setUp(self):
        super().setUp()
        self.handbook()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Archlens Test")
        self.git("config", "user.email", "test@example.invalid")
        (self.root / "src").mkdir()
        (self.root / "src/a.py").write_text("a = 1\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "baseline")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.root), *args], stderr=subprocess.STDOUT,
        ).decode("utf-8")

    def test_staged_unstaged_untracked_and_rename(self):
        self.git("mv", "src/a.py", "src/renamed.py")
        (self.root / "src/renamed.py").write_text("a = 2\n", encoding="utf-8")
        (self.root / "new file.txt").write_text("unknown", encoding="utf-8")
        report = archlens.impact_report(self.root, self.config, None)
        self.assertEqual(report["changedFiles"], ["new file.txt", "src/a.py", "src/renamed.py"])
        self.assertEqual(report["uncoveredFiles"], ["new file.txt"])
        self.assertEqual(report["candidates"][0]["changedSources"], ["src/a.py", "src/renamed.py"])

    def test_branch_changes_use_merge_base(self):
        self.git("checkout", "-b", "feature")
        (self.root / "src/a.py").write_text("a = 2\n", encoding="utf-8")
        self.git("commit", "-am", "change")
        report = archlens.impact_report(self.root, self.config, "main")
        self.assertEqual(report["mergeBase"], self.base)
        self.assertEqual(report["changedFiles"], ["src/a.py"])
        self.assertFalse(archlens.impact_report(self.root, self.config, None)["changedFiles"])

    def test_changed_page_does_not_clear_impact(self):
        (self.root / "src/a.py").unlink()
        (self.root / "docs/architecture/README.md").write_text("# Updated\n", encoding="utf-8")
        report = archlens.impact_report(self.root, self.config, None)
        self.assertTrue(report["candidates"][0]["pageAlsoChanged"])
        self.assertEqual(self.run_cli("impact", "--fail-on-impact")[0], 1)
        self.assertEqual(self.run_cli("impact")[0], 0)

    def test_invalid_base_and_option_injection(self):
        for value in ("missing-branch", "--help", ""):
            with self.subTest(value=value), self.assertRaises(archlens.ArchlensError):
                archlens.changed_files(self.root, value)

    def test_subdirectory_root_rejected(self):
        with self.assertRaises(archlens.ArchlensError):
            archlens.changed_files(self.root / "src", None)

    def test_unborn_repository(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            subprocess.check_call(["git", "-C", str(root), "init", "-q"])
            (root / "new.py").write_text("x = 1")
            self.assertEqual(archlens.changed_files(root, None)[0], ["new.py"])


class SummaryTests(unittest.TestCase):
    def test_large_report_is_bounded_and_omissions_are_exact(self):
        findings = [{"path": f"page-{n}.md", "message": "x" * 1000} for n in range(1000)]
        full = {"command": "check", "ok": False, "findings": findings}
        summary = archlens.bounded_report(full)
        self.assertLessEqual(len(json.dumps(summary).encode()), 6000)
        self.assertEqual(summary["totals"]["findings"], 1000)
        self.assertEqual(summary["omitted"]["findings"] + len(summary["findings"]), 1000)
        self.assertFalse(summary["ok"])
        self.assertEqual(full["findings"], findings)

    def test_huge_metadata_and_records(self):
        for report in (
            {"command": "config", "ok": True, "config": {"path": "x" * 20000}},
            {"command": "impact", "ok": False, "candidates": [{"path": "x" * 20000}]},
        ):
            summary = archlens.bounded_report(report)
            self.assertLessEqual(len(json.dumps(summary).encode()), 6000)
            self.assertEqual(summary["ok"], report["ok"])


class ExampleTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("order_service", ROOT / "examples/order-service/order_service.py")
        self.service = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.service)
        self.db = self.service.connect()
        self.addCleanup(self.db.close)

    def test_repeat_returns_same_order(self):
        first = self.service.submit_order(self.db, "key", "BOOK", 2)
        self.assertEqual(first, self.service.submit_order(self.db, "key", "BOOK", 2))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 1)

    def test_conflict_preserves_original(self):
        self.service.submit_order(self.db, "key", "BOOK", 2)
        with self.assertRaises(self.service.RequestConflict):
            self.service.submit_order(self.db, "key", "OTHER", 3)
        self.assertEqual(self.db.execute("SELECT sku, quantity FROM orders").fetchone(), ("BOOK", 2))

    def test_invalid_input_never_writes(self):
        for key, sku, quantity in (("", "A", 1), ("k", "", 1), ("k", "A", True), ("k", "A", 0)):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                self.service.submit_order(self.db, key, sku, quantity)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
