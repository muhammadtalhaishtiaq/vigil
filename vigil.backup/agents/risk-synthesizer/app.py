import os
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv

load_dotenv()

log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    handlers=[
        logging.FileHandler(log_dir / "app.json"),
        logging.StreamHandler(),
    ],
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}',
)
logger = logging.getLogger("risk-synthesizer")

app = FastAPI(title="Risk Synthesizer", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Risk Synthesizer — Vigil Intelligence</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  :root {
    --bg: #0d0005;
    --surface: #180008;
    --surface2: #220010;
    --border: #4a0018;
    --accent: #ff2d55;
    --accent2: #c40030;
    --accent3: #ff6b6b;
    --text: #f0e4e6;
    --muted: #7a5060;
    --success: #10b981;
    --danger: #ff2d55;
    --warning: #f59e0b;
    --gold: #fbbf24;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }

  /* ── Header ── */
  header {
    background: linear-gradient(135deg, #0d0005 0%, #1a000a 100%);
    border-bottom: 1px solid var(--border);
    padding: 18px 40px; display: flex; align-items: center; gap: 16px;
    position: relative; overflow: hidden;
  }
  header::after {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
  }
  .logo {
    width: 44px; height: 44px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 22px;
  }
  header h1 {
    font-size: 1.5rem; font-weight: 800;
    background: linear-gradient(90deg, var(--accent3), var(--accent));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    letter-spacing: -0.02em;
  }
  header span { font-size: 0.78rem; color: var(--muted); margin-left: 4px; }
  .header-badge {
    margin-left: auto;
    font-size: 0.7rem; font-weight: 700; color: var(--accent);
    background: rgba(255,45,85,0.12); border: 1px solid var(--border);
    padding: 5px 12px; border-radius: 20px; letter-spacing: .08em;
    text-transform: uppercase;
  }

  /* ── Layout ── */
  .layout {
    max-width: 1400px; margin: 0 auto; padding: 28px 24px;
    display: grid; grid-template-columns: 1fr 1fr; gap: 24px;
  }
  @media (max-width: 1000px) { .layout { grid-template-columns: 1fr; } }

  .left-col { display: flex; flex-direction: column; gap: 18px; }
  .right-col { display: flex; flex-direction: column; gap: 0; }

  /* ── Panels ── */
  .panel {
    background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 22px;
  }
  .panel-title {
    font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: .09em; margin-bottom: 16px;
    display: flex; align-items: center; gap: 8px; color: var(--accent);
  }
  .panel-title.gold { color: var(--gold); }

  .section-divider {
    font-size: 0.65rem; font-weight: 700; color: var(--muted);
    text-transform: uppercase; letter-spacing: .09em;
    padding: 6px 0 8px; border-bottom: 1px solid var(--border); margin-bottom: 12px; margin-top: 6px;
  }

  /* ── Form fields ── */
  .field { margin-bottom: 12px; }
  label {
    display: block; font-size: 0.7rem; font-weight: 600;
    color: var(--muted); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 5px;
  }
  input, textarea {
    width: 100%; background: var(--surface2); border: 1px solid var(--border);
    border-radius: 8px; padding: 9px 12px; color: var(--text);
    font-size: 0.85rem; transition: border .2s; outline: none; font-family: inherit;
  }
  input:focus, textarea:focus { border-color: var(--accent); }
  textarea { resize: vertical; }

  .horizon-group { display: flex; gap: 6px; }
  .horizon-btn {
    flex: 1; padding: 7px 0; border: 1px solid var(--border); background: var(--surface2);
    color: var(--muted); border-radius: 6px; font-size: 0.8rem; cursor: pointer;
    transition: all .2s; text-align: center;
  }
  .horizon-btn.active {
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-color: transparent; color: white; font-weight: 700;
  }

  /* ── Agent input cards ── */
  .agent-input {
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 10px; overflow: hidden; margin-bottom: 12px;
  }
  .agent-input:last-child { margin-bottom: 0; }
  .agent-input-header {
    display: flex; align-items: center; gap: 8px;
    padding: 9px 14px;
    background: rgba(255,45,85,0.06);
    border-bottom: 1px solid var(--border);
    cursor: pointer; user-select: none;
    justify-content: space-between;
  }
  .agent-input-header:hover { background: rgba(255,45,85,0.1); }
  .agent-input-title { font-size: 0.78rem; font-weight: 700; }
  .agent-dot {
    width: 7px; height: 7px; border-radius: 50%; background: var(--muted);
    transition: background .2s;
  }
  .agent-dot.filled { background: var(--accent); }
  .agent-input-body { padding: 12px; display: none; }
  .agent-input-body.open { display: block; }
  .agent-input textarea { min-height: 120px; font-size: 0.8rem; }

  .hint {
    font-size: 0.7rem; color: var(--muted); margin-top: 5px;
    padding: 5px 10px; background: var(--surface); border-radius: 6px;
    border-left: 2px solid var(--accent2);
  }

  /* ── Submit ── */
  .btn-verdict {
    width: 100%; padding: 16px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border: none; border-radius: 10px;
    color: white; font-size: 1.05rem; font-weight: 800;
    cursor: pointer; transition: all .2s;
    display: flex; align-items: center; justify-content: center; gap: 10px;
    letter-spacing: .02em;
    box-shadow: 0 0 30px rgba(255,45,85,0.25);
  }
  .btn-verdict:hover { opacity: .9; box-shadow: 0 0 40px rgba(255,45,85,0.4); }
  .btn-verdict:disabled { opacity: .35; cursor: not-allowed; box-shadow: none; }

  /* ── Output panel ── */
  .output-panel {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; height: 100%;
    display: flex; flex-direction: column;
  }
  .output-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 18px 22px; border-bottom: 1px solid var(--border);
    background: rgba(255,45,85,0.05);
  }
  .output-title { font-size: 0.85rem; font-weight: 800; color: var(--accent); letter-spacing: .05em; text-transform: uppercase; }

  #status-badge {
    font-size: 0.7rem; padding: 4px 12px; border-radius: 20px; font-weight: 700;
  }
  .badge-idle { background: var(--surface2); color: var(--muted); }
  .badge-running { background: #3d0015; color: var(--accent); animation: pulse 1.4s infinite; }
  .badge-done { background: #064e3b; color: var(--success); }
  .badge-error { background: #3d0015; color: var(--danger); }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

  #output-box {
    flex: 1; padding: 24px;
    font-size: 0.875rem; line-height: 1.78;
    overflow-y: auto; min-height: 500px; max-height: 82vh;
  }
  #output-box.empty {
    display: flex; align-items: center; justify-content: center;
    color: var(--muted); flex-direction: column; gap: 14px; text-align: center;
  }
  .empty-icon { font-size: 3.5rem; }
  .empty-sub { font-size: 0.8rem; max-width: 280px; line-height: 1.6; }

  /* ── Markdown ── */
  #output-box h2 {
    color: var(--accent); font-size: 0.95rem; margin: 22px 0 10px;
    padding-bottom: 6px; border-bottom: 1px solid var(--border);
  }
  #output-box h2:first-child { margin-top: 0; }
  #output-box h3 { font-size: 0.88rem; color: var(--accent3); margin: 14px 0 7px; }
  #output-box strong { color: #fca5a5; }
  #output-box blockquote {
    border-left: 3px solid var(--accent);
    padding: 10px 16px; margin: 14px 0;
    background: rgba(255,45,85,0.08); border-radius: 0 8px 8px 0;
    color: var(--text); font-style: italic; font-size: 0.95rem;
  }
  #output-box pre {
    background: #1a000a; border: 1px solid var(--border);
    border-radius: 8px; padding: 14px; margin: 12px 0;
    font-family: 'Courier New', monospace; font-size: 0.82rem;
    color: var(--accent3); overflow-x: auto; white-space: pre;
  }
  #output-box code { background: #1a000a; padding: 2px 6px; border-radius: 4px; font-size: 0.82rem; color: var(--accent3); }
  #output-box pre code { background: none; padding: 0; }
  #output-box ul, #output-box ol { padding-left: 18px; margin: 8px 0; }
  #output-box li { margin: 5px 0; }
  #output-box hr { border-color: var(--border); margin: 18px 0; }
  #output-box p { margin: 6px 0; }
  #output-box table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 0.83rem; }
  #output-box th {
    background: #3d0015; color: var(--accent);
    padding: 8px 12px; text-align: left; border: 1px solid var(--border);
    font-size: 0.75rem; text-transform: uppercase; letter-spacing: .05em;
  }
  #output-box td { padding: 8px 12px; border: 1px solid var(--border); vertical-align: top; }
  #output-box tr:nth-child(even) td { background: #1a000a; }

  .spinner {
    width: 44px; height: 44px;
    border: 3px solid var(--border); border-top-color: var(--accent);
    border-radius: 50%; animation: spin 0.75s linear infinite; margin: 80px auto;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Collapse chevron ── */
  .chevron { font-size: 0.7rem; color: var(--muted); transition: transform .2s; }
  .chevron.open { transform: rotate(180deg); }
</style>
</head>
<body>

<header>
  <div class="logo">⚡</div>
  <div>
    <h1>Risk Synthesizer <span>by Vigil</span></h1>
  </div>
  <div class="header-badge">Final Verdict Engine</div>
</header>

<div class="layout">

  <!-- LEFT: Inputs -->
  <div class="left-col">

    <!-- Business Context -->
    <div class="panel">
      <div class="panel-title">📋 Business Context</div>
      <div class="field">
        <label>Business Type</label>
        <input id="business_type" type="text" placeholder="e.g. SaaS HR platform for mid-market"/>
      </div>
      <div class="field">
        <label>Sector</label>
        <input id="sector" type="text" placeholder="e.g. Technology, Finance, Healthcare…"/>
      </div>
      <div class="field">
        <label>Risk Horizon</label>
        <div class="horizon-group">
          <div class="horizon-btn active" data-val="24h" onclick="selectHorizon(this)">24h</div>
          <div class="horizon-btn" data-val="7d" onclick="selectHorizon(this)">7d</div>
          <div class="horizon-btn" data-val="30d" onclick="selectHorizon(this)">30d</div>
          <div class="horizon-btn" data-val="90d" onclick="selectHorizon(this)">90d</div>
        </div>
      </div>
    </div>

    <!-- Agent Outputs -->
    <div class="panel">
      <div class="panel-title gold">📥 Agent Reports (paste all 4)</div>

      <!-- Signal Harvester -->
      <div class="agent-input" id="ai-signal">
        <div class="agent-input-header" onclick="toggleAgent('signal')">
          <span style="display:flex;align-items:center;gap:8px">
            <div class="agent-dot" id="dot-signal"></div>
            <span class="agent-input-title" style="color:#00d4ff">📡 Signal Harvester Report</span>
          </span>
          <span class="chevron" id="chev-signal">▼</span>
        </div>
        <div class="agent-input-body" id="body-signal">
          <textarea id="signal_report" placeholder="Paste Signal Harvester output here…" onchange="checkDot('signal', this)"></textarea>
        </div>
      </div>

      <!-- Narrative Intel -->
      <div class="agent-input" id="ai-narrative">
        <div class="agent-input-header" onclick="toggleAgent('narrative')">
          <span style="display:flex;align-items:center;gap:8px">
            <div class="agent-dot" id="dot-narrative"></div>
            <span class="agent-input-title" style="color:#a78bfa">🧠 Narrative Intel Report</span>
          </span>
          <span class="chevron" id="chev-narrative">▼</span>
        </div>
        <div class="agent-input-body" id="body-narrative">
          <textarea id="narrative_report" placeholder="Paste Narrative Intel output here…" onchange="checkDot('narrative', this)"></textarea>
        </div>
      </div>

      <!-- Macro Watchdog -->
      <div class="agent-input" id="ai-macro">
        <div class="agent-input-header" onclick="toggleAgent('macro')">
          <span style="display:flex;align-items:center;gap:8px">
            <div class="agent-dot" id="dot-macro"></div>
            <span class="agent-input-title" style="color:#f59e0b">🐕 Macro Watchdog Report</span>
          </span>
          <span class="chevron" id="chev-macro">▼</span>
        </div>
        <div class="agent-input-body" id="body-macro">
          <textarea id="macro_report" placeholder="Paste Macro Watchdog output here…" onchange="checkDot('macro', this)"></textarea>
        </div>
      </div>

      <!-- Competitive Intel -->
      <div class="agent-input" id="ai-competitive">
        <div class="agent-input-header" onclick="toggleAgent('competitive')">
          <span style="display:flex;align-items:center;gap:8px">
            <div class="agent-dot" id="dot-competitive"></div>
            <span class="agent-input-title" style="color:#00e5a0">🎯 Competitive Intel Report</span>
          </span>
          <span class="chevron" id="chev-competitive">▼</span>
        </div>
        <div class="agent-input-body" id="body-competitive">
          <textarea id="competitive_report" placeholder="Paste Competitive Intel output here…" onchange="checkDot('competitive', this)"></textarea>
        </div>
      </div>

      <div class="hint" style="margin-top:10px">
        💡 Paste outputs from all 4 Vigil agents above, then render the final verdict.
      </div>
    </div>

    <!-- Submit -->
    <button class="btn-verdict" id="submit-btn" onclick="synthesize()">
      <span id="btn-text">⚡ Render Final Verdict</span>
    </button>

  </div>

  <!-- RIGHT: Output -->
  <div class="right-col">
    <div class="output-panel">
      <div class="output-header">
        <div class="output-title">⚡ MarketShock Sentinel — Risk Verdict</div>
        <span id="status-badge" class="badge-idle">AWAITING INPUT</span>
      </div>
      <div id="output-box" class="empty">
        <div class="empty-icon">⚡</div>
        <div class="empty-sub">Feed all four agent reports and hit <strong>Render Final Verdict</strong> to get the authoritative risk score and action brief.</div>
      </div>
    </div>
  </div>

</div>

<script>
  let selectedHorizon = "24h";
  const openPanels = {};

  function selectHorizon(el) {
    document.querySelectorAll(".horizon-btn").forEach(b => b.classList.remove("active"));
    el.classList.add("active");
    selectedHorizon = el.dataset.val;
  }

  function toggleAgent(id) {
    const body = document.getElementById("body-" + id);
    const chev = document.getElementById("chev-" + id);
    const isOpen = body.classList.contains("open");
    body.classList.toggle("open", !isOpen);
    chev.classList.toggle("open", !isOpen);
  }

  function checkDot(id, el) {
    const dot = document.getElementById("dot-" + id);
    dot.classList.toggle("filled", el.value.trim().length > 0);
  }

  // Also check on input (not just change)
  ["signal","narrative","macro","competitive"].forEach(id => {
    const ta = document.getElementById(id + "_report");
    if (ta) ta.addEventListener("input", () => checkDot(id, ta));
  });

  async function synthesize() {
    const business_type = document.getElementById("business_type").value.trim();
    const sector = document.getElementById("sector").value.trim();
    const signal_report = document.getElementById("signal_report").value.trim();
    const narrative_report = document.getElementById("narrative_report").value.trim();
    const macro_report = document.getElementById("macro_report").value.trim();
    const competitive_report = document.getElementById("competitive_report").value.trim();

    if (!business_type || !sector) { alert("Please fill in Business Type and Sector."); return; }
    if (!signal_report || !narrative_report || !macro_report || !competitive_report) {
      alert("Please paste all 4 agent reports before running the synthesis."); return;
    }

    const btn = document.getElementById("submit-btn");
    const box = document.getElementById("output-box");
    btn.disabled = true;
    document.getElementById("btn-text").textContent = "Synthesizing…";

    const badge = document.getElementById("status-badge");
    badge.className = "badge-running"; badge.textContent = "SYNTHESIZING";
    box.classList.remove("empty");
    box.innerHTML = '<div class="spinner"></div>';

    try {
      const resp = await fetch("/synthesize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          business_type, sector, risk_horizon: selectedHorizon,
          signal_report, narrative_report, macro_report, competitive_report
        })
      });
      if (!resp.ok) { const e = await resp.json(); throw new Error(e.detail || "Unknown error"); }
      const data = await resp.json();
      box.innerHTML = marked.parse(data.report);
      badge.className = "badge-done"; badge.textContent = "VERDICT RENDERED";
    } catch (e) {
      box.innerHTML = `<div style="color:var(--danger); padding:20px">❌ Error: ${e.message}</div>`;
      badge.className = "badge-error"; badge.textContent = "ERROR";
    } finally {
      btn.disabled = false;
      document.getElementById("btn-text").textContent = "⚡ Render Final Verdict";
    }
  }
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


@app.post("/synthesize")
async def synthesize(request: Request):
    body = await request.json()
    business_type = body.get("business_type", "").strip()
    sector = body.get("sector", "").strip()
    risk_horizon = body.get("risk_horizon", "24h").strip()
    signal_report = body.get("signal_report", "").strip()
    narrative_report = body.get("narrative_report", "").strip()
    macro_report = body.get("macro_report", "").strip()
    competitive_report = body.get("competitive_report", "").strip()

    if not business_type or not sector:
        return JSONResponse(status_code=422, content={"detail": "business_type and sector are required"})
    if not all([signal_report, narrative_report, macro_report, competitive_report]):
        return JSONResponse(status_code=422, content={"detail": "All four agent reports are required"})

    logger.info(f"Risk Synthesizer: sector={sector}, horizon={risk_horizon}")
    try:
        from agent import run_risk_synthesizer
        report = run_risk_synthesizer(
            business_type, sector, risk_horizon,
            signal_report, narrative_report, macro_report, competitive_report
        )
        logger.info("Risk Synthesizer complete")
        return {"report": report}
    except Exception as e:
        logger.error(f"Risk Synthesizer error: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "risk-synthesizer"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 3007))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
