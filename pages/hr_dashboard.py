import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import plotly.express as px
import pandas as pd
from utils.auth import require_hr
from utils.db import (
    get_all_employees, get_all_jobs, get_all_performance,
    get_dept_skill_summary, get_job_required_skills,
    get_employee_skills, get_employee_performance,
    get_employee_training, upsert_match
)
from utils.ml_engine import (
    compute_skill_match, compute_experience_match,
    compute_performance_match, compute_growth_potential,
    compute_overall_match, skill_gap_analysis
)

st.set_page_config(page_title="HR Dashboard", page_icon="🏢", layout="wide")
require_hr()

st.title("🏢 HR Dashboard")

employees_df = get_all_employees()
jobs_df = get_all_jobs()
perf_df = get_all_performance()

# ── KPIs ──────────────────────────────────────────────────────────────

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Employees", len(employees_df))
c2.metric("Open Jobs", len(jobs_df[jobs_df["status"] == "Open"]) if not jobs_df.empty else 0)
c3.metric("Total Postings", len(jobs_df))
c4.metric("Avg Performance", f"{perf_df['performance_rating'].mean():.2f}/5" if not perf_df.empty else "N/A")

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["🎯 Job Matching", "👥 Employees", "📊 Analytics", "🗂 Jobs Overview"])

# ── Tab 1: Job Matching ───────────────────────────────────────────────────────
with tab1:
    st.subheader("Find Best Employees for a Job")

    open_jobs = jobs_df[jobs_df["status"] == "Open"] if not jobs_df.empty else pd.DataFrame()

    if open_jobs.empty:
        st.info("No open job postings.")
    else:
        job_options = {
            f"{r['job_title']} ({r['department']})": int(r["job_id"])
            for _, r in open_jobs.iterrows()
        }
        selected_label = st.selectbox("Select a Job Posting", list(job_options.keys()))
        selected_job_id = job_options[selected_label]
        selected_job = jobs_df[jobs_df["job_id"] == selected_job_id].iloc[0]

        min_match = st.slider("Minimum Match % to show", 0, 100, 0, 5)

        if st.button("▶ Run Matching", type="primary"):
            if employees_df.empty:
                st.warning("No employees in the system.")
            else:
                job_skills_df = get_job_required_skills(selected_job_id)
                results = []

                with st.spinner("Computing matches for all employees..."):
                    for _, emp in employees_df.iterrows():
                        emp_id = int(emp["employee_id"])
                        emp_skills = get_employee_skills(emp_id)
                        emp_perf = get_employee_performance(emp_id)
                        emp_training = get_employee_training(emp_id)

                        skill_score = compute_skill_match(emp_skills, job_skills_df)
                        exp_score = compute_experience_match(emp.to_dict(), selected_job.to_dict())
                        perf_score = compute_performance_match(emp_perf)
                        growth_score = compute_growth_potential(emp_perf, emp_training)
                        overall = compute_overall_match(skill_score, exp_score, perf_score, growth_score)

                        # Persist to DB
                        try:
                            upsert_match(selected_job_id, emp_id, {
                                "match_score": overall,
                                "skill_match_score": skill_score,
                                "experience_match_score": exp_score,
                                "performance_match_score": perf_score,
                                "growth_potential_score": growth_score,
                            })
                        except Exception:
                            pass

                        results.append({
                            "employee_id": emp_id,
                            "name": emp["full_name"],
                            "department": emp["current_department"],
                            "role": emp["current_role"],
                            "level": emp["employee_level"],
                            "overall": overall,
                            "skill": skill_score,
                            "experience": exp_score,
                            "performance": perf_score,
                            "growth": growth_score,
                        })

                results_df = pd.DataFrame(results).sort_values("overall", ascending=False)
                st.session_state[f"match_results_{selected_job_id}"] = results_df
                st.success(f"Matched {len(results_df)} employees!")

        # Display results (from session state so they persist without re-running)
        results_df = st.session_state.get(f"match_results_{selected_job_id}")
        if results_df is not None and not results_df.empty:
            display_df = results_df[results_df["overall"] >= min_match]
            st.caption(f"Showing {len(display_df)} employees with ≥{min_match}% match")

            # Summary chart
            fig = px.bar(
                display_df.head(20), x="name", y="overall",
                color="overall", color_continuous_scale="RdYlGn",
                range_color=[0, 100],
                title=f"Top Employee Matches for: {selected_label}",
                labels={"overall": "Match %", "name": "Employee"},
            )
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)

            # Detailed cards
            st.markdown("#### Employee Details")
            for _, row in display_df.iterrows():
                badge = "🟢" if row["overall"] >= 75 else ("🟡" if row["overall"] >= 50 else "🔴")
                with st.expander(f"{badge} **{row['name']}** — {row['role']} | {row['department']} | {row['overall']:.0f}% match"):
                    sc1, sc2, sc3, sc4 = st.columns(4)
                    sc1.metric("Skill Match", f"{row['skill']:.0f}%")
                    sc2.metric("Experience", f"{row['experience']:.0f}%")
                    sc3.metric("Performance", f"{row['performance']:.0f}%")
                    sc4.metric("Growth Potential", f"{row['growth']:.0f}%")

                    # Skill gap for this employee vs job
                    job_skills_df = get_job_required_skills(selected_job_id)
                    emp_skills = get_employee_skills(int(row["employee_id"]))
                    if not job_skills_df.empty:
                        gap_df = skill_gap_analysis(emp_skills, job_skills_df)
                        if not gap_df.empty:
                            gcol1, gcol2 = st.columns(2)
                            with gcol1:
                                matched = gap_df[gap_df["gap"] == 0]
                                if not matched.empty:
                                    st.markdown("✅ **Has these skills:**")
                                    for _, sk in matched.iterrows():
                                        st.markdown(f"- {sk['skill_name']} ({sk['employee_proficiency']}/5)")
                            with gcol2:
                                gaps = gap_df[gap_df["gap"] > 0]
                                if not gaps.empty:
                                    st.markdown("⚠️ **Skill gaps:**")
                                    for _, sk in gaps.iterrows():
                                        st.markdown(f"- {sk['skill_name']}: has {sk['employee_proficiency']}/5, needs {sk['required_proficiency']}/5")

                                if not emp_skills.empty:
                                    emp_skill_ids = set(emp_skills["skill_id"].tolist())
                                    new_skills = job_skills_df[~job_skills_df["skill_id"].isin(emp_skill_ids)]
                                else:
                                    new_skills = job_skills_df
                                if not new_skills.empty:
                                    st.markdown("🆕 **Missing skills entirely:**")
                                    for _, sk in new_skills.iterrows():
                                        st.markdown(f"- {sk['skill_name']} (need level {sk.get('minimum_proficiency', 1)}/5)")

# ── Tab 2: Employees ──────────────────────────────────────────────────────────
with tab2:
    if employees_df.empty:
        st.info("No employees found.")
    else:
        search = st.text_input("Search by name or department")
        filtered = employees_df
        if search:
            mask = (
                employees_df["full_name"].str.contains(search, case=False, na=False) |
                employees_df["current_department"].str.contains(search, case=False, na=False)
            )
            filtered = employees_df[mask]
        cols = ["full_name", "current_department", "current_role", "employee_level", "location", "hire_date"]
        st.dataframe(filtered[cols], use_container_width=True)

# ── Tab 3: Analytics ──────────────────────────────────────────────────────────
with tab3:
    if not employees_df.empty:
        col1, col2 = st.columns(2)
        with col1:
            dept_counts = employees_df["current_department"].value_counts().reset_index()
            dept_counts.columns = ["Department", "Count"]
            fig1 = px.pie(dept_counts, names="Department", values="Count", title="Employees by Department")
            st.plotly_chart(fig1, use_container_width=True)
        with col2:
            level_counts = employees_df["employee_level"].value_counts().reset_index()
            level_counts.columns = ["Level", "Count"]
            fig2 = px.bar(level_counts, x="Level", y="Count", title="Employees by Level")
            st.plotly_chart(fig2, use_container_width=True)

    skill_summary = get_dept_skill_summary()
    if not skill_summary.empty:
        fig3 = px.bar(
            skill_summary, x="current_department", y="avg_proficiency",
            color="skill_category", barmode="group",
            title="Avg Skill Proficiency by Department & Category"
        )
        st.plotly_chart(fig3, use_container_width=True)

# ── Tab 4: Jobs Overview ──────────────────────────────────────────────────────
with tab4:
    if jobs_df.empty:
        st.info("No job postings yet.")
    else:
        status_filter = st.selectbox("Filter by Status", ["All", "Open", "Closed", "Draft"])
        display = jobs_df if status_filter == "All" else jobs_df[jobs_df["status"] == status_filter]
        cols = ["job_title", "department", "location", "job_level", "status", "posting_date", "closing_date"]
        st.dataframe(display[cols], use_container_width=True)
