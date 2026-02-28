"""
pages/profile.py — Vigil Company Profile Page
Pixel-perfect match to vigil-profile.html reference.
Full HTML/CSS/JS rendered via st.components.v1.html.
"""

import os
import sys
import json
import html as _html
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from session_manager import (
    init_conversation,
    save_profile,
    load_profile,
    has_sufficient_profile,
)


# ─── Hide ALL Streamlit chrome ────────────────────────────────────────────────
st.markdown(
    """
<style>
#MainMenu,footer,header,
[data-testid="stToolbar"],
[data-testid="stStatusWidget"],
[data-testid="stDecoration"],
[data-testid="stHeader"],
[data-testid="stAppViewContainer"] > section:first-child,
.stDeployButton { display:none !important; }
html,body,.stApp,[data-testid="stAppViewContainer"] {
  background:#070809 !important;
  margin:0 !important; padding:0 !important;
}
.block-container,[data-testid="stAppViewBlockContainer"] {
  padding:0 !important; max-width:100% !important;
  margin:0 !important;
}
</style>
""",
    unsafe_allow_html=True,
)


# =============================================================================
# PRE-FILL JAVASCRIPT BUILDER
# =============================================================================
def build_prefill_js(profile_dict: dict) -> str:
    if not profile_dict:
        return ""
    p = json.dumps(profile_dict)
    return f"""
<script>
(function() {{
  var p = {p};
  function sv(id, v) {{
    var el = document.getElementById(id);
    if (el && v !== undefined && v !== null) el.value = v;
  }}
  sv('company_name', p.name || p.company_name || '');
  sv('website', p.website || '');
  sv('description', p.description || '');
  sv('sector', p.sector || '');
  sv('sub_sector', p.sub_sector || '');
  sv('primary_market', p.primary_market || 'EU');
  sv('country', p.country || '');
  sv('operating_countries', p.operating_countries || '');
  sv('arr', p.arr_range || p.arr || 'Pre-revenue');
  sv('stage', p.funding_stage || p.stage || 'Bootstrapped');
  sv('runway', p.runway || '12-18 months');
  sv('team_size', p.team_size || '1-5');
  sv('currency', p.revenue_currency || p.currency || 'EUR');
  sv('risk_tolerance', p.risk_tolerance || '3');
  sv('current_decisions', p.current_decisions || '');
  sv('comp_threat', p.comp_threat || p.primary_competitive_threat || '');
  sv('constraint', p.constraint || p.biggest_constraint || '');

  // Pre-select risk chips
  var areas = p.risk_areas || p.risk_exposure_areas || [];
  if (areas.length) {{
    document.querySelectorAll('#riskChips .chip-opt').forEach(function(c) {{
      if (areas.indexOf(c.textContent.trim()) >= 0) c.classList.add('sel');
    }});
  }}

  // Pre-select regulation chips
  var regs = p.regulations || p.active_regulations || [];
  if (regs.length) {{
    document.querySelectorAll('#regChips .chip-opt').forEach(function(c) {{
      if (regs.indexOf(c.textContent.trim()) >= 0) {{
        c.classList.add('sel');
        c.classList.add('sel-reg');
      }}
    }});
  }}

  // Update tolerance slider visual
  var rt = document.getElementById('risk_tolerance');
  if (rt) {{
    rt.style.setProperty('--val', ((parseInt(rt.value)-1)/4*100) + '%');
    var labels = ['Very Conservative','Conservative','Moderate','Growth-Oriented','Aggressive'];
    document.getElementById('tolLabel').textContent = labels[parseInt(rt.value)-1];
  }}

  // Update save button for edit mode
  if (p.name || p.company_name) {{
    var btn = document.querySelector('.save-btn');
    if (btn) btn.textContent = '⚡ Update Profile & Re-run Briefing';
  }}

  // Trigger preview update
  setTimeout(updatePreview, 100);
}})();
</script>
"""


# =============================================================================
# MAIN PAGE
# =============================================================================
def main() -> None:
    init_conversation()
    profile = load_profile()

    prefill_js = build_prefill_js(profile or {})

    # -------------------------------------------------------------------------
    # Full page HTML
    # -------------------------------------------------------------------------
    html_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vigil — Company Profile</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Cabinet+Grotesk:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
/* ── Design tokens ── */
:root{{
  --bg:#070809;--bg2:#0b0d10;--sf:#101316;--sf2:#161b21;--sf3:#1c2229;
  --br:#1c2229;--br2:#252d38;
  --g:#00e676;--gd:rgba(0,230,118,.09);--gg:rgba(0,230,118,.2);
  --or:#ff9100;--re:#ff5252;--ye:#ffd740;--bl:#448aff;
  --tx:#dde3ea;--tx2:#6b7787;--tx3:#2e3844;
  --mono:'DM Mono',monospace;--head:'Cabinet Grotesk',sans-serif;
}}
[data-theme=light]{{
  --bg:#f0f2f5;--bg2:#e8eaed;--sf:#ffffff;--sf2:#f5f7fa;--sf3:#ebedf0;
  --br:#e2e5ea;--br2:#d0d4db;
  --tx:#0d1117;--tx2:#5a6272;--tx3:#9ba3af;
}}

/* ── Reset & base ── */
*{{box-sizing:border-box;margin:0;padding:0;}}
html,body{{
  background:var(--bg);color:var(--tx);font-family:var(--mono);
  font-size:13px;line-height:1.5;min-height:100vh;
}}
::-webkit-scrollbar{{width:4px;height:4px;}}
::-webkit-scrollbar-track{{background:var(--bg);}}
::-webkit-scrollbar-thumb{{background:var(--br2);border-radius:2px;}}
a{{color:inherit;text-decoration:none;}}

/* ── Header ── */
.hdr{{
  height:48px;background:var(--sf);border-bottom:1px solid var(--br);
  display:flex;align-items:center;padding:0 20px;gap:12px;
  position:sticky;top:0;z-index:200;
}}
.logo{{display:flex;align-items:center;gap:7px;}}
.logo-glyph{{
  width:26px;height:26px;border:1.5px solid var(--g);border-radius:6px;
  display:flex;align-items:center;justify-content:center;font-size:12px;
}}
.logo-name{{
  font-family:var(--mono);font-size:14px;font-weight:500;
  color:var(--g);letter-spacing:.2em;
}}
.hdr-right{{margin-left:auto;display:flex;align-items:center;gap:10px;}}
.back-btn{{
  font-family:var(--mono);font-size:9px;color:var(--tx2);text-decoration:none;
  display:flex;align-items:center;gap:5px;padding:5px 11px;
  background:var(--sf2);border:1px solid var(--br2);border-radius:6px;transition:all .2s;
}}
.back-btn:hover{{border-color:var(--g);color:var(--g);}}
.tbtn{{
  background:var(--sf2);border:1px solid var(--br2);border-radius:6px;
  padding:5px 8px;font-size:13px;cursor:pointer;color:var(--tx2);
  transition:all .2s;line-height:1;
}}
.tbtn:hover{{border-color:var(--g);color:var(--g);}}

/* ── Page wrapper ── */
.page{{
  max-width:1100px;margin:0 auto;padding:32px 24px;
  display:grid;grid-template-columns:1fr 320px;gap:28px;
}}
@media(max-width:900px){{.page{{grid-template-columns:1fr;}}}}

/* ── Eyebrow / title / sub ── */
.eyebrow{{
  font-family:var(--mono);font-size:9px;letter-spacing:.2em;
  color:var(--g);text-transform:uppercase;margin-bottom:8px;
}}
.page-title{{
  font-family:var(--head);font-size:30px;font-weight:800;
  color:var(--tx);line-height:1.2;margin-bottom:8px;
}}
.page-sub{{font-size:12px;color:var(--tx2);line-height:1.6;margin-bottom:24px;}}

/* ── Before/After card ── */
.ba-card{{
  background:var(--sf);border:1px solid var(--br2);border-radius:10px;
  overflow:hidden;margin-bottom:24px;
}}
.ba-label{{
  font-family:var(--mono);font-size:8px;letter-spacing:.15em;
  text-transform:uppercase;padding:6px 14px 0;color:var(--tx3);
}}
.ba-row{{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--br);}}
.ba-side{{background:var(--sf);padding:12px 14px;}}
.ba-side-label{{
  font-family:var(--mono);font-size:8px;color:var(--tx3);
  margin-bottom:5px;text-transform:uppercase;letter-spacing:.1em;
}}
.ba-side.before .ba-text{{font-size:10.5px;color:var(--tx3);line-height:1.5;}}
.ba-side.after{{background:var(--gd);}}
.ba-side.after .ba-side-label{{color:var(--g);}}
.ba-side.after .ba-text{{font-size:10.5px;color:var(--tx);line-height:1.5;}}
.ba-side.after .ba-text em{{color:var(--or);font-style:normal;font-weight:600;}}

/* ── Completeness bar ── */
.comp-bar-wrap{{
  background:var(--sf);border:1px solid var(--br2);border-radius:10px;
  padding:14px 16px;margin-bottom:24px;
}}
.comp-bar-header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;}}
.comp-bar-title{{font-family:var(--mono);font-size:9px;letter-spacing:.15em;color:var(--tx3);text-transform:uppercase;}}
.comp-pct{{font-family:var(--head);font-size:16px;font-weight:800;transition:color .4s;}}
.comp-track{{height:6px;background:var(--sf3);border-radius:3px;overflow:hidden;margin-bottom:6px;}}
.comp-fill{{height:100%;border-radius:3px;transition:width .4s ease,background .4s ease;width:0%;background:var(--re);}}
.comp-label{{font-family:var(--mono);font-size:9px;color:var(--tx3);}}

/* ── Sections ── */
.section{{
  background:var(--sf);border:1px solid var(--br2);border-radius:10px;
  padding:20px;margin-bottom:16px;
}}
.section-title{{
  font-family:var(--mono);font-size:9px;letter-spacing:.18em;color:var(--g);
  text-transform:uppercase;margin-bottom:16px;display:flex;align-items:center;gap:8px;
}}
.section-title::after{{content:'';flex:1;height:1px;background:var(--br2);}}

/* ── Form rows ── */
.frow{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px;}}
.frow.full{{grid-template-columns:1fr;}}
.frow.three{{grid-template-columns:1fr 1fr 1fr;}}
.fgroup{{display:flex;flex-direction:column;}}
.flabel{{
  font-family:var(--mono);font-size:9px;color:var(--tx3);
  letter-spacing:.08em;text-transform:uppercase;margin-bottom:4px;
}}
.flabel .req{{color:var(--re);margin-left:2px;}}
.fhelper{{font-size:9px;color:var(--tx3);line-height:1.4;margin-top:2px;}}

/* ── Form controls ── */
input[type=text],input[type=url],textarea,select{{
  width:100%;background:var(--sf2);border:1px solid var(--br2);
  border-radius:7px;color:var(--tx);font-family:var(--mono);
  font-size:11px;padding:8px 10px;outline:none;
  transition:border-color .2s,box-shadow .2s;
  -webkit-appearance:none;appearance:none;
}}
textarea{{resize:vertical;min-height:80px;}}
select{{
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath fill='%236b7787' d='M0 0l5 6 5-6z'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 10px center;
  padding-right:28px;cursor:pointer;
}}
input[type=text]:focus,input[type=url]:focus,textarea:focus,select:focus{{
  border-color:var(--g);box-shadow:0 0 0 3px var(--gd);
}}
input.error,textarea.error{{border-color:var(--re)!important;box-shadow:0 0 0 3px rgba(255,82,82,.09)!important;}}
::placeholder{{color:var(--tx3);}}

/* ── Chip groups ── */
.chip-group{{display:flex;flex-wrap:wrap;gap:6px;margin-top:4px;}}
.chip-opt{{
  font-family:var(--mono);font-size:9px;padding:4px 10px;
  border:1px solid var(--br2);border-radius:20px;cursor:pointer;
  color:var(--tx2);background:var(--sf2);transition:all .15s;
  user-select:none;-webkit-user-select:none;
}}
.chip-opt:hover{{border-color:var(--tx2);color:var(--tx);}}
.chip-opt.sel{{
  background:var(--gd);border-color:var(--gg);color:var(--g);
}}
.chip-opt.sel-reg{{
  background:rgba(255,145,0,.08);border-color:rgba(255,145,0,.25);color:var(--or);
}}

/* ── Range slider ── */
input[type=range]{{
  -webkit-appearance:none;appearance:none;
  width:100%;height:4px;border-radius:2px;outline:none;
  border:none;padding:0;
  background:linear-gradient(to right, var(--g) 0%, var(--g) var(--val,50%), var(--sf3) var(--val,50%), var(--sf3) 100%);
  cursor:pointer;
}}
input[type=range]::-webkit-slider-thumb{{
  -webkit-appearance:none;width:16px;height:16px;border-radius:50%;
  background:var(--g);border:2px solid var(--sf);
  box-shadow:0 0 6px var(--gg);cursor:pointer;
}}
input[type=range]::-moz-range-thumb{{
  width:16px;height:16px;border-radius:50%;
  background:var(--g);border:2px solid var(--sf);
  box-shadow:0 0 6px var(--gg);cursor:pointer;
}}
.tolerance-labels{{
  display:flex;justify-content:space-between;
  font-family:var(--mono);font-size:8px;color:var(--tx3);margin-top:4px;
}}
.tolerance-current{{
  background:var(--gd);border:1px solid var(--gg);border-radius:6px;
  padding:5px 12px;font-family:var(--head);font-size:13px;font-weight:700;
  color:var(--g);text-align:center;margin-top:8px;display:inline-block;
}}

/* ── Save button + skip ── */
.save-btn{{
  width:100%;padding:14px;background:var(--g);
  color:#000;border:none;border-radius:8px;
  font-family:var(--mono);font-size:12px;font-weight:700;
  cursor:pointer;letter-spacing:.05em;transition:all .2s;
  margin-top:8px;
}}
.save-btn:hover{{background:#00ff88;box-shadow:0 0 24px var(--gg);}}
.skip-link{{
  display:block;text-align:center;margin-top:10px;
  font-family:var(--mono);font-size:9px;color:var(--tx3);
  cursor:pointer;padding:6px;border-radius:6px;
  border:1px dashed var(--br2);transition:all .2s;
}}
.skip-link:hover{{color:var(--tx2);border-color:var(--tx3);}}

/* ── Error messages ── */
.error-msg{{
  font-family:var(--mono);font-size:9px;color:var(--re);
  margin-top:3px;display:none;
}}
.error-msg.show{{display:block;}}

/* ── Toast ── */
.toast{{
  position:fixed;bottom:24px;left:50%;transform:translateX(-50%) translateY(60px);
  background:var(--sf);border:1px solid var(--gg);border-radius:8px;
  padding:10px 20px;font-family:var(--mono);font-size:11px;color:var(--g);
  z-index:9999;transition:transform .3s ease,opacity .3s ease;opacity:0;
  pointer-events:none;white-space:nowrap;
}}
.toast.show{{transform:translateX(-50%) translateY(0);opacity:1;}}

/* ── Preview column ── */
.preview-col{{position:sticky;top:64px;align-self:start;}}
.preview-card{{
  background:var(--sf);border:1px solid var(--br2);border-radius:10px;
  overflow:hidden;
}}
.preview-header{{
  padding:12px 14px;border-bottom:1px solid var(--br);
  display:flex;align-items:center;justify-content:space-between;
}}
.preview-title{{font-family:var(--mono);font-size:9px;letter-spacing:.15em;color:var(--g);text-transform:uppercase;}}
.preview-badge{{
  font-family:var(--mono);font-size:8px;
  background:rgba(255,82,82,.06);border:1px solid rgba(255,82,82,.15);
  border-radius:3px;padding:2px 7px;color:var(--re);transition:all .3s;
}}
.preview-body{{padding:14px;min-height:80px;}}
.pv-name{{font-family:var(--head);font-size:15px;font-weight:800;color:var(--tx);margin-bottom:3px;}}
.pv-sub{{font-size:9px;color:var(--tx3);margin-bottom:10px;}}
.pv-tags{{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:12px;}}
.pv-tag{{font-size:8px;border-radius:3px;padding:2px 7px;border:1px solid;}}
.pv-tag.re{{background:rgba(255,82,82,.08);border-color:rgba(255,82,82,.2);color:var(--re);}}
.pv-tag.or{{background:rgba(255,145,0,.08);border-color:rgba(255,145,0,.2);color:var(--or);}}
.pv-tag.gr{{background:var(--gd);border-color:rgba(0,230,118,.2);color:var(--g);}}
.pv-tag.nt{{background:var(--sf2);border-color:var(--br2);color:var(--tx3);}}
.pv-verdict{{
  background:var(--sf2);border:1px solid var(--br2);
  border-left:3px solid var(--or);border-radius:0 6px 6px 0;
  padding:9px 11px;font-size:10.5px;color:var(--tx2);line-height:1.6;margin-bottom:10px;
}}
.pv-verdict em{{color:var(--or);font-style:normal;font-weight:600;}}
.pv-empty{{text-align:center;padding:20px;color:var(--tx3);font-size:10px;line-height:1.7;}}
.pv-completeness{{border-top:1px solid var(--br);padding:10px 14px;}}
.pvc-row{{display:flex;align-items:center;justify-content:space-between;margin-bottom:5px;}}
.pvc-label{{font-family:var(--mono);font-size:8px;color:var(--tx3);letter-spacing:.1em;}}
.pvc-pct{{font-family:var(--head);font-size:14px;font-weight:800;transition:color .3s;}}
.pvc-track{{height:3px;background:var(--sf3);border-radius:2px;overflow:hidden;margin-bottom:4px;}}
.pvc-fill{{height:100%;border-radius:2px;transition:width .4s ease,background .4s ease;width:0%;}}
.pvc-quality{{font-family:var(--mono);font-size:8px;color:var(--tx3);}}
</style>
</head>
<body id="profBody">

<!-- ── Header ── -->
<header class="hdr">
  <a class="logo" href="/landing">
    <div class="logo-glyph">⚡</div>
    <div class="logo-name">VIGIL</div>
  </a>
  <div class="hdr-right">
    <a class="back-btn" href="/">← Back to Dashboard</a>
    <button class="tbtn" id="tbtn" onclick="toggleTheme()">🌙</button>
  </div>
</header>

<!-- ── Page grid ── -->
<div class="page">

  <!-- ════════════════════════════════════════════════════
       LEFT — Form column
  ════════════════════════════════════════════════════ -->
  <div class="form-col">

    <div class="eyebrow">Company Intelligence Profile</div>
    <h1 class="page-title">Tell Vigil about your business.</h1>
    <p class="page-sub">No account needed. Data lives in your browser session only.<br>
    More detail = more specific risk intelligence from all 8 agents.</p>

    <!-- Before / After card -->
    <div class="ba-card">
      <div class="ba-label">The difference a profile makes</div>
      <div class="ba-row">
        <div class="ba-side before">
          <div class="ba-side-label">Without profile</div>
          <div class="ba-text">"Fintech companies face regulatory risk from macro conditions."</div>
        </div>
        <div class="ba-side after">
          <div class="ba-side-label">With profile ⚡</div>
          <div class="ba-text">"AlfaTrader AI has <em>68% exposure to MiCA Art.63 enforcement</em>
          in Cyprus — compliance filing needed <em>by Thursday</em> to avoid Q3 risk."</div>
        </div>
      </div>
    </div>

    <!-- Completeness bar -->
    <div class="comp-bar-wrap">
      <div class="comp-bar-header">
        <span class="comp-bar-title">Profile Completeness</span>
        <span class="comp-pct" id="compPct" style="color:var(--re)">0%</span>
      </div>
      <div class="comp-track"><div class="comp-fill" id="compFill"></div></div>
      <div class="comp-label" id="compLabel">Basic — generic analysis only</div>
    </div>

    <!-- ── Section 1: Company Basics ── -->
    <div class="section">
      <div class="section-title">01 · Company Basics</div>

      <div class="frow">
        <div class="fgroup">
          <label class="flabel">Company Name <span class="req">*</span></label>
          <input type="text" id="company_name" placeholder="e.g. AlfaTrader AI"
                 oninput="updatePreview()">
          <div class="error-msg" id="err_name">Company name is required.</div>
        </div>
        <div class="fgroup">
          <label class="flabel">Website</label>
          <input type="url" id="website" placeholder="https://"
                 oninput="updatePreview()">
        </div>
      </div>

      <div class="frow full">
        <div class="fgroup">
          <label class="flabel">What does your company do? <span class="req">*</span></label>
          <div class="fhelper">Write this as you'd explain it to an investor. More detail = more specific risk analysis.</div>
          <textarea id="description" rows="4"
                    placeholder="We build AI-powered algorithmic trading tools for retail and institutional clients in the EU..."
                    oninput="updatePreview()"></textarea>
          <div class="error-msg" id="err_desc">Company description is required.</div>
        </div>
      </div>

      <div class="frow">
        <div class="fgroup">
          <label class="flabel">Sector <span class="req">*</span></label>
          <select id="sector" onchange="updatePreview()">
            <option value="">Select sector…</option>
            <option>Financial Services</option>
            <option>Technology / AI</option>
            <option>Fintech</option>
            <option>SaaS</option>
            <option>Consumer Tech</option>
            <option>Healthcare Tech</option>
            <option>E-commerce</option>
            <option>Manufacturing</option>
            <option>Real Estate</option>
            <option>Energy</option>
            <option>Other</option>
          </select>
        </div>
        <div class="fgroup">
          <label class="flabel">Sub-sector / Niche</label>
          <input type="text" id="sub_sector" placeholder="e.g. AI Trading, DevTools, RegTech"
                 oninput="updatePreview()">
        </div>
      </div>

      <div class="frow three">
        <div class="fgroup">
          <label class="flabel">Primary Market</label>
          <select id="primary_market" onchange="updatePreview()">
            <option>EU</option>
            <option>USA</option>
            <option>UK</option>
            <option>Middle East</option>
            <option>Asia Pacific</option>
            <option>Global</option>
          </select>
        </div>
        <div class="fgroup">
          <label class="flabel">Country <span class="req">*</span></label>
          <input type="text" id="country" placeholder="e.g. Cyprus, Germany, USA"
                 oninput="updatePreview()">
        </div>
        <div class="fgroup">
          <label class="flabel">Operating In</label>
          <input type="text" id="operating_countries" placeholder="EU, UAE, …"
                 oninput="updatePreview()">
        </div>
      </div>
    </div><!-- /section 1 -->

    <!-- ── Section 2: Financial Snapshot ── -->
    <div class="section">
      <div class="section-title">02 · Financial Snapshot</div>

      <div class="frow">
        <div class="fgroup">
          <label class="flabel">ARR Range</label>
          <select id="arr" onchange="updatePreview()">
            <option>Pre-revenue</option>
            <option>&lt; €500K</option>
            <option>€500K – €1M</option>
            <option>€1M – €5M</option>
            <option>€5M – €20M</option>
            <option>€20M – €100M</option>
            <option>€100M+</option>
          </select>
        </div>
        <div class="fgroup">
          <label class="flabel">Funding Stage</label>
          <select id="stage" onchange="updatePreview()">
            <option>Bootstrapped</option>
            <option>Pre-seed</option>
            <option>Seed</option>
            <option>Series A</option>
            <option>Series B</option>
            <option>Series C+</option>
            <option>Public</option>
            <option>Profitable</option>
          </select>
        </div>
      </div>

      <div class="frow three">
        <div class="fgroup">
          <label class="flabel">Runway</label>
          <select id="runway" onchange="updatePreview()">
            <option value="">Select…</option>
            <option>&lt; 6 months</option>
            <option>6–12 months</option>
            <option>12-18 months</option>
            <option>18–24 months</option>
            <option>24+ months</option>
            <option>Profitable</option>
          </select>
        </div>
        <div class="fgroup">
          <label class="flabel">Team Size</label>
          <select id="team_size" onchange="updatePreview()">
            <option>1-5</option>
            <option>6–15</option>
            <option>16–30</option>
            <option>31–100</option>
            <option>100–500</option>
            <option>500+</option>
          </select>
        </div>
        <div class="fgroup">
          <label class="flabel">Revenue Currency</label>
          <select id="currency" onchange="updatePreview()">
            <option>EUR</option>
            <option>USD</option>
            <option>GBP</option>
            <option>Multi-currency</option>
            <option>Crypto</option>
          </select>
        </div>
      </div>
    </div><!-- /section 2 -->

    <!-- ── Section 3: Risk Exposure Areas ── -->
    <div class="section">
      <div class="section-title">03 · Risk Exposure Areas</div>

      <div class="fgroup" style="margin-bottom:16px;">
        <label class="flabel">Key Risk Exposures <span style="font-family:var(--mono);font-size:8px;color:var(--tx3);font-weight:400;text-transform:none;letter-spacing:0;">— select all that apply</span></label>
        <div class="chip-group" id="riskChips">
          <div class="chip-opt" onclick="toggleChip(this,'risk')">Regulatory / Legal</div>
          <div class="chip-opt" onclick="toggleChip(this,'risk')">Interest Rates</div>
          <div class="chip-opt" onclick="toggleChip(this,'risk')">Funding Market</div>
          <div class="chip-opt" onclick="toggleChip(this,'risk')">Supply Chain</div>
          <div class="chip-opt" onclick="toggleChip(this,'risk')">AI / Tech Sector</div>
          <div class="chip-opt" onclick="toggleChip(this,'risk')">Geopolitical</div>
          <div class="chip-opt" onclick="toggleChip(this,'risk')">Currency / FX</div>
          <div class="chip-opt" onclick="toggleChip(this,'risk')">Cyber / Data</div>
          <div class="chip-opt" onclick="toggleChip(this,'risk')">Labor Market</div>
          <div class="chip-opt" onclick="toggleChip(this,'risk')">Consumer Spending</div>
          <div class="chip-opt" onclick="toggleChip(this,'risk')">Credit Markets</div>
          <div class="chip-opt" onclick="toggleChip(this,'risk')">Commodity Prices</div>
        </div>
      </div>

      <div class="fgroup" style="margin-bottom:16px;">
        <label class="flabel">Active Regulations <span style="font-family:var(--mono);font-size:8px;color:var(--tx3);font-weight:400;text-transform:none;letter-spacing:0;">— select all that apply</span></label>
        <div class="chip-group" id="regChips">
          <div class="chip-opt" onclick="toggleChip(this,'reg')">MiCA</div>
          <div class="chip-opt" onclick="toggleChip(this,'reg')">MiFID II</div>
          <div class="chip-opt" onclick="toggleChip(this,'reg')">GDPR</div>
          <div class="chip-opt" onclick="toggleChip(this,'reg')">EU AI Act</div>
          <div class="chip-opt" onclick="toggleChip(this,'reg')">SOC 2</div>
          <div class="chip-opt" onclick="toggleChip(this,'reg')">HIPAA</div>
          <div class="chip-opt" onclick="toggleChip(this,'reg')">SEC</div>
          <div class="chip-opt" onclick="toggleChip(this,'reg')">DORA</div>
          <div class="chip-opt" onclick="toggleChip(this,'reg')">PSD2</div>
          <div class="chip-opt" onclick="toggleChip(this,'reg')">ESMA</div>
        </div>
      </div>

      <div class="fgroup">
        <label class="flabel">Risk Tolerance</label>
        <input type="range" id="risk_tolerance" min="1" max="5" value="3"
               style="--val:50%"
               oninput="updateTolerance(this)">
        <div class="tolerance-labels">
          <span>Very Conservative</span>
          <span>Moderate</span>
          <span>Aggressive</span>
        </div>
        <div><span class="tolerance-current" id="tolLabel">Moderate</span></div>
      </div>
    </div><!-- /section 3 -->

    <!-- ── Section 4: Strategic Context ── -->
    <div class="section">
      <div class="section-title">04 · Strategic Context</div>

      <div class="frow full" style="margin-bottom:14px;">
        <div class="fgroup">
          <label class="flabel">Active Decisions &amp; Priorities</label>
          <div class="fhelper">The more specific you are, the more actionable Vigil's playbook will be.</div>
          <textarea id="current_decisions" rows="3"
                    placeholder="E.g. deciding whether to raise Series A in Q2, evaluating UAE expansion, considering 5 new hires, assessing MiCA compliance timeline…"
                    oninput="updatePreview()"></textarea>
        </div>
      </div>

      <div class="frow">
        <div class="fgroup">
          <label class="flabel">Primary Competitive Threat</label>
          <select id="comp_threat" onchange="updatePreview()">
            <option value="">Select…</option>
            <option>Incumbents / big banks</option>
            <option>Other startups</option>
            <option>Big Tech entering space</option>
            <option>Regulatory change</option>
            <option>Market consolidation</option>
            <option>Other</option>
          </select>
        </div>
        <div class="fgroup">
          <label class="flabel">Biggest Constraint Right Now</label>
          <select id="constraint" onchange="updatePreview()">
            <option value="">Select…</option>
            <option>Cash / runway</option>
            <option>Regulatory approval</option>
            <option>Hiring talent</option>
            <option>Product-market fit</option>
            <option>Sales / distribution</option>
            <option>International expansion</option>
            <option>Other</option>
          </select>
        </div>
      </div>
    </div><!-- /section 4 -->

    <!-- Save + Skip -->
    <button class="save-btn" onclick="saveProfile()">⚡ Activate Profile &amp; Open Dashboard →</button>
    <div class="skip-link" onclick="skipProfile()">Skip — use generic analysis →</div>

  </div><!-- /form-col -->

  <!-- ════════════════════════════════════════════════════
       RIGHT — Preview column (sticky)
  ════════════════════════════════════════════════════ -->
  <div class="preview-col">
    <div class="preview-card">
      <div class="preview-header">
        <span class="preview-title">Live Preview</span>
        <span class="preview-badge" id="previewBadge">Incomplete</span>
      </div>
      <div class="preview-body" id="previewBody">
        <div class="pv-empty">Start filling in your company details to see how Vigil will read your business.</div>
      </div>
      <div class="pv-completeness">
        <div class="pvc-row">
          <span class="pvc-label">Completeness</span>
          <span class="pvc-pct" id="pvPct" style="color:var(--re)">0%</span>
        </div>
        <div class="pvc-track"><div class="pvc-fill" id="pvFill"></div></div>
        <div class="pvc-quality" id="pvQuality">Basic — generic analysis only</div>
      </div>
    </div>
  </div><!-- /preview-col -->

</div><!-- /page -->

<!-- Toast notification -->
<div class="toast" id="toast"></div>

<!-- ══════════════════════════════════════════════════════
     JAVASCRIPT
══════════════════════════════════════════════════════ -->
<script>
const TOLERANCE_LABELS = ['Very Conservative','Conservative','Moderate','Growth-Oriented','Aggressive'];

function updateTolerance(el) {{
  const v = parseInt(el.value);
  el.style.setProperty('--val', ((v-1)/4*100) + '%');
  document.getElementById('tolLabel').textContent = TOLERANCE_LABELS[v-1];
  updatePreview();
}}

function toggleChip(el, type) {{
  if (type === 'risk') {{
    el.classList.toggle('sel');
  }} else {{
    el.classList.toggle('sel');
    el.classList.toggle('sel-reg', el.classList.contains('sel'));
  }}
  updatePreview();
}}

function getSelected(id) {{
  return [...document.querySelectorAll('#' + id + ' .chip-opt.sel'),
          ...document.querySelectorAll('#' + id + ' .chip-opt.sel-reg')]
    .map(function(c) {{ return c.textContent.trim(); }})
    .filter(function(v, i, a) {{ return a.indexOf(v) === i; }});
}}

function calcCompleteness() {{
  const name = document.getElementById('company_name').value.trim();
  const desc = document.getElementById('description').value.trim();
  const sector = document.getElementById('sector').value;
  const country = document.getElementById('country').value.trim();
  let score = 0;
  if (name) score += 15;
  if (desc) score += 15;
  if (sector) score += 15;
  if (country) score += 15;
  const opts = [
    document.getElementById('arr').value !== 'Pre-revenue',
    document.getElementById('stage').value !== 'Bootstrapped',
    document.getElementById('runway').value,
    document.getElementById('current_decisions').value.trim(),
    getSelected('riskChips').length > 0,
    getSelected('regChips').length > 0,
    document.getElementById('comp_threat').value,
    document.getElementById('constraint').value,
  ];
  opts.forEach(function(o) {{ if (o) score += 5; }});
  return Math.min(score, 100);
}}

function updatePreview() {{
  const score = calcCompleteness();
  const color = score >= 80 ? 'var(--g)' : score >= 60 ? 'var(--ye)' : score >= 31 ? 'var(--or)' : 'var(--re)';
  const quality = score >= 80 ? 'Excellent — fully calibrated ✓' :
                  score >= 60 ? 'Good — personalized analysis active ✓' :
                  score >= 31 ? 'Getting there — partially calibrated' : 'Basic — generic analysis only';

  // Update completeness bar
  document.getElementById('compPct').textContent = score + '%';
  document.getElementById('compPct').style.color = color;
  document.getElementById('compFill').style.width = score + '%';
  document.getElementById('compFill').style.background = color;
  document.getElementById('compLabel').textContent = quality;

  // Update preview bar
  document.getElementById('pvPct').textContent = score + '%';
  document.getElementById('pvPct').style.color = color;
  document.getElementById('pvFill').style.width = score + '%';
  document.getElementById('pvFill').style.background = color;
  document.getElementById('pvQuality').textContent = quality;

  const name = document.getElementById('company_name').value.trim();
  const sector = document.getElementById('sector').value;
  const country = document.getElementById('country').value.trim();
  const arr = document.getElementById('arr').value;
  const stage = document.getElementById('stage').value;
  const runway = document.getElementById('runway').value;
  const risks = getSelected('riskChips');
  const regs = getSelected('regChips');
  const market = document.getElementById('primary_market').value;

  const badge = document.getElementById('previewBadge');
  badge.textContent = score >= 60 ? 'Active ✓' : score >= 31 ? 'Partial' : 'Incomplete';
  badge.style.background = score >= 60 ? 'var(--gd)' : score >= 31 ? 'rgba(255,215,64,.08)' : 'rgba(255,82,82,.06)';
  badge.style.borderColor = score >= 60 ? 'rgba(0,230,118,.2)' : score >= 31 ? 'rgba(255,215,64,.2)' : 'rgba(255,82,82,.15)';
  badge.style.color = score >= 60 ? 'var(--g)' : score >= 31 ? 'var(--ye)' : 'var(--re)';

  const body = document.getElementById('previewBody');
  if (!name && !sector) {{
    body.innerHTML = '<div class="pv-empty">Start filling in your company details to see how Vigil will read your business.</div>';
    return;
  }}

  const tagHtml = [];
  if (regs.includes('MiCA')) tagHtml.push('<div class="pv-tag re">MiCA Exposed</div>');
  if (regs.includes('EU AI Act')) tagHtml.push('<div class="pv-tag re">EU AI Act</div>');
  if (['Series A','Series B','Series C+'].includes(stage)) tagHtml.push('<div class="pv-tag or">Raising</div>');
  if (['EU','UK'].includes(market)) tagHtml.push('<div class="pv-tag gr">EU Market</div>');
  if (runway && runway !== 'Profitable') tagHtml.push('<div class="pv-tag nt">' + runway + ' runway</div>');

  const topRisk = regs.includes('MiCA') ? 'MiCA Art.63 enforcement' : risks[0] || 'macro conditions';
  const verdictText = name
    ? '<em>' + name + '</em> faces elevated exposure to <em>' + topRisk + '</em> given current market conditions.'
    : (sector || 'Your company') + ' sector faces elevated exposure to ' + topRisk + ' given current conditions.';

  body.innerHTML =
    '<div class="pv-name">' + (name || sector || 'Your Company') + '</div>' +
    '<div class="pv-sub">' + [country, sector, stage, arr].filter(Boolean).join(' · ') + '</div>' +
    (tagHtml.length ? '<div class="pv-tags">' + tagHtml.join('') + '</div>' : '') +
    (score >= 31 ? '<div class="pv-verdict">' + verdictText + '</div>' : '');
}}

function saveProfile() {{
  const name = document.getElementById('company_name').value.trim();
  const desc = document.getElementById('description').value.trim();
  let valid = true;

  if (!name) {{
    document.getElementById('err_name').classList.add('show');
    document.getElementById('company_name').classList.add('error');
    valid = false;
  }} else {{
    document.getElementById('err_name').classList.remove('show');
    document.getElementById('company_name').classList.remove('error');
  }}
  if (!desc) {{
    document.getElementById('err_desc').classList.add('show');
    document.getElementById('description').classList.add('error');
    valid = false;
  }} else {{
    document.getElementById('err_desc').classList.remove('show');
    document.getElementById('description').classList.remove('error');
  }}
  if (!valid) return;

  const profile = {{
    company_name: name,
    website: document.getElementById('website').value,
    description: desc,
    sector: document.getElementById('sector').value,
    sub_sector: document.getElementById('sub_sector').value,
    primary_market: document.getElementById('primary_market').value,
    country: document.getElementById('country').value,
    operating_countries: document.getElementById('operating_countries').value,
    arr: document.getElementById('arr').value,
    stage: document.getElementById('stage').value,
    runway: document.getElementById('runway').value,
    team_size: document.getElementById('team_size').value,
    currency: document.getElementById('currency').value,
    risk_areas: getSelected('riskChips'),
    regulations: getSelected('regChips'),
    risk_tolerance: document.getElementById('risk_tolerance').value,
    current_decisions: document.getElementById('current_decisions').value,
    comp_threat: document.getElementById('comp_threat').value,
    constraint: document.getElementById('constraint').value,
    completeness: calcCompleteness(),
    saved_at: new Date().toISOString()
  }};

  // Store for Python to read
  sessionStorage.setItem('vigil_profile', JSON.stringify(profile));

  // Also try to trigger Streamlit save via parent document
  try {{
    var textareas = window.parent.document.querySelectorAll('textarea');
    textareas.forEach(function(ta) {{
      if (ta.getAttribute('data-profile-bridge')) {{
        var setter = Object.getOwnPropertyDescriptor(window.parent.HTMLTextAreaElement.prototype, 'value');
        if (setter && setter.set) setter.set.call(ta, JSON.stringify(profile));
        else ta.value = JSON.stringify(profile);
        ta.dispatchEvent(new Event('input', {{bubbles:true}}));
        ta.dispatchEvent(new Event('change', {{bubbles:true}}));
      }}
    }});
    setTimeout(function() {{
      var saveBtns = window.parent.document.querySelectorAll('button');
      saveBtns.forEach(function(btn) {{
        if (btn.textContent && btn.textContent.includes('VIGIL_SAVE')) btn.click();
      }});
    }}, 100);
  }} catch(e) {{}}

  // Show toast
  const t = document.getElementById('toast');
  t.textContent = '✓ Profile saved — Vigil is calibrated to ' + name;
  t.classList.add('show');
  setTimeout(function() {{ t.classList.remove('show'); }}, 2000);

  // Redirect after short delay to let Streamlit pick up sessionStorage
  setTimeout(function() {{
    window.parent.location.href = '/dashboard';
  }}, 600);
}}

function skipProfile() {{
  window.parent.location.href = '/dashboard';
}}

// Theme toggle
var dark = true;
function toggleTheme() {{
  dark = !dark;
  const body = document.getElementById('profBody');
  const btn = document.getElementById('tbtn');
  if (dark) {{
    body.removeAttribute('data-theme');
    btn.textContent = '🌙';
  }} else {{
    body.setAttribute('data-theme', 'light');
    btn.textContent = '☀️';
  }}
  sessionStorage.setItem('vt', dark ? 'dark' : 'light');
}}

// Restore theme on load
(function() {{
  if (sessionStorage.getItem('vt') === 'light') {{
    dark = false;
    document.getElementById('profBody').setAttribute('data-theme', 'light');
    document.getElementById('tbtn').textContent = '☀️';
  }}
}})();

// Initial preview render
updatePreview();
</script>

{prefill_js}

</body>
</html>"""

    # -------------------------------------------------------------------------
    # Render via st.components.v1.html (full iframe, no Streamlit chrome)
    # -------------------------------------------------------------------------
    import streamlit.components.v1 as components
    components.html(html_page, height=2200, scrolling=True)

    # -------------------------------------------------------------------------
    # Save bridge: read sessionStorage via streamlit-js-eval
    # -------------------------------------------------------------------------
    try:
        from streamlit_js_eval import streamlit_js_eval

        profile_json = streamlit_js_eval(
            js_expressions="sessionStorage.getItem('vigil_profile')",
            key="read_vigil_profile",
        )

        if profile_json:
            try:
                profile_data = json.loads(profile_json)
                if profile_data and profile_data.get("company_name"):
                    # Map HTML field names → session_manager field names
                    python_profile = {
                        "name": profile_data.get("company_name", ""),
                        "website": profile_data.get("website", ""),
                        "description": profile_data.get("description", ""),
                        "sector": profile_data.get("sector", ""),
                        "sub_sector": profile_data.get("sub_sector", ""),
                        "primary_market": profile_data.get("primary_market", ""),
                        "country": profile_data.get("country", ""),
                        "operating_countries": profile_data.get("operating_countries", ""),
                        "arr": profile_data.get("arr", ""),
                        "arr_range": profile_data.get("arr", ""),
                        "stage": profile_data.get("stage", ""),
                        "funding_stage": profile_data.get("stage", ""),
                        "runway": profile_data.get("runway", ""),
                        "team_size": profile_data.get("team_size", ""),
                        "revenue_currency": profile_data.get("currency", ""),
                        "risk_areas": profile_data.get("risk_areas", []),
                        "risk_exposure_areas": profile_data.get("risk_areas", []),
                        "regulations": profile_data.get("regulations", []),
                        "active_regulations": profile_data.get("regulations", []),
                        "risk_tolerance": int(profile_data.get("risk_tolerance", 3)),
                        "current_decisions": profile_data.get("current_decisions", ""),
                        "comp_threat": profile_data.get("comp_threat", ""),
                        "primary_competitive_threat": profile_data.get("comp_threat", ""),
                        "constraint": profile_data.get("constraint", ""),
                        "biggest_constraint": profile_data.get("constraint", ""),
                        "saved_at": profile_data.get("saved_at", datetime.now(timezone.utc).isoformat()),
                    }

                    existing = load_profile()
                    # Only save if it's a new profile or the name changed
                    if not existing or existing.get("name") != python_profile["name"]:
                        save_profile(python_profile)
                        st.session_state["pending_auto_load"] = True
                        st.session_state["vigil_auto_loaded"] = False

                        # Clear sessionStorage after reading
                        streamlit_js_eval(
                            js_expressions="sessionStorage.removeItem('vigil_profile')",
                            key="clear_profile",
                        )
                        st.switch_page("pages/dashboard.py")
            except Exception:
                pass
    except ImportError:
        pass


main()
