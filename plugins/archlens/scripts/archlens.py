#!/usr/bin/env python3
"""Read-only, standard-library checks for Archlens. Requires Python 3.10+."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
KINDS = {
    "index", "context", "containers", "component", "runtime", "data",
    "deployment", "quality", "glossary", "decision",
}
REVIEW_STATES = {"draft", "reviewed", "needs-review"}
DECISION_STATES = {"proposed", "accepted", "rejected", "deprecated", "superseded"}
PAGE_KEYS = {
    "path", "id", "kind", "owner", "reviewState", "verifiedCommit", "covers",
    "decisionStatus",
}


class ArchlensError(Exception):
    """An actionable input, filesystem, or command error."""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ArchlensError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path):
    try:
        return json.loads(
            path.read_text(encoding="utf-8-sig"),
            object_pairs_hook=unique_object,
            parse_constant=lambda value: invalid_constant(value),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArchlensError(f"Cannot read JSON {path}: {exc}") from exc
    except ArchlensError as exc:
        raise ArchlensError(f"{path}: {exc}") from exc


def invalid_constant(value):
    raise ArchlensError(f"Non-finite JSON number: {value}")


def relative_path(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        raise ArchlensError(f"{label} must be a non-empty relative path")
    normalized = value.replace("\\", "/")
    if PureWindowsPath(value).drive or normalized.startswith("/"):
        raise ArchlensError(f"{label} must not be an absolute path")
    if any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ArchlensError(f"{label} must not contain empty, '.' or '..' segments")
    return normalized


def contained(base: Path, relative: str, label: str) -> Path:
    candidate = (base / relative).resolve()
    if not candidate.is_relative_to(base.resolve()):
        raise ArchlensError(f"{label} escapes {base}: {relative}")
    return candidate


def validate_config(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise ArchlensError(f"{label} must be a JSON object")
    allowed = {"docsRoot", "styleTarget", "maxDiagramNodes", "maxSequenceParticipants"}
    unknown = value.keys() - allowed
    if unknown:
        raise ArchlensError(f"{label}: unknown settings: {', '.join(sorted(unknown))}")
    result = dict(value)
    if "docsRoot" in result:
        result["docsRoot"] = relative_path(result["docsRoot"], f"{label}.docsRoot")
    if "styleTarget" in result:
        score = result["styleTarget"]
        if type(score) not in (int, float) or not 0 <= score <= 1:
            raise ArchlensError(f"{label}.styleTarget must be a number from 0 to 1")
    for key, maximum in (("maxDiagramNodes", 30), ("maxSequenceParticipants", 15)):
        if key in result and (type(result[key]) is not int or not 2 <= result[key] <= maximum):
            raise ArchlensError(f"{label}.{key} must be an integer from 2 to {maximum}")
    return result


def load_config(root: Path, environ=None) -> tuple[dict, list[str]]:
    env = os.environ if environ is None else environ
    config = validate_config(read_json(PLUGIN_ROOT / "defaults.json"), "defaults")
    sources = [str(PLUGIN_ROOT / "defaults.json")]
    explicit = env.get("ARCHLENS_CONFIG")
    home = Path(env.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()
    user_path = Path(explicit).expanduser() if explicit else home / "archlens.json"
    if explicit and not user_path.is_file():
        raise ArchlensError(f"ARCHLENS_CONFIG does not name a readable file: {user_path}")
    project_path = contained(root, ".archlens.json", "project config")
    for path in (user_path, project_path):
        if path.exists() or path.is_symlink():
            config.update(validate_config(read_json(path), str(path)))
            sources.append(str(path))
    contained(root, config["docsRoot"], "docsRoot")
    return config, sources


def glob_regex(pattern: str) -> re.Pattern:
    pattern = relative_path(pattern, "covers pattern")
    if any(char in pattern for char in "[]{}!"):
        raise ArchlensError(f"Unsupported glob syntax: {pattern}")
    parts = pattern.split("/")
    if any("**" in part and part != "**" for part in parts):
        raise ArchlensError(f"'**' must be a complete path segment: {pattern}")
    result = ""
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        if part == "**":
            result += ".*" if last else "(?:[^/]+/)*"
        else:
            result += "".join("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c) for c in part)
            if not last:
                result += "/"
    return re.compile("^" + result + "$")


def load_map(root: Path, config: dict) -> tuple[Path, list[dict]]:
    docs = contained(root, config["docsRoot"], "docsRoot")
    map_path = contained(docs, "map.json", "document map")
    if not map_path.is_file():
        raise ArchlensError(f"No document map at {map_path}. Run /archlens:setup first.")
    data = read_json(map_path)
    if not isinstance(data, dict) or set(data) != {"version", "pages"}:
        raise ArchlensError("map.json requires exactly 'version' and 'pages'")
    if type(data["version"]) is not int or data["version"] != 1:
        raise ArchlensError("Unsupported document map version; expected 1")
    if not isinstance(data["pages"], list) or not data["pages"]:
        raise ArchlensError("map.json pages must be a non-empty list")
    paths, ids, resolved_paths = set(), set(), set()
    for index, page in enumerate(data["pages"]):
        label = f"map.json pages[{index}]"
        if not isinstance(page, dict):
            raise ArchlensError(f"{label} must be an object")
        missing = (PAGE_KEYS - {"decisionStatus"}) - page.keys()
        unknown = page.keys() - PAGE_KEYS
        if missing or unknown:
            raise ArchlensError(f"{label}: missing keys {sorted(missing)}; unknown keys {sorted(unknown)}")
        path = relative_path(page["path"], f"{label}.path")
        if not path.endswith(".md"):
            raise ArchlensError(f"{label}.path must end in .md")
        resolved = contained(docs, path, f"{label}.path")
        if path.casefold() in paths or resolved in resolved_paths:
            raise ArchlensError(f"Duplicate page path: {path}")
        paths.add(path.casefold())
        resolved_paths.add(resolved)
        page["path"] = path
        if not isinstance(page["id"], str) or not re.fullmatch(r"[A-Z][A-Z0-9-]*", page["id"]):
            raise ArchlensError(f"{label}.id must be an uppercase identifier")
        if page["id"] in ids:
            raise ArchlensError(f"Duplicate page ID: {page['id']}")
        ids.add(page["id"])
        if not isinstance(page["owner"], str) or not page["owner"].strip():
            raise ArchlensError(f"{label}.owner must be a non-empty string; use 'unknown' if needed")
        for key, choices in (("kind", KINDS), ("reviewState", REVIEW_STATES)):
            if not isinstance(page[key], str) or page[key] not in choices:
                raise ArchlensError(f"{label}.{key} must be one of {sorted(choices)}")
        commit = page["verifiedCommit"]
        if commit is not None and (not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit)):
            raise ArchlensError(f"{label}.verifiedCommit must be null or a full lowercase commit ID")
        covers = page["covers"]
        if not isinstance(covers, list):
            raise ArchlensError(f"{label}.covers must be a list")
        for pattern in covers:
            glob_regex(pattern)
        if page["kind"] == "decision":
            if not isinstance(page.get("decisionStatus"), str) or page["decisionStatus"] not in DECISION_STATES:
                raise ArchlensError(f"{label}.decisionStatus must be one of {sorted(DECISION_STATES)}")
        elif "decisionStatus" in page:
            raise ArchlensError(f"{label}: decisionStatus is only valid for decision pages")
    return docs, data["pages"]


def markdown_sections(text: str):
    """Return outside-fence lines, fenced blocks, and an unclosed fence line."""
    prose, blocks, body = [], [], []
    fence_char, fence_size, language, start = "", 0, "", 0
    in_metadata = text.startswith("---\n") or text.startswith("---\r\n")
    for number, line in enumerate(text.splitlines(), 1):
        if in_metadata:
            if number > 1 and line.strip() in {"---", "..."}:
                in_metadata = False
            continue
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if not fence_char:
            if match:
                fence_char, fence_size = match[1][0], len(match[1])
                language, start, body = match[2].strip().lower(), number, []
            else:
                prose.append((number, line))
        elif match and match[1][0] == fence_char and len(match[1]) >= fence_size and not match[2].strip():
            blocks.append((start, language, "\n".join(body)))
            fence_char = ""
        else:
            body.append(line)
    return prose, blocks, start if fence_char else (1 if in_metadata else None)


def local_targets(line: str):
    inline = re.finditer(r"!?\[[^\]]*\]\(\s*(<[^>]*>|[^()\s]*(?:\([^()]*\)[^()\s]*)*)"
                         r'(?:\s+"[^"]*")?\s*\)', line)
    for match in inline:
        yield match[1].strip("<>")
    definition = re.match(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]+>|\S+)", line)
    if definition:
        yield definition[1].strip("<>")


def check_link(root: Path, page: Path, target: str) -> str | None:
    target = unquote(target)
    if not target or target.startswith("#"):
        return None
    parts = urlsplit(target)
    if parts.scheme in {"http", "https", "mailto", "tel"}:
        return None
    if parts.scheme or parts.netloc:
        return f"Unsupported or unsafe link scheme: {target}"
    if not parts.path:
        return None
    if PureWindowsPath(parts.path).drive:
        return f"Absolute local link is not portable: {target}"
    location = (root / parts.path.lstrip("/")) if parts.path.startswith("/") else (page.parent / parts.path.replace("\\", "/"))
    location = location.resolve()
    if not location.is_relative_to(root):
        return f"Local link escapes the project: {target}"
    if not location.exists():
        return f"Missing local link target: {target}"
    return None


def check_documents(root: Path, config: dict) -> dict:
    docs, pages = load_map(root, config)
    findings = []
    diagram_count = 0

    def add(severity, path, line, code, message):
        findings.append({"severity": severity, "path": path, "line": line, "code": code, "message": message})

    mapped = {page["path"] for page in pages}
    for path in sorted(docs.rglob("*.md")):
        contained(docs, path.relative_to(docs).as_posix(), "documentation page")
        relative = path.relative_to(docs).as_posix()
        if relative not in mapped:
            add("error", path.relative_to(root).as_posix(), 1, "unmapped-page", "Add this page to map.json.")
    for page in pages:
        path = contained(docs, page["path"], "page")
        relative = path.relative_to(root).as_posix()
        if not path.is_file():
            add("error", relative, 1, "missing-page", "Mapped page does not exist.")
            continue
        text = path.read_text(encoding="utf-8-sig")
        prose, blocks, unclosed = markdown_sections(text)
        if unclosed:
            add("error", relative, unclosed, "unclosed-block", "Close the code fence or metadata block.")
        if not re.search(r"(?m)^#\s+\S", "\n".join(line for _, line in prose)):
            add("warning", relative, 1, "missing-title", "Add a level-one page title.")
        for number, line in prose:
            for target in local_targets(line):
                problem = check_link(root, path, target)
                if problem:
                    add("error", relative, number, "local-link", problem)
            if line.strip() and not line.lstrip().startswith(("#", "|", "<!--", "[")):
                plain = re.sub(r"`[^`]*`", "", line)
                if ";" in plain:
                    add("warning", relative, number, "semicolon", "Consider separate, direct sentences.")
                if len(re.findall(r"\b[\w'-]+\b", plain)) > 60:
                    add("warning", relative, number, "long-line", "Review this long prose line; split complex sentences.")
        for number, language, body in blocks:
            if language != "mermaid":
                continue
            diagram_count += 1
            if not body.strip():
                add("error", relative, number, "empty-diagram", "Add diagram source or remove the empty block.")
            if re.search(r"(?m)^\s*sequenceDiagram\s*$", body):
                if not re.search(r"(?m)^\s*autonumber(?:\s.*)?$", body):
                    add("warning", relative, number, "sequence-numbers", "Use autonumber to connect messages to steps.")
                participants = len(re.findall(r"(?m)^\s*(?:participant|actor)\s+", body))
                if participants > config["maxSequenceParticipants"]:
                    add("warning", relative, number, "sequence-density", "Consider splitting this sequence.")
    return {
        "command": "check", "root": str(root), "pages": len(pages),
        "mermaidBlocks": diagram_count, "findings": findings,
        "stylePassRate": None,
        "limits": [
            "Mermaid rendering and semantic accuracy are not checked.",
            "Only inline Markdown links and reference definitions are checked; anchors and remote URLs are not.",
            "Writing warnings are heuristics, not an STE score.",
        ],
    }


def git(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "--no-pager", "-C", str(root), *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ArchlensError(f"Cannot run Git: {exc}") from exc
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ArchlensError(f"Git {' '.join(args)} failed: {detail}")
    return result.stdout


def changed_files(root: Path, base: str | None) -> tuple[list[str], str | None]:
    git_root = Path(os.fsdecode(git(root, "rev-parse", "--show-toplevel")).strip()).resolve()
    if git_root != root:
        raise ArchlensError(f"--root must be the Git root for impact: {git_root}")
    changes = set()
    merge_base = None

    def collect(*args):
        for name in git(root, *args).split(b"\0"):
            if name:
                changes.add(name.decode("utf-8", errors="surrogateescape"))

    if base is not None:
        if not base.strip() or base.startswith("-"):
            raise ArchlensError("--base must be a non-empty local revision, not an option")
        revision = git(root, "rev-parse", "--verify", "--end-of-options", base + "^{commit}").decode().strip()
        merge_base = git(root, "merge-base", "HEAD", revision).decode().strip()
        collect("diff", "--no-ext-diff", "--no-renames", "--name-only", "-z", merge_base, "HEAD", "--")
    collect("diff", "--no-ext-diff", "--no-renames", "--name-only", "-z", "--")
    collect("diff", "--cached", "--no-ext-diff", "--no-renames", "--name-only", "-z", "--")
    collect("ls-files", "--others", "--exclude-standard", "-z")
    return sorted(changes), merge_base


def impact_report(root: Path, config: dict, base: str | None) -> dict:
    docs, pages = load_map(root, config)
    changed, merge_base = changed_files(root, base)
    doc_prefix = docs.relative_to(root).as_posix() + "/"
    source_changes = [path for path in changed if not path.startswith(doc_prefix) and path != ".archlens.json"]
    covered = set()
    candidates = []
    for page in pages:
        patterns = [glob_regex(pattern) for pattern in page["covers"]]
        matches = [path for path in source_changes if any(pattern.fullmatch(path) for pattern in patterns)]
        if matches:
            covered.update(matches)
            candidates.append({
                "page": doc_prefix + page["path"], "id": page["id"], "changedSources": matches,
                "pageAlsoChanged": doc_prefix + page["path"] in changed,
            })
    return {
        "command": "impact", "root": str(root),
        "scope": "branch-and-working-tree" if base is not None else "working-tree",
        "base": base, "mergeBase": merge_base, "changedFiles": changed,
        "candidates": candidates, "uncoveredFiles": sorted(set(source_changes) - covered),
        "limits": [
            "Path matches identify review candidates, not proven drift.",
            "Uncovered files need triage; they are not necessarily architecture changes.",
            "Indirect dependencies require semantic review.",
        ],
    }


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("config", "check", "impact"):
        command = commands.add_parser(name)
        command.add_argument("--root", type=Path, default=Path.cwd(), help="Project root (default: current folder)")
        output = command.add_mutually_exclusive_group()
        output.add_argument("--json", action="store_true", help="Emit the complete machine-readable report")
        output.add_argument("--summary", action="store_true", help="Emit bounded JSON (at most 6000 UTF-8 bytes)")
        if name == "check":
            command.add_argument("--strict", action="store_true", help="Also fail on warnings")
        if name == "impact":
            command.add_argument("--base", help="Local Git revision; compare merge base plus working tree")
            command.add_argument("--fail-on-impact", action="store_true", help="Exit 1 for candidates or uncovered source files")
    return parser


def bounded_report(report: dict, budget: int = 6000) -> dict:
    """Keep whole records and explicit omission counts, never silently truncate JSON."""
    collection_keys = ("findings", "candidates", "uncoveredFiles", "changedFiles")
    result = {key: value for key, value in report.items() if key not in collection_keys}
    result["totals"] = {key: len(report[key]) for key in collection_keys if key in report}
    result["omitted"] = dict(result["totals"])
    result["detailHint"] = "Use --json redirected to a local file; query omitted records in bounded batches."
    for key in result["totals"]:
        result[key] = []
    for key in result["totals"]:
        for item in report[key][:8]:
            result[key].append(item)
            result["omitted"][key] -= 1
            if len(json.dumps(result, ensure_ascii=True).encode("utf-8")) > budget:
                result[key].pop()
                result["omitted"][key] += 1
                break
    if len(json.dumps(result, ensure_ascii=True).encode("utf-8")) > budget:
        return {
            "command": report["command"], "ok": report["ok"], "totals": result["totals"],
            "omitted": result["totals"], "detailHint": result["detailHint"],
            "note": "Metadata exceeds summary budget. Inspect the complete report locally.",
        }
    return result


def print_report(report: dict, as_json: bool):
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return
    print(f"Archlens {report['command']}: {'PASS' if report['ok'] else 'REVIEW REQUIRED'}")
    if report["command"] == "config":
        print(json.dumps(report["config"], indent=2))
        print("Sources:\n  " + "\n  ".join(report["sources"]))
    elif report["command"] == "check":
        print(f"{report['pages']} pages; {report['mermaidBlocks']} Mermaid blocks (not rendered).")
        for finding in report["findings"]:
            print(f"{finding['severity'].upper()} {finding['path']}:{finding['line']} [{finding['code']}] {finding['message']}")
    else:
        print(f"Scope: {report['scope']}; {len(report['changedFiles'])} changed files.")
        for candidate in report["candidates"]:
            print(f"REVIEW {candidate['page']}: {', '.join(candidate['changedSources'])}")
        for path in report["uncoveredFiles"]:
            print(f"UNMAPPED {path}")
    for limit in report.get("limits", []):
        print(f"Note: {limit}")


def main(argv=None) -> int:
    args = make_parser().parse_args(argv)
    try:
        root = args.root.expanduser().resolve()
        if not root.is_dir():
            raise ArchlensError(f"Project root is not a directory: {root}")
        config, sources = load_config(root)
        if args.command == "config":
            report = {"command": "config", "root": str(root), "config": config, "sources": sources}
            failed = False
        elif args.command == "check":
            report = check_documents(root, config)
            failed = any(f["severity"] == "error" or args.strict for f in report["findings"])
        else:
            report = impact_report(root, config, args.base)
            failed = args.fail_on_impact and bool(report["candidates"] or report["uncoveredFiles"])
        report["ok"] = not failed
        if args.summary:
            print(json.dumps(bounded_report(report), ensure_ascii=True))
        else:
            print_report(report, args.json)
        return 1 if failed else 0
    except (ArchlensError, OSError, UnicodeError, ValueError) as exc:
        message = str(exc)
        if args.json or args.summary:
            error = {"command": args.command, "ok": False, "error": message}
            if args.summary and len(message) > 600:
                error["error"] = message[:600]
                error["errorTruncated"] = True
                error["detailHint"] = "Run with --json to inspect the complete error locally."
            print(json.dumps(error))
        else:
            print(f"Archlens error: {message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
