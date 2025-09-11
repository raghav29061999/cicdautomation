flowchart LR
    %% Shapes legend:
    %% ( )  = rounded terminator (start/end)
    %% [[ ]] = subroutine (API or function block)
    %% [ ]   = process step
    %% (( )) = circle (agent or model)
    %% { }   = decision
    %% [( )] = data store

    A([Start]) --> B[[API routes]]
    B --> C[Validate request]
    C --> D{Client exists}
    D -- yes --> E[[Load config and agents]]
    D -- no --> Z([Error response])

    E --> F((Orchestrator agent))
    F --> G[[Portfolio monitor]]
    G --> H[Read client positions]
    H --> I[(Clients data)]
    G --> J[Read market snapshot]
    J --> K[(Market data)]
    G --> L[Compute weights and volatility]
    L --> M[Compute concentration and grade]
    M --> N[[Short summary]]

    N --> O((LLM model))
    O --> P[Summary ready]

    P --> Q[[Recommender]]
    Q --> R[Apply rules]
    R --> S[Tailor to profile]
    S --> T[Format bullets]

    T --> U[[Pitch writer]]
    U --> V((LLM model))
    V --> W[Compliance sanitize]
    W --> X([OK response])
