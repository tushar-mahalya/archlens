"""A/B benchmark of answer quality and token use with real Claude Code sessions.

Conditions, all on the same snapshot of a repository:
  no-handbook  the architecture handbook folder is removed
  handbook     the handbook exists, but no plugin tells the agent about it
  archlens     the handbook plus the Archlens plugin (session map from the hook)

Each answer is graded blind by a separate model call against an answer key.
This spends real model usage. Usage:
  python tools/model_benchmark.py --questions benchmarks/questions/archlens.json --reps 2
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
from pathlib import Path
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/archlens"
CONDITIONS = ("no-handbook", "handbook", "archlens")
ANSWER_PROMPT = (
    "Answer this question about the repository in the current directory. "
    "Use the available read-only tools as needed. Reply in at most 150 words and cite file paths.\n\nQuestion: {q}"
)
JUDGE_PROMPT = """You grade an answer about a software repository. Do not use tools.
Question: {q}
Answer key (each item is one required fact):
{key}
Answer to grade:
<answer>
{a}
</answer>
Count how many key facts the answer states correctly (paraphrase is fine), and count
claims in the answer that contradict the key or are clearly false. Reply with only JSON:
{{"covered": <int>, "total": {n}, "incorrect": <int>, "note": "<one short sentence>"}}"""


def run(cmd: list[str], cwd: Path, timeout: int = 420) -> dict:
    try:
        out = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
        return json.loads(out.stdout.decode("utf-8", "replace"))
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return {"is_error": True, "result": f"harness error: {exc}"}


def snapshot(repo: Path, docs: str, keep_docs: bool, plugin_script: Path) -> Path:
    """Copy tracked and untracked files into a fresh Git repository."""
    target = Path(tempfile.mkdtemp(prefix="archlens-eval-")).resolve()
    listing = subprocess.check_output(["git", "-C", str(repo), "ls-files", "-co", "--exclude-standard", "-z"])
    for name in (n.decode() for n in listing.split(b"\0") if n):
        source = repo / name
        if not source.is_file() or (not keep_docs and name.startswith(docs + "/")):
            continue
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target / name)
    git = ["git", "-C", str(target)]
    subprocess.run(git + ["init", "-q"], check=True)
    if keep_docs:
        subprocess.run([sys.executable, str(plugin_script), "sync", "--root", str(target), "--all"],
                       check=True, stdout=subprocess.DEVNULL)
    subprocess.run(git + ["add", "."], check=True)
    subprocess.run(git + ["-c", "user.name=eval", "-c", "user.email=eval@example.invalid", "commit", "-qm", "snapshot"], check=True)
    return target


def ask(workspace: Path, question: str, model: str, with_plugin: bool) -> dict:
    cmd = [
        "claude", "-p", ANSWER_PROMPT.format(q=question), "--model", model,
        "--output-format", "json", "--no-session-persistence",
        "--setting-sources", "project", "--strict-mcp-config",
        "--tools", "Read", "Grep", "Glob", "--max-budget-usd", "1.50",
    ]
    if with_plugin:
        cmd += ["--plugin-dir", str(PLUGIN)]
    return run(cmd, workspace)


def judge(question: dict, answer: str, model: str, cwd: Path) -> dict:
    prompt = JUDGE_PROMPT.format(
        q=question["question"], key="\n".join(f"- {k}" for k in question["key"]),
        a=answer, n=len(question["key"]),
    )
    result = run(["claude", "-p", prompt, "--model", model, "--output-format", "json",
                  "--no-session-persistence", "--setting-sources", "project", "--strict-mcp-config",
                  "--tools", ""], cwd, timeout=180)
    text = str(result.get("result", "")).strip().strip("`").removeprefix("json").strip()
    covered = re.search(r'"covered"\s*:\s*(\d+)', text)
    incorrect = re.search(r'"incorrect"\s*:\s*(\d+)', text)
    note = re.search(r'"note"\s*:\s*"(.*?)"\s*}', text, re.S)
    if not covered or not incorrect:
        return {"covered": None, "total": len(question["key"]), "incorrect": None, "note": f"unparsed: {text[:300]}"}
    return {"covered": min(int(covered[1]), len(question["key"])), "total": len(question["key"]),
            "incorrect": int(incorrect[1]), "note": note[1] if note else ""}


def metrics(result: dict) -> dict:
    usage = result.get("usage") or {}
    fresh = usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
    cached = usage.get("cache_read_input_tokens", 0)
    return {
        "inputTokens": fresh + cached, "uncachedInputTokens": fresh, "cachedInputTokens": cached,
        "outputTokens": usage.get("output_tokens", 0), "turns": result.get("num_turns"),
        "costUsd": result.get("total_cost_usd"), "durationMs": result.get("duration_ms"),
        "error": bool(result.get("is_error")),
    }


def bootstrap(values: list[float], rounds: int = 2000) -> tuple[float, float]:
    """95% percentile bootstrap interval of the mean, with a fixed seed."""
    rng = random.Random(11)
    means = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(rounds))
    return means[int(0.025 * rounds)], means[int(0.975 * rounds) - 1]


def summarize(rows: list[dict]) -> list[dict]:
    table = []
    for condition in CONDITIONS:
        subset = [r for r in rows if r["condition"] == condition and r["grade"]["covered"] is not None]
        if not subset:
            continue
        mean = lambda key: statistics.mean(r[key] for r in subset)  # noqa: E731
        recalls = [r["grade"]["covered"] / r["grade"]["total"] for r in subset]
        low, high = bootstrap(recalls)
        table.append({
            "condition": condition, "runs": len(subset),
            "keyFactRecall": round(statistics.mean(recalls), 3),
            "recallCi95": [round(low, 3), round(high, 3)],
            "incorrectClaimsPerAnswer": round(statistics.mean(r["grade"]["incorrect"] for r in subset), 2),
            "inputTokens": round(mean("inputTokens")), "uncachedInputTokens": round(mean("uncachedInputTokens")),
            "outputTokens": round(mean("outputTokens")), "turns": round(mean("turns"), 1),
            "costUsd": round(mean("costUsd"), 4), "seconds": round(mean("durationMs") / 1000, 1),
        })
    return table


def markdown(summary: list[dict], meta: dict) -> str:
    lines = [
        f"Model: {meta['model']}; judge: {meta['judge']}; {meta['questions']} questions x {meta['reps']} runs; {meta['date']}.",
        "",
        "| Condition | Key-fact recall (95% CI) | Wrong claims / answer | Input tokens | Uncached input | Output | Turns | Cost | Time |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summary:
        ci = s["recallCi95"]
        lines.append(
            f"| {s['condition']} | {s['keyFactRecall']:.0%} ({ci[0]:.0%}-{ci[1]:.0%}) | {s['incorrectClaimsPerAnswer']} | {s['inputTokens']:,} | "
            f"{s['uncachedInputTokens']:,} | {s['outputTokens']:,} | {s['turns']} | ${s['costUsd']:.3f} | {s['seconds']} s |"
        )
    return "\n".join(lines) + "\n"


def per_question(rows: list[dict]) -> str:
    conditions = [c for c in CONDITIONS if any(r["condition"] == c for r in rows)]
    lines = ["| Question | " + " | ".join(conditions) + " |", "|---|" + "---:|" * len(conditions)]
    for question in sorted({r["question"] for r in rows}):
        cells = []
        for condition in conditions:
            grades = [r["grade"] for r in rows if r["question"] == question and r["condition"] == condition
                      and r["grade"]["covered"] is not None]
            cells.append(f"{statistics.mean(g['covered'] / g['total'] for g in grades):.0%}" if grades else "-")
        lines.append(f"| {question} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--docs", default="docs/architecture")
    parser.add_argument("--questions", type=Path)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--judge", default="sonnet")
    parser.add_argument("--reps", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--conditions", default=",".join(CONDITIONS))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--reuse", type=Path, help="Earlier result file; keep its runs for conditions not run now")
    parser.add_argument("--regrade", action="store_true", help="With --reuse, re-grade reused runs that failed to parse")
    parser.add_argument("--report", type=Path, help="Only print the summary of an existing result file")
    parser.add_argument("--rejudge", action="store_true", help="With --report and --questions, re-grade every stored answer")
    args = parser.parse_args(argv)
    if args.report and args.rejudge:
        data = json.loads(args.report.read_text(encoding="utf-8"))
        questions = {q["id"]: q for q in json.loads(args.questions.read_text(encoding="utf-8"))["questions"]}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            grades = list(pool.map(lambda r: judge(questions[r["question"]], r["answer"], args.judge, ROOT), data["runs"]))
        for row, grade in zip(data["runs"], grades):
            row["grade"] = grade
        data["summary"] = summarize(data["runs"])
        data["meta"]["regraded"] = date.today().isoformat()
        args.report.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if args.report:
        data = json.loads(args.report.read_text(encoding="utf-8"))
        print(markdown(summarize(data["runs"]), data["meta"]))
        print(per_question(data["runs"]))
        return 0
    spec = json.loads(args.questions.read_text(encoding="utf-8"))
    conditions = [c for c in args.conditions.split(",") if c in CONDITIONS]
    script = PLUGIN / "scripts/archlens.py"
    workspaces = {
        "no-handbook": snapshot(args.repo, args.docs, False, script),
        "handbook": snapshot(args.repo, args.docs, True, script),
    }
    workspaces["archlens"] = workspaces["handbook"]
    jobs = [(c, q, r) for c in conditions for q in spec["questions"] for r in range(args.reps)]
    random.Random(7).shuffle(jobs)

    def work(job):
        condition, question, rep = job
        result = ask(workspaces[condition], question["question"], args.model, condition == "archlens")
        answer = str(result.get("result", ""))
        row = {"condition": condition, "question": question["id"], "rep": rep, "answer": answer, **metrics(result)}
        row["grade"] = judge(question, answer, args.judge, workspaces["no-handbook"])
        print(f"{condition:12} {question['id']:14} rep{rep} recall={row['grade']['covered']}/{row['grade']['total']} "
              f"in={row['inputTokens']} turns={row['turns']}", file=sys.stderr, flush=True)
        return row

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(work, jobs))
    if args.reuse:
        questions = {q["id"]: q for q in spec["questions"]}
        reused = [r for r in json.loads(args.reuse.read_text(encoding="utf-8"))["runs"] if r["condition"] not in conditions]
        for row in reused:
            if args.regrade and row["grade"]["covered"] is None:
                row["grade"] = judge(questions[row["question"]], row["answer"], args.judge, workspaces["no-handbook"])
        rows = reused + rows
    meta = {"model": args.model, "judge": args.judge, "questions": len(spec["questions"]),
            "reps": args.reps, "date": date.today().isoformat(), "repository": spec.get("repository")}
    summary = summarize(rows)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"meta": meta, "summary": summary, "runs": rows}, indent=2) + "\n", encoding="utf-8")
    print(markdown(summary, meta))
    for path in set(workspaces.values()):
        shutil.rmtree(path, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
