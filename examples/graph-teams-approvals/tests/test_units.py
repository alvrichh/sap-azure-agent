"""Unit tests for the Teams approvals logic (no Graph, Teams or Azure needed)."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from teams_approvals.card import build_channel_message, build_po_card, validate_channel_message  # noqa: E402
from teams_approvals.decision import decide  # noqa: E402
from teams_approvals.notifications import classify  # noqa: E402

FX = ROOT / "tests/fixtures"
CARD_ID = "1730800000000"
SUB = "11111111-2222-3333-4444-555555555555"
APPROVERS = {"aaaaaaaa-0000-0000-0000-000000000001"}
NOTIFIER = "cccccccc-0000-0000-0000-000000000003"


def fx(name):
    return json.loads((FX / name).read_text())


class CardTests(unittest.TestCase):
    def test_card_message_follows_graph_rules(self):  # UT-01
        msg = build_channel_message(fx("po.json"), "https://fiori.example.com/po", attachment_id="att1")
        self.assertEqual(validate_channel_message(msg), [])
        self.assertIn('<attachment id="att1"></attachment>', msg["body"]["content"])
        self.assertIsInstance(msg["attachments"][0]["content"], str)

    def test_card_content(self):  # UT-02
        card = build_po_card(fx("po.json"), "https://fiori.example.com/po")
        facts = {f["title"]: f["value"] for f in card["body"][1]["facts"]}
        self.assertEqual(facts["Amount"], "58,250.00 EUR")
        self.assertEqual([a["type"] for a in card["actions"]], ["Action.OpenUrl"])

    def test_rejects_bad_po_number_and_http_url(self):  # UT-03
        po = dict(fx("po.json"), number="12345")
        with self.assertRaises(ValueError):
            build_po_card(po, "https://fiori.example.com/po")
        with self.assertRaises(ValueError):
            build_po_card(fx("po.json"), "http://fiori.example.com/po")

    def test_validator_catches_unsupported_actions_and_missing_reference(self):  # UT-04
        msg = build_channel_message(fx("po.json"), "https://fiori.example.com/po", attachment_id="att1")
        card = json.loads(msg["attachments"][0]["content"])
        card["actions"].append({"type": "Action.Submit", "title": "Approve"})
        msg["attachments"][0]["content"] = json.dumps(card)
        msg["body"]["content"] = "no reference"
        problems = validate_channel_message(msg)
        self.assertTrue(any("Action.Submit" in p for p in problems))
        self.assertTrue(any("not referenced" in p for p in problems))


class NotificationTests(unittest.TestCase):
    def test_validation_message_is_ignored(self):  # UT-05
        self.assertEqual(classify(fx("event-validation.json"), "test-client-state", {SUB})["kind"], "validation")

    def test_reply_is_extracted(self):  # UT-06
        items = classify(fx("event-reply-created.json"), "test-client-state", {SUB})["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["kind"], "reply")
        self.assertEqual(items[0]["parent"], CARD_ID)
        self.assertEqual(items[0]["reply"], "1730800100000")

    def test_mixed_batch(self):  # UT-07
        kinds = [(i["kind"], i.get("reason") or i.get("event"))
                 for i in classify(fx("event-mixed.json"), "test-client-state", {SUB})["items"]]
        self.assertEqual(kinds, [
            ("rejected", "clientState mismatch"),
            ("rejected", "unknown subscription"),
            ("ignored", "changeType updated"),
            ("ignored", "not a reply"),
            ("lifecycle", "reauthorizationRequired"),
        ])


class DecisionTests(unittest.TestCase):
    def run_decide(self, name, decided=None):
        return decide(fx(name), {CARD_ID: "4500001234"}, APPROVERS, NOTIFIER, decided if decided is not None else set())

    def test_approve(self):  # UT-08
        r = self.run_decide("message-approve.json")
        self.assertEqual((r["status"], r["po"]), ("approved", "4500001234"))

    def test_reject_with_reason_unescapes_html(self):  # UT-09
        r = self.run_decide("message-reject-with-reason.json")
        self.assertEqual(r["status"], "rejected")
        self.assertEqual(r["reason"], "price above contract & wrong plant")

    def test_reject_needs_reason(self):  # UT-10
        self.assertEqual(self.run_decide("message-reject-no-reason.json")["status"], "invalid")

    def test_only_approvers_decide(self):  # UT-11
        self.assertEqual(self.run_decide("message-unauthorized.json")["status"], "unauthorized")

    def test_ignored_messages(self):  # UT-12
        for name in ["message-notifier.json", "message-bot.json", "message-chatter.json",
                     "message-system.json", "message-other-thread.json"]:
            with self.subTest(name=name):
                self.assertEqual(self.run_decide(name)["status"], "ignored")

    def test_first_decision_wins(self):  # UT-13
        decided = set()
        self.assertEqual(self.run_decide("message-approve.json", decided)["status"], "approved")
        self.assertEqual(self.run_decide("message-reject-with-reason.json", decided)["status"], "duplicate")


class FlowTests(unittest.TestCase):
    def test_notification_to_decision(self):  # UT-14: Event Hubs event -> Graph GET (fixture) -> decision
        store = {"1730800100000": fx("message-approve.json")}
        decided, out = set(), []
        for item in classify(fx("event-reply-created.json"), "test-client-state", {SUB})["items"]:
            if item["kind"] == "reply":
                message = store[item["reply"]]  # stands in for GET /teams/.../replies/{id}
                out.append(decide(message, {CARD_ID: "4500001234"}, APPROVERS, NOTIFIER, decided))
        self.assertEqual([(d["status"], d["po"]) for d in out], [("approved", "4500001234")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
