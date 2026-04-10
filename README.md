# TalentForge: Smart Talent Selection Engine

TalentForge is an advanced, AI-powered resume parsing and candidate ranking platform designed to streamline the recruitment process. It leverages multi-stage extraction pipelines, vector-based semantic search, and deterministic scoring algorithms to provide highly accurate candidate matching and pedagogical justifications.

## 🚀 Core Features

- **Multi-Stage Resume Parsing**: Extracts structured data from PDF, DOCX, and images using Azure Document Intelligence and Google Gemini 2.0.
- **Hybrid Ranking Engine**: Combines semantic similarity (via pgvector) with weighted rule-based scoring (skills match, experience tenure, project quality).
- **AI-Driven Justification**: Automatically generates natural language explanations for candidate rankings using Llama 3.1 (via Groq).
- **Deterministic Experience Tracking**: Custom algorithms to calculate precise work history duration, correctly handling overlapping roles and career breaks.
- **Skill Normalization**: Canonicalizes extracted skills through a tiered mapping and LLM-fallback system.
- **Hyperlink & Portfolio Detection**: Automatically identifies and verifies GitHub repositories, LinkedIn profiles, and personal portfolio websites.
- **Real-time Processing**: Background task orchestration using Celery and Redis with live status updates in the UI.

## 🛠 Tech Stack & Models

### AI Models
- **Parsing (Structured Extraction)**: `gemini-2.0-flash` (Primary) — High-throughput, deep context understanding for complex resume layouts.
- **NER (Named Entity Recognition)**: `dslim/bert-base-NER` (via HuggingFace Inference API) — Pre-identifies names, organizations, and locations as ground-truth hints for the LLM.
- **AI Justification**: 
  - *Primary*: `gemini-2.0-flash` — Generates strict, 2-sentence candid fit justifications.
  - *Fallback*: `llama-3.1-8b-instant` (via Groq) — High-availability fallback.
- **Embeddings**: `text-embedding-3-small` (Azure OpenAI / OpenAI) — Generates 1536-dimensional semantic vectors.
- **OCR & Layout**: Azure AI Document Intelligence (`prebuilt-layout`) — Handles complex multi-column layouts and extracts embedded hyperlinks.

### Core Frameworks
- **Backend**: FastAPI (Python 3.11+), SQLAlchemy 2.0 (Async), Pydantic v2.
- **Infrastucture**: PostgreSQL (with `pgvector`), Redis (Caching & Job Queue), Celery (Distributed Tasks).
- **Frontend**: React 18, Vite, TypeScript, Tailwind CSS, Framer Motion.

## ⚙️ The TalentForge Pipeline

TalentForge operates as a stateful, asynchronous pipeline. Below is the journey of a resume from upload to ranked candidate:

### 1. Multi-Stage Parsing
When a resume is uploaded, it triggers a sophisticated background extraction process:
- **OCR & Structure**: Azure Document Intelligence converts files into structured markdown, preserving complex layouts and extracting "invisible" URLs behind clickable text.
- **Triangular Verification Extraction**:
  - **Regex**: Extracts authoritative contact data and bare-domain portfolios (e.g., `rahulmenon.dev`).
  - **HuggingFace NER**: BERT-based models identify structured entities (Names, Orgs, Locations) to guide the LLM.
  - **Gemini LLM**: Synthesizes all raw text and hints into a validated JSON schema, resolving ambiguities in work history and education.
- **Canonicalization**: Skills are normalized (e.g., "React.js" -> "React") and work durations are calculated using a deterministic interval-merge algorithm that correctly handles overlapping roles and career breaks.

### 2. Semantic Embedding
Parsed profiles are condensed into a **1536-dimensional semantic fingerprint**. This representation captures the *intent* of the candidate's professional background, allowing the engine to match concepts and experience levels rather than simple keyword overlap.

### 3. Hybrid Ranking Engine
Ranking is executed via high-performance SQL using `pgvector`. The final score is a weighted blend:
- **Semantic Score (40%)**: Derived from cosine similarity between the Job Description and Candidate vectors.
- **Rule-Based Score (60%)**: A deterministic evaluation of:
  - **Mandatory/Preferred Skills**: Precise percentage overlap.
  - **Experience Tenure**: Weighted against minimum year requirements.
  - **Project Relevance**: Technical alignment of recent projects with the target role.

### 4. AI Justification
For the top 5 candidates, an "analyst" agent (Gemini 2.0) generates exactly **two grounded sentences** explaining the fit. This output is strictly constrained to be factual and candid, acknowledging professional gaps as clearly as strengths, providing recruiters with immediate, actionable insights.

## 🏗 Project Structure

```text
.
├── backend/            # FastAPI source code
│   ├── app/
│   │   ├── api/        # REST endpoints (v1)
│   │   ├── core/       # Config and security
│   │   ├── models/      # SQLAlchemy database models
│   │   ├── services/    # Business logic (Parsing, Ranking, Scoring)
│   │   └── workers/     # Celery tasks and app definition
├── frontend/           # React source code
│   ├── src/
│   │   ├── components/  # Reusable UI components
│   │   ├── pages/       # Page-level components
│   │   └── lib/         # API clients and utilities
├── docker-compose.yml  # Local orchestration
└── .env.example        # Environment variable template
```

## 🚦 Getting Started

### Prerequisites
- Docker & Docker Compose
- API Keys for required services (Gemini, Groq, Azure, Supabase)

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd smart-talent-selection
   ```

2. **Configure Environment Variables**:
   Copy the example env file and fill in your credentials:
   ```bash
   cp .env.example .env
   ```
   *Note: Ensure `GEMINI_API_KEY`, `GROQ_API_KEY`, and `AZURE_DI_*` variables are set correctly.*

3. **Spin up the infrastructure**:
   ```bash
   docker compose up --build
   ```

4. **Access the application**:
   - **Frontend**: [http://localhost:3000](http://localhost:3000)
   - **Backend API**: [http://localhost:8000/api/v1](http://localhost:8000/api/v1)
   - **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)


## 📄 License
This project is licensed under the MIT License - see the LICENSE file for details.
