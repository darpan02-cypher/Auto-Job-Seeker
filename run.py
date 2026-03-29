#!/usr/bin/env python3
"""
run.py — Job Application Tool

Commands:
  python run.py setup          # First time: validate profile.json + resume
  python run.py fetch          # Pull jobs from all sources → jobs.json
  python run.py apply          # Auto-fill + apply (Playwright)
  python run.py stats          # Summary of what you've applied to
  python run.py filter swe     # Preview SWE jobs
  python run.py filter ds      # Preview Data Science jobs
"""

import sys
import json
from pathlib import Path


def cmd_setup():
    """Check profile.json and resume exist and look valid."""
    print("\n🔧 Setup Check\n")
    errors = []

    # Profile
    if not Path("profile.json").exists():
        errors.append("❌ profile.json not found — copy the template and fill it in")
    else:
        with open("profile.json") as f:
            p = json.load(f)
        b = p.get("basic", {})
        missing = [k for k in ["first_name","last_name","email","phone"] if not b.get(k)]
        if missing:
            errors.append(f"❌ profile.json missing: {', '.join(missing)}")
        else:
            print(f"  ✅ Profile   : {b['first_name']} {b['last_name']}  <{b['email']}>")

        resume = p.get("resume_path", "resume.pdf")
        if not Path(resume).exists():
            errors.append(f"❌ Resume not found: {resume}  (put your PDF here)")
        else:
            print(f"  ✅ Resume    : {resume}  ({Path(resume).stat().st_size // 1024} KB)")

    # Playwright
    try:
        from playwright.sync_api import sync_playwright
        print(f"  ✅ Playwright : installed")
    except ImportError:
        errors.append("❌ Playwright not installed — run: pip install playwright && playwright install chromium")

    if errors:
        print("\nIssues found:")
        for e in errors:
            print(f"  {e}")
        print()
    else:
        print("\n  All good! Run: python run.py fetch\n")


def cmd_fetch():
    from fetch_jobs import fetch_all
    jobs = fetch_all()
    print(f"\n✅ {len(jobs)} unique jobs saved → jobs.json")
    print("   Next: python run.py apply\n")


def cmd_apply():
    from apply import run
    run()


def cmd_stats():
    applied = []
    if Path("applied.json").exists():
        with open("applied.json") as f:
            applied = json.load(f)

    jobs = []
    if Path("jobs.json").exists():
        with open("jobs.json") as f:
            jobs = json.load(f)

    from collections import Counter
    print(f"\n{'='*50}")
    print(f"  📊 Application Summary")
    print(f"{'='*50}")
    print(f"  Jobs fetched   : {len(jobs)}")
    print(f"  Applied        : {len(applied)}")
    print(f"  Remaining      : {len(jobs) - len(applied)}")

    if applied:
        by_src = Counter(r["source"] for r in applied)
        print(f"\n  By source:")
        for src, n in by_src.most_common():
            print(f"    {src}: {n}")

        print(f"\n  Last 5 applied:")
        for r in sorted(applied, key=lambda x: x.get("applied_at",""), reverse=True)[:5]:
            print(f"    ✅  {r['company']:<22} {r['title'][:35]}")

    print(f"{'='*50}\n")


def cmd_filter(args):
    if not args:
        print("Usage: python run.py filter swe | ds | <keyword>")
        return
    if not Path("jobs.json").exists():
        print("Run: python run.py fetch first")
        return

    with open("jobs.json") as f:
        jobs = json.load(f)

    kw = " ".join(args).lower()
    alias = {"ds": "data science", "swe": "swe"}
    kw = alias.get(kw, kw)

    filtered = [j for j in jobs
                if kw in j.get("category","").lower()
                or kw in j.get("title","").lower()
                or kw in j.get("company","").lower()]

    print(f"\n  {len(filtered)} jobs matching '{kw}':\n")
    for j in filtered:
        print(f"  [{j['source']:<20}] {j['company']:<22} {j['title'][:38]}")
    print()


COMMANDS = {
    "setup":  cmd_setup,
    "fetch":  cmd_fetch,
    "apply":  cmd_apply,
    "stats":  cmd_stats,
}

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("help", "--help"):
        print(__doc__)
    elif args[0] == "filter":
        cmd_filter(args[1:])
    elif args[0] in COMMANDS:
        COMMANDS[args[0]]()
    else:
        print(f"Unknown command: {args[0]}")
        print(f"Try: {', '.join(COMMANDS)}, filter")
