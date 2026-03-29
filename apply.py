"""
apply.py — Apply workflow with Playwright auto-fill.

For each job:
  1. Shows job details
  2. Auto-fills the Greenhouse/Lever form using your profile
  3. Opens browser — you review and click Submit yourself
  4. You confirm → logged to applied.json
"""

import json
import sys
import logging
from datetime import datetime
from pathlib import Path

from autofill import autofill, load_profile, detect_platform

logging.basicConfig(level=logging.WARNING, format="%(message)s")

JOBS_FILE    = "jobs.json"
APPLIED_FILE = "applied.json"
PROFILE_FILE = "profile.json"


def load_jobs() -> list[dict]:
    if not Path(JOBS_FILE).exists():
        print("No jobs.json. Run: python run.py fetch")
        sys.exit(1)
    with open(JOBS_FILE) as f:
        return json.load(f)


def load_applied() -> dict:
    if not Path(APPLIED_FILE).exists():
        return {}
    with open(APPLIED_FILE) as f:
        records = json.load(f)
    return {r["apply_url"].strip().lower(): r for r in records}


def save_applied(applied: dict):
    with open(APPLIED_FILE, "w") as f:
        json.dump(list(applied.values()), f, indent=2)


def normalize(url: str) -> str:
    return url.strip().rstrip("/").lower()


def show_job(job: dict, idx: int, total: int):
    platform = detect_platform(job["apply_url"])
    platform_badge = {
        "greenhouse": "🌱 Greenhouse",
        "lever":      "⚙️  Lever",
    }.get(platform, "🔗 Direct")

    print("\n" + "─" * 62)
    print(f"  [{idx}/{total}]  {job.get('category','').upper()}  ·  {platform_badge}")
    print(f"  Role    : {job['title']}")
    print(f"  Company : {job['company']}")
    print(f"  Location: {job['location']}")
    print(f"  Source  : {job['source']}  {job.get('age','')}")
    print(f"  Link    : {job['apply_url']}")
    print("─" * 62)


def prompt(msg: str, options: str) -> str:
    valid = [o.strip() for o in options.lower().split("/")]
    while True:
        ans = input(f"  {msg} [{options}] → ").strip().lower()
        if ans in valid:
            return ans
        print(f"  Enter one of: {options}")


def run():
    profile = load_profile(PROFILE_FILE)
    jobs    = load_jobs()
    applied = load_applied()

    pending = [j for j in jobs if normalize(j["apply_url"]) not in applied]

    print(f"\n🎯  Job Apply Workflow  (Playwright auto-fill)")
    print(f"    Profile   : {profile['basic'].get('first_name','')} {profile['basic'].get('last_name','')}")
    print(f"    Resume    : {profile.get('resume_path','resume.pdf')}")
    print(f"    Fetched   : {len(jobs)}  |  Applied: {len(applied)}  |  Remaining: {len(pending)}")
    print(f"\n    [f] auto-fill + open   [o] just open   [s] skip   [q] quit\n")

    applied_this_session = 0

    for i, job in enumerate(pending, 1):
        key = normalize(job["apply_url"])
        show_job(job, i, len(pending))

        action = prompt("Action", "f/o/s/q")

        if action == "q":
            print("\n  👋 Exiting.")
            break

        elif action == "f":
            # Inject current job context so autofill can personalize cover letter
            profile["_current_job_title"] = job["title"]
            profile["_current_company"]   = job["company"]

            platform = detect_platform(job["apply_url"])
            if platform == "unknown":
                print(f"  ⚠️  Not a Greenhouse/Lever link — falling back to generic fill.")

            success = autofill(job["apply_url"], profile)

            if success:
                confirm = prompt("Did you submit?", "y/n")
                if confirm == "y":
                    applied[key] = _make_record(job)
                    save_applied(applied)
                    print(f"  ✅ Logged: {job['company']} — {job['title']}")
                    applied_this_session += 1
                else:
                    print("  ⏭  Not logged.")
            else:
                print("  ⚠️  Auto-fill failed. Try [o] to open manually.")

        elif action == "o":
            import webbrowser
            webbrowser.open(job["apply_url"])
            print("  🔗 Opened in browser.")
            confirm = prompt("Did you submit?", "y/n")
            if confirm == "y":
                applied[key] = _make_record(job)
                save_applied(applied)
                print(f"  ✅ Logged: {job['company']} — {job['title']}")
                applied_this_session += 1

        elif action == "s":
            print("  ⏭  Skipped.")

    print(f"\n  Session done. Submitted {applied_this_session} application(s).")
    print(f"  Total logged: {len(applied)}  →  {APPLIED_FILE}\n")


def _make_record(job: dict) -> dict:
    return {
        "title":       job["title"],
        "company":     job["company"],
        "apply_url":   job["apply_url"],
        "source":      job["source"],
        "category":    job.get("category", ""),
        "status":      "applied",
        "applied_at":  datetime.now().isoformat(),
    }


if __name__ == "__main__":
    run()
