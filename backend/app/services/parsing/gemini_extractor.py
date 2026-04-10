"""
Structured resume extraction using Groq Llama 3.3 70B Versatile.

Task 3.4 — Takes the raw resume text plus hints from Regex (Task 3.2)
and NER (Task 3.3), and produces a validated CandidateProfile JSON.

This is the "brain" of the parsing pipeline. It understands context,
resolves ambiguities (e.g. which dates belong to which job), and
generates a professional summary if one is missing.

Post-processing pipeline (after the model returns):
  1. Overlay verified regex data (email, phone, social links)
  2. Overlay authoritative hyperlinks from DOCX/PDF structure
  3. Resolve missing certification issuers via keyword lookup

URL priority chain (highest wins):
    Hyperlinks from file structure > Regex from text > model output

Design decisions:
    - Uses Groq llama-3.3-70b-versatile for strong instruction following and JSON reliability
  - Injects regex + NER results as "verified hints" to reduce hallucination
  - Returns Pydantic-validated output; falls back to partial data on errors
  - Runs synchronously (Celery worker thread)
"""

from __future__ import annotations

import json
import re
import time
from difflib import SequenceMatcher
from urllib.parse import urlparse

import structlog
from groq import Groq

from app.core.config import settings
from app.schemas.candidate_profile import CandidateProfile
from app.services.parsing.issuer_normaliser import resolve_issuer
from app.services.parsing.ner_extractor import NERResult
from app.services.parsing.regex_extractor import RegexResult
from app.services.parsing.experience_calculator import compute_total_experience_years

logger = structlog.get_logger(__name__)

# ─── Model configuration ──────────────────────────────────────────────────

_MODEL_NAME = "llama-3.3-70b-versatile"

# Configure the SDK once on module import
_client = Groq(api_key=settings.groq_api_key)


# ─── Prompt engineering ───────────────────────────────────────────────────

_SYSTEM_PROMPT = """Extract resume information into the JSON schema below. Rules:
1. Only extract what is explicitly stated. Never invent data.
2. Use null for missing optional fields and [] for missing lists.
3. Dates: "YYYY-MM" if month is known, "YYYY" if only year is known, "Present" if current.
4. Skills: individual items only, never combined strings.
5. Experience and education: most recent first.
6. total_experience_years: sum work experience durations with no overlap.
7. If no summary exists, write a 2-3 sentence summary from skills and experience.

VERIFIED CONTACT DATA (use these exact values, they override resume text):
{regex_hints}

DOCUMENT HYPERLINKS (real URLs behind clickable text — use for project url fields only):
{hyperlink_hints}
URL rules: only assign URLs from this list; do not invent or modify URLs; use null if no confident match.

OUTPUT SCHEMA:
{schema}
"""

_OUTPUT_SCHEMA = """{
    "full_name": "string",
    "email": "string | null",
    "phone": "string | null",
    "location": "string | null",
    "linkedin_url": "string | null",
    "github_url": "string | null",
    "portfolio_url": "string | null",
    "summary": "string",
    "skills": ["string"],
    "languages": ["string"],
    "experience": [{"company": "string", "title": "string", "location": "string | null", "start_date": "YYYY or YYYY-MM", "end_date": "YYYY or YYYY-MM or Present", "responsibilities": ["string"]}],
    "education": [{"institution": "string", "degree": "string", "field_of_study": "string", "start_date": "YYYY", "end_date": "YYYY or Present", "gpa": "string | null"}],
    "certifications": [{"name": "string", "issuer": "string | null", "date": "YYYY | null"}],
    "projects": [{"name": "string", "description": "string", "technologies": ["string"], "url": "string | null", "github_url": "string | null"}],
    "total_experience_years": 0.0
}"""


def _normalise_profile_keys(data: dict, fallback_name: str | None = None) -> dict:
    """
    Backward-compatible field normalization before Pydantic validation.

    Some model responses use older keys like `role` and `description` inside
    experience entries. This remaps them to the current schema.
    """
    # Normalise full name from alternative keys or fallback hints when model returns null.
    full_name = data.get("full_name")
    if not isinstance(full_name, str) or not full_name.strip():
        alt_name = data.get("name")
        if isinstance(alt_name, str) and alt_name.strip():
            data["full_name"] = alt_name.strip()
        elif isinstance(fallback_name, str) and fallback_name.strip():
            data["full_name"] = fallback_name.strip()
        else:
            data["full_name"] = "Unknown Candidate"

    # Guard summary as well because schema requires a string.
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        data["summary"] = "Summary not available from parsed resume text."

    experiences = data.get("experience")
    if not isinstance(experiences, list):
        return data

    for entry in experiences:
        if not isinstance(entry, dict):
            continue

        if "title" not in entry and isinstance(entry.get("role"), str):
            entry["title"] = entry["role"].strip()

        if "responsibilities" not in entry and "description" in entry:
            description = entry.get("description")
            if isinstance(description, str) and description.strip():
                entry["responsibilities"] = [description.strip()]
            elif isinstance(description, list):
                entry["responsibilities"] = [
                    str(item).strip() for item in description if str(item).strip()
                ]

    return data


def _build_prompt(
    text: str,
    regex_hints: RegexResult,
    ner_hints: NERResult,
    hyperlinks: dict | None = None,
) -> str:
    """
    Build the complete prompt with resume text and extraction hints.
    """
    # Format regex hints
    regex_section = json.dumps(regex_hints.to_dict(), indent=2)

    # Format hyperlink hints — only include non-GitHub project URLs
    # (GitHub repo → project matching is handled programmatically)
    if hyperlinks and hyperlinks.get("raw_hrefs"):
        # Filter to website URLs only (GitHub repos handled by fuzzy match)
        website_urls = [
            u
            for u in hyperlinks.get("project_urls", [])
            if "github.com/" not in u.lower()
        ]
        hyperlink_section = json.dumps(website_urls, indent=2) if website_urls else "[]"
    else:
        hyperlink_section = "[]"

    system = _SYSTEM_PROMPT.format(
        regex_hints=regex_section,
        hyperlink_hints=hyperlink_section,
        schema=_OUTPUT_SCHEMA,
    )

    # Combine system prompt with resume text
    return f"{system}\n\n--- RESUME TEXT ---\n{text}\n--- END RESUME TEXT ---"


def _try_repair_json(text: str) -> str | None:
    """
    Attempt to repair truncated JSON from Gemini.

    Common failure mode: max_output_tokens is hit mid-string or mid-object,
    producing output like: {"summary": "A skilled dev...
    This function tries to close open strings, arrays, and braces.

    Returns repaired JSON string, or None if repair is not possible.
    """
    # Strip trailing comma + whitespace (common at truncation point)
    repaired = text.rstrip().rstrip(",")

    # Count open vs close braces/brackets
    open_braces = repaired.count("{") - repaired.count("}")
    open_brackets = repaired.count("[") - repaired.count("]")

    # Check for unterminated string (odd number of unescaped quotes)
    in_string = False
    for i, ch in enumerate(repaired):
        if ch == '"' and (i == 0 or repaired[i - 1] != "\\"):
            in_string = not in_string

    if in_string:
        repaired += '"'

    # Close open brackets then braces (innermost first)
    repaired += "]" * open_brackets
    repaired += "}" * open_braces

    # Validate it actually parses
    try:
        json.loads(repaired)
        return repaired
    except json.JSONDecodeError:
        return None


def _parse_response(
    response_text: str,
    fallback_name: str | None = None,
) -> CandidateProfile:
    """
    Parse and validate the Gemini response into a CandidateProfile.

    Handles common LLM output issues:
      - Markdown code fences
      - Truncated JSON (unterminated strings, missing closing braces)
    """
    cleaned = response_text.strip()

    # Strip markdown code fences if present
    if cleaned.startswith("```"):
        # Remove opening fence
        first_newline = cleaned.index("\n")
        cleaned = cleaned[first_newline + 1 :]
        # Remove closing fence
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    # Parse JSON and validate with Pydantic
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(
            "gemini_json_malformed_attempting_repair",
            error=str(e),
            response_chars=len(cleaned),
            response_tail=cleaned[-200:] if len(cleaned) > 200 else cleaned,
        )

        repaired = _try_repair_json(cleaned)
        if repaired is None:
            logger.error(
                "gemini_json_repair_failed",
                raw_response=cleaned[:500],
            )
            raise ValueError(
                f"Gemini returned unparseable JSON ({e}). "
                f"Response length: {len(cleaned)} chars"
            ) from e

        logger.info("gemini_json_repair_succeeded")
        data = json.loads(repaired)

    data = _normalise_profile_keys(data, fallback_name=fallback_name)
    return CandidateProfile.model_validate(data)


def _call_model(prompt: str) -> str:
    """Call Groq JSON mode and return the assistant message content."""
    response = _client.chat.completions.create(
        model=_MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "You are a resume parser. Return only valid JSON that matches the provided schema.",
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=8192,
    )

    choice = response.choices[0] if response.choices else None
    message = choice.message if choice else None
    content = getattr(message, "content", None) if message else None
    if not content:
        raise ValueError("Groq returned an empty response")
    return content


# ─── Post-processing: Hyperlink merge ─────────────────────────────────────

# ─── Fuzzy matching config ────────────────────────────────────────────────

# Generic tokens with low signal value in repo slug/project matching.
_LOW_SIGNAL_TOKENS = {
    "app",
    "application",
    "demo",
    "project",
    "repo",
    "website",
    "portfolio",
    "web",
    "site",
    "platform",
    "tool",
    "system",
    "service",
    "api",
}

_HIGH_CONFIDENCE_THRESHOLD = 0.72
_MEDIUM_CONFIDENCE_THRESHOLD = 0.45
_AMBIGUITY_GAP_THRESHOLD = 0.12


def _extract_slug(url: str) -> str:
    """Extract the final path segment from a GitHub repo URL."""
    return urlparse(url).path.strip("/").split("/")[-1].removesuffix(".git")


def _text_tokens(text: str) -> set[str]:
    """Normalise text into lower-case alphanumeric tokens."""
    text = _split_camel(text)
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text)
    return {_normalise_token(token) for token in text.split() if token.strip()}


def _is_acronym_of_any(slug: str, projects: list) -> bool:
    """Return True if the slug is an acronym for any project name."""
    slug_acronym = _normalise_token(slug.replace("-", "").replace("_", ""))
    if not slug_acronym:
        return False

    for project in projects:
        project_tokens = [
            token
            for token in _text_tokens(project.name)
            if token not in _LOW_SIGNAL_TOKENS
        ]
        project_acronym = "".join(token[0] for token in project_tokens if token)
        if project_acronym and slug_acronym == project_acronym.lower():
            return True
    return False


def _is_slug_acronym_for_project(slug: str, project) -> bool:
    """Return True when the slug matches the acronym of one project."""
    slug_acronym = _normalise_token(slug.replace("-", "").replace("_", ""))
    project_tokens = [
        token for token in _text_tokens(project.name) if token not in _LOW_SIGNAL_TOKENS
    ]
    project_acronym = "".join(token[0] for token in project_tokens if token)
    return bool(
        slug_acronym and project_acronym and slug_acronym == project_acronym.lower()
    )


def _filter_project_urls_to_resume(
    project_urls: list[str], projects: list
) -> tuple[list[str], list[str]]:
    """
    Split extracted project URLs into URLs that appear to belong to resume projects
    and phantom URLs that have no signal against any project in the resume.
    """
    resume_urls: list[str] = []
    phantom_urls: list[str] = []

    all_project_name_tokens: set[str] = set()
    all_tech_tokens: set[str] = set()

    for project in projects:
        all_project_name_tokens.update(_text_tokens(project.name))
        for tech in project.technologies or []:
            all_tech_tokens.update(_text_tokens(tech))

    for url in list(dict.fromkeys(project_urls)):
        if "github.com/" not in url.lower():
            resume_urls.append(url)
            continue

        slug = _extract_slug(url)
        slug_tokens = _text_tokens(slug)

        has_name_overlap = bool(slug_tokens & all_project_name_tokens)
        has_tech_overlap = bool(slug_tokens & all_tech_tokens)
        is_acronym = _is_acronym_of_any(slug, projects)

        if has_name_overlap or has_tech_overlap or is_acronym:
            resume_urls.append(url)
        else:
            phantom_urls.append(url)

    return resume_urls, phantom_urls


def _score_repo_against_project(
    slug_tokens: set[str], project, stopwords: set[str]
) -> float:
    """
    Score a GitHub repo slug against a project using name coverage, slug precision,
    acronym bonus, and technology overlap.
    """
    name_tokens = _text_tokens(project.name) - stopwords
    clean_slug = slug_tokens - stopwords

    if not name_tokens or not clean_slug:
        return 0.0

    intersection = clean_slug & name_tokens
    if not intersection:
        tech_tokens: set[str] = set()
        for tech in project.technologies or []:
            tech_tokens.update(_text_tokens(tech))
        if not (clean_slug & tech_tokens):
            return 0.0

    name_coverage = len(intersection) / len(name_tokens)
    slug_precision = len(intersection) / len(clean_slug)

    score = 0.6 * name_coverage + 0.2 * slug_precision

    if _is_slug_acronym_for_project("-".join(sorted(clean_slug)), project):
        score += 0.3

    tech_tokens: set[str] = set()
    for tech in project.technologies or []:
        tech_tokens.update(_text_tokens(tech))
    tech_overlap = len(clean_slug & tech_tokens)
    score += 0.1 * min(tech_overlap, 2)

    return min(score, 1.0)


def _merge_hyperlinks(profile: CandidateProfile, hyperlinks: dict) -> None:
    """
    Override URL fields in the profile with authoritative hrefs
    extracted from the DOCX/PDF file structure.

    Hyperlinks from the file structure are the MOST trustworthy source
    because they contain the real href, not display text.

        Priority chain (highest wins):
            1. Hyperlinks from file structure (this function)
            2. Regex from visible text
            3. Model output

    GitHub repo URLs are matched to projects by fuzzy slug matching.
        Website URLs are handled by the model prompt (semantic matching).
    """
    if not hyperlinks:
        return

    # LinkedIn — hyperlink source is authoritative
    if hyperlinks.get("linkedin_url"):
        old = profile.linkedin_url
        profile.linkedin_url = hyperlinks["linkedin_url"]
        if old and old != profile.linkedin_url:
            logger.info(
                "linkedin_url_corrected",
                old_url=old,
                new_url=profile.linkedin_url,
                reason="hyperlink_override",
            )

    # GitHub profile — hyperlink source is authoritative
    if hyperlinks.get("github_url"):
        profile.github_url = hyperlinks["github_url"]

    # Portfolio / personal website — detect from project_urls
    # Look for non-platform personal domains in the hyperlinks
    _PLATFORM_DOMAINS = {
        "github.com", "linkedin.com", "medium.com", "dev.to",
        "youtube.com", "twitter.com", "x.com", "facebook.com",
        "instagram.com", "stackoverflow.com", "leetcode.com",
        "hackerrank.com", "leanpub.com", "patents.google.com",
        "reactnative.dev", "npmjs.com", "pypi.org",
    }
    project_urls = hyperlinks.get("project_urls", [])
    if not profile.portfolio_url:
        for url in project_urls:
            if url.startswith("mailto:"):
                continue
            try:
                from urllib.parse import urlparse as _urlparse
                parsed = _urlparse(url)
                domain = parsed.netloc.lower().removeprefix("www.")
                # Skip known platforms
                if any(domain.endswith(p) for p in _PLATFORM_DOMAINS):
                    continue
                # Skip GitHub repo URLs
                if "github.com" in domain:
                    continue
                # A personal portfolio is typically a short path (/ or /about etc.)
                path_parts = [p for p in parsed.path.split("/") if p]
                if len(path_parts) <= 1:
                    profile.portfolio_url = url
                    logger.info(
                        "portfolio_url_detected",
                        url=url,
                        source="hyperlink_project_urls",
                    )
                    break
            except Exception:
                continue

    # GitHub repo URLs — fuzzy match to projects by name
    github_repo_urls = [u for u in project_urls if "github.com/" in u.lower()]
    if github_repo_urls and profile.projects:
        resume_urls, phantom_urls = _filter_project_urls_to_resume(
            github_repo_urls, profile.projects
        )
        if phantom_urls:
            logger.info(
                "project_urls_filtered_as_phantom",
                phantom_urls=phantom_urls,
                count=len(phantom_urls),
                reason="no_signal_against_any_resume_project",
            )
        if resume_urls:
            _assign_github_repos(profile.projects, resume_urls)


def _tokenize(text: str) -> set[str]:
    """Split text into lowercase tokens, stripping hyphens/underscores."""
    return set(text.lower().replace("-", " ").replace("_", " ").split())


def _split_camel(text: str) -> str:
    """Insert spaces before camel-case boundaries."""
    return re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)


def _normalise_token(token: str) -> str:
    """Normalise token variants for resilient lexical matching."""
    token = token.lower().strip()
    if token.endswith("ies") and len(token) > 4:
        token = f"{token[:-3]}y"
    elif token.endswith("s") and len(token) > 3 and not token.endswith("ss"):
        token = token[:-1]
    return token


def _normalise_text_tokens(text: str) -> list[str]:
    """Tokenise text into normalized alphanumeric units."""
    text = _split_camel(text)
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text)
    tokens = [_normalise_token(t) for t in text.split() if t.strip()]
    return [t for t in tokens if t]


def _acronym(tokens: set[str]) -> str:
    """Build acronym from high-signal tokens."""
    filtered = [t for t in tokens if t and t not in _LOW_SIGNAL_TOKENS]
    return "".join(t[0] for t in filtered)


def _repo_slug(url: str) -> str:
    """Extract normalized repository slug from URL."""
    slug = urlparse(url).path.strip("/").split("/")[-1]
    return slug.removesuffix(".git")


def _project_context_tokens(project) -> set[str]:
    """Collect tokens from name, description and technologies for context matching."""
    name_tokens = _normalise_text_tokens(project.name)
    description_tokens = _normalise_text_tokens(project.description or "")
    tech_tokens: list[str] = []
    for tech in project.technologies:
        tech_tokens.extend(_normalise_text_tokens(tech))
    return set(name_tokens + description_tokens + tech_tokens)


def _pair_signals(
    repo_tokens: set[str],
    project_name_tokens: set[str],
    project_context_tokens: set[str],
) -> dict[str, float]:
    """Compute independent lexical signals for a repo/project pair."""
    overlap_name = repo_tokens & project_name_tokens
    overlap_context = repo_tokens & project_context_tokens

    name_overlap_ratio = len(overlap_name) / max(len(project_name_tokens), 1)
    context_overlap_ratio = len(overlap_context) / max(len(repo_tokens), 1)
    jaccard = len(overlap_name) / max(len(repo_tokens | project_name_tokens), 1)

    repo_joined = " ".join(sorted(repo_tokens))
    proj_joined = " ".join(sorted(project_name_tokens))
    char_ratio = SequenceMatcher(None, repo_joined, proj_joined).ratio()

    repo_acronym = _acronym(repo_tokens)
    proj_acronym = _acronym(project_name_tokens)
    acronym_match = 1.0 if repo_acronym and repo_acronym == proj_acronym else 0.0

    signals_positive = sum(
        [
            name_overlap_ratio >= 0.5,
            context_overlap_ratio >= 0.34,
            char_ratio >= 0.72,
            acronym_match == 1.0,
        ]
    )

    score = (
        0.6 * name_overlap_ratio
        + 0.2 * slug_precision_from_overlap(repo_tokens, project_name_tokens)
        + 0.2 * char_ratio
        + 0.1 * acronym_match
    )

    # Keep the score in [0, 1]
    score = min(score, 1.0)

    return {
        "score": score,
        "name_overlap_ratio": name_overlap_ratio,
        "context_overlap_ratio": context_overlap_ratio,
        "jaccard": jaccard,
        "char_ratio": char_ratio,
        "acronym_match": acronym_match,
        "signals_positive": float(signals_positive),
    }


def slug_precision_from_overlap(
    repo_tokens: set[str], project_name_tokens: set[str]
) -> float:
    """Compute how much of the slug is relevant to the project name."""
    overlap = repo_tokens & project_name_tokens
    if not repo_tokens:
        return 0.0
    return len(overlap) / len(repo_tokens)


def _assign_github_repos(projects: list, github_urls: list[str]) -> None:
    """
    Match GitHub repo URLs to projects by fuzzy-matching the repo slug
    against project names.

    Guards:
      - Stopword tokens ("app", "system", etc.) are excluded from matching
      - At least 2 non-stopword tokens must overlap for a match
      - Unmatched repos are logged at warning level, NOT assigned positionally
    """
    project_name_tokens = {
        i: _text_tokens(project.name) - _LOW_SIGNAL_TOKENS
        for i, project in enumerate(projects)
    }

    edges: list[dict] = []
    per_repo_scores: dict[str, list[dict]] = {}

    for repo_url in github_urls:
        slug = _repo_slug(repo_url)
        repo_tokens = _text_tokens(slug) - _LOW_SIGNAL_TOKENS
        if not repo_tokens:
            logger.warning(
                "github_repo_unmatched",
                repo_url=repo_url,
                slug=slug,
                reason="repo_slug_has_no_high_signal_tokens",
            )
            continue

        scored_candidates: list[dict] = []
        for idx, project in enumerate(projects):
            score = _score_repo_against_project(
                repo_tokens, project, _LOW_SIGNAL_TOKENS
            )
            project_context_tokens = (
                _project_context_tokens(project) - _LOW_SIGNAL_TOKENS
            )
            name_overlap = repo_tokens & project_name_tokens[idx]
            context_overlap = repo_tokens & project_context_tokens
            name_coverage = len(name_overlap) / max(len(project_name_tokens[idx]), 1)
            slug_precision = len(name_overlap) / max(len(repo_tokens), 1)
            char_ratio = SequenceMatcher(
                None,
                " ".join(sorted(repo_tokens)),
                " ".join(sorted(project_name_tokens[idx])),
            ).ratio()
            acronym_match = 1.0 if _is_acronym_of_any(slug, [project]) else 0.0
            signals = {
                "score": score,
                "name_overlap_ratio": name_coverage,
                "context_overlap_ratio": len(context_overlap)
                / max(len(repo_tokens), 1),
                "jaccard": len(name_overlap)
                / max(len(repo_tokens | project_name_tokens[idx]), 1),
                "char_ratio": char_ratio,
                "acronym_match": acronym_match,
                "signals_positive": float(
                    sum(
                        [
                            name_coverage >= 0.5,
                            len(context_overlap) > 0,
                            char_ratio >= 0.72,
                            acronym_match == 1.0,
                        ]
                    )
                ),
            }
            candidate = {
                "repo_url": repo_url,
                "repo_slug": slug,
                "repo_tokens": sorted(repo_tokens),
                "project_idx": idx,
                "project_name": project.name,
                **signals,
            }
            scored_candidates.append(candidate)
            edges.append(candidate)

        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        per_repo_scores[repo_url] = scored_candidates[:3]

    assigned_projects: set[int] = set()
    assigned_repos: set[str] = set()

    edges.sort(key=lambda x: x["score"], reverse=True)
    for edge in edges:
        repo_url = edge["repo_url"]
        project_idx = edge["project_idx"]
        if repo_url in assigned_repos or project_idx in assigned_projects:
            continue

        top_candidates = per_repo_scores.get(repo_url, [])
        best = top_candidates[0] if top_candidates else None
        second = top_candidates[1] if len(top_candidates) > 1 else None
        ambiguity_gap = (
            best["score"] - second["score"]
            if best is not None and second is not None
            else 1.0
        )

        score = edge["score"]
        signals_positive = int(edge["signals_positive"])

        is_high = score >= _HIGH_CONFIDENCE_THRESHOLD
        is_medium = (
            score >= _MEDIUM_CONFIDENCE_THRESHOLD
            and ambiguity_gap >= _AMBIGUITY_GAP_THRESHOLD
        )
        has_min_signals = signals_positive >= 2 or score >= 0.85

        if (is_high or is_medium) and has_min_signals:
            projects[project_idx].github_url = repo_url
            assigned_projects.add(project_idx)
            assigned_repos.add(repo_url)
            logger.info(
                "github_repo_matched",
                repo_url=repo_url,
                project_name=projects[project_idx].name,
                score=round(score, 4),
                ambiguity_gap=round(ambiguity_gap, 4),
                signals_positive=signals_positive,
                name_overlap_ratio=round(edge["name_overlap_ratio"], 4),
                context_overlap_ratio=round(edge["context_overlap_ratio"], 4),
                char_ratio=round(edge["char_ratio"], 4),
                acronym_match=bool(edge["acronym_match"]),
            )

    for repo_url in github_urls:
        if repo_url in assigned_repos:
            continue
        top_candidates = per_repo_scores.get(repo_url, [])
        best = top_candidates[0] if top_candidates else None
        logger.warning(
            "github_repo_unmatched",
            repo_url=repo_url,
            reason="no_confident_project_match",
            best_project=best["project_name"] if best else None,
            best_score=round(best["score"], 4) if best else None,
            top_candidates=[
                {
                    "project": c["project_name"],
                    "score": round(c["score"], 4),
                    "signals_positive": int(c["signals_positive"]),
                }
                for c in top_candidates
            ],
        )


# ─── Post-processing: Issuer normalisation ────────────────────────────────


def _apply_issuer_normalisation(profile: CandidateProfile) -> None:
    """
    Fill in missing certification issuers using keyword lookup.

    Runs resolve_issuer() on every certification where Gemini
    returned issuer=None.
    """
    for cert in profile.certifications:
        cert.issuer = resolve_issuer(cert.name, cert.issuer)


# ─── Main extraction function ─────────────────────────────────────────────

def extract_structured_profile(
    text: str,
    regex_hints: RegexResult,
    ner_hints: NERResult,
    hyperlinks: dict | None = None,
) -> CandidateProfile:
    """
    Extract a structured candidate profile from resume text using Groq.

        This function:
            1. Builds a prompt with the resume text and extraction hints
            2. Calls Groq llama-3.3-70b-versatile for structured JSON extraction
            3. Validates the response with Pydantic
            4. Overlays verified regex data (email, phone, links)
            5. Overlays authoritative hyperlinks from DOCX/PDF structure
            6. Resolves missing certification issuers

    Args:
        text: Normalised resume text from the text extractor
        regex_hints: Deterministic fields from regex extraction
        ner_hints: Named entities from NER extraction
        hyperlinks: Authoritative hrefs from DOCX/PDF file structure

    Returns:
        Validated CandidateProfile with all extracted data

    Raises:
        ValueError: If the model returns unparseable or invalid JSON
        Exception: For API errors (rate limits, network issues)
    """
    start_time = time.monotonic()

    prompt = _build_prompt(text, regex_hints, ner_hints, hyperlinks)

    logger.info(
        "structured_profile_api_call_started",
        model=_MODEL_NAME,
        provider="groq",
        prompt_chars=len(prompt),
    )

    # Call Groq
    response_text = _call_model(prompt)

    duration_ms = int((time.monotonic() - start_time) * 1000)

    logger.info(
        "structured_profile_api_call_complete",
        duration_ms=duration_ms,
        response_chars=len(response_text),
    )

    # Parse and validate
    fallback_name = ner_hints.names[0] if ner_hints.names else None
    profile = _parse_response(response_text, fallback_name=fallback_name)

    # ── Post-processing overlay pipeline ───────────────────────────────
    # Each step can override the previous one. Order matters:
    #   Groq model (base) → Regex (verified text) → Hyperlinks (authoritative)

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
    _merge_hyperlinks(profile, hyperlinks or {})

    # Step 3: Resolve missing certification issuers
    _apply_issuer_normalisation(profile)

    # Step 4: Deterministic experience calculation (overrides LLM arithmetic)
    llm_exp_years = profile.total_experience_years
    computed_exp_years = compute_total_experience_years(profile)
    if computed_exp_years > 0:
        profile.total_experience_years = computed_exp_years
        if abs(computed_exp_years - llm_exp_years) > 0.5:
            logger.warning(
                "experience_years_corrected",
                llm_value=llm_exp_years,
                computed_value=computed_exp_years,
                delta=round(computed_exp_years - llm_exp_years, 1),
            )

    logger.info(
        "gemini_extraction_complete",
        duration_ms=duration_ms,
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
