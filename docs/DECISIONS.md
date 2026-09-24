# Engineering decisions

## Begin with a deterministic baseline

A model call can hide extraction, retrieval, and grounding defects behind fluent language. The first public slice therefore runs locally and deterministically. It makes the evidence policy testable at zero variable cost and creates a baseline to compare with real embeddings and structured model extraction.

Tradeoff: the local hashed vector is not semantic enough for production and the heuristic extractor will miss complex prose. Those are visible limitations, not marketing claims.

## Keep provider boundaries narrow

The model adapter owns structured requirement extraction; the embedding adapter owns batches of vectors. Neither owns candidate truth or assessment policy. The default app never activates a provider merely because a key exists, preventing accidental cost or data transmission.

## Cite evidence objects, not generated prose

Assessments reference stable evidence IDs. The API returns the cited evidence objects separately, and tests assert that every positive ID resolves. Missing and human-confirmation states return no candidate citation.

## Use reciprocal-rank fusion

Lexical and vector signals have different score distributions. Reciprocal-rank fusion combines their ordered results without pretending those raw scores are directly comparable. A test failure exposed an early mistake: normalized RRF position was treated as relevance, which mislabeled unrelated GPU-research requirements as adjacent. The assessment policy now requires an actual normalized-skill overlap for the adjacent state.

## Use PostgreSQL as the evidence system of record

Evidence claims participate in durable relationships with profiles, source locators, future
resume versions, requirements, and assessments. PostgreSQL provides transactional integrity and
auditable identifiers for those relationships while JSONB preserves variable parser metadata.
Its full-text index and pgvector extension allow lexical and semantic retrieval to share the same
ownership and visibility filters.

Tradeoff: a database adds migrations, seeding, availability, and deployment work. RoleSignal
therefore keeps the deterministic fixture backend instead of requiring PostgreSQL for every demo.

## Make database activation configuration-driven and visible

`DATABASE_URL` selects the PostgreSQL backend. If it is absent, RoleSignal selects the local
fixture backend. If it is configured but a query fails, the wrapper logs the failure and uses the
deterministic fallback. `/v1/health` exposes the selected mode and database readiness so a fallback
cannot be mistaken for successful database retrieval.

The Vercel deployment currently has no `DATABASE_URL`; production therefore uses packaged
fixtures. A managed PostgreSQL instance, migrations, and seeding are prerequisites for changing
that behavior.

## Store no public résumé uploads in v1

The web contract accepts a preloaded profile ID, not arbitrary candidate content. This keeps the first public deployment honest and reduces privacy surface while retention, deletion, authorization, and abuse controls are unfinished.
