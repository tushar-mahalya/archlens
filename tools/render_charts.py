"""Render README benchmark charts as static SVG from benchmarks/results/model-sonnet.json.

Small multiples, one measure per panel, so no panel needs a second axis.
Archlens is the one highlighted series; baselines are neutral and every bar is labeled.
Usage: python tools/render_charts.py
"""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "benchmarks/results/model-sonnet.json"
TARGET = ROOT / "docs/assets/benchmark.svg"
LABELS = {"no-handbook": "No handbook", "handbook": "Handbook only", "archlens": "Archlens"}
PANELS = [
    ("keyFactRecall", "Key facts recalled", lambda v: f"{v:.0%}", "higher is better"),
    ("inputTokens", "Input tokens per answer", lambda v: f"{v / 1000:.1f}k", "lower is better"),
    ("turns", "Agent turns per answer", lambda v: f"{v:.1f}", "lower is better"),
    ("costUsd", "Cost per answer", lambda v: f"${v:.3f}", "lower is better"),
]
STYLE = """
  .surface { fill: none; }
  .title { font: 600 15px ui-sans-serif, -apple-system, 'Segoe UI', sans-serif; fill: #0b0b0b; }
  .note { font: 400 12px ui-sans-serif, -apple-system, 'Segoe UI', sans-serif; fill: #52514e; }
  .label { font: 400 13px ui-sans-serif, -apple-system, 'Segoe UI', sans-serif; fill: #52514e; }
  .label.focus { font-weight: 600; fill: #0b0b0b; }
  .value { font: 600 13px ui-monospace, 'SF Mono', Menlo, monospace; fill: #0b0b0b; }
  .bar { fill: #8a8984; }
  .bar.focus { fill: #2a78d6; }
  .ci { stroke: #0b0b0b; stroke-width: 1.5; }
  .axis { stroke: #d8d7d2; stroke-width: 1; }
  @media (prefers-color-scheme: dark) {
    .title, .value, .label.focus { fill: #f0efec; }
    .note, .label { fill: #c3c2b7; }
    .bar { fill: #8e8d88; }
    .bar.focus { fill: #3987e5; }
    .ci { stroke: #f0efec; }
    .axis { stroke: #3a3a37; }
  }
"""


def render(summary: list[dict], meta: dict) -> str:
    rows = {row["condition"]: row for row in summary}
    order = [c for c in ("no-handbook", "handbook", "archlens") if c in rows]
    width, panel_w, panel_h, gap = 960, 450, 128, 22
    label_w, bar_max, bar_h, row_gap = 120, 230, 18, 12
    height = 70 + 2 * (panel_h + gap)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-labelledby="t d">',
        '<title id="t">Archlens benchmark: answer quality and cost</title>',
        f'<desc id="d">{escape(describe(rows, order))}</desc>',
        f"<style>{STYLE}</style>",
        f'<rect class="surface" width="{width}" height="{height}"/>',
        f'<text class="note" x="20" y="28">{escape(subtitle(meta))}</text>',
    ]
    for index, (key, title, fmt, hint) in enumerate(PANELS):
        x0 = 20 + (index % 2) * (panel_w + gap)
        y0 = 50 + (index // 2) * (panel_h + gap)
        out.append(f'<text class="title" x="{x0}" y="{y0 + 16}">{escape(title)}</text>')
        out.append(f'<text class="note" x="{x0 + panel_w - 10}" y="{y0 + 16}" text-anchor="end">{hint}</text>')
        top = max(rows[c][key] if key != "keyFactRecall" else 1.0 for c in order)
        base_x = x0 + label_w
        out.append(f'<line class="axis" x1="{base_x}" y1="{y0 + 30}" x2="{base_x}" y2="{y0 + 30 + 3 * (bar_h + row_gap)}"/>')
        for row_index, condition in enumerate(order):
            value = rows[condition][key]
            y = y0 + 34 + row_index * (bar_h + row_gap)
            focus = " focus" if condition == "archlens" else ""
            length = max(2.0, bar_max * value / top)
            out.append(f'<text class="label{focus}" x="{base_x - 10}" y="{y + 13}" text-anchor="end">{LABELS[condition]}</text>')
            out.append(f'<rect class="bar{focus}" x="{base_x}" y="{y}" width="{length:.1f}" height="{bar_h}" rx="4"/>')
            end = base_x + length
            if key == "keyFactRecall" and rows[condition].get("recallCi95"):
                low, high = rows[condition]["recallCi95"]
                lx, hx = base_x + bar_max * low, base_x + bar_max * high
                mid = y + bar_h / 2
                out.append(f'<line class="ci" x1="{lx:.1f}" y1="{mid}" x2="{hx:.1f}" y2="{mid}"/>')
                out.append(f'<line class="ci" x1="{lx:.1f}" y1="{mid - 5}" x2="{lx:.1f}" y2="{mid + 5}"/>')
                out.append(f'<line class="ci" x1="{hx:.1f}" y1="{mid - 5}" x2="{hx:.1f}" y2="{mid + 5}"/>')
                end = max(end, hx)
            out.append(f'<text class="value" x="{end + 8:.1f}" y="{y + 13}">{fmt(value)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def subtitle(meta: dict) -> str:
    runs = meta["questions"] * meta["reps"]
    return (f"{runs} answers per condition, Claude Code ({meta['model']}), {meta['date']}. "
            "Recall bars show 95% confidence intervals. Source: docs/benchmarks.md")


def describe(rows: dict, order: list[str]) -> str:
    parts = []
    for condition in order:
        r = rows[condition]
        parts.append(f"{LABELS[condition]}: recall {r['keyFactRecall']:.0%}, {r['inputTokens']} input tokens, "
                     f"{r['turns']} turns, ${r['costUsd']:.3f} per answer")
    return "; ".join(parts) + "."


def main() -> int:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(render(data["summary"], data["meta"]), encoding="utf-8")
    print(f"Wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
