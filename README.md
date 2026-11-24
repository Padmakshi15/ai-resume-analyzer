# AI Resume Analyzer and Job Match Assistant

**Author:** Padmakshi Bhonagiri — Graduate Software Developer | Generative AI | Python | Java

**Stack:** Python, Streamlit, LLM API, MySQL, JSON

Upload a resume (PDF or DOCX), paste a job description, and get a
structured profile, a skill match with gaps, areas to strengthen, and
role-specific interview questions — then save each analysis so you can
compare an earlier resume version with a revised one.

> **Honest note:** without an `OPENAI_API_KEY` the app runs in
> **offline demo mode** — skills are extracted by keyword matching,
> no LLM call is made, and the sidebar says so. Set a key to get
> real LLM extraction. See [Configuration](#configuration).

## What it does

1. **Reads a resume** in PDF (via `pypdf`) or DOCX (via `python-docx`),
   or plain pasted text.
2. **Extracts a structured profile** — name, title, skills, tools,
   education, experience — as JSON, using an LLM with a structured
   prompt (or keyword extraction in offline demo mode).
3. **Validates the model output** and automatically retries when the
   JSON is incomplete or malformed, so a broken reply never crashes
   the app or silently produces a wrong profile.
4. **Compares the profile against a pasted job description** and lists
   matched skills, missing skills, and a match percentage.
5. **Generates role-specific interview questions** from the gaps —
   one per missing skill, plus one question about a strength.
6. **Stores each analysis** in MySQL when configured, otherwise in
   a local SQLite file, so earlier and revised versions can be compared.

## Architecture

```
User uploads resume (PDF / DOCX / TXT)
        |
        v
resume_parser.py  -- extract plain text
        |
        v
llm_client.py     -- structured prompt -> LLM (live) or
        |              keyword extraction (offline demo)
        v
analyzer.py       -- validate JSON + retry on malformed output
        |              match skills vs job description
        |              gap analysis + interview questions
        v
storage.py        -- save analysis
        |              MySQL (when MYSQL_* set) or SQLite (default)
        v
app.py (Streamlit) -- results, match score, questions, history
```

## Project structure

```
ai-resume-analyzer/
├── app.py                 # Streamlit UI
├── resume_parser.py       # PDF / DOCX / TXT text extraction
├── llm_client.py          # LLM call + offline demo (keyword) mode
├── analyzer.py            # JSON validation, retry, matching, questions
├── storage.py             # MySQL store + SQLite fallback store
├── requirements.txt
├── samples/
│   ├── sample_resume.txt        # sample resume (plain text)
│   ├── sample_resume.md         # same resume in Markdown
│   ├── sample_resume.docx       # same resume as a Word file
│   ├── sample_resume.pdf        # same resume as a PDF
│   └── sample_job_description.txt  # Python / Generative AI developer role
├── tests/
│   └── test_analyzer.py   # pytest suite (15 tests)
├── data/                  # created at runtime; SQLite file lives here
│   └── analyses.db        # (git-ignored)
├── LEARN.md               # beginner-friendly guide to the code
└── LICENSE                # MIT
```

## How to run locally

```bash
# 1. Clone and enter the project
git clone https://github.com/PadhuPadmakshi/ai-resume-analyzer.git
cd ai-resume-analyzer

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
streamlit run app.py
```

Then open the address Streamlit prints (usually
`http://localhost:8501`) in a browser.

## Configuration

### LLM key (optional — the app runs without it)

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o-mini"   # optional, this is the default
```

With the key set, the app uses live LLM extraction and the sidebar
shows "Live LLM mode". Without it, the app uses offline demo mode
(keyword extraction) and the sidebar says so. No key is ever stored
in the code or in the repository.

### MySQL storage (optional — SQLite is the default)

Without any MySQL settings, analyses are stored in the local file
`data/analyses.db` (SQLite, created automatically). To use MySQL
instead, set these environment variables before running the app:

```bash
export MYSQL_HOST="localhost"
export MYSQL_PORT="3306"            # optional, default 3306
export MYSQL_USER="root"
export MYSQL_PASSWORD="your-password"
export MYSQL_DATABASE="resume_analyzer"   # optional, default resume_analyzer
```

The `analyses` table is created automatically on first use. The
sidebar shows which backend is active.

## How to use it — step by step

1. Start the app with `streamlit run app.py` and open it in a browser.
2. Upload your resume (PDF, DOCX, or TXT) — or paste the resume text.
   Try the samples first: `samples/sample_resume.pdf` and
   `samples/sample_job_description.txt`.
3. Paste the job description for the role you want.
4. Click **Analyze resume vs job**.
5. Read the results:
   - **Match score** — the share of skills named in the job
     description that your resume shows.
   - **Matched skills** vs **Missing skills**.
   - **Structured profile (JSON)** — expand to see exactly what
     was extracted.
   - **Areas to strengthen** — one action per missing skill.
   - **Interview questions** — generated from your gaps.
6. The analysis is saved automatically. Scroll to **Past analyses**
   to see earlier runs, and use **Compare** to see what changed
   between an earlier and a revised resume (newly matched skills,
   skills no longer missing, match change).

## Screenshots

Screenshots are not included yet — after running the app, add them
here (`docs/screenshot-upload.png`, `docs/screenshot-results.png`).

What you will see:

- **Upload screen:** a file uploader on the left, a job-description
  box on the right, and a sidebar stating the mode (live LLM or
  offline demo) and the storage backend.
- **Results screen:** a match-score metric at the top, matched skills
  in one column and missing skills in the other, an expandable JSON
  view of the extracted profile, a list of areas to strengthen, and
  interview questions grouped by skill.
- **History section:** a list of past analyses with match scores,
  and a compare view showing newly matched skills and the match
  change between two runs.

## Tests

```bash
python -m pytest
```

Result (verified 2026-11-22):

```
15 passed
```

The suite in `tests/test_analyzer.py` covers JSON validation
(valid, missing field, wrong type, markdown fences, malformed JSON),
retry after malformed replies and giving up after the maximum
attempts, skill matching (including case-insensitive and alias
matching), gap detection, interview-question generation (including
the generic fallback), the Java/JavaScript distinction, and a full
end-to-end `analyze()` run.

## Limitations

- Offline demo mode extracts skills only from a fixed known-skills
  list, so a skill not in that list is missed; live LLM mode does
  not have this limit.
- PDF extraction depends on the PDF having a real text layer —
  scanned image-only PDFs return no text.
- Skill matching is keyword-based: it compares skill names, not
  depth of experience or years.
- Interview questions are template-based in this version; the LLM
  is used for extraction, not for writing the questions.
- MySQL is only used when `MYSQL_HOST` is set; otherwise the
  SQLite file is local to the machine running the app.

## Future improvements

- Let the LLM write the interview questions (with the same
  JSON validation and retry).
- Add a match explanation: which resume line supports each
  matched skill.
- Add a resume rewrite suggestion for each missing skill.
- Support more resume formats and scanned PDFs (OCR).
- Add a side-by-side diff view for compared analyses in the UI.
- Add GitHub Actions CI to run the pytest suite on every push.

## License

MIT — see [LICENSE](LICENSE).
