#!/usr/bin/env python3
"""Static validation of the Microsoft Graph + Teams approvals test case (no Graph, Teams or Azure needed).

  python3 examples/graph-teams-approvals/tests/validate_example.py
  python3 examples/graph-teams-approvals/tests/validate_example.py --strict   # also fail on unfilled <placeholders>
"""
import json
import py_compile
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
STRICT = "--strict" in sys.argv
TEMPLATE = REPO / "templates/bicep/eventhubs-graph-notifications.bicep"
PLACEHOLDER = re.compile(r"<[a-z][a-z0-9@.\-]*(?:-[a-z0-9@.]+)*>")
SECRET_PATTERNS = [re.compile(p, re.I) for p in [
    r"SharedAccessKey=", r"Endpoint=sb://", r"client_secret\s*[=:]\s*['\"][^<'\"]", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"Bearer\s+eyJ", r'"access_token"\s*:\s*"ey']]
TOO_BROAD = {"Group.ReadWrite.All", "ChannelMessage.ReadWrite.All", "Directory.ReadWrite.All", "Teamwork.Migrate.All",
             "Chat.ReadWrite.All", "Sites.FullControl.All"}

errors, warnings, passed = [], [], []


def check(ok, test_id, message):
    (passed if ok else errors).append(f"{test_id}: {message}")


# ST-01 JSON parses
bad = []
for f in ROOT.rglob("*.json"):
    try:
        json.loads(f.read_text())
    except json.JSONDecodeError as exc:
        bad.append(f"{f.relative_to(ROOT)}: {exc}")
check(not bad, "ST-01", f"all JSON files parse" + (f" — {bad}" if bad else ""))

sub = json.loads((ROOT / "graph/subscription-channel-messages.json").read_text())
settings = json.loads((ROOT / "config/settings.example.json").read_text())

# ST-02 subscription watches new channel messages/replies only
check(sub["changeType"] == "created" and re.fullmatch(r"/teams/[^/]+/channels/[^/]+/messages", sub["resource"]),
      "ST-02", "subscription is changeType=created on /teams/{id}/channels/{id}/messages")

# ST-03 Event Hubs delivery with Entra RBAC (no Key Vault/SAS URL) and tenantId
rbac_url = re.compile(r"^EventHub:https://[^/]+\.servicebus\.windows\.net/eventhubname/[^?]+\?tenantId=.+$")
check(bool(rbac_url.match(sub["notificationUrl"])), "ST-03", "notificationUrl uses Event Hubs with RBAC and tenantId")

# ST-04 lifecycle notifications configured (required for chatMessage subscriptions > 1 hour)
check(bool(rbac_url.match(sub.get("lifecycleNotificationUrl", ""))), "ST-04", "lifecycleNotificationUrl set (Event Hubs)")

# ST-05 no resource data -> no encryption certificate needed; clientState present and not hardcoded
check(sub["includeResourceData"] is False and "encryptionCertificate" not in sub, "ST-05",
      "notifications without resource data (no certificate to manage)")
check(PLACEHOLDER.search(sub["clientState"]) is not None, "ST-06", "clientState is a placeholder, not a committed value")

# ST-07 least privilege in the documented permissions
perms = set(settings["entra"]["delegatedPermissions"]) | set(settings["entra"]["productionListenerPermissions"])
check(not (perms & TOO_BROAD) and "ChannelMessage.Send" in perms, "ST-07",
      f"permissions are least privilege {sorted(perms)}" + (f" — too broad: {perms & TOO_BROAD}" if perms & TOO_BROAD else ""))

# ST-08 the token script requests only the documented delegated scopes
token_py = (ROOT / "scripts/get_token.py").read_text()
scopes = set(re.findall(r"https://graph\.microsoft\.com/([\w.]+)", token_py))
check(scopes == set(settings["entra"]["delegatedPermissions"]), "ST-08", f"device-code scopes match settings {sorted(scopes)}")

# ST-09 Bicep: no SAS, Graph Change Tracking = Data Sender, consumer = Data Receiver
bicep = TEMPLATE.read_text()
check("disableLocalAuth: true" in bicep, "ST-09", "Event Hubs local (SAS) authentication disabled")
check("2b629674-e913-4c01-ae53-ef4638d8f975" in bicep and "graphChangeTrackingPrincipalId" in bicep
      and "a638d3c7-ab3a-418d-83e6-5f17a39d4fde" in bicep, "ST-10",
      "Graph Change Tracking gets Data Sender; consumer gets Data Receiver (role IDs verified)")

# ST-11 parameter file references the template and the hub name matches the subscription
param = (ROOT / "bicep/eventhubs.dev.bicepparam").read_text()
using = re.search(r"using\s+'([^']+)'", param).group(1)
hub = re.search(r"param eventHubName = '([^']+)'", param).group(1)
check((ROOT / "bicep" / using).resolve() == TEMPLATE and f"/eventhubname/{hub}?" in sub["notificationUrl"]
      and settings["eventHubs"]["hub"] == hub, "ST-11", f"parameters → template; hub '{hub}' consistent with subscription and settings")

# ST-12 scripts compile
compiled = []
for f in sorted((ROOT / "scripts").glob("*.py")):
    try:
        py_compile.compile(str(f), doraise=True)
        compiled.append(f.name)
    except py_compile.PyCompileError as exc:
        errors.append(f"ST-12: {f.name} does not compile ({exc.msg})")
check(len(compiled) == 3, "ST-12", f"scripts compile {compiled}")

# ST-13 tokens only from environment, never from files
post = (ROOT / "scripts/post_card.py").read_text() + (ROOT / "scripts/consume.py").read_text()
writes_token = re.search(r"\bopen\(|write_text\(|\.write\(", re.sub(r"#.*", "", token_py))
check('os.environ.get("GRAPH_TOKEN")' in post and not writes_token, "ST-13",
      "Graph tokens are read from the environment and never written to disk")

# ST-14 no secrets anywhere (example and template)
hits = []
for f in [*ROOT.rglob("*"), TEMPLATE]:
    if f.is_file() and f.suffix in {".json", ".bicep", ".bicepparam", ".py", ".md"} and f.name != "validate_example.py":
        hits += [f"{f.name}: {p.pattern}" for p in SECRET_PATTERNS if p.search(f.read_text())]
check(not hits, "ST-14", "no secrets or tokens in any file" + (f" — {hits}" if hits else ""))

# ST-15 unit tests pass
ut = subprocess.run([sys.executable, str(ROOT / "tests/test_units.py")], capture_output=True, text=True)
summary = (ut.stderr.strip().splitlines() or ["?"])
ran = next((line for line in summary if line.startswith("Ran ")), "?")
check(ut.returncode == 0, "ST-15", f"unit tests pass ({ran})" + ("" if ut.returncode == 0 else f"\n{ut.stderr[-1500:]}"))

# Placeholders (deployment readiness)
pending = []
for f in [ROOT / "config/settings.example.json", ROOT / "graph/subscription-channel-messages.json",
          *ROOT.glob("bicep/*.bicepparam")]:
    pending += [f"{f.name}: {ph}" for ph in sorted(set(PLACEHOLDER.findall(f.read_text())))]
if pending:
    (errors if STRICT else warnings).append(f"PH-01: {len(pending)} placeholders still to fill before deployment")

print(f"Passed: {len(passed)}")
for p in passed:
    print(f"  PASS {p}")
for w in warnings:
    print(f"  WARN {w}")
for e in errors:
    print(f"  FAIL {e}")
if pending and (STRICT or "--verbose" in sys.argv):
    for p in pending:
        print(f"       {p}")
sys.exit(1 if errors else 0)
