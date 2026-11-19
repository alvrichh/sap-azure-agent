#!/usr/bin/env python3
"""Static validation of the Foundry SAP purchase order agent test case (no Azure, Foundry or SAP needed).

  python3 examples/foundry-sap-po-agent/tests/validate_example.py
  python3 examples/foundry-sap-po-agent/tests/validate_example.py --strict   # also fail on unfilled <placeholders>
"""
import json
import re
import subprocess
import sys
import xml.dom.minidom
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
STRICT = "--strict" in sys.argv
sys.path.insert(0, str(ROOT / "src"))

from po_agent.tool_config import ToolConfigError, build_mcp_tool_kwargs  # noqa: E402

APIM_TEMPLATE = REPO / "templates/bicep/apim-sap-odata.bicep"
MCP_TEMPLATE = REPO / "templates/bicep/apim-mcp-server.bicep"
MCP_POLICY = REPO / "templates/apim/mcp-server-policy.xml"
API_POLICIES = {"sandbox": ROOT / "apim/policy-po-tools-sandbox.xml", "s4hana": ROOT / "apim/policy-po-tools-s4hana.xml"}
OPENAPI = ROOT / "apim/po-tools.openapi.json"
TOOLS_BICEP = ROOT / "bicep/po-tools.bicep"
SETTINGS = ROOT / "config/settings.example.json"
PLACEHOLDER = re.compile(r"<[a-z][a-z0-9@.\-]*(?:-[a-z0-9@.]+)*>")
SECRET_PATTERNS = [re.compile(p, re.I) for p in
                   [r"AccountKey=", r"[?&]sig=", r"client_secret\s*[=:]", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
                    r"Bearer\s+eyJ", r'password="[^{"]', r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"]]

errors, passed = [], []


def check(ok, test_id, message):
    (passed if ok else errors).append(f"{test_id}: {message}")


def inbound_order(dom):
    inbound = dom.getElementsByTagName("inbound")[0]
    return [n.tagName for n in inbound.childNodes if n.nodeType == n.ELEMENT_NODE and n.tagName != "base"]


def text_of(dom, tag):
    return [e.firstChild.nodeValue for e in dom.getElementsByTagName(tag) if e.firstChild]


# ST-01 policies are valid XML
doms = {}
for name, path in {**API_POLICIES, "mcp": MCP_POLICY}.items():
    try:
        doms[name] = xml.dom.minidom.parse(str(path))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"ST-01: {path.name} is not valid XML ({exc})")
check(len(doms) == 3, "ST-01", "API policies (sandbox, s4hana) and the MCP-server policy are valid XML")

openapi = json.loads(OPENAPI.read_text())
ops = {op["operationId"]: (path, method, op) for path, item in openapi["paths"].items() for method, op in item.items()}
params = {p["name"]: p for _, _, op in ops.values() for p in op.get("parameters", [])}

for name, dom in doms.items():
    text = re.sub(r"<!--.*?-->", "", (API_POLICIES.get(name) or MCP_POLICY).read_text(), flags=re.S)
    role = "__APP_ROLE__" if name == "mcp" else "PurchaseOrder.Read"
    # ST-02 caller authentication first, audience and role enforced
    roles = [v for c in dom.getElementsByTagName("claim") if c.getAttribute("name") == "roles" for v in text_of(c, "value")]
    check(inbound_order(dom)[:1] == ["validate-azure-ad-token"] and text_of(dom, "audience") == ["{{entra-api-audience}}"]
          and roles == [role], "ST-02", f"[{name}] Entra ID token validated first, audience and role {role} enforced")
    # ST-03 per-caller rate limit
    rl = dom.getElementsByTagName("rate-limit-by-key")
    check(bool(rl) and "oid" in rl[0].getAttribute("counter-key"), "ST-03", f"[{name}] rate limit per caller (oid)")
    # ST-09 never read the response body (breaks MCP streaming); applies to every policy on the MCP path
    check("Response.Body" not in text, "ST-09", f"[{name}] policy doesn't read context.Response.Body")

for mode, path in API_POLICIES.items():
    dom, text = doms.get(mode), path.read_text()
    if not dom:
        continue
    # ST-04 read-only
    check('Method != "GET"' in text.replace("&quot;", '"') and "405" in text, "ST-04", f"[{mode}] non-GET requests get 405")
    # ST-05 input validation matches the OpenAPI patterns
    unescaped = text.replace("&quot;", '"')
    for pname in ("purchaseOrder", "supplier"):
        pattern = params[pname]["schema"]["pattern"]
        check(f'"{pattern}"' in unescaped, "ST-05", f"[{mode}] policy validates {pname} with the OpenAPI pattern {pattern}")
    # ST-06 $top capped like the OpenAPI maximum
    top_max = params["top"]["schema"]["maximum"]
    check(f'> {top_max}' in unescaped.replace("&gt;", ">") and "< 1" in unescaped.replace("&lt;", "<"),
          "ST-06", f"[{mode}] top limited to 1..{top_max}")
    # ST-07 every operation rewritten with $select, no copied client query parameters
    rewrites = dom.getElementsByTagName("rewrite-uri")
    check(len(rewrites) == len(ops) and all("$select=" in r.getAttribute("template") and
                                            r.getAttribute("copy-unmatched-params") == "false" for r in rewrites),
          "ST-07", f"[{mode}] {len(rewrites)} rewrites, all with $select and copy-unmatched-params=false")
    check(all(f'"{op_id}"' in unescaped for op_id in ops), "ST-07", f"[{mode}] policy maps every operationId")
    # ST-08 client token never reaches SAP; SAP session headers removed
    deleted = {h.getAttribute("name") for h in dom.getElementsByTagName("set-header") if h.getAttribute("exists-action") == "delete"}
    check({"Authorization", "Set-Cookie", "X-CSRF-Token"} <= deleted, "ST-08", f"[{mode}] Authorization, Set-Cookie and X-CSRF-Token removed")
check(not any(h.getAttribute("name") == "Authorization" for h in doms["mcp"].getElementsByTagName("set-header")),
      "ST-08", "[mcp] MCP policy keeps the Authorization header for the backing API")

# ST-10 named values used by each policy exist in the APIM template for that mode
bicep = APIM_TEMPLATE.read_text()
named = {}
for m in re.finditer(r"resource \w+ 'Microsoft\.ApiManagement/service/namedValues@[^']+' = (if \(([^)]*)\) )?\{(.*?)\n\}", bicep, re.S):
    cond, body = m.group(2), m.group(3)
    nv = re.search(r"displayName: '([^']+)'", body).group(1)
    named[nv] = {"s4hana", "sandbox"} if not cond else ({"s4hana"} if cond.strip() == "isS4" else {"sandbox"})
for mode, path in {**API_POLICIES, "mcp": MCP_POLICY}.items():
    used = set(re.findall(r"\{\{([a-z0-9-]+)\}\}", path.read_text()))
    modes = {"sandbox", "s4hana"} if mode == "mcp" else {mode}
    missing = [u for u in used if not modes <= named.get(u, set())]
    check(not missing, "ST-10", f"[{mode}] named values {sorted(used)} exist in apim-sap-odata.bicep" + (f" (missing {missing})" if missing else ""))
check("backend-id=\"sap-odata-backend\"" in API_POLICIES["sandbox"].read_text() and "'sap-odata-backend'" in bicep,
      "ST-10", "backend sap-odata-backend exists in the APIM template")

# ST-11 OpenAPI is agent-friendly
raw = OPENAPI.read_text()
check(openapi["openapi"].startswith("3.0"), "ST-11", f"OpenAPI {openapi['openapi']} (Foundry OpenAPI tools need 3.0)")
check(not re.search(r'"(anyOf|allOf|oneOf)"', raw) and not re.search(r'"type"\s*:\s*\[', raw), "ST-11",
      "no anyOf/allOf/oneOf or multi-type parameters (cause 'invalid tool schema' in Foundry)")
check(all(m == "get" for _, m, _ in ops.values()), "ST-11", "every operation is GET (read-only tools)")
check(all(p.get("description") and p["schema"].get("type") for p in params.values()) and
      all(len(op.get("description", "")) >= 60 for _, _, op in ops.values()), "ST-11", "operations and parameters have descriptions and types")

# ST-12 tools: bicep ↔ OpenAPI ↔ settings ↔ runtime tests
tools_bicep = TOOLS_BICEP.read_text()
tool_defs = re.findall(r"name: '([a-z_]+)'\s*operation: '([a-z-]+)'\s*description: '([^']+)'", tools_bicep)
settings = json.loads(SETTINGS.read_text())
check(tool_defs and all(op in ops for _, op, _ in tool_defs), "ST-12", f"tools map to OpenAPI operations {[o for _, o, _ in tool_defs]}")
check(sorted(n for n, _, _ in tool_defs) == sorted(settings["mcp"]["tools"]), "ST-12", "tool names match settings mcp.tools")
check(all(len(d) >= 80 and "Read-only" in d for _, _, d in tool_defs), "ST-12", "tool descriptions are specific and say read-only")
rt = (ROOT / "tests/run_mcp_tests.py").read_text()
check(all(f'"{n}"' in rt for n, _, _ in tool_defs), "ST-12", "runtime tests expect exactly these tools")

# ST-13 MCP template follows the documented resource model
mcp_t = MCP_TEMPLATE.read_text()
versions = re.findall(r"'Microsoft\.ApiManagement/service/apis(?:/tools|/policies)?@([0-9-]+(?:-preview)?)'", mcp_t)
check(versions and all(v >= "2025-09-01" for v in versions), "ST-13", f"MCP resources pinned to API version >= 2025-09-01-preview ({sorted(set(versions))})")
check("type: 'mcp'" in mcp_t and "resourceId('Microsoft.ApiManagement/service/apis/operations'" in mcp_t,
      "ST-13", "server is apis type 'mcp'; tool operationId is the backing operation's resource ID")
check("loadTextContent('../../../templates/apim/mcp-server-policy.xml'), '__APP_ROLE__'" in tools_bicep.replace("\n", ""),
      "ST-13", "example injects its app role into the MCP policy template")

# ST-14 agent tool definition is safe
try:
    kw = build_mcp_tool_kwargs(settings)
    ok, detail = True, f"allowed_tools {kw['allowed_tools']}, require_approval {kw['require_approval']}"
except ToolConfigError as exc:
    ok, detail = False, str(exc)
check(ok, "ST-14", f"Foundry MCP tool definition passes the safety rules ({detail})")
check(settings["entra"]["apiAudience"] in (ROOT / "bicep/apim.sandbox.dev.bicepparam").read_text(), "ST-14",
      "audience in settings matches the APIM parameters")

# ST-15 instructions and evaluation set
instr = (ROOT / "agent/instructions.md").read_text().lower()
check(all(k in instr for k in ("read-only", "never guess", "data, not instructions", "fiori")), "ST-15",
      "instructions: read-only, no guessing, SAP text is untrusted, refuse writes")
cases = json.loads((ROOT / "eval/cases.json").read_text())["cases"]
known = set(settings["mcp"]["tools"])
check(all(set(c.get("expectTools", [])) <= known for c in cases)
      and any(not c.get("expectTools") and c.get("expectAnswerContains") for c in cases)
      and sum(1 for c in cases if not c.get("expectTools")) >= 2, "ST-15",
      f"{len(cases)} evaluation cases, known tools only, including refusal and no-tool cases")

# ST-16 parameter files reference existing files and the purchase order service
for pf in sorted((ROOT / "bicep").glob("*.bicepparam")):
    target = re.search(r"using '([^']+)'", pf.read_text()).group(1)
    check((pf.parent / target).resolve().exists(), "ST-16", f"{pf.name} uses existing {target}")
for pf in sorted((ROOT / "bicep").glob("apim.*.bicepparam")):
    check("/API_PURCHASEORDER_PROCESS_SRV'" in pf.read_text(), "ST-16", f"{pf.name} points at API_PURCHASEORDER_PROCESS_SRV")
for ref in re.findall(r"loadTextContent\('([^']+)'\)", tools_bicep):
    check((TOOLS_BICEP.parent / ref).resolve().exists(), "ST-16", f"po-tools.bicep loads existing {ref}")

# ST-17 Python compiles; runtime script covers TC-01…TC-11
for py in sorted(ROOT.rglob("*.py")):
    try:
        compile(py.read_text(), str(py), "exec")
        compiled = True
    except SyntaxError:
        compiled = False
    check(compiled, "ST-17", f"{py.relative_to(ROOT)} compiles")
check(all(f'"TC-{i:02d}"' in rt for i in range(1, 12)), "ST-17", "runtime script covers TC-01…TC-11")

# ST-18 JSON parses, no secrets or tokens anywhere in the test case or new templates
files = [p for p in ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts
         and p != Path(__file__).resolve()] + [MCP_TEMPLATE, MCP_POLICY]
for p in files:
    content = p.read_text(errors="ignore")
    if p.suffix == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            errors.append(f"ST-18: {p.name} isn't valid JSON ({exc})")
    hits = [pat.pattern for pat in SECRET_PATTERNS if pat.search(content)]
    check(not hits, "ST-18", f"{p.relative_to(REPO)} has no secrets" + (f" (matched {hits})" if hits else ""))
    if STRICT and p.suffix in (".json", ".bicepparam") and p.name != "cases.json":
        holes = PLACEHOLDER.findall(content)
        check(not holes, "ST-19", f"{p.name} has no unfilled placeholders" + (f" ({holes})" if holes else ""))

# UT unit tests
ut = subprocess.run([sys.executable, str(ROOT / "tests/test_units.py")], capture_output=True, text=True)
summary = (ut.stderr.strip().splitlines() or ["no output"])
ran = next((line for line in summary if line.startswith("Ran ")), "")
check(ut.returncode == 0, "UT", f"unit tests: {ran} {summary[-1]}")

for line in passed if "--verbose" in sys.argv else []:
    print("  PASS", line)
for line in errors:
    print("  FAIL", line)
print(f"Passed: {len(passed)}, failed: {len(errors)}")
sys.exit(1 if errors else 0)
