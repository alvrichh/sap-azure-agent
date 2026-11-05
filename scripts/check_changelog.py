#!/usr/bin/env python3
"""Checks CHANGELOG.md: Keep a Changelog layout with Semantic Versioning.

  python3 scripts/check_changelog.py

CL-01 an [Unreleased] section comes first
CL-02 every release heading is '## [MAJOR.MINOR.PATCH] - YYYY-MM-DD', versions strictly descending, dates not increasing
CL-03 section headings are the standard ones (Added, Changed, Deprecated, Removed, Fixed, Security) and not empty
CL-04 every version has a compare/release link at the bottom, and no link points to an unknown version
"""
import re
import sys
from datetime import date
from pathlib import Path

TEXT = (Path(__file__).resolve().parents[1] / "CHANGELOG.md").read_text()
SEMVER = r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
SECTIONS = {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"}
errors, passed = [], []


def check(ok, test_id, message):
    (passed if ok else errors).append(f"{test_id}: {message}")


headings = re.findall(r"^## \[([^\]]+)\](.*)$", TEXT, re.M)
check(bool(headings) and headings[0] == ("Unreleased", ""), "CL-01", "[Unreleased] is the first section")

releases, bad = [], []
for name, rest in headings[1:]:
    m = re.fullmatch(SEMVER, name)
    d = re.fullmatch(r" - (\d{4}-\d{2}-\d{2})", rest)
    if not m or not d:
        bad.append(f"## [{name}]{rest}")
        continue
    releases.append((tuple(int(x) for x in m.groups()), date.fromisoformat(d.group(1)), name))
ordered = all(a[0] > b[0] and a[1] >= b[1] for a, b in zip(releases, releases[1:]))
check(not bad and ordered and releases, "CL-02",
      f"{len(releases)} releases with valid SemVer and dates, newest first" + (f" — bad headings {bad}" if bad else "") + ("" if ordered else " — order"))

problems = []
for block in re.split(r"^## ", TEXT, flags=re.M)[1:]:
    title = block.splitlines()[0]
    subs = re.findall(r"^### (.+)$", block, re.M)
    problems += [f"{title}: '### {s}'" for s in subs if s not in SECTIONS]
    for s in re.split(r"^### .+$", block, flags=re.M)[1:]:
        if not re.search(r"^- ", s, re.M):
            problems.append(f"{title}: empty section")
    if not title.startswith("[Unreleased]") and not subs:
        problems.append(f"{title}: no sections")
check(not problems, "CL-03", "standard, non-empty sections" + (f" — {problems}" if problems else ""))

links = dict(re.findall(r"^\[([^\]]+)\]: (\S+)$", TEXT, re.M))
names = {"Unreleased", *(r[2] for r in releases)}
missing, unknown = names - set(links), set(links) - names
check(not missing and not unknown, "CL-04", "every version has a link" + (f" — missing {sorted(missing)}" if missing else "") + (f" — unknown {sorted(unknown)}" if unknown else ""))

print(f"Passed: {len(passed)}")
for p in passed:
    print(f"  PASS {p}")
for e in errors:
    print(f"  FAIL {e}")
sys.exit(1 if errors else 0)
