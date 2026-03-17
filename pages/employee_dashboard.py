import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import plotly.express as px
from datetime import date
from utils.auth import require_login
from utils.db import (
    get_employee_by_id, get_employee_skills, get_employee_performance,
    get_employee_training, get_open_jobs, get_job_required_skills,
    get_career_interests, upsert_career_interest, mark_applied, upsert_match,
    get_all_skills, upsert_employee_skill, run_write
)
from utils.ml_engine import (
    compute_skill_match, compute_experience_match,
    compute_performance_match, compute_growth_potential,
    compute_overall_match, skill_gap_analysis
)

st.set_page_config(page_title="My Dashboard", page_icon="👤", layout="wide")
require_login()

emp_id = st.session_state["employee_id"]
emp_df = get_employee_by_id(emp_id)
if emp_df.empty:
    st.error("Employee record not found.")
    st.stop()

emp = emp_df.iloc[0]
emp_skills = get_employee_skills(emp_id)
perf_df = get_employee_performance(emp_id)
training_df = get_employee_training(emp_id)

st.title(f"👤 Welcome, {emp['full_name']}")
st.caption(f"{emp['current_role']} · {emp['current_department']} · {emp['location']}")

# ── KPI row ───────────────────────────────────────────────────────────────────
jobs_df = get_open_jobs()

col1, col2, col3, col4 = st.columns(4)
col1.metric("My Skills", len(emp_skills))
col2.metric("Avg Performance", f"{perf_df['performance_rating'].mean():.1f}/5" if not perf_df.empty else "N/A")
col3.metric("Trainings", len(training_df))
col4.metric("Open Positions", len(jobs_df))

st.divider()

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🎯 Job Matches", "🛠 My Skills", "➕ Manage Skills", "📈 Performance", "🌱 Career Goals"])

# ── Tab 1: Job Matches (live computed) ───────────────────────────────────────
with tab1:
    if jobs_df.empty:
        st.info("No open positions at the moment.")
    else:
        # Compute match for every open job
        job_matches = []
        for _, job in jobs_df.iterrows():
            job_skills_df = get_job_required_skills(int(job["job_id"]))
            skill_score = compute_skill_match(emp_skills, job_skills_df)
            exp_score = compute_experience_match(emp.to_dict(), job.to_dict())
            perf_score = compute_performance_match(perf_df)
            growth_score = compute_growth_potential(perf_df, training_df)
            overall = compute_overall_match(skill_score, exp_score, perf_score, growth_score)

            # Persist match to DB silently
            try:
                upsert_match(int(job["job_id"]), emp_id, {
                    "match_score": overall,
                    "skill_match_score": skill_score,
                    "experience_match_score": exp_score,
                    "performance_match_score": perf_score,
                    "growth_potential_score": growth_score,
                })
            except Exception:
                pass

            job_matches.append({
                "job_id": job["job_id"],
                "job_title": job["job_title"],
                "department": job["department"],
                "location": job["location"],
                "job_level": job.get("job_level", ""),
                "overall": overall,
                "skill": skill_score,
                "experience": exp_score,
                "performance": perf_score,
                "growth": growth_score,
                "job_skills_df": job_skills_df,
                "job_row": job,
            })

        job_matches.sort(key=lambda x: x["overall"], reverse=True)

        # Summary bar chart
        chart_data = [{"Job": m["job_title"], "Match %": m["overall"], "Department": m["department"]} for m in job_matches]
        import pandas as pd
        chart_df = pd.DataFrame(chart_data)
        fig_summary = px.bar(
            chart_df, x="Job", y="Match %", color="Department",
            title="Your Match % Across All Open Positions",
            labels={"Match %": "Match %"},
        )
        fig_summary.update_layout(height=300)
        st.plotly_chart(fig_summary, use_container_width=True)

        st.markdown(f"**{len(job_matches)} open positions** — click any to see skill breakdown")
        st.divider()

        for m in job_matches:
            badge = "🟢" if m["overall"] >= 75 else ("🟡" if m["overall"] >= 50 else "🔴")
            with st.expander(f"{badge} **{m['job_title']}** — {m['department']} | {m['job_level']} | {m['location']}   {m['overall']:.0f}% match"):
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("Overall", f"{m['overall']:.0f}%")
                mc2.metric("Skill Match", f"{m['skill']:.0f}%")
                mc3.metric("Experience", f"{m['experience']:.0f}%")
                mc4.metric("Performance", f"{m['performance']:.0f}%")

                left, right = st.columns([3, 2])
                with left:
                    job = m["job_row"]
                    st.markdown(f"**Description:** {job.get('job_description', 'N/A')}")
                    req_min = job.get('min_experience', 0) or 0
                    req_max = job.get('max_experience', '?')
                    hire_date = emp.get("hire_date")
                    if hire_date:
                        if hasattr(hire_date, "year"):
                            yrs = (date.today() - hire_date).days / 365.25
                        else:
                            from datetime import datetime
                            yrs = (date.today() - datetime.strptime(str(hire_date), "%Y-%m-%d").date()).days / 365.25
                    else:
                        yrs = 0
                    st.markdown(f"**Required Experience:** {req_min}–{req_max} yrs  |  **Your Experience:** {yrs:.1f} yrs")
                    st.markdown(f"**Closes:** {job.get('closing_date', 'N/A')}")

                with right:
                    job_skills_df = m["job_skills_df"]
                    if not job_skills_df.empty:
                        gap_df = skill_gap_analysis(emp_skills, job_skills_df)
                        if not gap_df.empty:
                            matched_sk = gap_df[gap_df["gap"] == 0]
                            gap_sk = gap_df[gap_df["gap"] > 0]

                            if not matched_sk.empty:
                                st.markdown("✅ **Skills you have:**")
                                for _, sk in matched_sk.iterrows():
                                    st.markdown(f"- {sk['skill_name']} ({sk['employee_proficiency']}/5)")

                            if not gap_sk.empty:
                                st.markdown("⚠️ **Skills to improve:**")
                                for _, sk in gap_sk.iterrows():
                                    st.markdown(f"- {sk['skill_name']}: {sk['employee_proficiency']}/5 → need {sk['required_proficiency']}/5")

                            if not emp_skills.empty:
                                emp_skill_ids = set(emp_skills["skill_id"].tolist())
                                new_skills = job_skills_df[~job_skills_df["skill_id"].isin(emp_skill_ids)]
                            else:
                                new_skills = job_skills_df
                            if not new_skills.empty:
                                st.markdown("🆕 **Skills to learn:**")
                                for _, sk in new_skills.iterrows():
                                    st.markdown(f"- {sk['skill_name']} (need level {sk.get('minimum_proficiency', 1)}/5)")

                            fig_gap = px.bar(
                                gap_df, x="skill_name",
                                y=["employee_proficiency", "required_proficiency"],
                                barmode="group",
                                color_discrete_map={"employee_proficiency": "#4F46E5", "required_proficiency": "#E11D48"},
                                labels={"value": "Level (1-5)", "skill_name": "Skill", "variable": ""},
                                title="Your Skills vs Required"
                            )
                            fig_gap.update_layout(height=260, margin=dict(t=40, b=10))
                            st.plotly_chart(fig_gap, use_container_width=True)
                    else:
                        st.info("No specific skills listed for this role.")

                if st.button("Apply Now", key=f"dash_apply_{m['job_id']}", type="primary"):
                    try:
                        mark_applied(int(m["job_id"]), emp_id)
                        st.success("Application submitted!")
                    except Exception as e:
                        st.error(f"Could not apply: {e}")

# ── Tab 2: My Skills ──────────────────────────────────────────────────────────
with tab2:
    # Refresh emp_skills inside tab so it reflects any updates from tab3
    emp_skills_view = get_employee_skills(emp_id)
    if emp_skills_view.empty:
        st.info("No skills on record yet. Use the 'Manage Skills' tab to add your skills.")
    else:
        fig_skills = px.bar(
            emp_skills_view.sort_values("proficiency_level", ascending=False),
            x="skill_name", y="proficiency_level",
            color="skill_category", title="Your Skill Proficiency",
            labels={"proficiency_level": "Proficiency (1-5)", "skill_name": "Skill"},
        )
        st.plotly_chart(fig_skills, use_container_width=True)
        st.dataframe(
            emp_skills_view[["skill_name", "skill_category", "proficiency_level", "years_experience", "certification_status"]],
            use_container_width=True
        )

# ── Tab 3: Manage Skills ──────────────────────────────────────────────────────
with tab3:
    st.subheader("Add / Update Your Skills")
    st.caption("Select skills from the master list and set your proficiency level.")

    all_skills_df = get_all_skills()
    current_skills = get_employee_skills(emp_id)
    current_skill_ids = set(current_skills["skill_id"].tolist()) if not current_skills.empty else set()

    PROFICIENCY_LABELS = {1: "1 - Beginner", 2: "2 - Basic", 3: "3 - Intermediate", 4: "4 - Advanced", 5: "5 - Expert"}

    if all_skills_df.empty:
        st.warning("No skills found in the master skills table.")
    else:
        categories = sorted(all_skills_df["skill_category"].dropna().unique().tolist())

        with st.form("manage_skills_form"):
            skill_entries = []
            for cat in categories:
                cat_skills = all_skills_df[all_skills_df["skill_category"] == cat]
                st.markdown(f"**{cat}**")
                cols = st.columns(2)
                for i, (_, skill_row) in enumerate(cat_skills.iterrows()):
                    sid = int(skill_row["skill_id"])
                    # Pre-fill existing proficiency if employee already has this skill
                    existing_prof = 3
                    if not current_skills.empty and sid in current_skill_ids:
                        match = current_skills[current_skills["skill_id"] == sid]
                        if not match.empty:
                            existing_prof = int(match.iloc[0]["proficiency_level"])

                    with cols[i % 2]:
                        selected = st.checkbox(
                            skill_row["skill_name"],
                            value=(sid in current_skill_ids),
                            key=f"msk_{sid}"
                        )
                        if selected:
                            prof = st.select_slider(
                                f"Proficiency — {skill_row['skill_name']}",
                                options=[1, 2, 3, 4, 5],
                                format_func=lambda x: PROFICIENCY_LABELS[x],
                                value=existing_prof,
                                key=f"mprof_{sid}"
                            )
                            skill_entries.append((sid, skill_row["skill_name"], prof))
                st.divider()

            save_btn = st.form_submit_button("Save Skills", type="primary")

        if save_btn:
            saved, errors = 0, []
            for skill_id, skill_name, prof in skill_entries:
                try:
                    upsert_employee_skill(
                        emp_id=emp_id,
                        skill_id=skill_id,
                        proficiency=prof,
                        years_exp=0,
                        last_used=date.today().strftime("%Y-%m-%d"),
                        cert_status="None"
                    )
                    saved += 1
                except Exception as e:
                    errors.append(f"{skill_name}: {e}")

            if errors:
                st.warning(f"Saved {saved} skills. Errors: {'; '.join(errors)}")
            else:
                st.success(f"Saved {saved} skills successfully!")
            st.rerun()

# ── Tab 4: Performance ────────────────────────────────────────────────────────
with tab4:
    if perf_df.empty:
        st.info("No performance reviews on record.")
    else:
        fig_perf = px.line(
            perf_df.sort_values("review_date"),
            x="review_date", y="performance_rating",
            markers=True, title="Performance Over Time",
            labels={"performance_rating": "Rating (1-5)"},
        )
        st.plotly_chart(fig_perf, use_container_width=True)
        st.dataframe(
            perf_df[["review_date", "performance_rating", "potential_rating", "reviewer_notes"]],
            use_container_width=True
        )

# ── Tab 5: Career Goals ───────────────────────────────────────────────────────
with tab5:
    interests_df = get_career_interests(emp_id)
    existing = interests_df.iloc[0].to_dict() if not interests_df.empty else {}

    DEPARTMENTS = ["Engineering", "Product", "Design", "Marketing", "Sales", "HR", "Finance", "Operations"]
    TIMELINES = ["0-6 months", "6-12 months", "1-2 years", "2+ years"]

    with st.form("career_goals_form"):
        dept_idx = DEPARTMENTS.index(existing.get("interested_department")) if existing.get("interested_department") in DEPARTMENTS else 0
        timeline_idx = TIMELINES.index(existing.get("target_timeline")) if existing.get("target_timeline") in TIMELINES else 0

        dept = st.selectbox("Target Department", DEPARTMENTS, index=dept_idx)
        role = st.text_input("Target Role", value=existing.get("interested_role", ""))
        timeline = st.selectbox("Timeline", TIMELINES, index=timeline_idx)
        relocate = st.checkbox("Willing to Relocate", value=bool(existing.get("willing_to_relocate", False)))
        notes = st.text_area("Notes", value=existing.get("notes", ""))
        if st.form_submit_button("Save Goals"):
            upsert_career_interest(emp_id, dept, role, timeline, relocate, notes)
            st.success("Career goals saved!")
