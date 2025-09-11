Mermaid Sequence - Request Response Token-light
sequenceDiagram
    participant Postman
    participant FastAPI as FastAPI (/pitch)
    participant Orchestrator
    participant PM as PortfolioMonitor
    participant RC as Recommender
    participant PW as PitchWriter
    participant Tools as Tools (@tool)
    participant OAI as Strands.OpenAIModel

    Postman->>FastAPI: POST /pitch {client_id}
    FastAPI->>Orchestrator: run(client_id)
    Orchestrator->>PM: run(client_id, client_name)
    PM->>Tools: load_client_positions, load_market_snapshot
    Tools-->>PM: positions, market
    PM->>Tools: score_portfolio (weights, vol, grade)
    Tools-->>PM: score dict
    PM->>OAI: prompt(portfolio_monitor)  (short polish)
    OAI-->>PM: summary
    Orchestrator->>RC: run(profile, score)
    RC->>Tools: recommend_rebalance, tailor_to_profile, format_bullets
    Tools-->>RC: list + bullets
    Orchestrator->>PW: run(client_name, findings, bullets)
    PW->>OAI: prompt(pitch)  (short synth)
    OAI-->>PW: draft pitch
    PW->>Tools: compliance_sanitize
    Tools-->>PW: compliant pitch
    Orchestrator-->>FastAPI: {client, portfolio, recs, pitch}
    FastAPI-->>Postman: 200 OK (JSON)

-------


flowchart LR
    subgraph Client["Client - Postman or UI"]
      RQ[POST pitch\nclient_id=C-1001]
    end

    subgraph API["FastAPI"]
      RT[api routes\nrouters for pitch and portfolio_score]
      SC[api schemas\nPydantic models]
    end

    subgraph Core["App Core"]
      MN[main py\ncreate_app\nload env and cfg\nbuild agents]
      CFG[configs base yaml\nmodel and agents\ntools and budget]
    end

    subgraph Orchestrator["Strands Orchestrator Agent"]
      ORC[orchestrator py\nOrchestrator run]
      PRV[providers py\nOpenAIModel]
      PP[prompts_provider py\nrender prompt_name ctx]
    end

    subgraph Specialists["Specialist Agents"]
      PM[PortfolioMonitor\nspecialists portfolio_monitor py]
      RC[Recommender\nspecialists recommender py]
      PW[PitchWriter\nspecialists pitch_writer py]
    end

    subgraph Prompts["Prompts - py files"]
      P_ORC[orchestrator prompt]
      P_PM[portfolio_monitor prompt]
      P_RC[recommender prompt]
      P_PW[pitch prompt]
    end

    subgraph Tools["Deterministic Tools - Strands @tool"]
      T_IO_CLI[load_client_profile\nload_client_positions]
      T_IO_MKT[load_market_snapshot]
      T_WT[compute_weights]
      T_RISK[estimate_portfolio_volatility\nconcentration_flags]
      T_SCORE[score_portfolio]
      T_RULES[recommend_rebalance\ntailor_to_profile]
      T_FMT[format_recommendations_bullets]
      T_COMP[compliance_sanitize]
    end

    subgraph Data["Demo Data"]
      CSV[clients csv]
      MKT[market json]
    end

    subgraph Provider["Model Provider via Strands"]
      OAI[OpenAI\nmodel gpt-4o-mini\nparams temperature=0\nmax_tokens=256]
    end

    %% Wiring
    RQ --> RT
    RT --> SC
    RT --> MN
    MN --> CFG
    MN --> ORC
    ORC --> PRV
    ORC --> PP
    PRV --> OAI

    %% Orchestration path
    ORC --> PM
    PM --> T_IO_CLI
    PM --> T_IO_MKT
    PM --> T_SCORE
    T_IO_CLI --> CSV
    T_IO_MKT --> MKT
    T_SCORE --> T_WT
    T_SCORE --> T_RISK

    ORC --> RC
    RC --> T_RULES
    RC --> T_FMT

    ORC --> PW
    PW --> T_COMP

    %% Prompts used at each agent
    ORC --> P_ORC
    PM --> P_PM
    RC --> P_RC
    PW --> P_PW

    %% Return
    ORC --> RT




