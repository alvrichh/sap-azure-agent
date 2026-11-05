#!/usr/bin/env python3
"""Static validation of the SAP -> Snowflake (Azure Data Factory) test case. No Azure, SAP or Snowflake needed.

  python3 examples/adf-sap-to-snowflake/tests/validate_example.py
  python3 examples/adf-sap-to-snowflake/tests/validate_example.py --strict   # also fail on unfilled <placeholders>
Requires duckdb for the unit tests.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
STRICT = "--strict" in sys.argv
PLACEHOLDER = re.compile(r"<[a-z][a-z0-9@.\-]*(?:-[a-z0-9@.]+)*>")
SECRET_PATTERNS = [re.compile(p, re.I) for p in [r"AccountKey=", r"[?&]sig=", r'"type"\s*:\s*"SecureString"',
                                                 r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"\bPASSWORD\s*=\s*'", r"sasUri"]]
READER = "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1"
TO_VERIFY = [
    "UV-01 Snowflake SQL in snowflake/01-setup.sql (storage integration, TYPE = SERVICE user, TRUNCATE privilege) follows Snowflake docs, not Microsoft Learn",
    "UV-02 Lookup on Snowflake V2 accepts a source with only 'query' (exportSettings documented as required for Copy, not for Lookup)",
    "UV-03 SAP Table connector writes DATS fields as 'YYYYMMDD' strings and packed numbers as decimals in Parquet",
    "UV-04 empty rfcTableOptions ('') is accepted as 'no filter'",
    "UV-05 staged COPY with storageIntegration: the connector's temporary stage in SAP_LANDING reads snowflake-staging through ADF_SAP_AZURE_INT",
]

errors, warnings, passed = [], [], []


def check(ok, test_id, message):
    (passed if ok else errors).append(f"{test_id}: {message}")


def load(path):
    return json.loads(Path(path).read_text())


# ST-01 JSON parses
bad = []
for f in ROOT.rglob("*.json"):
    try:
        json.loads(f.read_text())
    except json.JSONDecodeError as exc:
        bad.append(f"{f.relative_to(ROOT)}: {exc}")
check(not bad, "ST-01", "all JSON files parse" + (f" — {bad}" if bad else ""))

# ST-02 control file and DDL generated from objects.json (identifiers and filters validated there)
gen = subprocess.run([sys.executable, str(ROOT / "tools/generate.py"), "--check"], capture_output=True, text=True)
check(gen.returncode == 0, "ST-02", "control file and DDL are generated from adf/objects.json and up to date"
      + ("" if gen.returncode == 0 else f" — {(gen.stdout + gen.stderr).strip()[-300:]}"))

pipeline = load(ROOT / "adf/PL_Sap_To_Snowflake.json")["properties"]
setup = (ROOT / "snowflake/01-setup.sql").read_text()
ls = load(ROOT / "adf/LS_SnowflakeV2.json")["properties"]
staging_ls = load(ROOT / "adf/LS_BlobStaging.json")["properties"]
control = load(ROOT / "adf/sap-snowflake-objects.json")
spec = load(ROOT / "adf/objects.json")
bicep = (ROOT / "bicep/snowflake-staging.bicep").read_text()
bicep_param = (ROOT / "bicep/snowflake-staging.dev.bicepparam").read_text()


def walk(activities):
    for a in activities:
        yield a
        tp = a.get("typeProperties", {})
        for key in ("activities", "ifTrueActivities", "ifFalseActivities"):
            yield from walk(tp.get(key, []))


acts = {a["name"]: a for a in walk(pipeline["activities"])}

# ST-03 every dataset / linked service the pipeline uses exists, with the parameters it passes
definitions = {}
for f in [*(REPO / "templates/adf").rglob("*.json"), *(ROOT / "adf").glob("LS_*.json")]:
    d = json.loads(f.read_text())
    if isinstance(d, dict) and "name" in d:
        definitions[d["name"]] = d["properties"]
problems = []
for a in acts.values():
    refs = [*a.get("inputs", []), *a.get("outputs", []), a.get("typeProperties", {}).get("dataset"), a.get("linkedServiceName"),
            a.get("typeProperties", {}).get("stagingSettings", {}).get("linkedServiceName")]
    for r in filter(None, refs):
        target = definitions.get(r["referenceName"])
        if target is None:
            problems.append(f"{a['name']}: {r['referenceName']} not found")
        elif set(r.get("parameters", {})) != set(target.get("parameters", {})):
            problems.append(f"{a['name']}: parameters {sorted(r.get('parameters', {}))} != {sorted(target.get('parameters', {}))} of {r['referenceName']}")
check(not problems, "ST-03", "datasets and linked services referenced by the pipeline exist with matching parameters" + (f" — {problems}" if problems else ""))

# ST-04 Snowflake linked service: key pair from Key Vault, names consistent with the Snowflake setup
tp = ls["typeProperties"]
names_ok = all(re.search(pattern, setup) for pattern in [
    rf"CREATE DATABASE IF NOT EXISTS {tp['database']}\b", rf"CREATE WAREHOUSE IF NOT EXISTS {tp['warehouse']}\b",
    rf"CREATE ROLE IF NOT EXISTS {tp['role']}\b", rf"CREATE USER IF NOT EXISTS {tp['user']}\b",
    rf"CREATE SCHEMA IF NOT EXISTS {tp['database']}\.{tp['schema']}\b", rf"GRANT CREATE STAGE ON SCHEMA {tp['database']}\.{tp['schema']} "])
check(ls["type"] == "SnowflakeV2" and tp["authenticationType"] == "KeyPair" and "password" not in tp
      and all(tp[k]["type"] == "AzureKeyVaultSecret" for k in ("privateKey", "privateKeyPassphrase"))
      and names_ok and tp["schema"] == spec["landingSchema"], "ST-04",
      "SnowflakeV2 linked service: key pair from Key Vault; database/warehouse/role/user/schema exist in 01-setup.sql; session schema = landing (CREATE STAGE)")

# ST-05 storage integration and staging container consistent across pipeline, Snowflake and Bicep
copy = acts["CopyAdlsToSnowflakeLanding"]["typeProperties"]
integration = copy["sink"]["importSettings"].get("storageIntegration", "")
container = re.search(r"param stagingContainerName = '([^']+)'", bicep_param).group(1)
check(copy.get("enableStaging") is True and re.search(rf"CREATE STORAGE INTEGRATION IF NOT EXISTS {integration}\b", setup)
      and re.search(rf"GRANT USAGE ON INTEGRATION {integration} TO ROLE {tp['role']}", setup)
      and f"/{container}/'" in setup and copy["stagingSettings"]["path"] == container, "ST-05",
      f"staged COPY through storage integration {integration}; container '{container}' is the same in Bicep, Snowflake and the pipeline")

# ST-06 no SAS: staging with managed identity; Snowflake gets read-only access to the staging container only
stp = staging_ls["typeProperties"]
check(staging_ls["type"] == "AzureBlobStorage" and set(stp) == {"serviceEndpoint", "accountKind"}
      and READER in bicep and "scope: staging" in bicep and "Contributor" not in bicep.split("var storageBlobDataReader")[1],
      "ST-06", "staging linked service uses the factory managed identity (no key/SAS); Snowflake app has Storage Blob Data Reader on the container only")

# ST-07 least privilege and key-pair only in Snowflake
grants = re.findall(r"GRANT (.+?) ON (.+?) TO ROLE ADF_SAP_LOADER", setup)
too_much = [g for g in grants if re.search(r"\b(ALL|OWNERSHIP|DELETE|CREATE TABLE|MODIFY)\b", g[0])]
core_truncate = [g for g in grants if "TRUNCATE" in g[0] and spec["targetSchema"] in g[1]]
check(not too_much and not core_truncate and "TYPE = SERVICE" in setup and "RSA_PUBLIC_KEY" in setup
      and not re.search(r"\bPASSWORD\b", setup), "ST-07",
      f"loader role has {len(grants)} narrow grants (no ALL/OWNERSHIP/DELETE, TRUNCATE only on landing); service user is key-pair only (TYPE = SERVICE, no password)"
      + (f" — too broad: {too_much}" if too_much else ""))

# ST-08 pipeline safety: one run at a time, retries, reconciliation gates the MERGE
if_tp = acts["IfRowCountsMatch"]["typeProperties"]
check(pipeline.get("concurrency") == 1 and all(acts[n]["policy"]["retry"] >= 1 for n in ("CopySapToAdls", "CopyAdlsToSnowflakeLanding"))
      and [a["type"] for a in if_tp["ifTrueActivities"]] == ["Script"] and [a["type"] for a in if_tp["ifFalseActivities"]] == ["Fail"]
      and "rowsCopied" in if_tp["expression"]["value"] and "ROW_COUNT" in if_tp["expression"]["value"], "ST-08",
      "concurrency 1, retries on both copies, MERGE only when SAP rows = Snowflake landing rows, otherwise Fail")

# ST-09 Snowflake V2 (1.0): one statement per script block, no script parameters
stmts = [o["mergeSql"] for o in control] + [o["countSql"] for o in control]
scripts = [s for a in acts.values() if a["type"] == "Script" for s in a["typeProperties"]["scripts"]]
check(all(";" not in s for s in stmts) and all("parameters" not in s for s in scripts)
      and all(s["type"] == "NonQuery" for s in scripts), "ST-09",
      "single-statement script blocks without script parameters (supported by Snowflake V2 1.0 and 1.1)")

# ST-10 SAP extraction: fields and filter come from the control file; every target column is extracted
copy_sap = acts["CopySapToAdls"]["typeProperties"]["source"]
fields_ok = all(o["sapFields"].split(", ") == [c["name"] for c in next(s for s in spec["objects"] if s["sapTable"] == o["sapTable"])["columns"]]
                for o in control)
check(copy_sap["type"] == "SapTableSource" and copy_sap["rfcTableFields"]["value"] == "@item().sapFields"
      and copy_sap["rfcTableOptions"]["value"] == "@item().sapFilter" and fields_ok, "ST-10",
      "SAP Table source reads exactly the declared fields with the declared filter (RFC_READ_TABLE projection)")

# ST-11 parameter files reference their templates
problems = []
for f in (ROOT / "bicep").glob("*.bicepparam"):
    target = (f.parent / re.search(r"using\s+'([^']+)'", f.read_text()).group(1)).resolve()
    if not target.exists():
        problems.append(f.name)
check(not problems, "ST-11", "Bicep parameter files reference existing templates" + (f" — {problems}" if problems else ""))

# ST-12 no secrets
hits = []
for f in ROOT.rglob("*"):
    if f.is_file() and f.suffix in {".json", ".bicep", ".bicepparam", ".md", ".sql", ".py"} and f.name != "validate_example.py":
        hits += [f"{f.name}: {p.pattern}" for p in SECRET_PATTERNS if p.search(f.read_text())]
check(not hits, "ST-12", "no secrets in any file" + (f" — {hits}" if hits else ""))

# ST-13 unit tests (DuckDB runs the generated MERGE)
ut = subprocess.run([sys.executable, str(ROOT / "tests/test_units.py")], capture_output=True, text=True)
ran = next((line for line in ut.stderr.splitlines() if line.startswith("Ran ")), "?")
check(ut.returncode == 0, "ST-13", f"unit tests pass ({ran})" + ("" if ut.returncode == 0 else f"\n{ut.stderr[-1500:]}"))

pending = []
for f in [ROOT / "config/settings.example.json", *ROOT.glob("bicep/*.bicepparam"), *ROOT.glob("adf/LS_*.json"), ROOT / "snowflake/01-setup.sql"]:
    pending += [f"{f.name}: {ph}" for ph in sorted(set(PLACEHOLDER.findall(f.read_text())))]
if pending:
    (errors if STRICT else warnings).append(f"PH-01: {len(pending)} placeholders still to fill before deployment")

print(f"Passed: {len(passed)}")
for p in passed:
    print(f"  PASS {p}")
for w in warnings:
    print(f"  WARN {w}")
print("  TO VERIFY against real Snowflake / SAP / Data Factory (not confirmed by Microsoft Learn):")
for v in TO_VERIFY:
    print(f"       {v}")
for e in errors:
    print(f"  FAIL {e}")
if pending and (STRICT or "--verbose" in sys.argv):
    for p in pending:
        print(f"       {p}")
sys.exit(1 if errors else 0)
