# RoleSignal

RoleSignal evaluates a job description against a citation-backed candidate evidence corpus. It distinguishes what is **supported**, **adjacent**, **missing**, or **unknown**, cites every positive conclusion, and refuses to turn a gap into a resume claim.

This repository is a public applied-AI engineering case study by Thomas Falcon. It combines a Next.js/TypeScript interface with a typed Python/FastAPI service, hybrid retrieval, structured contracts, automated evaluation, failure-aware UI, and provider adapters.

[Open the live demo](https://rolesignal-ten.vercel.app) · [Inspect the public project board](https://github.com/users/tjfalcon/projects/2)

## What works now

- Paste a job description and analyze a preloaded sanitized Thomas profile.
- Detect company, position, qualification, authorization, benefit, legal, and other source sections.
- Extract requirements with section provenance, information type, importance, and normalized skills.
- Exclude company marketing, ordinary benefits, EEO language, and privacy boilerplate from fit scoring.
- Route education, language, work authorization, schedule, compensation, and location constraints
  to explicit human confirmation instead of résumé-similarity matching.
- Retrieve candidate evidence through a configurable backend: PostgreSQL full-text search plus
  pgvector in local and hosted environments, or deterministic fixture retrieval when no database
  is configured.
- Create immutable sanitized résumé versions, review evidence, and atomically activate the version
  used for future comparisons through a token-protected administrator workspace.
- Render exact claim and source-locator citations for supported or adjacent assessments.
- Treat compensation and location as human-confirmation items.
- Return missing requirements without fabricated evidence.
- Report latency, estimated model cost, and evidence coverage.
- Validate API requests and responses with Pydantic.
- Run a 30-case retrieval set and grounding tests in CI.

The default is a **deterministic, zero-cost demo**. It does not call OpenAI and does not pretend that local hashing is a production embedding model. An OpenAI adapter is included behind a narrow interface for the upcoming live retrieval experiment; hosted model use remains disabled until it is integrated into the measured path.

## Measured baseline

| Check | Current result |
|---|---:|
| Golden retrieval cases | 30 |
| Recall@5 | 100% (30/30) |
| Automated tests | 32 passing with PostgreSQL enabled |
| Python coverage | 91% with PostgreSQL integration tests |
| Known fabricated candidate claims in tests | 0 |
| Hosted model calls in default demo | 0 |

This small, deliberately clear fixture set is a baseline—not a general-quality claim. PostgreSQL
full-text search and pgvector retrieval are implemented and integration-tested. The remaining
Week 2 work expands the evaluation set with hard negatives, conflicting evidence, irrelevant
retrieval, and paraphrase stress cases.

## Architecture

```mermaid
flowchart LR
  Browser[Next.js analysis + profile editor] --> API[FastAPI API]
  API --> Profiles[Active resume version]
  API --> Sections[Section detection + provenance]
  Sections --> Extract[Typed requirement extraction]
  Extract --> Select{DATABASE_URL configured?}
  Select -->|Yes| PG[(Neon or local PostgreSQL)]
  PG --> FTS[Full-text ranking]
  PG --> Vector[pgvector ranking]
  FTS --> Fuse[Reciprocal-rank fusion]
  Vector --> Fuse
  Select -->|No or unavailable| Fixture[Sanitized fixture corpus]
  Fixture --> Local[Local lexical + hashed-vector ranking]
  Local --> Fuse
  Fuse --> Assess[Grounded assessment policy]
  Assess --> Contract[Pydantic FitAnalysis]
  Contract --> Browser
```

Candidate profiles, immutable résumé versions, evidence, source locators, and deterministic test
embeddings are stored in PostgreSQL. Job submissions and completed analyses remain transient: the
API keeps only a bounded in-process analysis cache. There is still no public résumé-upload
endpoint. See [the full runtime and data-flow diagrams](docs/ARCHITECTURE.md).
See [section-aware ingestion](docs/SECTION_INGESTION.md) for the classification and exclusion
policy.

### Deployment modes

| Environment | Retrieval backend | Current behavior |
|---|---|---|
| Local with `DATABASE_URL` | PostgreSQL FTS + pgvector + RRF | Active and integration-tested |
| Local without `DATABASE_URL` | Repository fixtures + local hashed vectors | Deterministic fallback |
| Vercel production | Neon PostgreSQL FTS + pgvector + RRF | Active; migrations run before deployment |
| Vercel previews | Isolated Neon branch per Git branch | Active; migration runs before preview build |

The deployed application queries Neon through its pooled runtime URL. Alembic uses the direct
unpooled URL during Vercel builds. If a runtime database query fails, the public demo can fall back
to the packaged fixtures for the two known demo profiles; a legitimate empty or unknown profile
never silently receives another candidate's evidence.

## API contracts

- `POST /v1/analyze` — accepts `job_text` and `candidate_profile_id`; returns detected sections,
  provenance-backed requirements, assessments, evidence, limitations, and metrics.
- `GET /v1/analyses/{analysis_id}` — returns an analysis still present in the bounded demo cache.
- `GET /v1/health` — reports the real demo mode, storage state, and provider configuration.
- Token-protected profile routes create/list résumé versions, add or edit evidence, and activate a
  reviewed draft. Active and archived versions are immutable.
- Interactive OpenAPI docs are available at `/docs` while the API is running.

Core public models live in [`api/models.py`](api/models.py): `CandidateEvidence`, `JobRequirement`, `RequirementAssessment`, and `FitAnalysis`.

## Run locally

Requires Node.js 22+ and Python 3.12+.

```bash
npm ci
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
docker compose up -d postgres
export DATABASE_URL="postgresql+psycopg://rolesignal:rolesignal-local@localhost:5432/rolesignal"
export PROFILE_ADMIN_TOKEN="choose-a-local-development-secret"
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.seed_evidence
npm run dev
```

`npm run dev` starts both Next.js and FastAPI. Open the Next.js URL printed in the terminal; it
uses port 3000 when available and typically 3001 when the portfolio is already using 3000. The
API defaults to `http://localhost:8000`; set `NEXT_PUBLIC_API_URL` for another API origin.
Production uses the same-origin `/v1` contract, which rewrites to the Vercel
Python function under `/api/v1`.

## Verify

```bash
.venv/bin/ruff check .
.venv/bin/mypy api
.venv/bin/pytest --cov=api --cov-report=term-missing
npm run typecheck
npm run build
```

CI runs the TypeScript build and Python test/evaluation lanes independently.

## Privacy and truthfulness

- Public users cannot upload résumés in v1.
- Hosted profile mutations require `PROFILE_ADMIN_TOKEN`; if it is absent, they fail closed.
- The current editor is for sanitized public evidence only, not private documents.
- The demo corpus is sanitized and stored as public evidence.
- Submitted job text is processed in memory and is not intentionally persisted; the current bounded analysis cache resets with the process.
- The default demo makes no external model request.
- A positive assessment must include an evidence ID that resolves to a returned citation.
- “Adjacent” means transferable evidence, not proof of the complete requirement.
- Compensation, location, authorization, and current preferences are never inferred from technical evidence.

Do not add employer source code, private documents, private résumé data, or claims that cannot be tied to an inspectable source.

## Delivery roadmap

- **Week 1:** end-to-end deterministic RAG-shaped slice, typed API, public evidence profile, responsive result UI, CI baseline.
- **Week 2:** PostgreSQL/pgvector and full-text retrieval shipped; next add real embeddings,
  metadata-aware chunks, 50+ difficult evaluation cases, and a retrieval/grounding report.
- **Week 3:** structured logs, correlation IDs, provider timeouts/retries, rate limits, prompt-injection cases, cached demo analyses, browser tests.
- **Week 4:** deployed case study, architecture/data-flow/threat-model diagrams, accessibility and performance audit, demo video.

## License and data

Source licensing will be finalized before accepting external contributions. The candidate fixtures may be used to run this project but must not be presented as another person's experience.
