#!/usr/bin/env python3
"""Static validation of the Logic Apps Standard + SAP IDoc test case (no Azure or SAP needed).

  python3 examples/logicapps-sap-idoc/tests/validate_example.py
  python3 examples/logicapps-sap-idoc/tests/validate_example.py --strict   # also fail on unfilled <placeholders>
Requires lxml and jsonschema for the unit tests.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
APP = ROOT / "logicapp"
TEMPLATE = REPO / "templates/bicep/logicapp-standard-sap.bicep"
STRICT = "--strict" in sys.argv
PLACEHOLDER = re.compile(r"<[a-z][a-z0-9@.\-]*(?:-[a-z0-9@.]+)*>")
# Operation IDs published in the SAP built-in connector reference (Microsoft Learn)
SAP_OPERATIONS = {"closeSession", "createSession", "bapiCallMethod", "bapiCommit", "bapiRollback", "confirmTransactionId",
                  "getIDocList", "getIDocStatus", "sendIDoc", "addRfcToTransaction", "callRfc", "commitRfcTransaction",
                  "createRfcTransaction", "getRfcTransaction", "getSchemaV2", "readTable", "respondToSapServer",
                  "runDiagnostics", "sendExceptionToSapServer", "SapTrigger"}
# Required SapTrigger parameters (connector reference)
TRIGGER_REQUIRED = {"idocFormat", "DegreeOfParallelism", "GatewayHost", "GatewayService", "ProgramId"}
SECRET_PATTERNS = [re.compile(p, re.I) for p in [r"AccountKey=[A-Za-z0-9+/]{20,}", r'"password"\s*:\s*"(?!@appsetting)[^"]+"',
                                                 r"[?&]sig=[A-Za-z0-9%]{10,}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
                                                 r"SharedAccessKey=[A-Za-z0-9+/=]{20,}"]]
TO_VERIFY = [
    "UV-01 serviceProviderId '/serviceProviders/sap' and the connection parameter keys in connections.json",
    "UV-02 sendIDoc payload key 'body' (the reference lists idocFormat, tId, confirmTid, allowUnreleasedSegmentV2 but not the payload key)",
    "UV-03 SapPlainXml layout: <ORDERS05><IDOC BEGIN=\"1\"><EDI_DC40 SEGMENT=\"1\">… accepted by sendIDoc; packet layout produced by SapTrigger",
    "UV-04 getIDocList output 'iDocNumbers' (list or string) and getIDocStatus output 'iDocStatus'",
    "UV-05 respondToSapServer 'body' for a tRFC IDoc call (no response parameters: empty body assumed)",
    "UV-06 Compose/Select keys starting with '@' (xml() attributes) accepted as-is; otherwise escape them as '@@SEGMENT'",
    "UV-07 SapTrigger output key 'content' (reference) vs 'Content' (scenario article) in triggerBody()",
]

errors, warnings, passed = [], [], []


def check(ok, test_id, message):
    (passed if ok else errors).append(f"{test_id}: {message}")


def walk_actions(actions):
    for name, action in actions.items():
        yield name, action
        yield from walk_actions(action.get("actions", {}))
        yield from walk_actions(action.get("else", {}).get("actions", {}))


def schema_strict(schema, path="$"):
    """Every object closed and fully typed, every string constrained by a pattern."""
    problems = []
    if schema.get("type") == "object":
        if schema.get("additionalProperties") is not False:
            problems.append(f"{path}: additionalProperties must be false")
        if not set(schema.get("required", [])) <= set(schema.get("properties", {})):
            problems.append(f"{path}: required lists unknown properties")
        for name, sub in schema.get("properties", {}).items():
            problems += schema_strict(sub, f"{path}.{name}")
    elif schema.get("type") == "array":
        if "maxItems" not in schema:
            problems.append(f"{path}: arrays need maxItems")
        problems += schema_strict(schema["items"], f"{path}[]")
    elif schema.get("type") == "string" and "pattern" not in schema:
        problems.append(f"{path}: string without pattern")
    return problems


# ST-01 JSON parses
bad = []
for f in ROOT.rglob("*.json"):
    try:
        json.loads(f.read_text())
    except json.JSONDecodeError as exc:
        bad.append(f"{f.relative_to(ROOT)}: {exc}")
check(not bad, "ST-01", "all JSON files parse" + (f" — {bad}" if bad else ""))

connections = json.loads((APP / "connections.json").read_text())["serviceProviderConnections"]
parameters = json.loads((APP / "parameters.json").read_text())
bicep = TEMPLATE.read_text()
param_file = (ROOT / "bicep/logicapp.dev.bicepparam").read_text()
base_settings = set(re.findall(r"\{ name: '([A-Za-z_]+)', value:", bicep))
extra_block = re.search(r"param additionalAppSettings = \{(.*?)\n\}", param_file, re.S)
extra_settings = set(re.findall(r"^\s*([A-Z][A-Z0-9_]+):", extra_block.group(1), re.M)) if extra_block else set()
workflows = {p.parent.name: json.loads(p.read_text()) for p in APP.glob("*/workflow.json")}
wf_text = {name: (APP / name / "workflow.json").read_text() for name in workflows}

# ST-02 SAP credentials only from app settings
sap = connections["sap"]["parameterValues"]
check(all(str(sap[k]).startswith("@appsetting(") for k in ("userName", "password", "appServerHost", "systemNumber", "client")),
      "ST-02", "SAP connection values come from app settings (no literals)")

# ST-03 every app setting referenced exists in the template or in the parameter file's additionalAppSettings
used = set(re.findall(r"@appsetting\('([^']+)'\)", (APP / "connections.json").read_text() + (APP / "parameters.json").read_text()))
missing = used - base_settings - extra_settings
check(not missing, "ST-03", f"{len(used)} app settings referenced are deployed by Bicep" + (f" — missing {sorted(missing)}" if missing else ""))

# ST-04 every parameters('x') used by a workflow is defined in parameters.json
refs = {m for text in wf_text.values() for m in re.findall(r"parameters\('([^']+)'\)", text)}
check(refs <= set(parameters), "ST-04", f"workflow parameters {sorted(refs)} defined in parameters.json" + (f" — missing {refs - set(parameters)}" if not refs <= set(parameters) else ""))

# ST-05 password in Key Vault; platform settings for the SAP built-in connector, including stateful mode
required = {"kind: 'functionapp,workflowapp'": "Standard logic app kind", "use32BitWorkerProcess: false": "64-bit (x64 NCo)",
            "virtualNetworkSubnetId: integrationSubnetId": "VNet integration", "vnetRouteAllEnabled: true": "all traffic via VNet",
            "vnetPrivatePortsCount: vnetPrivatePortsCount": "VNet private ports", "httpsOnly: true": "HTTPS only",
            "ftpsState: 'Disabled'": "FTP disabled", "4633458b-17de-408a-b874-0445c86b69e6": "Key Vault Secrets User"}
missing = [v for k, v in required.items() if k not in bicep]
kv_ref = re.search(r"name: 'SAP_PASSWORD', value: '@Microsoft\.KeyVault\(VaultName=", bicep)
ports = re.search(r"param vnetPrivatePortsCount = (\d+)", param_file)
check(not missing and kv_ref and ports and int(ports.group(1)) >= 2, "ST-05",
      "Key Vault reference for SAP_PASSWORD, 64-bit, VNet integration, private ports = 2 (stateful mode for trigger/TID)"
      + (f" — missing {missing}" if missing else "") + ("" if ports and int(ports.group(1)) >= 2 else " — vnetPrivatePortsCount < 2"))

# ST-06 every ServiceProvider trigger/action uses a defined connection and a published SAP operation
problems = []
for wf_name, wf in workflows.items():
    d = wf["definition"]
    for name, op in [*d["triggers"].items(), *walk_actions(d["actions"])]:
        if op.get("type") == "ServiceProvider":
            cfg = op["inputs"]["serviceProviderConfiguration"]
            if cfg["connectionName"] not in connections:
                problems.append(f"{wf_name}/{name}: unknown connection")
            elif cfg["serviceProviderId"] != connections[cfg["connectionName"]]["serviceProvider"]["id"]:
                problems.append(f"{wf_name}/{name}: serviceProviderId differs from connection")
            if cfg["operationId"] not in SAP_OPERATIONS:
                problems.append(f"{wf_name}/{name}: unknown operation {cfg['operationId']}")
check(not problems, "ST-06", "SAP trigger and actions use defined connections and published operation IDs" + (f" — {problems}" if problems else ""))

# ST-07 SAP trigger: required parameters present; gateway and program ID from settings, not hard-coded
receive = workflows["wf-receive-customer-idoc"]["definition"]
trig = receive["triggers"]["When_a_message_is_received"]["inputs"]["parameters"]
check(TRIGGER_REQUIRED <= set(trig) and all(trig[k].startswith("@parameters(") for k in ("GatewayHost", "GatewayService", "ProgramId"))
      and re.search(r"^\s*SAP_PROGRAM_ID: '[A-Z0-9_]{1,64}'$", param_file, re.M) is not None,
      "ST-07", "SAP trigger has idocFormat, parallelism, gateway host/service and program ID (from settings; ID uppercase, consistent case)")

# ST-08 receive: Respond to SAP server first; data errors never rejected back to SAP after acknowledging
acts = receive["actions"]
first = [n for n, a in acts.items() if a.get("runAfter") == {}]
no_reject = not any(a.get("inputs", {}).get("serviceProviderConfiguration", {}).get("operationId") == "sendExceptionToSapServer"
                    for _, a in walk_actions(acts))
check(first == ["Respond_to_SAP_server"] and no_reject, "ST-08",
      "inbound: 'Respond to SAP server' runs first (frees the SAP connection); no exception sent to SAP for application errors")

# ST-09 send: explicit TID, confirm only after a successful send, retries on the transfer
send = workflows["wf-send-sales-order-idoc"]["definition"]["actions"]
tr = send.get("Try", {}).get("actions", {})
s, c = tr.get("Send_ORDERS05_to_SAP", {}), tr.get("Confirm_transaction_ID", {})
check(s.get("inputs", {}).get("parameters", {}).get("confirmTid") == "false"
      and s["inputs"]["parameters"].get("tId") == c.get("inputs", {}).get("parameters", {}).get("tId") == "@variables('idocTransactionId')"
      and c.get("runAfter") == {"Send_ORDERS05_to_SAP": ["Succeeded"]} and s.get("retryPolicy", {}).get("count", 0) >= 1
      and "guid()" in send["Initialize_IDoc_transaction_ID"]["inputs"]["variables"][0]["value"],
      "ST-09", "outbound: one TID per order (caller-supplied or guid()), confirmTid=false, explicit confirm after success, retries")

# ST-10 HTTP contracts: strict schemas with validation; every path answers
problems = []
for name in ("wf-send-sales-order-idoc", "wf-idoc-status"):
    t = workflows[name]["definition"]["triggers"]["When_a_HTTP_request_is_received"]
    problems += [f"{name}: {p}" for p in schema_strict(t["inputs"]["schema"])]
    if t.get("operationOptions") != "EnableSchemaValidation":
        problems.append(f"{name}: schema validation off")
resp = {n for wf in workflows.values() for n, a in walk_actions(wf["definition"]["actions"]) if a.get("type") == "Response"}
if not {"Respond_202", "Respond_502", "Respond_200"} <= resp:
    problems.append(f"responses {sorted(resp)}")
if set(send.get("Catch", {}).get("runAfter", {}).get("Try", [])) != {"Failed", "TimedOut"}:
    problems.append("send: Catch must run on Failed/TimedOut")
check(not problems, "ST-10", "strict request schemas (closed objects, patterns, maxItems) with validation; 202/200/502 responses" + (f" — {problems}" if problems else ""))

# ST-11 workflow kinds: the TID and trigger workflows keep run history (audit, resubmit)
check(workflows["wf-send-sales-order-idoc"]["kind"] == workflows["wf-receive-customer-idoc"]["kind"] == "Stateful", "ST-11",
      "send and receive workflows are Stateful (run history for audit and resubmission)")

# ST-12 action timeout below the synchronous HTTP response window
host = json.loads((APP / "host.json").read_text())
timeout = host["extensions"]["workflow"]["settings"]["Runtime.FlowRunRetryableActionJobCallback.ActionJobExecutionTimeout"]
h, m, sec = (int(x) for x in timeout.split(":"))
check(h * 3600 + m * 60 + sec <= 230, "ST-12", f"SAP action timeout {timeout} ≤ 230 s; SAP inbound processing must be 'Trigger by background program'")

# ST-13 downstream call without secrets: managed identity
http = [a for wf in workflows.values() for _, a in walk_actions(wf["definition"]["actions"]) if a.get("type") == "Http"]
check(http and all(a["inputs"].get("authentication", {}).get("type") == "ManagedServiceIdentity" for a in http), "ST-13",
      "downstream HTTP calls authenticate with the logic app's managed identity")

# ST-14 SAP libraries not committed; parameter file references the template
dlls = list((APP / "lib").rglob("*.dll"))
using = re.search(r"using\s+'([^']+)'", param_file).group(1)
check(not dlls and "lib/builtinOperationSdks" in (REPO / ".gitignore").read_text() and (ROOT / "bicep" / using).resolve() == TEMPLATE,
      "ST-14", "SAP NCo DLLs not in Git; parameter file references the Logic App Standard template")

# ST-15 no secrets
hits = []
for f in [*ROOT.rglob("*"), TEMPLATE]:
    if f.is_file() and f.suffix in {".json", ".bicep", ".bicepparam", ".md", ".xml", ".py"} and f.name != "validate_example.py":
        hits += [f"{f.name}: {p.pattern}" for p in SECRET_PATTERNS if p.search(f.read_text())]
check(not hits, "ST-15", "no secrets in any file" + (f" — {hits}" if hits else ""))

# ST-16 unit tests
ut = subprocess.run([sys.executable, str(ROOT / "tests/test_units.py")], capture_output=True, text=True)
ran = next((line for line in ut.stderr.splitlines() if line.startswith("Ran ")), "?")
check(ut.returncode == 0, "ST-16", f"unit tests pass ({ran})" + ("" if ut.returncode == 0 else f"\n{ut.stderr[-1500:]}"))

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
print("  TO VERIFY in the Logic Apps designer / against a real SAP system (not confirmed by published docs):")
for v in TO_VERIFY:
    print(f"       {v}")
for e in errors:
    print(f"  FAIL {e}")
if pending and (STRICT or "--verbose" in sys.argv):
    for p in pending:
        print(f"       {p}")
sys.exit(1 if errors else 0)
