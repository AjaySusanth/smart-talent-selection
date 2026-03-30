from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import Candidate, JobRole, JobScoringConfig, ResumeUpload
from app.models.resume_upload import UploadStatus


@dataclass(frozen=True)
class SeedCandidate:
    slug: str
    job_role_title: str
    name: str
    email: str
    phone: str
    linkedin: str
    skills: list[str]
    certifications: list[str]
    languages: list[str]
    total_exp_years: Decimal
    summary_text: str
    raw_text: str


def build_seed_candidates() -> list[SeedCandidate]:
    return [
        SeedCandidate(
            slug="ananya-rao",
            job_role_title="Senior Backend Engineer",
            name="Ananya Rao",
            email="ananya.rao@example.com",
            phone="+91-98765-43210",
            linkedin="https://www.linkedin.com/in/ananyarao",
            skills=["Python", "FastAPI", "PostgreSQL", "Redis", "Docker"],
            certifications=["AWS Certified Developer - Associate"],
            languages=["English", "Hindi"],
            total_exp_years=Decimal("6.5"),
            summary_text="Senior backend engineer with deep experience in Python and distributed API systems. Built high-throughput microservices with FastAPI and PostgreSQL, improved API latency through query optimization, and implemented robust queue-driven processing using Redis-based workers. Strong ownership in production debugging, observability, CI/CD automation, and secure service integrations.",
            raw_text="Ananya Rao has 6+ years of backend development experience. She designed APIs in FastAPI, managed PostgreSQL schemas, and improved reliability with Redis queues and Dockerized deployments.",
        ),
        SeedCandidate(
            slug="ravi-menon",
            job_role_title="Senior Backend Engineer",
            name="Ravi Menon",
            email="ravi.menon@example.com",
            phone="+91-99887-76655",
            linkedin="https://www.linkedin.com/in/ravimenon",
            skills=["Go", "Python", "Kubernetes", "Kafka", "PostgreSQL"],
            certifications=["CKA"],
            languages=["English", "Malayalam"],
            total_exp_years=Decimal("8.0"),
            summary_text="Backend platform engineer focused on scalable event-driven architecture. Built streaming services with Kafka, production-grade APIs, and resilient deployment pipelines on Kubernetes. Experienced in system design, schema evolution, and incident response across cloud-native stacks.",
            raw_text="Ravi Menon worked on high-scale backend platforms, using Go and Python for services and Kafka for asynchronous processing.",
        ),
        SeedCandidate(
            slug="meera-iyer",
            job_role_title="Machine Learning Engineer",
            name="Meera Iyer",
            email="meera.iyer@example.com",
            phone="+91-91234-56789",
            linkedin="https://www.linkedin.com/in/meeraiyer",
            skills=["Python", "PyTorch", "NLP", "MLOps", "Airflow"],
            certifications=["TensorFlow Developer Certificate"],
            languages=["English", "Tamil"],
            total_exp_years=Decimal("4.5"),
            summary_text="Machine learning engineer specializing in NLP systems and model deployment. Built text classification and extraction pipelines, trained transformer-based models, and productionized inference workflows with MLOps practices. Comfortable with experimentation, model evaluation, and collaboration with backend teams.",
            raw_text="Meera Iyer built NLP pipelines in PyTorch and productionized models with MLOps tooling.",
        ),
        SeedCandidate(
            slug="arjun-shetty",
            job_role_title="Machine Learning Engineer",
            name="Arjun Shetty",
            email="arjun.shetty@example.com",
            phone="+91-97654-32109",
            linkedin="https://www.linkedin.com/in/arjunshetty",
            skills=[
                "Python",
                "scikit-learn",
                "TensorFlow",
                "SQL",
                "Feature Engineering",
            ],
            certifications=["Azure AI Engineer Associate"],
            languages=["English", "Kannada"],
            total_exp_years=Decimal("5.0"),
            summary_text="ML engineer with strong applied modeling experience across recommendation and forecasting problems. Designed feature pipelines, trained and tuned models, and delivered measurable improvements in prediction quality. Works effectively from data analysis to model deployment and monitoring.",
            raw_text="Arjun Shetty has hands-on machine learning experience in recommendation systems and forecasting with production deployment.",
        ),
        SeedCandidate(
            slug="priya-nair",
            job_role_title="Frontend Engineer",
            name="Priya Nair",
            email="priya.nair@example.com",
            phone="+91-90011-22334",
            linkedin="https://www.linkedin.com/in/priyanair",
            skills=["React", "TypeScript", "Next.js", "Tailwind CSS", "Jest"],
            certifications=["Meta Front-End Developer"],
            languages=["English", "Malayalam"],
            total_exp_years=Decimal("5.5"),
            summary_text="Frontend engineer experienced in building scalable React and TypeScript applications. Delivered design-system-driven interfaces, improved web performance, and implemented robust test coverage. Strong collaboration with product and backend teams to ship reliable user-facing features.",
            raw_text="Priya Nair builds production frontend applications in React and TypeScript with a focus on usability and performance.",
        ),
        SeedCandidate(
            slug="vikram-joshi",
            job_role_title="Frontend Engineer",
            name="Vikram Joshi",
            email="vikram.joshi@example.com",
            phone="+91-98989-12121",
            linkedin="https://www.linkedin.com/in/vikramjoshi",
            skills=["React", "Redux", "TypeScript", "Cypress", "Vite"],
            certifications=["AWS Cloud Practitioner"],
            languages=["English", "Marathi"],
            total_exp_years=Decimal("4.0"),
            summary_text="Frontend developer with expertise in complex UI state management and modern React tooling. Built reusable component libraries, end-to-end test suites, and analytics-enabled product surfaces. Values performance budgets and maintainable architecture.",
            raw_text="Vikram Joshi has built enterprise-grade React interfaces and test automation suites.",
        ),
        SeedCandidate(
            slug="nisha-verma",
            job_role_title="Senior Backend Engineer",
            name="Nisha Verma",
            email="nisha.verma@example.com",
            phone="+91-98123-88776",
            linkedin="https://www.linkedin.com/in/nishaverma",
            skills=["Java", "Spring Boot", "PostgreSQL", "Redis", "AWS"],
            certifications=["AWS Solutions Architect - Associate"],
            languages=["English", "Hindi"],
            total_exp_years=Decimal("7.0"),
            summary_text="Backend engineer with strong Java and cloud architecture background. Delivered secure API platforms, optimized relational data access, and improved reliability through caching and circuit-breaker patterns. Comfortable owning backend services end to end.",
            raw_text="Nisha Verma developed Spring Boot backend systems with PostgreSQL and AWS infrastructure.",
        ),
        SeedCandidate(
            slug="rahul-kapoor",
            job_role_title="Machine Learning Engineer",
            name="Rahul Kapoor",
            email="rahul.kapoor@example.com",
            phone="+91-93456-76543",
            linkedin="https://www.linkedin.com/in/rahulkapoor",
            skills=["Python", "XGBoost", "MLOps", "MLflow", "Docker"],
            certifications=["Databricks ML Associate"],
            languages=["English", "Hindi"],
            total_exp_years=Decimal("3.8"),
            summary_text="Applied machine learning engineer with practical experience in model lifecycle management. Built tabular ML systems, tracking and versioning workflows, and reproducible training pipelines. Focused on measurable business outcomes and model reliability.",
            raw_text="Rahul Kapoor designed ML pipelines with model tracking and reproducible deployment practices.",
        ),
        SeedCandidate(
            slug="sana-khan",
            job_role_title="Frontend Engineer",
            name="Sana Khan",
            email="sana.khan@example.com",
            phone="+91-92222-33445",
            linkedin="https://www.linkedin.com/in/sanakhan",
            skills=["React", "TypeScript", "GraphQL", "Storybook", "Accessibility"],
            certifications=["Google UX Design Certificate"],
            languages=["English", "Urdu"],
            total_exp_years=Decimal("4.7"),
            summary_text="Frontend engineer focused on accessible and maintainable UI systems. Implemented GraphQL-driven dashboards, reusable Storybook components, and accessibility-compliant workflows. Strong in cross-functional collaboration and iterative delivery.",
            raw_text="Sana Khan built accessible frontend products with React, GraphQL, and component-driven workflows.",
        ),
        SeedCandidate(
            slug="deepak-pillai",
            job_role_title="Senior Backend Engineer",
            name="Deepak Pillai",
            email="deepak.pillai@example.com",
            phone="+91-95555-66778",
            linkedin="https://www.linkedin.com/in/deepakpillai",
            skills=["Python", "Django", "FastAPI", "PostgreSQL", "Celery"],
            certifications=["Professional Scrum Master I"],
            languages=["English", "Malayalam"],
            total_exp_years=Decimal("6.2"),
            summary_text="Backend engineer with strong API and asynchronous processing experience. Built services using Django and FastAPI, designed data models in PostgreSQL, and handled background processing pipelines with Celery. Delivers production-ready services with strong engineering discipline.",
            raw_text="Deepak Pillai built backend services with Django, FastAPI, PostgreSQL, and Celery for asynchronous jobs.",
        ),
    ]


async def ensure_job_roles(session) -> dict[str, JobRole]:
    desired_roles = [
        "Senior Backend Engineer",
        "Machine Learning Engineer",
        "Frontend Engineer",
    ]

    existing = await session.execute(
        select(JobRole).where(JobRole.title.in_(desired_roles))
    )
    role_by_title = {role.title: role for role in existing.scalars().all()}

    missing_titles = [title for title in desired_roles if title not in role_by_title]
    for title in missing_titles:
        role = JobRole(title=title, description=f"Seeded role for {title}")
        session.add(role)

    if missing_titles:
        await session.flush()
        existing = await session.execute(
            select(JobRole).where(JobRole.title.in_(desired_roles))
        )
        role_by_title = {role.title: role for role in existing.scalars().all()}

    return role_by_title


async def ensure_default_scoring_config(session, roles: dict[str, JobRole]) -> None:
    for role in roles.values():
        existing = await session.execute(
            select(JobScoringConfig).where(JobScoringConfig.job_role_id == role.id)
        )
        if existing.scalar_one_or_none() is not None:
            continue

        session.add(
            JobScoringConfig(
                job_role_id=role.id,
                preset_name="Default",
                skill_match_weight=40,
                exp_years_weight=20,
                projects_weight=20,
                prof_exp_weight=15,
                certs_weight=5,
                is_customised=False,
            )
        )


def build_profile_json(candidate: SeedCandidate) -> dict:
    return {
        "name": candidate.name,
        "email": candidate.email,
        "phone": candidate.phone,
        "linkedin": candidate.linkedin,
        "skills": candidate.skills,
        "experience": [
            {
                "company": "TechNova Solutions",
                "role": "Engineer",
                "start": "2019-01",
                "end": None,
                "is_current": True,
                "type": "professional",
                "description": "Contributed to product features and reliability improvements.",
            }
        ],
        "education": [
            {
                "institution": "National Institute of Technology",
                "degree": "B.Tech",
                "field": "Computer Science",
                "graduation_year": 2018,
            }
        ],
        "certifications": candidate.certifications,
        "languages": candidate.languages,
    }


async def ensure_seed_candidates(session, roles: dict[str, JobRole]) -> None:
    for item in build_seed_candidates():
        file_key = f"seed/{item.slug}.pdf"

        upload_row = await session.execute(
            select(ResumeUpload).where(ResumeUpload.file_key == file_key)
        )
        resume_upload = upload_row.scalar_one_or_none()

        if resume_upload is None:
            resume_upload = ResumeUpload(
                job_role_id=roles[item.job_role_title].id,
                file_key=file_key,
                original_name=f"{item.slug}.pdf",
                mime_type="application/pdf",
                file_size_bytes=245_000,
                status=UploadStatus.parsed,
            )
            session.add(resume_upload)
            await session.flush()

        candidate_row = await session.execute(
            select(Candidate).where(Candidate.resume_upload_id == resume_upload.id)
        )
        existing_candidate = candidate_row.scalar_one_or_none()
        if existing_candidate is not None:
            continue

        session.add(
            Candidate(
                resume_upload_id=resume_upload.id,
                raw_text=item.raw_text,
                profile_json=build_profile_json(item),
                summary_text=item.summary_text,
                total_exp_years=item.total_exp_years,
                is_low_confidence=False,
            )
        )


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        roles = await ensure_job_roles(session)
        await ensure_default_scoring_config(session, roles)
        await ensure_seed_candidates(session, roles)
        await session.commit()

    print("Seed data inserted successfully.")


if __name__ == "__main__":
    asyncio.run(seed())
