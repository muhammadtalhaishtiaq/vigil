"""
health_check.py — Vigil Pre-Deployment Health Check
=====================================================
Run this before pushing to Streamlit Cloud to verify all three external
dependencies are reachable and returning valid data.

Usage:
    # Option A: keys from .env file
    python health_check.py

    # Option B: keys as env vars
    AIML_API_KEY=xxx NEWSAPI_KEY=yyy python health_check.py

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
"""

import os
import sys
import time

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional

# ── Colour helpers ─────────────────────────────────────────────────────────
_GREEN  = "\033[92m"
_RED    = "\033[91m"
_YELLOW = "\033[93m"
_BOLD   = "\033[1m"
_RESET  = "\033[0m"

def _pass(msg: str) -> None:
    print(f"  {_GREEN}✓ PASS{_RESET}  {msg}")

def _fail(msg: str, detail: str = "") -> None:
    print(f"  {_RED}✗ FAIL{_RESET}  {msg}")
    if detail:
        print(f"         {_YELLOW}↳ {detail}{_RESET}")

def _info(msg: str) -> None:
    print(f"  {_YELLOW}…{_RESET}      {msg}")


# ── Secret helper (mirrors app logic) ──────────────────────────────────────
def _get_secret(key: str) -> str:
    """Read from env (health_check always runs outside Streamlit)."""
    return os.getenv(key, "")


# =============================================================================
# CHECK 1 — NewsAPI connection
# =============================================================================
def check_newsapi() -> bool:
    import requests

    api_key = _get_secret("NEWSAPI_KEY")
    if not api_key:
        _fail("NewsAPI", "NEWSAPI_KEY not set in environment / .env")
        return False

    _info("Hitting NewsAPI /top-headlines (financial category)…")
    try:
        t0 = time.time()
        resp = requests.get(
            "https://newsapi.org/v2/top-headlines",
            params={"category": "business", "pageSize": 1, "apiKey": api_key},
            timeout=10,
        )
        elapsed = round(time.time() - t0, 2)

        if resp.status_code == 200:
            data = resp.json()
            total = data.get("totalResults", 0)
            _pass(f"NewsAPI — HTTP 200 · {total} total results · {elapsed}s")
            return True
        else:
            _fail("NewsAPI", f"HTTP {resp.status_code}: {resp.text[:120]}")
            return False
    except Exception as exc:
        _fail("NewsAPI", str(exc))
        return False


# =============================================================================
# CHECK 2 — yfinance (VIX spot price)
# =============================================================================
def check_yfinance() -> bool:
    _info("Fetching ^VIX from yfinance (no key required)…")
    try:
        import yfinance as yf

        t0 = time.time()
        ticker = yf.Ticker("^VIX")
        hist   = ticker.history(period="1d", interval="1d")
        elapsed = round(time.time() - t0, 2)

        if hist.empty:
            _fail("yfinance", "^VIX history returned empty DataFrame")
            return False

        price = float(hist["Close"].iloc[-1])
        _pass(f"yfinance — ^VIX = {price:.2f} · {elapsed}s")
        return True
    except Exception as exc:
        _fail("yfinance", str(exc))
        return False


# =============================================================================
# CHECK 3 — AIML API (1-token ping)
# =============================================================================
def check_aiml_api() -> bool:
    api_key = _get_secret("AIML_API_KEY")
    if not api_key:
        _fail("AIML API", "AIML_API_KEY not set in environment / .env")
        return False

    _info("Sending 1-token ping to AIML API (claude-haiku-4-5-20251001)…")
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url="https://api.aimlapi.com/v1")
        t0 = time.time()
        resp = client.chat.completions.create(
            model="claude-haiku-4-5-20251001",
            messages=[{"role": "user", "content": "Reply with one word: OK"}],
            max_tokens=4,
            temperature=0,
        )
        elapsed = round(time.time() - t0, 2)
        reply = resp.choices[0].message.content.strip()
        _pass(f"AIML API — response: '{reply}' · {elapsed}s")
        return True
    except Exception as exc:
        _fail("AIML API", str(exc)[:200])
        return False


# =============================================================================
# MAIN
# =============================================================================
def main() -> int:
    print(f"\n{_BOLD}Vigil Pre-Deployment Health Check{_RESET}")
    print("=" * 48)

    results = {}

    print(f"\n{_BOLD}[1/3] NewsAPI{_RESET}")
    results["newsapi"] = check_newsapi()

    print(f"\n{_BOLD}[2/3] yfinance (^VIX){_RESET}")
    results["yfinance"] = check_yfinance()

    print(f"\n{_BOLD}[3/3] AIML API{_RESET}")
    results["aiml_api"] = check_aiml_api()

    # ── Summary ───────────────────────────────────────────────────────────
    passed = sum(results.values())
    total  = len(results)
    print(f"\n{'=' * 48}")
    if passed == total:
        print(f"{_GREEN}{_BOLD}All {total}/{total} checks passed — safe to deploy ✓{_RESET}")
        return 0
    else:
        failed_list = [k for k, v in results.items() if not v]
        print(f"{_RED}{_BOLD}{total - passed}/{total} check(s) failed: {', '.join(failed_list)}{_RESET}")
        print(f"{_YELLOW}Fix the issues above before deploying to Streamlit Cloud.{_RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
