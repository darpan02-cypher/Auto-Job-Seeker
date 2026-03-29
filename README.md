# Job Apply Tool — with Auto-fill

## First time setup

```bash
pip install requests beautifulsoup4 playwright
playwright install chromium

python run.py setup   # checks everything is ready
```

## Step 1 — Fill your profile (do this once)

Edit `profile.json` with your real info:

```json
{
  "basic": {
    "first_name": "Jane",
    "last_name":  "Smith",
    "email":      "jane@email.com",
    "phone":      "555-123-4567",
    "location":   "San Francisco, CA",
    "linkedin":   "https://linkedin.com/in/janesmith",
    "github":     "https://github.com/janesmith"
  },
  "education": {
    "school":           "State University",
    "degree":           "Bachelor of Science",
    "major":            "Computer Science",
    "gpa":              "3.7",
    "graduation_year":  "2025"
  },
  "work_authorization": {
    "authorized_us":       true,
    "requires_sponsorship": false
  },
  "resume_path": "resume.pdf",   ← put your PDF in this folder
  ...
}
```

Drop your `resume.pdf` in the same folder.

## Step 2 — Fetch jobs

```bash
python run.py fetch
```

Pulls from: GitHub/zapplyjobs (SWE + DS internships), Remotive, Greenhouse boards.

## Step 3 — Apply

```bash
python run.py apply
```

For each job you'll see:

```
──────────────────────────────────────────────────────────────
  [1/47]  SWE  ·  🌱 Greenhouse
  Role    : Software Engineering Intern
  Company : Stripe
  Location: San Francisco, CA
  Source  : GitHub/zapplyjobs  1d
  Link    : https://stripe.greenhouse.io/...
──────────────────────────────────────────────────────────────
  Action [f/o/s/q] →
```

- **`f`** — auto-fill the form using your profile + attach your resume, then pause for your review. You click Submit.
- **`o`** — just open the link in browser (if the site isn't Greenhouse/Lever)
- **`s`** — skip this job
- **`q`** — quit session

After auto-fill, the browser stays open. You check every field, fix anything wrong, then Submit. The tool asks "Did you submit? y/n" — only then does it log it.

## Step 4 — Check your stats

```bash
python run.py stats
```

## Other commands

```bash
python run.py filter swe          # preview SWE jobs only
python run.py filter datascience  # DS jobs only
python run.py filter stripe       # filter by company name
```

## Files

```
profile.json    ← your info (fill once)
resume.pdf      ← your resume (drop here)
jobs.json       ← fetched jobs (refreshed each fetch)
applied.json    ← your application log (never overwritten)
```

## How dedup works

- Same job URL from multiple sources → shown only once
- Already in `applied.json` → skipped automatically, every session
- You will never be shown the same job twice

## What gets auto-filled (Greenhouse/Lever)

| Field | Source in profile.json |
|-------|----------------------|
| First / Last name | `basic.first_name`, `basic.last_name` |
| Email | `basic.email` |
| Phone | `basic.phone` |
| Location | `basic.location` |
| LinkedIn URL | `basic.linkedin` |
| GitHub URL | `basic.github` |
| Resume PDF | `resume_path` (uploaded directly) |
| Cover letter | `cover_letter_template` (filled with job+company name) |
| Work authorization | `work_authorization.authorized_us` |
| Sponsorship needed | `work_authorization.requires_sponsorship` |
| Demographic fields | `demographic.*` (optional, your choice) |
| "Why interested?" | `common_answers.why_interested` |
| Start date | `common_answers.start_date` |

Education fields filled where the form has them. All other fields remain blank for you to fill manually in the browser before submitting.

## Note on Jobright.ai

jobright.ai requires login to see recommendations — it can't be scraped without your credentials. Open it manually in your browser. The dedup in `applied.json` still prevents double-applying.
