#!/usr/bin/env python3
"""Standard-library helper for Archlens: checks, freshness, sync, and agent context. Python 3.9+."""

from __future__ import annotations

import argparse
import ast
import bisect
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
KINDS = {
    "index", "context", "containers", "component", "runtime", "data",
    "deployment", "quality", "glossary", "decision",
}
KIND_ORDER = [
    "index", "context", "containers", "runtime", "data", "component",
    "deployment", "quality", "glossary", "decision",
]
REVIEW_STATES = {"draft", "reviewed", "needs-review"}
DECISION_STATES = {"proposed", "accepted", "rejected", "deprecated", "superseded"}
PAGE_KEYS = {
    "path", "id", "kind", "owner", "reviewState", "verifiedCommit", "covers",
    "decisionStatus",
}
AUTO_UPDATE = {"off", "remind", "auto"}
STATE_FILE = ".archlens-state.json"
BLOCK_START = "<!-- archlens:context:start - generated from the handbook; edit pages, not this block -->"
BLOCK_END = "<!-- archlens:context:end -->"
MERMAID_TYPES = (
    "flowchart", "graph", "sequenceDiagram", "stateDiagram", "stateDiagram-v2", "erDiagram",
    "classDiagram", "C4Context", "C4Container", "C4Component", "C4Dynamic", "C4Deployment",
    "gantt", "pie", "journey", "mindmap", "timeline", "gitGraph", "quadrantChart",
    "requirementDiagram", "sankey-beta", "xychart-beta", "block-beta", "architecture-beta",
    "packet-beta", "kanban", "radar-beta", "treemap-beta",
)
WALK_EXCLUDES = {".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", ".mypy_cache", ".pytest_cache"}


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
    allowed = {
        "docsRoot", "styleTarget", "maxDiagramNodes", "maxSequenceParticipants",
        "contextBudget", "contextFile", "sessionContext", "autoUpdate", "filePointers", "fixAnchors",
    }
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
    for key, minimum, maximum in (
        ("maxDiagramNodes", 2, 30), ("maxSequenceParticipants", 2, 15), ("contextBudget", 600, 20000),
    ):
        if key in result and (type(result[key]) is not int or not minimum <= result[key] <= maximum):
            raise ArchlensError(f"{label}.{key} must be an integer from {minimum} to {maximum}")
    if "contextFile" in result and result["contextFile"] is not None:
        result["contextFile"] = relative_path(result["contextFile"], f"{label}.contextFile")
        if not result["contextFile"].lower().endswith(".md"):
            raise ArchlensError(f"{label}.contextFile must be null or a Markdown file such as AGENTS.md")
    for key in ("sessionContext", "filePointers", "fixAnchors"):
        if key in result and type(result[key]) is not bool:
            raise ArchlensError(f"{label}.{key} must be true or false")
    if "autoUpdate" in result and result["autoUpdate"] not in AUTO_UPDATE:
        raise ArchlensError(f"{label}.autoUpdate must be one of {sorted(AUTO_UPDATE)}")
    return result


def load_config(root: Path, environ=None) -> tuple[dict, list[str]]:
    env = os.environ if environ is None else environ
    config = validate_config(read_json(PLUGIN_ROOT / "defaults.json"), "defaults")
    sources = [str(PLUGIN_ROOT / "defaults.json")]
    explicit = env.get("ARCHLENS_CONFIG")
    if explicit:
        user_path = Path(explicit).expanduser()
    elif env.get("CLAUDE_CONFIG_DIR"):
        user_path = Path(env["CLAUDE_CONFIG_DIR"]).expanduser() / "archlens.json"
    else:
        config_home = Path(env.get("XDG_CONFIG_HOME") or Path.home() / ".config").expanduser()
        shared_path = config_home / "archlens" / "config.json"
        legacy_path = Path.home() / ".claude" / "archlens.json"
        user_path = shared_path if shared_path.exists() or shared_path.is_symlink() else legacy_path
    if explicit and not user_path.is_file():
        raise ArchlensError(f"ARCHLENS_CONFIG does not name a readable file: {user_path}")
    project_path = contained(root, ".archlens.json", "project config")
    for path in (user_path, project_path):
        if path.exists() or path.is_symlink():
            config.update(validate_config(read_json(path), str(path)))
            sources.append(str(path))
    contained(root, config["docsRoot"], "docsRoot")
    if config.get("contextFile"):
        contained(root, config["contextFile"], "contextFile")
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


def glob_prefix(pattern: str) -> str:
    """Literal leading directories of a pattern, used to skip regex work."""
    parts = pattern.replace("\\", "/").split("/")
    literal = []
    for part in parts[:-1]:
        if "*" in part or "?" in part:
            break
        literal.append(part)
    return "/".join(literal) + "/" if literal else ""


def load_map(root: Path, config: dict) -> tuple[Path, list[dict]]:
    docs = contained(root, config["docsRoot"], "docsRoot")
    map_path = contained(docs, "map.json", "document map")
    if not map_path.is_file():
        raise ArchlensError(f"No document map at {map_path}. Run Archlens setup (Claude: /archlens:setup) first.")
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


def heading_slugs(text: str) -> set[str]:
    """GitHub-style heading anchors for prose headings."""
    prose, _, _ = markdown_sections(text)
    slugs, seen = set(), {}
    for _, line in prose:
        match = re.match(r"^ {0,3}#{1,6}\s+(.*?)\s*#*\s*$", line)
        if not match:
            continue
        title = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", match[1])
        slug = re.sub(r"[^\w\- ]", "", title.lower().replace("`", "")).replace(" ", "-")
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        slugs.add(slug if count == 0 else f"{slug}-{count}")
    for anchor in re.findall(r"<a\s+(?:name|id)=\"([^\"]+)\"", text):
        slugs.add(anchor)
    return slugs


def resolve_link(root: Path, page: Path, target: str) -> tuple[Path | None, str, str | None]:
    """Return a resolved local path, its fragment, and an error message."""
    target = unquote(target)
    if not target or target.startswith("#"):
        return None, target[1:], None
    parts = urlsplit(target)
    if parts.scheme in {"http", "https", "mailto", "tel"}:
        return None, "", None
    if parts.scheme or parts.netloc:
        return None, "", f"Unsupported or unsafe link scheme: {target}"
    if not parts.path:
        return None, parts.fragment, None
    if PureWindowsPath(parts.path).drive:
        return None, "", f"Absolute local link is not portable: {target}"
    location = (root / parts.path.lstrip("/")) if parts.path.startswith("/") else (page.parent / parts.path.replace("\\", "/"))
    location = location.resolve()
    if not location.is_relative_to(root):
        return None, "", f"Local link escapes the project: {target}"
    if not location.exists():
        return None, "", f"Missing local link target: {target}"
    return location, parts.fragment, None


def check_link(root: Path, page: Path, target: str) -> str | None:
    return resolve_link(root, page, target)[2]


def check_fragment(page: Path, location: Path | None, fragment: str, page_text: str) -> tuple[str, str] | None:
    """Check a heading anchor or a GitHub line anchor such as #L10-L20."""
    if not fragment:
        return None
    lines = re.fullmatch(r"L(\d+)(?:C\d+)?(?:-L(\d+)(?:C\d+)?)?", fragment)
    target = location or page
    if lines:
        if target.suffix.lower() == ".md" and location is None:
            return None
        try:
            count = len(target.read_bytes().splitlines())
        except OSError:
            return None
        last = int(lines[2] or lines[1])
        if last > count:
            return ("error", f"Line anchor #{fragment} is past the end of {target.name} ({count} lines); evidence moved.")
        return None
    if target.suffix.lower() != ".md" or target.is_dir():
        return None
    text = page_text if location is None else target.read_text(encoding="utf-8-sig", errors="replace")
    if fragment.lower() not in heading_slugs(text):
        return ("warning", f"Heading anchor #{fragment} not found in {target.name}.")
    return None


def mermaid_type(body: str) -> str | None:
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        if stripped == "---":
            return "frontmatter"
        return stripped.split()[0].rstrip(";")
    return None


class References:
    """Checks that backticked paths, function names, and npm scripts in prose still exist."""

    SKIP = re.compile(r"[*<>{}$~\s|]|://|^[-/.]|^[A-Z]:")

    def __init__(self, root: Path, docs: Path):
        self.root = root
        self.exclude = f":(exclude){docs.relative_to(root).as_posix()}"
        self.git = in_git(root)
        self.symbols: dict[str, bool] = {}
        try:
            self.scripts = set(read_json(root / "package.json").get("scripts", {}))
        except (ArchlensError, AttributeError):
            self.scripts = None

    def problems(self, page: Path, line: str):
        for token in re.findall(r"`([^`\n]+)`", line):
            token = token.strip()
            npm = re.fullmatch(r"npm run ([\w:.-]+)", token)
            if npm and self.scripts is not None and npm[1] not in self.scripts:
                yield f"npm script not found in package.json: {npm[1]}"
            elif re.fullmatch(r"[A-Za-z_][\w.]*\(\)", token):
                name = token[:-2].rsplit(".", 1)[-1]
                if self.git and not self.symbol_exists(name):
                    yield f"Symbol not found in the repository: {token}"
            elif "/" in token and not self.SKIP.search(token):
                path = token.rstrip("/").split("#", 1)[0]
                first = path.split("/", 1)[0]
                if not (self.root / first).exists() and not (page.parent / first).exists():
                    continue
                if not (self.root / path).exists() and not (page.parent / path).exists():
                    yield f"Path not found: {token}"

    def symbol_exists(self, name: str) -> bool:
        if name not in self.symbols:
            try:
                found = git(self.root, "grep", "--untracked", "-l", "-w", "-F", "-e", name, "--", ".", self.exclude)
                self.symbols[name] = bool(found.strip())
            except ArchlensError:
                self.symbols[name] = False
        return self.symbols[name]


def check_documents(root: Path, config: dict) -> dict:
    docs, pages = load_map(root, config)
    findings = []
    diagram_count = 0

    def add(severity, path, line, code, message):
        findings.append({"severity": severity, "path": path, "line": line, "code": code, "message": message})

    references = References(root, docs)
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
                location, fragment, problem = resolve_link(root, path, target)
                if problem:
                    add("error", relative, number, "local-link", problem)
                    continue
                anchor = check_fragment(path, location, fragment, text)
                if anchor:
                    code = "line-anchor" if anchor[1].startswith("Line") else "heading-anchor"
                    add(anchor[0], relative, number, code, anchor[1])
            for problem in references.problems(path, line):
                add("warning", relative, number, "stale-reference", problem)
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
                continue
            kind = mermaid_type(body)
            if kind not in MERMAID_TYPES and kind != "frontmatter":
                add("error", relative, number, "mermaid-type", f"Unknown Mermaid diagram type: {kind}")
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
            "Mermaid rendering and semantic accuracy are not checked; only the diagram type is.",
            "Inline Markdown links, reference definitions, heading anchors, and line anchors are checked; remote URLs are not.",
            "Backticked paths, function() names, and npm scripts are checked for existence, not meaning.",
            "Writing warnings are heuristics, not an STE score.",
        ],
    }


def git(root: Path, *args: str, stdin: bytes | None = None) -> bytes:
    try:
        result = subprocess.run(
            ["git", "--no-pager", "-C", str(root), *args], input=stdin,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ArchlensError(f"Cannot run Git: {exc}") from exc
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ArchlensError(f"Git {' '.join(args)} failed: {detail}")
    return result.stdout


def names(output: bytes) -> list[str]:
    return [name.decode("utf-8", errors="surrogateescape") for name in output.split(b"\0") if name]


def in_git(root: Path) -> bool:
    try:
        return git(root, "rev-parse", "--is-inside-work-tree").strip() == b"true"
    except ArchlensError:
        return False


def head_commit(root: Path) -> str | None:
    try:
        return git(root, "rev-parse", "--verify", "-q", "HEAD").decode().strip() or None
    except ArchlensError:
        return None


def changed_files(root: Path, base: str | None) -> tuple[list[str], str | None]:
    git_root = Path(os.fsdecode(git(root, "rev-parse", "--show-toplevel")).strip()).resolve()
    if git_root != root:
        raise ArchlensError(f"--root must be the Git root for impact: {git_root}")
    changes = set()
    merge_base = None

    def collect(*args):
        changes.update(names(git(root, *args)))

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


def page_evidence(root: Path, docs: Path, page_path: Path) -> tuple[list[str], list[tuple[str, int, int]]]:
    """Linked project files or folders outside the handbook, plus line-range anchors."""
    try:
        text = page_path.read_text(encoding="utf-8-sig")
    except OSError:
        return [], []
    prose, _, _ = markdown_sections(text)
    links, anchors = set(), set()
    for _, line in prose:
        for target in local_targets(line):
            location, fragment, problem = resolve_link(root, page_path, target)
            if problem or location is None or location.is_relative_to(docs):
                continue
            relative = location.relative_to(root).as_posix()
            span = re.fullmatch(r"L(\d+)(?:C\d+)?(?:-L(\d+)(?:C\d+)?)?", fragment or "")
            if span and location.is_file():
                first = int(span[1])
                anchors.add((relative, first, max(first, int(span[2] or first))))
            else:
                links.add(relative + "/" if location.is_dir() else relative)
    return sorted(links), sorted(anchors)


def page_links(root: Path, docs: Path, page_path: Path) -> list[str]:
    links, anchors = page_evidence(root, docs, page_path)
    return sorted(set(links) | {path for path, _, _ in anchors})


class Coverage:
    """Which project files each page covers, through patterns and evidence links."""

    def __init__(self, root: Path, docs: Path, pages: list[dict]):
        self.rules, self.evidence = {}, {}
        for page in pages:
            patterns = [(glob_prefix(p), glob_regex(p)) for p in page["covers"]]
            links, anchors = page_evidence(root, docs, contained(docs, page["path"], "page"))
            self.rules[page["id"]] = (patterns, sorted(set(links) | {a[0] for a in anchors}))
            self.evidence[page["id"]] = (links, anchors)

    def matches(self, page_id: str, path: str) -> bool:
        patterns, links = self.rules[page_id]
        for prefix, regex in patterns:
            if path.startswith(prefix) and regex.fullmatch(path):
                return True
        return any(path == link or (link.endswith("/") and path.startswith(link)) for link in links)

    def files(self, page_id: str, paths) -> list[str]:
        """Covered paths, using sorted ranges so large repositories avoid full scans."""
        ordered = paths if isinstance(paths, SortedPaths) else SortedPaths(paths)
        patterns, links = self.rules[page_id]
        found = set()
        for prefix, regex in patterns:
            found.update(path for path in ordered.under(prefix) if regex.fullmatch(path))
        for link in links:
            found.update(ordered.under(link) if link.endswith("/") else ([link] if link in ordered.members else []))
        return sorted(found)

    def whole_file_evidence(self, page_id: str, path: str) -> bool:
        """True when the page cites the whole file or its folder, not just line ranges."""
        links, _ = self.evidence[page_id]
        return any(path == link or (link.endswith("/") and path.startswith(link)) for link in links)

    def has_evidence(self, page_id: str) -> bool:
        links, anchors = self.evidence[page_id]
        return bool(links or anchors)


def python_symbols(text: str) -> list[tuple[str, int, int, ast.AST]]:
    """Functions and classes with qualified names and line spans, including decorators."""
    found = []

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + child.name
                first = min([child.lineno] + [d.lineno for d in child.decorator_list])
                found.append((name, first, child.end_lineno or child.lineno, child))
                visit(child, name + ".")
            else:
                visit(child, prefix)

    visit(ast.parse(text), "")
    return found


def short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", "surrogateescape")).hexdigest()[:10]


def text_digest(lines: list[str]) -> str:
    """Ignore trailing spaces and blank lines so formatting-only edits do not count."""
    return short_hash("\n".join(line.rstrip() for line in lines if line.strip()))


def read_source(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8-sig", errors="surrogateescape")
    except OSError:
        return None


def fingerprint_anchor(root: Path, path: str, first: int, last: int) -> dict:
    """Record what a cited line range means: a Python symbol's AST, or the normalized text."""
    record = {"path": path, "lines": [first, last]}
    text = read_source(root / path)
    if text is None:
        return record
    if path.endswith(".py"):
        try:
            spans = [s for s in python_symbols(text) if s[1] <= first and s[2] >= last]
        except (SyntaxError, ValueError, RecursionError):
            spans = []
        if spans:
            name, start, end, node = min(spans, key=lambda s: s[2] - s[1])
            record.update(symbol=name, symbolLines=[start, end],
                          digest=short_hash(ast.dump(node, include_attributes=False)))
            return record
    lines = text.splitlines()
    if last <= len(lines):
        record["digest"] = text_digest(lines[first - 1:last])
    return record


def check_anchor(root: Path, record: dict) -> dict | None:
    """Compare a recorded anchor with current source. Returns a change, or None if unchanged."""
    path, (first, last) = record["path"], record["lines"]
    base = {"path": path, "lines": [first, last]}
    text = read_source(root / path)
    if text is None:
        return dict(base, change="evidence-removed")
    if record.get("symbol"):
        base["symbol"] = record["symbol"]
        try:
            match = [s for s in python_symbols(text) if s[0] == record["symbol"]]
        except (SyntaxError, ValueError, RecursionError):
            return dict(base, change="evidence-changed")
        if not match:
            return dict(base, change="symbol-removed")
        _, start, end, node = match[0]
        shift = start - record["symbolLines"][0]
        if short_hash(ast.dump(node, include_attributes=False)) != record.get("digest"):
            moved = {"newLines": [first + shift, last + shift]} if shift else {}
            return dict(base, change="evidence-changed", **moved)
        if shift:
            return dict(base, change="evidence-moved", newLines=[first + shift, last + shift])
        return None
    if record.get("digest") is None:
        return None
    lines = text.splitlines()
    size = last - first + 1
    if last <= len(lines) and text_digest(lines[first - 1:last]) == record["digest"]:
        return None
    for start in range(0, max(0, len(lines) - size + 1)):
        if text_digest(lines[start:start + size]) == record["digest"]:
            return dict(base, change="evidence-moved", newLines=[start + 1, start + size])
    return dict(base, change="evidence-changed")


class SortedPaths:
    """Sorted path list with prefix-range lookup."""

    def __init__(self, paths):
        self.items = sorted(paths)
        self.members = set(self.items)

    def under(self, prefix: str) -> list[str]:
        if not prefix:
            return self.items
        start = bisect.bisect_left(self.items, prefix)
        end = bisect.bisect_left(self.items, prefix[:-1] + chr(ord(prefix[-1]) + 1))
        return self.items[start:end]


def blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def project_files(root: Path, docs: Path) -> dict[str, str]:
    """Map project-relative source files to short Git-compatible content IDs."""
    files: dict[str, str] = {}
    if in_git(root):
        for record in git(root, "ls-files", "-s", "-z").split(b"\0"):
            if not record:
                continue
            meta, _, name = record.partition(b"\t")
            mode, sha = meta.split()[:2]
            if mode != b"160000":
                files[name.decode("utf-8", errors="surrogateescape")] = sha.decode()
        dirty = set(names(git(root, "diff", "--relative", "--no-ext-diff", "--no-renames", "--name-only", "-z")))
        dirty |= set(names(git(root, "ls-files", "--others", "--exclude-standard", "-z")))
        present = sorted(name for name in dirty if (root / name).is_file() and not (root / name).is_symlink())
        for name in dirty - set(present):
            files.pop(name, None)
        if present:
            listed = "\n".join(str(root / name) for name in present)
            hashed = git(root, "hash-object", "--stdin-paths", stdin=listed.encode("utf-8", "surrogateescape"))
            for name, sha in zip(present, hashed.decode().split()):
                files[name] = sha
    else:
        for folder, dirs, filenames in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in WALK_EXCLUDES and not os.path.islink(os.path.join(folder, d)))
            for filename in filenames:
                path = Path(folder) / filename
                if path.is_symlink() or not path.is_file():
                    continue
                files[path.relative_to(root).as_posix()] = blob_id(path.read_bytes())
    docs_prefix = docs.relative_to(root).as_posix() + "/"
    return {
        name: sha[:10] for name, sha in files.items()
        if not name.startswith(docs_prefix) and name != ".archlens.json" and "\n" not in name
    }


def load_state(docs: Path) -> dict:
    path = docs / STATE_FILE
    if not path.exists():
        return {"version": 1, "pages": {}}
    state = read_json(path)
    if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("pages"), dict):
        raise ArchlensError(f"{path} is not a valid Archlens state file; re-run sync to rebuild it")
    return state


def save_state(docs: Path, state: dict):
    """One page per line keeps diffs small and merges of different pages clean."""
    path = docs / STATE_FILE
    rows = [
        f"  {json.dumps(key)}: {json.dumps(state['pages'][key], sort_keys=True, ensure_ascii=True, separators=(',', ':'))}"
        for key in sorted(state["pages"])
    ]
    text = '{"version": 1, "pages": {\n' + ",\n".join(rows) + "\n}}\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=docs, delete=False, suffix=".tmp") as handle:
        handle.write(text)
    os.replace(handle.name, path)


def page_changes(root: Path, coverage: Coverage, page_id: str, current: dict, record: dict) -> list[dict]:
    """Classify changes: cited evidence makes a page stale; other covered files need review."""
    old = record["files"]
    has_anchor_state = isinstance(record.get("anchors"), list)
    anchored = {a["path"] for a in record.get("anchors") or []}
    cited = coverage.has_evidence(page_id)

    def severity(path):
        if coverage.whole_file_evidence(page_id, path):
            return "stale"
        if path in anchored and has_anchor_state:
            return "review"
        if path in anchored or not cited:
            return "stale"
        return "review"

    changes = []
    for anchor in record.get("anchors") or []:
        change = check_anchor(root, anchor)
        if change:
            changes.append(dict(change, severity="stale"))
    for path in sorted(current.keys() & old.keys()):
        if current[path] != old[path]:
            changes.append({"path": path, "change": "modified", "severity": severity(path)})
    for path in sorted(current.keys() - old.keys()):
        changes.append({"path": path, "change": "added", "severity": severity(path)})
    for path in sorted(old.keys() - current.keys()):
        changes.append({"path": path, "change": "removed",
                        "severity": "stale" if path in anchored or coverage.whole_file_evidence(page_id, path) else severity(path)})
    return changes


def freshness(root: Path, config: dict) -> dict:
    """Compare each page's covered files and cited evidence with its last sync."""
    docs, pages = load_map(root, config)
    files = project_files(root, docs)
    coverage = Coverage(root, docs, pages)
    state = load_state(docs)
    doc_prefix = docs.relative_to(root).as_posix() + "/"
    ordered = SortedPaths(files)
    results = []
    for page in pages:
        current = {path: files[path] for path in coverage.files(page["id"], ordered)}
        record = state["pages"].get(page["id"])
        entry = {"page": doc_prefix + page["path"], "id": page["id"], "kind": page["kind"]}
        if not isinstance(record, dict) or not isinstance(record.get("files"), dict):
            entry.update(state="unsynced", changed=[], coveredFiles=len(current))
        else:
            changes = page_changes(root, coverage, page["id"], current, record)
            level = "stale" if any(c["severity"] == "stale" for c in changes) else "review" if changes else "fresh"
            entry.update(
                state=level, changed=changes, coveredFiles=len(current),
                syncedAt=record.get("syncedAt"), syncedCommit=record.get("syncedCommit"),
            )
        results.append(entry)
    counts = {name: sum(r["state"] == name for r in results) for name in ("fresh", "stale", "review", "unsynced")}
    return {
        "command": "status", "root": str(root), "counts": counts,
        "needsSync": [r for r in results if r["state"] != "fresh"],
        "fresh": [r["page"] for r in results if r["state"] == "fresh"],
        "limits": [
            "Stale: cited evidence (linked files, Python symbols, or line ranges) changed or moved since the last sync.",
            "Review: other covered files changed; the page may still be accurate.",
            "Neither proves that the prose is wrong. Files outside patterns and links are not tracked.",
        ],
    }


def sync_pages(root: Path, config: dict, ids: list[str], every: bool) -> dict:
    """Record the current content of covered files and cited anchors for reviewed pages."""
    docs, pages = load_map(root, config)
    known = {page["id"] for page in pages}
    unknown = sorted(set(ids) - known)
    if unknown:
        raise ArchlensError(f"Unknown page IDs: {', '.join(unknown)}")
    if not every and not ids:
        raise ArchlensError("Name pages with --page ID (repeatable) or use --all")
    selected = known if every else set(ids)
    files = project_files(root, docs)
    coverage = Coverage(root, docs, pages)
    state = load_state(docs)
    state["pages"] = {key: value for key, value in state["pages"].items() if key in known}
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    commit = head_commit(root) if in_git(root) else None
    ordered = SortedPaths(files)
    for page in pages:
        if page["id"] in selected:
            _, anchors = coverage.evidence[page["id"]]
            state["pages"][page["id"]] = {
                "files": {path: files[path] for path in coverage.files(page["id"], ordered)},
                "anchors": [fingerprint_anchor(root, *anchor) for anchor in anchors],
                "syncedAt": stamp, "syncedCommit": commit,
            }
    save_state(docs, state)
    report = {"command": "sync", "root": str(root), "synced": sorted(selected), "stateFile": (docs / STATE_FILE).relative_to(root).as_posix()}
    if config.get("contextFile"):
        report["contextFile"] = write_context(root, config, contained(root, config["contextFile"], "contextFile"))
    return report


def fix_anchors(root: Path, config: dict, ids: list[str] | None = None) -> dict:
    """Rewrite line links whose cited code moved but did not change. No model needed."""
    docs, pages = load_map(root, config)
    status = freshness(root, config)
    state = load_state(docs)
    by_id = {page["id"]: page for page in pages}
    fixed = []
    for entry in status["needsSync"]:
        moves = [c for c in entry["changed"] if c["change"] == "evidence-moved"]
        record = state["pages"].get(entry["id"])
        if not moves or not isinstance(record, dict) or (ids and entry["id"] not in ids):
            continue
        page_path = docs / by_id[entry["id"]]["path"]
        text = page_path.read_text(encoding="utf-8-sig")
        for move in moves:
            target = Path(os.path.relpath(root / move["path"], page_path.parent)).as_posix()
            (a, b), (c, d) = move["lines"], move["newLines"]
            old = f"#L{a}" if a == b else f"#L{a}-L{b}"
            new = f"#L{c}" if c == d else f"#L{c}-L{d}"
            pattern = re.escape(target + old) + r"(?![\d-])"
            text = re.sub(pattern, lambda _: target + new, text)
            for anchor in record.get("anchors") or []:
                if anchor["path"] == move["path"] and anchor["lines"] == [a, b]:
                    anchor.update(fingerprint_anchor(root, move["path"], c, d))
            fixed.append({"page": entry["page"], "id": entry["id"], "path": move["path"], "from": [a, b], "to": [c, d]})
        page_path.write_text(text, encoding="utf-8")
    if fixed:
        save_state(docs, state)
    return {"command": "fix-anchors", "root": str(root), "fixed": fixed}


def page_brief(path: Path) -> tuple[str, str]:
    """A page's title and first explanatory sentence."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return path.stem, ""
    prose, _, _ = markdown_sections(text)
    title, summary = "", ""
    for _, line in prose:
        stripped = line.strip()
        if not title:
            match = re.match(r"^#\s+(.+)$", stripped)
            if match:
                title = match[1].strip()
            continue
        if not stripped:
            if summary:
                break
            continue
        if stripped.startswith(("#", "|", "<", "**", "![", ">")) or re.match(r"^([-*+]|\d+\.)\s", stripped):
            if summary:
                break
            continue
        summary = (summary + " " + stripped).strip()
    summary = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", summary)
    sentence = re.split(r"(?<=[.!?])\s+", summary)[0] if summary else ""
    if len(sentence) > 150:
        sentence = sentence[:147].rsplit(" ", 1)[0] + "..."
    return title or path.stem, sentence


def build_context(root: Path, config: dict, budget: int | None = None, live: bool = True) -> str:
    """A compact pointer map for an agent's always-loaded context.

    A live map (session hook) carries stale flags. A static map (committed file)
    omits them, because freshness changes between commits."""
    budget = budget or config["contextBudget"]
    docs, pages = load_map(root, config)
    status = freshness(root, config)
    states = {entry["id"]: entry for entry in status["needsSync"]}
    doc_rel = docs.relative_to(root).as_posix()
    ordered = sorted(pages, key=lambda p: (KIND_ORDER.index(p["kind"]), p["path"]))
    briefs = {p["id"]: page_brief(docs / p["path"]) for p in ordered}
    stale, unsynced = status["counts"]["stale"], status["counts"]["unsynced"]
    freshness_note = f"{stale} stale" + (f", {unsynced} never synced" if unsynced else "")
    guidance = (
        "Use them to find the right code fast and to learn why it is built this way. "
        "Pages summarize; source is authoritative: confirm names, limits, and behavior "
        "in the linked source before you answer or change code. "
    )
    if live:
        intro = (f"Pages live in `{doc_rel}/` ({len(pages)} pages, {freshness_note}). " + guidance
                 + "STALE means evidence the page cites changed after the last doc sync. ")
    else:
        intro = (f"Pages live in `{doc_rel}/` ({len(pages)} pages). " + guidance
                 + "Freshness changes between commits: run the Archlens `status` check before relying on a page. ")
    header = ["## Architecture handbook (Archlens)", intro + "After an architectural change, update the affected pages.", ""]

    def line(page, level):
        title, summary = briefs[page["id"]]
        text = f"- `{page['path']}` {title}"
        if level == 0 and summary and summary.lower() != title.lower():
            text += f": {summary}"
        if level <= 1 and page["covers"]:
            shown = ", ".join(page["covers"][:2]) + (f" +{len(page['covers']) - 2}" if len(page["covers"]) > 2 else "")
            text += f" [covers {shown}]"
        entry = states.get(page["id"]) if live else None
        if entry and entry["state"] == "stale":
            count = sum(c["severity"] == "stale" for c in entry["changed"])
            text += f" STALE: {count} cited change{'s' if count != 1 else ''}"
        return text

    for level in (0, 1, 2):
        lines = [line(page, level if page["kind"] != "decision" or level else 1) for page in ordered]
        text = "\n".join(header + lines)
        if len(text.encode("utf-8")) <= budget:
            return text + "\n"
    kept = []
    for page in ordered:
        candidate = "\n".join(header + kept + [line(page, 2), f"- +{len(ordered)} more pages in `{doc_rel}/map.json`"])
        if len(candidate.encode("utf-8")) > budget:
            break
        kept.append(line(page, 2))
    rest = len(ordered) - len(kept)
    return "\n".join(header + kept + [f"- +{rest} more pages in `{doc_rel}/map.json`"]) + "\n"


def write_context(root: Path, config: dict, target: Path) -> str:
    """Insert or replace the managed context block in an agent instruction file."""
    if not target.resolve().is_relative_to(root):
        raise ArchlensError(f"Context file escapes the project: {target}")
    block = f"{BLOCK_START}\n{build_context(root, config, live=False).rstrip()}\n{BLOCK_END}"
    existing = target.read_text(encoding="utf-8-sig") if target.exists() else ""
    if BLOCK_START.split(" - ")[0] in existing:
        pattern = re.compile(re.escape(BLOCK_START.split(" - ")[0]) + r".*?" + re.escape(BLOCK_END), re.S)
        updated = pattern.sub(lambda _: block, existing, count=1)
    else:
        updated = (existing.rstrip() + "\n\n" if existing.strip() else "") + block + "\n"
    if updated != existing:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(updated, encoding="utf-8")
    return target.relative_to(root).as_posix()


def context_already_loaded(root: Path, config: dict) -> bool:
    """True when CLAUDE.md already carries the block directly or through an import."""
    claude = root / "CLAUDE.md"
    try:
        text = claude.read_text(encoding="utf-8-sig")
    except OSError:
        return False
    if "archlens:context:start" in text:
        return True
    target = config.get("contextFile")
    return bool(target) and re.search(rf"(?m)^@{re.escape(target)}\s*$", text) is not None


def impact_report(root: Path, config: dict, base: str | None) -> dict:
    docs, pages = load_map(root, config)
    changed, merge_base = changed_files(root, base)
    doc_prefix = docs.relative_to(root).as_posix() + "/"
    source_changes = [path for path in changed if not path.startswith(doc_prefix) and path != ".archlens.json"]
    coverage = Coverage(root, docs, pages)
    covered = set()
    candidates = []
    for page in pages:
        matches = coverage.files(page["id"], source_changes)
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
            "Path and evidence-link matches identify review candidates, not proven drift.",
            "Uncovered files need triage; they are not necessarily architecture changes.",
            "Indirect dependencies require semantic review.",
        ],
    }


def hook_root(payload: dict) -> Path:
    for value in (os.environ.get("CLAUDE_PROJECT_DIR"), payload.get("cwd"), os.getcwd()):
        if value:
            return Path(value).expanduser().resolve()
    return Path.cwd()


def opted_in(root: Path, config: dict) -> bool:
    try:
        return (contained(root, config["docsRoot"], "docsRoot") / "map.json").is_file()
    except ArchlensError:
        return False


def session_key(root: Path, payload: dict) -> str:
    return hashlib.sha256(f"{root}|{payload.get('session_id', '')}".encode()).hexdigest()[:16]


def read_marker(name: str) -> str | None:
    folder = marker_folder()
    marker = folder / name if folder else None
    if not marker or marker.is_symlink():
        return None
    try:
        return marker.read_text(encoding="utf-8")
    except OSError:
        return None


def write_marker(name: str, value: str):
    folder = marker_folder()
    marker = folder / name if folder else None
    if marker and not marker.is_symlink():
        try:
            marker.write_text(value, encoding="utf-8")
        except OSError:
            pass


def hook_session_start(root: Path, config: dict, payload: dict | None = None) -> str:
    if not opted_in(root, config):
        return ""
    if in_git(root):
        head = head_commit(root)
        if head:
            write_marker(f"head-{session_key(root, payload or {})}.txt", head)
    if not config["sessionContext"] or context_already_loaded(root, config):
        return ""
    return build_context(root, config)


def hook_file_pointer(root: Path, config: dict, payload: dict) -> dict | None:
    """Point the agent to the page that documents a file it just read or edited, once per page."""
    if not config["filePointers"] or not opted_in(root, config):
        return None
    tool_input = payload.get("tool_input") or {}
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw, str) or not raw:
        return None
    path = Path(raw)
    path = (path if path.is_absolute() else root / path).resolve()
    if not path.is_relative_to(root):
        return None
    relative = path.relative_to(root).as_posix()
    docs, pages = load_map(root, config)
    if path.is_relative_to(docs):
        return None
    coverage = Coverage(root, docs, pages)
    key = session_key(root, payload)
    seen = set(filter(None, (read_marker(f"pointers-{key}.txt") or "").split("\n")))
    cited = [p for p in pages if coverage.whole_file_evidence(p["id"], relative)
             or any(a[0] == relative for a in coverage.evidence[p["id"]][1])]
    matched = cited + [p for p in pages if p not in cited and coverage.matches(p["id"], relative)]
    fresh = [p for p in matched if p["id"] not in seen][:2]
    if not fresh:
        return None
    write_marker(f"pointers-{key}.txt", "\n".join(sorted(seen | {p["id"] for p in fresh})))
    doc_rel = docs.relative_to(root).as_posix()
    listed = " and ".join(f"`{doc_rel}/{p['path']}` ({page_brief(docs / p['path'])[0]})" for p in fresh)
    return {"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": f"Archlens: `{relative}` is documented in {listed}. "
                             "Read it for intent before larger changes; update it if behavior changes.",
    }}


def marker_folder() -> Path | None:
    """A private folder for reminder markers; None if it is unsafe to use."""
    configured = os.environ.get("CLAUDE_PLUGIN_DATA")
    user = os.getuid() if hasattr(os, "getuid") else os.environ.get("USERNAME", "user")
    folder = Path(configured) if configured else Path(tempfile.gettempdir()) / f"archlens-{user}"
    try:
        if folder.is_symlink():
            return None
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        if hasattr(os, "getuid") and folder.stat().st_uid != os.getuid():
            return None
    except OSError:
        return None
    return folder


def hook_stop(root: Path, config: dict, payload: dict) -> dict | None:
    """Nudge once per new set of stale pages that this working tree changed."""
    if config["autoUpdate"] == "off" or not opted_in(root, config) or not in_git(root):
        return None
    dirty = set(names(git(root, "diff", "HEAD", "--relative", "--no-ext-diff", "--no-renames", "--name-only", "-z")))
    dirty |= set(names(git(root, "ls-files", "--others", "--exclude-standard", "-z")))
    start = (read_marker(f"head-{session_key(root, payload)}.txt") or "").strip()
    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", start):
        try:
            dirty |= set(names(git(root, "diff", "--relative", "--no-ext-diff", "--no-renames", "--name-only", "-z", start, "HEAD", "--")))
        except ArchlensError:
            pass
    if not dirty:
        return None
    moved_fixed = 0
    if config["fixAnchors"]:
        moved_fixed = len(fix_anchors(root, config)["fixed"])
    status = freshness(root, config)
    affected = []
    for entry in status["needsSync"]:
        paths = [c["path"] for c in entry["changed"] if c["path"] in dirty and c["severity"] == "stale"]
        if entry["state"] == "stale" and paths:
            affected.append((entry["page"], entry["id"], sorted(paths)))
    note = f"Archlens updated {moved_fixed} moved line link(s) in the handbook. " if moved_fixed else ""
    if not affected:
        return {"systemMessage": note.strip()} if note else None
    signature = hashlib.sha256(json.dumps(affected).encode()).hexdigest()
    name = f"notified-{session_key(root, payload)}.txt"
    if read_marker(name) == signature:
        return None
    write_marker(name, signature)
    docs_prefix = config["docsRoot"].rstrip("/") + "/"
    pages = ", ".join(page.removeprefix(docs_prefix) for page, _, _ in affected[:4]) + (f" +{len(affected) - 4}" if len(affected) > 4 else "")
    if config["autoUpdate"] == "auto" and not payload.get("stop_hook_active"):
        ids = " ".join(page_id for _, page_id, _ in affected)
        return {
            "decision": "block",
            "reason": (
                f"Archlens autoUpdate: your changes made these handbook pages stale: {pages}. "
                f"Invoke the archlens:update skill with pages {ids}; it runs in an isolated task. "
                "Then end your turn. Skip this if the user said not to touch documentation."
            ),
        }
    return {"systemMessage": f"{note}Archlens: {len(affected)} handbook page(s) cite code you changed ({pages}). Run /archlens:update to refresh them."}


def run_hook(event: str) -> int:
    """Claude Code hook entrypoint. Never fails the session and stays silent when not opted in."""
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
        root = hook_root(payload)
        config, _ = load_config(root)
        if event == "session-start":
            text = hook_session_start(root, config, payload)
            if text:
                print(text, end="")
        elif event == "file-pointer":
            result = hook_file_pointer(root, config, payload)
            if result:
                print(json.dumps(result))
        elif event == "stop":
            result = hook_stop(root, config, payload)
            if result:
                print(json.dumps(result))
    except Exception:  # noqa: BLE001 - a documentation hook must never break the agent session
        return 0
    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("config", "check", "impact", "status", "sync", "context", "fix-anchors"):
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
        if name == "status":
            command.add_argument("--fail-on-stale", action="store_true", help="Exit 1 when any page is stale or unsynced")
            command.add_argument("--fail-on-review", action="store_true", help="Also exit 1 when covered files changed outside cited evidence")
        if name == "fix-anchors":
            command.add_argument("--page", action="append", default=[], help="Limit to this page ID (repeatable)")
        if name == "sync":
            command.add_argument("--page", action="append", default=[], help="Page ID to mark as synced (repeatable)")
            command.add_argument("--all", action="store_true", help="Mark every mapped page as synced")
        if name == "context":
            command.add_argument("--write", nargs="?", const="", metavar="FILE",
                                 help="Update the managed block in FILE (default: configured contextFile)")
            command.add_argument("--budget", type=int, help="Maximum digest bytes (default: contextBudget)")
    hook = commands.add_parser("hook", help="Claude Code hook entrypoint (silent unless the project opted in)")
    hook.add_argument("event", choices=["session-start", "stop", "file-pointer"])
    return parser


def bounded_report(report: dict, budget: int = 6000) -> dict:
    """Keep whole records and explicit omission counts, never silently truncate JSON."""
    collection_keys = ("findings", "candidates", "uncoveredFiles", "changedFiles", "needsSync", "fresh", "fixed")
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
    if report["command"] == "context":
        print(report["context"], end="")
        if report.get("written"):
            print(f"Updated managed block in {report['written']}", file=sys.stderr)
        return
    print(f"Archlens {report['command']}: {'PASS' if report['ok'] else 'REVIEW REQUIRED'}")
    if report["command"] == "config":
        print(json.dumps(report["config"], indent=2))
        print("Sources:\n  " + "\n  ".join(report["sources"]))
    elif report["command"] == "check":
        print(f"{report['pages']} pages; {report['mermaidBlocks']} Mermaid blocks (not rendered).")
        for finding in report["findings"]:
            print(f"{finding['severity'].upper()} {finding['path']}:{finding['line']} [{finding['code']}] {finding['message']}")
    elif report["command"] == "status":
        counts = report["counts"]
        print(f"{counts['fresh']} fresh, {counts['stale']} stale, {counts['review']} review, {counts['unsynced']} unsynced.")
        for entry in report["needsSync"]:
            def describe(c):
                where = c["path"] + (f"#L{c['lines'][0]}-L{c['lines'][1]}" if c.get("lines") else "")
                where += f" ({c['symbol']})" if c.get("symbol") else ""
                moved = f" -> #L{c['newLines'][0]}-L{c['newLines'][1]}" if c.get("newLines") else ""
                return f"{c['change']} {where}{moved}"
            hard = [c for c in entry["changed"] if c["severity"] == "stale"]
            soft = [c for c in entry["changed"] if c["severity"] != "stale"]
            detail = ", ".join(describe(c) for c in hard[:6]) + (f" +{len(hard) - 6}" if len(hard) > 6 else "")
            if soft:
                detail += ("; " if detail else "") + "review: " + ", ".join(describe(c) for c in soft[:3])
                detail += f" +{len(soft) - 3}" if len(soft) > 3 else ""
            print(f"{entry['state'].upper()} {entry['page']} [{entry['id']}] {detail}".rstrip())
    elif report["command"] == "fix-anchors":
        print(f"Fixed {len(report['fixed'])} moved line link(s).")
        for item in report["fixed"]:
            print(f"FIXED {item['page']}: {item['path']}#L{item['from'][0]}-L{item['from'][1]} -> #L{item['to'][0]}-L{item['to'][1]}")
    elif report["command"] == "sync":
        print(f"Synced {len(report['synced'])} page(s): {', '.join(report['synced'])}")
        if report.get("contextFile"):
            print(f"Refreshed context block in {report['contextFile']}")
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
    if args.command == "hook":
        return run_hook(args.event)
    try:
        root = args.root.expanduser().resolve()
        if not root.is_dir():
            raise ArchlensError(f"Project root is not a directory: {root}")
        config, sources = load_config(root)
        failed = False
        if args.command == "config":
            report = {"command": "config", "root": str(root), "config": config, "sources": sources}
        elif args.command == "check":
            report = check_documents(root, config)
            failed = any(f["severity"] == "error" or args.strict for f in report["findings"])
        elif args.command == "status":
            report = freshness(root, config)
            gate = {"stale", "unsynced"} | ({"review"} if args.fail_on_review else set())
            failed = (args.fail_on_stale or args.fail_on_review) and any(e["state"] in gate for e in report["needsSync"])
        elif args.command == "sync":
            report = sync_pages(root, config, args.page, args.all)
        elif args.command == "fix-anchors":
            report = fix_anchors(root, config, args.page or None)
        elif args.command == "context":
            if args.budget is not None and not 600 <= args.budget <= 20000:
                raise ArchlensError("--budget must be from 600 to 20000 bytes")
            report = {"command": "context", "root": str(root), "context": build_context(root, config, args.budget)}
            if args.write is not None:
                target = args.write or config.get("contextFile")
                if not target:
                    raise ArchlensError("Name a file (--write AGENTS.md) or set contextFile in .archlens.json")
                report["written"] = write_context(root, config, contained(root, relative_path(target, "--write"), "--write"))
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
