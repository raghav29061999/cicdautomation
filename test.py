flowchart LR

%% === STYLES ===
classDef api fill:#E3F2FD,stroke:#1E88E5,stroke-width:2px,color:#0D47A1
classDef orchestrator fill:#E8F5E9,stroke:#43A047,stroke-width:2px,color:#1B5E20
classDef agent fill:#FFF3E0,stroke:#FB8C00,stroke-width:2px,color:#E65100
classDef tool fill:#F3E5F5,stroke:#8E24AA,stroke-width:2px,color:#4A148C
classDef db fill:#ECEFF1,stroke:#455A64,stroke-width:2px,color:#263238
classDef audit fill:#FFEBEE,stroke:#E53935,stroke-width:2px,color:#B71C1C

%% === FLOW ===
U[User or Swagger UI] --> API[FastAPI Chat API]

API --> TEAM[Agno Team Orchestrator<br/>Mode: Route]

TEAM --> A1[Agent 1<br/>General Query Agent]
TEAM --> A2[Agent 2<br/>Analytics Agent]
TEAM --> A3[Agent 3<br/>Data Integrity Agent]

A1 --> TOOL[Safe Postgres Tools<br/>Read Only Enforcement]
A2 --> TOOL
A3 --> TOOL

TOOL --> DB[(PostgreSQL Database<br/>Read Only Role)]
TOOL --> AUDIT[SQL Audit Logger<br/>Console Logs]

%% === CLASS ASSIGNMENT ===
class API api
class TEAM orchestrator
class A1,A2,A3 agent
class TOOL tool
class DB db
class AUDIT audit
