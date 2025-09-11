Happy Path Flow (flowchart)

“Here’s the happy path of our Strands POC when someone calls the /pitch API:

Request comes in → The API route gets the request (say client_id=C-1001).

Validation → FastAPI and our Pydantic schemas check if the request is valid and if the client exists in our demo data. If not, we immediately return an error.

Setup → If valid, we load our config (model, tools, prompts) and build the agents.

Orchestrator takes over → The Orchestrator agent coordinates the rest of the flow.

Portfolio Monitor

Reads client positions from CSV.

Reads market snapshot from JSON.

Computes diversification, volatility, and grade using tools.

Calls the LLM briefly to generate a short, human-friendly summary.

Recommender

Applies simple rule-based recommendations.

Tailors them to the client’s risk profile and horizon.

Formats them into concise bullet points.

Pitch Writer

Uses the LLM again, but only for short synthesis, to turn findings + bullets into a client-facing pitch.

Finally, runs a compliance check to strip risky language and add disclaimers.

Response → The orchestrator bundles everything (client profile, portfolio findings, recommendations, final pitch) and sends it back as JSON.

👉 The key point: tools do the heavy lifting; LLM only polishes and stitches. That keeps it modular, predictable, and cost-efficient.”




-----------------


Sequence Flow (sequenceDiagram)

“Now let’s look at the sequence of calls — how different parts talk to each other when generating a pitch:

Postman → FastAPI: We send a POST /pitch with a client ID.

FastAPI → Orchestrator: The request is handed over to our Orchestrator agent.

Orchestrator → PortfolioMonitor: Orchestrator first asks the Portfolio Monitor to run.

Portfolio Monitor fetches client positions and market snapshot using tools.

Tools compute weights, volatility, grade.

Portfolio Monitor calls the OpenAI model just for a short polish, producing a plain-English summary.

Orchestrator → Recommender: Next, the Orchestrator passes the client profile + score to the Recommender.

Recommender uses tools to apply rules, tailor them, and format them into bullet points.

Orchestrator → PitchWriter: Finally, the Orchestrator calls the Pitch Writer.

Pitch Writer uses OpenAI to generate a short client-facing pitch.

Runs compliance tool to sanitize the language and add disclaimers.

Return: Orchestrator collects client info, portfolio summary, recommendations, and pitch → returns JSON back to FastAPI, which sends a 200 OK response to Postman.

👉 This shows the orchestration clearly:

Tools first (deterministic, cheap).

LLM second (small calls for summaries/pitches).

Compliance last (safe output).

That’s how Strands keeps the flow modular and budget-friendly.”
