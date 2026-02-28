"""
app.py — Vigil Financial Intelligence Dashboard
Pixel-perfect match to vigil-dashboard.html reference design.
"""
import os, re, json, time, html as _html
from datetime import datetime, timezone
import streamlit as st


# =============================================================================
# MARKDOWN → HTML CONVERTER
# Uses the `markdown` library (installed) with safe HTML sanitisation.
# Falls back to a basic regex converter if the library is unavailable.
# =============================================================================
def md_to_html(text: str) -> str:
    """
    Convert a markdown string to HTML for display inside chat bubbles.

    Handles:
        - **bold** / *italic*
        - # h1 / ## h2 / ### h3 headings
        - - bullet lists  /  1. numbered lists
        - `inline code`  /  ```code blocks```
        - > blockquotes
        - --- horizontal rules
        - Preserves line breaks with <br>

    Returns safe HTML (no user-injected scripts).
    """
    try:
        import markdown as _md
        # Convert markdown to HTML; nl2br turns \n into <br> inside paragraphs
        html_out = _md.markdown(
            text,
            extensions=["nl2br", "sane_lists"],
        )
        return html_out
    except Exception:
        # Fallback: lightweight regex-based converter
        return _md_fallback(text)


def _md_fallback(text: str) -> str:
    """Regex-based markdown-to-HTML fallback (no external deps)."""
    # Escape HTML entities first, then re-introduce safe tags
    t = _html.escape(text)

    # Code blocks (``` ... ```)
    t = re.sub(r'```[^\n]*\n?(.*?)```', lambda m: f'<pre><code>{m.group(1)}</code></pre>', t, flags=re.DOTALL)
    # Inline code
    t = re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
    # Headings
    t = re.sub(r'^### (.+)$', r'<h5>\1</h5>', t, flags=re.MULTILINE)
    t = re.sub(r'^## (.+)$', r'<h4>\1</h4>', t, flags=re.MULTILINE)
    t = re.sub(r'^# (.+)$', r'<h3>\1</h3>', t, flags=re.MULTILINE)
    # Bold + italic
    t = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', t)
    t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'\*(.+?)\*', r'<em>\1</em>', t)
    # Blockquotes
    t = re.sub(r'^&gt; (.+)$', r'<blockquote>\1</blockquote>', t, flags=re.MULTILINE)
    # Horizontal rule
    t = re.sub(r'^---+$', r'<hr>', t, flags=re.MULTILINE)
    # Unordered lists
    t = re.sub(r'^[-*+] (.+)$', r'<li>\1</li>', t, flags=re.MULTILINE)
    t = re.sub(r'(<li>.*?</li>\n?)+', lambda m: f'<ul>{m.group(0)}</ul>', t, flags=re.DOTALL)
    # Ordered lists
    t = re.sub(r'^\d+\. (.+)$', r'<li>\1</li>', t, flags=re.MULTILINE)
    # Line breaks
    t = t.replace('\n', '<br>')
    return t

from data_layer import get_all_live_data
from session_manager import (
    init_conversation, load_profile, should_auto_load,
    get_auto_load_prompt, mark_auto_loaded, has_sufficient_profile,
    add_message, get_conversation_history,
)
from agent_pipeline import run_pipeline, update_agent_status

st.set_page_config(
    page_title="Vigil — Risk Intelligence",
    page_icon="⚡", layout="wide",
    initial_sidebar_state="collapsed",
)

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=90_000, key="vigil_refresh", debounce=False)
except ImportError:
    pass


# =============================================================================
# TIER / SCORE COLOR HELPERS
# =============================================================================
def tier_color(tier):
    t = (tier or "").upper()
    if "GREEN" in t: return "var(--g)"
    if "YELLOW" in t: return "var(--ye)"
    if "ORANGE" in t: return "var(--or)"
    if "RED" in t: return "var(--re)"
    if "DARK" in t: return "#c62828"
    return "var(--tx2)"


def score_color(score):
    if score is None: return "var(--tx3)"
    if score <= 25: return "var(--g)"
    if score <= 50: return "var(--ye)"
    if score <= 70: return "var(--or)"
    if score <= 85: return "var(--re)"
    return "#c62828"


def _time_ago(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        mins = int(delta.total_seconds() // 60)
        if mins < 1: return "just now"
        if mins < 60: return f"{mins}m ago"
        hrs = mins // 60
        return f"{hrs}h ago" if hrs < 24 else f"{hrs // 24}d ago"
    except Exception:
        return ""


def _trunc(s, n):
    return (s[:n] + "…") if len(s) > n else s


# =============================================================================
# CSS — ALL CLASSES FROM REFERENCE HTML
# =============================================================================
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,300;0,400;0,500;1,400&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Cabinet+Grotesk:wght@400;500;600;700;800;900&display=swap');

:root {
  --bg:#070809; --bg2:#0b0d10; --sf:#101316; --sf2:#161b21; --sf3:#1c2229;
  --br:#1c2229; --br2:#252d38;
  --g:#00e676; --gd:rgba(0,230,118,.09); --gg:rgba(0,230,118,.2);
  --or:#ff9100; --re:#ff5252; --ye:#ffd740; --bl:#448aff; --pu:#ce93d8;
  --tx:#dde3ea; --tx2:#6b7787; --tx3:#2e3844;
  --mono:'DM Mono',monospace; --head:'Cabinet Grotesk',sans-serif;
  --r:8px; --r2:12px;
}
[data-theme=light]{
  --bg:#f0f2f6; --bg2:#e8ecf1; --sf:#fff; --sf2:#f5f7fa; --sf3:#edf0f5;
  --br:#dde2ea; --br2:#cdd4df; --tx:#0c1117; --tx2:#4a5568; --tx3:#9aaabb;
}

/* ── Streamlit chrome removal ── */
[data-testid="stAppViewBlockContainer"]{padding:0!important;}
[data-testid="stHeader"]{display:none!important;height:0!important;min-height:0!important;overflow:hidden!important;}
[data-testid="stMain"]{padding-top:0!important;}
[data-testid="stMainBlockContainer"]{padding:0!important;max-width:100%!important;}
section.main>div{padding-top:0!important;}
.block-container{padding-top:0!important;padding-left:0!important;padding-right:0!important;max-width:100%!important;}
.stApp>header{display:none!important;height:0!important;}
[data-testid="stBottomBlockContainer"]{padding:0!important;}
[data-testid="column"]{padding:0!important;}
[data-testid="stForm"]{border:none!important;padding:0!important;}
.stApp{background:var(--bg)!important;}

/* Hide the Streamlit form completely — only used for Python-side submission */
.vigil-hidden-form{visibility:hidden;height:0;overflow:hidden;position:absolute;top:-9999px;left:-9999px;}
[data-testid="stTextInput"]{visibility:hidden;height:0;overflow:hidden;position:absolute;}
[data-testid="stFormSubmitButton"]{visibility:hidden;height:0;overflow:hidden;position:absolute;}

/* ── Animations ── */
@keyframes dotPulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.7)}}
@keyframes logoPulse{0%,100%{box-shadow:0 0 6px var(--gg)}50%{box-shadow:0 0 14px var(--gg),0 0 28px var(--gg)}}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
@keyframes fadeUp{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
@keyframes barGrow{from{width:0}to{width:var(--bar-w,100%)}}
@keyframes spin{to{transform:rotate(360deg)}}

/* ── App wrapper ── */
.app{
  font-family:var(--mono);
  background:var(--bg);
  color:var(--tx);
  min-height:100vh;
  display:flex;
  flex-direction:column;
}

/* ── HEADER ── */
.hdr{
  height:48px;
  background:var(--sf);
  border-bottom:1px solid var(--br);
  display:flex;
  align-items:center;
  padding:0 14px;
  gap:12px;
  flex-shrink:0;
  z-index:100;
  position:sticky;
  top:0;
}
.logo{
  display:flex;
  align-items:center;
  gap:6px;
  text-decoration:none;
  flex-shrink:0;
}
.logo-glyph{
  width:26px;height:26px;border-radius:6px;
  background:var(--g);
  display:flex;align-items:center;justify-content:center;
  font-size:13px;color:#000;font-weight:900;
  animation:logoPulse 3s ease-in-out infinite;
}
.logo-name{
  font-family:var(--head);font-weight:800;font-size:14px;
  letter-spacing:.08em;color:var(--tx);
}
.vdiv{width:1px;height:24px;background:var(--br2);flex-shrink:0;margin:0 2px;}

/* ── Agent flow ── */
.aflow{display:flex;align-items:center;gap:2px;flex:1;min-width:0;overflow:hidden;}
.afn{
  display:flex;align-items:center;gap:4px;
  padding:3px 7px;border-radius:4px;
  font-size:8px;color:var(--tx3);
  transition:all .2s;white-space:nowrap;
  border:1px solid transparent;
}
.afn.done{
  color:var(--g);
  background:var(--gd);
  border-color:var(--gg);
}
.afn.active{
  color:var(--g);
  background:rgba(0,230,118,.05);
  border-color:var(--gg);
  box-shadow:0 0 8px rgba(0,230,118,.15);
  animation:blink 1.2s ease-in-out infinite;
}
.afn.err{color:var(--re);background:rgba(255,82,82,.08);border-color:rgba(255,82,82,.2);}
.afd{
  width:5px;height:5px;border-radius:50%;
  background:var(--br2);flex-shrink:0;
}
.afn.done .afd{background:var(--g);}
.afn.active .afd{background:var(--g);animation:dotPulse 1s ease-in-out infinite;}
.afn.err .afd{background:var(--re);}
.afx{font-size:8px;color:var(--br2);flex-shrink:0;margin:0 1px;}

/* ── Header right ── */
.hright{display:flex;align-items:center;gap:8px;flex-shrink:0;}
.live-badge{
  display:flex;align-items:center;gap:4px;
  font-size:7.5px;font-weight:600;letter-spacing:.08em;
  color:var(--g);padding:2px 7px;border-radius:10px;
  background:var(--gd);border:1px solid var(--gg);
}
.ldot{
  width:5px;height:5px;border-radius:50%;
  background:var(--g);
  animation:dotPulse .9s ease-in-out infinite;
}
.hclock{font-size:9px;color:var(--tx2);font-family:var(--mono);}
.prof-pill{
  display:flex;align-items:center;gap:5px;
  padding:3px 10px;border-radius:10px;
  background:var(--sf2);border:1px solid var(--br2);
  font-size:9px;color:var(--tx);text-decoration:none;
  transition:border-color .15s;cursor:pointer;
}
.prof-pill:hover{border-color:var(--g);}
.pdot{
  width:6px;height:6px;border-radius:50%;
  background:var(--g);flex-shrink:0;
}
.tbtn{
  width:26px;height:26px;border-radius:6px;
  background:var(--sf2);border:1px solid var(--br2);
  cursor:pointer;font-size:12px;
  display:flex;align-items:center;justify-content:center;
  transition:border-color .15s;
}
.tbtn:hover{border-color:var(--tx2);}

/* ── VERDICT BAR ── */
.vbar{
  height:42px;
  background:var(--sf);
  border-bottom:1px solid var(--br);
  display:flex;
  align-items:center;
  padding:0 14px;
  gap:10px;
  flex-shrink:0;
}
.vscore{display:flex;align-items:center;gap:6px;flex-shrink:0;}
.vsnum{
  font-family:var(--head);font-weight:800;font-size:22px;
  line-height:1;min-width:32px;
}
.vstier{
  font-size:8px;font-weight:600;letter-spacing:.06em;
  padding:2px 6px;border-radius:4px;
}
.vsdir{font-size:9px;color:var(--tx3);}
.vtext{flex:1;font-size:10px;color:var(--tx);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.vtext em{font-style:normal;font-weight:600;}
.vchips{display:flex;align-items:center;gap:5px;flex-shrink:0;}
.vc{
  font-size:8px;padding:3px 9px;border-radius:10px;
  background:var(--sf2);border:1px solid var(--br2);
  color:var(--tx2);cursor:pointer;white-space:nowrap;
  transition:all .15s;
}
.vc:hover{border-color:var(--g);color:var(--g);background:var(--gd);}

/* ── INTELLIGENCE BAR ── */
.ibar{display:none;flex-direction:column;border-bottom:1px solid var(--br);flex-shrink:0;}
.ibar.on{display:flex;}
.ibar-strip{
  height:36px;
  background:var(--sf2);
  display:flex;align-items:center;
  padding:0 14px;gap:8px;
  cursor:pointer;
  transition:background .15s;
  border-bottom:1px solid transparent;
}
.ibar-strip:hover{background:var(--sf3);}
.ibar-strip.open{border-bottom-color:var(--br);}
.sl{font-size:7px;color:var(--tx3);letter-spacing:.1em;text-transform:uppercase;flex-shrink:0;}
.rchip{
  display:flex;align-items:center;gap:4px;
  padding:2px 8px;border-radius:4px;
  font-size:8px;white-space:nowrap;cursor:pointer;
  transition:opacity .15s;
}
.rchip:hover{opacity:.75;}
.rc1{background:rgba(255,82,82,.1);border:1px solid rgba(255,82,82,.22);color:#ff8a80;}
.rc2{background:rgba(255,145,0,.1);border:1px solid rgba(255,145,0,.22);color:#ffb74d;}
.rc3{background:rgba(255,215,64,.1);border:1px solid rgba(255,215,64,.22);color:#ffd740;}
.achip{
  display:flex;align-items:center;gap:4px;
  padding:2px 8px;border-radius:4px;
  font-size:8px;white-space:nowrap;cursor:pointer;
  background:var(--gd);border:1px solid var(--gg);color:#69f0ae;
  transition:opacity .15s;
}
.achip:hover{opacity:.75;}
.chip-txt{font-size:8px;}
.chip-meta{font-size:7px;opacity:.65;padding:1px 4px;border-radius:3px;background:rgba(255,255,255,.06);}
.sdiv{width:1px;height:18px;background:var(--br2);flex-shrink:0;margin:0 3px;}
.ibar-hint{margin-left:auto;display:flex;align-items:center;gap:4px;font-size:7.5px;color:var(--tx3);flex-shrink:0;}
.ibar-caret{font-size:9px;transition:transform .2s;}
.ibar-strip.open .ibar-caret{transform:rotate(180deg);}

/* ── Intelligence Drawer ── */
.idrawer{
  max-height:0;overflow:hidden;
  transition:max-height .28s cubic-bezier(.4,0,.2,1);
  background:var(--bg2);
}
.idrawer.open{max-height:520px;}

/* ── Drawer tabs ── */
.dtabs{
  display:flex;align-items:center;
  border-bottom:1px solid var(--br);
  padding:0 14px;background:var(--sf);
  position:sticky;top:0;z-index:10;gap:0;
}
.dtab{
  font-size:8.5px;color:var(--tx3);
  padding:9px 12px;cursor:pointer;
  border-bottom:2px solid transparent;
  transition:all .15s;white-space:nowrap;
  font-family:var(--mono);
}
.dtab:hover{color:var(--tx);}
.dtab.active{color:var(--g);border-bottom-color:var(--g);}
.dtab-close{
  margin-left:auto;font-size:10px;color:var(--tx3);
  cursor:pointer;padding:4px 8px;border-radius:4px;
  transition:color .15s;
}
.dtab-close:hover{color:var(--tx);}

.dbody{height:275px;overflow-y:auto;padding:12px 14px;}
.dtabpanel{display:none;}
.dtabpanel.active{display:block;}

/* ── Risks tab ── */
.drisks-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;}
.drc{
  background:var(--sf);border:1px solid var(--br2);
  border-radius:var(--r);padding:10px;
  border-left:3px solid var(--re);
}
.drc.r2{border-left-color:var(--or);}
.drc.r3{border-left-color:var(--ye);}
.drc-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;}
.drc-name{font-size:9.5px;font-weight:600;color:var(--tx);}
.drc-prob{font-size:8px;color:var(--re);}
.drc.r2 .drc-prob{color:var(--or);}
.drc.r3 .drc-prob{color:var(--ye);}
.drc-bar{height:3px;background:var(--sf3);border-radius:2px;margin-bottom:6px;overflow:hidden;}
.drc-bar-fill{height:100%;border-radius:2px;background:var(--re);transition:width .8s ease;}
.drc.r2 .drc-bar-fill{background:var(--or);}
.drc.r3 .drc-bar-fill{background:var(--ye);}
.drc-detail{font-size:8.5px;color:var(--tx2);line-height:1.55;margin-bottom:5px;}
.drc-ignored{font-size:7.5px;color:var(--tx3);font-style:italic;margin-bottom:5px;}
.drc-tags{display:flex;flex-wrap:wrap;gap:3px;}
.drc-tag{font-size:7px;padding:1px 5px;border-radius:3px;background:var(--sf3);color:var(--tx3);}

/* ── Actions tab ── */
.dactions-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;}
.dac{
  background:var(--sf);border:1px solid var(--br2);
  border-radius:var(--r);padding:10px;cursor:pointer;
  transition:opacity .2s,border-color .2s;
}
.dac:hover{border-color:var(--g);}
.dac.done{opacity:.5;}
.dac-titlerow{display:flex;align-items:center;gap:6px;margin-bottom:5px;}
.dac-check{
  width:14px;height:14px;border-radius:3px;
  border:1.5px solid var(--br2);
  display:flex;align-items:center;justify-content:center;
  font-size:8px;color:var(--g);flex-shrink:0;
  transition:all .15s;
}
.dac-check.done{background:var(--g);border-color:var(--g);color:#000;}
.dac-title{font-size:9px;font-weight:600;color:var(--tx);}
.dac-detail{font-size:8px;color:var(--tx2);line-height:1.55;margin-bottom:6px;}
.dac-tags{display:flex;flex-wrap:wrap;gap:3px;}
.datag{font-size:7px;padding:1px 5px;border-radius:3px;}
.datag.ow{background:rgba(0,230,118,.08);color:#69f0ae;border:1px solid rgba(0,230,118,.18);}
.datag.dl{background:rgba(255,145,0,.08);color:#ffb74d;border:1px solid rgba(255,145,0,.18);}
.datag.et{background:rgba(68,138,255,.08);color:#7eb5ff;border:1px solid rgba(68,138,255,.18);}
.datag.ur{background:rgba(255,82,82,.08);color:#ff8a80;border:1px solid rgba(255,82,82,.18);}

/* ── Playbook tab ── */
.dplaybook-layout{display:grid;grid-template-columns:1fr 260px;gap:12px;}
.dpb-copy{
  font-size:8px;padding:4px 10px;border-radius:4px;margin-bottom:8px;
  background:var(--sf2);border:1px solid var(--br2);color:var(--tx2);
  cursor:pointer;transition:all .15s;
}
.dpb-copy:hover{border-color:var(--g);color:var(--g);}
.dpb-content{
  font-size:9px;color:var(--tx2);line-height:1.7;
  white-space:pre-wrap;
  max-height:220px;overflow-y:auto;
}
.dpb-sidebar{
  background:var(--sf);border:1px solid var(--br2);
  border-radius:var(--r);padding:10px;
}
.dpbs-lbl{font-size:7.5px;color:var(--tx3);letter-spacing:.08em;text-transform:uppercase;margin-bottom:4px;}
.dpbs-val{font-family:var(--head);font-weight:700;font-size:12px;color:var(--tx);margin-bottom:8px;}
.dpbs-row{display:flex;align-items:center;gap:5px;margin-bottom:5px;}
.dpbs-lbl2{font-size:7.5px;color:var(--tx3);width:60px;flex-shrink:0;}
.dpbs-track{flex:1;height:3px;background:var(--sf3);border-radius:2px;overflow:hidden;}
.dpbs-fill{height:100%;border-radius:2px;background:var(--g);}
.dpbs-num{font-size:7.5px;color:var(--tx2);width:20px;text-align:right;flex-shrink:0;}
.dpbs-composite{
  margin-top:8px;padding-top:8px;
  border-top:1px solid var(--br);
}
.dpbs-clbl{font-size:7.5px;color:var(--tx3);margin-bottom:2px;}
.dpbs-cval{font-family:var(--head);font-weight:800;font-size:20px;}

/* ── Oracle tab ── */
.doracle-layout{display:grid;grid-template-columns:200px 1fr;gap:12px;}
.dov-box{
  background:var(--sf);border:1px solid var(--br2);
  border-radius:var(--r);padding:14px;
}
.dov-lbl{font-size:7.5px;color:var(--tx3);letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px;}
.dov-val{font-family:var(--head);font-weight:800;font-size:18px;margin-bottom:4px;}
.dov-conf{font-size:8px;color:var(--tx3);}
.doracle-cases{display:flex;flex-direction:column;gap:7px;}
.doc{
  padding:9px 11px;border-radius:var(--r);
  font-size:8.5px;color:var(--tx2);line-height:1.5;
  position:relative;
}
.doc.bull{background:rgba(0,230,118,.05);border:1px solid rgba(0,230,118,.18);}
.doc.bear{background:rgba(255,82,82,.05);border:1px solid rgba(255,82,82,.18);}
.doc.hist{background:var(--sf3);border:1px solid var(--br2);font-style:italic;}
.doc.take{background:var(--sf2);border:1px solid var(--br2);}
.doc-disc{
  font-size:7.5px;font-weight:700;letter-spacing:.05em;
  margin-bottom:3px;display:block;
}
.doc.bull .doc-disc{color:var(--g);}
.doc.bear .doc-disc{color:var(--re);}
.doc.hist .doc-disc{color:var(--tx3);}
.doc.take .doc-disc{color:var(--ye);}
.oracle-empty{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  height:200px;gap:8px;
}
.oracle-empty-title{font-size:11px;color:var(--tx2);font-weight:600;}
.oracle-empty-sub{font-size:9px;color:var(--tx3);}
.oracle-echips{display:flex;gap:6px;flex-wrap:wrap;justify-content:center;margin-top:4px;}
.oracle-ec{
  font-size:8px;padding:3px 9px;border-radius:10px;
  background:var(--sf2);border:1px solid var(--br2);
  color:var(--tx2);cursor:pointer;
  transition:all .15s;
}
.oracle-ec:hover{border-color:var(--g);color:var(--g);}

/* ── Scores tab ── */
.dscores-layout{display:grid;grid-template-columns:1fr 240px;gap:12px;}
.dsc-rows{}
.dsc-row{display:flex;align-items:center;gap:7px;margin-bottom:6px;}
.dsc-lbl{font-size:8px;color:var(--tx3);width:110px;flex-shrink:0;}
.dsc-track{flex:1;height:3px;background:var(--sf3);border-radius:2px;overflow:hidden;}
.dsc-fill{height:100%;border-radius:2px;transition:width .8s ease;}
.dsc-wt{font-size:7.5px;color:var(--tx3);width:22px;text-align:right;flex-shrink:0;}
.dsc-val{font-size:8px;color:var(--tx2);width:26px;text-align:right;flex-shrink:0;}
.dsc-formula{
  margin-top:10px;padding:8px;border-radius:var(--r);
  background:var(--sf);border:1px solid var(--br2);
  font-size:8px;color:var(--tx3);line-height:1.6;
}
.dsc-right{display:flex;flex-direction:column;gap:10px;}
.dsc-big{
  background:var(--sf);border:1px solid var(--br2);
  border-radius:var(--r);padding:14px;text-align:center;
}
.dsc-big-lbl{font-size:7.5px;color:var(--tx3);letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px;}
.dsc-big-val{font-family:var(--head);font-weight:800;font-size:36px;line-height:1;}
.dsc-big-tier{font-size:9px;margin-top:4px;}
.dsc-coherence{
  background:var(--sf);border:1px solid var(--br2);
  border-radius:var(--r);padding:10px;
}
.dsc-coh-lbl{font-size:7.5px;color:var(--tx3);margin-bottom:5px;}
.dsc-coh-badge{
  font-size:9px;padding:4px 10px;border-radius:4px;
  display:inline-block;
}

/* ── MAIN BODY ── */
.mbody{
  display:grid;
  grid-template-columns:210px 1fr 208px;
  gap:1px;
  flex:1;
  min-height:0;
  background:var(--br);
}

/* ── LEFT PANEL ── */
.lpanel{
  background:var(--bg2);
  display:flex;flex-direction:column;
  overflow:hidden;
}
.lptop{flex:1;overflow-y:auto;min-height:0;}
.lpbot{flex-shrink:0;}
.ptitle{
  font-size:7.5px;color:var(--tx3);letter-spacing:.1em;text-transform:uppercase;
  padding:7px 11px 5px;border-bottom:1px solid var(--br);
  display:flex;align-items:center;gap:5px;
  position:sticky;top:0;background:var(--bg2);z-index:2;
}
.pscroll{overflow-y:auto;}
.ni{
  padding:6px 11px;border-bottom:1px solid var(--br);
  cursor:pointer;transition:background .12s;
}
.ni:hover{background:var(--sf2);}
.ni-src{font-size:7.5px;color:var(--g);display:flex;align-items:center;justify-content:space-between;margin-bottom:2px;}
.ni-hl{
  font-size:9.5px;color:var(--tx);line-height:1.35;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
}
.ni-t{font-size:7.5px;color:var(--tx3);margin-top:2px;}
.sdot-p{width:5px;height:5px;border-radius:50%;background:var(--g);display:inline-block;}
.sdot-n{width:5px;height:5px;border-radius:50%;background:var(--re);display:inline-block;}
.sdot-u{width:5px;height:5px;border-radius:50%;background:var(--tx3);display:inline-block;}

/* Sector mini grid */
.smini{display:grid;grid-template-columns:1fr 1fr;gap:4px;padding:7px;}
.sb{
  padding:5px 7px;border-radius:5px;
  background:var(--sf2);border:1px solid var(--br2);
  cursor:pointer;transition:transform .12s;
}
.sb:hover{transform:scale(1.04);}
.sb.up{border-color:rgba(0,230,118,.18);background:rgba(0,230,118,.04);}
.sb.dn{border-color:rgba(255,82,82,.18);background:rgba(255,82,82,.04);}
.sbn{font-size:7px;color:var(--tx3);margin-bottom:2px;}
.sbp{font-family:var(--head);font-weight:700;font-size:12px;}
.sbp.up{color:var(--g);}
.sbp.dn{color:var(--re);}
.sbp.fl{color:var(--tx2);}

/* Regime card */
.regime-card{
  margin:5px 7px;padding:6px 9px;border-radius:5px;
  background:var(--sf2);border:1px solid var(--br2);
}
.regime-val{font-size:9px;font-weight:600;}
.regime-sub{font-size:7.5px;color:var(--tx3);margin-top:1px;}

/* Stance card */
.stance-card{
  margin:5px 7px;padding:6px 9px;border-radius:5px;
  background:var(--gd);border:1px solid var(--gg);
}
.stance-lbl{font-size:7px;color:var(--tx3);letter-spacing:.08em;text-transform:uppercase;margin-bottom:2px;}
.stance-val{font-family:var(--head);font-size:11px;font-weight:700;color:var(--g);}

/* Sector news in left panel */
.rni{padding:5px 11px;border-bottom:1px solid var(--br);cursor:pointer;transition:background .12s;}
.rni:hover{background:var(--sf2);}
.rni-src{font-size:7px;color:var(--g);margin-bottom:1px;}
.rni-hl{font-size:8.5px;color:var(--tx);line-height:1.3;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}

/* ── CENTER PANEL ── */
.cpanel{
  background:var(--bg);
  display:flex;flex-direction:column;
  min-height:0;
}
.cthread{
  flex:1;overflow-y:auto;
  display:flex;flex-direction:column;
  gap:10px;padding:14px 16px;
  min-height:0;
}
.msg{animation:fadeUp .25s ease;}
.msg.user{display:flex;flex-direction:column;align-items:flex-end;}
.msg.sys{display:flex;flex-direction:column;align-items:flex-start;width:100%;}
.mlbl{font-size:8px;color:var(--tx3);margin-bottom:3px;display:flex;align-items:center;gap:5px;}
.msg.user .mlbl{color:var(--g);}
.bubble{
  padding:9px 13px;border-radius:var(--r2);
  font-size:11px;line-height:1.55;
}
.msg.user .bubble{
  max-width:75%;background:var(--gd);
  border:1px solid var(--gg);color:var(--tx);
}
.msg.sys .bubble{
  width:100%;background:var(--sf2);
  border:1px solid var(--br2);color:var(--tx);
}

/* Agent output card inside sys bubble */
.acard{
  background:var(--sf);border:1px solid var(--br2);
  border-radius:var(--r);margin-top:7px;overflow:hidden;
}
.acard-head{
  display:flex;align-items:center;gap:6px;
  padding:5px 9px;border-bottom:1px solid var(--br);
}
.acard-dot{width:6px;height:6px;border-radius:50%;background:var(--g);}
.acard-name{font-size:8px;color:var(--tx2);flex:1;}
.acard-t{font-size:7.5px;color:var(--g);background:var(--gd);padding:1px 5px;border-radius:3px;}
.acard-body{
  padding:8px 10px;font-size:9.5px;color:var(--tx2);
  line-height:1.6;max-height:180px;overflow-y:auto;
  white-space:pre-wrap;
}

/* ── Markdown formatting inside vigil chat bubbles ── */
.vigil-md p{margin:0 0 6px 0;}
.vigil-md h3,.vigil-md h4,.vigil-md h5{
  color:var(--tx1);font-weight:600;margin:8px 0 4px 0;font-size:11px;
}
.vigil-md strong{color:var(--tx1);font-weight:600;}
.vigil-md em{color:var(--ye);font-style:italic;}
.vigil-md ul,.vigil-md ol{margin:4px 0 6px 14px;padding:0;}
.vigil-md li{margin:2px 0;line-height:1.5;}
.vigil-md code{
  background:rgba(255,255,255,0.06);border-radius:3px;
  padding:1px 4px;font-family:monospace;font-size:9px;color:var(--g);
}
.vigil-md pre{
  background:rgba(255,255,255,0.04);border-radius:4px;
  padding:8px;overflow-x:auto;margin:6px 0;
}
.vigil-md blockquote{
  border-left:2px solid var(--g);padding-left:8px;
  color:var(--tx2);margin:4px 0;font-style:italic;
}
.vigil-md hr{border:none;border-top:1px solid var(--bdr);margin:8px 0;}
.vigil-md a{color:var(--g);text-decoration:none;}
.vigil-md a:hover{text-decoration:underline;}

/* ── Chat input ── */
.cinput-wrap{
  padding:10px 14px;
  border-top:1px solid var(--br);
  background:var(--sf);
  flex-shrink:0;
}
.crow{display:flex;align-items:center;gap:7px;margin-bottom:7px;}
.cin{
  flex:1;background:var(--sf2);border:1px solid var(--br2);
  color:var(--tx);border-radius:var(--r);
  font-family:var(--mono);font-size:11px;
  padding:9px 13px;outline:none;transition:border-color .15s;
}
.cin:focus{border-color:var(--g);box-shadow:0 0 0 3px var(--gd);}
.cin::placeholder{color:var(--tx3);}
.sbtn{
  padding:9px 16px;border-radius:var(--r);
  background:var(--g);color:#000;
  font-family:var(--head);font-weight:700;font-size:12px;
  border:none;cursor:pointer;white-space:nowrap;
  transition:all .15s;flex-shrink:0;
}
.sbtn:hover{filter:brightness(1.1);box-shadow:0 0 10px var(--gg);}
.sbtn:disabled{opacity:.5;cursor:not-allowed;}
.qrow{display:flex;gap:5px;flex-wrap:wrap;}
.qp{
  font-size:8px;padding:3px 9px;border-radius:10px;
  background:var(--sf2);border:1px solid var(--br2);
  color:var(--tx2);cursor:pointer;white-space:nowrap;
  transition:all .15s;
}
.qp:hover{border-color:var(--g);color:var(--g);}

/* ── RIGHT PANEL ── */
.rpanel{
  background:var(--bg2);
  display:flex;flex-direction:column;
  overflow:hidden;
}
.rscroll{overflow-y:auto;flex:1;min-height:0;}
.rblock{border-bottom:1px solid var(--br);}

/* Profile block */
.cctx{padding:10px 11px;}
.ccname{font-family:var(--head);font-weight:700;font-size:13px;color:var(--tx);margin-bottom:2px;}
.ccsub{font-size:8px;color:var(--tx3);margin-bottom:6px;}
.cctags{display:flex;flex-wrap:wrap;gap:3px;margin-bottom:6px;}
.ctag{font-size:7.5px;padding:2px 6px;border-radius:3px;}
.ctag.re{background:rgba(255,82,82,.1);color:var(--re);border:1px solid rgba(255,82,82,.2);}
.ctag.or{background:rgba(255,145,0,.1);color:var(--or);border:1px solid rgba(255,145,0,.2);}
.ctag.gr{background:var(--gd);color:var(--g);border:1px solid var(--gg);}
.ctag.nt{background:var(--sf3);color:var(--tx3);border:1px solid var(--br2);}
.elink{font-size:8px;color:var(--g);text-decoration:none;}
.elink:hover{text-decoration:underline;}
.noprofile{
  padding:16px 11px;text-align:center;
  border:1px dashed var(--br2);border-radius:var(--r);margin:10px;
}

/* Score breakdown block */
.bdown{padding:8px 11px;}
.bdr{display:flex;align-items:center;gap:5px;margin-bottom:5px;}
.bdl{font-size:8px;color:var(--tx3);width:72px;flex-shrink:0;}
.bdt{flex:1;height:3px;background:var(--sf3);border-radius:2px;overflow:hidden;}
.bdf{height:100%;border-radius:2px;animation:barGrow .8s ease;}
.bdv{font-size:8px;color:var(--tx2);width:22px;text-align:right;flex-shrink:0;}

/* Sector grid */
.sgrid{display:grid;grid-template-columns:1fr 1fr;gap:3px;padding:6px;}
.sgb{
  padding:5px 6px;border-radius:4px;
  border:1px solid var(--br2);background:var(--sf2);
  cursor:pointer;transition:transform .12s;
}
.sgb:hover{transform:scale(1.03);}
.sgb.up{border-color:rgba(0,230,118,.15);background:rgba(0,230,118,.04);}
.sgb.dn{border-color:rgba(255,82,82,.15);background:rgba(255,82,82,.04);}
.sgbn{font-size:7px;color:var(--tx3);margin-bottom:1px;}
.sgbp{font-family:var(--head);font-weight:700;font-size:11px;}
.sgbp.up{color:var(--g);}
.sgbp.dn{color:var(--re);}
.sgbp.fl{color:var(--tx2);}

/* Market pulse block */
.pulse-grid{display:grid;grid-template-columns:1fr 1fr;gap:4px;padding:6px;}
.pm{padding:5px 7px;border-radius:4px;background:var(--sf);border:1px solid var(--br2);}
.pmk{font-size:7px;color:var(--tx3);margin-bottom:2px;}
.pmv{font-family:var(--head);font-weight:700;font-size:12px;}
.pmv.up{color:var(--g);}
.pmv.dn{color:var(--re);}
.pmv.ne{color:var(--tx2);}
</style>
"""

# =============================================================================
# JAVASCRIPT — Clock, Theme, Drawer, Bridge
# =============================================================================
JS = """
<script>
// ── Theme toggle ──
var dark = true;
function toggleTheme() {
  dark = !dark;
  var app = document.getElementById('app');
  var btn = document.getElementById('tbtn');
  if (dark) {
    app.removeAttribute('data-theme');
    btn.textContent = '🌙';
  } else {
    app.setAttribute('data-theme','light');
    btn.textContent = '☀️';
  }
  sessionStorage.setItem('vt', dark ? 'dark' : 'light');
}
(function(){
  if (sessionStorage.getItem('vt') === 'light') {
    dark = false;
    var app = document.getElementById('app');
    if (app) app.setAttribute('data-theme','light');
    var btn = document.getElementById('tbtn');
    if (btn) btn.textContent = '☀️';
  }
})();

// ── Clock ──
function tick() {
  var el = document.getElementById('clock');
  if (!el) return;
  var t = new Date().toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'America/New_York'});
  el.textContent = t + ' EST';
}
setInterval(tick, 1000);
tick();

// ── Intelligence drawer ──
function toggleDrawer() {
  var d = document.getElementById('idrawer');
  var s = document.getElementById('ibarStrip');
  if (d) d.classList.toggle('open');
  if (s) s.classList.toggle('open');
}
function openDrawerTo(event, tab) {
  event.stopPropagation();
  var d = document.getElementById('idrawer');
  var s = document.getElementById('ibarStrip');
  if (d) d.classList.add('open');
  if (s) s.classList.add('open');
  switchDTab(tab, document.getElementById('dtab-' + tab));
}
function switchDTab(tab, el) {
  ['risks','actions','playbook','oracle','scores'].forEach(function(t) {
    var dt = document.getElementById('dtab-' + t);
    var dp = document.getElementById('dpanel-' + t);
    if (dt) dt.classList.remove('active');
    if (dp) dp.classList.remove('active');
  });
  var activeTab = document.getElementById('dtab-' + tab);
  var activePanel = document.getElementById('dpanel-' + tab);
  if (activeTab) activeTab.classList.add('active');
  if (activePanel) activePanel.classList.add('active');
}
function closeDrawer() {
  var d = document.getElementById('idrawer');
  var s = document.getElementById('ibarStrip');
  if (d) d.classList.remove('open');
  if (s) s.classList.remove('open');
}

// ── Fill input from chip click ──
function fc(text) {
  var inp = window.parent.document.querySelector('[data-testid="stTextInput"] input');
  if (!inp) inp = document.getElementById('cin');
  if (inp) {
    var desc = Object.getOwnPropertyDescriptor(window.parent.HTMLInputElement.prototype, 'value')
            || Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
    if (desc && desc.set) desc.set.call(inp, text);
    else inp.value = text;
    inp.dispatchEvent(new Event('input', {bubbles: true}));
    inp.dispatchEvent(new Event('change', {bubbles: true}));
    inp.focus();
  }
  // Also fill visible cin
  var cin = document.getElementById('cin');
  if (cin && cin !== inp) cin.value = text;
}

// ── Send from visible input ──
function send() {
  var cin = document.getElementById('cin');
  var val = cin ? cin.value.trim() : '';
  if (!val) return;

  // Fill Streamlit hidden text input
  var stInput = window.parent.document.querySelector('[data-testid="stTextInput"] input');
  if (stInput) {
    var desc = Object.getOwnPropertyDescriptor(window.parent.HTMLInputElement.prototype, 'value')
            || Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
    if (desc && desc.set) desc.set.call(stInput, val);
    else stInput.value = val;
    stInput.dispatchEvent(new Event('input', {bubbles: true}));
    stInput.dispatchEvent(new Event('change', {bubbles: true}));
  }

  // Click Streamlit submit button
  setTimeout(function() {
    var submitBtn = window.parent.document.querySelector('[data-testid="stFormSubmitButton"] button');
    if (submitBtn) submitBtn.click();
  }, 80);

  // Loading state
  if (cin) { cin.disabled = true; cin.placeholder = 'Routing…'; }
  var sbtn = document.getElementById('sbtn');
  if (sbtn) { sbtn.disabled = true; sbtn.textContent = 'Routing…'; }
}

// ── Enter key in cin ──
document.addEventListener('DOMContentLoaded', function() {
  var cin = document.getElementById('cin');
  if (cin) {
    cin.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') { e.preventDefault(); send(); }
    });
  }
});

// ── Action checkboxes ──
function toggleDAction(card, ckId) {
  card.classList.toggle('done');
  var ck = document.getElementById(ckId);
  if (ck) {
    ck.classList.toggle('done');
    ck.textContent = ck.classList.contains('done') ? '✓' : '';
  }
}

// ── Copy playbook ──
function copyPlaybook() {
  var el = document.getElementById('playbookContent');
  var txt = el ? el.innerText : '';
  if (navigator.clipboard) {
    navigator.clipboard.writeText(txt).then(function() {
      var btn = document.querySelector('.dpb-copy');
      if (btn) {
        btn.textContent = '✓ Copied!';
        setTimeout(function(){ btn.textContent = '📋 Copy playbook'; }, 2000);
      }
    });
  }
}

// ── Auto-scroll chat ──
function scrollChat() {
  var t = document.getElementById('chatThread');
  if (t) t.scrollTop = t.scrollHeight;
}
setTimeout(scrollChat, 300);
</script>
"""


# =============================================================================
# RENDER FUNCTIONS
# =============================================================================

def render_header(statuses, profile):
    agents = [
        ("orchestrator",       "Orchestrator"),
        ("signal_harvester",   "Signal"),
        ("narrative_intel",    "Narrative"),
        ("macro_watchdog",     "Macro"),
        ("competitive_intel",  "Competitive"),
        ("risk_synthesizer",   "Synthesizer"),
        ("market_oracle",      "Oracle"),
        ("strategy_commander", "Commander"),
    ]
    flow_html = ""
    for i, (key, label) in enumerate(agents):
        status = statuses.get(key, "idle")
        dot_cls = {"idle": "", "queued": "", "running": "active",
                   "complete": "done", "error": "err"}.get(status, "")
        node_cls = dot_cls
        flow_html += (
            f'<div class="afn {node_cls}">'
            f'<div class="afd"></div>'
            f'<span>{label}</span>'
            f'</div>'
        )
        if i < len(agents) - 1:
            flow_html += '<span class="afx">›</span>'

    if profile and has_sufficient_profile():
        co = _trunc(profile.get("name", "Profile"), 18)
        prof_html = (
            f'<a class="prof-pill" href="/profile" target="_self">'
            f'<div class="pdot"></div>'
            f'<span>{_html.escape(co)}</span>'
            f'<span style="color:var(--tx3)">· Edit</span>'
            f'</a>'
        )
    else:
        prof_html = (
            '<a class="prof-pill" href="/profile" target="_self" '
            'style="color:var(--tx2)">Set up profile →</a>'
        )

    return f"""
<div class="hdr">
  <a class="logo" href="/landing" target="_self">
    <div class="logo-glyph">⚡</div>
    <span class="logo-name">VIGIL</span>
  </a>
  <div class="vdiv"></div>
  <div class="aflow">{flow_html}</div>
  <div class="hright">
    {prof_html}
    <div class="live-badge"><div class="ldot"></div>LIVE</div>
    <span class="hclock" id="clock">--:-- EST</span>
    <div class="tbtn" id="tbtn" onclick="toggleTheme()">🌙</div>
  </div>
</div>"""


def render_verdict_bar(score, tier, verdict, profile):
    score_str = str(score) if score is not None else "--"
    sc = score_color(score)
    tc = tier_color(tier)
    tier_str = tier or ""
    verdict_html = _html.escape(verdict or "Ask Vigil anything to get your risk score.")
    has_profile = profile and has_sufficient_profile()

    if has_profile:
        name = profile.get("name", "")
        chips = [
            ("MiCA →",     "Go deeper on MiCA compliance timeline"),
            ("Playbook →", "Show me the full 30-day playbook"),
            ("ECB? →",     "What if ECB cuts rates next month?"),
            ("Invest? →",  "Should I buy NASDAQ stocks right now?"),
        ]
    else:
        chips = [
            ("Market check →", "What's the market doing today?"),
            ("Stock analysis →", "Analyze the current stock market"),
            ("Macro pulse →", "Give me a macro economic briefing"),
            ("Advice →", "What should I be watching right now?"),
        ]

    chips_html = "".join(
        f'<div class="vc" onclick="fc(\'{_html.escape(c[1])}\')">{ _html.escape(c[0])}</div>'
        for c in chips
    )

    tier_bg = ""
    tier_bd = ""
    if "ORANGE" in tier_str.upper():
        tier_bg = "background:rgba(255,145,0,.12);"
        tier_bd = "border:1px solid rgba(255,145,0,.3);"
    elif "RED" in tier_str.upper():
        tier_bg = "background:rgba(255,82,82,.12);"
        tier_bd = "border:1px solid rgba(255,82,82,.3);"
    elif "GREEN" in tier_str.upper():
        tier_bg = "background:rgba(0,230,118,.09);"
        tier_bd = "border:1px solid rgba(0,230,118,.25);"
    elif "YELLOW" in tier_str.upper():
        tier_bg = "background:rgba(255,215,64,.1);"
        tier_bd = "border:1px solid rgba(255,215,64,.25);"

    vtext_style = "color:var(--tx2);font-weight:400" if not verdict else ""

    return f"""
<div class="vbar">
  <div class="vscore">
    <div class="vsnum" style="color:{sc}">{score_str}</div>
    <div class="vstier" style="color:{tc};{tier_bg}{tier_bd}">{_html.escape(tier_str)}</div>
    <div class="vsdir"></div>
  </div>
  <div class="vdiv"></div>
  <div class="vtext" style="{vtext_style}">{verdict_html}</div>
  <div class="vdiv"></div>
  <div class="vchips">{chips_html}</div>
</div>"""


def render_ibar(top_risks, top_actions, specialist_outputs, score_breakdown, score, tier):
    if not top_risks and not top_actions:
        return '<div class="ibar" id="ibar"></div>'

    risk_classes = ["rc1", "rc2", "rc3"]
    risk_chips = ""
    for i, r in enumerate(top_risks[:3]):
        cls = risk_classes[i] if i < 3 else "rc3"
        name = _trunc(r.get("name", "Risk"), 24)
        prob = r.get("probability", "")
        meta = f'<span class="chip-meta">{_html.escape(prob)}</span>' if prob else ""
        risk_chips += (
            f'<div class="rchip {cls}" onclick="openDrawerTo(event,\'risks\')">'
            f'<span class="chip-txt">⚠ {_html.escape(name)}</span>{meta}'
            f'</div>'
        )

    action_chips = ""
    for a in top_actions[:3]:
        title = _trunc(a.get("title", "Action"), 24)
        dl = a.get("deadline", "")
        meta = f'<span class="chip-meta">{_html.escape(dl)}</span>' if dl else ""
        action_chips += (
            f'<div class="achip" onclick="openDrawerTo(event,\'actions\')">'
            f'<span class="chip-txt">✓ {_html.escape(title)}</span>{meta}'
            f'</div>'
        )

    strip = f"""
<div class="ibar-strip" id="ibarStrip" onclick="toggleDrawer()">
  <span class="sl">RISKS</span>
  {risk_chips}
  <div class="sdiv"></div>
  <span class="sl">ACTIONS</span>
  {action_chips}
  <div class="ibar-hint">
    <span>Intelligence</span>
    <span class="ibar-caret">▾</span>
  </div>
</div>"""

    drawer = render_idrawer(top_risks, top_actions, specialist_outputs, score_breakdown, score, tier)

    return f'<div class="ibar on" id="ibar">{strip}{drawer}</div>'


def render_idrawer(top_risks, top_actions, specialist_outputs, score_breakdown, score, tier):
    risks_html = render_dtab_risks(top_risks)
    actions_html = render_dtab_actions(top_actions)
    playbook_html = render_dtab_playbook(specialist_outputs, score_breakdown, score)
    oracle_html = render_dtab_oracle(specialist_outputs)
    scores_html = render_dtab_scores(score_breakdown, score, tier)

    return f"""
<div class="idrawer" id="idrawer">
  <div class="dtabs">
    <div class="dtab active" id="dtab-risks" onclick="switchDTab('risks',this)">Risks</div>
    <div class="dtab" id="dtab-actions" onclick="switchDTab('actions',this)">Actions</div>
    <div class="dtab" id="dtab-playbook" onclick="switchDTab('playbook',this)">Playbook</div>
    <div class="dtab" id="dtab-oracle" onclick="switchDTab('oracle',this)">Oracle</div>
    <div class="dtab" id="dtab-scores" onclick="switchDTab('scores',this)">Scores</div>
    <span class="dtab-close" onclick="closeDrawer()">✕</span>
  </div>
  <div class="dbody">
    <div class="dtabpanel active" id="dpanel-risks">{risks_html}</div>
    <div class="dtabpanel" id="dpanel-actions">{actions_html}</div>
    <div class="dtabpanel" id="dpanel-playbook">{playbook_html}</div>
    <div class="dtabpanel" id="dpanel-oracle">{oracle_html}</div>
    <div class="dtabpanel" id="dpanel-scores">{scores_html}</div>
  </div>
</div>"""


def render_dtab_risks(top_risks):
    if not top_risks:
        return '<div style="color:var(--tx3);font-size:9px;padding:20px;text-align:center">Run an analysis to see risk breakdown</div>'

    variant = ["", "r2", "r3"]
    cards = ""
    for i, r in enumerate(top_risks[:3]):
        cls = variant[i] if i < len(variant) else "r3"
        name = _html.escape(r.get("name", f"Risk {i+1}"))
        prob = r.get("probability", "")
        detail = _html.escape(r.get("detail", ""))
        ignored = _html.escape(r.get("action_if_ignored", ""))
        tags_raw = r.get("tags", [])
        prob_num = 0
        m = re.search(r"(\d+)", prob)
        if m:
            prob_num = min(int(m.group(1)), 100)
        tags_html = "".join(
            f'<span class="drc-tag">{_html.escape(str(t))}</span>'
            for t in (tags_raw[:3] if isinstance(tags_raw, list) else [])
        )
        cards += f"""
<div class="drc {cls}">
  <div class="drc-head">
    <span class="drc-name">{name}</span>
    <span class="drc-prob">{_html.escape(prob)}</span>
  </div>
  <div class="drc-bar"><div class="drc-bar-fill" style="width:{prob_num}%"></div></div>
  <div class="drc-detail">{detail}</div>
  {f'<div class="drc-ignored">If ignored: {ignored}</div>' if ignored else ''}
  <div class="drc-tags">{tags_html}</div>
</div>"""

    return f'<div class="drisks-grid">{cards}</div>'


def render_dtab_actions(top_actions):
    if not top_actions:
        return '<div style="color:var(--tx3);font-size:9px;padding:20px;text-align:center">Run an analysis to see action plan</div>'

    cards = ""
    for i, a in enumerate(top_actions[:3]):
        title = _html.escape(a.get("title", f"Action {i+1}"))
        detail = _html.escape(a.get("detail", ""))
        owner = _html.escape(a.get("owner", "Leadership"))
        dl = _html.escape(a.get("deadline", "This week"))
        est = _html.escape(a.get("time_estimate", ""))
        urgency = _html.escape(a.get("urgency", "HIGH"))
        ck_id = f"dac-ck-{i}"
        cards += f"""
<div class="dac" onclick="toggleDAction(this,'{ck_id}')">
  <div class="dac-titlerow">
    <div class="dac-check" id="{ck_id}"></div>
    <span class="dac-title">{title}</span>
  </div>
  <div class="dac-detail">{detail}</div>
  <div class="dac-tags">
    <span class="datag ow">{owner}</span>
    <span class="datag dl">{dl}</span>
    {f'<span class="datag et">{est}</span>' if est else ''}
    <span class="datag ur">{urgency}</span>
  </div>
</div>"""

    return f'<div class="dactions-grid">{cards}</div>'


def render_dtab_playbook(specialist_outputs, score_breakdown, score):
    strat = (specialist_outputs or {}).get("strategy_commander", "")
    if not strat:
        return '<div style="color:var(--tx3);font-size:9px;padding:20px;text-align:center">Run a full briefing to generate the strategy playbook</div>'

    # Sidebar scores
    macro_sc = score_breakdown.get("macro") if score_breakdown else None
    market_sc = score_breakdown.get("market") if score_breakdown else None
    narr_sc = score_breakdown.get("narrative") if score_breakdown else None
    comp_sc = score_breakdown.get("competitive") if score_breakdown else None

    def sc_row(lbl, val):
        v = val or 0
        col = score_color(val)
        return f"""
<div class="dpbs-row">
  <span class="dpbs-lbl2">{lbl}</span>
  <div class="dpbs-track"><div class="dpbs-fill" style="width:{min(v,100)}%;background:{col}"></div></div>
  <span class="dpbs-num">{val if val else '--'}</span>
</div>"""

    composite_col = score_color(score)
    sidebar = f"""
<div class="dpb-sidebar">
  <div class="dpbs-lbl">Vigil Stance</div>
  <div class="dpbs-val">See Playbook</div>
  {sc_row('Macro', macro_sc)}
  {sc_row('Market', market_sc)}
  {sc_row('Narrative', narr_sc)}
  {sc_row('Competitive', comp_sc)}
  <div class="dpbs-composite">
    <div class="dpbs-clbl">Composite</div>
    <div class="dpbs-cval" style="color:{composite_col}">{score if score is not None else '--'}</div>
  </div>
</div>"""

    content = _html.escape(strat[:2000])
    return f"""
<div class="dplaybook-layout">
  <div>
    <button class="dpb-copy" onclick="copyPlaybook()">📋 Copy playbook</button>
    <div class="dpb-content" id="playbookContent">{content}</div>
  </div>
  {sidebar}
</div>"""


def render_dtab_oracle(specialist_outputs):
    oracle_out = (specialist_outputs or {}).get("market_oracle", "")
    if not oracle_out:
        return f"""
<div class="oracle-empty">
  <div class="oracle-empty-title">Market Oracle</div>
  <div class="oracle-empty-sub">Ask an investment question to activate Oracle</div>
  <div class="oracle-echips">
    <span class="oracle-ec" onclick="fc('Should I buy NASDAQ?')">Buy NASDAQ?</span>
    <span class="oracle-ec" onclick="fc('Is gold a buy now?')">Gold buy?</span>
    <span class="oracle-ec" onclick="fc('AAPL outlook')">AAPL outlook</span>
    <span class="oracle-ec" onclick="fc('Crypto timing?')">Crypto timing?</span>
  </div>
</div>"""

    # Parse verdict
    v_match = re.search(r"\*\*Verdict:\*\*\s*(BUY SIGNAL|WAIT|CAUTION|AVOID)[^\n]*", oracle_out, re.IGNORECASE)
    verdict_str = v_match.group(1).upper() if v_match else "CAUTION"
    vcol = {"BUY SIGNAL": "var(--g)", "WAIT": "var(--ye)", "CAUTION": "var(--or)", "AVOID": "var(--re)"}.get(verdict_str, "var(--tx2)")

    conf_match = re.search(r"[Cc]onfidence[:\s]+(\d+)[%]?", oracle_out)
    conf_str = f"Confidence: {conf_match.group(1)}%" if conf_match else "Confidence: --"

    dov = f"""
<div class="dov-box">
  <div class="dov-lbl">Oracle Verdict</div>
  <div class="dov-val" style="color:{vcol}">{_html.escape(verdict_str)}</div>
  <div class="dov-conf">{conf_str}</div>
</div>"""

    bull_m = re.search(r"THE BULL CASE[^\n]*\n([\s\S]+?)(?:\n##|\n---|\Z)", oracle_out, re.IGNORECASE)
    bear_m = re.search(r"THE BEAR CASE[^\n]*\n([\s\S]+?)(?:\n##|\n---|\Z)", oracle_out, re.IGNORECASE)
    hist_m = re.search(r"HISTORICAL PARALLEL[^\n]*\n([\s\S]+?)(?:\n##|\n---|\Z)", oracle_out, re.IGNORECASE)
    take_m = re.search(r"VIGIL.?S TAKE[^\n]*\n([\s\S]+?)(?:\n##|\n---|\Z)", oracle_out, re.IGNORECASE)

    cases = ""
    if bull_m:
        cases += f'<div class="doc bull"><span class="doc-disc">BULL CASE</span>{_html.escape(bull_m.group(1).strip()[:280])}</div>'
    if bear_m:
        cases += f'<div class="doc bear"><span class="doc-disc">BEAR CASE</span>{_html.escape(bear_m.group(1).strip()[:280])}</div>'
    if hist_m:
        cases += f'<div class="doc hist"><span class="doc-disc">HISTORICAL PARALLEL</span>{_html.escape(hist_m.group(1).strip()[:280])}</div>'
    if take_m:
        cases += f'<div class="doc take"><span class="doc-disc">VIGIL\'S TAKE</span>{_html.escape(take_m.group(1).strip()[:280])}</div>'

    if not cases:
        cases = f'<div class="doc take"><span class="doc-disc">ANALYSIS</span>{_html.escape(oracle_out[:400])}</div>'

    return f"""
<div class="doracle-layout">
  {dov}
  <div class="doracle-cases">{cases}</div>
</div>"""


def render_dtab_scores(score_breakdown, score, tier):
    bd = score_breakdown or {}
    weights = [
        ("Macro Watchdog",    35, bd.get("macro") or score),
        ("Market Signals",    25, bd.get("market") or score),
        ("Narrative Intel",   20, bd.get("narrative") or score),
        ("Competitive Intel", 20, bd.get("competitive") or score),
    ]
    rows_html = ""
    for lbl, wt, sc in weights:
        v = sc or 0
        col = score_color(sc)
        rows_html += f"""
<div class="dsc-row">
  <span class="dsc-lbl">{lbl}</span>
  <div class="dsc-track"><div class="dsc-fill" style="width:{min(v,100)}%;background:{col}"></div></div>
  <span class="dsc-wt">{wt}%</span>
  <span class="dsc-val">{sc if sc else '--'}</span>
</div>"""

    formula = "Score = Macro×0.35 + Market×0.25 + Narrative×0.20 + Competitive×0.20"
    composite_col = score_color(score)
    tier_col = tier_color(tier)

    coh_label = "ALIGNED"
    coh_col = "var(--g)"
    if score:
        if score >= 70:
            coh_label = "CONTRADICTORY"
            coh_col = "var(--re)"
        elif score >= 40:
            coh_label = "MIXED"
            coh_col = "var(--ye)"

    return f"""
<div class="dscores-layout">
  <div>
    <div class="dsc-rows">{rows_html}</div>
    <div class="dsc-formula">{formula}</div>
  </div>
  <div class="dsc-right">
    <div class="dsc-big">
      <div class="dsc-big-lbl">COMPOSITE SCORE</div>
      <div class="dsc-big-val" style="color:{composite_col}">{score if score is not None else '--'}</div>
      <div class="dsc-big-tier" style="color:{tier_col}">{_html.escape(tier or '')}</div>
    </div>
    <div class="dsc-coherence">
      <div class="dsc-coh-lbl">Signal coherence</div>
      <span class="dsc-coh-badge" style="background:{coh_col}18;border:1px solid {coh_col}30;color:{coh_col}">{coh_label}</span>
    </div>
  </div>
</div>"""


def render_left_panel(live_data):
    headlines = live_data.get("headlines", [])
    sectors = live_data.get("sectors", {})
    pulse = live_data.get("pulse", {})
    dq = live_data.get("data_quality", "UNKNOWN")
    dq_dot = {"FULL": "sdot-p", "PARTIAL": "sdot-u", "MINIMAL": "sdot-n"}.get(dq, "sdot-n")

    # News feed
    news_items = ""
    for h in headlines[:8]:
        sent = h.get("sentiment", "neutral")
        sdot = "sdot-p" if sent == "positive" else ("sdot-n" if sent == "negative" else "sdot-u")
        src = _html.escape(h.get("source", ""))
        title = _html.escape(_trunc(h.get("title", ""), 90))
        t_ago = _time_ago(h.get("publishedAt", ""))
        news_items += f"""
<div class="ni" onclick="fc('Analyze: {_html.escape(h.get('title','')[:60])}')">
  <div class="ni-src">{src}<span class="{sdot}"></span></div>
  <div class="ni-hl">{title}</div>
  <div class="ni-t">{t_ago}</div>
</div>"""

    if not news_items:
        news_items = '<div style="padding:14px;font-size:9px;color:var(--tx3);text-align:center">No headlines available</div>'

    # Sector mini grid (top2 + bottom2)
    sorted_secs = sorted(sectors.items(), key=lambda x: (x[1].get("pct_7d") or 0), reverse=True) if sectors else []
    display_secs = (sorted_secs[:2] + sorted_secs[-2:]) if len(sorted_secs) >= 4 else sorted_secs[:4]
    sb_html = ""
    for name, data in display_secs:
        pct = data.get("pct_7d")
        pct_str = f"{pct:+.1f}%" if pct is not None else "N/A"
        pcls = "up" if (pct and pct > 0.3) else ("dn" if (pct and pct < -0.3) else "fl")
        short = name[:7]
        sb_html += f"""
<div class="sb {pcls}">
  <div class="sbn">{_html.escape(short)}</div>
  <div class="sbp {pcls}">{pct_str}</div>
</div>"""

    # Regime
    regime = pulse.get("market_regime", "")
    if "OFF" in (regime or "").upper():
        regime_col = "var(--re)"
        regime_bg = "rgba(255,82,82,.08)"
    elif "ON" in (regime or "").upper():
        regime_col = "var(--g)"
        regime_bg = "rgba(0,230,118,.08)"
    else:
        regime_col = "var(--ye)"
        regime_bg = "rgba(255,215,64,.08)"

    regime_html = ""
    if regime:
        regime_html = f"""
<div class="regime-card" style="background:{regime_bg};border-color:{regime_col}30">
  <div class="regime-val" style="color:{regime_col}">{_html.escape(regime)}</div>
  <div class="regime-sub">Market regime</div>
</div>"""

    # Stance card
    strat_status = st.session_state.get("agent_statuses", {}).get("strategy_commander", "idle")
    stance_html = ""
    if strat_status == "complete":
        stance_html = """
<div class="stance-card">
  <div class="stance-lbl">Vigil Stance</div>
  <div class="stance-val">See Playbook →</div>
</div>"""

    # Sector news (right-side news items)
    rni_html = ""
    for h in headlines[8:12]:
        src = _html.escape(h.get("source", ""))
        title = _html.escape(_trunc(h.get("title", ""), 80))
        rni_html += f"""
<div class="rni">
  <div class="rni-src">{src}</div>
  <div class="rni-hl">{title}</div>
</div>"""

    return f"""
<div class="lpanel">
  <div class="lptop">
    <div class="ptitle">📡 Live Feed <span class="{dq_dot}"></span></div>
    {news_items}
  </div>
  <div class="lpbot">
    <div class="ptitle">📊 Sectors</div>
    <div class="smini">{sb_html}</div>
    {regime_html}
    {stance_html}
    <div class="ptitle" style="margin-top:2px">Sector News</div>
    {rni_html}
  </div>
</div>"""


def render_chat_thread(history, profile):
    msgs_html = ""
    if not history:
        if profile and has_sufficient_profile():
            name = _html.escape(profile.get("name", "your company"))
            msgs_html = f"""
<div class="msg sys">
  <div class="mlbl">⚡ Vigil · Auto-brief · {name} profile loaded</div>
  <div class="bubble" style="color:var(--tx2);font-size:11px;">
    Good morning. I've run this morning's analysis for {name}.<br>
    Your risk score is loading... Top risks and actions will appear above after analysis.<br>
    Ask anything below or click a shortcut to go deeper.
  </div>
</div>"""
        else:
            msgs_html = """
<div class="msg sys">
  <div class="mlbl">⚡ Vigil</div>
  <div class="bubble" style="color:var(--tx2);font-size:11px;">
    No company profile set — I'll use generic market analysis.<br>
    <a href="/profile" target="_self" style="color:var(--g)">Set up your profile →</a> for personalized intelligence.<br>
    Ask me anything to get started.
  </div>
</div>"""
    else:
        for msg in history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                # User messages: escape HTML to prevent injection
                escaped = _html.escape(str(content)).replace("\n", "<br>")
                msgs_html += f"""
<div class="msg user">
  <div class="mlbl">You</div>
  <div class="bubble">{escaped}</div>
</div>"""
            elif role == "vigil":
                intent = msg.get("intent_type", "")
                agents = msg.get("agents_used", [])
                agent_label = intent.replace("_", " ").title() if intent else "analysis"
                # Render vigil response as formatted markdown HTML
                formatted = md_to_html(str(content))
                # Build agent cards for specialist outputs
                specialist = st.session_state.get("vigil_specialist_outputs", {})
                acard_html = ""
                for ag in (agents or []):
                    ag_out = specialist.get(ag, "")
                    if ag_out:
                        dot_bg = "var(--pu)" if ag == "market_oracle" else "var(--g)"
                        ag_name = ag.replace("_", " ").title()
                        # Agent card bodies also rendered as markdown
                        acard_body = md_to_html(ag_out[:600])
                        acard_html += f"""
<div class="acard">
  <div class="acard-head">
    <div class="acard-dot" style="background:{dot_bg}"></div>
    <span class="acard-name">{_html.escape(ag_name)}</span>
  </div>
  <div class="acard-body">{acard_body}</div>
</div>"""

                msgs_html += f"""
<div class="msg sys">
  <div class="mlbl">⚡ Vigil · {_html.escape(agent_label)}</div>
  <div class="bubble vigil-md" style="font-size:11px;">{formatted}{acard_html}</div>
</div>"""

    return f'<div class="cthread" id="chatThread">{msgs_html}</div>'


def render_center_panel(live_data, profile):
    history = get_conversation_history()
    has_profile = profile and has_sufficient_profile()
    co_name = profile.get("name", "") if profile else ""

    placeholder = (
        f"Ask Vigil — {_html.escape(co_name)} context active..."
        if has_profile
        else "Ask Vigil anything — macro, stocks, risk analysis..."
    )

    if has_profile:
        qchips = [
            ("Delay Series A?",   "Should we delay our Series A?"),
            ("MiCA impact",       "What is the MiCA impact on our business?"),
            ("ECB scenario",      "ECB cuts rates — what does that mean for us?"),
            ("Hiring stance?",    "Should we be hiring or freezing headcount?"),
            ("Buy gold?",         "Should we buy gold as a hedge right now?"),
            ("FX risk?",          "What is our FX risk exposure?"),
        ]
    else:
        qchips = [
            ("Market check",      "What's the market doing today?"),
            ("Stock analysis",    "Analyze the current stock market"),
            ("Macro pulse",       "Give me a macro economic briefing"),
            ("Business brief",    "Give me a business intelligence briefing"),
            ("Buy NASDAQ?",       "Should I buy NASDAQ stocks right now?"),
            ("Safe havens?",      "What are the best safe haven assets now?"),
        ]

    chips_html = "".join(
        f'<span class="qp" onclick="fc(\'{_html.escape(c[1])}\')">{_html.escape(c[0])}</span>'
        for c in qchips
    )

    thread_html = render_chat_thread(history, profile)

    return f"""
<div class="cpanel">
  {thread_html}
  <div class="cinput-wrap">
    <div class="crow">
      <input class="cin" id="cin" type="text" placeholder="{placeholder}"
             onkeydown="if(event.key==='Enter'){{event.preventDefault();send();}}" />
      <button class="sbtn" id="sbtn" onclick="send()">⚡ Analyze</button>
    </div>
    <div class="qrow">{chips_html}</div>
  </div>
</div>"""


def render_right_panel(live_data, profile):
    sectors = live_data.get("sectors", {})
    pulse = live_data.get("pulse", {})

    # Profile block
    if profile and has_sufficient_profile():
        co = _html.escape(profile.get("name", "Your Company"))
        sec = _html.escape(profile.get("sector", ""))
        ctry = _html.escape(profile.get("country", ""))
        arr = _html.escape(profile.get("arr", ""))
        stage = _html.escape(profile.get("stage", ""))
        sub = " · ".join(x for x in [sec, ctry, arr, stage] if x)

        regs = profile.get("regulations", [])
        tags_html = ""
        if isinstance(regs, list):
            for r in regs[:2]:
                tags_html += f'<span class="ctag re">{_html.escape(str(r))}</span>'
        if stage and ("seed" in stage.lower() or "series" in stage.lower()):
            tags_html += '<span class="ctag or">Raising</span>'
        dec = profile.get("current_decisions", "")
        if dec and "expand" in str(dec).lower():
            tags_html += '<span class="ctag gr">Expanding</span>'

        profile_block = f"""
<div class="rblock">
  <div class="ptitle">🏢 Profile</div>
  <div class="cctx">
    <div class="ccname">{co}</div>
    <div class="ccsub">{sub}</div>
    <div class="cctags">{tags_html}</div>
    <a class="elink" href="/profile" target="_self">Edit profile →</a>
  </div>
</div>"""
    else:
        profile_block = f"""
<div class="rblock">
  <div class="ptitle">🏢 Profile</div>
  <div class="noprofile">
    <div style="font-size:22px;margin-bottom:6px">🏢</div>
    <div style="font-size:10px;color:var(--tx);font-weight:600;margin-bottom:3px">No profile set</div>
    <div style="font-size:8.5px;color:var(--tx3);margin-bottom:8px">Add your company for personalized analysis</div>
    <a class="elink" href="/profile" target="_self">Set up profile →</a>
  </div>
</div>"""

    # Score breakdown
    score = st.session_state.get("vigil_last_risk_score")
    bd = st.session_state.get("vigil_last_score_breakdown", {})
    sc_rows_data = [
        ("Macro ·35%",       bd.get("macro") or score),
        ("Market ·25%",      bd.get("market") or score),
        ("Narrative ·20%",   bd.get("narrative") or score),
        ("Competitive ·20%", bd.get("competitive") or score),
    ]
    bdown_html = ""
    for lbl, sc in sc_rows_data:
        v = min(sc or 0, 100)
        col = score_color(sc)
        bdown_html += f"""
<div class="bdr">
  <span class="bdl">{lbl}</span>
  <div class="bdt"><div class="bdf" style="width:{v}%;background:{col}"></div></div>
  <span class="bdv">{sc if sc else '--'}</span>
</div>"""

    score_block = f"""
<div class="rblock">
  <div class="ptitle">Score Breakdown</div>
  <div class="bdown">{bdown_html}</div>
</div>"""

    # Market Pulse 2x2
    vix = pulse.get("vix")
    dxy = pulse.get("dxy")
    gold = pulse.get("gold")
    sp500 = pulse.get("sp500_change")

    def pm_val(v, prefix=""):
        if v is None: return "var(--tx2)", "--"
        if isinstance(v, float) or isinstance(v, int):
            sign = "+" if float(v) > 0 else ""
            cls = "up" if float(v) > 0 else ("dn" if float(v) < 0 else "ne")
            return cls, f"{prefix}{sign}{v:.2f}"
        return "ne", str(v)

    vix_cls, vix_str = pm_val(vix)
    dxy_cls, dxy_str = pm_val(dxy)
    gold_cls, gold_str = pm_val(gold)
    sp5_cls, sp5_str = pm_val(sp500, "+")

    pulse_block = f"""
<div class="rblock">
  <div class="ptitle">Market Pulse</div>
  <div class="pulse-grid">
    <div class="pm"><div class="pmk">VIX</div><div class="pmv {vix_cls}">{vix_str}</div></div>
    <div class="pm"><div class="pmk">DXY</div><div class="pmv {dxy_cls}">{dxy_str}</div></div>
    <div class="pm"><div class="pmk">Gold</div><div class="pmv {gold_cls}">{gold_str}</div></div>
    <div class="pm"><div class="pmk">S&P 500</div><div class="pmv {sp5_cls}">{sp5_str}</div></div>
  </div>
</div>"""

    # All sectors grid
    sgrid_html = ""
    short_names = {
        "Technology": "Tech", "Healthcare": "Health",
        "Financial Services": "Fin", "Consumer Discretionary": "Cons",
        "Energy": "Energy", "Industrials": "Indust", "Real Estate": "RE",
    }
    for name, data in sectors.items():
        pct = data.get("pct_7d")
        pct_str = f"{pct:+.1f}%" if pct is not None else "N/A"
        pcls = "up" if (pct and pct > 0.3) else ("dn" if (pct and pct < -0.3) else "fl")
        short = short_names.get(name, name[:6])
        bg = "rgba(0,230,118,.04)" if (pct and pct > 0) else "rgba(255,82,82,.04)" if (pct and pct < 0) else "var(--sf2)"
        sgrid_html += f"""
<div class="sgb {pcls}" style="background:{bg}"
     onclick="fc('Analyze risk for {_html.escape(name)} sector')">
  <div class="sgbn">{_html.escape(short)}</div>
  <div class="sgbp {pcls}">{pct_str}</div>
</div>"""

    sectors_block = f"""
<div class="rblock">
  <div class="ptitle">📊 All Sectors (7D)</div>
  <div class="sgrid">{sgrid_html}</div>
</div>""" if sgrid_html else ""

    return f"""
<div class="rpanel">
  <div class="rscroll">
    {profile_block}
    {score_block}
    {pulse_block}
    {sectors_block}
  </div>
</div>"""


# =============================================================================
# SUBMISSION HANDLER
# =============================================================================
def _handle_submission(message):
    st.session_state["pipeline_running"] = True
    add_message("user", message)
    with st.spinner("⚡ Routing to agents…"):
        result = run_pipeline(message)
    st.session_state["vigil_specialist_outputs"] = result.get("specialist_outputs", {})
    st.session_state["pipeline_running"] = False
    # Persist after every agent run so reload restores full state
    try:
        from session_manager import _persist_current_session
        _persist_current_session()
    except Exception:
        pass
    st.rerun()


# =============================================================================
# MAIN
# =============================================================================
def main():
    # 1. Init session state
    init_conversation()

    # 2. Live data
    try:
        live_data = get_all_live_data()
    except Exception:
        live_data = {"headlines": [], "sectors": {}, "pulse": {}, "data_quality": "MINIMAL"}

    profile = load_profile()

    # 3. Auto-load flag
    if (
        should_auto_load()
        and "pending_auto_load" not in st.session_state
        and not get_conversation_history()
    ):
        st.session_state["pending_auto_load"] = True

    # 4. Inject CSS + JS
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(JS, unsafe_allow_html=True)

    # 5. Read state
    statuses = st.session_state.get("agent_statuses", {})
    top_risks = st.session_state.get("vigil_last_top_risks", [])
    top_actions = st.session_state.get("vigil_last_top_actions", [])
    specialist_outputs = st.session_state.get("vigil_specialist_outputs", {})
    score_breakdown = st.session_state.get("vigil_last_score_breakdown", {})
    score = st.session_state.get("vigil_last_risk_score")
    tier = st.session_state.get("vigil_last_risk_tier")
    verdict = st.session_state.get("vigil_last_verdict")

    # 6. Build complete HTML
    hdr = render_header(statuses, profile)
    vbar = render_verdict_bar(score, tier, verdict, profile)
    ibar = render_ibar(top_risks, top_actions, specialist_outputs, score_breakdown, score, tier)
    left = render_left_panel(live_data)
    center = render_center_panel(live_data, profile)
    right = render_right_panel(live_data, profile)

    full_html = f"""
<div class="app" id="app">
  {hdr}
  {vbar}
  {ibar}
  <div class="mbody">
    {left}
    {center}
    {right}
  </div>
</div>"""

    st.markdown(full_html, unsafe_allow_html=True)

    # 7. Hidden Streamlit form (wired via JS bridge)
    with st.container():
        st.markdown('<div class="vigil-hidden-form">', unsafe_allow_html=True)
        with st.form("chat_form", clear_on_submit=True):
            msg_input = st.text_input("", key="chat_input", label_visibility="collapsed")
            submitted = st.form_submit_button("Send")
        st.markdown('</div>', unsafe_allow_html=True)

    if submitted and msg_input and msg_input.strip():
        _handle_submission(msg_input.strip())

    # 8. Auto-load execution
    if st.session_state.pop("pending_auto_load", False):
        auto_prompt = get_auto_load_prompt(profile)
        with st.spinner(f"⚡ Vigil loading briefing for {profile.get('name', 'your company')}…"):
            result = run_pipeline(auto_prompt)
        st.session_state["vigil_specialist_outputs"] = result.get("specialist_outputs", {})
        mark_auto_loaded()
        st.rerun()


if __name__ == "__main__":
    main()
