#!/usr/bin/env python3
"""Standard-library helper for Archlens: checks, freshness, sync, and agent context. Python 3.9+."""

from __future__ import annotations

import argparse
import ast
import bisect
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import subprocess
import sys
import tempfile
import tokenize
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
AUTO_UPDATE = {"off", "remind", "commit", "auto"}
DOC_SUFFIXES = {".md", ".mdx", ".markdown", ".rst", ".adoc", ".txt"}
COMMIT_COMMAND = re.compile(r"(?:^|[;&|(\s])git(?:\s+-[Cc]\s+\S+)*\s+commit\b")
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


def page_location(root: Path, docs: Path, value, label: str) -> tuple[str, Path]:
    """A page path relative to the handbook. Leading '../' segments map an existing document
    in place, such as '../ARCHITECTURE.md'; the page must stay inside the project."""
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        raise ArchlensError(f"{label} must be a non-empty relative path")
    normalized = value.replace("\\", "/")
    if PureWindowsPath(value).drive or normalized.startswith("/"):
        raise ArchlensError(f"{label} must not be an absolute path")
    parts = normalized.split("/")
    lead = next((i for i, part in enumerate(parts) if part != ".."), len(parts))
    if lead == len(parts) or any(part in {"", ".", ".."} for part in parts[lead:]):
        raise ArchlensError(f"{label} may start with '../' but must not contain other empty, '.' or '..' segments")
    resolved = (docs / normalized).resolve()
    if not resolved.is_relative_to(root):
        raise ArchlensError(f"{label} escapes the project: {value}")
    if lead and resolved.is_relative_to(docs):
        raise ArchlensError(f"{label}: write pages inside the handbook without '..': {value}")
    if ".git" in resolved.relative_to(root).parts:
        raise ArchlensError(f"{label} must not point into .git: {value}")
    return normalized, resolved


def load_map(root: Path, config: dict) -> tuple[Path, list[dict]]:
    root = root.resolve()
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
        path, resolved = page_location(root, docs, page["path"], f"{label}.path")
        if not path.endswith(".md"):
            raise ArchlensError(f"{label}.path must end in .md")
        if path.casefold() in paths or resolved in resolved_paths:
            raise ArchlensError(f"Duplicate page path: {path}")
        paths.add(path.casefold())
        resolved_paths.add(resolved)
        page["path"] = path
        page["_file"] = resolved
        page["_relative"] = resolved.relative_to(root).as_posix()
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
        return location, parts.fragment, f"Missing local link target: {target}"
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


def near_symbol(root: Path, location: Path, fragment: str) -> str | None:
    """A line range that cuts off the first or last code line of a function or class by
    one or two lines is almost always an off-by-one citation. Blank and comment lines at
    either end do not count. Name the exact range so the author can fix it."""
    span = re.fullmatch(r"L(\d+)(?:-L(\d+))?", fragment or "")
    if not span or not span[2] or not location.is_file():
        return None
    relative = location.relative_to(root.resolve()).as_posix()
    text = read_source(location)
    symbols = code_symbols(relative, text) if text is not None else None
    if not symbols:
        return None
    code = [n for n, _ in code_lines(relative, text) if int(span[1]) <= n <= int(span[2])]
    if not code:
        return None
    first, last = code[0], code[-1]
    for name, start, end, _ in symbols:
        if end - start < 4 or not (abs(start - first) <= 2 and abs(end - last) <= 2):
            continue
        if first > start or last < end:
            return (f"#L{span[1]}-L{span[2]} cuts off part of `{name}` (#L{start}-L{end}) in {location.name}; "
                    "cite the exact range (the `cite` command prints it).")
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

    HISTORY_LOOKUPS = 40

    def __init__(self, root: Path, docs: Path, pages=()):
        self.root = root
        handbook = docs.relative_to(root).as_posix()
        self.exclude = [f":(exclude){handbook}"] + [f":(exclude){page}" for page in pages
                                                     if not page.startswith(handbook + "/")]
        self.git = in_git(root)
        self.symbols: dict[str, bool] = {}
        self.paths: dict[str, bool] = {}
        self.lookups = 0
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
                if not (self.root / path).exists() and not (page.parent / path).exists() and self.missing(path):
                    yield f"Path not found: {token}"

    def missing(self, path: str) -> bool:
        """A missing path counts unless Git ignores it (generated or local files) or it is an
        extension-less name that never existed, such as the MCP method `tools/list`."""
        if not self.git:
            return True
        if path not in self.paths:
            self.paths[path] = not self.ignored(path) and (
                "." in path.rsplit("/", 1)[-1] or self.ever_tracked(path))
        return self.paths[path]

    def ignored(self, path: str) -> bool:
        try:
            result = subprocess.run(
                ["git", "--no-pager", "-C", str(self.root), "check-ignore", "-q", "--", path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    def ever_tracked(self, path: str) -> bool:
        """True if any commit touched the path. Bounded so huge histories stay fast."""
        if self.lookups >= self.HISTORY_LOOKUPS:
            return True
        self.lookups += 1
        try:
            result = subprocess.run(
                ["git", "--no-pager", "-C", str(self.root), "log", "--all", "-1", "--format=%h", "--", path],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return True
        return result.returncode != 0 or bool(result.stdout.strip())

    def symbol_exists(self, name: str) -> bool:
        if name not in self.symbols:
            try:
                found = git(self.root, "grep", "--untracked", "-l", "-w", "-F", "-e", name, "--", ".", *self.exclude)
                self.symbols[name] = bool(found.strip())
            except ArchlensError:
                self.symbols[name] = False
        return self.symbols[name]


COMMIT_IN_PROSE = re.compile(r"\bcommit\s+`?(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b`?", re.I)


def table_cells(line: str) -> list[str]:
    """Cells of one Markdown table row; pipes inside code spans or escaped do not split."""
    cells, current, code = [], "", False
    body = line.strip()
    body = body[1:] if body.startswith("|") else body
    body = body[:-1] if body.endswith("|") and not body.endswith("\\|") else body
    for index, char in enumerate(body):
        if char == "`":
            code = not code
        if char == "|" and not code and (index == 0 or body[index - 1] != "\\"):
            cells.append(current.strip())
            current = ""
        else:
            current += char
    return cells + [current.strip()]


HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
LIST_ITEM = re.compile(r"^\s*(?:([-*+])|(\d+)[.)])\s+(.*)$")
TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def page_sections(text: str) -> list[dict]:
    """Leaf sections of a page: each heading with the lines up to the next heading.

    Line numbers are 1-based and inclusive, so an agent can read one section with an offset."""
    total = len(text.splitlines())
    prose, blocks, _ = markdown_sections(text)
    heads = [(number, len(match[1]), match[2].strip()) for number, line in prose if (match := HEADING.match(line))]
    sections, trail = [], []
    first = heads[0][0] if heads else total + 1
    if any(line.strip() for number, line in prose if number < first) or any(start < first for start, _, _ in blocks):
        sections.append({"heading": "", "level": 0, "trail": [], "lines": [1, first - 1]})
    for index, (number, level, title) in enumerate(heads):
        trail = [item for item in trail if item[0] < level] + [(level, title)]
        end = heads[index + 1][0] - 1 if index + 1 < len(heads) else total
        sections.append({"heading": title, "level": level, "trail": [name for _, name in trail[:-1]], "lines": [number, end]})
    for section in sections:
        first, last = section["lines"]
        section["diagrams"] = [
            {"type": mermaid_type(body) or "unknown", "lines": [start, start + len(body.splitlines()) + 1]}
            for start, language, body in blocks if language == "mermaid" and first <= start <= last
        ]
    return sections


def page_tables(prose) -> list[dict]:
    """Tables outside code fences: header cells and body rows with their line numbers."""
    tables, rows = [], []
    for number, line in [*prose, (0, "")]:
        if line.lstrip().startswith("|"):
            rows.append((number, line))
            continue
        if len(rows) >= 3 and TABLE_RULE.match(rows[1][1]):
            tables.append({"line": rows[0][0], "header": table_cells(rows[0][1]),
                           "rows": [(n, table_cells(row)) for n, row in rows[2:]]})
        rows = []
    return tables


def plain_text(markdown: str) -> str:
    """Prose without code, link targets, HTML, or emphasis marks. `X` stands for removed code."""
    text = re.sub(r"`[^`]*`", " X ", markdown)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>|https?://\S+", " X ", text)
    text = re.sub(r"\*{1,3}|~~|(?<!\w)_{1,3}|_{1,3}(?!\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def cell_text(cell: str) -> str:
    """A table cell as a reader sees it: link text and code kept, marks removed."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", cell)
    return re.sub(r"\s+", " ", re.sub(r"[`*~]", "", text)).strip()


def step_numbers(cell: str) -> set[int]:
    """Step numbers named by a step-table cell, such as `7`, `4-5`, or `11, 13`."""
    found = set()
    for first, last in re.findall(r"(\d+)(?:\s*[-–]\s*(\d+))?", plain_text(cell)):
        low, high = int(first), int(last or first)
        if low <= high <= low + 200:
            found.update(range(low, high + 1))
    return found


SEQUENCE_KEYWORDS = re.compile(
    r"^\s*(?:note|participant|actor|loop|alt|else|opt|par|and|critical|option|break|rect|end|autonumber|"
    r"activate|deactivate|title|box|create|destroy|links?|sequenceDiagram|%%)\b", re.I)
SEQUENCE_ARROW = re.compile(r"(?:<<)?--?(?:>>|>|x|\))[+-]?\s*[^:]*:")
FLOW_WORDS = {"subgraph", "end", "direction", "classdef", "class", "style", "linkstyle", "click", "flowchart", "graph",
              "tb", "td", "bt", "lr", "rl"}


def sequence_messages(body: str) -> int:
    """Numbered messages in a Mermaid sequence diagram (what `autonumber` counts)."""
    return sum(1 for line in body.splitlines()
               if not SEQUENCE_KEYWORDS.match(line) and SEQUENCE_ARROW.search(line))


def flowchart_nodes(body: str) -> int:
    """Distinct node IDs in a Mermaid flowchart. A heuristic reader, not a parser."""
    nodes = set()
    for line in body.splitlines():
        line = re.sub(r"%%.*$", "", line)
        line = re.sub(r'"[^"]*"', "", line)
        first = line.split(None, 1)[0].lower() if line.split() else ""
        if first in {"classdef", "class", "style", "linkstyle", "click", "direction"} or first.startswith("%%"):
            continue
        if first == "subgraph":
            continue
        line = re.sub(r"\|[^|]*\|", " ", line)                      # edge labels
        line = re.sub(r"--\s[^-|>]*?\s(?=--|-\.|==)", "--", line)    # inline edge text: A -- text --> B
        line = re.sub(r"[\[({]+[^\[\](){}]*[\])}]+", " ", line)        # node shapes and labels
        line = re.sub(r"[<xo]?(?:-{2,}|-\.+-|={2,})[>xo]?|-\.->|:::\w+|&|;", " ", line)
        for token in re.findall(r"[A-Za-z_][\w-]*", line):
            if token.lower() not in FLOW_WORDS:
                nodes.add(token)
    return len(nodes)


SENTENCE_BREAK = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])")
ABBREVIATION = re.compile(r"\b(?:e\.g|i\.e|etc|vs|cf|approx|No|Fig)\.[\"')\]]*$", re.I)
WORDY = re.compile(
    r"\b(in order to|in the event of|due to the fact that|a number of|utili[sz](?:e|es|ed|ing)|simply|"
    r"basically|obviously|of course|and/or|etc|as needed|as appropriate|very)\b", re.I)
PASSIVE_BY = re.compile(
    r"\b(?:is|are|was|were|be|been|being)\s+(?:(?:not|also|never|always|only|then|\w+ly)\s+)*(\w+)\s+by\b", re.I)
PARTICIPLES = {
    "built", "bound", "brought", "caught", "chosen", "done", "drawn", "driven", "found", "given", "held", "hidden",
    "kept", "known", "left", "lost", "made", "meant", "paid", "read", "run", "seen", "sent", "set", "shown", "sold",
    "taken", "thrown", "told", "understood", "written",
}
DESCRIPTION_WORDS, PROCEDURE_WORDS = 25, 20


def style_units(prose) -> list[tuple[list[tuple[int, str]], bool, bool]]:
    """Prose units as (numbered lines, procedural, needs a full stop): paragraphs, list items, table cells."""
    units, current = [], None
    lines = list(prose)

    def flush():
        nonlocal current
        if current and any(text.strip() for _, text in current[0]):
            units.append(tuple(current))
        current = None

    for index, (number, line) in enumerate(lines):
        stripped = re.sub(r"^\s*(?:>\s?)+", "", line).strip()
        if not stripped or HEADING.match(line) or stripped.startswith(("<!--", "---", "***", "===")) \
                or re.match(r"^\[[^\]]+\]:\s", stripped):
            flush()
            continue
        if stripped.startswith("|"):
            flush()
            following = lines[index + 1][1] if index + 1 < len(lines) else ""
            if TABLE_RULE.match(stripped) or TABLE_RULE.match(following.strip()):
                continue
            units.extend(([(number, cell)], False, True) for cell in table_cells(stripped) if cell)
            continue
        item = LIST_ITEM.match(line)
        if item:
            flush()
            current = [[(number, item[3])], item[2] is not None, True]
        elif current:
            current[0].append((number, stripped))
        else:
            current = [[(number, stripped)], False, False]
    flush()
    return units


def style_sentences(prose) -> list[dict]:
    """Complete sentences with the mechanical rules each one breaks.

    Checks length, semicolons, by-passives, and listed wordy phrases. It cannot judge
    actors, terminology, or ambiguity, so a pass here is not a pass of the full rubric."""
    sentences = []
    for parts, procedural, needs_stop in style_units(prose):
        # Clean the whole unit, so a link or code span that wraps over two lines stays whole.
        # Then find the line of each sentence by its share of the unit's raw text.
        raw = " ".join(text for _, text in parts)
        text = plain_text(raw)
        starts, offset = [], 0
        for number, part in parts:
            starts.append((offset, number))
            offset += len(part) + 1
        pieces, position = [], 0
        for match in [*SENTENCE_BREAK.finditer(text), None]:
            end = match.start() if match else len(text)
            piece = text[position:end]
            if pieces and ABBREVIATION.search(pieces[-1][1]):
                pieces[-1] = (pieces[-1][0], pieces[-1][1] + " " + piece)
            else:
                pieces.append((position, piece))
            position = match.end() if match else end
        for position, piece in pieces:
            words = [w for w in re.findall(r"[A-Za-z0-9][\w'\u2019/-]*", piece) if w != "X"]
            ended = re.search(r"[.!?:][\"')\]]*$", piece) is not None
            if len(words) < 3 or (needs_stop and not ended):
                continue
            # Map the cleaned offset back to a raw line by proportion; exact for one-line units.
            scaled = position * len(raw) / max(1, len(text))
            line = max((number for start, number in starts if start <= scaled + 1), default=parts[0][0])
            limit = PROCEDURE_WORDS if procedural else DESCRIPTION_WORDS
            reasons = []
            if len(words) > limit:
                reasons.append("long")
            if ";" in piece:
                reasons.append("semicolon")
            passive = PASSIVE_BY.search(piece)
            if passive and (passive[1].lower().endswith("ed") or passive[1].lower() in PARTICIPLES):
                reasons.append("passive")
            if WORDY.search(piece):
                reasons.append("wordy")
            sentences.append({"line": line, "words": len(words), "reasons": reasons})
    return sentences


def unknown_columns(prose) -> list[tuple[int, str]]:
    """(header line, column name) for table columns whose every body cell says unknown."""
    found = []
    for table in page_tables(prose):
        if len(table["rows"]) < 3:
            continue
        for column, name in enumerate(table["header"]):
            values = {re.sub(r"[*_`]", "", cells[column]).strip().lower()
                      for _, cells in table["rows"] if column < len(cells)}
            if values == {"unknown"}:
                found.append((table["line"], name or f"column {column + 1}"))
    return found


def mentions_handbook(root: Path, docs: Path, source: Path) -> bool:
    """True when a file outside the handbook links to it, or a root file names its folder."""
    try:
        text = source.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return False
    if source.parent == root and docs.relative_to(root).as_posix() in text:
        return True
    if source.suffix.lower() not in {".md", ".mdx", ".markdown"}:
        return False
    for _, line in markdown_sections(text)[0]:
        for target in local_targets(line):
            location, _, problem = resolve_link(root, source, target)
            if location is not None and not problem and location.is_relative_to(docs):
                return True
    return False


def placement_findings(root: Path, docs: Path, pages: list[dict]) -> list[tuple]:
    """Handbook placement problems: a second decision folder, or a handbook nothing points to."""
    findings = []
    inside = [page for page in pages if page["_file"].is_relative_to(docs)]
    outside = [page for page in pages if page not in inside]
    own = [page for page in inside if page["kind"] == "decision"]
    adopted = [page for page in outside if page["kind"] == "decision"]
    # The project's decision home is where most records live. Flag only the minority folder.
    if own and len(adopted) >= len(own):
        folder = sorted({page_file(root, page).rsplit("/", 1)[0] for page in adopted})[0]
        for page in own:
            findings.append(("warning", page_file(root, page), 1, "decision-split",
                             f"The project keeps decision records in `{folder}/`. Record this decision "
                             "there with its numbering and format, and link it from the handbook."))
    if docs != root and (root / "README.md").is_file() and inside:
        sources = [path for path in sorted(root.iterdir()) if path.is_file()
                   and path.suffix.lower() in {".md", ".mdx", ".markdown", ".yml", ".yaml", ".toml"}]
        folder = docs.parent
        while folder != root and folder.is_relative_to(root):
            sources += [folder / name for name in ("README.md", "index.md") if (folder / name).is_file()]
            folder = folder.parent
        sources += [page["_file"] for page in outside]
        if not any(mentions_handbook(root, docs, source) for source in sources):
            entry = next((page for page in inside if page["kind"] == "index"), inside[0])
            findings.append(("warning", page_file(root, entry), 1, "unlinked-handbook",
                             "Nothing outside the handbook points to it. Link this page from README.md "
                             "or the main architecture document, so people and other agents find it."))
    return findings


def check_documents(root: Path, config: dict, style_gate: bool = False) -> dict:
    docs, pages = load_map(root, config)
    findings = []
    diagram_count = 0

    def add(severity, path, line, code, message):
        findings.append({"severity": severity, "path": path, "line": line, "code": code, "message": message})

    references = References(root, docs, [page_file(root, page) for page in pages])
    mapped = {page["_file"] for page in pages}
    style_total = style_passing = 0
    for finding in placement_findings(root, docs, pages):
        add(*finding)
    for path in sorted(docs.rglob("*.md")):
        contained(docs, path.relative_to(docs).as_posix(), "documentation page")
        if path.resolve() not in mapped:
            add("error", path.relative_to(root).as_posix(), 1, "unmapped-page", "Add this page to map.json.")
    for page in pages:
        path = page["_file"]
        relative = page_file(root, page)
        if not path.is_file():
            add("error", relative, 1, "missing-page", "Mapped page does not exist.")
            continue
        text = path.read_text(encoding="utf-8-sig")
        owned = path.is_relative_to(docs)
        # An adopted document keeps its own conventions: presentation advice is a note, not a warning.
        advice = "warning" if owned else "info"
        # Decision records are history: a path they name may be gone by design.
        historical = page["kind"] == "decision" and page.get("decisionStatus") != "proposed"
        prose, blocks, unclosed = markdown_sections(text)
        if unclosed:
            add("error", relative, unclosed, "unclosed-block", "Close the code fence or metadata block.")
        if not re.search(r"(?m)^#\s+\S", "\n".join(line for _, line in prose)):
            add(advice, relative, 1, "missing-title", "Add a level-one page title.")
        if owned:
            commits = [number for number, line in prose if COMMIT_IN_PROSE.search(line)]
            if commits and page["kind"] != "decision":
                add("info", relative, commits[0], "prose-metadata",
                    f"Commit IDs in prose (lines {', '.join(map(str, commits[:5]))}) repeat map.json and "
                    "the sync state, and go stale after the next sync. Link the evidence instead.")
            for number, name in unknown_columns(prose):
                add("info", relative, number, "unknown-column",
                    f"Column '{name}' is unknown in every row. Drop it and state the unknown once.")
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
                elif location is not None:
                    near = near_symbol(root, location, fragment)
                    if near:
                        add("warning", relative, number, "anchor-offset", near)
            if not historical:
                for problem in references.problems(path, line):
                    add("warning", relative, number, "stale-reference", problem)
        sentences = style_sentences(prose)
        failing = [sentence for sentence in sentences if sentence["reasons"]]
        if owned:
            style_total += len(sentences)
            style_passing += len(sentences) - len(failing)
        if failing:
            lines = sorted({sentence["line"] for sentence in failing})
            labels = (("long", "long"), ("semicolon", "with semicolons"), ("passive", "passive with 'by'"), ("wordy", "wordy"))
            parts = [f"{count} {label}" for key, label in labels
                     if (count := sum(key in sentence["reasons"] for sentence in failing))]
            shown = ", ".join(map(str, lines[:5])) + (f" +{len(lines) - 5}" if len(lines) > 5 else "")
            findings.append({
                "severity": "info", "path": relative, "line": lines[0], "code": "style",
                "message": f"Mechanical style: {len(sentences) - len(failing)} of {len(sentences)} sentences pass. "
                           f"Candidates: {', '.join(parts)} (lines {shown}). Split or reword where it helps.",
                "lines": lines, "sentences": len(sentences), "passing": len(sentences) - len(failing),
            })
        tables = page_tables(prose)
        diagrams = sorted((number, body) for number, language, body in blocks if language == "mermaid")
        for position, (number, body) in enumerate(diagrams):
            diagram_count += 1
            if not body.strip():
                add("error", relative, number, "empty-diagram", "Add diagram source or remove the empty block.")
                continue
            kind = mermaid_type(body)
            if kind not in MERMAID_TYPES and kind != "frontmatter":
                add("error", relative, number, "mermaid-type", f"Unknown Mermaid diagram type: {kind}")
            if kind in {"flowchart", "graph"}:
                nodes = flowchart_nodes(body)
                if nodes > config["maxDiagramNodes"]:
                    add(advice, relative, number, "diagram-density",
                        f"{nodes} nodes exceed maxDiagramNodes ({config['maxDiagramNodes']}). Consider splitting this view.")
            if re.search(r"(?m)^\s*sequenceDiagram\s*$", body):
                numbered = re.search(r"(?m)^\s*autonumber(?:\s.*)?$", body) is not None
                if not numbered:
                    add(advice, relative, number, "sequence-numbers", "Use autonumber to connect messages to steps.")
                participants = len(re.findall(r"(?m)^\s*(?:participant|actor)\s+", body))
                if participants > config["maxSequenceParticipants"]:
                    add(advice, relative, number, "sequence-density", "Consider splitting this sequence.")
                # The step table between this diagram and the next one must name only real messages.
                following = diagrams[position + 1][0] if position + 1 < len(diagrams) else float("inf")
                steps = next((table for table in tables if number < table["line"] < following
                              and re.match(r"(?i)^step\b", plain_text(table["header"][0]))), None)
                if numbered and steps:
                    messages = sequence_messages(body)
                    named = {step: row for row, cells in steps["rows"] for step in step_numbers(cells[0])}
                    beyond = sorted(step for step in named if step > messages)
                    if beyond:
                        add("warning", relative, named[beyond[0]], "sequence-steps",
                            f"The step table names step {beyond[0]}, but the diagram has {messages} numbered messages.")
                    missing = [step for step in range(1, messages + 1) if step not in named]
                    if missing and not beyond:
                        shown = ", ".join(map(str, missing[:6])) + (f" +{len(missing) - 6}" if len(missing) > 6 else "")
                        add("info", relative, steps["line"], "sequence-steps",
                            f"Diagram messages without a step row: {shown}.")
    rate = round(style_passing / style_total, 2) if style_total >= 20 else None
    if style_gate and rate is not None and rate < config["styleTarget"]:
        entry = next((page for page in pages if page["kind"] == "index"), pages[0])
        add("warning", page_file(root, entry), 1, "style-target",
            f"Mechanical style pass rate {rate:.2f} is below styleTarget {config['styleTarget']} "
            f"({style_passing} of {style_total} handbook sentences pass).")
    # Broken links and vanished references first; presentation advice last.
    rank = {"error": 0, "warning": 1, "info": 2}
    cosmetic = {"sequence-numbers", "sequence-density", "diagram-density", "missing-title", "style-target"}
    findings.sort(key=lambda f: (rank[f["severity"]], f["code"] in cosmetic, f["path"], f["line"]))
    return {
        "command": "check", "root": str(root), "pages": len(pages),
        "mermaidBlocks": diagram_count, "findings": findings,
        "stylePassRate": rate,
        "style": {"sentences": style_total, "passing": style_passing, "target": config["styleTarget"]},
        "limits": [
            "Mermaid rendering and semantic accuracy are not checked; diagram type, density, and step numbers are.",
            "Inline Markdown links, reference definitions, heading anchors, and line anchors are checked; remote URLs are not.",
            "Backticked paths, function() names, and npm scripts are checked for existence, not meaning.",
            "Placement checks look at root files, parent README or index files, and mapped documents.",
            "stylePassRate is a mechanical floor for handbook-owned pages: sentence length, semicolons, "
            "by-passives, and listed wordy phrases. It is not an STE score or ASD-STE100 compliance.",
            "Style notes (info) never fail --strict. Only --style gates on styleTarget.",
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


def page_file(root: Path, page: dict) -> str:
    """Project-relative path of a mapped page."""
    return page["_relative"]


def page_evidence(root: Path, docs: Path, page_path: Path, mapped=frozenset()) -> tuple[list[str], list[tuple[str, int, int]]]:
    """Linked project files or folders outside the handbook and other mapped pages,
    plus line-range anchors."""
    try:
        text = page_path.read_text(encoding="utf-8-sig")
    except OSError:
        return [], []
    prose, _, _ = markdown_sections(text)
    links, anchors = set(), set()
    for _, line in prose:
        for target in local_targets(line):
            location, fragment, problem = resolve_link(root, page_path, target)
            # A link whose target was deleted still names evidence: its removal makes the page stale.
            missing = bool(problem) and problem.startswith("Missing local link target")
            if (problem and not missing) or location is None or location.is_relative_to(docs) or location in mapped:
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
        mapped = {page["_file"] for page in pages}
        for page in pages:
            patterns = [(glob_prefix(p), glob_regex(p)) for p in page["covers"]]
            links, anchors = page_evidence(root, docs, page["_file"], mapped)
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


BRACE_LANGUAGES = {
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".go", ".rs", ".java", ".kt",
    ".kts", ".scala", ".swift", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".cs", ".php", ".dart",
}
KEYWORD_DECLARATION = re.compile(
    r"(?:^|[^\w$.])(?:function\*?|class|interface|enum|struct|trait|impl(?:<[^>]*>)?|record|object|namespace|func|fn)"
    r"\s+(?:\([^)]*\)\s*)?([A-Za-z_$][\w$]*)"
    r"|^\s*(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:const|let|var|val)\s+([A-Za-z_$][\w$]*)"
    r"|^\s*(?:export\s+)?(?:declare\s+)?type\s+([A-Za-z_$][\w$]*)\s*(?:<[^=]*>)?\s*(?:=|struct\b|interface\b)"
)
METHOD_DECLARATION = re.compile(
    r"^\s*(?:(?:public|private|protected|internal|static|final|abstract|override|async|readonly|virtual|"
    r"sealed|open|suspend|inline|export|default|get|set|synchronized|unsafe|extern|pub(?:\([^)]*\))?)\s+)*"
    r"(?:[\w$<>\[\],.?*&:]+\s+)*?([A-Za-z_$][\w$]*)\s*(?:<[^>()]*>)?\s*\("
)
NOT_NAMES = {
    "if", "for", "while", "switch", "catch", "return", "else", "do", "try", "new", "throw", "await",
    "typeof", "sizeof", "with", "foreach", "using", "lock", "fixed", "when", "match", "select", "defer",
    "func", "case", "elif", "function", "super", "this", "yield", "delete", "void", "in", "of", "assert",
}


QUOTE_STRINGS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".php", ".dart"}
CHAR_LITERAL = re.compile(r"'(?:\\u\{[0-9A-Fa-f]+\}|\\[^\n]{1,9}|[^\\'\n])'")


def strip_code(text: str, suffix: str = ".js") -> tuple[str, str]:
    """Blank comments (first result) and also string contents (second), keeping offsets and newlines.
    A heuristic lexer for C-family syntax: quotes close on the same line, templates may span lines.
    Outside JavaScript-like languages a single quote starts only a short character literal,
    so Rust lifetimes such as 'a do not hide code."""
    keep, bare = list(text), list(text)
    i, size = 0, len(text)
    while i < size:
        two = text[i:i + 2]
        if two in ("//", "/*"):
            end = text.find("\n", i) if two == "//" else text.find("*/", i + 2)
            end = size if end < 0 else (end if two == "//" else end + 2)
            for j in range(i, end):
                if text[j] != "\n":
                    keep[j] = bare[j] = " "
            i = end
            continue
        char = text[i]
        if char == "'" and suffix not in QUOTE_STRINGS:
            literal = CHAR_LITERAL.match(text, i)
            for k in range(i + 1, literal.end() - 1 if literal else i + 1):
                bare[k] = " "
            i = literal.end() if literal else i + 1
            continue
        if char in "\"'`" and (char != "`" or suffix in QUOTE_STRINGS):
            j = i + 1
            while j < size and text[j] != char and (char == "`" or text[j] != "\n"):
                j += 2 if text[j] == "\\" else 1
            if j >= size or text[j] != char:
                i += 1
                continue
            for k in range(i + 1, j):
                if text[k] != "\n":
                    bare[k] = " "
            i = j + 1
            continue
        i += 1
    return "".join(keep), "".join(bare)


def brace_symbols(text: str, suffix: str = ".js") -> list[tuple[str, int, int, str]]:
    """Declarations in C-family files with qualified names, line spans, and comment-free digests.
    A declaration ends at its matched body brace, or for keyword forms at a top-level ';'."""
    kept, bare = strip_code(text, suffix)
    closes, stack = {}, []
    for index, char in enumerate(bare):
        if char == "{":
            stack.append(index)
        elif char == "}" and stack:
            closes[stack.pop()] = index
    line_starts = [0] + [m.end() for m in re.finditer("\n", bare)]
    kept_lines = kept.split("\n")
    found = []
    for number, start in enumerate(line_starts, 1):
        end_of_line = bare.find("\n", start)
        line = bare[start:end_of_line if end_of_line >= 0 else len(bare)]
        keyword = KEYWORD_DECLARATION.search(line)
        method = None if keyword else METHOD_DECLARATION.match(line)
        name = next(filter(None, keyword.groups()), None) if keyword else (method[1] if method else None)
        if not name or (method and NOT_NAMES & set(re.findall(r"\w+", method[0]))):
            continue
        depth, position, last, closed = 0, start + (keyword or method).start(), None, False
        limit = min(len(bare), start + 4000)
        while position < limit:
            char = bare[position]
            if char in "([":
                depth += 1
            elif char in ")]":
                depth -= 1
                closed = closed or depth == 0
                if depth < 0:
                    break
            elif char == "{" and depth == 0:
                close = closes.get(position)
                if close is not None:
                    last = bisect.bisect_right(line_starts, close)
                break
            elif depth == 0 and (char == ";" or (method and closed and char == "=")):
                if keyword:
                    last = bisect.bisect_right(line_starts, position)
                break
            position += 1
        if last:
            body = " ".join(" ".join(kept_lines[number - 1:last]).split())
            found.append([name, number, last, short_hash(body)])
    found.sort(key=lambda s: (s[1], -s[2]))
    enclosing = []
    for symbol in found:
        while enclosing and enclosing[-1][2] < symbol[2]:
            enclosing.pop()
        qualified = ".".join([e[0] for e in enclosing] + [symbol[0]])
        enclosing.append(list(symbol))
        symbol[0] = qualified
    return [tuple(symbol) for symbol in found]


SYMBOL_CACHE: dict[tuple[str, str], list | None] = {}


def code_symbols(path: str, text: str) -> list[tuple[str, int, int, str]] | None:
    """(qualified name, first line, last line, digest) for supported languages, else None."""
    suffix = PurePosixPath(path).suffix.lower()
    if suffix != ".py" and suffix not in BRACE_LANGUAGES:
        return None
    key = (suffix, hashlib.sha1(text.encode("utf-8", "surrogateescape")).hexdigest())
    if key not in SYMBOL_CACHE:
        if len(SYMBOL_CACHE) > 256:
            SYMBOL_CACHE.clear()
        try:
            SYMBOL_CACHE[key] = ([(name, first, last, short_hash(canonical(node)))
                                  for name, first, last, node in python_symbols(text)]
                                 if suffix == ".py" else brace_symbols(text, suffix))
        except (SyntaxError, ValueError, RecursionError):
            SYMBOL_CACHE[key] = None
    return SYMBOL_CACHE[key]


def code_lines(path: str, text: str) -> list[tuple[int, str]]:
    """Numbered non-blank code lines with comments removed and spaces collapsed."""
    suffix = PurePosixPath(path).suffix.lower()
    source = strip_code(text, suffix)[0] if suffix in BRACE_LANGUAGES else text
    result = []
    for number, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped and not (suffix == ".py" and stripped.startswith("#")):
            result.append((number, " ".join(stripped.split())))
    return result


HASH_COMMENT_SUFFIXES = {".py", ".yaml", ".yml", ".toml", ".sh", ".bash", ".zsh", ".ini", ".cfg", ".conf", ".env",
                         ".tf", ".rb", ".pl", ".mk", ".properties"}
HASH_COMMENT_NAMES = {"dockerfile", "makefile", ".gitignore", ".dockerignore", ".env"}


CONTENT_CACHE: dict[tuple[str, str], list[tuple[int, str, int]]] = {}


def without_hash_comments(text: str, python: bool) -> list[str]:
    """Lines with `#` comments removed. Python uses its tokenizer; other files cut a
    comment only where no quote comes before it, so a `#` inside a string stays."""
    lines = text.splitlines()
    if python:
        try:
            for token in tokenize.generate_tokens(io.StringIO(text).readline):
                if token.type == tokenize.COMMENT and token.start[0] <= len(lines):
                    row, column = token.start
                    lines[row - 1] = lines[row - 1][:column]
            return lines
        except (tokenize.TokenError, SyntaxError, ValueError):
            lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            lines[index] = ""
            continue
        quote = ""
        for position, char in enumerate(line):
            if quote:
                quote = "" if char == quote and line[position - 1] != "\\" else quote
            elif char in "\"'`":
                quote = char
            elif char == "#" and position and line[position - 1].isspace():
                lines[index] = line[:position]
                break
    return lines


def content_lines(path: str, text: str) -> list[tuple[int, str, int]]:
    """Numbered content lines for any file: (line, text with spaces collapsed, indent).

    Blank lines and comments are left out, so they never count as a change. Indent is kept
    where it can carry meaning (Python, YAML, plain text) and is zero in brace languages."""
    name = PurePosixPath(path)
    suffix = name.suffix.lower()
    key = (suffix or name.name.lower(), hashlib.sha1(text.encode("utf-8", "surrogateescape")).hexdigest())
    if key in CONTENT_CACHE:
        return CONTENT_CACHE[key]
    brace = suffix in BRACE_LANGUAGES
    if brace:
        source = strip_code(text, suffix)[0].splitlines()
    elif suffix in HASH_COMMENT_SUFFIXES or name.name.lower() in HASH_COMMENT_NAMES:
        source = without_hash_comments(text, suffix == ".py")
    else:
        source = text.splitlines()
    result = []
    for number, line in enumerate(source, 1):
        stripped = line.strip()
        if not stripped:
            continue
        wide = line.expandtabs(4)
        result.append((number, " ".join(stripped.split()), 0 if brace else len(wide) - len(wide.lstrip())))
    if len(CONTENT_CACHE) > 256:
        CONTENT_CACHE.clear()
    CONTENT_CACHE[key] = result
    return result


def span_digest(lines) -> str:
    """Hash of cited lines. Three-part lines also hash indent relative to the shallowest line,
    so a block that moves as a whole still matches and a re-indented statement does not."""
    if lines and len(lines[0]) == 3:
        base = min(indent for _, _, indent in lines)
        return short_hash("\n".join(f"{indent - base}:{code}" for _, code, indent in lines))
    return short_hash("\n".join(code for _, code in lines))


def span_lines(path: str, text: str, record: dict):
    """Lines in the form the record was fingerprinted with. Kind 1 is the form before 0.5."""
    return content_lines(path, text) if record.get("spanKind") == 2 else code_lines(path, text)


def outline(path: str, text: str) -> list[str] | None:
    """Short hashes of a code file's declared names: top-level symbols and constants, plus
    Python class members. Editing a body does not change them."""
    names = declared_names(path, text)
    return None if names is None else sorted({short_hash(name)[:8] for name in names})


def declared_names(path: str, text: str) -> set[str] | None:
    symbols = code_symbols(path, text)
    if symbols is None:
        return None
    python = path.lower().endswith(".py")
    declared = {s[0] for s in symbols if s[0].count(".") <= (1 if python else 0)}
    if python:
        for node in ast.parse(text).body:
            targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
            declared.update(t.id for t in targets if isinstance(t, ast.Name))
    return declared


def canonical(node) -> str:
    """Version-stable syntax-tree text. ast.dump changes across Python releases, and new
    releases add optional fields, so empty fields and positions are left out."""
    if isinstance(node, ast.AST):
        fields = [f"{name}={canonical(value)}" for name, value in ast.iter_fields(node)
                  if value is not None and value != []]
        return f"{type(node).__name__}({','.join(fields)})"
    if isinstance(node, list):
        return "[" + ",".join(canonical(item) for item in node) + "]"
    return repr(node)


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
    """Record what a cited line range means: a symbol's syntax tree, and the range's content lines."""
    record = {"path": path, "lines": [first, last]}
    text = read_source(root / path)
    if text is None:
        return record
    lines = text.splitlines()
    if last > len(lines):
        return record
    cited = [line for line in content_lines(path, text) if first <= line[0] <= last]
    own = {"span": span_digest(cited), "spanLines": len(cited), "spanKind": 2,
           "spanPad": [cited[0][0] - first, last - cited[-1][0]]} if cited else {}
    # Blank and comment lines at either end do not decide which symbol the range belongs to.
    low, high = (cited[0][0], cited[-1][0]) if cited else (first, last)
    spans = [s for s in code_symbols(path, text) or [] if s[1] <= low and s[2] >= high]
    if spans:
        name, start, end, digest = min(spans, key=lambda s: s[2] - s[1])
        record.update(symbol=name, symbolLines=[start, end], digest=digest)
        if (first, last) != (start, end):
            # A range that is not exactly the symbol also records its own content lines, so an
            # edit elsewhere in the same function does not flag this citation.
            record.update(own)
        return record
    # No single function or class holds the range: module-level code, several functions, or a
    # file without symbol support. Its content lines are the fingerprint, wherever they move.
    record.update(own or {"digest": text_digest(lines[first - 1:last])})
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
        symbols = code_symbols(path, text)
        if symbols is None:
            return dict(base, change="evidence-changed")
        match = [s for s in symbols if s[0] == record["symbol"]]
        if not match:
            old_start, old_end = record["symbolLines"]
            depth = record["symbol"].count(".")
            near = [s for s in symbols if s[0].count(".") == depth and abs(s[1] - old_start) <= 3
                    and abs((s[2] - s[1]) - (old_end - old_start)) <= 2]
            hint = {"renamedTo": near[0][0]} if len(near) == 1 else {}
            return dict(base, change="symbol-removed", **hint)
        # Same-named symbols (overloads, repeated test blocks): prefer an unchanged one, then the nearest.
        _, start, end, digest = min(match, key=lambda s: (s[3] != record.get("digest"), abs(s[1] - record["symbolLines"][0])))
        old_start, old_end = record["symbolLines"]
        shift = start - old_start
        if record.get("span"):
            # A range inside a symbol follows its own code lines, which can move inside
            # the symbol even when the symbol's fingerprint is unchanged (a new comment).
            found = find_span(span_lines(path, text, record), start, end, record, first + shift)
            if found == [first, last]:
                return None
            if found:
                return dict(base, change="evidence-moved", newLines=found)
            expected = [first + shift, last + shift]
        elif [first, last] == [old_start, old_end]:
            expected = [start, end]
        else:
            expected = [first + shift, min(last + shift + (end - start) - (old_end - old_start), end)]
        if digest != record.get("digest"):
            moved = {"newLines": expected} if expected != [first, last] else {}
            return dict(base, change="evidence-changed", **moved)
        if expected != [first, last]:
            return dict(base, change="evidence-moved", newLines=expected)
        return None
    if record.get("span"):
        found = find_span(span_lines(path, text, record), 1, sys.maxsize, record, first)
        if found == [first, last]:
            return None
        return dict(base, change="evidence-moved", newLines=found) if found else dict(base, change="evidence-changed")
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


def find_span(lines: list[tuple[int, str]], start: int, end: int, record: dict, expected: int) -> list[int] | None:
    """New lines of a cited range inside a changed symbol, nearest to where it was expected."""
    inside = [line for line in lines if start <= line[0] <= end]
    size = record.get("spanLines") or 0
    hits = [inside[i:i + size] for i in range(len(inside) - size + 1)
            if size and span_digest(inside[i:i + size]) == record["span"]]
    if not hits:
        return None
    lead, trail = record.get("spanPad") or [0, 0]
    best = min(hits, key=lambda run: abs(run[0][0] - lead - expected))
    # Keep blank or comment lines that the citation started or ended with.
    return [best[0][0] - lead, best[-1][0] + trail]


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


def project_files(root: Path, docs: Path, pages=()) -> dict[str, str]:
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
    skip = {".archlens.json"} | set(pages)
    return {
        name: sha[:10] for name, sha in files.items()
        if not name.startswith(docs_prefix) and name not in skip and "\n" not in name
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
            # A link to another document is a cross-reference, not code evidence.
            return "review" if PurePosixPath(path).suffix.lower() in DOC_SUFFIXES else "stale"
        if path in anchored and has_anchor_state:
            return "review"
        if path in anchored or not cited:
            return "stale"
        return "review"

    outlines = record.get("outlines") or {}
    changes = []
    for anchor in record.get("anchors") or []:
        # An identical file cannot hold a changed citation: skip the parse. This is most of
        # the work on a real repository, where nearly every cited file is untouched.
        if anchor["path"] in old and current.get(anchor["path"]) == old[anchor["path"]]:
            continue
        change = check_anchor(root, anchor)
        if change:
            changes.append(dict(change, severity="stale"))
    for path in sorted(current.keys() & old.keys()):
        if current[path] != old[path]:
            level = severity(path)
            if level == "stale" and path in outlines:
                # A whole-file link to code goes stale when a declared name the page may
                # mention is removed or renamed. Added names and body edits need only a review.
                text = read_source(root / path)
                now = outline(path, text) if text is not None else None
                recorded = outlines[path]
                if isinstance(recorded, str):
                    # State written before per-name outlines: one hash of all names.
                    names = declared_names(path, text) if text is not None else None
                    same = names is not None and short_hash("\n".join(sorted(names))) == recorded
                else:
                    same = now is not None and set(recorded) <= set(now)
                if same:
                    level = "review"
                else:
                    changes.append({"path": path, "change": "outline-changed", "severity": "stale"})
                    continue
            changes.append({"path": path, "change": "modified", "severity": level})
    for path in sorted(current.keys() - old.keys()):
        changes.append({"path": path, "change": "added", "severity": severity(path)})
    for path in sorted(old.keys() - current.keys()):
        changes.append({"path": path, "change": "removed",
                        "severity": "stale" if path in anchored or coverage.whole_file_evidence(page_id, path) else severity(path)})
    return changes


def freshness(root: Path, config: dict) -> dict:
    """Compare each page's covered files and cited evidence with its last sync."""
    docs, pages = load_map(root, config)
    page_paths = {page_file(root, page) for page in pages}
    files = project_files(root, docs, page_paths)
    coverage = Coverage(root, docs, pages)
    state = load_state(docs)
    ordered = SortedPaths(files)
    results = []
    for page in pages:
        current = {path: files[path] for path in coverage.files(page["id"], ordered)}
        record = state["pages"].get(page["id"])
        entry = {"page": page_file(root, page), "id": page["id"], "kind": page["kind"]}
        if not isinstance(record, dict) or not isinstance(record.get("files"), dict):
            entry.update(state="unsynced", changed=[], coveredFiles=len(current))
        else:
            # A document mapped as a page since the last sync is no longer evidence for others.
            record = dict(record, files={k: v for k, v in record["files"].items() if k not in page_paths})
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


def sync_pages(root: Path, config: dict, ids: list[str], every: bool, fresh: bool = False) -> dict:
    """Record the current content of covered files and cited anchors for reviewed pages."""
    docs, pages = load_map(root, config)
    known = {page["id"] for page in pages}
    unknown = sorted(set(ids) - known)
    if unknown:
        raise ArchlensError(f"Unknown page IDs: {', '.join(unknown)}")
    if not every and not ids and not fresh:
        raise ArchlensError("Name pages with --page ID (repeatable), or use --all or --fresh")
    selected = known if every else set(ids)
    if fresh:
        # A fresh page has no change to review, so recording it again approves nothing new.
        # It only rewrites the page's fingerprints in the current format.
        waiting = {entry["id"] for entry in freshness(root, config)["needsSync"]}
        selected |= known - waiting
    files = project_files(root, docs, [page_file(root, page) for page in pages])
    coverage = Coverage(root, docs, pages)
    state = load_state(docs)
    state["pages"] = {key: value for key, value in state["pages"].items() if key in known}
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    commit = head_commit(root) if in_git(root) else None
    ordered = SortedPaths(files)
    for page in pages:
        if page["id"] in selected:
            links, anchors = coverage.evidence[page["id"]]
            entry = {
                "files": {path: files[path] for path in coverage.files(page["id"], ordered)},
                "anchors": [fingerprint_anchor(root, *anchor) for anchor in anchors],
                "syncedAt": stamp, "syncedCommit": commit,
            }
            shapes = {}
            for link in links:
                text = None if link.endswith("/") or link not in files else read_source(root / link)
                shape = outline(link, text) if text is not None else None
                if shape:
                    shapes[link] = shape
            if shapes:
                entry["outlines"] = shapes
            state["pages"][page["id"]] = entry
    save_state(docs, state)
    report = {"command": "sync", "root": str(root), "synced": sorted(selected), "stateFile": (docs / STATE_FILE).relative_to(root).as_posix()}
    if config.get("contextFile"):
        report["contextFile"] = write_context(root, config, contained(root, config["contextFile"], "contextFile"))
    return report


def git_renames(root: Path, commits) -> dict[str, str]:
    """Old to new paths that Git pairs as renames since the given commits and in the working tree."""
    if not in_git(root):
        return {}
    result: dict[str, str] = {}

    def collect(*args):
        try:
            out = git(root, "diff", "--no-ext-diff", "-M", "--name-status", "-z", *args, "--")
        except ArchlensError:
            return
        parts = [part.decode("utf-8", "surrogateescape") for part in out.split(b"\0")]
        i = 0
        while i < len(parts):
            code = parts[i]
            if code[:1] in {"R", "C"} and i + 2 < len(parts):
                if code[:1] == "R":
                    result[parts[i + 1]] = parts[i + 2]
                i += 3
            else:
                i += 2 if code else 1

    for commit in sorted(c for c in commits if c):
        collect(commit, "HEAD")
    collect("HEAD")
    for old in list(result):
        new, seen = result[old], {old}
        while new in result and new not in seen:
            seen.add(new)
            new = result[new]
        result[old] = new
    return result


def link_target(root: Path, page_path: Path, path: str) -> str:
    return Path(os.path.relpath(root / path, page_path.parent)).as_posix()


def fix_anchors(root: Path, config: dict, ids: list[str] | None = None, status: dict | None = None) -> dict:
    """Rewrite links whose cited file was renamed, and line links whose cited code moved
    but did not change. No model needed."""
    docs, pages = load_map(root, config)
    status = status or freshness(root, config)
    state = load_state(docs)
    by_id = {page["id"]: page for page in pages}
    fixed = []
    selected = [e for e in status["needsSync"] if not ids or e["id"] in ids]
    removed = [e for e in selected if any(c["change"] in {"removed", "evidence-removed"} for c in e["changed"])]
    renames = git_renames(root, {(state["pages"].get(e["id"]) or {}).get("syncedCommit") for e in removed}) if removed else {}
    for entry in removed:
        record = state["pages"].get(entry["id"])
        moves = sorted({c["path"] for c in entry["changed"]
                        if c["change"] in {"removed", "evidence-removed"} and c["path"] in renames})
        if not moves or not isinstance(record, dict):
            continue
        page_path = by_id[entry["id"]]["_file"]
        text = page_path.read_text(encoding="utf-8-sig")
        for old in moves:
            new = renames[old]
            pattern = re.escape(link_target(root, page_path, old)) + r"(?=[#)>\s]|$)"
            text, count = re.subn(pattern, lambda _: link_target(root, page_path, new), text, flags=re.M)
            for anchor in record.get("anchors") or []:
                if anchor["path"] == old:
                    anchor["path"] = new
            for key in ("files", "outlines"):
                if old in (record.get(key) or {}):
                    record[key][new] = record[key].pop(old)
            if count:
                fixed.append({"page": entry["page"], "id": entry["id"], "path": old, "renamedTo": new})
        page_path.write_text(text, encoding="utf-8")
    if fixed:
        save_state(docs, state)
        # Exact-path coverage entries follow the rename too; patterns with wildcards stay as written.
        map_path = docs / "map.json"
        raw = map_path.read_text(encoding="utf-8-sig")
        updated = raw
        for item in fixed:
            updated = updated.replace(json.dumps(item["path"]), json.dumps(item["renamedTo"]))
        if updated != raw:
            map_path.write_text(updated, encoding="utf-8")
        status = freshness(root, config)
        state = load_state(docs)
    for entry in status["needsSync"]:
        moves = [c for c in entry["changed"] if c["change"] == "evidence-moved"]
        record = state["pages"].get(entry["id"])
        if not moves or not isinstance(record, dict) or (ids and entry["id"] not in ids):
            continue
        page_path = by_id[entry["id"]]["_file"]
        text = page_path.read_text(encoding="utf-8-sig")
        for move in moves:
            target = link_target(root, page_path, move["path"])
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


def cite(root: Path, config: dict, file: str, names: list[str], page: str | None) -> dict:
    """Link-ready line ranges for symbols in a source file, so pages cite exact evidence."""
    relative = relative_path(file, "file")
    path = contained(root, relative, "file")
    text = read_source(path) if path.is_file() else None
    if text is None:
        raise ArchlensError(f"Not a readable file: {relative}")
    symbols = code_symbols(relative, text)
    if symbols is None:
        raise ArchlensError(f"No symbol support for {relative}; cite a line range such as {relative}#L10-L20")
    base = relative
    if page:
        origin = contained(root, relative_path(page, "--from"), "--from")
        base = Path(os.path.relpath(path, origin.parent)).as_posix()
    if names:
        chosen, missing = [], []
        for name in names:
            found = [s for s in symbols if s[0] == name] or [s for s in symbols if s[0].rsplit(".", 1)[-1] == name]
            chosen.extend(found) if found else missing.append(name)
    else:
        python = relative.lower().endswith(".py")
        chosen, missing = [s for s in symbols if s[0].count(".") <= (1 if python else 0)], []
    entries = [{"symbol": name, "lines": [first, last], "link": f"{base}#L{first}-L{last}"}
               for name, first, last, _ in chosen]
    return {"command": "cite", "root": str(root), "file": relative, "symbols": entries, "missing": missing}


def page_brief(path: Path) -> tuple[str, str]:
    """A page's title and first explanatory sentence."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return path.stem, ""
    prose, _, _ = markdown_sections(text)
    title, summary = "", ""
    # Prefer a "Summary" section: a scope paragraph ("This page traces...") says less.
    marker = next((i for i, (_, line) in enumerate(prose) if re.match(r"^##\s+Summary\s*$", line.strip(), re.I)), None)
    if marker is not None:
        title = next((m[1].strip() for _, line in prose if (m := re.match(r"^#\s+(.+)$", line.strip()))), "")
        prose = prose[marker + 1:]
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
    briefs = {p["id"]: page_brief(p["_file"]) for p in ordered}
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
        # Worth its bytes only where pages are many: a small handbook is cheap to read whole.
        if budget >= 1500 and len(pages) >= 8:
            intro += (f'To read one section and not a whole page, run `python3 "{Path(__file__).resolve()}" query '
                      "--root . <words>` (or `--file <path>`, `--page <page>`). ")
    else:
        intro = (f"Pages live in `{doc_rel}/` ({len(pages)} pages). " + guidance
                 + "Freshness changes between commits: run the Archlens `status` check before relying on a page. "
                 + "Before you commit code, update the pages it marks stale and commit them together. ")
    header = ["## Architecture handbook (Archlens)", intro + "After an architectural change, update the affected pages.", ""]

    def line(page, detail=(False, False)):
        show_summary, show_covers = detail
        title, summary = briefs[page["id"]]
        text = f"- `{page['path']}` {title}"
        if show_summary and summary and summary.lower() != title.lower():
            text += f": {summary}"
        # An index or glossary covers the whole project; its patterns do not route a reader.
        if show_covers and page["covers"] and page["kind"] not in {"index", "glossary"}:
            shown = ", ".join(page["covers"][:2]) + (f" +{len(page['covers']) - 2}" if len(page["covers"]) > 2 else "")
            text += f" [covers {shown}]"
        entry = states.get(page["id"]) if live else None
        if entry and entry["state"] == "stale":
            count = sum(c["severity"] == "stale" for c in entry["changed"])
            text += f" STALE: {count} cited change{'s' if count != 1 else ''}"
        return text

    def group_line(group):
        _, folder, members = group
        stems, used = [], 0
        for member in members:
            stem = PurePosixPath(member["path"]).stem
            if used + len(stem) > 420:
                break
            stems.append(stem)
            used += len(stem) + 2
        more = f" +{len(members) - len(stems)}" if len(stems) < len(members) else ""
        return f"- `{folder}/` {len(members)} decision records: {', '.join(stems)}{more}"

    def text_of(items, details):
        return "\n".join(header + [group_line(item) if isinstance(item, tuple) else line(item, details[item["id"]])
                                   for item in items])

    def fill(items):
        """Start from the shortest line per page. Then add summaries, then coverage, in reading
        order while the budget allows: one long page does not cost every page its detail,
        and a summary orients an agent better than a list of paths."""
        details = {page["id"]: (False, False) for page in ordered}
        if len(text_of(items, details).encode("utf-8")) > budget:
            return None, 0
        for part in (0, 1):
            for item in items:
                if isinstance(item, tuple) or (part == 0 and item["kind"] == "decision"):
                    continue
                previous = details[item["id"]]
                details[item["id"]] = (True, previous[1]) if part == 0 else (previous[0], True)
                if len(text_of(items, details).encode("utf-8")) > budget:
                    details[item["id"]] = previous
        missed = sum(1 for item in items if not isinstance(item, tuple) and item["kind"] != "decision"
                     and briefs[item["id"]][1] and not details[item["id"]][0])
        return text_of(items, details) + "\n", missed

    full, missed = fill(ordered)
    if full is not None and not missed:
        return full
    # Summaries of working pages matter more than decision titles. When they do not all fit,
    # list each folder of four or more decision records on one line by file name.
    folders: dict[str, list[dict]] = {}
    for page in ordered:
        entry = states.get(page["id"]) if live else None
        if page["kind"] == "decision" and not (entry and entry["state"] == "stale"):
            folders.setdefault(PurePosixPath(page["path"]).parent.as_posix(), []).append(page)
    grouped, seen = [], set()
    for page in ordered:
        folder = PurePosixPath(page["path"]).parent.as_posix()
        members = folders.get(folder, [])
        if page["kind"] == "decision" and page in members and len(members) >= 4:
            if folder not in seen:
                seen.add(folder)
                grouped.append(("group", folder, members))
        else:
            grouped.append(page)
    if seen:
        compact, compact_missed = fill(grouped)
        if compact is not None and (full is None or compact_missed < missed):
            return compact
    if full is not None:
        return full
    kept = []
    for page in ordered:
        candidate = "\n".join(header + kept + [line(page), f"- +{len(ordered)} more pages in `{doc_rel}/map.json`"])
        if len(candidate.encode("utf-8")) > budget:
            break
        kept.append(line(page))
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
    page_paths = {page_file(root, page) for page in pages}
    source_changes = [path for path in changed if not path.startswith(doc_prefix)
                      and path != ".archlens.json" and path not in page_paths]
    coverage = Coverage(root, docs, pages)
    covered = set()
    candidates = []
    for page in pages:
        matches = coverage.files(page["id"], source_changes)
        if matches:
            covered.update(matches)
            candidates.append({
                "page": page_file(root, page), "id": page["id"], "changedSources": matches,
                "pageAlsoChanged": page_file(root, page) in changed,
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


STOP_WORDS = frozenset(
    "a an and are as at be by does do for from how in is it its of on or that the this to was what when where "
    "which who why will with".split())


def search_tokens(text: str) -> list[str]:
    """Lowercase search words. Identifiers also yield their parts: `RagService` -> rag, service."""
    found = []
    for raw in re.findall(r"[A-Za-z0-9_]+", text):
        parts = [part for part in re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", raw).replace("_", " ").split() if part]
        words = [part.lower() for part in parts]
        if len(words) > 1:
            words.append("".join(words))
        for word in words:
            if word in STOP_WORDS:
                continue
            for suffix, keep in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
                if word.endswith(suffix) and len(word) - len(suffix) >= 4 and not word.endswith("ss"):
                    word = word[: len(word) - len(suffix)] + keep
                    break
            found.append(word)
    return found


def resolve_page(root: Path, pages: list[dict], name: str) -> dict:
    """Find one mapped page by ID, map path, project path, or a unique file name."""
    wanted = name.replace("\\", "/").strip()
    for key in (lambda p: p["id"].lower() == wanted.lower(), lambda p: p["path"] == wanted,
                lambda p: page_file(root, p) == wanted.lstrip("./"),
                lambda p: PurePosixPath(page_file(root, p)).name == wanted or PurePosixPath(page_file(root, p)).stem == wanted):
        matches = [page for page in pages if key(page)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ArchlensError(f"Several pages match '{name}': {', '.join(page_file(root, p) for p in matches)}")
    raise ArchlensError(f"No mapped page matches '{name}'. Use a page ID or path from map.json.")


def section_record(root: Path, page: dict, section: dict, text_lines: list[str]) -> dict:
    first, last = section["lines"]
    while last > first and not text_lines[last - 1].strip():
        last -= 1
    body = "\n".join(text_lines[first - 1:last])
    record = {
        "page": page_file(root, page), "id": page["id"], "lines": [first, last],
        "heading": " > ".join([*section["trail"][1:], section["heading"]] if section["level"] > 1 else [section["heading"] or "(top)"]),
        "bytes": len(body.encode("utf-8")),
    }
    if section["diagrams"]:
        record["diagrams"] = [d["type"] for d in section["diagrams"]]
    return record


def citing_sections(root: Path, docs: Path, page: dict, relative: str) -> list[dict]:
    """Sections of a page that link to a project file or to a folder that contains it."""
    try:
        text = page["_file"].read_text(encoding="utf-8-sig")
    except OSError:
        return []
    lines = text.splitlines()
    prose, _, _ = markdown_sections(text)
    found = []
    for section in page_sections(text):
        first, last = section["lines"]
        ranges = set()
        cites = False
        for number, line in prose:
            if not first <= number <= last:
                continue
            for target in local_targets(line):
                location, fragment, problem = resolve_link(root, page["_file"], target)
                if problem or location is None or location.is_relative_to(docs):
                    continue
                link = location.relative_to(root).as_posix()
                if link == relative or (location.is_dir() and relative.startswith(link + "/")):
                    cites = True
                    if re.fullmatch(r"L\d+(?:-L\d+)?", fragment or ""):
                        ranges.add(fragment)
        if cites:
            record = section_record(root, page, section, lines)
            record["cites"] = sorted(ranges, key=lambda value: int(re.match(r"L(\d+)", value)[1]))
            found.append(record)
    return found


def query_handbook(root: Path, config: dict, terms: list[str], page_name: str | None = None, file: str | None = None,
                   step: int | None = None, row: str | None = None, diagram: int | None = None, limit: int = 5) -> dict:
    """Find the smallest part of the handbook that answers a need, without a model.

    Returns sections with line ranges, so the reader opens a few lines and not a whole page."""
    docs, pages = load_map(root, config)
    report = {"command": "query", "root": str(root), "mode": "search", "results": [],
              "limits": ["Word match only: no synonyms or meaning. Pages summarize; confirm in the linked source."]}
    try:
        states = {entry["id"]: entry["state"] for entry in freshness(root, config)["needsSync"]}
    except (ArchlensError, OSError):
        states = {}
    selected = [resolve_page(root, pages, page_name)] if page_name else sorted(
        pages, key=lambda p: (KIND_ORDER.index(p["kind"]), p["path"]))
    if (step is not None or row or diagram is not None) and not page_name:
        raise ArchlensError("--step, --row, and --diagram need --page")

    def mark(record: dict, page: dict) -> dict:
        if states.get(page["id"]) in {"stale", "unsynced"}:
            record["state"] = states[page["id"]]
        return record

    if file:
        target = Path(file)
        target = (target if target.is_absolute() else root / target).resolve()
        if not target.is_relative_to(root):
            raise ArchlensError(f"File is outside the project: {file}")
        relative = target.relative_to(root).as_posix()
        coverage = Coverage(root, docs, pages)
        report.update(mode="file", file=relative)
        for page in selected:
            report["results"] += [mark(record, page) for record in citing_sections(root, docs, page, relative)]
        cited = {record["id"] for record in report["results"]}
        report["coveredBy"] = [page_file(root, page) for page in selected
                               if page["id"] not in cited and coverage.matches(page["id"], relative)]
        return report

    texts = {}
    for page in selected:
        try:
            texts[page["id"]] = page["_file"].read_text(encoding="utf-8-sig")
        except OSError:
            continue

    if page_name and (step is not None or row):
        page = selected[0]
        prose = markdown_sections(texts.get(page["id"], ""))[0]
        report.update(mode="rows", page=page_file(root, page))
        for table in page_tables(prose):
            is_steps = re.match(r"(?i)^step\b", plain_text(table["header"][0])) is not None
            if step is not None and not is_steps:
                continue
            for number, cells in table["rows"]:
                first = cell_text(cells[0]) if cells else ""
                hit = step in step_numbers(cells[0]) if step is not None else row.lower() in first.lower()
                if hit:
                    report["results"].append(mark({
                        "page": page_file(root, page), "id": page["id"], "lines": [number, number],
                        "cells": {cell_text(name) or f"column {index + 1}": cell
                                  for index, (name, cell) in enumerate(zip(table["header"], cells))},
                    }, page))
        return report

    if page_name and diagram is not None:
        page = selected[0]
        text = texts.get(page["id"], "")
        lines = text.splitlines()
        found = [d for section in page_sections(text) for d in section["diagrams"]]
        if not 1 <= diagram <= len(found):
            raise ArchlensError(f"{page_file(root, page)} has {len(found)} diagram(s); --diagram {diagram} does not exist")
        first, last = found[diagram - 1]["lines"]
        source = "\n".join(lines[first - 1:last])
        tail = next((index for index in range(last, min(last + 4, len(lines))) if lines[index].strip()), None)
        if tail is not None and re.match(r"(?i)^text equivalent\b", lines[tail].strip()):
            end = tail
            while end + 1 < len(lines) and lines[end + 1].strip():
                end += 1
            source += "\n\n" + "\n".join(lines[tail:end + 1])
            last = end + 1
        report.update(mode="diagram", page=page_file(root, page))
        report["results"].append(mark({"page": page_file(root, page), "id": page["id"], "lines": [first, last],
                                       "type": found[diagram - 1]["type"], "source": source}, page))
        return report

    records = []
    for page in selected:
        text = texts.get(page["id"])
        if text is None:
            continue
        lines = text.splitlines()
        title = next((section["heading"] for section in page_sections(text) if section["level"] == 1), "")
        for section in page_sections(text):
            record = mark(section_record(root, page, section, lines), page)
            body = lines[section["lines"][0] - 1:section["lines"][1]]
            records.append((record, section, title, body))
    if page_name and not terms:
        report.update(mode="outline", page=page_file(root, selected[0]))
        for record, section, _, _ in records:
            record["level"] = section["level"]
            report["results"].append(record)
        return report
    wanted = search_tokens(" ".join(terms))
    if not wanted:
        raise ArchlensError("Give search words, or --page, or --file")
    documents = []
    for record, section, title, body in records:
        words = search_tokens("\n".join(body[1:] if section["level"] else body))
        words += search_tokens(section["heading"]) * 3 + search_tokens(" ".join(section["trail"])) + search_tokens(title)
        documents.append(words)
    average = sum(map(len, documents)) / max(1, len(documents))
    scored = []
    for (record, section, _, body), words in zip(records, documents):
        score = 0.0
        for term in set(wanted):
            count = words.count(term)
            if not count:
                continue
            containing = sum(term in other for other in documents)
            idf = math.log(1 + (len(documents) - containing + 0.5) / (containing + 0.5))
            score += idf * count * 2.2 / (count + 1.2 * (0.25 + 0.75 * len(words) / max(1.0, average)))
        if score > 0:
            best = max(body[1:] or body, key=lambda line: (len(set(search_tokens(line)) & set(wanted)), -len(line)), default="")
            snippet = re.sub(r"\s+", " ", best).strip()
            record["score"] = round(score, 2)
            record["snippet"] = snippet[:157] + "..." if len(snippet) > 160 else snippet
            scored.append(record)
    scored.sort(key=lambda r: (-r["score"], r["page"], r["lines"][0]))
    report["results"] = scored[:max(1, limit)]
    report["matches"] = len(scored)
    return report


def print_query(report: dict, budget: int = 6000):
    """Terse text for an agent: one line per section, then the detail it asked for."""
    out = []
    results = report["results"]
    for record in results:
        where = f"{record['page']}:{record['lines'][0]}-{record['lines'][1]}"
        flag = f"  {record['state'].upper()}" if record.get("state") else ""
        if report["mode"] == "rows":
            out.append(where + flag)
            out += [f"  {name}: {cell}" for name, cell in record["cells"].items()]
        elif report["mode"] == "diagram":
            out += [f"{where}  {record['type']}{flag}", record["source"]]
        else:
            indent = "  " * max(0, record.get("level", 1) - 1) if report["mode"] == "outline" else ""
            extra = f"  [{', '.join(record['diagrams'])}]" if record.get("diagrams") else ""
            extra += f"  cites {', '.join(record['cites'])}" if record.get("cites") else ""
            out.append(f"{indent}{where}  {record['heading']}  ({record['bytes']} B){extra}{flag}")
            if record.get("snippet"):
                out.append(f"    {record['snippet']}")
    if report.get("coveredBy"):
        out.append("Covered without a citation: " + ", ".join(report["coveredBy"][:6]))
    if not results and not report.get("coveredBy"):
        out.append("No matching section.")
    elif report.get("matches", 0) > len(results):
        out.append(f"+{report['matches'] - len(results)} more; raise --limit or add words.")
    text = "\n".join(out)
    if len(text.encode("utf-8")) > budget:
        text = text.encode("utf-8")[:budget].decode("utf-8", "ignore").rsplit("\n", 1)[0] + \
            "\n... truncated. Read the line ranges above for the rest."
    print(text)


def staged_paths(root: Path) -> set[str]:
    return set(names(git(root, "diff", "--cached", "--relative", "--no-ext-diff", "--no-renames", "--name-only", "-z")))


def precommit(root: Path, config: dict, stale_mode: str = "fail", style_gate: bool = False) -> dict:
    """One deterministic gate for a commit: rewrite moved links, check structure, and stop
    when the commit changes code that a page cites. No model, no network."""
    report = {"command": "precommit", "root": str(root), "fixed": [], "findings": [], "stale": [], "alreadyStale": 0}
    tracked = in_git(root)
    staged = staged_paths(root) if tracked else set()
    status = freshness(root, config)
    if config["fixAnchors"] and any(c["change"] in {"evidence-moved", "evidence-removed", "removed"}
                                    for entry in status["needsSync"] for c in entry["changed"]):
        report["fixed"] = fix_anchors(root, config, status=status)["fixed"]
        if report["fixed"]:
            status = freshness(root, config)
    checked = check_documents(root, config, style_gate)
    report["findings"] = [f for f in checked["findings"]
                          if f["severity"] == "error" or f["code"] == "style-target"]
    report["stylePassRate"] = checked["stylePassRate"]
    for entry in status["needsSync"]:
        hard = [c for c in entry["changed"] if c["severity"] == "stale"]
        if entry["state"] == "unsynced":
            caused = not staged or entry["page"] in staged
        else:
            caused = entry["state"] == "stale" and (not staged or any(c["path"] in staged for c in hard))
        if caused and stale_mode != "off":
            report["stale"].append({"page": entry["page"], "id": entry["id"], "state": entry["state"], "changed": hard[:6]})
        elif entry["state"] in {"stale", "unsynced"}:
            report["alreadyStale"] += 1
    report["staleMode"] = stale_mode
    report["stateFile"] = (contained(root, config["docsRoot"], "docsRoot") / STATE_FILE).relative_to(root).as_posix()
    report["failed"] = bool(report["fixed"] or report["findings"] or (report["stale"] and stale_mode == "fail"))
    return report


def print_precommit(report: dict):
    print(f"Archlens pre-commit: {'FAIL' if report['failed'] else 'PASS'}")
    for item in report["fixed"][:10]:
        if item.get("renamedTo"):
            print(f"FIXED {item['page']}: {item['path']} -> {item['renamedTo']}")
        else:
            print(f"FIXED {item['page']}: {item['path']}#L{item['from'][0]}-L{item['from'][1]} -> #L{item['to'][0]}-L{item['to'][1]}")
    if report["fixed"]:
        print(f"Archlens rewrote {len(report['fixed'])} moved link(s). Stage those pages and {report['stateFile']}, then commit again.")
    for finding in report["findings"][:10]:
        print(f"{finding['severity'].upper()} {finding['path']}:{finding['line']} [{finding['code']}] {finding['message']}")
    if len(report["findings"]) > 10:
        print(f"+{len(report['findings']) - 10} more; run the check command for all of them.")
    label = "STALE" if report["staleMode"] == "fail" else "WARN"
    for entry in report["stale"][:10]:
        if entry["state"] == "unsynced":
            print(f"{label} {entry['page']} [{entry['id']}] never synced")
            continue
        detail = ", ".join(
            f"{c['change']} {c['path']}" + (f"#L{c['lines'][0]}-L{c['lines'][1]}" if c.get("lines") else "")
            + (f" ({c['symbol']})" if c.get("symbol") else "") for c in entry["changed"][:3])
        print(f"{label} {entry['page']} [{entry['id']}] {detail}")
    if report["stale"]:
        ids = " ".join(f"--page {entry['id']}" for entry in report["stale"][:10])
        print("This commit changes code that these pages cite. Verify each page against the change, edit it if needed,")
        print(f"then run: archlens.py sync --root . {ids}")
        print(f"Stage the pages and {report['stateFile']}. A coding agent can run the Archlens update operation instead.")
    if report["alreadyStale"]:
        print(f"Note: {report['alreadyStale']} other page(s) were stale before this commit. They do not block it.")


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


def pointer_index(root: Path, docs: Path, pages: list[dict]) -> dict[str, tuple[list[str], list[str]]]:
    """Per page: the files and folders it links to, and the files it cites by line range.

    Reading every page costs most of a pointer's time, so the result is kept in the marker
    folder until the map or a page changes."""
    stamp = []
    for path in [docs / "map.json", *(page["_file"] for page in pages)]:
        try:
            info = path.stat()
            stamp.append(f"{path}|{info.st_mtime_ns}|{info.st_size}")
        except OSError:
            stamp.append(f"{path}|missing")
    signature = hashlib.sha256("\n".join(stamp).encode("utf-8", "surrogateescape")).hexdigest()
    name = f"index-{hashlib.sha256(str(root).encode('utf-8', 'surrogateescape')).hexdigest()[:16]}.json"
    try:
        cached = json.loads(read_marker(name) or "{}")
        if cached.get("signature") == signature and set(cached["pages"]) == {page["id"] for page in pages}:
            return {page_id: (entry[0], entry[1]) for page_id, entry in cached["pages"].items()}
    except (ValueError, KeyError, TypeError, IndexError, AttributeError):
        pass
    mapped = {page["_file"] for page in pages}
    index = {}
    for page in pages:
        links, anchors = page_evidence(root, docs, page["_file"], mapped)
        index[page["id"]] = (links, sorted({anchor[0] for anchor in anchors}))
    write_marker(name, json.dumps({"signature": signature, "pages": index}))
    return index


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
    key = session_key(root, payload)
    # Agents read and edit the same file many times. Answer a repeat before any page is opened.
    done = set(filter(None, (read_marker(f"files-{key}.txt") or "").split("\n")))
    if relative in done:
        return None
    docs, pages = load_map(root, config)
    if path.is_relative_to(docs) or any(path == page["_file"] for page in pages):
        return None
    evidence = pointer_index(root, docs, pages)
    seen = set(filter(None, (read_marker(f"pointers-{key}.txt") or "").split("\n")))

    def links_to(page):
        links, anchored = evidence[page["id"]]
        return relative in anchored or any(relative == link or (link.endswith("/") and relative.startswith(link)) for link in links)

    def covers(page):
        return any(relative.startswith(glob_prefix(pattern)) and glob_regex(pattern).fullmatch(relative)
                   for pattern in page["covers"])

    cited = [p for p in pages if links_to(p)]
    matched = cited + [p for p in pages if p not in cited and covers(p)]
    unseen = [p for p in matched if p["id"] not in seen]
    if len(unseen) <= 2 and len(done) < 2000:
        write_marker(f"files-{key}.txt", "\n".join(sorted(done | {relative})))
    fresh = unseen[:2]
    if not fresh:
        return None
    write_marker(f"pointers-{key}.txt", "\n".join(sorted(seen | {p["id"] for p in fresh})))
    def where(page):
        sections = citing_sections(root, docs, page, relative) if page in cited else []
        if not sections:
            return f"`{page_file(root, page)}` ({page_brief(page['_file'])[0]})"
        spots = ", ".join(f"{s['heading']} L{s['lines'][0]}-{s['lines'][1]}" for s in sections[:2])
        return f"`{page_file(root, page)}` ({spots}{f' +{len(sections) - 2}' if len(sections) > 2 else ''})"

    listed = " and ".join(where(p) for p in fresh)
    return {"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": f"Archlens: `{relative}` is documented in {listed}. "
                             "Read those lines for intent before larger changes; update the page if behavior changes.",
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


def session_changes(root: Path, payload: dict) -> set[str]:
    """Files changed in the working tree, staged, untracked, or committed during this session."""
    dirty = set(names(git(root, "diff", "HEAD", "--relative", "--no-ext-diff", "--no-renames", "--name-only", "-z")))
    dirty |= set(names(git(root, "ls-files", "--others", "--exclude-standard", "-z")))
    start = (read_marker(f"head-{session_key(root, payload)}.txt") or "").strip()
    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", start):
        try:
            dirty |= set(names(git(root, "diff", "--relative", "--no-ext-diff", "--no-renames", "--name-only", "-z", start, "HEAD", "--")))
        except ArchlensError:
            pass
    return dirty


def stale_from_changes(root: Path, config: dict, dirty: set[str]) -> tuple[list, list]:
    """Rewrite moved links, then list pages whose cited evidence this change set made stale."""
    status = freshness(root, config)
    fixed = []
    moved = any(c["change"] in {"evidence-moved", "evidence-removed", "removed"}
                for e in status["needsSync"] for c in e["changed"])
    if config["fixAnchors"] and moved:
        fixed = fix_anchors(root, config, status=status)["fixed"]
        if fixed:
            status = freshness(root, config)
    affected = []
    for entry in status["needsSync"]:
        paths = [c["path"] for c in entry["changed"] if c["path"] in dirty and c["severity"] == "stale"]
        if entry["state"] == "stale" and paths:
            affected.append((entry["page"], entry["id"], sorted(paths)))
    return affected, fixed


def page_list(config: dict, affected: list) -> str:
    docs_prefix = config["docsRoot"].rstrip("/") + "/"
    return ", ".join(page.removeprefix(docs_prefix) for page, _, _ in affected[:4]) + (
        f" +{len(affected) - 4}" if len(affected) > 4 else "")


def once(root: Path, payload: dict, kind: str, value) -> bool:
    """True the first time this session sees this value for this kind of notice."""
    signature = hashlib.sha256(json.dumps(value).encode()).hexdigest()
    name = f"{kind}-{session_key(root, payload)}.txt"
    if read_marker(name) == signature:
        return False
    write_marker(name, signature)
    return True


def hook_stop(root: Path, config: dict, payload: dict) -> dict | None:
    """Nudge once per new set of stale pages that this working tree changed."""
    if config["autoUpdate"] == "off" or not opted_in(root, config) or not in_git(root):
        return None
    dirty = session_changes(root, payload)
    if not dirty:
        return None
    affected, fixed = stale_from_changes(root, config, dirty)
    note = f"Archlens updated {len(fixed)} moved line link(s) in the handbook. " if fixed else ""
    if not affected or not once(root, payload, "notified", affected):
        return {"systemMessage": note.strip()} if note else None
    pages = page_list(config, affected)
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
    later = "They update when Claude commits, or run" if config["autoUpdate"] == "commit" else "Run"
    return {"systemMessage": f"{note}Archlens: {len(affected)} handbook page(s) cite code you changed ({pages}). {later} /archlens:update to refresh them."}


def hook_commit(root: Path, config: dict, payload: dict) -> dict | None:
    """Hold an agent's `git commit` once while it would leave cited pages stale, so the
    update runs once per commit and the docs land in the same commit as the code."""
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not COMMIT_COMMAND.search(command):
        return None
    if config["autoUpdate"] not in {"commit", "auto"} or not opted_in(root, config) or not in_git(root):
        return None
    dirty = session_changes(root, payload)
    if not dirty:
        return None
    affected, fixed = stale_from_changes(root, config, dirty)
    if not affected and not fixed:
        return None
    if not once(root, payload, "commit", affected or sorted({item["page"] for item in fixed})):
        return None
    if affected:
        ids = " ".join(page_id for _, page_id, _ in affected)
        reason = (
            f"Archlens: this commit would leave handbook pages stale: {page_list(config, affected)}. "
            f"Before committing, invoke the archlens:update skill with pages {ids}; it runs in an isolated task. "
            "Then stage the updated pages and the handbook's .archlens-state.json, and run the commit again. "
            "If the user said not to touch documentation, run the same commit again unchanged."
        )
    else:
        pages = sorted({item["page"] for item in fixed})
        reason = (f"Archlens rewrote moved line links in {', '.join(pages)}. "
                  "Stage those pages and the handbook's .archlens-state.json, then run the commit again.")
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason,
    }}


def run_hook(event: str, raw: str | None = None) -> int:
    """Claude Code hook entrypoint. Never fails the session and stays silent when not opted in."""
    try:
        if raw is None:
            raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
        if event == "commit-gate":
            # Runs before every Bash call: leave quickly unless the command is a commit.
            command = (payload.get("tool_input") or {}).get("command")
            if not isinstance(command, str) or "commit" not in command:
                return 0
        root = hook_root(payload)
        config, _ = load_config(root)
        if event == "commit-gate":
            result = hook_commit(root, config, payload)
            if result:
                print(json.dumps(result))
        elif event == "session-start":
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
    for name in ("config", "check", "impact", "status", "sync", "context", "fix-anchors", "cite", "query", "precommit"):
        command = commands.add_parser(name)
        command.add_argument("--root", type=Path, default=Path.cwd(), help="Project root (default: current folder)")
        output = command.add_mutually_exclusive_group()
        output.add_argument("--json", action="store_true", help="Emit the complete machine-readable report")
        output.add_argument("--summary", action="store_true", help="Emit bounded JSON (at most 6000 UTF-8 bytes)")
        if name == "check":
            command.add_argument("--strict", action="store_true", help="Also fail on warnings")
            command.add_argument("--style", action="store_true",
                                 help="Also fail when the mechanical style pass rate is below styleTarget")
        if name == "query":
            command.add_argument("terms", nargs="*", help="Words to find in handbook sections")
            command.add_argument("--page", help="Page ID or path: outline it, or limit the search to it")
            command.add_argument("--file", help="Project file: list the sections that cite it")
            command.add_argument("--step", type=int, help="With --page: step-table rows for this diagram step")
            command.add_argument("--row", help="With --page: table rows whose first cell contains this text")
            command.add_argument("--diagram", type=int, nargs="?", const=1, metavar="N",
                                 help="With --page: print diagram N (default 1) and its text equivalent")
            command.add_argument("--limit", type=int, default=5, help="Most sections to return (default 5)")
        if name == "precommit":
            command.add_argument("--stale", choices=["fail", "warn", "off"], default="fail",
                                 help="What to do when the commit changes cited code (default: fail)")
            command.add_argument("--style", action="store_true",
                                 help="Also fail when the mechanical style pass rate is below styleTarget")
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
            command.add_argument("--fresh", action="store_true",
                                 help="Record fresh pages again, to move their fingerprints to this version's format")
        if name == "cite":
            command.add_argument("file", help="Project-relative source file")
            command.add_argument("symbols", nargs="*", help="Function or class names (default: list the file's main symbols)")
            command.add_argument("--from", dest="origin", metavar="PAGE",
                                 help="Project-relative page that will contain the link; prints links relative to it")
        if name == "context":
            command.add_argument("--write", nargs="?", const="", metavar="FILE",
                                 help="Update the managed block in FILE (default: configured contextFile)")
            command.add_argument("--budget", type=int, help="Maximum digest bytes (default: contextBudget)")
    hook = commands.add_parser("hook", help="Claude Code hook entrypoint (silent unless the project opted in)")
    hook.add_argument("event", choices=["session-start", "stop", "file-pointer", "commit-gate"])
    return parser


def bounded_report(report: dict, budget: int = 6000) -> dict:
    """Keep whole records and explicit omission counts, never silently truncate JSON."""
    collection_keys = ("findings", "candidates", "uncoveredFiles", "changedFiles", "needsSync", "fresh", "fixed", "symbols",
                       "results", "stale")
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
    if report["command"] == "query":
        print_query(report)
        return
    if report["command"] == "precommit":
        print_precommit(report)
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
        style = report["style"]
        rate = f"{report['stylePassRate']:.0%}" if report["stylePassRate"] is not None else "not rated (under 20 sentences)"
        print(f"Mechanical style, handbook pages: {style['passing']} of {style['sentences']} sentences pass; {rate}; target {style['target']:.0%}.")
        for finding in report["findings"]:
            print(f"{finding['severity'].upper()} {finding['path']}:{finding['line']} [{finding['code']}] {finding['message']}")
    elif report["command"] == "status":
        counts = report["counts"]
        print(f"{counts['fresh']} fresh, {counts['stale']} stale, {counts['review']} review, {counts['unsynced']} unsynced.")
        for entry in report["needsSync"]:
            def describe(c):
                where = c["path"] + (f"#L{c['lines'][0]}-L{c['lines'][1]}" if c.get("lines") else "")
                where += f" ({c['symbol']})" if c.get("symbol") else ""
                where += f" now `{c['renamedTo']}`?" if c.get("renamedTo") else ""
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
        print(f"Fixed {len(report['fixed'])} moved link(s).")
        for item in report["fixed"]:
            if item.get("renamedTo"):
                print(f"FIXED {item['page']}: {item['path']} -> {item['renamedTo']} (file renamed)")
            else:
                print(f"FIXED {item['page']}: {item['path']}#L{item['from'][0]}-L{item['from'][1]} -> #L{item['to'][0]}-L{item['to'][1]}")
    elif report["command"] == "cite":
        for entry in report["symbols"]:
            print(f"[{entry['symbol']}]({entry['link']})")
        for name in report["missing"]:
            print(f"MISSING {name}: no such function or class in {report['file']}")
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
            report = check_documents(root, config, args.style)
            failed = any(f["severity"] == "error" or (args.strict and f["severity"] == "warning")
                         or f["code"] == "style-target" for f in report["findings"])
        elif args.command == "query":
            report = query_handbook(root, config, args.terms, args.page, args.file, args.step, args.row, args.diagram, args.limit)
        elif args.command == "precommit":
            report = precommit(root, config, args.stale, args.style)
            failed = report["failed"]
        elif args.command == "status":
            report = freshness(root, config)
            gate = {"stale", "unsynced"} | ({"review"} if args.fail_on_review else set())
            failed = (args.fail_on_stale or args.fail_on_review) and any(e["state"] in gate for e in report["needsSync"])
        elif args.command == "sync":
            report = sync_pages(root, config, args.page, args.all, args.fresh)
        elif args.command == "fix-anchors":
            report = fix_anchors(root, config, args.page or None)
        elif args.command == "cite":
            report = cite(root, config, args.file, args.symbols, args.origin)
            failed = bool(report["missing"])
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
