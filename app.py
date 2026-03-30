import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime, timedelta
import time
import os
import re

from fetch_jobs import fetch_all
from autofill import autofill, detect_platform

# --- Config ---
st.set_page_config(page_title="Auto-Job-Seeker UI", page_icon="🎯", layout="wide")

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
    st.metric("Total Fetched", len(jobs))
    st.metric("Total Applied/Skipped", len(applied))
    st.metric("Pending Applications", len(pending))

# --- Main UI ---
tab1, tab2 = st.tabs(["💼 Job Board", "📊 Analytics"])

with tab1:
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
        # Create a dropdown to select a job
        job_options = { f"{j['company']} — {j['title']} ({j.get('category', 'SWE')})": j for j in pending }
        
        selected_key = st.selectbox("Select a job to apply to:", options=list(job_options.keys()))
        selected_job = job_options[selected_key]
        
        platform = detect_platform(selected_job["apply_url"])
        
        st.markdown(f"### {selected_job['company']} - {selected_job['title']}")
        st.markdown(f"**Location:** {selected_job['location']} | **Source:** {selected_job['source']} | **Platform:** `{platform}`")
        st.markdown(f"[🔗 Direct Link]({selected_job['apply_url']})")
        
        st.divider()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🤖 1. Auto-Fill Application", type="primary", use_container_width=True):
                # Using st.spinner to show UI feedback while Playwright blocks
                with st.spinner("Browser is open! Fill the form, submit, and CLOSE the browser window when done."):
                    # Inject for cover letter resolution
                    profile["_current_job_title"] = selected_job["title"]
                    profile["_current_company"] = selected_job["company"]
                    
                    try:
                        success = autofill(selected_job["apply_url"], profile, headless=False, streamlit_mode=True)
                        if success:
                            st.success("✅ Script finished. Don't forget to mark as applied!")
                    except Exception as e:
                        st.error(f"Error during auto-fill: {e}")

        with col2:
            if st.button("✅ 2. Mark as Applied", use_container_width=True):
                key = normalize(selected_job["apply_url"])
                applied[key] = make_record(selected_job, "applied")
                save_applied(applied)
                st.toast(f"Logged {selected_job['company']} as Applied!")
                time.sleep(1)
                st.rerun()
                
        with col3:
            if st.button("⏭️ Skip Job", use_container_width=True):
                key = normalize(selected_job["apply_url"])
                applied[key] = make_record(selected_job, "skipped")
                save_applied(applied)
                st.toast(f"Skipped {selected_job['company']}")
                time.sleep(1)
                st.rerun()
                
        st.divider()
        st.subheader("All Pending Jobs")
        # Display as a clean dataframe
        df = pd.DataFrame(pending)[["company", "title", "category", "location", "source", "apply_url"]]
        st.dataframe(df, use_container_width=True, hide_index=True)

    else:
        st.info("No pending jobs! Click 'Fetch New Jobs' in the sidebar to find more.")

with tab2:
    st.header("Analytics")
    if applied:
        applied_list = [r for r in applied.values() if r.get("status") == "applied"]
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
                
            st.subheader("Recent Applications")
            recent_df = df_applied.sort_values("applied_at", ascending=False).head(10)
            st.dataframe(recent_df[["applied_at", "company", "title", "source"]], use_container_width=True, hide_index=True)
            
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
