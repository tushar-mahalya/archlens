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
        self.assertNotIn("src/a.py", archlens.impact_report(self.root, self.config, None)["changedFiles"])

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


class NewSettingsTests(Fixture):
    def test_new_settings_validation(self):
        for value in (
            {"autoUpdate": "always"}, {"contextBudget": 100}, {"contextBudget": 3000.5},
            {"contextFile": "AGENTS.txt"}, {"contextFile": "../AGENTS.md"}, {"sessionContext": "yes"},
        ):
            with self.subTest(value=value), self.assertRaises(archlens.ArchlensError):
                archlens.validate_config(value, "test")
        valid = archlens.validate_config({"contextFile": None, "autoUpdate": "auto", "contextBudget": 600}, "test")
        self.assertEqual(valid["autoUpdate"], "auto")


class AnchorAndDiagramTests(Fixture):
    def test_line_and_heading_anchors(self):
        docs = self.handbook()
        (self.root / "src").mkdir()
        (self.root / "src/a.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
        (docs / "other.md").write_text("# Other\n\n## Retry rules\n\n## Retry rules\n", encoding="utf-8")
        text = (
            "# Overview\n\n## Local `part`\n\n[ok](../../src/a.py#L2-L3) [bad](../../src/a.py#L9)\n"
            "[h](other.md#retry-rules) [h2](other.md#retry-rules-1) [self](#local-part)\n"
            "[missing](other.md#nowhere)\n"
        )
        self.handbook(text, pages=[page(), page("other.md", id="OTHER")])
        findings = archlens.check_documents(self.root, self.config)["findings"]
        codes = sorted((f["code"], f["severity"]) for f in findings)
        self.assertEqual(codes, [("heading-anchor", "warning"), ("line-anchor", "error")])

    def test_unknown_mermaid_type(self):
        self.handbook("# T\n\n```mermaid\nflowchat LR\n A-->B\n```\n\n```mermaid\n%% note\nflowchart LR\n A-->B\n```\n")
        findings = archlens.check_documents(self.root, self.config)["findings"]
        self.assertEqual([f["code"] for f in findings], ["mermaid-type"])


class ContextTests(Fixture):
    def pages(self, count):
        docs = self.handbook("# Understand this system\n\nOrders move from the API to the database.\n")
        entries = [page()]
        for n in range(count):
            (docs / f"p{n}.md").write_text(f"# Page {n}\n\nThis page explains flow number {n} in detail.\n", encoding="utf-8")
            entries.append(page(f"p{n}.md", id=f"P{n}", kind="runtime", covers=[f"src/p{n}/**"]))
        write_json(docs / "map.json", {"version": 1, "pages": entries})
        return docs

    def test_digest_is_bounded_and_summarized(self):
        self.pages(3)
        text = archlens.build_context(self.root, self.config)
        self.assertIn("`README.md` Understand this system: Orders move from the API to the database.", text)
        self.assertIn("[covers src/p0/**]", text)
        self.assertIn("(4 pages, 0 stale, 4 never synced)", text)
        self.pages(400)
        for budget in (600, 3000):
            text = archlens.build_context(self.root, self.config, budget)
            self.assertLessEqual(len(text.encode("utf-8")), budget)
            self.assertIn("more pages in `docs/architecture/map.json`", text)

    def test_write_block_is_idempotent_and_preserves_text(self):
        self.pages(1)
        target = self.root / "AGENTS.md"
        target.write_text("# Agents\n\nKeep this.\n", encoding="utf-8")
        self.assertEqual(self.run_cli("context", "--write", "AGENTS.md")[0], 0)
        first = target.read_text(encoding="utf-8")
        self.assertTrue(first.startswith("# Agents\n\nKeep this.\n\n<!-- archlens:context:start"))
        self.run_cli("context", "--write", "AGENTS.md")
        self.assertEqual(first, target.read_text(encoding="utf-8"))
        self.assertEqual(first.count("archlens:context:start"), 1)
        self.assertEqual(self.run_cli("context", "--write", "../outside.md")[0], 2)
        self.assertEqual(self.run_cli("context", "--write")[0], 2)

    def test_session_hook_silent_without_handbook_or_when_claude_md_has_block(self):
        self.assertEqual(archlens.hook_session_start(self.root, self.config), "")
        self.pages(1)
        self.assertIn("Architecture handbook", archlens.hook_session_start(self.root, self.config))
        (self.root / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
        self.assertEqual(archlens.hook_session_start(self.root, dict(self.config, contextFile="AGENTS.md")), "")
        self.assertEqual(archlens.hook_session_start(self.root, dict(self.config, sessionContext=False)), "")


@unittest.skipUnless(shutil.which("git"), "Git is required for freshness tests")
class FreshnessTests(Fixture):
    def setUp(self):
        super().setUp()
        self.docs = self.handbook("# Overview\n\nSee [helper](../../lib/helper.py).\n")
        (self.root / "src").mkdir()
        (self.root / "lib").mkdir()
        (self.root / "src/a.py").write_text("a = 1\n", encoding="utf-8")
        (self.root / "lib/helper.py").write_text("h = 1\n", encoding="utf-8")
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Archlens Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "baseline")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args]).decode()

    def state(self):
        return archlens.freshness(self.root, self.config)

    def test_unsynced_then_fresh_then_stale_after_commit(self):
        self.assertEqual(self.state()["counts"]["unsynced"], 1)
        self.assertEqual(self.run_cli("status", "--fail-on-stale")[0], 1)
        archlens.sync_pages(self.root, self.config, [], True)
        self.assertEqual(self.state()["counts"], {"fresh": 1, "stale": 0, "review": 0, "unsynced": 0})
        (self.root / "lib/helper.py").write_text("h = 2\n", encoding="utf-8")
        self.git("commit", "-qam", "change")
        report = self.state()
        self.assertEqual(report["needsSync"][0]["changed"], [{"path": "lib/helper.py", "change": "modified", "severity": "stale"}])
        self.assertEqual(self.run_cli("status", "--fail-on-stale")[0], 1)
        self.assertNotIn("src/a.py", archlens.impact_report(self.root, self.config, None)["changedFiles"])

    def test_added_removed_and_linked_files(self):
        archlens.sync_pages(self.root, self.config, ["INDEX"], False)
        (self.root / "src/new.py").write_text("n = 1\n", encoding="utf-8")
        (self.root / "lib/helper.py").write_text("h = 2\n", encoding="utf-8")
        (self.root / "src/a.py").unlink()
        changed = self.state()["needsSync"][0]["changed"]
        self.assertEqual(changed, [
            {"path": "lib/helper.py", "change": "modified", "severity": "stale"},
            {"path": "src/new.py", "change": "added", "severity": "review"},
            {"path": "src/a.py", "change": "removed", "severity": "review"},
        ])
        archlens.sync_pages(self.root, self.config, ["INDEX"], False)
        self.assertEqual(self.state()["counts"]["fresh"], 1)

    def test_sync_errors_and_state_is_not_a_page(self):
        with self.assertRaises(archlens.ArchlensError):
            archlens.sync_pages(self.root, self.config, ["MISSING"], False)
        with self.assertRaises(archlens.ArchlensError):
            archlens.sync_pages(self.root, self.config, [], False)
        archlens.sync_pages(self.root, self.config, [], True)
        self.assertTrue((self.docs / ".archlens-state.json").is_file())
        self.assertFalse(archlens.check_documents(self.root, self.config)["findings"])

    def test_sync_refreshes_configured_context_file(self):
        write_json(self.root / ".archlens.json", {"contextFile": "AGENTS.md"})
        code, output, _ = self.run_cli("sync", "--all", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["contextFile"], "AGENTS.md")
        self.assertIn("archlens:context:start", (self.root / "AGENTS.md").read_text(encoding="utf-8"))

    def test_non_git_projects_use_content_ids(self):
        with tempfile.TemporaryDirectory(prefix="archlens-plain-") as folder:
            root = Path(folder).resolve()
            shutil.copytree(self.root, root, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
            archlens.sync_pages(root, self.config, [], True)
            (root / "src/a.py").write_text("a = 3\n", encoding="utf-8")
            self.assertEqual(archlens.freshness(root, self.config)["counts"]["review"], 1)
            (root / "lib/helper.py").write_text("h = 3\n", encoding="utf-8")
            self.assertEqual(archlens.freshness(root, self.config)["counts"]["stale"], 1)

    def test_nested_project_with_uncommitted_changes(self):
        nested = self.root / "nested"
        (nested / "docs/architecture").mkdir(parents=True)
        (nested / "app.py").write_text("x = 1\n", encoding="utf-8")
        (nested / "docs/architecture/README.md").write_text("# Nested\n\nSee [app](../../app.py).\n", encoding="utf-8")
        write_json(nested / "docs/architecture/map.json", {"version": 1, "pages": [page(covers=[])]})
        self.git("add", ".")
        self.git("commit", "-qm", "nested")
        (nested / "app.py").write_text("x = 2\n", encoding="utf-8")
        (nested / "new.py").write_text("y = 1\n", encoding="utf-8")
        archlens.sync_pages(nested, self.config, [], True)
        self.assertEqual(archlens.freshness(nested, self.config)["counts"]["fresh"], 1)
        (nested / "app.py").write_text("x = 3\n", encoding="utf-8")
        self.assertEqual(archlens.freshness(nested, self.config)["counts"]["stale"], 1)

    def test_impact_includes_linked_evidence(self):
        (self.root / "lib/helper.py").write_text("h = 3\n", encoding="utf-8")
        report = archlens.impact_report(self.root, self.config, None)
        self.assertEqual(report["candidates"][0]["changedSources"], ["lib/helper.py"])
        self.assertEqual(report["uncoveredFiles"], [])

    def test_stop_hook_modes(self):
        archlens.sync_pages(self.root, self.config, [], True)
        data = self.root / "plugin-data"
        with patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": str(data)}):
            self.assertIsNone(archlens.hook_stop(self.root, self.config, {"session_id": "s"}))
            (self.root / "src/a.py").write_text("a = 4\n", encoding="utf-8")
            self.assertIsNone(archlens.hook_stop(self.root, self.config, {"session_id": "s"}))
            (self.root / "lib/helper.py").write_text("h = 4\n", encoding="utf-8")
            first = archlens.hook_stop(self.root, self.config, {"session_id": "s"})
            self.assertIn("/archlens:update", first["systemMessage"])
            self.assertIsNone(archlens.hook_stop(self.root, self.config, {"session_id": "s"}))
            auto = dict(self.config, autoUpdate="auto")
            blocked = archlens.hook_stop(self.root, auto, {"session_id": "t"})
            self.assertEqual(blocked["decision"], "block")
            self.assertIn("INDEX", blocked["reason"])
            self.assertNotIn("decision", archlens.hook_stop(self.root, auto, {"session_id": "u", "stop_hook_active": True}))
            self.assertIsNone(archlens.hook_stop(self.root, dict(self.config, autoUpdate="off"), {"session_id": "v"}))

    def test_marker_folder_rejects_symlinks(self):
        target = self.root / "elsewhere"
        target.mkdir()
        link = self.root / "data-link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"Symlinks unavailable: {exc}")
        with patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": str(link)}):
            self.assertIsNone(archlens.marker_folder())
        with patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": str(self.root / "private")}):
            self.assertEqual(archlens.marker_folder(), self.root / "private")

    def test_hook_entrypoint_never_fails(self):
        for stdin in ("not json", "[]", ""):
            with self.subTest(stdin=stdin), patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)}), \
                    patch("sys.stdin", io.StringIO(stdin)):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(archlens.main(["hook", "stop"]), 0)
        write_json(self.root / ".archlens.json", {"bad": 1})
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)}), patch("sys.stdin", io.StringIO("{}")):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(archlens.main(["hook", "session-start"]), 0)
            self.assertEqual(out.getvalue(), "")


@unittest.skipUnless(shutil.which("git"), "Git is required for anchor tests")
class AnchorTests(Fixture):
    SOURCE = (
        "import os\n\n\n"
        "def validate(order):\n"
        "    if order.quantity < 1:\n"
        "        raise ValueError('quantity')\n"
        "    return order\n\n\n"
        "def unrelated():\n"
        "    return 1\n"
    )

    def setUp(self):
        super().setUp()
        (self.root / "src").mkdir()
        (self.root / "src/svc.py").write_text(self.SOURCE, encoding="utf-8")
        (self.root / "src/app.js").write_text("const a = 1;\nfunction go() {\n  return a;\n}\n", encoding="utf-8")
        self.handbook(
            "# Orders\n\nThe [validator](../../src/svc.py#L4-L7) rejects bad input.\n"
            "The [entry](../../src/app.js#L2-L4) starts it.\n",
            pages=[page(covers=["src/**"])],
        )
        subprocess.check_call(["git", "-C", str(self.root), "init", "-q"])
        archlens.sync_pages(self.root, self.config, [], True)

    def changes(self):
        entry = archlens.freshness(self.root, self.config)["needsSync"]
        return entry[0]["state"] if entry else "fresh", (entry[0]["changed"] if entry else [])

    def write(self, name, text):
        (self.root / name).write_text(text, encoding="utf-8")

    def test_records_python_symbol(self):
        record = archlens.load_state(self.root / "docs/architecture")["pages"]["INDEX"]["anchors"]
        self.assertEqual([a.get("symbol") for a in record], [None, "validate"])

    def test_edit_outside_cited_evidence_is_review(self):
        self.write("src/svc.py", self.SOURCE.replace("return 1", "return 2"))
        state, changes = self.changes()
        self.assertEqual(state, "review")
        self.assertEqual(changes, [{"path": "src/svc.py", "change": "modified", "severity": "review"}])

    def test_comment_and_blank_line_inside_symbol_are_ignored(self):
        self.write("src/svc.py", self.SOURCE.replace("    return order\n", "    # checked\n\n    return order\n"))
        self.assertEqual(self.changes()[0], "review")

    def test_moved_symbol_reports_new_lines(self):
        self.write("src/svc.py", "# header\n# more\n" + self.SOURCE)
        state, changes = self.changes()
        self.assertEqual(state, "stale")
        self.assertIn({"path": "src/svc.py", "lines": [4, 7], "symbol": "validate", "change": "evidence-moved",
                       "newLines": [6, 9], "severity": "stale"}, changes)

    def test_changed_and_removed_symbol(self):
        self.write("src/svc.py", self.SOURCE.replace("< 1", "< 2"))
        self.assertEqual(self.changes()[1][0]["change"], "evidence-changed")
        self.write("src/svc.py", self.SOURCE.replace("def validate", "def check"))
        self.assertEqual(self.changes()[1][0]["change"], "symbol-removed")

    def test_fix_anchors_rewrites_moved_links(self):
        self.write("src/svc.py", "# header\n# more\n" + self.SOURCE)
        self.write("src/app.js", "// banner\nconst a = 1;\nfunction go() {\n  return a;\n}\n")
        report = archlens.fix_anchors(self.root, self.config)
        self.assertEqual(sorted((f["path"], tuple(f["to"])) for f in report["fixed"]), [("src/app.js", (3, 5)), ("src/svc.py", (6, 9))])
        text = (self.root / "docs/architecture/README.md").read_text(encoding="utf-8")
        self.assertIn("../../src/svc.py#L6-L9)", text)
        self.assertIn("../../src/app.js#L3-L5)", text)
        state, changes = self.changes()
        self.assertEqual(state, "review")
        self.assertFalse([c for c in changes if c["severity"] == "stale"])
        self.assertEqual(archlens.fix_anchors(self.root, self.config)["fixed"], [])

    def test_text_anchor_moves_and_changes(self):
        self.write("src/app.js", "// banner\nconst a = 1;\nfunction go() {\n  return a;\n}\n")
        moved = [c for c in self.changes()[1] if c["path"] == "src/app.js" and c["change"] == "evidence-moved"]
        self.assertEqual(moved[0]["newLines"], [3, 5])
        self.write("src/app.js", "const a = 1;\nfunction go() {\n  return a + 1;\n}\n")
        self.assertIn("evidence-changed", [c["change"] for c in self.changes()[1]])


@unittest.skipUnless(shutil.which("git"), "Git is required for reference and pointer tests")
class ReferenceAndPointerTests(Fixture):
    def setUp(self):
        super().setUp()
        (self.root / "src").mkdir()
        (self.root / "src/orders.py").write_text("def submit_order():\n    return 1\n", encoding="utf-8")
        write_json(self.root / "package.json", {"scripts": {"test": "x"}})
        subprocess.check_call(["git", "-C", str(self.root), "init", "-q"])
        self.handbook(
            "# Orders\n\nCall `submit_order()` from `src/orders.py`. Run `npm run test`.\n"
            "Old: `cancel_order()`, `src/gone.py`, `npm run build`. Ignore `origin/main` and `src/**`.\n",
            pages=[page(covers=["src/**"])],
        )
        subprocess.check_call(["git", "-C", str(self.root), "add", "."])

    def test_stale_references(self):
        findings = [f for f in archlens.check_documents(self.root, self.config)["findings"] if f["code"] == "stale-reference"]
        self.assertEqual(sorted(f["message"] for f in findings), [
            "Path not found: src/gone.py",
            "Symbol not found in the repository: cancel_order()",
            "npm script not found in package.json: build",
        ])

    def test_file_pointer_once_per_page(self):
        payload = {"session_id": "p", "tool_input": {"file_path": str(self.root / "src/orders.py")}}
        with patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": str(self.root / ".data")}):
            first = archlens.hook_file_pointer(self.root, self.config, payload)
            self.assertIn("docs/architecture/README.md", first["hookSpecificOutput"]["additionalContext"])
            self.assertIsNone(archlens.hook_file_pointer(self.root, self.config, payload))
            other = {"session_id": "p", "tool_input": {"file_path": str(self.root / "package.json")}}
            self.assertIsNone(archlens.hook_file_pointer(self.root, self.config, other))
            docs_page = {"session_id": "q", "tool_input": {"file_path": str(self.root / "docs/architecture/README.md")}}
            self.assertIsNone(archlens.hook_file_pointer(self.root, self.config, docs_page))
            self.assertIsNone(archlens.hook_file_pointer(self.root, dict(self.config, filePointers=False), dict(payload, session_id="r")))

    def test_static_map_has_no_stale_flags(self):
        archlens.sync_pages(self.root, self.config, [], True)
        (self.root / "src/orders.py").write_text("def submit_order():\n    return 2\n", encoding="utf-8")
        live = archlens.build_context(self.root, self.config)
        static = archlens.build_context(self.root, self.config, live=False)
        self.assertIn("STALE", live)
        self.assertNotIn("STALE", static)
        self.assertIn("run the Archlens `status` check", static)


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
