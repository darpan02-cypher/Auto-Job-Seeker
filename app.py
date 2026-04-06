import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime, timedelta
import time
import os
import re
import io

from fetch_jobs import fetch_all
from autofill import autofill, detect_platform

# --- Config ---
st.set_page_config(page_title="Auto-Job-Seeker Dashboard", page_icon="🎯", layout="wide")

# Detect if running on Streamlit Cloud
IS_CLOUD = os.environ.get("STREAMLIT_RUNTIME_ENV") is not None or os.environ.get("HOSTNAME") == "streamlit"

# --- Auto-Install Playwright for Streamlit Cloud ---
if "playwright_installed" not in st.session_state:
    try:
        # Check if playwright is working. If not, install.
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            pw.chromium.executable_path
        st.session_state["playwright_installed"] = True
    except Exception:
        # Install chromium binaries only if they are missing
        st.info("🔧 First-time setup: Installing browser binaries...")
        # Use python -m playwright to ensure it uses the correct environment's executable
        os.system("python3 -m playwright install chromium")
        st.session_state["playwright_installed"] = True
        st.rerun()

import subprocess
import socket

@st.cache_resource
def ensure_browser_running():
    """Launch a global Chromium process with CDP enabled if not already running."""
    port = 9222
    # Check if anything is listening on port 9222
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(('localhost', port)) == 0:
            return True # Already running

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            exe = pw.chromium.executable_path
            
        # Launch Chromium as a background process
        # We use a dedicated user data dir to avoid conflicts
        user_data_dir = os.path.abspath("./.browser_data")
        cmd = [
            exe,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check"
        ]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2) # Give it a moment to start
        return True
    except Exception as e:
        st.error(f"Failed to launch background browser: {e}")
        return False

# --- Custom Style for Premium Look ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"]  {
        font-family: 'Inter', sans-serif;
        color: #f8fafc;
    }
    
    /* Tighten Main Container */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 0rem !important;
        max-width: 95% !important;
    }
    
    /* Remove Header Gaps */
    h1, h2, h3 {
        margin-top: 0.5rem !important;
        margin-bottom: 0.5rem !important;
    }

    /* Modern Rounded Corners & Buttons */
    .stButton>button {
        border-radius: 6px;
        font-weight: 500;
        letter-spacing: 0.01em;
        transition: all 0.2s ease-in-out;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        background-color: #1e293b !important;
        padding: 0.2rem 0.5rem !important;
        height: auto !important;
    }
    
    .stButton>button:hover {
        transform: translateY(-1px);
        background-color: #334155 !important;
        border: 1px solid #6366f1 !important;
        box-shadow: 0 10px 20px -10px rgba(99, 102, 241, 0.5);
    }
    
    /* Primary Action Button (Auto-Fill) */
    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%) !important;
        border: none !important;
        color: white !important;
    }

    /* Individual Job Card Style */
    .job-card {
        padding: 0.5rem 1rem !important; /* Extremely tight */
        background-color: #0f172a;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05); /* Thin line instead of divider */
        margin-bottom: 0px !important;
    }
    
    .job-card:hover {
        background-color: #1e293b;
    }

    /* Compact row headers */
    .row-header {
        color: #64748b;
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 0.2rem;
    }

    /* Tighten Text Spacing */
    .stMarkdown div p {
        line-height: 1.2 !important;
    }

    /* Target specific Streamlit elements */
    [data-testid="stSidebar"] {
        background-color: #020617;
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 1.5rem;
        background-color: transparent;
    }
    
    .stTabs [data-baseweb="tab"] {
        font-weight: 600;
        color: #64748b;
        padding-top: 0px !important;
        padding-bottom: 0px !important;
    }
    
    .stTabs [aria-selected="true"] {
        color: #f8fafc !important;
    }

    /* Thinner Dividers */
    hr {
        margin: 0.5rem 0px !important;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

if "display_limit" not in st.session_state:
    st.session_state["display_limit"] = 20

JOBS_FILE = "jobs.json"
APPLIED_FILE = "applied.json"
PROFILE_FILE = "profile.json"

# --- Helpers ---
def load_json(path):
    if not Path(path).exists():
        return {} if "profile" in path else []
    with open(path) as f:
        return json.load(f)

def save_applied(applied_dict):
    with open(APPLIED_FILE, "w") as f:
        json.dump(list(applied_dict.values()), f, indent=2)

def normalize(url: str) -> str:
    return url.strip().rstrip("/").lower()

def make_record(job, status="applied"):
    return {
        "title": job["title"],
        "company": job["company"],
        "apply_url": job["apply_url"],
        "source": job["source"],
        "category": job.get("category", ""),
        "status": status,
        "applied_at": datetime.now().isoformat()
    }

# --- Export Helpers ---
SHEET_ID = "13h5N0vjW1wQpC6j_4i28-pvMFnULEWA8FjcwD7ToQJg"
CREDS_FILE = "credentials.json"

def build_applied_df(applied_dict):
    """Returns a DataFrame of only 'applied' (not skipped) records."""
    rows = [r for r in applied_dict.values() if r.get("status") == "applied"]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)[["applied_at", "company", "title", "source", "category", "apply_url"]]
    df.columns = ["Applied At", "Company", "Title", "Source", "Category", "URL"]
    # Clean up applied_at to a readable format
    df["Applied At"] = pd.to_datetime(df["Applied At"]).dt.strftime("%Y-%m-%d %H:%M")
    return df

def export_to_excel(applied_dict):
    """Returns an in-memory Excel (.xlsx) bytes object."""
    df = build_applied_df(applied_dict)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Applied Jobs")
        ws = writer.sheets["Applied Jobs"]
        # Auto-size columns
        col_widths = {"A": 18, "B": 28, "C": 40, "D": 18, "E": 14, "F": 55}
        for col, width in col_widths.items():
            ws.column_dimensions[col].width = width
    buffer.seek(0)
    return buffer.getvalue()

def sync_to_google_sheet(applied_dict):
    """Syncs applied jobs to the configured Google Sheet. Returns (success, message).
    Credentials are loaded from:
      1. st.secrets['gcp_service_account']  (Streamlit Cloud)
      2. credentials.json file              (local development)
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        # --- Load credentials: st.secrets first, then local file ---
        creds_info = None
        try:
            # Streamlit Cloud: store JSON fields under [gcp_service_account] in secrets.toml
            if "gcp_service_account" in st.secrets:
                creds_info = dict(st.secrets["gcp_service_account"])
        except (KeyError, FileNotFoundError):
            pass  # Not on Streamlit Cloud or secrets not set

        if creds_info:
            creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        elif Path(CREDS_FILE).exists():
            creds = Credentials.from_service_account_file(CREDS_FILE, scopes=scopes)
        else:
            return False, (
                "❌ No credentials found.\n\n"
                "**Local:** place `credentials.json` in the project folder.\n\n"
                "**Streamlit Cloud:** add your service account JSON to `st.secrets` "
                "under `[gcp_service_account]` in the dashboard."
            )

        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID)

        # Find the right worksheet by GID
        target_gid = 941207653
        ws = None
        for sheet in sh.worksheets():
            if sheet.id == target_gid:
                ws = sheet
                break
        if ws is None:
            ws = sh.sheet1  # Fallback: use first sheet

        df = build_applied_df(applied_dict)
        if df.empty:
            return False, "No applied jobs to sync."

        # Full overwrite: clear then write headers + rows
        ws.clear()
        headers = df.columns.tolist()
        rows = df.values.tolist()
        ws.update([headers] + rows)

        return True, f"✅ Synced {len(rows)} applied jobs to Google Sheet!"
    except Exception as e:
        return False, f"❌ Sync failed: {e}"

# --- Load Data ---
profile = load_json(PROFILE_FILE)
jobs = load_json(JOBS_FILE)

# applied is a dict mapping url -> record
raw_applied = load_json(APPLIED_FILE)
applied = {normalize(r["apply_url"]): r for r in raw_applied}

if not jobs:
    jobs = []

pending = [j for j in jobs if normalize(j["apply_url"]) not in applied]

# --- Sidebar ---
with st.sidebar:
    st.title("🎯 Auto-Job-Seeker")
    
    # --- Navigation (Moved to Top) ---
    st.markdown("### 📂 Navigation")
    page = st.radio("Go to:", ["💼 Job Board", "📊 Analytics"], label_visibility="collapsed")
    
    # --- Quick Stats ---
    st.divider()
    m1, m2 = st.columns(2)
    m1.metric("Pending", len(pending))
    m2.metric("Done", len(applied))
    st.caption(f"Total jobs fetched: {len(jobs)}")
    st.divider()

    if profile.get("basic"):
        b = profile["basic"]
        st.success("✅ Profile Loaded")
        st.markdown(f"**{b.get('first_name','')} {b.get('last_name','')}**")
        st.caption(f"📧 {b.get('email','')}")
        
        resume = profile.get("resume_path", "")
        if Path(resume).exists():
            st.caption(f"📄 Resume found ({Path(resume).stat().st_size // 1024} KB)")
        else:
            st.error("❌ Resume PDF not found")
    else:
        st.error("❌ profile.json is missing or empty")

    st.divider()
    
    st.markdown("### Quick Actions")
    if st.button("🔄 Fetch New Jobs", use_container_width=True):
        with st.spinner("Fetching jobs from all sources..."):
            new_jobs = fetch_all()
            st.session_state["fetch_done"] = True
            st.rerun()

    st.divider()
# --- Main UI ---
if page == "💼 Job Board":
    st.header("Job Board")
    
    # --- Filters ---
    st.subheader("Filters")
    col_f1, col_f2, col_f3 = st.columns(3)
    
    with col_f1:
        time_filter = st.radio("Actual Posted Date:", ["Any time", "Past 24 hours", "Past Week"], horizontal=True)
        
    with col_f2:
        all_sources = sorted(list(set(j.get("source", "Unknown") for j in pending)))
        selected_sources = st.multiselect("Source:", options=all_sources, default=all_sources)

    with col_f3:
        regions = ["US", "Canada", "UK", "Europe", "Remote"]
        selected_regions = st.multiselect("Quick Region Filter:", options=regions, default=[])
        location_keyword = st.text_input("City/Keyword Search:", "").lower().strip()

    # Apply Source Filter
    if selected_sources and len(selected_sources) != len(all_sources):
        pending = [j for j in pending if j.get("source", "Unknown") in selected_sources]
    
    # Apply Region Filter
    if selected_regions:
        def match_region(job_loc):
            loc = job_loc.lower()
            matches = []
            if any(k in loc for k in ["ca", "canada", "toronto", "vancouver", "montreal", "ottawa"]): matches.append("Canada")
            if any(k in loc for k in ["uk", "united kingdom", "london", "manchester", "birmingham"]): matches.append("UK")
            if any(k in loc for k in ["remote", "anywhere", "global"]): matches.append("Remote")
            if any(k in loc for k in ["us", "usa", "united states", "san francisco", "new york", "austin"]): matches.append("US")
            # Fallback for Europe if not UK
            if "uk" not in loc and any(k in loc for k in ["europe", "germany", "berlin", "paris", "france", "amsterdam", "netherlands", "spain", "italy"]): matches.append("Europe")
            
            return any(r in matches for r in selected_regions)
        
        pending = [j for j in pending if match_region(j.get("location", ""))]

    # Apply Manual Keyword Filter
    if location_keyword:
        pending = [j for j in pending if location_keyword in j.get("location", "").lower()]
    
    # Apply Time Filter
    if time_filter != "Any time":
        max_hours = 24 if time_filter == "Past 24 hours" else 168
        
        filtered_pending = []
        for j in pending:
            keep = False
            # 1. Check direct posted_at
            posted = j.get("posted_at")
            if posted:
                try:
                    dt = datetime.fromisoformat(posted.replace("Z", "+00:00"))
                    now_tz = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
                    keep = (now_tz - dt) <= timedelta(hours=max_hours)
                except Exception:
                    keep = True # fallback if parsing fails
            elif str(j.get("age", "")).strip():
                # 2. Check GitHub stringage
                age = str(j["age"]).lower()
                if any(x in age for x in ["hr", "hour", "min", "now"]):
                    keep = True
                elif "yesterday" in age:
                    keep = max_hours >= 24
                elif re.search(r'(\d+)\s*d', age):
                    keep = int(re.search(r'(\d+)\s*d', age).group(1)) * 24 <= max_hours
                elif re.search(r'(\d+)\s*w', age):
                    keep = int(re.search(r'(\d+)\s*w', age).group(1)) * 7 * 24 <= max_hours
                else:
                    keep = True
            else:
                # 3. Fallback: Check fetched_at
                fetched = j.get("fetched_at")
                if fetched:
                    try:
                        dt = datetime.fromisoformat(fetched)
                        keep = (datetime.now() - dt) <= timedelta(hours=max_hours)
                    except Exception:
                        keep = True
                else:
                    keep = True

            if keep:
                filtered_pending.append(j)
                
        pending = filtered_pending

    if pending:
        st.subheader(f"Showing {min(len(pending), st.session_state['display_limit'])} of {len(pending)} jobs")
        
        # Header Row - Styled with Custom CSS
        h1, h2, h3, h4 = st.columns([5, 1.2, 1.2, 1], gap="small")
        h1.markdown('<p class="row-header">Job Information</p>', unsafe_allow_html=True)
        h2.markdown('<p class="row-header">Auto-Fill</p>', unsafe_allow_html=True)
        h3.markdown('<p class="row-header">Applied</p>', unsafe_allow_html=True)
        h4.markdown('<p class="row-header">Skip</p>', unsafe_allow_html=True)

        for i, job in enumerate(pending[:st.session_state["display_limit"]]):
            url_key = normalize(job["apply_url"])
            platform = detect_platform(job["apply_url"])
            
            # Unique ID for buttons
            uid = f"{i}_{hash(url_key)}"

            st.write('<div style="margin-top: -10px;"></div>', unsafe_allow_html=True) # Negative spacer
            col_info, col_auto, col_done, col_skip = st.columns([5, 1.2, 1.2, 1], gap="small")
            
            with col_info:
                st.write(f"**{job['company']}** — {job['title']} [🔗]({job['apply_url']})")
                st.caption(f"📍 {job['location']} | {job['source']} | `{platform.upper()}`")

            with col_auto:
                if IS_CLOUD:
                    st.button("🤖 Auto-Fill", key=f"auto_{uid}", use_container_width=True, type="primary", disabled=True, help="Auto-Fill only works when running the app locally on your machine.")
                else:
                    if st.button("🤖 Auto-Fill", key=f"auto_{uid}", use_container_width=True, type="primary"):
                        with st.spinner("Connecting to browser..."):
                            profile["_current_job_title"] = job["title"]
                            profile["_current_company"] = job["company"]
                            try:
                                # 1. Ensure the background browser is alive
                                if ensure_browser_running():
                                    # 2. Connect via CDP (thread-safe)
                                    autofill(job["apply_url"], profile, cdp_port=9222)
                                    st.success("Tab opened!")
                                else:
                                    st.error("Could not start browser process.")
                            except Exception as e:
                                st.error(f"Error: {e}")

            with col_done:
                if st.button("✅ Done", key=f"done_{uid}", use_container_width=True):
                    applied[url_key] = make_record(job, "applied")
                    save_applied(applied)
                    st.toast(f"Applied to {job['company']}")
                    time.sleep(0.5)
                    st.rerun()

            with col_skip:
                if st.button("⏭️ Skip", key=f"skip_{uid}", use_container_width=True):
                    applied[url_key] = make_record(job, "skipped")
                    save_applied(applied)
                    st.toast(f"Skipped {job['company']}")
                    time.sleep(0.5)
                    st.rerun()
            
            st.write('<hr style="margin: 2px 0px; border: 0.1px solid rgba(255,255,255,0.05);">', unsafe_allow_html=True)

        if len(pending) > st.session_state["display_limit"]:
            if st.button("➕ Load More Jobs", use_container_width=True):
                st.session_state["display_limit"] += 20
                st.rerun()
    else:
        st.info("No pending jobs matches your filters! Click 'Fetch New Jobs' in the sidebar or adjust your filters.")

else: # 📊 Analytics
    st.header("Analytics")
    if applied:
        applied_list = [r for r in applied.values() if r.get("status") == "applied"]

        # --- Export Buttons ---
        exp_col1, exp_col2, exp_col3 = st.columns([1.5, 1.8, 5])
        with exp_col1:
            if applied_list:
                excel_bytes = export_to_excel(applied)
                st.download_button(
                    label="📥 Download Excel",
                    data=excel_bytes,
                    file_name=f"applied_jobs_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            else:
                st.button("📥 Download Excel", disabled=True, use_container_width=True)

        with exp_col2:
            if st.button("☁️ Sync to Google Sheet", use_container_width=True):
                with st.spinner("Syncing to Google Sheets..."):
                    success, msg = sync_to_google_sheet(applied)
                if success:
                    st.toast(msg, icon="✅")
                else:
                    st.error(msg)
                    if "credentials.json" in msg:
                        st.info(
                            "**How to add credentials:**\n"
                            "1. Go to [Google Cloud Console](https://console.cloud.google.com/) → IAM & Admin → Service Accounts\n"
                            "2. Create/select a service account → Keys → Add Key → JSON\n"
                            "3. Download the file and rename it to `credentials.json`\n"
                            "4. Place it inside your `Auto-Job-Seeker/` project folder\n"
                            "5. Share your Google Sheet with the service account email"
                        )

        st.divider()

        if not applied_list:
            st.info("You haven't applied to any jobs yet.")
        else:
            df_applied = pd.DataFrame(applied_list)
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Applications by Source")
                source_counts = df_applied["source"].value_counts().reset_index()
                source_counts.columns = ["Source", "Count"]
                st.bar_chart(source_counts.set_index("Source"))
                
            with col2:
                st.subheader("Applications by Category")
                cat_counts = df_applied["category"].value_counts().reset_index()
                cat_counts.columns = ["Category", "Count"]
                st.bar_chart(cat_counts.set_index("Category"))
                
            st.subheader(f"All Applications ({len(df_applied)} total)")
            recent_df = df_applied.sort_values("applied_at", ascending=False)
            st.dataframe(recent_df[["applied_at", "company", "title", "source", "category"]], use_container_width=True, hide_index=True)
            
        st.divider()
        st.subheader("Manage History")
        all_history = sorted(list(applied.values()), key=lambda x: x.get("applied_at", ""), reverse=True)
        # Format: [APPLIED] Company - Title
        undo_options = { f"[{r.get('status', 'applied').upper()}] {r['company']} — {r['title']}": normalize(r["apply_url"]) for r in all_history }
        
        col_u1, col_u2 = st.columns([3, 1])
        with col_u1:
            undo_choice = st.selectbox("Select a job to revert back to pending:", options=list(undo_options.keys()))
        with col_u2:
            st.write("") # Add some vertical spacing
            st.write("")
            if st.button("↩️ Revert Job", use_container_width=True):
                url_key = undo_options[undo_choice]
                if url_key in applied:
                    del applied[url_key]
                    save_applied(applied)
                    st.toast("Job reverted successfully!")
                    time.sleep(1)
                    st.rerun()

    else:
        st.info("No application history found.")
