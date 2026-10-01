#!/usr/bin/env python3
"""Usage: summarize_tests.py test.json [coverage.out]  -> markdown test and coverage summary.

Reads the output of `go test -json`; lines that are not JSON are ignored.
"""
import json
import os
import shutil
import subprocess
import sys


def main():
    path = sys.argv[1]
    cover = sys.argv[2] if len(sys.argv) > 2 else ""
    counts = {"pass": 0, "fail": 0, "skip": 0}
    failed = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if not ev.get("Test") or ev.get("Action") not in counts:
                continue
            counts[ev["Action"]] += 1
            if ev["Action"] == "fail":
                failed.append(f'{ev.get("Package", "")} {ev["Test"]}'.strip())
    print("| Passed | Failed | Skipped |")
    print("|---|---|---|")
    print(f'| {counts["pass"]} | {counts["fail"]} | {counts["skip"]} |')
    if cover and os.path.exists(cover) and shutil.which("go"):
        out = subprocess.run(["go", "tool", "cover", f"-func={cover}"], capture_output=True, text=True, check=False).stdout
        total = [ln.split()[-1] for ln in out.splitlines() if ln.startswith("total:")]
        if total:
            print(f"\n**Total coverage:** {total[0]}")
    if failed:
        print("\n**Failed tests:**")
        for name in failed:
            print(f"- `{name}`")


if __name__ == "__main__":
    main()
