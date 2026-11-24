"""Analysis core: JSON validation + retry, skill matching, gap analysis,
and interview-question generation.

This module has no Streamlit, network, or database dependencies, so it
is the part covered by the pytest suite in ``tests/``.
"""

from __future__ import annotations

import json
import re

# Canonical skill names, mapped from the lowercase forms / aliases
# that appear in real resumes and job descriptions.
SKILL_ALIASES: dict[str, str] = {
    "python": "Python",
    "java": "Java",
    "c#": "C#",
    "c sharp": "C#",
    ".net": ".NET",
    "asp.net": "ASP.NET",
    "asp.net core": "ASP.NET Core",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "sql": "SQL",
    "mysql": "MySQL",
    "postgresql": "PostgreSQL",
    "mongodb": "MongoDB",
    "html": "HTML",
    "css": "CSS",
    "react": "React",
    "angular": "Angular",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "flask": "Flask",
    "django": "Django",
    "fastapi": "FastAPI",
    "streamlit": "Streamlit",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "scikit-learn": "Scikit-learn",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "langchain": "LangChain",
    "openai": "OpenAI",
    "generative ai": "Generative AI",
    "genai": "Generative AI",
    "llm": "LLM",
    "llms": "LLM",
    "machine learning": "Machine Learning",
    "ml": "Machine Learning",
    "deep learning": "Deep Learning",
    "nlp": "NLP",
    "natural language processing": "NLP",
    "prompt engineering": "Prompt Engineering",
    "rag": "RAG",
    "git": "Git",
    "github": "GitHub",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "jenkins": "Jenkins",
    "aws": "AWS",
    "azure": "Azure",
    "gcp": "GCP",
    "linux": "Linux",
    "windows": "Windows",
    "rest api": "REST API",
    "rest apis": "REST API",
    "graphql": "GraphQL",
    "power bi": "Power BI",
    "tableau": "Tableau",
    "jira": "Jira",
    "postman": "Postman",
    "agile": "Agile",
    "scrum": "Scrum",
    "wpf": "WPF",
    "c++": "C++",
    "c": "C",
}

KNOWN_SKILLS: list[str] = sorted(set(SKILL_ALIASES.values()))

PROFILE_FIELDS = {"name", "title", "skills", "tools", "education", "experience"}
REQUIRED_LIST_FIELDS = ("skills", "tools", "education", "experience")

# Interview-question templates, keyed by the missing skill they probe.
# A generic fallback is used for skills with no specific template.
QUESTION_TEMPLATES: dict[str, list[str]] = {
    "Python": [
        "Explain the difference between a list and a tuple in Python, and when you would choose each.",
        "How do you handle errors and logging in a Python service you have built?",
    ],
    "Generative AI": [
        "Walk through a Generative AI feature you built end to end - what did the prompt, the model, and your validation code each do?",
        "How do you stop an LLM feature from inventing facts in its answers?",
    ],
    "Machine Learning": [
        "How would you decide whether a problem needs machine learning at all, versus a rules-based approach?",
        "Explain how you would split data and measure whether a model is actually improving.",
    ],
    "SQL": [
        "Write a query that finds the second-highest salary in an employees table, and explain how it works.",
        "How do you find and fix a slow SQL query?",
    ],
    "Docker": [
        "What goes into a Dockerfile for a Python web app, and why do you use multi-stage builds?",
        "How do you pass secrets such as API keys to a container without baking them into the image?",
    ],
    "React": [
        "Explain how state flows in a React app and when you would lift state up versus keep it local.",
        "What is the virtual DOM, and when does it actually help performance?",
    ],
    "AWS": [
        "Which AWS services would you use to deploy a Python API, and how would you keep it reliable?",
        "How do you keep cloud costs under control for a small service?",
    ],
    "Azure": [
        "Which Azure services would you use to deploy a Python API, and how would you keep it reliable?",
        "How do you secure secrets for an app running on Azure?",
    ],
    "LangChain": [
        "What problem does LangChain solve that plain API calls do not, and where does it get in the way?",
        "How would you build a retrieval-augmented generation (RAG) pipeline with LangChain?",
    ],
    "RAG": [
        "Explain a retrieval-augmented generation pipeline: how are documents chunked, stored, and retrieved?",
        "How do you measure whether retrieved context actually improved an answer?",
    ],
}


def _strip_fences(text: str) -> str:
    """Remove ```json / ``` fences around a JSON reply."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def validate_profile(data: object) -> dict:
    """Validate a parsed profile dict and normalise it to the schema.

    Raises:
        ValueError: If the data is not a dict, a required list field
            is missing or not a list, or a list item is not a string
            (experience items must be dicts).
    Returns:
        A normalised dict with exactly the schema fields, in order.
    """
    if not isinstance(data, dict):
        raise ValueError(f"Profile must be a JSON object, got {type(data).__name__}")
    unknown = sorted(set(data) - PROFILE_FIELDS)
    if unknown:
        raise ValueError(f"Unknown profile field(s): {', '.join(unknown)}")
    for field in REQUIRED_LIST_FIELDS:
        if field not in data:
            raise ValueError(f"Missing required field: '{field}'")
        if not isinstance(data[field], list):
            raise ValueError(f"Field '{field}' must be a list")
    for item in data["skills"] + data["tools"] + data["education"]:
        if not isinstance(item, str):
            raise ValueError("skills, tools and education must be lists of strings")
    for item in data["experience"]:
        if not isinstance(item, dict):
            raise ValueError("experience must be a list of objects")
    return {
        "name": str(data.get("name", "") or ""),
        "title": str(data.get("title", "") or ""),
        "skills": [str(s) for s in data["skills"]],
        "tools": [str(t) for t in data["tools"]],
        "education": [str(e) for e in data["education"]],
        "experience": [dict(e) for e in data["experience"]],
    }


def parse_llm_json(raw: str) -> dict:
    """Parse and validate one raw LLM reply. Raises ValueError if invalid."""
    if not raw or not raw.strip():
        raise ValueError("LLM reply was empty")
    try:
        data = json.loads(_strip_fences(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM reply was not valid JSON: {exc}") from exc
    return validate_profile(data)


def parse_llm_json_with_retry(raw_or_callable, max_attempts: int = 3) -> dict:
    """Parse LLM JSON, retrying when it is incomplete or malformed.

    Args:
        raw_or_callable: Either a raw JSON string, or a zero-argument
            callable returning a raw string. When a callable is given
            it is called again on each retry, so a caller can re-ask
            the model (or return the next canned reply in tests).
        max_attempts: How many attempts before giving up.

    Raises:
        ValueError: If every attempt failed; the last error is included.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    last_error: Exception | None = None
    for _attempt in range(max_attempts):
        raw = raw_or_callable() if callable(raw_or_callable) else raw_or_callable
        try:
            return parse_llm_json(raw)
        except ValueError as exc:
            last_error = exc
            continue
    raise ValueError(
        f"Could not get valid profile JSON after {max_attempts} attempt(s): "
        f"{last_error}"
    )


def extract_skills_from_text(text: str) -> list[str]:
    """Find known skills in free text, returned in canonical form.

    Matching is case-insensitive and uses word boundaries where the
    skill name allows it, so "Java" does not match "JavaScript".
    """
    if not text:
        return []
    lowered = text.lower()
    found: list[str] = []
    for alias, canonical in SKILL_ALIASES.items():
        pattern = r"(?<![A-Za-z0-9+#.])" + re.escape(alias) + r"(?![A-Za-z0-9+#])"
        # Short aliases such as "C" or "ML" need strict boundaries;
        # the lookarounds above already handle that.
        if re.search(pattern, lowered) and canonical not in found:
            found.append(canonical)
    return sorted(found)


def match_skills(profile_skills: list[str], job_description: str) -> dict:
    """Compare profile skills with the skills a job description asks for.

    Returns a dict with ``required`` (skills found in the JD),
    ``matched``, ``missing``, and ``match_percentage`` (0-100).
    Matching is case-insensitive and alias-aware.
    """
    required = extract_skills_from_text(job_description or "")
    profile_norm = {s.strip().lower() for s in profile_skills if s.strip()}
    # Also expand profile skills through the alias table so "GenAI"
    # in a profile matches "Generative AI" in a JD.
    expanded = set(profile_norm)
    for alias, canonical in SKILL_ALIASES.items():
        if alias in profile_norm:
            expanded.add(canonical.lower())
    matched = [s for s in required if s.lower() in expanded]
    missing = [s for s in required if s.lower() not in expanded]
    pct = round(100 * len(matched) / len(required), 1) if required else 0.0
    return {
        "required": required,
        "matched": matched,
        "missing": missing,
        "match_percentage": pct,
    }


def gap_analysis(match_result: dict) -> list[str]:
    """Turn missing skills into plain-language areas to strengthen."""
    return [
        f"Strengthen {skill}: add a small project or course that uses it, "
        f"then add the result to the resume."
        for skill in match_result.get("missing", [])
    ]


def generate_interview_questions(missing_skills: list[str],
                                 matched_skills: list[str] | None = None,
                                 per_skill: int = 1) -> list[dict]:
    """Generate role-specific interview questions from the skill gaps.

    Each question targets a missing skill; one question is also added
    for a matched skill so the candidate can show a strength.
    Returns a list of ``{"skill": ..., "question": ...}`` dicts.
    """
    questions: list[dict] = []
    for skill in missing_skills:
        templates = QUESTION_TEMPLATES.get(skill)
        if templates:
            for template in templates[:per_skill]:
                questions.append({"skill": skill, "question": template})
        else:
            questions.append({
                "skill": skill,
                "question": (
                    f"Tell me about a time you used {skill} in a real "
                    f"project - what did you build, and what did you learn?"
                ),
            })
    if matched_skills:
        skill = matched_skills[0]
        questions.append({
            "skill": skill,
            "question": (
                f"You list {skill} as a strength. Describe the most "
                f"challenging problem you solved with it."
            ),
        })
    return questions


def analyze(profile: dict, job_description: str) -> dict:
    """Run the full analysis: match, gaps, and interview questions.

    Args:
        profile: A validated profile dict (see ``validate_profile``).
        job_description: The pasted job description text.

    Returns:
        A dict with the profile, match result, areas to strengthen,
        and interview questions - the object stored by ``storage.py``.
    """
    profile = validate_profile(profile)
    all_skills = profile["skills"] + profile["tools"]
    match_result = match_skills(all_skills, job_description)
    questions = generate_interview_questions(
        match_result["missing"], match_result["matched"]
    )
    return {
        "profile": profile,
        "job_description": job_description or "",
        "matched_skills": match_result["matched"],
        "missing_skills": match_result["missing"],
        "required_skills": match_result["required"],
        "match_percentage": match_result["match_percentage"],
        "areas_to_strengthen": gap_analysis(match_result),
        "interview_questions": questions,
    }
