from sqlalchemy.orm import Session

from ..models import AuditLog


def add_audit(
    session: Session,
    action: str,
    entity_id: int | str,
    before: dict | None,
    after: dict | None,
    entity_type: str = "record",
) -> None:
    """Record one administrator change; committed together with the change itself."""
    session.add(AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        actor="local-admin",
        before_data=before,
        after_data=after,
    ))
