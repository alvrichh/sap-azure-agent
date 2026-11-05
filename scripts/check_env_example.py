#!/usr/bin/env python3
"""Checks the repository's configuration template and secret hygiene (no Azure or SAP needed).

  python3 scripts/check_env_example.py

EV-01 .env.example is tracked (not ignored) and a local .env would be ignored by Git
EV-02 every line is a comment, blank, or NAME=value with an unique UPPER_SNAKE_CASE name
EV-03 secret-like variables (tokens, passwords, passphrases, client secrets, SAS trigger URLs) are empty
EV-04 no value looks like a real secret (SAS signature, account key, private key, JWT, long base64)
EV-05 every environment variable that the repository's scripts and runbooks read is listed
EV-06 the Snowflake linked service uses key-pair auth with Key Vault references (no inline secrets)
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENV = REPO / ".env.example"
SECRET_NAME = re.compile(r"^(?!.*_SECRET_NAME$).*(?:(?:^|_)(?:TOKEN|PASSWORD|PASSPHRASE|CLIENT_SECRET|CLIENT_STATE|CONNECTION_STRING|ACCOUNT_KEY)(?:_|$)|TRIGGER_URL$)")
SECRET_VALUE = [re.compile(p) for p in [r"[?&]sig=", r"AccountKey=", r"SharedAccessKey=", r"-----BEGIN", r"\beyJ[A-Za-z0-9_-]{10,}\.",
                                        r"[A-Za-z0-9+/]{40,}={0,2}"]]
# Shell variables that are internal to a script, not configuration
INTERNAL = {"BASE", "ARM_TOKEN", "GITHUB_WORKSPACE", "PARAMS_FILE", "BICEP_FILE", "HOME", "PATH", "AUTH"}

errors, passed = [], []


def check(ok, test_id, message):
    (passed if ok else errors).append(f"{test_id}: {message}")


def ignored(path):
    return subprocess.run(["git", "check-ignore", "-q", path], cwd=REPO).returncode == 0


# EV-01
check(ENV.is_file() and not ignored(".env.example") and ignored(".env"), "EV-01",
      ".env.example exists and is tracked; .env is ignored by Git")

# EV-02
values, bad = {}, []
for n, line in enumerate(ENV.read_text().splitlines(), 1):
    if not line.strip() or line.lstrip().startswith("#"):
        continue
    m = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(.*)", line)
    if not m or m.group(1) in values:
        bad.append(f"line {n}: {line[:40]}")
        continue
    values[m.group(1)] = m.group(2)
check(not bad and values, "EV-02", f"{len(values)} variables, all NAME=value and unique" + (f" — {bad}" if bad else ""))

# EV-03
filled = [k for k, v in values.items() if SECRET_NAME.search(k) and v.strip()]
check(not filled, "EV-03", f"{sum(1 for k in values if SECRET_NAME.search(k))} secret-like variables left empty" + (f" — filled: {filled}" if filled else ""))

# EV-04
hits = [k for k, v in values.items() if any(p.search(v) for p in SECRET_VALUE)]
check(not hits, "EV-04", "no value looks like a secret" + (f" — {hits}" if hits else ""))

# EV-05 variables read by scripts (${X:?}, ${X:-}, os.environ.get("X")) and used as "$X" in runbooks
needed = {}
for f in REPO.rglob("*"):
    if ".git" in f.parts or not f.is_file() or f.suffix not in {".sh", ".py", ".md"} or f == Path(__file__).resolve():
        continue
    text = f.read_text(errors="ignore")
    found = set(re.findall(r"\$\{([A-Z][A-Z0-9_]+):[?-]", text)) | set(re.findall(r"os\.environ(?:\.get)?\(\s*[\"']([A-Z][A-Z0-9_]+)", text))
    if f.suffix == ".md":
        found |= set(re.findall(r"\"\$([A-Z][A-Z0-9_]+)\"", text))
    for name in found - INTERNAL:
        needed.setdefault(name, f.relative_to(REPO).as_posix())
missing = {k: v for k, v in needed.items() if k not in values}
check(not missing, "EV-05", f"{len(needed)} variables read by scripts and runbooks are listed" + (f" — missing {missing}" if missing else ""))

# EV-06
ls = json.loads((REPO / "templates/adf/linked-services/snowflake-v2.json").read_text())["properties"]["typeProperties"]
check(ls.get("authenticationType") == "KeyPair" and "password" not in ls
      and all(ls.get(k, {}).get("type") == "AzureKeyVaultSecret" for k in ("privateKey", "privateKeyPassphrase")),
      "EV-06", "Snowflake linked service: key-pair auth, private key and passphrase from Key Vault")

print(f"Passed: {len(passed)}")
for p in passed:
    print(f"  PASS {p}")
for e in errors:
    print(f"  FAIL {e}")
sys.exit(1 if errors else 0)
