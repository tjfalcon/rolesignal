from sqlalchemy.dialects.postgresql import insert

from api.analyzer import load_fixture_corpus
from api.database import create_database_engine, database_url
from api.db_models import EvidenceRecord
from api.retrieval import local_embedding

PROFILES = ("demo-thomas", "synthetic")
VERSION_IDS = {"demo-thomas": "demo-thomas-v1", "synthetic": "synthetic-v1"}


def main() -> None:
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is required to seed evidence")
    engine = create_database_engine(url)
    rows: list[dict[str, object]] = []
    for profile_id in PROFILES:
        for evidence in load_fixture_corpus(profile_id):
            searchable_text = f"{evidence.claim} {' '.join(evidence.skill_tags)}"
            rows.append(
                {
                    "id": evidence.id,
                    "profile_id": profile_id,
                    "claim": evidence.claim,
                    "skill_tags": evidence.skill_tags,
                    "skill_text": " ".join(evidence.skill_tags),
                    "source": evidence.source,
                    "source_locator": evidence.source_locator,
                    "visibility": evidence.visibility,
                    "resume_version_id": VERSION_IDS[profile_id],
                    "approved": True,
                    "embedding": local_embedding(searchable_text),
                }
            )
    statement = insert(EvidenceRecord).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[EvidenceRecord.id, EvidenceRecord.profile_id],
        set_={
            "claim": statement.excluded.claim,
            "skill_tags": statement.excluded.skill_tags,
            "skill_text": statement.excluded.skill_text,
            "source": statement.excluded.source,
            "source_locator": statement.excluded.source_locator,
            "visibility": statement.excluded.visibility,
            "resume_version_id": statement.excluded.resume_version_id,
            "approved": statement.excluded.approved,
            "embedding": statement.excluded.embedding,
        },
    )
    with engine.begin() as connection:
        connection.execute(statement)
    print(f"Seeded {len(rows)} evidence records across {len(PROFILES)} profiles.")


if __name__ == "__main__":
    main()
