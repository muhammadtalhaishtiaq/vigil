"""
app.py — Vigil Navigation Router
Defines the 3-page structure: Landing (default /) → Dashboard (/dashboard) → Profile (/profile)
"""
import streamlit as st

st.set_page_config(
    page_title="Vigil — Risk Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

pg = st.navigation(
    [
        st.Page("pages/landing.py",   title="Vigil",     icon="⚡", default=True),
        st.Page("pages/dashboard.py", title="Dashboard", icon="📊", url_path="dashboard"),
        st.Page("pages/profile.py",   title="Profile",   icon="🏢", url_path="profile"),
    ],
    position="hidden",  # hides the default sidebar nav
)

pg.run()
