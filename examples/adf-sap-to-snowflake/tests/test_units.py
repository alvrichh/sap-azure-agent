"""Offline tests of the SAP -> Snowflake test case.

- The generated MERGE statements run for real in DuckDB, with a three-construct dialect shim
  (TRY_TO_DATE, CURRENT_TIMESTAMP(), qualified SET targets), against the generated DDL.
- The pipeline's dynamic content and the reconciliation condition are evaluated with sample activity outputs.
- The generator rejects identifiers or filters that could change the SQL.
Requires: duckdb.
"""
import copy
import importlib.util
import json
import re
import unittest
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("generate", ROOT / "tools/generate.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

SPEC = json.loads((ROOT / "adf/objects.json").read_text())
CONTROL = json.loads((ROOT / "adf/sap-snowflake-objects.json").read_text())
DDL = (ROOT / "snowflake/02-tables.sql").read_text()
PIPE = json.loads((ROOT / "adf/PL_Sap_To_Snowflake.json").read_text())["properties"]
OUTPUTS = json.loads((ROOT / "tests/fixtures/run-outputs.json").read_text())
FOREACH = next(a for a in PIPE["activities"] if a["type"] == "ForEach")["typeProperties"]
INNER = {a["name"]: a for a in FOREACH["activities"]}
IF = INNER["IfRowCountsMatch"]["typeProperties"]


def shim(sql: str) -> str:
    """Translate the three Snowflake constructs DuckDB spells differently; everything else runs as generated."""
    sql = re.sub(r"TRY_TO_DATE\((NULLIF\(S\.\w+, '00000000'\)), 'YYYYMMDD'\)", r"CAST(try_strptime(\1, '%Y%m%d') AS DATE)", sql)
    sql = sql.replace("CURRENT_TIMESTAMP()", "current_timestamp")
    return re.sub(r"UPDATE SET (.*?) WHEN NOT", lambda m: "UPDATE SET " + re.sub(r"\bT\.", "", m.group(1)) + " WHEN NOT", sql)


def database():
    con = duckdb.connect()
    con.execute(f"CREATE SCHEMA {SPEC['landingSchema']}; CREATE SCHEMA {SPEC['targetSchema']};")
    for stmt in DDL.split(";"):
        stmt = re.sub(r"--.*", "", stmt).strip()
        if stmt:
            con.execute(stmt.replace("TIMESTAMP_NTZ", "TIMESTAMP").replace("NUMBER(", "DECIMAL("))
    return con


def merge_text(obj, run_id):
    """Evaluate the Script activity text: @replace(item().mergeSql, '{runId}', pipeline().RunId)."""
    expr = IF["ifTrueActivities"][0]["typeProperties"]["scripts"][0]["text"]["value"]
    assert expr == "@replace(item().mergeSql, '{runId}', pipeline().RunId)", expr
    return obj["mergeSql"].replace("{runId}", run_id)


def by_table(name):
    return next(o for o in CONTROL if o["sapTable"] == name)


class MergeTests(unittest.TestCase):
    def test_ddl_creates_all_tables(self):  # UT-01
        con = database()
        tables = {r[0] + "." + r[1] for r in con.execute("SELECT table_schema, table_name FROM information_schema.tables").fetchall()}
        for o in CONTROL:
            self.assertIn(f"{o['landingSchema']}.{o['landingTable']}", tables)
            self.assertIn(o["targetTable"], tables)

    def test_first_load_dedups_and_converts_dates(self):  # UT-02
        con = database()
        con.execute("INSERT INTO SAP_LANDING.KNA1 VALUES ('0000100001','Contoso','ES','Madrid','0001','','20260105'),"
                    "('0000100002','Fabrikam','PT','Lisboa','0001','X','00000000'),"
                    "('0000100002','Fabrikam','PT','Lisboa','0001','X','00000000')")
        con.execute(shim(merge_text(by_table("KNA1"), "run-1")))
        rows = con.execute("SELECT KUNNR, ERDAT, LOEVM, _ADF_RUN_ID FROM SAP_CORE.KNA1 ORDER BY 1").fetchall()
        self.assertEqual([(r[0], str(r[1]), r[2], r[3]) for r in rows],
                         [("0000100001", "2026-01-05", "", "run-1"), ("0000100002", "None", "X", "run-1")])

    def test_second_load_updates_and_inserts(self):  # UT-03
        con = database()
        con.execute("INSERT INTO SAP_LANDING.VBAK VALUES ('0000004711','TA','1000','0000100001',100.50,'EUR','20260110')")
        con.execute(shim(merge_text(by_table("VBAK"), "run-1")))
        con.execute("TRUNCATE SAP_LANDING.VBAK")
        con.execute("INSERT INTO SAP_LANDING.VBAK VALUES ('0000004711','TA','1000','0000100001',250.00,'EUR','20260110'),"
                    "('0000004712','TA','1000','0000100002',10.00,'USD','20260111')")
        con.execute(shim(merge_text(by_table("VBAK"), "run-2")))
        rows = con.execute("SELECT VBELN, NETWR, _ADF_RUN_ID FROM SAP_CORE.VBAK ORDER BY 1").fetchall()
        self.assertEqual([(r[0], float(r[1]), r[2]) for r in rows], [("0000004711", 250.0, "run-2"), ("0000004712", 10.0, "run-2")])

    def test_rows_absent_from_landing_are_kept(self):  # UT-04
        con = database()
        con.execute("INSERT INTO SAP_LANDING.MARA VALUES ('MAT-1001','FERT','001','ST',1.250,'20250301')")
        con.execute(shim(merge_text(by_table("MARA"), "run-1")))
        con.execute("TRUNCATE SAP_LANDING.MARA")
        con.execute(shim(merge_text(by_table("MARA"), "run-2")))
        self.assertEqual(con.execute("SELECT COUNT(*) FROM SAP_CORE.MARA").fetchone()[0], 1)  # no deletes

    def test_keys_never_updated(self):  # UT-05
        for o in CONTROL:
            set_clause = re.search(r"UPDATE SET (.*?) WHEN NOT", o["mergeSql"]).group(1)
            for k in o["keyColumns"]:
                self.assertNotIn(f"T.{k} =", set_clause, o["sapTable"])


class PipelineTests(unittest.TestCase):
    def evaluate_if(self, outputs):
        """@equals(int(activity('CopySapToAdls').output.rowsCopied), int(activity('CountLandingRows').output.firstRow.ROW_COUNT))"""
        self.assertEqual(IF["expression"]["value"],
                         "@equals(int(activity('CopySapToAdls').output.rowsCopied), int(activity('CountLandingRows').output.firstRow.ROW_COUNT))")
        return int(outputs["CopySapToAdls"]["rowsCopied"]) == int(outputs["CountLandingRows"]["firstRow"]["ROW_COUNT"])

    def test_reconciliation(self):  # UT-06
        self.assertTrue(self.evaluate_if(OUTPUTS["match"]))
        self.assertFalse(self.evaluate_if(OUTPUTS["mismatch"]))
        self.assertTrue(self.evaluate_if(OUTPUTS["empty"]))
        self.assertEqual([a["type"] for a in IF["ifFalseActivities"]], ["Fail"])
        self.assertEqual([a["name"] for a in IF["ifTrueActivities"]], ["MergeIntoCore"])

    def test_order_of_steps(self):  # UT-07
        dep = {n: [d["activity"] for d in a.get("dependsOn", [])] for n, a in INNER.items()}
        self.assertEqual(dep, {"CopySapToAdls": [], "CopyAdlsToSnowflakeLanding": ["CopySapToAdls"],
                               "CountLandingRows": ["CopyAdlsToSnowflakeLanding"], "IfRowCountsMatch": ["CountLandingRows"]})

    def test_truncate_targets_landing_only(self):  # UT-08
        expr = INNER["CopyAdlsToSnowflakeLanding"]["typeProperties"]["sink"]["preCopyScript"]["value"]
        self.assertEqual(expr, "@concat('TRUNCATE TABLE ', item().landingSchema, '.', item().landingTable)")
        for o in CONTROL:
            self.assertEqual(o["landingSchema"], SPEC["landingSchema"])
            self.assertNotEqual(o["landingSchema"], SPEC["targetSchema"])
            self.assertFalse(o["targetTable"].startswith(SPEC["landingSchema"] + "."))

    def test_same_folder_written_and_read(self):  # UT-09
        out = INNER["CopySapToAdls"]["outputs"][0]["parameters"]
        inp = INNER["CopyAdlsToSnowflakeLanding"]["inputs"][0]["parameters"]
        self.assertEqual(out, inp)
        self.assertIn("pipeline().RunId", out["folderPath"])   # a rerun never mixes files from another run

    def test_count_query_matches_landing(self):  # UT-10
        con = database()
        con.execute("INSERT INTO SAP_LANDING.KNA1 (KUNNR) VALUES ('1'),('2'),('3')")
        for o in CONTROL:
            n = con.execute(o["countSql"]).fetchone()[0]
            self.assertEqual(n, 3 if o["sapTable"] == "KNA1" else 0)


class GeneratorSafetyTests(unittest.TestCase):
    def test_rejects_unsafe_input(self):  # UT-11
        cases = [
            ("table", lambda s: s["objects"][0].update(sapTable="KNA1; DROP TABLE X")),
            ("column", lambda s: s["objects"][0]["columns"][1].update(name="NAME1) --")),
            ("type", lambda s: s["objects"][0]["columns"][1].update(type="VARCHAR(10); DELETE")),
            ("filter", lambda s: s["objects"][2].update(sapFilter="ERDAT GE '2026' OR 1 EQ 1")),
            ("filter quote", lambda s: s["objects"][2].update(sapFilter="ERDAT GE '20260101'' --'")),
            ("key", lambda s: s["objects"][0].update(keyColumns=["NOPE"])),
            ("schema", lambda s: s.update(targetSchema="sap_core")),
            ("date from non-DATS", lambda s: s["objects"][0]["columns"][6].pop("sapType")),
        ]
        for label, mutate in cases:
            bad = copy.deepcopy(SPEC)
            mutate(bad)
            with self.subTest(label), self.assertRaises(ValueError):
                gen.build(bad)

    def test_generated_files_up_to_date(self):  # UT-12
        control, ddl = gen.build(SPEC)
        self.assertEqual(control, (ROOT / "adf/sap-snowflake-objects.json").read_text())
        self.assertEqual(ddl, DDL)


if __name__ == "__main__":
    unittest.main(verbosity=1)
