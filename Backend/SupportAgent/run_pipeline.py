import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # Backend/ on path, so "python run_pipeline.py" works

from SupportAgent.Router.find_md_agent import find_md

queries = [
    "How many employees joined last quarter by department?",
    "Tell me how the is_active field is sourced for employeeDim"
           # out_of_scope
]

if __name__ == "__main__":                       # import-time must stay free: every call costs money
    for q in queries:
        d, ctx = find_md(q)
        print(q, "->", d.status, d.agent, list(ctx))
        print("   ", d.enhanced_query or d.message, "\n")
