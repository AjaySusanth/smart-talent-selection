"""
Structured resume extraction using Google Gemini 2.5 Flash.

Task 3.4 — Takes raw resume text plus hints from Regex (Task 3.2) and
NER (Task 3.3), and produces a validated CandidateProfile JSON.

Post-processing overlay (order = priority, highest last):
  Gemini output → Regex overlay → Hyperlink overlay (if provided)

Design decisions:
  - Uses gemini-2.5-flash for speed and free-tier availability
  - Low temperature (0.1) for deterministic, consistent extraction
  - Regex + NER results injected as verified hints to reduce hallucination
  - Pydantic validation catches malformed LLM output before it touches the DB
  - Runs synchronously inside Celery worker threads
"""

from __future__ import annotations

import json
import time

import google.generativeai as genai
import structlog
from groq import Groq

from app.core.config import settings
from app.schemas.candidate_profile import CandidateProfile
from app.services.parsing.ner_extractor import NERResult
from app.services.parsing.issuer_normaliser import resolve_issuer

logger = structlog.get_logger(__name__)

# ─── LLM clients configuration ─────────────────────────────────────────────

# Primary: Gemini 2.5 Flash
_GEMINI_MODEL = "gemini-2.5-flash"
genai.configure(api_key=settings.gemini_api_key)

# Fallback: Llama 3 70B (via Groq)
_GROQ_MODEL = "llama-3.3-70b-versatile"
_groq_client = Groq(api_key=settings.groq_api_key)

_gemini_config = genai.GenerationConfig(
    temperature=0.1,
    top_p=0.95,
    max_output_tokens=4096,
    response_mime_type="application/json",
)

_gemini_model = genai.GenerativeModel(
    model_name=_GEMINI_MODEL,
    generation_config=_gemini_config,
)


# ─── Prompt engineering ───────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a Senior Recruitment Data Analyst with 15 years of experience parsing resumes.
Extract ALL information from the resume text and return it as a structured JSON object.

RULES:
1. Extract ONLY what is explicitly stated. Do NOT invent data.
2. Missing optional fields → null. Missing list fields → [].
3. Dates: use "YYYY-MM" when month is known, "YYYY" when only year is known. Use "Present" for active roles.
4. Skills: one item per skill — never combine ("React" and "Next.js" are separate, not "React/Next.js").
5. Experience and Education: ordered most recent first.
6. total_experience_years: sum all work experience durations (non-overlapping).
7. If no professional summary exists, generate a concise 2-3 sentence one from the content.

VERIFIED CONTACT DATA (from regex — use these exact values, do not change):
{regex_hints}

ENTITY HINTS (from NER — use as guidance, not gospel):
{ner_hints}

Return valid JSON matching this schema exactly:
{schema}
"""


def _build_prompt(text: str, regex_hints: RegexResult, ner_hints: NERResult) -> str:
    system = _SYSTEM_PROMPT.format(
        regex_hints=json.dumps(regex_hints.to_dict(), indent=2),
        ner_hints=json.dumps(ner_hints.to_dict(), indent=2),
        schema=json.dumps(CandidateProfile.model_json_schema(), indent=2),
    )
    return f"{system}\n\n--- RESUME TEXT ---\n{text}\n--- END RESUME TEXT ---"


def _parse_response(response_text: str) -> CandidateProfile:
    """
    Parse LLM response into a validated CandidateProfile.
    Handles markdown code fences that models sometimes wrap JSON in.
    """
    cleaned = response_text.strip()

    # Handle various markdown JSON wrappers
    if "```" in cleaned:
        # Extract content between triple backticks
        import re
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1)

    # Some models might return an empty string if they fail silently
    if not cleaned:
        raise ValueError("LLM returned an empty response string")

    return CandidateProfile.model_validate(json.loads(cleaned))


def _extract_with_gemini(prompt: str) -> str:
    """Run extraction using Gemini 2.5 Flash."""
    response = _gemini_model.generate_content(prompt)

    if not response.candidates or not response.candidates[0].content.parts:
        finish_reason = (
            getattr(response.candidates[0], "finish_reason", "unknown")
            if response.candidates
            else "no_candidates"
        )
        raise ValueError(f"Gemini response blocked or empty. Reason: {finish_reason}")

    return response.candidates[0].content.parts[0].text


def _extract_with_groq(prompt: str) -> str:
    """Run extraction using Llama 3 70B via Groq."""
    chat_completion = _groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=_GROQ_MODEL,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    return chat_completion.choices[0].message.content or ""


# ─── Post-processing overlays ─────────────────────────────────────────────

def _overlay_regex(profile: CandidateProfile, regex_hints: RegexResult) -> None:
    """
    Force-replace contact fields with regex-extracted values.
    Regex patterns on visible text are more reliable than LLM guesses.
    """
    if regex_hints.emails:
        profile.email = regex_hints.emails[0]
    if regex_hints.phones:
        profile.phone = regex_hints.phones[0]
    if regex_hints.linkedin_url:
        profile.linkedin_url = regex_hints.linkedin_url
    if regex_hints.github_url:
        profile.github_url = regex_hints.github_url
    if regex_hints.portfolio_urls:
        profile.portfolio_url = regex_hints.portfolio_urls[0]


def _overlay_hyperlinks(profile: CandidateProfile, hyperlinks: dict) -> None:
    """
    Override URL fields with authoritative hrefs from the file structure.

    DOCX XML rels / PDF annotations contain the real href, not the display
    text. This is the highest-priority source for LinkedIn and GitHub URLs.
    Logs a warning if the LinkedIn URL is being corrected.
    """
    if hyperlinks.get("linkedin_url"):
        old = profile.linkedin_url
        profile.linkedin_url = hyperlinks["linkedin_url"]
        if old and old != profile.linkedin_url:
            logger.info(
                "linkedin_url_corrected",
                old_url=old,
                new_url=profile.linkedin_url,
            )

    if hyperlinks.get("github_url"):
        profile.github_url = hyperlinks["github_url"]

    # Assign project URLs in document order
    project_urls = hyperlinks.get("project_urls", [])
    if project_urls and profile.projects:
        github_urls = [u for u in project_urls if "github.com/" in u.lower()]
        website_urls = [u for u in project_urls if "github.com/" not in u.lower()]
        for i, project in enumerate(profile.projects):
            if i < len(github_urls):
                project.github_url = github_urls[i]
            if i < len(website_urls):
                project.url = website_urls[i]


# ─── Main extraction function ─────────────────────────────────────────────

def extract_structured_profile(
    text: str,
    regex_hints: RegexResult,
    ner_hints: NERResult,
    hyperlinks: dict | None = None,
) -> CandidateProfile:
    """
    Extract a structured candidate profile from resume text using LLMs.

    Strategy:
      1. Try Gemini 2.5 Flash first (fast, reliable JSON).
      2. If Gemini fails (API error, safety block), fall back to Llama 3 70B via Groq.
      3. Apply all post-processing (regex, hyperlinks, issuer normalisation).

    Args:
        text: Normalised resume text
        regex_hints: Deterministic fields from regex extraction
        ner_hints: Named entities from NER extraction
        hyperlinks: Real href values from DOCX/PDF structure (optional)

    Returns:
        Validated CandidateProfile

    Raises:
        ValueError: If both models fail to return valid data
    """
    start_time = time.monotonic()
    prompt = _build_prompt(text, regex_hints, ner_hints)

    # ─── Model Execution ───────────────────────────────────────────────────
    raw_json = None
    used_model = _GEMINI_MODEL

    try:
        logger.info("llm_extraction_started", model=_GEMINI_MODEL)
        raw_json = _extract_with_gemini(prompt)
    except Exception as e:
        logger.warning(
            "gemini_extraction_failed",
            error=str(e),
            action="falling_back_to_groq",
            fallback_model=_GROQ_MODEL,
        )
        try:
            used_model = _GROQ_MODEL
            raw_json = _extract_with_groq(prompt)
        except Exception as groq_err:
            logger.error("all_llm_models_failed", error=str(groq_err))
            raise ValueError(f"Full extraction pipeline failure: {str(groq_err)}") from groq_err

    duration_ms = int((time.monotonic() - start_time) * 1000)
    logger.info("llm_extraction_finished", model=used_model, duration_ms=duration_ms)

    # ─── Validation & Post-processing ──────────────────────────────────────
    profile = _parse_response(raw_json)

    # Step 1: Overlay verified regex data
    if regex_hints.emails:
        profile.email = regex_hints.emails[0]
    if regex_hints.phones:
        profile.phone = regex_hints.phones[0]
    if regex_hints.linkedin_url:
        profile.linkedin_url = regex_hints.linkedin_url
    if regex_hints.github_url:
        profile.github_url = regex_hints.github_url
    if regex_hints.portfolio_urls:
        profile.portfolio_url = regex_hints.portfolio_urls[0]

    # Step 2: Overlay authoritative hyperlinks (highest priority)
    if hyperlinks:
        _overlay_hyperlinks(profile, hyperlinks)

    # Step 3: Post‑processing: Issuer normalisation
    def _apply_issuer_normalisation(p: CandidateProfile) -> None:
        """Fill missing certification issuers using keyword lookup via resolve_issuer."""
        for cert in p.certifications:
            cert.issuer = resolve_issuer(cert.name, cert.issuer)

    _apply_issuer_normalisation(profile)

    logger.info(
        "llm_extraction_complete",
        duration_ms=duration_ms,
        model=used_model,
        full_name=profile.full_name,
        skills_count=len(profile.skills),
        experience_count=len(profile.experience),
        education_count=len(profile.education),
        certifications_count=len(profile.certifications),
        projects_count=len(profile.projects),
        total_exp_years=profile.total_experience_years,
        linkedin_url=profile.linkedin_url,
        github_url=profile.github_url,
    )

    return profile

