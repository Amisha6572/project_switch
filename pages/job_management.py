import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
from datetime import date, timedelta
from utils.auth import require_hr
from utils.db import (
    get_all_jobs, create_job_posting, update_job_status,
    get_all_skills, run_write, get_job_required_skills
)

st.set_page_config(page_title="Job Management", page_icon="⚙️", layout="wide")
require_hr()

st.title("⚙️ Job Management")

DEPARTMENTS = ["Engineering", "Product", "Design", "Marketing", "Sales", "HR", "Finance", "Operations"]
LEVELS = ["Junior", "Mid", "Senior", "Lead", "Principal", "Director"]
LOCATIONS = ["Remote", "New York", "San Francisco", "London", "Austin", "Chicago"]

tab1, tab2 = st.tabs(["📋 All Postings", "➕ Create Posting"])

# ── Tab 1: All Postings ───────────────────────────────────────────────────────
with tab1:
    jobs_df = get_all_jobs()
    if jobs_df.empty:
        st.info("No job postings yet.")
    else:
        for _, job in jobs_df.iterrows():
            status_badge = {"Open": "🟢", "Closed": "🔴", "Draft": "🟡"}.get(job["status"], "⚪")
            with st.expander(f"{status_badge} {job['job_title']} — {job['department']} | {job['status']}"):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**Location:** {job['location']}  |  **Level:** {job.get('job_level', 'N/A')}")
                    st.markdown(f"**Experience:** {job.get('min_experience', 0)}–{job.get('max_experience', '?')} years")
                    st.markdown(f"**Posted:** {job.get('posting_date', 'N/A')}  |  **Closes:** {job.get('closing_date', 'N/A')}")
                    st.markdown(f"**Description:** {job.get('job_description', '')[:300]}...")
                with col2:
                    new_status = st.selectbox(
                        "Change Status", ["Open", "Closed", "Draft"],
                        index=["Open", "Closed", "Draft"].index(job["status"]) if job["status"] in ["Open", "Closed", "Draft"] else 0,
                        key=f"status_{job['job_id']}"
                    )
                    if st.button("Update", key=f"upd_{job['job_id']}"):
                        update_job_status(job["job_id"], new_status)
                        st.success("Status updated!")
                        st.rerun()

# ── Tab 2: Create Posting ─────────────────────────────────────────────────────
with tab2:
    with st.form("create_job_form"):
        col1, col2 = st.columns(2)
        with col1:
            job_title = st.text_input("Job Title *")
            department = st.selectbox("Department", DEPARTMENTS)
            location = st.selectbox("Location", LOCATIONS)
            job_level = st.selectbox("Level", LEVELS)
        with col2:
            min_exp = st.number_input("Min Experience (years)", min_value=0, max_value=30, value=2)
            max_exp = st.number_input("Max Experience (years)", min_value=0, max_value=30, value=8)
            posting_date = st.date_input("Posting Date", value=date.today())
            closing_date = st.date_input("Closing Date", value=date.today() + timedelta(days=30))
            status = st.selectbox("Status", ["Open", "Draft"])

        job_description = st.text_area("Job Description *", height=120)
        key_responsibilities = st.text_area("Key Responsibilities", height=100)

        # Required skills
        st.markdown("**Required Skills** (optional)")
        all_skills = get_all_skills()
        skill_options = {row["skill_name"]: row["skill_id"] for _, row in all_skills.iterrows()} if not all_skills.empty else {}
        selected_skills = st.multiselect("Select Skills", list(skill_options.keys()))

        skill_configs = {}
        for sk in selected_skills:
            c1, c2 = st.columns(2)
            with c1:
                importance = st.slider(f"{sk} — Importance", 1, 5, 3, key=f"imp_{sk}")
            with c2:
                min_prof = st.slider(f"{sk} — Min Proficiency", 1, 5, 2, key=f"prof_{sk}")
            skill_configs[sk] = {"importance": importance, "min_prof": min_prof}

        submitted = st.form_submit_button("Create Job Posting")

    if submitted:
        if not job_title or not job_description:
            st.error("Job title and description are required.")
        else:
            try:
                job_id = create_job_posting({
                    "job_title": job_title,
                    "department": department,
                    "location": location,
                    "job_level": job_level,
                    "min_experience": min_exp,
                    "max_experience": max_exp,
                    "job_description": job_description,
                    "key_responsibilities": key_responsibilities,
                    "posting_date": posting_date.strftime("%Y-%m-%d"),
                    "closing_date": closing_date.strftime("%Y-%m-%d"),
                    "status": status,
                    "hiring_manager_id": st.session_state["employee_id"],
                })
                # Insert required skills
                for sk_name, cfg in skill_configs.items():
                    run_write(
                        """INSERT INTO job_required_skills (job_id, skill_id, importance_level, minimum_proficiency)
                           VALUES (%s, %s, %s, %s)
                           ON DUPLICATE KEY UPDATE importance_level=VALUES(importance_level), minimum_proficiency=VALUES(minimum_proficiency)""",
                        (job_id, skill_options[sk_name], cfg["importance"], cfg["min_prof"])
                    )
                st.success(f"Job posting created (ID: {job_id})")
            except Exception as e:
                st.error(f"Failed to create posting: {e}")
