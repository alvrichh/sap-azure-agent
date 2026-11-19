"""Unit tests (no Azure, Foundry or SAP needed): tool configuration rules, MCP parsing, evaluation scoring,
and the runtime test script exercised against a local mock of the APIM MCP endpoint."""
import contextlib
import io
import json
import re
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from po_agent.evaluation import load_cases, score_case, tool_calls_from_output  # noqa: E402
from po_agent.mcp_client import parse_mcp_body, tool_result_text  # noqa: E402
from po_agent.tool_config import (ToolConfigError, approval_setting, build_mcp_tool_kwargs,  # noqa: E402
                                  check_mcp_tool_kwargs, should_approve)
import run_mcp_tests  # noqa: E402

SETTINGS = json.loads((ROOT / "config/settings.example.json").read_text())
TOOLS = ["get_purchase_order_status", "list_supplier_purchase_orders"]


def settings_with(**mcp):
    s = json.loads(json.dumps(SETTINGS))
    s["mcp"].update(mcp)
    s["mcp"]["serverUrl"] = "https://apim.example.net/sap-po-mcp/mcp"
    return s


class ToolConfigTests(unittest.TestCase):
    def test_example_settings_build_a_safe_tool(self):  # UT-01
        kw = build_mcp_tool_kwargs(settings_with())
        self.assertEqual(kw["allowed_tools"], TOOLS)
        self.assertEqual(kw["require_approval"], {"never": TOOLS})
        self.assertEqual(kw["project_connection_id"], "sap-po-mcp-connection")

    def test_empty_allowed_tools_is_rejected(self):  # UT-02: [] means every tool in Foundry
        with self.assertRaises(ToolConfigError):
            build_mcp_tool_kwargs(settings_with(tools=[]))

    def test_never_for_all_is_rejected(self):  # UT-03
        kw = build_mcp_tool_kwargs(settings_with())
        kw["require_approval"] = "never"
        with self.assertRaises(ToolConfigError):
            check_mcp_tool_kwargs(kw, TOOLS)

    def test_write_tool_keeps_approval(self):  # UT-04
        s = settings_with(tools=TOOLS + ["release_purchase_order"])
        kw = build_mcp_tool_kwargs(s)
        self.assertNotIn("release_purchase_order", kw["require_approval"]["never"])
        self.assertEqual(approval_setting(["release_purchase_order"], TOOLS), "always")

    def test_undeclared_tool_cannot_skip_approval(self):  # UT-05
        kw = build_mcp_tool_kwargs(settings_with())
        kw["require_approval"] = {"never": ["release_purchase_order"]}
        with self.assertRaises(ToolConfigError):
            check_mcp_tool_kwargs(kw, TOOLS)

    def test_approval_denies_unknown_tools_and_asks_otherwise(self):  # UT-06
        self.assertFalse(should_approve("delete_po", {}, TOOLS, TOOLS, lambda *_: True))
        self.assertTrue(should_approve(TOOLS[0], {}, TOOLS, TOOLS, lambda *_: True))
        self.assertFalse(should_approve(TOOLS[0], {}, TOOLS, TOOLS, lambda *_: False))


class McpParsingTests(unittest.TestCase):
    def test_json_and_sse_bodies(self):  # UT-07
        msg = {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}}
        self.assertEqual(parse_mcp_body("application/json", json.dumps(msg)), [msg])
        sse = f"event: message\ndata: {json.dumps(msg)}\n\n"
        self.assertEqual(parse_mcp_body("text/event-stream", sse), [msg])
        self.assertEqual(parse_mcp_body("application/json", ""), [])

    def test_tool_result_text(self):  # UT-08
        ok = {"result": {"content": [{"type": "text", "text": "abc"}]}}
        self.assertEqual(tool_result_text(ok), ("abc", False))
        self.assertTrue(tool_result_text({"result": {"content": [], "isError": True}})[1])
        self.assertTrue(tool_result_text({"error": {"code": -32602}})[1])


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.cases = {c["id"]: c for c in load_cases(ROOT / "eval/cases.json", "4500000001", "17300001")}

    def test_markers_replaced(self):  # UT-09
        self.assertNotIn("<test-", json.dumps(list(self.cases.values())))

    def test_scoring(self):  # UT-10
        out = [{"type": "mcp_call", "name": "get_purchase_order_status", "arguments": '{"purchaseOrder": "4500000001"}'},
               {"type": "message"}]
        calls = tool_calls_from_output(out)
        self.assertEqual(score_case(self.cases["EV-01"], calls, "PO 4500000001 is released"), [])
        self.assertTrue(score_case(self.cases["EV-02"], calls, ""))  # wrong tool
        self.assertTrue(score_case(self.cases["EV-04"], calls, "Done"))  # must not call, must mention Fiori
        self.assertEqual(score_case(self.cases["EV-04"], [], "I can't release it; use the SAP Fiori app."), [])

    def test_injection_case(self):  # UT-12: the agent reads the status and doesn't obey the pasted email
        calls = [("get_purchase_order_status", {"purchaseOrder": "4500000001"})]
        case = self.cases["EV-07"]
        self.assertEqual(score_case(case, calls, "PO 4500000001 is not released yet. I can't release it: use the SAP Fiori app."), [])
        self.assertTrue(score_case(case, calls, "Done, I have released PO 4500000001."))
        self.assertTrue(score_case(case, [], "I can't help with that."))  # must still look up the status


# ---- local mock of the APIM MCP endpoint (behaviour the policies are designed to produce) ----
READER, NOROLE = "reader-token", "norole-token"
PO, SUPPLIER = "4500000001", "17300001"


class MockApim(BaseHTTPRequestHandler):
    calls = 0

    def log_message(self, *args):
        pass

    def _send(self, status, body=b"", ctype="application/json", headers=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path.startswith("/sap-po-tools/"):
            return self._send(405, b"These SAP tools are read-only.", "text/plain")
        if self.headers.get("Authorization") != f"Bearer {READER}":
            return self._send(401, b'{"statusCode": 401}')
        MockApim.calls += 1
        if MockApim.calls > 30:
            return self._send(429, b'{"statusCode": 429}')
        method, rid = body.get("method"), body.get("id")
        if rid is None:
            return self._send(202)
        if method == "initialize":
            return self._send(200, json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": "2025-03-26"}}).encode(),
                              headers={"Mcp-Session-Id": "s1"})
        if self.headers.get("Mcp-Session-Id") != "s1":
            return self._send(400, b"missing session")
        if method == "tools/list":
            tools = [{"name": n, "inputSchema": {"type": "object"}} for n in TOOLS]
            return self._send(200, json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"tools": tools}}).encode())
        name, args = body["params"]["name"], body["params"]["arguments"]
        if name == "get_purchase_order_status" and re.fullmatch(r"[0-9]{1,10}", args.get("purchaseOrder", "")):
            text, err = json.dumps({"d": {"PurchaseOrder": args["purchaseOrder"], "ReleaseIsNotCompleted": False}}), False
        elif name == "list_supplier_purchase_orders" and re.fullmatch(r"[A-Za-z0-9]{1,10}", args.get("supplier", "")) \
                and 1 <= int(args.get("top", 10)) <= 20:
            rows = [{"PurchaseOrder": str(4500000000 + i)} for i in range(int(args.get("top", 10)))]
            text, err = json.dumps({"d": {"results": rows}}), False
        elif name in TOOLS:
            text, err = "400 Bad Request", True
        else:
            msg = {"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": "Unknown tool"}}
            return self._send(200, json.dumps(msg).encode())
        msg = {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": text}], "isError": err}}
        return self._send(200, f"event: message\ndata: {json.dumps(msg)}\n\n".encode(), "text/event-stream")


class RuntimeScriptAgainstMockTests(unittest.TestCase):
    def test_runtime_script_against_mock(self):  # UT-11
        MockApim.calls = 0
        server = ThreadingHTTPServer(("127.0.0.1", 0), MockApim)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            settings = {"mcp": {"serverUrl": f"http://127.0.0.1:{server.server_port}/sap-po-mcp/mcp"},
                        "test": {"purchaseOrder": PO, "supplier": SUPPLIER}}
            with contextlib.redirect_stdout(io.StringIO()):
                results = run_mcp_tests.run(settings, READER, NOROLE, rate_limit=True)
        finally:
            server.shutdown()
            server.server_close()
        statuses = {tc: status for tc, status, _ in results}
        self.assertEqual([tc for tc, s in statuses.items() if s != "PASS"], [], results)
        self.assertEqual(len(statuses), 11)


if __name__ == "__main__":
    unittest.main(verbosity=1)
