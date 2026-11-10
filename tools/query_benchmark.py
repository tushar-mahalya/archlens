"""Deterministic retrieval benchmark for `archlens.py query`. No model calls.

For each benchmark question it compares three ways to load handbook context:
the top sections that `query` returns, the whole pages those sections are in,
and every mapped page. It reports bytes and key-term recall: the share of the
answer key's content words that the loaded text contains.

Key-term recall is a proxy for "the needed text was loaded". It is not answer
quality: a model can still misread loaded text. See docs/benchmarks.md.

Usage: python tools/query_benchmark.py [--top 1,3,5] [--out FILE] [--root PROJECT --questions FILE]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins/archlens/scripts/archlens.py"
QUESTIONS = ROOT / "benchmarks/questions/archlens.json"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


archlens = load(SCRIPT, "archlens")


def recall(key_terms: set[str], text: str) -> float:
    return len(key_terms & set(archlens.search_tokens(text))) / len(key_terms) if key_terms else 0.0


def run(tops: list[int], root: Path = ROOT, questions: Path = QUESTIONS) -> dict:
    root = root.resolve()
    config, _ = archlens.load_config(root)
    _, pages = archlens.load_map(root, config)
    texts = {archlens.page_file(root, page): page["_file"].read_text(encoding="utf-8") for page in pages}
    everything = "\n".join(texts.values())
    rows = []
    asked = json.loads(questions.read_text(encoding="utf-8"))
    for item in asked["questions"]:
        key_terms = set(archlens.search_tokens(" ".join(item["key"])))
        row = {"id": item["id"], "keyTerms": len(key_terms),
               "handbook": {"bytes": len(everything.encode("utf-8")), "recall": round(recall(key_terms, everything), 3)}}
        for top in tops:
            report = archlens.query_handbook(root, config, item["question"].split(), limit=top)
            sections, whole = [], {}
            for record in report["results"]:
                lines = texts[record["page"]].splitlines()
                sections.append("\n".join(lines[record["lines"][0] - 1:record["lines"][1]]))
                whole[record["page"]] = texts[record["page"]]
            # The command's own output is part of what an agent loads before it reads the sections.
            listing = sum(len(f"{r['page']}:{r['lines'][0]}-{r['lines'][1]}  {r['heading']}\n    {r['snippet']}\n".encode("utf-8"))
                          for r in report["results"])
            section_text, page_text = "\n".join(sections), "\n".join(whole.values())
            row[f"top{top}"] = {
                "sections": {"bytes": len(section_text.encode("utf-8")) + listing, "recall": round(recall(key_terms, section_text), 3)},
                "wholePages": {"bytes": len(page_text.encode("utf-8")), "recall": round(recall(key_terms, page_text), 3)},
            }
        rows.append(row)

    def mean(values):
        values = list(values)
        return round(sum(values) / len(values), 3) if values else 0.0

    summary = {"questions": len(rows), "handbook": {
        "bytes": rows[0]["handbook"]["bytes"] if rows else 0, "recall": mean(r["handbook"]["recall"] for r in rows)}}
    for top in tops:
        summary[f"top{top}"] = {
            kind: {"bytes": round(mean(r[f"top{top}"][kind]["bytes"] for r in rows)),
                   "recall": mean(r[f"top{top}"][kind]["recall"] for r in rows)}
            for kind in ("sections", "wholePages")}
    return {
        "benchmark": "query-retrieval", "repository": asked.get("repository", root.name), "pages": len(pages),
        "method": "Key-term recall of loaded text against each answer key; bytes are UTF-8, not tokens.",
        "limits": ["Proxy for loaded context, not answer quality.", "A few questions on one repository.",
                   "The question text is the query; an agent may choose better words."],
        "summary": summary, "questions": rows,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--top", default="1,3,5", help="Comma-separated result counts (default 1,3,5)")
    parser.add_argument("--out", type=Path, help="Write the JSON report to this file")
    parser.add_argument("--root", type=Path, default=ROOT, help="Project with a handbook (default: this repository)")
    parser.add_argument("--questions", type=Path, default=QUESTIONS, help="Question file with answer keys")
    args = parser.parse_args(argv)
    report = run([int(value) for value in args.top.split(",")], args.root, args.questions)
    text = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    summary = report["summary"]
    print(f"{'Load':<24}{'Bytes':>9}{'Key-term recall':>18}")
    print(f"{'Every mapped page':<24}{summary['handbook']['bytes']:>9}{summary['handbook']['recall']:>17.0%}")
    for name, value in summary.items():
        if name.startswith("top"):
            print(f"{'Whole pages, ' + name:<24}{value['wholePages']['bytes']:>9}{value['wholePages']['recall']:>17.0%}")
            print(f"{'Sections, ' + name:<24}{value['sections']['bytes']:>9}{value['sections']['recall']:>17.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
