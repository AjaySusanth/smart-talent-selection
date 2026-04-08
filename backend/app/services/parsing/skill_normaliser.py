"""
Skill normalisation (Task 3.5).

Pipeline:
  1. Deterministic alias map: fast canonicalisation for common variants.
  2. LLM fallback (Groq Llama 3.3 70B): resolve uncaptured skills and assign category.

The public entrypoint is `normalise_skills`.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

import structlog
from groq import Groq

from app.core.config import settings
from app.schemas.candidate_profile import NormalisedSkill

logger = structlog.get_logger(__name__)

_ALLOWED_CATEGORIES = {
    "language",
    "framework",
    "database",
    "tool",
    "cloud",
    "soft_skill",
}

_MODEL_NAME = "llama-3.3-70b-versatile"


# Canonical name lookup for common variants. Expand safely over time as needed.
SKILL_ALIASES: dict[str, str] = {
    "ai": "Artificial Intelligence",
    "android": "Android",
    "angular": "Angular",
    "angularjs": "Angular",
    "ansible": "Ansible",
    "apacheairflow": "Apache Airflow",
    "apachekafka": "Apache Kafka",
    "apachemaven": "Maven",
    "arangodb": "ArangoDB",
    "aspnet": "ASP.NET",
    "aspnetcore": "ASP.NET Core",
    "aws": "AWS",
    "awss3": "Amazon S3",
    "awslambda": "AWS Lambda",
    "awsec2": "Amazon EC2",
    "awscdk": "AWS CDK",
    "azure": "Azure",
    "azuredevops": "Azure DevOps",
    "azuresql": "Azure SQL",
    "babel": "Babel",
    "bash": "Bash",
    "bigquery": "BigQuery",
    "bitbucket": "Bitbucket",
    "blazor": "Blazor",
    "bootstrap": "Bootstrap",
    "c": "C",
    "csharp": "C#",
    "cplusplus": "C++",
    "canva": "Canva",
    "cassandra": "Cassandra",
    "chatgpt": "ChatGPT",
    "ci": "CI/CD",
    "cd": "CI/CD",
    "cicd": "CI/CD",
    "clickhouse": "ClickHouse",
    "communication": "Communication",
    "cpp": "C++",
    "css": "CSS",
    "css3": "CSS",
    "databricks": "Databricks",
    "dataanalysis": "Data Analysis",
    "datascience": "Data Science",
    "deep learning": "Deep Learning",
    "deep-learning": "Deep Learning",
    "deep_learning": "Deep Learning",
    "django": "Django",
    "django rest framework": "Django REST Framework",
    "django-rest-framework": "Django REST Framework",
    "docker": "Docker",
    "dynamodb": "DynamoDB",
    "elasticsearch": "Elasticsearch",
    "elastic search": "Elasticsearch",
    "excel": "Microsoft Excel",
    "express": "Express.js",
    "expressjs": "Express.js",
    "fastapi": "FastAPI",
    "figma": "Figma",
    "firebase": "Firebase",
    "flask": "Flask",
    "flutter": "Flutter",
    "gcp": "Google Cloud",
    "gcpcloud": "Google Cloud",
    "gcloud": "Google Cloud",
    "git": "Git",
    "github": "GitHub",
    "githubactions": "GitHub Actions",
    "gitlab": "GitLab",
    "gitlabci": "GitLab CI",
    "golang": "Go",
    "googlecloud": "Google Cloud",
    "graphql": "GraphQL",
    "graphqlapi": "GraphQL",
    "groovy": "Groovy",
    "hadoop": "Hadoop",
    "hive": "Hive",
    "html": "HTML",
    "html5": "HTML",
    "http": "HTTP",
    "huggingface": "Hugging Face",
    "java": "Java",
    "javascript": "JavaScript",
    "jest": "Jest",
    "jira": "Jira",
    "jquery": "jQuery",
    "js": "JavaScript",
    "json": "JSON",
    "jupyter": "Jupyter",
    "k8": "Kubernetes",
    "k8s": "Kubernetes",
    "kafka": "Kafka",
    "kanban": "Kanban",
    "keras": "Keras",
    "kotlin": "Kotlin",
    "kubernates": "Kubernetes",
    "kubernetes": "Kubernetes",
    "langchain": "LangChain",
    "leadership": "Leadership",
    "linux": "Linux",
    "llm": "LLM",
    "llms": "LLM",
    "machine learning": "Machine Learning",
    "machine-learning": "Machine Learning",
    "machine_learning": "Machine Learning",
    "matlab": "MATLAB",
    "maven": "Maven",
    "metabase": "Metabase",
    "microservices": "Microservices",
    "ml": "Machine Learning",
    "mongodb": "MongoDB",
    "mongo": "MongoDB",
    "ms excel": "Microsoft Excel",
    "mysql": "MySQL",
    "natural language processing": "NLP",
    "nestjs": "NestJS",
    "next": "Next.js",
    "nextjs": "Next.js",
    "node": "Node.js",
    "nodejs": "Node.js",
    "node js": "Node.js",
    "node.js": "Node.js",
    "nosql": "NoSQL",
    "nlp": "NLP",
    "numpy": "NumPy",
    "objectivec": "Objective-C",
    "oop": "OOP",
    "oracle": "Oracle",
    "pandas": "Pandas",
    "php": "PHP",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "postman": "Postman",
    "power bi": "Power BI",
    "powerbi": "Power BI",
    "problem solving": "Problem Solving",
    "problem-solving": "Problem Solving",
    "project management": "Project Management",
    "prompt engineering": "Prompt Engineering",
    "python": "Python",
    "pytorch": "PyTorch",
    "react": "React",
    "reactjs": "React",
    "react js": "React",
    "react.js": "React",
    "redis": "Redis",
    "rest": "REST",
    "restapi": "REST API",
    "restfulapi": "REST API",
    "ruby": "Ruby",
    "rust": "Rust",
    "salesforce": "Salesforce",
    "scikitlearn": "Scikit-learn",
    "scikit learn": "Scikit-learn",
    "seo": "SEO",
    "shell": "Shell Scripting",
    "snowflake": "Snowflake",
    "soft skills": "Soft Skills",
    "spark": "Apache Spark",
    "sql": "SQL",
    "sqlite": "SQLite",
    "spring": "Spring",
    "springboot": "Spring Boot",
    "spring boot": "Spring Boot",
    "sprint": "Agile",
    "svelte": "Svelte",
    "swift": "Swift",
    "tableau": "Tableau",
    "tailwind": "Tailwind CSS",
    "tailwindcss": "Tailwind CSS",
    "team work": "Teamwork",
    "teamwork": "Teamwork",
    "tensorflow": "TensorFlow",
    "terraform": "Terraform",
    "testing": "Testing",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "ubuntu": "Ubuntu",
    "uiux": "UI/UX Design",
    "vercel": "Vercel",
    "vite": "Vite",
    "vue": "Vue.js",
    "vuejs": "Vue.js",
    "web development": "Web Development",
    "windows": "Windows",
    "word": "Microsoft Word",
}

SKILL_CATEGORIES: dict[str, str] = {
    "Agile": "tool",
    "Amazon EC2": "cloud",
    "Amazon S3": "cloud",
    "Android": "framework",
    "Angular": "framework",
    "Ansible": "tool",
    "Apache Airflow": "tool",
    "Apache Kafka": "tool",
    "Apache Spark": "tool",
    "ArangoDB": "database",
    "Artificial Intelligence": "tool",
    "ASP.NET": "framework",
    "ASP.NET Core": "framework",
    "AWS": "cloud",
    "AWS CDK": "cloud",
    "AWS Lambda": "cloud",
    "Azure": "cloud",
    "Azure DevOps": "tool",
    "Azure SQL": "database",
    "Bash": "language",
    "BigQuery": "database",
    "Bitbucket": "tool",
    "Blazor": "framework",
    "Bootstrap": "framework",
    "C": "language",
    "C#": "language",
    "C++": "language",
    "Canva": "tool",
    "Cassandra": "database",
    "ChatGPT": "tool",
    "CI/CD": "tool",
    "ClickHouse": "database",
    "Communication": "soft_skill",
    "CSS": "language",
    "Data Analysis": "tool",
    "Data Science": "tool",
    "Databricks": "tool",
    "Deep Learning": "tool",
    "Django": "framework",
    "Django REST Framework": "framework",
    "Docker": "tool",
    "DynamoDB": "database",
    "Elasticsearch": "database",
    "Express.js": "framework",
    "FastAPI": "framework",
    "Figma": "tool",
    "Firebase": "cloud",
    "Flask": "framework",
    "Flutter": "framework",
    "Git": "tool",
    "GitHub": "tool",
    "GitHub Actions": "tool",
    "GitLab": "tool",
    "GitLab CI": "tool",
    "Go": "language",
    "Google Cloud": "cloud",
    "GraphQL": "tool",
    "Groovy": "language",
    "Hadoop": "tool",
    "Hive": "database",
    "HTML": "language",
    "HTTP": "tool",
    "Hugging Face": "tool",
    "Java": "language",
    "JavaScript": "language",
    "Jest": "tool",
    "Jira": "tool",
    "JSON": "tool",
    "jQuery": "framework",
    "Jupyter": "tool",
    "Kafka": "tool",
    "Kanban": "tool",
    "Keras": "framework",
    "Kotlin": "language",
    "Kubernetes": "cloud",
    "LangChain": "tool",
    "Leadership": "soft_skill",
    "Linux": "tool",
    "LLM": "tool",
    "Machine Learning": "tool",
    "MATLAB": "language",
    "Maven": "tool",
    "Metabase": "tool",
    "Microservices": "tool",
    "Microsoft Excel": "tool",
    "Microsoft Word": "tool",
    "MongoDB": "database",
    "MySQL": "database",
    "NestJS": "framework",
    "Next.js": "framework",
    "NLP": "tool",
    "Node.js": "language",
    "NoSQL": "database",
    "NumPy": "tool",
    "Objective-C": "language",
    "OOP": "tool",
    "Oracle": "database",
    "Pandas": "tool",
    "PHP": "language",
    "PostgreSQL": "database",
    "Postman": "tool",
    "Power BI": "tool",
    "Problem Solving": "soft_skill",
    "Project Management": "soft_skill",
    "Prompt Engineering": "tool",
    "PyTorch": "framework",
    "Python": "language",
    "React": "framework",
    "Redis": "database",
    "REST": "tool",
    "REST API": "tool",
    "Ruby": "language",
    "Rust": "language",
    "Salesforce": "cloud",
    "Scikit-learn": "framework",
    "SEO": "tool",
    "Shell Scripting": "language",
    "Snowflake": "database",
    "Soft Skills": "soft_skill",
    "SQL": "database",
    "SQLite": "database",
    "Spring": "framework",
    "Spring Boot": "framework",
    "Svelte": "framework",
    "Swift": "language",
    "Tableau": "tool",
    "Tailwind CSS": "framework",
    "Teamwork": "soft_skill",
    "TensorFlow": "framework",
    "Terraform": "tool",
    "Testing": "tool",
    "TypeScript": "language",
    "UI/UX Design": "tool",
    "Ubuntu": "tool",
    "Vercel": "cloud",
    "Vite": "tool",
    "Vue.js": "framework",
    "Web Development": "tool",
    "Windows": "tool",
}


@lru_cache(maxsize=1)
def _client() -> Groq:
    return Groq(api_key=settings.groq_api_key)


def _alias_key(skill: str) -> str:
    cleaned = skill.strip().lower()
    cleaned = re.sub(r"[\u2018\u2019\u201c\u201d]", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9+#.\-\s]", "", cleaned)
    cleaned = cleaned.replace("/", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Lookup key is punctuation-insensitive for common variants.
    flattened = re.sub(r"[^a-z0-9+#]", "", cleaned)
    return flattened or cleaned


def _clean_for_display(skill: str) -> str:
    value = re.sub(r"\s+", " ", skill.strip())
    if not value:
        return ""
    if value.isupper() and len(value) <= 5:
        return value
    return value.title()


def _category_for(name: str, proposed: str | None = None) -> str:
    if name in SKILL_CATEGORIES:
        return SKILL_CATEGORIES[name]

    if proposed:
        normalised = proposed.strip().lower()
        if normalised in _ALLOWED_CATEGORIES:
            return normalised

    return "tool"


def _dedupe(skills: list[NormalisedSkill]) -> list[NormalisedSkill]:
    seen: set[str] = set()
    result: list[NormalisedSkill] = []
    for skill in skills:
        key = _alias_key(skill.name)
        if key in seen:
            continue
        seen.add(key)
        result.append(skill)
    return result


def _normalise_deterministic(
    skills: list[str],
) -> tuple[list[NormalisedSkill], list[str]]:
    resolved: list[NormalisedSkill] = []
    unresolved: list[str] = []

    for raw in skills:
        if not raw or not raw.strip():
            continue

        raw_clean = re.sub(r"\s+", " ", raw.strip())
        key = _alias_key(raw_clean)
        canonical = SKILL_ALIASES.get(key)

        if canonical is None:
            unresolved.append(raw_clean)
            continue

        resolved.append(
            NormalisedSkill(
                name=canonical,
                category=_category_for(canonical),
            )
        )

    return _dedupe(resolved), unresolved


def _parse_llm_payload(text: str) -> list[dict[str, str]]:
    payload = json.loads(text)

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        if isinstance(payload.get("skills"), list):
            return [item for item in payload["skills"] if isinstance(item, dict)]
        if isinstance(payload.get("normalised_skills"), list):
            return [
                item for item in payload["normalised_skills"] if isinstance(item, dict)
            ]

    return []


def _normalise_with_llm(unresolved: list[str]) -> list[NormalisedSkill]:
    if not unresolved:
        return []

    prompt = (
        "You normalise resume skill strings. "
        "Return ONLY JSON as an array of objects with shape "
        '{"name": "Canonical Skill", "category": "language|framework|database|tool|cloud|soft_skill"}. '
        "Rules: deduplicate semantically equivalent entries, keep canonical industry names, "
        "do not add skills that are not present in input, and keep output concise.\n\n"
        f"Input skills:\n{json.dumps(unresolved, ensure_ascii=True)}"
    )

    response = _client().chat.completions.create(
        model=_MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "You are a strict JSON skill normaliser.",
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=900,
    )

    content = response.choices[0].message.content if response.choices else None
    if not content:
        raise ValueError("Groq returned an empty skill-normalisation response")

    parsed = _parse_llm_payload(content)
    output: list[NormalisedSkill] = []

    for item in parsed:
        raw_name = str(item.get("name", "")).strip()
        if not raw_name:
            continue

        canonical = SKILL_ALIASES.get(_alias_key(raw_name), raw_name)
        category = _category_for(canonical, str(item.get("category", "")))
        output.append(NormalisedSkill(name=canonical, category=category))

    return _dedupe(output)


def normalise_skills(raw_skills: list[str]) -> list[NormalisedSkill]:
    """Normalise raw skills into canonical, deduplicated, categorised entries."""
    deterministic_resolved, unresolved = _normalise_deterministic(raw_skills)

    llm_resolved: list[NormalisedSkill] = []
    if unresolved:
        try:
            llm_resolved = _normalise_with_llm(unresolved)
        except Exception as exc:
            logger.warning(
                "skill_normalisation_llm_failed",
                unresolved_count=len(unresolved),
                exc=str(exc),
            )
            # Graceful fallback so parsing pipeline still completes.
            llm_resolved = [
                NormalisedSkill(name=_clean_for_display(skill), category="tool")
                for skill in unresolved
                if _clean_for_display(skill)
            ]

    final = _dedupe([*deterministic_resolved, *llm_resolved])

    logger.info(
        "skill_normalisation_finished",
        raw_count=len(raw_skills),
        deterministic_resolved=len(deterministic_resolved),
        llm_resolved=len(llm_resolved),
        final_count=len(final),
        unresolved_count=max(len(unresolved) - len(llm_resolved), 0),
    )

    return final
