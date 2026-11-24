"""AI Resume Analyzer and Job Match Assistant -- Streamlit app.

Run with:  streamlit run app.py

Flow:
  1. Upload a resume (PDF / DOCX / TXT) or paste resume text.
  2. Paste a job description.
  3. Click "Analyze" -- the resume is parsed, sent to the LLM
     (or the offline demo extractor when no API key is set),
     matched against the job description, and stored.
  4. Review matched / missing skills, areas to strengthen, and
     role-specific interview questions. Compare with past analyses.
"""

from __future__ import annotations

import streamlit as st

from analyzer import analyze
from llm_client import LLMClient
from resume_parser import SUPPORTED_EXTENSIONS, extract_text_from_bytes
from storage import compare_analyses, get_store

st.set_page_config(
    page_title="AI Resume Analyzer",
    page_icon="📄",
    layout="wide",
)

st.title("📄 AI Resume Analyzer and Job Match Assistant")
st.write(
    "Upload a resume and paste a job description. The app extracts a "
    "structured profile, compares it with the role, lists the skills "
    "you are missing, and generates interview questions from those gaps."
)

# --- Sidebar: mode + configuration -------------------------------------
client = LLMClient()
with st.sidebar:
    st.header("Settings")
    if client.is_live:
        st.success(f"✅ Live LLM mode (model: {client.model})")
    else:
        st.warning(
            "⚠️ Offline demo mode — no `OPENAI_API_KEY` set.\n\n"
            "Skills are extracted by keyword matching, so the app "
            "still runs end to end. Set `OPENAI_API_KEY` and restart "
            "for real LLM extraction."
        )
    st.caption(
        "Storage: MySQL when `MYSQL_HOST` is set, otherwise a local "
        "SQLite file in `data/analyses.db`."
    )
    try:
        store = get_store()
        backend = "MySQL" if type(store).__name__ == "MySQLStore" else "SQLite (local file)"
        st.caption(f"Storage backend: {backend}")
    except Exception as exc:  # noqa: BLE001 - show the error, keep app usable
        store = None
        st.error(f"Storage unavailable: {exc}")

# --- Inputs -------------------------------------------------------------
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("1. Your resume")
    uploaded = st.file_uploader(
        "Upload a resume (PDF, DOCX, or TXT)",
        type=[ext.lstrip(".") for ext in sorted(SUPPORTED_EXTENSIONS)],
    )
    pasted_resume = st.text_area(
        "Or paste resume text here",
        height=220,
        placeholder="Paste the full resume text...",
    )

with col_right:
    st.subheader("2. Job description")
    job_description = st.text_area(
        "Paste the job description",
        height=300,
        placeholder="Paste the full job description for the role you want...",
    )

analyze_clicked = st.button("🔍 Analyze resume vs job", type="primary")

if analyze_clicked:
    if uploaded is not None:
        resume_text = extract_text_from_bytes(uploaded.read(), uploaded.name)
    elif pasted_resume.strip():
        resume_text = pasted_resume
    else:
        st.error("Please upload a resume or paste resume text first.")
        st.stop()
    if not job_description.strip():
        st.error("Please paste a job description first.")
        st.stop()

    with st.spinner("Extracting profile and matching skills..."):
        try:
            profile = client.extract_profile(resume_text)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not extract a profile: {exc}")
            st.stop()
        result = analyze(profile, job_description)

    st.session_state["last_result"] = result

    # --- Results --------------------------------------------------------
    st.subheader("3. Results")
    st.metric(
        "Match score",
        f"{result['match_percentage']}%",
        help="Share of skills named in the job description that your resume shows.",
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("### ✅ Matched skills")
        if result["matched_skills"]:
            st.write(", ".join(result["matched_skills"]))
        else:
            st.write("No required skills matched yet.")
    with col_b:
        st.markdown("### ❌ Missing skills")
        if result["missing_skills"]:
            st.write(", ".join(result["missing_skills"]))
        else:
            st.write("Nothing missing — every skill in the job description is covered.")

    with st.expander("Structured profile (JSON)"):
        st.json(result["profile"])

    st.markdown("### 🎯 Areas to strengthen")
    for area in result["areas_to_strengthen"]:
        st.write(f"- {area}")
    if not result["areas_to_strengthen"]:
        st.write("No gaps found for this job description.")

    st.markdown("### 💬 Interview questions (from your gaps)")
    for item in result["interview_questions"]:
        st.write(f"- **{item['skill']}:** {item['question']}")

    if store is not None:
        try:
            analysis_id = store.save_analysis(result)
            st.success(f"Saved as analysis #{analysis_id}. Compare it with earlier runs below.")
        except Exception as exc:  # noqa: BLE001
            st.warning(f"Result shown, but saving failed: {exc}")

# --- History / comparison ----------------------------------------------
st.subheader("📚 Past analyses — compare earlier and revised versions")
if store is not None:
    try:
        history = store.list_analyses(limit=10)
    except Exception as exc:  # noqa: BLE001
        history = []
        st.warning(f"Could not load history: {exc}")
    if history:
        for item in history:
            st.write(
                f"#{item['id']} — {item.get('profile_name') or 'Unnamed'} — "
                f"{item['created_at']} — {item['match_percentage']}% matched — "
                f"missing: {', '.join(item['missing_skills']) or 'none'}"
            )
        if len(history) >= 2:
            ids = [item["id"] for item in history]
            col_old, col_new = st.columns(2)
            with col_old:
                older_id = st.selectbox("Earlier analysis", ids[::-1], key="older")
            with col_new:
                newer_id = st.selectbox("Revised analysis", ids, key="newer")
            if st.button("Compare"):
                older = store.get_analysis(int(older_id))
                newer = store.get_analysis(int(newer_id))
                if older and newer:
                    diff = compare_analyses(older, newer)
                    st.write(f"Match change: {diff['match_percentage_change']:+}%")
                    st.write(f"Newly matched: {', '.join(diff['newly_matched']) or 'none'}")
                    st.write(f"No longer missing: {', '.join(diff['no_longer_missing']) or 'none'}")
                    st.write(f"Still missing: {', '.join(diff['still_missing']) or 'none'}")
    else:
        st.caption("No analyses saved yet. Run an analysis above to start the history.")
else:
    st.caption("Storage is unavailable, so history is not shown.")
