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
logger = logging.getLogger("market-oracle")

app = FastAPI(title="Market Oracle", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Market Oracle — Vigil Intelligence</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  :root {
    --bg: #06040f;
    --surface: #0e0a1e;
    --surface2: #160f2e;
    --surface3: #1e1540;
    --border: #2e1f6e;
    --accent: #c084fc;
    --accent2: #9333ea;
    --accent3: #e879f9;
    --gold: #fbbf24;
    --text: #ede9fe;
    --muted: #6b5a8a;
    --success: #10b981;
    --danger: #f87171;
    --warn: #fb923c;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }

  /* ── Stars bg ── */
  body::before {
    content: '';
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background-image:
      radial-gradient(1px 1px at 20% 30%, rgba(192,132,252,0.3) 0%, transparent 100%),
      radial-gradient(1px 1px at 80% 10%, rgba(232,121,249,0.2) 0%, transparent 100%),
      radial-gradient(1px 1px at 50% 70%, rgba(192,132,252,0.2) 0%, transparent 100%),
      radial-gradient(1px 1px at 10% 85%, rgba(147,51,234,0.15) 0%, transparent 100%),
      radial-gradient(1px 1px at 90% 55%, rgba(232,121,249,0.15) 0%, transparent 100%);
    pointer-events: none; z-index: 0;
  }

  /* ── Header ── */
  header {
    position: relative; z-index: 1;
    background: linear-gradient(135deg, rgba(6,4,15,0.95) 0%, rgba(14,10,30,0.95) 100%);
    border-bottom: 1px solid var(--border);
    padding: 20px 40px; display: flex; align-items: center; gap: 16px;
    backdrop-filter: blur(10px);
  }
  .logo {
    width: 48px; height: 48px;
    background: linear-gradient(135deg, var(--accent2), var(--accent3));
    border-radius: 50%; display: flex; align-items: center; justify-content: center;
    font-size: 24px; box-shadow: 0 0 20px rgba(147,51,234,0.5);
  }
  .header-text h1 {
    font-size: 1.5rem; font-weight: 800;
    background: linear-gradient(90deg, var(--accent), var(--accent3));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  .header-text p { font-size: 0.73rem; color: var(--muted); margin-top: 2px; }
  .header-badge {
    margin-left: auto; font-size: 0.68rem; font-weight: 700;
    color: var(--accent); background: rgba(192,132,252,0.1);
    border: 1px solid var(--border); padding: 5px 14px;
    border-radius: 20px; text-transform: uppercase; letter-spacing: .08em;
  }

  /* ── Layout ── */
  .layout {
    position: relative; z-index: 1;
    max-width: 1200px; margin: 0 auto; padding: 32px 24px;
    display: grid; grid-template-columns: 380px 1fr; gap: 24px; align-items: start;
  }
  @media (max-width: 960px) { .layout { grid-template-columns: 1fr; } }

  /* ── Panel ── */
  .panel {
    background: rgba(14,10,30,0.9); border: 1px solid var(--border);
    border-radius: 16px; padding: 24px;
    backdrop-filter: blur(8px);
  }
  .panel-title {
    font-size: 0.75rem; font-weight: 800; text-transform: uppercase;
    letter-spacing: .09em; color: var(--accent);
    margin-bottom: 18px; display: flex; align-items: center; gap: 8px;
  }

  /* ── Quick questions ── */
  .quick-label {
    font-size: 0.68rem; font-weight: 700; color: var(--muted);
    text-transform: uppercase; letter-spacing: .07em; margin-bottom: 10px;
  }
  .quick-chips {
    display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 18px;
  }
  .chip {
    font-size: 0.72rem; padding: 5px 11px;
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 20px; cursor: pointer; color: var(--muted);
    transition: all .2s;
  }
  .chip:hover {
    background: var(--surface3); color: var(--accent); border-color: var(--accent2);
  }

  /* ── Fields ── */
  .field { margin-bottom: 14px; }
  label {
    display: block; font-size: 0.7rem; font-weight: 600;
    color: var(--muted); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 6px;
  }
  textarea, input {
    width: 100%; background: var(--surface2); border: 1px solid var(--border);
    border-radius: 10px; padding: 11px 14px; color: var(--text);
    font-size: 0.88rem; transition: border .2s; outline: none; font-family: inherit; resize: vertical;
  }
  textarea:focus, input:focus { border-color: var(--accent); box-shadow: 0 0 12px rgba(192,132,252,0.15); }

  /* ── Signal toggle ── */
  .signal-toggle {
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 10px; cursor: pointer;
  }
  .toggle-switch {
    width: 36px; height: 20px; background: var(--surface3); border: 1px solid var(--border);
    border-radius: 10px; position: relative; transition: background .2s;
  }
  .toggle-switch.on { background: var(--accent2); border-color: var(--accent2); }
  .toggle-knob {
    position: absolute; top: 2px; left: 2px;
    width: 14px; height: 14px; border-radius: 50%;
    background: var(--muted); transition: all .2s;
  }
  .toggle-switch.on .toggle-knob { left: 18px; background: white; }
  .toggle-label { font-size: 0.75rem; color: var(--muted); }
  .toggle-label.on { color: var(--accent); }

  /* ── Submit ── */
  .btn-oracle {
    width: 100%; padding: 14px;
    background: linear-gradient(135deg, var(--accent2), var(--accent3));
    border: none; border-radius: 12px;
    color: white; font-size: 1rem; font-weight: 800;
    cursor: pointer; margin-top: 6px; transition: all .2s;
    display: flex; align-items: center; justify-content: center; gap: 10px;
    box-shadow: 0 0 24px rgba(147,51,234,0.3);
  }
  .btn-oracle:hover { opacity: .9; box-shadow: 0 0 36px rgba(147,51,234,0.5); transform: translateY(-1px); }
  .btn-oracle:disabled { opacity: .35; cursor: not-allowed; box-shadow: none; transform: none; }

  /* ── Output panel ── */
  .output-panel {
    background: rgba(14,10,30,0.9); border: 1px solid var(--border);
    border-radius: 16px; display: flex; flex-direction: column;
    min-height: 580px; backdrop-filter: blur(8px);
  }
  .output-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 16px 22px; border-bottom: 1px solid var(--border);
    background: rgba(192,132,252,0.04); border-radius: 16px 16px 0 0;
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
  .badge-running { background: #1e0a3d; color: var(--accent); animation: pulse 1.4s infinite; }
  .badge-done { background: #064e3b; color: var(--success); }
  .badge-error { background: #3d0015; color: var(--danger); }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

  #output-box {
    flex: 1; padding: 26px; font-size: 0.9rem; line-height: 1.78;
    overflow-y: auto; max-height: 82vh;
  }
  #output-box.empty {
    display: flex; align-items: center; justify-content: center;
    color: var(--muted); flex-direction: column; gap: 16px; text-align: center;
  }
  .empty-crystal { font-size: 4rem; filter: drop-shadow(0 0 20px rgba(192,132,252,0.5)); }
  .empty-title { font-size: 1rem; font-weight: 700; color: var(--accent); }
  .empty-sub { font-size: 0.8rem; max-width: 280px; line-height: 1.65; }

  /* ── Markdown ── */
  #output-box h2 {
    color: var(--accent); font-size: 0.95rem;
    margin: 22px 0 10px; padding-bottom: 6px;
    border-bottom: 1px solid var(--border);
  }
  #output-box h2:first-child { margin-top: 0; }
  #output-box h3 { font-size: 0.9rem; color: var(--accent3); margin: 14px 0 7px; }
  #output-box strong { color: #d8b4fe; }
  #output-box em { color: var(--muted); font-style: italic; }
  #output-box blockquote {
    border-left: 3px solid var(--accent2);
    padding: 10px 16px; margin: 14px 0;
    background: rgba(147,51,234,0.08); border-radius: 0 8px 8px 0;
    font-style: italic; color: var(--text); font-size: 0.92rem;
  }
  #output-box ul, #output-box ol { padding-left: 20px; margin: 8px 0; }
  #output-box li { margin: 6px 0; }
  #output-box hr { border-color: var(--border); margin: 18px 0; }
  #output-box p { margin: 7px 0; }
  #output-box code {
    background: var(--surface3); padding: 2px 7px;
    border-radius: 4px; font-size: 0.82rem; color: var(--accent);
  }

  /* ── Verdict pills ── */
  .verdict-pill {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 6px 14px; border-radius: 20px; font-weight: 800; font-size: 0.85rem;
    margin: 8px 0;
  }
  .verdict-buy { background: rgba(16,185,129,0.15); color: #34d399; border: 1px solid #065f46; }
  .verdict-wait { background: rgba(251,191,36,0.15); color: #fbbf24; border: 1px solid #92400e; }
  .verdict-caution { background: rgba(251,146,60,0.15); color: #fb923c; border: 1px solid #7c2d12; }
  .verdict-avoid { background: rgba(248,113,113,0.15); color: #f87171; border: 1px solid #7f1d1d; }

  .spinner {
    width: 44px; height: 44px;
    border: 3px solid var(--border); border-top-color: var(--accent);
    border-radius: 50%; animation: spin 0.75s linear infinite; margin: 80px auto;
    box-shadow: 0 0 20px rgba(192,132,252,0.2);
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .divider { border: none; border-top: 1px solid var(--border); margin: 16px 0; }
</style>
</head>
<body>

<header>
  <div class="logo">🔮</div>
  <div class="header-text">
    <h1>Market Oracle</h1>
    <p>Personal Investment Intelligence — Vigil</p>
  </div>
  <div class="header-badge">Plain English · No Hype</div>
</header>

<div class="layout">

  <!-- LEFT: Input -->
  <div style="display:flex;flex-direction:column;gap:18px;">

    <div class="panel">
      <div class="panel-title">🔮 Ask the Oracle</div>

      <div class="quick-label">Quick questions</div>
      <div class="quick-chips">
        <div class="chip" onclick="setQuestion('Should I buy stocks right now?')">Buy stocks now?</div>
        <div class="chip" onclick="setQuestion('Is the NASDAQ overvalued?')">NASDAQ overvalued?</div>
        <div class="chip" onclick="setQuestion('Should I buy gold or stocks?')">Gold vs stocks?</div>
        <div class="chip" onclick="setQuestion('Is crypto a good investment right now?')">Crypto now?</div>
        <div class="chip" onclick="setQuestion('Should I invest now or wait for a dip?')">Now or wait?</div>
        <div class="chip" onclick="setQuestion('What happens to my savings in a recession?')">Recession impact?</div>
      </div>

      <div class="field">
        <label>Your Question</label>
        <textarea id="user_question" style="min-height:90px" placeholder="Ask anything — e.g. 'Should I buy Apple stock right now?' or 'Is it a bad time to invest?'"></textarea>
      </div>

      <hr class="divider"/>

      <!-- Signal Harvester toggle -->
      <div class="signal-toggle" onclick="toggleSignal()">
        <div class="toggle-switch" id="signal-switch">
          <div class="toggle-knob"></div>
        </div>
        <span class="toggle-label" id="signal-label">Add Signal Harvester data (optional)</span>
      </div>

      <div id="signal-area" style="display:none;">
        <div class="field" style="margin-top:10px;">
          <label>Signal Harvester Report</label>
          <textarea id="signal_report" style="min-height:140px" placeholder="Paste Signal Harvester output here to ground the Oracle in live market data…"></textarea>
        </div>
      </div>

      <button class="btn-oracle" id="submit-btn" onclick="askOracle()">
        <span id="btn-text">🔮 Consult the Oracle</span>
      </button>
    </div>

    <!-- Info card -->
    <div class="panel" style="padding:18px;">
      <div style="font-size:0.72rem;color:var(--muted);line-height:1.7;">
        <div style="color:var(--accent);font-weight:700;margin-bottom:8px;font-size:0.78rem;">ℹ️ How it works</div>
        Market Oracle gives you a direct, honest market perspective in plain English — no broker jargon, no vague answers. Pair it with a Signal Harvester report for data-grounded responses, or ask on its own for a knowledge-based view.
        <div style="margin-top:8px;color:#4a3a60;">⚠️ Market intelligence only — not certified financial advice.</div>
      </div>
    </div>

  </div>

  <!-- RIGHT: Output -->
  <div class="output-panel">
    <div class="output-header">
      <div class="output-title">🔮 Oracle Reading</div>
      <span id="status-badge" class="badge-idle">IDLE</span>
    </div>
    <div id="output-box" class="empty">
      <div class="empty-crystal">🔮</div>
      <div class="empty-title">The Oracle Awaits</div>
      <div class="empty-sub">Ask any investment question — plain language, direct answer, no nonsense.</div>
    </div>
  </div>

</div>

<script>
  let signalOn = false;

  function setQuestion(q) {
    document.getElementById("user_question").value = q;
    document.getElementById("user_question").focus();
  }

  function toggleSignal() {
    signalOn = !signalOn;
    const sw = document.getElementById("signal-switch");
    const lbl = document.getElementById("signal-label");
    const area = document.getElementById("signal-area");
    sw.classList.toggle("on", signalOn);
    lbl.classList.toggle("on", signalOn);
    lbl.textContent = signalOn ? "Signal Harvester data enabled ✓" : "Add Signal Harvester data (optional)";
    area.style.display = signalOn ? "block" : "none";
  }

  async function askOracle() {
    const user_question = document.getElementById("user_question").value.trim();
    if (!user_question) { alert("Please enter your question."); return; }

    const signal_report = signalOn ? document.getElementById("signal_report").value.trim() : "";

    const btn = document.getElementById("submit-btn");
    const box = document.getElementById("output-box");
    btn.disabled = true;
    document.getElementById("btn-text").textContent = "Consulting…";

    const badge = document.getElementById("status-badge");
    badge.className = "badge-running"; badge.textContent = "READING";
    box.classList.remove("empty");
    box.innerHTML = '<div class="spinner"></div>';

    try {
      const resp = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_question, signal_report })
      });
      if (!resp.ok) { const e = await resp.json(); throw new Error(e.detail || "Unknown error"); }
      const data = await resp.json();
      box.innerHTML = marked.parse(data.answer);
      badge.className = "badge-done"; badge.textContent = "READING COMPLETE";
    } catch (e) {
      box.innerHTML = `<div style="color:var(--danger);padding:20px">❌ Error: ${e.message}</div>`;
      badge.className = "badge-error"; badge.textContent = "ERROR";
    } finally {
      btn.disabled = false;
      document.getElementById("btn-text").textContent = "🔮 Consult the Oracle";
    }
  }

  // Enter key support
  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("user_question").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) askOracle();
    });
  });
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


@app.post("/ask")
async def ask(request: Request):
    body = await request.json()
    user_question = body.get("user_question", "").strip()
    signal_report = body.get("signal_report", "").strip()

    if not user_question:
        return JSONResponse(status_code=422, content={"detail": "user_question is required"})

    logger.info(f"Market Oracle: question='{user_question[:80]}…'")
    try:
        from agent import run_market_oracle
        answer = run_market_oracle(user_question, signal_report)
        logger.info("Market Oracle complete")
        return {"answer": answer}
    except Exception as e:
        logger.error(f"Market Oracle error: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "market-oracle"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 3009))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
