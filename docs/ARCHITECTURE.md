# RoleSignal architecture

RoleSignal separates evidence truth, retrieval, and assessment policy. A retrieval backend may
change how candidate evidence is ranked, but it cannot create candidate claims or convert missing
experience into a positive assessment.

## Runtime selection

```mermaid
flowchart TD
  Start[FastAPI process starts] --> Config{DATABASE_URL present?}
  Config -->|No| Local[LocalRetrievalBackend]
  Config -->|Yes| Primary[PostgresRetrievalBackend]
  Primary --> Wrapped[FallbackRetrievalBackend]
  Wrapped --> Check{PostgreSQL query succeeds?}
  Check -->|Yes| DatabasePath[PostgreSQL retrieval]
  Check -->|No| Local
  DatabasePath --> Response[Grounded FitAnalysis]
  Local --> Response
```

The fallback is explicit in `/v1/health`. With a configured and reachable database, the response
reports `postgres-hybrid-with-local-fallback` and `postgres-ready`. Without `DATABASE_URL`, it
reports `deterministic` and `in-memory-demo`.

## Analysis and retrieval flow

```mermaid
sequenceDiagram
  actor User
  participant Web as Next.js
  participant API as FastAPI
  participant Extract as Requirement extractor
  participant Retrieve as Retrieval backend
  participant DB as PostgreSQL and pgvector
  participant Policy as Assessment policy

  User->>Web: Paste job description
  Web->>API: POST /v1/analyze
  API->>Extract: Detect sections and extract typed requirements with provenance
  loop Each assessable requirement
    Extract->>Retrieve: Search requirement and profile
    alt PostgreSQL configured and ready
      Retrieve->>DB: Full-text ranking
      Retrieve->>DB: Vector cosine ranking
      DB-->>Retrieve: Ranked evidence lists
      Retrieve->>Retrieve: Reciprocal-rank fusion
    else No database or query unavailable
      Retrieve->>Retrieve: Local lexical and hashed-vector ranking
    end
    Retrieve->>Policy: Candidate evidence with stable IDs
    Policy->>Policy: supported, adjacent, missing, or unknown
  end
  Policy-->>API: Assessments and citation IDs
  API-->>Web: Validated FitAnalysis
  Web-->>User: Results, citations, gaps, and limitations
```

## Current evidence data model

```mermaid
erDiagram
  CANDIDATE_PROFILE ||--o{ CANDIDATE_EVIDENCE : owns
  CANDIDATE_PROFILE {
    string id PK
  }
  CANDIDATE_EVIDENCE {
    string profile_id PK
    string id PK
    text claim
    jsonb skill_tags
    text skill_text
    text source
    text source_locator
    string visibility
    vector embedding
    tsvector search_vector
    timestamp created_at
    timestamp updated_at
  }
```

`CANDIDATE_PROFILE` is currently represented by the stable `profile_id`; it is not yet a separate
table because v1 exposes only two preloaded profiles. Resume upload and versioning will introduce
candidate, source-document, document-version, section, and evidence-provenance tables before
private user content is accepted.

## Storage boundaries

| Information | Current storage | Retention |
|---|---|---|
| Sanitized candidate fixtures | Repository JSON; optionally seeded into PostgreSQL | Versioned with the repository |
| Candidate evidence and embeddings | Local PostgreSQL when configured | Persistent Docker volume |
| Submitted job description | FastAPI process memory | Request processing only |
| Completed analysis | Bounded process-local cache | Until eviction or process restart |
| Original resume files | Not accepted | None |
| Hosted model input/output | Hosted model calls disabled | None |

## Deployment topology

```mermaid
flowchart LR
  subgraph Local[Local development]
    LocalWeb[Next.js on 3000 or 3001]
    LocalAPI[FastAPI on 8000]
    LocalDB[(PostgreSQL 17 + pgvector on 5432)]
    LocalWeb --> LocalAPI
    LocalAPI --> LocalDB
  end

  subgraph Production[Vercel production today]
    VercelWeb[Next.js deployment]
    VercelAPI[Python function]
    Fixtures[(Packaged sanitized fixtures)]
    VercelWeb -->|same-origin /v1| VercelAPI
    VercelAPI --> Fixtures
  end

  FutureDB[(Managed PostgreSQL + pgvector)]
  VercelAPI -. after DATABASE_URL, migration, and seed .-> FutureDB
```

Production does not currently use the local Docker database and cannot connect to `localhost` on
the developer machine. Activating PostgreSQL in production requires a managed database reachable
from Vercel, a production `DATABASE_URL`, migration execution, fixture seeding, and a successful
health check.
