import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from freyja_backend.db.models.context_snapshot import ContextSnapshotRow

# Queries for context snapshots (POINT2-SNAPSHOT-001). A snapshot is only ever inserted: the
# database itself rejects UPDATE (migration 0015), so this module has no update path at all.


def insert_if_absent(session: Session, values: dict[str, object]) -> bool:
    """Store the snapshot unless the very same content is already stored.

    Returns True if a row was inserted. An identical observation, judged by the same policy,
    is one snapshot: the stored row is left exactly as it is, never overwritten.
    """
    result = session.execute(
        pg_insert(ContextSnapshotRow)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["content_hash"])
        .returning(ContextSnapshotRow.id)
    )
    return result.first() is not None


def get_by_id(session: Session, snapshot_id: uuid.UUID) -> ContextSnapshotRow | None:
    return session.get(ContextSnapshotRow, snapshot_id)
