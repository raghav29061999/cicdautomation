app/agent/providers.py

import os
from typing import Dict, Any
from strands.models.openai import OpenAIModel

def make_model(model_cfg: Dict[str, Any]):
    """
    Build and return a Strands model from config.
    Supports OpenAI now; you can add Bedrock/Anthropic later.
    """
    provider = (model_cfg.get("provider") or "openai").lower()
    if provider != "openai":
        raise ValueError(f"Unsupported provider for this POC: {provider}")

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    return OpenAIModel(
        client_args={"api_key": api_key},
        model_id=model_cfg["model_id"],
        params=model_cfg.get("params", {"temperature": 0.0})
    )

------------------------------------------
app/agent/prompts_provider.py



import importlib
from typing import Any, Dict

class PromptProvider:
    """
    Loads .py prompt modules and calls their render(**ctx) -> str.
    """
    def __init__(self, module_prefix: str = "app.prompts"):
        self.module_prefix = module_prefix

    def render(self, name: str, **ctx: Dict[str, Any]) -> str:
        mod = importlib.import_module(f"{self.module_prefix}.{name}")
        return mod.render(**ctx)



--------------------------




app/agent/specialists/portfolio_monitor.py


from typing import Dict, Any
from strands import Agent
from app.agent.prompts_provider import PromptProvider

# Tools (deterministic, cheap)
from app.tools.io.load_client import load_client_positions
from app.tools.io.load_market import load_market_snapshot
from app.tools.portfolio.score import score_portfolio

class PortfolioMonitor:
    """
    Runs tool-first scoring; uses the model only to produce a short, clean summary.
    """
    def __init__(self, model, prompt_name: str, prompt_provider: PromptProvider):
        self.model = model
        self.prompt_name = prompt_name
        self.prompts = prompt_provider
        # Minimal agent; we don't register tools here to keep the loop lean
        self.agent = Agent(model=model, tools=[], name="PortfolioMonitor")

    def run(self, client_id: str, client_name: str) -> Dict[str, Any]:
        positions = load_client_positions(client_id)
        market = load_market_snapshot()
        score = score_portfolio(positions, market)

        # one short LLM polish (optional)
        prompt = self.prompts.render(
            self.prompt_name,
            client_name=client_name,
            positions=positions,
            market=market
        )
        summary = str(self.agent(prompt))  # small token use

        return {"score": score, "summary": summary}
--------------------------

app/agent/specialists/recommender.py



from typing import Dict, Any, List
from strands import Agent
from app.agent.prompts_provider import PromptProvider

# Tools
from app.tools.recommend.rules import recommend_rebalance, tailor_to_profile
from app.tools.recommend.formulate import format_recommendations_bullets

class Recommender:
    """
    Generates rule-based recos; uses model only to lightly refine if needed.
    """
    def __init__(self, model, prompt_name: str, prompt_provider: PromptProvider):
        self.model = model
        self.prompt_name = prompt_name
        self.prompts = prompt_provider
        self.agent = Agent(model=model, tools=[], name="Recommender")

    def run(self, profile: Dict[str, Any], score: Dict[str, Any]) -> Dict[str, Any]:
        base = recommend_rebalance(score)                # list[str]
        tailored = tailor_to_profile(profile, base)      # list[str]
        bullets = format_recommendations_bullets(tailored)

        # Optional polish (very short)
        prompt = self.prompts.render(
            self.prompt_name,
            client_name=profile.get("name", ""),
            profile=profile,
            score=score
        )
        _ = str(self.agent(prompt))  # not strictly needed; keep for symmetry

        return {"recommendations": tailored, "bullets": bullets}


---------------
app/agent/specialists/pitch_writer.py


from typing import Dict, Any
from strands import Agent
from app.agent.prompts_provider import PromptProvider
from app.tools.compliance import compliance_sanitize

class PitchWriter:
    """
    Turns findings + recos into a short client pitch and runs compliance pass.
    """
    def __init__(self, model, prompt_name: str, prompt_provider: PromptProvider):
        self.model = model
        self.prompt_name = prompt_name
        self.prompts = prompt_provider
        self.agent = Agent(model=model, tools=[], name="PitchWriter")

    def run(self, client_name: str, findings: str, recos_bullets: str) -> Dict[str, Any]:
        prompt = self.prompts.render(
            self.prompt_name,
            client_name=client_name,
            findings=findings,
            recos=recos_bullets
        )
        draft = str(self.agent(prompt))
        final = compliance_sanitize(draft)
        return {"pitch": final}


----------


app/agent/orchestrator.py

from typing import Dict, Any
from strands import Agent
from app.agent.prompts_provider import PromptProvider

# Tools (cheap IO)
from app.tools.io.load_client import load_client_profile

# Specialists
from app.agent.specialists.portfolio_monitor import PortfolioMonitor
from app.agent.specialists.recommender import Recommender
from app.agent.specialists.pitch_writer import PitchWriter

class Orchestrator:
    """
    Coordinates specialists. Uses LLM minimally for stitching.
    """
    def __init__(self, model, prompts: PromptProvider, cfg: Dict[str, Any]):
        self.model = model
        self.prompts = prompts
        self.cfg = cfg
        self.agent = Agent(model=model, tools=[], name="Orchestrator")

        # Build specialists per config
        self.portfolio_monitor = PortfolioMonitor(
            model, cfg["agents"]["portfolio_monitor"]["prompt"], prompts
        )
        self.recommender = Recommender(
            model, cfg["agents"]["recommender"]["prompt"], prompts
        )
        self.pitch_writer = PitchWriter(
            model, cfg["agents"]["pitch"]["prompt"], prompts
        )

    def run(self, client_id: str) -> Dict[str, Any]:
        profile = load_client_profile(client_id)
        client_name = profile.get("name") or profile.get("client_id", client_id)

        # 1) Portfolio assessment
        pm = self.portfolio_monitor.run(client_id=client_id, client_name=client_name)

        # 2) Recommendations
        rec = self.recommender.run(profile=profile, score=pm["score"])

        # 3) Final pitch
        pitch = self.pitch_writer.run(
            client_name=client_name,
            findings=pm["summary"],
            recos_bullets=rec["bullets"]
        )

        return {
            "client": profile,
            "portfolio": pm,
            "recommendations": rec,
            "pitch": pitch["pitch"]
        }


-----------


app/agent/factory.py

import yaml
from typing import Dict, Any
from app.agent.providers import make_model
from app.agent.prompts_provider import PromptProvider
from app.agent.orchestrator import Orchestrator

def load_cfg(path: str = "configs/base.yaml") -> Dict[str, Any]:
    with open(path, "r") as f:
        return yaml.safe_load(f)

def build_agents(cfg: Dict[str, Any]):
    """
    Entry point used by your API.
    Returns a dict of agents keyed by name.
    """
    model = make_model(cfg["model"])
    prompts = PromptProvider()

    orchestrator = Orchestrator(model, prompts, cfg)

    # If you want direct specialist access via API (optional), expose them too:
    return {
        "orchestrator": orchestrator,
        # "portfolio_monitor": orchestrator.portfolio_monitor,
        # "recommender": orchestrator.recommender,
        # "pitch_writer": orchestrator.pitch_writer,
    }
