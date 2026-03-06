5. Agent Architecture

The AI Analytics Backend uses a multi-agent architecture powered by Agno AgentOS.
Each agent is designed to perform a specialized analytical task while sharing access to common tools and infrastructure.

This modular design allows the system to remain extensible, enabling new agents to be added without modifying existing components.

Agents operate using the following structure:

Instructions – Define the reasoning and behavior of the agent

Tools – Provide controlled access to external systems such as databases or chart generation utilities

LLM Model – Responsible for reasoning and generating responses

Session Context – Maintains state across interactions

The orchestration layer routes requests to the appropriate agent based on the nature of the task.

5.1 Team Orchestrator

The Team Orchestrator is responsible for coordinating the execution of agents within the system.

When a request is received from the /api/chat endpoint, the orchestrator analyzes the query and determines which specialized agent should handle the request.

Responsibilities include:

Determining the appropriate agent for a given query

Managing agent execution flow

Passing contextual information such as selected tables

Aggregating responses when necessary

The orchestrator ensures that requests are handled efficiently and that agents operate within their defined scope.

5.2 General Purpose Agent

The General Purpose Agent handles standard analytical queries submitted through the chat interface.

Typical queries processed by this agent include:

Aggregation queries

Filtering and grouping operations

Basic exploratory data analysis

Data summaries and trends

The agent converts natural language requests into safe SQL queries using the available database tools.

5.3 Data Quality Agent

The Data Quality Agent is responsible for analyzing and reporting issues related to data integrity.

It performs checks such as:

Missing value analysis

Duplicate detection

Consistency checks across columns

Distribution analysis

The agent generates structured outputs, often in the form of markdown tables, which can be rendered directly in the frontend.

5.4 Anomaly Detection Agent

The Anomaly Detection Agent identifies unusual patterns or outliers within datasets.

This agent is used to detect:

Unexpected spikes or drops in data

Statistical outliers

Abnormal distributions

Deviations from expected patterns

These insights can help users quickly identify potential problems or hidden trends in the data.

5.5 Insights Agent

The Insights Agent generates a curated set of analytical prompts for a selected table.

These prompts help guide users toward meaningful analysis by suggesting relevant questions such as:

Trends in key metrics

Distribution of categorical values

Temporal changes in important fields

The generated prompts are displayed in the Insights tab and can be executed directly by the user.

5.6 Dashboard Agent

The Dashboard Agent is responsible for generating a structured analytical dashboard for a selected table.

The dashboard typically includes:

Key metrics derived from the dataset

Visualizations such as bar charts or line charts

Tabular summaries of important data characteristics

Column descriptions and analytical insights

The agent utilizes ECharts tools to produce visualization configurations that are rendered by the frontend.

6. API Endpoints

The backend exposes several REST endpoints that allow the frontend to interact with the agent system.

These APIs serve as the primary interface between the user interface and the AI-powered analytical engine.

6.1 Chat API

Endpoint

POST /api/chat

Purpose

Handles conversational data queries submitted by users.

Workflow

The user submits a natural language query.

The request is validated and authenticated.

The request is routed to the Team Orchestrator.

The orchestrator selects the appropriate agent.

The agent executes the query using available tools.

The response is returned to the user.

6.2 Insights API

Endpoint

GET /api/insights/prompts

Purpose

Generates a set of analytical prompts based on the schema and characteristics of the selected table.

Workflow

The frontend sends the selected table name.

The Insights Agent analyzes the table structure.

The agent generates a set of relevant analytical prompts.

These prompts are returned to the frontend.

6.3 Dashboard API

Endpoint

GET /api/dashboard

Purpose

Generates a complete analytical dashboard for the selected table.

Workflow

The frontend sends the selected table name.

The Dashboard Agent analyzes the table schema and data.

Key metrics and visualizations are generated.

The resulting dashboard configuration is returned as JSON.

6.4 Authentication API

Endpoint

POST /api/auth/login

Purpose

Authenticates users and generates JWT tokens used to secure API endpoints.

Workflow

User submits credentials.

Backend validates credentials.

A signed JWT token is generated.

The token must be included in future API requests.

9. Session and Context Handling

The backend maintains session context to ensure consistent interactions across multiple API calls.

Session information includes:

Selected table context

User session identifiers

Agent responses

Event history

This contextual information allows the system to maintain continuity between interactions, especially in conversational workflows.

Session data is stored using an InMemoryEventStore, which records events associated with a given session identifier.

Examples of session events include:

Chat requests and responses

Dashboard generation requests

Insights generation events

This mechanism enables the system to reconstruct interaction history when necessary.

10. Error Handling and Fallback Strategy

The system implements structured error handling to ensure robustness and user-friendly responses.

Error handling occurs at multiple layers of the architecture.

API Layer

The API layer validates incoming requests and handles exceptions using standardized HTTP responses.

Common error types include:

Invalid request parameters

Authentication failures

Rate limit violations

Internal server errors

Agent Execution Layer

Agents may encounter errors while generating queries or processing data.

Examples include:

Invalid SQL generation

Tool execution failures

Unexpected tool outputs

Fallback mechanisms ensure that these errors do not propagate to the user in an uncontrolled manner.

Database Layer

Database operations are executed through validated tools.

If an SQL query fails validation or execution, the system logs the error and returns a safe response.

Logging and Observability

All errors are logged using structured logging mechanisms, allowing developers to diagnose issues and monitor system health.

11. Security Architecture

Security is a critical component of the AI Analytics Backend, particularly because the system interacts directly with database systems.

Several security mechanisms are implemented to protect the platform.

11.1 JWT Authentication

The system uses JSON Web Tokens (JWT) to authenticate users and protect API endpoints.

Users must obtain a JWT token through the login endpoint before accessing the analytics APIs.

The token is included in API requests using the HTTP Authorization header.

Example:

Authorization: Bearer <access_token>

The backend validates the token for:

Signature integrity

Expiration time

Valid payload structure

Requests without a valid token are rejected.

11.2 Rate Limiting

To prevent abuse and protect system resources, API endpoints enforce rate limiting.

Rate limiting restricts the number of requests a user can make within a defined time window.

If a user exceeds the allowed request rate, the system returns an HTTP 429 error.

This helps prevent denial-of-service attacks and protects the AI agents from excessive workload.

11.3 API Protection

All analytical endpoints require authentication before processing requests.

Protected endpoints include:

Chat API

Insights API

Dashboard API

Authentication checks occur before the request reaches the agent orchestration layer, ensuring that unauthorized users cannot access sensitive data or system resources.

If you want, I can also generate the next section (12–15) in a more "enterprise
