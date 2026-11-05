#!/usr/bin/env python3
"""Prints the CHANGELOG.md section of one version, for the GitHub Release body.

  python3 scripts/release_notes.py v0.7.0
Fails if the version has no section, so a tag can't be released without changelog notes.
"""
import re
import sys
from pathlib import Path

version = sys.argv[1].removeprefix("v")
text = (Path(__file__).resolve().parents[1] / "CHANGELOG.md").read_text()
match = re.search(rf"^## \[{re.escape(version)}\] - [0-9-]+\n(.*?)(?=^## \[|^\[[^\]]+\]: )", text, re.M | re.S)
if not match:
    sys.exit(f"CHANGELOG.md has no section for {version}")
notes = match.group(1).strip()
print(notes)
print(f"\nFull history: [CHANGELOG.md](https://github.com/alvrichh/sap-azure-agent/blob/v{version}/CHANGELOG.md)")
