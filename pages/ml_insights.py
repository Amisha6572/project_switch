import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import plotly.express as px
import pandas as pd
from utils.auth import require_hr
from utils.db import (
    get_all_employees, get_all_jobs, get_matches_for_job,
    get_employee_skills, get_employee_performance, get_employee_training,
    get_job_required_skills, upsert_match
)
from utils.ml_engine import (
    run_matching_for_job, cluster_employees, skill_gap_analysis,
    compute_overall_match
)
import utils.db as db

st.set_page_config(page_title="ML Insights", page_icon="🤖", layout="wide")
require_hr()

st.title("🤖 ML Insights & Matching Engine")

tab1, tab2, tab3 = st.tabs(["🎯 Run Matching", "👥 Employee Clusters", "📊 Talent Analytics"])

# ── Tab 1: Run Matching ───────────────────────────────────────────────────────
with tab1:
    jobs_df = get_all_jobs()
    open_jobs = jobs_df[jobs_df["status"] == "Open"] if not jobs_df.empty else pd.DataFrame()

    if open_jobs.empty:
        st.info("No open jobs to match against.")
    else:
        job_options = {f"{r['job_title']} ({r['department']})": r["job_id"] for _, r in open_jobs.iterrows()}
        selected_job_label = st.selectbox("Select Job", list(job_options.keys()))
        selected_job_id = job_options[selected_job_label]

        col1, col2 = st.columns([1, 3])
        with col1:
            run_all = st.button("▶ Run Matching for All Employees", type="primary")

        if run_all:
            employees_df = get_all_employees()
            job_row = jobs_df[jobs_df["job_id"] == selected_job_id].iloc[0].to_dict()

            with st.spinner("Computing matches..."):
                results = run_matching_for_job(job_row, employees_df, db)
                for r in results:
                    upsert_match(selected_job_id, r["employee_id"], r)

            st.success(f"Matched {len(results)} employees!")
            results_df = pd.DataFrame(results)
            emp_names = employees_df.set_index("employee_id")["full_name"]
            results_df["name"] = results_df["employee_id"].map(emp_names)

            fig = px.bar(
                results_df.head(20), x="name", y="match_score",
                color="match_score", color_continuous_scale="Viridis",
                title="Top Employee Matches", labels={"match_score": "Match %"}
            )
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(
                results_df[["name", "match_score", "skill_match_score",
                             "experience_match_score", "performance_match_score", "growth_potential_score"]],
                use_container_width=True
            )
        else:
            # Show existing matches
            existing = get_matches_for_job(selected_job_id)
            if not existing.empty:
                st.subheader("Existing Matches")
                fig2 = px.bar(
                    existing.head(20), x="full_name", y="match_score",
                    color="match_score", color_continuous_scale="Blues",
                    title="Current Top Matches"
                )
                st.plotly_chart(fig2, use_container_width=True)
                st.dataframe(existing[["full_name", "current_department", "current_role",
                                       "match_score", "skill_match_score"]], use_container_width=True)

# ── Tab 2: Employee Clusters ──────────────────────────────────────────────────
with tab2:
    employees_df = get_all_employees()
    if employees_df.empty:
        st.info("No employee data available.")
    else:
        n_clusters = st.slider("Number of Clusters", 2, 8, 4)
        clustered = cluster_employees(employees_df, n_clusters)

        fig3 = px.scatter(
            clustered, x="hire_date", y="employee_level",
            color=clustered["cluster"].astype(str),
            hover_data=["full_name", "current_department", "current_role"],
            title="Employee Career Clusters",
            labels={"cluster": "Cluster"}
        )
        st.plotly_chart(fig3, use_container_width=True)

        for c in sorted(clustered["cluster"].unique()):
            group = clustered[clustered["cluster"] == c]
            with st.expander(f"Cluster {c} — {len(group)} employees"):
                st.dataframe(group[["full_name", "current_department", "current_role", "employee_level"]], use_container_width=True)

# ── Tab 3: Talent Analytics ───────────────────────────────────────────────────
with tab3:
    employees_df = get_all_employees()
    if employees_df.empty:
        st.info("No data.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            loc_counts = employees_df["location"].value_counts().reset_index()
            loc_counts.columns = ["Location", "Count"]
            fig4 = px.pie(loc_counts, names="Location", values="Count", title="Employees by Location")
            st.plotly_chart(fig4, use_container_width=True)
        with col2:
            dept_level = employees_df.groupby(["current_department", "employee_level"]).size().reset_index(name="count")
            fig5 = px.bar(dept_level, x="current_department", y="count", color="employee_level",
                          title="Department × Level Distribution", barmode="stack")
            st.plotly_chart(fig5, use_container_width=True)
