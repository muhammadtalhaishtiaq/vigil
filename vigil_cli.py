#!/usr/bin/env python3
"""
vigil_cli.py — the Vigil console
================================
An interactive terminal session for the same framework-free engine the MCP
server uses. This is the product, not a Q&A toy:

  • **Your company profile lives here.** `/profile` runs a setup wizard once;
    it persists to disk (session_store) and every subsequent question is
    analyzed *for your company*, not generically.
  • **Conversation is a session.** History persists across runs and is fed back
    into the pipeline, so follow-ups have context.
  • **You watch the agents work.** Every run renders the live agent-wave view
    (queued → running → complete, with per-agent timing).

Run `python vigil_cli.py` for the interactive console. One-shot subcommands
(`brief`, `ask`, `verdict`) still exist for scripting.

Requires an LLM key in the environment (AIML_API_KEY or LLM_API_KEY). With no
key the engine degrades gracefully and says so — it never fabricates analysis.
"""

from __future__ import annotations

import sys
import time
import argparse
import threading
from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.text import Text

import agent_core
from agent_pipeline import run_pipeline, has_sufficient_profile
from session_store import store
import tools  # importing also attaches the scout agents' data tools

console = Console()

_SESSION_ID = "cli"          # one local console session
_HISTORY_LIMIT = 40          # turns kept on disk
_DISCLAIMER = "Vigil analysis, not financial advice — verify independently."

# status → (icon, rich style)
_STATUS_STYLE = {
    "idle":     ("○", "dim"),
    "queued":   ("◔", "yellow"),
    "running":  ("◑", "bold cyan"),
    "complete": ("●", "green"),
    "error":    ("✕", "bold red"),
}

# Profile wizard: (field, prompt, required)
_PROFILE_FIELDS = [
    ("company_name", "Company name", True),
    ("description", "What does the company do (1–2 sentences)", True),
    ("sector", "Sector / industry (e.g. Fintech)", False),
    ("stage", "Stage (e.g. Series A, bootstrapped, public)", False),
    ("country", "Primary market / HQ country", False),
    ("arr", "Revenue or ARR range (e.g. $1–5M)", False),
    ("runway", "Runway (e.g. 14 months)", False),
    ("current_decisions", "Decisions on the table right now", False),
    ("risk_areas", "Known risk exposures (e.g. FX, EU regulation)", False),
]


# ---------------------------------------------------------------------------
# Session persistence (profile + history via session_store)
# ---------------------------------------------------------------------------
def _load_session() -> dict:
    data = store.get(_SESSION_ID) or {}
    data.setdefault("profile", {})
    data.setdefault("history", [])
    data.setdefault("score_history", [])
    data.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    return data


def _save_session(data: dict) -> None:
    data["history"] = data["history"][-_HISTORY_LIMIT:]
    store.set(_SESSION_ID, data)


# ---------------------------------------------------------------------------
# Live agent-wave view
# ---------------------------------------------------------------------------
def _agent_rows() -> list[str]:
    rows = list(agent_core.ALL_AGENTS)
    if agent_core.AGENT_STATUSES.get("risk_evaluator", "idle") != "idle":
        rows.append("risk_evaluator")
    return rows


def _render_agents(title: str) -> Panel:
    table = Table(expand=True, show_edge=False, pad_edge=False)
    table.add_column(" ", width=2, justify="center")
    table.add_column("agent", style="bold", no_wrap=True, min_width=16)
    table.add_column("status", min_width=9, no_wrap=True)
    table.add_column("time", min_width=6, justify="right", no_wrap=True)
    table.add_column("role", style="dim", ratio=1, overflow="ellipsis", no_wrap=True)

    for name in _agent_rows():
        status = agent_core.AGENT_STATUSES.get(name, "idle")
        elapsed = agent_core.AGENT_ELAPSED.get(name)
        icon, style = _STATUS_STYLE.get(status, ("○", "dim"))
        agent = agent_core.AGENTS.get(name)
        role = agent.role if agent else "critic — grades the briefing (evaluator-optimizer)"
        role = role.split(" — ")[-1] if " — " in role else role
        table.add_row(
            Text(icon, style=style),
            name,
            Text(status, style=style),
            f"{elapsed:.1f}s" if elapsed else "",
            role,
        )
    return Panel(table, title=f"[bold]{title}[/]", border_style="cyan")


def _run_with_live_view(query: str, profile: dict | None, history: list | None, title: str) -> dict:
    """Run the pipeline in a worker thread while rendering the live agent view."""
    holder: dict = {}

    def worker():
        try:
            holder["result"] = run_pipeline(query, profile=profile, history=history)
        except Exception as exc:
            holder["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    with Live(_render_agents(title), console=console, refresh_per_second=10) as live:
        while thread.is_alive():
            live.update(_render_agents(title))
            time.sleep(0.1)
        live.update(_render_agents(title))
    thread.join()

    if "error" in holder:
        raise holder["error"]
    return holder["result"]


# ---------------------------------------------------------------------------
# Result rendering
# ---------------------------------------------------------------------------
def _print_briefing(result: dict) -> None:
    score = result.get("risk_score")
    tier = result.get("risk_tier")
    verdict = result.get("verdict")

    color = "cyan"
    header = Text()
    if score is not None:
        color = "green" if score < 40 else "yellow" if score < 70 else "red"
        header.append(f"Risk {score}/100 ", style=f"bold {color}")
        if tier:
            header.append(f"({tier}) ", style=color)
    if verdict:
        header.append(f"— {verdict}", style="bold")
    if header.plain.strip():
        console.print(Panel(header, title="[bold]Verdict[/]", border_style=color))

    brief = result.get("executive_brief")
    if brief:
        console.print(Panel(brief, title="Executive brief", border_style="dim"))

    for r in (result.get("top_risks") or [])[:5]:
        name = r.get("name") or r.get("risk") or "Risk"
        detail = r.get("detail") or ""
        console.print(f"  [red]•[/] [bold]{name}[/]" + (f" — {detail}" if detail else ""))

    actions = (result.get("top_actions") or [])[:5]
    if actions:
        console.print("\n[bold]Recommended actions[/]")
        for a in actions:
            title = a.get("title") or a.get("action") or "Action"
            deadline = a.get("deadline")
            console.print(f"  [green]•[/] {title}" + (f" [dim](by {deadline})[/]" if deadline else ""))

    if score is None and not brief:
        console.print(result.get("primary_response") or "No analysis produced.")

    console.print(f"\n[dim]{_run_footer(result)} · {_DISCLAIMER}[/]")


def _run_footer(result: dict) -> str:
    """'4 agents · 48.2s · 21,340 tokens' — the cost-per-task line."""
    n = len(result.get("agents_activated") or [])
    took = result.get("total_time_seconds")
    usage = result.get("token_usage") or {}
    total_tokens = (usage.get("prompt") or 0) + (usage.get("completion") or 0)
    parts = [f"{n} agents"]
    if took is not None:
        parts.append(f"{took}s")
    if total_tokens:
        parts.append(f"{total_tokens:,} tokens")
    return " · ".join(parts)


def _print_text_result(result: dict, field: str = "primary_response") -> None:
    body = result.get(field) or result.get("primary_response") or "No response produced."
    console.print(Panel(body, border_style="cyan"))
    console.print(f"[dim]{_run_footer(result)} · {_DISCLAIMER}[/]")


def _answer_text(result: dict) -> str:
    """The text remembered in conversation history for follow-up context."""
    return (
        result.get("executive_brief")
        or result.get("oracle_output")
        or result.get("primary_response")
        or ""
    )


# ---------------------------------------------------------------------------
# Risk-trend memory — a score means little without its history
# ---------------------------------------------------------------------------
_SPARK_BLOCKS = "▁▂▃▄▅▆▇█"


def _record_score(session: dict, score: int, tier: str | None) -> None:
    """Append this run's score to the session's history (last 26 kept)."""
    hist = session.setdefault("score_history", [])
    prev = hist[-1] if hist else None
    hist.append({
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "score": int(score),
        "tier": tier or "",
    })
    session["score_history"] = hist[-26:]
    session["last_risk_score"] = int(score)
    session["last_risk_tier"] = tier
    if prev and prev["score"] != int(score):
        direction = "down" if int(score) < prev["score"] else "up"
        color = "green" if direction == "down" else "red"
        console.print(
            f"[{color}]trend: {score}/100 — {direction} from "
            f"{prev['score']} on {prev['date']}[/]"
        )


def _welcome_risk_tail(session: dict) -> str:
    """' · last risk 61/100 (down from 68 on 2026-07-03)' — or empty."""
    hist = session.get("score_history") or []
    if not hist:
        risk = session.get("last_risk_score")
        return f" · last risk [bold]{risk}/100[/]" if risk is not None else ""
    last = hist[-1]
    tail = f" · last risk [bold]{last['score']}/100[/]"
    if len(hist) >= 2 and hist[-2]["score"] != last["score"]:
        prev = hist[-2]
        direction = "down" if last["score"] < prev["score"] else "up"
        tail += f" ({direction} from {prev['score']} on {prev['date']})"
    return tail


def _show_trend(session: dict) -> None:
    """Terminal sparkline of the score history."""
    hist = session.get("score_history") or []
    if not hist:
        console.print("[dim]no scored briefings yet — run /brief first[/]")
        return
    spark = "".join(
        _SPARK_BLOCKS[min(7, int(e["score"]) * 8 // 101)] for e in hist
    )
    last = hist[-1]
    body = (
        f"[bold]{spark}[/]  ({len(hist)} briefings)\n"
        f"{hist[0]['date']} → {last['date']} · "
        f"latest [bold]{last['score']}/100[/] {last.get('tier', '')}\n"
        f"[dim]scores: {', '.join(str(e['score']) for e in hist[-10:])}[/]"
    )
    console.print(Panel(body, title="[bold]Risk trend[/]", border_style="cyan"))


# ---------------------------------------------------------------------------
# Reports: snapshot, markdown rendering, /export, monitor
# ---------------------------------------------------------------------------
def _briefing_snapshot(result: dict) -> dict:
    """Compact copy of a scored run — what /export and monitor reports render."""
    return {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "risk_score": result.get("risk_score"),
        "risk_tier": result.get("risk_tier"),
        "verdict": result.get("verdict"),
        "executive_brief": result.get("executive_brief"),
        "top_risks": (result.get("top_risks") or [])[:3],
        "top_actions": (result.get("top_actions") or [])[:3],
        "agents": len(result.get("agents_activated") or []),
        "time_s": result.get("total_time_seconds"),
    }


def _render_report_md(snap: dict, session: dict) -> str:
    """Render a briefing snapshot as a standalone markdown report."""
    company = (session.get("profile") or {}).get("company_name", "your company")
    lines = [
        f"# Vigil risk report — {company}",
        f"_{snap['date']} · {snap['agents']} agents · {snap['time_s']}s_",
        "",
        f"## Risk: {snap['risk_score']}/100 ({snap['risk_tier']})",
    ]
    hist = session.get("score_history") or []
    if len(hist) >= 2:
        prev = hist[-2]
        lines.append(f"Previous: {prev['score']}/100 on {prev['date']}")
    if snap.get("verdict"):
        lines += ["", f"**Verdict:** {snap['verdict']}"]
    if snap.get("executive_brief"):
        lines += ["", snap["executive_brief"]]
    if snap.get("top_risks"):
        lines += ["", "## Top risks"]
        for r in snap["top_risks"]:
            head = f"- **{r.get('name', 'Risk')}**"
            if r.get("probability") is not None:
                head += f" (~{r['probability']}%)"
            if r.get("detail"):
                head += f" — {r['detail']}"
            lines.append(head)
    if snap.get("top_actions"):
        lines += ["", "## Recommended actions"]
        for a in snap["top_actions"]:
            head = f"- {a.get('title', 'Action')}"
            if a.get("deadline"):
                head += f" (by {a['deadline']})"
            lines.append(head)
    lines += ["", "---",
              "_Vigil analysis, not financial advice — verify independently._"]
    return "\n".join(lines)


def _write_report(snap: dict, session: dict, prefix: str = "briefing") -> "Path":
    from pathlib import Path  # local: keeps module deps obvious
    reports = tools.workspace_dir("reports")
    reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path: Path = reports / f"{prefix}-{stamp}.md"
    path.write_text(_render_report_md(snap, session), encoding="utf-8")
    return path


def _cmd_export(session: dict) -> None:
    snap = session.get("last_briefing")
    if not snap:
        console.print("[yellow]Nothing to export yet — run /brief (or ask a "
                      "question that produces a risk score) first.[/]")
        return
    path = _write_report(snap, session)
    console.print(f"[green]✓ report written:[/] {path}")


# ---------------------------------------------------------------------------
# Workspace: /ingest — distill user docs into the knowledge base
# ---------------------------------------------------------------------------
def _cmd_ingest() -> None:
    """
    Distill every document in workspace/docs/ into a compact knowledge note in
    workspace/wiki/ (using the user's own LLM key). Notes ground every future
    briefing; originals stay the source of truth and remain readable by agents.
    """
    docs = tools.list_company_docs()
    if not docs:
        console.print(
            f"[yellow]No documents found in [bold]{tools.workspace_dir('docs')}[/bold].\n"
            "Drop .md / .txt / .csv files there (financials, plans, contracts) "
            "and run /ingest again.[/]"
        )
        return
    wiki = tools.workspace_dir("wiki")
    wiki.mkdir(parents=True, exist_ok=True)
    console.print(f"[dim]Distilling {len(docs)} document(s) into the knowledge base…[/]")
    ok = 0
    for path in docs:
        console.print(f"  [dim]{path.name} …[/]", end=" ")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[:12_000]
        except Exception as exc:
            console.print(f"[red]unreadable ({str(exc)[:40]})[/]")
            continue
        note = agent_core.DOC_DISTILLER.run(f"DOCUMENT ({path.name}):\n{text}")
        if note.startswith("[") and "UNAVAILABLE" in note:
            console.print("[red]distillation failed[/]")
            continue
        target = wiki / f"{path.stem}.md"
        header = (
            f"<!-- distilled from {path.name} on "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')} — this note is an "
            f"index; agents read the original via read_company_doc -->\n"
        )
        target.write_text(header + note, encoding="utf-8")
        console.print(f"[green]✓ wiki/{target.name}[/]")
        ok += 1
    if ok:
        console.print(
            f"[bold green]{ok}/{len(docs)} distilled.[/] Every briefing now uses "
            "your knowledge base as context. Re-run /ingest when documents change."
        )


# ---------------------------------------------------------------------------
# Profile commands
# ---------------------------------------------------------------------------
def _profile_wizard(existing: dict) -> dict:
    """Interactive profile setup. Enter keeps the current value; '-' clears it."""
    console.print(Panel(
        "Set up your company profile — this is what makes every briefing [bold]yours[/].\n"
        "[dim]Enter keeps the current value · '-' clears a field · required fields can't be empty[/]",
        title="[bold]Profile setup[/]", border_style="magenta",
    ))
    profile = dict(existing)
    for field, prompt, required in _PROFILE_FIELDS:
        current = str(profile.get(field) or "").strip()
        suffix = f" [dim]\\[{current}][/]" if current else (" [red]*[/]" if required else "")
        while True:
            raw = console.input(f"[bold]{prompt}[/]{suffix}: ").strip()
            if raw == "-":
                profile[field] = ""
                break
            if raw:
                profile[field] = raw
                break
            if current or not required:
                break  # keep current / skip optional
            console.print("[red]  this field is required[/]")
    profile["updated_at"] = datetime.now(timezone.utc).isoformat()
    return profile


def _show_profile(profile: dict) -> None:
    if not has_sufficient_profile(profile):
        console.print("[yellow]No profile yet — run [bold]/profile[/bold] to set one up.[/]")
        return
    table = Table(show_header=False, show_edge=False, pad_edge=False)
    table.add_column(style="dim", no_wrap=True)
    table.add_column()
    for field, prompt, _ in _PROFILE_FIELDS:
        value = str(profile.get(field) or "").strip()
        if value:
            table.add_row(prompt, value)
    console.print(Panel(table, title=f"[bold]{profile.get('company_name', 'Profile')}[/]",
                        border_style="magenta"))


# ---------------------------------------------------------------------------
# Interactive console
# ---------------------------------------------------------------------------
_HELP = """\
[bold]/profile[/]        set up or edit your company profile (the wizard)
[bold]/profile show[/]   view the saved profile
[bold]/brief[/]          full risk briefing for your company (all agent waves)
[bold]/agents[/]         the agent roster — who does what
[bold]/trend[/]          your risk score over time (sparkline)
[bold]/ingest[/]         distill workspace/docs/ into your knowledge base
[bold]/export[/]         write the last briefing to workspace/reports/ (markdown)
[bold]/history[/]        recent conversation
[bold]/clear[/]          clear conversation history
[bold]/help[/]           this help
[bold]/exit[/]           leave (profile + history are saved)

Anything else you type is a question — it runs through the agents with your
profile and conversation history as context. Examples:
  should I buy Tesla right now?
  how exposed are we to the new EU rules?
  what's the macro backdrop this week?"""


def _print_agents_roster() -> None:
    table = Table(expand=True, show_edge=False, pad_edge=False)
    table.add_column("agent", style="bold", no_wrap=True)
    table.add_column("model", style="dim", no_wrap=True)
    table.add_column("tools", no_wrap=True)
    table.add_column("role", style="dim", ratio=1, overflow="ellipsis", no_wrap=True)
    for name in agent_core.ALL_AGENTS:
        a = agent_core.AGENTS[name]
        model = "haiku" if "haiku" in a.model else "sonnet"
        tool_names = ", ".join(t.name for t in a.tools) or "—"
        table.add_row(name, model, tool_names, a.role)
    console.print(Panel(table, title="[bold]The 8 agents[/]", border_style="cyan"))


def _handle_question(session: dict, question: str) -> None:
    profile = session["profile"] if has_sufficient_profile(session["profile"]) else None
    result = _run_with_live_view(question, profile, session["history"], "Vigil")
    console.print()
    if result.get("risk_score") is not None:
        _print_briefing(result)
    elif result.get("oracle_output"):
        _print_text_result(result, "oracle_output")
    else:
        _print_text_result(result)

    session["history"].append({"role": "user", "content": question})
    answer = _answer_text(result)
    if answer:
        session["history"].append({"role": "assistant", "content": answer})
    if result.get("risk_score") is not None:
        _record_score(session, result["risk_score"], result.get("risk_tier"))
        session["last_briefing"] = _briefing_snapshot(result)
    _save_session(session)


def interactive() -> int:
    session = _load_session()
    profile = session["profile"]

    console.print(Panel(
        "[bold magenta]VIGIL[/] — multi-agent financial risk intelligence\n"
        "[dim]8 agents · live market data · analysis personalized to your company[/]",
        border_style="magenta",
    ))

    if has_sufficient_profile(profile):
        tail = _welcome_risk_tail(session)
        console.print(f"Welcome back — profile: [bold]{profile.get('company_name')}[/]{tail}")
        console.print("[dim]/help for commands, or just ask a question.[/]\n")
    else:
        console.print(
            "No company profile yet. You can ask general questions right away, but the\n"
            "whole point of Vigil is analysis [bold]for your company[/] — set that up first."
        )
        if console.input("[bold]Set up your profile now? \\[Y/n][/] ").strip().lower() not in ("n", "no"):
            session["profile"] = _profile_wizard(profile)
            _save_session(session)
            _show_profile(session["profile"])
        console.print("[dim]/help for commands, or just ask a question.[/]\n")

    while True:
        try:
            raw = console.input("[bold magenta]vigil>[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]saved · bye[/]")
            return 0
        if not raw:
            continue

        cmd = raw.lower()
        try:
            if cmd in ("/exit", "/quit", "exit", "quit"):
                console.print("[dim]saved · bye[/]")
                return 0
            elif cmd == "/help":
                console.print(Panel(_HELP, title="[bold]Commands[/]", border_style="dim"))
            elif cmd == "/profile show":
                _show_profile(session["profile"])
            elif cmd == "/profile":
                session["profile"] = _profile_wizard(session["profile"])
                _save_session(session)
                _show_profile(session["profile"])
            elif cmd == "/agents":
                _print_agents_roster()
            elif cmd == "/trend":
                _show_trend(session)
            elif cmd == "/ingest":
                _cmd_ingest()
            elif cmd == "/export":
                _cmd_export(session)
            elif cmd == "/history":
                history = session["history"]
                if not history:
                    console.print("[dim]no conversation yet[/]")
                for msg in history[-10:]:
                    style = "bold" if msg["role"] == "user" else "dim"
                    console.print(f"[{style}]{msg['role']}:[/] {msg['content'][:160]}")
            elif cmd == "/clear":
                session["history"] = []
                _save_session(session)
                console.print("[dim]history cleared[/]")
            elif cmd == "/brief":
                if not has_sufficient_profile(session["profile"]):
                    console.print("[yellow]A briefing needs a profile — run [bold]/profile[/bold] first.[/]")
                    continue
                name = session["profile"].get("company_name")
                _handle_question(session, f"Give me a full financial risk briefing for {name}.")
            elif raw.startswith("/"):
                console.print(f"[yellow]unknown command {raw} — /help lists them[/]")
            else:
                _handle_question(session, raw)
        except KeyboardInterrupt:
            console.print("\n[dim]cancelled[/]")
        except Exception as exc:
            console.print(f"[red]error:[/] {str(exc)[:200]}")


# ---------------------------------------------------------------------------
# One-shot subcommands (scripting; the interactive console is the main door)
# ---------------------------------------------------------------------------
def cmd_brief(args) -> None:
    session = _load_session()
    profile = session["profile"]
    if args.company:
        profile = {
            "company_name": args.company,
            "description": args.description or "",
            "sector": args.sector or "",
            "stage": args.stage or "",
            "country": args.country or "",
            "risk_areas": args.concerns or "",
        }
    if not has_sufficient_profile(profile):
        console.print("[yellow]No saved profile — pass --company/--description, or run "
                      "the console and use /profile.[/]")
        sys.exit(1)
    name = profile.get("company_name")
    console.print(f"\n[dim]Briefing for [bold]{name}[/] — running the full agent wave…[/]\n")
    result = _run_with_live_view(
        f"Give me a full financial risk briefing for {name}.",
        profile, session["history"], "Vigil — full risk briefing",
    )
    console.print()
    _print_briefing(result)


def cmd_ask(args) -> None:
    session = _load_session()
    profile = session["profile"] if has_sufficient_profile(session["profile"]) else None
    result = _run_with_live_view(args.query, profile, session["history"], "Vigil — analysis")
    console.print()
    _print_text_result(result)


def cmd_verdict(args) -> None:
    session = _load_session()
    result = _run_with_live_view(args.question, None, None, "Vigil — Market Oracle")
    console.print()
    _print_text_result(result, "oracle_output")


def cmd_monitor(args) -> None:
    """
    One-shot scheduled check (cron the command; the OS is the scheduler):
    run a full briefing with the saved profile, record the score, write a
    report, and signal risk jumps via exit code.

    Exit codes: 0 = ran, change below threshold · 2 = risk moved >= threshold
    (or first run) · 1 = cannot run (no profile / no score produced).
    """
    session = _load_session()
    if not has_sufficient_profile(session["profile"]):
        console.print("[red]monitor needs a saved profile — run `vigil` once and "
                      "complete /profile.[/]")
        sys.exit(1)
    name = session["profile"].get("company_name")
    console.print(f"[dim]monitor: full briefing for {name}…[/]")
    result = run_pipeline(
        f"Give me a full financial risk briefing for {name}.",
        profile=session["profile"], history=session["history"],
    )
    score = result.get("risk_score")
    if score is None:
        console.print("[red]monitor: run produced no risk score — see trace.[/]")
        sys.exit(1)

    hist = session.get("score_history") or []
    prev = hist[-1] if hist else None
    _record_score(session, score, result.get("risk_tier"))
    snap = _briefing_snapshot(result)
    session["last_briefing"] = snap
    _save_session(session)
    path = _write_report(snap, session, prefix="monitor")

    delta = abs(score - prev["score"]) if prev else None
    changed = delta is None or delta >= args.threshold
    console.print(
        f"{name}: [bold]{score}/100[/] ({result.get('risk_tier')})"
        + (f" · Δ{delta} vs {prev['score']} on {prev['date']}" if prev else " · first run")
        + f" · report: {path}"
    )
    sys.exit(2 if changed else 0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="vigil",
        description="Vigil — multi-agent financial risk intelligence. "
                    "Run with no arguments for the interactive console.",
    )
    sub = parser.add_subparsers(dest="command")

    p_brief = sub.add_parser("brief", help="One-shot full risk briefing (uses saved profile)")
    p_brief.add_argument("--company")
    p_brief.add_argument("--description")
    p_brief.add_argument("--sector")
    p_brief.add_argument("--stage")
    p_brief.add_argument("--country")
    p_brief.add_argument("--concerns")
    p_brief.set_defaults(func=cmd_brief)

    p_ask = sub.add_parser("ask", help="One-shot question (uses saved profile as context)")
    p_ask.add_argument("query")
    p_ask.set_defaults(func=cmd_ask)

    p_verdict = sub.add_parser("verdict", help="One-shot investment verdict (Market Oracle)")
    p_verdict.add_argument("question")
    p_verdict.set_defaults(func=cmd_verdict)

    p_monitor = sub.add_parser(
        "monitor",
        help="Cron-able check: brief, record score, write report; exit 2 on risk jump",
    )
    p_monitor.add_argument("--threshold", type=int, default=10,
                           help="score change that counts as a jump (default 10)")
    p_monitor.set_defaults(func=cmd_monitor)

    args = parser.parse_args(argv)
    if not args.command:
        return interactive()
    try:
        args.func(args)
    except KeyboardInterrupt:
        console.print("\n[dim]cancelled[/]")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
