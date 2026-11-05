#!/usr/bin/env python3
"""Static validation of the Logic Apps Standard + SAP RFC test case (no Azure or SAP needed).

  python3 examples/logicapps-sap-rfc/tests/validate_example.py
  python3 examples/logicapps-sap-rfc/tests/validate_example.py --strict   # also fail on unfilled <placeholders>
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
                  "runDiagnostics", "sendExceptionToSapServer"}
SECRET_PATTERNS = [re.compile(p, re.I) for p in [r"AccountKey=[A-Za-z0-9+/]{20,}", r'"password"\s*:\s*"(?!@appsetting)[^"]+"',
                                                 r"[?&]sig=[A-Za-z0-9%]{10,}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"]]
TO_VERIFY = [
    "UV-01 serviceProviderId '/serviceProviders/sap' (connections.json, workflow actions)",
    "UV-02 SAP connection parameter keys in connections.json (client, authType, userName, password, logonType, appServerHost, systemNumber, language)",
    "UV-03 callRfc input key 'body' and output shape body('<action>') = RFC response XML",
    "UV-04 trigger operationOptions 'EnableSchemaValidation' (designer: Settings > Schema Validation = On)",
]

errors, warnings, passed = [], [], []


def check(ok, test_id, message):
    (passed if ok else errors).append(f"{test_id}: {message}")


def walk_actions(actions):
    for name, action in actions.items():
        yield name, action
        yield from walk_actions(action.get("actions", {}))
        yield from walk_actions(action.get("else", {}).get("actions", {}))


# ST-01 JSON parses
bad = []
for f in ROOT.rglob("*.json"):
    try:
        json.loads(f.read_text())
    except json.JSONDecodeError as exc:
        bad.append(f"{f.relative_to(ROOT)}: {exc}")
check(not bad, "ST-01", "all JSON files parse" + (f" — {bad}" if bad else ""))

connections = json.loads((APP / "connections.json").read_text())["serviceProviderConnections"]
bicep = TEMPLATE.read_text()
bicep_settings = set(re.findall(r"\{ name: '([A-Za-z_]+)', value:", bicep))
workflows = {p.parent.name: json.loads(p.read_text()) for p in APP.glob("*/workflow.json")}

# ST-02 SAP credentials only from app settings
sap = connections["sap"]["parameterValues"]
check(all(str(sap[k]).startswith("@appsetting(") for k in ("userName", "password", "appServerHost", "systemNumber", "client")),
      "ST-02", "SAP connection values come from app settings (no literals)")

# ST-03 every app setting referenced exists in the Bicep template
used = set(re.findall(r"@appsetting\('([^']+)'\)", (APP / "connections.json").read_text()))
check(used <= bicep_settings, "ST-03", f"app settings {sorted(used)} are defined in Bicep" + (f" — missing {used - bicep_settings}" if not used <= bicep_settings else ""))

# ST-04 SAP password is a Key Vault reference, identity can read it
check(re.search(r"name: 'SAP_PASSWORD', value: '@Microsoft\.KeyVault\(VaultName=", bicep) is not None
      and "4633458b-17de-408a-b874-0445c86b69e6" in bicep, "ST-04",
      "SAP_PASSWORD is a Key Vault reference; app identity has Key Vault Secrets User")

# ST-05 platform settings required by the SAP built-in connector and for security
required = {"kind: 'functionapp,workflowapp'": "Standard logic app kind", "use32BitWorkerProcess: false": "64-bit (x64 NCo)",
            "virtualNetworkSubnetId: integrationSubnetId": "VNet integration", "vnetRouteAllEnabled: true": "all traffic via VNet",
            "httpsOnly: true": "HTTPS only", "ftpsState: 'Disabled'": "FTP disabled", "name: 'APP_KIND', value: 'workflowApp'": "APP_KIND",
            "name: 'FUNCTIONS_WORKER_RUNTIME', value: 'dotnet'": "worker runtime"}
missing = [v for k, v in required.items() if k not in bicep]
check(not missing, "ST-05", "Logic App platform settings for SAP built-in connector" + (f" — missing {missing}" if missing else ""))

# ST-06 every ServiceProvider action uses a defined connection and a published SAP operation
problems = []
for wf_name, wf in workflows.items():
    for name, action in walk_actions(wf["definition"]["actions"]):
        if action.get("type") == "ServiceProvider":
            cfg = action["inputs"]["serviceProviderConfiguration"]
            if cfg["connectionName"] not in connections:
                problems.append(f"{wf_name}/{name}: unknown connection {cfg['connectionName']}")
            if cfg["operationId"] not in SAP_OPERATIONS:
                problems.append(f"{wf_name}/{name}: unknown operation {cfg['operationId']}")
            if cfg["serviceProviderId"] != connections[cfg["connectionName"]]["serviceProvider"]["id"]:
                problems.append(f"{wf_name}/{name}: serviceProviderId differs from connection")
check(not problems, "ST-06", "SAP actions use defined connections and published operation IDs" + (f" — {problems}" if problems else ""))

# ST-07 strict input contract on the public trigger
wf = workflows["wf-material-availability"]["definition"]
trigger = wf["triggers"]["When_a_HTTP_request_is_received"]
schema = trigger["inputs"]["schema"]
check(schema.get("additionalProperties") is False and set(schema.get("required", [])) == set(schema["properties"])
      and all("pattern" in p for p in schema["properties"].values()) and trigger.get("operationOptions") == "EnableSchemaValidation",
      "ST-07", "trigger schema is strict (required, patterns, no extra fields) and validation is enabled")

# ST-08 error handling: Catch runs on Failed/TimedOut and answers the caller
catch = wf["actions"].get("Catch", {})
check(set(catch.get("runAfter", {}).get("Try", [])) >= {"Failed", "TimedOut"}
      and any(a.get("type") == "Response" for a in catch.get("actions", {}).values()),
      "ST-08", "Try/Catch: failures and timeouts return a controlled 502")

# ST-09 every path returns a response
responses = [n for n, a in walk_actions(wf["actions"]) if a.get("type") == "Response"]
check({"Respond_200", "Respond_422", "Respond_502"} <= set(responses), "ST-09", f"responses for success, SAP error and failure {sorted(responses)}")

# ST-10 retries on the SAP call; action timeout below the synchronous response limit
call = wf["actions"].get("Try", {}).get("actions", {}).get("Call_BAPI_MATERIAL_AVAILABILITY", {})
host = json.loads((APP / "host.json").read_text())
timeout = host["extensions"]["workflow"]["settings"]["Runtime.FlowRunRetryableActionJobCallback.ActionJobExecutionTimeout"]
h, m, s = (int(x) for x in timeout.split(":"))
check(call.get("retryPolicy", {}).get("count", 0) >= 1 and h * 3600 + m * 60 + s <= 230, "ST-10",
      f"SAP call has a retry policy; action timeout {timeout} ≤ 230 s (synchronous HTTP response window)")

# ST-11 SAP libraries are not committed
dlls = list((APP / "lib").rglob("*.dll"))
gitignore = (REPO / ".gitignore").read_text()
check(not dlls and "lib/builtinOperationSdks" in gitignore, "ST-11", "SAP NCo DLLs not in the repository and ignored by Git")

# ST-12 parameter file references the template
param = (ROOT / "bicep/logicapp.dev.bicepparam").read_text()
using = re.search(r"using\s+'([^']+)'", param).group(1)
check((ROOT / "bicep" / using).resolve() == TEMPLATE, "ST-12", "parameter file references the Logic App Standard template")

# ST-13 no secrets
hits = []
for f in [*ROOT.rglob("*"), TEMPLATE]:
    if f.is_file() and f.suffix in {".json", ".bicep", ".bicepparam", ".md", ".xml"}:
        hits += [f"{f.name}: {p.pattern}" for p in SECRET_PATTERNS if p.search(f.read_text())]
check(not hits, "ST-13", "no secrets in any file" + (f" — {hits}" if hits else ""))

# ST-14 unit tests
ut = subprocess.run([sys.executable, str(ROOT / "tests/test_units.py")], capture_output=True, text=True)
ran = next((line for line in ut.stderr.splitlines() if line.startswith("Ran ")), "?")
check(ut.returncode == 0, "ST-14", f"unit tests pass ({ran})" + ("" if ut.returncode == 0 else f"\n{ut.stderr[-1500:]}"))

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
print("  TO VERIFY in the Logic Apps designer (not confirmed by published docs):")
for v in TO_VERIFY:
    print(f"       {v}")
for e in errors:
    print(f"  FAIL {e}")
if pending and (STRICT or "--verbose" in sys.argv):
    for p in pending:
        print(f"       {p}")
sys.exit(1 if errors else 0)
