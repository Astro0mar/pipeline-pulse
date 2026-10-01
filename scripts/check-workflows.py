#!/usr/bin/env python3
"""Offline sanity checks for .github/workflows (needs PyYAML).

Verifies: valid YAML, `needs` targets exist, local reusable workflows exist,
`with:` keys match declared inputs, required inputs and secrets are provided.
"""
import pathlib
import re
import sys

import yaml

WF = pathlib.Path(".github/workflows")
errors = []


def load(path):
    data = yaml.safe_load(path.read_text())
    triggers = data.get("on", data.get(True))  # PyYAML parses the key `on` as True
    if isinstance(triggers, str):
        triggers = {triggers: None}
    elif isinstance(triggers, list):
        triggers = {t: None for t in triggers}
    return data, triggers


files = {p.name: load(p) for p in sorted(WF.glob("*.yml"))}
for name, (data, trig) in files.items():
    jobs = data.get("jobs") or {}
    if not jobs:
        errors.append(f"{name}: no jobs")
    for jid, job in jobs.items():
        needs = job.get("needs", [])
        for n in [needs] if isinstance(needs, str) else needs:
            if n not in jobs:
                errors.append(f"{name}: job {jid} needs unknown job {n}")
        uses = job.get("uses")
        if not uses:
            if "runs-on" not in job or "steps" not in job:
                errors.append(f"{name}: job {jid} lacks runs-on or steps")
            continue
        target = pathlib.Path(uses).name
        if target not in files:
            errors.append(f"{name}: job {jid} uses missing workflow {uses}")
            continue
        callee = files[target][1]
        if not isinstance(callee, dict) or "workflow_call" not in callee:
            errors.append(f"{target}: is called but has no workflow_call trigger")
            continue
        spec = callee["workflow_call"] or {}
        inputs = spec.get("inputs") or {}
        secrets = spec.get("secrets") or {}
        given = job.get("with") or {}
        for key in given:
            if key not in inputs:
                errors.append(f"{name}: job {jid} passes unknown input {key} to {target}")
        for key, meta in inputs.items():
            if meta.get("required") and key not in given:
                errors.append(f"{name}: job {jid} missing required input {key} for {target}")
        if secrets and job.get("secrets") != "inherit":
            errors.append(f"{name}: job {jid} must pass secrets (use secrets: inherit)")

for p in sorted(WF.glob("*.yml")):
    for ref in set(re.findall(r"scripts/[\w.-]+", p.read_text())):
        if ref != "scripts/" and not pathlib.Path(ref).exists() and "*" not in ref:
            errors.append(f"{p.name}: references missing {ref}")

if errors:
    print("\n".join(f"FAIL {e}" for e in errors))
    sys.exit(1)
print(f"OK: {len(files)} workflows checked")
