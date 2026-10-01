#!/usr/bin/env python3
"""Usage:
  trivy_report.py count   report.json          -> prints the number of findings
  trivy_report.py summary report.json [title]  -> prints a markdown findings table

Findings are CVEs, secrets and misconfigurations from a Trivy JSON report
(already filtered to HIGH and CRITICAL by the scan step).
"""
import json
import sys

ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def findings(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    rows = []
    for res in data.get("Results") or []:
        target = res.get("Target", "")
        for v in res.get("Vulnerabilities") or []:
            rows.append((v.get("Severity", ""), "CVE", v.get("VulnerabilityID", ""),
                         f'{v.get("PkgName", "")} {v.get("InstalledVersion", "")}', v.get("FixedVersion") or "-"))
        for s in res.get("Secrets") or []:
            rows.append((s.get("Severity", ""), "Secret", s.get("RuleID", ""), target, "-"))
        for m in res.get("Misconfigurations") or []:
            rows.append((m.get("Severity", ""), "Config", m.get("ID", ""), target, "-"))
    return sorted(rows, key=lambda r: ORDER.get(r[0], 9))


def main():
    mode, path = sys.argv[1], sys.argv[2]
    rows = findings(path)
    if mode == "count":
        print(len(rows))
        return
    print(f"#### {sys.argv[3] if len(sys.argv) > 3 else 'Trivy'}")
    if not rows:
        print("✅ No fixable HIGH or CRITICAL findings.")
        return
    print(f"❌ **{len(rows)}** finding(s) at HIGH or CRITICAL.\n")
    print("| Severity | Type | ID | Package or target | Fixed in |")
    print("|---|---|---|---|---|")
    for r in rows[:15]:
        print("| " + " | ".join(r) + " |")
    if len(rows) > 15:
        print(f"\n…and {len(rows) - 15} more. See the Security tab for the full list.")


if __name__ == "__main__":
    main()
