from fastapi import FastAPI, Query
app = FastAPI(title="MCP Portfolio (POC)")

DEMO = {
    "C-1001": {
        "profile": {"client_id":"C-1001","name":"Ada Moderate","risk":"moderate","horizon":"5y","goals":"retirement, college"},
        "positions": {"SPY":60.0,"AGG":30.0,"VXUS":10.0}
    }
}

@app.get("/client/profile")
def profile(client_id: str = Query(...)):
    return DEMO.get(client_id, {"client_id":client_id,"name":"","risk":"moderate","horizon":"5y","goals":""})

@app.get("/client/positions")
def positions(client_id: str = Query(...)):
    return DEMO.get(client_id, {}).get("positions", {"SPY":60.0,"AGG":30.0,"VXUS":10.0})


--------------------

import os
import pandas as pd
from typing import Dict, Any
from strands import tool
from app.mcp.client import mcp_enabled, fetch

DATA_PATH = os.getenv("DATA_PATH", "data/clients.csv")

@tool
def load_client_profile(client_id: str) -> Dict[str, Any]:
    """
    Try MCP portfolio:client_profile first; fallback to CSV.
    """
    if mcp_enabled():
        try:
            return fetch("portfolio", "client_profile", {"client_id": client_id})
        except Exception:
            pass  # fallback

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
    Try MCP portfolio:positions first; fallback to CSV (pos_* columns).
    """
    if mcp_enabled():
        try:
            data = fetch("portfolio", "positions", {"client_id": client_id})
            return {k: float(v) for k, v in data.items()}
        except Exception:
            pass  # fallback

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
        positions = {"SPY": 60.0, "AGG": 30.0, "VXUS": 10.0}
    return positions


----------


import os, json
from typing import Dict, Any
from strands import tool
from app.mcp.client import mcp_enabled, fetch

MARKET_PATH = os.getenv("MARKET_PATH", "data/market.json")

@tool
def load_market_snapshot() -> Dict[str, Any]:
    """
    Try MCP market:snapshot first; fallback to local JSON.
    """
    if mcp_enabled():
        try:
            return fetch("market", "snapshot")
        except Exception:
            pass  # fallback

    if not os.path.exists(MARKET_PATH):
        return {
            "volatility": {"SPY": 0.16, "AGG": 0.05, "VXUS": 0.18}
        }
    with open(MARKET_PATH, "r") as f:
        return json.load(f)



---------
How to run (POC with MCP)

Start both MCP demo servers (two terminals):

uvicorn app.mcp.servers.market_server:app --port 8765 --reload
uvicorn app.mcp.servers.portfolio_server:app --port 8766 --reload


Ensure app/mcp/client.yaml exists and has enabled: true.

Start your main API:

uvicorn app.main:app --reload





-------


import os, json, time
from typing import Any, Dict, Optional
import yaml, requests

_CFG_CACHE: Optional[Dict[str, Any]] = None

def load_mcp_cfg(path: str = "app/mcp/client.yaml") -> Dict[str, Any]:
    global _CFG_CACHE
    if _CFG_CACHE is not None:
        return _CFG_CACHE
    if not os.path.exists(path):
        _CFG_CACHE = {"enabled": False, "servers": {}}
        return _CFG_CACHE
    with open(path, "r") as f:
        _CFG_CACHE = yaml.safe_load(f) or {}
    return _CFG_CACHE

def mcp_enabled() -> bool:
    cfg = load_mcp_cfg()
    # allow env override
    env = os.getenv("MCP_ENABLED")
    if env is not None:
        return env.lower() in ("1", "true", "yes")
    return bool(cfg.get("enabled", False))

def fetch(server: str, resource: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """
    POC fetcher: calls simple HTTP JSON endpoints defined in client.yaml.
    Later you can replace this with a proper MCP client (JSON-RPC / streams).
    """
    cfg = load_mcp_cfg()
    servers = cfg.get("servers", {})
    if server not in servers:
        raise ValueError(f"MCP server '{server}' not configured")

    base = servers[server]["base_url"].rstrip("/")
    resources = servers[server].get("resources", {})
    if resource not in resources:
        raise ValueError(f"MCP resource '{server}:{resource}' not configured")

    path = resources[resource]
    url = f"{base}{path}"
    timeout = float(cfg.get("timeout_seconds", 3))

    resp = requests.get(url, params=params or {}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()

