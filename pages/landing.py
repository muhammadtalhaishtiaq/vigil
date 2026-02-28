"""
pages/landing.py — Vigil Landing Page
Serves vigil-landing.html via st.components.v1.html.
All navigation links wired to /dashboard and /profile via window.parent.
Auto-resizes iframe to content height to eliminate extra whitespace.
"""
import sys
import os
from pathlib import Path

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Hide Streamlit chrome so the full landing page fills the viewport
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
[data-testid="stMain"] { padding: 0 !important; }
</style>
""", unsafe_allow_html=True)

landing_path = Path(__file__).parent.parent / "vigil-landing.html"

if landing_path.exists():
    html = landing_path.read_text(encoding="utf-8")

    # ── Fix every link that points to vigil-dashboard.html ──────────────────
    # href="vigil-dashboard.html" → JS parent navigation
    html = html.replace(
        'href="vigil-dashboard.html"',
        'href="javascript:void(0)" onclick="window.parent.location.href=\'/dashboard\'"'
    )
    # onclick="location.href='vigil-dashboard.html'"
    html = html.replace(
        "onclick=\"location.href='vigil-dashboard.html'\"",
        "onclick=\"window.parent.location.href='/dashboard'\""
    )

    # ── Fix every link that points to vigil-profile.html ────────────────────
    html = html.replace(
        'href="vigil-profile.html"',
        'href="javascript:void(0)" onclick="window.parent.location.href=\'/profile\'"'
    )
    html = html.replace(
        "onclick=\"location.href='vigil-profile.html'\"",
        "onclick=\"window.parent.location.href='/profile'\""
    )

    # ── Fix any remaining #dashboard / #profile anchors ─────────────────────
    html = html.replace('href="#dashboard"', 'href="javascript:void(0)" onclick="window.parent.location.href=\'/dashboard\'"')
    html = html.replace('href="#profile"',   'href="javascript:void(0)" onclick="window.parent.location.href=\'/profile\'"')

    # ── Inject auto-resize script before </body> ────────────────────────────
    auto_resize = """
<script>
(function() {
  function sendHeight() {
    var h = Math.max(
      document.body.scrollHeight,
      document.documentElement.scrollHeight
    );
    window.parent.postMessage({isStreamlitMessage: true, type: 'streamlit:setFrameHeight', height: h}, '*');
  }
  window.addEventListener('load', sendHeight);
  window.addEventListener('resize', sendHeight);
  // Fire immediately and again after fonts/images load
  setTimeout(sendHeight, 300);
  setTimeout(sendHeight, 1200);
})();
</script>
"""
    html = html.replace("</body>", auto_resize + "</body>")

    # Render — height=8000 as safe fallback; auto-resize script will correct it
    st.components.v1.html(html, height=8000, scrolling=False)

else:
    st.error("vigil-landing.html not found.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("⚡ Go to Dashboard"):
            st.switch_page("pages/dashboard.py")
    with col2:
        if st.button("Set up Profile"):
            st.switch_page("pages/profile.py")
