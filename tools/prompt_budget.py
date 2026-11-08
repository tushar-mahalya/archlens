"""Check deterministic prompt-size budgets; byte counts are not model token counts."""

import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/archlens"
PORTABLE = ROOT / "skills/archlens"
SKILL_LIMIT = 2600
CONTRACT_LIMIT = 2400
BASE_LIMIT = 5000
ROUTER_LIMIT = 2200
PORTABLE_BASE_LIMIT = 7200
REQUIRED_SECTIONS = {
    "setup": [
        ("configuration.md", "Document map"),
        ("configuration.md", "Freshness and agent context"),
        ("workflow.md", "Initial coverage"),
        ("workflow.md", "Trace execution and data"),
    ],
    "decide": [("templates.md", "Decision record")],
}
COLD_LIMITS = {"setup": 10500, "decide": 6500, "check": 5000, "update": 5000, "explain": 5000, "learn": 2200}
PORTABLE_COLD_LIMITS = {"setup": 12700, "decide": 8700, "check": 7200, "update": 7200, "explain": 7200, "learn": 4200}
OPERATIONS = ("setup", "update", "check", "explain", "decide", "learn")
# Only update may be chosen by the model, so only its description costs startup context.
MODEL_INVOCABLE = {"update"}
DESCRIPTION_LIMIT = 260
# learn runs inline so the user can keep asking follow-up questions; it skips the contract.
INLINE = {"learn"}
# PostToolUse adds at most one short pointer per documented page per session.
HOOK_EVENTS = {"SessionStart", "Stop", "PostToolUse"}
CONTEXT_BUDGET_LIMIT = 4000


def section_bytes(filename, heading):
    text = (PLUGIN / "references" / filename).read_text(encoding="utf-8")
    if heading is None:
        return len(text.encode("utf-8"))
    match = re.search(rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)", text)
    if not match:
        raise ValueError(f"Missing routed section: {filename}: {heading}")
    return len(match[0].encode("utf-8"))


def audit_hooks():
    """Hooks may only inject the bounded map at session start and nudge at stop."""
    path = PLUGIN / "hooks/hooks.json"
    if not path.exists():
        return []
    errors = []
    hooks = json.loads(path.read_text(encoding="utf-8"))["hooks"]
    if set(hooks) - HOOK_EVENTS:
        errors.append(f"Hooks limited to {sorted(HOOK_EVENTS)}; review budget for {sorted(set(hooks) - HOOK_EVENTS)}")
    for event, groups in hooks.items():
        for group in groups:
            for hook in group["hooks"]:
                args = hook.get("args", [])
                if hook.get("type") != "command" or not args or "scripts/archlens.py" not in args[0]:
                    errors.append(f"{event}: hooks must run the bundled checker in exec form")
                if hook.get("async") or hook.get("asyncRewake"):
                    errors.append(f"{event}: async hooks are not budgeted")
    return errors


def audit():
    contract = (PLUGIN / "references/contract.md").read_bytes()
    errors = []
    routes = []
    if len(contract) > CONTRACT_LIMIT:
        errors.append(f"Shared contract exceeds {CONTRACT_LIMIT} bytes")
    startup_bytes = 0
    for path in sorted((PLUGIN / "skills").glob("*/SKILL.md")):
        raw = path.read_bytes()
        text = raw.decode("utf-8").replace("\r\n", "\n")
        name = path.parent.name
        frontmatter = text.split("---", 2)[1]
        inline = name in INLINE
        contract_bytes = 0 if inline else len(contract)
        if len(raw) > SKILL_LIMIT:
            errors.append(f"{name}: skill exceeds {SKILL_LIMIT} bytes")
        if len(raw) + contract_bytes > BASE_LIMIT:
            errors.append(f"{name}: base instructions exceed {BASE_LIMIT} bytes")
        expected = [f"name: {name}", "metadata:\n  internal: true"]
        if not inline:
            expected += ["context: fork", "agent: general-purpose", "background: false"]
        if name not in MODEL_INVOCABLE:
            expected.append("disable-model-invocation: true")
        for item in expected:
            if item not in frontmatter:
                errors.append(f"{name}: missing {item}")
        if inline and "context: fork" in frontmatter:
            errors.append(f"{name}: inline skill must not fork")
        if name in MODEL_INVOCABLE:
            if "disable-model-invocation: true" in frontmatter:
                errors.append(f"{name}: expected to be model-invocable")
            description = re.search(r'(?m)^description: "(.*)"$', frontmatter)
            size = len(description[1].encode("utf-8")) if description else DESCRIPTION_LIMIT + 1
            if size > DESCRIPTION_LIMIT:
                errors.append(f"{name}: startup description exceeds {DESCRIPTION_LIMIT} bytes")
            startup_bytes += size
        if "!`" in text or re.search(r"(?m)^```!", text):
            errors.append(f"{name}: eager shell injection is prohibited")
        if not inline and "references/contract.md" not in text:
            errors.append(f"{name}: missing bounded-read contract")
        for target in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w/.-]+)", text):
            if not (PLUGIN / target).is_file():
                errors.append(f"{name}: missing resource {target}")
        required_bytes = sum(section_bytes(*item) for item in REQUIRED_SECTIONS.get(name, []))
        cold_bytes = len(raw) + contract_bytes + required_bytes
        if cold_bytes > COLD_LIMITS.get(name, 0):
            errors.append(f"{name}: required cold-load references exceed the command budget")
        routes.append({
            "command": f"/archlens:{name}", "skillBytes": len(raw),
            "contractBytes": contract_bytes, "baseBytes": len(raw) + contract_bytes,
            "roughBaseTokens": (len(raw) + contract_bytes + 3) // 4,
            "requiredColdBytes": cold_bytes,
            "roughRequiredColdTokens": (cold_bytes + 3) // 4,
            "runs": "inline" if inline else "isolated",
        })
    if len(routes) != len(OPERATIONS):
        errors.append(f"Expected exactly {len(OPERATIONS)} command routes")
    errors.extend(audit_hooks())
    defaults = json.loads((PLUGIN / "defaults.json").read_text(encoding="utf-8"))
    if defaults["contextBudget"] > CONTEXT_BUDGET_LIMIT:
        errors.append(f"Default session context budget exceeds {CONTEXT_BUDGET_LIMIT} bytes")
    router = (PORTABLE / "SKILL.md").read_bytes()
    router_text = router.decode("utf-8").replace("\r\n", "\n")
    if len(router) > ROUTER_LIMIT:
        errors.append(f"Portable router exceeds {ROUTER_LIMIT} bytes")
    if router_text.count("](references/contract.md)") != 1:
        errors.append("Portable router must link the shared contract exactly once")
    portable_routes = []
    for name in OPERATIONS:
        if router_text.count(f"](workflows/{name}.md)") != 1:
            errors.append(f"Portable router must link the {name} workflow exactly once")
        path = PORTABLE / "workflows" / f"{name}.md"
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        if len(raw) > SKILL_LIMIT:
            errors.append(f"Portable {name}: workflow exceeds {SKILL_LIMIT} bytes")
        base_bytes = len(router) + len(raw) + (0 if name in INLINE else len(contract))
        if base_bytes > PORTABLE_BASE_LIMIT:
            errors.append(f"Portable {name}: base instructions exceed {PORTABLE_BASE_LIMIT} bytes")
        required_bytes = sum(section_bytes(*item) for item in REQUIRED_SECTIONS.get(name, []))
        cold_bytes = base_bytes + required_bytes
        if cold_bytes > PORTABLE_COLD_LIMITS[name]:
            errors.append(f"Portable {name}: required cold-load references exceed the operation budget")
        for target in re.findall(r"<skill-dir>/([\w/.-]+)", text):
            if not (PORTABLE / target).is_file():
                errors.append(f"Portable {name}: missing resource {target}")
        if "${CLAUDE_PLUGIN_ROOT}" in text or "$ARGUMENTS" in text:
            errors.append(f"Portable {name}: Claude-specific placeholder remains")
        portable_routes.append({
            "operation": name, "routerBytes": len(router), "workflowBytes": len(raw),
            "contractBytes": len(contract), "baseBytes": base_bytes,
            "requiredColdBytes": cold_bytes,
            "roughRequiredColdTokens": (cold_bytes + 3) // 4,
        })
    for forbidden in ("agents", ".mcp.json", "CLAUDE.md", "output-styles", "monitors"):
        if (PLUGIN / forbidden).exists():
            errors.append(f"New always-on surface needs a budget review: {forbidden}")
    return {
        "ok": not errors, "errors": errors,
        "startup": {
            "modelInvocableDescriptionBytes": startup_bytes,
            "sessionContextBudgetBytes": defaults["contextBudget"],
            "note": "Session context loads only in projects with an Archlens map; elsewhere hooks print nothing.",
        },
        "routes": routes, "portableRoutes": portable_routes,
        "note": "Tokens are a rough bytes/4 estimate, NOT measured model tokens. Conditional reads, source, tool output, and host context are extra.",
    }


if __name__ == "__main__":
    report = audit()
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["ok"] else 1)
