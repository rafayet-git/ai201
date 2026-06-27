"""Milestone 5 — Streamlit interface.

Run:  streamlit run app.py
"""

import streamlit as st
from query import ask

st.set_page_config(page_title="Unofficial Budget Phone Guide", page_icon="📱")

st.title("📱 The Unofficial Budget Phone Guide")
st.caption(
    "Ask about budget smartphones (under ~$300). Answers come only from the "
    "collected reviews and user opinions — not the model's general knowledge."
)

with st.form("query_form"):
    question = st.text_input(
        "Your question",
        placeholder="e.g. Does the Pixel 9a have overheating issues?",
    )
    submitted = st.form_submit_button("Ask")

if submitted and question.strip():
    with st.spinner("Searching the reviews…"):
        result = ask(question)

    st.subheader("Answer")
    st.write(result["answer"])

    st.subheader("Retrieved from")
    if result["sources"]:
        for s in result["sources"]:
            st.markdown(f"- [{s['source']}]({s['url']})")
    else:
        st.markdown("_No sources — the guide doesn't cover this question._")

    with st.expander("Show retrieved chunks (debug)"):
        for i, c in enumerate(result["chunks"], 1):
            st.markdown(f"**[{i}] {c['source']}** · distance `{c['distance']:.3f}`")
            st.text(c["text"])
