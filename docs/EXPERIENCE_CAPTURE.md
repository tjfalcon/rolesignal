# Experience capture

The manual form requires only experience text (10–2,000 characters). Paste one
resume excerpt, work story, or short code example per entry. File ingestion and
splitting full resumes into claims are outside this flow.

New entries use `Manual entry` as their source. The optional Reference field
maps to `source_locator` and accepts a document section, project name, or link.
An empty reference is stored as an empty string; no external citation is invented.
Editing existing entries preserves their original source. Version activation,
visibility, and evidence approval retain their existing behavior.

## Skill mentions

`api/skill_dictionary.json` is the shared, extensible dictionary used by the
browser, evidence creation API, and job requirement parser. Each canonical skill
has explicit aliases. Matching is case-insensitive and respects token boundaries,
including punctuation in names such as C++, C#, and Next.js. The dictionary is
curated, not exhaustive. It does not infer related technologies or proficiency.

The form displays detected skills and permits removal or manual additions.
Saving accepts the displayed set. No selected skills is a valid entry. Edits
preserve previously saved skill choices; newly mentioned technologies appear as
suggestions. Removed tags remain excluded for the current edit session.

“Prepared a Next.js app for deployment on Azure” detects both Next.js and Azure.
The user must remove Azure if it does not represent their own experience. A
future LLM can propose this distinction from context; keyword matching cannot.
The current analyzer still uses accepted tags in its deterministic fit heuristic.

## API compatibility

Existing evidence endpoints and response fields are unchanged. Creation now
allows omitted `source` (defaults to Manual entry), omitted `source_locator`
(defaults to empty), and omitted `skill_tags` (detects literal mentions).
An explicit empty tag list means no tags and must not trigger detection.
Updates preserve omitted fields and accept empty references and tag lists.
Claim-only updates preserve existing tags; the form submits its reviewed tags
alongside text changes. Search text and embeddings are rebuilt on claim/tag edits.
Existing stored evidence is not retagged. No database migration is required.
