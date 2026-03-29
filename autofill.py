"""
autofill.py — Playwright auto-filler for Greenhouse & Lever job applications.

Detects which platform the URL is for, then fills every visible field
using your profile.json. Pauses for your review before anything is submitted.
You always click Submit yourself.
"""

import json
import time
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def load_profile(path: str = "profile.json") -> dict:
    if not Path(path).exists():
        raise FileNotFoundError(f"profile.json not found at {path}. Copy the template and fill it.")
    with open(path) as f:
        return json.load(f)


def detect_platform(url: str) -> str:
    url = url.lower()
    if "greenhouse.io" in url or "boards.greenhouse" in url:
        return "greenhouse"
    if "lever.co" in url:
        return "lever"
    return "unknown"


# ─── Shared helpers ────────────────────────────────────────────────────────────

def safe_fill(page, selector: str, value: str, label: str = ""):
    """Fill a field if it exists and value is non-empty."""
    if not value:
        return
    try:
        el = page.locator(selector).first
        if el.count() == 0:
            return
        if el.is_visible(timeout=2000):
            el.fill(str(value))
            log.debug(f"  ✓ {label or selector} → {value[:40]}")
    except Exception as e:
        log.debug(f"  skip {label}: {e}")


def safe_select(page, selector: str, value: str, label: str = ""):
    """Select a dropdown option by value or label text."""
    if not value:
        return
    try:
        el = page.locator(selector).first
        if el.is_visible(timeout=2000):
            try:
                el.select_option(value=value)
            except Exception:
                el.select_option(label=value)
            log.debug(f"  ✓ dropdown {label} → {value}")
    except Exception as e:
        log.debug(f"  skip dropdown {label}: {e}")


def safe_check(page, selector: str, label: str = ""):
    """Check a checkbox if unchecked."""
    try:
        el = page.locator(selector).first
        if el.is_visible(timeout=2000) and not el.is_checked():
            el.check()
            log.debug(f"  ✓ checked {label}")
    except Exception as e:
        log.debug(f"  skip checkbox {label}: {e}")


def fill_resume(page, resume_path: str):
    """Attach resume PDF to any file upload input."""
    if not resume_path or not Path(resume_path).exists():
        log.warning(f"  Resume not found: {resume_path} — skipping upload")
        return
    try:
        # Most ATS use input[type=file] for resume
        inputs = page.locator("input[type='file']")
        for i in range(inputs.count()):
            inp = inputs.nth(i)
            parent_text = inp.locator("..").inner_text() if inp.count() else ""
            if any(kw in parent_text.lower() for kw in ["resume", "cv", "upload"]):
                inp.set_input_files(str(Path(resume_path).resolve()))
                log.debug(f"  ✓ Resume uploaded: {resume_path}")
                return
        # Fallback: first file input
        if inputs.count() > 0:
            inputs.first.set_input_files(str(Path(resume_path).resolve()))
            log.debug(f"  ✓ Resume uploaded (fallback): {resume_path}")
    except Exception as e:
        log.warning(f"  Resume upload failed: {e}")


# ─── Greenhouse ────────────────────────────────────────────────────────────────

def fill_greenhouse(page, profile: dict, job_title: str = "", company: str = ""):
    """Fill a Greenhouse application form."""
    b = profile.get("basic", {})
    edu = profile.get("education", {})
    auth = profile.get("work_authorization", {})
    demo = profile.get("demographic", {})
    answers = profile.get("common_answers", {})

    log.info("  Filling Greenhouse form...")

    # ── Basic info ──
    safe_fill(page, "#first_name",          b.get("first_name"), "first name")
    safe_fill(page, "#last_name",           b.get("last_name"),  "last name")
    safe_fill(page, "#email",               b.get("email"),      "email")
    safe_fill(page, "#phone",               b.get("phone"),      "phone")
    safe_fill(page, "#job_application_location", b.get("location"), "location")

    # Greenhouse sometimes uses these selectors too
    safe_fill(page, "input[name='job_application[first_name]']", b.get("first_name"), "first name alt")
    safe_fill(page, "input[name='job_application[last_name]']",  b.get("last_name"),  "last name alt")
    safe_fill(page, "input[name='job_application[email]']",      b.get("email"),      "email alt")
    safe_fill(page, "input[name='job_application[phone]']",      b.get("phone"),      "phone alt")

    # ── Links ──
    safe_fill(page, "#job_application_linkedin_profile_url", b.get("linkedin"), "linkedin")
    safe_fill(page, "#job_application_website",              b.get("portfolio") or b.get("github"), "website")
    safe_fill(page, "input[id*='linkedin']",                 b.get("linkedin"), "linkedin alt")
    safe_fill(page, "input[id*='github']",                   b.get("github"),   "github alt")
    safe_fill(page, "input[id*='website']",                  b.get("portfolio") or b.get("github"), "website alt")

    # ── Resume upload ──
    fill_resume(page, profile.get("resume_path", "resume.pdf"))

    # ── Cover letter (if text area present) ──
    cl_template = profile.get("cover_letter_template", "")
    if cl_template:
        cl_text = cl_template.format(
            role=job_title or "this role",
            company=company or "your company",
            top_skills=", ".join(profile.get("skills", [])[:3]),
        )
        safe_fill(page, "textarea[id*='cover']",  cl_text, "cover letter")
        safe_fill(page, "textarea[name*='cover']", cl_text, "cover letter alt")

    # ── Education (some Greenhouse forms have inline edu fields) ──
    safe_fill(page, "input[id*='school']",     edu.get("school"),          "school")
    safe_fill(page, "input[id*='degree']",     edu.get("degree"),          "degree")
    safe_fill(page, "input[id*='major']",      edu.get("major"),           "major")
    safe_fill(page, "input[id*='gpa']",        edu.get("gpa"),             "gpa")
    safe_fill(page, "input[id*='graduation']", edu.get("graduation_year"), "grad year")

    # ── Work auth ──
    # Greenhouse usually shows these as Yes/No dropdowns or radio buttons
    if auth.get("authorized_us"):
        _click_radio_yes(page, "authorized")
        _click_radio_yes(page, "work_authorization")
    if not auth.get("requires_sponsorship"):
        _click_radio_no(page, "sponsorship")
        _click_radio_no(page, "visa_sponsorship")

    # ── Demographic (optional fields) ──
    if demo.get("gender"):
        safe_select(page, "select[id*='gender']", demo["gender"], "gender")
    if demo.get("ethnicity"):
        safe_select(page, "select[id*='ethnicity']", demo["ethnicity"], "ethnicity")
    if demo.get("veteran_status"):
        safe_select(page, "select[id*='veteran']", demo["veteran_status"], "veteran status")
    if demo.get("disability_status"):
        safe_select(page, "select[id*='disability']", demo["disability_status"], "disability")

    # ── Common free-text questions ──
    # Walk all textareas and try to match known questions
    _fill_custom_questions(page, answers, profile)

    log.info("  Greenhouse form filled. Review and click Submit yourself.")


# ─── Lever ────────────────────────────────────────────────────────────────────

def fill_lever(page, profile: dict, job_title: str = "", company: str = ""):
    """Fill a Lever application form."""
    b = profile.get("basic", {})
    edu = profile.get("education", {})
    auth = profile.get("work_authorization", {})
    answers = profile.get("common_answers", {})

    log.info("  Filling Lever form...")

    # Lever uses name/data-qa attributes
    safe_fill(page, "input[name='name']",       f"{b.get('first_name','')} {b.get('last_name','')}".strip(), "full name")
    safe_fill(page, "input[name='email']",      b.get("email"),     "email")
    safe_fill(page, "input[name='phone']",      b.get("phone"),     "phone")
    safe_fill(page, "input[name='org']",        b.get("location"),  "location/org")
    safe_fill(page, "input[name='location']",   b.get("location"),  "location")

    # Links
    safe_fill(page, "input[name='urls[LinkedIn]']", b.get("linkedin"),  "linkedin")
    safe_fill(page, "input[name='urls[GitHub]']",   b.get("github"),    "github")
    safe_fill(page, "input[name='urls[Portfolio]']", b.get("portfolio"), "portfolio")
    # Generic url fields
    safe_fill(page, "input[data-qa='additional-cards-url-input']", b.get("linkedin"), "url field")

    # Resume upload
    fill_resume(page, profile.get("resume_path", "resume.pdf"))

    # Cover letter
    cl_template = profile.get("cover_letter_template", "")
    if cl_template:
        cl_text = cl_template.format(
            role=job_title or "this role",
            company=company or "your company",
            top_skills=", ".join(profile.get("skills", [])[:3]),
        )
        safe_fill(page, "textarea[name='comments']", cl_text, "cover letter")

    # Work auth — Lever usually has dropdowns
    if auth.get("authorized_us"):
        _click_radio_yes(page, "authorization")
    if not auth.get("requires_sponsorship"):
        _click_radio_no(page, "sponsorship")

    # Custom questions
    _fill_custom_questions(page, answers, profile)

    log.info("  Lever form filled. Review and click Submit yourself.")


# ─── Custom question matching ──────────────────────────────────────────────────

QUESTION_PATTERNS = {
    "why": "why_interested",
    "interest": "why_interested",
    "motivation": "why_interested",
    "strength": "strengths",
    "skill": "strengths",
    "start": "start_date",
    "available": "start_date",
    "salary": "salary_expectation",
    "compensation": "salary_expectation",
    "hours": "hours_per_week",
    "remote": "remote_preference",
    "hybrid": "remote_preference",
}

def _fill_custom_questions(page, answers: dict, profile: dict):
    """
    Walk all textarea/text inputs that aren't already filled and
    try to match their label text to a known answer.
    """
    try:
        textareas = page.locator("textarea")
        for i in range(textareas.count()):
            ta = textareas.nth(i)
            if not ta.is_visible():
                continue
            current = ta.input_value()
            if current.strip():
                continue  # already filled

            # Find label for this textarea
            label_text = _find_label(page, ta).lower()
            for kw, answer_key in QUESTION_PATTERNS.items():
                if kw in label_text:
                    val = answers.get(answer_key, "")
                    if val:
                        ta.fill(val)
                        log.debug(f"  ✓ custom Q '{label_text[:40]}' → {answer_key}")
                    break
    except Exception as e:
        log.debug(f"  custom Q scan: {e}")


def _find_label(page, element) -> str:
    """Try to find the label text associated with an input element."""
    try:
        el_id = element.get_attribute("id")
        if el_id:
            label = page.locator(f"label[for='{el_id}']")
            if label.count() > 0:
                return label.first.inner_text()
        # Walk up and look for nearby label/legend/p
        return element.evaluate("""el => {
            let node = el.parentElement;
            for (let i = 0; i < 5; i++) {
                if (!node) break;
                const label = node.querySelector('label, legend, p, span');
                if (label && label.textContent.trim()) return label.textContent.trim();
                node = node.parentElement;
            }
            return '';
        }""")
    except Exception:
        return ""


def _click_radio_yes(page, keyword: str):
    """Click a 'Yes' radio/option near a label containing keyword."""
    try:
        radios = page.locator(f"input[type='radio'][value='Yes'], input[type='radio'][value='yes'], input[type='radio'][value='true']")
        for i in range(radios.count()):
            r = radios.nth(i)
            label = _find_label(page, r).lower()
            if keyword in label and r.is_visible():
                r.check()
                return
    except Exception:
        pass


def _click_radio_no(page, keyword: str):
    """Click a 'No' radio/option near a label containing keyword."""
    try:
        radios = page.locator(f"input[type='radio'][value='No'], input[type='radio'][value='no'], input[type='radio'][value='false']")
        for i in range(radios.count()):
            r = radios.nth(i)
            label = _find_label(page, r).lower()
            if keyword in label and r.is_visible():
                r.check()
                return
    except Exception:
        pass


# ─── Main entry point ─────────────────────────────────────────────────────────

def autofill(url: str, profile: dict, headless: bool = False):
    """
    Open the apply URL in a real browser, fill the form, then pause.
    headless=False so you can see and review everything.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  Playwright not installed. Run: pip install playwright && playwright install chromium")
        return False

    platform = detect_platform(url)
    job_title = profile.get("_current_job_title", "")
    company = profile.get("_current_company", "")

    print(f"\n  🤖 Opening {platform} form for: {company} — {job_title}")
    print(f"  📎 Attaching resume: {profile.get('resume_path','resume.pdf')}")
    print(f"  ⏸  Form will fill then PAUSE. You review + click Submit.\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=200)
        ctx = browser.new_context(accept_downloads=True)
        page = ctx.new_page()

        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)  # let JS render

        if platform == "greenhouse":
            fill_greenhouse(page, profile, job_title, company)
        elif platform == "lever":
            fill_lever(page, profile, job_title, company)
        else:
            # Unknown platform — do best-effort generic fill
            log.warning(f"  Unknown platform for {url} — attempting generic fill")
            _generic_fill(page, profile)

        page.wait_for_timeout(1000)

        print("\n  ✅ Form filled. Browser is open.")
        print("  👀 Review everything carefully before submitting.")
        print("  Press ENTER here when you're done (this closes the browser)...")
        input()

        browser.close()

    return True


def _generic_fill(page, profile: dict):
    """Best-effort fill for unknown ATS platforms."""
    b = profile.get("basic", {})
    safe_fill(page, "input[name*='first']",  b.get("first_name"), "first name")
    safe_fill(page, "input[name*='last']",   b.get("last_name"),  "last name")
    safe_fill(page, "input[type='email']",   b.get("email"),      "email")
    safe_fill(page, "input[type='tel']",     b.get("phone"),      "phone")
    safe_fill(page, "input[name*='phone']",  b.get("phone"),      "phone")
    safe_fill(page, "input[name*='location']", b.get("location"), "location")
    safe_fill(page, "input[name*='linkedin']", b.get("linkedin"), "linkedin")
    fill_resume(page, profile.get("resume_path", "resume.pdf"))
