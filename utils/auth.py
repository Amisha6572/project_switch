import bcrypt
import streamlit as st

HR_EMAILS = {
    "hr@company.com",
    "admin@company.com",
    "hrmanager@company.com",
}

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False

def is_hr(email: str) -> bool:
    return email.lower() in HR_EMAILS

def set_session(employee_row, role: str):
    st.session_state["logged_in"] = True
    st.session_state["employee_id"] = int(employee_row["employee_id"])
    st.session_state["full_name"] = employee_row["full_name"]
    st.session_state["email"] = employee_row["email"]
    st.session_state["role"] = role  # "hr" or "employee"
    st.session_state["department"] = employee_row.get("current_department", "")

def clear_session():
    for key in ["logged_in", "employee_id", "full_name", "email", "role", "department"]:
        st.session_state.pop(key, None)

def require_login():
    if not st.session_state.get("logged_in"):
        st.warning("Please log in to access this page.")
        st.stop()

def require_hr():
    require_login()
    if st.session_state.get("role") != "hr":
        st.error("Access denied. HR only.")
        st.stop()
