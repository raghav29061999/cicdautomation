4.5 Agent Orchestration Layer

The orchestration layer coordinates how requests are processed by the various agents in the system.

For conversational queries, the request is passed to a Team Orchestrator, which determines which specialized agent should handle the request.

The orchestrator performs the following tasks:

Analyzes the user query

Determines the most suitable agent

Coordinates agent execution

Ensures tool usage follows defined safety constraints

This layer enables the system to operate as a multi-agent analytical platform, where different agents handle different analytical tasks.

4.6 Specialized Agent Layer

The system contains multiple specialized agents designed to perform specific analytical tasks.

Examples include:

General Purpose Agent

Handles standard analytical queries about the dataset.

Data Quality Agent

Identifies potential data quality issues such as missing values, duplicates, or inconsistencies.

Anomaly Detection Agent

Detects unusual patterns or statistical outliers within the dataset.

Insights Agent

Generates business-relevant analytical prompts for exploration.

Dashboard Agent

Produces a structured dashboard consisting of metrics, charts, and tables.

Each agent operates based on a defined set of instructions and tools that guide its reasoning and behavior.

4.7 Tooling Layer

Agents interact with external systems and perform operations through a set of controlled tools.

The tooling layer ensures that all operations performed by agents are safe, auditable, and restricted to allowed actions.

Key tools used in the system include:

SafePostgresTools

Executes read-only SQL queries against the PostgreSQL database.

Includes SQL validation to prevent unsafe operations.

ECharts Tools

Generates chart configuration JSON used to render visualizations on the frontend.

Data Quality Tools

Produces tabular summaries and analytical outputs related to dataset quality.

Tools act as the bridge between agent reasoning and system operations.

4.8 Data Access Layer

The data access layer manages interactions with the underlying PostgreSQL database.

Agents do not access the database directly. Instead, all database interactions occur through controlled tool interfaces.

The system enforces several safeguards:

Use of a read-only database role

SQL query validation

Prevention of data modification commands

Query execution through SafePostgresTools

These safeguards ensure that the AI system cannot perform destructive operations on the database.

4.9 Session Management Layer

The platform maintains contextual information across requests using a session management system.

Session information includes:

Selected table context

User interaction history

Request metadata

Agent responses

This information is stored in an event store, allowing the system to maintain state across multiple interactions and provide a consistent user experience.

4.10 Logging and Monitoring Layer

The logging layer provides observability into system behavior and helps diagnose issues during development and production.

The system uses structured logging via:

agno.utils.log

Logs capture key events such as:

API request lifecycle

SQL query execution

Agent decisions

Error conditions

Security events

Structured logging enables easier debugging, monitoring, and integration with centralized logging systems in production environments.
