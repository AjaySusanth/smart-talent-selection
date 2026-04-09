"""
AI Justification generator for top-ranked candidates.

Uses Gemini 2.0 Flash as the primary model, with Groq llama-3.1-8b-instant
as fallback if Gemini's free tier is exhausted or returns an error.

Produces exactly 2 sentences explaining the actual fit quality for a candidate
and a job description. The output must be strict and grounded, not promotional.
"""

from __future__ import annotations

import json
import time

import structlog
from groq import Groq

from app.core.config import settings

logger = structlog.get_logger(__name__)

# ─── Model configuration ─────────────────────────────────────────────────

_PRIMARY_MODEL = "gemini-2.0-flash"
_FALLBACK_MODEL = "llama-3.1-8b-instant"


def _fit_verdict(match_context: dict | None) -> str:
    context = match_context or {}
    final_score = float(context.get("final_score", 0) or 0)
    skill_score = float(context.get("skill_score", 0) or 0)
    matched_mandatory = int(context.get("matching_mandatory_skills", 0) or 0)
    total_mandatory = int(context.get("total_mandatory_skills", 0) or 0)

    if total_mandatory > 0 and matched_mandatory == 0:
        return "Poor fit"
    if skill_score == 0 or final_score < 45:
        return "Poor fit"
    if final_score < 65:
        return "Medium fit"
    if final_score < 80:
        return "Strong fit"
    return "Strong fit"


# ─── Prompt ───────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a talent-matching analyst. Given a Job Description's requirements, a Candidate's profile, and the match scores, write exactly 2 sentences explaining the candidate's fit.

Rules:
1. Be strict and candid. Do not sound generally positive or encouraging unless the scores support it.
2. Use the verdict label exactly as provided in the prompt. Do not invent a different label.
3. If the verdict is Poor fit, state that plainly and do not praise the candidate.
4. Mention only skills, experience, and certifications that are actually present in the match facts.
5. If a candidate has a partial match, acknowledge the exact partial match and the gap.
6. Do not mention frontend, leadership, or other unrelated strengths unless they are directly relevant to the JD.
7. No bullet points, no headers.
8. Return ONLY the 2 sentences, nothing else."""


def _build_justification_prompt(
    jd_requirements: dict,
    candidate_profile: dict,
    match_context: dict | None = None,
) -> str:
    """Build the user prompt with JD + candidate context."""
    jd_section = json.dumps(jd_requirements, indent=2, default=str)

    match_context = match_context or {}
    match_context = dict(match_context)
    match_context["verdict"] = _fit_verdict(match_context)

    match_section = json.dumps(match_context, indent=2, default=str)

    # Extract relevant candidate fields (avoid sending the full blob)
    candidate_summary = {
        "name": candidate_profile.get("full_name", "Unknown"),
        "summary": candidate_profile.get("summary", ""),
        "skills": [
            s.get("name", s) if isinstance(s, dict) else s
            for s in candidate_profile.get(
                "normalised_skills", candidate_profile.get("skills", [])
            )
        ],
        "experience_years": candidate_profile.get("total_experience_years", 0),
        "experience": [
            {"title": e.get("title", ""), "company": e.get("company", "")}
            for e in candidate_profile.get("experience", [])[:3]
        ],
        "projects": [
            {"name": p.get("name", ""), "technologies": p.get("technologies", [])}
            for p in candidate_profile.get("projects", [])[:3]
        ],
        "certifications": [
            c.get("name", c) if isinstance(c, dict) else c
            for c in candidate_profile.get("certifications", [])
        ],
    }
    candidate_section = json.dumps(candidate_summary, indent=2, default=str)

    return (
        f"JOB REQUIREMENTS:\n{jd_section}\n\n"
        f"MATCH CONTEXT:\n{match_section}\n\n"
        f"CANDIDATE PROFILE:\n{candidate_section}\n\n"
        f"Write exactly 2 sentences describing the actual fit. Start with the verdict label and then give only factual evidence from MATCH CONTEXT and CANDIDATE PROFILE."
    )


# ─── Gemini 2.0 Flash (Primary) ──────────────────────────────────────────


def _call_gemini(prompt: str) -> str:
    """Call Gemini 2.0 Flash via the google-genai SDK."""
    from google import genai

    client = genai.Client(api_key=settings.gemini_api_key)

    response = client.models.generate_content(
        model=_PRIMARY_MODEL,
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            temperature=0.3,
            max_output_tokens=120,
        ),
    )

    text = response.text
    if not text or not text.strip():
        raise ValueError("Gemini returned an empty response")
    return text.strip()


# ─── Groq llama-3.1-8b-instant (Fallback) ────────────────────────────────

_groq_client = Groq(api_key=settings.groq_api_key)


def _call_groq_fallback(prompt: str) -> str:
    """Call Groq llama-3.1-8b-instant as fallback."""
    response = _groq_client.chat.completions.create(
        model=_FALLBACK_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=120,
    )

    choice = response.choices[0] if response.choices else None
    content = getattr(choice.message, "content", None) if choice else None
    if not content or not content.strip():
        raise ValueError("Groq fallback returned an empty response")
    return content.strip()


# ─── Public API ───────────────────────────────────────────────────────────


def generate_justification(
    jd_requirements: dict,
    candidate_profile: dict,
    match_context: dict | None = None,
) -> tuple[str, str]:
    """
    Generate a 2-sentence justification for a candidate-JD match.

    Returns:
        Tuple of (justification_text, model_name_used)

    Raises:
        ValueError: If both primary and fallback models fail.
    """
    prompt = _build_justification_prompt(
        jd_requirements,
        candidate_profile,
        match_context,
    )
    start = time.monotonic()

    # Try Gemini 2.0 Flash first
    try:
        text = _call_gemini(prompt)
        model_used = _PRIMARY_MODEL
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "justification_generated",
            model=model_used,
            duration_ms=duration_ms,
            chars=len(text),
        )
        return text, model_used

    except Exception as gemini_exc:
        logger.warning(
            "justification_gemini_failed_trying_fallback",
            exc=str(gemini_exc),
        )

    # Fallback to Groq
    try:
        fallback_start = time.monotonic()
        text = _call_groq_fallback(prompt)
        model_used = _FALLBACK_MODEL
        duration_ms = int((time.monotonic() - fallback_start) * 1000)
        logger.info(
            "justification_generated",
            model=model_used,
            duration_ms=duration_ms,
            chars=len(text),
            fallback=True,
        )
        return text, model_used

    except Exception as fallback_exc:
        logger.error(
            "justification_both_models_failed",
            gemini_exc=str(gemini_exc),
            groq_exc=str(fallback_exc),
        )
        raise ValueError(
            f"Both models failed. Gemini: {gemini_exc}, Groq: {fallback_exc}"
        ) from fallback_exc
