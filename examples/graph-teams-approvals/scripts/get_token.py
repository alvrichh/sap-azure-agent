#!/usr/bin/env python3
"""Get a delegated Microsoft Graph token with the device code flow (public client, no secret).

  export GRAPH_TOKEN=$(python3 scripts/get_token.py --tenant <tenant-id> --client-id <app-client-id>)

Sign in as the service account (to post) or as yourself (to read). The token is printed to stdout only.
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

SCOPES = "https://graph.microsoft.com/ChannelMessage.Send https://graph.microsoft.com/ChannelMessage.Read.All"


def post(url, data):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode())
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as err:
        return json.load(err)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tenant", required=True)
    p.add_argument("--client-id", required=True)
    p.add_argument("--scopes", default=SCOPES)
    a = p.parse_args()
    base = f"https://login.microsoftonline.com/{a.tenant}/oauth2/v2.0"
    code = post(f"{base}/devicecode", {"client_id": a.client_id, "scope": a.scopes})
    if "device_code" not in code:
        sys.exit(f"device code request failed: {code.get('error_description', code)}")
    print(code["message"], file=sys.stderr)
    interval = int(code.get("interval", 5))
    while True:
        time.sleep(interval)
        tok = post(f"{base}/token", {"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                                     "client_id": a.client_id, "device_code": code["device_code"]})
        if "access_token" in tok:
            print(tok["access_token"])
            return
        if tok.get("error") == "slow_down":
            interval += 5
        elif tok.get("error") != "authorization_pending":
            sys.exit(f"sign-in failed: {tok.get('error_description', tok)}")


if __name__ == "__main__":
    main()
