src/agents/dashboard_schema_agent.py

from __future__ import annotations

from agno.agent import Agent
from agno.utils.log import log_debug

from src.config import get_llm_model


def create_dashboard_summary_agent() -> Agent:
    """
    Business Dashboard Schema Agent.

    This agent's job is NOT to generate dashboards.
    It only analyzes table schema and classifies columns into:

    - business metric columns
    - business dimension columns
    - business time columns
    - technical columns

    The dashboard builder then uses this classification to
    generate metrics, charts and tables deterministically.

    This keeps dashboard generation stable while still allowing
    AI to understand business meaning of the schema.
    """

    agent = Agent(
        id="dashboard_summary_agent",
        name="Business Dashboard Summary Agent",
        model=get_llm_model(),
        instructions=[
            "You are a Business Data Schema Analyst.",
            "",
            "You will receive a table schema including column names and data types.",
            "Your job is to classify each column based on business usefulness.",
            "",
            "Classify columns into the following categories:",
            "",
            "1. business_metric_columns",
            "   Numeric columns representing measurable business values.",
            "   Examples: revenue, amount, price, cost, quantity, balance, score.",
            "",
            "2. business_dimension_columns",
            "   Categorical fields used to group or segment business data.",
            "   Examples: region, category, product, customer, status, segment.",
            "",
            "3. business_time_columns",
            "   Time related fields used for trend analysis.",
            "   Examples: order_date, transaction_date, created_date, timestamp.",
            "",
            "4. technical_columns",
            "   Fields that are technical or metadata and should NOT be used in business dashboards.",
            "   Examples:",
            "   id, uuid, hash, source_file, batch_id, created_at, updated_at, metadata, flags.",
            "",
            "You must also infer the BUSINESS CONTEXT of the table.",
            "Possible values:",
            "",
            "transaction  -> orders, payments, sales, invoices",
            "customer     -> users, accounts, clients",
            "inventory    -> products, stock, items",
            "support      -> tickets, issues",
            "generic      -> if none clearly applies",
            "",
            "Rules:",
            "",
            "- Do NOT generate SQL.",
            "- Do NOT generate charts.",
            "- Do NOT summarize data.",
            "- Only analyze column names and types.",
            "",
            "Return ONLY valid JSON in the following structure:",
            "",
            "{",
            '  "business_context": "transaction | customer | inventory | support | generic",',
            '  "business_metric_columns": ["col1", "col2"],',
            '  "business_dimension_columns": ["col1", "col2"],',
            '  "business_time_columns": ["col1"],',
            '  "technical_columns": ["col1", "col2"]',
            "}",
            "",
            "Do not include markdown fences.",
            "Do not include explanations.",
            "Return only JSON.",
        ],
    )

    log_debug("Business Dashboard Schema Agent initialized")

    return agent


------------------------------------------------------------------------------------

