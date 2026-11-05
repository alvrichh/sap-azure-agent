"""Offline tests of the Logic Apps workflows: they read the workflow.json files and evaluate
their schema, request construction, XPath expressions and branching against sample SAP responses.
Requires: lxml, jsonschema.
"""
import json
import re
import unittest
from pathlib import Path
from xml.sax.saxutils import escape

import jsonschema
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "tests/fixtures"
WF = json.loads((ROOT / "logicapp/wf-material-availability/workflow.json").read_text())["definition"]
PING = json.loads((ROOT / "logicapp/wf-sap-ping/workflow.json").read_text())["definition"]
TRY = WF["actions"]["Try"]["actions"]
XPATH = re.compile(r"xpath\(xml\(body\('[^']+'\)\), '(.+)'\)\}$")


def trigger_schema():
    return WF["triggers"]["When_a_HTTP_request_is_received"]["inputs"]["schema"]


def build_request_xml(body: dict) -> bytes:
    """Mimic Build_RFC_request + xml(): '@xmlns' becomes the namespace, values are XML-escaped."""
    template = WF["actions"]["Build_RFC_request"]["inputs"]
    root_name, fields = next(iter(template.items()))
    parts = []
    for name, value in fields.items():
        if name.startswith("@"):
            continue
        m = re.fullmatch(r"@triggerBody\(\)\?\['(\w+)'\]", value)
        text = body[m.group(1)] if m else value
        parts.append(f"<{name}>{escape(text)}</{name}>" if text else f"<{name} />")
    return f'<{root_name} xmlns="{fields["@xmlns"]}">{"".join(parts)}</{root_name}>'.encode()


def eval_parse(fixture: str) -> dict:
    doc = etree.fromstring((FX / fixture).read_bytes())
    out = {}
    for key, expr in TRY["Parse_SAP_response"]["inputs"].items():
        out[key] = doc.xpath(XPATH.search(expr).group(1))
    return out


def branch(parsed: dict) -> int:
    """Evaluate the SAP_reported_error condition: E or A -> 422, otherwise 200."""
    cond = TRY["SAP_reported_error"]["expression"]["or"]
    hit = any(parsed["returnType"] == c["equals"][1] for c in cond)
    actions = TRY["SAP_reported_error"]["actions"] if hit else TRY["SAP_reported_error"]["else"]["actions"]
    return next(iter(actions.values()))["inputs"]["statusCode"]


class TriggerSchemaTests(unittest.TestCase):
    def test_valid_request(self):  # UT-01
        jsonschema.validate({"material": "MAT-1001", "plant": "1000", "unit": "ST"}, trigger_schema())

    def test_invalid_requests_rejected(self):  # UT-02
        bad = [
            {"material": "MAT-1001", "plant": "1000"},                              # missing unit
            {"material": "MAT-1001", "plant": "1000", "unit": "ST", "x": 1},        # extra field
            {"material": "mat-1001", "plant": "1000", "unit": "ST"},                # lowercase
            {"material": "<A>", "plant": "1000", "unit": "ST"},                     # markup
            {"material": "MAT-1001", "plant": "10000", "unit": "ST"},               # plant length
            {"material": "M" * 19, "plant": "1000", "unit": "ST"},                  # > 18 chars
        ]
        for body in bad:
            with self.subTest(body=body), self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(body, trigger_schema())


class RequestTests(unittest.TestCase):
    def test_request_xml_shape(self):  # UT-03
        doc = etree.fromstring(build_request_xml({"material": "MAT-1001", "plant": "1000", "unit": "ST"}))
        ns = {"r": "http://Microsoft.LobServices.Sap/2007/03/Rfc/"}
        self.assertEqual(etree.QName(doc).localname, "BAPI_MATERIAL_AVAILABILITY")
        self.assertEqual(doc.xpath("string(r:MATERIAL)", namespaces=ns), "MAT-1001")
        self.assertEqual(doc.xpath("string(r:PLANT)", namespaces=ns), "1000")
        self.assertEqual(len(doc.xpath("r:WMDVSX | r:WMDVEX", namespaces=ns)), 2)  # empty tables -> returned by SAP

    def test_values_are_escaped(self):  # UT-04 (defence in depth behind the schema)
        doc = etree.fromstring(build_request_xml({"material": "A&B</MATERIAL><X>", "plant": "1000", "unit": "ST"}))
        self.assertEqual(doc.xpath("string(*[local-name()='MATERIAL'])"), "A&B</MATERIAL><X>")
        self.assertEqual(len(doc), 5)

    def test_call_uses_compose_output(self):  # UT-05
        call = TRY["Call_BAPI_MATERIAL_AVAILABILITY"]["inputs"]["parameters"]
        self.assertEqual(call["rfcName"], "BAPI_MATERIAL_AVAILABILITY")
        self.assertEqual(call["body"], "@{xml(outputs('Build_RFC_request'))}")


class ResponseTests(unittest.TestCase):
    def test_success(self):  # UT-06
        p = eval_parse("sap-response-ok.xml")
        self.assertEqual((p["availableQuantity"], p["endLeadTime"], p["returnType"]), ("125.000", "20261120", "S"))
        self.assertEqual(branch(p), 200)

    def test_error_maps_to_422(self):  # UT-07
        p = eval_parse("sap-response-error.xml")
        self.assertEqual(p["returnType"], "E")
        self.assertIn("not maintained", p["returnMessage"])
        self.assertEqual(branch(p), 422)

    def test_warning_still_200(self):  # UT-08
        p = eval_parse("sap-response-warning.xml")
        self.assertEqual((p["returnType"], branch(p)), ("W", 200))
        self.assertEqual(float(p["availableQuantity"]), 12.0)

    def test_abort_maps_to_422(self):  # UT-09
        self.assertEqual(branch({"returnType": "A"}), 422)


class ExpressionSyntaxTests(unittest.TestCase):
    def test_string_literals_are_well_formed(self):  # UT-11
        """In Workflow Definition Language, a quote inside a '...' literal must be doubled ('').
        Walk every @{...} expression and check that all single-quoted literals close before the expression ends."""
        def literals_ok(expr):
            i, depth = 0, 0
            while i < len(expr):
                c = expr[i]
                if c == "'":
                    j = i + 1
                    while True:
                        k = expr.find("'", j)
                        if k == -1:
                            return False
                        if expr[k + 1:k + 2] == "'":
                            j = k + 2
                            continue
                        break
                    nxt = expr[k + 1:k + 2]
                    if nxt and nxt not in ")],}]" and nxt not in " ,":
                        return False  # literal closed and immediately followed by an identifier: broken quoting
                    i = k + 1
                    continue
                depth += c == "("
                depth -= c == ")"
                i += 1
            return depth == 0

        def walk(node):
            if isinstance(node, dict):
                for v in node.values():
                    yield from walk(v)
            elif isinstance(node, list):
                for v in node:
                    yield from walk(v)
            elif isinstance(node, str) and node.startswith("@"):
                yield node

        for wf in (WF, PING):
            for expr in walk(wf):
                with self.subTest(expr=expr[:80]):
                    self.assertTrue(literals_ok(expr), f"malformed literal in {expr}")


class PingTests(unittest.TestCase):
    def test_ping_xpaths(self):  # UT-10
        doc = etree.fromstring((FX / "stfc-connection-response.xml").read_bytes())
        body = PING["actions"]["Respond"]["inputs"]["body"]
        echo = doc.xpath(XPATH.search(body["echo"]).group(1))
        info = doc.xpath(XPATH.search(body["sapInfo"]).group(1))
        self.assertEqual(echo, "logicapp-ping")
        self.assertIn("Sysid: S4P", info)


if __name__ == "__main__":
    unittest.main(verbosity=2)
