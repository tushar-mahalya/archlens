"""Deterministic Archlens benchmarks: context footprint and checker speed at scale.

No model calls. Byte counts are not exact tokens; the token column uses bytes/4.
Usage: python tools/benchmark.py [--sizes 1000:20,10000:100,50000:300] [--out FILE]
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins/archlens/scripts/archlens.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


archlens = load(SCRIPT, "archlens")
budget = load(ROOT / "tools/prompt_budget.py", "prompt_budget")


def defaults() -> dict:
    return json.loads((ROOT / "plugins/archlens/defaults.json").read_text(encoding="utf-8"))


def handbook_bytes(root: Path, config: dict) -> int:
    docs = root / config["docsRoot"]
    return sum(p.stat().st_size for p in docs.rglob("*.md"))


def footprint() -> dict:
    report = budget.audit()
    config = defaults()
    maps = {}
    for name, root in (("this repository", ROOT), ("order example", ROOT / "examples/order-service")):
        text = archlens.build_context(root, config)
        size = len(text.encode("utf-8"))
        maps[name] = {
            "mapBytes": size, "roughTokens": (size + 3) // 4,
            "handbookBytes": handbook_bytes(root, config),
            "ratio": round(size / handbook_bytes(root, config), 3),
        }
    return {
        "startupDescriptionBytes": report["startup"]["modelInvocableDescriptionBytes"],
        "sessionMapBudgetBytes": report["startup"]["sessionContextBudgetBytes"],
        "sessionMaps": maps,
        "nativeCommands": {r["command"]: r["requiredColdBytes"] for r in report["routes"]},
        "portableOperations": {r["operation"]: r["requiredColdBytes"] for r in report["portableRoutes"]},
    }


def git(root: Path, *args: str):
    subprocess.run(["git", "-C", str(root), *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def synthetic(root: Path, files: int, pages: int):
    """A Git repository with `files` sources spread across `pages` covered folders."""
    per_folder = max(1, files // pages)
    for n in range(files):
        folder = root / "src" / f"mod{n // per_folder % pages}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"f{n}.py").write_text(f"value_{n} = {n}\n", encoding="utf-8")
    docs = root / "docs/architecture"
    docs.mkdir(parents=True)
    entries = []
    for p in range(pages):
        (docs / f"p{p}.md").write_text(
            f"# Module {p}\n\nModule {p} handles one part of the flow.\n\n"
            f"See [entry](../../src/mod{p}/f{p * per_folder}.py#L1).\n", encoding="utf-8",
        )
        entries.append({
            "path": f"p{p}.md", "id": f"P{p}", "kind": "component", "owner": "bench",
            "reviewState": "draft", "verifiedCommit": None, "covers": [f"src/mod{p}/**"],
        })
    (docs / "map.json").write_text(json.dumps({"version": 1, "pages": entries}), encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "-c", "user.name=bench", "-c", "user.email=bench@example.invalid", "commit", "-qm", "init")


def timed(fn, repeat=3) -> float:
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            fn()
        samples.append(time.perf_counter() - start)
    return round(statistics.median(samples) * 1000)


def performance(sizes) -> list[dict]:
    config = defaults()
    rows = []
    for files, pages in sizes:
        with tempfile.TemporaryDirectory(prefix="archlens-bench-") as folder:
            root = Path(folder).resolve()
            synthetic(root, files, pages)
            sync_ms = timed(lambda: archlens.sync_pages(root, config, [], True), 1)
            for n in range(0, files, max(1, files // 25)):
                path = root / "src" / f"mod{n // max(1, files // pages) % pages}" / f"f{n}.py"
                path.write_text(path.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
            status = archlens.freshness(root, config)
            env = {"CLAUDE_PLUGIN_DATA": str(root / ".bench-data")}
            with patch_env(env):
                stop_ms = timed(lambda: archlens.hook_stop(root, config, {"session_id": str(time.time())}))
            rows.append({
                "files": files, "pages": pages,
                "syncMs": sync_ms,
                "statusMs": timed(lambda: archlens.freshness(root, config)),
                "contextMs": timed(lambda: archlens.build_context(root, config)),
                "stopHookMs": stop_ms,
                "checkMs": timed(lambda: archlens.check_documents(root, config)),
                "stalePages": status["counts"]["stale"],
                "mapBytes": len(archlens.build_context(root, config).encode("utf-8")),
                "stateFileBytes": (root / "docs/architecture/.archlens-state.json").stat().st_size,
            })
    return rows


@contextlib.contextmanager
def patch_env(values: dict):
    old = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def markdown(result: dict) -> str:
    fp = result["footprint"]
    lines = [
        f"Machine: {result['machine']}; Python {result['python']}.",
        "",
        "| Synthetic repo | sync | status | context | Stop hook | check | Map bytes | State file |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in result["performance"]:
        lines.append(
            f"| {r['files']:,} files, {r['pages']} pages | {r['syncMs']:,} ms | {r['statusMs']:,} ms | "
            f"{r['contextMs']:,} ms | {r['stopHookMs']:,} ms | {r['checkMs']:,} ms | {r['mapBytes']:,} | {r['stateFileBytes']:,} |"
        )
    lines += ["", "| Session map | Bytes | ~Tokens | Handbook bytes | Map / handbook |", "|---|---:|---:|---:|---:|"]
    for name, m in fp["sessionMaps"].items():
        lines.append(f"| {name} | {m['mapBytes']:,} | {m['roughTokens']:,} | {m['handbookBytes']:,} | {m['ratio']:.1%} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sizes", default="1000:20,10000:100,50000:300", help="files:pages pairs")
    parser.add_argument("--out", type=Path, help="Write the JSON result here")
    args = parser.parse_args(argv)
    sizes = [tuple(int(x) for x in pair.split(":")) for pair in args.sizes.split(",") if pair]
    result = {
        "machine": f"{platform.system()} {platform.machine()}",
        "python": platform.python_version(),
        "footprint": footprint(),
        "performance": performance(sizes),
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(markdown(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
