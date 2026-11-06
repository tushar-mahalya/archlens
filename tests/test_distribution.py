import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DistributionTests(unittest.TestCase):
    def test_prompt_budgets(self):
        report = load_tool("prompt_budget").audit()
        self.assertTrue(report["ok"], report["errors"])
        documentation = (ROOT / "docs/context-efficiency.md").read_text(encoding="utf-8")
        for route in report["portableRoutes"]:
            row = (
                f"| {route['operation']} | {route['baseBytes']:,} bytes | "
                f"{route['requiredColdBytes']:,} bytes |"
            )
            self.assertIn(row, documentation)

    def test_prompt_budget_rejects_a_missing_portable_route(self):
        tool = load_tool("prompt_budget")
        with tempfile.TemporaryDirectory() as folder:
            portable = Path(folder) / "archlens"
            shutil.copytree(ROOT / "skills/archlens", portable, ignore=shutil.ignore_patterns("__pycache__"))
            router = portable / "SKILL.md"
            router.write_text(router.read_text(encoding="utf-8").replace("workflows/explain.md", "missing.md"), encoding="utf-8")
            with patch.object(tool, "PORTABLE", portable):
                self.assertTrue(any("explain workflow" in error for error in tool.audit()["errors"]))

    def test_portable_resources_are_current_and_self_contained(self):
        tool = load_tool("sync_portable")
        self.assertEqual(tool.audit(), [])
        skill = ROOT / "skills/archlens"
        text = (skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: archlens\n"))
        self.assertIn("\nlicense: MIT\n", text)
        self.assertEqual(
            (skill / "LICENSE").read_text(encoding="utf-8"),
            (ROOT / "LICENSE").read_text(encoding="utf-8"),
        )
        for path in skill.rglob("*.md"):
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", content, str(path))
            self.assertNotIn("$ARGUMENTS", content, str(path))

    def test_generator_detects_stale_and_unexpected_resources(self):
        tool = load_tool("sync_portable")
        with tempfile.TemporaryDirectory() as folder, patch.object(tool, "PORTABLE", Path(folder)):
            router = Path(folder) / "SKILL.md"
            router.write_text("portable router", encoding="utf-8")
            self.assertEqual(tool.generate(), [])
            target = Path(folder) / "workflows/explain.md"
            target.write_text("stale", encoding="utf-8")
            self.assertTrue(any("Stale generated resource" in error for error in tool.audit()))
            self.assertEqual(tool.generate(), [])
            (Path(folder) / "workflows/unexpected.md").write_text("extra", encoding="utf-8")
            self.assertTrue(any("Unexpected generated resource" in error for error in tool.audit()))
            (Path(folder) / "unexpected.md").write_text("extra", encoding="utf-8")
            self.assertTrue(any("unexpected.md" in error for error in tool.audit()))
            router.unlink()
            self.assertTrue(any("Missing portable router" in error for error in tool.audit()))

    def test_manifest_paths_and_version(self):
        market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(market["name"], "archlens")
        entry = market["plugins"][0]
        plugin = ROOT / entry["source"]
        manifest = json.loads((plugin / ".claude-plugin/plugin.json").read_text())
        self.assertEqual(manifest["name"], entry["name"])
        self.assertEqual(manifest["version"], market["metadata"]["version"])
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual((plugin / "LICENSE").read_text(), (ROOT / "LICENSE").read_text())
        package = json.loads((ROOT / "package.json").read_text())
        lock = json.loads((ROOT / "package-lock.json").read_text())
        self.assertEqual(package["version"], manifest["version"])
        self.assertEqual(lock["version"], manifest["version"])
        self.assertEqual(lock["packages"][""]["version"], manifest["version"])

    def test_reproducible_complete_archive(self):
        tool = load_tool("package_release")
        with tempfile.TemporaryDirectory() as folder:
            first = tool.build(Path(folder) / "first")
            second = tool.build(Path(folder) / "second")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                names = archive.namelist()
                self.assertTrue(any(name.endswith("/.claude-plugin/marketplace.json") for name in names))
                self.assertTrue(any(name.endswith("/scripts/archlens.py") for name in names))
                self.assertTrue(any(name.endswith("/plugins/archlens/LICENSE") for name in names))
                self.assertTrue(any(name.endswith("/skills/archlens/LICENSE") for name in names))
                self.assertTrue(any(name.endswith("/skills/archlens/workflows/setup.md") for name in names))
                self.assertEqual(sum(name.endswith("/SKILL.md") for name in names), 6)
                self.assertFalse(any("\\" in name or ".validation" in name or "__pycache__" in name for name in names))
                for path in (ROOT / "skills/archlens").rglob("*"):
                    if path.is_file() and "__pycache__" not in path.parts:
                        self.assertIn(f"{first.stem}/{path.relative_to(ROOT).as_posix()}", names)
                for name in names:
                    relative = name.split("/", 1)[1]
                    self.assertEqual(archive.read(name), (ROOT / relative).read_bytes())


if __name__ == "__main__":
    unittest.main()
