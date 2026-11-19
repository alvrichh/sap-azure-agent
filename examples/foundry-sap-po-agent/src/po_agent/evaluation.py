"""Scores agent runs against eval/cases.json (expected tool calls and arguments)."""
import json
from pathlib import Path


def load_cases(path, purchase_order, supplier):
    """Cases with the <test-purchase-order> / <test-supplier> markers replaced by real test values."""
    raw = Path(path).read_text()
    raw = raw.replace("<test-purchase-order>", purchase_order).replace("<test-supplier>", supplier)
    return json.loads(raw)["cases"]


def tool_calls_from_output(output_items):
    """[(tool name, arguments dict)] from Responses API output items of type mcp_call."""
    calls = []
    for item in output_items:
        item_type = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
        if item_type != "mcp_call":
            continue
        get = item.get if isinstance(item, dict) else (lambda k, d=None, i=item: getattr(i, k, d))
        args = get("arguments", "{}") or "{}"
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"_raw": args}
        calls.append((get("name"), args))
    return calls


def score_case(case, calls, answer):
    """Return a list of failures (empty list = pass)."""
    failures = []
    names = [name for name, _ in calls]
    expected = case.get("expectTools", [])
    if not expected and names:
        failures.append(f"expected no tool call, got {names}")
    for tool in expected:
        if tool not in names:
            failures.append(f"expected a call to {tool}, got {names}")
    for key, value in case.get("expectArgs", {}).items():
        seen = [args.get(key) for name, args in calls if name in expected]
        if not any(str(v) == str(value) for v in seen):
            failures.append(f"expected argument {key}={value!r}, got {seen}")
    for text in case.get("expectAnswerContains", []):
        if text.lower() not in (answer or "").lower():
            failures.append(f"answer should mention {text!r}")
    for text in case.get("expectAnswerNotContains", []):
        if text.lower() in (answer or "").lower():
            failures.append(f"answer must not say {text!r}")
    return failures
