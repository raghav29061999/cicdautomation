flowchart LR
    A[User Request] --> B[LLM - OpenAI / Anthropic]
    B --> C{{Agent Type\nZero-shot / Structured-Chat}}
    C --> D[Tools\nadd, subtract, multiply, divide...]
    D --> E[Final Answer]

    style A fill:#dae8fc,stroke:#6c8ebf
    style B fill:#ffffff,stroke:#000000
    style C fill:#fff2cc,stroke:#d6b656
    style D fill:#d5e8d4,stroke:#82b366
    style E fill:#f8cecc,stroke:#b85450




flowchart LR
    A[User Request] --> B[LLM - OpenAI / Anthropic / Bedrock]
    B --> C{{Universal Agent Loop}}
    C --> D[Tools\nadd, subtract, multiply, integrate...]
    D --> E[Final Answer]

    style A fill:#dae8fc,stroke:#6c8ebf
    style B fill:#ffffff,stroke:#000000
    style C fill:#fff2cc,stroke:#d6b656
    style D fill:#d5e8d4,stroke:#82b366
    style E fill:#f8cecc,stroke:#b85450
