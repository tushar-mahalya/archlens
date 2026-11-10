"""Mutation benchmark for drift detection. No model calls; the project is never modified.

For every line-range citation in a project's handbook, it copies the cited file to a
temporary folder, records the citation's fingerprint, applies one small edit, and asks
the checker what changed. Each edit has a known right answer:

  shift           three lines added above the file's code  -> moved by exactly 3, not changed
  comment         a comment line added inside the range     -> not changed
  format          trailing spaces and a blank line added     -> not changed
  change          a literal or operator edited in the range -> changed
  change-outside  the same edit, outside the cited symbol   -> not changed
  delete          the cited lines removed                    -> changed or removed
  inline-comment  a comment added at the end of a cited line -> not changed
  sibling         an edit in the same function, outside a cited sub-range -> not changed
  reindent        a cited Python statement moved out of its block -> changed
  rename          the cited function or class renamed        -> changed

Detection rate is the share of real changes that are flagged. False-alarm rate is the
share of harmless edits flagged as changed. Python edits are verified with the syntax
tree, so a "harmless" edit truly keeps the program and a "change" truly alters it.

With --symbols, it cites every function and class in the matching files instead, to test
the fingerprints on far more code than a handbook cites. --script runs another checker
version on the same edits, for a before and after comparison.

Usage: python tools/drift_benchmark.py [--root PROJECT] [--symbols 'src/**/*.ts'] [--script FILE]
                                       [--out FILE] [--failures N]
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins/archlens/scripts/archlens.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


archlens = load(SCRIPT, "archlens")

SWAPS = [(r"\bTrue\b", "False"), (r"\bFalse\b", "True"), (r"\btrue\b", "false"), (r"\bfalse\b", "true"),
         (r"==", "!="), (r"!=", "=="), (r"<=", "<"), (r">=", ">"), (r"\band\b", "or"), (r"\bor\b", "and"),
         (r"&&", "||"), (r"\|\|", "&&"), (r"(?<![\w.])(\d+)(?![\w.])", None)]


def language(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    return "python" if suffix == ".py" else "c-family" if suffix in archlens.BRACE_LANGUAGES else "text"


def comment_mark(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in {".py", ".toml", ".yaml", ".yml", ".sh", ".cfg", ".ini", ".conf", ""} or language(path) == "python":
        return "#"
    return "//" if language(path) == "c-family" else ""


def tree(text: str):
    try:
        return ast.dump(ast.parse(text))
    except (SyntaxError, ValueError, RecursionError):
        return None


def edit_line(line: str) -> str | None:
    """One semantic edit to a code line, or None when the line has nothing safe to edit."""
    code = line.split("#", 1)[0] if "#" in line and '"' not in line and "'" not in line else line
    if code.strip().startswith(("#", "//", "*", "/*", '"""', "'''")) or not code.strip():
        return None
    for pattern, replacement in SWAPS:
        match = re.search(pattern, code)
        if not match:
            continue
        new = str(int(match[1]) + 1) if replacement is None else replacement
        return line[:match.start()] + new + line[match.end():]
    return None


def mutate(kind: str, path: str, lines: list[str], first: int, last: int, symbol: list[int] | None) -> list[str] | None:
    """The file's lines after one edit, or None when the edit does not apply here."""
    mark = comment_mark(path)
    if kind == "shift":
        if not mark:
            return ["", "", ""] + lines
        start = 1 if lines and lines[0].startswith("#!") else 0
        return lines[:start] + [f"{mark} archlens benchmark", "", ""] + lines[start:]
    if kind == "comment":
        if not mark or last == first:
            return None
        for at in range(first, last):        # insert after line `at` (1-based), inside the range
            indent = re.match(r"\s*", lines[at])[0] if at < len(lines) else ""
            previous = lines[at - 1].rstrip()
            if language(path) == "c-family" and not previous.endswith((";", "{", "}")):
                continue
            return lines[:at] + [f"{indent}{mark} archlens benchmark"] + lines[at:]
        return None
    if kind == "format":
        changed = list(lines)
        changed[first - 1] = changed[first - 1] + "   "
        if language(path) == "text":
            return changed
        # A blank line after a statement boundary, where every supported language allows one.
        for at in range(first, last):
            if lines[at - 1].rstrip().endswith((":", ";", "{", "}", ",")) or language(path) == "python":
                return changed[:at] + [""] + changed[at:]
        return changed
    if kind in {"change", "change-outside"}:
        low, high = symbol or [first, last]
        if kind == "change":
            candidates = range(first, last + 1)
        else:
            candidates = [n for n in range(1, len(lines) + 1) if n < low - 1 or n > high + 1]
        for number in candidates:
            new = edit_line(lines[number - 1])
            if new is not None and new != lines[number - 1]:
                return lines[:number - 1] + [new] + lines[number:]
        return None
    if kind == "delete":
        return lines[:first - 1] + lines[last:]
    if kind == "inline-comment":
        if not mark:
            return None
        for number in range(first, last + 1):
            line = lines[number - 1]
            if line.strip() and not any(char in line for char in "\"'`\\") and not line.strip().startswith(mark) \
                    and (language(path) != "c-family" or line.rstrip().endswith((";", "{", "}"))):
                return lines[:number - 1] + [f"{line}  {mark} archlens benchmark"] + lines[number:]
        return None
    if kind == "sibling":
        if not symbol or (symbol[0] >= first and symbol[1] <= last):
            return None
        for number in [n for n in range(symbol[0] + 1, symbol[1] + 1) if n < first - 1 or n > last + 1]:
            new = edit_line(lines[number - 1])
            if new is not None and new != lines[number - 1]:
                return lines[:number - 1] + [new] + lines[number:]
        return None
    if kind == "reindent":
        if language(path) != "python":
            return None
        for number in range(first + 1, last + 1):
            line, above = lines[number - 1], lines[number - 2]
            depth = len(line) - len(line.lstrip())
            if line.strip() and above.strip() and depth >= 8 and depth == len(above) - len(above.lstrip()):
                return lines[:number - 1] + [line[4:]] + lines[number:]
        return None
    if kind == "rename":
        if not symbol:
            return None
        for number in range(symbol[0], min(symbol[1], symbol[0] + 12) + 1):
            match = re.match(r"^(\s*(?:export\s+)?(?:async\s+)?(?:def|class|function)\s+)(\w+)", lines[number - 1])
            if match:
                return lines[:number - 1] + [match[1] + match[2] + "Renamed" + lines[number - 1][match.end():]] + lines[number:]
        return None
    raise ValueError(kind)


EXPECT = {"shift": "moved", "comment": "kept", "format": "kept", "change": "changed",
          "change-outside": "kept", "delete": "changed", "inline-comment": "kept", "sibling": "kept",
          "reindent": "changed", "rename": "changed"}


def verdict(kind: str, change: dict | None, first: int, last: int) -> tuple[bool, str]:
    what = change["change"] if change else "unchanged"
    flagged = what in {"evidence-changed", "evidence-removed", "symbol-removed"}
    if EXPECT[kind] == "changed":
        return flagged, what
    if kind == "shift":
        return (change is not None and what == "evidence-moved" and change.get("newLines") == [first + 3, last + 3]), what
    return not flagged, what


def symbol_anchors(root: Path, patterns: list[str], per_file: int = 40) -> list[tuple[str, int, int]]:
    anchors = []
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            parts = path.relative_to(root).parts
            if not path.is_file() or any(part in archlens.WALK_EXCLUDES or part.startswith(".") for part in parts):
                continue
            relative = path.relative_to(root).as_posix()
            text = archlens.read_source(path)
            symbols = archlens.code_symbols(relative, text) if text is not None else None
            anchors += [(relative, first, last) for _, first, last, _ in (symbols or [])[:per_file] if last > first]
    return sorted(set(anchors))


def run(root: Path, failures: int = 0, patterns: list[str] | None = None) -> dict:
    root = root.resolve()
    if patterns:
        anchors = symbol_anchors(root, patterns)
    else:
        config, _ = archlens.load_config(root)
        docs, pages = archlens.load_map(root, config)
        mapped = {page["_file"] for page in pages}
        anchors = sorted({anchor for page in pages for anchor in archlens.page_evidence(root, docs, page["_file"], mapped)[1]})
    results, examples = {}, []
    with tempfile.TemporaryDirectory(prefix="archlens-drift-") as folder:
        work = Path(folder)
        for path, first, last in anchors:
            source = archlens.read_source(root / path)
            if source is None or last > len(source.splitlines()):
                continue
            target = work / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8", errors="surrogateescape")
            record = archlens.fingerprint_anchor(work, path, first, last)
            lines = source.splitlines()
            base_tree = tree(source) if language(path) == "python" else None
            for kind in EXPECT:
                changed = mutate(kind, path, lines, first, last, record.get("symbolLines"))
                if changed is None:
                    continue
                text = "\n".join(changed) + "\n"
                if base_tree is not None:
                    # Keep only edits whose effect is certain: harmless ones keep the tree, real ones alter it.
                    new_tree = tree(text)
                    harmless = EXPECT[kind] != "changed"
                    if new_tree is None or (new_tree == base_tree) != harmless:
                        if not (kind in {"change-outside", "sibling"} and new_tree is not None and new_tree != base_tree):
                            continue
                target.write_text(text, encoding="utf-8", errors="surrogateescape")
                ok, what = verdict(kind, archlens.check_anchor(work, record), first, last)
                bucket = results.setdefault((language(path), kind), [0, 0])
                bucket[0] += ok
                bucket[1] += 1
                if not ok and len(examples) < failures:
                    examples.append({"edit": kind, "anchor": f"{path}#L{first}-L{last}", "symbol": record.get("symbol"), "reported": what})
            target.write_text(source, encoding="utf-8", errors="surrogateescape")

    def total(kinds, languages=None):
        right = sum(v[0] for (lang, kind), v in results.items() if kind in kinds and (languages is None or lang in languages))
        count = sum(v[1] for (lang, kind), v in results.items() if kind in kinds and (languages is None or lang in languages))
        return right, count

    def rate(pair):
        return round(pair[0] / pair[1], 4) if pair[1] else None

    real = tuple(kind for kind, expected in EXPECT.items() if expected == "changed")
    harmless = tuple(kind for kind, expected in EXPECT.items() if expected != "changed")
    summary = {"anchors": len(anchors)}
    for name, languages in (("all", None), ("python", {"python"}), ("c-family", {"c-family"}), ("text", {"text"})):
        detected, kept = total(real, languages), total(harmless, languages)
        summary[name] = {
            "detection": rate(detected), "realEdits": detected[1],
            "falseAlarms": round(1 - rate(kept), 4) if kept[1] else None, "harmlessEdits": kept[1],
        }
    table = {f"{lang}/{kind}": {"correct": v[0], "total": v[1]} for (lang, kind), v in sorted(results.items())}
    return {
        "benchmark": "drift-mutation", "repository": root.name, "summary": summary, "byEdit": table, "failures": examples,
        "limits": ["One edit at a time, on citations that exist in this handbook.",
                   "Python edits are verified with the syntax tree. Other languages use statement-boundary heuristics.",
                   "It measures citation fingerprints, not whether a page's prose is still right."],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="Project with a handbook (default: this repository)")
    parser.add_argument("--out", type=Path, help="Write the JSON report to this file")
    parser.add_argument("--failures", type=int, default=0, help="Include up to N wrong verdicts in the report")
    parser.add_argument("--symbols", action="append", default=[], metavar="GLOB",
                        help="Cite every function and class in files that match (repeatable)")
    parser.add_argument("--script", type=Path, help="Checker to test (default: this repository's)")
    args = parser.parse_args(argv)
    if args.script:
        global archlens
        archlens = load(args.script.resolve(), "archlens_under_test")
    report = run(args.root, args.failures, args.symbols)
    report["script"] = str(args.script) if args.script else "plugins/archlens/scripts/archlens.py"
    report["citations"] = "every symbol in " + ", ".join(args.symbols) if args.symbols else "handbook"
    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{report['summary']['anchors']} citations in {report['repository']}")
    print(f"{'Language':<10}{'Real edits':>11}{'Detected':>10}{'Harmless':>10}{'False alarms':>14}")
    for name in ("all", "python", "c-family", "text"):
        row = report["summary"][name]
        if row["realEdits"] or row["harmlessEdits"]:
            detection = f"{row['detection']:.1%}" if row["detection"] is not None else "-"
            alarms = f"{row['falseAlarms']:.1%}" if row["falseAlarms"] is not None else "-"
            print(f"{name:<10}{row['realEdits']:>11}{detection:>10}{row['harmlessEdits']:>10}{alarms:>14}")
    for name, value in report["byEdit"].items():
        print(f"  {name:<26}{value['correct']:>4} / {value['total']}")
    for item in report["failures"]:
        print(f"  WRONG {item['edit']}: {item['anchor']} ({item['symbol']}) reported {item['reported']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
