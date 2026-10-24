"""Streamlit UI for the Database Analyst.

Run from the project folder:  streamlit run FrontEnd/app.py
"""

import os
import sys

import streamlit as st

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.append(os.path.join(ROOT, "Backend", "agents"))

from composer_agent import run_composer_agent  # noqa: E402
from insight_agent import run_insight_agent  # noqa: E402

# TODO: replace with the md path from the upstream routing agent once it exists
MD_PATH = os.path.join(ROOT, "Backend", "assets", "KnowledgeBase", "EmployeeDimInsights.md")

def show_result(result):
    if "error" in result:
        st.error(result["error"])
        return
    st.markdown("**Summary**")
    st.write(result["summary"])
    if result["figure"] is not None:
        st.pyplot(result["figure"])
    st.markdown("**Insights**\n" + "\n".join(f"- {insight}" for insight in result["insights"]))
    with st.expander("Detailed read"):
        st.write(result["detailed"])
        st.dataframe(result["table"], hide_index=True)


st.title("Database Analyst")

# Streamlit reruns the script on every input, so past questions and answers live in session_state
if "history" not in st.session_state:
    st.session_state.history = []

for query, result in st.session_state.history:
    with st.chat_message("user"):
        st.write(query)
    with st.chat_message("assistant"):
        show_result(result)

query = st.chat_input("Ask a question about the data")
if query:
    with st.chat_message("user"):
        st.write(query)
    with st.chat_message("assistant"):
        with st.spinner("Analysing..."):
            result = run_insight_agent(MD_PATH, query)
            if "error" not in result:
                # TODO: pass the debug agent's output here once it exists
                result = run_composer_agent(result, debug_output=None)
        show_result(result)
    st.session_state.history.append((query, result))
