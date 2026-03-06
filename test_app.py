4. Application Architecture Layers

The backend system follows a layered architecture that separates responsibilities across distinct functional layers. This design improves maintainability, scalability, and security by ensuring that each layer handles a specific set of responsibilities.

Requests flow through the system sequentially, starting from the client layer and moving through the API, orchestration, agent, and data layers before returning a structured response to the user.

The major architecture layers are described below.

4.1 Client Layer (Frontend UI)

The client layer represents the user-facing interface that interacts with the backend APIs. The frontend application provides a simplified analytics experience through three main modules:

Chat Interface

Allows users to ask natural language questions about a selected table.

The system converts the query into a safe SQL query and returns structured responses such as textual summaries, charts, or tables.

Insights Interface

Displays automatically generated analytical prompts for the selected table.

These prompts help users explore the dataset without requiring SQL knowledge.

Dashboard Interface

Generates a default analytical dashboard for the selected table.

Includes metrics, visualizations, and tabular summaries derived from the table schema and data.

The frontend communicates with the backend exclusively through REST APIs exposed by the FastAPI server.

4.2 API Layer (FastAPI)

The API layer acts as the entry point into the backend system and exposes endpoints used by the frontend.

The API layer is implemented using FastAPI, which provides request validation, dependency injection, and automatic API documentation.

The primary API endpoints include:

Endpoint	Purpose
/api/chat	Handles natural language data queries
/api/insights/prompts	Generates analytical prompts for a table
/api/dashboard	Generates a default dashboard for a table
/api/auth/login	Authenticates users and issues JWT tokens

The API layer performs several critical functions:

Request validation using Pydantic models

Authentication and authorization

Session management

Dependency injection for agents and services

Request logging and tracing

Error handling and response formatting

After validation, requests are routed to the agent orchestration layer for further processing.

4.3 Authentication & Security Layer

To protect the system from unauthorized access, the backend implements a JWT-based authentication mechanism.

Users must first authenticate using the login endpoint to obtain a JSON Web Token (JWT). This token must then be included in subsequent API requests using the HTTP Authorization header.

Example header:

Authorization: Bearer <access_token>

Security measures implemented in this layer include:

JWT token validation

Protected API endpoints

Optional rate limiting

Secure environment configuration for credentials

This ensures that only authenticated users can access the analytics functionality.

4.4 Dependency Injection Layer

The system uses FastAPI’s dependency injection mechanism to manage shared components across the application.

This layer is responsible for initializing and providing access to core services such as:

Agent teams

Insights agent

Dashboard agent

Event store

Database tools

The dependency injection system ensures that these components are initialized once a
