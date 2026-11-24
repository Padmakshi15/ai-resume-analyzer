"""Tests for analyzer.py — run with: python -m pytest"""

import json

import pytest

from analyzer import (
    analyze,
    extract_skills_from_text,
    gap_analysis,
    generate_interview_questions,
    match_skills,
    parse_llm_json,
    parse_llm_json_with_retry,
    validate_profile,
)

VALID_PROFILE = {
    "name": "Padmakshi Bhonagiri",
    "title": "Graduate Software Developer",
    "skills": ["Python", "SQL", "Generative AI"],
    "tools": ["Git", "MySQL"],
    "education": ["B.Tech, Information Technology (2016)"],
    "experience": [
        {"role": "Graduate Software Developer", "employer": "Personal Projects",
         "dates": "Jul 2025 - Oct 2025", "summary": "Built an AI resume analyzer."}
    ],
}

JD = "We need a Python developer with SQL, Docker, and Generative AI experience."


def test_validate_profile_accepts_valid_profile():
    result = validate_profile(VALID_PROFILE)
    assert result["name"] == "Padmakshi Bhonagiri"
    assert result["skills"] == ["Python", "SQL", "Generative AI"]
    assert result["tools"] == ["Git", "MySQL"]


def test_validate_profile_rejects_missing_field():
    bad = {k: v for k, v in VALID_PROFILE.items() if k != "skills"}
    with pytest.raises(ValueError, match="Missing required field: 'skills'"):
        validate_profile(bad)


def test_validate_profile_rejects_wrong_type():
    bad = dict(VALID_PROFILE, skills="Python, SQL")
    with pytest.raises(ValueError, match="must be a list"):
        validate_profile(bad)


def test_parse_llm_json_accepts_valid_json():
    raw = json.dumps(VALID_PROFILE)
    assert parse_llm_json(raw)["title"] == "Graduate Software Developer"


def test_parse_llm_json_accepts_markdown_fences():
    raw = "```json\n" + json.dumps(VALID_PROFILE) + "\n```"
    assert parse_llm_json(raw)["name"] == "Padmakshi Bhonagiri"


def test_parse_llm_json_rejects_malformed_json():
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_llm_json('{"skills": ["Python",] oops')


def test_retry_succeeds_after_malformed_replies():
    replies = iter([
        "not json at all",
        '{"skills": "not a list"}',
        json.dumps(VALID_PROFILE),
    ])
    result = parse_llm_json_with_retry(lambda: next(replies), max_attempts=3)
    assert result["skills"] == ["Python", "SQL", "Generative AI"]


def test_retry_gives_up_after_max_attempts():
    with pytest.raises(ValueError, match="after 3 attempt"):
        parse_llm_json_with_retry("garbage {", max_attempts=3)


def test_skill_matching_finds_matched_and_missing():
    result = match_skills(["Python", "SQL", "Generative AI"], JD)
    assert set(result["matched"]) == {"Python", "SQL", "Generative AI"}
    assert result["missing"] == ["Docker"]
    assert result["match_percentage"] == 75.0


def test_skill_matching_is_case_insensitive_and_alias_aware():
    result = match_skills(["python", "GenAI"], "Python and Generative AI needed.")
    assert result["match_percentage"] == 100.0
    assert result["missing"] == []


def test_gap_detection_lists_missing_skills():
    gaps = gap_analysis({"missing": ["Docker", "Kubernetes"]})
    assert len(gaps) == 2
    assert "Docker" in gaps[0]
    assert "Kubernetes" in gaps[1]
    assert gap_analysis({"missing": []}) == []


def test_interview_questions_target_the_gaps():
    questions = generate_interview_questions(["Docker"], ["Python"])
    skills = [q["skill"] for q in questions]
    assert "Docker" in skills
    assert "Python" in skills  # one strength question is also added
    assert all(q["question"].strip().endswith(("?", ".")) for q in questions)


def test_interview_questions_use_generic_fallback_for_unknown_skill():
    questions = generate_interview_questions(["COBOL"])
    assert len(questions) == 1
    assert "COBOL" in questions[0]["question"]


def test_extract_skills_does_not_confuse_java_with_javascript():
    skills = extract_skills_from_text("Built a front end with JavaScript and React.")
    assert "JavaScript" in skills
    assert "Java" not in skills


def test_full_analyze_end_to_end():
    result = analyze(VALID_PROFILE, JD)
    assert result["match_percentage"] == 75.0
    assert result["missing_skills"] == ["Docker"]
    # matched order follows the (sorted) required-skills order
    assert sorted(result["matched_skills"]) == ["Generative AI", "Python", "SQL"]
    assert len(result["areas_to_strengthen"]) == 1
    assert result["interview_questions"]
    assert result["profile"]["name"] == "Padmakshi Bhonagiri"
