#!/usr/bin/env python3
"""Static validation of the S/4HANA -> Fabric test case.

Runs without SAP or Azure. Checks that the configuration is internally consistent
and safe before anything is deployed:

  python3 examples/s4hana-to-fabric/tests/validate_example.py            # design checks
  python3 examples/s4hana-to-fabric/tests/validate_example.py --strict   # also fail on unfilled <placeholders>

Exit code 0 = all checks passed.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
STRICT = "--strict" in sys.argv

VALID_CONTEXTS = {"ABAP_CDS", "SAPI", "BW", "HANA"}
VALID_RUN_MODES = {"fullAndIncrementalLoad", "incrementalLoad", "fullLoad"}
PLACEHOLDER = re.compile(r"<[^<>\s][^<>]*>")
SECRET_PATTERNS = [
    re.compile(r"AccountKey=", re.I),
    re.compile(r"[?&]sig=", re.I),
    re.compile(r"client_secret", re.I),
    re.compile(r'"type"\s*:\s*"SecureString"', re.I),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]

errors, warnings, passed = [], [], []


def check(condition, test_id, message):
    (passed if condition else errors).append(f"{test_id}: {message}")


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


# ST-01 every JSON file parses
json_files = sorted(ROOT.rglob("*.json"))
bad = []
for f in json_files:
    try:
        json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        bad.append(f"{f.relative_to(ROOT)} ({exc})")
check(not bad, "ST-01", f"{len(json_files)} JSON files parse" + (f" — invalid: {bad}" if bad else ""))

objects = load("adf/sap-cdc-objects.json")
linked_service = load("adf/LS_SapCdc.json")
settings = load("config/settings.example.json")

# ST-02 control file fields
required = {"checkPointKey", "sapContext", "sapObjectName", "sapRunMode", "sapKeyColumns",
            "sapPartitions", "deltaContainer", "deltaFolder", "deltaKeyColumns"}
missing = [o.get("sapObjectName", "?") for o in objects if not required.issubset(o)]
check(not missing, "ST-02", "control file entries have all required fields" + (f" — missing in {missing}" if missing else ""))

# ST-03 valid contexts and run modes
bad = [o["sapObjectName"] for o in objects
       if not (o["sapContext"] in VALID_CONTEXTS or o["sapContext"].startswith("SLT~"))
       or o["sapRunMode"] not in VALID_RUN_MODES]
check(not bad, "ST-03", "ODP contexts and run modes are valid" + (f" — invalid: {bad}" if bad else ""))

# ST-04 unique checkpoint keys (one CDC state per object)
keys = [o["checkPointKey"] for o in objects]
check(len(keys) == len(set(keys)), "ST-04", "checkpoint keys are unique")

# ST-05 checkpoint key contains the object name (traceability)
bad = [o["checkPointKey"] for o in objects if o["sapObjectName"] not in o["checkPointKey"]]
check(not bad, "ST-05", "checkpoint keys contain the object name" + (f" — {bad}" if bad else ""))

# ST-06 incremental objects have key columns, and sink keys match source keys
bad = [o["sapObjectName"] for o in objects
       if o["sapRunMode"] != "fullLoad"
       and (not o["sapKeyColumns"] or set(o["sapKeyColumns"]) != set(o["deltaKeyColumns"]))]
check(not bad, "ST-06", "incremental objects define key columns and sink keys match" + (f" — {bad}" if bad else ""))

# ST-07 one target folder per object
folders = [f'{o["deltaContainer"]}/{o["deltaFolder"]}' for o in objects]
check(len(folders) == len(set(folders)), "ST-07", "each object writes to its own Delta folder")

# ST-08 partitions are well formed and don't overlap (same field, BT/EQ ranges)
def partition_problems(obj):
    problems, ranges = [], []
    for part in obj["sapPartitions"]:
        if not isinstance(part, list) or not part:
            problems.append("partition must be a non-empty list of conditions")
            continue
        for cond in part:
            if cond.get("sign") not in {"I", "E"} or "fieldName" not in cond or "low" not in cond:
                problems.append(f"malformed condition {cond}")
            if cond.get("option") == "BT" and "high" not in cond:
                problems.append(f"BT without high: {cond}")
            if cond.get("sign") == "I" and cond.get("option") in {"BT", "EQ"}:
                low = cond["low"]
                high = cond.get("high", low)
                if low > high:
                    problems.append(f"low > high in {cond}")
                ranges.append((cond["fieldName"], low, high))
    by_field = {}
    for field, low, high in ranges:
        by_field.setdefault(field, []).append((low, high))
    for field, rs in by_field.items():
        rs.sort()
        for (l1, h1), (l2, h2) in zip(rs, rs[1:]):
            if l2 <= h1:
                problems.append(f"overlapping partitions on {field}: {l1}-{h1} and {l2}-{h2}")
    return problems

bad = {o["sapObjectName"]: p for o in objects if (p := partition_problems(o))}
check(not bad, "ST-08", "source partitions are well formed and non-overlapping" + (f" — {bad}" if bad else ""))

# ST-09 subscriber name: uppercase, <= 32 chars, consistent with settings
sub = linked_service["properties"]["typeProperties"]["subscriberName"]
check(sub == sub.upper() and len(sub) <= 32 and sub == settings["dataFactory"]["subscriberName"],
      "ST-09", f"subscriber name '{sub}' is uppercase, <= 32 characters and matches settings")

# ST-10 SAP password comes from Key Vault, never inline
pwd = linked_service["properties"]["typeProperties"]["password"]
check(pwd.get("type") == "AzureKeyVaultSecret"
      and pwd.get("secretName") == settings["sap"]["keyVaultSecretName"],
      "ST-10", "SAP password is a Key Vault reference matching settings")

# ST-11 linked service uses the self-hosted IR named in settings
ir = linked_service["properties"]["connectVia"]["referenceName"]
check(ir == settings["dataFactory"]["selfHostedIrName"], "ST-11", f"linked service uses self-hosted IR '{ir}'")

# ST-12 one Fabric shortcut per Delta folder, in Tables, pointing at the right subpath
shortcuts = {p.stem: json.loads(p.read_text()) for p in (ROOT / "fabric/shortcuts").glob("*.json")}
expected = {f'/{o["deltaContainer"]}/{o["deltaFolder"]}' for o in objects}
actual = {s["target"]["adlsGen2"]["subpath"] for s in shortcuts.values()}
bad_path = [n for n, s in shortcuts.items() if s["path"] != "Tables"]
check(expected == actual and not bad_path, "ST-12",
      "every Delta folder has a Tables shortcut" + (f" — missing {expected - actual}, extra {actual - expected}, not in Tables {bad_path}" if (expected != actual or bad_path) else ""))

# ST-13 shortcut names match the tables used in the SQL scripts
sql = "\n".join(p.read_text() for p in (ROOT / "sql").glob("*.sql"))
used = set(re.findall(r"dbo\.(\w+)", sql))
check(used <= set(shortcuts), "ST-13", "SQL scripts only reference tables that have a shortcut"
      + (f" — unknown: {used - set(shortcuts)}" if not used <= set(shortcuts) else ""))

# ST-14 bicepparam files point to existing templates
for p in (ROOT / "bicep").glob("*.bicepparam"):
    m = re.search(r"using\s+'([^']+)'", p.read_text())
    target = (p.parent / m.group(1)).resolve() if m else None
    check(bool(target and target.exists()), "ST-14", f"{p.name} references an existing template ({m.group(1) if m else 'no using'})")

# ST-15 no secrets anywhere in the example
hits = []
for f in ROOT.rglob("*"):
    if f.is_file() and f.suffix in {".json", ".bicepparam", ".sql", ".md", ".py"} and f.name != "validate_example.py":
        text = f.read_text(encoding="utf-8")
        hits += [f"{f.relative_to(ROOT)}: {pat.pattern}" for pat in SECRET_PATTERNS if pat.search(text)]
check(not hits, "ST-15", "no secrets or inline credentials" + (f" — {hits}" if hits else ""))

# ST-16 the pipeline template passes every control-file field the data flow needs
pipeline = json.loads((REPO / "templates/adf/pipelines/sap-cdc-incremental-to-delta.json").read_text())
flow = pipeline["properties"]["activities"][1]["typeProperties"]["activities"][0]["typeProperties"]
passed_params = set(flow["dataflow"]["parameters"])
needed = {"sapContext", "sapObjectName", "sapRunMode", "sapKeyColumns", "sapPartitions",
          "deltaContainer", "deltaFolder", "deltaKeyColumns"}
check(needed <= passed_params and "customizedCheckpointKey" in flow["continuationSettings"],
      "ST-16", "pipeline template passes all object parameters and a per-object checkpoint key")

# Placeholders (deployment readiness)
pending = []
for f in [ROOT / "config/settings.example.json", ROOT / "adf/LS_SapCdc.json", *ROOT.glob("bicep/*.bicepparam"),
          *ROOT.glob("fabric/shortcuts/*.json")]:
    for ph in sorted(set(PLACEHOLDER.findall(f.read_text()))):
        pending.append(f"{f.relative_to(ROOT)}: {ph}")
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
