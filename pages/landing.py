"""
pages/landing.py — Vigil Landing Page
Serves the vigil-landing.html file directly, wires CTAs.
"""
import sys
import os
from pathlib import Path

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

st.set_page_config(
    page_title="Vigil — Risk Intelligence Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Hide Streamlit chrome
st.markdown("""
<style>
#MainMenu, footer, header,
[data-testid="stToolbar"],
[data-testid="stStatusWidget"],
[data-testid="stDecoration"],
[data-testid="stHeader"] { display: none !important; }
.stDeployButton { display: none !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }
[data-testid="stAppViewBlockContainer"] { padding: 0 !important; }
</style>
""", unsafe_allow_html=True)

# Serve the HTML file
landing_path = Path(__file__).parent.parent / "vigil-landing.html"

if landing_path.exists():
    html_content = landing_path.read_text(encoding="utf-8")
    # Wire CTAs: replace href links to point to correct Streamlit pages
    html_content = html_content.replace('href="#dashboard"', 'href="/" target="_self"')
    html_content = html_content.replace('href="#profile"', 'href="/profile" target="_self"')
    # Handle onclick CTA buttons
    html_content = html_content.replace(
        "window.location.href='dashboard.html'",
        "window.parent.location.href='/'"
    )
    html_content = html_content.replace(
        "window.location.href='index.html'",
        "window.parent.location.href='/'"
    )
    html_content = html_content.replace(
        "window.location.href='profile.html'",
        "window.parent.location.href='/profile'"
    )
    st.components.v1.html(html_content, height=6000, scrolling=True)
else:
    st.error("Landing page not found. Please check vigil-landing.html exists.")
    st.markdown("## ⚡ VIGIL")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("⚡ Go to Dashboard"):
            st.switch_page("app.py")
    with col2:
        if st.button("Set up Profile"):
            st.switch_page("pages/profile.py")
