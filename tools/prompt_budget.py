"""Check deterministic prompt-size budgets; byte counts are not model token counts."""

import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/archlens"
SKILL_LIMIT = 2600
CONTRACT_LIMIT = 2400
BASE_LIMIT = 5000
REQUIRED_SECTIONS = {
    "setup": [
        ("configuration.md", None),
        ("workflow.md", "Initial coverage"),
        ("workflow.md", "Trace execution and data"),
    ],
    "decide": [("templates.md", "Decision record")],
}
COLD_LIMITS = {"setup": 10500, "decide": 6500, "check": 5000, "update": 5000, "explain": 5000}


def section_bytes(filename, heading):
    text = (PLUGIN / "references" / filename).read_text(encoding="utf-8")
    if heading is None:
        return len(text.encode("utf-8"))
    match = re.search(rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)", text)
    if not match:
        raise ValueError(f"Missing routed section: {filename}: {heading}")
    return len(match[0].encode("utf-8"))


def audit():
    contract = (PLUGIN / "references/contract.md").read_bytes()
    errors = []
    routes = []
    if len(contract) > CONTRACT_LIMIT:
        errors.append(f"Shared contract exceeds {CONTRACT_LIMIT} bytes")
    for path in sorted((PLUGIN / "skills").glob("*/SKILL.md")):
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        name = path.parent.name
        if len(raw) > SKILL_LIMIT:
            errors.append(f"{name}: skill exceeds {SKILL_LIMIT} bytes")
        if len(raw) + len(contract) > BASE_LIMIT:
            errors.append(f"{name}: base instructions exceed {BASE_LIMIT} bytes")
        for expected in (
            f"name: {name}", "disable-model-invocation: true", "context: fork",
            "agent: general-purpose", "background: false",
        ):
            if expected not in text.split("---", 2)[1]:
                errors.append(f"{name}: missing {expected}")
        if "!`" in text or re.search(r"(?m)^```!", text):
            errors.append(f"{name}: eager shell injection is prohibited")
        if "references/contract.md" not in text:
            errors.append(f"{name}: missing bounded-read contract")
        for target in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w/.-]+)", text):
            if not (PLUGIN / target).is_file():
                errors.append(f"{name}: missing resource {target}")
        required_bytes = sum(section_bytes(*item) for item in REQUIRED_SECTIONS.get(name, []))
        cold_bytes = len(raw) + len(contract) + required_bytes
        if cold_bytes > COLD_LIMITS.get(name, 0):
            errors.append(f"{name}: required cold-load references exceed the command budget")
        routes.append({
            "command": f"/archlens:{name}", "skillBytes": len(raw),
            "contractBytes": len(contract), "baseBytes": len(raw) + len(contract),
            "roughBaseTokens": (len(raw) + len(contract) + 3) // 4,
            "requiredColdBytes": cold_bytes,
            "roughRequiredColdTokens": (cold_bytes + 3) // 4,
        })
    if len(routes) != 5:
        errors.append("Expected exactly five explicit command routes")
    for forbidden in ("agents", "hooks", ".mcp.json", "CLAUDE.md"):
        if (PLUGIN / forbidden).exists():
            errors.append(f"New always-on surface needs a budget review: {forbidden}")
    return {
        "ok": not errors, "errors": errors, "routes": routes,
        "note": "Tokens are a rough bytes/4 estimate, NOT measured Claude tokens. Conditional reads, source, tool output, and host context are extra.",
    }


if __name__ == "__main__":
    report = audit()
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["ok"] else 1)
