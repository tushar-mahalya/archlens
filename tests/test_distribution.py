import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
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
                self.assertEqual(sum(name.endswith("/SKILL.md") for name in names), 5)
                self.assertFalse(any("\\" in name or ".validation" in name or "__pycache__" in name for name in names))
                for name in names:
                    relative = name.split("/", 1)[1]
                    self.assertEqual(archive.read(name), (ROOT / relative).read_bytes())


if __name__ == "__main__":
    unittest.main()
