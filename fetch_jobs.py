"""
fetch_jobs.py — Unified Job Fetcher
Pulls SWE + Data Science internship listings from:
  1. zapplyjobs/Internships-2026 GitHub README (markdown table parsing)
  2. Remotive public API
  3. Greenhouse public boards

Deduplicates across all sources by apply link.
Outputs: jobs.json
"""

import re
import json
import time
import logging
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass, asdict
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal-job-tracker/1.0)"}


@dataclass
class Job:
    title: str
    company: str
    location: str
    apply_url: str
    source: str
    category: str = ""
    age: str = ""
    posted_at: str = ""
    fetched_at: str = ""

    def key(self) -> str:
        return self.apply_url.strip().rstrip("/").lower()

    def to_dict(self):
        return asdict(self)


def fetch_github_repo_jobs(url: str, source_name: str, default_category: str = "SWE") -> list[Job]:
    """Generic scraper for GitHub internship README tables."""
    jobs = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        tables = soup.find_all("table")
        log.info(f"{source_name}: found {len(tables)} tables")

        current_category = default_category
        # We walk all elements to catch headers that define categories (common in US repo)
        all_elements = soup.find_all(["h1", "h2", "h3", "h4", "table"])

        for el in all_elements:
            if el.name in ("h1", "h2", "h3", "h4"):
                text = el.get_text().lower()
                if any(kw in text for kw in ["data science", "data", "analyst"]):
                    current_category = "Data Science"
                elif any(kw in text for kw in ["swe", "software", "engineering", "dev"]):
                    current_category = "SWE"

            elif el.name == "table":
                rows = el.find_all("tr")
                if not rows:
                    continue
                header_cells = rows[0].find_all(["th", "td"])
                headers = [c.get_text(strip=True).lower() for c in header_cells]
                
                # Minimum requirement: must have a link column
                if not any("apply" in h or "link" in h for h in headers):
                    continue

                col_map = {}
                for i, h in enumerate(headers):
                    if "company" in h:                              col_map["company"] = i
                    elif any(kw in h for kw in ["role", "position", "program", "opportunity"]): col_map["role"] = i
                    elif "location" in h:                           col_map["location"] = i
                    elif "apply" in h or "link" in h:               col_map["apply"] = i
                    elif any(kw in h for kw in ["age", "posted", "date"]): col_map["age"] = i

                if "apply" not in col_map:
                    continue

                for row in rows[1:]:
                    cells = row.find_all(["td", "th"])
                    if not cells:
                        continue

                    def cell_text(key):
                        idx = col_map.get(key)
                        return cells[idx].get_text(strip=True) if idx is not None and idx < len(cells) else ""

                    def cell_link(key):
                        idx = col_map.get(key)
                        if idx is None or idx >= len(cells):
                            return ""
                        # Check for <a> tag
                        a = cells[idx].find("a")
                        if a and a.get("href"):
                            return a["href"]
                        # Check for markdown style link inside text if BS4 missed it
                        text = cells[idx].get_text()
                        match = re.search(r'\]\((https?://[^\)]+)\)', text)
                        return match.group(1) if match else ""

                    company   = cell_text("company")
                    role      = cell_text("role")
                    location  = cell_text("location") or "Remote/Global"
                    apply_url = cell_link("apply")
                    age       = cell_text("age")

                    if not role or not apply_url or apply_url.startswith("#") or not company:
                        continue

                    jobs.append(Job(
                        title=role, company=company, location=location,
                        apply_url=apply_url, source=source_name,
                        category=current_category, age=age,
                        fetched_at=datetime.now().isoformat(),
                    ))

        log.info(f"{source_name}: {len(jobs)} jobs parsed")
    except Exception as e:
        log.error(f"{source_name} failed: {e}")
    return jobs

def fetch_zapplyjobs_github() -> list[Job]:
    return fetch_github_repo_jobs("https://github.com/zapplyjobs/Internships-2026", "GitHub/Global")

def fetch_canada_github() -> list[Job]:
    return fetch_github_repo_jobs("https://github.com/negarprh/Canadian-Tech-Internships-2026", "GitHub/Canada")

def fetch_europe_github() -> list[Job]:
    return fetch_github_repo_jobs("https://github.com/soongenwong/Europe-Tech-Internships-2026", "GitHub/Europe")


def fetch_remotive(roles=None) -> list[Job]:
    roles = roles or ["software engineer intern", "data science intern", "ml intern"]
    jobs = []
    for role in roles:
        try:
            resp = requests.get("https://remotive.com/api/remote-jobs",
                                params={"search": role, "limit": 20},
                                headers=HEADERS, timeout=10)
            resp.raise_for_status()
            for item in resp.json().get("jobs", []):
                jobs.append(Job(
                    title=item.get("title", ""),
                    company=item.get("company_name", ""),
                    location=item.get("candidate_required_location", "Remote"),
                    apply_url=item.get("url", ""),
                    source="Remotive",
                    category="SWE" if "engineer" in item.get("title","").lower() else "Data Science",
                    posted_at=item.get("publication_date", ""),
                    fetched_at=datetime.now().isoformat(),
                ))
            time.sleep(1)
        except Exception as e:
            log.warning(f"Remotive '{role}': {e}")
    log.info(f"Remotive: {len(jobs)} jobs")
    return jobs


GREENHOUSE_COMPANIES = [
    "anthropic", "openai", "stripe", "airbnb", "notion",
    "figma", "vercel", "databricks", "scale", "cohere",
    "shopify", "wealthsimple", "hootsuite", "revolut",
    "monzo", "deliveroo", "zalando", "spotify", "klarna", "mangroup",
]

def fetch_greenhouse(role_keywords=None) -> list[Job]:
    keywords = [k.lower() for k in (role_keywords or ["intern", "data", "engineer"])]
    jobs = []
    for company in GREENHOUSE_COMPANIES:
        try:
            url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code != 200:
                continue
            for item in resp.json().get("jobs", []):
                title = item.get("title", "")
                if not any(kw in title.lower() for kw in keywords):
                    continue
                jobs.append(Job(
                    title=title,
                    company=company.capitalize(),
                    location=item.get("location", {}).get("name", "Unknown"),
                    apply_url=item.get("absolute_url", ""),
                    source="Greenhouse",
                    category="Data Science" if any(k in title.lower() for k in ["data", "ml", "machine learning"]) else "SWE",
                    posted_at=item.get("updated_at", ""),
                    fetched_at=datetime.now().isoformat(),
                ))
            time.sleep(0.5)
        except Exception as e:
            log.debug(f"Greenhouse {company}: {e}")
    log.info(f"Greenhouse: {len(jobs)} jobs")
    return jobs


def dedup(jobs: list[Job]) -> list[Job]:
    seen = {}
    for job in jobs:
        k = job.key()
        if k and k not in seen:
            seen[k] = job
    result = list(seen.values())
    log.info(f"After dedup: {len(result)} unique (was {len(jobs)})")
    return result


def save(jobs: list[Job], path="jobs.json"):
    with open(path, "w") as f:
        json.dump([j.to_dict() for j in jobs], f, indent=2)
    log.info(f"Saved {len(jobs)} jobs → {path}")

def load(path="jobs.json") -> list[Job]:
    with open(path) as f:
        return [Job(**d) for d in json.load(f)]

def fetch_all(out_path="jobs.json") -> list[Job]:
    all_jobs = []
    all_jobs += fetch_zapplyjobs_github()
    all_jobs += fetch_canada_github()
    all_jobs += fetch_europe_github()
    all_jobs += fetch_remotive()
    all_jobs += fetch_greenhouse()
    unique = dedup(all_jobs)
    save(unique, out_path)
    return unique

if __name__ == "__main__":
    jobs = fetch_all()
    print(f"\n✅ {len(jobs)} unique jobs → jobs.json")
