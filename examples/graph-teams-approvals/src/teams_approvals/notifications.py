"""Handle Microsoft Graph change notifications for Teams channel messages delivered through Event Hubs.

Subscriptions are created without resource data (no encryption certificate), so each notification
only carries the resource path; the consumer then GETs the message with Graph.
"""
import hmac
import re

REPLY_RESOURCE = re.compile(
    r"^teams\('(?P<team>[^']+)'\)/channels\('(?P<channel>[^']+)'\)"
    r"/messages\('(?P<parent>[^']+)'\)/replies\('(?P<reply>[^']+)'\)$")
LIFECYCLE_EVENTS = {"reauthorizationRequired", "subscriptionRemoved", "missed"}


def classify(event: dict, expected_client_state: str, subscription_ids: set[str]) -> dict:
    """Classify one Event Hubs event body (a changeNotificationCollection or a validation message).

    Returns {"kind": ...} with kind in: validation, lifecycle, reply, ignored, rejected.
    """
    if "validationTokens" in event and "value" not in event:
        return {"kind": "validation"}  # Event Hubs: ignore validation messages
    results = []
    for n in event.get("value", []):
        if n.get("subscriptionId") not in subscription_ids:
            results.append({"kind": "rejected", "reason": "unknown subscription"})
            continue
        if n.get("lifecycleEvent") in LIFECYCLE_EVENTS:
            results.append({"kind": "lifecycle", "event": n["lifecycleEvent"], "subscriptionId": n["subscriptionId"]})
            continue
        if not hmac.compare_digest(str(n.get("clientState", "")), expected_client_state):
            results.append({"kind": "rejected", "reason": "clientState mismatch"})
            continue
        if n.get("changeType") != "created":
            results.append({"kind": "ignored", "reason": f"changeType {n.get('changeType')}"})
            continue
        m = REPLY_RESOURCE.match(n.get("resource", ""))
        if not m:
            results.append({"kind": "ignored", "reason": "not a reply"})
            continue
        results.append({"kind": "reply", **m.groupdict(), "resource": n["resource"]})
    return {"kind": "batch", "items": results}
