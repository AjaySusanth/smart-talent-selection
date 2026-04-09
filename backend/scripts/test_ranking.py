from __future__ import annotations

import argparse
import asyncio
from uuid import UUID

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import JobRole, JobScoringConfig
from app.schemas.job_description import JobDescriptionCreate
from app.services.jd.manager import create_job_description
from app.services.ranking.ranking_service import get_top_candidates

_DEFAULT_JD_TEXT = """
We are hiring a Python Developer.
Requirements:
- Minimum 3+ years of experience in backend development
- Strong skills in Python, FastAPI, PostgreSQL, and Docker
- Nice to have Redis and Kubernetes
- Certifications in AWS or Azure are a plus
""".strip()


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a JD and print ranked candidates"
    )
    parser.add_argument(
        "--job-role-id", type=str, default="", help="Existing job role UUID"
    )
    parser.add_argument(
        "--job-role-title",
        type=str,
        default="Senior Backend Engineer",
        help="Role title if --job-role-id is not provided",
    )
    parser.add_argument("--jd-text", type=str, default=_DEFAULT_JD_TEXT)
    parser.add_argument("--limit", type=int, default=5)
    return parser.parse_args()


async def _resolve_or_create_job_role(session, job_role_id: str, title: str) -> UUID:
    if job_role_id:
        return UUID(job_role_id)

    existing = await session.execute(select(JobRole).where(JobRole.title == title))
    role = existing.scalar_one_or_none()
    if role is None:
        role = JobRole(title=title, description="Created by ranking smoke test")
        session.add(role)
        await session.flush()

    config = await session.execute(
        select(JobScoringConfig).where(JobScoringConfig.job_role_id == role.id)
    )
    if config.scalar_one_or_none() is None:
        session.add(JobScoringConfig(job_role_id=role.id))
        await session.flush()

    return role.id


async def main() -> None:
    args = _args()

    async with AsyncSessionLocal() as session:
        role_id = await _resolve_or_create_job_role(
            session,
            job_role_id=args.job_role_id,
            title=args.job_role_title,
        )
        await session.commit()

        jd = await create_job_description(
            session,
            JobDescriptionCreate(job_role_id=role_id, raw_text=args.jd_text),
        )

        ranked_rows, total = await get_top_candidates(
            session=session,
            jd_id=jd.id,
            limit=args.limit,
        )

        print(f"JD created: {jd.id}")
        print(f"Total candidates scored: {total}")
        print("Top candidates:")

        for index, row in enumerate(ranked_rows, start=1):
            breakdown = row["breakdown"]
            print(
                f"{index}. candidate={row['candidate_id']} "
                f"final={breakdown['final_score']:.2f} "
                f"semantic={breakdown['semantic_score']:.2f} "
                f"rule={breakdown['rule_score']:.2f} "
                f"skills={breakdown['matching_mandatory_skills']}/{breakdown['total_mandatory_skills']}"
            )


if __name__ == "__main__":
    asyncio.run(main())
