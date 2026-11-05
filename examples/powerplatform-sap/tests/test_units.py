"""Offline tests of the Power Platform + SAP test case. They read the real flow definitions and deployment
settings and evaluate their expressions with tests/wdl.py against sample SAP responses.
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from wdl import Evaluator, condition  # noqa: E402

FX = ROOT / "tests/fixtures"
F1 = json.loads((ROOT / "solution/flows/sap-check-material-availability.json").read_text())["properties"]["definition"]
F2 = json.loads((ROOT / "solution/flows/sap-search-business-partners.json").read_text())["properties"]["definition"]
SETTINGS = {e: json.loads((ROOT / f"deployment/settings.{e}.json").read_text()) for e in ("dev", "test", "prod")}
SAP_SYS = "SAP system (sap_SapSystem)"
MAX = "SAP max results (sap_MaxResults)"
FILTER = re.compile(r"^startswith\(BusinessPartnerFullName,'((?:[^']|'')*)'\) eq true$")


def env_value(env, schema):
    return next(v["Value"] for v in SETTINGS[env]["EnvironmentVariables"] if v["SchemaName"] == schema)


def run_flow1(material, plant, unit, sap_body):
    """Walk flow 1: input validation, BAPI call inputs, and which response is sent with what body."""
    ev = Evaluator({"trigger_body": {"text": material, "text_1": plant, "text_2": unit},
                    "parameters": {SAP_SYS: env_value("dev", "sap_SapSystem")},
                    "body": {"Call_BAPI_MATERIAL_AVAILABILITY": sap_body}})
    a = F1["actions"]
    if not condition(ev, a["Validate_input"]["expression"]):
        return None, ev.evaluate(a["Validate_input"]["else"]["actions"]["Respond_invalid_input"]["inputs"]["body"])
    call = ev.evaluate(a["Try"]["actions"]["Call_BAPI_MATERIAL_AVAILABILITY"]["inputs"]["parameters"])
    branch = a["Try"]["actions"]["SAP_reported_error"]
    actions = branch["actions"] if condition(ev, branch["expression"]) else branch["else"]["actions"]
    return call, ev.evaluate(next(iter(actions.values()))["inputs"]["body"])


def run_flow2(text, odata_body, max_results=20):
    ev = Evaluator({"trigger_body": {"text": text}, "parameters": {MAX: max_results},
                    "body": {"Query_business_partners": odata_body}})
    a = F2["actions"]
    if not condition(ev, a["Validate_input"]["expression"]):
        return None, None
    query = ev.evaluate(a["Try"]["actions"]["Query_business_partners"]["inputs"]["parameters"])
    select = a["Try"]["actions"]["Shape_results"]["inputs"]
    rows = [Evaluator({**ev.ctx, "item": it}).evaluate(select["select"]) for it in ev.evaluate(select["from"])]
    ev.ctx["body"]["Shape_results"] = rows
    return query, ev.evaluate(a["Try"]["actions"]["Respond_partners"]["inputs"]["body"])


class MaterialFlowTests(unittest.TestCase):
    def test_bapi_inputs(self):  # UT-01
        call, _ = run_flow1(" mat-1001 ", "1000", "st", json.loads((FX / "bapi-ok.json").read_text()))
        self.assertEqual(call["rfcName"], "BAPI_MATERIAL_AVAILABILITY")
        self.assertEqual(call["rfcInputs"], {"MATERIAL": "MAT-1001", "PLANT": "1000", "UNIT": "ST", "CHECK_RULE": "A"})
        self.assertEqual(json.loads(call["x-ms-sap-system"])["AppServerHost"], "<sap-dev-app-server-host>")

    def test_success_and_warning(self):  # UT-02
        _, ok = run_flow1("MAT-1001", "1000", "ST", json.loads((FX / "bapi-ok.json").read_text()))
        self.assertEqual((ok["status"], ok["quantity"]), ("ok", "125.0"))
        _, warn = run_flow1("MAT-1001", "1000", "ST", json.loads((FX / "bapi-warning.json").read_text()))
        self.assertEqual((warn["status"], warn["quantity"], warn["message"]), ("ok", "40.0", "Planned receipts not considered"))

    def test_sap_error(self):  # UT-03
        _, err = run_flow1("MAT-9999", "1000", "ST", json.loads((FX / "bapi-error.json").read_text()))
        self.assertEqual(err["status"], "error")
        self.assertIn("does not exist", err["message"])

    def test_invalid_input_never_calls_sap(self):  # UT-04
        for material, plant, unit in [("", "1000", "ST"), ("M" * 41, "1000", "ST"), ("MAT", "100", "ST"), ("MAT", "1000", "LONG")]:
            with self.subTest(material=material, plant=plant, unit=unit):
                call, body = run_flow1(material, plant, unit, None)
                self.assertIsNone(call)
                self.assertEqual(body["status"], "error")


class PartnerFlowTests(unittest.TestCase):
    def test_query_and_shape_v2(self):  # UT-05
        query, body = run_flow2("Contoso", json.loads((FX / "odata-v2-partners.json").read_text()))
        self.assertEqual(query["entity"], "A_BusinessPartner")
        self.assertEqual(query["top"], 20)
        partners = json.loads(body["partners"])
        self.assertEqual([p["category"] for p in partners], ["Organization", "Person"])
        self.assertEqual(partners[1]["name"], "Contoso O'Brien")

    def test_odata_v4_shape(self):  # UT-06
        _, body = run_flow2("Contoso", json.loads((FX / "odata-v4-partners.json").read_text()))
        self.assertEqual(json.loads(body["partners"])[0]["id"], "1000012")

    def test_filter_injection_stays_inside_literal(self):  # UT-07
        for text in ["O'Brien", "x') or (1 eq 1", "'''", "C' eq true or startswith(X,'"]:
            with self.subTest(text=text):
                query, _ = run_flow2(text, {"value": []})
                m = FILTER.match(query["filter"])
                self.assertIsNotNone(m, query["filter"])
                self.assertEqual(m.group(1).replace("''", "'"), text.strip())

    def test_top_is_capped(self):  # UT-08
        query, _ = run_flow2("Contoso", {"value": []}, max_results=500)
        self.assertEqual(query["top"], 50)

    def test_short_input_rejected(self):  # UT-09
        self.assertEqual(run_flow2("ab", {"value": []}), (None, None))


class SettingsTests(unittest.TestCase):
    ALLOWED = {"AppServerHost", "AppServerService", "Client", "Language", "LogonGroup", "LogonType", "MessageServerHost",
               "MessageServerService", "SafeTyping", "SncCertificate", "SncMyName", "SncLibraryPath", "SncPartnerName",
               "SncQop", "SncSso", "SsoCertificateSubject", "SystemId", "SystemNumber", "UseSnc"}  # connector reference

    def test_sap_system_json(self):  # UT-10
        for env in SETTINGS:
            with self.subTest(env=env):
                v = json.loads(env_value(env, "sap_SapSystem"))
                self.assertLessEqual(set(v), self.ALLOWED)
                if v["LogonType"] == "ApplicationServer":
                    self.assertTrue({"AppServerHost", "SystemNumber", "Client"} <= set(v))
                else:
                    self.assertEqual(v["LogonType"], "Group")
                    self.assertTrue({"MessageServerHost", "LogonGroup", "Client"} <= set(v) and ({"SystemId", "MessageServerService"} & set(v)))

    def test_snc_outside_dev(self):  # UT-11
        for env in ("test", "prod"):
            v = json.loads(env_value(env, "sap_SapSystem"))
            self.assertEqual(v.get("UseSnc"), "Yes", env)
            self.assertIn(v.get("SncQop"), {"Authentication", "Integrity", "Privacy", "Default", "Maximum"})


class ExpressionSyntaxTests(unittest.TestCase):
    def test_every_expression_parses(self):  # UT-12
        """Every @-expression in both flows tokenizes and parses (catches broken quoting like ' inside '...')."""
        from wdl import tokenize

        def walk(node):
            if isinstance(node, dict):
                for v in node.values():
                    yield from walk(v)
            elif isinstance(node, list):
                for v in node:
                    yield from walk(v)
            elif isinstance(node, str) and node.startswith("@") and not node.startswith("@@"):
                yield node

        for flow in (F1, F2):
            for expr in walk(flow):
                inner = [m.group(1) for m in re.finditer(r"@\{(.*?)\}(?=$|[^}])", expr)] if "@{" in expr else [expr[1:]]
                for text in inner:
                    with self.subTest(expr=text[:60]):
                        tokens = tokenize(text)
                        depth = sum(1 for k, v in tokens if v in ("(", "[", "?[")) - sum(1 for k, v in tokens if v in (")", "]"))
                        self.assertEqual(depth, 0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
