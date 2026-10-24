"""Composer agent.

Gets the outputs of the insight agent and the debug agent (parallel agent, not built yet),
picks the chart, and writes the answer the user sees: summary, insights and a detailed read.
Every number it shows must come from those outputs.
"""

import json
import os
import re

import anthropic
from dotenv import load_dotenv
from matplotlib.figure import Figure

load_dotenv()
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
MODEL = "claude-haiku-4-5"

COMPOSER_PROMPT = """You are writing the final answer for a business user who asked a question
about employee data. Other agents have already done the work; use only their outputs.

User question:
{query}

Insight agent output - computation: {agg} of "{metric}"{grouping}. Result table:
{table}

Debug agent output:
{debug}

Reply with ONLY a JSON object, no markdown fences and no extra text, of this shape:
{{
  "chart": "bar | line | pie | none",
  "title": "short sentence-case chart title",
  "summary": "2-3 sentences that directly answer the question, for a quick read",
  "insights": ["3-5 insights; each is 2-3 sentences: the observation, then why it matters"],
  "detailed": "a detailed read in 3-4 paragraphs separated by blank lines: what was measured,
               what the result shows, how the groups compare, and anything from the debug
               output the user should know"
}}

Rules:
- Chart: "line" for trends over time, "bar" for comparing categories, "pie" only for parts of a
  whole with at most 6 parts, "none" when the table has a single value.
- Only use numbers that appear exactly in the agent outputs above. Do not calculate new numbers
  (no percentages, differences, ratios or totals that are not there).
- Write plain business language, not code or SQL.
"""


def run_composer_agent(insight_output, debug_output=None):
    """Returns {"summary", "insights", "detailed", "table", "figure"}. On failure, {"error": ...}."""
    table, op = insight_output["table"], insight_output["operation"]
    debug = json.dumps(debug_output, default=str, indent=2) if debug_output else "None"

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": COMPOSER_PROMPT.format(
            query=insight_output["query"], agg=op["agg"], metric=op["metric"],
            grouping=f' per "{op["group_by"]}"' if op["group_by"] else "",
            table=table.to_string(index=False), debug=debug)}],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)  # Haiku sometimes adds fences anyway

    try:
        answer = json.loads(text)
        summary, insights, detailed = answer["summary"], answer["insights"], answer["detailed"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return {"error": f"LLM did not return the expected JSON. Raw reply:\n{text}"}

    # Any number the LLM wrote must be in the agent outputs
    allowed = numbers_in(table.to_string(index=False) + debug + insight_output["query"])
    if numbers_in(summary) - allowed:
        return {"error": "LLM summary stated numbers that are not in the agent outputs."}
    insights = [i for i in insights if not numbers_in(i) - allowed]
    detailed = "\n\n".join(p for p in detailed.split("\n\n") if not numbers_in(p) - allowed)

    return {"summary": summary, "insights": insights, "detailed": detailed, "table": table,
            "figure": make_chart(table, answer.get("chart"), answer.get("title", ""))}


def numbers_in(text):
    """Numbers in the text, plus their rounded forms, so 38.4615 also allows 38.5 and 38."""
    nums = {float(n) for n in re.findall(r"\d+(?:\.\d+)?", str(text).replace(",", ""))}
    return {r for n in nums for r in (n, round(n), round(n, 1), round(n, 2))}


def make_chart(table, chart, title):
    """Return a matplotlib Figure, or None when there is nothing to draw."""
    if chart not in ("bar", "line", "pie") or len(table.columns) < 2:
        return None
    x, y = table.columns[0], table.columns[1]
    if chart == "pie" and len(table) > 6:
        chart = "bar"  # pie only for at most 6 parts

    fig = Figure(figsize=(8, 5))
    ax = fig.subplots()
    if chart == "line":
        ax.plot(table[x].astype(str), table[y], marker="o")
    elif chart == "bar":
        ax.bar(table[x].astype(str), table[y])
    else:
        ax.pie(table[y], labels=table[x].astype(str), autopct="%1.1f%%")
    if chart != "pie":
        ax.set_xlabel(x)
        ax.set_ylabel(y)
        ax.tick_params(axis="x", labelrotation=45)
    ax.set_title(title)
    fig.tight_layout()
    return fig
