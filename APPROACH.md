# Smart Talent Selection Engine — Approach Document

## 1. Problem Statement

Traditional resume screening is manual, inconsistent, and scales poorly. Recruiters spend ~23 hours per hire on screening alone, often relying on keyword matching that misses qualified candidates with different terminology. We needed a system that could parse unstructured resumes with near-human accuracy, rank candidates against job descriptions using both semantic understanding and hard requirements, and explain its decisions transparently.

## 2. Solution Architecture

The system is a four-stage asynchronous pipeline, each stage designed to maximise accuracy while remaining fault-tolerant:

```
Resume Upload → [Celery Worker] → OCR → NER + Regex → LLM Extraction → Embedding → DB
                                                                                    ↓
                         Frontend ← API ← Hybrid Ranking (pgvector SQL) ← Job Description
                                          ↓
                                   AI Justification (async, top-5)
```

**Stage 1 — Parsing (Multi-model triangulation):** Azure Document Intelligence handles OCR and hyperlink extraction. In parallel, a HuggingFace BERT model (`dslim/bert-base-NER`) identifies entities and a regex engine extracts verified contact data. These are injected as "ground truth hints" into `gemini-2.0-flash`, which synthesises everything into a validated JSON profile. This triangulation approach eliminates single-model hallucination risk.

**Stage 2 — Canonicalization:** Deterministic post-processing normalises skills (alias map + LLM fallback), merges overlapping work intervals for precise experience calculation, and resolves certification issuers via keyword lookup. No LLM is used here — these are business-critical calculations that must be reproducible.

**Stage 3 — Ranking:** A single SQL query uses `pgvector` cosine similarity (semantic) blended with rule-based scoring (skills, experience, projects, certifications) at a 40/60 weight split. Weights are configurable per job role via a scoring config table.

**Stage 4 — Justification:** For the top 5 candidates, Gemini 2.0 Flash generates exactly two grounded sentences explaining fit quality. A Groq-hosted Llama 3.1 fallback guarantees availability during rate-limiting.

## 3. Tech Stack & Justification

| Layer | Choice | Why |
|-------|--------|-----|
| **API** | FastAPI + Pydantic v2 | Native async, automatic OpenAPI docs, and Pydantic's validation ensures type safety at the boundary layer. |
| **Database** | PostgreSQL + pgvector | pgvector enables semantic search *inside* the ranking SQL — no external vector DB needed, reducing infrastructure complexity and keeping data co-located with relational metadata. |
| **Task Queue** | Celery + Redis | Resume parsing takes 15-40s per file. Celery decouples this from the request cycle, and Redis doubles as both broker and a caching layer for justification results. |
| **OCR** | Azure Document Intelligence | Superior handling of multi-column layouts, tables, and embedded hyperlinks compared to open-source alternatives (Tesseract, PyMuPDF alone). The `prebuilt-layout` model preserves document structure that pure text extraction loses. |
| **NER** | HuggingFace (`bert-base-NER`) | Lightweight, serverless inference via the HF API. Provides entity hints without adding model-hosting overhead. Gracefully degrades — if HF is unavailable, the LLM step still functions. |
| **LLM (Parsing)** | Gemini 2.0 Flash | Best-in-class cost/performance ratio for structured JSON extraction. Handles 1M+ token context windows, allowing full resumes without chunking. |
| **LLM (Justification)** | Gemini 2.0 Flash + Groq Llama 3.1 fallback | Dual-model strategy ensures 100% uptime. Groq's inference speed (~200ms) makes it an ideal fallback. |
| **Embeddings** | Azure OpenAI `text-embedding-3-small` | 1536 dimensions provides a strong balance between semantic resolution and storage/compute cost. Azure hosting ensures low-latency from our infrastructure. |
| **Frontend** | React + Vite + TypeScript | Vite's HMR enables rapid iteration. TypeScript catches API contract mismatches at compile time. Framer Motion provides polished micro-animations without bundle bloat. |
| **Storage** | Supabase (S3-compatible) | Managed object storage with presigned URLs for secure resume downloads without proxying through the API. |

## 4. Key Design Decisions

- **LLM for understanding, deterministic code for business logic.** Experience calculation, skill normalisation, and score computation are *never* delegated to an LLM. This ensures reproducibility and auditability.
- **Triangular extraction over single-model parsing.** Three independent extraction methods (Regex, NER, LLM) cross-validate each other, dramatically reducing hallucination in contact details and URLs.
- **In-database ranking over application-layer scoring.** The entire ranking algorithm runs as a single SQL CTE, eliminating N+1 queries and enabling sub-100ms ranking for hundreds of candidates.

## 5. What We'd Improve With More Time

- **Fine-tuned embedding model**: Train a domain-specific embedding model on resume-JD pairs to improve semantic matching beyond the general-purpose `text-embedding-3-small`.
- **Agentic parsing pipeline**: Replace the fixed pipeline with an LLM agent that can iteratively refine extraction — re-querying specific resume sections when confidence is low.
- **Candidate deduplication**: Implement fuzzy matching on (name + email + phone) to detect re-uploaded or updated resumes across job roles.


