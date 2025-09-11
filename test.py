client_id,name,risk,horizon,goals,pos_SPY,pos_AGG,pos_VXUS
C-1001,Ada Moderate,moderate,5y,"retirement, college",60,30,10


{"volatility": {"SPY": 0.16, "AGG": 0.05, "VXUS": 0.18}}


from dotenv import load_dotenv
load_dotenv()  # Load OPENAI_API_KEY and any other env vars early

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.factory import load_cfg, build_agents
from app.api.http import router as api_router


def create_app() -> FastAPI:
    # Load config (configs/base.yaml by default)
    cfg = load_cfg("configs/base.yaml")

    # Build agents (orchestrator + specialists as exposed by factory)
    agents = build_agents(cfg)

    app = FastAPI(
        title="Financial Multi-Agent POC",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # (Optional) CORS for local tools/UI
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # tighten for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Attach state for dependency injection
    app.state.cfg = cfg
    app.state.agents = agents

    # Mount API routes
    app.include_router(api_router)

    return app


# FastAPI entrypoint
app = create_app()
