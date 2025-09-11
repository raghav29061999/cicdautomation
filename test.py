from typing import Dict, Any, List, Optional
from pydantic import BaseModel, field_validator


# ---------- Requests ----------
class PitchRequest(BaseModel):
    client_id: str
    # Optional overrides if you want to bypass CSV defaults during demo
    goals: Optional[str] = None
    risk: Optional[str] = None

class PortfolioScoreRequest(BaseModel):
    client_id: str


# ---------- Responses ----------
class PortfolioScore(BaseModel):
    weights: Dict[str, float]
    volatility: float
    concentration: Dict[str, float]
    grade: str

class PortfolioMonitorResult(BaseModel):
    score: PortfolioScore
    summary: str

class RecommendationsResult(BaseModel):
    recommendations: List[str]
    bullets: str

class ClientProfile(BaseModel):
    client_id: str
    name: str
    risk: str
    horizon: str
    goals: str

class PitchResponse(BaseModel):
    client: ClientProfile
    portfolio: PortfolioMonitorResult
    recommendations: RecommendationsResult
    pitch: str


# ---------- helpers (nice-to-have) ----------
class _NullableFloats(BaseModel):
    a: Optional[float] = None
    b: Optional[float] = None

    @field_validator("a", "b", mode="before")
    @classmethod
    def empty_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


=-----------

app/api/http.py
from fastapi import APIRouter, Depends, HTTPException, Request
from .schemas import (
    PitchRequest, PitchResponse, PortfolioScoreRequest,
    PortfolioMonitorResult, PortfolioScore, ClientProfile, RecommendationsResult
)

router = APIRouter()


def get_agents(request: Request):
    """Read orchestrator from app state (set in main.py)."""
    agents = getattr(request.app.state, "agents", None)
    if not agents or "orchestrator" not in agents:
        raise HTTPException(status_code=500, detail="Agents not initialized")
    return agents


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/pitch", response_model=PitchResponse)
def make_pitch(req: PitchRequest, agents = Depends(get_agents)):
    """
    High-level orchestration endpoint:
    - loads client profile (from CSV)
    - runs portfolio monitor (tools-first)
    - runs recommender (rules + format)
    - composes final pitch (short LLM pass + compliance)
    """
    result = agents["orchestrator"].run(client_id=req.client_id)

    # shape result to response model
    profile = result["client"]
    pm = result["portfolio"]
    rec = result["recommendations"]

    return PitchResponse(
        client=ClientProfile(
            client_id=profile.get("client_id", req.client_id),
            name=profile.get("name", ""),
            risk=profile.get("risk", "moderate"),
            horizon=profile.get("horizon", "5y"),
            goals=profile.get("goals", "")
        ),
        portfolio=PortfolioMonitorResult(
            score=PortfolioScore(**pm["score"]),
            summary=pm.get("summary", "")
        ),
        recommendations=RecommendationsResult(
            recommendations=rec.get("recommendations", []),
            bullets=rec.get("bullets", "")
        ),
        pitch=result.get("pitch", "")
    )


@router.post("/portfolio/score", response_model=PortfolioMonitorResult)
def portfolio_score(req: PortfolioScoreRequest, agents = Depends(get_agents)):
    """
    Direct access to portfolio monitor (useful for demos or budget-saving paths).
    """
    orchestrator = agents["orchestrator"]
    pm = orchestrator.portfolio_monitor.run(
        client_id=req.client_id, client_name=req.client_id
    )
    return PortfolioMonitorResult(
        score=PortfolioScore(**pm["score"]),
        summary=pm.get("summary", "")
    )
