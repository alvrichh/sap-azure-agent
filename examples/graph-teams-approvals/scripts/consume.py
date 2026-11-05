#!/usr/bin/env python3
"""Read Graph change notifications from Event Hubs, fetch each reply and print the SAP decision.

Requires: pip install azure-eventhub azure-identity
Auth: Event Hubs with your Entra identity (Azure Event Hubs Data Receiver); Graph with GRAPH_TOKEN
(delegated ChannelMessage.Read.All). In production, the decision is sent to SAP (e.g. release the PO
through the sap-api-integration skill) instead of printed.

  GRAPH_TOKEN=... python3 scripts/consume.py --namespace <ns>.servicebus.windows.net --hub graph-notifications \
      --subscription-id <id> --client-state-env CLIENT_STATE --approvers <object-id>[,<object-id>] --notifier <object-id>
"""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from teams_approvals.decision import decide  # noqa: E402
from teams_approvals.notifications import classify  # noqa: E402


def graph_get(resource, token):
    req = urllib.request.Request(f"https://graph.microsoft.com/v1.0/{resource}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--namespace", required=True)
    p.add_argument("--hub", default="graph-notifications")
    p.add_argument("--consumer-group", default="sap-approvals")
    p.add_argument("--subscription-id", required=True)
    p.add_argument("--client-state-env", default="CLIENT_STATE")
    p.add_argument("--approvers", required=True)
    p.add_argument("--notifier", required=True)
    a = p.parse_args()
    try:
        from azure.eventhub import EventHubConsumerClient
        from azure.identity import DefaultAzureCredential
    except ImportError:
        sys.exit("pip install azure-eventhub azure-identity")
    token = os.environ.get("GRAPH_TOKEN") or sys.exit("set GRAPH_TOKEN")
    client_state = os.environ.get(a.client_state_env) or sys.exit(f"set {a.client_state_env}")
    cards = json.loads((ROOT / "state/cards.json").read_text())
    approvers, decided = set(a.approvers.split(",")), set()

    def on_event(partition_context, event):
        body = event.body_as_json()
        result = classify(body, client_state, {a.subscription_id})
        for item in result.get("items", []):
            if item["kind"] == "reply":
                message = graph_get(item["resource"], token)
                print(json.dumps(decide(message, cards, approvers, a.notifier, decided)), flush=True)
            elif item["kind"] in {"lifecycle", "rejected"}:
                print(json.dumps(item), flush=True)
        partition_context.update_checkpoint(event)

    client = EventHubConsumerClient(fully_qualified_namespace=a.namespace, eventhub_name=a.hub,
                                    consumer_group=a.consumer_group, credential=DefaultAzureCredential())
    print("listening… (Ctrl+C to stop)", file=sys.stderr)
    with client:
        client.receive(on_event=on_event, starting_position="@latest")


if __name__ == "__main__":
    main()
