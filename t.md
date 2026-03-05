flowchart LR

subgraph UI[Client UI]
  U[User]
  ChatUI[Chat UI]
  InsightsTab[Insights Tab]
  DashboardUI[Dashboard UI]
end

subgraph API1[API 1: Chat]
  ChatAPI[Chat API Endpoint]
  Orch[Orchestrator]
  Router{Select best agent}
  A1[Agent 1]
  A2[Agent 2]
  A3[Agent 3]
  SQLGen[Generate SQL]
  Auditor{SQL Auditor read-only?}
  Block[BLOCK write detected]
  Exec[Execute SQL]
end

DB[(Database)]

subgraph API2[API 2: Insights]
  InsightsAPI[Insights API Endpoint]
  InsightsAgents[Insights Agents]
  Prompts[Prompt List]
end

subgraph API3[API 3: Dashboard]
  DashAPI[Dashboard API Endpoint]
  MetricQueries[Run metric queries]
  Charts[Build charts and notes]
end

%% Chat flow
U --> ChatUI --> ChatAPI --> Orch --> Router
Router --> A1 --> SQLGen
Router --> A2 --> SQLGen
Router --> A3 --> SQLGen
SQLGen --> Auditor
Auditor -->|NO| Block --> ChatAPI
Auditor -->|YES| Exec --> DB --> ChatAPI --> ChatUI

%% Insights flow
U --> InsightsTab --> InsightsAPI --> InsightsAgents --> Prompts --> InsightsTab
InsightsTab -->|Select prompt| ChatAPI

%% Dashboard flow
U --> DashboardUI --> DashAPI --> MetricQueries --> DB --> Charts --> DashAPI --> DashboardUI
