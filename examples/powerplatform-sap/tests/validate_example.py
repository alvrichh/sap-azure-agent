#!/usr/bin/env python3
"""Static validation of the Power Platform + SAP test case (no Power Platform, SAP or Azure needed).

  python3 examples/powerplatform-sap/tests/validate_example.py
  python3 examples/powerplatform-sap/tests/validate_example.py --strict   # also fail on unfilled <placeholders>
Requires PyYAML for the pipeline check.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
STRICT = "--strict" in sys.argv
PLACEHOLDER = re.compile(r"<[a-z][a-z0-9@.\-]*(?:-[a-z0-9@.]+)*>")
# Operation IDs published in the connector references (Microsoft Learn); deprecated 'Invoke' deliberately excluded
OPERATIONS = {
    "/providers/Microsoft.PowerApps/apis/shared_saperp": {"CallRfcJson", "CallRfcJsonV3", "CloseSession", "CreateSession",
                                                          "ReadTableVersion3", "AttachmentReconstruct", "RunDiagnostics"},
    "/providers/Microsoft.PowerApps/apis/shared_sapodata": {"AdHocBulkRequest", "AdHocRequest", "CreateEntry", "DeleteEntry",
                                                            "GetEntityData", "GetEntry", "UpdateEntry"},
}
READ_ONLY_OPERATIONS = {"CallRfcJson", "CallRfcJsonV3", "GetEntityData", "GetEntry", "ReadTableVersion3", "RunDiagnostics"}
READ_ONLY_RFCS = {"BAPI_MATERIAL_AVAILABILITY", "STFC_CONNECTION"}
SECRET_PATTERNS = [re.compile(p, re.I) for p in [r'"(Password|User|Username|Passwd)"\s*:', r"client-secret", r"password-secret",
                                                 r"[?&]sig=", r"-----BEGIN", r"AccountKey="]]
TO_VERIFY = [
    "UV-01 cloud flow JSON layout (OpenApiConnection host keys, connectionReferences block, environment variable parameters named '<display name> (<schema name>)')",
    "UV-02 CallRfcJson 'rfcInputs' nesting and the output shape (RETURN as an object, AV_QTY_PLT as a number)",
    "UV-03 Power Apps (V2) trigger input names text, text_1, text_2 and the 'Respond to a PowerApp or flow' schema",
    "UV-04 SAP OData connector output for API_BUSINESS_PARTNER through APIM (OData v2 d.results; v4 value handled too) and 'top' as a number",
    "UV-05 'SAP system' JSON for SNC with Microsoft Entra ID (Kerberos): UseSnc 'Yes', SncQop values; test the connection in the test environment",
]

errors, warnings, passed = [], [], []


def check(ok, test_id, message):
    (passed if ok else errors).append(f"{test_id}: {message}")


def walk(actions):
    for name, a in actions.items():
        yield name, a
        yield from walk(a.get("actions", {}))
        yield from walk(a.get("else", {}).get("actions", {}))


# ST-01 parse
bad = []
for f in ROOT.rglob("*"):
    try:
        if f.suffix == ".json":
            json.loads(f.read_text())
        elif f.suffix in (".yml", ".yaml"):
            yaml.safe_load(f.read_text())
    except Exception as exc:
        bad.append(f"{f.relative_to(ROOT)}: {exc}")
check(not bad, "ST-01", "JSON and YAML files parse" + (f" — {bad}" if bad else ""))

solution = json.loads((ROOT / "solution/solution.json").read_text())
refs = {r["logicalName"]: r for r in solution["connectionReferences"]}
env_vars = {v["schemaName"]: v for v in solution["environmentVariables"]}
flows = {p: json.loads((ROOT / "solution" / p).read_text())["properties"] for p in solution["flows"]}
prefix = solution["publisher"]["prefix"] + "_"

# ST-02 naming and connection references
problems = [n for n in [*refs, *env_vars] if not n.startswith(prefix)]
for path, props in flows.items():
    for name, cr in props["connectionReferences"].items():
        logical = cr["connection"]["connectionReferenceLogicalName"]
        if logical not in refs:
            problems.append(f"{path}: unknown connection reference {logical}")
        elif not refs[logical]["connectorId"].endswith("/" + cr["api"]["name"]):
            problems.append(f"{path}: {logical} points to another connector")
check(not problems, "ST-02", f"flows use only the solution's connection references; names use the publisher prefix '{prefix}'" + (f" — {problems}" if problems else ""))

# ST-03 published operation IDs, matching the connection's connector
problems = []
for path, props in flows.items():
    api_by_conn = {n: refs[cr["connection"]["connectionReferenceLogicalName"]]["connectorId"] for n, cr in props["connectionReferences"].items()}
    for name, a in walk(props["definition"]["actions"]):
        if a.get("type") == "OpenApiConnection":
            host = a["inputs"]["host"]
            if host["apiId"] != api_by_conn.get(host["connectionName"]):
                problems.append(f"{path}/{name}: apiId differs from its connection reference")
            if host["operationId"] not in OPERATIONS.get(host["apiId"], set()):
                problems.append(f"{path}/{name}: operation {host['operationId']} not in the connector reference")
check(not problems, "ST-03", "connector actions use operation IDs published in the SAP ERP / SAP OData connector references (no deprecated actions)" + (f" — {problems}" if problems else ""))

# ST-04 environment variables used by flows are declared, with the designer naming '<display> (<schema>)'
problems = []
for path, props in flows.items():
    text = json.dumps(props["definition"])
    for pname, p in props["definition"]["parameters"].items():
        if pname.startswith("$"):
            continue
        schema = p.get("metadata", {}).get("schemaName")
        if schema not in env_vars or pname != f"{env_vars[schema]['displayName']} ({schema})":
            problems.append(f"{path}: parameter {pname!r}")
    for used in re.findall(r"parameters\('([^'$][^']*)'\)", text):
        if used not in props["definition"]["parameters"]:
            problems.append(f"{path}: uses undeclared parameter {used!r}")
check(not problems, "ST-04", "environment variables used by the flows are declared in the solution" + (f" — {problems}" if problems else ""))

# ST-05 deployment settings for every environment match the solution exactly
problems = []
for env in ("dev", "test", "prod"):
    s = json.loads((ROOT / f"deployment/settings.{env}.json").read_text())
    if {v["SchemaName"] for v in s["EnvironmentVariables"]} != set(env_vars):
        problems.append(f"{env}: environment variables differ")
    if {(c["LogicalName"], c["ConnectorId"]) for c in s["ConnectionReferences"]} != {(r["logicalName"], r["connectorId"]) for r in refs.values()}:
        problems.append(f"{env}: connection references differ")
    if any(not re.fullmatch(r"<[a-z-]+>|[0-9a-f]{32}", c["ConnectionId"]) for c in s["ConnectionReferences"]):
        problems.append(f"{env}: ConnectionId must be a placeholder or a 32-hex connection ID")
    for v in s["EnvironmentVariables"]:
        if env_vars[v["SchemaName"]]["type"] == "Number" and not re.fullmatch(r"\d+", v["Value"]):
            problems.append(f"{env}: {v['SchemaName']} is not a number")
check(not problems, "ST-05", "deployment settings for dev, test and prod cover exactly the solution's environment variables and connection references" + (f" — {problems}" if problems else ""))

# ST-06 no credentials anywhere (SAP credentials belong to each user's connection)
hits = []
for f in ROOT.rglob("*"):
    if f.is_file() and f.suffix in {".json", ".yml", ".md"}:
        hits += [f"{f.relative_to(ROOT)}: {p.pattern}" for p in SECRET_PATTERNS if p.search(f.read_text())]
CREDENTIAL_KEYS = re.compile(r"pass|user|secret|token|key$|credential", re.I)
for env in ("dev", "test", "prod"):
    for v in json.loads((ROOT / f"deployment/settings.{env}.json").read_text())["EnvironmentVariables"]:
        try:
            value = json.loads(v["Value"])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            hits += [f"settings.{env}.json {v['SchemaName']}: {k}" for k in value if CREDENTIAL_KEYS.search(k)]
check(not hits, "ST-06", "no credentials or secrets in flows, settings, pipeline or docs" + (f" — {hits}" if hits else ""))

# ST-07 robustness: validation before SAP, Try/Catch, retries, every exit answers the app with the same schema
problems = []
for path, props in flows.items():
    acts = props["definition"]["actions"]
    if set(acts.get("Catch", {}).get("runAfter", {}).get("Try", [])) != {"Failed", "TimedOut"}:
        problems.append(f"{path}: Catch must run on Failed/TimedOut")
    if acts.get("Try", {}).get("runAfter") != {"Validate_input": ["Succeeded"]}:
        problems.append(f"{path}: SAP is called only after Validate_input")
    responses = [a for _, a in walk(acts) if a.get("type") == "Response"]
    schemas = {json.dumps(a["inputs"]["schema"], sort_keys=True) for a in responses}
    if len(schemas) != 1 or any(a.get("kind") != "PowerApp" for a in responses) or len(responses) < 3:
        problems.append(f"{path}: responses to Power Apps must share one schema")
    for name, a in walk(acts):
        if a.get("type") == "OpenApiConnection" and a.get("retryPolicy", {}).get("count", 0) < 1:
            problems.append(f"{path}/{name}: no retry policy")
check(not problems, "ST-07", "input validated before SAP; Try/Catch; retries; every exit answers Power Apps with the same schema" + (f" — {problems}" if problems else ""))

# ST-08 read-only test case: no write operations, only allow-listed RFCs; OData $select and capped $top
problems = []
for path, props in flows.items():
    for name, a in walk(props["definition"]["actions"]):
        if a.get("type") != "OpenApiConnection":
            continue
        op, p = a["inputs"]["host"]["operationId"], a["inputs"]["parameters"]
        if op not in READ_ONLY_OPERATIONS:
            problems.append(f"{name}: {op} writes")
        if "rfcName" in p and p["rfcName"] not in READ_ONLY_RFCS:
            problems.append(f"{name}: RFC {p['rfcName']} not allow-listed")
        if op == "GetEntityData" and (not p.get("select") or "min(" not in str(p.get("top"))):
            problems.append(f"{name}: needs $select and a capped $top")
check(not problems, "ST-08", "read-only: allow-listed RFCs, no create/update/delete; OData query with $select and capped $top" + (f" — {problems}" if problems else ""))

# ST-09 ALM pipeline: OIDC only, managed import with each environment's settings, prod gated after test
wf = yaml.safe_load((ROOT / "pipelines/powerplatform-alm.yml").read_text())
text = (ROOT / "pipelines/powerplatform-alm.yml").read_text()
jobs = wf["jobs"]
runs = "\n".join(s.get("run", "") for j in jobs.values() for s in j.get("steps", []))
auths = re.findall(r"pac auth create[^\n]*", runs)
imports = {name: next((s["run"] for s in j["steps"] if "pac solution import" in s.get("run", "")), "") for name, j in jobs.items()}
check(wf["permissions"].get("id-token") == "write" and auths and all("--githubFederated" in a for a in auths)
      and "secrets." not in text and "settings.test.json" in imports.get("deploy-test", "") and "settings.prod.json" in imports.get("deploy-prod", "")
      and "--packagetype Managed" in runs and jobs["deploy-prod"].get("needs") == "deploy-test"
      and jobs["deploy-prod"].get("environment") == "powerplatform-prod", "ST-09",
      f"ALM: {len(auths)} pac sign-ins all with GitHub federation (no secrets); managed solution imported with each environment's settings; prod gated after test")

# ST-10 unit tests
ut = subprocess.run([sys.executable, str(ROOT / "tests/test_units.py")], capture_output=True, text=True)
ran = next((line for line in ut.stderr.splitlines() if line.startswith("Ran ")), "?")
check(ut.returncode == 0, "ST-10", f"unit tests pass ({ran})" + ("" if ut.returncode == 0 else f"\n{ut.stderr[-1500:]}"))

pending = []
for f in [*ROOT.glob("deployment/*.json"), ROOT / "config/settings.example.json"]:
    pending += [f"{f.name}: {ph}" for ph in sorted(set(PLACEHOLDER.findall(f.read_text())))]
if pending:
    (errors if STRICT else warnings).append(f"PH-01: {len(pending)} placeholders still to fill before deployment")

print(f"Passed: {len(passed)}")
for p in passed:
    print(f"  PASS {p}")
for w in warnings:
    print(f"  WARN {w}")
print("  TO VERIFY in the Power Automate designer / against SAP (not confirmed by published docs):")
for v in TO_VERIFY:
    print(f"       {v}")
for e in errors:
    print(f"  FAIL {e}")
if pending and (STRICT or "--verbose" in sys.argv):
    for p in pending:
        print(f"       {p}")
sys.exit(1 if errors else 0)
