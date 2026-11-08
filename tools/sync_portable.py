"""Generate the portable Agent Skill from the canonical Claude plugin."""

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "archlens"
PORTABLE = ROOT / "skills" / "archlens"
OPERATIONS = ("setup", "update", "check", "explain", "decide", "learn")


def workflow(name):
    source = (PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    parts = source.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError(f"{name}: invalid native skill frontmatter")
    body = parts[2].lstrip("\n")
    body = body.replace("${CLAUDE_PLUGIN_ROOT}", "<skill-dir>")
    body = body.replace("$ARGUMENTS", "the relevant part of the user's request")
    body = body.replace("`/archlens:setup`", "the Archlens setup operation")
    body = body.replace(
        "Claude Code loads a short handbook map at session start. For other agents,\n   offer",
        "This host may not load a handbook map at session start.\n   Offer",
    )
    body = body.replace("Use the Archlens block already in context", "Use an Archlens context block already loaded")
    if "${CLAUDE_PLUGIN_ROOT}" in body or "$ARGUMENTS" in body:
        raise ValueError(f"{name}: a Claude-specific placeholder remains")
    return body.encode("utf-8")


def expected_files():
    files = {
        Path("LICENSE"): (PLUGIN / "LICENSE").read_bytes(),
        Path("defaults.json"): (PLUGIN / "defaults.json").read_bytes(),
        Path("scripts/archlens.py"): (PLUGIN / "scripts" / "archlens.py").read_bytes(),
    }
    for path in sorted((PLUGIN / "references").glob("*.md")):
        files[Path("references") / path.name] = path.read_bytes()
    for name in OPERATIONS:
        files[Path("workflows") / f"{name}.md"] = workflow(name)
    return files


def linked(path):
    current = PORTABLE
    if current.is_symlink():
        return True
    for part in path.relative_to(PORTABLE).parts:
        current = current / part
        if current.is_symlink():
            return True
    return not path.resolve().is_relative_to(PORTABLE.resolve())


def audit():
    expected = expected_files()
    errors = []
    router = PORTABLE / "SKILL.md"
    if linked(router):
        errors.append("Refusing a linked portable resource: SKILL.md")
    elif not router.is_file():
        errors.append("Missing portable router: SKILL.md")
    for relative, content in expected.items():
        path = PORTABLE / relative
        if linked(path):
            errors.append(f"Refusing a linked portable resource: {relative}")
        elif not path.is_file():
            errors.append(f"Missing generated resource: {relative}")
        elif path.read_bytes() != content:
            errors.append(f"Stale generated resource: {relative}")
    if PORTABLE.exists() and not PORTABLE.is_symlink():
        for path in PORTABLE.rglob("*"):
            if "__pycache__" in path.parts:
                continue
            relative = path.relative_to(PORTABLE)
            if path.is_symlink() and relative not in expected and relative != Path("SKILL.md"):
                errors.append(f"Refusing a linked portable resource: {relative}")
            elif path.is_file() and relative not in expected and relative != Path("SKILL.md"):
                errors.append(f"Unexpected generated resource: {relative}")
    return errors


def generate():
    expected = expected_files()
    for relative, content in expected.items():
        path = PORTABLE / relative
        if linked(path):
            raise ValueError(f"Refusing a linked portable resource: {relative}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return audit()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check for missing or stale generated resources")
    args = parser.parse_args(argv)
    errors = audit() if args.check else generate()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Portable resources match the canonical plugin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
