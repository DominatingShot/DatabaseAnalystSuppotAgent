"""Live API checks for the five routing scenarios in ReadMdFileAgent."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv

AGENTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = AGENTS_DIR.parents[1]
BACKEND_ENV = PROJECT_ROOT / "Backend" / ".env"
sys.path.insert(0, str(AGENTS_DIR))

from readMdFileAgent import ReadMdFileAgent


load_dotenv(BACKEND_ENV)

FLOW_FILE = "Backend/assets/KnowledgeBase/EmployeeFlowAndFullBusinessLogic.md"
INSIGHTS_FILE = "Backend/assets/KnowledgeBase/EmployeeDimInsights.md"

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_KEY"),
    reason="ANTHROPIC_KEY is not available in Backend/.env or the environment",
)


SCENARIOS = [
    (
        "How many active employees are in each department?",
        "insight",
        True,
    ),
    (
        "What is the total salary paid to engineering employees?",
        "insight",
        False,
    ),
    (
        "Why does Kiran Das show as EMPLOYEE when Beeline lists him as a contractor?",
        "debug",
        True,
    ),
    (
        "Give me the average salary of contractors and tell me why Rahul Varma still shows an enabled badge.",
        "combined",
        None,
    ),
    (
        "Check the data and tell me if it looks right.",
        "clarification_needed",
        None,
    ),
]


def _assert_part(part: dict[str, Any], original_query: str) -> None:
    assert isinstance(part.get("query"), str) and part["query"].strip()
    assert isinstance(part.get("solvable"), bool)
    assert isinstance(part.get("relevant_files"), list)

    if part["solvable"]:
        assert part["relevant_files"]
        assert part["reasoning"] is None
    else:
        assert part["relevant_files"] == []
        assert isinstance(part["reasoning"], str) and part["reasoning"].strip()

    start = part.get("source_start")
    end = part.get("source_end")
    if start is None or end is None:
        assert start is None and end is None
        assert part.get("resolved_query") is None
    else:
        assert isinstance(start, int) and isinstance(end, int)
        assert 0 <= start < end <= len(original_query)
        assert " ".join(original_query[start:end].split()) == " ".join(part["query"].split())


def test_live_routing_scenarios() -> None:
    """Run all five documented scenarios against the Anthropic API."""
    agent = ReadMdFileAgent(
        project_root=PROJECT_ROOT,
        max_turns=10,
        max_retries=2,
    )

    for query, expected_type, expected_solvable in SCENARIOS:
        result = agent.route(query)

        assert result["query_type"] == expected_type, query
        assert result["clarification_question"] is None if expected_type != "clarification_needed" else (
            isinstance(result["clarification_question"], str)
            and bool(result["clarification_question"].strip())
        )

        if expected_type == "clarification_needed":
            assert result["insight"] is None
            assert result["debug"] is None
            continue

        if expected_type == "insight":
            assert result["debug"] is None
            part = result["insight"]
            assert part is not None
            assert part["solvable"] is expected_solvable
            _assert_part(part, query)
            if expected_solvable:
                assert INSIGHTS_FILE in part["relevant_files"]
            continue

        if expected_type == "debug":
            assert result["insight"] is None
            part = result["debug"]
            assert part is not None
            assert part["solvable"] is True
            _assert_part(part, query)
            assert FLOW_FILE in part["relevant_files"]
            continue

        insight = result["insight"]
        debug = result["debug"]
        assert insight is not None and debug is not None
        assert insight["solvable"] is False
        assert debug["solvable"] is True
        _assert_part(insight, query)
        _assert_part(debug, query)
        assert insight["source_end"] <= debug["source_start"] or debug["source_end"] <= insight["source_start"]
        assert FLOW_FILE in debug["relevant_files"]
