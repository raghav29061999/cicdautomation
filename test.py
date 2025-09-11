app/tools/common/utils.py

---

from typing import Dict, Any, List

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    total = sum(abs(w) for w in weights.values()) or 1.0
    return {k: (w / total) for k, w in weights.items()}

def top_k(d: Dict[str, float], k: int = 3) -> List[str]:
    return [k for k, _ in sorted(d.items(), key=lambda x: -abs(x[1]))[:k]]

def safe_get(d: Dict[str, Any], *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur




------------

app/tools/io/load_client.py

import os
import pandas as pd
from typing import Dict, Any
from strands import tool

DATA_PATH = os.getenv("DATA_PATH", "data/clients.csv")

@tool
def load_client_profile(client_id: str) -> Dict[str, Any]:
    """
    Load a client's basic profile from CSV.
    CSV columns (example): client_id,name,risk,horizon,goals
    """
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Missing data file: {DATA_PATH}")
    df = pd.read_csv(DATA_PATH, dtype=str).fillna("")
    row = df.loc[df["client_id"] == client_id]
    if row.empty:
        raise ValueError(f"Client {client_id} not found")
    r = row.iloc[0]
    return {
        "client_id": r["client_id"],
        "name": r.get("name", ""),
        "risk": r.get("risk", "moderate"),
        "horizon": r.get("horizon", "5y"),
        "goals": r.get("goals", "")
    }

@tool
def load_client_positions(client_id: str) -> Dict[str, float]:
    """
    Return a simple positions map {ticker: amount}.
    For POC, assume positions are in extra CSV columns like pos_AAPL,pos_BND,...
    """
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Missing data file: {DATA_PATH}")
    df = pd.read_csv(DATA_PATH, dtype=str).fillna("")
    row = df.loc[df["client_id"] == client_id]
    if row.empty:
        raise ValueError(f"Client {client_id} not found")
    r = row.iloc[0].to_dict()
    positions = {}
    for k, v in r.items():
        if k.startswith("pos_") and v:
            try:
                positions[k.replace("pos_", "")] = float(v)
            except ValueError:
                continue
    if not positions:
        # Default tiny demo portfolio
        positions = {"SPY": 60.0, "AGG": 30.0, "VXUS": 10.0}
    return positions



------------

app/tools/io/load_market.py



import os, json
from typing import Dict, Any
from strands import tool

MARKET_PATH = os.getenv("MARKET_PATH", "data/market.json")

@tool
def load_market_snapshot() -> Dict[str, Any]:
    """
    Load a tiny market snapshot JSON, e.g.:
    {
      "volatility": {"SPY": 0.16, "AGG": 0.05, "VXUS": 0.18},
      "sectors": {"AAPL": "Tech", ...},
      "benchmarks": {"US_STOCK": 0.60, "US_BOND": 0.40}
    }
    """
    if not os.path.exists(MARKET_PATH):
        # Safe default snapshot
        return {
            "volatility": {"SPY": 0.16, "AGG": 0.05, "VXUS": 0.18},
            "benchmarks": {"US_STOCK": 0.60, "US_BOND": 0.40}
        }
    with open(MARKET_PATH, "r") as f:
        return json.load(f)



-------------------
app/tools/portfolio/weights.py


from typing import Dict
from strands import tool
from app.tools.common.utils import normalize_weights

@tool
def compute_weights(positions: Dict[str, float]) -> Dict[str, float]:
    """
    Convert raw position amounts into normalized weights that sum to ~1.0
    Negative or zero positions are ignored (POC simplification).
    """
    clean = {k: float(v) for k, v in positions.items() if float(v) > 0.0}
    return normalize_weights(clean)

--------------

app/tools/portfolio/risk.py


from typing import Dict
from strands import tool
from app.tools.common.utils import clamp

@tool
def estimate_portfolio_volatility(weights: Dict[str, float],
                                  vol_lookup: Dict[str, float]) -> float:
    """
    Estimate volatility as weighted sum of individual volatilities (POC simplification).
    """
    vol = 0.0
    for t, w in weights.items():
        vol += abs(w) * float(vol_lookup.get(t, 0.15))
    # clamp to a sane range
    return float(clamp(vol, 0.01, 0.60))

@tool
def concentration_flags(weights: Dict[str, float], threshold: float = 0.30) -> Dict[str, float]:
    """
    Report tickers whose absolute weight exceeds threshold (default 30%).
    """
    return {t: w for t, w in weights.items() if abs(w) >= threshold}
-----------------

app/tools/portfolio/score.py


from typing import Dict, Any
from strands import tool
from app.tools.portfolio.weights import compute_weights
from app.tools.portfolio.risk import estimate_portfolio_volatility, concentration_flags

def _grade_from_vol(vol: float) -> str:
    if vol < 0.08: return "A"
    if vol < 0.12: return "B"
    if vol < 0.18: return "C"
    if vol < 0.25: return "D"
    return "E"

@tool
def score_portfolio(positions: Dict[str, float], market: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute a simple score for diversification & volatility.
    Returns: {"weights": {...}, "volatility": 0.xx, "concentration": {...}, "grade": "B"}
    """
    weights = compute_weights(positions)
    vol_lookup = market.get("volatility", {})
    vol = estimate_portfolio_volatility(weights, vol_lookup)
    flags = concentration_flags(weights, threshold=0.35)
    grade = _grade_from_vol(vol)
    return {
        "weights": weights,
        "volatility": round(vol, 4),
        "concentration": flags,
        "grade": grade
    }
-----------
: app/tools/recommend/rules.py
from typing import Dict, Any, List
from strands import tool

@tool
def recommend_rebalance(score: Dict[str, Any]) -> List[str]:
    """
    Basic rule-based recommendations based on score.
    """
    recs = []
    vol = float(score.get("volatility", 0.15))
    grade = str(score.get("grade", "C"))
    concentration = score.get("concentration", {})

    if concentration:
        recs.append("Reduce positions above 35% weight to improve diversification.")
    if grade in ("D", "E") or vol >= 0.18:
        recs.append("Shift 10-15% into short-duration bond/treasury index for risk control.")
    elif grade in ("A", "B"):
        recs.append("Maintain current allocation; rebalance within ±5% bands.")
    else:
        recs.append("Consider gradual rebalancing toward a 60/40 or 70/30 mix.")
    return recs

@tool
def tailor_to_profile(profile: Dict[str, Any], recs: List[str]) -> List[str]:
    """
    Adjust recommendations using client risk tolerance / horizon.
    """
    risk = (profile.get("risk") or "moderate").lower()
    horizon = str(profile.get("horizon", "5y"))

    out = list(recs)
    if "short" in horizon.lower():
        out.append("Favor higher-liquidity ETFs due to shorter time horizon.")
    if risk in ("low", "conservative"):
        out.append("Cap equity exposure at ~50% until risk appetite increases.")
    if risk in ("high", "aggressive"):
        out.append("Allow tactical equity tilt up to +10% during strong markets.")
    return out[:4]  # keep it concise
----------
app/tools/recommend/formulate.py

from typing import List
from strands import tool

@tool
def format_recommendations_bullets(recs: List[str]) -> str:
    """
    Turn a list of recommendation sentences into a compact bullet string.
    """
    bullets = [f"- {r.strip()}" for r in recs if r and r.strip()]
    return "\n".join(bullets[:5])
------------

app/tools/compliance.py

import re
from strands import tool

RISKY_PHRASES = [
    r"guarantee(d)?",
    r"no risk",
    r"risk[- ]?free",
    r"will outperform",
]

DISCLAIMER = "Disclaimer: This content is for information only and not investment advice."

@tool
def compliance_sanitize(text: str) -> str:
    """
    Remove risky phrases and append a simple disclaimer.
    """
    clean = text
    for pat in RISKY_PHRASES:
        clean = re.sub(pat, "[avoid strong guarantees]", clean, flags=re.IGNORECASE)
    if DISCLAIMER.lower() not in clean.lower():
        clean = f"{clean.rstrip()}\n\n{DISCLAIMER}"
    return clean
------

app/tools/__init__.py

# Optional: expose a handy list for discovery if you prefer registry-by-import
from .io.load_client import load_client_profile, load_client_positions
from .io.load_market import load_market_snapshot
from .portfolio.weights import compute_weights
from .portfolio.risk import estimate_portfolio_volatility, concentration_flags
from .portfolio.score import score_portfolio
from .recommend.rules import recommend_rebalance, tailor_to_profile
from .recommend.formulate import format_recommendations_bullets
from .compliance import compliance_sanitize

__all_tools__ = [
    load_client_profile,
    load_client_positions,
    load_market_snapshot,
    compute_weights,
    estimate_portfolio_volatility,
    concentration_flags,
    score_portfolio,
    recommend_rebalance,
    tailor_to_profile,
    format_recommendations_bullets,
    compliance_sanitize,
]





