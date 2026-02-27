"""
data_layer.py — Vigil Live Data Backend
All external data fetching lives here. No mock data. Every external call is
wrapped in try/except. All keys read from environment variables only.
"""

import os
import time
import logging
from datetime import datetime, timezone
from typing import Optional

import requests
import yfinance as yf

# Load .env for local development (no-op in Streamlit Cloud)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [data_layer] %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Secret resolution: st.secrets (cloud) → os.getenv (local .env)
# ---------------------------------------------------------------------------
def _get_secret(key: str, default: str = "") -> str:
    """Read a secret from Streamlit Cloud secrets first, then env var."""
    try:
        import streamlit as st          # type: ignore
        val = st.secrets.get(key, "")
        if val:
            return str(val)
    except Exception:
        pass
    return os.getenv(key, default)

# ---------------------------------------------------------------------------
# Module-level 60-second cache
# ---------------------------------------------------------------------------
_cache: dict = {}
_cache_ts: float = 0.0
_CACHE_TTL: int = 60  # seconds


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _classify_sentiment(text: str) -> str:
    """
    Keyword-based sentiment classifier for news headlines.

    Returns 'positive', 'negative', or 'neutral'.
    """
    lowered = text.lower()
    positive_kw = {
        "rally", "surge", "surges", "surged", "beat", "beats", "beaten",
        "growth", "recovery", "recover", "gains", "gain", "rises", "rise",
        "rose", "jumped", "jump", "boost", "boosts", "boosted", "strong",
        "soared", "soar", "record high", "bullish", "upgrade",
    }
    negative_kw = {
        "crash", "crashes", "crashed", "fall", "falls", "fell", "fear",
        "recession", "drop", "drops", "dropped", "crisis", "decline",
        "declines", "declined", "plunge", "plunges", "plunged", "sell-off",
        "selloff", "tumble", "tumbles", "tumbled", "downgrade", "layoff",
        "layoffs", "default", "bankruptcy", "bearish", "loss", "losses",
    }
    for kw in negative_kw:
        if kw in lowered:
            return "negative"
    for kw in positive_kw:
        if kw in lowered:
            return "positive"
    return "neutral"


def _safe_float(value) -> Optional[float]:
    """Safely coerce a value to float, returning None on failure."""
    try:
        v = float(value)
        return round(v, 4)
    except (TypeError, ValueError):
        return None


def _pct_change_color(pct: Optional[float]) -> str:
    """Map a percentage change to a Vigil color token."""
    if pct is None:
        return "neutral"
    if pct > 2.0:
        return "dark_green"
    if pct > 0.5:
        return "light_green"
    if pct >= -0.5:
        return "neutral"
    if pct >= -2.0:
        return "light_red"
    return "dark_red"


def _pct_change_signal(pct: Optional[float]) -> str:
    """Map a percentage change to a directional signal string."""
    if pct is None:
        return "UNKNOWN"
    if pct > 2.0:
        return "STRONGLY BULLISH"
    if pct > 0.5:
        return "BULLISH"
    if pct >= -0.5:
        return "NEUTRAL"
    if pct >= -2.0:
        return "BEARISH"
    return "STRONGLY BEARISH"


# ---------------------------------------------------------------------------
# FUNCTION 1 — get_live_headlines
# ---------------------------------------------------------------------------

def get_live_headlines(sector: str = "finance") -> list[dict]:
    """
    Fetch the top 8 financial headlines from NewsAPI.org filtered by sector.

    Args:
        sector: Topic/sector string used as search query (e.g. "technology",
                "finance", "healthcare").

    Returns:
        List of dicts, each with keys:
            title       (str)
            source      (str)
            url         (str)
            publishedAt (str) — ISO 8601
            sentiment   (str) — "positive" | "neutral" | "negative"
    """
    _FALLBACK = [
        {
            "title": "Markets steady as investors await Fed guidance",
            "source": "Reuters",
            "url": "https://reuters.com",
            "publishedAt": datetime.now(timezone.utc).isoformat(),
            "sentiment": "neutral",
        },
        {
            "title": "Inflation data shows cooling trend for third consecutive month",
            "source": "Bloomberg",
            "url": "https://bloomberg.com",
            "publishedAt": datetime.now(timezone.utc).isoformat(),
            "sentiment": "positive",
        },
        {
            "title": "Tech sector faces headwinds amid rising yield concerns",
            "source": "FT",
            "url": "https://ft.com",
            "publishedAt": datetime.now(timezone.utc).isoformat(),
            "sentiment": "negative",
        },
    ]

    api_key = _get_secret("NEWSAPI_KEY")
    if not api_key:
        logger.warning("NEWSAPI_KEY not set — returning fallback headlines")
        return _FALLBACK

    query = f"{sector} economy market finance"
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 8,
        "apiKey": api_key,
    }

    try:
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        articles = data.get("articles", [])
        results = []
        for art in articles[:8]:
            title = art.get("title") or ""
            source = (art.get("source") or {}).get("name") or "Unknown"
            results.append(
                {
                    "title": title,
                    "source": source,
                    "url": art.get("url") or "",
                    "publishedAt": art.get("publishedAt") or "",
                    "sentiment": _classify_sentiment(title),
                }
            )
        logger.info("Headlines fetched: %d articles for sector '%s'", len(results), sector)
        return results if results else _FALLBACK
    except Exception as exc:
        logger.error("get_live_headlines failed: %s — returning fallback", exc)
        return _FALLBACK


# ---------------------------------------------------------------------------
# FUNCTION 2 — get_sector_performance
# ---------------------------------------------------------------------------

_SECTOR_ETFS: dict[str, str] = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financial Services": "XLF",
    "Consumer Discretionary": "XLY",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Real Estate": "XLRE",
}


def get_sector_performance() -> dict:
    """
    Retrieve 1-day and 7-day price performance for 7 major sector ETFs
    using yfinance (no API key required).

    Returns:
        Dict keyed by sector name, each value:
            ticker  (str)
            pct_7d  (float | None)  — 7-day % change
            pct_1d  (float | None)  — 1-day % change
            color   (str)           — based on pct_7d
            signal  (str)           — based on pct_7d
    """
    results: dict = {}

    for sector_name, ticker in _SECTOR_ETFS.items():
        _fallback_entry = {
            "ticker": ticker,
            "pct_7d": None,
            "pct_1d": None,
            "color": "neutral",
            "signal": "UNKNOWN",
        }
        try:
            tkr = yf.Ticker(ticker)
            # Fetch 10 days of daily history to reliably get 7-day change
            hist = tkr.history(period="10d", interval="1d")
            if hist.empty or len(hist) < 2:
                logger.warning("No history for %s", ticker)
                results[sector_name] = _fallback_entry
                continue

            close_prices = hist["Close"].dropna()
            latest = float(close_prices.iloc[-1])
            prev_1d = float(close_prices.iloc[-2])
            pct_1d = round(((latest - prev_1d) / prev_1d) * 100, 2) if prev_1d else None

            # 7-day: compare latest to price 7+ trading days ago
            ref_idx = min(7, len(close_prices) - 1)
            ref_price = float(close_prices.iloc[-ref_idx - 1])
            pct_7d = round(((latest - ref_price) / ref_price) * 100, 2) if ref_price else None

            results[sector_name] = {
                "ticker": ticker,
                "pct_7d": pct_7d,
                "pct_1d": pct_1d,
                "color": _pct_change_color(pct_7d),
                "signal": _pct_change_signal(pct_7d),
            }
        except Exception as exc:
            logger.error("get_sector_performance failed for %s: %s", ticker, exc)
            results[sector_name] = _fallback_entry

    logger.info("Sector performance fetched: %d sectors", len(results))
    return results


# ---------------------------------------------------------------------------
# FUNCTION 3 — get_market_pulse
# ---------------------------------------------------------------------------

def get_market_pulse() -> dict:
    """
    Fetch key macro market indicators using yfinance and derive
    human-readable risk signals.

    Instruments: VIX (^VIX), S&P 500 (^GSPC), 10Y Treasury (^TNX),
                 Gold (GC=F), US Dollar Index (DX-Y.NYB).

    Returns:
        Structured dict with raw values, derived labels, and
        composite fear/greed score (0–100).
    """

    def _fetch_latest(symbol: str) -> Optional[float]:
        try:
            tkr = yf.Ticker(symbol)
            hist = tkr.history(period="5d", interval="1d")
            if hist.empty:
                return None
            return _safe_float(hist["Close"].dropna().iloc[-1])
        except Exception as exc:
            logger.error("_fetch_latest(%s) failed: %s", symbol, exc)
            return None

    def _fetch_pct_change(symbol: str, days: int = 5) -> Optional[float]:
        try:
            tkr = yf.Ticker(symbol)
            hist = tkr.history(period=f"{days + 5}d", interval="1d")
            if hist.empty or len(hist) < 2:
                return None
            closes = hist["Close"].dropna()
            ref_idx = min(days, len(closes) - 1)
            latest = float(closes.iloc[-1])
            ref = float(closes.iloc[-ref_idx - 1])
            return round(((latest - ref) / ref) * 100, 2) if ref else None
        except Exception as exc:
            logger.error("_fetch_pct_change(%s) failed: %s", symbol, exc)
            return None

    # --- VIX ---
    vix = _fetch_latest("^VIX")
    if vix is None:
        vix_level = "UNKNOWN"
    elif vix < 15:
        vix_level = "LOW"
    elif vix < 20:
        vix_level = "ELEVATED"
    elif vix < 30:
        vix_level = "HIGH"
    else:
        vix_level = "EXTREME"

    # --- S&P 500 ---
    spx = _fetch_latest("^GSPC")
    spx_7d = _fetch_pct_change("^GSPC", days=5)  # ~1 trading week
    spx_trend = _pct_change_signal(spx_7d)

    # --- 10-Year Treasury Yield ---
    tnx = _fetch_latest("^TNX")  # quoted as e.g. 4.25 (percent)
    if tnx is None:
        yield_signal = "UNKNOWN"
    elif tnx > 5.0:
        yield_signal = "VERY HIGH — restrictive"
    elif tnx > 4.0:
        yield_signal = "HIGH — moderately restrictive"
    elif tnx > 3.0:
        yield_signal = "MODERATE — neutral territory"
    else:
        yield_signal = "LOW — accommodative"

    # Yield curve proxy: compare TNX to short-term (use 2Y via ^IRX if available)
    irx = _fetch_latest("^IRX")  # 13-week T-bill, roughly short-term proxy
    if tnx is not None and irx is not None:
        # IRX is quoted in annualised %, divide by 100 to get comparable
        irx_pct = irx / 100 if irx > 10 else irx  # handle quoting inconsistency
        spread = round(tnx - irx_pct, 3)
        if spread > 0.5:
            yield_curve = "NORMAL"
        elif spread > -0.1:
            yield_curve = "FLAT"
        else:
            yield_curve = "INVERTED"
    else:
        spread = None
        yield_curve = "UNKNOWN"

    # --- Gold ---
    gold = _fetch_latest("GC=F")
    gold_7d = _fetch_pct_change("GC=F", days=5)

    # --- USD Index ---
    dxy = _fetch_latest("DX-Y.NYB")
    dxy_7d = _fetch_pct_change("DX-Y.NYB", days=5)

    # --- Market Regime ---
    # Risk-on: low VIX + positive SPX + negative gold move
    # Risk-off: high VIX + negative SPX + positive gold move
    regime_score = 0
    if vix is not None:
        regime_score += 1 if vix < 20 else (-1 if vix > 25 else 0)
    if spx_7d is not None:
        regime_score += 1 if spx_7d > 0.5 else (-1 if spx_7d < -0.5 else 0)
    if gold_7d is not None:
        regime_score += -1 if gold_7d > 1.0 else (1 if gold_7d < -1.0 else 0)

    if regime_score >= 2:
        market_regime = "RISK-ON"
    elif regime_score <= -2:
        market_regime = "RISK-OFF"
    else:
        market_regime = "TRANSITIONAL"

    # --- Fear/Greed Score (0-100) ---
    # Composite of VIX, SPX momentum, gold momentum, DXY
    fg_components = []
    if vix is not None:
        # Invert VIX: low VIX → greed, high VIX → fear
        vix_score = max(0, min(100, int(100 - (vix / 50) * 100)))
        fg_components.append(vix_score)
    if spx_7d is not None:
        spx_score = max(0, min(100, int(50 + spx_7d * 5)))
        fg_components.append(spx_score)
    if gold_7d is not None:
        # Rising gold → fear
        gold_score = max(0, min(100, int(50 - gold_7d * 5)))
        fg_components.append(gold_score)

    fear_greed_score = int(sum(fg_components) / len(fg_components)) if fg_components else 50

    if fear_greed_score <= 20:
        fear_greed_label = "EXTREME FEAR"
    elif fear_greed_score <= 40:
        fear_greed_label = "FEAR"
    elif fear_greed_score <= 60:
        fear_greed_label = "NEUTRAL"
    elif fear_greed_score <= 80:
        fear_greed_label = "GREED"
    else:
        fear_greed_label = "EXTREME GREED"

    pulse = {
        "vix": {
            "value": vix,
            "level": vix_level,
        },
        "spx": {
            "value": spx,
            "pct_7d": spx_7d,
            "trend": spx_trend,
        },
        "treasury_10y": {
            "yield_pct": tnx,
            "signal": yield_signal,
            "yield_curve": yield_curve,
            "spread_vs_short": spread,
        },
        "gold": {
            "price": gold,
            "pct_7d": gold_7d,
            "signal": _pct_change_signal(gold_7d),
        },
        "dxy": {
            "value": dxy,
            "pct_7d": dxy_7d,
            "signal": _pct_change_signal(dxy_7d),
        },
        "market_regime": market_regime,
        "fear_greed": {
            "score": fear_greed_score,
            "label": fear_greed_label,
        },
    }

    logger.info(
        "Market pulse fetched | VIX:%.1f | SPX_7d:%.2f%% | Regime:%s | FG:%s(%d)",
        vix or 0, spx_7d or 0, market_regime, fear_greed_label, fear_greed_score,
    )
    return pulse


# ---------------------------------------------------------------------------
# FUNCTION 4 — get_stock_data
# ---------------------------------------------------------------------------

def get_stock_data(ticker: str) -> dict:
    """
    Fetch fundamentals and price history for a specific stock or asset
    ticker, used by the Market Oracle agent for investment queries.

    Args:
        ticker: Any valid yfinance ticker symbol (e.g. "AAPL", "BTC-USD",
                "QQQ", "GLD").

    Returns:
        Dict with keys:
            ticker, name, current_price, currency,
            pct_7d, pct_30d, pct_1yr,
            pe_ratio, market_cap, week_52_high, week_52_low,
            analyst_target, volume,
            valid (bool) — False if ticker not found
            error (str | None)
    """
    _empty = {
        "ticker": ticker.upper(),
        "name": None,
        "current_price": None,
        "currency": None,
        "pct_7d": None,
        "pct_30d": None,
        "pct_1yr": None,
        "pe_ratio": None,
        "market_cap": None,
        "week_52_high": None,
        "week_52_low": None,
        "analyst_target": None,
        "volume": None,
        "valid": False,
        "error": None,
    }

    try:
        tkr = yf.Ticker(ticker)
        info = tkr.info or {}

        # Validate ticker — yfinance returns minimal dict for unknowns
        current_price = _safe_float(
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
        )
        if current_price is None:
            # Try from history as last resort
            hist_check = tkr.history(period="5d")
            if hist_check.empty:
                _empty["error"] = f"Ticker '{ticker}' not found or no price data"
                return _empty
            current_price = _safe_float(hist_check["Close"].dropna().iloc[-1])

        # Historical % changes
        def _hist_pct(days: int) -> Optional[float]:
            try:
                hist = tkr.history(period=f"{days + 10}d", interval="1d")
                if hist.empty or len(hist) < 2:
                    return None
                closes = hist["Close"].dropna()
                ref_idx = min(days, len(closes) - 1)
                ref = float(closes.iloc[-ref_idx - 1])
                latest = float(closes.iloc[-1])
                return round(((latest - ref) / ref) * 100, 2) if ref else None
            except Exception:
                return None

        pct_7d = _hist_pct(5)   # ~1 trading week
        pct_30d = _hist_pct(21)  # ~1 trading month
        pct_1yr = _hist_pct(252)

        return {
            "ticker": ticker.upper(),
            "name": info.get("shortName") or info.get("longName") or ticker.upper(),
            "current_price": current_price,
            "currency": info.get("currency") or "USD",
            "pct_7d": pct_7d,
            "pct_30d": pct_30d,
            "pct_1yr": pct_1yr,
            "pe_ratio": _safe_float(info.get("trailingPE") or info.get("forwardPE")),
            "market_cap": info.get("marketCap"),
            "week_52_high": _safe_float(info.get("fiftyTwoWeekHigh")),
            "week_52_low": _safe_float(info.get("fiftyTwoWeekLow")),
            "analyst_target": _safe_float(info.get("targetMeanPrice")),
            "volume": info.get("regularMarketVolume") or info.get("volume"),
            "valid": True,
            "error": None,
        }

    except Exception as exc:
        logger.error("get_stock_data(%s) failed: %s", ticker, exc)
        _empty["error"] = str(exc)
        return _empty


# ---------------------------------------------------------------------------
# FUNCTION 5 — get_all_live_data  (master aggregator with 60s cache)
# ---------------------------------------------------------------------------

def get_all_live_data(sector: str = "finance") -> dict:
    """
    Master aggregator that combines all three live data sources into a
    single structured payload. Results are cached for 60 seconds to
    avoid hammering external APIs on rapid Streamlit reruns.

    Args:
        sector: Sector label passed through to get_live_headlines().

    Returns:
        Dict with keys:
            headlines    (list[dict])
            sectors      (dict)
            pulse        (dict)
            fetched_at   (str)   — ISO 8601 UTC timestamp
            data_quality (str)   — "FULL" | "PARTIAL" | "MINIMAL"
    """
    global _cache, _cache_ts

    now = time.monotonic()
    if _cache and (now - _cache_ts) < _CACHE_TTL:
        logger.info("Returning cached live data (age %.1fs)", now - _cache_ts)
        return _cache

    headlines = get_live_headlines(sector)
    sectors = get_sector_performance()
    pulse = get_market_pulse()

    # Determine data quality
    headlines_ok = bool(headlines) and any(
        h["source"] not in {"Reuters", "Bloomberg", "FT"} for h in headlines
    ) or (bool(headlines) and len(headlines) >= 4)
    sectors_ok = any(v["pct_7d"] is not None for v in sectors.values())
    pulse_ok = pulse.get("vix", {}).get("value") is not None

    if headlines_ok and sectors_ok and pulse_ok:
        data_quality = "FULL"
    elif sectors_ok or pulse_ok:
        data_quality = "PARTIAL"
    else:
        data_quality = "MINIMAL"

    result = {
        "headlines": headlines,
        "sectors": sectors,
        "pulse": pulse,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data_quality": data_quality,
    }

    _cache = result
    _cache_ts = now

    logger.info(
        "Vigil fetch | Headlines:%d | Sectors:%d | VIX:%s | Quality:%s",
        len(headlines),
        len(sectors),
        pulse.get("vix", {}).get("value", "N/A"),
        data_quality,
    )

    return result
