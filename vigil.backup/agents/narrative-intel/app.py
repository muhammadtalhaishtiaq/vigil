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
logger = logging.getLogger("narrative-intel")

app = FastAPI(title="Narrative Intel", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Narrative Intel — Vigil Intelligence</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  :root {
    --bg: #0a0816;
    --surface: #100c1f;
    --surface2: #1a1332;
    --border: #2d1f5e;
    --accent: #a78bfa;
    --accent2: #7c3aed;
    --text: #e2e8f0;
    --muted: #64748b;
    --success: #10b981;
    --danger: #ef4444;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }

  header {
    background: linear-gradient(135deg, #0a0816 0%, #100c1f 100%);
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
    max-width: 1100px; margin: 0 auto; padding: 40px 24px;
    display: grid; grid-template-columns: 360px 1fr; gap: 28px; align-items: start;
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
    color: var(--muted); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 7px;
  }
  textarea {
    width: 100%; background: var(--surface2); border: 1px solid var(--border);
    border-radius: 10px; padding: 11px 14px; color: var(--text);
    font-size: 0.88rem; transition: border .2s; outline: none; resize: vertical; min-height: 260px;
    font-family: 'Segoe UI', system-ui, sans-serif;
  }
  textarea:focus { border-color: var(--accent); }

  .hint {
    font-size: 0.75rem; color: var(--muted); margin-top: 6px;
    padding: 8px 12px; background: var(--surface2); border-radius: 8px;
    border-left: 3px solid var(--accent2);
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
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px;
  }
  #status-badge {
    font-size: 0.75rem; padding: 4px 12px; border-radius: 20px; font-weight: 600;
  }
  .badge-idle { background: var(--surface2); color: var(--muted); }
  .badge-running { background: #1c1240; color: var(--accent); animation: pulse 1.5s infinite; }
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
    margin: 20px 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--border);
  }
  #output-box h2:first-child { margin-top: 0; }
  #output-box strong { color: #c4b5fd; }
  #output-box ul, #output-box ol { padding-left: 18px; margin: 8px 0; }
  #output-box li { margin: 4px 0; }
  #output-box hr { border-color: var(--border); margin: 16px 0; }
  #output-box p { margin: 6px 0; }
  #output-box code { background: #1e1040; padding: 2px 6px; border-radius: 4px; font-size: 0.85rem; }
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
  <div class="logo">🧠</div>
  <div>
    <h1>Narrative Intel <span>by Vigil</span></h1>
  </div>
</header>

<div class="container">
  <div class="panel">
    <h2>📥 Signal Harvester Input</h2>
    <div class="field">
      <label>Paste Signal Harvest Report</label>
      <textarea id="signal_report" placeholder="Paste the full output from Signal Harvester here…"></textarea>
      <div class="hint">💡 Run Signal Harvester first, then paste the full report here to get the narrative analysis.</div>
    </div>
    <button class="btn-submit" id="submit-btn" onclick="analyze()">
      <span id="btn-text">🧠 Analyze Narratives</span>
    </button>
  </div>

  <div class="panel output-panel">
    <div class="output-header">
      <h2 style="margin:0">🧠 Narrative Intelligence Report</h2>
      <span id="status-badge" class="badge-idle">IDLE</span>
    </div>
    <div id="output-box" class="empty">
      <div class="empty-icon">🧠</div>
      <div>Paste a Signal Harvest report and hit <strong>Analyze Narratives</strong></div>
    </div>
  </div>
</div>

<script>
  async function analyze() {
    const signal_report = document.getElementById("signal_report").value.trim();
    if (!signal_report) { alert("Please paste a Signal Harvest report."); return; }

    const btn = document.getElementById("submit-btn");
    const box = document.getElementById("output-box");
    btn.disabled = true;
    document.getElementById("btn-text").textContent = "Analyzing…";

    const badge = document.getElementById("status-badge");
    badge.className = "badge-running"; badge.textContent = "ANALYZING";
    box.classList.remove("empty");
    box.innerHTML = '<div class="spinner"></div>';

    try {
      const resp = await fetch("/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ signal_report })
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
      document.getElementById("btn-text").textContent = "🧠 Analyze Narratives";
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
    signal_report = body.get("signal_report", "").strip()

    if not signal_report:
        return JSONResponse(status_code=422, content={"detail": "signal_report is required"})

    logger.info("Narrative Intel: processing signal report")
    try:
        from agent import run_narrative_intel
        report = run_narrative_intel(signal_report)
        logger.info("Narrative Intel complete")
        return {"report": report}
    except Exception as e:
        logger.error(f"Narrative Intel error: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "narrative-intel"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 3004))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
