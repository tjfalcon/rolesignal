import os

from alembic import command
from alembic.config import Config

DEPLOYMENT_ENVIRONMENTS = {"preview", "production"}


def main() -> None:
    environment = os.getenv("VERCEL_ENV", "").strip().lower()
    if environment not in DEPLOYMENT_ENVIRONMENTS:
        print("Skipping deployment migration outside Vercel Preview or Production.")
        return

    unpooled_url = os.getenv("DATABASE_URL_UNPOOLED", "").strip()
    if not unpooled_url:
        raise RuntimeError(
            f"DATABASE_URL_UNPOOLED is required for the {environment} deployment migration"
        )

    # Alembic reads DATABASE_URL. Migrations use Neon's direct endpoint while the
    # deployed application continues to use the pooled DATABASE_URL.
    os.environ["DATABASE_URL"] = unpooled_url
    print(f"Applying database migrations for Vercel {environment}.")
    command.upgrade(Config("alembic.ini"), "head")


if __name__ == "__main__":
    main()
