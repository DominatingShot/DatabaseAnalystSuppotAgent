"""Data insights agent.

Called only for insight-type questions. Gets the md file path (from the upstream agent) and the
user's query, asks the LLM which aggregation answers it, and computes that table in pandas.
Its output goes to the composer agent, which picks the chart and writes the answer.
"""

import json
import os
import re

import anthropic
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
MODEL = "claude-haiku-4-5"

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "..", "Database", "dim_employee.xlsx")
TARGET_SHEET = "v_dim_employee_current"

ALLOWED_AGGS = {"sum", "mean", "count", "max", "min"}

INSIGHT_PROMPT = """You are a data insights assistant. A user asked a question about a dataset.
Decide which single aggregation answers it.

Business context (knowledge base document):
<context>
{md_content}
</context>

Available columns (name: dtype). You may ONLY use these exact column names:
{columns}

User question:
{query}

Reply with ONLY a JSON object, no markdown fences and no extra text, of this shape:
{{"group_by": "column or null", "metric": "numeric column", "agg": "sum | mean | count | max | min"}}

Rules:
- group_by must be a column name from the list or null. metric must be a column name from the list.
- Use a numeric column as metric for sum, mean, max and min. Any column works for count.
- Follow the rules in the business context.
"""


def run_insight_agent(md_path, query):
    """Returns {"query", "operation", "table"}. On failure, {"error": readable message}."""
    with open(md_path, encoding="utf-8") as f:
        md_content = f.read()
    df = pd.read_excel(DATA_PATH, sheet_name=TARGET_SHEET)

    columns = "\n".join(f"- {col}: {dtype}" for col, dtype in df.dtypes.astype(str).items())
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    response = client.messages.create(
        model=MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": INSIGHT_PROMPT.format(
            md_content=md_content, columns=columns, query=query)}],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)  # Haiku sometimes adds fences anyway

    try:
        op = json.loads(text)
        group_by, metric, agg = op.get("group_by"), op["metric"], op["agg"]
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
        return {"error": f"LLM did not return the expected JSON. Raw reply:\n{text}"}

    if group_by in ("null", ""):
        group_by = None
    if group_by is not None and group_by not in df.columns:
        return {"error": f"group_by column '{group_by}' does not exist in the table."}
    if metric not in df.columns:
        return {"error": f"metric column '{metric}' does not exist in the table."}
    if agg not in ALLOWED_AGGS:
        return {"error": f"agg '{agg}' is not one of {sorted(ALLOWED_AGGS)}."}
    if agg != "count" and not pd.api.types.is_numeric_dtype(df[metric]):
        return {"error": f"metric '{metric}' is not numeric, so '{agg}' cannot be applied."}

    if group_by:
        table = df.groupby(group_by)[metric].agg(agg).reset_index()
    else:
        table = pd.DataFrame({"metric": [metric], agg: [df[metric].agg(agg)]})

    return {"query": query, "operation": {"group_by": group_by, "metric": metric, "agg": agg},
            "table": table}
