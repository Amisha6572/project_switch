import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import plotly.express as px
from utils.auth import require_login
from utils.db import get_matches_for_employee
from utils.ml_engine import skill_gap_analysis
from utils.db import get_employee_skills, get_job_required_skills

st.set_page_config(page_title="My Applications", page_icon="📋", layout="wide")
require_login()

emp_id = st.session_state["employee_id"]
st.title("📋 My Applications & Matches")

matches_df = get_matches_for_employee(emp_id)

if matches_df.empty:
    st.info("No matches or applications yet.")
    st.stop()

applied = matches_df[matches_df.get("employee_applied", False) == True] if "employee_applied" in matches_df.columns else matches_df.iloc[0:0]
all_matches = matches_df

tab1, tab2 = st.tabs([f"📨 Applied ({len(applied)})", f"🎯 All Matches ({len(all_matches)})"])

with tab1:
    if applied.empty:
        st.info("You haven't applied to any positions yet.")
    else:
        for _, row in applied.iterrows():
            with st.expander(f"{row['job_title']} — {row['department']} | Score: {row['match_score']:.0f}%"):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Skill", f"{row['skill_match_score']:.0f}%")
                c2.metric("Experience", f"{row['experience_match_score']:.0f}%")
                c3.metric("Performance", f"{row['performance_match_score']:.0f}%")
                c4.metric("Growth", f"{row['growth_potential_score']:.0f}%")

                # Skill gap
                emp_skills = get_employee_skills(emp_id)
                job_skills = get_job_required_skills(row["job_id"])
                if not job_skills.empty:
                    gap_df = skill_gap_analysis(emp_skills, job_skills)
                    gaps = gap_df[gap_df["gap"] > 0]
                    if not gaps.empty:
                        st.markdown("**Skill Gaps:**")
                        fig = px.bar(gaps, x="skill_name", y="gap", color="importance",
                                     title="Skills to Develop", labels={"gap": "Gap (levels)"})
                        st.plotly_chart(fig, use_container_width=True)

with tab2:
    fig_all = px.bar(
        all_matches.sort_values("match_score", ascending=False).head(20),
        x="job_title", y="match_score", color="department",
        title="Your Top Job Matches", labels={"match_score": "Match %"}
    )
    st.plotly_chart(fig_all, use_container_width=True)
    st.dataframe(
        all_matches[["job_title", "department", "location", "job_level", "match_score",
                     "skill_match_score", "experience_match_score"]].sort_values("match_score", ascending=False),
        use_container_width=True
    )
