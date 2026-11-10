#!/usr/bin/env python3
"""Fast entry for the Claude Code hooks. Python 3.9+.

Claude Code runs a hook for every tool call, in every project. Most calls need nothing:
the command is not a commit, or the project has no handbook. This file answers those
cases before it loads the checker, and loads the checker as a cached module otherwise.
It never fails the session and prints nothing unless the checker has something to say."""

import json
import os
import sys


def user_config_exists() -> bool:
    """A user preference file can move the handbook, so only the checker can decide."""
    home = os.path.expanduser("~")
    explicit = os.environ.get("ARCHLENS_CONFIG")
    claude = os.environ.get("CLAUDE_CONFIG_DIR")
    shared = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    candidates = [os.path.join(shared, "archlens", "config.json"), os.path.join(home, ".claude", "archlens.json")]
    if claude:
        candidates.append(os.path.join(claude, "archlens.json"))
    return bool(explicit) or any(os.path.isfile(path) for path in candidates)


def nothing_to_do(event: str, raw: str) -> bool:
    if event == "commit-gate" and "commit" not in raw:
        return True
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        return True
    cwd = payload.get("cwd") if isinstance(payload, dict) else None
    root = os.environ.get("CLAUDE_PROJECT_DIR") or (cwd if isinstance(cwd, str) else None) or os.getcwd()
    root = os.path.expanduser(root)
    default_map = os.path.join(root, "docs", "architecture", "map.json")
    project_config = os.path.join(root, ".archlens.json")
    return not (os.path.isfile(default_map) or os.path.isfile(project_config) or user_config_exists())


def main() -> int:
    try:
        event = sys.argv[1] if len(sys.argv) > 1 else ""
        if event not in {"session-start", "stop", "file-pointer", "commit-gate"}:
            return 0
        # Hook input is UTF-8 JSON. Read bytes: the default text encoding differs on Windows.
        raw = "" if sys.stdin.isatty() else sys.stdin.buffer.read().decode("utf-8", "replace")
        if nothing_to_do(event, raw):
            return 0
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import archlens
        return archlens.run_hook(event, raw)
    except Exception:  # noqa: BLE001 - a documentation hook must never break the agent session
        return 0


if __name__ == "__main__":
    sys.exit(main())
