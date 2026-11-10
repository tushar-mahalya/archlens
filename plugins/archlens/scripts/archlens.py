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
    if not resolved.is_relative_to(root.resolve()):
        raise ArchlensError(f"{label} escapes the project: {value}")
    if lead and resolved.is_relative_to(docs):
        raise ArchlensError(f"{label}: write pages inside the handbook without '..': {value}")
    if ".git" in resolved.relative_to(root.resolve()).parts:
        raise ArchlensError(f"{label} must not point into .git: {value}")
    return normalized, resolved


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
        path, resolved = page_location(root, docs, page["path"], f"{label}.path")
        if not path.endswith(".md"):
            raise ArchlensError(f"{label}.path must end in .md")
        if path.casefold() in paths or resolved in resolved_paths:
            raise ArchlensError(f"Duplicate page path: {path}")
        paths.add(path.casefold())
        resolved_paths.add(resolved)
        page["path"] = path
        page["_file"] = resolved
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


def check_documents(root: Path, config: dict) -> dict:
    docs, pages = load_map(root, config)
    findings = []
    diagram_count = 0

    def add(severity, path, line, code, message):
        findings.append({"severity": severity, "path": path, "line": line, "code": code, "message": message})

    references = References(root, docs, [page_file(root, page) for page in pages])
    style: dict[str, dict[str, list[int]]] = {}
    mapped = {page["_file"] for page in pages}
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
        # Decision records are history: a path they name may be gone by design.
        historical = page["kind"] == "decision" and page.get("decisionStatus") != "proposed"
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
                elif location is not None:
                    near = near_symbol(root, location, fragment)
                    if near:
                        add("warning", relative, number, "anchor-offset", near)
            if not historical:
                for problem in references.problems(path, line):
                    add("warning", relative, number, "stale-reference", problem)
            if line.strip() and not line.lstrip().startswith(("#", "|", "<!--", "[")):
                plain = re.sub(r"`[^`]*`", "", line)
                hits = style.setdefault(relative, {"semicolon": [], "long-line": []})
                if ";" in plain:
                    hits["semicolon"].append(number)
                if len(re.findall(r"\b[\w'-]+\b", plain)) > 60:
                    hits["long-line"].append(number)
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
    for relative, hits in sorted(style.items()):
        lines = sorted(set(hits["semicolon"]) | set(hits["long-line"]))
        if not lines:
            continue
        parts = [f"{len(hits[key])} {label}" for key, label in (
            ("semicolon", "line(s) with semicolons"), ("long-line", "long line(s)")) if hits[key]]
        shown = ", ".join(map(str, lines[:5])) + (f" +{len(lines) - 5}" if len(lines) > 5 else "")
        findings.append({
            "severity": "info", "path": relative, "line": lines[0], "code": "style",
            "message": f"Editorial candidates: {' and '.join(parts)} (lines {shown}). Split complex sentences where it helps.",
            "lines": lines,
        })
    # Broken links and vanished references first; presentation advice last.
    rank = {"error": 0, "warning": 1, "info": 2}
    cosmetic = {"sequence-numbers", "sequence-density", "missing-title"}
    findings.sort(key=lambda f: (rank[f["severity"]], f["code"] in cosmetic, f["path"], f["line"]))
    return {
        "command": "check", "root": str(root), "pages": len(pages),
        "mermaidBlocks": diagram_count, "findings": findings,
        "stylePassRate": None,
        "limits": [
            "Mermaid rendering and semantic accuracy are not checked; only the diagram type is.",
            "Inline Markdown links, reference definitions, heading anchors, and line anchors are checked; remote URLs are not.",
            "Backticked paths, function() names, and npm scripts are checked for existence, not meaning.",
            "Style notes (info) are heuristics, not an STE score, and never fail --strict.",
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
    return page["_file"].relative_to(root.resolve()).as_posix()


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


def span_digest(lines: list[tuple[int, str]]) -> str:
    return short_hash("\n".join(code for _, code in lines))


def outline(path: str, text: str) -> str | None:
    """Digest of a code file's declared names: top-level symbols and constants, plus Python
    class members. Renaming, adding, or removing one changes it; editing a body does not."""
    symbols = code_symbols(path, text)
    if symbols is None:
        return None
    python = path.lower().endswith(".py")
    declared = {s[0] for s in symbols if s[0].count(".") <= (1 if python else 0)}
    if python:
        for node in ast.parse(text).body:
            targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
            declared.update(t.id for t in targets if isinstance(t, ast.Name))
    return short_hash("\n".join(sorted(declared)))


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
    """Record what a cited line range means: a Python symbol's AST, or the normalized text."""
    record = {"path": path, "lines": [first, last]}
    text = read_source(root / path)
    if text is None:
        return record
    spans = [s for s in code_symbols(path, text) or [] if s[1] <= first and s[2] >= last]
    if spans:
        name, start, end, digest = min(spans, key=lambda s: s[2] - s[1])
        record.update(symbol=name, symbolLines=[start, end], digest=digest)
        if (first, last) != (start, end):
            # A range inside a symbol: also record its own code lines, so an edit
            # elsewhere in the same function does not flag this citation.
            cited = [line for line in code_lines(path, text) if first <= line[0] <= last]
            if cited:
                record.update(span=span_digest(cited), spanLines=len(cited),
                              spanPad=[cited[0][0] - first, last - cited[-1][0]])
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
        symbols = code_symbols(path, text)
        if symbols is None:
            return dict(base, change="evidence-changed")
        match = [s for s in symbols if s[0] == record["symbol"]]
        if not match:
            return dict(base, change="symbol-removed")
        # Same-named symbols (overloads, repeated test blocks): prefer an unchanged one, then the nearest.
        _, start, end, digest = min(match, key=lambda s: (s[3] != record.get("digest"), abs(s[1] - record["symbolLines"][0])))
        old_start, old_end = record["symbolLines"]
        shift = start - old_start
        if record.get("span"):
            # A range inside a symbol follows its own code lines, which can move inside
            # the symbol even when the symbol's fingerprint is unchanged (a new comment).
            found = find_span(code_lines(path, text), start, end, record, first + shift)
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
        change = check_anchor(root, anchor)
        if change:
            changes.append(dict(change, severity="stale"))
    for path in sorted(current.keys() & old.keys()):
        if current[path] != old[path]:
            level = severity(path)
            if level == "stale" and path in outlines:
                # A whole-file link to code goes stale when the file's declared names change.
                # Body edits are worth a review; the cited ranges catch body changes precisely.
                text = read_source(root / path)
                if text is not None and outline(path, text) == outlines[path]:
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
        page_path = by_id[entry["id"]]["_file"]
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
        if show_covers and page["covers"]:
            shown = ", ".join(page["covers"][:2]) + (f" +{len(page['covers']) - 2}" if len(page["covers"]) > 2 else "")
            text += f" [covers {shown}]"
        entry = states.get(page["id"]) if live else None
        if entry and entry["state"] == "stale":
            count = sum(c["severity"] == "stale" for c in entry["changed"])
            text += f" STALE: {count} cited change{'s' if count != 1 else ''}"
        return text

    def fits(details):
        text = "\n".join(header + [line(page, details[page["id"]]) for page in ordered])
        return len(text.encode("utf-8")) <= budget

    # Start from the shortest line per page. Then add summaries, then coverage, in reading
    # order while the budget allows: one long page does not cost every page its detail,
    # and a summary orients an agent better than a list of paths.
    details = {page["id"]: (False, False) for page in ordered}
    if fits(details):
        for part in (0, 1):
            for page in ordered:
                if part == 0 and page["kind"] == "decision":
                    continue
                previous = details[page["id"]]
                details[page["id"]] = (True, previous[1]) if part == 0 else (previous[0], True)
                if not fits(details):
                    details[page["id"]] = previous
        return "\n".join(header + [line(page, details[page["id"]]) for page in ordered]) + "\n"
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
    if path.is_relative_to(docs) or any(path == page["_file"] for page in pages):
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
    listed = " and ".join(f"`{page_file(root, p)}` ({page_brief(p['_file'])[0]})" for p in fresh)
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
    fixed = fix_anchors(root, config)["fixed"] if config["fixAnchors"] else []
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


def run_hook(event: str) -> int:
    """Claude Code hook entrypoint. Never fails the session and stays silent when not opted in."""
    try:
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
    for name in ("config", "check", "impact", "status", "sync", "context", "fix-anchors", "cite"):
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
    collection_keys = ("findings", "candidates", "uncoveredFiles", "changedFiles", "needsSync", "fresh", "fixed", "symbols")
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
            report = check_documents(root, config)
            failed = any(f["severity"] == "error" or (args.strict and f["severity"] == "warning")
                         for f in report["findings"])
        elif args.command == "status":
            report = freshness(root, config)
            gate = {"stale", "unsynced"} | ({"review"} if args.fail_on_review else set())
            failed = (args.fail_on_stale or args.fail_on_review) and any(e["state"] in gate for e in report["needsSync"])
        elif args.command == "sync":
            report = sync_pages(root, config, args.page, args.all)
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
