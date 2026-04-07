import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime, timedelta
import time
import os
import re
import io
import subprocess
import socket

from fetch_jobs import fetch_all
from autofill import autofill, detect_platform

# --- Config ---
st.set_page_config(page_title="Auto-Job-Seeker Dashboard", page_icon="🎯", layout="wide")

# Detect if running on Streamlit Cloud
IS_CLOUD = os.environ.get("STREAMLIT_RUNTIME_ENV") is not None or os.environ.get("HOSTNAME") == "streamlit"

# --- Auto-Install Playwright for Streamlit Cloud ---
if "playwright_installed" not in st.session_state:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            pw.chromium.executable_path
        st.session_state["playwright_installed"] = True
    except Exception:
        if IS_CLOUD:
            try:
                st.info("🔧 First-time setup: Installing browser binaries...")
                os.system("python3 -m playwright install chromium")
                st.session_state["playwright_installed"] = True
                st.rerun()
            except Exception as e:
                st.error(f"⚠️ Could not install browser binaries: {e}")
                st.session_state["playwright_installed"] = True
        else:
            st.warning("⚠️ Playwright not detected. Run `playwright install chromium` in your terminal.")
            st.session_state["playwright_installed"] = True

@st.cache_resource
def ensure_browser_running():
    """Launch a global Chromium process with CDP enabled if not already running."""
    port = 9222
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(('localhost', port)) == 0:
            return True 

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            exe = pw.chromium.executable_path
            
        user_data_dir = os.path.abspath("./.browser_data")
        cmd = [
            exe,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check"
        ]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2) 
        return True
    except Exception as e:
        st.error(f"Failed to launch background browser: {e}")
        return False

# --- Custom Style ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"]  {
        font-family: 'Inter', sans-serif;
        color: #f8fafc;
    }
    
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 0rem !important;
        max-width: 95% !important;
    }
    
    h1, h2, h3 {
        margin-top: 0.5rem !important;
        margin-bottom: 0.5rem !important;
    }

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
    
    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%) !important;
        border: none !important;
        color: white !important;
    }

    .job-card {
        padding: 0.5rem 1rem !important;
        background-color: #0f172a;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        margin-bottom: 0px !important;
    }
    
    .job-card:hover {
        background-color: #1e293b;
    }

    .row-header {
        color: #64748b;
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 0.2rem;
    }

    .stMarkdown div p {
        line-height: 1.2 !important;
    }

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
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {} if "profile" in path else []

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
    rows = [r for r in applied_dict.values() if r.get("status") == "applied"]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)[["applied_at", "company", "title", "source", "category", "apply_url"]]
    df.columns = ["Applied At", "Company", "Title", "Source", "Category", "URL"]
    
    # Robust date conversion using errors='coerce'
    dt_col = pd.to_datetime(df["Applied At"], errors='coerce')
    df["Applied At"] = dt_col.dt.strftime("%Y-%m-%d %H:%M").fillna("N/A")
    return df

def export_to_excel(applied_dict):
    df = build_applied_df(applied_dict)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Applied Jobs")
        ws = writer.sheets["Applied Jobs"]
        col_widths = {"A": 18, "B": 28, "C": 40, "D": 18, "E": 14, "F": 55}
        for col, width in col_widths.items():
            ws.column_dimensions[col].width = width
    buffer.seek(0)
    return buffer.getvalue()

def clean_private_key(key: str) -> str:
    """The most radical cleaning approach for the private_key to solve Offset 1624."""
    if not key or not isinstance(key, str):
        return key

    # 1. Normalize escapes and outer wrapping
    key = key.replace("\\n", "\n").strip().strip("'").strip('"')
    
    header = "-----BEGIN PRIVATE KEY-----"
    footer = "-----END PRIVATE KEY-----"
    
    # Extract content between markers
    content = key
    if header in key:
        content = key.split(header)[1]
    if footer in content:
        content = content.split(footer)[0]
    
    # 2. Strict character filtering
    clean_body = re.sub(r'[^A-Za-z0-9+/=]', '', content)
    
    # 3. Auto-Padding fix (ensure length is multiple of 4)
    # If the key is cut off, we try to pad it enough for the parser to try
    missing = len(clean_body) % 4
    if missing > 0:
        clean_body += "=" * (4 - missing)
    
    # 4. Single-line PEM (no wrapping in middle). Most libraries prefer this.
    rebuilt = f"{header}\n{clean_body}\n{footer}\n"
    return rebuilt

def get_creds_info():
    """Helper to load credentials from either secrets or local file."""
    try:
        if IS_CLOUD and "gcp_service_account" in st.secrets:
            # Use to_dict() for Streamlit Secrets
            return dict(st.secrets.to_dict()["gcp_service_account"])
        elif Path(CREDS_FILE).exists():
            with open(CREDS_FILE) as f:
                return json.load(f)
    except Exception as e:
        st.error(f"Error loading credentials structure: {e}")
    return None

def sync_to_google_sheet(applied_dict):
    """Syncs applied jobs to the configured Google Sheet."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = get_creds_info()

        if not creds_info:
            return False, "❌ No credentials found."

        original_pk = creds_info.get("private_key", "")
        if original_pk:
            creds_info["private_key"] = clean_private_key(original_pk)

        try:
            creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        except Exception as e:
            last_few = original_pk[-40:].replace("\n", " [NL] ") if original_pk else "None"
            return False, f"❌ PEM Error: {e}\n\n**Diagnostic:** Key end snippet: `{last_few}`.\n\n**Length:** {len(original_pk)} chars."

        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID)

        target_gid = 941207653
        ws = next((s for s in sh.worksheets() if s.id == target_gid), sh.sheet1)

        df = build_applied_df(applied_dict)
        if df.empty: return False, "No applied jobs to sync."

        ws.clear()
        ws.update([df.columns.tolist()] + df.values.tolist())

        return True, f"✅ Synced {len(df)} applied jobs to Google Sheet!"
    except Exception as e:
        return False, f"❌ Sync failed: {e}. If persistence failed, verify YOUR Spreadsheet ID."

def fetch_applied_from_gsheet():
    """On startup, load previously applied jobs from GSheet."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds_info = get_creds_info()
        if not creds_info: return {}
        
        if creds_info.get("private_key"):
            creds_info["private_key"] = clean_private_key(creds_info["private_key"])
            
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID)
        
        target_gid = 941207653
        ws = next((s for s in sh.worksheets() if s.id == target_gid), sh.sheet1)
        
        records = ws.get_all_records()
        pulled = {}
        for r in records:
            url = normalize(str(r.get("URL", "")))
            if url:
                pulled[url] = {
                    "title": r.get("Title", ""),
                    "company": r.get("Company", ""),
                    "apply_url": r.get("URL", ""),
                    "source": r.get("Source", ""),
                    "category": r.get("Category", ""),
                    "status": "applied",
                    "applied_at": r.get("Applied At", datetime.now().isoformat())
                }
        return pulled
    except Exception:
        return {}

# --- Load Data ---
profile = load_json(PROFILE_FILE)
jobs = load_json(JOBS_FILE)
raw_applied = load_json(APPLIED_FILE)
applied = {normalize(r["apply_url"]): r for r in raw_applied}

# --- Persistence Fix: Restore from GSheet on first load ---
if "gsheet_sync_done" not in st.session_state:
    with st.spinner("🔄 Restoring application history from Google Sheets..."):
        gsheet_applied = fetch_applied_from_gsheet()
        if gsheet_applied:
            applied.update(gsheet_applied)
            save_applied(applied)
        st.session_state["gsheet_sync_done"] = True

if not jobs:
    jobs = []

pending = [j for j in jobs if normalize(j["apply_url"]) not in applied]

# --- Sidebar ---
with st.sidebar:
    st.title("🎯 Auto-Job-Seeker")
    st.markdown("### 📂 Navigation")
    page = st.radio("Go to:", ["💼 Job Board", "📊 Analytics"], label_visibility="collapsed")
    
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
    else:
        st.error("❌ profile.json is missing or empty")

    st.divider()
    
    st.markdown("### Quick Actions")
    if st.button("🔄 Fetch New Jobs", use_container_width=True):
        with st.spinner("Fetching jobs from all sources..."):
            new_jobs = fetch_all()
            st.rerun()

    st.divider()

# --- Main UI ---
if page == "💼 Job Board":
    st.header("Job Board")
    
    st.subheader("Filters")
    col_f1, col_f2, col_f3 = st.columns(3)
    
    with col_f1:
        time_filter = st.radio("Posted Date:", ["Any time", "Past 24 hours", "Past Week"], horizontal=True)
        
    with col_f2:
        all_sources = sorted(list(set(j.get("source", "Unknown") for j in pending)))
        selected_sources = st.multiselect("Source:", options=all_sources, default=all_sources)

    with col_f3:
        regions = ["US", "Canada", "UK", "Europe", "Remote"]
        selected_regions = st.multiselect("Quick Region Filter:", options=regions, default=[])
        location_keyword = st.text_input("City/Keyword Search:", "").lower().strip()

    if selected_sources and len(selected_sources) != len(all_sources):
        pending = [j for j in pending if j.get("source", "Unknown") in selected_sources]
    
    if selected_regions:
        def match_region(job_loc):
            loc = job_loc.lower()
            matches = []
            if any(k in loc for k in ["ca", "canada"]): matches.append("Canada")
            if any(k in loc for k in ["uk", "united kingdom"]): matches.append("UK")
            if any(k in loc for k in ["remote", "anywhere"]): matches.append("Remote")
            if any(k in loc for k in ["us", "usa", "united states"]): matches.append("US")
            if "uk" not in loc and any(k in loc for k in ["europe", "germany", "france"]): matches.append("Europe")
            return any(r in matches for r in selected_regions)
        pending = [j for j in pending if match_region(j.get("location", ""))]

    if location_keyword:
        pending = [j for j in pending if location_keyword in j.get("location", "").lower()]
    
    if pending:
        st.subheader(f"Showing {min(len(pending), st.session_state['display_limit'])} of {len(pending)} jobs")
        
        h1, h2, h3, h4 = st.columns([5, 1.2, 1.2, 1], gap="small")
        h1.markdown('<p class="row-header">Job Information</p>', unsafe_allow_html=True)
        h2.markdown('<p class="row-header">Auto-Fill</p>', unsafe_allow_html=True)
        h3.markdown('<p class="row-header">Applied</p>', unsafe_allow_html=True)
        h4.markdown('<p class="row-header">Skip</p>', unsafe_allow_html=True)

        for i, job in enumerate(pending[:st.session_state["display_limit"]]):
            url_key = normalize(job["apply_url"])
            platform = detect_platform(job["apply_url"])
            uid = f"{i}_{hash(url_key)}"

            st.write('<div style="margin-top: -10px;"></div>', unsafe_allow_html=True)
            col_info, col_auto, col_done, col_skip = st.columns([5, 1.2, 1.2, 1], gap="small")
            
            with col_info:
                st.write(f"**{job['company']}** — {job['title']} [🔗]({job['apply_url']})")
                st.caption(f"📍 {job['location']} | {job['source']} | `{platform.upper()}`")

            with col_auto:
                if IS_CLOUD:
                    st.link_button("🤖 Go to Job", job["apply_url"], use_container_width=True, type="primary")
                else:
                    if st.button("🤖 Auto-Fill", key=f"auto_{uid}", use_container_width=True, type="primary"):
                        if ensure_browser_running():
                            autofill(job["apply_url"], profile, cdp_port=9222)
                            st.success("Tab opened!")

            with col_done:
                if st.button("✅ Done", key=f"done_{uid}", use_container_width=True):
                    applied[url_key] = make_record(job, "applied")
                    save_applied(applied)
                    st.rerun()

            with col_skip:
                if st.button("⏭️ Skip", key=f"skip_{uid}", use_container_width=True):
                    applied[url_key] = make_record(job, "skipped")
                    save_applied(applied)
                    st.rerun()
            
            st.write('<hr style="margin: 2px 0px; border: 0.1px solid rgba(255,255,255,0.05);">', unsafe_allow_html=True)

        if len(pending) > st.session_state["display_limit"]:
            if st.button("➕ Load More Jobs", use_container_width=True):
                st.session_state["display_limit"] += 20
                st.rerun()
    else:
        st.info("No pending jobs matches your filters!")

else: # 📊 Analytics
    st.header("Analytics")
    if applied:
        applied_list = [r for r in applied.values() if r.get("status") == "applied"]

        exp_col1, exp_col2, exp_col3 = st.columns([1.5, 1.8, 5])
        with exp_col1:
            if applied_list:
                excel_bytes = export_to_excel(applied)
                st.download_button(label="📥 Download Excel", data=excel_bytes, file_name=f"applied_jobs.xlsx", use_container_width=True)

        with exp_col2:
            if st.button("☁️ Sync to Google Sheet", key="sync_btn", use_container_width=True):
                with st.spinner("Syncing..."):
                    success, msg = sync_to_google_sheet(applied)
                if success: st.toast(msg, icon="✅")
                else: st.error(msg)

        st.divider()

        if applied_list:
            df_applied = pd.DataFrame(applied_list)
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Applications by Source")
                st.bar_chart(df_applied["source"].value_counts())
            with col2:
                st.subheader("Applications by Category")
                st.bar_chart(df_applied["category"].value_counts())
                
            st.subheader(f"All Applications ({len(df_applied)} total)")
            st.dataframe(df_applied.sort_values("applied_at", ascending=False)[["applied_at", "company", "title", "source", "category"]], use_container_width=True, hide_index=True)
            
        st.divider()
        st.subheader("Manage History")
        all_history = sorted(list(applied.values()), key=lambda x: x.get("applied_at", ""), reverse=True)
        undo_options = { f"[{r.get('status','').upper()}] {r['company']} - {r['title']}": normalize(r["apply_url"]) for r in all_history }
        
        undo_choice = st.selectbox("Revert a job to pending:", options=list(undo_options.keys()))
        if st.button("↩️ Revert Job"):
            url_key = undo_options[undo_choice]
            del applied[url_key]
            save_applied(applied)
            st.rerun()
    else:
        st.info("No history found.")
