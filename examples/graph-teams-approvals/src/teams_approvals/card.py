"""Build the Graph chatMessage that posts an SAP purchase-order card to a Teams channel.

Rules enforced (Microsoft Graph, Teams messaging):
- The attachment id must appear both in the body (<attachment id="..."></attachment>) and in attachments[].id.
- Card content is the serialized Adaptive Card JSON (a string).
- Messages posted through Graph only support Action.OpenUrl actions (no Action.Submit / ShowCard).
"""
import json
import re
import uuid
from decimal import Decimal

ADAPTIVE_CARD = "application/vnd.microsoft.card.adaptive"
PO_PATTERN = re.compile(r"^\d{10}$")
ALLOWED_ACTIONS = {"Action.OpenUrl"}


def _money(amount: Decimal, currency: str) -> str:
    return f"{amount:,.2f} {currency}"


def build_po_card(po: dict, fiori_url: str) -> dict:
    """Return the Adaptive Card for a purchase order awaiting approval."""
    if not PO_PATTERN.match(po["number"]):
        raise ValueError(f"invalid SAP purchase order number: {po['number']!r} (expected 10 digits)")
    if not fiori_url.startswith("https://"):
        raise ValueError("fiori_url must be an https URL")
    amount = Decimal(str(po["amount"]))
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [
            {"type": "TextBlock", "size": "Medium", "weight": "Bolder",
             "text": f"Purchase order {po['number']} needs approval"},
            {"type": "FactSet", "facts": [
                {"title": "Supplier", "value": po["supplier"]},
                {"title": "Amount", "value": _money(amount, po["currency"])},
                {"title": "Company code", "value": po["companyCode"]},
                {"title": "Requested by", "value": po["requester"]},
            ]},
            {"type": "TextBlock", "wrap": True,
             "text": "Reply in this thread with **APPROVE**, or **REJECT** followed by the reason."},
        ],
        "actions": [
            {"type": "Action.OpenUrl", "title": "Open in SAP Fiori", "url": fiori_url},
        ],
    }


def build_channel_message(po: dict, fiori_url: str, attachment_id: str | None = None) -> dict:
    """Return the request body for POST /teams/{team-id}/channels/{channel-id}/messages."""
    card = build_po_card(po, fiori_url)
    attachment_id = attachment_id or uuid.uuid4().hex
    return {
        "subject": f"PO {po['number']} approval",
        "body": {"contentType": "html", "content": f'<attachment id="{attachment_id}"></attachment>'},
        "attachments": [{
            "id": attachment_id,
            "contentType": ADAPTIVE_CARD,
            "contentUrl": None,
            "content": json.dumps(card, separators=(",", ":")),
        }],
    }


def validate_channel_message(message: dict) -> list[str]:
    """Return a list of problems; empty when the body follows the Graph rules above."""
    problems = []
    body = message.get("body", {}).get("content", "")
    for att in message.get("attachments", []):
        if f'<attachment id="{att.get("id")}"></attachment>' not in body:
            problems.append(f"attachment {att.get('id')} not referenced in body")
        if att.get("contentType") != ADAPTIVE_CARD:
            problems.append(f"unexpected contentType {att.get('contentType')}")
        if not isinstance(att.get("content"), str):
            problems.append("card content must be a JSON string")
            continue
        card = json.loads(att["content"])
        actions = [a["type"] for a in card.get("actions", [])]
        actions += [a["type"] for el in card.get("body", []) for a in el.get("actions", [])]
        bad = set(actions) - ALLOWED_ACTIONS
        if bad:
            problems.append(f"unsupported actions for Graph-posted cards: {sorted(bad)}")
    if not message.get("attachments"):
        problems.append("no card attachment")
    return problems
