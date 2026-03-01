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
logger = logging.getLogger("strategy-commander")

app = FastAPI(title="Strategy Commander", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Strategy Commander — Vigil Intelligence</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  :root {
    --bg: #070a0d;
    --surface: #0d1117;
    --surface2: #161c24;
    --border: #1f3a52;
    --accent: #e8b04b;
    --accent2: #c8851a;
    --accent3: #ffd580;
    --text: #e8e6e1;
    --muted: #6b7280;
    --success: #10b981;
    --danger: #ef4444;
    --red: #ff2d55;
    --green: #00e5a0;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }

  /* ── Header ── */
  header {
    background: linear-gradient(135deg, #070a0d 0%, #0d1117 100%);
    border-bottom: 2px solid var(--accent2);
    padding: 18px 40px; display: flex; align-items: center; gap: 16px;
  }
  .logo {
    width: 46px; height: 46px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 22px;
  }
  .header-text h1 {
    font-size: 1.45rem; font-weight: 800; letter-spacing: -.02em;
    background: linear-gradient(90deg, var(--accent3), var(--accent));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  .header-text p { font-size: 0.73rem; color: var(--muted); margin-top: 2px; }
  .header-badge {
    margin-left: auto; font-size: 0.68rem; font-weight: 800;
    color: var(--accent); background: rgba(232,176,75,0.1);
    border: 1px solid var(--accent2); padding: 5px 14px;
    border-radius: 20px; text-transform: uppercase; letter-spacing: .1em;
  }

  /* ── Layout ── */
  .layout {
    max-width: 1400px; margin: 0 auto; padding: 28px 24px;
    display: grid; grid-template-columns: 400px 1fr; gap: 24px; align-items: start;
  }
  @media (max-width: 1050px) { .layout { grid-template-columns: 1fr; } }

  /* ── Panel ── */
  .panel {
    background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 24px;
  }
  .panel-title {
    font-size: 0.75rem; font-weight: 800; text-transform: uppercase;
    letter-spacing: .09em; color: var(--accent);
    margin-bottom: 18px; display: flex; align-items: center; gap: 8px;
  }
  .section-divider {
    font-size: 0.65rem; font-weight: 700; color: var(--muted);
    text-transform: uppercase; letter-spacing: .09em;
    padding: 0 0 7px; border-bottom: 1px solid var(--border); margin: 18px 0 13px;
  }
  .section-divider:first-of-type { margin-top: 0; }

  /* ── Fields ── */
  .field { margin-bottom: 13px; }
  label {
    display: block; font-size: 0.7rem; font-weight: 600;
    color: var(--muted); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 5px;
  }
  input, textarea {
    width: 100%; background: var(--surface2); border: 1px solid var(--border);
    border-radius: 8px; padding: 10px 13px; color: var(--text);
    font-size: 0.87rem; transition: border .2s; outline: none; font-family: inherit;
  }
  input:focus, textarea:focus { border-color: var(--accent); }
  textarea { resize: vertical; }

  .horizon-group { display: flex; gap: 6px; }
  .horizon-btn {
    flex: 1; padding: 8px 0; border: 1px solid var(--border);
    background: var(--surface2); color: var(--muted); border-radius: 7px;
    font-size: 0.8rem; cursor: pointer; transition: all .2s; text-align: center;
  }
  .horizon-btn.active {
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-color: transparent; color: #07080a; font-weight: 800;
  }

  /* ── Verdict input box ── */
  .verdict-box {
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 10px; overflow: hidden;
  }
  .verdict-box-header {
    padding: 9px 14px; background: rgba(232,176,75,0.07);
    border-bottom: 1px solid var(--border);
    font-size: 0.75rem; font-weight: 700; color: var(--accent);
    display: flex; align-items: center; gap: 7px;
  }
  .verdict-dot {
    width: 7px; height: 7px; border-radius: 50%; background: var(--muted); transition: background .2s;
  }
  .verdict-dot.filled { background: var(--accent); }
  .verdict-box textarea {
    border: none; border-radius: 0; background: var(--surface2);
    min-height: 220px; font-size: 0.8rem;
    border-bottom-left-radius: 10px; border-bottom-right-radius: 10px;
  }
  .verdict-box textarea:focus { border-color: transparent; box-shadow: none; }

  .hint {
    font-size: 0.7rem; color: var(--muted); margin-top: 6px;
    padding: 6px 10px; background: var(--surface2); border-radius: 6px;
    border-left: 2px solid var(--accent2);
  }

  /* ── Submit ── */
  .btn-command {
    width: 100%; padding: 15px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border: none; border-radius: 10px;
    color: #07080a; font-size: 1rem; font-weight: 900;
    cursor: pointer; margin-top: 10px; transition: all .2s;
    display: flex; align-items: center; justify-content: center; gap: 10px;
    letter-spacing: .03em;
    box-shadow: 0 0 28px rgba(232,176,75,0.2);
  }
  .btn-command:hover { opacity: .9; box-shadow: 0 0 40px rgba(232,176,75,0.35); }
  .btn-command:disabled { opacity: .35; cursor: not-allowed; box-shadow: none; }

  /* ── Output ── */
  .output-panel {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; display: flex; flex-direction: column;
    min-height: 700px;
  }
  .output-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 16px 22px; border-bottom: 1px solid var(--border);
    background: rgba(232,176,75,0.04);
  }
  .output-title {
    font-size: 0.82rem; font-weight: 800; color: var(--accent);
    text-transform: uppercase; letter-spacing: .07em;
    display: flex; align-items: center; gap: 8px;
  }
  #status-badge {
    font-size: 0.7rem; padding: 4px 12px; border-radius: 20px; font-weight: 700;
  }
  .badge-idle { background: var(--surface2); color: var(--muted); }
  .badge-running { background: #1a1400; color: var(--accent); animation: pulse 1.4s infinite; }
  .badge-done { background: #064e3b; color: var(--success); }
  .badge-error { background: #3d0015; color: var(--danger); }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

  #output-box {
    flex: 1; padding: 26px; font-size: 0.875rem; line-height: 1.78;
    overflow-y: auto; max-height: 85vh;
  }
  #output-box.empty {
    display: flex; align-items: center; justify-content: center;
    color: var(--muted); flex-direction: column; gap: 14px; text-align: center;
  }
  .empty-icon { font-size: 3.5rem; }
  .empty-sub { font-size: 0.8rem; max-width: 300px; line-height: 1.6; }

  /* ── Markdown ── */
  #output-box h2 {
    color: var(--accent); font-size: 0.95rem;
    margin: 24px 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--border);
  }
  #output-box h2:first-child { margin-top: 0; }
  #output-box h3 { font-size: 0.88rem; color: var(--accent3); margin: 14px 0 7px; }
  #output-box h4 { font-size: 0.82rem; color: var(--muted); margin: 10px 0 5px; text-transform: uppercase; letter-spacing: .05em; }
  #output-box strong { color: var(--accent3); }
  #output-box blockquote {
    border-left: 3px solid var(--accent);
    padding: 10px 16px; margin: 12px 0;
    background: rgba(232,176,75,0.07); border-radius: 0 8px 8px 0;
    font-style: normal; color: var(--text);
  }
  #output-box pre {
    background: #0a0c0f; border: 1px solid var(--border);
    border-radius: 8px; padding: 16px; margin: 12px 0;
    font-family: 'Courier New', monospace; font-size: 0.82rem;
    color: var(--accent3); overflow-x: auto; white-space: pre;
  }
  #output-box code { background: #0a0c0f; padding: 2px 6px; border-radius: 4px; font-size: 0.82rem; color: var(--accent3); }
  #output-box pre code { background: none; padding: 0; }
  #output-box ul, #output-box ol { padding-left: 20px; margin: 8px 0; }
  #output-box li { margin: 6px 0; }
  #output-box hr { border-color: var(--border); margin: 20px 0; }
  #output-box p { margin: 7px 0; }
  #output-box table { width: 100%; border-collapse: collapse; margin: 14px 0; font-size: 0.83rem; }
  #output-box th {
    background: #1a1400; color: var(--accent);
    padding: 9px 13px; text-align: left; border: 1px solid var(--border);
    font-size: 0.75rem; text-transform: uppercase; letter-spacing: .05em;
  }
  #output-box td { padding: 9px 13px; border: 1px solid var(--border); vertical-align: top; }
  #output-box tr:nth-child(even) td { background: #0d1117; }

  /* ── Urgency ribbon ── */
  .urgency-bar {
    display: flex; gap: 0; margin-bottom: 18px; border-radius: 8px; overflow: hidden;
    border: 1px solid var(--border);
  }
  .urgency-item {
    flex: 1; padding: 8px 0; text-align: center; font-size: 0.72rem; font-weight: 700;
    color: var(--muted); background: var(--surface2); cursor: pointer;
    border-right: 1px solid var(--border); transition: all .2s; text-transform: uppercase; letter-spacing: .05em;
  }
  .urgency-item:last-child { border-right: none; }
  .urgency-item.active-monitor { background: #064e3b; color: var(--success); }
  .urgency-item.active-prepare { background: #1a1400; color: var(--accent); }
  .urgency-item.active-mobilize { background: #2d1a00; color: #fb923c; }
  .urgency-item.active-emergency { background: #3d0015; color: var(--red); }

  .spinner {
    width: 42px; height: 42px;
    border: 3px solid var(--border); border-top-color: var(--accent);
    border-radius: 50%; animation: spin 0.75s linear infinite; margin: 80px auto;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<header>
  <div class="logo">🎖️</div>
  <div class="header-text">
    <h1>Strategy Commander</h1>
    <p>Action Engine — Vigil Intelligence</p>
  </div>
  <div class="header-badge">Strategic Playbook</div>
</header>

<div class="layout">

  <!-- LEFT: Inputs -->
  <div style="display:flex;flex-direction:column;gap:18px;">

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

    <!-- Risk Synthesizer Verdict -->
    <div class="panel">
      <div class="panel-title">⚡ Risk Synthesizer Input</div>

      <div class="verdict-box">
        <div class="verdict-box-header">
          <div class="verdict-dot" id="verdict-dot"></div>
          ⚡ Risk Synthesizer Verdict
        </div>
        <textarea id="risk_verdict" placeholder="Paste the full Risk Synthesizer verdict here…" onchange="checkDot(this)" oninput="checkDot(this)"></textarea>
      </div>
      <div class="hint">💡 Run Risk Synthesizer first, then paste the full verdict here to generate the strategic playbook.</div>
    </div>

    <button class="btn-command" id="submit-btn" onclick="generatePlaybook()">
      <span id="btn-text">🎖️ Generate Strategic Playbook</span>
    </button>

  </div>

  <!-- RIGHT: Output -->
  <div class="output-panel">
    <div class="output-header">
      <div class="output-title">🎖️ Strategic Playbook</div>
      <span id="status-badge" class="badge-idle">AWAITING INPUT</span>
    </div>
    <div id="output-box" class="empty">
      <div class="empty-icon">🎖️</div>
      <div class="empty-sub">Paste the Risk Synthesizer verdict and hit <strong>Generate Strategic Playbook</strong> to get your time-bound action commands.</div>
    </div>
  </div>

</div>

<script>
  let selectedHorizon = "24h";

  function selectHorizon(el) {
    document.querySelectorAll(".horizon-btn").forEach(b => b.classList.remove("active"));
    el.classList.add("active");
    selectedHorizon = el.dataset.val;
  }

  function checkDot(el) {
    document.getElementById("verdict-dot").classList.toggle("filled", el.value.trim().length > 0);
  }

  async function generatePlaybook() {
    const business_type = document.getElementById("business_type").value.trim();
    const sector = document.getElementById("sector").value.trim();
    const risk_verdict = document.getElementById("risk_verdict").value.trim();

    if (!business_type || !sector) { alert("Please fill in Business Type and Sector."); return; }
    if (!risk_verdict) { alert("Please paste the Risk Synthesizer verdict."); return; }

    const btn = document.getElementById("submit-btn");
    const box = document.getElementById("output-box");
    btn.disabled = true;
    document.getElementById("btn-text").textContent = "Commanding…";

    const badge = document.getElementById("status-badge");
    badge.className = "badge-running"; badge.textContent = "GENERATING PLAYBOOK";
    box.classList.remove("empty");
    box.innerHTML = '<div class="spinner"></div>';

    try {
      const resp = await fetch("/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ business_type, sector, risk_horizon: selectedHorizon, risk_verdict })
      });
      if (!resp.ok) { const e = await resp.json(); throw new Error(e.detail || "Unknown error"); }
      const data = await resp.json();
      box.innerHTML = marked.parse(data.playbook);
      badge.className = "badge-done"; badge.textContent = "PLAYBOOK READY";
    } catch (e) {
      box.innerHTML = `<div style="color:var(--danger);padding:20px">❌ Error: ${e.message}</div>`;
      badge.className = "badge-error"; badge.textContent = "ERROR";
    } finally {
      btn.disabled = false;
      document.getElementById("btn-text").textContent = "🎖️ Generate Strategic Playbook";
    }
  }
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


@app.post("/command")
async def command(request: Request):
    body = await request.json()
    business_type = body.get("business_type", "").strip()
    sector = body.get("sector", "").strip()
    risk_horizon = body.get("risk_horizon", "24h").strip()
    risk_verdict = body.get("risk_verdict", "").strip()

    if not business_type or not sector:
        return JSONResponse(status_code=422, content={"detail": "business_type and sector are required"})
    if not risk_verdict:
        return JSONResponse(status_code=422, content={"detail": "risk_verdict is required"})

    logger.info(f"Strategy Commander: sector={sector}, horizon={risk_horizon}")
    try:
        from agent import run_strategy_commander
        playbook = run_strategy_commander(risk_verdict, business_type, sector, risk_horizon)
        logger.info("Strategy Commander complete")
        return {"playbook": playbook}
    except Exception as e:
        logger.error(f"Strategy Commander error: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "strategy-commander"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 3008))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
