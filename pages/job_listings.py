import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import plotly.express as px
from datetime import date
from utils.auth import require_login
from utils.db import (
    get_open_jobs, get_job_required_skills, get_employee_skills,
    get_employee_by_id, get_employee_performance, get_employee_training,
    mark_applied, mark_viewed, upsert_match
)
from utils.ml_engine import (
    compute_skill_match, compute_experience_match,
    compute_performance_match, compute_growth_potential,
    compute_overall_match, skill_gap_analysis
)

st.set_page_config(page_title="Job Listings", page_icon="💼", layout="wide")
require_login()

st.title("💼 Open Job Listings")

emp_id = st.session_state["employee_id"]

# Load employee data once
emp_df = get_employee_by_id(emp_id)
if emp_df.empty:
    st.error("Employee record not found.")
    st.stop()

emp = emp_df.iloc[0]
emp_skills = get_employee_skills(emp_id)
perf_df = get_employee_performance(emp_id)
training_df = get_employee_training(emp_id)

# Compute years of experience for display
hire_date = emp.get("hire_date")
if hire_date:
    if hasattr(hire_date, "year"):
        years_exp = (date.today() - hire_date).days / 365.25
    else:
        from datetime import datetime
        years_exp = (date.today() - datetime.strptime(str(hire_date), "%Y-%m-%d").date()).days / 365.25
else:
    years_exp = 0

jobs_df = get_open_jobs()

if jobs_df.empty:
    st.info("No open positions at the moment.")
    st.stop()

# ── Filters ───────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
with col1:
    dept_filter = st.selectbox("Department", ["All"] + sorted(jobs_df["department"].unique().tolist()))
with col2:
    level_filter = st.selectbox("Level", ["All"] + sorted(jobs_df["job_level"].dropna().unique().tolist()))
with col3:
    loc_filter = st.selectbox("Location", ["All"] + sorted(jobs_df["location"].unique().tolist()))

filtered = jobs_df.copy()
if dept_filter != "All":
    filtered = filtered[filtered["department"] == dept_filter]
if level_filter != "All":
    filtered = filtered[filtered["job_level"] == level_filter]
if loc_filter != "All":
    filtered = filtered[filtered["location"] == loc_filter]

# ── Pre-compute match scores for all visible jobs ─────────────────────────────
def get_match_for_job(job_row):
    job_skills_df = get_job_required_skills(int(job_row["job_id"]))
    skill_score = compute_skill_match(emp_skills, job_skills_df)
    exp_score = compute_experience_match(emp.to_dict(), job_row.to_dict())
    perf_score = compute_performance_match(perf_df)
    growth_score = compute_growth_potential(perf_df, training_df)
    overall = compute_overall_match(skill_score, exp_score, perf_score, growth_score)
    return {
        "overall": overall,
        "skill": skill_score,
        "experience": exp_score,
        "performance": perf_score,
        "growth": growth_score,
        "job_skills_df": job_skills_df,
    }

# Sort jobs by match score descending
match_cache = {}
for _, job in filtered.iterrows():
    match_cache[job["job_id"]] = get_match_for_job(job)

filtered = filtered.copy()
filtered["_match_score"] = filtered["job_id"].map(lambda jid: match_cache[jid]["overall"])
filtered = filtered.sort_values("_match_score", ascending=False)

st.caption(f"Showing {len(filtered)} of {len(jobs_df)} open positions — sorted by your match %")
st.divider()

# ── Job Cards ─────────────────────────────────────────────────────────────────
for _, job in filtered.iterrows():
    scores = match_cache[job["job_id"]]
    overall = scores["overall"]
    job_skills_df = scores["job_skills_df"]

    # Color-code match badge
    if overall >= 75:
        badge = f"🟢 {overall:.0f}% Match"
    elif overall >= 50:
        badge = f"🟡 {overall:.0f}% Match"
    else:
        badge = f"🔴 {overall:.0f}% Match"

    with st.expander(f"**{job['job_title']}** — {job['department']} | {job.get('job_level', '')} | {job['location']}   {badge}"):
        # Mark as viewed (safe — upsert won't fail if no match_results row exists)
        try:
            mark_viewed(job["job_id"], emp_id)
        except Exception:
            pass

        # ── Score breakdown ───────────────────────────────────────────────────
        st.markdown("#### Your Match Breakdown")
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Overall Match", f"{scores['overall']:.0f}%")
        mc2.metric("Skill Match", f"{scores['skill']:.0f}%")
        mc3.metric("Experience", f"{scores['experience']:.0f}%")
        mc4.metric("Performance", f"{scores['performance']:.0f}%")

        st.divider()
        left, right = st.columns([3, 2])

        with left:
            st.markdown("#### Job Details")
            st.markdown(f"**Description:** {job.get('job_description', 'N/A')}")
            st.markdown(f"**Responsibilities:** {job.get('key_responsibilities', 'N/A')}")
            req_min = job.get('min_experience', 0) or 0
            req_max = job.get('max_experience', '?')
            st.markdown(f"**Required Experience:** {req_min}–{req_max} years  |  **Your Experience:** {years_exp:.1f} years")
            st.markdown(f"**Closes:** {job.get('closing_date', 'N/A')}")
            if job.get("hiring_manager_name"):
                st.markdown(f"**Hiring Manager:** {job['hiring_manager_name']}")

        with right:
            if not job_skills_df.empty:
                st.markdown("#### Skills Analysis")
                gap_df = skill_gap_analysis(emp_skills, job_skills_df)

                if not gap_df.empty:
                    # Split into matched vs gaps
                    matched = gap_df[gap_df["gap"] == 0]
                    gaps = gap_df[gap_df["gap"] > 0]
                    missing = job_skills_df[
                        ~job_skills_df["skill_id"].isin(
                            emp_skills["skill_id"].tolist() if not emp_skills.empty else []
                        )
                    ] if not emp_skills.empty else job_skills_df

                    if not matched.empty:
                        st.markdown("✅ **Skills you already have:**")
                        for _, sk in matched.iterrows():
                            st.markdown(f"- {sk['skill_name']} (your level: {sk['employee_proficiency']}/5, required: {sk['required_proficiency']}/5)")

                    if not gaps.empty:
                        st.markdown("⚠️ **Skills to improve:**")
                        for _, sk in gaps.iterrows():
                            st.markdown(f"- {sk['skill_name']} — you: {sk['employee_proficiency']}/5, need: {sk['required_proficiency']}/5 (gap: {sk['gap']})")

                    # Skills not in employee profile at all
                    if not emp_skills.empty:
                        emp_skill_ids = set(emp_skills["skill_id"].tolist())
                        new_skills = job_skills_df[~job_skills_df["skill_id"].isin(emp_skill_ids)]
                    else:
                        new_skills = job_skills_df

                    if not new_skills.empty:
                        st.markdown("🆕 **Skills to learn:**")
                        for _, sk in new_skills.iterrows():
                            st.markdown(f"- {sk['skill_name']} (need level {sk.get('minimum_proficiency', 1)}/5)")

                    # Visual chart
                    fig = px.bar(
                        gap_df, x="skill_name", y=["employee_proficiency", "required_proficiency"],
                        barmode="group",
                        labels={"value": "Proficiency (1-5)", "skill_name": "Skill", "variable": ""},
                        color_discrete_map={"employee_proficiency": "#4F46E5", "required_proficiency": "#E11D48"},
                        title="Your Skills vs Required"
                    )
                    fig.update_layout(height=280, margin=dict(t=40, b=20))
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No specific skills listed for this role.")

        st.divider()
        # Save match to DB and allow apply
        try:
            upsert_match(job["job_id"], emp_id, {
                "match_score": scores["overall"],
                "skill_match_score": scores["skill"],
                "experience_match_score": scores["experience"],
                "performance_match_score": scores["performance"],
                "growth_potential_score": scores["growth"],
            })
        except Exception:
            pass

        if st.button("Apply Now", key=f"apply_{job['job_id']}", type="primary"):
            try:
                mark_applied(job["job_id"], emp_id)
                st.success("Application submitted!")
            except Exception as e:
                st.error(f"Could not apply: {e}")
