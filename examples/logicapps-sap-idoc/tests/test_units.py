"""Offline tests of the Logic Apps IDoc workflows: they read the workflow.json files and evaluate
their schemas, IDoc construction, transaction-ID handling, XPath expressions and branching against sample IDocs.
Requires: lxml, jsonschema.
"""
import json
import re
import unittest
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import jsonschema
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "logicapp"
FX = ROOT / "tests/fixtures"
SEND = json.loads((APP / "wf-send-sales-order-idoc/workflow.json").read_text())["definition"]
STATUS = json.loads((APP / "wf-idoc-status/workflow.json").read_text())["definition"]
RECEIVE = json.loads((APP / "wf-receive-customer-idoc/workflow.json").read_text())["definition"]
PARAMS = {k: v["value"] for k, v in json.loads((APP / "parameters.json").read_text()).items()}
ORDER = json.loads((FX / "order-request.json").read_text())
XPATH_EXPR = re.compile(r"^@xpath\(xml\((triggerBody\(\)\?\['content'\]|item\(\))\), '(.+)'\)$")
APP_SETTINGS = {  # values a deployment would provide (from the bicepparam additionalAppSettings)
    "SAP_IDOC_SENDER_PORT": "LOGICAPP", "SAP_IDOC_SENDER_PARTNER": "LOGICAPP",
    "SAP_IDOC_RECEIVER_PORT": "SAPS4P", "SAP_IDOC_RECEIVER_PARTNER": "S4PCLNT100",
}


def resolve(value, body, item=None, outputs=None):
    """Evaluate the small subset of Workflow Definition Language used in the Compose/Select inputs."""
    if isinstance(value, dict):
        return {k: resolve(v, body, item, outputs) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, body, item, outputs) for v in value]
    if not isinstance(value, str) or not value.startswith("@"):
        return value
    for pattern, getter in [
        (r"@triggerBody\(\)\?\['(\w+)'\]", lambda k: body[k]),
        (r"@item\(\)\?\['(\w+)'\]", lambda k: item[k]),
        (r"@body\('(\w+)'\)", lambda k: outputs[k]),
        (r"@parameters\('(\w+)'\)", lambda k: APP_SETTINGS[re.fullmatch(r"@appsetting\('(\w+)'\)", PARAMS[k]).group(1)]),
    ]:
        m = re.fullmatch(pattern, value)
        if m:
            return getter(m.group(1))
    raise ValueError(f"expression not supported by the test evaluator: {value}")


def to_xml(obj) -> bytes:
    """Mimic xml(): one root property; '@name' keys become attributes; arrays become repeated elements."""
    def element(name, value):
        if isinstance(value, list):
            return "".join(element(name, v) for v in value)
        if isinstance(value, dict):
            attrs = "".join(f" {k[1:]}={quoteattr(str(v))}" for k, v in value.items() if k.startswith("@"))
            children = "".join(element(k, v) for k, v in value.items() if not k.startswith("@"))
            return f"<{name}{attrs}>{children}</{name}>"
        return f"<{name}>{escape(str(value))}</{name}>"
    (root, content), = obj.items()
    return element(root, content).encode()


def build_idoc(body) -> etree._Element:
    acts = SEND["actions"]
    items = [resolve(acts["Map_items"]["inputs"]["select"], body, item=i) for i in resolve(acts["Map_items"]["inputs"]["from"], body)]
    composed = resolve(acts["Build_ORDERS05_IDoc"]["inputs"], body, outputs={"Map_items": items})
    return etree.fromstring(to_xml(composed))


def xpath_of(expr: str):
    return XPATH_EXPR.match(expr).group(2)


def receive_branch(fixture: str):
    """Evaluate Is_customer_master_IDoc and, if true, the Extract_customers Select over the packet."""
    doc = etree.fromstring((FX / fixture).read_bytes())
    cond = RECEIVE["actions"]["Is_customer_master_IDoc"]
    left, right = cond["expression"]["and"][0]["equals"]
    if doc.xpath(xpath_of(left)) != right:
        return "else", next(iter(cond["else"]["actions"]))
    select = cond["actions"]["Extract_customers"]["inputs"]
    rows = []
    for node in doc.xpath(xpath_of(select["from"])):
        item = etree.fromstring(etree.tostring(node))
        rows.append({k: item.xpath(xpath_of(v)) for k, v in select["select"].items()})
    return "then", rows


class OrderSchemaTests(unittest.TestCase):
    def schema(self):
        return SEND["triggers"]["When_a_HTTP_request_is_received"]["inputs"]["schema"]

    def test_valid_order(self):  # UT-01
        jsonschema.validate(ORDER, self.schema())
        jsonschema.validate({**ORDER, "transactionId": "3f2c1a9e-8b7d-4c6e-9f10-1a2b3c4d5e6f"}, self.schema())

    def test_invalid_orders_rejected(self):  # UT-02
        item = ORDER["items"][0]
        bad = [
            {k: v for k, v in ORDER.items() if k != "customer"},                     # missing field
            {**ORDER, "extra": "x"},                                                 # extra field
            {**ORDER, "items": []},                                                  # no items
            {**ORDER, "items": [{**item, "position": "10"}]},                        # POSEX not 6 digits
            {**ORDER, "items": [{**item, "quantity": "1,5"}]},                       # decimal comma
            {**ORDER, "items": [{**item, "material": "<MAT>"}]},                     # markup
            {**ORDER, "items": [{**item, "note": "x"}]},                             # extra item field
            {**ORDER, "salesOrg": "10000"},                                          # sales org length
            {**ORDER, "transactionId": "not-a-guid"},                                # TID must be a GUID
        ]
        for body in bad:
            with self.subTest(body=body), self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(body, self.schema())


class IDocBuildTests(unittest.TestCase):
    def test_control_record(self):  # UT-03
        idoc = build_idoc(ORDER)
        self.assertEqual(idoc.tag, "ORDERS05")
        self.assertEqual(idoc.xpath("string(IDOC/@BEGIN)"), "1")
        dc = {e.tag: e.text for e in idoc.find("IDOC/EDI_DC40")}
        self.assertEqual(dc["TABNAM"], "EDI_DC40")
        self.assertEqual(dc["DIRECT"], "2")                      # inbound to SAP
        self.assertEqual((dc["IDOCTYP"], dc["MESTYP"]), ("ORDERS05", "ORDERS"))
        self.assertEqual((dc["SNDPRT"], dc["SNDPRN"], dc["RCVPRN"]), ("LS", "LOGICAPP", "S4PCLNT100"))
        self.assertEqual(idoc.xpath("string(IDOC/EDI_DC40/@SEGMENT)"), "1")

    def test_segments_and_order(self):  # UT-04
        idoc = build_idoc(ORDER).find("IDOC")
        order = [e.tag for e in idoc]
        self.assertEqual(order, ["EDI_DC40", "E1EDK01", "E1EDK14", "E1EDK14", "E1EDK14", "E1EDK14", "E1EDKA1", "E1EDK02", "E1EDP01", "E1EDP01"])
        k14 = {e.findtext("QUALF"): e.findtext("ORGID") for e in idoc.findall("E1EDK14")}
        self.assertEqual(k14, {"008": "1000", "007": "10", "006": "00", "012": "TA"})
        self.assertEqual(idoc.xpath("string(E1EDKA1[PARVW='AG']/PARTN)"), "100001")
        self.assertEqual(idoc.xpath("string(E1EDK02[QUALF='001']/BELNR)"), "PO-2026-0001")
        items = [(p.findtext("POSEX"), p.findtext("MENGE"), p.findtext("MENEE"), p.findtext("E1EDP19/IDTNR")) for p in idoc.findall("E1EDP01")]
        self.assertEqual(items, [("000010", "5", "ST", "MAT-1001"), ("000020", "12.5", "KG", "MAT-2002")])
        self.assertTrue(all(s.get("SEGMENT") == "1" for s in idoc.iter() if s.tag.startswith("E1")))

    def test_single_item_still_repeats_correctly(self):  # UT-05
        idoc = build_idoc({**ORDER, "items": ORDER["items"][:1]}).find("IDOC")
        self.assertEqual(len(idoc.findall("E1EDP01")), 1)


class TransactionTests(unittest.TestCase):
    def test_send_confirm_list_share_one_tid(self):  # UT-06
        init = SEND["actions"]["Initialize_IDoc_transaction_ID"]["inputs"]["variables"][0]
        self.assertEqual(init["value"], "@{coalesce(triggerBody()?['transactionId'], guid())}")
        tr = SEND["actions"]["Try"]["actions"]
        send = tr["Send_ORDERS05_to_SAP"]["inputs"]["parameters"]
        self.assertEqual(send["confirmTid"], "false")             # confirm explicitly, after success
        self.assertEqual(send["idocFormat"], "SapPlainXml")
        self.assertIn("xml(outputs('Build_ORDERS05_IDoc'))", send["body"])
        for name in ("Send_ORDERS05_to_SAP", "Confirm_transaction_ID", "Get_IDoc_numbers"):
            self.assertEqual(tr[name]["inputs"]["parameters"]["tId"], "@variables('idocTransactionId')", name)
        self.assertEqual(tr["Confirm_transaction_ID"]["runAfter"], {"Send_ORDERS05_to_SAP": ["Succeeded"]})
        self.assertEqual(tr["Get_IDoc_numbers"]["inputs"]["parameters"]["direction"], "Receive")

    def test_failure_returns_tid_for_safe_retry(self):  # UT-07
        body = SEND["actions"]["Catch"]["actions"]["Respond_502"]["inputs"]["body"]
        self.assertEqual(body["transactionId"], "@variables('idocTransactionId')")
        self.assertEqual(SEND["actions"]["Catch"]["runAfter"]["Try"], ["Failed", "TimedOut"])


class ReceiveTests(unittest.TestCase):
    def test_respond_to_sap_first(self):  # UT-08
        acts = RECEIVE["actions"]
        self.assertEqual(acts["Respond_to_SAP_server"]["runAfter"], {})
        others = [n for n in acts if n != "Respond_to_SAP_server"]
        self.assertTrue(all("Respond_to_SAP_server" in acts[n]["runAfter"] for n in others))

    def test_debmas_packet_split(self):  # UT-09
        branch, rows = receive_branch("debmas07-packet.xml")
        self.assertEqual(branch, "then")
        self.assertEqual([r["customer"] for r in rows], ["0000100001", "0000100002"])
        self.assertEqual(rows[0]["name"], "Contoso Iberia & Co")      # entity decoded
        self.assertEqual(rows[0]["idocNumber"], "0000000000412345")
        self.assertEqual((rows[1]["country"], rows[1]["deletionFlag"]), ("PT", "X"))
        self.assertEqual(rows[0]["deletionFlag"], "")
        self.assertEqual(rows[0]["sapSystem"], "S4PCLNT100")

    def test_other_message_type_not_forwarded(self):  # UT-10
        branch, action = receive_branch("matmas05-single.xml")
        self.assertEqual(branch, "else")
        self.assertEqual(RECEIVE["actions"]["Is_customer_master_IDoc"]["else"]["actions"][action]["inputs"]["runStatus"], "Cancelled")

    def test_downstream_failure_marks_run_failed(self):  # UT-11
        then = RECEIVE["actions"]["Is_customer_master_IDoc"]["actions"]
        self.assertEqual(then["Mark_run_failed"]["runAfter"], {"Forward_to_customer_API": ["Failed", "TimedOut"]})
        self.assertEqual(then["Forward_to_customer_API"]["inputs"]["authentication"]["type"], "ManagedServiceIdentity")


class StatusTests(unittest.TestCase):
    def describe(self, code):
        """Evaluate coalesce(parameters('idocStatusText')?[string(status)], default)."""
        expr = STATUS["actions"]["Respond_200"]["inputs"]["body"]["description"]
        default = re.search(r", '([^']+)'\)$", expr).group(1)
        return PARAMS["idocStatusText"].get(str(code), default)

    def test_status_text(self):  # UT-12
        self.assertEqual(self.describe("53"), "Application document posted")
        self.assertEqual(self.describe("51"), "Application document not posted")
        self.assertTrue(self.describe("99").startswith("Unknown status"))

    def test_status_schema(self):  # UT-13
        schema = STATUS["triggers"]["When_a_HTTP_request_is_received"]["inputs"]["schema"]
        jsonschema.validate({"idocNumber": "0000000000412345"}, schema)
        for bad in ({"idocNumber": "412345"}, {"idocNumber": "0000000000412345", "x": 1}, {}):
            with self.subTest(bad=bad), self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(bad, schema)


class ExpressionSyntaxTests(unittest.TestCase):
    def test_string_literals_well_formed(self):  # UT-14
        """A "'" inside a '...' WDL literal ends the literal early: XPaths must use double quotes."""
        def strings(node):
            if isinstance(node, dict):
                for v in node.values():
                    yield from strings(v)
            elif isinstance(node, list):
                for v in node:
                    yield from strings(v)
            elif isinstance(node, str) and node.startswith("@"):
                yield node
        for wf in (SEND, STATUS, RECEIVE):
            for expr in strings(wf):
                body = re.sub(r"'[^']*'", "''", expr)          # drop literals
                self.assertEqual(body.count("'") % 2, 0, expr)
                # a literal always sits next to ( , [ ] ) or a space; text glued to it means a literal ended early
                self.assertIsNone(re.search(r"\w''|''\w", body), expr)
                self.assertEqual(body.count("("), body.count(")"), expr)


if __name__ == "__main__":
    unittest.main(verbosity=1)
