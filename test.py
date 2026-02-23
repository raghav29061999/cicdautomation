flowchart LR
    %% Styling
    classDef api fill:#E3F2FD,stroke:#1E88E5,stroke-width:2px,color:#0D47A1
    classDef orchestrator fill:#E8F5E9,stroke:#43A047,stroke-width:2px,color:#1B5E20
    classDef agent fill:#FFF3E0,stroke:#FB8C00,stroke-width:2px,color:#E65100
    classDef tool fill:#F3E5F5,stroke:#8E24AA,stroke-width:2px,color:#4A148C
    classDef db fill:#ECEFF1,stroke:#455A64,stroke-width:2px,color:#263238
    classDef audit fill:#FFEBEE,stroke:#E53935,stroke-width:2px,color:#B71C1C

    %% User Layer
    U[User / Swagger UI] --> API[/FastAPI Chat Endpoint/]
    class API api

    %% Orchestration Layer
    API --> TEAM[Agno Team Orchestrator\n(mode = route)]
    class TEAM orchestrator

    %% Agents
    TEAM --> A1[Agent 1\n(General Query Agent)]
    TEAM --> A2[Agent 2\n(Analytics Agent)]
    TEAM --> A3[Agent 3\n(Data Integrity Agent)]
    class A1,A2,A3 agent

    %% Tool Layer
    A1 --> TOOL[SafePostgresTools\n(Read-Only Enforced)]
    A2 --> TOOL
    A3 --> TOOL
    class TOOL tool

    %% DB Layer
    TOOL --> DB[(PostgreSQL\nRead-Only Role)]
    class DB db

    %% Audit
    TOOL --> AUDIT[SQL Audit Logger\n(Console Structured Logs)]
    class AUDIT audit
