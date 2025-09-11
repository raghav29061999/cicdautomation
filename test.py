# app/api/routes.py
from fastapi import APIRouter, Depends, HTTPException, Request
from .schemas import (
    PitchRequest, PitchResponse, PortfolioScoreRequest,
    PortfolioMonitorResult, PortfolioScore, ClientProfile, RecommendationsResult
)

router = APIRouter()

def get_agents(request: Request):
    agents = getattr(request.app.state, "agents", None)
    if not agents or "orchestrator" not in agents:
        raise HTTPException(status_code=500, detail="Agents not initialized")
    return agents

@router.get("/health")
def health():
    return {"status": "ok"}

@router.post("/pitch", response_model=PitchResponse)
def make_pitch(req: PitchRequest, agents = Depends(get_agents)):
    result = agents["orchestrator"].run(client_id=req.client_id)

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
    orchestrator = agents["orchestrator"]
    pm = orchestrator.portfolio_monitor.run(
        client_id=req.client_id, client_name=req.client_id
    )
    return PortfolioMonitorResult(
        score=PortfolioScore(**pm["score"]),
        summary=pm.get("summary", "")
    )












-----------





# app/main.py
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

def create_app() -> FastAPI:
    # Lazy imports to avoid any circulars
    from app.agent.factory import load_cfg, build_agents
    from app.api.routes import router as api_router

    cfg = load_cfg("configs/base.yaml")
    agents = build_agents(cfg)

    fa = FastAPI(title="Financial Multi-Agent POC", version="0.1.0")
    fa.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    fa.state.cfg = cfg
    fa.state.agents = agents
    fa.include_router(api_router)

    return fa

app = create_app()










