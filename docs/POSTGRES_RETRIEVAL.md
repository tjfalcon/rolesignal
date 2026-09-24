# PostgreSQL retrieval slice

RoleSignal can use PostgreSQL as the system of record for citation-backed evidence.
PostgreSQL full-text search supplies the lexical ranking, pgvector supplies the semantic
ranking, and reciprocal-rank fusion combines the two without treating their raw scores as
directly comparable.

This path is active in local development when `DATABASE_URL` is set. The public Vercel deployment
does not currently use PostgreSQL because it has no managed database or `DATABASE_URL`; it uses
the deterministic fixture backend instead.

The original files belong in private object storage when uploads are introduced. PostgreSQL
stores source identity, versions, parsed sections, evidence claims, provenance, and embeddings.
Flexible parser output can use JSONB without weakening the foreign-key relationships that make
citations auditable.

## Run locally

Add the local database URL to `.env.local` without removing any existing provider settings:

```dotenv
DATABASE_URL=postgresql+psycopg://rolesignal:rolesignal-local@localhost:5432/rolesignal
```

Then initialize and run the stack:

```bash
docker compose up -d postgres
set -a; source .env.local; set +a
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.seed_evidence
npm run dev
```

With `DATABASE_URL` configured, `/v1/health` reports
`postgres-hybrid-with-local-fallback` and
`postgres-ready`. If PostgreSQL is temporarily unavailable, analysis visibly falls back to the
deterministic local fixture backend instead of fabricating or dropping citations.

## Production activation checklist

1. Provision managed PostgreSQL with pgvector support.
2. Add its encrypted `DATABASE_URL` to the appropriate Vercel environments.
3. Run `alembic upgrade head` against the managed database.
4. Run `python -m scripts.seed_evidence` against that database.
5. Confirm `/v1/health` reports `postgres-ready`.
6. Run the golden retrieval and citation-integrity suites against the hosted environment.
7. Keep public job-description submissions transient; do not enable resume uploads yet.

The local Docker URL must never be added to Vercel: from a serverless function, `localhost`
refers to that function's own runtime rather than the developer's PostgreSQL container.

The current 192-dimensional vectors are deterministic local test embeddings. Replacing them
with provider embeddings requires a new vector dimension migration and a full re-embedding job;
it must not mix incompatible embedding models in the same index.
