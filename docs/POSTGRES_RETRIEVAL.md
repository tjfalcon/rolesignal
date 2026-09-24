# PostgreSQL retrieval slice

RoleSignal uses PostgreSQL as the system of record for versioned, citation-backed evidence.
PostgreSQL full-text search supplies the lexical ranking, pgvector supplies the semantic
ranking, and reciprocal-rank fusion combines the two without treating their raw scores as
directly comparable.

The original files belong in private object storage when uploads are introduced. PostgreSQL
stores source identity, versions, parsed sections, evidence claims, provenance, and embeddings.
Flexible parser output can use JSONB without weakening the foreign-key relationships that make
citations auditable.

## Run locally

```bash
cp .env.example .env.local
docker compose up -d postgres
set -a; source .env.local; set +a
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.seed_evidence
npm run dev
```

With `DATABASE_URL` configured, `/v1/health` reports `postgres-hybrid` and
`postgres-ready`. If PostgreSQL is temporarily unavailable, analysis visibly falls back to the
deterministic local fixture backend instead of fabricating or dropping citations.

The current 192-dimensional vectors are deterministic local test embeddings. Replacing them
with provider embeddings requires a new vector dimension migration and a full re-embedding job;
it must not mix incompatible embedding models in the same index.
