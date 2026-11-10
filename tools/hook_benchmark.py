"""Hook latency as Claude Code sees it: one real process per tool call. No model calls.

Usage: python tools/hook_benchmark.py [--root PROJECT] [--entry FILE] [--runs 9]
--entry tests another hook entry, such as an older release's archlens.py with `hook`.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "plugins/archlens/scripts/hook.py"


def measure(command: list[str], payload: dict, env: dict, runs: int) -> int:
    samples = []
    for index in range(runs):
        data = json.dumps(dict(payload, session_id=f"bench-{index}-{time.time()}")).encode()
        start = time.perf_counter()
        subprocess.run(command, input=data, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        samples.append(time.perf_counter() - start)
    return round(statistics.median(samples) * 1000)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="Project with a handbook (default: this repository)")
    parser.add_argument("--entry", type=Path, default=ENTRY, help="Hook entry script (default: this repository's)")
    parser.add_argument("--file", help="Project-relative documented file for the pointer rows")
    parser.add_argument("--runs", type=int, default=9)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    entry = [sys.executable, str(args.entry.resolve())] + ([] if args.entry.name == "hook.py" else ["hook"])
    with tempfile.TemporaryDirectory() as data, tempfile.TemporaryDirectory() as empty:
        here = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), CLAUDE_PLUGIN_DATA=data)
        elsewhere = dict(here, CLAUDE_PROJECT_DIR=empty)
        documented = str(root / (args.file or "plugins/archlens/scripts/archlens.py"))
        rows = [
            ("Bash call that is not a commit", "commit-gate", {"tool_input": {"command": "ls -la"}}, here),
            ("Read or Edit of a documented file", "file-pointer", {"tool_input": {"file_path": documented}}, here),
            ("Session start", "session-start", {}, here),
            ("Turn end", "stop", {}, here),
            ("Agent commit", "commit-gate", {"tool_input": {"command": "git commit -m x"}}, here),
            ("Any tool call, project without a handbook", "file-pointer", {"tool_input": {"file_path": empty + "/a.py"}}, elsewhere),
        ]
        floor = measure([sys.executable, "-c", "pass"], {}, here, args.runs)
        print(f"{'Python start alone':<44}{floor:>5} ms")
        for name, event, payload, env in rows:
            print(f"{name:<44}{measure(entry + [event], payload, env, args.runs):>5} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
