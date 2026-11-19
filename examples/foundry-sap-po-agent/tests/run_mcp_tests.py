#!/usr/bin/env python3
"""Runtime tests against the deployed MCP server in API Management (TC-01…TC-11).

  export TOKEN_READER=$(az account get-access-token --resource api://sap-po-agent --query accessToken -o tsv)
  export TOKEN_NOROLE=<token of a test user without PurchaseOrder.Read>      # optional, for TC-02
  python3 examples/foundry-sap-po-agent/tests/run_mcp_tests.py [--settings path] [--rate-limit]

Values come from config/settings.json (mcp.serverUrl, test.purchaseOrder, test.supplier).
Tests without the token they need are reported as SKIP. Exit code 1 if any test fails.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from po_agent.mcp_client import McpClient, tool_result_text  # noqa: E402

EXPECTED_TOOLS = {"get_purchase_order_status", "list_supplier_purchase_orders"}


def is_error(resp, msg):
    if resp.status >= 400:
        return True
    _, flagged = tool_result_text(msg)
    text, _ = tool_result_text(msg)
    return flagged or bool(re.search(r"\b(400|404|405)\b", text))


def run(settings, reader, norole, rate_limit):
    url = settings["mcp"]["serverUrl"]
    po, supplier = settings["test"]["purchaseOrder"], settings["test"]["supplier"]
    results = []

    def record(test_id, ok, detail):
        results.append((test_id, "PASS" if ok else "FAIL", detail))

    def skip(test_id, detail):
        results.append((test_id, "SKIP", detail))

    resp, _ = McpClient(url).initialize()
    record("TC-01", resp.status == 401, f"no token -> {resp.status} (expected 401)")

    if norole:
        resp, _ = McpClient(url, norole).initialize()
        record("TC-02", resp.status in (401, 403), f"token without role -> {resp.status} (expected 401/403)")
    else:
        skip("TC-02", "TOKEN_NOROLE not set")

    if not reader:
        for tc in ("TC-03", "TC-04", "TC-05", "TC-06", "TC-07", "TC-08", "TC-09", "TC-10", "TC-11"):
            skip(tc, "TOKEN_READER not set")
        return results

    client = McpClient(url, reader)
    resp, msg = client.initialize()
    record("TC-03", resp.status == 200 and msg is not None and "result" in msg,
           f"initialize -> {resp.status}, session {'set' if client.session_id else 'none'}")

    resp, msg = client.list_tools()
    names = {t.get("name") for t in ((msg or {}).get("result") or {}).get("tools", [])}
    record("TC-04", names == EXPECTED_TOOLS, f"tools/list -> {sorted(names)} (expected exactly {sorted(EXPECTED_TOOLS)})")

    resp, msg = client.call_tool("get_purchase_order_status", {"purchaseOrder": po})
    text, _ = tool_result_text(msg)
    record("TC-05", not is_error(resp, msg) and po in text, f"status of {po} -> {resp.status}, {len(text)} chars")

    resp, msg = client.call_tool("get_purchase_order_status", {"purchaseOrder": "45' or 1 eq 1"})
    record("TC-06", is_error(resp, msg), "injection-like purchase order number rejected")

    resp, msg = client.call_tool("list_supplier_purchase_orders", {"supplier": supplier, "top": 3})
    text, _ = tool_result_text(msg)
    try:
        rows = json.loads(text).get("d", {}).get("results", [])
    except (json.JSONDecodeError, AttributeError):
        rows = None
    record("TC-07", not is_error(resp, msg) and rows is not None and len(rows) <= 3,
           f"supplier {supplier}, top 3 -> {None if rows is None else len(rows)} rows")

    resp, msg = client.call_tool("list_supplier_purchase_orders", {"supplier": supplier, "top": 50})
    record("TC-08", is_error(resp, msg), "top=50 rejected (max 20)")

    resp, msg = client.call_tool("delete_purchase_order", {"purchaseOrder": po})
    record("TC-09", is_error(resp, msg) or (msg or {}).get("error") is not None, "unknown tool rejected")

    api_url = re.sub(r"/[^/]+/mcp/?$", f"/sap-po-tools/purchase-orders/{po}", url)
    req = urllib.request.Request(api_url, data=b"{}", method="POST",
                                 headers={"Authorization": f"Bearer {reader}", "Content-Type": "application/json"})
    try:
        status = urllib.request.urlopen(req, timeout=30).status
    except urllib.error.HTTPError as err:
        status = err.code
    record("TC-10", status in (404, 405), f"POST on the facade API -> {status} (expected 405, or 404 if no POST operation)")

    if rate_limit:
        statuses = [client.call_tool("get_purchase_order_status", {"purchaseOrder": po})[0].status for _ in range(35)]
        record("TC-11", 429 in statuses, f"35 calls in a burst -> 429 seen: {429 in statuses}")
    else:
        skip("TC-11", "run with --rate-limit")
    return results


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", default=str(ROOT / "config/settings.json"))
    parser.add_argument("--rate-limit", action="store_true")
    args = parser.parse_args(argv)
    settings = json.loads(Path(args.settings).read_text())
    results = run(settings, os.environ.get("TOKEN_READER"), os.environ.get("TOKEN_NOROLE"), args.rate_limit)
    for test_id, status, detail in results:
        print(f"{status:4} {test_id}: {detail}")
    counts = {s: sum(1 for r in results if r[1] == s) for s in ("PASS", "FAIL", "SKIP")}
    print(f"{counts['PASS']} passed, {counts['FAIL']} failed, {counts['SKIP']} skipped")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
