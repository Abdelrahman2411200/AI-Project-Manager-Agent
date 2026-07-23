from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.audit import AuditEvent


class AuditRecorder:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(
        self,
        *,
        owner_id: UUID,
        actor_id: UUID | None,
        action: str,
        entity_type: str,
        request_id: str,
        project_id: UUID | None = None,
        entity_id: UUID | None = None,
        before_ref: dict[str, Any] | None = None,
        after_ref: dict[str, Any] | None = None,
        actor_type: str = "user",
    ) -> AuditEvent:
        event = AuditEvent(
            owner_id=owner_id,
            project_id=project_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_ref=before_ref,
            after_ref=after_ref,
            request_id=request_id,
        )
        self._session.add(event)
        return event
