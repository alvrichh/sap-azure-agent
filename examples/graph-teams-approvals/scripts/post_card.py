#!/usr/bin/env python3
"""Post the SAP purchase-order card to the approvals channel (delegated ChannelMessage.Send).

  GRAPH_TOKEN=... python3 scripts/post_card.py --team <team-id> --channel <channel-id> \
      --po tests/fixtures/po.json --fiori-url "https://<fiori-host>/..." [--dry-run]

Writes the card message ID -> PO number mapping to state/cards.json (ignored by Git).
"""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from teams_approvals.card import build_channel_message, validate_channel_message  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--team", required=True)
    p.add_argument("--channel", required=True)
    p.add_argument("--po", required=True)
    p.add_argument("--fiori-url", required=True)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    po = json.loads(Path(a.po).read_text())
    message = build_channel_message(po, a.fiori_url)
    problems = validate_channel_message(message)
    if problems:
        sys.exit(f"message rejected locally: {problems}")
    if a.dry_run:
        print(json.dumps(message, indent=2))
        return
    token = os.environ.get("GRAPH_TOKEN") or sys.exit("set GRAPH_TOKEN")
    url = f"https://graph.microsoft.com/v1.0/teams/{a.team}/channels/{a.channel}/messages"
    req = urllib.request.Request(url, data=json.dumps(message).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            created = json.load(resp)
    except urllib.error.HTTPError as err:
        sys.exit(f"Graph returned {err.code}: {err.read().decode()[:500]}")
    state = ROOT / "state/cards.json"
    state.parent.mkdir(exist_ok=True)
    cards = json.loads(state.read_text()) if state.exists() else {}
    cards[created["id"]] = po["number"]
    state.write_text(json.dumps(cards, indent=2))
    print(json.dumps({"messageId": created["id"], "po": po["number"]}))


if __name__ == "__main__":
    main()
