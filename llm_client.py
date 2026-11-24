"""LLM client for resume extraction.

Two modes, chosen automatically:

1. Live mode -- when the ``OPENAI_API_KEY`` environment variable is set,
   the resume text is sent to an OpenAI-compatible chat model with a
   structured prompt that asks for JSON only.
2. Offline demo mode -- when no key is set, no network call is made.
   Skills, tools, education and experience are extracted by keyword
   matching against a known-skills list (see ``analyzer.py``).
   The app labels this mode honestly in the UI so nobody mistakes a
   keyword extraction for an LLM result.

To use live mode, set::

    export OPENAI_API_KEY="sk-..."
    export OPENAI_MODEL="gpt-4o-mini"   # optional, this is the default

The ``openai`` package is only imported when live mode is used, so the
app still runs without it in offline demo mode.
"""

from __future__ import annotations

import json
import os
import re

from analyzer import (
    KNOWN_SKILLS,
    extract_skills_from_text,
    validate_profile,
)

DEFAULT_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = (
    "You are a resume parser. Extract structured information from the "
    "resume text provided by the user. Return ONLY valid JSON, with no "
    "markdown fences, no commentary, and no extra text. "
    "Use exactly this schema:\n"
    '{\n'
    '  "name": "full name or empty string",\n'
    '  "title": "current or target role or empty string",\n'
    '  "skills": ["skill 1", "skill 2"],\n'
    '  "tools": ["tool 1", "tool 2"],\n'
    '  "education": ["degree, institution, year"],\n'
    '  "experience": [\n'
    '    {"role": "...", "employer": "...", "dates": "...", "summary": "..."}\n'
    "  ]\n"
    "}\n"
    "Skills are programming languages, frameworks, libraries and "
    "technical concepts. Tools are named products and platforms "
    "(for example Git, Docker, MySQL). Keep every list item short. "
    "If a field is not present in the resume, use an empty list or "
    "an empty string. Do not invent skills, employers or dates."
)


def build_prompt(resume_text: str) -> str:
    """Build the user prompt that wraps the raw resume text."""
    return (
        "Extract the structured profile from this resume:\n\n"
        f"{resume_text}\n\n"
        "Return ONLY the JSON object described in the system prompt."
    )


def _mock_extract(resume_text: str) -> dict:
    """Offline demo extraction: keyword matching, no LLM call.

    Returns a profile dict in exactly the same shape as the live
    mode, so the rest of the app (matching, questions, storage)
    works identically in both modes.
    """
    skills = extract_skills_from_text(resume_text)
    tools = [s for s in skills if s in {
        "Git", "GitHub", "Docker", "MySQL", "PostgreSQL", "MongoDB",
        "Jenkins", "Kubernetes", "AWS", "Azure",
        "Power BI", "Tableau", "Jira", "Postman", "Linux", "Windows",
    }]
    core_skills = [s for s in skills if s not in tools]

    # Name: first non-empty line, if it looks like a name (2-4 words,
    # no digits, no common resume headings).
    name = ""
    title = ""
    lines = [ln.strip() for ln in resume_text.splitlines() if ln.strip()]
    if lines and re.match(r"^[A-Za-z][A-Za-z .'-]{2,60}$", lines[0]) \
            and lines[0].lower() not in {"resume", "curriculum vitae", "cv"}:
        name = lines[0]
    for line in lines[:6]:
        if "|" in line and len(line) < 120:
            title = line
            break

    education: list[str] = []
    for line in lines:
        if re.search(r"\b(B\.?Tech|B\.?E\.?|B\.?Sc|M\.?Tech|M\.?Sc|MBA|Bachelor|Master)\b",
                     line, re.IGNORECASE):
            education.append(line)

    profile = {
        "name": name,
        "title": title,
        "skills": core_skills,
        "tools": tools,
        "education": education,
        "experience": [],
    }
    return validate_profile(profile)


class LLMClient:
    """Thin wrapper around the LLM (or the offline demo extractor)."""

    def __init__(self, api_key: str | None = None,
                 model: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
        self.mode = "live" if self.api_key else "offline-demo"

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    def extract_profile(self, resume_text: str) -> dict:
        """Extract a structured profile dict from resume text.

        Live mode: calls the LLM and validates the returned JSON,
        retrying once on malformed output. Offline mode: keyword
        extraction (see ``_mock_extract``).
        """
        if not resume_text or not resume_text.strip():
            raise ValueError("Resume text is empty - nothing to extract.")
        if not self.is_live:
            return _mock_extract(resume_text)
        return self._extract_live(resume_text)

    def _extract_live(self, resume_text: str) -> dict:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "The 'openai' package is required for live mode. "
                "Install it with: pip install openai"
            ) from exc
        client = OpenAI(api_key=self.api_key)
        last_error: Exception | None = None
        for attempt in range(2):
            prompt = build_prompt(resume_text)
            if attempt > 0:
                prompt += (
                    "\n\nYour previous reply was not valid JSON. "
                    "Reply with ONLY a valid JSON object, no fences."
                )
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )
            raw = response.choices[0].message.content or ""
            try:
                data = json.loads(_strip_fences(raw))
            except json.JSONDecodeError as exc:
                last_error = exc
                continue
            try:
                return validate_profile(data)
            except ValueError as exc:
                last_error = exc
                continue
        raise ValueError(
            f"LLM returned invalid profile JSON after 2 attempts: {last_error}"
        )


def _strip_fences(text: str) -> str:
    """Remove ```json / ``` fences if the model added them anyway."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()
