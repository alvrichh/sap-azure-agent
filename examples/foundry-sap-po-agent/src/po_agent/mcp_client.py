"""Minimal MCP (streamable HTTP, JSON-RPC 2.0) client used by the runtime tests. Standard library only."""
import json
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2025-03-26"


def parse_mcp_body(content_type, body):
    """Return the JSON-RPC messages in a response that is either application/json or text/event-stream."""
    text = body.decode("utf-8") if isinstance(body, bytes) else body
    if not text.strip():
        return []
    if "text/event-stream" in (content_type or ""):
        messages, data = [], []
        for line in text.splitlines() + [""]:
            if line.startswith("data:"):
                data.append(line[5:].lstrip())
            elif line == "" and data:
                messages.append(json.loads("\n".join(data)))
                data = []
        return messages
    parsed = json.loads(text)
    return parsed if isinstance(parsed, list) else [parsed]


class McpResponse:
    def __init__(self, status, headers, messages):
        self.status = status
        self.headers = headers
        self.messages = messages

    def result(self, request_id):
        for m in self.messages:
            if m.get("id") == request_id:
                return m
        return None


class McpClient:
    """One MCP session against a server URL, with an optional bearer token."""

    def __init__(self, url, token=None, timeout=60):
        self.url = url
        self.token = token
        self.timeout = timeout
        self.session_id = None
        self._next_id = 1

    def _post(self, payload):
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": PROTOCOL_VERSION}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body, status, hdrs = resp.read(), resp.status, dict(resp.headers)
        except urllib.error.HTTPError as err:
            body, status, hdrs = err.read(), err.code, dict(err.headers or {})
        messages = []
        if 200 <= status < 300:
            messages = parse_mcp_body(hdrs.get("Content-Type", ""), body)
        return McpResponse(status, hdrs, messages)

    def request(self, method, params=None):
        request_id = self._next_id
        self._next_id += 1
        resp = self._post({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        return resp, resp.result(request_id)

    def notify(self, method, params=None):
        return self._post({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def initialize(self):
        resp, msg = self.request("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                                "clientInfo": {"name": "sap-po-agent-tests", "version": "1.0"}})
        if resp.status == 200:
            self.session_id = next((v for k, v in resp.headers.items() if k.lower() == "mcp-session-id"), None)
            self.notify("notifications/initialized")
        return resp, msg

    def list_tools(self):
        return self.request("tools/list")

    def call_tool(self, name, arguments):
        return self.request("tools/call", {"name": name, "arguments": arguments})


def tool_result_text(msg):
    """Concatenated text content of a tools/call result, and whether the server flagged it as an error."""
    result = (msg or {}).get("result") or {}
    text = "".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
    return text, bool(result.get("isError")) or "error" in (msg or {})
