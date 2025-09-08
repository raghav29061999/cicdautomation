def load_data(state: State) -> State:
    if DATA_PATH.exists():
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            state["input"] = json.load(f)
    else:
        state["input"] = FALLBACK_DATA
    return state

def build_prompt(state: State) -> State:
    d = state["input"]
    client = d["client"]["name"]
    constraints = ", ".join(d["profile"].get("constraints", []))
    prefs = json.dumps(d["profile"].get("preferences", {}), ensure_ascii=False)
    market_lines = "\n".join(f"- {n['title']}: {n['summary']}" for n in d.get("market_notes", []))
    disclosures = d.get("compliance", {}).get("disclosures_required", [])

    prompt = f"""
You are an RM co-pilot. Create a concise, client-ready investment pitch.

Client: {client} ({d['client']['segment']}, {d['client']['jurisdiction']})
RM intent: {d['rm_intent']}

Profile:
- Risk band: {d['profile']['risk_band']}
- Horizon (months): {d['profile']['horizon_months']}
- Liquidity: {d['profile']['liquidity_needs']}
- Constraints: {constraints}
- Preferences: {prefs}

Treasury snapshot:
- Cash reserves (INR mn): {d['treasury_snapshot']['cash_reserves_inr_mn']}
- Target yield: {d['treasury_snapshot']['target_yield']}

Market notes (for context):
{market_lines}

Task:
1) 3-point talk track tailored to the profile.
2) 2–3 product ideas with brief rationale.
3) Simple allocation suggestion (percentages add to 100%).
4) Flag 1–2 key risks.
5) Append these disclosures verbatim under 'Disclosures':
{chr(10).join(f"- {line}" for line in disclosures)}

Output JSON with keys:
- talk_track: string[]
- recommendations: array of {{product, rationale}}
- allocation: object of {{bucket: percent}}
- risks: string[]
- disclosures: string[]

Do not include code fences. Return ONLY raw JSON (no prose, no markdown).
""".strip()
    state["prompt"] = prompt
    return state

def call_llm(state: State) -> State:
    client = OpenAI()  # uses OPENAI_API_KEY from env
    resp = client.responses.create(model=MODEL, input=state["prompt"])

    # Prefer Responses API helper if available
    text_out = None
    try:
        text_out = resp.output_text  # SDK helper
    except Exception:
        # Fallback: try to assemble text from generic fields
        try:
            parts = []
            for out in getattr(resp, "output", []) or []:
                for c in getattr(out, "content", []) or []:
                    if hasattr(c, "text"):
                        parts.append(c.text)
            if parts:
                text_out = "\n".join(parts)
        except Exception:
            pass

    if not text_out:
        # Last resort: stringify entire response
        try:
            text_out = json.dumps(resp.model_dump(), ensure_ascii=False)
        except Exception:
            text_out = str(resp)

    state["raw_output"] = text_out
    return state

def structure_output(state: State) -> State:
    raw = state.get("raw_output", "")
    try:
        state["structured"] = extract_json(raw)
    except Exception as e:
        state["structured"] = {"error": f"Parsing failed: {e}", "raw": raw}
    return state

def print_result(state: State) -> State:
    print("\n=== Pitch (structured) ===")
    print(json.dumps(state.get("structured"), indent=2, ensure_ascii=False))
    d = state.get("structured", {})
    if isinstance(d, dict) and "disclosures" in d:
        print("\n--- Disclosures ---")
        for line in d["disclosures"]:
            print(f"- {line}")
    return state


----------------

def build_graph():
    g = StateGraph(dict)
    g.add_node("load_data", load_data)
    g.add_node("build_prompt", build_prompt)
    g.add_node("call_llm", call_llm)
    g.add_node("structure_output", structure_output)
    g.add_node("print_result", print_result)

    g.set_entry_point("load_data")
    g.add_edge("load_data", "build_prompt")
    g.add_edge("build_prompt", "call_llm")
    g.add_edge("call_llm", "structure_output")
    g.add_edge("structure_output", "print_result")
    g.add_edge("print_result", END)
    return g.compile()


-------------
if __name__ == "__main__":
    import json, pathlib, re
    from datetime import datetime

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Please set OPENAI_API_KEY in your environment or .env file.")

    # Toggle saving (can also set SAVE_TO_FILE=0/false in env)
    SAVE_TO_FILE = os.getenv("SAVE_TO_FILE", "1").lower() not in ("0", "false")
    OUT_DIR = pathlib.Path(os.getenv("OUT_DIR", "out"))

    app = build_graph()
    state = app.invoke({})  # final state returned by LangGraph

    if SAVE_TO_FILE:
        try:
            OUT_DIR.mkdir(parents=True, exist_ok=True)

            # Derive filename: client name + UTC timestamp
            client_name = (
                state.get("input", {})
                     .get("client", {})
                     .get("name", "client")
            )
            safe_client = re.sub(r"[^a-z0-9_]+", "_", client_name.lower().replace("&", "and").replace(" ", "_"))
            ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

            structured = state.get("structured")
            raw = state.get("raw_output", "")

            if isinstance(structured, (dict, list)):
                out_path = OUT_DIR / f"{safe_client}_{ts}_structured.json"
                out_path.write_text(json.dumps(structured, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"\n💾 Saved structured JSON → {out_path}")
            else:
                out_path = OUT_DIR / f"{safe_client}_{ts}_raw.txt"
                out_path.write_text(str(raw), encoding="utf-8")
                print(f"\n💾 Saved raw text → {out_path}")

        except Exception as e:
            print(f"⚠️ Failed to save output: {e}")
