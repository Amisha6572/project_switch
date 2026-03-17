import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity
import warnings
warnings.filterwarnings("ignore")

# ── Skill Match Score ─────────────────────────────────────────────────────────

def compute_skill_match(emp_skills_df: pd.DataFrame, job_skills_df: pd.DataFrame) -> float:
    if job_skills_df.empty:
        return 50.0
    if emp_skills_df.empty:
        return 0.0

    total_weight = 0.0
    matched_weight = 0.0

    for _, req in job_skills_df.iterrows():
        importance = req.get("importance_level", 3)
        min_prof = req.get("minimum_proficiency", 1)
        total_weight += importance

        emp_match = emp_skills_df[emp_skills_df["skill_id"] == req["skill_id"]]
        if not emp_match.empty:
            emp_prof = emp_match.iloc[0]["proficiency_level"]
            if emp_prof >= min_prof:
                matched_weight += importance * min(emp_prof / 5.0, 1.0)
            else:
                matched_weight += importance * (emp_prof / min_prof) * 0.5

    return round((matched_weight / total_weight) * 100, 2) if total_weight > 0 else 0.0


def compute_experience_match(employee: dict, job: dict) -> float:
    from datetime import date
    hire_date = employee.get("hire_date")
    if hire_date is None:
        return 50.0
    if isinstance(hire_date, str):
        from datetime import datetime
        hire_date = datetime.strptime(hire_date, "%Y-%m-%d").date()
    years = (date.today() - hire_date).days / 365.25
    min_exp = job.get("min_experience", 0) or 0
    max_exp = job.get("max_experience", 20) or 20
    if years < min_exp:
        score = max(0, (years / max(min_exp, 1)) * 70)
    elif years <= max_exp:
        score = 100.0
    else:
        score = max(60, 100 - (years - max_exp) * 5)
    return round(score, 2)


def compute_performance_match(perf_df: pd.DataFrame) -> float:
    if perf_df.empty:
        return 60.0
    avg_rating = perf_df["performance_rating"].astype(float).mean()
    return round((avg_rating / 5.0) * 100, 2)


def compute_growth_potential(perf_df: pd.DataFrame, training_df: pd.DataFrame) -> float:
    score = 50.0
    if not perf_df.empty:
        potential_map = {"High": 30, "Medium": 20, "Low": 10, "Exceptional": 35}
        latest = perf_df.iloc[0]
        score += potential_map.get(str(latest.get("potential_rating", "")), 15)
    if not training_df.empty:
        score += min(len(training_df) * 3, 20)
    return round(min(score, 100), 2)


def compute_overall_match(skill, experience, performance, growth) -> float:
    weights = {"skill": 0.40, "experience": 0.25, "performance": 0.20, "growth": 0.15}
    total = (
        skill * weights["skill"]
        + experience * weights["experience"]
        + performance * weights["performance"]
        + growth * weights["growth"]
    )
    return round(total, 2)


# ── Batch Matching ────────────────────────────────────────────────────────────

def run_matching_for_job(job_row: dict, employees_df: pd.DataFrame, db) -> list:
    """
    Compute match scores for all employees against a single job.
    Returns list of dicts with employee_id and score breakdown.
    """
    job_id = job_row["job_id"]
    job_skills_df = db.get_job_required_skills(job_id)
    results = []

    for _, emp in employees_df.iterrows():
        emp_id = emp["employee_id"]
        emp_skills = db.get_employee_skills(emp_id)
        perf = db.get_employee_performance(emp_id)
        training = db.get_employee_training(emp_id)

        skill_score = compute_skill_match(emp_skills, job_skills_df)
        exp_score = compute_experience_match(emp.to_dict(), job_row)
        perf_score = compute_performance_match(perf)
        growth_score = compute_growth_potential(perf, training)
        overall = compute_overall_match(skill_score, exp_score, perf_score, growth_score)

        results.append({
            "employee_id": emp_id,
            "match_score": overall,
            "skill_match_score": skill_score,
            "experience_match_score": exp_score,
            "performance_match_score": perf_score,
            "growth_potential_score": growth_score,
        })

    return sorted(results, key=lambda x: x["match_score"], reverse=True)


# ── Career Path Clustering ────────────────────────────────────────────────────

def cluster_employees(employees_df: pd.DataFrame, n_clusters: int = 4) -> pd.DataFrame:
    """
    Cluster employees by level and tenure for career path grouping.
    Returns employees_df with a 'cluster' column added.
    """
    if employees_df.empty or len(employees_df) < n_clusters:
        employees_df["cluster"] = 0
        return employees_df

    from datetime import date
    def years_tenure(hire_date):
        if pd.isna(hire_date):
            return 0
        if isinstance(hire_date, str):
            from datetime import datetime
            hire_date = datetime.strptime(hire_date, "%Y-%m-%d").date()
        return (date.today() - hire_date).days / 365.25

    level_map = {"Junior": 1, "Mid": 2, "Senior": 3, "Lead": 4, "Principal": 5, "Director": 6}
    features = pd.DataFrame({
        "tenure": employees_df["hire_date"].apply(years_tenure),
        "level": employees_df["employee_level"].map(level_map).fillna(2),
    })

    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(features)
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    employees_df = employees_df.copy()
    employees_df["cluster"] = km.fit_predict(scaled)
    return employees_df


# ── Skill Gap Analysis ────────────────────────────────────────────────────────

def skill_gap_analysis(emp_skills_df: pd.DataFrame, job_skills_df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns a DataFrame showing each required skill, employee proficiency,
    required proficiency, and gap.
    """
    rows = []
    for _, req in job_skills_df.iterrows():
        emp_match = emp_skills_df[emp_skills_df["skill_id"] == req["skill_id"]]
        emp_prof = int(emp_match.iloc[0]["proficiency_level"]) if not emp_match.empty else 0
        gap = max(0, int(req.get("minimum_proficiency", 1)) - emp_prof)
        rows.append({
            "skill_name": req.get("skill_name", req["skill_id"]),
            "required_proficiency": req.get("minimum_proficiency", 1),
            "employee_proficiency": emp_prof,
            "gap": gap,
            "importance": req.get("importance_level", 3),
        })
    return pd.DataFrame(rows)
