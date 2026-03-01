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
logger = logging.getLogger("competitive-intel")

app = FastAPI(title="Competitive Intel", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Competitive Intel — Vigil Intelligence</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  :root {
    --bg: #000d0a;
    --surface: #001a14;
    --surface2: #002519;
    --border: #00422d;
    --accent: #00e5a0;
    --accent2: #00b87a;
    --accent3: #ef4444;
    --text: #e2e8f0;
    --muted: #5a7a6e;
    --success: #10b981;
    --danger: #ef4444;
    --warning: #f59e0b;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }

  header {
    background: linear-gradient(135deg, #000d0a 0%, #001a14 100%);
    border-bottom: 1px solid var(--border);
    padding: 20px 40px; display: flex; align-items: center; gap: 16px;
  }
  .logo {
    width: 44px; height: 44px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 22px;
  }
  header h1 {
    font-size: 1.5rem; font-weight: 700;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  header span { font-size: 0.8rem; color: var(--muted); margin-left: 4px; }

  .container {
    max-width: 1200px; margin: 0 auto;
    padding: 36px 24px;
    display: grid; grid-template-columns: 380px 1fr;
    gap: 28px; align-items: start;
  }
  @media (max-width: 900px) { .container { grid-template-columns: 1fr; } }

  .panel {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 16px; padding: 26px;
  }
  .panel h2 {
    font-size: 0.9rem; font-weight: 700; color: var(--accent);
    text-transform: uppercase; letter-spacing: .07em;
    margin-bottom: 20px; display: flex; align-items: center; gap: 8px;
  }

  .section-label {
    font-size: 0.68rem; font-weight: 700; color: var(--muted);
    text-transform: uppercase; letter-spacing: .08em;
    margin: 18px 0 10px; padding-bottom: 6px;
    border-bottom: 1px solid var(--border);
  }
  .section-label:first-of-type { margin-top: 0; }

  .field { margin-bottom: 14px; }
  label {
    display: block; font-size: 0.72rem; font-weight: 600;
    color: var(--muted); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 6px;
  }
  input, textarea {
    width: 100%; background: var(--surface2);
    border: 1px solid var(--border); border-radius: 9px;
    padding: 10px 13px; color: var(--text);
    font-size: 0.88rem; transition: border .2s; outline: none;
    font-family: inherit;
  }
  input:focus, textarea:focus { border-color: var(--accent); }
  textarea { resize: vertical; }

  .horizon-group { display: flex; gap: 6px; }
  .horizon-btn {
    flex: 1; padding: 8px 0;
    border: 1px solid var(--border); background: var(--surface2);
    color: var(--muted); border-radius: 7px;
    font-size: 0.82rem; cursor: pointer; transition: all .2s; text-align: center;
  }
  .horizon-btn.active {
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-color: transparent; color: #000d0a; font-weight: 700;
  }

  .hint {
    font-size: 0.73rem; color: var(--muted); margin-top: 6px;
    padding: 7px 11px; background: var(--surface2); border-radius: 7px;
    border-left: 3px solid var(--accent2);
  }

  .btn-submit {
    width: 100%; padding: 14px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border: none; border-radius: 10px;
    color: #000d0a; font-size: 1rem; font-weight: 800;
    cursor: pointer; margin-top: 10px; transition: opacity .2s;
    display: flex; align-items: center; justify-content: center; gap: 8px;
  }
  .btn-submit:hover { opacity: .88; }
  .btn-submit:disabled { opacity: .4; cursor: not-allowed; }

  .output-panel { min-height: 500px; }
  .output-header {
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px;
  }
  #status-badge {
    font-size: 0.75rem; padding: 4px 12px; border-radius: 20px; font-weight: 700;
  }
  .badge-idle { background: var(--surface2); color: var(--muted); }
  .badge-running { background: #002519; color: var(--accent); animation: pulse 1.5s infinite; }
  .badge-done { background: #064e3b; color: var(--success); }
  .badge-error { background: #450a0a; color: var(--danger); }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }

  #output-box {
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 12px; padding: 24px;
    min-height: 440px; font-size: 0.88rem; line-height: 1.75;
    overflow-y: auto; max-height: 78vh;
  }
  #output-box.empty {
    display: flex; align-items: center; justify-content: center;
    color: var(--muted); flex-direction: column; gap: 12px;
  }
  .empty-icon { font-size: 3rem; }

  /* ── Markdown ── */
  #output-box h2 {
    color: var(--accent); font-size: 0.97rem;
    margin: 22px 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--border);
  }
  #output-box h3 { font-size: 0.9rem; margin: 16px 0 8px; color: #6ee7b7; }
  #output-box h2:first-child { margin-top: 0; }
  #output-box strong { color: #6ee7b7; }
  #output-box ul, #output-box ol { padding-left: 18px; margin: 8px 0; }
  #output-box li { margin: 5px 0; }
  #output-box hr { border-color: var(--border); margin: 16px 0; }
  #output-box p { margin: 6px 0; }
  #output-box table {
    width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 0.84rem;
  }
  #output-box th {
    background: #003d2b; color: var(--accent);
    padding: 8px 12px; text-align: left; border: 1px solid var(--border);
    font-size: 0.78rem; text-transform: uppercase; letter-spacing: .05em;
  }
  #output-box td {
    padding: 8px 12px; border: 1px solid var(--border); vertical-align: top;
  }
  #output-box tr:nth-child(even) td { background: #001f16; }
  #output-box code {
    background: #001a14; padding: 2px 6px;
    border-radius: 4px; font-size: 0.83rem; color: var(--accent);
  }

  .spinner {
    width: 40px; height: 40px;
    border: 3px solid var(--border); border-top-color: var(--accent);
    border-radius: 50%; animation: spin 0.8s linear infinite; margin: 70px auto;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<header>
  <div class="logo">🎯</div>
  <div>
    <h1>Competitive Intel <span>by Vigil</span></h1>
  </div>
</header>

<div class="container">

  <!-- Input Panel -->
  <div class="panel">
    <h2>📥 Input</h2>

    <div class="section-label">Business Context</div>

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

    <div class="section-label" style="margin-top:20px">Signal Harvest Report</div>

    <div class="field">
      <label>Paste Report</label>
      <textarea id="signal_report" style="min-height:200px" placeholder="Paste the full output from Signal Harvester here…"></textarea>
      <div class="hint">💡 Run Signal Harvester first, then paste the full report here.</div>
    </div>

    <button class="btn-submit" id="submit-btn" onclick="analyze()">
      <span id="btn-text">🎯 Scan Battlefield</span>
    </button>
  </div>

  <!-- Output Panel -->
  <div class="panel output-panel">
    <div class="output-header">
      <h2 style="margin:0; color: var(--accent); font-size:1rem;">🎯 Competitive Intelligence Report</h2>
      <span id="status-badge" class="badge-idle">IDLE</span>
    </div>
    <div id="output-box" class="empty">
      <div class="empty-icon">🎯</div>
      <div>Fill in context + paste Signal Harvest report, then hit <strong>Scan Battlefield</strong></div>
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

  async function analyze() {
    const business_type = document.getElementById("business_type").value.trim();
    const sector = document.getElementById("sector").value.trim();
    const signal_report = document.getElementById("signal_report").value.trim();

    if (!business_type || !sector) { alert("Please fill in Business Type and Sector."); return; }
    if (!signal_report) { alert("Please paste the Signal Harvest report."); return; }

    const btn = document.getElementById("submit-btn");
    const box = document.getElementById("output-box");
    btn.disabled = true;
    document.getElementById("btn-text").textContent = "Scanning…";

    const badge = document.getElementById("status-badge");
    badge.className = "badge-running"; badge.textContent = "SCANNING";
    box.classList.remove("empty");
    box.innerHTML = '<div class="spinner"></div>';

    try {
      const resp = await fetch("/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ business_type, sector, risk_horizon: selectedHorizon, signal_report })
      });
      if (!resp.ok) { const e = await resp.json(); throw new Error(e.detail || "Unknown error"); }
      const data = await resp.json();
      box.innerHTML = marked.parse(data.report);
      badge.className = "badge-done"; badge.textContent = "COMPLETE";
    } catch (e) {
      box.innerHTML = `<div style="color:var(--danger)">❌ Error: ${e.message}</div>`;
      badge.className = "badge-error"; badge.textContent = "ERROR";
    } finally {
      btn.disabled = false;
      document.getElementById("btn-text").textContent = "🎯 Scan Battlefield";
    }
  }
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


@app.post("/analyze")
async def analyze(request: Request):
    body = await request.json()
    business_type = body.get("business_type", "").strip()
    sector = body.get("sector", "").strip()
    risk_horizon = body.get("risk_horizon", "24h").strip()
    signal_report = body.get("signal_report", "").strip()

    if not business_type or not sector:
        return JSONResponse(status_code=422, content={"detail": "business_type and sector are required"})
    if not signal_report:
        return JSONResponse(status_code=422, content={"detail": "signal_report is required"})

    logger.info(f"Competitive Intel: sector={sector}, horizon={risk_horizon}")
    try:
        from agent import run_competitive_intel
        report = run_competitive_intel(signal_report, business_type, sector, risk_horizon)
        logger.info("Competitive Intel complete")
        return {"report": report}
    except Exception as e:
        logger.error(f"Competitive Intel error: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "competitive-intel"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 3006))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
