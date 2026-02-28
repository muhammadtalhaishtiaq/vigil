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
logger = logging.getLogger("vigil-orchestrator")

app = FastAPI(title="Vigil Orchestrator", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Vigil — Financial Risk Intelligence</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  :root {
    --bg: #050709;
    --surface: #0a0d12;
    --surface2: #0f1419;
    --surface3: #141c26;
    --border: #1a2a3a;
    --border2: #1e3550;
    --accent: #00b4d8;
    --accent2: #0077b6;
    --accent3: #48cae4;
    --gold: #ffd166;
    --red: #ef233c;
    --green: #06d6a0;
    --text: #ccd6f6;
    --text2: #8892b0;
    --muted: #4a5568;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: var(--bg); color: var(--text);
    display: flex; flex-direction: column; height: 100vh; overflow: hidden;
  }

  /* ── Header ── */
  header {
    flex-shrink: 0;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 0 28px;
    height: 58px;
    display: flex; align-items: center; justify-content: space-between;
    position: relative;
  }
  header::after {
    content: '';
    position: absolute; bottom: 0; left: 0; right: 0; height: 1px;
    background: linear-gradient(90deg, transparent, var(--accent2), var(--accent), transparent);
  }
  .header-left { display: flex; align-items: center; gap: 12px; }
  .vigil-logo {
    display: flex; align-items: center; gap: 10px;
  }
  .logo-mark {
    width: 32px; height: 32px;
    background: linear-gradient(135deg, var(--accent2), var(--accent));
    border-radius: 7px;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px; font-weight: 900; color: white;
  }
  .logo-text {
    font-size: 1.1rem; font-weight: 800; letter-spacing: .08em;
    background: linear-gradient(90deg, var(--accent3), var(--accent));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  .logo-sub { font-size: 0.65rem; color: var(--muted); margin-top: 1px; }
  .header-right { display: flex; align-items: center; gap: 10px; }
  .status-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--green); box-shadow: 0 0 6px var(--green);
    animation: blink 2s infinite;
  }
  @keyframes blink { 0%,100%{opacity:1} 50%{opacity:.4} }
  .status-txt { font-size: 0.68rem; color: var(--muted); letter-spacing: .06em; }
  .agent-count {
    font-size: 0.65rem; background: var(--surface3); border: 1px solid var(--border2);
    color: var(--accent); padding: 3px 10px; border-radius: 12px; font-weight: 700;
  }

  /* ── Agent pipeline bar ── */
  .pipeline-bar {
    flex-shrink: 0;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 8px 28px;
    display: flex; align-items: center; gap: 6px; overflow-x: auto;
    scrollbar-width: none;
  }
  .pipeline-bar::-webkit-scrollbar { display: none; }
  .pipe-label { font-size: 0.62rem; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; white-space: nowrap; margin-right: 4px; }
  .pipe-agent {
    font-size: 0.65rem; font-weight: 700; padding: 3px 10px;
    border-radius: 12px; white-space: nowrap; border: 1px solid var(--border);
    color: var(--muted); background: var(--surface2); transition: all .3s;
  }
  .pipe-agent.active { border-color: var(--accent2); color: var(--accent3); background: rgba(0,119,182,0.15); animation: pulse-a 1.2s infinite; }
  .pipe-agent.done { border-color: rgba(6,214,160,0.4); color: var(--green); background: rgba(6,214,160,0.08); }
  @keyframes pulse-a { 0%,100%{opacity:1} 50%{opacity:.6} }
  .pipe-arrow { color: var(--muted); font-size: 0.6rem; }

  /* ── Chat area ── */
  .chat-area {
    flex: 1; overflow-y: auto; padding: 24px 28px;
    display: flex; flex-direction: column; gap: 20px;
  }
  .chat-area::-webkit-scrollbar { width: 4px; }
  .chat-area::-webkit-scrollbar-track { background: transparent; }
  .chat-area::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 4px; }

  /* ── Messages ── */
  .msg { display: flex; gap: 12px; max-width: 100%; }
  .msg.user { flex-direction: row-reverse; }

  .msg-avatar {
    width: 34px; height: 34px; border-radius: 8px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center; font-size: 16px;
  }
  .msg.user .msg-avatar { background: var(--surface3); border: 1px solid var(--border2); }
  .msg.assistant .msg-avatar {
    background: linear-gradient(135deg, var(--accent2), var(--accent));
    box-shadow: 0 0 12px rgba(0,180,216,0.3);
  }

  .msg-bubble {
    max-width: calc(100% - 50px); padding: 14px 18px;
    border-radius: 12px; line-height: 1.65; font-size: 0.875rem;
  }
  .msg.user .msg-bubble {
    background: var(--surface3); border: 1px solid var(--border2);
    color: var(--text); border-top-right-radius: 4px;
    margin-left: auto;
  }
  .msg.assistant .msg-bubble {
    background: var(--surface2); border: 1px solid var(--border);
    border-top-left-radius: 4px;
  }

  /* ── Markdown in bubbles ── */
  .msg-bubble h2 {
    color: var(--accent); font-size: 0.92rem; margin: 18px 0 8px;
    padding-bottom: 5px; border-bottom: 1px solid var(--border);
  }
  .msg-bubble h2:first-child { margin-top: 0; }
  .msg-bubble h3 { color: var(--accent3); font-size: 0.86rem; margin: 12px 0 6px; }
  .msg-bubble strong { color: var(--gold); }
  .msg-bubble em { color: var(--text2); }
  .msg-bubble blockquote {
    border-left: 3px solid var(--accent); padding: 8px 14px;
    margin: 10px 0; background: rgba(0,180,216,0.07);
    border-radius: 0 7px 7px 0; font-style: normal;
    color: var(--text); font-size: 0.9rem;
  }
  .msg-bubble ul, .msg-bubble ol { padding-left: 18px; margin: 7px 0; }
  .msg-bubble li { margin: 5px 0; }
  .msg-bubble hr { border-color: var(--border); margin: 14px 0; }
  .msg-bubble p { margin: 6px 0; }
  .msg-bubble code { background: var(--surface3); padding: 1px 6px; border-radius: 4px; font-size: 0.8rem; color: var(--accent3); }
  .msg-bubble table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 0.8rem; }
  .msg-bubble th { background: var(--surface3); color: var(--accent); padding: 7px 11px; text-align: left; border: 1px solid var(--border); font-size: 0.72rem; text-transform: uppercase; letter-spacing: .05em; }
  .msg-bubble td { padding: 7px 11px; border: 1px solid var(--border); vertical-align: top; }
  .msg-bubble tr:nth-child(even) td { background: rgba(255,255,255,0.02); }

  /* ── Agent tag strip ── */
  .agent-strip {
    display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 10px;
  }
  .agent-tag {
    font-size: 0.62rem; padding: 2px 8px; border-radius: 10px; font-weight: 700;
    background: rgba(0,119,182,0.15); border: 1px solid rgba(0,180,216,0.3); color: var(--accent3);
  }

  /* ── Typing indicator ── */
  .typing-indicator {
    display: flex; align-items: center; gap: 10px;
    padding: 14px 18px; background: var(--surface2);
    border: 1px solid var(--border); border-radius: 12px;
    border-top-left-radius: 4px; max-width: 320px;
  }
  .typing-dots { display: flex; gap: 4px; }
  .typing-dots span {
    width: 6px; height: 6px; background: var(--accent); border-radius: 50%;
    animation: tdot 1.2s infinite;
  }
  .typing-dots span:nth-child(2) { animation-delay: .2s; }
  .typing-dots span:nth-child(3) { animation-delay: .4s; }
  @keyframes tdot { 0%,100%{opacity:.2;transform:scale(.8)} 50%{opacity:1;transform:scale(1)} }
  .typing-status { font-size: 0.72rem; color: var(--muted); }

  /* ── Welcome ── */
  .welcome {
    text-align: center; padding: 40px 20px;
    display: flex; flex-direction: column; align-items: center; gap: 14px;
  }
  .welcome-icon { font-size: 3rem; filter: drop-shadow(0 0 16px rgba(0,180,216,0.4)); }
  .welcome-title { font-size: 1.2rem; font-weight: 800; color: var(--accent); letter-spacing: -.01em; }
  .welcome-sub { font-size: 0.82rem; color: var(--text2); max-width: 420px; line-height: 1.7; }
  .starter-grid {
    display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px;
    width: 100%; max-width: 500px; margin-top: 8px;
  }
  .starter {
    padding: 10px 14px; background: var(--surface2); border: 1px solid var(--border);
    border-radius: 10px; font-size: 0.77rem; color: var(--text2);
    cursor: pointer; transition: all .2s; text-align: left; line-height: 1.4;
  }
  .starter:hover { background: var(--surface3); border-color: var(--border2); color: var(--text); }
  .starter strong { display: block; color: var(--accent3); font-size: 0.7rem; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 3px; }

  /* ── Input bar ── */
  .input-bar {
    flex-shrink: 0;
    background: var(--surface);
    border-top: 1px solid var(--border);
    padding: 14px 28px;
  }
  .input-row {
    display: flex; align-items: flex-end; gap: 10px;
    background: var(--surface2); border: 1px solid var(--border2);
    border-radius: 12px; padding: 10px 14px;
    transition: border-color .2s;
  }
  .input-row:focus-within { border-color: var(--accent2); }
  #user-input {
    flex: 1; background: transparent; border: none; outline: none;
    color: var(--text); font-size: 0.9rem; font-family: inherit;
    resize: none; min-height: 22px; max-height: 120px;
    line-height: 1.5; padding: 1px 0;
  }
  #user-input::placeholder { color: var(--muted); }
  .send-btn {
    width: 34px; height: 34px; flex-shrink: 0;
    background: linear-gradient(135deg, var(--accent2), var(--accent));
    border: none; border-radius: 8px; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    font-size: 15px; transition: all .2s;
    box-shadow: 0 0 12px rgba(0,119,182,0.3);
  }
  .send-btn:hover { opacity: .88; transform: scale(1.05); }
  .send-btn:disabled { opacity: .3; cursor: not-allowed; transform: none; }
  .input-hint { font-size: 0.62rem; color: var(--muted); margin-top: 7px; text-align: center; }
</style>
</head>
<body>

<!-- Header -->
<header>
  <div class="header-left">
    <div class="vigil-logo">
      <div class="logo-mark">V</div>
      <div>
        <div class="logo-text">VIGIL</div>
        <div class="logo-sub">Financial Risk Intelligence</div>
      </div>
    </div>
  </div>
  <div class="header-right">
    <div class="status-dot"></div>
    <span class="status-txt">ALL SYSTEMS ONLINE</span>
    <span class="agent-count">7 AGENTS ACTIVE</span>
  </div>
</header>

<!-- Pipeline bar -->
<div class="pipeline-bar">
  <span class="pipe-label">Pipeline:</span>
  <span class="pipe-agent" id="pipe-signal">📡 Signal</span>
  <span class="pipe-arrow">›</span>
  <span class="pipe-agent" id="pipe-narrative">🧠 Narrative</span>
  <span class="pipe-arrow">›</span>
  <span class="pipe-agent" id="pipe-macro">🐕 Macro</span>
  <span class="pipe-arrow">›</span>
  <span class="pipe-agent" id="pipe-competitive">🎯 Competitive</span>
  <span class="pipe-arrow">›</span>
  <span class="pipe-agent" id="pipe-risk">⚡ Risk</span>
  <span class="pipe-arrow">›</span>
  <span class="pipe-agent" id="pipe-strategy">🎖️ Strategy</span>
  <span class="pipe-arrow">›</span>
  <span class="pipe-agent" id="pipe-oracle">🔮 Oracle</span>
</div>

<!-- Chat -->
<div class="chat-area" id="chat-area">
  <div class="welcome" id="welcome-screen">
    <div class="welcome-icon">⚡</div>
    <div class="welcome-title">Vigil is online.</div>
    <div class="welcome-sub">Tell me about your business and I'll activate the right intelligence agents. Ask anything — market risk, competitor moves, macro impact, or investment questions.</div>
    <div class="starter-grid">
      <div class="starter" onclick="sendStarter(this.dataset.q)" data-q="I run a B2B SaaS company in fintech. Give me a full risk briefing for the next 30 days."><strong>Full Briefing</strong>B2B SaaS fintech — 30-day risk analysis</div>
      <div class="starter" onclick="sendStarter(this.dataset.q)" data-q="What is the macro environment doing to my e-commerce business right now?"><strong>Macro Focus</strong>E-commerce macro impact check</div>
      <div class="starter" onclick="sendStarter(this.dataset.q)" data-q="Who has the competitive advantage in the HR software market right now?"><strong>Competitive Intel</strong>HR software battlefield scan</div>
      <div class="starter" onclick="sendStarter(this.dataset.q)" data-q="Should I buy S&P 500 index funds right now?"><strong>Investment Q&A</strong>Is now a good time to buy the S&P 500?</div>
    </div>
  </div>
</div>

<!-- Input bar -->
<div class="input-bar">
  <div class="input-row">
    <textarea id="user-input" rows="1" placeholder="Ask Vigil anything — 'Give me a full risk briefing for my SaaS company' or 'Should I buy gold right now?'"></textarea>
    <button class="send-btn" id="send-btn" onclick="sendMessage()" title="Send (Enter)">➤</button>
  </div>
  <div class="input-hint">Enter to send · Shift+Enter for new line · Vigil routes to the right agents automatically</div>
</div>

<script>
  const AGENT_MAP = {
    "Signal Harvester": "pipe-signal",
    "Narrative Intel": "pipe-narrative",
    "Macro Watchdog": "pipe-macro",
    "Competitive Intel": "pipe-competitive",
    "Risk Synthesizer": "pipe-risk",
    "Strategy Commander": "pipe-strategy",
    "Market Oracle": "pipe-oracle",
  };

  let conversationHistory = [];
  let isProcessing = false;

  function resetPipeline() {
    Object.values(AGENT_MAP).forEach(id => {
      const el = document.getElementById(id);
      if (el) { el.classList.remove("active", "done"); }
    });
  }

  function activateAgent(name) {
    const id = AGENT_MAP[name];
    if (!id) return;
    // mark previous as done
    let found = false;
    for (const [n, i] of Object.entries(AGENT_MAP)) {
      const el = document.getElementById(i);
      if (el && el.classList.contains("active") && n !== name) {
        el.classList.remove("active"); el.classList.add("done");
      }
    }
    const el = document.getElementById(id);
    if (el) el.classList.add("active");
  }

  function finishPipeline(agents) {
    Object.values(AGENT_MAP).forEach(id => {
      const el = document.getElementById(id);
      if (el) el.classList.remove("active");
    });
    agents.forEach(name => {
      const id = AGENT_MAP[name];
      if (id) {
        const el = document.getElementById(id);
        if (el) { el.classList.remove("active"); el.classList.add("done"); }
      }
    });
    // also mark signal if it was used
    if (!agents.includes("Market Oracle")) {
      document.getElementById("pipe-signal").classList.add("done");
    }
    setTimeout(resetPipeline, 4000);
  }

  function appendMessage(role, content, agents = []) {
    const welcome = document.getElementById("welcome-screen");
    if (welcome) welcome.remove();

    const chat = document.getElementById("chat-area");
    const div = document.createElement("div");
    div.className = "msg " + role;

    const avatar = document.createElement("div");
    avatar.className = "msg-avatar";
    avatar.textContent = role === "user" ? "👤" : "⚡";

    const bubble = document.createElement("div");
    bubble.className = "msg-bubble";

    if (role === "assistant" && agents.length > 0) {
      const strip = document.createElement("div");
      strip.className = "agent-strip";
      agents.forEach(a => {
        const tag = document.createElement("span");
        tag.className = "agent-tag";
        tag.textContent = a;
        strip.appendChild(tag);
      });
      bubble.appendChild(strip);
    }

    const content_div = document.createElement("div");
    content_div.innerHTML = marked.parse(content);
    bubble.appendChild(content_div);

    div.appendChild(avatar);
    div.appendChild(bubble);
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
  }

  function showTyping(statusText = "Activating agents…") {
    const welcome = document.getElementById("welcome-screen");
    if (welcome) welcome.remove();

    const chat = document.getElementById("chat-area");
    const div = document.createElement("div");
    div.className = "msg assistant";
    div.id = "typing-msg";

    const avatar = document.createElement("div");
    avatar.className = "msg-avatar";
    avatar.textContent = "⚡";

    const bubble = document.createElement("div");
    bubble.className = "typing-indicator";
    bubble.innerHTML = `
      <div class="typing-dots"><span></span><span></span><span></span></div>
      <span class="typing-status" id="typing-status">${statusText}</span>
    `;

    div.appendChild(avatar);
    div.appendChild(bubble);
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
  }

  function updateTypingStatus(text) {
    const el = document.getElementById("typing-status");
    if (el) el.textContent = text;
  }

  function removeTyping() {
    const el = document.getElementById("typing-msg");
    if (el) el.remove();
  }

  async function sendMessage() {
    if (isProcessing) return;
    const input = document.getElementById("user-input");
    const msg = input.value.trim();
    if (!msg) return;

    input.value = "";
    input.style.height = "auto";
    isProcessing = true;
    document.getElementById("send-btn").disabled = true;

    appendMessage("user", msg);
    conversationHistory.push({ role: "user", content: msg });

    resetPipeline();
    showTyping("Parsing your query…");

    // Simulate pipeline activation steps
    const pipelineSteps = [
      { delay: 600,  status: "Activating Signal Harvester…", agent: "Signal Harvester" },
      { delay: 3000, status: "Running intelligence pipeline…", agent: null },
      { delay: 6000, status: "Synthesizing results…", agent: null },
    ];
    let stepTimeout;
    let stepIdx = 0;
    function runStep() {
      if (stepIdx < pipelineSteps.length) {
        const step = pipelineSteps[stepIdx++];
        stepTimeout = setTimeout(() => {
          updateTypingStatus(step.status);
          if (step.agent) activateAgent(step.agent);
          runStep();
        }, step.delay);
      }
    }
    runStep();

    try {
      const resp = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg, history: conversationHistory.slice(0, -1) })
      });

      clearTimeout(stepTimeout);

      if (!resp.ok) { const e = await resp.json(); throw new Error(e.detail || "Unknown error"); }
      const data = await resp.json();

      removeTyping();
      finishPipeline(data.activated_agents || []);
      appendMessage("assistant", data.response, data.activated_agents || []);
      conversationHistory.push({ role: "assistant", content: data.response });

    } catch (e) {
      clearTimeout(stepTimeout);
      removeTyping();
      resetPipeline();
      appendMessage("assistant", `❌ **Error:** ${e.message}`);
    } finally {
      isProcessing = false;
      document.getElementById("send-btn").disabled = false;
      input.focus();
    }
  }

  function sendStarter(q) {
    const input = document.getElementById("user-input");
    input.value = q;
    sendMessage();
  }

  // Auto-resize textarea
  document.addEventListener("DOMContentLoaded", () => {
    const ta = document.getElementById("user-input");
    ta.addEventListener("input", () => {
      ta.style.height = "auto";
      ta.style.height = Math.min(ta.scrollHeight, 120) + "px";
    });
    ta.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
  });
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    message = body.get("message", "").strip()
    history = body.get("history", [])

    if not message:
        return JSONResponse(status_code=422, content={"detail": "message is required"})

    logger.info(f"Orchestrator: message='{message[:80]}'")
    try:
        from agent import run_orchestrator
        result = run_orchestrator(message, history)
        logger.info(f"Orchestrator complete: intent={result.get('intent')}, agents={result.get('activated_agents')}")
        return result
    except Exception as e:
        logger.error(f"Orchestrator error: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "vigil-orchestrator"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 3010))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
