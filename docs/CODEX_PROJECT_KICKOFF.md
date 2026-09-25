# RoleSignal: Separate Codex Project Kickoff

Use this document to start a dedicated Codex project or task for RoleSignal. The repository and its
checked-in documentation are the source of truth; this prompt does not depend on any earlier chat.

## Initial prompt

```text
Work with me on RoleSignal in /Users/thomasfalcon/Dev/rolesignal.

RoleSignal is a public portfolio project that compares a job posting with a citation-backed
candidate evidence profile. Its purpose is to demonstrate senior full-stack engineering plus
reliable applied-AI delivery: Python/FastAPI, TypeScript/Next.js, PostgreSQL/pgvector, retrieval,
structured model outputs, evaluations, observability, and safe failure behavior.

Begin by reading README.md and every file directly linked from it under docs/. Inspect the current
branch, git status, recent history, open pull requests, CI, and the deployed health endpoint before
making changes. Preserve existing user work and never commit secrets, private resumes, proprietary
employer code, or unsupported career claims.

Current architecture:
- Next.js/TypeScript frontend and Python/FastAPI backend.
- Neon PostgreSQL in Vercel; local PostgreSQL through Docker Compose.
- Alembic migrations use the unpooled administrative URL; runtime queries use the pooled URL.
- PostgreSQL full-text search, pgvector, and reciprocal-rank fusion are implemented.
- Candidate profiles use immutable resume versions. Only approved public evidence in the active
  version may support an analysis.
- The hosted default remains deterministic and makes no model call until model-backed behavior is
  evaluated and deliberately enabled.
- Vercel routes the public /v1 tree to the single api/index.py FastAPI entrypoint through
  vercel.json. Do not create per-route Python functions under api/.

Working style:
- Make controlled, reviewable increments with one feature in progress at a time.
- Explain important decisions so I learn the Python, retrieval, evaluation, and operational ideas.
- Run proportionate tests, type checks, linting, builds, database migrations, and preview checks.
- Use pull requests and verify preview behavior before merging deployment-sensitive work.
- Treat grounding and evaluations as product behavior, not optional polish.
- Positive or adjacent career assessments must resolve to returned evidence citations.
- Fail closed for private/profile administration and fail clearly when evidence is unavailable.
- Keep public submissions transient until real authentication, retention controls, and private
  storage are designed.

First, report the verified current state and select the smallest next milestone from this order:
1. Configure and verify PROFILE_ADMIN_TOKEN in Preview and Production if it is still absent.
2. Add model-assisted structured requirement extraction behind the existing provider boundary,
   retaining the deterministic path as a baseline and fallback.
3. Add real embeddings as a measured retrieval experiment, not as an assumed improvement.
4. Expand the golden set to at least 50 difficult cases: hard negatives, paraphrases, conflicts,
   irrelevant evidence, prompt injection, and insufficient-evidence cases.
5. Publish a deterministic-versus-model-assisted evaluation report with quality, grounding,
   latency, and estimated-cost comparisons.
6. Add request correlation, structured logs, timeouts, retry boundaries, rate limiting, graceful
   degradation, and end-to-end browser tests.

Do not start private resume uploads or general multi-user authentication unless I explicitly move
them ahead of the reliability milestones. Before coding, propose one bounded increment with its
acceptance criteria; then implement it autonomously unless a secret or product decision requires
my input. If blocked, give me exact manual steps without requesting that I paste a secret into chat.
```

## Verified handoff state (2026-09-25)

- Production: <https://rolesignal-ten.vercel.app>
- Repository: <https://github.com/tjfalcon/rolesignal>
- Production health reports PostgreSQL ready.
- Public deterministic analysis works against the active Neon-backed evidence version.
- Nested FastAPI routing is verified in preview and production.
- Profile administration deliberately returns `503` until `PROFILE_ADMIN_TOKEN` is configured.
- CI covers the frontend build, Python tests/evaluations, migrations, PostgreSQL retrieval, and the
  resume-version lifecycle.
- The latest completed work is represented by pull requests 13 through 16.

## Manual setup that must remain outside source control

Generate and retain an administrator token locally, add it as the sensitive
`PROFILE_ADMIN_TOKEN` environment variable for Vercel Preview and Production, and redeploy. Never
put the value in this document, an issue, a commit, or a chat transcript.

Model-backed work will separately require an API key in local and hosted secret storage. Enabling a
key is not, by itself, permission to make an unbounded number of calls; evaluation commands and
hosted model modes must keep explicit cost limits.

## Completion target for the dedicated project

RoleSignal is portfolio-ready when a reviewer can verify, in under ten minutes, the live product,
Python API design, hybrid retrieval, versioned evidence model, citations, evaluation results,
failure handling, operational telemetry, CI, architecture decisions, and the precise boundary
between deterministic and model-assisted behavior.
