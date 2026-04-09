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
        CASE
            WHEN c.embedding IS NULL OR jd.embedding IS NULL THEN 0::numeric
            ELSE 100::numeric * (1::numeric - (c.embedding <=> jd.embedding)::numeric)
        END AS semantic_score,

        CASE
            WHEN cardinality(req.mandatory_skills) = 0 THEN 100::numeric
            ELSE (
                (
                    SELECT COUNT(DISTINCT lower(cs.skill_name))::numeric
                    FROM candidate_skills cs
                    WHERE cs.candidate_id = c.id
                    AND lower(cs.skill_name) = ANY(req.mandatory_skills)
                )
                / cardinality(req.mandatory_skills)::numeric
            ) * 100::numeric
        END AS skill_score,

        CASE
            WHEN req.min_experience_years <= 0 THEN 100::numeric
            WHEN c.total_exp_years::numeric >= req.min_experience_years THEN 100::numeric
            ELSE GREATEST(
                0::numeric,
                (c.total_exp_years::numeric / req.min_experience_years) * 100::numeric * 0.9::numeric
            )
        END AS exp_score,

        -- Projects score: 50% project count (capped at 3) + 50% tech relevance
        CASE
            WHEN (
                SELECT COUNT(*)
                FROM candidate_experience ce
                WHERE ce.candidate_id = c.id AND ce.exp_type = 'project'
            ) = 0 THEN 0::numeric
            ELSE LEAST(100::numeric, (
                -- Count component: up to 50 pts for having 3+ projects
                LEAST(50::numeric,
                    (SELECT COUNT(*)::numeric FROM candidate_experience ce
                     WHERE ce.candidate_id = c.id AND ce.exp_type = 'project')
                    * 50.0 / 3.0
                )
                +
                -- Relevance component: up to 50 pts for tech overlap with JD skills
                CASE
                    WHEN cardinality(req.mandatory_skills || req.preferred_skills) = 0
                        THEN 50::numeric
                    ELSE LEAST(50::numeric,
                        COALESCE((
                            SELECT COUNT(DISTINCT lower(tech.value))::numeric
                                * 50.0
                                / GREATEST(1, cardinality(req.mandatory_skills || req.preferred_skills))::numeric
                            FROM jsonb_array_elements(
                                COALESCE(c.profile_json -> 'projects', '[]'::jsonb)
                            ) proj,
                            jsonb_array_elements_text(
                                COALESCE(proj -> 'technologies', '[]'::jsonb)
                            ) tech
                            WHERE lower(tech.value) = ANY(
                                req.mandatory_skills || req.preferred_skills
                            )
                        ), 0::numeric)
                    )
                END
            ))
        END AS projects_score,

        CASE
            WHEN req.min_experience_years <= 0 THEN
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM candidate_experience ce
                        WHERE ce.candidate_id = c.id
                        AND ce.exp_type = 'professional'
                    ) THEN 100::numeric
                    ELSE 0::numeric
                END
            ELSE LEAST(
                100::numeric,
                (
                    COALESCE(
                        (
                            SELECT SUM(ce.duration_months)::numeric
                            FROM candidate_experience ce
                            WHERE ce.candidate_id = c.id
                            AND ce.exp_type = 'professional'
                        ),
                        0::numeric
                    )
                    / (req.min_experience_years * 12::numeric)
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
        (
            SELECT COUNT(DISTINCT lower(cs.skill_name))::int
            FROM candidate_skills cs
            WHERE cs.candidate_id = c.id
            AND lower(cs.skill_name) = ANY(req.mandatory_skills)
        ) AS matching_mandatory_skills
    FROM candidates c
    JOIN resume_uploads ru
        ON ru.id = c.resume_upload_id
    CROSS JOIN jd
    CROSS JOIN requirements req
    WHERE ru.job_role_id = jd.job_role_id
),
with_scores AS (
    SELECT
        scored.*,
        (
            (
                (config.skill_w * scored.skill_score)
                + (config.exp_w * scored.exp_score)
                + (config.project_w * scored.projects_score)
                + (config.prof_w * scored.professional_score)
                + (config.cert_w * scored.certs_score)
            ) / 100::numeric
        ) AS rule_score
    FROM scored
    CROSS JOIN config
),
finalised AS (
    SELECT
        candidate_id,
        resume_upload_id,
        total_exp_years,
        semantic_score,
        skill_score,
        exp_score,
        projects_score,
        professional_score,
        certs_score,
        total_mandatory_skills,
        matching_mandatory_skills,
        rule_score,
        (0.4::numeric * semantic_score) + (0.6::numeric * rule_score) AS final_score,
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
    ROUND(rule_score, 2) AS rule_score,
    ROUND(final_score, 2) AS final_score,
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
            "final_score": float(row["final_score"] or 0),
            "skill_score": float(row["skill_score"] or 0),
            "exp_score": float(row["exp_score"] or 0),
            "projects_score": float(row["projects_score"] or 0),
            "professional_score": float(row["professional_score"] or 0),
            "certs_score": float(row["certs_score"] or 0),
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
