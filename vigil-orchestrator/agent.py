import os
import json
import requests
from datetime import datetime, timezone
from typing import TypedDict, Annotated, Literal
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from dotenv import load_dotenv

load_dotenv()

# ── Sub-agent base URLs ──────────────────────────────────────────────────────
SIGNAL_URL     = "http://localhost:3003/harvest"
NARRATIVE_URL  = "http://localhost:3004/analyze"
MACRO_URL      = "http://localhost:3005/analyze"
COMPETITIVE_URL= "http://localhost:3006/analyze"
RISK_URL       = "http://localhost:3007/synthesize"
STRATEGY_URL   = "http://localhost:3008/command"
ORACLE_URL     = "http://localhost:3009/ask"

TIMEOUT = 120  # seconds per agent call

# ── Parse prompt ─────────────────────────────────────────────────────────────
PARSE_PROMPT = """You are the intent parser for Vigil, a financial risk intelligence platform.

Extract the following from the user message and return ONLY valid JSON:

{
  "business_type": "<extracted or null if not mentioned>",
  "sector": "<inferred sector or null>",
  "risk_horizon": "<24h|7d|30d|90d — infer from urgency>",
  "specific_concern": "<key concern or 'general briefing'>",
  "analysis_depth": "<quick|standard|deep>",
  "intent": "<FULL_BRIEFING|MACRO_FOCUS|COMPETITIVE_FOCUS|DECISION_SUPPORT|MARKET_PULSE|SCENARIO|INVESTMENT_QUERY>",
  "missing_business_info": <true|false>,
  "user_query": "<original message verbatim>"
}

INTENT classification rules:
- FULL_BRIEFING: "full analysis", "full briefing", "how exposed am I", "full picture", "complete analysis"
- MACRO_FOCUS: Fed, rates, inflation, recession, economy, macro
- COMPETITIVE_FOCUS: competitors, market position, who's winning, market share, competitive
- DECISION_SUPPORT: "should I hire/raise/expand/price", "is now a good time to"
- MARKET_PULSE: "quick check", "what's happening today", "fast", "brief"
- SCENARIO: "what if", "simulate", "suppose", "if X happens"
- INVESTMENT_QUERY: "should I buy", stock/ETF/crypto names, "is X a good investment", "NASDAQ", "S&P 500", "gold", "overvalued", "undervalued", any ticker symbol, "invest my savings", "invest now or wait"

RISK HORIZON inference:
- "today/now/this morning/urgent" → 24h
- "this week/next few days" → 7d
- "this month/near term" → 30d
- "strategic/long term/this quarter/this year" → 90d
- default → 30d

missing_business_info = true ONLY if intent is NOT INVESTMENT_QUERY AND business_type is completely absent."""

# ── Synthesis prompt ──────────────────────────────────────────────────────────
SYNTHESIS_PROMPT = """You are the Orchestrator of Vigil — an autonomous financial risk intelligence platform.

You receive agent outputs and format the final briefing. Format EXACTLY as shown:

---
## ⚡ Vigil
*[Business] | [Sector] | [Date/Time] | Agents activated: [comma-separated list]*

### 🔴 THE VERDICT
> [Risk Synthesizer's one-line verdict — display exactly as written, in blockquote. If no risk synthesizer output, write your own verdict based on available data.]

**RISK SCORE: [X]/100 | TIER: [EMOJI + COLOR TIER NAME]**

---

### 📋 EXECUTIVE BRIEF
[Strategy Commander's 3-sentence brief. If unavailable, write a 3-sentence brief from available data.]

---

### 🔴 TOP 3 RISKS
1. **[Risk name]** — [impact] — Probability: [X%]
2. **[Risk name]** — [impact] — Probability: [X%]
3. **[Risk name]** — [impact] — Probability: [X%]

### ✅ YOUR NEXT 3 MOVES
1. **[Action]** → Owner: [role] | Deadline: [specific]
2. **[Action]** → Owner: [role] | Deadline: [specific]
3. **[Action]** → Owner: [role] | Deadline: [specific]

---

### 📊 MARKET PULSE
[Key signal data — 4-5 bullet points max]

---

### 💬 GO DEEPER
Ask a follow-up: *"deeper on competitive"* / *"what if rates rise 50bps?"* / *"give me the full 30-day playbook"* / *"what should my CFO do this week?"*

---
*Analysis by Vigil AI agents | Powered by Complete.dev*

For INVESTMENT_QUERY: display the Market Oracle output directly (it is already well-formatted). Just prepend the ⚡ Vigil header line and append the GO DEEPER footer.
For MARKET_PULSE: keep the output to 5 bullet points maximum under MARKET PULSE. Skip NEXT 3 MOVES."""

# ── State ─────────────────────────────────────────────────────────────────────
class OrchestratorState(TypedDict):
    messages: Annotated[list, add_messages]
    user_query: str
    intent: str
    business_context: dict
    analysis_depth: str
    missing_business_info: bool
    signal_output: str
    narrative_output: str
    macro_output: str
    competitive_output: str
    risk_output: str
    strategy_output: str
    oracle_output: str
    activated_agents: list
    final_response: str


# ── LLM ──────────────────────────────────────────────────────────────────────
llm = ChatOpenAI(
    base_url="https://api.aimlapi.com/v1",
    api_key=os.getenv("AIML_API_KEY"),
    model="gpt-4o",
    temperature=0.2,
)


# ── Helper: safe HTTP call to sub-agent ──────────────────────────────────────
def call_agent(url: str, payload: dict) -> str:
    try:
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        # Each agent returns different keys
        for key in ("report", "playbook", "answer"):
            if key in data:
                return data[key]
        return str(data)
    except Exception as e:
        return f"[Agent unavailable: {str(e)}]"


# ── NODE 1: Parse intent ──────────────────────────────────────────────────────
def parse_intent(state: OrchestratorState) -> OrchestratorState:
    last_human = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), ""
    )
    response = llm.invoke([
        SystemMessage(content=PARSE_PROMPT),
        HumanMessage(content=last_human),
    ])
    try:
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
    except Exception:
        parsed = {
            "business_type": None, "sector": None, "risk_horizon": "30d",
            "specific_concern": "general briefing", "analysis_depth": "standard",
            "intent": "FULL_BRIEFING", "missing_business_info": True,
            "user_query": last_human,
        }

    return {
        **state,
        "user_query": parsed.get("user_query", last_human),
        "intent": parsed.get("intent", "FULL_BRIEFING"),
        "analysis_depth": parsed.get("analysis_depth", "standard"),
        "missing_business_info": parsed.get("missing_business_info", False),
        "business_context": {
            "business_type": parsed.get("business_type") or "general business",
            "sector": parsed.get("sector") or "General",
            "risk_horizon": parsed.get("risk_horizon", "30d"),
            "specific_concern": parsed.get("specific_concern", "general briefing"),
        },
        "signal_output": "", "narrative_output": "", "macro_output": "",
        "competitive_output": "", "risk_output": "", "strategy_output": "",
        "oracle_output": "", "activated_agents": [], "final_response": "",
    }


# ── NODE 2: Ask for missing info ──────────────────────────────────────────────
def ask_for_info(state: OrchestratorState) -> OrchestratorState:
    response = "To give you a precise risk briefing, I need one quick detail:\n\n**What type of business are you running?** (e.g. 'B2B SaaS company', 'e-commerce retailer', 'fintech startup', 'manufacturing firm')\n\nOnce you tell me, I'll activate the full Vigil pipeline."
    return {**state, "final_response": response}


# ── NODE 3: Execute agent pipeline ───────────────────────────────────────────
def execute_pipeline(state: OrchestratorState) -> OrchestratorState:
    ctx = state["business_context"]
    intent = state["intent"]
    now = datetime.now(timezone.utc).strftime("%A, %B %d, %Y — %H:%M:%S UTC")
    activated = []

    signal_out = narrative_out = macro_out = competitive_out = ""
    risk_out = strategy_out = oracle_out = ""

    # ── Signal Harvester (always first, except pure investment queries) ──
    if intent != "INVESTMENT_QUERY":
        activated.append("Signal Harvester")
        signal_out = call_agent(SIGNAL_URL, {
            "business_type": ctx["business_type"],
            "sector": ctx["sector"],
            "risk_horizon": ctx["risk_horizon"],
            "specific_concern": ctx.get("specific_concern", ""),
        })

    # ── Route based on intent ──────────────────────────────────────────────
    if intent == "INVESTMENT_QUERY":
        activated.append("Market Oracle")
        oracle_out = call_agent(ORACLE_URL, {
            "user_question": state["user_query"],
            "signal_report": signal_out,
        })

    elif intent == "MARKET_PULSE":
        activated.append("Narrative Intel")
        narrative_out = call_agent(NARRATIVE_URL, {"signal_report": signal_out})
        activated.append("Risk Synthesizer")
        risk_out = call_agent(RISK_URL, {
            "business_type": ctx["business_type"],
            "sector": ctx["sector"],
            "risk_horizon": ctx["risk_horizon"],
            "signal_report": signal_out,
            "narrative_report": narrative_out,
            "macro_report": "",
            "competitive_report": "",
        })

    elif intent == "MACRO_FOCUS":
        activated.append("Macro Watchdog")
        macro_out = call_agent(MACRO_URL, {
            "business_type": ctx["business_type"],
            "sector": ctx["sector"],
            "risk_horizon": ctx["risk_horizon"],
            "signal_report": signal_out,
        })
        activated.append("Risk Synthesizer")
        risk_out = call_agent(RISK_URL, {
            "business_type": ctx["business_type"],
            "sector": ctx["sector"],
            "risk_horizon": ctx["risk_horizon"],
            "signal_report": signal_out,
            "narrative_report": "",
            "macro_report": macro_out,
            "competitive_report": "",
        })
        activated.append("Strategy Commander")
        strategy_out = call_agent(STRATEGY_URL, {
            "business_type": ctx["business_type"],
            "sector": ctx["sector"],
            "risk_horizon": ctx["risk_horizon"],
            "risk_verdict": risk_out,
        })

    elif intent == "COMPETITIVE_FOCUS":
        activated.append("Competitive Intel")
        competitive_out = call_agent(COMPETITIVE_URL, {
            "business_type": ctx["business_type"],
            "sector": ctx["sector"],
            "risk_horizon": ctx["risk_horizon"],
            "signal_report": signal_out,
        })
        activated.append("Risk Synthesizer")
        risk_out = call_agent(RISK_URL, {
            "business_type": ctx["business_type"],
            "sector": ctx["sector"],
            "risk_horizon": ctx["risk_horizon"],
            "signal_report": signal_out,
            "narrative_report": "",
            "macro_report": "",
            "competitive_report": competitive_out,
        })
        activated.append("Strategy Commander")
        strategy_out = call_agent(STRATEGY_URL, {
            "business_type": ctx["business_type"],
            "sector": ctx["sector"],
            "risk_horizon": ctx["risk_horizon"],
            "risk_verdict": risk_out,
        })

    elif intent in ("DECISION_SUPPORT", "SCENARIO"):
        activated.append("Macro Watchdog")
        macro_out = call_agent(MACRO_URL, {
            "business_type": ctx["business_type"],
            "sector": ctx["sector"],
            "risk_horizon": ctx["risk_horizon"],
            "signal_report": signal_out,
        })
        activated.append("Risk Synthesizer")
        risk_out = call_agent(RISK_URL, {
            "business_type": ctx["business_type"],
            "sector": ctx["sector"],
            "risk_horizon": ctx["risk_horizon"],
            "signal_report": signal_out,
            "narrative_report": "",
            "macro_report": macro_out,
            "competitive_report": "",
        })
        activated.append("Strategy Commander")
        strategy_out = call_agent(STRATEGY_URL, {
            "business_type": ctx["business_type"],
            "sector": ctx["sector"],
            "risk_horizon": ctx["risk_horizon"],
            "risk_verdict": risk_out,
        })

    else:  # FULL_BRIEFING (default)
        activated.append("Narrative Intel")
        narrative_out = call_agent(NARRATIVE_URL, {"signal_report": signal_out})

        activated.append("Macro Watchdog")
        macro_out = call_agent(MACRO_URL, {
            "business_type": ctx["business_type"],
            "sector": ctx["sector"],
            "risk_horizon": ctx["risk_horizon"],
            "signal_report": signal_out,
        })

        activated.append("Competitive Intel")
        competitive_out = call_agent(COMPETITIVE_URL, {
            "business_type": ctx["business_type"],
            "sector": ctx["sector"],
            "risk_horizon": ctx["risk_horizon"],
            "signal_report": signal_out,
        })

        activated.append("Risk Synthesizer")
        risk_out = call_agent(RISK_URL, {
            "business_type": ctx["business_type"],
            "sector": ctx["sector"],
            "risk_horizon": ctx["risk_horizon"],
            "signal_report": signal_out,
            "narrative_report": narrative_out,
            "macro_report": macro_out,
            "competitive_report": competitive_out,
        })

        activated.append("Strategy Commander")
        strategy_out = call_agent(STRATEGY_URL, {
            "business_type": ctx["business_type"],
            "sector": ctx["sector"],
            "risk_horizon": ctx["risk_horizon"],
            "risk_verdict": risk_out,
        })

    return {
        **state,
        "signal_output": signal_out,
        "narrative_output": narrative_out,
        "macro_output": macro_out,
        "competitive_output": competitive_out,
        "risk_output": risk_out,
        "strategy_output": strategy_out,
        "oracle_output": oracle_out,
        "activated_agents": activated,
    }


# ── NODE 4: Synthesize final response ────────────────────────────────────────
def synthesize_response(state: OrchestratorState) -> OrchestratorState:
    ctx = state["business_context"]
    now = datetime.now(timezone.utc).strftime("%B %d, %Y %H:%M UTC")
    agents_str = ", ".join(["Signal Harvester"] + state["activated_agents"]) \
        if state["intent"] != "INVESTMENT_QUERY" else "Market Oracle"

    synthesis_input = {
        "business_type": ctx["business_type"],
        "sector": ctx["sector"],
        "risk_horizon": ctx["risk_horizon"],
        "datetime": now,
        "intent": state["intent"],
        "activated_agents": agents_str,
        "signal_output": state["signal_output"],
        "narrative_output": state["narrative_output"],
        "macro_output": state["macro_output"],
        "competitive_output": state["competitive_output"],
        "risk_output": state["risk_output"],
        "strategy_output": state["strategy_output"],
        "oracle_output": state["oracle_output"],
    }

    response = llm.invoke([
        SystemMessage(content=SYNTHESIS_PROMPT),
        HumanMessage(content=json.dumps(synthesis_input, indent=2)),
    ])

    return {**state, "final_response": response.content}


# ── Routing functions ─────────────────────────────────────────────────────────
def route_after_parse(state: OrchestratorState) -> Literal["ask_for_info", "execute_pipeline"]:
    if state.get("missing_business_info") and state.get("intent") != "INVESTMENT_QUERY":
        return "ask_for_info"
    return "execute_pipeline"


def route_after_ask(state: OrchestratorState) -> Literal["__end__"]:
    return "__end__"


def route_after_execute(state: OrchestratorState) -> Literal["synthesize_response"]:
    return "synthesize_response"


# ── Build graph ───────────────────────────────────────────────────────────────
def build_orchestrator():
    graph = StateGraph(OrchestratorState)

    graph.add_node("parse_intent", parse_intent)
    graph.add_node("ask_for_info", ask_for_info)
    graph.add_node("execute_pipeline", execute_pipeline)
    graph.add_node("synthesize_response", synthesize_response)

    graph.set_entry_point("parse_intent")

    graph.add_conditional_edges("parse_intent", route_after_parse, {
        "ask_for_info": "ask_for_info",
        "execute_pipeline": "execute_pipeline",
    })
    graph.add_edge("ask_for_info", END)
    graph.add_edge("execute_pipeline", "synthesize_response")
    graph.add_edge("synthesize_response", END)

    return graph.compile()


orchestrator = build_orchestrator()


def run_orchestrator(user_message: str, history: list = None) -> dict:
    """
    history: list of {"role": "user"|"assistant", "content": str}
    Returns: {"response": str, "activated_agents": list, "intent": str}
    """
    messages = []
    for h in (history or []):
        if h["role"] == "user":
            messages.append(HumanMessage(content=h["content"]))
        else:
            messages.append(AIMessage(content=h["content"]))
    messages.append(HumanMessage(content=user_message))

    initial_state: OrchestratorState = {
        "messages": messages,
        "user_query": user_message,
        "intent": "",
        "business_context": {},
        "analysis_depth": "standard",
        "missing_business_info": False,
        "signal_output": "", "narrative_output": "",
        "macro_output": "", "competitive_output": "",
        "risk_output": "", "strategy_output": "", "oracle_output": "",
        "activated_agents": [], "final_response": "",
    }

    result = orchestrator.invoke(initial_state)
    return {
        "response": result.get("final_response", "No response generated."),
        "activated_agents": result.get("activated_agents", []),
        "intent": result.get("intent", ""),
    }
