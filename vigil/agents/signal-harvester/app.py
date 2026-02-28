import os
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv

load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────────
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
logger = logging.getLogger("signal-harvester")

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Signal Harvester", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Signal Harvester — Vigil Intelligence</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  :root {
    --bg: #0a0e1a;
    --surface: #111827;
    --surface2: #1a2235;
    --border: #1e3a5f;
    --accent: #00d4ff;
    --accent2: #7c3aed;
    --text: #e2e8f0;
    --muted: #64748b;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
  }
  header {
    background: linear-gradient(135deg, #0a0e1a 0%, #0f172a 100%);
    border-bottom: 1px solid var(--border);
    padding: 20px 40px;
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .logo {
    width: 44px; height: 44px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 22px;
  }
  header h1 {
    font-size: 1.5rem; font-weight: 700;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  header span { font-size: 0.8rem; color: var(--muted); margin-left: 4px; }
  .container {
    max-width: 1100px; margin: 0 auto;
    padding: 40px 24px;
    display: grid;
    grid-template-columns: 360px 1fr;
    gap: 28px; align-items: start;
  }
  @media (max-width: 800px) { .container { grid-template-columns: 1fr; } }
  .panel {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 16px; padding: 28px;
  }
  .panel h2 {
    font-size: 1rem; font-weight: 600; color: var(--accent);
    margin-bottom: 22px; display: flex; align-items: center; gap: 8px;
  }
  .field { margin-bottom: 18px; }
  label {
    display: block; font-size: 0.78rem; font-weight: 600;
    color: var(--muted); text-transform: uppercase;
    letter-spacing: .06em; margin-bottom: 7px;
  }
  input, textarea {
    width: 100%; background: var(--surface2);
    border: 1px solid var(--border); border-radius: 10px;
    padding: 11px 14px; color: var(--text);
    font-size: 0.92rem; transition: border .2s; outline: none;
  }
  input:focus, textarea:focus { border-color: var(--accent); }
  textarea { resize: vertical; min-height: 80px; }
  .horizon-group { display: flex; gap: 8px; flex-wrap: wrap; }
  .horizon-btn {
    flex: 1; padding: 9px 0;
    border: 1px solid var(--border); background: var(--surface2);
    color: var(--muted); border-radius: 8px;
    font-size: 0.85rem; cursor: pointer; transition: all .2s; text-align: center;
  }
  .horizon-btn.active {
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-color: transparent; color: white; font-weight: 600;
  }
  .btn-submit {
    width: 100%; padding: 14px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border: none; border-radius: 10px;
    color: white; font-size: 1rem; font-weight: 700;
    cursor: pointer; margin-top: 8px; transition: opacity .2s;
    display: flex; align-items: center; justify-content: center; gap: 8px;
  }
  .btn-submit:hover { opacity: .88; }
  .btn-submit:disabled { opacity: .45; cursor: not-allowed; }
  .output-panel { min-height: 500px; }
  .output-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 18px;
  }
  #status-badge {
    font-size: 0.75rem; padding: 4px 12px;
    border-radius: 20px; font-weight: 600;
  }
  .badge-idle { background: var(--surface2); color: var(--muted); }
  .badge-running { background: #1e3a5f; color: var(--accent); animation: pulse 1.5s infinite; }
  .badge-done { background: #064e3b; color: var(--success); }
  .badge-error { background: #450a0a; color: var(--danger); }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }
  #output-box {
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 12px; padding: 24px;
    min-height: 420px; font-size: 0.9rem; line-height: 1.7;
    overflow-y: auto; max-height: 75vh;
  }
  #output-box.empty {
    display: flex; align-items: center; justify-content: center;
    color: var(--muted); flex-direction: column; gap: 12px;
  }
  .empty-icon { font-size: 3rem; }
  #output-box h2 {
    color: var(--accent); font-size: 1rem;
    margin: 20px 0 10px; padding-bottom: 6px;
    border-bottom: 1px solid var(--border);
  }
  #output-box h2:first-child { margin-top: 0; }
  #output-box strong { color: #93c5fd; }
  #output-box ul, #output-box ol { padding-left: 18px; margin: 8px 0; }
  #output-box li { margin: 4px 0; }
  #output-box hr { border-color: var(--border); margin: 16px 0; }
  #output-box p { margin: 6px 0; }
  #output-box code {
    background: #1e293b; padding: 2px 6px;
    border-radius: 4px; font-size: 0.85rem;
  }
  .spinner {
    width: 40px; height: 40px;
    border: 3px solid var(--border); border-top-color: var(--accent);
    border-radius: 50%; animation: spin 0.8s linear infinite; margin: 60px auto;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<header>
  <div class="logo">📡</div>
  <div>
    <h1>Signal Harvester <span>by Vigil</span></h1>
  </div>
</header>

<div class="container">
  <div class="panel">
    <h2>📋 Business Context</h2>
    <div class="field">
      <label>Business Type</label>
      <textarea id="business_type" placeholder="e.g. SaaS platform selling HR software to mid-market companies"></textarea>
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
    <div class="field">
      <label>Specific Concern <span style="color:var(--muted);font-weight:400;text-transform:none">(optional)</span></label>
      <textarea id="specific_concern" placeholder="e.g. Impact of rising rates on our SaaS valuations…" style="min-height:60px"></textarea>
    </div>
    <button class="btn-submit" id="submit-btn" onclick="harvest()">
      <span id="btn-text">⚡ Harvest Signals</span>
    </button>
  </div>

  <div class="panel output-panel">
    <div class="output-header">
      <h2 style="margin:0">📊 Intelligence Briefing</h2>
      <span id="status-badge" class="badge-idle">IDLE</span>
    </div>
    <div id="output-box" class="empty">
      <div class="empty-icon">📡</div>
      <div>Enter your business context and hit <strong>Harvest Signals</strong></div>
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

  function setStatus(type, label) {
    const b = document.getElementById("status-badge");
    b.className = "badge-" + type;
    b.textContent = label;
  }

  async function harvest() {
    const business_type = document.getElementById("business_type").value.trim();
    const sector = document.getElementById("sector").value.trim();
    const specific_concern = document.getElementById("specific_concern").value.trim();

    if (!business_type || !sector) { alert("Please fill in Business Type and Sector."); return; }

    const btn = document.getElementById("submit-btn");
    const box = document.getElementById("output-box");
    btn.disabled = true;
    document.getElementById("btn-text").textContent = "Harvesting…";
    setStatus("running", "HARVESTING");
    box.classList.remove("empty");
    box.innerHTML = '<div class="spinner"></div>';

    try {
      const resp = await fetch("/harvest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ business_type, sector, risk_horizon: selectedHorizon, specific_concern })
      });
      if (!resp.ok) { const e = await resp.json(); throw new Error(e.detail || "Unknown error"); }
      const data = await resp.json();
      box.innerHTML = marked.parse(data.report);
      setStatus("done", "COMPLETE");
    } catch (e) {
      box.innerHTML = `<div style="color:var(--danger)">❌ Error: ${e.message}</div>`;
      setStatus("error", "ERROR");
    } finally {
      btn.disabled = false;
      document.getElementById("btn-text").textContent = "⚡ Harvest Signals";
    }
  }
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


@app.post("/harvest")
async def harvest(request: Request):
    body = await request.json()
    business_type = body.get("business_type", "").strip()
    sector = body.get("sector", "").strip()
    risk_horizon = body.get("risk_horizon", "24h").strip()
    specific_concern = body.get("specific_concern", "").strip()

    if not business_type or not sector:
        return JSONResponse(status_code=422, content={"detail": "business_type and sector are required"})

    logger.info(f"Harvest request: sector={sector}, horizon={risk_horizon}")
    try:
        from agent import run_signal_harvester
        report = run_signal_harvester(business_type, sector, risk_horizon, specific_concern)
        logger.info("Harvest completed successfully")
        return {"report": report}
    except Exception as e:
        logger.error(f"Harvest error: {str(e)}")
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "signal-harvester"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 3003))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
