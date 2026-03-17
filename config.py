import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

def _get(key: str, default=None):
    """Read from Streamlit secrets first, then env vars, then default."""
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)

DB_CONFIG = {
    "host":     _get("DB_HOST", "localhost"),
    "user":     _get("DB_USER", "root"),
    "password": _get("DB_PASSWORD", ""),
    "database": _get("DB_NAME", "internal_mobility_db"),
    "port":     int(_get("DB_PORT", 3306)),
}

APP_NAME = "InternalMobility Hub"
VERSION  = "1.0.0"
