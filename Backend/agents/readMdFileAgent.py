"""
ReadMdFileAgent
===============

Routing agent for Project_Data_Analytics. Given a user query, it uses a
knowledge-base catalogue to decide:

  * whether the query is understood (otherwise it returns a clarification question),
  * the query type: insight, debug, or combined,
  * which knowledge-base .md files the downstream agent(s) need,
  * whether each part of the query is solvable from those files.

It does NOT answer the query. It returns a validated dict (or JSON string)
that is passed to the insight and/or debug agent.

Usage
-----
    from ReadMdFileAgent import ReadMdFileAgent

    agent = ReadMdFileAgent()
    result = agent.route("How many active employees are in each department?")

Setup
-----
    pip install anthropic python-dotenv        (pydantic is installed with anthropic)

    .env file (project root):
        ANTHROPIC_KEY=sk-ant-...
        # optional:
        # PROJECT_ROOT=/path/to/Project_Data_Analytics

Requires Python 3.9+.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Literal, Optional

import anthropic
from pydantic import BaseModel, Field, StrictInt, ValidationError, field_validator, model_validator

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional; real environment variables still work
    load_dotenv = None


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

DEFAULT_MODEL = "claude-haiku-5-5"
API_KEY_ENV = "ANTHROPIC_KEY"
PROJECT_ROOT_ENV = "PROJECT_ROOT"

# All paths are relative to the project root (Project_Data_Analytics), forward slashes.
CATALOG_PATH = "Backend/assets/Catalog.md"
KB_DIR = "Backend/assets/KnowledgeBase"

MAX_FILE_CHARS = 200_000  # safety cap on what a single read_file call returns


# --------------------------------------------------------------------------- #
# Prompt (embedded). The catalogue is appended to it at call time.
# --------------------------------------------------------------------------- #

ROUTER_PROMPT = r"""# Role

You are a **routing agent** for an employee-data analytics system. You do not answer queries, write SQL, or run anything against the database. Your only job is to decide:

1. whether you understand the query (if not, ask the user what they mean),
2. what type of query it is (insight, debug, or combined),
3. which knowledge-base `.md` files a downstream agent needs to solve it,
4. whether the query is solvable from those files.

You then return a single JSON object that is passed to the downstream agent(s).

# Tools

The catalogue is provided at the end of this prompt. You also have a `read_file` tool for reading the knowledge-base `.md` files listed in the catalogue.

All paths are **relative to the project root** (`Project_Data_Analytics`), and use forward slashes.

# Query types

- **Insight**: the user wants information derived from the data (counts, breakdowns, trends, comparisons, listings).
- **Debug**: the user wants help checking whether a value or record in a table is correct or wrong, by looking at the values and understanding the schema and the logic that produced them.
- **Combined**: the query contains both an insight request and a debug request.

# Workflow

Follow these steps in order.

1. **Understand the query.** Identify what is asked, which tables, columns, people and metrics are mentioned, and whether it is insight, debug, or both. If you cannot tell what the user is asking, go to "When you do not understand the query" below and stop.
2. **Use the catalogue first.** The catalogue is provided below. Use its file entries (summary, can answer, cannot answer, keywords, example queries, related files), its data objects list and its not-covered list to find candidate files. Do not open files the catalogue shows to be irrelevant.
3. **Select candidate files.** Include a file if it has real relevance to the query. Include a file as **supporting** if the primary file alone is not enough (for example, a debug question that also needs the allowed values or business meaning of a column). Do not include a file only because it shares a topic.
4. **Read the candidate files** with the `read_file` tool and confirm they actually contain the information needed. Remove any file that turns out not to help. You must read a file before you list it in `relevant_files`.
5. **Check solvability**, separately for each part of the query:
   - *Insight*: the metrics, columns, filters and definitions the query needs exist in the files, and the meaning is unambiguous. The query must not depend on data the files say does not exist.
   - *Debug*: the files document the table and columns involved, the rules or transformations that produce the value, and enough logic to judge whether the value is correct.
   - If a required table, column, rule or definition is missing, or a file states it does not exist, the part is **not solvable**.
6. **Build the JSON** following the output rules below.

# When you do not understand the query

Ask the user instead of guessing. Do this when:

- the request is too vague to identify what is wanted (for example "check the data", "how many people?" with no sense of which people or what measure),
- a key detail is missing that changes the answer (for example which person, which column, which time period, which of two plausible meanings),
- the request is not an insight or debug request about the employee data at all.

In these cases do not select files and do not judge solvability. Return the clarification JSON (see output rules) with one clear question that tells the user exactly what you need.

For a combined query where one part is clear and the other is not, ask for clarification on the unclear part only, and return no routing until it is answered.

**Do not confuse this with "not solvable".** If you understood the question but the files cannot answer it (for example it asks for salary, which does not exist), that is `solvable: false` with reasoning, not a clarification request.

# Handling combined queries

- Split the query into its insight part and its debug part.
- Return `source_start` and `source_end` for **both** parts. They locate the part inside the original user query. Indices are **zero-based** (the first character is index 0) and `source_end` is **exclusive**, so the part is `original_query[source_start:source_end]`. Count every character, including spaces and punctuation.
- `query` must **exactly match** that slice of the original user query. Copy the user's wording. Do not rewrite, summarise, reorder or improve it. Words that only connect the two parts (for example "and") sit outside the spans.
- Use `resolved_query` **only** when a part cannot stand alone because of a pronoun or reference (for example "it", "them", "that person") that points to the other part or to something earlier in the query. Put the clarified wording in `resolved_query`, changing as little as possible. Otherwise set `resolved_query` to `null`. Do not rewrite the query in any other way.
- The two spans must not overlap.
- Evaluate each part independently. If one part is solvable and the other is not, return the files and query for the solvable part, and the reasoning for the unsolvable part. Do not fail the whole request.

# Output rules

Return **only** a JSON object. No text before or after it, and no markdown code fence.

```
{
  "query_type": "insight" | "debug" | "combined" | "clarification_needed",
  "clarification_question": null | "<question for the user>",
  "insight": null | {
    "query": "<query text>",
    "source_start": null | <integer>,
    "source_end": null | <integer>,
    "resolved_query": null | "<clarified query text>",
    "solvable": true | false,
    "relevant_files": ["<relative file path>", ...],
    "reasoning": null | "<reason>"
  },
  "debug": null | {
    "query": "<query text>",
    "source_start": null | <integer>,
    "source_end": null | <integer>,
    "resolved_query": null | "<clarified query text>",
    "solvable": true | false,
    "relevant_files": ["<relative file path>", ...],
    "reasoning": null | "<reason>"
  }
}
```

- `query_type = "insight"`: `insight` filled, `debug` is `null`. `query` is the **original user query, verbatim**.
- `query_type = "debug"`: `debug` filled, `insight` is `null`. `query` is the **original user query, verbatim**.
- `query_type = "combined"`: both filled. Each part has its own `query`, plus `source_start` and `source_end` (both required), and `resolved_query` only when a reference had to be clarified (otherwise `null`).
- For `query_type` other than `"combined"`, `source_start`, `source_end` and `resolved_query` are always `null`.
- `query_type = "clarification_needed"`: `clarification_question` filled, `insight` and `debug` are both `null`. For every other type, `clarification_question` is `null`.
- `relevant_files`: the **relative file path** of each selected file, copied exactly from the `Path` field in the catalogue (relative to the project root, forward slashes, for example `Backend/assets/KnowledgeBase/EmployeeDimInsights.md`). Never output an absolute path such as one starting with `C:\`. List primary and supporting files together. Use an empty list `[]` when the part is not solvable.
- **The downstream agents can read only the files you list.** They cannot see the rest of the knowledge base. List every file needed to solve the part, and no file that is not needed.
- `solvable = true`: `reasoning` is `null`.
- `solvable = false`: `reasoning` must be specific and name what is missing or why the files rule it out (for example: the query asks for total salary, and `EmployeeDimInsights.md` §2 states the dimension has no salary column). Never give vague reasons such as "not enough information".
- `clarification_question` must be a direct, specific question to the user, written in plain language. Offer the likely options when you can (for example "Do you mean active employees only, or contractors as well?").

# Constraints

- Do not answer the query, write SQL, or guess values.
- Do not guess what the user meant when the query is unclear. Ask.
- Do not invent file names or paths. Only return files listed in the catalogue, with the exact path given there.
- Base every decision on the catalogue and the files, not on assumptions about the data.

# Examples

**Insight, solvable**

User: "How many active employees are in each department?"

{"query_type":"insight","clarification_question":null,"insight":{"query":"How many active employees are in each department?","source_start":null,"source_end":null,"resolved_query":null,"solvable":true,"relevant_files":["Backend/assets/KnowledgeBase/EmployeeDimInsights.md"],"reasoning":null},"debug":null}

**Insight, not solvable**

User: "What is the total salary paid to engineering employees?"

{"query_type":"insight","clarification_question":null,"insight":{"query":"What is the total salary paid to engineering employees?","source_start":null,"source_end":null,"resolved_query":null,"solvable":false,"relevant_files":[],"reasoning":"The query needs salary data. EmployeeDimInsights.md section 2 states dim_employee has no salary, compensation or payroll-amount column, and no other file covers one."},"debug":null}

**Debug, solvable**

User: "Why does Kiran Das show as EMPLOYEE when Beeline lists him as a contractor?"

{"query_type":"debug","clarification_question":null,"insight":null,"debug":{"query":"Why does Kiran Das show as EMPLOYEE when Beeline lists him as a contractor?","source_start":null,"source_end":null,"resolved_query":null,"solvable":true,"relevant_files":["Backend/assets/KnowledgeBase/EmployeeFlowAndFullBusinessLogic.md","Backend/assets/KnowledgeBase/EmployeeDimInsights.md"],"reasoning":null}}

**Combined, one part not solvable** (the original query is 99 characters long; "and " sits between the spans)

User: "Give me the average salary of contractors and tell me why Rahul Varma still shows an enabled badge."

{"query_type":"combined","clarification_question":null,"insight":{"query":"Give me the average salary of contractors","source_start":0,"source_end":41,"resolved_query":null,"solvable":false,"relevant_files":[],"reasoning":"The dimension holds no salary column (EmployeeDimInsights.md section 2). bill_rate is a vendor charge rate in mixed currencies and units, not pay to the person."},"debug":{"query":"tell me why Rahul Varma still shows an enabled badge.","source_start":46,"source_end":99,"resolved_query":null,"solvable":true,"relevant_files":["Backend/assets/KnowledgeBase/EmployeeFlowAndFullBusinessLogic.md","Backend/assets/KnowledgeBase/EmployeeDimInsights.md"],"reasoning":null}}

**Combined, with a reference that needs resolving** (the original query is 89 characters long; ", and " sits between the spans)

User: "How many leavers still have an enabled badge, and why does Rahul Varma appear among them?"

{"query_type":"combined","clarification_question":null,"insight":{"query":"How many leavers still have an enabled badge","source_start":0,"source_end":44,"resolved_query":null,"solvable":true,"relevant_files":["Backend/assets/KnowledgeBase/EmployeeDimInsights.md"],"reasoning":null},"debug":{"query":"why does Rahul Varma appear among them?","source_start":50,"source_end":89,"resolved_query":"why does Rahul Varma appear among the leavers who still have an enabled badge?","solvable":true,"relevant_files":["Backend/assets/KnowledgeBase/EmployeeFlowAndFullBusinessLogic.md","Backend/assets/KnowledgeBase/EmployeeDimInsights.md"],"reasoning":null}}

**Clarification needed**

User: "Check the data and tell me if it looks right."

{"query_type":"clarification_needed","clarification_question":"Which value or table would you like me to check, and for which person or column? For example, a specific field in dim_employee for one employee, or a count you think is wrong.","insight":null,"debug":null}
"""


READ_FILE_TOOL = {
    "name": "read_file",
    "description": (
        "Read a knowledge-base .md file listed in the catalogue. "
        "Pass the path exactly as given in the catalogue: relative to the project root, "
        "forward slashes (for example Backend/assets/KnowledgeBase/EmployeeDimInsights.md). "
        "Only files inside the knowledge-base folder can be read."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path of the .md file, taken from the catalogue.",
            }
        },
        "required": ["path"],
    },
}


# --------------------------------------------------------------------------- #
# Output schema (validated after the model replies)
# --------------------------------------------------------------------------- #

class PartResult(BaseModel):
    query: str
    source_start: Optional[StrictInt] = None   # combined queries only; zero-based
    source_end: Optional[StrictInt] = None     # combined queries only; exclusive
    resolved_query: Optional[str] = None       # combined queries only; clarified wording
    solvable: bool
    relevant_files: list[str] = Field(default_factory=list)
    reasoning: Optional[str] = None

    @field_validator("reasoning")
    @classmethod
    def _empty_reasoning_is_none(cls, v: Optional[str]) -> Optional[str]:
        return v if v and v.strip() else None

    @model_validator(mode="after")
    def _check_consistency(self) -> "PartResult":
        if not self.query.strip():
            raise ValueError("query must not be empty")
        if self.resolved_query is not None and not self.resolved_query.strip():
            raise ValueError("resolved_query must be non-empty when supplied (use null if nothing was resolved)")
        if (self.source_start is None) != (self.source_end is None):
            raise ValueError("source_start and source_end must be given together")
        if self.source_start is not None and not (0 <= self.source_start < self.source_end):
            raise ValueError("source_start must be >= 0 and less than source_end")
        if self.solvable:
            if not self.relevant_files:
                raise ValueError("a solvable part must list at least one relevant file")
            if self.reasoning is not None:
                raise ValueError("reasoning must be null when solvable is true")
        else:
            if self.relevant_files:
                raise ValueError("relevant_files must be empty when solvable is false")
            if self.reasoning is None:
                raise ValueError("reasoning is required when solvable is false")
        return self


class RouterOutput(BaseModel):
    query_type: Literal["insight", "debug", "combined", "clarification_needed"]
    clarification_question: Optional[str] = None
    insight: Optional[PartResult] = None
    debug: Optional[PartResult] = None

    @model_validator(mode="after")
    def _check_shape(self) -> "RouterOutput":
        qt = self.query_type
        if qt == "insight" and (self.insight is None or self.debug is not None):
            raise ValueError("query_type 'insight' needs 'insight' filled and 'debug' null")
        if qt == "debug" and (self.debug is None or self.insight is not None):
            raise ValueError("query_type 'debug' needs 'debug' filled and 'insight' null")
        if qt == "combined" and (self.insight is None or self.debug is None):
            raise ValueError("query_type 'combined' needs both 'insight' and 'debug' filled")
        if qt == "combined":
            for name, part in (("insight", self.insight), ("debug", self.debug)):
                if part.source_start is None:
                    raise ValueError(f"'{name}' needs source_start and source_end for a combined query")
        elif qt in ("insight", "debug"):
            part = self.insight or self.debug
            if part.source_start is not None or part.source_end is not None or part.resolved_query is not None:
                raise ValueError(
                    "source_start, source_end and resolved_query must be null unless query_type is 'combined'"
                )
        if qt == "clarification_needed":
            if not (self.clarification_question and self.clarification_question.strip()):
                raise ValueError("clarification_question is required for 'clarification_needed'")
            if self.insight is not None or self.debug is not None:
                raise ValueError("'insight' and 'debug' must be null for 'clarification_needed'")
        elif self.clarification_question is not None:
            raise ValueError("clarification_question must be null unless query_type is 'clarification_needed'")
        return self


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #

class RouterError(Exception):
    """Raised when routing fails (setup problem, API failure, or invalid output after retries)."""


class _OutputError(Exception):
    """Internal: the model's reply failed validation; the message is fed back to the model."""


# --------------------------------------------------------------------------- #
# Agent
# --------------------------------------------------------------------------- #

class ReadMdFileAgent:
    """Routes a query to insight / debug agents using the knowledge-base catalogue."""

    def __init__(
        self,
        project_root: Optional[str | Path] = None,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        max_turns: int = 10,
        max_retries: int = 2,
        max_tokens: int = 2048,
        temperature: Optional[float] = None,
        client: Optional[Any] = None,
    ) -> None:
        """
        project_root : folder that contains Backend/assets/Catalog.md. If omitted, the
                       PROJECT_ROOT env variable is used, else the folder is found by
                       walking up from this file.
        api_key      : overrides the ANTHROPIC_KEY environment variable.
        max_turns    : cap on model calls per route() (tool-use turns and retries included).
        max_retries  : how many times an invalid reply is sent back to the model for repair.
        temperature  : only sent to the API if you set it.
        client       : optional pre-built anthropic.Anthropic client (mainly for tests).
        """
        self.project_root = self._resolve_project_root(project_root)

        if load_dotenv:
            backend_env = self.project_root / "Backend" / ".env"
            if backend_env.is_file():
                load_dotenv(backend_env)  # does not override existing variables

        self.model = model
        self.max_turns = max_turns
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self.temperature = temperature

        if client is not None:
            self.client = client
        else:
            key = api_key or os.environ.get(API_KEY_ENV)
            if not key:
                raise RouterError(
                    f"No API key found. Set {API_KEY_ENV} in your .env file or environment."
                )
            self.client = anthropic.Anthropic(api_key=key)

        self._kb_dir = (self.project_root / KB_DIR).resolve()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def route(self, query: str) -> dict:
        """Route a query. Returns the validated routing result as a dict."""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")

        catalogue_text, allowed_paths = self._load_catalogue()
        system_prompt = self._build_system_prompt(catalogue_text)

        messages: list[dict] = [{"role": "user", "content": query}]
        files_read: set[str] = set()
        retries = 0

        for _ in range(self.max_turns):
            kwargs: dict[str, Any] = dict(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                tools=[READ_FILE_TOOL],
                messages=messages,
            )
            if self.temperature is not None:
                kwargs["temperature"] = self.temperature

            try:
                response = self.client.messages.create(**kwargs)
            except anthropic.APIError as exc:
                raise RouterError(f"Anthropic API call failed: {exc}") from exc

            messages.append({"role": "assistant", "content": response.content})

            # The model wants to read files: run the tool(s) and continue.
            if response.stop_reason == "tool_use":
                results = [
                    self._run_tool(block, files_read, allowed_paths)
                    for block in response.content
                    if getattr(block, "type", None) == "tool_use"
                ]
                messages.append({"role": "user", "content": results})
                continue

            # Final answer: parse and validate.
            text = "".join(
                block.text for block in response.content if getattr(block, "type", None) == "text"
            )
            try:
                return self._parse_and_validate(text, query, allowed_paths, files_read)
            except _OutputError as exc:
                if retries >= self.max_retries:
                    raise RouterError(
                        f"Model output was invalid after {self.max_retries} retries: {exc}"
                    ) from exc
                retries += 1
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your reply was rejected: {exc}\n"
                            "Fix this and return only the corrected JSON object, with no other text."
                        ),
                    }
                )

        raise RouterError(f"Routing did not finish within max_turns={self.max_turns}.")

    def route_json(self, query: str, indent: Optional[int] = None) -> str:
        """Same as route(), returned as a JSON string."""
        return json.dumps(self.route(query), indent=indent, ensure_ascii=False)

    # ------------------------------------------------------------------ #
    # Setup helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _resolve_project_root(project_root: Optional[str | Path]) -> Path:
        candidate = project_root or os.environ.get(PROJECT_ROOT_ENV)
        if candidate:
            root = Path(candidate).expanduser().resolve()
            if not (root / CATALOG_PATH).is_file():
                raise RouterError(f"Catalogue not found at {root / CATALOG_PATH}")
            return root

        for parent in Path(__file__).resolve().parents:
            if (parent / CATALOG_PATH).is_file():
                return parent

        raise RouterError(
            f"Could not locate {CATALOG_PATH} by walking up from {Path(__file__).resolve()}. "
            f"Pass project_root=... or set {PROJECT_ROOT_ENV}."
        )

    def _load_catalogue(self) -> tuple[str, set[str]]:
        """Read the catalogue (fresh each call, so edits are picked up) and list its file paths."""
        text = (self.project_root / CATALOG_PATH).read_text(encoding="utf-8")
        paths = set(re.findall(r"\|\s*\*\*Path\*\*\s*\|\s*`([^`]+)`", text))
        allowed = {p for p in paths if p.startswith(KB_DIR + "/")}
        if not allowed:
            raise RouterError("No knowledge-base file paths found in the catalogue.")
        return text, allowed

    @staticmethod
    def _build_system_prompt(catalogue_text: str) -> str:
        return f"{ROUTER_PROMPT}\n\n# Catalogue\n\n<catalogue>\n{catalogue_text}\n</catalogue>\n"

    # ------------------------------------------------------------------ #
    # read_file tool
    # ------------------------------------------------------------------ #

    def _safe_resolve(self, raw_path: str) -> Path:
        rel = (raw_path or "").strip().replace("\\", "/")
        if not rel:
            raise ValueError("path is empty")
        if rel.startswith("/") or re.match(r"^[A-Za-z]:", rel):
            raise ValueError("absolute paths are not allowed; use the relative path from the catalogue")

        target = (self.project_root / rel).resolve()
        if not target.is_relative_to(self._kb_dir):
            raise ValueError(f"only files inside {KB_DIR}/ can be read")
        if target.suffix.lower() != ".md":
            raise ValueError("only .md files can be read")
        if not target.is_file():
            raise ValueError(f"file not found: {rel}")
        return target

    def _run_tool(self, block: Any, files_read: set[str], allowed_paths: set[str]) -> dict:
        try:
            if block.name != "read_file":
                raise ValueError(f"unknown tool '{block.name}'")
            tool_input = block.input if isinstance(block.input, dict) else {}
            target = self._safe_resolve(tool_input.get("path", ""))
            rel_path = target.relative_to(self.project_root).as_posix()
            if rel_path not in allowed_paths:
                raise ValueError(
                    "this file is not listed in the catalogue; only catalogue-listed files can be read"
                )
            content = target.read_text(encoding="utf-8")
            if len(content) > MAX_FILE_CHARS:
                content = content[:MAX_FILE_CHARS] + "\n\n[file truncated]"
            files_read.add(rel_path)
            return {"type": "tool_result", "tool_use_id": block.id, "content": content}
        except (ValueError, OSError) as exc:
            return {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": f"Error: {exc}",
                "is_error": True,
            }

    # ------------------------------------------------------------------ #
    # Output parsing and validation
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_json(text: str) -> Any:
        text = text.strip()
        fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
        if fence:
            text = fence.group(1)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
        raise _OutputError("the reply is not a valid JSON object")

    @staticmethod
    def _norm(s: str) -> str:
        return " ".join(s.split())

    def _check_spans(self, out: RouterOutput, original: str) -> None:
        """Validate source_start/source_end of both parts of a combined query against the original text."""
        n = len(original)
        spans = []
        for name, part in (("insight", out.insight), ("debug", out.debug)):
            start, end = part.source_start, part.source_end
            if end > n:
                raise _OutputError(
                    f"{name} span [{start}, {end}) goes past the end of the original query, which has "
                    f"{n} characters (indices are zero-based and source_end is exclusive, so the largest "
                    f"valid source_end is {n})"
                )
            if self._norm(original[start:end]) != self._norm(part.query):
                wanted = part.query.strip()
                found = original.find(wanted)
                if wanted and found != -1:
                    hint = (
                        f"The text of {name}.query does appear in the original query, at "
                        f"source_start={found}, source_end={found + len(wanted)}. Use those indices"
                    )
                else:
                    hint = (
                        f"{name}.query is not copied verbatim from the original query. The original text at "
                        f"[{start}, {end}) is {original[start:end]!r}. Copy the wording exactly"
                    )
                raise _OutputError(f"{name}.query does not match original_query[{start}:{end}]. {hint}")
            spans.append((start, end, name))

        spans.sort()
        if spans[0][1] > spans[1][0]:
            raise _OutputError(
                f"the spans of '{spans[0][2]}' and '{spans[1][2]}' overlap; each part must cover different text"
            )

    def _parse_and_validate(
        self, text: str, original_query: str, allowed_paths: set[str], files_read: set[str]
    ) -> dict:
        data = self._extract_json(text)

        try:
            out = RouterOutput.model_validate(data)
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(p) for p in err['loc']) or 'root'}: {err['msg']}" for err in exc.errors()
            )
            raise _OutputError(f"JSON does not match the required schema ({details})") from exc

        # Insight-only and debug-only queries must carry the original query verbatim.
        if out.query_type in ("insight", "debug"):
            part = out.insight or out.debug
            if self._norm(part.query) != self._norm(original_query):
                raise _OutputError(
                    "for a single-type query, 'query' must be the original user query verbatim"
                )

        # Combined queries: each part must come from a real, non-overlapping span of the original query.
        if out.query_type == "combined":
            self._check_spans(out, original_query)

        # Every listed file must be in the catalogue, and must have been read by the model.
        for name, part in (("insight", out.insight), ("debug", out.debug)):
            if part is None:
                continue
            for path in part.relevant_files:
                if path not in allowed_paths:
                    raise _OutputError(
                        f"{name}.relevant_files contains '{path}', which is not a path listed in the "
                        "catalogue. Use the exact relative path from the catalogue (forward slashes)"
                    )
                if path not in files_read:
                    raise _OutputError(
                        f"{name}.relevant_files lists '{path}', but you have not read it. "
                        "Read it with read_file first, or remove it"
                    )

        return out.model_dump()


# --------------------------------------------------------------------------- #
# Command line: python ReadMdFileAgent.py "your query"
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print('Usage: python ReadMdFileAgent.py "your query"')
        sys.exit(1)

    print(ReadMdFileAgent().route_json(" ".join(sys.argv[1:]), indent=2))