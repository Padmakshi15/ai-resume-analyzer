# Learn: AI Resume Analyzer and Job Match Assistant

**Author:** Padmakshi Bhonagiri — Graduate Software Developer | Generative AI | Python | Java

This guide explains the project the way you would explain it in an
interview: what each file does, how data flows through the app, the
key ideas behind it, and three small exercises to try yourself.

## The big picture

A resume is messy text. A job description is messy text. This app
turns both into **structured data** (JSON), compares them, and turns
the comparison into useful output: a match score, missing skills,
and interview questions.

```
resume file ──> text ──> LLM prompt ──> JSON profile
                                            │
job description ──> skills in the JD ────────┤
                                            ▼
                              matched vs missing skills
                                            │
                                            ▼
                     areas to strengthen + interview questions
                                            │
                                            ▼
                              saved in MySQL / SQLite
```

## Each file, explained

### `app.py` — the Streamlit user interface

This is the only file Streamlit runs (`streamlit run app.py`).
It does no real analysis itself; it collects input, calls the other
modules, and shows results.

- `st.file_uploader` takes the resume file; `st.text_area` takes
  pasted text and the job description.
- It creates one `LLMClient`, calls `extract_profile()`, then
  `analyze()`, then `store.save_analysis()`.
- `st.session_state["last_result"]` keeps the last result in memory
  for the session; the history section reads past runs from storage.
- The sidebar is honest about the mode: live LLM when a key is set,
  offline demo otherwise.

**Why this separation matters:** if the UI and the logic were mixed,
you could not test the logic without launching a browser. Here you
can — see `tests/test_analyzer.py`.

### `resume_parser.py` — resume file → plain text

- `extract_text(path)` picks a parser from the file extension
  (`.pdf`, `.docx`, `.txt`, `.md`) and raises a clear error for
  anything else.
- `extract_text_from_bytes(data, filename)` does the same for an
  uploaded file, which Streamlit gives you as bytes, not a path.
- `extract_pdf` uses `pypdf` (`PdfReader`, one page at a time).
- `extract_docx` uses `python-docx` (paragraphs, plus table cells,
  because some resumes put skills in a table).

**Key idea:** every later step works on plain text. Parsing is a
separate, testable step, and adding a new format means adding one
function here, not changing the whole app.

### `llm_client.py` — resume text → structured profile (JSON)

This is the LLM part, and it has two modes:

- **Live mode** (when `OPENAI_API_KEY` is set): it sends the resume
  to the model with a system prompt that describes the exact JSON
  schema and says "return ONLY valid JSON". Temperature is 0, so
  the output is deterministic.
- **Offline demo mode** (no key): no network call. It extracts
  skills by keyword matching against `KNOWN_SKILLS` in
  `analyzer.py`, guesses the name from the first line, and collects
  education lines by degree keywords. It returns a profile in the
  *same shape* as live mode, so the rest of the app cannot tell
  the difference — and the UI labels the mode honestly.

**Key idea — prompt engineering:** the model is not asked an open
question ("tell me about this resume"). It is given a schema and a
format rule. That is what makes the output usable as data instead
of prose.

### `analyzer.py` — the brain: validation, matching, questions

No Streamlit, no network, no database — pure functions, which is
why this is the file the tests cover.

- **`validate_profile(data)`** checks a parsed profile: it must be
  a dict, it must have the required list fields (`skills`, `tools`,
  `education`, `experience`), lists must really be lists, and
  experience items must be dicts. It returns a normalised dict
  with exactly the schema fields. Anything else raises `ValueError`
  with a message saying what is wrong.
- **`parse_llm_json(raw)`** strips ```json fences if the model
  added them anyway, parses the JSON, then validates it.
- **`parse_llm_json_with_retry(...)`** calls the parser up to
  `max_attempts` times. Give it a string, or a callable that
  returns a new reply each time (in live mode that callable
  re-asks the model). It only succeeds on a fully valid profile;
  after the last attempt it raises, including the last error.
- **`extract_skills_from_text(text)`** finds known skills with
  case-insensitive matching and word boundaries — that boundary
  rule is why "JavaScript" does not also match "Java".
  `SKILL_ALIASES` maps lowercase forms ("genai", "c sharp") to
  canonical names ("Generative AI", "C#").
- **`match_skills(profile_skills, job_description)`** extracts the
  skills the JD asks for, then splits them into `matched` and
  `missing`, and computes `match_percentage`.
- **`gap_analysis(match_result)`** turns each missing skill into a
  plain-language action: strengthen it, build a small project,
  add the result to the resume.
- **`generate_interview_questions(missing, matched)`** picks a
  template per missing skill from `QUESTION_TEMPLATES`, falls back
  to a generic "tell me about a time you used X" question for
  skills with no template, and adds one strength question for a
  matched skill.
- **`analyze(profile, job_description)`** runs the whole pipeline
  and returns one dict — the object that gets stored.

### `storage.py` — saving analyses so versions can be compared

- **`get_store()`** is the decision point: if `MYSQL_HOST` is set
  it returns a `MySQLStore`, otherwise a `SQLiteStore` that writes
  to `data/analyses.db`. Both classes have the same methods.
- **`save_analysis(result)`** stores the match percentage, the
  matched/missing skill lists, and the full result as JSON, and
  returns the new row id.
- **`list_analyses(limit)`** and **`get_analysis(id)`** power the
  history section in the app.
- **`compare_analyses(older, newer)`** is pure logic (no database):
  newly matched skills, skills no longer missing, skills still
  missing, and the change in match percentage.

**Key idea:** the app never writes SQL in `app.py`. The storage
choice lives in one place, so switching backends is one
environment variable, not a rewrite.

### `tests/test_analyzer.py` — proving the brain works

15 pytest tests, all in plain functions with `assert`. They cover
valid and invalid profiles, markdown fences, malformed JSON, retry
success after two bad replies, retry giving up, matching, alias
matching, gap detection, question generation, the Java/JavaScript
distinction, and a full end-to-end `analyze()` run.

Run them with `python -m pytest` (15 passed).

### `samples/` — data to try the app with

- `sample_resume.txt` / `.md` / `.docx` / `.pdf` — the same sample
  resume in four formats, so you can test each parser.
- `sample_job_description.txt` — a Python / Generative AI
  developer role. Against the sample resume it matches most
  required skills and leaves a small number missing, which is
  exactly the interesting case: matched skills, a few gaps, and
  questions about those gaps.

## Key concepts, in one paragraph each

- **Structured JSON output:** asking an LLM for JSON with a fixed
  schema turns free-form model output into data your code can use.
  The schema is the contract between the prompt and the program.
- **Prompt engineering:** the system prompt does three jobs — it
  states the role ("you are a resume parser"), the exact output
  format, and what not to do ("do not invent skills"). Small
  wording changes here change the output more than model choice does.
- **Validation + retry:** LLMs sometimes return almost-JSON.
  Instead of trusting the reply, the code parses it, validates the
  shape, and retries (re-asking with a note that the last reply
  was invalid) before giving up with a clear error. Never let a
  malformed reply silently become a wrong answer.
- **MySQL storage:** each analysis is a row with a timestamp, a
  match percentage, and the full result as JSON. That is what makes
  "compare my earlier resume with my revised resume" possible —
  the comparison is just two rows, read back and differenced.

## Exercises — try these yourself

### Exercise 1 — Add a new skill

1. Open `analyzer.py` and add an entry to `SKILL_ALIASES`, for
   example `"tailwind": "Tailwind CSS"`.
2. Add `"Tailwind CSS"` to the sample resume and to the sample job
   description (or just to the JD, to see it appear as missing).
3. Run `python -m pytest` — the suite should still pass — then
   run the app and check the new skill is matched or listed
   as missing.

*What you learn:* the alias table is the single source of truth
for keyword extraction, and both the JD side and the resume side
read from it.

### Exercise 2 — Change the prompt

1. Open `llm_client.py` and change `SYSTEM_PROMPT` so the profile
   also extracts a `"summary"` field (one sentence).
2. Add `"summary"` to `PROFILE_FIELDS` in `analyzer.py` — and
   think about whether it should be a required string field or
   optional. Update `validate_profile` to handle it.
3. Add a test in `tests/test_analyzer.py` for a profile with a
   summary, run `python -m pytest`, and fix the test until it
   passes.

*What you learn:* a schema change touches three places — prompt,
validator, and tests — and the tests are what catch a place you
forgot.

### Exercise 3 — Add a new interview-question type

1. Pick a skill with no template yet, for example "Flask", and
   add two questions for it to `QUESTION_TEMPLATES` in
   `analyzer.py`.
2. Change `generate_interview_questions` so that, for missing
   skills, it also adds a follow-up question: "What would you
   do first in your first week to learn this skill on the job?"
3. Add a test that checks the follow-up appears, run the suite,
   and try it in the app with a JD that asks for Flask.

*What you learn:* question generation is data (the templates)
plus a small function — new behaviour is usually a new template
or one new rule, not a rewrite.
