#!/usr/bin/env python3
"""Static validation of the SAP OData + API Management test case (no Azure or SAP needed).

  python3 examples/sap-odata-apim/tests/validate_example.py
  python3 examples/sap-odata-apim/tests/validate_example.py --strict   # also fail on unfilled <placeholders>
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
TEMPLATE = REPO / "templates/bicep/apim-sap-odata.bicep"
POLICIES = {"s4hana": ROOT / "apim/policy-s4hana.xml", "sandbox": ROOT / "apim/policy-sandbox.xml"}
PLACEHOLDER = re.compile(r"<[a-z][a-z0-9@.\-]*(?:-[a-z0-9@.]+)*>")
SECRET_PATTERNS = [re.compile(p, re.I) for p in
                   [r"AccountKey=", r"[?&]sig=", r"client_secret\s*[=:]", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
                    r"Bearer\s+eyJ", r'password="[^{"]']]

errors, warnings, passed = [], [], []


def check(ok, test_id, message):
    (passed if ok else errors).append(f"{test_id}: {message}")


def elements(dom, tag):
    return dom.getElementsByTagName(tag)


def first_inbound_policy(dom):
    inbound = elements(dom, "inbound")[0]
    names = [n.tagName for n in inbound.childNodes if n.nodeType == n.ELEMENT_NODE]
    return [n for n in names if n != "base"]


# Named values declared by the Bicep template, with the mode in which they exist
bicep = TEMPLATE.read_text()
named_values = {}
for m in re.finditer(r"resource \w+ 'Microsoft\.ApiManagement/service/namedValues@[^']+' = (if \(([^)]*)\) )?\{(.*?)\n\}", bicep, re.S):
    condition, body = m.group(2), m.group(3)
    name = re.search(r"displayName: '([^']+)'", body).group(1)
    modes = {"s4hana", "sandbox"} if not condition else ({"s4hana"} if condition.strip() == "isS4" else {"sandbox"})
    named_values[name] = {"modes": modes, "keyVault": "keyVault:" in body, "inlineValue": re.search(r"\n\s*value:", body) is not None}
backend_names = set(re.findall(r"backends@[^']+' = \{\s*parent: apim\s*name: '([^']+)'", bicep))

# ST-01 policies are valid XML
doms = {}
for mode, path in POLICIES.items():
    try:
        doms[mode] = xml.dom.minidom.parse(str(path))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"ST-01: {path.name} is not valid XML ({exc})")
check(len(doms) == 2, "ST-01", "both policies are valid XML")

for mode, dom in doms.items():
    text = POLICIES[mode].read_text()
    order = first_inbound_policy(dom)

    # ST-02 caller authentication is the first inbound policy
    check(order[:1] == ["validate-azure-ad-token"], "ST-02", f"[{mode}] Entra ID token validation runs first in inbound ({order[:3]})")

    # ST-03 audience and required roles are enforced
    aud = [a.firstChild.nodeValue for a in elements(dom, "audience")]
    roles = [v.firstChild.nodeValue for c in elements(dom, "claim") if c.getAttribute("name") == "roles" for v in elements(c, "value")]
    check(aud == ["{{entra-api-audience}}"] and {"BusinessPartner.Read", "BusinessPartner.Write"} <= set(roles),
          "ST-03", f"[{mode}] audience from named value and roles claim required")

    # ST-04 throttling per caller
    rl = elements(dom, "rate-limit-by-key")
    check(bool(rl) and "oid" in rl[0].getAttribute("counter-key"), "ST-04", f"[{mode}] rate limit per caller (oid)")

    # ST-05 the caller's bearer token is not forwarded to SAP
    deleted = [h.getAttribute("name").lower() for h in elements(dom, "set-header")
               if h.getAttribute("exists-action") == "delete" and h.parentNode.tagName == "inbound"]
    check("authorization" in deleted, "ST-05", f"[{mode}] client Authorization header removed before calling SAP")

    # ST-06 traffic goes to the TLS-validated backend defined in Bicep
    backend = [b.getAttribute("backend-id") for b in elements(dom, "set-backend-service")]
    check(backend and set(backend) <= backend_names, "ST-06", f"[{mode}] backend {backend} is defined in the Bicep template")

    # ST-07 every named value used exists in Bicep for this mode
    used = set(re.findall(r"\{\{([^}]+)\}\}", text))
    missing = {u for u in used if u not in named_values or mode not in named_values[u]["modes"]}
    check(not missing, "ST-07", f"[{mode}] all named values exist for this mode" + (f" — missing {missing}" if missing else ""))

    # ST-08 credentials only via named values
    basic = elements(dom, "authentication-basic")
    creds_ok = all(b.getAttribute("password").startswith("{{") and b.getAttribute("username").startswith("{{") for b in basic)
    apikey = [h for h in elements(dom, "set-header") if h.getAttribute("name").lower() == "apikey"]
    apikey_ok = all(h.getElementsByTagName("value")[0].firstChild.nodeValue.startswith("{{") for h in apikey)
    check(creds_ok and apikey_ok, "ST-08", f"[{mode}] SAP credentials come only from named values")

    # ST-09 SAP cookies never reach the client
    out_deleted = [h.getAttribute("name").lower() for h in elements(dom, "set-header")
                   if h.getAttribute("exists-action") == "delete" and h.parentNode.tagName == "outbound"]
    check("set-cookie" in out_deleted, "ST-09", f"[{mode}] Set-Cookie removed in outbound")

# ST-10 s4hana: CSRF fetch for writes, and write authorization before the backend call
s4 = doms.get("s4hana")
if s4:
    sends = elements(s4, "send-request")
    csrf = sends and elements(sends[0], "set-method")[0].firstChild.nodeValue == "HEAD" and any(
        h.getAttribute("name") == "X-CSRF-Token" and h.getElementsByTagName("value")[0].firstChild.nodeValue == "Fetch"
        for h in elements(sends[0], "set-header"))
    conds = [w.getAttribute("condition") for w in elements(s4, "when")]
    check(bool(csrf) and any("BusinessPartner.Write" in c for c in conds), "ST-10",
          "[s4hana] CSRF token fetched for writes and Write role required for non-GET")
    order = first_inbound_policy(s4)
    check(order.index("choose") < order.index("set-backend-service"), "ST-11",
          "[s4hana] write authorization happens before routing to SAP")

# ST-12 sandbox is read-only
sb = doms.get("sandbox")
if sb:
    statuses = [s.getAttribute("code") for s in elements(sb, "set-status")]
    check("405" in statuses, "ST-12", "[sandbox] non-GET requests return 405")

# ST-13 secrets are Key Vault-backed named values
secret_nv = {"sap-password", "sap-apikey"}
bad = [n for n in secret_nv if not named_values.get(n, {}).get("keyVault") or named_values[n]["inlineValue"]]
check(not bad, "ST-13", "SAP secrets are Key Vault references, never inline values" + (f" — {bad}" if bad else ""))

# ST-14 backend validates TLS
check("validateCertificateChain: true" in bicep and "validateCertificateName: true" in bicep, "ST-14",
      "backend validates the SAP TLS certificate chain and name")

# ST-15 parameter files reference existing templates and match the template's modes
for p in sorted((ROOT / "bicep").glob("*.bicepparam")):
    t = p.read_text()
    m = re.search(r"using\s+'([^']+)'", t)
    mode = re.search(r"param authMode = '([^']+)'", t)
    target = (p.parent / m.group(1)).resolve() if m else None
    check(bool(target and target.exists() and mode and mode.group(1) in POLICIES), "ST-15",
          f"{p.name} → {m.group(1) if m else '?'} (authMode={mode.group(1) if mode else '?'})")

# ST-16 the policy deployment loads both policy files
api_policy = (ROOT / "bicep/api-policy.bicep").read_text()
check(all(f"loadTextContent('../apim/{p.name}')" in api_policy for p in POLICIES.values()), "ST-16",
      "api-policy.bicep loads both policy files")

# ST-17 runtime test script is valid bash and covers TC-01…TC-11
script = ROOT / "tests/run_api_tests.sh"
syntax = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
ids = set(re.findall(r"\bTC-(\d\d)\b", script.read_text()))
check(syntax.returncode == 0 and {f"{i:02d}" for i in range(1, 12)} <= ids, "ST-17",
      "run_api_tests.sh is valid bash and covers TC-01…TC-11" + (f" — {syntax.stderr.strip()}" if syntax.returncode else ""))

# ST-18 settings and examples JSON parse; no secrets anywhere
bad_json = []
for f in ROOT.rglob("*.json"):
    try:
        json.loads(f.read_text())
    except json.JSONDecodeError as exc:
        bad_json.append(f"{f.name}: {exc}")
hits = []
for f in [*ROOT.rglob("*"), TEMPLATE]:
    if f.is_file() and f.suffix in {".json", ".bicep", ".bicepparam", ".xml", ".sh", ".md"}:
        hits += [f"{f.name}: {p.pattern}" for p in SECRET_PATTERNS if p.search(f.read_text())]
check(not bad_json and not hits, "ST-18", "JSON parses and no secrets or tokens in any file"
      + (f" — {bad_json + hits}" if bad_json or hits else ""))

# Placeholders (deployment readiness)
pending = []
for f in [ROOT / "config/settings.example.json", *ROOT.glob("bicep/*.bicepparam")]:
    pending += [f"{f.name}: {ph}" for ph in sorted(set(PLACEHOLDER.findall(f.read_text())))]
if pending:
    (errors if STRICT else warnings).append(f"PH-01: {len(pending)} placeholders still to fill before deployment")

print(f"Passed: {len(passed)}")
for p in passed:
    print(f"  PASS {p}")
for w in warnings:
    print(f"  WARN {w}")
for e in errors:
    print(f"  FAIL {e}")
if pending and (STRICT or "--verbose" in sys.argv):
    for p in pending:
        print(f"       {p}")
sys.exit(1 if errors else 0)
