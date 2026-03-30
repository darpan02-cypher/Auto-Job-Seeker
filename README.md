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

## 🎯 Auto-Job-Seeker

A powerful, automated job application tool that finds internships (SWE, Data Science, ML) and auto-fills Greenhouse and Lever application forms using Playwright. Now featuring a sleek **Streamlit UI** for effortless job management.

---

## 🚀 Quick Start (For New Systems)

To run this project on a new machine, follow these steps:

### 1. Clone & Install Dependencies
Ensure you have Python 3.9+ installed.

```bash
# Clone the repository
git clone https://github.com/darpan02-cypher/Auto-Job-Seeker.git
cd Auto-Job-Seeker

# Install required Python packages
python3 -m pip install requests beautifulsoup4 playwright streamlit pandas pypdf

# Install Playwright browser binaries
python3 -m playwright install chromium
```

### 2. Setup Your Profile
The tool uses `profile.json` and a PDF resume to fill applications.

1.  **Fill `profile.json`**: Enter your contact info, education, experience, and common answers.
2.  **Add Resume**: Place your resume PDF in the project folder and update the `"resume_path"` in `profile.json` with the absolute path.

### 3. Verify Setup
Run the setup check to ensure everything is configured correctly:
```bash
python3 run.py setup
```

---

## 🖥️ Using the Streamlit UI (Recommended)

The easiest way to use the tool is through the web-based dashboard.

### Launch the Dashboard
```bash
python3 -m streamlit run app.py
```

### Key UI Features:
- **🔄 Live Fetching**: Click "Fetch New Jobs" in the sidebar to pull the latest listings from GitHub, Remotive, and Greenhouse.
- **🕒 Smart Filtering**: Filter jobs by **Actual Posted Date** (Past 24h, Past Week) and **Source** (GitHub, Remotive, etc.).
- **🤖 One-Click Auto-Fill**: Select a job and hit "Auto-Fill". Playwright will open a browser, fill the form, and attach your resume.
- **↩️ Undo/Revert**: Made a mistake? Go to the **Analytics** tab and revert any applied/skipped job back to your pending list.
- **📊 Analytics**: Visualize your application progress with charts showing sources and categories.

---

## ⌨️ CLI Usage (Alternative)

If you prefer the terminal, you can still use the original commands:

- `python3 run.py fetch`: Pull fresh jobs from all sources.
- `python3 run.py apply`: Start the interactive terminal apply session.
- `python3 run.py stats`: See a summary of your applications.
- `python3 run.py filter <keyword>`: Search for specific jobs (e.g., `swe`, `data`, `stripe`).

---

## 📂 Project Structure

- `app.py`: The Streamlit frontend application.
- `profile.json`: Your personal data (never share this!).
- `fetch_jobs.py`: The scraping engine for Job Boards and APIs.
- `autofill.py`: The Playwright logic for Greenhouse/Lever forms.
- `jobs.json`: Currently fetched jobs (refreshed daily).
- `applied.json`: Your permanent log of successful applications.

---

## 🛠️ How Auto-Fill Works

The tool detects if a link is for **Greenhouse** or **Lever** and automatically fills:
- **Personal Info**: Name, Email, Phone, Location.
- **Socials**: LinkedIn, GitHub, Portfolio.
- **Documents**: Uploads your Resume PDF directly.
- **Questions**: Answers "Why are you interested?", "Salary expectations", and "Start date" using your predefined answers.
- **Sponsorship**: Handles "Are you authorized to work in the US?" and "Do you require sponsorship?".

**Note**: The tool *never* clicks "Submit" for you. It pauses so you can review details, fix any edge cases, and click the final button yourself.

---

## 🔒 Privacy & Security
- All data (including `profile.json` and `applied.json`) stays **local** on your machine. 
- Ensure you don't commit your `profile.json` to public repositories.

---

Developed for high-efficiency job seekers. 🚀
