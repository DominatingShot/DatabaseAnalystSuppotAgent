from pathlib import Path
import anthropic

from SupportAgent.config import ROUTER_MODEL, ROUTER_MAX_TURNS
from SupportAgent.Retrieval.catalogue import load_catalogue, list_md_files, read_md_file
from SupportAgent.Router.schemas import RouteDecision

client = anthropic.Anthropic()
PROMPT = (Path(__file__).with_name("find_md_prompt.md")).read_text(encoding="utf-8")

TOOLS = [
    {
        "name": "read_md_file",
        "description": "Read one knowledge base file by its exact filename from the catalogue.",
        "input_schema": {
            "type": "object",
            "properties": {"filename": {"type": "string"}},
            "required": ["filename"],
        },
    },
    {
        "name": "submit_decision",
        "description": "Submit the final routing decision. Call exactly once, when done.",
        "input_schema": RouteDecision.model_json_schema(),
    },
]

def find_md(user_query: str) -> tuple[RouteDecision, dict[str, str]]:
    system = PROMPT.replace("{{CATALOGUE}}", load_catalogue())
    messages = [{"role": "user", "content": user_query}]

    for _ in range(ROUTER_MAX_TURNS):
        resp = client.messages.create(
            model=ROUTER_MODEL,
            max_tokens=8000,                    # thinking is on by default and shares this budget
            system=system,
            tools=TOOLS,
            tool_choice={"type": "auto"},       # "any" is rejected on sonnet-5-5 and later
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            try:
                if b.name == "read_md_file":
                    out = read_md_file(b.input.get("filename", ""))   # missing key -> ValueError -> model retries
                else:  # submit_decision
                    d = RouteDecision(**b.input)
                    bad = [f for f in d.md_files if f not in list_md_files()]
                    if bad:
                        raise ValueError(f"Files not in knowledge base: {bad}")
                    contexts = {f: read_md_file(f) for f in d.md_files}
                    return d, contexts           # done
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
            except ValueError as e:              # includes pydantic ValidationError
                results.append({"type": "tool_result", "tool_use_id": b.id,
                                "content": str(e), "is_error": True})
        if not results:                         # "auto" lets it answer in prose; push it back on task
            results = [{"type": "text", "text": "Call read_md_file or submit_decision."}]
        messages.append({"role": "user", "content": results})

    raise RuntimeError("Find MD agent did not reach a decision")
