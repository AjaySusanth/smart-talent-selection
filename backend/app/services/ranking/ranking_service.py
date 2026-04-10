from __future__ import annotations

import json
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RankingError

logger = structlog.get_logger(__name__)


_RANKING_SQL = text(
    """
WITH jd AS (
    SELECT id, job_role_id, requirements_json, embedding
    FROM job_descriptions
    WHERE id = :jd_id AND is_active = TRUE
),
config AS (
    SELECT
        COALESCE(jsc.skill_match_weight, 40)::numeric AS skill_w,
        COALESCE(jsc.exp_years_weight, 20)::numeric AS exp_w,
        COALESCE(jsc.projects_weight, 20)::numeric AS project_w,
        COALESCE(jsc.prof_exp_weight, 15)::numeric AS prof_w,
        COALESCE(jsc.certs_weight, 5)::numeric AS cert_w
    FROM jd
    LEFT JOIN job_scoring_config jsc ON jsc.job_role_id = jd.job_role_id
),
requirements AS (
    SELECT
        ARRAY(
            SELECT lower(value)
            FROM jsonb_array_elements_text(
                COALESCE(jd.requirements_json -> 'mandatory_skills', '[]'::jsonb)
            )
        )::text[] AS mandatory_skills,
        ARRAY(
            SELECT lower(value)
            FROM jsonb_array_elements_text(
                COALESCE(jd.requirements_json -> 'preferred_skills', '[]'::jsonb)
            )
        )::text[] AS preferred_skills,
        ARRAY(
            SELECT lower(value)
            FROM jsonb_array_elements_text(
                COALESCE(jd.requirements_json -> 'certifications', '[]'::jsonb)
            )
        )::text[] AS certifications,
        ARRAY[
            'a','an','the','and','or','to','of','for','in','on','at','by','with','from',
            'as','is','are','was','were','be','been','being','this','that','these','those',
            'it','its','into','over','under','across','within','about','after','before',
            'during','through','using','used','work','worked','working','role','roles',
            'team','teams','project','projects','experience','years','year','responsible',
            'responsibilities','developed','managed','support','supporting','analysis'
        ]::text[] AS stop_tokens,
        ARRAY(
            SELECT DISTINCT token
            FROM (
                SELECT value
                FROM jsonb_array_elements_text(
                    COALESCE(jd.requirements_json -> 'mandatory_skills', '[]'::jsonb)
                )
                UNION ALL
                SELECT value
                FROM jsonb_array_elements_text(
                    COALESCE(jd.requirements_json -> 'preferred_skills', '[]'::jsonb)
                )
            ) src
            CROSS JOIN LATERAL regexp_split_to_table(
                lower(src.value),
                '[^a-z0-9#+]+'
            ) AS token
            WHERE token <> ''
            AND char_length(token) >= 2
        )::text[] AS skill_anchor_tokens,
        ARRAY(
            SELECT DISTINCT token
            FROM (
                SELECT COALESCE(jd.requirements_json ->> 'domain', '') AS chunk
                UNION ALL
                SELECT value
                FROM jsonb_array_elements_text(
                    COALESCE(jd.requirements_json -> 'responsibilities', '[]'::jsonb)
                )
                UNION ALL
                SELECT value
                FROM jsonb_array_elements_text(
                    COALESCE(jd.requirements_json -> 'mandatory_skills', '[]'::jsonb)
                )
                UNION ALL
                SELECT value
                FROM jsonb_array_elements_text(
                    COALESCE(jd.requirements_json -> 'preferred_skills', '[]'::jsonb)
                )
            ) src
            CROSS JOIN LATERAL regexp_split_to_table(
                lower(src.chunk),
                '[^a-z0-9#+]+'
            ) AS token
            WHERE token <> ''
            AND char_length(token) >= 2
            AND token <> ALL(
                ARRAY[
                    'a','an','the','and','or','to','of','for','in','on','at','by','with','from',
                    'as','is','are','was','were','be','been','being','this','that','these','those',
                    'it','its','into','over','under','across','within','about','after','before',
                    'during','through','using','used','work','worked','working','role','roles',
                    'team','teams','project','projects','experience','years','year','responsible',
                    'responsibilities','developed','managed','support','supporting','analysis'
                ]::text[]
            )
        )::text[] AS domain_tokens,
        COALESCE(
            NULLIF(jd.requirements_json ->> 'min_experience_years', '')::numeric,
            NULLIF(jd.requirements_json ->> 'min_years_experience', '')::numeric,
            0::numeric
        ) AS min_experience_years
    FROM jd
),
scored AS (
    SELECT
        c.id AS candidate_id,
        c.resume_upload_id,
        c.total_exp_years::numeric AS total_exp_years,
        COALESCE(rel.relevant_months, 0::numeric) AS relevant_experience_months,
        COALESCE(prof.relevant_professional_months, 0::numeric) AS relevant_professional_months,
        CASE
            WHEN c.embedding IS NULL OR jd.embedding IS NULL THEN 0::numeric
            ELSE 100::numeric * (1::numeric - (c.embedding <=> jd.embedding)::numeric)
        END AS semantic_score,

        CASE
            WHEN cardinality(req.mandatory_skills) = 0 THEN 100::numeric
            ELSE (
                skill_stats.matching_mandatory_skills::numeric
                / cardinality(req.mandatory_skills)::numeric
            ) * 100::numeric
        END AS skill_score,

        CASE
            WHEN cardinality(req.mandatory_skills) > 0
                 AND COALESCE(skill_stats.matching_mandatory_skills, 0) < 2 THEN 0::numeric
            WHEN COALESCE(rel.relevant_months, 0::numeric) <= 0::numeric THEN 0::numeric
            ELSE LEAST(
                100::numeric,
                (
                    COALESCE(rel.relevant_months, 0::numeric)
                    / (GREATEST(req.min_experience_years, 1::numeric) * 12::numeric)
                ) * 100::numeric
            )
        END AS exp_score,

        -- Projects score: pure tech overlap (no count bonus)
        CASE
            WHEN COALESCE(proj_stats.project_count, 0) = 0 THEN 0::numeric
            WHEN cardinality(req.mandatory_skills) = 0
                 AND cardinality(req.preferred_skills) = 0 THEN 100::numeric
            ELSE LEAST(
                100::numeric,
                (
                    (
                        0.7::numeric
                        * (
                            COALESCE(proj_stats.required_overlap_count, 0::numeric)
                            / GREATEST(cardinality(req.mandatory_skills), 1)::numeric
                        )
                    )
                    +
                    (
                        0.3::numeric
                        * (
                            COALESCE(proj_stats.preferred_overlap_count, 0::numeric)
                            / GREATEST(cardinality(req.preferred_skills), 1)::numeric
                        )
                    )
                )
                * 100::numeric
            )
        END AS projects_score,

        CASE
            WHEN cardinality(req.mandatory_skills) > 0
                 AND COALESCE(skill_stats.matching_mandatory_skills, 0) < 2 THEN 0::numeric
            WHEN COALESCE(prof.relevant_professional_months, 0::numeric) <= 0::numeric THEN 0::numeric
            ELSE LEAST(
                100::numeric,
                (
                    COALESCE(prof.relevant_professional_months, 0::numeric)
                    / (GREATEST(req.min_experience_years, 1::numeric) * 12::numeric)
                ) * 100::numeric
            )
        END AS professional_score,

        CASE
            WHEN cardinality(req.certifications) = 0 THEN 100::numeric
            ELSE (
                (
                    SELECT COUNT(*)::numeric
                    FROM jsonb_array_elements(COALESCE(c.profile_json -> 'certifications', '[]'::jsonb)) cert
                    WHERE lower(
                        CASE jsonb_typeof(cert)
                            WHEN 'string' THEN trim(BOTH '"' FROM cert::text)
                            WHEN 'object' THEN COALESCE(cert ->> 'name', '')
                            ELSE ''
                        END
                    ) = ANY(req.certifications)
                )
                / cardinality(req.certifications)::numeric
            ) * 100::numeric
        END AS certs_score,

        cardinality(req.mandatory_skills) AS total_mandatory_skills,
        skill_stats.matching_mandatory_skills
    FROM candidates c
    JOIN resume_uploads ru
        ON ru.id = c.resume_upload_id
    CROSS JOIN jd
    CROSS JOIN requirements req
    LEFT JOIN LATERAL (
        SELECT COUNT(DISTINCT lower(cs.skill_name))::int AS matching_mandatory_skills
        FROM candidate_skills cs
        WHERE cs.candidate_id = c.id
        AND lower(cs.skill_name) = ANY(req.mandatory_skills)
    ) skill_stats ON TRUE
    LEFT JOIN LATERAL (
        SELECT COALESCE(SUM(COALESCE(ce.duration_months, 0)), 0)::numeric AS relevant_months
        FROM candidate_experience ce
        WHERE ce.candidate_id = c.id
        AND ce.exp_type <> 'project'
        AND (
            SELECT COUNT(DISTINCT token)
            FROM regexp_split_to_table(
                lower(
                    concat_ws(
                        ' ',
                        COALESCE(ce.role, ''),
                        COALESCE(ce.description, ''),
                        COALESCE(ce.company, '')
                    )
                ),
                '[^a-z0-9#+]+'
            ) AS token
            WHERE token <> ''
            AND char_length(token) >= 2
            AND token <> ALL(req.stop_tokens)
            AND token = ANY(req.mandatory_skills)
        ) >= CASE
            WHEN cardinality(req.mandatory_skills) > 0 THEN 2
            ELSE 1
        END
        AND (
            SELECT COUNT(DISTINCT token)
            FROM regexp_split_to_table(
                lower(
                    concat_ws(
                        ' ',
                        COALESCE(ce.role, ''),
                        COALESCE(ce.description, ''),
                        COALESCE(ce.company, '')
                    )
                ),
                '[^a-z0-9#+]+'
            ) AS token
            WHERE token <> ''
            AND char_length(token) >= 2
            AND token <> ALL(req.stop_tokens)
            AND token = ANY(req.domain_tokens)
        ) >= CASE
            WHEN cardinality(req.mandatory_skills) >= 4 THEN 3
            ELSE 2
        END
    ) rel ON TRUE
    LEFT JOIN LATERAL (
        SELECT COALESCE(SUM(COALESCE(ce.duration_months, 0)), 0)::numeric AS relevant_professional_months
        FROM candidate_experience ce
        WHERE ce.candidate_id = c.id
        AND ce.exp_type = 'professional'
        AND (
            SELECT COUNT(DISTINCT token)
            FROM regexp_split_to_table(
                lower(
                    concat_ws(
                        ' ',
                        COALESCE(ce.role, ''),
                        COALESCE(ce.description, ''),
                        COALESCE(ce.company, '')
                    )
                ),
                '[^a-z0-9#+]+'
            ) AS token
            WHERE token <> ''
            AND char_length(token) >= 2
            AND token <> ALL(req.stop_tokens)
            AND token = ANY(req.mandatory_skills)
        ) >= CASE
            WHEN cardinality(req.mandatory_skills) > 0 THEN 2
            ELSE 1
        END
        AND (
            SELECT COUNT(DISTINCT token)
            FROM regexp_split_to_table(
                lower(
                    concat_ws(
                        ' ',
                        COALESCE(ce.role, ''),
                        COALESCE(ce.description, ''),
                        COALESCE(ce.company, '')
                    )
                ),
                '[^a-z0-9#+]+'
            ) AS token
            WHERE token <> ''
            AND char_length(token) >= 2
            AND token <> ALL(req.stop_tokens)
            AND token = ANY(req.domain_tokens)
        ) >= CASE
            WHEN cardinality(req.mandatory_skills) >= 4 THEN 3
            ELSE 2
        END
    ) prof ON TRUE
    LEFT JOIN LATERAL (
        SELECT
            (
                SELECT COUNT(*)::int
                FROM jsonb_array_elements(COALESCE(c.profile_json -> 'projects', '[]'::jsonb))
            ) AS project_count,
            COALESCE(
                (
                    SELECT COUNT(DISTINCT lower(tech.value))::numeric
                    FROM jsonb_array_elements(
                        COALESCE(c.profile_json -> 'projects', '[]'::jsonb)
                    ) proj
                    CROSS JOIN LATERAL jsonb_array_elements_text(
                        COALESCE(proj -> 'technologies', '[]'::jsonb)
                    ) AS tech(value)
                    WHERE lower(tech.value) = ANY(req.mandatory_skills)
                ),
                0::numeric
            ) AS required_overlap_count,
            COALESCE(
                (
                    SELECT COUNT(DISTINCT lower(tech.value))::numeric
                    FROM jsonb_array_elements(
                        COALESCE(c.profile_json -> 'projects', '[]'::jsonb)
                    ) proj
                    CROSS JOIN LATERAL jsonb_array_elements_text(
                        COALESCE(proj -> 'technologies', '[]'::jsonb)
                    ) AS tech(value)
                    WHERE lower(tech.value) = ANY(req.preferred_skills)
                ),
                0::numeric
            ) AS preferred_overlap_count
    ) proj_stats ON TRUE
    WHERE ru.job_role_id = jd.job_role_id
),
with_scores AS (
    SELECT
        scored.*,
        CASE
            WHEN scored.total_mandatory_skills = 0 THEN 1::numeric
            ELSE (
                scored.matching_mandatory_skills::numeric
                / scored.total_mandatory_skills::numeric
            )
        END AS mandatory_ratio,
        (
            (
                (config.skill_w * scored.skill_score)
                + ((config.exp_w + config.prof_w) * scored.professional_score)
                + (config.project_w * scored.projects_score)
                + (config.cert_w * scored.certs_score)
            ) / 100::numeric
        ) AS raw_rule_score
    FROM scored
    CROSS JOIN config
),
finalised AS (
    SELECT
        candidate_id,
        resume_upload_id,
        total_exp_years,
        relevant_experience_months,
        relevant_professional_months,
        semantic_score,
        skill_score,
        exp_score,
        projects_score,
        professional_score,
        certs_score,
        total_mandatory_skills,
        matching_mandatory_skills,
        mandatory_ratio,
        LEAST(1::numeric, mandatory_ratio / 0.4::numeric) AS gate_multiplier,
        raw_rule_score,
        (raw_rule_score * LEAST(1::numeric, mandatory_ratio / 0.4::numeric)) AS rule_score,
        (0.4::numeric * semantic_score)
            + (0.6::numeric * (raw_rule_score * LEAST(1::numeric, mandatory_ratio / 0.4::numeric))) AS final_score,
        COUNT(*) OVER()::int AS total_candidates
    FROM with_scores
)
SELECT
    candidate_id,
    resume_upload_id,
    total_exp_years,
    ROUND(semantic_score, 2) AS semantic_score,
    ROUND(skill_score, 2) AS skill_score,
    ROUND(exp_score, 2) AS exp_score,
    ROUND(projects_score, 2) AS projects_score,
    ROUND(professional_score, 2) AS professional_score,
    ROUND(certs_score, 2) AS certs_score,
    ROUND(raw_rule_score, 2) AS raw_rule_score,
    ROUND(mandatory_ratio, 4) AS mandatory_ratio,
    ROUND(gate_multiplier, 4) AS gate_multiplier,
    ROUND(rule_score, 2) AS rule_score,
    ROUND(final_score, 2) AS final_score,
    ROUND(relevant_experience_months, 2) AS relevant_experience_months,
    ROUND(relevant_professional_months, 2) AS relevant_professional_months,
    matching_mandatory_skills,
    total_mandatory_skills,
    total_candidates
FROM finalised
ORDER BY final_score DESC, semantic_score DESC
LIMIT :limit;
"""
)

_UPSERT_JOB_MATCH_SQL = text(
    """
INSERT INTO job_matches (
    id, jd_id, candidate_id,
    semantic_score, rule_score, final_score,
    score_breakdown_json, ranked_at
)
VALUES (
    uuid_generate_v4(), :jd_id, :candidate_id,
    :semantic_score, :rule_score, :final_score,
    CAST(:score_breakdown_json AS jsonb), NOW()
)
ON CONFLICT (jd_id, candidate_id)
DO UPDATE SET
    semantic_score = EXCLUDED.semantic_score,
    rule_score = EXCLUDED.rule_score,
    final_score = EXCLUDED.final_score,
    score_breakdown_json = EXCLUDED.score_breakdown_json,
    ranked_at = NOW()
RETURNING id;
"""
)


async def get_top_candidates(
    session: AsyncSession,
    jd_id: UUID,
    limit: int = 20,
) -> tuple[list[dict], int]:
    safe_limit = max(1, min(limit, 100))

    jd_exists = await session.execute(
        text("SELECT 1 FROM job_descriptions WHERE id = :jd_id AND is_active = TRUE"),
        {"jd_id": str(jd_id)},
    )
    if jd_exists.scalar_one_or_none() is None:
        raise RankingError(f"Job description {jd_id} not found or inactive")

    result = await session.execute(
        _RANKING_SQL,
        {
            "jd_id": str(jd_id),
            "limit": safe_limit,
        },
    )

    rows = []
    total_candidates = 0
    for row in result.mappings():
        total_candidates = int(row["total_candidates"] or 0)
        breakdown = {
            "semantic_score": float(row["semantic_score"] or 0),
            "rule_score": float(row["rule_score"] or 0),
            "raw_rule_score": float(row["raw_rule_score"] or 0),
            "final_score": float(row["final_score"] or 0),
            "skill_score": float(row["skill_score"] or 0),
            "exp_score": float(row["exp_score"] or 0),
            "projects_score": float(row["projects_score"] or 0),
            "professional_score": float(row["professional_score"] or 0),
            "certs_score": float(row["certs_score"] or 0),
            "mandatory_ratio": float(row["mandatory_ratio"] or 0),
            "gate_multiplier": float(row["gate_multiplier"] or 0),
            "relevant_experience_months": float(
                row["relevant_experience_months"] or 0
            ),
            "relevant_professional_months": float(
                row["relevant_professional_months"] or 0
            ),
            "matching_mandatory_skills": int(row["matching_mandatory_skills"] or 0),
            "total_mandatory_skills": int(row["total_mandatory_skills"] or 0),
        }
        rows.append(
            {
                "candidate_id": row["candidate_id"],
                "resume_upload_id": row["resume_upload_id"],
                "total_exp_years": float(row["total_exp_years"] or 0),
                "breakdown": breakdown,
            }
        )

    # ── Persist results to job_matches ────────────────────────────────
    for item in rows:
        try:
            await session.execute(
                _UPSERT_JOB_MATCH_SQL,
                {
                    "jd_id": str(jd_id),
                    "candidate_id": str(item["candidate_id"]),
                    "semantic_score": item["breakdown"]["semantic_score"],
                    "rule_score": item["breakdown"]["rule_score"],
                    "final_score": item["breakdown"]["final_score"],
                    "score_breakdown_json": json.dumps(item["breakdown"]),
                },
            )
        except Exception as exc:
            logger.warning(
                "job_match_upsert_failed",
                candidate_id=str(item["candidate_id"]),
                exc=str(exc),
            )

    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.error("job_match_commit_failed", exc=str(exc))

    # ── Enqueue justification tasks for top 5 ─────────────────────────
    from app.workers.tasks.ranking import generate_justification_task

    top_5 = rows[:5]
    for item in top_5:
        try:
            # Task itself handles Redis caching and DB updates
            generate_justification_task.delay(str(jd_id), str(item["candidate_id"]))
            logger.info(
                "justification_task_enqueued",
                candidate_id=str(item["candidate_id"]),
            )
        except Exception as exc:
            logger.warning(
                "justification_task_enqueue_failed",
                candidate_id=str(item["candidate_id"]),
                exc=str(exc),
            )

    # ── Fetch existing justifications for the response ────────────────
    candidate_ids = [str(r["candidate_id"]) for r in rows]
    if candidate_ids:
        justification_result = await session.execute(
            text(
                """
                SELECT candidate_id, justification_text
                FROM job_matches
                WHERE jd_id = :jd_id AND candidate_id = ANY(CAST(:candidate_ids AS uuid[]))
                AND justification_text IS NOT NULL
            """
            ),
            {"jd_id": str(jd_id), "candidate_ids": candidate_ids},
        )
        justification_map = {
            str(row["candidate_id"]): row["justification_text"]
            for row in justification_result.mappings()
        }

        for item in rows:
            item["justification_text"] = justification_map.get(
                str(item["candidate_id"])
            )
    else:
        for item in rows:
            item["justification_text"] = None

    logger.info(
        "jd_ranking_computed",
        jd_id=str(jd_id),
        returned_candidates=len(rows),
        total_candidates=total_candidates,
        limit=safe_limit,
        matches_persisted=len(rows),
        justifications_enqueued=len(top_5),
    )

    return rows, total_candidates
