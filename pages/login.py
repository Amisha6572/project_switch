import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
from utils.db import get_employee_by_email
from utils.auth import verify_password, is_hr, set_session

st.set_page_config(page_title="Login", page_icon="🔐")
st.title("🔐 Login")

with st.form("login_form"):
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    submitted = st.form_submit_button("Login")

if submitted:
    if not email or not password:
        st.error("Please fill in all fields.")
    else:
        df = get_employee_by_email(email.strip().lower())
        if df.empty:
            st.error("Invalid email or password.")
        else:
            row = df.iloc[0]
            if verify_password(password, str(row.get("password_hash", ""))):
                role = "hr" if is_hr(email) else "employee"
                set_session(row, role)
                st.success(f"Welcome, {row['full_name']}!")
                st.rerun()
            else:
                st.error("Invalid email or password.")

if st.session_state.get("logged_in"):
    st.info(f"Already logged in as {st.session_state['full_name']}")
    if st.button("Go to Dashboard"):
        if st.session_state["role"] == "hr":
            st.switch_page("pages/hr_dashboard.py")
        else:
            st.switch_page("pages/employee_dashboard.py")
