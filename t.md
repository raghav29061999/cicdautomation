API Testing

This project tests two HTTP APIs with pytest and HTTPX for smoke and contract checks, and k6 for load regressions. The same pytest suite runs directly in Python, Docker, or Podman. The commands below are the intended interface for the project once the test files and container image are implemented.

|Target|Access   |Request path                                                                                      |
|------|---------|--------------------------------------------------------------------------------------------------|
|`abc` |Unsecured|The test runner calls the backend directly.                                                       |
|`def` |Secured  |The test runner obtains a token and calls the secured API. That API calls `abc` behind the scenes.|

Project structure

api-tests/
├── .env                         # Local URLs, endpoint paths, and credentials
├── .env.example                 # Committed template with placeholders
├── .gitignore
├── .dockerignore
├── Dockerfile                   # Shared by Docker and Podman
├── pyproject.toml
├── README.md
├── api_testing/
│   ├── __init__.py
│   ├── settings.py
│   ├── client.py
│   └── auth.py
├── tests/
│   ├── conftest.py
│   ├── smoke/
│   │   ├── test_health.py
│   │   ├── test_readiness.py
│   │   └── test_auth.py
│   └── contract/
│       └── test_chat.py
├── schemas/
│   ├── chat-success.schema.json
│   └── chat-error.schema.json
├── testdata/
│   └── chat/
│       └── requests.json
└── load/
    ├── chat.js
    └── profiles.json

Environment setup

Copy .env.example to .env and fill in the actual base URLs, endpoint paths, and auth settings. Configure the auth method, request fields, token response field, and token header in auth.py according to the working Insomnia request. The credentials below are example variable names for a client-credentials flow. Use the names and fields that match your API. If the token endpoint lives on a separate host, put its full URL in DEF_AUTH_URL.

ABC_BASE_URL=
ABC_HEALTH_PATH=
ABC_READINESS_PATH=
ABC_CHAT_PATH=

DEF_BASE_URL=
DEF_AUTH_URL=
DEF_HEALTH_PATH=
DEF_READINESS_PATH=
DEF_CHAT_PATH=
DEF_CLIENT_ID=
DEF_CLIENT_SECRET=

For local Python, load .env with python-dotenv and give existing environment variables precedence. Docker and Podman read the same file on the host and inject its values at startup through --env-file. Add .env to both ignore files and commit only .env.example. Keep credentials and access tokens out of logs and reports.

Phase 1 — Health, readiness, and auth

|Target|Request sequence                                                                                          |
|------|----------------------------------------------------------------------------------------------------------|
|`abc` |Call health and readiness directly.                                                                       |
|`def` |Call the auth endpoint, validate and extract the token, then use that token for both health and readiness.|

• Check the status and response fields defined by each endpoint’s contract. Check health and readiness independently so a health failure still leaves a readiness result.
• For def, use a session-scoped fixture to attempt auth once per pytest process. Let test_auth.py report the outcome and let both probe tests reuse it. A probe run by itself still authenticates.
• If auth fails, report it as failed and mark both secured probes as blocked by auth. When implementing the fixture, ensure a standalone secured probe run also returns a failing exit status for auth failure, even if test_auth.py was excluded. On abc, the auth test is inapplicable.
• Validate required configuration for the selected target and phase up front. A missing required probe route or credential should fail with the variable name and omit its value.

Phase 2 — Chat contract and load regression

Chat contract with pytest

Call the configured chat route for each target that exposes it. Reuse client.py and the def auth fixture. Use representative payloads from testdata/chat/requests.json.

• Validate a successful response against the success schema and a malformed request’s response against the documented error schema. If the two APIs have different contracts, use target-specific schemas.
• Check expected status codes and required fields. Assert a follow-up turn when the API supports sessions, and isolate session IDs across tests.
• If chat streams, validate the documented event format and completion signal separately from any non-streaming JSON response contract.

Load regression with k6

Use def for the end-to-end benchmark. If abc exposes chat, run it separately for a backend baseline. Running both together would put additional traffic on the same backend.

• Begin with a low-rate profile. After it passes, run the configured target profile against a stable test environment. Set the target profile to 30 requests per second if that is the agreed target. Use a constant-arrival-rate scenario with one chat request per iteration.
• Obtain and validate the def token in k6 setup, outside the timed chat iterations. For the initial implementation, make sure the token stays valid for the entire run, including warm-up.
• Check status, parseability, and critical response fields under load. Set thresholds for p95 latency, HTTP failures, response check failures, and dropped iterations. Report actual throughput and compare it with the configured rate.
• Record the target, environment, profile, build, and measured results. Use a repeatable baseline to set regression limits. If the API streams, measure time to first content and total completion time with a streaming-capable client.

Run locally

Run from the repository root after implementing the files above.

Python

Create and activate a virtual environment, then install the project and its test dependencies.

python -m pip install -e .
python -m pytest tests/smoke --target abc
python -m pytest tests/smoke --target def
python -m pytest tests/contract --target def

Docker and Podman

Use python -m pytest as the Dockerfile entry point. Pass the test path and target as container arguments.

docker build -t api-tests .
docker run --rm --env-file .env api-tests tests/smoke --target abc
docker run --rm --env-file .env api-tests tests/smoke --target def
docker run --rm --env-file .env api-tests tests/contract --target def

podman build -t api-tests .
podman run --rm --env-file .env api-tests tests/smoke --target abc
podman run --rm --env-file .env api-tests tests/smoke --target def
podman run --rm --env-file .env api-tests tests/contract --target def

With Podman Desktop, use the same commands once the Podman engine is running. If def only works in Insomnia, compare its auth flow, VPN, DNS, proxy, and TLS settings from the environment where the test actually runs. Container network and certificate settings may differ from the host’s.

k6

For native k6, export the relevant .env values into the invoking shell before running the scenario. For a container run, pass --env-file .env and mount only the script, profile, and request-fixture directories.

k6 run -e TARGET=def -e PROFILE=smoke load/chat.js

docker run --rm --env-file .env -e TARGET=def -e PROFILE=smoke \
  -v "$PWD/load:/work/load:ro" \
  -v "$PWD/testdata:/work/testdata:ro" \
  -w /work grafana/k6 run load/chat.js

For Podman, use the same command with podman run. The scenario reads configuration from __ENV, resolves profiles from load/profiles.json, and loads payloads from testdata/chat/requests.json.

GitHub Enterprise Actions

Add .github/workflows/api-tests.yml for smoke and chat contract checks and .github/workflows/api-load.yml for a separate manual or scheduled load job. Use the same variables as local runs. Supply URLs and paths through environment configuration and credentials through Actions secrets or the organization’s approved secret store.

Run the functional workflow after deployment to a test environment or on demand. Run load manually until the baseline is stable. The runner must reach the relevant API hosts and the auth endpoint. Use an organization runner on the required network if the hosts are private. Verify one complete def auth-and-probe run from that runner before enabling the chat and load jobs.

Phase 3 — Future Ragas evaluation

Add an evaluation/ directory with a curated dataset and a Ragas runner. Reuse Python settings, client, and auth. Submit curated questions through the chat API and retain the final response and the ordered evidence used to generate it. Retrieve evidence through a test-accessible response field or correlate it through a request ID exposed by the API.

|Metric            |What it checks                                                                                                   |
|------------------|-----------------------------------------------------------------------------------------------------------------|
|Faithfulness      |Whether the evidence supports the claims made in the response.                                                   |
|Response Relevancy|Whether the response addresses the user’s question.                                                              |
|Context Precision |Whether useful evidence ranks ahead of irrelevant evidence. Reference-based scoring also needs reference answers.|

Run evaluation independently from smoke, contract, and load tests. Use a fixed dataset and judge configuration to establish a baseline before setting quality thresholds.
