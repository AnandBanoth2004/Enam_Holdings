from pathlib import Path

from alembic.script import ScriptDirectory


MIGRATIONS_DIRECTORY = (
    Path(__file__).resolve().parents[1] / "backend" / "migrations"
)


def test_revision_ids_fit_alembic_version_column() -> None:
    revisions = tuple(ScriptDirectory(str(MIGRATIONS_DIRECTORY)).walk_revisions())
    oversized = [revision.revision for revision in revisions if len(revision.revision) > 32]

    assert not oversized, f"Alembic revision IDs exceed 32 characters: {oversized}"
