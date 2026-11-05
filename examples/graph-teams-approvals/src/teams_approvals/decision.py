"""Turn a Teams reply into an SAP purchase-order decision.

Rules:
- Only replies to a known PO card count; the first valid decision per PO wins.
- Only human users in the approver list can decide; bots/apps and the notifier account are ignored.
- First word APPROVE or REJECT (case-insensitive); REJECT needs a reason.
"""
import html
import re

TAG = re.compile(r"<[^>]+>")


def plain_text(message: dict) -> str:
    content = message.get("body", {}).get("content", "")
    if message.get("body", {}).get("contentType") == "html":
        content = html.unescape(TAG.sub(" ", content))
    return " ".join(content.split())


def decide(message: dict, cards: dict, approvers: set[str], notifier_id: str, decided: set[str]) -> dict:
    """Return {"status": ..., ...}. status: approved, rejected, ignored, unauthorized, invalid, duplicate."""
    if message.get("messageType") != "message":
        return {"status": "ignored", "reason": "system message"}
    parent = message.get("replyToId")
    if parent not in cards:
        return {"status": "ignored", "reason": "not a reply to a PO card"}
    po = cards[parent]
    sender = (message.get("from") or {}).get("user")
    if not sender or (message.get("from") or {}).get("application"):
        return {"status": "ignored", "reason": "not sent by a user", "po": po}
    if sender.get("id") == notifier_id:
        return {"status": "ignored", "reason": "notifier account", "po": po}
    text = plain_text(message)
    words = text.split(" ", 1)
    verb = words[0].upper() if words and words[0] else ""
    if verb not in {"APPROVE", "REJECT"}:
        return {"status": "ignored", "reason": "no decision keyword", "po": po}
    if sender.get("id") not in approvers:
        return {"status": "unauthorized", "po": po, "user": sender.get("id")}
    if po in decided:
        return {"status": "duplicate", "po": po, "user": sender.get("id")}
    reason = words[1].strip() if len(words) > 1 else ""
    if verb == "REJECT" and not reason:
        return {"status": "invalid", "reason": "REJECT requires a reason", "po": po}
    decided.add(po)
    return {"status": "approved" if verb == "APPROVE" else "rejected", "po": po,
            "user": sender.get("id"), "userName": sender.get("displayName"),
            "reason": reason, "messageId": message.get("id")}
